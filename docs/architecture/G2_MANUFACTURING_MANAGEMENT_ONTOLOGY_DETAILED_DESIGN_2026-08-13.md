# G2 제조 경영 온톨로지 런타임 상세 설계

> 문서 상태: **구현 대기 상세 설계 기준선**  
> 작성: Codex / 2026-08-13  
> 상위 설계: `docs/design_manufacturing_management_ontology_2026-08-13.md`  
> 기계 판독 계약: `docs/architecture/g2_first_vertical_ontology_contract_v1.json`  
> 구현 착수 조건: **G1-B P0(B01~B05) 완료·커밋**  
> 현재 허용 범위: 설계·샘플 계약·검증 시나리오. 코드·DB·API 마이그레이션은 아직 금지한다.

---

## 1. 설계 목적

G2는 ECM·MDM·데이터 카탈로그·용어사전·Crosswalk·데이터 계보·외부지표·계획 모델을
하나의 그래프 DB로 복제하는 기능이 아니다. 각 진실원본의 식별자를 유지한 채, 다음 질문에
**승인된 관계와 근거 경로로 재현 가능하게** 답하는 통합 의미 런타임이다.

> 원료 도입이 14일 늦어지면 어느 공장, 어떤 원료 재고, 어떤 생산계획과 판매계획이 영향을 받고,
> 그 결과 매출·현금흐름·손익의 어떤 계산을 다시 수행해야 하는가?

G2의 책임은 `무엇이 무엇과 왜 연결되는가`까지다. 변화량·손익·현금 등 수치는 G4가 승인된
계산 정의로 산출한다.

### 1.1 사용자에게 제공할 가치

1. 업무 데이터가 어느 회사·사업부·공장에 속하며 어떤 데이터와 연결되는지 찾는다.
2. 결과의 원천·근거·버전·기준시점·승인 상태를 함께 보여 준다.
3. 데이터가 부족하면 답을 꾸며내지 않고 필요한 데이터와 다음 행동을 제안한다.
4. 영향 경로 중 계산 가능한 구간과 아직 계산 정의가 없는 구간을 구분한다.
5. 자연어 질문을 결정론적 질의 계획으로 바꾸되, LLM이 SQL·권한·공식 관계를 결정하지 못하게 한다.

### 1.2 비목표

- 모든 원천 데이터를 온톨로지 DB에 복제하지 않는다.
- 외부 참여자에게 경영 시스템을 개방하지 않는다. 외부 입력은 기존 포털·ERP·LPL류 시스템에서
  받고 승인된 Connector/Query Contract/Snapshot으로만 참조한다.
- LLM이 관계·수치·승인 상태를 자동 확정하지 않는다.
- 첫 단계에서 전사 전체 21개 유형을 억지로 모델링하지 않는다.
- 별도 그래프 DB를 먼저 도입하지 않는다.

---

## 2. 실측 기준선과 재사용 자산

### 2.1 스타터 키트

`KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0`에는 35개 데이터 계약과 다음 수직 흐름이 있다.

```text
조직·공통기준
  → 원료·공급사·공장·BOM·Routing·계정
  → 구매계약·구매주문
  → 선적·통관·내륙운송
  → 재고
  → 생산계획·생산실적
  → 판매계획·수주·출하
  → 원가·매입/매출채권·원장/현금흐름
  → 외부지표·Driver·시나리오·의사결정
```

모든 샘플 계약은 `tenant_id`, `scope_node_id`, `data_class`, `quality_status`,
`certification_status`, `as_of_date`, `lineage_id`를 공통 필드로 가진다. G2는 이 필드를 다시
만들지 않고 객체 범위와 근거 판정에 사용한다.

### 2.2 기존 엔진

| 자산 | G2 사용 방식 | 금지 |
|---|---|---|
| ECM 조직 그래프 | 회사·사업부·공장 범위·REAL/VIRTUAL/SANDBOX 문맥 | 조직 관계 복제 |
| MDM `entity_types`, `master_records` | 객체 유형 시드·기준 개체 | 트랜잭션 복제 |
| 카탈로그·계약·품질 | 근거·스키마·품질 상태 | 빈 계약을 있다고 표현 |
| `lineage_edges` | BFS·깊이 제한·순환 방지 알고리즘 재사용 | 업무 의미 관계와 같은 표에 저장 |
| `planning_drivers`·Planning Engine | G4 계산 대상 식별·실행 | 온톨로지에서 계산식 실행 |
| Decision Ledger | 승인 행위·결정 근거의 불변 감사 | 별도 승인 감사 원장을 진실원본으로 운영 |

### 2.3 현재 G4 보완 필요사항

상세 설계 실측에서 다음 두 결함을 확인했다. G2가 `calculation_ref`를 전달해도 이 두 항목이
해결되지 않으면 대표 질문을 끝까지 계산할 수 없다.

1. `planning_drivers.expand_driver_assumption()`은 동인 가정에서 `pct`만 지원한다. 스타터 키트의
   `DRV-DELAY=14 DAY`, `DRV-DOWNTIME=48 HOUR`, `DRV-CAPEX=KRW set`은 현재 방식으로 실행할 수 없다.
2. 미승인 `driver_impacts`가 차단되지 않고 경고만 남긴 채 계산에 사용된다. 경영 시뮬레이션은
   미승인 계수를 Fail-closed 해야 한다.

따라서 G4는 `pct|delta|set`별 승인된 변환 계약과 미승인 파급계수 실행 차단을 구현해야 한다.

---

## 3. 통합 객체 참조 계약

### 3.1 객체를 복제하지 않는 주소

모든 관계 끝점은 다음 구조를 사용한다.

```json
{
  "namespace": "dataset",
  "object_type": "purchase-order-line",
  "object_id": "PO-000001-10",
  "dataset_id": "PRC-02",
  "version": "1.0.0",
  "as_of": "2026-08-11"
}
```

DB에는 `subject_namespace/type/id`, `object_namespace/type/id`를 분리 저장한다. URI 문자열 하나로
합쳐 저장하지 않는다. 문자열 파싱 오류와 구분자 충돌을 피하고 원천별 검증기를 적용하기 위해서다.

### 3.2 네임스페이스

| namespace | 진실원본 | 예시 |
|---|---|---|
| `ecm` | 회사·조직·사업장 | `organization-node:plant-afs-smelting-01` |
| `mdm` | 기준정보 | `material:RM-CU-CONC` |
| `dataset` | Snapshot/Query Contract가 제공하는 업무 레코드 | `shipment:SHP-000001` |
| `external` | 외부지표 관측값·지표 정의 | `indicator:USD_KRW` |
| `g4` | 동인·계산 정의·계획계정 | `driver:DRV-DELAY` |
| `decision` | 시나리오·결정·실행과제 | `case:DEC-...` |
| `knowledge` | 지식 문서·표준·계약 근거 | `document:DOC-...` |

### 3.3 첫 수직 폐루프 객체 유형

| 그룹 | 객체 유형 | 원천 | 키 | 모델링 상태 |
|---|---|---|---|---|
| 조직 | `organization-node` | ECM/FND-01 | `node_id` | REQUIRED |
| 기준 | `material` | MDM-01 | `material_id` | REQUIRED |
| 기준 | `supplier` | MDM-02 | `supplier_id` | REQUIRED |
| 기준 | `location` | MDM-04 | `location_id` | REQUIRED |
| 기준 | `bom-line` | MDM-05 | `bom_id+line_no` | REQUIRED |
| 기준 | `routing-operation` | MDM-06 | `routing_id+operation_seq` | REQUIRED |
| 기준 | `equipment` | MDM-06 | `equipment_id` | REQUIRED |
| 기준 | `account`·`cost-center` | MDM-07 | `account_id`·`cost_center_id` | REQUIRED |
| 기준 | `logistics-reference` | MDM-08 | `reference_id` | REQUIRED |
| 구매 | `procurement-contract` | PRC-01 | `contract_id` | REQUIRED |
| 구매 | `purchase-order-line` | PRC-02 | `po_line_id` | REQUIRED |
| 물류 | `partner-submission` | LOG-01 | `submission_id` | OPTIONAL |
| 물류 | `shipment` | LOG-02 | `shipment_id` | REQUIRED |
| 물류 | `shipment-milestone` | LOG-03 | `milestone_id` | REQUIRED |
| 물류 | `customs-clearance` | LOG-04 | `clearance_id` | REQUIRED |
| 물류 | `transport-event` | LOG-05 | `transport_event_id` | REQUIRED |
| 재고 | `inventory-snapshot` | INV-01 | `snapshot_id` | REQUIRED |
| 생산 | `production-plan-line` | MFG-01 | `plan_line_id` | REQUIRED |
| 생산 | `production-batch` | MFG-02 | `batch_id` | OPTIONAL |
| 판매 | `sales-line` | SLS-01 | `sales_line_id` | REQUIRED |
| 재무 | `cost-record` | FIN-01 | `cost_record_id` | REQUIRED |
| 재무 | `finance-document` | FIN-02 | `finance_document_id` | REQUIRED |
| 재무 | `ledger-line` | FIN-03 | `ledger_line_id` | REQUIRED |
| 외부 | `external-observation` | EXT-01~03 | `observation_id` | REQUIRED |
| 계산 | `driver` | SIM-01/G4 | `driver_id` | REQUIRED |
| 결정 | `scenario`·`decision` | SIM-02/DEC-01 | 각 ID | REQUIRED |

`REQUIRED`는 첫 폐루프 시연에 필요한 유형이다. `OPTIONAL`은 경로를 더 정확하게 하지만 없다고
전체 기능을 차단하지 않는다. 그 외 유형은 `UNMODELED`이며 완료로 세지 않는다.

---

## 4. 관계 유형 정본

### 4.1 관계 유형 공통 필드

```text
relation_type_id, name_ko, description
directional, inverse_relation_type_id, symmetric, transitive
schema_version, approval_status, effective_from, effective_to
required_evidence_kinds, created_by, approved_by, ledger_correlation_id
```

공식 상태는 `DRAFT → IN_REVIEW → APPROVED → SUPERSEDED|RETIRED`다. 반려는 `REJECTED`로
남긴다. `EXPIRED`는 상태값이 아니라 유효기간으로 계산한다.

### 4.2 첫 수직 폐루프 관계 사전

역관계는 별도 간선을 중복 저장하지 않는다. 한 개의 정방향 간선을 역방향으로 탐색할 때 사용하는
표시명·질의 별칭이다. 따라서 정방향 관계가 개정·폐기되면 역방향 결과도 같은 버전과 상태를 따른다.

| ID | 사용자 표현 | 역관계 | 용도 |
|---|---|---|---|
| `OWNED_BY` | 소유 조직 | `OWNS` | 모든 객체의 책임 범위 |
| `LOCATED_AT` | 위치함 | `HOSTS` | 설비·재고·공정·생산계획 위치 |
| `SUPPLIES` | 공급함 | `SUPPLIED_BY` | 공급사→원료 |
| `COVERS_MATERIAL` | 계약 대상 원료 | `COVERED_BY_CONTRACT` | 구매계약→원료 |
| `AGREED_WITH` | 계약 상대 | `HAS_CONTRACT` | 구매계약→공급사 |
| `ORDERED_UNDER` | 계약에 따라 주문 | `HAS_ORDER` | 구매주문→계약 |
| `ORDERS_MATERIAL` | 주문 원료 | `ORDERED_BY` | 구매주문→원료 |
| `FULFILLED_BY_SHIPMENT` | 선적으로 이행 | `FULFILLS_ORDER` | 구매주문→선적 |
| `HAS_MILESTONE` | 진행 이력 | `MILESTONE_OF` | 선적→이벤트 |
| `CLEARED_BY` | 통관 처리 | `CLEARS` | 선적→통관 |
| `DELIVERED_BY` | 내륙 운송 | `DELIVERS` | 선적→운송 이벤트 |
| `DELIVERED_TO` | 도착 위치 | `RECEIVES` | 운송→창고/공장 |
| `STOCKS_MATERIAL` | 보유 원료 | `STOCKED_AS` | 재고 Snapshot→원료 |
| `AT_LOCATION` | 재고 위치 | `HAS_INVENTORY` | 재고 Snapshot→위치 |
| `CONSUMES_MATERIAL` | 투입 원료 | `CONSUMED_BY_BOM` | BOM→원료 |
| `PRODUCES_MATERIAL` | 산출 품목 | `PRODUCED_BY` | BOM/생산→제품 |
| `USES_BOM` | BOM 적용 | `USED_BY_PLAN` | 생산계획→BOM |
| `USES_ROUTE` | Routing 적용 | `ROUTE_FOR_PLAN` | 생산계획→Routing |
| `USES_EQUIPMENT` | 설비 사용 | `USED_BY_OPERATION` | Routing→설비 |
| `FULFILLS_SALES` | 판매계획 충족 | `FULFILLED_BY_PLAN` | 생산계획→판매라인 |
| `SETTLED_BY` | 재무문서로 정산 | `SETTLES` | 구매/판매→재무문서 |
| `POSTED_TO_ACCOUNT` | 계정 반영 | `HAS_POSTING` | 원장라인→계정 |
| `DRIVES` | 경영 동인으로 연결 | `DRIVEN_BY` | 외부지표→G4 동인 |
| `AFFECTS` | 영향을 줌 | `AFFECTED_BY` | 승인된 인과 경로 |
| `MEASURED_BY` | KPI로 측정 | `MEASURES` | 결과 객체→KPI |
| `AUTHORIZED_BY` | 결정으로 승인 | `AUTHORIZES` | 시나리오/실행→결정 |

### 4.3 관계 제약 원칙

1. 관계 유형만 등록돼 있어도 아무 객체나 연결할 수 없다. `subject namespace/type`과
   `object namespace/type`의 허용 조합이 승인돼야 한다.
2. 구조·키 연결은 승인된 Data Contract와 실제 FK/비즈니스 키를 근거로 `derived` 후보를 만들 수 있다.
3. `AFFECTS`는 최소 하나의 업무 근거가 필요하다. 수치 영향을 주장하려면 `calculation_ref`도 필수다.
4. LLM/Graph RAG가 만든 `suggested` 관계는 기본 질의에서 제외한다.
5. 관계 경로의 중간 노드가 권한 밖이면 건너뛰어 양 끝을 직접 잇지 않는다.

### 4.4 핵심 허용 조합

| Subject | Relation | Object | 필수 근거 | 계산 참조 |
|---|---|---|---|---|
| supplier | SUPPLIES | material | MDM-02 `material_ids` | 없음 |
| procurement-contract | COVERS_MATERIAL | material | PRC-01 `material_id` | 없음 |
| procurement-contract | AGREED_WITH | supplier | PRC-01 `supplier_id` | 없음 |
| purchase-order-line | ORDERED_UNDER | procurement-contract | PRC-02 `contract_id` | 없음 |
| purchase-order-line | ORDERS_MATERIAL | material | PRC-02 `material_id` | 없음 |
| purchase-order-line | FULFILLED_BY_SHIPMENT | shipment | LOG-02 `po_line_id` | 없음 |
| shipment | HAS_MILESTONE | shipment-milestone | LOG-03 `shipment_id` | 없음 |
| shipment | CLEARED_BY | customs-clearance | LOG-04 `shipment_id` | 없음 |
| shipment | DELIVERED_BY | transport-event | LOG-05 `shipment_id` | 없음 |
| transport-event | DELIVERED_TO | location | LOG-05 `destination_location_id` | 없음 |
| inventory-snapshot | STOCKS_MATERIAL | material | INV-01 `material_id` | 없음 |
| inventory-snapshot | AT_LOCATION | location | INV-01 `location_id` | 없음 |
| bom-line | CONSUMES_MATERIAL | material | MDM-05 `input_material_id` | 없음 |
| bom-line | PRODUCES_MATERIAL | material | MDM-05 `output_material_id` | 없음 |
| production-plan-line | USES_BOM | bom-line | 제품+BOM 유효기간 매칭 | 없음 |
| production-plan-line | USES_ROUTE | routing-operation | MFG-01 site/product + MDM-06 | 없음 |
| routing-operation | USES_EQUIPMENT | equipment | MDM-06 `equipment_id` | 없음 |
| production-plan-line | FULFILLS_SALES | sales-line | product+period+approved allocation | 없음 |
| purchase-order-line | SETTLED_BY | finance-document | FIN-02 `reference_id` | 없음 |
| ledger-line | POSTED_TO_ACCOUNT | account | FIN-03 `account_id` | 없음 |
| external-observation | DRIVES | driver | SIM-01 `input_metric` | driver ID |
| shipment | AFFECTS | inventory-snapshot | 승인된 지연 모델 | `CALC.LOGISTICS.ARRIVAL_DELAY.v1` |
| inventory-snapshot | AFFECTS | production-plan-line | BOM·재고·계획 | `CALC.INVENTORY.MATERIAL_SHORTAGE.v1` |
| production-plan-line | AFFECTS | sales-line | 생산·수주 allocation | `CALC.PRODUCTION.REVENUE_TIMING.v1` |
| cost-record | AFFECTS | ledger-line | 원가-계정 매핑 | `CALC.FINANCE.COST_MARGIN_CASH.v1` |

---

## 5. 관계 인스턴스·버전·승인 모델

### 5.1 4층 저장 구조

1. `semantic_relation_types`: 관계 사전.
2. `semantic_relation_constraints`: 허용 객체 유형 조합과 근거 조건.
3. `semantic_relations`: 후보와 승인 관계 인스턴스.
4. `semantic_relation_events`: 관계 변경 이력. 승인 결정은 Decision Ledger에 연결.

### 5.2 관계 인스턴스 최소 계약

```text
relation_id
subject_namespace / subject_type / subject_id
object_namespace  / object_type  / object_id
relation_type_id
version / supersedes_relation_id
effective_from / effective_to
tenant_id / enterprise_scope_id / entity_mode
scope_type / owner_organization_id / scope_assignments / classification
approval_status / submitted_by / approved_by / approved_at
origin(user|derived|suggested) / confidence(nullable)
evidence_refs(JSON array) / source_lineage(JSON)
calculation_ref(nullable)
ledger_correlation_id
created_by / created_at / updated_at
```

### 5.3 유일성

- DRAFT·REJECTED 후보는 여러 개 공존할 수 있다.
- 동일 `(subject, relation, object, tenant, mode, scope)`에 같은 시점에 유효한 APPROVED 관계는
  하나만 존재한다.
- 미래 효력 버전은 현재 버전과 공존할 수 있으나 유효기간이 겹치면 승인할 수 없다.
- 개정은 덮어쓰지 않고 새 행을 만들며 이전 행은 `SUPERSEDED`와 `effective_to`로 닫는다.

### 5.4 승인 권한

| 변경 | 최소 권한 | 추가 조건 |
|---|---|---|
| 후보 생성 | 해당 객체 읽기 + 관계 제안 | 양 끝 객체가 모두 보임 |
| 검토 제출 | 관계 오너/데이터 스튜어드 | 근거 존재 |
| 승인 | 지정 승인자 | 자기 승인 금지 |
| 폐기 | 관계 오너 + 영향 검토 | 사용 중인 계산/결정 영향 표시 |
| 전사 공용 | 전사 데이터 거버넌스 | `ENTERPRISE_SHARED` 명시 승인 |

---

## 6. 권한과 문맥 계약

### 6.1 G1-B 의존 구조

```text
인증 Principal
  → G1-B PDP가 Capability·조직 권한·테넌트 판정
  → ResourceScope Adapter가 G2 객체/관계를 범용 자원 계약으로 번역
  → Query Executor가 승인·기간·문맥 필터 적용
  → 보이는 노드와 간선만 Path Builder에 전달
```

어댑터는 판정하지 않는다. 다음 정보만 만든다.

```json
{
  "resource_kind": "ontology_relation",
  "tenant_id": "tenant-afs-demo-materials",
  "scope_node_id": "plant-afs-smelting-01",
  "entity_mode": "VIRTUAL",
  "classification": "INTERNAL",
  "owner_organization_id": "org-afs-metals",
  "required_capability": "ontology.relation.read"
}
```

### 6.2 존재 은폐

- 권한 밖 노드·관계는 결과, 개수, 사유에 포함하지 않는다.
- 권한은 있으나 현재 선택 문맥과 달라 제외된 경우만 `context_omitted` 건수와 문맥 전환 방법을
  제공할 수 있다.
- 단건 권한 거부는 404, 인증 부재는 401, 문맥 판정 불능은 503, 입력 형식 오류는 422다.
- 감사 로그에는 요청 문맥·서버 판정 문맥·차단 사유·query_id를 기록한다.

### 6.3 경로 판정

경로의 모든 노드와 간선이 보여야 경로를 반환한다. 중간 노드가 차단되면 그 경로 전체를 제거한다.
차단 노드를 생략해 새 경로를 만들면 안 된다.

---

## 7. 자연어 질의 계획

### 7.1 지원 질문 유형

| Intent | 사용자 예시 | 결과 |
|---|---|---|
| `DEFINE` | “동정광이 무엇인가?” | 객체·정의·별칭·근거 |
| `RELATE` | “이 공급사가 어떤 원료를 공급하지?” | 직접 승인 관계 |
| `TRACE` | “이 숫자는 어디서 왔나?” | 원천·계보·계약 경로 |
| `IMPACT` | “선적이 14일 늦으면 무엇이 영향받나?” | 의미 경로·계산 가능 구간 |
| `AS_OF` | “2026년 3월 기준 관계는?” | 당시 유효 버전 경로 |
| `COMPARE_SCOPE` | “1공장과 2공장 영향 차이는?” | 권한 범위 내 경로 비교 |
| `READINESS` | “이 시뮬레이션을 돌릴 데이터가 충분한가?” | 준비 데이터·결손·품질 |
| `WHAT_IF` | “환율 10% 상승 시 손익은?” | G2 경로 + G4 실행 초안 |
| `EVIDENCE` | “왜 이 관계를 인정했나?” | 승인자·근거·버전 |

### 7.2 처리 순서

1. 현재 회사·조직·모드·사용자 권한을 서버에서 확정한다.
2. 질문을 intent·기간·수치 가정·개체 표현으로 분해한다.
3. 승인된 용어·동의어·Crosswalk로 **권한 범위 안에서만** 객체 후보를 찾는다.
4. 단일 후보가 아니면 사용자에게 2~3개 선택지를 제시한다. 임의로 하나를 고르지 않는다.
5. 관계 유형 화이트리스트와 허용 조합으로 결정론적 Query Plan을 만든다.
6. 승인·as-of·범위·품질 필터를 적용해 경로를 탐색한다.
7. 근거와 부족 데이터를 조립한다.
8. 사용자가 수치 계산을 요청했고 모든 계산 참조가 준비된 경우에만 G4 실행 초안을 만든다.

### 7.3 LLM 허용 범위

허용: intent 분류, 표현 추출, 후보 설명, 답변 문장화.  
금지: SQL 생성·실행, 권한 판정, 공식 관계 생성/승인, 수치 계산, 모호한 객체 자동 선택.

### 7.4 Query Plan 계약

```json
{
  "query_id": "oq-...",
  "intent": "IMPACT",
  "subject_refs": [{"namespace":"dataset","object_type":"shipment","object_id":"SHP-000001"}],
  "target_types": ["production-plan-line","sales-line","ledger-line"],
  "relation_types": ["AFFECTS","FULFILLED_BY_SHIPMENT","STOCKS_MATERIAL"],
  "as_of": "2026-08-11T00:00:00Z",
  "max_depth": 6,
  "include_evidence": true,
  "calculation_requested": false,
  "assumptions": [{"driver_id":"DRV-DELAY","operator":"delta","value":14,"unit":"DAY"}],
  "context_fingerprint": "sha256:..."
}
```

`context_fingerprint`가 현재 문맥과 달라지면 실행 결과를 폐기하고 다시 조회한다.

---

## 8. API 상세 계약

### 8.1 탐색 API

| Method | Path | 역할 |
|---|---|---|
| POST | `/api/v1/ontology/object-resolutions` | 표현→권한 내 객체 후보 |
| POST | `/api/v1/ontology/query-plans` | 자연어→검토 가능한 질의 계획 |
| POST | `/api/v1/ontology/queries` | 결정론적 계획 실행 |
| GET | `/api/v1/ontology/objects/{namespace}/{type}/{id}` | 객체 상세·원천 참조 |
| GET | `/api/v1/ontology/relations/{relation_id}` | 관계 상세·버전·근거 |
| GET | `/api/v1/ontology/paths/{query_id}` | 재현 가능한 저장 결과 조회 |

### 8.2 거버넌스 API

| Method | Path | 권한 |
|---|---|---|
| GET/POST | `/api/v1/ontology/relation-types` | 조회 / 모델 관리자 |
| GET/POST | `/api/v1/ontology/relation-constraints` | 조회 / 모델 관리자 |
| POST | `/api/v1/ontology/relations` | 관계 제안 |
| POST | `/relations/{id}/submit` | 관계 오너 |
| POST | `/relations/{id}/approve` | 승인자, 자기 승인 금지 |
| POST | `/relations/{id}/reject` | 승인자, 사유 필수 |
| POST | `/relations/{id}/supersede` | 승인자, 새 버전 필수 |
| POST | `/relations/{id}/retire` | 오너+승인자, 영향 검토 필수 |

### 8.3 경로 응답

```json
{
  "query_id": "oq-123",
  "status": "COMPLETE",
  "as_of": "2026-08-11T00:00:00Z",
  "paths": [{
    "path_id": "path-1",
    "nodes": [],
    "edges": [],
    "evidence_refs": [],
    "calculation_readiness": "PARTIAL",
    "missing_requirements": ["CALC.INVENTORY.MATERIAL_SHORTAGE.v1 승인본"]
  }],
  "context_omitted": {"count": 2, "how_to_include": "상위 조직 범위를 선택하십시오."},
  "data_readiness": {"status":"PARTIAL","missing_datasets":["LOG-03"]},
  "warnings": []
}
```

권한 밖·미승인 관계의 수는 포함하지 않는다. 결과가 없으면 `NO_VISIBLE_PATH`, 데이터 계약이
없으면 `INSUFFICIENT_DATA`, 관계 정의가 없으면 `UNMODELED`, 계산식이 없으면
`CALCULATION_NOT_READY`로 구분한다.

---

## 9. G4 계산 그래프 인계

### 9.1 계산 요청 초안

G2는 사용자가 `시뮬레이션으로 보내기`를 확인하기 전에는 G4를 실행하지 않는다.

```json
{
  "calculation_request_id": "cr-...",
  "baseline_id": "BASELINE-DEMO-1.0",
  "tenant_id": "tenant-afs-demo-materials",
  "scope_node_id": "plant-afs-smelting-01",
  "entity_mode": "VIRTUAL",
  "as_of": "2026-08-11",
  "assumptions": [{"driver_id":"DRV-DELAY","operator":"delta","value":14,"unit":"DAY"}],
  "calculation_chain": [
    "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
    "CALC.INVENTORY.MATERIAL_SHORTAGE.v1",
    "CALC.PRODUCTION.REVENUE_TIMING.v1",
    "CALC.FINANCE.COST_MARGIN_CASH.v1"
  ],
  "relation_versions": [],
  "evidence_refs": [],
  "path_fingerprint": "sha256:..."
}
```

### 9.2 실행 전 게이트

다음 중 하나라도 실패하면 실행하지 않는다.

- 기준선·계산 정의·관계가 모두 승인 상태인가.
- 계산 정의의 유효기간이 `as_of`를 포함하는가.
- 데이터 품질과 certification 등급이 계산 목적에 충분한가.
- `pct|delta|set` 연산자가 해당 계산기에 구현돼 있는가.
- relation/version/path fingerprint가 바뀌지 않았는가.
- 사용자가 결과 적용이 아닌 단순 조회를 요청한 것은 아닌가.

### 9.3 대표 지연 경로

```text
SHP-000001(선적)
 └─ FULFILLS_ORDER → PO-000002-10
     └─ ORDERS_MATERIAL → RM-MHP
         ├─ STOCKED_AS → 해당 공장 재고 Snapshot
         └─ CONSUMED_BY_BOM → 생산 대상 BOM
             └─ USED_BY_PLAN → 생산계획
                 └─ FULFILLS_SALES → 판매계획
                     └─ G4 계정 영향 → 매출·재고·매입채무·현금·매출총이익
```

경로를 찾는 것과 숫자를 계산하는 것을 분리한다. 경로가 있어도 계산 정의가 없으면
`영향 관계는 확인됨 / 수치 계산은 준비되지 않음`으로 표시한다.

---

## 10. 기업 경영 의미지도 UI/UX

### 10.1 정보 구조

기존 승인 셸을 사용한다. 별도 테마와 새로운 내비게이션 체계를 만들지 않는다.

```text
상단 Context Bar
  회사 › 사업부 › 공장 · REAL/VIRTUAL/SANDBOX · 기준시점 · 모델 버전

좌측 238px                 중앙 가변 작업면                         우측 300px
질문/탐색 모드             질문 결과와 승인된 의미 경로             AI 비서
객체·관계 필터             경로별 근거·계산 준비 상태               현재 선택 객체/경로
저장된 질문                부족 데이터·다음 행동                    후속 질문·설명

하단 Drawer
  원천·계보 · 관계 버전 · 승인 이력 · 데이터 품질 · 계산 인계 초안
```

### 10.2 화면 탭

1. **의미 탐색**: 객체 정의·별칭·직접 관계.
2. **영향 경로**: 질문 중심 경로와 계산 가능 구간.
3. **관계 검토**: 제안·검토·승인·반려. 권한자에게만 표시.
4. **모델 상태**: 모델링 완료/UNMODELED, 근거 부족, 데이터 준비율.

### 10.3 기본 화면

- 자연어 질문창을 중앙 상단에 크게 둔다.
- 예시 질문은 현재 문맥과 실제 가능한 데이터에 따라 3개만 제안한다.
- 빈 화면에는 그래프 장식 대신 `현재 연결 가능한 데이터`, `부족한 데이터`, `권장 첫 질문`을 표시한다.
- 전체 전사 그래프를 기본으로 펼치지 않는다. 질문에 답하는 1~3개 핵심 경로만 보여 주고 사용자가
  확장하게 한다. 그래프 헤어볼은 경영자가 읽을 수 없다.

### 10.4 노드와 간선 표현

- 노드: 사용자 명칭, 객체 유형, 조직 범위, 데이터 상태 배지.
- 간선: 한국어 관계명, 승인 상태, 유효기간, 근거 개수, 계산 가능 여부.
- 색만으로 상태를 구분하지 않고 텍스트·아이콘을 병행한다.
- `SYNTHETIC`, `DEMO_ONLY`, `VIRTUAL`은 경로 상단과 결과 카드에 반복 표시한다.
- 미승인 관계는 공식 결과 그래프에 나타내지 않고 관계 검토 탭에서만 점선으로 표시한다.

### 10.5 결과 카드

각 경로는 다음 순서로 읽힌다.

1. **무엇이 연결됐는가**
2. **왜 연결됐는가**
3. **어느 시점·버전인가**
4. **어떤 데이터가 근거인가**
5. **수치 계산이 가능한가**
6. **다음에 무엇을 할 수 있는가**

행동 버튼은 상태에 따라 하나만 주행동으로 둔다.

- 준비 완료: `시뮬레이션 초안 만들기`
- 계산 정의 부족: `필요 계산 정의 요청`
- 데이터 부족: `데이터 준비 안내 보기`
- 관계 미승인: `관계 검토 요청`

### 10.6 AI 비서 문맥

Task ID를 요구하지 않는다. 서버가 확정한 회사·조직·모드, 선택 객체/경로, 허용 행동만 전달한다.
원문 데이터나 권한 밖 객체 목록은 비서 문맥에 넣지 않는다.

추천 질문 예:

- “이 경로에서 아직 확인되지 않은 데이터는 무엇인가요?”
- “이 관계가 승인된 근거를 설명해 주세요.”
- “수치 시뮬레이션을 하려면 무엇을 더 준비해야 하나요?”

### 10.7 반응형·접근성

- 1280px 이상: 3열 유지.
- 1024~1279px: 좌측·비서 레일을 Drawer로 전환하고 선택 경로를 보존.
- 1024px 미만: 그래프 대신 순서형 Path List를 기본 제공.
- 노드·간선은 키보드 탐색 가능하고 포커스 시 상세 설명을 읽을 수 있어야 한다.
- 본문 14px 이상, 보조 텍스트 12px 이상, 가로 오버플로 0을 수용 기준으로 한다.

---

## 11. 유형 통합 마이그레이션

### 11.1 정본

`quality-spec`, `finance-param`, `emission-factor`, `sensor-spec`를 정본으로 한다.

### 11.2 단계

1. **감사**: 밑줄형을 참조하는 레코드·바인딩·부서 master_domains·프로젝트 메타·시드·로더·테스트를
   전수 출력한다. 모호한 참조는 변경하지 않는다.
2. **별칭 계약**: `entity_type_aliases`를 먼저 생성하고 네 쌍을 등록한다.
3. **정규화 계층**: 입력에서 밑줄형을 받아 정본으로 변환하되 응답과 신규 저장은 정본만 사용한다.
4. **데이터 이관**: 트랜잭션과 백업 아래 `master_records.type_id` 및 실제 유형 참조만 변경한다.
5. **코드 이관**: `org_seed.py`, `api_data_loader.py`, 문서·테스트 참조를 목적별로 확인해 변경한다.
   `master_domains`가 유형 ID가 아닌 업무 태그로 쓰이는 곳은 기계적으로 바꾸지 않는다.
6. **대사**: 전후 레코드 수·활성 버전·범위 바인딩·주입 결과·중복 탐지 결과가 같아야 한다.
7. **폐쇄**: 밑줄형 신규 생성 차단. 별칭 조회는 유지한다.

### 11.3 롤백

- 적용 전 JSON 감사 보고서와 DB 백업을 생성한다.
- 변경 행마다 old/new type_id를 기록한다.
- 롤백은 감사 보고서의 정확한 대상만 되돌린다.
- 정규화 코드를 먼저 제거하지 않는다. 데이터 롤백 후 제거한다.

---

## 12. 외부 원천·Snapshot·Query Contract

현재 런타임의 `connectors`, `query_contracts`, `external_observations`가 비어 있으므로 스타터 키트
CSV를 운영 원천처럼 읽으면 안 된다. 첫 구현은 다음 두 모드를 구분한다.

| 모드 | 원천 | 사용 가능 범위 |
|---|---|---|
| DEMO | 스타터 키트 계약+SYNTHETIC Snapshot | 기능·화면·회귀 검증 |
| OPERATIONAL | 승인 Connector/Query Contract/Snapshot | 실제 경영 질의·계산 |

운영 원천 연결 순서:

1. Source Inventory 등록.
2. 스키마·키·단위·기간·보안등급 프로파일링.
3. RAW 불변 Snapshot과 checksum.
4. Crosswalk·격리·대사.
5. 데이터 오너 승인과 CERTIFIED 기준선.
6. G2 객체 Resolver와 관계 후보 생성.

외부 포털은 G2 사용자가 아니다. 포털 데이터는 Connector를 통해 내부 승인 데이터로 들어온다.

---

## 13. 테스트와 수용 기준

### 13.1 결정론

- 동일 사용자·문맥·as-of·모델 버전·질문은 동일 Query Plan과 path fingerprint를 반환한다.
- LLM 모델을 바꿔도 객체 후보 확정 후의 경로 결과는 동일하다.

### 13.2 보안

- 타 테넌트·타 조직·타 실행 모드 관계가 목록·경로·개수·비서 문맥에 나타나지 않는다.
- 중간 노드 차단 시 경로를 건너뛰어 재연결하지 않는다.
- 권한 회수 후 기존 캐시·저장 질의가 다시 보이지 않는다.
- 승인 전·REJECTED·SUPERSEDED·RETIRED·기간 밖 관계는 기본 질의에 나오지 않는다.

### 13.3 버전·기간

- 현재/과거/미래 유효 관계를 as-of로 정확히 재현한다.
- 같은 시점의 승인 관계 중복을 막고 미래 버전 공존은 허용한다.
- 폐기 후 과거 결정의 근거 경로는 재현된다.

### 13.4 데이터·근거

- 모든 공식 간선에 근거가 있다.
- 원천 계약·행·버전이 사라지거나 품질이 하락하면 `STALE` 또는 `INSUFFICIENT_DATA`가 된다.
- SYNTHETIC 경로가 REAL/CERTIFIED 결과로 승격되지 않는다.

### 13.5 G4

- 계산 정의 미승인·기간 밖·연산자 미지원이면 실행하지 않는다.
- `DRV-DELAY 14 DAY`, `DRV-FX +10%`, `DRV-CAPEX set` 세 연산 형태를 독립 검증한다.
- 미승인 파급계수는 경고 후 실행이 아니라 **실행 차단**이다.
- path/relation/calculation fingerprint가 결과에 고정된다.

### 13.6 UX

- 조회 실패를 0건으로 표시하지 않는다.
- 권한 밖 건수를 표시하지 않는다.
- 1280×720·1440×900에서 핵심 질문·경로·행동·비서가 보인다.
- 그래프를 사용하지 못하는 환경에서도 Path List로 같은 정보를 읽을 수 있다.

---

## 14. 성능·관측성

### 14.1 목표

- 직접 관계 조회 p95 300ms 이하.
- 6홉 이하 대표 경로 조회 p95 700ms 이하.
- 자연어 계획 생성 제외, 결정론적 실행 시간만 별도 계측.
- 경로 결과 최대 20개, 기본 표시 3개. 초과 시 페이지/필터를 요구한다.

### 14.2 텔레메트리

```text
ontology.query.count / latency_ms / path_count / max_depth
ontology.resolve.ambiguous_count / no_match_count
ontology.path.context_omitted_count
ontology.evidence.missing_count / stale_count
ontology.calculation.ready_count / blocked_count_by_safe_reason
ontology.cache.hit / invalidated_by_scope / invalidated_by_version
```

권한 거부 객체 수는 사용자 텔레메트리에 싣지 않는다. 보안 감사 채널에서만 기록한다.

### 14.3 그래프 DB 재판정

SQLite 인덱스·재귀 CTE·캐시로 시작한다. 활성 간선 10만 건, 단일 범위 1만 건, 6홉 경로 p95
1.5초 초과, 1회 1,000경로 이상, 가중 최단경로 같은 확정 요구 중 2개 이상이 관측될 때만
그래프 DB를 검토한다.

---

## 15. 구현 단계와 출구 조건

### G2-D0 — 상세 설계 동결

- 본 문서와 기계 계약 교차검토.
- G1-B `ResourceScope` 실제 필드 결합.
- 첫 폐루프 관계 오너·승인자 지정.

### G2-D1 — 유형 정규화

- `entity_type_aliases`와 dry-run 마이그레이션.
- 네 중복 유형 대사·롤백 시험.

### G2-D2 — 관계 거버넌스 저장소

- 4층 스키마·상태 전이·기간·부분 유일성.
- Decision Ledger correlation.

### G2-D3 — 객체 Resolver와 결정론적 경로

- 각 원천 Adapter.
- 승인·기간·범위 필터.
- 기존 BFS 골격 일반화.

### G2-D4 — 첫 수직 관계 적재

- Data Contract 명시 키로 `derived` 후보 생성.
- 관계 오너 검토·승인.
- 대표 지연 경로 재현.

### G2-D5 — 자연어 질의와 의미지도 UI

- Query Plan 생성·모호성 선택.
- 경로·근거·데이터 준비 상태.
- AI 비서 문맥 연결.

### G2-D6 — G4 인계와 폐루프 카나리

- `pct|delta|set` 승인 계산.
- 선적 14일 지연 → 생산·매출·현금·손익.
- 결과→Decision Package→실행과제 연결.

### 최종 출구 질문

다음 질문에 시스템이 한 번에 답하고 사용자가 근거를 확인할 수 있어야 한다.

> “SHP-000001 선적이 14일 늦어질 경우, 2026년 3월 31일 기준으로 어느 공장의 어떤 원료와
> 생산계획·판매계획이 영향받습니까? 수치 계산이 가능한 구간과 아직 필요한 데이터·계산 정의를
> 구분하고, 사용 가능한 시뮬레이션 초안을 보여 주세요.”

통과 조건:

1. 승인된 의미 경로와 근거가 표시된다.
2. 권한 밖 정보는 존재도 드러나지 않는다.
3. 계산 가능한 구간만 G4가 실행한다.
4. 부족 데이터와 다음 행동을 시스템이 제안한다.
5. 동일 기준시점·버전으로 재실행하면 동일 결과가 나온다.

---

## 16. 팀별 다음 작업

- Claude Code: G1-B P0 완료 후 `ResourceScope` 실제 계약을 본 설계에 결합하고 G2-D1~D4 구현.
- Codex: 의미지도 화면 상세 시안·질문/경로/근거 상호작용 및 사용자 수용 점검.
- Antigravity: 관계 근거 등급·외부 원천 신뢰 등급·그래프 DB 임계값 교차검증.
- Supervisor/현업 오너: 첫 폐루프 관계 오너·승인자와 실제 원천 대체 우선순위 승인.

역할은 주담당이며 고정 경계가 아니다. 권한·데이터 모델·수치 계산은 최소 한 명이 독립 교차검토한다.
