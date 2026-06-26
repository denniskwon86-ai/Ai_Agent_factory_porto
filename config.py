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

# ==========================================
# 5. 토론·합의 루프 / 단계별 성공기준 / Supervisor 설정 (V5.1)
# ==========================================
# 다중 에이전트 토론을 적용할 단계 (상류 생성 단계만 — 무료 티어 429/비용 절제)
DEBATE_STAGES = ["RFP", "PLANNING", "ARCHITECTURE", "TECH_SPEC"]
DEBATE_MAX_ROUNDS = 2   # 토론 최대 라운드(초안→비평→개정 반복 상한). 합의(치명결함 0) 시 조기 종료
DEBATE_CRITICS = 1      # 라운드당 비평가 수 (무료 티어 429 방어로 1명 권장)

# 단계별 비평가 페르소나 (관점 차등 비평)
STAGE_CRITIC_PERSONAS = {
    "RFP":          "발주처 입장에서 진짜 목적과 필수 요건이 빠짐없이 정의됐는지 따지는 시니어 비즈니스 분석가",
    "PLANNING":     "실현 가능성과 사용자 가치를 동시에 따지는 시니어 프로덕트 매니저",
    "ARCHITECTURE": "확장성·보안·결합도를 검증하는 수석 아키텍트",
    "TECH_SPEC":    "구현 누락과 PRD 추적성을 검증하는 테크리드",
}

# Supervisor 게이트 / 무한루프 안전장치
MAX_STAGE_REWORKS = 2            # 단계별 in-node 재작업 한도. 초과 시 인간 개입(HOTL)
GLOBAL_MAX_SUPERVISOR_HOPS = 8   # 전역 Supervisor 왕복 상한
ON_STAGE_LIMIT_EXCEEDED = "HOTL" # 한도 초과 시: "HOTL"(인간 대기) | "FORCE_PASS"(강행)

# 단계별 통과 임계 점수 (rubric 가중합 기준)
STAGE_PASS_THRESHOLDS = {
    "RFP":          0.8,
    "PLANNING":     0.8,
    "PMO":          1.0,
    "ARCHITECTURE": 0.7,
    "TECH_SPEC":    0.7,
    "CODE_REVIEW":  0.9,
}

# Deterministic 기준 임계값 (LLM 0콜로 검사)
RFP_MIN_LENGTH = 600   # 빈약 요구정의서 차단
PRD_MIN_LENGTH = 800   # 빈약 PRD(3~5줄) 정면 차단
WBS_MIN_TASKS  = 4     # WBS 최소 태스크 수