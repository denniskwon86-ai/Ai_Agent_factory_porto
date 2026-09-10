"""실제 키트 행으로 검사한다. 후보 통과는 설치·경영 계산 준비도 통과가 아니다."""
import copy
import hashlib
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation.kit_logistics_revision import (
    inspect_logistics, plan_logistics_revision, propose_logistics_candidate,
)

KIT = Path(__file__).resolve().parents[1] / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"
EXPECTED = {"PRC-02": 1800, "LOG-02": 1200, "LOG-03": 7200, "LOG-04": 1200, "LOG-05": 2400}


@pytest.fixture(scope="module")
def quick():
    _, rows, contracts, _, errors = read_package(KIT, "quick")
    assert not errors
    return {k: rows[k] for k in EXPECTED}, contracts


def codes(report):
    return {i["code"] for i in report["issues"]}


def test_real_full_and_quick_preserve_all_rows_business_values_and_reproducibility(quick):
    data, contracts = quick
    original = copy.deepcopy(data)
    assert inspect_logistics(data, contracts)["status"] == "PASS_CHECKED_SCOPE"
    candidate = propose_logistics_candidate(data, contracts)
    assert data == original
    for key in EXPECTED:
        assert candidate["candidate_rows"][key] == [
            {**r, "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE"}
            for r in original[key]]
    assert candidate["status"] == "REVIEW_ONLY" and candidate["installed"] is False
    full = plan_logistics_revision(KIT)
    assert full["candidate_check"] == "PASS_CHECKED_SCOPE"
    assert full["inspection"]["row_counts"] == EXPECTED
    assert full["inspection"]["unique_reference_counts"] == {
        "LOG-02->PRC-02": 1200, "LOG-03->LOG-02": 7200,
        "LOG-04->LOG-02": 1200, "LOG-05->LOG-02": 2400}
    assert full == plan_logistics_revision(KIT)
    changed = copy.deepcopy(data)
    changed["LOG-02"][0]["freight_amount"] = "123456"
    assert propose_logistics_candidate(changed, contracts)["candidate_rows_fingerprint"] != candidate["candidate_rows_fingerprint"]
    assert full["not_verified"]  # 검사 밖 의존성을 준비 완료로 바꾸지 않음.


@pytest.mark.parametrize("mode", ["missing", "other_tenant"])
def test_missing_parent_or_another_tenant_never_satisfies_reference(quick, mode):
    data, contracts = quick
    rows = copy.deepcopy(data)
    if mode == "missing":
        rows["LOG-02"].pop(0)
    else:
        rows["LOG-02"][0]["tenant_id"] = "unrelated-tenant"
    result = inspect_logistics(rows, contracts)
    assert result["status"] == "FAIL"
    broken = [i for i in result["issues"] if i["code"] == "REFERENCE_MISSING"]
    assert {"LOG-03", "LOG-04", "LOG-05"}.issubset({i["dataset"] for i in broken})
    assert "REFERENCE_AMBIGUOUS" not in codes(result)


def test_duplicate_parent_is_ambiguous_not_a_missing_or_arbitrary_match(quick):
    data, contracts = quick
    rows = copy.deepcopy(data)
    rows["LOG-02"].append(copy.deepcopy(rows["LOG-02"][0]))
    result = inspect_logistics(rows, contracts)
    assert {"DUPLICATE_BUSINESS_KEY", "REFERENCE_AMBIGUOUS"} <= codes(result)
    assert "REFERENCE_MISSING" not in codes(result)
    assert propose_logistics_candidate(rows, contracts)["candidate_check"] == "FAIL"


def test_parent_only_date_shift_reproduces_installed_misalignment(quick):
    data, contracts = quick
    rows = copy.deepcopy(data)
    for field in ("etd", "eta"):
        rows["LOG-02"][0][field] = (date.fromisoformat(rows["LOG-02"][0][field]) + timedelta(days=84)).isoformat()
    result = inspect_logistics(rows, contracts)
    assert "EVENT_ANCHOR_MISMATCH" in codes(result)
    assert {"LOG-04", "LOG-05"} <= {i["dataset"] for i in result["issues"] if i["code"] == "TIME_ORDER"}
    assert "REFERENCE_MISSING" not in codes(result)  # 키는 같지만 시간이 틀린 경우.


@pytest.mark.parametrize("problem", ["date_missing", "date_invalid", "real", "key_contract"])
def test_unknown_input_is_not_reported_as_a_pass(quick, problem):
    data, contracts = copy.deepcopy(quick)
    if problem == "date_missing":
        data["LOG-05"][0]["event_at"] = ""
    elif problem == "date_invalid":
        data["LOG-05"][0]["event_at"] = "2026-99-99"
    elif problem == "real":
        data["LOG-05"][0]["data_origin"] = "ACTUAL"
    else:
        contracts["LOG-05"]["business_keys"] = ["transport_id"]
    result = propose_logistics_candidate(data, contracts)
    assert result["candidate_check"] == "FAIL" and result["installed"] is False
    expected = {"date_missing": "INVALID_DATE", "date_invalid": "INVALID_DATE",
                "real": "SAMPLE_PROVENANCE", "key_contract": "CONTRACT_KEY_MISMATCH"}[problem]
    assert expected in codes(result["inspection"])


def test_cli_writes_complete_candidate_once_without_modifying_sources(tmp_path):
    before = {key: hashlib.sha256((KIT / "samples/full" / f"{key}.csv").read_bytes()).hexdigest() for key in EXPECTED}
    output = tmp_path / "logistics-review.json"
    command = [sys.executable, "-m", "scripts.plan_kit_logistics_revision", "--report", str(output)]
    result = subprocess.run(command, cwd=KIT.parents[2], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert {k: len(v) for k, v in report["candidate_rows"].items()} == EXPECTED
    saved = output.read_bytes()
    again = subprocess.run(command, cwd=KIT.parents[2], capture_output=True, text=True, timeout=60)
    assert again.returncode == 2 and output.read_bytes() == saved
    assert json.loads(again.stdout)["status"] == "UNAVAILABLE"
    assert before == {key: hashlib.sha256((KIT / "samples/full" / f"{key}.csv").read_bytes()).hexdigest() for key in EXPECTED}
