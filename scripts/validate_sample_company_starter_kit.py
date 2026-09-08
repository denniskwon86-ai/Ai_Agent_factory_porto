#!/usr/bin/env python3
"""AFS 샘플 회사 Starter Kit 계약·참조·대사 검증기."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data_preparation.production_inputs import modern, verify_model


ROOT = Path(__file__).resolve().parents[1]
KIT_ID = "KIT-MFG-NONFERROUS-PROCUREMENT"
KIT_VERSION = "1.0.0"
KIT_ROOT = ROOT / "starter_kits" / KIT_ID / KIT_VERSION
COMMON = {"record_id", "tenant_id", "scope_node_id", "data_class", "business_data_kind",
          "data_origin", "quality_status", "certification_status", "as_of_date", "lineage_id"}


def read_csv(profile: str, dataset_id: str) -> List[Dict[str, str]]:
    path = KIT_ROOT / "samples" / profile / f"{dataset_id}.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f(v: Any) -> float:
    return float(v or 0)


class Validation:
    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: str = "", *, severity: str = "ERROR") -> None:
        self.checks.append({"check": name, "status": "PASS" if ok else "FAIL",
                            "severity": severity, "detail": detail})

    @property
    def passed(self) -> bool:
        return not any(c["status"] == "FAIL" and c["severity"] == "ERROR" for c in self.checks)


def production_model_errors(data):
    bad = []
    for row in data.get("MFG-02", []):
        try:
            if modern(row):
                verify_model(row, data.get("MDM-05", []), data.get("MDM-01", []))
            elif abs(f(row["output_quantity"]) / max(f(row["input_quantity"]), 1e-9) - f(row["actual_yield"])) > 0.002:
                raise ValueError("legacy yield mismatch")
        except (ValueError, KeyError, ArithmeticError):
            bad.append(row.get("batch_id"))
    return bad


def validate_profile(profile: str, dataset_ids: Sequence[str], v: Validation) -> Dict[str, int]:
    data = {ds: read_csv(profile, ds) for ds in dataset_ids}
    counts = {ds: len(rows) for ds, rows in data.items()}
    v.check(f"{profile}:35개 데이터 파일", len(data) == 35 and all(counts.values()),
            f"files={len(data)}, empty={[k for k,x in counts.items() if not x]}")
    for ds, rows in data.items():
        headers = set(rows[0]) if rows else set()
        v.check(f"{profile}:{ds}:공통필드", COMMON <= headers, f"missing={sorted(COMMON-headers)}")
        bad = [r["record_id"] for r in rows if r.get("data_class") != "SYNTHETIC" or r.get("data_origin") != "SYNTHETIC"]
        v.check(f"{profile}:{ds}:합성표시", not bad, f"bad={bad[:5]}")
        ids = [r["record_id"] for r in rows]
        v.check(f"{profile}:{ds}:record_id고유", len(ids) == len(set(ids)), f"rows={len(ids)}, unique={len(set(ids))}")
        v.check(f"{profile}:{ds}:scope필수", all(r.get("scope_node_id") for r in rows))

    # Organization cycle and parent integrity.
    org = data["FND-01"]
    org_ids = {r["node_id"] for r in org}
    parents = {r["node_id"]: r.get("parent_id", "") for r in org}
    v.check(f"{profile}:조직부모참조", all(not p or p in org_ids for p in parents.values()))
    cyclic = []
    for node in org_ids:
        seen = set()
        cur = node
        while cur and cur in parents:
            if cur in seen:
                cyclic.append(node); break
            seen.add(cur); cur = parents[cur]
    v.check(f"{profile}:조직순환없음", not cyclic, f"cyclic={cyclic[:5]}")

    # MDM references.
    materials = {r["material_id"] for r in data["MDM-01"]}
    suppliers = {r["supplier_id"] for r in data["MDM-02"]}
    customers = {r["customer_id"] for r in data["MDM-03"]}
    locations = {r["location_id"] for r in data["MDM-04"]}
    v.check(f"{profile}:BOM품목참조", all(r["output_material_id"] in materials and r["input_material_id"] in materials for r in data["MDM-05"]))
    v.check(f"{profile}:판매고객품목참조", all(r["customer_id"] in customers and r["product_id"] in materials for r in data["SLS-01"]))

    # Contract → PO → Shipment.
    contracts = {r["contract_id"]: r for r in data["PRC-01"]}
    pos = {r["po_line_id"]: r for r in data["PRC-02"]}
    v.check(f"{profile}:계약공급사품목참조", all(r["supplier_id"] in suppliers and r["material_id"] in materials for r in contracts.values()))
    v.check(f"{profile}:PO계약참조", all(r["contract_id"] in contracts for r in pos.values()))
    ordered = defaultdict(float)
    for p in pos.values():
        ordered[p["contract_id"]] += f(p["order_quantity"])
    over = {cid: (qty, f(contracts[cid]["contract_quantity"])) for cid, qty in ordered.items()
            if qty > f(contracts[cid]["contract_quantity"]) + 0.001}
    v.check(f"{profile}:계약량소진", not over, f"over={list(over.items())[:3]}")
    shipments = {r["shipment_id"]: r for r in data["LOG-02"]}
    v.check(f"{profile}:선적PO참조", all(r["po_line_id"] in pos for r in shipments.values()))
    bad_qty = [sid for sid, s in shipments.items() if f(s["shipment_quantity"]) > f(pos[s["po_line_id"]]["order_quantity"]) + 0.001]
    v.check(f"{profile}:선적수량", not bad_qty, f"bad={bad_qty[:5]}")

    # Milestone order.
    event_order = {"BOOKED": 1, "PICKED_UP": 2, "ETD": 3, "ETA": 4, "ATA": 5, "UNLOADED": 6}
    milestones = defaultdict(list)
    for r in data["LOG-03"]:
        milestones[r["shipment_id"]].append(r)
    bad_events = []
    for sid, rows in milestones.items():
        if sid not in shipments:
            bad_events.append((sid, "missing_shipment")); continue
        seq = [event_order.get(r["event_type"], 99) for r in rows]
        if seq != sorted(seq):
            bad_events.append((sid, "sequence"))
        actuals = [r["actual_at"] for r in sorted(rows, key=lambda x: event_order.get(x["event_type"], 99))]
        if actuals != sorted(actuals):
            bad_events.append((sid, "time"))
    v.check(f"{profile}:물류사건순서", not bad_events, f"bad={bad_events[:5]}")
    v.check(f"{profile}:통관선적참조", all(r["shipment_id"] in shipments for r in data["LOG-04"]))
    v.check(f"{profile}:운송선적위치참조", all(r["shipment_id"] in shipments and r["destination_location_id"] in locations for r in data["LOG-05"]))

    # Production references and yield conservation.
    plans = {r["plan_line_id"]: r for r in data["MFG-01"]}
    batches = data["MFG-02"]
    v.check(f"{profile}:생산계획참조", all(r["plan_line_id"] in plans for r in batches))
    bad_yield = production_model_errors(data)
    v.check(f"{profile}:생산수율대사", not bad_yield, f"bad={bad_yield[:5]}")

    # Inventory movement → monthly snapshot equality.
    movements = sorted(data["INV-02"], key=lambda r: (r["movement_date"], r["movement_id"]))
    snapshots_by_date = defaultdict(list)
    for r in data["INV-01"]:
        snapshots_by_date[r["snapshot_date"]].append(r)
    balance = defaultdict(float)
    idx = 0
    bad_snapshot = []
    excluded = {"", "PRODUCTION", "CUSTOMER", "IN_TRANSIT", "ADJUSTMENT"}
    for snap_date in sorted(snapshots_by_date):
        while idx < len(movements) and movements[idx]["movement_date"] <= snap_date:
            m = movements[idx]
            loc = m["from_location_id"] if m["movement_type"] in {"PRODUCTION_ISSUE", "SALES_SHIPMENT"} else m["to_location_id"]
            if loc not in excluded:
                balance[(m["material_id"], loc)] += f(m["quantity"])
            idx += 1
        for r in snapshots_by_date[snap_date]:
            delta = balance[(r["material_id"], r["location_id"])] - f(r["unrestricted_quantity"])
            if abs(delta) > 0.002:
                bad_snapshot.append((r["snapshot_id"], round(delta, 4)))
                if len(bad_snapshot) >= 5: break
        if bad_snapshot: break
    v.check(f"{profile}:재고월말대사", not bad_snapshot, f"bad={bad_snapshot}")

    # Financial documents balance.
    gl = defaultdict(lambda: [0.0, 0.0])
    for r in data["FIN-03"]:
        gl[r["document_id"]][0] += f(r["debit_amount"])
        gl[r["document_id"]][1] += f(r["credit_amount"])
    unbalanced = [(doc, round(x[0]-x[1], 2)) for doc, x in gl.items() if abs(x[0]-x[1]) > 0.01]
    v.check(f"{profile}:재무차대대사", not unbalanced, f"bad={unbalanced[:5]}")
    fin_refs = {r["reference_id"] for r in data["FIN-02"]}
    source_refs = set(pos) | {r["sales_line_id"] for r in data["SLS-01"]}
    v.check(f"{profile}:APAR원천참조", fin_refs <= source_refs, f"missing={list(fin_refs-source_refs)[:5]}")

    v.check(f"{profile}:시나리오10개", len(data["SIM-02"]) == 10, f"count={len(data['SIM-02'])}")
    v.check(f"{profile}:결정샘플3개", len(data["DEC-01"]) == 3, f"count={len(data['DEC-01'])}")
    return counts


def main() -> None:
    manifest_path = KIT_ROOT / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("manifest.json이 없습니다. 생성기를 먼저 실행하십시오.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ids = [d["dataset_id"] for d in manifest["datasets"]]
    v = Validation()
    v.check("manifest:kit_id", manifest.get("kit_id") == KIT_ID)
    v.check("manifest:version", manifest.get("version") == KIT_VERSION)
    v.check("manifest:35개", len(ids) == 35 and len(set(ids)) == 35, f"count={len(ids)}")
    v.check("manifest:SYNTHETIC", manifest.get("data_class") == "SYNTHETIC" and manifest.get("not_for_management_decision") is True)
    counts = {p: validate_profile(p, ids, v) for p in ("quick", "full")}
    contracts = list((KIT_ROOT / "contracts").glob("*.contract.json"))
    v.check("계약:35개", len(contracts) == 35, f"count={len(contracts)}")
    for cpath in contracts:
        c = json.loads(cpath.read_text(encoding="utf-8"))
        v.check(f"계약:{cpath.stem}:합성표시", c.get("classification", {}).get("data_class") == "SYNTHETIC")
        v.check(f"계약:{cpath.stem}:scope필수", c.get("quality", {}).get("fail_closed_on_scope_missing") is True)

    company_profile_paths = sorted((KIT_ROOT / "company_profiles").glob("*.json"))
    company_profiles = [json.loads(path.read_text(encoding="utf-8")) for path in company_profile_paths]
    profile_ids = [row.get("company_profile_id") for row in company_profiles]
    v.check("가상회사:6개", len(company_profiles) == 6, f"count={len(company_profiles)}")
    v.check("가상회사:ID고유", len(profile_ids) == len(set(profile_ids)))
    v.check("가상회사:합성격리", all(row.get("entity_mode") == "VIRTUAL" and
                                    row.get("data_class") == "SYNTHETIC" and
                                    row.get("not_for_management_decision") is True
                                    for row in company_profiles))
    v.check("가상회사:추가5개원본", all(row.get("source_profile_id")
                                      for row in company_profiles
                                      if row.get("profile_role") != "BASE_SAMPLE_COMPANY"))
    v.check("가상회사:목적·조직·가정", all(row.get("purpose") and row.get("organization_blueprint") and
                                         row.get("default_assumptions") for row in company_profiles))

    quarantine_root = KIT_ROOT / "samples" / "full" / "quarantine"
    quarantine_manifest_path = quarantine_root / "expected_quarantine_manifest.json"
    quarantine_candidates_path = quarantine_root / "candidates.csv"
    v.check("격리:manifest존재", quarantine_manifest_path.exists())
    v.check("격리:candidates존재", quarantine_candidates_path.exists())
    if quarantine_manifest_path.exists() and quarantine_candidates_path.exists():
        quarantine_manifest = json.loads(quarantine_manifest_path.read_text(encoding="utf-8"))
        with quarantine_candidates_path.open("r", encoding="utf-8-sig", newline="") as stream:
            quarantine_rows = list(csv.DictReader(stream))
        actual_by_reason = defaultdict(int)
        for row in quarantine_rows:
            actual_by_reason[row["reason_code"]] += 1
        expected_by_reason = {
            item["reason_code"]: int(item["expected_count"])
            for item in quarantine_manifest.get("expected_by_reason", [])
        }
        v.check("격리:예상총건수", len(quarantine_rows) == int(quarantine_manifest.get("expected_total", -1)),
                f"actual={len(quarantine_rows)} expected={quarantine_manifest.get('expected_total')}")
        v.check("격리:사유별건수", dict(actual_by_reason) == expected_by_reason,
                f"actual={dict(actual_by_reason)} expected={expected_by_reason}")
        v.check("격리:합성표시", all(row.get("data_class") == "SYNTHETIC" and
                                     row.get("expected_disposition") == "QUARANTINE"
                                     for row in quarantine_rows))

    report = {
        "kit_id": KIT_ID, "version": KIT_VERSION,
        "validated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS" if v.passed else "FAIL",
        "summary": {"checks": len(v.checks), "passed": sum(c["status"] == "PASS" for c in v.checks),
                    "failed": sum(c["status"] == "FAIL" for c in v.checks),
                    "quick_rows": sum(counts["quick"].values()), "full_rows": sum(counts["full"].values())},
        "checks": v.checks,
    }
    out = KIT_ROOT / "validations" / "validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if v.passed:
        manifest["status"] = "VALIDATED_FOR_DEMO"
        manifest["validation"] = {
            "status": "PASS",
            "report_path": out.relative_to(KIT_ROOT).as_posix(),
            "checks": report["summary"]["checks"],
            "validated_at": report["validated_at"],
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"] | {"status": report["status"], "report": str(out)}, ensure_ascii=False, indent=2))
    if not v.passed:
        for c in v.checks:
            if c["status"] == "FAIL":
                print(f"FAIL {c['check']}: {c['detail']}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
