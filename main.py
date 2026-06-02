import os
import sys
import time
import subprocess
import traceback
import webbrowser  # 브라우저 자동 실행용
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 0순위 config 상수 및 1순위 state 헬퍼 함수 임포트
from agent_graph import app
from state import ProjectState, create_initial_state
from config import WBS_FILE, MASTER_PRD_FILE

DASHBOARD_PROCESS = None

print("⚙️ Gemini LLM E2E 파이프라인 가동 (V5.0 Core Architecture)")

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

# ==========================================================
# 🚀 [라이브 프리뷰] 결과물 즉시 확인 로직
# ==========================================================
def _launch_live_preview(state_values):
    workspace = state_values.get("project_output_path", "")
    if not workspace or not os.path.exists(workspace):
        return
        
    ans = input("\n🌐 [Live Preview] 빌드가 성공했습니다! 로컬 웹 서버를 띄워 결과물을 확인하시겠습니까? (y/n):\n> ").strip().lower()
    if ans == 'y':
        print("\n🚀 라이브 프리뷰 서버를 기동합니다...")
        try:
            # 1. 프론트엔드 (React/Vite) 서버 기동
            frontend_dir = os.path.join(workspace, "frontend")
            if not os.path.exists(frontend_dir) and os.path.exists(os.path.join(workspace, "package.json")):
                frontend_dir = workspace
                
            if os.path.exists(frontend_dir):
                dist_dir = os.path.join(frontend_dir, "dist")
                build_dir = os.path.join(frontend_dir, "build")
                target_dir = dist_dir if os.path.exists(dist_dir) else build_dir if os.path.exists(build_dir) else frontend_dir
                
                print(f"▶️ 프론트엔드 정적 서버 기동 중... ({target_dir})")
                npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
                subprocess.Popen([npx_cmd, "serve", "-s", target_dir, "-p", "3000"], cwd=frontend_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2) 
                webbrowser.open("http://localhost:3000")
                
            # 2. 백엔드 (FastAPI) 서버 기동
            backend_dir = os.path.join(workspace, "backend")
            if not os.path.exists(backend_dir) and os.path.exists(os.path.join(workspace, "requirements.txt")):
                backend_dir = workspace
                
            if os.path.exists(backend_dir):
                print(f"▶️ 파이썬 백엔드 서버 기동 중... ({backend_dir})")
                entry = state_values.get("executable_entry_point", "main.py")
                script_name = os.path.basename(entry)
                python_cmd = sys.executable
                subprocess.Popen([python_cmd, script_name], cwd=backend_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2)
                if not os.path.exists(frontend_dir): 
                    webbrowser.open("http://localhost:8000")
                    
            print("\n✅ 서버가 백그라운드에서 기동되었습니다. 브라우저를 확인하세요!")
            print("💡 (서버 프로세스는 터미널을 닫으면 함께 종료됩니다.)")
            
        except Exception as e:
            print(f"⚠️ 서버 기동 중 오류 발생: {e}")

# ==========================================================
# 🚀 [코어 분리] UI에서 직접 호출할 수 있는 Track별 실행 함수들
# ==========================================================
def execute_track_0(project_name: str, initial_idea: str):
    """[Track 0] 마스터 플랜 수립 (웹 UI 호출용)"""
    print(f"\n🚀 [System] Track 0: Master PM & PMO 에이전트 가동 시작 ({project_name})")
    config = {"configurable": {"thread_id": "master_planning_thread"}}
    initial_input = create_initial_state(
        factory_mode="PLANNING",
        project_name=project_name,
        initial_idea=initial_idea,
        wbs_master_plan_path=WBS_FILE,
        output_dir="." 
    )
    try:
        for event in app.stream(initial_input, config=config):
            for key, value in event.items():
                print(f"✅ [{key}] 에이전트 작업 완료!")
        print("\n🔔 [System] 전체 기획서 및 마스터플랜 수립 완료.")
        return True
    except Exception as e:
        print(f"\n🚨 Track 0 오류 발생: {e}")
        traceback.print_exc()
        return False

def execute_track_1_sprint(task_id: str):
    """[Track 1] 일일 스프린트 팩토리 가동 (웹 UI 호출용)"""
    print(f"\n🚀 [System] Track 1: Task [{task_id}] 일일 스프린트 가동 시작")
    if not os.path.exists(WBS_FILE) or not os.path.exists(MASTER_PRD_FILE):
        print("⛔ [Error] Master PRD 또는 WBS 파일이 없습니다.")
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config = {"configurable": {"thread_id": f"sprint_thread_{task_id}"}}
    master_prd = get_master_prd_content()
    
    initial_input = create_initial_state(
        factory_mode="EXECUTION",
        current_sprint_task_id=task_id,
        wbs_master_plan_path=WBS_FILE,
        prd=master_prd, 
        prd_summary=master_prd[:1000] + "\n...(후략)",
        output_dir=f"outputs/{task_id}_{timestamp}"
    )
    
    return _run_pipeline_stream(initial_input, config)

def execute_track_3_qa():
    """[Track 3] 통합 시스템 릴리즈 QA (웹 UI 호출용)"""
    print("\n🔬 [System] Track 3: 통합 테스트 릴리즈 프로세스 가동")
    if not os.path.exists(MASTER_PRD_FILE):
        print("⛔ [Error] Master PRD 파일이 없습니다.")
        return False
        
    config = {"configurable": {"thread_id": "global_qa_release_thread"}}
    master_prd = get_master_prd_content()
    initial_input = create_initial_state(
        factory_mode="QA_RELEASE",
        prd=master_prd,
        prd_summary=master_prd[:1000],
        output_dir="outputs/Final_Release"
    )
    return _run_pipeline_stream(initial_input, config)

def resume_hotl_sprint(task_id: str, user_feedback: str = ""):
    """중단된 스프린트 이어서 진행 (웹 UI HOTL 처리용)"""
    config = {"configurable": {"thread_id": f"sprint_thread_{task_id}"}}
    snapshot = app.get_state(config)
    
    if not snapshot.values:
        print("🚨 DB 기록이 없습니다.")
        return False
        
    if user_feedback:
        print(f"\n🔄 피드백 접수: '{user_feedback}'")
        current_state = snapshot.values
        queue = current_state.get("human_feedback_queue", [])
        queue.append(user_feedback)
        app.update_state(config, {"human_feedback_queue": queue, "needs_revision": True})
    else:
        print("\n▶️ 승인되었습니다. 재개합니다...")
        app.update_state(config, {"needs_revision": False})
        
    return _run_pipeline_stream(None, config)

def _run_pipeline_stream(initial_input, config):
    """내부 파이프라인 스트리밍 실행기 (CLI와 WEB 공용)"""
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
                print(f"🎉 [파이프라인 완전 종료] 모든 산출물이 저장되었습니다.")
                print("="*60)
                
                # 🚀 [Live Preview 실행] 빌드가 성공했다면 즉시 브라우저 실행
                state_values = snapshot.values
                if state_values.get("build_status") == "success":
                    _launch_live_preview(state_values)
                    
                return "COMPLETED"
            else:
                print("\n" + "="*60)
                print(f"⏸️ [HOTL] 파이프라인 일시 정지 (현재 대기 노드: {snapshot.next})")
                print("="*60)
                return "PAUSED"  # 웹 UI에 상태를 반환하고 즉시 제어권 넘김
                
    except Exception as e:
        print(f"\n🚨 파이프라인 실행 중 치명적 오류 발생: {e}")
        print("\n" + "🔥"*30)
        print("🔍 [상세 디버그 추적 로그 - Stack Trace]")
        traceback.print_exc()
        print("🔥"*30 + "\n")
        return "ERROR"

# ==========================================================
# 🖥️ CLI 실행 인터페이스 (개발자 및 디버깅용 유지)
# ==========================================================
def run_cli():
    print("=" * 65)
    print(" 🏭 범용 자율형 AI 소프트웨어 팩토리 플랫폼 (V5.0 CLI/WEB Core)")
    print("=" * 65)

    while True:
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

        if choice == '0':
            p_name = input("\n🏷️ 프로젝트 명칭 (예: 제조업 ERP 미니 대시보드):\n> ").strip()
            idea = input("\n💡 플랫폼이 만들고자 하는 전체 비즈니스 요구사항을 상세히 입력하세요:\n> ").strip()
            execute_track_0(p_name, idea)
            
        elif choice == '1':
            t_id = input("\n🎯 오늘 가동할 WBS Task ID (예: E2E-01):\n> ").strip()
            status = execute_track_1_sprint(t_id)
            if status == "PAUSED":
                _handle_cli_hotl(t_id)
                
        elif choice == '2':
            t_id = input("\n📂 이어서 진행할 Task ID를 입력하세요:\n> ").strip()
            _handle_cli_hotl(t_id)
            
        elif choice == '3':
            execute_track_3_qa()

def _handle_cli_hotl(task_id: str):
    """CLI 전용 HOTL 루프"""
    while True:
        user_input = input("\n📝 [승인(Enter)] / [피드백 입력] / [종료(exit)]:\n> ").strip()
        if user_input.lower() == 'exit':
            break
        status = resume_hotl_sprint(task_id, user_input)
        if status == "COMPLETED" or status == "ERROR":
            break

if __name__ == "__main__":
    run_cli()