import os
from dotenv import load_dotenv
import google.generativeai as genai

# .env 파일에서 API 키 로드
load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    print("🚨 GOOGLE_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
    exit(1)

# API 키 설정
genai.configure(api_key=api_key)

print("🔍 현재 환경 및 API 키로 접근 가능한 Gemini 텍스트 생성 모델 목록을 조회합니다...\n")
print("-" * 50)

try:
    available_models = []
    # 서버에 사용 가능한 전체 모델 리스트 요청
    for m in genai.list_models():
        # 텍스트 생성(generateContent)을 지원하는 모델만 필터링
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            print(f"✅ 사용 가능 모델: {m.name}")
            
    print("-" * 50)
    
    if not available_models:
        print("🚨 접근 가능한 텍스트 생성 모델이 없습니다. API 키 권한을 확인해야 합니다.")
    else:
        print(f"총 {len(available_models)}개의 텍스트 생성 모델이 확인되었습니다.")
        
except Exception as e:
    print(f"🚨 모델 목록 조회 중 오류 발생: {e}")