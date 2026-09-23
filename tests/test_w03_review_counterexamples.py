"""Codex 수용검토 반례. 합성 격리 전용; 현재 결함을 정상 계약 단언으로 남긴다.

제품을 고친 시험이 아니다. 2026-09-22 c246b49fa에서 실패를 예상하며,
정상 소비/기존 집중 시험과 함께 해석한다. 운영 경로는 사용하지 않는다.
"""
import asyncio
import json

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
