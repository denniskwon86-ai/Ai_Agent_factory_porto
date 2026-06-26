import os
import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state_models import ProjectState

from nodes.planning import run_master_pm, run_master_pmo
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
        
    return agents

def _has_role(agents: list, role_en: str, role_ko: str) -> bool:
    for a in agents:
        a_lower = a.lower()
        if role_en.lower() in a_lower or role_ko in a:
            return True
    return False

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
    if state.factory_mode == "PLANNING": return "Master_PM"
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

def create_factory_graph():
    workflow = StateGraph(ProjectState)

    workflow.add_node("Master_PM", run_master_pm)
    workflow.add_node("Master_PMO", run_master_pmo)
    workflow.add_node("Architect", run_architect)
    workflow.add_node("Tech_Lead", run_tech_lead)
    workflow.add_node("Backend", run_developer_be)
    workflow.add_node("Frontend", run_developer_fe)
    workflow.add_node("CodeBuilder", run_code_builder)
    workflow.add_node("Reviewer", run_supervisor)
    workflow.add_node("QA", run_qa)
    workflow.add_node("ManualWriter", run_manual_writer)

    workflow.set_conditional_entry_point(
        route_factory_mode,
        {
            "Master_PM": "Master_PM", "Tech_Lead": "Tech_Lead", "Architect": "Architect",
            "Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"
        }
    )

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

    memory = MemorySaver()
    # 이전 HOTL 중단점 설정 유지
    app = workflow.compile(checkpointer=memory, interrupt_after=["Master_PMO", "Tech_Lead"])
    return app

app = create_factory_graph()