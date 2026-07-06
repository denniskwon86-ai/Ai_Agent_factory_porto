import requests
import json
import time
import os

BASE_URL = "http://127.0.0.1:8080/api/v1/factory"

def run_test():
    project_id = "test_swarm_demo"
    print(f"1. 프로젝트 생성: {project_id}")
    try:
        res = requests.post(f"{BASE_URL}/projects", json={"project_id": project_id})
        print(res.json())
    except Exception as e:
        print("프로젝트 생성 실패 (이미 존재할 수 있음):", e)

    print("2. WBS 및 초기 상태 설정...")
    os.makedirs(f"projects/{project_id}", exist_ok=True)
    wbs = {
        "project_name": "Swarm 테스트 프로젝트",
        "tasks": [
            {
                "task_id": "TASK_DEV_01",
                "task_name": "Swarm 병렬 코딩 테스트",
                "status": "TODO",
                "required_agents": ["Frontend", "Backend"]
            }
        ]
    }
    with open(f"projects/{project_id}/00_wbs_master_plan.json", "w", encoding="utf-8") as f:
        json.dump(wbs, f, ensure_ascii=False)

    print("3. 스프린트 시작 (Micro-Swarm 가동)")
    payload = {
        "task_id": "TASK_DEV_01",
        "project_state_payload": {
            "project_name": "Swarm 테스트 프로젝트",
            "initial_idea": "사용자가 텍스트를 입력하면 화면에 보여주는 아주 간단한 컴포넌트",
            "current_sprint_task_id": "TASK_DEV_01",
            "current_required_agents": ["Frontend", "Backend"]
        }
    }
    res = requests.post(f"{BASE_URL}/{project_id}/sprint/start", json=payload)
    print("API 응답:", res.json())
    print("테스트가 성공적으로 트리거되었습니다. 이제 UI에서 'Swarm 테스트 프로젝트'를 열고 진행 상황을 확인하세요!")

if __name__ == "__main__":
    run_test()
