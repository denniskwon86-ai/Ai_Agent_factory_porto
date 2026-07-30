"""[M2 관문 B-2] 접근 감사 — **은폐는 외부용이고, 내부에는 반드시 남는다.**

## 왜 이 모듈이 필요한가

M2 는 타 조직 자원의 거부를 **404 로 은폐**한다(존재 자체를 알려주지 않는 Data Stealth).
그런데 은폐만 하고 기록하지 않으면 **운영자는 침해 시도를 영원히 볼 수 없다.**
"아무 일도 없었다"와 "누군가 열 번 시도했다"가 똑같이 조용하다.

거부 판정은 여러 곳에서 난다(기준정보 주입 · 목록 · 개별 조회 · MCP). 기록 형식이 곳마다
다르면 추적이 불가능하므로, 판정 로직을 `scoping.py` 한 곳에 모은 것과 같은 이유로
**기록도 한 곳에 모은다.**

## 네 가지 원칙

1. **은폐는 외부용이다.** 응답은 404 로 뭉개도 감사로그에는 **실제 대상 식별자**를 남긴다.
   그러지 않으면 "무엇에 대한 시도였는지" 모르는 기록만 쌓인다.
2. **요청값과 서버 계산값을 둘 다 남긴다.** 무엇을 요구했고(`requested_scope`) 무엇이
   허용됐는지(`actor_scopes`)를 나란히 둬야 **권한 상승 시도**가 보인다. 하나만 남기면
   "정상 조회"와 "남의 범위를 적어 보낸 시도"가 같은 모양이 된다.
3. **감사 기록 실패가 요청을 죽이지 않는다.** 단 실패를 **세어서** 드러낸다 — 조용히
   유실되면 감사로그의 존재 이유가 사라진다(`stats()["write_failures"]`).
4. **append-only.** `llm_call_log` · `quality_outcomes` 와 같은 규약(`data/access_audit.jsonl`).
   감사 기록은 고쳐 쓸 수 있으면 감사가 아니다.

## 무엇을 기록하고 무엇을 기록하지 않는가

**기록한다**: 거부(권한·범위 불일치) · 승인/권한 변경 같은 되돌리기 어려운 조작 ·
샌드박스 토큰 발급·사용.
**기록하지 않는다**: 정상 조회 전건. 명세서 §9.3 은 "조회는 주체·목적·범위·권한 근거를
남긴다"고 하지만, 전건 기록은 로그를 폭증시켜 **정작 봐야 할 거부를 묻어버린다.**
정상 조회의 범위 근거는 응답의 `permission` 메타로 이미 나가고 있다(텔레메트리 관례).

⚠️ **감사로그 자체가 민감정보다** — 누가 무엇을 시도했는지가 담긴다. 열람 API 는 보존기간·
열람권한이 사용자 결정으로 확정된 뒤에 만든다(설계서 §6 열린 질문 4).
"""
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

_LOG_PATH = os.path.join("data", "access_audit.jsonl")
_lock = threading.Lock()
_write_failures = 0

# ── 이벤트 열거값 — 자유 문자열을 쓰지 않는다 ────────────────────────────────
# 문자열을 그때그때 지어내면 같은 사건이 여러 이름으로 쌓여 집계가 불가능해진다.
ACCESS_DENIED_SCOPE_MISMATCH = "ACCESS_DENIED_SCOPE_MISMATCH"   # 조직 범위 불일치
ACCESS_DENIED_UNAUTHENTICATED = "ACCESS_DENIED_UNAUTHENTICATED"  # 식별 없음
ACCESS_DENIED_CLASSIFICATION = "ACCESS_DENIED_CLASSIFICATION"    # 등급 부족
SCOPE_BINDING_CHANGED = "SCOPE_BINDING_CHANGED"                  # 범위·소유 변경
APPROVAL_GRANTED = "APPROVAL_GRANTED"                            # 공용 전환 등 승인
SANDBOX_TOKEN_ISSUED = "SANDBOX_TOKEN_ISSUED"
SANDBOX_TOKEN_USED = "SANDBOX_TOKEN_USED"
# [§7.2] 외부 연계 조회 — "모든 조회에는 요청자·목적·데이터 범위·시각·결과 요약을
#   감사 로그로 남긴다". 거부도 남긴다 — 거부된 시도가 침해 시도의 신호다.
CONNECTOR_QUERY_EXECUTED = "CONNECTOR_QUERY_EXECUTED"
CONNECTOR_QUERY_DENIED = "CONNECTOR_QUERY_DENIED"
# 프로그램 사용여부(IT 관리자) — 배포된 프로그램을 지우는 대신 사용만 막는다.
#   누가 언제 왜 껐는지가 남지 않으면 아무도 다시 켜지 못한다.
PROGRAM_STATUS_CHANGED = "PROGRAM_STATUS_CHANGED"
PROGRAM_USE_BLOCKED = "PROGRAM_USE_BLOCKED"

EVENTS = (
    ACCESS_DENIED_SCOPE_MISMATCH, ACCESS_DENIED_UNAUTHENTICATED,
    ACCESS_DENIED_CLASSIFICATION, SCOPE_BINDING_CHANGED, APPROVAL_GRANTED,
    SANDBOX_TOKEN_ISSUED, SANDBOX_TOKEN_USED,
    CONNECTOR_QUERY_EXECUTED, CONNECTOR_QUERY_DENIED,
    PROGRAM_STATUS_CHANGED, PROGRAM_USE_BLOCKED,
)

#: 식별되지 않은 주체. 빈 문자열로 두면 "기록 누락"과 구분되지 않는다.
ANONYMOUS = "anonymous"


def record(event: str, resource_type: str, resource_id: str,
           actor: str = "", actor_scopes: Optional[Iterable[str]] = None,
           requested_scope: str = "", outcome: str = "denied",
           reason: str = "", detail: str = "") -> bool:
    """감사 이벤트 1건. 성공 여부를 돌려주되 **예외는 던지지 않는다**(요청을 죽이지 않는다).

    ⚠️ `resource_id` 를 비우지 말 것. 404 로 은폐하는 것은 응답이지 기록이 아니다 —
      여기까지 비면 운영자는 "누군가 무언가를 시도했다"만 알고 끝난다."""
    global _write_failures
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event if event in EVENTS else f"UNKNOWN:{event}",
        "actor": actor or ANONYMOUS,
        # 서버가 계산한 값 — 클라이언트가 보낸 것이 아니다.
        "actor_scopes": sorted(set(actor_scopes or ())),
        "resource_type": resource_type or "",
        "resource_id": resource_id or "",
        # 클라이언트가 요청한 범위 — 신뢰하지 않되 **기록은 한다**(상승 시도 탐지).
        "requested_scope": requested_scope or "",
        "outcome": outcome or "denied",
        "reason": reason or "",
        "detail": (detail or "")[:600],
    }
    try:
        with _lock:
            os.makedirs(os.path.dirname(_LOG_PATH) or ".", exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        _write_failures += 1
        # 조용히 넘기지 않는다 — 감사 기록의 유실 자체가 사건이다.
        print(f"⚠️ [audit] 감사 기록 실패({_write_failures}회): {e}")
        return False


def denied_scope(resource_type: str, resource_id: str, actor: str,
                 actor_scopes: Optional[Iterable[str]] = None,
                 requested_scope: str = "", detail: str = "") -> bool:
    """범위 불일치 거부 — 호출부가 매번 이벤트 이름을 적지 않게 하는 지름길.

    거부 지점이 여러 곳이라 이름을 손으로 적게 두면 오타 하나로 그 경로만 집계에서 빠진다."""
    return record(ACCESS_DENIED_SCOPE_MISMATCH, resource_type, resource_id,
                  actor=actor, actor_scopes=actor_scopes,
                  requested_scope=requested_scope, outcome="denied",
                  reason="scope_mismatch", detail=detail)


def read_events(path: str = "") -> List[Dict[str, Any]]:
    """전 이벤트. 실행 중 append 되므로 **깨진 줄은 건너뛴다**(전체 폐기 금지)."""
    out: List[Dict[str, Any]] = []
    p = path or _LOG_PATH
    if not os.path.exists(p):
        return out
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def recent(limit: int = 50, event: str = "") -> List[Dict[str, Any]]:
    """최근 이벤트(최신 우선). `event` 로 종류를 좁힌다."""
    evs = read_events()
    if event:
        evs = [e for e in evs if e.get("event") == event]
    return list(reversed(evs))[:max(1, limit)]


def stats() -> Dict[str, Any]:
    """집계 + **기록 실패 횟수**. 실패가 0 이 아니면 이 로그는 불완전하다 —
    그 사실을 감추면 "거부가 없었다"는 거짓 안심을 준다."""
    evs = read_events()
    by_event: Dict[str, int] = {}
    by_actor: Dict[str, int] = {}
    for e in evs:
        by_event[e.get("event", "?")] = by_event.get(e.get("event", "?"), 0) + 1
        by_actor[e.get("actor", "?")] = by_actor.get(e.get("actor", "?"), 0) + 1
    return {
        "total": len(evs),
        "by_event": by_event,
        "by_actor": by_actor,
        "write_failures": _write_failures,
        "note": ("`write_failures` 가 0 이 아니면 이 로그는 불완전합니다 — "
                 "거부 건수를 실제보다 적게 보고 있습니다."),
    }
