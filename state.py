import operator
from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import BaseMessage

class ProjectState(TypedDict):
    """
    범용 다중 에이전트 소프트웨어 팩토리(v3.2) 상태 메모리 객체
    LangGraph의 SqliteSaver와 결합하여 체크포인터에 영구 저장됩니다.
    """
    
    # ---------------------------------------------------------
    # 1. LangGraph 코어 메시지 버스
    # ---------------------------------------------------------
    messages: Annotated[List[BaseMessage], operator.add]

    # ---------------------------------------------------------
    # 2. [신규] PMO & WBS 자원 관리 (투 트랙 아키텍처)
    # ---------------------------------------------------------
    factory_mode: str               # "PLANNING" (마스터플랜 수립 모드) | "EXECUTION" (스프린트 가동 모드)
    wbs_master_plan_path: str       # WBS JSON 파일 물리 경로 (기본값: "00_wbs_master_plan.json")
    current_sprint_task_id: Optional[str]  # 현재 가동 중인 태스크 ID (예: "E2E-01"). thread_id로도 사용됨
    accumulated_token_usage: int    # 파이프라인 누적 토큰 사용량 (TPM 한도 방어 및 예산 추적용)

    # ---------------------------------------------------------
    # 3. 프로젝트 메타데이터
    # ---------------------------------------------------------
    project_name: str               # 프로젝트 명칭 (예: "제조업 E2E 경영 시뮬레이터")
    project_output_path: str        # 코드가 물리적으로 생성될 루트 디렉토리

    # ---------------------------------------------------------
    # 4. [기존] Code Builder 자가 치유(Self-Healing) 인프라
    # ---------------------------------------------------------
    # 라우터 증발 버그를 해결하고 물리 노드에서 영구 기억하도록 밖으로 빼낸 카운터
    developer_retry_count: int      
    build_status: str               # "pending" | "success" | "failed"
    build_error_log: str            # Head+Tail 기법으로 압축된 에러 로그 (컨텍스트 슬라이싱)
    executable_entry_point: str     # 컴파일 검증을 위한 진입점 파일 (예: "main.py", "index.js")