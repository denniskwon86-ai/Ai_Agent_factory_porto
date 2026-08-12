# 기술·제품 용어 UI 전환 백로그

> 생성일: 2026-08-12  
> 성격: 자동 치환 목록이 아닌 사용자 노출 여부 확인용 후보 목록  
> 정본: `data/terminology/technology_terminology_glossary.json`

## 1. 실측 요약

- 검사 파일: **92개** (`frontend/src`의 TS·TSX·HTML)
- 등장한 전환 후보 용어: **53개**
- 정확 문자열 등장 위치: **1767건**
- 사용자 노출 유력: **71건** · 문자열 확인 필요: **412건**
- 기술 식별자 가능성: **1127건** · 주석: **157건**
- API 경로, 변수명, 타입명, 테스트 식별자는 이 목록만으로 변경하지 않습니다.

## 2. 적용 순서

1. `과거 별칭`이 실제 화면 문구로 노출되는 위치를 먼저 제거합니다.
2. 메뉴·페이지 제목·버튼·빈 상태·도움말 순으로 권장 용어를 적용합니다.
3. 로그·관리자 화면은 사용자 문구와 기술 식별자를 구분해 병기합니다.
4. 한 화면군씩 시각 검증 후 반영하며 일괄 검색·치환은 금지합니다.

## 3. 정확 문자열 후보

| 우선 | ID | 현재 용어 | 권장 사용자 용어 | 상태 | 노출 유력 | 전체 위치 |
|---:|---|---|---|---|---:|---:|
| 1 | `DEC-22` | Boardroom | 통합 프로젝트 관제 | 과거 별칭 | 0 | 4 |
| 2 | `ASST-02` | Atlas | Jarvis | 과거 별칭 | 0 | 3 |
| 3 | `PROD-20` | Vault | 프로젝트 보관함 | 과거 별칭 | 0 | 3 |
| 4 | `PROD-05` | Living Enterprise Canvas | 전사 경영 허브 | 과거 별칭 | 0 | 2 |
| 5 | `UI-06` | Data | 데이터 기반 | 권장안 | 4 | 219 |
| 6 | `AI-01` | Agent | AI 에이전트 | 권장안 | 6 | 207 |
| 7 | `PROD-17` | Project | 앱 제작 프로젝트 | 권장안 | 7 | 196 |
| 8 | `FLOW-09` | Stage | 작업 단계 | 권장안 | 5 | 158 |
| 9 | `ORG-12` | Scope | 접근 범위 | 권장안 | 2 | 153 |
| 10 | `FLOW-08` | Task | 작업 항목 | 권장안 | 13 | 151 |
| 11 | `FLOW-37` | Release | 릴리스 | 권장안 | 5 | 85 |
| 12 | `UI-01` | Enterprise | 전사 경영 허브 | 권장안 | 0 | 45 |
| 13 | `OPS-01` | Governance | 정책·통제 체계 | 권장안 | 3 | 43 |
| 14 | `PROD-16` | Program | 업무 프로그램 | 권장안 | 0 | 40 |
| 15 | `FLOW-32` | QA | 품질 검증 에이전트 | 권장안 | 9 | 38 |
| 16 | `DEC-16` | Publication | 보고서 발간 | 권장안 | 0 | 35 |
| 17 | `AI-09` | Skill | 에이전트 스킬 | 권장안 | 0 | 33 |
| 18 | `FLOW-38` | Promotion | 운영 자산 승격 | 권장안 | 0 | 30 |
| 19 | `UI-14` | Telemetry | 운영 계측 | 권장안 | 0 | 30 |
| 20 | `KNOW-05` | Evidence | 근거 자료 | 권장안 | 0 | 29 |
| 21 | `UI-07` | Agents | AI 에이전트 | 권장안 | 1 | 29 |
| 22 | `DATA-29` | PLAN | 계획 | 권장안 | 2 | 26 |
| 23 | `UI-05` | Knowledge | 전사 지식 허브 | 권장안 | 0 | 21 |
| 24 | `ASST-07` | Advisor | 업무·데이터 설계 상담 | 권장안 | 0 | 20 |
| 25 | `ASST-03` | Supervisor | 품질 감독 에이전트 | 권장안 | 1 | 18 |
| 26 | `FLOW-33` | Supervisor | 파이프라인 품질 감독 에이전트 | 권장안 | 1 | 18 |
| 27 | `PROD-19` | Workspace | 부서 업무공간 | 권장안 | 0 | 16 |
| 28 | `DATA-16` | Crosswalk | 코드·항목 연결표 | 권장안 | 1 | 14 |
| 29 | `UI-11` | Crosswalk | 코드·항목 연결표 | 권장안 | 1 | 14 |
| 30 | `UI-08` | Collaboration | 협업·의사결정 | 권장안 | 0 | 13 |
| 31 | `AI-13` | Workflow | AI 작업 흐름 | 권장안 | 0 | 10 |
| 32 | `FLOW-02` | Clarification | 요구사항 구체화 | 권장안 | 0 | 10 |
| 33 | `DEC-02` | Decision Package | 의사결정 검토서 | 권장안 | 2 | 8 |
| 34 | `UI-03` | Operate | 업무 앱 | 권장안 | 0 | 7 |
| 35 | `AI-07` | Agent Governance | 에이전트 자산 통제 | 권장안 | 3 | 6 |
| 36 | `DATA-22` | RAW | 수집 원본 | 권장안 | 0 | 5 |
| 37 | `OPS-25` | Traceability | 추적성 | 권장안 | 0 | 5 |
| 38 | `DATA-01` | MDM | 기준정보 관리 | 권장안 | 1 | 2 |
| 39 | `DATA-30` | FORECAST | 전망 | 권장안 | 0 | 2 |
| 40 | `DATA-31` | SCENARIO | 시나리오 | 권장안 | 1 | 2 |
| 41 | `FLOW-31` | Reviewer | 코드 품질 검토 에이전트 | 권장안 | 0 | 2 |
| 42 | `PROD-06` | Enterprise Canvas | 전사 경영 허브 | 권장안 | 0 | 2 |
| 43 | `TWIN-04` | Simulation | 경영 시뮬레이션 | 권장안 | 0 | 2 |
| 44 | `TWIN-13` | Benchmark | 비교 기준 | 권장안 | 2 | 2 |
| 45 | `AI-10` | Skill Evolution | AI 스킬 개선 | 권장안 | 0 | 1 |
| 46 | `DATA-05` | Reference Registry | 공식 근거 등록부 | 권장안 | 0 | 1 |
| 47 | `DATA-28` | ACTUAL | 실적 | 권장안 | 0 | 1 |
| 48 | `DEC-03` | Decision Ledger | 의사결정 원장 | 권장안 | 0 | 1 |
| 49 | `PROD-02` | 경영 시스템 | 제조 경영 시스템 | 권장안 | 0 | 1 |
| 50 | `PROD-18` | Mega Project | 통합 제작 프로젝트 | 권장안 | 1 | 1 |
| 51 | `RUN-04` | Capability Manifest | 앱 권한 선언서 | 권장안 | 0 | 1 |
| 52 | `UI-09` | Administration | 시스템 관리 | 권장안 | 0 | 1 |
| 53 | `UI-10` | Master Data | 기준정보 관리 | 권장안 | 0 | 1 |

## 4. 파일·줄 단위 확인 목록

### DEC-22 · Boardroom → 통합 프로젝트 관제

- **문자열 확인 필요** · `frontend/src/App.tsx:34` — `import MegaBoardroomPanel from './components/MegaBoardroomPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:34` — `import MegaBoardroomPanel from './components/MegaBoardroomPanel';`
- **기술 식별자 가능성** · `frontend/src/App.tsx:529` — `<MegaBoardroomPanel />`
- **기술 식별자 가능성** · `frontend/src/components/MegaBoardroomPanel.tsx:4` — `export default function MegaBoardroomPanel() {`

### ASST-02 · Atlas → Jarvis

- **주석** · `frontend/src/components/EnterprisePage.tsx:7` — `//   ⑤ 우측 회사 범위 Atlas               ⑥ 상단 회사·사업부·공장 Context`
- **주석** · `frontend/src/components/EnterprisePage.tsx:485` — `{/* ── ⑤ 우 360: Atlas (§4.7) ──────────────────────────────────────── */}`
- **기술 식별자 가능성** · `frontend/src/components/EnterprisePage.tsx:217` — `생겼다. §9.2 는 1024~1279 구간에서 「Decision Queue 또는 Atlas 를 drawer 로 전환」`

### PROD-20 · Vault → 프로젝트 보관함

- **주석** · `frontend/src/components/AdminConsolePanel.tsx:10` — `//   API Key·토큰은 **마스킹된 값도 재표시하지 않는다** — Vault 참조·연결 상태·마지막 교체일만`
- **주석** · `frontend/src/components/AdminConsolePanel.tsx:442` — `{/* ★★ [설계 §5.8] 「API Key·토큰은 **마스킹된 값도 재표시하지 않는다.** Vault`
- **기술 식별자 가능성** · `frontend/src/components/AdminConsolePanel.tsx:447` — `API Key·토큰은 <b>마스킹된 형태로도 다시 보여 주지 않습니다.</b> 화면에는 Vault`

### PROD-05 · Living Enterprise Canvas → 전사 경영 허브

- **주석** · `frontend/src/design/HubShell.tsx:1` — `// [UIUX] 허브 3열 셸 — 승인 시안(Living Enterprise Canvas)의 공용 레이아웃`
- **주석** · `frontend/src/features/collaboration/CollaborationHub.tsx:1` — `// [CL-1 · UIUX] 협업 허브 — 승인 시안(Living Enterprise Canvas) 기준선 위에서 동작하는 실제 화면`

### UI-06 · Data → 데이터 기반

- **사용자 노출 유력** · `frontend/src/components/FormatMasterPanel.tsx:195` — `<option value="json">JSON Data (Code Block)</option>`
- **사용자 노출 유력** · `frontend/src/components/PreviewPanel.tsx:705` — `setError(null); setDataBlocked(false); setHealOffered(false); setHealRequested(false);`
- **사용자 노출 유력** · `frontend/src/components/PreviewPanel.tsx:930` — `<button onClick={() => setDataBlocked(false)} className="shrink-0 text-sky-700 hover:text-sky-900 font-bold px-1" aria-label="이 안내 닫기">✕</button>`
- **사용자 노출 유력** · `frontend/src/lib/masterDataApi.ts:90` — `async function formRequest<T>(path: string, form: FormData): Promise<T> {`
- **문자열 확인 필요** · `frontend/src/App.tsx:26` — `import { MasterDataPanel } from './components/MasterDataPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:26` — `import { MasterDataPanel } from './components/MasterDataPanel';`
- **문자열 확인 필요** · `frontend/src/components/AdminConsolePanel.tsx:29` — `import { EmptyOrError, Refreshing, failed, loading, ok, refreshing, type Loaded } from '../design/DataState';`
- **문자열 확인 필요** · `frontend/src/components/AdminConsolePanel.tsx:30` — `import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';`
- **문자열 확인 필요** · `frontend/src/components/AdvisorPanel.tsx:3` — `import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';`
- **문자열 확인 필요** · `frontend/src/components/AdvisorPanel.tsx:4` — `import { EmptyOrError, failed, ok, type Loaded } from '../design/DataState';`
- **문자열 확인 필요** · `frontend/src/components/AgentAssetWizard.tsx:24` — `import { ConfirmInline, FormField } from '../design/DataFoundationShell';`
- **문자열 확인 필요** · `frontend/src/components/AgentGovernancePanel.tsx:26` — `import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';`
- **문자열 확인 필요** · `frontend/src/components/AgentGovernancePanel.tsx:27` — `import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:29` — `} from '../design/DataFoundationShell';`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:30` — `import { Metric, type Loaded } from '../design/DataState';`
- **문자열 확인 필요** · `frontend/src/components/BriefingPanel.tsx:20` — `import { EvidenceStrip, FoundationToolbar } from '../design/DataFoundationShell';`
- **문자열 확인 필요** · `frontend/src/components/BriefingPanel.tsx:21` — `import { Metric, failed, loading, ok, type Loaded } from '../design/DataState';`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:44` — `if (!templateData || !templateData.agents || templateData.id === 'default') {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:44` — `if (!templateData || !templateData.agents || templateData.id === 'default') {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:44` — `if (!templateData || !templateData.agents || templateData.id === 'default') {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:75` — `if (!templateData || templateData.id === 'default') {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:75` — `if (!templateData || templateData.id === 'default') {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:97` — `const [masterData, setMasterData] = useState("");`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:97` — `const [masterData, setMasterData] = useState("");`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:134` — `setMasterData(prev => prev ? prev + "\n\n" + content : content);`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:160` — `const isDynamic = currentTemplateData && currentTemplateData.agents && currentTemplateData.id !== 'default' && currentTemplateData.pipeline_name !== '소프트웨어 개발 팩토리';`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:160` — `const isDynamic = currentTemplateData && currentTemplateData.agents && currentTemplateData.id !== 'default' && currentTemplateData.pipeline_name !== '소프트웨어 개발 팩토리';`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:160` — `const isDynamic = currentTemplateData && currentTemplateData.agents && currentTemplateData.id !== 'default' && currentTemplateData.pipeline_name !== '소프트웨어 개발 팩토리';`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:160` — `const isDynamic = currentTemplateData && currentTemplateData.agents && currentTemplateData.id !== 'default' && currentTemplateData.pipeline_name !== '소프트웨어 개발 팩토리';`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:162` — `const coreTasks = wbsData?.tasks?.filter((t: any) => !t.task_id?.startsWith('TASK_REV_')) || [];`
- 그 외 189건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### AI-01 · Agent → AI 에이전트

- **사용자 노출 유력** · `frontend/src/App.tsx:228` — `{ id: 'agent-gov', icon: '🏛', label: 'Agent Governance Center',`
- **사용자 노출 유력** · `frontend/src/components/AgentGovernancePanel.tsx:240` — `<HubDialog label="Agent Governance Center — 조직 자산의 범위·권한·승인" onClose={onClose}>`
- **사용자 노출 유력** · `frontend/src/components/AgentGovernancePanel.tsx:242` — `<b>Agent Governance Center</b>`
- **사용자 노출 유력** · `frontend/src/components/AgentMasterPanel.tsx:551` — `<button className="text-button" onClick={() => fetchAgentRegistry()}>다시 시도</button>`
- **사용자 노출 유력** · `frontend/src/components/SkillEvolutionPanel.tsx:274` — `<h4>영향 Agent<em>같은 스킬 파일을 쓰는 에이전트</em></h4>`
- **사용자 노출 유력** · `frontend/src/components/TimelinePanel.tsx:127` — `<div className="text-[10px] text-gray-500 mb-2 font-bold tracking-wider">✅ COMPLETED AGENTS ({completedAgents.length})</div>`
- **문자열 확인 필요** · `frontend/src/App.tsx:12` — `import AgentMasterPanel from './components/AgentMasterPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:12` — `import AgentMasterPanel from './components/AgentMasterPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:40` — `import { AgentGovernancePanel } from './components/AgentGovernancePanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:40` — `import { AgentGovernancePanel } from './components/AgentGovernancePanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:627` — `⚠️ 이 면책은 **Studio 에만** 해당한다. 바로 위 \`AgentGovernancePanel\` 은 양쪽에`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:51` — `updateAgent(agent.id, "role", data.role);`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:52` — `updateAgent(agent.id, "skill", data.skill);`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:83` — `onClick={() => updateAgent(agent.id, "enabled", !agent.enabled)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:94` — `onChange={(e) => updateAgent(agent.id, "name_ko", e.target.value)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:104` — `onChange={(e) => updateAgent(agent.id, "role", e.target.value)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:124` — `onChange={(e) => updateAgent(agent.id, "skill", e.target.value)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:133` — `onChange={(e) => updateAgent(agent.id, "stage", e.target.value)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:145` — `onChange={(e) => updateAgent(agent.id, "model_tier", e.target.value)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:157` — `onChange={(e) => updateAgent(agent.id, "order", parseInt(e.target.value) || 0)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:171` — `onChange={(e) => updateAgent(agent.id, "output_format", e.target.value)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:192` — `onClick={() => updateAgent(agent.id, "is_start", !agent.is_start)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:198` — `onClick={() => updateAgent(agent.id, "is_end", !agent.is_end)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:211` — `onClick={() => updateAgent(agent.id, "hotl_after", !agent.hotl_after)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:217` — `onClick={() => updateAgent(agent.id, "debate", !agent.debate)}`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentNode.tsx:38` — `{data.name_ko || "Unnamed Agent"}`
- **문자열 확인 필요** · `frontend/src/components/AgentGovernancePanel.tsx:38` — `import { AgentAssetWizard } from './AgentAssetWizard';`
- **문자열 확인 필요** · `frontend/src/components/AgentGovernancePanel.tsx:38` — `import { AgentAssetWizard } from './AgentAssetWizard';`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:24` — `import AgentDetailSidebar from './AgentFlow/AgentDetailSidebar';`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:24` — `import AgentDetailSidebar from './AgentFlow/AgentDetailSidebar';`
- 그 외 177건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### PROD-17 · Project → 앱 제작 프로젝트

- **사용자 노출 유력** · `frontend/src/App.tsx:547` — `<span className="text-blue-400 truncate">[{projects.find(p => p.id === currentProjectId)?.name || currentProjectId}]</span> 통제실`
- **사용자 노출 유력** · `frontend/src/App.tsx:547` — `<span className="text-blue-400 truncate">[{projects.find(p => p.id === currentProjectId)?.name || currentProjectId}]</span> 통제실`
- **사용자 노출 유력** · `frontend/src/components/BuildStartDialog.tsx:97` — `<span style={label}>Project ID (영문)</span>`
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:231` — `if (!currentProjectId) return alert("프로젝트가 선택되지 않았습니다.");`
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:269` — `const html = \`<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>WBS · ${esc(currentProjectId)}</title>\``
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:275` — `+ \`<h1>📋 전체 WBS — ${esc(currentProjectId)} <span style="color:#64748b;font-weight:400">(${tasks.length}개 태스크)</span></h1>\``
- **사용자 노출 유력** · `frontend/src/components/MegaBoardroomPanel.tsx:47` — `return <div className="p-10 text-gray-100 text-center">Not a Mega Project</div>;`
- **문자열 확인 필요** · `frontend/src/App.tsx:319` — `if (!currentProjectId && space === 'enterprise') {`
- **문자열 확인 필요** · `frontend/src/components/AdvisorPanel.tsx:127` — `const [projectId, setProjectId] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/BuildStartDialog.tsx:37` — `const [projectId, setProjectId] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/BuildStartDialog.tsx:49` — `setErr('Project ID 는 영문·숫자·\`.\`·\`_\`·\`-\` 로 2자 이상이어야 합니다.');`
- **문자열 확인 필요** · `frontend/src/components/BuildStartDialog.tsx:99` — `onChange={(e) => { setProjectId(e.target.value); setErr(''); }}`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:297` — `const res = await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/start\`, {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:335` — `await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/start\`, {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:360` — `await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/pause\`, {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:398` — `const res = await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/revision\`, {`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:792` — `a.href = \`${API_BASE_URL}/api/v1/factory/${currentProjectId}/export\`;`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:793` — `a.download = \`${currentProjectId}.zip\`;`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:823` — `const res = await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/resimulate\`, {`
- **문자열 확인 필요** · `frontend/src/components/HOTLInput.tsx:89` — `const response = await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/hotl/resume\`, {`
- **문자열 확인 필요** · `frontend/src/components/HOTLInput.tsx:112` — `const response = await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/supervisor/chat\`, {`
- **문자열 확인 필요** · `frontend/src/components/MegaBoardroomPanel.tsx:55` — `const res = await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/mega/start_all\`, {`
- **문자열 확인 필요** · `frontend/src/components/MegaBoardroomPanel.tsx:92` — `<button onClick={() => setCurrentProject(null)} className="text-sm font-bold text-purple-200 hover:text-white bg-purple-800 px-3 py-1.5 rounded transition-colors">`
- **문자열 확인 필요** · `frontend/src/components/MegaBoardroomPanel.tsx:147` — `const res = await fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/mega/plan\`, {`
- **문자열 확인 필요** · `frontend/src/components/MegaBoardroomPanel.tsx:194` — `<button onClick={() => setCurrentProject(projId as string)} className="w-full mt-auto bg-gray-700 hover:bg-blue-600 text-white font-bold py-2 rounded transition-colors text-sm">`
- **문자열 확인 필요** · `frontend/src/components/TelemetryPanel.tsx:30` — `import { telemetryApi, type TelemetryProject, type TelemetrySummary } from '../lib/telemetryApi';`
- **문자열 확인 필요** · `frontend/src/components/TelemetryPanel.tsx:57` — `const [project, setProject] = useState('');            // '' = 전역`
- **문자열 확인 필요** · `frontend/src/components/TraceabilityGraph.tsx:19` — `fetch(\`${API_BASE_URL}/api/v1/factory/${currentProjectId}/traceability\`)`
- **문자열 확인 필요** · `frontend/src/components/TraceabilityGraph.tsx:32` — `if (!currentProjectId) return <div className="p-4 text-gray-400">프로젝트를 선택하세요.</div>;`
- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:148` — `const [projectId, setProjectId] = useState('');`
- 그 외 166건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### FLOW-09 · Stage → 작업 단계

- **사용자 노출 유력** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:260` — `<h3>{shownStageLabel || '이 단계'}의 작업면은 아직 이 화면에 없습니다</h3>`
- **사용자 노출 유력** · `frontend/src/factory/AdaptiveProductionStudio.tsx:111` — `<b>{shownStage ? shownStage.label : '제작 작업면'}</b>`
- **사용자 노출 유력** · `frontend/src/factory/AdaptiveProductionStudio.tsx:111` — `<b>{shownStage ? shownStage.label : '제작 작업면'}</b>`
- **사용자 노출 유력** · `frontend/src/factory/ContextInspector.tsx:67` — `<b>{shownStageLabel || '단계 미선택'}</b>`
- **사용자 노출 유력** · `frontend/src/factory/ContextInspector.tsx:112` — `순서상 다음은 <b>{inspect.nextStage.label}</b>입니다.`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:169` — `const legacyStages = ["RFP", "PLANNING", "TECH_SPEC", "CODE_REVIEW", "QA", "END"];`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:170` — `const curIdx = legacyStages.indexOf(state?.current_stage || "RFP");`
- **문자열 확인 필요** · `frontend/src/components/WorkStandardPanel.tsx:72` — `const [selectedStage, setSelectedStage] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/WorkStandardPanel.tsx:72` — `const [selectedStage, setSelectedStage] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/WorkStandardPanel.tsx:125` — `setSelectedStage(''); setDetail(ok(null)); setHist(ok<HistoryRow[]>([]));`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:23` — `import { ReleaseCanvas, StageArtifactCanvas } from './StageArtifactCanvas';`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:23` — `import { ReleaseCanvas, StageArtifactCanvas } from './StageArtifactCanvas';`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:257` — `const plan = NOT_YET_PLAN[(shownStageId || '').toUpperCase()];`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:32` — `import { ProductionStageMap } from './ProductionStageMap';`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:32` — `import { ProductionStageMap } from './ProductionStageMap';`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:54` — `const [selectedStageId, setSelectedStageId] = useState('');`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:54` — `const [selectedStageId, setSelectedStageId] = useState('');`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:101` — `onSelectStage={(id) => setSelectedStageId((prev) => (prev === id ? '' : id))}`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:101` — `onSelectStage={(id) => setSelectedStageId((prev) => (prev === id ? '' : id))}`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:145` — `vm.stages.find((s) => s.id === vm.currentStageId)?.label || '아직 없습니다'`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:154` — `shownStageLabel={shownStage?.label || ''}`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:154` — `shownStageLabel={shownStage?.label || ''}`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:167` — `shownStageLabel={shownStage?.label || ''}`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:167` — `shownStageLabel={shownStage?.label || ''}`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:179` — `shownStageLabel={shownStage?.label || ''}`
- **문자열 확인 필요** · `frontend/src/factory/AdaptiveProductionStudio.tsx:179` — `shownStageLabel={shownStage?.label || ''}`
- **문자열 확인 필요** · `frontend/src/factory/ContextInspector.tsx:71` — `vm.stages.find((s) => s.id === vm.currentStageId)?.label || '없습니다'`
- **문자열 확인 필요** · `frontend/src/factory/DecisionJarvisDock.tsx:132` — `stage_status: vm.stages.find((s) => s.id === shownStageId)?.status || '',`
- **문자열 확인 필요** · `frontend/src/factory/DecisionJarvisDock.tsx:170` — `: (decision.prompt || \`«${shownStageLabel || decision.impact}» 단계의 산출물을 검토하고 승인해야 합니다.\`)}`
- **문자열 확인 필요** · `frontend/src/factory/DecisionJarvisDock.tsx:206` — `? \`«${shownStageLabel}» 문맥으로 답합니다\``
- 그 외 128건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### ORG-12 · Scope → 접근 범위

- **사용자 노출 유력** · `frontend/src/components/WorkspacePanel.tsx:329` — `<b>{current?.from_scope || fromScope || '미지정'}</b></div>`
- **사용자 노출 유력** · `frontend/src/components/WorkspacePanel.tsx:421` — `changes={<>{releaseId} 가 <b>{current?.from_scope || fromScope || '이 조직'}</b>`
- **문자열 확인 필요** · `frontend/src/App.tsx:39` — `import { actingScope, governanceBlockReason, type ActingScope } from './lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/App.tsx:39` — `import { actingScope, governanceBlockReason, type ActingScope } from './lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/App.tsx:39` — `import { actingScope, governanceBlockReason, type ActingScope } from './lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/AdminConsolePanel.tsx:122` — `setPolicy(p.status === 'fulfilled' ? ok(p.value) : failed<ScopePolicy>(p.reason));`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:35` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:35` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:35` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/BriefingPanel.tsx:113` — `const [scopeNode, setScopeNode] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/GovernanceConsole.tsx:31` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/GovernanceConsole.tsx:31` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/GovernanceConsole.tsx:31` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/GovernanceConsole.tsx:87` — `const [scopeNode, setScopeNode] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/MasterDataPanel.tsx:77` — `const [previewScope, setPreviewScope] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/MasterDataPanel.tsx:77` — `const [previewScope, setPreviewScope] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/OrgChartPanel.tsx:34` — `import { orgApi, type Dept, type MyScope, type OrgEdge, type OrgUser } from '../lib/orgApi';`
- **문자열 확인 필요** · `frontend/src/components/OrgChartPanel.tsx:96` — `const [scopeDraft, setScopeDraft] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/OrgChartPanel.tsx:129` — `setMe(m.status === 'fulfilled' ? ok(m.value) : failed<MyScope | null>(m.reason));`
- **문자열 확인 필요** · `frontend/src/components/OrgChartPanel.tsx:187` — `useEffect(() => { setScopeDraft(selectedDept?.scope_node_id || ''); }, [selDept, selectedDept]);`
- **문자열 확인 필요** · `frontend/src/components/ShadowModePanel.tsx:80` — `const [scopeText, setScopeText] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/ShadowModePanel.tsx:104` — `setMsg(''); setErr(''); setAck(new Set()); setScopeText('');`
- **문자열 확인 필요** · `frontend/src/components/SkillEvolutionPanel.tsx:22` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/SkillEvolutionPanel.tsx:22` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/SkillEvolutionPanel.tsx:22` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/WorkStandardPanel.tsx:35` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/WorkStandardPanel.tsx:35` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/WorkStandardPanel.tsx:35` — `import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';`
- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:149` — `const [fromScope, setFromScope] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:149` — `const [fromScope, setFromScope] = useState('');`
- 그 외 123건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### FLOW-08 · Task → 작업 항목

- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:276` — `+ \`<table><thead><tr><th>#</th><th>Task ID</th><th>태스크</th><th>상태</th><th>배정 에이전트</th><th>Sprint Day</th></tr></thead>\``
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:327` — `if (!confirm(\`[${targetTask.task_id}] ${targetTask.title}\n해당 스프린트를 가동/재가동하시겠습니까?\`)) return;`
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:327` — `if (!confirm(\`[${targetTask.task_id}] ${targetTask.title}\n해당 스프린트를 가동/재가동하시겠습니까?\`)) return;`
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:374` — `if (!suspendedTaskId) return alert("재가동할 보류 태스크 정보가 없습니다. 페이지를 새로고침해 주세요.");`
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:707` — `<span className="text-xs font-bold text-blue-400">진척률: {progressPercent}% ({doneTasks}/{totalTasks})</span>`
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:707` — `<span className="text-xs font-bold text-blue-400">진척률: {progressPercent}% ({doneTasks}/{totalTasks})</span>`
- **사용자 노출 유력** · `frontend/src/components/HOTLInput.tsx:71` — `alert("🚨 재개할 타겟 태스크(Task ID)를 찾을 수 없습니다.");`
- **사용자 노출 유력** · `frontend/src/components/HOTLInput.tsx:144` — `<span className="text-xs text-gray-400">Target Task: {currentTask || "알 수 없음"}</span>`
- **사용자 노출 유력** · `frontend/src/components/HOTLInput.tsx:144` — `<span className="text-xs text-gray-400">Target Task: {currentTask || "알 수 없음"}</span>`
- **사용자 노출 유력** · `frontend/src/components/TraceabilityGraph.tsx:46` — `<span className="text-lg font-bold text-purple-400">Task: {m.task_id}</span>`
- **사용자 노출 유력** · `frontend/src/factory/ContextInspector.tsx:77` — `선택한 작업 <b>{selectedTask.id}</b> {selectedTask.title}`
- **사용자 노출 유력** · `frontend/src/factory/ContextInspector.tsx:77` — `선택한 작업 <b>{selectedTask.id}</b> {selectedTask.title}`
- **사용자 노출 유력** · `frontend/src/factory/ContextInspector.tsx:101` — `<b>{inspect.suspendedTaskId}</b> 이(가) 쿼터 소진으로 동결됐습니다 — 쿼터가 회복되면`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:80` — `if (n.id === 'manualwriter') return isFinalTask;`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:81` — `if (n.id === 'qa') return has('QA') || isFinalTask;`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:162` — `const coreTasks = wbsData?.tasks?.filter((t: any) => !t.task_id?.startsWith('TASK_REV_')) || [];`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:164` — `let doneTasks = coreTasks.filter((t: any) => t.status === 'DONE').length;`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:164` — `let doneTasks = coreTasks.filter((t: any) => t.status === 'DONE').length;`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:346` — `factory_mode: targetTask.task_id.startsWith('TASK_REV_') ? "REVISION" : "EXECUTION",`
- **문자열 확인 필요** · `frontend/src/components/HOTLInput.tsx:116` — `task_id: currentTask || "",  // 자비스 모드: 태스크 없이도 시스템 전체 질문 가능`
- **문자열 확인 필요** · `frontend/src/factory/ContextInspector.tsx:78` — `{selectedTask.agent && \` · 담당 ${selectedTask.agent}\`}`
- **문자열 확인 필요** · `frontend/src/factory/ContextInspector.tsx:78` — `{selectedTask.agent && \` · 담당 ${selectedTask.agent}\`}`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:468` — `const hotlAgent = String(snap.hotlTaskId || '').toLowerCase();`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:511` — `&& String(snap.hotlTaskId) === String(t?.task_id ?? '');`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:512` — `const kind: FactoryWbsKind = isTaskDone(t?.status) ? 'done'`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:514` — `: isTaskActive(t?.status) ? 'active'`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:628` — `suspendedTaskId: snap.isSuspendedQuota ? String(snap.suspendedTaskId || '') : '',`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:628` — `suspendedTaskId: snap.isSuspendedQuota ? String(snap.suspendedTaskId || '') : '',`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:639` — `label: snap.hotlTaskId ? '사용자 결정 대기'`
- **주석** · `frontend/src/components/ControlPanel.tsx:416` — `// 이 태스크에 배정된 에이전트만으로 파이프라인 구성 (PMO Task별 매핑 반영)`
- 그 외 121건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### FLOW-37 · Release → 릴리스

- **사용자 노출 유력** · `frontend/src/App.tsx:304` — `📦 결과물 실행: <span className="text-emerald-400">{viewingRelease.project_name}</span>`
- **사용자 노출 유력** · `frontend/src/App.tsx:305` — `<span className="text-xs text-gray-500 font-normal ml-2">{viewingRelease.created_at}</span>`
- **사용자 노출 유력** · `frontend/src/components/BuildPage.tsx:33` — `{ id: 'releases', label: 'Releases', hint: '완성되어 전달 가능한 결과물' },`
- **사용자 노출 유력** · `frontend/src/factory/RunControls.tsx:189` — `<Btn label="Release 저장" why={releaseWhy} busy={busy === 'Release 저장 중'}`
- **사용자 노출 유력** · `frontend/src/factory/RunControls.tsx:189` — `<Btn label="Release 저장" why={releaseWhy} busy={busy === 'Release 저장 중'}`
- **문자열 확인 필요** · `frontend/src/App.tsx:302` — `<button onClick={closeRelease} className="text-sm font-bold text-gray-400 hover:text-gray-100 bg-gray-700 px-3 py-1.5 rounded transition-colors shrink-0">◀ 라이브러리</button>`
- **문자열 확인 필요** · `frontend/src/App.tsx:310` — `<PreviewPanel rawCode={viewingRelease.frontend_code_summary || ""} release={viewingRelease} />`
- **문자열 확인 필요** · `frontend/src/App.tsx:310` — `<PreviewPanel rawCode={viewingRelease.frontend_code_summary || ""} release={viewingRelease} />`
- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:147` — `const [releaseId, setReleaseId] = useState('');`
- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:287` — `onChange={(e) => setReleaseId(e.target.value)} placeholder="release_id" />`
- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:439` — `() => promoteRelease(releaseId), '전사 승격했습니다.'))} />`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:23` — `import { ReleaseCanvas, StageArtifactCanvas } from './StageArtifactCanvas';`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:251` — `if (kind === 'release') return <ReleaseCanvas vm={vm} />;`
- **문자열 확인 필요** · `frontend/src/factory/RunControls.tsx:128` — `const doRelease = () => guard('Release 저장 중', async () => {`
- **문자열 확인 필요** · `frontend/src/factory/RunControls.tsx:128` — `const doRelease = () => guard('Release 저장 중', async () => {`
- **문자열 확인 필요** · `frontend/src/factory/RunControls.tsx:135` — `? { tone: 'ok', text: \`Release 를 저장했습니다 — ${r.releaseId}\` }`
- **문자열 확인 필요** · `frontend/src/factory/RunControls.tsx:136` — `: { tone: 'bad', text: r.message || 'Release 를 저장하지 못했습니다.' });`
- **문자열 확인 필요** · `frontend/src/factory/RunControls.tsx:190` — `onClick={doRelease} hint="현재 산출물을 하나의 릴리스로 묶어 보관합니다." />`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:159` — `export const rollbackRelease = (releaseId: string, reason: string, toReleaseId = '') =>`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:159` — `export const rollbackRelease = (releaseId: string, reason: string, toReleaseId = '') =>`
- **주석** · `frontend/src/App.tsx:64` — `// deleteRelease 는 더 이상 목록에서 쓰지 않는다 — 서버가 삭제를 거부하고 사용 중단을`
- **주석** · `frontend/src/components/BuildPage.tsx:6` — `// · 본문: **미완료 / 내 프로젝트 / Mega / Releases / Archive**`
- **주석** · `frontend/src/components/ControlPanel.tsx:770` — `// ⚠️ \`saveRelease\` 는 이제 **이유를 담은 객체**를 돌려준다. \`if (r)\` 로 검사하면`
- **주석** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:12` — `* 아키텍처·WBS·검증·Release)는 §7-6 의 순차 이식 대상이다.`
- **주석** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:234` — `* ★ [6단계] 기본 14단계는 이제 모두 Canvas 를 갖는다(요구 확인 · 구현 · WBS · Release ·`
- **주석** · `frontend/src/factory/AdaptiveProductionStudio.tsx:34` — `// [7단계 전제] 실행 통제 — 시작·재개·복구·재분할·Release. §8 기능 게이트가 요구한다.`
- **주석** · `frontend/src/factory/ProjectHeader.tsx:10` — `* 「Sprint 시작·일시정지·정지·재개·복구·재분할·Release·Export 가 보존된다」를 요구한다. 즉`
- **주석** · `frontend/src/factory/RunControls.tsx:2` — `* [트랙 E · 7단계 전제] 실행 통제 — Sprint 시작 · 재개 · 복구 · WBS 재분할 · Release 저장.`
- **주석** · `frontend/src/factory/RunControls.tsx:4` — `* 근거: 구현 명세 §8 **기능 게이트** — 「Sprint 시작·일시정지·정지·재개·복구·재분할·Release·`
- **주석** · `frontend/src/factory/RunControls.tsx:127` — `// ── Release 저장 ─────────────────────────────────────────────────────────`
- 그 외 55건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### UI-01 · Enterprise → 전사 경영 허브

- **문자열 확인 필요** · `frontend/src/App.tsx:41` — `import { EnterprisePage } from './components/EnterprisePage';`
- **문자열 확인 필요** · `frontend/src/App.tsx:41` — `import { EnterprisePage } from './components/EnterprisePage';`
- **문자열 확인 필요** · `frontend/src/components/AgentAssetWizard.tsx:28` — `import { getEnterpriseContext } from '../lib/api';`
- **문자열 확인 필요** · `frontend/src/components/AgentAssetWizard.tsx:125` — `if (d.visibility === 'ENTERPRISE' && !canPublishEnterprise) {`
- **문자열 확인 필요** · `frontend/src/components/AgentAssetWizard.tsx:264` — `{d.visibility === 'ENTERPRISE' && !canPublishEnterprise && (`
- **문자열 확인 필요** · `frontend/src/components/AgentGovernancePanel.tsx:31` — `import { getEnterpriseContext } from '../lib/api';`
- **문자열 확인 필요** · `frontend/src/components/CompanyContextBar.tsx:15` — `import { getEnterpriseContext, setEnterpriseContext } from '../lib/api';`
- **문자열 확인 필요** · `frontend/src/components/CompanyContextBar.tsx:15` — `import { getEnterpriseContext, setEnterpriseContext } from '../lib/api';`
- **문자열 확인 필요** · `frontend/src/components/EnterprisePage.tsx:29` — `import { getEnterpriseContext } from '../lib/api';`
- **문자열 확인 필요** · `frontend/src/design/HubDialog.tsx:22` — `import { getEnterpriseContext } from '../lib/api';`
- **문자열 확인 필요** · `frontend/src/lib/api.ts:95` — `const TENANT_HEADER = 'X-Enterprise-Tenant';`
- **문자열 확인 필요** · `frontend/src/lib/api.ts:96` — `const SCOPE_HEADER = 'X-Enterprise-Scope';`
- **문자열 확인 필요** · `frontend/src/lib/api.ts:107` — `const EMPTY_CTX: EnterpriseContextSelection = { tenantId: '', scopeNodeId: '', entityMode: '' };`
- **문자열 확인 필요** · `frontend/src/store/useFactoryStore.ts:156` — `import { getEnterpriseContext, getSessionToken } from '../lib/api';`
- **문자열 확인 필요** · `frontend/src/store/useFactoryStore.ts:944` — `body: JSON.stringify({ scope_node_id: getEnterpriseContext().scopeNodeId || '' }),`
- **주석** · `frontend/src/components/EnterprisePage.tsx:5` — `//   ① 좌측 역할 기반 의사결정 대기열     ② 중앙 Enterprise Digital Thread`
- **주석** · `frontend/src/components/EnterprisePage.tsx:96` — `/** §4.3 EnterpriseThreadCanvas — 업무 노드.`
- **주석** · `frontend/src/components/EnterprisePage.tsx:303` — `{/* ── ② Enterprise Digital Thread + ③ DATA/SW/TWIN 레이어 ───────── */}`
- **주석** · `frontend/src/components/OrgChartPanel.tsx:778` — `/** [UI 설계서 §5.8 Enterprise Structure] 의미 그래프 — 소유·운영·공유·연결.`
- **주석** · `frontend/src/design/HubShell.tsx:1` — `// [UIUX] 허브 3열 셸 — 승인 시안(Living Enterprise Canvas)의 공용 레이아웃`
- **주석** · `frontend/src/features/collaboration/CollaborationHub.tsx:1` — `// [CL-1 · UIUX] 협업 허브 — 승인 시안(Living Enterprise Canvas) 기준선 위에서 동작하는 실제 화면`
- **주석** · `frontend/src/lib/actingScope.ts:105` — `*   \`canEditOrg\`·\`canRunEnterprise\`)와 문구는 \`api/deps.governance_block_reason\` 과 **같아야**`
- **주석** · `frontend/src/lib/advisorApi.ts:10` — `// ECM 문맥 헤더(X-Enterprise-Scope 등)는 전역 컨텍스트 스위처가 생기면 인터셉터에 추가한다 —`
- **주석** · `frontend/src/lib/api.ts:86` — `// ★★ 서버는 이미 \`X-Enterprise-Tenant\` · \`X-Enterprise-Scope\` · \`X-Entity-Mode\` 를 읽는다`
- **주석** · `frontend/src/lib/api.ts:86` — `// ★★ 서버는 이미 \`X-Enterprise-Tenant\` · \`X-Enterprise-Scope\` · \`X-Entity-Mode\` 를 읽는다`
- **주석** · `frontend/src/lib/orgApi.ts:121` — `/** [설계 §5.8 Enterprise Structure] 의미 그래프 — 소유·운영·공유·연결 관계.`
- **기술 식별자 가능성** · `frontend/src/App.tsx:338` — `<EnterprisePage`
- **기술 식별자 가능성** · `frontend/src/components/AgentAssetWizard.tsx:104` — `const ctx = getEnterpriseContext();`
- **기술 식별자 가능성** · `frontend/src/components/AgentAssetWizard.tsx:113` — `const canPublishEnterprise = Boolean(caps?.can_publish_enterprise);`
- **기술 식별자 가능성** · `frontend/src/components/AgentGovernancePanel.tsx:210` — `const ctx = getEnterpriseContext();`
- 그 외 15건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### OPS-01 · Governance → 정책·통제 체계

- **사용자 노출 유력** · `frontend/src/App.tsx:228` — `{ id: 'agent-gov', icon: '🏛', label: 'Agent Governance Center',`
- **사용자 노출 유력** · `frontend/src/components/AgentGovernancePanel.tsx:240` — `<HubDialog label="Agent Governance Center — 조직 자산의 범위·권한·승인" onClose={onClose}>`
- **사용자 노출 유력** · `frontend/src/components/AgentGovernancePanel.tsx:242` — `<b>Agent Governance Center</b>`
- **문자열 확인 필요** · `frontend/src/App.tsx:13` — `import GovernanceConsole from './components/GovernanceConsole';`
- **문자열 확인 필요** · `frontend/src/App.tsx:13` — `import GovernanceConsole from './components/GovernanceConsole';`
- **문자열 확인 필요** · `frontend/src/App.tsx:40` — `import { AgentGovernancePanel } from './components/AgentGovernancePanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:40` — `import { AgentGovernancePanel } from './components/AgentGovernancePanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:627` — `⚠️ 이 면책은 **Studio 에만** 해당한다. 바로 위 \`AgentGovernancePanel\` 은 양쪽에`
- **문자열 확인 필요** · `frontend/src/components/AgentAssetWizard.tsx:31` — `} from '../lib/agentGovernanceApi';`
- **문자열 확인 필요** · `frontend/src/components/AgentGovernancePanel.tsx:36` — `} from '../lib/agentGovernanceApi';`
- **문자열 확인 필요** · `frontend/src/lib/governanceApi.ts:25` — `const e = new Error(j?.detail || \`요청 실패 (${r.status})\`) as GovernanceError;`
- **주석** · `frontend/src/App.tsx:114` — `// [P2-2] Agent Governance Center — 조직 자산의 범위·권한·승인(설계 §8.3~§8.6).`
- **주석** · `frontend/src/components/AgentGovernancePanel.tsx:1` — `// [D-017 §9 P2-2] Agent Governance Center — 범위 탭 · 권한 상태 · 승인 흐름.`
- **주석** · `frontend/src/design/HubDialog.tsx:41` — `* Governance 하나**뿐이었다(6개는 둘 다 없고, 4개는 조직만). 화면마다 각자 그리게 두면 새`
- **주석** · `frontend/src/lib/agentGovernanceApi.ts:1` — `// [D-017 §9 P2-2] Agent Governance Center API 클라이언트.`
- **주석** · `frontend/src/lib/governanceApi.ts:3` — `// ⚠️ 화면(GovernanceConsole.tsx)과 **의도적으로 분리**한다. 디자인 시안이 확정되면 화면을`
- **기술 식별자 가능성** · `frontend/src/App.tsx:100` — `const [showGovernance, setShowGovernance] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:100` — `const [showGovernance, setShowGovernance] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:212` — `onSelect: () => setShowGovernance(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:354` — `<AgentGovernancePanel onClose={() => setShowAgentGov(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:363` — `{showGovernance && (<GovernanceConsole onClose={() => setShowGovernance(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:363` — `{showGovernance && (<GovernanceConsole onClose={() => setShowGovernance(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:363` — `{showGovernance && (<GovernanceConsole onClose={() => setShowGovernance(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:410` — `{showGovernance && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:411` — `<GovernanceConsole onClose={() => setShowGovernance(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:411` — `<GovernanceConsole onClose={() => setShowGovernance(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:442` — `<AgentGovernancePanel onClose={() => setShowAgentGov(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:559` — `onClick={() => setShowGovernance(true)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:603` — `{showGovernance && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:604` — `<GovernanceConsole onClose={() => setShowGovernance(false)} />`
- 그 외 13건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### PROD-16 · Program → 업무 프로그램

- **문자열 확인 필요** · `frontend/src/App.tsx:16` — `import ProgramAdminPanel from './components/ProgramAdminPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:16` — `import ProgramAdminPanel from './components/ProgramAdminPanel';`
- **문자열 확인 필요** · `frontend/src/components/ProgramAdminPanel.tsx:35` — `import type { ProgramLifecycle, ProgramStatus } from '../lib/programApi';`
- **문자열 확인 필요** · `frontend/src/components/ProgramAdminPanel.tsx:35` — `import type { ProgramLifecycle, ProgramStatus } from '../lib/programApi';`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:25` — `export type ProgramStatus = 'active' | 'deprecated' | 'disabled';`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:76` — `req<ProgramLifecycle>('GET', \`/api/v1/programs/${encodeURIComponent(releaseId)}\`);`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:78` — `export const fetchProgramStatuses = (status = '') =>`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:79` — `req<ProgramLifecycle[]>('GET', \`/api/v1/programs${status ? \`?status=${status}\` : ''}\`);`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:82` — `req<ProgramLifecycle>('POST', \`/api/v1/programs/${encodeURIComponent(releaseId)}/disable\`, args);`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:85` — `req<ProgramLifecycle>('POST', \`/api/v1/programs/${encodeURIComponent(releaseId)}/deprecate\`, args);`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:87` — `export const reactivateProgram = (releaseId: string, reason = '') =>`
- **문자열 확인 필요** · `frontend/src/lib/programApi.ts:88` — `req<ProgramLifecycle>('POST', \`/api/v1/programs/${encodeURIComponent(releaseId)}/reactivate\`,`
- **기술 식별자 가능성** · `frontend/src/App.tsx:126` — `const [adminProgram, setAdminProgram] = useState<{ id: string; name: string } | null>(null);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:126` — `const [adminProgram, setAdminProgram] = useState<{ id: string; name: string } | null>(null);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:423` — `{adminProgram && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:424` — `<ProgramAdminPanel`
- **기술 식별자 가능성** · `frontend/src/App.tsx:425` — `releaseId={adminProgram.id}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:426` — `releaseName={adminProgram.name}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:427` — `onClose={() => setAdminProgram(null)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:510` — `onManageRelease={(r) => setAdminProgram({ id: r.release_id, name: r.project_name || r.release_id })}`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:37` — `STATUS_LABEL, deprecateProgram, disableProgram, fetchProgram, reactivateProgram,`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:37` — `STATUS_LABEL, deprecateProgram, disableProgram, fetchProgram, reactivateProgram,`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:37` — `STATUS_LABEL, deprecateProgram, disableProgram, fetchProgram, reactivateProgram,`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:37` — `STATUS_LABEL, deprecateProgram, disableProgram, fetchProgram, reactivateProgram,`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:48` — `const TONE: Record<ProgramStatus, string> = {`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:52` — `export default function ProgramAdminPanel({ releaseId, releaseName, onClose, onChanged }: Props) {`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:53` — `const [prog, setProg] = useState<Loaded<ProgramLifecycle>>(loading<ProgramLifecycle>());`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:53` — `const [prog, setProg] = useState<Loaded<ProgramLifecycle>>(loading<ProgramLifecycle>());`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:70` — `const d = await fetchProgram(releaseId);`
- **기술 식별자 가능성** · `frontend/src/components/ProgramAdminPanel.tsx:79` — `: failed<ProgramLifecycle>(e));`
- 그 외 10건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### FLOW-32 · QA → 품질 검증 에이전트

- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:18` — `{ id: 'qa', label: 'QA', agent: 'QA' },`
- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:18` — `{ id: 'qa', label: 'QA', agent: 'QA' },`
- **사용자 노출 유력** · `frontend/src/components/PreviewPanel.tsx:836` — `{ id: 'REVIEW', label: '📝 리뷰' }, { id: 'QA', label: '🧪 QA' },`
- **사용자 노출 유력** · `frontend/src/components/PreviewPanel.tsx:836` — `{ id: 'REVIEW', label: '📝 리뷰' }, { id: 'QA', label: '🧪 QA' },`
- **사용자 노출 유력** · `frontend/src/components/PreviewPanel.tsx:982` — `: <p className="text-gray-400 text-sm mt-8 text-center">사용자 매뉴얼이 아직 생성되지 않았습니다.<br />QA 승인 완료 후 자동으로 작성됩니다.</p>`
- **사용자 노출 유력** · `frontend/src/components/WorkflowStrip.tsx:8` — `{ key: 'VISION_QA', label: '비전QA' },`
- **사용자 노출 유력** · `frontend/src/components/WorkflowStrip.tsx:8` — `{ key: 'VISION_QA', label: '비전QA' },`
- **사용자 노출 유력** · `frontend/src/components/WorkflowStrip.tsx:15` — `{ key: 'QA', label: 'QA' },`
- **사용자 노출 유력** · `frontend/src/components/WorkflowStrip.tsx:15` — `{ key: 'QA', label: 'QA' },`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:25` — `["QA", "QA"], ["MANUAL", "매뉴얼"],`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:25` — `["QA", "QA"], ["MANUAL", "매뉴얼"],`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:81` — `if (n.id === 'qa') return has('QA') || isFinalTask;`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:169` — `const legacyStages = ["RFP", "PLANNING", "TECH_SPEC", "CODE_REVIEW", "QA", "END"];`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:747` — `🧪 QA(통합검수): {state?.qa_verdict === "PASS" ? "✅ 통과" : state?.qa_verdict === "FAIL" ? "❌ 미통과" : "—"}`
- **문자열 확인 필요** · `frontend/src/components/MegaBoardroomPanel.tsx:71` — `if (subState.factory_mode === 'QA_RELEASE') return 100;`
- **문자열 확인 필요** · `frontend/src/components/PreviewPanel.tsx:808` — `case 'QA': return docs.qa_report_summary || "QA(통합검수) 리포트가 없습니다.";`
- **문자열 확인 필요** · `frontend/src/components/PreviewPanel.tsx:808` — `case 'QA': return docs.qa_report_summary || "QA(통합검수) 리포트가 없습니다.";`
- **문자열 확인 필요** · `frontend/src/components/PreviewPanel.tsx:809` — `case 'ACCEPT': return docs.supervisor_report_summary || "고객사 수용검수 리포트가 아직 없습니다.\nQA 통과 후 최종 수용검수가 수행됩니다.";`
- **문자열 확인 필요** · `frontend/src/design/terms.ts:43` — `VISION_QA: '화면 검증',`
- **문자열 확인 필요** · `frontend/src/design/terms.ts:50` — `QA: '품질 검증',`
- **문자열 확인 필요** · `frontend/src/design/terms.ts:78` — `QA: '품질 검증 담당',`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:52` — `'RFP', 'PLANNING', 'ARCHITECTURE', 'TECH_SPEC', 'CODE_REVIEW', 'QA', 'SUPERVISOR', 'MANUAL',`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:53` — `'UI_DESIGN', 'VISION_QA',`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:412` — `QA: { text: 'qa_report_summary', verdict: 'qa_verdict' },`
- **문자열 확인 필요** · `frontend/src/store/useFactoryStore.ts:21` — `qa_verdict?: string;  // "" | "PASS" | "FAIL" — QA(수행사 통합검수) 판정`
- **주석** · `frontend/src/components/ControlPanel.tsx:745` — `{/* QA(수행사 통합검수) 보조 표시 */}`
- **주석** · `frontend/src/components/WorkStandardPanel.tsx:10` — `//      사전을 거친다. 단, \`STD-QA\` 처럼 **실제 식별자**는 그대로 둔다 — 사용자도 그 문자열로 찾는다.`
- **주석** · `frontend/src/design/terms.ts:12` — `// ★ 코드·식별자는 여기 대상이 아니다. \`BP-GOLD-001\`, \`STD-QA\` 같은 값은 **실제 식별자**이고,`
- **주석** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:47` — `*  ★ [2026-08-06 실측] \`UI_DESIGN\`·\`VISION_QA\` 를 이 집합에서 빼 두었더니 「작업면이 아직 이`
- **주석** · `frontend/src/factory/factoryViewModel.ts:191` — `/** 판정이 있는 단계만 채운다(QA·수용검수의 PASS/FAIL). 없으면 빈 문자열. */`
- 그 외 8건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### DEC-16 · Publication → 보고서 발간

- **문자열 확인 필요** · `frontend/src/features/collaboration/CollaborationHub.tsx:25` — `import { PublicationCenter, type PublicationJarvis } from './PublicationCenter';`
- **문자열 확인 필요** · `frontend/src/features/collaboration/CollaborationHub.tsx:25` — `import { PublicationCenter, type PublicationJarvis } from './PublicationCenter';`
- **문자열 확인 필요** · `frontend/src/features/collaboration/CollaborationHub.tsx:25` — `import { PublicationCenter, type PublicationJarvis } from './PublicationCenter';`
- **문자열 확인 필요** · `frontend/src/features/collaboration/PublicationCenter.tsx:93` — `setList(loading<Publication[]>()); setDecisions([]); setCurrent(null); setMode('list'); load();`
- **문자열 확인 필요** · `frontend/src/features/collaboration/PublicationCenter.tsx:405` — `doc: Publication['current_version'] extends null ? never : any;`
- **문자열 확인 필요** · `frontend/src/features/collaboration/PublicationCenter.tsx:407` — `version: Publication['current_version']; external: boolean;`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:68` — `}) => req<Publication>('POST', '/api/v1/publications', body),`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:75` — `return req<Publication[]>('GET', \`/api/v1/publications${s ? \`?${s}\` : ''}\`);`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:78` — `get: (id: string) => req<Publication>('GET', \`/api/v1/publications/${id}\`),`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:80` — `render: (id: string) => req<Publication>('POST', \`/api/v1/publications/${id}/render\`),`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:83` — `req<Publication>('POST', \`/api/v1/publications/${id}/request-approval\`, { review_types }),`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:86` — `req<Publication>('POST', \`/api/v1/publications/${id}/approve\`,`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:90` — `req<Publication>('POST', \`/api/v1/publications/${id}/publish\`, { targets }),`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:93` — `req<Publication>('POST', \`/api/v1/publications/${id}/correct\`, { reason }),`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:96` — `req<Publication>('POST', \`/api/v1/publications/${id}/withdraw\`, { reason }),`
- **주석** · `frontend/src/features/collaboration/PublicationCenter.tsx:450` — `{/* ★ [설계 §5.3] 「중앙은 **실제 보고서 페이지 비율의** \`PublicationPreview\`」.`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/CollaborationHub.tsx:202` — `const [pubCtx, setPubCtx] = useState<PublicationJarvis | null>(null);`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/CollaborationHub.tsx:459` — `<PublicationCenter onJarvis={setPubCtx} />`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:23` — `type Audience, type Publication, type ReviewType, type SourceType,`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:27` — `export type PublicationJarvis = {`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:34` — `function StatusChip({ p }: { p: Publication }) {`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:55` — `export function PublicationCenter({ onJarvis }: { onJarvis?: (c: PublicationJarvis) => void }) {`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:55` — `export function PublicationCenter({ onJarvis }: { onJarvis?: (c: PublicationJarvis) => void }) {`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:61` — `const [list, setList] = useState<Loaded<Publication[]>>(loading<Publication[]>());`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:61` — `const [list, setList] = useState<Loaded<Publication[]>>(loading<Publication[]>());`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:62` — `const [current, setCurrent] = useState<Publication | null>(null);`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:83` — `setList(failed<Publication[]>(e));`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:114` — `const act = async (label: string, fn: () => Promise<Publication>) => {`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:233` — `list: Publication[];`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:234` — `state: Loaded<Publication[]>;`
- 그 외 5건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### AI-09 · Skill → 에이전트 스킬

- **문자열 확인 필요** · `frontend/src/App.tsx:20` — `import { SkillEvolutionPanel } from './components/SkillEvolutionPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:20` — `import { SkillEvolutionPanel } from './components/SkillEvolutionPanel';`
- **문자열 확인 필요** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:114` — `{isGeneratingSkill ? "⏳ AI가 스킬 문서 작성 중..." : "✨ AI로 역할 구체화 및 스킬 자동 생성"}`
- **문자열 확인 필요** · `frontend/src/components/SkillEvolutionPanel.tsx:25` — `import { skillApi, type SkillProposal } from '../lib/skillApi';`
- **문자열 확인 필요** · `frontend/src/lib/skillApi.ts:33` — `const e = new Error(j?.detail || \`요청 실패 (${r.status})\`) as SkillApiError;`
- **문자열 확인 필요** · `frontend/src/lib/skillApi.ts:41` — `proposals: () => call<SkillProposal[]>('GET', '/skills/proposals'),`
- **주석** · `frontend/src/components/SkillEvolutionPanel.tsx:224` — `{/* ★ [설계 §5.7 Skill Evolution] 「제안 카드마다 **실패 근거, 현재 규칙,`
- **주석** · `frontend/src/design/DataFoundationShell.tsx:244` — `*   있었다(AgentMasterPanel·OrgChartPanel·SkillEvolutionPanel·WorkStandardPanel).`
- **주석** · `frontend/src/lib/skillApi.ts:3` — `// ⚠️ 종전 \`SkillEvolutionPanel\` 은 \`if (res.ok)\` 만 처리하고 **else 를 버렸다.** 그래서 403 이어도`
- **기술 식별자 가능성** · `frontend/src/App.tsx:87` — `const [showSkillEvolution, setShowSkillEvolution] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:87` — `const [showSkillEvolution, setShowSkillEvolution] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:236` — `onSelect: () => setShowSkillEvolution(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:364` — `{showSkillEvolution && (<SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:364` — `{showSkillEvolution && (<SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:364` — `{showSkillEvolution && (<SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:376` — `{showSkillEvolution && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:377` — `<SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:377` — `<SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />`
- **기술 식별자 가능성** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:29` — `const [isGeneratingSkill, setIsGeneratingSkill] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:29` — `const [isGeneratingSkill, setIsGeneratingSkill] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:33` — `const handleGenerateSkill = async () => {`
- **기술 식별자 가능성** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:38` — `setIsGeneratingSkill(true);`
- **기술 식별자 가능성** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:60` — `setIsGeneratingSkill(false);`
- **기술 식별자 가능성** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:110` — `onClick={handleGenerateSkill}`
- **기술 식별자 가능성** · `frontend/src/components/AgentFlow/AgentDetailSidebar.tsx:111` — `disabled={isGeneratingSkill || !agent.role?.trim()}`
- **기술 식별자 가능성** · `frontend/src/components/SkillEvolutionPanel.tsx:27` — `export function SkillEvolutionPanel({ onClose }: { onClose: () => void }) {`
- **기술 식별자 가능성** · `frontend/src/components/SkillEvolutionPanel.tsx:28` — `const [list, setList] = useState<Loaded<SkillProposal[]>>(loading<SkillProposal[]>());`
- **기술 식별자 가능성** · `frontend/src/components/SkillEvolutionPanel.tsx:28` — `const [list, setList] = useState<Loaded<SkillProposal[]>>(loading<SkillProposal[]>());`
- **기술 식별자 가능성** · `frontend/src/components/SkillEvolutionPanel.tsx:35` — `const approve = useConfirm<SkillProposal>();`
- **기술 식별자 가능성** · `frontend/src/components/SkillEvolutionPanel.tsx:36` — `const reject = useConfirm<SkillProposal>();`
- 그 외 3건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인

### FLOW-38 · Promotion → 운영 자산 승격

- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:110` — `const statuses = Object.keys(PROMO).filter((s) => present.has(s as Promotion['status']));`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:76` — `export const fetchPromotions = (status = '') =>`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:77` — `req<Promotion[]>('GET', \`/api/v1/workspace/promotions${status ? \`?status=${status}\` : ''}\`);`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:85` — `}) => req<Promotion>('POST', '/api/v1/workspace/promotions', body);`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:88` — `req<Promotion>('POST', '/api/v1/workspace/promotions/owner-approve',`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:92` — `req<Promotion>('POST', '/api/v1/workspace/promotions/reject',`
- **문자열 확인 필요** · `frontend/src/lib/workspaceApi.ts:96` — `req<Promotion>('POST', '/api/v1/workspace/promotions/promote', { release_id: releaseId });`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:41` — `Checklist, ChecklistStep, Fork, Gate, GateCheck, Promotion, RollbackResult, Share,`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:44` — `createShare, fetchChecklist, fetchForks, fetchGate, fetchPromotions, fetchShares,`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:45` — `ownerApprove, promoteRelease, rejectPromotion, requestPromotion, revokeShare,`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:45` — `ownerApprove, promoteRelease, rejectPromotion, requestPromotion, revokeShare,`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:103` — `rows: Promotion[]; filter: OperateFilter; onChange: (f: OperateFilter) => void;`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:105` — `const uniq = (pick: (p: Promotion) => string) =>`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:146` — `const [promotions, setPromotions] = useState<Loaded<Promotion[]>>(loading<Promotion[]>());`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:146` — `const [promotions, setPromotions] = useState<Loaded<Promotion[]>>(loading<Promotion[]>());`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:146` — `const [promotions, setPromotions] = useState<Loaded<Promotion[]>>(loading<Promotion[]>());`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:174` — `setPromotions(loading<Promotion[]>());`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:174` — `setPromotions(loading<Promotion[]>());`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:176` — `const rows = await fetchPromotions();`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:178` — `setPromotions(ok(rows || []));`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:181` — `setPromotions(failed<Promotion[]>(e));`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:181` — `setPromotions(failed<Promotion[]>(e));`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:241` — `const shownPromotions = (promotions.value || []).filter((p) =>`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:298` — `) : shownPromotions.length === 0 ? (`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:308` — `{shownPromotions.map((p) => (`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:377` — `onClick={() => act(() => requestPromotion({`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:413` — `act(() => rejectPromotion(releaseId,`
- **기술 식별자 가능성** · `frontend/src/lib/workspaceApi.ts:50` — `export type Promotion = {`
- **기술 식별자 가능성** · `frontend/src/lib/workspaceApi.ts:83` — `export const requestPromotion = (body: {`
- **기술 식별자 가능성** · `frontend/src/lib/workspaceApi.ts:91` — `export const rejectPromotion = (releaseId: string, reason: string) =>`

### UI-14 · Telemetry → 운영 계측

- **문자열 확인 필요** · `frontend/src/App.tsx:32` — `import { TelemetryPanel } from './components/TelemetryPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:32` — `import { TelemetryPanel } from './components/TelemetryPanel';`
- **문자열 확인 필요** · `frontend/src/components/TelemetryPanel.tsx:30` — `import { telemetryApi, type TelemetryProject, type TelemetrySummary } from '../lib/telemetryApi';`
- **문자열 확인 필요** · `frontend/src/components/TelemetryPanel.tsx:30` — `import { telemetryApi, type TelemetryProject, type TelemetrySummary } from '../lib/telemetryApi';`
- **문자열 확인 필요** · `frontend/src/components/TelemetryPanel.tsx:101` — `const t = d?.totals || ({} as TelemetrySummary['totals']);`
- **문자열 확인 필요** · `frontend/src/lib/telemetryApi.ts:53` — `projects: () => closedLoopFetch<TelemetryProject[]>('GET', '/api/v1/telemetry/projects'),`
- **주석** · `frontend/src/components/AdvisorPanel.tsx:17` — `//    · 기존 패널(TelemetryPanel 등)의 다크 모달 패턴과 클래스를 그대로 쓴다. 새 디자인 언어를 만들지 않는다.`
- **주석** · `frontend/src/lib/telemetryApi.ts:6` — `// ★ 종전 \`TelemetryPanel\` 은 화면 안에서 raw \`fetch\` 를 하고 \`.catch(() => setData(null))\``
- **기술 식별자 가능성** · `frontend/src/App.tsx:96` — `const [showTelemetry, setShowTelemetry] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:96` — `const [showTelemetry, setShowTelemetry] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:257` — `onSelect: () => setShowTelemetry(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:362` — `{showTelemetry && (<TelemetryPanel onClose={() => setShowTelemetry(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:362` — `{showTelemetry && (<TelemetryPanel onClose={() => setShowTelemetry(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:362` — `{showTelemetry && (<TelemetryPanel onClose={() => setShowTelemetry(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:404` — `{showTelemetry && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:405` — `<TelemetryPanel onClose={() => setShowTelemetry(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:405` — `<TelemetryPanel onClose={() => setShowTelemetry(false)} />`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:55` — `export function TelemetryPanel({ onClose }: { onClose: () => void }) {`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:58` — `const [projects, setProjects] = useState<Loaded<TelemetryProject[]>>(`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:59` — `loading<TelemetryProject[]>());`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:60` — `const [sum, setSum] = useState<Loaded<TelemetrySummary>>(loading<TelemetrySummary>());`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:60` — `const [sum, setSum] = useState<Loaded<TelemetrySummary>>(loading<TelemetrySummary>());`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:76` — `setProjects(asLoaded<TelemetryProject[]>(e));`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:82` — `setSum(loading<TelemetrySummary>());`
- **기술 식별자 가능성** · `frontend/src/components/TelemetryPanel.tsx:89` — `setSum(asLoaded<TelemetrySummary>(e));`
- **기술 식별자 가능성** · `frontend/src/lib/telemetryApi.ts:12` — `export type TelemetryProject = {`
- **기술 식별자 가능성** · `frontend/src/lib/telemetryApi.ts:18` — `export type TelemetryTotals = {`
- **기술 식별자 가능성** · `frontend/src/lib/telemetryApi.ts:34` — `export type TelemetrySummary = {`
- **기술 식별자 가능성** · `frontend/src/lib/telemetryApi.ts:35` — `totals: TelemetryTotals;`
- **기술 식별자 가능성** · `frontend/src/lib/telemetryApi.ts:55` — `summary: (project: string) => closedLoopFetch<TelemetrySummary>(`

### KNOW-05 · Evidence → 근거 자료

- **문자열 확인 필요** · `frontend/src/components/BriefingPanel.tsx:20` — `import { EvidenceStrip, FoundationToolbar } from '../design/DataFoundationShell';`
- **문자열 확인 필요** · `frontend/src/components/GovernanceConsole.tsx:22` — `import { EvidenceStrip, FoundationToolbar } from '../design/DataFoundationShell';`
- **주석** · `frontend/src/components/DecisionDrawer.tsx:6` — `// · 순서 **Summary → Impact → Evidence → Related objects → Approval → History**`
- **주석** · `frontend/src/components/DecisionDrawer.tsx:98` — `{/* ③ Evidence */}`
- **주석** · `frontend/src/components/EnterprisePage.tsx:512` — `{/* §5.1 Decision Drawer — 520px · Summary→Impact→Evidence→Related→Approval→History */}`
- **주석** · `frontend/src/design/DataFoundationShell.tsx:24` — `// 그 자료로 만든 산출물도 설명할 수 없다. 그래서 \`EvidenceStrip\` 을 셸이 제공하고,`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:27` — `ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar, useConfirm,`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:614` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:796` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/BriefingPanel.tsx:100` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/GovernanceConsole.tsx:519` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/KnowledgeHubPanel.tsx:28` — `ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar,`
- **기술 식별자 가능성** · `frontend/src/components/KnowledgeHubPanel.tsx:317` — `<EvidenceStrip`
- **기술 식별자 가능성** · `frontend/src/components/MasterDataPanel.tsx:12` — `ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar,`
- **기술 식별자 가능성** · `frontend/src/components/MasterDataPanel.tsx:425` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/MasterDataPanel.tsx:456` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/MasterDataPanel.tsx:648` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/MasterDataPanel.tsx:699` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/OrgChartPanel.tsx:23` — `ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar, VersionHistory,`
- **기술 식별자 가능성** · `frontend/src/components/OrgChartPanel.tsx:426` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/OrgChartPanel.tsx:549` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/OrgChartPanel.tsx:696` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/SkillEvolutionPanel.tsx:16` — `import { ConfirmInline, EvidenceStrip, FoundationList, useConfirm, type FoundationRow }`
- **기술 식별자 가능성** · `frontend/src/components/SkillEvolutionPanel.tsx:217` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/components/WorkStandardPanel.tsx:24` — `ConfirmInline, EvidenceStrip, FoundationList, FoundationToolbar, VersionHistory, useConfirm,`
- **기술 식별자 가능성** · `frontend/src/components/WorkStandardPanel.tsx:336` — `<EvidenceStrip items={[`
- **기술 식별자 가능성** · `frontend/src/design/DataFoundationShell.tsx:127` — `export function EvidenceStrip({ items, note }: {`
- **기술 식별자 가능성** · `frontend/src/design/JarvisRail.tsx:19` — `export type JarvisEvidence = { label: string; value: string };`
- **기술 식별자 가능성** · `frontend/src/design/JarvisRail.tsx:97` — `evidence?: JarvisEvidence[];`

### UI-07 · Agents → AI 에이전트

- **사용자 노출 유력** · `frontend/src/components/TimelinePanel.tsx:127` — `<div className="text-[10px] text-gray-500 mb-2 font-bold tracking-wider">✅ COMPLETED AGENTS ({completedAgents.length})</div>`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:268` — `id: \`e-${sortedAgents[i].id}-${sortedAgents[i + 1].id}\`,`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:268` — `id: \`e-${sortedAgents[i].id}-${sortedAgents[i + 1].id}\`,`
- **문자열 확인 필요** · `frontend/src/components/AgentMasterPanel.tsx:581` — `? \`${agents.length - enabledAgents.length}개는 빠집니다\` : '전부 참여'} />`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:243` — `const sortedAgents = [...draft.agents].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:247` — `return sortedAgents.map((agent, index) => {`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:265` — `if (currentEdges.length === 0 && sortedAgents.length > 1) {`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:266` — `for (let i = 0; i < sortedAgents.length - 1; i++) {`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:269` — `source: sortedAgents[i].id,`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:270` — `target: sortedAgents[i + 1].id,`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:373` — `const enabledAgents = agents.filter((a) => a.enabled);`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:374` — `const hotlCount = enabledAgents.filter((a) => a.hotl_after).length;`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:375` — `const filteredAgents = (() => {`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:464` — `const agentRows: FoundationRow[] = filteredAgents.map((a) => ({`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:578` — `value={draft ? enabledAgents.length : null}`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:580` — `hint={draft && enabledAgents.length < agents.length`
- **기술 식별자 가능성** · `frontend/src/components/AgentMasterPanel.tsx:757` — `<FlowValidationPanel agents={enabledAgents} edges={edges} hotlCount={hotlCount} />`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:71` — `const buildTaskPipeline = (requiredAgents: string[], execPipeline: any[], templateData: any, isFinalTask: boolean = false) => {`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:72` — `const ra = (requiredAgents || []).map((a) => a.toLowerCase());`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:111` — `const completedAgents = useFactoryStore((s) => s.completed_agents);`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:212` — `const completedIdx = (completedAgents || []).reduce((m: number, n: string) => Math.max(m, NODE_MACRO[n] ?? -1), -1);`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:418` — `const currentAgentIdx = pipeline.findIndex(a => !completedAgents.map((ca: string) => ca.toLowerCase()).includes(a.id));`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:435` — `const isCompleted = completedAgents.map((ca: string) => ca.toLowerCase()).includes(agent.id);`
- **기술 식별자 가능성** · `frontend/src/components/TimelinePanel.tsx:38` — `const completedAgents = useFactoryStore((s) => s.completed_agents);`
- **기술 식별자 가능성** · `frontend/src/components/TimelinePanel.tsx:130` — `{completedAgents.length > 0 ? (`
- **기술 식별자 가능성** · `frontend/src/components/TimelinePanel.tsx:131` — `completedAgents.map((agent: string, i: number) => (`
- **기술 식별자 가능성** · `frontend/src/store/useFactoryStore.ts:876` — `const domainAgents: string[] = result.data.domain_agents || [];`
- **기술 식별자 가능성** · `frontend/src/store/useFactoryStore.ts:877` — `if (domainAgents.length > 0 && templateData?.agents) {`
- **기술 식별자 가능성** · `frontend/src/store/useFactoryStore.ts:881` — `domainAgents.includes(a.id) || a.is_framework === true`

### DATA-29 · PLAN → 계획

- **사용자 노출 유력** · `frontend/src/components/PlanningPanel.tsx:131` — `<ScreenHead kicker="PLANNING" title="계획 · 실적 · 시나리오"`
- **사용자 노출 유력** · `frontend/src/factory/RunControls.tsx:246` — `<p className="run-hint">{REPLAN_CONFIRM}</p>`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:23` — `["CLARIFICATION", "요구확인"], ["RFP", "요구정의"], ["PLANNING", "기획"], ["ARCHITECTURE", "아키텍처"], ["PMO", "WBS"],`
- **문자열 확인 필요** · `frontend/src/components/ControlPanel.tsx:169` — `const legacyStages = ["RFP", "PLANNING", "TECH_SPEC", "CODE_REVIEW", "QA", "END"];`
- **문자열 확인 필요** · `frontend/src/components/HOTLInput.tsx:59` — `PLANNING: { what: "기획서 (PRD)", where: "우측 '기획서' 탭" },`
- **문자열 확인 필요** · `frontend/src/components/MegaBoardroomPanel.tsx:72` — `if (subState.factory_mode === 'PLANNING') return 10;`
- **문자열 확인 필요** · `frontend/src/components/WorkflowStrip.tsx:6` — `{ key: 'PLANNING', label: '기획' },`
- **문자열 확인 필요** · `frontend/src/design/terms.ts:41` — `PLANNING: '사업 기획',`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:52` — `'RFP', 'PLANNING', 'ARCHITECTURE', 'TECH_SPEC', 'CODE_REVIEW', 'QA', 'SUPERVISOR', 'MANUAL',`
- **문자열 확인 필요** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:257` — `const plan = NOT_YET_PLAN[(shownStageId || '').toUpperCase()];`
- **문자열 확인 필요** · `frontend/src/factory/factoryViewModel.ts:408` — `PLANNING: { text: 'prd_summary' },`
- **문자열 확인 필요** · `frontend/src/factory/sprintActions.ts:69` — `factory_mode: 'PLANNING',`
- **문자열 확인 필요** · `frontend/src/factory/sprintActions.ts:75` — `return \`PLANNING_${Date.now()}\`;`
- **문자열 확인 필요** · `frontend/src/lib/planningApi.ts:8` — `export const VALUE_KINDS = ['ACTUAL', 'PLAN', 'FORECAST', 'SCENARIO'] as const;`
- **문자열 확인 필요** · `frontend/src/lib/planningApi.ts:169` — `export const fetchCashFlow = (orgId: string, period: string, valueKind: ValueKind = 'PLAN') =>`
- **문자열 확인 필요** · `frontend/src/lib/planningApi.ts:207` — `export const fetchRollupCheck = (orgId: string, period: string, valueKind: ValueKind = 'PLAN') =>`
- **주석** · `frontend/src/factory/RunControls.tsx:150` — `// ⚠️ \`docs\` 는 배열이 아니라 **stage 키 맵**이다. 기획 산출물은 \`PLANNING\` 에 들어 있고,`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:32` — `CLARIFICATION: 0, RFP: 1, PLANNING: 2, ARCHITECTURE: 3, PMO: 4, TECH_SPEC: 5,`
- **기술 식별자 가능성** · `frontend/src/components/WorkflowStrip.tsx:25` — `CLARIFICATION: 0, RFP: 1, PLANNING: 2, UI_DESIGN: 3, VISION_QA: 4, ARCHITECTURE: 5, PMO: 6, TECH_SPEC: 7, EXECUTION: 8, BUILD: 9, CODE_REVIEW: 10, QA: 11, SUPERVISOR: 12, MANUAL: 1`
- **기술 식별자 가능성** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:238` — `const NOT_YET_PLAN: Record<string, { what: string; where: string }> = {};`
- **기술 식별자 가능성** · `frontend/src/factory/RunControls.tsx:25` — `REPLAN_CONFIRM, REVISION_NOTE, SELF_HEAL_NOTE, exportArchiveUrl, newPlanningTaskId,`
- **기술 식별자 가능성** · `frontend/src/factory/RunControls.tsx:153` — `const replanWhy = !vm.docs.PLANNING`
- **기술 식별자 가능성** · `frontend/src/factory/StageArtifactCanvas.tsx:37` — `const PLAN: Record<string, { title: string; aux: string; noSource?: string }> = {`
- **기술 식별자 가능성** · `frontend/src/factory/StageArtifactCanvas.tsx:42` — `PLANNING: {`
- **기술 식별자 가능성** · `frontend/src/factory/StageArtifactCanvas.tsx:99` — `const plan = PLAN[id];`
- **기술 식별자 가능성** · `frontend/src/factory/sprintActions.ts:126` — `export const REPLAN_CONFIRM =`

### UI-05 · Knowledge → 전사 지식 허브

- **문자열 확인 필요** · `frontend/src/App.tsx:24` — `import { KnowledgeHubPanel } from './components/KnowledgeHubPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:24` — `import { KnowledgeHubPanel } from './components/KnowledgeHubPanel';`
- **주석** · `frontend/src/components/CrosswalkPanel.tsx:17` — `// \`KnowledgeHubPanel\` 의 모든 호출이 **조용히 익명으로** 나갔다. 지금은 인터셉터가 origin 으로`
- **주석** · `frontend/src/lib/api.ts:171` — `//   \`KnowledgeHubPanel.tsx\` 는 자기만의 \`API_BASE_URL\` 을 \`http://localhost:8080\` 으로`
- **주석** · `frontend/src/lib/closedLoopFetch.ts:8` — `// ★ \`API_BASE_URL\` 을 다시 선언하지 않는다. 예전에 \`KnowledgeHubPanel\` 이 자기 \`localhost:8080\``
- **주석** · `frontend/src/lib/collaborationApi.ts:4` — `//   \`KnowledgeHubPanel.tsx\` 가 자기 \`localhost:8080\` 을 선언해 인터셉터(\`127.0.0.1\` 기준)가`
- **주석** · `frontend/src/lib/crosswalkApi.ts:9` — `// \`KnowledgeHubPanel\` 의 모든 호출이 **조용히 익명으로** 나갔다(무제한 관리자인데 화면은`
- **주석** · `frontend/src/lib/knowledgeApi.ts:3` — `// ⚠️ 예전 \`KnowledgeHubPanel\` 은 **자기 \`API_BASE_URL\` 을 선언**하고 \`fetch\` 를 직접 썼으며,`
- **기술 식별자 가능성** · `frontend/src/App.tsx:88` — `const [showKnowledgeHub, setShowKnowledgeHub] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:88` — `const [showKnowledgeHub, setShowKnowledgeHub] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:123` — `const [knowledgePacks, setKnowledgePacks] = useState<any[]>([]);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:163` — `setKnowledgePacks(r?.data || []);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:167` — `}, [showKnowledgeHub, actingUserRev]); // 허브에서 팩을 만들고 닫으면·사용자를 바꾸면 갱신`
- **기술 식별자 가능성** · `frontend/src/App.tsx:198` — `onSelect: () => setShowKnowledgeHub(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:356` — `{showKnowledgeHub && (<KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:356` — `{showKnowledgeHub && (<KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:356` — `{showKnowledgeHub && (<KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:379` — `{showKnowledgeHub && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:380` — `<KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:380` — `<KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />`
- **기술 식별자 가능성** · `frontend/src/components/KnowledgeHubPanel.tsx:47` — `export function KnowledgeHubPanel({ onClose }: { onClose: () => void }) {`

### ASST-07 · Advisor → 업무·데이터 설계 상담

- **문자열 확인 필요** · `frontend/src/App.tsx:33` — `import { AdvisorPanel } from './components/AdvisorPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:33` — `import { AdvisorPanel } from './components/AdvisorPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:341` — `if (id === 'advisor') setShowAdvisor(true);`
- **문자열 확인 필요** · `frontend/src/lib/advisorApi.ts:150` — `throw new AdvisorApiError(body?.detail || \`요청 실패 (HTTP ${res.status})\`, res.status);`
- **주석** · `frontend/src/lib/advisorApi.ts:3` — `// ⚠️ 화면(AdvisorPanel.tsx)과 **의도적으로 분리**한다. 디자인 시안이 확정되면 화면을 대대적으로`
- **기술 식별자 가능성** · `frontend/src/App.tsx:98` — `const [showAdvisor, setShowAdvisor] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:98` — `const [showAdvisor, setShowAdvisor] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:182` — `onSelect: () => setShowAdvisor(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:346` — `{showAdvisor && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:347` — `<AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:347` — `<AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:407` — `{showAdvisor && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:408` — `<AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:408` — `<AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:552` — `onClick={() => setShowAdvisor(true)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:600` — `{showAdvisor && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:601` — `<AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:601` — `<AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />`
- **기술 식별자 가능성** · `frontend/src/components/AdvisorPanel.tsx:100` — `export function AdvisorPanel(`
- **기술 식별자 가능성** · `frontend/src/lib/advisorApi.ts:132` — `class AdvisorApiError extends Error {`

### ASST-03 · Supervisor → 품질 감독 에이전트

- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:17` — `{ id: 'reviewer', label: 'Supervisor', agent: null as string | null },`
- **문자열 확인 필요** · `frontend/src/design/terms.ts:79` — `Supervisor: '총괄 감독',`
- **주석** · `frontend/src/components/ControlPanel.tsx:36` — `// 노드 id → Supervisor 채점 단계 키 (배지 표시용)`
- **주석** · `frontend/src/components/ControlPanel.tsx:420` — `// 단계별 최신 Supervisor 판정 맵 (criteria_log에서 추출)`
- **주석** · `frontend/src/components/ControlPanel.tsx:452` — `// Supervisor 채점 배지 (점수 + 판정색 + 토론 라운드)`
- **주석** · `frontend/src/components/ControlPanel.tsx:742` — `{/* 🚀 모든 단계 완료 시 — 고객 수용검수(Supervisor) 연동 + 최종 결과물 저장(배포) */}`
- **주석** · `frontend/src/components/ControlPanel.tsx:749` — `{/* Supervisor(고객사 수용검수) = 완료/배포 판단 기준 */}`
- **주석** · `frontend/src/design/DataFoundationShell.tsx:2` — `//   대상: 지식 허브 → 기준정보 마스터 → 업무표준 (Supervisor 이관 순서)`
- **주석** · `frontend/src/design/DataFoundationShell.tsx:5` — `// ## 왜 세 화면을 따로 꾸미기 전에 이것부터 만드는가 (Supervisor 이관 순서 지정)`
- **주석** · `frontend/src/design/JarvisRail.tsx:4` — `// ★★ §3 명칭 호환: 표시명은 \`Jarvis\`, 엔진은 기존 Supervisor 다. 두 번째 채팅 API 를 만들지`
- **주석** · `frontend/src/factory/DecisionJarvisDock.tsx:4` — `* 근거: 구현 명세 §2.3 · §4(\`HOTLInput\` → \`DecisionDock\`, Supervisor Chat → \`JarvisDock\`).`
- **주석** · `frontend/src/lib/jarvisApi.ts:49` — `/** 기존 Supervisor(=Jarvis) 엔진에 문맥을 붙여 넘긴다. 새 엔진이 아니다(§3). */`
- **주석** · `frontend/src/store/useFactoryStore.ts:26` — `// 토론·합의 / 단계별 성공기준 / Supervisor (V5.1 관측성)`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:760` — `ℹ️ 수용검수 정보 없음 — 고객사 최종 수용검수(Supervisor)가 아직 수행되지 않았을 수 있습니다.`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:15` — `const [supervisorReply, setSupervisorReply] = useState<string | null>(null);`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:84` — `setSupervisorReply(null);`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:126` — `setSupervisorReply(data.reply);`
- **기술 식별자 가능성** · `frontend/src/components/TimelinePanel.tsx:62` — `🧭 Supervisor Console`

### FLOW-33 · Supervisor → 파이프라인 품질 감독 에이전트

- **사용자 노출 유력** · `frontend/src/components/ControlPanel.tsx:17` — `{ id: 'reviewer', label: 'Supervisor', agent: null as string | null },`
- **문자열 확인 필요** · `frontend/src/design/terms.ts:79` — `Supervisor: '총괄 감독',`
- **주석** · `frontend/src/components/ControlPanel.tsx:36` — `// 노드 id → Supervisor 채점 단계 키 (배지 표시용)`
- **주석** · `frontend/src/components/ControlPanel.tsx:420` — `// 단계별 최신 Supervisor 판정 맵 (criteria_log에서 추출)`
- **주석** · `frontend/src/components/ControlPanel.tsx:452` — `// Supervisor 채점 배지 (점수 + 판정색 + 토론 라운드)`
- **주석** · `frontend/src/components/ControlPanel.tsx:742` — `{/* 🚀 모든 단계 완료 시 — 고객 수용검수(Supervisor) 연동 + 최종 결과물 저장(배포) */}`
- **주석** · `frontend/src/components/ControlPanel.tsx:749` — `{/* Supervisor(고객사 수용검수) = 완료/배포 판단 기준 */}`
- **주석** · `frontend/src/design/DataFoundationShell.tsx:2` — `//   대상: 지식 허브 → 기준정보 마스터 → 업무표준 (Supervisor 이관 순서)`
- **주석** · `frontend/src/design/DataFoundationShell.tsx:5` — `// ## 왜 세 화면을 따로 꾸미기 전에 이것부터 만드는가 (Supervisor 이관 순서 지정)`
- **주석** · `frontend/src/design/JarvisRail.tsx:4` — `// ★★ §3 명칭 호환: 표시명은 \`Jarvis\`, 엔진은 기존 Supervisor 다. 두 번째 채팅 API 를 만들지`
- **주석** · `frontend/src/factory/DecisionJarvisDock.tsx:4` — `* 근거: 구현 명세 §2.3 · §4(\`HOTLInput\` → \`DecisionDock\`, Supervisor Chat → \`JarvisDock\`).`
- **주석** · `frontend/src/lib/jarvisApi.ts:49` — `/** 기존 Supervisor(=Jarvis) 엔진에 문맥을 붙여 넘긴다. 새 엔진이 아니다(§3). */`
- **주석** · `frontend/src/store/useFactoryStore.ts:26` — `// 토론·합의 / 단계별 성공기준 / Supervisor (V5.1 관측성)`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:760` — `ℹ️ 수용검수 정보 없음 — 고객사 최종 수용검수(Supervisor)가 아직 수행되지 않았을 수 있습니다.`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:15` — `const [supervisorReply, setSupervisorReply] = useState<string | null>(null);`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:84` — `setSupervisorReply(null);`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:126` — `setSupervisorReply(data.reply);`
- **기술 식별자 가능성** · `frontend/src/components/TimelinePanel.tsx:62` — `🧭 Supervisor Console`

### PROD-19 · Workspace → 부서 업무공간

- **문자열 확인 필요** · `frontend/src/App.tsx:15` — `import WorkspacePanel from './components/WorkspacePanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:15` — `import WorkspacePanel from './components/WorkspacePanel';`
- **기술 식별자 가능성** · `frontend/src/App.tsx:104` — `const [showWorkspace, setShowWorkspace] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:104` — `const [showWorkspace, setShowWorkspace] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:248` — `onSelect: () => setShowWorkspace(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:366` — `{showWorkspace && (<WorkspacePanel onClose={() => setShowWorkspace(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:366` — `{showWorkspace && (<WorkspacePanel onClose={() => setShowWorkspace(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:366` — `{showWorkspace && (<WorkspacePanel onClose={() => setShowWorkspace(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:419` — `{showWorkspace && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:420` — `<WorkspacePanel onClose={() => setShowWorkspace(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:420` — `<WorkspacePanel onClose={() => setShowWorkspace(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:582` — `onClick={() => setShowWorkspace(true)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:612` — `{showWorkspace && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:613` — `<WorkspacePanel onClose={() => setShowWorkspace(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:613` — `<WorkspacePanel onClose={() => setShowWorkspace(false)} />`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:145` — `export default function WorkspacePanel({ onClose }: Props) {`

### DATA-16 · Crosswalk → 코드·항목 연결표

- **사용자 노출 유력** · `frontend/src/components/AdminConsolePanel.tsx:455` — `개별 시스템 연결·범위 지정은 <b>Crosswalk</b> 화면에서 관리합니다. 이 화면은`
- **문자열 확인 필요** · `frontend/src/App.tsx:31` — `import { CrosswalkPanel } from './components/CrosswalkPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:31` — `import { CrosswalkPanel } from './components/CrosswalkPanel';`
- **주석** · `frontend/src/lib/crosswalkApi.ts:7` — `// \`CrosswalkPanel\` 상단에 \`const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '…8080'\``
- **기술 식별자 가능성** · `frontend/src/App.tsx:95` — `const [showCrosswalk, setShowCrosswalk] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:95` — `const [showCrosswalk, setShowCrosswalk] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:207` — `onSelect: () => setShowCrosswalk(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:361` — `{showCrosswalk && (<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:361` — `{showCrosswalk && (<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:361` — `{showCrosswalk && (<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:401` — `{showCrosswalk && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:402` — `<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:402` — `<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />`
- **기술 식별자 가능성** · `frontend/src/components/CrosswalkPanel.tsx:44` — `export function CrosswalkPanel({ onClose }: { onClose: () => void }) {`

### UI-11 · Crosswalk → 코드·항목 연결표

- **사용자 노출 유력** · `frontend/src/components/AdminConsolePanel.tsx:455` — `개별 시스템 연결·범위 지정은 <b>Crosswalk</b> 화면에서 관리합니다. 이 화면은`
- **문자열 확인 필요** · `frontend/src/App.tsx:31` — `import { CrosswalkPanel } from './components/CrosswalkPanel';`
- **문자열 확인 필요** · `frontend/src/App.tsx:31` — `import { CrosswalkPanel } from './components/CrosswalkPanel';`
- **주석** · `frontend/src/lib/crosswalkApi.ts:7` — `// \`CrosswalkPanel\` 상단에 \`const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '…8080'\``
- **기술 식별자 가능성** · `frontend/src/App.tsx:95` — `const [showCrosswalk, setShowCrosswalk] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:95` — `const [showCrosswalk, setShowCrosswalk] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:207` — `onSelect: () => setShowCrosswalk(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:361` — `{showCrosswalk && (<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:361` — `{showCrosswalk && (<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:361` — `{showCrosswalk && (<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:401` — `{showCrosswalk && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:402` — `<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />`
- **기술 식별자 가능성** · `frontend/src/App.tsx:402` — `<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />`
- **기술 식별자 가능성** · `frontend/src/components/CrosswalkPanel.tsx:44` — `export function CrosswalkPanel({ onClose }: { onClose: () => void }) {`

### UI-08 · Collaboration → 협업·의사결정

- **문자열 확인 필요** · `frontend/src/App.tsx:23` — `import { CollaborationHub } from './features/collaboration/CollaborationHub';`
- **문자열 확인 필요** · `frontend/src/App.tsx:23` — `import { CollaborationHub } from './features/collaboration/CollaborationHub';`
- **문자열 확인 필요** · `frontend/src/App.tsx:342` — `else if (id === 'collaboration') setShowCollaboration(true);`
- **문자열 확인 필요** · `frontend/src/features/collaboration/CollaborationHub.tsx:191` — `export function CollaborationHub({ onClose, initialView = 'inbox', releaseIds = [],`
- **기술 식별자 가능성** · `frontend/src/App.tsx:94` — `const [showCollaboration, setShowCollaboration] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:94` — `const [showCollaboration, setShowCollaboration] = useState(false);`
- **기술 식별자 가능성** · `frontend/src/App.tsx:185` — `onSelect: () => setShowCollaboration(true) },`
- **기술 식별자 가능성** · `frontend/src/App.tsx:349` — `{showCollaboration && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:350` — `<CollaborationHub onClose={() => setShowCollaboration(false)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:350` — `<CollaborationHub onClose={() => setShowCollaboration(false)}`
- **기술 식별자 가능성** · `frontend/src/App.tsx:394` — `{showCollaboration && (`
- **기술 식별자 가능성** · `frontend/src/App.tsx:395` — `<CollaborationHub`
- **기술 식별자 가능성** · `frontend/src/App.tsx:396` — `onClose={() => setShowCollaboration(false)}`

### AI-13 · Workflow → AI 작업 흐름

- **문자열 확인 필요** · `frontend/src/App.tsx:11` — `import WorkflowStrip from './components/WorkflowStrip';`
- **문자열 확인 필요** · `frontend/src/App.tsx:11` — `import WorkflowStrip from './components/WorkflowStrip';`
- **주석** · `frontend/src/components/BuildStartDialog.tsx:12` — `// ⚠️ 아직 없는 것을 만들어 넣지 않는다. 설계 §5.2 의 «전체 Workflow Map + 앞으로 생성될`
- **주석** · `frontend/src/factory/ProductionStageMap.tsx:4` — `* 근거: 구현 명세 §2.1(상시 노출) · §4(\`WorkflowStrip\` → \`ProductionStageMap\`,`
- **주석** · `frontend/src/factory/factoryViewModel.ts:21` — `* 4. **단계 목록을 하드코딩하지 않는다**(§4 \`WorkflowStrip\` → \`ProductionStageMap\` 행:`
- **주석** · `frontend/src/factory/factoryViewModel.ts:253` — `*   \`WorkflowStrip\` 은 14단계를 파일에 적어 두었는데, 그것은 커스텀 템플릿에서 실제 흐름과`
- **기술 식별자 가능성** · `frontend/src/App.tsx:635` — `<WorkflowStrip />`
- **기술 식별자 가능성** · `frontend/src/components/WorkflowStrip.tsx:28` — `export default function WorkflowStrip() {`
- **기술 식별자 가능성** · `frontend/src/store/useFactoryStore.ts:41` — `export interface WorkflowTemplate {`
- **기술 식별자 가능성** · `frontend/src/store/useFactoryStore.ts:84` — `templates: WorkflowTemplate[];`

### FLOW-02 · Clarification → 요구사항 구체화

- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:30` — `const isClarification =`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:43` — `if (!isClarification) return;`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:46` — `}, [isClarification, questionsFingerprint]);`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:88` — `const payloadFeedback = isClarification ? serializeAnswers() : feedback.trim();`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:173` — `{isClarification ? (`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:192` — `{isClarification && (`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:233` — `isClarification`
- **기술 식별자 가능성** · `frontend/src/components/HOTLInput.tsx:249` — `: (isClarification`
- **기술 식별자 가능성** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:125` — `function ClarificationCanvas({ clarify, selections, onToggle }: {`
- **기술 식별자 가능성** · `frontend/src/factory/AdaptivePhaseCanvas.tsx:247` — `<ClarificationCanvas clarify={vm.clarify} selections={selections} onToggle={onToggleChoice} />`

### DEC-02 · Decision Package → 의사결정 검토서

- **사용자 노출 유력** · `frontend/src/features/collaboration/DecisionCenter.tsx:278` — `description="시뮬레이션 결과를 하나의 Decision Package 로 만들고, 요청자·의사결정자·영향부서가 같은 문서를 관점별로 봅니다."`
- **사용자 노출 유력** · `frontend/src/features/collaboration/DecisionCenter.tsx:897` — `<ScreenHead kicker="NEW PACKAGE" title="새 Decision Package"`
- **문자열 확인 필요** · `frontend/src/features/collaboration/DecisionCenter.tsx:309` — `: '내가 참여자로 지정된 안건이 없습니다. 시뮬레이션 결과에서 «새 안건 만들기» 로 Decision Package 를 만들 수 있습니다.'} />`
- **문자열 확인 필요** · `frontend/src/features/collaboration/DecisionCenter.tsx:373` — `|| '세 관점은 같은 Decision Package 의 다른 렌더링입니다 — package_version 과 evidence_hash 가 같아야 같은 문서입니다.'}`
- **주석** · `frontend/src/features/collaboration/DecisionCenter.tsx:1` — `// [CL-2] 의사결정 센터 — 시뮬레이션 결과에서 Decision Package 를 만들고, 세 관점으로 검토하고,`
- **주석** · `frontend/src/lib/decisionApi.ts:1` — `// [CL-2] Decision Package API 클라이언트 — 작업서 §CL-BE-03.`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/DecisionCenter.tsx:1059` — `Decision Package 만들기`
- **기술 식별자 가능성** · `frontend/src/features/collaboration/PublicationCenter.tsx:425` — `이 문서는 원천 Decision Package 의 결정론적 투영입니다 — 원천이 바뀌어도 자동으로`

### UI-03 · Operate → 업무 앱

- **문자열 확인 필요** · `frontend/src/components/WorkspacePanel.tsx:162` — `const [filter, setFilter] = useState<OperateFilter>({ scope: '', status: '', target: '' });`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:93` — `type OperateFilter = { scope: string; status: string; target: string };`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:102` — `function OperateFilters({ rows, filter, onChange }: {`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:103` — `rows: Promotion[]; filter: OperateFilter; onChange: (f: OperateFilter) => void;`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:103` — `rows: Promotion[]; filter: OperateFilter; onChange: (f: OperateFilter) => void;`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:112` — `const group = (title: string, key: keyof OperateFilter, opts: string[],`
- **기술 식별자 가능성** · `frontend/src/components/WorkspacePanel.tsx:263` — `<OperateFilters rows={promotions.value || []} filter={filter} onChange={setFilter} />`

### AI-07 · Agent Governance → 에이전트 자산 통제

- **사용자 노출 유력** · `frontend/src/App.tsx:228` — `{ id: 'agent-gov', icon: '🏛', label: 'Agent Governance Center',`
- **사용자 노출 유력** · `frontend/src/components/AgentGovernancePanel.tsx:240` — `<HubDialog label="Agent Governance Center — 조직 자산의 범위·권한·승인" onClose={onClose}>`
- **사용자 노출 유력** · `frontend/src/components/AgentGovernancePanel.tsx:242` — `<b>Agent Governance Center</b>`
- **주석** · `frontend/src/App.tsx:114` — `// [P2-2] Agent Governance Center — 조직 자산의 범위·권한·승인(설계 §8.3~§8.6).`
- **주석** · `frontend/src/components/AgentGovernancePanel.tsx:1` — `// [D-017 §9 P2-2] Agent Governance Center — 범위 탭 · 권한 상태 · 승인 흐름.`
- **주석** · `frontend/src/lib/agentGovernanceApi.ts:1` — `// [D-017 §9 P2-2] Agent Governance Center API 클라이언트.`

### DATA-22 · RAW → 수집 원본

- **문자열 확인 필요** · `frontend/src/features/collaboration/PublicationCenter.tsx:342` — `{p.status === 'WITHDRAWN' && (`
- **문자열 확인 필요** · `frontend/src/features/collaboration/PublicationCenter.tsx:359` — `const canRender = !['APPROVED', 'PUBLISHED', 'WITHDRAWN', 'CORRECTED'].includes(p.status);`
- **문자열 확인 필요** · `frontend/src/features/collaboration/PublicationCenter.tsx:638` — `{!published && p.status !== 'WITHDRAWN' && (`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:16` — `| 'CORRECTED' | 'WITHDRAWN';`
- **문자열 확인 필요** · `frontend/src/lib/publicationApi.ts:109` — `WITHDRAWN: { label: '회수됨', tone: 'danger' },`

### OPS-25 · Traceability → 추적성

- **문자열 확인 필요** · `frontend/src/components/PreviewPanel.tsx:3` — `import TraceabilityGraph from './TraceabilityGraph';`
- **문자열 확인 필요** · `frontend/src/components/PreviewPanel.tsx:3` — `import TraceabilityGraph from './TraceabilityGraph';`
- **기술 식별자 가능성** · `frontend/src/components/PreviewPanel.tsx:987` — `<TraceabilityGraph />`
- **기술 식별자 가능성** · `frontend/src/components/TraceabilityGraph.tsx:10` — `export default function TraceabilityGraph() {`
- **기술 식별자 가능성** · `frontend/src/components/TraceabilityGraph.tsx:40` — `🔗 산출물 추적성 엔진 (Traceability)`

### DATA-01 · MDM → 기준정보 관리

- **사용자 노출 유력** · `frontend/src/components/EnterprisePage.tsx:120` — `{ key: 'mdm', title: 'MDM', state: 'loading', headline: '확인 중', detail: '' },`
- **주석** · `frontend/src/design/DataFoundationShell.tsx:279` — `// ── 이력 (업무표준·MDM 공용) ────────────────────────────────────────────────`

### DATA-30 · FORECAST → 전망

- **문자열 확인 필요** · `frontend/src/components/TimelinePanel.tsx:23` — `FORECAST: "수요 예측",`
- **문자열 확인 필요** · `frontend/src/lib/planningApi.ts:8` — `export const VALUE_KINDS = ['ACTUAL', 'PLAN', 'FORECAST', 'SCENARIO'] as const;`

### DATA-31 · SCENARIO → 시나리오

- **사용자 노출 유력** · `frontend/src/components/PlanningPanel.tsx:210` — `<Panel kicker="SCENARIOS" title="시나리오 선택"`
- **문자열 확인 필요** · `frontend/src/lib/planningApi.ts:8` — `export const VALUE_KINDS = ['ACTUAL', 'PLAN', 'FORECAST', 'SCENARIO'] as const;`

### FLOW-31 · Reviewer → 코드 품질 검토 에이전트

- **문자열 확인 필요** · `frontend/src/design/terms.ts:77` — `Reviewer: '코드 심사 담당',`
- **기술 식별자 가능성** · `frontend/src/components/ControlPanel.tsx:29` — `Backend: 6, Frontend: 6, CodeBuilder: 7, Reviewer: 8, QA: 9, ManualWriter: 10,`

### PROD-06 · Enterprise Canvas → 전사 경영 허브

- **주석** · `frontend/src/design/HubShell.tsx:1` — `// [UIUX] 허브 3열 셸 — 승인 시안(Living Enterprise Canvas)의 공용 레이아웃`
- **주석** · `frontend/src/features/collaboration/CollaborationHub.tsx:1` — `// [CL-1 · UIUX] 협업 허브 — 승인 시안(Living Enterprise Canvas) 기준선 위에서 동작하는 실제 화면`

### TWIN-04 · Simulation → 경영 시뮬레이션

- **주석** · `frontend/src/components/AgentMasterPanel.tsx:40` — `/** [UI 설계서 §5.7] 하단 Simulation/Validation panel —`
- **주석** · `frontend/src/components/AgentMasterPanel.tsx:755` — `{/* ★ [설계 §5.7] 「하단 Simulation/Validation panel: **그래프 유효성, 예상 호출,`

### TWIN-13 · Benchmark → 비교 기준

- **사용자 노출 유력** · `frontend/src/components/AdminConsolePanel.tsx:421` — `<Panel kicker="QUALITY" title="Golden Benchmark">`
- **사용자 노출 유력** · `frontend/src/components/AdminConsolePanel.tsx:424` — `품질 기준선은 <b>Golden Benchmark</b> 화면에서 시나리오별로 관리합니다 —`

### AI-10 · Skill Evolution → AI 스킬 개선

- **주석** · `frontend/src/components/SkillEvolutionPanel.tsx:224` — `{/* ★ [설계 §5.7 Skill Evolution] 「제안 카드마다 **실패 근거, 현재 규칙,`

### DATA-05 · Reference Registry → 공식 근거 등록부

- **주석** · `frontend/src/components/KnowledgeHubPanel.tsx:551` — `/** [설계 §5.6 Registry 화면 공통 · Reference Registry 특화]`

### DATA-28 · ACTUAL → 실적

- **문자열 확인 필요** · `frontend/src/lib/planningApi.ts:8` — `export const VALUE_KINDS = ['ACTUAL', 'PLAN', 'FORECAST', 'SCENARIO'] as const;`

### DEC-03 · Decision Ledger → 의사결정 원장

- **주석** · `frontend/src/components/AdvisorPanel.tsx:708` — `{/* 결정 이력 (Decision Ledger) */}`

### PROD-02 · 경영 시스템 → 제조 경영 시스템

- **주석** · `frontend/src/design/DataState.tsx:3` — `// 감사 지적(경영 시스템에서 매우 위험한 표현):`

### PROD-18 · Mega Project → 통합 제작 프로젝트

- **사용자 노출 유력** · `frontend/src/components/MegaBoardroomPanel.tsx:47` — `return <div className="p-10 text-gray-100 text-center">Not a Mega Project</div>;`

### RUN-04 · Capability Manifest → 앱 권한 선언서

- **주석** · `frontend/src/features/collaboration/CollaborationHub.tsx:7` — `//   ③ 앱이 요구하는 권한(Capability Manifest)과 "별도 로그인 없음" — 자체 로그인 화면을 만난`

### UI-09 · Administration → 시스템 관리

- **주석** · `frontend/src/components/AdminConsolePanel.tsx:1` — `// [UI 설계서 §5.8 Settings & Administration Console] 환경설정·관리자.`

### UI-10 · Master Data → 기준정보 관리

- **주석** · `frontend/src/components/EnterprisePage.tsx:189` — `/** §5.1 상단 KPI **최대 4개**. 「업무 도메인 / Master Data / 연결 / 근거 충실도」를 기본으로`

## 5. 완료 판정

- 사용자에게 보이는 문자열은 권장 용어 또는 승인된 병기 방식으로 표시됩니다.
- 과거 별칭은 검색·이력에서만 찾을 수 있고 신규 UI 제목·메뉴·버튼에는 나타나지 않습니다.
- 기술 표준명은 API·DB·코드 호환성을 유지하며 사용자 UI 변경과 분리됩니다.
- 변경한 화면군은 1280×720과 1440×900에서 시각 검증합니다.

## 6. 재생성

```powershell
venv\Scripts\python.exe scripts\audit_terminology_usage.py
```
