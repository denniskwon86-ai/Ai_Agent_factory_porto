"""전사 업무 시나리오의 봉인된 재무 결과를 G5 Decision Package로 투영한다.

숫자를 다시 계산하지 않는다. APP-07이 반환한 COMPLETE 결과와 그 결과를 만든
조합·기준선·부서 결과·인증판 지문만 하나의 근거 봉투로 묶는다. LLM 호출 0건.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping


DEPARTMENT_LABELS = {
    "procurement": "원료 구매·도입",
    "production": "재고·생산계획",
    "sales": "판매·매출",
}
METRIC_LABELS = {
    "in_transit_quantity": "운송 중 수량",
    "shortage_quantity": "자재 부족량",
    "producible_quantity": "생산 가능량",
    "revenue_shift_days": "매출 인식 이동일",
}
DATASET_LABELS = {
    "MDM-07": "회계 계정·원가센터",
    "EXT-01": "대외 환율 지표",
    "PRC-02": "구매 주문행",
    "SLS-01": "판매 주문행",
    "FIN-01": "표준·실제 원가",
    "FIN-02": "채권·채무 일정",
    "LOG-02": "선적",
    "LOG-03": "운송 이력",
    "INV-01": "재고 현황",
    "MFG-01": "생산 계획",
    "MDM-05": "자재 소요 기준",
}


class EnterpriseScenarioDecisionError(ValueError):
    """전사 시나리오 결과가 의사결정 근거 계약을 충족하지 못했다."""


def _required(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise EnterpriseScenarioDecisionError(f"{label}이(가) 비어 있습니다.")
    return text


def _money(value: Any) -> str:
    try:
        return f"{float(value):,.0f}원"
    except (TypeError, ValueError) as exc:
        raise EnterpriseScenarioDecisionError(
            "재무 영향 요약에 숫자가 아닌 값이 있습니다.") from exc


def build(*, scenario: Mapping[str, Any], composition: Mapping[str, Any],
          question: str) -> Dict[str, Dict[str, Any]]:
    """같은 결과를 Decision Center와 발간기가 읽는 package/evidence로 만든다."""
    scenario_id = _required(scenario.get("scenario_id"), "전사 시나리오")
    if scenario_id != _required(composition.get("scenario_id"), "조합 시나리오"):
        raise EnterpriseScenarioDecisionError(
            "전사 시나리오와 조합 결과의 식별자가 다릅니다.")
    if str(composition.get("status") or "") != "READY":
        raise EnterpriseScenarioDecisionError(
            "세 부서 결과가 모두 결합된 전사 조합만 안건으로 만들 수 있습니다.")
    decision_question = _required(question, "결정 문장")
    composition_fp = _required(
        composition.get("composition_fingerprint"), "전사 조합 지문")
    baseline_id = _required(composition.get("baseline_id"), "기준선")
    baseline_fp = _required(
        composition.get("baseline_fingerprint"), "기준선 지문")
    as_of = _required(composition.get("as_of"), "기준시점")
    snapshots = dict(composition.get("used_snapshots") or {})
    if not snapshots or any(not str(value or "").strip() for value in snapshots.values()):
        raise EnterpriseScenarioDecisionError("전사 조합의 인증판 결속이 비어 있습니다.")

    financial = composition.get("financial_impact")
    if not isinstance(financial, Mapping) or financial.get("status") != "COMPLETE":
        raise EnterpriseScenarioDecisionError(
            "재무 영향 계산이 완료된 전사 조합만 안건으로 만들 수 있습니다.")
    financial_fp = _required(financial.get("result_fingerprint"), "재무 결과 지문")
    model_version = _required(financial.get("model_version"), "재무 모델 판")
    bridge_fp = _required(financial.get("bridge_fingerprint"), "업무-회계 변환 계약 지문")
    summary = dict(financial.get("summary") or {})
    required_summary = (
        "inventory_in_transit_krw", "revenue_timing_exposure_krw",
        "material_conversion_margin_timing_exposure_krw",
        "cash_receipts_timing_exposure_krw",
    )
    if any(key not in summary for key in required_summary):
        raise EnterpriseScenarioDecisionError("전사 재무 영향 요약이 완전하지 않습니다.")
    periods = list(financial.get("period_impacts") or [])
    if not periods:
        raise EnterpriseScenarioDecisionError(
            "기간별 재무 영향이 없어 안건의 비교표를 만들 수 없습니다.")

    departments = list(composition.get("department_results") or [])
    if len(departments) != 3:
        raise EnterpriseScenarioDecisionError("세 부서 결과 지문을 모두 확인할 수 없습니다.")
    department_fps = {
        _required(row.get("department_role"), "부서 역할"):
        _required(row.get("result_fingerprint"), "부서 결과 지문")
        for row in departments if isinstance(row, Mapping)
    }
    if len(department_fps) != 3:
        raise EnterpriseScenarioDecisionError("세 부서 결과 지문이 서로 구분되지 않습니다.")

    name = _required(scenario.get("name"), "전사 시나리오 이름")
    purpose = _required(scenario.get("purpose"), "전사 시나리오 목적")
    brief = [
        f"전사 시나리오: {name}",
        f"검토 목적: {purpose}",
        f"운송 중 재고 노출액: {_money(summary['inventory_in_transit_krw'])}",
        f"매출 인식 이동 규모: {_money(summary['revenue_timing_exposure_krw'])}",
        ("매출-재료·가공비 기여액 이동 규모: "
         + _money(summary["material_conversion_margin_timing_exposure_krw"])),
        f"현금회수 이동 규모: {_money(summary['cash_receipts_timing_exposure_krw'])}",
    ]
    department_views = []
    for row in departments:
        values = row.get("values") or {}
        department_views.append({
            "department_role": DEPARTMENT_LABELS.get(
                str(row["department_role"]), str(row["department_role"])),
            "result_metrics": [
                METRIC_LABELS.get(str(metric), str(metric)) for metric in values],
            "affected_items": sum(
                len(series) if isinstance(series, Mapping) else 0
                for series in values.values()),
        })
    package = {
        "executive_brief": brief,
        "problem": purpose,
        "why_simulated": "구매·생산·판매 부서 결과를 같은 기준선과 인증판으로 결합했습니다.",
        "asks": {"decision_question": decision_question},
        "baseline": {
            "baseline_id": baseline_id,
            "baseline_fingerprint": baseline_fp,
            "as_of": as_of,
            "comparison_basis": "봉인된 매출 인식 기준일과 채권 만기 대비 시나리오 이동",
        },
        "options": {
            "scenario_name": name,
            "period_impacts": periods,
            "department_results": department_views,
        },
        "financial_impact": {
            "reporting_currency": financial.get("reporting_currency"),
            "summary": summary,
            "period_impacts": periods,
            "affected_sales_lines": financial.get("affected_sales_lines"),
            "affected_account_names": list(
                financial.get("affected_account_names") or []),
        },
        "dept_changes": department_views,
        "resource_impact": summary,
        "dependencies": {
            "departments": sorted(department_fps),
            "certified_datasets": [
                DATASET_LABELS.get(key, "업무 데이터") for key in sorted(snapshots)],
        },
    }
    evidence = {
        "source_type": "ENTERPRISE_WORK_SCENARIO",
        "scenario_id": scenario_id,
        "composition_fingerprint": composition_fp,
        "financial_result_fingerprint": financial_fp,
        "financial_model_version": model_version,
        "financial_bridge_fingerprint": bridge_fp,
        "baseline_id": baseline_id,
        "baseline_fingerprint": baseline_fp,
        "as_of": as_of,
        "department_result_fingerprints": dict(sorted(department_fps.items())),
        "used_snapshots": dict(sorted(snapshots.items())),
    }
    return {"package": package, "evidence": evidence}
