"""[G4 / Wave G] 최소 계산 — **LLM 이 숫자를 만들지 않는다.**

## 이 파일이 지키는 것 넷

★★★ ① **같은 입력이면 같은 결과.** Baseline 지문 + 가정이 같으면 결과가 같아야
  한다(설계 §12.2). 그러지 않으면 「같은 조건에서 왜 다른 답이 나왔나」에 답할 수 없다.

★★★ ② **LLM 이 숫자를 만들지 않는다.** 여기는 산술뿐이다. 문장을 생성하는 코드가
  이 파일에 들어오면, 그 순간 「그럴듯한 숫자」가 보고서에 들어간다.

★★★ ③ **기준선 없이는 계산하지 않는다.** 「최신 데이터로 대충」은 재현할 수 없는
  숫자를 낳고, 그 숫자가 회의에 올라간다.

★★★ ④ **성격을 결과에 달고 다닌다.** 시연 데이터로 만든 결과는 시연 결과다 —
  화면에서 그 표시가 빠지면 실적으로 읽힌다.

## 지금 있는 것 (설계 §11.3 최소)

Driver 셋 · 결과 다섯. 늘리지 않는다 — 채울 데이터가 없는 칸을 만들면 화면이 0을
그리고, 아무도 그것을 고장으로 보지 않는다.
"""
import hashlib
import json
from typing import Any, Dict, List, NamedTuple, Tuple


class CalcError(Exception):
    """계산할 수 없다. **부분 결과를 돌려주지 않는다.**"""


#: ★ Driver — **닫힌 목록.** 이름과 단위를 함께 못 박는다.
#: ⚠️ 단위를 안 적으면 「+10」이 퍼센트인지 절대값인지 두 사람이 다르게 읽는다.
DRIVERS: Tuple[Tuple[str, str, str], ...] = (
    ("fx_rate_pct", "환율", "%"),
    ("lead_time_days", "도입 지연", "일"),
    ("power_price_pct", "전력단가", "%"),
)
DRIVER_KEYS: Tuple[str, ...] = tuple(k for k, _, _ in DRIVERS)

#: ★ 결과 — 닫힌 목록.
OUTPUTS: Tuple[Tuple[str, str, str], ...] = (
    ("production_qty", "생산량", "ton"),
    ("ending_inventory", "기말재고", "ton"),
    ("purchase_payment", "구매지급", "원"),
    ("ending_cash", "기말현금", "원"),
    ("operating_profit", "영업이익", "원"),
)
OUTPUT_KEYS: Tuple[str, ...] = tuple(k for k, _, _ in OUTPUTS)

#: 계산 계약 판. ⚠️ 산식이 바뀌면 **반드시** 올린다 — 같은 판인데 다른 답이 나오면
#: 「동일 입력 동일 결과」 주장이 무너진다.
CALC_VERSION = "1.0.0"


class Result(NamedTuple):
    values: Dict[str, float]
    fingerprint: str
    calc_version: str
    baseline_fingerprint: str
    data_kind: str
    assumptions: Dict[str, float]

    def public(self) -> Dict[str, Any]:
        return {
            "values": dict(self.values),
            "fingerprint": self.fingerprint,
            "calc_version": self.calc_version,
            "baseline_fingerprint": self.baseline_fingerprint,
            "data_kind": self.data_kind,
            "assumptions": dict(self.assumptions),
            "units": {k: u for k, _, u in OUTPUTS},
            "labels": {k: lb for k, lb, _ in OUTPUTS},
        }


def normalize_assumptions(raw: Any) -> Dict[str, float]:
    """가정을 정규화한다. **모르는 Driver 는 던진다.**

    ⚠️ 조용히 무시하면 사용자가 「환율을 올렸는데 결과가 그대로」를 보고, 원인을
      영원히 못 찾는다. 안 준 Driver 는 0(변화 없음)이다."""
    out = {k: 0.0 for k in DRIVER_KEYS}
    for k, v in (raw or {}).items():
        key = str(k).strip()
        if key not in out:
            raise CalcError(
                f"알 수 없는 Driver 입니다: {key or '(없음)'} — "
                f"가능한 것은 {list(DRIVER_KEYS)} 입니다.")
        try:
            out[key] = float(v)
        except (TypeError, ValueError):
            raise CalcError(f"{key}: 숫자가 아닙니다({v!r}).")
    return out


def _fingerprint(baseline_fp: str, assumptions: Dict[str, float]) -> str:
    """계산 지문 = 기준선 + 가정 + 산식 판.

    ★★★ 셋 중 하나라도 다르면 다른 지문이어야 한다 — 그래야 「이 숫자는 무엇으로
      만들었나」에 답할 수 있다.

    ⚠️ **`sort_keys=True` 는 지금 시험으로 관측되지 않는다**(2026-08-19 변이 검사).
      바깥 키는 코드에 박힌 세 개 그대로이고, `assumptions` 는 이미 `sorted()` 로
      쌓기 때문에 꺼도 같은 문자열이 나온다. 그래도 남긴다 — 나중에 키가 하나
      늘거나 `assumptions` 를 다른 곳에서 만들어 넣는 순간, 이것이 없으면 **같은
      입력이 실행마다 다른 지문**을 내기 시작하고 그 고장은 조용하다.
      없는 시험을 지어내 초록으로 덮지 않는다."""
    body = json.dumps({"baseline": baseline_fp, "calc": CALC_VERSION,
                       "assumptions": {k: round(assumptions[k], 6)
                                       for k in sorted(assumptions)}},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _require(base: Dict[str, Any], key: str) -> float:
    """기준값 하나. **없으면 던진다 — 0으로 채우지 않는다.**

    ⚠️⚠️ 0으로 채우면 「데이터가 없다」가 「값이 0이다」가 되고, 그 위에서 만든
      보고서는 완성돼 보인다."""
    if key not in (base or {}):
        raise CalcError(f"기준값 «{key}» 이 없습니다 — 없는 값을 0으로 채우지 않습니다.")
    try:
        return float(base[key])
    except (TypeError, ValueError):
        raise CalcError(f"기준값 «{key}» 이 숫자가 아닙니다({base[key]!r}).")


def simulate(baseline: Any, base_values: Dict[str, Any],
             assumptions: Any = None) -> Result:
    """세 Driver → 다섯 결과. **산술뿐이다.**

    ★ 산식은 단순하고 **설명 가능**해야 한다. 설명할 수 없는 숫자는 회의에서
      「어떻게 나온 겁니까」에 답하지 못하고, 그 순간 신뢰를 잃는다.

    ⚠️ 기준선이 없으면 계산하지 않는다 — 재현할 수 없는 숫자는 만들지 않는다."""
    baseline_fp = str(getattr(baseline, "fingerprint", "") or "")
    if not baseline_fp:
        raise CalcError(
            "기준선 없이 계산하지 않습니다 — 「최신 데이터로 대충」은 재현할 수 없는 "
            "숫자를 낳고, 그 숫자가 회의에 올라갑니다.")

    a = normalize_assumptions(assumptions)
    fx, delay, power = a["fx_rate_pct"], a["lead_time_days"], a["power_price_pct"]

    qty0 = _require(base_values, "production_qty")
    inv0 = _require(base_values, "ending_inventory")
    pay0 = _require(base_values, "purchase_payment")
    cash0 = _require(base_values, "ending_cash")
    profit0 = _require(base_values, "operating_profit")
    power_cost0 = _require(base_values, "power_cost")
    days = _require(base_values, "period_days")
    if days <= 0:
        raise CalcError("기간(period_days)이 0 이하입니다 — 하루당 값을 낼 수 없습니다.")

    #: 도입이 늦으면 그만큼 못 만든다(기간 비례). ★ 음수가 되지 않게 바닥을 둔다 —
    #: 「지연이 기간보다 길다」는 «생산 0» 이지 «음의 생산» 이 아니다.
    lost_ratio = min(max(delay, 0.0) / days, 1.0)
    qty = qty0 * (1.0 - lost_ratio)

    #: 못 만든 만큼 원료가 남는다.
    inventory = inv0 + (qty0 - qty)

    #: 환율이 오르면 수입 원료 대금이 그만큼 오른다.
    payment = pay0 * (1.0 + fx / 100.0)

    #: 전력단가는 원가에만 붙는다(생산량 비례).
    power_cost = power_cost0 * (1.0 + power / 100.0) * (qty / qty0 if qty0 else 0.0)

    #: 이익 = 기준이익 − 늘어난 구매대금 − 늘어난 전력비 − 못 판 물량의 기여
    unit_margin = (profit0 / qty0) if qty0 else 0.0
    profit = (profit0
              - (payment - pay0)
              - (power_cost - power_cost0)
              - unit_margin * (qty0 - qty))

    #: 현금은 대금 증가분만큼 줄고, 이익 변화만큼 따라간다.
    cash = cash0 - (payment - pay0) + (profit - profit0)

    values = {
        "production_qty": round(qty, 6),
        "ending_inventory": round(inventory, 6),
        "purchase_payment": round(payment, 6),
        "ending_cash": round(cash, 6),
        "operating_profit": round(profit, 6),
    }
    #: 목록과 구현이 갈라지지 않게 — 결과 칸이 빠지면 여기서 즉시 깨진다.
    assert set(values) == set(OUTPUT_KEYS)

    return Result(values=values, fingerprint=_fingerprint(baseline_fp, a),
                  calc_version=CALC_VERSION, baseline_fingerprint=baseline_fp,
                  data_kind=str(getattr(baseline, "data_kind", "") or ""),
                  assumptions=a)


def compare(base: Result, scenario: Result) -> List[Dict[str, Any]]:
    """기준 대비 변화. **비율이 아니라 값과 비율을 함께** 준다.

    ⚠️ 비율만 주면 작은 기준값에서 「+300%」 같은 숫자가 나오고, 그것이 회의에서
      실제 규모보다 크게 읽힌다."""
    out = []
    for key, label, unit in OUTPUTS:
        b, s = base.values[key], scenario.values[key]
        out.append({"key": key, "label": label, "unit": unit,
                    "base": b, "scenario": s, "delta": round(s - b, 6),
                    #: ★ 기준이 0이면 비율은 **없다** — 무한대를 0으로 적지 않는다.
                    "delta_pct": (round((s - b) / b * 100.0, 4) if b else None)})
    return out
