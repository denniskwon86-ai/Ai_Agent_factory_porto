"""K1-c7d: 저장된 RAW 품질·의존성 진단. DB/RAW/승인 상태는 변경하지 않는다."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from core.data_preparation.kit_sample_audit import read_package, inspect_rows
from core.data_preparation.kit_procurement_reference_revision import inspect_procurement, IDENTITIES
from core.data_preparation.snapshot_service import parse_csv, profile_rows
from core.data_preparation.kit_logistics_revision import fingerprint
from scripts.prepare_kit_purchase_rehearsal import KIT, RUN, verified
from scripts.rehearse_kit_factory_connection import ROOT, tables, digest, ro

STAGE = RUN / "raw-stage-5rsqiaph"


def field_profile(rows, contract):
    """빈 선택값과 필수 누락을 구분한다. 관측 코드 목록은 승인된 코드표가 아니다."""
    fields = contract["schema"]["fields"]
    columns = [f["name"] for f in fields]
    profile = profile_rows(rows, columns)
    profile["missing_required"] = {f["name"]: profile["missing"][f["name"]] for f in fields
        if f.get("required") and profile["missing"][f["name"]]}
    invalid = []
    for i, row in enumerate(rows, 2):
        for field in fields:
            name, kind = field["name"], field["type"]
            value = row.get(name, "")
            if not str(value).strip():
                continue
            try:
                if kind in {"integer", "number"}:
                    number = Decimal(value)
                    if not number.is_finite() or (kind == "integer" and number != number.to_integral_value()):
                        raise ValueError("유한한 수 또는 정수가 아닙니다")
                elif kind == "boolean":
                    if value.lower() not in {"true", "false"}:
                        raise ValueError("boolean 아님")
                elif kind != "string":
                    raise ValueError("점검기 미지원 자료형")
                if name.endswith("_date") or name in {"valid_from", "valid_to"}:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("ISO 날짜 아님")
                if field.get("enum") is not None and value not in field["enum"]:
                    raise ValueError("계약 enum 밖 값")
            except (ValueError, InvalidOperation, TypeError):
                invalid.append({"line_in_combined_dataset": i, "field": name, "declared_type": kind})
    profile["invalid_values"] = invalid
    profile["observed_codes"] = {f: dict(Counter(row.get(f, "") for row in rows)) for f in
        ("base_uom", "quantity_uom", "currency", "material_type", "benchmark_code", "incoterm", "payment_terms", "status", "active")
        if f in columns}
    profile["declared_enum_fields"] = [f["name"] for f in fields if f.get("enum") is not None]
    return profile


def price_basis_review(data, source_benchmarks):
    """이전 문맥 원천은 의미 대조에만 사용한다. 새 문맥 참조를 충족시키지 않는다."""
    dimensions = defaultdict(set)
    for row in source_benchmarks:
        dimensions[row["commodity_code"]].add((row["currency"], row["unit"]))
    flags, counts = {}, Counter()
    contracts = {(r["tenant_id"], r["contract_id"]): r for r in data["PRC-01"]}
    for key, row in contracts.items():
        options = dimensions.get(row["benchmark_code"], set())
        reasons = []
        if len(options) != 1:
            reasons.append("SOURCE_PRICE_DIMENSION_MISSING_OR_AMBIGUOUS")
        else:
            currency, unit = next(iter(options))
            numerator, separator, denominator = unit.partition("/")
            if not separator or not denominator or numerator != currency:
                reasons.append("SOURCE_PRICE_UNIT_UNSUPPORTED")
            else:
                if row["currency"] != currency:
                    reasons.append("PRICE_CURRENCY_CONVERSION_UNEVIDENCED")
                if row["quantity_uom"] != denominator:
                    reasons.append("PRICE_QUANTITY_CONVERSION_UNEVIDENCED")
        if reasons:
            flags[key] = reasons
            counts.update(reasons)
    impacted_orders, formula_matches = [], 0
    for row in data["PRC-02"]:
        key = row["tenant_id"], row["contract_id"]
        if key in flags:
            impacted_orders.append(row["po_line_id"])
        c = contracts.get(key)
        if c and c["price_formula"] == "BENCHMARK_PRICE*(1+PREMIUM_RATE)":
            try:
                expected = Decimal(c["benchmark_price"]) * (1 + Decimal(c["premium_rate"]))
                if abs(Decimal(row["unit_price"]) - expected) <= Decimal("0.005"):
                    formula_matches += 1
            except (InvalidOperation, ValueError):
                pass  # 자료형 오류는 field_profile에서 별도로 기록한다.
    return {"basis": "SOURCE_CATALOG_COMPARISON_ONLY_NOT_CONTEXT_BINDING", "contract_reason_counts": dict(counts),
        "affected_contract_count": len(flags), "affected_order_count": len(impacted_orders),
        "affected_contracts": [{"tenant_id": k[0], "contract_id": k[1], "reasons": v} for k, v in sorted(flags.items())],
        "affected_order_ids": impacted_orders, "unconverted_formula_match_count": formula_matches,
        "formula_tolerance": "0.005", "not_verified": ["approved conversion", "observation/vintage/date binding", "corrected monetary values"]}


def main():
    def readonly(event, args):
        if event == "sqlite3.connect" and not str(args[0]).endswith("?mode=ro"):
            raise PermissionError("품질 점검은 SQLite 읽기 전용입니다")
    sys.addaudithook(readonly)
    report = verified(STAGE / "raw-result.json", "report_fingerprint")
    connection = verified(RUN / "result.json", "report_fingerprint")
    if report["parent_connection_fingerprint"] != connection["report_fingerprint"]:
        raise ValueError("연결 부모 변경")
    protected = {"raw_copy": Path(report["copy_path"]), "installation_preparation": ROOT / "data/data_preparation.db",
        "installation_master": ROOT / "data/master/master.db", "installation_ecm": ROOT / "data/enterprise_context.db",
        "installation_ledger": ROOT / "data/decision_ledger.db",
        **{f"organization_copy_{k}": Path(v) for k, v in connection["copy_paths"].items()}}
    before = {k: digest(tables(p)) for k, p in protected.items()}
    if before["raw_copy"] != report["copy_table_fingerprint"] or any(
        before[f"organization_copy_{k}"] != v for k, v in connection["copy_table_fingerprints"].items()):
        raise ValueError("기존 사본 지문 변경")
    data, per_snapshot, raw_fingerprints = {}, [], {}
    with closing(ro(protected["raw_copy"])) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        for info in report["snapshots"]:
            snapshot = dict(conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?", (info["snapshot_id"],)).fetchone())
            binding = dict(conn.execute("SELECT * FROM source_bindings WHERE binding_id=?", (info["binding_id"],)).fetchone())
            instance = dict(conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (info["instance_id"],)).fetchone())
            if snapshot["state"] != "RAW" or binding["state"] != "DRAFT" or snapshot["data_kind"] != "DEMO/SYNTHETIC" or snapshot["certified_at"]:
                raise ValueError("RAW/DRAFT 상태 변경")
            if any(snapshot[k] != binding[k] or snapshot[k] != instance[k] for k in ("instance_id", "tenant_id", "scope_node_id", "entity_mode")):
                raise ValueError("판/결속/인스턴스 문맥 불일치")
            path = Path(snapshot["raw_path"]).resolve()
            if not path.is_relative_to(STAGE.resolve()):
                raise ValueError("RAW 경로가 사본 밖입니다")
            payload = path.read_bytes()
            parsed = parse_csv(payload, file_name=path.name)
            if parsed.checksum != info["checksum"] or parsed.checksum != snapshot["checksum"] or parsed.checksum != snapshot["content_fingerprint"]:
                raise ValueError("RAW 지문 변경")
            if len(parsed.rows) != snapshot["row_count"] or len(payload) != snapshot["byte_size"]:
                raise ValueError("RAW 모수/크기 변경")
            if any(r["tenant_id"] != snapshot["tenant_id"] or r["scope_node_id"] != snapshot["scope_node_id"] for r in parsed.rows):
                raise ValueError("RAW 행 문맥 변경")
            raw_fingerprints[str(path)] = parsed.checksum
            data.setdefault(snapshot["dataset_contract_key"], []).extend(parsed.rows)
            per_snapshot.append({"snapshot_id": snapshot["snapshot_id"], "dataset": snapshot["dataset_contract_key"],
                "scope_node_id": snapshot["scope_node_id"], "profile": profile_rows(parsed.rows, parsed.columns)})
        inventory = [dict(r) for r in conn.execute("SELECT dataset_contract_key,tenant_id,scope_node_id,entity_mode,state,row_count FROM dataset_snapshots")]
    if {k: len(v) for k, v in data.items()} != {"MDM-01": 220, "MDM-02": 40, "PRC-01": 100, "PRC-02": 1800} or len(per_snapshot) != 7:
        raise ValueError("대상 모수 변경")
    manifest, source, contracts, files, errors = read_package(KIT, "full")
    if errors:
        raise ValueError("의존성 원천을 읽을 수 없습니다")
    selected = {k: contracts[k] for k in data}
    profiles = {k: field_profile(rows, selected[k]) for k, rows in data.items()}
    issues = inspect_rows(data, selected)
    counts, _ = inspect_procurement(data)
    missing = sorted(set(d for k in data for d in contracts[k]["dependencies"]) - set(data))
    tenant = report["snapshots"][0]["tenant_id"]
    dependencies = [{"dataset": k, "name": contracts[k]["dataset_name"], "required_by": [d for d in data if k in contracts[d]["dependencies"]],
        "source_full_rows": len(source[k]), "source_file": files[k],
        "source_scopes": dict(Counter(r["scope_node_id"] for r in source[k])),
        "observed_snapshot_metadata": [r for r in inventory if r["dataset_contract_key"] == k],
        "target_context_snapshot_count": sum(r["dataset_contract_key"] == k and r["tenant_id"] == tenant and r["entity_mode"] == "REAL" for r in inventory),
        "dependencies": contracts[k]["dependencies"], "certified_usable": False} for k in missing]
    org = connection["copy_paths"]["ecm"]
    with closing(ro(Path(org))) as conn:
        matched = {s: conn.execute("SELECT count(*) FROM organization_nodes WHERE tenant_id=? AND node_id=? AND status='ACTIVE'",
                   (tenant, s)).fetchone()[0] for s in {r["scope_node_id"] for rows in data.values() for r in rows}}
    prices = price_basis_review(data, source["EXT-02"])
    material_index = {(r["tenant_id"], r["material_id"]): r for r in data["MDM-01"]}
    material_checks = {"contract_uom_mismatch": sum(r["quantity_uom"] != material_index[(r["tenant_id"], r["material_id"])]["base_uom"] for r in data["PRC-01"]),
        "contracts_using_inactive_material": sum(material_index[(r["tenant_id"], r["material_id"])]["active"].lower() != "true" for r in data["PRC-01"])}
    if any(digest(tables(p)) != before[k] for k, p in protected.items()):
        raise ValueError("점검 중 DB 지문 변경")
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != fp for p, fp in raw_fingerprints.items()):
        raise ValueError("점검 중 RAW 변경")
    result = {"status": "INSPECTED_WITH_OPEN_ISSUES", "installed": False, "executable": False, "certified": False,
        "parent_raw_fingerprint": report["report_fingerprint"], "per_snapshot": per_snapshot, "dataset_profiles": profiles,
        "contracts_fingerprint": fingerprint(selected), "source_manifest_fingerprint": fingerprint(manifest),
        "source_benchmark_file": files["EXT-02"], "core_audit_issue_counts": dict(Counter(i["code"] for i in issues)),
        "core_audit_issue_examples": issues[:10], "procurement_reconciliation": counts, "material_checks": material_checks,
        "dependency_inventory": dependencies, "price_basis_review": prices, "active_ecm_scope_match_counts": matched,
        "scope_note": "ECM 노드 존재는 FND-01의 새 문맥 판/권한/역사적 유효기간 검증을 대신하지 않는다",
        "db_fingerprints_before_and_after": before, "raw_checksums_before_and_after": raw_fingerprints,
        "not_verified": ["ownership approval", "all declared dependencies certified", "observation date binding", "HTTP/browser", "corrected price calculation"],
        "next": "가격 단위·통화 보정 방안 검토와 누락 선행자료 연결 계획; 원문/상태 자동 수정 금지"}
    result["report_fingerprint"] = fingerprint(result)
    with (STAGE / "quality-result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": result["status"], "row_counts": {k: p["row_count"] for k, p in profiles.items()},
        "missing_required": sum(sum(p["missing_required"].values()) for p in profiles.values()),
        "invalid_values": sum(len(p["invalid_values"]) for p in profiles.values()), "core_audit_issue_counts": result["core_audit_issue_counts"],
        "price_contracts": prices["affected_contract_count"], "price_orders": prices["affected_order_count"],
        "price_reasons": prices["contract_reason_counts"], "missing_dependencies": missing, "report_fingerprint": result["report_fingerprint"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
