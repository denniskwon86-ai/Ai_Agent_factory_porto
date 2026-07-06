import requests
import time
import json
import sys

base_url = 'http://localhost:8080/api/v1/factory'
project_id = 'e2e-full-test-2'

print("1. 프로젝트 생성 중...")
res = requests.post(f"{base_url}/projects", json={"project_id": project_id, "template_id": "default"})
if res.status_code not in (200, 400):
    print(res.text)

print("2. 초기 스프린트 시작...")
payload = {
    "task_id": "sprint_init",
    "project_state_payload": {
        "project_id": project_id,
        "human_feedback_queue": [{"task_id": "sprint_init", "feedback": "다크모드가 지원되는 깔끔한 ToDo 웹앱을 만들어줘. DB는 SQLite 사용."}]
    }
}
requests.post(f"{base_url}/{project_id}/sprint/start", json=payload)

print("3. 파이프라인 진행 모니터링 중...")
chat_injected = False

while True:
    time.sleep(3)
    try:
        with open(f"projects/{project_id}/wbs.json", "r", encoding="utf-8") as f:
            wbs = json.load(f)
    except Exception as e:
        continue
        
    tasks = wbs.get("tasks", [])
    running_task = next((t for t in tasks if t["status"] == "IN_PROGRESS"), None)
    
    if running_task:
        task_id = running_task["task_id"]
        
        # 중간에 슈퍼바이저에게 채팅 주입 (아키텍처 단계쯤)
        if "architecture" in task_id.lower() and not chat_injected:
            print(f"\n[채팅 주입] {task_id} 실행 중 슈퍼바이저에게 지시 전달!")
            try:
                chat_res = requests.post(
                    f"{base_url}/{project_id}/supervisor/chat", 
                    json={"task_id": task_id, "message": "사용자 인터페이스의 폰트를 너무 크게 하지 말고, 세련된 폰트를 사용하도록 강제해줘. 백엔드에는 영향을 주지 마."}
                )
                print("슈퍼바이저 답변:", chat_res.json().get('reply'))
            except Exception as ex:
                print("채팅 전송 에러:", ex)
            chat_injected = True
        
        # HOTL 대기 중인지 체크
        try:
            check_res = requests.get(f"{base_url}/{project_id}/hotl/check").json()
            if check_res.get("hotl_task_id") == task_id:
                print(f"\n[HOTL Pause 감지] {task_id} 자동 승인 및 재가동")
                requests.post(f"{base_url}/{project_id}/hotl/resume", json={"task_id": task_id, "feedback": ""})
                time.sleep(1)
        except:
            pass
    
    all_done = all(t["status"] == "COMPLETED" for t in tasks) if tasks else False
    if tasks and all_done:
        print("\n🎉 모든 태스크 완료!")
        try:
            with open(f"projects/{project_id}/latest_state.json", "r", encoding="utf-8") as f:
                state = json.load(f)
                score = state.get("quality_score", "N/A")
                print(f"최종 품질 점수: {score}")
        except:
            pass
        break
