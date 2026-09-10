import copy

import pytest

from core import enterprise_scenario_decision as esd


def _scenario():
    return {"scenario_id": "ews-1", "name": "원료 수급 대응",
            "purpose": "조달 지연의 전사 영향 검토"}


def _composition():
    departments = []
    for role, segment in (("procurement", "arrival"), ("production", "shortage"),
                          ("sales", "revenue")):
        departments.append({"department_role": role, "segment_ref": segment,
                            "values": {segment: {"row-1": 1}},
                            "result_fingerprint": f"fp-{role}"})
    return {
        "status": "READY", "scenario_id": "ews-1", "as_of": "2026-06-01T00:00:00Z",
        "composition_fingerprint": "composition-fp", "baseline_id": "bl-1",
        "baseline_fingerprint": "baseline-fp", "department_results": departments,
        "used_snapshots": {"SLS-01": "ds-sales", "FIN-01": "ds-cost"},
        "financial_impact": {
            "status": "COMPLETE", "result_fingerprint": "financial-fp",
            "model_version": "financial-v1", "bridge_fingerprint": "bridge-fp",
            "reporting_currency": "KRW", "affected_sales_lines": 1,
            "affected_account_names": ["제품매출", "매출채권"],
            "summary": {"inventory_in_transit_krw": 10,
                        "revenue_timing_exposure_krw": 20,
                        "material_conversion_margin_timing_exposure_krw": 12,
                        "cash_receipts_timing_exposure_krw": 20},
            "period_impacts": [{"period": "2026-06", "revenue_delta_krw": -20,
                                "material_conversion_margin_delta_krw": -12,
                                "cash_receipts_delta_krw": 0}],
        },
    }


def test_전사_재무결과를_같은_지문의_의사결정_근거로_만든다():
    got = esd.build(scenario=_scenario(), composition=_composition(),
                    question="긴급 조달안을 실행할 것인가?")
    assert got["evidence"]["composition_fingerprint"] == "composition-fp"
    assert got["evidence"]["financial_result_fingerprint"] == "financial-fp"
    assert got["evidence"]["baseline_fingerprint"] == "baseline-fp"
    assert got["package"]["financial_impact"]["summary"][
        "cash_receipts_timing_exposure_krw"] == 20
    assert got["package"]["options"]["period_impacts"][0]["period"] == "2026-06"
    assert got["package"]["dept_changes"][0]["department_role"] == "원료 구매·도입"
    assert "MDM-07" not in str(got["package"])
    assert "fp-procurement" not in str(got["package"])


@pytest.mark.parametrize("field", ["composition_fingerprint", "baseline_id",
                                     "baseline_fingerprint"])
def test_조합과_기준선_결속이_비면_안건을_만들지_않는다(field):
    composition = _composition()
    composition[field] = ""
    with pytest.raises(esd.EnterpriseScenarioDecisionError):
        esd.build(scenario=_scenario(), composition=composition, question="결정할 것인가?")


def test_재무결과가_막혔으면_숫자_안건을_만들지_않는다():
    composition = _composition()
    composition["financial_impact"] = {
        "status": "BLOCKED", "reason_code": "FINANCIAL_DATA_REQUIRED"}
    with pytest.raises(esd.EnterpriseScenarioDecisionError, match="완료"):
        esd.build(scenario=_scenario(), composition=composition, question="결정할 것인가?")


def test_기간표나_세부서_결속이_빠지면_완성된_척하지_않는다():
    for mutate in (lambda row: row["financial_impact"].update(period_impacts=[]),
                   lambda row: row.update(department_results=row["department_results"][:2])):
        composition = copy.deepcopy(_composition())
        mutate(composition)
        with pytest.raises(esd.EnterpriseScenarioDecisionError):
            esd.build(scenario=_scenario(), composition=composition,
                      question="결정할 것인가?")
