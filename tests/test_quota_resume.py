"""core/async_orchestrator.py — [R2] SUSPENDED_QUOTA 재개 경로 검증.

쿼터 완전 고갈로 동결(SUSPENDED_QUOTA)된 스프린트를, '처음부터 재실행'이 아니라
마지막 체크포인트 지점부터 재개(astream(None))해야 한다. 핵심 불변식:
  1) 동결 시 직전 정상 모드를 pre_suspend_mode 로 보존한다.
  2) 이미 동결 상태에서 재소진되면 원래 보존값을 덮지 않는다.
  3) 재개 시 factory_mode 를 pre_suspend_mode 로 복구한다(HOTL 감지 정상화의 전제).
  4) SUSPENDED_QUOTA 가 아닌 태스크/이미 실행 중인 태스크는 재개하지 않는다.
pytest-asyncio 없이 asyncio.run 으로 구동(리포 관례)."""
import asyncio
from core import async_orchestrator as ao
from core.async_orchestrator import AsyncFactoryOrchestrator


class _Snap:
    def __init__(self, values, next_=None):
        self.values = values
        self.next = next_


class _FakeEngine:
    """LangGraph 런타임 앱 대역. aget_state/aupdate_state/astream 만 흉내낸다."""
    def __init__(self, values, next_=None):
        self._values = dict(values)
        self._next = next_
        self.updates = []  # aupdate_state 로 들어온 갱신 이력

    async def aget_state(self, config):
        return _Snap(dict(self._values), self._next)

    async def aupdate_state(self, config, updates):
        self.updates.append(dict(updates))
        self._values.update(updates)

    async def astream(self, inp, config=None):
        # 빈 async generator (재개 스트림은 테스트에서 즉시 취소되므로 실제로는 안 돌아감)
        if False:
            yield None

    def merged_updates(self):
        m = {}
        for u in self.updates:
            m.update(u)
        return m


def _patch(monkeypatch, engine, orch):
    async def fake_get(tid="default", expected_fingerprint=""):
        return engine
    monkeypatch.setattr(ao, "get_runtime_app", fake_get)

    async def noop(*a, **k):
        return None
    monkeypatch.setattr(ao.factory_broadcaster, "broadcast", noop)
    monkeypatch.setattr(orch, "_save_latest_state", noop)


async def _drain(orch):
    """resume 가 create_task 로 띄운 백그라운드 재개 스트림을 즉시 취소·정리."""
    for k, t in list(orch.active_tasks.items()):
        t.cancel()
        try:
            await t
        except BaseException:
            pass


def test_suspend_preserves_prev_mode(monkeypatch):
    orch = AsyncFactoryOrchestrator()
    engine = _FakeEngine({"factory_mode": "EXECUTION", "workspace_root": "./x"})
    _patch(monkeypatch, engine, orch)
    cfg = {"configurable": {"thread_id": "t"}}
    asyncio.run(orch._suspend_for_quota(engine, cfg, "E2E-01", "./x"))
    m = engine.merged_updates()
    assert m["factory_mode"] == "SUSPENDED_QUOTA"
    assert m["pre_suspend_mode"] == "EXECUTION"  # 직전 모드 보존


def test_suspend_twice_keeps_original_prev(monkeypatch):
    # 재개 직후 다시 소진(이미 SUSPENDED_QUOTA)된 경우 원래 보존값을 덮지 않아야 한다
    orch = AsyncFactoryOrchestrator()
    engine = _FakeEngine({"factory_mode": "SUSPENDED_QUOTA",
                          "pre_suspend_mode": "PLANNING", "workspace_root": "./x"})
    _patch(monkeypatch, engine, orch)
    cfg = {"configurable": {"thread_id": "t"}}
    asyncio.run(orch._suspend_for_quota(engine, cfg, "E2E-01", "./x"))
    assert all("pre_suspend_mode" not in u for u in engine.updates)
    assert engine._values["pre_suspend_mode"] == "PLANNING"


def test_resume_restores_mode_and_starts(monkeypatch):
    orch = AsyncFactoryOrchestrator()
    engine = _FakeEngine({"factory_mode": "SUSPENDED_QUOTA", "pre_suspend_mode": "EXECUTION",
                          "workspace_root": "./projects/PID", "template_id": "default"})
    _patch(monkeypatch, engine, orch)

    async def go():
        ok = await orch.resume_from_suspend("E2E-01", "PID")
        await _drain(orch)
        return ok

    ok = asyncio.run(go())
    assert ok is True
    m = engine.merged_updates()
    assert m["factory_mode"] == "EXECUTION"  # 직전 모드로 복구
    assert m["pre_suspend_mode"] == ""       # 보존값 초기화


def test_resume_defaults_execution_when_no_prev(monkeypatch):
    # pre_suspend_mode 가 비어 있으면 안전 기본값 EXECUTION 으로 복구
    orch = AsyncFactoryOrchestrator()
    engine = _FakeEngine({"factory_mode": "SUSPENDED_QUOTA",
                          "workspace_root": "./projects/PID", "template_id": "default"})
    _patch(monkeypatch, engine, orch)

    async def go():
        ok = await orch.resume_from_suspend("E2E-01", "PID")
        await _drain(orch)
        return ok

    assert asyncio.run(go()) is True
    assert engine.merged_updates()["factory_mode"] == "EXECUTION"


def test_resume_rejects_non_suspended(monkeypatch):
    # SUSPENDED_QUOTA 가 아니면 재개 대상이 아니다(오작동 방지)
    orch = AsyncFactoryOrchestrator()
    engine = _FakeEngine({"factory_mode": "EXECUTION", "workspace_root": "./projects/PID"})
    _patch(monkeypatch, engine, orch)
    ok = asyncio.run(orch.resume_from_suspend("E2E-01", "PID"))
    assert ok is False
    assert orch.active_tasks == {}
    # 상태를 건드리지 않아야 함
    assert engine.updates == []


def test_resume_rejects_when_already_running(monkeypatch):
    orch = AsyncFactoryOrchestrator()

    async def go():
        async def _sleep():
            await asyncio.sleep(10)
        running = asyncio.create_task(_sleep())
        orch.active_tasks[ao._skey("PID", "E2E-01")] = running
        engine = _FakeEngine({"factory_mode": "SUSPENDED_QUOTA", "workspace_root": "./projects/PID"})
        _patch(monkeypatch, engine, orch)
        ok = await orch.resume_from_suspend("E2E-01", "PID")
        running.cancel()
        try:
            await running
        except BaseException:
            pass
        return ok, engine

    ok, engine = asyncio.run(go())
    assert ok is False
    assert engine.updates == []  # 실행 중이면 아무 상태도 건드리지 않음
