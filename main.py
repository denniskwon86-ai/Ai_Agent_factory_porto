import os
import sys
import time
import json
import re
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agent_graph import app, harness, ProjectState

WBS_FILE = "00_wbs_master_plan.json"
MASTER_PRD_FILE = "00_master_prd.md"
DASHBOARD_PROCESS = None

print("⚙️ Gemini LLM E2E 파이프라인 가동 (V4.0 3-Track Architecture)")

def launch_pmo_dashboard():
    global DASHBOARD_PROCESS
    if os.path.exists(WBS_FILE) and DASHBOARD_PROCESS is None:
        print(f"\n📊 [System] WBS 마스터플랜 확인 완료. PMO 대시보드를 백그라운드에서 기동합니다.")
        DASHBOARD_PROCESS = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "pmo_dashboard.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("🌐 대시보드 주소: http://localhost:8501")
        return True
    return DASHBOARD_PROCESS is not None

def get_master_prd_content():
    """루트 경로에 저장된 Master PRD 내용을 읽어옵니다."""
    if os.path.exists(MASTER_PRD_FILE):
        with open(MASTER_PRD_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "⚠️ Master PRD 파일이 루트에 존재하지 않습니다."

def handle_feedback_routing(user_input: str, config: dict):
    # [터보 모드] PM 노드가 없으므로 라우팅 후보군 재설정
    print("\n🔄 델타 업데이트 및 파이프라인 재가동 (Architect 노드 롤백 적용)...")
    current_state = app.get_state(config).values
    queue = current_state.get("human_feedback_queue", [])
    queue.append(user_input)
    
    app.update_state(
        config,
        {"human_feedback_queue": queue, "needs_revision": True},
        as_node="Architect" # 최상단인 설계 노드로 피드백 전송
    )

def run_pipeline():
    print("=" * 65)
    print(" 🏭 범용 자율형 AI 소프트웨어 팩토리 플랫폼 (V4.0)")
    print("=" * 65)

    while True:
        initial_input = None
        dashboard_launched = launch_pmo_dashboard()
        if not dashboard_launched:
            print("\n💡 [System] 수립된 WBS가 없습니다. Track 0부터 시작하세요.")

        print("\n[메뉴를 선택해주세요]")
        print("  [0] 마스터 플랜 수립 (Master PRD 및 WBS 자동 생성)")
        print("  [1] 일일 스프린트 팩토리 가동 (기획 생략 -> 즉시 설계/코딩/빌드)")
        print("  [2] 중단된 스프린트 이어서 진행 (HOTL / 복구)")
        print("  [3] 시스템 통합 QA 및 릴리즈 승인 (모든 Task 종료 후 실행)")
        print("  [q] 파이프라인 종료")
        
        choice = input("\n선택 > ").strip()

        if choice.lower() == 'q':
            print("시스템을 종료합니다.")
            if DASHBOARD_PROCESS:
                DASHBOARD_PROCESS.terminate()
            sys.exit(0)

        # ==========================================================
        # [Track 0] 마스터 플랜 수립
        # ==========================================================
        if choice == '0':
            project_name = input("\n🏷️ 프로젝트 명칭 (예: 제조업 ERP 미니 대시보드):\n> ").strip()
            initial_idea = input("\n💡 플랫폼이 만들고자 하는 전체 비즈니스 요구사항을 상세히 입력하세요:\n> ").strip()
            
            config = {"configurable": {"thread_id": "master_planning_thread"}}
            initial_input = {
                "factory_mode": "PLANNING",
                "project_name": project_name,
                "initial_idea": initial_idea,
                "wbs_master_plan_path": WBS_FILE,
                "human_feedback_queue": [],
                "output_dir": "." 
            }
            
            print("\n🚀 [System] Master PM & PMO 에이전트 가동을 시작합니다...\n")
            try:
                for event in app.stream(initial_input, config=config):
                    for key, value in event.items():
                        print(f"✅ [{key}] 에이전트 작업 완료!")
                print("\n🔔 [System] 전체 기획서 및 마스터플랜 수립 완료. [1]번 메뉴로 가동을 시작하세요.")
                launch_pmo_dashboard()
            except Exception as e:
                print(f"\n🚨 마스터플랜 수립 중 오류 발생: {e}")
            continue

        # ==========================================================
        # [Track 1] 일일 스프린트 팩토리 (초고속 개발 트랙)
        # ==========================================================
        elif choice == '1':
            if not os.path.exists(WBS_FILE) or not os.path.exists(MASTER_PRD_FILE):
                print("\n⛔ [Error] Master PRD 또는 WBS 파일이 없습니다. [0]번을 먼저 실행하세요.")
                continue

            task_id = input("\n🎯 오늘 가동할 WBS Task ID를 입력하세요 (예: E2E-01):\n> ").strip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            config = {"configurable": {"thread_id": f"sprint_thread_{task_id}"}}
            
            master_prd = get_master_prd_content()
            
            initial_input = {
                "factory_mode": "EXECUTION",
                "current_sprint_task_id": task_id,
                "wbs_master_plan_path": WBS_FILE,
                "prd": master_prd, 
                "prd_summary": master_prd[:1000] + "\n...(후략)",
                "output_dir": f"outputs/{task_id}_{timestamp}",
                "human_feedback_queue": [],
                "pipeline_status": "running",
                "review_iteration": 0,
                "max_review_iterations": 1,
                "developer_retry_count": 0,
                "architect_retry_count": 0,
                "needs_revision": False
            }
            
            print(f"\n🚀 [System] Task [{task_id}] 기획(PM) 과정을 생략하고 즉시 시스템 설계(Architect)부터 질주합니다...\n")

        # ==========================================================
        # [Track 2] 중단된 스프린트 복구
        # ==========================================================
        elif choice == "2":
            task_id = input("\n📂 이어서 진행할 Task ID를 입력하세요:\n> ").strip()
            config = {"configurable": {"thread_id": f"sprint_thread_{task_id}"}}
            snapshot = app.get_state(config)
            
            if not snapshot.values:
                print("\n🚨 DB 기록이 없습니다. 새로운 세션은 [1]번 메뉴를 사용하세요.")
                continue
                
            print(f"\n🔄 Task [{task_id}] 세션 준비 완료.")
            if snapshot.next:
                print(f"▶️ 중단된 노드 {snapshot.next} 부터 실행을 재개합니다...\n")
            else:
                print("✅ 이 파이프라인은 이미 끝까지 완료된 상태입니다.")
            initial_input = None

        # ==========================================================
        # [Track 3] 통합 시스템 릴리즈 QA
        # ==========================================================
        elif choice == "3":
            if not os.path.exists(MASTER_PRD_FILE):
                print("\n⛔ [Error] Master PRD 파일이 없어 검증 기준을 알 수 없습니다.")
                continue
                
            print("\n🔬 [System] 통합 테스트 릴리즈 프로세스를 가동합니다.")
            config = {"configurable": {"thread_id": "global_qa_release_thread"}}
            
            initial_input = {
                "factory_mode": "QA_RELEASE",
                "prd": get_master_prd_content(),
                "prd_summary": get_master_prd_content()[:1000],
                "output_dir": "outputs/Final_Release",
                "human_feedback_queue": []
            }

        else:
            print("잘못된 입력입니다.")
            continue

        # ==========================================================
        # 파이프라인 실행 엔진
        # ==========================================================
        try:
            if initial_input is not None:
                for event in app.stream(initial_input, config=config):
                    for key, value in event.items():
                        print(f"✅ [{key}] 에이전트 작업 완료!")
                        time.sleep(1)

            while True:
                snapshot = app.get_state(config)
                
                if not snapshot.next:
                    print("\n" + "="*60)
                    print(f"🎉 [해당 트랙 파이프라인 완전 종료] 모든 산출물이 저장되었습니다.")
                    print("="*60)
                    break 
                else:
                    print("\n" + "="*60)
                    print(f"⏸️ [HOTL] 파이프라인 일시 정지 (현재 대기 노드: {snapshot.next})")
                    print("="*60)
                    user_input = input("\n📝 [승인(Enter)] / [피드백 입력] / [종료(exit)]:\n> ").strip()
                    
                    if user_input.lower() == 'exit':
                        print("\n🛑 파이프라인을 일시 중단합니다.")
                        break 
                    
                    if user_input == "":
                        print("\n▶️ 승인되었습니다. 재개합니다...")
                        app.update_state(config, {"needs_revision": False})
                    else:
                        print(f"\n🔄 피드백 접수: '{user_input}'")
                        current_state = snapshot.values
                        queue = current_state.get("human_feedback_queue", [])
                        queue.append(user_input)
                        app.update_state(config, {"human_feedback_queue": queue, "needs_revision": True})
                    
                    for event in app.stream(None, config=config):
                        for key, value in event.items():
                            print(f"✅ [{key}] 에이전트 작업 완료!")
                            time.sleep(1)
                            
        except Exception as e:
            print(f"\n🚨 파이프라인 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    run_pipeline()