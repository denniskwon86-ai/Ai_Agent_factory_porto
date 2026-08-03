"""실시간 이벤트(SSE).

[CL-4] 구독 시 **사용자를 확정해서 브로커에 넘긴다**(작업서 §CL-BE-05).
  ★ 지정 수신자 이벤트(전달·결정·발간 알림)는 이 값으로만 배달된다. 넘기지 않으면 그 연결은
    전역 이벤트만 받는다 — 즉 **식별되지 않은 브라우저는 남의 알림을 받지 않는다.**
  ⚠️ EventSource 는 헤더를 붙일 수 없어 `?as_user=` 쿼리를 쓴다(`api/deps` §③). 이것은 인증이
    아니라 식별이다. 지금 단계에서 중요한 것은 "필터가 화면이 아니라 서버에 있다"는 것이고,
    식별을 신뢰 가능한 세션으로 바꾸는 일은 `ORG_TRUST_HEADER` 를 끄는 별도 작업이다.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.deps import Principal, current_principal
from core.broadcaster import factory_broadcaster

router = APIRouter(prefix="/ws", tags=["Realtime Events"])


@router.get("/timeline")
async def subscribe_timeline(p: Principal = Depends(current_principal)):
    """웹 브라우저의 EventSource 객체와 통신하는 엔드포인트."""
    return StreamingResponse(
        factory_broadcaster.subscribe(user_id=p.user_id or ""),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
