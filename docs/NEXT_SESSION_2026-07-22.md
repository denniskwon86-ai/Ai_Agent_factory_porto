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

### ✅ R2. `SUSPENDED_QUOTA` **재개 경로** — **구현 완료(2026-07-22)**
HOTL이 아니므로 재개 게이트가 없어 "처음부터 재실행"만 가능하던 문제를, **중단 지점부터 재개**하는
경로로 해결. (기존 `_resume_stream`의 `astream(None)` 체크포인트 재개 인프라 재사용.)
- **`state_models.py`**: `pre_suspend_mode` 필드 신설 — 동결 직전 정상 모드 보존.
- **`core/async_orchestrator.py`**: 중복 SUSPEND 처리를 `_suspend_for_quota()` 헬퍼로 통합(직전 모드
  보존, 재소진 시 원본 유지). **`resume_from_suspend()`** 신설 — 실행중/미동결 방어 → `factory_mode`를
  `pre_suspend_mode`로 **복구**(이게 있어야 재개 후 `is_hotl_pending` 정상화) → `astream(None)` 재개.
  쿼터 미회복이면 재개 스트림이 다시 소진을 만나 자연 재동결(무한루프 없음).
- **`api/routes/factory_control.py`**: `POST /{pid}/sprint/resume-quota`(미동결 대상은 409).
- **프론트**: `QUOTA_EXHAUSTED` 시 `suspendedTaskId` 저장, 배너에 **[▶️ 중단 지점부터 재가동]** 버튼 배선.
- **테스트**: `tests/test_quota_resume.py` 6건(모드 보존/복구·미동결/실행중 거부). 전 스위트 **214건 통과**,
  프론트 `tsc --noEmit` 통과.
- **미검증(런타임)**: 실제 쿼터 소진 재현이 필요한 E2E 재개는 A-1 재실행 시 함께 실측 필요.

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
3. ~~**R2 resume 경로 구현**~~ ✅ **완료(2026-07-22)** — 중단 지점부터 재개(§2 R2 참조). 단 E2E 재개
   실측은 A-1 재실행(쿼터 소진 재현) 시 함께 확인 필요.
4. **M1 기준정보 저장소** — ✅ **완료(2026-07-22, 백엔드+주입+UI)**.
   - 백엔드: `core/master_data.py`(SQLite DDL·CRUD·복합PK 개정 리니지·별칭 단어경계 감지·결정론 선정·
     `get_master_context`) / `api/routes/master_control.py`(타입·레코드·별칭·CSV·grounding preview,
     main.py 등록) / `ProjectState.master_domains` + `project_meta` 연동 + start_sprint 주입 /
     ContextEngine 주입(지식팩 그라운딩 **앞**) / `tests/test_master_data.py` 11건 / gitignore.
   - UI: `frontend/src/components/MasterDataPanel.tsx`(설계 §5 "🗂 기준정보 마스터" — 타입/레코드/
     별칭칩/CSV/주입 미리보기) + App 헤더 버튼 + 프로젝트 생성 폼 `master_domains` 입력.
   - **런타임 검증 완료(브라우저 E2E)**: 타입 생성 → 레코드 생성(속성/도메인 저장) → 별칭 칩 →
     주입 미리보기(별칭 감지 `매칭: PROC-ASSY-01` + 기준정보 블록 렌더)까지 실동작 확인. tsc 통과.
   - 잔여(후속): 캐시와의 상호작용은 무해 확인(기준정보가 프롬프트→캐시해시에 포함되어 변경 시 자동
     무효화). M2(크로스워크)·시뮬 승격 루프는 로드맵대로 이후.
5. **골든 벤치마크** — ✅ **프레임워크 구축 완료(2026-07-22)**. `core/golden_benchmark.py`(3축 채점:
   deterministic LLM0콜 + llm_judge[score_stage 재사용] + human, 스코어카드 저장, 골든 승격, 회귀비교)
   + `api/routes/benchmark_control.py`(scenarios·evaluate·human-score·promote-golden·compare) +
   `tests/test_golden_benchmark.py` 6건. **골든 데이터는 A-1 완주 후 시드**(promote_golden). 대표 세트
   A-1/C-1/D-1(C-1·D-1 project_id 는 완주 시 실제 폴더명으로 조정). 잔여: 뷰 UI(선택), A-1 완주 후 골든 고정.
6. **R3 (code 모드 토큰 실측 0 여부)** — A-1 완주 로그에서 code 단계 토큰이 0이면 `with_structured_output`
   경로 별도 토큰 집계 처리 추가.
7. **M2 스키마 레지스트리 + 키 크로스워크** — ✅ **완료(2026-07-22, 백엔드+UI)**. 설계
   `docs/design_master_data_m2.md`(a/b/c 확정)대로: `core/crosswalk.py`(시스템·스키마 CRUD·propose
   [결정론+Flash 옵트인]·approve/reject·mappings, DDL 은 master_data 소유) + `api/routes/crosswalk_control.py`
   + main.py 등록 + `frontend/src/components/CrosswalkPanel.tsx`(🔗 연계/크로스워크 버튼) +
   `tests/test_crosswalk.py` 7건. 매핑은 승인(confirmed=1)해야 유효. 브라우저 UI 마운트·API E2E 검증 완료.
   ~~**다음(M3)**~~ ✅ 아래 8번에서 완료.
8. **M3 MCP 데이터 브로커** — ✅ **완료(2026-07-22, 백엔드)**. 설계 `docs/design_master_data_m3.md`
   (a~e 확정)대로: `core/mcp_broker.py`(어댑터 인터페이스+`MockMCPAdapter`, `resolve`[온디맨드·캐시·
   as_of], `invalidate`, `health`, 읽기전용·정직한 실패·필드→속성 라벨링) + `api/routes/mcp_control.py`
   + main.py 등록 + `tests/test_mcp_broker.py` 9건. 별도 `data/mcp_cache.db`(TTL 캐시, 복제 아님).
   승인 매핑(confirmed=1)+활성 시스템만 조회. **실 MCP 커넥터는 `set_adapter`로 교체**(v1 목).
   - ✅ **UI 실측 조회**(2026-07-22): CrosswalkPanel 승인 매핑에 [🔄 실측 조회] 버튼 → `/mcp/resolve`
     결과(값·as_of·cache) 인라인 표시.
   - ✅ **ContextEngine 실측 병기 토글**(2026-07-22): `ProjectState.mcp_live_grounding`(기본 off) +
     project_meta 연동 + start_sprint 주입 + 프로젝트 생성 폼 체크박스. 켜면 `mcp_broker.get_live_context`
     가 활성 시스템 승인 매핑을 온디맨드 조회해 M1 골든값 뒤에 '참고(비신뢰)·as_of' 블록으로 병기.

---

## 4. 새 대화창 시작 방법

```
docs/NEXT_SESSION_2026-07-22.md 와 AI_HANDOFF.md 읽고 이어서 작업해줘.
```
- 환경 세팅: `AI_HANDOFF.md §0`(git pull → pip install -r docs/requirements.txt → run.py / npm run dev)
- 테스트 재개: `docs/test_plan/02_progress_tracker.md`(P2 A-1이 다음 관문)
- 설계 근거: `docs/design_master_data_m1.md`, 고도화 로드맵은 `AI_HANDOFF.md §2-3`

## 5. 상태 스냅샷 (2026-07-22 갱신)
- 로컬 `dev` = R1 + R2 + M1(백엔드/주입/UI) + 3번문서 + 2번 골든벤치마크 + M2 설계 + **M2 구현** 누적.
- pytest **248건 통과**(이 환경 `.venv` 기준, 회귀 0). 내역: R2까지 214 + M1 11 + 캐시 1 +
  골든벤치마크 6 + 크로스워크 7 + MCP브로커 9. 프론트 `tsc --noEmit` 통과(M1 UI·골든·M2 UI 포함).
- **로드맵 M1·M2·M3 전부 구현 완료.** 남은 최종 단계 = A-1 완주 재실행(별도 환경, 쿼터 회복 후).
  ※ 이전 세션 211건과의 기준 차이는 환경별 선택 의존성(playwright/chromadb 등) 수집 차이로 추정.
- ⚠️ **동시 작업 감지**: 워킹트리에 외부 세션의 'LLM Exact 캐시'(core/cache_manager.py 신규 +
  core/llm_gateway.py 수정 + tests/test_cache_manager.py) 유입됨. **이 커밋에는 포함하지 않음**
  (M1 파일만 선택 스테이징). 캐시 변경 검토 소견은 세션 대화 참조 — TTL/무효화 부재·재작업 루프
  무력화·토론 다양성 상실 위험 있어 그쪽 작업자와 협의 필요.
- 미커밋: `data/interaction_log.jsonl`(런타임 로그)만.
- **인터프리터 주의**: 이 PC의 실제 가상환경은 `venv\`가 아니라 **`.venv\Scripts\python.exe`** 다
  (AI_HANDOFF §0의 `venv\` 예시와 경로 다름). 시스템 Python312에는 deps 없음.
- 주의: 폴더 클라우드 동기화 중일 수 있음 → 작업 직후 commit/push 습관화.
