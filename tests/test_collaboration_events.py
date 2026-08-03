"""★★★ [CL-4] 협업 알림 격리 — **내 것만 온다.**

작업서 §10 필수 케이스 11(사용자 A 의 SSE 이벤트가 사용자 B 에게 전달되지 않음)을 여기서
고정한다.

## 왜 이것이 «완료 판정 조건»인가

작업서 §CL-BE-05 는 못을 박았다: "다른 사용자의 이벤트가 현재 클라이언트로 전송되는 구조라면
구현을 완료로 판정하지 않는다." 기존 `factory_broadcaster.broadcast()` 는 **연결된 모두에게**
간다. 공장 진행 상황은 그래도 됐다 — 전사 공통 정보였다. 협업은 다르다.
"권 부장님이 당신에게 결정을 요청했습니다"가 전 직원 화면에 뜨면 알림이 아니라 유출이다.

## 여기서 막는 세 가지 실패

1. **남에게 간다** — 참여자가 아닌 사람에게 배달.
2. **아무에게나 간다** — 수신자 계산이 실패(빈 목록)했을 때 '전체'로 되돌아가는 것.
   실패는 **닫히는 쪽**이어야 한다.
3. **알림이 조회를 대신한다** — 페이로드에 문서 본문·참여자 명단이 실려 권한 검사를 우회하는
   두 번째 경로가 되는 것.
"""
import asyncio

import pytest

from core.broadcaster import SSEBroadcaster
from core.collaboration_events import (APP_DELIVERY_RECEIVED, DECISION_REVIEW_REQUESTED,
                                       DECISION_UPDATED, EVENTS, CollaborationEvents)


class _FakeClient:
    """구독자 한 명 = 큐 하나. 실제 `subscribe()` 와 같은 구조로 등록한다."""

    def __init__(self, b: SSEBroadcaster, user_id: str):
        self.q: asyncio.Queue = asyncio.Queue(maxsize=100)
        b.clients.append(self.q)
        b._client_users[id(self.q)] = user_id

    def drain(self):
        out = []
        while not self.q.empty():
            out.append(self.q.get_nowait())
        return out


@pytest.fixture
def b():
    return SSEBroadcaster()


@pytest.fixture
def ev(b):
    return CollaborationEvents(broadcaster=b)


# ── §10-11 사용자 격리 ────────────────────────────────────────────────────
def test_event_reaches_only_the_named_user(b, ev):
    """★★★ 작업서 §10-11 — A 의 이벤트가 B 에게 가지 않는다."""
    a = _FakeClient(b, "kim")
    other = _FakeClient(b, "lee")
    sent = ev.emit(DECISION_REVIEW_REQUESTED, ["kim"], {"id": "dec_1", "status": "REVIEW_REQUESTED"})
    assert sent == 1
    assert len(a.drain()) == 1
    assert other.drain() == [], "다른 사용자에게 배달되면 그것이 유출이다"


def test_anonymous_client_never_receives_targeted_events(b, ev):
    """★★★ 식별하지 않은 브라우저는 **절대** 지정 수신자 이벤트를 받지 않는다.

    ⚠️ 익명 연결이 받으면 로그인하지 않은 창이 남의 알림을 읽는다."""
    anon = _FakeClient(b, "")
    named = _FakeClient(b, "kim")
    ev.emit(DECISION_UPDATED, ["kim"], {"id": "dec_1"})
    assert anon.drain() == []
    assert len(named.drain()) == 1


def test_empty_recipients_go_to_nobody(b, ev):
    """★★★ 수신자가 비면 **아무에게도** 가지 않는다.

    ⚠️ '비었으니 전체'로 해석하는 순간, 권한 계산이 실패한 이벤트가 전사에 뿌려진다.
      실패는 닫히는 쪽이어야 한다."""
    c1, c2 = _FakeClient(b, "kim"), _FakeClient(b, "lee")
    assert ev.emit(DECISION_UPDATED, [], {"id": "dec_1"}) == 0
    assert c1.drain() == [] and c2.drain() == []


def test_blank_recipient_ids_are_dropped(b, ev):
    """★ 빈 문자열·공백은 수신자가 아니다 — 빈 `user_id` 로 저장된 참여자가 있을 수 있다."""
    anon = _FakeClient(b, "")
    assert ev.emit(DECISION_UPDATED, ["", "   ", None], {"id": "dec_1"}) == 0
    assert anon.drain() == []


def test_global_broadcast_still_reaches_everyone(b):
    """★ 기존 전역 브로드캐스트는 그대로다 — 지금 도는 15개 화면이 여기에 의존한다."""
    c1, c2 = _FakeClient(b, "kim"), _FakeClient(b, "")
    asyncio.run(b.broadcast("FACTORY_PROGRESS", {"step": 3}))
    assert len(c1.drain()) == 1 and len(c2.drain()) == 1


def test_unsubscribe_removes_the_user_mapping(b, ev):
    """★ 연결이 끊기면 매핑도 사라진다 — 남으면 다음 큐가 남의 주소를 물려받는다."""
    async def run():
        gen = b.subscribe(user_id="kim")
        task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)
        assert b._client_users, "구독 중에는 매핑이 있다"
        task.cancel()
        try:
            await gen.aclose()
        except Exception:
            pass
    asyncio.run(run())
    assert b._client_users == {}
    assert b.clients == []


# ── 페이로드 최소화 ───────────────────────────────────────────────────────
def test_payload_drops_document_body_and_participant_list(b, ev):
    """★★★ **문서 본문·참여자 명단을 싣지 않는다**(§CL-BE-05).

    ⚠️ 알림에 본문을 실으면 권한 검사를 우회하는 두 번째 조회 경로가 생기고, 그 경로는
      아무도 감사하지 않는다."""
    c = _FakeClient(b, "kim")
    ev.emit(DECISION_UPDATED, ["kim"], {
        "id": "dec_1", "status": "DECIDED", "at": "2026-08-04",
        "package": {"financial_impact": "연 12억"},      # 실려서는 안 된다
        "participants": ["kim", "lee", "park"],           # 실려서는 안 된다
        "evidence": {"secret": 1},
    })
    line = c.drain()[0]
    assert "dec_1" in line and "DECIDED" in line
    assert "12억" not in line, "문서 본문이 알림으로 새면 안 된다"
    assert "park" not in line, "참여자 명단은 곧 조직 정보다"
    assert "secret" not in line


def test_title_is_truncated(b, ev):
    """★ 제목도 내용이다 — 결정 문장 전체를 실으면 사실상 문서를 보낸 것이다."""
    c = _FakeClient(b, "kim")
    ev.emit(DECISION_UPDATED, ["kim"], {"id": "d", "title": "가" * 500})
    assert "가" * 200 not in c.drain()[0]


def test_unknown_event_type_is_not_sent(b, ev):
    """★★ 목록 밖 이벤트는 보내지 않고 **실패로 센다.**

    ⚠️ 조용히 보내면 화면은 아무 일도 하지 않고, 원인도 남지 않는다."""
    c = _FakeClient(b, "kim")
    assert ev.emit("SOMETHING_ELSE", ["kim"], {"id": "x"}) == 0
    assert c.drain() == []
    assert ev.failures == 1


def test_all_declared_events_are_deliverable(b, ev):
    """★ 작업서 §CL-BE-05 가 요구한 6개 이벤트가 모두 실제로 배달된다."""
    c = _FakeClient(b, "kim")
    for e in EVENTS:
        assert ev.emit(e, ["kim"], {"id": "x"}) == 1
    assert len(c.drain()) == len(EVENTS)


# ── 실패를 삼키되 세어 둔다 ───────────────────────────────────────────────
def test_broadcaster_failure_does_not_raise_but_is_counted(ev):
    """★★ 알림 실패가 결정·발간을 취소시키면 부가 기능이 본업을 망가뜨린다.

    ⚠️ 다만 **조용히 0 으로 두지 않는다** — 세지 않으면 "알림이 안 온다"는 신고를 확인할
      방법이 없다."""
    class _Broken:
        def emit_to(self, *a, **k):
            raise RuntimeError("큐 오류")

    ev._broadcaster_override = _Broken()
    assert ev.emit(APP_DELIVERY_RECEIVED, ["kim"], {"id": "x"}) == 0
    assert ev.failures == 1
    assert "큐 오류" in ev.last["error"]


# ── 도메인 수신자 계산 ────────────────────────────────────────────────────
def test_delivery_recipients_are_only_sender_and_recipient(ev):
    """★★ 전달 알림은 두 사람뿐이다 — 부서 전체가 아니다."""
    r = ev.delivery_recipients({"sender_user_id": "kim", "recipient_user_id": "lee",
                                "enterprise_scope_id": "MNM"})
    assert set(r) == {"kim", "lee"}


def test_decision_recipients_match_the_participant_list(ev):
    """★★★ 결정 알림 수신자는 `queue()` 가 보여주는 사람과 같아야 한다.

    ⚠️ 두 곳이 갈라지면 **안 보이는 안건의 알림**이 온다 — 존재를 숨기기로 한 결정이 알림으로
      새는 것이다."""
    case = {"participants": [{"user_id": "kim", "role": "REQUESTER"},
                             {"user_id": "boss", "role": "DECIDER"}]}
    assert set(ev.decision_recipients(case)) == {"kim", "boss"}


def test_publication_recipients_are_author_and_known_reviewers(ev):
    """★ 검토자가 아직 판정하지 않았으면 수신자에 없다(그 계약이 아직 없기 때문 — 알려진 한계).

    ★★ 모르는 수신자를 '전체'로 대체하지 않는다. 그 순간 대외 발간 검토 요청이 전사에 뿌려진다."""
    pub = {"created_by": "kim",
           "reviews": [{"review_type": "EXECUTIVE", "reviewer_id": "boss"},
                       {"review_type": "LEGAL_DISCLOSURE", "reviewer_id": ""}]}
    r = [x for x in ev.publication_recipients(pub) if x]
    assert set(r) == {"kim", "boss"}
