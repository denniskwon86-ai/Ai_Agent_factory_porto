# AI Factory Studio 두 번째 가상기업 데이터 등록 상세 수행계획: AFS 배터리케미컬

> 문서 상태: 수행계획 정본 1.0  
> 기준일: 2026-08-11  
> 작성: Gemini Antigravity (전담: 데이터·시뮬레이션·품질 검증)  
> 대상 기업: `AFS 배터리케미컬` (`KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT` v1.0.0)  
> 관련 문서: `SAMPLE_COMPANY_BATTERY_CHEMICAL_STARTER_KIT_SPEC_2026-08-11.md`

---

## 1. 수행 목표 및 범위

본 문서는 두 번째 가상기업인 `AFS 배터리케미컬`의 35개 데이터 패키지에 대한 상세 데이터 스키마, Quick/Full 생성 건수, 대사(Reconciliation) 규칙 및 자동 생성 스크립트 실행 방안을 확정합니다.

---

## 2. 35개 데이터 패키지 패키징 및 생성 계획

### 2.1 기반 및 마스터 데이터 (FND-01~03, MDM-01~08)

| ID | 데이터 패키지명 | 필수 필드 사양 | Quick 건수 | Full 건수 (36M) | 품질 및 참조 대사 규칙 |
|---|---|---|---:|---:|---|
| **FND-01** | 기업·조직 계층 | org_id, org_name, org_type, parent_id, legal_entity, currency | 8건 | 16건 | 계층 구조 무결성, 순환 참조 없음 |
| **FND-02** | 사용자·역할·권한 | user_id, user_name, role_code, scope_org_id, email, status | 15건 | 45건 | FND-01 유효 org_id 매핑 |
| **FND-03** | 달력·통화·단위 | date_key, currency_code, fx_rate, unit_code, unit_conv_factor | 180건 | 1,095건 | USD/KRW/EUR 환산계수 정합성 |
| **MDM-01** | 품목·원료 마스터 | item_code, item_name, item_category, spec, base_unit, cost_type | 25건 | 160건 | 원료/중간재/양극재 구분 명확화 |
| **MDM-02** | 공급사·파트너 | vendor_code, vendor_name, country, incoterms, credit_rating | 8건 | 35건 | 해외 리튬 광산사 및 화학공급사 |
| **MDM-03** | 고객·시장 | customer_code, customer_name, country, industry, priority | 3건 | 12건 | 글로벌 배터리 셀 제조사 |
| **MDM-04** | 공장·창고 위치 | location_id, plant_code, wh_name, is_hazmat, capacity_unit | 6건 | 18건 | 위험물 탱크터미널 및 창고 |
| **MDM-05** | BOM·수율 기준 | bom_id, parent_item, child_item, std_qty, std_yield_pct | 12건 | 48건 | 전구체+리튬 반응 표준 수율(92.5%) |
| **MDM-06** | Routing·설비 | routing_id, plant_code, eq_code, eq_name, std_capacity_hr | 10건 | 42건 | 공침 반응기 및 소성 킬른 설비 |
| **MDM-07** | 계정·원가요소 | account_code, account_name, cost_center, category_type | 20건 | 50건 | 원재료비, 전력비, 스팀비, 운반비 |
| **MDM-08** | 거래조건·단위 | term_id, incoterms_code, price_index_ref, payment_days | 8건 | 20건 | Fastmarkets/LME 지수 연동 조건 |

### 2.2 조달 및 물류 데이터 (PRC-01~02, LOG-01~05)

| ID | 데이터 패키지명 | 필수 필드 사양 | Quick 건수 | Full 건수 (36M) | 품질 및 참조 대사 규칙 |
|---|---|---|---:|---:|---|
| **PRC-01** | 구매계약·가격 | contract_no, vendor_code, item_code, base_price, formula | 10건 | 40건 | LME/Fastmarkets 지수 연동 수식 |
| **PRC-02** | 구매주문 (PO) | po_no, contract_no, order_date, item_code, qty, due_date | 35건 | 350건 | PO 수량 = 계약 잔여 수량 이하 |
| **LOG-01** | 파트너 제출 | event_id, po_no, vendor_code, coa_purity_pct, status | 30건 | 300건 | COA 순도 99.5% 이상 검증 |
| **LOG-02** | 선적·운송편 | vessel_id, vessel_name, pol_code, pod_code, bl_no, status | 20건 | 200건 | 호주 둔바항 → 포항항 해상 루트 |
| **LOG-03** | 선적 Milestone | milestone_id, vessel_id, event_type, etd_date, eta_date | 80건 | 800건 | ETD < ETA 순서 및 지연 사건 포함 |
| **LOG-04** | 통관·검사 | customs_id, bl_no, duty_amount, inspection_status | 20건 | 200건 | 수입 위험물 신고 및 관세 계산 |
| **LOG-05** | 내륙 운송 | transport_id, bl_no, truck_no, origin, dest, ata_date | 25건 | 250건 | 항만 → 포항/광양 공장 입고 |

### 2.3 재고, 생산 및 품질 데이터 (INV-01~02, MFG-01~03, QLT-01)

| ID | 데이터 패키지명 | 필수 필드 사양 | Quick 건수 | Full 건수 (36M) | 품질 및 참조 대사 규칙 |
|---|---|---|---:|---:|---|
| **INV-01** | 재고 스냅샷 | snapshot_date, location_id, item_code, qty, unit | 180건 | 1,095건 | 가용재고 + 입고예정 - 소요량 |
| **INV-02** | 재고 수불·Lot | txn_id, lot_no, item_code, txn_type, qty, txn_date | 120건 | 1,200건 | Lot 단위 입출고 무결성 100% |
| **MFG-01** | 생산계획 | plan_id, plant_code, item_code, plan_qty, plan_date | 30건 | 360건 | 월간 MRP 자재소요량 산출 연동 |
| **MFG-02** | 생산실적·수율 | actual_id, plan_id, actual_qty, actual_yield_pct | 150건 | 1,800건 | 실제 수율 = (생산량/투입량)*100 |
| **MFG-03** | 설비 가동·정비 | log_id, eq_code, run_hours, downtime_hours, reason | 90건 | 900건 | 비공정 킬른 소성로 온도 하락 건 |
| **QLT-01** | 입고·공정 품질 | test_id, lot_no, purity_pct, fe_ppm, status | 60건 | 600건 | 수산화리튬 Fe < 10ppm 합격판정 |

### 2.4 판매, 재무 및 시뮬레이션 데이터 (SLS-01, FIN-01~03, EXT-01~03, KNW-01, SIM-01~02, DEC-01)

| ID | 데이터 패키지명 | 필수 필드 사양 | Quick 건수 | Full 건수 (36M) | 품질 및 참조 대사 규칙 |
|---|---|---|---:|---:|---|
| **SLS-01** | 판매계획·수주 | so_no, customer_code, item_code, qty, price, ship_date | 25건 | 300건 | 셀 제조사 납품 수주 데이터 |
| **FIN-01** | 표준/실제 원가 | cost_id, period_key, item_code, unit_cost, variance | 12건 | 72건 | 원재료비+전력/스팀비 배치 원가 |
| **FIN-02** | 매입/매출 채권 | claim_id, party_code, amount, due_date, status | 40건 | 400건 | AP/AR 현금 흐름 대사 |
| **FIN-03** | 예산·경영손익 | period_key, revenue, cogs, operating_profit, EBITDA | 6건 | 36건 | 월별 손익계산서(P&L) 무결성 |
| **EXT-01** | 환율·금리 | date_key, usd_krw, eur_krw, fed_rate | 180건 | 1,095건 | 일별 환율 시계열 |
| **EXT-02** | 원자재 기준가 | date_key, lithium_fastmarkets, nickel_lme, cobalt_lme | 180건 | 1,095건 | 국제 리튬/니켈 시세 지수 |
| **EXT-03** | 에너지·ESG | date_key, industrial_power_krw, lng_import_price | 180건 | 1,095건 | 한전 전력단가 & LNG 스팀 단가 |
| **KNW-01** | 품질규격·지식 | doc_id, doc_title, category, content_hash | 5건 | 15건 | NCM 양극재 제조 표준 지침서 |
| **SIM-01** | 결정론적 산식 | formula_id, target_metric, input_vars, math_expr | 8건 | 20건 | 원료가/전력비 → 손익 인과 산식 |
| **SIM-02** | 시나리오 세트 | scenario_id, scenario_name, shock_params | 3건 | 10건 | [S-BC-01] 리튬가 40% 폭등 세트 |
| **DEC-01** | Decision Ledger | decision_id, title, status, approved_by, ledger_hash | 2건 | 8건 | 리튬 장기계약 갱신 승인 안건 |

---

## 3. 대사(Reconciliation) 및 품질 검증 4대 기준

1. **원재료 수지 대사 (Material Balance Reconciliation):**
   $$\text{수산화리튬 기초재고} + \text{당월 입고량} - \text{양극재 생산 투입량} = \text{수산화리튬 기말재고}$$
   *(오차 범위 0.05% 이내 합격)*

2. **원가-손익 연결 대사 (Cost-to-Profit Reconciliation):**
   $$\text{매출원가(COGS)} = \sum (\text{양극재 출하량} \times \text{FIN-01 배치 단위원가})$$

3. **결정론적 시뮬레이션 재현성 (Deterministic Simulation Replay):**
   동일한 `EXT-01~03` 입력 변수 및 `SIM-01` 산식 적용 시, 100% 동일한 손익 예측 결과 재현.

---

## 4. 실행 및 자동 시드 스크립트 구축

- **실행 스크립트:** `scripts/seed_battery_chemical_starter_kit.py`
- **생성 결과 저장 경로:**
  - `starter_kits/KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT/1.0.0/quick/`
  - `starter_kits/KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT/1.0.0/full/`

---
**[확인]** 본 수행계획은 35개 패키지의 완결성을 보장하며, 자동 생성을 위한 모든 명세를 확정하였습니다.
