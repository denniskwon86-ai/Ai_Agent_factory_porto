from __future__ import annotations

import sqlite3

import pytest

from core import planning_driver_release as release
from core.decision_ledger import DecisionLedger
from core.planning_model import PlanningError, PlanningStore


@pytest.fixture()
def stores(tmp_path):
    store = PlanningStore(str(tmp_path / "planning.db"))
    conn = store._connect()
    try:
        conn.executescript("""
        CREATE TABLE plan_drivers(driver_code TEXT PRIMARY KEY,name TEXT NOT NULL,unit TEXT,
          category TEXT,external_code TEXT,note TEXT,created_at TEXT);
        CREATE TABLE driver_impacts(impact_id TEXT PRIMARY KEY,driver_code TEXT,account_code TEXT,
          elasticity REAL,rationale TEXT,source TEXT,approved_by TEXT,approved_at TEXT,created_at TEXT);
        """)
        conn.execute("INSERT INTO plan_drivers VALUES(?,?,?,?,?,?,?)",
                     ("DRV-FX", "환율", "%", "fx", "USD-KRW", "원가 영향", "2026-01-01"))
        conn.execute("INSERT INTO driver_impacts VALUES(?,?,?,?,?,?,?,?,?)",
                     ("imp-1", "DRV-FX", "5000", .6, "수입 원료 비중", "재무 검토",
                      "", "", "2026-01-01"))
        conn.commit()
    finally:
        conn.close()
    return store, DecisionLedger(str(tmp_path / "ledger.db"))


def _approve(store, ledger):
    return release.approve(
        "DRV-FX", "reviewer@test.invalid", "동인·파급 검토", tenant_id="tenant-a",
        scope_node_id="node-a", entity_mode="REAL", store=store, ledger=ledger)


def test_draft_is_unbound_until_immutable_ledger_approval(stores):
    store, ledger = stores
    assert release.effective_release("DRV-FX", store=store, ledger=ledger) is None
    approved = _approve(store, ledger)
    got = release.effective_release("DRV-FX", store=store, ledger=ledger)
    assert got and got["fingerprint"] == approved["fingerprint"]
    event = ledger.get_event_strict(got["approval_event_id"])
    assert (event["event_type"], event["subject_type"], event["subject_id"]) == (
        release.EVENT_APPROVED, release.SUBJECT_TYPE, got["fingerprint"])


def test_same_material_is_idempotent_but_changed_impact_requires_revoke(stores):
    store, ledger = stores
    first = _approve(store, ledger)
    same = _approve(store, ledger)
    assert same["idempotent"] is True and same["fingerprint"] == first["fingerprint"]
    conn = store._connect()
    try:
        conn.execute("UPDATE driver_impacts SET elasticity=.7 WHERE impact_id='imp-1'")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="먼저 철회"):
        _approve(store, ledger)


def test_empty_impacts_or_scope_never_approves(stores):
    store, ledger = stores
    conn = store._connect()
    try:
        conn.execute("DELETE FROM driver_impacts")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="파급계수가 없는"):
        _approve(store, ledger)
    with pytest.raises(PlanningError, match="조직 범위"):
        release.approve("DRV-FX", "reviewer@test.invalid", "검토", tenant_id="tenant-a",
                        scope_node_id="", entity_mode="REAL", store=store, ledger=ledger)


def test_revoke_kills_current_release_and_keeps_ledger_history(stores):
    store, ledger = stores
    approved = _approve(store, ledger)
    revoked = release.revoke("DRV-FX", "reviewer@test.invalid", "모형 재검토",
                             store=store, ledger=ledger)
    assert revoked["status"] == release.REVOKED
    assert release.effective_release("DRV-FX", store=store, ledger=ledger) is None
    assert {row["event_type"] for row in ledger.list_events(subject_id=approved["fingerprint"])} == {
        release.EVENT_APPROVED, release.EVENT_REVOKED}


def test_release_body_and_ledger_binding_cannot_be_tampered(stores):
    store, ledger = stores
    _approve(store, ledger)
    conn = store._connect()
    try:
        conn.execute("UPDATE driver_releases SET name='바뀐 동인' WHERE driver_code='DRV-FX'")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PlanningError, match="내용 지문"):
        release.effective_release("DRV-FX", store=store, ledger=ledger)


def test_product_routes_are_mounted():
    import main
    paths = {route.path for route in main.app.routes}
    assert "/api/v1/planning/drivers/{driver_code}/approve" in paths
    assert "/api/v1/planning/drivers/{driver_code}/revoke" in paths
