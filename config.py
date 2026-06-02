# ==========================================
# 범용 AI 소프트웨어 팩토리 플랫폼 - 시스템 환경 설정
# ==========================================

# 1. 시스템 파일 및 데이터베이스 경로
WBS_FILE = "00_wbs_master_plan.json"
MASTER_PRD_FILE = "00_master_prd.md"
PIPELINE_DB_FILE = "pipeline_state.db"

# 2. 에이전트 산출물 파일명 매핑
OUTPUT_ARTIFACTS = {
    "master_prd":   "00_master_prd.md",
    "wbs_plan":     "00_wbs_master_plan.json",
    "architecture": "02_architecture_doc.md",
    "tech_spec":    "03_tech_spec.md",
    "frontend":     "04_frontend_code.md",
    "backend":      "05_backend_code.md",
    "review":       "06_code_review_report.md",
    "qa":           "07_final_qa_report.md",
}

# 3. 파이프라인 엔진 제어 파라미터
MAX_REVIEW_ITERATIONS = 1  # V4.0 터보 모드 적용 (리뷰어 무한 루프 방지)
MAX_BUILD_RETRIES = 3      # 코드 빌드 실패 시 최대 롤백 횟수
CONTEXT_MAX_LENGTH = 10000
PREVIOUS_OUTPUT_MAX_LENGTH = 8000
SUMMARY_MAX_LENGTH = 4000
# ==========================================
# 4. LLM 엔진 설정 (모델 불가지성 보장)
# ==========================================
# 논리 티어 → 물리 모델 매핑 테이블
ENGINE_TIERS = {
    "gemini": {
        "pro":   "gemini-2.5-pro",
        "flash": "gemini-2.5-flash-lite",
    },
    "groq": {
        "pro":   "llama-3.3-70b-versatile", # [수정] 퇴역한 llama3-70b-8192 모델을 최신 주력 모델로 교체
        "flash": "llama-3.1-8b-instant",    # [수정] mixtral 대신 최신 고속 모델로 교체
    }
}

# 폴백(Fallback) 순서 리스트
LLM_PRO_FALLBACK_LIST   = ["gemini-2.5-pro", "llama-3.3-70b-versatile"]
LLM_FLASH_FALLBACK_LIST = ["gemini-2.5-flash-lite", "llama-3.1-8b-instant"]

# 모델별 컨텍스트 윈도우 한도 (토큰 기준, 안전 마진 포함)
MODEL_CONTEXT_LIMITS = {
    "gemini-2.5-pro":          600000,
    "gemini-2.5-flash-lite":    75000,
    "llama-3.3-70b-versatile":   6000,  # 8k 제한 방어
    "llama-3.1-8b-instant":      6000,  # 8k 제한 방어
}
CHARS_PER_TOKEN_ESTIMATE = 2.5  # 한국어 혼용 기준 보수적 추정