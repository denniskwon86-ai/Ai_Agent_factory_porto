"""K1-c7g: 가격 후보의 후속 연결/금액을 조사한다. 보정 후보·DB 쓰기는 제공하지 않는다."""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN
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

IDENTITIES = {"PRC-01": "contract_id", "PRC-02": "po_line_id", "LOG-02": "shipment_id",
    "LOG-03": "milestone_id", "LOG-04": "clearance_id", "LOG-05": "transport_event_id",
    "FIN-02": "finance_document_id", "FIN-03": "ledger_line_id", "INV-02": "movement_id"}


def number(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("유한한 비음수 금액/수량만 허용합니다")
    return result


def ap_checks(order, document, ledger):
    """차대 일치와 원천 금액 일치를 분리한다. HALF_EVEN은 비교용이지 선택된 전표 정책이 아니다."""
    exact = number(order["order_quantity"]) * number(order["unit_price"])
    generated = Decimal(str(round(float(order["order_quantity"]) * float(order["unit_price"]), 2)))
    amount = number(document["amount"])
    debit = sum(number(r["debit_amount"]) for r in ledger)
    credit = sum(number(r["credit_amount"]) for r in ledger)
    cents = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return {"stored_amount": str(amount), "old_exact_quantity_times_price": str(exact),
        "matches_old_generator": amount == generated,
        "decimal_half_even_comparison": str(cents), "rounding_difference": str(cents - amount),
        "ledger_balanced": debit == credit,
        "ledger_matches_document": debit == credit == amount,
        "ledger_debit": str(debit), "ledger_credit": str(credit),
        "posting_matches_po_due_date": document["posting_date"] == order["due_date"]}


def inspect_impact(source, downstream, target, price_rows, scope_mapping):
    """이전 tenant의 계보와 새 tenant 후보를 명시적으로 비교하고 행은 변경하지 않는다."""
    old = {k: _index(downstream[k], v) for k, v in IDENTITIES.items()}
    original = {k: _index(source[k], IDENTITIES[k]) for k in ("PRC-01", "PRC-02")}
    raw = {k: _index(target[k], IDENTITIES[k]) for k in ("PRC-01", "PRC-02")}
    new = {k: _index(price_rows[k], IDENTITIES[k]) for k in ("PRC-01", "PRC-02")}
    tenants = {r["tenant_id"] for r in downstream["PRC-02"]}
    if len(tenants) != 1 or not new["PRC-02"]:
        raise ValueError("단일 원천 tenant와 비어 있지 않은 후보가 필요합니다")
    source_tenant = next(iter(tenants))
    for dataset, index in new.items():
        price_field = "unit_price" if dataset == "PRC-02" else "benchmark_price"
        for key, row in index.items():
            baseline = raw[dataset][key]
            if set(row) != set(baseline) or {k for k in row if row[k] != baseline[k]} != {price_field}:
                raise ValueError("가격 필드만 변경한 후보가 아닙니다")
            if row["quality_status"] != "PENDING_VALIDATION" or row["certification_status"] != "UNVERIFIED_CANDIDATE":
                raise ValueError("미검증 후보만 조사합니다")
            number(row[price_field])

    def related(dataset, field):
        result = defaultdict(list)
        for row in old[dataset].values():
            result[row["tenant_id"], row[field]].append(row)
        return result

    ships = related("LOG-02", "po_line_id")
    customs = related("LOG-04", "shipment_id")
    milestones = related("LOG-03", "shipment_id")
    transports = related("LOG-05", "shipment_id")
    movements = related("INV-02", "reference_id")
    documents = related("FIN-02", "reference_id")
    ledgers = related("FIN-03", "document_id")
    orders, shipment_evidence, ap_evidence = [], [], []
    money_ids = {"LOG-04": [], "FIN-02": [], "FIN-03": []}
    for key, candidate in sorted(new["PRC-02"].items()):
        source_key = (source_tenant, key[1])
        po = old["PRC-02"][source_key]
        baseline = raw["PRC-02"][key]
        original_po = original["PRC-02"][source_key]
        ignored = {"tenant_id", "scope_node_id", "quality_status", "certification_status"}
        if set(po) != set(baseline) or any(po[k] != baseline[k] for k in po if k not in ignored):
            raise ValueError("발주 업무값의 명시적 원천 계보가 맞지 않습니다")
        if scope_mapping.get(po["scope_node_id"]) != baseline["scope_node_id"]:
            raise ValueError("원천/대상 공장 매핑 불일치")
        contract_key = (key[0], po["contract_id"])
        contract = raw["PRC-01"][contract_key]
        new_contract = new["PRC-01"][contract_key]
        original_contract = original["PRC-01"][source_tenant, po["contract_id"]]
        if original_contract["benchmark_price"] != contract["benchmark_price"]:
            raise ValueError("원천 기준가격과 RAW 기준가격 불일치")
        if po["currency"] != "USD" or po["quantity_uom"] != "TON":
            raise ValueError("환산이 필요한 발주는 이번 조사 범위 밖입니다")
        children = ships[source_key]
        aps = [r for r in documents[source_key] if r["document_type"] == "AP"]
        if len(children) not in (0, 1) or len(aps) != len(children):
            raise ValueError("키트의 선적 1건/매입전표 1건 관계가 깨졌습니다")

        def check_context(rows):
            if any(r["scope_node_id"] != po["scope_node_id"] or r["tenant_id"] != source_tenant for r in rows):
                raise ValueError("후속 행 회사/공장 문맥 혼입")

        orders.append({"po_line_id": key[1], "contract_id": po["contract_id"],
            "source_tenant_id": source_tenant, "source_scope_node_id": po["scope_node_id"],
            "target_tenant_id": key[0], "target_scope_node_id": baseline["scope_node_id"],
            "old_unit_price": baseline["unit_price"], "candidate_unit_price": candidate["unit_price"],
            "shipment_ids": [r["shipment_id"] for r in children],
            "ap_ids": [r["finance_document_id"] for r in aps],
            "relation": "SOURCE_LINEAGE_REVIEW_ONLY_NOT_TARGET_BINDING"})
        for ship in children:
            sk = (source_tenant, ship["shipment_id"])
            cs, ms, ts = customs[sk], milestones[sk], transports[sk]
            inv = [r for r in movements[sk] if r["reference_type"] == "SHIPMENT"]
            deliveries = [r for r in ts if r["event_type"] == "DELIVERED"]
            if (len(cs), len(ms), len(ts), len(inv), len(deliveries)) != (1, 6, 2, 1, 1):
                raise ValueError("선적 사건/통관/입고 연결 모수 불일치")
            check_context([ship, *cs, *ms, *ts, *inv])
            clearance = cs[0]
            if ship["quantity_uom"] != "TON" or clearance["currency"] != po["currency"]:
                raise ValueError("선적 단위/통관 통화 불일치")
            suffix = ship["shipment_id"].removeprefix("SHP-")
            if ship["shipment_id"] != "SHP-" + suffix or not suffix.isdecimal():
                raise ValueError("생성기 선적 번호 형식 불일치")
            # 이 번호 기반 0/1%는 원천 생성기 재현용이며 관세율 정책이 아니다.
            rate = 0.01 if int(suffix) % 5 == 0 else 0.0
            expected_old = Decimal(str(round(float(original_contract["benchmark_price"]) * float(original_po["order_quantity"]) * rate, 2)))
            duty = number(clearance["duty_amount"])
            if rate:
                money_ids["LOG-04"].append(clearance["clearance_id"])
            shipment_evidence.append({"shipment_id": ship["shipment_id"], "po_line_id": key[1],
                "contract_id": po["contract_id"], "clearance_id": clearance["clearance_id"],
                "milestone_ids": [r["milestone_id"] for r in ms],
                "transport_ids": [r["transport_event_id"] for r in ts],
                "inventory_movement_ids": [r["movement_id"] for r in inv],
                "source_records": {"shipment": ship["record_id"], "customs": clearance["record_id"]},
                "quantity_matches_po": number(ship["shipment_quantity"]) == number(po["order_quantity"]),
                "receipt_matches_shipment": number(deliveries[0]["delivered_quantity"]) == number(inv[0]["quantity"]) == number(ship["shipment_quantity"]),
                "freight_amount": ship["freight_amount"], "freight_currency": ship["freight_currency"],
                "freight_price_dependency": False, "stored_duty_amount": str(duty),
                "generator_only_duty_rate": str(rate), "matches_old_generator": duty == expected_old,
                "requires_amount_review": bool(rate), "new_duty_amount": None,
                "old_benchmark": contract["benchmark_price"], "candidate_benchmark": new_contract["benchmark_price"],
                "cleared_at": clearance["cleared_at"], "delivery_at": deliveries[0]["event_at"]})
        for ap in aps:
            lines = ledgers[source_tenant, ap["finance_document_id"]]
            check_context([ap, *lines])
            if len(lines) != 2 or {r["account_id"] for r in lines} != {"1200", "2000"}:
                raise ValueError("키트의 재고/매입채무 2행 관계가 깨졌습니다")
            if ap["partner_id"] != po["supplier_id"] or ap["currency"] != po["currency"] or any(r["currency"] != ap["currency"] for r in lines):
                raise ValueError("전표 거래처/통화 불일치")
            checks = ap_checks(po, ap, lines)
            check_row = {"finance_document_id": ap["finance_document_id"], "po_line_id": key[1],
                "contract_id": po["contract_id"], "source_record_id": ap["record_id"],
                "source_lineage_id": ap["lineage_id"], "ledger_line_ids": [r["ledger_line_id"] for r in lines],
                "currency": ap["currency"], **checks, "requires_amount_review": True, "new_amount": None,
                "posting_date": ap["posting_date"], "due_date": ap["due_date"], "paid_at": ap["paid_at"],
                "status": ap["status"], "cash_settlement_verified": False,
                "posting_before_clearance": date.fromisoformat(ap["posting_date"]) < date.fromisoformat(shipment_evidence[-1]["cleared_at"])}
            ap_evidence.append(check_row)
            money_ids["FIN-02"].append(ap["finance_document_id"])
            money_ids["FIN-03"].extend(r["ledger_line_id"] for r in lines)
    return {"orders": orders, "shipments": shipment_evidence, "payables": ap_evidence,
        "requires_amount_review_ids": money_ids,
        "counts": {"orders": len(orders), "unshipped_orders_without_ap": sum(not r["shipment_ids"] for r in orders),
            "shipments": len(shipment_evidence), "customs": len(shipment_evidence),
            "milestones": sum(len(r["milestone_ids"]) for r in shipment_evidence),
            "transport_events": sum(len(r["transport_ids"]) for r in shipment_evidence),
            "inventory_receipts": sum(len(r["inventory_movement_ids"]) for r in shipment_evidence),
            "payables": len(ap_evidence), "ledger_lines": len(money_ids["FIN-03"]),
            "duty_amount_review": len(money_ids["LOG-04"]),
            "ap_rounding_differences": sum(Decimal(r["rounding_difference"]) != 0 for r in ap_evidence),
            "posting_before_clearance": sum(r["posting_before_clearance"] for r in ap_evidence)},
        "checks": {"old_ap_generator_mismatches": sum(not r["matches_old_generator"] for r in ap_evidence),
            "old_duty_generator_mismatches": sum(not r["matches_old_generator"] for r in shipment_evidence),
            "gl_document_mismatches": sum(not r["ledger_matches_document"] for r in ap_evidence),
            "gl_unbalanced": sum(not r["ledger_balanced"] for r in ap_evidence),
            "shipment_quantity_mismatches": sum(not r["quantity_matches_po"] or not r["receipt_matches_shipment"] for r in shipment_evidence)}}


def main():
    # 공유 원장 감시 오류와 분리: 이 조사에서는 읽기 연결을 포함해 모든 DB 접속을 거부한다.
    def no_database(event, args):
        if event == "sqlite3.connect":
            raise PermissionError("후속 영향 조사는 DB에 연결하지 않습니다")
    sys.addaudithook(no_database)
    parents = {"price": (STAGE / "price-candidate.json", "proposal_fingerprint"),
        "raw": (STAGE / "raw-result.json", "report_fingerprint"),
        "logistics": (REVIEW / "candidate.json", "proposal_fingerprint"),
        "purchase": (RUN / "purchase-preparation.json", "proposal_fingerprint"),
        "connection": (RUN / "result.json", "report_fingerprint")}
    reports = {k: verified(*v) for k, v in parents.items()}
    p, raw, logistics, purchase, connection = (reports[k] for k in parents)
    if p["parent_raw_fingerprint"] != raw["report_fingerprint"] or raw["parent_purchase_fingerprint"] != purchase["proposal_fingerprint"] or purchase["parent_logistics_fingerprint"] != logistics["proposal_fingerprint"] or purchase["parent_connection_fingerprint"] != connection["report_fingerprint"]:
        raise ValueError("부모 계보 불일치")
    if p["installed"] or p["executable"] or p["operational_approval"] or p["candidate_rows_fingerprint"] != fingerprint(p["candidate_rows"]):
        raise ValueError("비설치 가격 후보 경계 불일치")
    if {r["contract_id"] for r in p["candidate_rows"]["PRC-01"]} != {"CTR-00002", "CTR-00003"} or len(p["candidate_rows"]["PRC-02"]) != 36:
        raise ValueError("승인된 2/36 후보 범위 불일치")
    watched = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path, _ in parents.values()}
    target = {}
    for snap in raw["snapshots"]:
        path = Path(snap["raw_path"]).resolve()
        if not path.is_relative_to(STAGE.resolve()):
            raise ValueError("RAW 경계 이탈")
        parsed = parse_csv(path.read_bytes(), file_name=path.name)
        if parsed.checksum != snap["checksum"] or len(parsed.rows) != snap["row_count"]:
            raise ValueError("RAW 지문/모수 변경")
        watched[str(path)] = parsed.checksum
        target.setdefault(snap["dataset_contract_key"], []).extend(parsed.rows)
    _, source, _, files, errors = read_package(KIT, "full")
    if errors or any(files[k] != v for k, v in logistics["source_files"].items()):
        raise ValueError("물류 원천 변경")
    downstream = {**source, **logistics["candidate_rows"]}
    result = inspect_impact(source, downstream, target, p["candidate_rows"],
        {r["source_scope_node_id"]: r["target_scope_node_id"] for r in connection["mapping"]})
    if any(result["checks"].values()):
        raise ValueError("기준선 대사 불일치: " + str(result["checks"]))
    _, _, _, files_after, errors_after = read_package(KIT, "full")
    if errors_after or files != files_after or any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != value for path, value in watched.items()):
        raise ValueError("조사 중 입력 변경")
    result.update({"status": "READ_ONLY_IMPACT_REVIEW_NOT_APPLIED", "installed": False, "executable": False,
        "operational_approval": False, "database_connections": 0, "new_financial_amounts_calculated": False,
        "parent_fingerprints": {k: reports[k][field] for k, (_, field) in parents.items()},
        "input_hashes_before_and_after": watched, "source_files_before_and_after": files,
        "code_evidence_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in
            (ROOT / "scripts/generate_sample_company_starter_kit.py", ROOT / "core/enterprise_financial_model.py")},
        "not_verified": ["target-context downstream bindings/ownership/certification", "actual customs/settlement policy",
            "financial document rounding policy", "payment transaction evidence", "runtime calculation results",
            "previous full regression ledger sentinel error"],
        "next": "사용자에게 전표 0.01 HALF_EVEN 및 생성기 통관식 유지의 시연 가정을 제안; 선택 전 후속 금액 후보/설치 금지"})
    result["report_fingerprint"] = fingerprint(result)
    with (STAGE / "price-impact-review.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("status", "counts", "checks", "report_fingerprint")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
