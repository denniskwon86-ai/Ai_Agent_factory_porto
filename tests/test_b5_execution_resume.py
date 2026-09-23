"""B5 정지 완료와 같은 체크포인트 재개의 격리 회귀. 실행은 메인 전용이다.

orchestrator/정지 파일은 실제 구현을 쓰고, 그래프·WBS·방송은 명시적 대역이다.
실제 LangGraph/LLM/운영 DB 실행 또는 권한 API 종단 증거로 취급하지 않는다.
"""
from __future__ import annotations

import asyncio
import copy
import json
import sqlite3
from types import SimpleNamespace

import pytest

PROJECT = "resume-project.test.invalid"
TASK = "PLANNING_1700000000"


class Engine:
    """읽기 판본과 스트림 입력만 관찰하는 메모리 그래프 대역."""
    interrupt_before_nodes = ()
    interrupt_after_nodes = ()

    def __init__(self, root):
        self.values = {"workspace_root": str(root), "current_sprint_task_id": TASK,
            "factory_mode": "PLANNING", "current_stage": "PLANNING",
            "template_id": "fixture-template", "config_fingerprint": "a" * 64,
            "terminal_status": "", "terminal_reason": "",
            "requirements": "원래 기획 본문", "generated_code": {"main": "기존 산출물"}}
        self.next = ("Planner",)
        self.config = {"configurable": {"thread_id": f"sprint_{PROJECT}__{TASK}", "checkpoint_id": "checkpoint-1"}}
        self.metadata = {"source": "loop", "step": 2, "writes": {"Other": {}}}
        self.tasks = ()
        self.updates = []
        self.streams = []
        self.release = None
        self.started = None
        self.read_hook = None

    async def aget_state(self, config):
        if self.read_hook:
            self.read_hook()
        return SimpleNamespace(values=copy.deepcopy(self.values), next=self.next,
            config=copy.deepcopy(self.config), metadata=copy.deepcopy(self.metadata), tasks=self.tasks)

    async def aupdate_state(self, config, updates):
        self.updates.append(copy.deepcopy(updates))
        self.values.update(copy.deepcopy(updates))
        self.config["configurable"]["checkpoint_id"] = "checkpoint-updated"

    async def astream(self, value, config):
        self.streams.append((copy.deepcopy(value), copy.deepcopy(config)))
        self.started.set()
        await self.release.wait()
        if False:
            yield {}


@pytest.fixture
def execution(monkeypatch, tmp_path):
    # 보호된 runner의 RUN 격리 아래 모듈 초기화를 먼저 마친다.
    # 이후 시험 본문에서는 대역 외의 런타임 DB 연결을 모두 차단한다.
    from core import async_orchestrator as ao, paths, studio_pause_state as pauses
    from core.enterprise_context.process_schema import ProcessError

    def no_database(*args, **kwargs):
        pytest.fail("정지/재개 단위 시험의 실제 DB 연결은 금지됩니다.")
    monkeypatch.setattr(sqlite3, "connect", no_database)
    monkeypatch.setattr(paths, "PROJECTS_DIR", str(tmp_path))
    root = tmp_path / PROJECT
    root.mkdir()
    for name in ("00_wbs_master_plan.json", "latest_state.json", "project_meta.json", "artifact.txt"):
        (root / name).write_text('{"original":"합성 원문"}', encoding="utf-8")
    (root / "project_meta.json").write_text('{"template_id":"fixture-template"}', encoding="utf-8")
    engine = Engine(root)
    h = SimpleNamespace(ao=ao, pauses=pauses, Error=ProcessError, root=root,
        engine=engine, orch=ao.AsyncFactoryOrchestrator(), runtime=[], broadcasts=[])

    async def bound(pid):
        assert pid == PROJECT
        return engine

    async def runtime(*args):
        h.runtime.append(args)
        return engine

    async def broadcast(*args):
        h.broadcasts.append(args)

    async def stream_end(*args):
        pass

    async def save_latest(*args):
        pytest.fail("일반 재개가 latest_state 원문을 다시 쓰면 안 됩니다.")

    class NoWBS:
        def __init__(self, *args, **kwargs):
            pytest.fail("기존 기획 재개가 WBS를 새로 만들거나 checkout하면 안 됩니다.")

    monkeypatch.setattr(ao.AsyncFactoryOrchestrator, "_bound_engine", lambda self, pid: bound(pid))
    monkeypatch.setattr(ao.AsyncFactoryOrchestrator, "_broadcast_stream_end", lambda self, *args: stream_end(*args))
    monkeypatch.setattr(ao.AsyncFactoryOrchestrator, "_save_latest_state", lambda self, *args: save_latest(*args))
    monkeypatch.setattr(ao, "get_runtime_app", runtime)
    monkeypatch.setattr(ao.factory_broadcaster, "broadcast", broadcast)
    monkeypatch.setattr(ao, "WBSManager", NoWBS)
    monkeypatch.setattr(ao.shutil, "move", lambda *args: pytest.fail("기존 기획 재개에서 아카이브 이동 금지"))
    return h


async def _worker(h, *, cleanup=None, entered=None):
    ready = asyncio.Event()
    async def body():
        ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            if entered:
                entered.set()
            if cleanup:
                await cleanup.wait()
    task = asyncio.create_task(body())
    h.orch._register_task(PROJECT, TASK, task)
    await ready.wait()
    return task


async def _pause(h):
    await _worker(h)
    assert await h.orch.pause_sprint(TASK, PROJECT) is True
    row = h.pauses.read(h.root, TASK)
    assert row["status"] == "PAUSED"
    return row


async def _resume_and_finish(h):
    h.engine.started, h.engine.release = asyncio.Event(), asyncio.Event()
    assert await h.orch.resume_existing(TASK, PROJECT) is True
    task = h.orch.active_tasks[h.ao._skey(PROJECT, TASK)]
    await h.engine.started.wait()
    h.engine.release.set()
    await task
    await asyncio.sleep(0)


def _files(h):
    return {p.name: p.read_bytes() for p in h.root.iterdir() if not p.name.startswith(".studio_pause")}


def test_pause_waits_for_actual_worker_cleanup_and_blocks_start(execution):
    h = execution
    async def scenario():
        cleanup, entered = asyncio.Event(), asyncio.Event()
        task = await _worker(h, cleanup=cleanup, entered=entered)
        pause = asyncio.create_task(h.orch.pause_sprint(TASK, PROJECT))
        await entered.wait()
        assert not pause.done() and not task.done()
        assert h.orch.active_tasks[h.ao._skey(PROJECT, TASK)] is task
        payload = {"terminal_status": "KEEP"}
        assert await h.orch.start_sprint(TASK, payload, str(h.root)) is False
        assert payload == {"terminal_status": "KEEP"}
        assert h.pauses.read(h.root, TASK) is None
        cleanup.set()
        assert await pause is True
        assert task.done() and not h.orch.active_tasks
        assert h.pauses.read(h.root, TASK)["status"] == "PAUSED"
    asyncio.run(scenario())


def test_cancelled_pause_request_keeps_reservation_until_worker_and_proof_finish(execution):
    h = execution
    async def scenario():
        cleanup, entered = asyncio.Event(), asyncio.Event()
        await _worker(h, cleanup=cleanup, entered=entered)
        pause = asyncio.create_task(h.orch.pause_sprint(TASK, PROJECT))
        await entered.wait()
        pause.cancel()
        await asyncio.sleep(0)
        pause.cancel()
        await asyncio.sleep(0)
        assert not pause.done()
        assert h.orch._studio_commands[PROJECT] == 1
        assert await h.orch.resume_existing(TASK, PROJECT) is False
        cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await pause
        assert not h.orch.active_tasks and not h.orch._studio_commands
        assert h.pauses.read(h.root, TASK)["status"] == "PAUSED"
    asyncio.run(scenario())


def test_old_done_callback_never_removes_new_same_id_task(execution):
    h = execution
    async def scenario():
        old = await _worker(h)
        newer = asyncio.create_task(asyncio.Event().wait())
        h.orch._register_task(PROJECT, TASK, newer)
        old.cancel()
        with pytest.raises(asyncio.CancelledError):
            await old
        await asyncio.sleep(0)
        assert h.orch.active_tasks[h.ao._skey(PROJECT, TASK)] is newer
        assert h.orch.task_projects[h.ao._skey(PROJECT, TASK)] == PROJECT
        newer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await newer
    asyncio.run(scenario())


def test_same_planning_resume_after_restart_preserves_task_checkpoint_body_and_files(execution):
    h = execution
    original, values = _files(h), copy.deepcopy(h.engine.values)
    async def scenario():
        await _pause(h)
        h.orch = h.ao.AsyncFactoryOrchestrator()
        assert (await h.orch.read_pause_state(TASK, PROJECT))["resumable"] is True
        await _resume_and_finish(h)
        assert h.engine.streams == [(None, {"configurable": {"thread_id": f"sprint_{PROJECT}__{TASK}"}})]
        assert h.runtime == [("fixture-template", "a" * 64), ("fixture-template", "a" * 64)]
        assert h.pauses.read(h.root, TASK)["status"] == "CONSUMED"
        assert not h.engine.updates and h.engine.values == values and _files(h) == original
        assert not (h.root / ".archive").exists()
        assert await h.orch.resume_existing(TASK, PROJECT) is False
    asyncio.run(scenario())


def test_current_failed_node_checkpoint_can_retry_without_reset_or_new_planning(execution):
    h = execution
    h.engine.tasks = (SimpleNamespace(name="Planner", error="합성 오류", interrupts=()),)
    original = _files(h)
    asyncio.run(_resume_and_finish(h))
    assert h.engine.streams[0][0] is None
    assert not h.engine.updates and _files(h) == original


def test_quota_mode_write_followed_by_read_failure_is_unknown_not_false(execution):
    h = execution
    h.engine.values.update(factory_mode="SUSPENDED_QUOTA", pre_suspend_mode="PLANNING")
    #: ⚠️ [대역 보정 2026-09-23 — CR §12-P1②] **기대(assert)는 바꾸지 않았다.**
    #:   동결은 checkpoint 와 정본을 **함께** 기록한 상태다(`_suspend_for_quota` 가 둘 다
    #:   쓴다). 이 fixture 의 `latest_state.json` 은 checkpoint 와 무관한 표식이라, 쿼터
    #:   재개가 이제 「동결 checkpoint 가 지금 정본과 이어져 있는가」를 모드 복구 **전에**
    #:   묻자 409(동결 사이 정본이 바뀌었다)로 먼저 막혔다 — 이 시험이 보려는 「모드를 쓴
    #:   뒤 읽기가 실패하면 503」까지 가지 못한 것이다. 이 시험 안에서만 동결 상태를
    #:   실제대로 맞춘다(fixture 를 공유하는 다른 시험은 건드리지 않는다).
    import json
    (h.root / "latest_state.json").write_text(json.dumps(h.engine.values, ensure_ascii=False),
                                              encoding="utf-8")
    def failed_read():
        if h.engine.updates:
            raise OSError("합성: 모드 변경 뒤 조회 실패")
    h.engine.read_hook = failed_read
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_from_suspend(TASK, PROJECT))
    assert exc.value.status_code == 503 and exc.value.reason_code == "STUDIO_QUOTA_RESUME_UNKNOWN"
    assert h.engine.updates and not h.engine.streams and not h.orch.active_tasks


def test_next_nodes_without_pause_or_failure_are_not_resume_evidence(execution):
    h = execution
    assert asyncio.run(h.orch.resume_existing(TASK, PROJECT)) is False
    assert not h.engine.streams and not h.runtime


def test_other_node_failure_is_not_current_task_retry_evidence(execution):
    h = execution
    h.engine.tasks = (SimpleNamespace(name="Other", error="다른 노드 오류", interrupts=()),)
    assert asyncio.run(h.orch.resume_existing(TASK, PROJECT)) is False
    assert not h.engine.streams


def test_project_cancellation_also_waits_before_registry_cleanup(execution):
    h = execution
    async def scenario():
        cleanup, entered = asyncio.Event(), asyncio.Event()
        task = await _worker(h, cleanup=cleanup, entered=entered)
        cancellation = asyncio.create_task(h.orch.cancel_project(PROJECT))
        await entered.wait()
        assert not cancellation.done() and not task.done()
        assert h.orch.active_tasks[h.ao._skey(PROJECT, TASK)] is task
        cleanup.set()
        assert await cancellation == 1
        assert not h.orch.active_tasks
    asyncio.run(scenario())


def test_checkpoint_change_after_pause_file_lock_never_launches(execution, monkeypatch):
    h = execution
    consume = h.pauses.consume
    def change_after_consume(root, row):
        result = consume(root, row)
        h.engine.config["configurable"]["checkpoint_id"] = "changed-after-lock"
        return result
    monkeypatch.setattr(h.pauses, "consume", change_after_consume)
    async def scenario():
        await _pause(h)
        with pytest.raises(h.Error) as exc:
            await h.orch.resume_existing(TASK, PROJECT)
        assert exc.value.status_code == 503
        assert exc.value.reason_code == "STUDIO_PAUSE_OUTCOME_UNKNOWN"
        assert not h.engine.streams and h.pauses.read(h.root, TASK)["status"] == "CONSUMED"
    asyncio.run(scenario())


@pytest.mark.parametrize("kind,code", [
    ("empty", "CHECKPOINT_REQUIRED"), ("finished", "FINISHED"), ("terminal", "TERMINAL"),
    ("quota", "QUOTA_REQUIRED"), ("contract", "REVIEW_REQUIRED"), ("questions", "REVIEW_REQUIRED"),
    ("approval", "REVIEW_REQUIRED"), ("interrupt", "HOTL_REQUIRED"),
    ("before", "HOTL_REQUIRED"), ("after", "HOTL_REQUIRED"),
    ("root", "CONTEXT_CONFLICT"), ("task", "CONTEXT_CONFLICT"), ("thread", "CONTEXT_CONFLICT"),
])
def test_resume_does_not_bypass_existing_boundaries(execution, kind, code):
    h = execution
    async def scenario():
        await _pause(h)
        if kind == "empty": h.engine.values = {}
        elif kind == "finished": h.engine.next = ()
        elif kind == "terminal": h.engine.values["terminal_status"] = "FAILED"
        elif kind == "quota": h.engine.values["factory_mode"] = "SUSPENDED_QUOTA"
        elif kind == "contract": h.engine.values["current_stage"] = "CONTRACT_REVIEW"
        elif kind == "questions": h.engine.values["current_stage"] = "CLARIFICATION"
        elif kind == "approval": h.engine.values["app_runtime_contract_status"] = "APPROVAL_PENDING"
        elif kind == "interrupt": h.engine.tasks = (SimpleNamespace(error=None, interrupts=("review",)),)
        elif kind == "before": h.engine.interrupt_before_nodes = ("Planner",)
        elif kind == "after": h.engine.interrupt_after_nodes = ("Other",)
        elif kind == "root": h.engine.values["workspace_root"] = str(h.root.parent / "other.invalid")
        elif kind == "task": h.engine.values["current_sprint_task_id"] = "OTHER"
        elif kind == "thread": h.engine.config["configurable"]["thread_id"] = "other-thread"
        with pytest.raises(h.Error) as exc:
            await h.orch.resume_existing(TASK, PROJECT)
        assert exc.value.status_code == 409
        assert exc.value.reason_code == "STUDIO_PAUSE_" + code
        assert not h.engine.streams and not h.engine.updates
    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["requirements", "checkpoint_id"])
def test_changed_pause_proof_is_not_reusable(execution, field):
    h = execution
    async def scenario():
        await _pause(h)
        if field == "checkpoint_id":
            h.engine.config["configurable"][field] = "checkpoint-2"
        else:
            h.engine.values[field] = "다른 본문"
        assert (await h.orch.read_pause_state(TASK, PROJECT))["resumable"] is False
        with pytest.raises(h.Error) as exc:
            await h.orch.resume_existing(TASK, PROJECT)
        assert exc.value.reason_code == "STUDIO_PAUSE_CONFLICT"
        assert not h.engine.streams
    asyncio.run(scenario())


@pytest.mark.parametrize("raw", ["{broken", '{"schema_version":1,"schema_version":1,"records":{}}', '{"schema_version":2,"records":{}}'])
def test_corrupt_pause_file_fails_closed_without_runtime_or_repair(execution, raw):
    h = execution
    path = h.root / h.pauses.FILENAME
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_existing(TASK, PROJECT))
    assert exc.value.status_code == 503
    assert path.read_text(encoding="utf-8") == raw and not h.runtime


def test_pause_read_without_marker_creates_no_file_or_lock(execution):
    h = execution
    before = _files(h)
    assert asyncio.run(h.orch.read_pause_state(TASK, PROJECT)) == {
        "status": "NOT_PAUSED", "resumable": False, "reason_code": "STUDIO_PAUSE_EVIDENCE_REQUIRED"}
    assert _files(h) == before and not list(h.root.glob(".studio_pause*"))


def test_pause_cas_and_failed_replace_preserve_existing_proof(execution, monkeypatch):
    h = execution
    row = asyncio.run(_pause(h))
    path = h.root / h.pauses.FILENAME
    before = path.read_bytes()
    def fail_replace(*args):
        raise OSError("합성 원자 교체 실패")
    with monkeypatch.context() as patch:
        patch.setattr(h.pauses.os, "replace", fail_replace)
        with pytest.raises(h.Error) as exc:
            h.pauses.consume(h.root, row)
        assert exc.value.status_code == 503
    assert path.read_bytes() == before
    assert not list(h.root.glob(".studio_pause_*.tmp"))
    h.pauses.consume(h.root, row)
    with pytest.raises(h.Error) as exc:
        h.pauses.consume(h.root, row)
    assert exc.value.status_code == 409


def test_explicit_pause_is_not_hotl_and_cannot_use_hotl_response(execution):
    h = execution
    async def scenario():
        await _pause(h)
        assert await h.orch.is_hotl_pending(TASK, PROJECT) is False
        context = await h.orch.read_hotl_context(TASK, PROJECT)
        assert context["available"] is False and context["reason_code"] == "STUDIO_EXPLICIT_PAUSE"
        assert await h.orch.resume_hotl(TASK, "잘못된 승인", PROJECT) is False
        assert not h.engine.updates and not h.engine.streams
    asyncio.run(scenario())


@pytest.mark.parametrize("marker", [False, True])
def test_legacy_start_same_planning_checkpoint_never_archives_even_without_marker(execution, marker):
    h = execution
    original = _files(h)
    async def scenario():
        if marker:
            await _pause(h)
        payload = {"terminal_status": "KEEP", "requirements": "새 본문"}
        assert await h.orch.start_sprint(TASK, payload, str(h.root)) is False
        assert payload == {"terminal_status": "KEEP", "requirements": "새 본문"}
        assert _files(h) == original and not h.engine.streams
    asyncio.run(scenario())


def test_pause_on_actual_resume_stream_records_cancellation_after_done(execution):
    h = execution
    async def scenario():
        h.engine.started, h.engine.release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(h.orch._resume_stream(
            {"configurable": {"thread_id": f"sprint_{PROJECT}__{TASK}"}}, TASK,
            str(h.root), "fixture-template", "a" * 64))
        h.orch._register_task(PROJECT, TASK, task)
        await h.engine.started.wait()
        assert await h.orch.pause_sprint(TASK, PROJECT) is True
        assert task.done() and task._studio_cancelled
        assert h.pauses.read(h.root, TASK)["status"] == "PAUSED"
    asyncio.run(scenario())


@pytest.mark.parametrize("flag", ["_studio_stream_completed", "_studio_at_hotl"])
def test_pause_racing_normal_or_hotl_exit_cannot_mint_manual_resume_proof(execution, flag):
    h = execution
    async def scenario():
        task = await _worker(h)
        setattr(task, flag, True)
        assert await h.orch.pause_sprint(TASK, PROJECT) is False
        assert task.done() and h.pauses.read(h.root, TASK) is None
    asyncio.run(scenario())
