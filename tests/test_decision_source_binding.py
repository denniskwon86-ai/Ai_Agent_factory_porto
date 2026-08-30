"""Decision Package 실행 선택은 표시명과 서버 결속을 분리한다."""
import json

import pytest

from core.decision_source_binding import (DecisionSourceBlocked,
                                          DecisionSourceCatalog,
                                          DecisionSourceNotFound)
from core.planning_model import PlanningStore


@pytest.fixture()
def catalog(tmp_path):
    store = PlanningStore(str(tmp_path / "planning.db"))
    conn = store._connect()
    try:
        conn.execute(
            "INSERT INTO scenarios(scenario_id,name,org_id,baseline_kind,created_at,"
            "owner_organization_id) VALUES(?,?,?,?,?,?)",
            ("scn_hidden", "구리 가격 상승 대응", "MNM", "PLAN", "2026-08-28", "scope-mnm"),
        )
        metrics = {
            "baseline_id": "bln_server_only",
            "org_id": "MNM",
            "period": "2027",
            "baseline_kind": "PLAN",
            "complete": True,
            "unapplied_assumptions": [],
            "driver_warnings": [],
        }
        conn.execute(
            "INSERT INTO simulation_runs(run_id,scenario_id,engine_version,input_hash,status,"
            "started_at,completed_at,metrics_json) VALUES(?,?,?,?,?,?,?,?)",
            ("sim_server_only", "scn_hidden", "1.0.0", "fingerprint", "completed",
             "2026-08-28T01:00:00Z", "2026-08-28T01:00:01Z", json.dumps(metrics)),
        )
        conn.commit()
    finally:
        conn.close()
    return DecisionSourceCatalog(store)


def test_list_uses_human_labels_without_rendering_internal_ids(catalog):
    rows = catalog.list_options({"scope-mnm"})
    assert len(rows) == 1
    assert rows[0]["label"] == "구리 가격 상승 대응 · 2027 · 계획 기준"
    assert "sim_server_only" not in rows[0]["label"]
    assert "bln_server_only" not in rows[0]["baseline_label"]
    assert rows[0]["bindable"] is True


def test_resolve_returns_the_server_binding_not_caller_fields(catalog):
    row = catalog.resolve("sim_server_only", {"scope-mnm"})
    assert row["scenario_id"] == "scn_hidden"
    assert row["baseline_id"] == "bln_server_only"
    assert row["scope_id"] == "scope-mnm"
    assert row["binding"]["input_hash"] == "fingerprint"


def test_out_of_scope_and_unknown_runs_are_indistinguishable(catalog):
    for run_id, scopes in (("sim_server_only", {"scope-other"}), ("missing", {"scope-mnm"})):
        with pytest.raises(DecisionSourceNotFound, match="찾을 수 없습니다"):
            catalog.resolve(run_id, scopes)


def test_legacy_run_without_sealed_metadata_is_visible_but_not_bindable(catalog):
    conn = catalog.store._connect()
    try:
        conn.execute(
            "INSERT INTO simulation_runs(run_id,scenario_id,engine_version,input_hash,status,"
            "started_at,completed_at,metrics_json) VALUES(?,?,?,?,?,?,?,?)",
            ("legacy", "scn_hidden", "1.0.0", "old", "completed",
             "2026-08-01", "2026-08-01", "{}"),
        )
        conn.commit()
    finally:
        conn.close()
    row = next(item for item in catalog.list_options({"scope-mnm"}) if item["run_id"] == "legacy")
    assert row["bindable"] is False
    assert "이전 실행" in row["blocked_reason"]
    with pytest.raises(DecisionSourceBlocked):
        catalog.resolve("legacy", {"scope-mnm"})


def test_incomplete_or_partially_applied_run_is_blocked(catalog):
    conn = catalog.store._connect()
    try:
        metrics = {
            "baseline_id": "bln_bad", "org_id": "MNM", "period": "2027",
            "baseline_kind": "PLAN", "complete": False,
            "unapplied_assumptions": ["매출 가정"], "driver_warnings": [],
        }
        conn.execute(
            "INSERT INTO simulation_runs(run_id,scenario_id,engine_version,input_hash,status,"
            "started_at,completed_at,metrics_json) VALUES(?,?,?,?,?,?,?,?)",
            ("incomplete", "scn_hidden", "1.0.0", "bad", "completed",
             "2026-08-28", "2026-08-28", json.dumps(metrics)),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(DecisionSourceBlocked, match="완전하지|적용되지"):
        catalog.resolve("incomplete", {"scope-mnm"})
