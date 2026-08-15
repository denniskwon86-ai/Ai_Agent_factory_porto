# 팀 공통 인수인계 — 데이터 연결·준비 런타임

> 인계 ID: `BDR-HANDOFF-01`  
> 작성자: Codex  
> 작성 시각: 2026-08-15 15:17 KST  
> 대상: Supervisor · Claude Code · Gemini Antigravity · Codex 및 후속 팀원/LLM  
> 상태: 상세설계 완료 · **BDR-1(=I-4 2.2/2.2a) 구현 완료 · BDR-2~7 미착수**  
> ⚠️ 2026-08-15 갱신: 이 문서가 「즉시 할 일」로 적은 BDR-1 은 끝났다. 계약 Schema·Compiler 결정표·이중 입력 게이트·물질화 검증·두 지문 봉인(I-4 3단계)까지 커밋돼 있다.  
> 정본 설계: `docs/architecture/BUSINESS_DATA_BINDING_RUNTIME_DETAILED_DESIGN_2026-08-15.md`  
> 기계 계약: `docs/architecture/business_data_binding_contract_v1.schema.json`  
> 예시 Profile: `docs/architecture/first_vertical_data_binding_profile_v1.example.json`

---

## 0. 재개하는 팀원은 여기부터 읽는다

1. `docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md` §4·§5·§7
2. `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md` §4.1~4.6·§8
3. `docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md` G1-B·G1-D·G2-B~D·G4
4. `PROGRESS.md`
5. `docs/handoff/I4_HOST_RUNTIME_HANDOFF_2026-08-15.md`
6. 본 인수인계
7. 정본 상세설계와 JSON Schema

### 착수 전 네 문항

| 질문 | 답 |
|---|---|
| 로드맵 권고 착수와의 관계 | G2-B 데이터 키트, G2-D MVA, G1-D 안전 연계의 구현 연결부 |
| 관문 | G2 주관, I-4/G3와 G4의 선행 계약 |
| 첫 수직 폐루프에 직접 필요한가 | 예. 실제·승인 데이터 기준선 없이는 원료 도입→손익 폐루프가 데모에 머묾 |
| 왜 지금 설계했는가 | 사용자 명시 지시 + I-4 생성기 계약이 데이터 출처 구분 없이 물질화되기 전에 중복 입력 방지 계약을 고정해야 함 |

---

## 1. 사용자 결정과 문제 정의

Supervisor가 확정한 제품 방향은 다음과 같다.

- 현업 앱의 데이터만 있어야 돌아가는 시스템으로 만들지 않는다.
- ERP·MES·WMS·기존 외부 협업 시스템을 모두 비싼 EAI로 선연결하지 않는다.
- 기존 시스템이 보유한 데이터를 AFS에서 다시 입력시키지 않는다.
- 사용자는 맨땅에서 시작하지 않고, 업종·업무별 기본 데이터 키트를 그대로 따라 준비한다.
- 데이터가 부족해도 가능한 범위와 다음 행동을 시스템이 먼저 제안한다.
- AFS 업무 앱은 원천에 없는 결손, 예외 판단, 시나리오, 실행·효과 데이터를 보완한다.
- 공식 경영 시뮬레이션은 승인된 Snapshot·계약·산식·버전으로 재현한다.
- 통합 수준은 L0 파일부터 시작하고 ROI가 확인될 때만 L1~L3로 올린다.

### 제품 메시지

> 기존에 있는 데이터는 가장 낮은 비용으로 재사용하고, 없는 데이터만 현업 앱으로 보완합니다. 어디서 온 데이터든 같은 계약·의미·품질·계보로 관리하여 실제 경영 질문과 시뮬레이션에 연결합니다.

---

## 2. 현재 저장소 상태와 충돌 주의

이 문서를 처음 쓴 시점의 기준 HEAD는 `cd6d539fa`(I-4 2.1b)였다. ⚠️ **그 뒤로 옮겨졌다** — 2.2(BDR-1) · 2.2a · 3단계가 차례로 커밋됐고, `docs/handoff/I4_HOST_RUNTIME_HANDOFF_2026-08-15.md` 기준 **4~8단계가 미착수**다. 인계 작성 중 수정되던 I-4 제품 소스는 현재 깨끗해졌으며, 공유 `.agents/TEAM_BOARD.md`와 여러 문서·산출물만 다른 팀원 변경과 함께 미커밋 상태다.

이 최신 상태는 BDR-1을 넣기 가장 저렴한 시점이다. I-4 3단계는 계약 지문과 물질화 지문을 증명에 봉인하므로, 그 전에 `source_intent`, `data_role`, `duplicate_entry_policy`를 계약 의미에 넣어야 한다.

### 금지

- 다른 세션이 I-4 3단계를 다시 시작했는지 `git status`와 최신 인수인계부터 확인한다.
- ~~I-4 3단계 계약 지문 봉인을 먼저 완료한 뒤 `source_intent`를 넣지 않는다.~~ **(해소됨 — 2.2 → 2.2a → 3단계 순서로 진행해 지문을 한 번만 바꿨다.)**
- 다른 팀원의 작업을 되돌리거나 선택적으로 import해 깨진 HEAD를 숨기지 않는다.
- origin push는 사용자 명시 지시 없이 하지 않는다.

### 안전한 적용 시점

1. 최신 I-4 인수인계에서 **어느 단계까지 끝났는지** 먼저 확인한다(이 문서보다 그쪽이 새롭다)
2. **BDR-1을 I-4 2.2 보강으로 별도 커밋**
3. 계약 Schema·Compiler·승인 초기화·레거시 분류 회귀 확인
4. I-4 3단계에서 확장된 계약 지문과 물질화 지문을 함께 증명에 봉인
5. old proof·stale frame·재승인 회귀와 함께 검증

---

## 3. 핵심 설계 결정 12개

1. **Source-independent**: 앱은 출처를 모르고 Host Runtime 데이터 표면만 사용한다.
2. **No duplicate input**: 기존 권위 원천이 있으면 AFS 입력 UI와 create/update를 차단한다.
3. **Progressive integration**: L0 파일→L1 예약→L2 API/MCP→L3 EAI/CDC 순으로 ROI에 따라 승격한다.
4. **Snapshot-first**: 공식 계산은 live query가 아니라 승인 불변 Snapshot을 고정한다.
5. **Gap-only native**: AFS Native는 결손·예외·시나리오·실행 결과를 보완한다.
6. **Template≠Operational contract**: 제품 키트 템플릿과 회사별 운영 Data Contract를 분리한다.
7. **Data role separation**: Actual/Plan/Forecast/Supplement/Scenario/Reference/Derived를 섞지 않는다.
8. **Fail-closed scope**: tenant/scope/entity mode 미지정·판독 실패는 공용이 아니라 비노출이다.
9. **No silent empty**: 원천 장애·권한 실패·품질 실패를 0건으로 접지 않는다.
10. **MDD first**: 35개 전체가 아니라 첫 경영 질문을 완주하는 Minimum Decision Dataset부터 연결한다.
11. **Reuse before interface**: 앱마다 I/F를 만들지 않고 Connector/Query Contract와 Snapshot을 재사용한다.
12. **Deterministic official result**: 동일 Snapshot Set·계산 계약·가정이면 동일 결과를 재현한다.

---

## 4. 구현 우선순위와 담당

역할은 강점 기반 기본 배치이며 배타적 경계가 아니다. Supervisor가 언제든 교대·교차검토를 지정할 수 있다.

### 4.1 Claude Code — 주 구현

#### ✅ 완료: BDR-1 (I-4 2.2 · 2.2a)

⚠️ 아래는 **한 일의 목록**이다. 다시 하지 않는다.
판정·상수는 `core/business_data_semantics.py` 한 곳에 있고 계약 계층과 물질화 계층이 같은 함수를 부른다(2.2a — 두 곳에 적었더니 세 조합이 갈라졌다).

1. `core/app_runtime_contract.py`
   - Dataset Schema에 `data_role`, `source_intent`, `duplicate_entry_policy` 추가
   - 선택 필드 `enterprise_contract_key`, `required_freshness`
   - 닫힌 목록 상수 추가
   - 의미 지문 입력에 포함
2. `core/host_contract_compiler.py`
   - Source Intent 결정표
   - `ENTERPRISE_READ`, `EXTERNAL_REFERENCE`, `DERIVED_READ`는 현재 `HOST_SERVICE_REQUIRED`
   - `AFS_NATIVE`만 현재 물질화 허용
   - 알려지지 않은 Source Intent fail-closed
3. 정적·계약 검사
   - 기업 읽기 데이터셋의 입력 UI/create/update 금지
   - 원천 직접 API/DB/MCP 코드 금지
4. 테스트
   - 지문 변이
   - 계약 이전 상태 호환
   - 승인 초기화
   - 입력 UI 차단
   - 조용한 AFS_NATIVE 폴백 부재

#### 후속: BDR-2~BDR-7

- `core/data_preparation/` 패키지와 API
- Kit Instance·Source Binding·Snapshot·Readiness·Baseline
- 승인 제품 셸 기반 검증용 UI
- Host Runtime Provider Dispatch
- G2/G4 종단 테스트

### 4.2 Codex — 제품·UX·교차검토

1. 데이터 키트 선택→회사 데이터 준비→원천 결속→품질·대사→기준선 승인 UX 상세화
2. 승인 제품 셸 기반 프로토타입
3. 다음 표현을 시각 감사
   - 없음 vs 조회 실패 vs 승인 전 vs 만료
   - 샘플/합성 vs 실제/인증
   - 기존 원천 vs 보완 입력
   - 지금 가능한 기능 vs 막힌 공식 결과
4. Claude 구현의 이중 입력·옥상옥·BI화 위험 교차검토
5. 경영자·현업 메시지와 90일 파일럿 지표 연결

### 4.3 Gemini Antigravity — 데이터·외부 원천·독립 검증

1. 첫 수직 폐루프 Source Inventory 후보 조사
2. 신뢰 가능한 외부지표 원천·공표주기·수정판·라이선스 정리
3. L0/L1/L2/L3 비용·효익 측정 양식
4. Quick/Full 데이터의 품질·대사·합성 오염 감사
5. 종단 카나리에서 데이터 손실·누설·오분류·0건 오독 검증

### 4.4 Supervisor — 제품·운영 결정

1. 첫 실제 적용 조직·업무·Sponsor
2. 각 Dataset Data Owner와 승인 책임
3. 실제 원천 후보와 접근 승인
4. 공식 결과 허용 오차·최신성·보존기간
5. L2/L3 비용 승인과 중단 기준

실제 Data Owner가 아직 없어도 REFERENCE/SYNTHETIC 구현은 진행한다. 다만 CERTIFIED ACTUAL은 발급하지 않는다.

---

## 5. 구현 백로그

### BDR-1 — I-4 Source Intent와 이중 입력 차단

| ID | 작업 | 완료 기준 |
|---|---|---|
| BDR-101 | Contract Schema 필드 추가 | JSON Schema·Compiler·상태 round-trip |
| BDR-102 | Source Intent 결정표 | 미지원 출처가 HOST_SERVICE_REQUIRED |
| BDR-103 | Zero Duplicate Entry Gate | 기업 Actual 입력 UI/SDK 금지 |
| BDR-104 | 지문·승인 연계 | 필드 변경 시 승인 초기화·old proof 차단 준비 |
| BDR-105 | 레거시 보고 | 미분류 계약 수·영향 보고, 자동 Actual 승격 0 |

### BDR-2 — 저장소·범위·키트

| ID | 작업 | 완료 기준 |
|---|---|---|
| BDR-201 | `data_preparation.db` DDL | 새 DB에서 생성·마이그레이션·멱등 |
| BDR-202 | Kit Registry | 버전·fingerprint·깨진 키트 차단 |
| BDR-203 | Kit Instance API | 명시 scope 없이 생성 불가 |
| BDR-204 | Source Binding 전이 | 후보→검증→승인→활성 트랜잭션 |
| BDR-205 | ResourceScope/PDP | 타 조직 404, 미바인딩 fail-closed |
| BDR-206 | 감사 | 성공·거부·실패 사건 화이트리스트 등록 |

### BDR-3 — L0 Snapshot MVP

| ID | 작업 | 완료 기준 |
|---|---|---|
| BDR-301 | 승인 파일 수집 | 원본 불변·checksum·row count |
| BDR-302 | 프로파일러 | 결측·중복·분포·코드·단위 |
| BDR-303 | Field/Crosswalk 매핑 | 미매핑 격리, 임의 추정 0 |
| BDR-304 | Reconciliation | control total·허용 오차 |
| BDR-305 | Data Owner 인증 | Decision Ledger·판 불변성 |
| BDR-306 | 최소 3종 종단 | PRC-02·INV-01·FIN-03 |

### BDR-4 — Connector Snapshot

| ID | 작업 | 완료 기준 |
|---|---|---|
| BDR-401 | Adapter Reference Profile | 특정 LPL 하드코딩 없음 |
| BDR-402 | Query Contract→Snapshot | 요청·응답·범위·목적 강제 |
| BDR-403 | 오류 의미 | 실패≠0행, 잘림≠전체 |
| BDR-404 | 재사용 지표 | 동일 원천 소비처 수 측정 |

### BDR-5 — Readiness·UI

| ID | 작업 | 완료 기준 |
|---|---|---|
| BDR-501 | Dataset 준비도 판정 | 동일 입력 동일 판정 |
| BDR-502 | Output 준비도 | 기능별 AVAILABLE/BLOCKED |
| BDR-503 | 준비 보드 | 사용자 다음 행동·책임자·기준시점 |
| BDR-504 | Javis 문맥 | 권한 내 설명, 임의 승인 0 |
| BDR-505 | 육안·자동 감사 | 1280×720·1440×900, 12px 이상, 오독 0 |

### BDR-6 — Host Runtime Provider

| ID | 작업 | 완료 기준 |
|---|---|---|
| BDR-601 | Provider Dispatch | 앱은 SDK 표면 하나만 사용 |
| BDR-602 | Snapshot 읽기 | 승인 판만, 기준시점 노출 |
| BDR-603 | 쓰기 강제 | Native 외 403 |
| BDR-604 | Proof 결속 | 계약·물질화·binding 지문 변경 차단 |
| BDR-605 | 원천 장애 | 마지막 인증 판 정책·UNAVAILABLE |

### BDR-7 — G2/G4 폐루프

| ID | 작업 | 완료 기준 |
|---|---|---|
| BDR-701 | Baseline Build | Snapshot ID 집합 고정 |
| BDR-702 | 온톨로지 참조 | 근거·as-of·source lineage |
| BDR-703 | 계산 그래프 | 미승인 산식·계수 차단 |
| BDR-704 | 경영 결과 | 재고·생산·매출·현금·손익 |
| BDR-705 | 결정·실행 | 회의 요청·3관점 검토서·효과 측정 |

---

## 6. BDR-1 구현 상세 — Claude Code 즉시 사용

### 6.1 기존 I-4 Dataset Schema 보정

현재 `_DATASET_SCHEMA.additionalProperties=False`이므로 필드를 Schema에 넣지 않으면 Compiler 입력이 거부된다. 다음 필드는 `required`로 두되 레거시 상태 승격은 별도 migration에서 명시적으로 처리한다.

```python
DATA_ROLES = (
    "ENTERPRISE_ACTUAL",
    "OPERATIONAL_PLAN",
    "OPERATIONAL_FORECAST",
    "NATIVE_SUPPLEMENT",
    "SCENARIO_INPUT",
    "DERIVED_RESULT",
)

SOURCE_INTENTS = (
    "AFS_NATIVE",
    "ENTERPRISE_READ",
    "EXTERNAL_REFERENCE",
    "DERIVED_READ",
)

DUPLICATE_ENTRY_POLICIES = (
    "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS",
    "ALLOW_SUPPLEMENT_ONLY",
    "NO_DUPLICATE_CHECK_REQUIRED",
)
```

### 6.2 Compiler 의사코드

```python
def classify_dataset(raw):
    source_intent = require_closed_value(raw, "source_intent", SOURCE_INTENTS)
    data_role = require_closed_value(raw, "data_role", DATA_ROLES)
    duplicate_policy = require_closed_value(
        raw, "duplicate_entry_policy", DUPLICATE_ENTRY_POLICIES)

    if source_intent == "AFS_NATIVE":
        if data_role == "ENTERPRISE_ACTUAL":
            error("기업 Actual은 명시적 원천 결속 없이 AFS Native로 만들 수 없습니다.")
        return SUPPORTED

    if any(action in raw.allowed_actions for action in ("create", "update", "delete")):
        error("기업/외부/계산 데이터는 읽기 전용이어야 합니다.")

    return HOST_SERVICE_REQUIRED
```

### 6.3 필수 회귀

1. `ENTERPRISE_READ + read` → HOST_SERVICE_REQUIRED
2. `ENTERPRISE_READ + create` → Compiler error
3. `AFS_NATIVE + NATIVE_SUPPLEMENT + create` → SUPPORTED
4. `AFS_NATIVE + ENTERPRISE_ACTUAL` → error
5. 알 수 없는 Source Intent → fail-closed
6. Source Intent 변경 → semantic fingerprint 변경
7. Duplicate policy 변경 → semantic fingerprint 변경
8. 기존 승인 계약에 필드 변경 → approval PENDING
9. 직접 API/DB/MCP 생성 신호 → 정적 검사 실패
10. 데이터셋 0개 앱도 계약이 존재하고 통과

### 6.4 변이 검사

- Source Intent 검사 제거
- read-only 강제 제거
- AFS Native Actual 금지 제거
- unknown fallback을 SUPPORTED로 변경
- fingerprint projection에서 새 필드 하나씩 제거
- `additionalProperties` 허용

각 변이가 최소 1개 시험을 실패시켜야 한다.

---

## 7. API·DB 구현 규율

1. 판정 함수는 한 곳에 둔다. Route가 같은 규칙을 다시 계산하지 않는다.
2. 존재 판정 전에 PDP를 실행해 이름 열거를 막는다.
3. 후보 여러 개는 허용하되 ACTIVE 유일성은 DB 부분 인덱스로 지킨다.
4. 상태 전이·감사·승인은 하나의 트랜잭션으로 묶는다.
5. 인증 판은 UPDATE하지 않고 새 판을 만든다.
6. 조회 실패·어댑터 없음·판정 실패는 빈 목록으로 반환하지 않는다.
7. 권한 밖 건수·미승인 자원 건수는 사용자 응답에 넣지 않는다.
8. 운영 DB 마이그레이션 전 사본에서 실측하고 원본 지문 불변을 확인한다.
9. 테스트는 제품과 같은 Principal·scope·session을 구성한다.
10. 코드가 참조하는 신규 내부 모듈은 같은 원자 커밋에 포함한다.

---

## 8. 팀 교차검토 요청

### Claude Code가 Codex에게 요청할 것

- Source Intent와 데이터 역할이 현업 언어로 이해되는가
- 기존 원천이 있을 때 입력 UI가 실제로 사라지는가
- 데이터 부족 시 기능·다음 행동이 과장 없이 보이는가
- 데이터 준비 보드가 또 하나의 관리자 BI 화면처럼 보이지 않는가

### Claude Code가 Antigravity에게 요청할 것

- 첫 MDD의 필드·최신성·대사 규칙이 실제 원천에 적용 가능한가
- L0/L1/L2/L3 비용·운영 가정이 현실적인가
- 합성/REFERENCE/Actual 오염 경로가 없는가

### Codex·Antigravity가 Claude Code에게 요청할 것

- 판정·상태·DB 제약이 실제 코드에서 한 곳에 있는가
- 테스트가 구현을 실제로 검출하는가
- 기존 I-4/G1-B 보안 경계를 약화시키지 않는가

교차검토는 구현자의 자가검토를 금지하지 않는다. P0 보안·데이터 승격·핵심 API는 병합/강제 전 최소 한 명의 독립 검토를 받되, 낮은 위험의 문서·UI 개선은 사후 검토 부채로 진행할 수 있다.

---

## 9. 카나리 계획

### 9.1 격리 구조

- fresh worktree
- 별도 `data_preparation.db`, `app_data.db`, catalog DB
- `AFS_TEST_SANDBOX` + SANDBOX entity mode
- 운영 Connector 자격증명·운영 DB 접근 없음
- 샘플 회사 Quick Dataset

### 9.2 카나리 시나리오

1. L0 구매주문 파일→RAW→대사→인증
2. L2 Reference Connector 선적 사건→Snapshot
3. AFS Native Scenario 입력
4. 기존 Actual이 있는 필드의 AFS 중복 입력 차단
5. 필수 FIN-03 미인증 상태에서 공식 손익 차단
6. 인증 후 기준선 생성·G4 계산
7. Connector 장애 후 마지막 인증 판 사용
8. Snapshot 만료 후 STALE·다음 행동
9. 타 조직·VIRTUAL/SANDBOX 누설 차단
10. 현업 앱 미사용 상태에서도 기존 Actual 기준선 유지

### 9.3 증거

- 계약·binding·snapshot·baseline 지문
- HTTP와 UI 결과
- audit event
- readiness result
- 원천 대사 보고서
- 운영 DB 불변 지문
- 예상 I/F 비용과 실제 투입시간

---

## 10. 완료·차단·보류 정의

### 완료

- 정본 설계의 완료 판정 10개 충족
- 전체 회귀·집중 회귀·변이·브라우저 카나리 통과
- 다른 팀원이 대화 없이 정본 문서만 읽고 같은 다음 3개 작업을 제시

### 차단

- G1-B PDP/Host Proof가 우회됨
- Source Intent가 AFS Native로 폴백
- SYNTHETIC/SANDBOX가 공식 Actual/Baseline에 혼입
- 원천 장애가 0건으로 표시
- Snapshot 지문·승인·계보 없이 공식 계산

### 보류 가능

- 실제 Data Owner 승인 부재: CERTIFIED ACTUAL만 보류, 기능 구현은 REFERENCE/SYNTHETIC으로 진행
- 실제 LPL/ERP 연계 부재: 범용 Connector Reference Profile과 L0 파일로 진행
- L3 write-back: 첫 수직 폐루프 필수 아님

---

## 11. 교대 체크포인트

- 마지막 확인 상태: 상세설계·JSON Schema·첫 수직 Profile·팀 인수인계 작성 완료
- 변경 범위: 문서와 팀보드만. 제품 코드·DB·API·테스트 수정 0
- 검증: Product Bible·전략·로드맵·I-4 인수인계·데이터 키트·현행 Connector/Catalog/App Data/External/Baseline 코드 대조
- 커밋/푸시: 미실시. origin 변경 금지 유지
- 첫 재개 행동: HEAD·작업트리를 다시 확인하고 I-4 3단계가 여전히 미착수면 BDR-1을 I-4 2.2 보강으로 먼저 구현할 영향 파일 diff·테스트 계획 보고
- 금지 범위: 새로 시작된 I-4 미커밋 변경과 혼합, I-4 3단계 선행 후 의미 계약 재수정, 기존 Actual 재입력 UI 생성, 범위 미지정 공용 처리, live query의 공식 계산 직결, 샘플 데이터 Actual 승격
