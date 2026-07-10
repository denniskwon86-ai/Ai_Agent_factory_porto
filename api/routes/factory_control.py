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

class SupervisorChatRequest(BaseModel):
    task_id: str
    message: str

class ProjectCreateRequest(BaseModel):
    project_id: str
    template_id: str = "default"  # 이 프로젝트가 실행될 워크플로우 템플릿(범용 플랫폼 T2-b)
    output_format_id: str = "default"  # 이 프로젝트에 적용될 출력 포맷
    view_type: str = "react_app"

class ProjectCopyRequest(BaseModel):
    new_project_id: str

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

# 새로고침/SSE 재연결 후 클라이언트 state가 비거나 stale 해지면, 다음 태스크 페이로드에서
# 누적 산출물(file_index/요약/git)이 유실되어 기존 맥락·기능이 사라진다(감사: file_index_gap).
# → 태스크 시작 시 디스크 진실원본(latest_state.json)에서 '비어 있는 누적 필드만' 채운다
#   (클라이언트가 채운 값/이번 태스크 의도는 절대 덮어쓰지 않는 보수적 병합).
_ACCUMULATED_FIELDS = [
    "file_index", "rfp_summary", "prd_summary", "architecture_summary", "tech_spec_summary",
    "frontend_code_summary", "backend_code_summary", "code_review_report_summary",
    "qa_report_summary", "user_manual_summary", "git_info",
    "architecture_decisions", "technical_debt", "initial_idea", "project_name",
]


def _is_empty(v) -> bool:
    return v in (None, "", [], {})


# 프로젝트↔워크플로우 템플릿 바인딩(T2-b) — 프로젝트 폴더에 영속해, 새로고침/HOTL 재개로
# 프론트 state 가 stale 해져도 모든 태스크가 같은 템플릿으로 실행되도록 보장한다.
def _project_meta_path(workspace_root: str) -> str:
    return os.path.join(workspace_root, "project_meta.json")


def _read_project_meta(workspace_root: str) -> tuple[str, str, str]:
    try:
        with open(_project_meta_path(workspace_root), "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            tid = data.get("template_id", "default")
            fid = data.get("output_format_id", "default")
            vtype = data.get("view_type", "react_app")
        return tid or "default", fid or "default", vtype or "react_app"
    except Exception:
        return "default", "default", "react_app"

def _read_project_template(workspace_root: str) -> str:
    tid, _, _ = _read_project_meta(workspace_root)
    return tid


def _write_project_meta(workspace_root: str, template_id: str, output_format_id: str = "default", view_type: str = "react_app") -> None:
    try:
        with open(_project_meta_path(workspace_root), "w", encoding="utf-8") as f:
            json.dump({"template_id": template_id or "default", "output_format_id": output_format_id or "default", "view_type": view_type or "react_app"}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ project_meta 저장 실패: {e}")


def _restore_accumulated_from_disk(payload: dict, workspace_root: str) -> dict:
    state_path = os.path.join(workspace_root, "latest_state.json")
    if not os.path.exists(state_path):
        return payload
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            disk = json.load(f)
    except Exception:
        return payload  # 읽기 실패 시 원본 유지
    if not isinstance(disk, dict):
        return payload
    for k in _ACCUMULATED_FIELDS:
        if _is_empty(payload.get(k)) and not _is_empty(disk.get(k)):
            payload[k] = disk[k]
    return payload

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
            initial_idea = ""
            if os.path.exists(wbs_path):
                try:
                    with open(wbs_path, "r", encoding="utf-8") as f:
                        wbs_data = json.load(f)
                        project_name = wbs_data.get("project_name", item)
                except:
                    pass
            state_path = os.path.join(item_path, "latest_state.json")
            if os.path.exists(state_path):
                try:
                    with open(state_path, "r", encoding="utf-8") as f:
                        state_data = json.load(f)
                        initial_idea = state_data.get("initial_idea", "")
                except:
                    pass
            project_list.append({"id": item, "name": project_name, "initial_idea": initial_idea})
            
    return {"status": "success", "data": project_list}

@router.post("/projects")
async def create_project(req: ProjectCreateRequest):
    _safe_id(req.project_id, "project_id")  # 디스크에 안전한 id만 생성 → 이후 모든 라우트가 안전한 id를 다루도록 보장
    # 템플릿 id 검증(형식 + 존재). 미존재/잘못된 형식이면 거부 — 잘못된 바인딩이 조용히 default 로
    # 폴백해 사용자가 고른 워크플로우와 다르게 실행되는 혼란을 막는다.
    from core.agent_registry import _safe_tid, list_templates
    tid = req.template_id or "default"
    try:
        _safe_tid(tid)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 template_id 형식입니다.")
    if tid not in {t["id"] for t in list_templates()}:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 템플릿입니다: {tid}")

    project_path = os.path.join("./projects", req.project_id)
    if os.path.exists(project_path):
        raise HTTPException(status_code=409, detail="이미 존재하는 프로젝트 ID입니다.")
    os.makedirs(project_path, exist_ok=True)
    _write_project_meta(project_path, tid, req.output_format_id, req.view_type)  # 프로젝트↔템플릿/포맷 바인딩 영속
    return {"status": "success", "project_id": req.project_id, "template_id": tid, "view_type": req.view_type}

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

@router.post("/projects/{project_id}/copy")
async def copy_project(project_id: str, req: ProjectCopyRequest):
    _safe_id(project_id, "project_id")
    _safe_id(req.new_project_id, "new_project_id")
    
    src_path = os.path.join("./projects", project_id)
    dst_path = os.path.join("./projects", req.new_project_id)
    
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="원본 프로젝트가 없습니다.")
    if os.path.exists(dst_path):
        raise HTTPException(status_code=409, detail="새 프로젝트 ID가 이미 존재합니다.")
        
    try:
        shutil.copytree(src_path, dst_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"복사 실패: {e}")
        
    return {"status": "success", "new_project_id": req.new_project_id}

@router.post("/{project_id}/sprint/start")
async def start_sprint(project_id: str, req: SprintStartRequest):
    _safe_id(project_id, "project_id")
    workspace_root = f"./projects/{project_id}"
    req.project_state_payload["workspace_root"] = workspace_root
    # T2-b: 프로젝트에 바인딩된 템플릿을 권위 있는 출처(project_meta.json)에서 주입 — 프론트 state 가
    #   stale 해도 모든 태스크가 같은 워크플로우로 실행되도록 보장(오케스트레이터가 이 값으로 그래프 선택).
    req.project_state_payload["template_id"] = _read_project_template(workspace_root)

    # 신규 기획(PLANNING)은 새 출발이므로 옛 누적 산출물을 복원하지 않는다.
    # 그 외(실행/리비전) 태스크는 stale 페이로드의 빈 누적 필드를 디스크 진실원본에서 복원.
    if not req.task_id.startswith("PLANNING"):
        req.project_state_payload = _restore_accumulated_from_disk(req.project_state_payload, workspace_root)
        # 🚨 태스크별 재작업 카운터 리셋 — 이전 태스크의 누적(supervisor_hops/developer_retry_count)이
        #   새 태스크로 새어 즉시 상한에 걸려 검수가 통째로 건너뛰어지는 크로스-태스크 오염 차단.
        #   (각 태스크는 독립적인 리뷰/빌드 재작업 예산을 받는다.)
        req.project_state_payload["supervisor_hops"] = 0
        req.project_state_payload["developer_retry_count"] = 0

    # 리비전 태스크(TASK_REV_*)는 Architect를 건너뛰고 Tech_Lead로 직행해야 하므로
    # 프론트엔드 오탐을 방어하기 위해 백엔드에서도 factory_mode를 강제 보정합니다.
    if req.task_id.startswith("TASK_REV_"):
        req.project_state_payload["factory_mode"] = "REVISION"

    req.project_state_payload["current_sprint_task_id"] = req.task_id

    # Reset old stages and inject current_required_agents from WBS
    wbs_path = os.path.join(workspace_root, "00_wbs_master_plan.json")
    if os.path.exists(wbs_path):
        try:
            with open(wbs_path, "r", encoding="utf-8") as f:
                wbs_data = json.load(f)
                for t in wbs_data.get("tasks", []):
                    if t.get("task_id") == req.task_id:
                        req.project_state_payload["current_required_agents"] = t.get("required_agents", [])
                        break
        except Exception:
            pass

    # Clear current_stage and stage_scores for execution so it runs cleanly
    if req.project_state_payload.get("factory_mode") == "EXECUTION" and not req.task_id.startswith("PLANNING"):
        req.project_state_payload["current_stage"] = ""
        # Remove old coding scores so it doesn't skip
        for st in ["CODE_REVIEW", "Backend", "Frontend", "QA"]:
            if "stage_scores" in req.project_state_payload and st in req.project_state_payload["stage_scores"]:
                del req.project_state_payload["stage_scores"][st]

    await orchestrator.start_sprint(req.task_id, req.project_state_payload, workspace_root)
    return {"status": "started", "task_id": req.task_id}

@router.post("/{project_id}/sprint/pause")
async def pause_sprint(project_id: str, req: SprintPauseRequest):
    _safe_id(project_id, "project_id")
    await orchestrator.pause_sprint(req.task_id, project_id)
    return {"status": "paused", "task_id": req.task_id}

@router.post("/{project_id}/hotl/resume")
async def resume_from_hotl(project_id: str, req: HOTLResumeRequest):
    _safe_id(project_id, "project_id")
    success = await orchestrator.resume_hotl(req.task_id, req.feedback, project_id)
    if not success:
        raise HTTPException(status_code=500, detail="파이프라인 재가동에 실패했습니다.")
    return {"status": "resumed", "task_id": req.task_id}

@router.post("/{project_id}/supervisor/chat")
async def supervisor_chat(project_id: str, req: SupervisorChatRequest):
    _safe_id(project_id, "project_id")
    state_path = os.path.join("projects", project_id, "latest_state.json")
    state_data = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
        except:
            pass
    from core.supervisor_daemon import supervisor_daemon
    response = await supervisor_daemon.handle_user_chat(project_id, req.task_id, req.message, state_data)
    return response

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
            if await orchestrator.is_hotl_pending(tid, project_id):
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
    project_state_payload["template_id"] = _read_project_template(workspace_root)  # T2-b: 바인딩 템플릿 유지

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
        tid, fid, vtype = _read_project_meta(os.path.join("projects", project_id))
        return {"status": "not_found", "data": {"template_id": tid, "output_format_id": fid, "view_type": vtype}}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        # fallback to meta if missing in state
        if "output_format_id" not in state_data or not state_data["output_format_id"]:
            _, fid, vtype = _read_project_meta(os.path.join("projects", project_id))
            state_data["output_format_id"] = fid
            state_data["view_type"] = vtype
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

    from core.agent_registry import load_template
    tid = s.get("template_id", "default")
    template_data = load_template(tid)

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
        "template_id": s.get("template_id", "default"),
        "deliverable_type": template_data.get("deliverable_type", "software_app"),
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
                    "template_id": r.get("template_id", "default"),
                    "deliverable_type": r.get("deliverable_type", "software_app"),
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
    edges: Optional[list] = []


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


# ==========================================
# AI 추천 엔진 연동 (파이프라인 및 스킬 자동 생성)
# ==========================================
class AIRecommendPipelineRequest(BaseModel):
    user_request: str

class AIRecommendSkillRequest(BaseModel):
    agent_id: str
    agent_name_ko: str
    role_description: str

@router.post("/ai-recommend/pipeline")
async def ai_recommend_pipeline(req: AIRecommendPipelineRequest):
    from core.llm_gateway import LLMGateway
    prompt = f"""
    사용자가 원하는 에이전트 기능을 바탕으로 전체 파이프라인(에이전트 목록 및 연결 관계)을 설계해 줘.
    요청: {req.user_request}
    
    출력 형식: 반드시 아래 JSON 스키마를 따를 것.
    {{
        "pipeline_name": "...",
        "description": "...",
        "agents": [
            {{
                "id": "영문_ID_형식",
                "name_ko": "한글 표시명",
                "role": "역할 상세 설명",
                "skill": "skill_name_without_md",
                "stage": "STAGE_NAME",
                "category": "planning|execution|review|system 중에 하나 선택",
                "model_tier": "pro",
                "order": 1,
                "enabled": true,
                "hotl_after": false,
                "debate": false,
                "llm": true,
                "is_start": true/false,
                "is_end": true/false
            }}
        ],
        "edges": [
            {{
                "id": "e-source_agent_id-target_agent_id",
                "source": "source_agent_id",
                "target": "target_agent_id",
                "animated": true,
                "style": {{"stroke": "#4b5563", "strokeWidth": 2}}
            }}
        ]
    }}
    """
    llm = LLMGateway()
    res = await llm.aexecute({}, prompt, output_mode="json", light=True)
    try:
        import re
        # 마크다운 ```json ... ``` 코드블록 제거
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', res, re.DOTALL)
        if match:
            res = match.group(1)
        data = json.loads(res)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파이프라인 생성 실패: {str(e)}\n\n(LLM 응답: {res[:100]}...)")

@router.post("/ai-recommend/skill")
async def ai_recommend_skill(req: AIRecommendSkillRequest):
    from core.llm_gateway import LLMGateway
    prompt = f"""
    사용자가 지정한 에이전트의 간략한 역할을 바탕으로, 이 에이전트가 어떤 입력을 받아 어떤 산출물을 내고, 누구에게 전달해야 하는지를 명시하는 상세 마크다운 스킬 문서를 작성해 줘.
    - 에이전트 ID: {req.agent_id}
    - 에이전트 명: {req.agent_name_ko}
    - 사용자 입력 간략 역할: {req.role_description}
    
    [출력 요구사항]
    1. 이 에이전트의 구체적 역할과 책임을 상세히 작성할 것 (role 업데이트용으로 사용됨).
    2. 그에 맞는 스킬 마크다운 문서 내용을 작성할 것.
    
    출력 형식: 반드시 아래 JSON 형식으로 반환해 줘.
    {{
        "role_expanded": "에이전트 역할에 대한 2~3줄 상세 설명",
        "skill_markdown": "작성된 스킬 마크다운 내용 전체 (문자열)"
    }}
    """
    llm = LLMGateway()
    res = await llm.aexecute({}, prompt, output_mode="json", light=True)
    try:
        import re
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', res, re.DOTALL)
        if match:
            res = match.group(1)
        data = json.loads(res)
        skill_id = f"{req.agent_id.lower()}_skill"
        skill_path = os.path.join("skills", f"{skill_id}.md")
        os.makedirs("skills", exist_ok=True)
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(data["skill_markdown"])
            
        return {"status": "success", "role": data["role_expanded"], "skill": skill_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스킬 생성 실패: {str(e)}\n\n(LLM 응답: {res[:100]}...)")


# ==========================================
# 다중 워크플로우 템플릿 (Copy 모델) — 기존(default) 보존 + 복사로 새 워크플로우 생성/편집
# ==========================================
class TemplateCopyRequest(BaseModel):
    src_id: str = "default"
    new_id: str
    new_name: Optional[str] = ""


@router.get("/templates")
async def list_workflow_templates():
    """공존하는 워크플로우 템플릿 목록(항상 default 포함)."""
    from core.agent_registry import list_templates
    return {"status": "success", "data": list_templates()}


@router.get("/templates/{template_id}")
async def get_workflow_template(template_id: str):
    from core.agent_registry import load_template, _safe_tid, _template_path
    try:
        _safe_tid(template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    print("DEBUG get_template path:", _template_path(template_id))
    return {"status": "success", "data": load_template(template_id)}


@router.post("/templates/copy")
async def copy_workflow_template(req: TemplateCopyRequest):
    """기존 템플릿을 복사해 새 워크플로우 생성(기존은 불변 — Copy 모델)."""
    from core.agent_registry import copy_template
    try:
        tpl = copy_template(req.src_id, req.new_id, req.new_name or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "template_id": req.new_id, "data": tpl}


@router.put("/templates/{template_id}")
async def update_workflow_template(template_id: str, payload: AgentRegistryPayload):
    from core.agent_registry import save_template, _safe_tid
    try:
        _safe_tid(template_id)
        saved = save_template(template_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"템플릿 저장 오류: {str(e)}")
    return {"status": "success", "data": saved}


@router.delete("/templates/{template_id}")
async def delete_workflow_template(template_id: str):
    from core.agent_registry import delete_template, _safe_tid
    try:
        _safe_tid(template_id)
        delete_template(template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success"}