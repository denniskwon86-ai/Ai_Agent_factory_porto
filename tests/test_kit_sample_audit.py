"""Data auditor tests use independent tiny contracts; production sample inspection is read-only."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from core.data_preparation.kit_sample_audit import audit_package, inspect_rows
from core.data_preparation.business_kits import BUSINESS_KITS

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"


@pytest.fixture
def sample():
    common = dict(tenant_id="company-a", scope_node_id="plant-a",
                  data_class="SYNTHETIC", data_origin="SYNTHETIC")
    def row(**values):
        return {**common, **values}
    data = {
        "FND-01": [row(node_id="plant-a")],
        "MDM-01": [row(material_id="raw"), row(material_id="product")],
        "MDM-02": [row(supplier_id="supplier")],
        "MDM-03": [row(customer_id="customer")],
        "MDM-04": [row(location_id="warehouse")],
        "MDM-05": [row(bom_id="bom", line_no="1", output_material_id="product", input_material_id="raw",
                       component_role="INPUT", quantity_per_output="2", standard_yield="0.5",
                       input_uom="KG", output_uom="KG", effective_from="2026-01-01", effective_to="2026-12-31")],
        "PRC-01": [row(contract_id="contract", supplier_id="supplier", material_id="raw", quantity_uom="KG", currency="KRW")],
        "PRC-02": [row(po_line_id="order", contract_id="contract", supplier_id="supplier", material_id="raw",
                       quantity_uom="KG", currency="KRW", order_quantity="10")],
        "LOG-02": [row(shipment_id="shipment", po_line_id="order", shipment_quantity="6", quantity_uom="KG")],
        "LOG-03": [row(event_id="event", shipment_id="shipment")],
        "INV-01": [row(snapshot_id="stock", location_id="warehouse", material_id="raw")],
        "MFG-01": [row(plan_line_id="plan", product_id="product", plan_date="2026-09-08", plan_quantity="10",
                       quantity_uom="KG", material_requirement="40")],
        "SLS-01": [row(sales_line_id="sales", customer_id="customer", product_id="product")],
        "FIN-03": [row(document_id="document", line_no="1", currency="KRW", debit_amount="10", credit_amount="0"),
                   row(document_id="document", line_no="2", currency="KRW", debit_amount="0", credit_amount="10")],
    }
    keys = {"FND-01": ["node_id"], "MDM-01": ["material_id"], "MDM-02": ["supplier_id"],
            "MDM-03": ["customer_id"], "MDM-04": ["location_id"], "MDM-05": ["bom_id", "line_no"],
            "PRC-01": ["contract_id"], "PRC-02": ["po_line_id"], "LOG-02": ["shipment_id"],
            "LOG-03": ["event_id"], "INV-01": ["snapshot_id"], "MFG-01": ["plan_line_id"],
            "SLS-01": ["sales_line_id"], "FIN-03": ["document_id", "line_no"]}
    contracts = {key: {"business_keys": values,
                      "schema": {"fields": [{"name": f, "required": True}
                                            for f in ["tenant_id", "scope_node_id", *values]]}}
                 for key, values in keys.items()}
    return data, contracts


def codes(sample):
    return {issue["code"] for issue in inspect_rows(*sample)}


def test_valid_independent_chain_and_inputs_are_unchanged(sample):
    before = copy.deepcopy(sample)
    assert inspect_rows(*sample) == []
    assert sample == before


def test_split_shipments_cannot_each_reuse_the_entire_order(sample):
    sample[0]["LOG-02"].append({**sample[0]["LOG-02"][0], "shipment_id": "second", "shipment_quantity": "5"})
    assert "SHIPMENT_TOTAL_EXCEEDS_ORDER" in codes(sample)


def test_split_shipments_exactly_equal_order_are_valid(sample):
    sample[0]["LOG-02"].append({**sample[0]["LOG-02"][0], "shipment_id": "second", "shipment_quantity": "4"})
    assert inspect_rows(*sample) == []


def test_same_named_order_in_another_tenant_cannot_satisfy_reference(sample):
    sample[0]["LOG-02"][0]["tenant_id"] = "company-b"
    assert {"REFERENCE_NOT_UNIQUE", "SCOPE_REFERENCE"} <= codes(sample)


def test_duplicate_business_key_not_just_record_id(sample):
    sample[0]["PRC-02"].append({**sample[0]["PRC-02"][0], "record_id": "another-record"})
    assert {"DUPLICATE_BUSINESS_KEY", "REFERENCE_NOT_UNIQUE"} <= codes(sample)


@pytest.mark.parametrize("value", ["", "NaN", "Infinity", "-1"])
def test_unknown_nonfinite_negative_quantity_is_not_zero(sample, value):
    sample[0]["LOG-02"][0]["shipment_quantity"] = value
    assert "SHIPMENT_NUMBER" in codes(sample)


def test_mismatched_units_are_not_summed(sample):
    sample[0]["LOG-02"][0]["quantity_uom"] = "TON"
    assert "SHIPMENT_UNIT" in codes(sample)
    assert "SHIPMENT_TOTAL_EXCEEDS_ORDER" not in codes(sample)


def test_order_does_not_silently_change_contract_supplier(sample):
    sample[0]["PRC-02"][0]["supplier_id"] = "other"
    assert "PO_CONTRACT_MISMATCH" in codes(sample)


def test_product_bom_reconciliation_detects_wrong_stored_requirement(sample):
    sample[0]["MFG-01"][0]["material_requirement"] = "39"
    assert "BOM_PRODUCT_RECONCILIATION" in codes(sample)


def test_reconciliation_uses_input_roles_and_sums_repeated_material(sample):
    bom = sample[0]["MDM-05"]
    bom[0]["quantity_per_output"] = "1"
    bom.append({**bom[0], "line_no": "2"})
    bom.append({**bom[0], "line_no": "3", "component_role": "RETURN", "quantity_per_output": "99"})
    assert inspect_rows(*sample) == []


@pytest.mark.parametrize("field,value,code", [
    ("effective_to", "2026-01-31", "BOM_NOT_BOUND"),
    ("scope_node_id", "other-plant", "BOM_NOT_BOUND"),
    ("input_uom", "TON", "BOM_UNIT"),
])
def test_bom_binding_and_units_must_match(sample, field, value, code):
    sample[0]["MDM-05"][0][field] = value
    assert code in codes(sample)


def test_ledger_cannot_net_amounts_across_currencies(sample):
    sample[0]["FIN-03"][1]["currency"] = "USD"
    assert "LEDGER_UNBALANCED" in codes(sample)


def test_alternative_bom_versions_are_not_added_together(sample):
    sample[0]["MDM-05"].append({**sample[0]["MDM-05"][0], "bom_id": "other-version"})
    assert "BOM_AMBIGUOUS" in codes(sample)


def test_no_implicit_actual_data_promotion(sample):
    sample[0]["PRC-02"][0]["data_class"] = "REAL"
    assert "SAMPLE_PROVENANCE" in codes(sample)


def test_empty_dataset_does_not_pass(sample):
    sample[0]["MFG-01"] = []
    assert "EMPTY_DATASET" in codes(sample)


def test_inspection_never_rewrites_checked_in_samples():
    def fingerprint():
        return {p.relative_to(KIT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in KIT.rglob("*") if p.is_file() and "samples/full" not in p.as_posix()}
    before = fingerprint()
    report = audit_package(KIT)
    assert fingerprint() == before
    assert report["dataset_count"] == 35
    assert sum(report["rows"].values()) == 13585
    # This is a diagnostic run, not an assertion that the existing files are ready.
    assert report["status"] in {"FAIL", "PASS_CHECKED_SCOPE"}
    assert "DART/ECOS actual-source reconciliation" in report["not_verified"]
    assert report["issue_count"] == sum(report["issue_counts"].values())
    assert report["quantity_flow"]["status"] == "FAIL"
    assert report["issue_counts"]["Q_UNIT"] == report["quantity_flow"]["issue_counts"]["Q_UNIT"]
    assert report["quantity_flow"]["population"]["movements"] == 5000


def test_missing_csv_reports_failure_not_a_matching_empty_baseline(tmp_path):
    (tmp_path / "contracts").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({"kit_id": "fixture", "version": "1",
        "datasets": [{"dataset_id": "PRC-02"}]}), encoding="utf-8")
    (tmp_path / "contracts/PRC-02.contract.json").write_text(json.dumps({"business_keys": ["po_line_id"],
        "schema": {"fields": [{"name": "po_line_id", "required": True}]}}), encoding="utf-8")
    report = audit_package(tmp_path)
    assert report["status"] == "FAIL"
    assert report["issue_counts"]["UNREADABLE_ASSET"] == 1


@pytest.mark.parametrize("datasets", [[], [{"dataset_id": "PRC-02"}, {"dataset_id": "PRC-02"}]])
def test_empty_or_duplicate_manifest_never_passes(tmp_path, datasets):
    (tmp_path / "manifest.json").write_text(json.dumps({"datasets": datasets}), encoding="utf-8")
    with pytest.raises(ValueError, match="nonempty and unique"):
        audit_package(tmp_path)


def test_guides_cover_every_declared_business_area_not_just_seven_apps():
    guides = json.loads((ROOT / "frontend/src/content/kitGettingStarted.json").read_text(encoding="utf-8"))
    assert guides["kit_id"] == "KIT-MFG-NONFERROUS-PROCUREMENT"
    assert guides["version"] == "1.0.0"
    assert [g["id"] for g in guides["groups"]] == [g["business_kit_id"] for g in BUSINESS_KITS]
    for guide in guides["groups"]:
        assert all(guide[field].strip() for field in ("question", "bring", "check", "handoff", "limit"))
