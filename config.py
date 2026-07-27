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
        "pro":   "meta-llama/llama-3.3-70b-instruct",
        "flash": "google/gemini-2.0-flash-lite-preview-02-05:free",
    }
}

# 폴백(Fallback) 순서 리스트 — [0]=Gemini(1차), [1]=xAI(2차), [2]=Groq(3차), [3]=Cerebras(4차), [4]=OpenRouter(5차)
# ⚠️⚠️ [2026-07-27 실측 — A-1 이 오래 완주하지 못한 최대 원인] Pro 체인에 `gemini-2.5-flash` 가 없었다.
#   실측(라이브 프로브): `gemini-2.5-pro` → 429 RESOURCE_EXHAUSTED(무료 쿼터 소진)
#                        `gemini-2.5-flash` → 성공 1.5초 (무료, 생존)
#   그런데 코드 생성은 is_heavy=True 라 Pro 체인만 타므로, 1순위가 쿼터사하면 grok/groq/cerebras 를
#   거쳐 **출력 상한 8,192 인 OpenRouter llama** 에 착지했다. 그 결과:
#     · test_a1_v3 = 100/100 호출, test_a1_v4 = 35/35 호출이 **전부 llama-3.3-70b 단독**
#     · 코드 생성에 Gemini 가 쓰인 횟수 **0회**
#     · 결함 #15("정확히 8,192 에서 파싱 실패")의 정체 = 상한 설정값이 아니라 **그 모델의 천장**
#       (상한을 16384 로 올려도 실패한 이유. 설정으로 풀 수 있는 문제가 아니었다)
#   → 살아있는 무료 Flash(출력 65,536 = llama 의 8배)를 Pro 체인에 편입한다. **비용 0.**
#   'Pro 티어에 Flash 모델을 넣는 게 맞나'에 대한 답: **죽은 Pro 보다 살아있는 Flash 가 낫다.**
#   품질이 필요한 자리는 1순위 2.5-pro 가 살아나면 자동으로 되찾는다(쿨다운 만료 시 재프로브).
# ⚠️⚠️ 이 리스트는 **위치 기반**이다: [0]=Gemini, [1]=xAI, [2]=Groq, [3]=Cerebras, [4]=OpenRouter.
#   `llm_gateway._build_chains` 가 인덱스로 제공사를 매핑하므로 **중간에 항목을 끼워 넣으면
#   전 제공사 매핑이 밀린다**(실측: 끼워 넣었더니 xAI 에 gemini 모델을 보내는 체인이 만들어졌다).
#   Gemini 계열을 더 넣고 싶으면 이 리스트가 아니라 `PRO_TIER_EXTRA_GEMINI` 를 쓸 것.
LLM_PRO_FALLBACK_LIST   = ["gemini-2.5-pro", "grok-2-latest", "llama-3.3-70b-versatile", "llama-3.3-70b", "meta-llama/llama-3.3-70b-instruct"]
# ★ [2026-07-27] Pro 티어의 Gemini 변종 풀에 **추가로** 붙일 모델(제공사 매핑과 무관하게 안전).
#   실측(라이브 프로브): gemini-2.5-pro = 429 RESOURCE_EXHAUSTED(무료 쿼터 소진)
#                        gemini-2.5-flash = 성공 1.5초 (무료, 생존), 출력 상한 65,536
#   코드 생성은 is_heavy=True 라 Pro 체인만 타는데, 1순위가 쿼터사하면 나머지 제공사를 거쳐
#   **출력 상한 8,192 인 OpenRouter llama** 에 착지했다. 그 결과 v3 100/100 · v4 35/35 호출이
#   전부 llama 단독이었고 코드 생성에 Gemini 가 한 번도 쓰이지 않았다.
#   → 살아있는 무료 Flash 를 Pro 변종 풀에 붙인다. 비용 0. 죽은 Pro 보다 살아있는 Flash 가 낫다.
PRO_TIER_EXTRA_GEMINI = ["gemini-2.5-flash", "gemini-2.0-flash"]
# ⚠️ [2026-07-26 실측 결함 수정] Flash 체인 말단이 무료 모델(`...:free`)이었다.
#   judge/scoring 은 Flash 티어를 쓰는데 체인 전체가 무료라 **OpenRouter 크레딧이 있어도
#   Flash 호출은 쓸 수 없었다.** 실측: RFP 채점에서 depth=7 walk 전부 실패 → 전 모델 쿨다운 →
#   `_compose_chain` 이 ordered[0](무료 gemini) 하나로 재프로브 → 0.15초 429 ×3 → SUSPENDED_QUOTA.
#   → 말단을 유료 모델로 교체한다. 이 환경에서 22콜 연속 성공이 확인된 모델을 쓴다(신뢰성 우선).
#   비용은 관측치 기준 콜당 약 $0.005 로 무시 가능. 더 저렴한 8B 로 교체는 슬러그 검증 후 별건.
LLM_FLASH_FALLBACK_LIST = ["gemini-2.5-flash", "grok-2-latest", "llama-3.1-8b-instant", "llama3.1-8b", "meta-llama/llama-3.3-70b-instruct"]

# ==========================================
# 4-0. ★ 코드 생성 모델 적격성 정책 (2026-07-27 신설)
# ==========================================
# 코드 생성(output_mode="code")은 `with_structured_output(CodeOutput)` 로 **JSON 이 마지막 `}` 까지
# 완결**되어야 한다. 한 파일만 잘려도 응답 전체가 폐기된다. 따라서 출력 예산이 부족한 모델은
# "가끔 실패"하는 게 아니라 **구조적으로 완결할 수 없다**.
#   실측: llama-3.3-70b-instruct(상한 8,192)가 정확히 8,192 를 소진하고 파싱 실패(결함 #15).
#         같은 프롬프트를 gemini-2.5-flash(상한 65,536)로 보내면 여유가 8배.
# → 코드 생성 폴백 체인에서는 이 기준 미만 모델을 **후순위로 밀어낸다**(제거는 하지 않는다 —
#   전멸 시 아무것도 못 하는 것보다 낮은 확률이라도 시도하는 편이 낫다).
CODE_GEN_MIN_OUTPUT_TOKENS = 16000
# 적격 모델이 하나도 살아있지 않을 때 부적격 모델이라도 쓸지. False 면 즉시
# FAILED_GENERATION_CONTRACT 로 종결한다(무의미한 3분 폭주를 미리 차단).
CODE_GEN_ALLOW_INELIGIBLE_FALLBACK = True

# ==========================================
# 4-1. 제공사별 타임아웃 (2026-07-26 실측 기반 — 제공사마다 의미가 다르다!)
# ==========================================
# [실측 근거] A-1 E2E 실패 5건 전수 분석:
#   · Gemini  56.27s / 58.55s / 57.79s 에서 실패 → 504 DEADLINE_EXCEEDED
#     ChatGoogleGenerativeAI 는 timeout 을 int(timeout*1000) ms 로 변환해 gRPC **total deadline**
#     으로 넘긴다(langchain_google_genai/chat_models.py:2883-2887). 즉 60초가 '총 시간' 상한이라
#     긴 코드 생성이 구조적으로 걸린다. → 넉넉히 연장해야 한다.
#   · OpenRouter 294.67s 까지 진행(성공 콜도 최대 95.82s) → timeout=60 이 **발동하지 않았다**.
#     ChatOpenAI 의 timeout 은 httpx 로 가는데 httpx 의 read 는 '바이트 간 간격'이지 총 시간이
#     아니다. 프록시가 커넥션을 살려두면 무한정 기다린다. → 총 시간 상한을 별도로 걸어야 한다.
# ⚠️ 따라서 "타임아웃을 일괄로 늘린다"는 잘못된 처방이다. Gemini 는 늘리고, OpenAI 호환 계열은
#    오히려 상한을 씌워 빨리 폴백시키는 것이 옳다.
LLM_TIMEOUT_GEMINI = 180         # gRPC total deadline (초). 60 → 180 으로 연장
LLM_TIMEOUT_OPENAI_COMPAT = 90   # httpx read 간격(초). Cerebras/OpenRouter — read 는 '바이트 간격'이라 잘 안 걸림
LLM_TIMEOUT_XAI = 90
LLM_TIMEOUT_GROQ = 90
# [핵심] aexecute 1회(= 폴백 체인 전체 walk)의 **총 시간 상한**. asyncio.wait_for 로 강제한다.
# 없으면 httpx read 가 안 걸리는 프록시 경유 호출이 무한정 매달린다(실측 294.67초).
# 단일 모델 상한(Gemini 180)보다 충분히 커야 정상 폴백을 잘라먹지 않는다.
LLM_TOTAL_DEADLINE_SEC = 420

# [레버B] 게이트웨이 자원 관리 파라미터
MAX_GEMINI_VARIANTS = 3          # 동적 탐색된 Gemini 변종을 티어당 이 개수로 제한(죽은 체인 walk 축소)
MODEL_COOLDOWN_SEC = 1800        # 특정 모델이 429/에러로 죽으면 이 시간(초) 동안 폴백 체인에서 제외(재시도 낭비 방지)
# ★ [2026-07-27 실측 결함] 모든 실패에 30분 쿨다운을 걸면 **일시적 실패 한 번이 모델을
#   실행 전체에서 배제**한다. 완주가 15~20분인데 쿨다운이 30분이면 회복 기회가 없다.
#   실측: 첫 호출(attempts=10)에서 gemini-2.5-flash 가 한 번 실패해 30분 쿨다운에 들어갔고,
#         이후 호출은 attempts=1 로 유료 백스톱 하나에 붕괴했다. 그런데 같은 시점에 그 모델을
#         직접 호출하면 구조화 출력까지 2.2초에 성공한다 — 즉 죽지 않았는데 배제된 것이다.
#   → 일일 쿼터 소진(429/RESOURCE_EXHAUSTED)만 장기 배제하고, 그 외(타임아웃·네트워크·
#     분당 레이트리밋·파싱)는 짧게 쉬었다가 다시 시도한다.
TRANSIENT_MODEL_COOLDOWN_SEC = 90

# ★ [2026-07-27] Gemini 재시도 횟수. 0 이면 **분당 레이트리밋 한 번에 즉시 폴백**한다.
#   ⚠️ 실측(test_a1_v5): Gemini 가 코드 생성 적격 1순위인데도 실제 응답은 33콜 중 2건(6%)뿐이었다.
#     무료 티어의 분당 제한에 걸리는 순간 재시도 없이 체인을 타고 내려가 출력 8k 짜리 llama 가
#     받았고, llama 는 응답이 20초대에 품질이 낮아 재작업이 늘고, 재작업마다 또 llama 를 부르는
#     악순환이 됐다.
#   분당 제한은 몇 초만 기다리면 풀린다. Gemini 응답이 2~12초인데 llama 는 20초 이상이므로,
#   **짧게 재시도하는 편이 폴백보다 빠르고 품질도 높다.** (일일 쿼터 소진은 재시도해도 안 풀리지만,
#   그 경우 쿨다운이 모델을 체인에서 빼주므로 손실은 첫 walk 한 번뿐이다.)
GEMINI_MAX_RETRIES = 2
# ⚠️ [2026-07-26] 유료/종량제 모델은 무료와 같은 장기 쿨다운을 적용하면 안 된다.
#   무료가 죽는 건 일일 쿼터(RPD) 소진이라 30분 쉬는 게 맞지만, 유료는 크레딧이 있는 한 살아 있다.
#   똑같이 30분 배제하면 '살아있는 유료'가 체인에서 빠지고 `_compose_chain` 이 ordered[0](무료)
#   하나로 재프로브하다 즉사한다 — 실측으로 재현됨(0.15초 429 ×3 → SUSPENDED_QUOTA).
#   → 유료 모델은 짧게만 쿨다운해 '항상 살아있는 백스톱'이 되게 한다(완전 면제는 진짜 장애 시
#     무한 재시도가 되므로 하지 않는다).
PAID_MODEL_COOLDOWN_SEC = 60
# 유료 판정 마커. OpenRouter 유료 슬러그는 ':free' 접미사가 없다.
PAID_MODEL_MARKERS = ("meta-llama/", "anthropic/", "openai/", "google/gemini-2.0-flash-001")
QUOTA_RETRY_SLEEP_SEC = 8        # Flash 체인마저 소진 시 재시도 전 대기(과거 15초 → 단축)

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
    "meta-llama/llama-3.3-70b-instruct": 200000,
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
    # ⚠️ [2026-07-26 오진 기록 — 올리지 말 것] 8192 소진 실패를 보고 16384 로 올렸으나
    #   **16384 에서 똑같이 소진**됐다(prompt 6,160 → output 16,384, 즉 프롬프트의 2.7배).
    #   즉 '상한 부족'이 아니라 **모델이 종료하지 않는 문제**(구조화 출력 중 반복/폭주)다.
    #   상한을 올리면 실패가 더 느리고 비싸질 뿐 벽만 옮긴다 → 8192 로 원복.
    #   실제 필요량은 성공 사례로 확인됨: 정상 생성 시 출력 1,895~1,948 토큰이면 충분하다.
    #   폭주는 상한이 아니라 재시도(새 표본)로 회피한다 — 그래서 nodes/execution.py 의
    #   `cacheable=not _is_rework` 수정이 이 문제의 실질 대응이다.
    "meta-llama/llama-3.3-70b-instruct": 8192,
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

# [저쿼터 모드] 무료 공통 키의 극소 Pro 한도(분당 2~5회 수준)에서 스프린트를 '완주'시키기 위한 절약 모드.
# True 면 — 기획 드래프트 중 PRO_DRAFT_STAGES(구조 설계)만 Pro, 나머지(RFP/PRD/UI)는 Flash;
# 토론 리비전·단계 재작업도 Flash. → 스프린트당 대용량 Pro 콜을 ~7~13 → ~4(아키텍처·기술명세 드래프트
# + QA·Supervisor 판정)로 줄여 한도 내 완주를 노린다. 그라운딩(지식팩/기준정보)이 문서형 산출물의
# 도메인 정확성을 받치므로 완주용 1차로는 Flash 로 충분. 완주 증거 확보 후 벤치마크로 단계별 Pro 복귀 판정.
LOW_QUOTA_MODE = False
PRO_DRAFT_STAGES = {"ARCHITECTURE", "TECH_SPEC"}  # 저쿼터 모드에서도 드래프트를 Pro 로 유지할 구조 설계 단계

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