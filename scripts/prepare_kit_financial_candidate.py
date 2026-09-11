"""K1-c7h: 승인된 합성 전표/통관 규칙으로 74행 비설치 후보만 만든다."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path
import sys

from core.data_preparation.kit_logistics_revision import fingerprint
from core.data_preparation.kit_procurement_reference_revision import _index
from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation.snapshot_service import parse_csv
from scripts.prepare_kit_purchase_rehearsal import KIT, RUN, verified
from scripts.rehearse_kit_factory_connection import REVIEW, ROOT
from scripts.inspect_kit_raw_quality import STAGE
from scripts.inspect_kit_price_impact import inspect_impact, number

RULE = "synthetic-financial-amounts-half-even/1"
KEYS = {"LOG-04": "clearance_id", "FIN-02": "finance_document_id", "FIN-03": "ledger_line_id"}
METADATA = {"quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE"}


def amount(quantity, price, rate="1"):
    """전표마다 마지막에 소수 2자리로 반올림한다. 실제 세금/지급 정책이 아니다."""
    q, p, r = (number(v) for v in (quantity, price, rate))
    if q <= 0 or p <= 0 or r not in (Decimal("1"), Decimal("0.01"), Decimal("0")):
        raise ValueError("양수 수량/가격과 승인된 합성 배율만 허용합니다")
    with localcontext() as context:
        context.prec = 50
        return format((q * p * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), ".2f")


def make_candidate(source, downstream, target, price_rows, mapping, reviewed):
    current = inspect_impact(source, downstream, target, price_rows, mapping)
    if any(current["checks"].values()) or any(current[k] != reviewed[k] for k in current):
        raise ValueError("검토 당시의 연결/금액 대사를 재현할 수 없습니다")
    old = {k: _index(downstream[k], field) for k, field in KEYS.items()}
    prices = {k: _index(price_rows[k], field) for k, field in (("PRC-01", "contract_id"), ("PRC-02", "po_line_id"))}
    shipments = _index(downstream["LOG-02"], "shipment_id")
    traces = {r["po_line_id"]: r for r in current["orders"]}
    if len(traces) != len(current["orders"]):
        raise ValueError("복수 문맥의 발주를 동일 ID로 합치지 않습니다")
    candidate = {k: [] for k in KEYS}
    before = {k: [] for k in KEYS}
    changes, metadata_changes, evidence, reconciliations = [], [], [], []
    controls = defaultdict(lambda: {"AP": [Decimal(0), Decimal(0)], "DUTY": [Decimal(0), Decimal(0)]})

    def add(dataset, source_key, column, value, trace, proof):
        original = old[dataset][source_key]
        if number(original[column]) == number(value):
            raise ValueError("금액이 바뀌지 않은 행을 74행 보정 범위에 넣지 않습니다")
        updated = {**original, column: value, **METADATA}
        candidate[dataset].append(updated)
        before[dataset].append(dict(original))
        changes.append({"dataset": dataset, "tenant_id": source_key[0], "object_id": source_key[1],
            "column": column, "before": original[column], "after": value,
            "contract_id": trace["contract_id"], "po_line_id": trace["po_line_id"]})
        for field, status in METADATA.items():
            if original[field] != status:
                metadata_changes.append({"dataset": dataset, "object_id": source_key[1], "column": field,
                    "before": original[field], "after": status})
        allowed = {column, *METADATA}
        if set(updated) != set(original) or any(updated[k] != original[k] for k in original if k not in allowed):
            raise ValueError("금액/후보 상태 외 필드 변경")
        evidence.append({"dataset": dataset, "object_id": source_key[1], "rule_version": RULE,
            "source_record_id": original["record_id"], "source_lineage_id": original["lineage_id"],
            "source_row_fingerprint": fingerprint(original), "source_tenant_id": original["tenant_id"],
            "source_scope_node_id": original["scope_node_id"], "price_candidate_tenant_id": trace["target_tenant_id"],
            "price_candidate_scope_node_id": trace["target_scope_node_id"], "contract_id": trace["contract_id"],
            "po_line_id": trace["po_line_id"], "rounding": "ROUND_HALF_EVEN / 0.01 / PER_DOCUMENT",
            "context_relation": "EXPLICIT_REHEARSAL_LINEAGE_ONLY_NOT_AUTHORIZED_SOURCE_BINDING",
            "actual_tax_or_settlement_verified": False, **proof})
        return updated

    for payable in current["payables"]:
        trace = traces[payable["po_line_id"]]
        tenant = trace["source_tenant_id"]
        price_po = prices["PRC-02"][trace["target_tenant_id"], trace["po_line_id"]]
        new_amount = amount(price_po["order_quantity"], price_po["unit_price"])
        document = add("FIN-02", (tenant, payable["finance_document_id"]), "amount", new_amount, trace,
            {"formula": "order_quantity * candidate_unit_price", "quantity": price_po["order_quantity"],
             "candidate_unit_price": price_po["unit_price"], "currency": price_po["currency"],
             "cash_settlement_verified": False})
        new_lines = []
        for identity in payable["ledger_line_ids"]:
            line = old["FIN-03"][tenant, identity]
            debit = line["account_id"] == "1200"
            side, zero_side = ("debit_amount", "credit_amount") if debit else ("credit_amount", "debit_amount")
            if number(line[zero_side]) != 0 or number(line[side]) != number(payable["stored_amount"]):
                raise ValueError("기존 GL의 계정별 차변/대변 방향 또는 금액 불일치")
            if line["posting_date"] != document["posting_date"] or line["fiscal_period"] != document["posting_date"][:7]:
                raise ValueError("기존 GL의 기표일/기간 불일치")
            new_lines.append(add("FIN-03", (tenant, identity), side, new_amount, trace,
                {"formula": "linked_AP.amount", "finance_document_id": document["finance_document_id"],
                 "account_id": line["account_id"], "side": side, "currency": document["currency"]}))
        debit = sum(number(r["debit_amount"]) for r in new_lines)
        credit = sum(number(r["credit_amount"]) for r in new_lines)
        if debit != credit or debit != number(document["amount"]):
            raise ValueError("후보 AP/GL 차대 대사 실패")
        reconciliations.append({"finance_document_id": document["finance_document_id"], "currency": document["currency"],
            "ap_amount": document["amount"], "debit": str(debit), "credit": str(credit), "matched": True})
        control = controls[trace["contract_id"], document["currency"]]["AP"]
        control[0] += number(payable["stored_amount"])
        control[1] += number(new_amount)

    for shipment in current["shipments"]:
        if not shipment["requires_amount_review"]:
            if number(shipment["stored_duty_amount"]) != 0:
                raise ValueError("0% 합성 통관 금액이 0이 아닙니다")
            continue
        trace = traces[shipment["po_line_id"]]
        tenant = trace["source_tenant_id"]
        source_ship = shipments[tenant, shipment["shipment_id"]]
        contract = prices["PRC-01"][trace["target_tenant_id"], trace["contract_id"]]
        if Decimal(shipment["generator_only_duty_rate"]) != Decimal("0.01"):
            raise ValueError("승인한 합성 통관 배율 불일치")
        new_amount = amount(source_ship["shipment_quantity"], contract["benchmark_price"], "0.01")
        updated = add("LOG-04", (tenant, shipment["clearance_id"]), "duty_amount", new_amount, trace,
            {"formula": "candidate_benchmark_price * shipment_quantity * generator_only_rate",
             "shipment_id": shipment["shipment_id"], "quantity": source_ship["shipment_quantity"],
             "candidate_benchmark_price": contract["benchmark_price"], "generator_only_rate": "0.01",
             "currency": "USD", "real_customs_policy": False})
        control = controls[trace["contract_id"], updated["currency"]]["DUTY"]
        control[0] += number(shipment["stored_duty_amount"])
        control[1] += number(new_amount)

    preserved = {}
    for dataset, field in KEYS.items():
        changed = {r[field] for r in candidate[dataset]}
        expected = current["requires_amount_review_ids"][dataset]
        if len(changed) != len(candidate[dataset]) or len(expected) != len(set(expected)) or changed != set(expected):
            raise ValueError("검토 대상 외 행/중복/누락 후보")
        remaining = [r for r in downstream[dataset] if r[field] not in changed]
        preserved[dataset] = {"count": len(remaining), "rows_fingerprint": fingerprint(remaining)}
    return {"candidate_rows": candidate, "source_rows_before": before, "changes": changes,
        "candidate_metadata_changes": metadata_changes, "amount_evidence": evidence,
        "ap_gl_reconciliation": reconciliations, "untouched_population": preserved,
        "unshipped_orders_preserved": [r["po_line_id"] for r in current["orders"] if not r["shipment_ids"]],
        "zero_duty_rows_preserved": [r["clearance_id"] for r in current["shipments"] if not r["requires_amount_review"]],
        "control_totals": [{"contract_id": key[0], "currency": key[1], "old_AP": str(values["AP"][0]),
            "new_AP": str(values["AP"][1]), "old_duty": str(values["DUTY"][0]), "new_duty": str(values["DUTY"][1]),
            "not_actual_savings": True, "AP_and_GL_must_not_be_added_together": True}
            for key, values in sorted(controls.items())]}


def main():
    def no_database(event, args):
        if event == "sqlite3.connect":
            raise PermissionError("비설치 재무 후보는 DB에 연결하지 않습니다")
    sys.addaudithook(no_database)
    impact_path = STAGE / "price-impact-review.json"
    impact = verified(impact_path, "report_fingerprint")
    watched = {**impact["input_hashes_before_and_after"], str(impact_path): hashlib.sha256(impact_path.read_bytes()).hexdigest()}
    def check_inputs():
        if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != value for path, value in watched.items()):
            raise ValueError("검토 증적/RAW 원문 변경")
        for relative, value in impact["code_evidence_sha256"].items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != value:
                raise ValueError("검토한 생성기/금액 사용처 변경")
    check_inputs()
    price = verified(STAGE / "price-candidate.json", "proposal_fingerprint")
    raw = verified(STAGE / "raw-result.json", "report_fingerprint")
    logistics = verified(REVIEW / "candidate.json", "proposal_fingerprint")
    connection = verified(RUN / "result.json", "report_fingerprint")
    if impact["installed"] or impact["executable"] or price["installed"] or price["executable"] or price["operational_approval"]:
        raise ValueError("비설치 후보 상태가 아닙니다")
    for name, obj, field in (("price", price, "proposal_fingerprint"), ("raw", raw, "report_fingerprint"),
            ("logistics", logistics, "proposal_fingerprint"), ("connection", connection, "report_fingerprint")):
        if impact["parent_fingerprints"][name] != obj[field]:
            raise ValueError("부모 계보 불일치")
    target = {}
    for snap in raw["snapshots"]:
        path = Path(snap["raw_path"]).resolve()
        if not path.is_relative_to(STAGE.resolve()):
            raise ValueError("RAW 경계 이탈")
        parsed = parse_csv(path.read_bytes(), file_name=path.name)
        if parsed.checksum != snap["checksum"] or len(parsed.rows) != snap["row_count"]:
            raise ValueError("RAW 지문/모수 불일치")
        target.setdefault(snap["dataset_contract_key"], []).extend(parsed.rows)
    _, source, _, files, errors = read_package(KIT, "full")
    if errors or files != impact["source_files_before_and_after"]:
        raise ValueError("원천 full 파일 변경")
    result = make_candidate(source, {**source, **logistics["candidate_rows"]}, target, price["candidate_rows"],
        {r["source_scope_node_id"]: r["target_scope_node_id"] for r in connection["mapping"]}, impact)
    if {k: len(v) for k, v in result["candidate_rows"].items()} != {"LOG-04": 5, "FIN-02": 23, "FIN-03": 46}:
        raise ValueError("승인된 74행 모수 불일치")
    if {c["contract_id"] for c in result["changes"]} != {"CTR-00002", "CTR-00003"}:
        raise ValueError("승인된 두 계약 범위 이탈")
    check_inputs()
    _, _, _, after_files, after_errors = read_package(KIT, "full")
    if after_errors or files != after_files:
        raise ValueError("계산 중 원천 변경")
    result.update({"status": "PREPARED_NOT_INSTALLED", "installed": False, "executable": False,
        "operational_approval": False, "database_connections": 0, "rule_version": RULE,
        "user_authorization": "2026-09-11: HALF_EVEN 0.01 및 기존 합성 통관식으로 74행 비설치 후보 생성 승인. 실제 세금/지급/인증/소유권 승인이 아님",
        "parent_impact_fingerprint": impact["report_fingerprint"], "parent_price_fingerprint": price["proposal_fingerprint"],
        "candidate_rows_fingerprint": fingerprint(result["candidate_rows"]), "input_hashes_before_and_after": watched,
        "source_files_before_and_after": files, "code_evidence_sha256": impact["code_evidence_sha256"],
        "candidate_context": "SOURCE_TENANT_AND_SCOPE_PRESERVED; TARGET_CONTEXT_NOT_INSTALLED_OR_BOUND",
        "metadata_policy": "후보만 PENDING_VALIDATION/UNVERIFIED_CANDIDATE; 과거 인증 표시는 source_rows_before에 보존",
        "not_verified": ["actual tax/grade/recognition/settlement", "target-context source bindings and ownership",
            "certification", "cash settlement evidence", "previous full regression ledger sentinel error"],
        "next": "가격 38행+후속 74행을 통합한 비설치 문맥/선행자료/적재 순서 점검; DB 설치/승인/인증은 별도"})
    result["proposal_fingerprint"] = fingerprint(result)
    with (STAGE / "financial-candidate.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": result["status"], "counts": {k: len(v) for k, v in result["candidate_rows"].items()},
        "business_changes": len(result["changes"]), "metadata_changes": len(result["candidate_metadata_changes"]),
        "controls": result["control_totals"], "proposal_fingerprint": result["proposal_fingerprint"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
