"""K1-c2: 설치 DB를 읽기 전용으로 열고 물류 후보의 대입 영향을 조사한다.

출력은 검토 자료이며 설치·인증·승인 판정이 아니다. 제품 저장소의 초기화 경로를 호출하지 않는다.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import sqlite3

from core.data_preparation.kit_logistics_revision import KEYS, fingerprint
from core.data_preparation.kit_quantity_audit import inspect_quantity_flow
from core.data_preparation.kit_sample_audit import inspect_rows, read_package

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def readonly(path):
    # SQL 쓰기는 금지한다. WAL 모드에서는 SQLite가 빈 WAL/SHM을 만들 수 있으므로
    # 파일 무변경까지 보장하지 않으며, 별도 전후 지문으로 관측한다.
    conn = sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        yield conn
    finally:
        conn.close()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(rows, field):
    index = defaultdict(list)
    for row in rows:
        index[row["tenant_id"], row[field]].append(row)
    return index


def day(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def measured_relations(data, ownership, nodes, mode):
    """항목별 집계 단위를 고정한다. 오류 건수 합을 고유 오류 행수로 부르지 않는다."""
    counts, examples = Counter(), defaultdict(list)

    def hit(code, row, identity):
        counts[code] += 1
        if len(examples[code]) < 3:
            examples[code].append(row.get(identity, ""))

    contracts = unique(data["PRC-01"], "contract_id")
    orders = unique(data["PRC-02"], "po_line_id")
    ships = unique(data["LOG-02"], "shipment_id")
    suppliers = unique(data["MDM-02"], "supplier_id")
    ordered = defaultdict(Decimal)
    for row in data["PRC-02"]:
        parents = contracts.get((row["tenant_id"], row["contract_id"]), [])
        if len(parents) != 1:
            hit("PO_CONTRACT_NOT_UNIQUE", row, "po_line_id")
            continue
        parent = parents[0]
        if not day(parent["valid_from"]) <= day(row["order_date"]) <= day(parent["valid_to"]):
            hit("PO_OUTSIDE_CONTRACT_DATE", row, "po_line_id")
        for field in ("supplier_id", "material_id", "currency", "quantity_uom"):
            if row[field] != parent[field]:
                hit("PO_CONTRACT_" + field.upper(), row, "po_line_id")
        if row["quantity_uom"] == parent["quantity_uom"]:
            ordered[row["tenant_id"], row["contract_id"]] += Decimal(row["order_quantity"])
        owners = suppliers.get((row["tenant_id"], row["supplier_id"]), [])
        if len(owners) == 1 and row["material_id"] not in json.loads(owners[0]["material_ids"]):
            hit("PO_MATERIAL_NOT_IN_SUPPLIER_DECLARATION", row, "po_line_id")
    for key, amount in ordered.items():
        parent = contracts[key][0]
        if amount > Decimal(parent["contract_quantity"]):
            hit("CONTRACT_ORDER_QUANTITY_EXCEEDED", parent, "contract_id")
        if amount != Decimal(parent["ordered_quantity"]):
            hit("CONTRACT_ORDERED_TOTAL_DIFFERS", parent, "contract_id")

    for row in data["LOG-01"]:
        parents = orders.get((row["tenant_id"], row["business_ref"]), [])
        if len(parents) != 1:
            hit("SUBMISSION_PO_NOT_UNIQUE", row, "submission_id")
            continue
        if row["partner_id"] != parents[0]["supplier_id"]:
            hit("SUBMISSION_PARTNER_DIFFERS", row, "submission_id")
        if not row["submitted_at"]:
            hit("SUBMISSION_DATE_NOT_RECORDED", row, "submission_id")
        elif day(row["submitted_at"]) < day(parents[0]["order_date"]):
            hit("SUBMISSION_BEFORE_PO_DATE", row, "submission_id")

    # 입고는 회사·조직·선적·자재·창고·단위·날짜를 같은 키로 대조한다.
    receipts, deliveries = defaultdict(Decimal), defaultdict(Decimal)
    for row in data["INV-02"]:
        if row["movement_type"] == "PURCHASE_RECEIPT":
            key = (row["tenant_id"], row["scope_node_id"], row["reference_id"],
                   row["material_id"], row["to_location_id"], row["quantity_uom"],
                   str(day(row["movement_date"])))
            receipts[key] += Decimal(row["quantity"])
    for row in data["LOG-05"]:
        if row["event_type"] != "DELIVERED":
            continue
        parents = ships.get((row["tenant_id"], row["shipment_id"]), [])
        pos = orders.get((row["tenant_id"], parents[0]["po_line_id"]), []) if len(parents) == 1 else []
        if len(parents) != 1 or len(pos) != 1:
            hit("DELIVERY_PARENT_NOT_UNIQUE", row, "transport_event_id")
            continue
        key = (row["tenant_id"], row["scope_node_id"], row["shipment_id"],
               pos[0]["material_id"], row["destination_location_id"], row["quantity_uom"],
               str(day(row["event_at"])))
        deliveries[key] += Decimal(row["delivered_quantity"])
    counts["RECEIPT_BUCKETS"] = len(receipts)
    counts["DELIVERY_BUCKETS_RESOLVED"] = len(deliveries)
    counts["RECEIPT_WITHOUT_DELIVERY_BUCKET"] = len(receipts.keys() - deliveries.keys())
    counts["DELIVERY_WITHOUT_RECEIPT_BUCKET"] = len(deliveries.keys() - receipts.keys())
    common = receipts.keys() & deliveries.keys()
    counts["RECEIPT_DELIVERY_EQUAL_BUCKETS"] = sum(abs(receipts[k] - deliveries[k]) <= Decimal("0.001") for k in common)
    counts["RECEIPT_DELIVERY_QUANTITY_DIFFERS"] = sum(abs(receipts[k] - deliveries[k]) > Decimal("0.001") for k in common)

    coverage = defaultdict(Counter)
    declared = {(r["tenant_id"], r["entity_mode"], r["dataset_contract_key"], r["scope_node_id"])
                for r in ownership if r["status"] == "ACTIVE"}
    ecm = {(r["tenant_id"], r["node_id"]) for r in nodes if r["status"] == "ACTIVE"}
    for dataset in KEYS:
        for row in data[dataset]:
            scope = row["scope_node_id"]
            coverage[dataset][scope] += 1
            if (row["tenant_id"], mode, dataset, scope) not in declared:
                hit("OWNERSHIP_ACTIVE_ROW_MISSING", row, KEYS[dataset])
            if (row["tenant_id"], scope) not in ecm:
                hit("ECM_ACTIVE_NODE_MISSING", row, KEYS[dataset])

    events = defaultdict(lambda: defaultdict(list))
    for row in data["LOG-03"]:
        events[row["tenant_id"], row["shipment_id"]][row["event_type"]].append(row)
    event_order = ("BOOKED", "PICKED_UP", "ETD", "ETA", "ATA", "UNLOADED")
    for row in data["LOG-02"]:
        group = events[row["tenant_id"], row["shipment_id"]]
        if any(len(group[k]) != 1 for k in event_order):
            hit("SHIP_EVENT_SET_NOT_EXACTLY_SIX", row, "shipment_id")
            continue
        times = [datetime.fromisoformat(group[k][0]["actual_at"].replace("Z", "+00:00")) for k in event_order]
        if times != sorted(times):
            hit("SHIP_SYNTHETIC_EVENT_ORDER_DIFFERS", row, "shipment_id")
    return {"counts": dict(sorted(counts.items())), "examples": dict(examples),
            "scope_rows": {k: dict(v) for k, v in coverage.items()},
            "limitations": ["ownership counts ACTIVE rows only, not authority/ledger/effective-time verification",
                            "declared supplier material mismatch needs domain review, not automatic rejection",
                            "event order is this synthetic kit convention, not universal shipping policy",
                            "receipt bucket comparison does not certify unit conversions or stock balances"]}


def review(candidate_path, db_path, ecm_path, kit_root, instance_id):
    candidate_bytes = candidate_path.read_bytes()
    candidate = json.loads(candidate_bytes)
    claimed = candidate["proposal_fingerprint"]
    body = {k: v for k, v in candidate.items() if k != "proposal_fingerprint"}
    if claimed != fingerprint(body) or candidate["candidate_rows_fingerprint"] != fingerprint(candidate["candidate_rows"]):
        raise ValueError("후보 지문 불일치")
    if candidate["status"] != "REVIEW_ONLY" or candidate["installed"] is not False:
        raise ValueError("비설치 후보만 검토합니다")
    manifest, _, contracts, files, errors = read_package(kit_root, "full")
    if errors or candidate["source_files"] != {k: files[k] for k in KEYS}:
        raise ValueError("원본 판독 또는 지문 불일치")
    if candidate["manifest_fingerprint"] != fingerprint(manifest) or candidate["contracts_fingerprint"] != fingerprint({k: contracts[k] for k in KEYS}):
        raise ValueError("명세 또는 계약 변경을 다시 확인해야 합니다")
    paths = [db_path, Path(str(db_path) + "-wal"), ecm_path, Path(str(ecm_path) + "-wal")]
    before = {str(p): digest(p) if p.exists() else None for p in paths}
    with readonly(db_path) as conn:
        item = conn.execute("SELECT instance_id,tenant_id,entity_mode,scope_node_id,status FROM kit_instances WHERE instance_id=?", (instance_id,)).fetchone()
        if item is None:
            raise ValueError("지정한 설치 인스턴스가 없습니다")
        instance = dict(item)
        snapshots = [dict(r) for r in conn.execute(
            """SELECT s.dataset_contract_key,s.snapshot_id,s.raw_path,s.checksum,s.row_count
               FROM dataset_snapshots s JOIN source_bindings b ON s.binding_id=b.binding_id
               WHERE b.instance_id=? AND b.state='ACTIVE' AND s.state='DEMO_CERTIFIED' AND s.status='active'""", (instance_id,))]
        ownership = [dict(r) for r in conn.execute(
            "SELECT tenant_id,entity_mode,dataset_contract_key,scope_node_id,status FROM dataset_ownership_bindings WHERE tenant_id=?", (instance["tenant_id"],))]
        approvals = []
        for row in conn.execute("SELECT ref,status,binding_json,valid_until FROM calc_execution_approvals WHERE tenant_id=?", (instance["tenant_id"],)):
            binding = json.loads(row["binding_json"])
            approvals.append({"ref": row["ref"], "status": row["status"], "valid_until": row["valid_until"],
                              "snapshots": binding["snapshots"],
                              "replacement_keys": sorted(set(binding["snapshots"]) & KEYS.keys())})
        apps = []
        for row in conn.execute("SELECT contract_json FROM kit_app_contracts WHERE instance_id=?", (instance_id,)):
            app = json.loads(row["contract_json"])
            datasets = sorted(d["enterprise_contract_key"] for d in app["datasets"] if d.get("enterprise_contract_key"))
            apps.append({"contract_id": app["contract_id"], "status": app["status"], "datasets": datasets,
                         "replacement_keys": sorted(set(datasets) & KEYS.keys())})
        baselines = []
        for row in conn.execute("SELECT build_id,status,detail_json FROM baseline_builds WHERE instance_id=?", (instance_id,)):
            d = json.loads(row["detail_json"])
            baselines.append({"build_id": row["build_id"], "status": row["status"],
                              "sales_allocation": d.get("sales_allocation"),
                              "baseline_recognition": d.get("baseline_recognition")})
    with readonly(ecm_path) as conn:
        nodes = [dict(r) for r in conn.execute("SELECT tenant_id,node_id,status FROM organization_nodes WHERE tenant_id=?", (instance["tenant_id"],))]
        results = [dict(r) for r in conn.execute("SELECT result_id,snapshot_id,computed_at FROM scenario_results WHERE tenant_id=?", (instance["tenant_id"],))]
    current = {}
    for snap in snapshots:
        key = snap["dataset_contract_key"]
        if key in current:
            raise ValueError("인증판이 여러 개여서 선택할 수 없습니다: " + key)
        raw = Path(snap["raw_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != snap["checksum"]:
            raise ValueError("RAW 체크섬 불일치: " + key)
        current[key] = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
        if len(current[key]) != snap["row_count"]:
            raise ValueError("RAW 행수 불일치: " + key)
    if set(current) != set(contracts):
        raise ValueError("설치 자료와 계약 집합이 일치하지 않습니다")
    overlaid = {**current, **candidate["candidate_rows"]}
    comparisons = {}
    for name, data in (("installed", current), ("candidate_overlay", overlaid)):
        issues = inspect_rows(data, contracts)
        quantities = inspect_quantity_flow(data)
        comparisons[name] = measured_relations(data, ownership, nodes, instance["entity_mode"])
        comparisons[name]["existing_row_audit_counts"] = dict(Counter(i["code"] for i in issues))
        comparisons[name]["existing_quantity_audit_counts"] = quantities["issue_counts"]
    identity_changes = {}
    for k, field in KEYS.items():
        old, new = set(unique(current[k], field)), set(unique(overlaid[k], field))
        identity_changes[k] = {"old": len(old), "new": len(new), "removed": len(old-new), "added": len(new-old)}
    after = {str(p): digest(p) if p.exists() else None for p in paths}
    raw_changed = [s["snapshot_id"] for s in snapshots if digest(Path(s["raw_path"])) != s["checksum"]]
    return {"status": "REVIEW_ONLY", "proposal_fingerprint": claimed,
            "candidate_file_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
            "instance": instance, "snapshot_count": len(snapshots), "raw_checksums_verified": len(snapshots),
            "snapshots": snapshots, "identity_changes": identity_changes, "comparisons": comparisons,
            "calculation_approvals": approvals, "app_contracts": apps, "baselines": baselines,
            "ecm_scenario_result_count": len(results),
            "invariants": {"selected_db_files_before": before, "selected_db_files_after": after,
                           "selected_db_files_unchanged": before == after, "raw_changed": raw_changed},
            "not_verified": ["cross-database atomic snapshot", "runtime authorization and approval ledger replay",
                             "all stored calculation/decision/publication references", "installation", "browser"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True, help="새 검토 JSON만 기록. 기존 파일은 덮어쓰지 않습니다")
    args = parser.parse_args()
    # 검토 결과도 운영 자료 폴더에 새 데이터로 만들지 않는다.
    if not args.report.resolve().is_relative_to((ROOT / "output").resolve()):
        parser.error("보고서는 저장소 output/ 아래 새 파일로만 저장합니다")
    report = review(args.candidate, ROOT / "data/data_preparation.db", ROOT / "data/enterprise_context.db",
                    ROOT / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0", "ki_6b06ffb50a994a")
    with args.report.open("x", encoding="utf-8") as out:
        json.dump(report, out, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in {"snapshots", "invariants", "app_contracts"}}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
