"""통합 계획의 의존순서·문맥·산정표 대조 시험."""
import copy

import pytest

from scripts.inspect_kit_integration_plan import dependency_layers, overlay, progress_audit, reviewed_context


def test_dependency_order_is_deterministic_and_shared_once():
    contracts = {"A": {"dependencies": []}, "B": {"dependencies": ["A"]},
        "C": {"dependencies": ["A"]}, "D": {"dependencies": ["C", "B"]}}
    assert dependency_layers(contracts, ["D", "C", "D"]) == [["A"], ["B", "C"], ["D"]]


@pytest.mark.parametrize("contracts", [{"A": {"dependencies": ["A"]}}, {"A": {"dependencies": ["B"]}}])
def test_missing_or_cyclic_dependency_is_not_ignored(contracts):
    with pytest.raises(ValueError):
        dependency_layers(contracts, ["A"])


def table(scores):
    return "## 6. 진척과 다음 작업\n" + "\n".join(f"| 영역{i} | {n}/4 |" for i, n in enumerate(scores)) + "\n## 7. 다음"


def test_historical_score_arithmetic_and_live_caveat():
    result = progress_audit(table([3, 2, 2, 1, 2, 2, 3, 1, 1, 1]))
    assert result["overall"] == {"score": 18, "total": 40}
    assert result["local"] == {"score": 15, "total": 28}
    assert not result["current_all_area_reassessment_performed"]


@pytest.mark.parametrize("scores", [[1]*9, [1]*11, [5]+[1]*9])
def test_invalid_progress_table_is_rejected(scores):
    with pytest.raises(ValueError):
        progress_audit(table(scores))


def test_overlay_is_exact_and_does_not_drop_other_rows():
    rows = [{"tenant_id": "A", "id": "1", "value": "old"}, {"tenant_id": "B", "id": "1", "value": "other"}]
    before = copy.deepcopy(rows)
    assert overlay(rows, [{**rows[0], "value": "new"}], "id") == [{**rows[0], "value": "new"}, rows[1]]
    assert rows == before


@pytest.mark.parametrize("problem", ["duplicate_patch", "duplicate_base", "missing_key"])
def test_bad_overlay_cannot_expand_scope(problem):
    rows = [{"tenant_id": "A", "id": "1"}]
    patch = [dict(rows[0])]
    if problem == "duplicate_patch":
        patch *= 2
    elif problem == "duplicate_base":
        rows *= 2
    else:
        patch[0]["tenant_id"] = "B"
    with pytest.raises(ValueError):
        overlay(rows, patch, "id")


def example_row():
    return {"tenant_id": "source", "scope_node_id": "plant1", "data_origin": "SYNTHETIC",
        "certification_status": "UNVERIFIED_CANDIDATE", "id": "A", "value": "123"}


def test_only_explicit_context_changes_in_memory():
    row = example_row()
    before = dict(row)
    result = reviewed_context([row], {"plant1": "target-plant"}, "source", "target")[0]
    assert row == before
    assert {k for k in row if row[k] != result[k]} == {"tenant_id", "scope_node_id"}


@pytest.mark.parametrize("field,value", [("tenant_id", "other"), ("scope_node_id", "unknown"),
    ("data_origin", "ACTUAL"), ("certification_status", "CERTIFIED_FOR_DEMO")])
def test_unreviewed_context_or_certification_is_rejected(field, value):
    row = example_row()
    row[field] = value
    with pytest.raises(ValueError):
        reviewed_context([row], {"plant1": "target-plant"}, "source", "target")
