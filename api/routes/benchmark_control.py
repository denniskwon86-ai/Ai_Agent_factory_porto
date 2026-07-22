"""골든 벤치마크 REST API. prefix /api/v1/benchmark.

core/golden_benchmark.py 의 3축 채점·스코어카드·회귀비교를 노출한다.
evaluate 는 (use_llm_judge=True 시) LLM 쿼터를 쓰므로 명시적 호출로만 동작한다.
응답 봉투는 리포 관례 {"status": "success", "data": ...}.
"""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.golden_benchmark import golden_benchmark

router = APIRouter(prefix="/api/v1/benchmark")


class HumanScoreRequest(BaseModel):
    score: float
    notes: Optional[str] = ""


@router.get("/scenarios")
async def list_scenarios():
    return {"status": "success", "data": golden_benchmark.list_scenarios()}


@router.post("/{scenario_id}/evaluate")
async def evaluate(scenario_id: str, use_llm_judge: bool = False):
    """시나리오 산출물을 3축으로 채점해 스코어카드를 생성. use_llm_judge=True 는 LLM 쿼터 소비."""
    try:
        card = await golden_benchmark.evaluate(scenario_id, use_llm_judge=use_llm_judge)
        return {"status": "success", "data": card}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{scenario_id}/scorecard")
async def latest_scorecard(scenario_id: str):
    card = await asyncio.to_thread(golden_benchmark.latest_scorecard, scenario_id)
    if not card:
        raise HTTPException(status_code=404, detail="스코어카드가 없습니다. 먼저 evaluate 하세요.")
    return {"status": "success", "data": card}


@router.post("/{scenario_id}/human-score")
async def set_human_score(scenario_id: str, req: HumanScoreRequest):
    try:
        rec = await asyncio.to_thread(golden_benchmark.set_human_score, scenario_id, req.score, req.notes or "")
        return {"status": "success", "data": rec}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{scenario_id}/promote-golden")
async def promote_golden(scenario_id: str):
    """현재(최신) 스코어카드를 이 시나리오의 골든 기준으로 고정."""
    try:
        card = await asyncio.to_thread(golden_benchmark.promote_golden, scenario_id)
        return {"status": "success", "data": card}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{scenario_id}/compare")
async def compare(scenario_id: str):
    """골든 기준 대비 최신 스코어카드의 회귀(점수 하락) 리포트."""
    report = await asyncio.to_thread(golden_benchmark.compare, scenario_id)
    return {"status": "success", "data": report}
