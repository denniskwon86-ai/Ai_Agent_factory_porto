# L2 업무·통합 Studio — 다른 모델/세션 재개 인수인계

> 2026-09-15 이후 작업 재개는 [Claude Code 시작 안내](CLAUDE_CODE_START_HERE_2026-09-15.md)를 먼저 읽는다. 사용자 후속 승인으로 동일 스냅샷의 **키 없는 ZIP 공유본**이 추가됐다. [최신 복원 절차](../../data_sync/README.md)를 우선하며 아래 키 필요/평문 금지 문구는 과거 암호화본 승인 기록이다. B5/B6 다음 작업도 최신 안내로 갱신됐다.09-13 스냅샷이 이후 데이터까지 자동 동기화하는 것은 아니다.

작성: Codex · 2026-09-13 23:30 KST. 사용자 요청: 현재 작업과 설정 데이터를 보존하고, 다른 모델이 같은 브랜치를 pull하여 이어받도록 상세 인계 후 commit/push.

> **최신 전달 상태 — 2026-09-13 23:45 KST:** 앞선 `58713ed1d`는 보안 검토에 따라 코드·문서만 전달했다. 이후 **공개 저장소에 암호화된 업무 데이터 스냅샷을 추가하고 키는 별도 비공개 전달한다는 조건**에 사용자가 “네 승인합니다”로 명시 승인했다. 이 추가 커밋에는 `data_sync/session-data-20260913.aesgcm`을 포함한다. 암호문은 pull로 받되 **키는 Git에 없으므로 비공개로 별도 전달받아야** 한다. 아래 같은 절대경로 복원/다른 경로 검사전용·인증계정 미이관 제한은 그대로다. 평문 DB나 키를 공개하는 승인은 아니다.

## 0. 새 세션이 먼저 알아야 할 결론

- 작업 브랜치: **`codex/l2-unified-studio-20260912`**. 이전 원격 기준은 `58e666833b6d346297231a6e8da5c1aef8ac5cc2`이다. 이 문서를 포함한 후속 커밋이 인계 기준이며 실제 SHA는 `git log -1`로 확인한다.
- 원격: `https://github.com/denniskwon86-ai/Ai_Agent_factory_porto.git`. GitHub API에서 **public** 확인. 원본 업무 DB/RAW는 평문 공개하지 않고 암호화 파일로 전달한다.
- 전체 제품 진척 **21/40 = 52.5%**, 로컬 구현 **18/28 ≈ 64.3%**. B0~B4 지정 코드 출구 완료, B5 부분 완료, B6/B7 미완료. 이번 인계/백업/시험을 제품 완료 칸에 더하지 않는다.
- **다음 구현은 일반 HOTL 제출의 저장 초안 사용완료 결속 + B5 잔여 출구 판정**. 집중 검증 포함 45~75분 초기 예상. 이미 끝낸 실행 명령·일반 재개·HEAL을 다시 구현하지 않는다.
- 전역 `main.py`, `frontend/src/App.tsx`는 이번 L2 구현에서도 변경하지 않았다. 두 생성기 진입점을 합치는 B6은 아직이다.
- 사용자 요구: 빠르게 사용 가능한 기능 묶음을 마감하고, 작업 내용/완료 근거/남은 범위/전체 진척/다음 예상 시간을 구체적으로 보고한다. 상태 보고만 하고 다음 구현을 멈추지 않는다. 긴 검사를 반복해 시간을 소비하지 않는다.

## 1. 필독 순서와 의사결정

1. `.agents/AGENTS.md`
2. `docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md`
3. `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md`
4. `docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md`
5. `PROGRESS.md` **최상단 최신 기록**
6. `docs/design_business_kit_l2_process_setup_2026-09-12.md`
7. `docs/design_l2_unified_studio_execution_2026-09-12.md` (revision2.1과 후속 실행 갱신/§11)
8. 본 인계 + 필요한 단계별 인계

이 작업은 권고 착수4·7·10(G2 업무 의미/구조→G3 Factory/AppShell), 선행5·6(데이터 안전성)에 해당한다. 첫 원료구매 폐루프의 회사·업무·데이터·생성 앱 문맥을 연결하는 작업이다. 과거 관리평가 진행률이나 UI 시험 건수를 전체 제품 완성도로 대신하지 않는다.

사용자가 승인한 설계 결정:

- 업무키트에 수정 가능한 **L1/L2 표준 업무 골격**을 제공한다. 상세 업무를 처음부터 현업에게 전부 떠넘기지 않는다.
- L2는 업무 분류/문맥이다. 제작 단계나 순차 실행 엔진이 아니다.
- 회사·조직/REAL·VIRTUAL·COMPETITOR, L1/L2 업무 위치, 제작 진행의 세 축을 분리한다.
- `AdaptiveProductionStudio`, `RunControls`, 기존 store/API를 재사용한다. 제3의 생성기를 만들지 않는다.
- 기본 흐름: 업무 선택→요구 입력→현재 필요한 행동→제작/검토/사용 준비. 고급 조작은 뒤로 보내되 기존 기능을 삭제하지 않는다.
- 29개의 개별 ERP 업무 앱 전부 구현, 자동 발주/입고 확정/지급, 실적 인증 승격, 운영 배포는 이번 범위 밖이다.
- 업무 정의 승인 ≠ 데이터 인증 ≠ 실행 승인 ≠ 사용 준비. 하나의 승인으로 다른 권한을 얻지 않는다.

## 2. 단계별 현황과 읽을 코드

| 단계 | 이번 브랜치의 결과 | 남은 경계 / 정본 인계 |
|---|---|---|
| B0 | 데이터 소비 fail-closed, 실제 인증 권한/불변 대상/원자성/멱등 | 전체 제품/운영 인증 완료가 아님. `L2_STUDIO_B0_IMPLEMENTATION_2026-09-13.md`, `L2_STUDIO_B0B_CERTIFICATION_2026-09-13.md` |
| B1 | ECM v2 안전 저장, 문맥별 head, 명령 제안/CAS/타인 승인, v1 writer guard | 감사 outbox는 로컬 PENDING. `L2_STUDIO_B1_STORAGE_2026-09-13.md` |
| B2 | 불변 프로세스 팩, 계획→설치→별도 승인→적용, v1 명시 이관/보존 | 새 Starter 출시·운영 설치가 아님. `L2_STUDIO_B2_SETUP_2026-09-13.md` |
| B3 | 서버 고정 문맥, 요구 초안/결정 차수/같은 ID 승격, 일반·키트 v2 계약 소비, 릴리스/Host 경계 | 실제 LLM/운영 데이터/브라우저 수용은 미완료. `L2_STUDIO_B3_CONTEXT_2026-09-13.md` |
| B4 | 설치·탐색·재개·검토 UI, 이름/설명/순서와 업무 추가/사용 상태/이동/바로가기 편집, 제품 내 진입 | 코드·집중 검사 마감. 실제 브라우저 클릭/포커스 수용 OPEN. `L2_STUDIO_B4_INSTALLATION_FLOW_2026-09-13.md` |
| B5 | 대표 행동/결정패널, 요구·입력 초안, 키트 계약 검토, 수정 요청 멱등 접수/복구/초안 소비, 실행 명령/일반 재개/HEAL | **부분 완료**. 일반 HOTL 초안 소비 및 잔여 판정 필요. `L2_STUDIO_B5_CORE_2026-09-13.md` 최신 23:03 기록 우선 |
| B6 | 설계됨 | 단일 진입/URL/상태 복원/회사 문맥/SSE 단일 mount, 레거시 parity. 전역 파일 담당 1명 |
| B7 | 설계됨 | 실제 브라우저·접근성·현업 수용·기존 설정 보존 회귀 |

위 단계별 파일은 모두 `docs/handoff/`에 있다. 파일 안의 과거 “미구현/다음 예정” 문장은 이후 최신 추가 기록이 대체한다. 특히 B5 하단에 남은 “일반 재개/HEAL 미구현”은 23:03 기록 이후 현재 상태가 아니다.

핵심 파일 묶음:

- ECM: `core/enterprise_context/process_{schema,configuration,installation,context,references}.py`; `api/routes/process_{configuration,installation}_control.py`.
- 팩/키트: `core/data_preparation/process_{pack_artifacts,kit_instances}.py`, `process_packs/afs.manufacturing.materials-processes/1.1.0/` 4개 JSON. **8 L1/29 L2, NO_DATA/DOMAIN_REVIEW_REQUIRED, REFERENCE_ONLY 앱 후보**다. 기존 Starter 1.0.0을 변경하지 않았다.
- B3 서버: `core/studio_{drafts,bootstrap,project_context,contract_reconcile,hotl_context,release_context,release_readiness,runtime_data}.py`, `core/advisor_{revision_store,bootstrap_ledger}.py`와 해당 `api/routes/studio_*`.
- B4 화면: `ProcessInstallationPanel`, `ProcessConfigurationEditor`, `ProcessStructureEditor`, 기존 `CompanySetupPanel/EnterprisePage/KitOperationsPanel`, `processInstallationFlow` 및 편집 모델.
- B5 화면: `StudioDecisionPanel`, `StudioInputDraftControls`, `RevisionRequestEditor`, `StudioExecutionRequests`, `studioNextAction`, 기존 `AdaptiveProductionStudio/RunControls/ProjectHeader/sprintActions/useFactoryStore`.
- API/flow는 `frontend/src/lib/studio*`, `kitContractReview*`에 있다. UI에 동일 요청/권한 계약을 다시 구현하지 않는다.

## 3. 마지막 완료 기능 — 재개·실행 요청·오류 복구

서버 API:

```text
POST /api/v1/factory/{pid}/execution-commands
GET  /api/v1/factory/{pid}/execution-commands
GET  /api/v1/factory/{pid}/execution-commands/{uuid}
```

요청은 `client_request_id:UUID`, `operation:START|RESUME|RESUME_QUOTA|PAUSE|STOP|HEAL`, `task_id`, 닫힌 `input` DTO다. START는 initial_idea/master_data/feedback, HEAL은 error_log, 나머지는 빈 객체다. 64KiB 제한. actor/company/context/schema/전체 state를 클라이언트가 권위 있는 값으로 전달하지 않는다.

- `core/studio_execution_commands.py`: 요청 원문/지문/상태/결과를 Advisor DB 별도 표에 저장. PROCESSING→ACCEPTED/REJECTED/UNKNOWN, 동일 키·동일 본문 멱등, 다른 본문409, 종결 CAS. 비가시 문맥404. HEAL 서버 3회 상한(HOTL_PENDING 반환 포함).
- `core/studio_execution_guard.py`: 실행/계약 reconcile 동일 프로세스 예약. owner ContextVar는 **동일 asyncio Task**만 인정한다. 취소 시 실제 worker가 끝날 때까지 예약을 유지한다. 다중 서버 분산락은 아니다.
- `api/routes/studio_execution_control.py`: fresh 가시성→예약→권한→replay→실행 검사→접수→기존 handler→종결→최신 권한 확인. 실제 부작용 후 오류는 UNKNOWN. 구 START/QUOTA도 영속 UNKNOWN을 우회할 수 없다. 원키 없는 구 HEAL은409.
- `core/async_orchestrator.py`: pause/stop은 cancel만 요청하고 끝내지 않고 실제 종료 대기. `resume_existing`은 같은 thread/task/checkpoint로 `astream(None)`을 호출한다. 기존 산출물/WBS를 archive/reset하지 않는다. HOTL·quota·계약 오류와 수동 정지를 구분한다.
- `.studio_pause_state.json`: checkpoint/task/thread/next/template/context 지문을 고정한 PAUSED→CONSUMED proof. 단순 상태 문자열만 보고 재개하지 않는다.
- `core/studio_healing_task.py`: 요청 UUID로 고정한 `TASK_REV_HEAL_{uuidhex}`, 원 실패 task/명령 지문 결속. 엄격 WBS+FileLock+CAS+fsync/replace. 같은 키는 기존 task를 반환하며 진행 상태를 초기화하지 않는다. 현재 다른 task HOTL도 우선 반환한다.
- quota 상태 변경 후 재조회 실패는 `503/STUDIO_QUOTA_RESUME_UNKNOWN`으로 남긴다. 이미 쓴 뒤 False/REJECTED로 오판하지 않는다.
- `/state/latest`의 `studio_execution_state`는 실제 running/검증된 pause를 투영한다. **접수 CONFIRMED는 작업 실행중/완료를 뜻하지 않는다.**
- 프런트는 POST 후 원 UUID GET으로 확인한다. UNKNOWN은 같은 키 GET만 제공하고 자동 POST 재전송하지 않는다. 개별 fresh GET 검증 전 요청 본문을 숨긴다. 사용자/회사 전환과 늦은 응답으로 이전 입력이 노출되지 않게 한다.

같은 원칙의 수정 요청 API/불변 영수증/초안 소비는 직전 22:04 B5 인계에 상세히 있다. 구 `/sprint/revision`은409이고 새 `revision-requests`를 사용한다.

## 4. 검증 근거 — 무엇을 실행했고 무엇을 안 했는가

| 최종 지점 | 검증 | 범위/한계 |
|---|---|---|
| B0~B3 09:42 | 1923 PASS / Windows symlink 6 skip | 지정 통합, 저장소 전체 T3 아님 |
| B4 안정 통합 12:58 | full/jobs1 2187 PASS /7 skip/186 subtests | 2194 정확 수집·실행, 1645.47초. 이후 소스에 전체 PASS 승계 금지 |
| B4 구조편집 17:14 | 서버177 PASS/77.84초, 프런트105 PASS/375.67ms | 프런트104 UNIT/SSR +1 STATIC. 실제 클릭 아님 |
| B5 키트 검토 20:44 | 서버156 PASS/1422.62초, 프런트81 PASS | 무거운 4파일 묶음. 매 편집 후 다시 돌리지 않음 |
| B5 수정 요청 22:04 | 서버213 PASS/127.33초, 프런트105 PASS | 원번호·초안 소비·권한·WBS 회귀 |
| **B5 실행/재개 23:03** | **서버260 PASS/163.16초**, wrapper179.049초/0; **프런트127 PASS/1005.8953ms** | 서버790소스/259자산, 프런트31소스 전후 불일치0. SQLite535 own RUN/금지0 |

23:03 원본 보고서는 원본 PC의 `output/usage-holds-4w0j3fcs/isolation.json`, `output/studio-contracts-4b7a3635-658e-4bae-b645-a38ecfaa32b2/report.json`이다. output은 Git에 포함하지 않는다. 공개 가능한 요약은 `data_sync/verification-summary.json`에 별도 포함한다. 새 환경에서는 명령을 재실행해 자기 환경의 증거를 만든다.

- 최종 제품 tsc+Vite build, fixture build PASS. 지정 5파일 ESLint 오류0/cleanup ref 경고1. 기존 dynamic import/큰 chunk 경고는 남는다.
- 프런트127은 기존105+실행22이며 전체 STATIC4를 포함한다. API 대역/UNIT/React SSR을 실제 네트워크/브라우저 수용으로 표시하지 않는다.
- 독립 Hilbert가 quota 후조회 실패 오판과 다른 현재 HOTL 누락 P2 두 건을 지적했고 수정/회귀 추가 후 정적 재대조를 마쳤다. 시험 실행자는 main이며 독립 시험실행이나 전체 보안 인증이 아니다.
- **실제 브라우저 클릭·포커스·현업 수용 NOT_RUN.** 컴퓨터사용 초기화 환경 오류가 있었고 HTTP200/SSR/build로 대체 완료 처리하지 않았다.
- 실제 LLM/Host 운영 실행, 운영 회사 실제 인증·승인·데이터 마이그레이션, 분산 원자성, 운영 배포 미실행.
- 실패 기록은 각 단계 인계에 보존되어 있다. 첫 시험부터 모두 통과한 것처럼 바꾸지 않는다.

## 5. 검증 실행법과 시간 절약 규칙

Windows 기준 Python `venv/Scripts/python.exe`(현재3.14), Node `C:/Program Files/nodejs/node.exe`. 일반 `python`이 WindowsApps 별칭일 수 있다. 프런트 `package-lock.json`을 따르고 `npm ci`로 의존성을 복구한다. 새 Python 환경은 저장소 requirements를 먼저 확인한다. 암호화 유틸은 `cryptography` 필요(현재46.0.7).

저장소 루트에서 마지막 실행 경계 회귀:

```powershell
venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b5_execution_resume.py --target tests/test_b5_execution_commands_api.py --target tests/test_b5_execution_command_store.py --target tests/test_b5_healing_task.py --target tests/test_b3_execution_guard.py --target tests/test_b3_hotl_api.py --target tests/test_b5_revision_requests.py --target tests/test_route_authority_table.py::test_every_table_entry_matches_a_real_route --target tests/test_route_authority_table.py::test_every_write_route_is_decided
```

`frontend/`에서:

```powershell
node scripts/check-studio-contracts.mjs
node scripts/check-process-installation.mjs
npm run build
node scripts/build-studio-transition-fixture.mjs
```

암호화 도구 자체 시험은 루트에서 `venv/Scripts/python.exe -B -m unittest tests.test_session_data_snapshot -v`.

효율화 정본은 `docs/testing_efficiency_2026-09-13.md`다. 변경 최소 회귀→기능 묶음→안정 통합 지점에서 full 순으로 수행한다. `scripts/run_verification.py --tier quick|feature|full --jobs 1` 지원. feature의 `--changed PATH` 및 `--plan-only`로 범위를 먼저 확인한다. 기본 jobs1. 보안/권한 경계를 속도 때문에 skip하지 않는다.

주의:

- no-conftest 격리 runner에서 `test_route_authority_table.py` 전체를 선택하면 `ecm_org_seed` 없는 일부 시험이 ERROR가 된다. 위 두 명시 nodeid는 통과한 정확한 선택이다.
- source/asset fingerprint가 실행 중 바뀌면 시험 숫자가 PASS여도 wrapper 실패다. 수정 동결 후 다시 검증한다.
- venv 없이 전역 Python, 전체 `pytest` 직접실행, 운영 DB를 사용하는 임의 스크립트/마이그레이션을 먼저 시도하지 않는다.
- 새 모델은 현재 도구의 권한 지침을 따른다. 과거 환경 오류를 근거로 권한 우회하지 않는다.

## 6. 바로 보는 합성 UI

fixture 생성물은 Git에서 제외된다. 위 build 후 루트에서 정적 서버를 별도 터미널로 실행:

```powershell
venv/Scripts/python.exe -m http.server 8768 --bind 127.0.0.1 --directory output/process-installation-browser
```

기존8768 서버가 있으면 중복 실행하지 않는다. 이 서버는 제품 API/LLM 서버가 아니다.

- `/tests/studio-transition.fixture.html?scene=execution`: 실행 요청 목록/오류 복구/응답 유실 후 원키 확인.
- `?scene=paused`: 멈춘 기획/일반 작업 이어하기.
- `?scene=revision`: 저장 초안→수정 요청 접수→사용완료.
- `?scene=kit`: 키트 계약 검토/자기 승인 차단/조회 오류.
- `/tests/process-installation.fixture.html`: B4 설치·표시/구조 편집(필요시 `build-process-installation-fixture.mjs`로 별도 빌드).

합성 메모리 API, 미지원 요청 실패, CSP connect-src none, 실제 API fallback 없음. **이 화면의 메모리 데이터는 운영 DB의 L2 설치 결과가 아니다.** 새로고침/새 브라우저에서 상태가 초기화되는 것이 정상이다.

## 7. 데이터가 pull에 따라오지 않았던 이유와 이번 전달

`.gitignore`가 `*.db`, `data/master/`, `data/raw/`, `projects/`, `data/reference_registry.json`, `data/scope_policy.json`, `agents_registry.json`, 모델 라우팅/로그/환경 파일을 제외한다. `core/paths.py`는 각 checkout의 루트를 기준으로 `data/`를 고정한다. 별도 checkout은 별도 DB를 보며 `pull`은 이 ignored 런타임을 동기화하지 않는다.

이번에는 다음을 함께 전달한다:

1. 신규 코드/시험/단계별 인계와 불변 표준 프로세스 팩4파일을 Git 추적.
2. `data_sync/session-data-20260913.aesgcm`: 실제 현재 업무 DB15개+RAW143개+설정6개, 총164개(원문105,391,236bytes, 암호문13,672,011bytes). 실제 현재 설정이며 새로 꾸민 fixture로 대체하지 않았다. RAW는 data/raw/141개와 구 raw/의 실제 참조2개를 포함한다.
3. `data_sync/snapshot-public.json`: AES-256-GCM, 암호문 SHA `c0dded58abf4eb0b8e30ba0c8f2504b70024651b38c32f657cd6bac718809790`, 건수와 제외 범위만 공개.
4. `scripts/session_data_snapshot.py`와 시험/README: 암호화 내보내기, 인증 복호화·파일 지문 검증, 무덮어쓰기 복원.
5. **키는 별도**: 원본 PC `C:/WorkSpace/gemini_agent_team_verG/output/session-handoff/session-data-20260913.key`. 값은 문서/로그/Git에 기록하지 않는다. 다른 PC에는 비공개 경로로 직접 전달해야 한다. `pull`만으로 복호화할 수 없는 것이 의도된 보안 경계다.

원본 DB에는 ECM 법인19/조직노드32/프로필8(기존 process_profile 포함), DP 키트 인스턴스1/원천결속35/스냅샷38이 있다. 스냅샷 중 합성만 있는 것이 아니라 REAL 표시 2건도 있어 평문 공개를 막았다. **REAL 표시/기존 인증 상태를 이번 턴에서 새로 검증하거나 승격한 것이 아니다.**

현재 운영 ECM/DP에는 신규 B1/B2 L2 설치 표가 아직 없다. B0~B5 개발 검증은 격리 DB/합성 fixture에서 했으며 사용자 운영 설정을 몰래 v2로 이관하지 않았다. “새 코드가 있다”와 “운영 데이터에 L2 팩이 이미 적용됐다”는 별개다.

원장·역할·정책·승인 결속은 암호문 안에서 원형 보존한다. 인증 DB, 비밀번호, 세션, 커넥터 자격증명, Advisor 개인 대화/로그, 생성 프로젝트/체크포인터는 제외한다. 따라서 진행 중인 생성 작업 자체의 이전이나 같은 로그인 재현까지 완료했다고 주장하지 않는다.

복원 절차와 명령은 [data_sync/README.md](../../data_sync/README.md) 참조. 핵심:

- 원본 PC 같은 checkout이면 데이터는 이미 있으므로 다시 덮어쓰지 않는다.
- 다른 PC, **동일 절대 루트 `C:/WorkSpace/gemini_agent_team_verG`**의 새 checkout에서 앱을 띄우기 전에 복원한다. 같은 Git 설정 파일만 유지, 기존 DB/다른 설정은 전부 사전 거절한다.
- 다른 폴더/OS에서는 `--copy-only`로 검사 사본만 복원한다. DB의 절대 RAW/Starter 경로를 임의 치환하면 지문/승인 결속을 깨뜨릴 수 있어 자동 relocation을 구현하지 않았다.
- 새 환경 로그인 계정/역할의 적격 연결은 별도 확인한다. 복원한 역할을 새 사용자의 관리자 권한으로 자동 승계하지 않는다.
- 누락된 library/프로젝트/체크포인터를 요구하는 기능은 별도 이관 범위다. 앱이 기동된다는 사실만으로 동일 실행 상태라고 보고하지 않는다.

내보내기 최종 원본 본체/WAL 지문 전후 일치. 첫 시도는 전후차이를 감지해 결과 생성 전 중단했으며 원인을 확정하지 않았다. 재시도는 안정된 지문으로 완료. 여러 DB의 전역 원자 스냅샷으로 과장하지 않는다. 실제 암호문 인증 복호화/164파일 지문/검사 사본 복원, SQLite15 quick_check/107표 건수/38 RAW 참조 checksum 모두 일치. 실제 앱의 동일 경로 복원·로그인·수용은 별도 미검증이다. 최초 unittest는 테스트 연결 미종료로 Windows 임시파일 정리에8ERROR가 있었고 closing/commit 보완 후 최종10PASS. 이전 RAW2개 누락 암호문/키는 output/session-handoff/superseded/에만 보존하고 Git에서 제외한다.

인계 직전 프런트 계약 재실행 `output/studio-contracts-d1389a79-221b-48f9-b102-76dcda0cd204/report.json`도127PASS/실패0. 제품 구현 소스는 23:03 이후 바꾸지 않았고 이번 새 변경은 인계/암호화 전달 도구와 시험이다.

23:36 추가 독립검토 보완: RAW는 CSV만 허용하고 숨김/인증/키 계열 파일명을 export/restore 공통으로 거절한다. `--copy-only`는 지정 위치의 `inspection-files/` 아래에만 쓰며 마커를 먼저 생성한다. 실제 앱의 data/를 채우지 않는다. 원래10시험+회귀2개=최종12PASS/0.538초. 최종 암호문164파일 재검증 및 `output/session-handoff/reviewed-inspection-copy/inspection-files/` 복원 PASS. 민감 CSV 본문 전체 DLP나 사용자 권한 자동이관 보장은 아니다.

Hilbert가 위 두 수정점의 정적 종결을 확인했다(독립 실행 아님). 커밋 점검에서 `tests/test_b3_contract_reconcile.py`의 끝 빈 줄 하나를 제거했으므로 해당 시험 파일의 원시 해시는 과거 검사 시점과 달라진다. 제품 구현 의미 변경은 없다.

## 8. 다음 구현 순서·완료 기준

### 8.1 일반 HOTL 초안 소비 + B5 잔여 (45~75분 초기 예상)

1. `studio_input_drafts.py`, `studio_input_draft_control.py`, `studio_hotl_context.py`, 실제 HOTL 제출 handler를 대조한다. 수정 요청/키트/일반 HOTL의 target·revision·digest와 접수 증명을 섞지 않는다.
2. 저장한 개인 초안이 실제 같은 업무/대상/본문의 제출로 확정되었을 때만 명시 사용완료 CAS에 연결한다. 접수 UNKNOWN은 원키 확인, 재전송/자동 소비 금지.
3. UI에 현재 입력·저장 여부·제출/사용완료 결과를 연결하고 사용자/회사 전환·늦은 응답·재조회 실패에서 입력/권한 경계를 검증한다.
4. 관련 API/flow/SSR만 집중 검증하고 B5 설계의 모든 출구를 표로 판정한다. 단지 이 한 묶음 완료만으로 B5 전체를 닫지 않는다.

남은 알려진 항목: legacy release/replan의 내구 영수증 없는 UNKNOWN, 서버 PROCESSING/UNKNOWN 운영 복구(자동 재실행 금지), 실제 브라우저, 세부 접근성. B5 또는 후속의 어느 출구인지 설계와 대조해 명시한다.

### 8.2 B6 단일 진입 통합

new/draft/project/kit/release/mega 유형별 resolver와 URL 복귀, bootstrap 완료→동일 project, 회사 문맥/SSE 중복 mount 방지, 기존 레거시 동작 parity를 연결한다. 전역 파일은 한 담당자가 소유한다. ETA는 B5 잔여 판정 후 범위를 읽고 재산정한다.

**중요 선행:** AGENTS가 요구하는 병렬개발 통합 계획을 확보/정독하기 전 B6 전역 연결을 시작하지 않는다.

- 원본: `workspace/codex-three-week-mvp/docs/roadmap/PARALLEL_DEVELOPMENT_INTEGRATION_EXECUTION_PLAN_2026-08-15.md`
- 통합 후 정본: `docs/roadmap/PARALLEL_DEVELOPMENT_INTEGRATION_EXECUTION_PLAN_2026-08-15.md`
- 인계: `docs/handoff/PARALLEL_INTEGRATION_EXECUTION_HANDOFF_2026-08-15.md`

이번 턴 앞의 두 계획 경로에서 파일을 확인하지 못했다. 임의 요약본을 정본처럼 만들지 않았다. B6 착수 전에 원본 보유 작업공간/브랜치에서 확인하고, 없으면 사용자에게 제공을 요청한다. 이번 작업은 동일 브랜치 변경 보존이며 다른 브랜치 merge/I-4 완료가 아니다.

### 8.3 B7 수용

실제 브라우저에서 주요 여정을 클릭하고 좁은 화면/키보드/포커스/빈 상태/비활성 이유/오류 복구/사용자·회사 전환과 기존 설정 보존을 검증한다. 실사용 검증 없이는 UI가 쉽다고 단정하지 않는다. 실제 데이터/배포/추가 외부 쓰기 권한은 별도 요청한다.

## 9. Git/보존/작업 운영 규칙

다른 PC의 새 clone 또는 자신의 변경이 없는 checkout에서:

```powershell
git status --short
git fetch origin
git switch codex/l2-unified-studio-20260912
git pull --ff-only origin codex/l2-unified-studio-20260912
git log -1 --oneline
```

로컬 브랜치가 없으면 `git switch --track origin/codex/l2-unified-studio-20260912`. dirty/분기 충돌이면 reset/전체 stash/강제 pull 하지 말고 변경 소유자를 확인한다. 기존 dev에 전체 브랜치를 merge하지 않는다. 사용자 승인 없는 운영 DB 변경·실승인·배포 금지.

원본 PC의 `data/interaction_log.jsonl`은 이 작업 전부터 수정돼 있었다. SHA256 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510`을 보존하고 이번 커밋에서 제외한다. **이미 tracked인 과거 내용/이력까지 Git에서 없어진 것은 아니다.** 이번 인계에서 Git history rewrite는 하지 않는다.

공개 저장소 스캔에서는 기존 HEAD에도 있는 계정 이메일형 식별자가 일부 문서에 있었다. 새 비밀값 패턴은 독립 검사에서 미탐지였으나 전체 이력/모든 바이너리의 무비밀 인증은 아니다. 민감자료 평문 확대 공개는 하지 않는다.

작업 시작 시 무엇을 만들지와 예상 시간, 진행 중에는 현재 바뀐 사용자 기능/장애, 단계 마감 시 완료·검증·미완료·전체21/40·다음 예상 시간을 보고한다. 수십 분 동안 무응답으로 검사만 돌리지 않는다.

## 10. 다음 모델에게 그대로 전달할 재개 요청

> 이 브랜치의 `.agents/AGENTS.md`, 상위 제품/로드맵, PROGRESS 최신 기록, `docs/handoff/L2_STUDIO_CROSS_SESSION_HANDOFF_2026-09-13.md`와 B5 23:03 인계를 읽고 이어서 구현하세요. 전체21/40=52.5%, 로컬18/28이며 B0~B4 지정 코드 출구 완료/B5 부분/B6·B7 미완료입니다. 다음은 일반 HOTL 저장 초안의 실제 제출·사용완료 결속과 B5 잔여 출구 판정입니다. 이미 완료한 실행 명령/일반 재개/HEAL을 다시 구현하지 마세요. 암호화 데이터는 data_sync/에 있고 키는 별도입니다. 새 경로 사본은 자동 경로 이관/실행 승인된 상태가 아닙니다. 작업 전 계획·예상 시간, 진행 중 기능 변화, 단계별 검증/전체 진척/다음 ETA를 구체적으로 보고하세요. 최소 관련 회귀로 반복하고 안정된 통합점에서 full 검사하세요. main.py/App.tsx 전역 통합은 B6이며 필수 통합 계획 확보 전 착수하지 마세요. 운영 DB·RAW·실승인·로그·기존 사용자 변경을 보존하세요.
