import os
import google.generativeai as genai
from dotenv import load_dotenv

# 환경변수 로드 및 API 키 세팅
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("=== 현재 API 키로 사용 가능한 제미나이 모델 목록 ===")
# generateContent를 지원하는 모든 모델의 정확한 문자열을 터미널에 출력합니다.
for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(model.name)