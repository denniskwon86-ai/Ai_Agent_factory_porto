# 선제안형 데이터 온보딩·외부 인텔리전스 상세 구현 설계서

> **실행 우선순위 승격(2026-08-03):** 이 문서의 P4 읽기 전용 운영 데이터 파일럿은 더 이상 기능 구현 이후의 선택 과제가 아니라, 원료 구매 수직 폐루프에서 `Minimum Viable Actual` 기준선을 만드는 G2 선행 작업이다. 최신 데이터 영역(RAW/QUARANTINE/STANDARDIZED/CERTIFIED/SCENARIO/SYNTHETIC), 원천 대사와 Sprint 순서는 [`roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md`](roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md) §6 G2-D를 우선한다. 운영계 쓰기는 여전히 별도 승인 전 금지한다.

> 문서 상태: 구현 준비 완료(코드 변경 전 설계 확정본)  
> 기준일: 2026-07-29  
> 상위 SSOT: `docs/LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md` §4, §6, §12  
> 적용 순서: 현재 진행 중인 MDM·기업문맥·권한 구현 완료 및 통합 후  
> 범위: 사업 사용자에게 필요한 데이터를 **먼저 제안**하고, 확보·검증·등록·시뮬레이션 적용까지 실제 작업으로 연결하는 기능

---

## 1. 문제 정의와 제품 원칙

### 1.1 해결하려는 문제

현업 사용자는 보통 “내년 경영계획을 만들고 싶다”, “공장 생산성을 시뮬레이션하고 싶다”라는 목적은 알고 있지만, 필요한 데이터의 종류·원천·품질·우선순위·확보 방법을 알지 못한다. 사용자에게 처음부터 데이터 설계를 맡기면 다음 문제가 생긴다.

- 업종·업무에 따라 반드시 필요한 기준정보와 실적 정보가 빠진다.
- 사용자가 가진 엑셀만 등록되어, 실제·계획·가정·외부 전망이 섞인다.
- 외부 정보가 웹 검색 결과나 최신 뉴스에 좌우되어 재현할 수 없다.
- “데이터가 부족합니다”라는 안내 뒤에 실제 다음 행동이 없어 프로젝트가 멈춘다.

따라서 시스템은 사용자를 인터뷰해 빈 화면을 채우게 하는 도구가 아니라, **선행 지식을 가진 데이터 준비 컨설턴트**로 동작해야 한다.

### 1.2 제품 원칙

1. **산업·업무별 표준 패키지를 먼저 제시한다.** 사용자는 표준을 새로 발명하지 않고 보유·연결·부족 상태만 간단히 답한다.
2. **안내에서 끝내지 않는다.** 부족 항목마다 데이터 오너, 원천, 확보 방법, 필요한 권한, 완료 기준을 가진 실행 작업을 만든다.
3. **외부 데이터는 승인된 원천만 수집한다.** 범용 웹 크롤러로 기준 수치를 만들지 않는다.
4. **빠름보다 검증 가능성을 우선한다.** 1~2일 늦더라도 출처·발표일·수정 이력·라이선스가 명확한 값을 기준 시나리오에 사용한다.
5. **LLM은 설명·후보 추천에만 사용한다.** 준비도 계산, 권한 판정, 데이터 품질 판정, 수치 계산, 시뮬레이션 결과는 규칙·검증·결정론적 엔진이 담당한다.
6. **실제·계획·예측·가상 시나리오를 절대 혼합하지 않는다.** 값뿐 아니라 화면·API·저장소·권한·스냅샷에서도 구분한다.
7. **데이터 수치의 현실 정확도는 운영 전 보정 대상이다.** 현 단계의 완료 기준은 기능적 완결성, 참조 정합성, 격리, 추적성이다. 임의 수치를 실제 수치처럼 표현하지 않는다.

---

## 2. To-Be 사용자 경험

### 2.1 최초 흐름

```text
사용자: “배터리소재 사업부의 내년 경영계획과 수익성 시뮬레이션을 만들고 싶다.”
  → 기업·법인·사업부·공장 문맥 선택
  → 시스템이 “배터리소재 경영계획 패키지”를 선제안
  → 사용자는 각 데이터 요구사항을 보유/연결 가능/파일 보유/부족/해당 없음으로 표시
  → 시스템이 준비도, 현재 가능한 기능, 차단 기능, 다음 행동을 계산
  → 사용자가 작업 묶음을 승인
  → 커넥터 활성화·파일 업로드·데이터 오너 승인·검증 작업이 생성
  → 검증된 데이터 스냅샷으로 기준 시나리오와 위험 시나리오 실행
```

### 2.2 데이터 준비 보드

| 사용자에게 보이는 열 | 의미 |
|---|---|
| 필요한 이유 | 어떤 의사결정·KPI·앱·시뮬레이션에 쓰이는가 |
| 데이터 항목 | 예: 월별 제품별 매출실적, 제품 BOM, 전력 사용량 |
| 표준 원천 | ERP, MES, LIMS, 설비 historian, 공식 외부 API 등 |
| 현재 상태 | `보유`, `연결 가능`, `파일 보유`, `검증 필요`, `부족`, `해당 없음` |
| 지금 가능한 범위 | 현재 데이터만으로 가능한 보고·시뮬레이션 |
| 다음 행동 | 연결, 업로드, 매핑, 오너 승인, 외부지표 활성화 중 하나 |
| 책임·기한 | 담당 조직, 데이터 오너, 목표 시점 |

사용자에게는 “ERP 테이블 이름”이 아니라 **업무 언어**로 보인다. 기술 매핑과 API 인증은 데이터 담당자 화면에서 분리한다.

### 2.3 결과 상태

| 상태 | 의미 | 시스템 동작 |
|---|---|---|
| `READY` | 필수 데이터와 승인된 가정이 충족 | 기준 시뮬레이션과 공식 보고 허용 |
| `READY_WITH_ASSUMPTIONS` | 일부 값은 명시적 가정 또는 합성 시드 | 탐색·파일럿 허용, 결과에 경고·가정 표시 |
| `BLOCKED_BY_DATA` | 핵심 결손으로 특정 계산 불가 | 대체 수치를 꾸며내지 않고 데이터 작업 생성 |
| `BLOCKED_BY_APPROVAL` | 데이터는 있으나 사용·공유 권한 미승인 | 승인 요청 및 영향 범위 표시 |
| `STALE` | 최신성 조건 초과 | 마지막 승인 스냅샷을 유지하고 갱신 요청 표시 |

---

## 3. 선제안 데이터 패키지 모델

### 3.1 공통 데이터 계약

모든 데이터셋은 아래 공통 속성을 가져야 한다. 이 속성이 없는 파일·API 응답은 카탈로그 후보로만 저장하고 기준 시뮬레이션에는 넣지 않는다.

```text
dataset_id, dataset_name, data_contract_version,
tenant_id, scope_node_id, scope_type,
data_kind(ACTUAL/PLAN/FORECAST/SCENARIO/REFERENCE/EVENT),
grain, business_keys, period_start, period_end, as_of_date,
source_system, data_origin(INTERNAL/OFFICIAL_EXTERNAL/APPROVED_PARTNER/SYNTHETIC),
unit, currency, timezone, owner_org_id, data_owner_id,
classification, quality_status, approval_status,
effective_from, effective_to, ingested_at, version, lineage_ref
```

### 3.2 표준 패키지

| 코드 | 패키지 | 최소 항목 | 최초 활용 목적 |
|---|---|---|---|
| `ORG-01` | 조직·권한 | 그룹/법인/사업부/공장, 데이터 오너, 역할 | 데이터 범위·접근 통제 |
| `MDM-01` | 기준정보 | 조직, 품목, 제품, BOM, 설비, 고객, 계정, 단위 | 모든 데이터의 결합 키 |
| `PROC-01` | 공정·능력 | Routing, 설비능력, 공정시간, 제약, 작업장 | 생산·납기·능력 시뮬레이션 |
| `ACT-01` | 운영 실적 | 수주, 매출, 생산, 재고, 품질, 원가, 설비 가동 | 현재 상태·보정 |
| `PLAN-01` | 경영계획 | 판매, 생산, 구매, 인력, 투자, 예산 | 계획 대비·중장기 전망 |
| `EXT-01` | 외부환경 | 환율, 금리, 물가, 원자재, 에너지, 산업경기, 기상 | 외부 동인 시나리오 |
| `SCN-01` | 시나리오 | 조절 변수, 범위, 근거, 승인자, 기간 | What-if 실행 |
| `DOC-01` | 문서·지식 | 표준서, 계약, 보고서, 규정, 연구자료 | 근거 탐색·설명 |
| `GOV-01` | 거버넌스 | 출처, 라이선스, 품질, 계보, 민감도, 승인 | 재현·감사·공유 |

### 3.3 업종 패키지의 구성

`playbooks/*.json`의 업무 질문·데이터 요구사항을 확장하되, 플레이북을 산업 전체 프로필과 동일시하지 않는다.

```text
Industry Baseline Package
  = 업무 플레이북
  + 표준 데이터 요구사항
  + KPI/Driver 후보 그래프
  + 허용 외부 원천 목록
  + 데이터 품질 규칙
  + 공정/산업 용어 사전
  + 시뮬레이션 템플릿
```

각 패키지는 `industry_codes`, `business_types`, `applicable_scope_types`, `version`, `source`, `hash`, `effective_from/to`를 가진다. 기업문맥의 업종과 호환되지 않으면 적용을 차단하거나 명시적 예외 승인을 요구한다.

---

## 4. 외부 인텔리전스: 최초 승인 원천

### 4.1 원천 선정 기준

1. 국가기관·국제기구·시장 운영기관 등 원 발행자여야 한다.
2. API 또는 공식 파일 다운로드가 가능해야 한다.
3. 발표일·대상 기간·단위·수정 여부를 확인할 수 있어야 한다.
4. 내부 분석·저장·재사용 범위의 라이선스를 확인할 수 있어야 한다.
5. 기준 시나리오용 Gold와 전망·위험 시나리오용 Silver를 구분할 수 있어야 한다.

### 4.2 MVP 원천 등록부 초안

| source_id | 제공자·원천 | 초기 지표 | 기본 등급 | 수집 방식 | 용도·주의사항 |
|---|---|---|---|---|---|
| `SRC_BOK_ECOS` | 한국은행 ECOS | 환율, 금리, 물가 등 | Gold | 공식 Open API | 거시·환산·금융비용 동인. 각 통계표의 기준일과 단위를 지표별로 고정한다. |
| `SRC_KOSIS` | 국가통계포털 KOSIS | 제조업 생산·출하·재고·가동률, 무역·산업 통계 | Gold | 공식 Open API | 업종 경기·수요 기준선. 산업분류·공표 지연을 지표 메타데이터로 관리한다. |
| `SRC_WB_PINK_SHEET` | World Bank Commodity Markets | 금속·에너지·비료 등 월별 국제 원자재 가격 | Gold 또는 Silver | 공식 XLS 다운로드 | 실구매 단가를 대체하지 않는다. 국제 기준 가격·시나리오 동인으로 쓴다. |
| `SRC_KPX` | 전력거래소/산업 데이터 포털 | SMP, 전력수요 예측 | Silver | 승인된 공공 API | 실제 공장 전력비가 아니다. 전력시장 변동성의 보조 동인이다. |
| `SRC_KMA` | 기상청 API | 지역별 관측·단기·중기 예보 | Gold(관측), Silver(예보) | 공식 API | 물류·공장 가동·수요 차질 시나리오. 사업장 위치와 명시적으로 매핑한다. |

후순위 원천은 무역·통관, 광물·금속 전문 지표, 유료 시장 데이터, 규제·공시 데이터다. 이들은 실제 사업부의 품목·해외 거래·의사결정 빈도가 확인된 뒤 별도 라이선스 검토와 함께 추가한다.

### 4.3 명확한 사용 제한

- 전력거래소 SMP는 전기요금 청구서·계약요금의 대체값이 아니다.
- World Bank·공식 국제 가격은 공급사 계약단가·헤지·프리미엄·물류비를 대체하지 않는다.
- 외부 전망치·기사·공시 알림은 승인 전 기준 계획을 바꾸지 않는다.
- 유료 데이터는 계약 범위 밖의 재배포·학습·프롬프트 투입을 하지 않는다.
- HTML 수집은 공식 API·공식 파일이 없고 약관상 허용되는 경우에만 한다.

---

## 5. 구현 아키텍처

### 5.1 저장소 경계

```text
data/
  master_data.db                  # MDM 기준 정의와 조직 범위 바인딩
  decision_ledger.db              # 승인·결정·스냅샷 참조 이력
  external_intelligence.db        # 외부 원천·지표·관측·수집 이력
  external_raw/                   # 원문 응답/CSV/XLS와 checksum, 수집 메타데이터
  catalog/                        # 데이터 자산·계약·품질·계보 메타데이터(구현 단계에서 DB화)
```

`pipeline_state.db`에는 외부 관측값 원문을 저장하지 않는다. Chroma/RAG에는 승인된 설명·근거 문서의 검색용 요약만 넣으며, 수치 계산의 원천으로 사용하지 않는다.

### 5.2 핵심 테이블

기존 상위 명세의 테이블에 아래 운영 필드를 보강한다.

```text
external_sources(
  source_id PK, publisher, source_type, base_url, license_url,
  allowed_usage, collection_method, refresh_frequency, acceptable_latency,
  rate_limit, trust_grade, enabled, owner_org_id, secret_ref,
  approved_at, approved_by, created_at, updated_at
)

external_indicators(
  indicator_id PK, code UNIQUE, name, category, canonical_term_id,
  geography_code, commodity_code, unit, frequency,
  data_kind, canonical_source_id, backup_source_id,
  verification_policy, allowed_simulation_use, status
)

external_observations(
  observation_id PK, indicator_id FK, observed_at, published_at,
  ingested_at, vintage_date, value, unit, source_id FK,
  source_record_ref, raw_object_ref, checksum,
  quality_status, supersedes_observation_id, validation_report_json
)

external_snapshots(
  snapshot_id PK, scope_node_id, purpose, created_at,
  as_of_date, observation_cutoff_at, snapshot_hash,
  status, created_by, approved_by, approval_at
)

external_snapshot_items(
  snapshot_id FK, observation_id FK, indicator_id FK,
  PRIMARY KEY(snapshot_id, observation_id)
)

driver_mappings(
  mapping_id PK, external_indicator_id FK, internal_metric_id,
  scope_node_id, mapping_type, formula_definition,
  lag_period, unit_conversion_rule, evidence_ref,
  effective_from, effective_to, version, approval_status,
  owner_org_id, approved_by
)
```

### 5.3 코드 경계

```text
core/external_intelligence/
  repository.py          # DB 접근, 테넌트·조직 범위 필수화
  source_registry.py     # 원천 등록·라이선스·활성화 상태
  collectors/            # ecos.py, kosis.py, world_bank.py, kma.py, kpx.py
  raw_store.py           # 원문 보관, checksum, 재수집 방지
  normalizer.py          # 날짜·단위·통화·주기 정규화
  validator.py           # 중복·범위·최신성·단위·수정값 검증
  snapshot_service.py    # 재현 가능한 관측값 묶음 고정
  driver_mapping.py      # 외부지표→내부 KPI 연결과 승인
  scheduler.py           # 별도 워커 등록. SSE/슈퍼바이저에 넣지 않음

api/routes/external_intelligence_control.py
frontend/src/components/ExternalIntelligencePanel.tsx
frontend/src/components/DataReadinessBoard.tsx
frontend/src/components/ScenarioWorkbenchPanel.tsx
```

### 5.4 API 초안

| Method | API | 역할 |
|---|---|---|
| `GET` | `/api/v1/external-intelligence/sources` | 권한 범위 내 승인 원천 조회 |
| `POST` | `/api/v1/external-intelligence/sources/{id}/activate` | 원천 사용 승인·자격 증명 참조 연결 |
| `POST` | `/api/v1/external-intelligence/collect` | 지표·기간·원천의 수집 작업 요청 |
| `GET` | `/api/v1/external-intelligence/indicators` | 지표 카탈로그와 품질·최신성 조회 |
| `GET` | `/api/v1/external-intelligence/observations` | 지표·기간·vintage 기반 조회 |
| `POST` | `/api/v1/external-intelligence/snapshots` | 시뮬레이션용 승인 스냅샷 생성 |
| `POST` | `/api/v1/external-intelligence/driver-mappings` | 외부지표와 내부 KPI의 승인된 연결 생성 |
| `GET` | `/api/v1/data-readiness/{blueprint_id}` | 선제안 요구사항과 현재 준비도 조회 |
| `POST` | `/api/v1/data-readiness/{blueprint_id}/actions` | 연결·업로드·검증·승인 작업 생성 |

모든 API는 `tenant_id`, `scope_node_id`, 요청 목적, 권한 근거를 서버에서 확인한다. 클라이언트가 전달한 조직 범위를 신뢰하지 않는다.

---

## 6. 수집·검증·공개 파이프라인

```text
스케줄러 또는 사용자 승인 수집 요청
  → 원천별 Collector
  → 원문 파일/API 응답 보관(raw_object_ref + checksum)
  → Normalizer(날짜·주기·단위·통화 표준화)
  → Validator
      - 스키마·필수값
      - 중복·역전 기간
      - 단위·통화 불일치
      - 급격한 값 변화·결측·최신성
      - 원천 메타데이터와 값의 기간 일치
  → RAW / VALIDATED / REJECTED / SUPERSEDED 판정
  → 카탈로그와 품질 현황 갱신
  → 승인된 스냅샷 생성 가능 상태 공개
  → 영향 Driver Mapping 재계산 필요 알림
  → Decision Ledger 기록
```

### 6.1 필수 검증 규칙

| 검증 | 예시 | 실패 시 처리 |
|---|---|---|
| 기준일 | 2026년 계획에 2027년 발표값 혼입 | `REJECTED` 또는 별도 vintage로 격리 |
| 단위 | USD/MT와 KRW/kg 혼용 | 명시적 환산 규칙 없으면 차단 |
| 최신성 | 월간 지표가 허용 지연을 넘김 | `STALE`, 마지막 승인 스냅샷 유지 |
| 수정값 | 과거 관측값이 수정 공표됨 | 신규 vintage 저장, 기존 스냅샷 불변 |
| 조직 범위 | A공장 가정이 B공장에 자동 적용 | 매핑·승인 없으면 차단 |
| 실제성 | 외부 전망을 Actual로 저장 | 데이터 종류 검증 실패 |

### 6.2 원본·스냅샷 보존

어떤 결과든 아래 질문에 답할 수 있어야 한다.

> “2026년 12월 15일 실행한 A공장 손익 시뮬레이션은, 어떤 환율·원자재 가격·전력비 가정·사내 실적을 사용했는가?”

답은 `simulation_run → external_snapshot → observation → raw_object → source` 경로로 재현되어야 한다. 원천이 수정돼도 과거 실행의 스냅샷은 바꾸지 않는다.

---

## 7. 내부 데이터와 외부 지표의 결합 규칙

외부지표가 손익을 직접 바꾸게 해서는 안 된다. 반드시 업무·계산 경로를 거친다.

```text
환율
  → 계약 통화별 수입 원재료 단가
  → 품목별 표준원가/실제원가
  → 제품별 매출총이익
  → 운전자본·현금흐름
```

```text
국제 구리 기준 가격
  → 공급사 계약단가 + 프리미엄 + 물류비 + 환율
  → 정광/원재료 조달비
  → 제조원가
  → 손익 및 재고평가 시나리오
```

`driver_mappings`의 공식화된 계산식은 업무 오너와 데이터 오너의 공동 승인을 받아야 한다. Graph RAG는 관련 계약·실적·문서를 찾는 데 도움을 줄 수 있으나, 공식 산식과 승인 상태를 대체하지 않는다.

---

## 8. 단계별 실행계획

### P0 — 구현 착수 전 정렬 (2~3일)

**목표:** 현재 MDM·ECM·권한 구현과 충돌 없는 계약을 확정한다.

- R-001의 조직 범위 바인딩 원칙을 확정한다. 외부 관측값도 전역 값과 조직별 적용 범위를 분리한다.
- `ORG-01`과 M1~M4 시드의 범위·버전·소유자를 점검한다.
- 최초 지표 6종과 지표별 단위·주기·Gold/Silver·기준 원천·허용 지연을 확정한다.
- 외부 데이터 라이선스 검토 체크리스트와 비밀 관리 방식을 확정한다.

**완료 기준:** 데이터 계약, DB 마이그레이션, API 스키마, 권한 규칙, UI 상태를 문서와 테스트 표에 확정한다.

### P1 — 외부 인텔리전스 기반 (1~2주)

**목표:** 외부 데이터를 안전하게 저장·검증·재현한다.

- `external_intelligence.db`, 원문 보관, source/indicator/observation/snapshot/driver mapping 구현
- 원천 등록부 관리 API와 관리자 UI
- 수집 작업·실패·재시도·최신성 상태
- ECOS, KOSIS, World Bank 커넥터 3종
- fixture 기반 단위·계약·vintage·중복 테스트

**완료 기준:** 지표별 관측값을 수집하고, 수정본과 원본을 구분하며, 승인 스냅샷을 만든 뒤 동일 결과를 재현할 수 있다.

### P2 — 선제안형 데이터 준비 보드 (1~2주)

**목표:** 사용자가 해야 할 일을 실제 작업으로 바꾼다.

- 산업·사업부 문맥별 표준 데이터 패키지 로드
- 보유/연결 가능/파일 보유/부족/해당 없음 빠른 응답 UI
- 결정론적 준비도 계산 및 현재 가능 범위 산출
- 결손 데이터마다 커넥터·업로드·매핑·승인 태스크 생성
- 프로젝트 RFP/WBS에 데이터 확보 작업 반영

**완료 기준:** 새 사용자가 데이터 모델을 몰라도 10분 이내에 데이터 준비 보드와 우선 작업 목록을 만들 수 있다.

### P3 — 시뮬레이션 연결 (1~2주)

**목표:** 외부 데이터가 경영 시뮬레이션에 통제된 방식으로 반영된다.

- 실제/계획/예측/시나리오 스냅샷 선택 UI
- `driver_mappings` 승인·유효기간·근거 관리
- 기준·상승·하락·공급차질 시나리오 템플릿
- 결과에 데이터 스냅샷·가정·산식·경고 표시

**완료 기준:** 배터리소재 또는 동제련 기준 시나리오 1건에서 외부지표 변동이 원가·손익 경로를 거쳐 설명 가능하게 반영된다.

### P4 — 실제 운영 데이터 파일럿 (별도 승인 후)

**목표:** 기업의 ERP/MES/LIMS/파일 데이터를 읽기 전용으로 연결한다.

- 데이터 계약과 필드 매핑
- 고객사가 사용하는 외부 협업 레거시를 Connector/Crosswalk에 등록하고, 공식 API·MCP·Read Replica·Export 중 승인된 접속 방식을 사용. LS 환경의 LPL은 첫 Reference Profile로만 관리
- 계약·선적·통관·운송 사건은 원천키·사건 버전·발생/수정/조회 시각을 보존하고 cursor 기반 증분 수집
- Shadow Mode, 품질·권한·감사 로그
- 실제 데이터와 시드·가상 시나리오의 격리
- 결과 보정과 Driver Mapping 재승인

**완료 기준:** 실제 운영 시스템에 쓰지 않고도, 특정 사업부의 실적 기반 시뮬레이션을 재현·설명할 수 있다.

---

## 9. 최초 파일럿의 구체 범위

### 9.1 권장 파일럿: 배터리소재 사업부 경영계획

| 영역 | 내부 최소 데이터 | 외부 기본 동인 | 결과 |
|---|---|---|---|
| 판매 | 월별 제품·고객·지역 매출/물량, 판매계획 | 환율, 산업 수요 지표 | 매출·물량 계획 |
| 구매 | 원재료 계약단가·조달물량·재고 | 원자재 기준 가격, 환율 | 조달비·재고 영향 |
| 생산 | BOM, 수율, 설비능력, 가동률 | 전력시장·기상은 보조 변수 | 생산 가능량·원가 |
| 원가 | 재료비·노무비·경비·전력 사용량 | 물가·에너지 지표 | 제품별 표준/시나리오 원가 |
| 재무 | 계정체계, 매출채권·재고·투자 계획 | 금리·환율 | 손익·운전자본·현금흐름 |

### 9.2 결과 화면의 필수 고지

- 기준일과 내부·외부 스냅샷 식별자
- 실제값·계획값·전망값·가정값의 범례
- 데이터 결손과 그로 인한 결과 한계
- 적용 Driver Mapping과 승인 상태
- “공식 경영 수치”인지 “파일럿 탐색 결과”인지 상태

---

## 10. 보안·라이선스·운영 원칙

1. API 키, 토큰, 계약서, 유료 데이터 원문은 코드·프롬프트·로그에 저장하지 않고 비밀 참조(`secret_ref`)만 보관한다.
2. 외부 데이터의 사용·재배포·AI 학습 가능 범위는 `external_sources.allowed_usage`에 명시한다.
3. 조직·공장별 적용은 `scope_node_id`와 승인된 매핑을 통해서만 한다. 전역 데이터를 무조건 문맥에 주입하지 않는다.
4. 외부 수집 워커는 API 서버·SSE·슈퍼바이저와 분리한다. 수집 지연이 프로젝트 실행을 멈추게 해서는 안 된다.
5. 유료 데이터 도입은 “무료·공식 대체 수단 부재”, “의사결정 개선 가치”, “라이선스 적합성” 세 조건을 모두 만족할 때만 제안한다.

---

## 11. 테스트·수용 기준

### 11.1 계약·정합성

- ECOS/KOSIS/World Bank fixture를 수집·정규화·저장할 수 있다.
- 동일 관측값의 중복 수집은 멱등적이다.
- 수정 공표된 값은 기존 observation을 덮어쓰지 않고 새 vintage를 만든다.
- 단위·통화·주기가 맞지 않으면 명시적 변환 규칙 없이는 시뮬레이션 입력이 될 수 없다.

### 11.2 권한·격리

- 권한 밖 조직의 데이터·스냅샷·원문은 API와 LLM 문맥에서 모두 조회되지 않는다.
- 실제와 가상 회사, 경쟁사, 시나리오 데이터가 상호 혼입되지 않는다.
- 사용자 제공 `scope_node_id` 변조는 서버 권한 검사에서 차단된다.

### 11.3 사용자 흐름

- 경영계획 사용자가 업종·조직 문맥을 선택하면 선제안 패키지가 표시된다.
- 데이터 상태를 고르면 준비도·가능 범위·차단 기능·다음 작업이 결정론적으로 갱신된다.
- 부족 데이터 작업이 WBS/프로젝트에 생성되고, 업무 목표·영향·오너·완료 기준을 가진다.
- 시뮬레이션 결과가 참조한 데이터·가정·산식·버전을 표시한다.

### 11.4 실패 처리

- 원천 API 장애는 기존 승인 스냅샷을 훼손하지 않는다.
- 최신성 초과는 `STALE`로 보이며 조용히 최신값으로 가장하지 않는다.
- 수집·검증 실패는 재시도 정책과 오류 원인을 남기며, 프로젝트 실행 루프나 슈퍼바이저를 멈추지 않는다.

---

## 12. Post-Launch 자율 운영 아키텍처 (Proactive Intelligence Loop)

시스템 오픈 후(Post-Launch), 사용자의 수동 지시 없이도 마켓 인텔리전스가 자율적으로 최신화되고 확장되는 **'능동형 에이전트 자가 발전'** 모델을 가동한다.

### 12.1 핵심 설계 사상: Proactive Agent
사용자가 일일이 "특정 광산을 조사해라"라고 프롬프팅하지 않아도, 전담 에이전트(Market Intelligence Agent)가 백그라운드 크론(Cron) 스케줄러와 결합하여 스스로 인지하고 제안하는 루프를 운영한다.

### 12.2 자율 운영 파이프라인 (3-Step Loop)

1. **내부 취약점 인지 (Trigger & Gap Analysis)**
   - **방식:** 에이전트가 주기적(Weekly 등)으로 시스템의 주요 KPI(동제련 이익률, 조달 단가 등)와 시뮬레이션 오차율을 모니터링한다.
   - **판단:** 실제 원가가 예측치를 크게 벗어나면 "시스템에 누락된 새로운 외부 변수(Blind Spot)가 발생했다"고 스스로 판단한다.

2. **능동적 외부 리서치 및 맵핑 (Self-Research & Modeling)**
   - **방식:** 에이전트가 자율적으로 웹 검색 도구(`search_web`)를 가동하여 해당 원자재의 글로벌 위기, 실적 등을 탐색한다.
   - **행동:** 유의미한 원인을 발견하면, 즉각 RAG 보고서를 작성하고 시뮬레이터가 읽을 수 있는 **이벤트 드라이버(JSON)**를 자율 생성하여 파급 효과(Impact)를 맵핑한다.

3. **의사결정권자 승인 (Human-in-the-Loop)**
   - **방식:** 에이전트는 시스템의 코어 로직을 임의로 바꾸지 않고, 사용자(Supervisor)에게 대시보드를 통해 **'새로운 인텔리전스 패치 알림'**을 전송한다.
   - **결과:** 사용자가 내용과 근거를 확인하고 **[Approve(승인)]** 버튼을 누르면, 시스템이 최신 시장 상황으로 영구 업데이트된다.

---

## 12. 이번 구현 이후의 의사결정 지점

1. **최초 산업 파일럿 선택:** 배터리소재와 동제련 중 어느 패키지를 우선 완주할지 결정한다.
2. **지표별 기준 원천 승인:** ECOS·KOSIS·World Bank 3종은 기본 승인 후보로 두고, 실제 API 계정·이용약관·호출량을 확인한다.
3. **실제 데이터 연결 승인:** P4는 데이터 오너·보안·ITO 운영 주체의 명시적 승인이 있을 때만 시작한다.
4. **유료 데이터 판단:** 공식 무료 원천으로 부족한 품목·빈도·정확도가 확인된 뒤 ROI와 라이선스를 근거로 별도 제안한다.

---

## 부록 A. 공식 원천 참고 링크

- 한국은행 경제통계시스템 ECOS: https://ecos.bok.or.kr/
- 국가통계포털 KOSIS: https://kosis.kr/serviceInfo/kosisIntroduce.do
- KOSIS 공유서비스(Open API): https://kosis.kr/openapi/introduce/introduce_01List.do
- World Bank Commodity Markets / Pink Sheet: https://www.worldbank.org/en/research/commodity-markets
- 전력거래소 계통한계가격 데이터 안내: https://www.idx.or.kr/portal/data/search/872b5ee1-c6cb-5e89-baad-78c510aedf6e
- 기상청 단기예보 API: https://www.data.go.kr/data/15139470/openapi.do

각 원천의 실제 적용 전에는 API 약관, 요청 한도, 상업적 이용·저장·재배포 허용 범위, 최신 API 엔드포인트를 원천별로 재확인한다.
