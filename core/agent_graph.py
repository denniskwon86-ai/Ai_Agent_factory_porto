import os
import json
import asyncio
import config
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state_models import ProjectState

from nodes.planning import run_rfp_analyst, run_master_pm, run_master_pmo
from nodes.execution import (
    run_architect,
    run_tech_lead,
    run_developer_fe,
    run_developer_be,
    run_code_builder,
    run_supervisor,
    run_qa,
    run_manual_writer
)

# 요구 에이전트 명단 정규화: 별칭(영문 키워드/한글) → 정규 노드 id.
# PMO 는 정규 영문 id(Architect/Tech_Lead/Backend/Frontend/Reviewer/QA)를 내도록 지시받지만,
# 간헐적 비정형 출력에 대비해 정규화 후 '정확 id 일치'로 라우팅한다(substring 오탐 제거).
_AGENT_ALIASES = {
    "Architect": ("architect", "아키"),
    "Tech_Lead": ("tech_lead", "techlead", "tech lead", "테크", "기술"),
    "Backend": ("backend", "백엔드"),
    "Frontend": ("frontend", "프론트"),
    "QA": ("qa", "품질", "테스트"),
    "Reviewer": ("reviewer", "리뷰", "검수"),
    "RFP_Analyst": ("rfp_analyst", "rfp", "요구"),
    "Master_PM": ("master_pm", "기획"),
    "Master_PMO": ("master_pmo", "pmo", "wbs"),
    "CodeBuilder": ("codebuilder", "code_builder", "빌더"),
    "ManualWriter": ("manualwriter", "manual_writer", "manual", "매뉴얼"),
}
_CANON_IDS = set(_AGENT_ALIASES.keys())


def _canonicalize(raw: str) -> str:
    """단일 요구 에이전트 문자열 → 정규 노드 id. 정규 id 면 그대로, 별칭이면 매핑, 미상이면 원문 유지(보수)."""
    if not raw:
        return raw
    s = str(raw).strip()
    if s in _CANON_IDS:  # 이미 정규 id (PMO 정상 출력) → 별칭 검사 생략(오탐 방지)
        return s
    low = s.lower()
    for cid, aliases in _AGENT_ALIASES.items():
        if low == cid.lower() or any(al in low for al in aliases):
            return cid
    return s


def _normalize_agents(raw_list) -> list:
    seen, out = set(), []
    for r in (raw_list or []):
        c = _canonicalize(r)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _get_required_agents(state: ProjectState) -> list:
    agents = []
    try:
        wbs_path = os.path.join(state.workspace_root, "00_wbs_master_plan.json")
        if os.path.exists(wbs_path):
            with open(wbs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for t in data.get("tasks", []):
                    if t.get("task_id") == state.current_sprint_task_id:
                        agents = t.get("required_agents", [])
                        break
    except Exception:
        pass

    # 🚨 [치명적 버그 수정] 피드백(Revision) 생성 시 WBS 투입 명단이 비어버리는 현상 완벽 방어
    # agents가 비어있으면 AI가 코딩을 건너뛰는 사태를 막기 위해 강제로 개발 요원을 투입합니다.
    if not agents or len(agents) == 0:
        agents = getattr(state, "current_required_agents", [])

    if not agents or len(agents) == 0:
        agents = ["Architect", "Tech_Lead", "Backend", "Frontend", "QA"]

    # 정규 id 로 정규화 → 라우터의 정확 일치(_has_role) 입력
    return _normalize_agents(agents)


def _has_role(agents: list, role_en: str, role_ko: str = "") -> bool:
    # agents 는 _normalize_agents 로 정규화된 정규 id 목록 → 정확 일치(substring 오탐 제거).
    # role_en 은 항상 정규 id(Architect/Tech_Lead/Backend/Frontend/QA 등). role_ko 는 하위호환용 미사용.
    return role_en in (agents or [])

def _is_final_task(state: ProjectState) -> bool:
    """현재 시점에 WBS의 모든 태스크가 DONE인지(=마지막 태스크가 방금 완료됐는지) 확인.
    QA(최종 통합 검증)를 WBS 매핑과 무관하게 마지막 단계에서 자동 실행하기 위함."""
    try:
        wbs_path = os.path.join(state.workspace_root, "00_wbs_master_plan.json")
        if not os.path.exists(wbs_path):
            return False
        with open(wbs_path, "r", encoding="utf-8") as f:
            tasks = json.load(f).get("tasks", []) or []
        if not tasks:
            return False
        # 리비전(TASK_REV_*)은 후속 작업 유무 판단에서 제외하고 본 태스크 기준으로 본다
        core = [t for t in tasks if not str(t.get("task_id", "")).startswith("TASK_REV_")]
        target = core or tasks
        return all(t.get("status") == "DONE" for t in target)
    except Exception:
        return False

def _route_to_first_assigned(agents: list, include_design: bool = True) -> str:
    """배정된 에이전트 명단에서 파이프라인 순서상 첫 실행 대상 노드를 고른다."""
    if include_design:
        if _has_role(agents, "Architect", "아키"): return "Architect"
        if _has_role(agents, "Tech_Lead", "테크") or _has_role(agents, "Tech_Lead", "기술"): return "Tech_Lead"
    if _has_role(agents, "Backend", "백엔드"): return "Backend"
    if _has_role(agents, "Frontend", "프론트"): return "Frontend"
    return "CodeBuilder"

def route_factory_mode(state: ProjectState) -> str:
    if state.factory_mode == "PLANNING": return "RFP_Analyst"
    elif state.factory_mode == "REVISION": return "Tech_Lead"
    # EXECUTION: 태스크에 배정된 에이전트 기준으로 진입 (설계 재사용 — 미배정 시 Architect/Tech_Lead 생략)
    return _route_to_first_assigned(_get_required_agents(state), include_design=True)

def route_from_architect(state: ProjectState) -> str:
    # Architect 완료 후, 배정된 다음 에이전트로 (Tech_Lead 미배정 시 생략)
    return _route_to_first_assigned(_get_required_agents(state), include_design=False) \
        if not _has_role(_get_required_agents(state), "Tech_Lead", "테크") \
        else "Tech_Lead"

def route_from_tech_lead(state: ProjectState) -> str:
    agents = _get_required_agents(state)
    if _has_role(agents, "Backend", "백엔드"): return "Backend"
    if _has_role(agents, "Frontend", "프론트"): return "Frontend"
    return "CodeBuilder"

def route_from_backend(state: ProjectState) -> str:
    agents = _get_required_agents(state)
    if _has_role(agents, "Frontend", "프론트"): return "Frontend"
    return "CodeBuilder"

def map_builder_router(state: ProjectState) -> str:
    if state.build_status == "failed":
        if state.developer_retry_count < 3:
            failed_target = state.failed_node
            allowed_agents = _get_required_agents(state)
            
            if failed_target == "Backend" and _has_role(allowed_agents, "Backend", "백엔드"):
                print("🔄 [Circuit Breaker] 빌드 실패. Backend 담당자에게 수정을 지시합니다.")
                return "Backend"
            elif failed_target == "Frontend" and _has_role(allowed_agents, "Frontend", "프론트"):
                print("🔄 [Circuit Breaker] 빌드 실패. Frontend 담당자에게 수정을 지시합니다.")
                return "Frontend"
            else:
                return "Reviewer"
        else:
            print("🚨 [Circuit Breaker] 최대 재시도 초과. 파이프라인 일시정지.")
            return END 
    return "Reviewer"

def route_from_reviewer(state: ProjectState) -> str:
    decision = getattr(state, "reviewer_decision", "PASS")

    # 🚦 무한루프 차단: 리뷰 의사결정 왕복(ESCALATE_PM/REWORK_DEV)이 전역 상한 도달 시 강제 종료
    hops = getattr(state, "supervisor_hops", 0)
    if decision in ("ESCALATE_PM", "REWORK_DEV") and hops >= config.GLOBAL_MAX_SUPERVISOR_HOPS:
        print(f"🚨 [Supervisor Circuit Breaker] 리뷰 의사결정 왕복 {hops}회 도달(상한 {config.GLOBAL_MAX_SUPERVISOR_HOPS}) — 무한 루프 차단, 파이프라인 정지(END).")
        return END

    if decision == "ESCALATE_PM":
        print("🔙 [PM 상신 루프] 기획적 모순 발견. PM에게 최종 판단을 받으러 갑니다.")
        return "Master_PM"
    elif decision == "REWORK_DEV":
        print("🔙 [실무 재작업 루프] 코드/설계 결함 발견. Tech Lead에게 재설계 및 코딩 재작업을 지시합니다.")
        return "Tech_Lead"
        
    agents = _get_required_agents(state)
    # QA는 ① 태스크에 명시 배정됐거나 ② 프로젝트 마지막 태스크가 완료된 시점(최종 통합 검증)에 자동 실행
    if _has_role(agents, "QA", "QA") or _has_role(agents, "QA", "테스트"):
        return "QA"
    if _is_final_task(state):
        print("🧪 [최종 통합 검증] 모든 WBS 태스크 완료 — QA를 자동 투입합니다 (WBS 미배정이어도 실행).")
        return "QA"
    return "ManualWriter"

def route_from_pm(state: ProjectState) -> str:
    if not state.current_sprint_task_id:
        return "Master_PMO"
    
    if getattr(state, "needs_revision", False):
        print("⏩ [의사결정 완료] PM이 기획서를 수정했습니다. Tech Lead에게 변경된 설계 반영을 지시합니다.")
        return "Tech_Lead" 
        
    print("⏩ [의사결정 완료] PM이 강행을 지시했습니다. Reviewer에게 강제 승인을 지시합니다.")
    return "Reviewer"

# 레지스트리 id → 노드 구현 함수. 레지스트리가 노드 멤버십을 구동하기 위한 seam.
# (모든 레지스트리 에이전트 id 를 커버해야 동적 빌더가 임의 enabled 집합을 생성 가능)
NODE_IMPL = {
    "RFP_Analyst": run_rfp_analyst,
    "Master_PM": run_master_pm,
    "Master_PMO": run_master_pmo,
    "Architect": run_architect,
    "Tech_Lead": run_tech_lead,
    "Backend": run_developer_be,
    "Frontend": run_developer_fe,
    "CodeBuilder": run_code_builder,
    "Reviewer": run_supervisor,
    "QA": run_qa,
    "ManualWriter": run_manual_writer,
}


def _wire_edges(workflow):
    """현 SW 파이프라인의 엣지/라우터 구조.
    (b)-1 동작 보존: 하드코딩 유지. (b)-2 에서 레지스트리 order/category 기반 데이터 구동으로 전환 예정.
    (상태 구동 결정 라우터 — include_design·역방향 수렴·QA 자동투입·빌드실패 되돌림 — 은 함수 로직 유지)"""
    workflow.set_conditional_entry_point(
        route_factory_mode,
        {
            "RFP_Analyst": "RFP_Analyst", "Master_PM": "Master_PM", "Tech_Lead": "Tech_Lead", "Architect": "Architect",
            "Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"
        }
    )
    workflow.add_edge("RFP_Analyst", "Master_PM")
    workflow.add_conditional_edges("Master_PM", route_from_pm, {"Master_PMO": "Master_PMO", "Tech_Lead": "Tech_Lead", "Reviewer": "Reviewer"})
    workflow.add_edge("Master_PMO", END)

    workflow.add_conditional_edges("Architect", route_from_architect, {"Tech_Lead": "Tech_Lead", "Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    workflow.add_conditional_edges("Tech_Lead", route_from_tech_lead, {"Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    workflow.add_conditional_edges("Backend", route_from_backend, {"Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    workflow.add_edge("Frontend", "CodeBuilder")
    workflow.add_conditional_edges("CodeBuilder", map_builder_router, {"Frontend": "Frontend", "Backend": "Backend", "Reviewer": "Reviewer", END: END})

    workflow.add_conditional_edges("Reviewer", route_from_reviewer, {"QA": "QA", "ManualWriter": "ManualWriter", "Master_PM": "Master_PM", "Tech_Lead": "Tech_Lead", END: END})
    workflow.add_edge("QA", "ManualWriter")
    workflow.add_edge("ManualWriter", END)


def build_graph_from_registry(registry=None):
    """레지스트리의 enabled 에이전트 id 로 노드를 생성(NODE_IMPL 매핑)하고, 엣지/라우터와
    interrupt_after(hotl_after) 를 적용해 (workflow, interrupt_after) 반환.

    (b)-1 동작 보존: DEFAULT_REGISTRY(전부 enabled)에서는 기존 하드코딩 토폴로지와 동일하다.
    엣지는 아직 _wire_edges 하드코딩이므로, enabled 에서 노드를 빼는 것은 (b)-2 에서 엣지 데이터화와
    함께 지원한다(현재 임의 비활성화는 dangling edge 로 compile 실패할 수 있음)."""
    from core.agent_registry import load_registry, get_interrupt_after
    reg = registry or load_registry()
    enabled_ids = [a["id"] for a in reg.get("agents", []) if a.get("enabled", True)]

    workflow = StateGraph(ProjectState)
    for aid in enabled_ids:
        impl = NODE_IMPL.get(aid)
        if impl is not None:
            workflow.add_node(aid, impl)

    _wire_edges(workflow)

    # HOTL 중단점 = 레지스트리 hotl_after(enabled 노드로 한정). 손상/부재 시 기존 기본값 폴백.
    interrupt_after = [i for i in get_interrupt_after(default=["RFP_Analyst", "Master_PMO", "Tech_Lead"]) if i in enabled_ids]
    return workflow, interrupt_after


def _build_workflow():
    """토폴로지 빌더 진입점 — 레지스트리 구동(build_graph_from_registry)으로 위임.
    create_factory_graph(studio/테스트)와 get_runtime_app(런타임 영속)이 공유한다."""
    return build_graph_from_registry()


def create_factory_graph():
    """동기 컴파일(MemorySaver) — LangGraph Studio/langgraph.json 및 단위 테스트용.
    런타임(오케스트레이터)은 재시작 내성을 위해 영속 체크포인터를 쓰는 get_runtime_app()을 사용한다."""
    workflow, interrupt_after = _build_workflow()
    return workflow.compile(checkpointer=MemorySaver(), interrupt_after=interrupt_after)


# 스튜디오/langgraph.json/테스트용 동기 인스턴스(휘발성). 런타임은 get_runtime_app() 사용.
app = create_factory_graph()


# ── 런타임 전용 영속 체크포인터 그래프 (재시작 내성) ──────────────────────────────
# AsyncSqliteSaver 는 생성 시 실행 중 이벤트루프가 필요하므로 모듈 import 시점엔 만들 수 없다.
# → 첫 호출(오케스트레이터의 async 컨텍스트) 때 1회 lazy compile 하고 캐시한다.
_runtime_app = None
_runtime_lock = asyncio.Lock()


async def _build_runtime_app(db_path: str):
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    conn = await aiosqlite.connect(db_path, check_same_thread=False)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    workflow, interrupt_after = _build_workflow()
    return workflow.compile(checkpointer=saver, interrupt_after=interrupt_after)


async def get_runtime_app():
    """오케스트레이터용 그래프(영속 체크포인터=SQLite). 첫 호출 시 이벤트루프 내에서 1회 compile·캐시.
    → 서버 재시작 시에도 HOTL 대기 체크포인트가 디스크에 보존되어 스프린트 재개가 가능하다."""
    global _runtime_app
    if _runtime_app is not None:
        return _runtime_app
    async with _runtime_lock:
        if _runtime_app is None:
            _runtime_app = await _build_runtime_app(config.PIPELINE_DB_FILE)
    return _runtime_app