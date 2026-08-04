"""★★★ [D-017] 관리자 capability 계약 — **권한의 정본은 서버다.**

D-017 은 접근을 3단계로 강제한다: ① 글로벌 메뉴 가시성 ② 페이지 Route Guard ③ **서버 API
권한 재검사**. 앞의 둘은 편의이고 마지막 하나만 보안이다 — 화면을 숨기는 것은 URL 을 아는
사람 앞에서 아무 일도 하지 않는다.

## 이 파일이 막는 네 가지

1. **읽기 범위가 관리 범위로 새는 것.** 경영진은 전 부서를 읽지만 **관리하지 않는다**.
   두 집합을 같게 두면 열람 권한이 곧 편집 권한이 된다.
2. **`is_data_admin` 이 AI 관리자를 대신하는 것.** 데이터 표준 승인과 AI 정책 승인은 책임이
   다르다(설계 §4.2). 묶으면 «이 사람이 왜 모델 정책을 바꿀 수 있었나» 에 답할 수 없다.
3. **권한 계산 실패가 «권한 있음» 이 되는 것.** 실패는 닫히는 쪽이어야 한다.
4. **부트스트랩 전면 허용을 숨기는 것.** 조직이 서기 전에는 막을 수 없지만(막으면 첫 관리자를
   만들 사람이 없어 잠긴다), 막지 않았다는 사실은 드러나야 한다.
"""
import pytest

from core.admin_capability import (ADMIN_AGENT_ACCESS, ADMIN_AUDIT, ADMIN_DATA_ACCESS,
                                   ADMIN_ORGANIZATION, ADMIN_SECURITY, ADMIN_TABS, ADMIN_USERS,
                                   AGENT_CREATE, AGENT_EXECUTE, AGENT_PUBLISH, AGENT_READ,
                                   ALL_CAPABILITIES, MODEL_POLICY_MANAGE, SKILL_APPROVE,
                                   SYSTEM_DEFAULT_EDIT,
                                   TAB_ROUTES, AdminCapabilityError, capabilities_for, require,
                                   require_dept, resolve)
from core.org_directory import AccessScope, OrgDirectory


@pytest.fixture()
def org(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    o = OrgDirectory(db_path=str(tmp_path / "org.db"))
    o.create_department("hq", "본사")
    o.create_department("prod", "생산", parent_id="hq")
    o.create_department("prod_a", "1라인", parent_id="prod")
    o.create_department("sales", "영업", parent_id="hq")
    return o


def _scope(**kw):
    base = dict(user_id="u", unrestricted=False)
    base.update(kw)
    return AccessScope(**base)


# ── 부트스트랩 ────────────────────────────────────────────────────────────
def test_bootstrap_allows_everything_but_says_so():
    """★★★ 조직이 서기 전에는 막지 않되, **막지 않았다는 사실을 숨기지 않는다.**

    ⚠️ 막으면 첫 관리자를 만들 사람이 아무도 없어 시스템이 잠긴다. 그러나 그 상태를 «권한이
      있다» 로 표시하면, 조직을 세운 뒤에도 아무도 권한을 확인하지 않는다."""
    c = resolve(_scope(unrestricted=True))
    assert c.bootstrap is True
    assert c.any_admin is True
    assert set(c.capabilities) == set(ALL_CAPABILITIES)
    assert c.to_dict()["bootstrap"] is True, "화면이 이 상태를 말할 수 있어야 한다"


def test_bootstrap_is_not_platform_admin():
    """★ 부트스트랩은 «아직 아무도 없어서» 이지 «관리자여서» 가 아니다."""
    c = resolve(_scope(unrestricted=True))
    assert c.is_platform_admin is False


# ── 읽기 범위 ≠ 관리 범위 ─────────────────────────────────────────────────
def test_executive_reads_everything_but_manages_nothing(org):
    """★★★ 경영진은 전 부서를 읽지만 **관리하지 않는다**(설계 §4.2: 생성·승인 불가).

    ⚠️ 읽기 범위를 관리 범위로 흘리면 열람 권한이 곧 편집 권한이 된다 — 가장 흔한 권한 사고다."""
    org.upsert_user("exec", "임원", primary_dept_id="hq", is_executive=True)
    org.upsert_user("staff", "직원", primary_dept_id="sales")
    s = org.resolve_scope("exec")
    assert len(s.readable_dept_ids) == 4, "전 부서를 읽는다"
    assert s.manageable_dept_ids == frozenset(), "그러나 관리 대상은 없다"

    c = resolve(s, org.get_user("exec"))
    assert c.has(AGENT_READ) and c.has(AGENT_EXECUTE)
    assert not c.has(AGENT_CREATE), "경영진은 만들지 않는다"
    assert not c.has(AGENT_PUBLISH), "경영진은 승인하지 않는다"
    assert not c.has(ADMIN_USERS), "사용자 관리 탭이 없다"


def test_manager_manages_own_subtree_only(org):
    """★★ 부서 manager 는 **자기 부서와 하위**만 관리한다. 형제 부서는 아니다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    s = org.resolve_scope("m")
    c = resolve(s, org.get_user("m"))
    assert c.can_manage_dept("prod") and c.can_manage_dept("prod_a")
    assert not c.can_manage_dept("sales"), "형제 부서는 관리 범위 밖이다"
    assert not c.can_manage_dept("hq"), "상위 부서로 거슬러 올라가지 않는다"


def test_member_cannot_publish(org):
    """★★ member 는 초안까지다. 승인은 «요청» 이므로 `publish` 가 없다(설계 §4.2)."""
    org.upsert_user("u1", "사원", primary_dept_id="prod")
    org.set_user_roles("u1", {"prod": "member"})
    c = resolve(org.resolve_scope("u1"), org.get_user("u1"))
    assert c.has(AGENT_CREATE)
    assert not c.has(AGENT_PUBLISH)
    assert c.any_admin is False, "일반 사원에게 관리자 센터 메뉴가 보이면 안 된다"


def test_viewer_can_only_read_and_execute(org):
    """★ viewer 는 승인된 것을 읽고 실행만 한다."""
    org.upsert_user("v", "열람자", primary_dept_id="sales")
    org.set_user_roles("v", {"sales": "viewer"})
    c = resolve(org.resolve_scope("v"), org.get_user("v"))
    assert c.has(AGENT_READ) and c.has(AGENT_EXECUTE)
    assert not c.has(AGENT_CREATE)
    assert c.manageable_dept_ids == frozenset()


def test_no_dept_means_no_management(org):
    """★★ 대상 부서를 지정하지 않은 요청을 «전부 허용» 으로 읽지 않는다.

    ⚠️ 관리 작업은 대상이 분명해야 한다. 빈 값을 통과시키면 «전체 대상» 요청이 조용히 성공한다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    c = resolve(org.resolve_scope("m"), org.get_user("m"))
    assert c.can_manage_dept("") is False


# ── 역할 분리 ─────────────────────────────────────────────────────────────
def test_data_admin_does_not_get_ai_policy(org):
    """★★★ `is_data_admin` 이 AI 관리자를 대신하지 않는다(설계 §4.2 명시).

    ⚠️ 데이터 표준 승인과 AI 행동·비용 정책 승인은 책임이 다르다. 한 플래그로 묶으면
      «이 사람이 왜 모델 정책을 바꿀 수 있었나» 에 답할 수 없다."""
    org.upsert_user("da", "데이터관리자", primary_dept_id="hq", is_data_admin=True)
    c = resolve(org.resolve_scope("da"), org.get_user("da"))
    assert c.has(ADMIN_DATA_ACCESS)
    assert not c.has(MODEL_POLICY_MANAGE), "데이터 관리자는 AI 정책을 바꾸지 않는다"
    assert not c.has(SKILL_APPROVE)
    assert not c.has(ADMIN_AGENT_ACCESS)


def test_ai_admin_gets_policy_but_not_data_tab(org):
    """★★ AI 관리자는 Agent/Workflow/Skill 권한과 정책 탭만 관리한다(설계 §8.2)."""
    org.upsert_user("aa", "AI관리자", primary_dept_id="hq", is_ai_admin=True)
    u = org.get_user("aa")
    assert u["is_ai_admin"] is True, "컬럼이 실제로 저장돼야 한다"
    c = resolve(org.resolve_scope("aa"), u)
    assert c.has(MODEL_POLICY_MANAGE) and c.has(SKILL_APPROVE) and c.has(ADMIN_AGENT_ACCESS)
    assert not c.has(ADMIN_DATA_ACCESS), "데이터 탭은 데이터 관리자 몫이다"
    assert not c.has(ADMIN_SECURITY), "보안 정책은 플랫폼 관리자 몫이다"


def test_ai_admin_cannot_edit_system_default(org):
    """★★★ [설계 §4.2 표] AI 거버넌스 관리자는 «시스템 기본 수정 **직접 수정 불가**».

    ⚠️ 2026-08-04 실측으로 잡힌 설계-구현 괴리다. `admin.permissions` 로 이 판정을 대신했더니
      AI 권한을 부여하는 순간 그 사람이 **전역 기본 레지스트리와 default 워크플로우를
      덮어쓸 수 있게** 됐다. 승인 권한이 있다고 기본값을 고칠 수 있는 것이 아니다 —
      승인은 «남이 만든 것을 통과시키는 일» 이고, 기본 수정은 «전 사용자의 출발점을 바꾸는 일» 이다."""
    org.upsert_user("aa", "AI관리자", primary_dept_id="hq", is_ai_admin=True)
    c = resolve(org.resolve_scope("aa"), org.get_user("aa"))
    assert c.has(SKILL_APPROVE), "승인 권한은 있다"
    assert c.has(MODEL_POLICY_MANAGE), "정책 권한도 있다"
    assert not c.has(SYSTEM_DEFAULT_EDIT), "그러나 시스템 기본은 직접 못 고친다"


def test_only_platform_admin_edits_system_default(org):
    """★★ 이 권한을 가진 사람은 **플랫폼 관리자뿐**이다(설계 §4.2 표 세로줄)."""
    org.upsert_user("root", "관리자", primary_dept_id="hq", is_admin=True)
    org.upsert_user("m", "부서장", primary_dept_id="hq")
    org.set_user_roles("m", {"hq": "manager"})
    org.upsert_user("exec", "임원", primary_dept_id="hq", is_executive=True)
    org.upsert_user("da", "데이터", primary_dept_id="hq", is_data_admin=True)

    assert resolve(org.resolve_scope("root"), org.get_user("root")).has(SYSTEM_DEFAULT_EDIT)
    for uid in ("m", "exec", "da"):
        c = resolve(org.resolve_scope(uid), org.get_user(uid))
        assert not c.has(SYSTEM_DEFAULT_EDIT), f"{uid} 가 시스템 기본을 고칠 수 있으면 안 된다"


def test_platform_admin_sees_every_tab(org):
    org.upsert_user("root", "관리자", primary_dept_id="hq", is_admin=True)
    c = resolve(org.resolve_scope("root"), org.get_user("root"))
    assert set(c.visible_tabs) == set(ADMIN_TABS)
    assert c.is_platform_admin is True and c.bootstrap is False


# ── 서버 재검사 ───────────────────────────────────────────────────────────
def test_require_blocks_missing_capability(org):
    org.upsert_user("u1", "사원", primary_dept_id="prod")
    org.set_user_roles("u1", {"prod": "member"})
    c = resolve(org.resolve_scope("u1"), org.get_user("u1"))
    require(c, AGENT_CREATE)                       # 있는 것은 통과
    with pytest.raises(AdminCapabilityError):
        require(c, ADMIN_SECURITY)


def test_require_demands_all_not_any(org):
    """★★ 여러 개를 넘기면 **전부** 요구한다.

    ⚠️ `any` 를 기본으로 두면 언젠가 넓은 쪽이 우연히 통과한다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    c = resolve(org.resolve_scope("m"), org.get_user("m"))
    assert c.has(ADMIN_USERS)
    with pytest.raises(AdminCapabilityError):
        require(c, ADMIN_USERS, ADMIN_SECURITY)    # 하나만 있어도 막힌다


def test_require_dept_blocks_other_org(org):
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    c = resolve(org.resolve_scope("m"), org.get_user("m"))
    require_dept(c, "prod_a")
    with pytest.raises(AdminCapabilityError):
        require_dept(c, "sales")


def test_unknown_capability_code_is_refused():
    """★★ 오타 하나가 «권한 있음» 이 되면 안 된다."""
    capabilities_for([AGENT_READ, ADMIN_AUDIT])
    with pytest.raises(AdminCapabilityError):
        capabilities_for(["agent.definition.raed"])


# ── 화면 계약 ─────────────────────────────────────────────────────────────
def test_every_admin_route_maps_to_a_registered_capability():
    """★★ Route Guard 와 서버가 **같은 표**를 본다. 표가 갈라지면 보이는데 안 되는 화면이 생긴다."""
    assert set(TAB_ROUTES.values()) == set(ADMIN_TABS)
    for cap in TAB_ROUTES.values():
        assert cap in ALL_CAPABILITIES


def test_to_dict_exposes_menu_visibility_inputs(org):
    """★ 3단계 중 ①(메뉴 가시성)이 쓰는 값이 실제로 나간다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    d = resolve(org.resolve_scope("m"), org.get_user("m")).to_dict()
    assert d["any_admin"] is True
    assert ADMIN_USERS in d["visible_tabs"]
    assert ADMIN_SECURITY not in d["visible_tabs"]
    assert d["manageable_dept_ids"] == ["prod", "prod_a"]


def test_scope_carries_manage_fields_separately(org):
    """★★ `AccessScope` 가 관리 범위를 **확정 결과로** 남긴다(설계 §4.2 요구).

    화면·라우트가 각자 `is_admin` 을 보고 판단하면 세 곳이 서서히 갈라진다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    s = org.resolve_scope("m")
    assert s.can_manage_agents is True
    assert s.manageable_dept_ids == frozenset({"prod", "prod_a"})
    d = s.to_dict()
    assert "can_manage_agents" in d and "manageable_dept_ids" in d and "is_ai_admin" in d


# ── [P1-4] 자산 승인 범위 ─────────────────────────────────────────────────
def test_can_manage_scope_is_separate_from_dept(org):
    """★★ 자산 소유는 **부서 id 가 아니라 조직 범위 노드**(`owner_scope_id`)로 적힌다.

    한 함수에 섞으면 부서 관리 권한이 조직 범위 승인 권한으로 번지거나 그 반대가 된다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    c = resolve(org.resolve_scope("m"), org.get_user("m"))
    for node in c.manageable_scope_nodes:
        assert c.can_manage_scope(node) is True
    assert c.can_manage_scope("NO_SUCH_NODE") is False


def test_unowned_asset_is_not_manageable(org):
    """★★★ 소유 조직이 **비어 있는** 자산은 관리 대상이 아니다.

    ⚠️ 미기재를 «누구나 관리» 로 읽으면 소유를 채우지 않는 것이 이득이 된다 — `MDM-SCOPE-01`
      에서 «바인딩 없으면 통과» 가 유출 창구가 된 것과 같은 형태다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    c = resolve(org.resolve_scope("m"), org.get_user("m"))
    assert c.can_manage_scope("") is False


def test_department_manager_cannot_publish_enterprise(org):
    """★★★ 부서 manager 는 «자기 조직 승인 가능, 전사는 승격 요청만» 이다(설계 §4.2).

    한 부서장이 전 사업부가 쓰는 정의를 혼자 확정하면 그 승인은 누구도 검토하지 않은 승인이다."""
    org.upsert_user("m", "부서장", primary_dept_id="prod")
    org.set_user_roles("m", {"prod": "manager"})
    c = resolve(org.resolve_scope("m"), org.get_user("m"))
    assert c.can_publish_enterprise() is False

    org.upsert_user("ai", "AI관리자", primary_dept_id="prod", is_ai_admin=True)
    ca = resolve(org.resolve_scope("ai"), org.get_user("ai"))
    assert ca.can_publish_enterprise() is True


def test_ai_admin_is_not_limited_by_scope_nodes(org):
    """AI 거버넌스 관리자는 조직 범위 제한을 받지 않는다(설계 §4.2) — 범위 노드가 비어 있어도
    조직 자산을 승인한다. 그 사실을 못 박아 둔다: 나중에 범위 제한을 걸려면 설계 결정이 먼저다."""
    org.upsert_user("ai", "AI관리자", primary_dept_id="prod", is_ai_admin=True)
    c = resolve(org.resolve_scope("ai"), org.get_user("ai"))
    assert c.can_manage_scope("ANY_NODE") is True


def test_existing_users_get_no_new_power_after_migration(org):
    """★★★ 컬럼 추가 마이그레이션이 **아무에게도 권한을 주지 않는다.**

    ⚠️ 권한을 주는 마이그레이션은 조용히 전권을 만드는 가장 흔한 경로다."""
    org.upsert_user("old", "기존사용자", primary_dept_id="sales")
    u = org.get_user("old")
    assert u["is_ai_admin"] is False
    c = resolve(org.resolve_scope("old"), u)
    assert c.any_admin is False and not c.has(MODEL_POLICY_MANAGE)
