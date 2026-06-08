import os
from typing import Dict, Any
from state_models import ProjectState
from core.llm_gateway import gateway

def _load_skill(role_name: str) -> str:
    """외부 마크다운 프롬프트 파일을 읽어옵니다 (하드코딩 배제)"""
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

async def run_architect(state: ProjectState) -> Dict[str, Any]:
    print("🧭 [Agent] Architect 비동기 설계 진행 중...")
    prompt = _load_skill("architect_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=True)
    return {
        "architecture_summary": output,
        "factory_mode": "EXECUTION",
        "needs_revision": False
    }

async def run_tech_lead(state: ProjectState) -> Dict[str, Any]:
    print("🛠️ [Agent] Tech Lead 비동기 분석 진행 중...")
    prompt = _load_skill("tech_lead_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=True)
    return {"tech_spec_summary": output}

async def run_developer_fe(state: ProjectState) -> Dict[str, Any]:
    print("🎨 [Agent] Frontend Worker 비동기 코딩 중...")
    prompt = _load_skill("frontend_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=False)
    return {"frontend_code_summary": output}

async def run_developer_be(state: ProjectState) -> Dict[str, Any]:
    print("⚙️ [Agent] Backend Worker 비동기 코딩 중...")
    prompt = _load_skill("backend_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=False)
    return {"backend_code_summary": output}

async def run_code_builder(state: ProjectState) -> Dict[str, Any]:
    print("🏗️ [Agent] CodeBuilder 비동기 병합 진행 중...")
    from nodes.code_builder import CodeBuilder
    
    # 🚨 [패치] LangGraph 런타임의 Pydantic vs Dict 타입 혼용 완벽 방어선 구축
    workspace_root = state.get("workspace_root") if isinstance(state, dict) else state.workspace_root
    frontend_code = state.get("frontend_code_summary", "") if isinstance(state, dict) else state.frontend_code_summary
    backend_code = state.get("backend_code_summary", "") if isinstance(state, dict) else state.backend_code_summary
    dev_retry = state.get("developer_retry_count", 0) if isinstance(state, dict) else state.developer_retry_count
    file_index = state.get("file_index", {}) if isinstance(state, dict) else state.file_index
    
    if not workspace_root:
        raise ValueError("CodeBuilder 실행 중 치명적 오류: workspace_root가 없습니다.")
        
    builder = CodeBuilder(workspace_root=workspace_root)
    target_code = frontend_code + "\n" + backend_code
    
    # 하위 병합 엔진으로 보낼 때 순수 Dict로 변환하여 에러 원천 차단
    state_dict = state if isinstance(state, dict) else state.model_dump()
    updated_state_dict, results = builder.run(state_dict, target_code)
    
    is_failed = updated_state_dict.get("build_status") == "failed"
    new_retry_count = dev_retry + (1 if is_failed else 0)

    return {
        "build_status": "failed" if is_failed else "success",
        "build_error_log": updated_state_dict.get("build_error_log", ""),
        "developer_retry_count": new_retry_count,
        "file_index": updated_state_dict.get("file_index", file_index)
    }

async def run_reviewer(state: ProjectState) -> Dict[str, Any]:
    print("📝 [Agent] Reviewer 비동기 문서화 진행 중...")
    
    prompt = "현재 작성된 모든 코드를 리뷰하고 릴리즈 노트를 작성하십시오."
    output = await gateway.aexecute(state, prompt, is_heavy=False)
    
    from nodes.utils.git_manager import GitManager
    from nodes.utils.wbs_manager import WBSManager
    from core.broadcaster import factory_broadcaster
    import os
    
    # 🚨 [패치] Pydantic/Dict 타입 방어
    workspace_root = state.get("workspace_root") if isinstance(state, dict) else state.workspace_root
    task_id = state.get("current_sprint_task_id", "") if isinstance(state, dict) else state.current_sprint_task_id
    state_dict = state if isinstance(state, dict) else state.model_dump()
    git_info = state.get("git_info", {}) if isinstance(state, dict) else state.git_info.model_dump()
    
    git_mgr = GitManager(workspace_root)
    commit_hash = git_mgr.commit_sprint_changes(task_id, state_dict)
    
    if commit_hash:
        git_info["last_commit_hash"] = commit_hash
        git_info["last_commit_task"] = task_id

    wbs_path = os.path.join(workspace_root, "00_wbs_master_plan.json")
    if os.path.exists(wbs_path):
        # 🚨 [패치] json_path를 전달하던 에러 교정 및 workspace_root 필수 전달
        wbs_mgr = WBSManager(workspace_root=workspace_root)
        wbs_mgr.complete_task(task_id)
        await factory_broadcaster.broadcast("WBS_UPDATED", {"task_id": task_id, "status": "DONE"})

    return {
        "code_review_report_summary": output,
        "git_info": git_info
    }