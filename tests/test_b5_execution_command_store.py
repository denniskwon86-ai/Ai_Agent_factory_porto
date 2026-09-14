"""B5 명령 저장소 집중 회귀. 실행/수집은 main의 기존 strict-writes 런너 전용.

기존 실제 AdvisorStore·tmp SQLite 격리를 재사용한다. 실행 엔진/PDP/HTTP 검증으로
표현하지 않으며 DB 밖 task·WBS·운영 자료·RAW를 건드리지 않는다.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from tests.test_b3_studio_drafts import isolated_stores  # noqa: F401


PROJECT = "B5_COMMAND_TEST"
ACTOR = "author@command.test.invalid"
BOUNDARY = {"ownership": {"tenant_id": "test", "enterprise_scope_id": "scope-A", "entity_mode": "REAL"},
            "viewing_context": {"scope_node_id": "scope-A"}, "process_context": {}}


def key(number=1):
    return f"b5000000-0000-4000-8000-{number:012d}"


def request(number=1, operation="START", **changes):
    return {**dict(client_request_id=key(number), operation=operation, task_id="TASK-01",
                   input={"feedback": "합성 원문 보존"}), **changes}


@pytest.fixture
def commands(isolated_stores):
    from core.studio_execution_commands import CommandStore
    return SimpleNamespace(store=CommandStore(isolated_stores.advisor), advisor=isolated_stores.advisor,
        args=dict(project_id=PROJECT, actor_id=ACTOR, boundary=copy.deepcopy(BOUNDARY)))


def begin(env, number=1, operation="START", **changes):
    return env.store.begin(**env.args, request=request(number, operation, **changes))


def get(env, number=1):
    return env.store.get(**env.args, request_id=key(number))


def finish(env, number=1, outcome="ACCEPTED", result=None):
    return env.store.finish(**env.args, request_id=key(number), outcome=outcome,
                            result={"execution_started": True} if result is None else result)


def failure(call, status, reason):
    from core.studio_execution_commands import CommandStoreError
    with pytest.raises(CommandStoreError) as exc:
        call()
    assert exc.value.status_code == status and exc.value.reason_code == "STUDIO_COMMAND_" + reason
    return str(exc.value)


def stored_rows(env):
    with env.store.transaction() as conn:
        if not env.store._ready(conn):
            return []
        return [tuple(row) for row in conn.execute("SELECT * FROM studio_execution_commands ORDER BY request_id")]


def fresh_store(env):
    from core.studio_execution_commands import CommandStore
    # 동일 DB, 독립 잠금: SQLite BEGIN IMMEDIATE가 서로 다른 저장소 인스턴스도 보호한다.
    return CommandStore(SimpleNamespace(_lock=threading.Lock(), _connect=env.advisor._connect))


def test_constructor_get_and_list_do_not_create_command_table(commands):
    env = commands
    with env.store.transaction() as conn:
        before = [tuple(row) for row in conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name")]
    failure(lambda: get(env), 404, "NOT_FOUND")
    assert env.store.list(**env.args) == []
    with env.store.transaction() as conn:
        assert [tuple(row) for row in conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name")] == before


def test_begin_has_exact_dto_and_reopened_canonical_retry_is_identical(commands):
    from core.studio_execution_commands import digest
    env = commands
    original = request(input={"feedback": "원문 \n", "initial_idea": "구매"})
    row, created = env.store.begin(**env.args, request=original)
    assert created is True and row["status"] == "PROCESSING" and row["result"] is None
    assert set(row) == {"request_id", "project_id", "actor_id", "operation", "task_id", "input", "command_digest",
                        "status", "result", "created_at", "updated_at", "receipt_digest"}
    assert row["project_id"] == PROJECT and row["actor_id"] == ACTOR and row["request_id"] == key()
    assert row["input"] == original["input"] and row["command_digest"] == digest(original)
    assert row["receipt_digest"] == digest({k: v for k, v in row.items() if k != "receipt_digest"})
    assert row["created_at"] == row["updated_at"]
    before = stored_rows(env)
    reordered = {"input": {"initial_idea": "구매", "feedback": "원문 \n"}, "task_id": "TASK-01",
                 "operation": "START", "client_request_id": key().upper()}
    reopened = fresh_store(env)
    assert reopened.begin(**env.args, request=reordered) == (row, False)
    assert reopened.get(**env.args, request_id=key().upper()) == row
    assert stored_rows(env) == before
    row["input"]["feedback"] = "반환 객체 편집"
    assert get(env)["input"] == original["input"]


@pytest.mark.parametrize("change", [{"operation": "STOP"}, {"task_id": "TASK-02"}, {"input": {"feedback": "다른 의견"}}])
def test_same_key_changed_command_is_409_without_mutation(commands, change):
    env = commands
    begin(env)
    before = stored_rows(env)
    failure(lambda: begin(env, **change), 409, "IDEMPOTENCY_CONFLICT")
    assert stored_rows(env) == before


@pytest.mark.parametrize("identity", [{"actor_id": "other@command.test.invalid"}, {"project_id": "OTHER"},
    {"boundary": {**BOUNDARY, "viewing_context": {"scope_node_id": "scope-B"}}}])
def test_other_actor_project_or_context_cannot_read_replay_or_finish(commands, identity):
    env = commands
    begin(env)
    before = stored_rows(env)
    args = {**env.args, **identity}
    calls = [lambda: env.store.get(**args, request_id=key()),
             lambda: env.store.begin(**args, request=request(input={"feedback": "다른 명령"})),
             lambda: env.store.finish(**args, request_id=key(), outcome="ACCEPTED", result={})]
    for call in calls:
        message = failure(call, 404, "NOT_FOUND")
        assert ACTOR not in message and "합성 원문" not in message
    assert env.store.list(**args) == [] and stored_rows(env) == before


@pytest.mark.parametrize("outcome", ["ACCEPTED", "REJECTED", "UNKNOWN"])
def test_finish_is_one_way_cas_and_identical_retry_is_read_only(commands, outcome):
    from core.studio_execution_commands import digest
    env = commands
    started, _ = begin(env)
    result = {"execution_started": False, "reason_code": "SYNTHETIC", "detail": {"preserved": True}}
    closed = finish(env, outcome=outcome, result=result)
    assert closed["status"] == outcome and closed["result"] == result
    for name in ("request_id", "project_id", "actor_id", "input", "operation", "task_id", "created_at", "command_digest"):
        assert closed[name] == started[name]
    assert closed["receipt_digest"] != started["receipt_digest"]
    assert closed["receipt_digest"] == digest({k: v for k, v in closed.items() if k != "receipt_digest"})
    before = stored_rows(env)
    assert finish(env, outcome=outcome, result=dict(reversed(list(result.items())))) == closed
    assert begin(env) == (closed, False) and get(env) == closed
    for different in ({"outcome": "REJECTED" if outcome != "REJECTED" else "ACCEPTED", "result": result},
                      {"outcome": outcome, "result": {"changed": True}}):
        failure(lambda: finish(env, **different), 409, "TERMINAL_CONFLICT")
    assert stored_rows(env) == before


@pytest.mark.parametrize("outcome,result", [("PROCESSING", {}), ("CONFIRMED", {}), ("accepted", {}),
                                          (True, {}), ("ACCEPTED", []), ("UNKNOWN", None)])
def test_finish_accepts_only_closed_explicit_outcomes_and_object_result(commands, outcome, result):
    env = commands
    begin(env)
    before = stored_rows(env)
    failure(lambda: env.store.finish(**env.args, request_id=key(), outcome=outcome, result=result), 422, "INVALID")
    assert stored_rows(env) == before


@pytest.mark.parametrize("status", ["PROCESSING", "UNKNOWN"])
@pytest.mark.parametrize("operation", ["START", "RESUME", "RESUME_QUOTA", "HEAL"])
def test_project_unresolved_command_blocks_all_new_execution_without_cross_actor_leak(commands, status, operation):
    env = commands
    begin(env)
    if status == "UNKNOWN":
        finish(env, outcome="UNKNOWN", result={"secret": "private-result"})
    before = stored_rows(env)
    other = {**env.args, "actor_id": "other@command.test.invalid", "boundary": {"ownership": "other-view"}}
    message = failure(lambda: env.store.begin(**other, request=request(2, operation)), 409, "PROJECT_BUSY")
    assert ACTOR not in message and "private-result" not in message and key() not in message
    assert stored_rows(env) == before
    failure(lambda: get(env, 2), 404, "NOT_FOUND")


@pytest.mark.parametrize("operation", ["PAUSE", "STOP"])
@pytest.mark.parametrize("status", ["PROCESSING", "UNKNOWN"])
def test_pause_and_stop_remain_available_when_project_outcome_is_unresolved(commands, operation, status):
    env = commands
    row, _ = begin(env)
    if status == "UNKNOWN":
        row = finish(env, outcome="UNKNOWN", result={})
    emergency, created = begin(env, 2, operation)
    assert created and emergency["operation"] == operation and emergency["status"] == "PROCESSING"
    assert get(env) == row


@pytest.mark.parametrize("outcome", ["ACCEPTED", "REJECTED"])
def test_confirmed_terminal_command_does_not_block_next_execution(commands, outcome):
    env = commands
    begin(env)
    finish(env, outcome=outcome)
    assert begin(env, 2, "RESUME")[1] is True


def test_heal_limit_persists_across_instances_actors_contexts_and_all_terminal_results(commands):
    from core.studio_execution_commands import HEAL_LIMIT
    env = commands
    assert HEAL_LIMIT == 3  # 이번 저장소 서버 한도. 기존 UI 또는 빌드 차수를 입증하지 않는다.
    for number in range(1, HEAL_LIMIT + 1):
        store = fresh_store(env)
        args = {**env.args, "actor_id": f"actor-{number}@test.invalid", "boundary": {"server_scope": str(number)}}
        row, created = store.begin(**args, request=request(number, "HEAL", input={"error_log": "합성 오류"}))
        assert created and store.begin(**args, request=request(number, "HEAL", input={"error_log": "합성 오류"})) == (row, False)
        store.finish(**args, request_id=key(number), outcome="REJECTED" if number == 2 else "ACCEPTED", result={})
    before = stored_rows(env)
    failure(lambda: begin(env, 4, "HEAL", input={"feedback": "reset 횟수 0이라는 클라이언트 의견"}),
            409, "HEAL_BUDGET_EXHAUSTED")
    assert stored_rows(env) == before
    assert begin(env, 5, "STOP")[1] is True
    other_project = {**env.args, "project_id": "OTHER_PROJECT"}
    assert env.store.begin(**other_project, request=request(6, "HEAL"))[1] is True


def test_processing_heal_counts_once_before_any_execution_and_unknown_never_refunds(commands):
    env = commands
    row, _ = begin(env, operation="HEAL")
    assert row["status"] == "PROCESSING" and len(stored_rows(env)) == 1
    assert begin(env, operation="HEAL") == (row, False)
    finish(env, outcome="UNKNOWN", result={"execution_started": None})
    failure(lambda: begin(env, 2, "HEAL"), 409, "PROJECT_BUSY")
    assert len(stored_rows(env)) == 1


def test_hotl_pending_heal_receipt_still_uses_explicit_server_budget(commands):
    env = commands
    for number in range(1, 4):
        row, created = begin(env, number, "HEAL", task_id="sprint_init")
        assert created and row["task_id"] == "sprint_init"
        closed = finish(env, number, result={"reason_code": "HOTL_PENDING", "execution_started": False})
        assert closed["status"] == "ACCEPTED"
    before = stored_rows(env)
    failure(lambda: begin(env, 4, "HEAL", task_id="sprint_init"), 409, "HEAL_BUDGET_EXHAUSTED")
    assert stored_rows(env) == before


def test_list_returns_only_current_personal_context_recent_verified_records(commands):
    env = commands
    values = [begin(env, n, "PAUSE")[0] for n in range(1, 4)]
    other_args = {**env.args, "actor_id": "other@test.invalid"}
    env.store.begin(**other_args, request=request(4, "STOP"))
    before = stored_rows(env)
    expected = sorted(values, key=lambda value: (value["created_at"], value["request_id"]), reverse=True)
    assert env.store.list(**env.args) == expected
    assert env.store.list(**env.args, limit=2) == expected[:2]
    assert all(get(env, n) == values[n - 1] for n in range(1, 4))
    assert stored_rows(env) == before


@pytest.mark.parametrize("limit", [0, -1, 101, True, "50"])
def test_list_bound_is_strict(commands, limit):
    failure(lambda: commands.store.list(**commands.args, limit=limit), 422, "INVALID")


@pytest.mark.parametrize("changes", [
    {"client_request_id": "not-uuid"}, {"client_request_id": key().replace("-", "")},
    {"operation": "QUOTA"}, {"operation": "APPROVE"}, {"task_id": "../outside"},
    {"input": {"reset": True}}, {"input": {"heal_budget_exempt": "true"}},
    {"input": {"master_data": {}}}, {"input": {"feedback": None}}, {"input": {"feedback": float("nan")}},
    {"input": {1: "text"}}, {"unexpected": "actor override"},
])
def test_request_is_closed_and_client_cannot_reset_heal_budget(commands, changes):
    env = commands
    failure(lambda: env.store.begin(**env.args, request=request(**changes)), 422, "INVALID")
    assert stored_rows(env) == []


def test_request_size_limit_counts_canonical_utf8_bytes_including_envelope(commands):
    from core.studio_execution_commands import MAX_REQUEST_BYTES, canonical
    env = commands
    command = request(input={"error_log": ""})
    available = MAX_REQUEST_BYTES - len(canonical(command).encode("utf-8"))
    command["input"]["error_log"] = "x" * available
    assert len(canonical(command).encode("utf-8")) == MAX_REQUEST_BYTES
    assert env.store.begin(**env.args, request=command)[1]
    before = stored_rows(env)
    command["input"]["error_log"] += "x"
    failure(lambda: env.store.begin(**env.args, request=command), 422, "INVALID")
    command["input"]["error_log"] = "가" * (available // 3 + 1)
    failure(lambda: env.store.begin(**env.args, request=command), 422, "INVALID")
    assert stored_rows(env) == before


@pytest.mark.parametrize("damage", ["json", "record_digest", "command_digest", "receipt_digest", "status", "boundary", "rehash_input"])
def test_corrupt_record_is_503_on_get_list_replay_finish_and_new_begin_without_repair(commands, damage):
    from core.studio_execution_commands import canonical, digest
    env = commands
    begin(env)
    with env.store.transaction(write=True) as conn:
        if damage in {"record_digest", "command_digest", "receipt_digest", "status", "json"}:
            column = "record_json" if damage == "json" else damage
            value = "ACCEPTED" if damage == "status" else "{"
            conn.execute(f"UPDATE studio_execution_commands SET {column}=? WHERE request_id=?", (value, key()))
        else:
            row = conn.execute("SELECT * FROM studio_execution_commands WHERE request_id=?", (key(),)).fetchone()
            payload = json.loads(row["record_json"])
            if damage == "boundary":
                payload["boundary"] = {"ownership": "tampered"}
            else:
                payload["record"]["input"]["feedback"] = "원문 위조"
                payload["record"]["receipt_digest"] = digest({k: v for k, v in payload["record"].items() if k != "receipt_digest"})
            conn.execute("UPDATE studio_execution_commands SET record_json=?,record_digest=?,receipt_digest=? WHERE request_id=?",
                (canonical(payload), digest(payload), payload["record"]["receipt_digest"], key()))
    before = stored_rows(env)
    for call in (lambda: get(env), lambda: env.store.list(**env.args), lambda: begin(env),
                 lambda: finish(env), lambda: begin(env, 2, "STOP")):
        failure(call, 503, "INTEGRITY")
        assert stored_rows(env) == before


@pytest.mark.parametrize("same_key", [True, False])
def test_atomic_begin_across_independent_store_locks_allows_one_new_execution(commands, same_key):
    from core.studio_execution_commands import CommandStoreError
    env = commands
    barrier = threading.Barrier(4)
    def submit(number):
        store = fresh_store(env)
        barrier.wait(timeout=5)
        try:
            return store.begin(**env.args, request=request(1 if same_key else number))
        except CommandStoreError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(submit, n) for n in range(1, 5)]
        results = [future.result(timeout=15) for future in futures]
    accepted = [value for value in results if isinstance(value, tuple)]
    assert sum(created for _, created in accepted) == 1 and len(stored_rows(env)) == 1
    assert len(accepted) == (4 if same_key else 1)
    for value in results:
        if isinstance(value, CommandStoreError):
            assert value.status_code == 409 and value.reason_code == "STUDIO_COMMAND_PROJECT_BUSY"
        else:
            assert value[0] == accepted[0][0]


def test_concurrent_different_finish_has_one_terminal_winner(commands):
    from core.studio_execution_commands import CommandStoreError
    env = commands
    begin(env)
    barrier = threading.Barrier(2)
    def complete(outcome):
        barrier.wait(timeout=5)
        try:
            return fresh_store(env).finish(**env.args, request_id=key(), outcome=outcome, result={"outcome": outcome})
        except CommandStoreError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(complete, outcome) for outcome in ("ACCEPTED", "REJECTED")]
        results = [future.result(timeout=15) for future in results]
    records = [value for value in results if isinstance(value, dict)]
    errors = [value for value in results if isinstance(value, CommandStoreError)]
    assert len(records) == len(errors) == 1 and get(env) == records[0]
    assert errors[0].status_code == 409 and errors[0].reason_code == "STUDIO_COMMAND_TERMINAL_CONFLICT"


@pytest.mark.parametrize("phase", ["begin", "finish"])
def test_sql_write_failure_rolls_back_and_does_not_fabricate_success(commands, monkeypatch, phase):
    env = commands
    if phase == "finish":
        begin(env)
    before = stored_rows(env)
    original = env.advisor._connect
    class Connection:
        def __init__(self):
            self.conn = original()
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def execute(self, sql, *args):
            prefix = "INSERT INTO studio_execution_commands" if phase == "begin" else "UPDATE studio_execution_commands"
            if sql.startswith(prefix):
                raise sqlite3.OperationalError("합성 DB 쓰기 실패")
            return self.conn.execute(sql, *args)
    monkeypatch.setattr(env.advisor, "_connect", Connection)
    failure(lambda: begin(env) if phase == "begin" else finish(env), 503, "STORAGE_UNAVAILABLE")
    assert stored_rows(env) == before


@pytest.mark.parametrize("column,value", [("status", "UNKNOWN"), ("receipt_digest", "stale"), ("record_digest", "stale")])
def test_finish_cas_checks_processing_and_both_fingerprints(commands, monkeypatch, column, value):
    env = commands
    begin(env)
    before = stored_rows(env)
    original = env.advisor._connect
    touched = []
    class Connection:
        def __init__(self):
            self.conn = original()
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def execute(self, sql, *args):
            if sql.startswith("UPDATE studio_execution_commands SET status=?,receipt_digest=?") and not touched:
                touched.append(True)
                self.conn.execute(f"UPDATE studio_execution_commands SET {column}=? WHERE request_id=?", (value, key()))
            return self.conn.execute(sql, *args)
    monkeypatch.setattr(env.advisor, "_connect", Connection)
    failure(lambda: finish(env), 409, "CONFLICT")
    assert touched == [True] and stored_rows(env) == before


@pytest.mark.parametrize("phase", ["begin", "finish"])
def test_commit_ack_loss_can_be_read_back_without_duplicate_command_or_finish(commands, monkeypatch, phase):
    env = commands
    if phase == "finish":
        begin(env)
    original = env.advisor._connect
    lost = []
    class Connection:
        def __init__(self):
            self.conn = original()
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def commit(self):
            self.conn.commit()
            if not lost:
                lost.append(True)
                raise sqlite3.OperationalError("합성 commit 완료 후 ACK 유실")
    monkeypatch.setattr(env.advisor, "_connect", Connection)
    failure(lambda: begin(env) if phase == "begin" else finish(env), 503, "STORAGE_UNAVAILABLE")
    assert lost == [True]
    recorded = get(env)
    before = stored_rows(env)
    assert recorded["status"] == ("PROCESSING" if phase == "begin" else "ACCEPTED")
    assert begin(env) == (recorded, False)
    if phase == "finish":
        assert finish(env) == recorded
    assert stored_rows(env) == before and len(before) == 1


def test_command_writes_leave_all_existing_advisor_tables_unchanged(commands):
    env = commands
    with env.store.transaction() as conn:
        conn.execute("""INSERT INTO consultations(consultation_id,scope,status,created_at,updated_at)
                        VALUES('synthetic-existing','project','open','2026-09-13','2026-09-13')""")
    def existing():
        with env.store.transaction() as conn:
            names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'studio_execution_commands' ORDER BY name")]
            return {name: [tuple(row) for row in conn.execute('SELECT * FROM "' + name.replace('"', '""') + '"')]
                    for name in names}
    before = existing()
    begin(env)
    finish(env, result={"execution_started": False})
    assert env.store.list(**env.args) == [get(env)]
    assert existing() == before


# ── [B5] 프로젝트 단위 명령(RELEASE·REPLAN) ────────────────────────────────────
def project_request(number=1, operation="RELEASE", **changes):
    from core.studio_execution_commands import PROJECT_TASK
    return {**dict(client_request_id=key(number), operation=operation, task_id=PROJECT_TASK, input={}), **changes}


@pytest.mark.parametrize("operation", ["RELEASE", "REPLAN"])
def test_project_scoped_commands_are_recorded_and_block_new_executions(commands, operation):
    """원키 없는 직접 POST 였던 두 경로를 같은 상태 기계로 닫는다."""
    from core.studio_execution_commands import EXECUTIONS, PROJECT_SCOPED, PROJECT_TASK
    assert operation in PROJECT_SCOPED and operation in EXECUTIONS
    value, created = commands.store.begin(**commands.args, request=project_request(1, operation))
    assert created is True and value["status"] == "PROCESSING" and value["operation"] == operation
    # 확인이 필요한 명령이 남아 있으면 새 실행을 막는다. 되돌릴 수 없는 재분할이 겹치지 않게 한다.
    failure(lambda: begin(commands, 2, "START"), 409, "PROJECT_BUSY")
    failure(lambda: commands.store.begin(**commands.args, request=project_request(3, operation)),
            409, "PROJECT_BUSY")
    done = finish(commands, 1, result={"execution_started": True})
    assert done["status"] == "ACCEPTED"
    assert get(commands, 1) == done


@pytest.mark.parametrize("operation", ["RELEASE", "REPLAN"])
def test_project_scoped_commands_refuse_task_level_input_or_arbitrary_task(commands, operation):
    failure(lambda: commands.store.begin(**commands.args,
            request=project_request(1, operation, input={"feedback": "임의 입력"})), 422, "INVALID")
    # 임의 task 를 기록에 남기면 「어느 작업에 적용됐나」가 실제 범위와 달라진다.
    failure(lambda: commands.store.begin(**commands.args,
            request=project_request(1, operation, task_id="TASK-01")), 422, "INVALID")


@pytest.mark.parametrize("operation", ["RELEASE", "REPLAN"])
def test_project_scoped_unknown_is_not_cleared_by_another_key(commands, operation):
    """응답 유실 뒤 새 키로 다시 눌러도 WBS 를 또 지우지 않는다."""
    commands.store.begin(**commands.args, request=project_request(1, operation))
    finish(commands, 1, outcome="UNKNOWN", result={"http_status": 503})
    failure(lambda: commands.store.begin(**commands.args, request=project_request(2, operation)),
            409, "PROJECT_BUSY")
    assert get(commands, 1)["status"] == "UNKNOWN"
