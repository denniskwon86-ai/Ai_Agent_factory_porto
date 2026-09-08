"""배치 하나에 KG 원료 두 종·EA 소모품이 붙는 독립 예제. 실제 DB/생성기는 호출하지 않는다."""
import copy
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from core.data_preparation.kit_production_revision import rebuild_production_candidate
from core.data_preparation.production_inputs import (
    INPUT_VERSION, ProductionInputError, input_lines, model_inputs, verify_model,
)
from core.data_preparation.kit_quantity_audit import inspect_quantity_flow
from core.data_preparation.kit_stock_revision import rebuild_stock_candidate, inspect_batch_input_contract
from core.data_preparation.kit_sample_revision import plan_package_revision
from scripts.validate_sample_company_starter_kit import production_model_errors
from tests.test_kit_stock_revision import stock_case
from tests.test_kit_quantity_audit import flow

KIT = Path(__file__).resolve().parents[1] / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"


@pytest.fixture
def multi(stock_case):
    data = stock_case
    batch = data["MFG-02"][0]
    batch.update(actual_yield="0.75", input_lot_id="original-raw-lot", output_lot_id="original-product-lot",
                 record_id="original-batch-record", scrap_quantity="1")
    data["INV-02"][3]["lot_id"] = "original-raw-lot"
    data["INV-02"][4]["lot_id"] = "original-product-lot"
    for identity, unit, coefficient, opening, balance in (
            ("raw-b", "KG", "0.5", "5", "3"), ("pack", "EA", "0.2", "10", "9")):
        data["MDM-01"].append({**data["MDM-01"][0], "material_id": identity, "base_uom": unit})
        bom = {**data["MDM-05"][0], "line_no": str(len(data["MDM-05"]) + 1),
               "input_material_id": identity, "input_uom": unit, "quantity_per_output": coefficient}
        if unit == "EA":
            bom.update(consumption_basis="PER_GOOD_OUTPUT", count_rounding="CEILING")
        data["MDM-05"].append(bom)
        data["INV-02"].append({**data["INV-02"][0], "movement_id": "open-" + identity,
                              "material_id": identity, "quantity_uom": unit, "quantity": opening})
        data["INV-01"].append({**data["INV-01"][0], "snapshot_id": "stock-" + identity,
                              "material_id": identity, "quantity_uom": unit, "location_id": "raw-store",
                              "unrestricted_quantity": balance})
    data["QLT-01"] = [{**batch, "inspection_id": "quality-1", "object_ref": "batch"}]
    return data


def converted(multi):
    candidate, report = rebuild_production_candidate(multi)
    assert not report["held"], report
    return candidate


def test_three_native_inputs_keep_one_output_and_existing_references(multi):
    original = copy.deepcopy(multi)
    candidate, report = rebuild_production_candidate(multi)
    assert multi == original
    assert report["converted_batches"] == 1 and report["added_input_movements"] == 2
    assert report["status"] == "REVIEW_ONLY"
    assert report["contract_delta"]["status"] == "DRAFT_NOT_INSTALLED"
    batch = candidate["MFG-02"][0]
    assert batch["batch_id"] == "batch" and batch["record_id"] == "original-batch-record"
    assert batch["output_quantity"] == "3" and batch["output_lot_id"] == "original-product-lot"
    assert len(candidate["MFG-02"]) == 1 and candidate["QLT-01"] == original["QLT-01"]
    assert candidate["SLS-01"] == original["SLS-01"] and candidate["MFG-01"] == original["MFG-01"]
    assert candidate["INV-01"] == original["INV-01"]  # 다른 단계에서 재산출.
    assert "input_quantity" not in batch and "scrap_quantity" not in batch
    lines = {r["material_id"]: r for r in batch["input_lines"]}
    assert {m: (r["quantity"], r["quantity_uom"]) for m, r in lines.items()} == {
        "raw": ("4.000", "KG"), "raw-b": ("2.000", "KG"), "pack": ("1", "EA")}
    assert lines["raw"]["lot_id"] == "original-raw-lot"
    assert lines["pack"]["lot_id"].startswith("SYN-LOT-")
    moves = [r for r in candidate["INV-02"] if r["movement_type"] == "PRODUCTION_ISSUE"]
    assert len(moves) == 3 and len({r["input_line_id"] for r in moves}) == 3
    assert next(r for r in moves if r["material_id"] == "raw")["movement_id"] == "input"
    assert [r for r in candidate["INV-02"] if r["movement_type"] == "PRODUCTION_RECEIPT"] == [original["INV-02"][4]]
    assert all(c["after"]["certification_status"] == "UNVERIFIED_CANDIDATE" for c in report["changes"])
    assert rebuild_production_candidate(multi) == (candidate, report)
    again, again_report = rebuild_production_candidate(candidate)
    assert again == candidate and again_report["changes"] == []


def test_quantity_audit_and_stock_rebuild_consume_actual_new_shape(multi):
    candidate = converted(multi)
    candidate, stock = rebuild_stock_candidate(candidate)
    assert stock["candidate_check"] == "PASS_CHECKED_SCOPE", stock
    report = inspect_quantity_flow(candidate)
    assert report["status"] == "PASS_CHECKED_SCOPE", report
    assert report["checks"]["matched_source_totals"] == 5  # 투입3+생산1+판매1.
    assert report["checks"]["matched_synthetic_input_models"] == 1
    assert inspect_batch_input_contract(candidate)["issue_count"] == 0
    assert production_model_errors(candidate) == []
    values = {r["material_id"]: Decimal(r["unrestricted_quantity"]) for r in candidate["INV-01"]}
    assert values == {"raw": Decimal("10.5"), "raw-b": Decimal("3"), "pack": Decimal("9"), "product": Decimal("3")}


def test_csv_json_roundtrip_is_identical(multi):
    candidate = converted(multi)
    batch = candidate["MFG-02"][0]
    parsed = input_lines(batch)
    batch["input_lines"] = json.dumps(batch["input_lines"])
    assert input_lines(batch) == parsed
    assert verify_model(batch, candidate["MDM-05"], candidate["MDM-01"]) == parsed


@pytest.mark.parametrize("problem", [
    "version", "missing_version", "no_lines", "empty", "invalid_json", "object", "scalar_line",
    "blank_id", "duplicate_id", "duplicate_material", "zero", "negative", "nan", "infinity",
    "fraction_ea", "unit", "context_override", "legacy", "no_refs", "no_lot",
])
def test_invalid_new_contract_never_falls_back(multi, problem):
    candidate = converted(multi)
    batch = candidate["MFG-02"][0]
    first = batch["input_lines"][0]  # pack EA.
    if problem == "version": batch["input_contract_version"] = "unknown"
    elif problem == "missing_version": batch.pop("input_contract_version")
    elif problem == "no_lines": batch.pop("input_lines")
    elif problem == "empty": batch["input_lines"] = []
    elif problem == "invalid_json": batch["input_lines"] = "["
    elif problem == "object": batch["input_lines"] = {}
    elif problem == "scalar_line": batch["input_lines"] = ["bad"]
    elif problem == "blank_id": first["input_line_id"] = " "
    elif problem == "duplicate_id": batch["input_lines"][1]["input_line_id"] = first["input_line_id"]
    elif problem == "duplicate_material": batch["input_lines"][1]["material_id"] = first["material_id"]
    elif problem in {"zero", "negative", "nan", "infinity", "fraction_ea"}:
        first["quantity"] = {"zero": "0", "negative": "-1", "nan": "NaN",
                             "infinity": "Infinity", "fraction_ea": "0.5"}[problem]
    elif problem == "unit": first["quantity_uom"] = "BOX"
    elif problem == "context_override": first["tenant_id"] = "other-company"
    elif problem == "legacy": batch["input_quantity"] = "7"
    elif problem == "no_refs": first["bom_refs"] = []
    elif problem == "no_lot": first["lot_id"] = ""
    with pytest.raises(ProductionInputError):
        input_lines(batch)
    before = copy.deepcopy(candidate)
    result, report = rebuild_production_candidate(candidate)
    assert result == before and report["held_count"] == 1
    assert inspect_quantity_flow(candidate)["issue_counts"]["Q_INPUT_CONTRACT"]
    assert production_model_errors(candidate) == ["batch"]


@pytest.mark.parametrize("problem,reason", [
    ("unit", "BOM_MASTER_UNIT_MISMATCH"), ("no_ea_policy", "EA_CONSUMPTION_POLICY_REQUIRED"),
    ("future", "NO_EFFECTIVE_INPUT_BOM"), ("ambiguous", "AMBIGUOUS_INPUT_BOM"),
    ("duplicate_line", "DUPLICATE_BOM_LINE"), ("missing_master", "REFERENCE_NOT_UNIQUE"),
    ("yield", "INVALID_YIELD"), ("zero_coeff", "INVALID_INPUT_NUMBER"),
    ("foreign_company", "NO_EFFECTIVE_INPUT_BOM"),
])
def test_no_invented_recipe_or_count_conversion(multi, problem, reason):
    if problem == "unit": multi["MDM-05"][-1]["input_uom"] = "TON"
    elif problem == "no_ea_policy": multi["MDM-05"][-1].pop("consumption_basis")
    elif problem == "future":
        for row in multi["MDM-05"]: row["effective_from"] = "2026-10-01"
    elif problem == "ambiguous": multi["MDM-05"].append({**multi["MDM-05"][0], "bom_id": "other"})
    elif problem == "duplicate_line": multi["MDM-05"].append(copy.deepcopy(multi["MDM-05"][0]))
    elif problem == "missing_master": multi["MDM-01"].pop()
    elif problem == "yield": multi["MFG-02"][0]["actual_yield"] = "1.1"
    elif problem == "zero_coeff": multi["MDM-05"][0]["quantity_per_output"] = "0"
    elif problem == "foreign_company":
        for row in multi["MDM-05"]: row["tenant_id"] = "other"
    original = copy.deepcopy(multi)
    result, report = rebuild_production_candidate(multi)
    assert multi == result == original
    assert report["held_counts"] == {reason: 1}
    assert report["changes"] == []


def test_coefficients_sum_before_rounding_and_return_is_not_consumed(multi):
    multi["MDM-05"][0]["quantity_per_output"] = "0.3333"
    multi["MDM-05"].append({**multi["MDM-05"][0], "line_no": "4", "quantity_per_output": "0.6667"})
    multi["MDM-05"].append({**multi["MDM-05"][0], "line_no": "5", "component_role": "RETURN",
                           "quantity_per_output": "100"})
    candidate = converted(multi)
    raw = next(r for r in candidate["MFG-02"][0]["input_lines"] if r["material_id"] == "raw")
    assert raw["quantity"] == "4.000" and len(raw["bom_refs"]) == 2
    reversed_data = copy.deepcopy(multi)
    reversed_data["MDM-05"].reverse()
    assert converted(reversed_data)["MFG-02"] == candidate["MFG-02"]


@pytest.mark.parametrize("problem", ["wrong_qty", "duplicate_issue", "bad_date", "warehouse", "missing_receipt", "duplicate_batch", "id_collision"])
def test_batch_and_issues_change_atomically_or_not_at_all(multi, problem):
    if problem == "wrong_qty": multi["INV-02"][3]["quantity"] = "-3"
    elif problem == "duplicate_issue": multi["INV-02"].append({**multi["INV-02"][3], "movement_id": "another"})
    elif problem == "bad_date": multi["INV-02"][3]["movement_date"] = "2026-09-04"
    elif problem == "warehouse": multi["MDM-04"][0]["active"] = False
    elif problem == "missing_receipt": multi["INV-02"].pop(4)
    elif problem == "duplicate_batch": multi["MFG-02"].append(copy.deepcopy(multi["MFG-02"][0]))
    elif problem == "id_collision":
        preview, _ = rebuild_production_candidate(multi)
        added = next(r for r in preview["INV-02"] if r["movement_id"].startswith("MOV-INP-"))
        multi["INV-02"].append({**multi["INV-02"][0], "movement_id": added["movement_id"]})
    original = copy.deepcopy(multi)
    result, report = rebuild_production_candidate(multi)
    assert result == multi == original and report["held"] and report["changes"] == []


def test_raw_material_overage_cannot_cancel_another_material_shortfall(multi):
    candidate = converted(multi)
    issues = {r["material_id"]: r for r in candidate["INV-02"] if r["movement_type"] == "PRODUCTION_ISSUE"}
    issues["raw"]["quantity"] = "-5"
    issues["raw-b"]["quantity"] = "-1"  # 총량 6은 같아도 두 원료 모두 틀린 값.
    report = inspect_quantity_flow(candidate)
    assert report["issue_counts"]["Q_SOURCE_TOTAL"] == 2
    assert report["status"] == "FAIL"


@pytest.mark.parametrize("problem,code", [
    ("line", "Q_INPUT_LINE_REFERENCE"), ("lot", "Q_INPUT_LOT"),
    ("count", "Q_COUNT"), ("double_output", "Q_SOURCE_TOTAL"), ("stale_bom", "Q_INPUT_CONTRACT"),
])
def test_real_consumer_rejects_broken_links_and_stale_model(multi, problem, code):
    candidate = converted(multi)
    issue = next(r for r in candidate["INV-02"] if r.get("material_id") == "pack" and r["movement_type"] == "PRODUCTION_ISSUE")
    if problem == "line": issue["input_line_id"] = "unrelated"
    elif problem == "lot": issue["lot_id"] = "other"
    elif problem == "count": issue["quantity"] = "-0.5"
    elif problem == "double_output":
        candidate["INV-02"].append({**candidate["INV-02"][4], "movement_id": "duplicate-output"})
    elif problem == "stale_bom": candidate["MDM-05"][0]["quantity_per_output"] = "2"
    report = inspect_quantity_flow(candidate)
    assert report["status"] == "FAIL" and report["issue_counts"][code]
    rebuilt, _ = rebuild_stock_candidate(candidate)
    # 결함이 있는 품목은 보류하되 독립적으로 유효한 다른 품목까지 막지 않는다.
    affected = "product" if problem == "double_output" else "raw" if problem == "stale_bom" else "pack"
    assert next(r for r in rebuilt["INV-01"] if r["material_id"] == affected) == next(
        r for r in candidate["INV-01"] if r["material_id"] == affected)


def test_actual_input_is_never_rewritten_as_synthetic(multi):
    multi["MFG-02"][0]["data_origin"] = "ACTUAL"
    with pytest.raises(ProductionInputError, match="SYNTHETIC_ONLY"):
        rebuild_production_candidate(multi)


def test_installed_quick_candidate_changes_no_source_file_and_keeps_invalid_ea_recipe():
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()}
    report = plan_package_revision(KIT, resolve_exact_bom_copies=True, repair_warehouses=True,
                                   rebuild_production=True, rebuild_stock=True)
    stage = report["production_revision"]
    assert stage["converted_batches"] > 217 and stage["added_input_movements"] > 217
    assert stage["held_counts"]["BOM_MASTER_UNIT_MISMATCH"] == 108
    assert stage["contract_delta"]["status"] == "DRAFT_NOT_INSTALLED"
    assert report["candidate_check"] == "FAIL" and report["status"] == "REVIEW_ONLY"
    assert report["stock_revision"]["production_input_contract"]["issue_counts"] == {"BOM_MASTER_UNIT_MISMATCH": 108}
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()}


def test_cli_reaches_production_candidate_and_reports_remaining_blockers(tmp_path):
    target = tmp_path / "production.json"
    result = subprocess.run([sys.executable, "-m", "scripts.plan_business_kit_initial_revision",
                             "--resolve-exact-bom-copies", "--repair-warehouses", "--rebuild-production",
                             "--report", str(target)], capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["production_revision"]["converted_batches"] > 0
    assert report["production_revision"]["held_count"] > 0
    assert report["candidate_check"] == "FAIL"
