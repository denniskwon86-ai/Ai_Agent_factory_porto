# 외부 협업 레거시 시스템 연계 표준 설계

> 상태: 제품 공통 SSOT 1.0  
> 기준일: 2026-08-03  
> 결정권자: Supervisor  
> 작성: Codex  
> 적용 대상: 거래처·협력사·관세사·포워더·운송사·검사기관 등 외부 참여자가 사용하는 고객사 기존 시스템

---

## 1. 제품 정체성과 비협상 경계

AI Factory Studio는 업무 편의를 위한 범용 자동화 포털이 아니라 **회사의 실제 경영 데이터를 연결하고, 경영 시뮬레이션·의사결정·실행 효과를 관리하는 내부 경영 시스템**이다.

따라서 다음을 비협상 원칙으로 한다.

1. AI Factory Studio를 외부 인원에게 개방하지 않는다.
2. 외부 사용자 계정, 게스트 조직, 파트너용 앱 주머니와 입력 화면을 만들지 않는다.
3. 외부 참여자의 인증·입력·원본 업무 사건은 고객사가 이미 운영하는 외부 협업 레거시 시스템이 책임한다고 전제한다.
4. AI Factory Studio는 기존 시스템을 교체하지 않고 승인된 읽기 전용 Connector 계약으로 필요한 데이터만 받는다.
5. 고객사별 시스템 이름·스키마·인증 방식을 제품 코어에 하드코딩하지 않는다.
6. LPL(LS Partner's Lounge)은 LS 환경의 첫 Reference Profile이며 제품 기능명이나 공통 데이터 모델이 아니다.

외부 협업 시스템이 없는 고객은 내부 직원이 승인된 파일을 등록하거나 고객사·ITO가 별도 외부 포털을 제공해야 한다. 이를 이유로 AI Factory Studio의 보안 경계를 외부로 확장하지 않는다.

---

## 2. 목표 아키텍처

```text
외부 참여자
  ↓ 고객사 기존 화면에서 입력
External Engagement System
  (Partner Portal / Customs / Logistics / Supplier Portal 등)
  ↓ Read-only API·MCP·DB View·Export
Connector Registry + Query Contract
  ↓ 범위·필드·행·목적·감사 강제
Adapter Profile
  ├─ 온디맨드 조회 → 내부 운영 앱의 현재 상태
  └─ 증분/Snapshot → RAW·표준화·대사·CERTIFIED Actual
                         ↓
       Management Twin·Decision Package·경영 보고
```

AI Factory Studio는 외부 업무를 실행하는 원천 시스템이 아니라 여러 운영 시스템의 데이터를 경영 의미와 영향 경로로 연결하는 상위 지능·통제 계층이다.

---

## 3. 책임 분리

| 책임 | 기존 외부 협업 시스템 | AI Factory Studio |
|---|---|---|
| 외부 사용자 인증·계정·약관 | 진실 원천 | 보유 금지 |
| 외부 입력 UI·첨부·수정 | 수행 | 중복 구현 금지 |
| 외부 제출 원본·감사 | 진실 원천 | 원천 참조·버전 보존 |
| 고객사 내부 조직·권한 | 필요 시 조직코드 제공 | ECM·권한 진실 원천 |
| 내부 기준정보·표준 의미 | 원천코드 제공 | MDM·Crosswalk 관리 |
| 내부 업무 앱 | 연계 대상 | 생성·실행·권한 관리 |
| 경영 계산·시나리오 | 비대상 또는 참고 | 결정론적 Twin |
| 의사결정·효과 측정 | 원천 사건 제공 | Decision Ledger·폐루프 |

원천 시스템이 업무상 확정한 값이라도 경영 계산에 즉시 사용할 수 있는 것은 아니다. 내부 업무키 연결, 기간·단위·상태, 원천 대사와 데이터 오너 승인 규칙을 통과해야 한다.

---

## 4. 제품 공통 모델과 고객사 Profile 분리

### 4.1 제품 코어

제품 코어에는 다음 일반 개념만 존재한다.

- `connector`
- `query_contract`
- `adapter_profile`
- `source_system_id`
- `source_entity`, `source_event_id`, `source_version`
- `source_as_of`, `occurred_at`, `updated_at`, `received_at`
- `source_sync_contract`, `source_sync_run`, `source_snapshot`
- `crosswalk`, `reconciliation`, `certification`

코어에 `lpl_*`, 특정 ERP 테이블명, 특정 회사 조직코드를 만들지 않는다.

### 4.2 고객사 Adapter Profile

고객사별 차이는 설정·계약·어댑터로 격리한다.

```text
profiles/
  ls_lpl/
    connector_profile.json
    query_contracts.json
    field_crosswalk.json
    status_mapping.json
    fixtures/

  customer_b_supplier_portal/
    ...
```

Profile에는 다음만 둔다.

- 시스템 표시명과 kind(API/MCP/DB/File)
- endpoint의 Secret 참조
- 논리 계약→원천 엔터티·필드 매핑
- 상태·코드 Crosswalk
- pagination/cursor/update semantics
- 허용 조직 범위와 데이터 등급
- fixture와 계약 테스트

제품 로직을 고객사별 `if company == ...`로 분기하지 않는다.

---

## 5. 고객 온보딩 발견 절차

새 고객사에서는 외부 참여자가 사용할 시스템이 존재한다고 전제하되 실제 연결 방식은 조사한다.

### 업무 발견

- 어떤 외부 주체가 어떤 데이터를 입력하는가?
- 어느 시스템이 원본 업무 사건의 진실 원천인가?
- 내부 직원은 어느 시스템에서 검토·확정하는가?
- 정정·취소·분쟁이 어떻게 처리되는가?

### 기술 발견

- REST/GraphQL/SOAP API 또는 MCP 제공 여부
- Read-only DB View/Replica 가능 여부
- 정기 Export 형식·주기·전달 위치
- 인증(mTLS/OAuth2/API Key/서비스 계정)
- 테스트 환경·샘플 응답·운영 SLA
- Primary Key, 사건 ID, 버전, 수정시각
- pagination, rate limit, cursor, webhook
- 스키마 변경·장애 공지 절차

### 거버넌스 발견

- 데이터 오너와 시스템 오너
- 개인정보·영업비밀·보존·국외이전
- AI 사용·재가공·보고서 사용 허용 범위
- 감사·원문 증빙·정정 책임

확인되지 않은 기술 사실을 추측해 구현하지 않는다.

---

## 6. 연계 방식 우선순위

1. 고객사 공식 API 또는 MCP Server
2. 승인된 DB Read Replica/View
3. 정기 파일 Export와 checksum
4. 내부 직원이 승인한 파일 업로드
5. 화면 자동화는 앞 방법이 모두 불가능하고 별도 위험 승인을 받은 경우에만 고려

첫 연계는 읽기 전용이다. 운영계 쓰기·상태 변경·외부 알림은 별도 Action Contract, 사용자 확인, Shadow 검증 없이는 허용하지 않는다.

---

## 7. Query Contract

각 고객사 Profile은 원천 물리 구조를 제품 공통 논리 계약에 매핑한다.

원료 구매 파일럿의 논리 계약 후보:

| 논리 계약 | 목적 | 필수 조건 | 최소 의미 |
|---|---|---|---|
| `partner_submission` | 외부 제출 상태 확인 | company + transaction/order | partner code, status, updated_at |
| `shipment_milestone` | 선적 일정·실적 확인 | shipment/order id | ETD/ATD/ETA/ATA, port, status |
| `customs_clearance` | 통관 진행 확인 | import/shipment id | stage, result, event date |
| `transport_milestone` | 운송·도착 확인 | transport/shipment id | pickup/departure/arrival, status |

실제 고객사가 일부 계약을 다른 시스템에서 제공하면 Connector를 나누어 조합한다. 하나의 외부 포털이 모든 데이터를 보유한다고 가정하지 않는다.

계약 필수 항목:

- 허용 엔터티와 필드 화이트리스트
- 필수 조회 파라미터
- 최대 행·페이지 크기·정렬
- 민감 필드와 프롬프트 전달 금지
- 조직·법인·사업부 범위
- 사용 목적과 승인자
- 계약 버전과 유효기간

---

## 8. Adapter 계약

현재 단일 객체 `fetch()`를 유지하면서 목록·증분 계약을 확장한다.

```python
class ExternalSystemAdapter:
    def fetch(self, system_id, endpoint, entity, selector) -> dict: ...

    def query(
        self, system_id, endpoint, entity,
        filters: dict, fields: list[str],
        cursor: str = "", limit: int = 100
    ) -> dict:
        # {items, next_cursor, source_as_of, source_version}
        ...

    def changes_since(
        self, system_id, endpoint, entity,
        updated_after: str, cursor: str = "", limit: int = 100
    ) -> dict:
        ...
```

필수 강제:

- Query Contract 검증 후 원천 호출
- 필수 필터 없는 전건 조회 금지
- 원천 응답에도 허용 필드 재적용
- cursor·limit·timeout·retry·circuit breaker
- 원천 계약 위반과 부분 응답 기록
- `(system_id, source_event_id, source_version)` 멱등 처리

---

## 9. 온디맨드 조회와 불변 Snapshot

### 온디맨드

- 내부 앱의 현재 상태 표시
- 짧은 TTL
- `source_system`, `as_of`, `stale` 표시
- 원천 장애 시 오래된 값을 최신으로 위장하지 않음
- 공식 시뮬레이션 입력으로 직접 사용하지 않음

### Snapshot

- Twin·Backtest·의사결정·보고서 입력
- 조회 조건·계약 버전·원천 시점·checksum 고정
- RAW를 덮어쓰지 않음
- Crosswalk·품질·대사·승인과 함께 `snapshot_id` 발급
- CERTIFIED만 공식 Actual 기준선으로 사용

TTL MCP 캐시는 Snapshot 저장소가 아니다.

---

## 10. 영구 동기화 논리 모델

새 SQLite를 추가하기보다 목표 Postgres `integration` 스키마로 수렴한다. 로컬 PoC 물리 저장은 DB 전략 승인 후 결정한다.

```text
source_sync_contracts
  id, connector_id, query_contract_id, profile_id,
  entity, scope_node_id, mode, schedule,
  cursor_strategy, status, approved_by/at

source_sync_runs
  id, contract_id, started/finished_at,
  cursor_from/to, fetched/accepted/quarantined,
  source_as_of, status, error_summary

source_event_versions
  system_id, source_event_id, source_version,
  entity, business_key, event_type,
  occurred_at, source_updated_at, received_at,
  raw_ref, checksum, is_latest

source_snapshots
  snapshot_id, contract_id, scope_node_id,
  source_as_of, query_fingerprint, contract_version,
  raw_ref, checksum, certification_status,
  certified_by/at
```

원천에 버전이 없으면 원천키·수정시각·payload checksum을 조합하되 정확한 취소·정정 추적이 제한됨을 표시한다.

---

## 11. 표준화·대사·승격

| 상태 | 의미 | Twin 사용 |
|---|---|---|
| RECEIVED | 원천에서 수신 | 금지 |
| QUARANTINED | 필수값·코드·버전·범위 오류 | 금지 |
| STANDARDIZED | MDM·Crosswalk 매핑 완료 | 탐색 가능 |
| RECONCILED | 내부 ERP/구매/입고와 허용 오차 내 대사 | 후보 |
| CERTIFIED | 데이터 오너 승인 | Actual 가능 |

대사 항목은 업무별로 정의한다.

- 발주·계약·선적·통관·운송·입고 참조키
- 수량·단위·통화·기간
- 사건 순서와 상태 전이
- 정정·취소·중복
- 회사·법인·사업부·공장 범위

불일치는 삭제하지 않고 데이터 준비 보드에 원인, 영향, 담당자, 다음 작업으로 표시한다.

---

## 12. 내부 API 후보

```text
POST /api/v1/connectors/{id}/query
POST /api/v1/connectors/{id}/changes-since
POST /api/v1/connectors/{id}/sync/preview
POST /api/v1/connectors/{id}/sync/run
GET  /api/v1/connectors/{id}/sync-runs
GET  /api/v1/source-snapshots/{snapshot_id}
POST /api/v1/source-snapshots/{snapshot_id}/certify
```

이 API는 내부 사용자와 내부 서비스만 사용한다. 외부 사용자를 위한 API가 아니다.

---

## 13. 보안 비협상 조건

- AI Factory Studio의 외부 사용자 접근 경로 0건
- 원천 시스템 자격증명을 코드·DB·로그·프롬프트에 저장 금지
- Query Contract 밖 필드·행·전건 조회 차단
- 원문·첨부·개인정보의 LLM 자동 전달 금지
- VIRTUAL·COMPETITOR 문맥의 운영계 호출 금지
- 캐시보다 조직 범위 판정 선행
- 조회 목적·요청자·범위·계약·건수·시각 감사
- 사용자 승인 없는 원천 시스템 쓰기 금지

---

## 14. 테스트

제품 코어가 특정 고객사에 종속되지 않았음을 증명하기 위해 최소 두 개의 서로 다른 Mock Profile로 같은 계약 테스트를 실행한다.

### 공통 계약

- 필수 조건 누락·금지 필드·전건 조회 차단
- 원천의 초과 필드 제거와 계약 위반 기록
- 페이지·cursor·rate limit

### 사건

- 중복 수신 멱등
- 정정 버전·취소·late-arrival
- 중단 cursor 재개

### 권한

- 다른 조직 원천 사건 비노출
- VIRTUAL/COMPETITOR 차단
- 캐시 선행 유출 방지

### Profile 독립성

- `ls_lpl` fixture와 `generic_supplier_portal` fixture가 동일 코어 테스트 통과
- 코어 코드에 고객사·시스템명 조건문 없음
- Profile 제거 후 다른 고객사 기능 정상

---

## 15. 적용 단계

| 단계 | 작업 | 완료 기준 |
|---|---|---|
| E0 Discovery | 고객사 외부 협업 시스템·업무·기술·거버넌스 조사 | Source Inventory |
| E1 Contract | Connector·Query Contract·Crosswalk | 승인된 최소 필드 |
| E2 Profile Fixture | Adapter Profile과 두 Mock 회귀 | 하드코딩 없음 |
| E3 Read-only | 테스트 원천 연계 | 현재 상태·as_of |
| E4 Snapshot | RAW·대사·Certification | 재현 가능한 Actual |
| E5 Shadow | 실제 업무와 병행 비교 | 누락·지연·오차 측정 |
| E6 Production Read | 운영 읽기 | SLA·감사·복구 |

운영 쓰기 연계와 외부 포털 구축은 완료 범위가 아니다.

---

## 16. LPL의 위치

LPL은 위 표준의 첫 적용 대상이다.

- Profile ID 예시: `ls_lpl`
- Connector 표시명: 고객사 설정
- 논리 계약: 제품 공통
- 원천 엔터티·필드·상태 매핑: LPL Profile
- LPL API/MCP 제공 여부: Discovery에서 확인

LPL에서 검증된 패턴은 제품 코어를 수정하지 않고 다른 고객사의 공급사 포털·물류 포털·통관 시스템 Profile로 교체할 수 있어야 한다.

---

## 17. 완료 정의

- 외부 참여자는 고객사의 기존 시스템만 사용한다.
- AI Factory Studio 외부 사용자·파트너 화면은 없다.
- 고객사마다 다른 시스템을 Connector Profile로 연결한다.
- 원천키·버전·시점·정정·취소가 추적된다.
- 현재 조회는 `as_of/stale`, 경영 계산은 CERTIFIED Snapshot을 사용한다.
- 동일 Snapshot·모델에서 결과를 재현한다.
- 특정 시스템 이름을 제거해도 제품 코어가 동작한다.

