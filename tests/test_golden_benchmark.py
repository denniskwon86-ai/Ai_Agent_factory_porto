"""core/golden_benchmark.py — 골든 벤치마크 프레임워크 검증.

품질 회귀 방지 프레임워크: 3축 채점(deterministic/llm_judge/human) + 스코어카드 + 골든 회귀비교.
골든 데이터(완주 산출물)는 A-1 후 시드하므로, 여기서는 프레임워크 로직만 격리 검증한다.
pytest-asyncio 없이 asyncio.run 으로 구동(리포 관례). LLM judge 축은 쿼터가 필요해 여기선 미사용.
"""
import os
import json
import asyncio
import tempfile
import pytest
from core.golden_benchmark import GoldenBenchmark


def _gb():
    root = tempfile.mkdtemp()
    proj = tempfile.mkdtemp()
    return GoldenBenchmark(root=os.path.join(root, "bench"), projects_dir=proj), proj


def _write_state(proj_dir, project_id, **fields):
    d = os.path.join(proj_dir, project_id)
    os.makedirs(d, exist_ok=True)
    base = {"project_name": project_id}
    base.update(fields)
    with open(os.path.join(d, "latest_state.json"), "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False)


def test_no_artifact_scores_none():
    gb, _ = _gb()
    card = asyncio.run(gb.evaluate("A-1"))
    assert card["has_artifact"] is False
    assert card["axes"]["deterministic"]["score"] is None
    assert card["composite"] is None


def test_deterministic_scoring_with_artifact():
    gb, proj = _gb()
    _write_state(proj, "test_a1_unitconv",
                 rfp_summary="x" * 600, prd_summary="y" * 600,
                 architecture_summary="arch", tech_spec_summary="ts", ui_mockup_summary="ui",
                 build_status="success",
                 architecture_decisions=[{"id": "ADR-001", "decision": "d", "reason": "r"}])
    card = asyncio.run(gb.evaluate("A-1"))
    det = card["axes"]["deterministic"]
    assert card["has_artifact"] is True
    assert 0.0 < det["score"] <= 1.0
    assert det["checks"]["stage_rfp"] is True
    assert det["checks"]["build_success"] is True
    assert det["passed"] <= det["total"]


def test_human_score_validation_and_composite():
    gb, _ = _gb()
    with pytest.raises(ValueError):
        gb.set_human_score("A-1", 1.5)          # 범위 밖
    with pytest.raises(ValueError):
        gb.set_human_score("UNKNOWN", 0.5)      # 알 수 없는 시나리오
    gb.set_human_score("A-1", 0.8, "수기")
    card = asyncio.run(gb.evaluate("A-1"))       # 산출물 없음 → human 축만
    assert card["axes"]["human"]["score"] == 0.8
    # deterministic None 이고 human 만 있으면 composite = human 점수(재정규화)
    assert card["composite"] == 0.8


def test_promote_and_compare_ok_then_regression():
    gb, proj = _gb()
    _write_state(proj, "test_a1_unitconv", rfp_summary="x" * 600, build_status="success")
    gb.set_human_score("A-1", 0.9)
    asyncio.run(gb.evaluate("A-1"))
    gb.promote_golden("A-1")
    assert gb.compare("A-1")["status"] == "ok"          # 골든=현재
    # 사람 점수 하락 → 재평가 → 회귀 탐지
    gb.set_human_score("A-1", 0.4)
    asyncio.run(gb.evaluate("A-1"))
    rep = gb.compare("A-1")
    assert rep["status"] == "regression"
    assert "human" in rep["regressions"]
    assert rep["composite_delta"] < 0


def test_compare_without_golden():
    gb, _ = _gb()
    assert gb.compare("C-1")["status"] == "no_golden"


def test_promote_without_scorecard_raises():
    gb, _ = _gb()
    with pytest.raises(ValueError):
        gb.promote_golden("D-1")                # evaluate 전 → 승격 불가
