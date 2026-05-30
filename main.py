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

print("⚙️ Gemini LLM E2E 파이프라인 가동 (Dynamic 429 Failover Router 탑재)")
# harness 모듈 내부에서 이미 동적 라우터 예비 탄창이 장전되어 있습니다.

def launch_pmo_dashboard():
    """WBS 파일이 존재할 때만 Streamlit 대시보드를 백그라운드에서 기동하는 안전 함수"""
    if os.path.exists(WBS_FILE):
        print(f"\n📊 [System] WBS 마스터플랜 확인 완료. PMO 대시보드를 백그라운드에서 기동합니다.")
        # subprocess.Popen을 사용하여 메인 파이프라인 블로킹 없이 독립 실행
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "pmo_dashboard.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("🌐 대시보드 주소: http://localhost:8501 (브라우저에서 확인 가능)")
        return True
    return False

def handle_feedback_routing(user_input: str, config: dict):
    """피드백 텍스트를 분석하여 최적의 타겟 노드를 도출하고 LangGraph 상태를 롤백하는 라우터"""
    prompt = f"""당신은 다중 에이전트 파이프라인의 라우팅 감독관입니다.
사용자의 피드백을 분석하여 어떤 에이전트 단계부터 재시작해야 할지 결정하십시오.

[선택 가능 타겟 번호 및 역할]
1. PM: 비즈니스 로직, 기획, 핵심 기능 대폭 변경 시
2. Architect: 시스템 아키텍처, 데이터베이스 스키마, 인프라 변경 시
3. Tech_Lead: 기술 명세, API 시그니처 상세 변경 시
4. Frontend: UI 변경, 화면 로직 수정 시
5. Backend: 서버 API 로직, 데이터 처리 수정 시
6. CodeBuilder: 소스코드 수정 없이 빌드/패키징만 재시도 시

사용자 피드백: "{user_input}"

반드시 아래의 엄격한 JSON 형식으로만 응답하십시오. 다른 설명은 추가하지 마십시오.
{{"target": "단계명(PM, Architect, Tech_Lead, Frontend, Backend, CodeBuilder 중 택1)", "confidence": 0.0부터 1.0사이 숫자, "reason": "판단 근거 1문장"}}
"""
    print("\n🧠 [RouterAgent] 피드백 문 문맥 분석 및 최적 타겟 노드 계산 중...")
    
    try:
        response = harness._safe_invoke(False, prompt)
        json_str = re.search(r'\{.*\}', response, re.DOTALL).group()
        router_result = json.loads(json_str)
        
        target = router_result.get("target")
        confidence = float(router_result.get("confidence", 0.0))
        reason = router_result.get("reason", "")
    except Exception as e:
        print(f"⚠️ 라우터 분석 실패 (JSON 파싱 오류): {e}")
        target = ""
        confidence = 0.0
        reason = "AI 분석 실패"

    final_target = None
    targets_map = {
        "1": "PM", "2": "Architect", "3": "Tech_Lead",
        "4": "Frontend", "5": "Backend", "6": "CodeBuilder"
    }

    if confidence >= 0.85 and target in targets_map.values():
        print(f"\n🤖 판단 근거: {reason}")
        print(f"   추천 시작점: [{target}] (신뢰도: {int(confidence*100)}%)")
        confirm = input("이대로 진행할까요? (Y: 승인 / N: 수동 선택):\n> ").strip().upper()
        if confirm == 'Y':
            final_target = target
    else:
        if confidence > 0:
            print(f"\n🤖 라우터 추천: [{target}] (신뢰도: {int(confidence*100)}%) - 확신도가 낮아 수동 선택으로 전환합니다.")

    if not final_target:
        print("\n시작 노드를 직접 선택하세요:")
        print("  [1] PM (기획 변경)")
        print("  [2] Architect (구조/DB 변경)")
        print("  [3] Tech_Lead (기술/API 명세 변경)")
        print("  [4] Frontend (UI 코드 수정)")
        print("  [5] Backend (서버 코드 수정)")
        print("  [6] CodeBuilder (단순 재빌드)")
        
        while True:
            choice = input("\n입력 (숫자):\n> ").strip()
            if choice in targets_map:
                final_target = targets_map[choice]
                break
            else:
                print("⚠️ 올바른 숫자를 입력해주세요 (1~6).")

    print(f"\n🔄 [{final_target}] 단계부터 델타 업데이트 및 파이프라인 재가동을 준비합니다...")
    
    current_state = app.get_state(config).values
    queue = current_state.get("human_feedback_queue", [])
    queue.append(user_input)
    
    node_mapping = {
        "PM": ("PM", True),                 
        "Architect": ("PM", False),         
        "Tech_Lead": ("Architect", False),
        "Frontend": ("Tech_Lead", False),
        "Backend": ("Frontend", False),
        "CodeBuilder": ("Backend", False)
    }
    
    as_node, needs_rev = node_mapping[final_target]
    app.update_state(
        config,
        {"human_feedback_queue": queue, "needs_revision": needs_rev},
        as_node=as_node
    )

def run_pipeline():
    print("=" * 65)
    print(" 🏭 범용 다중 에이전트 소프트웨어 팩토리 (v3.2) - 투 트랙 PMO 탑재")
    print("=" * 65)

    dashboard_launched = launch_pmo_dashboard()
    if not dashboard_launched:
        print("💡 [System] 현재 수립된 WBS 마스터플랜이 없습니다. 대시보드 대기 중...")

    print("\n[메뉴를 선택해주세요]")
    print("  [0] WBS 마스터플랜 수립 (Master PMO 전담 - 전체 기획 분할)")
    print("  [1] 일일 스프린트 팩토리 가동 (새로운 Task 시작)")
    print("  [2] 중단된 스프린트 이어서 진행 (HOTL 피드백 재개 / 로컬 복구)")
    print("  [q] 파이프라인 종료")
    
    choice = input("\n선택 > ").strip()

    if choice.lower() == 'q':
        print("시스템을 종료합니다.")
        sys.exit(0)

    # =====================================================================
    # [Track 0] 마스터 플랜 수립 모드 (PLANNING)
    # =====================================================================
    if choice == '0':
        project_name = input("\n🏷️ 프로젝트 명칭을 입력하세요 (예: 제조업 E2E 경영 시뮬레이터):\n> ").strip()
        initial_idea = input("\n💡 개발하고자 하는 전체 비즈니스 요구사항을 상세히 입력하세요:\n> ").strip()
        
        config = {"configurable": {"thread_id": "master_planning_thread"}}
        initial_input = {
            "factory_mode": "PLANNING",
            "project_name": project_name,
            "initial_idea": initial_idea,
            "wbs_master_plan_path": WBS_FILE,
            "human_feedback_queue": [],
            "output_dir": "./output_planning"
        }
        
        print("\n🚀 [System] Master PMO 에이전트 가동을 시작합니다. 요구사항을 분할 중...\n")
        try:
            for event in app.stream(initial_input, config=config):
                for key, value in event.items():
                    print(f"✅ [{key}] 에이전트 작업 완료!")
            print("\n🔔 [System] 마스터플랜 수립이 완료되었습니다.")
            if not dashboard_launched:
                launch_pmo_dashboard()
        except Exception as e:
            print(f"\n🚨 마스터플랜 수립 중 오류 발생: {e}")
        return # WBS 수립 후에는 즉시 종료 (단일 책임 원칙)

    # =====================================================================
    # [Track 1] 일일 스프린트 가동 모드 (EXECUTION - New Task)
    # =====================================================================
    elif choice == '1':
        if not os.path.exists(WBS_FILE):
            print("\n⛔ [Error] WBS 파일이 없습니다. [0]번 메뉴를 통해 기획을 먼저 수립하세요.")
            return

        task_id = input("\n🎯 오늘 가동할 WBS Task ID를 입력하세요 (예: E2E-01):\n> ").strip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        config = {"configurable": {"thread_id": f"sprint_thread_{task_id}"}}
        
        initial_input = {
            "factory_mode": "EXECUTION",
            "current_sprint_task_id": task_id,
            "wbs_master_plan_path": WBS_FILE,
            "output_dir": f"outputs/{task_id}_{timestamp}",
            "human_feedback_queue": [],
            "pipeline_status": "running",
            "review_iteration": 0,
            "max_review_iterations": 3,
            "developer_retry_count": 0,
            "needs_revision": False
        }
        
        print(f"\n📂 산출물 저장 예정 경로: {initial_input['output_dir']}")
        print(f"🔗 세션 ID (Thread): sprint_thread_{task_id}")
        print(f"🚀 [System] Task [{task_id}] 팩토리 라인 가동을 시작합니다...\n")

    # =====================================================================
    # [Track 2] 기존 중단된 스프린트 이어서 진행 (Resume & HOTL)
    # =====================================================================
    elif choice == "2":
        if not os.path.exists(WBS_FILE):
            print("\n⛔ [Error] WBS 파일이 없습니다. 먼저 마스터플랜을 수립하세요.")
            return
            
        task_id = input("\n📂 이어서 진행할 Task ID를 입력하세요 (예: E2E-01):\n> ").strip()
        config = {"configurable": {"thread_id": f"sprint_thread_{task_id}"}}
        snapshot = app.get_state(config)
        
        # 1. DB에 기록이 없는 경우 로컬 파일에서 복원 시도 (기존 강력한 복구 로직 보존)
        if not snapshot.values:
            target_dir = input("\n🔍 DB에 기록이 없습니다. 산출물이 저장된 로컬 폴더명을 입력하세요 (예: outputs/E2E-01_20260529_101255):\n> ").strip()
            if os.path.exists(target_dir):
                print(f"\n⚠️ 로컬 디렉토리 '{target_dir}'에서 산출물을 스캔하여 메모리를 복원합니다...")
                recovered_state = {
                    "factory_mode": "EXECUTION",
                    "current_sprint_task_id": task_id,
                    "wbs_master_plan_path": WBS_FILE,
                    "output_dir": target_dir,
                    "human_feedback_queue": [],
                    "review_iteration": 0,
                    "max_review_iterations": 3,
                    "developer_retry_count": 0,
                    "needs_revision": False
                }
                
                file_node_map = [
                    ("01_prd.md", "prd", "PM"),
                    ("02_architecture_doc.md", "architecture_doc", "Architect"),
                    ("03_tech_spec.md", "tech_spec", "Tech_Lead"),
                    ("04_frontend_code.md", "frontend_code", "Frontend"),
                    ("05_backend_code.md", "backend_code", "Backend"),
                    ("06_code_review_report.md", "code_review_report", "Reviewer"),
                    ("07_qa_report.md", "qa_report", "QA")
                ]
                last_node = None
                for filename, state_key, node_name in file_node_map:
                    filepath = os.path.join(target_dir, filename)
                    if os.path.exists(filepath):
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        recovered_state[state_key] = content
                        recovered_state[f"{state_key}_summary"] = content[:500] + "\n\n... (로컬 파일에서 복원됨)"
                        last_node = node_name
                
                if last_node:
                    app.update_state(config, recovered_state, as_node=last_node)
                    print(f"✅ [{last_node}] 에이전트 단계까지의 산출물 복원이 완벽하게 완료되었습니다.")
                    snapshot = app.get_state(config)
                else:
                    print("🚨 폴더는 존재하지만 복구 가능한 마크다운(.md) 산출물이 없습니다.")
                    return
            else:
                print(f"🚨 해당 로컬 폴더({target_dir})가 존재하지 않습니다.")
                return
            
        print(f"\n🔄 Task [{task_id}] 세션을 성공적으로 준비했습니다.")
        if snapshot.next:
            print(f"▶️ 중단된 노드 {snapshot.next} 부터 실행을 재개합니다...\n")
        else:
            print("✅ 이 파이프라인은 이미 끝까지 완료된 상태입니다.")
            
        initial_input = None 
    else:
        print("잘못된 입력입니다. 프로그램을 종료합니다.")
        return

    # =====================================================================
    # 파이프라인 실행 및 HOTL (Human-in-the-Loop) 피드백 루프 처리 (트랙 1, 2 공통)
    # =====================================================================
    try:
        # 최초 실행일 경우
        if initial_input is not None:
            for event in app.stream(initial_input, config=config):
                for key, value in event.items():
                    print(f"✅ [{key}] 에이전트 작업 완료!")
                    time.sleep(1)

        # 상태 폴링 및 피드백 루프
        while True:
            snapshot = app.get_state(config)
            
            if not snapshot.next:
                print("\n" + "="*60)
                print(f"🎉 [E2E 파이프라인 완료] Task [{snapshot.values.get('current_sprint_task_id')}] 산출물 및 빌드가 완성되었습니다.")
                print("="*60)
                user_input = input("\n📝 [종료(Enter)] / [추가 수정 피드백 입력 (타겟 자동 라우팅)]:\n> ").strip()
                
                if user_input == "" or user_input.lower() == 'exit':
                    print("\n🛑 파이프라인을 최종 종료합니다. 수고하셨습니다!")
                    break
                
                handle_feedback_routing(user_input, config)
                
                for event in app.stream(None, config=config):
                    for key, value in event.items():
                        print(f"✅ [{key}] 에이전트 작업 완료!")
                        time.sleep(1)
            else:
                print("\n" + "="*60)
                print(f"⏸️ [HOTL] 파이프라인 일시 정지 (현재 대기 노드: {snapshot.next})")
                print("="*60)
                user_input = input("\n📝 [승인(Enter)] / [피드백 입력 (해당 노드 델타 업데이트)] / [종료(exit)]:\n> ").strip()
                
                if user_input.lower() == 'exit':
                    print("\n🛑 파이프라인을 안전하게 일시 중단합니다. 나중에 [2. 이어서 진행] 메뉴를 통해 재개할 수 있습니다.")
                    break
                
                if user_input == "":
                    print("\n▶️ 승인되었습니다. 다음 단계로 파이프라인을 재개합니다...")
                    app.update_state(config, {"needs_revision": False})
                else:
                    print(f"\n🔄 피드백이 접수되었습니다: '{user_input}'")
                    current_state = snapshot.values
                    queue = current_state.get("human_feedback_queue", [])
                    queue.append(user_input)
                    app.update_state(config, {"human_feedback_queue": queue, "needs_revision": True})
                
                for event in app.stream(None, config=config):
                    for key, value in event.items():
                        print(f"✅ [{key}] 에이전트 작업 완료!")
                        time.sleep(1)
                        
    except Exception as e:
        print(f"\n🚨 파이프라인 실행 중 치명적 오류 발생: {e}")

if __name__ == "__main__":
    run_pipeline()