import os
import sqlite3
from typing import List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from harness import AgentHarness

# [신규 추가] state와 code_builder 모듈 참조
from state import ProjectState
from nodes.code_builder import run_code_builder

def save_artifact_to_disk(output_dir: str, filename: str, content: str):
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📁 파일 저장 완료: {file_path}")

harness = AgentHarness()

def run_pm(state: ProjectState) -> ProjectState:
    print(f"[Agent] PM 실행 중... (재시도 횟수: {state.get('pm_retry_count', 0)})")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    output = harness.execute(
        role_name="pm_skill",
        context_data=f"Initial Idea: {state['initial_idea']}",
        feedback=feedback,
        previous_output=state.get("prd")
    )
    summary = harness.summarize_context(output)
    
    if feedback:
        state["pm_retry_count"] += 1

    save_artifact_to_disk(state["output_dir"], "01_prd.md", output)
    state["prd"] = output
    state["prd_summary"] = summary
    state["needs_revision"] = False
    return state

def run_architect(state: ProjectState) -> ProjectState:
    print(f"[Agent] Architect 실행 중... (재시도 횟수: {state.get('architect_retry_count', 0)})")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    output = harness.execute(
        role_name="architect_skill",
        context_data=f"PRD Summary: {state['prd_summary']}",
        feedback=feedback,
        previous_output=state.get("architecture_doc")
    )
    summary = harness.summarize_context(output)
    
    if feedback:
        state["architect_retry_count"] += 1

    save_artifact_to_disk(state["output_dir"], "02_architecture_doc.md", output)
    state["architecture_doc"] = output
    state["architecture_summary"] = summary
    state["needs_revision"] = False
    return state

def run_tech_lead(state: ProjectState) -> ProjectState:
    print("[Agent] Tech Lead 실행 중...")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    context = f"PRD Summary: {state['prd_summary']}\nArch Summary: {state['architecture_summary']}"
    
    output = harness.execute(
        role_name="tech_lead_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("tech_spec")
    )
    summary = harness.summarize_context(output)
    
    save_artifact_to_disk(state["output_dir"], "03_tech_spec.md", output)
    state["tech_spec"] = output
    state["tech_spec_summary"] = summary
    return state

def run_frontend(state: ProjectState) -> ProjectState:
    print(f"[Agent] Frontend Engineer 실행 중... (빌드 루프 횟수: {state.get('developer_retry_count', 0)})")
    
    # [핵심] 컴파일 에러 발생 시 개발 에이전트의 프롬프트에 자동 주입
    build_err = state.get("build_error_log", "")
    context = f"Tech Spec Summary: {state['tech_spec_summary']}"
    if build_err:
        context += f"\n\n🚨 [빌드 오류 피드백 발생] 이전 컴파일이 실패했습니다. 아래 에러 로그를 분석하고 코드를 엄격히 수정하십시오:\n{build_err}"
        
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    output = harness.execute(
        role_name="frontend_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("frontend_code")
    )
    summary = harness.summarize_context(output)
    
    save_artifact_to_disk(state["output_dir"], "04_frontend_code.md", output)
    state["frontend_code"] = output
    state["frontend_code_summary"] = summary
    return state

def run_backend(state: ProjectState) -> ProjectState:
    print("[Agent] Backend Engineer 실행 중...")
    
    # [핵심] 컴파일 에러 발생 시 개발 에이전트의 프롬프트에 자동 주입
    build_err = state.get("build_error_log", "")
    context = f"Tech Spec Summary: {state['tech_spec_summary']}"
    if build_err:
        context += f"\n\n🚨 [빌드 오류 피드백 발생] 이전 컴파일이 실패했습니다. 아래 에러 로그를 분석하고 코드를 엄격히 수정하십시오:\n{build_err}"
        
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    output = harness.execute(
        role_name="backend_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("backend_code")
    )
    summary = harness.summarize_context(output)
    
    save_artifact_to_disk(state["output_dir"], "05_backend_code.md", output)
    state["backend_code"] = output
    state["backend_code_summary"] = summary
    return state

def run_reviewer(state: ProjectState) -> ProjectState:
    print(f"[Agent] Reviewer 실행 중... (Iteration: {state['review_iteration'] + 1}/{state['max_review_iterations']})")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    context = (
        f"Arch Summary: {state['architecture_summary']}\n"
        f"Tech Spec Summary: {state['tech_spec_summary']}\n"
        f"Frontend Code: {state['frontend_code_summary']}\n"
        f"Backend Code: {state['backend_code_summary']}"
    )
    
    output = harness.execute(
        role_name="reviewer_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("code_review_report")
    )
    summary = harness.summarize_context(output)
    
    save_artifact_to_disk(state["output_dir"], "06_code_review_report.md", output)
    state["code_review_report"] = output
    state["code_review_report_summary"] = summary
    state["review_iteration"] += 1  
    return state

def run_qa(state: ProjectState) -> ProjectState:
    print("[Agent] QA Engineer 실행 중...")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    # [신규] QA 에이전트가 빌드된 실제 폴더 경로를 인지할 수 있도록 컨텍스트 주입
    context = (
        f"PRD Summary: {state['prd_summary']}\n"
        f"Tech Spec Summary: {state['tech_spec_summary']}\n"
        f"Project Path: {state.get('project_output_path', '')}\n"
        f"Executable Entry Point: {state.get('executable_entry_point', '')}"
    )
    
    output = harness.execute(
        role_name="qa_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("qa_report")
    )
    summary = harness.summarize_context(output)
    
    save_artifact_to_disk(state["output_dir"], "07_qa_report.md", output)
    state["qa_report"] = output
    state["qa_report_summary"] = summary
    state["pipeline_status"] = "completed"
    return state

# ==========================================
# 라우팅 로직 (Conditional Edges)
# ==========================================
def pm_router(state: ProjectState) -> str:
    if state.get("needs_revision"):
        if state.get("pm_retry_count", 0) >= state.get("max_review_iterations", 3):
            print("🚨 [WARNING] PM 기획 수정 최대 한도 초과. 강제 진행합니다.")
            return "proceed"
        return "revision"
    return "proceed"

def map_builder_router(state: ProjectState) -> str:
    """CodeBuilderNode 컴파일 성공 여부에 따른 자동 피드백 루프 라우터"""
    status = state.get("build_status", "pending")
    # 이미 CodeBuilder에서 +1 되어 넘어온 카운터를 읽기만 함
    retry_count = state.get("developer_retry_count", 0)
    max_retry = state.get("max_review_iterations", 3)
    
    if status == "failed":
        if retry_count > max_retry:
            print(f"🚨 [WARNING] 빌드 연속 실패 한도({max_retry}회) 초과. 무한 루프를 방지하고 강제로 다음 단계(Reviewer)로 회피합니다.")
            return "proceed"
        print(f"🔄 [Build Fail Loop] 빌드 결함 감지! 개발 에이전트(Frontend/Backend)로 에러 로그를 주입하고 재구동합니다. ({retry_count}/{max_retry})")
        return "recode"
    
    print("✅ 빌드 무결성 테스트 대성공! 리뷰어 단계로 진입합니다.")
    return "proceed"

def architect_router(state: ProjectState) -> str:
    if state.get("needs_revision"):
        if state.get("architect_retry_count", 0) >= state.get("max_review_iterations", 3):
            print("🚨 [WARNING] Architect 설계 수정 최대 한도 초과. 강제 진행합니다.")
            return "proceed"
        return "revision"
    return "proceed"

def reviewer_router(state: ProjectState) -> str:
    report = state.get("code_review_report", "")
    iteration = state.get("review_iteration", 0)
    max_iter = state.get("max_review_iterations", 3)
    
    if "[CRITICAL]" in report and iteration < max_iter:
        print("🚨 [CRITICAL] 리뷰어 검증 결함 발견! 코드를 재수정하기 위해 개발 단계로 롤백합니다.")
        return "rollback"
    return "proceed"

# ==========================================
# LangGraph 파이프라인 조립 및 영구 체크포인트 설정
# ==========================================
workflow = StateGraph(ProjectState)

workflow.add_node("PM", run_pm)
workflow.add_node("Architect", run_architect)
workflow.add_node("Tech_Lead", run_tech_lead)
workflow.add_node("Frontend", run_frontend)
workflow.add_node("Backend", run_backend)
workflow.add_node("CodeBuilder", run_code_builder) # [신규] 노드 추가
workflow.add_node("Reviewer", run_reviewer)
workflow.add_node("QA", run_qa)

workflow.set_entry_point("PM")

workflow.add_conditional_edges("PM", pm_router, {"revision": "PM", "proceed": "Architect"})
workflow.add_conditional_edges("Architect", architect_router, {"revision": "Architect", "proceed": "Tech_Lead"})

workflow.add_edge("Tech_Lead", "Frontend")
workflow.add_edge("Frontend", "Backend")

# [신규] 백엔드 완료 후 코드를 수집하여 CodeBuilder 가동
workflow.add_edge("Backend", "CodeBuilder") 

# [신규] CodeBuilder 검증 결과 라우팅 연결 (실패 시 Frontend 재수정 루프, 성공 시 Reviewer행)
workflow.add_conditional_edges("CodeBuilder", map_builder_router, {"recode": "Frontend", "proceed": "Reviewer"})

workflow.add_conditional_edges("Reviewer", reviewer_router, {"rollback": "Frontend", "proceed": "QA"})
workflow.add_edge("QA", END)

conn = sqlite3.connect("pipeline_state.db", check_same_thread=False)
memory = SqliteSaver(conn)

app = workflow.compile(
    checkpointer=memory,
    interrupt_after=["PM", "Architect"]
)

if __name__ == "__main__":
    print("다중 에이전트 자동화 파이프라인 그래프 조립 완료.")