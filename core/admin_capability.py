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

#: ★★ [설계 §4.2 표] **시스템 기본 정의를 직접 고치는 권한.**
#:   표는 이렇게 되어 있다: 플랫폼 관리자 «복사·버전 승격만 가능» / AI 거버넌스 관리자
#:   «직접 수정 불가» / 부서 manager·member·viewer «불가».
#:   ⚠️ 이것을 `admin.permissions` 로 대신 쓰면 **AI 관리자가 전역 기본을 덮어쓴다** —
#:     2026-08-04 실측: AI 권한을 넉넉히 부여하자 내 회귀 테스트 2건이 즉시 깨졌고,
#:     그것이 설계와 구현이 갈라진 지점이었다. 그래서 전용 코드로 분리한다.
SYSTEM_DEFAULT_EDIT = "system.default.edit"

# ── 프로젝트(공장) 권한 ─────────────────────────────────────────────────────
#
# ★★ [2026-08-07] **이 제품의 핵심 객체에 권한 코드가 하나도 없었다.**
#   Agent·Workflow·Skill·Model 에는 코드가 있는데, 정작 사용자가 하루 종일 만지는
#   «프로젝트» 에는 없었다. 그래서 프로젝트 라우트 20개가 「Principal 을 받으니 통제됨」으로
#   세어졌고, 실측에서 **viewer 가 프로젝트를 지우고·만들고·스프린트를 돌릴 수 있었다.**
#
# ⚠️ 왜 네 개로 나누는가 — 하나(`project.manage`)로 묶으면 「돌려만 볼 사람」에게 릴리스
#   게시와 소유권 변경까지 딸려 간다. 반대로 라우트마다 코드를 만들면 표가 관리 불가능해진다.
#   **되돌리기 비용이 다른 지점**에서 끊었다:
#     · 만들기 — 되돌리기 쉽다(빈 프로젝트)
#     · 돌리기 — 비용이 나간다(LLM). 되돌릴 수 없다
#     · 고치기 — 남의 자료를 끌어온다(지식·기준정보 바인딩, 소유권)
#     · 게시 — **남에게 나간다.** 여기서부터는 회수해도 이미 본 사람이 있다
PROJECT_CREATE = "project.create"
PROJECT_RUN = "project.run"
PROJECT_EDIT = "project.edit"
PROJECT_RELEASE = "project.release"

PROJECT_CAPS = (PROJECT_CREATE, PROJECT_RUN, PROJECT_EDIT, PROJECT_RELEASE)

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
    WORKFLOW_BIND, SKILL_PROPOSE, SKILL_APPROVE, MODEL_POLICY_MANAGE, SYSTEM_DEFAULT_EDIT,
) + PROJECT_CAPS + ADMIN_TABS

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

    def can_manage_scope(self, scope_id: str) -> bool:
        """[P1-4] 이 **ECM 조직 노드**의 자산을 승인·폐기할 수 있는가.

        `can_manage_dept` 와 나눈 이유: 자산의 소유는 부서 id 가 아니라 조직 범위 노드
        (`owner_scope_id`)로 적힌다. 한 함수에 섞으면 부서 관리 권한이 조직 범위 승인 권한으로
        번지거나 그 반대가 된다.

        ★ AI 거버넌스 관리자는 조직 범위 제한을 받지 않는다(설계 §4.2 — 조직 공개 가능,
          전사 승인 가능). 부서 `manager` 는 `manageable_scope_nodes` 안에서만 승인한다.
        ⚠️ 소유 조직이 **비어 있는 자산은 관리 대상이 아니다.** 미기재를 «누구나 관리» 로 읽으면
          소유를 채우지 않는 것이 이득이 된다.

        ★★★ [2026-08-05 / D-018 이행] **양쪽을 정본으로 맞춰 비교한다.**
          백필(⑤)이 `departments.scope_node_id` 를 `node_*` 로 승격한 순간, 코드(`LS_MNM`)로
          들어온 요청이 **전부 403** 이 됐다 — 관리 범위는 정본인데 입력은 별칭이었기 때문이다.
          실측으로 조직 자산 생성이 막혔다(백필 직후 자산 거버넌스 테스트 22건 실패).
          ⚠️ 이행기에는 **어느 쪽이 별칭인지 알 수 없다**: 백필 전이면 관리 범위가 코드이고,
            백필 후면 입력이 코드다. 그래서 한쪽만 정규화하면 반대 상황에서 다시 막힌다.
          ⚠️ 라우트에서 정규화하지 않는 이유: 호출부가 셋이고(생성·수정·승인), 라우트마다
            정규화하면 또 복제가 된다 — 이 저장소가 `_scope` 헬퍼에서 이미 겪은 형태다."""
        if self.bootstrap or self.is_platform_admin or self.is_ai_admin:
            return True
        if not scope_id:
            return False
        if scope_id in self.manageable_scope_nodes:
            return True
        return self._canonical(scope_id) in {self._canonical(s)
                                             for s in self.manageable_scope_nodes}

    @staticmethod
    def _canonical(scope_ref: str) -> str:
        """별칭(업무 코드·부서 id)을 정본 `node_id` 로 바꾼다. 해석 못 하면 원본을 준다.

        ⚠️ 원본을 그대로 돌려주는 이유: 여기서 빈 값을 주면 «해석 못 한 두 값» 이 서로 같아져
          (빈 문자열 == 빈 문자열) **관리 권한이 우연히 통과**한다."""
        if not scope_ref:
            return ""
        try:
            from core.enterprise_context.scoping import resolve_scope_ref
            return resolve_scope_ref(scope_ref) or scope_ref
        except Exception:
            return scope_ref

    def can_publish_enterprise(self) -> bool:
        """[P1-4] **전사 공개**를 승인할 수 있는가.

        ⚠️ 조직 승인과 같은 판정으로 두면 안 된다. 부서 `manager` 는 «자기 조직 승인 가능,
          전사는 승격 요청만» 이다(설계 §4.2) — 한 부서장이 전사 전체가 쓰는 정의를 혼자
          확정하는 일이 생기면 그 승인은 누구도 검토하지 않은 승인이 된다."""
        return bool(self.bootstrap or self.is_platform_admin or self.is_ai_admin)

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
    # ⚠️ **프로젝트 권한이 하나도 없다.** 실측에서 viewer 가 프로젝트를 지우고 스프린트를
    #   돌릴 수 있었던 것이 이 줄이 비어 있어서가 아니라, 라우트가 아무 코드도 요구하지
    #   않았기 때문이다 — 표가 없으면 역할을 아무리 좁혀도 소용이 없다.
    "viewer": frozenset({AGENT_READ, WORKFLOW_READ, AGENT_EXECUTE}),
    # 부서 member — 개인/조직 초안까지. 승인은 «요청» 만 할 수 있으므로 publish 가 없다.
    # 프로젝트는 **만들고 돌리고 고칠 수 있다.** 게시(`PROJECT_RELEASE`)는 남에게 나가는
    # 일이므로 여기 없다 — Agent 에서 `publish` 를 뺀 것과 같은 기준이다.
    "member": frozenset({AGENT_READ, AGENT_CREATE, AGENT_UPDATE, AGENT_EXECUTE,
                         WORKFLOW_READ, WORKFLOW_CREATE, SKILL_PROPOSE,
                         PROJECT_CREATE, PROJECT_RUN, PROJECT_EDIT}),
    # 부서 manager — 자기 조직 승인까지. 전사 공개(승격)는 «요청» 이므로 여기 없다.
    "manager": frozenset({AGENT_READ, AGENT_CREATE, AGENT_UPDATE, AGENT_PUBLISH, AGENT_RETIRE,
                          AGENT_EXECUTE, WORKFLOW_READ, WORKFLOW_CREATE, WORKFLOW_UPDATE,
                          WORKFLOW_PUBLISH, WORKFLOW_BIND, SKILL_PROPOSE,
                          ADMIN_USERS, ADMIN_ORGANIZATION}) | frozenset(PROJECT_CAPS),
}

#: 경영진 — **만들지 않고 본다.** 실행과 결과 열람만(설계 §4.2).
_EXECUTIVE_CAPS = frozenset({AGENT_READ, WORKFLOW_READ, AGENT_EXECUTE, ADMIN_AUDIT})

#: AI 거버넌스 관리자 — 승인 권한은 있으나 **시스템 기본 정의를 직접 수정하지 못한다.**
_AI_ADMIN_CAPS = frozenset({
    AGENT_READ, AGENT_CREATE, AGENT_UPDATE, AGENT_PUBLISH, AGENT_RETIRE, AGENT_EXECUTE,
    WORKFLOW_READ, WORKFLOW_CREATE, WORKFLOW_UPDATE, WORKFLOW_PUBLISH, WORKFLOW_RETIRE,
    WORKFLOW_BIND, SKILL_PROPOSE, SKILL_APPROVE, MODEL_POLICY_MANAGE,
    ADMIN_AGENT_ACCESS, ADMIN_PERMISSIONS, ADMIN_AUDIT,
    # 프로젝트도 전부 — AI 거버넌스 관리자는 어느 부서의 실행이든 들여다보고 멈출 수 있어야
    # 한다. ⚠️ 단 `SYSTEM_DEFAULT_EDIT` 은 여전히 없다(§4.2, `resolve()` 가 discard 한다).
} | set(PROJECT_CAPS))

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
        caps |= set(ALL_CAPABILITIES)
    if is_ai:
        caps |= _AI_ADMIN_CAPS
        # ★ 설계 §4.2: AI 거버넌스 관리자는 **시스템 기본 정의를 직접 수정하지 못한다.**
        #   승인 권한이 있다고 기본값을 고칠 수 있는 것은 아니다 — 승인은 «남이 만든 것을
        #   통과시키는 일» 이고, 기본 수정은 «전 사용자의 출발점을 바꾸는 일» 이다.
        caps.discard(SYSTEM_DEFAULT_EDIT)
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
