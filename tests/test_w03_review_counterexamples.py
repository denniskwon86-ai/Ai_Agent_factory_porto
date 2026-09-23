"""Codex 수용검토 반례. 합성 격리 전용; 현재 결함을 정상 계약 단언으로 남긴다.

제품을 고친 시험이 아니다. 2026-09-22 c246b49fa에서 실패를 예상하며,
정상 소비/기존 집중 시험과 함께 해석한다. 운영 경로는 사용하지 않는다.
"""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from core import atomic_write


@pytest.mark.parametrize("fresh_writer", [False, True], ids=["after-conflict", "fresh-writer"])
def test_stale_payload_cannot_acquire_a_new_baseline(tmp_path, monkeypatch, fresh_writer):
    from core import async_orchestrator as ao

    async def no_broadcast(*args, **kwargs):
        pass

    monkeypatch.setattr(ao.factory_broadcaster, "broadcast", no_broadcast)
    writer = ao.AsyncFactoryOrchestrator()
    workspace = tmp_path / "proj_review"
    first = asyncio.run(writer._save_latest_state({"value": "base"}, str(workspace)))
    assert first["saved"] is True
    stale_payload = {"value": "stale-derived-from-base"}
    path = workspace / "latest_state.json"
    # 다른 정상 writer가 새 변경을 확정했다.
    atomic_write.replace_json_if_unchanged(
        path, {"value": "new-confirmed"}, expected_digest=atomic_write.digest_of(path))
    confirmed = path.read_bytes()
    if fresh_writer:
        writer = ao.AsyncFactoryOrchestrator()
    else:
        rejected = asyncio.run(writer._save_latest_state(stale_payload, str(workspace)))
        assert rejected["saved"] is False and rejected["stale"] is True
        assert path.read_bytes() == confirmed
    # 실제 내용을 다시 읽거나 재계산하지 않고 같은 낡은 payload를 보낸다.
    result = asyncio.run(writer._save_latest_state(stale_payload, str(workspace)))
    observed = json.loads(path.read_text(encoding="utf-8"))
    assert not result["saved"] and path.read_bytes() == confirmed, (
        f"낡은 payload가 기준 지문만 재취득해 저장됨: saved={result['saved']}, content={observed}")


def test_explicit_root_does_not_hide_a_junction_above_it(tmp_path):
    try:
        import _winapi
    except ImportError:
        pytest.skip("이 반례는 실제 Windows junction 사용")
    real = tmp_path / "actual"
    (real / "projects" / "proj_review").mkdir(parents=True)
    link = tmp_path / "linked_parent"
    _winapi.CreateJunction(str(real), str(link))
    assert link.is_junction()
    declared_root = link / "projects"  # root 자체는 일반 디렉터리다.
    path = declared_root / "proj_review" / "latest_state.json"
    try:
        with pytest.raises(ValueError):
            atomic_write.replace_json(path, {"value": "must-not-write"}, root=declared_root)
        assert not (real / "projects" / "proj_review" / "latest_state.json").exists()
    finally:
        link.rmdir()  # 격리 시험이 직접 만든 junction만 제거; 실제 대상은 지우지 않음.


@pytest.mark.parametrize("resume", [False, True], ids=["start-stale-payload", "restart-resume"])
def test_product_loop_preserves_revision_contract(tmp_path, monkeypatch, resume):
    """실제 시작/재개 루프와 파일 저장을 실행한다. 엔진/통지는 합성 대역, LLM 0.

    보안/HTTP/실제 checkpoint 엔진 검증이 아니라 루프의 저장 결속 검사다.
    시작은 낡은 내용을 새 지문으로 승인하면 안 되고 정상 재개는 저장할 수 있어야 한다.
    """
    from types import SimpleNamespace
    from core import async_orchestrator as ao

    workspace = tmp_path / "proj_loop_review"
    workspace.mkdir()
    path = workspace / "latest_state.json"
    atomic_write.replace_json(path, {"value": "base"})
    stale_input = {"value": "derived-from-base"}
    if not resume:
        atomic_write.replace_json_if_unchanged(
            path, {"value": "other-writer-confirmed"},
            expected_digest=atomic_write.digest_of(path))
    before = path.read_bytes()
    outcome = {"value": "resume-result"} if resume else stale_input
    events = []

    class Engine:
        #: ⚠️ [대역 보정 2026-09-23 — 사용자 승인, CR §12-P1②] **기대(assert)는 바꾸지 않았다.**
        #:   바꾼 것은 이 대역이 「재개 직전 checkpoint」에 답하는 값 하나다.
        #:
        #:   종전 대역은 `aget_state` 가 스트림 전후를 가리지 않고 **언제나 결과**를 돌려줬다.
        #:   제품이 재개 전에 checkpoint 를 물어보지 않던 때 만든 대역이라 그래도 됐다.
        #:   이제 재개는 「checkpoint 가 지금 정본과 이어져 있는가」를 **스트림 전에** 묻는다
        #:   (낡은 checkpoint 가 새 정본을 덮는 반례 — 아래 `resume-older-checkpoint`). 그 질문에
        #:   종전 대역은 아직 계산하지 않은 결과를 답하므로, 정본과 다르다고 판정돼 **정상
        #:   재개가 거절**된다. 실제 엔진에서는 노드마다 checkpoint 와 정본을 함께 저장하므로
        #:   아무도 끼어들지 않은 재개 직전 checkpoint 는 정본과 **같다.** 대역을 그 사실에
        #:   맞췄다 — 스트림 전에는 정본과 이어진 checkpoint, 스트림 뒤에는 결과.
        #:
        #:   이 시험이 지키려던 뜻(「정상 재개는 저장할 수 있어야 한다」)은 그대로이고,
        #:   `resume-older-checkpoint` 가 반대쪽(끼어든 뒤의 재개는 거절)을 지킨다.
        def __init__(self):
            self.values = json.loads(path.read_text(encoding="utf-8"))

        async def astream(self, state, *, config):
            self.values = outcome
            yield {"review_node": outcome}

        async def aget_state(self, config):
            return SimpleNamespace(values=self.values)

    async def runtime(*args):
        return Engine()

    async def broadcast(kind, payload):
        events.append((kind, payload))

    async def end(*args):
        pass

    monkeypatch.setattr(ao, "get_runtime_app", runtime)
    monkeypatch.setattr(ao.factory_broadcaster, "broadcast", broadcast)
    writer = ao.AsyncFactoryOrchestrator()
    monkeypatch.setattr(writer, "_broadcast_stream_end", end)
    if resume:
        asyncio.run(writer._resume_stream({}, "task_review", str(workspace)))
    else:
        asyncio.run(writer._run_sprint_loop({}, stale_input, "task_review", str(workspace)))
    completed = [payload for kind, payload in events if kind == "NODE_COMPLETED"]
    assert len(completed) == 1, events
    if resume:
        assert completed[0]["state_saved"] and json.loads(path.read_text(encoding="utf-8")) == outcome, events
    else:
        assert not completed[0]["state_saved"] and path.read_bytes() == before, (
            f"시작 루프가 낡은 내용을 새 기준으로 승인함: {completed[0]}, {path.read_text(encoding='utf-8')}")


@pytest.mark.parametrize("resume", [False, True], ids=["normal-start-through-entry", "resume-older-checkpoint"])
def test_start_and_resume_bind_the_actual_input_revision(tmp_path, monkeypatch, resume):
    """실제 start_sprint/재개 루프 검사. 엔진·WBS·통지만 대역이며 권한/API 시험은 아님."""
    from types import SimpleNamespace
    from core import async_orchestrator as ao

    workspace = tmp_path / "proj_entry_review"
    workspace.mkdir()
    path = workspace / "latest_state.json"
    original = {"value": "base", "terminal_status": "FAILED", "terminal_reason": "old-failure"}
    atomic_write.replace_json(path, original)
    checkpoint = dict(original)
    if resume:
        atomic_write.replace_json_if_unchanged(path, {**original, "value": "new-confirmed"},
                                              expected_digest=atomic_write.digest_of(path))
    before = path.read_bytes()
    events = []

    class Engine:
        def __init__(self):
            self.values = dict(checkpoint)

        async def astream(self, state, *, config):
            self.values = {**(self.values if state is None else state), "value": "computed"}
            yield {"review_node": dict(self.values)}

        async def aget_state(self, config):
            return SimpleNamespace(values=dict(self.values))

    engine = Engine()

    async def runtime(*args):
        return engine

    async def broadcast(kind, payload):
        events.append((kind, payload))

    async def end(*args):
        pass

    monkeypatch.setattr(ao, "get_runtime_app", runtime)
    monkeypatch.setattr(ao.factory_broadcaster, "broadcast", broadcast)
    monkeypatch.setattr(ao, "WBSManager", lambda **kw: SimpleNamespace(checkout_task=lambda tid: None))
    writer = ao.AsyncFactoryOrchestrator()
    monkeypatch.setattr(writer, "_broadcast_stream_end", end)

    async def execute():
        if resume:
            await writer._resume_stream({}, "TASK_REVIEW", str(workspace))
        else:
            accepted = await writer.start_sprint("TASK_REVIEW", dict(original), str(workspace))
            assert accepted is True
            await asyncio.gather(*list(writer.active_tasks.values()))

    asyncio.run(execute())
    completed = [payload for kind, payload in events if kind == "NODE_COMPLETED"]
    if resume:
        assert path.read_bytes() == before and not any(p["state_saved"] for p in completed), events
    else:
        assert completed and completed[-1]["state_saved"], events
        assert json.loads(path.read_text(encoding="utf-8"))["value"] == "computed"


# ── [CR §12 보강 / 2026-09-23] 재개 **진입점**을 실제로 지나는 반례 ─────────────────
#
# 위 `resume-older-checkpoint` 는 `_resume_stream` 을 **직접** 부른다. 그런데 `resume_hotl`·
# `resume_from_suspend` 는 들어오면서 `aupdate_state` 로 checkpoint 를 **손댄다**(피드백·모드 복구).
# 진입점이 가공을 하면 진입점을 지나야 한다 — §12.1 이 `start_sprint` 진입을 요구한 것과 같은
# 이유다. 손대기 전 값을 기준으로 넘기는 배선이 맞는지는 진입점을 지나야만 보인다.
#
# ★ `resume_existing`(일시정지·실패 재개)은 checkpoint 를 **가공하지 않는다**(`aupdate_state`·
#   저장 호출 없음). 그래서 재개가 스스로 읽는 값이 곧 기준이다 — 그래도 진입점을 지나는 반례를
#   따로 둔다. 가공이 없다는 것 자체를 시험이 확인해 두어야, 나중에 누가 가공을 넣으면 걸린다.


class _ResumeEngine:
    """재개 진입점 대역. 스트림 **전**에는 checkpoint 를, 스트림 **뒤**에는 계산 결과를 준다.
    `aupdate_state` 는 checkpoint 를 실제로 바꾼다 — 진입점이 손대는 것을 그대로 흉내 낸다."""
    interrupt_after_nodes = ()

    def __init__(self, checkpoint):
        self.values = copy.deepcopy(checkpoint)
        self.updates = []

    async def aget_state(self, config):
        return SimpleNamespace(values=copy.deepcopy(self.values), next=(), config={}, tasks=(), metadata={})

    async def aupdate_state(self, config, updates):
        self.updates.append(copy.deepcopy(updates))
        self.values.update(copy.deepcopy(updates))

    async def astream(self, state, *, config):
        self.values = {**self.values, "value": "computed"}
        yield {"review_node": copy.deepcopy(self.values)}


def _wire_resume(monkeypatch, engine):
    """엔진·통지만 대역이다. 서비스·재개 루프·인수·파일 저장은 **실제**를 탄다."""
    from core import async_orchestrator as ao

    events = []

    async def runtime(*args, **kwargs):
        return engine

    async def broadcast(kind, payload):
        events.append((kind, payload))

    async def end(*args):
        pass

    monkeypatch.setattr(ao, "get_runtime_app", runtime)
    monkeypatch.setattr(ao.factory_broadcaster, "broadcast", broadcast)
    writer = ao.AsyncFactoryOrchestrator()
    monkeypatch.setattr(writer, "_broadcast_stream_end", end)
    return writer, events


@pytest.mark.parametrize("stale", [False, True], ids=["hotl-normal", "hotl-older-checkpoint"])
def test_resume_hotl_entry_binds_the_checkpoint_before_feedback(tmp_path, monkeypatch, stale):
    """★ `resume_hotl` 을 **실제로 지난다.** 진입점이 `needs_revision` 을 써 넣으므로 재개 기준은
    그 **전** checkpoint 여야 한다 — 정상(checkpoint==정본)은 저장되고, 끼어든 뒤는 거절된다."""
    project = "proj_hotl_review"
    workspace = tmp_path / project
    workspace.mkdir()
    path = workspace / "latest_state.json"
    checkpoint = {"value": "base", "workspace_root": str(workspace), "runtime_document_version": "1.0",
                  "needs_revision": True, "human_feedback_queue": []}
    atomic_write.replace_json(path, {**checkpoint, "value": "new-confirmed"} if stale else checkpoint)
    before = path.read_bytes()
    engine = _ResumeEngine(checkpoint)
    writer, events = _wire_resume(monkeypatch, engine)

    async def go():
        assert await writer.resume_hotl("TASK_HOTL", "", project) is True
        await asyncio.gather(*list(writer.active_tasks.values()))

    asyncio.run(go())
    #: 전제 확인 — 진입점이 정말 checkpoint 를 손댔다. 안 손댔다면 이 시험은 아무것도 안 본다.
    assert engine.updates == [{"needs_revision": False}], engine.updates
    completed = [p for kind, p in events if kind == "NODE_COMPLETED"]
    assert completed, events
    if stale:
        assert path.read_bytes() == before and not any(p["state_saved"] for p in completed), \
            "옛 checkpoint 에서 이어 계산한 결과가 다른 writer 의 새 정본을 덮었다"
    else:
        assert completed[-1]["state_saved"], completed
        assert json.loads(path.read_text(encoding="utf-8"))["value"] == "computed"


@pytest.mark.parametrize("stale", [False, True], ids=["quota-normal", "quota-changed-while-suspended"])
def test_resume_from_suspend_entry_checks_the_frozen_checkpoint_before_restoring(tmp_path, monkeypatch, stale):
    """★ 쿼터 재개를 **실제로 지난다.** 동결 checkpoint 가 정본과 이어져 있지 않으면 모드를
    복구하기 **전에** 409 로 멈추고 checkpoint 도 정본도 건드리지 않는다. 이어져 있으면 모드를
    복구해 기록하고, 이어서 재개한 결과까지 저장된다."""
    from core.enterprise_context.process_schema import ProcessError

    project = "proj_quota_review"
    workspace = tmp_path / project
    workspace.mkdir()
    path = workspace / "latest_state.json"
    frozen = {"value": "base", "workspace_root": str(workspace), "template_id": "default",
              "factory_mode": "SUSPENDED_QUOTA", "pre_suspend_mode": "EXECUTION"}
    atomic_write.replace_json(path, {**frozen, "value": "new-confirmed"} if stale else frozen)
    before = path.read_bytes()
    engine = _ResumeEngine(frozen)
    writer, events = _wire_resume(monkeypatch, engine)

    if stale:
        with pytest.raises(ProcessError) as caught:
            asyncio.run(writer.resume_from_suspend("TASK_QUOTA", project))
        assert caught.value.status_code == 409 and caught.value.reason_code == "STUDIO_QUOTA_RESUME_CONFLICT"
        assert engine.updates == [], "충돌인데 동결 checkpoint 를 먼저 복구했다 — 어중간한 상태가 남는다"
        assert path.read_bytes() == before and not writer.active_tasks
        return

    async def go():
        assert await writer.resume_from_suspend("TASK_QUOTA", project) is True
        await asyncio.gather(*list(writer.active_tasks.values()))

    asyncio.run(go())
    assert engine.updates and engine.updates[0]["factory_mode"] == "EXECUTION", engine.updates
    completed = [p for kind, p in events if kind == "NODE_COMPLETED"]
    assert completed and completed[-1]["state_saved"], events
    assert json.loads(path.read_text(encoding="utf-8"))["value"] == "computed"


@pytest.mark.parametrize("stale", [False, True], ids=["existing-normal", "existing-older-checkpoint"])
def test_resume_existing_entry_uses_the_checkpoint_it_resumes(tmp_path, monkeypatch, stale):
    """★ `resume_existing`(일시정지·실패 재개)을 **실제로 지난다.**

    재개 **근거** 판정(정지 증거·현재 노드 오류)은 대역으로 통과시킨다 — 그것은 W03.2 의 관심사가
    아니고 `tests/test_b5_execution_resume.py` 가 따로 지킨다. 관심사인 **인수·저장은 실제**를 탄다.
    이 진입점은 checkpoint 를 손대지 않으므로, 정상(checkpoint==정본)은 저장되고 끼어든 뒤는
    거절돼야 한다.
    """
    from core import studio_pause_state as pauses

    project, task = "proj_existing_review", "TASK_EXISTING"
    workspace = tmp_path / project
    workspace.mkdir()
    path = workspace / "latest_state.json"
    checkpoint = {"value": "base", "workspace_root": str(workspace), "current_sprint_task_id": task,
                  "template_id": "default", "config_fingerprint": ""}
    atomic_write.replace_json(path, {**checkpoint, "value": "new-confirmed"} if stale else checkpoint)
    before = path.read_bytes()
    engine = _ResumeEngine(checkpoint)
    writer, events = _wire_resume(monkeypatch, engine)

    async def bound(pid):
        return engine

    evidence = {"template_id": "default", "config_fingerprint": ""}
    monkeypatch.setattr(writer, "_bound_engine", bound)
    monkeypatch.setattr(writer, "_pause_evidence", lambda snap, eng, tid, pid: (str(workspace), evidence))
    monkeypatch.setattr(type(writer), "_failed_retry", staticmethod(lambda snap: True))
    monkeypatch.setattr(pauses, "read", lambda root, task_id: None)   # 실패 재시도 경로 — 정지 기록 없음

    async def go():
        assert await writer.resume_existing(task, project) is True
        await asyncio.gather(*list(writer.active_tasks.values()))

    asyncio.run(go())
    #: 전제 확인 — 이 진입점은 checkpoint 를 손대지 않는다. 누가 가공을 넣으면 여기서 걸린다.
    assert engine.updates == [], engine.updates
    completed = [p for kind, p in events if kind == "NODE_COMPLETED"]
    assert completed, events
    if stale:
        assert path.read_bytes() == before and not any(p["state_saved"] for p in completed), \
            "옛 checkpoint 에서 이어 계산한 결과가 다른 writer 의 새 정본을 덮었다"
    else:
        assert completed[-1]["state_saved"], completed
        assert json.loads(path.read_text(encoding="utf-8"))["value"] == "computed"
