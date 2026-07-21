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
CONTEXT_MAX_LENGTH = 20000  # 코드 누적/기존기능 보존 위해 상향(기존 10000). 멀티태스크 회귀 완화.
# 개발자(코드 작성) 호출에서 '본인 소유 파일'을 전체(무절단) 주입할 때의 총 컨텍스트 상한.
# 전체 파일 재출력 시 truncation 으로 기존 기능이 누락되던 회귀의 근본 차단용(증분 codegen).
CONTEXT_MAX_LENGTH_CODE = 200000
PREVIOUS_OUTPUT_MAX_LENGTH = 8000
SUMMARY_MAX_LENGTH = 4000
# ==========================================
# 4. LLM 엔진 설정 (모델 불가지성 보장)
# ==========================================
# 논리 티어 → 물리 모델 매핑 테이블
#
# [5중 폴백 아키텍처] 각 논리 티어(pro/flash)는 5개 제공사를 순차 폴백한다:
#   Gemini(1차·주력) → xAI(2차) → Groq(3차) → Cerebras(4차) → OpenRouter(5차·최후 보루)
# 다섯 제공사 모두 '무료 티어'를 제공하므로, 한 곳의 일일/분당 할당량(429)이 소진돼도
# 다음 제공사로 자동 강하하여 파이프라인이 멈추지 않는다(무료 쿼터를 사실상 5배로 확장).
# Groq·Cerebras 는 동일 Llama 계열을 서빙하므로 폴백 시에도 응답 품질 편차가 작다.
ENGINE_TIERS = {
    "gemini": {
        "pro":   "gemini-2.5-pro",
        "flash": "gemini-2.5-flash",
    },
    "groq": {
        "pro":   "llama-3.3-70b-versatile", # [수정] 퇴역한 llama3-70b-8192 모델을 최신 주력 모델로 교체
        "flash": "llama-3.1-8b-instant",    # [수정] mixtral 대신 최신 고속 모델로 교체
    },
    # Cerebras 무료 티어(일 100만 토큰, 카드 불필요). Meta 가 Llama API 공식 파트너로 택한
    # 초고속 추론(LPU/웨이퍼스케일) 제공사. 모델 ID 는 Cerebras 문서 표기를 그대로 사용한다
    # (주의: 70B 는 하이픈 'llama-3.3-70b', 8B 는 하이픈 없이 'llama3.1-8b' — Cerebras 표기 불일치).
    "cerebras": {
        "pro":   "llama-3.3-70b",
        "flash": "llama3.1-8b",
    },
    "xai": {
        "pro":   "grok-2-latest",
        "flash": "grok-2-latest",
    },
    "openrouter": {
        "pro":   "meta-llama/llama-3.3-70b-instruct:free",
        "flash": "google/gemini-2.0-flash-lite-preview-02-05:free",
    }
}

# 폴백(Fallback) 순서 리스트 — [0]=Gemini(1차), [1]=xAI(2차), [2]=Groq(3차), [3]=Cerebras(4차), [4]=OpenRouter(5차)
LLM_PRO_FALLBACK_LIST   = ["gemini-2.5-pro", "grok-2-latest", "llama-3.3-70b-versatile", "llama-3.3-70b", "meta-llama/llama-3.3-70b-instruct:free"]
LLM_FLASH_FALLBACK_LIST = ["gemini-2.5-flash", "grok-2-latest", "llama-3.1-8b-instant", "llama3.1-8b", "google/gemini-2.0-flash-lite-preview-02-05:free"]

# 모델별 컨텍스트 윈도우 한도 (토큰 기준, 안전 마진 포함)
MODEL_CONTEXT_LIMITS = {
    "gemini-2.5-pro":          600000,
    "gemini-2.5-flash":        500000,  # 동적 폴백 2순위 (flash-lite 소진 시)
    "gemini-2.5-flash-lite":    75000,
    "gemini-2.0-flash":        500000,  # 동적 폴백 3순위
    "llama-3.3-70b-versatile":   6000,  # 8k 제한 방어
    "llama-3.1-8b-instant":      6000,  # 8k 제한 방어
    # Cerebras 무료 티어는 컨텍스트 창이 보수적(모델 자체는 크나 무료 한도가 낮음) → Groq 와 동일하게 방어
    "llama-3.3-70b":             6000,
    "llama3.1-8b":               6000,
    "grok-2-latest":             32000,
    "meta-llama/llama-3.3-70b-instruct:free": 6000,
    "google/gemini-2.0-flash-lite-preview-02-05:free": 60000,
}
CHARS_PER_TOKEN_ESTIMATE = 2.5  # 한국어 혼용 기준 보수적 추정

# 모델별 '출력' 토큰 상한. 미설정 시 SDK 기본값(예: Gemini 8192)으로 응답이 잘려
# 누적 파일 전체 재출력이 중간에 끊기고(=기능 누락 회귀), 그 JSON이 파싱 실패로 전량 폐기된다.
# → 코드 생성에 충분한 큰 값으로 명시 설정. (Gemini 2.5 계열 64k 출력 지원)
MODEL_OUTPUT_LIMITS = {
    "gemini-2.5-pro":          65536,
    "gemini-2.5-flash":        65536,  # 동적 폴백 2순위
    "gemini-2.5-flash-lite":   65536,
    "gemini-2.0-flash":        65536,  # 동적 폴백 3순위
    "llama-3.3-70b-versatile":  8000,
    "llama-3.1-8b-instant":     8000,
    # Cerebras Llama 계열 출력 상한 — Groq 와 동일하게 8k 로 설정
    "llama-3.3-70b":            8000,
    "llama3.1-8b":              8000,
    "grok-2-latest":            8192,
    "meta-llama/llama-3.3-70b-instruct:free": 8000,
    "google/gemini-2.0-flash-lite-preview-02-05:free": 8192,
}
DEFAULT_OUTPUT_LIMIT_GEMINI = 65536
DEFAULT_OUTPUT_LIMIT_GROQ = 8000
DEFAULT_OUTPUT_LIMIT_CEREBRAS = 8000
DEFAULT_OUTPUT_LIMIT_XAI = 8192
DEFAULT_OUTPUT_LIMIT_OPENROUTER = 8000

# ==========================================
# 5. 토론·합의 루프 / 단계별 성공기준 / Supervisor 설정 (V5.1)
# ==========================================
# [예약/미참조] 현재 코드는 이 목록을 읽지 않는다 — 토론 적용 단계는 run_supervised_stage 를
# 호출하는 노드(planning/execution)가 결정한다. Phase 2에서 registry.debate 로 통합 예정.
DEBATE_STAGES = ["RFP", "PLANNING", "ARCHITECTURE", "TECH_SPEC"]
DEBATE_MAX_ROUNDS = 1   # 토론 최대 라운드(무료 티어 할당량 절감 — 초안→비평 1회). 합의 시 조기 종료
DEBATE_CRITICS = 1      # 라운드당 비평가 수 (무료 티어 429 방어로 1명 권장)

# 단계별 비평가 페르소나 (관점 차등 비평)
STAGE_CRITIC_PERSONAS = {
    "RFP":          "발주처 입장에서 진짜 목적과 필수 요건이 빠짐없이 정의됐는지 따지는 시니어 비즈니스 분석가",
    "PLANNING":     "실현 가능성과 사용자 가치를 동시에 따지는 시니어 프로덕트 매니저",
    "ARCHITECTURE": "확장성·보안·결합도를 검증하는 수석 아키텍트",
    "TECH_SPEC":    "구현 누락과 PRD 추적성을 검증하는 테크리드",
}

# [심판 앵커링] llm_judge 채점을 항상 Pro(가용 최강) 체인으로 고정할지 여부.
# ⚠️ False 로 되돌림 (2026-07-20): 공통 API 키라 Pro 일일 한도가 '단일 유한 풀'이다.
#   True 였을 때는 채점마다 Pro 를 태워, 정작 중요한 '생성(creation)'에 쓸 Pro 예산을 앞당겨
#   소진시키고 서킷 브레이커 트리거를 가속했다. 채점 잣대의 모델 불변성은 '실시간 Pro 채점'이
#   아니라 '오프라인 골든 벤치마크(의도적 Pro 사용)'가 담당하는 게 맞다. 하드 게이트는 결정론
#   검사(빌드/회귀/렌더/fr_coverage)가 이미 지킨다. → judge 는 rubric.judge_heavy(QA/Supervisor)만 Pro.
JUDGE_FORCE_HEAVY = False

# Supervisor 게이트 / 무한루프 안전장치
MAX_STAGE_REWORKS = 1            # 단계별 in-node 재작업 한도(할당량 절감). 초과 시 인간 개입(HOTL)
GLOBAL_MAX_SUPERVISOR_HOPS = 8   # 전역 Supervisor 왕복 상한
ON_STAGE_LIMIT_EXCEEDED = "HOTL" # 한도 초과 시: "HOTL"(인간 대기) | "FORCE_PASS"(강행)

# 단계별 통과 임계 점수는 criteria.py 의 각 STAGE_RUBRICS[...]["pass_threshold"] 로 단일화됨(SSOT).
# (과거 여기 중복 정의됐던 STAGE_PASS_THRESHOLDS 는 scoring.py 가 rubric 값을 직접 읽도록 바뀌며 제거)

# Deterministic 기준 임계값 (LLM 0콜로 검사)
RFP_MIN_LENGTH = 600   # 빈약 요구정의서 차단
PRD_MIN_LENGTH = 1200  # 빈약 PRD 차단 — 7개 섹션 깊이를 강제하기 위해 상향(기존 800)
WBS_MIN_TASKS  = 4     # WBS 최소 태스크 수
# WBS 태스크당 추정 토큰 상한(결정론 게이트). pmo_skill 권장은 3,000~5,000 이므로 그 3배를
# '명백히 과대'로 본다. 큰 태스크 하나는 1회 코드 생성에서 절단→재작업 루프를 유발하고, 공통 키의
# 유한 일일 Pro 예산을 크게 잠식하므로 재분할을 유도한다. 필드 없음/비숫자는 판단 불가로 통과(오차단 방지).
WBS_MAX_TASK_TOKENS = 15000

# 프론트 코드 품질 정적 백스톱(quality_checker) — 거대 단일 파일 판정 임계(둘 다 충족 시 권고)
FE_MONOLITH_MAX_LINES      = 400  # 한 파일이 이 줄 수 이상이고
FE_MONOLITH_MIN_COMPONENTS = 3    # 컴포넌트가 이 개수 이상이면 '분리 누락' 권고