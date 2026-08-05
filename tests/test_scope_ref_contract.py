"""★★★ [D-018 ①②④] 조직 범위 해석 계약 — 정본은 `node_id`, 모호하면 해석하지 않는다.

## 결정 (`.agents/DECISIONS.md` `[D-018]`)

ECM 조직 범위의 정본은 불변 `organization_nodes.node_id` 다.
`LS_MNM`·`MNM_BATTERY` 같은 `code` 는 **표시·레거시 매핑용 업무키**, `dept_id` 는 **권한
디렉터리 키**다. 둘 다 입력으로 받되 서버 경계에서 `node_id` 로 정규화하고 혼합 저장하지 않는다.

## 이 파일이 지키는 것

1. **세 형태를 모두 받아 하나의 `node_id` 로 돌려준다**(D-018 ① · D-005 입력 호환 계약).
2. **모호하면 해석하지 않는다**(D-018 ②). 같은 코드·부서가 여러 노드에 걸리면 임의로 하나를
   고르지 않는다 — 종전 `find_node_by_code` 는 `ORDER BY updated_at DESC LIMIT 1` 이었고,
   그것은 «최근에 고친 사람이 조직 권한을 정한다» 는 뜻이었다.
3. **코드는 tenant·entity_mode 문맥에서만 유일하다**(D-018 ④). 문맥을 주면 좁혀지고, 주지
   않으면 전역에서 찾되 후보가 둘 이상일 때 거부한다.
4. **`node_id` 조회에는 문맥을 걸지 않는다.** 전역 PK 이므로 좁힐 필요가 없고, 좁히면
   «맞는 id 인데 문맥이 달라 못 찾는» 상태가 생긴다.

⚠️ 실측(2026-08-05): 지금 데이터에서 코드는 유일하다(노드 16개, tenant+mode+code 중복 0).
  가상 복제가 `V{n}_원본코드` 접두사를 붙여 충돌을 **회피**하기 때문이다(`clone_service`).
  이 테스트는 **그 관행이 깨지는 날 조용히 틀리지 않는지**를 확인한다 — 그래서 중복을 직접
  만들어 넣는다(격리 DB 이므로 안전하다).
"""
import pytest

from core.enterprise_context.models import STATUS_ACTIVE, EnterpriseEntity, OrganizationNode
from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.resolver import EcmResolver


@pytest.fixture()
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture()
def resolver(repo):
    return EcmResolver(repo=repo)


def _entity(repo, name, mode="REAL", base=""):
    return repo.upsert_entity(EnterpriseEntity(
        name_ko=name, entity_mode=mode, base_entity_id=base, status=STATUS_ACTIVE))


def _node(repo, entity_id, code, name, dept_id="", tenant_id="tenant_default"):
    return repo.upsert_node(OrganizationNode(
        entity_id=entity_id, code=code, name_ko=name, dept_id=dept_id,
        tenant_id=tenant_id, status=STATUS_ACTIVE))


# ── 세 형태를 모두 받는다 (D-018 ① · D-005) ───────────────────────────────
def test_node_id_resolves_to_itself(repo, resolver):
    e = _entity(repo, "LS MnM")
    n = _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    r = resolver.resolve_scope_ref(n.node_id)
    assert r["resolved"] is True and r["kind"] == "ecm_node"
    assert r["node_id"] == n.node_id


def test_code_resolves_to_node_id(repo, resolver):
    """★ 코드는 **별칭**이다 — 정본 `node_id` 로 바뀌어 나온다."""
    e = _entity(repo, "LS MnM")
    n = _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    r = resolver.resolve_scope_ref("LS_MNM")
    assert r["resolved"] is True and r["kind"] == "ecm_code"
    assert r["node_id"] == n.node_id


def test_dept_id_resolves_to_node_id(repo, resolver):
    e = _entity(repo, "배터리")
    n = _node(repo, e.entity_id, "MNM_BATTERY", "배터리소재", dept_id="production_battery")
    r = resolver.resolve_scope_ref("production_battery")
    assert r["resolved"] is True and r["kind"] == "department_mapped"
    assert r["node_id"] == n.node_id


def test_resolution_carries_display_fields(repo, resolver):
    """[D-018 ③] 표시용 `code`·`name_ko` 를 함께 준다 — 화면이 `node_id` 해시를 보여줄 수 없다."""
    e = _entity(repo, "LS MnM")
    _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    for ref in ("LS_MNM",):
        r = resolver.resolve_scope_ref(ref)
        assert r["code"] == "LS_MNM" and r["name_ko"] == "LS MnM"


def test_unknown_ref_is_not_resolved(repo, resolver):
    r = resolver.resolve_scope_ref("__no_such_scope__")
    assert r["resolved"] is False and not r["node_id"]


# ── 모호하면 해석하지 않는다 (D-018 ②) ───────────────────────────────────
def test_duplicate_code_is_refused_not_guessed(repo, resolver):
    """★★★ 같은 코드가 두 노드에 걸리면 **해석하지 않는다.**

    ⚠️ 종전에는 `ORDER BY updated_at DESC LIMIT 1` 로 «최근에 고쳐진 것» 이 이겼다. 그것은
      선택이 아니라 **tie-break 가 조직 권한을 결정하는 것**이다 — 이 저장소는 부서 1:N
      매핑에서 이미 같은 사고를 겪었다."""
    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    a = _node(repo, real.entity_id, "LS_MNM", "LS MnM (실제)")
    b = _node(repo, virt.entity_id, "LS_MNM", "LS MnM (가상)")

    r = resolver.resolve_scope_ref("LS_MNM")
    assert r["resolved"] is False, "모호한데 하나를 골랐다"
    assert r["kind"] == "code_ambiguous"
    assert {c["node_id"] for c in r["candidates"]} == {a.node_id, b.node_id}, \
        "어느 후보들 때문에 막혔는지 알려줘야 한다 — 그러지 않으면 고칠 수 없다"
    # 단일 후보 조회도 같은 규칙으로 거부한다.
    assert repo.find_node_by_code("LS_MNM") is None


def test_duplicate_code_is_resolvable_once_context_narrows_it(repo, resolver):
    """★★★ [D-018 ④] **문맥을 주면 유일해진다.** 그것이 «코드는 tenant·entity_mode 안에서만
    유일하다» 의 실질적 의미다."""
    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    a = _node(repo, real.entity_id, "LS_MNM", "LS MnM (실제)")
    b = _node(repo, virt.entity_id, "LS_MNM", "LS MnM (가상)")

    r_real = resolver.resolve_scope_ref("LS_MNM", entity_mode="REAL")
    assert r_real["resolved"] is True and r_real["node_id"] == a.node_id

    r_virt = resolver.resolve_scope_ref("LS_MNM", entity_mode="VIRTUAL")
    assert r_virt["resolved"] is True and r_virt["node_id"] == b.node_id


def test_tenant_narrows_code_lookup(repo, resolver):
    """테넌트 확장에서도 같은 코드가 쓰인다 — 회사마다 `LS_MNM` 이 있을 수 있다."""
    e1 = _entity(repo, "회사1")
    e2 = _entity(repo, "회사2")
    a = _node(repo, e1.entity_id, "HQ", "본사1", tenant_id="tenant_a")
    b = _node(repo, e2.entity_id, "HQ", "본사2", tenant_id="tenant_b")

    assert resolver.resolve_scope_ref("HQ")["resolved"] is False       # 전역이면 모호
    assert resolver.resolve_scope_ref("HQ", tenant_id="tenant_a")["node_id"] == a.node_id
    assert resolver.resolve_scope_ref("HQ", tenant_id="tenant_b")["node_id"] == b.node_id


def test_failure_reasons_are_distinguished(repo, resolver):
    """★★★ 실패를 **세 가지로 나눈다** — 필요한 조치가 다르기 때문이다.

    · `code_ambiguous`      → 데이터를 정리해야 한다(같은 코드가 여러 노드에)
    · `code_out_of_context` → **요청이 틀렸다**(가상 범위를 실제 문맥으로 물었다)
    · `department`          → 매핑을 채워야 한다(ECM 에 없는 부서)

    ⚠️ 한 값으로 뭉개면 운영자가 원인을 짚을 수 없다. 실측에서 «코드는 있는데 문맥이 다르다» 가
      «ECM 에 없는 부서» 로 보고돼 이 구분을 추가했다."""
    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    _node(repo, real.entity_id, "MNM_BATTERY", "배터리(실제)")
    _node(repo, virt.entity_id, "V1_MNM_BATTERY", "배터리(가상)")
    _node(repo, real.entity_id, "DUP", "중복1")
    _node(repo, virt.entity_id, "DUP", "중복2")

    # 코드는 있으나 요청 문맥에 없다 — 후보를 알려줘 어디에 있는지 짚게 한다.
    r = resolver.resolve_scope_ref("MNM_BATTERY", entity_mode="VIRTUAL")
    assert r["resolved"] is False and r["kind"] == "code_out_of_context"
    assert r["requested_entity_mode"] == "VIRTUAL" and r["candidates"]

    assert resolver.resolve_scope_ref("DUP")["kind"] == "code_ambiguous"
    assert resolver.resolve_scope_ref("__no_such__")["kind"] == "department"


def test_out_of_context_is_not_reported_without_context(repo, resolver):
    """문맥을 주지 않았으면 «문맥 불일치» 라는 말이 성립하지 않는다 — 추가 조회도 하지 않는다."""
    real = _entity(repo, "실제")
    _node(repo, real.entity_id, "ONLY_REAL", "실제만")
    r = resolver.resolve_scope_ref("__absent__")
    assert r["kind"] == "department" and "candidates" not in r


def test_duplicate_dept_mapping_is_refused(repo, resolver):
    """부서 경로도 같은 규칙이다(종전부터 지켜지고 있었다 — 회귀 방지로 잠근다)."""
    e = _entity(repo, "실제")
    a = _node(repo, e.entity_id, "MNM_BATTERY", "배터리", dept_id="production")
    b = _node(repo, e.entity_id, "MNM_COPPER", "동제련", dept_id="production")
    r = resolver.resolve_scope_ref("production")
    assert r["resolved"] is False and r["kind"] == "department_ambiguous"
    assert {c["node_id"] for c in r["candidates"]} == {a.node_id, b.node_id}


# ── `node_id` 조회에는 문맥을 걸지 않는다 ─────────────────────────────────
def test_node_id_lookup_ignores_context(repo, resolver):
    """★★ `node_id` 는 전역 PK 다. 문맥으로 좁히면 «맞는 id 인데 문맥이 달라 못 찾는» 상태가
    생기고, 그것은 정본을 정본으로 쓰지 못하게 만든다."""
    # ⚠️ 가상 엔티티는 `base_entity_id` 가 필수다(저장소 계약 — «무엇의 복제인가» 에 답해야 한다).
    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    n = _node(repo, virt.entity_id, "V1_LS_MNM", "LS MnM (가상)")
    # 일부러 **틀린** 문맥을 준다 — 그래도 정본 id 는 해석돼야 한다.
    r = resolver.resolve_scope_ref(n.node_id, entity_mode="REAL", tenant_id="tenant_other")
    assert r["resolved"] is True and r["node_id"] == n.node_id


# ── 얇은 래퍼 (`scoping.resolve_scope_ref`) ───────────────────────────────
def test_thin_wrapper_returns_empty_for_ambiguous(repo, monkeypatch):
    """★★ 문자열 래퍼는 «없다» 와 «모호하다» 를 모두 빈 문자열로 준다 — 그래서 호출부가
    fail-closed 로 동작한다. 구분이 필요하면 리솔버를 직접 부른다."""
    from core.enterprise_context import resolver as _res
    from core.enterprise_context import scoping as sc

    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    _node(repo, real.entity_id, "DUP", "실제")
    _node(repo, virt.entity_id, "DUP", "가상")
    monkeypatch.setattr(_res, "ecm_resolver", EcmResolver(repo=repo))

    assert sc.resolve_scope_ref("DUP") == ""
    assert sc.resolve_scope_ref("DUP", entity_mode="REAL") != ""
    assert sc.resolve_scope_ref("__nope__") == ""


def test_visible_scopes_passes_context_through(repo, monkeypatch):
    """★ `visible_scopes` 는 문맥을 **그대로 흘린다.** 여기서 «REAL 이겠지» 로 채우면 가상
    시나리오 범위가 조용히 실제 범위로 해석된다."""
    from core.enterprise_context import resolver as _res
    from core.enterprise_context import scoping as sc

    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    a = _node(repo, real.entity_id, "DUP", "실제")
    b = _node(repo, virt.entity_id, "DUP", "가상")
    monkeypatch.setattr(_res, "ecm_resolver", EcmResolver(repo=repo))

    # 문맥 없음 → 모호 → 노드로 정규화되지 않는다(입력값만 남는다, fail-closed)
    assert sc.visible_scopes("DUP") == {"DUP"}
    # 문맥 있음 → 각자의 노드로 정규화된다
    assert a.node_id in sc.visible_scopes("DUP", entity_mode="REAL")
    assert b.node_id in sc.visible_scopes("DUP", entity_mode="VIRTUAL")


# ── 기존 관행이 유지되는지 (회귀 방지) ────────────────────────────────────
def test_prefixed_clone_codes_stay_unambiguous(repo, resolver):
    """★ `clone_service` 는 복제 코드에 `V{n}_` 접두사를 붙여 충돌을 **회피**한다. 그 관행이
    지켜지는 동안은 문맥 없이도 해석된다 — 이 테스트가 그 사실을 못 박아 둔다.

    ⚠️ 회피에 의존하지 않는 것이 위 fail-closed 의 목적이다. 둘은 상충하지 않는다."""
    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    a = _node(repo, real.entity_id, "LS_MNM", "LS MnM")
    _node(repo, virt.entity_id, "V1_LS_MNM", "LS MnM (가상)")
    assert resolver.resolve_scope_ref("LS_MNM")["node_id"] == a.node_id
