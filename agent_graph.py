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

# 중앙화된 config 상수 임포트
import config

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
    
    save_artifact_to_disk(state.get("output_dir", ""), config.OUTPUT_ARTIFACTS["master_prd"], output)
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
        
    wbs_path = state.get("wbs_master_plan_path", config.WBS_FILE)
    save_artifact_to_disk(state.get("output_dir", ""), wbs_path, json_str)
    print(f"✅ [PMO] WBS 마스터 플랜 생성 완료: {wbs_path}")
    
    return state

# ==========================================
# [Track 1] 스프린트 실행 (컨베이어 벨트) 에이전트 노드
# ==========================================

def run_architect(state: ProjectState) -> ProjectState:
    print("[Agent] Architect 실행 중...")
    
    # WBS 태스크를 IN_PROGRESS로 업데이트하여 대시보드에 진행 상황 전파
    task_id = state.get("current_sprint_task_id")
    wbs_path = state.get("wbs_master_plan_path")
    if task_id and wbs_path:
        from nodes.utils.wbs_manager import WBSManager
        WBSManager.set_status(wbs_path, task_id, "IN_PROGRESS")
        
    context = f"Master PRD: {state.get('prd_summary')}"
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    wbs_path = state.get("wbs_master_plan_path", config.WBS_FILE)
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

    save_artifact_to_disk(state.get("output_dir", ""), config.OUTPUT_ARTIFACTS["architecture"], output)
    state["architecture_doc"] = output
    state["architecture_summary"] = summary
    state["needs_revision"] = False
    return state

# 🚨 [신규 추가] main.py의 버그를 완벽히 우회하는 물리적 HOTL(대기) 노드
def run_hotl(state: ProjectState) -> ProjectState:
    print("\n" + "="*60)
    print("⏸️ [HOTL] 파이프라인 일시 정지 (Architect 설계 확인 및 승인 대기)")
    print("="*60)
    user_input = input("\n📝 [설계 승인(Enter)] / [수정 피드백 입력] / [종료(exit)]:\n> ").strip()
    
    if user_input.lower() == 'exit':
        print("🛑 시스템을 종료합니다.")
        import sys
        sys.exit(0)
    
    if user_input:
        q = state.get("human_feedback_queue", [])
        q.append(user_input)
        state["human_feedback_queue"] = q
        state["needs_revision"] = True
        print("🔄 피드백이 접수되었습니다. Architect 노드로 롤백하여 재설계합니다...")
    else:
        state["needs_revision"] = False
        print("▶️ 설계가 승인되었습니다. Tech Lead 노드로 진행합니다...")
        
    return state

def run_tech_lead(state: ProjectState) -> ProjectState:
    task_id = state.get("current_sprint_task_id", "Unknown")
    print(f"\n[Agent] Tech Lead 실행 중... [Task: {task_id}]")
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    
    # Tech Lead에게도 현재 Task의 스코프를 락(Lock)으로 걸어줍니다.
    wbs_path = state.get("wbs_master_plan_path", config.WBS_FILE)
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
        f"Master PRD Summary: {state['prd_summary']}\n"
        f"Arch Summary: {state['architecture_summary']}\n"
        f"--- [오늘 구현해야 할 정확한 WBS Task ({task_id})] ---\n"
        f"{task_info}\n"
        "-------------------------------------------\n"
        "🚨 [최고 중요 지시사항]: Architect가 이미 전체 구조와 DB 스키마를 짰습니다. "
        "당신은 절대 구조를 다시 짜거나 중복 서술하지 마십시오. 오직 위 WBS Task의 'scope' 기능을 구현하기 위해, "
        "Frontend와 Backend 개발자가 당장 오늘 생성/수정해야 할 '물리적 파일 목록'과 '함수/API 시그니처'만 간결하고 명확하게 기술하십시오."
    )
    
    output = harness.execute(
        role_name="tech_lead_skill",
        context_data=context,
        feedback=feedback,
        previous_output=state.get("tech_spec")
    )
    summary = harness.summarize_context(output)
    
    save_artifact_to_disk(state.get("output_dir", ""), config.OUTPUT_ARTIFACTS["tech_spec"], output)
    state["tech_spec"] = output
    state["tech_spec_summary"] = summary
    return state

def run_frontend(state: ProjectState) -> ProjectState:
    print(f"[Agent] Frontend Engineer 실행 중... (빌드 루프 횟수: {state.get('developer_retry_count', 0)})")
    build_err = state.get("build_error_log", "")
    
    # 오직 Tech Spec '원본'만 제공하여 토큰 절약 및 집중도 향상
    context = f"--- [Tech Spec (기술 명세서)] ---\n{state.get('tech_spec', '')}"

    if build_err:
        context += (
            f"\n\n🚨 [빌드 오류 피드백 발생] 이전 컴파일이 실패했습니다. 에러 로그를 분석하십시오:\n{build_err}\n\n"
            f"⚠️ [절대 주의]: 오류를 해결하기 위해 수정이 필요한 '특정 파일'의 코드만 <file> 태그로 묶어서 제출하십시오. "
            f"에러와 무관한 전체 코드를 처음부터 다시 작성하는 행위를 엄격히 금지합니다."
        )
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    output = harness.execute(role_name="frontend_skill", context_data=context, feedback=feedback, previous_output=state.get("frontend_code"))
    
    save_artifact_to_disk(state.get("output_dir", ""), config.OUTPUT_ARTIFACTS["frontend"], output)
    state["frontend_code"] = output
    state["frontend_code_summary"] = harness.summarize_context(output)
    return state

def run_backend(state: ProjectState) -> ProjectState:
    print("[Agent] Backend Engineer 실행 중...")
    build_err = state.get("build_error_log", "")
    
    # Tech Spec 원본만 제공
    context = f"--- [Tech Spec (기술 명세서)] ---\n{state.get('tech_spec', '')}"
 
    if build_err:
        context += (
            f"\n\n🚨 [빌드 오류 피드백 발생] 이전 컴파일이 실패했습니다. 에러 로그를 분석하십시오:\n{build_err}\n\n"
            f"⚠️ [절대 주의]: 오류를 해결하기 위해 수정이 필요한 '특정 파일'의 코드만 <file> 태그로 묶어서 제출하십시오. "
            f"에러와 무관한 전체 코드를 처음부터 다시 작성하는 행위를 엄격히 금지합니다."
        )
        
    feedback = state["human_feedback_queue"].pop() if state["human_feedback_queue"] else None
    output = harness.execute(role_name="backend_skill", context_data=context, feedback=feedback, previous_output=state.get("backend_code"))
    
    save_artifact_to_disk(state.get("output_dir", ""), config.OUTPUT_ARTIFACTS["backend"], output)
    state["backend_code"] = output
    state["backend_code_summary"] = harness.summarize_context(output)
    return state

# agent_graph.py 내부 수정 (기존 run_reviewer 함수 덮어쓰기)

def run_reviewer(state: ProjectState) -> ProjectState:
    print(f"[Agent] Reviewer 실행 중... (코드 품질 리포트 작성)")
    feedback = state.get("human_feedback_queue", [])
    current_feedback = feedback.pop() if feedback else None
    if feedback != state.get("human_feedback_queue"):
        state["human_feedback_queue"] = feedback

    context = (
        f"Arch Summary: {state.get('architecture_summary', '')}\n"
        f"Frontend Code: {state.get('frontend_code_summary', '')}\n"
        f"Backend Code: {state.get('backend_code_summary', '')}"
    )
    output = harness.execute(role_name="reviewer_skill", context_data=context, feedback=current_feedback, previous_output=state.get("code_review_report"))
    
    # 1. 스프린트 완료 시 WBS 상태를 DONE으로 업데이트
    task_id = state.get("current_sprint_task_id", "unknown_task")
    wbs_path = state.get("wbs_master_plan_path")
    if task_id and wbs_path:
        from nodes.utils.wbs_manager import WBSManager
        WBSManager.set_status(wbs_path, task_id, "DONE")
        
    save_artifact_to_disk(state.get("output_dir", ""), config.OUTPUT_ARTIFACTS["review"], output)
    state["code_review_report"] = output
    state["code_review_report_summary"] = harness.summarize_context(output)
    
    # 2. [신규] Git Layer 자동화 커밋 및 State 연동
    from nodes.utils.git_manager import GitManager
    workspace_root = state.get("workspace_root", "./workspace")
    git_mgr = GitManager(workspace_root)
    
    commit_hash = git_mgr.commit_sprint_changes(task_id, state)
    if commit_hash:
        if "git_info" not in state:
            state["git_info"] = {}
        state["git_info"]["last_commit_hash"] = commit_hash
        state["git_info"]["last_commit_timestamp"] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        state["git_info"]["last_commit_task"] = task_id
        
    return state

# ==========================================
# [Track 3] 통합 시스템 릴리즈 QA 노드
# ==========================================

def run_qa(state: ProjectState) -> ProjectState:
    print("[Agent] QA Analyst 실행 중... 전체 시스템 통합 검증")
    
    context = (
        f"Master PRD Summary: {state.get('prd_summary', '')}\n"
        f"Project Name: {state.get('project_name', '')}\n"
    )
    
    # QA 에이전트가 코드를 직접 들여다볼 수 있도록 실제 산출물 맥락 추가
    if state.get("frontend_code_summary"):
        context += f"\n[Frontend Code Summary]\n{state['frontend_code_summary']}\n"
    if state.get("backend_code_summary"):
        context += f"\n[Backend Code Summary]\n{state['backend_code_summary']}\n"
    if state.get("code_review_report_summary"):
        context += f"\n[Sprint Review Report]\n{state['code_review_report_summary']}\n"

    output = harness.execute(role_name="qa_skill", context_data=context)
    
    save_artifact_to_disk(state.get("output_dir", ""), config.OUTPUT_ARTIFACTS["qa"], output)
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
        if state.get("architect_retry_count", 0) >= state.get("max_review_iterations", config.MAX_REVIEW_ITERATIONS):
            print("🚨 [WARNING] 설계 수정 한도 초과. 강제 진행합니다.")
            return "proceed"
        return "revision"
    return "proceed"

def map_builder_router(state: ProjectState) -> str:
    status = state.get("build_status", "pending")
    retry_count = state.get("developer_retry_count", 0)
    max_retries = config.MAX_BUILD_RETRIES
    
    if status == "failed":
        if retry_count <= max_retries:
            print(f"🔄 [Build Fail Loop] 에러 로그 주입 후 개발자 롤백 (재시도: {retry_count}/{max_retries})")
            return "recode"
        else:
            print(f"🚨 [System] 최대 빌드 재시도 횟수({max_retries})를 초과하여 강제로 다음 노드(Reviewer)로 진행합니다.")
            return "proceed"
            
    print("✅ 빌드 및 컴파일 무결성 검증 완료! 리뷰어 단계로 진입합니다.")
    return "proceed"

def reviewer_router(state: ProjectState) -> str:
    print("⏩ [Fast-Track] 리뷰 리포트 작성 완료. 일일 스프린트를 즉시 종료합니다.")
    return "proceed"

# ==========================================
# LangGraph 파이프라인 조립 (V4.0)
# ==========================================
workflow = StateGraph(ProjectState)

workflow.add_node("Master_PM", run_master_pm)
workflow.add_node("Master_PMO", run_master_pmo)
workflow.add_node("Architect", run_architect)
workflow.add_node("HOTL", run_hotl) # 🚨 물리적 HOTL 노드 추가
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
workflow.add_edge("Architect", "HOTL") # Architect 종료 후 무조건 HOTL 진입
workflow.add_conditional_edges("HOTL", architect_router, {"revision": "Architect", "proceed": "Tech_Lead"}) # HOTL 입력 결과에 따라 분기
workflow.add_edge("Tech_Lead", "Frontend")
workflow.add_edge("Frontend", "Backend")
workflow.add_edge("Backend", "CodeBuilder") 
workflow.add_conditional_edges("CodeBuilder", map_builder_router, {"recode": "Frontend", "proceed": "Reviewer"})
workflow.add_conditional_edges("Reviewer", reviewer_router, {"rollback": "Frontend", "proceed": END})

# Track 3 흐름
workflow.add_edge("QA", END)

conn = sqlite3.connect(config.PIPELINE_DB_FILE, check_same_thread=False)
memory = SqliteSaver(conn)

app = workflow.compile(
    checkpointer=memory
    # 🚨 LangGraph 엔진의 interrupt 기능 완전 제거 (버그 원천 차단)
)

if __name__ == "__main__":
    print("V4.0 다중 에이전트 자동화 파이프라인 그래프 조립 완료.")