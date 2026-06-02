from typing import TypedDict, List, Optional

class ProjectState(TypedDict):
    # ==========================================
    # 1. 공통 제어
    # ==========================================
    initial_idea: str
    human_feedback_queue: List[str]
    pipeline_status: str
    error_log: str
    output_dir: str
    review_iteration: int
    max_review_iterations: int
    pm_retry_count: int
    architect_retry_count: int
    developer_retry_count: int
    needs_revision: bool

    # ==========================================
    # 2. PMO & WBS 자원 관리
    # ==========================================
    factory_mode: str               
    wbs_master_plan_path: str       
    current_sprint_task_id: Optional[str] 
    accumulated_token_usage: int    
    project_name: str               

    # ==========================================
    # 3. 각 에이전트 산출물 메모리
    # ==========================================
    prd: str
    prd_summary: str
    architecture_doc: str
    architecture_summary: str
    tech_spec: str
    tech_spec_summary: str
    frontend_code: str
    frontend_code_summary: str
    backend_code: str
    backend_code_summary: str
    code_review_report: str
    code_review_report_summary: str
    qa_report: str
    qa_report_summary: str

    # ==========================================
    # 4. CodeBuilder & 환경 상태
    # ==========================================
    project_output_path: str        
    build_status: str               
    build_error_log: str            
    executable_entry_point: str     
    project_type: str               # [신규] Tech Lead가 명시적으로 선언 ("python" | "node" | "fullstack")


def create_initial_state(**overrides) -> ProjectState:
    """
    파이프라인 초기 상태를 안전하게 생성하는 헬퍼 함수.
    모든 필드에 기본값을 보장하여 런타임 KeyError를 원천 차단합니다.
    """
    defaults: ProjectState = {
        "initial_idea": "",
        "human_feedback_queue": [],
        "pipeline_status": "idle",
        "error_log": "",
        "output_dir": "",
        "review_iteration": 0,
        "max_review_iterations": 1,
        "pm_retry_count": 0,
        "architect_retry_count": 0,
        "developer_retry_count": 0,
        "needs_revision": False,
        
        "factory_mode": "EXECUTION",
        "wbs_master_plan_path": "00_wbs_master_plan.json",
        "current_sprint_task_id": None,
        "accumulated_token_usage": 0,
        "project_name": "",
        
        "prd": "", "prd_summary": "",
        "architecture_doc": "", "architecture_summary": "",
        "tech_spec": "", "tech_spec_summary": "",
        "frontend_code": "", "frontend_code_summary": "",
        "backend_code": "", "backend_code_summary": "",
        "code_review_report": "", "code_review_report_summary": "",
        "qa_report": "", "qa_report_summary": "",
        
        "project_output_path": "",
        "build_status": "pending",
        "build_error_log": "",
        "executable_entry_point": "",
        "project_type": "",
    }
    defaults.update(overrides)
    return defaults