# Living Enterprise Canvas 실제 구현 매핑

이 문서는 대표 화면을 현재 소스의 기능과 연결하고, 아직 없는 부분을 명확히 분리한다. 디자인 채택 전에는 실제 `frontend/`와 API를 변경하지 않는다.

## 1. 화면 영역별 현재 구현 상태

| 화면 영역 | 현재 연결 가능한 소스·API | 상태 | 추가 구현 |
|---|---|---|---|
| 회사·사업부·공장 컨텍스트 | `enterprise_context_control.py`의 `/nodes/{node_id}/scope`, `/contexts/{scope_id}/resolved-profile`, `OrgChartPanel.tsx` | 부분 구현 | 현재 사용자 기본 scope와 회사 CI 토큰을 함께 반환하는 Context Bootstrap 필요 |
| 좌측 의사결정 대기열 | `/{project_id}/wbs`, `/feed`, `/state/latest`, `useFactoryStore.ts`의 WBS·Feed·SSE 상태 | 프로젝트 단위 구현 | 여러 프로젝트·운영·품질·경영 이슈를 영향도 순으로 합치는 회사 범위 Read Model 필요 |
| Enterprise Digital Thread | WBS 작업·SSE 노드 이벤트, 조직·Master scope, Release Library | 데이터가 분산됨 | 수주→손익 표준 도메인과 프로젝트·시스템·데이터·Twin을 연결하는 Aggregate API 필요 |
| 현업 생성 SW 레이어 | `/library/list`, 프로젝트·릴리스·Workspace 기능 | 구현 | 각 릴리스에 업무 도메인·회사 scope·운영 상태를 연결하는 메타데이터 보강 |
| Data 레이어 | `master_control.py`의 Master record·alias·scope binding, 외부 연계·계약·카탈로그 기능 | 부분 구현 | Domain Node별 근거 수·품질·최신시점 요약 API 필요 |
| Digital Twin 레이어 | `planning_control.py`의 외부 Driver, Factory `resimulate` 및 시뮬레이션 상태 | 부분 구현 | 시나리오와 업무 노드·경영 KPI의 관계를 표준화한 Scenario Summary 필요 |
| 하단 Trust Foundation | MDM scope binding, 지식 Library, 외부 Driver, 연계 시스템 상태 | 부분 구현 | 최신성·계보·권한·계약 상태를 단일 구조로 집계 |
| 우측 Atlas | `/{project_id}/supervisor/chat`, `HOTLInput.tsx` | 프로젝트 대화 구현 | 프로젝트 ID 없는 회사 범위 Atlas API와 Context Resolver 필요 |
| Agent·품질·LLM 비용 | SSE Agent 활동, 품질·실패 상태, 텔레메트리 화면 | 부분 구현 | 회사 범위 비용·품질 집계와 선택 노드별 drill-down 필요 |

## 2. 신규 Read Model API 제안

초기 구현은 기존 테이블과 API를 파괴적으로 통합하지 않고 읽기 전용 집계 계층을 추가한다.

```http
GET /api/v1/enterprise-canvas?scope_id={scope_id}&as_of={iso_datetime}
```

```json
{
  "context": {
    "scope_id": "lsmnm-smelting-onsan-1",
    "company_name": "LS MnM",
    "org_path": ["LS MnM", "동제련 사업부", "온산 제1공장"],
    "industry_profile": "nonferrous_metal_manufacturing",
    "theme": {"primary": "#0A1E5A", "accent": "#FA002D"}
  },
  "decision_queue": [],
  "domain_nodes": [],
  "relationships": [],
  "trust_foundation": {
    "master_data": {},
    "operation_data": {},
    "knowledge": {},
    "external_signals": {}
  },
  "agent_summary": {},
  "cost_summary": {},
  "generated_at": "2026-07-30T00:00:00Z"
}
```

### `domain_nodes[]` 최소 계약

```json
{
  "domain_code": "production_plan",
  "label": "생산계획",
  "status": "DECISION_REQUIRED",
  "metrics": [{"code": "delivery_rate", "value": 96.8, "unit": "%"}],
  "projects": [],
  "releases": [],
  "data_assets": [],
  "scenarios": [],
  "evidence_count": 48,
  "confidence": 0.89,
  "updated_at": "2026-07-30T00:00:00Z"
}
```

## 3. Atlas 전역 대화 계약

현재 Supervisor Chat은 `project_id`가 필요하므로 대표 화면의 Atlas 요구와 완전히 일치하지 않는다. 프로젝트 API를 억지로 재사용하지 않고 회사 범위의 별도 진입점을 둔다.

```http
POST /api/v1/atlas/chat
Content-Type: application/json
```

```json
{
  "scope_id": "lsmnm-smelting-onsan-1",
  "project_id": null,
  "domain_code": "production_plan",
  "question": "전력비가 15% 오르면 내년 손익은?",
  "screen_context": {
    "selected_decision_id": "decision-001",
    "selected_scenario_id": null,
    "as_of": "2026-07-30T00:00:00Z"
  }
}
```

응답은 답변 본문뿐 아니라 사용 근거·권한 범위·추천 행동·실행 가능 여부를 분리해야 한다. Atlas가 실제 제어를 요청하면 읽기 답변과 실행 명령 사이에 HOTL 확인을 둔다.

## 4. 프론트엔드 컴포넌트 분해

```text
LivingEnterprisePage
├─ CompanyContextBar
├─ DecisionQueue
├─ EnterpriseThreadCanvas
│  ├─ DomainNode
│  ├─ RelationshipLayer
│  ├─ ProductOverlay
│  ├─ DataOverlay
│  ├─ TwinOverlay
│  └─ DecisionFocusPanel
├─ TrustFoundationStrip
└─ AtlasGlobalRail
```

기존 `ControlPanel`, `TimelinePanel`, `PreviewPanel`은 폐기하지 않는다. 사용자가 Domain Node·현업 SW·프로젝트를 선택했을 때 열리는 상세 작업 공간으로 재배치한다.

## 5. 단계별 수행 계획

### MC-1 · Read-only Canvas

- Enterprise Canvas Aggregate API와 타입 정의
- 회사 Context, 프로젝트 WBS·상태·Feed, Release, MDM 요약 연결
- 대표 화면을 읽기 전용 React 화면으로 이식
- 기존 통제실로 돌아가는 안전한 링크 유지

### MC-2 · 실시간 운영 연결

- 기존 `/ws/timeline` 프로젝트 이벤트를 선택 노드에 반영
- 프로젝트 밖 운영 이벤트는 회사 scope Event Contract가 준비될 때 추가
- 이벤트가 없어도 Aggregate API 재조회로 복구 가능한 구조 유지

### MC-3 · Atlas Global

- 전역 Context Resolver와 `/api/v1/atlas/chat` 구현
- 근거·권한·비용을 답변과 함께 반환
- 실행성 행동은 HOTL 승인 후 기존 Sprint·Twin·Release API로 위임

### MC-4 · 실제 의사결정

- 시나리오 비교·근거 추적·의사결정안 저장 연결
- 역할별 대기열과 조직 공유·승인 적용
- 완료 시간·오류·이해도·의사결정 확신을 사용자 과업 테스트로 측정

## 6. 채택 게이트

다음 기준을 충족한 경우에만 실제 메인 화면으로 확대한다.

1. 처음 보는 사용자가 10초 안에 현재 회사 범위와 가장 중요한 의사결정을 찾는다.
2. 30초 안에 문제와 연결된 데이터·SW·시나리오·근거로 이동한다.
3. Atlas가 프로젝트 ID 없이 선택한 회사·업무 맥락으로 답한다.
4. 근거 없는 수치나 실행 불가능한 버튼을 표시하지 않는다.
5. 기존 프로젝트 통제실의 기능 손실 없이 상세 화면으로 연결된다.
