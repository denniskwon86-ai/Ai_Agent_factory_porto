# 1단계 운영 트라이얼 — 목표/현행 Gap 기반 전체 실행 계획

기준: **TRIAL-GAP-20260921-R3 / 2026-09-21**, 작성 Codex. 아래 목표53개와 Gap 분석은 유지한다. 사용자 추가 지시에 따라 큰 목표 전부완료/0점 방식을 폐기하고 [단계별 즉시 가산 실행계획](OPERATIONAL_TRIAL_DELIVERY_PLAN.md)과 [단계 원장](OPERATIONAL_TRIAL_DELIVERY_STEPS.json)을 적용한다.
정본: [기계 원장](OPERATIONAL_TRIAL_GAP_BASELINE.json). 보고 진입점은 [PROGRESS.md](../../PROGRESS.md).
**전환 시 전체 진척: 1800/5300점 = 34.0%. 목표 종결18/53, 단계 수용18/139.** 이후 현재값은 단계 원장/계산기로 산출한다. 아래35개 잔여 분류는 R2 시작 상태이며 중간 단계가 완료되면 상위 목표 종료 전에도 점수를 인정한다.
이번 작업은 목표/모수/판정의 재구성이며 새 제품 기능을 18개 구현했다는 뜻이 아니다.

## 1. 100%가 뜻하는 사용자 경험

실제 담당자는 자기 계정으로 접속해 원료구매 업무의 L2 표준 골격을 설치·변경하고, 승인된 회사/기간 자료를 등록·인증해 업무앱에서 사용한다. 요구를 작성해 앱을 제작·수정하고, 적격 판본을 전달·수락·실행한다. 원료/물류/재고 변화가 생산·재무에 미치는 영향을 근거와 계산으로 확인하고, 결정·실행과제·결과/효과를 같은 이력으로 추적한다.

그 시스템은 NCP의 PostgreSQL·공유 업무 상태 위에서 최대30명/동시10명으로 운영된다. 자체 배포관리 웹UI와 GitHub를 통해 신뢰 가능한 소스/산출물을 승인 배포하며, 일상 변경 중 세션·입력·작업을 잃지 않는다. 장애 시 코드 복귀와 자료 복원을 구분해 수행한다. 운영 이슈는 정제된 재현 정보와 운영 버전을 기준으로 로컬 Codex 수정→PR→검증→승인 배포로 이어진다.

- 기존7앱과 L2 변경 가능성은 범위에서 제거하지 않는다. 기존 표준팩은 참조 후보이지 현업 승인/데이터 완성품이 아니다.
- 실제 자료·실제 역할·반복 업무·권한 거절·장애/복구 증거가 필수다. 합성 fixture로 실제 인수를 대체하지 않는다.
- 모든 ERP의 양방향 연결이나 모든 업종의 업무 완성을 1단계 필수로 가정하지 않는다. 첫 폐루프에서 실제 내부 과제와 실행 증빙을 사용하며, 외부 전송 경로를 쓴다면 해당 실제 연계를 검증한다.
- 100/동시30, 200/동시50+, 두 번째 실제 법인 확산, 장기 코호트 ROI는 후속 목표로 보존한다. 첫 업무의 효과 기록/비교는 M05/U01에 포함한다.
- 계정 인증 방식, 실자료/비용/클라우드 승인, RPO/RTO는 미결 승인 항목이다. 불명확한 값을 임의 채워 100%로 만들지 않는다.

## 2. 어떻게 완전히 다시 구성했는가

**목표 사용자 행동 → 필요한 생산자/소비자/정본 → 현행 코드·실행 증거 → 남은 Gap 유형 → 별도 완료 가능한 납품/인수 항목** 순서로 분해했다. 기존 점수18/28·21/40·22/52는 분자 계산에 넣지 않았다.

11개 목표에서 독립적으로 완료를 판정할 수 있는 53개 항목이 나왔다. 항목마다 현재 코드/증거, 남은 일, 출구, 담당, 선행 항목, 예비 작업시간을 기계 원장에 명시했다. 코드/문서 존재만으로 실환경 수용을 완료 처리하지 않았다. 구현물이 이미 있는 경우에는 새로운 구현이 아니라 연결 또는 검증으로 표시했다.

계산식은 **수용된 중간 단계 배점 합 ÷ 고정5300점**이다. 53개 목표를139개 실행/인수 단계로 구체화했고, 남은 배점은 목표별 작업량 차이를 반영했다. 상위 목표를 다 닫을 때까지 점수를 보류하지 않는다. 단계별 선행·출구·증거를 충족하면 즉시 가산하며, 단계 분할의 배점합과53개 목표 범위는 유지한다. 실제공수/가동확률 지표는 아니다.

전체가 완료돼도 trial 차단 P0/P1이 남아 있으면 해당 항목을 재개방한다. U01~U03 최종 인수가 없으면 100%에 도달할 수 없다. 한 번의 유료 제작, schema 파일, CI YAML, readiness 표식만으로 해당 실사용 출구를 닫지 않는다.

| 목표별 묶음 | 완료/전체 | 남은 항목 ID |
|---|---:|---|
| A 권한에 맞게 로그인하고 업무를 이어간다 | 3/5 | A04, A05 |
| L L2 골격을 설치·수정하고 부서 앱으로 사용한다 | 3/4 | L04 |
| D 실자료를 등록·검증·인증해 업무에 쓴다 | 4/6 | D05, D06 |
| F 요구에서 실제 업무 앱을 만들고 수정한다 | 2/5 | F03, F04, F05 |
| R 앱·산출물을 전달하고 안전하게 운영한다 | 1/5 | R01, R02, R04, R05 |
| M 근거로 계산·판단하고 실행 결과를 확인한다 | 2/6 | M01, M04, M05, M06 |
| P 업무 정본이 PostgreSQL에서 보존·복구된다 | 2/5 | P03, P04, P05 |
| W 서버를 바꿔도 작업·이벤트·파일이 유지된다 | 0/4 | W01, W02, W03, W04 |
| C 자체 관리 UI로 신뢰 가능한 배포를 통제한다 | 1/6 | C02, C03, C04, C05, C06 |
| N NCP에서 무중단 변경과 운영 대응이 가능하다 | 0/4 | N01, N02, N03, N04 |
| U 실제 사용자가 반복 업무를 수행하고 인수한다 | 0/3 | U01, U02, U03 |

**진척과 운영 준비를 혼동하지 않는다:** 18개 완료는 아래의 국소 코드/계약/조사 결과다. 현재 실제 PG·원격 CI·NCP 배포·전체 실사용을 완료했다는 뜻은 아니다. 반대로 이미 구현된 인증 API/선행자료/L2 변경 기능을 다시 미구현으로 보내지도 않는다.

## 3. 이번 대조에서 확인한 중요한 Gap

1. **인증 서버와 인증 화면은 다르다.** `data_preparation_control.py`에 서명/인증/정책 API가 있고 집중 시험도 통과했다. 그러나 frontend/src의 해당 endpoint/OWNER_CERTIFIED 검색에서는 소비 연결이 없었다. D04는 완료, D05는 화면 연결 작업이다.
2. **문맥 격리와 운영 계정 사용성은 다르다.** 현행 세션/문맥 게이트는 존재하지만 viewer/member의 전환 정책이 결정 대상이다. 편의를 위해 manager로 배정한 검증이 일반 사용자 수용이 되지 않는다.
3. **재개 수정과 모든 활성화 차단은 다르다.** 일반 `programs/{id}/status`는 admin 확인 후 set_status를 직접 호출한다. R03이 완료여도 R04의 정책/연결 확인이 필요하다.
4. **프런트 SSE 보호와 서버 이벤트 영속성은 다르다.** `SSEBroadcaster.clients/asyncio.Queue`는 메모리다. A03은 재사용하고 W02에서 프로세스 밖 저장/재생을 구현해야 한다.
5. **접수 영수증과 작업 지속성은 다르다.** `active_tasks: Dict[str, asyncio.Task]`와 create_task만으로 두 worker·재시작·배포 중 단일 실행을 보장하지 않는다. F02 완료와 W01 미완료를 분리했다.
6. **DB adapter와 DB 이관은 다르다.** 첫7테이블/SQL wrapper와20건 계약 시험은 P02 완료다. 실제 PG 경로 P03, 필수 업무 저장소 P04, 실제 자료 이관/복원 P05는 남는다. 기동 DDL 분리는 조사 단계다.
7. **CI 파일과 신뢰 가능한 릴리스는 다르다.** `.github/workflows/artifact-contract.yml`은 존재한다. 파일 색인·24건 시험을 full manifest/SBOM/provenance·원격 Linux 실행으로 과장하지 않는다.
8. **관리툴 시제품과 운영 control plane은 다르다.** ops_control의7상태 SQLite 원장은 미연결이고 반례가 남는다. R1 계약을 바탕으로 관리 PG/API·UI·외부 실행 연결을 구현해야 한다.
9. **온톨로지/Host Runtime도 오래된 ‘없음’ 표시를 믿으면 안 된다.** 현행 runtime/resolver/bridge 코드가 존재한다. M01/R01은 재구현 지시가 아니라 현재 실제 경로의 연결/수용 Gap이다.
10. **설치→데이터→제작→실행을 분리해야 한다.** L2 설치 승인은 데이터 인증이나 앱 실행 권한이 아니다. 참조 팩29L2/기존7앱 존재만으로 현업 폐루프를 완료할 수 없다.

## 4. 기능별 Gap 원장

아래 완료는 항목에 적힌 국소 출구만 인정한 것이다. 전체 사용자 인수는 U01~U03에서 추가 증거로 판정한다. 담당·의존성·추정시간과 구조화된 근거는 JSON 정본에 있으며, 아래 경로는 직접 재검토할 수 있는 근거다.

### A. 권한에 맞게 로그인하고 업무를 이어간다

**A01 직접 진입 대상 서버 확인 — 완료**

- 현재: project/mega/kit_app/draft/release 진입 게이트와 소유 문맥/판본 확인 구현·검증 기록.
- Gap/할 일: 없음. 새 기능이나 게이트를 재구현하지 않음.
- 완료 출구: 대표 대상의 정상 진입 및 없는/비가시 대상 거절을 기존 서버 권한으로 판단.
- 담당/선행: Codex / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `frontend/src/factory/studioDraftEntry.ts`, `docs/handoff/CLAUDE_REVIEW_REQUEST_CLOSEOUT_2026-09-19.md`.

**A02 URL·히스토리·미저장 입력 보호 — 완료**

- 현재: 뒤로/앞으로·초안 닫기·URL 보존·동일 문서 이동 보호 실측 기록.
- Gap/할 일: 없음. 문서 이탈/배포 중 입력 보존의 최종 수용은 U02에서 확인.
- 완료 출구: 동일 문서 이동에서 URL/화면 일치, 취소 시 입력 보존, 늦은 응답 오염 차단.
- 담당/선행: Codex / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `frontend/src/factory/studioLeaveGuard.ts`, `docs/handoff/CLAUDE_REVIEW_REQUEST_B6_CONTEXT_2026-09-18.md`, `docs/handoff/CLAUDE_REVIEW_REQUEST_CLOSEOUT_2026-09-19.md`.

**A03 문맥 전환·현재 연결 소비 차단 — 완료**

- 현재: 회사 전환 재확인·합성 SSE 생산자→store→DOM 및 옛 연결 무시 시험/실측.
- Gap/할 일: 없음. 서버 이벤트 영속화·재생은 W02와 다른 일.
- 완료 출구: 문맥 전환 시 이전 내용 차단, 재권한 확인, 옛 연결 이벤트 미반영 및 현재 이벤트 양성 대조.
- 담당/선행: Codex / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/CLAUDE_REVIEW_REQUEST_B6_DECISIONS_2026-09-19.md`, `docs/handoff/CLAUDE_REVIEW_REQUEST_CLOSEOUT_2026-09-19.md`.

**A04 실제 계정·역할·문맥 전환 운영 설정 — 부분 구현**

- 현재: 세션 인증은 있으나 AuthStore의 자격증명 미등록 분기는 공통 초기 비밀번호를 비교한다(core/auth.py:224). viewer/member 문맥 전환 정책도 미결이다.
- Gap/할 일: 공통 초기 자격증명 fallback의 trial 사용 차단, 안전한 최초 등록/회수 검증, 운영 인증·역할 정책 확정. 기존 자격증명/권한 임의 변경 금지.
- 완료 출구: 미등록/공통 초기 자격증명으로 trial 로그인 불가. 실제 계정/역할 관리와 자기 허용 범위 전환을 검증한다. 임의 관리자 승격 금지.
- 담당/선행: Codex + 사용자/인증 담당 / 없음; 남은 엔지니어 예산 4~12시간.
- 근거: `core/auth.py`, `docs/handoff/CLAUDE_REVIEW_REQUEST_B6_DECISIONS_2026-09-19.md`.

**A05 실자료 접근·역할 회수 통합 보안 수용 — 검증 필요**

- 현재: 여러 개별 가시성/404 검증은 있으나 trial 실계정/실자료 통합 매트릭스 증거 없음.
- Gap/할 일: 목록/단건/첨부/생성앱/작업/SSE에 같은 접근 경계를 실환경으로 증명.
- 완료 출구: 허용·금지 역할의 양성/음성 쌍, 세션/권한 회수·교차 문맥 유출0, 비밀/실자료 로그 노출0.
- 담당/선행: Codex / A04, D06, R05, P04; 남은 엔지니어 예산 4~10시간.
- 근거: `api/routes/program_control.py`, `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-20_B.md`.


### L. L2 골격을 설치·수정하고 부서 앱으로 사용한다

**L01 고정 판본 표준 L2 팩 저장 계약 — 완료**

- 현재: 8L1/29L2 참조 팩·불변 원문/지문·version 충돌 검사 구현. NO_DATA/DOMAIN_REVIEW_REQUIRED 표기 유지.
- Gap/할 일: 없음. 현업 적합성 승인과 앱·데이터 완성은 L04.
- 완료 출구: 팩 원문/ID/판본 고정, 변조/중복 버전 거절, REFERENCE_ONLY와 실사용 적격을 구분.
- 담당/선행: Claude / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `core/data_preparation/process_pack_artifacts.py`, `docs/handoff/L2_STUDIO_B2_SETUP_2026-09-13.md`.

**L02 L1/L2 변경·제안·독립 승인 — 완료**

- 현재: 추가/사용상태/상위 이동/바로가기 변경과 제안·타인 승인·재조회 코드 및 집중 검사.
- Gap/할 일: 없음. 새 기획 없이 현재 기능을 trial에서 수용.
- 완료 출구: 업무 ID와 기존 참조를 보존해 변경·차이 검토·독립 승인·조회 반영.
- 담당/선행: Codex / L01; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/L2_STUDIO_B4_INSTALLATION_FLOW_2026-09-13.md`, `frontend/src/lib/processInstallationApi.ts`, `output/process-installation-check-a4a6bf37-2924-4837-9110-97cdb3a903ab/report.json`.

**L03 키트 설치·실패 재개·문맥 결속 — 완료**

- 현재: plan/start/resume/cancel, 적격자 인수, revision CAS·설치 상태와 DP/ECM 계약 구현·검사.
- Gap/할 일: 없음. 실제 설치 시 업무 준비도 승격은 L04.
- 완료 출구: 같은 설치 재시도에서 중복 인스턴스/늦은 응답 오염 방지 및 명시적 승인.
- 담당/선행: Claude / L01; 남은 엔지니어 예산 0~0시간.
- 근거: `core/enterprise_context/process_installation.py`, `docs/handoff/L2_STUDIO_B2_SETUP_2026-09-13.md`, `output/process-installation-check-a4a6bf37-2924-4837-9110-97cdb3a903ab/report.json`.

**L04 선정 부서 L2·7앱 실제 자료 연결 — 부분 구현**

- 현재: 기존7앱과 후보 업무 골격 존재. 코드 출구는 데이터 준비/현업 인증 완료를 명시적으로 제외.
- Gap/할 일: 도메인 담당 검토, 기존 앱별 인증 데이터/권한/업무 계약 결속 및 실행.
- 완료 출구: 선정 원료구매 폐루프에 쓰는 기존7앱의 입력·책임·L2·자료·권한 연결이 실제 사용자 기준으로 성립.
- 담당/선행: Claude + 현업 담당 / L02, L03, D06, R05; 남은 엔지니어 예산 8~20시간.
- 근거: `docs/handoff/L2_STUDIO_B2_SETUP_2026-09-13.md`, `docs/handoff/K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md`.


### D. 실자료를 등록·검증·인증해 업무에 쓴다

**D01 파일 등록·원천 결속·RAW 판 보존 — 완료**

- 현재: 기존 업로드/결속/스냅샷 API와 RAW 보존·재조회·대사 기록.
- Gap/할 일: 없음. 실제 자료 승인/인증과는 분리.
- 완료 출구: 입력 원문·판본·체크섬·문맥·출처를 보존하고 잘못된 결속을 거절.
- 담당/선행: Claude / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `api/routes/data_preparation_control.py`, `docs/handoff/K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md`.

**D02 선행 데이터 참조 정렬 — 완료**

- 현재: 선행5종/1397행·6RAW판 및 기존자료 참조 대사 기록. 합성/미인증 성격 보존.
- Gap/할 일: 없음. 동일 자료 재적재 금지.
- 완료 출구: 조직/달력/창고/조건/가격 자료를 원문 보존으로 정렬하고 참조 오류 확인.
- 담당/선행: Claude / D01; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/FOUNDATION_ALIGNMENT_CHECKPOINT_2026-09-11.md`.

**D03 사용 보류의 인증·소비 강제 — 완료**

- 현재: usage_policy가 인증/준비도/객체/앱/계산을 차단하고 경쟁 쓰기 회귀 기록.
- Gap/할 일: 없음. 보류를 정식 해제한 증거는 D06.
- 완료 출구: 미검증·잘못된 문맥·가격/기간 보류를 실제 인증·계산 경계에서 차단.
- 담당/선행: Claude / D01; 남은 엔지니어 예산 0~0시간.
- 근거: `core/data_preparation/usage_policy.py`, `docs/handoff/DATA_USAGE_HOLD_ENFORCEMENT_2026-09-12.md`.

**D04 회사 실적 서명·인증 서버 계약 — 완료**

- 현재: OWNER_CERTIFIED API·정책·서명과 최종 인증 원자성 구현, 133건 합동 회귀 기록.
- Gap/할 일: 없음. UI가 없는 것과 서버가 없는 것을 혼동하지 않음.
- 완료 출구: 적격 주체/기간/용도 서명과 보류 검사, 마지막 서명/인증의 원자성 보장.
- 담당/선행: Claude / D03; 남은 엔지니어 예산 0~0시간.
- 근거: `api/routes/data_preparation_control.py`, `docs/handoff/PROPOSAL_ACTUAL_CERTIFICATION_2026-09-11.md`, `output/usage-holds-qkq_3qxq/tests.xml`.

**D05 인증 정책·서명·반려 사용자 화면 — 추가 구현**

- 현재: 인증 API는 존재하나 frontend/src에서 certifications/OWNER_CERTIFIED/정책 API 소비 연결을 발견하지 못함.
- Gap/할 일: 화면 경로를 확인하고 미연결 소비자를 기존 API에 연결. 새 인증 정책 엔진을 만들지 않음.
- 완료 출구: Data Owner와 관리자가 기간/용도/보류/서명 현황을 보고 권한에 맞게 확인·서명·재검토 가능.
- 담당/선행: Codex / D04; 남은 엔지니어 예산 6~14시간.
- 근거: `frontend/src/components/DataPrepPanel.tsx`, `frontend/src/lib/dataPrepApi.ts`, `api/routes/data_preparation_control.py`.

**D06 승인 실자료 인증→앱·계산 소비 — 검증 필요**

- 현재: RAW·합성 정렬 증거는 있으나 실제 소유권·가격/시점 근거·회사 인증 및 대표 앱/계산 수용 미완료.
- Gap/할 일: 사용자가 승인한 자료/오너/기간으로 인증, 보류 해제 근거와 downstream 대사.
- 완료 출구: 실제 자료가 적격 서명을 거쳐 해당 회사/기간 앱·계산에 사용되고 미승인 자료는 차단.
- 담당/선행: Claude + 실제 Data Owner / D02, D05, A04; 남은 엔지니어 예산 4~12시간.
- 근거: `docs/handoff/FOUNDATION_ALIGNMENT_CHECKPOINT_2026-09-11.md`, `docs/handoff/DATA_USAGE_HOLD_ENFORCEMENT_2026-09-12.md`.


### F. 요구에서 실제 업무 앱을 만들고 수정한다

**F01 요구 초안 저장·지정 판본 재개 — 완료**

- 현재: BuildStartDialog·draft metadata/open·서버 소유 문맥·판본별 내용 복원 기록.
- Gap/할 일: 없음. 실제 제작 생산자 검증은 F04.
- 완료 출구: 요구 입력을 저장하고 정확한 초안/판본/문맥으로 다시 연다. 저장을 제작/승인으로 오인하지 않음.
- 담당/선행: Codex / A01; 남은 엔지니어 예산 0~0시간.
- 근거: `frontend/src/factory/studioDraftEntry.ts`, `docs/handoff/CLAUDE_REVIEW_REQUEST_CLOSEOUT_2026-09-19.md`.

**F02 제작 명령 영수증·미확정 보호 — 완료**

- 현재: 저장 초안·요청 신원·결과 영수증·UNKNOWN 보호·같은 사건 복구 계약 구현/검사 기록.
- Gap/할 일: 없음. 모든 실제 장기작업 제어의 정상완주는 F03/W01.
- 완료 출구: ACCEPTED/REJECTED/UNKNOWN 구분, 중복/늦은 응답 방지, 서버 접수와 실행 완료 분리.
- 담당/선행: Codex / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/L2_STUDIO_B5_GENERAL_HOTL_CONSUMPTION_2026-09-14.md`, `frontend/src/factory/studioInputMemory.ts`.

**F03 수정 요구·중단·재개의 사용자 동작 — 부분 구현**

- 현재: 수정 요청은 TODO와 execution_started=False를 기록한다(studio_revision_requests.py:216). PROCESSING/UNKNOWN 잔류가 새 실행을 차단한다.
- Gap/할 일: 접수된 TODO의 실제 실행/결과 연결, 잔류 미확정 복구와 새·구 제어 경로 대조. 안전한 차단을 실행/복구 완료로 인정하지 않는다.
- 완료 출구: 같은 산출물 기준으로 수정 요청이 실제 실행에 반영되고 pause/stop/recovery가 사실과 일치.
- 담당/선행: Codex / F02, W01; 남은 엔지니어 예산 4~10시간.
- 근거: `frontend/src/factory/RevisionRequestEditor.tsx`, `frontend/src/factory/sprintActions.ts`, `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-19.md`.

**F04 실제 제작→Host 계약→산출물 — 부분 구현**

- 현재: 생성기·Host 계약/물질화 경로 존재, 최근 주요 수용은 합성 fixture 중심.
- Gap/할 일: 승인된 실제 LLM 제작으로 계약·컴파일·물질화·미리보기·실행을 관통; 미연결만 수정.
- 완료 출구: 실제 사용자 요구로 생성한 앱이 Host 계약과 데이터 경계를 상속하고 결과물을 만들며 수정 후 새판 생성.
- 담당/선행: Claude / F01, D06, R01; 남은 엔지니어 예산 8~20시간.
- 근거: `core/host_runtime_provider.py`, `docs/handoff/I4_HOST_RUNTIME_HANDOFF_2026-08-15.md`, `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-20.md`.

**F05 LLM 호출·재시도·비용 한도 운영 수용 — 검증 필요**

- 현재: 모델/비용 계측 기반은 존재. 실제 trial 제작 동시 제한·실행 전 상한 집행 확인 미완료.
- Gap/할 일: 실행 모델/호출·토큰·재시도·시간·동시작업 상한과 비밀 관리 확인.
- 완료 출구: 승인 예산 초과 작업은 접수/재시도 제한, 비용/실패가 보이며 운영 App/DB를 예산 때문에 삭제하지 않음.
- 담당/선행: Claude + 비용 승인자 / F04; 남은 엔지니어 예산 4~10시간.
- 근거: `docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md`.

### R. 앱·산출물을 전달하고 안전하게 운영한다

**R01 생성 앱 Host 보안·브리지 현행 수용 — 부분 구현**

- 현재: Host wire/provider/bridge 존재. 실제 제공은 Native·Snapshot, 쓰기는 Native만. Connector·Derived는 지원 대기로 거절된다(host_runtime_provider.py:49).
- Gap/할 일: 대상7앱의 provider 요구와 필수 연결·토큰/권한 상속을 검증/보완한다. 미지원 provider를 전체 지원이나 Native fallback으로 위장하지 않는다.
- 완료 출구: 생성 앱이 별도 인증/직접 DB 없이 Host로만 접근하고 미선언 능력·다른 조직·잘못된 origin을 거절.
- 담당/선행: Claude / A04; 남은 엔지니어 예산 4~10시간.
- 근거: `frontend/src/lib/hostRuntimeBridge.ts`, `core/host_runtime_wire.py`, `docs/handoff/I4_HOST_RUNTIME_HANDOFF_2026-08-15.md`.

**R02 검토 버전·미리보기·내려받기 전달 — 부분 구현**

- 현재: 버전 저장 목록·실클릭 export200 및 ZIP 응답 기록. 디스크 저장은 미검증, 일부 자료는 합성.
- Gap/할 일: 실제 제작 산출물의 앱/보고서/문서 미리보기와 사용자 다운로드 파일 열기 확인.
- 완료 출구: 정확한 판본의 결과를 저장/미리보기/내려받고 실패는 명시. 브라우저 제한을 디스크 성공으로 보고하지 않음.
- 담당/선행: Codex / F04; 남은 엔지니어 예산 2~6시간.
- 근거: `docs/handoff/CLAUDE_REVIEW_REQUEST_DOWNLOAD_2026-09-19.md`, `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-19.md`.

**R03 릴리스 단건 은닉·재개 원상 복원 — 완료**

- 현재: 비가시/없는 릴리스 동일404, 재개 원상상태·fingerprint·반복호출·원자성 보완과 관련 시험.
- Gap/할 일: 없음. 일반 status 승격은 R04에서 별도 차단.
- 완료 출구: 단건 조회가 목록 가시성을 우회하지 않고 재개가 candidate를 active로 임의 승격하거나 지문을 잃지 않음.
- 담당/선행: Claude / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-20_B.md`, `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-21.md`, `core/program_lifecycle.py`, `output/usage-holds-qkq_3qxq/tests.xml`.

**R04 모든 릴리스 활성화 진입의 준비도 일치 — 부분 구현**

- 현재: 일반 POST programs/{id}/status가 admin 검사 후 set_status를 직접 호출; 재개 수정만으로 전체 승격 봉쇄 아님.
- Gap/할 일: 정식 승격 근거와 일반 status API 허용 범위를 확정하고 우회·회귀 검사.
- 완료 출구: 모든 candidate→active 경로에 승인·데이터/Host 준비도·동일 판본 근거가 일치; 예외는 명시 정책/감사.
- 담당/선행: Claude + 정책 결정자 / R03; 남은 엔지니어 예산 3~8시간.
- 근거: `api/routes/program_control.py`, `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-21.md`.

**R05 생성 앱 전달·수락·실데이터 실행 — 검증 필요**

- 현재: 전달/공유/승격 구성요소 존재. 실제 역할·인증자료·생성 결과가 연결된 반복 사용 증거 부족.
- Gap/할 일: 다른 실제 사용자 수락→실행→입력/조회→감사 검증.
- 완료 출구: 앱 수락이 데이터 권한 부여로 바뀌지 않고 사용자별 허용 자료만 실행. 부적격 릴리스 실행 차단.
- 담당/선행: Claude / F04, R01, R04, D06; 남은 엔지니어 예산 4~12시간.
- 근거: `frontend/src/components/KitAppPanel.tsx`, `core/host_runtime_provider.py`.


### M. 근거로 계산·판단하고 실행 결과를 확인한다

**M01 업무 의미 경로·근거 탐색 현행 연결 — 부분 구현**

- 현재: ontology_runtime/resolvers/path와 API/UI 존재. 오래된 헌장의 런타임 부재 주장은 현행과 다름.
- Gap/할 일: 대표 원료 지연→공장/생산/현금흐름 질문의 승인 관계·권한·시점 연결을 검증.
- 완료 출구: 중간 비가시 노드를 건너뛰지 않고 객체·관계·출처·기준시점·품질을 설명하며 수치는 계산엔진에 위임.
- 담당/선행: Codex / D06; 남은 엔지니어 예산 4~12시간.
- 근거: `core/ontology_runtime.py`, `core/ontology_resolvers.py`, `api/routes/ontology_control.py`.

**M02 공개 관측→동인→결정론적 계산 — 완료**

- 현재: WorldBank240행 수집·승격·동인·시나리오·SOURCE_CERTIFIED 대표 경로 기록.
- Gap/할 일: 없음. 회사 실적/다원천 운영 수용과 분리.
- 완료 출구: 대표 공개 원천의 출처/판본을 보존하고 승인 동인·계산으로 연결.
- 담당/선행: Claude / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/test_plan/F8_REAL_WALK.md`, `docs/handoff/SESSION_2026-09-11_WORLDBANK_LIVE_RUN.md`.

**M03 의사결정 근거 결속·작성 API — 완료**

- 현재: baseline/scenario/engine_version 결속과 실제 UI 요청의 API 재대입·임시원장 검증 기록.
- Gap/할 일: 없음. 실제 실행/효과는 M05.
- 완료 출구: 안건이 정확한 계산/원천 근거와 묶여 저장되고 근거 누락·불일치가 거절.
- 담당/선행: Codex / M02; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/DECISION_CREATION_CONTRACT_REPAIR_2026-09-11.json`, `api/routes/decision_control.py`.

**M04 회사 실적 대사·Replay/Backtest — 검증 필요**

- 현재: 계산·시나리오 기반 존재; 같은 회사/기간의 인증 실적 백테스트 수용 미완료.
- Gap/할 일: 실적 입력과 기준선·산식·단위·통화·기간을 고정하고 오차/기여를 대사.
- 완료 출구: 선정 업무의 물량/원가/현금흐름 결과가 재현되고 실제 대비 차이와 근거가 설명됨.
- 담당/선행: Claude + 현업 / D06, M01, M02; 남은 엔지니어 예산 6~16시간.
- 근거: `core/planning_engine.py`, `core/enterprise_financial_model.py`.

**M05 결정→실행과제→증빙·효과 폐루프 — 부분 구현**

- 현재: 의사결정/실행/효과 이력과 합성 어댑터 경로 존재. 실제 trial 반복 업무는 미완료.
- Gap/할 일: 실제 책임자의 승인·과제/실행·증빙·예상 대비 효과를 같은 업무ID로 결속.
- 완료 출구: 내부 실제 과제 실행 및 결과를 추적; 외부 전송을 사용하는 경우 승인된 실제 어댑터로 검증. mock은 대체 불가.
- 담당/선행: Codex + 현업 / M03, M04, R05; 남은 엔지니어 예산 6~16시간.
- 근거: `docs/test_plan/F8_REAL_WALK.md`, `core/decision_case.py`.

**M06 Task ID 없는 근거 질문·안전한 행동 제안 — 부분 구현**

- 현재: Jarvis/ontology/decision 경로는 존재하나 선정 업무 실자료에서 전 구간 수용 미확인.
- Gap/할 일: 권한 기반 질의·설명·영향 미리보기·사람 승인까지 연결 검사.
- 완료 출구: 프로젝트ID 없이도 허용 근거로 답하고 데이터 누락/충돌을 알리며 승인 없이 실행하지 않음.
- 담당/선행: Codex / M01, M05; 남은 엔지니어 예산 4~12시간.
- 근거: `docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md`, `api/routes/ontology_control.py`.


### P. 업무 정본이 PostgreSQL에서 보존·복구된다

**P01 현행 DB·파일 이관 대상 지도 — 완료**

- 현재: 20파일/95표/16startup ALTER와 업무14·캐시5·빈파일1, JSON정본 분리 실측.
- Gap/할 일: 없음. 전부 PG 이관으로 가정하지 않음.
- 완료 출구: 저장소 종류·DB밖 정본·첫 경로·기동 DDL·소유/수명 차이 명시.
- 담당/선행: Claude / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/CLAUDE_DB0_DELTA_AND_FIRST_SLICE_2026-09-20.md`.

**P02 DB 방언 어댑터·첫 schema 계약 — 완료**

- 현재: core/db wrapper·auth/ECM 주입점·7테이블 설치SQL·SQLite/대역20검사 기록.
- Gap/할 일: 없음. 실제 PG 실행은 P03.
- 완료 출구: 잘못된 backend/DSN 누락 거절, SQL 변환 및 기본 SQLite 호환을 검증한 adapter/설치 명세.
- 담당/선행: Claude / P01; 남은 엔지니어 예산 0~0시간.
- 근거: `core/db/__init__.py`, `core/db/schema/001_auth_and_context.sql`, `docs/handoff/CLAUDE_DB1_FIRST_ADAPTER_2026-09-21.md`, `output/usage-holds-qkq_3qxq/tests.xml`.

**P03 실제 PG 인증·문맥·티켓 경로 — 부분 구현**

- 현재: PG 설치SQL은 있으나 실제 PG 실행0확인. 기본 Docker endpoint도 연결 실패.
- Gap/할 일: 격리 PG/driver 확보, runtime DDL 분리, empty→NULL 이관과 동시 소비 검증.
- 완료 출구: 실제 PG 로그인/문맥/권한/티켓1회소비·대사·재시작이 정상, 기동 DDL0.
- 담당/선행: Claude / P02; 남은 엔지니어 예산 4~8시간.
- 근거: `docs/handoff/CLAUDE_DB1_FIRST_ADAPTER_2026-09-21.md`.

**P04 나머지 필수 업무 저장소 PG 전환 — 추가 구현**

- 현재: 기동 DDL 분리는 조사 단계. data_preparation/decision/planning/advisor 등 SQLite 핵심 경로 잔존.
- Gap/할 일: 첫 slice 이외 필수 저장소별 migration·SQL·락/트리거·runtime DDL 제거 및 시험.
- 완료 출구: 트라이얼 필수 업무 경로가 실제 PG로 실행; startup seed/DDL0, 업무 제약·권한·N/N-1 호환 유지.
- 담당/선행: Claude / P03; 남은 엔지니어 예산 24~60시간.
- 근거: `docs/handoff/CLAUDE_DB0_BOOT_DDL_SEPARATION_2026-09-21.md`, `core/data_preparation/store.py`.

**P05 승인 자료 ETL·DB/파일 대사·복원 — 추가 구현**

- 현재: 조사/기존RAW사본 도구는 존재하나 승인 자료의 PG ETL·정본파일 교차대사·복원 증거 없음.
- Gap/할 일: 비밀 제외한 이관/대사/복원 도구와 사본 리허설, 승인 후 actual cutover.
- 완료 출구: row/key/hash/권한/파일참조 대사와 복원 후 업무 재실행 성공, 원본 불변/복구 가능.
- 담당/선행: Claude / P04, W03; 남은 엔지니어 예산 8~20시간.
- 근거: `docs/handoff/CLAUDE_DB0_DELTA_AND_FIRST_SLICE_2026-09-20.md`.


### W. 서버를 바꿔도 작업·이벤트·파일이 유지된다

**W01 영속 작업큐·단일 실행 소유권 — 추가 구현**

- 현재: active_tasks는 Dict[str, asyncio.Task], create_task 프로세스 실행. DB영수증은 작업영속성 자체가 아님.
- Gap/할 일: durable job/lease/fencing·재시작/두worker 인수·중복 side effect 방지 구현.
- 완료 출구: 배포/worker 재시작 중 접수 작업 유실/중복 실행0, 현재 소유권과 실행 상태 복구.
- 담당/선행: Claude / P03; 남은 엔지니어 예산 12~28시간.
- 근거: `core/async_orchestrator.py`, `core/studio_execution_guard.py`.

**W02 프로세스 밖 이벤트·SSE 재생 — 추가 구현**

- 현재: SSEBroadcaster.clients와 asyncio.Queue가 메모리; 프런트 옛 연결 가드와는 별개.
- Gap/할 일: 공유 이벤트 저장/브로커·cursor·재생/중복/권한 재검사 연결.
- 완료 출구: 다른 App노드/재시작 후 이벤트 누락·중복 표시·권한 밖 반영0.
- 담당/선행: Claude / P03, A03; 남은 엔지니어 예산 8~20시간.
- 근거: `core/broadcaster.py`.

**W03 프로젝트·릴리스 파일 공유·원자 저장 — 추가 구현**

- 현재: projects/latest_state.json·library/release.json와 DB상태 분리. 표식 디렉터리는 실제 공유증거 아님.
- Gap/할 일: 공유 저장 위치·노드 접근/권한·원자쓰기·DB파일 일관성/복구 연결.
- 완료 출구: 두 노드가 같은 판본을 안전하게 읽고 동시쓰기/장애 시 부분/옛파일·다른문맥 노출 방지.
- 담당/선행: Claude / P01; 남은 엔지니어 예산 8~20시간.
- 근거: `docs/handoff/CLAUDE_DB0_DELTA_AND_FIRST_SLICE_2026-09-20.md`, `docs/handoff/CLAUDE_DEP_R1R4_REMEDIATION_2026-09-21.md`.

**W04 구/신 버전 API·assets·worker 호환/드레인 — 추가 구현**

- 현재: 계획은 있으나 구UI chunk·장기작업·API/schema 동시호환/드레인 실측 미확인.
- Gap/할 일: 호환창·이전asset보존·worker payload·장기작업 인계/완료 정책 구현.
- 완료 출구: 열린 입력/세션/작업을 강제로 잃지 않고 N/N-1 병행 및 SSE 재연결.
- 담당/선행: Codex + Claude / P04, W01, W02, W03; 남은 엔지니어 예산 6~16시간.
- 근거: `docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md`.

### C. 자체 관리 UI로 신뢰 가능한 배포를 통제한다

**C01 배포계약·보안/실행 경계 확정 — 완료**

- 현재: R1 명세/API 및 지정6건 독립 재검토/구조 검증 완료.
- Gap/할 일: 없음. 계약 완료를 backend/실배포로 합산하지 않음.
- 완료 출구: 요청자·승인·claim·lease·원자완료·복귀새계획·독립PG·관측 정책의 구현 기준 확정.
- 담당/선행: Codex / 없음; 남은 엔지니어 예산 0~0시간.
- 근거: `docs/handoff/CODEX_HYBRID_DEPLOYMENT_R1_2026-09-21.md`.

**C02 불변 artifact·출처·Linux CI — 부분 구현**

- 현재: 파일 색인/허용목록 도구·24시험과 artifact-contract.yml 초안. 원격 CI 미실행.
- Gap/할 일: fullmanifest/digest/runtime lock/SBOM/provenance·Linux실행·변조/비밀 배제 증거.
- 완료 출구: 같은 소스에서 신뢰 가능한 불변 산출물 생성, 원격 CI 확인, 검증불가 artifact 배포 차단.
- 담당/선행: Codex / C01; 남은 엔지니어 예산 4~8시간.
- 근거: `.github/workflows/artifact-contract.yml`, `scripts/release_artifact.py`.

**C03 독립 관리 PG·원자 계획 API — 추가 구현**

- 현재: ops_control은 7상태 SQLite 미연결 prototype; 원자성 반례 존재.
- Gap/할 일: R1 상태모델/독립PG migration·auth·lease·멱등·감사 구현. 구 원장 재완성 금지.
- 완료 출구: 경쟁/실패 때 단일 current pointer/상태/감사가 원자적, 업무DB fallback/기동 DDL0.
- 담당/선행: Codex / C01; 남은 엔지니어 예산 8~16시간.
- 근거: `ops_control/deploy_ledger.py`, `ops_control/counterexamples_deploy_ledger.py`.

**C04 자체 배포관리 UI 3메뉴 — 추가 구현**

- 현재: 상세 설계만 있고 ops_control에 UI/API 구현을 찾지 못함.
- Gap/할 일: 준비/환경·배포 상세·이력 화면 및 상태/권한/오류 연결.
- 완료 출구: 실제 backend로 안전한 요청/관측/이력 탐색, UNKNOWN/stale를 성공으로 표시하지 않음.
- 담당/선행: Codex / C03; 남은 엔지니어 예산 8~12시간.
- 근거: `docs/design/DEPLOYMENT_CONTROL_PLANE_V1_2026-09-21.md`.

**C05 GitHub 신원·승인·claim 통합 — 추가 구현**

- 현재: user dispatch/OIDC/회수 확인·환경 보호는 명세. 실제 설정/권한·실행 증거 없음.
- Gap/할 일: GitHub App/환경/보호·user run 신원/claim·결과 대조 연결; 지원 플랜 확인.
- 완료 출구: 실제 사용자·run·plan 신원 일치, 자기승인/회수/중복/미보호 실행 차단.
- 담당/선행: Codex + 저장소 관리자 / C02, C03; 남은 엔지니어 예산 8~16시간.
- 근거: `docs/design/contracts/deployment-control-v1.openapi.json`.

**C06 제한 agent·실제 readiness 관측 — 추가 구현**

- 현재: readiness 선언/표식만으로 READY 거절하게 보완됐지만 실제 관측 생산자 미구현.
- Gap/할 일: mTLS agent·명령 allowlist·실제 DB/mount/slot/version freshness 관측 구현.
- 완료 출구: 승인된 plan/현재lease만 실행, 오래되거나 없는 증거는 차단, 업무 App와 독립 동작.
- 담당/선행: Codex + Claude 관측 / C03, P03, W03; 남은 엔지니어 예산 8~16시간.
- 근거: `docs/handoff/CLAUDE_DEP_R1R4_REMEDIATION_2026-09-21.md`.


### N. NCP에서 무중단 변경과 운영 대응이 가능하다

**N01 NCP 격리 인프라·TLS·HA·비밀 — 검증 필요**

- 현재: 구성/예산 권고만 확인. 현재 클라우드 실구축 상태를 조회하지 않음.
- Gap/할 일: 승인견적·망/방화벽·TLS·DB HA·비밀·staging/trial 자료 분리 구성/검증.
- 완료 출구: 실자료와 관리면이 필요한 주체에게만 열리고 HA/백업/운영 권한 최소화.
- 담당/선행: 인프라 담당 + Codex / C01; 남은 엔지니어 예산 8~16시간.
- 근거: `docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md`.

**N02 실제 무중단 전환·새 계획 rollback — 검증 필요**

- 현재: 블루그린·LB/드레인·실환경 복귀 증거 없음. API 기능 지원도 확인 필요.
- Gap/할 일: 이중slot·트래픽/관측·새복귀계획을 실제 업무부하에서 리허설.
- 완료 출구: 배포기인5xx/세션유실/쓰기유실/명령중복0, 실패 시 호환코드로 복귀; DB 자동되감기 금지.
- 담당/선행: Codex + 인프라 / N01, W04, C05, C06, P05; 남은 엔지니어 예산 8~16시간.
- 근거: `docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md`.

**N03 운영 관측·감사·백업·비용 알림 — 검증 필요**

- 현재: 각 계측/감사 기반 및 예산정책 존재; trial 수집/보관/알림·복구/비밀정제 전구간 미검증.
- Gap/할 일: 메트릭/로그/감사·권한보관·복구목표·비용 알림과 운영절차 연결.
- 완료 출구: 오류/비용/자료접근/배포 이력 관측, 승인RPO/RTO로 복원, 자료 유출 없는 진단 가능.
- 담당/선행: Codex + 운영자 / N01, P05, F05; 남은 엔지니어 예산 6~12시간.
- 근거: `docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md`.

**N04 운영 이슈→로컬 수정→PR→승인 배포 — 검증 필요**

- 현재: Codex 로컬 소스 수정 방식 결정. 새 모델 API/운영서버 직접수정은 제외.
- Gap/할 일: 운영버전/정제로그 기반 실제 작은 수정 한 건으로 PR/CI/staging/trial 추적.
- 완료 출구: 운영비밀/실자료를 자동 모델에 보내지 않고 승인된 소스 변경만 검증·배포, 요청부터 결과까지 추적.
- 담당/선행: Codex / C02, C05, N02; 남은 엔지니어 예산 2~6시간.
- 근거: `docs/design/DEPLOYMENT_CONTROL_PLANE_V1_2026-09-21.md`.


### U. 실제 사용자가 반복 업무를 수행하고 인수한다

**U01 실제 원료구매 업무 반복 폐루프 인수 — 검증 필요**

- 현재: 컴포넌트/합성/일부API 실측이 분산돼 있음. 실제 역할·자료로 전체반복완주 기록 부족.
- Gap/할 일: 원료구매→물류/재고→생산/재무 영향→결정/실행/효과를 실제 담당자로 반복.
- 완료 출구: 합의된 대상업무/기간/책임자의 반복 수용, 데이터 근거와 실행 결과 대사, 해당경로 P0/P1차단결함0.
- 담당/선행: 실제 현업 + Codex / A05, L04, R02, M05, M06, N02; 남은 엔지니어 예산 8~16시간.
- 근거: `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md`.

**U02 사용자30·동시10·배포중 부하 수용 — 검증 필요**

- 현재: 부하목표만 있음. 동시10 혼합업무/제작제한/배포장애 시험 기록 미확인.
- Gap/할 일: 실제 workload 비율·자료량·SLO 확정, 정상10/스트레스15 및 배포중 수용.
- 완료 출구: 일반API p95≤1.5초·정상망SSE재연결≤5초 목표와 유실/중복0 검증; 목표 미달이면 차단/승인 재조정.
- 담당/선행: Codex + Claude / U01, F05, N02; 남은 엔지니어 예산 6~12시간.
- 근거: `docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md`.

**U03 운영 인수·복구 훈련·최종 개시 판정 — 검증 필요**

- 현재: 격리 검증 절차는 있으나 trial 운영 책임/온보딩·복구 훈련·실자료보관 최종인수 없음.
- Gap/할 일: 운영자 계정/권한·백업/복구/장애·자료보관·비상절차와 사용자 안내 수용.
- 완료 출구: 운영자가 직접 복구·장애 대응·배포 이력을 확인, 모든 필수 Gap 닫힘 및 개시 승인. 100%여도 미해결P0/P1이면 개시금지.
- 담당/선행: 운영자 + 사용자 / U02, N03, N04; 남은 엔지니어 예산 4~8시간.
- 근거: `docs/handoff/ISOLATED_VERIFICATION_ENV_2026-09-16.md`.



## 5. 실행 순서와 담당 — 조사 반복 대신 두 구현 경로

**즉시 Codex:** C02 불변 산출물/manifest·CI. 기존 파일 선별기를 재사용한다. 첫30분에 수정 파일/재사용/출구를 고정하고 다음60~90분에 생성·검증 첫 실행물을 만든다. C02의4~8시간은 외부 승인 대기 제외 추정이며, 로컬 생성만 끝났다면 C02 전체를 완료 처리하지 않는다. 이후 C03→C04와 C05/C06 통합을 순차 진행한다.

**즉시 Claude:** P03 실제 PG 첫 경로. P02를 재작성하지 않는다. 첫30분에는 사용할 격리 PG/driver/설치 역할을 특정한다. 없으면 환경 확보 담당·정확한 필요 조치를 적고 runtime DDL 분리/ETL/시험 준비는 계속한다. 환경 확보 후4~8시간에 로그인/문맥/티켓 원자성의 첫 실측을 목표로 한다. 이후 P04, W01/W02/W03의 명확한 소유 파일 단위로 진행한다.

**다음 제품 연결 묶음:** D05 인증 화면→D06 실제 인증자료→R01/F04 실제 생성/Host→L04/R05 실제 앱 사용. 인증 API·L2 저장소·선행5종 정렬은 반복 구현하지 않는다. A04/R04의 정책 결정 준비는 기존 권한을 바꾸지 않는 재현/선택안으로 병행한다. 이 경로를 배포 UI 완성 뒤로 무기한 미루지 않는다.

**최종 합류:** P04/W01~W04와 C02~C06·N01이 준비되면 P05/N02에서 실제 이관/무중단을 검증한다. 제품 경로와 합쳐 U01 반복 업무→U02 혼합부하/배포중 수용→U03 운영인수로 닫는다. 모든53항목이 이 목표에 연결되고, 존재하는 UI 한 곳씩 무제한 탐색하는 작업은 넣지 않는다.

기계 원장에 기록한 남은 순수 엔지니어 시간은 **223~526시간의 예비 범위**다. 이는 확정 일정/현재 팀 생산성 실측이 아니라, 부분·신규·검증35개를 빠짐없이 드러내기 위한 작업 예산이다. DB 나머지 저장소, 영속작업, 실제 자료 수용이 큰 불확실성이다. 승인/자료/실사용자 대기를 포함하지 않으며 2명으로 단순 나눠 개시일을 약속하지 않는다. P03·C02 첫 실측 후 해당 항목과 핵심 경로의 예상 시간을 갱신한다. 기존 관리툴6~11인일 추정을 전체 오픈 일정으로 쓰지 않는다.

현재 Claude의 다음 지시 수신·착수는 미확인이다. 위는 통합 작업 배치이며, 직접 전달됐다고 주장하지 않는다. 같은 파일을 동시에 수정하지 않고 공통 API/기동부는 지정 통합 담당자가 마지막에 연결한다.

## 6. 사용자/운영 권한이 필요한 결정

- A04: 실계정 인증 방식과 일반 역할의 자기 범위 전환 정책. 현재 권한을 임의 확대하지 않는다.
- R04: 일반 활성화 API와 정식 승격 근거의 관계. admin이라는 이유로 준비도 생략을 승인하지 않는다.
- P03/N01/C05: 격리 PG·클라우드 자원·GitHub 보호/계정 설정. 코드 준비와 실제 설정 변경을 구분한다.
- D06/F04: 실자료 소유자/회사/기간/인증자 및 실제 LLM 실행 상한. 운영 데이터를 자동으로 모델에 보내지 않는다.
- N03/U03: 실제 자료 보관·삭제·RPO/RTO·운영 책임자와 개시 승인.

이 결정들이 미정이라고 무관한 안전한 구현을 멈추지는 않는다. 반대로 승인이 없으면 해당 실제 실행 수용을 완료로 표시하지 않는다.

## 7. 검증·한계·진척 운영

이번 직접 재검증: 인증API28 + DB adapter20 + 재개13 + 릴리스 조회8 + 산출물24 = **서버93 passed / exit0**. `output/usage-holds-qkq_3qxq/`의 tests.xml/isolation.json에 근거가 있다. 보호자산 불변·차단 쓰기0·SQLite51경로 격리·전역 conftest 미로드. 로그의 열 추가는 격리 DB에서 발생했으며 운영 이관이 아니다.

L2 설치/구조 편집은 **프런트105 PASS / exit0**, `output/process-installation-check-a4a6bf37-2924-4837-9110-97cdb3a903ab/report.json`. 합성API/STATIC1 포함이며 실제 브라우저 수용이 아니다. 다른 완료 항목은 명시한 현행 코드와 기존 한정 증거를 대조했으며 이번에 모두 재실행한 것은 아니다.

독립 검토: 별도 Codex Popper가 읽기 전용 정적 검토로 인증 초기 fallback·일반 역할 전환·일반 활성화·Host provider 제한·수정 TODO/미확정 실행 경계5건을 제시했다. 메인이 코드 재대조 후 A04/R01/F03의 잔여와 출구를 보강했다. R04는 잔여로 유지한다. 전체 제품/보안 PASS나 실환경 수용이 아니다. 진척 계산기는 ID·상태·근거 경로·합계·의존성 순환·보고값만 검사한다. 초기 계산기 실행에서 L03 근거 폴더 오기를 발견해 실제 enterprise_context 경로로 정정했다.

향후 보고는 **전체 수용점수/5300와 % → 이번에 수용된 단계ID/사용자 변화 → 다음 단계ID/예상시간 → 막힌 단계/담당** 순서다. 목표 종결n/53은 보조값이다. 회귀 시 해당 단계 점수만 회수하고 이유를 공개한다. 단계 수용 즉시 계산/보고하며 큰 목표 종료까지 가산을 미루지 않는다. 계획 변경만으로 새 구현 점수는 주지 않는다.

이번 변경은 진척 정본/상세 Gap/계산기/재개 링크·보드·결정 기록만이다. 제품·운영 DB·클라우드·실자료·원격 설정·커밋/푸시는 변경하지 않았다.
