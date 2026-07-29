"""[M4] Backtest — **과거 기간으로 모델을 검증한다** (§11.5 검증 · §17.3 파일럿 성공 기준).

## 무엇을 하는가

"작년 이맘때 이 모델로 계획을 세웠다면, 실제와 얼마나 달랐을까?"

과거 기간의 **계획(또는 시나리오)** 과 **실적**을 나란히 놓고 오차를 잰다. 그래야
"이 모델을 믿고 내년 계획을 세워도 되는가"에 답할 수 있다.

## 이 모듈이 가장 조심하는 것 — **미래 정보 누설(look-ahead bias)**

Backtest 의 고전적 실패는 **결과를 알고 나서 만든 가정으로 과거를 맞히는 것**이다.
그렇게 하면 오차가 0 에 가깝게 나오고, 사람들은 모델이 훌륭하다고 믿는다. 그리고
실제 미래에 쓰면 완전히 빗나간다.

그래서:

- 시나리오 가정이 **대상 기간보다 나중에 만들어졌으면 경고**한다(`created_at` 비교).
  차단하지 않는 이유는 초기 도입에서 모든 가정이 사후에 입력되기 때문이다 —
  대신 **그 사실을 결과에 못박아** 오차를 액면 그대로 믿지 않게 한다.
- 실적이 없는 기간은 **계산하지 않는다**(0 으로 채우지 않는다).

## 오차를 어떻게 재는가

| 지표 | 뜻 | 왜 |
|---|---|---|
| `mape` | 평균 절대 백분율 오차 | 규모가 다른 계정을 함께 볼 수 있다 |
| `bias` | 평균 부호 오차 | **한쪽으로 치우쳤는지** — 늘 과대추정하는 모델은 절대오차가 작아도 위험하다 |
| `worst` | 최악 계정 | 평균이 좋아도 한 계정이 크게 틀리면 그 계획은 못 쓴다 |

⚠️ **`mape` 하나만 보면 안 된다.** 매출을 늘 10% 과대추정하는 모델과, 어떤 해는 +10%
어떤 해는 −10% 인 모델은 `mape` 가 같지만 **완전히 다른 문제**다. 앞의 것은 보정하면 되고
뒤의 것은 못 믿는다. 그래서 `bias` 를 함께 낸다.
"""
from typing import Any, Dict, List, Optional

from core.planning_engine import ENGINE_VERSION, compute_pl, run_scenario
from core.planning_model import ACTUAL, PLAN, PlanningError, planning_store


def _by_account(facts: List[Dict[str, Any]]) -> Dict[str, float]:
    return {f["account_code"]: float(f["amount"]) for f in facts}


def _error_metrics(predicted: Dict[str, float],
                   actual: Dict[str, float]) -> Dict[str, Any]:
    """오차 지표. **실적이 0 인 계정은 백분율에서 제외**한다(0 으로 나눌 수 없다).

    제외한 사실은 `excluded_zero_actual` 로 남긴다 — 조용히 빼면 MAPE 가 실제보다 좋아 보인다."""
    rows, ape, signed = [], [], []
    excluded_zero: List[str] = []
    only_predicted: List[str] = []
    only_actual: List[str] = []

    for code in sorted(set(predicted) | set(actual)):
        p, a = predicted.get(code), actual.get(code)
        if p is None:
            only_actual.append(code)
            continue
        if a is None:
            only_predicted.append(code)
            continue
        err = p - a
        row = {"account_code": code, "predicted": round(p, 4), "actual": round(a, 4),
               "error": round(err, 4)}
        if a == 0:
            excluded_zero.append(code)
            row["pct_error"] = None
        else:
            pct = err / abs(a) * 100.0
            row["pct_error"] = round(pct, 2)
            ape.append(abs(pct))
            signed.append(pct)
        rows.append(row)

    worst = max((r for r in rows if r.get("pct_error") is not None),
                key=lambda r: abs(r["pct_error"]), default=None)
    return {
        "by_account": rows,
        "mape": round(sum(ape) / len(ape), 2) if ape else None,
        # ★ 편향 — 늘 과대추정하는 모델은 절대오차가 작아도 위험하다.
        "bias": round(sum(signed) / len(signed), 2) if signed else None,
        "worst": worst,
        "excluded_zero_actual": excluded_zero,
        "only_predicted": only_predicted,   # 계획엔 있는데 실적이 없는 계정
        "only_actual": only_actual,         # 실적엔 있는데 계획이 없는 계정
        "measured_accounts": len(ape),
    }


def backtest_plan(org_id: str, period: str) -> Dict[str, Any]:
    """그 기간의 **계획 vs 실적** 오차. 모델이 아니라 계획의 정확도를 잰다."""
    plan = planning_store.list_facts(org_id=org_id, period=period, value_kind=PLAN)
    actual = planning_store.list_facts(org_id=org_id, period=period, value_kind=ACTUAL)
    if not plan or not actual:
        return {
            "org_id": org_id, "period": period, "measurable": False,
            "reason": ("계획이 없습니다" if not plan else "실적이 없습니다"),
            "note": ("한쪽이 비어 있어 오차를 재지 않았습니다 — 없는 값을 0 으로 두면 "
                     "오차 100% 로 잘못 읽힙니다."),
            "engine_version": ENGINE_VERSION,
        }
    m = _error_metrics(_by_account(plan), _by_account(actual))
    return {
        "org_id": org_id, "period": period, "measurable": True,
        "kind": "plan_vs_actual",
        "plan_pl": compute_pl(plan), "actual_pl": compute_pl(actual),
        **m,
        "engine_version": ENGINE_VERSION,
    }


def backtest_scenario(scenario_id: str, org_id: str, period: str,
                      baseline_kind: str = PLAN) -> Dict[str, Any]:
    """시나리오를 **과거 기간에 돌려** 실적과 비교한다.

    ⚠️ 가정이 대상 기간보다 나중에 만들어졌으면 **미래 정보 누설**일 수 있다.
      차단하지 않고 경고한다 — 초기 도입에서는 모든 가정이 사후 입력이기 때문이다.
      대신 그 사실을 결과에 못박아 오차를 액면 그대로 믿지 않게 한다."""
    actual = planning_store.list_facts(org_id=org_id, period=period, value_kind=ACTUAL)
    if not actual:
        return {"org_id": org_id, "period": period, "scenario_id": scenario_id,
                "measurable": False, "reason": "실적이 없습니다",
                "note": "실적 없이 backtest 하면 무엇과 비교했는지 알 수 없습니다.",
                "engine_version": ENGINE_VERSION}

    run = run_scenario(scenario_id, org_id, period, baseline_kind)
    predicted = {f["account_code"]: f["amount"] for f in
                 _applied_facts(scenario_id, org_id, period, baseline_kind)}
    m = _error_metrics(predicted, _by_account(actual))

    warnings = list(run.get("driver_warnings") or [])
    if run.get("unapplied_assumptions"):
        warnings.append(f"적용되지 않은 가정 {len(run['unapplied_assumptions'])}건 — "
                        f"이 결과는 의도한 시나리오가 아닙니다.")
    leak = _lookahead_warning(scenario_id, period)
    if leak:
        warnings.append(leak)

    return {
        "org_id": org_id, "period": period, "scenario_id": scenario_id,
        "measurable": True, "kind": "scenario_vs_actual",
        "run_id": run["run_id"], "input_hash": run["input_hash"],
        "scenario_pl": run["result"], "actual_pl": compute_pl(actual),
        **m,
        "warnings": warnings,
        "lookahead_risk": bool(leak),
        "engine_version": ENGINE_VERSION,
    }


def _applied_facts(scenario_id: str, org_id: str, period: str,
                   baseline_kind: str) -> List[Dict[str, Any]]:
    """시나리오를 적용한 사실 목록(엔진과 같은 경로를 쓴다 — 두 곳에서 계산하면 어긋난다)."""
    from core.planning_drivers import expand_assumptions
    from core.planning_engine import apply_assumptions

    conn = planning_store._connect()
    try:
        assumptions = [dict(r) for r in conn.execute(
            "SELECT * FROM scenario_assumptions WHERE scenario_id=? ORDER BY assumption_id",
            (scenario_id,))]
    finally:
        conn.close()
    baseline = planning_store.list_facts(org_id=org_id, period=period, value_kind=baseline_kind)
    expanded, _ = expand_assumptions(assumptions)
    applied, _ = apply_assumptions(baseline, expanded)
    return applied


def _lookahead_warning(scenario_id: str, period: str) -> str:
    """가정이 대상 기간 **이후**에 만들어졌는지 본다(미래 정보 누설 신호).

    ★ Backtest 의 고전적 실패는 **결과를 알고 나서 만든 가정으로 과거를 맞히는 것**이다.
      그러면 오차가 0 에 가깝게 나오고 사람들은 모델을 신뢰하게 된다 — 그리고 실제 미래에
      쓰면 완전히 빗나간다."""
    conn = planning_store._connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT created_at FROM scenario_assumptions WHERE scenario_id=?", (scenario_id,))]
    finally:
        conn.close()
    if not rows:
        return ""
    # period 는 'YYYY' 또는 'YYYY-MM'. 그 기간의 끝을 넘겨 만들어진 가정을 센다.
    year = (period or "")[:4]
    if not year.isdigit():
        return ""
    late = [r for r in rows if (r.get("created_at") or "")[:4] > year]
    if not late:
        return ""
    return (f"⚠️ 미래 정보 누설 가능성: 가정 {len(late)}/{len(rows)}건이 대상 기간({period}) "
            f"이후에 작성되었습니다. 결과를 알고 만든 가정이라면 이 오차는 실제 예측력이 "
            f"아닙니다.")


def backtest_series(org_id: str, periods: List[str]) -> Dict[str, Any]:
    """여러 기간을 연속으로 검증한다 — **한 해만 맞힌 것은 우연일 수 있다.**

    편향(`bias`)이 여러 기간에 걸쳐 같은 방향이면 그것은 우연이 아니라 **모델의 습관**이다."""
    results = [backtest_plan(org_id, p) for p in periods]
    usable = [r for r in results if r.get("measurable") and r.get("mape") is not None]
    if not usable:
        return {"org_id": org_id, "periods": periods, "measurable": False,
                "reason": "오차를 잴 수 있는 기간이 없습니다.",
                "results": results, "engine_version": ENGINE_VERSION}
    biases = [r["bias"] for r in usable if r.get("bias") is not None]
    same_direction = bool(biases) and (all(b > 0 for b in biases) or all(b < 0 for b in biases))
    return {
        "org_id": org_id, "periods": periods, "measurable": True,
        "avg_mape": round(sum(r["mape"] for r in usable) / len(usable), 2),
        "avg_bias": round(sum(biases) / len(biases), 2) if biases else None,
        # ★ 같은 방향의 편향이 반복되면 우연이 아니라 습관이다 — 보정 대상이다.
        "systematic_bias": same_direction,
        "note": ("편향이 여러 기간에 걸쳐 같은 방향이면 모델이 한쪽으로 치우쳐 있습니다 — "
                 "절대오차(MAPE)가 작아도 그대로 쓰면 안 됩니다."
                 if same_direction else
                 "편향의 방향이 기간마다 달라 계통 오차로 보기는 어렵습니다."),
        "results": results,
        "engine_version": ENGINE_VERSION,
    }
