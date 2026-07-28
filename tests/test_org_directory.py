# ==========================================
# 조직·사용자·권한 디렉터리 (설계서 Phase 1)
#
# 가장 중요한 계약: **조직 미도입 상태에서 지금과 100% 동일하게 동작**해야 한다.
# `departments` 가 비면 resolve_scope 가 unrestricted=True 를 즉시 반환하고 모든 필터가 no-op 이다.
# 이게 깨지면 기존 기능이 전부 막힌다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.master_data import MasterDataError
from core.org_directory import AccessScope, OrgDirectory


@pytest.fixture()
def org(tmp_path, monkeypatch):
    """권한 해석을 검증하려면 강제 스위치를 켜야 한다.
    기본값 ORG_ENFORCE=False 는 단계적 도입을 위한 안전판이며 별도 테스트로 검증한다."""
    import config
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    return OrgDirectory(db_path=str(tmp_path / "org_test.db"))


# ── 하위호환 계약 ────────────────────────────────────────────────────────
def test_no_departments_means_unrestricted(org):
    assert org.has_any_department() is False
    s = org.resolve_scope("anyone")
    assert s.unrestricted is True
    assert s.can_read("whatever") and s.can_write("whatever")
    assert org.visible_resources(s, "project") is None, "무제한이면 필터하지 말라는 뜻의 None 이어야 합니다"


def test_bootstrap_not_locked_when_no_users_exist(org):
    """★ 부서만 만들고 사용자가 없으면 무제한이어야 한다.
    여기서 강제하면 **첫 관리자를 만들 권한을 가진 사람이 아무도 없어 시스템이 잠긴다**."""
    org.create_department("sales", "영업부")
    assert org.has_any_user() is False
    s = org.resolve_scope("")
    assert s.unrestricted is True and s.can_edit_org is True, "부트스트랩이 막히면 조직을 세울 수 없습니다"


def test_enforcement_starts_after_first_user(org):
    org.create_department("sales", "영업부")
    org.upsert_user("u1", "사용자1")
    assert org.resolve_scope("u1").unrestricted is False, "첫 사용자 등록 후에는 강제되어야 합니다"


def test_org_enforce_switch_off_disables_all_filters(tmp_path, monkeypatch):
    """ORG_ENFORCE=False 면 조직·사용자가 있어도 필터가 no-op — 단계적 도입 안전판."""
    import config
    monkeypatch.setattr(config, "ORG_ENFORCE", False, raising=False)
    od = OrgDirectory(db_path=str(tmp_path / "off.db"))
    od.create_department("sales", "영업부")
    od.upsert_user("u1", "사용자1")
    s = od.resolve_scope("u1")
    assert s.unrestricted is True
    assert od.visible_resources(s, "project") is None


def test_visible_resources_none_vs_empty_are_distinct(org):
    """None(필터 없음)과 []( 볼 게 없음)을 섞으면 무제한 모드에서 아무것도 안 보인다."""
    org.create_department("sales", "영업부")
    org.upsert_user("u1", "사용자1")
    s = org.resolve_scope("u1")
    assert s.unrestricted is False
    assert org.visible_resources(s, "project") == []


# ── 계층 · 경로 ─────────────────────────────────────────────────────────
def test_materialized_path_and_depth(org):
    org.create_department("hq", "본사")
    org.create_department("sales", "영업본부", parent_id="hq")
    org.create_department("kr", "국내영업", parent_id="sales")
    assert org.get_department("kr")["path"] == "/hq/sales/kr/"
    assert org.get_department("kr")["depth"] == 2
    assert set(org.descendants_of("hq")) == {"hq", "sales", "kr"}
    assert set(org.descendants_of("sales")) == {"sales", "kr"}


def test_glob_prefix_does_not_leak_across_underscore(org):
    """GLOB 을 써야 한다 — LIKE 에서 `_` 는 와일드카드라 sales_kr 이 salesXkr 에 매칭된다."""
    org.create_department("sales_kr", "국내영업")
    org.create_department("salesxkr", "무관부서")
    assert org.descendants_of("sales_kr") == ["sales_kr"]


# ── 순환 방지 3중 가드 ───────────────────────────────────────────────────
def test_guard1_self_parent_rejected(org):
    org.create_department("aa", "A")
    with pytest.raises(MasterDataError):
        org.update_department("aa", parent_id="aa")


def test_guard2_descendant_as_parent_rejected(org):
    org.create_department("aa", "A")
    org.create_department("bb", "B", parent_id="aa")
    org.create_department("cc", "C", parent_id="bb")
    with pytest.raises(MasterDataError):
        org.update_department("aa", parent_id="cc")   # 자기 손자를 부모로


def test_guard3_missing_parent_rejected(org):
    with pytest.raises(MasterDataError):
        org.create_department("xx", "X", parent_id="nope")


def test_guard3_depth_limit_enforced(org):
    """ORG_MAX_DEPTH=8 이면 depth 0~8 까지 9단계가 정상이고 10번째에서 막혀야 한다."""
    import config
    limit = getattr(config, "ORG_MAX_DEPTH", 8)
    prev = ""
    for i in range(limit + 1):          # depth 0 .. limit → 정상
        org.create_department(f"d{i:02d}", f"D{i}", parent_id=prev)
        prev = f"d{i:02d}"
    with pytest.raises(MasterDataError) as e:
        org.create_department("over", "초과", parent_id=prev)
    assert "깊이" in str(e.value)


# ── 개편(이동)과 이력 ────────────────────────────────────────────────────
def test_move_updates_subtree_paths(org):
    org.create_department("hq", "본사")
    org.create_department("sales", "영업", parent_id="hq")
    org.create_department("kr", "국내", parent_id="sales")
    org.create_department("new_hq", "신본사")
    org.update_department("sales", parent_id="new_hq")
    assert org.get_department("sales")["path"] == "/new_hq/sales/"
    assert org.get_department("kr")["path"] == "/new_hq/sales/kr/", "하위 트리가 함께 이동해야 합니다"
    assert org.get_department("kr")["depth"] == 2


def test_revision_preserves_history(org):
    org.create_department("sales", "영업부")
    org.update_department("sales", name_ko="영업본부")
    hist = org.get_department_history("sales")
    assert len(hist) == 2
    assert hist[0]["version"] == 2 and hist[0]["status"] == "active"
    assert hist[1]["version"] == 1 and hist[1]["valid_to"] is not None
    assert org.get_department("sales")["name_ko"] == "영업본부"


def test_retire_is_soft_and_blocked_by_children(org):
    org.create_department("hq", "본사")
    org.create_department("sales", "영업", parent_id="hq")
    with pytest.raises(MasterDataError):
        org.retire_department("hq")
    assert org.retire_department("sales") is True
    assert org.get_department("sales")["status"] == "retired"
    # 물리 삭제가 아니어야 ownership 의 과거 참조가 해석 가능하다
    assert any(d["dept_id"] == "sales" for d in org.list_departments(include_retired=True))


# ── 권한 해석 ────────────────────────────────────────────────────────────
def _org_with_tree(org):
    org.create_department("hq", "본사")
    org.create_department("sales", "영업", parent_id="hq")
    org.create_department("kr", "국내", parent_id="sales")
    org.create_department("rnd", "연구소", parent_id="hq")
    return org


def test_role_inheritance_downward(org):
    _org_with_tree(org)
    org.upsert_user("u", "사용자")
    org.set_user_roles("u", {"sales": "manager"})
    s = org.resolve_scope("u")
    assert s.readable_dept_ids == frozenset({"sales", "kr"}), "상위 부서 권한은 하위로 상속된다"
    assert "rnd" not in s.readable_dept_ids
    assert s.can_write("kr") and not s.can_write("rnd")


def test_viewer_can_read_but_not_write(org):
    _org_with_tree(org)
    org.upsert_user("v", "뷰어")
    org.set_user_roles("v", {"sales": "viewer"})
    s = org.resolve_scope("v")
    assert s.can_read("kr") and not s.can_write("kr")


def test_admin_is_unrestricted_with_all_powers(org):
    _org_with_tree(org)
    org.upsert_user("a", "관리자", is_admin=True)
    s = org.resolve_scope("a")
    assert s.unrestricted and s.can_edit_org and s.can_run_enterprise and s.can_manage_standard


def test_executive_reads_all_but_cannot_edit_org(org):
    """경영진은 전 부서를 보고 전사 실행을 하되, 조직 편집·표준 관리 권한은 없다."""
    _org_with_tree(org)
    org.upsert_user("e", "임원", is_executive=True)
    s = org.resolve_scope("e")
    assert s.readable_dept_ids == frozenset({"hq", "sales", "kr", "rnd"})
    assert s.can_run_enterprise is True
    assert s.can_edit_org is False
    assert s.can_manage_standard is False


def test_data_admin_manages_standards_but_not_org(org):
    """DA 는 표준·카탈로그 전권과 전사 열람을 갖되, 조직 편집·전사 실행 권한은 없다."""
    _org_with_tree(org)
    org.upsert_user("da", "데이터관리자", is_data_admin=True)
    s = org.resolve_scope("da")
    assert s.can_manage_standard is True
    assert s.can_edit_org is False
    assert s.can_run_enterprise is False
    assert s.readable_dept_ids == frozenset({"hq", "sales", "kr", "rnd"})


def test_unknown_user_sees_nothing(org):
    _org_with_tree(org)
    org.upsert_user("someone", "등록사용자")   # 사용자가 있어야 강제가 시작된다(부트스트랩 해제)
    s = org.resolve_scope("ghost")
    assert s.unrestricted is False and s.readable_dept_ids == frozenset()


def test_scope_cache_invalidated_on_write(org):
    _org_with_tree(org)
    org.upsert_user("u", "사용자")
    assert org.resolve_scope("u").readable_dept_ids == frozenset()
    org.set_user_roles("u", {"rnd": "member"})
    assert org.resolve_scope("u").readable_dept_ids == frozenset({"rnd"}), "쓰기 후 캐시가 무효화돼야 합니다"


# ── 소유권 미러 ──────────────────────────────────────────────────────────
def test_ownership_visibility_rules(org):
    _org_with_tree(org)
    org.upsert_user("u", "사용자")
    org.set_user_roles("u", {"sales": "member"})
    org.set_ownership("project", "p_sales", dept_id="sales")
    org.set_ownership("project", "p_rnd", dept_id="rnd")
    org.set_ownership("project", "p_pub", dept_id="rnd", visibility="company")
    org.set_ownership("project", "p_mine", dept_id="rnd", owner_user_id="u", visibility="personal")
    got = set(org.visible_resources(org.resolve_scope("u"), "project"))
    assert got == {"p_sales", "p_pub", "p_mine"}
    assert "p_rnd" not in got


def test_invalid_ids_rejected(org):
    with pytest.raises(MasterDataError):
        org.create_department("A", "대문자불가")
    with pytest.raises(MasterDataError):
        org.upsert_user("bad id!", "공백불가")
    org.create_department("ok", "정상")
    org.upsert_user("u", "사용자")
    with pytest.raises(MasterDataError):
        org.set_user_roles("u", {"ok": "superuser"})


# ── 조회 경로 복원력 ─────────────────────────────────────────────────────
# 조직 DB 가 없는 환경(신규 클론·시드 전·작업 디렉터리 변경)에서 부서 조회가 예외로 죽으면
# `create_mega_project` 가 500 으로 실패한다. 그 함수는 미등록 부서를 레거시 기본값으로
# 폴백하도록 설계돼 있으므로, **테이블 부재도 '조직 미도입'으로 흘러가야** 한다.
def test_dept_lookup_survives_missing_schema(tmp_path):
    d = OrgDirectory(db_path=str(tmp_path / "sub" / "gone.db"))
    assert d.list_departments() == []
    assert d.get_department("quality") is None


def test_dept_lookup_survives_unwritable_path(tmp_path, monkeypatch):
    """스키마 복구조차 실패하는 경우에도 예외를 올리지 않는다."""
    d = OrgDirectory(db_path=str(tmp_path / "org.db"))
    monkeypatch.setattr(d, "_ensure_tables", lambda: False)
    assert d.list_departments() == []
    assert d.get_department("quality") is None
