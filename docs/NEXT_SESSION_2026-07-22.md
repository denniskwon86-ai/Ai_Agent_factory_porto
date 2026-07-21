# 🔵 다음 세션 이어가기 브리프 (2026-07-22 작성)

> **새 대화창에서 이 파일 + `AI_HANDOFF.md` + `docs/session_log_2026-07-21.md` 를 읽으면 즉시 이어서 작업 가능.**
> 브랜치 `dev`, 최신 커밋 **`403e31e7a`**. 전 pytest 스위트 **211건 통과** 확인(2026-07-22).

---

## 0. 지금 어디까지 왔나 (한 문단)

무료 공통 API 키의 극소 Pro 한도에서 A-1 스프린트가 완주 못 하던 문제를 잡기 위해, 지난 세션들에서
**Pro 예산 보존(JUDGE Flash화) → Pro 볼륨 감축(LOW_QUOTA_MODE) → 대기 제거(per-model 쿨다운·체인
정제) → 실측 관측(운영 계기판)** 4대 조치를 넣었고, 어제(07-21 후반) 외부 환경에서 **쿼터 완전 고갈
핫픽스 + 텔레메트리 토큰 실측(v2) + 실행단계 컨텍스트 다이어트** 3건을 추가했다. 코드·테스트는 건강한
상태(211건 통과). **다음 관문은 A-1 실제 완주**이며, 그 다음이 M1 기준정보 저장소 구현이다.

---

## 1. 어제 외부 세션이 추가한 것 (상세 분석)

### 1-1. `752d35275` — SUSPENDED_QUOTA HOTL 오탐지·무한루프 방지
- `core/async_orchestrator.py::is_hotl_pending()` — 스냅샷의 `factory_mode == "SUSPENDED_QUOTA"` 면 **False 반환**.
  (쿼터 완전 고갈로 멈춘 상태를 "사람 대기(HOTL)"로 착각해 무한 대기하던 것을 차단.)
- `run_e2e_scenario.py::wait_phase()` — `SUSPENDED_QUOTA` 감지 시 즉시 `failed:...` 반환(**fail-fast**, 타임아웃 대기 안 함).
- **평가**: 방향 정확. 쿼터 고갈은 인간 개입으로 풀 문제가 아니므로 HOTL이 아니라고 본 게 맞다.

### 1-2. `8cf42e558` — 텔레메트리 v2(토큰 실측) + 실행단계 컨텍스트 다이어트
- **토큰 실측**: `_ModelRecorder.on_llm_end` 추가 — `llm_output.token_usage`(OpenAI계) 또는
  `message.usage_metadata`(ChatModel계)에서 input/output 토큰 추출 → `_log_llm_call` 및 계기판
  `/summary`의 `total_input_tokens`/`total_output_tokens` 로 집계. (지난 세션에 v2로 예고했던 것 구현됨)
- **컨텍스트 다이어트**(`core/context_engine.py`):
  - 실행 단계에선 아키텍처 요약을 **절반(sm//2)으로 강제 압축**.
  - 기술명세는 현재 태스크의 `required_agents`를 보고 **마크다운 `#` 헤더 기준으로 무관 섹션을 잘라냄**
    (FE 전담 태스크엔 backend/api/db 헤더 섹션 제거, BE 전담엔 frontend/ui/client 섹션 제거).
- **평가**: 컨텍스트 낭비 감축 방향은 맞음. 단 아래 ⚠️ 리뷰 소견 참고.

### 1-3. `403e31e7a` — 문서 업데이트(session_log §5·§6, 향후 M1)

---

## 2. ⚠️ 내(제3자) 비평적 리뷰 소견 — 다음 세션에서 검토 필요

### ✅ R1. 컨텍스트 다이어트의 기술명세 필터가 **FE 태스크에서 API 계약을 버릴 수 있음** — **해결(2026-07-22, `9d740c380`)**
`context_engine.py`의 tech-spec 필터가 `api`를 `backend/database/db`와 한 묶음으로 취급해, FE 전담
태스크에서 **프론트가 호출할 API 계약(엔드포인트/요청·응답 스키마) 섹션까지 drop** → 연동 불일치 유발
가능성이 있었다.
- **조치**: API/계약/인터페이스 헤더를 별도 **SHARED 범주로 분리**해 FE·BE 양쪽 모두 **항상 유지**.
  `Backend API` 류 헤더는 SHARED 우선판정으로 보존, 순수 DB/서버 구현 섹션만 무관 담당에서 제거.
  분류 불가(개요 등) 헤더는 `keep=True`로 리셋(이전 drop 상태가 다음 섹션에 전파되던 버그도 수정).
- **회귀 테스트 3건 추가**(`tests/test_context_full_files.py`): FE→계약 유지·DB 제거 / BE→FE 제거 / 풀스택→전체 유지. 전 스위트 **208건 통과**.

### 🟡 R2. `SUSPENDED_QUOTA` **재개 경로 부재** — **결정: resume 경로 구현(향후 세션)**
HOTL이 아니므로 UI 재개 게이트가 안 뜨고, 현재는 "fail-fast 종료 → 처음부터 재실행"만 가능하다.
- **사용자 확정(2026-07-22)**: "처음부터 재실행"이 아니라, **쿼터 회복 시 SUSPENDED 지점부터 resume**하는
  체크포인트 재개 경로를 구현하기로 결정. (이번 세션엔 착수하지 않음 — 규모 있는 작업으로 향후 진행.)
- 착수 시 참고: `run_e2e_scenario.py::wait_phase()`의 `SUSPENDED_QUOTA` fail-fast 반환 지점,
  `core/async_orchestrator.py::is_hotl_pending()`, 체크포인트 DB(`pipeline_state.db`) 재개 지점 매핑 필요.

### 🟡 R3. 토큰 실측이 **code 모드(structured output)에서 0일 수 있음**
`with_structured_output`(코드 생성) 경로는 `usage_metadata`/`token_usage`가 응답 객체에 안 실릴 수 있어
input/output 토큰이 0으로 남을 가능성. 계기판 토큰 합계가 코드 단계를 과소집계할 수 있으니, 실측 후
0으로 나오면 code 경로 별도 처리 필요.

---

## 3. 다음 할 일 (우선순위)

1. **A-1 관문 재실행 (별도 환경, 쿼터 회복 후)** — 4대 조치+어제 3건+R1 수정이 적용된 `dev`로 완주 실측.
   완주하면 계기판 📊에서 `used`(실제 모델)·`downgraded`·**토큰 합계**·단계별 소요 확인.
   실패하면 `SUSPENDED_QUOTA`로 fail-fast 되므로 어느 단계에서 소진됐는지 로그로 즉시 파악 가능.
2. ~~**R1 검토·수정**~~ ✅ **완료(`9d740c380`)** — API 계약 섹션을 FE·BE 양쪽 항상 보존하도록 분리.
3. **R2 resume 경로 구현** (사용자 확정) — 쿼터 회복 시 SUSPENDED 지점부터 재개하는 체크포인트 경로.
   §2 R2의 착수 참고 지점 사용.
4. **M1 기준정보 저장소 구현** — `docs/design_master_data_m1.md`(복합 PK·별칭 오탐 방지·결정론 선정
   반영본)대로 `core/master_data.py`(DDL·CRUD·별칭감지·get_master_context) → API → ContextEngine 주입.
   (환각 차단·모델 불변성의 최강 축)
5. **골든 벤치마크** 구축 → 이후 LOW_QUOTA_MODE 단계별 Pro 복귀를 점수로 판정.
6. **R3 (code 모드 토큰 실측 0 여부)** — A-1 완주 로그에서 code 단계 토큰이 0이면 `with_structured_output`
   경로 별도 토큰 집계 처리 추가.

---

## 4. 새 대화창 시작 방법

```
docs/NEXT_SESSION_2026-07-22.md 와 AI_HANDOFF.md 읽고 이어서 작업해줘.
```
- 환경 세팅: `AI_HANDOFF.md §0`(git pull → pip install -r docs/requirements.txt → run.py / npm run dev)
- 테스트 재개: `docs/test_plan/02_progress_tracker.md`(P2 A-1이 다음 관문)
- 설계 근거: `docs/design_master_data_m1.md`, 고도화 로드맵은 `AI_HANDOFF.md §2-3`

## 5. 상태 스냅샷 (2026-07-22 갱신)
- 로컬 `dev` = **`9d740c380`** (R1 수정 커밋). ⚠️ 아직 `git push` 안 함 — 다음에 push 필요.
- pytest **208건 통과**(이 환경 `.venv` 기준, 신규 회귀 0). ※ 이전 세션 211건과의 차이는 환경별
  선택 의존성(playwright/chromadb 등) 수집 차이로 추정 — 실패/에러 0.
- 미커밋: `data/interaction_log.jsonl`(런타임 로그)만.
- **인터프리터 주의**: 이 PC의 실제 가상환경은 `venv\`가 아니라 **`.venv\Scripts\python.exe`** 다
  (AI_HANDOFF §0의 `venv\` 예시와 경로 다름). 시스템 Python312에는 deps 없음.
- 주의: 폴더 클라우드 동기화 중일 수 있음 → 작업 직후 commit/push 습관화.
