import os
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from harness import AgentHarness

# ==========================================
# 1. 블랙보드 스키마 정의 (ProjectState)
# ==========================================
class ProjectState(TypedDict):
    # 입력 및 메타데이터
    initial_idea: str
    human_feedback_queue: List[str]
    
    # 상태 관제 및 로깅
    pipeline_status: str
    error_log: str
    output_dir: str
    
    # 루프 제어 변수
    review_iteration: int
    max_review_iterations: int
    
    # 에이전트 산출물 (원본 및 요약본)
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
# 2. 하네스 초기화 및 글로벌 설정
# ==========================================
# 실제 환경에 맞게 LLM 인스턴스를 주입해야 합니다. (예: ChatOpenAI, ChatGoogleGenerativeAI 등)
llm_pro = "pro_model_instance"      # 실제 LangChain LLM 객체로 대체 필요
llm_flash = "flash_model_instance"  # 실제 LangChain LLM 객체로 대체 필요
harness = AgentHarness(llm_pro, llm_flash)

# ==========================================
# 3. 노드 실행 함수 정의
# ==========================================
def run_pm(state: ProjectState) -> ProjectState:
    print("[Agent] PM 실행 중...")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    # 하네스를 통해 PM 스킬 실행
    output = harness.execute(
        role_name="pm_skill",
        context_data=f"Initial Idea: {state['initial_idea']}",
        feedback=feedback,
        previous_output=state.get("prd")
    )
    summary = harness.summarize_context(output)
    
    state["prd"] = output
    state["prd_summary"] = summary
    return state

def run_architect(state: ProjectState) -> ProjectState:
    print("[Agent] Architect 실행 중...")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    output = harness.execute(
        role_name="architect_skill",
        context_data=f"PRD Summary: {state['prd_summary']}",
        feedback=feedback,
        previous_output=state.get("architecture_doc")
    )
    summary = harness.summarize_context(output)
    
    state["architecture_doc"] = output
    state["architecture_summary"] = summary
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
    
    state["code_review_report"] = output
    state["code_review_report_summary"] = summary
    state["review_iteration"] += 1  # 리뷰 반복 횟수 1 증가
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
    
    state["qa_report"] = output
    state["qa_report_summary"] = summary
    state["pipeline_status"] = "completed"
    return state

# ==========================================
# 4. 라우팅 로직 (Conditional Edges)
# ==========================================
def reviewer_router(state: ProjectState) -> str:
    """
    Reviewer의 검토 결과를 분석하여 다음 진행 방향을 결정합니다.
    """
    report = state.get("code_review_report", "")
    iteration = state.get("review_iteration", 0)
    max_iter = state.get("max_review_iterations", 3)
    
    # 조건 1: [CRITICAL] 태그 존재 및 반복 한도 미도달 ➔ Frontend로 롤백 (재개발)
    if "[CRITICAL]" in report and iteration < max_iter:
        print("🚨 [CRITICAL] 결함 발견! 프론트엔드/백엔드 코드를 재수정하기 위해 Rollback 합니다.")
        return "rollback"
        
    # 조건 2: 무결함 또는 반복 한도 도달 ➔ QA 노드로 강제 진행
    print("✅ 리뷰 통과 또는 최대 반복 횟수 도달. QA 단계로 넘어갑니다.")
    return "proceed"

# ==========================================
# 5. LangGraph 파이프라인 조립
# ==========================================
workflow = StateGraph(ProjectState)

# 노드 추가
workflow.add_node("PM", run_pm)
workflow.add_node("Architect", run_architect)
workflow.add_node("Tech_Lead", run_tech_lead)
workflow.add_node("Frontend", run_frontend)
workflow.add_node("Backend", run_backend)
workflow.add_node("Reviewer", run_reviewer)
workflow.add_node("QA", run_qa)

# 엣지 연결 (정상 흐름)
workflow.set_entry_point("PM")
workflow.add_edge("PM", "Architect")
workflow.add_edge("Architect", "Tech_Lead")
workflow.add_edge("Tech_Lead", "Frontend")
workflow.add_edge("Frontend", "Backend")
workflow.add_edge("Backend", "Reviewer")

# 조건부 분기 (리뷰 결과에 따른 롤백 or 진행)
workflow.add_conditional_edges(
    "Reviewer",
    reviewer_router,
    {
        "rollback": "Frontend",  # 반려 시 Frontend부터 다시 파이프라인 수행
        "proceed": "QA"          # 통과 시 QA로 이동
    }
)

# QA 종료 지점 연결
workflow.add_edge("QA", END)

# 그래프 컴파일 (HOTL - 사용자 개입 정지 시점을 설정할 수 있습니다)
app = workflow.compile()

if __name__ == "__main__":
    print("다중 에이전트 자동화 파이프라인 그래프 조립 완료.")