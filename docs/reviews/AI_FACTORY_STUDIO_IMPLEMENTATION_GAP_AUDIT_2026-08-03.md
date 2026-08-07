# AI Factory Studio 구현 현황·미비점 감사

> 기준일: 2026-08-03  
> 작성: Codex  
> 검토 기준 커밋: `a484c6f63`  
> 개정: 1.3 — 범용 외부 협업 레거시 Profile 간극 반영  
> 목적: 문서의 계획과 현재 소스를 분리해 판정하고, Claude Code의 최신 CL-0 구현 및 다음 통합 위험을 코드 근거로 전달한다.

---

## 1. 요약 판정

AI Factory Studio는 단순 프로토타입보다 훨씬 앞서 있다. 30개 안팎의 API Router, 다중 에이전트 생성 파이프라인, MDM·카탈로그·조직 범위·외부지표·계획·가상기업·감사 기반이 실제 코드에 존재한다.

그러나 현재의 강한 기반은 아직 하나의 제품 경험으로 닫히지 않았다. 다음 세 간극이 가장 크다.

1. **통합 간극**: 데이터·권한·생성·시뮬레이션·결정 기능이 개별 API로 존재하지만 동일 현업 사건을 공유하지 않는다.
2. **강제 간극**: 정책과 Manifest가 있어도 생성 앱 런타임·실제 인증·SSE에서 우회를 차단하는 강제가 부족하다.
3. **증명 간극**: 실제 데이터의 과거 재현, 시나리오 오차, 실행 전후 효과와 ROI가 측정되지 않았다.

따라서 다음 목표는 새 기능 개수 증가가 아니라 `안전한 앱 런타임 + 원료 구매 수직 폐루프`의 통합이다.

---

## 2. 소스 기준 구현 자산

### 2.1 실제 API 표면

`main.py:78-111` 기준으로 다음 영역이 Router로 등록되어 있다.

- Factory, 출력 양식, 실시간, 스킬 진화
- Knowledge, Reference, Telemetry
- Planning, Connector, Briefing, Shadow, Workspace, Readiness, Program
- Scope, Sandbox, Admin, Master, Standard, Organization
- Advisor, Decision Ledger
- Enterprise Context, Benchmark
- Catalog, Glossary, Lineage, Contract, External Intelligence
- Crosswalk, MCP

이는 제품 개념이 문서에만 있는 것이 아니라 상당 부분 API로 구현되었음을 뜻한다. 반대로 Router 수는 사용자 가치나 폐루프 완주를 증명하지 않는다.

### 2.2 AI SW 생성 공장

실제 구현:

- LangGraph 상태·체크포인트 기반 단계 실행
- 요구사항 명확화와 선택형 HOTL
- 기획, UI, 아키텍처, WBS, 개발, 검토, QA, 릴리스
- 다중 LLM 공급자와 폴백
- 코드·렌더·상호작용·백엔드 smoke·회귀 품질 게이트
- 실패 재작업과 상태 저장

남은 핵심:

- 자가복구 3회 소진 후 명시적 종료·인계 상태
- 릴리스 적격성과 운영 실행 차단
- 생성 앱 Host SDK와 데이터 접근 강제
- 장시간·쿼터 소진·서버 재시작 E2E 신뢰성

### 2.3 회사·데이터·지식 기반

실제 구현:

- ECM의 조직 계층 및 REAL/VIRTUAL/COMPETITOR
- 마스터 데이터와 조직 범위
- 카탈로그·용어·계보·계약·크로스워크
- 외부지표와 시나리오 연결 구조
- Knowledge/Reference 데이터 수집·검색 기반

남은 핵심:

- 여러 저장소를 하나의 의미 경로로 묶는 통합 질의 계약
- 업무 엔터티 간 확정 관계와 유효기간
- 실제 운영 데이터의 품질 SLA와 소유자 보정 흐름
- 자연어 질의의 근거 경로와 권한 필터
- GraphRAG 후보와 결정론적 계산의 책임 분리

### 2.4 경영계획·시뮬레이션

실제 구현:

- 계획, 가정, 기준선, 결과 비교의 초기 데이터 모델
- 외부지표·경쟁사 근거·전사 집계·보드 계열
- 가상기업 Sandbox

남은 핵심:

- 버전이 고정된 계산식과 실행 코드
- 원료 구매→재고→생산→현금→손익의 첫 계산 그래프
- 과거 시점 빈티지 데이터 기반 백테스트
- 실제 실적 대사와 오차 분해
- 의사결정·실행·효과 측정 연결

### 2.5 프론트엔드

실제 구현:

- 현재 Factory 통제실과 다수 관리 Panel
- 개발용 사용자·회사 컨텍스트 전환
- SSE, Preview, Timeline, WBS, HOTL
- 승인된 정적 UI North Star와 폐루프 프로토타입

구조 부채:

- `frontend/src/App.tsx:59-80`의 다수 `showX` boolean과 조건부 Panel 방식
- URL·뒤로가기·깊은 링크·페이지별 권한 경계의 불명확성
- 실제 제품과 정적 시안의 차이
- 전역 Jarvis, 회사 컨텍스트, 설정·관리자의 일관된 AppShell 미완

다음 단계는 전면 재디자인이 아니라 URL 기반 AppShell에 실제 기능을 점진적으로 이식하는 것이다. Factory의 전체 흐름·WBS·현재 작업·사용자 결정·Jarvis를 다시 숨기면 안 된다.

---

## 3. 엔터프라이즈 준비도 감사

### 3.1 인증과 사용자 관리

현재 `UserSwitcher`와 요청 헤더 기반 전환은 개발·검증 도구다. 실제 인증으로 간주할 수 없다.

필요 항목:

- OIDC/SAML SSO
- 사용자·그룹 동기화
- 세션·토큰 수명과 강제 로그아웃
- 서비스·앱 계정
- 관리자 위임과 break-glass
- 다중 조직 정책과 데이터 계층 강제

### 3.2 실시간 이벤트

`core/broadcaster.py:15`는 클라이언트 Queue 목록만 관리하고 `broadcast()`가 전체 구독자에게 팬아웃한다. 프론트의 프로젝트 필터는 정보 유출 방지 경계가 될 수 없다.

필수 수정:

- 구독 principal·scope 저장
- 이벤트 대상 사용자·조직·프로젝트 분류
- 서버측 필터
- 오프라인 재전송·멱등성
- 협업 이벤트 격리 테스트

### 3.3 데이터 저장소

`core/`에는 advisor, connector, decision ledger, external intelligence, master data, MCP, organization, enterprise context, planning, program lifecycle, release readiness, shadow, workspace 등의 SQLite 연결이 분산되어 있다.

개발 속도에는 유리하지만 상용 운영에서는 다음 위험이 있다.

- 도메인 간 원자적 상태 전이 어려움
- 마이그레이션·백업·복구 절차 분산
- 다중 워커 잠금과 성능
- 일관된 RLS 적용 어려움
- 이벤트와 원장의 이중 기록 실패

권고:

- 즉시 전면 통합하지 않는다.
- 먼저 도메인 소유권과 트랜잭션 경계를 문서화한다.
- 협업 폐루프는 단일 Postgres 스키마 또는 명확한 outbox로 설계한다.
- 파일럿 후 운영 DB 통합·마이그레이션을 G7에서 수행한다.

### 3.4 운영성

테스트 수는 강점이지만 다음이 별도 증명되어야 한다.

- 다중 워커·장시간 작업·서버 재시작 복구
- queue, retry, dead-letter
- 구조화 metric/trace/LLM telemetry
- 데이터·문서·체크포인트 백업과 복구 훈련
- DB migration과 rollback
- 자원·비용 quota와 테넌트 제한

### 3.5 실제 데이터 부트스트랩과 외부 협업 레거시 연계

현재 시스템에는 기준정보 시드, Reference 등록, Connector·Crosswalk·MCP, 외부지표 기반이 있으나 원료 구매 파일럿의 운영 데이터에 대해 `원천 등록 → 최소 추출 → RAW 보존 → 품질 격리 → 표준 매핑 → 원천 대사 → 데이터 오너 승인 → CERTIFIED 기준선`을 하나의 사용자 여정으로 수행하는 기능은 완성되지 않았다. 시드가 잘 적재됐다는 사실은 Actual 준비 완료를 뜻하지 않는다.

외부 거래처·관세사·포워더·운송사가 사용하는 고객사 기존 시스템은 현재 고객별 Adapter Profile로 추상화돼 있지 않다. 현재 `MCPAdapter.fetch()`는 승인된 단일 객체 조회와 TTL 캐시에 적합하지만 선적·통관·운송 사건의 목록·페이지·증분 변경·정정·취소를 가져오는 계약은 없다. 외부 사용자를 우리 조직과 권한 모델에 추가하지 않고, 고객사 기존 시스템을 읽기 전용 System of Engagement로 등록해 `query/changes_since`, cursor, source event version, 멱등키, Crosswalk, 원천 대사를 보강해야 한다. LPL은 LS 환경의 첫 Reference Profile이며 코어에 하드코딩해서는 안 된다.

---

## 4. Claude Code CL-0 교차검토

### 4.1 검토 대상

- `core/app_manifest.py`
- `nodes/utils/platform_auth_checker.py`
- `api/routes/factory_control.py` 릴리스 경로
- `tests/test_app_manifest.py`
- `tests/test_m0_end_to_end.py`
- 커밋 `a484c6f63`

### 4.2 검증 결과

명령:

```powershell
venv\Scripts\python.exe -m pytest tests/test_app_manifest.py tests/test_m0_end_to_end.py -q
```

결과: **45 passed**, 경고 2건은 외부 패키지 deprecation이다.

### 4.3 잘된 점

- App-in-App의 인증·조직·감사 상속 원칙이 코드 계약으로 생겼다.
- Manifest canonicalization과 snapshot을 릴리스에 저장한다.
- 자체 로그인·사용자 저장소·JWT 발급 같은 생성 오류를 탐지한다.
- 기존 릴리스 키를 깨뜨리지 않고 증빙을 추가했다.
- 일반 입력 폼을 인증 화면으로 오탐하지 않으려는 테스트 방향이 있다.

### 4.4 결함과 위험

#### A. 정규식 검사는 보안 경계가 아니다

`nodes/utils/platform_auth_checker.py:92`의 `scan_text()`는 라인 기반 패턴이다. 문자열 분리, 동적 import, 간접 호출, 별도 설정 파일로 우회할 수 있다.

조치: 정적 검사는 릴리스 품질 증빙으로 유지하되 실제 보안은 Host Runtime API에서 강제한다.

#### B. 허용 문맥이 너무 넓다

`nodes/utils/platform_auth_checker.py:38`의 `_ALLOWED_CONTEXT`는 라인에 특정 단어가 포함되면 허용 사유가 된다. 생성 코드가 허용 단어를 주석이나 변수명에 넣어 차단을 피할 수 있다.

조치: 파일 위치, AST 문맥, 명시적 예외 식별자와 승인 이력으로 제한한다.

#### C. 과거 아카이브가 현재 릴리스를 오염시킨다

검사는 프로젝트 경로 전체를 순회하지만 `.archive`를 제외하지 않는다. 실제 프로젝트에는 이전 산출물 아카이브가 존재한다.

조치: `file_index` 또는 릴리스 Manifest의 확정 파일만 검사하고 아카이브·이전 릴리스를 제외한다.

#### D. 빈 capability Manifest도 정상이다

`core/app_manifest.py:221`의 `snapshot(None)`은 기본 Manifest를 만든다. 실제 기능이 데이터를 읽고 쓰더라도 선언이 비어 있으면 현재 계약만으로 차이를 잡지 못한다.

조치: 앱 유형별 필수 capability, 코드 관측, Runtime 호출을 비교하고 차이를 차단 또는 재승인한다.

#### E. 차단 결과가 릴리스를 막지 않는다

`api/routes/factory_control.py:1247-1265`는 Manifest와 검사 결과를 릴리스에 저장하지만 검사 실패를 릴리스 부적격 상태로 강제하지 않는다.

조치: `DRAFT → SCANNED → ELIGIBLE/INELIGIBLE → APPROVED → ACTIVE` 릴리스 상태를 두고 전달·수락·실행에서 재검증한다.

#### F. 런타임 강제가 없다

생성 앱이 직접 DB 연결, 외부 네트워크, 플랫폼 사용자 토큰을 얻지 못하게 하는 실행 경계가 아직 없다.

조치: Host Runtime SDK, short-lived scoped token, capability policy, network allowlist, audit를 CL-1 선행 계약으로 둔다.

### 4.5 CL-0.5 필수 테스트

- `.archive`에 금지 코드가 있어도 현재 릴리스만 정상 판정
- 현재 릴리스 금지 코드의 문자열 분리·간접 호출 탐지 또는 런타임 차단
- 읽기 실패 파일이 있으면 검사 완료로 처리하지 않음
- 빈 capability로 실제 데이터 API 호출 시 차단
- Manifest 축소 업데이트 후 기존 권한 호출 차단
- INELIGIBLE 릴리스 전달·수락·실행 차단
- Manifest fingerprint 위변조 탐지
- 검사 결과와 런타임 관측 차이 감사 기록

### 4.6 최종 판정

CL-0은 **조건부 승인**이다. “Manifest와 정적 검사 기반 마련”으로는 완료지만 “플랫폼 인증 상속 강제 완료”는 아니다. CL-1 통합 전에 CL-0.5와 Host Runtime 최소 계약을 완료해야 한다.

---

## 5. 기능별 미비 우선순위

| 순위 | 미비점 | 실패 시 영향 | 대응 단계 |
|---:|---|---|---|
| 1 | Host Runtime·릴리스 강제 미비 | 앱 권한 우회·보안 사고 | G1 |
| 2 | 사용자별 SSE 미비 | 협업 정보 유출 | G1 |
| 3 | MVA 부트스트랩·원천 대사 미완 | Actual 없는 데모 Twin | G2 |
| 4 | 외부 레거시 Adapter Profile·증분 사건 연계 미완 | 고객별 SI 분기·중복/오래된 값 위험 | G1/G2 |
| 5 | 첫 도메인 의미 모델 미완 | 데이터 기반 차별화 불가 | G2 |
| 6 | 결정론적 계산·백테스트 미완 | Twin 신뢰 불가 | G4 |
| 7 | 앱 전달·수락 실제 구현 미완 | 부서 협업 가치 미증명 | G3 |
| 8 | 결정→실행→효과 미완 | 보고서 생성 도구에 머묾 | G5 |
| 9 | 실제 SSO·RLS·Secret 미완 | 엔터프라이즈 도입 불가 | G7 |
| 10 | 운영 DB·관측·DR 미완 | 상용 SLA 불가 | G7 |
| 11 | Jarvis 전역 실행 미완 | 통합 사용 경험 부족 | G6 |
| 12 | 실제 ROI·사용성 미측정 | 내부 확산·사업화 설득 불가 | G8 |

---

## 6. 다음 통합 전에 답해야 할 질문

### CL-1 앱 전달

- 전달 이벤트는 누구에게만 보이는가?
- 수락한 사용자가 원래 권한 없는 데이터에 접근하지 않는가?
- 앱 버전 변경 시 어떤 capability가 다시 승인되는가?
- 거절·철회·만료·퇴직·조직 이동은 어떻게 처리하는가?

### 시뮬레이션

- 숫자를 만든 주체가 LLM인가 계산 엔진인가?
- 입력과 모델 버전을 고정해 결과를 재현할 수 있는가?
- 관측·전망·가정을 화면에서 구분하는가?
- 과거 공개 시점 기준으로 백테스트할 수 있는가?

### 의사결정

- 보고서 생성 시점의 데이터가 불변 스냅샷인가?
- 승인자가 본 자료와 실행에 사용된 자료가 같은가?
- 실행 실패·부분 완료·취소가 결정 원장에 연결되는가?
- 효과 KPI와 측정 기간을 결정 시점에 고정하는가?

### Jarvis

- Task ID 없이 어떤 범위의 전사 데이터를 읽는가?
- 답변 근거와 기준시점을 반환하는가?
- 도구 실행은 어떤 승인 단계와 권한을 통과하는가?
- 대화 기억이 조직 이동·퇴직·데이터 삭제를 따르는가?

---

## 7. 감사 결론

현재 시스템의 가장 큰 위험은 기술력이 부족한 것이 아니라, 이미 만든 많은 기반을 제품의 한 문장과 한 업무 폐루프로 묶지 못한 채 다음 기능으로 이동하는 것이다.

다음 통합의 성공 기준은 다음과 같다.

> “구매 담당자가 만든 앱을 물류 담당자가 안전하게 수락해 실제 데이터를 입력하고, 그 데이터가 생산·현금·손익 시뮬레이션과 의사결정·실행 효과까지 이어졌다.”

이 문장이 실제 사용자·실제 데이터·실제 권한으로 재현되면 AI Factory Studio는 경쟁사의 기능 목록을 따라가는 제품이 아니라 독자적인 제조 경영 운영체계가 된다.
