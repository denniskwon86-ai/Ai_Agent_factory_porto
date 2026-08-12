"""★★★ [G1-C1.4] 협업 알림 테넌트 격리 — **실제 배선을 타는** 종단 검증.

## 왜 이 파일이 따로 필요한가

1차 구현은 `emit_to` 가 `payload["project_id"]` 를 읽어 테넌트를 판정하게 했다. 그런데 그 키는
브라우저로 나가기 전에 `CollaborationEvents._clean()` 이 지운다(`ALLOWED_KEYS` 에 없다).
즉 **판정에 쓰려던 값이 판정 지점에 도달하기 전에 사라졌고**, 실서비스에서는 언제나
「근거 없음」이었다 — 모든 테넌트 창에 알림이 갔다.

그런데도 테스트는 초록이었다. 테스트가 `CollaborationEvents` 를 **건너뛰고** `bus.emit_to()` 를
직접 불렀기 때문이다.

    테스트:   bus.emit_to(payload 에 project_id 포함)      → 격리 통과
    실서비스: 도메인 → _clean() 이 project_id 제거 → emit_to → 근거 없음 → 전부 전달

★★★ **테스트가 실제 배선을 타지 않으면 그 초록은 거짓이다.** 그래서 이 파일은 반드시
  `CollaborationEvents.emit()` 을 통과하고, 가능한 곳은 도메인의 `_notify()` 까지 탄다.
  `bus.emit_to()` 만 부르는 것은 단위 테스트로만 두고 종단 근거로 쓰지 않는다.
"""
import asyncio

import pytest

from core.broadcaster import SSEBroadcaster
from core.collaboration_events import DECISION_UPDATED, CollaborationEvents


def _client(bus, user_id, tenant_id, entity_mode="REAL"):
    q = asyncio.Queue(maxsize=100)
    bus.clients.append(q)
    bus._client_users[id(q)] = user_id
    bus._client_ctx[id(q)] = {"tenant_id": tenant_id, "scope_node_id": "",
                              "entity_mode": entity_mode, "session_id": "sess"}
    return q


def _drained(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


@pytest.fixture()
def bus(monkeypatch):
    from core.auth import auth_store
    from core.org_directory import org_directory
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(auth_store, "session_alive_by_hash", lambda h: True)
    return SSEBroadcaster()


def test_같은_사람의_다른_테넌트_창에는_가지_않는다(bus):
    """★★★ 이것이 1차 구현이 못 잡던 바로 그 경우다.

    한 사람이 두 회사 문맥으로 창을 열어 둘 수 있다. 알림은 **그 알림이 속한 테넌트 창에만**
    가야 한다. `CollaborationEvents.emit()` 을 통과시켜 실제 배선으로 확인한다."""
    ev = CollaborationEvents(broadcaster=bus)
    here = _client(bus, "kim", "tenant_default")
    there = _client(bus, "kim", "tenant_other")

    sent = ev.emit(DECISION_UPDATED, ["kim"], {"id": "dec_1", "status": "DECIDED"},
                   routing_context={"tenant_id": "tenant_default", "scope_node_id": "",
                                    "entity_mode": "REAL"})
    assert _drained(here), "제 테넌트 창에도 안 왔다 — 격리가 아니라 고장이다"
    assert _drained(there) == [], "다른 테넌트 창으로 결정 알림이 갔다"
    assert sent == 1


def test_REAL_알림은_VIRTUAL_창에_가지_않는다(bus):
    """검증 샌드박스(VIRTUAL) 창에 실제 업무 알림이 섞이면, 시험 문맥에서 실제 결정을 본다."""
    ev = CollaborationEvents(broadcaster=bus)
    real = _client(bus, "kim", "tenant_default", entity_mode="REAL")
    virt = _client(bus, "kim", "tenant_default", entity_mode="VIRTUAL")
    ev.emit(DECISION_UPDATED, ["kim"], {"id": "dec_1"},
            routing_context={"tenant_id": "tenant_default", "entity_mode": "REAL"})
    assert _drained(real) and _drained(virt) == []


def test_라우팅_문맥이_없으면_아무에게도_가지_않고_실패로_센다(bus, capsys):
    """⚠️ 「모르니 전부에게」는 격리를 없애는 것과 같다. 대신 **실패로 세어 드러낸다.**"""
    ev = CollaborationEvents(broadcaster=bus)
    q = _client(bus, "kim", "tenant_default")
    assert ev.emit(DECISION_UPDATED, ["kim"], {"id": "dec_1"}) == 0
    assert _drained(q) == []
    assert ev.failures == 1 and ev.last["error"] == "missing_routing_tenant"
    assert "routing" in capsys.readouterr().out.lower()


def test_라우팅_문맥은_브라우저로_나가지_않는다(bus):
    """★★ 판정용 조직 문맥이 payload 에 섞이면, 이번엔 **반대 방향 유출**이 된다."""
    ev = CollaborationEvents(broadcaster=bus)
    q = _client(bus, "kim", "tenant_default")
    ev.emit(DECISION_UPDATED, ["kim"], {"id": "dec_1"},
            routing_context={"tenant_id": "tenant_default", "scope_node_id": "node_secret",
                             "entity_mode": "REAL", "project_id": ""})
    line = _drained(q)[0]
    assert "node_secret" not in line and "tenant_default" not in line


def test_도메인_notify_가_라우팅_문맥을_실제로_넘긴다():
    """★★★ **도메인 → CollaborationEvents** 배선을 직접 탄다.

    ⚠️ 여기가 1차 구현이 놓친 지점이다. 도메인이 문맥을 안 넘기면 아무리 브로드캐스터를 잘
      만들어도 판정 근거가 없다 — 그리고 그 사실은 단위 테스트로는 보이지 않는다."""
    from core.decision_case import DecisionCase

    import core.decision_case as dc
    real = dc.collaboration_events
    seen = {}

    class _Spy:
        """⚠️ 도메인은 `decision_recipients` · `routing_context` 도 이 객체에서 부른다.
        스파이가 그 둘을 안 갖고 있으면 «배선을 탄다» 는 이 테스트 자체가 도메인 코드에서
        터진다 — 진짜 것을 위임해서 **배선만** 관찰한다."""
        failures = 0
        last = None
        decision_recipients = staticmethod(real.decision_recipients)
        routing_context = staticmethod(real.routing_context)

        def emit(self, event, recipients, payload=None, routing_context=None):
            seen["event"] = event
            seen["routing"] = routing_context
            return 1

    dc.collaboration_events = _Spy()
    try:
        DecisionCase._notify("DECISION_UPDATED", {
            "decision_id": "d1", "status": "DECIDED", "updated_at": "2026-08-12",
            "question": "q", "package_version": 1, "participants": [{"user_id": "kim"}],
            "tenant_id": "tenant_default", "scope_id": "node_x",
        }, "kim")
    finally:
        dc.collaboration_events = real

    assert seen.get("routing"), "도메인이 라우팅 문맥을 넘기지 않았다"
    assert seen["routing"]["tenant_id"] == "tenant_default"
    assert seen["routing"]["scope_node_id"] == "node_x"
