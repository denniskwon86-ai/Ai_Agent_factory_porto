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


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ [2026-08-07] 레코드를 콜로 세면 **실패한 호출만 분모를 두 배로 키운다**
#
# 이 화면은 `Master_PMO 성공률 6.7%` 를 띄웠고 그 숫자는 두 겹으로 틀렸다.
# 첫 겹이 여기다 — 게이트웨이는 실패하면 `pro(retry0)`+`flash(retry1)` 로 **2줄**을,
# 성공하면 **1줄**을 남긴다. 줄로 나누면 실패 쪽만 분모가 부푼다(실제 12.5% → 표시 6.7%).
# ═══════════════════════════════════════════════════════════════════════════
def test_retry_chain_is_one_call_not_two():
    """★★★ 한 번의 호출이 재시도로 두 줄을 남겼다고 «두 번 호출» 이 되어서는 안 된다."""
    recs = [
        _rec(call_id="c1", ok=False, retry_count=0, tier="pro_router"),
        _rec(call_id="c1", ok=False, retry_count=1, tier="flash_router"),
        _rec(call_id="c2", ok=True, retry_count=0),
    ]
    a = ao.aggregate_by_agent(recs)["agents"][0]
    assert a["calls"] == 2, "재시도 줄이 별도 호출로 세어졌다"
    assert a["failed"] == 1 and a["ok"] == 1
    assert a["success_rate"] == 0.5, "줄로 세면 33% 가 나온다 — 그것이 이 결함이었다"
    assert a["log_records"] == 3, "몇 줄이 접혔는지는 남아야 한다"


def test_call_that_survived_a_retry_is_a_success_not_a_failure():
    """★★★ `retry_count==0` 만 세는 우회가 틀리는 이유.

    ⚠️ 게이트웨이는 성공 즉시 반환한다. retry1 에서 살아난 호출은 **성공한 호출 1건**이지
      「1실패 + 1성공」이 아니다. 머리 기록만 보면 이 호출은 영영 실패로 남는다
      (실제 로그에 5건 있었다)."""
    recs = [
        _rec(call_id="c1", ok=False, retry_count=0, tier="pro_router"),
        _rec(call_id="c1", ok=True, retry_count=1, tier="flash_router"),
    ]
    a = ao.aggregate_by_agent(recs)["agents"][0]
    assert a["calls"] == 1 and a["ok"] == 1 and a["failed"] == 0
    assert a["success_rate"] == 1.0


def test_retry_cost_is_summed_not_collapsed():
    """⚠️ 콜 수를 1로 접었다고 **비용까지 1회분으로 접으면** 이번엔 비용이 거짓이 된다.

    재시도는 실제로 돈을 썼다. 호출 수와 비용은 접는 규칙이 다르다."""
    recs = [
        _rec(call_id="c1", ok=False, retry_count=0, cost_estimate_usd=0.2,
             input_tokens=100, output_tokens=10),
        _rec(call_id="c1", ok=True, retry_count=1, cost_estimate_usd=0.3,
             input_tokens=100, output_tokens=10),
    ]
    a = ao.aggregate_by_agent(recs)["agents"][0]
    assert a["calls"] == 1
    assert a["cost_usd"] == 0.5, "재시도가 쓴 비용이 사라졌다"
    assert a["input_tokens"] == 200 and a["output_tokens"] == 20


def test_legacy_records_without_call_id_are_not_guessed():
    """★★ 과거 기록은 **묶지 않는다** — 순서로 추측하면 동시 실행 교차에서 깨진다(실측 11건).

    대신 몇 건이 그런지를 드러내고, 그 성공률이 «하한» 임을 문장으로 말한다."""
    recs = [_rec(ok=False, retry_count=0), _rec(ok=False, retry_count=1)]
    agg = ao.aggregate_by_agent(recs)
    assert agg["coverage"]["records_without_call_id"] == 2
    assert agg["coverage"]["uncollapsed_retry_records"] == 1
    assert "하한" in agg["coverage"]["note"]


def test_no_retry_noise_when_nothing_was_retried():
    """★ `call_id` 가 없다는 사실 자체는 경고가 아니다 — 재시도가 없으면 왜곡도 없다.

    ⚠️ 늘 켜져 있는 경고는 꺼져 있는 것과 같다(`test_full_coverage_says_nothing_alarming`)."""
    agg = ao.aggregate_by_agent([_rec(), _rec(agent="B")])
    assert agg["coverage"]["records_without_call_id"] == 2
    assert agg["coverage"]["uncollapsed_retry_records"] == 0
    assert agg["coverage"]["note"] == "", "왜곡이 없는데 경고가 붙었다"


# ═══════════════════════════════════════════════════════════════════════════
# ⑥ [2026-08-07] 시간 축이 없으면 **고쳐진 사고가 현재 상태로 보고된다**
#
# 두 번째 겹. 실패 40건은 전부 2026-07-29 11:43~12:03 의 단일 실행이었고 원인은 같은 날
# 12:18 에 이미 고쳐졌다(커밋 2334d1572). 직후 실행은 48/48 성공. 그런데 9일 뒤 화면은
# 그 20분을 «현재» 로 보여줬다. 창이 없으면 대시보드는 **사고를 상태로 바꿔 놓는다.**
# ═══════════════════════════════════════════════════════════════════════════
def test_window_excludes_old_records_but_says_so():
    """★★ 자른 것을 «없는 것»으로 만들지 않는다 — 몇 건을 잘랐는지 응답에 남긴다."""
    recs = [_rec(ts="2026-07-29T12:00:00", ok=False),
            _rec(ts="2026-08-06T09:00:00", ok=True)]
    agg = ao.aggregate_by_agent(recs, since="2026-08-01")
    assert agg["agents"][0]["calls"] == 1
    assert agg["agents"][0]["success_rate"] == 1.0
    assert agg["window"]["records_outside_window"] == 1
    assert "창 밖 1건" in agg["window"]["note"]


def test_no_window_says_old_incidents_are_still_counted():
    """전 기간 집계라면 **그 사실이 문장으로** 나와야 한다 — 침묵하면 «최근» 으로 읽힌다."""
    note = ao.aggregate_by_agent([_rec()])["window"]["note"]
    assert "전 기간" in note and "고쳐진" in note


def test_empty_window_is_not_total_failure():
    """★★★ 창 안에 기록이 없는 것은 «전부 실패» 가 아니라 «호출이 없었다» 이다.

    ⚠️ 이 둘을 구분하지 않으면 조용한 시스템이 고장난 시스템처럼 보인다."""
    agg = ao.aggregate_by_agent([_rec(ts="2026-07-01T00:00:00")], since="2026-08-01")
    assert agg["agents"] == []
    assert "호출이 없었다" in agg["window"]["note"]
    assert agg["window"]["records_outside_window"] == 1


def test_records_without_ts_are_not_silently_dropped():
    """⚠️ 창을 못 재는 기록을 버리면 「창 밖 N건」에도 안 잡혀 영영 사라진다."""
    agg = ao.aggregate_by_agent([_rec()], since="2026-08-01")
    assert agg["agents"][0]["calls"] == 1


# ── ⑦ 실패가 «한 번의 사고» 인지 «지속» 인지 구분한다 ───────────────────────
def test_single_run_failures_are_labelled_as_one_incident():
    """★★★ 표본이 충분하다는 것이 «지속되는 문제» 를 뜻하지는 않는다.

    Master_PMO 는 30줄이라 표본이 충분해 보였고 우연도 아니었다. 그런데 실패는 전부 한 날
    한 실행이었고 원인은 그날 안에 고쳐진 결함 하나였다. 「표본이 크니 진짜다」가 조사를
    9일 늦췄다 — 그 구분을 이제 집계가 직접 말한다."""
    recs = [_rec(agent="P", ok=False, ts="2026-07-29T12:0%d:00" % i,
                 project_id="canary2") for i in range(6)]
    agg = ao.aggregate_by_agent(recs)
    conc = agg["agents"][0]["failure_concentration"]
    assert conc["single_run"] is True
    assert conc["top_project"] == "canary2"
    assert "한 번의 사고" in conc["note"]
    assert ao.failing_agents(agg)[0]["single_run"] is True


def test_persistent_failures_are_not_labelled_single_run():
    """반대로 여러 날에 걸친 실패는 **단일 사고로 치부되면 안 된다** — 그게 진짜 문제다."""
    recs = [_rec(agent="P", ok=False, ts=f"2026-08-0{i}T09:00:00",
                 project_id=f"proj{i}") for i in range(1, 6)]
    conc = ao.aggregate_by_agent(recs)["agents"][0]["failure_concentration"]
    assert conc["single_run"] is False
    assert conc["distinct_days"] == 5


def test_persistent_failures_rank_above_one_off_incidents():
    """★ 지속되는 실패가 목록 **위**에 와야 한다 — 단일 사고가 위를 차지하면 진짜를 가린다."""
    recs = ([_rec(agent="ONE_OFF", ok=False, ts="2026-07-29T12:00:00", project_id="c2")
             for _ in range(9)]
            + [_rec(agent="ALWAYS", ok=False, ts="2026-08-0%dT09:00:00" % i,
                    project_id="p%d" % i) for i in range(1, 7)])
    rows = ao.failing_agents(ao.aggregate_by_agent(recs))
    assert [r["agent"] for r in rows][0] == "ALWAYS", "단일 사고가 지속 실패를 가렸다"


def test_no_concentration_field_when_nothing_failed():
    """실패가 없으면 «집중도» 는 `None` 이다 — 빈 dict 를 두면 화면이 0% 를 그린다."""
    assert ao.aggregate_by_agent([_rec()])["agents"][0]["failure_concentration"] is None
