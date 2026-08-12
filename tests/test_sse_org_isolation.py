"""★★★ [G1-C] SSE 조직·프로젝트 격리 — **남의 공장 사정이 내 화면에 흐르지 않는다.**

## 무엇이 열려 있었나

`factory_broadcaster.broadcast()` 는 이름 그대로 **연결된 모든 큐**에 넣었다. 그래서
다른 사업부의 프로젝트가 어느 단계에 있고 무엇이 실패했는지가, 그 프로젝트를 **목록에서
볼 수도 없는 사람의 화면에 실시간으로** 흘렀다. `NODE_COMPLETED` 는 `state` 전체를 싣는다.

E0-1B(티켓)와 E0-1C(헤더 신뢰 차단)는 **신원**을 닫았다. 즉 「내가 누구인지」는 이제 서버가
안다. 그런데 「그 사람이 이 이벤트를 봐도 되는가」는 아무도 묻지 않았다. 그것이 G1-C 다.

## 세는 규칙

★ **화면 필터를 통제로 세지 않는다.** 프론트가 `project_id` 로 걸러도 데이터는 이미 브라우저에
  도착해 있다(작업서 §CL-BE-05 와 같은 판단). 그래서 이 파일은 **큐에 들어갔는가**를 본다.

★★ **대조군을 함께 둔다.** 「안 왔다」는 격리 때문일 수도, 애초에 아무것도 안 보내졌기
  때문일 수도 있다. 그래서 같은 이벤트를 **볼 자격이 있는 구독자**가 함께 붙어 있고,
  그쪽에는 **와야** 한다. 한쪽만 보면 브로드캐스트가 통째로 고장 나도 초록이다.
"""
import asyncio
import json

import pytest

from core.broadcaster import SSEBroadcaster


class _Scope:
    """`AccessScope` 를 흉내 낸다 — 판정에 쓰이는 세 필드만 있으면 된다."""

    def __init__(self, depts, unrestricted=False):
        self.readable_dept_ids = frozenset(depts)
        self.unrestricted = unrestricted


#: 프로젝트 P_A 는 D1 소속, P_B 는 D2 소속.
OWNERSHIP = {
    "P_A": {"owner_dept_id": "D1", "owner_user_id": "a@x", "visibility": "dept"},
    "P_B": {"owner_dept_id": "D2", "owner_user_id": "b@x", "visibility": "dept"},
    "P_OPEN": {"owner_dept_id": "D2", "owner_user_id": "b@x", "visibility": "company"},
    #: D1 소속이지만 **내 것은 아닌** 프로젝트. 부서 권한으로만 보인다 —
    #: 소유자 본인은 부서가 바뀌어도 계속 보이므로, 회수 검증에는 이쪽을 써야 한다.
    "P_D1_OTHER": {"owner_dept_id": "D1", "owner_user_id": "z@x", "visibility": "dept"},
    "P_LEGACY": {},          # 마이그레이션 전 — 소유권 미기록
}

SCOPES = {
    "a@x": _Scope({"D1"}),
    "b@x": _Scope({"D2"}),
    "boss@x": _Scope(set(), unrestricted=True),
}


@pytest.fixture()
def bus(monkeypatch):
    """소유권·권한 해석을 격리한 브로드캐스터.

    ⚠️ `core.project_visibility` 쪽을 갈아끼운다. `api.routes.factory_control` 의 같은 이름을
      바꿔도 **브로드캐스터에는 닿지 않는다** — 서로 다른 모듈에서 부르기 때문이다."""
    import core.paths as paths
    import core.project_visibility as pv
    from core.org_directory import org_directory

    monkeypatch.setattr(paths, "workspace_path", lambda *p: "/".join(p), raising=False)
    monkeypatch.setattr(pv, "read_project_ownership",
                        lambda ws: dict(OWNERSHIP.get(str(ws).split("/")[-1], {})))
    monkeypatch.setattr(org_directory, "resolve_scope",
                        lambda uid="": SCOPES.get(uid, _Scope(set())))
    return SSEBroadcaster()


def _types(q: asyncio.Queue) -> list:
    """큐에 실제로 들어간 이벤트 타입 목록."""
    out = []
    while not q.empty():
        line = q.get_nowait()
        if line.startswith("data: "):
            out.append(json.loads(line[6:])["type"])
    return out


def _queue_of(bus, index: int) -> asyncio.Queue:
    return bus.clients[index]


async def _subscribe(bus, user_id: str):
    """`subscribe()` 를 큐 등록 단계까지만 돌린다.

    ⚠️ 제너레이터를 끝까지 소비하면 15초 ping 을 기다린다. 우리가 볼 것은 «큐에 들어갔는가»
      이므로 큐를 직접 읽는다."""
    agen = bus.subscribe(user_id=user_id)
    task = asyncio.ensure_future(agen.asend(None))
    await asyncio.sleep(0.05)            # 큐가 self.clients 에 붙을 틈
    return agen, task


def _run(coro):
    """시나리오를 돌리고 **남은 태스크를 정리한 뒤** 루프를 닫는다.

    ⚠️ 정리하지 않으면 «Task was destroyed but it is pending!» 이 테스트마다 찍힌다.
      기능은 멀쩡하지만, 늘 찍히는 경고는 사람이 경고를 안 읽게 만든다 — 진짜 경고가
      나올 때 함께 묻힌다."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in pending:
            t.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


# ── 핵심: 남의 조직 이벤트는 큐에 들어가지도 않는다 ────────────────────────

def test_다른_조직_프로젝트_이벤트는_큐에_들어가지_않는다(bus):
    async def scenario():
        await _subscribe(bus, "a@x")     # D1 사람
        await _subscribe(bus, "b@x")     # D2 사람
        qa, qb = _queue_of(bus, 0), _queue_of(bus, 1)

        await bus.broadcast("NODE_COMPLETED", {"project_id": "P_B", "state": {"비밀": 1}})

        got_a, got_b = _types(qa), _types(qb)
        # ★ 대조군 — b 에게는 **와야** 한다. 안 오면 브로드캐스트가 고장 난 것이지
        #   격리가 잘 된 것이 아니다.
        assert got_b == ["NODE_COMPLETED"], (
            f"자기 조직 이벤트가 자기에게도 안 왔다({got_b}). 격리가 아니라 고장이다.")
        assert got_a == [], f"다른 조직(D2) 이벤트가 D1 사용자 큐에 들어갔다: {got_a}"

    _run(scenario())


def test_무제한_권한자는_전부_받는다(bus):
    """감독·경영진은 전사를 본다 — 격리가 «아무도 못 보는» 것이 되면 안 된다."""
    async def scenario():
        await _subscribe(bus, "boss@x")
        q = _queue_of(bus, 0)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_A"})
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_B"})
        assert _types(q) == ["WBS_UPDATED", "WBS_UPDATED"]

    _run(scenario())


def test_전사공개_프로젝트는_다른_조직도_받는다(bus):
    """`visibility='company'` 는 목록에서도 보인다 — 이벤트도 같은 답이어야 한다."""
    async def scenario():
        await _subscribe(bus, "a@x")
        q = _queue_of(bus, 0)
        await bus.broadcast("SPRINT_COMPLETED", {"project_id": "P_OPEN"})
        assert _types(q) == ["SPRINT_COMPLETED"]

    _run(scenario())


def test_소유권_미기록_프로젝트는_막지_않는다(bus):
    """마이그레이션 전 프로젝트까지 막으면 기능이 통째로 멈춘다(하위호환 계약)."""
    async def scenario():
        await _subscribe(bus, "a@x")
        q = _queue_of(bus, 0)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_LEGACY"})
        assert _types(q) == ["WBS_UPDATED"]

    _run(scenario())


# ── 분류가 없으면 보내지 않는다 ────────────────────────────────────────────

def test_project_id_가_없으면_아무에게도_보내지_않는다(bus, capsys):
    """⚠️ 「분류를 못 붙였으니 전체에게」로 해석하면 G1-C 가 무의미해진다.

    ★ 대신 **소리 내어** 남긴다. 조용히 사라지면 새 이벤트를 만든 사람이 원인을 못 찾는다."""
    async def scenario():
        await _subscribe(bus, "a@x")
        await _subscribe(bus, "boss@x")
        qa, qb = _queue_of(bus, 0), _queue_of(bus, 1)
        await bus.broadcast("MYSTERY_EVENT", {"detail": "분류 없음"})
        assert _types(qa) == [] and _types(qb) == [], "분류 없는 이벤트가 배달됐다"
        assert "MYSTERY_EVENT" in capsys.readouterr().out, "조용히 버렸다 — 경고가 없다"

    _run(scenario())


def test_전사공통_표식은_명시할_때만_먹는다(bus):
    """정말 전사 공통인 이벤트는 표식을 적어서 보낸다."""
    async def scenario():
        await _subscribe(bus, "a@x")
        q = _queue_of(bus, 0)
        await bus.broadcast("SYSTEM_NOTICE", {"_broadcast_scope": "global", "msg": "점검"})
        assert _types(q) == ["SYSTEM_NOTICE"]

    _run(scenario())


def test_익명_구독자는_프로젝트_이벤트를_받지_못한다(bus):
    """티켓 도입 후 실제로는 익명이 붙지 못하지만, 규칙 자체를 확인해 둔다."""
    async def scenario():
        await _subscribe(bus, "")
        q = _queue_of(bus, 0)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_A"})
        assert _types(q) == []

    _run(scenario())


# ── 권한은 «보낼 때마다» 다시 읽는다 ───────────────────────────────────────

def test_권한을_회수하면_열린_연결에도_즉시_반영된다(bus, monkeypatch):
    """★★ 구독 시점의 scope 를 굳혀 두면 **연결이 사는 12시간 동안 옛 권한이 흐른다.**

    화면을 새로고침해야만 사라지는 종류의 유출이고, 아무도 그것을 보지 못한다.

    ⚠️ 대상은 **내가 소유하지 않은** D1 프로젝트여야 한다. 처음에 `P_A`(내가 소유자)로
      썼다가 실패했는데, 그것은 격리가 안 된 것이 아니라 **소유자는 부서가 바뀌어도 자기
      프로젝트를 본다**는 원래 규칙이 맞은 것이었다 — 전제가 틀린 테스트였다."""
    async def scenario():
        await _subscribe(bus, "a@x")
        q = _queue_of(bus, 0)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_D1_OTHER"})
        assert _types(q) == ["WBS_UPDATED"], "처음에는 보여야 한다"

        # 조직 이동 — D1 권한을 잃었다. 연결은 그대로 열려 있다.
        from core.org_directory import org_directory
        monkeypatch.setattr(org_directory, "resolve_scope",
                            lambda uid="": _Scope(set()))
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_D1_OTHER"})
        assert _types(q) == [], "권한을 회수했는데 열린 연결로 계속 흐른다"

    _run(scenario())


# ── 지정 수신자 경로는 건드리지 않는다 ─────────────────────────────────────

def test_결정_요청은_프로젝트_밖_사람에게도_간다(bus):
    """⚠️ `emit_to` 에 프로젝트 필터를 겹쳐 걸면 **결정 요청이 결정권자에게 못 간다.**

    승인자·데이터 오너는 대개 그 프로젝트의 부서 소속이 아니다. 두 경로의 목적이 다르다."""
    async def scenario():
        await _subscribe(bus, "b@x")      # D2 사람 — P_A 를 볼 수 없다
        q = _queue_of(bus, 0)
        sent = bus.emit_to("DECISION_REQUESTED", {"project_id": "P_A"}, ["b@x"])
        assert sent == 1 and _types(q) == ["DECISION_REQUESTED"]

    _run(scenario())
