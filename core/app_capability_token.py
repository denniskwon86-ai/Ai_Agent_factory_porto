"""★★★ [G1-B03] 생성 앱 데이터 접근용 **단기 capability token**.

    app_id · release_id · user · tenant · scope · entity_mode · capabilities · 짧은 만료

## ⚠️⚠️ 가장 먼저 알아야 할 것 — **이 토큰은 앱에게 주지 않는다**

`design_app_data_plane_2026-08-08.md` §7 이 못박은 계약이다:

> 앱은 `fetch` 를 직접 호출하지 않는다. 주입되는 것은 `window.afs.data.*` 뿐이고 그 구현은
> `postMessage` 로 **부모에게** 요청을 보내는 얇은 껍데기다. **앱은 토큰·헤더·사용자
> 식별자를 본 적이 없다.**

그러면 토큰은 왜 필요한가. **부모(호스트 화면)가 자기 호출을 한 앱에 못 박기 위해서**다.

    앱 ──postMessage(데이터셋 «이름» 만)──▶ 부모 ──토큰 + 이름──▶ 서버
                                                    └ 토큰이 release 를 고정한다

부모가 `release_id` 를 붙이는 계약(§7-4)만으로는 **부모 코드의 실수 하나가 곧 남의 앱
데이터 노출**이 된다. 토큰이 있으면 서버가 마지막으로 대조한다 — 토큰의 릴리스와 요청한
자원의 릴리스가 다르면 거부다(`app_policy.DENY_TOKEN_APP_MISMATCH`).

★ 그래서 이것은 «앱에게 주는 권한» 이 아니라 **«이 화면이 지금 이 앱을 열고 있다» 는 증명**이다.

## 왜 `sandbox_token` 을 확장하지 않는가

`core/sandbox_token.py` 는 **`entity_mode=VIRTUAL` 고정 · `capability=read` 고정**이고
그 파일이 스스로 「쓰기 토큰은 존재하지 않는다」고 못박았다. 생성 앱은 REAL 문맥에서
데이터를 **쓴다** — 확장하면 그 네 보장이 전부 깨진다.

→ **저장소는 나누고 규율은 그대로 승계한다**: 짧은 만료 · 만료 상한 · 전문 1회 노출 ·
  발급/사용/만료/회수 감사 · 프로세스 재시작 시 소멸.

## 권한은 «넘겨받는» 것이지 «생기는» 것이 아니다

⚠️ 토큰에 담긴 `capabilities` 는 **요청자가 그때 가지고 있던 권한의 부분집합**이다. 토큰만
  보고 판정하면 **권한을 회수해도 토큰 수명 동안 살아 있다.** 그래서 `app_policy.decide()` 는
  토큰과 **사람 권한을 함께** 보고 교집합을 낸다 — 이 파일은 그 교집합의 한쪽일 뿐이다.

LLM 0콜.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.app_policy import ACTIONS, READ

#: 기본 만료(분). 미리보기 한 세션 정도만 살아 있으면 된다.
DEFAULT_TTL_MINUTES = 15
#: 만료 상한. 「하루짜리 앱 토큰」은 세션 증명이 아니라 상시 권한이다.
MAX_TTL_MINUTES = 60

#: 토큰 접두어. 로그에서 눈으로 구분되게 둔다(`sbx_` 와 섞이면 안 된다).
PREFIX = "app_"
#: 감사·목록에 남기는 앞자리 길이. 전문은 발급 응답에서 **단 한 번만** 나간다.
_FINGERPRINT = 12


def token_hash(raw: str) -> str:
    """토큰 원문 → 저장용 해시.

    ★★★ [rev.2 · 교차검토 지적 5] 초판은 **원문을 메모리 키와 레코드에 그대로** 들고 있었다.
      프로세스 덤프·디버거·예외 출력 어디에서든 그것이 새면 곧 권한이다. 저장은 해시로 하고
      원문은 발급 응답에서 한 번만 나간다(`core/auth._ticket_hash` 와 같은 판단).

    ⚠️ 비밀번호가 아니므로 pbkdf2 를 쓰지 않는다 — 192비트 난수이고 최대 60분 산다.
      대신 조회 경로가 빨라야 한다(요청마다 1회)."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


class AppTokenError(ValueError):
    """토큰 발급·사용 계약 위반 — 라우트가 4xx 로 바꾼다."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AppCapabilityTokenStore:
    """메모리 저장. **재시작하면 사라지는 것이 의도된 성질**이다.

    ⚠️ 다중 워커(gunicorn -w N)에서는 워커별로 갈린다 — 발급받은 워커가 아닌 곳에서는
      거부된다(**안전한 방향의 실패**). 다중 워커 운영으로 가면 공유 저장소가 필요하고,
      그때는 «토큰을 DB 에 둔다» 가 아니라 «세션 저장소를 공유한다» 가 답이다
      (`sandbox_token` 이 같은 한계를 같은 방식으로 적어 두었다)."""

    def __init__(self) -> None:
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    # ── 발급 ──────────────────────────────────────────────────────────────
    def issue(self, *, actor: str, session_id: str, app_id: str, release_id: str,
              capabilities: Tuple[str, ...] = (READ,),
              tenant_id: str = "", entity_mode: str = "",
              scope_node_id: str = "", ttl_minutes: int = DEFAULT_TTL_MINUTES,
              purpose: str = "") -> Dict[str, Any]:
        """토큰 발급. 반환에 **전문(`token`)이 들어 있는 유일한 곳**이다.

        ⚠️ 호출부는 이 값을 로그·목록·오류 메시지에 다시 싣지 않는다."""
        actor = (actor or "").strip()
        if not actor:
            raise AppTokenError(
                "발급 대상(actor)이 필요합니다 — 누구를 대신해 도는지 없는 토큰은 뒷문입니다.")
        app_id = (app_id or "").strip()
        release_id = (release_id or "").strip()
        if not release_id:
            raise AppTokenError(
                "release_id 가 필요합니다 — 릴리스가 없는 토큰은 «모든 앱» 을 뜻하게 되고, "
                "그것이 정확히 이 토큰이 막으려는 상태입니다.")
        if not app_id:
            raise AppTokenError("app_id 가 필요합니다 — 어느 앱인지 없는 증명은 증명이 아닙니다.")
        #: ★★★ [rev.2] **세션에 묶는다.** 없으면 로그아웃·재로그인 후에도 같은 토큰이 통하고,
        #:   그것이 「다른 세션에서 재사용」 경로다(교차검토 지적 2).
        session_id = (session_id or "").strip()
        if not session_id:
            raise AppTokenError(
                "session_id 가 필요합니다 — 세션에 묶이지 않은 증명은 로그아웃 뒤에도 살아 "
                "있고, 그것은 회수할 수 없는 권한입니다.")

        caps = tuple(dict.fromkeys(str(c).strip() for c in (capabilities or ()) if str(c).strip()))
        if not caps:
            raise AppTokenError(
                "capabilities 가 비었습니다 — 빈 권한 토큰은 «전부 허용» 으로 오해되기 쉽습니다. "
                f"허용 값: {list(ACTIONS)}")
        bad = [c for c in caps if c not in ACTIONS]
        if bad:
            raise AppTokenError(f"알 수 없는 capability: {bad} — 허용 값: {list(ACTIONS)}")

        # ⚠️ 문맥을 비운 채 발급하지 않는다. 빈 문맥은 `app_policy` 에서 «판정 불가» 이고,
        #   판정 불가 토큰을 만들면 그 토큰은 아무 데도 못 쓰거나(좋음) 어딘가에서
        #   빈 값이 통과하는 순간 경계가 사라진다(나쁨). 만들 때 막는 편이 확실하다.
        tenant_id = (tenant_id or "").strip()
        entity_mode = (entity_mode or "").strip()
        scope_node_id = (scope_node_id or "").strip()
        if not tenant_id or not entity_mode:
            raise AppTokenError(
                "tenant_id 와 entity_mode 가 필요합니다 — 실행 문맥 없는 토큰은 경계를 확인할 "
                "수 없습니다(D-014).")
        #: ⚠️ [rev.2] 범위 공란을 허용하지 않는다. 빈 범위 토큰은 판정에서 «좁히지 않음» 이 되어
        #:   사실상 전 조직으로 통한다 — 교차검토 지적 1·3.
        if not scope_node_id:
            raise AppTokenError(
                "scope_node_id 가 필요합니다 — 범위 없는 증명은 «전 조직 허용» 이 됩니다.")

        try:
            ttl = int(ttl_minutes)
        except (TypeError, ValueError):
            raise AppTokenError(f"ttl_minutes 는 숫자여야 합니다: {ttl_minutes}")
        if ttl <= 0:
            raise AppTokenError("ttl_minutes 는 1 이상이어야 합니다.")
        if ttl > MAX_TTL_MINUTES:
            raise AppTokenError(
                f"ttl_minutes 는 최대 {MAX_TTL_MINUTES}분입니다({ttl} 요청) — 긴 만료는 "
                f"«이 화면이 지금 그 앱을 열고 있다» 는 증명이 아니라 상시 권한입니다.")

        now = _now()
        token = f"{PREFIX}{secrets.token_urlsafe(24)}"
        rec = {
            #: ⚠️ **원문을 넣지 않는다.** 해시만 보관한다.
            "fingerprint": token[:_FINGERPRINT],
            "actor": actor,
            "session_id": session_id,
            "app_id": app_id,
            "release_id": release_id,
            "capabilities": caps,
            "tenant_id": tenant_id,
            "entity_mode": entity_mode,
            "scope_node_id": scope_node_id,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
            "ttl_minutes": ttl,
            "purpose": purpose or "",
            "use_count": 0,
            "revoked": False,
        }
        with self._lock:
            self._tokens[token_hash(token)] = rec
        self._audit("APP_TOKEN_ISSUED", rec,
                    reason=purpose or "생성 앱 데이터 접근 증명 발급",
                    detail=f"ttl={ttl}m release={release_id} caps={list(caps)}")
        #: 전문은 **여기서만** 나간다. 저장소에는 해시만 있다.
        out = dict(rec)
        out["token"] = token
        return out

    # ── 사용 ──────────────────────────────────────────────────────────────
    def resolve(self, token: str, *, quiet: bool = False) -> Optional[Dict[str, Any]]:
        """토큰을 판정용 dict 로 바꾼다. **없거나 회수됐으면 `None`.**

        ★ 만료는 `None` 이 아니라 `expired=True` 로 돌려준다 — `app_policy` 가
          「만료됐다」와 「그런 토큰이 없다」를 **다르게 말해야** 하기 때문이다.
          사용자가 할 일이 다르다(다시 열기 vs 접근 불가)."""
        tok = (token or "").strip()
        if not tok:
            return None
        with self._lock:
            rec = self._tokens.get(token_hash(tok))
            if rec is None:
                return None
            if rec.get("revoked"):
                return None
            expired = _now() > datetime.fromisoformat(rec["expires_at"])
            if not expired:
                rec["use_count"] = int(rec.get("use_count", 0)) + 1
            out = dict(rec)
        out["expired"] = expired
        out.pop("token", None)              # ⚠️ 판정 경로에 전문을 들고 다니지 않는다
        if not quiet:
            if expired:
                self._audit("APP_TOKEN_EXPIRED", out, outcome="denied",
                            reason="만료된 앱 토큰 사용 시도")
            else:
                #: ★★★ [rev.2 · 교차검토 지적 5] **성공 사용을 남긴다.**
                #:   발급과 거부만 남기면 「그 증명으로 실제로 무엇을 했나」에 답할 수 없고,
                #:   유출 조사에서 가장 필요한 것이 바로 그 기록이다.
                self._audit("APP_TOKEN_USED", out,
                            reason="앱 데이터 접근 증명 사용",
                            detail=f"release={out.get('release_id','')} "
                                   f"use_count={out.get('use_count')}")
        return out

    def revoke(self, token: str, actor: str = "") -> bool:
        with self._lock:
            rec = self._tokens.get(token_hash((token or "").strip()))
            if rec is None or rec.get("revoked"):
                return False
            rec["revoked"] = True
            snapshot = dict(rec)
        self._audit("APP_TOKEN_REVOKED", snapshot, reason=f"회수: {actor or '미상'}")
        return True

    def revoke_session(self, session_id: str, actor: str = "") -> int:
        """★ [rev.2] **세션이 끝나면 그 세션의 증명도 끝난다.**

        로그아웃했는데 앱 증명이 살아 있으면 「회수할 수 없는 권한」이 남는다 —
        `auth.destroy_all_for` 와 짝을 이루는 쪽이다."""
        sid = (session_id or "").strip()
        if not sid:
            return 0
        killed = []
        with self._lock:
            for rec in self._tokens.values():
                if rec.get("session_id") == sid and not rec.get("revoked"):
                    rec["revoked"] = True
                    killed.append(dict(rec))
        for rec in killed:
            self._audit("APP_TOKEN_REVOKED", rec,
                        reason=f"세션 종료로 회수: {actor or '미상'}")
        return len(killed)

    def active(self, actor: str = "") -> List[Dict[str, Any]]:
        """살아 있는 토큰 목록. ⚠️ **전문은 절대 싣지 않는다** — 지문만."""
        now = _now()
        out = []
        with self._lock:
            for rec in self._tokens.values():
                if rec.get("revoked"):
                    continue
                if now > datetime.fromisoformat(rec["expires_at"]):
                    continue
                if actor and rec["actor"] != actor:
                    continue
                out.append(dict(rec))       # 저장소에 전문이 없으므로 지울 것도 없다
        return sorted(out, key=lambda r: r["issued_at"])

    def purge_expired(self) -> int:
        """만료분 정리. 메모리 저장이라 무한히 쌓이지 않게 한다."""
        now = _now()
        with self._lock:
            dead = [t for t, r in self._tokens.items()
                    if now > datetime.fromisoformat(r["expires_at"])]
            for t in dead:
                self._tokens.pop(t, None)
        return len(dead)

    # ── 감사 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _audit(event: str, rec: Dict[str, Any], outcome: str = "allowed",
               reason: str = "", detail: str = "") -> None:
        """발급·사용·만료·회수를 남긴다. **추적되지 않는 임시 권한은 뒷문이다.**

        ⚠️ 기록 실패가 요청을 죽이지 않는다 — 다만 `audit.record` 가 내부에서 실패를 센다.
        ⚠️ **전문을 남기지 않는다.** 지문(앞 12자)만 남긴다 — 로그를 읽을 수 있는 사람이
          곧 권한자가 되면 안 된다."""
        try:
            from core.enterprise_context import audit
            audit.record(event=event, resource_type="app_capability_token",
                         resource_id=rec.get("fingerprint", ""),
                         actor=rec.get("actor", ""),
                         requested_scope=rec.get("scope_node_id", ""),
                         outcome=outcome, reason=reason,
                         detail=detail or f"release={rec.get('release_id', '')}")
        except Exception:
            pass


app_capability_tokens = AppCapabilityTokenStore()
