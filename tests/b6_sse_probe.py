"""[B6-CONTEXT-SSE-01 · 결정 3] 합성 표식 하나를 **실제 브로드캐스터로** 발행하는 하네스.

## 왜 이런 모양인가

실시간 전달을 재려면 이벤트가 하나 있어야 하는데, **읽기만 하는 무해한 제품 행동 중에
timeline 이벤트를 내는 것을 찾지 못했다.** 실제 생산자는 스프린트 계열(`pause_sprint` →
`SPRINT_PAUSED`)이고 그것은 활성 task·엔진 상태를 요구한다. `NODE_COMPLETED` 는 감독
데몬이 **LLM 을 태울 수 있어** 표식으로 쓸 수 없다.

★ 그래서 **합성 표식**을 쓴다. 다만 «전달 경로» 는 조금도 흉내 내지 않는다:

    이 하네스 → factory_broadcaster.broadcast(실제)
              → 서버의 소유권·문맥 필터(실제)
              → /ws/timeline(실제) → EventSource(실제) → 기존 store 의 일반 로그(실제)

⚠️ 그래서 결과는 「**합성 생산자 + 실제 제품 SSE 전달/필터/소비**」다. 실제 업무 행동이
  이벤트를 낸다는 증거도, 시뮬레이션 parity 증거도 **아니다.**

## 안전 (확인하고 적는다)

- `SupervisorDaemon.handle_event` 는 `NODE_COMPLETED` **그리고** 감시 노드일 때만 움직인다
  (`core/supervisor_daemon.py`). 이 표식은 둘 다 아니므로 **LLM 0 · 외부 전송 0**.
- 브로드캐스터의 내부 리스너는 그 하나뿐이다(`add_internal_listener` 호출처 1곳).
- `_broadcast_scope='global'` 을 **싣지 않는다.** 전사 전송은 필터를 통째로 건너뛴다.
- `project_id` 는 **허용 목록**으로 막는다. 격리 fixture 말고는 발행하지 않는다.

## 어디에 붙이나

⚠️ **제품 라우터에 디버그 발행 API 를 추가하지 않는다.** 이 모듈은 부르지 않으면 아무 일도
  하지 않는 «시험 영역» 코드이고, 임시 접근점은 **격리 런처**(`run_isolated.py`, 워크트리
  전용)가 `install_probe_route(app)` 로 붙인다. 운영 기동 경로에는 존재하지 않는다.
"""
import re
from typing import Iterable

#: ⚠️⚠️ `Request` 는 **모듈 전역에서** import 한다. 함수 안에서만 가져오면 FastAPI 가
#:   타입 주석을 «쿼리 파라미터» 로 읽어 모든 호출이 422 가 된다 — 저장소가 이미 한 번
#:   겪은 사고다(`tests/plugin_test_auth.py` 머리말). 실제로 여기서도 같은 422 를 봤다.
from fastapi import HTTPException, Request

#: 이 하네스가 낼 수 있는 **단 하나의** 이벤트 종류.
EVENT_TYPE = "B6_SCOPE_PROBE"

#: 표식 문자열 형식 — 로그에 그대로 찍히므로 눈으로 찾을 수 있게 좁게 잡는다.
_MARKER_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

#: ★★★ [검토 2026-09-19] **화면이 읽는 칸에 실어야 보인다.**
#:
#:  ⚠️ 종전에는 `marker`·`note` 만 실었다. 그런데 화면 경로는
#:    `store.logs → factoryViewModel.toEvents → ContextInspector 「최근 실행 기록」` 이고,
#:    `toEvents` 의 표시 문자열은 **`event`/`message`/`text`/`status`** 에서만 나온다.
#:    그래서 전달·소비는 되는데 **표시만** 안 됐다 — 「로그를 그리는 자리가 없다」가 아니었다.
#:  ★ 제품 mapper·화면을 바꾸지 않는다. 하네스가 **기존 칸**(`message`)에 싣는다.
#:  ⚠️ 문구는 **서버가 만든다.** 호출자가 임의 `message` 를 통과시키면 그 순간 이 접근점이
#:    「아무 문자열이나 실시간으로 밀어 넣는 도구」가 된다.
_MESSAGE_PREFIX = "[SYNTHETIC B6] "

#: 로컬 루프백만. 다른 기계에서 부를 수 있으면 그것은 더 이상 «격리» 가 아니다.
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def install_probe_route(app, allowed_project_ids: Iterable[str], path: str = "/__isolated__/b6-sse-probe"):
    """격리 서버 **프로세스 안**에 임시 발행점을 붙인다.

    ★ 여기서 붙이는 이유: 발행이 **실제 SSE 를 제공하는 그 프로세스/이벤트 루프**에서
      일어나야 전달 증거가 된다. 별도 파이썬 프로세스에서 브로드캐스터를 부르면 그것은
      그 프로세스 안의 구독자에게만 가고, 서버의 연결은 아무것도 받지 않는다.
    """
    allowed = frozenset(str(p).strip() for p in allowed_project_ids if str(p).strip())
    if not allowed:
        raise ValueError("허용할 fixture project_id 를 적어도 하나 주십시오.")

    async def publish(request: Request):
        host = (request.client.host if request.client else "") or ""
        if host not in _LOCAL_HOSTS:
            raise HTTPException(status_code=403, detail="로컬에서만 부를 수 있습니다.")
        body = await request.json() if await request.body() else {}
        pid = str(body.get("project_id") or "").strip()
        marker = str(body.get("marker") or "").strip()
        if pid not in allowed:
            #: ⚠️ 허용 목록 밖은 **거절**한다. 「아무 프로젝트나 발행」은 실시간 경계를 뚫는 도구다.
            raise HTTPException(status_code=403, detail="이 격리 fixture 가 아닙니다.")
        if not _MARKER_RE.match(marker):
            raise HTTPException(status_code=400, detail="marker 형식이 맞지 않습니다.")

        from core.broadcaster import factory_broadcaster
        #: ★ 페이로드에 `_broadcast_scope` 를 넣지 않는다 — 소유권·문맥 필터를 그대로 태운다.
        payload = {"project_id": pid, "marker": marker,
                   #: 표시용 칸 — 값은 **검증된 marker 로부터 서버가** 만든다(고정 접두어).
                   "message": _MESSAGE_PREFIX + marker,
                   "note": "격리 검증용 합성 표식(B6). 업무 데이터 아님."}
        await factory_broadcaster.broadcast(EVENT_TYPE, payload)
        return {"status": "success", "data": {"event": EVENT_TYPE, "project_id": pid,
                                              "marker": marker}}

    app.add_api_route(path, publish, methods=["POST"], include_in_schema=False)
    return path
