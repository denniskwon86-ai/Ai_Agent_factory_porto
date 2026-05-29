import os
import sqlite3
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from harness import AgentHarness

# ==========================================
# 물리적 파일 저장 헬퍼 함수
# ==========================================
def save_artifact_to_disk(output_dir: str, filename: str, content: str):
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📁 파일 저장 완료: {file_path}")

# ==========================================
# 1. 블랙보드 스키마 정의 (ProjectState)
# ==========================================
class ProjectState(TypedDict):
    initial_idea: str
    human_feedback_queue: List[str]
    
    pipeline_status: str
    error_log: str
    output_dir: str
    
    review_iteration: int
    max_review_iterations: int
    pm_retry_count: int         
    architect_retry_count: int  
    needs_revision: bool        
    
    prd: str
    prd_summary: str
    architecture_doc: str
    architecture_summary: str
    tech_spec: str
    tech_spec_summary: str
    frontend_code: str
    frontend_code_summary: str
    backend_code: str
    backend_code_summary: str
    code_review_report: str
    code_review_report_summary: str
    qa_report: str
    qa_report_summary: str

# ==========================================
# 2. 하네스 초기화
# ==========================================
llm_pro = "pro_model_instance"
llm_flash = "flash_model_instance"
harness = AgentHarness(llm_pro, llm_flash)

# ==========================================
# 3. 노드 실행 함수 정의
# ==========================================
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
    print("[Agent] Frontend Engineer 실행 중...")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    context = f"Tech Spec Summary: {state['tech_spec_summary']}"
    
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
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    context = f"Tech Spec Summary: {state['tech_spec_summary']}"
    
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
    context = (
        f"PRD Summary: {state['prd_summary']}\n"
        f"Tech Spec Summary: {state['tech_spec_summary']}\n"
        f"Frontend Summary: {state['frontend_code_summary']}\n"
        f"Backend Summary: {state['backend_code_summary']}"
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
# 4. 라우팅 로직 (Conditional Edges)
# ==========================================
def pm_router(state: ProjectState) -> str:
    if state.get("needs_revision"):
        if state.get("pm_retry_count", 0) >= state.get("max_review_iterations", 3):
            print("🚨 [WARNING] PM 기획 수정 최대 한도 초과. 강제 진행합니다.")
            return "proceed"
        return "revision"
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
        print("🚨 [CRITICAL] 결함 발견! 프론트엔드/백엔드 코드를 재수정하기 위해 Rollback 합니다.")
        return "rollback"
    
    print("✅ 리뷰 통과 또는 최대 반복 횟수 도달. QA 단계로 넘어갑니다.")
    return "proceed"

# ==========================================
# 5. LangGraph 파이프라인 조립 및 영구 체크포인트 설정
# ==========================================
workflow = StateGraph(ProjectState)

workflow.add_node("PM", run_pm)
workflow.add_node("Architect", run_architect)
workflow.add_node("Tech_Lead", run_tech_lead)
workflow.add_node("Frontend", run_frontend)
workflow.add_node("Backend", run_backend)
workflow.add_node("Reviewer", run_reviewer)
workflow.add_node("QA", run_qa)

workflow.set_entry_point("PM")

workflow.add_conditional_edges("PM", pm_router, {"revision": "PM", "proceed": "Architect"})
workflow.add_conditional_edges("Architect", architect_router, {"revision": "Architect", "proceed": "Tech_Lead"})

workflow.add_edge("Tech_Lead", "Frontend")
workflow.add_edge("Frontend", "Backend")
workflow.add_edge("Backend", "Reviewer")

workflow.add_conditional_edges("Reviewer", reviewer_router, {"rollback": "Frontend", "proceed": "QA"})
workflow.add_edge("QA", END)

# [수정] In-Memory를 영구 저장 로컬 SQLite DB로 교체
conn = sqlite3.connect("pipeline_state.db", check_same_thread=False)
memory = SqliteSaver(conn)

app = workflow.compile(
    checkpointer=memory,
    interrupt_after=["PM", "Architect"]
)

if __name__ == "__main__":
    print("다중 에이전트 자동화 파이프라인 그래프 조립 완료.")