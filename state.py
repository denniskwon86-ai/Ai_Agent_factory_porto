from typing import TypedDict, List, Optional

class ProjectState(TypedDict):
    # ==========================================
    # 1. 기존 공통 상태 및 파이프라인 제어
    # ==========================================
    initial_idea: str
    human_feedback_queue: List[str]
    
    pipeline_status: str
    error_log: str
    output_dir: str             # [복구 완료] 파일 저장 물리 경로 (WinError 3 해결 핵심)
    
    review_iteration: int
    max_review_iterations: int
    pm_retry_count: int         
    architect_retry_count: int  
    developer_retry_count: int  # 빌드 자동 피드백 루프 카운터
    needs_revision: bool        

    # ==========================================
    # 2. [신규 추가] PMO & WBS 자원 관리 (투 트랙 아키텍처)
    # ==========================================
    factory_mode: str               # "PLANNING" (마스터플랜) | "EXECUTION" (스프린트 가동)
    wbs_master_plan_path: str       # WBS JSON 파일 경로
    current_sprint_task_id: Optional[str] # 현재 가동 중인 Task ID (thread_id로 사용)
    accumulated_token_usage: int    # 누적 토큰 사용량 (대시보드 예산 추적용)
    project_name: str               # 프로젝트 명칭

    # ==========================================
    # 3. 각 에이전트 산출물 및 요약 메모리
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
    # 4. CodeBuilderNode 물리적 빌드 상태
    # ==========================================
    project_output_path: str        # 생성된 실제 프로젝트 경로 (outputs/TIMESTAMP/workspace)
    build_status: str               # "success" | "failed" | "pending"
    build_error_log: str            # 빌드 실패 시 에러 로그 (Dev 에이전트 피드백용)
    executable_entry_point: str     # 실행 진입점 경로