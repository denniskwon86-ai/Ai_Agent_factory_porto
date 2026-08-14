import os
import sys

# uvicorn reload=True 워커 자식 프로세스는 run.py의 stdout 재설정을 상속받지 못한다.
# 워커가 import하는 진입점(main.py)에서 직접 UTF-8로 고정하여 cp949 콘솔에서의
# 이모지 print UnicodeEncodeError(파이프라인 500 크래시)를 영구 방지한다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# [SSL 신뢰저장소 주입] 사내망 등 SSL 검사(자체 루트 CA 주입) 환경에서 certifi 번들에 해당 CA 가
# 없어 외부 LLM API 호출이 CERTIFICATE_VERIFY_FAILED 로 전부 실패하는 문제를 방지한다.
# truststore 는 파이썬 ssl/httpx/requests 가 'OS 신뢰저장소'(사내 CA 포함)를 쓰게 만든다.
# SSL 검사가 없는 환경에서도 무해(그냥 OS 저장소 사용)하므로 항상 주입한다. 미설치 시 조용히 건너뜀.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.sys_logger import StdoutInterceptor
sys.stdout = StdoutInterceptor(sys.stdout)
sys.stderr = StdoutInterceptor(sys.stderr)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import factory_control, realtime, format_control, skill_control, knowledge_control, telemetry_control, master_control, catalog_control, glossary_control, lineage_control, contract_control, external_control, benchmark_control, crosswalk_control, mcp_control, standard_control, org_control, advisor_control, ledger_control, enterprise_context_control, reference_control, planning_control, connector_control, briefing_control, shadow_control, workspace_control, readiness_control, program_control, scope_control, sandbox_control, admin_control, agent_governance

# 슈퍼바이저 데몬 초기화 (백그라운드 이벤트 리스너 등록)
import core.supervisor_daemon

# ★★★ [P0-1B 보정] 접근 로그에서 비밀값을 가린다.
#   SSE 접속표는 URL 로 오가므로 `uvicorn.access` 의 request line 에 그대로 남는다.
#   응답의 `Referrer-Policy` 는 브라우저 참조자만 막을 뿐 **서버 로그는 가리지 못한다.**
#   ⚠️ 앱 생성 **전에** 걸어야 uvicorn 이 로거를 잡기 전에 필터가 붙는다.
from core.log_redaction import install as _install_log_redaction

_install_log_redaction()

app = FastAPI(
    title="V5.0 AI Factory Studio API",
    description="범용 자율형 소프트웨어 팩토리 플랫폼 관제용 비동기 API",
    version="5.1.0"
)


@app.get("/api/v1/health", tags=["System"])
async def health():
    """[UIUX-AUDIT-29 §3] 서버 생존 확인 — **화면이 «연결»을 지어내지 않게 하기 위한 것.**

    ⚠️ 이 경로는 인증도 DB 접근도 하지 않는다. 무거우면 화면이 «확인 중»에 머물고, 그러면
      사용자는 서버가 죽은 것으로 오해한다. 판단에 필요한 최소한만 답한다."""
    return {"status": "ok", "version": app.version}

# [QA 보완] 하드코딩 배제: 운영 서버와 로컬 환경을 분리하기 위해 환경 변수 사용
# ⚠️ 개발 기본값에 **5174·5175 를 포함한다.** 세션이 여럿이면 5173 이 이미 점유돼 Vite 가
#   다음 포트로 올라가는데, 그때 모든 요청이 CORS 로 막히고 화면은 「서버가 죽었다」처럼
#   보인다(2026-08-04 Codex 5174 · 2026-08-06 내가 5175 에서 같은 벽을 만났다).
#   ★ 2026-08-08 에 **5177 에서 세 번째로** 같은 벽을 만났다 — 5173·5175 가 둘 다 다른 세션에
#     점유된 상태였다. 세션 수가 늘면 이 목록은 계속 모자라므로 5176·5177 까지 미리 넓힌다.
#     ⚠️ 이 벽의 증상은 «권한 오류» 가 아니라 **`Failed to fetch`** 다. 화면은 그것을
#       「서버가 죽었다」로 그리고, 그러면 검증하던 사람이 자기 변경을 의심한다.
#   운영 환경은 `CORS_ALLOWED_ORIGINS` 로 명시 지정하므로 이 기본값이 넓어져도 영향이 없다.
allowed_origins_env = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,"
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5174,http://127.0.0.1:5174,"
    "http://localhost:5175,http://127.0.0.1:5175,"
    "http://localhost:5176,http://127.0.0.1:5176,"
    "http://localhost:5177,http://127.0.0.1:5177")
allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _warmup():
    """기동 시 기본 그래프·체크포인터를 미리 컴파일 - 재시작 직후 첫 API 호출이
    초기화(그래프 컴파일+SQLite 커넥션)로 수십 초 지연되던 문제 제거."""
    try:
        from core.agent_graph import get_runtime_app
        await get_runtime_app()
        print("[OK] [Warmup] 기본 그래프/체크포인터 사전 컴파일 완료.")
    except Exception as e:
        print(f"⚠️ [Warmup] 사전 컴파일 실패(첫 호출 시 초기화됨): {e}")

    # ★ [2026-07-27] 업무표준(규정/지침) 분류 등록 + 초기 시드 — 멱등.
    #   에이전트가 "나는 어떤 기준으로 일하고 무엇을 확인해 넘기는가"를 코드 상수가 아니라
    #   관리되는 기준정보에서 조회하게 한다. 이미 등록된 표준은 덮어쓰지 않는다(운영 중 개정본 보호).
    try:
        from core.work_standard_seed import seed_from_criteria
        _seeded = seed_from_criteria(force=False)
        _new = [k for k, v in _seeded.items() if not v.startswith("skip")]
        if _new:
            print(f"📜 [업무표준] 신규 등록 {len(_new)}건: {_new}")
        else:
            print(f"📜 [업무표준] 등록본 {len(_seeded)}건 확인 (기존 유지)")
    except Exception as e:
        print(f"⚠️ [업무표준] 시드 실패(코드 기본값으로 폴백): {e}")


from api.routes import (app_delivery_control, decision_control,  # [CL-1, CL-2]
                        publication_control,  # [CL-3] 대내외 발간 게이트
                        jarvis_control,  # [CL-4 선행] 기존 Supervisor 계약의 문맥 어댑터
                        auth_control,  # [2026-08-09] 로그인·세션 — 식별의 유일한 정본
                        app_data_control,  # [트랙 I] 생성 앱 데이터 평면
                        app_data_runtime)  # [G1-B 3.5] Host Runtime 전용(앱 증명 필수)
app.include_router(factory_control.router)
app.include_router(format_control.router)
app.include_router(realtime.router)
app.include_router(skill_control.router)
app.include_router(knowledge_control.router)
app.include_router(reference_control.router)
app.include_router(telemetry_control.router)
app.include_router(planning_control.router)
app.include_router(connector_control.router)
app.include_router(briefing_control.router)
app.include_router(shadow_control.router)
app.include_router(workspace_control.router)
app.include_router(readiness_control.router)
app.include_router(program_control.router)
# [M2 §2.1] 범위 계약 — 소유 지정·조직 공유·전사 공용 승인·한시 예외 이행
app.include_router(scope_control.router)
# [M2 §4.3] VIRTUAL Sandbox capability token — 권한 승급이 아닌 세션 전용 읽기 토큰
app.include_router(sandbox_control.router)
# [관리자] 감사로그 열람·보존(5년) + 범위 정책 — 모든 경로가 관리자 권한을 요구한다
app.include_router(admin_control.router)
# [D-017 P1-4] 에이전트·워크플로우·스킬 자산의 조직별 목록·복사·승인·폐기
app.include_router(agent_governance.router)
app.include_router(master_control.router)
app.include_router(standard_control.router)
app.include_router(org_control.router)
app.include_router(advisor_control.router)   # [M0] 업무·데이터 설계 상담사 (LLM 0콜)
app.include_router(ledger_control.router)    # [M0] Decision Ledger 조회 전용(쓰기 없음)
app.include_router(enterprise_context_control.router)  # [ECM E1] 조직 그래프·범위·프로필
app.include_router(benchmark_control.router)
app.include_router(catalog_control.router)
app.include_router(glossary_control.router)
app.include_router(lineage_control.router)
app.include_router(contract_control.router)
app.include_router(external_control.router)
app.include_router(crosswalk_control.router)
# [CL-1] 개인 앱 전달 — 조직 공유·업무 배정·전사 승격과 **별도 경로**다(작업서 §3-1,2).
app.include_router(app_delivery_control.router)
# [CL-2] Decision Package — 세 관점은 같은 문서의 렌더링이다(§3-5).
app.include_router(decision_control.router)
# [CL-3] 대내외 발간 — **대외 이중 승인 차단은 화면이 아니라 이 라우터에서 일어난다**(§CL-BE-04).
app.include_router(publication_control.router)
# [CL-4 선행] Jarvis 문맥 어댑터 — 두 번째 채팅 API 가 아니라 기존 엔진의 주소 변환기다(§3).
app.include_router(jarvis_control.router)
# [트랙 I] 생성 앱 데이터 평면 — 생성된 앱은 자기 백엔드를 갖지 않으므로(CL-0 계약) 업무
#   데이터는 **이 라우터를 통해서만** 드나든다. 앱은 `release_id` 를 말하지 않는다(설계 §7).
app.include_router(app_data_control.router)
# ★★★ [G1-B 3.5] Host Runtime 전용 데이터 평면. **앱 증명이 없으면 세션으로 내려가지
#   않고 차단한다.** 같은 라우터에서 폴백을 허용하면 앱이 헤더 하나를 생략해 사람의 넓은
#   권한으로 데이터를 만질 수 있다(교차검토 [G1-B-I3-REVIEW-82]).
app.include_router(app_data_runtime.router)
app.include_router(mcp_control.router)
# [2026-08-09] 로그인. ⚠️ 이 라우터 자체는 인증을 요구하지 않는다(로그인이 인증의 입구다).
app.include_router(auth_control.router)
