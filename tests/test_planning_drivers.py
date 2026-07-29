"""[M4] 계획 동인 — **가정을 업무 언어로, 파급 계수는 근거와 함께.**

"판매량 +10%" 는 경영진이 읽을 수 있지만 "4000 계정 pct +10" 은 읽을 수 없다.
그런데 동인을 도입하면 새로운 위험이 생긴다 — **파급 계수가 그럴듯한 가짜 인과**가 되는 것이다.
`환율 +10% → 원가 +6%` 는 자명하지 않은데, 한 번 등록되면 경영 보고서에
"환율 때문에 원가가 이만큼 오릅니다"로 인쇄된다.

그래서 이 파일이 잠그는 것은 계산이 아니라 **근거의 강제**다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import planning_drivers as dr
from core import planning_engine as eng
from core.planning_model import PLAN, PlanningError, PlanningStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = PlanningStore(db_path=str(tmp_path / "planning.db"))
    monkeypatch.setattr("core.planning_model.planning_store", s)
    monkeypatch.setattr(dr, "planning_store", s)
    monkeypatch.setattr(eng, "planning_store", s)
    s.upsert_account("4000", "매출", "REVENUE", sign=1)
    s.upsert_account("5000", "원가", "COGS", sign=-1)
    s.upsert_account("6000", "판관비", "SGA", sign=-1)
    s.put_fact("MNM_BATTERY", "4000", "2027", PLAN, 1000.0)
    s.put_fact("MNM_BATTERY", "5000", "2027", PLAN, 600.0)
    s.put_fact("MNM_BATTERY", "6000", "2027", PLAN, 200.0)
    return s


# ── 근거의 강제 ──────────────────────────────────────────────────────────────
def test_impact_requires_rationale(store):
    """★★ 근거 없는 파급 계수는 창작이다 — 그리고 그 창작이 경영 보고서에 인쇄된다."""
    dr.register_driver("SALES_VOL", "판매량", unit="ton", category="volume")
    with pytest.raises(PlanningError, match="rationale"):
        dr.add_impact("SALES_VOL", "4000", 1.0, "", "실적회귀")


def test_impact_requires_source(store):
    """실적회귀인지 업계자료인지 전문가판단인지 — 출처가 없으면 검증할 수 없다."""
    dr.register_driver("SALES_VOL", "판매량")
    with pytest.raises(PlanningError, match="source"):
        dr.add_impact("SALES_VOL", "4000", 1.0, "판매량과 매출은 비례", "")


def test_unregistered_driver_is_refused(store):
    with pytest.raises(PlanningError, match="등록되지 않은 동인"):
        dr.add_impact("GHOST", "4000", 1.0, "근거", "출처")


# ── 펼치기 ───────────────────────────────────────────────────────────────────
def test_driver_expands_to_accounts_with_elasticity(store):
    """판매량 +10% → 매출 +10%(탄력도 1.0), 원가 +8%(탄력도 0.8)."""
    dr.register_driver("SALES_VOL", "판매량")
    dr.add_impact("SALES_VOL", "4000", 1.0, "판매량과 매출은 비례", "실적회귀 2024-2026", "cfo")
    dr.add_impact("SALES_VOL", "5000", 0.8, "변동비 비중 80%", "원가분석", "cfo")

    rows, warns = dr.expand_driver_assumption("SALES_VOL", 10.0)
    vals = {r["target_code"]: r["value"] for r in rows}
    assert vals["4000"] == 10.0 and vals["5000"] == 8.0
    assert warns == []
    # 펼쳐진 가정에도 근거가 따라붙는다 — 나중에 "왜 8%인가"에 답할 수 있어야 한다.
    assert "탄력도 0.8" in next(r["rationale"] for r in rows if r["target_code"] == "5000")


def test_driver_without_mapping_is_reported_not_silent(store):
    """★★ "판매량 10% 올렸는데 아무것도 안 변했다"의 유일한 단서."""
    dr.register_driver("FX_RATE", "환율")
    rows, warns = dr.expand_driver_assumption("FX_RATE", 10.0)
    assert rows == []
    assert warns and "파급 계수가 없습니다" in warns[0]


def test_unapproved_elasticity_is_flagged_but_not_blocked(store):
    """미승인 계수를 막으면 도입이 멈춘다 — 대신 결과에 표시한다."""
    dr.register_driver("FX_RATE", "환율")
    dr.add_impact("FX_RATE", "5000", 0.6, "수입 원자재 비중", "업계자료")   # approved_by 없음
    rows, warns = dr.expand_driver_assumption("FX_RATE", 10.0)
    assert rows[0]["approved"] is False
    assert any("미승인" in w for w in warns)


def test_non_pct_driver_operator_is_rejected_with_reason(store):
    """동인은 비율 변화만 의미가 있다 — 조용히 무시하지 않고 사유를 남긴다."""
    dr.register_driver("SALES_VOL", "판매량")
    _, warns = dr.expand_assumptions([{"target_kind": "driver", "target_code": "SALES_VOL",
                                       "operator": "set", "value": 100}])
    assert warns and "pct 만 지원" in warns[0]


def test_account_assumptions_pass_through(store):
    """계정 가정은 그대로 통과 — 두 형태가 한 경로로 합류한다."""
    rows, warns = dr.expand_assumptions([
        {"target_kind": "account", "target_code": "4000", "operator": "pct", "value": 5}])
    assert rows[0]["target_code"] == "4000" and warns == []


# ── 엔진 통합 ────────────────────────────────────────────────────────────────
def _scenario(store, sid, target_kind, code, op, val):
    conn = store._connect()
    try:
        conn.execute("INSERT INTO scenarios(scenario_id,name,org_id,created_at) VALUES(?,?,?,?)",
                     (sid, sid, "MNM_BATTERY", "2026-07-29"))
        conn.execute("INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,"
                     "target_code,operator,value,rationale,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (f"a-{sid}", sid, target_kind, code, op, val, "테스트", "2026-07-29"))
        conn.commit()
    finally:
        conn.close()


def test_engine_applies_driver_assumption(store):
    """★★ 시나리오에 동인 가정을 넣으면 여러 계정에 **한 번에** 파급된다."""
    dr.register_driver("SALES_VOL", "판매량")
    dr.add_impact("SALES_VOL", "4000", 1.0, "비례", "실적회귀", "cfo")
    dr.add_impact("SALES_VOL", "5000", 0.8, "변동비 80%", "원가분석", "cfo")
    _scenario(store, "vol-up", "driver", "SALES_VOL", "pct", 10)

    r = eng.run_scenario("vol-up", "MNM_BATTERY", "2027")
    # 매출 1100, 원가 648, 판관비 200 → 영업이익 252
    assert r["result"]["operating_profit"] == 252.0
    assert r["expanded_count"] == 2          # 동인 하나가 계정 둘로 펼쳐졌다
    assert r["driver_warnings"] == []


def test_engine_surfaces_driver_warning(store):
    """매핑 없는 동인은 결과에 경고로 남는다 — 숫자가 안 변한 이유를 알 수 있어야 한다."""
    dr.register_driver("FX_RATE", "환율")
    _scenario(store, "fx", "driver", "FX_RATE", "pct", 10)

    r = eng.run_scenario("fx", "MNM_BATTERY", "2027")
    assert r["delta"]["net_profit"] == 0.0
    assert r["driver_warnings"], "동인 경고가 결과에 실리지 않았다"


def test_external_indicator_link_is_recorded_not_auto_injected(store):
    """★ §12 외부 지표 연결은 **표시일 뿐 자동 주입이 아니다**(등급 정책은 그쪽에서 강제된다)."""
    d = dr.register_driver("FX_RATE", "환율", external_code="ECOS.USD_KRW", category="fx")
    assert d["external_code"] == "ECOS.USD_KRW"
    # 연결만으로 값이 들어오지 않는다 — 파급 계수가 없으면 아무 일도 일어나지 않는다.
    rows, warns = dr.expand_driver_assumption("FX_RATE", 5.0)
    assert rows == [] and warns
