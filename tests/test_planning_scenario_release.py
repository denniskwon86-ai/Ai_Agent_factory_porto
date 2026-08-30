from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.decision_ledger import DecisionLedger
from core.planning_model import PlanningError, PlanningStore
from core import planning_scenario_release as release


@pytest.fixture()
def stores(tmp_path):
    return (
        PlanningStore(str(tmp_path / "planning.db")),
        DecisionLedger(str(tmp_path / "ledger.db")),
    )


def _seed(store: PlanningStore, *, scenario_id: str = "scn-source", scope: str = "node-a"):
    conn = store._connect()
    try:
        conn.execute(
            "INSERT INTO scenarios(scenario_id,name,org_id,baseline_kind,baseline_period,"
            "tenant_id,owner_organization_id,entity_mode,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (scenario_id, "원료비 상승", "dept-a", "PLAN", "2027", "tenant-a", scope,
             "REAL", "2026-08-28T00:00:00+00:00"))
        conn.execute(
            "INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,target_code,"
            "operator,value,unit,rationale,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (f"asm-{scenario_id}", scenario_id, "driver", "원료 단가", "pct", 12.5, "%",
             "공급사 갱신 제안", "2026-08-28T00:00:00+00:00"))
        conn.commit()
    finally:
        conn.close()


def test_draft_is_not_effective_until_human_approval(stores):
    store, ledger = stores
    _seed(store)
    assert release.effective_release("scn-source", store=store, ledger=ledger) is None

    approved = release.approve(
        "scn-source", "reviewer@test.invalid", "가정과 근거 검토 완료",
        store=store, ledger=ledger)
    assert approved["status"] == release.APPROVED
    got = release.effective_release("scn-source", store=store, ledger=ledger)
    assert got and got["fingerprint"] == approved["fingerprint"]
    event = ledger.get_event_strict(got["approval_event_id"])
    assert event["event_type"] == release.EVENT_APPROVED
    assert event["subject_type"] == release.SUBJECT_TYPE
    assert event["subject_id"] == got["fingerprint"]


def test_same_content_is_idempotent_but_changed_draft_needs_explicit_revoke(stores):
    store, ledger = stores
    _seed(store)
    first = release.approve("scn-source", "reviewer@test.invalid", "검토", store=store,
                            ledger=ledger)
    same = release.approve("scn-source", "reviewer@test.invalid", "재시도", store=store,
                           ledger=ledger)
    assert same["idempotent"] is True and same["fingerprint"] == first["fingerprint"]
    assert len(ledger.list_events(event_type=release.EVENT_APPROVED)) == 1

    conn = store._connect()
    try:
        conn.execute("UPDATE scenario_assumptions SET value=20 WHERE scenario_id='scn-source'")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="먼저 기존 판본을 철회"):
        release.approve("scn-source", "reviewer@test.invalid", "변경 승인", store=store,
                        ledger=ledger)


def test_missing_scope_and_empty_assumptions_never_become_approved(stores):
    store, ledger = stores
    _seed(store, scenario_id="no-scope", scope="")
    with pytest.raises(PlanningError, match="조직 범위"):
        release.approve("no-scope", "reviewer@test.invalid", "검토", store=store,
                        ledger=ledger)
    _seed(store, scenario_id="empty")
    conn = store._connect()
    try:
        conn.execute("DELETE FROM scenario_assumptions WHERE scenario_id='empty'")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="가정이 없는"):
        release.approve("empty", "reviewer@test.invalid", "검토", store=store,
                        ledger=ledger)
    assert ledger.list_events(event_type=release.EVENT_APPROVED) == []


def test_revocation_kills_current_release_and_keeps_history(stores):
    store, ledger = stores
    _seed(store)
    approved = release.approve("scn-source", "reviewer@test.invalid", "검토", store=store,
                               ledger=ledger)
    historical = (datetime.fromisoformat(approved["approved_at"]) + timedelta(microseconds=1))
    revoked = release.revoke("scn-source", "reviewer@test.invalid", "가정 재검토",
                             store=store, ledger=ledger)
    assert revoked["status"] == release.REVOKED
    assert release.effective_release("scn-source", store=store, ledger=ledger) is None
    old = release.effective_release(
        "scn-source", historical.astimezone(timezone.utc).isoformat(), store=store, ledger=ledger)
    assert old and old["fingerprint"] == approved["fingerprint"]
    events = ledger.list_events(subject_id=approved["fingerprint"])
    assert {row["event_type"] for row in events} == {
        release.EVENT_APPROVED, release.EVENT_REVOKED}


def test_approval_subject_mismatch_and_ledger_failure_are_fail_closed(stores):
    store, ledger = stores
    _seed(store)
    approved = release.approve("scn-source", "reviewer@test.invalid", "검토", store=store,
                               ledger=ledger)
    conn = sqlite3.connect(ledger.db_path)
    try:
        conn.execute("UPDATE decision_ledger_events SET subject_id='other' WHERE event_id=?",
                     (ledger.list_events(event_type=release.EVENT_APPROVED)[0]["event_id"],))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="대상이 일치하지"):
        release.effective_release("scn-source", store=store, ledger=ledger)

    # A missing/corrupt ledger is not the same as "not approved".
    bad_ledger = Path(str(store.db_path) + ".bad-ledger")
    bad_ledger.write_bytes(b"not a sqlite database")
    ledger.db_path = str(bad_ledger)
    ledger._prepared_for = None
    with pytest.raises(PlanningError, match="승인 원장을 확인하지"):
        release.effective_release("scn-source", store=store, ledger=ledger)


def test_release_body_and_approval_actor_cannot_change_behind_the_fingerprint(stores):
    store, ledger = stores
    _seed(store)
    release.approve("scn-source", "reviewer@test.invalid", "검토", store=store, ledger=ledger)
    conn = store._connect()
    try:
        conn.execute("UPDATE scenario_releases SET name='바뀐 이름' WHERE scenario_id='scn-source'")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="내용 지문"):
        release.effective_release("scn-source", store=store, ledger=ledger)

    conn = store._connect()
    try:
        row = conn.execute("SELECT * FROM scenario_releases WHERE scenario_id='scn-source'").fetchone()
        material = dict(row)
        assumptions = __import__("json").loads(material["assumptions_json"])
        material["name"] = "원료비 상승"
        material["owner_organization_id"] = material["scope_node_id"]
        material["assumptions"] = assumptions
        restored = release.fingerprint(material)
        conn.execute(
            "UPDATE scenario_releases SET name=?,fingerprint=?,approved_by=? "
            "WHERE scenario_id='scn-source'",
            ("원료비 상승", restored, "other@test.invalid"))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="승인 결속값"):
        release.effective_release("scn-source", store=store, ledger=ledger)


def test_product_router_exposes_human_approval_and_revocation_paths():
    import main
    paths = {route.path for route in main.app.routes}
    assert "/api/v1/planning/scenarios/{scenario_id}/approve" in paths
    assert "/api/v1/planning/scenarios/{scenario_id}/revoke" in paths
