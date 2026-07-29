"""[M4] Backtest — **모델을 믿어도 되는지** 과거로 검증한다 (§17.3 파일럿 성공 기준).

Backtest 의 고전적 실패는 **결과를 알고 나서 만든 가정으로 과거를 맞히는 것**이다.
그러면 오차가 0 에 가깝게 나오고 사람들은 모델이 훌륭하다고 믿는다 — 그리고 실제 미래에
쓰면 완전히 빗나간다.

그래서 이 파일이 잠그는 것은 "오차를 잘 계산하는가"가 아니라
**"오차를 액면 그대로 믿게 두지 않는가"** 다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import planning_backtest as bt
from core import planning_drivers as dr
from core import planning_engine as eng
from core.planning_model import ACTUAL, PLAN, PlanningStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = PlanningStore(db_path=str(tmp_path / "planning.db"))
    for mod in ("core.planning_model", ):
        monkeypatch.setattr(f"{mod}.planning_store", s)
    monkeypatch.setattr(eng, "planning_store", s)
    monkeypatch.setattr(bt, "planning_store", s)
    monkeypatch.setattr(dr, "planning_store", s)
    s.upsert_account("4000", "매출", "REVENUE", sign=1)
    s.upsert_account("5000", "원가", "COGS", sign=-1)
    return s


def _pa(s, period, plan_rev, act_rev, plan_cost=600.0, act_cost=600.0):
    s.put_fact("MNM_BATTERY", "4000", period, PLAN, plan_rev)
    s.put_fact("MNM_BATTERY", "5000", period, PLAN, plan_cost)
    s.put_fact("MNM_BATTERY", "4000", period, ACTUAL, act_rev)
    s.put_fact("MNM_BATTERY", "5000", period, ACTUAL, act_cost)


# ── 잴 수 없으면 재지 않는다 ─────────────────────────────────────────────────
def test_missing_actual_is_not_zero_error(store):
    """★★ 없는 값을 0 으로 두면 **오차 100%** 로 잘못 읽힌다."""
    store.put_fact("MNM_BATTERY", "4000", "2026", PLAN, 1000.0)
    r = bt.backtest_plan("MNM_BATTERY", "2026")
    assert r["measurable"] is False and "실적이 없습니다" in r["reason"]


def test_zero_actual_accounts_are_excluded_and_named(store):
    """실적이 0 인 계정은 백분율을 낼 수 없다 — 조용히 빼면 MAPE 가 실제보다 좋아 보인다."""
    _pa(store, "2026", 1000.0, 900.0, plan_cost=100.0, act_cost=0.0)
    r = bt.backtest_plan("MNM_BATTERY", "2026")
    assert r["excluded_zero_actual"] == ["5000"]
    assert r["measured_accounts"] == 1


# ── 오차 지표 ────────────────────────────────────────────────────────────────
def test_mape_and_bias(store):
    """계획 1000 · 실적 900 → +11.11% 과대추정."""
    _pa(store, "2026", 1000.0, 900.0)
    r = bt.backtest_plan("MNM_BATTERY", "2026")
    assert r["measurable"] is True
    rev = next(x for x in r["by_account"] if x["account_code"] == "4000")
    assert rev["pct_error"] == pytest.approx(11.11, abs=0.01)
    assert r["bias"] > 0        # 과대추정 방향


def test_bias_distinguishes_two_very_different_models(store, tmp_path, monkeypatch):
    """★★ MAPE 가 같아도 **완전히 다른 문제**다.

    늘 +10% 과대추정하는 모델은 보정하면 되고, 어떤 해는 +10% 어떤 해는 −10% 인 모델은
    못 믿는다. `mape` 하나만 보면 이 둘이 구분되지 않는다."""
    s2 = PlanningStore(db_path=str(tmp_path / "b.db"))
    monkeypatch.setattr(bt, "planning_store", s2)
    s2.upsert_account("4000", "매출", "REVENUE", sign=1)
    # 한쪽으로 치우친 모델
    s2.put_fact("O", "4000", "2025", PLAN, 1100.0)
    s2.put_fact("O", "4000", "2025", ACTUAL, 1000.0)
    s2.put_fact("O", "4000", "2026", PLAN, 1100.0)
    s2.put_fact("O", "4000", "2026", ACTUAL, 1000.0)
    biased = bt.backtest_series("O", ["2025", "2026"])
    assert biased["systematic_bias"] is True
    assert "한쪽으로 치우쳐" in biased["note"]

    # 진동하는 모델 — 평균 오차는 비슷한데 방향이 갈린다
    s2.put_fact("O", "4000", "2026", PLAN, 900.0)
    swinging = bt.backtest_series("O", ["2025", "2026"])
    assert swinging["systematic_bias"] is False


def test_worst_account_is_surfaced(store):
    """평균이 좋아도 **한 계정이 크게 틀리면** 그 계획은 못 쓴다."""
    _pa(store, "2026", 1000.0, 990.0, plan_cost=600.0, act_cost=300.0)
    r = bt.backtest_plan("MNM_BATTERY", "2026")
    assert r["worst"]["account_code"] == "5000"


def test_accounts_present_on_only_one_side_are_listed(store):
    """계획엔 있는데 실적이 없는 계정(또는 그 반대)은 **오차가 아니라 결손**이다."""
    _pa(store, "2026", 1000.0, 900.0)
    store.put_fact("MNM_BATTERY", "9000", "2026", PLAN, 50.0)
    store.upsert_account("9000", "기타", "SGA", sign=-1)
    r = bt.backtest_plan("MNM_BATTERY", "2026")
    assert r["only_predicted"] == ["9000"]


# ── ★★ 미래 정보 누설 ───────────────────────────────────────────────────────
def _scn(store, sid, created_at, code="4000", op="pct", val=10):
    conn = store._connect()
    try:
        conn.execute("INSERT INTO scenarios(scenario_id,name,org_id,created_at) VALUES(?,?,?,?)",
                     (sid, sid, "MNM_BATTERY", created_at))
        conn.execute("INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,"
                     "target_code,operator,value,rationale,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (f"a-{sid}", sid, "account", code, op, val, "근거", created_at))
        conn.commit()
    finally:
        conn.close()


def test_lookahead_bias_is_flagged(store):
    """★★ 결과를 알고 나서 만든 가정으로 과거를 맞히면 **오차가 0 에 가깝게 나온다.**

    그리고 사람들은 모델을 신뢰한다 — 실제 미래에 쓰면 완전히 빗나간다."""
    _pa(store, "2026", 1000.0, 1100.0)
    _scn(store, "hindsight", "2027-01-01")       # 대상 기간(2026) 이후에 작성
    r = bt.backtest_scenario("hindsight", "MNM_BATTERY", "2026")
    assert r["lookahead_risk"] is True
    assert any("미래 정보 누설" in w for w in r["warnings"])


def test_contemporaneous_assumption_is_not_flagged(store):
    """대상 기간 안에 만들어진 가정은 정상이다 — 경고가 남발되면 아무도 안 본다."""
    _pa(store, "2026", 1000.0, 1100.0)
    _scn(store, "honest", "2026-01-01")
    r = bt.backtest_scenario("honest", "MNM_BATTERY", "2026")
    assert r["lookahead_risk"] is False


def test_scenario_backtest_measures_against_actual(store):
    """시나리오를 과거에 돌려 실적과 비교한다 — 매출 +10% → 1100, 실적 1100 이면 오차 0."""
    _pa(store, "2026", 1000.0, 1100.0)
    _scn(store, "up10", "2026-01-01")
    r = bt.backtest_scenario("up10", "MNM_BATTERY", "2026")
    rev = next(x for x in r["by_account"] if x["account_code"] == "4000")
    assert rev["predicted"] == 1100.0 and rev["pct_error"] == 0.0


def test_unapplied_assumptions_are_warned_in_backtest(store):
    """적용되지 않은 가정이 있으면 **이 결과는 의도한 시나리오가 아니다.**"""
    _pa(store, "2026", 1000.0, 1100.0)
    _scn(store, "ghost", "2026-01-01", code="7777")
    r = bt.backtest_scenario("ghost", "MNM_BATTERY", "2026")
    assert any("적용되지 않은 가정" in w for w in r["warnings"])


def test_scenario_backtest_without_actual_is_refused(store):
    """실적 없이 backtest 하면 **무엇과 비교했는지** 알 수 없다."""
    store.put_fact("MNM_BATTERY", "4000", "2026", PLAN, 1000.0)
    _scn(store, "x", "2026-01-01")
    r = bt.backtest_scenario("x", "MNM_BATTERY", "2026")
    assert r["measurable"] is False


# ── 연속 기간 ────────────────────────────────────────────────────────────────
def test_series_needs_measurable_periods(store):
    r = bt.backtest_series("MNM_BATTERY", ["2024", "2025"])
    assert r["measurable"] is False


def test_series_averages_and_keeps_each_period(store):
    """한 해만 맞힌 것은 우연일 수 있다 — 기간별 결과를 함께 남긴다."""
    _pa(store, "2025", 1000.0, 950.0)
    _pa(store, "2026", 1000.0, 900.0)
    r = bt.backtest_series("MNM_BATTERY", ["2025", "2026"])
    assert r["measurable"] is True
    assert len(r["results"]) == 2 and r["avg_mape"] > 0
