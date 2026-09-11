"""시연 후속금액 후보의 범위·반올림·차대 방향·비변경성 시험."""
import copy

import pytest

from scripts.inspect_kit_price_impact import inspect_impact
from scripts.prepare_kit_financial_candidate import amount, make_candidate


def row(**values):
    return {"tenant_id": "source", "scope_node_id": "old-plant", "record_id": "record", "lineage_id": "lineage",
        "data_origin": "SYNTHETIC", "data_class": "SYNTHETIC", "quality_status": "PENDING_VALIDATION",
        "certification_status": "UNVERIFIED_CANDIDATE", **values}


@pytest.fixture
def example():
    po = row(po_line_id="PO-1-10", contract_id="CTR-00002", currency="USD", quantity_uom="TON",
        order_quantity="2", unit_price="10", supplier_id="S1", due_date="2023-09-01")
    certified = {"quality_status": "PASS", "certification_status": "CERTIFIED_FOR_DEMO"}
    source = {
        "PRC-01": [row(contract_id="CTR-00002", benchmark_price="10")],
        "PRC-02": [po, {**po, "po_line_id": "PO-2-10"}],
        "LOG-02": [row(shipment_id="SHP-000005", po_line_id="PO-1-10", shipment_quantity="2",
            quantity_uom="TON", freight_amount="7", freight_currency="USD")],
        "LOG-03": [row(milestone_id=f"MS-{i}", shipment_id="SHP-000005") for i in range(6)],
        "LOG-04": [row(clearance_id="C1", shipment_id="SHP-000005", duty_amount="0.2", currency="USD", cleared_at="2023-09-04")],
        "LOG-05": [row(transport_event_id=f"TR-{i}", shipment_id="SHP-000005", event_type=event,
            delivered_quantity="2" if i else "0", event_at="2023-09-05T00:00:00+00:00")
            for i, event in enumerate(["DISPATCHED", "DELIVERED"])],
        "INV-02": [row(movement_id="MOV1", reference_type="SHIPMENT", reference_id="SHP-000005", quantity="2")],
        "FIN-02": [row(finance_document_id="AP1", reference_id="PO-1-10", document_type="AP", amount="20",
            partner_id="S1", currency="USD", posting_date="2023-09-01", due_date="2023-10-16",
            paid_at="2023-10-13", status="PAID", **certified)],
        "FIN-03": [row(ledger_line_id=f"GL{i}", document_id="AP1", currency="USD", account_id=account,
            debit_amount=debit, credit_amount=credit, posting_date="2023-09-01", fiscal_period="2023-09", **certified)
            for i, (account, debit, credit) in enumerate([("1200", "20", "0"), ("2000", "0", "20")])],
    }
    target = {k: [{**r, "tenant_id": "target", "scope_node_id": "new-plant"} for r in source[k]] for k in ("PRC-01", "PRC-02")}
    price = copy.deepcopy(target)
    price["PRC-01"][0]["benchmark_price"] = "8"
    for r in price["PRC-02"]:
        r["unit_price"] = "8"
    args = [source, copy.deepcopy(source), target, price, {"old-plant": "new-plant"}]
    return [*args, inspect_impact(*args)]


def test_candidate_preserves_business_values_and_source_certification_evidence(example):
    before = copy.deepcopy(example)
    result = make_candidate(*example)
    assert example == before
    assert len(result["changes"]) == 4
    assert len(result["candidate_metadata_changes"]) == 6
    assert result["candidate_rows"]["LOG-04"][0]["duty_amount"] == "0.16"
    assert result["candidate_rows"]["FIN-02"][0]["amount"] == "16.00"
    assert result["source_rows_before"]["FIN-02"][0]["certification_status"] == "CERTIFIED_FOR_DEMO"
    for dataset, rows in result["candidate_rows"].items():
        for old, new in zip(result["source_rows_before"][dataset], rows):
            changed = {k for k in new if old[k] != new[k]}
            assert changed <= {"duty_amount", "amount", "debit_amount", "credit_amount", "quality_status", "certification_status"}
            assert new["tenant_id"] == "source" and new["scope_node_id"] == "old-plant"
            assert new["certification_status"] == "UNVERIFIED_CANDIDATE"
    assert result["candidate_rows"]["FIN-02"][0]["status"] == "PAID"
    assert result["unshipped_orders_preserved"] == ["PO-2-10"]
    assert result["ap_gl_reconciliation"][0]["debit"] == result["ap_gl_reconciliation"][0]["credit"] == "16.00"
    assert result["control_totals"][0]["AP_and_GL_must_not_be_added_together"]


@pytest.mark.parametrize("quantity,price,rate,expected", [
    ("1", "2.345", "1", "2.34"), ("1", "2.355", "1", "2.36"),
    ("46.5", "31575.87", "1", "1468277.96"), ("1", "2.345", "0", "0.00"),
    ("1", "234.5", "0.01", "2.34"), ("1", "235.5", "0.01", "2.36"),
])
def test_document_round_half_even(quantity, price, rate, expected):
    assert amount(quantity, price, rate) == expected


@pytest.mark.parametrize("quantity,price,rate", [
    ("0", "1", "1"), ("1", "0", "1"), ("-1", "1", "1"), ("1", "-1", "1"),
    ("NaN", "1", "1"), ("1", "Infinity", "1"), ("1", "1", "0.05"), ("1", "1", "NaN"),
])
def test_invalid_or_unapproved_amount_inputs(quantity, price, rate):
    with pytest.raises(ValueError):
        amount(quantity, price, rate)


@pytest.mark.parametrize("problem", ["review", "balanced_wrong_sides", "wrong_period", "wrong_posting_date", "quantity", "duplicate", "currency", "scope", "actual", "price_not_changed"])
def test_bad_lineage_or_ledger_is_rejected(example, problem):
    source, downstream, target, price, mapping, review = example
    if problem == "review":
        review["counts"]["payables"] = 999
    elif problem == "balanced_wrong_sides":
        for line in downstream["FIN-03"]:
            line["debit_amount"], line["credit_amount"] = line["credit_amount"], line["debit_amount"]
    elif problem == "wrong_period":
        downstream["FIN-03"][0]["fiscal_period"] = "2023-08"
    elif problem == "wrong_posting_date":
        downstream["FIN-03"][0]["posting_date"] = "2023-09-02"
    elif problem == "quantity":
        price["PRC-02"][0]["order_quantity"] = "3"
    elif problem == "duplicate":
        downstream["FIN-03"].append(dict(downstream["FIN-03"][0]))
    elif problem == "currency":
        downstream["FIN-02"][0]["currency"] = "KRW"
    elif problem == "scope":
        mapping["old-plant"] = "other"
    elif problem == "actual":
        downstream["LOG-04"][0]["data_origin"] = "ACTUAL"
    elif problem == "price_not_changed":
        price["PRC-02"][0]["unit_price"] = "10"
    with pytest.raises(ValueError):
        make_candidate(*example)
