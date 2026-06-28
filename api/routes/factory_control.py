import json
import os
import re
import shutil
import stat
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.async_orchestrator import orchestrator

router = APIRouter(prefix="/api/v1/factory")

LIBRARY_DIR = "library"  # 배포된 최종 결과물 보관소

class SprintStartRequest(BaseModel):
    task_id: str
    project_state_payload: dict

class HOTLResumeRequest(BaseModel):
    task_id: str
    feedback: Optional[str] = ""

class RevisionRequest(BaseModel):
    feedback: str

class ProjectCreateRequest(BaseModel):
    project_id: str

class HealRequest(BaseModel):
    error_log: str

class SprintPauseRequest(BaseModel):
    task_id: str

# Windows '.git' 읽기 전용 폴더 강제 권한 해제 콜백 (Python 3.12+ onexc 규격)
def _on_rmtree_error(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)

# 경로 파라미터(project_id/release_id)는 파일시스템 경로로 직접 사용되므로 단일 세그먼트만 허용한다.
# '/', '\\', '..', 절대경로, 빈값을 차단해 디렉토리 이탈(path traversal)을 원천 봉쇄한다.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

def _safe_id(value: str, label: str = "id") -> str:
    if not _ID_RE.match(value or ""):
        raise HTTPException(status_code=400, detail=f"잘못된 {label} 형식입니다.")
    return value

@router.get("/projects")
async def get_projects():
    projects_dir = "./projects"
    os.makedirs(projects_dir, exist_ok=True)
    
    project_list = []
    for item in os.listdir(projects_dir):
        item_path = os.path.join(projects_dir, item)
        if os.path.isdir(item_path):
            wbs_path = os.path.join(item_path, "00_wbs_master_plan.json")
            project_name = item
            if os.path.exists(wbs_path):
                try:
                    with open(wbs_path, "r", encoding="utf-8") as f:
                        wbs_data = json.load(f)
                        project_name = wbs_data.get("project_name", item)
                except:
                    pass
            project_list.append({"id": item, "name": project_name})
            
    return {"status": "success", "data": project_list}

@router.post("/projects")
async def create_project(req: ProjectCreateRequest):
    _safe_id(req.project_id, "project_id")  # 디스크에 안전한 id만 생성 → 이후 모든 라우트가 안전한 id를 다루도록 보장
    project_path = os.path.join("./projects", req.project_id)
    if os.path.exists(project_path):
        raise HTTPException(status_code=409, detail="이미 존재하는 프로젝트 ID입니다.")
    os.makedirs(project_path, exist_ok=True)
    return {"status": "success", "project_id": req.project_id}

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    _safe_id(project_id, "project_id")  # rmtree 대상 경로 이탈 방지(가장 파괴적인 벡터)
    # 🛑 삭제 전, 해당 프로젝트의 실행 중 스프린트를 취소 (좀비 스프린트 방지)
    await orchestrator.cancel_project(project_id)
    project_path = os.path.join("./projects", project_id)
    if os.path.exists(project_path):
        try:
            # 🚨 ignore_errors=True 대신 강제 권한 해제(onerror) 로직 적용
            shutil.rmtree(project_path, onexc=_on_rmtree_error)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"삭제 실패 (파일이 사용 중일 수 있습니다): {str(e)}")
    return {"status": "success"}

@router.post("/{project_id}/sprint/start")
async def start_sprint(project_id: str, req: SprintStartRequest):
    _safe_id(project_id, "project_id")
    workspace_root = f"./projects/{project_id}"
    req.project_state_payload["workspace_root"] = workspace_root

    # 리비전 태스크(TASK_REV_*)는 Architect를 건너뛰고 Tech_Lead로 직행해야 하므로
    # 프론트엔드 오탐을 방어하기 위해 백엔드에서도 factory_mode를 강제 보정합니다.
    if req.task_id.startswith("TASK_REV_"):
        req.project_state_payload["factory_mode"] = "REVISION"

    await orchestrator.start_sprint(req.task_id, req.project_state_payload, workspace_root)
    return {"status": "started", "task_id": req.task_id}

@router.post("/{project_id}/sprint/pause")
async def pause_sprint(project_id: str, req: SprintPauseRequest):
    _safe_id(project_id, "project_id")
    await orchestrator.pause_sprint(req.task_id)
    return {"status": "paused", "task_id": req.task_id}

@router.post("/{project_id}/hotl/resume")
async def resume_from_hotl(project_id: str, req: HOTLResumeRequest):
    _safe_id(project_id, "project_id")
    success = await orchestrator.resume_hotl(req.task_id, req.feedback)
    if not success:
        raise HTTPException(status_code=500, detail="파이프라인 재가동에 실패했습니다.")
    return {"status": "resumed", "task_id": req.task_id}

@router.get("/{project_id}/hotl/check")
async def check_hotl(project_id: str):
    """진행 중(IN_PROGRESS) 태스크가 HOTL 중단점에서 대기 중인지 조회 (SSE 이벤트 유실 복구용)."""
    _safe_id(project_id, "project_id")
    from nodes.utils.wbs_manager import WBSManager
    try:
        wbs = WBSManager(workspace_root=f"./projects/{project_id}").get_wbs()
    except Exception:
        wbs = {"tasks": []}
    for t in wbs.get("tasks", []):
        if t.get("status") == "IN_PROGRESS":
            tid = t.get("task_id")
            if await orchestrator.is_hotl_pending(tid):
                return {"status": "success", "hotl_task_id": tid}
    return {"status": "success", "hotl_task_id": None}

@router.post("/{project_id}/sprint/revision")
async def create_revision_task(project_id: str, req: RevisionRequest):
    _safe_id(project_id, "project_id")
    from nodes.utils.wbs_manager import WBSManager
    wbs_mgr = WBSManager(workspace_root=f"./projects/{project_id}")
    task_id = wbs_mgr.add_revision_task(req.feedback)
    if not task_id:
        raise HTTPException(status_code=500, detail="WBS를 찾을 수 없습니다.")
    return {"status": "success", "task_id": task_id}

@router.post("/{project_id}/heal")
async def trigger_self_healing(project_id: str, req: HealRequest):
    _safe_id(project_id, "project_id")
    from nodes.utils.wbs_manager import WBSManager

    workspace_root = f"./projects/{project_id}"
    wbs_mgr = WBSManager(workspace_root=workspace_root)

    feedback = f"🚨 [자동 캡처 에러 리포트] UI 렌더링 중 에러 발생:\n{req.error_log}\n해당 에러를 분석하여 코드를 즉시 복원하십시오."
    task_id = wbs_mgr.add_revision_task(feedback)

    state_path = os.path.join(workspace_root, "latest_state.json")
    project_state_payload = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                project_state_payload = json.load(f)
        except:
            pass

    project_state_payload["build_error_log"] = req.error_log
    project_state_payload["factory_mode"] = "REVISION"
    project_state_payload["current_sprint_task_id"] = task_id
    project_state_payload["workspace_root"] = workspace_root

    await orchestrator.start_sprint(task_id, project_state_payload, workspace_root)
    return {"status": "healing_started", "task_id": task_id}

@router.get("/{project_id}/wbs")
async def get_wbs_master_plan(project_id: str):
    _safe_id(project_id, "project_id")
    wbs_path = os.path.join("projects", project_id, "00_wbs_master_plan.json")
    if not os.path.exists(wbs_path):
        return {"status": "not_found", "data": None}
    try:
        with open(wbs_path, "r", encoding="utf-8") as f:
            wbs_data = json.load(f)
        return {"status": "success", "data": wbs_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WBS 파일을 읽는 중 오류 발생: {str(e)}")

@router.get("/{project_id}/feed")
async def get_supervisor_feed(project_id: str):
    """슈퍼바이저 콘솔 피드(토론·채점 내레이션) 조회 — 새로고침/재접속 복구용."""
    _safe_id(project_id, "project_id")
    feed_path = os.path.join("projects", project_id, "supervisor_feed.json")
    if not os.path.exists(feed_path):
        return {"status": "success", "data": []}
    try:
        with open(feed_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"status": "success", "data": data if isinstance(data, list) else []}
    except Exception:
        return {"status": "success", "data": []}

@router.get("/{project_id}/state/latest")
async def get_latest_state(project_id: str):
    _safe_id(project_id, "project_id")
    state_path = os.path.join("projects", project_id, "latest_state.json")
    if not os.path.exists(state_path):
        return {"status": "not_found", "data": None}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        return {"status": "success", "data": state_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 파일 읽기 오류: {str(e)}")


# ==========================================
# 결과물 라이브러리 (배포/최종 결과물 저장 + 보관 + 재실행)
# ==========================================
@router.post("/{project_id}/release")
async def create_release(project_id: str):
    """완료된 프로젝트의 최종 결과물을 라이브러리에 스냅샷 저장(배포)."""
    _safe_id(project_id, "project_id")  # 경로 이탈 방지 + release_id가 라이브러리 라우트와 왕복 가능하도록 보장
    state_path = os.path.join("projects", project_id, "latest_state.json")
    if not os.path.exists(state_path):
        raise HTTPException(status_code=404, detail="저장할 결과물 상태가 없습니다.")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 읽기 오류: {str(e)}")

    wbs_tasks = []
    wbs_path = os.path.join("projects", project_id, "00_wbs_master_plan.json")
    if os.path.exists(wbs_path):
        try:
            with open(wbs_path, "r", encoding="utf-8") as f:
                wbs_tasks = json.load(f).get("tasks", [])
        except Exception:
            pass

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    release_id = f"{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    release = {
        "release_id": release_id,
        "project_id": project_id,
        "project_name": s.get("project_name", project_id),
        "created_at": created_at,
        "rfp_summary": s.get("rfp_summary", ""),
        "prd_summary": s.get("prd_summary", ""),
        "architecture_summary": s.get("architecture_summary", ""),
        "tech_spec_summary": s.get("tech_spec_summary", ""),
        "frontend_code_summary": s.get("frontend_code_summary", ""),
        "backend_code_summary": s.get("backend_code_summary", ""),
        "code_review_report_summary": s.get("code_review_report_summary", ""),
        "qa_report_summary": s.get("qa_report_summary", ""),
        "user_manual_summary": s.get("user_manual_summary", ""),
        "wbs_tasks": wbs_tasks,
    }
    rel_dir = os.path.join(LIBRARY_DIR, release_id)
    os.makedirs(rel_dir, exist_ok=True)
    with open(os.path.join(rel_dir, "release.json"), "w", encoding="utf-8") as f:
        json.dump(release, f, ensure_ascii=False, indent=2)
    return {"status": "success", "release_id": release_id}


@router.get("/library/list")
async def list_releases():
    """라이브러리에 보관된 결과물 목록(요약)."""
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    items = []
    for rid in os.listdir(LIBRARY_DIR):
        rp = os.path.join(LIBRARY_DIR, rid, "release.json")
        if os.path.exists(rp):
            try:
                with open(rp, "r", encoding="utf-8") as f:
                    r = json.load(f)
                items.append({
                    "release_id": r.get("release_id", rid),
                    "project_name": r.get("project_name", rid),
                    "created_at": r.get("created_at", ""),
                    "task_count": len(r.get("wbs_tasks", [])),
                })
            except Exception:
                continue
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"status": "success", "data": items}


@router.get("/library/item/{release_id}")
async def get_release(release_id: str):
    """결과물 상세(재실행/프리뷰용 — frontend 코드 포함)."""
    _safe_id(release_id, "release_id")  # 경로 이탈로 임의 release.json 읽기 방지
    rp = os.path.join(LIBRARY_DIR, release_id, "release.json")
    if not os.path.exists(rp):
        raise HTTPException(status_code=404, detail="결과물을 찾을 수 없습니다.")
    try:
        with open(rp, "r", encoding="utf-8") as f:
            return {"status": "success", "data": json.load(f)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"결과물 읽기 오류: {str(e)}")


@router.delete("/library/item/{release_id}")
async def delete_release(release_id: str):
    _safe_id(release_id, "release_id")  # 경로 이탈로 임의 디렉토리 삭제 방지
    rel_dir = os.path.join(LIBRARY_DIR, release_id)
    if not os.path.isdir(rel_dir):
        raise HTTPException(status_code=404, detail="결과물을 찾을 수 없습니다.")
    try:
        # delete_project와 동일하게 onexc로 Windows 잠금/읽기전용 파일 실패를 표면화한다(ignore_errors=True의 무음 실패 방지)
        shutil.rmtree(rel_dir, onexc=_on_rmtree_error)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제 실패 (파일이 사용 중일 수 있습니다): {str(e)}")
    return {"status": "success"}


# ==========================================
# 에이전트 마스터 제어판 — 레지스트리(역할/스킬/모델/순서/HOTL/활성화) 조회·저장
# (범용 멀티에이전트 플랫폼 Phase 1: 외부 SSOT. HOTL 중단점은 서버 재시작 시 그래프에 반영)
# ==========================================
class AgentRegistryPayload(BaseModel):
    version: Optional[int] = 1
    pipeline_name: Optional[str] = ""
    description: Optional[str] = ""
    agents: list


@router.get("/agents")
async def get_agent_registry():
    """에이전트 마스터 레지스트리 조회."""
    from core.agent_registry import load_registry
    return {"status": "success", "data": load_registry()}


@router.put("/agents")
async def update_agent_registry(payload: AgentRegistryPayload):
    """제어판에서 편집한 레지스트리 저장(검증·정규화 후 영속화)."""
    from core.agent_registry import save_registry
    try:
        saved = save_registry(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"레지스트리 저장 오류: {str(e)}")
    # 주의: HOTL 중단점 등 실행 반영은 그래프 재컴파일(서버 재시작) 시 적용된다.
    return {"status": "success", "data": saved, "note": "HOTL 중단점 변경은 서버 재시작 후 파이프라인에 반영됩니다."}


@router.post("/agents/reset")
async def reset_agent_registry():
    """레지스트리를 기본값(현재 SW 파이프라인)으로 초기화."""
    from core.agent_registry import reset_registry
    return {"status": "success", "data": reset_registry()}