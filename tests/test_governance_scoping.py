# ==========================================
# [ECM E2] 카탈로그·용어사전·계약의 조직 범위 격리
#
# 기준정보는 R-001 로 격리했는데 이 셋은 안 돼 있었다 — 즉 **같은 누출 경로가 새로 생긴**
# 상태였다. 사업부 자산·용어·계약이 다른 사업부에 새면 안 된다.
#
# 구조 선택의 근거: `master_records` 는 "원본 1 : 적용범위 N"(같은 자재 기준을 여러 법인이
# 함께 참조) 때문에 별도 바인딩 테이블이 필요했다. 자산·용어·계약은 **소유 조직이 하나**다.
# 1:N 이 아닌 것을 1:N 으로 만들면 "이 자산의 주인이 누구냐"에 답이 여러 개가 되어 책임
# 소재가 흐려진다. 그래서 상담·Blueprint 와 같은 ECM-lite 3키를 쓴다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.business_glossary import BusinessGlossary
from core.data_catalog import DataCatalog
from core.data_contract import DataContracts
from core.enterprise_context import EcmRepository, EcmResolver
from core.enterprise_context.scoping import coverage, resolve_scope_ref, visible_scopes
from core.enterprise_context.seed import seed_example_organization
from core.master_data import MasterData


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = EcmRepository(db_path=str(tmp_path / "ecm.db"))
    ids = seed_example_organization(repo)["node_ids"]
    import core.enterprise_context.resolver as res_mod
    monkeypatch.setattr(res_mod, "ecm_resolver", EcmResolver(repo))
    md = MasterData(db_path=str(tmp_path / "m.db"))
    return DataCatalog(md), BusinessGlossary(md), DataContracts(md), ids


# ── 가시성 규칙 자체 ──────────────────────────────────────────────────────
def test_visible_scopes_includes_operating_ancestors(env):
    """상위 조직의 것은 하위가 본다(전사 표준 → 사업부). 그 반대는 아니다."""
    *_, ids = env
    vis = visible_scopes(ids["BATT_PLANT_1"])
    assert ids["BATT_PLANT_1"] in vis and ids["MNM_BATTERY"] in vis and ids["LS_MNM"] in vis
    assert ids["MNM_COPPER"] not in vis
    assert ids["MNM_BATTERY"] not in visible_scopes(ids["LS_MNM"]), "하위 것이 상위에 보이면 안 된다"


def test_visible_scopes_fails_closed(monkeypatch):
    """★ 리솔버 장애를 '전부 보임'으로 처리하면 장애가 곧 전사 유출이 된다."""
    import core.enterprise_context.resolver as res_mod

    class _Broken:
        def ancestors(self, *a, **k):
            raise RuntimeError("boom")
    monkeypatch.setattr(res_mod, "ecm_resolver", _Broken())
    assert visible_scopes("node_x") == {"node_x"}


def test_resolve_scope_ref_failure_is_empty(monkeypatch):
    import core.enterprise_context.resolver as res_mod

    class _Broken:
        def resolve_scope_ref(self, *a, **k):
            raise RuntimeError("boom")
    monkeypatch.setattr(res_mod, "ecm_resolver", _Broken())
    assert resolve_scope_ref("whatever") == ""


# ── 카탈로그 격리 ─────────────────────────────────────────────────────────
def test_catalog_cross_division_isolation(env):
    """★★ 배터리소재 자산이 동제련에 보이면 안 된다."""
    dc, _, _, ids = env
    dc.create_asset("배터리 생산실적", enterprise_scope_id=ids["MNM_BATTERY"])
    dc.create_asset("동제련 생산실적", enterprise_scope_id=ids["MNM_COPPER"])

    batt = {a["name"] for a in dc.list_assets(scope_node_id=ids["MNM_BATTERY"])}
    copper = {a["name"] for a in dc.list_assets(scope_node_id=ids["MNM_COPPER"])}
    assert batt == {"배터리 생산실적"} and copper == {"동제련 생산실적"}


def test_catalog_inherits_from_parent(env):
    """전사 자산은 하위 사업부·공장에 보인다."""
    dc, _, _, ids = env
    dc.create_asset("전사 환율표", enterprise_scope_id=ids["LS_MNM"])
    for node in ("MNM_BATTERY", "MNM_COPPER", "BATT_PLANT_1"):
        assert any(a["name"] == "전사 환율표" for a in dc.list_assets(scope_node_id=ids[node]))


def test_other_legal_entity_sees_nothing(env):
    """★ 다른 법인(LS전선)은 MnM 자산을 전혀 보지 않는다."""
    dc, _, _, ids = env
    dc.create_asset("전사 환율표", enterprise_scope_id=ids["LS_MNM"])
    dc.create_asset("배터리 생산실적", enterprise_scope_id=ids["MNM_BATTERY"])
    assert dc.list_assets(scope_node_id=ids["LS_CABLE"]) == []


def test_unscoped_asset_is_invisible_by_default(env):
    """★★ [관문 A · 2026-07-30] 범위 미지정 자산은 **보이지 않는다**(fail-closed).

    종전 규칙("미지정 = 전사 공용")은 점진 도입 장치였지만 동시에 유출 창구였다. 빈 값은
    **아무 말도 하지 않은 것**이고, 그것을 "전 조직에 공개"로 읽으면 안 된다.
    전사 공용은 이제 `scope_type=ENTERPRISE_SHARED` + 승인 이력이라는 **명시적 상태**다."""
    dc, _, _, ids = env
    dc.create_asset("범위 미지정표")
    assert not any(a["name"] == "범위 미지정표"
                   for a in dc.list_assets(scope_node_id=ids["LS_CABLE"])), \
        "범위 미지정 자산이 타 조직에 그대로 보인다 — 관문 A 가 뚫렸다"
    # 범위를 주지 않는 호출(ECM 미도입 흐름)에서는 그대로 보인다 — 데이터가 사라진 게 아니다.
    assert any(a["name"] == "범위 미지정표" for a in dc.list_assets())


def test_no_scope_argument_means_no_filter(env):
    """ECM 미도입 흐름을 막지 않는다."""
    dc, _, _, ids = env
    dc.create_asset("배터리", enterprise_scope_id=ids["MNM_BATTERY"])
    assert len(dc.list_assets()) == 1


def test_entity_mode_must_match(env):
    """★ REAL 문맥에 VIRTUAL 데이터가 섞이면 그게 곧 오염이다."""
    dc, _, _, ids = env
    dc.create_asset("가상 시나리오표", enterprise_scope_id=ids["MNM_BATTERY"],
                    entity_mode="VIRTUAL")
    assert dc.list_assets(scope_node_id=ids["MNM_BATTERY"], entity_mode="REAL") == []
    assert len(dc.list_assets(scope_node_id=ids["MNM_BATTERY"], entity_mode="VIRTUAL")) == 1


def test_tenant_isolation(env):
    dc, _, _, ids = env
    dc.create_asset("다른 테넌트", tenant_id="tenant_other",
                    enterprise_scope_id=ids["MNM_BATTERY"])
    assert dc.list_assets(scope_node_id=ids["MNM_BATTERY"], tenant_id="tenant_default") == []


def test_search_respects_scope(env):
    """★★ 목록만 막고 검색이 새면 격리가 없는 것과 같다(배선 확인)."""
    dc, _, _, ids = env
    dc.create_asset("배터리 생산실적", description="생산량",
                    enterprise_scope_id=ids["MNM_BATTERY"])
    assert dc.search_assets("생산량", scope_node_id=ids["MNM_COPPER"]) == []
    assert dc.search_assets("생산량", scope_node_id=ids["MNM_BATTERY"])


def test_governance_gaps_respect_scope(env):
    """부서 담당자가 남의 부서 결손까지 떠안으면 목록을 안 본다."""
    dc, _, _, ids = env
    dc.create_asset("남의 부서 결손표", enterprise_scope_id=ids["MNM_COPPER"])
    assert dc.governance_gaps(scope_node_id=ids["MNM_BATTERY"]) == []
    assert dc.governance_gaps(scope_node_id=ids["MNM_COPPER"])


# ── 용어사전 격리 ─────────────────────────────────────────────────────────
def test_terms_are_isolated_and_inherited(env):
    """★★ §6.1 이 지적한 실제 문제 — 같은 말을 부서마다 다르게 정의한다."""
    _, g, _, ids = env
    g.create_term("가동률", calculation="배터리 방식", enterprise_scope_id=ids["MNM_BATTERY"])
    g.create_term("제련수율", calculation="동제련 방식", enterprise_scope_id=ids["MNM_COPPER"])
    g.create_term("영업이익", enterprise_scope_id=ids["LS_MNM"])

    batt = {t["canonical_name"] for t in g.list_terms(scope_node_id=ids["MNM_BATTERY"])}
    assert batt == {"가동률", "영업이익"}, "동제련 용어가 배터리에 새면 안 된다"


def test_expand_respects_scope(env):
    """확장이 남의 부서 용어를 끌어오면 매칭 전체가 오염된다."""
    _, g, _, ids = env
    g.create_term("제련수율", synonyms=["yield"], enterprise_scope_id=ids["MNM_COPPER"])
    assert g.expand("yield", scope_node_id=ids["MNM_BATTERY"])["terms"] == []
    assert g.expand("yield", scope_node_id=ids["MNM_COPPER"])["terms"]


def test_match_requirement_respects_scope(env):
    """★★ §6.4 전 경로에 범위가 이어지는가 — 여기서 끊기면 앞의 격리가 무의미하다."""
    dc, g, _, ids = env
    g.create_term("제련수율", synonyms=["yield"], enterprise_scope_id=ids["MNM_COPPER"])
    dc.create_asset("동제련 수율표", owner_dept_id="p", refresh_cadence="daily",
                    description="yield 원천", enterprise_scope_id=ids["MNM_COPPER"])
    assert g.match_requirement("제련수율", catalog=dc,
                               scope_node_id=ids["MNM_BATTERY"])["candidates"] == []
    assert g.match_requirement("제련수율", catalog=dc,
                               scope_node_id=ids["MNM_COPPER"])["candidates"]


# ── 계약 격리 ─────────────────────────────────────────────────────────────
def test_contracts_are_isolated(env):
    dc, _, dk, ids = env
    a = dc.create_asset("배터리 자산", enterprise_scope_id=ids["MNM_BATTERY"])
    dk.create(name="배터리 공급", producer_asset_id=a["asset_id"], consumer="app",
              catalog=dc, enterprise_scope_id=ids["MNM_BATTERY"])
    assert dk.list(scope_node_id=ids["MNM_COPPER"]) == []
    assert dk.list(scope_node_id=ids["MNM_BATTERY"])
    assert dk.list(scope_node_id=ids["LS_MNM"]) == [], "하위 계약이 상위에 보이면 안 된다"


# ── 관측: 조용한 노출을 막는다 ────────────────────────────────────────────
def test_coverage_counts_unscoped(env):
    """★★ 미지정 건수 관측 — 이게 없어서 기준정보에서 실제 사고가 났다.

    [관문 A] 세는 **목적이 바뀌었다.** 종전엔 "조용히 새는 건수"였고 지금은 "조용히 사라진
    건수"다. 둘 다 조용하면 위험하다 — 안 보이는 이유를 모르면 사용자는 데이터가 지워진 줄
    안다. 그래서 note 는 이제 '보이지 않는다'와 그 해소 방법을 말해야 한다."""
    dc, _, _, ids = env
    dc.create_asset("범위 있음", enterprise_scope_id=ids["MNM_BATTERY"])
    dc.create_asset("범위 없음 1")
    dc.create_asset("범위 없음 2")
    cov = coverage(dc.list_assets(), "자산")
    assert cov["total"] == 3 and cov["unscoped"] == 2
    assert cov["coverage_ratio"] == pytest.approx(1 / 3, abs=1e-4)
    # 표시 없는 미지정은 비노출로 세어지고, 그 사실과 해소 방법이 note 에 있어야 한다.
    assert cov["hidden_unscoped"] == 2 and cov["legacy_grandfathered"] == 0
    assert "보이지 않습니다" in cov["note"] and "지워진 것이 아니라" in cov["note"]


def test_coverage_of_empty_set_is_full(env):
    """0 건일 때 0% 로 표시하면 새 설치가 위험해 보인다."""
    dc, _, _, _ = env
    assert coverage(dc.list_assets())["coverage_ratio"] == 1.0
