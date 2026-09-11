"""일괄 RAW 적재의 모집단·범위·불변식 시험. DB는 열지 않는다."""
import copy
from collections import Counter

import pytest

from core.data_preparation.kit_logistics_revision import fingerprint
from scripts.stage_kit_logistics_batch import COUNTS, KEYS, grouped_batch, verify_additions, verify_initialization


@pytest.fixture
def prepared():
    rows = {k: [{KEYS[k]: f"{k}-{i}", "tenant_id": "T", "scope_node_id": "P1" if i % 2 else "P2",
        "data_class": "SYNTHETIC", "data_origin": "SYNTHETIC", "quality_status": "PENDING_VALIDATION",
        "certification_status": "UNVERIFIED_CANDIDATE"} for i in range(n)] for k, n in COUNTS.items()}
    plan = {"next_single_batch": [{"dataset": k, "rows": len(v), "row_fingerprint": fingerprint(v),
        "scope_counts": dict(Counter(r["scope_node_id"] for r in v))} for k, v in rows.items()]}
    return rows, plan


def test_all_twelve_groups_roundtrip_without_mutation(prepared):
    rows, plan = prepared
    before = copy.deepcopy(rows)
    groups = grouped_batch(rows, plan, "T", {"P1", "P2"})
    assert len(groups) == 12
    assert sum(len(v) for v in groups.values()) == 13900
    assert rows == before
    assert {k: sum(len(v) for (d, _), v in groups.items() if d == k) for k in rows} == COUNTS


@pytest.mark.parametrize("field,value", [("tenant_id", "other"), ("scope_node_id", "P3"),
    ("data_class", "ACTUAL"), ("data_origin", "ACTUAL"), ("quality_status", "PASS"),
    ("certification_status", "CERTIFIED_FOR_DEMO")])
def test_unapproved_state_or_context_fails(prepared, field, value):
    rows, plan = prepared
    rows["PRC-01"][0][field] = value
    with pytest.raises(ValueError):
        grouped_batch(rows, plan, "T", {"P1", "P2"})


@pytest.mark.parametrize("problem", ["missing_row", "duplicate_id", "extra_finance", "changed_plan_hash", "changed_scope_count", "duplicate_plan_dataset", "wrong_factory_count"])
def test_changed_batch_cannot_be_staged(prepared, problem):
    rows, plan = prepared
    scopes = {"P1", "P2"}
    if problem == "missing_row":
        rows["LOG-02"].pop()
    elif problem == "duplicate_id":
        rows["PRC-01"][1]["contract_id"] = rows["PRC-01"][0]["contract_id"]
    elif problem == "extra_finance":
        rows["FIN-02"] = [rows["PRC-01"][0]]
    elif problem == "changed_plan_hash":
        plan["next_single_batch"][0]["row_fingerprint"] = "wrong"
    elif problem == "changed_scope_count":
        plan["next_single_batch"][0]["scope_counts"] = {"P1": 100}
    elif problem == "duplicate_plan_dataset":
        plan["next_single_batch"].append(plan["next_single_batch"][0])
    else:
        scopes.add("P3")
    with pytest.raises(ValueError):
        grouped_batch(rows, plan, "T", scopes)


def example_tables():
    return {"kit_instances": [("instance",)], "source_bindings": [("old-binding",)],
        "dataset_snapshots": [("old-snapshot",)], "ownership": [("old-owner",)]}


def test_only_append_in_the_two_allowed_tables():
    before = example_tables()
    after = copy.deepcopy(before)
    after["source_bindings"].append(("new-binding",))
    after["dataset_snapshots"].append(("new-snapshot",))
    verify_additions(before, after, {"source_bindings": 1, "dataset_snapshots": 1})


@pytest.mark.parametrize("problem", ["modified_old_snapshot", "new_instance", "new_owner", "new_table", "missing_old_duplicate"])
def test_preserved_tables_are_not_silently_rewritten(problem):
    before = example_tables()
    after = copy.deepcopy(before)
    if problem == "modified_old_snapshot":
        after["dataset_snapshots"][0] = ("rewritten",)
    elif problem == "new_instance":
        after["kit_instances"].append(("new",))
    elif problem == "new_owner":
        after["ownership"].append(("new",))
    elif problem == "new_table":
        after["new"] = []
    else:
        before["ownership"] = [("same",), ("same",)]
        after["ownership"] = [("same",), ("different",)]
    with pytest.raises(ValueError):
        verify_additions(before, after, {})


def schema_example():
    old = {"dataset_snapshots": [(0, "snapshot_id", "TEXT", 0, None, 1), (1, "certified_at", "TEXT", 1, "''", 0)],
        "ownership": [(0, "owner", "TEXT", 0, None, 1)]}
    new = copy.deepcopy(old)
    new["dataset_snapshots"].append((2, "certified_by", "TEXT", 1, "''", 0))
    before = {"dataset_snapshots": [("old", "prior-time"), ("raw", "")], "ownership": [("owner",)]}
    after = {"dataset_snapshots": [("old", "prior-time", ""), ("raw", "", "")], "ownership": [("owner",)]}
    return before, after, old, new


def test_additive_empty_author_column_preserves_every_original_value():
    before, after, old, new = schema_example()
    report = verify_initialization(before, after, old, new)
    assert report["old_columns_and_values_preserved"]
    assert not report["approval_values_added"]
    assert report["additive_schema_changes"][0]["preserved_rows"] == 2


def test_no_schema_change_also_requires_exact_old_rows():
    before, _, old, _ = schema_example()
    assert verify_initialization(before, copy.deepcopy(before), old, copy.deepcopy(old))["additive_schema_changes"] == []


@pytest.mark.parametrize("problem", ["nonempty_author", "changed_old_value", "unknown_column", "nullable_author", "different_default",
    "removed_column", "reordered_column", "modified_other_table", "new_table", "lost_duplicate", "changed_column_metadata", "existing_author_rewritten"])
def test_initialization_rejects_every_change_beyond_empty_author_addition(problem):
    before, after, old, new = schema_example()
    if problem == "nonempty_author":
        after["dataset_snapshots"][0] = ("old", "prior-time", "approved")
    elif problem == "changed_old_value":
        after["dataset_snapshots"][0] = ("old", "", "")
    elif problem in ("unknown_column", "nullable_author", "different_default"):
        new["dataset_snapshots"][-1] = {"unknown_column": (2, "other", "TEXT", 1, "''", 0),
            "nullable_author": (2, "certified_by", "TEXT", 0, "''", 0),
            "different_default": (2, "certified_by", "TEXT", 1, "'approved'", 0)}[problem]
    elif problem == "removed_column":
        new["dataset_snapshots"].pop(1)
    elif problem == "reordered_column":
        new["dataset_snapshots"].reverse()
    elif problem == "modified_other_table":
        after["ownership"] = [("different",)]
    elif problem == "new_table":
        after["new"] = []
        new["new"] = []
    elif problem == "lost_duplicate":
        before["ownership"] = [("same",), ("same",)]
        after["ownership"] = [("same",), ("different",)]
    elif problem == "changed_column_metadata":
        new["dataset_snapshots"][0] = (0, "snapshot_id", "INTEGER", 0, None, 1)
    else:
        old = copy.deepcopy(new)
        before["dataset_snapshots"] = [("old", "prior-time", "original-author"), ("raw", "", "")]
    with pytest.raises(ValueError):
        verify_initialization(before, after, old, new)
