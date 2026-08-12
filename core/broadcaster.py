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
        # [CL-4] 큐 → 구독자 사용자 ID. **전역 브로드캐스트와 지정 수신자를 구분하기 위한 것.**
        #   ⚠️ 기존 `clients` 목록은 그대로 둔다 — 지금 도는 15개 화면이 전역 이벤트에 의존한다.
        self._client_users: dict[int, str] = {}
        #: [G1-C1.1] 큐 → 구독 문맥(테넌트·실행모드·세션). 신원만으로는 이벤트를 가를 수 없다.
        self._client_ctx: dict[int, dict] = {}
        self.internal_listeners = []  # 내부 파이썬 콜백 함수들 (슈퍼바이저 데몬 등)

    def add_internal_listener(self, callback):
        """내부 데몬용 이벤트 구독 (async callback)"""
        self.internal_listeners.append(callback)

    async def subscribe(self, user_id: str = "", tenant_id: str = "",
                        scope_node_id: str = "", entity_mode: str = "",
                        session_id: str = "") -> AsyncGenerator[str, None]:
        """클라이언트(웹 브라우저) 구독 및 연결 유지.

        [CL-4] `user_id` 는 **지정 수신자 이벤트를 받기 위한 주소**다. 비우면 전역 이벤트만
        받는다 — 익명 연결이 남의 결정·발간 알림을 받는 일은 없어야 한다(작업서 §CL-BE-05).

        ★★ [G1-C01] 「인증 principal 과 허용 scope 를 등록한다」에 대해 — **scope 는 여기서
          굳히지 않는다.** 등록하는 것은 `user_id` 하나이고, 권한은 이벤트를 보낼 때마다
          `org_directory.resolve_scope` 로 다시 해석한다.

          구독 시점의 scope 를 들고 있으면 코드는 더 짧아지지만, 이 연결은 최대 12시간 산다.
          그 사이 사람을 다른 부서로 옮기거나 계정을 폐지해도 **이미 열린 스트림으로는 옛
          권한이 계속 흐른다.** 그것은 화면을 새로고침해야만 사라지는 종류의 유출이고,
          아무도 그것을 보지 못한다. `api/deps` 가 세션 토큰에 권한을 담지 않는 이유와 같다."""
        # 유한 큐: 죽은/느린 클라이언트의 큐가 무한히 쌓여 메모리를 잠식하는 것 방지
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.clients.append(q)
        self._client_users[id(q)] = (user_id or "").strip()
        self._client_ctx[id(q)] = {"tenant_id": (tenant_id or "").strip(),
                                   "scope_node_id": (scope_node_id or "").strip(),
                                   "entity_mode": (entity_mode or "").strip(),
                                   "session_id": (session_id or "").strip()}
        try:
            while True:
                try:
                    # broadcast 가 이미 직렬화한 문자열을 그대로 전달(클라이언트 수만큼 재직렬화 방지)
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield line
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            # CancelledError 외의 어떤 종료 경로(인코딩 예외 등)에서도 큐를 반드시 회수
            # - 회수 누락 시 broadcast 가 좀비 큐를 영원히 채우는 누수가 된다
            try:
                self.clients.remove(q)
            except ValueError:
                pass
            self._client_users.pop(id(q), None)
            self._client_ctx.pop(id(q), None)

    # ── [G1-C] 조직·프로젝트 격리 ────────────────────────────────────────────
    #: 분류를 못 붙인 이벤트를 **한 번만** 경고한다. 매 이벤트 찍으면 로그가 묻히고,
    #: 아예 안 찍으면 사라진 이벤트를 아무도 모른다.
    _warned_unclassified: set = set()

    #: 「이 이벤트는 정말로 전사 공통이다」를 **적어서** 밝히는 표식. 지금은 쓰는 곳이 없다.
    #: ⚠️ 새 이벤트를 만들면서 이 값을 붙이는 것은 «필터를 끄는 것» 이다. 붙이기 전에
    #:   그 이벤트에 남의 조직 정보가 실려 있지 않은지 확인해야 한다.
    GLOBAL_MARKER = "_broadcast_scope"

    def _resolve_target(self, event_type: str, payload: Dict[str, Any]):
        """이 이벤트를 누구에게 보낼지 판정할 재료를 만든다.

        돌려주는 것: `(전사공통인가, 소유권정보 or None)`.
        소유권 정보가 `None` 이면 **아무에게도 보내지 않는다.**

        ★ 소유권 파일을 **이벤트당 한 번만** 읽는다. 구독자마다 읽으면 접속자 수만큼
          파일 I/O 가 늘고, 이벤트는 노드가 끝날 때마다 나온다."""
        d = payload if isinstance(payload, dict) else {}
        if str(d.get(self.GLOBAL_MARKER, "")).strip() == "global":
            return True, None
        pid = str(d.get("project_id") or "").strip()
        if not pid:
            # ⚠️ **분류가 없으면 보내지 않는다.** 「분류를 못 붙였으니 전체에게」로 해석하는
            #   순간 G1-C 가 무의미해진다 — 실패는 닫히는 쪽이어야 한다.
            #   지금 실제 호출처는 전부 `project_id` 를 싣는다(오케스트레이터 12 · VisionQA ·
            #   토론). 그러므로 이 경고가 뜬다는 것은 **새로 생긴 경로가 분류를 빠뜨렸다**는 뜻이다.
            if event_type not in self._warned_unclassified:
                self._warned_unclassified.add(event_type)
                print(f"⚠️ [Broadcaster] '{event_type}' 이벤트에 project_id 가 없어 "
                      f"**아무에게도 보내지 않았습니다**(G1-C). 이벤트에 project_id 를 싣거나, "
                      f"정말 전사 공통이면 payload['{self.GLOBAL_MARKER}']='global' 을 명시하십시오.")
            return False, None
        try:
            from core.paths import workspace_path
            from core.project_visibility import read_project_ownership
            return False, read_project_ownership(workspace_path(pid))
        except Exception as e:                                   # pragma: no cover
            print(f"⚠️ [Broadcaster] '{event_type}' 소유권 판독 실패({pid}): {e} — 보내지 않습니다.")
            return False, None

    @staticmethod
    def _context_matches(ctx: dict, own) -> bool:
        """구독 문맥과 자원 문맥이 같은가 (테넌트 · 조직범위 · REAL/VIRTUAL).

        ★★ [G1-C1.1] 조직 권한만으로는 부족하다. `visibility="company"` 는 **테넌트를 넘어**
          통과할 수 있고, 검증 샌드박스(VIRTUAL) 자료가 실제 문맥(REAL) 화면에 섞이면
          시험 산출물이 실제 진행 상황처럼 보인다.

        ★★★ [G1-C1.2] **문맥이 없는 구독은 이제 아무것도 못 받는다.** 종전에는 「비어 있으면
          대조하지 않는다」였고, 그것이 곧 fail-open 이었다 — 문맥을 못 만든 연결이 오히려
          경계 없이 전부 받았다. 티켓에 `context_version` 을 봉인하고 옛 표를 거절하므로,
          살아 있는 구독은 **반드시** 테넌트와 실행 모드를 갖는다.

        ⚠️ `scope_node_id` 는 **권한이 아니라 «지금 무엇을 보기로 했는가»** 다. 비어 있으면
          「전체」를 고른 것이므로 좁히지 않는다 — 여기서 막으면 범위를 안 고른 사람이
          아무것도 못 본다. 권한 경계는 `ownership_visible` 이 따로 지킨다."""
        own = own or {}
        c_tenant = str(ctx.get("tenant_id", "") or "")
        c_mode = str(ctx.get("entity_mode", "") or "")
        if not c_tenant or not c_mode:
            return False                 # 문맥 없는 구독 = 경계를 확인할 수 없음 = 차단
        if str(own.get("tenant_id", "") or "") not in ("", c_tenant):
            return False
        if str(own.get("entity_mode", "") or "") not in ("", c_mode):
            return False
        try:
            from core.project_visibility import scope_covers
            return scope_covers(str(ctx.get("scope_node_id", "") or ""),
                                str(own.get("enterprise_scope_id", "") or ""))
        except Exception:
            return True                  # 범위 좁히기 실패는 권한 경계가 아니다(위 주석 참조)

    def _may_receive(self, user_id: str, is_global: bool, own, ctx: dict = None) -> bool:
        """이 구독자가 이 이벤트를 받아도 되는가.

        ⚠️ 권한을 **보낼 때마다 다시 해석한다.** 구독 시점에 굳혀 두면 SSE 연결이 살아 있는
          동안(최대 12시간) 회수한 권한이 계속 유효하다 — `api/deps` 가 세션 토큰에 권한을
          담지 않는 이유와 같다. `resolve_scope` 는 캐시되고 조직 쓰기 때 무효화된다."""
        uid = (user_id or "").strip()
        if not uid:
            # 익명 구독자는 전사 공통 이벤트만 받는다. E0-1B 이후 티켓이 신원을 요구하므로
            # 실제로는 여기 오지 않지만, 규칙을 코드에 남겨 둔다.
            return is_global
        if is_global:
            return True
        if own is None:
            return False
        if not self._context_matches(ctx or {}, own):
            return False
        # [G1-C1.3] 진행 이벤트도 마찬가지다 — 로그아웃한 창에 공장 상태가 계속 흐르면 안 된다.
        if not self._session_alive(ctx or {}):
            return False
        try:
            from core.org_directory import org_directory
            from core.project_visibility import ownership_visible
            return ownership_visible(org_directory.resolve_scope(uid), uid, own)
        except Exception:
            return False                 # 판정 실패가 노출로 이어지지 않는다

    async def broadcast(self, event_type: str, payload: Dict[str, Any]):
        """시스템 전역에서 호출되는 실시간 상태 Push 메서드.

        ★★★ [G1-C · 2026-08-09] 이름은 `broadcast` 지만 **더 이상 모두에게 가지 않는다.**
          종전에는 연결된 모든 큐에 그대로 넣었다. 그래서 다른 사업부의 프로젝트가 어느
          단계에 있고 무엇이 실패했는지가 **그 프로젝트를 목록에서 볼 수도 없는 사람의
          화면에 실시간으로 흘렀다.** `NODE_COMPLETED` 는 `state` 전체를 싣는다.

          이름을 바꾸지 않는 이유: 호출처 17곳의 의미는 그대로 「진행 상황을 알린다」이고,
          바뀐 것은 **누가 받는가** 뿐이다. 대신 이 주석을 남긴다.

        ⚠️ 내부 리스너(슈퍼바이저 데몬)는 **거르지 않는다.** 그것은 사용자 화면이 아니라
          서버 자신이며, 걸러 버리면 감독이 자기 공장을 못 본다."""
        message = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "payload": payload
        }
        # 직렬화는 브로드캐스트 시 1회만 수행(과거: 클라이언트별 매 이벤트 재직렬화)
        # Pydantic 모델, datetime 등 직렬화 불가 객체를 기본 파이썬 타입으로 강제 분해
        try:
            safe_data = jsonable_encoder(message)
            line = f"data: {json.dumps(safe_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            print(f"⚠️ [Broadcaster] 이벤트 직렬화 실패({event_type}): {e}")
            return

        # [G1-C] 보낼 대상 판정 재료를 **한 번만** 만든다(구독자 수와 무관한 비용).
        is_global, own = self._resolve_target(event_type, payload)

        # SSE 클라이언트 전송 - 가득 찬 큐(느린/죽은 클라이언트)는 가장 오래된 이벤트를 버리고 최신 유지
        for q in list(self.clients):
            if not self._may_receive(self._client_users.get(id(q), ""), is_global, own,
                                     self._client_ctx.get(id(q), {})):
                continue
            try:
                q.put_nowait(line)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(line)
                except Exception:
                    pass

        # 내부 리스너 비동기 실행 (슈퍼바이저 데몬용)
        for callback in self.internal_listeners:
            asyncio.create_task(callback(event_type, payload))

    # ── [CL-4] 지정 수신자 이벤트 ────────────────────────────────────────────
    def emit_to(self, event_type: str, payload: Dict[str, Any],
                recipients) -> int:
        """**지정한 사용자에게만** 보낸다. 보낸 큐 수를 돌려준다.

        ★★ 이것이 CL-4 의 핵심이다. 기존 `broadcast()` 는 **모두에게** 간다 — 협업 이벤트를
          거기에 실으면 A 의 결정 요청이 B 의 화면에 뜬다(작업서 §CL-BE-05: "다른 사용자의
          이벤트가 현재 클라이언트로 전송되는 구조라면 구현을 완료로 판정하지 않는다").

        ⚠️ **수신자가 비어 있으면 아무에게도 보내지 않는다.** '비었으니 전체'로 해석하는 순간
          권한 계산이 실패한 이벤트가 전사에 뿌려진다 — 실패는 닫히는 쪽이어야 한다.
        ⚠️ 익명 구독자(사용자 미지정)는 **절대 받지 않는다.** 받으면 식별하지 않은 브라우저가
          남의 알림을 읽는다.

        `broadcast()` 와 달리 async 가 아니다 — `put_nowait` 만 쓰므로 동기 도메인 코드
        (`decision_case`, `publication`)에서 이벤트 루프 없이도 부를 수 있다.

        ⚠️ [G1-C] **여기에는 프로젝트 필터를 걸지 않는다.** 수신자를 이미 도메인이 계산했고,
          그 계산의 요점이 「이 프로젝트 밖에 있는 사람에게도 결정을 요청한다」이기 때문이다
          — 승인자·데이터 오너는 대개 그 프로젝트의 부서 소속이 아니다. 여기에 프로젝트
          가시성을 겹쳐 걸면 **결정 요청이 결정권자에게 도달하지 못한다.**
          `broadcast()` 의 필터는 «분류 없이 모두에게 가던 것» 을 막는 것이고, 이쪽은 애초에
          분류해서 보내는 경로다. 둘의 목적이 다르다."""
        targets = {str(r).strip() for r in (recipients or []) if str(r).strip()}
        if not targets:
            return 0
        message = {"type": event_type, "timestamp": datetime.now().isoformat(),
                   "payload": payload}
        try:
            line = f"data: {json.dumps(jsonable_encoder(message), ensure_ascii=False)}\n\n"
        except Exception as e:
            print(f"⚠️ [Broadcaster] 이벤트 직렬화 실패({event_type}): {e}")
            return 0
        #: 이 알림이 어느 문맥의 것인가. 프로젝트가 적혀 있을 때만 알 수 있다.
        own_ctx = None
        pid = str((payload or {}).get("project_id") or "").strip() if isinstance(payload, dict) else ""
        if pid:
            try:
                from core.paths import workspace_path
                from core.project_visibility import read_project_ownership
                own_ctx = read_project_ownership(workspace_path(pid))
            except Exception:
                own_ctx = None
        sent = 0
        for q in list(self.clients):
            uid = self._client_users.get(id(q), "")
            if not uid or uid not in targets:
                continue
            # ★★ [G1-C1.1] **지금도 유효한 계정인가.** 수신자는 도메인이 계산했지만 그것은
            #   «그때» 의 판단이다. SSE 연결은 최대 12시간 살아 있어서, 그 사이 계정을 폐지해도
            #   이미 열린 스트림으로는 결정·발간 알림이 계속 간다.
            #   ⚠️ 프로젝트 필터는 여기 걸지 않는다 — 승인자는 대개 그 프로젝트 밖에 있다.
            if not self._recipient_still_valid(uid, self._client_ctx.get(id(q), {})):
                continue
            # ★★ [G1-C1.1] **다른 테넌트 창으로는 보내지 않는다.** 같은 사람이 여러 문맥으로
            #   접속해 있을 수 있고, 테넌트는 「보안·계약·데이터 격리 최상위 경계」다.
            #   ⚠️ 판정 근거(`project_id`)가 없으면 대조하지 않는다 — 알림 대부분은 프로젝트에
            #     매이지 않고, 근거 없이 막으면 결정 요청이 사라진다.
            if not self._context_matches(self._client_ctx.get(id(q), {}), own_ctx):
                continue
            try:
                q.put_nowait(line)
                sent += 1
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(line)
                    sent += 1
                except Exception:
                    pass
        return sent

    @staticmethod
    def _session_alive(ctx: dict) -> bool:
        """이 구독의 세션이 아직 살아 있는가.

        ⚠️ 봉인된 세션 해시가 없으면 **살아 있다고 답하지 않는다.** 없다는 것은 확인할 수 없다는
          뜻이고, 확인할 수 없는 것을 통과로 두면 이 검사도 장식이 된다."""
        try:
            from core.auth import auth_store
            return bool(auth_store.session_alive_by_hash(
                str((ctx or {}).get("session_id", "") or "")))
        except Exception:
            return False

    @staticmethod
    def _recipient_still_valid(user_id: str, ctx: dict) -> bool:
        """폐지되지 않은 계정인가. 실패하면 **보내지 않는다.**

        ⚠️ 「조회 실패니까 일단 보낸다」로 두면, 인증 저장소가 흔들리는 순간이 곧 알림 유출
          구간이 된다. 알림 한 건을 놓치는 쪽이 낫다 — 사용자는 화면을 새로고침하면 본다."""
        # ★★★ [G1-C1.3] **로그아웃한 세션에는 보내지 않는다.**
        #   SSE 는 한 번 열리면 최대 12시간 산다. 그래서 로그아웃·비밀번호 변경·관리자의 세션
        #   강제 폐기가 **이미 열린 스트림에는 닿지 않았다** — 사용자는 나갔다고 믿는데 그
        #   브라우저는 계속 알림을 받는다. 「나갔다」와 「안 보인다」가 다르면 그것은 유출이다.
        #   ⚠️ 티켓에 세션 해시가 없으면(옛 구독) 이 검사를 건너뛰지 **않는다** — 없다는 것은
        #     확인할 수 없다는 뜻이고, 확인할 수 없는 것을 통과로 두면 이것도 장식이 된다.
        if not SSEBroadcaster._session_alive(ctx or {}):
            return False
        try:
            from core.org_directory import org_directory
            # ⚠️ **조직을 도입하기 전에는 막지 않는다.** 부서·사용자가 없는 환경에서 이 검사를
            #   그대로 적용하면 «아무도 유효하지 않다» 가 되어 알림이 전부 사라진다. 그것은
            #   통제가 아니라 고장이다 — `AccessScope` 주석이 못박은 저장소 공통 계약이다.
            if org_directory.is_bootstrap():
                return True
            u = org_directory.get_user(user_id)
            if not u:
                return False
            status = u.get("status", "active") if isinstance(u, dict) else getattr(u, "status", "active")
            return str(status) == "active"
        except Exception:
            return False

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