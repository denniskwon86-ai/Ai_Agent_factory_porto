# Claude Code 단독 수행 인계 — I-4·업무키트·3주 시연 MVP 통합 실행

> 인계 ID: `CLAUDE-SOLO-I4-BDR-MVP-20260816-01`  
> 지시자: Supervisor  
> 작성자: Codex  
> 작성일: 2026-08-16 KST  
> 필수 수신자: Claude Code 및 이후 동일 작업을 이어받는 세션  
> 실행 방식: **병렬개발 일시 보류 · Claude Code 단독 순차 구현**  
> 현재 기준 HEAD: `d3df38d21`  
> 현재 작업 중: I-4 `4c-0` 프로필 3상태 판독·손상 차단(미커밋 변경 존재)  
> origin 정책: **사용자의 별도 명시 지시 전까지 fetch·push·merge 등 origin 작업 금지**

---

## 0. Supervisor의 이번 지시

토큰 사용 한도 문제로 Codex·Claude Code의 병렬 코드 구현을 일단 보류한다. Claude Code는 현재 진행 중인 I-4 4단계를 마친 뒤 단순히 I-4 5~8만 끝내는 것이 아니라, 직전에 확정한 **업무키트 데이터 연결·준비 런타임 상세설계(BDR)**를 현재 실행계획 안에 삽입하여 3주 시연에 필요한 수직 폐루프를 최대한 완주한다.

이 문서는 기존 정본을 대체하지 않는다. 여러 정본의 작업 순서와 3주 시연 절단선을 **Claude Code 단독 실행 기준으로 묶는 실행 지시서**다.

### 이 지시를 한 문장으로

> I-4가 안전한 App-in-App을 만드는 데서 끝나지 않게 하고, 원료 구매 업무키트를 선택해 승인 파일 Snapshot을 준비하고, 생성 앱·온톨로지·계산·의사결정이 동일한 데이터 판을 사용하는 시연 경로까지 연결한다.

---

## 1. 반드시 전문으로 읽을 정본과 우선순위

다음 순서로 읽는다. 요약만 읽고 구현하지 않는다.

1. `docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md`
2. `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md`
3. `docs/roadmap/THREE_WEEK_DEMONSTRABLE_MVP_EXECUTION_PLAN_2026-08-15.md`
4. `docs/design_i4_generator_host_runtime_2026-08-15.md`
5. `docs/handoff/I4_HOST_RUNTIME_HANDOFF_2026-08-15.md`
6. `docs/architecture/BUSINESS_DATA_BINDING_RUNTIME_DETAILED_DESIGN_2026-08-15.md`
7. `docs/architecture/business_data_binding_contract_v1.schema.json`
8. `docs/architecture/first_vertical_data_binding_profile_v1.example.json`
9. `docs/handoff/BUSINESS_DATA_BINDING_RUNTIME_TEAM_HANDOFF_2026-08-15.md`
10. 본 인계서

충돌 시 우선순위는 다음과 같다.

```text
Supervisor 최신 지시
→ Product Bible·최신 전략
→ 3주 시연 MVP 실행계획
→ I-4·BDR 상세설계
→ 본 단독 수행 인계
→ 과거 인수인계·대화·주석
```

본 인계서가 기존 병렬개발 문서와 다른 점은 **구현자가 Claude Code 한 명이라는 것**뿐이다. 보안·데이터·게이트 기준은 낮추지 않는다.

---

## 2. 현재 사실과 재개 지점

### 2.1 완료된 것 — 다시 만들지 않는다

| 영역 | 완료 상태 |
|---|---|
| G1-B Host Runtime·PDP·앱 증명 | 완료·강제 전환됨 |
| I-4 1단계 | 계약 Schema·Compiler·ProjectState 완료 |
| I-4 2단계 | 안정 데이터셋 식별자·릴리스 바인딩·데이터셋별 판정 완료 |
| I-4 2.1/2.1b | 스키마 판·불변 지문·테넌트/앱 결속·fail-closed 완료 |
| BDR-1/I-4 2.2·2.2a | 데이터 역할·출처 의도·중복 입력 정책·공통 의미 판정 완료 |
| I-4 3단계 | 계약 원문 지문+물질화 지문 증명 봉인·410 완료 |
| I-4 4a·4b | WBS `artifact_kind`·Tech Lead 필수화·ContractReviewGate 판정 완료 |
| 테스트 하니스 | 깨끗한 checkout과 작업트리가 같은 대상을 검사하도록 보정됨 |

### 2.2 현재 미커밋 소유 변경

Claude Code가 4c-0으로 수정 중인 파일:

- `api/routes/factory_control.py`
- `core/wbs_artifact_kind.py`
- `tests/test_runtime_contract_profile.py`

현재 구현 내용:

- `LEGACY_OFF / V1_ON / UNREADABLE` 3상태
- 손상·미지원·누락 메타의 스프린트 시작/재개 503 차단
- 레거시 기존 흐름 보존
- 운영 프로젝트 60건이 모두 `LEGACY_OFF`이고 손상 0건이라는 실측

### 2.3 첫 재개 행동

1. 위 3개 파일 외 다른 세션 변경이 섞이지 않았는지 `git diff --name-only`로 확인한다.
2. 4c-0 집중 회귀와 전체 회귀를 다시 기록한다.
3. 4c-0 파일만 원자 커밋한다.
4. 커밋 ID를 본 인계의 완료 보고에 남긴다.
5. 4c-1로 이동한다.

`.agents/TEAM_BOARD.md`, `.agents/AGENTS.md`, 데이터키트 문서 등 다른 미커밋 변경은 4c-0 코드 커밋에 섞지 않는다.

---

## 3. 제품 범위 동결

### 3.1 3주 시연에서 반드시 완주할 사용자 경로

```text
샘플 회사·조직 선택
→ 원료 구매·도입 업무키트 선택
→ 필요한 데이터와 현재 준비 상태 확인
→ 제공 샘플 또는 회사 CSV 파일 등록
→ RAW 불변 Snapshot 생성
→ 품질·단위·결측·대사 확인
→ DEMO/SYNTHETIC 인증 Snapshot 승인
→ 생성 앱에서 기존 원천 데이터는 읽고, 원천에 없는 대응 메모만 입력
→ 동일 Snapshot Set으로 온톨로지 영향 경로 조회
→ 환율 +10%·도입 지연 +14일·전력비 +12% 시뮬레이션
→ 생산량·재고·현금·영업이익 변화
→ 의사결정 회의 요청·3관점 검토서·경영 브리핑
```

### 3.2 반드시 포함

- 신규 App-in-App의 계약→검토→승인→물질화→실행
- 원료 구매 업무키트 1종
- 회사·조직별 Kit Instance
- Source Binding 최소 2종: `FILE_SNAPSHOT`, `AFS_NATIVE`
- PRC-02 구매주문, INV-01 재고, FIN-03 손익·현금의 L0 파일 Snapshot 종단
- 나머지 시연 MDD는 검증된 DEMO Fixture로 제공하되 같은 계약·Snapshot 표면 사용
- 준비도 상태와 다음 행동
- 생성 앱의 Provider Dispatch
- 승인 Snapshot ID 집합으로 만든 Baseline
- G2 최소 경로와 G4 최소 계산 연결
- 모든 값의 DEMO/SYNTHETIC·출처·기준시점·품질 상태 표시

### 3.3 3주 필수 경로에서 제외

- 실제 고객 ERP·MES·WMS·LPL 신규 EAI
- BDR-4의 실제 운영 Connector 연계
- L3 write-back·양방향 자동화
- 모든 업종·업무 키트 범용화
- 실제 회사 데이터의 `CERTIFIED ACTUAL` 발급
- 자유형 온톨로지 질의 전체
- 전체 UI 테마 재설계
- 실제 경영효과·ROI 달성 주장

제외 항목은 조용히 폴백하지 않는다. 화면과 API에서 `지원 대기` 또는 `현재 시연 범위 아님`으로 표시한다.

---

## 4. 단독 수행 전체 순서 — 변경 금지

```text
Wave A  I-4 4c-0~4c-7 안전한 그래프 연결
  ↓ Gate A
Wave B  I-4 5 Typed SDK·정적검사
  ↓ Gate B
Wave C  BDR-2 Kit Instance·Source Binding
  ↓ Gate C
Wave D  BDR-3 L0 파일 Snapshot MVP
  ↓ Gate D
Wave E  BDR-5 최소 Readiness + BDR-6 Provider Dispatch
  ↓ Gate E
Wave F  I-4 6·7·8 Preview→ACTIVE→종단 카나리
  ↓ Gate F
Wave G  BDR-7 Baseline→G2→G4→의사결정 종단
  ↓ Gate G
Wave H  최소 제품 화면·Demo Reset·Readiness Check·리허설
```

I-4 내부 순서 4→5→6→7→8은 유지한다. BDR-2/3/5/6은 I-4 5와 6 사이에 삽입하여, I-4 8 카나리를 AFS Native만으로 끝낸 뒤 다시 뜯는 일을 막는다.

---

## 5. Wave A — I-4 4c 완결

### 4c-0 프로필 3상태·손상 차단

현재 작업을 원자 커밋한다.

완료 조건:

- 정상 키 없음/빈 값=`LEGACY_OFF`
- 명시 `v1`=`V1_ON`
- 파일 없음·손상·비객체·미지원 값=`UNREADABLE`
- `sprint/start`와 `hotl/resume` 모두 503
- 운영 60개 기존 프로젝트가 소급 적용되지 않음

### 4c-1 프로젝트 단위 계약 합산기

HostContractCompiler는 현재 태스크 하나가 아니라 WBS의 모든 계약 대상 태스크를 모아 프로젝트 계약 하나를 만든다.

필수 규칙:

1. 태스크 순서와 무관하게 동일 지문
2. 서로 다른 `dataset_key`는 모두 포함
3. 같은 `dataset_key`의 동일 계약은 한 번만 포함
4. 같은 `dataset_key`의 schema/action/role/source/policy 충돌은 자동 병합 금지·`BLOCKED`
5. 계약 대상이 아닌 `REPORT/DOCUMENT/LIBRARY`는 제외
6. WBS 판독 불가는 APP 계약 대상으로 유지

삭제 태스크 정책은 다음으로 확정한다. 추가 판단을 기다리지 않는다.

> WBS에서 삭제된 태스크의 데이터셋은 **새 프로젝트 계약 합산에서 즉시 제외**한다. 이로 인해 지문이 변경되고 재승인이 필요하다. 기존 물리 데이터셋·레코드·이전 릴리스 바인딩은 삭제하지 않는다. 물리 폐지는 별도 명시적 retire 절차에서만 수행한다.

필수 회귀:

- APP 2개·서로 다른 데이터셋 모두 포함
- 한 태스크 개정 시 다른 태스크 보존
- 순서 변경 지문 동일
- 충돌 dataset key 차단
- 태스크 삭제 시 새 계약 제외·기존 레코드 보존

### 4c-2 검토 요청 이벤트

ContractReviewGate가 `REVIEW_REQUIRED`일 때 Decision Ledger에 `APP_CONTRACT_REVIEW_REQUESTED`를 한 번 기록한다.

- 요청 이벤트 ID를 체크포인트/상태에 보관
- 요청 당시 compiled fingerprint, 이전 승인 fingerprint, 대상 태스크 목록 저장
- 동일 지문에 열린 요청이 있으면 중복 요청 생성 금지
- 기록 실패 시 그래프 진행 금지

### 4c-3 전용 승인·반려 API

권고 경로:

```text
GET  /api/v1/factory/{project_id}/contract-review/pending
POST /api/v1/factory/{project_id}/contract-review/decision
```

요청은 `request_event_id`, `decision=APPROVE|REJECT`, `rationale`만 받는다. 계약 지문·승인 지문·사용자 ID·tenant·scope는 서버가 파생한다.

필수:

- 현재 principal과 프로젝트 쓰기 권한 확인
- 열린 요청 이벤트 존재 확인
- 요청 당시 지문과 현재 체크포인트 지문 일치 확인
- 승인/반려 이벤트가 요청 이벤트를 `parent_event_id`로 참조
- 승인 시 상태 지문 봉인, 반려 시 승인 지문 제거
- 같은 요청의 두 번째 결정 409
- 타 사용자·타 scope 404/403 계약 유지

Decision Ledger를 SSOT로 한다. API가 Ledger를 먼저 기록하고 그래프는 Ledger 결정을 읽어 상태를 갱신한다. 그래프 재개 실패 때문에 승인 자체가 사라지면 안 된다.

### 4c-4 일반 HOTL 우회 차단

계약 검토 대기 상태에서는 기존 `/{project_id}/hotl/resume`가 409를 반환한다. 빈 피드백을 계약 승인으로 해석하지 않는다.

- 일반 산출물 HOTL은 기존 동작 유지
- 계약 검토는 전용 API만 사용
- 계약 결정 없이 Backend/Frontend 진입 불가

### 4c-5 비소급 회귀

- `LEGACY_OFF` 체크포인트는 예전 토폴로지로 재개
- `V1_ON` 신규 프로젝트만 HostContractCompiler/ContractReviewGate 진입
- `UNREADABLE`은 시작·재개 불가
- 기존 `completed_agents`가 새 노드 때문에 어긋나지 않음

### 4c-6 그래프 연결

권고 흐름:

```text
Tech_Lead
→ HostContractCompiler(비-LLM 결정론적 컴파일)
→ ContractReviewGate
   ├─ AUTO_PASS → Materialize/Code Builder
   ├─ REVIEW_REQUIRED → interrupt
   ├─ BLOCKED → 계약 오류 화면
   └─ NOT_APPLICABLE → 기존 경로
```

진행 중 프로젝트에 노드를 소급 삽입하지 않는다. `runtime_contract_profile`로 라우팅한다.

### 4c-7 실행 릴리스 최종 차단

유효하지만 잘못 분류된 `REPORT`가 실행 가능한 App-in-App으로 만들어져 계약을 피하는 경로를 닫는다.

```text
requires_contract =
    artifact_kind in {APP, SIMULATOR}
    OR release_output_is_executable_app_in_app
```

실행 가능한 릴리스는 승인 계약·물질화 지문이 없으면 proof 발급·ACTIVE 승격 모두 차단한다.

### Gate A

- 4c-0~7 개별 원자 커밋 또는 의미상 결합 가능한 최소 커밋
- 집중 회귀·변이 검사·전체 회귀 0 failed
- 일반 HOTL 계약 우회 0
- 다중 APP 계약 손실 0
- 레거시 소급 0

---

## 6. Wave B — I-4 5 Typed SDK·정적검사

설계 §20의 5단계를 구현한다.

필수:

- 생성 코드는 `window.afs.data.*`만 사용
- 자체 로그인·세션·토큰·직접 fetch/sql/db/mcp 금지
- Dataset Contract의 `allowed_actions`에 맞는 Typed Adapter 생성
- `AFS_NATIVE`만 create/update/delete Adapter 제공
- `ENTERPRISE_READ/FILE_SNAPSHOT/DERIVED_READ`는 read-only Adapter
- Host Service 미지원 기능은 `지원 대기`, 폴백 금지
- 정적 검사 실패 릴리스에 proof 발급 금지

Gate B:

- 금지 신호 변이 검출
- 계약 밖 메서드 생성 0
- 데이터셋 0개 앱도 명시적 빈 계약 보유
- 프런트 타입 검사·빌드 통과

---

## 7. Wave C — BDR-2 Kit Instance·Source Binding

정본: BDR 상세설계 §7·§8·§13·§14·§17·§18·§19.

### 7.1 신규 파일 구조

```text
core/data_preparation/
├─ models.py
├─ store.py
├─ kit_registry.py
├─ source_binding.py
├─ readiness_engine.py
├─ provider_dispatch.py
└─ baseline_builder.py

api/routes/data_preparation_control.py
tests/test_data_kit_runtime.py
tests/test_source_binding.py
```

`snapshot_service.py`는 Wave D에서 추가한다. 저장 DB는 `data/data_preparation.db` 하나로 시작하고 App Data·Ontology DB와 합치지 않는다.

### 7.2 BDR-201 DDL·마이그레이션

최소 테이블:

- `kit_registry_versions`
- `kit_instances`
- `source_bindings`
- `dataset_snapshots`
- `readiness_evaluations`
- `baseline_builds`

모든 운영 자원에 `tenant_id`, `scope_node_id`, `entity_mode`, 상태, 지문, 생성·변경 시각을 명시한다. 미지정 공용 기본값 금지.

### 7.3 BDR-202 Kit Registry

- `docs/data-kits`와 기계 Profile을 읽는 버전 로더
- 키트 원문 fingerprint
- 깨진 키트·모르는 버전 차단
- 템플릿은 운영 Data Contract가 아님

시연 등록 키트:

```text
kit_id: afs_materials_procurement_v1
name: 원료 구매·도입 경영 키트
mode: DEMO/SYNTHETIC
```

### 7.4 BDR-203 Kit Instance API

```text
GET  /api/v1/data-preparation/kits
GET  /api/v1/data-preparation/kits/{kit_id}/versions/{version}
POST /api/v1/data-preparation/instances
GET  /api/v1/data-preparation/instances/{id}
```

tenant는 선택 회사 문맥에서 서버가 파생한다. 명시 `scope_node_id`와 `entity_mode` 없이는 생성하지 않는다.

### 7.5 BDR-204 Source Binding

상태:

```text
DRAFT → VALIDATED → APPROVED → ACTIVE → RETIRED
                  ↘ BLOCKED
```

- 한 Kit Instance·Dataset Contract당 ACTIVE 하나만 DB 부분 유일성으로 보장
- 후보는 여러 개 허용
- 활성 교체는 기존 ACTIVE 종료와 신규 ACTIVE를 한 트랜잭션으로 처리
- `FILE_SNAPSHOT`, `AFS_NATIVE` 두 Provider를 MVP에서 지원
- `CONNECTOR_QUERY`는 계약·화면 자리만 두고 `지원 대기`

### 7.6 범위·감사

- G1-B PDP 위 ResourceScope 어댑터 사용
- 프로젝트 전용 visibility를 자체 판정기로 복제하지 않음
- 타 조직·tenant·entity mode는 404
- 판정 불가 503, 상태 충돌 409
- 성공·거부·실패 감사 이벤트 등록

Gate C:

- 새 DB 마이그레이션·재실행 멱등
- 명시 범위 없는 Instance 0
- 타 범위 존재·개수 누설 0
- ACTIVE 중복 0
- 키트 적용→결속 후보→검증→승인→활성 전이 통과

---

## 8. Wave D — BDR-3 L0 파일 Snapshot MVP

신규 파일:

- `core/data_preparation/snapshot_service.py`
- `tests/test_dataset_snapshot.py`

### 8.1 파일 등록

- 허용 형식은 시연용 CSV 우선, XLSX는 기존 파서가 안정적일 때만 추가
- 원본을 불변 RAW 영역에 저장
- SHA-256 checksum, 파일 크기, 행 수, 스키마 추정, 업로드 principal 기록
- 파일명·경로로 원천을 신뢰하지 않음
- 조회/파싱 실패를 0행 Snapshot으로 저장하지 않음

### 8.2 파이프라인

```text
RAW
→ PROFILED
→ STANDARDIZED
→ RECONCILED
→ CERTIFIED | QUARANTINED | REVOKED
```

- 결측·중복·분포·코드·단위 검사
- MDM/Crosswalk 미매핑 행 격리
- 원천 control total·행 수·금액 합계 대사
- 인증 후 원문·본문 UPDATE 금지
- 정정은 새 Snapshot 생성

### 8.3 시연용 인증 의미

실제 Data Owner가 없으므로 `CERTIFIED ACTUAL`을 주장하지 않는다.

- `knowledge/data_kind = DEMO/SYNTHETIC`
- 인증은 `DEMO_CERTIFIED` 또는 이에 준하는 제품 내 명시 상태
- REAL 기준선과 섞이지 않음
- 화면·API·보고서에 샘플임을 표시

### 8.4 최소 종단 3종

| 계약 | 파일 내용 | 대사 |
|---|---|---|
| PRC-02 | 구매주문 12건 | 주문금액·수량·납기 |
| INV-01 | 원료 재고 Snapshot | 품목·공장별 수량 |
| FIN-03 | 6개월 손익·현금 | 월별 합계·기초/기말 현금 |

나머지 MDD는 제공 Fixture를 같은 Snapshot 저장 경로로 로드하되, 실제 파일 인증을 했다고 표현하지 않는다.

Gate D:

- RAW checksum 재현
- 실패≠0행
- 잘림≠전체
- 미매핑·단위 오류 격리
- 원천 합계 대사
- 인증 후 수정 차단
- 타 범위 Snapshot 404

---

## 9. Wave E — BDR-5 최소 Readiness + BDR-6 Provider Dispatch

### 9.1 결정론적 준비도

최소 상태:

```text
NOT_CONFIGURED
SOURCE_CONFIGURED
DATA_AVAILABLE
QUALITY_FAILED
RECONCILIATION_FAILED
APPROVAL_PENDING
READY
STALE
UNAVAILABLE
```

응답에는 다음을 포함한다.

- 현재 가능한 기능
- 차단된 공식 결과
- 사용자에게 보이는 다음 행동
- 책임 역할
- 기준시점
- `context_omitted`만 허용하며 권한 밖 개수·사유는 미노출

`없음`, `못 읽음`, `승인 전`, `만료`를 서로 다른 상태로 유지한다.

### 9.2 Provider Dispatch

앱 표면은 `window.afs.data.*` 하나를 유지한다.

```text
AFS_NATIVE       → app_data.db
FILE_SNAPSHOT    → 승인된 data_preparation Snapshot
CONNECTOR_QUERY  → NOT_YET_SUPPORTED/지원 대기
DERIVED          → 승인된 계산 결과(후속 연결)
```

필수:

- 앱이 Provider 종류·원천 자격증명·실제 내부 ID를 받지 않음
- read 요청은 계약·Source Binding·Snapshot 상태·범위를 매 요청 대조
- Native 외 쓰기 403
- 원천 장애 시 빈 목록 금지
- 마지막 인증 Snapshot 사용 정책과 STALE 표기
- binding/snapshot 지문 변경 시 기존 proof 또는 frame 무효화

Gate E:

- 같은 SDK로 Native 보완 입력과 파일 Snapshot 조회
- 기업/파일 데이터 write 차단
- 준비도 동일 입력 동일 결과
- 권한 밖 존재·개수 미노출
- 장애·만료·승인 전 상태 오독 0

---

## 10. Wave F — I-4 6·7·8

### I-4 6 Release Candidate·Preview DB·Preview Proof

- Preview DB 물리 분리
- Candidate만 Preview proof 발급
- SYNTHETIC_TEST만 사용
- Preview/운영 proof audience 교차 사용 양방향 차단
- 파일 Snapshot은 시연용 복제/참조 정책을 명시하고 운영 기준선으로 승격하지 않음

### I-4 7 ACTIVE 원자 승격

- 계약·정적검사·Review·물질화·Snapshot Readiness를 한 번 더 검증
- ACTIVE 승격과 바인딩 전환 원자성
- 실패 시 이전 ACTIVE 보존
- 실행 가능한 App-in-App의 계약 누락 차단

### I-4 8 종단 카나리

```text
업무키트 선택
→ 계약 합산·승인
→ 데이터셋 물질화
→ 파일 Snapshot read + Native memo write
→ Preview
→ ACTIVE
→ 새 세션 실행
```

구조적으로 분리된 DB와 fresh worktree를 사용한다. 운영 DB에 카나리 쓰기 금지.

Gate F:

- 생성→Preview→ACTIVE→실행 완주
- 읽기·쓰기 허용/거부 양쪽 표본
- 계약·물질화·binding·snapshot 변경 stale 차단
- 운영 DB 지문 불변
- 전체 회귀·프론트 빌드·브라우저 카나리 통과

---

## 11. Wave G — BDR-7 Baseline·G2·G4·의사결정

### 11.1 Baseline Build

- 최신 포인터가 아니라 Snapshot ID 집합 고정
- 계약·범위·기준시점·품질·인증 상태 검증
- DEMO/SYNTHETIC Baseline임을 명시
- 동일 집합은 동일 fingerprint

### 11.2 G2 최소 연결

첫 경로만 구현/사용한다.

```text
원료 → 구매주문 → 선적·통관 → 입고·재고
    → 생산계획 → 제품 → 현금·손익
외부환경 지표 ──────────────┘
```

온톨로지는 Snapshot 본문을 복제하지 않고 Snapshot/원천 식별자와 관계 근거만 참조한다. 수치 계산은 G4가 담당한다.

### 11.3 G4 최소 계산

Driver:

- 환율 +10%
- 도입 지연 +14일
- 전력단가 +12%

결과:

- 생산량
- 기말재고
- 구매지급
- 기말현금
- 영업이익

동일 Baseline·가정·산식 버전은 동일 결과를 반환한다. LLM이 숫자를 만들지 않는다.

### 11.4 결정·보고

- 시뮬레이션 실행에서 의사결정 안건 생성
- 요청자·의사결정자·영향부서용 3관점 검토서
- 실행 책임자·기한
- 경영 브리핑에 질문·근거·기준선 대비 변화·권고 표시

Gate G:

- Snapshot ID→관계 근거→계산식→결과→회의 요청의 계보 재현
- 미승인 데이터·관계·산식 사용 0
- 동일 실행 3회 결과 동일
- 보고서의 수치가 계산 결과와 일치

---

## 12. Wave H — 최소 제품 화면과 시연 안정화

Claude Code 단독 수행이므로 화면은 시연 경로에 필요한 최소만 구현한다. 전면 디자인 개편은 금지한다.

필수 화면:

1. 기본 데이터 키트 목록
2. Kit Instance 상세/준비도 보드
3. Source Binding Drawer
4. Snapshot 품질·대사·인증 화면
5. Baseline 승인 요약
6. 생성 앱에서 출처·기준시점·품질 표시
7. Javis 데이터 준비 문맥

UI 규칙:

- 승인된 제품 셸·의미 토큰 재사용
- 기술 ID·slug 기본 노출 금지
- 본문 12px 미만 금지
- 조회 실패와 0건 구분
- 다음 행동과 전체 진행상태 동시 표시
- 샘플/합성/실제 상태를 색만으로 구분하지 않음
- Javis가 권한 밖·미지원 기능을 가능하다고 말하지 않음

Demo Reset과 Readiness Check를 제공한다. 핵심 시연은 외부 LLM·네트워크 실패에 의존하지 않도록 Fixture와 결정론적 계산으로 재현한다.

---

## 13. 15영업일 재배치 — Claude Code 단독 기준

날짜보다 선행관계를 우선하되, 매일 종료 시 다음 표를 갱신한다.

| 일차 | 단독 주 작업 | 최소 종료 조건 |
|---:|---|---|
| D1 | 4c-0 커밋, 4c-1 합산기 | 다중 APP 계약 보존 |
| D2 | 4c-2~4 계약 API·HOTL 차단 | 승인 우회 0 |
| D3 | 4c-5~7 그래프·릴리스 차단 | 신규만 계약 경로 진입 |
| D4 | I-4 5 SDK·정적검사 | 직접 인증/API 0 |
| D5 | BDR-2 DB·Kit Registry·Instance | 샘플 회사에 키트 적용 |
| D6 | BDR-2 Source Binding·PDP·감사 | FILE/Native 결속 활성화 |
| D7 | BDR-3 RAW·프로파일·표준화 | 3종 파일 파싱·격리 |
| D8 | BDR-3 대사·DEMO 인증 | PRC/INV/FIN 준비 |
| D9 | BDR-5 준비도·BDR-6 Dispatch | 같은 SDK로 두 출처 사용 |
| D10 | I-4 6 Preview | Preview 물리 격리 |
| D11 | I-4 7~8 ACTIVE·카나리 | 생성 앱 종단 완주 |
| D12 | Baseline·G2 최소 연결 | 영향 경로 재현 |
| D13 | G4·결정·브리핑 | 질문→결정 패키지 완주 |
| D14 | 최소 UI·Reset·Readiness·역할 E2E | 12분 동선 1회 완주 |
| D15 | 결함 수정·3회 연속 리허설·동결 | 치명 결함 0 |

### 일정 방어선

- D4 지연: 라이브 자유형 생성 제외, 승인된 원료 구매 템플릿 사용
- D8 지연: 실제 Connector 전부 제외, 검증 파일 Snapshot만 사용
- D11 지연: 온톨로지 자연어 자유질의 제외, 고정 Intent 3종 사용
- D13 지연: 보고서 1종과 경영 브리핑만 유지
- 절대 자르지 않음: Host Runtime 경계, 데이터 역할·출처 표시, Snapshot 불변성, 계산 재현성, 권한 누설 방지

---

## 14. 커밋·테스트·작업트리 규율

### 커밋

- 각 Wave 또는 하위 게이트를 원자 커밋
- 커밋 전에 `git diff --cached`로 본인 파일만 확인
- 다른 세션 미커밋 문서·보드·DB 백업·산출물 포함 금지
- 새 내부 모듈을 import하는 코드와 그 모듈은 같은 커밋
- 실패한 기준선을 커밋해 다음 단계로 넘기지 않음
- origin은 사용자 명시 지시 전까지 건드리지 않음

### 테스트

각 단계에서 다음을 기록한다.

1. 해당 기능 집중 회귀
2. 변이 또는 반대 구현 대조
3. 전체 `tests` 회귀
4. TypeScript 타입 검사·프론트 빌드(프런트 영향 시)
5. 브라우저/HTTP 종단(라우트·UI 영향 시)
6. 깨끗한 checkout 재현(Gate A·F·G)
7. 운영 DB·정책 파일 지문 불변

테스트 환경 격리에 실패하면 즉시 실패한다. 운영 조직/프로젝트/DB가 비어 있어 bootstrap 권한으로 통과하는 시험을 만들지 않는다.

### 운영 데이터

- 운영 DB 마이그레이션 금지
- 운영 DB는 읽기 전용 실측만
- 마이그레이션은 사본에서 검증
- 카나리는 별도 worktree·별도 DB·`AFS_TEST_SANDBOX`
- DEMO/SYNTHETIC을 Actual로 승격하지 않음

---

## 15. 중단 조건

다음 중 하나라도 참이면 다음 Wave로 넘어가지 않는다.

1. 프로필·scope·tenant·entity mode 판독 실패가 통과됨
2. 일반 HOTL로 계약 검토를 우회할 수 있음
3. APP 여러 개 중 하나의 Dataset Contract가 사라짐
4. 기업/파일 데이터에 create/update/delete가 열림
5. 조회 실패가 0건 Snapshot 또는 빈 목록으로 저장됨
6. 인증 전 Snapshot이 Baseline·G2·G4에 들어감
7. Preview와 운영 DB/Proof가 교차 사용됨
8. LLM이 경영 수치를 직접 생성함
9. 권한 밖 객체·결속·Snapshot의 존재·개수가 응답에 드러남
10. 테스트가 운영 DB·조직·projects 폴더에 쓰기
11. 전체 회귀 빨강 또는 깨끗한 checkout에서 재현 불가

---

## 16. 완료 보고 형식 — 매번 잔여사항 포함

Claude Code는 매 완료 보고에 아래 형식을 사용한다.

```text
[작업] ID·이름
[이유] 어떤 제품 위험/시연 차단을 닫았는가
[변경] 파일·DB·API·상태 전이
[판단] 설계와 달라진 점·왜 달랐는가
[검증] 집중/변이/전체/프론트/브라우저/DB 불변
[커밋] ID · push 여부
[남은 위험] 확인하지 못한 것과 영향
[다음] 다음 작업·착수 조건
```

진척은 반드시 다음처럼 전체를 표시한다.

```text
I-4 4c 안전한 그래프       ░░░░░░░░░░  0/8
I-4 5 SDK·정적검사         ░░░░░░░░░░  0/1
BDR-2 Kit/Binding          ░░░░░░░░░░  0/6
BDR-3 File Snapshot        ░░░░░░░░░░  0/6
BDR-5 Readiness 최소       ░░░░░░░░░░  0/3
BDR-6 Provider Dispatch    ░░░░░░░░░░  0/5
I-4 6~8 승격·카나리        ░░░░░░░░░░  0/3
BDR-7 G2/G4 폐루프         ░░░░░░░░░░  0/5
제품 화면·시연 안정화       ░░░░░░░░░░  0/5

전체 시연 경로             ░░░░░░░░░░  0/1
```

퍼센트만 보고하지 않는다. 완료 분자·분모가 늘면 이유를 적는다.

---

## 17. 현재 진척 기준선

```text
I-4 1~3 기반               ██████████  완료
I-4 4a·4b                  ██████████  완료
I-4 4c-0                   ██████████  구현·회귀 완료 / 원자 커밋 대기
I-4 4c-1~7                 ░░░░░░░░░░  미착수
I-4 5~8                    ░░░░░░░░░░  미착수
BDR-1 의미·중복입력 계약    ██████████  완료
BDR-2~3 업무키트 런타임     ░░░░░░░░░░  미착수
BDR-5~7 시연 폐루프         ░░░░░░░░░░  미착수

표준 12분 시연 종단         ░░░░░░░░░░  미완
```

다음 행동은 **4c-0 원자 커밋 → 4c-1 프로젝트 단위 계약 합산기**다.

---

## 18. Claude Code 수신 확인 양식

Claude Code는 이 문서를 읽은 직후 `.agents/TEAM_BOARD.md` 또는 자신의 다음 작업 보고에 아래를 남긴다. 공유 보드가 다른 세션에서 수정 중이면 파일을 충돌시키지 말고 보고문에 먼저 남긴 뒤 다음 안전한 커밋에서 반영한다.

```yaml
reader: Claude Code
read_at: YYYY-MM-DD HH:MM KST
handoff_id: CLAUDE-SOLO-I4-BDR-MVP-20260816-01
read_full_handoff: true
parallel_development: paused
single_implementer: Claude Code
current_task: I-4 4c-0 commit then 4c-1
current_base_commit: d3df38d21
owned_dirty_files:
  - api/routes/factory_control.py
  - core/wbs_artifact_kind.py
  - tests/test_runtime_contract_profile.py
next_sequence:
  - I-4 4c-0~7
  - I-4 5
  - BDR-2
  - BDR-3
  - BDR-5 minimum
  - BDR-6
  - I-4 6~8
  - BDR-7/G2/G4/demo loop
origin_operations: forbidden_until_supervisor_instruction
```

