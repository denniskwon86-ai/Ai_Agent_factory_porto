"""합성 참조 후보의 최소 변경·부정 입력·원천 결속 회귀. 설치 완료를 뜻하지 않는다."""
import copy
import json
from pathlib import Path

import pytest

from core.data_preparation.kit_logistics_revision import fingerprint, plan_logistics_revision
from core.data_preparation.kit_procurement_reference_revision import (
    IDENTITIES, inspect_procurement, plan_reference_revision, propose_reference_candidate,
)
from core.data_preparation.kit_sample_audit import read_package

KIT = Path(__file__).resolve().parents[1] / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"


@pytest.fixture(scope="module")
def full():
    _, data, _, _, errors = read_package(KIT, "full")
    assert errors == []
    return {k: data[k] for k in IDENTITIES}


def test_full_candidate_fixes_only_two_fields_and_keeps_source_intact(full):
    original = copy.deepcopy(full)
    report = propose_reference_candidate(full)
    assert full == original
    assert report == propose_reference_candidate(full)
    assert report["status"] == "REVIEW_ONLY" and report["installed"] is False
    assert report["before_counts"] == {"orders_outside_contract_period": 261,
                                        "orders_outside_supplier_materials": 1782,
                                        "contracts_outside_supplier_materials": 99}
    assert report["after_counts"] == {"orders_outside_contract_period": 0,
                                       "orders_outside_supplier_materials": 0,
                                       "contracts_outside_supplier_materials": 0}
    assert report["row_counts"] == {"PRC-01": 100, "MDM-02": 40}
    assert len(report["changes"]) == 140
    assert report["not_verified"]
    additions = 0
    for dataset, field in (("PRC-01", "valid_from"), ("MDM-02", "material_ids")):
        for old, new in zip(full[dataset], report["candidate_rows"][dataset], strict=True):
            assert {k: v for k, v in old.items() if k not in {field, "quality_status", "certification_status"}} == {
                k: v for k, v in new.items() if k not in {field, "quality_status", "certification_status"}}
            assert new["quality_status"] == "PENDING_VALIDATION"
            assert new["certification_status"] == "UNVERIFIED_CANDIDATE"
            if dataset == "PRC-01":
                orders = [p for p in full["PRC-02"] if p["contract_id"] == old["contract_id"] and p["tenant_id"] == old["tenant_id"]]
                assert new[field] == min([old[field]] + [p["order_date"] for p in orders])
            else:
                original_materials, proposed_materials = json.loads(old[field]), json.loads(new[field])
                required = {c["material_id"] for c in full["PRC-01"] if c["supplier_id"] == old["supplier_id"] and c["tenant_id"] == old["tenant_id"]}
                assert proposed_materials[:len(original_materials)] == original_materials
                assert set(proposed_materials) == set(original_materials) | required
                additions += len(proposed_materials) - len(original_materials)
    assert additions == 99
    repaired = {**full, **report["candidate_rows"]}
    assert propose_reference_candidate(repaired)["changes"] == []


@pytest.mark.parametrize("problem", ["real", "duplicate", "wrong_tenant", "material_missing", "bad_json",
                                     "duplicate_material", "unit", "total", "expiry", "bad_number", "bad_date", "empty"])
def test_unknown_or_out_of_scope_changes_fail_closed(full, problem):
    data = copy.deepcopy(full)
    if problem == "real":
        data["PRC-01"][0]["data_origin"] = "REAL"
    elif problem == "duplicate":
        data["MDM-02"].append(copy.deepcopy(data["MDM-02"][0]))
    elif problem == "wrong_tenant":
        data["MDM-02"][0]["tenant_id"] = "other-tenant"
    elif problem == "material_missing":
        data["MDM-02"][0]["material_ids"] = '["UNKNOWN-MATERIAL"]'
    elif problem == "bad_json":
        data["MDM-02"][0]["material_ids"] = '"RM-CU-CONC"'
    elif problem == "duplicate_material":
        m = json.loads(data["MDM-02"][0]["material_ids"])[0]
        data["MDM-02"][0]["material_ids"] = json.dumps([m, m])
    elif problem == "unit":
        data["PRC-02"][0]["quantity_uom"] = "KG"
    elif problem == "total":
        data["PRC-01"][0]["ordered_quantity"] = "0"
    elif problem == "expiry":
        data["PRC-02"][0].update(order_date="2028-01-01", due_date="2028-02-01")
    elif problem == "bad_number":
        data["PRC-01"][0]["contract_quantity"] = "not-a-number"
    elif problem == "bad_date":
        data["PRC-01"][0]["valid_from"] = "20240101"
    elif problem == "empty":
        data["PRC-02"] = []
    unchanged = copy.deepcopy(data)
    with pytest.raises(ValueError):
        propose_reference_candidate(data)
    assert unchanged == data


def test_parent_artifact_is_bound_to_source_not_just_self_hash(tmp_path):
    parent = plan_logistics_revision(KIT)
    path = tmp_path / "parent.json"
    path.write_text(json.dumps(parent), encoding="utf-8")
    report = plan_reference_revision(KIT, path)
    assert report["parent_logistics_fingerprint"] == parent["proposal_fingerprint"]
    assert report["candidate_check"] == "PASS_CHECKED_SCOPE"
    assert report["proposal_fingerprint"] == fingerprint({k: v for k, v in report.items() if k != "proposal_fingerprint"})
    # 자기 지문까지 다시 계산해도 원천 업무값과 다르면 차단한다.
    parent["candidate_rows"]["PRC-02"][0]["unit_price"] = "1"
    parent["candidate_rows_fingerprint"] = fingerprint(parent["candidate_rows"])
    parent["proposal_fingerprint"] = fingerprint({k: v for k, v in parent.items() if k != "proposal_fingerprint"})
    path.write_text(json.dumps(parent), encoding="utf-8")
    with pytest.raises(ValueError, match="업무값"):
        plan_reference_revision(KIT, path)


def test_after_inspection_detects_each_reintroduced_defect(full):
    repaired = {**full, **propose_reference_candidate(full)["candidate_rows"]}
    repaired["PRC-01"][0]["valid_from"] = "2024-01-01"
    counts, _ = inspect_procurement(repaired)
    assert counts["orders_outside_contract_period"] > 0
    repaired["MDM-02"][0]["material_ids"] = "[]"
    counts, _ = inspect_procurement(repaired)
    assert counts["orders_outside_supplier_materials"] > 0
