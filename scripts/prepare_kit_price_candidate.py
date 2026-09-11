"""사용자가 선택한 시연용 고정가격: 2개 계약/36개 발주의 비설치 후보만 생성."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
import sys

from core.data_preparation.kit_procurement_reference_revision import _index, inspect_procurement, IDENTITIES
from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation.kit_logistics_revision import fingerprint
from core.data_preparation.snapshot_service import parse_csv
from scripts.prepare_kit_purchase_rehearsal import KIT, verified
from scripts.inspect_kit_raw_quality import STAGE
from scripts.plan_kit_price_basis import eligible_observation, review
from scripts.rehearse_kit_factory_connection import tables, digest

RULE = "synthetic-contract-start-fixed/1"
TARGET_IDS = {"CTR-00002", "CTR-00003"}


def rounded_prices(observed_value, premium_rate):
    """기존 2자리 기준가격 → 할증 적용 → 2자리 단가 순서를 Decimal로 명시한다."""
    value, premium = Decimal(observed_value), Decimal(premium_rate)
    if not value.is_finite() or value <= 0 or not premium.is_finite() or premium <= -1:
        raise ValueError("유한한 양수 가격과 유효한 할증률이 필요합니다")
    base = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    price = (base * (1 + premium)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    if base <= 0 or price <= 0:
        raise ValueError("반올림 후 양수 가격이 아닙니다")
    return format(base, ".2f"), format(price, ".2f")


def make_candidate(data, source_rows, selected):
    indexes = {k: _index(data[k], field) for k, field in IDENTITIES.items()}
    counts, _ = inspect_procurement(data)
    if any(counts.values()):
        raise ValueError("기존 참조/수량 대사 실패")
    keys = {(r["tenant_id"], r["contract_id"]) for r in selected}
    if len(selected) != 2 or len(keys) != 2 or {k[1] for k in keys} != TARGET_IDS or len({k[0] for k in keys}) != 1:
        raise ValueError("승인된 두 계약 범위만 가능합니다")
    _index(source_rows, "observation_id")
    source_tenants = {r["tenant_id"] for r in source_rows}
    if len(source_tenants) != 1:
        raise ValueError("가격 원천의 회사 문맥이 섞였습니다")
    by_contract = defaultdict(list)
    for order in data["PRC-02"]:
        by_contract[order["tenant_id"], order["contract_id"]].append(order)
    candidate = {"PRC-01": [], "PRC-02": []}
    evidence, changes, controls = [], [], []
    for key in sorted(keys):
        contract = indexes["PRC-01"][key]
        material = indexes["MDM-01"][key[0], contract["material_id"]]
        if contract["currency"] != "USD" or contract["quantity_uom"] != "TON" or material["base_uom"] != "TON":
            raise ValueError("통화/수량단위 환산은 승인 범위 밖입니다")
        if not material["benchmark_code"] or material["benchmark_code"] != contract["benchmark_code"]:
            raise ValueError("자재 가격지표 불일치")
        orders = by_contract[key]
        if len(orders) != 18 or any(r["scope_node_id"] != contract["scope_node_id"] for r in orders) or material["scope_node_id"] != contract["scope_node_id"]:
            raise ValueError("계약별 18행/공장 범위 불일치")
        for row in [contract, *orders]:
            if row["quality_status"] != "PENDING_VALIDATION" or row["certification_status"] != "UNVERIFIED_CANDIDATE":
                raise ValueError("미검증 후보만 허용합니다")
        observation = eligible_observation(source_rows, code=contract["benchmark_code"], pricing_date=contract["valid_from"])
        if not observation or observation["currency"] != "USD" or observation["unit"] != "USD/TON":
            raise ValueError("그 시점에 알려진 USD/TON 가격이 없습니다")
        base, price = rounded_prices(observation["value"], contract["premium_rate"])
        for dataset, rows, column, value in (("PRC-01", [contract], "benchmark_price", base), ("PRC-02", orders, "unit_price", price)):
            for row in rows:
                updated = {**row, column: value}
                candidate[dataset].append(updated)
                changes.append({"dataset": dataset, "object_id": row[IDENTITIES[dataset]], "tenant_id": row["tenant_id"],
                    "contract_id": key[1], "column": column, "before": row[column], "after": value,
                    "source_record_id": row["record_id"], "source_lineage_id": row["lineage_id"]})
        evidence.append({"contract_id": key[1], "tenant_id": key[0], "pricing_mode": "FIXED_AT_CONTRACT_START_DEMO",
            "pricing_date": contract["valid_from"], "rule_version": RULE,
            "material_price_basis": "SYNTHETIC_INDEX_PER_MATERIAL_TON_FOR_DEMO_ONLY",
            "real_grade_or_settlement_verified": False, "source_observation": dict(observation),
            "source_to_target_relation": "EXPLICIT_CANDIDATE_LINEAGE_ONLY_NOT_AUTHORIZED_SOURCE_BINDING",
            "benchmark_price": base, "premium_rate": contract["premium_rate"], "unit_price": price,
            "price_currency": "USD", "price_uom": "USD/TON", "fx_applied": False, "mass_conversion_applied": False,
            "rounding": "ROUND_HALF_EVEN; benchmark 0.01 then premium then unit_price 0.01"})
        quantity = sum(Decimal(r["order_quantity"]) for r in orders)
        controls.append({"contract_id": key[1], "orders": len(orders), "quantity": str(quantity), "quantity_uom": "TON",
            "currency": "USD", "old_unit_price_values": sorted({r["unit_price"] for r in orders}), "new_unit_price": price,
            "old_demo_order_amount": str(sum(Decimal(r["order_quantity"]) * Decimal(r["unit_price"]) for r in orders)),
            "new_demo_order_amount": str(quantity * Decimal(price)), "not_actual_savings": True})
    # 98건을 가격 보정된 자료에 포함하지 않는다. 전체 대사는 메모리에서만 한다.
    overlay = {**data}
    for dataset in candidate:
        field = IDENTITIES[dataset]
        patch = {(r["tenant_id"], r[field]): r for r in candidate[dataset]}
        overlay[dataset] = [patch.get((r["tenant_id"], r[field]), r) for r in data[dataset]]
    after, _ = inspect_procurement(overlay)
    if any(after.values()):
        raise ValueError("후보 참조/수량 대사 실패")
    held_contracts = [r["contract_id"] for r in data["PRC-01"] if (r["tenant_id"], r["contract_id"]) not in keys]
    held_orders = [r["po_line_id"] for r in data["PRC-02"] if (r["tenant_id"], r["contract_id"]) not in keys]
    return {"candidate_rows": candidate, "changes": changes, "pricing_evidence": evidence, "control_totals": controls,
        "held_contract_ids": held_contracts, "held_order_ids": held_orders,
        "hold_scope": "PRICE_CALCULATION_ONLY; source rows retained; enforcement not installed",
        "full_population_reconciliation": after}


def main():
    def readonly(event, args):
        if event == "sqlite3.connect" and not str(args[0]).endswith("?mode=ro"):
            raise PermissionError("비설치 후보는 DB에 쓰지 않습니다")
    sys.addaudithook(readonly)
    raw = verified(STAGE / "raw-result.json", "report_fingerprint")
    plan = verified(STAGE / "price-policy-review.json", "report_fingerprint")
    quality = verified(STAGE / "quality-result.json", "report_fingerprint")
    if plan["parent_raw_fingerprint"] != raw["report_fingerprint"] or plan["parent_quality_fingerprint"] != quality["report_fingerprint"]:
        raise ValueError("부모 문서 불일치")
    db = STAGE / "data_preparation.db"
    if digest(tables(db)) != raw["copy_table_fingerprint"]:
        raise ValueError("기존 사본 변경")
    data, raw_hashes = {}, {}
    for info in raw["snapshots"]:
        path = Path(info["raw_path"]).resolve()
        if not path.is_relative_to(STAGE.resolve()):
            raise ValueError("RAW 경로 변경")
        parsed = parse_csv(path.read_bytes(), file_name=path.name)
        if parsed.checksum != info["checksum"] or len(parsed.rows) != info["row_count"]:
            raise ValueError("RAW 지문/모수 변경")
        raw_hashes[str(path)] = parsed.checksum
        data.setdefault(info["dataset_contract_key"], []).extend(parsed.rows)
    _, source, _, files, errors = read_package(KIT, "full")
    if errors or any(files[k] != fp for k, fp in plan["source_files"].items()):
        raise ValueError("검토 원천 변경")
    recalculated = review(data, source)
    if recalculated["contracts"] != plan["contracts"]:
        raise ValueError("현재 원천에서 정책 검토를 재현할 수 없습니다")
    selected = [r for r in plan["contracts"] if r["route"] == "DEMO_INDEX_POLICY_PILOT_CANDIDATE"]
    result = make_candidate(data, source["EXT-02"], selected)
    if len(result["held_contract_ids"]) != 98 or len(result["held_order_ids"]) != 1764:
        raise ValueError("보류/후보 모집단 불일치")
    for change in result["changes"]:
        dataset = change["dataset"]
        key = IDENTITIES[dataset]
        old = next(r for r in data[dataset] if r[key] == change["object_id"] and r["tenant_id"] == change["tenant_id"])
        new = next(r for r in result["candidate_rows"][dataset] if r[key] == change["object_id"] and r["tenant_id"] == change["tenant_id"])
        if any(old[k] != new[k] for k in old if k != change["column"]):
            raise ValueError("가격 외 업무값 변경")
    if digest(tables(db)) != raw["copy_table_fingerprint"] or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != fp for p, fp in raw_hashes.items()):
        raise ValueError("기존 DB/RAW가 변경됐습니다")
    result.update({"status": "PREPARED_NOT_INSTALLED", "installed": False, "executable": False, "operational_approval": False,
        "user_authorization": "2026-09-11 사용자: 시연용 계약 시작일 고정가격의 2계약/36발주 비설치 후보 생성 승인. 원장/소유권/인증 승인이 아님",
        "rule_version": RULE, "parent_plan_fingerprint": plan["report_fingerprint"], "parent_raw_fingerprint": raw["report_fingerprint"],
        "candidate_rows_fingerprint": fingerprint(result["candidate_rows"]), "source_price_file": files["EXT-02"],
        "copy_fingerprint_before_and_after": raw["copy_table_fingerprint"], "raw_hashes_before_and_after": raw_hashes,
        "not_verified": ["real material grade/settlement basis", "certified target-context reference datasets", "ownership approval",
            "production calculation readiness", "previous full regression ledger sentinel error"],
        "next": "후보를 DB에 적용하기 전에 변경 단가의 후속 사용처와 파생 금액 일관성을 읽기 전용 점검"})
    result["proposal_fingerprint"] = fingerprint(result)
    with (STAGE / "price-candidate.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": result["status"], "candidate_counts": {k: len(v) for k, v in result["candidate_rows"].items()},
        "held_counts": [len(result["held_contract_ids"]), len(result["held_order_ids"])],
        "prices": [{k: e[k] for k in ("contract_id", "benchmark_price", "unit_price")} for e in result["pricing_evidence"]],
        "proposal_fingerprint": result["proposal_fingerprint"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
