import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any
from fastapi.encoders import jsonable_encoder  # 🚨 Pydantic 객체를 안전하게 변환하는 만능 인코더 추가

class SSEBroadcaster:
    """
    FastAPI Server-Sent Events (SSE) 브로드캐스터.
    Redis 외부 의존성 없이 asyncio.Queue만을 사용하여 실시간 통신망을 구축합니다.
    """
    def __init__(self):
        self.clients: list[asyncio.Queue] = []

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """클라이언트(웹 브라우저) 구독 및 연결 유지"""
        q = asyncio.Queue()
        self.clients.append(q)
        try:
            while True:
                try:
                    event_data = await asyncio.wait_for(q.get(), timeout=15.0)
                    
                    # 🚨 [핵심 조치] Pydantic 모델, datetime 등 직렬화 불가 객체를 기본 파이썬 타입(dict, str)으로 강제 분해
                    safe_data = jsonable_encoder(event_data)
                    
                    yield f"data: {json.dumps(safe_data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            self.clients.remove(q)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]):
        """시스템 전역에서 호출되는 실시간 상태 Push 메서드"""
        message = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "payload": payload
        }
        for q in self.clients:
            await q.put(message)

factory_broadcaster = SSEBroadcaster()