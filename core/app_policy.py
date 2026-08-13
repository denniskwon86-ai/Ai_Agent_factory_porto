"""★★★ [G1-B04] 생성 앱 데이터 접근의 **정책 결정점(PDP)** — 판정은 여기 한 곳에서 한다.

## 왜 `assert_*` 로 충분하지 않았나

기존 `api/deps.assert_release_readable/writable` 은 **예외를 던진다.** 막는 데는 충분하지만
두 가지를 못 한다.

1. **왜 막혔는지 호출부가 쓸 수 없다.** 던져진 문구를 파싱할 수는 없고, 그래서 화면은
   「권한 없음」과 「문맥 밖」과 「토큰이 다른 앱 것」을 같은 말로 뭉갠다.
2. **주체가 사람뿐이다.** G1-B 는 **앱이 자기 토큰으로** 부르는 경로를 새로 만든다
   (`app_capability_token`). 그때 판정 대상은 `Principal` 이 아니다.

그래서 «판정» 을 «강제» 에서 분리한다 — 이 모듈은 **답을 돌려주고**, 라우트가 그 답을 HTTP 로
바꾼다. 로드맵 G1-B04 「데이터 읽기·쓰기·업무 액션별 정책 결정점」이 이것이다.

## 의존 방향

⚠️ `core/` 는 `api/` 를 import 하지 않는다. 그래서 이 함수는 `Principal` 이 아니라 **이미
  해석된 원시값**(scope 객체 · user_id · 문맥 dict)을 받는다 — `project_visibility.
  ownership_visible(scope, user_id, own)` 이 같은 이유로 같은 모양이다.
  라우트가 어댑터 노릇을 한다.

★ 이 계약은 나중에 온톨로지의 `ResourceScope` 가 얹힐 자리이기도 하다(설계
  `design_manufacturing_management_ontology_2026-08-13.md` §5). 그래서 자원 종류를
  `AppResource` 하나로 못 박지 않고 «판정에 필요한 사실» 만 받는다.

## 교집합이 실제 권한이다

    요청자 권한 ∩ 지금 고른 문맥 ∩ 토큰 capability ∩ 매니페스트 선언 ∩ 자원 정책(app_class)

설계 `design_agent_governance_scope_permissions_2026-08-04.md` §6.4 가 도구 호출에 대해
같은 식을 못박았다. 하나라도 비면 **거부**다 — «대부분 통과했으니 통과» 는 없다.

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

#: 쓰기로 취급하는 액션. 「읽기만 허용」 토큰이 무엇을 막는지 한 곳에서 정한다.
_MUTATING = (WRITE, DELETE, MANAGE)

#: 거부 사유 코드. **화면에 그대로 내보내지 않는다** — 사유의 노출 범위는 호출부가 정한다
#: (권한 밖 자원의 존재를 알리면 안 되는 경우가 있다).
DENY_UNIDENTIFIED = "UNIDENTIFIED"           # 누구인지 모른다
DENY_NO_SUBJECT = "NO_SUBJECT"               # 판정할 주체 자체가 없다
DENY_TOKEN_EXPIRED = "TOKEN_EXPIRED"
DENY_TOKEN_APP_MISMATCH = "TOKEN_APP_MISMATCH"       # 남의 앱 데이터를 요청했다
DENY_TOKEN_CAPABILITY = "TOKEN_CAPABILITY"           # 토큰이 그 행동을 담고 있지 않다
DENY_MANIFEST_CAPABILITY = "MANIFEST_CAPABILITY"     # 앱이 선언하지 않은 행동
DENY_CONTEXT = "CONTEXT_MISMATCH"                    # 테넌트·실행 모드가 다르다
DENY_SCOPE = "SCOPE_DENIED"                          # 조직 권한 밖
DENY_PERSONAL = "PERSONAL_OWNER_ONLY"                # 개인 앱은 만든 사람만
DENY_RETIRED = "RESOURCE_RETIRED"
DENY_UNKNOWN_ACTION = "UNKNOWN_ACTION"
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

    def __bool__(self) -> bool:            # `if decide(...):` 로 쓸 수 있게
        return self.allowed


def _deny(reason: str, message: str) -> PolicyDecision:
    return PolicyDecision(False, reason, message)


def _allow(*obligations: str) -> PolicyDecision:
    return PolicyDecision(True, ALLOW, "", tuple(obligations))


@dataclass(frozen=True)
class Subject:
    """판정 대상. 사람일 수도 있고 **앱 토큰**일 수도 있다.

    · `user_id`   최종 책임 주체. 앱 토큰도 «누구를 대신해» 도는지 반드시 갖는다.
    · `scope`     조직 권한(`AccessScope` 호환 — `unrestricted`·`readable_dept_ids` 등).
    · `ctx`       지금 고른 실행 문맥(`tenant_id`·`entity_mode`·`scope_node_id`).
    · `via`       `session` | `app_token`.
    · `token`     앱 토큰일 때의 발급 내용(§`app_capability_token`).

    ⚠️ **앱 토큰은 사람 권한을 넘을 수 없다.** 그래서 토큰 경로에서도 `scope` 를 함께 받아
      교집합을 낸다 — 토큰만 보고 판정하면 회수된 권한이 토큰 수명 동안 살아 있다."""
    user_id: str = ""
    scope: Any = None
    ctx: Optional[Dict[str, Any]] = None
    via: str = "session"
    token: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Resource:
    """판정 대상 자원. «판정에 필요한 사실» 만 담는다 — 저장소 행을 그대로 넘기지 않는다.

    ⚠️ 행을 그대로 넘기면 저장소 스키마가 바뀔 때마다 판정이 조용히 달라진다."""
    kind: str = "dataset"              # dataset | record
    release_id: str = ""
    dataset_id: str = ""
    app_class: str = ""                # personal | departmental | enterprise
    owner_user_id: str = ""            # personal 앱의 소유자
    owner_dept_id: str = ""
    tenant_id: str = ""
    entity_mode: str = ""
    scope_node_id: str = ""
    status: str = "active"
    #: 매니페스트가 **선언한** capability. 빈 튜플이면 «선언 없음» 이고, 그것은 «전부 허용» 이
    #: 아니라 «데이터 행동을 선언하지 않은 앱» 이다(§4 참조).
    declared_capabilities: Tuple[str, ...] = field(default_factory=tuple)


def _ctx_ok(subject: Subject, res: Resource) -> bool:
    """테넌트·실행 모드가 맞는가.

    ⚠️ 문맥이나 자원 쪽 값이 **비어 있으면 통과시키지 않는다** — D-014 「미지정은 전사 공용이
      아니라 비노출」. `project_visibility.context_visible` 과 같은 규칙이다.
      다만 조직 범위 좁히기는 여기서 하지 않는다(권한 축이 `_scope_ok` 로 따로 있다)."""
    c = subject.ctx or {}
    c_tenant = str(c.get("tenant_id", "") or "").strip()
    c_mode = str(c.get("entity_mode", "") or "").strip()
    r_tenant = str(res.tenant_id or "").strip()
    r_mode = str(res.entity_mode or "").strip()
    if not c_tenant or not c_mode:
        return False
    if not r_tenant or not r_mode:
        return False
    return r_tenant == c_tenant and r_mode == c_mode


def _scope_ok(subject: Subject, res: Resource, action: str) -> bool:
    """조직 권한. `api/deps` 의 릴리스 판정과 **같은 결론**을 내야 한다.

    ⚠️ 여기서 더 느슨해지면 PDP 를 도입하는 것만으로 통제가 약해진다. 그래서 규칙을 그대로 옮긴다:
      · 무제한이면 통과(조직 미도입·플랫폼 관리자 하위호환 계약)
      · 소유자 본인이면 통과
      · 그 외에는 부서 권한 — 읽기는 `readable_dept_ids`, 쓰기는 `writable_dept_ids`"""
    scope = subject.scope
    if scope is None:
        return False
    try:
        if bool(getattr(scope, "unrestricted", False)):
            return True
    except Exception:
        return False                    # 권한 객체가 이상하면 차단
    uid = (subject.user_id or "").strip()
    if uid and res.owner_user_id and res.owner_user_id == uid:
        return True
    dept = (res.owner_dept_id or "").strip()
    if not dept:
        # ⚠️ 소유권 미기록 자원의 관대함은 **식별된 사용자에게만** 준다(`assert_release_writable`
        #   의 판단 그대로). 식별 검사는 `decide()` 앞단에서 이미 했다.
        return True
    try:
        if action in _MUTATING:
            return dept in getattr(scope, "writable_dept_ids", frozenset())
        return dept in getattr(scope, "readable_dept_ids", frozenset())
    except Exception:
        return False


def decide(subject: Subject, resource: Resource, action: str) -> PolicyDecision:
    """★★★ **단일 판정.** 앱 데이터의 읽기·쓰기·업무 액션이 전부 여기를 지난다.

    순서가 규칙이다 — **좁은 것부터** 본다. 넓은 검사를 먼저 통과시키면 거부 사유가
    「권한 없음」으로 뭉개져서 진짜 원인(예: 남의 앱 토큰)이 보이지 않는다."""
    if action not in ACTIONS:
        return _deny(DENY_UNKNOWN_ACTION, f"알 수 없는 행동입니다: {action}")
    if subject is None:
        return _deny(DENY_NO_SUBJECT, "판정할 주체가 없습니다.")

    # ① 식별 — 쓰기는 예외 없이 요구한다(트랙 H 가 봉합한 «식별만으로 열리는 쓰기» 의 반대편).
    uid = (subject.user_id or "").strip()
    if not uid:
        return _deny(DENY_UNIDENTIFIED,
                     "누가 하는 요청인지 확인할 수 없습니다. 로그인이 필요합니다.")

    # ② 자원 상태
    if (resource.status or "active") != "active":
        return _deny(DENY_RETIRED, "이 데이터셋은 사용 중단됐습니다.")

    # ③ 앱 토큰 경로 — **가장 좁은 검사부터**
    if subject.via == "app_token":
        tok = subject.token or {}
        if not tok:
            return _deny(DENY_NO_SUBJECT, "앱 토큰 내용이 없습니다.")
        if tok.get("expired"):
            return _deny(DENY_TOKEN_EXPIRED, "앱 접근 권한이 만료됐습니다. 다시 여십시오.")
        # ★★★ 이 한 줄이 「앱이 남의 데이터를 읽는」 경로를 원천 차단한다(설계 §7-4).
        if str(tok.get("release_id", "")) != str(resource.release_id or ""):
            return _deny(DENY_TOKEN_APP_MISMATCH,
                         "이 앱의 데이터가 아닙니다.")
        caps = tuple(tok.get("capabilities") or ())
        if action not in caps:
            return _deny(DENY_TOKEN_CAPABILITY,
                         f"이 앱에는 «{action}» 권한이 부여되지 않았습니다.")

    # ④ 매니페스트 선언 — 앱이 «하겠다고 말한 것» 밖은 하지 못한다
    #    ⚠️ 선언이 **비어 있으면 쓰기를 막는다.** 「선언 안 했으니 전부 허용」은 CL-0 이
    #      막으려던 것 자체다(빈 capability 매니페스트가 정상으로 통과하던 감사 지적 D).
    if action in _MUTATING and subject.via == "app_token":
        declared = tuple(resource.declared_capabilities or ())
        if not declared:
            return _deny(DENY_MANIFEST_CAPABILITY,
                         "이 앱은 데이터를 바꾸겠다고 선언하지 않았습니다.")
        if action not in declared:
            return _deny(DENY_MANIFEST_CAPABILITY,
                         f"이 앱은 «{action}» 을 선언하지 않았습니다.")

    # ⑤ 실행 문맥 — 「전권」과 「지금 보는 범위」는 다른 축이다
    if not _ctx_ok(subject, resource):
        return _deny(DENY_CONTEXT, "지금 선택한 회사·실행 문맥의 자료가 아닙니다.")

    # ⑥ 조직 권한
    if not _scope_ok(subject, resource, action):
        return _deny(DENY_SCOPE, "이 자료에 대한 권한이 없습니다.")

    # ⑦ 개인 앱 — 만든 사람만(설계 §5-1). 부서로 열면 개인 도구가 부서 공유물이 된다.
    #    ⚠️ 무제한 권한자도 **여기서는 통과시키지 않는다.** 「관리자니까 남의 개인 메모를 본다」는
    #      권한 문제가 아니라 신뢰 문제다.
    if (resource.app_class or "") == "personal":
        owner = (resource.owner_user_id or "").strip()
        if owner and owner != uid:
            return _deny(DENY_PERSONAL, "개인용 앱의 데이터는 만든 사람만 볼 수 있습니다.")

    # 허용 — 쓰기에는 **기록 의무**를 함께 돌려준다.
    return _allow("audit") if action in _MUTATING else _allow()
