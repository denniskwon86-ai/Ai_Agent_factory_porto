import os
import json
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END

# 내부 모듈 임포트
from state import ProjectState
from harness import AgentHarness
from nodes.code_builder import run_code_builder
from nodes.utils.wbs_manager import WBSManager

# 하네스 싱글톤 인스턴스 (앱 구동 주기 동안 LLM 엔진을 유지)
harness = AgentHarness()

# ==========================================
# [Track 0] Master Planning 노드
# ==========================================
def run_master_pm(state: ProjectState) -> ProjectState:
    print("[Agent] Master PM 실행 중...")
    context = f"Project: {state['project_name']}\nIdea: {state['initial_idea']}"
    output = harness.execute(role_name="pm_skill", context_data=context, previous_output=state.get("prd"))
    
    return {
        "prd": output,
        "prd_summary": harness.summarize_context(output)
    }

def run_master_pmo(state: ProjectState) -> ProjectState:
    print("[Agent] Master PMO 실행 중... WBS 생성")
    context = f"Master PRD Summary: {state['prd_summary']}"
    output = harness.execute(role_name="pmo_skill", context_data=context)
    
    # JSON 파싱 방어 로직 (Phase 1: T-07 연동)
    try:
        import re
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            wbs_data = json.loads(json_match.group(0))
            # WBS 파일 저장
            wbs_path = state.get("wbs_master_plan_path", "00_wbs_master_plan.json")
            with open(wbs_path, 'w', encoding='utf-8') as f:
                json.dump(wbs_data, f, ensure_ascii=False, indent=2)
            print(f"  ✅ WBS 저장 완료: {wbs_path}")
        else:
            print("  ⚠️ WBS JSON 파싱 실패 (코드블록 없음)")
    except Exception as e:
        print(f"  ⚠️ WBS 저장 중 오류: {e}")

    return {} # PMO는 상태 객체에 큰 텍스트를 남기지 않고 파일 시스템에 직접 기록

# ==========================================
# [Track 1] Sprint Execution 노드
# ==========================================
def run_architect(state: ProjectState) -> ProjectState:
    print("[Agent] Architect 실행 중...")
    
    # [Phase 4: T-12 연동] WBS 태스크를 IN_PROGRESS로 업데이트
    task_id = state.get("current_sprint_task_id")
    wbs_path = state.get("wbs_master_plan_path")
    if task_id and wbs_path:
        WBSManager.set_status(wbs_path, task_id, "IN_PROGRESS")
        
    context = f"Master PRD: {state.get('prd_summary')}"
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    output = harness.execute(role_name="architect_skill", context_data=context, feedback=feedback, previous_output=state.get("architecture_doc"))
    
    return {
        "architecture_doc": output,
        "architecture_summary": harness.summarize_context(output)
    }

def run_tech_lead(state: ProjectState) -> ProjectState:
    print("[Agent] Tech Lead 실행 중...")
    context = (
        f"Master PRD: {state.get('prd_summary')}\n"
        f"Architecture: {state.get('architecture_summary')}"
    )
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    output = harness.execute(role_name="tech_lead_skill", context_data=context, feedback=feedback, previous_output=state.get("tech_spec"))
    
    # Project Type 자동 추출
    project_type = "python"
    try:
        import yaml
        import re
        yaml_match = re.search(r'```yaml\n(.*?)\n```', output, re.DOTALL)
        if yaml_match:
            spec_meta = yaml.safe_load(yaml_match.group(1))
            project_type = spec_meta.get("project_type", "python")
    except Exception:
        pass

    return {
        "tech_spec": output,
        "tech_spec_summary": harness.summarize_context(output),
        "project_type": project_type
    }

def run_frontend(state: ProjectState) -> ProjectState:
    print(f"[Agent] Frontend Engineer 실행 중... (빌드 루프 횟수: {state.get('developer_retry_count', 0)})")
    build_err = state.get("build_error_log", "")
    context = f"Tech Spec 원본: {state['tech_spec']}" # [V5.0 정책: 원본 주입]
    
    # [Phase 1: T-09] 중복 에러 블록 단일화
    if build_err:
        context += f"\n\n🚨 [빌드 오류 피드백 발생] 이전 컴파일이 실패했습니다. 에러 로그를 분석하고 수정하십시오:\n{build_err}"
        
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    output = harness.execute(role_name="frontend_skill", context_data=context, feedback=feedback, previous_output=state.get("frontend_code"))
    
    return {
        "frontend_code": output,
        "frontend_code_summary": harness.summarize_context(output)
    }

def run_backend(state: ProjectState) -> ProjectState:
    print(f"[Agent] Backend Engineer 실행 중... (빌드 루프 횟수: {state.get('developer_retry_count', 0)})")
    build_err = state.get("build_error_log", "")
    context = f"Tech Spec 원본: {state['tech_spec']}" # [V5.0 정책: 원본 주입]
    
    # [Phase 1: T-09] 중복 에러 블록 단일화
    if build_err:
        context += f"\n\n🚨 [빌드 오류 피드백 발생] 이전 컴파일이 실패했습니다. 에러 로그를 분석하고 수정하십시오:\n{build_err}"
        
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    output = harness.execute(role_name="backend_skill", context_data=context, feedback=feedback, previous_output=state.get("backend_code"))
    
    return {
        "backend_code": output,
        "backend_code_summary": harness.summarize_context(output)
    }

def run_reviewer(state: ProjectState) -> ProjectState:
    print("[Agent] Code Reviewer & Sprint Documenter 실행 중...")
    context = (
        f"Tech Spec Summary: {state['tech_spec_summary']}\n"
        f"Frontend Summary: {state['frontend_code_summary']}\n"
        f"Backend Summary: {state['backend_code_summary']}\n"
        f"Build Status: {state['build_status']}\n"
        f"Retry Count: {state['developer_retry_count']}"
    )
    output = harness.execute(role_name="reviewer_skill", context_data=context)
    
    # [Phase 4: T-12 연동] 스프린트 완료 시 WBS 상태를 DONE으로 업데이트
    task_id = state.get("current_sprint_task_id")
    wbs_path = state.get("wbs_master_plan_path")
    if task_id and wbs_path:
        WBSManager.set_status(wbs_path, task_id, "DONE")

    return {
        "code_review_report": output,
        "code_review_report_summary": harness.summarize_context(output)
    }

# ==========================================
# [Track 3] QA Release 노드
# ==========================================
def run_qa(state: ProjectState) -> ProjectState:
    print("[Agent] QA Analyst 실행 중... 전체 시스템 통합 검증")
    
    context = (
        f"Master PRD Summary: {state.get('prd_summary', '')}\n"
        f"Project Name: {state.get('project_name', '')}\n"
    )
    
    # [Phase 4: T-10 연동] QA 에이전트에 실제 산출물 맥락 추가
    if state.get("frontend_code_summary"):
        context += f"\n[Frontend Code Summary]\n{state['frontend_code_summary']}\n"
    if state.get("backend_code_summary"):
        context += f"\n[Backend Code Summary]\n{state['backend_code_summary']}\n"
    if state.get("code_review_report_summary"):
        context += f"\n[Sprint Review Report]\n{state['code_review_report_summary']}\n"

    output = harness.execute(role_name="qa_skill", context_data=context)
    
    return {
        "qa_report": output,
        "qa_report_summary": harness.summarize_context(output)
    }

# ==========================================
# 라우팅 로직 (Edges)
# ==========================================
def map_builder_router(state: ProjectState) -> Literal["Frontend", "Backend", "Reviewer"]:
    """빌드 결과에 따라 무한루프를 방지하고 적절한 노드로 분기합니다."""
    # 최대 3회 재시도 (물리 노드에서 state 업데이트됨)
    if state.get("developer_retry_count", 0) >= 3:
        print("🚨 [Eviction] 최대 재시도(3회) 초과. 기술 부채를 남기고 Reviewer로 강제 회피합니다.")
        return "Reviewer"

    if state.get("build_status") == "success":
        return "Reviewer"
    
    # 실패 시 프로젝트 타입에 따라 적절한 에이전트에게 롤백
    ptype = state.get("project_type", "python").lower()
    if ptype == "node":
        return "Frontend"
    else:
        return "Backend"

def track_router(state: ProjectState) -> Literal["Master_PM", "Architect", "QA"]:
    """팩토리 모드에 따라 3-Track 진입점을 동적으로 분기합니다."""
    mode = state.get("factory_mode", "EXECUTION")
    if mode == "PLANNING":
        return "Master_PM"
    elif mode == "QA_RELEASE":
        return "QA"
    else: # EXECUTION
        return "Architect"

# ==========================================
# StateGraph 조립
# ==========================================
workflow = StateGraph(ProjectState)

# 노드 등록
workflow.add_node("Master_PM", run_master_pm)
workflow.add_node("Master_PMO", run_master_pmo)

workflow.add_node("Architect", run_architect)
workflow.add_node("Tech_Lead", run_tech_lead)
workflow.add_node("Frontend", run_frontend)
workflow.add_node("Backend", run_backend)
workflow.add_node("CodeBuilder", run_code_builder)
workflow.add_node("Reviewer", run_reviewer)

workflow.add_node("QA", run_qa)

# 엣지 연결 (진입점 동적 라우팅)
workflow.set_conditional_entry_point(
    track_router,
    {
        "Master_PM": "Master_PM",
        "Architect": "Architect",
        "QA": "QA"
    }
)

# Track 0: PLANNING
workflow.add_edge("Master_PM", "Master_PMO")
workflow.add_edge("Master_PMO", END)

# Track 1: EXECUTION
workflow.add_edge("Architect", "Tech_Lead")
workflow.add_edge("Tech_Lead", "Frontend")
workflow.add_edge("Frontend", "Backend")
workflow.add_edge("Backend", "CodeBuilder")

workflow.add_conditional_edges(
    "CodeBuilder",
    map_builder_router,
    {
        "Frontend": "Frontend",
        "Backend": "Backend",
        "Reviewer": "Reviewer"
    }
)
workflow.add_edge("Reviewer", END)

# Track 3: QA
workflow.add_edge("QA", END)