from typing import TypedDict, List

class ProjectState(TypedDict):
    initial_idea: str
    human_feedback_queue: List[str]
    
    pipeline_status: str
    error_log: str
    output_dir: str
    
    review_iteration: int
    max_review_iterations: int
    pm_retry_count: int         
    architect_retry_count: int  
    developer_retry_count: int  # [신규] 빌드 자동 피드백 루프 카운터
    needs_revision: bool        
    
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
    # CodeBuilderNode 관련 신규 필드
    # ==========================================
    project_output_path: str        # 생성된 실제 프로젝트 경로 (outputs/TIMESTAMP/workspace)
    build_status: str               # "success" | "failed" | "pending"
    build_error_log: str            # 빌드 실패 시 에러 로그 (Dev 에이전트 피드백용)
    executable_entry_point: str     # 실행 진입점 경로