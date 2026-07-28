# ==========================================
# [§6.3 / §6.1] 데이터 품질 프로파일 + 계보
#
# §6.1 이 이 두 가지에 붙인 제약이 이 테스트의 전부다:
#   품질 — "단순 LLM 평가 금지". 읽지도 않은 데이터에 그럴듯한 점수가 붙으면
#          '품질 확인함'으로 읽히고, 그건 없는 것보다 나쁘다.
#   계보 — "추적성 그래프의 근거". 근거 없이 그은 선으로 만든 영향 분석은
#          **"영향 없음"을 잘못 말해서** 사고를 만든다.
#
# 그래서 여기서 보는 것은 기능이 도는가가 아니라 **거짓을 만들지 않는가**다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.business_glossary import BusinessGlossary
from core.data_catalog import DataCatalog, DataCatalogError
from core.data_lineage import DataLineage, LineageError
from core.master_data import MasterData


@pytest.fixture
def env(tmp_path):
    md = MasterData(db_path=str(tmp_path / "m.db"))
    return DataCatalog(md), BusinessGlossary(md), DataLineage(md)


# ── 품질: 거짓 점수를 만들지 않는가 ───────────────────────────────────────
def test_measured_requires_evidence(env):
    """★★ '측정했다'는 주장은 검증 가능해야 한다 — 근거 없는 measured 는 거짓말이다."""
    dc, _, _ = env
    a = dc.create_asset("표")
    with pytest.raises(DataCatalogError) as e:
        dc.record_quality_profile(a["asset_id"], method="measured", completeness=0.99)
    assert "evidence_ref" in str(e.value)
    assert dc.record_quality_profile(a["asset_id"], method="measured", completeness=0.99,
                                     evidence_ref="run_123")


def test_declared_does_not_require_evidence(env):
    """오너 신고값은 근거가 사람이다 — 막으면 아무도 등록하지 않는다. 대신 method 로 구분된다."""
    dc, _, _ = env
    a = dc.create_asset("표")
    p = dc.record_quality_profile(a["asset_id"], method="declared", completeness=0.8)
    assert p["method"] == "declared" and p["evidence_ref"] == ""


def test_unmeasured_metric_is_null_not_zero(env):
    """★★ 0점과 미측정은 다르다. 0 으로 채우면 '완전성 0%'라는 없는 사실이 생긴다."""
    dc, _, _ = env
    a = dc.create_asset("표")
    p = dc.record_quality_profile(a["asset_id"], method="declared", completeness=0.8)
    assert p["completeness"] == 0.8
    assert p["validity"] is None and p["duplicate_rate"] is None


def test_invalid_method_and_range_are_rejected(env):
    dc, _, _ = env
    a = dc.create_asset("표")
    with pytest.raises(DataCatalogError):
        dc.record_quality_profile(a["asset_id"], method="llm_guess")
    with pytest.raises(DataCatalogError):
        dc.record_quality_profile(a["asset_id"], completeness=1.5)


def test_latest_profile_wins(env):
    dc, _, _ = env
    a = dc.create_asset("표")
    dc.record_quality_profile(a["asset_id"], completeness=0.5,
                              measured_at="2026-01-01T00:00:00+00:00")
    dc.record_quality_profile(a["asset_id"], completeness=0.9,
                              measured_at="2026-07-01T00:00:00+00:00")
    assert dc.latest_quality_profile(a["asset_id"])["completeness"] == 0.9
    assert len(dc.list_quality_profiles(a["asset_id"])) == 2, "이력은 남는다"


# ── 최신성: 모르는 것을 좋게 치지 않는가 ──────────────────────────────────
def test_freshness_unknown_is_not_optimistic(env):
    """★★ 판정 근거가 없으면 unknown 이다. fresh 로 낙관하면 §6.4 최신성 확인이 형식만 남는다."""
    dc, _, _ = env
    a = dc.create_asset("주기없음")                      # cadence·last 둘 다 없음
    assert dc.assess_freshness(a["asset_id"])["state"] == "unknown"

    b = dc.create_asset("주기만", refresh_cadence="daily")
    assert dc.assess_freshness(b["asset_id"])["state"] == "unknown"


def test_adhoc_cadence_is_unknown_not_stale(env):
    """adhoc 은 기대 주기 자체가 없다 — 임의 숫자로 '오래됨' 경고를 만들면 오탐이다."""
    dc, _, _ = env
    a = dc.create_asset("수시", refresh_cadence="adhoc")
    dc.update_asset(a["asset_id"], last_refreshed_at="2020-01-01T00:00:00+00:00")
    assert dc.assess_freshness(a["asset_id"])["state"] == "unknown"


def test_freshness_states(env):
    dc, _, _ = env
    a = dc.create_asset("일간", refresh_cadence="daily")   # 허용 30시간
    now = "2026-07-29T00:00:00+00:00"
    for last, want in (("2026-07-28T12:00:00+00:00", "fresh"),   # 12h
                       ("2026-07-27T12:00:00+00:00", "late"),    # 36h
                       ("2026-07-20T00:00:00+00:00", "stale")):  # 216h
        dc.update_asset(a["asset_id"], last_refreshed_at=last)
        assert dc.assess_freshness(a["asset_id"], now=now)["state"] == want, last


def test_unparseable_timestamp_is_unknown(env):
    """깨진 시각을 0 으로 치면 '방금 갱신됨'이 된다."""
    dc, _, _ = env
    a = dc.create_asset("깨짐", refresh_cadence="daily")
    dc.update_asset(a["asset_id"], last_refreshed_at="어제")
    assert dc.assess_freshness(a["asset_id"])["state"] == "unknown"


# ── 계보: 근거 없는 선을 긋지 않는가 ──────────────────────────────────────
def test_edge_validation(env):
    _, _, lin = env
    with pytest.raises(LineageError):
        lin.add_edge("표", "x", "asset", "y")                    # 잘못된 타입
    with pytest.raises(LineageError):
        lin.add_edge("asset", "x", "asset", "x")                 # 자기 자신
    with pytest.raises(LineageError):
        lin.add_edge("asset", "x", "asset", "y", confidence=2.0)
    with pytest.raises(LineageError):
        lin.add_edge("asset", "", "asset", "y")


def test_add_edge_is_idempotent(env):
    _, _, lin = env
    a = lin.add_edge("asset", "A", "master", "M", "references")
    b = lin.add_edge("asset", "A", "master", "M", "references", confidence=0.5)
    assert a["edge_id"] == b["edge_id"] and b["confidence"] == 0.5


def test_remove_is_soft(env):
    """과거 산출물이 왜 그 값을 썼는지 설명하려면 지난 연결이 남아야 한다."""
    _, _, lin = env
    e = lin.add_edge("asset", "A", "master", "M")
    assert lin.remove_edge(e["edge_id"]) is True
    assert lin.remove_edge(e["edge_id"]) is False
    assert lin.edges_of("asset", "A") == []


def test_derive_only_from_declared_links(env):
    """★★ 도출은 명시된 링크에서만 — 이름이 비슷하다고 잇기 시작하면 영향 분석을 믿을 수 없다."""
    dc, g, lin = env
    a = dc.create_asset("생산실적", owner_dept_id="p", refresh_cadence="daily")
    dc.upsert_field(a["asset_id"], "qty", master_code="FG-A")
    dc.upsert_field(a["asset_id"], "note")                       # 연결 없음
    g.create_term("생산량", master_code="FG-A")
    g.create_term("무관용어")                                     # 연결 없음

    made = lin.derive_edges(catalog=dc, glossary=g)
    assert made["field_to_master"] == 1 and made["term_to_master"] == 1
    assert made["asset_to_field"] == 2
    # 연결 없는 필드·용어는 기준정보로 이어지지 않는다
    assert not lin.edges_of("field", f"{a['asset_id']}.note", "out")


def test_derive_is_idempotent(env):
    dc, g, lin = env
    a = dc.create_asset("표")
    dc.upsert_field(a["asset_id"], "qty", master_code="FG-A")
    lin.derive_edges(catalog=dc, glossary=g)
    before = len(lin.edges_of("asset", a["asset_id"], "out"))
    lin.derive_edges(catalog=dc, glossary=g)
    assert len(lin.edges_of("asset", a["asset_id"], "out")) == before


# ── 영향 분석 ─────────────────────────────────────────────────────────────
def test_impact_traverses_multiple_hops(env):
    """"이 값이 바뀌면 무엇이 틀어지나" — 이게 계보의 존재 이유다."""
    _, _, lin = env
    lin.add_edge("system", "sap", "asset", "A")
    lin.add_edge("asset", "A", "field", "A.f1")
    lin.add_edge("field", "A.f1", "master", "M1")
    r = lin.impact_of("system", "sap")
    ids = {n["node_id"] for n in r["impacted"]}
    assert ids == {"A", "A.f1", "M1"}
    assert max(n["depth"] for n in r["impacted"]) == 3


def test_impact_upstream(env):
    _, _, lin = env
    lin.add_edge("asset", "A", "field", "A.f1")
    lin.add_edge("field", "A.f1", "master", "M1")
    r = lin.impact_of("master", "M1", direction="upstream")
    assert {n["node_id"] for n in r["impacted"]} == {"A.f1", "A"}


def test_impact_survives_cycles(env):
    """★ 조직 데이터에 순환이 없다고 가정하면 언젠가 무한 루프로 서버가 멈춘다."""
    _, _, lin = env
    lin.add_edge("asset", "A", "asset", "B")
    lin.add_edge("asset", "B", "asset", "C")
    lin.add_edge("asset", "C", "asset", "A")
    r = lin.impact_of("asset", "A")
    assert {n["node_id"] for n in r["impacted"]} == {"B", "C"}


def test_impact_respects_depth_limit(env):
    _, _, lin = env
    for i in range(10):
        lin.add_edge("asset", f"n{i}", "asset", f"n{i+1}")
    r = lin.impact_of("asset", "n0", max_depth=3)
    assert r["truncated"] is True and r["impacted_count"] == 3


def test_impact_states_its_limitation(env):
    """★★ "영향 0건"이 "안전하다"로 읽히면 안 된다 — 계보는 등록된 만큼만 안다."""
    _, _, lin = env
    r = lin.impact_of("master", "NEVER-REGISTERED")
    assert r["impacted_count"] == 0
    assert "영향 0건이 곧 안전을 뜻하지 않는다" in r["limitation"]


def test_low_confidence_edges_are_counted(env):
    """확신 없는 선으로 만든 영향 분석은 그 사실이 보여야 한다."""
    _, _, lin = env
    lin.add_edge("asset", "A", "master", "M", confidence=0.4)
    assert lin.impact_of("asset", "A")["low_confidence_count"] == 1


# ── §6.4 와의 배선 ────────────────────────────────────────────────────────
def test_stale_asset_blocks_confirmation(env):
    """★★ 오래된 자산을 확정하면 준비도만 올라가고 실제로는 낡은 값을 쓰게 된다(§6.4 5단계)."""
    dc, g, _ = env
    g.create_term("환율")
    a = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily",
                        description="환율")
    dc.update_asset(a["asset_id"], last_refreshed_at="2020-01-01T00:00:00+00:00")
    c = g.match_requirement("환율", catalog=dc)["candidates"][0]
    assert c["confirmable"] is False
    assert any("오래됐다" in b for b in c["blockers"])
    assert c["freshness"]["state"] == "stale"


def test_match_exposes_quality_profile(env):
    """§6.4 5단계는 '품질 확인'을 포함한다 — 후보에 품질이 안 보이면 확인할 수 없다."""
    dc, g, _ = env
    g.create_term("환율")
    a = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily",
                        description="환율")
    dc.record_quality_profile(a["asset_id"], method="measured", completeness=0.97,
                              evidence_ref="run_1")
    c = g.match_requirement("환율", catalog=dc)["candidates"][0]
    assert c["quality"]["method"] == "measured" and c["quality"]["completeness"] == 0.97


def test_confirm_records_lineage(env, tmp_path):
    """★★ 확정은 계보의 근거가 되는 사건이다 — 여기서 간선을 안 남기면 나중에 그 자산이 바뀔 때
    무엇이 영향받는지 알 수 없다."""
    dc, g, lin = env
    from core.advisor_store import AdvisorStore
    st = AdvisorStore(db_path=str(tmp_path / "adv.db"))
    with st._connect() as conn:
        conn.execute("INSERT INTO solution_blueprints(blueprint_id,title,status,payload_json,"
                     "created_at,updated_at) VALUES('bp1','t','draft','{}','n','n')")
        conn.execute("INSERT INTO blueprint_data_requirements(id,blueprint_id,req_key,"
                     "canonical_term,readiness_status) VALUES('r1','bp1','fx','환율','missing')")
        conn.commit()
    a = dc.create_asset("환율표", owner_dept_id="finance", refresh_cadence="daily")
    out = g.confirm_match("bp1", "fx", a["asset_id"], confirmed_by="kim", store=st, catalog=dc)
    assert out["lineage_edge_id"]

    imp = lin.impact_of("asset", a["asset_id"])
    assert any(n["node_id"] == "bp1/fx" for n in imp["impacted"]), \
        "이 자산이 바뀌면 이 요구사항이 영향받는다는 사실이 남아야 한다"
