"""실시간 이벤트(SSE).

[CL-4] 구독 시 **사용자를 확정해서 브로커에 넘긴다**(작업서 §CL-BE-05).
  ★ 지정 수신자 이벤트(전달·결정·발간 알림)는 이 값으로만 배달된다.

## ★★★ [P0-1B · 2026-08-09] `?as_user=` 를 폐기하고 1회용 접속표로 바꿨다

종전 주석은 이렇게 적혀 있었다 — 「이것은 인증이 아니라 식별이다. 신뢰 가능한 세션으로 바꾸는
일은 `ORG_TRUST_HEADER` 를 끄는 별도 작업이다.」 그 별도 작업이 이것이다.

`?as_user=관리자` 를 적으면 **그 사람으로 구독됐다.** 전달·결정·발간 알림이 남에게 갔다.
EventSource 가 헤더를 못 붙이는 것은 사실이지만, 그 제약의 답은 「자기 신고를 믿는 것」이
아니라 **세션으로 받은 1회용 표를 쓰는 것**이다.

  1. 화면이 세션 토큰으로 `POST /api/v1/auth/sse-ticket` 을 부른다(헤더가 붙는 평범한 요청)
  2. 서버가 30초짜리 opaque 난수를 발급한다(저장소에는 해시만)
  3. EventSource 가 `?ticket=` 으로 붙고, 서버가 **원자적으로 한 번만** 소비한다
  4. 재연결할 때마다 새 표를 받는다

⚠️ **실패해도 `as_user` 로 돌아가지 않는다.** 폴백을 남기면 그것이 곧 우회로다 — 401 로 끊고
  화면이 새 표를 받아 다시 연결하게 한다.

⚠️ 이 파일이 닫는 것은 **신원**뿐이다. 조직·프로젝트 단위 이벤트 격리는 **G1-C 에서 따로**
  닫는다. 여기까지를 「SSE 보안 완료」라고 부르면 안 된다.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.auth import auth_store
from core.broadcaster import factory_broadcaster

router = APIRouter(prefix="/ws", tags=["Realtime Events"])


@router.get("/timeline")
async def subscribe_timeline(ticket: str = Query("", description="POST /auth/sse-ticket 로 받은 1회용 표")):
    """웹 브라우저의 EventSource 객체와 통신하는 엔드포인트.

    ⚠️ 표를 **응답 본문·오류 메시지에 되싣지 않는다.** 티켓은 URL 로 오가므로 접근 로그에 남을
      수 있고, 오류 메시지에까지 실으면 유출면이 하나 더 늘어난다."""
    ctx = auth_store.consume_sse_ticket(ticket)
    if not ctx or not ctx.get("user_id"):
        # 없음·만료·이미 씀을 구분하지 않는다 — 사용자가 할 일은 어느 쪽이든 같다.
        raise HTTPException(status_code=401,
                            detail="실시간 연결 표가 유효하지 않습니다. 다시 연결하십시오.")
    #: ★★ [G1-C1.1] 신원뿐 아니라 **실행 문맥**을 그대로 넘긴다. 이 값들은 발급 시점에 서버가
    #  해석해 표에 묶어 둔 것이고, 화면이 바꿔 신고할 수 없다.
    return StreamingResponse(
        factory_broadcaster.subscribe(
            user_id=ctx["user_id"],
            tenant_id=ctx.get("tenant_id", ""),
            entity_mode=ctx.get("entity_mode", ""),
            session_id=ctx.get("session_id", "")),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 표가 URL 에 있었으므로 이 응답이 어디로도 참조를 흘리지 않게 한다.
            "Referrer-Policy": "no-referrer",
        }
    )
