"""★★★ [ECM E4 마지막 조각] 외부환경 인텔리전스 → 보드 `FORECAST` 계열.

## 왜 이 연결이 위험한가

외부 지표는 "없으면 아쉬운" 값이 아니라 **경영 보고에 올라가는 값**이다. `external_intelligence`
는 용도별 최소 등급을 지켜 등급 미달이면 `allowed=False, value=None` 을 준다(§12.2). 그 규율을
연결 지점에서 무너뜨리기가 아주 쉽다 — 거부된 값을 0 이나 이전 값으로 채우면 표는 정상으로
보이고, §12.1 이 금지한 "검증 없이 시장 전망값으로 기준 계획을 바꾸는" 상황이 된다.

⚠️ 그리고 그 차이는 화면에서 보이지 않는다. 그래서 이 파일이 지키는 것은 하나다:
  **등급 미달은 값이 아니라 결손이다.**
"""
import pytest

from core.enterprise_context.outlook_series import (DEFAULT_PURPOSE, OutlookError,
                                                    OutlookSeries)


class _FakeEI:
    """외부 인텔리전스 대역 — 실물과 **같은 반환 모양**을 준다(`allowed`/`value`/등급/이유).

    ⚠️ 대역이 실물과 다르면 그 테스트는 실물이 아니라 대역을 검증한다. 키 이름을
      `resolve_value()` 에서 그대로 가져왔다."""
    def __init__(self, table):
        self.table = table
        self.calls = []

    def resolve_value(self, code, purpose="baseline_plan", as_of="", vintage=""):
        self.calls.append({"code": code, "purpose": purpose, "as_of": as_of,
                           "vintage": vintage})
        v = self.table.get(code)
        if v is None:
            return {"indicator_code": code, "allowed": False, "value": None,
                    "reason": "등록되지 않은 지표입니다.",
                    "next_action": "지표를 등록하거나 플레이북에서 시드하십시오."}
        if isinstance(v, dict) and v.get("blocked"):
            return {"indicator_code": code, "allowed": False, "value": None,
                    "required_grade": v.get("required_grade", "gold"),
                    "available_grade": v.get("available_grade", "bronze"),
                    "reason": v.get("reason", "등급이 부족합니다."),
                    "next_action": "승인된 공식 원천을 등록하십시오."}
        if isinstance(v, dict) and v.get("raise"):
            raise RuntimeError("저장소 손상")
        return {"indicator_code": code, "allowed": True, "value": v["value"],
                "unit": v.get("unit", ""), "grade": v.get("grade", "silver"),
                "observed_at": v.get("observed_at", "2026-07-01"),
                "vintage": v.get("vintage", "2026-07"),
                "source_id": v.get("source_id", "src_1"),
                "quality_status": v.get("quality_status", "VALIDATED"),
                "required_grade": "silver"}


def _svc(table):
    return OutlookSeries(intelligence=_FakeEI(table))


# ── 결손 처리 ─────────────────────────────────────────────────────────────
def test_blocked_indicators_are_excluded_not_filled():
    """★★★ **이 파일의 핵심.** 등급 미달 지표는 계열에서 빠지고, 0 으로 채우지 않는다."""
    svc = _svc({
        "ENERGY_PRICE": {"value": 132.5, "grade": "silver"},
        "FX_USD": {"blocked": True, "required_grade": "gold", "available_grade": "bronze",
                   "reason": "'official_report' 용도는 최소 'gold' 등급이 필요합니다."},
    })
    out = svc.build(["ENERGY_PRICE", "FX_USD"])
    assert out["values"] == {"ENERGY_PRICE": 132.5}
    assert "FX_USD" not in out["values"], "등급 미달 값이 계열에 들어갔다"
    assert out["blocked"][0]["indicator_code"] == "FX_USD"
    assert out["blocked"][0]["required_grade"] == "gold"
    assert any("0 으로 채우지 않았습니다" in n for n in out["notes"])


def test_unknown_indicator_is_reported_with_next_action():
    """★★ 없는 지표는 조용히 빠지지 않는다 — 무엇을 해야 하는지까지 올린다."""
    out = _svc({}).build(["NOPE"])
    assert out["values"] == {} and out["excluded"] == 1
    assert "등록되지 않은" in out["blocked"][0]["reason"]
    assert out["blocked"][0]["next_action"]


def test_resolver_crash_becomes_a_blocked_entry_not_silence():
    """★★★ 조회가 깨져도 조용히 빠지면 **"지표가 없다"와 "조회가 깨졌다"가 같아진다.**"""
    out = _svc({"BROKEN": {"raise": True}}).build(["BROKEN"])
    assert out["values"] == {}
    assert "조회 실패" in out["blocked"][0]["reason"]


def test_empty_series_says_do_not_draw_it():
    """★★★ 쓸 수 있는 값이 하나도 없으면 **계열을 세우지 말라고 말한다** —
    빈 계열은 "전망이 0" 으로 읽힌다."""
    out = _svc({}).build(["A", "B"])
    assert out["usable"] == 0
    assert any("전망 계열을 보드에 세우지 마십시오" in n for n in out["notes"])


# ── 근거 ──────────────────────────────────────────────────────────────────
def test_evidence_travels_with_each_value():
    """★★★ 등급·관측시점·vintage·원천이 없으면 보드에서 전망값과 실적이 **같은 숫자로 보인다**
    (§12.2 가 "구분해 표기해야 한다"고 한 이유)."""
    svc = _svc({"ENERGY_PRICE": {"value": 132.5, "grade": "gold",
                                 "observed_at": "2026-07-15", "vintage": "2026-07",
                                 "source_id": "src_kepco", "unit": "원/kWh"}})
    ev = svc.build(["ENERGY_PRICE"])["meta"]["evidence"]["ENERGY_PRICE"]
    assert ev["grade"] == "gold" and ev["vintage"] == "2026-07"
    assert ev["source_id"] == "src_kepco" and ev["unit"] == "원/kWh"


def test_forecast_series_is_never_official():
    """★★ 전망은 공식 수치가 아니다 — 보드가 `official` 로 구분해 그릴 수 있어야 한다."""
    out = _svc({"A": {"value": 1}}).build(["A"])
    assert out["meta"]["official"] is False
    assert any("실적이 아닙니다" in n for n in out["notes"])


# ── 용도·등급 ─────────────────────────────────────────────────────────────
def test_default_purpose_is_scenario_grade():
    """★ 전망 계열의 기본 용도는 시나리오 등급(silver)이다 — 전망에 gold 를 요구하면 실무에서
    계열이 늘 비게 되고, 그러면 아무도 쓰지 않는다."""
    assert DEFAULT_PURPOSE == "scenario"
    svc = OutlookSeries(intelligence=_FakeEI({"A": {"value": 1}}))
    svc.build(["A"])
    assert svc._ei.calls[0]["purpose"] == "scenario"


def test_caller_can_require_official_grade():
    """★★ 경영 보고용 보드는 gold 를 요구할 수 있다 — 용도를 여기서 고정하면 화면마다 다른
    기준이 생긴다."""
    svc = OutlookSeries(intelligence=_FakeEI({"A": {"value": 1}}))
    out = svc.build(["A"], purpose="official_report")
    assert svc._ei.calls[0]["purpose"] == "official_report"
    assert out["meta"]["purpose"] == "official_report"


def test_unknown_purpose_is_refused():
    """★★ 용도를 정하지 않으면 어떤 등급이 필요한지 정해지지 않는다(§12.2)."""
    with pytest.raises(OutlookError, match="purpose"):
        _svc({"A": {"value": 1}}).build(["A"], purpose="whatever")


def test_empty_indicator_list_is_refused():
    """★ 빈 목록으로 계열을 만들려는 호출은 실수다 — 조용히 빈 결과를 주지 않는다."""
    with pytest.raises(OutlookError, match="비어"):
        _svc({}).build([])


def test_vintage_and_as_of_are_passed_through():
    """★★ 과거 계획의 재현 경로 — `vintage` 를 주면 그 시점 발표값을 쓴다."""
    svc = OutlookSeries(intelligence=_FakeEI({"A": {"value": 1}}))
    svc.build(["A"], as_of="2026-06-30", vintage="2026-06")
    assert svc._ei.calls[0]["as_of"] == "2026-06-30"
    assert svc._ei.calls[0]["vintage"] == "2026-06"


# ── 보드 결합 ─────────────────────────────────────────────────────────────
def test_attach_adds_forecast_series_to_board_input():
    """★★ 보드 입력에 계열과 근거가 함께 붙는다."""
    svc = _svc({"ENERGY_PRICE": {"value": 132.5}})
    merged = svc.attach_to_board({"node_id": "n1", "series": {"ACTUAL": {"매출": 10}}},
                                 ["ENERGY_PRICE"])
    assert merged["series"]["FORECAST"] == {"ENERGY_PRICE": 132.5}
    assert merged["meta"]["FORECAST"]["official"] is False
    assert merged["outlook"]["usable"] == 1


def test_attach_does_not_create_an_empty_forecast_series():
    """★★★ 쓸 수 있는 값이 없으면 **계열을 세우지 않는다.** 빈 계열을 세우면 "전망이 0" 으로
    읽힌다 — 결손을 0 으로 채우지 않는 것과 같은 이유다."""
    svc = _svc({"A": {"blocked": True}})
    merged = svc.attach_to_board({"node_id": "n1", "series": {"ACTUAL": {"매출": 10}}}, ["A"])
    assert "FORECAST" not in merged["series"]
    assert merged["outlook"]["excluded"] == 1 and merged["outlook"]["blocked"]


def test_attach_preserves_existing_series():
    """★ 기존 계열을 덮지 않는다(전망을 붙이다 실적을 지우면 안 된다)."""
    svc = _svc({"A": {"value": 1}})
    merged = svc.attach_to_board(
        {"node_id": "n1", "series": {"ACTUAL": {"매출": 10}, "PLAN": {"매출": 12}},
         "meta": {"ACTUAL": {"as_of": "2026-06-30"}}}, ["A"])
    assert merged["series"]["ACTUAL"] == {"매출": 10}
    assert merged["series"]["PLAN"] == {"매출": 12}
    assert merged["meta"]["ACTUAL"]["as_of"] == "2026-06-30"


def test_board_accepts_the_attached_series():
    """★★★ 결합 결과가 **보드가 실제로 받는 모양**이어야 한다 — 여기까지 확인하지 않으면
    "붙였다"고 믿고 화면에서 깨진다(오늘 아침 목록 API 에서 겪은 유형)."""
    from core.enterprise_context.executive_board import build_board
    svc = _svc({"ENERGY_PRICE": {"value": 132.5, "grade": "silver"}})
    merged = svc.attach_to_board({"node_id": "n1", "series": {"ACTUAL": {"ENERGY_PRICE": 120}}},
                                 ["ENERGY_PRICE"])
    b = build_board(merged["node_id"], merged["series"], merged["meta"])
    row = next(r for r in b["rows"] if r["key"] == "ENERGY_PRICE")
    assert row["cells"]["ACTUAL"]["official"] is True
    assert row["cells"]["FORECAST"]["official"] is False
    assert row["cells"]["FORECAST"]["mode_ko"] == "예측"
    assert row["cross_mode_total"] is None
