"""[M2 §4.3] VIRTUAL Sandbox capability token — **"권한 승급"이 아니다.**

## 문제

E3(가상 기업 Sandbox)에서는 `entity_mode` 완전 일치 규칙이 걸림돌이 된다. 가상 문맥에서
일하려면 가상 데이터를 봐야 하는데, 가시성 판정은 REAL/VIRTUAL 을 엄격히 분리한다
(REAL 문맥에 VIRTUAL 데이터가 섞이면 그게 곧 오염이다).

가장 쉬운 해결은 **사용자의 실제 조직 권한을 올려 주는 것**이고, 그것이 정확히 금지된 방식이다.
가상 실험을 하려고 실제 권한을 올리면, 실험이 끝난 뒤에도 그 권한이 남는다 — 임시로 준 권한이
영구가 되는 것은 이 저장소가 이미 다른 곳에서 겪은 유형이다(한시 예외가 영구 규칙이 된 것).

## 이 토큰이 지키는 네 가지

1. **짧은 만료**(기본 30분). 만료된 토큰은 거부되고 `SANDBOX_TOKEN_EXPIRED` 로 남는다.
2. **읽기 전용.** 쓰기 요청에는 어떤 경우에도 쓰이지 않는다 — 가상 문맥의 실험이 실제 데이터를
   바꿀 경로는 존재하지 않아야 한다.
3. **가상 조직 범위로만 유효.** 토큰은 `entity_mode=VIRTUAL` 인 행에만 통한다. REAL 데이터에
   대한 권한은 **한 조각도** 주지 않는다 — 이것이 "승급이 아니다"의 실질이다.
4. **발급·사용·만료를 전부 감사에 남긴다.** 임시 권한은 추적되지 않으면 뒷문이다.

## 왜 메모리 저장인가

토큰은 세션 전용이고 만료가 30분이다. DB 에 넣으면 프로세스 재시작 후에도 살아남는데, 그것은
"세션 전용"의 정의에 반한다. 재시작하면 사라지는 것이 **의도된 성질**이다.
⚠️ 다중 워커(gunicorn -w N)에서는 워커별로 토큰이 갈린다 — 발급받은 워커가 아닌 곳에서는
  거부된다(안전한 방향의 실패). 다중 워커 운영으로 가면 공유 저장소가 필요하다.

LLM 0콜.
"""
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

#: 기본 만료(분). 짧게 두는 것이 요점이다 — 길면 임시 권한이 상시 권한이 된다.
DEFAULT_TTL_MINUTES = 30
#: 만료 상한. 호출자가 아무 값이나 주지 못하게 막는다("24시간 토큰"은 세션 토큰이 아니다).
MAX_TTL_MINUTES = 120

VIRTUAL = "VIRTUAL"
READ = "read"


class SandboxTokenError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SandboxTokenStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._tokens: Dict[str, Dict[str, Any]] = {}

    # ── 발급 ──────────────────────────────────────────────────────────────
    def issue(self, actor: str, scope_node_id: str, tenant_id: str = "tenant_default",
              ttl_minutes: int = DEFAULT_TTL_MINUTES, purpose: str = "") -> Dict[str, Any]:
        """가상 문맥 읽기 토큰을 발급한다.

        ⚠️ `scope_node_id` 는 **가상 조직 범위**다. 실제 조직 범위를 넣어도 REAL 데이터는
          열리지 않는다(`allows()` 가 `entity_mode=VIRTUAL` 만 통과시킨다) — 그래도 목적이
          섞이지 않게 발급 시점에 감사로 남긴다."""
        if not (actor or "").strip():
            raise SandboxTokenError(
                "발급 대상(actor)이 필요합니다 — 누구에게 발급했는지 없는 임시 권한은 뒷문입니다.")
        if not (scope_node_id or "").strip():
            raise SandboxTokenError(
                "가상 조직 범위(scope_node_id)가 필요합니다 — 범위 없는 토큰은 '전부 허용'이 "
                "되고, 그것은 권한 승급입니다.")
        try:
            ttl = int(ttl_minutes)
        except (TypeError, ValueError):
            raise SandboxTokenError(f"ttl_minutes 는 숫자여야 합니다: {ttl_minutes}")
        if ttl <= 0:
            raise SandboxTokenError("ttl_minutes 는 1 이상이어야 합니다.")
        if ttl > MAX_TTL_MINUTES:
            raise SandboxTokenError(
                f"ttl_minutes 는 최대 {MAX_TTL_MINUTES}분입니다({ttl} 요청) — 긴 만료는 "
                f"세션 토큰이 아니라 상시 권한이고, 실험이 끝난 뒤에도 남습니다.")

        now = _now()
        token = f"sbx_{secrets.token_urlsafe(24)}"
        rec = {
            "token": token, "actor": actor.strip(), "scope_node_id": scope_node_id.strip(),
            "tenant_id": tenant_id or "tenant_default",
            "entity_mode": VIRTUAL,          # 고정 — 호출자가 REAL 로 바꿀 수 없다
            "capability": READ,              # 고정 — 쓰기 토큰은 존재하지 않는다
            "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
            "ttl_minutes": ttl, "purpose": purpose or "", "use_count": 0,
        }
        with self._lock:
            self._tokens[token] = rec
        self._audit("SANDBOX_TOKEN_ISSUED", rec,
                    reason=purpose or "가상 문맥 읽기 토큰 발급",
                    detail=f"ttl={ttl}m scope={rec['scope_node_id']} capability={READ}")
        return dict(rec)

    # ── 검증 ──────────────────────────────────────────────────────────────
    def resolve(self, token: str, quiet: bool = False) -> Optional[Dict[str, Any]]:
        """토큰을 확인한다. 없거나 만료면 `None`.

        ★ 만료는 조용히 지나가지 않는다 — `SANDBOX_TOKEN_EXPIRED` 로 남긴다. 만료된 토큰으로
          계속 두드리는 것은 "세션이 끝난 줄 모르는 클라이언트"이거나 **재사용 시도**이고,
          둘을 구분하려면 기록이 있어야 한다."""
        if not (token or "").strip():
            return None
        with self._lock:
            rec = self._tokens.get(token.strip())
            if not rec:
                return None
            expired = _now().isoformat() > rec["expires_at"]
            if expired:
                self._tokens.pop(token.strip(), None)
        if expired:
            if not quiet:
                self._audit("SANDBOX_TOKEN_EXPIRED", rec, outcome="denied",
                            reason="만료된 토큰 사용 시도",
                            detail=f"expired_at={rec['expires_at']} uses={rec['use_count']}")
            return None
        return dict(rec)

    def allows(self, token: str, row: Dict[str, Any], scope_node_id: str = "",
               capability: str = READ) -> bool:
        """이 토큰이 이 행을 열어 주는가.

        네 조건을 **모두** 만족해야 한다. 하나라도 빠지면 그것이 승급 경로가 된다:
          ① 토큰이 유효(미만료)
          ② 행이 `entity_mode=VIRTUAL` — **REAL 데이터는 한 조각도 열지 않는다**
          ③ 요청 범위가 토큰의 가상 조직 범위와 일치
          ④ 요구 권한이 읽기 — 쓰기에는 통하지 않는다"""
        if capability != READ:
            return False
        rec = self.resolve(token)
        if not rec:
            return False
        if (row.get("entity_mode") or "REAL") != VIRTUAL:
            return False
        if scope_node_id and scope_node_id != rec["scope_node_id"]:
            return False
        if (row.get("tenant_id") or "tenant_default") != rec["tenant_id"]:
            return False
        with self._lock:
            live = self._tokens.get(rec["token"])
            if live:
                live["use_count"] += 1
                count = live["use_count"]
            else:
                count = rec["use_count"]
        # 사용도 남긴다 — 발급만 남기면 "받아 갔지만 쓰지 않았다"와 구분되지 않는다.
        self._audit("SANDBOX_TOKEN_USED", rec, outcome="allowed",
                    reason="가상 문맥 읽기",
                    detail=f"use_count={count} scope={rec['scope_node_id']}")
        return True

    # ── 관리 ──────────────────────────────────────────────────────────────
    def revoke(self, token: str, actor: str = "") -> bool:
        """토큰을 즉시 무효화한다. 만료를 기다리지 않고 끊을 수단이 없으면 사고에 대응할 수 없다."""
        with self._lock:
            rec = self._tokens.pop((token or "").strip(), None)
        if not rec:
            return False
        self._audit("SANDBOX_TOKEN_EXPIRED", rec, outcome="denied",
                    reason=f"수동 회수(actor={actor or 'unknown'})",
                    detail=f"uses={rec['use_count']}")
        return True

    def active(self, actor: str = "") -> List[Dict[str, Any]]:
        """살아 있는 토큰 목록. 만료분은 정리하며 지난다.

        ★ "지금 열려 있는 임시 권한이 무엇인가"에 답할 수 없으면 임시 권한을 운영할 수 없다."""
        now = _now().isoformat()
        with self._lock:
            dead = [t for t, r in self._tokens.items() if now > r["expires_at"]]
            for t in dead:
                self._tokens.pop(t, None)
            rows = [dict(r) for r in self._tokens.values()
                    if not actor or r["actor"] == actor]
        for r in rows:
            r["token"] = r["token"][:12] + "…"      # 목록에 전체 토큰을 싣지 않는다
        return sorted(rows, key=lambda r: r["expires_at"])

    # ── 감사 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _audit(event: str, rec: Dict[str, Any], outcome: str = "allowed",
               reason: str = "", detail: str = "") -> None:
        try:
            from core.enterprise_context import audit
            audit.record(getattr(audit, event, event), resource_type="sandbox_token",
                         # 토큰 전체를 감사로그에 남기지 않는다 — 로그가 곧 자격증명이 된다.
                         resource_id=rec["token"][:12] + "…",
                         actor=rec.get("actor") or audit.ANONYMOUS,
                         actor_scopes=[rec.get("scope_node_id", "")],
                         requested_scope=rec.get("scope_node_id", ""),
                         outcome=outcome, reason=reason, detail=detail)
        except Exception as e:                                       # pragma: no cover
            print(f"⚠️ [sandbox_token] 감사 기록 실패: {e}")


sandbox_tokens = SandboxTokenStore()
