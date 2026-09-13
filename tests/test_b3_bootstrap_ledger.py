"""B3 고정 event ID 원장 어댑터 독립 회귀 — 작성만, 병렬 담당 실행 금지.

main의 audit + --noconftest 격리 런너에서만 실행한다. 제품 모듈은 fixture 안에서
import한다. 모든 ledger 연결은 새 tmp_path 절대 경로를 강제하며 식별자/URL은
synthetic .invalid 값이다. 운영 원장/AdvisorStore/API/starter asset에 접근하지 않는다.
변조/장애 주입 SQL 역시 여기서 생성한 임시 원장에만 적용한다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace

import pytest


EVENT_ID = "dle-b3-bootstrap.test.invalid"
PROJECT_ID = "prj-b3-bootstrap.test.invalid"
PAYLOAD = {
    "event_type": "PROJECT_BOOTSTRAPPED", "subject_type": "project",
    "subject_id": PROJECT_ID, "project_id": PROJECT_ID,
    "tenant_id": "tenant.test.invalid", "enterprise_scope_id": "scope.test.invalid",
    "entity_mode": "REAL", "blueprint_id": "avr.test.invalid",
    "actor_type": "user", "actor_id": "author@test.invalid", "decision": "BOOTSTRAPPED",
    "rationale": "승인 판본의 프로젝트 read-back을 확인함",
    "evidence_refs": [{"uri": "https://evidence.test.invalid/readback", "digest": "a" * 64}],
    "input_version_refs": [{"approved_revision_id": "avr.test.invalid", "digest": "b" * 64,
                            "context_key": {"tenant_id": "tenant.test.invalid",
                                            "context_root_id": "root.test.invalid",
                                            "entity_mode": "REAL", "scope_node_id": "scope.test.invalid"}}],
    "output_version_refs": [{"project_id": PROJECT_ID, "operation_id": "bop.test.invalid"}],
    "parent_event_id": "",
}


@pytest.fixture
def env(tmp_path):
    from core.advisor_bootstrap_ledger import BootstrapLedgerError, append_bootstrap_once
    from core.decision_ledger import DecisionLedger, _compute_hash

    root = tmp_path.resolve()

    class TempLedger(DecisionLedger):
        def __init__(self, path):
            assert Path(path).resolve().is_relative_to(root)
            super().__init__(str(Path(path).resolve()))
            self.connections = []
            self.trace = []

        def _connect(self):
            assert Path(self.db_path).resolve().is_relative_to(root)
            conn = super()._connect()
            self.connections.append(conn)
            conn.set_trace_callback(lambda sql: self.trace.append((conn, sql)))
            return conn

    ledger = TempLedger(root / "ledger.test.invalid.db")
    return SimpleNamespace(ledger=ledger, make=TempLedger, root=root,
                           append=append_bootstrap_once, error=BootstrapLedgerError,
                           compute_hash=_compute_hash)


def _append(env, event_id=EVENT_ID, **changes):
    return env.append(env.ledger, event_id, **{**copy.deepcopy(PAYLOAD), **changes})


@contextmanager
def _db(env):
    env.ledger._ready()
    conn = env.ledger._connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _rows(env):
    with _db(env) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM decision_ledger_events ORDER BY seq")]


def _assert_closed(ledger):
    for conn in ledger.connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def _error(env, call, code, status=409):
    with pytest.raises(env.error) as failure:
        call()
    assert failure.value.reason_code == code
    assert failure.value.status_code == status


def _race(env, first, second):
    other = env.make(env.ledger.db_path)
    # schema 준비 경합과 append 경합을 분리한다. 두 객체의 lock은 서로 다르다.
    env.ledger._ready()
    other._ready()
    barrier = threading.Barrier(2)

    def invoke(ledger, changes):
        barrier.wait(timeout=5)
        try:
            return env.append(ledger, EVENT_ID, **{**copy.deepcopy(PAYLOAD), **changes})
        except env.error as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke, env.ledger, first), pool.submit(invoke, other, second)]
        results = [future.result(timeout=10) for future in futures]
    _assert_closed(env.ledger)
    _assert_closed(other)
    return results


def test_fixed_event_id_returns_actual_committed_public_row(env):
    event = _append(env)
    raw = _rows(env)
    assert len(raw) == 1 and raw[0]["event_id"] == EVENT_ID
    assert event == env.ledger._to_public(raw[0])
    assert event["seq"] == 1 and event["prev_hash"] == ""
    assert event["event_hash"] == env.compute_hash(raw[0], "")
    assert event["evidence_refs"] == PAYLOAD["evidence_refs"]
    assert event["is_substantiated"] is True
    _assert_closed(env.ledger)


def test_replay_ignores_new_build_timestamp_and_keeps_original_row(env, monkeypatch):
    monkeypatch.setattr(env.ledger, "_now", lambda: "2030-01-01T00:00:00+00:00")
    first = _append(env)
    monkeypatch.setattr(env.ledger, "_now", lambda: "2031-01-01T00:00:00+00:00")
    assert _append(env) == first
    assert len(_rows(env)) == 1
    _assert_closed(env.ledger)


def test_same_payload_different_event_ids_append_two_events(env):
    first = _append(env)
    second = _append(env, "dle-second.test.invalid")
    assert second["event_id"] != first["event_id"]
    assert second["seq"] == 2 and second["prev_hash"] == first["event_hash"]
    assert len(_rows(env)) == 2
    assert _append(env) == first


def test_independent_ledger_instances_replay_after_restart(env):
    first = _append(env)
    another = env.make(env.ledger.db_path)
    assert env.append(another, EVENT_ID, **copy.deepcopy(PAYLOAD)) == first
    assert len(_rows(env)) == 1
    _assert_closed(another)


@pytest.mark.parametrize("changes", [
    {"tenant_id": "other-tenant.test.invalid"},
    {"enterprise_scope_id": "other-scope.test.invalid"},
    {"entity_mode": "VIRTUAL"},
    {"project_id": "other-project.test.invalid", "subject_id": "other-project.test.invalid"},
    {"blueprint_id": "other-blueprint.test.invalid"},
    {"actor_id": "other@test.invalid"}, {"actor_type": "system"},
    {"decision": "DIFFERENT"}, {"rationale": "다른 근거"},
    {"evidence_refs": []}, {"input_version_refs": []}, {"output_version_refs": []},
    {"parent_event_id": "other-event.test.invalid"},
])
def test_same_id_changed_request_field_is_conflict_without_append(env, changes):
    first = _append(env)
    _error(env, lambda: _append(env, **changes), "ADVISOR_LEDGER_IDEMPOTENCY_CONFLICT")
    assert len(_rows(env)) == 1 and _append(env) == first
    _assert_closed(env.ledger)


def test_nested_exact_boundary_change_is_conflict(env):
    _append(env)
    refs = copy.deepcopy(PAYLOAD["input_version_refs"])
    refs[0]["context_key"]["context_root_id"] = "other-root.test.invalid"
    _error(env, lambda: _append(env, input_version_refs=refs), "ADVISOR_LEDGER_IDEMPOTENCY_CONFLICT")
    assert len(_rows(env)) == 1


def test_dict_key_order_is_canonical_but_list_order_is_request_material(env):
    refs = [{"z": 1, "a": 2}, {"other": 3}]
    first = _append(env, evidence_refs=refs)
    assert _append(env, evidence_refs=[{"a": 2, "z": 1}, {"other": 3}]) == first
    _error(env, lambda: _append(env, evidence_refs=list(reversed(refs))), "ADVISOR_LEDGER_IDEMPOTENCY_CONFLICT")


def test_closed_event_subject_types_and_row_metadata_are_rejected_without_io(env):
    for changes in ({"event_type": "BLUEPRINT_APPROVED"}, {"subject_type": "blueprint"},
                    {"project_id": ""}, {"subject_id": "other.test.invalid"},
                    {"actor_type": "unregistered"}, {"seq": 1}, {"created_at": "forged"},
                    {"prev_hash": ""}, {"event_hash": "forged"}, {"context_key": {}},
                    {"evidence_refs": {"not": "a list"}}, {"actor_id": 1},
                    {"evidence_refs": [float("nan")]}, {"evidence_refs": [float("inf")]}):
        _error(env, lambda: _append(env, **changes), "ADVISOR_LEDGER_INPUT_INVALID", 422)
    for key in ("event_type", "subject_type", "subject_id", "project_id"):
        body = copy.deepcopy(PAYLOAD)
        body.pop(key)
        _error(env, lambda: env.append(env.ledger, EVENT_ID, **body), "ADVISOR_LEDGER_INPUT_INVALID", 422)
    assert env.ledger.connections == []
    assert not Path(env.ledger.db_path).exists()


@pytest.mark.parametrize("event_id", ["", "  ", " leading", "trailing ", "bad\nkey", 42, None, "x" * 257])
def test_invalid_fixed_id_does_not_open_any_database(env, event_id):
    _error(env, lambda: _append(env, event_id), "ADVISOR_LEDGER_INPUT_INVALID", 422)
    assert env.ledger.connections == []


def test_build_insert_public_reuse_one_begin_immediate_connection(env, monkeypatch):
    calls = []
    build, insert, public = env.ledger._build_row, env.ledger._insert, env.ledger._to_public

    def tracked_build(**payload):
        calls.append("build")
        return build(**payload)

    def tracked_insert(conn, row):
        assert conn.in_transaction
        assert row["event_id"] == EVENT_ID
        trace = [sql for seen, sql in env.ledger.trace if seen is conn]
        assert trace[0] == "BEGIN IMMEDIATE"
        assert any("WHERE event_id=" in sql for sql in trace)
        assert any("ORDER BY seq" in sql for sql in trace)
        calls.append("insert")
        return insert(conn, row)

    def tracked_public(row):
        calls.append("public")
        return public(row)

    monkeypatch.setattr(env.ledger, "_build_row", tracked_build)
    monkeypatch.setattr(env.ledger, "_insert", tracked_insert)
    monkeypatch.setattr(env.ledger, "_to_public", tracked_public)
    first = _append(env)
    assert _append(env) == first
    assert calls == ["build", "insert", "public", "build", "public"]
    _assert_closed(env.ledger)


def test_independent_connections_same_id_same_request_get_one_event(env):
    results = _race(env, {}, {})
    assert isinstance(results[0], dict) and results[0] == results[1]
    assert len(_rows(env)) == 1


def test_independent_connections_same_id_different_request_cannot_overwrite(env):
    results = _race(env, {}, {"rationale": "다른 요청"})
    assert sum(isinstance(result, dict) for result in results) == 1
    failure = next(result for result in results if isinstance(result, env.error))
    assert failure.reason_code == "ADVISOR_LEDGER_IDEMPOTENCY_CONFLICT"
    assert failure.status_code == 409 and len(_rows(env)) == 1


def test_insert_failure_rolls_back_then_same_fixed_id_can_retry(env, monkeypatch):
    original = env.ledger._insert

    def insert_then_fail(conn, row):
        original(conn, row)
        raise sqlite3.OperationalError("synthetic failure after INSERT")

    monkeypatch.setattr(env.ledger, "_insert", insert_then_fail)
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_UNAVAILABLE", 503)
    assert _rows(env) == []
    _assert_closed(env.ledger)
    monkeypatch.setattr(env.ledger, "_insert", original)
    assert _append(env)["event_id"] == EVENT_ID and len(_rows(env)) == 1


def test_public_conversion_failure_rolls_back_and_closes(env, monkeypatch):
    def fail(_row):
        raise RuntimeError("synthetic conversion failure")

    monkeypatch.setattr(env.ledger, "_to_public", fail)
    with pytest.raises(RuntimeError, match="synthetic conversion"):
        _append(env)
    assert _rows(env) == []
    _assert_closed(env.ledger)


@pytest.mark.parametrize("committed", [False, True])
def test_commit_failure_never_acknowledges_and_fixed_id_retry_recovers(env, monkeypatch, committed):
    env.ledger._ready()
    connect = env.ledger._connect

    class CommitFailure:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def commit(self):
            if committed:
                self.connection.commit()
            raise sqlite3.OperationalError("synthetic uncertain commit")

    monkeypatch.setattr(env.ledger, "_connect", lambda: CommitFailure(connect()))
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_UNAVAILABLE", 503)
    _assert_closed(env.ledger)
    monkeypatch.setattr(env.ledger, "_connect", connect)
    assert len(_rows(env)) == int(committed)
    actual = _append(env)
    assert actual["event_id"] == EVENT_ID and actual["seq"] == 1
    assert len(_rows(env)) == 1


def test_new_insert_readback_integrity_failure_rolls_back(env, monkeypatch):
    insert = env.ledger._insert

    def corrupt_after_insert(conn, row):
        insert(conn, row)
        conn.execute("UPDATE decision_ledger_events SET rationale='tampered' WHERE event_id=?", (EVENT_ID,))

    monkeypatch.setattr(env.ledger, "_insert", corrupt_after_insert)
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_INTEGRITY", 503)
    assert _rows(env) == []
    _assert_closed(env.ledger)


def test_missing_parent_is_not_acknowledged(env):
    _error(env, lambda: _append(env, parent_event_id="missing.test.invalid"), "ADVISOR_LEDGER_INPUT_INVALID", 422)
    assert _rows(env) == []
    _assert_closed(env.ledger)


def test_ledger_committed_but_saga_ack_lost_recovers_same_event(env):
    actual = _append(env)
    # main의 ack 장애는 ledger transaction 이후 별개다. DB op/파일을 여기서 만들지 않는다.
    with pytest.raises(RuntimeError, match="ack failed"):
        raise RuntimeError("ack failed")
    retry = _append(env)
    assert retry == actual and len(_rows(env)) == 1
    assert {"ledger_event_id": retry["event_id"], "ledger_acknowledged": True} == {
        "ledger_event_id": EVENT_ID, "ledger_acknowledged": True}


def test_existing_other_event_type_with_same_id_is_not_reused(env):
    env.ledger._ready()
    row = env.ledger._build_row(event_type="REQUIREMENT_CONFIRMED", subject_type="project",
                                 subject_id=PROJECT_ID, project_id=PROJECT_ID,
                                 actor_id="legacy@test.invalid")
    row["event_id"] = EVENT_ID
    with _db(env) as conn:
        conn.execute("BEGIN IMMEDIATE")
        env.ledger._insert(conn, row)
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_IDEMPOTENCY_CONFLICT")
    assert len(_rows(env)) == 1


@pytest.mark.parametrize("column,value", [("rationale", "tampered"), ("event_hash", "0" * 64),
                                          ("prev_hash", "1" * 64), ("created_at", "tampered")])
def test_corrupt_existing_row_never_receives_replay_ack(env, column, value):
    _append(env)
    with _db(env) as conn:
        conn.execute(f"UPDATE decision_ledger_events SET {column}=? WHERE event_id=?", (value, EVENT_ID))
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_INTEGRITY", 503)
    assert len(_rows(env)) == 1


def test_ancestor_tampering_blocks_replay_and_new_append(env):
    _append(env, "ancestor.test.invalid")
    _append(env)
    with _db(env) as conn:
        conn.execute("UPDATE decision_ledger_events SET rationale='tampered' WHERE seq=1")
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_INTEGRITY", 503)
    _error(env, lambda: _append(env, "third.test.invalid"), "ADVISOR_LEDGER_INTEGRITY", 503)
    assert len(_rows(env)) == 2


def test_valid_self_hash_with_wrong_previous_link_is_rejected(env):
    _append(env, "ancestor.test.invalid")
    _append(env)
    row = _rows(env)[1]
    row["prev_hash"] = "f" * 64
    # 임시 원장의 타깃 self hash만 재계산해도 read-chain prev 확인이 잡아야 한다.
    event_hash = env.compute_hash(row, row["prev_hash"])
    with _db(env) as conn:
        conn.execute("UPDATE decision_ledger_events SET prev_hash=?,event_hash=? WHERE event_id=?",
                     (row["prev_hash"], event_hash, EVENT_ID))
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_INTEGRITY", 503)


def test_sequence_gap_is_rejected_even_if_remaining_self_hash_is_recomputed(env):
    _append(env)
    row = _rows(env)[0]
    row["seq"] = 2
    with _db(env) as conn:
        conn.execute("UPDATE decision_ledger_events SET seq=2,event_hash=? WHERE event_id=?",
                     (env.compute_hash(row, ""), EVENT_ID))
    _error(env, lambda: _append(env), "ADVISOR_LEDGER_INTEGRITY", 503)


def test_schema_and_preexisting_rows_are_not_changed(env):
    _append(env, "prior.test.invalid")
    before_rows = _rows(env)
    with _db(env) as conn:
        schema = [tuple(row) for row in conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")]
    _append(env)
    _append(env)
    with _db(env) as conn:
        assert [tuple(row) for row in conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")] == schema
    assert _rows(env)[:1] == before_rows
    assert len(_rows(env)) == 2
