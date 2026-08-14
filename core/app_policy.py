"""★★★ [G1-B04] 자원 접근의 **정책 결정점(PDP)** — 판정은 여기 한 곳에서 한다.

## 왜 `assert_*` 로 충분하지 않았나

기존 `api/deps.assert_release_readable/writable` 은 **예외를 던진다.** 막는 데는 충분하지만
두 가지를 못 한다.

1. **왜 막혔는지 호출부가 쓸 수 없다.** 던져진 문구를 파싱할 수는 없고, 그래서 화면은
   「권한 없음」과 「문맥 밖」과 「토큰이 다른 앱 것」을 같은 말로 뭉갠다.
2. **주체가 사람뿐이다.** G1-B 는 **앱이 자기 증명으로** 부르는 경로를 새로 만든다.

그래서 «판정» 을 «강제» 에서 분리한다 — 이 모듈은 **답을 돌려주고**, 라우트가 HTTP 로 바꾼다.

## ★★★ [rev.2 · 2026-08-13] 계약을 둘로 나눈다

교차검토 `[G1-B-P0-REVIEW-75]` 의 지적: 초판의 `Resource` 는 `app_class`·`release_id`·
매니페스트 capability 가 섞인 **앱 전용 구조**였다. 그것을 G2 온톨로지가 재사용하면
정책 모델이 다시 꼬인다.

    ResourceScope      범용 — tenant · entity_mode · scope_node_id · owner · binding_state
    AppResourceFacts   앱 전용 — app_id · release_id · app_class · manifest · capabilities

온톨로지는 `ResourceScope` 만 채우고 `AppResourceFacts` 를 넘기지 않는다. 앱 전용 규칙은
`app_facts` 가 있을 때만 돈다.

## 교집합이 실제 권한이다

    요청자 권한 ∩ 지금 고른 문맥 ∩ 자원 범위 ∩ 토큰 전수 대조 ∩ 매니페스트 선언 ∩ 자원 정책

설계 `design_agent_governance_scope_permissions_2026-08-04.md` §6.4 가 도구 호출에 대해
같은 식을 못박았다. 하나라도 비면 **거부**다 — «대부분 통과했으니 통과» 는 없다.

## ⚠️ 이 파일이 되돌리면 안 되는 것 (rev.2 에서 고친 fail-open 들)

- **미바인딩 자원을 통과시키지 않는다.** 초판은 `owner_dept_id` 가 비면 식별된 사용자에게
  허용했다(기존 릴리스 판정의 관대함을 승계). 신규 Host Runtime 자원에서 그것은 D-014 위반이다.
  레거시 호환은 `binding_state=LEGACY` 로 **명시**해야만 열린다.
- **앱 토큰의 READ 도 매니페스트 선언을 요구한다.** 초판은 읽기를 면제했다.
- **토큰은 전수 대조한다** — actor · app_id · release_id · tenant · entity_mode · scope · capability.
  하나라도 안 보면 그 축으로 재사용이 열린다.

LLM 0콜.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

#: 업무 액션. 자유 문자열을 받지 않는다 — 오타 하나가 «판정하지 않음» 이 되면 안 된다.
READ = "read"
WRITE = "write"
DELETE = "delete"
MANAGE = "manage"                     # 스키마 변경·데이터셋 폐기
ACTIONS = (READ, WRITE, DELETE, MANAGE)

#: 쓰기로 취급하는 액션. 「읽기만 허용」이 무엇을 막는지 한 곳에서 정한다.
_MUTATING = (WRITE, DELETE, MANAGE)

#: 자원의 범위 바인딩 상태. `project_visibility` 와 **같은 낱말**을 쓴다 — 같은 개념에
#: 다른 이름을 붙이면 두 곳을 대조할 때마다 번역이 필요하다.
BOUND = "BOUND"
LEGACY = "LEGACY"          # 마이그레이션 대상 — **명시해야만** 관대함이 적용된다
INVALID = "INVALID"        # 판독 실패 — 언제나 차단

#: 거부 사유 코드. **화면에 그대로 내보내지 않는다** — 노출 범위는 호출부가 정한다
#: (권한 밖 자원의 존재를 알리면 안 되는 경우가 있다).
DENY_UNIDENTIFIED = "UNIDENTIFIED"
DENY_NO_SUBJECT = "NO_SUBJECT"
#: ★ [rev.3] 주체 자체가 자료를 볼 수 없는 상태 — 폐지된 계정 · 미등록 사용자 · 부서 미배정.
#:   기존 `api/deps.visibility_block_reason` 이 쓰기 경로에서만 보던 축인데, PDP 에 없으면
#:   **폐지된 계정이 PDP 로는 통과**한다(동등성 대조에서 실제로 드러났다).
DENY_PRINCIPAL_BLOCKED = "PRINCIPAL_BLOCKED"
DENY_TOKEN_EXPIRED = "TOKEN_EXPIRED"
DENY_TOKEN_ACTOR_MISMATCH = "TOKEN_ACTOR_MISMATCH"   # 다른 사람의 토큰
DENY_TOKEN_SESSION_MISMATCH = "TOKEN_SESSION_MISMATCH"  # 다른 세션에서 재사용
DENY_TOKEN_APP_MISMATCH = "TOKEN_APP_MISMATCH"       # 남의 앱 데이터를 요청했다
DENY_TOKEN_CONTEXT_MISMATCH = "TOKEN_CONTEXT_MISMATCH"  # 다른 회사·실행 문맥에서 재사용
DENY_TOKEN_SCOPE_MISMATCH = "TOKEN_SCOPE_MISMATCH"   # 토큰이 묶인 조직 범위 밖
#: ★★★ 증명 발급 당시의 앱 선언과 지금의 선언이 다르다 — **앱이 바뀌었다.**
#:   ⚠️ capability 만 비교하면 «같은 권한을 유지한 채 내용이 바뀐 매니페스트» 를 놓친다.
DENY_TOKEN_MANIFEST_MISMATCH = "TOKEN_MANIFEST_MISMATCH"
DENY_TOKEN_CAPABILITY = "TOKEN_CAPABILITY"
DENY_MANIFEST_CAPABILITY = "MANIFEST_CAPABILITY"
DENY_CONTEXT = "CONTEXT_MISMATCH"                    # 요청 문맥 ↔ 자원 문맥
DENY_UNBOUND = "RESOURCE_UNBOUND"                    # 자원에 범위가 없다(D-014)
DENY_SCOPE = "SCOPE_DENIED"                          # 조직 권한 밖
DENY_PERSONAL = "PERSONAL_OWNER_ONLY"
DENY_RETIRED = "RESOURCE_RETIRED"
DENY_UNKNOWN_ACTION = "UNKNOWN_ACTION"
#: ★★★ [I-4 2단계] 계약이 **이 데이터셋에 대해** 이 행동을 주지 않았다.
#:   ⚠️ `DENY_TOKEN_CAPABILITY`(전역 권한 없음)와 다른 사유다 — 전역으로는 있는데
#:     이 데이터셋에만 없는 경우이고, 그것이 정확히 이 통제가 존재하는 이유다.
#:     하나로 뭉개면 「왜 막혔나」에 답할 수 없고, 개발자는 계약 대신 증명을 의심한다.
DENY_DATASET_ACTION = "DATASET_ACTION_NOT_CONTRACTED"
ALLOW = "OK"


@dataclass(frozen=True)
class PolicyDecision:
    """판정 결과. **던지지 않는다** — 호출부가 HTTP 로 바꾼다.

    ★ `obligations` 는 «허용하되 반드시 함께 해야 하는 것» 이다(감사 기록 등). 허용만 돌려주고
      의무를 말하지 않으면 호출부마다 기록을 빠뜨리는 곳이 생긴다."""
    allowed: bool
    reason: str = ALLOW
    message: str = ""
    obligations: Tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return self.allowed


def _deny(reason: str, message: str) -> PolicyDecision:
    return PolicyDecision(False, reason, message)


def _allow(*obligations: str) -> PolicyDecision:
    return PolicyDecision(True, ALLOW, "", tuple(obligations))


@dataclass(frozen=True)
class Subject:
    """판정 대상. 사람일 수도 있고 **앱 증명**일 수도 있다.

    · `user_id`    최종 책임 주체.
    · `scope`      조직 권한(`AccessScope` 호환).
    · `ctx`        지금 고른 실행 문맥(`tenant_id`·`entity_mode`·`scope_node_id`).
    · `session_id` 지금 로그인한 세션의 해시. **토큰 재사용 차단의 축**이다.
    · `blocked_reason` 주체가 아예 자료를 볼 수 없는 상태의 사유(빈 문자열이면 정상).
      ⚠️ **여기서 계산하지 않는다.** 「등록된 사용자인가·계정이 살아 있는가·부서가 있는가」는
        조직 저장소를 봐야 하고, 그 판정은 `api/deps.visibility_block_reason` 하나에 있다.
        PDP 는 `scope` 를 받는 것과 **같은 방식으로** 그 결과를 받아 쓴다 — 두 곳에서 계산하면
        조용히 갈라진다.
    · `via`        `session` | `app_token`.
    · `token`      앱 증명일 때의 내용(`app_capability_token.resolve()` 결과).

    ⚠️ **앱 증명은 사람 권한을 넘을 수 없다.** 그래서 토큰 경로에서도 `scope` 를 함께 받아
      교집합을 낸다 — 토큰만 보고 판정하면 회수된 권한이 토큰 수명 동안 살아 있다."""
    user_id: str = ""
    scope: Any = None
    ctx: Optional[Dict[str, Any]] = None
    session_id: str = ""
    blocked_reason: str = ""
    via: str = "session"
    token: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ResourceScope:
    """★ **범용** 자원 범위 계약. 앱·온톨로지·그 밖의 자원이 공유한다.

    ⚠️ 여기에 앱 전용 개념(`release_id`·`app_class`)을 넣지 말 것 — 넣는 순간 온톨로지가
      이 계약을 쓸 수 없게 되고, 그러면 정책 모델이 둘로 갈린다(교차검토 지적).

    · `binding_state` 가 `BOUND` 가 아니면 **원칙적으로 차단**이다. `LEGACY` 는 마이그레이션
      대상임을 **명시**했을 때만 관대함이 적용된다 — 빈 값을 관대함으로 읽지 않는다."""
    tenant_id: str = ""
    entity_mode: str = ""
    scope_node_id: str = ""
    owner_user_id: str = ""
    owner_dept_id: str = ""
    binding_state: str = BOUND
    status: str = "active"


@dataclass(frozen=True)
class AppResourceFacts:
    """앱 전용 정책 사실. **온톨로지는 이것을 넘기지 않는다.**

    · `declared_capabilities` 매니페스트가 선언한 행동. 빈 튜플은 «전부 허용» 이 아니라
      «데이터 행동을 선언하지 않은 앱» 이다.
    · `legacy_mode` **명시적** 하위호환. 켜면 미선언 READ 를 허용한다 — 켜지 않으면 막힌다.
      ⚠️ 기본값을 `True` 로 되돌리지 말 것. 그 순간 CL-0 감사 지적 D 가 되살아난다."""
    app_id: str = ""
    release_id: str = ""
    app_class: str = ""                # personal | departmental | enterprise
    manifest_fingerprint: str = ""
    declared_capabilities: Tuple[str, ...] = field(default_factory=tuple)
    manifest_version: str = ""
    legacy_mode: bool = False


# ── 축별 판정 ─────────────────────────────────────────────────────────────

def _ctx_ok(subject: Subject, res: ResourceScope) -> bool:
    """요청 문맥과 자원 문맥의 테넌트·실행 모드가 맞는가.

    ⚠️ 어느 쪽이든 **비어 있으면 통과시키지 않는다** — D-014 「미지정은 전사 공용이 아니라
      비노출」. `project_visibility.context_visible` 과 같은 규칙이다."""
    c = subject.ctx or {}
    c_tenant = str(c.get("tenant_id", "") or "").strip()
    c_mode = str(c.get("entity_mode", "") or "").strip()
    r_tenant = str(res.tenant_id or "").strip()
    r_mode = str(res.entity_mode or "").strip()
    if not c_tenant or not c_mode or not r_tenant or not r_mode:
        return False
    return r_tenant == c_tenant and r_mode == c_mode


def _scope_covers(selected: str, resource_node: str) -> Tuple[bool, bool]:
    """고른 조직 범위가 자원의 범위를 덮는가. `(덮는가, 조회실패인가)`.

    ★ 계층 탐색은 **G1 에서 확정한 primitive 를 그대로 쓴다** — 운영 상속(`OPERATING_PARENT`)만
      따르는 규칙(D-003)을 여기서 다시 구현하면 판정이 두 곳이 된다.
    ⚠️ 조회 실패를 «덮는다» 로 뭉개지 않는다 — 보안 경계에서 실패는 차단 쪽이어야 한다."""
    sel = (selected or "").strip()
    res = (resource_node or "").strip()
    if not sel:
        return True, False           # 「전체」를 고름 — 좁히지 않는다(권한 축이 따로 있다)
    if not res:
        return False, False          # 자원에 범위가 없다 — D-014 로 위에서 이미 막힌다
    if sel == res:
        return True, False
    try:
        from core.project_visibility import _scope_is_ancestor
        return _scope_is_ancestor(sel, res)
    except Exception:
        return False, True


def _scope_ok(subject: Subject, res: ResourceScope, action: str) -> Tuple[bool, str]:
    """조직 권한. `(허용, 사유)` — 거부 사유를 나눠야 화면이 다르게 말할 수 있다.

    순서: ① 자원 바인딩 → ② 고른 범위가 덮는가 → ③ 부서 권한.
    ⚠️ ①을 뒤로 미루면 미바인딩 자원이 «권한 없음» 으로 보고돼 마이그레이션 대상이 안 드러난다."""
    # ① 자원이 범위를 갖고 있는가 (D-014)
    state = (res.binding_state or BOUND).strip()
    if state == INVALID:
        return False, DENY_UNBOUND
    if state != LEGACY and not (res.scope_node_id or "").strip():
        # ★★★ [rev.2] 초판은 `owner_dept_id` 가 비면 통과시켰다. 신규 Host Runtime 자원에서
        #   그것은 fail-open 이다 — 범위 없는 자원은 «전사 공용» 이 아니라 «비노출» 이다.
        return False, DENY_UNBOUND

    scope = subject.scope
    if scope is None:
        return False, DENY_SCOPE
    try:
        unrestricted = bool(getattr(scope, "unrestricted", False))
    except Exception:
        return False, DENY_SCOPE          # 권한 객체가 이상하면 차단

    # ② 지금 고른 조직 범위가 자원을 덮는가 (문맥 축)
    #    ⚠️ 무제한 권한자도 여기서 면제되지 않는다 — 「전권」과 「지금 보는 범위」는 다른 축이다.
    c = subject.ctx or {}
    covers, lookup_failed = _scope_covers(str(c.get("scope_node_id", "") or ""),
                                          res.scope_node_id)
    if lookup_failed or not covers:
        return False, DENY_SCOPE

    # ③ 부서 권한
    if unrestricted:
        return True, ALLOW
    uid = (subject.user_id or "").strip()
    if uid and res.owner_user_id and res.owner_user_id == uid:
        return True, ALLOW
    dept = (res.owner_dept_id or "").strip()
    if not dept:
        # 여기 도달하려면 `scope_node_id` 는 있고 부서만 없는 것이다. 레거시로 **명시**된
        # 경우에만 통과시킨다 — 빈 값을 관대함으로 읽지 않는다.
        return (True, ALLOW) if state == LEGACY else (False, DENY_UNBOUND)
    try:
        allowed = (getattr(scope, "writable_dept_ids", frozenset()) if action in _MUTATING
                   else getattr(scope, "readable_dept_ids", frozenset()))
        return (dept in allowed), (ALLOW if dept in allowed else DENY_SCOPE)
    except Exception:
        return False, DENY_SCOPE


def _token_ok(subject: Subject, res: ResourceScope,
              app: Optional[AppResourceFacts], action: str) -> Tuple[bool, str, str]:
    """★★★ [rev.2] 앱 증명 **전수 대조.** `(통과, 사유, 문구)`.

    초판은 `release_id` 와 capability 두 축만 봤다. 나머지 축(actor·session·app_id·tenant·
    entity_mode·scope)은 **저장만 되고 판정에 쓰이지 않았고**, 안 보는 축마다 재사용 경로가
    하나씩 열려 있었다 — 다른 사람의 토큰, 다른 세션, 다른 회사 문맥."""
    tok = subject.token or {}
    if not tok:
        return False, DENY_NO_SUBJECT, "앱 증명 내용이 없습니다."
    if tok.get("expired"):
        return False, DENY_TOKEN_EXPIRED, "앱 접근 증명이 만료됐습니다. 다시 여십시오."

    # ① 누구의 증명인가 — 다른 사람의 토큰을 주워 쓸 수 없다
    if str(tok.get("actor", "")) != str(subject.user_id or ""):
        return False, DENY_TOKEN_ACTOR_MISMATCH, "다른 사용자의 앱 접근 증명입니다."

    # ② 어느 세션의 증명인가 — 로그아웃·재로그인 후 재사용을 막는다
    #    ⚠️ 토큰에 세션이 없으면 통과시키지 않는다. «옛 토큰이라 세션이 없다» 를 허용하면
    #      그것이 곧 우회로다.
    tok_sid = str(tok.get("session_id", "") or "")
    if not tok_sid or tok_sid != str(subject.session_id or ""):
        return False, DENY_TOKEN_SESSION_MISMATCH, "다른 로그인 세션의 증명입니다."

    # ③ 어느 앱인가 — release 와 app_id 를 **둘 다** 본다
    if app is None:
        return False, DENY_TOKEN_APP_MISMATCH, "앱 정보가 없는 요청입니다."
    if str(tok.get("release_id", "")) != str(app.release_id or ""):
        return False, DENY_TOKEN_APP_MISMATCH, "이 앱의 데이터가 아닙니다."
    if str(tok.get("app_id", "")) != str(app.app_id or ""):
        return False, DENY_TOKEN_APP_MISMATCH, "이 앱의 데이터가 아닙니다."

    # ③-b 그 앱의 **어느 판**인가 — 발급 당시의 선언과 지금의 선언이 같아야 한다
    #     ⚠️ 빈 값을 통과시키지 않는다. 「옛 증명이라 지문이 없다」를 허용하면 그것이 곧
    #       우회로다(세션 축과 같은 판단).
    tok_fp = str(tok.get("manifest_fingerprint", "") or "")
    tok_mv = str(tok.get("manifest_version", "") or "")
    if (not tok_fp
            or tok_fp != str(app.manifest_fingerprint or "")
            or tok_mv != str(app.manifest_version or "")):
        return (False, DENY_TOKEN_MANIFEST_MISMATCH,
                "앱 선언이 발급 이후 바뀌었습니다. 앱을 다시 여십시오.")

    # ④ 어느 회사·실행 문맥의 증명인가 — 문맥을 바꿔 재사용하는 경로를 막는다
    c = subject.ctx or {}
    if (str(tok.get("tenant_id", "")) != str(c.get("tenant_id", "") or "")
            or str(tok.get("entity_mode", "")) != str(c.get("entity_mode", "") or "")):
        return False, DENY_TOKEN_CONTEXT_MISMATCH, "다른 회사·실행 문맥의 증명입니다."
    if str(tok.get("tenant_id", "")) != str(res.tenant_id or ""):
        return False, DENY_TOKEN_CONTEXT_MISMATCH, "다른 회사 문맥의 자료입니다."

    # ⑤ 어느 조직 범위로 묶인 증명인가
    tok_scope = str(tok.get("scope_node_id", "") or "")
    if tok_scope:
        covers, failed = _scope_covers(tok_scope, res.scope_node_id)
        if failed or not covers:
            return False, DENY_TOKEN_SCOPE_MISMATCH, "이 증명이 묶인 조직 범위 밖입니다."

    # ⑥ 그 행동을 담고 있는가
    if action not in tuple(tok.get("capabilities") or ()):
        return False, DENY_TOKEN_CAPABILITY, f"이 앱에는 «{action}» 권한이 부여되지 않았습니다."
    return True, ALLOW, ""


def _manifest_ok(app: AppResourceFacts, action: str) -> Tuple[bool, str]:
    """매니페스트 선언. `(통과, 문구)`.

    ★★★ [rev.2] **읽기도 선언을 요구한다.** 초판은 READ 를 면제했는데, 그러면 «선언하지 않은
      앱이 데이터를 읽는» 경로가 남는다 — CL-0 감사 지적 D(빈 capability 매니페스트가 정상
      통과)와 같은 구멍이다.
    ⚠️ 기존 앱 호환은 `legacy_mode=True` 로 **명시**했을 때만이다."""
    declared = tuple(app.declared_capabilities or ())
    if not declared:
        if app.legacy_mode and action == READ:
            return True, ""
        return False, "이 앱은 다룰 데이터 행동을 선언하지 않았습니다."
    if action not in declared:
        return False, f"이 앱은 «{action}» 을 선언하지 않았습니다."
    return True, ""


# ── 단일 판정 ─────────────────────────────────────────────────────────────

def decide(subject: Subject, resource: ResourceScope, action: str,
           app: Optional[AppResourceFacts] = None) -> PolicyDecision:
    """★★★ **단일 판정.** 앱 데이터의 읽기·쓰기·업무 액션이 전부 여기를 지난다.

    `app` 이 `None` 이면 **범용 자원**으로 판정한다(온톨로지가 그렇게 쓴다).

    순서가 규칙이다 — **좁은 것부터** 본다. 넓은 검사를 먼저 통과시키면 거부 사유가
    「권한 없음」으로 뭉개져서 진짜 원인(예: 남의 앱 증명)이 보이지 않는다."""
    if action not in ACTIONS:
        return _deny(DENY_UNKNOWN_ACTION, f"알 수 없는 행동입니다: {action}")
    if subject is None or resource is None:
        return _deny(DENY_NO_SUBJECT, "판정할 주체 또는 자원이 없습니다.")

    # ① 식별 — 읽기까지 요구한다. 누구인지 모르는 접근은 추적이 불가능하다.
    uid = (subject.user_id or "").strip()
    if not uid:
        return _deny(DENY_UNIDENTIFIED,
                     "누가 하는 요청인지 확인할 수 없습니다. 로그인이 필요합니다.")

    # ①-b 주체가 아예 자료를 볼 수 없는 상태인가 (폐지 계정·미등록·부서 미배정)
    #     ⚠️ 이 축이 없으면 **폐지된 계정이 PDP 로 통과**한다 — 기존 쓰기 판정보다 느슨해진다.
    if (subject.blocked_reason or "").strip():
        return _deny(DENY_PRINCIPAL_BLOCKED, subject.blocked_reason.strip())

    # ② 자원 상태
    if (resource.status or "active") != "active":
        return _deny(DENY_RETIRED, "이 자원은 사용 중단됐습니다.")

    # ③ 앱 증명 전수 대조 — 가장 좁은 검사
    if subject.via == "app_token":
        ok, reason, msg = _token_ok(subject, resource, app, action)
        if not ok:
            return _deny(reason, msg)

    # ④ 매니페스트 선언 — 앱 경로에서만. 앱이 «하겠다고 말한 것» 밖은 하지 못한다.
    if app is not None and subject.via == "app_token":
        ok, msg = _manifest_ok(app, action)
        if not ok:
            return _deny(DENY_MANIFEST_CAPABILITY, msg)

    # ⑤ 실행 문맥 — 「전권」과 「지금 보는 범위」는 다른 축이다
    if not _ctx_ok(subject, resource):
        return _deny(DENY_CONTEXT, "지금 선택한 회사·실행 문맥의 자료가 아닙니다.")

    # ⑥ 자원 바인딩 + 조직 범위 + 부서 권한
    ok, reason = _scope_ok(subject, resource, action)
    if not ok:
        if reason == DENY_UNBOUND:
            return _deny(DENY_UNBOUND,
                         "이 자료에 소유 조직이 기록되어 있지 않습니다 — 점검이 필요합니다.")
        return _deny(DENY_SCOPE, "이 자료에 대한 권한이 없습니다.")

    # ⑦ 개인 앱 — 만든 사람만(설계 §5-1). 부서로 열면 개인 도구가 부서 공유물이 된다.
    #    ⚠️ 무제한 권한자도 통과시키지 않는다 — 권한 문제가 아니라 신뢰 문제다.
    if app is not None and (app.app_class or "") == "personal":
        owner = (resource.owner_user_id or "").strip()
        if owner and owner != uid:
            return _deny(DENY_PERSONAL, "개인용 앱의 데이터는 만든 사람만 볼 수 있습니다.")

    # 허용 — **모든 판정에 기록 의무**를 돌려준다. 쓰기만 남기면 「누가 무엇을 읽었나」에
    # 답할 수 없고, 그것이 곧 유출 조사가 불가능한 상태다.
    return _allow("audit")
