"""카나리 판독기 검증 — **판정 도구가 오판하면 잘못된 근거로 Close 된다.**

1차 카나리에서 "완주했으니 텔레메트리도 정합하다"는 보고가 올라왔고, 실제로는 품질 게이트
계측이 한 건도 없었다. 판정을 코드로 고정한 이유가 그것이므로, 그 코드가 맞는지도 잠근다.

특히 지키는 것: **비어 있는 계측을 '충족'으로 읽지 않는다.** 없는 것을 0 으로 채우면
"실패 0건"처럼 보여 오히려 건강해 보인다 — 이 저장소에서 반복된 오독 유형이다.
"""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "canary_report", os.path.join(ROOT, "scripts", "canary_report.py"))
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


def _call(**kw):
    base = {"stage": "QA", "agent": "QA", "attempts": ["m1"], "input_tokens": 100,
            "output_tokens": 50, "duration_s": 1.0, "cost_basis": "paid",
            "cost_estimate_usd": 0.01, "context_chars": 5000, "context_budget": 20000,
            "context_clipped": False,
            "context_blocks": {"master_data": 3000, "tech_spec": 2000},
            "knowledge_packs": ["core-m3"], "knowledge_hits": [{"pack_id": "core-m3"}]}
    base.update(kw)
    return base


# ── ⑴ 모델·폴백 ──────────────────────────────────────────────────────────────
def test_unidentified_calls_are_not_counted_as_met():
    """★ 단계도 주체도 모르는 호출이 있으면 충족이 아니다(1차 카나리 36% 문제)."""
    v, _ = cr.measure_1_models_and_fallbacks([_call(stage="", agent="")])
    assert v == cr.NO


def test_fallback_without_reason_is_partial_not_met():
    """폴백이 났는데 사유가 없으면 '왜 넘어갔는지'를 답할 수 없다 — 충족 아님."""
    v, _ = cr.measure_1_models_and_fallbacks(
        [_call(attempts=["m1", "m2"], fallback_errors=[])])
    assert v == cr.PARTIAL


def test_fallback_with_reason_is_met():
    v, lines = cr.measure_1_models_and_fallbacks(
        [_call(attempts=["m1", "m2"], fallback_errors=[{"model": "m1", "error": "429"}])])
    assert v == cr.OK
    assert any("429" in l for l in lines)


# ── ⑶ 컨텍스트 ───────────────────────────────────────────────────────────────
def test_missing_context_measurement_is_not_met():
    """★★ 1차 카나리가 걸린 지점 — 계측이 없으면 D-010 판정이 불가능하다."""
    v, lines = cr.measure_3_context([_call(context_chars=None)])
    assert v == cr.NO
    assert "D-010" in lines[0]


def test_grounding_absence_is_surfaced():
    """★ 지식팩 참조가 0 이면 그라운딩 없이 돈 것이다 — 조용히 넘기지 않는다."""
    v, lines = cr.measure_3_context([_call(knowledge_packs=[], knowledge_hits=[])])
    assert v == cr.PARTIAL
    assert any("그라운딩 없이" in l for l in lines)


def test_tech_spec_starvation_is_flagged():
    """★★ 기준정보만 있고 기술 명세가 0 이면 2026-07-29 회귀 유형이다."""
    _, lines = cr.measure_3_context(
        [_call(context_blocks={"master_data": 9000, "tech_spec": 0})])
    assert any("밀려났을 가능성" in l for l in lines)


def test_clipping_is_flagged():
    _, lines = cr.measure_3_context([_call(context_clipped=True)])
    assert any("절단" in l for l in lines)


# ── ⑷⑸ 게이트·재작업 ────────────────────────────────────────────────────────
def test_empty_quality_log_is_not_met():
    """★★ 게이트 기록이 없는 것을 '실패 0건(건강함)'으로 읽으면 안 된다."""
    v, _ = cr.measure_4_rework([], {"developer_retry_count": 0, "supervisor_hops": 1})
    assert v == cr.NO


def test_gates_without_measurement_are_partial_even_if_all_done():
    """WBS 가 전부 DONE 이어도 **어떻게 통과했는지** 모르면 부분 충족이다."""
    v, lines = cr.measure_5_gates([], {"build_status": "success", "qa_verdict": "PASS"},
                                  [{"status": "DONE"}])
    assert v == cr.PARTIAL
    assert any("어떻게 통과했는지" in l for l in lines)


def test_full_measurement_is_met():
    outcomes = [{"gate_name": "QA", "pass_fail": "PASS", "root_cause": "unclassified"}]
    v, _ = cr.measure_5_gates(outcomes, {"build_status": "success", "qa_verdict": "PASS"},
                              [{"status": "DONE"}])
    assert v == cr.OK


def test_unclassified_failures_are_pointed_at_a_human():
    _, lines = cr.measure_4_rework(
        [{"pass_fail": "FAIL", "root_cause": "unclassified"}], {})
    assert any("사후 분류" in l for l in lines)


# ── 비용: 미산정을 0 으로 위장하지 않는다 ────────────────────────────────────
def test_unpriced_calls_make_the_total_a_lower_bound():
    v, lines = cr.measure_2_cost([_call(cost_basis="unpriced", cost_estimate_usd=None)])
    assert any("≥" in l for l in lines), "미산정이 있으면 합계는 하한이다"
