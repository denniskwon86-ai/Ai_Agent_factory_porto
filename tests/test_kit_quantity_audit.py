"""Independent small ledgers: 10 + 5 - 4 - .5 = 10.5; 2 + 3 - 2 = 3.

No stores, approvals, source edits or generator calls are used to establish truth.
"""
import copy

import pytest

from core.data_preparation.kit_quantity_audit import inspect_quantity_flow


@pytest.fixture
def flow():
    def row(**fields):
        return {"tenant_id": "company", "scope_node_id": "plant", "quantity_uom": "KG", **fields}

    def move(identity, kind, material, quantity, when, source, target, ref_type, ref):
        return row(movement_id=identity, movement_type=kind, material_id=material,
                   quantity=str(quantity), movement_date=when, from_location_id=source,
                   to_location_id=target, reference_type=ref_type, reference_id=ref)

    def snapshot(material, location, unrestricted, quality="0", blocked="0"):
        return row(snapshot_id=f"stock-{material}", material_id=material, location_id=location,
                   snapshot_date="2026-09-30", lot_id="ALL", unrestricted_quantity=unrestricted,
                   quality_quantity=quality, blocked_quantity=blocked, safety_stock_quantity="50")

    return {
        "MDM-01": [row(material_id="raw", base_uom="KG"), row(material_id="product", base_uom="KG")],
        "MDM-04": [row(location_id="raw-store", active="True"), row(location_id="fg-store", active="True")],
        "PRC-02": [row(po_line_id="po", material_id="raw", order_quantity="5")],
        "LOG-02": [row(shipment_id="ship", po_line_id="po")],
        "LOG-05": [row(transport_event_id="delivered", shipment_id="ship", event_type="DELIVERED",
                       event_at="2026-09-02T12:00:00", destination_location_id="raw-store", delivered_quantity="5")],
        "MFG-01": [row(plan_line_id="plan", product_id="product")],
        "MFG-02": [row(batch_id="batch", plan_line_id="plan", input_material_id="raw",
                       output_material_id="product", input_quantity="4", output_quantity="3", production_date="2026-09-03")],
        "SLS-01": [row(sales_line_id="sales", product_id="product", order_quantity="2", shipped_quantity="2",
                       order_date="2026-09-01", actual_ship_date="2026-09-04")],
        "INV-02": [
            move("open-r", "OPENING", "raw", 10, "2026-09-01", "", "raw-store", "OPENING_BALANCE", "initial"),
            move("open-p", "OPENING", "product", 2, "2026-09-01", "", "fg-store", "OPENING_BALANCE", "initial"),
            move("buy", "PURCHASE_RECEIPT", "raw", 5, "2026-09-02", "IN_TRANSIT", "raw-store", "SHIPMENT", "ship"),
            move("input", "PRODUCTION_ISSUE", "raw", -4, "2026-09-03", "raw-store", "PRODUCTION", "BATCH", "batch"),
            move("output", "PRODUCTION_RECEIPT", "product", 3, "2026-09-03", "PRODUCTION", "fg-store", "BATCH", "batch"),
            move("sale", "SALES_SHIPMENT", "product", -2, "2026-09-04", "fg-store", "CUSTOMER", "SALES_ORDER", "sales"),
            move("adjust", "CYCLE_COUNT_ADJUSTMENT", "raw", "-0.5", "2026-09-05", "ADJUSTMENT", "raw-store", "CYCLE_COUNT", "count"),
        ],
        "INV-01": [snapshot("raw", "raw-store", "7.5", "2", "1"), snapshot("product", "fg-store", "3")],
    }


def assert_issue(flow, code):
    result = inspect_quantity_flow(flow)
    assert result["status"] == "FAIL", result
    assert result["issue_counts"].get(code, 0) > 0, result
    return result


def test_independent_ledger_balances_without_adding_safety_stock(flow):
    original = copy.deepcopy(flow)
    result = inspect_quantity_flow(flow)
    assert result["status"] == "PASS_CHECKED_SCOPE", result
    assert result["checks"] == {"valid_movements": 7, "matched_source_totals": 3,
                                "matched_receipt_totals": 1, "matched_snapshot_totals": 2}
    assert flow == original
    assert inspect_quantity_flow(flow) == result
    flow["INV-01"][0]["safety_stock_quantity"] = "500"
    assert inspect_quantity_flow(flow) == result


def test_quantity_not_covered_is_not_pass():
    assert inspect_quantity_flow({})["status"] == "NOT_IN_SCOPE"


@pytest.mark.parametrize("dataset", ["INV-02", "INV-01", "MDM-04", "MFG-02", "LOG-05"])
def test_empty_inputs_never_reconcile_as_zero(flow, dataset):
    flow[dataset] = []
    assert_issue(flow, "Q_DATASET_UNAVAILABLE")


@pytest.mark.parametrize("value", ["", "NaN", "Infinity", "abc"])
def test_invalid_number_is_not_missing_zero(flow, value):
    flow["INV-02"][0]["quantity"] = value
    result = assert_issue(flow, "Q_NUMBER")
    assert result["checks"]["blocked_snapshot_comparisons"] == 2
    assert not result["checks"].get("matched_snapshot_totals")


@pytest.mark.parametrize("field,value,code", [
    ("movement_type", "TRANSFER", "Q_MOVEMENT_TYPE"),
    ("quantity", "4", "Q_MOVEMENT_SIGN"),
    ("movement_date", "2026-99-01", "Q_DATE"),
    ("movement_date", "2026-09-04", "Q_SOURCE_DATE"),
    ("to_location_id", "CUSTOMER", "Q_MOVEMENT_ENDPOINT"),
    ("reference_id", "absent", "Q_REFERENCE"),
    ("reference_type", "SHIPMENT", "Q_MOVEMENT_ENDPOINT"),
    ("quantity_uom", "TON", "Q_UNIT"),
    ("scope_node_id", "other", "Q_WAREHOUSE_SCOPE"),
    ("tenant_id", "other", "Q_REFERENCE"),
])
def test_bad_movement_is_explicit_and_blocks_stock_subtotal(flow, field, value, code):
    flow["INV-02"][3][field] = value
    result = assert_issue(flow, code)
    assert result["checks"]["blocked_snapshot_comparisons"] == 2


def test_unregistered_finished_warehouse_is_not_created(flow):
    flow["MDM-04"].pop()
    assert_issue(flow, "Q_REFERENCE")


def test_inactive_warehouse_is_rejected(flow):
    flow["MDM-04"][0]["active"] = "False"
    assert_issue(flow, "Q_WAREHOUSE_INACTIVE")


def test_material_can_be_held_in_other_scope_without_changing_stock_owner(flow):
    # Material-master scope is not stock custody. Warehouse scope is authoritative here.
    flow["MDM-01"][0]["scope_node_id"] = "headquarters"
    assert inspect_quantity_flow(flow)["status"] == "PASS_CHECKED_SCOPE"


@pytest.mark.parametrize("dataset", ["MDM-01", "MDM-04", "INV-02", "MFG-02", "SLS-01", "LOG-05"])
def test_duplicate_keys_do_not_select_first_row(flow, dataset):
    flow[dataset].append(copy.deepcopy(flow[dataset][0]))
    assert_issue(flow, "Q_DUPLICATE_KEY")


def test_other_company_cannot_supply_same_named_master(flow):
    flow["MDM-01"][0]["tenant_id"] = "other"
    assert_issue(flow, "Q_REFERENCE")


def test_partial_movements_are_summed_per_business_reference(flow):
    for index in (3, 5):
        row = flow["INV-02"][index]
        row["quantity"] = "-2" if index == 3 else "-1"
        flow["INV-02"].append({**row, "movement_id": row["movement_id"] + "-partial"})
    result = inspect_quantity_flow(flow)
    assert result["status"] == "PASS_CHECKED_SCOPE", result
    flow["INV-02"][-1]["quantity"] = "-2"
    assert_issue(flow, "Q_SOURCE_TOTAL")


@pytest.mark.parametrize("dataset,field,value,code", [
    ("MFG-02", "input_quantity", "5", "Q_SOURCE_TOTAL"),
    ("MFG-02", "output_quantity", "4", "Q_SOURCE_TOTAL"),
    ("MFG-02", "plan_line_id", "missing", "Q_REFERENCE"),
    ("MFG-01", "product_id", "raw", "Q_BATCH_PLAN"),
    ("SLS-01", "shipped_quantity", "1", "Q_SOURCE_TOTAL"),
    ("SLS-01", "shipped_quantity", "3", "Q_SALES_OVER_ORDER"),
    ("SLS-01", "shipped_quantity", "-1", "Q_SOURCE_QUANTITY"),
    ("LOG-05", "delivered_quantity", "6", "Q_RECEIPT_TOTAL"),
    ("LOG-05", "event_at", "2026-09-03T12:00:00", "Q_RECEIPT_TOTAL"),
    ("LOG-05", "event_at", "2026-09-02T99:00:00", "Q_DATE"),
])
def test_source_values_and_dates_are_independent_of_movement_totals(flow, dataset, field, value, code):
    flow[dataset][0][field] = value
    assert_issue(flow, code)


def test_missing_source_movement_cannot_disappear_from_denominator(flow):
    flow["INV-02"].pop(5)
    assert_issue(flow, "Q_SOURCE_TOTAL")


def test_receipt_without_delivered_event_is_not_validated_by_row_count(flow):
    flow["LOG-05"][0]["event_type"] = "DISPATCHED"
    assert_issue(flow, "Q_RECEIPT_TOTAL")


def test_duplicate_source_id_in_other_company_does_not_merge_totals(flow):
    for dataset, rows in list(flow.items()):
        flow[dataset] += [{**row, "tenant_id": "other"} for row in rows.copy()]
    result = inspect_quantity_flow(flow)
    assert result["status"] == "PASS_CHECKED_SCOPE", result
    assert result["checks"]["matched_snapshot_totals"] == 4


def test_negative_physical_stock_never_clamps_to_zero(flow):
    flow["INV-01"][0]["unrestricted_quantity"] = "-1"
    assert_issue(flow, "Q_NEGATIVE_STOCK")


def test_negative_stock_is_reported_even_if_unit_is_bad(flow):
    flow["INV-01"][0].update(unrestricted_quantity="-1", quantity_uom="TON")
    result = assert_issue(flow, "Q_NEGATIVE_STOCK")
    assert result["issue_counts"]["Q_UNIT"] == 1


def test_same_row_count_stock_change_is_detected(flow):
    flow["INV-01"][0]["quality_quantity"] = "3"
    assert_issue(flow, "Q_STOCK_BALANCE")


def test_missing_stock_row_does_not_shrink_population(flow):
    flow["INV-01"].pop()
    assert_issue(flow, "Q_SNAPSHOT_MISSING")


def test_duplicate_snapshot_and_unsupported_lot_grain(flow):
    flow["INV-01"].append(copy.deepcopy(flow["INV-01"][0]))
    assert_issue(flow, "Q_SNAPSHOT_DUPLICATE")
    flow["INV-01"].pop()
    flow["INV-01"][0]["lot_id"] = "one-lot"
    assert_issue(flow, "Q_SNAPSHOT_GRAIN")


def test_late_or_duplicate_opening_cannot_reset_ledger(flow):
    flow["INV-02"].append({**flow["INV-02"][0], "movement_id": "late", "movement_date": "2026-09-10"})
    assert_issue(flow, "Q_OPENING_POSITION")


def test_future_movements_do_not_enter_current_snapshot(flow):
    flow["INV-02"].append({**flow["INV-02"][-1], "movement_id": "future",
                          "movement_date": "2026-10-01", "quantity": "100"})
    result = inspect_quantity_flow(flow)
    assert result["status"] == "PASS_CHECKED_SCOPE", result


def test_day_order_is_deterministic_not_csv_order(flow):
    before = inspect_quantity_flow(flow)
    for rows in flow.values():
        rows.reverse()
    assert inspect_quantity_flow(flow) == before


def test_receipt_can_be_owned_by_different_scope_from_purchasing(flow):
    flow["PRC-02"][0]["scope_node_id"] = "procurement-headquarters"
    assert inspect_quantity_flow(flow)["status"] == "PASS_CHECKED_SCOPE"


def test_removing_one_companys_entire_snapshot_calendar_is_detected(flow):
    for dataset, rows in list(flow.items()):
        flow[dataset] += [{**row, "tenant_id": "other"} for row in rows.copy()]
    flow["INV-01"] = [row for row in flow["INV-01"] if row["tenant_id"] == "company"]
    assert_issue(flow, "Q_SNAPSHOT_MISSING")
