import React, { useEffect, useState } from 'react';

import { useFactoryStore } from './store/useFactoryStore';

import { Group, Panel, Separator } from 'react-resizable-panels';

import ControlPanel from './components/ControlPanel';
import TimelinePanel from './components/TimelinePanel';
import PreviewPanel from './components/PreviewPanel';
import WorkflowStrip from './components/WorkflowStrip';
import AgentMasterPanel from './components/AgentMasterPanel';
import GovernanceConsole from './components/GovernanceConsole';
import ShadowModePanel from './components/ShadowModePanel';
import WorkspacePanel from './components/WorkspacePanel';
import ProgramAdminPanel from './components/ProgramAdminPanel';
import { PlanningPanel } from './components/PlanningPanel';
import { BriefingPanel } from './components/BriefingPanel';
import FormatMasterPanel from './components/FormatMasterPanel';
import { SkillEvolutionPanel } from './components/SkillEvolutionPanel';
// [CL-1] 협업 허브 — 앱 전달·수락·내 앱. 오버레이 boolean 을 4개 만들지 않고
//   하나의 허브 안에서 내부 view 를 관리한다(작업서 §CL-FE-01).
import { CollaborationHub } from './features/collaboration/CollaborationHub';
import { KnowledgeHubPanel } from './components/KnowledgeHubPanel';
import { MasterDataPanel } from './components/MasterDataPanel';
import { WorkStandardPanel } from './components/WorkStandardPanel';
import { OrgChartPanel } from './components/OrgChartPanel';
import { UserSwitcher } from './components/UserSwitcher';
import { CrosswalkPanel } from './components/CrosswalkPanel';
import { TelemetryPanel } from './components/TelemetryPanel';
import { AdvisorPanel } from './components/AdvisorPanel';
import MegaBoardroomPanel from './components/MegaBoardroomPanel';
import ErrorBoundary from './components/ErrorBoundary';
import ServerLogPopup from './components/ServerLogPopup';
// [UIUX-AUDIT-30 §3] 16개 동급 버튼 나열 → 1차 영역 + 영역별 전체 메뉴
import { GlobalNav, type NavGroup, type NavItem } from './components/GlobalNav';


export default function App() {
  const connectSSE = useFactoryStore((state) => state.connectSSE);
  const isConnected = useFactoryStore((state) => state.isConnected);
  const projects = useFactoryStore((state) => state.projects);
  const currentProjectId = useFactoryStore((state) => state.currentProjectId);
  const fetchProjects = useFactoryStore((state) => state.fetchProjects);
  const createProject = useFactoryStore((state) => state.createProject);
  const deleteProject = useFactoryStore((state) => state.deleteProject);
  const setCurrentProject = useFactoryStore((state) => state.setCurrentProject);
  const statePayload = useFactoryStore((state) => state.state);
  const releases = useFactoryStore((state) => state.releases);
  const viewingRelease = useFactoryStore((state) => state.viewingRelease);
  const fetchReleases = useFactoryStore((state) => state.fetchReleases);
  const viewRelease = useFactoryStore((state) => state.viewRelease);
  const closeRelease = useFactoryStore((state) => state.closeRelease);
  // deleteRelease 는 더 이상 목록에서 쓰지 않는다 — 서버가 삭제를 거부하고 사용 중단을
  //   안내한다(사용자 결정 2026-07-30). 스토어 액션 자체는 남겨둔다.
  const showAgentPanel = useFactoryStore((state) => state.showAgentPanel);
  const openAgentPanel = useFactoryStore((state) => state.openAgentPanel);
  const showFormatPanel = useFactoryStore((state) => state.showFormatPanel);
  const templates = useFactoryStore((state) => state.templates);
  const selectedTemplateId = useFactoryStore((state) => state.selectedTemplateId);
  const setSelectedTemplate = useFactoryStore((state) => state.setSelectedTemplate);
  const fetchTemplates = useFactoryStore((state) => state.fetchTemplates);

  const [newProjectId, setNewProjectId] = useState("");
  const [showSkillEvolution, setShowSkillEvolution] = useState(false);
  const [showKnowledgeHub, setShowKnowledgeHub] = useState(false);
  const [showMasterData, setShowMasterData] = useState(false);
  const [showWorkStandard, setShowWorkStandard] = useState(false);
  const [showOrgChart, setShowOrgChart] = useState(false);
  const [showCollaboration, setShowCollaboration] = useState(false);
  const [showCrosswalk, setShowCrosswalk] = useState(false);
  const [showTelemetry, setShowTelemetry] = useState(false);
  // [M0] 업무·데이터 설계 상담 — §4.3 F-DA-01: 런처와 프로젝트 화면 **양쪽에서** 접근 가능해야 한다
  const [showAdvisor, setShowAdvisor] = useState(false);
  // 데이터 거버넌스 콘솔 — 기능 확인용. 디자인 확정 후 개편 대상.
  const [showGovernance, setShowGovernance] = useState(false);
  // Shadow Mode — 후보를 병렬 검증하고 범위를 제한해 승격(§7.3).
  const [showShadow, setShowShadow] = useState(false);
  // 부서 워크스페이스 — 공유·복제·전사 승격 게이트(§9.3).
  const [showWorkspace, setShowWorkspace] = useState(false);
  // [M4] 경영계획 — 결정론적 계산(LLM 0콜). 디자인 확정 후 개편 대상.
  const [showPlanning, setShowPlanning] = useState(false);
  // [M5] 전사 브리핑 — 권한 범위 안의 상태 집계(LLM 0콜). 디자인 확정 후 개편 대상.
  const [showBriefing, setShowBriefing] = useState(false);
  const [activeTab, setActiveTab] = useState<"mega" | "vault" | "releases">("mega");
  const [projectType, setProjectType] = useState<"independent" | "mega">("independent");
  const [showLogPopup, setShowLogPopup] = useState(false);
  // 신규 프로젝트에 연결할 지식팩 선택 상태
  const [knowledgePacks, setKnowledgePacks] = useState<any[]>([]);
  const [packsBlocked, setPacksBlocked] = useState('');   // 권한으로 가려진 이유(비었으면 정상)
  const [selectedPackIds, setSelectedPackIds] = useState<string[]>([]);
  // [M1] 신규 프로젝트에 적용할 기준정보 도메인 태그(콤마구분)
  const [masterDomainsInput, setMasterDomainsInput] = useState('');
  // [M3] 외부 실측값(MCP) 병기 토글 (기본 off)
  const [mcpLiveGrounding, setMcpLiveGrounding] = useState(false);
  // [사용자 결정 2026-07-30] 프로그램 사용여부 제어 대상 — 삭제 대신 비활성화한다.
  const [adminProgram, setAdminProgram] = useState<{ id: string; name: string } | null>(null);

  // ★★ [2026-07-31 실측 결함] 사용자를 바꾸면 권한이 바뀌므로 **목록을 다시 불러야 한다.**
  //   `UserSwitcher` 는 전환 시 이 이벤트를 쏘면서 "목록도 권한에 따라 달라진다"고 적어 뒀지만
  //   듣는 곳이 없었다 — 전환 후에도 **이전 사용자의 목록이 그대로 남는다.**
  //   ⚠️ 통제가 서버에서 옳게 동작해도 화면이 옛 답을 들고 있으면 사용자에게는 같은 사고다.
  const [actingUserRev, setActingUserRev] = useState(0);
  useEffect(() => {
    const h = () => {
      setActingUserRev(v => v + 1);
      // [CL-4] ★★ SSE 도 **다시 연결한다.** `?as_user=` 가 URL 에 박혀 있으므로, 재연결하지
      //   않으면 스트림은 계속 **이전 사용자 주소**로 열려 있다 — 새 사용자의 알림은 안 오고,
      //   이전 사용자의 알림이 이 화면으로 계속 들어온다. 두 번째가 더 나쁘다.
      connectSSE();
    };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [connectSSE]);

  useEffect(() => {
    // 런처 진입 시 지식팩 목록 로드(생성 폼의 선택지)
    const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080';
    fetch(`${API}/api/v1/knowledge/packs`).then(r => r.ok ? r.json() : null)
      .then(r => {
        setKnowledgePacks(r?.data || []);
        // 권한 때문에 비었으면 그 이유를 들고 있는다 — "없다"와 "안 보인다"는 정반대다.
        setPacksBlocked(r?.blocked_reason || '');
      }).catch(() => {});
  }, [showKnowledgeHub, actingUserRev]); // 허브에서 팩을 만들고 닫으면·사용자를 바꾸면 갱신

  const isSubProject = (id: string) => projects.some(p => p.is_mega_project && id.startsWith(p.id + "_"));

  const selectedTemplateData = templates.find((t: any) => t.id === selectedTemplateId);

  useEffect(() => {
    connectSSE();
    fetchProjects();
    fetchReleases();
    fetchTemplates();
  }, [connectSSE, fetchProjects, fetchReleases, fetchTemplates]);

  // ── [UIUX-AUDIT-30 §3] 글로벌 내비게이션 정의 ─────────────────────────────
  // ★ 툴팁 문구를 그대로 `desc` 로 옮겼다. 툴팁은 키보드·터치에서 보이지 않아서, 지금까지
  //   «이 기능이 무엇인지»는 마우스 사용자만 알 수 있었다.
  const primaryNav: NavItem[] = [
    { id: 'advisor', icon: '🧭', label: '업무·데이터 설계 상담',
      desc: '무엇을 만들지 모를 때 — 선택형 대화로 필요한 데이터와 추진 순서를 정하고, 승인하면 프로젝트가 됩니다',
      onSelect: () => setShowAdvisor(true) },
    { id: 'collaboration', icon: '🤝', label: '협업·의사결정·발간',
      desc: '앱 전달·수락, 의사결정 패키지, 대내외 발간을 한 곳에서 — 수락해도 데이터 권한은 넓어지지 않습니다',
      onSelect: () => setShowCollaboration(true) },
    { id: 'briefing', icon: '🧭', label: '전사 브리핑',
      desc: '권한 범위 안의 전사 상태 — 내가 결정할 것·막힌 것·데이터 결손·비용 (LLM 0콜)',
      onSelect: () => setShowBriefing(true) },
  ];

  const navGroups: NavGroup[] = [
    {
      title: '데이터 기반',
      hint: '에이전트가 무엇을 근거로 답하는가를 정하는 곳입니다.',
      items: [
        { id: 'knowledge', icon: '📚', label: '지식 허브',
          desc: '도메인 참고자료(표준·논문·데이터)를 등록하고 프로젝트에 연결',
          onSelect: () => setShowKnowledgeHub(true) },
        { id: 'master', icon: '🗂', label: '기준정보 마스터',
          desc: '자재·공정·설비·KPI 골든 레코드 — 확정 조회로 모든 에이전트에 주입(모델 불변)',
          onSelect: () => setShowMasterData(true) },
        { id: 'crosswalk', icon: '🔗', label: '연계/크로스워크',
          desc: '외부 시스템(ERP/MES 등)의 키·필드를 기준정보와 매핑 — 초안→사용자 승인',
          onSelect: () => setShowCrosswalk(true) },
        { id: 'governance', icon: '🛡️', label: '데이터 거버넌스',
          desc: '조직 범위 노출·중복 기준정보·카탈로그 결손·데이터 계약·외부지표 준비도',
          onSelect: () => setShowGovernance(true) },
      ],
    },
    {
      title: '업무 기준과 조직',
      hint: '누가 무엇을 어떤 기준으로 판단하는가를 정합니다.',
      items: [
        { id: 'standard', icon: '📜', label: '업무표준',
          desc: '에이전트의 법규·사규 — 무엇을 어떤 기준으로 평가해 다음 단계로 넘기는지. 개정 시 구판 보존',
          onSelect: () => setShowWorkStandard(true) },
        { id: 'org', icon: '🏢', label: '조직·권한',
          desc: '부서·사용자·권한 — 부서는 기준정보라 개편하면 새 버전이 되고 구판은 이력으로 남습니다',
          onSelect: () => setShowOrgChart(true) },
        { id: 'agents', icon: '⚙️', label: '에이전트 통제소',
          desc: '각 에이전트의 역할·스킬·모델·순서·HOTL(전문가 개입)을 설정',
          onSelect: openAgentPanel },
        { id: 'skills', icon: '🧬', label: 'AI 스킬 진화',
          desc: '에이전트가 스스로 제안한 스킬 개선안 승인/반려',
          onSelect: () => setShowSkillEvolution(true) },
      ],
    },
    {
      title: '운영과 검증',
      hint: '만든 것을 실제로 돌리고, 돌린 결과를 확인합니다.',
      items: [
        { id: 'planning', icon: '📊', label: '경영계획',
          desc: '계획·실적·시나리오를 동일 기준선에서 비교 (결정론적 계산, LLM 0콜)',
          onSelect: () => setShowPlanning(true) },
        { id: 'workspace', icon: '🏢', label: '워크스페이스',
          desc: '부서 앱의 공유·복제와 전사 승격 게이트 — 계약·보안·품질·소유자 승인을 모두 통과해야 승격',
          onSelect: () => setShowWorkspace(true) },
        { id: 'shadow', icon: '🧪', label: 'Shadow Mode',
          desc: '새 규칙·모델을 실제 데이터에 병렬 적용해 비교하고, 승인된 범위에서만 제한 적용',
          onSelect: () => setShowShadow(true) },
        { id: 'telemetry', icon: '📈', label: 'LLM 텔레메트리',
          desc: '실제 사용 모델·폴백·소요시간 — 모델 불변성 실측',
          onSelect: () => setShowTelemetry(true) },
      ],
    },
  ];

  const handleCreateProject = async () => {
    if (!newProjectId.trim()) return;
    const masterDomains = masterDomainsInput.split(',').map((s) => s.trim()).filter(Boolean);
    const success = await createProject(newProjectId.trim(), selectedTemplateId, selectedPackIds, masterDomains, mcpLiveGrounding);
    if (success) {
      setNewProjectId("");
      setSelectedPackIds([]);
      setMasterDomainsInput("");
      setMcpLiveGrounding(false);
      setCurrentProject(newProjectId.trim());
    }
  };

  const isMegaProject = projects.find(p => p.id === currentProjectId)?.is_mega_project === true;

  const handleDeleteProject = async (id: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`⚠️ [경고] 프로젝트 볼트 '${name} (${id})'를 완전히 삭제하시겠습니까?\n이 작업은 물리 디스크의 모든 산출물을 지우며 복구할 수 없습니다.`)) return;
    
    const success = await deleteProject(id);
    if (success) {
      alert("프로젝트가 안전하게 삭제되었습니다.");
    } else {
      alert("프로젝트 삭제 중 에러가 발생했습니다.");
    }
  };

  const copyProject = useFactoryStore((s) => s.copyProject);
  const handleCopyProject = async (id: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newId = prompt(`'${name}' 시나리오를 복제합니다.\n새로운 프로젝트 ID를 입력하세요 (영문/숫자/하이픈):`, `${id}-copy`);
    if (!newId || !newId.trim()) return;
    const success = await copyProject(id, newId.trim());
    if (success) {
      alert("시나리오가 성공적으로 복제되었습니다.");
    }
  };

  // ⚠️ [이관 6/10] 에이전트 통제소는 이제 **모달**(`HubDialog`)이다. 종전처럼 여기서 조기
  //   반환하면 `#root` 안에 아무것도 남지 않고, 모달은 body 로 portal 되므로 **뒤가 빈 화면**이
  //   된다(배경 inert 처리도 대상이 사라진다). 다른 허브 화면들과 같이 런처 위에 겹쳐 띄운다.
  if (showFormatPanel) {
    return (
      <ErrorBoundary>
        <FormatMasterPanel />
      </ErrorBoundary>
    );
  }

  if (viewingRelease) {
    return (
      <ErrorBoundary>
        <div className="h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans overflow-hidden">
          <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6 shrink-0">
            <div className="flex items-center gap-4 min-w-0">
              <button onClick={closeRelease} className="text-sm font-bold text-gray-400 hover:text-gray-100 bg-gray-700 px-3 py-1.5 rounded transition-colors shrink-0">◀ 라이브러리</button>
              <h1 className="text-lg font-bold text-gray-100 truncate">
                📦 결과물 실행: <span className="text-emerald-400">{viewingRelease.project_name}</span>
                <span className="text-xs text-gray-500 font-normal ml-2">{viewingRelease.created_at}</span>
              </h1>
            </div>
          </header>
          <div className="flex-1 overflow-hidden">
            <PreviewPanel rawCode={viewingRelease.frontend_code_summary || ""} release={viewingRelease} />
          </div>
        </div>
      </ErrorBoundary>
    );
  }

  if (!currentProjectId) {
    return (
      <ErrorBoundary>
        {showSkillEvolution && (
          <SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />
        )}
        {showKnowledgeHub && (
          <KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />
        )}
        {showMasterData && (
          <MasterDataPanel onClose={() => setShowMasterData(false)} />
        )}
        {showWorkStandard && (
          <WorkStandardPanel onClose={() => setShowWorkStandard(false)} />
        )}
        {showOrgChart && (
          <OrgChartPanel onClose={() => setShowOrgChart(false)} />
        )}
        {showCollaboration && (
          <CollaborationHub
            onClose={() => setShowCollaboration(false)}
            // 라이브러리에 있는 릴리스를 그대로 선택지로 넘긴다 — 화면이 id 를 지어내지 않는다.
            releaseIds={releases.map((r: any) => r.release_id).filter(Boolean)}
          />
        )}
        {showCrosswalk && (
          <CrosswalkPanel onClose={() => setShowCrosswalk(false)} />
        )}
        {showTelemetry && (
          <TelemetryPanel onClose={() => setShowTelemetry(false)} />
        )}
        {showAdvisor && (
          <AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />
        )}
        {showGovernance && (
          <GovernanceConsole onClose={() => setShowGovernance(false)} />
        )}
        {/* ⚠️ 이 모달 목록은 이 파일에 **두 벌** 있다(프로젝트 없음 화면 / 있는 화면).
            한쪽에만 추가하면 특정 상태에서만 안 열린다 — 기존 중복이며 정리 대상이다. */}
        {showAgentPanel && <AgentMasterPanel />}
        {showShadow && (
          <ShadowModePanel onClose={() => setShowShadow(false)} />
        )}
        {showWorkspace && (
          <WorkspacePanel onClose={() => setShowWorkspace(false)} />
        )}
        {/* [사용자 결정 2026-07-30] 프로그램 사용여부 — 삭제 대신 비활성화 (IT 관리자) */}
        {adminProgram && (
          <ProgramAdminPanel
            releaseId={adminProgram.id}
            releaseName={adminProgram.name}
            onClose={() => setAdminProgram(null)}
            onChanged={fetchReleases}
          />
        )}
        {showPlanning && (
          <PlanningPanel onClose={() => setShowPlanning(false)} />
        )}
        {showBriefing && (
          <BriefingPanel onClose={() => setShowBriefing(false)} />
        )}
        <div className="min-h-screen w-full bg-gray-950 text-gray-100 flex flex-col font-sans">
          <header className="h-16 bg-gray-950/95 backdrop-blur-md border-b border-gray-700 flex items-center justify-between gap-2 px-3 xl:px-5 shrink-0 sticky top-0 z-10 overflow-hidden">
            <h1 className="text-xl 2xl:text-2xl font-bold tracking-tight text-gray-100 flex items-center gap-2 shrink-0">
              <span className="text-indigo-400">🏭 V5.2</span> Private AI Cockpit
            </h1>
            {/* ★ 사용자 전환기는 «기능»이 아니라 «지금 누구인가»다. 메뉴 안으로 숨기지 않는다 —
                권한 범위가 사람마다 다르므로 상시 보여야 한다(채택 결정 6항). */}
            <div className="flex items-center gap-3 min-w-0">
              <UserSwitcher />
              <GlobalNav
              // 1차 영역 — 매일 쓰는 진입점 3개. 넘기면 다시 «나열»이 된다.
              primary={primaryNav}
              groups={navGroups}
              right={
                <div className="relative shrink-0">
                  <button
                    onClick={() => setShowLogPopup(v => !v)}
                    title="서버 로그 보기"
                    className="flex items-center gap-2 bg-black/20 hover:bg-black/40 transition-colors px-1.5 2xl:px-3 py-1.5 rounded-full border border-white/5 cursor-pointer"
                  >
                    <span className="hidden 2xl:inline text-xs text-gray-400 font-medium">Network</span>
                    <div className={`w-2.5 h-2.5 rounded-full shadow-[0_0_8px] ${isConnected ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500 shadow-red-500/50 animate-pulse'}`} />
                  </button>
                  {showLogPopup && <ServerLogPopup onClose={() => setShowLogPopup(false)} />}
                  </div>
                }
              />
            </div>
          </header>

          <main className="flex-1 flex flex-col items-center p-8 overflow-y-auto w-full">
            <div className="w-full max-w-6xl flex flex-col gap-8">
              
              {/* Hero Section: 신규 프로젝트 생성 */}
              <div className="relative overflow-hidden bg-gray-900 border border-gray-700 rounded-2xl p-8 shadow-2xl">
                <h2 className="text-xl font-bold text-gray-100 mb-6 flex items-center gap-2 relative z-10">
                  ✨ 신규 프로젝트 개설
                </h2>
                <div className="flex items-end gap-6 flex-wrap relative z-10">
                  <div className="flex-[2] min-w-[200px]">
                    <label className="block text-sm font-medium text-gray-400 mb-2">Project ID (영문)</label>
                    <input
                      type="text"
                      value={newProjectId}
                      onChange={(e) => setNewProjectId(e.target.value)}
                      placeholder="예: smart-life-app"
                      className="w-full bg-gray-950 border border-gray-700 rounded-xl p-3.5 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 transition-colors shadow-inner"
                    />
                  </div>
                  <div className="flex-[3] min-w-[250px]">
                    <label className="block text-sm font-medium text-gray-400 mb-2">워크플로우 템플릿</label>
                    <select
                      value={selectedTemplateId}
                      onChange={(e) => setSelectedTemplate(e.target.value)}
                      className="w-full bg-gray-950 border border-gray-700 rounded-xl p-3.5 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 transition-colors shadow-inner"
                    >
                      {templates.length === 0 && <option value="default">기본 워크플로우</option>}
                      {templates.map((t) => (
                         <option key={t.id} value={t.id}>
                           {t.name || t.id}{t.builtin ? " (기본)" : ""}
                         </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* 📚 지식팩 연결 — 선택한 팩의 자료가 모든 에이전트 산출물의 그라운딩 기준이 된다 */}
                <div className="mt-4 relative z-10">
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    📚 연결할 지식팩 <span className="text-gray-600">(선택 — 등록된 도메인 자료를 참고해 산출물을 생성)</span>
                  </label>
                  {knowledgePacks.length === 0 ? (
                    packsBlocked ? (
                      /* 권한으로 가려진 경우 — 자료가 없다고 말하면 사용자는 등록하려 든다(잘못된 다음 행동) */
                      <div className="text-xs text-red-300 bg-red-900/20 border border-red-800/50 rounded-xl p-3">
                        <b>지식팩이 보이지 않습니다(자료가 없는 것이 아닙니다).</b> {packsBlocked}
                      </div>
                    ) : (
                      <div className="text-xs text-gray-500 bg-gray-950/60 border border-gray-700 rounded-xl p-3">
                        등록된 지식팩이 없습니다. 우측 상단 <b className="text-cyan-300">📚 지식 허브</b>에서 표준·논문 등 참고자료를 먼저 등록하세요.
                      </div>
                    )
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {knowledgePacks.map((p: any) => {
                        const on = selectedPackIds.includes(p.pack_id);
                        return (
                          <button key={p.pack_id} type="button"
                            onClick={() => setSelectedPackIds(prev => on ? prev.filter(x => x !== p.pack_id) : [...prev, p.pack_id])}
                            className={`text-xs font-bold px-3 py-1.5 rounded-full border transition-colors ${
                              on ? 'bg-cyan-900/50 border-cyan-500 text-cyan-200' : 'bg-gray-950 border-gray-700 text-gray-400 hover:border-gray-500'
                            }`}
                            title={p.description || p.pack_id}
                          >
                            {on ? '✓ ' : ''}{p.name} <span className="opacity-60 font-normal">({p.documents?.length || 0})</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* 🗂 기준정보 도메인 — 여기 지정한 도메인의 골든 레코드가 확정 조회로 산출물에 주입된다 */}
                <div className="mt-4 relative z-10">
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    🗂 기준정보 도메인 <span className="text-gray-600">(선택 — 콤마구분, 예: manufacturing. 해당 도메인 골든 레코드가 확정 주입됨)</span>
                  </label>
                  <input
                    type="text"
                    value={masterDomainsInput}
                    onChange={(e) => setMasterDomainsInput(e.target.value)}
                    placeholder="예: manufacturing, logistics"
                    className="w-full bg-gray-950 border border-gray-700 rounded-xl p-3 text-sm text-gray-200 focus:outline-none focus:border-emerald-500 transition-colors shadow-inner"
                  />
                  {/* [M3] 외부 실측값 병기 토글 (기본 off) */}
                  <label className="mt-2 flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                    <input type="checkbox" checked={mcpLiveGrounding} onChange={(e) => setMcpLiveGrounding(e.target.checked)} />
                    🔗 외부 실측값(MCP) 병기 <span className="text-gray-600">— 켜면 활성 연계 시스템의 실측값을 매 산출물에 참고로 병기(지연·쿼터 증가, 기본 off)</span>
                  </label>
                </div>

                <div className="mt-6 p-4 bg-gray-950/50 border border-gray-700 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="flex flex-col gap-2">
                    <label className="text-sm font-medium text-gray-300 mb-1">프로젝트 유형 선택</label>
                    <div className="flex gap-6">
                      <label className="flex items-center gap-2 cursor-pointer group">
                        <input type="radio" name="projectType" value="independent" checked={projectType === "independent"} onChange={() => setProjectType("independent")} className="hidden" />
                        <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${projectType === "independent" ? "border-indigo-400" : "border-gray-500 group-hover:border-gray-400"}`}>
                          {projectType === "independent" && <div className="w-2.5 h-2.5 bg-indigo-400 rounded-full"></div>}
                        </div>
                        <span className={`font-bold ${projectType === "independent" ? "text-indigo-300" : "text-gray-400"}`}>독립 프로젝트</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer group">
                        <input type="radio" name="projectType" value="mega" checked={projectType === "mega"} onChange={() => setProjectType("mega")} className="hidden" />
                        <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${projectType === "mega" ? "border-purple-400" : "border-gray-500 group-hover:border-gray-400"}`}>
                          {projectType === "mega" && <div className="w-2.5 h-2.5 bg-purple-400 rounded-full"></div>}
                        </div>
                        <span className={`font-bold ${projectType === "mega" ? "text-purple-300" : "text-gray-400"}`}>🌟 메가 프로젝트</span>
                      </label>
                    </div>
                    <div className="text-xs text-gray-500 mt-1 max-w-xl">
                      {projectType === "independent" 
                        ? "선택한 워크플로우를 따라 단일 목표를 수행하는 프로젝트입니다." 
                        : "여러 도메인(영업, 구매, 생산 등)의 에이전트 그룹이 동시에 병렬 협업하여 거대한 시나리오를 달성하는 대규모 프로젝트입니다."}
                    </div>
                  </div>
                  
                  <button
                    onClick={async () => {
                      if (!newProjectId.trim()) {
                        alert("먼저 상단의 Project ID를 입력해주세요!");
                        return;
                      }
                      if (projectType === "independent") {
                        await handleCreateProject();
                      } else {
                        const { useFactoryStore } = await import('./store/useFactoryStore');
                        const success = await useFactoryStore.getState().createMegaProject(newProjectId.trim(), selectedTemplateId);
                        if (success) {
                          setNewProjectId("");
                          setCurrentProject(newProjectId.trim());
                        }
                      }
                    }}
                    className={`shrink-0 w-full md:w-32 h-[46px] rounded-xl font-bold text-white shadow-lg transition-all hover:scale-[1.02] ${
                      projectType === "independent"
                        ? "bg-indigo-600 hover:bg-indigo-500"
                        : "bg-purple-600 hover:bg-purple-500"
                    }`}
                  >
                    프로젝트 생성
                  </button>
                </div>

                {selectedTemplateData && selectedTemplateData.description && (
                  <div className="text-sm text-gray-300 mt-4 bg-gray-950/50 p-3 rounded-lg border border-gray-700 inline-block">
                    ℹ️ {selectedTemplateData.description}
                  </div>
                )}
              </div>

              {/* Tabs Section */}
              <div className="flex items-center gap-6 border-b border-gray-700 pb-2">
                <button 
                  onClick={() => setActiveTab("mega")}
                  className={`text-lg font-bold pb-2 border-b-2 transition-all ${activeTab === "mega" ? "text-purple-400 border-purple-500" : "text-gray-400 border-transparent hover:text-gray-200"}`}
                >
                  🌟 메가 프로젝트
                </button>
                <button 
                  onClick={() => setActiveTab("vault")}
                  className={`text-lg font-bold pb-2 border-b-2 transition-all ${activeTab === "vault" ? "text-indigo-400 border-indigo-500" : "text-gray-400 border-transparent hover:text-gray-200"}`}
                >
                  📂 독립 가동 대장
                </button>
                <button 
                  onClick={() => setActiveTab("releases")}
                  className={`text-lg font-bold pb-2 border-b-2 transition-all ${activeTab === "releases" ? "text-emerald-400 border-emerald-500" : "text-gray-400 border-transparent hover:text-gray-200"}`}
                >
                  📦 결과물 라이브러리
                </button>
              </div>

              {/* Tab Content */}
              {activeTab === "mega" && (
                <div className="animate-fade-in flex flex-col gap-6">
                  {projects.filter(p => p.is_mega_project).length === 0 && (
                    <div className="text-gray-500 text-center py-10 bg-white/5 border border-white/5 rounded-xl">
                      가동 중인 메가 프로젝트가 없습니다.
                    </div>
                  )}
                  {projects.filter(p => p.is_mega_project).map((mega) => {
                    const subs = projects.filter(p => p.parent_project_id === mega.id);
                    return (
                      <div key={mega.id} className="bg-gray-900 border border-gray-700 hover:border-purple-500/50 rounded-2xl p-6 shadow-2xl relative group transition-colors">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-3">
                            <h3 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-indigo-400">🌟 {mega.name}</h3>
                            <span className="text-xs px-2 py-1 bg-purple-900/40 text-purple-300 border border-purple-700/50 rounded-full font-mono">Mega Vault</span>
                          </div>
                          <button onClick={(e) => handleDeleteProject(mega.id, mega.name, e)} className="text-xs text-red-400 hover:text-red-300 bg-red-950/40 hover:bg-red-900/60 border border-red-900/50 rounded-lg px-3 py-1.5 transition-colors">🗑️ 완전 삭제</button>
                        </div>
                        <div className="flex items-center gap-4 mb-4">
                          <span className="text-xs bg-purple-900/60 text-purple-200 border border-purple-700/50 rounded px-2 py-1">
                            {templates.find((t: any) => t.id === mega.template_id)?.name || mega.template_id || "템플릿 없음"}
                          </span>
                          <div className="flex-1 max-w-xs">
                            {(() => {
                              const megaTotal = subs.reduce((sum, s) => sum + (s.total_tasks || 0), 0) + (mega.total_tasks || 0);
                              const megaCompleted = subs.reduce((sum, s) => sum + (s.completed_tasks || 0), 0) + (mega.completed_tasks || 0);
                              const progress = megaTotal > 0 ? Math.round((megaCompleted / megaTotal) * 100) : 0;
                              return megaTotal > 0 ? (
                                <div className="flex items-center gap-2">
                                  <div className="flex-1 h-1.5 bg-gray-800 border border-gray-700 rounded-full overflow-hidden">
                                    <div className="h-full bg-gradient-to-r from-purple-500 to-indigo-500" style={{ width: `${progress}%` }}></div>
                                  </div>
                                  <span className="text-xs text-gray-400 font-medium">{progress}%</span>
                                </div>
                              ) : null;
                            })()}
                          </div>
                        </div>
                        <button onClick={() => setCurrentProject(mega.id)} className="w-full mb-6 bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 rounded-xl flex items-center justify-center gap-2 transition-transform hover:scale-[1.01] shadow-lg">🔌 메가 프로젝트 보드룸 진입</button>
                        
                        {/* 서브 프로젝트 그리드 최적화 */}
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                          {subs.map(sub => (
                            <div key={sub.id} className="bg-gray-900 border border-gray-700 rounded-xl p-4 hover:border-indigo-500/50 hover:bg-gray-900 transition-all flex flex-col relative group/sub shadow-inner">
                              <div className="flex items-start justify-between mb-1">
                                <h4 className="text-sm font-bold text-indigo-300 truncate pr-2">🔹 {sub.name}</h4>
                                <button onClick={(e) => handleDeleteProject(sub.id, sub.name, e)} className="opacity-0 group-hover/sub:opacity-100 text-[10px] text-red-400 hover:text-red-300 transition-opacity">🗑</button>
                              </div>
                              {sub.total_tasks && sub.total_tasks > 0 && (
                                <div className="w-full h-1 bg-gray-800 rounded-full mb-1 overflow-hidden">
                                  <div className="h-full bg-indigo-500" style={{ width: `${Math.round(((sub.completed_tasks || 0) / (sub.total_tasks || 1)) * 100)}%` }}></div>
                                </div>
                              )}
                              <span className="text-[10px] text-gray-500 font-mono mb-4">{sub.id}</span>
                              <button onClick={() => setCurrentProject(sub.id)} className="w-full mt-auto bg-gray-800 hover:bg-indigo-600 text-gray-300 hover:text-white text-xs font-bold py-2 rounded-lg transition-colors border border-gray-700 hover:border-transparent">서브 진입</button>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {activeTab === "vault" && (
                <div className="animate-fade-in flex flex-col gap-6">
                  {projects.filter(p => !p.is_mega_project && !p.parent_project_id && !isSubProject(p.id)).length === 0 && (
                    <div className="text-gray-500 text-center py-10 bg-gray-900 border border-gray-700 rounded-xl">
                      가동 중인 독립 프로젝트가 없습니다.
                    </div>
                  )}
                  {/* 일반 프로젝트 그리드 */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {projects.filter(p => !p.is_mega_project && !p.parent_project_id && !isSubProject(p.id)).map((proj) => (
                      <div key={proj.id} className="bg-gray-900 border border-gray-700 hover:border-blue-500/50 hover:bg-gray-900 rounded-2xl p-6 transition-all shadow-xl flex flex-col group relative">
                        <div className="flex items-start justify-between mb-4 gap-2">
                          <div className="flex flex-col gap-1 min-w-0">
                            <h3 className="text-lg font-bold text-blue-300 truncate">{proj.name}</h3>
                            <span className="text-[10px] text-gray-500 font-mono truncate">{proj.id}</span>
                          </div>
                          <div className="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                            <button
                              onClick={(e) => handleCopyProject(proj.id, proj.name, e)}
                              className="bg-blue-950/60 hover:bg-blue-800 text-blue-400 hover:text-white border border-blue-900/50 rounded p-1.5 transition-colors"
                              title="복제"
                            >🧬</button>
                            <button
                              onClick={(e) => handleDeleteProject(proj.id, proj.name, e)}
                              className="bg-red-950/60 hover:bg-red-800 text-red-400 hover:text-white border border-red-900/50 rounded p-1.5 transition-colors"
                              title="삭제"
                            >🗑️</button>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 mb-3">
                          <span className="text-xs bg-indigo-900/40 text-indigo-300 border border-indigo-700/50 rounded px-2 py-0.5 truncate">
                            {templates.find((t: any) => t.id === proj.template_id)?.name || proj.template_id || "기본 워크플로우"}
                          </span>
                          {proj.total_tasks && proj.total_tasks > 0 && (
                            <div className="flex items-center gap-1.5 flex-1 ml-2 text-xs text-gray-400">
                              <div className="flex-1 h-1 bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full bg-blue-500" style={{ width: `${Math.round(((proj.completed_tasks || 0) / (proj.total_tasks || 1)) * 100)}%` }}></div>
                              </div>
                              <span className="shrink-0">{Math.round(((proj.completed_tasks || 0) / (proj.total_tasks || 1)) * 100)}%</span>
                            </div>
                          )}
                        </div>
                        <div className="flex-1 text-xs text-gray-400 mb-6 overflow-hidden line-clamp-3 leading-relaxed">
                          {proj.initial_idea || "독립 환경에서 가동 대기 중입니다."}
                        </div>
                        <button
                          onClick={() => setCurrentProject(proj.id)}
                          className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-xl transition-transform hover:scale-[1.02] shadow-lg"
                        >
                          🔌 통제실 진입
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {activeTab === "releases" && (
                <div className="animate-fade-in">
                  {releases.length === 0 ? (
                    <div className="bg-gray-900 border border-dashed border-gray-700 rounded-2xl p-10 flex flex-col items-center justify-center text-center">
                      <div className="text-4xl mb-4 opacity-50">📦</div>
                      <div className="text-gray-400 font-medium">아직 배포된 결과물이 없습니다.</div>
                      <div className="text-gray-500 text-sm mt-2">프로젝트 통제실에서 "최종 결과물 저장(배포)"을 완료하면 이곳에 표시됩니다.</div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-4 gap-6">
                      {releases.map((rel: any) => {
                        // [사용자 결정 2026-07-30] 사용 중단된 프로그램은 실행 버튼을 열지 않는다.
                        //   ⚠️ 화면 차단은 통제가 아니다 — 서버가 실행 payload 를 직접 막는다
                        //   (`GET /factory/library/item/{id}`). 여기서 막는 것은 사용자가
                        //   눌러본 뒤에야 알게 되는 일을 없애기 위한 것이다.
                        const life = rel.lifecycle_status || 'active';
                        const blocked = life === 'disabled';
                        return (
                        <div key={rel.release_id} className={`bg-gray-900 border rounded-2xl p-5 transition-all flex flex-col shadow-xl group ${blocked ? 'border-red-900/50 opacity-75' : 'border-gray-700 hover:border-emerald-500/60 hover:bg-gray-900'}`}>
                          <div className="flex items-start justify-between mb-3 gap-2">
                            <h3 className={`text-base font-bold truncate ${blocked ? 'text-gray-400 line-through' : 'text-emerald-300'}`}>{rel.project_name}</h3>
                            <button
                              onClick={() => setAdminProgram({ id: rel.release_id, name: rel.project_name })}
                              className="opacity-0 group-hover:opacity-100 text-xs text-gray-300 hover:text-gray-100 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded px-2 py-1 shrink-0 transition-all"
                              title="사용여부 제어 (IT 관리자) — 삭제하지 않고 비활성화합니다"
                            >⚙</button>
                          </div>
                          {/* 사용여부를 목록에서 보여준다 — 없으면 눌러본 뒤에야 막혔음을 안다. */}
                          {life !== 'active' && (
                            <div className={`mb-3 text-[11px] rounded-lg px-2 py-1.5 border ${blocked ? 'bg-red-950/40 text-red-300 border-red-800/60' : 'bg-amber-900/30 text-amber-300 border-amber-700/60'}`}>
                              <b>{blocked ? '⛔ 사용 중단' : '⚠ 중단 예고'}</b>
                              {rel.lifecycle_reason ? ` — ${rel.lifecycle_reason}` : ''}
                              {rel.replacement_release_id
                                ? <div className="text-indigo-300 mt-0.5">대체: {rel.replacement_release_id}</div>
                                : (blocked ? <div className="text-gray-400 mt-0.5">대체 프로그램 미지정 — 관리자에게 문의</div> : null)}
                            </div>
                          )}
                          <div className="text-[11px] text-gray-400 mb-6 bg-gray-950 p-2 rounded-lg border border-gray-700">
                            <div className="mb-1 text-gray-300">📅 {rel.created_at}</div>
                            <div>✓ 태스크 {rel.task_count}개 완료</div>
                          </div>
                          {blocked ? (
                            <button
                              disabled
                              title="IT 관리자가 사용을 중단시켰습니다. 기록은 보존되어 있습니다."
                              className="mt-auto w-full bg-gray-800 text-gray-500 font-bold py-2.5 rounded-xl cursor-not-allowed border border-gray-700"
                            >⛔ 사용 중단됨</button>
                          ) : (!rel.deliverable_type || rel.deliverable_type === "software_app") ? (
                            <button
                              onClick={() => viewRelease(rel.release_id)}
                              className="mt-auto w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 rounded-xl transition-transform hover:scale-[1.02] shadow-lg"
                            >▶ 앱 실행 (Run)</button>
                          ) : (
                            <button
                              onClick={() => viewRelease(rel.release_id)}
                              className="mt-auto w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2.5 rounded-xl transition-transform hover:scale-[1.02] shadow-lg"
                            >📄 보고서 열람</button>
                          )}
                        </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </main>
        </div>
      </ErrorBoundary>
    );
  }

  // 🌟 메가 프로젝트 보드룸 — 서브 프로젝트 현황을 한눈에 보는 관제 화면
  if (isMegaProject) {
    return (
      <ErrorBoundary>
        <MegaBoardroomPanel />
      </ErrorBoundary>
    );
  }

  // 🚀 [3단 레이아웃 독립 스크롤 최적화 설계 구조 적용]
  return (
    <ErrorBoundary>
      <div className="h-screen w-screen bg-gray-950 text-gray-100 flex flex-col font-sans overflow-hidden">
        <header className="h-14 bg-gray-950/95 backdrop-blur border-b border-gray-700 flex items-center justify-between px-6 shrink-0 z-20">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setCurrentProject(null)}
              className="text-sm font-bold text-gray-400 hover:text-gray-100 flex items-center gap-1 bg-gray-700 px-3 py-1.5 rounded transition-colors"
            >
              ◀ 런처 복귀
            </button>
            <h1 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2 truncate max-w-xl">
              <span className="text-blue-400 truncate">[{projects.find(p => p.id === currentProjectId)?.name || currentProjectId}]</span> 통제실
            </h1>
          </div>
          <div className="relative flex items-center gap-3">
            <button
              onClick={() => setShowAdvisor(true)}
              className="text-xs font-bold text-indigo-200 bg-indigo-900/50 hover:bg-indigo-800/70 border border-indigo-700/60 px-3 py-1.5 rounded-lg transition-colors"
              title="업무·데이터 설계 상담 — 필요한 데이터와 추진 순서를 선택형 대화로 정합니다"
            >
              🧭 설계 상담
            </button>
            <button
              onClick={() => setShowGovernance(true)}
              className="text-xs font-bold text-slate-200 bg-slate-800/70 hover:bg-slate-700/70 border border-slate-600/60 px-3 py-1.5 rounded-lg transition-colors"
              title="조직 범위 노출·중복 기준정보·카탈로그 결손·데이터 계약 상태·외부지표 준비도"
            >
              🛡️ 거버넌스
            </button>
            <button
              onClick={() => setShowShadow(true)}
              className="text-xs font-bold text-slate-200 bg-slate-800/70 hover:bg-slate-700/70 border border-slate-600/60 px-3 py-1.5 rounded-lg transition-colors"
              title="후보 병렬 검증 · 제한적 승격(§7.3)"
            >
              🧪 Shadow
            </button>
            <button
              onClick={() => setShowWorkspace(true)}
              className="text-xs font-bold text-slate-200 bg-slate-800/70 hover:bg-slate-700/70 border border-slate-600/60 px-3 py-1.5 rounded-lg transition-colors"
              title="공유·복제·전사 승격 게이트(§9.3)"
            >
              🏢 워크스페이스
            </button>
            <button 
              onClick={() => setShowLogPopup(v => !v)}
              title="서버 로그 보기"
              className="flex items-center gap-3 hover:bg-white/10 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
            >
              <span className="text-sm text-gray-400 font-medium">실시간 통신망:</span>
              <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
            </button>
            {showLogPopup && <ServerLogPopup onClose={() => setShowLogPopup(false)} />}
          </div>
        </header>

        {showAdvisor && (
          <AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />
        )}
        {showGovernance && (
          <GovernanceConsole onClose={() => setShowGovernance(false)} />
        )}
        {/* ⚠️ 이 모달 목록은 이 파일에 **두 벌** 있다(프로젝트 없음 화면 / 있는 화면).
            한쪽에만 추가하면 특정 상태에서만 안 열린다 — 기존 중복이며 정리 대상이다. */}
        {showAgentPanel && <AgentMasterPanel />}
        {showShadow && (
          <ShadowModePanel onClose={() => setShowShadow(false)} />
        )}
        {showWorkspace && (
          <WorkspacePanel onClose={() => setShowWorkspace(false)} />
        )}
        {showPlanning && (
          <PlanningPanel onClose={() => setShowPlanning(false)} />
        )}
        {showBriefing && (
          <BriefingPanel onClose={() => setShowBriefing(false)} />
        )}

        {/* 전체 워크플로우 진행 스트립 */}
        <WorkflowStrip />

        {/* 3단 레이아웃 — 드래그로 크기 조절 가능 (react-resizable-panels) */}
        <Group orientation="horizontal" className="flex-1 w-full h-full overflow-hidden flex">
          {/* 좌측: 제어반 */}
          <Panel defaultSize="22%" minSize="14%" className="h-full">
            <div className="bg-gray-800 flex flex-col h-full overflow-hidden">
              <ControlPanel />
            </div>
          </Panel>
          <Separator className="w-1.5 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize shrink-0" />

          {/* 중앙: 슈퍼바이저 콘솔 */}
          <Panel defaultSize="40%" minSize="20%" className="h-full">
            <div className="bg-gray-900 flex flex-col relative h-full overflow-hidden">
              <TimelinePanel />
            </div>
          </Panel>
          <Separator className="w-1.5 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize shrink-0" />

          {/* 우측: 다중 탭 및 렌더링 샌드박스 */}
          <Panel defaultSize="38%" minSize="20%" className="h-full">
            <div className="bg-gray-800 flex flex-col h-full overflow-hidden">
              <PreviewPanel rawCode={statePayload?.frontend_code_summary || ""} />
            </div>
          </Panel>
        </Group>
      </div>
    </ErrorBoundary>
  );
}
