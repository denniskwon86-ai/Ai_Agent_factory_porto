"""후속 영향 조사의 순수 함수 시험. 원천/후보·DB를 쓰지 않는다."""
import copy
from decimal import Decimal

import pytest

from scripts.inspect_kit_price_impact import ap_checks, inspect_impact, number


def row(**values):
    return {"tenant_id": "source", "scope_node_id": "old-plant", "record_id": "record",
        "lineage_id": "lineage", "data_origin": "SYNTHETIC", "data_class": "SYNTHETIC",
        "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE", **values}


@pytest.fixture
def example():
    contract = row(contract_id="CTR-00002", benchmark_price="10")
    po = row(po_line_id="PO-1-10", contract_id="CTR-00002", currency="USD", quantity_uom="TON",
        order_quantity="2", unit_price="10", supplier_id="S1", due_date="2023-09-01")
    source = {
        "PRC-01": [contract], "PRC-02": [po, {**po, "po_line_id": "PO-2-10"}],
        "LOG-02": [row(shipment_id="SHP-000005", po_line_id="PO-1-10", shipment_quantity="2",
            quantity_uom="TON", freight_amount="7", freight_currency="USD")],
        "LOG-03": [row(milestone_id=f"MS-{i}", shipment_id="SHP-000005") for i in range(6)],
        "LOG-04": [row(clearance_id="C1", shipment_id="SHP-000005", duty_amount="0.2",
            currency="USD", cleared_at="2023-09-04")],
        "LOG-05": [row(transport_event_id=f"TR-{i}", shipment_id="SHP-000005", event_type=event,
            delivered_quantity="2" if i else "0", event_at="2023-09-05T00:00:00+00:00")
            for i, event in enumerate(["DISPATCHED", "DELIVERED"])],
        "INV-02": [row(movement_id="MOV1", reference_type="SHIPMENT", reference_id="SHP-000005", quantity="2")],
        "FIN-02": [row(finance_document_id="AP1", reference_id="PO-1-10", document_type="AP", amount="20",
            partner_id="S1", currency="USD", posting_date="2023-09-01", due_date="2023-10-16",
            paid_at="2023-10-13", status="PAID")],
        "FIN-03": [row(ledger_line_id=f"GL{i}", document_id="AP1", currency="USD", account_id=account,
            debit_amount=debit, credit_amount=credit) for i, (account, debit, credit) in
            enumerate([("1200", "20", "0"), ("2000", "0", "20")])],
    }
    target = {k: [{**r, "tenant_id": "target", "scope_node_id": "new-plant"} for r in source[k]]
        for k in ("PRC-01", "PRC-02")}
    price = copy.deepcopy(target)
    price["PRC-01"][0]["benchmark_price"] = "8"
    for r in price["PRC-02"]:
        r["unit_price"] = "8"
    return source, copy.deepcopy(source), target, price, {"old-plant": "new-plant"}


def test_trace_is_nonmutating_and_unshipped_has_no_invented_document(example):
    before = copy.deepcopy(example)
    result = inspect_impact(*example)
    assert example == before
    assert result["counts"]["orders"] == 2
    assert result["counts"]["unshipped_orders_without_ap"] == 1
    assert result["counts"]["payables"] == 1
    assert result["requires_amount_review_ids"] == {"LOG-04": ["C1"], "FIN-02": ["AP1"], "FIN-03": ["GL0", "GL1"]}
    assert not any(result["checks"].values())
    assert result["payables"][0]["new_amount"] is None
    assert not result["payables"][0]["cash_settlement_verified"]
    assert not result["shipments"][0]["freight_price_dependency"]


def test_balanced_ledger_does_not_prove_document_amount(example):
    source, downstream, target, price, mapping = example
    downstream["FIN-03"][0]["debit_amount"] = "19"
    downstream["FIN-03"][1]["credit_amount"] = "19"
    result = inspect_impact(*example)
    assert result["checks"]["gl_unbalanced"] == 0
    assert result["checks"]["gl_document_mismatches"] == 1


def test_binary_float_rounding_is_reported_not_silently_fixed():
    order = {"order_quantity": "46.5", "unit_price": "31575.87", "due_date": "2023-09-01"}
    doc = {"amount": "1468277.95", "posting_date": "2023-09-01"}
    lines = [{"debit_amount": doc["amount"], "credit_amount": "0"}, {"debit_amount": "0", "credit_amount": doc["amount"]}]
    result = ap_checks(order, doc, lines)
    assert result["matches_old_generator"]
    assert result["rounding_difference"] == "0.01"
    assert doc["amount"] == "1468277.95"


@pytest.mark.parametrize("problem", ["duplicate", "scope", "tenant", "actual", "price_scope", "quantity_change", "certified", "missing_ap", "missing_gl", "currency", "missing_receipt"])
def test_ambiguous_or_out_of_scope_trace_is_rejected(example, problem):
    source, downstream, target, price, mapping = example
    if problem == "duplicate":
        downstream["FIN-02"].append(dict(downstream["FIN-02"][0]))
    elif problem in ("scope", "tenant"):
        downstream["FIN-02"][0]["scope_node_id" if problem == "scope" else "tenant_id"] = "other"
    elif problem == "actual":
        downstream["FIN-03"][0]["data_origin"] = "ACTUAL"
    elif problem == "price_scope":
        mapping["old-plant"] = "wrong"
    elif problem == "quantity_change":
        price["PRC-02"][0]["order_quantity"] = "3"
    elif problem == "certified":
        price["PRC-02"][0]["certification_status"] = "CERTIFIED"
    elif problem == "missing_ap":
        downstream["FIN-02"] = []
    elif problem == "missing_gl":
        downstream["FIN-03"].pop()
    elif problem == "currency":
        downstream["FIN-02"][0]["currency"] = "KRW"
    elif problem == "missing_receipt":
        downstream["INV-02"] = []
    with pytest.raises(ValueError):
        inspect_impact(*example)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1"])
def test_invalid_amount_is_rejected(value):
    with pytest.raises(ValueError):
        number(value)


def test_zero_is_a_valid_stored_amount():
    assert number("0") == Decimal(0)
