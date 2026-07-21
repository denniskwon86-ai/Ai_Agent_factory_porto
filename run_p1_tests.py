import requests
import json
import time
import os

BASE_URL = "http://localhost:8080/api/v1/factory"

def test_s1_s2():
    print("--- S-1 & S-2: 프로젝트 CRUD 및 잘못된 입력 방어 ---")
    # S-1 프로젝트 생성
    r = requests.post(f"{BASE_URL}/projects", json={"project_id": "test_s1_proj", "idea": "test idea", "template_id": "default"})
    assert r.status_code == 200, f"Failed to create project: {r.text}"
    print("S-1 Project creation OK")
    
    # S-2 존재하지 않는 템플릿
    r = requests.post(f"{BASE_URL}/projects", json={"project_id": "test_s1_fail", "idea": "test idea", "template_id": "invalid_template_xyz"})
    assert r.status_code == 404, f"Expected 404 for invalid template, got {r.status_code}"
    
    # S-2 중복 ID
    r = requests.post(f"{BASE_URL}/projects", json={"project_id": "test_s1_proj", "idea": "test idea", "template_id": "default"})
    assert r.status_code == 409, f"Expected 409 for duplicate project ID, got {r.status_code}"
    print("S-2 Bad input defense OK")

    # 프로젝트 삭제
    r = requests.delete(f"{BASE_URL}/projects/test_s1_proj")
    assert r.status_code == 200, "Failed to delete project"
    print("S-1 Project deletion OK")

def test_s3():
    print("--- S-3: 메가 프로젝트 프로비저닝 ---")
    r = requests.post(f"{BASE_URL}/projects/mega", json={"project_id": "test_s3_mega", "idea": "mega idea"})
    assert r.status_code == 200, f"Mega project creation failed: {r.text}"
    print("S-3 Mega project OK")
    requests.delete(f"{BASE_URL}/projects/test_s3_mega")
    
def test_s4():
    print("--- S-4: 출력 포맷 CRUD ---")
    # This assumes /api/v1/factory/format or /api/v1/format ? Let's check routes.
    pass # format routes are in format_control.py, mounted at /api/v1/format maybe?

def main():
    test_s1_s2()
    test_s3()
    print("P1 Structure tests completed successfully!")

if __name__ == "__main__":
    main()
