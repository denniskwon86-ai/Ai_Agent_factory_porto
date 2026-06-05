import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.async_orchestrator import orchestrator

# 최상위 main.py에서 prefix="/api/v1/factory"를 처리하므로 여기서는 순수 라우터만 선언합니다.
router = APIRouter()

class SprintStartRequest(BaseModel):
    task_id: str
    project_state_payload: dict

class HOTLResumeRequest(BaseModel):
    task_id: str
    feedback: Optional[str] = ""

@router.post("/sprint/start")
async def start_sprint(req: SprintStartRequest):
    """프론트엔드의 가동 명령을 받아 오케스트레이터의 스프린트를 시작합니다."""
    await orchestrator.start_sprint(req.task_id, req.project_state_payload)
    return {"status": "started", "task_id": req.task_id}

@router.post("/hotl/resume")
async def resume_from_hotl(req: HOTLResumeRequest):
    """인간의 승인/피드백을 받아 멈춰있던 파이프라인을 재가동합니다."""
    success = await orchestrator.resume_hotl(req.task_id, req.feedback)
    if not success:
        raise HTTPException(status_code=500, detail="파이프라인 재가동에 실패했습니다.")
    return {"status": "resumed", "task_id": req.task_id}

@router.get("/wbs")
async def get_wbs_master_plan():
    """프론트엔드에서 현재 WBS 진행 현황을 조회하기 위한 엔드포인트"""
    wbs_path = os.path.join("workspace", "00_wbs_master_plan.json")
    if not os.path.exists(wbs_path):
        return {"status": "not_found", "message": "WBS 마스터 플랜이 아직 생성되지 않았습니다.", "data": None}
    
    try:
        with open(wbs_path, "r", encoding="utf-8") as f:
            wbs_data = json.load(f)
        return {"status": "success", "data": wbs_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WBS 파일을 읽는 중 오류 발생: {str(e)}")