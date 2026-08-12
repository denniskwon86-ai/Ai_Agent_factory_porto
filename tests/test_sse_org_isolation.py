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

    def __init__(self, depts, unrestricted=False, is_admin=False):
        self.readable_dept_ids = frozenset(depts)
        self.unrestricted = unrestricted
        #: 플랫폼 관리자 — `LEGACY_UNBOUND`(마이그레이션 대상)를 볼 수 있는 유일한 일반 경로.
        self.is_admin = is_admin


#: 프로젝트 P_A 는 D1 소속, P_B 는 D2 소속.
OWNERSHIP = {
    "P_A": {"owner_dept_id": "D1", "owner_user_id": "a@x", "visibility": "dept"},
    "P_B": {"owner_dept_id": "D2", "owner_user_id": "b@x", "visibility": "dept"},
    "P_OPEN": {"owner_dept_id": "D2", "owner_user_id": "b@x", "visibility": "company"},
    #: D1 소속이지만 **내 것은 아닌** 프로젝트. 부서 권한으로만 보인다 —
    #: 소유자 본인은 부서가 바뀌어도 계속 보이므로, 회수 검증에는 이쪽을 써야 한다.
    "P_D1_OTHER": {"owner_dept_id": "D1", "owner_user_id": "z@x", "visibility": "dept"},
    "P_LEGACY": {},          # 마이그레이션 전 — 소유권 미기록
    #: [G1-C1.1] 문맥 경계 검증용. 조직 권한은 통과해도 테넌트·실행모드가 다르면 막혀야 한다.
    "P_OTHER_TENANT": {"owner_dept_id": "D1", "owner_user_id": "z@x", "visibility": "dept",
                       "tenant_id": "tenant_other", "entity_mode": "REAL"},
    "P_SANDBOX": {"owner_dept_id": "D1", "owner_user_id": "z@x", "visibility": "dept",
                  "tenant_id": "tenant_default", "entity_mode": "VIRTUAL"},
}

SCOPES = {
    "a@x": _Scope({"D1"}),
    "b@x": _Scope({"D2"}),
    "boss@x": _Scope(set(), unrestricted=True),
    "plat@x": _Scope(set(), is_admin=True),      # 플랫폼 관리자(무제한은 아님)
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
    #: [G1-C1.1] `emit_to` 가 계정 유효성을 확인한다 — 합성 사용자를 활성으로 세워 준다.
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
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


def test_소유권_미기록_프로젝트는_관리자에게만_간다(bus):
    """★★★ [G1-C1.1] 종전 계약은 「미기록도 막지 않는다(하위호환)」였다.

    실측이 그 대가를 보여 줬다 — 61개 중 **53개가 미기록**이어서, 하위호환이 통제의 예외가
    아니라 **통제의 기본값**이 되어 있었다. 이제 마이그레이션 대상은 플랫폼 관리자만 받는다.
    ★ 완전히 끊지 않는 이유: 관리자에게는 보여야 무엇을 마이그레이션할지 알 수 있다."""
    async def scenario():
        await _subscribe(bus, "a@x")        # 일반 사용자
        await _subscribe(bus, "plat@x")     # 플랫폼 관리자
        qa, qp = _queue_of(bus, 0), _queue_of(bus, 1)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_LEGACY"})
        assert _types(qa) == [], "미기록 프로젝트 이벤트가 일반 사용자에게 갔다"
        assert _types(qp) == ["WBS_UPDATED"], "관리자에게도 안 가면 부채를 못 본다"

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


# ── 문맥 경계: 조직 권한을 통과해도 테넌트·실행모드가 다르면 막는다 ────────

async def _subscribe_ctx(bus, user_id, tenant_id="", entity_mode=""):
    agen = bus.subscribe(user_id=user_id, tenant_id=tenant_id, entity_mode=entity_mode)
    asyncio.ensure_future(agen.asend(None))
    await asyncio.sleep(0.05)
    return agen


def test_다른_테넌트_프로젝트는_조직권한이_있어도_막힌다(bus):
    """★★★ [G1-C1.1] 부서 권한만 보면 통과한다 — `D1` 사람이 `D1` 소유 프로젝트를 본다.

    그런데 그 프로젝트는 **다른 테넌트**의 것이다. 테넌트는 「보안·계약·데이터 격리 최상위
    경계」이고, 부서 이름이 우연히 같다고 넘어가면 그 경계가 이름 충돌 하나로 무너진다."""
    async def scenario():
        await _subscribe_ctx(bus, "a@x", tenant_id="tenant_default", entity_mode="REAL")
        q = _queue_of(bus, 0)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_D1_OTHER"})
        assert _types(q) == ["WBS_UPDATED"], "같은 테넌트 이벤트가 안 왔다 — 대조군이 죽었다"
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_OTHER_TENANT"})
        assert _types(q) == [], "다른 테넌트 프로젝트 이벤트가 배달됐다"

    _run(scenario())


def test_실제_문맥_구독자는_샌드박스_이벤트를_받지_않는다(bus):
    """★★ 검증 샌드박스(VIRTUAL) 자료가 실제 문맥(REAL) 화면에 섞이면, 시험 산출물의 진행이
    **실제 업무 진행처럼** 보인다. 그 화면을 보고 사람이 판단한다."""
    async def scenario():
        await _subscribe_ctx(bus, "a@x", tenant_id="tenant_default", entity_mode="REAL")
        await _subscribe_ctx(bus, "a@x", tenant_id="tenant_default", entity_mode="VIRTUAL")
        q_real, q_virtual = _queue_of(bus, 0), _queue_of(bus, 1)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_SANDBOX"})
        assert _types(q_real) == [], "REAL 구독자에게 샌드박스 이벤트가 갔다"
        assert _types(q_virtual) == ["WBS_UPDATED"], "VIRTUAL 구독자에게도 안 갔다 — 고장이다"

    _run(scenario())


def test_문맥_없는_옛_구독은_막지_않는다(bus):
    """⚠️ G1-C1.1 이전 티켓에는 문맥이 없다. 다 막으면 **이미 열린 연결이 전부 끊긴다** —
    통제가 아니라 장애다. 새 티켓은 항상 문맥을 싣는다."""
    async def scenario():
        await _subscribe_ctx(bus, "a@x")     # 문맥 없음(옛 티켓)
        q = _queue_of(bus, 0)
        await bus.broadcast("WBS_UPDATED", {"project_id": "P_D1_OTHER"})
        assert _types(q) == ["WBS_UPDATED"]

    _run(scenario())
