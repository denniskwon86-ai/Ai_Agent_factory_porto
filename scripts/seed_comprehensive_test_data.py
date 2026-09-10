"""
종합 테스트 시나리오 및 시드 데이터 / 기준정보 자동 생성 스크립트
"""
import requests
import json
import time

BASE_URL = "http://localhost:8080/api/v1/factory"
HEADERS_ADMIN = {
    "X-User-ID": "admin",
    "X-Principal-ID": "admin",
    "Content-Type": "application/json"
}
HEADERS_LEGAL = {
    "X-User-ID": "user_legal",
    "X-Principal-ID": "user_legal",
    "Content-Type": "application/json"
}

def seed_scenarios():
    print("==================================================")
    print(" [SEED] Test Scenarios and Seed Data Setting Start")
    print("==================================================")

    # ----------------------------------------------------
    # 시나리오 1: SW Factory E2E 풀 파이프라인
    # ----------------------------------------------------
    p1_id = "scenario-01-enterprise-ai"
    print(f"\n[Scenario 1] Creating Project: {p1_id}")
    r1 = requests.post(f"{BASE_URL}/projects", json={
        "project_id": p1_id,
        "template_id": "manufacturing-cost-analysis"
    }, headers=HEADERS_ADMIN)
    print("  -> Result:", r1.status_code)

    r1_start = requests.post(f"{BASE_URL}/{p1_id}/sprint/start", json={
        "task_id": "sprint_init",
        "project_state_payload": {
            "project_id": p1_id,
            "human_feedback_queue": [{
                "task_id": "sprint_init",
                "feedback": "사내 벤처 경영실적 및 원가 분석 모니터링 AI 대시보드 시스템을 구축해줘. SQLite 데이터베이스 연동 및 REST API 포함."
            }]
        }
    }, headers=HEADERS_ADMIN)
    print("  -> Sprint Start Result:", r1_start.status_code)

    # ----------------------------------------------------
    # 시나리오 2: 조직/권한 보안 격리 & 발간 게이트
    # ----------------------------------------------------
    p2_id = "scenario-02-security-audit"
    print(f"\n[Scenario 2] Creating Project by Admin: {p2_id}")
    r2 = requests.post(f"{BASE_URL}/projects", json={
        "project_id": p2_id,
        "template_id": "default"
    }, headers=HEADERS_ADMIN)
    print("  -> Admin Create Result:", r2.status_code)

    # Legal 사용자의 접근 권한 통제 테스트
    r2_legal = requests.get(f"{BASE_URL}/{p2_id}/state", headers=HEADERS_LEGAL)
    print(f"  -> Legal User Access Check Status: {r2_legal.status_code}")

    # ----------------------------------------------------
    # 시나리오 3: 폐루프 Decision Package & 텔레메트리 관측
    # ----------------------------------------------------
    p3_id = "scenario-03-closed-loop"
    print(f"\n[Scenario 3] Creating Project: {p3_id}")
    r3 = requests.post(f"{BASE_URL}/projects", json={
        "project_id": p3_id,
        "template_id": "content-marketing"
    }, headers=HEADERS_ADMIN)
    print("  -> Result:", r3.status_code)

    print("\n==================================================")
    print(" [SUCCESS] 3 Test Scenario Projects Seeded Successfully.")
    print("==================================================")

if __name__ == "__main__":
    seed_scenarios()
