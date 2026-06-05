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
    """[Track 1] 아키텍처 및 DB 스키마 설계 (Pro 모델 배정)"""
    print("🧭 [Agent] Architect 비동기 설계 진행 중...")
    prompt = _load_skill("architect_skill")
    
    output = await gateway.aexecute(state, prompt, is_heavy=True)
    
    # LangGraph Native Reducer 활용: 전체 State 객체를 덮어쓰지 않고 변경된 Dict만 반환 (코드 획기적 단축)
    return {
        "architecture_summary": output,
        "factory_mode": "EXECUTION",
        "needs_revision": False
    }

async def run_tech_lead(state: ProjectState) -> Dict[str, Any]:
    """[Track 1] 기술 명세 및 수정 대상 파일 색출 (Pro 모델 배정)"""
    print("🛠️ [Agent] Tech Lead 비동기 분석 진행 중...")
    prompt = _load_skill("tech_lead_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=True)
    return {"tech_spec_summary": output}

async def run_developer_fe(state: ProjectState) -> Dict[str, Any]:
    """[Track 1] 프론트엔드 React 컴포넌트 코딩 (Flash 모델 배정 - 자원 최적화)"""
    print("🎨 [Agent] Frontend Worker 비동기 코딩 중...")
    prompt = _load_skill("frontend_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=False)
    return {"frontend_code_summary": output}

async def run_developer_be(state: ProjectState) -> Dict[str, Any]:
    """[Track 1] 백엔드 FastAPI 라우터 코딩 (Flash 모델 배정 - 자원 최적화)"""
    print("⚙️ [Agent] Backend Worker 비동기 코딩 중...")
    prompt = _load_skill("backend_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=False)
    return {"backend_code_summary": output}

async def run_code_builder(state: ProjectState) -> Dict[str, Any]:
    """[Track 1] 4계층 스마트 패치 엔진 (CPU 바운드 로직)"""
    print("🏗️ [Agent] CodeBuilder 비동기 병합 진행 중...")
    from nodes.code_builder import CodeBuilder  # 기존 V4.0 병합 엔진 재사용
    
    builder = CodeBuilder(workspace_root=state.workspace_root)
    # FE/BE 코드를 취합하여 스마트 패치 전송
    target_code = state.frontend_code_summary + "\n" + state.backend_code_summary
    
    # 기존 코드빌더는 딕셔너리 기반 state를 사용했으므로 모델을 dump하여 넘김
    state_dict = state.model_dump()
    updated_state_dict, results = builder.run(state_dict, target_code)
    
    # 빌드 실패 여부에 따른 서킷 브레이커 카운트 갱신
    is_failed = updated_state_dict.get("build_status") == "failed"
    new_retry_count = state.developer_retry_count + (1 if is_failed else 0)

    return {
        "build_status": "failed" if is_failed else "success",
        "build_error_log": updated_state_dict.get("build_error_log", ""),
        "developer_retry_count": new_retry_count,
        "file_index": updated_state_dict.get("file_index", state.file_index)
    }

async def run_reviewer(state: ProjectState) -> Dict[str, Any]:
    """[Track 1] 스프린트 릴리즈 노트 작성 및 자동 커밋 (Flash 모델 배정)"""
    print("📝 [Agent] Reviewer 비동기 문서화 진행 중...")
    prompt = _load_skill("reviewer_skill")
    output = await gateway.aexecute(state, prompt, is_heavy=False)
    
    # Git Layer 자동 커밋 및 WBS 매니저 호출
    from nodes.utils.git_manager import GitManager
    from nodes.utils.wbs_manager import WBSManager  # 🚨 WBS 매니저 임포트 추가
    import os
    
    workspace_root = state.get("workspace_root", "./workspace") if isinstance(state, dict) else state.workspace_root
    task_id = state.get("current_sprint_task_id", "") if isinstance(state, dict) else state.current_sprint_task_id
    state_dict = state if isinstance(state, dict) else state.model_dump()
    
    git_mgr = GitManager(workspace_root)
    commit_hash = git_mgr.commit_sprint_changes(task_id, state_dict)
    
    git_info = state.get("git_info", {}) if isinstance(state, dict) else state.git_info.model_dump()
    if commit_hash:
        git_info["last_commit_hash"] = commit_hash
        git_info["last_commit_task"] = task_id

    # 🚨 [추가 로직] 스프린트 최종 완료 시 WBS 마스터플랜 파일에 'DONE' 상태 원자적 기록
    wbs_path = os.path.join(workspace_root, "00_wbs_master_plan.json")
    if os.path.exists(wbs_path):
        wbs_mgr = WBSManager(json_path=wbs_path)
        wbs_mgr.checkout_task(task_id)

    return {
        "code_review_report_summary": output,
        "git_info": git_info
    }