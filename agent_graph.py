import os
import sqlite3
import re
import json
from typing import List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from harness import AgentHarness

from state import ProjectState
from nodes.code_builder import run_code_builder

def save_artifact_to_disk(output_dir: str, filename: str, content: str):
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📁 파일 저장 완료: {file_path}")

harness = AgentHarness()

# ==========================================
# [Track 0] 기획 및 설계 에이전트 노드
# ==========================================

def run_master_pm(state: ProjectState) -> ProjectState:
    print("\n" + "="*50)
    print("🧭 [Agent] Master PM 실행 중... (전체 시스템 Master PRD 작성)")
    print("="*50)
    
    context = f"Project Name: {state.get('project_name', 'Unknown')}\nInitial Idea: {state.get('initial_idea', '')}"
    
    output = harness.execute(
        role_name="pm_skill",
        context_data=context + "\n\n🚨 단일 Task가 아닌, 전체 프로젝트 관점의 통합 마스터 기획서(Master PRD)를 작성하십시오.",
        feedback=None,
        previous_output=None
    )
    summary = harness.summarize_context(output)
    
    save_artifact_to_disk(state.get("output_dir", ""), "00_master_prd.md", output)
    state["prd"] = output
    state["prd_summary"] = summary
    return state

def run_master_pmo(state: ProjectState) -> ProjectState:
    print("\n🧭 [Agent] Master PMO 실행 중... (WBS 마스터플랜 분할)")
    
    context = f"Master PRD Summary: {state.get('prd_summary', '')}"
    
    output = harness.execute(
        role_name="pmo_skill",
        context_data=context,
        feedback=None,
        previous_output=None
    )
    
    try:
        json_str = re.search(r'\{.*\}', output, re.DOTALL).group()
    except Exception as e:
        print(f"⚠️ JSON 파싱 실패: {e}")
        json_str = output
        
    wbs_path = state.get("wbs_master_plan_path", "00_wbs_master_plan.json")
    save_artifact_to_disk(state.get("output_dir", ""), wbs_path, json_str)
    print(f"✅ [PMO] WBS 마스터 플랜 생성 완료: {wbs_path}")
    
    return state

# ==========================================
# [Track 1] 스프린트 실행 (컨베이어 벨트) 에이전트 노드
# ==========================================

def run_architect(state: ProjectState) -> ProjectState:
    task_id = state.get("current_sprint_task_id", "Unknown")
    print(f"\n[Agent] Architect 실행 중... [Task: {task_id}] (재시도 횟수: {state.get('architect_retry_count', 0)})")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    # WBS를 읽고 현재 Task의 스코프를 파싱하여 Architect에게 주입 (스코프 락 이관)
    wbs_path = state.get("wbs_master_plan_path", "00_wbs_master_plan.json")
    task_info = "⚠️ WBS 태스크 정보를 찾을 수 없습니다."
    try:
        if os.path.exists(wbs_path):
            with open(wbs_path, "r", encoding="utf-8") as f:
                wbs_data = json.load(f)
                for task in wbs_data.get("tasks", []):
                    if task.get("task_id") == task_id:
                        task_info = json.dumps(task, indent=2, ensure_ascii=False)
                        break
    except Exception as e:
        print(f"⚠️ WBS 파일 읽기 실패: {e}")

    context = (
        f"Master PRD Summary: {state.get('prd_summary', '')}\n"
        f"--- [오늘의 구현 대상: WBS Task ({task_id})] ---\n"
        f"{task_info}\n"
        "-------------------------------------------\n"
        "🚨 [최고 중요 지시사항]: Master PRD의 맥락을 참고하되, 반드시 위 WBS Task 정보의 'scope'에 명시된 기능에 대해서만 아키텍처 및 DB 설계를 진행하십시오. 'out_of_scope'는 철저히 배제하십시오."
    )
    
    output = harness.execute(
        role_name="architect_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("architecture_doc")
    )
    summary = harness.summarize_context(output)
    
    if feedback:
        state["architect_retry_count"] = state.get("architect_retry_count", 0) + 1

    save_artifact_to_disk(state.get("output_dir", ""), "02_architecture_doc.md", output)
    state["architecture_doc"] = output
    state["architecture_summary"] = summary
    state["needs_revision"] = False
    return state

def run_tech_lead(state: ProjectState) -> ProjectState:
    print("[Agent] Tech Lead 실행 중...")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    context = f"Master PRD Summary: {state['prd_summary']}\nArch Summary: {state['architecture_summary']}"
    
    output = harness.execute(
        role_name="tech_lead_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("tech_spec")
    )
    summary = harness.summarize_context(output)
    save_artifact_to_disk(state.get("output_dir", ""), "03_tech_spec.md", output)
    state["tech_spec"] = output
    state["tech_spec_summary"] = summary
    return state

def run_frontend(state: ProjectState) -> ProjectState:
    print(f"[Agent] Frontend Engineer 실행 중... (빌드 루프 횟수: {state.get('developer_retry_count', 0)})")
    build_err = state.get("build_error_log", "")
    context = f"Tech Spec Summary: {state['tech_spec_summary']}"
    if build_err:
        context += f"\n\n🚨 [빌드 오류 피드백 발생] 이전 컴파일이 실패했습니다. 에러 로그를 분석하고 수정하십시오:\n{build_err}"
        
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    output = harness.execute(role_name="frontend_skill", context_data=context, feedback=feedback, previous_output=state.get("frontend_code"))
    
    save_artifact_to_disk(state.get("output_dir", ""), "04_frontend_code.md", output)
    state["frontend_code"] = output
    state["frontend_code_summary"] = harness.summarize_context(output)
    return state

def run_backend(state: ProjectState) -> ProjectState:
    print("[Agent] Backend Engineer 실행 중...")
    build_err = state.get("build_error_log", "")
    context = f"Tech Spec Summary: {state['tech_spec_summary']}"
    if build_err:
        context += f"\n\n🚨 [빌드 오류 피드백 발생] 에러 로그를 분석하고 수정하십시오:\n{build_err}"
        
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    output = harness.execute(role_name="backend_skill", context_data=context, feedback=feedback, previous_output=state.get("backend_code"))
    
    save_artifact_to_disk(state.get("output_dir", ""), "05_backend_code.md", output)
    state["backend_code"] = output
    state["backend_code_summary"] = harness.summarize_context(output)
    return state

def run_reviewer(state: ProjectState) -> ProjectState:
    print(f"[Agent] Reviewer 실행 중... (코드 품질 리포트 작성)")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    context = (
        f"Arch Summary: {state['architecture_summary']}\n"
        f"Frontend Code: {state['frontend_code_summary']}\n"
        f"Backend Code: {state['backend_code_summary']}"
    )
    output = harness.execute(role_name="reviewer_skill", context_data=context, feedback=feedback, previous_output=state.get("code_review_report"))
    
    save_artifact_to_disk(state.get("output_dir", ""), "06_code_review_report.md", output)
    state["code_review_report"] = output
    state["code_review_report_summary"] = harness.summarize_context(output)
    return state

# ==========================================
# [Track 3] 통합 시스템 릴리즈 QA 노드
# ==========================================

def run_qa(state: ProjectState) -> ProjectState:
    print("\n" + "="*50)
    print("🔬 [Agent] Master QA 실행 중... (전체 시스템 통합 검증 및 릴리즈 승인)")
    print("="*50)
    
    context = (
        f"Master PRD Summary: {state.get('prd_summary', '')}\n"
        f"Project Name: {state.get('project_name', '')}\n"
        f"빌드가 통과된 전체 Workspace 폴더 및 실행 진입점의 연동 무결성을 최종 검증하십시오."
    )
    
    output = harness.execute(role_name="qa_skill", context_data=context, feedback=None, previous_output=state.get("qa_report"))
    save_artifact_to_disk(state.get("output_dir", ""), "07_final_qa_report.md", output)
    state["qa_report"] = output
    state["pipeline_status"] = "completed"
    return state

# ==========================================
# 라우팅 로직 (Conditional Edges)
# ==========================================

def route_factory_mode(state: ProjectState) -> str:
    mode = state.get("factory_mode", "EXECUTION")
    if mode == "PLANNING":
        return "Master_PM"
    elif mode == "QA_RELEASE":
        return "QA"
    else:
        print(f"⚙️ [Router] 스프린트 팩토리 가동(EXECUTION) ➔ Architect 노드 진입")
        return "Architect"

def architect_router(state: ProjectState) -> str:
    if state.get("needs_revision"):
        if state.get("architect_retry_count", 0) >= state.get("max_review_iterations", 1):
            print("🚨 [WARNING] 설계 수정 한도 초과. 강제 진행합니다.")
            return "proceed"
        return "revision"
    return "proceed"

def map_builder_router(state: ProjectState) -> str:
    status = state.get("build_status", "pending")
    if status == "failed" and state.get("developer_retry_count", 0) <= 3:
        print(f"🔄 [Build Fail Loop] 에러 로그 주입 후 개발자 롤백")
        return "recode"
    print("✅ 빌드 검증 완료! 리뷰어 단계로 진입합니다.")
    return "proceed"

def reviewer_router(state: ProjectState) -> str:
    # [터보 모드 + QA 분리] 리뷰어 통과 시 즉시 Task 스프린트 완전 종료
    print("⏩ [Fast-Track] 리뷰 리포트 작성 완료. 일일 스프린트를 즉시 종료합니다.")
    return "proceed"

# ==========================================
# LangGraph 파이프라인 조립 (V4.0)
# ==========================================
workflow = StateGraph(ProjectState)

workflow.add_node("Master_PM", run_master_pm)
workflow.add_node("Master_PMO", run_master_pmo)
workflow.add_node("Architect", run_architect)
workflow.add_node("Tech_Lead", run_tech_lead)
workflow.add_node("Frontend", run_frontend)
workflow.add_node("Backend", run_backend)
workflow.add_node("CodeBuilder", run_code_builder)
workflow.add_node("Reviewer", run_reviewer)
workflow.add_node("QA", run_qa)

workflow.set_conditional_entry_point(
    route_factory_mode,
    {
        "Master_PM": "Master_PM",
        "Architect": "Architect",
        "QA": "QA"
    }
)

# Track 0 흐름
workflow.add_edge("Master_PM", "Master_PMO")
workflow.add_edge("Master_PMO", END)

# Track 1 흐름
workflow.add_conditional_edges("Architect", architect_router, {"revision": "Architect", "proceed": "Tech_Lead"})
workflow.add_edge("Tech_Lead", "Frontend")
workflow.add_edge("Frontend", "Backend")
workflow.add_edge("Backend", "CodeBuilder") 
workflow.add_conditional_edges("CodeBuilder", map_builder_router, {"recode": "Frontend", "proceed": "Reviewer"})
workflow.add_conditional_edges("Reviewer", reviewer_router, {"rollback": "Frontend", "proceed": END}) # 터보 모드 적용 (QA 생략 후 즉시 종료)

# Track 3 흐름
workflow.add_edge("QA", END)

conn = sqlite3.connect("pipeline_state.db", check_same_thread=False)
memory = SqliteSaver(conn)

app = workflow.compile(
    checkpointer=memory,
    interrupt_after=["Architect"]
)

if __name__ == "__main__":
    print("V4.0 다중 에이전트 자동화 파이프라인 그래프 조립 완료.")