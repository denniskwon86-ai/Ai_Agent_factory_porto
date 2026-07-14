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
    run_reviewer,
    run_qa,
    run_supervisor,
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
    # 비최종 태스크는 여기서 스프린트 종료(END). 매뉴얼은 최종 태스크의 QA 직후(QA→ManualWriter)에만 1회 작성.
    print("✅ [태스크 완료] 비최종 태스크 — 스프린트 종료(매뉴얼은 마지막에 한 번만 작성).")
    return END

def route_from_pm(state: ProjectState) -> str:
    if not state.current_sprint_task_id:
        return "UIDesigner"
    
    if getattr(state, "needs_revision", False):
        print("⏩ [의사결정 완료] PM이 기획서를 수정했습니다. Tech Lead에게 변경된 설계 반영을 지시합니다.")
        return "Tech_Lead" 
        
    print("⏩ [의사결정 완료] PM이 강행을 지시했습니다. Reviewer에게 강제 승인을 지시합니다.")
    return "Reviewer"

def route_from_ui_designer(state: ProjectState) -> str:
    if getattr(state, "needs_revision", False):
        print("🔁 [UI 재설계] 사용자 피드백 반영 — UIDesigner 로 되돌려 다시 디자인합니다.")
        return "UIDesigner"
    return "Master_PMO"

def route_from_pmo(state: ProjectState) -> str:
    """WBS(PMO) 게이트 직후 분기: 사용자가 피드백을 줬으면(needs_revision) WBS 재분할을 위해
    Master_PMO 로 되돌리고, 승인(피드백 없음)이면 종결 노드(WBS_Approved)로 진행.
    ⚠️ 승인 경로를 END 로 직접 두면 interrupt_after 가 '멈출 다음 노드'가 없어 HOTL 일시정지가
    생기지 않는다(=WBS 승인 게이트가 작동 안 함). 실제 노드(WBS_Approved)로 보내야 게이트가 멈추고,
    재개 시 needs_revision 으로 재평가되어 재분할/종료가 갈린다(RFP 게이트와 동일 패턴)."""
    if getattr(state, "needs_revision", False):
        print("🔁 [WBS 재분할] 사용자 피드백 반영 — Master_PMO 로 되돌려 WBS 를 다시 분할합니다.")
        return "Master_PMO"
    return "WBS_Approved"


def run_wbs_approved(state: ProjectState) -> dict:
    """WBS 승인 종결 노드(no-op) — WBS 게이트가 실제로 멈출 수 있도록 두는 '다음 노드'.
    승인되면 여기로 진행한 뒤 END 로 종료(기획 완료). 상태는 변경하지 않는다."""
    print("✅ [WBS 승인] 사용자가 WBS 를 승인했습니다 — 기획 단계를 종료합니다.")
    return {}

def route_from_rfp(state: ProjectState) -> str:
    """RFP HOTL 게이트 직후 분기: 사용자 피드백(needs_revision)이면 RFP 재작성을 위해
    RFP_Analyst 로 되돌리고(자기루프), 승인(피드백 없음)이면 다음 단계(Master_PM)로 진행.
    interrupt_after=RFP_Analyst 라 매 라운드 인간 게이트가 강제되므로 자동 무한루프 없음."""
    if getattr(state, "needs_revision", False):
        print("🔁 [RFP 재작성] 사용자 피드백 반영 — RFP_Analyst 로 되돌려 요구정의서를 다시 작성합니다.")
        return "RFP_Analyst"
    return "Master_PM"

def route_from_qa(state: ProjectState) -> str:
    """QA(수행사 통합검수) 직후 분기: 합격이면 고객사 수용검수(Supervisor)로, 미달이면 Tech_Lead 재작업.
    (비최종 태스크의 전용 QA는 드물게 실행되며 통과 시 그대로 스프린트 종료.)"""
    if getattr(state, "qa_verdict", "") == "FAIL":
        print("🔁 [QA 미달] 설계·통합 결함 — Tech_Lead 에게 재작업 지시.")
        return "Tech_Lead"
    if _is_final_task(state):
        print("➡️ [QA 통과] 고객사 수용검수(Supervisor)로 진행.")
        return "Supervisor"
    print("✅ [전용 QA 통과] 비최종 태스크 — 스프린트 종료.")
    return END

def route_from_supervisor(state: ProjectState) -> str:
    """고객사 수용검수(Supervisor) 직후 분기: 수용(PASS)→매뉴얼, 반려(REJECT)→PM 재조정.
    수용 시도 2회 초과(반복 반려) 시 무한 루프 대신 종료(인간 검토)로 표면화 — 보수적."""
    if getattr(state, "supervisor_verdict", "") == "PASS":
        return "ManualWriter"
    attempts = (getattr(state, "stage_attempt_counts", {}) or {}).get("SUPERVISOR", 0)
    if attempts >= 2:
        print("⚠️ [수용검수 상한] 반복 반려 — 무한 루프 방지 위해 종료(인간 검토 필요).")
        return END
    print("🔁 [고객 수용 미달] PM 에게 요구·기능 재조정 상신.")
    return "Master_PM"

# 레지스트리 id → 노드 구현 함수. 레지스트리가 노드 멤버십을 구동하기 위한 seam.
# (모든 레지스트리 에이전트 id 를 커버해야 동적 빌더가 임의 enabled 집합을 생성 가능)
NODE_IMPL = {
    "RFP_Analyst": run_rfp_analyst,
    "Master_PM": run_master_pm,
    "UIDesigner": __import__("nodes.ui_designer", fromlist=["run_ui_designer"]).run_ui_designer,
    "Master_PMO": run_master_pmo,
    "Architect": run_architect,
    "Tech_Lead": run_tech_lead,
    "Backend": run_developer_be,
    "Frontend": run_developer_fe,
    "CodeBuilder": run_code_builder,
    "Reviewer": run_reviewer,
    "QA": run_qa,
    "Supervisor": run_supervisor,
    "ManualWriter": run_manual_writer,
    "VisionQA": __import__("nodes.vision_qa", fromlist=["run_vision_qa"]).run_vision_qa,
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
    # RFP 게이트 피드백 루프: 피드백 시 RFP_Analyst 재실행(요구정의 재작성), 승인 시 Master_PM 진행
    workflow.add_conditional_edges("RFP_Analyst", route_from_rfp, {"RFP_Analyst": "RFP_Analyst", "Master_PM": "Master_PM"})
    workflow.add_conditional_edges("Master_PM", route_from_pm, {"UIDesigner": "UIDesigner", "Tech_Lead": "Tech_Lead", "Reviewer": "Reviewer"})
    
    workflow.add_conditional_edges("UIDesigner", route_from_ui_designer, {"UIDesigner": "UIDesigner", "Master_PMO": "Master_PMO"})
    
    # WBS 게이트: interrupt_after=Master_PMO 가 실제로 멈추도록 승인 경로를 '실제 노드'(WBS_Approved)로
    # 보낸다. 피드백 시 Master_PMO 재실행(WBS 재분할), 승인 시 WBS_Approved→END(기획 종료).
    workflow.add_node("WBS_Approved", run_wbs_approved)
    workflow.add_conditional_edges("Master_PMO", route_from_pmo, {"Master_PMO": "Master_PMO", "WBS_Approved": "WBS_Approved"})
    workflow.add_edge("WBS_Approved", END)

    workflow.add_conditional_edges("Architect", route_from_architect, {"Tech_Lead": "Tech_Lead", "Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    workflow.add_conditional_edges("Tech_Lead", route_from_tech_lead, {"Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    workflow.add_conditional_edges("Backend", route_from_backend, {"Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    workflow.add_edge("Frontend", "CodeBuilder")
    workflow.add_conditional_edges("CodeBuilder", map_builder_router, {"Frontend": "Frontend", "Backend": "Backend", "Reviewer": "Reviewer", END: END})

    workflow.add_conditional_edges("Reviewer", route_from_reviewer, {"QA": "QA", "ManualWriter": "ManualWriter", "Master_PM": "Master_PM", "Tech_Lead": "Tech_Lead", END: END})
    # 3단 수용 사다리: QA(수행사 통합검수) → Supervisor(고객사 수용검수) → ManualWriter
    #   QA: 통과→Supervisor / 미달→Tech_Lead 재작업
    #   Supervisor: 수용→ManualWriter / 반려→PM 재조정(상한 초과 시 종료)
    workflow.add_conditional_edges("QA", route_from_qa, {"Supervisor": "Supervisor", "Tech_Lead": "Tech_Lead", END: END})
    workflow.add_conditional_edges("Supervisor", route_from_supervisor, {"ManualWriter": "ManualWriter", "Master_PM": "Master_PM", END: END})
    workflow.add_edge("ManualWriter", END)


def build_graph_from_registry(registry=None):
    """레지스트리의 enabled 에이전트 id 로 노드를 생성(NODE_IMPL 매핑)하고, 엣지/라우터와
    interrupt_after(hotl_after) 를 적용해 (workflow, interrupt_after) 반환.

    (b)-1 동작 보존: DEFAULT_REGISTRY(전부 enabled)에서는 기존 하드코딩 토폴로지와 동일하다.
    엣지는 아직 _wire_edges 하드코딩이므로, enabled 에서 노드를 빼는 것은 (b)-2 에서 엣지 데이터화와
    함께 지원한다(현재 임의 비활성화는 dangling edge 로 compile 실패할 수 있음)."""
    from core.agent_registry import load_registry
    reg = registry or load_registry()
    # reg.agents 는 _normalize 로 order 정렬됨 — 범용 선형 그래프의 실행 순서로 사용
    enabled = [a for a in reg.get("agents", []) if a.get("enabled", True)]
    enabled_ids = [a["id"] for a in enabled]

    workflow = StateGraph(ProjectState)

    # 토폴로지 분기:
    #  - 순수 SW 템플릿(모든 enabled 노드가 NODE_IMPL 에 구현됨) → 기존 하드코딩 라우팅(동작 보존).
    #  - 커스텀 에이전트가 하나라도 있으면 → 범용 선형 파이프라인(T3): 모든 노드를 범용 실행기로
    #    생성하고 order 순으로 연결. SW 전용 라우터/필드에 의존하지 않는다.
    is_sw_pipeline = bool(enabled_ids) and all(aid in NODE_IMPL for aid in enabled_ids)

    if is_sw_pipeline:
        for aid in enabled_ids:
            impl = NODE_IMPL.get(aid)
            if impl is not None:
                workflow.add_node(aid, impl)
        _wire_edges(workflow)
        # HOTL 중단점 = "전달된 레지스트리" 의 hotl_after(SW 노드로 한정). DEFAULT_REGISTRY 면 기존과 동일.
        interrupt_after = [a["id"] for a in enabled
                           if a.get("hotl_after", False) and a["id"] in NODE_IMPL]
    else:
        # 범용 선형 파이프라인 — 설정만으로 새 에이전트 타입(마케팅/리서치/문서 등) 실행
        from nodes.universal import make_universal_node
        for aid in enabled_ids:
            workflow.add_node(aid, make_universal_node(aid))
            
        if enabled_ids:
            def route_universal(state: ProjectState, current_node_id: str) -> str:
                # 재실행(resimulate) 모드일 경우 시작점을 다르게 라우팅
                if state.factory_mode == "EXECUTION" and reg.get("simulation_framework", False):
                    resim_entry = reg.get("framework_agents", {}).get("resim_entry", "")
                    if resim_entry and current_node_id == "" and resim_entry in enabled_ids:
                        print(f"🔄 [Resimulate] 기존 설계 건너뛰기. {resim_entry}부터 재실행합니다.")
                        return resim_entry
                
                # 다음 실행할 노드를 찾습니다.
                try:
                    current_idx = enabled_ids.index(current_node_id) if current_node_id else -1
                except ValueError:
                    current_idx = -1
                
                # domain_agents 필터가 있으면 적용 (프레임워크 에이전트는 무조건 실행)
                domain_agents = getattr(state, "domain_agents", [])
                framework_agents = []
                if reg.get("simulation_framework", False):
                    framework_agents = reg.get("framework_agents", {}).get("preparation", []) + \
                                       reg.get("framework_agents", {}).get("evaluation", [])
                
                for idx in range(current_idx + 1, len(enabled_ids)):
                    next_node = enabled_ids[idx]
                    # 서브 프로젝트의 domain_agents가 지정된 경우 필터링
                    if domain_agents and next_node not in framework_agents and next_node not in domain_agents:
                        continue
                    return next_node
                
                return END

            # 조건부 진입점 설정
            workflow.set_conditional_entry_point(
                lambda s: route_universal(s, ""),
                {aid: aid for aid in enabled_ids}
            )
            
            for a_id in enabled_ids:
                workflow.add_conditional_edges(
                    a_id,
                    lambda s, current_node=a_id: route_universal(s, current_node),
                    {aid: aid for aid in enabled_ids} | {END: END}
                )
            
        # HOTL 중단점 = enabled 노드 중 hotl_after(범용 노드는 모두 add_node 됐으므로 제한 없음)
        interrupt_after = [a["id"] for a in enabled if a.get("hotl_after", False)]

    return workflow, interrupt_after


def _build_workflow(registry=None):
    """토폴로지 빌더 진입점 — 레지스트리 구동(build_graph_from_registry)으로 위임.
    create_factory_graph(studio/테스트)와 get_runtime_app(런타임 영속)이 공유한다.
    registry 미지정 시 default 레지스트리(하위호환)."""
    return build_graph_from_registry(registry)


def create_factory_graph():
    """동기 컴파일(MemorySaver) — LangGraph Studio/langgraph.json 및 단위 테스트용.
    런타임(오케스트레이터)은 재시작 내성을 위해 영속 체크포인터를 쓰는 get_runtime_app()을 사용한다."""
    workflow, interrupt_after = _build_workflow()
    return workflow.compile(checkpointer=MemorySaver(), interrupt_after=interrupt_after)


# 스튜디오/langgraph.json/테스트용 동기 인스턴스(휘발성). 런타임은 get_runtime_app() 사용.
app = create_factory_graph()


# ── 런타임 전용 영속 체크포인터 그래프 (재시작 내성) ──────────────────────────────
# AsyncSqliteSaver 는 생성 시 실행 중 이벤트루프가 필요하므로 모듈 import 시점엔 만들 수 없다.
# → 첫 호출(오케스트레이터의 async 컨텍스트) 때 1회 lazy 생성하고 캐시한다.
# T2-b: 템플릿마다 토폴로지가 다를 수 있으므로 컴파일 그래프를 template_id 별로 캐시한다.
#       체크포인터(SQLite saver)는 전 템플릿이 공유한다 — thread_id(project__task)가 상태를
#       격리하고, 한 프로젝트/태스크는 항상 같은 템플릿으로 실행되므로 충돌하지 않는다.
_runtime_saver = None                 # 공유 AsyncSqliteSaver(1회 생성)
_runtime_apps: dict = {}              # template_id -> 컴파일된 그래프
_runtime_lock = asyncio.Lock()


async def _get_runtime_saver():
    global _runtime_saver
    if _runtime_saver is None:
        postgres_uri = os.environ.get("POSTGRES_URI")
        if postgres_uri:
            try:
                import asyncpg
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                conn = await asyncpg.connect(postgres_uri)
                _runtime_saver = AsyncPostgresSaver(conn)
                await _runtime_saver.setup()
                print("🐘 [Checkpointer] PostgreSQL 분산 DB 어댑터 연결 성공.")
            except ImportError:
                print("⚠️ [Checkpointer] asyncpg 모듈이 없어 PostgreSQL 연동 실패. SQLite로 Fallback합니다.")
                postgres_uri = None
        
        if not postgres_uri:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            conn = await aiosqlite.connect(config.PIPELINE_DB_FILE, check_same_thread=False)
            _runtime_saver = AsyncSqliteSaver(conn)
            await _runtime_saver.setup()
            print("🗄️ [Checkpointer] 기본 SQLite 어댑터 연결 완료.")
            
    return _runtime_saver


async def get_runtime_app(template_id: str = "default"):
    """오케스트레이터용 그래프(영속 체크포인터=SQLite). template_id 별로 1회 compile·캐시.
    → 서버 재시작 시에도 HOTL 대기 체크포인트가 디스크에 보존되어 스프린트 재개가 가능하다.
    → 템플릿마다 enabled/hotl_after 가 다르면 토폴로지·중단점도 그에 맞게 컴파일된다(T2-b)."""
    tid = template_id or "default"
    cached = _runtime_apps.get(tid)
    if cached is not None:
        return cached
    async with _runtime_lock:
        if tid not in _runtime_apps:
            from core.agent_registry import load_template
            saver = await _get_runtime_saver()
            workflow, interrupt_after = _build_workflow(load_template(tid))
            _runtime_apps[tid] = workflow.compile(checkpointer=saver, interrupt_after=interrupt_after)
    return _runtime_apps[tid]