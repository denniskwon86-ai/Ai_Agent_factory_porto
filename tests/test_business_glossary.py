# ==========================================
# [§6.3 / §6.4] 업무 용어사전 + 데이터 요구사항 매칭
#
# §6.1: 용어사전은 "MDM 과 연결되나 **별도 관리**".
#   MDM 은 값(RM-MHP-001 단가 15,000), 용어사전은 말(현업이 부르는 이름과 계산 정의).
#   "가동률"이 부서마다 다르게 계산되는 것이 제조 현장의 실제 문제이고, 합의된 계산 정의를
#   적어두지 않으면 LLM 이 그때그때 지어낸다.
#
# §6.4 가 못박은 것: "LLM 은 후보 검색·설명에만 사용한다. **최종 매칭 확정은 데이터 오너 또는
#   승인된 규칙이 담당한다.**" → 이 테스트의 절반은 "자동으로 확정하지 않는가"를 본다.
#   준비도는 착수 판단에 쓰이므로 근거 없는 상향이 가장 위험하다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.business_glossary import BusinessGlossary, GlossaryError
from core.data_catalog import DataCatalog
from core.master_data import MasterData


@pytest.fixture
def gc(tmp_path):
    md = MasterData(db_path=str(tmp_path / "m.db"))
    return BusinessGlossary(md), DataCatalog(md)


# ── 용어 ──────────────────────────────────────────────────────────────────
def test_create_term_with_calculation(gc):
    """★ 합의된 계산 정의가 이 테이블의 존재 이유다 — 없으면 LLM 이 지어낸다."""
    g, _ = gc
    t = g.create_term("가동률", definition="설비가 실제로 돌아간 비율",
                      calculation="실가동시간 / 계획가동시간", domain="manufacturing",
                      synonyms=["OEE", "operating rate"])
    assert t["calculation"] == "실가동시간 / 계획가동시간"
    assert {s["synonym"] for s in t["synonyms"]} == {"OEE", "operating rate"}
    assert t["status"] == "draft", "등록만으로 전사 합의가 되면 안 된다"


def test_duplicate_canonical_name_is_rejected(gc):
    g, _ = gc
    g.create_term("가동률")
    with pytest.raises(GlossaryError):
        g.create_term("가동률")


def test_retired_name_can_be_reused(gc):
    """폐기한 이름을 영원히 못 쓰면 용어 정비가 막힌다."""
    g, _ = gc
    t = g.create_term("가동률")
    g.retire_term(t["term_id"])
    assert g.create_term("가동률")["term_id"] != t["term_id"]


def test_approval_requires_an_approver(gc):
    """★ 승인자 없는 승인은 "누가 이 정의에 합의했나"에 답할 수 없다."""
    g, _ = gc
    t = g.create_term("가동률")
    with pytest.raises(GlossaryError):
        g.approve_term(t["term_id"], "")
    out = g.approve_term(t["term_id"], "kim")
    assert out["status"] == "approved" and out["approved_by"] == "kim"


# ── 동의어 확장 (§6.4 1~2단계) ────────────────────────────────────────────
def test_expand_finds_term_by_synonym(gc):
    g, _ = gc
    g.create_term("가동률", synonyms=["OEE"])
    exp = g.expand("OEE 를 개선하고 싶다")
    assert exp["terms"] and exp["terms"][0]["canonical_name"] == "가동률"
    assert "OEE" in exp["words"] and "가동률" in exp["words"]


def test_unapproved_synonyms_are_reported_separately(gc):
    """★★ 섞어서 주면 "이 매칭의 근거가 승인된 것이었나"를 되짚을 수 없다."""
    g, _ = gc
    t = g.create_term("가동률", synonyms=["OEE", "설비효율"])
    g.approve_synonym(t["term_id"], "OEE", "kim")
    exp = g.expand("가동률")
    assert "설비효율" in exp["unapproved"] and "OEE" not in exp["unapproved"]


def test_approved_only_mode_excludes_unapproved(gc):
    g, _ = gc
    g.create_term("가동률", synonyms=["설비효율"])
    assert "설비효율" not in g.expand("가동률", approved_only=True)["words"]


def test_expand_empty_returns_nothing(gc):
    g, _ = gc
    g.create_term("가동률")
    assert g.expand("")["terms"] == []


# ── §6.4 매칭 ─────────────────────────────────────────────────────────────
def test_match_finds_asset_via_synonym(gc):
    """★★ 동의어 확장이 실제로 카탈로그 검색으로 이어지는가(배선 확인)."""
    g, dc = gc
    t = g.create_term("가동률", synonyms=["OEE"])
    g.approve_synonym(t["term_id"], "OEE", "kim")
    dc.create_asset("설비 로그", owner_dept_id="production", refresh_cadence="hourly",
                    description="OEE 산출용 원천")
    r = g.match_requirement("가동률", catalog=dc)
    assert r["candidates"] and r["candidates"][0]["name"] == "설비 로그"
    assert "OEE" in r["candidates"][0]["matched_via"]


def test_match_never_auto_confirms(gc):
    """★★ §6.4: 최종 확정은 데이터 오너의 몫. 후보 산출이 확정이 되면 안 된다."""
    g, dc = gc
    g.create_term("환율", synonyms=["FX"])
    dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    r = g.match_requirement("환율", catalog=dc)
    assert "최종 매칭 확정은 데이터 오너" in r["note"]
    assert all("confirmable" in c for c in r["candidates"])


def test_unapproved_synonym_match_is_not_confirmable(gc):
    """★ 미승인 동의어로만 걸린 후보는 확정 근거가 약하다."""
    g, dc = gc
    g.create_term("가동률", synonyms=["OEE"])            # 승인 안 함
    dc.create_asset("설비 로그", owner_dept_id="production", refresh_cadence="hourly",
                    description="OEE 원천")
    c = g.match_requirement("가동률", catalog=dc)["candidates"][0]
    assert c["confirmable"] is False
    assert any("승인되지 않은 동의어" in b for b in c["blockers"])


def test_asset_without_owner_is_not_confirmable(gc):
    """§6.4 5단계(품질·최신성·권한 확인)를 할 수 없는 자산은 확정할 수 없다."""
    g, dc = gc
    g.create_term("환율")
    dc.create_asset("환율 임시파일", asset_type="file", description="환율")
    c = g.match_requirement("환율", catalog=dc)["candidates"][0]
    assert c["confirmable"] is False
    assert any("책임자 또는 갱신주기" in b for b in c["blockers"])


def test_missing_mdm_link_is_a_blocker(gc):
    """§6.4 4단계 — 용어가 기준정보를 가리키는데 필드 연결이 없으면 확정 못 한다."""
    g, dc = gc
    g.create_term("MHP 단가", master_code="RM-MHP-001")
    a = dc.create_asset("구매단가표", owner_dept_id="purchasing", refresh_cadence="daily",
                        description="MHP 단가")
    c = g.match_requirement("MHP 단가", catalog=dc)["candidates"][0]
    assert any("기준정보(RM-MHP-001)" in b for b in c["blockers"])

    dc.upsert_field(a["asset_id"], "unit_price", master_code="RM-MHP-001")
    c2 = g.match_requirement("MHP 단가", catalog=dc)["candidates"][0]
    assert not any("기준정보" in b for b in c2["blockers"])


def test_match_works_without_registered_term(gc):
    """★ 용어사전이 비어 있다고 매칭이 통째로 멈추면 도입 초기에 아무것도 못 한다(점진 도입)."""
    g, dc = gc
    dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    r = g.match_requirement("환율표", catalog=dc)
    assert r["resolved_term"] is None and r["candidates"]


def test_candidates_ordered_by_confirmability(gc):
    """확정 가능한 것이 위로 와야 한다 — 목록 위에 못 쓸 후보가 있으면 아래를 안 본다."""
    g, dc = gc
    g.create_term("환율")
    dc.create_asset("환율 임시파일", asset_type="file", description="환율")   # 결손
    dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily",
                    description="환율")
    names = [c["name"] for c in g.match_requirement("환율", catalog=dc)["candidates"]]
    assert names[0] == "환율표"


# ── §6.4 6단계: 확정 (사람 행위) ──────────────────────────────────────────
def test_confirm_requires_a_person(gc):
    """★★ 확정자 없는 매칭은 준비도 점수의 근거가 사라진다."""
    g, dc = gc
    a = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    with pytest.raises(GlossaryError) as e:
        g.confirm_match("bp1", "fx_rate", a["asset_id"], confirmed_by="", catalog=dc)
    assert "확정자" in str(e.value)


def test_confirm_rejects_unknown_asset(gc):
    g, dc = gc
    with pytest.raises(GlossaryError):
        g.confirm_match("bp1", "fx_rate", "da_nope", confirmed_by="kim", catalog=dc)


def test_confirm_rejects_bad_status(gc):
    g, dc = gc
    a = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    with pytest.raises(GlossaryError):
        g.confirm_match("bp1", "fx_rate", a["asset_id"], confirmed_by="kim",
                        readiness_status="perfect", catalog=dc)


def test_confirm_updates_requirement_status(gc, tmp_path):
    """★★ §6.4 6단계 배선 — 확정이 실제로 데이터 요구사항 상태를 바꾸는가."""
    g, dc = gc
    from core.advisor_store import AdvisorStore
    st = AdvisorStore(db_path=str(tmp_path / "adv.db"))
    with st._connect() as conn:
        conn.execute("INSERT INTO solution_blueprints(blueprint_id,title,status,payload_json,"
                     "created_at,updated_at) VALUES('bp1','t','draft','{}','now','now')")
        conn.execute("INSERT INTO blueprint_data_requirements(id,blueprint_id,req_key,"
                     "canonical_term,readiness_status) VALUES('r1','bp1','fx_rate','환율','missing')")
        conn.commit()

    a = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    out = g.confirm_match("bp1", "fx_rate", a["asset_id"], confirmed_by="kim", store=st,
                          catalog=dc)
    assert out["readiness_status"] == "held"
    with st._connect() as conn:
        row = conn.execute("SELECT readiness_status FROM blueprint_data_requirements "
                           "WHERE id='r1'").fetchone()
    assert row["readiness_status"] == "held"


def test_confirm_rejects_unknown_requirement(gc, tmp_path):
    """없는 요구사항에 조용히 성공하면 아무것도 안 바뀐 채 확정됐다고 믿게 된다."""
    g, dc = gc
    from core.advisor_store import AdvisorStore
    st = AdvisorStore(db_path=str(tmp_path / "adv.db"))
    a = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    with pytest.raises(GlossaryError):
        g.confirm_match("bp_none", "nope", a["asset_id"], confirmed_by="kim", store=st,
                        catalog=dc)
