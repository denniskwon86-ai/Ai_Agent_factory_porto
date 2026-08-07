"""[D-017 §9 P4-1] 에이전트별 운영 지표 — **대시보드가 조용히 거짓말하지 않게.**

## 실측이 만든 규칙

`llm_call_log.jsonl` 1,133건 중 `agent` 필드가 있는 것은 **113건(10%)** 이다. 계측 축이
나중에 추가됐기 때문이고 그 자체는 정상이다. 그런데 이 상태에서 「에이전트별 비용」을
순진하게 집계하면 **총비용의 10%만 보인다.** 화면에는 그럴듯한 막대가 서고, 아무도
「나머지 90%는 어디 갔나」를 묻지 않는다 — **숫자가 있으면 사람은 그것을 전부라고 읽는다.**

그래서 이 모듈은 세 가지를 지킨다:
1. 귀속되지 않은 호출을 **버리지 않고** «(미상)» 으로 같은 표에 세운다
2. **관측률**을 함께 낸다 — 숫자만이 아니라 문장으로도
3. 단가를 모르는 호출은 비용에 **더하지 않는다**(0 은 「공짜였다」는 거짓이다)
"""
import pytest

from core import agent_operations as ao


def _rec(**kw):
    base = {"agent": "A", "ok": True, "input_tokens": 10, "output_tokens": 5,
            "cost_estimate_usd": 0.001, "attempts": ["m1"], "used": "m1", "stage": "S"}
    base.update(kw)
    return base


# ── ① 귀속되지 않은 호출을 버리지 않는다 ───────────────────────────────────
def test_unattributed_calls_are_kept_not_dropped():
    """★★★ 없는 것처럼 만들면 그 몫은 영원히 아무도 보지 않는다."""
    agg = ao.aggregate_by_agent([_rec(), _rec(agent=""), _rec(agent=None)])
    names = [a["agent"] for a in agg["agents"]]
    assert ao.UNATTRIBUTED in names
    assert sum(a["calls"] for a in agg["agents"]) == 3, "호출이 사라졌다"


def test_coverage_is_reported_as_number_and_sentence():
    """★★ 「관측률 10%」를 숫자로만 두면 아무도 안 본다. 문장으로도 말한다."""
    agg = ao.aggregate_by_agent([_rec()] + [_rec(agent="") for _ in range(9)])
    cov = agg["coverage"]
    assert cov["records"] == 10 and cov["with_agent"] == 1
    assert cov["attribution_rate"] == 0.1
    assert "관측률" in cov["note"] and "전체가 아닙니다" in cov["note"]


def test_full_coverage_says_nothing_alarming():
    """전부 귀속됐으면 경고문이 **비어야** 한다 — 늘 경고하면 경고를 아무도 안 읽는다."""
    agg = ao.aggregate_by_agent([_rec(), _rec(agent="B")])
    assert agg["coverage"]["attribution_rate"] == 1.0
    assert agg["coverage"]["note"] == ""


def test_empty_input_is_not_zero_cost():
    """★ 기록이 없는 것과 비용이 0인 것은 다르다."""
    note = ao.aggregate_by_agent([])["coverage"]["note"]
    assert "기록이 없다" in note


# ── ② 단가를 모르면 0 으로 더하지 않는다 ────────────────────────────────────
def test_unpriced_calls_are_not_counted_as_free():
    """⚠️ 0 으로 더하면 「공짜였다」는 거짓이 된다(`core/llm_cost.py` 주석과 같은 규칙)."""
    agg = ao.aggregate_by_agent([_rec(cost_estimate_usd=None), _rec(cost_estimate_usd=0.5)])
    a = agg["agents"][0]
    assert a["unpriced_calls"] == 1
    assert a["cost_usd"] == 0.5
    assert agg["coverage"]["unpriced_calls"] == 1
    assert "0원이 아니라" in agg["coverage"]["note"]


def test_average_cost_divides_by_priced_calls_only():
    """★ 가격을 모르는 호출이 평균을 낮추면 «싸 보이는» 에이전트가 된다.

    ⚠️ 이름에 그 사실을 담는다(`avg_cost_usd_of_priced`) — 필드 이름이 계산을 설명해야 한다."""
    agg = ao.aggregate_by_agent([_rec(cost_estimate_usd=None), _rec(cost_estimate_usd=1.0)])
    assert agg["agents"][0]["avg_cost_usd_of_priced"] == 1.0


def test_average_is_none_when_nothing_is_priced():
    """모두 미가격이면 평균은 **0 이 아니라 `None`** 이다."""
    agg = ao.aggregate_by_agent([_rec(cost_estimate_usd=None)])
    assert agg["agents"][0]["avg_cost_usd_of_priced"] is None


# ── ③ 성공률·폴백 ───────────────────────────────────────────────────────────
def test_success_and_fallback_rates():
    recs = [_rec(), _rec(ok=False), _rec(attempts=["m1", "m2"])]
    a = ao.aggregate_by_agent(recs)["agents"][0]
    assert a["calls"] == 3 and a["ok"] == 2 and a["failed"] == 1
    assert a["success_rate"] == round(2 / 3, 4)
    assert a["fallback_rate"] == round(1 / 3, 4)


def test_low_success_needs_a_sample():
    """★ 1콜 실패를 «성공률 0%» 로 올리면 목록이 소음이 되고, 소음이면 아무도 안 본다."""
    agg = ao.aggregate_by_agent([_rec(agent="X", ok=False)])
    assert ao.failing_agents(agg) == []
    agg2 = ao.aggregate_by_agent([_rec(agent="X", ok=False) for _ in range(6)])
    rows = ao.failing_agents(agg2)
    assert rows and rows[0]["agent"] == "X" and rows[0]["sample_size"] == 6


def test_low_success_excludes_unattributed():
    """«(미상)» 을 «성능이 나쁜 에이전트» 로 올리면 고칠 대상을 잘못 가리킨다."""
    agg = ao.aggregate_by_agent([_rec(agent="", ok=False) for _ in range(9)])
    assert ao.failing_agents(agg) == []


def test_top_cost_keeps_unattributed():
    """★ 반대로 비용 상위에서는 «(미상)» 을 빼지 않는다 — 대개 그것이 1위이고 그게 중요하다."""
    recs = [_rec(agent="", cost_estimate_usd=9.0)] + [_rec(agent="A", cost_estimate_usd=0.1)]
    top = ao.top_cost_agents(ao.aggregate_by_agent(recs))
    assert top[0]["agent"] == ao.UNATTRIBUTED


# ── ④ 라우트 배선 ───────────────────────────────────────────────────────────
def test_route_exposes_coverage_and_reuses_scope():
    """★★ 집계만 초록이고 라우트가 범위 규칙을 안 쓰면 남의 부서 비용이 보인다.

    ⚠️ 텔레메트리는 이미 `apply_scope` 로 부서 범위를 건다 — **같은 것을 다시 쓴다.**"""
    import inspect

    import api.routes.telemetry_control as tc
    src = inspect.getsource(tc.telemetry_by_agent)
    assert "apply_scope(_read_records(project), p)" in src, "범위 규칙을 다시 만들고 있다"
    assert "aggregate_by_agent" in src
    assert "_scope_meta(scoped)" in src, "무엇이 걸러졌는지 말하지 않는다"
