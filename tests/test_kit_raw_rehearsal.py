"""RAW 리허설의 입력/쓰기 경계. 운영 DB를 열지 않는 순수 함수 시험."""
import copy

import pytest

from scripts.stage_kit_raw_rehearsal import COUNTS, grouped_candidates, payload_for, sqlite_guard
from core.data_preparation.kit_procurement_reference_revision import IDENTITIES
from core.data_preparation.snapshot_service import parse_csv


@pytest.fixture
def candidate():
    return {key: [{IDENTITIES[key]: f"{key}-{i}", "tenant_id": "test-tenant",
        "scope_node_id": "company" if key == "MDM-02" else ("plant-a" if i % 2 else "plant-b"),
        "data_origin": "SYNTHETIC", "data_class": "SYNTHETIC",
        "certification_status": "UNVERIFIED_CANDIDATE", "quality_status": "PENDING_VALIDATION"}
        for i in range(count)] for key, count in COUNTS.items()}


def group(candidate):
    return grouped_candidates(candidate, "test-tenant", {
        k: {"company"} if k == "MDM-02" else {"plant-a", "plant-b"} for k in COUNTS})


def test_seven_groups_preserve_every_row(candidate):
    original = copy.deepcopy(candidate)
    groups = group(candidate)
    assert len(groups) == 7
    assert sum(map(len, groups.values())) == 2160
    assert candidate == original
    for (key, scope), rows in groups.items():
        assert rows == [r for r in original[key] if r["scope_node_id"] == scope]


@pytest.mark.parametrize("field,value", [
    ("tenant_id", "other-company"), ("scope_node_id", "unmapped"),
    ("data_origin", "ACTUAL"), ("data_class", "ACTUAL"),
    ("certification_status", "CERTIFIED_FOR_DEMO"), ("quality_status", "PASS"),
])
def test_changed_context_or_classification_rejected(candidate, field, value):
    candidate["MDM-02"][0][field] = value
    with pytest.raises(ValueError):
        group(candidate)


def test_duplicate_key_rejected(candidate):
    candidate["PRC-02"][1]["po_line_id"] = candidate["PRC-02"][0]["po_line_id"]
    with pytest.raises(ValueError):
        group(candidate)


def test_missing_rows_rejected(candidate):
    candidate["MDM-01"].pop()
    with pytest.raises(ValueError):
        group(candidate)


def test_csv_quotes_newlines_and_unicode_preserved():
    rows = [{"name": '합성 공급사, "A"\n둘째 줄', "ids": "MAT-01|MAT-02", "empty": ""}]
    assert parse_csv(payload_for(rows)).rows == rows


@pytest.mark.parametrize("rows", [[], [{"a": None}], [{"a": 1}], [{"a": "1"}, {"b": "2"}]])
def test_lossy_serialization_rejected(rows):
    with pytest.raises(ValueError):
        payload_for(rows)


def test_guard_allows_only_explicit_copy_and_ro_original(tmp_path):
    target = (tmp_path / "copy.db").resolve()
    original = tmp_path / "original.db"
    guard = sqlite_guard(target, [original, target])
    guard("sqlite3.connect", (str(target),))
    guard("sqlite3.connect", (original.resolve().as_uri() + "?mode=ro",))
    guard("unrelated", ())


@pytest.mark.parametrize("form", ["original_write", "other_copy", "rw_uri", "unknown_ro_uri", "memory"])
def test_guard_blocks_other_sqlite_targets(tmp_path, form):
    target = (tmp_path / "copy.db").resolve()
    original = tmp_path / "original.db"
    inputs = {"original_write": str(original), "other_copy": str(tmp_path / "other.db"),
              "rw_uri": original.resolve().as_uri() + "?mode=rw",
              "unknown_ro_uri": (tmp_path / "other.db").resolve().as_uri() + "?mode=ro", "memory": ":memory:"}
    with pytest.raises(PermissionError):
        sqlite_guard(target, [original, target])("sqlite3.connect", (inputs[form],))
