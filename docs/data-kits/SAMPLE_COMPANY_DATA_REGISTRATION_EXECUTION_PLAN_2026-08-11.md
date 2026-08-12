# 샘플 회사 Starter Kit 데이터 등록 준비 상세 수행계획

> 문서 상태: 실행 기준안 1.0  
> 기준일: 2026-08-11  
> 작성: Codex  
> 대상 키트: `KIT-MFG-NONFERROUS-PROCUREMENT` 1.0.0  
> 기준 규격: `SAMPLE_COMPANY_STARTER_KIT_MASTER_SPEC_2026-08-11.md`  
> 적용 관문: G2-B 데이터 키트, G2-D MVA 부트스트랩, G3 앱 연결, G4 계산·시나리오  
> 원칙: 구현 완료가 우선이며 실제 회사 수치의 정확도는 운영 도입 전·사용 과정에서 보정한다. 합성값을 Actual로 표현하지 않는다.

---

## 1. 수행 목표

이 계획의 목표는 35개 데이터 패키지를 단순 파일 목록으로 만드는 것이 아니라 다음 상태까지 준비하는 것이다.

```text
데이터 요구사항 정의
  → 계약·Excel 양식·샘플 준비
  → 인과형 합성 데이터 생성
  → 품질·대사 검증
  → 카탈로그·MDM·계보·권한 등록
  → 사전 앱·시뮬레이션·보고서 연결
  → 사용자가 자기 회사 데이터로 교체 가능한 상태
```

첫 번째 출구 조건은 **샘플 회사 Full Demo 폐루프 완주**다. 실제 회사 데이터의 `CERTIFIED ACTUAL` 발급은 그 다음 단계이며, 현재 구현을 멈추는 선행 조건으로 두지 않는다.

---

## 2. 적용 원칙

### 2.1 데이터 작성 원칙

1. 업무 언어로 먼저 정의하고 원천 테이블명은 Crosswalk에서 연결한다.
2. 모든 데이터셋에 조직 범위·기간·단위·버전·출처·종류를 넣는다.
3. 생성 순서는 원인→사건→결과 순서로 고정한다.
4. 수량·금액·기간·참조 무결성을 자동 대사한다.
5. 불일치는 자동으로 숨기지 않고 `QUARANTINE` 또는 생성 실패로 처리한다.
6. 사용자가 업로드할 양식과 시스템 샘플의 스키마를 동일하게 유지한다.
7. 외부 협업 데이터는 범용 Query Contract로만 정의한다.
8. 샘플 데이터와 실제 데이터는 저장·화면·API·계보에서 분리한다.

### 2.2 업무 범위 원칙

- 첫 수직 폐루프에 필요한 데이터부터 만든다.
- 공장 전체 센서·전표·ERP 전체 복제는 하지 않는다.
- 앱과 Twin이 실제로 소비하지 않는 필드는 첫 버전에서 제외한다.
- 실제 원천 접근 전에도 Reference·Synthetic 데이터로 API와 화면을 완성한다.
- 실제 데이터 도입 시 계약을 바꾸는 것이 아니라 Mapping만 추가하는 구조를 목표로 한다.

---

## 3. 전체 Wave와 산출물

| Wave | 목표 | 주요 산출물 | 출구 조건 |
|---|---|---|---|
| W0 | 기준선·규약 고정 | manifest, ID·분류·폴더 규칙 | 모든 팀원이 같은 키트 범위를 사용 |
| W1 | 회사·MDM 기반 | FND 3종, MDM 8종 | 조직·코드·단위 참조가 유효 |
| W2 | 구매·물류 사건 | PRC 2종, LOG 5종 | 계약→발주→선적→입고 추적 |
| W3 | 재고·생산·품질 | INV 2종, MFG 3종, QLT 1종 | 물량 대사와 생산 영향 계산 |
| W4 | 판매·재무·계획 | SLS 1종, FIN 3종 | 원가·손익·현금 연결 |
| W5 | 외부·지식·Twin | EXT 3종, KNW, SIM 2종 | Driver·시나리오·근거 연결 |
| W6 | 결정·앱·보고서 | DEC, 앱 5종, 보고서 5종 | 결정→실행→효과의 샘플 폐루프 |
| W7 | 사용자 온보딩 | Excel 35종, 복사·교체 흐름 | 샘플→회사 데이터 교체 가능 |
| W8 | 실제 데이터 준비 | Source Inventory, Mapping, 대사 | 최소 1개 RAW→CERTIFIED 추적 준비 |

W1~W5는 계약 확정 후 일부 병렬화할 수 있다. 단, 하위 거래 데이터는 상위 MDM 키가 고정되기 전에 등록하지 않는다.

---

## 4. 공통 납품물 규격

### 4.1 데이터셋별 파일

```text
contracts/{dataset_id}.contract.json
templates/{dataset_id}.onboarding.xlsx
samples/quick/{dataset_id}.csv
samples/full/{dataset_id}.parquet 또는 csv
generators/{dataset_id}.rules.json
validations/{dataset_id}.quality.json
validations/{dataset_id}.reconciliation.json
mappings/{dataset_id}.canonical_codes.json
catalog/{dataset_id}.asset.json
lineage/{dataset_id}.lineage.json
```

### 4.2 계약 JSON 필수 블록

```text
identity        dataset_id, name, version, status
scope           tenant, allowed scope types, owner
classification  data class, origin, sensitivity
schema          fields, type, nullable, unit, business key
references      foreign key, master entity, crosswalk rule
quality         validation rules, threshold, severity
reconciliation  count/sum/balance equations, tolerance
freshness       frequency, latency, stale rule
lineage         source, transform, consumer
authorization   read/write/approve capabilities
usage           apps, simulations, reports, queries
```

### 4.3 Excel 공통 Sheet

| Sheet | 준비 내용 | 자동화 목표 |
|---|---|---|
| README | 목적·담당·준비 순서·주의 | 데이터 준비 상담 에이전트가 설명에 사용 |
| DATA_DICTIONARY | 컬럼·형식·단위·예시 | 계약 JSON에서 자동 생성 |
| CODE_MAP | 원천↔표준 코드 | Crosswalk 후보 생성 |
| SAMPLE | 완성 예시 | 샘플 회사 데이터에서 추출 |
| INPUT | 사용자 입력 | 업로드 원본 |
| VALIDATION | 오류·경고·행 번호 | 등록 전 로컬 검증 |
| RESULT | 등록 가능 여부·다음 작업 | 준비도 보드와 연결 |

---

## 5. 데이터 등록 준비 상세 목록

### 5.1 기반·회사·권한

#### FND-01 기업·조직 계층

| 항목 | 내용 |
|---|---|
| 핵심 필드 | node_id, node_type, parent_id, code, name, entity_mode, industry_code, effective_from/to |
| Quick/Full | 7 / 15~25 노드 |
| 준비 원천 | 가상기업 구조, ECM 표준 |
| 품질 | 부모 존재, 순환 없음, 동일 부모 내 코드 중복 없음, 유효기간 일치 |
| 등록 | Enterprise Context Master, 카탈로그, 조직 범위 |
| 소비 | 전 화면 문맥, 권한, 데이터 바인딩, Twin 집계 |
| 완료 | 그룹→법인→사업부→공장 탐색과 상속 범위 테스트 통과 |

#### FND-02 사용자·역할·권한

| 항목 | 내용 |
|---|---|
| 핵심 필드 | user_id, department_id, role_id, scope_node_id, capability, effect, effective_from/to |
| Quick/Full | 8 / 24 사용자, 6 / 8~12 역할 |
| 준비 원천 | 예시 업무 Persona와 조직 |
| 품질 | 모든 사용자는 유효 조직 소속, 미바인딩 권한 없음, 역할 충돌 표시 |
| 등록 | 조직·권한 저장소, 테스트 계정 시드 |
| 소비 | 데이터·앱·결정·보고서 범위 |
| 완료 | 구매·물류·생산·재무·경영진·감사 역할별 허용/차단 매트릭스 통과 |

#### FND-03 달력·통화·단위·환산

| 항목 | 내용 |
|---|---|
| 핵심 필드 | calendar_id, date, fiscal_period, currency, uom, conversion_factor, effective_date |
| Quick/Full | 1년 / 5년 달력, 핵심 통화·단위 |
| 준비 원천 | ISO 통화·단위 후보, 회사 회계기간 예시 |
| 품질 | 변환 역수·기간 공백·중복·유효기간 검증 |
| 등록 | MDM·용어·계산 엔진 |
| 소비 | 모든 수량·환율·재무 계산 |
| 완료 | TON↔KG, USD↔KRW, 일↔월 집계 회귀 통과 |

### 5.2 MDM·업무 표준

#### MDM-01 품목·제품·원료

| 항목 | 내용 |
|---|---|
| 핵심 필드 | material_id, code, aliases, type, grade, base_uom, valuation_class, scope |
| Quick/Full | 30 / 180~300 |
| 생성 | 원료·WIP·제품·부산물·소모품 비율 규칙 |
| 품질 | 코드 중복 0, 별칭 충돌, 단위 필수, 유효기간·조직 범위 |
| 등록 | MDM, 용어사전, 카탈로그 |
| 소비 | 구매·재고·BOM·생산·판매·원가 |
| 완료 | 자연어·코드·동의어로 같은 품목 검색, 타 법인 격리 |

#### MDM-02 공급사·파트너

| 항목 | 내용 |
|---|---|
| 핵심 필드 | supplier_id, country, material_group, lead_time, payment_terms, risk_grade, active |
| Quick/Full | 10 / 30~50 |
| 생성 | 핵심·대체·Spot 공급사, 국가·리드타임·위험 분포 |
| 품질 | 국가·통화·지급조건 참조, 공급 가능 품목 1개 이상 |
| 등록 | MDM, 공급 위험 그래프 |
| 소비 | 계약·발주·대체 공급사 시나리오 |
| 완료 | 공급사 중단 시 대체 관계와 추가비용 계산 가능 |

#### MDM-03 고객·시장

| 항목 | 내용 |
|---|---|
| 핵심 필드 | customer_id, market, country, currency, credit_terms, product_group |
| Quick/Full | 8 / 20~30 |
| 품질 | 시장·통화·신용조건 참조, 판매 제품 매핑 |
| 등록 | MDM, 판매·재무 범위 |
| 소비 | 판매계획·매출·채권·수요 시나리오 |
| 완료 | 고객·시장별 매출·현금 집계 가능 |

#### MDM-04 공장·창고·저장 위치

| 항목 | 내용 |
|---|---|
| 핵심 필드 | site_id, warehouse_id, storage_location, material_class, capacity, owner_scope |
| Quick/Full | 공장 1·창고 3 / 공장 3·창고 8 |
| 품질 | 조직 노드 존재, 용량·단위 유효, 저장 품목 호환 |
| 등록 | ECM·MDM·재고 범위 |
| 소비 | 재고·입고·공장 간 이동·안전재고 |
| 완료 | 위치별 재고 합계가 공장·법인 집계와 일치 |

#### MDM-05 BOM·수율·부산물

| 항목 | 내용 |
|---|---|
| 핵심 필드 | bom_id, output_material, input_material, quantity, yield, byproduct, version, dates |
| Quick/Full | 8 / 25~40 구조 |
| 품질 | 순환 없음, 품목 존재, 수율 범위, 단위 환산, 버전 중첩 금지 |
| 등록 | MDM·계산식·계보 |
| 소비 | 소요량·원가·생산·수율 시나리오 |
| 완료 | 제품 수요에서 원료 소요량 역산 가능 |

#### MDM-06 Routing·설비·생산능력

| 항목 | 내용 |
|---|---|
| 핵심 필드 | routing_id, operation_seq, equipment_id, rate, setup_time, capacity, OEE |
| Quick/Full | 설비 12 / 40~60, Routing 10 / 30~50 |
| 품질 | 공정 순서·설비·단위·가동시간·능력 유효 |
| 등록 | MDM·공정 그래프·Twin |
| 소비 | 생산 가능량·납기·정지 영향 |
| 완료 | 수요·재고·설비 중단 조건으로 생산 가능량 계산 |

#### MDM-07 계정·원가요소·원가센터

| 항목 | 내용 |
|---|---|
| 핵심 필드 | account_id, account_type, cost_element, cost_center, P&L_line, cashflow_line |
| Quick/Full | 핵심 30 / 80~150 계정 |
| 품질 | 계정 분류·조직·손익·현금흐름 매핑 완결 |
| 등록 | MDM·재무 의미 모델 |
| 소비 | 원가·예산·회계·손익·현금 보고서 |
| 완료 | 모든 재무 행이 손익 또는 대차·현금 분류에 연결 |

#### MDM-08 계약조건·항만·운송구간

| 항목 | 내용 |
|---|---|
| 핵심 필드 | incoterm, payment_term, port_id, lane_id, mode, standard_lead_time, currency |
| Quick/Full | 핵심 조건 10 / 운송구간 30~50 |
| 품질 | 출발·도착·운송수단·기간·책임 경계 유효 |
| 등록 | MDM·Crosswalk·물류 의미 모델 |
| 소비 | 계약·운임·ETA·위험 시나리오 |
| 완료 | 계약조건에 따른 비용·위험 귀속 계산 |

### 5.3 구매·외부 협업·물류

#### PRC-01 구매계약·가격조건

| 항목 | 내용 |
|---|---|
| 핵심 필드 | contract_id, supplier_id, material_id, quantity, index, premium, currency, incoterm, payment |
| Quick/Full | 20 / 80~120 계약 |
| 생성 | 장기·분기·Spot 계약 혼합, 가격식·상하한·유효기간 |
| 품질 | 공급사·품목·조건 참조, 계약량·소진량, 가격식 입력 완결 |
| 등록 | 운영 데이터·계약 카탈로그·계보 |
| 소비 | 발주·구매원가·공급 위험·현금 |
| 완료 | 외부가격과 환율로 계약 가격 재현 |

#### PRC-02 구매주문·납기 일정

| 항목 | 내용 |
|---|---|
| 핵심 필드 | po_id, line_id, contract_id, order_date, due_date, quantity, price, status |
| Quick/Full | 200 / 1,500~2,500 행 |
| 생성 | 생산 소요·안전재고·리드타임에서 발주 역산 |
| 품질 | 계약 참조, 계약량 초과, 날짜 순서, 수량·통화·단위 |
| 등록 | App Data Plane·운영 데이터·계보 |
| 소비 | 도입계획 앱·선적·재고 전망 |
| 완료 | PO→계약→품목→공장 경로 추적 |

#### LOG-01 파트너 제출 상태

| 항목 | 내용 |
|---|---|
| 핵심 필드 | source_system, partner_id, business_ref, submission_status, submitted_at, revised_at |
| 생성 | 외부 협업 시스템 Fixture, 미제출·수정·완료 상태 |
| 품질 | 개인정보 제외, 원천 사건·키·버전 보존, 중복 멱등 |
| 등록 | 범용 Query Contract `partner_submission` |
| 소비 | 구매·물류 담당 알림, 결손 데이터 보드 |
| 완료 | 특정 LPL 스키마 없이 Adapter Profile로 조회 가능 |

#### LOG-02 선적 헤더·운송편

| 항목 | 내용 |
|---|---|
| 핵심 필드 | shipment_id, po_line_id, vessel_or_mode, origin, destination, quantity, freight |
| Quick/Full | 120 / 1,000~1,500 |
| 생성 | PO 분할 선적, 운송구간·용량·리드타임 기반 |
| 품질 | PO 수량 대비 선적량, 항만·운송구간 참조, 중복 없음 |
| 등록 | 운영 데이터·물류 그래프 |
| 소비 | 도입 추적·운임·ETA·입고 전망 |
| 완료 | PO→선적→통관→입고 한 경로 조회 |

#### LOG-03 선적 Milestone

| 항목 | 내용 |
|---|---|
| 핵심 필드 | shipment_id, event_type, planned_at, actual_at, location, status, source_version |
| Quick/Full | 800 / 8,000~15,000 사건 |
| 생성 | Booking→Pickup→ETD→ETA→ATA→Unloading 순서 |
| 품질 | 사건 순서·시간 역전·중복·late-arrival 검증 |
| 등록 | Query Contract `shipment_milestone` |
| 소비 | 지연 감지·재고부족·생산 영향 |
| 완료 | 계획과 실적 ETA 차이 및 영향 계산 |

#### LOG-04 통관·검사·관세

| 항목 | 내용 |
|---|---|
| 핵심 필드 | clearance_id, shipment_id, declaration, inspection, duty, cleared_at, status |
| Quick/Full | 100 / 800~1,200 |
| 생성 | 정상·검사·보류·정정 사례 |
| 품질 | 선적 참조, 날짜 순서, 통화·세율·금액 대사 |
| 등록 | Query Contract `customs_clearance` |
| 소비 | 입고 가능일·도입원가·지연 영향 |
| 완료 | 통관 보류가 재고·생산에 미치는 경로 계산 |

#### LOG-05 내륙 운송 Milestone

| 항목 | 내용 |
|---|---|
| 핵심 필드 | transport_id, shipment_id, dispatch, pickup, gate_in, delivered, status |
| 생성 | 항만→공장 운송과 부분 도착 |
| 품질 | 선적·차량/운송편·도착 수량·시간 순서 |
| 등록 | Query Contract `transport_milestone` |
| 소비 | 공장 입고 예측·물류 담당 앱 |
| 완료 | 도착 사건이 입고·재고 Snapshot으로 이어짐 |

### 5.4 재고·생산·품질

#### INV-01 재고 스냅샷

| 항목 | 내용 |
|---|---|
| 핵심 필드 | snapshot_date, site, location, material, lot, unrestricted, quality, blocked, safety_stock |
| Quick/Full | 2,000 / 15,000~25,000 행 |
| 생성 | 전일 재고와 당일 이동에서 산출 |
| 품질 | 음수·단위·위치·품목, 이동 원장과 수량 대사 |
| 등록 | 운영 Snapshot·카탈로그 |
| 소비 | 안전재고·생산 가능량·운전자본 |
| 완료 | 기초+이동=기말 등식 통과 |

#### INV-02 재고 이동·Lot

| 항목 | 내용 |
|---|---|
| 핵심 필드 | movement_id, date, type, material, lot, from/to, quantity, reference |
| Quick/Full | 5,000 / 30,000~50,000 |
| 생성 | 입고→투입→산출→이동→출하 사건에서 생성 |
| 품질 | 참조 사건·수량 부호·위치·Lot 계보·중복 |
| 등록 | 운영 원장·계보 |
| 소비 | 재고 Snapshot·원료 추적·제품 계보 |
| 완료 | 원료 Lot에서 제품 Lot까지 추적 |

#### MFG-01 생산계획·소요량

| 항목 | 내용 |
|---|---|
| 핵심 필드 | plan_id, period, site, product, quantity, priority, material_requirement, capacity_requirement |
| Quick/Full | 800 / 5,000~8,000 |
| 생성 | 판매계획·안전재고·BOM·Routing에서 계산 |
| 품질 | BOM·능력·기간·공장·단위 일치 |
| 등록 | Planning Engine·운영 계획 |
| 소비 | 구매계획·재고·납기·Twin |
| 완료 | 제품 계획 변화가 원료 소요·구매로 전파 |

#### MFG-02 생산실적·수율

| 항목 | 내용 |
|---|---|
| 핵심 필드 | batch_id, date, site, input_lot, output_lot, input_qty, output_qty, yield, downtime |
| Quick/Full | 1,000 / 7,000~12,000 |
| 생성 | 계획·설비 가동·수율 분포·품질 조건 기반 |
| 품질 | 투입·산출·부산물·스크랩 물량 대사, 수율 범위 |
| 등록 | 운영 실적·계보·Twin 보정 |
| 소비 | 실적·원가·수율 시나리오 |
| 완료 | 생산실적에서 재고·원가·품질까지 연결 |

#### MFG-03 가동·고장·정비

| 항목 | 내용 |
|---|---|
| 핵심 필드 | event_id, equipment_id, start/end, event_type, planned, root_cause, capacity_loss |
| 생성 | MTBF·MTTR 기반이되 생산계획과 겹침 반영 |
| 품질 | 시간 중첩·설비·가동시간·손실능력 검증 |
| 등록 | 설비 실적·Twin Driver |
| 소비 | OEE·생산능력·정지 시나리오 |
| 완료 | 정지 사건이 생산·출하·매출에 전파 |

#### QLT-01 입고·공정·제품 품질

| 항목 | 내용 |
|---|---|
| 핵심 필드 | inspection_id, object_type, lot, characteristic, result, spec, verdict, action |
| Quick/Full | 1,500 / 10,000~20,000 |
| 생성 | 품목 규격·공정 상태·공급사 위험 기반 |
| 품질 | 규격 버전·단위·검사 대상·판정 규칙 |
| 등록 | 품질 원장·지식·계보 |
| 소비 | 가용재고·수율·클레임·공급사 평가 |
| 완료 | 부적합이 보류재고·생산·원가에 반영 |

### 5.5 판매·재무·계획

#### SLS-01 판매계획·수주·출하

| 항목 | 내용 |
|---|---|
| 핵심 필드 | customer, product, plan/order/shipment, quantity, price, currency, due_date, actual_date |
| Quick/Full | 300 / 2,000~4,000 |
| 생성 | 시장·고객·계절성·시나리오 기반 |
| 품질 | 고객·품목·통화·출하·매출 참조, 중복·기간 |
| 등록 | 판매·매출 운영 데이터 |
| 소비 | 생산계획·매출·채권·수요 시나리오 |
| 완료 | 수요 변화가 생산·재고·손익에 연결 |

#### FIN-01 표준원가·실제원가

| 항목 | 내용 |
|---|---|
| 핵심 필드 | period, product, cost_component, standard_amount, actual_amount, quantity, currency |
| 생성 | 구매원가·BOM·가동·품질·물류에서 계산 |
| 품질 | 원가요소·제품·기간·통화, 구성요소 합계 대사 |
| 등록 | 재무 의미 모델·Twin |
| 소비 | 원가차이·마진·시나리오 |
| 완료 | 원료·운임·수율 변화의 제품원가 영향 분해 |

#### FIN-02 매입·미지급·매출채권

| 항목 | 내용 |
|---|---|
| 핵심 필드 | document_id, partner, reference, posting_date, due_date, amount, currency, paid_at |
| 생성 | 입고·Invoice·판매·지급조건에서 생성 |
| 품질 | 원천 사건·금액·통화·지급·회수 대사 |
| 등록 | AP/AR·현금 전망 |
| 소비 | 운전자본·현금흐름·연체 위험 |
| 완료 | 구매·판매 사건이 지급·회수 일정으로 연결 |

#### FIN-03 예산·회계실적·현금흐름

| 항목 | 내용 |
|---|---|
| 핵심 필드 | ledger, period, account, cost_center, actual/plan, amount, currency, cashflow_line |
| Quick/Full | 5,000 / 30,000~60,000 |
| 생성 | 운영 사건을 계정 규칙으로 전환, 계획은 별도 생성 |
| 품질 | 차변·대변 또는 관리손익 균형, 기간·계정·통화·조직 대사 |
| 등록 | 경영계획·실적·현금 기준선 |
| 소비 | 손익·현금·경영 보고·Twin |
| 완료 | 운영 KPI와 재무 KPI의 영향 경로 재현 |

### 5.6 외부환경·지식·시뮬레이션·결정

#### EXT-01 환율·금리·물가

| 항목 | 내용 |
|---|---|
| 핵심 필드 | indicator, geography, observed_at, published_at, vintage, value, unit, source, grade |
| 준비 | 공식 원천 Reference Fixture + 합성 미래 시나리오 분리 |
| 품질 | 관측일·발표일·수정판·단위·결측·중복 |
| 등록 | External Intelligence·Snapshot |
| 소비 | 환산·금융비용·거시 시나리오 |
| 완료 | 과거 시점 Vintage를 사용한 Replay 가능 |

#### EXT-02 원자재·제품 기준가격

| 항목 | 내용 |
|---|---|
| 핵심 필드 | commodity, benchmark, date, price, currency, unit, source, grade |
| 준비 | 공식·검증 기준가격. 회사 계약단가 대체 금지 |
| 품질 | 단위·통화·시장·공표시점·수정판 |
| 등록 | External Intelligence·Driver Mapping |
| 소비 | 계약가격·제품가격·시나리오 |
| 완료 | 계약별 index+premium 가격 재현 |

#### EXT-03 운임·에너지·기상·산업지표

| 항목 | 내용 |
|---|---|
| 핵심 필드 | indicator, route/site/industry, date, value, unit, source, grade |
| 준비 | Reference 관측과 Scenario 값을 별도 저장 |
| 품질 | 사업장·운송구간 Mapping, 시차·단위·라이선스 |
| 등록 | External Intelligence·Driver Mapping |
| 소비 | 운임·가공원가·물류·수요 위험 |
| 완료 | 내부 KPI에 적용하는 산식과 승인 이력 존재 |

#### KNW-01 표준서·계약·규정·연구자료

| 항목 | 내용 |
|---|---|
| 핵심 필드 | document_id, title, type, scope, classification, owner, effective dates, approval, source |
| 준비 | `docs/reference` 등록부를 후보로 사용, 승인 전 주입 금지 |
| 품질 | checksum·추출 가능·중복·유효기간·권한·라이선스 |
| 등록 | 지식팩·카탈로그·계보 |
| 소비 | Jarvis 설명·데이터 준비 안내·검토서 근거 |
| 완료 | 답변마다 문서 근거·범위·기준시점 표시 |

#### SIM-01 Driver·계산식·제약

| 항목 | 내용 |
|---|---|
| 핵심 필드 | driver_id, input_metric, output_metric, formula, lag, unit_rule, scope, version, approval |
| 준비 | 재고·구매원가·생산능력·원가·손익·현금 등식 |
| 품질 | 입력·출력 존재, 단위 일치, 순환·결손, 유효기간 |
| 등록 | Planning Engine·Calc Bridge·계보 |
| 소비 | 모든 경영 시나리오 |
| 완료 | 동일 입력에서 결정론적 동일 결과, 근거 경로 반환 |

#### SIM-02 기준·위험·대안 시나리오

| 항목 | 내용 |
|---|---|
| 핵심 필드 | scenario_id, baseline_id, driver changes, period, scope, rationale, approval, result_ref |
| Quick/Full | 3 / 10 이상 |
| 준비 | Master Spec §10 Golden Case |
| 품질 | Actual 변경 금지, 기준선 참조, 단위·범위·기간·승인 |
| 등록 | Scenario Workbench·결정 원장 |
| 소비 | Twin·보고서·의사결정 |
| 완료 | 기준·대안 결과와 차이 원인 분해 가능 |

#### DEC-01 결정·실행과제·효과

| 항목 | 내용 |
|---|---|
| 핵심 필드 | decision_id, package_id, scenario_id, requester, approver, decision, action, KPI_before/target/actual |
| 준비 | 10개 Golden Case 중 3개 대표 폐루프 이력 |
| 품질 | 결정–실행–증빙–효과 참조 무결성, 권한·시간 순서 |
| 등록 | Decision Ledger·회의·실행과제·효과 측정 |
| 소비 | 세 관점 검토서·Jarvis·학습 환류 |
| 완료 | 기대와 실제 차이를 데이터·가정·모델·실행으로 분해 |

---

## 6. 인과형 합성 데이터 생성 순서

합성 생성기는 다음 DAG 순서를 따른다.

```text
FND-01~03
  ↓
MDM-01~08
  ↓
EXT-01~03 + SLS-01 계획
  ↓
MFG-01 생산계획·소요량
  ↓
PRC-01 계약 → PRC-02 발주
  ↓
LOG-01~05 물류·통관
  ↓
QLT-01 입고검사 → INV-02 이동 → INV-01 Snapshot
  ↓
MFG-03 가동 → MFG-02 생산실적 → QLT-01 공정·제품검사
  ↓
SLS-01 출하·매출
  ↓
FIN-01 원가 → FIN-02 AP/AR → FIN-03 손익·현금
  ↓
SIM-01 계산 → SIM-02 시나리오 → DEC-01 결정·효과
```

### 6.1 생성기 설정

```text
profile                QUICK/FULL
start_date/end_date    기간
company_profile        조직 규모
random_seed            재현성
seasonality            수요 계절성
growth_rate            기준 성장률
volatility             외부지표·납기·수율 변동
shock_events            지연·고장·가격충격
quality_defect_rate     품질 변동
payment_behavior        지급·회수 편차
scenario_overlay        What-if 변경
```

### 6.2 데이터 누락도 의도적으로 생성한다

Full Demo에는 완전 정상 데이터만 넣지 않는다. 제품의 데이터 준비 기능을 보여주기 위해 다음 결손을 통제된 비율로 포함한다.

- 원천 코드 미매핑
- 중복 선적 Milestone
- 통관 정정 사건
- 늦게 도착한 실적
- 단위 불일치 후보
- 품질 보류 재고
- 계획 대비 생산 편차
- 미제출 파트너 상태

오류는 `expected_quarantine_manifest.json`에 예상 건수와 이유를 기록한다. 검증 결과가 이 manifest와 달라지면 실패한다.

---

## 7. 대사·검증 계획

### 7.1 물량 대사

| 대사 | 기준 |
|---|---|
| 계약량 | 계약량 ≥ 누적 발주량, 예외 계약은 명시 |
| 발주–선적 | 발주량 = 선적량 + 미선적량 ± 취소·정정 |
| 선적–입고 | 선적량 = 입고량 + 운송중 + 허용 손실 |
| 재고 | 기초 + 입고 + 생산 - 투입 - 출하 ± 조정 = 기말 |
| 생산 | 투입 = 제품 + 부산물 + 스크랩 + 공정 손실 |

### 7.2 금액 대사

| 대사 | 기준 |
|---|---|
| 계약가격 | index + premium + 조건별 조정 |
| 도입원가 | 상품가 + 운임 + 보험 + 관세 + 부대비용 |
| 매입 | 입고·Invoice·환율·세금과 연결 |
| 원가 | 재료 + 가공 + 물류 + 품질 손실 |
| 손익 | 제품별 원가와 매출 집계가 회사 손익과 일치 |
| 현금 | AP/AR 지급·회수와 현금잔액 변화 일치 |

### 7.3 시간·사건 검증

- 계약 유효일 ≤ 발주일
- 발주일 ≤ 선적 예정·실적 사건
- ETD ≤ ETA, 실제 정정은 버전으로 보존
- 통관 완료 ≤ 내륙 운송 완료 ≤ 입고
- 생산 투입 전에 가용재고 존재
- 출하 전에 완제품 생산·가용재고 존재
- 회계기간과 업무일자의 허용 관계 준수

### 7.4 Golden Case 허용 오차

- 결정론적 수량 등식: 0 또는 정의된 반올림 오차
- 통화 환산: 소수점·환율 기준에 따른 명시 오차
- 확률적 생성 분포: 지정 신뢰구간과 Seed 일치
- 시나리오 KPI: `expected_results.json`의 항목별 허용 오차
- 보고서 서술: 숫자·방향·근거 ID 일치, 문장 동일성은 요구하지 않음

---

## 8. 등록 배선 계획

### 8.1 등록 순서

```text
1. Starter Kit manifest 등록
2. 데이터 계약 등록
3. 카탈로그 자산 등록
4. 회사·조직·권한 등록
5. MDM·용어·Crosswalk 등록
6. 합성 RAW 또는 SYNTHETIC 영역 적재
7. 품질·대사 실행
8. STANDARDIZED/SYNTHETIC 승인 상태 기록
9. 계보·Snapshot 등록
10. 앱·시나리오·보고서 연결
```

### 8.2 저장 경계

| 자산 | 저장 경계 |
|---|---|
| 키트 manifest·계약·템플릿 | 버전 관리 제품 자산 |
| 합성 거래 데이터 | 샘플 회사 전용 데이터 영역 |
| 회사 실제 RAW | 회사·조직별 불변 원천 저장소 |
| MDM·Crosswalk | 기준정보 저장소와 조직 바인딩 |
| 외부 관측 | External Intelligence 저장소 |
| 지식 문서 | 원본 저장소 + 승인된 검색 인덱스 |
| 시나리오·결과 | Planning/Twin 저장소와 Snapshot 참조 |
| 결정·실행·효과 | Decision Ledger·업무 증빙 저장소 |

`pipeline_state.db`와 LLM 프롬프트에 원본 거래 데이터 전체를 복제하지 않는다.

### 8.3 Loader 공통 동작

- dry-run 지원
- manifest·checksum 검증
- 동일 kit/version 멱등 처리
- 범위 미지정 Fail-closed
- 사용자 개정값 자동 덮어쓰기 금지
- 오류 행 QUARANTINE 분리
- 등록 건수·합계·오류·소요시간 반환
- 카탈로그·계보·품질 결과 생성
- 실행 전후 Snapshot ID 기록

---

## 9. 사용자 경험 구현 요구사항

### 9.1 Starter Kit 선택 화면

카드에 다음을 표시한다.

- 업종·업무 범위
- 포함 앱·시나리오·보고서
- 필요한 데이터와 현재 준비도
- Quick/Full 예상 데이터량
- 합성 데이터임을 알리는 고정 배지
- `샘플 회사로 체험`과 `우리 회사에 복사`

### 9.2 데이터 준비 보드

| 열 | 내용 |
|---|---|
| 데이터 | 업무 언어의 데이터셋 이름 |
| 필요한 이유 | 사용하는 앱·계산·보고서 |
| 현재 상태 | 샘플/파일 보유/연결 가능/부족/검증 필요 |
| 품질·승인 | 오류·경고·대사·오너 승인 |
| 지금 가능한 것 | 실행 가능한 기능 |
| 막힌 것 | 계산·보고·결정 차단 사유 |
| 다음 행동 | 업로드·매핑·대사·승인·연결 |
| 담당·기한 | 데이터 오너·실무 담당 |

### 9.3 데이터 교체 경험

사용자가 실제 데이터를 등록하면 샘플 행을 물리적으로 덮어쓰지 않는다. 동일 데이터셋에서 `data_class`, `snapshot_id`, `scope`, `period`로 병렬 관리하고 화면에서 기준선을 선택한다.

```text
[샘플 기준선]
[회사 파일 기준선]
[CERTIFIED 실제 기준선]
[시나리오 기준선]
```

---

## 10. 역할과 협업

역할은 고정 경계가 아니라 기본 주도 기준이다.

| 업무 | 기본 주도 | 교차검토 |
|---|---|---|
| 키트 제품 범위·사용자 흐름 | Codex | Supervisor, Claude Code |
| 외부 원천·산업 기준·라이선스 | Antigravity | Supervisor |
| 계약·Loader·DB·API 구현 | Claude Code | Codex 데이터 UX, Antigravity 검증 |
| 합성 생성·대사·Golden Case | Antigravity/Claude Code | Codex 제품 의미, Supervisor 도메인 판단 |
| 실제 회사 값·오너·허용 오차 | Supervisor·현업 데이터 오너 | 팀 지원 |
| UI·온보딩 워크북 경험 | Codex | Claude Code 구현 가능성 |

실제 수치 승인 부재는 Synthetic 구현을 막지 않는다. 다만 `CERTIFIED ACTUAL` 승격은 데이터 오너 없이는 수행하지 않는다.

---

## 11. 일정과 우선순위

아래는 구현 준비 범위이며 다른 P0 보안 작업과 병행한다.

### Sprint DK-0 — 규격·기반

- manifest schema
- 데이터 계약 공통 schema
- ID·분류·범위·버전 규칙
- 폴더·Loader 인터페이스
- 가상기업 조직 Profile

출구: FND·MDM 계약을 코드 없이도 검토 가능.

### Sprint DK-1 — Quick Demo

- FND 3종, MDM 8종
- 구매·물류 최소 데이터
- 6개월 Quick 데이터
- 시나리오 3개
- 앱 3개에 연결할 Fixture

출구: 10분 제품 체험 경로 동작.

### Sprint DK-2 — Full 운영 데이터

- 재고·생산·품질·판매·재무
- 36개월 시계열
- 물량·금액 대사
- 통제된 QUARANTINE

출구: 기준선 손익·현금·재고 계산 재현.

### Sprint DK-3 — Twin·결정

- 외부 Driver
- 시나리오 10개
- Golden Case
- 앱 5개·보고서 5개·DEC 이력

출구: 기준→시나리오→결정→실행→효과 샘플 폐루프.

### Sprint DK-4 — 온보딩·교체

- Excel 35종
- 업로드·검증·Crosswalk
- 샘플→회사 데이터 복사
- 준비도 보드

출구: 사용자가 안내에 따라 첫 데이터셋을 교체.

### Sprint DK-5 — MVA 실제 데이터 연결 준비

- Source Inventory
- 원천별 Adapter Profile
- RAW Snapshot·checksum
- 대사·Certification UI

출구: 실제 데이터 하나를 RAW→CERTIFIED로 승격할 준비.

---

## 12. 테스트 계획

### 12.1 계약 테스트

- 35개 데이터셋 계약 schema 유효
- manifest 의존성 순환 없음
- 모든 FK가 MDM·ECM 계약을 참조
- 필수 scope·기간·단위·분류 존재

### 12.2 생성기 테스트

- 같은 Seed 동일 결과
- Quick·Full 크기 조건
- 물량·금액·시간 대사
- 의도된 QUARANTINE만 발생
- 가상기업과 REAL 데이터 영역 혼합 없음

### 12.3 등록 테스트

- dry-run 결과와 실제 등록 일치
- 재실행 멱등
- 사용자 개정값 보존
- 미바인딩 Fail-closed
- 카탈로그·계보·품질 결과 생성

### 12.4 소비자 테스트

- APP-01~05가 계약된 데이터만 사용
- 시뮬레이션이 Snapshot·산식 버전을 반환
- 보고서 숫자가 계산 결과와 일치
- 자연어 질문에 원천·시점·신뢰도 표시
- 데이터 제거 시 `BLOCKED_BY_DATA`

### 12.5 권한 테스트

- 법인·사업부·공장별 데이터 격리
- 구매 담당과 물류 담당의 쓰기 범위 차이
- 경영진 집계 권한과 원본 상세 권한 분리
- 가상 증설 공장 데이터가 운영 실적에 포함되지 않음
- 앱 전달이 데이터 권한을 확장하지 않음

---

## 13. 완료 체크리스트

### 키트 정본

- [ ] manifest 1.0.0 승인
- [ ] 가상기업 명칭·구조 승인
- [ ] 35개 데이터셋 계약 등록
- [ ] Quick·Full Profile 정의
- [ ] 분류·표시·계보 정책 적용

### 데이터 생성

- [ ] FND·MDM 생성
- [ ] 구매·물류 생성
- [ ] 재고·생산·품질 생성
- [ ] 판매·재무 생성
- [ ] 외부지표·시나리오 생성
- [ ] DEC 샘플 이력 생성

### 품질

- [ ] 물량 대사 통과
- [ ] 금액·손익·현금 대사 통과
- [ ] 시간·참조 무결성 통과
- [ ] 의도된 QUARANTINE 일치
- [ ] Golden Case 10개 허용 오차 통과

### 등록·활용

- [ ] 카탈로그·MDM·용어·계보 등록
- [ ] 앱 5개 연결
- [ ] 보고서 5개 연결
- [ ] Starter 질문 6개 근거 응답
- [ ] 샘플 회사 즉시 실행
- [ ] 우리 회사에 복사
- [ ] 실제 데이터 1종 교체 예행연습

---

## 14. 위험과 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| 합성값을 실제값으로 오인 | 제품 신뢰 훼손 | 고정 배지·data_class·보고서 워터마크·공식 결정 차단 |
| 데이터만 많고 인과가 없음 | 시뮬레이션 무의미 | DAG 생성·대사 등식·Golden Case |
| 특정 회사 구조에 고착 | 상품화 어려움 | 가상기업 Core + Company Overlay + Adapter Profile |
| Excel 양식과 API 계약 불일치 | 온보딩 실패 | 계약에서 Excel·검증 schema 자동 생성 |
| 외부 원천 값으로 내부 가격 대체 | 잘못된 경영 계산 | Reference Driver와 Actual 계약단가 분리 |
| 지식 문서 전수 주입 | 권한·토큰·정확도 문제 | 승인 지식팩·검색 후 필요한 근거만 주입 |
| 실제값 확정 대기로 구현 정지 | 제품 완성 지연 | Synthetic·Reference로 구현, CERTIFIED만 보류 |
| 고객별 필드 추가로 SI화 | 유지보수 붕괴 | 표준 계약 + Crosswalk + Overlay, Core 포크 금지 |

---

## 15. 즉시 착수 백로그

다른 기능 구현이 끝나는 즉시 다음 순서로 시작한다.

1. `starter_kit_manifest.schema.json` 작성
2. 35개 Dataset ID와 의존성 JSON 작성
3. FND-01~03·MDM-01~08 데이터 계약 작성
4. `AFS Demo Materials Group` 조직 Profile 작성
5. Quick Demo 기준정보 생성
6. 구매계약→발주→선적→입고 최소 생성기 작성
7. 재고 물량 대사기 작성
8. APP-01 원료 도입계획 Fixture 연결
9. Excel 공통 템플릿 1종을 FND-01로 검증
10. 검증된 패턴을 35개 데이터셋으로 확장

### 첫 검토 관문

다음 네 질문에 모두 답할 수 있을 때 DK-1로 넘어간다.

1. 사용자가 이 데이터가 왜 필요한지 이해할 수 있는가?
2. 생성 앱과 Twin이 같은 ID·단위·버전을 사용하는가?
3. 합성값과 실제값이 어떤 경로에서도 혼동되지 않는가?
4. 실제 회사 파일을 같은 계약으로 교체할 수 있는가?

---

## 16. 인계용 최종 요약

> 첫 번째 데이터 제품은 `KIT-MFG-NONFERROUS-PROCUREMENT`이다. 가상기업 `AFS 데모소재그룹`의 35개 데이터 패키지(운영 기준선 28개 + Twin·근거·결정 7개), 36개월 인과형 합성 데이터, 시나리오 10개, 앱 5개, 보고서 5개를 제공한다. 모든 값은 조직·기간·단위·출처·종류·품질·계보를 가지며 합성값은 Actual로 승격할 수 없다. 사용자는 샘플 회사를 즉시 체험한 뒤 같은 데이터 계약의 Excel·파일·연계 방식으로 자기 회사 데이터를 데이터셋 단위 교체한다. 첫 구현 순서는 manifest와 FND·MDM 계약, Quick Demo, 구매–물류–재고 최소 생성기, APP-01 연결이다.
