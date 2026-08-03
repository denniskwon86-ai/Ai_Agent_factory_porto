# Living Enterprise Canvas · 구현 추적 매트릭스

> 목적: 승인 UI와 현재 구현 사이의 기능 누락·중복·신규 의존성을 추적한다.  
> 기준: 2026-07-30 현재 `dev` 소스와 공유 작업트리.  
> 주의: 이 문서는 UI 구현 시 기능을 “예쁘게 재작성”하는 문서가 아니라, 기존 도메인 규칙과 API를 보존하는 인계표다.

---

## 1. 현재 상태 요약

| 영역 | 현재 구현 | 제품 화면 관점 평가 | M6 조치 |
|---|---|---|---|
| 회사·조직 문맥 | ECM tree/entity/node/edge/profile/scope 검증 | 백엔드 강함, 전역 선택기 없음 | Shell Context Switcher |
| 업무 상담 | 선택형 질문·데이터 준비도·청사진·승인·프로젝트 생성 | 기능 완결, 독립 전체화면 | `새 업무 만들기`에 이식 |
| SW 생성 | LangGraph·WBS·SSE·HOTL·Preview·Release | 핵심 제품 기능, 현재 3패널 통제실 | Production Workspace로 보존 이식 |
| 협업 폐쇄루프 | 상세기획·승인 클릭형 프로토타입 | 개인 전달·의사결정·발간 API/React 미구현 | Collaboration Workflow Hub 신규 |
| 전사 브리핑 | 권한 범위 집계, LLM 0콜, 불완전성 노출 | North Star의 좌측 큐 재료 | Decision Queue/Canvas Read Model |
| 부서 워크스페이스 | 공유·포크·승격·운영 준비·롤백·영향 | 기능 완결, 흐름이 한 패널에 밀집 | Operate 3개 화면으로 분해 |
| Shadow Mode | 동일입력 비교·검토·제한 승격 | 기능 완결 | Operate/Simulate 연결 |
| 프로그램 수명주기 | active/deprecated/disabled, 의존 영향 | 기능 완결 | Release/Operate에 배치 |
| 경영계획 | P/L·시나리오·승인·현금흐름·Backtest·동인 | 코어 강함, 현재 단일 긴 화면 | Digital Twin 4개 화면 |
| 지식·원본자료 | 지식팩 CRUD/RAG, 원본 68건 등록부·스캔 | 등록은 됐으나 승인→색인 흐름 미완 | Knowledge Registry + 승인 API |
| MDM·카탈로그 | Golden record·범위·중복·카탈로그·거버넌스 | 기능 분산 | Knowledge/Data 공통 Registry |
| 외부 연계 | Connector·Contract·Crosswalk·MCP | API 다수, UI는 Crosswalk 중심 | Integration Workbench |
| Agent | Registry·Template·Format·Skill Evolution | 구현됨, 제품 흐름과 분리 | Agent Mesh/Studio |
| 품질·비용 | Quality outcome, root cause, LLM telemetry | 구현됨 | Operate Quality & Operations |
| Atlas | 프로젝트 Supervisor Chat + 결정론적 Briefing 기반 | 전역 비서 API 미구현 | `/atlas/chat` 신규 |
| Enterprise Canvas | 승인 HTML prototype | React/API 미구현 | Aggregate API + read-only canary |

---

## 2. 현재 프론트 컴포넌트 → 목표 화면

| 현재 파일 | 현재 책임 | 목표 화면 | 재사용 전략 | 주의 |
|---|---|---|---|---|
| `App.tsx` | 런처, 다수 overlay, 메인 분기 | LE-00 Shell | 대체 | overlay state를 route/context로 전환 |
| `AdvisorPanel.tsx` | 상담 전체 흐름 | BW-01 | UI 재작성, `advisorApi` 재사용 | 준비도·Ledger 기능 보존 |
| `BriefingPanel.tsx` | 전사 집계 목록 | LE-01/LE-02 | 데이터/문구 규칙 재사용 | `complete=false` 최상단 유지 |
| `ControlPanel.tsx` | 아이디어, WBS, Sprint, 복구 | BW-03 | 기능 단위 분해 | Quota/복구/중지 상태 손실 금지 |
| `TimelinePanel.tsx` | Feed+SSE 타임라인 | BW-03 | 재작성 | 로그 cap/virtualization |
| `PreviewPanel.tsx` | 앱·문서·코드 Preview | BW-05/BW-03 | 보안 수정 후 재사용 | iframe same-origin 제거 필요 |
| `WorkflowStrip.tsx` | Agent 단계 | BW-03 | 실제 graph 기반 재작성 | 순서 하드코딩 금지 |
| `HOTLInput.tsx` | 승인·질문·Supervisor Chat | BW-04/AT-01 | 분리 | 프로젝트 HOTL과 전역 Atlas 구분 |
| `MegaBoardroomPanel.tsx` | Mega shared ledger/subprojects | BW-02/LE-01 | 도메인 노드 adapter | 상태 응답 `data.data` 사용 확인 |
| `WorkspacePanel.tsx` | 공유·승격·준비·롤백 | OP-01/OP-02 | 2개 화면 분해 | 게이트 상태 계약 보존 |
| 신규 `CollaborationHub` | 개인 앱 전달·수락·의사결정·발간 | CL-01~04 | 신규 구현 | Workspace 조직 공유와 상태 분리 |
| `ProgramAdminPanel.tsx` | 사용여부 변경 | OP-03 | Drawer로 재작성 | recorded active 구분 |
| `ShadowModePanel.tsx` | Run/비교/검토/승격 | OP-04 | UI 재작성 | 악화 인지·미측정 보존 |
| `PlanningPanel.tsx` | 계획 전체 | DT-01~04 | 4개 화면 분해 | 경고가 숫자 위에 위치 |
| `GovernanceConsole.tsx` | 5개 거버넌스 요약 | KD-01/KD-04 | Home 요약으로 재사용 | D-014 주석/정책 최신화 확인 |
| `KnowledgeHubPanel.tsx` | 지식팩·업로드·검색·원본요약 | KD-01/KD-02 | 분해 | 원본 승인/색인과 즉시 업로드 구분 |
| `MasterDataPanel.tsx` | Master type/record/alias/import | KD-03 | Registry shell에 이식 | 범위·유효기간·버전 강조 |
| `CrosswalkPanel.tsx` | 시스템·스키마·매핑·MCP 테스트 | KD-06 | Integration 흐름에 이식 | Connector/Contract 화면 추가 |
| `WorkStandardPanel.tsx` | Agent 규정과 버전 | OR-04/AG-02 | 재배치 | 업무표준과 Output Format 구분 |
| `OrgChartPanel.tsx` | 부서·사용자·권한 | OR-01/OR-03 | 분해 | ECM 관계 그래프와 기존 부서 매핑 구분 |
| `AgentMasterPanel.tsx` | Agent registry/template 편집 | AG-01 | 재작성 | 그래프 유효성 사전검증 |
| `FormatMasterPanel.tsx` | 출력 양식 | AG-02 | 재배치 | default 삭제 금지 |
| `SkillEvolutionPanel.tsx` | 규칙 승인/반려 | AG-03 | 재작성 | 실패 근거와 회귀 영향 추가 |
| `TelemetryPanel.tsx` | 비용·모델·폴백 | OP-05/AG-04 | 차트 재작성 | 미단가 비용은 하한 |
| `QualityOutcomesView.tsx` | 품질/실패 분류 | OP-05 | 재사용 | 사람 판정 3분리 |
| `TraceabilityGraph.tsx` | 프로젝트 추적성 | BW-05/KD-07 | 확대 | 데이터 Lineage와 연결 |
| `ServerLogPopup.tsx` | 서버 로그 | OP-05 | 관리자 Drawer | 민감정보 마스킹 필요 |
| `UserSwitcher.tsx` | 개발용 사용자 전환 | OR-03 | 운영에서 제거/격리 | impersonation 감사 필요 |

---

## 3. API → 화면 매핑

### 3.1 Enterprise/Atlas

| API | 목표 소비처 | 상태 |
|---|---|---|
| `GET /api/v1/briefing` | LE-01 Decision Queue/요약 | 연결 |
| `GET /api/v1/briefing/sections/{section}` | LE-02 상세 필터 | 연결 |
| `GET /api/v1/enterprise-context/tree` | LE-00 Context Switcher | 연결 |
| `POST /api/v1/enterprise-context/contexts/select` | 문맥 전환 검증 | 연결 |
| `GET /nodes/{node_id}/scope` | 문맥 영향 범위 | 연결 |
| `GET /contexts/{scope_id}/resolved-profile` | 프로필/산업 특화 UI | 연결 |
| `GET /api/v1/enterprise-canvas` | LE-01 통합 Read Model | **신규** |
| `POST /api/v1/atlas/chat` | AT-01 전역 Atlas | **신규** |
| `POST /factory/{project_id}/supervisor/chat` | BW-03 프로젝트 감독 | 하위 호환 |

### 3.2 Build SW

| API 묶음 | 목표 화면 | 상태 |
|---|---|---|
| Advisor consultation/blueprint | BW-01 | 연결 |
| Factory projects/mega/copy/delete | BW-02 | 연결 |
| Factory sprint/hotl/wbs/feed/state | BW-03/BW-04 | 연결 |
| Factory release/export/library | BW-05 | 연결 |
| Factory traceability/impact | BW-05/KD-07 | 연결 |
| `/ws/timeline` | BW-03 live state | 연결 |

### 3.3 Operate

| API 묶음 | 목표 화면 | 상태 |
|---|---|---|
| Workspace shares/forks/access | OP-01 | 연결 |
| Workspace promotions/gate | OP-02 | 연결 |
| Readiness checklist/rollback/impact | OP-02 | 연결 |
| Program status/disable/deprecate/reactivate | OP-03 | 연결 |
| Shadow summary/runs/compare/review/promote | OP-04 | 연결 |
| Telemetry/quality/raw/classify | OP-05 | 연결 |

### 3.4 Simulate

| API 묶음 | 목표 화면 | 상태 |
|---|---|---|
| planning accounts/facts/scenarios/run/compare | DT-01/DT-02 | 연결 |
| submissions/current/approve/reject/integrity | DT-03 | 연결 |
| drivers/impacts/preview/external | DT-02 | 화면 보완 |
| cash-flow/variance/backtest/rollup-check | DT-04 | 연결 |
| import rows/csv/template | DT-01/DT-03 | 화면 보완 |

### 3.5 Knowledge/Data

| API 묶음 | 목표 화면 | 상태 |
|---|---|---|
| Knowledge packs/documents/search | KD-01 | 연결 |
| 자연어 Hybrid Search(lexical+semantic+graph+lineage) | KD-01 | 신규 API·UI 필요 |
| Reference summary/assets/scan | KD-02 | 연결 |
| Reference approve/reject/index | KD-02 | **신규** |
| Master types/records/aliases/import/scope/quality | KD-03 | 연결 |
| Catalog assets/fields/governance | KD-04 | 연결 |
| Glossary terms/synonyms/match | KD-05 | 화면 신규 |
| Connector adapters/connectors/contracts/execute | KD-06 | 화면 신규/보완 |
| Contract preview/evaluate/activate | KD-06/KD-07 | 화면 신규/보완 |
| Crosswalk schema/proposals/mappings | KD-06 | 연결 |
| MCP resolve/batch/health | KD-06 | 연결 |
| Lineage quality/freshness/edges/impact | KD-07 | 화면 신규/보완 |
| External indicators/sources/observations/value | KD-08 | 화면 신규 |

### 3.6 Agent/Admin

| API 묶음 | 목표 화면 | 상태 |
|---|---|---|
| Factory agents/templates/ai-recommend | AG-01/AG-02 | 연결 |
| Format CRUD | AG-02 | 연결 |
| Skill proposals approve/reject | AG-03 | 연결 |
| Benchmark evaluate/scorecard/golden/compare | AG-04 | 화면 신규 |
| ECM entities/nodes/edges/profiles | OR-01/OR-02 | 연결 |
| ECM entity clone/scenario | OR-01 | 아직 미구현 |
| Brand theme | OR-02/Shell | **신규 계약** |
| Org departments/users/roles | OR-03 | 연결 |
| Ledger event/history/verify | 전 화면 이력 | 연결 |
| Access audit query | OR-04 | 정책 확정 후 신규 |
| User preference read/update/reset | OR-05/Shell | **신규 계약** |
| Provider availability/model routing/budget | AG-04/Admin | Telemetry 연결 + 정책 API 신규 |
| Connector health/secret rotation metadata | KD-06/Admin | 상태 연결 + Vault 계약 신규 |
| Platform health/backup/recovery status | OR-04/OP-05 | **신규 읽기 계약** |

### 3.7 Collaboration

| API 묶음 | 목표 화면 | 상태 |
|---|---|---|
| app-deliveries create/inbox/outbox/detail/accept/reject/revoke | CL-01/CL-02 | **신규** |
| me/apps list/update | CL-02 | **신규** |
| simulations/{run_id}/decision-cases | DT-02/CL-03 | **신규** |
| decisions queue/detail/views/review/meeting/respond/decide/actions/effect | CL-03 | **신규** |
| publications create/list/detail/render/approval/publish/correct/withdraw | RP-04/CL-04 | **신규** |
| collaboration user-scoped event stream | CL-01~04/전역 알림 | **신규 또는 기존 SSE 보안 확장** |
| Decision Ledger append/history/verify | CL-01~04 감사 이력 | 연결·이벤트 추가 |

---

## 4. 신규 계약 우선순위

### P0 · 전역 문맥 헤더

현재 API 클라이언트마다 scope 인자가 다르게 전달된다. `lib/api.ts` 공통 계층에 검증된 `X-Enterprise-Scope`, `X-Entity-Mode`를 넣고, 비동기 응답의 현재 문맥 일치 여부를 확인해야 한다.

### P0 · Enterprise Canvas Aggregate

UI가 Factory, Planning, Knowledge, Telemetry 저장소를 직접 순차 호출하면 로딩·부분 실패·권한 해석이 제각각이 된다. 기존 저장소 위에 읽기 전용 집계를 만든다.

### P0 · Atlas Global

프로젝트 ID 의존 Supervisor Chat과 분리한다. Atlas는 Screen Context와 Evidence를 받되, 쓰기는 기존 도메인 API를 우회하지 않는다.

### P1 · Reference Approval/Indexing

현재 원본 등록부는 조회·재스캔까지만 있다. 승인 상태를 사람이 변경하고 승인된 자산만 지식팩에 색인하는 API가 필요하다.

### P1 · Company Brand Profile

회사/가상회사별 CI와 대표색을 Shell에 적용할 승인 가능한 프로필 계약이 필요하다.

### P1 · App-in-App Collaboration Contract

생성 앱은 호스트 인증·회사 문맥·역할·감사로그를 상속하고 자체 로그인·사용자 저장소·JWT를 만들지 않는다. 릴리스별 Capability Manifest, 개인 전달·수락·내 앱, 증거 고정형 Decision Package, 대내외 발간 게이트를 새 협업 도메인 계약으로 구현한다. 개인 전달은 기존 조직 단위 Workspace Share/Promotion과 합치지 않는다.

### P2 · Audit Read API

감사 로그의 보존·열람권한·마스킹 기준 확정 후 OR-04용 읽기 API를 만든다.

### P2 · Settings & Administration Aggregate

Admin 화면이 Org, ECM, Telemetry, Contract, Audit 저장소를 직접 수정하지 않도록 읽기 집계와 도메인별 명령 adapter를 분리한다. 개인 설정은 사용자 선호 저장소로 즉시 반영하고, 회사·권한·모델·연계·운영 변경은 `draft → impact_checked → review_requested → approved → scheduled/applied → rolled_back` 상태를 가진 변경 요청으로 전달한다.

---

## 5. Claude Code 현재 작업과의 충돌 방지

2026-07-30 공유 작업트리에는 Reference Dataset Registry와 Knowledge Hub 연계가 아직 커밋되지 않은 상태로 존재한다.

- 수정: `api/routes/knowledge_control.py`
- 수정: `frontend/src/components/KnowledgeHubPanel.tsx`
- 신규: `api/routes/reference_control.py`
- 신규: `core/reference_registry.py`
- 신규: `scripts/build_reference_inventory.py`
- 신규: `tests/test_reference_registry.py`
- 신규 데이터/문서: `data/reference_registry.json`, `docs/reference/REFERENCE_DATASET_REGISTER.md`

M6 UI 작업은 이 파일들을 덮어쓰지 않는다. Knowledge Hub를 교체할 때 다음 원칙을 지킨다.

1. Office 문서 추출 지원을 유지한다.
2. 원본 68건 등록부와 지식팩 CRUD를 동일 개념으로 합치지 않는다.
3. 미승인 원본의 자동 색인을 금지한다.
4. 현재 조회/재스캔 기능을 먼저 adapter로 연결하고 승인/색인은 후속 API 준비 후 활성화한다.

---

## 6. 구현 분할 제안

| 작업 ID | 산출물 | Claude Code 구현 범위 | Codex 검토 범위 |
|---|---|---|---|
| M6-UI-01 | AppShell·토큰·Context | Shell, route, provider, API interceptor | 시각·문맥·가독성 |
| M6-UI-01A | Company Universe | ECM tree/profile/scope, VIRTUAL copy wizard | 계층 이해·REAL/VIRTUAL 오독·격리 UX |
| M6-UI-02 | 경영 홈 Read-only | 승인 Master Concept 복원, Aggregate API, Briefing adapter | 정보 위계·의사결정 집중·Studio 기능 혼입 금지 |
| M6-UI-03 | Software Factory Studio | 독립 route, Advisor/Portfolio/Production/HOTL 이식 | 기능 손실·주 CTA·오류 UX·실행 중 이탈 보호 |
| M6-UI-03R | Reports | 구조화 문서 모델, Report Studio, Review/Trace/Export adapter | 가독성·근거·버전·승인 UX |
| M6-UI-03C | Collaboration | App-in-App 계약, 개인 전달·내 앱, Decision Package·회의, Publication Control | 개인/조직 공유 구분·권한 영향·3관점 정합성·대외 발간 게이트·Jarvis 문맥 |
| M6-UI-04 | Operate | Workspace/Promotion/Program/Shadow | 게이트 오독·영향 확인 |
| M6-UI-05 | Digital Twin Studio | 독립 route, Value Flow Sankey, Scenario Lab, Planning 화면 분해 | 숫자 오독·불완전성·영향경로·비교 UX |
| M6-UI-06 | Knowledge | Registry shell, current API adapters | 데이터 흐름·승인 UX |
| M6-UI-07A | Agent Studio | 독립 route, Agent Mesh Canvas, Template/Skill/Model/HOTL/Benchmark | 그래프·미저장 변경·비용·품질·복구 |
| M6-UI-07B | Administration | Settings Console, ECM/Profile/Access, Model/Cost, Integration/Operations gateway | 권한·브랜드·변경 영향·비밀정보 |
| M6-UI-08 | Atlas | 전역 API/rail/HOTL handoff, SW·Twin·보고서 공동설계 | 대화 품질·근거·제어·생성상담 UX |

각 작업은 자체검토 후 진행 가능하되, 권한·데이터 노출·경영수치·운영 승격 변경은 다른 팀원의 후속 교차검토 대상으로 TEAM_BOARD에 남긴다. 검토 대기 때문에 작업 전체를 멈추지는 않는다.

---

## 7. 회귀 방지 인수 체크

| 영역 | 반드시 보존할 계약 |
|---|---|
| Briefing | 불완전 소스가 숫자보다 위, 비용 하한 `≥` |
| Advisor | 추천 선택형 질문, 준비도 measurable max, 승인 후 프로젝트 생성 |
| Factory | HOTL, Quota 재개, 실패 종료, SSE 복구, Preview, WBS 재분할 |
| Collaboration | 개인 전달≠조직 공유≠업무 배정≠전사 승격, 수락 멱등성, 데이터 권한 비확대, 단일 Decision Package, 대외 이중 게이트 |
| Workspace | unverifiable 차단, 오너 승인, gate snapshot |
| Readiness | 롤백 한계와 change impact |
| Program | 삭제 대신 상태, dependents 409 확인 |
| Shadow | 동일 입력, 악화 인지, 범위 필수 |
| Planning | 값 종류 분리, 기준선, fingerprint, 현금 계산 불가, Backtest 위험 |
| Knowledge | 미승인 원본 자동색인 금지, Office 추출 |
| MDM | 범위·별칭·중복·유효기간 |
| Integration | Connector→Contract→Crosswalk→MCP, 권한 실패 은폐 |
| Quality | 실패 6원인+미분류, 사람 판정 3분리 |
| ECM | REAL/VIRTUAL/COMPETITOR 격리, OPERATING_PARENT만 권한 상속 |

---

## 8. 완료 판정

M6는 화면이 새 디자인처럼 보이는 것만으로 완료되지 않는다. 아래를 모두 충족해야 한다.

- 새 Shell에서 현재 기능 전체에 도달 가능.
- 기존 패널의 핵심 행동과 상태 계약이 보존됨.
- Enterprise Home에서 회사 범위 의사결정·업무·데이터·SW·Twin을 연결해 탐색 가능.
- Atlas가 Task ID 없이 현재 회사 문맥으로 답하고 근거·부족 데이터·실행 초안을 분리.
- 생성 앱 전달부터 수락·공동업무, 시뮬레이션부터 검토·회의·결정·실행·발간까지 객체 계보가 끊기지 않음.
- 앱 수락이 데이터 권한을 자동 확대하지 않고, 대외 발간은 책임 임원과 법무·공시의 이중 승인 전 차단됨.
- 권한 실패와 데이터 불완전성이 정상 상태로 보이지 않음.
- 기존 UI로 돌아갈 수 있는 카나리 fallback 유지.
- 주요 사용자 여정과 브라우저 과업 테스트 통과 후 기본 화면 전환.

---

## 9. P0 통합 프로토타입 구현 결과와 반려 이력 · 2026-07-31

### 9.1 구현 범위

| 작업 | 반영 결과 | 구현 파일 |
|---|---|---|
| 전역 제품 셸 | 기존 7개 메뉴 기준선과 신규 `협업` 메뉴, 회사 문맥, REAL 배지, Sample Data 고지, 설정·새 업무 CTA 통일 | `uiux-prototypes/product-shell.css` |
| 작업 보호 | 미저장 Draft·시나리오 및 실행 중 Factory의 전역 이탈 경고 | `uiux-prototypes/product-shell.js` |
| 경영 홈 | 업무축 수치 7개 일치, 진행 제품 2건 일치, 근거·Factory·Twin 실제 이동 | `uiux-prototypes/master-concept/index.html` |
| Software Factory R2 | 요구 입력·선택형 명확화·기획 산출물 Rail, 8단계 진행선, WBS, Agent Timeline, 실행화면/보고서/코드/추적성/품질, HOTL·복구·인계, Atlas Global Rail | `uiux-prototypes/revision-v2-2/factory/index.html` |
| Agent Studio R2 | Template Portfolio, 12개 노드 Graph, Agent Inspector, HOTL·복구·모델·비용·검증, Atlas Global Rail | `uiux-prototypes/revision-v2/v10/index.html` |
| Digital Twin R2 | 공통 밝은 제품 테마, 3개 Scenario, 4개 동인, KPI·Value Flow·영향 설명, 공식·출처·Backtest·승인, Atlas Global Rail | `uiux-prototypes/revision-v2/v9/index.html` |
| Studio 공통 계약 R2 | Task ID 없는 전역 Atlas 대화·추천·제어 요청, 공통 Rail 스타일과 상호작용 | `uiux-prototypes/studio-workspaces.css`, `uiux-prototypes/studio-atlas.js` |
| Reports·Knowledge·Operate·Admin | 동일 전역 셸로 M6 기능 화면에 연결 | `uiux-prototypes/m6-product-samples/index.html` |

### 9.2 제거한 임시 구조

`studio-nav.js`가 화면 위에 두 번째 전역 바를 주입하고 V10 본문을 실행 시 Agent 문구로 바꾸던 방식을 폐기했다. 각 Studio는 이제 원본 HTML 자체가 해당 업무 의미와 정보 구조를 가진다. 실제 React 이식 시에도 DOM 사후 치환이 아니라 `AppShell`, `CompanyContextBar`, route별 Studio Layout 컴포넌트로 구현한다.

### 9.3 브라우저 검증 결과

- 최초 P0는 시각 통일을 우선하면서 Factory의 요구 입력·WBS·Preview 작업 공간을 생산라인 개념도로 축약하고, 세 Studio의 Atlas를 하단 한 줄 브리핑으로 축소했다. Supervisor가 기능 손실·Twin 테마 부조화·Atlas 부재를 지적해 최종 기준선에서 제외했다.
- R2 Factory에서 업무 요구사항 입력, 선택형 명확화, 기획 산출물 6종, WBS 18개, Timeline, Artifact 5개 탭, 복구 1/3, Atlas Rail이 동시에 렌더링됨을 확인했다.
- R2 Agent에서 Template 6개, Agent Node 12개, Inspector, Atlas Rail을 확인했고 Atlas 빠른 질문 클릭 시 사용자/Agent 메시지와 비용 절감 답변이 정상 추가됐다.
- R2 Twin에서 공통 전역 셸·밝은 작업면·4개 동인·5개 KPI·Value Flow 6개 노드·근거·신뢰도·Atlas Rail을 확인했다.
- 세 Studio 모두 동일 회사 문맥과 메뉴 순서를 사용하고 Atlas에 `Task ID 없이 ... 대화 가능` 상태를 명시한다.

### 9.4 실제 React 이식 경계

이번 결과는 승인 디자인과 기능 배치를 검증하는 정적 기준선이다. `frontend/` 이식은 Claude Code가 담당하며 다음을 가짜 샘플 상태에서 실제 계약으로 교체해야 한다.

1. 전역 회사 문맥을 ECM Scope Resolver와 연결하고 모든 API 요청·응답에 같은 scope를 검증한다.
2. Factory 실행 보호를 실제 Sprint 상태·SSE·HOTL·종료 인계 상태와 연결한다.
3. Agent Graph를 Registry·Template API의 node/edge SSOT와 연결하고 Draft version을 저장한다.
4. Twin 수치를 Planning Baseline·Formula Registry·External Snapshot·Backtest 결과와 연결한다.
5. Report·Knowledge·Operate·Admin은 현재 M6 기능을 유지한 채 같은 AppShell route로 이식한다.

### 9.5 Supervisor 판정 · R2 확정 취소

R2 Factory는 요구 입력, 기획 산출물, Workflow, WBS, Timeline, Preview, 품질, 복구, Atlas를 네 개의 동시 열과 상단 상태에 모두 펼쳐 원본보다 복잡해졌다. 기능 문자열이 모두 존재하는 것은 사용성이 보존됐다는 뜻이 아니다. Supervisor 판정에 따라 R2 Factory는 실제 React 이식 기준에서 제외한다.

보존 기준선은 현재 React의 `WorkflowStrip + ControlPanel + TimelinePanel(Supervisor/HOTL) + PreviewPanel`이다. 개선은 이 구조를 폐기하지 않고 단계별 정보 노출과 집중 모드를 보완하는 방식으로 수행한다.

## 10. SW 생성기 전용 UI 비교안 · 2026-07-31

| 후보 | 구조 | 목적 | 경로 |
|---|---|---|---|
| A · Original Plus | 원본 Control / Supervisor / Preview 3패널 | 현재 구조의 최소 위험 정돈 | `uiux-prototypes/sw-factory-concepts/original-plus/` |
| B · Guided Journey | 5단계 신규 기획 + 준비도·Atlas 도움 | 처음 사용하는 현업 사용자의 요구·데이터 구체화 | `uiux-prototypes/sw-factory-concepts/guided-journey/` |
| C · Focus Workbench | 기획/WBS/실행/산출물/품질 탭 + Atlas Drawer | 산출물·실행 집중 작업과 낮은 정보 밀도 | `uiux-prototypes/sw-factory-concepts/focus-workbench/` |
| D · Transparent Orchestration | 전체 Workflow + WBS Spine + 현재 작업·산출물 + 중앙 하단 여백형 사용자 결정/Jarvis 상하 카드 + 우측 상태·실행 기록 | AI 진행을 암묵지로 만들지 않고 전체 연결·사용자 상호작용·현재 집중을 동시에 제공 | `uiux-prototypes/sw-factory-concepts/transparent-orchestration/` |

2026-07-31 재검토에서 `B 신규 생성 → C 집중 작업`만을 기본 구조로 삼는 권고를 철회했다. 사용자는 여러 Agent와 WBS가 어떤 의존관계로 무엇을 만들고 있는지 항상 확인할 수 있어야 한다. D를 기본 작업공간 후보로 두고 B의 선택형 안내와 C의 넓은 작업면은 D의 중앙 Focus Surface 모드로 흡수한다. A는 기능 회귀 검사와 통합 관제 참고 자료로 유지한다. 기능 보존·투명한 집중 기준은 `uiux-prototypes/sw-factory-concepts/README.md`를 SSOT로 사용한다.

## 11. 협업 폐쇄루프 승인 기준선 · 2026-08-03

Supervisor는 `uiux-prototypes/closed-loop-product-samples/`의 프로토타입 상태를 승인했다. 이 화면은 다음 제품 계약의 시각 기준선이며 실제 React·API 구현은 `docs/uiux/CLAUDE_IMPLEMENTATION_WORK_ORDER_CLOSED_LOOP_2026-08-03.md`를 따른다.

| 화면 | 승인된 핵심 | 실제 구현 교체 대상 |
|---|---|---|
| 사용자에게 전달 | 릴리스·수신자·최소권한·만료·플랫폼 인증 상속 확인 | 실제 사용자 검색, Release Manifest, 권한 영향 검사 |
| 받은 앱·내 앱 | 수락/거절, 내 앱 주머니, 보낸 요청 상태 | 개인 전달 DB/API, 멱등성, 회수·버전 상태 |
| 의사결정 센터 | 단일 Package, 요청자/결정자/영향부서 3관점, 회의 | Twin Snapshot, 참여자 응답, 결정·실행·효과측정 |
| 대내외 발간 | 대내/대외 분리, 근거·민감정보, 책임자+법무/공시 이중 게이트 | 구조화 Report, Redaction, 승인·게시·정정·회수 adapter |
| Jarvis | 모든 화면에서 회사·객체 문맥 유지 | 전역 Atlas API와 근거·실행 초안 계약 |

프로토타입의 샘플 사용자·수치·일정은 제품 데이터가 아니다. 실제 구현은 서버 권한을 SSOT로 사용하고 타 범위 자원 404 은폐, 사용자별 알림 필터, 명시적 외부 쓰기 확인을 회귀 테스트로 고정한다.
