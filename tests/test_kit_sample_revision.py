"""조직/BOM 후보는 설치·인증을 대신하지 않고 원본 바이트를 바꾸지 않는다."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.data_preparation import kit_sample_revision as revision
from core.data_preparation.kit_sample_audit import audit_package

KIT = Path(__file__).resolve().parents[1] / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"


@pytest.fixture
def candidate():
    def row(**values):
        return dict(tenant_id="a", scope_node_id="plant", data_class="SYNTHETIC",
                    data_origin="SYNTHETIC", certification_status="CERTIFIED_FOR_DEMO", **values)
    root = row(node_id="root", parent_id="")
    root["scope_node_id"] = "root"
    org = [root, row(node_id="division", parent_id="root"), row(node_id="plant", parent_id="division")]
    data = {
        "FND-01": [root],
        "MDM-01": [row(material_id="raw"), row(material_id="product")],
        "MDM-05": [row(bom_id="b1", line_no="1", output_material_id="product", input_material_id="raw",
                       component_role="INPUT", quantity_per_output="0.5", standard_yield="0.5",
                       input_uom="KG", output_uom="KG", effective_from="2024-01-01", effective_to="9999-12-31")],
        "MFG-01": [row(plan_line_id="plan", product_id="product", plan_quantity="10", plan_date="2026-09-08",
                       quantity_uom="KG", material_requirement="1")],
    }
    data["MDM-05"] += [
        {**data["MDM-05"][0], "line_no": "2"},
        {**data["MDM-05"][0], "line_no": "3", "component_role": "RETURN", "quantity_per_output": "99"},
    ]
    keys = {"FND-01": ["node_id"], "MDM-01": ["material_id"], "MDM-05": ["bom_id", "line_no"],
            "MFG-01": ["plan_line_id"]}
    contracts = {key: {"business_keys": fields, "schema": {"fields": [
        {"name": field, "required": True} for field in ["tenant_id", "scope_node_id", *fields]]}}
        for key, fields in keys.items()}
    return data, contracts, org


def plans(report):
    return [c for c in report["changes"] if c["dataset"] == "MFG-01"]


def test_candidate_completes_ancestors_and_reconciles_input_roles_yield(candidate):
    original = copy.deepcopy(candidate)
    report = revision.propose_revision(*candidate)
    assert candidate == original
    assert report["status"] == "REVIEW_ONLY"
    assert report["candidate_check"] == "PASS_CHECKED_SCOPE"
    assert report["change_counts"] == {"FND-01": 2, "MFG-01": 1}
    assert report["after"]["issue_count"] == 0
    assert [c["key"] for c in report["changes"][:2]] == ["division", "plant"]
    assert plans(report)[0]["before"]["material_requirement"] == "1"
    # 독립 기대값: 10 * (0.5+0.5) / 0.5 = 20; RETURN 99는 투입 아님.
    assert plans(report)[0]["after"]["material_requirement"] == "20.000"
    assert all(c["after"]["certification_status"] == "UNVERIFIED_CANDIDATE" for c in report["changes"])
    assert all(c["after"]["data_class"] == "SYNTHETIC" for c in report["changes"])
    assert len(plans(report)[0]["source_bom_rows"]) == 2
    assert report == revision.propose_revision(*candidate)


def test_round_after_sum_not_each_material(candidate):
    data = candidate[0]
    data["MDM-01"].append({**data["MDM-01"][0], "material_id": "other"})
    for i, b in enumerate(data["MDM-05"][:2]):
        b.update(input_material_id=("raw", "other")[i], quantity_per_output="0.00051", standard_yield="1")
    data["MFG-01"][0]["plan_quantity"] = "1"
    report = revision.propose_revision(*candidate)
    # 각 자재 반올림 후 합은 0.002지만 총량에 마지막 한 번이면 0.001이다.
    assert plans(report)[0]["after"]["material_requirement"] == "0.001"


@pytest.mark.parametrize("field,value", [
    ("effective_from", "2027-01-01"), ("effective_to", "2026-01-01"),
    ("input_uom", "TON"), ("scope_node_id", "other"), ("tenant_id", "b"),
    ("standard_yield", "0"), ("standard_yield", "1.1"),
    ("standard_yield", "NaN"), ("standard_yield", "Infinity"),
])
def test_unbound_or_conflicting_bom_stays_held(candidate, field, value):
    for b in candidate[0]["MDM-05"]:
        b[field] = value
    original = copy.deepcopy(candidate)
    report = revision.propose_revision(*candidate)
    assert plans(report) == []
    assert any(h["dataset"] == "MFG-01" for h in report["held"])
    assert report["candidate_check"] == "FAIL"
    assert candidate == original


def test_no_historical_backdating(candidate):
    candidate[0]["MFG-01"][0]["plan_date"] = "2023-12-31"
    report = revision.propose_revision(*candidate)
    assert report["after"]["issue_counts"]["BOM_NOT_BOUND"] == 1
    assert plans(report) == []
    assert report["held"][-1]["plan_date"] == "2023-12-31"
    assert candidate[0]["MDM-05"][0]["effective_from"] == "2024-01-01"


def test_no_combining_alternative_boms(candidate):
    candidate[0]["MDM-05"].append({**candidate[0]["MDM-05"][0], "bom_id": "alternative"})
    assert plans(revision.propose_revision(*candidate)) == []


def test_same_material_different_yields_are_not_chosen(candidate):
    candidate[0]["MDM-05"][1]["standard_yield"] = "0.9"
    assert plans(revision.propose_revision(*candidate)) == []


@pytest.mark.parametrize("problem", ["other_tenant", "duplicate", "cycle", "missing_parent"])
def test_no_invented_or_partially_added_organization(candidate, problem):
    org = candidate[2]
    if problem == "other_tenant":
        org[-1]["tenant_id"] = "b"
    elif problem == "duplicate":
        org.append(copy.deepcopy(org[-1]))
    elif problem == "cycle":
        org[-1]["parent_id"] = "plant"
    else:
        org[1]["parent_id"] = "missing"
    report = revision.propose_revision(*candidate)
    assert report["change_counts"] == {}
    assert report["candidate_check"] == "FAIL"
    assert any(h["dataset"] == "FND-01" for h in report["held"])


@pytest.mark.parametrize("target", ["source", "reference"])
def test_no_actual_or_public_source_rewrite(candidate, target):
    row = candidate[0]["MFG-01"][0] if target == "source" else candidate[2][-1]
    row["data_origin"] = "PUBLIC_DISCLOSURE"
    with pytest.raises(ValueError, match="합성"):
        revision.propose_revision(*candidate)


def test_product_verifier_must_actually_return_reconciliation(candidate, monkeypatch):
    monkeypatch.setattr(revision, "material_shortage", lambda **kwargs: {"reconciliation": []})
    report = revision.propose_revision(*candidate)
    assert plans(report) == []
    assert any("제품 소요량 대사" in h["reason"] for h in report["held"])


def test_current_valid_rows_have_no_value_change(candidate):
    candidate[0]["MFG-01"][0]["material_requirement"] = "20"
    report = revision.propose_revision(*candidate)
    assert plans(report) == []


def test_quantity_failure_blocks_candidate_even_when_bom_has_no_issues(candidate, monkeypatch):
    failure = {"status": "FAIL", "issues": [{"code": "Q_STOCK_BALANCE"}], "issue_count": 1}
    seen = []
    def check(rows):
        seen.append(rows["MFG-01"][0]["material_requirement"])
        return failure
    monkeypatch.setattr(revision, "inspect_quantity_flow", check)
    report = revision.propose_revision(*candidate)
    assert seen == ["20.000"]  # Candidate rows, not stale source rows.
    assert report["after"]["issue_count"] == 0 and report["held"] == []
    assert report["quantity_flow"] == failure
    assert report["candidate_check"] == "FAIL"


def test_real_quick_assets_candidate_keeps_ambiguous_boms_without_touching_source():
    def hashes():
        return {str(p.relative_to(KIT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in KIT.rglob("*") if p.is_file()}
    before = hashes()
    report = revision.plan_package_revision(KIT, "quick")
    assert report["before"]["issue_counts"] == {
        "BOM_PRODUCT_RECONCILIATION": 333, "BOM_AMBIGUOUS": 167, "SCOPE_REFERENCE": 3215}
    assert report["change_counts"] == {"FND-01": 3, "MFG-01": 333}
    assert report["candidate_check"] == "FAIL"
    assert report["after"]["issue_counts"] == {"BOM_AMBIGUOUS": 167}
    assert len(report["held"]) == 167
    assert plans(report)[0]["after"]["material_requirement"] == "2.188"
    assert len(report["source_files"]) == 35
    assert report["contracts_fingerprint"]
    assert hashes() == before
    # 후보일 뿐이다. 원본의 문제는 그대로 남아 있어야 한다.
    assert audit_package(KIT, "quick")["status"] == "FAIL"


def test_cli_missing_source_is_unavailable_not_success(tmp_path):
    result = subprocess.run([sys.executable, "-m", "scripts.plan_business_kit_initial_revision",
                             "--kit-root", str(tmp_path / "absent")],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "UNAVAILABLE"


def test_real_full_candidate_preserves_all_pre_bom_plans():
    report = revision.plan_package_revision(KIT, "full")
    assert report["change_counts"] == {"MFG-01": 5157}
    assert report["after"]["issue_counts"] == {"BOM_NOT_BOUND": 843}
    assert report["candidate_check"] == "FAIL"
    assert len(report["held"]) == 843
    assert all(row["plan_date"] < "2024-01-01" for row in report["held"])


def test_cli_does_not_overwrite_prior_report(tmp_path):
    target = tmp_path / "report.json"
    target.write_text("preserved report", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "scripts.plan_business_kit_initial_revision",
                             "--report", str(target)], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "UNAVAILABLE"
    assert target.read_text(encoding="utf-8") == "preserved report"


def test_cli_real_candidate_reports_failure_not_completion(tmp_path):
    target = tmp_path / "candidate.json"
    result = subprocess.run([sys.executable, "-m", "scripts.plan_business_kit_initial_revision",
                             "--report", str(target)], capture_output=True, text=True)
    assert result.returncode == 1
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["status"] == "REVIEW_ONLY"
    assert report["candidate_check"] == "FAIL"
    assert len(report["held"]) == 167


@pytest.fixture
def copied_bom(candidate):
    data, contracts, org = candidate
    reference = copy.deepcopy(data["MDM-05"])
    data["MDM-05"] += [{**row, "bom_id": "copy-b1", "record_id": f"copy-{i}",
                        "lineage_id": f"copy-lineage-{i}"} for i, row in enumerate(reference)]
    return data, contracts, org, reference


def test_exact_copy_resolution_keeps_source_and_uses_reference_identity(copied_bom):
    data, contracts, org, reference = copied_bom
    original = copy.deepcopy(copied_bom)
    report = revision.propose_revision(data, contracts, org, reference_bom=reference)
    assert copied_bom == original
    assert report["candidate_check"] == "PASS_CHECKED_SCOPE"
    assert report["change_counts"] == {"FND-01": 2, "MDM-05": 3, "MFG-01": 1}
    removed = [c for c in report["changes"] if c["dataset"] == "MDM-05"]
    assert {c["key"][0] for c in removed} == {"copy-b1"}
    assert all(c["after"] is None and c["before"] and c["retained_bom_id"] == "b1" for c in removed)
    assert all(len(c["reference_bom_rows"]) == 3 for c in removed)
    assert plans(report)[0]["after"]["material_requirement"] == "20.000"
    assert report == revision.propose_revision(data, contracts, org, reference_bom=reference)
    # 명시 옵션 없는 종전 경로는 여전히 대체판 충돌을 보류한다.
    assert revision.propose_revision(data, contracts, org)["candidate_check"] == "FAIL"


@pytest.mark.parametrize("field,value", [
    ("quantity_per_output", "0.6"), ("standard_yield", "0.6"),
    ("input_uom", "TON"), ("effective_to", "2026-12-31"),
    ("component_role", "INPUT"), ("byproduct_material_id", "other"),
    ("future_business_field", "must-not-be-ignored"),
])
def test_different_bom_content_never_coalesces(copied_bom, field, value):
    data, contracts, org, reference = copied_bom
    data["MDM-05"][-1][field] = value
    report = revision.propose_revision(data, contracts, org, reference_bom=reference)
    assert report["candidate_check"] == "FAIL"
    assert not [c for c in report["changes"] if c["dataset"] == "MDM-05"]
    assert plans(report) == []


@pytest.mark.parametrize("problem", ["missing", "other_tenant", "other_scope", "two_versions", "duplicate_line", "referenced_copy"])
def test_copy_resolution_requires_unambiguous_reference_and_no_consumers(copied_bom, problem):
    data, contracts, org, reference = copied_bom
    if problem == "missing":
        reference.clear()
    elif problem in {"other_tenant", "other_scope"}:
        for row in reference:
            row["tenant_id" if problem == "other_tenant" else "scope_node_id"] = "other"
    elif problem == "two_versions":
        reference += [{**r, "bom_id": "another"} for r in reference.copy()]
    elif problem == "duplicate_line":
        reference.append(copy.deepcopy(reference[0]))
    else:
        data["MFG-01"][0]["selected_bom_id"] = "copy-b1"
    report = revision.propose_revision(data, contracts, org, reference_bom=reference)
    assert report["candidate_check"] == "FAIL"
    assert not [c for c in report["changes"] if c["dataset"] == "MDM-05"]


def test_real_quick_exact_copy_candidate_reconciles_all_500_plans():
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()}
    report = revision.plan_package_revision(KIT, "quick", resolve_exact_bom_copies=True)
    assert report["status"] == "REVIEW_ONLY"
    # Organization/BOM are reconciled, but the newly checked inventory chain is not.
    assert report["candidate_check"] == "FAIL"
    assert report["quantity_flow"]["status"] == "FAIL"
    assert report["quantity_flow"]["issue_counts"]["Q_UNIT"] > 0
    assert report["quantity_flow"]["issue_counts"]["Q_NEGATIVE_STOCK"] > 0
    assert report["after"]["issue_count"] == 0 and report["held"] == []
    assert report["change_counts"] == {"FND-01": 3, "MDM-05": 5, "MFG-01": 500}
    assert plans(report)[0]["before"]["material_requirement"] == "66.4"
    assert plans(report)[0]["after"]["material_requirement"] == "33.673"
    assert report["bom_reference"]["sha256"]
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()} == before


def test_full_historical_gaps_remain_even_with_copy_resolution():
    report = revision.plan_package_revision(KIT, "full", resolve_exact_bom_copies=True)
    assert report["candidate_check"] == "FAIL"
    assert report["after"]["issue_counts"] == {"BOM_NOT_BOUND": 843}
    assert len(report["held"]) == 843
    assert all(h["plan_date"] < "2024-01-01" for h in report["held"])


def test_cli_explicit_copy_resolution_is_checked_candidate_not_certification(tmp_path):
    target = tmp_path / "candidate.json"
    result = subprocess.run([sys.executable, "-m", "scripts.plan_business_kit_initial_revision",
                             "--resolve-exact-bom-copies", "--report", str(target)], capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["status"] == "REVIEW_ONLY" and report["after"]["issue_count"] == 0
    assert report["bom_copy_rule"] == "exact-bom-copy-against-full/1"
    assert report["quantity_flow"]["status"] == "FAIL"


def test_generator_does_not_pad_bom_count_by_repeating_products():
    from scripts.generate_sample_company_starter_kit import PROFILES, generate_bom, generate_materials
    for name, expected_products in [("quick", 6), ("full", 30)]:
        profile = PROFILES[name]
        materials = generate_materials(profile)
        original = copy.deepcopy(materials)
        rows = generate_bom(profile, materials)  # 메모리 안에서만 실행. build(clean=True)는 호출하지 않는다.
        grouped = {}
        for row in rows:
            grouped.setdefault(row["output_material_id"], set()).add(row["bom_id"])
        assert len(grouped) == expected_products
        assert all(len(ids) == 1 for ids in grouped.values())
        assert rows == generate_bom(profile, materials)
        assert materials == original
