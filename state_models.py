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
    """아키텍처 결정 기록.

    ⚠️ [2026-07-26 실측 결함] 과거 `extra='forbid'` + 필수 필드 3개(id/decision/reason)로
    엄격했다. LLM 이 ADR 을 `{id, title, description}` 같은 **동의어 키**로 내면
    `ProjectState` 검증이 8개 오류로 실패하고 **스프린트 루프가 통째로 죽었다**
    (`Sprint Loop Error: 8 validation errors for ProjectState`).
    산출물 형태의 사소한 편차가 파이프라인을 죽여선 안 된다 — 형제 모델 `DebtItem` 은
    이미 `extra='ignore'` + 기본값 + before-validator 로 이 문제를 해결하고 있었으므로
    **그 검증된 패턴을 여기에도 적용**한다(동의어 흡수 + 누락 시 기본값)."""
    model_config = ConfigDict(extra='ignore')
    id: str = Field(default="ADR-fallback")
    decision: str = Field(default="")
    reason: str = Field(default="")
    timestamp: str = Field(default_factory=now_utc)

    @model_validator(mode='before')
    @classmethod
    def absorb_synonyms(cls, values):
        """LLM 이 흔히 쓰는 동의어 키를 정규 필드로 흡수한다."""
        if isinstance(values, dict):
            if 'decision' not in values:
                for alt in ('title', 'summary', 'what', 'content'):
                    if values.get(alt):
                        values['decision'] = values[alt]
                        break
            if 'reason' not in values:
                for alt in ('description', 'rationale', 'why', 'reasoning'):
                    if values.get(alt):
                        values['reason'] = values[alt]
                        break
            if not values.get('id'):
                import time
                values['id'] = f"ADR-{int(time.time())}"
        return values

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

    # ── 소유권 (설계서 Phase 3) ──────────────────────────────────────────
    # ⚠️ `extra='forbid'` 이므로 여기에 선언하지 않으면 소유권을 실은 상태가
    #   ValidationError 로 즉사한다. 진실원본은 `project_meta.json` 이고 여기는 주입본이다.
    owner_dept_id: str = Field(default="", description="소유 부서(권한 스코프의 기준)")
    owner_user_id: str = Field(default="", description="개인 소유자(personal 가시성일 때 의미)")
    visibility: str = Field(default="dept", description="dept | company | personal")
    # [D-019] 위 `owner_dept_id` 가 **가리키던 조직 노드**를 기록 시점에 찍어 둔다.
    #   ⚠️ 이것은 `owner_dept_id` 의 대체가 아니라 병기다. 실측상 활성 부서 12개 중 9개가
    #     `node_41402723bc90`(LS_MNM) 하나에 매핑돼 있어 node 만 실으면 부서별 비용이 한 줄로
    #     뭉치고, 반대로 dept 만 실으면 조직개편 뒤 과거 비용을 해석할 수 없다.
    #   ⚠️ **기록 시점 스냅샷이다.** `org_directory.update_department` 가 `scope_node_id` 를
    #     새 버전으로 개정하므로, 나중에 dept→node 를 다시 풀면 과거 비용이 소급해 움직인다.
    #   ⚠️ `owner_dept_id` 에 node_id 를 넣지 말 것 — `knowledge_base` 의 부서 필터가
    #     `get_department(node_id)` → None → 매칭 0건, 즉 과거사례 주입이 **조용히** 끊긴다.
    owner_scope_node_id: str = Field(default="", description="[D-019] 기록 시점의 ECM 조직 노드(해석·롤업용)")
    # [M0-d] 이 프로젝트가 어느 Solution Blueprint 에서 나왔는가(§18-7 추적성).
    #   ⚠️ Blueprint 를 프로젝트 생성으로 연결할 때 링크가 없으면, 나중에 "이 앱이 왜 이런
    #     요구사항을 갖게 됐나"를 되짚을 수 없다(§1.3 기업 의도와 결정의 보존). 상담 없이 만든
    #     프로젝트는 빈 값이다.
    blueprint_id: str = Field(default="", description="출처 Solution Blueprint id (없으면 직접 생성)")
    # [ECM E1/E2 · R-001] 실행 문맥. 기준정보 주입의 **범위 필터 기준**이 된다.
    #   ⚠️ 이 값이 없으면 `master_data.get_master_context()` 가 전체 활성 기준정보를 도메인만 맞으면
    #     주입해 A 법인 기준정보가 B 법인 프롬프트에 섞인다(감사 Finding 1). 진실원본은
    #     `project_meta.json` 이고 여기는 주입본이다.
    tenant_id: str = Field(default="", description="테넌트(ECM) — 비면 기본 테넌트")
    enterprise_scope_id: str = Field(default="", description="조직 범위 — 부서 id 또는 ECM node_id")
    entity_mode: str = Field(default="REAL", description="REAL | VIRTUAL | COMPETITOR_REFERENCE")
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
    
    # ----------------------------------------------------
    # [메가 프로젝트 연동 및 계층화 속성]
    # ----------------------------------------------------
    is_mega_project: bool = Field(default=False, description="이 프로젝트가 여러 서브 프로젝트를 관장하는 마스터인지 여부")
    parent_project_id: str = Field(default="", description="이 프로젝트가 속한 마스터 프로젝트 ID (빈 값이면 최상위)")
    sub_projects_map: Dict[str, str] = Field(default_factory=dict, description="마스터 프로젝트일 경우, 하위 프로젝트 목록 (domain -> project_id)")
    shared_ledger: Dict[str, dict] = Field(default_factory=dict, description="서브 프로젝트 간 공유되는 전사 공통 원장 (이벤트/변수 버스)")
    domain_agents: List[str] = Field(default_factory=list, description="서브 프로젝트에 할당된 실행 에이전트 ID 목록 (비어 있으면 전체 파이프라인 실행)")
    
    factory_mode: Literal["PLANNING", "EXECUTION", "REVISION", "REVIEW", "QA_RELEASE", "HOTL_PAUSED", "SUSPENDED_QUOTA"] = Field(default="PLANNING")
    # 쿼터 완전 고갈로 SUSPENDED_QUOTA 로 전환하기 직전의 정상 모드를 보존한다.
    # 쿼터 회복 후 재개(resume) 시 이 값으로 factory_mode 를 정확히 복구해야
    # 이후 HOTL 게이트 감지(is_hotl_pending)가 정상 동작한다(SUSPENDED 는 항상 HOTL=False 이므로).
    pre_suspend_mode: str = Field(default="")
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

    # ══════════════════════════════════════════════════════════════════════════
    # ★ [2026-07-27 신설] 업무 종료 상태 (terminal status)
    # ══════════════════════════════════════════════════════════════════════════
    # ⚠️ 왜 필요한가 (실측 결함):
    #   LangGraph 의 `END` 는 "그래프가 더 진행할 노드가 없다"는 **기술적 사실**일 뿐
    #   성공을 뜻하지 않는다. 그런데 `async_orchestrator` 는 빌드 3회 실패만 걸러내고
    #   **그 외 모든 END 를 WBS `DONE` 으로 마킹**했다.
    #   실측: E2E-01 이 리뷰 재작업 상한에서 `best-effort 수용` 된 뒤 `DONE` 이 됐다.
    #   즉 미해결 결함을 안고 '완료'로 보이는 **가짜 통과**가 구조적으로 가능했다.
    # → WBS 상태와 UI 는 `END` 가 아니라 이 필드를 기준으로 결정해야 한다.
    #   `""`(빈 값) = 아직 종결되지 않음(진행 중).
    terminal_status: Literal[
        "", "COMPLETED",
        "FAILED_BUILD",                 # 자가복구 소진 — 코드가 끝내 빌드되지 않음
        "FAILED_REVIEW",                # 리뷰 왕복 상한 — 미해결 결함이 남음
        "FAILED_GENERATION_CONTRACT",   # 구조화 출력 절단·출력 예산 부족 (코드 결함 아님)
        "REJECTED_ACCEPTANCE",          # 수용검수 반려
        "SUSPENDED_QUOTA",              # 할당량 소진 — 회복 후 재개 가능
        "SUSPENDED_PROVIDER",           # 공급자 타임아웃/네트워크 — 코드 결함 아님
        "CANCELLED",
    ] = Field(default="")
    terminal_reason: str = Field(default="")     # 사람이 읽을 종결 사유
    failure_bundle_path: str = Field(default="") # 실패 번들(재현 근거) 저장 경로

    # 이원화 피드백 루프 상태
    reviewer_decision: str = Field(default="NONE")  # "PASS", "REWORK_DEV", "ESCALATE_PM"
    reviewer_feedback: str = Field(default="")
    # ★ [2026-07-27] 리뷰어 판정 이력. 리뷰어가 **자기 이전 판정을 기억하지 못해** 같은 지적을
    #   반복하며 재작업 예산을 소진하던 결함을 막는다(실측: 동일 지적 8회 반복 → FAILED_REVIEW).
    #   이 이력을 프롬프트에 되돌려주고, 반복이 감지되면 ESCALATE_PM 으로 자동 승격한다.
    rework_history: List[str] = Field(default_factory=list)
    # [VisionQA 자문 강등] VisionQA 는 UI 를 자동 반려하지 않고 '소견'만 남긴다. 사람이 미리보기 +
    # 이 소견을 함께 보고 승인/재설계를 결정한다(왕복 루프 제거 → 무료 티어 콜 폭발 방지).
    ui_review_advisory: str = Field(default="")
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
    ui_mockup_summary: str = Field(default="")
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

    # 요구 확인 인터뷰(RFP 이전 게이트): 에이전트가 생성한 선택형 질문 목록과,
    # 사용자가 선택으로 답한 결과 요약(RFP/PRD 작성 시 입력으로 주입·참조)
    clarification_questions: List[Dict] = Field(default_factory=list)
    clarification_summary: str = Field(default="")

    # 시뮬레이션 재실행(What-if) 추적 - resimulate API 가 주입(extra='forbid'라 정식 필드 필요)
    sim_cycle_count: int = Field(default=1, ge=1)
    sim_modified_params: Dict = Field(default_factory=dict)
    sim_base_cycle: int = Field(default=1)

    # 이 프로젝트에 연결된 도메인 지식팩(그라운딩 RAG) - project_meta 가 진실원본, 스프린트 시작 시 주입
    knowledge_pack_ids: List[str] = Field(default_factory=list)
    # [M1] 이 프로젝트에 적용할 기준정보(Master Data) 도메인 태그 - project_meta 가 진실원본,
    # 스프린트 시작 시 주입. 결정론적 기준정보 주입(get_master_context)의 도메인 필터로 쓰인다.
    master_domains: List[str] = Field(default_factory=list)
    # [M3] 외부 실측값(MCP 브로커) 병기 토글. 기본 off — 켜면 매 LLM 호출에 활성 연계 시스템의
    # 승인 매핑을 온디맨드 조회해 '참고(비신뢰)' 블록으로 병기(지연·쿼터·신뢰 리스크가 있어 명시 옵트인).
    mcp_live_grounding: bool = Field(default=False)

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
                            "criteria_log", "current_required_agents", "clarification_questions",
                            "knowledge_pack_ids", "master_domains")
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
