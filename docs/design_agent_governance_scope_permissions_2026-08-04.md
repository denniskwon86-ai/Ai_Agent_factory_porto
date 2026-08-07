# AI Factory Studio 에이전트 생성기·워크플로우 권한 통합 설계

> 문서 상태: Supervisor 승인 · 구현 기준 확정 / 코드 적용 전  
> 작성: Codex / 2026-08-04  
> 목적: 조직·회사 권한을 에이전트 생성, 워크플로우 편집, 스킬 생성, 조직 배치, 실제 실행까지 끊김 없이 적용한다.

> **승인 결정(2026-08-04):** 기존 `조직·권한` 모달을 최종안으로 유지하지 않는다. 동일 제품 안의 독립 전체화면 `관리자 센터`를 구축하고, 메뉴 가시성·페이지 진입·서버 API의 3단계 권한 강제를 적용한다. 별도 배포 애플리케이션은 현 단계 범위가 아니며 향후 규제·보안 요구가 생길 때 재검토한다.

## 1. 결론

현재 조직·사용자 권한과 에이전트 생성기는 **연결되어 있지 않다**. 조직별 `Agent Pack` 바인딩이 일부 구현되어 있으나, 이는 이미 존재하는 에이전트 ID 목록을 조직에 배치하는 기능일 뿐 다음을 통제하지 못한다.

- 누가 에이전트 정의를 조회·생성·수정·초기화할 수 있는가
- 누가 워크플로우 템플릿을 복사·수정·삭제·공유·승인할 수 있는가
- 어느 회사·사업부·공장에 어떤 에이전트와 템플릿이 보이고 실행되는가
- 생성된 에이전트가 어떤 데이터·도구·외부 시스템을 읽고 쓸 수 있는가
- 실제 조직과 가상 회사의 에이전트·데이터 권한이 어떻게 분리되는가
- 어떤 버전의 에이전트 구성이 어떤 산출물을 만들었는가

따라서 `Agent Master`를 전역 JSON 편집기에서 **범위·승인·버전·실행 권한을 관리하는 Agent Governance Center**로 전환한다. 화면 버튼 숨김이 아니라 서버 저장소, API, 프로젝트 생성, 그래프 실행, 도구 호출까지 같은 정책으로 강제해야 한다.

## 2. 현재 코드에서 확인된 결함

### 2.1 전역 레지스트리 무권한 조회·수정·초기화

- `api/routes/factory_control.py:1666-1691`
  - `GET /agents`, `PUT /agents`, `POST /agents/reset`에 `current_principal` 의존성이 없다.
  - 등록된 일반 사용자·익명 사용자·타 사업부 사용자 구분 없이 전역 구성을 읽고 덮어쓰거나 초기화할 수 있다.
- `core/agent_registry.py:140-178`
  - 모든 사용자가 하나의 `agents_registry.json`을 공유한다.
  - 소유 조직, 테넌트, 공개 범위, 승인 상태, 작성자, 변경 이력이 없다.

### 2.2 워크플로우 템플릿 전역 노출·변경

- `api/routes/factory_control.py:1905-1952`
  - 템플릿 목록·상세·복사·저장·삭제 API 모두 사용자·조직 문맥을 받지 않는다.
- `core/agent_registry.py:225-309`
  - `templates/<id>.json`을 전역 저장소로 사용한다.
  - 어느 부서 사용자가 만든 템플릿인지, 누가 사용할 수 있는지 판단할 정보가 없다.
- `api/routes/factory_control.py:421-485`
  - 독립 프로젝트 생성은 템플릿이 전체 목록에 존재하는지만 확인한다.
  - 현재 사용자의 조직에 허용된 템플릿인지 검증하지 않는다.

### 2.3 스킬 자동생성의 P0 보안·무결성 결함

- `api/routes/factory_control.py:1858` 이후 `POST /ai-recommend/skill`
  - 권한 검사 없이 공용 `skills/` 디렉터리에 파일을 직접 쓴다.
  - `agent_id`를 파일명에 사용하면서 안전한 ID 정규식 검증이 없다.
  - 기존 공용 스킬을 덮어쓸 수 있고, 잘못된 ID가 경로 구성에 개입할 수 있다.
  - 초안·검토·승인·버전·되돌림 절차가 없다.

### 2.4 Agent Pack은 생성기 권한을 대체하지 못함

- `core/enterprise_context/agent_pack_binding.py`
  - 팩은 에이전트 ID 목록과 조직 바인딩을 관리한다. 에이전트 정의와 스킬의 소유·편집 권한은 관리하지 않는다.
- `core/org_seed.py:100-140`
  - 팩 해석은 Mega 프로젝트용 부서 설정 경로에서만 사용한다.
  - 바인딩이 없거나 해석 실패 시 기존 `domain_agents`를 사용하는 하위호환 폴백이 있어, 권한 강제 환경에서도 의도치 않은 실행이 가능하다.
- `api/routes/enterprise_context_control.py:655-721`
  - 팩 목록은 요청자 가시 범위나 테넌트로 필터링하지 않는다.
  - 노드별 에이전트 해석 API는 해당 노드를 볼 권한을 확인하지 않는다.
- 독립 프로젝트 생성·일반 스프린트 실행은 조직별 Agent Pack 허용 집합을 검사하지 않는다.

### 2.5 프론트엔드가 권한 상태를 표현하지 않음

- `frontend/src/store/useFactoryStore.ts:426-567`
  - 조회·저장·초기화·템플릿 복사·삭제가 모두 전역 API를 호출한다.
  - 전역 fetch interceptor는 사용자 식별만 붙이고 Enterprise Context 헤더는 아직 붙이지 않는다.
- `frontend/src/components/AgentMasterPanel.tsx`
  - 사용자 역할과 무관하게 저장·초기화·AI 추천·복사·삭제 버튼을 제공한다.
  - 현재 회사·사업부·공장, 소유 조직, 공개 범위, 승인 상태, 사용 가능 범위를 표시하지 않는다.

## 3. 제품 원칙

1. **정의 권한과 실행 권한을 분리한다.** 에이전트를 볼 수 있다고 수정하거나 실행할 수 있는 것은 아니다.
2. **미지정은 공용이 아니다.** `tenant_id`, `owner_scope_id`, `entity_mode`가 없으면 신규 자산은 누구에게도 노출·실행하지 않는다.
3. **기본 제공 자산은 불변이다.** 시스템 기본 에이전트·스킬·워크플로우는 직접 수정하지 않고 복사본으로 확장한다.
4. **조직 공유는 승인 행위다.** 개인 초안이 자동으로 부서 또는 전사 자산이 되지 않는다.
5. **데이터·도구 권한은 실행 시 재검사한다.** 화면에서 허용했더라도 실제 도구 호출 직전에 서버가 다시 판단한다.
6. **가상 조직은 정의를 복사할 수 있지만 실제 데이터 권한은 복사하지 않는다.** REAL과 VIRTUAL의 데이터·커넥터·비밀정보 경계를 유지한다.
7. **모든 실행은 버전 스냅샷을 남긴다.** 나중에 산출물의 생성 근거를 설명할 수 있어야 한다.
8. **타 조직 자산은 목록에서 필터하고 상세 조회는 404로 은폐한다.** 존재 여부 자체를 누설하지 않는다.

## 4. 권한 모델

### 4.1 권한 단위

| 권한 코드 | 의미 |
|---|---|
| `agent.definition.read` | 허용 범위의 에이전트 정의 조회 |
| `agent.definition.create` | 개인/조직 초안 생성 |
| `agent.definition.update` | 소유 초안 또는 관리 범위 정의 수정 |
| `agent.definition.publish` | 조직·전사 사용 가능 상태로 승인 |
| `agent.definition.retire` | 신규 사용 중단, 과거 버전 보존 |
| `agent.execute` | 승인된 에이전트 실행 |
| `workflow.read/create/update` | 워크플로우 조회·생성·편집 |
| `workflow.publish/retire` | 워크플로우 승인·폐기 |
| `workflow.bind` | 조직 노드에 워크플로우/Agent Pack 배치 |
| `skill.propose` | 스킬 초안·변경 제안 생성 |
| `skill.approve` | 공용 스킬 승인·활성화 |
| `model.policy.manage` | 모델 티어·비용 한도·공급자 정책 변경 |

### 4.2 역할별 기본 권한

| 주체 | 생성/초안 | 조직 공개 | 전사 공개 | 시스템 기본 수정 | 실행 |
|---|---:|---:|---:|---:|---:|
| 플랫폼 관리자 | 가능 | 가능 | 가능 | 복사·버전 승격만 가능 | 가능 |
| AI 거버넌스 관리자 | 가능 | 가능 | 승인 가능 | 직접 수정 불가 | 가능 |
| 부서 `manager` | 가능 | 자기 조직 승인 가능 | 승격 요청만 | 불가 | 자기 가시 범위 |
| 부서 `member` | 개인/조직 초안 가능 | 승인 요청만 | 불가 | 불가 | 승인된 가시 범위 |
| 부서 `viewer` | 불가 | 불가 | 불가 | 불가 | 승인된 읽기 전용 실행만 |
| 경영진 | 불가 | 불가 | 불가 | 불가 | 가시 범위 실행·결과 열람 |
| Jarvis/자동화 계정 | 위임된 권한만 | 불가 | 불가 | 불가 | 요청자 권한을 초과할 수 없음 |

현재 `AccessScope`에는 AI 관리 권한과 `manager` 범위가 확정 결과로 남지 않는다. 다음 필드를 추가한다.

- 사용자: `is_ai_admin`
- 확정 범위: `can_manage_agents`, `manageable_dept_ids`, `manageable_scope_nodes`
- `/api/v1/org/me`: 위 권한을 화면용으로 반환

`is_data_admin`을 AI 관리자 대신 사용하지 않는다. 데이터 표준 승인과 AI 행동·비용 정책 승인은 책임이 다르다.

## 5. 자산 모델

### 5.1 공통 메타데이터

모든 에이전트 정의, 스킬, 워크플로우 템플릿, Agent Pack에 다음 필드를 공통 적용한다.

```json
{
  "tenant_id": "tenant_default",
  "owner_scope_id": "lsmnm-copper",
  "entity_mode": "REAL",
  "visibility": "PERSONAL|SCOPE|DESCENDANTS|ENTERPRISE|SYSTEM",
  "status": "DRAFT|REVIEW|APPROVED|RETIRED",
  "version": 3,
  "created_by": "user-id",
  "approved_by": "user-id",
  "effective_from": "2026-08-04",
  "effective_to": "",
  "supersedes_version": 2
}
```

### 5.2 에이전트 정의 추가 필드

```json
{
  "agent_id": "Material_Planning_Agent",
  "name_ko": "원료 도입계획 에이전트",
  "purpose": "원료 구매·통관·입고 계획 생성",
  "skill_asset_id": "skill_xxx",
  "model_policy_id": "balanced-pro-v1",
  "required_permissions": ["purchase.plan.read"],
  "allowed_data_domains": ["supplier", "purchase_order", "shipment"],
  "allowed_tools": ["catalog.query", "mcp.erp.read"],
  "write_effects": ["draft.create"],
  "approval_gate": "REQUIRED_BEFORE_EXTERNAL_WRITE",
  "output_classification": "INTERNAL"
}
```

에이전트의 `allowed_tools`는 희망 목록이며 실제 실행 권한은 `요청자 권한 ∩ 조직 정책 ∩ 에이전트 허용 목록 ∩ 도구 자체 정책`으로 계산한다.

### 5.3 저장소 전환

새 자산을 전역 JSON/Markdown 파일로 직접 쓰지 않는다.

- 코드 내 `DEFAULT_REGISTRY`와 기존 `skills/*.md`: `SYSTEM` 원본, 읽기 전용
- 기존 `templates/*.json`: 마이그레이션 시 명시적 테넌트·소유 범위를 부여한 레거시 자산
- 신규 정의·스킬·템플릿: `master.db`의 버전형 자산 테이블에 저장
- 런타임: DB 자산을 기존 그래프 입력 구조로 변환하는 adapter 사용

권장 테이블:

- `agent_definitions`
- `agent_definition_versions`
- `skill_assets`
- `skill_asset_versions`
- `workflow_templates_v2`
- `workflow_template_versions`
- `workflow_scope_bindings`
- `agent_execution_snapshots`

기존 파일 저장소는 즉시 삭제하지 않고 읽기 adapter로 유지한다.

## 6. 서버 판정 흐름

### 6.1 목록·상세

1. `current_principal`과 `enterprise_context`를 해석한다.
2. 권한 강제 상태에서 미식별·미바인딩 요청은 비노출한다.
3. `tenant_id`, `entity_mode`, 가시 조직, visibility, status를 모두 만족하는 자산만 목록에 포함한다.
4. 목록 응답은 `data`, `blocked_reason`, `hidden_count`, `permission`을 반환한다.
5. 타 조직 상세 ID 직접 조회는 404를 반환하고 감사 로그를 남긴다.

### 6.2 생성·수정·승인

1. 생성 시 소유 조직을 요청 본문만 믿지 않고 서버 문맥과 요청자 쓰기 범위로 교차 검증한다.
2. `member`는 DRAFT 생성·수정까지만 가능하다.
3. 조직 `manager`는 관리 범위의 APPROVED 전환과 하위 상속을 승인할 수 있다.
4. ENTERPRISE 승격과 시스템 정책 변경은 AI 거버넌스 관리자 이상만 가능하다.
5. 승인된 버전은 덮어쓰지 않고 새 버전을 만든다.
6. 삭제는 물리 삭제가 아니라 RETIRED 전환이다.

### 6.3 프로젝트 생성·실행

1. 프로젝트 생성 시 템플릿 존재 여부가 아니라 **현재 조직에서 사용 가능한 승인 버전인지** 검사한다.
2. 독립 프로젝트와 Mega 프로젝트가 같은 resolver를 사용한다.
3. 프로젝트 메타에 다음을 스냅샷한다.
   - `workflow_template_id/version`
   - `agent_definition_ids/versions`
   - `skill_asset_ids/versions`
   - `policy_decision_id`
   - `tenant_id`, `enterprise_scope_id`, `entity_mode`
4. 스프린트 재개 시 현재 권한을 다시 검사한다. 권한이 회수됐으면 새 외부 읽기·쓰기는 막되 과거 체크포인트는 감사 목적으로 보존한다.
5. Agent Pack 미바인딩·해석 실패를 `domain_agents` 전면 통과로 바꾸지 않는다. 권한 강제 모드에서는 명시적 실패 상태를 반환한다.

### 6.4 도구 호출

각 도구 호출 직전에 `AgentToolAuthorization`을 실행한다.

```text
사용자 권한
  ∩ 선택 조직 문맥
  ∩ 승인된 에이전트 정의의 allowed_tools / data_domains
  ∩ 프로젝트 데이터 계약
  ∩ 도구별 읽기·쓰기 정책
  = 실제 허용 권한
```

LLM의 프롬프트 지시는 권한 근거가 아니다. 거부된 호출은 다른 모델로 폴백하지 않고 중단·설명·감사한다.

## 7. API 명세

기존 `/api/v1/factory/agents`, `/templates`는 호환 adapter로 유지하되 신규 구현은 다음 API를 기준으로 한다.

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/v1/agent-governance/capabilities` | 현재 사용자의 에이전트 관련 권한과 이유 |
| GET/POST | `/api/v1/agent-governance/agents` | 가시 에이전트 목록 / 초안 생성 |
| GET/PUT | `/api/v1/agent-governance/agents/{id}` | 상세 / 새 버전 저장 |
| POST | `/api/v1/agent-governance/agents/{id}/submit` | 승인 요청 |
| POST | `/api/v1/agent-governance/agents/{id}/approve` | 조직·전사 승인 |
| POST | `/api/v1/agent-governance/agents/{id}/retire` | 소프트 폐기 |
| GET/POST | `/api/v1/agent-governance/workflows` | 워크플로우 목록 / 초안 생성 |
| POST | `/api/v1/agent-governance/workflows/{id}/copy` | 허용 범위로 복사 |
| POST | `/api/v1/agent-governance/workflows/{id}/bind` | 조직 노드 배치 |
| POST | `/api/v1/agent-governance/skills/propose` | 스킬 초안 생성, 파일 직접 쓰기 금지 |
| POST | `/api/v1/agent-governance/skills/{id}/approve` | 승인 후 새 버전 활성화 |
| POST | `/api/v1/agent-governance/resolve` | 현재 문맥에서 실제 사용 가능한 구성과 근거 해석 |

### 7.1 기존 API의 즉시 계약

- 모든 기존 Agent/Template/AI Recommend API에 `current_principal`과 필요한 경우 `enterprise_context`를 추가한다.
- `PUT /agents`, `POST /agents/reset`, 기존 파일 기반 skill 생성은 플랫폼 관리자만 허용한다.
- `agent_id`, `template_id`, `skill_id`를 서버의 동일한 안전 정규식으로 검증한다.
- 기존 `GET` 목록은 사용자 가시 범위만 반환한다.
- 권한 없는 상세는 404, 권한 없는 명시적 변경은 403을 사용한다.
- 모든 변경·초기화·승인·바인딩·실행을 감사 로그에 남긴다.

## 8. 관리자 센터와 Agent Governance Center 화면

### 8.1 화면 분리 원칙

기존 `OrgChartPanel` 모달은 최종 구조로 사용하지 않는다. 제품 최상위에 독립된 **관리자 센터(Admin Center)**를 두고, `AgentMasterPanel`은 별도의 **Agent Governance Center**로 운영한다.

```text
관리자 센터
├─ 회사·조직 구조
├─ 사용자·부서 역할
├─ 관리자 역할·기능 권한
├─ 프로그램·업무 앱 접근 권한
├─ 에이전트·워크플로우 관리 권한
├─ 데이터·MCP·외부연계 권한
├─ SSO·인증·세션 정책
└─ 접근 검토·감사 이력

Agent Governance Center
├─ 에이전트 정의·버전
├─ 스킬·도구·데이터 사용 범위
├─ 워크플로우 구성
├─ 조직 배치·공유·승인
└─ 실행 품질·비용·정책 위반
```

관리자 센터는 “누가 무엇을 할 수 있는가”를 설정하고, Agent Governance Center는 그 권한 범위 안에서 “어떤 에이전트를 만들고 운영할 것인가”를 관리한다. 두 책임을 한 화면에 섞지 않는다.

### 8.2 관리자 센터 진입·권한 계약

- 상단 글로벌 메뉴의 일반 업무 기능과 분리된 `관리자 센터` 진입점을 둔다.
- 관리자 capability가 하나도 없는 사용자는 메뉴를 보지 못한다.
- URL 또는 내부 상태를 직접 조작해 진입하면 Route Guard가 접근 불가 화면을 표시한다.
- Route Guard는 편의를 위한 1차 제어일 뿐이며, 모든 관리자 API는 서버에서 다시 권한을 검사한다.
- 전체 관리자는 모든 탭을 볼 수 있다.
- 조직 관리자는 허용된 조직 범위의 사용자·역할만 관리한다.
- AI 관리자는 Agent/Workflow/Skill 권한과 정책 탭만 관리한다.
- 데이터 관리자는 데이터·카탈로그·MCP 권한 탭만 관리한다.
- 감사 담당자는 변경 없이 접근 이력과 권한 검토 결과만 열람한다.
- 현재 권한과 선택 조직을 상단에 고정하고, 다른 조직을 선택해도 권한이 자동 승급되지 않는다.
- 타 조직의 사용자·역할·정책 상세는 404로 은폐한다.

최종 URL 구조는 다음을 권장한다. 현재 SPA가 URL Router를 사용하지 않는 이행 단계에서는 동일한 경계를 최상위 full-screen view로 먼저 구현하되, 모달로 되돌리지 않는다.

| URL | 화면 |
|---|---|
| `/admin/organization` | 회사·조직 구조와 조직 범위 |
| `/admin/users` | 사용자·소속·부서 역할 |
| `/admin/permissions` | 기능·프로그램·관리 capability |
| `/admin/agent-access` | 에이전트 생성·승인·실행 권한 |
| `/admin/data-access` | 데이터·카탈로그·MCP·외부연계 권한 |
| `/admin/security` | SSO·인증·세션·보안 정책 |
| `/admin/audit` | 접근 이력·권한 변경·정기 재검토 |
| `/agent-governance` | 에이전트·스킬·워크플로우 운영 |

개인 알림·언어·화면 밀도 같은 사용자 환경설정은 관리자 센터가 아니라 별도의 `내 설정`에 둔다. 회사 CI·대표 색상처럼 전사에 영향을 주는 설정은 관리자 센터의 회사 설정에 둔다.

### 8.3 Agent Governance Center 상단 문맥

- 현재 회사 / 사업부 / 공장 / REAL·VIRTUAL
- 현재 권한: `조직 초안 작성 가능`, `승인 불가`처럼 행동 단위로 표시
- 현재 보는 범위와 숨겨진 자산 수

### 8.4 자산 탭

- 기본 제공
- 전사 공용
- 우리 조직
- 내 초안
- 승인 대기
- 사용 중단

각 카드·그래프 노드에 `소유 조직`, `공개 범위`, `상태`, `버전`, `승인자`, `사용 중인 프로젝트 수`를 표시한다.

### 8.5 생성 마법사

1. 업무 목적과 산출물
2. 소유 조직과 공개 범위
3. 필요한 데이터 도메인
4. 허용 도구와 쓰기 영향
5. 모델 품질·비용 정책
6. 사용자 승인 게이트
7. 테스트 실행
8. 승인 요청

AI 추천은 사용자가 허용받은 데이터·도구 범위 안에서만 후보를 만든다. 권한이 없는 기능을 Jarvis나 추천 UI가 “가능”하다고 안내하지 않는다.

### 8.6 버튼 계약

- 권한이 없으면 단순히 숨기지 말고, 자산을 볼 수 있는 상황에서는 비활성 버튼과 사유를 제공한다.
- 타 조직 자산 존재 자체가 비공개인 경우에는 항목을 표시하지 않는다.
- `기본값 초기화`는 플랫폼 관리자에게만 표시한다.
- `저장`은 초안 저장, `승인 요청`, `조직 공개`, `전사 승격 요청`을 분리한다.

## 9. 단계별 구현 순서

### P0 — 즉시 보안 봉합

1. 기존 Agent/Template/Recommend API에 요청자 식별과 권한 검사 추가
2. 스킬 파일 경로 검증, 공용 파일 직접 덮어쓰기 차단
3. 전역 reset·default 수정은 플랫폼 관리자 전용
4. Agent Pack 목록·상세·resolve에 tenant/조직 범위 필터와 404 은폐 적용
5. 권한 강제 모드의 미바인딩 fallback 차단
6. 관련 감사 이벤트와 회귀 테스트 추가

### P1 — 범위형 자산 저장소

1. 버전형 Agent/Skill/Workflow 테이블 추가
2. 기존 파일 자산을 SYSTEM·LEGACY adapter로 노출
3. 역할·capability 해석 추가
4. 조직별 목록·복사·승인·폐기 API 구현
5. 기존 `/agents`, `/templates`를 adapter로 전환

### P2 — 생성기 UI 통합

1. 전역 컨텍스트 헤더를 공통 API interceptor에 연결
2. Agent Governance Center의 범위 탭·권한 상태·승인 흐름 구현
3. AI 추천 입력에 현재 조직 프로필과 허용 데이터·도구 목록 주입
4. 관리자·manager·member·viewer·익명 화면 실측

### P3 — 런타임 강제

1. 독립·Mega 프로젝트가 동일한 Agent Configuration Resolver 사용
2. 프로젝트·릴리스에 버전 스냅샷과 정책 결정 ID 저장
3. 도구 호출 권한 교집합 강제
4. 권한 회수·템플릿 폐기·버전 변경 중 재개 규칙 구현

### P4 — 품질·비용·운영 고도화

1. 에이전트별 비용 한도·모델 정책·성공률 표시
2. 조직별 사용량·실패·승인 대기·정책 위반 대시보드
3. 검증된 조직 자산의 전사 승격 추천
4. 사용되지 않거나 중복된 에이전트·스킬 정리 제안

## 10. 필수 테스트

### 보안

- 익명·미등록 사용자는 에이전트/템플릿 목록과 변경 API를 사용할 수 없다.
- A 사업부 사용자는 B 사업부 비공개 에이전트의 목록·상세·복사·실행을 할 수 없다.
- 타 조직 상세는 404이며 감사 이벤트가 남는다.
- member는 초안을 만들 수 있지만 승인할 수 없다.
- manager는 자기 관리 범위만 승인할 수 있다.
- 경영진은 전사 결과를 볼 수 있어도 에이전트 정의를 수정할 수 없다.
- 시스템 기본 자산은 어떤 사용자도 직접 덮어쓰지 못한다.
- `../`, 슬래시, 제어문자가 포함된 agent/skill/template ID는 400으로 차단한다.

### 범위·실행

- 독립 프로젝트와 Mega 프로젝트가 동일한 조직별 허용 구성을 얻는다.
- 미바인딩 상태는 “에이전트 0개”가 아니라 “조직 배치 없음”으로 구분된다.
- 테넌트가 다른 Agent Pack을 바인딩하거나 해석하지 못한다.
- REAL에서 만든 정의를 VIRTUAL에 복사해도 REAL 데이터·MCP 비밀 권한은 따라가지 않는다.
- 폐기된 템플릿으로 새 프로젝트는 만들 수 없고 기존 프로젝트는 스냅샷으로 감사 가능하다.
- 스프린트 도중 권한 회수 시 새 외부 쓰기가 차단되고 사용자에게 다음 조치가 안내된다.

### UI

- 관리자·manager·member·viewer·익명 각각에서 버튼·설명·목록이 서버 권한과 일치한다.
- API 403을 버튼 클릭 후 처음 알게 되는 경로가 없어야 한다.
- 현재 회사·조직·모드가 화면에서 항상 확인 가능하다.
- 조회 실패, 권한 없음, 자산 0건, 배치 없음이 서로 다른 상태로 표시된다.

## 11. 완료 기준

다음이 모두 충족돼야 “권한이 에이전트 생성기에 반영됐다”고 판정한다.

1. 조회·생성·수정·승인·공유·실행 권한이 서버에서 강제된다.
2. 독립 프로젝트와 Mega 프로젝트가 같은 조직별 resolver를 사용한다.
3. Agent·Skill·Workflow·Pack이 명시적 tenant/scope/mode와 버전을 가진다.
4. 실제 도구 호출이 요청자와 에이전트 권한의 교집합을 벗어나지 못한다.
5. 관리자·manager·member·viewer·익명, REAL·VIRTUAL 조합 회귀 테스트가 통과한다.
6. UI가 허용되지 않은 행동을 추천하거나 가능하다고 안내하지 않는다.
7. 누가 언제 무엇을 생성·변경·승인·배치·실행했는지 감사 로그로 재현할 수 있다.

## 12. 구현 작업 분담 제안

- **Claude Code**: P0 서버 봉합, P1 저장소/API, P3 런타임·테스트
- **Codex**: Agent Governance Center 정보구조·권한 상태 UI, 역할별 래스터 감사, 기존 기능 보존 검토
- **Antigravity**: 외부 엔터프라이즈 Agent Governance 사례와 정책 비교, 도구·데이터 권한 분류 교차검증
- **Supervisor**: 조직별 작성·승인 역할과 전사 승격 책임자 최종 결정

역할은 고정 경계가 아니며 보안·권한·핵심 API는 구현자가 자체 검토한 뒤 최소 한 번 교차검증한다. 교차검증 대기 때문에 P0 봉합을 미루지는 않는다.
