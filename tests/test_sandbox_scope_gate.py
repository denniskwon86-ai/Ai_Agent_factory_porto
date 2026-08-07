"""★★★ [트랙 H] 샌드박스 토큰 발급 범위 — **아무 가상 조직으로든 발급할 수 있었다.**

`core/sandbox_token.issue()` 는 `scope_node_id` 가 **비어 있는지만** 봤다:

    「범위 없는 토큰은 '전부 허용'이 되고, 그것은 권한 승급입니다」

빈 값은 막았는데 **남의 범위**는 막지 않았다. 즉 식별된 사용자면 누구나 **어떤 가상 조직으로든**
읽기 전용 토큰을 발급할 수 있었다.

## 판정 기준을 지어내지 않았다 — 설계가 이미 정해 두었다

`docs/design_enterprise_context_master.md` §7.1: **가상 조직은 실제 조직의 복제본**이고
`EnterpriseEntity.base_entity_id` 가 복제 원본을 가리킨다.

    → **복제 원본을 볼 수 있는 사람이 그 복제본도 볼 수 있다.**

⚠️ 「가상 노드가 내 `readable_scope_nodes` 안에 있는가」로 막으면 **E3 기능이 통째로 죽는다** —
  복제본은 조직 디렉터리에 등록되지 않으므로 아무도 통과하지 못한다. 이 파일의
  `test_clone_of_my_org_is_allowed` 가 그 회귀를 지킨다.

⚠️ 해석 실패는 **거부**(fail-closed)다. 「원본을 못 찾았으니 통과」로 두면 ECM 조회 장애가
  곧 가상 조직 전면 개방이 된다.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.routes.sandbox_control as sc
from core.enterprise_context.models import EnterpriseEntity, OrganizationNode
from core.enterprise_context.repository import EcmRepository

REAL_ENTITY = "ent_real"
VIRTUAL_ENTITY = "ent_virtual"
MY_NODE = "node_mine"
VIRT_NODE = "node_virt"
OTHER_NODE = "node_other"


@pytest.fixture
def ecm(tmp_path, monkeypatch):
    """격리 ECM. ⚠️ 싱글턴을 돌리지 않으면 이 검사가 **운영 조직도에 좌우된다.**"""
    repo = EcmRepository(db_path=str(tmp_path / "ecm.db"))
    repo.upsert_entity(EnterpriseEntity(
        entity_id=REAL_ENTITY, name_ko="실제회사", entity_mode="REAL"))
    repo.upsert_entity(EnterpriseEntity(
        entity_id=VIRTUAL_ENTITY, name_ko="가상복제본", entity_mode="VIRTUAL",
        base_entity_id=REAL_ENTITY))
    repo.upsert_node(OrganizationNode(
        node_id=MY_NODE, entity_id=REAL_ENTITY, code="MINE", name_ko="내 부서",
        dept_id="quality"))
    repo.upsert_node(OrganizationNode(
        node_id=VIRT_NODE, entity_id=VIRTUAL_ENTITY, code="VIRT", name_ko="가상 부서"))
    repo.upsert_node(OrganizationNode(
        node_id=OTHER_NODE, entity_id=REAL_ENTITY, code="OTHER", name_ko="남의 부서",
        dept_id="sales"))
    import core.enterprise_context.repository as mod
    monkeypatch.setattr(mod, "ecm_repository", repo, raising=False)
    return repo


def _p(*, unrestricted=False, nodes=(), depts=()):
    return SimpleNamespace(user_id="u@ls", scope=SimpleNamespace(
        unrestricted=unrestricted,
        readable_scope_nodes=frozenset(nodes), readable_dept_ids=frozenset(depts)))


# ── ① 남의 가상 조직은 막는다 ───────────────────────────────────────────────
def test_foreign_virtual_scope_is_refused(ecm):
    """★★★ 이 파일 전체의 이유. 내 조직과 무관한 복제본으로는 토큰을 못 만든다."""
    with pytest.raises(HTTPException) as e:
        sc._assert_may_sandbox(_p(nodes={"node_somewhere_else"}), VIRT_NODE)
    assert e.value.status_code == 403


def test_unknown_scope_is_refused(ecm):
    """존재하지 않는 범위 — 원본을 찾을 수 없으므로 거부다(fail-closed)."""
    with pytest.raises(HTTPException):
        sc._assert_may_sandbox(_p(nodes={MY_NODE}), "node_does_not_exist")


def test_resolver_failure_is_fail_closed(ecm, monkeypatch, capsys):
    """⚠️ ECM 조회가 죽으면 **거부**다. 「못 찾았으니 통과」는 곧 가상 조직 전면 개방이다."""
    import core.enterprise_context.repository as mod
    monkeypatch.setattr(mod.ecm_repository, "get_node",
                        lambda _n: (_ for _ in ()).throw(OSError("db locked")))
    with pytest.raises(HTTPException):
        sc._assert_may_sandbox(_p(nodes={MY_NODE}), VIRT_NODE)
    assert "db locked" in capsys.readouterr().out


# ── ② E3 기능을 죽이지 않는다 ───────────────────────────────────────────────
def test_clone_of_my_org_is_allowed(ecm):
    """★★★ **이 검사가 «막기» 보다 중요하다.**

    가상 노드는 조직 디렉터리에 등록되지 않으므로 `readable_scope_nodes` 로 판정하면
    **아무도 통과하지 못하고 E3 기능이 통째로 죽는다.** 복제 원본을 따라가야 한다."""
    sc._assert_may_sandbox(_p(nodes={MY_NODE}), VIRT_NODE)      # 예외가 나면 실패


def test_clone_is_allowed_via_dept_mapping(ecm):
    """부서 권한만 가진 사용자도 통과한다 — ECM 은 부서 체계를 **교체하지 않고 매핑**한다(§10.1)."""
    sc._assert_may_sandbox(_p(depts={"quality"}), VIRT_NODE)


def test_real_node_in_my_scope_passes_directly(ecm):
    """실제 조직 노드를 그대로 준 경우 — 복제 추적 없이 바로 통과."""
    sc._assert_may_sandbox(_p(nodes={MY_NODE}), MY_NODE)


def test_unrestricted_subject_passes(ecm):
    """조직 미도입·플랫폼 관리자 — 하위호환 계약."""
    sc._assert_may_sandbox(_p(unrestricted=True), VIRT_NODE)


# ── ③ 라우트가 판정을 부르는가 ──────────────────────────────────────────────
def test_issue_route_calls_the_gate():
    """⚠️ 판정 함수를 만들어 두고 라우트가 안 부르면 아무 일도 일어나지 않는다."""
    import inspect
    src = inspect.getsource(sc.issue_token)
    assert "_assert_may_sandbox(" in src, "발급 라우트가 범위 판정을 부르지 않는다"


def test_revoke_requires_identity():
    """회수는 **소유자**를 안 보지만 **식별**은 요구한다(감사의 actor).

    ⚠️ bearer 토큰이므로 소유자 검사는 보호가 아니라 사고 대응 지연이다 — 유출된 토큰을
      발견한 사람이 즉시 끊을 수 있어야 한다. 그러나 `actor=unknown` 으로 남는 회수는
      「누가 끊었나」에 답할 수 없어 조사에 쓸모가 없다."""
    import inspect
    src = inspect.getsource(sc.revoke_token)
    assert "_actor(p)" in src, "회수가 식별을 요구하지 않는다"
