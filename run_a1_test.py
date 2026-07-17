import requests
import json

base_url = 'http://localhost:8080/api/v1/factory'
project_id = 'test_a1_unitconv'

print(f"[{project_id}] 1. Project creation...")
res = requests.post(f"{base_url}/projects", json={"project_id": project_id, "template_id": "default"})
if res.status_code not in (200, 400):
    print("Creation error:", res.text)
else:
    print("[OK] Project ready")

print(f"\n[{project_id}] 2. A-1 Init sprint...")
payload = {
    "task_id": "sprint_init",
    "project_state_payload": {
        "project_id": project_id,
        "human_feedback_queue": [{"task_id": "sprint_init", "feedback": "길이(cm/inch), 무게(kg/lb), 온도(섭씨/화씨)를 서로 변환해주는 심플한 단위 변환기 웹앱. 로그인 불필요, 단일 화면, 변환 이력 5개까지 화면에 표시."}]
    }
}
try:
    res = requests.post(f"{base_url}/{project_id}/sprint/start", json=payload)
    print("[OK] API Response:", res.json())
    print("\n[SUCCESS] A-1 scenario started successfully!")
    print("Check backend logs for agent execution.")
except Exception as e:
    print("[ERROR] API Call failed:", e)
