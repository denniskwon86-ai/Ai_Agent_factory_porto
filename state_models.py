from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime, timezone

#: ★★★ 파이프라인 상태 계약의 버전. **문자열을 다른 곳에 적지 않는다** — 반복하면
#: 한 곳만 고치는 날이 오고, 그때 두 값이 갈라진다.
#:
#: ⚠️ `main.py` 의 FastAPI `version=` 은 **다른 계약**이다(API 버전). 같은 숫자로 묶으면
#:   이후 한쪽만 올릴 수 없게 된다.
#: ⚠️ `app_runtime_contract.SCHEMA_VERSION`(계약 문서 형식)과도 다른 것이다.
PROJECT_STATE_SCHEMA_VERSION = "5.3.0"

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_version(raw: Any) -> Optional[Tuple[int, int, int]]:
    """`X.Y.Z` → 튜플. 모양이 아니면 `None`(패턴 검증이 그 자리에서 말하게 둔다)."""
    parts = str(raw or "").strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return None

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
    schema_version: str = Field(default=PROJECT_STATE_SCHEMA_VERSION,
                                pattern=r"^\d+\.\d+\.\d+$")
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
    # 서버가 계산한 워크플로우 의미 지문. 클라이언트 입력이 아니라 프로젝트 결속에서 주입한다.
    config_fingerprint: str = Field(default="")
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
        # ★ [I-4 4c-6] 계약이 없거나 합산이 막혀 빌드로 넘어갈 수 없다.
        #   ⚠️ `FAILED_GENERATION_CONTRACT`(구조화 출력 절단)와 **다른 것**이다. 뭉개면
        #     「모델이 형식을 못 맞췄다」와 「사람이 계약을 정해야 한다」가 같은 화면이
        #     되고, 사용자는 재시도만 반복한다.
        "CONTRACT_BLOCKED",
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

    # ── [I-4] App Runtime Contract (5.2.0) ──────────────────────────────
    # ⚠️ `extra='forbid'` 이므로 여기에 선언하지 않으면 Compiler 가 계약을 산출해도
    #   상태가 그것을 **조용히 버린다**.
    # ★ 계약 **원문은 workspace 파일이 정본**이고 여기에는 요약·상태·지문만 둔다 —
    #   원문을 상태에 실으면 체크포인터가 매 단계 그것을 복사하고, 커지는 상태는 재개를
    #   느리게 만든다(그리고 언젠가 잘린다).
    capability_intents: List[Dict[str, Any]] = Field(default_factory=list)
    app_runtime_contract_status: str = Field(default="")      # DRAFT|COMPILED|APPROVED
    app_runtime_contract_fingerprint: str = Field(default="")
    app_runtime_contract_summary: str = Field(default="")     # 사람이 읽는 요약
    unsupported_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    approved_contract_fingerprint: str = Field(default="")    # 게이트가 비교하는 값
    # ★★★ [I-4 §3] 계약 절차의 **영속 opt-in.** `""`(적용 안 함) 또는 `"v1"`.
    #
    # ⚠️⚠️ **기본값을 절대 `"v1"` 으로 두지 않는다.** 여기서 기본을 켜면 이미 돌고
    #   있는 모든 프로젝트가 상태를 읽는 순간 새 절차를 타고, 그 어긋남은 «재개할
    #   때에야» 드러난다 — 원인을 찾기 가장 어려운 시점이다.
    # ★ 값은 `project_meta.json` 이 정본이고 `start_sprint` 가 주입한다. 프론트가
    #   보낸 값을 믿지 않는다 — 오래 열린 브라우저가 상태를 바꾸는 경로를 만들지
    #   않는다(`schema_version` 을 서버가 부여하는 것과 같은 이유).
    runtime_contract_profile: str = Field(default="")
    # ★ [I-4 4c-2] 열린 계약 검토 요청의 이벤트 id — **캐시다.**
    #
    # ⚠️⚠️ 정본은 Decision Ledger 다. 이 값만 보고 「요청이 있다/없다」를 판정하면,
    #   체크포인트 저장이 실패한 순간 요청이 두 건 생기고 승인이 어느 쪽에 붙었는지
    #   아무도 답할 수 없다. 판정은 언제나 원장에서 다시 찾는다.
    # ⚠️ 클라이언트가 이 값을 정하지 못한다 — 서버가 부여한다(`schema_version` 과 같다).
    contract_review_request_event_id: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _migrate_schema_version(cls, data):
        """★★★ 지연 마이그레이션 — 읽을 때 승격한다(기존 파일을 일괄 재작성하지 않는다).

        · **버전 없음** → 구버전으로 간주해 승격한다. 「구버전이라 계약 필드가 없는 상태」와
          「신버전인데 데이터셋 0개인 정상 계약 상태」는 **전혀 다른 사실**이고, 버전을
          기록해야 그 둘이 구분된다.
        · 새 필드는 선언된 기본값이 채운다(여기서 채워 넣지 않는다 — 기본값이 두 곳이 된다).
        · ⚠️⚠️ **미래 버전은 조용히 읽지 않는다.** 모르는 계약을 추측해 읽으면 그 추측이 곧
          데이터 손상이다 — 필드 하나를 잘못 해석한 상태가 저장되면 원본은 사라진다."""
        if not isinstance(data, dict):
            return data
        raw = data.get("schema_version")
        current = _parse_version(PROJECT_STATE_SCHEMA_VERSION)
        if raw is None or not str(raw).strip():
            data["schema_version"] = PROJECT_STATE_SCHEMA_VERSION
            return data
        parsed = _parse_version(raw)
        if parsed is None:
            return data  # 모양이 아니다 → 패턴 검증이 명확히 거부한다
        if parsed > current:  # type: ignore[operator]
            raise ValueError(
                f"상태 스키마 {raw} 는 이 빌드({PROJECT_STATE_SCHEMA_VERSION})보다 새 계약입니다 "
                f"— 추측해 읽지 않습니다. 최신 빌드로 열어 주십시오.")
        if parsed < current:  # type: ignore[operator]
            data["schema_version"] = PROJECT_STATE_SCHEMA_VERSION
        return data

    @model_validator(mode="before")
    @classmethod
    def _coerce_none_collections(cls, data):
        # 부분 저장/레거시 상태에서 컬렉션 필드가 null로 들어와도 기본값으로 보정 (검증 크래시 방지)
        if isinstance(data, dict):
            none_to_list = ("architecture_decisions", "technical_debt", "human_feedback_queue",
                            "criteria_log", "current_required_agents", "clarification_questions",
                            "knowledge_pack_ids", "master_domains",
                            "capability_intents", "unsupported_requirements")
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
