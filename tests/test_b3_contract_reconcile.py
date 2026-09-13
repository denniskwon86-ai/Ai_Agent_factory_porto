"""Host reconcile helper 단위 통합: 실제 새 임시 원장/계약 파일, main audit 전용.

현재 PDP/Factory API/실제 graph checkpoint/실행 guard는 검증하지 않는다(main 소유).
계약 compiler/validator/DecisionLedger는 실제이며 2.0 ProcessContext만 합성 DTO다.
제품 import는 격리 fixture 안에서만 한다. pytest를 여기서 실행하지 않는다.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace

import pytest

PROJECT = "P_RECONCILE"
TASK = "T_RECONCILE"
ACTOR = "reviewer@reconcile.test.invalid"
WHEN = "2030-01-02T03:04:05+00:00"
BOUNDARY = {"tenant_id": "tenant.test.invalid", "enterprise_scope_id": "scope.test.invalid", "entity_mode": "REAL"}


@contextmanager
def _db(env):
    conn = env.ledger._connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _rows(env):
    with _db(env) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM decision_ledger_events ORDER BY seq")]


def _request(env, fingerprint):
    return env.ledger.append(
        event_type="APP_CONTRACT_REVIEW_REQUESTED", subject_type="app_contract",
        subject_id=fingerprint, project_id=PROJECT, decision="검토 요청",
        evidence_refs=[{"compiled_fingerprint": fingerprint, "task_ids": [TASK]}], **BOUNDARY)


def _decision(env, parent, *, approved=True):
    return env.ledger.append(
        event_type="APP_CONTRACT_APPROVED" if approved else "APP_CONTRACT_REJECTED",
        subject_type="app_contract", subject_id=parent["subject_id"], project_id=PROJECT,
        actor_type="user", actor_id=ACTOR, decision="승인" if approved else "반려",
        rationale="synthetic helper review", parent_event_id=parent["event_id"],
        evidence_refs=[{"compiled_fingerprint": parent["subject_id"], "task_id": TASK}], **BOUNDARY)


def _seed(env, contract):
    parent = _request(env, contract["semantic_fingerprint"])
    event = _decision(env, parent)
    env.parent, env.event, env.contract = parent, event, contract
    env.args = dict(project_id=PROJECT, task_id=TASK, request_event_id=parent["event_id"],
                    event_id=event["event_id"], compiled_fingerprint=contract["semantic_fingerprint"], **BOUNDARY)
    _write(env, contract)


def _write(env, contract):
    assert env.path.resolve().is_relative_to(env.root)
    env.path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")


def _validate(env, **changes):
    return env.module.validate_approval(env.ledger, **{**env.args, **changes})


def _stamp(env, proof=None):
    return env.module.stamp_approval(env.workspace, event=_validate(env) if proof is None else proof,
                                    fingerprint=env.args["compiled_fingerprint"])


def _error(env, call, code, status=409):
    with pytest.raises(env.module.ReconcileError) as failed:
        call()
    assert failed.value.reason_code == code
    assert failed.value.status_code == status


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    from core import paths
    monkeypatch.setattr(paths, "DATA_DIR", str(root / "data"))
    monkeypatch.setattr(paths, "PROJECTS_DIR", str(root / "projects"))
    connect = sqlite3.connect

    def guarded_connect(database, *args, **kwargs):
        assert isinstance(database, (str, Path)) and not str(database).startswith("file:")
        assert Path(database).is_absolute() and Path(database).resolve().is_relative_to(root)
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    from core import studio_contract_reconcile as module, host_contract_compiler as compiler
    from core.decision_ledger import DecisionLedger, _compute_hash

    class TempLedger(DecisionLedger):
        def _connect(self):
            assert Path(self.db_path).resolve().is_relative_to(root)
            conn = super()._connect()
            self.connections.append(conn)
            conn.set_trace_callback(self.trace.append)
            return conn

    ledger = TempLedger(str(root / "ledger.test.invalid.db"))
    ledger.connections, ledger.trace = [], []
    monkeypatch.setattr(ledger, "_now", lambda: WHEN)
    workspace = root / "projects" / PROJECT
    (workspace / "contracts").mkdir(parents=True)
    result = SimpleNamespace(module=module, ledger=ledger, root=root, workspace=workspace,
                             path=workspace / "contracts" / "app_runtime_contract.json",
                             compute_hash=_compute_hash)

    def compile_contract(version="1.0", app_class="departmental"):
        context = None
        if version == "2.0":
            context = {
                "schema_version": 1, "configuration_id": "configuration.test.invalid",
                "profile_id": "profile.test.invalid", "process_ids": ["process.test.invalid"],
                "process_semantic_fingerprint": "a" * 64, "configuration_fingerprint": "b" * 64,
                "context_key": {"tenant_id": BOUNDARY["tenant_id"], "context_root_id": "root.test.invalid",
                                "entity_mode": BOUNDARY["entity_mode"], "scope_node_id": BOUNDARY["enterprise_scope_id"]},
                "data_requirements": [], "verified_binding_refs": [], "blockers": [],
                "permitted_actions": ["DRAFT"],
                "sources": [{"kind": "PROCESS_PROFILE", "configuration_id": "configuration.test.invalid",
                             "profile_id": "profile.test.invalid", "fingerprint": "b" * 64}],
            }
        compiled = compiler.compile_contract(
            {"app_class": app_class, "capability_intents": [], "datasets": []},
            project_id=PROJECT, task_id=TASK, document_version=version, process_context=context)
        assert compiled.ok, compiled.errors
        return compiled.contract

    result.compile = compile_contract
    _seed(result, compile_contract())
    return result


def test_validation_reads_existing_unique_approval_without_sql_writes_and_closes_connection(env):
    before = _rows(env)
    env.ledger.trace.clear()
    count = len(env.ledger.connections)
    proof = _validate(env)
    assert proof["event_id"] == env.event["event_id"] and proof.get("actor_id") == ACTOR
    assert proof["created_at"] == WHEN and proof["task_id"] == TASK
    assert not any(re.match(r"\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP)\b", s, re.I)
                   for s in env.ledger.trace)
    assert any(s == "BEGIN IMMEDIATE" for s in env.ledger.trace)
    for conn in env.ledger.connections[count:]:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
    assert _rows(env) == before
    with pytest.raises(TypeError):
        proof["actor_id"] = "forged@test.invalid"


@pytest.mark.parametrize("version", ["1.0", "2.0"])
def test_atomic_stamp_keeps_original_approval_identity_and_repeat_is_byte_noop(env, monkeypatch, version):
    if version == "2.0":
        _seed(env, env.compile(version))
    proof = _validate(env)
    before = _rows(env)
    first = _stamp(env, proof)
    assert first["stamp_applied"] is True and first["already_applied"] is False
    raw = env.path.read_bytes()
    contract = json.loads(raw)
    assert contract["schema_version"] == version and contract["status"] == "APPROVED"
    assert contract["approval"]["approved_by"] == ACTOR
    assert contract["approval"]["approved_at"] == WHEN
    assert contract["approval"]["decision_ledger_id"] == env.event["event_id"]
    for key, value in env.contract.items():
        if key not in {"status", "approval"}:
            assert contract[key] == value
    monkeypatch.setattr(env.module.os, "replace", lambda *_: pytest.fail("same approval must not rewrite"))
    second = _stamp(env, _validate(env))
    assert second["already_applied"] is True and second["contract_digest"] == first["contract_digest"]
    assert env.path.read_bytes() == raw and _rows(env) == before


def test_plain_http_event_dict_is_not_a_verified_approval(env):
    _error(env, lambda: _stamp(env, dict(_validate(env))), "RECONCILE_VERIFIED_EVENT_REQUIRED", 422)


@pytest.mark.parametrize("change", [
    {"tenant_id": "other.test.invalid"}, {"enterprise_scope_id": "other.test.invalid"}, {"entity_mode": "VIRTUAL"},
])
def test_other_exact_event_context_is_hidden_without_file_change(env, change):
    before = env.path.read_bytes()
    _error(env, lambda: _validate(env, **change), "RECONCILE_NOT_FOUND", 404)
    assert env.path.read_bytes() == before


@pytest.mark.parametrize("change", [
    {"event_id": ""}, {"enterprise_scope_id": ""}, {"compiled_fingerprint": "A" * 64}, {"entity_mode": "AUTO"},
])
def test_invalid_server_inputs_are_rejected(env, change):
    _error(env, lambda: _validate(env, **change), "RECONCILE_INPUT_INVALID", 422)


def test_missing_or_request_event_cannot_be_reapplied_as_approval(env):
    _error(env, lambda: _validate(env, event_id="missing.test.invalid"), "RECONCILE_NOT_FOUND", 404)
    _error(env, lambda: _validate(env, event_id=env.parent["event_id"]), "RECONCILE_APPROVAL_CONFLICT")


def test_another_task_or_fingerprint_cannot_consume_same_approval(env):
    _error(env, lambda: _validate(env, task_id="T_OTHER"), "RECONCILE_TASK_CONFLICT")
    _error(env, lambda: _validate(env, compiled_fingerprint="0" * 64), "RECONCILE_APPROVAL_CONFLICT")


@pytest.mark.parametrize("approved", [True, False])
def test_second_decision_invalidates_unique_approval_without_rewriting_ledger(env, approved):
    _decision(env, env.parent, approved=approved)
    before = _rows(env)
    _error(env, lambda: _validate(env), "RECONCILE_APPROVAL_CONFLICT")
    assert _rows(env) == before


def test_rejected_event_is_never_restored_as_approved(env):
    rejected = _decision(env, env.parent, approved=False)
    _error(env, lambda: _validate(env, event_id=rejected["event_id"]), "RECONCILE_APPROVAL_CONFLICT")


@pytest.mark.parametrize("fingerprint", ["same", "different"])
def test_later_review_blocks_old_approval_even_same_fingerprint(env, fingerprint):
    _request(env, env.args["compiled_fingerprint"] if fingerprint == "same" else "0" * 64)
    _error(env, lambda: _validate(env), "RECONCILE_REVIEW_SUPERSEDED")


def test_correction_of_approved_event_is_not_silently_ignored(env):
    env.ledger.append(event_type="CORRECTION", subject_type="app_contract",
                      subject_id=env.args["compiled_fingerprint"], project_id=PROJECT,
                      parent_event_id=env.event["event_id"], decision="정정", **BOUNDARY)
    _error(env, lambda: _validate(env), "RECONCILE_APPROVAL_CONFLICT")


def _rewrite_and_rehash(env, event_id, changes):
    assert set(changes) <= {"evidence_refs_json", "entity_mode", "parent_event_id"}
    with _db(env) as conn:
        assignments = ",".join(key + "=?" for key in changes)
        conn.execute("UPDATE decision_ledger_events SET " + assignments + " WHERE event_id=?",
                     (*changes.values(), event_id))
        previous = ""
        for stored in conn.execute("SELECT * FROM decision_ledger_events ORDER BY seq").fetchall():
            row = dict(stored)
            digest = env.compute_hash(row, previous)
            conn.execute("UPDATE decision_ledger_events SET prev_hash=?,event_hash=? WHERE event_id=?",
                         (previous, digest, row["event_id"]))
            previous = digest


def test_valid_hash_but_missing_task_proof_is_blocked(env):
    _rewrite_and_rehash(env, env.parent["event_id"], {"evidence_refs_json": "[]"})
    _error(env, lambda: _validate(env), "RECONCILE_TASK_CONFLICT")


@pytest.mark.parametrize("raw", ["{", "{}", '[{"task_id":"x","task_id":"y"}]'])
def test_valid_hash_but_broken_or_duplicate_key_evidence_is_integrity_failure(env, raw):
    _rewrite_and_rehash(env, env.event["event_id"], {"evidence_refs_json": raw})
    _error(env, lambda: _validate(env), "RECONCILE_LEDGER_INTEGRITY", 503)


def test_ancestor_hash_tampering_is_detected_and_connection_closed(env):
    with _db(env) as conn:
        conn.execute("UPDATE decision_ledger_events SET event_hash=? WHERE event_id=?",
                     ("0" * 64, env.parent["event_id"]))
    count = len(env.ledger.connections)
    _error(env, lambda: _validate(env), "RECONCILE_LEDGER_INTEGRITY", 503)
    for conn in env.ledger.connections[count:]:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


@pytest.mark.parametrize("field,value", [("project_id", "P_OTHER"), ("task_id", "T_OTHER"),
                                        ("semantic_fingerprint", "0" * 64)])
def test_contract_identity_or_current_fingerprint_changed_is_409_and_preserved(env, field, value):
    contract = copy.deepcopy(env.contract)
    contract[field] = value
    _write(env, contract)
    before = env.path.read_bytes()
    _error(env, lambda: _stamp(env), "RECONCILE_CONTRACT_CONFLICT")
    assert env.path.read_bytes() == before


def test_valid_new_contract_semantics_are_not_restored_with_old_approval(env):
    _write(env, env.compile(app_class="personal"))
    before = env.path.read_bytes()
    _error(env, lambda: _stamp(env), "RECONCILE_CONTRACT_CONFLICT")
    assert env.path.read_bytes() == before


def test_corrupt_contract_is_not_reconstructed_or_overwritten(env):
    env.path.write_bytes(b'{"project_id":')
    _error(env, lambda: _stamp(env), "RECONCILE_CONTRACT_INTEGRITY", 503)
    assert env.path.read_bytes() == b'{"project_id":'


def test_existing_different_approval_stamp_is_preserved(env):
    contract = copy.deepcopy(env.contract)
    contract["status"] = "APPROVED"
    contract["approval"] = {"status": "APPROVED", "approved_by": ACTOR, "approved_at": WHEN,
                            "decision_ledger_id": "different-event.test.invalid"}
    _write(env, contract)
    before = env.path.read_bytes()
    _error(env, lambda: _stamp(env), "RECONCILE_APPROVAL_CONFLICT")
    assert env.path.read_bytes() == before


def test_same_event_old_stamp_clock_is_fixed_once_to_original_event_time(env):
    contract = copy.deepcopy(env.contract)
    contract["status"] = "APPROVED"
    contract["approval"] = {"status": "APPROVED", "approved_by": ACTOR,
                            "approved_at": "2031-01-02T03:04:05+00:00",
                            "decision_ledger_id": env.event["event_id"]}
    _write(env, contract)
    assert _stamp(env)["already_applied"] is False
    assert json.loads(env.path.read_bytes())["approval"]["approved_at"] == WHEN
    assert _stamp(env)["already_applied"] is True


def test_raw_contract_cas_conflict_does_not_overwrite_concurrent_bytes(env, monkeypatch):
    read = env.module._read_regular
    calls = []
    concurrent = env.path.read_bytes() + b"\n"

    def race(path):
        calls.append(path)
        if len(calls) == 2:
            env.path.write_bytes(concurrent)
        return read(path)

    monkeypatch.setattr(env.module, "_read_regular", race)
    _error(env, lambda: _stamp(env), "RECONCILE_CONTRACT_CONFLICT")
    assert env.path.read_bytes() == concurrent
    assert not list(env.path.parent.glob(".host-reconcile-*.tmp"))


def test_atomic_replace_io_failure_preserves_contract_ledger_and_foreign_tmp(env, monkeypatch):
    before, rows = env.path.read_bytes(), _rows(env)
    sentinel = env.path.parent / ".host-reconcile-foreign.test.invalid.tmp"
    sentinel.write_bytes(b"must preserve")

    def fail(*_args):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(env.module.os, "replace", fail)
    _error(env, lambda: _stamp(env), "RECONCILE_CONTRACT_IO", 503)
    assert env.path.read_bytes() == before and _rows(env) == rows
    assert sentinel.read_bytes() == b"must preserve"
    assert list(env.path.parent.glob(".host-reconcile-*.tmp")) == [sentinel]


def test_post_replace_readback_failure_recovers_same_original_event_without_new_write(env, monkeypatch):
    read = env.module._read_regular
    calls = []

    def fail_ack(path):
        calls.append(path)
        if len(calls) == 3:
            raise OSError("synthetic lost stamp readback")
        return read(path)

    before = _rows(env)
    monkeypatch.setattr(env.module, "_read_regular", fail_ack)
    _error(env, lambda: _stamp(env), "RECONCILE_CONTRACT_IO", 503)
    saved = env.path.read_bytes()
    monkeypatch.setattr(env.module, "_read_regular", read)
    assert _stamp(env)["already_applied"] is True
    assert env.path.read_bytes() == saved and _rows(env) == before


def test_symlink_contract_is_preserved_and_never_stamped(env):
    import errno
    import os
    target = env.root / "linked-contract.test.invalid.json"
    env.path.rename(target)
    before = target.read_bytes()
    try:
        env.path.symlink_to(target)
    except OSError as exc:
        if ((os.name == "nt" and getattr(exc, "winerror", None) == 1314)
                or exc.errno in {errno.ENOSYS, errno.EOPNOTSUPP}):
            pytest.skip("actual symlink unavailable; main audit must report separately")
        raise
    _error(env, lambda: _stamp(env), "RECONCILE_CONTRACT_CONFLICT")
    assert env.path.is_symlink() and target.read_bytes() == before
