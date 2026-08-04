"""[D-017 P0] 관리자 capability 계약 — **권한의 정본은 서버다.**

## 왜 별도 모듈인가

D-017 은 접근을 3단계로 강제한다: ① 글로벌 메뉴 가시성 ② 페이지 Route Guard ③ **서버 API
권한 재검사**. 앞의 둘은 편의이고, 마지막 하나만 보안이다 — 화면을 숨기는 것은 URL 을 아는
사람 앞에서 아무 일도 하지 않는다.

★ 그래서 «누가 무엇을 할 수 있는가» 를 **한 곳에서** 계산한다. 화면·라우트·서비스가 각자
  `is_admin` 을 보고 판단하면 세 곳이 서서히 갈라지고, 갈라진 그 한 곳이 열린 문이 된다.

## `is_data_admin` 을 AI 관리자 대신 쓰지 않는다 (설계 §4.2)

데이터 표준 승인과 AI 행동·비용 정책 승인은 **책임이 다르다.** 한 플래그로 묶으면 "이 사람이
왜 모델 정책을 바꿀 수 있었나"에 답할 수 없다. 그래서 `is_ai_admin` 을 따로 둔다.

## 부트스트랩

조직이 아직 서지 않았거나(`unrestricted`) 사용자가 0명이면 권한 강제가 의미 없다 —
그 상태에서 막으면 **첫 관리자를 만들 사람이 아무도 없어 시스템이 잠긴다**(`org_directory`
의 `is_bootstrap` 과 같은 이유). 그때는 전 capability 를 허용하되, **그 사실을 숨기지 않는다**
(`AdminCapabilities.bootstrap == True`).

LLM 0콜 — 전부 결정론적 계산이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable

# ── 권한 코드 (설계 §4.1) ────────────────────────────────────────────────────
AGENT_READ = "agent.definition.read"
AGENT_CREATE = "agent.definition.create"
AGENT_UPDATE = "agent.definition.update"
AGENT_PUBLISH = "agent.definition.publish"
AGENT_RETIRE = "agent.definition.retire"
AGENT_EXECUTE = "agent.execute"

WORKFLOW_READ = "workflow.read"
WORKFLOW_CREATE = "workflow.create"
WORKFLOW_UPDATE = "workflow.update"
WORKFLOW_PUBLISH = "workflow.publish"
WORKFLOW_RETIRE = "workflow.retire"
WORKFLOW_BIND = "workflow.bind"

SKILL_PROPOSE = "skill.propose"
SKILL_APPROVE = "skill.approve"

MODEL_POLICY_MANAGE = "model.policy.manage"

#: 관리자 센터 탭 접근(설계 §8.2). **탭마다 따로 둔다** — 하나로 묶으면 «조직 관리자» 가
#: 모델 정책까지 바꿀 수 있게 되고, 그것이 D-017 이 분리하려던 바로 그 상태다.
ADMIN_ORGANIZATION = "admin.organization"
ADMIN_USERS = "admin.users"
ADMIN_PERMISSIONS = "admin.permissions"
ADMIN_AGENT_ACCESS = "admin.agent_access"
ADMIN_DATA_ACCESS = "admin.data_access"
ADMIN_SECURITY = "admin.security"
ADMIN_AUDIT = "admin.audit"

ADMIN_TABS = (ADMIN_ORGANIZATION, ADMIN_USERS, ADMIN_PERMISSIONS, ADMIN_AGENT_ACCESS,
              ADMIN_DATA_ACCESS, ADMIN_SECURITY, ADMIN_AUDIT)

ALL_CAPABILITIES = (
    AGENT_READ, AGENT_CREATE, AGENT_UPDATE, AGENT_PUBLISH, AGENT_RETIRE, AGENT_EXECUTE,
    WORKFLOW_READ, WORKFLOW_CREATE, WORKFLOW_UPDATE, WORKFLOW_PUBLISH, WORKFLOW_RETIRE,
    WORKFLOW_BIND, SKILL_PROPOSE, SKILL_APPROVE, MODEL_POLICY_MANAGE,
) + ADMIN_TABS

#: 관리자 센터 URL → 필요한 capability(설계 §8.2 표). Route Guard 와 서버가 **같은 표**를 본다.
TAB_ROUTES: Dict[str, str] = {
    "/admin/organization": ADMIN_ORGANIZATION,
    "/admin/users": ADMIN_USERS,
    "/admin/permissions": ADMIN_PERMISSIONS,
    "/admin/agent-access": ADMIN_AGENT_ACCESS,
    "/admin/data-access": ADMIN_DATA_ACCESS,
    "/admin/security": ADMIN_SECURITY,
    "/admin/audit": ADMIN_AUDIT,
}


class AdminCapabilityError(PermissionError):
    """권한 없음. 라우트가 **404 로 은폐**할지 403 을 낼지는 자원 성격에 따라 고른다.

    ⚠️ 타 조직 자원의 존재를 알리면 안 되는 곳(사용자·정책 상세)은 404 다(설계 §8.2)."""


@dataclass(frozen=True)
class AdminCapabilities:
    """한 사용자의 확정 관리자 권한. **불변**이며 `resolve()` 만이 만든다."""
    user_id: str = ""
    capabilities: FrozenSet[str] = field(default_factory=frozenset)
    #: 관리 대상 부서. **읽기 범위와 다르다** — 볼 수 있다고 바꿀 수 있는 것이 아니다.
    manageable_dept_ids: FrozenSet[str] = field(default_factory=frozenset)
    manageable_scope_nodes: FrozenSet[str] = field(default_factory=frozenset)
    #: 조직 미도입·사용자 0명 상태에서 전면 허용됐는가. **숨기지 않는다** — 화면이 이 사실을
    #: 말해야 «권한이 있어서» 와 «아직 아무도 없어서» 를 구분할 수 있다.
    bootstrap: bool = False
    is_platform_admin: bool = False
    is_ai_admin: bool = False
    is_data_admin: bool = False

    def has(self, cap: str) -> bool:
        return cap in self.capabilities

    def can_manage_dept(self, dept_id: str) -> bool:
        """이 부서의 사용자·역할을 바꿀 수 있는가.

        ⚠️ 부서를 지정하지 않은 요청을 «전부 허용» 으로 읽지 않는다. 관리 작업은 대상이
          분명해야 하고, 대상이 없으면 그 요청 자체가 잘못된 것이다."""
        if self.bootstrap or self.is_platform_admin:
            return True
        if not dept_id:
            return False
        return dept_id in self.manageable_dept_ids

    @property
    def any_admin(self) -> bool:
        """관리자 센터 메뉴를 **보여줄지** 정하는 값(3단계 중 ①)."""
        return any(c in self.capabilities for c in ADMIN_TABS)

    @property
    def visible_tabs(self) -> list:
        return [t for t in ADMIN_TABS if t in self.capabilities]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "capabilities": sorted(self.capabilities),
            "manageable_dept_ids": sorted(self.manageable_dept_ids),
            "manageable_scope_nodes": sorted(self.manageable_scope_nodes),
            "bootstrap": self.bootstrap,
            "is_platform_admin": self.is_platform_admin,
            "is_ai_admin": self.is_ai_admin,
            "is_data_admin": self.is_data_admin,
            "any_admin": self.any_admin,
            "visible_tabs": self.visible_tabs,
            "can_manage_agents": self.has(AGENT_PUBLISH) or self.has(ADMIN_AGENT_ACCESS),
        }


# ── 역할 → capability (설계 §4.2 표를 그대로 옮긴 것) ───────────────────────
#: ⚠️ 이 표를 코드 여러 곳에 흩지 않는다. 흩는 순간 «부서 manager 가 전사 공개를 할 수 있는가»
#:   같은 질문의 답이 파일마다 달라진다.
_ROLE_CAPS: Dict[str, FrozenSet[str]] = {
    # 부서 viewer — 승인된 것을 읽고 실행만.
    "viewer": frozenset({AGENT_READ, WORKFLOW_READ, AGENT_EXECUTE}),
    # 부서 member — 개인/조직 초안까지. 승인은 «요청» 만 할 수 있으므로 publish 가 없다.
    "member": frozenset({AGENT_READ, AGENT_CREATE, AGENT_UPDATE, AGENT_EXECUTE,
                         WORKFLOW_READ, WORKFLOW_CREATE, SKILL_PROPOSE}),
    # 부서 manager — 자기 조직 승인까지. 전사 공개(승격)는 «요청» 이므로 여기 없다.
    "manager": frozenset({AGENT_READ, AGENT_CREATE, AGENT_UPDATE, AGENT_PUBLISH, AGENT_RETIRE,
                          AGENT_EXECUTE, WORKFLOW_READ, WORKFLOW_CREATE, WORKFLOW_UPDATE,
                          WORKFLOW_PUBLISH, WORKFLOW_BIND, SKILL_PROPOSE,
                          ADMIN_USERS, ADMIN_ORGANIZATION}),
}

#: 경영진 — **만들지 않고 본다.** 실행과 결과 열람만(설계 §4.2).
_EXECUTIVE_CAPS = frozenset({AGENT_READ, WORKFLOW_READ, AGENT_EXECUTE, ADMIN_AUDIT})

#: AI 거버넌스 관리자 — 승인 권한은 있으나 **시스템 기본 정의를 직접 수정하지 못한다.**
_AI_ADMIN_CAPS = frozenset({
    AGENT_READ, AGENT_CREATE, AGENT_UPDATE, AGENT_PUBLISH, AGENT_RETIRE, AGENT_EXECUTE,
    WORKFLOW_READ, WORKFLOW_CREATE, WORKFLOW_UPDATE, WORKFLOW_PUBLISH, WORKFLOW_RETIRE,
    WORKFLOW_BIND, SKILL_PROPOSE, SKILL_APPROVE, MODEL_POLICY_MANAGE,
    ADMIN_AGENT_ACCESS, ADMIN_PERMISSIONS, ADMIN_AUDIT,
})

#: 데이터 관리자 — 데이터·카탈로그·MCP 권한 탭만(설계 §8.2).
_DATA_ADMIN_CAPS = frozenset({ADMIN_DATA_ACCESS, ADMIN_AUDIT, AGENT_READ, WORKFLOW_READ})


def resolve(scope, user: Dict[str, Any] | None = None) -> AdminCapabilities:
    """`AccessScope` 와 사용자 레코드에서 관리자 권한을 **확정**한다.

    ★ 여기가 정본이다. 라우트·서비스·화면은 이 결과만 본다.
    ⚠️ 위임 계정(Jarvis·자동화)은 **요청자 권한을 초과할 수 없다**(설계 §4.2) — 위임은 이
      함수에 들어오기 전에 요청자 신원으로 치환돼야 하며, 여기서 별도 승급 경로를 두지 않는다.
    """
    uid = getattr(scope, "user_id", "") or ""
    u = user or {}
    is_platform = bool(getattr(scope, "is_admin", False))
    is_ai = bool(u.get("is_ai_admin"))
    is_data = bool(getattr(scope, "is_data_admin", False))
    is_exec = bool(getattr(scope, "is_executive", False))
    unrestricted = bool(getattr(scope, "unrestricted", False))

    # ── 부트스트랩: 조직이 서기 전에는 막지 않되, 막지 않았다는 사실을 남긴다 ──
    if unrestricted and not is_platform:
        return AdminCapabilities(
            user_id=uid, capabilities=frozenset(ALL_CAPABILITIES),
            manageable_dept_ids=frozenset(), manageable_scope_nodes=frozenset(),
            bootstrap=True, is_platform_admin=False, is_ai_admin=is_ai, is_data_admin=is_data)

    caps: set = set()
    if is_platform:
        # 플랫폼 관리자 — 전 capability. 단 «시스템 기본 정의 직접 수정» 은 자산 계층에서
        # 별도로 막는다(설계 §4.2: 복사·버전 승격만 가능).
        caps |= set(ALL_CAPABILITIES)
    if is_ai:
        caps |= _AI_ADMIN_CAPS
    if is_data:
        caps |= _DATA_ADMIN_CAPS
    if is_exec:
        caps |= _EXECUTIVE_CAPS

    # ── 부서 역할 ──────────────────────────────────────────────────────────
    roles: Dict[str, str] = dict(u.get("roles") or {})
    for _dept_id, role in roles.items():
        caps |= _ROLE_CAPS.get(role, frozenset())

    # ── 관리 범위 ──────────────────────────────────────────────────────────
    # ★★ **여기서 다시 계산하지 않는다.** `resolve_scope` 가 이미 부서 상속까지 확정해
    #   `scope.manageable_dept_ids` 에 담아 두었다. 여기서 또 계산하면 계산 지점이 둘이 되고,
    #   둘은 반드시 갈라진다 — 2026-08-04 실측에서 이 함수가 전역 싱글턴 `org_directory` 를
    #   붙잡는 바람에 다른 저장소의 부서 트리를 보지 못해 **하위 부서가 관리 범위에서 빠졌다.**
    # ⚠️ 전역 싱글턴을 참조하지 않는다. 권한 계산이 «지금 어느 저장소를 보고 있는가» 에
    #   의존하면, 그 의존이 보이지 않는 곳에서 범위를 좁히거나 넓힌다.
    manageable: set = set(getattr(scope, "manageable_dept_ids", frozenset()) or frozenset())
    if is_platform:
        manageable |= set(getattr(scope, "writable_dept_ids", frozenset()) or frozenset())

    # 관리 대상 조직 노드도 scope 가 확정한 값을 쓴다 — **읽기 노드와 다르다.**
    nodes = frozenset(getattr(scope, "manageable_scope_nodes", frozenset()) or frozenset())
    if is_platform and not nodes:
        nodes = frozenset(getattr(scope, "readable_scope_nodes", frozenset()) or frozenset())

    return AdminCapabilities(
        user_id=uid, capabilities=frozenset(caps),
        manageable_dept_ids=frozenset(manageable), manageable_scope_nodes=nodes,
        bootstrap=False, is_platform_admin=is_platform, is_ai_admin=is_ai, is_data_admin=is_data)


def require(caps: AdminCapabilities, *needed: str) -> None:
    """서버 재검사(3단계 중 ③). **하나라도 없으면 막는다.**

    ⚠️ 여러 개를 넘기면 **전부** 요구한다(교집합이 아니라 합집합을 요구). «둘 중 하나» 가
      필요하면 호출부에서 명시적으로 갈라 쓴다 — `any` 를 기본으로 두면 언젠가 넓은 쪽이
      우연히 통과한다."""
    missing = [c for c in needed if not caps.has(c)]
    if missing:
        raise AdminCapabilityError(
            f"권한이 없습니다: {sorted(missing)} — 관리자 센터의 해당 탭 권한이 필요합니다.")


def require_dept(caps: AdminCapabilities, dept_id: str) -> None:
    """대상 부서를 관리할 수 있는지. 없으면 `AdminCapabilityError`.

    ★ 호출부는 이것을 **404 로 바꾼다** — 타 조직 사용자·정책의 존재를 알리지 않는다(§8.2)."""
    if not caps.can_manage_dept(dept_id):
        raise AdminCapabilityError(f"관리 범위 밖의 조직입니다: {dept_id or '(미지정)'}")


def capabilities_for(caps: Iterable[str]) -> FrozenSet[str]:
    """알 수 없는 코드를 조용히 통과시키지 않는다 — 오타 하나가 «권한 있음» 이 되면 안 된다."""
    out = set()
    for c in caps or ():
        if c not in ALL_CAPABILITIES:
            raise AdminCapabilityError(f"등록되지 않은 권한 코드입니다: {c}")
        out.add(c)
    return frozenset(out)
