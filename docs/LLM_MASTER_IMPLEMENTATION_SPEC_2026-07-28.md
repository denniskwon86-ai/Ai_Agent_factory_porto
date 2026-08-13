# AI Factory Studio — LLM 구현 마스터 명세서

> **최신 실행 기준(2026-08-03, 용어 보강 2026-08-13):** 이 문서는 기능별 상세 요구사항의 기준으로 유지한다. 다만 §14의 기존 단계 순서는 이후 구현 진척과 경쟁 기준점 재검토 이전에 작성된 상위 계획이다. 최신 제품 범주·차별화 판단은 [`strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md`](strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md), 실제 착수 순서·선행조건·완료 관문은 [`roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md`](roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md)를 우선한다. 핵심 순서는 **CL-0.5/Host Runtime 안전 경계 → 원료 구매 수직 제조 경영 온톨로지(경영 의미 모델) → 운영 앱 전달·수락 → 결정론적 Twin → 의사결정·실행·효과 폐루프 → 엔터프라이즈 제품화**이다.

> **Enterprise Context Master 선행 규칙(2026-07-28):** 이후 구현되는 MDM, 카탈로그, MCP, 권한, 상담사, SW 생성기, 시뮬레이션은 `tenant → 기업집단 → 법인 → 사업부 → 사업장/공장` 문맥과 실제/가상/경쟁사 상태를 명시적으로 가져야 한다. 상세 모델·API·복제·격리 규칙은 [`design_enterprise_context_master.md`](design_enterprise_context_master.md)를 SSOT로 한다.

> **앱 전달·의사결정·발간 확장안(2026-08-03):** 생성 앱의 지정 사용자 전달·수락·내 앱 등록, App-in-App 인증 상속, 시뮬레이션 기반 Decision Package·회의 요청·세 관점 검토서·대내외 발간의 상세 구현 준비안은 [`design_app_delivery_decision_publication_loop.md`](design_app_delivery_decision_publication_loop.md)를 따른다. 현재는 상세기획 상태이며 구현 완료로 간주하지 않는다.

> 문서 목적: 이 문서는 다른 LLM 또는 개발 에이전트가 별도의 대화 이력 없이도 AI Factory Studio의 제품 의도, 현재 구현 경계, 향후 기능 설계, 구현 우선순위와 완료 기준을 이해하고 일관되게 작업하도록 하는 기준 문서다.
>
> 기준일: 2026-07-28  
> 문서 성격: **To-Be 구현 명세 + As-Is 경계 정의**. 현재 코드에 없는 기능을 이미 구현된 것처럼 표현하지 않는다.

---

## 0. 작업자 필독 규칙

1. 사용자 대면 문서, 화면 문구, 운영 로그, 협업 보고는 한국어를 기본으로 한다. 코드 식별자와 표준 기술 용어는 필요할 때만 영어를 사용한다.
2. 이 제품은 단순한 “AI 코드 생성기”가 아니다. 궁극적으로 현업 데이터와 기준정보를 기반으로 업무 앱을 생성하고, 전사 운영·계획·시나리오를 검증하는 플랫폼이다.
3. LLM은 기획, 추천, 설명, 초안 작성, 코드 생성, 비정형 지식 해석에 사용한다. 숫자 계산, 권한 판정, 데이터 품질 판정, 시뮬레이션 결과는 가능한 한 결정론적 규칙·검증 엔진이 담당한다.
4. 외부 업무 시스템 연계의 기본값은 **읽기 전용**이다. 쓰기 연계는 데이터 계약, 권한, 감사 로그, Shadow Mode 검증 뒤에만 허용한다.
5. 목표 기능을 한 번에 구현하지 않는다. 아래 로드맵의 선행 조건과 완료 기준을 만족한 뒤 다음 단계로 이동한다.
6. 변경 전에는 현행 소스, `AI_HANDOFF.md`, 최근 handoff 문서, 본 문서를 함께 읽는다. 작업 중 사용자 또는 다른 에이전트가 만든 변경사항을 덮어쓰지 않는다.

---

## 1. 제품 비전과 성공 정의

### 1.1 최종 비전

AI Factory Studio는 다음 흐름을 제공하는 기업 운영 플랫폼을 지향한다.

```text
현업 사용자 요청
  → 업무·데이터 설계 상담
  → 필요한 데이터와 기준정보 정의
  → 현업 시스템/파일의 읽기 전용 연계
  → AI 에이전트가 업무 앱·워크플로우·시뮬레이터 생성
  → 부서별 운영·공유·승인
  → 전사 데이터·지식·의사결정 통합
  → 실제/계획/예측/시나리오 기반 디지털트윈 경영
```

### 1.2 고객에게 제공할 일곱 가지 핵심 가치

1. **업무 앱 생성**: 현업 사용자가 요구사항을 바탕으로 필요한 SW를 직접 생성·검토·사용한다.
2. **전사 지식화**: 생성된 앱, 문서, 데이터 정의, 운영 지식이 전사 라이브러리와 지식 허브에 누적된다.
3. **시뮬레이션**: 부서 단위 또는 전사 단위의 운영·계획 시나리오를 실행한다.
4. **에이전트 공장**: 업무별 에이전트, 스킬, 워크플로우, 템플릿을 추천·생성·관리한다.
5. **전역 슈퍼바이저**: 자비스처럼 제품 전체 상태를 이해하고 사용자 질의·통제·개입을 지원한다.
6. **부서별 권한과 공유**: 부서가 특화 기능을 안전하게 만들고 공유하며, 데이터 접근은 권한에 따라 제한된다.
7. **경영 디지털트윈**: 수주, 구매, 생산, 품질, 물류, 판매, 회계와 전사 손익을 연결해 미래 시나리오를 검증한다.

### 1.3 제품의 차별점

핵심 차별점은 “생성 속도”만이 아니다.

- **기업 의도와 결정의 보존**: 왜 이 앱·규칙·수치가 만들어졌는지 추적 가능해야 한다.
- **데이터 기반 생성**: 모델이 바뀌어도 조직의 지식·기준·표준·데이터 계약을 참조해 일정한 품질을 유지해야 한다.
- **안전한 운영 전환**: 생성한 앱과 규칙을 실제 운영에 바로 쓰지 않고 Shadow Mode로 검증한다.
- **비용 대비 품질 최적화**: 토큰당 비용이 아니라 “승인된 결과물 1건당 비용”을 최소화한다.

---

## 2. 현재 시스템(As-Is)과 명확한 경계

### 2.1 현재 구현의 정체성

현재 시스템은 FastAPI + LangGraph + React/Vite 기반의 **AI 업무 SW 생성·검토·통제 플랫폼(Control Plane)** 이다. 다음 기능은 실제 코드 경로가 있다.

- 프로젝트, 템플릿, Mega 프로젝트 생성·관리
- 선택형 요구사항 정제, RFP, 기획, 아키텍처, WBS 생성
- 백엔드·프런트엔드 코드 생성, 빌드, 리뷰, QA, 릴리스, 내보내기
- HOTL(Human-on-the-loop) 승인·수정·재개
- SSE 기반 진행 이벤트·타임라인
- 지식 허브, 릴리스 RAG, 경량 M1 기준정보, Crosswalk, 읽기 전용 MCP 브로커
- 텔레메트리, 스킬 진화 제안·승인, 부분 추적성·영향 분석

### 2.2 현재 구현이 아닌 것

아래는 목표 또는 부분 기반 기능이며, 완성된 제품 기능으로 안내하거나 설계해서는 안 된다.

- 운영용 멀티테넌트 업무 앱 런타임
- SSO·서버 강제 RBAC·부서/필드 단위 데이터 권한
- 완성형 데이터 카탈로그, 데이터 품질, 데이터 계보, 데이터 계약
- ERP/MES에 대한 안전한 양방향 운영 연계
- 결정론적 생산·원가·손익·현금흐름 시뮬레이터
- 전사 경영 디지털트윈
- 프로젝트 ID와 무관하게 전사 상태를 완전히 이해하는 자비스형 전역 슈퍼바이저

### 2.3 현재 주요 소스 경계

| 관심사 | 대표 위치 |
|---|---|
| FastAPI 진입점/라우터 | `main.py`, `api/routes/` |
| 그래프·라우팅 | `core/agent_graph.py` |
| 비동기 스프린트 제어 | `core/async_orchestrator.py` |
| LLM·공급자 폴백 | `core/llm_gateway.py`, `config.py` |
| 문맥·RAG | `core/context_engine.py`, `core/knowledge_base.py` |
| 경량 기준정보 | `core/master_data.py`, `api/routes/master_control.py` |
| Crosswalk/MCP | `core/crosswalk.py`, `core/mcp_broker.py` |
| 상태 모델 | `state_models.py` |
| 프런트 앱/상태 | `frontend/src/App.tsx`, `frontend/src/store/useFactoryStore.ts` |
| 작업 통제/승인 UI | `frontend/src/components/ControlPanel.tsx`, `HOTLInput.tsx` |

---

## 3. 목표 논리 아키텍처

```text
┌───────────────────────────────────────────────────────────────────────┐
│ 사용자 / 부서 / 경영진                                                  │
├───────────────────────────────────────────────────────────────────────┤
│ 전역 자비스: 업무·데이터 설계 상담 / 상태 질의 / 통제 / 설명             │
├───────────────────────────────────────────────────────────────────────┤
│ Solution Blueprint + Decision Ledger                                   │
│ - 목표, KPI, 범위, 가정, 승인, 근거, 데이터 요구사항, 변경 이력           │
├───────────────────────────────────────────────────────────────────────┤
│ 데이터 기반 계층                                                        │
│ MDM → 데이터 카탈로그 → 품질·계보·계약 → 제조 경영 온톨로지 → 권한       │
├───────────────────────────────────────────────────────────────────────┤
│ 연계 계층                                                               │
│ 파일/DB/API/MCP 읽기 연계 → 캐시/정규화 → Shadow Mode → 제한적 쓰기      │
├───────────────────────────────────────────────────────────────────────┤
│ AI Factory Control Plane                                                │
│ 템플릿/에이전트/생성/검토/테스트/릴리스/추적성/비용·품질 최적화           │
├───────────────────────────────────────────────────────────────────────┤
│ 부서 업무 앱 / 전사 통합 앱 / 결정론적 시뮬레이션·디지털트윈              │
└───────────────────────────────────────────────────────────────────────┘
```

### 3.1 계층 간 책임 분리

| 계층 | 책임 | 금지 사항 |
|---|---|---|
| LLM/에이전트 | 요구 이해, 후보 제안, 문서·코드 생성, 자연어 설명 | 숫자 진실·권한 진실을 단독으로 판단 |
| Decision Ledger | 결정·가정·승인·근거의 불변 이력 | 임의 수정으로 이력 삭제 |
| MDM | 전사 공통 식별자와 표준 값 | 모든 거래 데이터를 MDM에 넣기 |
| 카탈로그 | 데이터 자산의 메타데이터·책임·발견 | 데이터 원천 그 자체를 대체 |
| 제조 경영 온톨로지 | 개체·업무 사건·조직 책임·KPI·정책·영향 관계의 의미와 제약 | MDM·카탈로그를 대체하거나 LLM이 관계를 무승인 확정 |
| Graph RAG | 온톨로지·지식 그래프의 관계를 따라 근거와 영향 경로 탐색 | 공식 관계·권한 판정·수치 계산을 대체 |
| 데이터 계약 | 앱/시스템 간 입출력·품질·권한 약속 | 계약 없는 직접 테이블 결합 |
| Shadow Mode | 실제 데이터에서 새 규칙의 무해한 병렬 검증 | 검증 없이 운영 쓰기 |
| 시뮬레이션 엔진 | 재현 가능한 수치 계산과 비교 | LLM 출력값을 계산 결과로 확정 |

---

## 4. 기능 1 — 업무·데이터 설계 상담사

### 4.1 문제 정의

현재의 Clarification은 이미 프로젝트를 만들기로 한 사용자에게 요구사항을 구체화한다. 하지만 신규 사용자는 무엇을 만들어야 하는지, 필요한 데이터가 무엇인지, 준비가 되었는지 모른다.

**업무·데이터 설계 상담사(Business Discovery Advisor)** 는 프로젝트 생성 이전 단계에서 사용자의 모호한 업무 목표를 구현 가능한 청사진으로 변환한다.

### 4.2 사용자 시나리오

```text
사용자: 나는 경영관리팀 담당자인데 내년도 사업계획 데이터를 생성하고 관리하고 싶어.

상담사:
1) 전사/사업부/제품 중 어디까지 계획을 관리할지 선택하게 한다.
2) 계획 수립, 승인, 실적 비교, 시나리오 중 필요한 범위를 확인한다.
3) 시스템에 등록된 데이터와 연결 가능한 원천을 조회한다.
4) 필요한 기준정보·실적·계획 동인·외부 지표를 제시한다.
5) 보유/부족/검증 필요 데이터를 구분한다.
6) 추천 구축 순서와 초기 프로젝트 템플릿을 제안한다.
7) 사용자가 승인하면 Solution Blueprint와 프로젝트 초안을 생성한다.
```

### 4.3 기능 요구사항

#### F-DA-01. 전역 상담 진입

- 프로젝트 미선택 런처와 모든 프로젝트 화면에서 접근 가능해야 한다.
- 상담 범위를 `전사`, `부서`, `프로젝트`, `데이터`, `시뮬레이션`으로 표시한다.
- 현재 프로젝트 문맥이 있으면 관련 산출물·WBS·연결 데이터만 권한 범위 내에서 참조한다.

#### F-DA-02. 짧은 선택형 대화

- 한 번에 하나의 결정만 요청한다.
- 각 질문은 2~4개의 추천 선택지와 “직접 입력”을 제공한다.
- 장문 입력은 선택 사항이며, 기본 추천안만 선택해도 진행 가능해야 한다.
- 대화 질문은 목적·범위·시간·사용자·데이터·결정 단계를 우선한다.

#### F-DA-03. 업무 유형 분류

초기 분류는 규칙 + 저비용 LLM의 구조화 출력으로 수행한다.

| 업무 유형 | 예시 |
|---|---|
| 계획/예산 | 경영계획, 예산 편성, 인력 계획 |
| 운영 관리 | 구매 요청, 생산 지시, 품질 이슈, 물류 배차 |
| 분석/보고 | 매출 분석, 원가 분석, KPI 대시보드 |
| 시뮬레이션 | 수요 변화, 원가 상승, 생산능력 제약 |
| 데이터 정비 | 마스터 통합, 엑셀 정리, 시스템 키 매핑 |
| SW 생성 | 특정 현업 기능의 화면·API·워크플로우 생성 |

#### F-DA-04. 데이터 요구사항 추천

각 업무 유형별 플레이북에서 다음을 추천한다.

- 필수 기준정보
- 필수 실적/거래 데이터
- 계획/예측 동인
- 외부 지표
- 데이터 소유 부서
- 일반적인 원천 시스템
- 최소 시작 데이터와 고도화 데이터

#### F-DA-05. 데이터 준비도 산정

LLM의 주관적 판단이 아니라 정형 규칙으로 산정한다.

```text
준비도 =
  기준정보 완성도       25점
  과거 실적 연결성      25점
  계획/운영 동인 확보율 25점
  품질·최신성           15점
  책임자 지정           10점
```

점수와 함께 반드시 결손 항목, 영향, 다음 조치를 표시한다.

#### F-DA-06. Solution Blueprint 생성

사용자 승인 후 상담 결과를 구조화된 업무 자산으로 저장한다. 이 결과는 RFP·WBS·프로젝트·데이터 준비 작업의 입력값이 된다.

### 4.4 화면 구성

| 영역 | 내용 |
|---|---|
| 대화 영역 | 질문, 추천 선택지, 사용자 답변, 근거 링크 |
| 상담 결과 보드 | 목표, 범위, KPI, 추천 시스템 유형, 준비도 |
| 데이터 보드 | 보유/부족/검증 필요 데이터, 소유 부서, 연결 후보 |
| 실행 보드 | 권장 단계, 위험요인, 예상 산출물, 생성 버튼 |

### 4.5 핵심 데이터 모델

```text
consultations
  id, tenant_id, workspace_id?, user_id, scope, status,
  initial_prompt, summary, created_at, updated_at

consultation_turns
  id, consultation_id, turn_no, speaker, message,
  question_type, option_set_json, selected_values_json, created_at

solution_blueprints
  id, consultation_id, title, business_domain, objective,
  scope_json, kpis_json, recommended_solution_json,
  readiness_score, status, approved_by, approved_at

data_requirements
  id, blueprint_id, canonical_term, requirement_type,
  necessity(required/recommended/optional), purpose,
  expected_grain, freshness_requirement, owner_department,
  source_candidate_json, readiness_status, readiness_score
```

### 4.6 API 초안

```text
POST   /api/v1/advisor/consultations
POST   /api/v1/advisor/consultations/{id}/messages
GET    /api/v1/advisor/consultations/{id}
POST   /api/v1/advisor/consultations/{id}/blueprint
GET    /api/v1/advisor/blueprints/{id}
POST   /api/v1/advisor/blueprints/{id}/approve
POST   /api/v1/advisor/blueprints/{id}/bootstrap-project
POST   /api/v1/advisor/blueprints/{id}/create-data-tasks
```

### 4.7 기존 시스템과의 연결

```text
상담 완료
  → Solution Blueprint 승인
  → 프로젝트 메타데이터/지식 연결/템플릿 추천 생성
  → RFP Analyst에는 정제된 Blueprint를 입력
  → Master PM/Architect/PMO는 데이터 요구사항과 가정을 참조
  → WBS에 데이터 준비·연계·검증 태스크 자동 추가
```

---

## 5. 기능 2 — Solution Blueprint와 Decision Ledger

### 5.1 Solution Blueprint

Blueprint는 단순 보고서가 아니라 시스템 전반이 참조하는 구조화 계약이다.

| 영역 | 필수 필드 |
|---|---|
| 업무 | 목적, 문제, 사용자, 의사결정자, 범위, 제외 범위 |
| KPI | 지표명, 공식, 단위, 기준일, 허용 오차 |
| 데이터 | 필요 데이터, 원천, 소유자, 최신성, 민감도 |
| 프로세스 | 입력, 검증, 승인, 예외, 출력 |
| 시스템 | 추천 앱, 화면, API, 템플릿, 에이전트 |
| 시뮬레이션 | 가정, 변수, 제약, 기준 시나리오 |
| 위험 | 데이터 결손, 권한, 외부 연계, 품질, 비용 |

### 5.2 Decision Ledger

모든 중요한 변화는 불변 이벤트로 기록한다.

```text
decision_ledger_events
  id, tenant_id, workspace_id, project_id?, blueprint_id?,
  event_type, subject_type, subject_id,
  actor_type(user/agent/system), actor_id,
  decision, rationale, evidence_refs_json,
  input_version_refs_json, output_version_refs_json,
  parent_event_id?, created_at
```

#### 필수 이벤트 유형

- `REQUIREMENT_CONFIRMED`
- `BLUEPRINT_APPROVED`
- `DATA_REQUIREMENT_ACCEPTED`
- `MASTER_VALUE_CHANGED`
- `DATA_CONTRACT_PUBLISHED`
- `WBS_APPROVED`
- `RELEASE_ACCEPTED`
- `SCENARIO_EXECUTED`
- `SHADOW_MODE_PASSED`
- `PRODUCTION_WRITE_APPROVED`

#### 원칙

- 이벤트는 수정 대신 정정 이벤트로 보완한다.
- AI의 추천과 사용자의 확정 결정을 구분한다.
- 근거 데이터셋·버전·테스트 결과가 없는 경영 수치는 “검증되지 않은 추정”으로 표시한다.

---

## 6. 기능 3 — MDM, 데이터 카탈로그, 제조 경영 온톨로지, 품질, 계보, 데이터 계약

### 6.1 개념 구분

| 구성 | 정의 | 대체 불가 관계 |
|---|---|---|
| MDM | 고객·제품·조직·계정 등 전사 공통 기준값 | 카탈로그로 대체 불가 |
| 데이터 카탈로그 | 데이터 자산의 설명·위치·책임·갱신·민감도 | Graph RAG로 대체 불가 |
| 용어사전 | 비즈니스 용어·동의어·약어·계산 정의 | MDM과 연결되나 별도 관리 |
| 데이터 품질 | 완전성·중복·유효성·최신성·정합성 | 단순 LLM 평가 금지 |
| 데이터 계보 | 원천→변환→앱→보고서→결정의 영향 관계 | 추적성 그래프의 근거 |
| 데이터 계약 | 시스템/앱 간 필드·형식·권한·SLA 약속 | 직접 DB 결합의 대안 |
| 제조 경영 온톨로지 | 공식 개체·업무 사건·조직 책임·정책·KPI·재무 영향의 의미 관계와 제약 | MDM·카탈로그·용어사전을 연결하지만 대체하지 않음 |
| Graph RAG | 승인된 관계를 따라 근거·관련 지식·영향 경로 후보를 탐색 | 온톨로지·권한·계산 그래프를 대체 불가 |

#### 6.1.1 정식 용어와 구현 경계

- 기술 정식 명칭: **제조 경영 온톨로지(Manufacturing Management Ontology)**
- 제품·사업 설명: **경영 의미 모델**
- 사용자 화면 설명: **기업 경영 의미지도**
- `entity_types`와 타입별 `relations`는 온톨로지의 타입·허용 관계 시드이며, 완성형 온톨로지 저장소나 런타임이 아니다.
- 온톨로지에는 관계 인스턴스뿐 아니라 조직 범위, 유효기간, 버전, 출처, 신뢰도, 승인 상태가 필요하다.
- 지식 그래프는 온톨로지를 따라 생성된 개체·관계 인스턴스이고, Graph RAG는 그것을 검색하는 방식이다.
- 공식 금액·물량은 온톨로지나 LLM이 계산하지 않고 버전 관리된 결정론적 계산 그래프가 산출한다.

```text
MDM·카탈로그·용어·Crosswalk·계보
  → 제조 경영 온톨로지(의미·관계·제약)
  → 지식 그래프(승인된 관계 인스턴스·근거)
  → Graph RAG(관계 기반 탐색)
  → 계산 그래프(승인 수식 계산)
  → 앱·시뮬레이션·경영 의사결정
```

### 6.2 우선 도메인

1. 조직/법인/사업부/원가센터
2. 계정과목/손익 항목
3. 제품/품목/단위
4. 고객/공급사
5. 프로젝트/설비/창고/로케이션

### 6.3 핵심 엔터티

```text
business_terms(term_id, canonical_name, definition, domain, owner, status)
term_synonyms(term_id, synonym, language, confidence, approved_by)
data_assets(asset_id, name, asset_type, system_id, location, owner, sensitivity)
data_asset_fields(field_id, asset_id, name, logical_type, term_id?, pii_classification)
data_quality_profiles(profile_id, asset_id, measured_at, completeness, freshness, validity, duplicate_rate)
lineage_edges(id, from_type, from_id, to_type, to_id, relation_type, confidence, evidence_ref)
data_contracts(contract_id, producer, consumer, version, schema_json, quality_rules_json, access_policy_json, status)
```

위 엔터티는 온톨로지 입력 자산이다. 온톨로지의 물리 스키마와 서비스 계약은 최신 로드맵의 G2-C에서 확정하며, 이 문서만 보고 별도 그래프 저장소를 중복 구축하지 않는다.

### 6.4 데이터 준비도 연계 규칙

상담사가 “필요하다”고 판단한 데이터는 카탈로그에서 다음 순서로 매칭한다.

```text
업무 용어
  → 동의어/유사어 확장
  → 데이터 카탈로그 후보 검색
  → MDM 기준 엔터티 연결 여부 확인
  → 품질/최신성/권한 확인
  → 데이터 요구사항 상태 갱신
```

LLM은 후보 검색·설명에만 사용한다. 최종 매칭 확정은 데이터 오너 또는 승인된 규칙이 담당한다.

---

## 7. 기능 4 — 외부 연계, MCP, Shadow Mode

### 7.1 커넥터 계층

```text
Connector Registry
  → 인증/권한/비밀관리
  → 시스템별 Query Contract
  → MCP/API/DB/File Adapter
  → 읽기 전용 조회
  → 정규화·캐시·품질 측정
  → 카탈로그·계보·Decision Ledger 기록
```

### 7.2 MCP 원칙

- MCP는 외부 시스템을 호출하는 프로토콜이며 MDM·카탈로그·권한 모델을 대체하지 않는다.
- 호출 가능한 도구는 시스템별로 명시적으로 등록한다.
- 기본은 최소 권한, 읽기 전용, 짧은 TTL 캐시다.
- 원천의 민감 데이터는 모델 프롬프트로 무제한 전달하지 않는다.
- 모든 조회에는 요청자, 목적, 데이터 범위, 시각, 결과 요약을 감사 로그로 남긴다.

#### 7.2.1 외부 협업 레거시 경계 확정

- 거래처·관세사·포워더·운송사는 고객사가 이미 운영하는 공급사·협력사·물류·통관 시스템에서 데이터를 입력한다고 전제한다. LS 환경의 LPL(LS Partner's Lounge)은 첫 Reference Profile이다.
- AI Factory Studio에는 외부 사용자 계정·파트너 조직·파트너용 앱 화면을 만들지 않는다.
- 고객사 기존 시스템은 외부 협업 System of Engagement로 유지하고 첫 연계는 읽기 전용 MCP/API/DB View/Export로 제한한다.
- 원천키·사건 ID·버전·발생/수정/조회 시각을 보존하고 Crosswalk로 내부 표준 의미와 연결한다.
- 목록·증분 사건은 단일 `fetch()`가 아니라 cursor 기반 `query/changes_since` 계약으로 조회한다.
- 정정·취소·재수신은 `(system_id, source_event_id, source_version)` 멱등키로 처리한다.
- 기존 시스템으로 쓰기는 별도 Action Contract, 사용자 확인, 감사, Shadow 검증 전에는 금지한다.
- 특정 고객사 시스템명과 물리 필드는 Adapter Profile로 격리하고 제품 코어에 하드코딩하지 않는다.

### 7.3 Shadow Mode

새로운 앱·규칙·예측 모델을 실제 데이터에 병렬 적용하지만 운영 시스템에는 쓰지 않는다.

| 단계 | 수행 내용 |
|---|---|
| 기준선 설정 | 현행 규칙·현행 결과·평가 기간을 확정 |
| 병렬 실행 | 같은 입력에 현행과 후보 시스템을 동시에 실행 |
| 비교 | KPI, 오류, 예외, 비용, 사용자 수정량 비교 |
| 검토 | 데이터 오너·업무 오너가 차이를 승인/반려 |
| 승격 | 승인된 범위에서만 제한적 운영 적용 |

### 7.4 Shadow Run 모델

```text
shadow_runs
  id, blueprint_id?, app_version, baseline_version,
  input_snapshot_ref, scenario_ref?, started_at, ended_at,
  status, metrics_json, variance_json, review_status
```

---

## 8. 기능 5 — 증빙을 동반한 SW 생성

### 8.1 생성 완료의 정의

코드 파일이 작성되었다고 완료가 아니다. 아래 증빙 묶음이 있어야 릴리스 후보가 된다.

- 요구사항, Blueprint, RFP, PRD, 아키텍처, WBS 간 추적성
- 화면·API·데이터 모델·권한 규칙 명세
- 핵심 업무 시나리오 기반 테스트
- 데이터 계약 및 입력 검증
- 빌드·정적 분석·보안·렌더·스모크 검사 결과
- 사용자 매뉴얼·운영 가이드·장애 대응 기준
- 사용 모델·비용·에이전트·프롬프트·근거 데이터 기록

### 8.2 릴리스 게이트

```text
초안 생성
  → 코드/문서/스키마 검사
  → 요구사항 추적성 검사
  → 핵심 업무 테스트
  → 권한/데이터 계약 검사
  → 사용자 수용검수
  → Shadow Mode(실운영 연계형 기능)
  → 릴리스 승인
```

### 8.3 실패 처리 원칙

- 재시도 횟수만 늘리지 않는다.
- 실패 원인을 `모델 품질`, `문맥 부족`, `출력 계약`, `외부 환경`, `테스트 하네스`, `요구사항 모호성`으로 분류한다.
- 3회 복구 실패 시 프로젝트를 조용히 종료하지 않는다. `TERMINAL_FAILURE` 상태, 실패 번들, 권장 후속 조치, 인간 승인 선택지를 제공한다.
- 동일 실패가 반복되면 스킬 진화 후보와 시스템 결함 후보를 분리한다.

---

## 9. 기능 6 — 부서 권한, 작업공간, 공유

### 9.1 권한 모델

권한은 UI 숨김이 아니라 백엔드 정책 집행이어야 한다.

```text
Tenant
  └ Entity/Legal Entity
      └ Department/Workspace
          └ Project/App/Simulation
              └ Data Asset / Field / Record Scope
```

### 9.2 최소 역할

| 역할 | 권한 |
|---|---|
| 현업 작성자 | 자신이 허용받은 부서 프로젝트·앱 사용 및 초안 작성 |
| 부서 관리자 | 부서 앱 공유, 작업 승인, 부서 데이터 접근 승인 요청 |
| 데이터 오너 | 데이터 정의·품질·계약·공유 범위 승인 |
| 경영진 | 전사 집계·시나리오 조회·의사결정 승인 |
| 플랫폼 관리자 | 템플릿·커넥터·정책·모델·감사 관리 |

### 9.3 필수 정책

- 모든 데이터 조회는 주체, 목적, 범위, 권한 근거를 남긴다.
- 모델 문맥 구성도 같은 권한 필터를 통과해야 한다.
- 부서 앱을 전사 앱으로 승격할 때 데이터 계약·보안·품질·소유자 승인을 요구한다.

---

## 10. 기능 7 — 비용·품질 최적화 엔진

### 10.1 측정 단위

핵심 KPI는 다음과 같다.

```text
승인된 결과물 1건당 비용
= LLM 비용 + 재작업 비용 + 검토 시간 비용 + 실패/지연 비용
```

### 10.2 모델 라우팅 정책

| 작업 | 기본 전략 |
|---|---|
| 분류·추출·요약·질문 생성 | 저비용 모델 + 구조화 JSON |
| RFP/PRD 초안 | 중간 비용 모델 + 템플릿/지식 참조 |
| 아키텍처·복잡 코드·최종 심사 | 고성능 모델 + 좁은 문맥 + 검증 |
| 숫자 계산·스키마·권한·품질 | LLM 대신 규칙/테스트 엔진 |
| 실패 재작업 | 원인 분석 후 문맥·작업 분할·출력 계약부터 수정 |

### 10.3 텔레메트리 필수 항목

```text
llm_calls
  provider, model, tier, task_type, prompt_tokens, output_tokens,
  latency_ms, cost_estimate, fallback_chain, result_status, project_id

quality_outcomes
  artifact_type, gate_name, pass_fail, retry_count,
  root_cause_classification, human_acceptance, rework_reason
```

### 10.4 비용 절감 규칙

- 전체 파일을 매번 프롬프트에 넣지 않고 소유 파일·변경 파일·서명 요약을 선택한다.
- 대화는 전체 로그 대신 승인된 Blueprint 요약과 최근 의사결정만 재사용한다.
- 카탈로그·MDM·상태 조회는 LLM이 아니라 API/SQL로 수행한다.
- 동일 입력·동일 버전의 분석은 캐시한다.
- 병렬 스웜은 재작업 또는 고위험 작업에만 제한적으로 사용한다.

---

## 11. 기능 8 — 경영 시뮬레이션과 디지털트윈

### 11.1 초기 파일럿: 경영계획

첫 번째 디지털트윈 파일럿은 **경영계획–실적–시나리오 관리**로 한다. 이유는 조직·계정·제품·실적·계획·승인·시뮬레이션을 동시에 검증할 수 있기 때문이다.

### 11.2 최소 데이터셋

| 분류 | 예시 |
|---|---|
| 기준정보 | 법인, 조직, 사업부, 원가센터, 계정, 제품, 고객, 프로젝트 |
| 과거 실적 | 매출, 매입, 제조원가, 판관비, 재고, 인건비, 투자, 손익 |
| 계획 동인 | 판매량, 단가, 원재료 가격, 생산능력, 인원, 임금, 전기료 |
| 외부 지표 | 환율, 금리, 물가, 산업 성장률, 원자재 지수 |
| 업무 흐름 | 부서 입력, 검증, 조정, 승인, 실적 비교, 차이 분석 |

### 11.3 시뮬레이션 원칙

- 실제(Actual), 계획(Plan), 예측(Forecast), 시나리오(Scenario)를 절대 섞지 않는다.
- 기준 시나리오는 버전으로 고정한다.
- 모든 결과는 입력 스냅샷, 모델/공식 버전, 가정, 실행 시각을 기록한다.
- LLM은 가정 후보·결과 설명·이상 탐지 보조 역할만 수행한다.
- 수치 계산은 재현 가능한 함수·규칙·제약조건 모델로 구현한다.

### 11.4 초기 가치사슬 모델

```text
수주/수요
  → 판매계획
  → 생산계획
  → 구매/재고
  → 생산/품질
  → 물류/납기
  → 매출/원가
  → 손익/현금흐름
```

### 11.5 시나리오 모델

```text
scenarios
  id, name, scope, baseline_version, status, owner

scenario_assumptions
  id, scenario_id, driver_term_id, target_scope,
  operator, value, unit, effective_period, rationale

simulation_runs
  id, scenario_id, input_snapshot_ref, engine_version,
  status, started_at, completed_at, output_snapshot_ref, metrics_json
```

---

## 12. 기능 9 — 외부환경 인텔리전스와 검증 데이터 기반 시뮬레이션

### 12.1 목표와 기본 입장

경영계획과 디지털트윈에서 가장 불확실하면서 영향이 큰 입력은 환율, 금리, 원자재, 에너지, 수요, 물류, 규제 같은 외부환경 요인이다. 이 기능의 목표는 인터넷에서 가장 빠른 정보를 수집하는 것이 아니라, **출처·발표 시점·수정 이력·검증 상태가 명확한 외부 데이터를 회사의 계획과 시나리오에 안전하게 연결**하는 것이다.

따라서 1~2일의 지연이 있더라도 검증·확정된 데이터를 기본 시뮬레이션에 우선 사용한다. 실시간 시장 정보, 뉴스, 웹 크롤링은 경보와 위험 시나리오 후보를 만드는 보조 정보이며, 검증 없이 기준 계획이나 공식 수치를 자동 변경해서는 안 된다.

### 12.2 데이터 등급과 사용 정책

| 등급 | 데이터 예 | 허용 용도 | 금지 용도 |
|---|---|---|---|
| Gold: 검증·확정 | 공식 통계, 확정 단가, 승인된 사내 실적, 규제기관 고지 | 기준 계획, 공식 시뮬레이션, 경영 보고 | 없음. 단, 권한·기준일은 적용 |
| Silver: 잠정·전망 | 잠정 통계, 시장 전망, 공급사 전망, 허가된 유료 데이터 | 전망/공격/위험 시나리오, 검토 자료 | 실제값 또는 확정 계획으로 표시 |
| Bronze: 사건 후보 | 기사, RSS, 공시 알림, 웹 수집, 비정형 보고서 | 사건 감지, 검토 요청, 근거 탐색 | 자동 수치 변경, 자동 의사결정 |

모든 화면과 API는 실제값(Actual), 외부 전망(Forecast), 사내 경영 가정(Plan Assumption), 의도적 시나리오(Scenario)를 구분해 표시한다.

### 12.3 물리 저장 위치와 기존 시스템 경계

외부정보를 기존 LangGraph 체크포인트 또는 RAG에 무분별하게 넣지 않는다.

```text
data/
  pipeline_state.db                 # 기존 LangGraph 체크포인트 전용. 외부정보 저장 금지
  chroma_db/                        # 기존 RAG. 승인된 해설/요약/근거 탐색에만 사용
  external_intelligence.db          # 신규: 외부지표·관측값·전망·사건·수집 이력
  external_raw/                     # 신규: API 응답, CSV, HTML, PDF 원문과 메타데이터
```

초기에는 별도 SQLite 저장소로 시작할 수 있으나, 시계열·다중 사용자·감사 범위가 커지면 PostgreSQL 기반 `external_intelligence` 스키마로 이전한다. 시간별 관측량이 커질 경우 시계열 확장 저장소를 별도 검토한다.

MDM에는 국가, 통화, 품목, 산업, 지역, 지표 유형 같은 **기준 정의**만 둔다. 날짜별 환율·가격·통계값은 외부 인텔리전스 저장소에 둔다. 데이터 카탈로그는 해당 데이터가 어디에서 왔고, 누가 책임지고, 얼마나 신뢰할 수 있는지 설명한다.

### 12.4 원천 등록부(Source Registry)

범용 웹 크롤러를 만들지 않는다. 승인된 원천만 등록하고 수집한다. 원천 선택 우선순위는 다음과 같다.

```text
공식 API
  → 공식 CSV/엑셀 다운로드
  → RSS/공시 피드
  → 계약된 데이터 제공자 API
  → 사용자가 등록한 보고서/PDF
  → 이용약관상 허용된 웹페이지 HTML 수집
```

```text
external_sources
  id, name, source_type(API/RSS/CSV/WEB/REPORT), base_url,
  license_type, allowed_usage, collection_method,
  refresh_frequency, rate_limit, owner_department,
  trust_grade, enabled, canonical_source_priority
```

각 외부지표는 `canonical_source_id`, `backup_source_id`, `acceptable_latency`, `verification_policy`를 가져야 한다. 유료 데이터는 공식·저비용 대체 원천이 없고, 의사결정 품질 개선이 구독료보다 크며, 내부 분석·재사용 라이선스가 명확할 때만 보조 원천으로 도입한다.

### 12.5 핵심 데이터 모델

```text
external_indicators
  id, canonical_term_id, code, name, category,
  geography_code, unit, frequency, default_source_id,
  canonical_source_id, backup_source_id, acceptable_latency,
  verification_policy, status

external_observations
  id, indicator_id, observed_at, published_at, ingested_at,
  value, unit, vintage, source_id, source_record_ref,
  quality_status(RAW/VALIDATED/REJECTED/SUPERSEDED), snapshot_hash

external_forecasts
  id, indicator_id, provider_name, forecast_period, published_at,
  vintage, value, lower_bound, upper_bound, confidence_level,
  methodology_summary, source_record_ref, quality_status

external_events
  id, event_type(REGULATION/WEATHER/SUPPLY_CHAIN/MARKET/POLITICAL),
  title, occurred_at, detected_at, geography_scope, industry_scope,
  severity, confidence, status(CANDIDATE/REVIEWED/APPROVED/DISMISSED),
  summary, owner_department, created_by

external_event_evidence
  id, event_id, source_id, source_url, raw_document_ref,
  extracted_excerpt, published_at, evidence_hash

driver_mappings
  id, external_indicator_id, internal_metric_id, target_scope,
  mapping_type(FORMULA/ELASTICITY/RULE/MODEL), formula_definition,
  lag_period, effective_from, effective_to, evidence_ref,
  owner_department, approval_status, version
```

`vintage`는 필수다. 나중에 수정된 지표가 있어도, 특정 경영계획과 시뮬레이션이 당시 어떤 발표값을 사용했는지 재현할 수 있어야 한다.

### 12.6 수집·검증·공개 처리 흐름

외부 수집은 SSE 리스너나 슈퍼바이저 데몬에 넣지 않고 별도 워커로 구현한다.

```text
Scheduler
  → Collector(API/RSS/CSV/허용 WEB)
  → Raw Store 원문 보관
  → Normalizer 표준화
  → Validator(단위/날짜/범위/중복/수정값 검사)
  → external_* 테이블 저장
  → 데이터 오너 검토 또는 자동 검증
  → Catalog Publisher 공개
  → Decision Ledger 기록
  → 영향 매핑 대상에 재계산 필요 알림
```

권장 코드 경계는 다음과 같다.

```text
core/external_intelligence/
  source_registry.py
  collector.py
  normalizer.py
  validator.py
  event_extractor.py
  publisher.py
  scheduler.py

api/routes/external_intelligence_control.py
frontend/src/components/ExternalIntelligencePanel.tsx
frontend/src/components/ScenarioWorkbenchPanel.tsx
```

LLM은 비정형 문서에서 사건 후보를 추출하고 요약할 수 있다. 그러나 후보는 반드시 `CANDIDATE` 상태로 저장하며, 담당자 검토 없이 공식 시뮬레이션 입력으로 사용하지 않는다.

### 12.7 내부 KPI와의 영향 매핑

외부지표를 손익에 직접 연결하지 않는다. 중간의 업무·계산 경로를 명시적으로 등록한다.

```text
환율 상승
  → 수입 원자재 매입단가 상승
  → 제품별 제조원가 상승
  → 매출총이익률 하락
  → 운전자본·현금흐름 영향
```

예시 매핑:

```text
외부지표: 전기요금지수
내부지표: 제조경비-전력비
적용범위: A공장
관계식: 전력비 = 기준 전력사용량 × 전기단가
영향시차: 당월
근거: 전력 계약·최근 12개월 실적
승인자: 생산관리팀 + 재무팀
```

Driver Mapping은 업무 오너와 데이터 오너의 승인, 근거, 버전, 유효기간을 갖는다. 이 연결은 Graph RAG의 그래프 간선 후보가 될 수 있지만, 그래프 자체가 공식 계산 규칙을 대체해서는 안 된다.

### 12.8 시나리오·시뮬레이션 연결 규칙

```text
Gold 관측값/승인된 외부 사건
  → 외부 데이터 스냅샷 고정
  → 승인된 Driver Mapping 적용
  → 사용자 시나리오 가정 추가
  → 결정론적 계산 엔진 실행
  → 손익·원가·재고·납기·현금흐름 결과
  → Decision Ledger 기록
```

모든 `simulation_runs`는 최소한 다음 참조를 보유한다.

```text
internal_data_snapshot_ref
external_data_snapshot_ref
external_event_version_refs
driver_mapping_version_refs
engine_version
scenario_assumption_refs
executed_by / approved_by
```

기준 시나리오는 Gold 데이터와 승인된 사내 계획 가정을 사용한다. Silver 데이터는 전망·공격·위험 시나리오에만 사용한다. Bronze 사건은 검토 요청 또는 위험 시나리오 후보일 뿐 자동 반영하지 않는다.

### 12.9 화면과 사용자 흐름

Private AI Cockpit의 공통 관리 진입에 다음 두 화면을 추가한다.

```text
External Intelligence Center
  - 원천 관리
  - 외부지표 카탈로그
  - 수집 현황·오류·품질
  - 실제값/전망값 시계열 비교
  - 사건 후보 검토·승인
  - 내부 KPI 영향 매핑
  - 라이선스·소유자·갱신주기

Scenario Workbench
  - 기준 시나리오 선택
  - 외부/내부 변수 조절
  - 영향 범위 선택
  - 결과·민감도·범위 비교
  - 승인·저장·공유
  - Shadow Mode 실행
```

### 12.10 경영계획 파일럿의 첫 지표

처음부터 모든 지표를 수집하지 않는다. 다음 여섯 가지를 기준으로 시작한다.

1. 환율
2. 주요 원자재 가격
3. 전기료/에너지 비용
4. 금리
5. 산업 수요지수 또는 판매량 선행지표
6. 임금 상승률

초기에는 공식 API·공식 CSV·수동 파일 등록을 지원한다. 웹 수집과 뉴스 사건 분석은 3단계 이후에 추가한다.

---

## 13. 기능 10 — 전역 자비스형 슈퍼바이저

### 13.1 현재 슈퍼바이저와의 차이

현재 프로젝트 단위 HOTL/감시 데몬은 전역 자비스가 아니다. 전역 슈퍼바이저는 프로젝트 ID를 요구하지 않아도 사용자의 권한 범위 내에서 다음 질문에 답해야 한다.

- 지금 어떤 프로젝트가 멈췄는가?
- 경영계획 준비에 부족한 데이터는 무엇인가?
- 이번 주 비용이 많이 든 에이전트 작업은 무엇인가?
- 기준정보 변경이 어느 앱에 영향을 주는가?
- 특정 시나리오의 손익 하락 원인은 무엇인가?

### 13.2 구성

```text
Global Supervisor
  ├─ Intent Router: 질의 범위 판별
  ├─ Permission Filter: 권한 범위 강제
  ├─ Enterprise Context: Blueprint/Decision/Data Catalog/Telemetry 조회
  ├─ Action Planner: 조회·승인 요청·프로젝트 개입 계획
  ├─ Tool Executor: 읽기 도구 우선 호출
  └─ Response Composer: 근거·불확실성·다음 조치 제시
```

### 13.3 안전 원칙

- 실행보다 조회·설명·권고를 우선한다.
- 중단·재개·릴리스·외부 쓰기 같은 행위는 명시 승인과 감사 로그가 필요하다.
- 모르는 데이터는 추정으로 채우지 않고 “연결/검증 필요”로 표시한다.
- 응답에는 가능한 경우 근거 데이터, 시각, 신뢰도, 권한상 제외된 범위를 표시한다.

---

## 14. 단계별 수행계획

### P0. 생성 공장 안정화 ✅ **완료 (2026-07-28)** — §18-2 의 M0 선행 게이트 해제

**목표**: 기존 LangGraph 파이프라인이 성공·대기·실패·복구 상태를 신뢰성 있게 표현하도록 한다.

| 작업 | 완료 기준 | 실제 구현 |
|---|---|---|
| 실패 계약 | `SPRINT_FAILED`, `NODE_FAILED`, `TERMINAL_FAILURE` 이벤트와 UI 표시 | ✅ 단일 `TERMINAL_FAILURE` 대신 **원인별 8값**으로 세분화: `terminal_status`(`state_models.py:157`) = `FAILED_BUILD`/`FAILED_REVIEW`/`FAILED_GENERATION_CONTRACT`/`REJECTED_ACCEPTANCE`/`SUSPENDED_QUOTA`/`SUSPENDED_PROVIDER`/`CANCELLED`/`COMPLETED` + `terminal_reason` + `SPRINT_FAILED` 방송(`async_orchestrator.py:181`). **`END` 는 성공이 아니다**를 구조로 강제 |
| 복구 정책 | 3회 실패 뒤 실패 번들·후속 선택지·안전 종료 | ✅ `failure_bundle_path`, `_recovery_swarm_size`·`_targeted_repair_instruction`(`nodes/execution.py`). 보류(`SUSPENDED_*`)는 WBS `BLOCKED` 로 분리해 재개 가능 |
| 공급자/문맥 | 모델 선택·컨텍스트 한도·타임아웃·폴백 기록 | ✅ `MODEL_CONTEXT_LIMITS`/`MODEL_OUTPUT_LIMITS`, `LLM_TOTAL_DEADLINE_SEC` 하드 상한, 모델 쿨다운·티어 강등, `attempts`(폴백 체인) 기록 |
| 테스트 하네스 | 실제 생성물 결함과 하네스 거짓 실패 분리 | ✅ `FAILED_GENERATION_CONTRACT`(출력 절단·구조화 실패) = "코드 결함 아님"으로 분류 |
| 비용 관측 | 호출 모델·비용·지연·성공 여부 수집 | ✅ **2026-07-28 완료** — `core/llm_cost.py` 신설. §10.3 `llm_calls` 표준 필드(`project_id`·`owner_dept_id`·`provider`·`cost_estimate_usd`·`cost_basis`)를 게이트웨이가 기록하고, 구 로그는 읽는 시점에 **소급 산정**. ⚠️ 단가 미등록 유료 모델은 **0 이 아니라 `unpriced`** 로 남겨 총액을 하한으로 표시한다(§16: 근거 없는 수치 금지) |

> **비용 관측 실측 (2026-07-28)** — 실제 로그 972건 전량 소급 산정:
> 총 **$4.556**(971/972 산정, 미산정 1건은 퇴역 모델) · 유료 720건 / 무료티어 144건 / 캐시적중 107건 ·
> 제공사 분포 **openrouter 734건(전액) · gemini 130건($0) · groq 1건**.
> 단가 출처는 OpenRouter 공식 모델 API(확인일 2026-07-28)이며, `google/gemini-2.5-flash` 출력
> $2.50/1M 이 `config.py:67` 의 기존 실측 기록과 일치해 교차검증됐다.
> ★ 시사점: **유료 백스톱이 호출의 76%** 를 처리했다. 무료 Pro 쿼터 소진 시 유료로 착지하는
> 구조(`config.py:76` 주석)가 비용에서 실제로 확인된다 — §10.2 모델 라우팅 정책의 1차 근거.

### M0. 업무·데이터 설계 상담과 Blueprint

**목표**: 신규 사용자가 10분 이내에 실행 가능한 업무 청사진을 얻는다.

| 작업 묶음 | 주요 산출물 |
|---|---|
| 플레이북 | 경영계획, 구매, 생산, 품질, 물류, 판매, 회계의 표준 질문·데이터 요구사항 |
| 상담 API/UI | 전역 상담 패널, 선택형 질문, 상담 세션 저장 |
| Blueprint | 구조화 모델, 승인, 프로젝트·RFP 초안 부트스트랩 |
| 준비도 | 규칙 기반 점수, 결손 데이터 태스크 생성 |

### M1. 데이터 기반과 거버넌스

**목표**: 필요한 데이터가 어디에 있고 누가 책임지며 사용할 수 있는지 판단한다.

| 작업 묶음 | 주요 산출물 |
|---|---|
| MDM 확장 | 우선 도메인 기준정보, 별칭, 중복 후보, 승인 |
| 카탈로그 | 데이터 자산·필드·소유자·민감도·갱신주기 |
| 용어사전 | 동의어·유사어·계산 정의·MDM 연결 |
| 품질/계보 | 프로파일링, 원천→앱→보고서 영향 관계 |
| 계약 | 스키마·품질·접근·버전 계약 |
| 외부 인텔리전스 기반 | 승인 원천 등록부, 첫 외부지표 6종, 실제값/전망/사건 분리 |

### M2. 권한과 안전한 연계

**목표**: 부서별 데이터와 외부 시스템을 안전하게 읽고 검증한다.

| 작업 묶음 | 주요 산출물 |
|---|---|
| IAM/RBAC | 테넌트·부서·워크스페이스·데이터 범위 권한 |
| 커넥터 | 파일/DB/API/MCP 등록, 비밀 관리, Query Contract |
| 감사 | 조회·모델 문맥·승인·외부 호출 감사 로그 |
| Shadow Mode | 기준선·병렬 실행·비교·승격 승인 |

### M3. 증빙형 부서 업무 앱

**목표**: 현업이 만든 앱을 검증·공유·운영 가능한 단위로 만든다.

| 작업 묶음 | 주요 산출물 |
|---|---|
| 생성 계약 | 기능·화면·API·데이터·권한·테스트 증빙 묶음 |
| 부서 워크스페이스 | 앱 공유·복제·승격·승인 |
| 운영 준비 | 릴리스 체크리스트, 매뉴얼, 모니터링, 롤백 |
| 영향 분석 | 기준/계약 변경 시 영향 앱·보고서·시뮬레이션 표시 |

### M4. 경영계획 디지털트윈 파일럿

**목표**: 실제/계획/예측/시나리오를 구분한 경영계획 모델을 구축한다.

| 작업 묶음 | 주요 산출물 |
|---|---|
| 데이터 모델 | 조직·계정·제품·실적·계획·동인·시나리오 |
| 외부환경 입력 | Gold 외부 데이터 스냅샷, 승인된 Driver Mapping, 외부 사건 버전 |
| 계획 앱 | 부서 입력·검증·조정·승인·차이 분석 |
| 계산 엔진 | 손익·원가·현금흐름 산식, 제약조건, 버전 |
| 시나리오 | 기본/공격/위험 시나리오와 변화 요인 비교 |
| 검증 | 과거 기간 Backtest, Shadow Mode, 사용자 승인 |

### M5. 전사 자비스와 개인화

**목표**: 권한 범위 안에서 전사 상태·데이터·의사결정을 연결하는 보좌 에이전트를 제공한다.

---

## 15. 우선 구현 백로그

### 즉시 착수 가능

1. ~~상담 플레이북 스키마와 경영계획 도메인 플레이북 작성~~ ✅ **완료 (2026-07-28)** — `core/advisor_playbook.py`(Pydantic 스키마 + 레지스트리 + **준비도 산정**) · `playbooks/business_planning.json`(질문 6 · 데이터 요구 21) · 테스트 34건.
   플레이북은 **저작 설정**이라 DB 가 아니라 `playbooks/*.json` 에 둔다 — `templates/<id>.json`·`skills/*.md` 와 같은 규약(§18-4 조사 결과). 상담 세션·Blueprint 는 사용자 데이터이므로 별도 저장소(백로그 2).
   · 준비도(§4.3 F-DA-05)는 **LLM 0콜 결정론**. 5축 25/25/25/15/10 배점, 상태 계수(보유 1.0 / 검증필요 0.5 / 부족 0.0), 필수:권장 = 2:1 가중, optional 은 점수 제외·결손엔 표시.
   · ⚠️ **모르는 상태를 보유로 치지 않고**, 플레이북이 정의하지 않은 축은 **만점 처리하지 않는다**(`measurable_max` 로 분리) — 낙관 편향이 착수 판단을 망친다.
   · 저작 불변식 하나를 검증기로 잠갔다: **조건부 요구사항은 `required` 일 수 없다.** 초안이 이를 위반해 추천안만 고른 사용자에게 21건 중 7건만 활성화됐다(준비도가 실제보다 높게 나오고 결손 안내도 안 뜸). 지금은 필수 전량이 기본 활성이다.
   · **§12 정렬 완료** — 외부지표 6종(§12.10)을 `requirement_type: external` 로 반영하고 등급·`acceptable_latency`·`vintage_required`·권장 원천을 함께 담았다. M1 원천 등록부는 이 목록을 입력으로 쓴다(스키마 자리를 미리 잡아 마이그레이션 회피).
   · 선택형 질문은 `nodes/clarification.py` 가 만드는 형태와 **동일 계약**이라 프론트 `HOTLInput.tsx` 를 재사용할 수 있다(백로그 3 규모 축소).
   · 실측: 경영관리팀·부서단위·월1년·중앙입력·ERP실적 시나리오 → **준비도 64.2점**, 차단 결손 3건(환율·원자재·전기료)이 담당 부서·영향·다음 조치와 함께 산출.
2. ~~`SolutionBlueprint` Pydantic 모델과 저장소/API 설계~~ ✅ **완료 (2026-07-28)** — `core/advisor_blueprint.py`(§5.1 7영역 모델 + 결정론 조립) · `core/advisor_store.py`(`data/advisor.db`) · `api/routes/advisor_control.py`(라우트 10) · 테스트 52건.
   · ★ **Blueprint 초안을 LLM 이 아니라 플레이북에서 결정론적으로 조립한다**(LLM 0콜). 근거: 바이블 §9.3(AI 에게 진실을 맡기지 말 것) · §0-3(숫자·판정은 결정론) · 같은 답변이면 같은 Blueprint 라야 "왜 이렇게 나왔나"를 설명할 수 있다. LLM 보강은 나중에 `origin="ai"` 로 구분해 얹는다.
   · **제외 범위는 추론이 아니라 사실** — 사용자가 고르지 않은 선택지가 곧 제외 범위다(§5.1 필수 필드).
   · **출처 표시**(§5.2·바이블 §9.3): `origin`(rule|user|ai) + `confirmed` 2필드. 승인은 `confirmed` 만 켜고 **`origin` 은 지우지 않는다** — AI 가 제안했던 것은 승인 뒤에도 그렇고, 지우면 결정의 계보가 끊긴다(§1.3).
   · **바이블 §7.1 정렬**: 요구사항마다 `data_kind`(actual/plan/forecast/scenario/reference/event). 외부지표는 등급이 성격을 정한다 — Gold=actual, Silver=forecast, Bronze=event.
   · 데이터 요구사항을 **행으로도** 저장한다(`blueprint_data_requirements`) — "어느 부서가 어떤 데이터를 몇 건 못 갖췄나"를 질의해야 하고 JSON 안에 있는 것은 검색되지 않는다(§4.4 데이터 보드, M1 카탈로그 매칭 입력).
   · **권한을 처음부터 부서 스코프로 걸었다.** 나중에 얹는 비용이 이 프로젝트에서 반복적으로 컸다(Phase 4 는 21곳에 단언을 뒤늦게 주입, Phase 5 는 이미 전역 유출 상태였다). ⚠️ 상담은 이 기능과 함께 새로 생기는 데이터라 지킬 레거시가 없으므로, 프로젝트 목록과 달리 **부서 미지정(개인) 상담은 본인만**(fail-closed).
   · **차단이 아니라 가시화**: 필수 데이터 결손 상태로도 승인은 되지만 `approved_with_blocking_gaps` 로 무엇을 안고 승인했는지 남는다. 막으면 우회한다.
   · ⚠️ ~~명세서 §4.5 의 `tenant_id` 는 **넣지 않았다**~~ → **정정 (2026-07-28, ECM-lite)**: 최상단 선행 규칙이 상담사를 명시적 적용 대상으로 지목하므로 `tenant_id`·`enterprise_scope_id`·`entity_mode` 3키를 추가했다. "쓰지 않는 컬럼은 오해를 만든다"는 판단은 SSOT 요구가 없을 때의 것이었고, 지금은 근거가 무효다. 상세는 [`design_enterprise_context_master.md`](design_enterprise_context_master.md) §11 E1 의 "ECM-lite 선점 완료".
   · 미구현(백로그 4 = M0-d): `bootstrap-project`, `create-data-tasks`.
3. 전역 상담 패널 UI와 선택형 질문 컴포넌트
4. ~~상담 결과를 기존 프로젝트 생성·RFP 입력으로 연결~~ ✅ **완료 (2026-07-28)** — `POST /advisor/blueprints/{id}/bootstrap-project` · `POST .../create-data-tasks` · 테스트 19건.
   · **승인된 Blueprint 만** 프로젝트가 된다(§4.2-7). 초안으로 만들 수 있으면 승인 게이트가 장식이 된다.
   · **Clarification 을 우회하지 않는다**(§18-6) — Blueprint 를 `initial_idea` 의 상위 입력값으로 주입할 뿐 요구 확인 인터뷰는 그대로 돈다. 상담은 "무엇을 만들지", Clarification 은 "어떻게 만들지"의 모호점 제거로 **다른 게이트**다. 사용자의 원래 말이 앞, Blueprint 요약이 뒤 — 순서를 바꾸면 LLM 이 요약을 사용자 발화로 오해한다.
   · 프롬프트에는 **요약만** 넣는다(§10.4 / ECM §5.2-5). 목적·범위·**제외 범위(만들지 말 것)**·결정·준비도·필수/미확보 데이터·권장 순서. 전문 대비 1/3 미만임을 테스트로 고정.
   · 프로젝트는 Blueprint 의 **소유권·ECM 문맥을 물려받는다**(요청 헤더가 아니라). 헤더를 쓰면 승인된 Blueprint 와 다른 문맥의 프로젝트가 생겨 추적이 끊긴다(ECM §10.2).
   · `project_meta.json` + `ProjectState` 에 `blueprint_id` 추적 링크 추가(§18-7). `_ACCUMULATED_FIELDS` 에 편입 — 스프린트 사이에 유실되면 다시 채워줄 곳이 없다.
   · `POST /projects` 와 부트스트랩이 **`provision_project()` 단일 경로**를 공유한다. 복사하면 템플릿 검증·소유권·문맥 중 하나가 한쪽에만 반영되어 조용히 어긋난다(이 프로젝트에서 세 번 반복된 결함 유형).
   · ⚠️ `create-data-tasks` 는 **기획 완료 후에만** 동작한다(WBS 없으면 409). `initialize_wbs` 가 파일을 통째로 다시 쓰므로 기획 전에 넣은 태스크는 PMO 가 WBS 를 만드는 순간 사라진다 — 조용히 만들어 두면 지워진 줄도 모른다. 근본 경로는 `initial_idea` 의 Blueprint 요약(필수·미확보 데이터 포함)을 PMO 가 읽고 처음부터 포함하는 것이고, 이 엔드포인트는 기획이 놓친 것을 사람이 보강하는 보조 경로다.
   · 태스크 목표에 영향·조치·필요 단위·최신성·**데이터 구분**(§7.1)을 함께 넣는다 — 태스크만 있고 왜/무엇을 모르면 방치된다.
5. ~~`DecisionLedgerEvent` 최소 모델과 Blueprint 승인 이력 기록~~ ✅ **완료 (2026-07-28)** — `core/decision_ledger.py` · `api/routes/ledger_control.py`(조회 전용) · 테스트 30건.
   · **저장소는 별도 `data/decision_ledger.db`** — Ledger 는 Blueprint·프로젝트·릴리스·시나리오·조직문맥을 모두 참조하는 전사 자산이라 `advisor.db` 안에 두면 상담 전용처럼 보인다. ECM §6.2 가 문맥 변경·프로필 변경·복제·권한부여·외부 연결·시나리오 실행까지 대상으로 지정했으므로 이벤트 유형에 그 5종을 함께 등록했다.
   · **불변성을 코드로 강제한다** — `update`/`delete` 메서드를 **아예 만들지 않았고** 그 사실을 테스트로 잠갔다(있으면 누군가 쓴다). 정정은 `CORRECTION` + `parent_event_id` 로 잇고, `parent_event_id` 없는 `CORRECTION` 은 거부한다. 틀린 기록도 "그때 그렇게 판단했다"는 사실이므로 지우면 이력이 거짓이 된다.
   · **쓰기 API 를 만들지 않았다** — 외부에서 임의 기록이 가능하면 "이 결정이 실제로 일어났다"는 증거가 무의미해진다. 기록은 결정이 실제로 일어나는 코드 경로에서만 이뤄진다(테스트로 쓰기 경로 부재를 확인).
   · ★ **승인 기록은 라우트가 아니라 저장소 계층(`set_blueprint_decision`)에서** 한다. 승인 경로가 늘어나도(배치 승인·경영진 일괄 승인) 기록이 자동으로 따라온다 — 라우트에 두면 새 경로가 기록을 빠뜨리고, 그게 이 프로젝트에서 반복된 배선 누락 유형이다.
   · ★ **기록 실패를 삼키지 않는다.** 텔레메트리는 부가 기능이라 실패를 삼켰지만 Ledger 는 "왜 이 결정을 했는가"의 유일한 근거다. 승인 이력 없는 승인은 §1.3 을 정면으로 어긴다.
   · **무엇을 알면서 승인했는지**를 근거로 남긴다 — 준비도 점수·미확보 필수 데이터 목록·공식 미기재 지표 수. 근거(`evidence_refs`)가 비면 `is_substantiated=False` 로 읽혀 §5.2 "근거 없는 수치는 검증되지 않은 추정" 판정을 조회부가 할 수 있다.
   · **해시 체인**(명세서에 없으나 추가) — `prev_hash + 정규화 payload` 의 SHA-256 을 이어 변조를 **탐지**한다. ⚠️ **한계를 API 응답에 명시**했다: DB 직접 조작을 *막지는* 못하고 불일치 탐지만 가능하다. '위조 불가'로 오해하면 안 된다. 진짜 위조 방지는 외부 append-only 저장소나 서명이 필요하고 이 단계 범위가 아니다.
   · 조회는 문맥(테넌트·`entity_mode`)과 부서로 격리한다. 범위 없는 이벤트는 무제한 권한자 또는 본인(행위자)만 본다(fail-closed) — 감사 이력은 결정 사유·승인자를 담는다. `/verify` 는 체인이 테넌트를 가로질러 하나이므로 전사 열람 권한자 전용.
   · 기록 지점: `BLUEPRINT_APPROVED`/`BLUEPRINT_REJECTED`(저장소), `PROJECT_BOOTSTRAPPED`·`DATA_REQUIREMENT_ACCEPTED`(M0-d 경로). 나머지 유형(`MASTER_VALUE_CHANGED`·`RELEASE_ACCEPTED`·`SCENARIO_EXECUTED`·`WBS_APPROVED` 등)은 **유형만 등록**돼 있고 실제 기록 지점 연결은 해당 기능 구현 시 붙인다.
   · 실측: 준비도 38.3점·미확보 필수 6건 상태로 승인 → 그 사실이 근거와 함께 이력에 남고, DB 에서 근거를 "준비도 100점"으로 위조하자 체인 검증이 즉시 불일치(seq 1)를 지목.
6. ~~텔레메트리에 작업 유형·모델·비용·성공 여부 표준 필드 추가~~ ✅ **완료 (2026-07-28)** — 위 P0 표 참조. 남은 항목은 §10.3 `quality_outcomes`(게이트별 pass/fail·재시도·근본원인 분류·인간 수용) 로, 이건 §8.3 실패 원인 분류와 함께 별도 작업이다
7. 외부 인텔리전스의 원천 등록부·지표 마스터·관측값 스키마 상세 설계

### 선행 설계가 필요한 작업

1. 테넌트/부서/데이터 범위 RBAC
2. 데이터 카탈로그와 품질·계보의 저장소 선택
3. 외부 비밀 관리와 커넥터 인증 모델
4. Shadow Mode의 기준선·스냅샷·비교 지표
5. 시뮬레이션 엔진의 산식·단위·기간·재현성 규격

---

## 16. 품질·보안·운영의 비협상 조건

- 실제·계획·예측·시나리오 데이터를 혼합 표기하지 않는다.
- 민감 데이터와 권한 밖 데이터는 LLM 문맥에 넣지 않는다.
- 외부 시스템 쓰기, 릴리스, 영향이 큰 승인에는 사용자 확인과 감사 로그를 강제한다.
- 데이터 카탈로그와 MDM을 제조 경영 온톨로지나 Graph RAG로 대체하지 않는다. 온톨로지는 의미·관계 계층이고 Graph RAG는 그 위에서 근거 탐색을 강화하는 검색 방식이다.
- MCP를 데이터 모델 또는 권한 모델로 오해하지 않는다. MCP는 연결 방식이다.
- 생성 앱의 Preview를 운영 환경으로 오해하지 않는다.
- 디지털트윈 수치는 재현 가능해야 하며, 입력 스냅샷·엔진 버전·가정·출력을 함께 보존해야 한다.
- 비용 절감 때문에 최종 품질 게이트를 제거하지 않는다. 대신 저비용 단계와 고비용 단계를 분리한다.

---

## 17. 첫 파일럿: 경영계획–실적–시나리오 관리

### 17.1 사용자 목표

경영관리팀이 다음을 수행한다.

- 내년도 사업계획 작성과 부서별 승인
- 월별 실적과 계획 차이 분석
- 매출, 원가, 인력, 전기료, 환율, 원자재 가격 변화의 손익 영향 분석
- 경영진의 기본/공격/위험 시나리오 비교

### 17.2 최소 기능 범위

1. 조직·계정·제품·원가센터 기준정보 등록
2. 최근 3년 손익·매출·원가 실적 연결 또는 파일 등록
3. 계획 입력 템플릿과 부서별 승인 흐름
4. 계획 대비 실적 차이 분석
5. 단가·물량·원가·인력·전기료·환율 가정 변경
6. 손익·현금흐름 결과 비교
7. 가정·데이터·승인·계산 버전의 Decision Ledger 기록

### 17.3 파일럿 성공 기준

- 경영관리팀 사용자가 상담사만으로 필요한 데이터와 추진 순서를 이해한다.
- 최소 기준정보와 실적 데이터의 준비도를 수치로 확인한다.
- 계획 입력부터 승인까지 한 번 완주한다.
- 적어도 세 개의 시나리오를 동일 기준선에서 재현한다.
- 결과 수치의 입력 데이터·가정·산식 버전을 추적한다.
- 기존 엑셀 기반 계획 대비 업무 시간 또는 오류·재작업을 줄였다는 사용자 검증을 확보한다.

---

## 18. 다음 작업자가 시작할 작업

1. 이 문서와 `AI_HANDOFF.md`, 최신 handoff를 읽고 현재 브랜치·작업트리 상태를 확인한다.
2. P0 안정화 이슈가 미완료라면 M0 기능보다 먼저 해결한다.
3. M0의 첫 구현은 “경영계획 상담 플레이북 + Solution Blueprint”로 제한한다.
4. 새 테이블/파일 저장소를 만들기 전 현재 M1 기준정보·지식 허브·프로젝트 상태 저장 방식을 조사한다.
5. 상담 결과는 자유 텍스트가 아닌 Pydantic 스키마를 통과한 JSON으로 저장한다.
6. 프로젝트 생성으로 연결할 때 기존 Clarification을 우회하지 말고, Blueprint를 상위 입력값으로 주입한다.
7. 구현 뒤에는 단위 테스트, API 계약 테스트, 선택형 대화 E2E, 기존 프로젝트 생성 회귀 테스트를 추가한다.

---

## 19. 완료 선언 기준

어떤 마일스톤도 UI 화면 하나 또는 API 하나만으로 완료 선언하지 않는다. 아래 네 가지가 모두 있어야 한다.

1. 데이터 모델과 저장 방식
2. 백엔드 API와 권한/오류 처리
3. 실제 사용 가능한 UI와 상태 전이
4. 자동 테스트와 사용자 수용 기준

이 원칙을 지켜야 AI Factory Studio가 데모 중심 생성기가 아니라, 신뢰 가능한 기업 운영 플랫폼으로 성장할 수 있다.
