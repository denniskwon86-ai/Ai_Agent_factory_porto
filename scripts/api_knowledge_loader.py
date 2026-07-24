import os
import requests
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_BASE = "http://localhost:8080/api/v1/knowledge"

PACK_ID = "core-m3-standards"
PACK_NAME = "AI 팩토리 글로벌/국가 표준 통합 지식팩"
PACK_DESC = "M3 JSON, AAS, KS X 9101 및 스마트 제조 논문 PDF 모음"

def create_knowledge_pack():
    print(f"Creating Knowledge Pack '{PACK_ID}'...")
    payload = {
        "pack_id": PACK_ID,
        "name": PACK_NAME,
        "description": PACK_DESC
    }
    resp = requests.post(f"{API_BASE}/packs", json=payload)
    if resp.status_code == 200:
        print(" -> Created Successfully.")
    elif resp.status_code == 409:
        print(" -> Pack already exists. Skipping creation.")
    else:
        print(f" -> Failed to create pack: {resp.status_code} - {resp.text}")

def upload_document(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    filename = os.path.basename(file_path)
    print(f"Uploading Document '{filename}'...")
    
    with open(file_path, 'rb') as f:
        files = {'file': (filename, f)}
        resp = requests.post(f"{API_BASE}/packs/{PACK_ID}/documents", files=files)
        
    if resp.status_code == 200:
        print(f" -> Uploaded and Indexed '{filename}' successfully.")
    else:
        print(f" -> Failed to upload '{filename}': {resp.status_code} - {resp.text}")

def run_migration():
    print("--- Starting API-based Knowledge Hub Migration ---")
    create_knowledge_pack()
    
    # 1. Upload M3 JSON
    m3_path = os.path.join(BASE_DIR, "docs", "master_data", "global_standard_m3.json")
    upload_document(m3_path)
    
    # 2. Upload PDFs in docs/reference
    reference_dir = os.path.join(BASE_DIR, "docs", "reference")
    if os.path.exists(reference_dir):
        for fname in os.listdir(reference_dir):
            if fname.lower().endswith('.pdf'):
                pdf_path = os.path.join(reference_dir, fname)
                upload_document(pdf_path)
                
    print("\nKnowledge Migration Completed Successfully.")

if __name__ == "__main__":
    run_migration()
