import os
import time
from datetime import datetime
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from agent_graph import app, harness, ProjectState

# 1. 환경 변수 로드 (.env 파일에 GOOGLE_API_KEY 가 있어야 합니다)
load_dotenv()

# 2. 실제 Gemini 모델 인스턴스 주입 (Pro: 복잡한 추론, Flash: 요약 및 단순 작업)
print("⚙️ Gemini LLM 엔진을 초기화합니다...")
llm_pro = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.2)
llm_flash = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)

# 하네스 객체에 실제 모델 덮어쓰기
harness.llm_pro = llm_pro
harness.llm_flash = llm_flash

def create_initial_state(idea: str) -> ProjectState:
    """초기 상태(Blackboard)를 완전히 비워진 상태로 생성합니다."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "initial_idea": idea,
        "human_feedback_queue": [],
        "pipeline_status": "running",
        "error_log": "",
        "output_dir": f"outputs/{timestamp}",
        "review_iteration": 0,
        "max_review_iterations": 3,
        "prd": "", "prd_summary": "",
        "architecture_doc": "", "architecture_summary": "",
        "tech_spec": "", "tech_spec_summary": "",
        "frontend_code": "", "frontend_code_summary": "",
        "backend_code": "", "backend_code_summary": "",
        "code_review_report": "", "code_review_report_summary": "",
        "qa_report": "", "qa_report_summary": ""
    }

def run_pipeline():
    print("=" * 60)
    print("🚀 다중 에이전트 자동화 파이프라인 (v2.4) 가동 준비 완료")
    print("=" * 60)
    
    # 사용자로부터 초기 아이디어 입력 받기
    idea = input("\n💡 개발하고자 하는 소프트웨어의 초기 아이디어를 입력하세요:\n> ")
    if not idea.strip():
        print("아이디어가 입력되지 않아 실행을 종료합니다.")
        return

    # 상태 초기화
    state = create_initial_state(idea)
    print(f"\n📂 산출물 저장 예정 경로: {state['output_dir']}")
    print("시동을 겁니다. 파이프라인 실행 중...\n")

    # LangGraph 실행 및 상태 스트리밍 출력
    try:
        # app.stream은 각 노드(에이전트)가 실행을 마칠 때마다 상태를 yield 합니다.
        for output in app.stream(state):
            for key, value in output.items():
                print(f"✅ [{key}] 에이전트 작업 완료!")
                time.sleep(1) # 로그 가독성을 위한 짧은 대기
                
        print("\n🎉 모든 파이프라인 프로세스가 성공적으로 완료되었습니다!")
        
    except Exception as e:
        print(f"\n🚨 파이프라인 실행 중 치명적 오류 발생: {e}")

if __name__ == "__main__":
    run_pipeline()