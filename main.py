import os
import time
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from agent_graph import app, harness, ProjectState

load_dotenv()

print("⚙️ Gemini LLM 엔진을 초기화합니다... (검증된 Lite 모델 및 Semantic Router 가동)")

def initialize_models():
    primary_model = "gemini-2.5-flash-lite"
    fallback_model = "gemini-flash-lite-latest"
    
    try:
        print(f"🔍 '{primary_model}' 모델 가용성 테스트(Ping) 중...")
        test_llm = ChatGoogleGenerativeAI(model=primary_model, temperature=0.1)
        test_llm.invoke("ping")
        print(f"✅ {primary_model} 모델이 정상적으로 인식되었습니다!")
        return primary_model
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "NOT_FOUND" in error_msg:
            print(f"⚠️ '{primary_model}' 모델을 찾을 수 없습니다.")
            print(f"🔄 범용 Lite 모델인 '{fallback_model}'(으)로 자동 폴백(Fallback) 합니다.")
            return fallback_model
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            print("✅ 모델 존재는 확인되었으나, 현재 분당 API 호출 한도(RPM)에 도달한 상태입니다.")
            print("⏳ 6초간 숨을 고른 후 작업을 시작합니다...")
            time.sleep(6)
            return primary_model
        else:
            raise e

active_model_name = initialize_models()

llm_pro = ChatGoogleGenerativeAI(model=active_model_name, temperature=0.2)
llm_flash = ChatGoogleGenerativeAI(model=active_model_name, temperature=0.1)

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
        "developer_retry_count": 0,
        "needs_revision": False,
        "prd": "", "prd_summary": "",
        "architecture_doc": "", "architecture_summary": "",
        "tech_spec": "", "tech_spec_summary": "",
        "frontend_code": "", "frontend_code_summary": "",
        "backend_code": "", "backend_code_summary": "",
        "code_review_report": "", "code_review_report_summary": "",
        "qa_report": "", "qa_report_summary": "",
        "project_output_path": "",
        "build_status": "",
        "build_error_log": "",
        "executable_entry_point": ""
    }

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
    print("\n🧠 [RouterAgent] 피드백 문맥 분석 및 최적 타겟 노드 계산 중...")
    
    try:
        response = llm_flash.invoke(prompt).content
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

    # 1. 신뢰도(Confidence) 점수에 따른 HITL 분기
    if confidence >= 0.85 and target in targets_map.values():
        print(f"\n🤖 판단 근거: {reason}")
        print(f"   추천 시작점: [{target}] (신뢰도: {int(confidence*100)}%)")
        confirm = input("이대로 진행할까요? (Y: 승인 / N: 수동 선택):\n> ").strip().upper()
        if confirm == 'Y':
            final_target = target
    else:
        if confidence > 0:
            print(f"\n🤖 라우터 추천: [{target}] (신뢰도: {int(confidence*100)}%) - 확신도가 낮아 수동 선택으로 전환합니다.")

    # 2. 수동 메뉴 (N 선택 시 또는 Confidence 미달 시)
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

    # 3. Time-travel 상태 주입 (선택된 타겟 직전 노드에서 출발하도록 설정)
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
    print("=" * 60)
    print("🚀 다중 에이전트 자동화 파이프라인 (v3.0 E2E) 가동 준비 완료")
    print("=" * 60)
    
    print("1. 새 프로젝트 시작")
    print("2. 기존 프로젝트 이어서 진행 (Resume)")
    choice = input("\n원하시는 작업을 선택하세요 (1 또는 2):\n> ").strip()

    if choice == "2":
        session_id = input("\n📂 이어서 진행할 폴더명(세션 ID)을 입력하세요 (예: 20260529_101255):\n> ").strip()
        config = {"configurable": {"thread_id": session_id}}
        snapshot = app.get_state(config)
        
        if not snapshot.values:
            folder_path = f"outputs/{session_id}"
            if os.path.exists(folder_path):
                print(f"\n⚠️ DB 기록 누락 감지. 로컬 디렉토리 '{folder_path}'에서 산출물을 스캔하여 메모리를 복원합니다...")
                recovered_state = create_initial_state("로컬 파일 기반 복구 세션", session_id)
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
                    filepath = os.path.join(folder_path, filename)
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
                print(f"🚨 해당 세션의 DB 기록도 없고, 로컬 폴더({folder_path})도 존재하지 않습니다.")
                return
            
        print(f"\n🔄 세션 '{session_id}'을(를) 성공적으로 준비했습니다.")
        if snapshot.next:
            print(f"▶️ 중단된 노드 {snapshot.next} 부터 실행을 재개합니다...\n")
        else:
            print("✅ 이 파이프라인은 이미 끝까지 완료된 상태입니다.")
            
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
        # 최초 1회 스트림
        if initial_input is not None:
            for event in app.stream(initial_input, config=config):
                for key, value in event.items():
                    print(f"✅ [{key}] 에이전트 작업 완료!")
                    time.sleep(1)

        while True:
            snapshot = app.get_state(config)
            
            if not snapshot.next:
                # [수정] 파이프라인이 QA까지 모두 완료된 상태일 때 Semantic Router 가동
                print("\n" + "="*60)
                print("🎉 [E2E 파이프라인 완료] 모든 산출물 및 빌드 패키지가 생성되었습니다.")
                print("="*60)
                user_input = input("\n📝 [종료(Enter)] / [추가 수정 피드백 입력 (타겟 자동 라우팅)]:\n> ").strip()
                
                if user_input == "" or user_input.lower() == 'exit':
                    print("\n🛑 파이프라인을 최종 종료합니다. 수고하셨습니다!")
                    break
                
                handle_feedback_routing(user_input, config)
                
                # 라우팅 결과에 따라 재가동
                for event in app.stream(None, config=config):
                    for key, value in event.items():
                        print(f"✅ [{key}] 에이전트 작업 완료!")
                        time.sleep(1)
            else:
                # [유지] 진행 중 Interrupt 발생 시 Node-specific HOTL 제어
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