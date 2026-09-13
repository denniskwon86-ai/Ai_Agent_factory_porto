"""실제 오케스트레이터의 HOTL 조회·재개 회귀. 실행은 main 전용이다.

그래프 공급자·체크포인터·persona·품질 기록·stream은 명시적인 메모리 대역이다.
실제 DB·LLM·파일 쓰기를 실행하지 않으며 API 인증의 종단 증거로 취급하지 않는다.
"""
from __future__ import annotations

import asyncio
import copy
import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest


PROJECT = "hotl-resume.test.invalid"
TASK = "TASK-HOTL"
TEMPLATE = "template-memory"
CONFIG_FP = "config-memory"
_FIXED = ("runtime_document_version", "process_context", "approved_blueprint_revision_id",
          "approved_blueprint_digest", "bootstrap_operation_id")


class MemoryEngine:
    """최초·결속·최종 조회를 분리하는 대역. 쓰면 합성 체크포인트 회차만 증가한다."""

    def __init__(self, snapshot):
        self.snapshot = copy.deepcopy(snapshot)
        self.reads = []
        self.writes = []
        self.write_attempts = []
        self.read_error = None
        self.write_error = None
        self.read_entered = None
        self.read_release = None

    async def aget_state(self, config):
        self.reads.append(copy.deepcopy(config))
        if self.read_entered is not None:
            self.read_entered.set()
            await asyncio.wait_for(self.read_release.wait(), timeout=5)
        if self.read_error is not None:
            raise self.read_error
        return copy.deepcopy(self.snapshot)

    async def aupdate_state(self, config, updates):
        self.write_attempts.append((copy.deepcopy(config), copy.deepcopy(updates)))
        if self.write_error is not None:
            raise self.write_error
        self.writes.append((copy.deepcopy(config), copy.deepcopy(updates)))
        self.snapshot.values.update(copy.deepcopy(updates))
        self.snapshot.config["configurable"]["checkpoint_id"] = f"memory-written-{len(self.writes)}"


def _stub_module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    parent, _, child = name.rpartition(".")
    if parent in sys.modules:
        monkeypatch.setattr(sys.modules[parent], child, module, raising=False)


@pytest.fixture
def hotl(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        pytest.fail("HOTL 메모리 회귀에서 운영 DB·파일·WBS·LLM 진입은 금지됩니다.")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    h = SimpleNamespace(bound_calls=[], runtime_calls=[], persona_calls=[], quality_calls=[],
                        stream_calls=[], stream_entered=None, stream_release=None,
                        bound_error=None, final_engine_error=None, persona_error=None)

    async def runtime(*args, **kwargs):
        h.runtime_calls.append((args, kwargs))
        if (args or kwargs) and h.final_engine_error is not None:
            raise h.final_engine_error
        return h.initial if not args and not kwargs else h.final

    def record_interaction(*args, **kwargs):
        h.persona_calls.append((args, kwargs))
        if h.persona_error is not None:
            raise h.persona_error

    def record_human_decision(*args, **kwargs):
        h.quality_calls.append((args, kwargs))

    persona = SimpleNamespace(record_interaction=record_interaction)
    broadcaster = SimpleNamespace(broadcast=forbidden)
    # 실제 모듈의 최초 import도 persona 싱글턴이나 그래프를 생성하지 않도록 차단한다.
    _stub_module(monkeypatch, "core.agent_graph", get_runtime_app=runtime)
    _stub_module(monkeypatch, "core.persona_learner", persona_learner=persona)
    _stub_module(monkeypatch, "core.llm_gateway", QuotaExhaustedException=type("MemoryQuotaError", (Exception,), {}))
    _stub_module(monkeypatch, "core.broadcaster", factory_broadcaster=broadcaster)
    _stub_module(monkeypatch, "nodes.utils.wbs_manager", WBSManager=forbidden)
    _stub_module(monkeypatch, "core.quality_telemetry", record_human_decision=record_human_decision,
                 StateRef=lambda state, **kwargs: SimpleNamespace(state=copy.deepcopy(state), **kwargs))

    already_loaded = "core.async_orchestrator" in sys.modules
    from langgraph.types import StateSnapshot
    from core import paths
    from core import async_orchestrator as ao, studio_execution_guard as guard
    from core.enterprise_context.process_schema import ProcessError
    from core.studio_hotl_context import hotl_context

    # 공통 경로 함수의 루트만 격리한다. 합성 프로젝트 디렉터리는 생성하지 않는다.
    monkeypatch.setattr(paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    h.workspace = paths.workspace_path(PROJECT)
    values = {
        "workspace_root": h.workspace, "template_id": TEMPLATE,
        "config_fingerprint": CONFIG_FP, "runtime_document_version": "2.0",
        "current_stage": "CLARIFICATION", "factory_mode": "PLANNING",
        "clarification_questions": [{"id": "Q1", "question": "합성 기밀 질문", "options": [
            {"label": "첫째", "recommended": True}, {"label": "둘째", "recommended": False}]}],
        "human_feedback_queue": [], "needs_revision": True,
        "process_context": {"schema_version": 1, "context_key": {
            "tenant_id": "memory-tenant", "context_root_id": "memory-root",
            "scope_node_id": "memory-scope", "entity_mode": "REAL"}},
        "approved_blueprint_revision_id": "memory-blueprint",
        "approved_blueprint_digest": "b" * 64, "bootstrap_operation_id": "memory-operation",
    }
    snapshot = StateSnapshot(values=values, next=("RFP_Analyst",),
        config={"configurable": {"checkpoint_id": "memory-round-01"}},
        metadata=None, created_at=None, parent_config=None, tasks=(), interrupts=())
    h.ao, h.guard, h.Error, h.context = ao, guard, ProcessError, hotl_context
    h.orch = ao.AsyncFactoryOrchestrator()
    h.initial, h.bound, h.final = (MemoryEngine(snapshot) for _ in range(3))

    async def bound(project_id):
        h.bound_calls.append(project_id)
        if h.bound_error is not None:
            raise h.bound_error
        return h.bound

    async def resume_stream(*args, **kwargs):
        # 실제 그래프 대신 예약된 재개 호출과 종료만 관찰한다.
        h.stream_calls.append((args, kwargs))
        if h.stream_entered is not None:
            h.stream_entered.set()
        if h.stream_release is not None:
            await asyncio.wait_for(h.stream_release.wait(), timeout=5)

    async def no_file_write(*args, **kwargs):
        forbidden(*args, **kwargs)

    # 다른 회귀에서 실제 모듈이 이미 적재됐어도 동일한 부작용 경계를 보장한다.
    monkeypatch.setattr(ao, "get_runtime_app", runtime)
    monkeypatch.setattr(ao, "persona_learner", persona)
    monkeypatch.setattr(ao, "factory_broadcaster", broadcaster)
    monkeypatch.setattr(ao, "WBSManager", forbidden)
    monkeypatch.setattr(h.orch, "_bound_engine", bound)
    monkeypatch.setattr(h.orch, "_resume_stream", resume_stream)
    monkeypatch.setattr(h.orch, "_save_latest_state", no_file_write)
    monkeypatch.setattr(h.orch, "_run_sprint_loop", no_file_write)
    try:
        yield h
    finally:
        # 처음 적재한 모듈에 대역 참조가 남아 다른 회귀로 전파되지 않게 한다.
        if not already_loaded:
            sys.modules.pop("core.async_orchestrator", None)
            parent = sys.modules.get("core")
            if parent is not None and getattr(parent, "async_orchestrator", None) is ao:
                delattr(parent, "async_orchestrator")


def _config():
    return {"configurable": {"thread_id": f"sprint_{PROJECT}__{TASK}"}}


def _tokens(h):
    context = h.context(h.bound.snapshot, project_id=PROJECT, task_id=TASK)
    assert context["available"] is True
    return {"expected_request_id": context["request_id"],
            "expected_questions_digest": context["questions_digest"]}


def _fixed(h):
    return {key: copy.deepcopy(h.bound.snapshot.values[key]) for key in _FIXED}


def _no_effects(h):
    assert h.initial.writes == h.bound.writes == h.final.writes == []
    assert h.persona_calls == h.quality_calls == h.stream_calls == []
    assert h.orch.active_tasks == {} and h.orch.task_projects == {}
    assert getattr(h.orch, "_studio_commands", {}) == {}


async def _drain(h):
    if h.stream_release is not None:
        h.stream_release.set()
    tasks = list(h.orch.active_tasks.values())
    if tasks:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
    await asyncio.sleep(0)


def test_read_hotl_context_uses_bound_project_snapshot_and_stays_stable(hotl):
    h = hotl
    async def scenario():
        first = await h.orch.read_hotl_context(TASK, PROJECT)
        second = await h.orch.read_hotl_context(TASK, PROJECT)
        assert first == second == h.context(h.bound.snapshot, project_id=PROJECT, task_id=TASK)
        assert first["available"] is True and first["decision_kind"] == "CLARIFICATION"
        assert h.bound_calls == [PROJECT, PROJECT] and h.bound.reads == [_config(), _config()]
        assert h.runtime_calls == h.initial.reads == h.final.reads == []
        assert "합성 기밀 질문" not in str(first)
        _no_effects(h)
    asyncio.run(scenario())


@pytest.mark.parametrize("condition,status", [
    ("active", "NOT_PENDING"), ("quota", "NOT_PENDING"), ("end", "NOT_PENDING"),
    ("checkpoint_missing", "UNKNOWN"), ("read_error", "UNKNOWN"),
])
def test_read_hotl_context_fails_closed_for_non_pending_or_unreadable_state(hotl, condition, status):
    h = hotl
    if condition == "active":
        h.orch.active_tasks[f"{PROJECT}__{TASK}"] = SimpleNamespace(done=lambda: False)
    elif condition == "quota":
        h.bound.snapshot.values["factory_mode"] = "SUSPENDED_QUOTA"
    elif condition == "end":
        h.bound.snapshot = h.bound.snapshot._replace(next=())
    elif condition == "checkpoint_missing":
        h.bound.snapshot.config["configurable"].clear()
    else:
        h.bound.read_error = OSError("합성 상태 조회 실패")
    result = asyncio.run(h.orch.read_hotl_context(TASK, PROJECT))
    assert result["status"] == status and result["available"] is False
    assert result["request_id"] == result["questions_digest"] == ""
    assert h.bound.reads == [_config()] and h.runtime_calls == []
    h.orch.active_tasks.clear()
    _no_effects(h)


@pytest.mark.parametrize("change", [
    "request", "digest", "missing_request", "missing_digest", "both_missing",
    "identical_new_round", "changed_questions", "missing_checkpoint", "no_longer_pending",
])
def test_fresh_final_round_mismatch_is_409_before_update_telemetry_or_resume(hotl, change):
    h = hotl
    tokens = _tokens(h)
    if change == "request":
        tokens["expected_request_id"] = "f" * 64
    elif change == "digest":
        tokens["expected_questions_digest"] = "f" * 64
    elif change == "missing_request":
        tokens.pop("expected_request_id")
    elif change == "missing_digest":
        tokens.pop("expected_questions_digest")
    elif change == "both_missing":
        tokens.clear()
    elif change == "identical_new_round":
        h.final.snapshot.config["configurable"]["checkpoint_id"] = "memory-round-02"
    elif change == "changed_questions":
        h.final.snapshot.values["clarification_questions"][0]["question"] = "새 질문"
    elif change == "missing_checkpoint":
        h.final.snapshot.config["configurable"].clear()
    else:
        h.final.snapshot = h.final.snapshot._replace(next=())
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_hotl(TASK, "", PROJECT, **tokens))
    assert exc.value.status_code == 409 and exc.value.reason_code == "HOTL_ROUND_CONFLICT"
    assert h.final.reads == [_config()]
    if change == "both_missing":
        assert h.initial.reads == [_config()] and h.bound_calls == []
        assert h.runtime_calls == [((), {}), ((TEMPLATE, CONFIG_FP), {})]
    else:
        assert h.bound.reads == [_config()] and h.initial.reads == []
        assert h.runtime_calls == [((TEMPLATE, CONFIG_FP), {})]
    _no_effects(h)


def test_partial_tokens_require_fresh_validation_even_for_legacy_document(hotl):
    h = hotl
    for engine in (h.initial, h.bound, h.final):
        engine.snapshot.values["runtime_document_version"] = "1.0"
    tokens = _tokens(h)
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_hotl(TASK, "", PROJECT,
            expected_request_id=tokens["expected_request_id"]))
    assert exc.value.reason_code == "HOTL_ROUND_CONFLICT" and exc.value.status_code == 409
    assert h.bound.reads == h.final.reads == [_config()]
    _no_effects(h)


@pytest.mark.parametrize("field", ["process_context", "approved_blueprint_digest"])
def test_matching_tokens_do_not_allow_changed_fixed_studio_context(hotl, field):
    h = hotl
    expected = _fixed(h)
    if field == "process_context":
        h.final.snapshot.values[field]["context_key"]["scope_node_id"] = "other-scope"
    else:
        h.final.snapshot.values[field] = "c" * 64
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_hotl(TASK, "", PROJECT,
            **_tokens(h), expected_studio_context=expected))
    assert exc.value.reason_code == "HOTL_CONTEXT_CONFLICT" and exc.value.status_code == 409
    assert h.final.reads == [_config()]
    _no_effects(h)


@pytest.mark.parametrize("field", ["workspace_root", "template_id", "config_fingerprint"])
def test_strict_resume_rejects_workspace_or_graph_drift_before_any_write(hotl, field):
    h = hotl
    expected = _fixed(h)
    # 기존 토큰·고정 5필드는 모두 동일하다. 최종 조회의 실행 대상만 바꾼다.
    h.final.snapshot.values[field] = {
        "workspace_root": h.workspace + "-other",
        "template_id": "other-template", "config_fingerprint": "other-config",
    }[field]
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_hotl(TASK, "", PROJECT,
            **_tokens(h), expected_studio_context=expected))
    assert exc.value.status_code == 409
    assert h.final.reads == [_config()]
    _no_effects(h)


def test_correct_tokens_empty_feedback_update_once_resume_once_and_reject_repeated_round(hotl):
    h = hotl
    async def scenario():
        h.stream_entered, h.stream_release = asyncio.Event(), asyncio.Event()
        tokens = _tokens(h)
        try:
            assert await h.orch.resume_hotl(TASK, "", PROJECT,
                **tokens, expected_studio_context=_fixed(h)) is True
            await asyncio.wait_for(h.stream_entered.wait(), timeout=2)
            assert h.final.writes == [(_config(), {"needs_revision": False})]
            assert h.initial.writes == h.bound.writes == [] and h.persona_calls == []
            assert len(h.quality_calls) == 1
            assert h.quality_calls[0][1] == {"gate_name": "HOTL", "accepted": True, "feedback": ""}
            assert h.stream_calls == [((_config(), TASK, h.workspace, TEMPLATE, CONFIG_FP), {})]
            calls = copy.deepcopy((h.bound_calls, h.runtime_calls, h.final.reads))
            assert await h.orch.resume_hotl(TASK, "", PROJECT, **tokens) is False
            assert (h.bound_calls, h.runtime_calls, h.final.reads) == calls
            await _drain(h)
            # 대역의 쓰기가 이미 다음 체크포인트를 만들었다. 완료 후에도 옛 토큰 재사용은 금지다.
            with pytest.raises(h.Error) as exc:
                await h.orch.resume_hotl(TASK, "", PROJECT, **tokens)
            assert exc.value.reason_code == "HOTL_ROUND_CONFLICT"
            assert len(h.final.writes) == len(h.stream_calls) == len(h.quality_calls) == 1
            assert h.orch._studio_commands == {} and h.orch.active_tasks == {}
        finally:
            await _drain(h)
    asyncio.run(scenario())


def test_legacy_without_tokens_keeps_initial_default_engine_and_feedback_behavior(hotl):
    h = hotl
    for engine in (h.initial, h.bound, h.final):
        engine.snapshot.values["runtime_document_version"] = "1.0"
    async def scenario():
        try:
            assert await h.orch.resume_hotl(TASK, "합성 수정 의견", PROJECT) is True
            await _drain(h)
            assert h.runtime_calls == [((), {}), ((TEMPLATE, CONFIG_FP), {})]
            assert h.initial.reads == [_config()] and h.bound_calls == h.final.reads == []
            assert h.final.writes == [(_config(), {"human_feedback_queue": [{
                "task_id": TASK, "feedback": "합성 수정 의견", "status": "pending", "priority": 1}],
                "needs_revision": True})]
            assert h.persona_calls == [(("hotl_feedback", "합성 수정 의견", PROJECT), {})]
            assert len(h.quality_calls) == len(h.stream_calls) == 1
            assert h.quality_calls[0][1]["accepted"] is False
        finally:
            await _drain(h)
    asyncio.run(scenario())


def test_concurrent_resume_and_other_same_project_services_stop_before_engine_entry(hotl):
    h = hotl
    async def scenario():
        h.final.read_entered, h.final.read_release = asyncio.Event(), asyncio.Event()
        tokens = _tokens(h)
        first = asyncio.create_task(h.orch.resume_hotl(TASK, "", PROJECT, **tokens))
        try:
            await asyncio.wait_for(h.final.read_entered.wait(), timeout=2)
            assert h.orch._studio_commands[PROJECT] == 1 and h.orch.active_tasks == {}
            before = copy.deepcopy((h.bound_calls, h.runtime_calls, h.final.reads))
            payload = {"terminal_status": "KEEP", "terminal_reason": "KEEP"}
            assert await h.orch.resume_hotl(TASK, "", PROJECT, **tokens) is False
            assert await h.orch.start_sprint("TASK-OTHER", payload, h.workspace) is False
            assert await h.orch.resume_from_suspend("TASK-OTHER", PROJECT) is False
            assert payload == {"terminal_status": "KEEP", "terminal_reason": "KEEP"}
            assert (h.bound_calls, h.runtime_calls, h.final.reads) == before
            assert h.final.writes == h.quality_calls == h.persona_calls == []
            # 타 프로젝트의 예약까지 막는 전역 잠금은 아니다.
            with h.guard.command(h.orch, "other-project", exclusive=True, quiescent=True):
                assert h.orch._studio_commands["other-project"] == 1
            h.final.read_release.set()
            assert await asyncio.wait_for(first, timeout=5) is True
            await _drain(h)
            assert len(h.final.writes) == len(h.stream_calls) == len(h.quality_calls) == 1
            assert h.orch._studio_commands == {}
        finally:
            h.final.read_release.set()
            await asyncio.wait_for(asyncio.gather(first, return_exceptions=True), timeout=5)
            await _drain(h)
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["read", "write"])
def test_engine_failure_never_resumes_and_releases_command_reservation(hotl, stage):
    h = hotl
    failure = OSError("합성 최종 엔진 실패")
    if stage == "read":
        h.final.read_error = failure
    else:
        h.final.write_error = failure
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_hotl(TASK, "", PROJECT, **_tokens(h)))
    assert exc.value.status_code == 503
    assert exc.value.reason_code == (
        "HOTL_CHECKPOINT_UNAVAILABLE" if stage == "read" else "HOTL_RESUME_OUTCOME_UNKNOWN")
    assert h.bound_calls == [PROJECT] and h.runtime_calls == [((TEMPLATE, CONFIG_FP), {})]
    assert h.bound.reads == h.final.reads == [_config()] and h.initial.reads == []
    # 쓰기 예외를 명확한 미반영 또는 일반 충돌로 취급하지 않는다. 자동 재시도도 금지다.
    assert h.final.write_attempts == ([] if stage == "read" else [(_config(), {"needs_revision": False})])
    _no_effects(h)


@pytest.mark.parametrize("stage", ["bound_engine", "initial_read", "engine_validation"])
def test_strict_initial_lookup_and_engine_validation_failures_are_unavailable_503(hotl, stage):
    h = hotl
    if stage == "bound_engine":
        h.bound_error = OSError("합성 결속 엔진 획득 실패")
    elif stage == "initial_read":
        h.bound.read_error = OSError("합성 최초 체크포인트 조회 실패")
    else:
        h.final_engine_error = ValueError("합성 실행 엔진 구성 검증 실패")
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_hotl(TASK, "", PROJECT,
            **_tokens(h), expected_studio_context=_fixed(h)))
    assert exc.value.status_code == 503 and exc.value.reason_code == "HOTL_CHECKPOINT_UNAVAILABLE"
    assert h.bound_calls == [PROJECT]
    assert h.bound.reads == ([] if stage == "bound_engine" else [_config()])
    assert h.runtime_calls == ([((TEMPLATE, CONFIG_FP), {})] if stage == "engine_validation" else [])
    assert h.initial.reads == h.final.reads == []
    assert h.initial.write_attempts == h.bound.write_attempts == h.final.write_attempts == []
    _no_effects(h)


def test_strict_persona_failure_after_update_is_unknown_503_without_replay_or_resume(hotl):
    h = hotl
    feedback = "보존해야 할 합성 수정 의견"
    arguments = {**_tokens(h), "expected_studio_context": _fixed(h)}
    original_arguments = copy.deepcopy(arguments)
    h.persona_error = OSError("합성 후처리 기록 실패")
    with pytest.raises(h.Error) as exc:
        asyncio.run(h.orch.resume_hotl(TASK, feedback, PROJECT, **arguments))
    assert exc.value.status_code == 503 and exc.value.reason_code == "HOTL_RESUME_OUTCOME_UNKNOWN"
    expected_queue = [{"task_id": TASK, "feedback": feedback, "status": "pending", "priority": 1}]
    expected_write = (_config(), {"human_feedback_queue": expected_queue, "needs_revision": True})
    assert h.final.write_attempts == h.final.writes == [expected_write]
    assert h.final.snapshot.values["human_feedback_queue"] == expected_queue
    assert h.final.snapshot.config["configurable"]["checkpoint_id"] == "memory-written-1"
    assert h.bound_calls == [PROJECT] and h.runtime_calls == [((TEMPLATE, CONFIG_FP), {})]
    assert h.bound.reads == h.final.reads == [_config()]
    assert h.persona_calls == [(("hotl_feedback", feedback, PROJECT), {})]
    assert h.quality_calls == h.stream_calls == []
    assert h.initial.writes == h.bound.writes == []
    assert h.orch.active_tasks == {} and h.orch.task_projects == {} and h.orch._studio_commands == {}
    assert arguments == original_arguments
    # 이미 반영된 입력을 보존한다. 두 번째 서비스 호출로 자동 재전송을 흉내 내지 않는다.
    assert h.bound.snapshot.values["human_feedback_queue"] == []


def test_exclusive_and_quiescent_command_options_preserve_default_nesting(hotl):
    h = hotl
    with h.guard.command(h.orch, PROJECT):
        with h.guard.command(h.orch, PROJECT):
            assert h.orch._studio_commands[PROJECT] == 2
        with pytest.raises(h.Error) as exc:
            with h.guard.command(h.orch, PROJECT, exclusive=True):
                pytest.fail("배타 예약이 중복 허용되었습니다.")
        assert exc.value.reason_code == "STUDIO_COMMAND_BUSY" and exc.value.status_code == 409
    h.orch.active_tasks["opaque-task"] = SimpleNamespace(done=lambda: False)
    h.orch.task_projects["opaque-task"] = PROJECT
    try:
        with pytest.raises(h.Error) as exc:
            with h.guard.command(h.orch, PROJECT, quiescent=True):
                pytest.fail("실행 중 프로젝트의 정지 전제 예약이 허용되었습니다.")
        assert exc.value.reason_code == "STUDIO_COMMAND_BUSY" and exc.value.status_code == 409
    finally:
        h.orch.active_tasks.clear()
        h.orch.task_projects.clear()
    _no_effects(h)
