# ==========================================
# [§6.3 / §14 M1] 데이터 카탈로그
#
# §6.1 은 카탈로그를 MDM 으로도 Graph RAG 로도 **대체 불가**로 규정한다:
#   MDM   = 값 그 자체 / 카탈로그 = 그 값이 어디 있고 누가 책임지며 얼마나 자주 갱신되나
#
# 이 테스트가 지키는 것:
#   ① 크로스워크와 **병렬 등록이 되지 않는다** (같은 대상 두 벌 = 2026-07-29 기준정보 사고 재현)
#   ② 거버넌스 결손(소유자·갱신주기·PII 불일치)이 **자동으로 메워지지 않고 드러난다**
#   ③ 연계에서 가져온 필드의 스키마 속성은 편집 금지 (편집해도 되돌아가면 사용자가 이유를 모름)
#   ④ 검색이 **근거를 함께** 준다 (§6.4 는 최종 확정을 사람 몫으로 못박았다)
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.crosswalk import Crosswalk
from core.data_catalog import DataCatalog, DataCatalogError
from core.master_data import MasterData


@pytest.fixture
def cat(tmp_path):
    md = MasterData(db_path=str(tmp_path / "m.db"))
    return DataCatalog(md), Crosswalk(md)


# ── 기본 등록 ─────────────────────────────────────────────────────────────
def test_create_and_get_asset(cat):
    dc, _ = cat
    a = dc.create_asset("생산실적", asset_type="table", owner_dept_id="production",
                        sensitivity="internal", refresh_cadence="daily",
                        location="mes.prod_result")
    got = dc.get_asset(a["asset_id"])
    assert got["name"] == "생산실적" and got["owner_dept_id"] == "production"
    assert got["status"] == "active" and got["fields"] == []


def test_invalid_vocabulary_is_rejected(cat):
    """어휘를 자유 문자열로 두면 나중에 집계도 필터도 안 된다."""
    dc, _ = cat
    for kw in ({"asset_type": "spreadsheet"}, {"sensitivity": "secret"},
               {"refresh_cadence": "sometimes"}):
        with pytest.raises(DataCatalogError):
            dc.create_asset("X", **kw)


def test_half_link_is_rejected(cat):
    """★ system_id 만 있고 entity 가 없으면 중복 방지 인덱스가 안 걸린다 — 반쪽 링크 금지."""
    dc, _ = cat
    with pytest.raises(DataCatalogError):
        dc.create_asset("X", system_id="sap", entity="")
    with pytest.raises(DataCatalogError):
        dc.create_asset("X", system_id="", entity="MARA")


def test_retire_is_soft(cat):
    """어떤 앱·보고서가 이 자산을 썼는지가 계보의 근거라 물리 삭제하지 않는다."""
    dc, _ = cat
    a = dc.create_asset("임시")
    assert dc.retire_asset(a["asset_id"]) is True
    assert dc.retire_asset(a["asset_id"]) is False
    assert dc.list_assets() == []
    assert any(x["asset_id"] == a["asset_id"] for x in dc.list_assets(include_inactive=True))


# ── ① 크로스워크와 중복 등록 방지 ─────────────────────────────────────────
def _seed_system(xw):
    xw.create_system("sap", "SAP ERP")
    xw.add_schema_field("sap", "MARA", "MATNR", field_type="char", is_key=True)
    xw.add_schema_field("sap", "MARA", "MAKTX", field_type="char")
    xw.add_schema_field("sap", "MSEG", "MENGE", field_type="dec")


def test_sync_creates_one_asset_per_entity(cat):
    dc, xw = cat
    _seed_system(xw)
    r = dc.sync_from_crosswalk("sap", owner_dept_id="it")
    assert r["entities"] == 2 and len(r["assets_created"]) == 2
    assert r["fields_upserted"] == 3
    names = {a["name"] for a in dc.list_assets()}
    assert names == {"sap.MARA", "sap.MSEG"}


def test_sync_is_idempotent(cat):
    """★★ 없으면 동기화할 때마다 같은 테이블이 새 자산으로 쌓인다."""
    dc, xw = cat
    _seed_system(xw)
    dc.sync_from_crosswalk("sap")
    r2 = dc.sync_from_crosswalk("sap")
    assert r2["assets_created"] == [] and len(r2["assets_reused"]) == 2
    assert len(dc.list_assets()) == 2


def test_manual_duplicate_of_linked_entity_is_blocked(cat):
    """★★ 같은 외부 엔터티를 두 자산으로 등록하는 것을 막는다.

    이걸 허용하면 기준정보에서 겪은 것과 같은 문제가 카탈로그에서 재현된다 —
    같은 테이블이 두 벌로 등록되고 어느 쪽이 정본인지 알 수 없어진다."""
    dc, xw = cat
    _seed_system(xw)
    dc.sync_from_crosswalk("sap")
    with pytest.raises(DataCatalogError) as e:
        dc.create_asset("자재마스터(수기)", system_id="sap", entity="MARA")
    assert "이미 등록된 외부 엔터티" in str(e.value)


def test_retired_asset_does_not_block_reregistration(cat):
    """★★ 폐기는 소프트 삭제인데 UNIQUE 인덱스가 그것까지 잡으면 **한 번 폐기한 테이블을
    영원히 다시 등록할 수 없다.** 실제 API 프로브에서 드러난 결함."""
    dc, xw = cat
    _seed_system(xw)
    a = dc.create_asset("자재마스터", system_id="sap", entity="MARA")
    dc.retire_asset(a["asset_id"])
    again = dc.create_asset("자재마스터(재등록)", system_id="sap", entity="MARA")
    assert again["asset_id"] != a["asset_id"] and again["status"] == "active"


def test_sync_reactivates_retired_asset(cat):
    """★★ 폐기된 자산을 '재사용'하면 목록에 안 보이는 자산에 필드만 써넣고 성공했다고 보고한다."""
    dc, xw = cat
    _seed_system(xw)
    dc.sync_from_crosswalk("sap")
    aid = next(a["asset_id"] for a in dc.list_assets() if a["name"] == "sap.MARA")
    dc.retire_asset(aid)
    assert not any(a["asset_id"] == aid for a in dc.list_assets())

    r = dc.sync_from_crosswalk("sap")
    assert aid in r["assets_reactivated"]
    assert any(a["asset_id"] == aid for a in dc.list_assets()), "동기화 후 목록에 보여야 한다"


def test_sync_requires_registered_system(cat):
    dc, _ = cat
    with pytest.raises(DataCatalogError):
        dc.sync_from_crosswalk("no_such_system")


# ── ③ 임포트 필드의 스키마 속성 편집 금지 ─────────────────────────────────
def test_crosswalk_field_schema_is_locked(cat):
    """★ 편집해도 다음 동기화에서 되돌아가므로, 허용하면 같은 수정을 반복하게 된다."""
    dc, xw = cat
    _seed_system(xw)
    dc.sync_from_crosswalk("sap")
    aid = next(a["asset_id"] for a in dc.list_assets() if a["name"] == "sap.MARA")
    with pytest.raises(DataCatalogError) as e:
        dc.upsert_field(aid, "MATNR", logical_type="int")
    assert "되돌아갑니다" in str(e.value)


def test_governance_attributes_stay_editable(cat):
    """거버넌스 속성(용어·기준정보·PII)은 카탈로그의 본업이라 편집 가능해야 한다."""
    dc, xw = cat
    _seed_system(xw)
    dc.sync_from_crosswalk("sap")
    aid = next(a["asset_id"] for a in dc.list_assets() if a["name"] == "sap.MARA")
    dc.upsert_field(aid, "MAKTX", pii_classification="pii", term_id="term_material_name",
                    description="자재명")
    f = next(f for f in dc.get_asset(aid)["fields"] if f["name"] == "MAKTX")
    assert f["pii_classification"] == "pii" and f["term_id"] == "term_material_name"
    assert f["origin"] == "crosswalk", "거버넌스 편집이 출처 표시를 지우면 안 된다"


# ── ② 거버넌스 결손이 드러나는가 ──────────────────────────────────────────
def test_missing_owner_is_a_gap_not_a_silent_default(cat):
    """★ §6.1 의 카탈로그 정의가 '책임'을 포함한다. 소유자 없는 자산은 결함이다."""
    dc, _ = cat
    dc.create_asset("주인없는표", refresh_cadence="daily")
    kinds = {g["kind"] for g in dc.governance_gaps()}
    assert "no_owner" in kinds


def test_missing_refresh_cadence_is_a_gap(cat):
    dc, _ = cat
    dc.create_asset("갱신모름", owner_dept_id="hq")
    kinds = {g["kind"] for g in dc.governance_gaps()}
    assert "no_refresh_cadence" in kinds


def test_pii_below_sensitivity_is_flagged_not_auto_raised(cat):
    """★★ PII 가 있는데 민감도가 낮으면 **자동으로 올리지 않고** 불일치로 표시한다.

    조용히 바꾸면 왜 바뀌었는지 아무도 모르고 사람이 검토하지 않게 된다."""
    dc, _ = cat
    a = dc.create_asset("직원표", owner_dept_id="hq", refresh_cadence="daily",
                        sensitivity="internal")
    dc.upsert_field(a["asset_id"], "resident_no", pii_classification="sensitive_pii")

    g = next(x for x in dc.governance_gaps() if x["kind"] == "sensitivity_below_pii")
    assert g["severity"] == "high" and "restricted" in g["why"]
    assert "자동으로 올리지 않습니다" in g["suggested_action"]
    assert dc.get_asset(a["asset_id"])["sensitivity"] == "internal", "값이 바뀌면 안 된다"


def test_sufficient_sensitivity_is_not_flagged(cat):
    dc, _ = cat
    a = dc.create_asset("직원표", owner_dept_id="hq", refresh_cadence="daily",
                        sensitivity="restricted")
    dc.upsert_field(a["asset_id"], "resident_no", pii_classification="sensitive_pii")
    assert not [g for g in dc.governance_gaps() if g["kind"] == "sensitivity_below_pii"]


def test_gaps_carry_why_and_action(cat):
    dc, _ = cat
    dc.create_asset("빈표")
    for g in dc.governance_gaps():
        assert g["why"] and g["suggested_action"] and g["asset_id"]
        assert g["severity"] in ("high", "medium", "low")


def test_governance_check_does_not_mutate(cat):
    """★ 자동 보정 금지 — 시스템이 소유자를 추측해 넣으면 없는 것보다 나쁘다."""
    dc, _ = cat
    a = dc.create_asset("빈표")
    before = dc.get_asset(a["asset_id"])
    dc.governance_gaps()
    assert dc.get_asset(a["asset_id"]) == before


# ── ④ 검색 (§6.4 3단계) ───────────────────────────────────────────────────
def test_search_matches_name_and_fields(cat):
    dc, _ = cat
    a = dc.create_asset("월별 생산실적", owner_dept_id="production", refresh_cadence="monthly",
                        description="공장별 생산량 집계")
    dc.upsert_field(a["asset_id"], "output_qty", description="생산량")
    dc.create_asset("고객 마스터", owner_dept_id="sales", refresh_cadence="daily")

    hits = dc.search_assets("생산량")
    assert hits and hits[0]["name"] == "월별 생산실적"
    assert "output_qty" in hits[0]["matched_fields"]
    assert not any(h["name"] == "고객 마스터" for h in hits)


def test_search_returns_evidence_and_readiness(cat):
    """★ 근거 없이 후보만 던지면 데이터 오너가 확정할 수 없다(§6.4: 확정은 사람 몫)."""
    dc, _ = cat
    ready = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    dc.create_asset("환율 임시파일", asset_type="file")            # 소유자·주기 없음

    hits = {h["name"]: h for h in dc.search_assets("환율")}
    assert len(hits) == 2
    assert hits["환율표"]["governance_ready"] is True
    assert hits["환율 임시파일"]["governance_ready"] is False, \
        "책임자·갱신주기가 없으면 후보로는 뜨되 확정 가능 상태가 아니다"
    for h in hits.values():
        assert h["why"], "왜 후보인지 근거가 있어야 한다"


def test_search_ignores_retired(cat):
    dc, _ = cat
    a = dc.create_asset("폐기될표", description="환율")
    dc.retire_asset(a["asset_id"])
    assert dc.search_assets("환율") == []


def test_search_empty_query_returns_nothing(cat):
    """빈 검색어에 전체를 돌려주면 화면이 의미 없는 목록으로 채워진다."""
    dc, _ = cat
    dc.create_asset("아무거나")
    assert dc.search_assets("") == [] and dc.search_assets("   ") == []
