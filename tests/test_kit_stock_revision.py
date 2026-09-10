"""검토 후보만 생성. 독립된 작은 원장으로 수량·단위·기간·미변경을 검증한다."""
import copy
import csv
from decimal import Decimal
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.data_preparation.kit_stock_revision import rebuild_stock_candidate
from core.data_preparation.kit_quantity_audit import inspect_quantity_flow
from core.data_preparation.kit_sample_revision import plan_package_revision
from tests.test_kit_quantity_audit import flow

KIT = Path(__file__).resolve().parents[1] / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"


@pytest.fixture
def stock_case(flow):
    flow["FND-03"] = [{"tenant_id": "company", "reference_type": "CONVERSION", "reference_key": "TON_KG",
                       "unit": "KG/TON", "value": "1000", "effective_date": "2026-09-01"}]
    flow["MDM-05"] = [{"tenant_id": "company", "scope_node_id": "plant", "bom_id": "bom", "line_no": "1",
                       "output_material_id": "product", "input_material_id": "raw", "input_uom": "KG",
                       "output_uom": "KG", "component_role": "INPUT", "effective_from": "2026-09-01",
                       "effective_to": "9999-12-31", "quantity_per_output": "1", "standard_yield": "1"}]
    flow["INV-01"][0].update(unrestricted_quantity="999", quality_quantity="0", blocked_quantity="0")
    for rows in flow.values():
        for row in rows:
            row.update(data_class="SYNTHETIC", data_origin="SYNTHETIC", quality_status="PASS",
                       certification_status="CERTIFIED_FOR_DEMO")
    return flow


def test_rebuild_from_source_not_wrong_snapshot_and_preserve_original(stock_case):
    original = copy.deepcopy(stock_case)
    result, report = rebuild_stock_candidate(stock_case)
    assert stock_case == original
    assert result["INV-01"][0]["unrestricted_quantity"] == "10.500"  # 10+5-4-.5, not 999.
    assert result["INV-01"][0]["safety_stock_quantity"] == "50.000"  # policy is not stock.
    assert result["INV-02"] == original["INV-02"]
    assert report["candidate_check"] == "PASS_CHECKED_SCOPE"
    assert inspect_quantity_flow(result)["status"] == "PASS_CHECKED_SCOPE"
    assert rebuild_stock_candidate(stock_case) == (result, report)
    for change in report["changes"]:
        assert change["after"]["certification_status"] == "UNVERIFIED_CANDIDATE"
    # 재실행도 같은 값. 생성된 후보에 환산계수를 또 곱하지 않는다.
    again, again_report = rebuild_stock_candidate(result)
    assert again == result and again_report["changes"] == []


def test_ton_to_kg_converts_quantity_and_policy_but_rebuilds_mixed_stock(stock_case):
    stock_case["INV-02"][-1].update(quantity_uom="TON", quantity="-0.0005")
    stock_case["INV-01"][0].update(quantity_uom="TON", unrestricted_quantity="100.25", safety_stock_quantity="0.05")
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-02"][-1]["quantity"] == "-0.500"
    assert result["INV-02"][-1]["quantity_uom"] == "KG"
    assert result["INV-01"][0]["unrestricted_quantity"] == "10.500"
    assert result["INV-01"][0]["safety_stock_quantity"] == "50.000"
    assert report["change_counts"]["CONVERT_QUANTITY_AND_UNIT"] == 1
    conversion = next(c for c in report["changes"] if c["dataset"] == "INV-02")
    assert conversion["factor"] == "1000" and conversion["reference"] == stock_case["FND-03"][0]
    assert len(conversion["reference_fingerprint"]) == 64


@pytest.mark.parametrize("problem,reason", [
    ("missing", "NO_EFFECTIVE_CONVERSION"), ("future", "NO_EFFECTIVE_CONVERSION"),
    ("other_company", "NO_EFFECTIVE_CONVERSION"), ("duplicate", "AMBIGUOUS_CONVERSION"),
    ("zero", "INVALID_CONVERSION_FACTOR"), ("wrong_factor", "CONVERSION_FACTOR_CONFLICTS_WITH_UNIT"),
    ("nan", "NONFINITE_NUMBER"), ("fraction", "CONVERSION_PRECISION_LOSS"),
])
def test_unbound_bad_conversion_never_relabels_or_rebuilds_subtotal(stock_case, problem, reason):
    stock_case["INV-02"][-1].update(quantity_uom="TON", quantity="-0.0005")
    if problem == "missing":
        stock_case["FND-03"] = []
    elif problem == "duplicate":
        stock_case["FND-03"] *= 2
    elif problem == "fraction":
        stock_case["INV-02"][-1]["quantity"] = "0.0000001"
    else:
        key, value = {"future": ("effective_date", "2026-10-01"), "other_company": ("tenant_id", "other"),
                      "zero": ("value", "0"), "nan": ("value", "NaN"), "wrong_factor": ("value", "999")}[problem]
        stock_case["FND-03"][0][key] = value
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-02"] == stock_case["INV-02"]
    assert result["INV-01"][0] == stock_case["INV-01"][0]
    assert reason in {h["reason"] for h in report["held"]}
    assert report["candidate_check"] == "FAIL"


def test_ea_never_mass_converted_even_with_fabricated_reference(stock_case):
    stock_case["MDM-01"][0]["base_uom"] = "EA"
    stock_case["FND-03"].append({**stock_case["FND-03"][0], "unit": "EA/KG", "value": "1"})
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-02"] == stock_case["INV-02"]
    assert result["INV-01"][0] == stock_case["INV-01"][0]
    assert any(h["reason"] == "NO_COUNT_MASS_CONVERSION" for h in report["held"])


def test_effective_conversion_uses_movement_day_not_snapshot_day(stock_case):
    stock_case["INV-02"][-1].update(quantity_uom="TON", quantity="-0.0005")
    stock_case["FND-03"][0]["effective_date"] = "2026-09-10"
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-02"][-1] == stock_case["INV-02"][-1]
    assert report["candidate_check"] == "FAIL"


def test_negative_stock_preserved_and_first_shortfall_has_source(stock_case):
    stock_case["INV-02"][0]["quantity"] = "1"
    stock_case["INV-02"][-1]["quantity"] = "-5"
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-01"][0]["unrestricted_quantity"] == "-3.000"
    assert result["INV-02"] == stock_case["INV-02"]
    shortage = report["shortages"][0]
    assert shortage["first_shortfall"]["date"] == "2026-09-05"
    assert shortage["first_shortfall"]["balance_before_day"] == "2"
    assert shortage["minimum_daily_balance"] == "-3"
    assert shortage["first_shortfall"]["movements"][0]["id"] == "adjust"
    assert shortage["additional_quantity_applied"] == "0"
    assert report["candidate_check"] == "FAIL"


def test_shortfall_between_month_ends_is_not_hidden(stock_case):
    stock_case["INV-02"][0]["quantity"] = "1"
    stock_case["INV-02"][-1]["quantity"] = "-5"
    stock_case["INV-02"].append({**stock_case["INV-02"][-1], "movement_id": "recovered", "quantity": "10",
                               "movement_date": "2026-09-10"})
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-01"][0]["unrestricted_quantity"] == "7.000"
    assert report["shortages"] and report["candidate_check"] == "FAIL"


def test_future_movements_do_not_enter_current_snapshot(stock_case):
    stock_case["INV-02"].append({**stock_case["INV-02"][-1], "movement_id": "future", "quantity": "100",
                               "movement_date": "2026-10-02"})
    result, _ = rebuild_stock_candidate(stock_case)
    assert result["INV-01"][0]["unrestricted_quantity"] == "10.500"


@pytest.mark.parametrize("problem", ["source_total", "unknown_type", "duplicate_move", "missing_dataset", "duplicate_snapshot"])
def test_invalid_inputs_not_discarded_to_obtain_a_green_balance(stock_case, problem):
    if problem == "source_total":
        stock_case["MFG-02"][0]["input_quantity"] = "100"
    elif problem == "unknown_type":
        stock_case["INV-02"][0]["movement_type"] = "UNKNOWN"
    elif problem == "duplicate_move":
        stock_case["INV-02"].append(copy.deepcopy(stock_case["INV-02"][0]))
    elif problem == "missing_dataset":
        stock_case["LOG-05"] = []
    else:
        stock_case["INV-01"].append(copy.deepcopy(stock_case["INV-01"][0]))
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-01"][0] == stock_case["INV-01"][0]
    assert report["candidate_check"] == "FAIL"


def test_quality_or_blocked_stock_not_reclassified_as_unrestricted(stock_case):
    stock_case["INV-01"][0]["quality_quantity"] = "2"
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-01"][0] == stock_case["INV-01"][0]
    assert any(h["reason"] == "STOCK_COMPARTMENT_ALLOCATION_UNBOUND" for h in report["held"])


def test_new_warehouse_requires_exact_own_policy_reference(stock_case):
    reference = [copy.deepcopy(stock_case["INV-01"][1])]
    stock_case["INV-01"] = stock_case["INV-01"][:1]
    result, report = rebuild_stock_candidate(stock_case)
    assert len(result["INV-01"]) == 1
    assert any(h["reason"] == "NEW_WAREHOUSE_POLICY_UNBOUND" for h in report["held"])
    result, report = rebuild_stock_candidate(stock_case, stock_reference=reference)
    assert len(result["INV-01"]) == 2
    assert result["INV-01"][1]["unrestricted_quantity"] == "3.000"
    added = next(c for c in report["changes"] if c["action"] == "ADD_DERIVED_STOCK")
    assert added["before"] is None and len(added["reference_stock_fingerprint"]) == 64


@pytest.mark.parametrize("problem", ["company", "scope", "date", "duplicate", "non_synthetic"])
def test_new_warehouse_does_not_borrow_foreign_or_ambiguous_reference(stock_case, problem):
    reference = [copy.deepcopy(stock_case["INV-01"].pop())]
    if problem == "non_synthetic":
        reference[0]["data_origin"] = "PUBLIC"
        with pytest.raises(ValueError, match="SYNTHETIC_ONLY"):
            rebuild_stock_candidate(stock_case, stock_reference=reference)
        return
    if problem == "duplicate":
        reference *= 2
    else:
        key, value = {"company": ("tenant_id", "other"), "scope": ("scope_node_id", "other"),
                      "date": ("snapshot_date", "2026-08-31")}[problem]
        reference[0][key] = value
    result, report = rebuild_stock_candidate(stock_case, stock_reference=reference)
    assert len(result["INV-01"]) == 1 and report["candidate_check"] == "FAIL"


def test_multi_input_bom_is_not_claimed_verified_by_single_input_batch(stock_case):
    stock_case["MDM-05"].append({**stock_case["MDM-05"][0], "line_no": "2", "input_material_id": "other-raw"})
    _, report = rebuild_stock_candidate(stock_case)
    assert report["production_input_contract"]["issue_counts"] == {"MULTI_INPUT_NOT_REPRESENTABLE": 1}
    assert report["candidate_check"] == "FAIL"


def test_actual_inputs_rejected(stock_case):
    stock_case["INV-02"][0]["data_origin"] = "ACTUAL"
    with pytest.raises(ValueError, match="SYNTHETIC_ONLY"):
        rebuild_stock_candidate(stock_case)


def test_identical_numeric_values_are_not_changes(stock_case):
    stock_case["INV-01"][0]["unrestricted_quantity"] = "10.50"
    result, report = rebuild_stock_candidate(stock_case)
    assert result == stock_case and report["changes"] == []
    assert report["rebuilt_snapshot_count"] == 2


def test_latest_effective_reference_and_inverse_are_explicit(stock_case):
    stock_case["INV-02"][-1].update(quantity_uom="TON", quantity="-0.0005")
    ref = stock_case["FND-03"][0]
    stock_case["FND-03"] = [{**ref, "effective_date": "2026-08-01", "value": "999"},
                           {**ref, "unit": "TON/KG", "value": "0.001"},
                           {**ref, "effective_date": "2026-12-01", "value": "123"}]
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-02"][-1]["quantity"] == "-0.500"
    assert report["candidate_check"] == "PASS_CHECKED_SCOPE"


def test_source_unit_mismatch_is_not_individually_relabelled(stock_case):
    stock_case["INV-02"][3]["quantity_uom"] = "TON"
    result, report = rebuild_stock_candidate(stock_case)
    assert result["INV-02"] == stock_case["INV-02"]
    assert result["INV-01"][0] == stock_case["INV-01"][0]
    assert report["candidate_check"] == "FAIL"


def test_real_full_remains_held_and_does_not_backdate_bom():
    report = plan_package_revision(KIT, "full", repair_warehouses=True, resolve_exact_bom_copies=True, rebuild_stock=True)
    assert report["after"]["issue_counts"] == {"BOM_NOT_BOUND": 843}
    stock = report["stock_revision"]
    assert stock["change_counts"]["CONVERT_QUANTITY_AND_UNIT"] == 46
    assert stock["rebuilt_snapshot_count"] == 34524
    # 새 개수 단위 검사가 full 원본의 소수 EA 입출고도 포착한다. 검사의 상수를
    # 기대값으로 재사용하지 않고 원본 CSV를 독립적으로 대조한다.
    with (KIT / "samples/full/INV-02.csv").open(encoding="utf-8-sig", newline="") as stream:
        fractional_ea = [r for r in csv.DictReader(stream) if r["quantity_uom"] == "EA"
                         and Decimal(r["quantity"]) % 1 != 0]
    assert len(fractional_ea) == 260
    assert report["quantity_flow"]["issue_counts"] == {"Q_NEGATIVE_STOCK": 1082, "Q_UNIT": 27778, "Q_COUNT": 260}
    assert stock["production_input_contract"]["issue_counts"] == {
        "NO_EFFECTIVE_INPUT_BOM": 1131, "MULTI_INPUT_NOT_REPRESENTABLE": 459, "BOM_MASTER_UNIT_MISMATCH": 2975}
    assert len(stock["shortages"]) == 24 and stock["candidate_check"] == "FAIL"
    assert not [c for c in report["changes"] if c["dataset"] == "MDM-05"]
    assert report["candidate_check"] == "FAIL"


def test_real_quick_candidate_and_cli_are_wired_without_writing_sources(tmp_path):
    source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()}
    original = plan_package_revision(KIT, repair_warehouses=True, resolve_exact_bom_copies=True)
    report = plan_package_revision(KIT, repair_warehouses=True, resolve_exact_bom_copies=True, rebuild_stock=True)
    assert original["stock_revision"] is None
    assert report["stock_revision"]["change_counts"]["CONVERT_QUANTITY_AND_UNIT"] == 108
    assert report["stock_revision"]["rebuilt_snapshot_count"] == 462
    assert report["stock_revision"]["production_input_contract"]["issue_counts"] == {
        "MULTI_INPUT_NOT_REPRESENTABLE": 217, "BOM_MASTER_UNIT_MISMATCH": 108}
    assert len(report["stock_revision"]["shortages"]) == 5
    with (KIT / "samples/quick/INV-02.csv").open(encoding="utf-8-sig", newline="") as stream:
        fractional_ea = [r for r in csv.DictReader(stream) if r["quantity_uom"] == "EA"
                         and Decimal(r["quantity"]) % 1 != 0]
    assert len(fractional_ea) == 19
    assert report["quantity_flow"]["issue_counts"] == {"Q_NEGATIVE_STOCK": 16, "Q_UNIT": 972, "Q_COUNT": 19}
    assert report["quantity_flow"]["issue_counts"]["Q_UNIT"] < original["quantity_flow"]["issue_counts"]["Q_UNIT"]
    assert report["candidate_check"] == "FAIL" and report["warehouse_rebuild_required"]
    assert report["proposal_fingerprint"] == plan_package_revision(
        KIT, repair_warehouses=True, resolve_exact_bom_copies=True, rebuild_stock=True)["proposal_fingerprint"]
    path = tmp_path / "stock-candidate.json"
    run = subprocess.run([sys.executable, "-m", "scripts.plan_business_kit_initial_revision", "--rebuild-stock",
                          "--repair-warehouses", "--resolve-exact-bom-copies", "--report", str(path)],
                         capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 1, run.stderr
    assert json.loads(path.read_text(encoding="utf-8")) == report
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()} == source_hashes
