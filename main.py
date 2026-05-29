import os
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from agent_graph import app, harness, ProjectState

# 1. 환경 변수 로드
load_dotenv()

# 2. 실제 Gemini 2.5 모델 인스턴스 주입
print("⚙️ Gemini LLM 엔진을 초기화합니다...")
llm_pro = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)
llm_flash = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

harness.llm_pro = llm_pro
harness.llm_flash = llm_flash

def create_initial_state(idea: str) -> ProjectState:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "initial_idea": idea,
        "human_feedback_queue": [],
        "pipeline_status": "running",
        "error_log": "",
        "output_dir": f"outputs/{timestamp}",
        "review_iteration": 0,
        "max_review_iterations": 3,
        "pm_retry_count": 0,
        "architect_retry_count": 0,
        "needs_revision": False,
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
    
    idea = input("\n💡 개발하고자 하는 소프트웨어의 초기 아이디어를 입력하세요:\n> ")
    if not idea.strip():
        print("아이디어가 입력되지 않아 실행을 종료합니다.")
        return

    state = create_initial_state(idea)
    
    # [수정] thread_id 생성 및 config 주입을 통한 메모리 격리
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    
    print(f"\n📂 산출물 저장 예정 경로: {state['output_dir']}")
    print(f"🔗 세션 ID (Thread): {session_id}")
    print("시동을 겁니다. 파이프라인 실행 중...\n")

    try:
        # 1. 초기 그래프 스트리밍
        for event in app.stream(state, config=config):
            for key, value in event.items():
                print(f"✅ [{key}] 에이전트 작업 완료!")
                time.sleep(1)

        # 2. HOTL 루프 제어
        while True:
            snapshot = app.get_state(config)
            
            # 다음 실행할 노드가 없으면(그래프 끝 도달) 루프 탈출
            if not snapshot.next:
                break
                
            current_state = snapshot.values
            
            print("\n" + "="*60)
            print("⏸️ [HOTL] 파이프라인 일시 정지 (사용자 검토 대기)")
            print("="*60)
            print("현재 에이전트의 산출물이 생성되었습니다. 로컬 output 디렉토리에서 문서를 확인하세요.")
            
            user_input = input("\n📝 [승인(Enter)] / [피드백 입력 (반려 및 델타 업데이트)]:\n> ").strip()
            
            if user_input == "":
                print("\n▶️ 승인되었습니다. 다음 단계로 파이프라인을 재개합니다...")
                app.update_state(config, {"needs_revision": False})
            else:
                print(f"\n🔄 피드백이 접수되었습니다: '{user_input}'")
                print("해당 노드를 재실행하여 산출물을 델타 업데이트합니다.")
                
                queue = current_state.get("human_feedback_queue", [])
                queue.append(user_input)
                
                # 라우터가 이전 노드로 회귀할 수 있도록 needs_revision 플래그를 True로 변경
                app.update_state(config, {
                    "human_feedback_queue": queue,
                    "needs_revision": True
                })
            
            # None을 전달하여 중단된 지점부터 스트리밍 재개 (이때 라우터가 플래그를 평가함)
            for event in app.stream(None, config=config):
                for key, value in event.items():
                    print(f"✅ [{key}] 에이전트 작업 완료!")
                    time.sleep(1)

        print("\n🎉 모든 파이프라인 프로세스가 성공적으로 완료되었습니다!")
        
    except Exception as e:
        print(f"\n🚨 파이프라인 실행 중 치명적 오류 발생: {e}")

if __name__ == "__main__":
    run_pipeline()