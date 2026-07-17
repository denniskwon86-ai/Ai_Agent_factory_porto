import asyncio
import json
import os
import urllib.request
from datetime import datetime
from typing import AsyncGenerator, Dict, Any
from fastapi.encoders import jsonable_encoder  #  Pydantic 객체를 안전하게 변환하는 만능 인코더 추가

class SSEBroadcaster:
    """
    FastAPI Server-Sent Events (SSE) 브로드캐스터.
    Redis 외부 의존성 없이 asyncio.Queue만을 사용하여 실시간 통신망을 구축합니다.
    """
    def __init__(self):
        self.clients: list[asyncio.Queue] = []
        self.internal_listeners = []  # 내부 파이썬 콜백 함수들 (슈퍼바이저 데몬 등)

    def add_internal_listener(self, callback):
        """내부 데몬용 이벤트 구독 (async callback)"""
        self.internal_listeners.append(callback)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """클라이언트(웹 브라우저) 구독 및 연결 유지"""
        q = asyncio.Queue()
        self.clients.append(q)
        try:
            while True:
                try:
                    event_data = await asyncio.wait_for(q.get(), timeout=15.0)
                    
                    #  [핵심 조치] Pydantic 모델, datetime 등 직렬화 불가 객체를 기본 파이썬 타입(dict, str)으로 강제 분해
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
        # SSE 클라이언트 전송
        for q in self.clients:
            await q.put(message)
            
        # 내부 리스너 비동기 실행 (슈퍼바이저 데몬용)
        for callback in self.internal_listeners:
            asyncio.create_task(callback(event_type, payload))

    async def send_alert(self, message: str):
        """Slack/Teams 등 Webhook 채널로 긴급 알람 전송 (HOTL, 에러 발생 시)"""
        webhook_url = os.environ.get("ALERT_WEBHOOK_URL")
        if not webhook_url:
            print(f"⚠️ [Alert] ALERT_WEBHOOK_URL이 설정되지 않아 알람을 전송할 수 없습니다: {message}")
            return
            
        payload = json.dumps({"text": f" [AI Factory Studio Alert] {message}"}).encode('utf-8')
        req = urllib.request.Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        
        def _send():
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status >= 300:
                        print(f"⚠️ [Alert] Webhook 전송 실패: {response.status}")
            except Exception as e:
                print(f"⚠️ [Alert] Webhook 전송 중 오류 발생: {e}")
                
        await asyncio.to_thread(_send)

factory_broadcaster = SSEBroadcaster()