import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Any

class SSEBroadcaster:
    """
    FastAPI Server-Sent Events (SSE) 브로드캐스터.
    Redis 외부 의존성 없이 asyncio.Queue만을 사용하여 실시간 통신망을 구축합니다.
    """
    def __init__(self):
        # 연결된 클라이언트들의 큐를 관리하는 리스트
        self.clients: list[asyncio.Queue] = []

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """클라이언트(웹 브라우저) 구독 및 연결 유지"""
        q = asyncio.Queue()
        self.clients.append(q)
        try:
            while True:
                try:
                    # 15초 타임아웃을 걸어 큐 대기 (에이전트 장기 추론 타임아웃 방어)
                    event_data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 타임아웃 발생 시 브라우저 연결 유지를 위한 SSE 표준 Ping(Heartbeat) 발송
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            # 브라우저 탭을 닫거나 연결 종료 시 메모리 누수 방지를 위한 큐 정리
            self.clients.remove(q)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]):
        """시스템 전역에서 호출되는 실시간 상태 Push 메서드"""
        message = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "payload": payload
        }
        # 연결된 모든 클라이언트 큐에 비동기 Non-blocking 전송
        for q in self.clients:
            await q.put(message)

# 애플리케이션 전역에서 상태를 공유할 싱글톤 인스턴스
factory_broadcaster = SSEBroadcaster()