"""B3 저장 기반 독립 회귀. main의 audit/--noconftest 런너에서만 실행한다.

이 파일은 작성만 되었으며 병렬 담당자는 실행하지 않는다. 수집 시 제품 저장소를
import/생성하지 않는다. AdvisorStore와 동일한 _connect/_lock 인터페이스의 연결
대역만 사용하여 모든 SQLite/고장 주입을 tmp_path 아래에 제한한다.
실제 AdvisorStore/API/PDP/ECM/파일/원장 연결 검증은 main 통합 시험 범위다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import sqlite3
import threading
from types import SimpleNamespace
from pathlib import Path

import pytest

from core.advisor_revision_store import RevisionStore, RevisionStoreError


AUTHOR = "author@test.invalid"
REVIEWER = "reviewer@test.invalid"
OTHER = "other@test.invalid"
CONTEXT = {"tenant_id": "tenant-test", "context_root_id": "root-test",
           "entity_mode": "REAL", "scope_node_id": "dept-test"}
SEMANTIC = "a" * 64
BLUEPRINT = {"title": "구매계획", "business": {"objective": "요구사항을 검토한다"},
             "data_requirements": [{"key": "purchase", "readiness_status": "missing"}]}
PROCESS = {"schema_version": 1, "state": "APPROVED", "configuration_id": "cfg-test",
           "profile_id": "profile-test", "process_ids": ["process-purchase"],
           "context_key": CONTEXT, "process_semantic_fingerprint": SEMANTIC,
           "configuration_fingerprint": "b" * 64}


class _Connection(sqlite3.Connection):
    def execute(self, sql, parameters=()):
        if self.adapter.fault and self.adapter.fault in sql:
            raise sqlite3.OperationalError("주입한 저장 실패")
        return super().execute(sql, parameters)


class _AdvisorConnection:
    """실제 AdvisorStore._connect의 연결/PRAGMA/Lock 계약만 재현한다."""
    def __init__(self, path, root):
        self.root = Path(root).resolve()
        self.db_path = str(Path(path).resolve())
        assert Path(self.db_path).is_relative_to(self.root)
        self._lock = threading.Lock()
        self.fault = ""
        self.connections = []

    def _connect(self):
        assert Path(self.db_path).resolve().is_relative_to(self.root)
        conn = sqlite3.connect(self.db_path, timeout=5, factory=_Connection)
        conn.adapter = self
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            # 실제 AdvisorStore도 PRAGMA 재설정 경합은 연결 실패로 삼지 않는다.
            pass
        self.connections.append(conn)
        return conn


@contextmanager
def _db(env):
    conn = env.adapter._connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


@pytest.fixture
def env(tmp_path):
    adapter = _AdvisorConnection(tmp_path / "advisor.db", tmp_path)
    out = SimpleNamespace(adapter=adapter, root=tmp_path, service=RevisionStore(adapter))
    # 가짜 레거시 행은 fixture의 tmp DB에만 작성한다. 제품 레거시 저장소는 import하지 않는다.
    with _db(out) as conn:
        conn.execute("CREATE TABLE consultations(id TEXT PRIMARY KEY,payload TEXT)")
        conn.execute("CREATE TABLE solution_blueprints(id TEXT PRIMARY KEY,payload TEXT)")
        conn.execute("INSERT INTO consultations VALUES('old-cons','unchanged-consultation')")
        conn.execute("INSERT INTO solution_blueprints VALUES('old-bp','unchanged-approved-blueprint')")
    return out


def _save(env, previous=None, **changes):
    args = {"boundary": copy.deepcopy(CONTEXT), "actor": AUTHOR,
            "draft_id": previous["draft_id"] if previous else "",
            "expected_revision": previous["revision"] if previous else 0,
            "expected_digest": previous["digest"] if previous else "",
            "blueprint": copy.deepcopy(BLUEPRINT), "process_ref": copy.deepcopy(PROCESS),
            "client_request_id": f"save-{previous['revision'] + 1}" if previous else "save-1"}
    return env.service.save(**{**args, **changes})


def _decide(env, draft, **changes):
    args = {"boundary": CONTEXT, "actor": REVIEWER, "draft_id": draft["draft_id"],
            "expected_revision": draft["revision"], "draft_digest": draft["digest"],
            "decision": "APPROVED", "reason": "요구사항 및 미확보 데이터를 확인함"}
    return env.service.decide(**{**args, **changes})


def _reserve(env, approved, **changes):
    args = {"approved_revision_id": approved["revision_id"], "digest": approved["digest"],
            "context_key": CONTEXT, "actor": AUTHOR, "client_request_id": "bootstrap-1",
            "semantic_digest": SEMANTIC}
    return env.service.reserve_bootstrap(**{**args, **changes})


def _advance(env, op, stage, result=None, **changes):
    args = {"operation_id": op["operation_id"], "boundary": CONTEXT, "actor": AUTHOR,
            "current_stage": op["stage"], "next_stage": stage,
            "expected_version": op["version"], "result": result or {}}
    return env.service.advance(**{**args, **changes})


def _get_op(env, op, **changes):
    return env.service.get(**{"boundary": CONTEXT, "actor": AUTHOR,
                              "operation_id": op["operation_id"], **changes})


def _finish(env, op):
    op = _advance(env, op, "PROVISIONING")
    op = _advance(env, op, "CONTEXT_WRITTEN", {"meta_digest": "c" * 64, "state_digest": "d" * 64})
    op = _advance(env, op, "LEDGER_PENDING")
    return _advance(env, op, "COMPLETED", {"ledger_event_id": op["event_id"], "ledger_acknowledged": True})


def _count(env, table):
    assert table in {"advisor_v2_drafts", "advisor_v2_revisions", "advisor_v2_requests",
                     "advisor_v2_bootstraps", "advisor_v2_transitions"}
    with _db(env) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _error(call, code, status=409):
    with pytest.raises(RevisionStoreError) as failure:
        call()
    assert failure.value.reason_code == code
    assert failure.value.status_code == status


def _race(env, first, second):
    other_adapter = _AdvisorConnection(env.adapter.db_path, env.root)
    other = SimpleNamespace(service=RevisionStore(other_adapter))
    env.service._ensure()
    other.service._ensure()
    gate = threading.Barrier(2)

    def run(target, action):
        gate.wait(timeout=5)
        try:
            return action(target)
        except RevisionStoreError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, env, first), pool.submit(run, other, second)]
        return [future.result(timeout=10) for future in futures]


def test_constructor_does_not_connect_or_initialize():
    def forbidden():
        raise AssertionError("생성자가 연결하면 안 된다")
    RevisionStore(SimpleNamespace(_connect=forbidden, _lock=threading.Lock(), db_path="unused"))


def test_save_is_frozen_content_and_does_not_mutate_input(env):
    blueprint, ref = copy.deepcopy(BLUEPRINT), copy.deepcopy(PROCESS)
    before = copy.deepcopy((blueprint, ref))
    draft = _save(env, blueprint=blueprint, process_ref=ref)
    assert (blueprint, ref) == before
    assert draft["revision"] == 1 and draft["status"] == "DRAFT"
    assert draft["approved_revision_id"] == "" and len(draft["digest"]) == 64
    draft["blueprint"]["title"] = "응답 객체 변경"
    stored = env.service.get(boundary=CONTEXT, actor=AUTHOR, draft_id=draft["draft_id"])
    assert stored["blueprint"]["title"] == BLUEPRINT["title"]


def test_no_process_or_data_required_to_save_but_not_bootstrap(env):
    draft = _save(env, process_ref=None, blueprint={"title": "업무 미정"})
    approved = _decide(env, draft)
    _error(lambda: _reserve(env, approved), "ADVISOR_PROCESS_CONTEXT_REQUIRED", 422)
    assert _count(env, "advisor_v2_revisions") == 1
    assert _count(env, "advisor_v2_bootstraps") == 0


@pytest.mark.parametrize("field", ["approved_by", "status", "owner_user_id", "actor", "revision",
                                  "digest", "context_key", "process_context", "permitted_actions"])
def test_authority_fields_cannot_arrive_inside_blueprint(env, field):
    _error(lambda: _save(env, blueprint={**BLUEPRINT, field: "forged"}), "ADVISOR_AUTHORITY_FIELDS_FORBIDDEN", 422)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()])
def test_non_json_values_are_rejected(env, value):
    _error(lambda: _save(env, blueprint={"title": "부정 입력", "value": value}), "ADVISOR_INPUT_INVALID", 422)


def test_save_replay_is_original_result_even_after_approval(env):
    first = _save(env)
    approved = _decide(env, first)
    assert _save(env) == first
    assert env.service.get(boundary=CONTEXT, actor=AUTHOR, draft_id=first["draft_id"]) == approved
    assert _count(env, "advisor_v2_revisions") == 1


def test_request_key_cannot_change_content(env):
    _save(env)
    _error(lambda: _save(env, blueprint={"title": "다른 요청"}), "ADVISOR_IDEMPOTENCY_CONFLICT")


def test_request_key_is_scoped_by_context_and_actor(env):
    a = _save(env)
    b = _save(env, actor=OTHER)
    context = {**CONTEXT, "context_root_id": "other-root"}
    c = _save(env, boundary=context, process_ref={**PROCESS, "context_key": context})
    assert len({v["draft_id"] for v in (a, b, c)}) == 3


@pytest.mark.parametrize("key,value", [("tenant_id", "other"), ("context_root_id", "other"),
                                      ("scope_node_id", "other"), ("entity_mode", "VIRTUAL")])
def test_exact_boundary_on_get_and_decide(env, key, value):
    draft = _save(env)
    context = {**CONTEXT, key: value}
    _error(lambda: env.service.get(boundary=context, actor=AUTHOR, draft_id=draft["draft_id"]), "ADVISOR_NOT_FOUND", 404)
    _error(lambda: _decide(env, draft, boundary=context), "ADVISOR_NOT_FOUND", 404)


def test_missing_or_extra_context_keys_do_not_default(env):
    for context in ({"tenant_id": "tenant-test"}, {**CONTEXT, "unknown": "ignored?"}):
        _error(lambda: _save(env, boundary=context), "ADVISOR_CONTEXT_INVALID", 422)


def test_actor_required_and_editing_another_authors_draft_is_hidden(env):
    _error(lambda: _save(env, actor=""), "ADVISOR_INPUT_INVALID", 422)
    draft = _save(env)
    _error(lambda: _save(env, draft, actor=OTHER), "ADVISOR_NOT_FOUND", 404)


def test_process_reference_wrong_boundary_cannot_save(env):
    _error(lambda: _save(env, process_ref={**PROCESS, "context_key": {**CONTEXT, "entity_mode": "VIRTUAL"}}),
           "ADVISOR_CONTEXT_MISMATCH", 422)


def test_save_cas_and_existing_revision_history(env):
    first = _save(env)
    second = _save(env, first)
    assert second["revision"] == 2 and second["digest"] != first["digest"]
    _error(lambda: _save(env, first, client_request_id="stale"), "ADVISOR_REVISION_CONFLICT")
    assert env.service.get(boundary=CONTEXT, actor=AUTHOR, draft_id=first["draft_id"], revision=1) == first


def test_approval_consumes_old_digest_and_new_edit_is_new_revision(env):
    first = _save(env)
    approved = _decide(env, first)
    assert approved["approved_revision_id"] == first["revision_id"]
    assert approved["revision"] == first["revision"] and approved["digest"] != first["digest"]
    _error(lambda: _save(env, first), "ADVISOR_REVISION_CONFLICT")
    second = _save(env, approved)
    assert second["revision"] == 2 and second["status"] == "DRAFT"
    assert env.service.get(boundary=CONTEXT, actor=REVIEWER, approved_revision_id=approved["approved_revision_id"]) == approved
    assert _decide(env, first) == approved


def test_approved_revision_cannot_be_rejected_or_reapproved_by_other_actor(env):
    first = _save(env)
    approved = _decide(env, first)
    _error(lambda: _decide(env, first, decision="REJECTED"), "ADVISOR_DECISION_CONFLICT")
    _error(lambda: _decide(env, first, actor=OTHER), "ADVISOR_DECISION_CONFLICT")
    assert _decide(env, first) == approved


def test_only_current_draft_can_be_decided(env):
    first = _save(env)
    _save(env, first)
    _error(lambda: _decide(env, first), "ADVISOR_REVISION_CONFLICT")


def test_self_approval_and_empty_rationale_are_blocked(env):
    first = _save(env)
    _error(lambda: _decide(env, first, actor=AUTHOR.upper()), "ADVISOR_SELF_APPROVAL_FORBIDDEN", 403)
    _error(lambda: _decide(env, first, reason=""), "ADVISOR_INPUT_INVALID", 422)


def test_multiline_reason_is_preserved(env):
    reason = "범위 확인\n미확보 데이터는 후속 준비\n승인 근거 보존"
    assert _decide(env, _save(env), reason=reason)["reason"] == reason


@pytest.mark.parametrize("status", ["DRAFT", "REJECTED"])
def test_unapproved_revisions_cannot_bootstrap(env, status):
    first = _save(env)
    if status == "REJECTED":
        first = _decide(env, first, decision=status)
    _error(lambda: _reserve(env, first), "ADVISOR_APPROVAL_REQUIRED")
    assert _count(env, "advisor_v2_bootstraps") == 0


def test_draft_process_reference_cannot_bootstrap(env):
    approved = _decide(env, _save(env, process_ref={**PROCESS, "state": "DRAFT"}))
    _error(lambda: _reserve(env, approved), "ADVISOR_PROCESS_CONTEXT_REQUIRED")


def test_save_failure_rolls_back_revision_head_and_idempotency(env):
    env.adapter.fault = "INSERT INTO advisor_v2_requests"
    _error(lambda: _save(env), "ADVISOR_STORAGE_UNAVAILABLE", 503)
    env.adapter.fault = ""
    assert [_count(env, table) for table in ("advisor_v2_drafts", "advisor_v2_revisions", "advisor_v2_requests")] == [0, 0, 0]
    assert _save(env)["revision"] == 1


def test_decision_failure_does_not_leave_approved_revision(env):
    draft = _save(env)
    env.adapter.fault = "UPDATE advisor_v2_drafts SET head_digest"
    _error(lambda: _decide(env, draft), "ADVISOR_STORAGE_UNAVAILABLE", 503)
    env.adapter.fault = ""
    assert env.service.get(boundary=CONTEXT, actor=AUTHOR, draft_id=draft["draft_id"]) == draft


def test_independent_connections_save_cas_has_one_winner(env):
    draft = _save(env)
    results = _race(env, lambda e: _save(e, draft, client_request_id="edit-left"),
                    lambda e: _save(e, draft, client_request_id="edit-right"))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert next(r for r in results if isinstance(r, RevisionStoreError)).status_code == 409
    assert _count(env, "advisor_v2_revisions") == 2


def test_independent_connections_edit_versus_approval_has_one_winner(env):
    draft = _save(env)
    results = _race(env, lambda e: _save(e, draft), lambda e: _decide(e, draft))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert next(r for r in results if isinstance(r, RevisionStoreError)).status_code == 409


def test_bootstrap_ids_survive_restart_and_completed_response_loss(env):
    approved = _decide(env, _save(env))
    first = _reserve(env, approved)
    assert first["stage"] == "RESERVED" and first["version"] == 1
    assert first["project_id"].startswith("prj_") and first["event_id"].startswith("dle_")
    final = _finish(env, first)
    env.service = RevisionStore(_AdvisorConnection(env.adapter.db_path, env.root))
    assert _reserve(env, approved) == final
    _save(env, approved)
    assert _reserve(env, approved) == final
    assert _count(env, "advisor_v2_bootstraps") == 1
    assert not (env.root / "projects").exists() and not (env.root / "library").exists()


def test_bootstrap_same_key_cannot_change_semantic_or_approved_digest(env):
    approved = _decide(env, _save(env))
    first = _reserve(env, approved)
    _error(lambda: _reserve(env, approved, semantic_digest="f" * 64), "ADVISOR_PROCESS_SEMANTIC_CONFLICT")
    _error(lambda: _reserve(env, approved, digest="f" * 64), "ADVISOR_REVISION_CONFLICT")
    assert _get_op(env, first) == first


def test_bootstrap_reservation_failure_leaves_no_operation(env):
    approved = _decide(env, _save(env))
    env.adapter.fault = "INSERT INTO advisor_v2_bootstraps"
    _error(lambda: _reserve(env, approved), "ADVISOR_STORAGE_UNAVAILABLE", 503)
    env.adapter.fault = ""
    assert _count(env, "advisor_v2_bootstraps") == 0
    assert _reserve(env, approved)["stage"] == "RESERVED"


def test_bootstrap_actor_scopes_idempotency_and_operation_access(env):
    approved = _decide(env, _save(env))
    first = _reserve(env, approved)
    other = _reserve(env, approved, actor=OTHER)
    assert first["operation_id"] != other["operation_id"]
    _error(lambda: _get_op(env, first, actor=OTHER), "ADVISOR_NOT_FOUND", 404)
    _error(lambda: _advance(env, first, "PROVISIONING", actor=OTHER), "ADVISOR_NOT_FOUND", 404)


def test_bootstrap_wrong_boundary_is_hidden(env):
    approved = _decide(env, _save(env))
    _error(lambda: _reserve(env, approved, context_key={**CONTEXT, "context_root_id": "other"}), "ADVISOR_NOT_FOUND", 404)


def test_independent_connections_reserve_one_operation(env):
    approved = _decide(env, _save(env))
    results = _race(env, lambda e: _reserve(e, approved), lambda e: _reserve(e, approved))
    assert results[0] == results[1]
    assert _count(env, "advisor_v2_bootstraps") == 1


def test_stage_skip_and_missing_readback_are_blocked(env):
    first = _reserve(env, _decide(env, _save(env)))
    _error(lambda: _advance(env, first, "COMPLETED"), "ADVISOR_STAGE_INVALID")
    provisioning = _advance(env, first, "PROVISIONING")
    _error(lambda: _advance(env, provisioning, "CONTEXT_WRITTEN"), "ADVISOR_INPUT_INVALID", 422)
    assert _get_op(env, first) == provisioning


def test_retryable_resume_cannot_skip_failed_stage_and_keeps_ids(env):
    first = _reserve(env, _decide(env, _save(env)))
    failed = _advance(env, first, "FAILED_RETRYABLE", {"error_code": "TEMP_UNAVAILABLE", "error_message": "쓰기 지연"})
    assert failed["resume_stage"] == "RESERVED"
    _error(lambda: _advance(env, failed, "PROVISIONING"), "ADVISOR_STAGE_INVALID")
    resumed = _advance(env, failed, "RESERVED")
    assert resumed["project_id"] == first["project_id"] and resumed["version"] == 3
    assert "error_code" not in resumed["result"]
    # ABA: 단계가 RESERVED로 돌아와도 옛 version으로 전진할 수 없다.
    _error(lambda: _advance(env, first, "PROVISIONING"), "ADVISOR_OPERATION_CONFLICT")
    assert _finish(env, resumed)["stage"] == "COMPLETED"


def test_blocked_is_not_automatically_resumable(env):
    first = _reserve(env, _decide(env, _save(env)))
    blocked = _advance(env, first, "FAILED_BLOCKED", {"error_code": "CONTEXT_CHANGED", "error_message": "검토 필요"})
    _error(lambda: _advance(env, blocked, "RESERVED"), "ADVISOR_STAGE_INVALID")
    assert _get_op(env, first) == blocked


def test_transition_replay_returns_original_result_after_later_stage(env):
    first = _reserve(env, _decide(env, _save(env)))
    second = _advance(env, first, "PROVISIONING")
    _advance(env, second, "CONTEXT_WRITTEN", {"meta_digest": "c" * 64, "state_digest": "d" * 64})
    assert _advance(env, first, "PROVISIONING") == second
    _error(lambda: _advance(env, first, "PROVISIONING", {"note": "different"}), "ADVISOR_OPERATION_CONFLICT")


def test_ids_and_written_digests_cannot_be_replaced(env):
    first = _reserve(env, _decide(env, _save(env)))
    _error(lambda: _advance(env, first, "PROVISIONING", {"project_id": "prj-other"}), "ADVISOR_OPERATION_CONFLICT")
    second = _advance(env, first, "PROVISIONING")
    context = _advance(env, second, "CONTEXT_WRITTEN", {"meta_digest": "c" * 64, "state_digest": "d" * 64})
    _error(lambda: _advance(env, context, "LEDGER_PENDING", {"meta_digest": "e" * 64}), "ADVISOR_OPERATION_CONFLICT")


@pytest.mark.parametrize("ack", [{}, {"ledger_acknowledged": True, "ledger_event_id": "wrong"},
                                  {"ledger_acknowledged": 1}])
def test_completion_requires_exact_fixed_event_ack(env, ack):
    op = _reserve(env, _decide(env, _save(env)))
    op = _advance(env, op, "PROVISIONING")
    op = _advance(env, op, "CONTEXT_WRITTEN", {"meta_digest": "c" * 64, "state_digest": "d" * 64})
    op = _advance(env, op, "LEDGER_PENDING")
    _error(lambda: _advance(env, op, "COMPLETED", ack), "ADVISOR_LEDGER_ACK_REQUIRED")
    assert _get_op(env, op) == op


def test_transition_failure_rolls_back_stage_and_event(env):
    first = _reserve(env, _decide(env, _save(env)))
    env.adapter.fault = "INSERT INTO advisor_v2_transitions"
    _error(lambda: _advance(env, first, "PROVISIONING"), "ADVISOR_STORAGE_UNAVAILABLE", 503)
    env.adapter.fault = ""
    assert _get_op(env, first) == first and _count(env, "advisor_v2_transitions") == 0


def test_independent_connections_cannot_double_advance(env):
    first = _reserve(env, _decide(env, _save(env)))
    results = _race(env, lambda e: _advance(e, first, "PROVISIONING"),
                    lambda e: _advance(e, first, "FAILED_RETRYABLE", {"error_code": "TEMP", "error_message": "지연"}))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert next(r for r in results if isinstance(r, RevisionStoreError)).status_code == 409
    assert _count(env, "advisor_v2_transitions") == 1


def test_approved_revision_and_request_history_have_database_write_guards(env):
    approved = _decide(env, _save(env))
    with _db(env) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE advisor_v2_revisions SET status='REJECTED' WHERE revision_id=?", (approved["revision_id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM advisor_v2_revisions WHERE revision_id=?", (approved["revision_id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM advisor_v2_requests")


def test_operation_state_tampering_is_not_read_as_success(env):
    first = _reserve(env, _decide(env, _save(env)))
    with _db(env) as conn:
        conn.execute("UPDATE advisor_v2_bootstraps SET stage='COMPLETED' WHERE operation_id=?", (first["operation_id"],))
    _error(lambda: _get_op(env, first), "ADVISOR_STORAGE_INTEGRITY", 503)


def test_head_rewind_is_detected(env):
    first = _save(env)
    _save(env, first)
    with _db(env) as conn:
        conn.execute("UPDATE advisor_v2_drafts SET head_revision=1,head_revision_id=?,head_digest=? WHERE draft_id=?",
                     (first["revision_id"], first["digest"], first["draft_id"]))
    _error(lambda: env.service.get(boundary=CONTEXT, actor=AUTHOR, draft_id=first["draft_id"]), "ADVISOR_STORAGE_INTEGRITY", 503)


def test_legacy_tables_and_schema_are_not_changed(env):
    with _db(env) as conn:
        before_schema = [tuple(r) for r in conn.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('consultations','solution_blueprints') ORDER BY name")]
    _finish(env, _reserve(env, _decide(env, _save(env))))
    with _db(env) as conn:
        assert [tuple(r) for r in conn.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('consultations','solution_blueprints') ORDER BY name")] == before_schema
        assert [tuple(r) for r in conn.execute("SELECT * FROM consultations")] == [("old-cons", "unchanged-consultation")]
        assert [tuple(r) for r in conn.execute("SELECT * FROM solution_blueprints")] == [("old-bp", "unchanged-approved-blueprint")]


def test_all_store_connections_are_closed(env):
    _save(env)
    for conn in env.adapter.connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def _replay(env, **changes):
    return env.service.replay_save(**{
        "boundary": CONTEXT, "actor": AUTHOR, "client_request_id": "save-1",
        "command_digest": "c" * 64, **changes})


def test_command_replay_miss_does_not_create_draft_or_request(env):
    assert _replay(env) is None
    assert _count(env, "advisor_v2_drafts") == _count(env, "advisor_v2_requests") == 0


def test_command_replay_returns_original_after_approval_and_later_edit(env):
    original = _save(env, command_digest="c" * 64)
    approved = _decide(env, original)
    newer = _save(env, approved, command_digest="d" * 64)
    assert newer["revision"] == 2
    assert _replay(env) == original
    assert _replay(env)["status"] == "DRAFT"
    assert _count(env, "advisor_v2_revisions") == 2


def test_save_command_fingerprint_ignores_server_dynamic_projection_on_exact_retry(env):
    original = _save(env, command_digest="c" * 64)
    newer = _save(env, original, command_digest="d" * 64)
    changed_ref = {**PROCESS, "blockers": [{"code": "NEW_DYNAMIC_BLOCKER"}],
                   "configuration_fingerprint": "e" * 64}
    assert _save(env, newer, client_request_id="save-1", command_digest="c" * 64,
                  process_ref=changed_ref, blueprint={"title": "현재 head에서 다시 합성한 입력"}) == original
    assert _count(env, "advisor_v2_revisions") == 2


def test_same_save_key_different_command_is_conflict_for_lookup_and_write(env):
    original = _save(env, command_digest="c" * 64)
    _error(lambda: _replay(env, command_digest="d" * 64), "ADVISOR_IDEMPOTENCY_CONFLICT")
    _error(lambda: _save(env, command_digest="d" * 64), "ADVISOR_IDEMPOTENCY_CONFLICT")
    assert _replay(env) == original
    assert _count(env, "advisor_v2_revisions") == 1


def test_replay_lookup_does_not_disclose_other_actor_or_boundary(env):
    _save(env, command_digest="c" * 64)
    assert _replay(env, actor=OTHER) is None
    assert _replay(env, boundary={**CONTEXT, "context_root_id": "other"}) is None
    assert _replay(env, actor=AUTHOR.upper()) is not None


def test_direct_save_without_command_keeps_full_body_fingerprint(env):
    original = _save(env)
    assert _save(env, command_digest="") == original
    _error(lambda: _save(env, blueprint={"title": "다른 입력"}), "ADVISOR_IDEMPOTENCY_CONFLICT")
    # 기존 full-body 요청을 임의의 command digest로 조회/전환할 수 없다.
    _error(lambda: _replay(env), "ADVISOR_IDEMPOTENCY_CONFLICT")


@pytest.mark.parametrize("command", [None, 1, True, "x" * 64, "A" * 64, "a" * 63,
                                      "a" * 65, " " + "a" * 64, "a" * 64 + "\n"])
def test_server_command_digest_must_be_strict_lowercase_sha256(env, command):
    _error(lambda: _save(env, command_digest=command), "ADVISOR_INPUT_INVALID", 422)
    _error(lambda: _replay(env, command_digest=command), "ADVISOR_INPUT_INVALID", 422)


def test_replay_requires_nonempty_command_digest(env):
    _error(lambda: _replay(env, command_digest=""), "ADVISOR_INPUT_INVALID", 422)


def test_command_digest_is_not_client_blueprint_content(env):
    _error(lambda: _save(env, blueprint={"title": "입력", "command_digest": "c" * 64}),
           "ADVISOR_AUTHORITY_FIELDS_FORBIDDEN", 422)


def test_replay_still_verifies_current_head_integrity(env):
    first = _save(env, command_digest="c" * 64)
    _save(env, first, command_digest="d" * 64)
    with _db(env) as conn:
        conn.execute("UPDATE advisor_v2_drafts SET head_revision=1,head_revision_id=?,head_digest=? WHERE draft_id=?",
                     (first["revision_id"], first["digest"], first["draft_id"]))
    _error(lambda: _replay(env), "ADVISOR_STORAGE_INTEGRITY", 503)


def test_replay_still_verifies_original_content_after_new_head(env):
    first = _save(env, command_digest="c" * 64)
    _save(env, first, command_digest="d" * 64)
    # 임시 DB의 DRAFT를 허용된 확정 모양으로 바꾸되 digest를 맞추지 않는 고장 주입.
    with _db(env) as conn:
        conn.execute("UPDATE advisor_v2_revisions SET status='REJECTED',decision_actor=?,reason='tampered',"
                     "decided_at='tampered',decision_request_fingerprint='tampered' WHERE revision_id=?",
                     (REVIEWER, first["revision_id"]))
    _error(lambda: _replay(env), "ADVISOR_STORAGE_INTEGRITY", 503)


def test_two_command_saves_after_replay_miss_are_atomic(env):
    assert _replay(env) is None
    results = _race(env, lambda e: _save(e, command_digest="c" * 64),
                    lambda e: _save(e, command_digest="c" * 64,
                                     process_ref={**PROCESS, "blockers": ["dynamic"]}))
    assert isinstance(results[0], dict) and results[0] == results[1]
    assert _count(env, "advisor_v2_revisions") == _count(env, "advisor_v2_requests") == 1


def test_project_lookup_unknown_returns_none_and_oracle_false(env):
    assert env.service.is_v2_project("unknown.test.invalid") is False
    assert env.service.get_for_project(boundary=CONTEXT, project_id="unknown.test.invalid") is None
    assert _count(env, "advisor_v2_bootstraps") == 0


def test_project_lookup_uses_reserved_db_actor_and_current_operation(env):
    reserved = _reserve(env, _decide(env, _save(env)), actor=OTHER)
    assert env.service.is_v2_project(reserved["project_id"]) is True
    assert env.service.get_for_project(boundary=CONTEXT, project_id=reserved["project_id"]) == reserved
    progressed = _advance(env, reserved, "PROVISIONING", actor=OTHER)
    assert env.service.get_for_project(boundary=CONTEXT, project_id=reserved["project_id"]) == progressed


@pytest.mark.parametrize("key,value", [("tenant_id", "other"), ("context_root_id", "other"),
                                      ("entity_mode", "VIRTUAL"), ("scope_node_id", "other")])
def test_project_lookup_wrong_boundary_is_404_never_legacy_none(env, key, value):
    op = _reserve(env, _decide(env, _save(env)))
    assert env.service.is_v2_project(op["project_id"]) is True
    _error(lambda: env.service.get_for_project(boundary={**CONTEXT, key: value}, project_id=op["project_id"]),
           "ADVISOR_NOT_FOUND", 404)


@pytest.mark.parametrize("stage", ["RESERVED", "FAILED_RETRYABLE", "FAILED_BLOCKED", "COMPLETED"])
def test_any_reserved_project_stays_v2_without_metadata_markers(env, stage):
    op = _reserve(env, _decide(env, _save(env)))
    if stage == "COMPLETED":
        op = _finish(env, op)
    elif stage != "RESERVED":
        op = _advance(env, op, stage, {"error_code": "SYNTHETIC", "error_message": "임시 오류"})
    # meta/state/클라이언트 marker를 만들거나 읽지 않아도 DB 예약이 단일 기준이다.
    assert env.service.is_v2_project(op["project_id"]) is True
    assert env.service.get_for_project(boundary=CONTEXT, project_id=op["project_id"]) == op


def test_corrupt_operation_is_v2_but_not_a_successful_project_lookup(env):
    op = _reserve(env, _decide(env, _save(env)))
    with _db(env) as conn:
        conn.execute("UPDATE advisor_v2_bootstraps SET stage='COMPLETED' WHERE operation_id=?", (op["operation_id"],))
    assert env.service.is_v2_project(op["project_id"]) is True
    _error(lambda: env.service.get_for_project(boundary=CONTEXT, project_id=op["project_id"]),
           "ADVISOR_STORAGE_INTEGRITY", 503)


def test_project_lookup_and_command_replay_storage_faults_are_not_misses(env):
    _save(env, command_digest="c" * 64)
    env.adapter.fault = "FROM advisor_v2_bootstraps"
    _error(lambda: env.service.is_v2_project("unknown.test.invalid"), "ADVISOR_STORAGE_UNAVAILABLE", 503)
    _error(lambda: env.service.get_for_project(boundary=CONTEXT, project_id="unknown.test.invalid"),
           "ADVISOR_STORAGE_UNAVAILABLE", 503)
    env.adapter.fault = "FROM advisor_v2_requests"
    _error(lambda: _replay(env), "ADVISOR_STORAGE_UNAVAILABLE", 503)
    env.adapter.fault = ""
    for conn in env.adapter.connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


_V2_TABLES = ("advisor_v2_drafts", "advisor_v2_revisions", "advisor_v2_requests",
              "advisor_v2_bootstraps", "advisor_v2_transitions")
_IDENTITY_COLLISIONS = [
    ("advisor_v2_drafts", "draft_id"),
    ("advisor_v2_revisions", "revision_id"), ("advisor_v2_revisions", "revision_number"),
    ("advisor_v2_requests", "request_scope"),
    ("advisor_v2_bootstraps", "operation_id"), ("advisor_v2_bootstraps", "project_id"),
    ("advisor_v2_bootstraps", "event_id"), ("advisor_v2_bootstraps", "request_scope"),
    ("advisor_v2_transitions", "transition_version"),
]


@pytest.mark.parametrize("field", ["runtime_document_version", "setup_status",
                                  "approved_blueprint_revision_id", "approved_blueprint_digest"])
def test_server_runtime_provenance_is_not_blueprint_or_transition_input(env, field):
    _error(lambda: _save(env, blueprint={field: "forged"}), "ADVISOR_AUTHORITY_FIELDS_FORBIDDEN", 422)
    op = _reserve(env, _decide(env, _save(env)))
    _error(lambda: _advance(env, op, "PROVISIONING", {field: "forged"}), "ADVISOR_AUTHORITY_FIELDS_FORBIDDEN", 422)
    assert _get_op(env, op) == op


def _v2_snapshot(conn):
    return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in _V2_TABLES}


@pytest.mark.parametrize("verb", ["INSERT OR REPLACE", "REPLACE", "INSERT OR IGNORE"])
@pytest.mark.parametrize("table,identity", _IDENTITY_COLLISIONS)
def test_v2_insert_identity_guards_block_every_unique_collision_without_recursive_triggers(env, verb, table, identity):
    approved = _decide(env, _save(env))
    _advance(env, _reserve(env, approved), "PROVISIONING")
    with _db(env) as conn:
        conn.execute("PRAGMA recursive_triggers=OFF")
        assert conn.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        before = _v2_snapshot(conn)
        row = dict(conn.execute(f"SELECT * FROM {table} ORDER BY rowid LIMIT 1").fetchone())
        candidate = dict(row)
        if table == "advisor_v2_drafts":
            candidate["owner_actor"] = OTHER
        elif table == "advisor_v2_revisions":
            # PK와 draft/revision UNIQUE를 각각 단독으로 충돌시킨다.
            if identity == "revision_id":
                candidate["revision"] += 100
            else:
                candidate["revision_id"] = "avr_other.test.invalid"
            candidate["content_json"] = '{"tampered":true}'
        elif table == "advisor_v2_bootstraps":
            candidate.update(operation_id="bop_other.test.invalid", project_id="prj_other.test.invalid",
                             event_id="dle_other.test.invalid", client_request_id="other-request.test.invalid")
            if identity == "request_scope":
                candidate["client_request_id"] = row["client_request_id"]
            else:
                candidate[identity] = row[identity]
        else:
            candidate["request_fingerprint"] = "0" * 64
        fields = ",".join(candidate)
        marks = ",".join("?" for _ in candidate)
        # FK/CHECK가 우연히 막은 결과를 INSERT 가드 통과로 잘못 세지 않는다.
        with pytest.raises(sqlite3.IntegrityError, match="advisor v2 insert identity collision"):
            conn.execute(f"{verb} INTO {table} ({fields}) VALUES ({marks})", tuple(candidate.values()))
        assert _v2_snapshot(conn) == before


def test_normal_first_insert_and_api_replay_work_with_recursive_triggers_off(env, monkeypatch):
    connect = env.adapter._connect

    def no_recursive_connect():
        conn = connect()
        conn.execute("PRAGMA recursive_triggers=OFF")
        return conn

    monkeypatch.setattr(env.adapter, "_connect", no_recursive_connect)
    first = _save(env)
    assert _save(env) == first
    approved = _decide(env, first)
    assert _decide(env, first) == approved
    reserved = _reserve(env, approved)
    completed = _finish(env, reserved)
    assert _reserve(env, approved) == completed
    assert _save(env, approved)["revision"] == 2
    with _db(env) as conn:
        triggers = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'advisor_v2_%_insert_identity'")]
        assert len(triggers) == 5
        assert [tuple(row) for row in conn.execute("SELECT * FROM consultations")] == [("old-cons", "unchanged-consultation")]
        assert [tuple(row) for row in conn.execute("SELECT * FROM solution_blueprints")] == [("old-bp", "unchanged-approved-blueprint")]


def _at_stage(env, target):
    op = _reserve(env, _decide(env, _save(env)))
    if target == "RESERVED":
        return op
    op = _advance(env, op, "PROVISIONING")
    if target == "PROVISIONING":
        return op
    op = _advance(env, op, "CONTEXT_WRITTEN", {"meta_digest": "c" * 64, "state_digest": "d" * 64})
    if target == "CONTEXT_WRITTEN":
        return op
    return _advance(env, op, "LEDGER_PENDING")


@pytest.mark.parametrize("current,next_stage", [("RESERVED", "PROVISIONING"),
    ("PROVISIONING", "CONTEXT_WRITTEN"), ("CONTEXT_WRITTEN", "LEDGER_PENDING"),
    ("LEDGER_PENDING", "COMPLETED"), ("RESERVED", "FAILED_RETRYABLE"),
    ("PROVISIONING", "FAILED_BLOCKED")])
def test_wrong_ledger_event_id_is_rejected_before_any_stage_write(env, current, next_stage):
    op = _at_stage(env, current)
    result = {"ledger_event_id": "dle_wrong.test.invalid", "meta_digest": "c" * 64, "state_digest": "d" * 64}
    if next_stage == "COMPLETED":
        result["ledger_acknowledged"] = True
    if next_stage.startswith("FAILED_"):
        result.update(error_code="SYNTHETIC", error_message="실패 시험")
    count = _count(env, "advisor_v2_transitions")
    _error(lambda: _advance(env, op, next_stage, result), "ADVISOR_LEDGER_ACK_REQUIRED")
    assert _get_op(env, op) == op and _count(env, "advisor_v2_transitions") == count


def test_failed_retry_resume_also_rejects_wrong_ledger_event_id(env):
    reserved = _at_stage(env, "RESERVED")
    failed = _advance(env, reserved, "FAILED_RETRYABLE", {"error_code": "SYNTHETIC", "error_message": "실패 시험"})
    _error(lambda: _advance(env, failed, "RESERVED", {"ledger_event_id": "dle_wrong.test.invalid"}),
           "ADVISOR_LEDGER_ACK_REQUIRED")
    assert _get_op(env, reserved) == failed
    resumed = _advance(env, failed, "RESERVED", {"ledger_event_id": failed["event_id"]})
    assert _finish(env, resumed)["stage"] == "COMPLETED"


def test_correct_fixed_event_id_can_be_recorded_early_without_ack(env):
    reserved = _at_stage(env, "RESERVED")
    first = _advance(env, reserved, "PROVISIONING", {"ledger_event_id": reserved["event_id"]})
    assert first["result"]["ledger_event_id"] == reserved["event_id"]
    assert "ledger_acknowledged" not in first["result"]
    assert _advance(env, reserved, "PROVISIONING", {"ledger_event_id": reserved["event_id"]}) == first
    second = _advance(env, first, "CONTEXT_WRITTEN", {"meta_digest": "c" * 64, "state_digest": "d" * 64})
    pending = _advance(env, second, "LEDGER_PENDING")
    assert _advance(env, pending, "COMPLETED", {"ledger_acknowledged": True})["stage"] == "COMPLETED"


@pytest.mark.parametrize("value", [None, "", 1, True])
def test_malformed_ledger_event_id_is_422_without_partial_write(env, value):
    op = _at_stage(env, "RESERVED")
    _error(lambda: _advance(env, op, "PROVISIONING", {"ledger_event_id": value}), "ADVISOR_INPUT_INVALID", 422)
    assert _get_op(env, op) == op


def _seed_pre_fix_ledger_id_history(env, *, later_clean_head=False):
    """pre-fix가 저장할 수 있던 해시 일치 상태를 새 임시 DB에만 구성한다.

    보호 trigger 제거/REPLACE 없이 새 이력 INSERT + 아직 미완료인 op UPDATE만 한다.
    later_clean_head는 과거 오류를 단순히 현재 head에서 지운 경우도 fail closed인지 확인한다.
    """
    from core.advisor_revision_store import _hash, _json
    op = _at_stage(env, "RESERVED")
    poisoned = {**op, "stage": "PROVISIONING", "version": 2, "updated_at": "2030-01-01T00:00:00+00:00",
                "result": {**op["result"], "ledger_event_id": "dle_wrong.test.invalid"}}
    entries = [poisoned]
    if later_clean_head:
        entries.append({**poisoned, "stage": "CONTEXT_WRITTEN", "version": 3,
                        "result": {**op["result"], "meta_digest": "c" * 64, "state_digest": "d" * 64}})
    head = entries[-1]
    with _db(env) as conn:
        conn.execute("UPDATE advisor_v2_bootstraps SET stage=?,version=?,updated_at=?,result_json=?,result_digest=? WHERE operation_id=?",
                     (head["stage"], head["version"], head["updated_at"], _json(head["result"]), _hash(head["result"]), op["operation_id"]))
        for entry in entries:
            conn.execute("INSERT INTO advisor_v2_transitions VALUES(?,?,?,?,?)",
                         (op["operation_id"], entry["version"] - 1, "e" * 64, _json(entry), _hash(entry)))
    return head


@pytest.mark.parametrize("later_clean_head", [False, True])
def test_pre_fix_mismatched_ledger_history_is_corrupt_even_with_matching_hashes(env, later_clean_head):
    head = _seed_pre_fix_ledger_id_history(env, later_clean_head=later_clean_head)
    _error(lambda: _get_op(env, head), "ADVISOR_STORAGE_INTEGRITY", 503)
    _error(lambda: env.service.get_for_project(boundary=CONTEXT, project_id=head["project_id"]), "ADVISOR_STORAGE_INTEGRITY", 503)
    _error(lambda: _advance(env, head, "LEDGER_PENDING"), "ADVISOR_STORAGE_INTEGRITY", 503)
    assert env.service.is_v2_project(head["project_id"]) is True
