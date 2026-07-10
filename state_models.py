from __future__ import annotations
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime, timezone

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

class GitInfo(BaseModel):
    model_config = ConfigDict(extra='forbid')
    branch: str = Field(default="dev")
    last_commit_hash: str = Field(default="")
    last_commit_timestamp: str = Field(default="")
    last_commit_task: str = Field(default="")

class FileMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str
    last_modified_agent: str = Field(default="system")
    last_modified_task: str = Field(default="unknown")
    last_modified_at: str = Field(default_factory=now_utc)
    change_summary: str = Field(default="")
    purpose: str = Field(default="")
    last_hash: str = Field(default="")
    dependencies: List[str] = Field(default_factory=list)

class DebtItem(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str = Field(default_factory=lambda: f"DEBT-fallback")
    description: str = Field(default="")
    priority: int = Field(default=3, ge=1, le=5)
    assigned_task: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def populate_desc(cls, values):
        if isinstance(values, dict):
            if 'content' in values and 'description' not in values:
                values['description'] = values['content']
            if 'id' not in values:
                import time
                values['id'] = f"DEBT-{int(time.time())}"
        return values

class ADR(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    decision: str
    reason: str
    timestamp: str = Field(default_factory=now_utc)

class AgentMemory(BaseModel):
    model_config = ConfigDict(extra='forbid')
    last_thought: str = Field(default="")
    success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    context_shortcuts: Dict[str, str] = Field(default_factory=dict)

class FeedbackItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str
    feedback: str
    priority: int = Field(default=3)
    status: Literal["pending", "applied", "rejected"] = Field(default="pending")

class ProjectState(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    schema_version: str = Field(default="5.1.0", pattern=r"^\d+\.\d+\.\d+$")
    project_name: str = Field(default="New Project")
    initial_idea: str = Field(default="")
    master_data: str = Field(default="", description="전사 통합 환경변수 및 제약사항 (마스터 데이터)")
    # 범용 플랫폼(T2-b): 이 프로젝트가 실행될 워크플로우 템플릿 id(레지스트리/그래프/스킬 해석의 기준).
    # "default" = 기존 SW 파이프라인(하위호환). 노드는 이 값으로 자기 스킬/그래프를 해석한다.
    template_id: str = Field(default="default")
    output_format_id: str = Field(default="default")
    view_type: str = Field(default="react_app")
    # 범용 노드(T3): 커스텀 에이전트 파이프라인의 단계별 산출물 저장소(<agent_id> → 텍스트).
    # SW 파이프라인은 전용 *_summary 필드를 쓰고 이 필드는 비어 있다(추가 전용·하위호환).
    artifacts: Dict[str, str] = Field(default_factory=dict)
    artifact_summaries: Dict[str, str] = Field(default_factory=dict)
    factory_mode: Literal["PLANNING", "EXECUTION", "REVISION", "REVIEW", "QA_RELEASE", "HOTL_PAUSED"] = Field(default="PLANNING")
    workspace_root: str = Field(default="./workspace")
    git_info: GitInfo = Field(default_factory=GitInfo)
    workspace_hash: str = Field(default="")
    file_index: Dict[str, FileMetadata] = Field(default_factory=dict)
    current_sprint: int = Field(default=1, ge=1)
    current_sprint_task_id: str = Field(default="")
    current_required_agents: List[str] = Field(default_factory=list)

    # 빌드 상태
    build_status: Literal["pending", "success", "failed"] = Field(default="pending")
    build_error_log: str = Field(default="")
    developer_retry_count: int = Field(default=0, ge=0)
    failed_node: str = Field(default="")
    supervisor_hops: int = Field(default=0, ge=0)  # 리뷰 의사결정 왕복 횟수(무한루프 차단용 — GLOBAL_MAX_SUPERVISOR_HOPS)

    # 이원화 피드백 루프 상태
    reviewer_decision: str = Field(default="NONE")  # "PASS", "REWORK_DEV", "ESCALATE_PM"
    reviewer_feedback: str = Field(default="")
    pm_override_reason: str = Field(default="")
    needs_revision: bool = Field(default=False)

    # 설계 아티팩트
    architecture_decisions: List[ADR] = Field(default_factory=list)
    technical_debt: List[DebtItem] = Field(default_factory=list)
    agent_memories: Dict[str, AgentMemory] = Field(default_factory=dict)

    # 에이전트 산출물 요약
    rfp_summary: str = Field(default="")  # 요구사항 정의서(RFP) — 기획·QA의 기준 계약
    prd_summary: str = Field(default="")
    architecture_summary: str = Field(default="")
    tech_spec_summary: str = Field(default="")
    frontend_code_summary: str = Field(default="")
    backend_code_summary: str = Field(default="")
    code_review_report_summary: str = Field(default="")
    qa_report_summary: str = Field(default="")
    qa_verdict: str = Field(default="")  # QA(수행사 통합검수) 판정: "" | "PASS" | "FAIL"
    supervisor_report_summary: str = Field(default="")  # 고객사 대리인 최종 수용검수 리포트
    supervisor_verdict: str = Field(default="")  # 최종 수용검수 판정: "" | "PASS" | "REJECT" (완료/배포 게이트)
    user_manual_summary: str = Field(default="")

    human_feedback_queue: List[FeedbackItem] = Field(default_factory=list)

    # 토론·합의 루프 / 단계별 성공기준 / Supervisor (V5.1)
    current_stage: str = Field(default="")  # PLANNING/PMO/ARCHITECTURE/TECH_SPEC/CODE_REVIEW/QA
    stage_attempt_counts: Dict[str, int] = Field(default_factory=dict)
    stage_scores: Dict[str, float] = Field(default_factory=dict)
    debate_rounds_used: Dict[str, int] = Field(default_factory=dict)
    supervisor_feedback: str = Field(default="")
    criteria_log: List[Dict] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_none_collections(cls, data):
        # 부분 저장/레거시 상태에서 컬렉션 필드가 null로 들어와도 기본값으로 보정 (검증 크래시 방지)
        if isinstance(data, dict):
            none_to_list = ("architecture_decisions", "technical_debt", "human_feedback_queue",
                            "criteria_log", "current_required_agents")
            none_to_dict = ("file_index", "agent_memories", "stage_attempt_counts",
                            "stage_scores", "debate_rounds_used", "artifacts", "artifact_summaries")
            for k in none_to_list:
                if data.get(k, "skip") is None:
                    data[k] = []
            for k in none_to_dict:
                if data.get(k, "skip") is None:
                    data[k] = {}
        return data

    @classmethod
    def create_initial_state(cls, **kwargs) -> ProjectState:
        return cls(**kwargs)
