# Enterprise Context Master 상세 설계

> 상태: **To-Be 기준 설계** · 2026-07-28  
> 적용 범위: 조직·권한·MDM·데이터 카탈로그·업무 템플릿·AI 에이전트·SW 생성·시뮬레이션·MCP 연계  
> 상위 기준: [`AI_FACTORY_STUDIO_PRODUCT_BIBLE.md`](AI_FACTORY_STUDIO_PRODUCT_BIBLE.md), [`LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md`](LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md)

## 1. 목적

AI Factory Studio는 하나의 공장만을 전제한 도구가 아니다. 지주회사, 복수 법인, 사업부, 사업장, 공장, 공통 지원조직으로 이루어진 실제 기업 집단이 각자의 업무를 운영하면서도 전사 관점에서 연결·집계·시뮬레이션할 수 있는 **기업 운영 설계 플랫폼**이 되어야 한다.

이를 위해 모든 사용자는 프로젝트를 시작하기 전에 자신이 다루는 기업 문맥을 선택한다. 이 문맥은 단순한 화면 필터가 아니라 다음을 함께 결정하는 런타임 기준이다.

- 접근 가능한 데이터·프로젝트·시뮬레이터·업무 앱의 범위
- 해당 조직의 업종, 공정, 제품, 회계/경영관리 기준, 용어와 동의어
- 제안할 업무 템플릿, 데이터셋, 에이전트 조합, 검증 규칙
- 외부 시스템/MCP 연결의 허용 범위와 데이터 사용 목적
- 집계 가능한 상위 조직과 공유 서비스 조직의 관계

이 기준 체계를 **Enterprise Context Master(ECM)** 라고 한다.

ECM은 실제 조직만 관리하지 않는다. 실제 회사의 기준정보를 안전하게 복제해 신사업, 증설, 사업 철수, 사업부 재편을 실험하는 **가상 기업/가상 조직**과, 공개·승인된 정보만으로 관리하는 **경쟁사 참조 모델**도 같은 언어로 다룬다.

## 2. 설계 원칙과 비목표

### 2.1 비협상 원칙

1. **조직은 메뉴가 아니라 의미적 실행 문맥이다.** 선택된 조직은 권한뿐 아니라 데이터 계약, AI 문맥, 템플릿 추천, 계산 단위까지 결정한다.
2. **법적 소유, 운영 보고, 공유 서비스, 연결 집계는 서로 다른 관계다.** 단일 트리로 억지로 표현하지 않는다.
3. **실제·계획·예측·가상 시나리오·경쟁사 추정치는 절대로 혼합하지 않는다.** 모든 값은 상태와 근거를 가진다.
4. **가상 조직은 실제 조직의 안전한 복제본이지 운영계의 우회 통로가 아니다.** 운영 DB 자격증명, 실거래, 외부 쓰기 권한은 복제하지 않는다.
5. **경쟁사 모델은 정보 수집 대상이지 사실을 꾸며내는 대상이 아니다.** 공개 또는 계약상 허용된 데이터만 쓰며, 추정은 추정으로 표시한다.
6. **AI는 조직·업종을 임의로 단정하지 않는다.** 프로필과 승인된 템플릿을 근거로 추천하고, 사용자가 선택·수정할 수 있다.

### 2.2 비목표

- 첫 단계에서 ERP/MES의 모든 원장과 거래를 재구축하지 않는다.
- ECM이 HR 조직도나 법인 등기 정보의 유일한 원본 시스템이 되지는 않는다. 원본은 연결하고, ECM은 운영·분석·생성에 필요한 승인된 문맥 사본과 의미 관계를 관리한다.
- 경쟁사의 비공개 정보 수집, 추론을 통한 영업비밀 생성, 외부 시스템에 대한 무단 쓰기를 허용하지 않는다.

## 3. 핵심 용어와 계층

### 3.1 네 가지 관점

| 관점 | 질문 | 대표 관계 | 예시 |
|---|---|---|---|
| 보안 테넌트 | 누구의 독립 환경인가? | `TENANT_BOUNDARY` | 고객사 A의 AI Factory 환경 |
| 법적/소유 구조 | 어느 법인과 지주 관계인가? | `LEGAL_OWNERSHIP` | LS → LS MnM |
| 운영 구조 | 실제 누가 업무·공정을 수행하는가? | `OPERATING_PARENT` | 사업부 → 제1공장 → 생산라인 |
| 관리/집계 구조 | 어떤 기준으로 공유·연결·집계하는가? | `SHARED_SERVICE`, `CONSOLIDATION_SCOPE` | 전사 경영관리·재무회계, 연결 손익 |

한 노드에 부모 하나만 강제하면 전사 공통 재무조직, 매트릭스 조직, 공동 물류센터, 연결회계 범위를 표현할 수 없다. 따라서 ECM은 **노드(`organization_nodes`) + 다중 관계(`organization_edges`)** 모델을 사용한다. 화면에서는 이해하기 쉬운 기본 운영 트리를 제공하되, 데이터 모델은 그래프 관계를 보존한다.

### 3.2 표준 조직 노드 유형

```text
Tenant
└─ Enterprise Group(지주/기업집단)
   └─ Legal Entity(법인)
      ├─ Shared Service Organization(전사공통: 경영관리·재무회계·IT 등)
      ├─ Business Division / Business Unit(사업부)
      │  └─ Site / Plant(사업장·공장)
      │     └─ Facility / Line / Warehouse(설비·라인·창고)
      └─ Functional Department(구매·생산·품질·물류·판매 등)
```

`Business Unit`, `Functional Department`, `Plant`는 하나의 법인 아래에만 있어야 한다는 제약을 두지 않는다. 운영상 공동 조직이나 법인 간 공유 시설은 관계와 유효기간으로 모델링한다.

### 3.3 예시: 사용자가 제시한 구조

```text
LS (Enterprise Group)
├─ LS전선 (Legal Entity, 제조업)
├─ LS일렉트릭 (Legal Entity, 제조업)
└─ LS MnM (Legal Entity, 제련·소재 제조업)
   ├─ 전사공통 (Shared Service: 경영관리, 재무회계)
   ├─ 동제련 사업부 (Business Unit: 동·은·금·귀금속 제련)
   └─ 배터리소재 사업부 (Business Unit: 황산화물 생산)
      ├─ 제1공장 (Plant)
      └─ 제2공장 (Plant)
```

LS MnM 권한을 가진 사용자는 정책에 따라 하위 사업부·공장 전체를 볼 수 있다. 동제련 사업부 권한만 가진 사용자는 그 사업부와 하위 조직으로 제한된다. 전사공통 재무회계 조직은 여러 사업부를 집계할 수 있으나, 운영 원천 데이터의 세부 열람은 별도 데이터 도메인 권한을 요구한다.

## 4. 데이터 모델

### 4.1 공통 식별·유효기간·상태

ECM의 모든 기준 레코드는 다음 공통 필드를 갖는다.

| 필드 | 설명 |
|---|---|
| `tenant_id` | 보안·계약·데이터 격리 최상위 경계 |
| `entity_id` / `node_id` | 불변 UUID 식별자 |
| `code`, `name`, `aliases` | 사람·외부 시스템이 사용하는 표준 코드/명칭/동의어 |
| `status` | `DRAFT`, `ACTIVE`, `SUSPENDED`, `ARCHIVED` |
| `effective_from`, `effective_to` | 조직개편·사업장 변경을 위한 유효기간 |
| `version`, `approved_by`, `approved_at` | 승인 가능한 기준정보 버전 |
| `source_ref`, `evidence_ref` | 원본·증빙·데이터 카탈로그 연결 |

### 4.2 핵심 테이블

| 테이블 | 핵심 필드 | 역할 |
|---|---|---|
| `enterprise_entities` | `entity_type`, `entity_mode`, `legal_name`, `industry_code`, `base_entity_id` | 실제/가상/경쟁사 기업 또는 조직 실체 |
| `organization_nodes` | `entity_id`, `node_type`, `default_parent_id`, `path_hint` | 화면 기본 트리와 운영 단위 |
| `organization_edges` | `from_node_id`, `to_node_id`, `relation_type`, `weight`, `effective_*` | 소유·운영·공유서비스·집계 관계 |
| `enterprise_profiles` | `scope_node_id`, `profile_kind`, `payload_json`, `inheritance_mode` | 업종·공정·제품·회계·용어·지역 특성 |
| `profile_template_bindings` | `profile_id`, `binding_type`, `target_id`, `priority` | 프로세스, 데이터셋, 에이전트팩, 스킬, 시뮬레이션 모듈 연결 |
| `scope_assignments` | `principal_id`, `scope_node_id`, `inherit_descendants`, `domain`, `actions` | 역할과 조직 범위 결합 |
| `scenario_entities` | `scenario_id`, `entity_id`, `clone_source_id`, `snapshot_id`, `assumption_set_id` | 가상 조직/시나리오의 격리된 실행 단위 |
| `clone_jobs` | `source_id`, `target_id`, `clone_mode`, `copy_policy`, `approval_status` | 복사 작업, 승인·감사 기록 |

### 4.3 `entity_mode`와 데이터 취급

| 값 | 의미 | 허용 데이터 | 금지 사항 |
|---|---|---|---|
| `REAL` | 실제 법인·사업부·사업장 | 승인된 실제/계획/예측 데이터, 연결 시스템 참조 | 무단 외부 쓰기 |
| `VIRTUAL` | 신사업·증설·변경을 위한 가상 조직 | 기준정보 복제본, 스냅샷, 명시적 가정, 계산 결과 | 실거래 데이터 자동 반영·원본 연결 자격증명 복제 |
| `COMPETITOR_REFERENCE` | 경쟁사 또는 시장 비교 모델 | 공개/계약상 허용/승인된 외부 정보, 신뢰도·근거 | 비공개 추정의 사실화, 내부 실제값과 무표지 혼합 |

### 4.4 프로필 상속

프로필은 아래 우선순위로 병합한다. 충돌 시 가장 하위의 **승인된** 프로필이 이긴다.

```text
산업 공통 프로필
  → 기업집단 프로필
    → 법인 프로필
      → 사업부 프로필
        → 사업장/공장 프로필
          → 프로젝트 또는 시나리오의 명시적 오버레이
```

프로필에는 최소한 다음 묶음이 있다.

- `business_profile`: 업종·업태·제품군·고객/공급망·규제·회계 기준
- `process_profile`: 표준 업무 프로세스, 공정, KPI, 병목·제약 조건
- `data_profile`: 필수 마스터·거래·파일·외부지표, 품질 임계값, 동의어
- `solution_profile`: 권장 업무 앱, 화면/리포트, 데이터 계약, 재사용 자산
- `agent_profile`: 권장 에이전트 조합, 스킬, HOTL 지점, 금지·검토 규칙
- `simulation_profile`: 계산 모듈, 입출력 변수, 기준 시나리오, 검증 범위

## 5. 사용자 경험과 AI 동작

### 5.1 전역 Enterprise Context Switcher

현재 프로젝트 선택 이전의 런처와 프로젝트 통제실 상단에 공통 선택기를 둔다.

```text
[테넌트] LS 그룹  ▾  /  [법인] LS MnM ▾  /  [운영 범위] 배터리소재 사업부 · 제1공장 ▾
현재 모드: 실제 운영 문맥        [가상 시나리오 만들기] [조직/프로필 관리]
```

- 사용자는 권한 내에서만 노드를 탐색·선택한다.
- 선택 결과는 `EnterpriseContext` 토큰으로 모든 API·SSE·LLM 호출에 전달한다.
- 선택 변경 시 다른 범위의 열려 있는 프로젝트/시뮬레이션과 혼동되지 않도록 확인한다.
- 전역 슈퍼바이저는 선택 범위뿐 아니라 사용자의 허용 범위 내 상위·하위 상태를 이해해 답변한다.

### 5.2 상담사·SW 생성기·에이전트 추천

예: 사용자가 LS MnM/배터리소재 사업부를 선택하고 “내년도 사업계획을 만들고 싶다”고 말한다.

1. 상담사는 `business_profile`, `process_profile`, 데이터 카탈로그, 미충족 데이터 계약을 읽는다.
2. 공정·원가·생산능력·에너지·판매·외부지표 중 어떤 데이터가 필요한지 선택형 질문으로 제시한다.
3. 승인된 업무 템플릿과 권장 에이전트팩을 제안한다.
4. 사용자가 승인한 Solution Blueprint에만 프로젝트를 생성한다.
5. 이후 LLM 프롬프트에는 원문 전체가 아니라 필요한 범위의 승인된 프로필·카탈로그·계보·권한 요약만 주입한다.

제조업 법인을 선택했다는 이유만으로 같은 프로세스를 강제하지 않는다. 사업부·공장 프로필의 공정과 데이터 가용성을 우선해 권장안을 구성하고, 모든 추천은 근거와 버전을 표시한다.

## 6. 권한 모델

권한은 `주체 × 조직 범위 × 데이터 도메인 × 행동 × 상태`로 판정한다.

| 항목 | 예시 |
|---|---|
| 주체 | 사람 사용자, 서비스 계정, 에이전트 실행 ID |
| 조직 범위 | LS MnM 전체, 동제련 사업부, 제1공장 |
| 도메인 | 생산, 품질, 구매, 재무, 인사, 시뮬레이션, 기준정보 |
| 행동 | `READ`, `CREATE`, `EDIT`, `APPROVE`, `PUBLISH`, `RUN_SIMULATION`, `CONNECT`, `EXPORT` |
| 상태 | 실제, 계획, 예측, 가상 시나리오, 경쟁사 참조 |

### 6.1 상속 규칙

- 상위 범위의 `inherit_descendants=true` 권한은 하위 운영 노드에 상속된다.
- 공유 서비스·연결 집계 관계는 자동 전체열람 권한을 만들지 않는다. 필요한 도메인과 집계 수준을 별도로 부여한다.
- 가상 시나리오는 원본 범위의 `READ`만으로 생성할 수 없다. `RUN_SIMULATION` 또는 `CLONE_TO_VIRTUAL` 권한을 별도로 요구한다.
- 경쟁사 참조는 별도 `MARKET_INTELLIGENCE_READ`/`COMPETITOR_MODEL_EDIT` 도메인으로 격리한다.

### 6.2 감사 규칙

조직 문맥 변경, 프로필 변경, 복제, 권한부여, 외부 연결, 시나리오 실행·공유는 모두 `Decision Ledger`와 감사 로그에 남긴다. LLM·에이전트도 동일한 권한 평가를 통과한 도구만 호출할 수 있다.

## 7. 가상 기업·신사업·경쟁사 참조 모델

### 7.1 가상 조직 생성 흐름

```text
실제 조직 또는 승인된 템플릿 선택
  → 복제 범위·목적·유효기간 선택
  → 복사 정책 확인(기준정보/프로필/프로세스/에이전트 바인딩만)
  → 가정값·외부지표 시나리오 입력
  → 격리된 시나리오 스냅샷 생성
  → 결정론적 계산 엔진 실행
  → 결과·가정·근거·버전을 비교/승인
```

복사는 사용자가 요청한 “미리 등록된 회사정보 복사 후 새로 추가” 기능의 표준 방식이다. 다만 복제 대상은 다음처럼 구분한다.

| 복제 항목 | 기본값 | 이유 |
|---|---|---|
| 조직·회사 프로필·동의어 | 복사 | 새 조직 설계의 출발점 |
| 표준 프로세스·KPI·에이전트 바인딩 | 선택 복사 | 유사 사업을 빠르게 시작 |
| 데이터 카탈로그 정의·데이터 계약 | 참조 또는 선택 복사 | 필요한 데이터셋을 명확히 함 |
| 실제 거래·원장·개인정보 | 복사 금지 | 실제값 오염·보안 위험 방지 |
| 외부 시스템 자격증명·MCP 쓰기 권한 | 복사 금지 | 가상환경의 운영계 접근 차단 |
| 승인된 집계 스냅샷 | 선택 복사 | 기준선 비교와 시뮬레이션 |

### 7.2 가상 시나리오 예시

| 목적 | 원본 | 가상 변경 | 산출물 |
|---|---|---|---|
| 배터리소재 제3공장 증설 | 배터리소재 사업부/제2공장 | 생산능력, CAPEX, 인력, 전력단가, 램프업 일정 | 수익성·현금흐름·병목·민감도 |
| 신규 제련 사업 진입 | 동제련 사업부 템플릿 | 제품군, 원료가격, 회수율, 규제, 수요 | 사업성·리스크·필수 데이터/시스템 |
| 사업부 재편 | LS MnM 실제 조직 | 지원조직 공유, 물류 경로, 원가배부 기준 | 조직별/연결 손익과 운영 영향 |

### 7.3 경쟁사 모델

경쟁사 모델은 회사 구조와 업종을 표현할 수 있지만, 실제 회사와 같은 권한·운영 연결을 갖지 않는다.

- 공개 공시, 공식 발표, 계약상 이용 허용된 산업 데이터, 검증된 조사자료만 입력한다.
- 각 값에 `source`, `published_at`, `as_of_date`, `confidence`, `evidence_level`을 기록한다.
- LLM은 빈 칸을 사실처럼 채우지 않고 “확인 불가” 또는 가정 후보로 제시한다.
- 내부 실적과 경쟁사 추정치는 동일 차트에 표시할 수 있으나, 색·범례·데이터 상태를 분리한다.
- 경쟁사 모델은 시장 조건과 상대적 시나리오를 위한 참조이며, 회계·경영의 공식 수치가 아니다.

## 8. 시뮬레이션·데이터·외부 연계 경계

### 8.1 시뮬레이션 실행 문맥

모든 실행 요청은 다음 식별자를 가진다.

```json
{
  "tenant_id": "tenant_ls",
  "enterprise_scope_id": "plant_battery_01",
  "entity_mode": "VIRTUAL",
  "scenario_id": "scn_battery_plant_03",
  "baseline_snapshot_id": "snap_2026h1_approved",
  "assumption_set_id": "asm_energy_price_up_12pct",
  "calculation_model_version": "capacity_cost_v1.4"
}
```

산출 결과도 같은 키를 갖는다. 실제값, 계획, 예측, 시나리오, 경쟁사 참조는 물리적/논리적 저장 영역과 조회 조건에서 분리한다.

### 8.2 MDM·카탈로그·GraphRAG의 역할

- **ECM**: 어떤 회사/조직/시나리오에서 무엇을 의미하는지 정의한다.
- **MDM**: 품목, 고객, 공급처, 계정, 공정, 시설 같은 기준 대상을 정합화한다.
- **데이터 카탈로그**: 어떤 데이터셋이 존재하는지, 소유자·품질·민감도·계보·사용 조건을 설명한다.
- **GraphRAG**: 위 대상들 사이의 승인된 관계를 검색·설명한다. 권한 필터와 증빙을 반드시 통과한다.
- **시뮬레이션 엔진**: 승인된 스냅샷과 가정을 입력으로 계산한다. LLM은 계산값을 대신 만들지 않는다.

### 8.3 MCP·외부 시스템

- `REAL` 문맥에서도 MCP는 기본 읽기 전용, 데이터 계약·권한·목적·감사 통과 후에만 사용한다.
- `VIRTUAL` 및 `COMPETITOR_REFERENCE` 문맥에서는 원칙적으로 외부 운영 시스템 호출을 금지한다. 승인된 정적 스냅샷 또는 익명화된 안전 데이터만 사용한다.
- 쓰기 연계는 별도 Shadow Mode와 사람이 승인한 제한된 명령에서만 가능하며, 가상 시나리오 결과를 실제 시스템에 자동 반영하지 않는다.

## 9. API 명세 초안

Prefix: `/api/v1/enterprise-context`

| Method | Path | 설명 | 필요 권한 |
|---|---|---|---|
| `GET` | `/tree` | 사용자가 접근 가능한 조직/가상 모델 트리 | `READ` |
| `POST` | `/entities` | 실제/가상/경쟁사 엔터티 초안 생성 | `EDIT_MASTER` |
| `GET` | `/entities/{entity_id}` | 프로필·관계·유효기간 포함 조회 | 범위 `READ` |
| `PATCH` | `/entities/{entity_id}` | 승인 전 변경안 수정 | `EDIT_MASTER` |
| `POST` | `/entities/{entity_id}/approve` | 조직/프로필 버전 승인 | `APPROVE_MASTER` |
| `POST` | `/entities/{entity_id}/clone` | 가상 시나리오/경쟁사/조직 템플릿으로 복제 | `CLONE_TO_VIRTUAL` |
| `GET` | `/contexts/{scope_id}/resolved-profile` | 상속이 해석된 실행 프로필 조회 | 범위 `READ` |
| `POST` | `/contexts/select` | 세션의 EnterpriseContext 선택/검증 | 범위 `READ` |
| `POST` | `/scenarios` | 가상 시나리오 생성 및 가정 묶음 연결 | `RUN_SIMULATION` |
| `POST` | `/scenarios/{scenario_id}/promote-request` | 가상 설계를 실제 조직 초안으로 승격 요청 | `REQUEST_PROMOTION` |

### 9.1 복제 요청 예시

```json
{
  "clone_mode": "VIRTUAL_SCENARIO",
  "target_parent_id": "bu_battery_materials",
  "name": "배터리소재 제3공장(증설안 A)",
  "effective_from": "2027-01-01",
  "copy_policy": {
    "profiles": true,
    "process_templates": true,
    "agent_bindings": true,
    "catalog_definitions": "reference",
    "approved_snapshots": true,
    "transaction_data": false,
    "connection_credentials": false
  },
  "assumptions": {
    "annual_capacity_ton": 120000,
    "electricity_price_change_pct": 12,
    "ramp_up_months": 9
  }
}
```

서버는 복제본에 새 `entity_id`, `scenario_id`, `snapshot_id`를 부여하며, 원본 ID·복사 정책·가정·승인자를 감사 로그에 남긴다.

## 10. 구현 구성

### 10.1 백엔드 모듈

```text
core/enterprise_context/
├─ models.py                 # Pydantic 모델, 상태/관계 enum
├─ repository.py             # ECM 저장소와 유효기간 질의
├─ resolver.py               # 범위·프로필 상속 해석
├─ authorization.py          # 조직 범위 권한 판정
├─ clone_service.py          # 가상/경쟁사 복제와 격리 정책
├─ profile_recommender.py    # 업종·업무 템플릿/에이전트 추천 근거
└─ audit.py                  # Decision Ledger 연동
api/routes/enterprise_context_control.py
```

기존 `core/org_directory.py`, `core/master_data.py`, `core/crosswalk.py`, `core/mcp_broker.py`를 한 번에 교체하지 않는다. ECM을 공통 범위/프로필 해석 계층으로 먼저 도입하고, 기존 모듈이 `EnterpriseContext`를 받도록 점진적으로 이행한다.

### 10.2 프론트엔드 화면

| 화면 | 핵심 기능 |
|---|---|
| Enterprise Context Switcher | 현재 회사·법인·사업부·공장·시나리오 선택, 권한 내 탐색 |
| 조직/프로필 스튜디오 | 조직 트리·관계 그래프·유효기간·프로필·템플릿 바인딩 관리 |
| 가상 기업 실험실 | 원본 선택, 복사 범위, 가정 입력, 격리 상태·비용·결과 비교 |
| 경쟁사 참조 보드 | 공개 근거, 신뢰도, 갱신일, 시장 시나리오 연결 |
| 권한 매트릭스 | 사용자/역할 × 조직 범위 × 도메인 × 행동 관리 |
| 상담사 대화창 | 선택된 조직 문맥에서 필요한 데이터·업무·템플릿을 선택형으로 제안 |

현재 Control Room의 프로젝트 선택은 유지한다. 다만 프로젝트는 반드시 `enterprise_scope_id`와 `entity_mode`를 소유하고, 범위가 다른 프로젝트를 같은 실행 상태로 섞어 보이지 않게 한다.

## 11. 단계별 수행계획

### E0 — 용어·기준 확정

- 조직 노드/관계/유효기간/상태/복제 정책의 표준 용어를 확정한다.
- 첫 파일럿 조직(예: 하나의 법인–두 사업부–두 공장)을 정하고, 실제 원본 시스템과 책임자를 지정한다.
- 실제·계획·예측·가상·경쟁사 데이터 상태와 승격 규칙을 승인한다.

### E1 — 최소 Enterprise Context ✅ **백엔드 완료 (2026-07-28)**

- `enterprise_entities`, `organization_nodes`, `organization_edges`, `enterprise_profiles`를 도입한다.
- 전역 선택기, 범위 권한, 프로젝트 `enterprise_scope_id` 귀속을 구현한다.
- 선택 범위를 ContextEngine, 상담사, 슈퍼바이저에 읽기 전용 문맥으로 주입한다.

> #### ✅ E1 백엔드 완료 — 조직 그래프·범위 전개·권한 가시성
>
> 구현: `core/enterprise_context/`(패키지 전환 — `models.py` · `repository.py` · `resolver.py` ·
> `seed.py`, 기존 `context.py` 는 그대로) · `api/routes/enterprise_context_control.py`(라우트 11) ·
> 테스트 36건(전체 619 통과)
>
> **패키지 전환은 호출부 수정 0** — §10.1 이 예고한 구조로 바꾸면서 `__init__.py` 가 ECM-lite 심볼을
> re-export 한다. `api/deps.py`·`advisor_store.py`·`advisor_control.py`·`factory_control.py` 의
> `from core.enterprise_context import ...` 가 그대로 동작한다(기존 26건 테스트 무영향).
>
> | 항목 | 상태 |
> |---|---|
> | 4테이블 + 유효기간·승인·상태(DRAFT/ACTIVE/SUSPENDED/ARCHIVED) | ✅ |
> | 노드 + **다중 관계 그래프**(4관계 공존), 기본 트리는 `default_parent_id` 로 분리 | ✅ |
> | 범위 전개(운영 하위·조상·집계 범위·서비스 대상) | ✅ |
> | 권한 가시성 — 부서 권한을 ECM 노드로 연결 | ✅ |
> | 문맥 해석 — 부서 id 와 ECM `node_id` 를 **모두** 받는다 | ✅ |
> | §3.3 예시 조직 시드(멱등, `source_ref='design_doc_example'`) | ✅ |
> | 프로필 **저장·조회**와 `is_effective`(승인된 것만 상속 참여) | ✅ |
> | 프로필 **상속 병합** | ❌ **E2** — 반쪽 병합은 "되는 것처럼 보이는데 아닌" 상태라 더 위험 |
> | 전역 선택기 UI, 프로젝트 화면의 문맥 표시 | ❌ 다음 단계(프론트) |
> | 복제·시나리오 | ❌ E3 |
>
> **핵심 결정 4건**
> ① ★ **권한 상속은 `OPERATING_PARENT` 만 따른다.** 공유서비스·연결집계 관계는 자동 열람 권한을
>   만들지 않는다(§6.1). 실측: 전사공통 노드의 `consolidation_scope` 2건·`shared_service_consumers`
>   2건이 나오지만 그 사업부 상세 조회는 403 이다. 응답에 "열람 권한을 부여하지 않습니다" 를 명시하고
>   `GET /meta` 가 `inheritable_relations: ["OPERATING_PARENT"]` 를 스스로 알려준다.
> ② **부서 권한을 재사용한다**(§10.1 점진 이행). `scope_assignments` 를 새로 만들지 않고
>   `organization_nodes.dept_id` 로 기존 부서에 매핑했다. 지금 새 권한 축을 만들면 Phase 1~5 에서
>   검증된 부서 권한과 두 갈래가 되어 어긋난다. ECM 전용 권한 테이블은 **E2**.
> ③ **부서 매핑이 없는 노드는 자체 열람 권한을 갖지 않는다**(fail-closed). 단 트리가 조각나지 않게
>   조상은 `readable=false` 로 **경로 표시용**으로만 포함한다 — 빼면 자기 조직의 위치를 알 수 없고,
>   열람 가능으로 표시하면 권한이 부풀려진다.
> ④ **순환 관계 거부**(400). 사이클이 생기면 범위 전개가 무한 재귀에 빠져 서버가 멈춘다. 조회 경로에도
>   깊이 상한(32)을 둬서 손상된 데이터로도 죽지 않게 했다.
>
> **가상·경쟁사 근거 강제**: 가상 조직은 `base_entity_id`(복제 원본), 경쟁사는 `evidence_ref`(공개
> 근거) 없이 만들 수 없다(§2.1-4, §7.3). 실제/가상/경쟁사는 한 트리에 섞이지 않는다(`entity_mode` 필터).
>
> **실측(`ORG_ENFORCE=True`, 실제 부서·사용자)**: 같은 트리를 세 사용자가 다르게 본다 —
> `admin` 9개 전부 / `bob`(sales) **0개**(시드는 hq·production 매핑) / `exec` 5개 열람 + `LS`·`LS MnM`
> 은 경로 표시만. `bob` 의 문맥 선택은 403. 순환 400, 가상 근거 누락 400, 시드 재실행 skipped.
>
> **남은 이행 항목**: `enterprise_scope_id` 는 여전히 부서 id 를 담은 데이터가 많다.
> `resolve_scope_ref` 가 `kind`(`ecm_node`/`department_mapped`/`department`)로 구분해 주므로,
> 승격 대상을 식별할 수 있다. 일괄 승격은 실제 파일럿 조직 확정(E0) 이후에 한다.

> #### ✅ ECM-lite 선점 완료 (2026-07-28) — 상담사(M0) 한정
>
> E1 전체는 미착수다. 다만 상담·Blueprint 는 **사용자 데이터**라 문맥 키 없이 쌓이기 시작하면
> 저장분 마이그레이션 + 화면 + API 를 한꺼번에 고쳐야 한다. 그래서 **문맥 키와 격리 규칙만**
> 먼저 선점했다(당시 데이터 0행이라 마이그레이션 비용 0).
>
> 구현: `core/enterprise_context.py` · `api/deps.py`(`enterprise_context` 의존성) ·
> `config.py`(기본 테넌트 + 헤더 3종) · `core/advisor_store.py`(문맥 3키 + 멱등 컬럼 마이그레이션) ·
> `core/advisor_blueprint.py` · `api/routes/advisor_control.py` · 테스트 26건(전체 525 통과)
>
> | 항목 | 상태 |
> |---|---|
> | 문맥 3키(`tenant_id`·`enterprise_scope_id`·`entity_mode`) 표준화·전달·저장 | ✅ |
> | `entity_mode` 기반 조회 격리(목록·집계·**단건**) | ✅ |
> | Blueprint 가 상담의 문맥을 승계(요청 헤더가 아니라) | ✅ |
> | `APPROVE` 행동 분리(§6) — 판정 지점만 분리, 판정 내용은 아직 쓰기와 동일 | ⚠️ seam only |
> | 조직 노드·관계 그래프, 프로필 상속 해석 | ❌ E1 |
> | 프로필 기반 템플릿·질문·에이전트 추천 차별화(수용 기준 3) | ❌ E2 |
> | 가상 조직 복제·스냅샷·가정, 경쟁사 근거 관리 | ❌ E3 |
>
> **결정 2건 (이 문서가 명시하지 않아 구현에서 확정)**
> ① **`REAL` 외 문맥의 생성은 막았다.** §2.1-4 의 안전장치(격리 스냅샷·가정 세트·외부 연계 차단·
>   복사 정책)가 E3 의 내용인데, 그것 없이 `VIRTUAL` 자료를 만들 수 있게 열어두면 가정값이 실제와
>   섞인 채 쌓인다(§13 위험표의 그 항목). `entity_mode` 컬럼은 기록·격리 기반으로만 먼저 깔았고,
>   조회 문맥으로는 이미 유효하다. 생성 시도는 400 + "E3 선행" 안내.
> ② **플레이북(`playbooks/*.json`)은 §4.4 상속 체인 최상위 "산업 공통 프로필"의 저작 기본값이다.**
>   이 문서는 플레이북을 언급하지 않는데 `data_profile`/`solution_profile`/`agent_profile` 이
>   플레이북의 데이터 요구·추천 템플릿과 겹쳐 우선순위를 정해야 했다. 도메인 지식은 리뷰·이력이
>   필요하므로 git diff 가 되는 파일에 남기고, `enterprise_profiles`(DB)는 **조직별 차이만** 담는다.
>   오버레이 해석(리솔버)은 E2. → 이 결정에 이견이 있으면 E2 착수 전에 뒤집는 것이 싸다.
>
> **`enterprise_scope_id` 는 지금 부서 id(`org_directory`)를 담는다.** E1 에서 ECM `node_id` 로
> 승격되어야 하며, 그 대상을 식별할 수 있도록 `EnterpriseContext.scope_kind` 로 출처를 표시한다.

### E2 — 프로필 기반 생성·권한 강제

- 프로세스·데이터 계약·에이전트팩·업무 템플릿 바인딩과 상속 해석을 구현한다.
- MDM/카탈로그/크로스워크/MCP에 범위 키를 도입하고 권한을 강제한다.
- 공유 서비스·연결 집계의 도메인별 접근을 검증한다.

### E3 — 가상 기업/경쟁사 Sandbox

- 안전한 복제, 스냅샷, 가정 세트, 결과 비교, 승격 요청을 구현한다.
- 가상 문맥의 외부 연계 차단과 경쟁사 근거·신뢰도 관리를 검증한다.
- 하나의 신사업/증설 시나리오를 실제 사용자와 운영한다.

### E4 — 전사 디지털트윈 연계

- 법인·사업부·공장 간 집계, 기준 시나리오, 외부환경 인텔리전스, 결정론적 계산 모듈을 연결한다.
- 경영진 보드에서 실제·계획·예측·가상 결과를 근거·가정과 함께 비교한다.

## 12. 완료 판정과 테스트

다음은 구현 완료의 최소 수용 기준이다.

1. 상위 법인 권한 사용자는 정책상 허용된 하위 사업부·공장 프로젝트를 보되, 다른 법인 데이터는 볼 수 없다.
2. 사업부 권한 사용자는 상위 법인이나 형제 사업부의 상세 운영 데이터를 보지 못한다.
3. 같은 “생산계획” 요청이라도 선택 조직의 업종·공정·데이터 계약에 따라 다른 템플릿·질문·에이전트 추천 근거가 나온다.
4. 실제 공장 프로필을 가상 제3공장으로 복제할 때 거래·자격증명·외부 쓰기 권한이 복제되지 않는다.
5. 가상 시나리오의 가정과 결과가 실제/계획/예측 데이터와 조회·저장·차트에서 명확히 분리된다.
6. 경쟁사 값마다 출처·기준일·신뢰도를 확인할 수 있으며, 근거 없는 값은 공식 결과로 승격되지 않는다.
7. 프로젝트, 생성 SW, 시뮬레이터, 데이터셋, Decision Ledger가 같은 `enterprise_scope_id`/`scenario_id`로 추적된다.

## 13. 위험과 방지책

| 위험 | 방지책 |
|---|---|
| 조직도를 한 개 트리로 고정 | 노드+관계 모델, 기본 트리는 보기용으로만 사용 |
| 전사 권한이 모든 상세 데이터 권한으로 비화 | 조직 상속과 도메인·행동 권한을 분리 |
| 가상 시나리오가 실제 DB를 오염 | 별도 scenario/snapshot 키, 외부 쓰기·자격증명 복제 금지 |
| 업종 템플릿이 강제되어 현장 예외를 삭제 | 프로필 상속·오버레이·사용자 승인과 버전 관리 |
| 경쟁사 추정을 사실처럼 사용 | 근거/신뢰도/상태 의무화, 승인 전 공식 보고 사용 금지 |
| LLM에 전체 조직·데이터를 과주입 | 권한 필터된 최소 문맥, 카탈로그·계보 기반 검색, 프롬프트 예산 |

## 14. 관련 문서의 역할

- [`design_org_permission_enterprise.md`](design_org_permission_enterprise.md): ECM 범위 권한과 기존 조직·권한 단계의 이행 설계
- [`design_master_data_m1.md`](design_master_data_m1.md): ECM과 MDM 기준정보 저장소의 연결
- [`design_master_data_m2.md`](design_master_data_m2.md): 법인/공장별 외부 키와 스키마 크로스워크
- [`design_master_data_m3.md`](design_master_data_m3.md): 조직/시나리오 문맥의 안전한 MCP 조회
- [`design_backbone_system_platform.md`](design_backbone_system_platform.md): ERP/MES급 운영 플랫폼과 범위 키/집계 경계
- [`LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md`](LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md): 전체 제품 구현 순서와 API/품질 기준

이 설계는 조직을 예쁘게 표현하기 위한 부가 기능이 아니다. 사용자가 어느 회사·법인·사업부·공장을 위해 무엇을 만들고, 어떤 데이터와 가정으로 미래를 실험하는지를 일관되게 보장하는 제품의 기반이다.
