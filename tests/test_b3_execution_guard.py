"""B3 실행 예약과 계약 복구의 독립 메모리 회귀. 실행은 main 전용이다.

실제 AsyncFactoryOrchestrator 인스턴스와 guard/복구 메서드를 호출한다.
결속 엔진·WBS·방송·실행 루프는 명시적인 앱 실행 대역이다. 실제 DB 연결,
LLM 호출, 파일 생성, 인증·원장 검증의 종단 증거로 취급하지 않는다.
"""
from __future__ import annotations

import asyncio
import copy
import sqlite3
import threading
from types import SimpleNamespace

import pytest


PROJECT = "guard-project.test.invalid"
OTHER = "other-project.test.invalid"
TASK = "TASK-UNIT"
FINGERPRINT = "a" * 64
REQUEST = "review-unit.test.invalid"


def _state():
    return {
        "app_runtime_contract_fingerprint": FINGERPRINT,
        "approved_contract_fingerprint": "",
        "app_runtime_contract_status": "APPROVAL_PENDING",
        "contract_review_request_event_id": REQUEST,
        "runtime_document_version": "2.0",
        "process_context": {"schema_version": 1, "context_key": {
            "tenant_id": "unit-tenant", "context_root_id": "unit-root",
            "entity_mode": "REAL", "scope_node_id": "unit-scope"},
            "process_semantic_fingerprint": "b" * 64},
        "approved_blueprint_revision_id": "blueprint-unit",
        "approved_blueprint_digest": "c" * 64,
        "bootstrap_operation_id": "bootstrap-unit",
        "unrelated_payload": {"keep": True},
    }


class FakeBoundEngine:
    """메모리 상태만 읽고 쓰는 앱 실행 대역. 실제 그래프나 체크포인터가 아니다."""

    def __init__(self, values):
        self.values = copy.deepcopy(values)
        self.reads = []
        self.writes = []
        self.fail = ""
        self.discard_updates = False
        self.after_update = None

    async def aget_state(self, config):
        self.reads.append(copy.deepcopy(config))
        if self.fail == "read" or (self.fail == "readback" and self.writes):
            raise OSError("합성 엔진 읽기 실패")
        return SimpleNamespace(values=copy.deepcopy(self.values))

    async def aupdate_state(self, config, updates):
        if self.fail == "write":
            raise OSError("합성 엔진 쓰기 실패")
        self.writes.append((copy.deepcopy(config), copy.deepcopy(updates)))
        if not self.discard_updates:
            self.values.update(copy.deepcopy(updates))
        if self.after_update is not None:
            self.after_update(self.values)


@pytest.fixture
def guarded(monkeypatch):
    def no_database(*_args, **_kwargs):
        pytest.fail("실행 guard 단위 회귀에서 실제 DB 연결은 금지됩니다.")
    monkeypatch.setattr(sqlite3, "connect", no_database)

    from core import async_orchestrator as ao, studio_execution_guard as guard
    from core.enterprise_context.process_schema import ProcessError

    orch = ao.AsyncFactoryOrchestrator()
    h = SimpleNamespace(ao=ao, guard=guard, orch=orch, Error=ProcessError,
        engine=FakeBoundEngine(_state()), runtime_engine=FakeBoundEngine(None),
        bound_calls=[], runtime_calls=[], wbs_calls=[], broadcasts=[], loop_calls=[])

    async def bound(project_id):
        h.bound_calls.append(project_id)
        return h.engine

    async def runtime(*args, **kwargs):
        h.runtime_calls.append((args, kwargs))
        return h.runtime_engine

    class FakeWBS:
        def __init__(self, *, workspace_root):
            self.root = workspace_root

        def checkout_task(self, task_id):
            h.wbs_calls.append((self.root, task_id))

    async def broadcast(*args, **kwargs):
        h.broadcasts.append((args, kwargs))

    async def loop(*args, **kwargs):
        h.loop_calls.append((args, kwargs))

    monkeypatch.setattr(orch, "_bound_engine", bound)
    monkeypatch.setattr(ao, "get_runtime_app", runtime)
    monkeypatch.setattr(ao, "WBSManager", FakeWBS)
    monkeypatch.setattr(ao.factory_broadcaster, "broadcast", broadcast)
    monkeypatch.setattr(orch, "_run_sprint_loop", loop)
    return h


def _busy(h, call):
    with pytest.raises(h.Error) as exc:
        with call():
            pytest.fail("복구 예약이 중복 허용되었습니다.")
    assert exc.value.reason_code == "CONTRACT_RECONCILE_BUSY"
    assert exc.value.status_code == 409


def _clean(h):
    assert h.orch._studio_commands == {}
    assert not h.guard.is_reconciling(h.orch, PROJECT)


async def _service(h, service, project_id, payload=None):
    if service == "start_sprint":
        return await h.orch.start_sprint(TASK, payload if payload is not None else {},
                                         f"./unused/{project_id}/")
    if service == "resume_hotl":
        return await h.orch.resume_hotl(TASK, None, project_id=project_id)
    return await h.orch.resume_from_suspend(task_id=TASK, project_id=project_id)


async def _apply(h, *, expected=None, fingerprint=FINGERPRINT, request_event_id=REQUEST):
    with h.guard.reconcile(h.orch, PROJECT):
        return await h.orch.apply_reconciled_contract_decision(
            TASK, PROJECT, fingerprint=fingerprint, request_event_id=request_event_id,
            expected_state=copy.deepcopy(_state() if expected is None else expected))


@pytest.mark.parametrize("index", ["project_map", "composite_key"])
def test_same_project_active_task_blocks_reconcile_by_both_indexes(guarded, index):
    h = guarded
    key = "opaque-task" if index == "project_map" else f"{PROJECT}__{TASK}"
    h.orch.active_tasks[key] = SimpleNamespace(done=lambda: False)
    if index == "project_map":
        h.orch.task_projects[key] = PROJECT
    _busy(h, lambda: h.guard.reconcile(h.orch, PROJECT))
    with h.guard.reconcile(h.orch, OTHER):
        assert h.guard.is_reconciling(h.orch, OTHER)
    h.orch.active_tasks[key] = SimpleNamespace(done=lambda: True)
    with h.guard.reconcile(h.orch, PROJECT):
        assert h.guard.is_reconciling(h.orch, PROJECT)


def test_nested_commands_and_reconcile_exceptions_always_release_reservation(guarded):
    h = guarded
    with h.guard.command(h.orch, PROJECT):
        with pytest.raises(RuntimeError):
            with h.guard.command(h.orch, PROJECT):
                assert h.orch._studio_commands[PROJECT] == 2
                raise RuntimeError("내부 명령 실패")
        assert h.orch._studio_commands[PROJECT] == 1
        _busy(h, lambda: h.guard.reconcile(h.orch, PROJECT))
    _clean(h)
    with pytest.raises(RuntimeError):
        with h.guard.reconcile(h.orch, PROJECT):
            _busy(h, lambda: h.guard.reconcile(h.orch, PROJECT))
            with pytest.raises(h.Error) as exc:
                with h.guard.command(h.orch, PROJECT):
                    pytest.fail("복구 중 명령 예약 허용")
            assert exc.value.reason_code == "CONTRACT_RECONCILE_BUSY"
            raise RuntimeError("복구 실패")
    _clean(h)
    with h.guard.command(h.orch, PROJECT):
        assert h.orch._studio_commands[PROJECT] == 1
    _clean(h)


@pytest.mark.parametrize("service", ["start_sprint", "resume_hotl", "resume_from_suspend"])
def test_three_real_services_return_false_before_body_while_reconciling(guarded, service):
    h = guarded
    payload = {"terminal_status": "KEEP", "terminal_reason": "KEEP"}
    async def scenario():
        with h.guard.reconcile(h.orch, PROJECT):
            assert await _service(h, service, PROJECT, payload) is False
            assert h.orch._studio_commands == {}
        assert h.runtime_calls == h.wbs_calls == h.broadcasts == h.loop_calls == []
        assert payload == {"terminal_status": "KEEP", "terminal_reason": "KEEP"}
        assert h.orch.active_tasks == {} and h.orch.task_projects == {}
        _clean(h)
    asyncio.run(scenario())


@pytest.mark.parametrize("service", ["start_sprint", "resume_hotl", "resume_from_suspend"])
def test_recovery_of_other_project_does_not_block_actual_service_entry(guarded, service):
    h = guarded
    async def scenario():
        with h.guard.reconcile(h.orch, PROJECT):
            result = await _service(h, service, OTHER)
            if service == "start_sprint":
                assert result is True
                assert len(h.wbs_calls) == 1 and len(h.broadcasts) == 1
                tasks = list(h.orch.active_tasks.values())
                assert len(tasks) == 1
                await asyncio.gather(*tasks)
                await asyncio.sleep(0)
                assert len(h.loop_calls) == 1
            else:
                # 메서드 본문에는 진입했다. 대역의 상태가 없어서 실행 재개만 False다.
                assert result is False
                assert len(h.runtime_calls) == 1 and len(h.runtime_engine.reads) == 1
            assert h.orch._studio_commands == {}
        assert h.orch.active_tasks == {} and h.orch.task_projects == {}
        _clean(h)
    asyncio.run(scenario())


@pytest.mark.parametrize("finish", ["return", "error", "cancel"])
def test_actual_command_await_gap_blocks_recovery_and_finally_cleans(guarded, monkeypatch, finish):
    h = guarded
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting_engine(*_args, **_kwargs):
            entered.set()
            await release.wait()
            if finish == "error":
                raise RuntimeError("합성 엔진 준비 실패")
            return FakeBoundEngine(None)
        monkeypatch.setattr(h.ao, "get_runtime_app", waiting_engine)
        task = asyncio.create_task(h.orch.resume_hotl(TASK, None, PROJECT))
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            assert h.orch.active_tasks == {}
            assert h.orch._studio_commands[PROJECT] == 1
            _busy(h, lambda: h.guard.reconcile(h.orch, PROJECT))
            with h.guard.reconcile(h.orch, OTHER):
                assert h.guard.is_reconciling(h.orch, OTHER)
            if finish == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                release.set()
                if finish == "error":
                    with pytest.raises(RuntimeError, match="준비 실패"):
                        await task
                else:
                    assert await task is False
        finally:
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        _clean(h)
        with h.guard.reconcile(h.orch, PROJECT):
            assert h.guard.is_reconciling(h.orch, PROJECT)
    asyncio.run(scenario())


def test_read_reconcile_uses_bound_project_and_exact_thread_without_starting_engine(guarded):
    h = guarded
    result = asyncio.run(h.orch.read_reconcile_state(TASK, PROJECT))
    assert result == _state()
    assert h.bound_calls == [PROJECT]
    assert h.engine.reads == [{"configurable": {"thread_id": f"sprint_{PROJECT}__{TASK}"}}]
    assert h.engine.writes == [] and h.runtime_calls == h.loop_calls == []
    result["process_context"]["context_key"]["scope_node_id"] = "caller-change"
    assert h.engine.values == _state()


def test_apply_without_recovery_reservation_never_reads_or_writes(guarded):
    h = guarded
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.apply_reconciled_contract_decision(TASK, PROJECT,
            fingerprint=FINGERPRINT, request_event_id=REQUEST, expected_state=_state()))
    assert exc.value.reason_code == "CONTRACT_RECONCILE_REQUIRED"
    assert h.bound_calls == [] and h.engine.reads == h.engine.writes == []


def test_apply_readback_and_same_success_retry_write_only_once(guarded):
    h = guarded
    async def scenario():
        expected = await h.orch.read_reconcile_state(TASK, PROJECT)
        assert await _apply(h, expected=expected) is True
        updates = {"approved_contract_fingerprint": FINGERPRINT,
                   "app_runtime_contract_status": "APPROVED", "contract_review_request_event_id": ""}
        config = {"configurable": {"thread_id": f"sprint_{PROJECT}__{TASK}"}}
        assert h.engine.writes == [(config, updates)]
        assert h.engine.values == {**expected, **updates}
        # CAS 비교용 현재값을 다시 읽는다. 같은 사건·지문 재호출은 추가 쓰기가 없다.
        current = await h.orch.read_reconcile_state(TASK, PROJECT)
        before_reads = len(h.engine.reads)
        assert await _apply(h, expected=current) is True
        assert len(h.engine.reads) == before_reads + 1
        assert h.engine.writes == [(config, updates)]
        assert all(project_id == PROJECT for project_id in h.bound_calls)
        assert h.runtime_calls == h.loop_calls == [] and h.orch.active_tasks == {}
        _clean(h)
    asyncio.run(scenario())


@pytest.mark.parametrize("argument,value", [("fingerprint", "d" * 64), ("request_event_id", "different-event")])
def test_different_fingerprint_or_review_request_never_writes(guarded, argument, value):
    h = guarded
    with pytest.raises(h.Error) as exc:
        asyncio.run(_apply(h, **{argument: value}))
    assert exc.value.reason_code == "CONTRACT_RECONCILE_CONFLICT" and exc.value.status_code == 409
    assert h.engine.writes == []
    _clean(h)


@pytest.mark.parametrize("field", ["runtime_document_version", "process_context",
    "approved_blueprint_revision_id", "approved_blueprint_digest", "bootstrap_operation_id",
    "contract_review_request_event_id"])
def test_fixed_context_cas_rejects_changed_state_without_writes(guarded, field):
    h = guarded
    expected = _state()
    if field == "process_context":
        h.engine.values[field]["context_key"]["scope_node_id"] = "other-scope"
    elif field == "contract_review_request_event_id":
        # 이미 비워진 현재 상태와 원래 pending 상태를 같다고 간주하지 않는다.
        h.engine.values[field] = ""
    else:
        h.engine.values[field] = "changed"
    with pytest.raises(h.Error) as exc:
        asyncio.run(_apply(h, expected=expected))
    assert exc.value.reason_code == "CONTRACT_RECONCILE_CONFLICT"
    assert h.engine.writes == []
    _clean(h)


@pytest.mark.parametrize("damage", ["discard_update", "context_drift"])
def test_readback_must_confirm_projection_and_same_fixed_context(guarded, damage):
    h = guarded
    if damage == "discard_update":
        h.engine.discard_updates = True
    else:
        h.engine.after_update = lambda values: values["process_context"]["context_key"].update(scope_node_id="drift")
    assert asyncio.run(_apply(h)) is False
    assert len(h.engine.writes) == 1 and len(h.engine.reads) == 2
    assert h.runtime_calls == h.loop_calls == [] and h.orch.active_tasks == {}
    _clean(h)


@pytest.mark.parametrize("values,status,reason", [
    (None, 404, "CONTRACT_CHECKPOINT_NOT_FOUND"),
    (["잘못된 상태 형태"], 503, "CONTRACT_CHECKPOINT_UNAVAILABLE"),
])
def test_missing_or_invalid_checkpoint_never_becomes_empty_success(guarded, values, status, reason):
    h = guarded
    h.engine.values = values
    with pytest.raises(h.Error) as exc:
        asyncio.run(_apply(h))
    assert exc.value.status_code == status and exc.value.reason_code == reason
    assert h.engine.writes == []
    _clean(h)


@pytest.mark.parametrize("stage", ["read", "write", "readback"])
def test_engine_failures_are_503_and_release_recovery_reservation(guarded, stage):
    h = guarded
    h.engine.fail = stage
    with pytest.raises(h.Error) as exc:
        asyncio.run(_apply(h))
    assert exc.value.reason_code == "CONTRACT_CHECKPOINT_UNAVAILABLE" and exc.value.status_code == 503
    assert len(h.engine.writes) == (1 if stage == "readback" else 0)
    assert h.runtime_calls == h.loop_calls == [] and h.orch.active_tasks == {}
    _clean(h)

class _ThreadFailure(RuntimeError):
    """합성 worker 예외. 실제 파일·DB 작업은 하지 않는다."""


class _PausedThreadWorker:
    """실제 to_thread에서 Event로 잠시 멈추는 대역. 모든 대기는 최대 5초다."""

    def __init__(self, loop, *, fail=False):
        self.loop = loop
        self.entered = asyncio.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.fail = fail
        self.error = _ThreadFailure("합성 stamp worker 실패")
        self.trace = []
        self.thread_id = None

    def run(self):
        self.thread_id = threading.get_ident()
        self.trace.append("worker_started")
        self.loop.call_soon_threadsafe(self.entered.set)
        try:
            if not self.release.wait(timeout=5):
                raise AssertionError("worker 해제 Event의 5초 제한 초과")
            if self.fail:
                raise self.error
            return "worker-complete"
        finally:
            self.trace.append("worker_finished")
            self.finished.set()


async def _guarded_thread_operation(h, worker, reservation):
    """실제 API 대신 전체 operation의 예약 범위만 재현한다."""
    reserve = h.guard.reconcile if reservation == "reconcile" else h.guard.command
    with reserve(h.orch, PROJECT):
        try:
            result = await asyncio.to_thread(worker.run)
            worker.trace.append("operation_after_worker")
            return result
        finally:
            worker.trace.append("operation_finally")


async def _drain_thread_request(caller, worker):
    """회귀가 실패해도 worker를 풀고 요청을 회수한다. 별도 daemon은 만들지 않는다."""
    worker.release.set()
    await asyncio.wait_for(asyncio.gather(caller, return_exceptions=True), timeout=5)


@pytest.mark.parametrize("reservation,worker_fails", [
    ("reconcile", False), ("command", False), ("reconcile", True),
])
def test_repeated_cancellation_waits_for_real_thread_and_keeps_guard(guarded, reservation, worker_fails):
    h = guarded
    async def scenario():
        loop = asyncio.get_running_loop()
        worker = _PausedThreadWorker(loop, fail=worker_fails)
        caller = asyncio.create_task(h.guard.finish_before_cancel(
            _guarded_thread_operation(h, worker, reservation)))
        try:
            await asyncio.wait_for(worker.entered.wait(), timeout=2)
            assert worker.thread_id != threading.get_ident()
            # 취소를 두 차례 각각 전달한다. worker가 멈춘 동안 guard가 유지되어야 한다.
            for _ in range(2):
                assert caller.cancel()
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                assert not caller.done()
                assert not worker.finished.is_set()
                assert worker.trace == ["worker_started"]
                _busy(h, lambda: h.guard.reconcile(h.orch, PROJECT))
                if reservation == "reconcile":
                    assert h.guard.is_reconciling(h.orch, PROJECT)
                    for service in ("start_sprint", "resume_hotl", "resume_from_suspend"):
                        assert await _service(h, service, PROJECT) is False
                    assert h.runtime_calls == h.wbs_calls == h.broadcasts == h.loop_calls == []
                else:
                    assert h.orch._studio_commands[PROJECT] == 1
                with h.guard.reconcile(h.orch, OTHER):
                    assert h.guard.is_reconciling(h.orch, OTHER)

            worker.release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(caller), timeout=5)
            worker.trace.append("caller_cancelled")
            assert caller.cancelled() and worker.finished.is_set()
            expected = ["worker_started", "worker_finished"]
            if not worker_fails:
                expected.append("operation_after_worker")
            assert worker.trace == expected + ["operation_finally", "caller_cancelled"]
            assert h.orch.active_tasks == {} and h.orch.task_projects == {}
            _clean(h)
            with h.guard.reconcile(h.orch, PROJECT):
                assert h.guard.is_reconciling(h.orch, PROJECT)
        finally:
            await _drain_thread_request(caller, worker)
    asyncio.run(scenario())


@pytest.mark.parametrize("worker_fails", [False, True])
def test_uncancelled_thread_result_or_original_error_releases_guard(guarded, worker_fails):
    h = guarded
    async def scenario():
        worker = _PausedThreadWorker(asyncio.get_running_loop(), fail=worker_fails)
        caller = asyncio.create_task(h.guard.finish_before_cancel(
            _guarded_thread_operation(h, worker, "reconcile")))
        try:
            await asyncio.wait_for(worker.entered.wait(), timeout=2)
            assert h.guard.is_reconciling(h.orch, PROJECT)
            assert worker.thread_id != threading.get_ident() and not caller.done()
            worker.release.set()
            if worker_fails:
                with pytest.raises(_ThreadFailure) as exc:
                    await asyncio.wait_for(asyncio.shield(caller), timeout=5)
                assert exc.value is worker.error
            else:
                assert await asyncio.wait_for(asyncio.shield(caller), timeout=5) == "worker-complete"
            assert caller.done() and not caller.cancelled()
            assert worker.finished.is_set() and worker.trace[-1] == "operation_finally"
            _clean(h)
            with h.guard.command(h.orch, PROJECT):
                assert h.orch._studio_commands[PROJECT] == 1
            _clean(h)
        finally:
            await _drain_thread_request(caller, worker)
    asyncio.run(scenario())
