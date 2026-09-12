# L2 업무 문맥·단일 SW 제작 작업공간 상세 설계 및 실행 계획

> 작성자: Codex · 2026-09-12 · revision 2.1
> 상태: **독립 이중검토 지적 반영·제한적 재확인 PASS(설계 한정). 원격 확인 대기 / 구현 미착수.**
> 브랜치: `codex/l2-unified-studio-20260912` · 분기점 `574c26fd8`
> 선행 코드 보존: `41af3c06c`. 푸시는 자동 보안 검토가 목적지 확인을 요구해 미실행.
> 전체 21/40=52.5%, 로컬 18/28≈64% 유지. 문서·시험 명세를 제품 완료로 가산하지 않는다.

## 1. 사용자 요구와 결정 범위

사용자 요구: 수정 가능한 표준 L2를 업무키트에 제공하고, 두 SW 생성기 화면을
직관적인 하나의 사용자 여정으로 정리한다. 구현 전에 상세 설계·실행 계획과
객관적 이중검토를 수행한다. 기존 작업은 먼저 커밋·푸시하고 새 브랜치에서 진행한다.

- 전면 중단하지 않는다. 기존 데이터 안전성·회귀를 먼저 닫고, L2와 무관한 대사·근거 준비는 유지한다.
- 기존 평면 업무·이중 화면을 전제로 하는 신규 UI/키트 확장은 보류한다.
- 새 생성기 세 번째 버전을 만들지 않는다. `AdaptiveProductionStudio`와 기존 상태·실행 API를 재사용한다.
- 첫 수직 범위는 BK-01 원료구매 4개 정본 L2 후보(공급사 선정은 선택), BK-02/03/07의 관련 업무 바로가기다.
- L2는 업무 분류·문맥이며 순차 실행 엔진이 아니다. 제작 단계는 별도의 축이다.
- 29개 업무의 개별 앱·ERP 입력 화면, 신규 디자인 시스템, 전역 내비게이션 전면 재작성,
  자동 발주·입고확정·지급·실적 인증·운영 배포는 이번 구현 범위가 아니다.

### 1.1 상위 문서와 착수 정렬

Product Bible → 독자 제품 전략 → 최종 완성 로드맵 → PROGRESS → 본 설계 순서다.
권고 착수 4·7(G2 업무/의미)와 10(G3 Factory/AppShell), 선행 5·6(G2-D 데이터 안전성)에 해당한다.
첫 구매 폐루프의 회사·업무·데이터·생성 앱 문맥을 잇기 위해 직접 필요하며,
단일 생성기와 L2 표준 제공은 사용자의 명시적 요청이다.

기존 `docs/design_business_kit_l2_process_setup_2026-09-12.md`는 데이터 모델·설치·변경·업데이트
계약의 정본이다. 본 문서는 이를 대체하지 않고 **실행 순서와 통합 UX·전환 계약**을 구체화한다.
별도 통합 시에는 기존 병렬개발 통합 계획의 clean worktree·권한/계약/제품 연결 Gate를 지킨다.

## 2. 확인된 As-Is와 영향

| 접점 | 확인된 사실 | 처리 |
|---|---|---|
| `App.tsx` | 기존 3패널 위 `showStudio`로 새 화면을 띄움; 보고서 경로와 일반 프로젝트 진입이 다름 | 단일 route resolver와 프로젝트 작업공간으로 통합 |
| `AdaptiveProductionStudio.tsx` | HubDialog 컨테이너, 종전 통제실 복귀 버튼, 유사한 확대 토글 2개 | 페이지 컨테이너와 내용 분리, 확대 한 기능, 구 화면 선택 제거 |
| `RunControls.tsx` | 시작·재개·복구·재분할·저장·수정·ZIP을 함께 제공; 비활성 이유는 이미 있음 | 상태별 대표 행동, 추가 조작 분리; 기존 기능 보존 |
| `sprintActions.ts` | 시작 payload·여러 실행 명령을 공유 | 호출·직렬화 재사용, 화면마다 API 판단 복제 금지 |
| `factoryViewModel.ts` | 현재 실행 단계와 사용자가 보는 단계를 분리하고 상태 정규화 | 이 구분 유지; 대표 행동도 한 projection에서 산출 |
| `BuildStartDialog.tsx` | 키트/일반 경로; 일반은 유형·절차·지식·기준정보를 초기에 요청 | 업무와 요구 먼저, 나머지 기본값/추가 설정 |
| `ProductShell.tsx` | 회사 문맥과 7개 주 메뉴 | 승인된 shell·토큰·브랜드 유지, 제작 세부 페이지에도 일관 적용 |
| ECM `process_profile` | 현재 v1 평면 구조, v2 설계만 존재 | 새 문맥/불변판/CAS/구 writer guard가 선행 |
| `kit_app_contract.draft` | 인증판에서 스키마 확보 | 데이터 없는 요구 초안은 별도 Blueprint, 이 API 우회 금지 |
| `project_data_context` | 현재 회귀 7건: FakeStore.transaction 부재 | 구현 첫 묶음에서 fail-closed 소비 계약 확정·수정 |

소스 기반 진단이다. 실제 렌더링·현업 테스트를 수행했다고 주장하지 않는다.
기존 Studio의 시작 기능이 없다는 과거 주석은 현재 `RunControls` 구현과 다르므로 현행 코드를 기준으로 한다.

## 3. 정보 구조: 세 축을 섞지 않는다

1. **기업 문맥**: 회사/조직 + REAL/VIRTUAL/COMPETITOR. 화면 상단에 항상 표시한다.
2. **업무 문맥**: 원료구매 > 구매계획. 업무 탐색·도구 연결의 위치다.
3. **제작 진행**: 요구사항 정리 > 설계 > 제작 > 검토 > 사용 준비. 생성 과정의 상태다.

공통 shell 안에서 L1 선택 후 해당 L2만 보여준다. 홈에 29개 L2나 제작 세부 단계 전부를 펼치지 않는다.
프로젝트에 들어오면 같은 회사/업무 위치를 유지하면서 중앙 영역이 제작 작업공간으로 바뀐다.
현재 실행 중인 단계와 과거 결과를 열어 보는 상태를 시각·문구로 구별한다.
다른 L2를 탐색하는 것만으로 실행 중 프로젝트의 소속·데이터 계약을 바꾸지 않는다.

### 3.1 역할별 기본 화면

| 사용자 | 첫 화면의 중심 | 추가 설정/별도 흐름 |
|---|---|---|
| 현업 요청자 | 업무 목적, 사용 가능한 도구, 앱 요청, 내 검토 대기 | 기술 실행 구조·코드·고급 생성 설정 |
| 업무 구성 편집자 | 현업 화면 + 업무 구성 수정/변경 제안 | 구조 변경 diff·적격 승인 요청 |
| 데이터/앱 승인자 | 내 검토 대상, 근거·차이·영향, 승인/반려 | 정책·원장 세부 |
| 제작 운영자 | 동일 프로젝트 + 실행 진단·복구 | 로그·작업 재분할·내보내기 |

별도 제품/권한 DB를 만들지 않는다. 표시가 달라도 동일 사용자·서버 권한 판정을 사용한다.
역할을 클라이언트에서 선택했다고 승인권이 생기지 않는다.

## 4. 대표 사용자 여정

### J1. 표준 업무에서 새 앱 요청

L1/L2 선택 → `이 업무에 필요한 앱 만들기` → 자연어 요구/예시 선택 →
시스템이 이해한 목적·사용자·입력·결과·데이터 범위를 확인 → 설계/계약 준비 →
제작 → 결과 검토 → 검토용 버전 저장 → 자격 확인·승인 후 기존 전달/운영 흐름.

업무키트에서 문맥·지식·절차를 추천하되 선택 근거와 바꿀 수 있는 위치를 제공한다.
자연어 요청 한 번으로 실행·데이터 승인·외부 쓰기를 묶어 수행하지 않는다.

### J2. L2 또는 데이터 없이 시작

`새 앱 요청` → 자유 요구 → **요구사항 초안 저장**.
업무가 없으면 `업무 연결 미정`, 데이터가 없으면 `데이터 준비 필요`로 표시한다.
전체 업무지도를 완성하거나 인증판을 만들기 전에도 요구사항을 정리할 수 있다.
단, 실행 계약 발급·운영 앱 릴리스 전에는 적격 업무 매핑·데이터/정책을 확인한다.
Mock 결과를 원하면 명시적 SYNTHETIC 실험으로 분리하고 실제 결과처럼 표시하지 않는다.

### J3. 기존 앱 또는 보고서 작업 계속하기

최근 작업/앱 제작 목록/기존 링크 → 같은 단일 Studio → 저장된 프로젝트 상태 복원.
앱·문서·보고서·시뮬레이터는 같은 진입/통제 틀을 사용하되 중앙 산출물 뷰는 유형에 맞게 유지한다.
보고서를 앱 미리보기로 강제 변환하거나 메가 프로젝트 보드룸을 없애지 않는다.
기존 프로젝트에 L2가 없다는 이유로 조회·검토·복구를 막거나 전체를 자동 이관하지 않는다.

### J4. 부족 데이터와 승인 대기 해소

차단 이유 → 현재 부족한 계약/데이터 성격/기준시점 → 적격 담당 역할 → 다음 행동.
담당자가 실제로 결속되지 않았다면 `담당 미지정`이며 이름을 추정하지 않는다.
연락/요청은 기존 내부 요청 기능과 별도 확인을 사용한다. 화면 조회만으로 메시지를 보내지 않는다.
데이터 준비 화면에서 돌아오면 초안·선택 업무·프로젝트를 복원하고 준비도는 서버에서 재조회한다.

### J5. 회사 업무 구성 변경

`업무 구성 수정` → 이름/설명/순서/추가/미사용/바로가기 변경 → 영향 미리보기 →
변경 제안 또는 적격 승인 → 같은 업무 ID/기존 앱을 보존한 새 승인판.
초기판에서도 이 기본 변경·이력은 제공한다. 분리/통합·복잡한 상속 편집은 후속이다.
미지원 행동은 클릭 가능한 성공 버튼으로 보이지 않는다.

## 5. 화면 구성과 문구 규칙

### 5.1 시작 화면

- 기본 입력은 업무(선택되어 있으면 상속)와 `어떤 일을 쉽게 만들고 싶으세요?`다.
- 예시는 구매계획 등 선택 업무에 맞추되 예시 선택이 실제 데이터/권한 결속을 만들지 않는다.
- 업무 이름은 제안 후 변경 가능. 통합 프로젝트·절차·지식팩·기준정보는 `추가 설정`에 둔다.
- 기준정보는 허용 목록 검색/선택으로 제공한다. 내부 domain code를 콤마로 입력하도록 요구하지 않는다.
- 키트/일반은 내부 구성 경로로 해석하며, 현업이 두 생성기 중 하나를 선택하게 하지 않는다.
- 추천값이 없는 경우 없음/추천 불가를 표시한다. 임의의 기본 계약·담당자·기간을 만들지 않는다.

### 5.2 프로젝트 작업공간

상단: 작업 이름, 회사/업무, 저장/연결 상태. 그 아래 간결한 제작 단계.
중앙: 지금 필요한 입력·설계 확인·산출물. 보조 영역: 질문/결정 및 필요한 근거.
작업 목록·실행 로그·상세 근거는 접어서 열 수 있게 하되 승인 판단에 필수인 차이·위험은 기본 노출한다.
`보고서 크게/넓게`는 `결과물 전체 화면` 한 기능으로 정리한다.
주요 여정은 페이지, 짧은 확인만 대화상자다. Studio 위 Studio나 설정 대화상자를 중첩하지 않는다.
뒤로가기/닫기는 화면 이동이지 실행 중단이 아니다. 중단은 별도 버튼과 결과 확인을 가진다.

### 5.3 용어

| 현재 표현 | 기본 사용자 표현 | 의미 보존 |
|---|---|---|
| 기획 가동 | 요구사항 정리 시작 | 실제 호출이 기획 시작임을 설명 |
| WBS | 작업 목록 | 전문가 설명에 WBS 병기 가능 |
| WBS 재분할 | 작업 계획 다시 나누기 | 기존 계획 변경 영향·확인 필수 |
| Release 저장 | 검토용 버전 저장 | 배포/운영 시작과 다름 |
| 산출물 ZIP | 코드·문서 내려받기 | 현재 내보내기 권한 유지 |
| usage hold | 데이터 사용 보류 | 사유 코드와 근거는 상세에 보존 |

`실제 데이터`, `합성·시연 데이터`, `인증 용도`, `승인 필요`, `조직 범위`는 쉬운 표현으로 항상 구별한다.
포괄적인 거버넌스를 일괄 '설정'으로 치환하지 않고 해당 작업의 목적을 제목으로 사용한다.

## 6. 상태별 대표 행동과 실패 계약

아래는 UI projection이며 서버 상태 머신을 새로 만드는 것이 아니다.
`factoryViewModel`의 현재 상태 + 서버 권한/차단 결과에서 한 번만 도출한다.
과거 단계 선택, 브라우저 시간, 작업 완료 개수만으로 실행 권한을 추론하지 않는다.

| 상황 | 대표 행동/표시 | 계속 접근 가능한 행동 |
|---|---|---|
| 로딩/문맥 확인 중 | 확인 중, 쓰기 비활성 | 목록 복귀 |
| 요구 없음 | 요구사항 정리 시작 | 초안 저장/추가 설정 |
| 명확화 질문 대기 | 질문에 답하고 계속 | 초안 보존 |
| 설계/계약 검토 대기 | 설계 확인 또는 적격 검토 요청 | 차이·근거·반려 |
| 실행 중 | 제작 중, 현재 작업과 다음 사람 확인 시점 | 일시정지·중단 |
| 일시정지/한도 대기 | 서버가 허용한 재개 | 상태 조회·중단 |
| 복구 가능한 실패 | 오류 확인 후 재시도 | 진단·기존 제한 횟수·인계 |
| 복구 한도 소진 | 실패 패키지 확인 | 범위 조정 제안·보류·전문가 인계 |
| 데이터 보류/권한/계약 차단 | 사유 확인 및 해결 경로 | 초안/기존 결과 조회(허용 범위) |
| 결과 검토 대기 | 결과 확인하기 | 수정 요청·시험 결과 |
| 검토용 버전 저장 가능 | 검토용 버전 저장 | 수정·내보내기 |
| 운영 자격·승인 완료 | 사용 준비/기존 전달 흐름으로 이동 | 권한·버전 확인 |
| 오프라인/상태 불명 | 연결 다시 확인, 성공으로 표시 금지 | 저장된 초안 보존 |

동시에 여러 조건이면 비가시/권한 회수 > 상태 조회 실패 > 명시적 승인/차단 > 실행 상태 순으로
안전한 행동을 선택한다. 중단 요청이 실패하면 '중단됨'이 아니라 결과 확인 필요로 남긴다.
401 재인증, 403 보이는 대상의 행동 불가, 404 비가시/없음, 409 변경 충돌,
422 입력/계약 불충족, 503 판단 불가를 구별한다. 비가시 대상의 이름·개수·승인자 정보는 누설하지 않는다.

### 6.1 결정 종류별 연결 계약 — 검토 B-1

UI의 '확인/승인'은 아래 구분자의 view adapter다. 같은 버튼/API로 합치지 않는다.
`ContractReviewGate`/`contractReviewApi`의 계약 동작을 Studio 내부 결정 영역으로 이식한다.

| 결정 종류 | 조회/쓰기 API(기존) | 결속 키·행동 |
|---|---|---|
| 일반 HOTL | factory `/{project}/hotl/check`, `/{project}/hotl/resume` | project/task + 현재 결정 차수; feedback/명확화 답변. 계약 승인에는 사용 금지 |
| Host 계약 승인 | factory `/{project}/contract-review/pending`, `/contract-review/decision` | project/task/request_event_id/compiled_fingerprint; APPROVE 또는 사유 있는 REJECT |
| 지원 능력 선택 | factory `/{project}/contract-decisions/pending`, `/contract-decisions/resolve` | 해당 계약의 pending decision ID와 허용 선택. 임의 능력 승인으로 해석 금지 |
| 키트 앱 계약 | data-preparation `/instances/{instance}/apps/{app}/contract`, `/contract/approve` | instance/app/revision/semantic fingerprint; 적격 타인 승인·근거. 일반 HOTL과 무관 |

표의 prefix는 `/api/v1/factory`, `/api/v1/data-preparation`이다.
키트의 명시적 반려 API는 현재 확인되지 않았다. `/contract/reject`를 **신규 계약 제안**으로
B3에 포함한다(revision/expected_digest/rationale, 현재 초안만 반려, 승인판 불변, 감사·적격자 검사).
구현·검증 전에는 반려 성공 버튼을 노출하지 않고 수정 요청/미승인 상태를 그대로 표현한다.

Host 응답의 `state_applied=false`는 결정 원장 기록 성공과 실행 반영 실패가 공존하는 상태다.
event_id/request_event_id/계약 지문을 보존하고 재승인 버튼을 금지한다.
복구는 기존 승인 사건을 조회·검증한 뒤 같은 task의 상태/계약 stamp만 멱등 재적용한다.
이를 위한 `POST /api/v1/factory/{project}/contract-review/reconcile`는 **신규 제안**이며,
기존 사건 참조·현재 프로젝트 쓰기/재개 권한·현재 계약 지문을 검사하고 새 승인 사건을 만들지 않는다.
복구 확인 후 별도의 작업 재가동을 안내한다. pending=없음만으로 제작이 재개됐다고 표시하지 않는다.
타 결정/새 지문은 기존 사건으로 복구할 수 없고 409 후 새 검토가 필요하다.

### 6.2 실행 명령과 결과 확인 — 검토 B-2

| 명령 | 대상/기존 API | 모드·보존·완료 판정 |
|---|---|---|
| 기획 시작 | 새 planning task, `/{project}/sprint/start` | PLANNING; 요구·업무 문맥 보존, 이미 있는 WBS 실행과 구분 |
| 개별 작업 시작/일반 중단 후 재가동 | 기존 task, `/sprint/start` | 서버의 task 분류에 맞는 EXECUTION/REVISION; WBS·기존 결과·문맥·피드백 보존 |
| 실패 작업 재시도 | 기존 실패 task, `/sprint/start` | 서버 허용 시 재시도 이유/피드백과 기존 결과 보존; 새 프로젝트 생성 금지 |
| 쿼터 재개 | 해당 task, `/sprint/resume-quota` | 저장된 모드/체크포인트 사용; 일반 일시정지 재개로 재사용 금지 |
| 일시정지 | 활성 task, `/sprint/pause` | 요청 접수와 실제 정지 확인 구분; 임의 active task 삭제 금지 |
| 중단 | 활성 task, `/sprint/stop` | 결과 확인 전 running/HOTL 참조 보존; 페이지 이동과 별도 |
| 복구 | project와 error_log, `/heal` | 기존 HOTL 반환 또는 새 REVISION task 생성. 아래 별도 결과 계약 사용 |

`sprintActions`를 명령 조립의 정본으로 확장하고 기존 ControlPanel의 개별 작업 payload를
복사하지 않는다. 서버가 보호하는 schema/승인/문맥 필드를 클라이언트 state spread로 덮지 않는다.
`useFactoryStore.stopSprint`의 finally에서 무조건 상태를 비우는 동작은 보존 대상이 아니라
B5의 명시적 결함 수정 대상이다. start/pause도 HTTP 실패를 성공으로 표시하지 않게 한다.
반환 계약은 `REJECTED`(명시 거절), `ACCEPTED`(접수), `UNKNOWN`(응답 유실),
`CONFIRMED`(서버 최신 상태/이벤트에서 결과 확인)를 구별한다.
UNKNOWN에서는 같은 쓰기를 자동 재전송하지 않고 상태를 재조회한다. 서버 멱등성이 확인되지 않은
명령을 임의 재시도하지 않는다. 한도/정책 차단은 재개 버튼 대신 실제 해결 경로를 제공한다.

**복구의 실제 분기(검토 B-2 재확인 보완):** 현행 `/heal`은 원래 실패 task를 그대로
재실행하는 API가 아니다. 기존 HOTL 대기가 있으면 `hotl_task_id`를 반환하고 새 실행을 하지 않는다.
그 외에는 새 REVISION 작업을 만들어 `status=healing_started, task_id`를 반환한다.

- HEAL_STARTED: 반환된 **새 task_id**를 관찰한다. 원래 실패 task·결과·근거는 보존하고
  새 복구 작업과의 연결을 보여준다. 단순200이 아니라 응답 분기를 해석한다.
- HOTL_PENDING: 반환된 **기존 hotl_task_id**의 결정/대기 화면을 열고 '확인이 먼저 필요'로 표시한다.
  복구 실행 시작이나 새 task 생성으로 집계하지 않는다. 결정 종류는 §6.1로 다시 조회한다.
- LOCAL_BLOCKED: 프로젝트 미선택은 선택 안내, 연결 끊김은 연결/상태 확인,
  현재 클라이언트의3회 제한 도달은 자동 복구 중지·실패 패키지/수동 검토 안내.
  요청을 보내지 않은 경우이며 복구 성공·서버 접수로 표시하지 않는다.
- REJECTED/UNKNOWN: 거절 사유 또는 결과 확인 필요를 표시한다. 응답 유실 시 새 REVISION을
  자동으로 추가하지 않고 WBS/최신 상태를 조회해 실제 생성 여부와 관찰 대상을 확인한다.

현행3회·연결 차단은 `useFactoryStore.triggerSelfHealing`의 **로컬 선행 검사**다.
서버의 동등한 횟수 제한·멱등성이 구현됐다고 단정하지 않는다. B5에서 반환 계약을 위 union으로
보완하고, 서버의 승인된 복구 예산/재시도 정책 확인과 request ID 멱등 결속은 **신규 보강 제안**으로
분리한다. 서버 보장이 검증되기 전 자동 재전송·연속 복구는 활성화하지 않는다.
로컬 카운터를 서버 정책/권한의 근거로 삼거나 새 브라우저에서 횟수를 초기화해 서버 제한을 우회하지 않는다.

## 7. URL·문맥·초안 수명

### 7.1 단일 진입 계약

현재 App은 project가 있으면 `space=build`로 정규화한다. revision1의 `space=factory` 제안을
철회하고 기존 `space=build` 아래 **구분자 있는 target union**으로 상세 상태를 확장한다.
예: `?space=build&target=project&project=<id>&configuration=<id>&process=<id>`.
새 라우터 라이브러리 없이 기존 navigation 함수/상태를 한 resolver로 모은다.

| target | 식별자/읽기 | 상위 복귀·제약 |
|---|---|---|
| new | 저장 전 요청. GET만으로 프로젝트/초안 생성 없음 | 원래 L2 또는 앱 제작 목록 |
| draft | draft_kind=consultation/blueprint, 해당 ID·revision; advisor consultations/blueprints GET | 원래 상담/초안 목록 또는 L2; blueprint와 project ID 혼용 금지 |
| project | project_id; factory state/latest 및 WBS/산출물 조회 | 앱 제작 목록 또는 검증된 부모 mega |
| kit_app | instance_id/app_id, 선택 release_id; data-preparation 인스턴스 앱 목록 + 기존 허용 릴리스/runtime reader | 원래 L2/키트 앱 목록; 가짜 project 생성 금지 |
| release | release_id, 서버가 확인한 app/project 귀속; 기존 factory/library/item 등 해당 릴리스 reader | 해당 앱/프로젝트/보고서 목록 |
| mega | mega_project_id 및 선택 child_project_id; 기존 mega/project 조회 | 메가 목록↔부모 보드↔자식 Studio |

kit_app의 release 조회는 instance/app/release 귀속과 권한을 먼저 검사하는 reader adapter를 둔다.
기존 library reader가 해당 릴리스를 지원하지 않으면 정식 조회 계약을 추가하며 임의 project ID로 우회하지 않는다.
report/simulation은 project의 deliverable 종류이지 다른 project ID 체계가 아니다.
구 project 링크는 target=project로, 구 보고서/키트/알림 링크는 실제 자산 종류로만 변환한다.
여러 종류의 상충하는 ID는 INVALID_TARGET로 거절하고 임의 우선순위로 열지 않는다.
return target은 허용된 내부 target union만 사용한다. 임의 URL redirect를 허용하지 않으며
회사/권한이 바뀌거나 부모가 비가시면 안전한 해당 목록으로 복귀한다.
데이터 준비 왕복 시 origin target·초안 revision·선택 업무를 유지하고 돌아온 뒤 서버에서 재검증한다.
상단 메뉴/뒤로/앞으로/새로고침도 같은 resolver를 거친다. target별 view adapter는 같은 Studio
내용 영역을 사용하며 다른 생성기나 숨겨진 자동 프로젝트를 추가하지 않는다.
URL의 ID는 위치 힌트일 뿐 권한·회사 소속의 증거가 아니다. 서버 문맥 검증 전 이전 화면을 재사용하지 않는다.

프로젝트 자체의 서버 소속과 URL/현재 회사가 다르면 데이터를 먼저 노출하지 않고 전환 확인 또는
비가시 오류를 표시한다. 프로젝트를 다른 회사로 재결속하지 않는다.
브라우저 새로고침/뒤로가기/앞으로가기는 같은 ID와 조회 상태를 복원하며 쓰기를 재실행하지 않는다.

### 7.2 저장과 취소

요구사항 초안은 기존 `advisor_store`/`advisor_blueprint`의 재사용 가능 계약을 확장한다.
공식 실행 계약은 `kit_app_contract`의 별도 상태다. 두 저장소를 한 개의 '저장 완료'로 뭉개지 않는다.
저장에 실패하면 편집 중 값을 유지하고 '저장 실패'를 표시한다. 초안 revision/CAS로 중복 탭의 덮어쓰기를 막는다.
회사/모드/사용자 전환 전 미저장 변경을 확인한다. 캐시 키는 사용자·tenant·root·mode·scope·project·profile를 포함한다.
문맥 전환 시 이전 요청을 취소/세대 토큰으로 무효화하고 SSE 티켓을 새 문맥으로 연결한다.
늦게 도착한 A회사 응답을 B회사 화면에 반영하지 않는다. 민감한 요구를 전역 localStorage에 저장하지 않는다.

### 7.3 입력별 저장·복원·폐기 — 검토 B-4

| 입력 | 서버 초안 키(공통 사용자/문맥 키에 추가) | 복원/소비 규칙 |
|---|---|---|
| 요구사항 | consultation/blueprint ID + draft revision | 동일 초안만 복원; 프로젝트 승격 후에도 원본 보존 |
| 명확화 답변 | project/task + 질문 요청 ID/차수 + 질문집 digest | 질문집 동일 시 복원; 새 차수에 자동 답변 금지 |
| 승인/반려 의견 | decision_kind + 실제 대상 + request_event_id 또는 계약 revision/digest | 해당 결정에만 복원; 승인 기록 성공 시 소비 표시, 새 결정에 복사 금지 |
| 수정 요청 | project/task + 기준 artifact/release digest + feedback draft ID | 기준 결과가 바뀌면 재확인; 제출 성공 후 요청 ID에 결속 |

서버가 질문/결정 차수 식별자를 제공하지 않는 경로는 B3에서 명시적으로 추가한다.
입력 내용이 같다는 이유로 같은 결정으로 취급하지 않는다. 초안 저장 API는 결정/실행 API와 별개이며
저장이 승인/재개/수정 요청 제출을 자동 실행하지 않는다.
명시 저장 또는 허용된 자동 저장의 성공 전에는 '미저장'이다. 문맥/페이지 이동 전 저장·유지·폐기 선택을
제공하고 저장 실패 시 이동하지 않는다. 동일 문맥 내 단순 패널 전환은 입력을 유지한다.
로그아웃/사용자 전환 시 메모리·대기 요청을 지우며 다른 사용자의 서버 초안은 조회할 수 없다.
소비된 초안은 이력 정책에 따라 보존하되 입력 기본값으로 복원하지 않는다.
서버 저장 성공한 초안의 복원과 아직 메모리에만 있는 입력 보호를 별도 시험한다.

## 8. 서버 계약과 데이터 경계

### 8.1 L2 기반 재사용

기존 L2 설계의 ECM v2 불변 승인판/head CAS, `(tenant, context_root, mode, scope)` 경계,
v1 writer 차단, 데이터 없는 지도 승인, 정확한 artifact/bundle digest, 설치 operation/outbox를 그대로 따른다.
새 독립 업무지도 DB, UI에만 있는 L2 정본, 이름 기반 ID, 현재 등록부로 과거 표준 재구성은 금지한다.
팩 설치 APPLIED와 데이터 준비·앱 실행 가능 상태는 별도다. 업무 추가가 데이터 인증이나 자동 앱 생성을 수행하지 않는다.

### 8.2 ProcessContext와 생성 계약

제안 DTO: `schema_version`, `configuration_id`, `profile_id`, `process_ids`,
`process_semantic_fingerprint`, `configuration_fingerprint`, `context_key`,
`data_requirements`, `verified_binding_refs`, `blockers`, `permitted_actions`, `sources`.

- 서버가 승인판과 현재 행위자에서 구성한다. 클라이언트가 보낸 권한·승인자·digest를 신뢰하지 않는다.
- 초안은 draft reference로 분리하고 공식 ProcessContext와 같은 타입/상태로 취급하지 않는다.
- 표시명/순서는 의미 지문에서 제외; 목적·입출력·데이터 요구·정책 변경은 재검토 대상이다.
- 새로운 runtime contract schema를 명시적으로 지원한다. 기존 schema에 임의 필드를 숨기지 않는다.
- 생성 시작/재개와 릴리스 승인에서 고정 문맥과 현재 변경을 검증한다. 실행 시 현재 Host 권한·인증·보류를 재평가한다.
- L2와 앱은 다대다. 연결 변경으로 기존 앱/release ID를 복제하거나 코드 재생성을 자동 실행하지 않는다.
- 원문 업무/지식 설명은 요구사항 데이터다. 그 안의 지시문이 권한이나 도구 실행 지시가 되지 않는다.

### 8.3 API 변경 목록(제안, 아직 미구현)

| 생산자/저장 | 소비자 | 계약 변경 및 검증 |
|---|---|---|
| ECM process-configurations/context API | 홈/L2/Studio | 같은 승인판·문맥·의미 지문, 권한별 필터 |
| 기존 advisor 초안 API | 통합 시작 화면 | optional draft process reference·revision·사유, 데이터 없이 저장 |
| factory project creation/meta/state | Studio·재개 | 서버 검증한 process context 보존, URL/사용자 입력은 후보만 |
| kit_app_contract / app_runtime_contract | 생성·릴리스·Host | schema migration와 의미 지문, v1 앱 호환 경로 명시 |
| 기존 sprint/clarify/HOTL/release API | 공통 actions/view model | 동작·정책은 재사용, 새 상태/오류 필드만 정식 계약화 |
| process changes/approve/install/resume | 업무 구성/키트 설치 | 기존 L2 설계 §13, CAS·멱등·현재 권한 재검사 |

데이터·권한 실패를 UI용 빈 배열로 바꾸지 않는다. 두 UI의 backend 동작을 별도로 구현하지 않는다.
서버 permitted_actions는 안내이고 실제 action endpoint가 최종 권한을 다시 검사한다.

### 8.4 실제 계약 생산자와 버전별 지문 — 검토 A-4

| 경계 | 책임/보존 필드 | 실패 규칙 |
|---|---|---|
| ECM context resolver → advisor | 승인 profile ID·process IDs·문맥·의미 digest를 서버 확인; draft는 별도 타입 | 비가시404, 의미/판본 충돌409, 판정 불가503 |
| advisor → project meta/state | 승인 blueprint revision과 검증한 ProcessContext를 함께 고정 | 문맥 쓰기 실패를 성공으로 삼키지 않음 |
| 일반 `project_contract_aggregator.py` | 개별 초안 합산 시 같은 서버 문맥만 전달 | 문맥 유실·혼합 차단 |
| 일반 `host_contract_compiler.py`/`nodes/contract.py` | 새 계약 구성 시 서버 문맥과 schema 명시 포함 | LLM의 process ID/권한/지문으로 대체 금지 |
| 키트 `kit_app_builder.py`/`kit_app_contract.py` | 정확한 instance/blueprint/artifact와 같은 ProcessContext 결속 | 등록부 최신값으로 조용히 교체 금지 |
| `app_runtime_contract.py` | 버전별 validator·의미 재료·canonical serialization 분기 | 미지원 버전/필수 문맥 누락 차단 |
| release/approval/Host proof | 원문·schema·계약 지문·process 의미 지문 보존 | 저장/승인/실행에서 지문·현재 권한/보류 검증 |

현행 runtime **문서 schema_version="1.0"**의 validator/해시 재료/직렬화는 불변으로 둔다.
기존 1.0 계약·승인·릴리스·Host proof에 새 빈 필드를 넣거나 일괄 재해시하지 않는다.
ProcessContext를 담는 차기 문서 schema는 **"2.0" 제안**으로 별도 등록한다.
이는 ECM payload schema=2, ProjectState 버전, Host wire/runtime_contract_version과 다른 축이다.
문맥 추가만으로 Host wire를 자동 상승시키지 않고 실제 wire 영향 계약을 시험한다.
버전별 validate/semantic_fingerprint/compiler dispatch를 두고 전역 상수만 바꾸지 않는다.
선택은 서버가 기록한 전환 cohort·프로젝트 유래·명시적 이관 상태로 결정한다(§10.2).
2.0 대상의 누락/미지원은 차단하며1.0으로 폴백하지 않는다. 기존1.0은 기존 생산자/검증기로
보존한다. 이관은 기존 계약을 덮지 않는 새 계약·별도 승인이다.
일반/키트 두 경로에서 의미 변경은 새 지문, 표시명 변경만은 같은 의미 지문이어야 한다.
기존1.0 golden 원문·해시·승인·proof 불변과2.0 누락/변조/유실 부정 시험을 함께 요구한다.

### 8.5 초안 revision·승인·프로젝트 승격 — 검토 A-5

기존 advisor_store.save_blueprint의 무조건 upsert와 bootstrap 재요청의 새 ID 발급을
그대로 사용하지 않는다. 다음은 B3의 정식 구현 범위다.

- 저장: draft_id/expected_revision/expected_digest/patch/client_request_id.
  같은 저장소 write transaction의 CAS; 새 초안은 expected_revision=0.
  충돌409·입력 보존, 같은 멱등키/요청은 같은 revision 반환.
- 승인/반려: draft_id/expected_revision/draft_digest/rationale.
  편집·승인 경합은 한쪽만 성공하며 승인 revision은 불변. 이후 편집은 새 revision.
- bootstrap: approved_revision_id/approved_digest/expected_process_semantic_digest/client_request_id와
  현재 문맥 검증. 필요한 문맥 미정은 초안 보존 후409/422이며 임의 실행 계약을 발급하지 않는다.
- advisor DB에 bootstrap_operation(신규 제안)을 먼저 예약하고 project ID를 한 번만 확정한다.
  멱등키는 사용자/tenant/root/mode/scope/blueprint 승인 revision/client request 범위.
  같은 키·다른 body는409, 같은 키·같은 body는 같은 operation/project를 재사용한다.
- 상태: RESERVED → PROVISIONING → CONTEXT_WRITTEN → LEDGER_PENDING → COMPLETED,
  FAILED_RETRYABLE/BLOCKED. FS·advisor DB·원장은 별개이므로 분산 원자성을 주장하지 않는다.
- project 생성, meta/state의 blueprint/process 참조 저장과 read-back digest 확인,
  고정 event ID의 감사 outbox/원장 접수 확인 후에만 COMPLETED.
  `_write_project_meta`의 print 후 예외 삼킴을 새 경로에서 금지하고 실패를 정식 반환한다.
- 부분 project는 SETUP_INCOMPLETE로 실행/릴리스 불가. 현재 권한으로 같은 operation 재개.
  기존 입력/파일/결정 자동 삭제·재생성 금지. 실패 후 새 project를 만들지 않는다.
- 성공 응답 유실 시 재조회/재개도 같은 project·승인 revision·문맥을 반환한다.
  원장 알림은 같은 event ID로 재전송하며 새 승인 사건을 만들지 않는다.

일반 project 생성과 kit build도 실제 결과 ID의 기록·확인 후 성공을 반환한다.
UI는 operation 실패/진행과 Blueprint 저장 성공을 구분한다.

## 9. 구현 전에 해소할 기존 결함: B0

### B0-A. 보류 projection 소비 계약

현재 실측: 보류 회귀 234 통과, 실적 인증 28 통과, project_data_context 1 통과/7 실패.
같은 connection의 두 SELECT만으로 동일 읽기 시점이 보장되지는 않는다(검토 A-1).
B0에 store.py의 get_snapshot/list_snapshots **projection 생산자**를 포함한다.
첫 SELECT 전에 명시적 읽기 transaction을 시작해 snapshot과 source_binding 보류를 같은
SQLite 읽기 snapshot에서 투영한다. 복수 행 목록도 한 읽기 transaction에서 완성한다.
이미 transaction 안이면 호출자 경계를 존중하고 중첩 BEGIN/임의 commit하지 않는다.
일반 transaction wrapper 전체를 바꿔 기존 BEGIN IMMEDIATE 쓰기를 깨뜨리지 않는다.
기준시점은 첫 snapshot 읽기 시점이며 반환 DTO는 영구 사용 승인/잠금이 아니다.
수정 후보는 `load_sealed`/`active_seals`가 저장소가 투영한 `usage_holds`를
`require_no_holds`로 검증하는 것이다. 이는 인증 쓰기 트랜잭션의 `require_usable_conn`을 대체하지 않는다.
단위 FakeStore도 보류 없음 `[]`를 명시한다. 누락/잘못된 타입/알 수 없는 보류는 차단한다.
최신판이 보류되면 옛 판으로 폴백하지 않는 성질과 검사 순서를 유지한다.
공유 저장소 조회에 두 시점의 판정을 섞지 않되, 장시간 실행의 현재 사용 가능성 재평가는
기존 실행 경계에서 다시 수행한다. 이미 읽은 과거 row가 영구 승인 증거가 되지 않는다.
독립 연결이 snapshot SELECT와 정책 SELECT 사이에 개입할 때 일관된 이전 읽기 또는
경쟁 쓰기 차단을 확인한다. 한 행의 상태/보류 혼합, 목록 내 시점 혼합을 금지한다.

보류 오류는 구조화 reason_code/category로 SealedDatasetError → ProjectDataBindingError →
factory API에 연결한다(검토 A-6). 문자열 파싱으로 분류하지 않는다.
가시성 확인을 먼저 하여 타 문맥404, 알려진 업무 보류409/DATA_USAGE_HOLD,
정책 판독 불가503/USAGE_POLICY_UNREADABLE, 계약 입력 불충족422로 구분한다.
비가시 응답에 내부 사유를 노출하지 않으며 차단 시 project/작업폴더를 만들지 않는다.
실제 프로젝트 생성 HTTP 경로의 부정 시험도 B0에 포함한다.

### B0-B. 실적 인증 경쟁 경계 검증

현재 `sign_actual_certification`은 마지막 여부를 잠금 밖에서 계산하고,
동시 서명으로 마지막이 되는 fallback에는 서명 commit 후 별도 인증 transaction이 남아 있다.
기존 28건 통과만으로 이 경로의 원자성을 확정하지 않는다.
둘 이상의 독립 connection이 다른 종류로 동시에 서명하는 상황, 서명 직후 보류/철회/용도·기간 변경을
재현해 단일 snapshot 상태·서명 집합·용도/기간을 같은 write transaction 안에서 판단하도록 설계·검증한다.
서버가 확인한 소유권/승인권과 서명 내용의 일관성도 확인한다. 시험에서 정책을 no-op으로 바꿔 완료로 세지 않는다.
결함이 재현되면 최소 수정과 부정 시험으로 닫은 뒤 다음 배치로 간다.

**대상/권한(검토 A-2):** 인증 GET/POST 모두 `_snapshot_or_404` 또는 동등한
tenant/root/mode/scope 가시성 판정을 먼저 거친다. 일반 표준 관리권만으로
해당 소유부서의 DATA_OWNER/EXECUTIVE 적격성을 대신하지 않는다.
서버 `can_sign(subject, actor, review_kind)`는 실제 소유권 결속과 종류별 직무/위임을 검사한다.
활성 사용자·부서/위임 범위·서명 종류·현재 승인권을 확인하며 관리자 플래그만으로 두 종류를 허용하지 않는다.
회사 승인 직무/위임 매핑이 미정이면 ROLE_MAPPING_REQUIRED로 차단한다. 시험용 역할을 운영에 복사하지 않는다.
제안 기본값은 종류별 다른 서명자다. 동일인 복수 종류 예외는 명시 승인된 회사 정책 판본과
양쪽 적격성 확인이 있어야 허용한다. 본 문서가 실제 직무/예외 승인 자체를 수행하지 않는다.

**불변 서명 대상(검토 A-3):** certification_subject는 snapshot ID/checksum,
tenant/root/mode/scope, use_kind, 명시된 귀속기간, ownership binding ID/digest,
적용 서명 정책 ID/version/digest를 포함한다. 기간 정규화/유효성을 확인하고 누락을 추정하지 않는다.
서버 미리보기의 subject_digest를 expected_subject_digest로 받아 잠금 안에서 다시 확인한다.
첫 서명에 subject revision을 고정하며 이후에는 동일 subject에만 서명한다.
상이한 기간/용도/원천/소유권/정책 요청은 무시하지 않고409 재확인이다.
현재 시험의 상이한 기간을 무시하는 기대를 실패 계약으로 바꾸고 동일 기간 성공을 별도 검증한다.
정책/소유권 변경 시 미완료 인증은 REVIEW_STALE. 명시적 새 subject revision에 새 서명을 받는다.
이전 서명은 감사 이력으로 보존하되 새 subject의 충족 수에 넣지 않는다.
완료 OWNER_CERTIFIED 내용 변경은 기존 원칙대로 새 snapshot에서 진행한다.

**원자성·멱등:** 같은 write transaction에서 fresh snapshot/subject/서명 집합/보류를 읽고,
서명 추가 결과가 완성이면 상태/기간/용도/인증자를 함께 확정한다.
잠금 밖 completes 및 서명 선commit 후 인증 fallback은 제거 대상이다.
키는 subject_id/review_kind/actor/client_request_id; 동일 요청 재시도는 같은 사건/결과를 반환한다.
같은 종류의 상이한 내용 재서명은 overwrite하지 않고409 또는 명시적 새 검토 revision을 요구한다.
완료 뒤 동일 요청 재전송도 기존 결과를 반환하되 현재 조회 권한은 재검사한다.
외부 조직/PDP 저장소까지 한 transaction이라고 주장하지 않는다. 현재 명령 판정 때 기존 PDP를
호출하고 확인한 정책/권한 판본을 기록한다. 같은 DB의 소유 결속/subject는 잠금 안에서 재확인한다.
완성 직전 기존 서명의 현재 적격성/정책을 재평가하고 판정 불가·회수는 차단한다.
원자성은 해당 데이터 준비 DB의 subject/서명/snapshot 상태 범위다. 다른 저장소의 즉시 전역
직렬화·권한 회수까지 보장했다고 표현하지 않는다. 후속 요청/사용은 현재 Host 정책을 따른다.

실제 임시 조직·역할·위임 fixture로 적격 성공, 교차 tenant/root/mode/scope404,
종류 부적격403, 권한 회수 거절, 동일인 금지/명시 예외, 정책·소유권 변경을 검증한다.
순차/동시 상이한 기간·용도, 응답 유실 재시도, 마지막 서명 실패 후 부분 commit 없음도 포함한다.

전체 T3의 starter asset 변형/실행순서 문제는 별도 격리 점검 대상이다.
운영 DB·추적 패키지 자산을 시험이 바꾸면 이후 전역 시험을 멈추고 실행 환경부터 고친다.

## 10. 단일 화면 전환·구버전 호환

기존 Studio 내용 컴포넌트와 HubDialog 컨테이너를 분리해 같은 내용을 페이지에서 사용한다.
새 clone UI·새 상태 저장소·새 sprint payload는 만들지 않는다.
구 3패널과 새 Studio를 한 프로젝트에 동시에 mount해 이벤트/쓰기/복구가 이중 실행되지 않게 한다.

| 전환 단계 | 일반 사용자 진입 | 구 화면 역할 | 통과 조건 |
|---|---|---|---|
| C0 내부 검증 | 기존 유지 | 기준 비교 | 새 page container, 기능 동등성 검사 |
| C1 제한 회사/사용자 | 단일 Studio 하나 | 운영자 제한 fallback | 역할·유형·실패/복귀 시나리오 통과 |
| C2 일반 전환 | 모든 일반 진입 단일 Studio | 기본 메뉴/화면에서 제거 | URL·상태·권한·부하·UX 수용 |
| C3 정리 | 동일 | 참조/호출 없음 확인 후 코드 제거 | 아래 parity 전체와 rollback 검증 |

fallback은 권한을 넓히는 URL 스위치가 아니다. 서버/배포의 제한 cohort 설정과 현재 권한을 따른다.
화면 flag를 되돌려도 v2 writer guard·계약 검증·데이터 보류 검사는 유지한다.
v2를 해석하지 못하는 서버로 DB를 downgrade하지 않는다. 호환 읽기 또는 안전한 차단으로 보존한다.
자동 데이터 롤백/삭제는 하지 않는다. 정상 승인판 복구는 새 복구판으로 수행한다.

### 10.1 반드시 보존할 기능

프로젝트 생성/열기, 요구 명확화, 기획 시작, 설계/계약 결정, HOTL 승인/반려,
실행 관찰, 일시정지/중단/재개, 한도 대기, 실패 복구/횟수 제한,
작업 재분할, 수정 요구, 앱/보고서/문서 미리보기, 근거·시험 결과,
검토용 버전 저장, 코드·문서 내려받기, 기존 공유/승격 진입, 비용/연결 상태.
항목별 기존 호출·새 호출·권한·성공/실패·상태 갱신·증거를 parity 표에 기록한다.
단순 DOM 존재나 import 일치만으로 동등성을 통과시키지 않는다.

### 10.2 유형×행동×기존/신규 호환 — 검토 B-5

서버 이관 등록부의 LEGACY_UNMAPPED(전환 전 기존 프로젝트), PROCESS_BOUND(새 문맥 계약),
DRAFT_UNBOUND(요구 초안)를 구분한다. 클라이언트가 legacy 플래그나 schema를 골라 우회할 수 없다.
기존 무L2 프로젝트는 기존1.0 계약·승인·Host 통제 아래 조회/실행/수정/검토용 저장·릴리스를 계속한다.
화면 전환만으로 이를 차단하거나 자동 L2 매핑하지 않는다. 명시적 L2 이관 시 새2.0 계약과 별도 승인이 필요하며,
이관 후1.0으로 되돌려 검사를 우회할 수 없다. 신규/copy/fork 프로젝트는 서버의 전환 cohort 규칙을
다시 적용하고 기존 프로젝트의 legacy 자격을 상속하지 않는다. cohort 밖 기존 정책도 UI가 임의 변경하지 않는다.
신규 L2 대상의 공식 계약/릴리스에는 업무 문맥을 요구하되 DRAFT_UNBOUND 요구 저장은 계속 가능하다.

| 유형 | 기존1.0/무L2에서 보존할 행동 | 신규/L2 문맥 대상 추가 조건 |
|---|---|---|
| 업무 앱 프로젝트 | 기획·개별 task 실행·중단/재개·수정·앱 preview·저장/기존 승인 release | ProcessContext가 일반 합산기/compiler/release/Host까지 보존 |
| 문서/보고서 | 문서 생성·수정·현재 결과 검토·저장/내보내기 | 실제 문서 artifact/단계로 이동. EXECUTION/BUILD 검색만으로 결과 버튼을 구현하지 않음 |
| 시뮬레이터 | 기존 인자 변경 resimulate, 이전 cycle/결과/근거·입력판 보존 | 새 인자/기준선은 별도 cycle; L2/데이터 의미·승인/보류 재검증. 기존 결과 덮기 금지 |
| 메가 프로젝트 | 기획·start_all·자식 상태·부모/자식 왕복 | 자식별 문맥/권한을 검증; 부모 이름/업무만으로 자식 실행권 부여 금지 |
| 키트 앱/릴리스 | 계약 초안/승인·build·기존 승격/실행·이전 release 조회 | instance/app/release ID 유지, 같은2.0 계약 규칙; 존재하지 않는 project 생성 금지 |

시뮬레이션 API는 기존 factory `/{project}/resimulate`, 메가는
`/projects/{project}/mega/plan`과 `/mega/start_all`을 재사용한다.
start_all은 자식별 접수/거절/실패·실행 상태를 표시하며 일부 접수를 전체 성공으로 표시하지 않는다.
모든 표 행에서 성공/실패·권한 부족·응답 유실·구/신규 ID 보존을 시험한다.
기존 미완성 데이터·계약을 legacy라는 이유로 통과시키는 예외는 없다.

## 11. 배치 계획·소유·검증

| 배치 | 선행 | 변경 파일/산출물(신규는 제안) | 출구 |
|---|---|---|---|
| R0 기록/분기 | 사용자 지시 | 체크포인트 코드/문서, 새 branch, 원격 일치 | push 확인; 실행 로그/운영 자료 제외 |
| R1 상세 설계·이중검토 | R0 로컬 기록 | 본 문서, 검토 기록, TEAM_BOARD/PROGRESS | 독립 두 검토, P0/P1 0, 중요 P2 조치/보류 명시 |
| B0 기존 기준선 복구 | R0 원격 + R1 | store projection·calc loader·project_data_context/HTTP, 인증 subject/종류별 적격성/정책·API·회귀 | 7 실패 해소·일관 읽기·인증 부정/경쟁·HTTP 격리 회귀 |
| B1 L2 저장/안전 | B0 | ECM models/repository, 신규 process_configuration service, `route_authority.py`, 관련 API | v2 읽기/쓰기·CAS·범위·구 writer guard |
| B2 팩/설치 시범 | B1 | kit registry/business kits, 신규 process pack/setup, instance operation 멱등성 | BK-01 설치·재개·실패·불변판 |
| B3 문맥/초안 계약 | B1; B2 통합 전 | advisor CAS/승격 operation, project meta/state, project_contract_aggregator/host_contract_compiler/nodes.contract, kit/runtime contract, 결정 조회/복구 계약 | 초안/승격 복구·양쪽 생성 경로·1.0 해시 보존·2.0 유실/위조 차단 |
| B4 L2 탐색/기본 수정 | B1/B2 API | companyApi, CompanySetupPanel, EnterprisePage, KitOperationsPanel | 설치→조회→수정→승인→새로고침 |
| B5 단일 제작 내용 | B3 계약 | Studio/RunControls/viewModel/sprintActions/BuildStartDialog, useFactoryStore 반환/확인, ContractReviewGate·결정 adapter, 입력별 draft 관리 | 결정 종류·개별 실행/일반/쿼터 재개·저장·오류/접근성·정적/브라우저 분리 |
| B6 제품 진입 연결 | B4/B5 | **App.tsx 단일 담당자**, ProductShell, BuildPage, 각 생성/알림 진입 | 단일 mount·URL/회사/SSE·유형별 parity |
| B7 업데이트/전환 수용 | B6 | process upgrade/restore, 회귀·브라우저·현업 측정 | override/기존 앱 보존, C1→C2 승격 판단 |

본 문서 작성·통합 책임은 Codex. 구현 담당은 배치 시작 시 TEAM_BOARD에서 한 명으로 확정한다.
독립 검토자는 구현 작성자와 분리한다. 같은 공통 파일을 둘이 동시에 편집하지 않는다.
B3 계약 설계와 B4 UI 설계는 병렬 가능하지만 전역 라우트 연결은 B6 한 번이다.
회사별 도메인 확인·실제 데이터 승인 지연을 개발 완료로 숨기지 않는다.
시간 공수는 B0의 실제 수정/회귀 결과 후 산정한다. 현 시점에 근거 없는 완료일·재작업 백분율을 제시하지 않는다.

## 12. 검증 명세와 합격 기준

기존 L2 설계 T01~T46을 유지한다. 아래 U01~U30은 추가 명세이며 **실행 결과가 아니다**.

| ID | 검증 | 합격 기준 |
|---|---|---|
| U01 | 기존 데이터 문맥 8건 | 8 통과; 누락 정책을 허용하는 편법 없음 |
| U02 | 보류 projection 변이 | None/손상/unknown hold 모두 차단, 최신 보류판 fallback 없음 |
| U03 | 인증 동시 서명·보류 경쟁 | 실패 시 해당 요청의 서명·상태·기간/용도 부분 commit 없음 |
| U04 | 일반/키트/보고서/알림/구 URL | 같은 프로젝트의 단일 Studio, 원치 않는 신규 프로젝트 0 |
| U05 | 단일 mount | 구/새 통제 중복 없음; 사용자 한 요청당 실행 한 번 |
| U06 | 문맥·직접 링크 변조 | 타 tenant/root/mode/scope 데이터·개수·이벤트 비노출 |
| U07 | 회사/사용자 전환 지연 응답 | 이전 응답·초안·SSE가 새 문맥에 나타나지 않음 |
| U08 | 새로고침/뒤로/앞으로 | 위치·저장 초안 복원, 실행/승인 재전송 없음 |
| U09 | 무데이터/무L2 시작 | 요구 초안 가능, 실행 계약/운영 READY 자동 승격 없음 |
| U10 | 실행 기능 parity | §10.1 모든 기능의 성공·실패/권한 결과 동등 |
| U11 | CTA projection | 과거 단계 선택으로 재실행 안 됨; 차단/unknown을 성공으로 표시 안 함 |
| U12 | 편집 저장 충돌·오프라인 | 입력 손실 없음, 실패/미저장 표시, 서버 CAS 충돌 설명 |
| U13 | 계약/의미 변경 | 표시명만 변경 시 재생성 안 함, 의미 변경은 재검토 |
| U14 | UI flag rollback | 구 writer 재개·v2 데이터 유실·보류 우회 없음 |
| U15 | 산출물 유형 | 앱/보고서/문서/시뮬레이터·메가 보드 경로 보존 |
| U16 | 키보드·화면 | 1280×720/1440×900 및 좁은 화면; 핵심 조작/오류/중단 접근 가능 |
| U17 | 초보 현업 과제 | J1~J5의 첫 행동·완주·오류·도움 요청을 동일 절차로 측정 |
| U18 | 영향/분모 표시 | 업무 골격/데이터/도구/실사용 지표 분리, 숨김으로 완료율 상승 없음 |
| U19 | A-1 projection 생산자 경쟁 | 독립 연결 개입·복수 행에서도 같은 읽기 snapshot, 최신 보류판 fallback 금지 |
| U20 | A-2 인증 대상/종류별 권한 | 실제 격리 조직/PDP로 교차 문맥404·부적격403·적격 성공·회수 차단·동일인 정책 |
| U21 | A-3 서명 subject 불변/멱등 | 다른 기간/용도409, 정책/소유권 변경 재확인, 동일 재시도 동일 사건, 동시 부분 commit 없음 |
| U22 | A-4 생산자/버전 호환 | 일반/키트 문맥 유실·위조 차단, 의미 변경 새지문/표시 변경 유지,1.0 golden proof 불변 |
| U23 | A-5 초안/승격 실패 | 편집↔승인 CAS, meta/state/원장 단계별 실패 후 같은 project/문맥 재개, 불완전 실행 차단 |
| U24 | A-6 프로젝트 생성 HTTP | 보류409/판독불가503/비가시404,500으로 위장 안함, project 생성/노출 없음 |
| U25 | B-1 결정 종류별 승인 | 일반HOTL/Host/능력선택/키트 분리, 승인/반려/403, state_applied=false 재승인 없이 복구 |
| U26 | B-2 개별 실행/중단/복구 | 대기/일반중단/실패/쿼터 task/mode, heal 새task·기존HOTL·연결/횟수 차단의 관찰 대상/다음행동, 거절/응답 유실 시 상태 초기화·추가REVISION 자동 생성 없음 |
| U27 | B-3 target별 경로 | new/draft/project/kit_app/release/mega 직접링크·뒤/앞/새로고침·상단메뉴·데이터 준비 왕복, 쓰기 재전송 없음 |
| U28 | B-4 입력 수명 | 네 입력 종류의 저장/미저장 이동·같은 project 새결정·사용자 전환에서 유실/오복원 없음 |
| U29 | B-5 유형×기존/신규 | §10.2 모든 업무 행동·이전 cycle/ID/승인 보존, 결과 버튼 무동작·legacy 우회 없음 |
| U30 | B-6 사용성 판정 | J1~J5 참가자×과제 원표, 순서 교차·도움 기준·실패 포함, 자동 검증과 현업 결과 분리 |

검증 실행 방식:

- B0는 새 임시 DB만 허용하는 audit hook/기존 격리 도구를 사용한다. 전역 conftest의 운영 접근을 우회 허용하지 않는다.
- ECM·키트·프로젝트·권한·Host 계약은 해당 단위/통합/HTTP 부정 시험을 배치별로 실행한다.
- 프론트 `package.json`에는 현재 별도 단위 test script가 없다. 기존 자동화 기반을 확인해
  projection 단위 시험·브라우저 회귀를 배치 B5 전에 마련하고 실제 실행 명령을 인계한다.
  명령이 존재하지 않는 `npm test`를 통과했다고 기록하지 않는다.
- 프론트 빌드/타입 검사, URL/역할별 실제 브라우저 E2E, 이미지 육안 검증을 분리한다.
  DOM 통과는 시각 검증을 대신하지 않는다. 로컬 개발 포트와 격리 데이터만 사용한다.
- 사용자 시험 목표(미측정): 대표 현업 최소 5명, 첫 행동 무도움 성공 4/5 이상,
  J1/J3 핵심 과제 무도움 완주 4/5 이상, 심각한 잘못된 승인/데이터 혼동 0건.
  시간은 기존 화면과 같은 과제·참여자 조건으로 비교하되 임의 '몇 초 단축'을 성과로 쓰지 않는다.
  표본이 작아 일반화할 수 없으며 관찰 실패가 있으면 원인·수정·재시험을 남긴다.

### 12.1 재사용 검증 도구와 새 하네스 — 검토 B-6

아래 현존 명령은 소스를 확인한 재사용 후보이며 이번 설계 턴에 실행한 명령이 아니다.

| 구분 | 명령/산출물 | 검증 범위와 한계 |
|---|---|---|
| 현존 React SSR·순수함수 패턴 | frontend에서 `node scripts/check-kit-getting-started.mjs` | 실제 React 정적 렌더/TS transpile·assert 패턴. 이벤트·권한·실제 브라우저 아님 |
| 현존 레이아웃 fixture | frontend에서 `node scripts/build-enterprise-layout-fixture.mjs` | Vite로 격리 fixture 번들 생성. 브라우저 실행·이미지/키보드 검증은 별도 |
| 현존 생성 그래프 시험 | 격리 runner에서 `tests/test_sw_factory_walkthrough.py`, `tests/test_sw_factory_full_walk.py` | 실제 그래프/컴파일러, LLM 응답은 대역. Studio 브라우저 검증 아님 |
| 신규 작성 예정 | `frontend/scripts/check-studio-contracts.mjs`, 실행 `node scripts/check-studio-contracts.mjs` | 순수 CTA/target/draft key mapper의 table tests와 SSR. 상태 응답 fixture는 명시하며 서버 권한을 대역으로 입증하지 않음 |
| 신규 작성 예정 | `frontend/tests/studio-transition.fixture.*`와 전용 Vite build script | 앱/문서/시뮬레이터/메가·오류 상태 layout 확인. 실 API/SSE/승인 여정은 별도 로컬 E2E |
| 신규 작성 예정 | `scripts/verify_l2_studio_contracts.py` | 임시 경로 allowlist·전역 conftest 격리·소스/자산 해시·JUnit으로 실제 HTTP/DB 경계 회귀 |

신규 파일/명령은 B3/B5에서 작성·동작 확인한 뒤 실제 증거 경로와 함께 인계한다.
단위 mapper는 기존 view model의 상태 판정을 입력으로 받고 두 번째 업무 상태 머신을 만들지 않는다.
fixture는 SYNTHETIC 배너·모의 응답 범위를 명시한다. 실제 브라우저 E2E는 별도 포트·현재 권한
fixture·실제 제품 API를 사용하고 UI/API/SSE 실패를 대역 성공으로 덮지 않는다.
빌드/SSR/HTTP/브라우저/현업 결과는 다섯 별도 열로 보고하며 하나의 PASS로 합치지 않는다.

### 12.2 현업 시험의 사전 판정 규칙

대표 현업 최소5명에게 동등 난이도의 서로 다른 과제를 사용한다.
기존→신규와 신규→기존을 교차 배정(5명이면3/2), 과제·데이터 fixture·노출 순서를 기록한다.
진행자는 과제 설명만 읽고, 버튼/위치/기능 설명을 한 번이라도 도우면 assisted로 센다.
연습 효과·역할·외부 승인 대기 시간은 별도 기록하며 개선의 인과관계를 과장하지 않는다.

- J1: 업무 선택→요구→설계 확인→결과 검토. 무도움4/5 이상.
- J2: 무데이터 요구 저장→재열기, 초안과 운영 준비 구별. 무도움4/5 이상.
- J3: 기존 작업/결과→올바른 재개·검토. 무도움4/5 이상.
- J4: 차단 이유/담당 역할 파악→데이터 준비 진입→원래 초안 복귀. 무도움4/5 이상.
- J5: 이름/순서/추가/미사용 변경 제안→적격자 검토→ID/연결 보존 확인.
  실제 역할을 나누어 평가하고 작성자·승인자 각 과제 무도움4/5 이상; 역할 없는 사용자의 거절이 정상이다.
- 모든 과제: 심각한 잘못된 승인·회사/데이터 성격 혼동0. 실패/중도 포기를 분모에서 빼지 않는다.

참가자 익명 ID×과제별 첫 행동/완주/도움 횟수/오류/활동 시간·전체 시간/화면 revision을 원표로 남긴다.
운영 승인이나 외부 발송 없는 격리 과제로 수행한다. 이는 도메인 실데이터 수용 시험을 대체하지 않는다.
관찰이 없는 현재 단계의 결과는 NOT_RUN이다.

## 13. 이중검토 방식과 구현 시작 Gate

**서로 다른 독립 에이전트 두 개**가 문서·현행 소스를 읽고 판단한다.
실제 Claude/Gemini 또는 현업 승인으로 가장하지 않는다. 작성자의 자체검토를 독립 검토로 세지 않는다.

- 검토 A: 데이터/아키텍처/구현 가능성. 범위·ID·CAS·설치 실패·runtime 계약·기존 회귀·동시성.
- 검토 B: 현업 사용성/제품 범위/전환 회귀. 두 화면 제거 경로·첫 행동·무데이터 초안·권한·오류·복구·측정.
- 각각 근거 위치, 실패 시나리오, 심각도, 수정안, 확인할 시험을 반환한다.
- 작성자가 두 결과를 조정·반영하고, 원 검토자에게 반영본을 다시 보내 해결 여부를 확인한다.
- 판정은 PASS / CHANGES_REQUIRED / BLOCKED. P0/P1 미해결이면 구현하지 않는다.
  안전/정보유실과 무관한 P2만 책임자·배치·검증을 지정해 이관 가능하다.
- 설계 검토 PASS는 B0 착수 허용이지 B1~B7·운영 데이터·배포 승인이나 기능 통과가 아니다.
- 사용자 요청의 순서를 위해 원격 체크포인트 확인도 B0 전제다. 푸시 차단 중에는 문서/읽기 검토만 진행한다.

## 14. 진척 보고 규칙·완료 정의

전체 분모 40과 로컬 28을 임의로 바꾸지 않는다. 본 배치의 문서 수·L2 수·시험 수를 제품 분자에 더하지 않는다.
매 작업 보고에 전체 52.5%/로컬 약64%, 현재 배치 상태, 새 검증 증거, 막힌 항목, 다음 행동을 구분한다.
실제 연결/실사용 종료 증거가 생길 때 PROGRESS의 해당 영역을 다시 평가한다.

본 설계 단계 완료는 상세 문서 + 두 독립 검토 기록 + 조치 재확인 + 실행 순서/소유/중단 기준이다.
실행 코드와 UI의 완료는 B0~B7 출구 증거이며 별개다.

## 15. 근거·기록

- 상위: Product Bible, 독자 제품 전략 §4/8/9/11, 최종 완성 로드맵 G0/G2/G3 및 §15.
- 기존 계약: `docs/design_business_kit_l2_process_setup_2026-09-12.md` §5~16, T01~T46.
- 체크포인트: `docs/handoff/L2_STUDIO_BRANCH_CHECKPOINT_2026-09-12.md`.
- 최신 인계: `docs/handoff/CLAUDE_TO_CODEX_USAGE_HOLD_FAKESTORE_2026-09-12.md`.
- UI 근거: §2 파일, `frontend/src/lib/companyApi.ts`, `frontend/src/store/useFactoryStore.ts`.
- 서버 근거: ECM repository/profile resolver, `api/routes/factory_control.py`,
  `core/advisor_store.py`, `core/advisor_blueprint.py`, `core/kit_app_contract.py`,
  `core/app_runtime_contract.py`, `core/data_preparation/usage_policy.py`/snapshot_service/store.
- 이번 초안 작성은 문서만 변경한다. 새 브랜치에서 제품 코드·키트·DB·승인·앱·운영 배포 변경 없음.
