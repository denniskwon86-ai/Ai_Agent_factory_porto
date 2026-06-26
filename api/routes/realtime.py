from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from core.broadcaster import factory_broadcaster

router = APIRouter(prefix="/ws", tags=["Realtime Events"])

@router.get("/timeline")
async def subscribe_timeline():
    """웹 브라우저의 EventSource 객체와 통신하는 엔드포인트"""
    return StreamingResponse(
        factory_broadcaster.subscribe(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )