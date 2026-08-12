"""[CL-4] 협업 알림 — **내 것만 온다.**

## 왜 별도 계층인가 (작업서 §CL-BE-05)

기존 `factory_broadcaster.broadcast()` 는 **연결된 모두에게** 간다. 지금까지는 그래도 됐다 —
공장 진행 상황은 전사 공통 정보였다. 협업은 다르다. "권 부장님이 당신에게 결정을 요청했습니다"
가 전 직원 화면에 뜨면, 그것은 알림이 아니라 유출이다.

★ 그래서 이 계층은 **수신자를 도메인에서 계산**해서 `emit_to()` 로만 보낸다. 화면이 필터링하는
  구조로 만들지 않는다 — 화면 필터는 브라우저 개발자도구에서 걷어낼 수 있고, 그때 이미 데이터는
  클라이언트에 도착해 있다.

## 페이로드에 무엇을 싣지 않는가

**문서 본문·권한 스냅샷·참여자 명단을 싣지 않는다**(§CL-BE-05). 알림은 "무엇이 바뀌었으니 가서
보라"는 신호이고, 실제 내용은 권한 검사를 통과한 조회 API 로 받아야 한다. 알림에 본문을 실으면
권한 검사를 우회하는 두 번째 경로가 생긴다 — 그리고 그 경로는 아무도 감사하지 않는다.
→ 싣는 것은 **ID · 상태 · 발생시각 · 짧은 제목**뿐이다.

## 실패를 삼키는 이유

원장(`decision_ledger`)은 실패를 삼키지 않는다 — 그것이 기록이기 때문이다. 알림은 기록이 아니다.
알림 전송이 실패했다고 결정 기록이 취소되면, 부가 기능이 본업을 망가뜨린다.
→ 여기서는 예외를 잡고 **실패 카운터만 올린다**. 다만 조용히 0 으로 두지 않는다 — 세지 않으면
  "알림이 안 온다"는 신고가 들어와도 확인할 방법이 없다.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

#: 작업서 §CL-BE-05 신규 이벤트. **이 목록 밖의 이름을 쓰지 않는다** — 화면이 모르는 이벤트는
#: 아무 일도 하지 않고 사라진다.
APP_DELIVERY_RECEIVED = "APP_DELIVERY_RECEIVED"
APP_DELIVERY_UPDATED = "APP_DELIVERY_UPDATED"
DECISION_REVIEW_REQUESTED = "DECISION_REVIEW_REQUESTED"
DECISION_UPDATED = "DECISION_UPDATED"
PUBLICATION_REVIEW_REQUESTED = "PUBLICATION_REVIEW_REQUESTED"
PUBLICATION_UPDATED = "PUBLICATION_UPDATED"

EVENTS = (APP_DELIVERY_RECEIVED, APP_DELIVERY_UPDATED,
          DECISION_REVIEW_REQUESTED, DECISION_UPDATED,
          PUBLICATION_REVIEW_REQUESTED, PUBLICATION_UPDATED)

#: 페이로드에 허용되는 키. **이 밖의 키는 버린다.**
#: ⚠️ 화이트리스트인 이유: 나중에 누군가 편의를 위해 `package` 나 `participants` 를 얹는다.
#:   그 순간 알림이 권한 검사를 우회하는 두 번째 조회 경로가 된다.
ALLOWED_KEYS = ("id", "kind", "status", "at", "title", "actor", "version")

#: 제목 길이 상한. 제목도 내용이다 — 결정 문장 전체를 실으면 사실상 문서를 보낸 것이다.
TITLE_MAX = 80


class CollaborationEvents:
    def __init__(self, broadcaster=None):
        self._broadcaster_override = broadcaster
        #: 전송 실패 수. **조용히 0 으로 두지 않는다** — 세지 않으면 "알림이 안 온다"를
        #: 확인할 방법이 없다.
        self.failures = 0
        #: 마지막 전송 결과(운영 점검용). 내용이 아니라 메타만 담는다.
        self.last: Optional[Dict[str, Any]] = None

    @property
    def _broadcaster(self):
        if self._broadcaster_override is not None:
            return self._broadcaster_override
        from core.broadcaster import factory_broadcaster
        return factory_broadcaster

    @staticmethod
    def routing_context(record: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """[G1-C1.4] 도메인 레코드에서 **서버 내부 라우팅 문맥**을 만든다.

        ## 왜 payload 에 넣으면 안 되는가

        1차 구현은 `emit_to` 가 `payload["project_id"]` 를 읽어 테넌트를 판정하게 했다.
        **그런데 그 키는 브라우저로 나가기 전에 `_clean()` 이 지운다**(`ALLOWED_KEYS` 에 없다).
        즉 판정에 쓰려던 값이 판정 지점에 도달하기 전에 사라졌고, 실서비스에서는 언제나
        「근거 없음」이었다. 그런데도 테스트는 초록이었다 — 테스트가 `CollaborationEvents` 를
        건너뛰고 `bus.emit_to()` 를 직접 불렀기 때문이다.

        ★★★ 그래서 **두 통로를 분리한다.**
            · `payload`         브라우저로 나간다. 최소 정보만(`ALLOWED_KEYS`).
            · `routing_context` 서버 안에서만 쓴다. **직렬화하지 않는다.**

        ⚠️ 라우팅 정보를 payload 에 넣으면 두 문제가 동시에 생긴다 — 판정 근거가 사라지거나
          (지금처럼), 아니면 조직 문맥이 브라우저로 새어 나간다. 둘 다 피하려면 통로가 달라야 한다."""
        r = record or {}
        tenant = str(r.get("tenant_id", "") or "").strip()
        scope = str(r.get("enterprise_scope_id", "") or r.get("scope_id", "") or "").strip()
        mode = str(r.get("entity_mode", "") or "").strip()
        if not mode and scope:
            #: 레코드에 실행 모드가 없으면 **그 조직 노드에서** 가져온다. 지어내지 않는다.
            try:
                from core.enterprise_context.repository import ecm_repository as repo
                mode = repo.node_entity_mode(scope) or ""
                if not mode:
                    node = repo.find_node_by_code(scope) or repo.find_node_by_dept(scope)
                    mode = repo.node_entity_mode(node.node_id) if node else ""
            except Exception:
                mode = ""
        return {"tenant_id": tenant, "scope_node_id": scope, "entity_mode": mode,
                "project_id": str(r.get("project_id", "") or "").strip()}

    def emit(self, event_type: str, recipients: Iterable[str],
             payload: Optional[Dict[str, Any]] = None,
             routing_context: Optional[Dict[str, Any]] = None) -> int:
        """지정 수신자에게 알림 1건. 보낸 큐 수를 돌려준다.

        ⚠️ 발신자 자신을 수신자에서 빼지 않는다 — 여러 창을 띄운 사용자가 자기 행동의 결과를
          다른 창에서 못 보면 그것도 버그다. 대신 **본인이 아닌 사람은 절대 넣지 않는다.**

        ⚠️⚠️ [G1-C1.4] `routing_context` 에 테넌트가 없으면 **보내지 않는다.** 같은 사람이
          여러 테넌트 창에 접속해 있을 수 있고, 테넌트를 모르면 어느 창에 보내야 하는지 알 수
          없다. 「모르니 전부에게」는 격리를 없애는 것과 같다. 대신 실패로 세어 드러낸다."""
        if event_type not in EVENTS:
            # 목록 밖 이름은 화면이 모른다. 조용히 보내면 아무 일도 안 일어나고 원인도 안 남는다.
            self.failures += 1
            self.last = {"event": event_type, "sent": 0, "error": "unknown_event_type"}
            return 0
        ctx = dict(routing_context or {})
        if not str(ctx.get("tenant_id", "") or "").strip():
            self.failures += 1
            self.last = {"event": event_type, "sent": 0, "error": "missing_routing_tenant"}
            print(f"⚠️ [CollaborationEvents] '{event_type}' 에 라우팅 테넌트가 없어 **보내지 "
                  f"않았습니다**(G1-C1.4). 도메인이 `routing_context` 를 넘기는지 확인하십시오.")
            return 0
        targets = sorted({str(r).strip() for r in (recipients or []) if str(r).strip()})
        body = self._clean(payload or {})
        body["kind"] = body.get("kind") or event_type
        try:
            sent = self._broadcaster.emit_to(event_type, body, targets, routing_context=ctx)
        except Exception as e:
            # 알림 실패가 결정·발간을 취소시키면 부가 기능이 본업을 망가뜨린다.
            self.failures += 1
            self.last = {"event": event_type, "sent": 0, "error": f"{type(e).__name__}: {e}"}
            return 0
        self.last = {"event": event_type, "sent": sent, "recipients": len(targets)}
        return sent

    @staticmethod
    def _clean(payload: Dict[str, Any]) -> Dict[str, Any]:
        """허용 키만 남기고 제목을 자른다. **문서 본문이 알림으로 새는 경로를 막는다.**"""
        out: Dict[str, Any] = {}
        for k in ALLOWED_KEYS:
            if k not in payload:
                continue
            v = payload[k]
            if v is None:
                continue
            if k == "title":
                v = str(v)[:TITLE_MAX]
            elif not isinstance(v, (str, int, float, bool)):
                # 목록·사전은 싣지 않는다 — 참여자 명단이 곧 조직 정보다.
                continue
            out[k] = v
        return out

    # ── 도메인별 수신자 계산 ──────────────────────────────────────────────
    @staticmethod
    def delivery_recipients(delivery: Dict[str, Any]) -> List[str]:
        """전달 알림은 **보낸 사람과 받는 사람** 둘뿐이다. 부서 전체가 아니다."""
        return [delivery.get("sender_user_id", ""), delivery.get("recipient_user_id", "")]

    @staticmethod
    def decision_recipients(case: Dict[str, Any]) -> List[str]:
        """결정 알림은 **참여자에게만.** 목록에 없는 사람은 안건의 존재도 몰라야 한다
        (`decision_case.queue()` 가 같은 규칙을 쓴다 — 두 곳이 갈라지면 알림이 목록보다 넓어진다)."""
        return [p.get("user_id", "") for p in (case.get("participants") or [])]

    @staticmethod
    def publication_recipients(pub: Dict[str, Any]) -> List[str]:
        """발간 알림은 **작성자와 검토자에게만.**

        ⚠️ 검토가 요청되지 않은 단계에서는 작성자뿐이다 — 아직 아무에게도 부탁하지 않았다."""
        out = [pub.get("created_by", "")]
        out += [r.get("reviewer_id", "") for r in (pub.get("reviews") or [])]
        # 검토자 ID 는 판정 후에야 채워진다. 요청 단계의 수신자는 별도로 넘긴다.
        return out


collaboration_events = CollaborationEvents()
