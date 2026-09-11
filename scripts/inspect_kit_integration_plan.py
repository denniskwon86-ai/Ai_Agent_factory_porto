"""112행 후보 통합·의존자료·일괄 RAW 적재 계획. DB 연결/설치는 제공하지 않는다."""
from collections import Counter
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
import re
import sys

from core.data_preparation.kit_logistics_revision import fingerprint, inspect_logistics
from core.data_preparation.kit_procurement_reference_revision import IDENTITIES, inspect_procurement
from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation.snapshot_service import parse_csv
from scripts.prepare_kit_purchase_rehearsal import KIT, RUN, verified
from scripts.rehearse_kit_factory_connection import ROOT, REVIEW
from scripts.inspect_kit_raw_quality import STAGE

LOG_KEYS = {"LOG-02": "shipment_id", "LOG-03": "milestone_id", "LOG-04": "clearance_id", "LOG-05": "transport_event_id"}
CORE_KEYS = (*IDENTITIES, *LOG_KEYS)


def dependency_layers(contracts, roots):
    seen, visiting = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError("계약 의존성 순환")
        if key in seen:
            return
        if key not in contracts:
            raise ValueError("의존 계약 미등록: " + key)
        visiting.add(key)
        for dep in contracts[key].get("dependencies", []):
            visit(dep)
        visiting.remove(key)
        seen.add(key)
    for root in roots:
        visit(root)
    layers, remaining = [], set(seen)
    while remaining:
        layer = sorted(k for k in remaining if not set(contracts[k].get("dependencies", [])) & remaining)
        layers.append(layer)
        remaining.difference_update(layer)
    return layers


def progress_audit(document):
    section = document.split("## 6. 진척과 다음 작업", 1)[1].split("## 7.", 1)[0]
    scores = [(name.strip(), int(score), int(total)) for name, score, total in
        re.findall(r"^\| ([^|]+) \| (\d+)/(\d+) \|$", section, re.M)]
    if len(scores) != 10 or any(total != 4 or not 0 <= score <= total for _, score, total in scores):
        raise ValueError("원본 관리평가 10영역 표를 판독하지 못했습니다")
    return {"kind": "HISTORICAL_MANAGEMENT_ASSESSMENT_NOT_LIVE_PRODUCT_COMPLETION", "baseline_date": "2026-09-08",
        "areas": [{"area": n, "score": s, "total": t} for n, s, t in scores],
        "overall": {"score": sum(s for _, s, _ in scores), "total": 40},
        "local": {"score": sum(s for _, s, _ in scores[:7]), "total": 28},
        "previously_reported_local_score": 16, "current_all_area_reassessment_performed": False}


def overlay(rows, candidates, field):
    baseline = {(r["tenant_id"], r[field]): r for r in rows}
    patch = {(r["tenant_id"], r[field]): r for r in candidates}
    if len(baseline) != len(rows) or len(patch) != len(candidates) or not set(patch) <= set(baseline):
        raise ValueError("후보 중복 또는 원천 밖의 키")
    return [patch.get((r["tenant_id"], r[field]), r) for r in rows]


def reviewed_context(rows, mapping, source_tenant, target_tenant):
    """명시된 두 공장만 메모리에서 대조한다. 제품의 범위/인증 승인이 아니다."""
    result = []
    for row in rows:
        if row["tenant_id"] != source_tenant or row["scope_node_id"] not in mapping:
            raise ValueError("미검토 회사/공장 범위")
        if row["data_origin"] != "SYNTHETIC" or row["certification_status"] != "UNVERIFIED_CANDIDATE":
            raise ValueError("합성 미검증 후보만 통합 대조합니다")
        result.append({**row, "tenant_id": target_tenant, "scope_node_id": mapping[row["scope_node_id"]]})
    return result


def main():
    def no_db(event, args):
        if event == "sqlite3.connect":
            raise PermissionError("통합 계획은 DB에 연결하지 않습니다")
    sys.addaudithook(no_db)
    paths = {"price": (STAGE / "price-candidate.json", "proposal_fingerprint"),
        "finance": (STAGE / "financial-candidate.json", "proposal_fingerprint"),
        "raw": (STAGE / "raw-result.json", "report_fingerprint"),
        "logistics": (REVIEW / "candidate.json", "proposal_fingerprint"),
        "connection": (RUN / "result.json", "report_fingerprint")}
    parents = {k: verified(*v) for k, v in paths.items()}
    price, finance, raw, logistics, connection = (parents[k] for k in paths)
    watched = {**finance["input_hashes_before_and_after"], **{str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p, _ in paths.values()}}
    def unchanged():
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != fp for p, fp in watched.items()):
            raise ValueError("부모 증적/RAW 변경")
    unchanged()
    if finance["parent_price_fingerprint"] != price["proposal_fingerprint"] or price["parent_raw_fingerprint"] != raw["report_fingerprint"]:
        raise ValueError("가격/재무/RAW 계보 불일치")
    for report in (price, finance):
        if report["installed"] or report["executable"] or report["operational_approval"] or report["candidate_rows_fingerprint"] != fingerprint(report["candidate_rows"]):
            raise ValueError("비설치 후보 경계 변경")
    mapping = {r["source_scope_node_id"]: r["target_scope_node_id"] for r in connection["mapping"]}
    target = {}
    for snapshot in raw["snapshots"]:
        path = Path(snapshot["raw_path"]).resolve()
        if not path.is_relative_to(STAGE.resolve()):
            raise ValueError("RAW 경로 이탈")
        parsed = parse_csv(path.read_bytes(), file_name=path.name)
        if parsed.checksum != snapshot["checksum"] or len(parsed.rows) != snapshot["row_count"]:
            raise ValueError("RAW 지문/모수 불일치")
        target.setdefault(snapshot["dataset_contract_key"], []).extend(parsed.rows)
    _, source, contracts, files, errors = read_package(KIT, "full")
    if errors or files != finance["source_files_before_and_after"]:
        raise ValueError("검토 원천 변경")
    source_tenants = {r["tenant_id"] for r in logistics["candidate_rows"]["PRC-02"]}
    target_tenants = {r["tenant_id"] for r in target["PRC-02"]}
    if len(source_tenants) != 1 or len(target_tenants) != 1:
        raise ValueError("원천/대상 회사 문맥 혼입")
    source_tenant, target_tenant = next(iter(source_tenants)), next(iter(target_tenants))
    for key in ("PRC-01", "PRC-02"):
        target[key] = overlay(target[key], price["candidate_rows"][key], IDENTITIES[key])
    for key, field in LOG_KEYS.items():
        rows = logistics["candidate_rows"][key]
        if key == "LOG-04":
            rows = overlay(rows, finance["candidate_rows"][key], field)
        target[key] = reviewed_context(rows, mapping, source_tenant, target_tenant)
    procurement, _ = inspect_procurement(target)
    log_check = inspect_logistics(target, contracts)
    if any(procurement.values()) or log_check["issues"]:
        raise ValueError("통합 참조/수량/날짜 대사 실패")
    ap = reviewed_context(finance["candidate_rows"]["FIN-02"], mapping, source_tenant, target_tenant)
    gl = reviewed_context(finance["candidate_rows"]["FIN-03"], mapping, source_tenant, target_tenant)
    orders = {(r["tenant_id"], r["po_line_id"]): r for r in target["PRC-02"]}
    for document in ap:
        order = orders[document["tenant_id"], document["reference_id"]]
        lines = [r for r in gl if (r["tenant_id"], r["document_id"]) == (document["tenant_id"], document["finance_document_id"])]
        if len(lines) != 2 or any(r["scope_node_id"] != order["scope_node_id"] or r["currency"] != order["currency"] for r in [document, *lines]):
            raise ValueError("통합 전표 문맥/통화 불일치")
        if sum(Decimal(r["debit_amount"]) for r in lines) != sum(Decimal(r["credit_amount"]) for r in lines) or sum(Decimal(r["debit_amount"]) for r in lines) != Decimal(document["amount"]):
            raise ValueError("통합 AP/GL 대사 실패")
        expected = (Decimal(order["order_quantity"]) * Decimal(order["unit_price"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if Decimal(document["amount"]) != expected:
            raise ValueError("통합 PO/AP 가격 대사 실패")
    target_contracts = {(r["tenant_id"], r["contract_id"]): r for r in target["PRC-01"]}
    target_ships = {(r["tenant_id"], r["shipment_id"]): r for r in target["LOG-02"]}
    selected_orders = {r["po_line_id"] for r in price["candidate_rows"]["PRC-02"]}
    duty_checks = 0
    for clearance in target["LOG-04"]:
        ship = target_ships[clearance["tenant_id"], clearance["shipment_id"]]
        if ship["po_line_id"] not in selected_orders:
            continue
        order = orders[ship["tenant_id"], ship["po_line_id"]]
        contract = target_contracts[order["tenant_id"], order["contract_id"]]
        rate = Decimal("0.01") if int(ship["shipment_id"].split("-")[1]) % 5 == 0 else Decimal(0)
        expected = (Decimal(contract["benchmark_price"]) * Decimal(ship["shipment_quantity"]) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if Decimal(clearance["duty_amount"]) != expected:
            raise ValueError("통합 계약/통관 합성 금액 대사 실패")
        duty_checks += 1
    core_layers = dependency_layers(contracts, CORE_KEYS)
    full_layers = dependency_layers(contracts, (*CORE_KEYS, "FIN-02", "FIN-03"))
    core_dependencies = {k for layer in core_layers for k in layer}
    missing = sorted(core_dependencies - set(target))
    foundation = [{"dataset": k, "source_full_rows": len(source[k]), "dependencies": contracts[k].get("dependencies", []),
        "source_scopes": dict(Counter(r["scope_node_id"] for r in source[k])), "target_reference_prepared": False,
        "blocks_raw_storage": False, "blocks_certification_or_use": True} for k in missing]
    score_path = ROOT / "docs/handoff/RELEASE_CATALOG_CLEANUP_2026-09-08.md"
    score_bytes = score_path.read_bytes()
    scores = progress_audit(score_bytes.decode("utf-8-sig"))
    batch_keys = ("PRC-01", "PRC-02", *LOG_KEYS)
    batch = [{"dataset": k, "rows": len(target[k]), "scope_counts": dict(Counter(r["scope_node_id"] for r in target[k])),
        "row_fingerprint": fingerprint(target[k]), "action": "NEW_RAW_REVISION_PRESERVE_OLD" if k.startswith("PRC") else "NEW_RAW_DATASET"}
        for k in batch_keys]
    counts = {k: len(v) for k, v in target.items()}
    if sum(len(v) for v in price["candidate_rows"].values()) != 38 or sum(len(v) for v in finance["candidate_rows"].values()) != 74 or sum(r["rows"] for r in batch) != 13900:
        raise ValueError("112행 후보 또는 13,900행 적재 모수 이탈")
    _, _, _, after_files, after_errors = read_package(KIT, "full")
    unchanged()
    if after_errors or after_files != files or score_path.read_bytes() != score_bytes:
        raise ValueError("검토 중 원천/산정표 변경")
    report = {"status": "INTEGRATED_REVIEW_BATCH_DEFINED_NOT_INSTALLED", "installed": False, "executable": False,
        "database_connections": 0, "certification_or_ownership_approval": False,
        "parent_fingerprints": {k: parents[k][field] for k, (_, field) in paths.items()},
        "reviewed_price_and_financial_rows": 112, "in_memory_core_dataset_counts": counts,
        "in_memory_core_rows": sum(counts.values()), "procurement_checks": procurement, "logistics_checks": log_check,
        "same_context_AP_GL_documents": len(ap), "same_context_AP_GL_lines": len(gl), "same_context_duty_checks": duty_checks,
        "context_mapping_applied_only_in_memory": mapping, "target_reference_datasets": foundation,
        "core_dependency_layers": core_layers, "finance_inclusive_dependency_layers": full_layers,
        "finance_only_extra_datasets": sorted({k for layer in full_layers for k in layer} - core_dependencies),
        "next_single_batch": batch, "next_batch_rows": 13900,
        "deferred": {"financial_candidate_rows": 69, "reason": "정식 FIN 계약의 판매/생산 의존성은 RAW 물류 적재 선행조건이 아님; 후보 보존, 적용/인증하지 않음",
            "unpriced_contracts": len(price["held_contract_ids"]), "unpriced_orders": len(price["held_order_ids"]),
            "price_hold_runtime_enforcement_installed": False},
        "exit_conditions": {"next_batch": "새 격리 사본에서 6종 13,900행 RAW 왕복·기존 7판 보존·모수/대사·12공장별 그룹 확인",
            "after_batch": "5종 선행자료를 함께 정렬하고 품질/참조 대사; 소유권/인증/앱 연결·실사용은 별도 관문"},
        "progress_audit": scores, "progress_source_sha256": hashlib.sha256(score_bytes).hexdigest(),
        "input_hashes_before_and_after": watched, "source_files_before_and_after": files,
        "not_verified": ["fresh all-domain completion assessment", "current live DB inventory", "target-context foundation data",
            "all-contract price policy", "runtime hold enforcement", "ownership/certification", "UI/HTTP/T3",
            "previous full regression ledger sentinel error"]}
    report["report_fingerprint"] = fingerprint(report)
    with (STAGE / "integration-batch-plan.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("status", "reviewed_price_and_financial_rows", "in_memory_core_rows", "next_batch_rows",
        "core_dependency_layers", "finance_only_extra_datasets", "progress_audit", "report_fingerprint")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
