import os
import time
from datetime import datetime
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from agent_graph import app, harness, ProjectState

load_dotenv()

# [복구됨] 모델 라우팅을 위해 Pro와 Flash를 각각 올바르게 초기화합니다.
print("⚙️ Gemini LLM 엔진을 초기화합니다... (Model Router 및 지수 백오프 방어막 가동)")
llm_pro = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)
llm_flash = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

harness.llm_pro = llm_pro
harness.llm_flash = llm_flash

def create_initial_state(idea: str, timestamp: str) -> ProjectState:
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
    
    print("1. 새 프로젝트 시작")
    print("2. 기존 프로젝트 이어서 진행 (Resume)")
    choice = input("\n원하시는 작업을 선택하세요 (1 또는 2):\n> ").strip()

    if choice == "2":
        session_id = input("\n📂 이어서 진행할 폴더명(세션 ID)을 입력하세요 (예: 20260529_101255):\n> ").strip()
        config = {"configurable": {"thread_id": session_id}}
        
        snapshot = app.get_state(config)
        if not snapshot.values:
            print("🚨 해당 세션의 저장된 상태를 찾을 수 없습니다. (DB에 기록이 없음)")
            return
            
        print(f"\n🔄 세션 '{session_id}'을(를) DB에서 성공적으로 복구했습니다.")
        if snapshot.next:
            print(f"▶️ 중단된 노드 {snapshot.next} 부터 실행을 재개합니다...\n")
        else:
            print("✅ 이 파이프라인은 이미 끝까지 완료된 상태입니다.")
            return
            
        initial_input = None 
        
    else:
        idea = input("\n💡 개발하고자 하는 소프트웨어의 초기 아이디어를 입력하세요:\n> ")
        if not idea.strip():
            print("아이디어가 입력되지 않아 실행을 종료합니다.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = timestamp 
        config = {"configurable": {"thread_id": session_id}}
        initial_input = create_initial_state(idea, timestamp)
        
        print(f"\n📂 산출물 저장 예정 경로: {initial_input['output_dir']}")
        print(f"🔗 세션 ID (Thread): {session_id}")
        print("시동을 겁니다. 파이프라인 실행 중...\n")

    try:
        for event in app.stream(initial_input, config=config):
            for key, value in event.items():
                print(f"✅ [{key}] 에이전트 작업 완료!")
                time.sleep(1)

        while True:
            snapshot = app.get_state(config)
            
            if not snapshot.next:
                break
                
            current_state = snapshot.values
            
            print("\n" + "="*60)
            print("⏸️ [HOTL] 파이프라인 일시 정지 (사용자 검토 대기)")
            print("="*60)
            print("현재 에이전트의 산출물이 생성되었습니다. 로컬 output 디렉토리에서 문서를 확인하세요.")
            
            user_input = input("\n📝 [승인(Enter)] / [피드백 입력 (반려 및 델타 업데이트)] / [종료(exit)]:\n> ").strip()
            
            if user_input.lower() == 'exit':
                print("\n🛑 파이프라인을 안전하게 일시 중단합니다. 나중에 [2. 이어서 진행] 메뉴를 통해 재개할 수 있습니다.")
                break
            
            if user_input == "":
                print("\n▶️ 승인되었습니다. 다음 단계로 파이프라인을 재개합니다...")
                app.update_state(config, {"needs_revision": False})
            else:
                print(f"\n🔄 피드백이 접수되었습니다: '{user_input}'")
                print("해당 노드를 재실행하여 산출물을 델타 업데이트합니다.")
                
                queue = current_state.get("human_feedback_queue", [])
                queue.append(user_input)
                
                app.update_state(config, {
                    "human_feedback_queue": queue,
                    "needs_revision": True
                })
            
            for event in app.stream(None, config=config):
                for key, value in event.items():
                    print(f"✅ [{key}] 에이전트 작업 완료!")
                    time.sleep(1)

        if not snapshot.next and user_input.lower() != 'exit':
            print("\n🎉 모든 파이프라인 프로세스가 성공적으로 완료되었습니다!")
        
    except Exception as e:
        print(f"\n🚨 파이프라인 실행 중 치명적 오류 발생: {e}")

if __name__ == "__main__":
    run_pipeline()