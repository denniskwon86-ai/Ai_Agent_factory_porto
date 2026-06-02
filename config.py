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