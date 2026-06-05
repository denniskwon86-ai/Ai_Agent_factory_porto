import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.async_orchestrator import orchestrator
from state_models import ProjectState

router = APIRouter(prefix="/api/v1/factory", tags=["Factory Control"])

class StartSprintRequest(BaseModel):
    task_id: str
    project_state_payload: ProjectState

class HOTLResumeRequest(BaseModel):
    task_id: str
    feedback: str = ""

@router.post("/sprint/start")
async def start_sprint(req: StartSprintRequest):
    """지정된 Task ID의 스프린트를 시작합니다."""
    # 중복 실행 방어
    if req.task_id in orchestrator.active_tasks:
        raise HTTPException(status_code=409, detail="해당 태스크는 이미 실행 중입니다.")
        
    await orchestrator.start_sprint_track(req.task_id, req.project_state_payload)
    return {"status": "started", "task_id": req.task_id, "message": "스프린트가 비동기로 가동되었습니다."}

@router.post("/hotl/resume")
async def resume_from_hotl(req: HOTLResumeRequest):
    """대기 상태인 파이프라인에 피드백을 전달하고 재가동합니다."""
    if req.task_id in orchestrator.active_tasks:
        raise HTTPException(status_code=409, detail="해당 태스크는 현재 처리 중입니다. 대기 상태가 아닙니다.")
        
    success = await orchestrator.resume_hotl(req.task_id, req.feedback)
    if not success:
        raise HTTPException(status_code=404, detail="해당 Task ID의 대기 중인 세션을 찾을 수 없습니다.")
    return {"status": "resumed", "task_id": req.task_id}

@router.post("/sprint/{task_id}/stop")
async def stop_sprint(task_id: str):
    """실행 중인 스프린트를 안전하게 취소(Cancel)합니다."""
    success = orchestrator.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="실행 중인 태스크를 찾을 수 없습니다.")
    return {"status": "stopped", "task_id": task_id, "message": "강제 중지 명령이 전달되었습니다."}

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