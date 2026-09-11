"""K1-c7e: 가격 기준 변경 방안만 작성한다. 새 가격·RAW·인증판은 만들지 않는다."""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation.snapshot_service import parse_csv
from core.data_preparation.kit_logistics_revision import fingerprint
from scripts.prepare_kit_purchase_rehearsal import KIT, RUN, verified
from scripts.inspect_kit_raw_quality import STAGE
from scripts.rehearse_kit_factory_connection import tables, digest


def eligible_observation(rows, *, code, pricing_date):
    """검토용 계약 고정일 가정. 관측/공표/vintage 모두 컷오프 이하여야 한다."""
    cutoff = date.fromisoformat(pricing_date)
    eligible = []
    for row in rows:
        if row["commodity_code"] != code:
            continue
        times = tuple(date.fromisoformat(row[k]) for k in ("observed_at", "published_at", "vintage_date"))
        if max(times) <= cutoff:
            eligible.append((times, row))
    if not eligible:
        return None
    newest = max(times for times, _ in eligible)
    matches = [row for times, row in eligible if times == newest]
    if len(matches) != 1:
        raise ValueError("같은 관측시점의 원천이 중복/모호합니다")
    return matches[0]


def review(data, source):
    materials = {(r["tenant_id"], r["material_id"]): r for r in data["MDM-01"]}
    orders = defaultdict(list)
    for r in data["PRC-02"]:
        orders[r["tenant_id"], r["contract_id"]].append(r)
    plan_rows, dimensions, material_codes = [], Counter(), Counter()
    future_contracts = future_orders = 0
    for contract in data["PRC-01"]:
        key = contract["tenant_id"], contract["contract_id"]
        material = materials[contract["tenant_id"], contract["material_id"]]
        dimensions[contract["currency"], contract["quantity_uom"]] += 1
        material_code = material["benchmark_code"]
        match = "EMPTY" if not material_code else "EXACT" if material_code == contract["benchmark_code"] else "DIFFERENT"
        material_codes[match] += 1
        matching = [r for r in source["EXT-02"] if r["commodity_code"] == contract["benchmark_code"]
                    and abs(Decimal(r["value"]) - Decimal(contract["benchmark_price"])) <= Decimal("0.005")]
        future = None
        if len(matching) == 1:
            latest_known = max(matching[0][k] for k in ("observed_at", "published_at", "vintage_date"))
            future = latest_known > contract["valid_from"]
            future_contracts += int(future)
            future_orders += sum(r["order_date"] < latest_known for r in orders[key])
        compatible = contract["currency"] == "USD" and contract["quantity_uom"] == "TON"
        route = "DEMO_INDEX_POLICY_PILOT_CANDIDATE" if match == "EXACT" and compatible else "PRICE_BASIS_UNRESOLVED"
        observation = eligible_observation(source["EXT-02"], code=material_code, pricing_date=contract["valid_from"]) if route == "DEMO_INDEX_POLICY_PILOT_CANDIDATE" else None
        plan_rows.append({"tenant_id": key[0], "contract_id": key[1], "material_id": contract["material_id"],
            "material_name": material["material_name"], "scope_node_id": contract["scope_node_id"],
            "currency": contract["currency"], "quantity_uom": contract["quantity_uom"],
            "material_benchmark": material_code, "contract_benchmark": contract["benchmark_code"], "benchmark_match": match,
            "order_count": len(orders[key]), "route": route, "price_fixing_date_confirmed": False,
            "unique_price_value_match": len(matching) == 1, "matched_source_after_contract_start": future,
            "matched_source_observations": [{k: r[k] for k in ("observation_id", "observed_at", "published_at", "vintage_date")} for r in matching],
            "unapproved_contract_start_hypothesis": {"pricing_date": contract["valid_from"],
                "source_observation_id": observation["observation_id"] if observation else None,
                "source_dates": {k: observation[k] for k in ("observed_at", "published_at", "vintage_date")} if observation else None},
            "candidate_price": None, "ready_for_price_calculation": False})
    return {"contract_count": len(plan_rows), "order_count": sum(r["order_count"] for r in plan_rows),
        "dimension_groups": [{"currency": k[0], "quantity_uom": k[1], "contracts": n,
            "orders": sum(r["order_count"] for r in plan_rows if (r["currency"], r["quantity_uom"]) == k)} for k, n in sorted(dimensions.items())],
        "material_benchmark_counts": dict(material_codes), "source_price_after_contract_start": future_contracts,
        "source_price_after_order_date": future_orders, "routes": dict(Counter(r["route"] for r in plan_rows)), "contracts": plan_rows}


def main():
    def readonly(event, args):
        if event == "sqlite3.connect" and not str(args[0]).endswith("?mode=ro"):
            raise PermissionError("가격 방안 검토는 SQLite 읽기 전용입니다")
    sys.addaudithook(readonly)
    raw = verified(STAGE / "raw-result.json", "report_fingerprint")
    quality = verified(STAGE / "quality-result.json", "report_fingerprint")
    if quality["parent_raw_fingerprint"] != raw["report_fingerprint"]:
        raise ValueError("부모 보고서 불일치")
    db = STAGE / "data_preparation.db"
    before = digest(tables(db))
    if before != raw["copy_table_fingerprint"]:
        raise ValueError("RAW 사본 변경")
    data, hashes = {}, {}
    for snapshot in raw["snapshots"]:
        path = Path(snapshot["raw_path"]).resolve()
        if not path.is_relative_to(STAGE.resolve()):
            raise ValueError("RAW 경로가 사본 밖입니다")
        parsed = parse_csv(path.read_bytes(), file_name=path.name)
        if parsed.checksum != snapshot["checksum"] or len(parsed.rows) != snapshot["row_count"]:
            raise ValueError("RAW 지문/모수 변경")
        hashes[str(path)] = parsed.checksum
        data.setdefault(snapshot["dataset_contract_key"], []).extend(parsed.rows)
    _, source, _, files, errors = read_package(KIT, "full")
    if errors or files["EXT-02"] != quality["source_benchmark_file"]:
        raise ValueError("가격 원천 변경/읽기 오류")
    result = review(data, source)
    if result["contract_count"] != 100 or result["order_count"] != 1800:
        raise ValueError("계약/발주 모수 불일치")
    if digest(tables(db)) != before or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != fp for p, fp in hashes.items()):
        raise ValueError("검토 중 RAW/DB 변경")
    result.update({"status": "PRICE_POLICY_REVIEW_NOT_APPLIED", "installed": False, "executable": False, "approved": False,
        "parent_quality_fingerprint": quality["report_fingerprint"], "parent_raw_fingerprint": raw["report_fingerprint"],
        "source_files": {k: files[k] for k in ("EXT-02", "EXT-01", "FND-03")}, "copy_fingerprint_before_and_after": before,
        "raw_hashes_before_and_after": hashes,
        "time_match_caveat": "반올림 가격 일치와 생성기 경로의 증거이며 정식 observation 결속이 아니다",
        "recommendation": "2건으로 시연용 계약 고정가격 정책을 우선 검증하는 방안. 98건은 RAW 보존·가격계산 보류. 적용은 사용자 정책 선택 뒤 별도 후보에서 수행",
        "proposed_pricing_date_rule": "계약 valid_from까지 관측·공표·vintage가 모두 도달한 최근 가격; 검토 가정이며 아직 미승인",
        "policy_caveats": ["valid_from은 이전 합성자료 보정에서 바뀐 유효일이며 실제 가격 결정일의 증거가 아니다",
            "자재/지표 코드 일치는 품위·규격·정산 및 중량 기준 일치를 입증하지 않는다",
            "이전 tenant의 관측자료는 후보 조사 근거이며 목표 문맥의 인증된 자료가 아니다"],
        "required_evidence_fields": ["pricing_mode", "pricing_date", "material_price_basis", "price_observation_id",
            "observed_at", "published_at", "vintage_date", "price_currency", "price_uom", "target_currency", "target_uom",
            "fx_observation_id_or_fixed_fx_policy", "material_specific_mass_per_unit_if_needed", "rounding_policy", "rule_version"],
        "unresolved": ["고정가격/발주별 변동가격 정책 선택", "96건의 명시적 견적 또는 가격지표 규칙", "2건의 지표 불일치 규칙",
            "KRW 환율 고정/시계열 정책", "EA별 품목 중량 또는 개당 견적", "선행자료의 새 문맥 연결·소유권·인증"],
        "not_performed": ["새 가격 계산/저장", "RAW/DB/계약 스키마 변경", "승인/인증", "공유 원장 또는 전체 회귀 실행"]})
    result["report_fingerprint"] = fingerprint(result)
    with (STAGE / "price-policy-review.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("status", "dimension_groups", "material_benchmark_counts", "source_price_after_contract_start", "source_price_after_order_date", "routes", "report_fingerprint")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
