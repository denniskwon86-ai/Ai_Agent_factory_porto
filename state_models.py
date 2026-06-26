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
    model_config = ConfigDict(extra='forbid')
    id: str
    description: str
    priority: int = Field(ge=1, le=5)
    assigned_task: Optional[str] = None

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
                            "stage_scores", "debate_rounds_used")
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
