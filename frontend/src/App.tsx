import React, { useCallback, useEffect, useState } from 'react';

import { useFactoryStore } from './store/useFactoryStore';

import { Group, Panel, Separator } from 'react-resizable-panels';

import ControlPanel from './components/ControlPanel';
import { AdaptiveProductionStudio } from './factory/AdaptiveProductionStudio';
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
import { TerminologyGlossaryPanel } from './components/TerminologyGlossaryPanel';
import { MasterDataPanel } from './components/MasterDataPanel';
import { WorkStandardPanel } from './components/WorkStandardPanel';
import { OrgChartPanel } from './components/OrgChartPanel';
import { LoginPage } from './components/LoginPage';
import { SessionBar } from './components/SessionBar';
import { CrosswalkPanel } from './components/CrosswalkPanel';
import { TelemetryPanel } from './components/TelemetryPanel';
import { AdvisorPanel } from './components/AdvisorPanel';
import MegaBoardroomPanel from './components/MegaBoardroomPanel';
import ErrorBoundary from './components/ErrorBoundary';
import ServerLogPopup from './components/ServerLogPopup';
// [UIUX-AUDIT-30 §3] 16개 동급 버튼 나열 → 1차 영역 + 영역별 전체 메뉴
import { GlobalNav, type NavGroup, type NavItem } from './components/GlobalNav';
import { actingScope, governanceBlockReason, type ActingScope } from './lib/actingScope';
import { AgentGovernancePanel } from './components/AgentGovernancePanel';
import { EnterprisePage } from './components/EnterprisePage';
// [BDR-5 / Wave H] 데이터 준비 보드 — 「지금 무엇까지 믿고 만들 수 있는가」
import { CalcApprovalPanel } from './components/CalcApprovalPanel';
import { DataPrepPanel } from './components/DataPrepPanel';
import { PathCalcPanel } from './components/PathCalcPanel';
// [G4 / Wave H] 시나리오 시뮬레이션 — 고정된 기준선 위에서만 계산한다
import { ScenarioPanel } from './components/ScenarioPanel';
// [Wave G 11.4] 의사결정 안건 — 3관점 검토서·책임자·기한·근거 계보
import { DecisionPanel } from './components/DecisionPanel';
// [I-4 7 / Wave H-4] 운영 승격 — 후보를 운영으로 올리는 단 하나의 문
import { ReleasePromotionPanel } from './components/ReleasePromotionPanel';
import { CompanyContextBar } from './components/CompanyContextBar';
import { BuildPage } from './components/BuildPage';
import { BuildStartDialog } from './components/BuildStartDialog';
import { Banner } from './design/HubShell';
import { API_BASE_URL, getSessionToken, setActingUser, setSessionToken } from './lib/api';


function AppShell() {
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
  const fetchTemplates = useFactoryStore((state) => state.fetchTemplates);

  // ★★★ [UI 설계서 §3.2 · §3.4] **첫 화면은 경영 홈(Decision Canvas)이다.**
  //   Software Factory 는 거기서 들어가는 Immersive Studio 다 — 설계는 「경영 홈에서 Studio 로
  //   이동한다」고 방향을 못박았는데, 실제로는 「신규 프로젝트 개설」 폼이 첫 화면이었다
  //   (2026-07-28 리버스엔지니어링 AS-IS 그대로. 화면 이관은 개별 화면만 옮겼다).
  //   ⚠️ URL 라우터가 아직 없으므로 상태로 둔다 — 설계 §3.3 은 「React Router 도입 여부와
  //     무관하게 URL 은 새로고침·공유가 가능한 상태 계약으로 관리한다」고 했고, 그 계약은
  //     라우터를 넣을 때 이 한 값을 URL 로 올리면 된다.
  const [space, setSpace] = useState<'enterprise' | 'build'>('enterprise');
  // 경영 홈 → Factory, 목록 → 프로젝트처럼 화면 문맥이 바뀔 때 이전 화면의 스크롤 위치를
  // 가져오면 핵심 행동과 헤더가 화면 밖에서 시작한다. 새 화면은 항상 문서 맨 위에서 시작한다.
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [space, currentProjectId]);
  // §5.2 «새 업무 만들기» — 생성은 목록면에서 분리된 별도 흐름이다(설계 `/build/start`).
  const [buildStart, setBuildStart] = useState(false);
  const [showSkillEvolution, setShowSkillEvolution] = useState(false);
  const [showKnowledgeHub, setShowKnowledgeHub] = useState(false);
  const [showDataPrep, setShowDataPrep] = useState(false);
  const [showCalcApproval, setShowCalcApproval] = useState(false);
  const [showPathCalc, setShowPathCalc] = useState(false);
  const [showScenario, setShowScenario] = useState(false);
  const [showDecisionPkg, setShowDecisionPkg] = useState(false);
  const [showPromotion, setShowPromotion] = useState(false);
  // 기술·제품 용어 전환 사전 — 사용자 권장 용어와 현재 기술 용어를 함께 확인하는 임시 페이지.
  const [showTerminology, setShowTerminology] = useState(false);
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
  // [트랙 E 2단계] Adaptive Production Studio — **병행 카나리**.
  // ⚠️ 기존 3패널을 대체하지 않는다(구현 명세 §7-7: 기능 회귀·시각 게이트 통과 후 제거).
  //   지금 신규 화면에는 Sprint 시작·정지·재개·HOTL 승인이 없으므로, 종전 통제실을 닫으면
  //   그 기능이 사라진다. 그래서 열고 닫는 오버레이로 둔다.
  const [showStudio, setShowStudio] = useState(false);
  // [P2-2] Agent Governance Center — 조직 자산의 범위·권한·승인(설계 §8.3~§8.6).
  const [showAgentGov, setShowAgentGov] = useState(false);
  // [P2-4] 거버넌스 계열 메뉴를 «누르기 전에» 막기 위한 자격. 판정은 `actingScope` 한 곳에 있다.
  const [scope, setScope] = useState<ActingScope | null>(actingScope.peek());
  useEffect(() => { actingScope.load().then(setScope).catch(() => setScope(null)); }, []);
  useEffect(() => actingScope.subscribe(setScope), []);
  const govBlocked = governanceBlockReason(scope);
  const [showLogPopup, setShowLogPopup] = useState(false);
  // 신규 프로젝트에 연결할 지식팩 선택 상태
  const [knowledgePacks, setKnowledgePacks] = useState<any[]>([]);
  const [packsBlocked, setPacksBlocked] = useState('');   // 권한으로 가려진 이유(비었으면 정상)
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
      // [CL-4] ★★ SSE 도 **다시 연결한다.**
      //   ⚠️ [P0-1C] 종전 이유는 「`?as_user=` 가 URL 에 박혀 있어서」였다. 그 쿼리는 사라졌고
      //     이제 1회용 접속표로 연결한다(P0-1B). 그래도 **재연결은 여전히 필요하다** — 표는
      //     발급 시점의 세션으로 사용자를 확정하므로, 사용자가 바뀌면 열려 있는 스트림은
      //     계속 **이전 사용자의 스트림**이다. 새 사용자의 알림은 안 오고 이전 사용자의
      //     알림이 이 화면으로 들어온다. 두 번째가 더 나쁘다.
      connectSSE();
    };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [connectSSE]);

  // ★★★ [G1-C1.2] 회사·사업부를 바꾸면 **SSE 를 다시 맺는다.**
  //   티켓에 조직 범위가 봉인돼 있어서, 스트림을 그대로 두면 목록은 A 인데 실시간 이벤트는
  //   계속 B 로 흐른다. 회사 선택기와 실시간 데이터 범위가 어긋나면 사용자는 자기가 보는
  //   숫자가 어느 회사 것인지 알 수 없다 — 경영 화면에서 그것은 오답보다 나쁘다.
  useEffect(() => {
    const h = () => { connectSSE(); };
    window.addEventListener('factory:enterprise-context-changed', h);
    return () => window.removeEventListener('factory:enterprise-context-changed', h);
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
        { id: 'terminology', icon: '📖', label: '기술·제품 용어집',
          desc: '현재 용어·권장 사용자 용어·기술 표준명을 함께 보는 전환 사전',
          onSelect: () => setShowTerminology(true) },
        { id: 'master', icon: '🗂', label: '기준정보 마스터',
          desc: '자재·공정·설비·KPI 골든 레코드 — 확정 조회로 모든 에이전트에 주입(모델 불변)',
          onSelect: () => setShowMasterData(true) },
        { id: 'dataprep', icon: '📥', label: '업무 데이터 준비',
          desc: '업무키트 적용 · 원천 결속 · 파일 판 인증 · 준비 상태 보드',
          onSelect: () => setShowDataPrep(true) },
        { id: 'scenario', icon: '📈', label: '시나리오 시뮬레이션',
          desc: '환율·도입 지연·전력단가 → 생산량·재고·현금·손익 (고정 기준선 기준)',
          onSelect: () => setShowScenario(true) },
        { id: 'path-calc', icon: '🧮', label: '경로 계산',
          desc: '승인된 관계를 따라가 부족량·생산가능량·매출 이연을 계산 — 막히면 무엇이 없는지 말합니다(LLM 0콜)',
          onSelect: () => setShowPathCalc(true) },
        { id: 'decision-pkg', icon: '🧭', label: '의사결정 안건',
          desc: '영향 경로 · 3관점 검토서 · 실행 책임자와 기한 · 근거 계보',
          onSelect: () => setShowDecisionPkg(true) },
        { id: 'promotion', icon: '🚀', label: '운영 승격',
          desc: '후보 판을 운영으로 — 계약·물질화·정적검사·승인·데이터 준비도 다섯 검사',
          onSelect: () => setShowPromotion(true) },
        { id: 'crosswalk', icon: '🔗', label: '연계/크로스워크',
          desc: '외부 시스템(ERP/MES 등)의 키·필드를 기준정보와 매핑 — 초안→사용자 승인',
          onSelect: () => setShowCrosswalk(true) },
        { id: 'governance', icon: '🛡️', label: '데이터 거버넌스',
          desc: '조직 범위 노출·중복 기준정보·카탈로그 결손·데이터 계약·외부지표 준비도',
          // ★ 서버가 403 을 줄 자리를 **누르기 전에** 말한다(설계 §10 수용 기준).
          disabledReason: govBlocked,
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
        { id: 'agent-gov', icon: '🏛', label: 'Agent Governance Center',
          desc: '조직 자산의 범위·권한·승인 — 누가 만들고 누가 승인해서 어디에 쓰이는가',
          // ⚠️ 여기는 「내 업무」다 — viewer 도 자기 범위의 자산을 볼 수 있어야 하므로
          //   거버넌스 콘솔(전사 정비 상태)과 달리 막지 않는다. 자격은 화면 안에서
          //   행동 단위로 표시하고, 못 누르는 버튼마다 사유를 붙인다(§8.6).
          onSelect: () => setShowAgentGov(true) },
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
        { id: 'calc-approval', icon: '🔐', label: '계산 실행 승인 · 시연 초기화',
          desc: '산식별 정의·단위·부호·범위·유효기간을 보고 승인 — 누르기 전까지 계산은 «막힘» 입니다. 시연 초기화는 실행 결과만 되돌립니다',
          // ⚠️ 시스템 관리자 전용이다. 화면에서 숨기는 것은 **편의**이고, 실제로 막는 것은
          //   서버(`route_authority` 표의 `ADMIN_SECURITY`)다 — 숨김을 통제로 믿지 않는다.
          onSelect: () => setShowCalcApproval(true) },
        { id: 'telemetry', icon: '📈', label: 'LLM 텔레메트리',
          desc: '실제 사용 모델·폴백·소요시간 — 모델 불변성 실측',
          // ⚠️ 이 화면의 «품질 결과» 탭과 에이전트 집계는 거버넌스 관문을 지난다 —
          //   `/telemetry/agents` 가 형제 둘과 갈라져 익명에게 열려 있던 것을 함께 고쳤다.
          disabledReason: govBlocked,
          onSelect: () => setShowTelemetry(true) },
      ],
    },
  ];

  const isMegaProject = projects.find(p => p.id === currentProjectId)?.is_mega_project === true;

  const handleDeleteProject = async (id: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    // ★★ [2026-08-07] **문구가 서버와 같은 말을 해야 한다.**
    //   종전 문구는 「물리 디스크의 모든 산출물을 지우며 복구할 수 없습니다」였다. 사용자 결정에
    //   따라 이 버튼은 이제 **표시 삭제**이고 데이터는 남으며 되돌릴 수 있다 — 옛 문구를 그대로
    //   두면 화면이 서버보다 무섭게 거짓말을 하고, 사용자는 지워도 되는 것을 안 지운다.
    //   (실제 삭제는 관리자 전용이며 이 버튼에 없다.)
    if (!confirm(`'${name} (${id})' 를 목록에서 내리시겠습니까?\n\n`
      + `산출물은 지워지지 않고 그대로 보관됩니다. 관리자가 되돌릴 수 있습니다.\n`
      + `※ 다른 부서·사용자에게 공유·전달된 프로젝트는 관리자만 내릴 수 있습니다.`)) return;

    const success = await deleteProject(id);
    if (success) {
      alert("목록에서 내렸습니다. 산출물은 보관돼 있습니다.");
    } else {
      // ⚠️ 「에러가 발생했습니다」로 뭉개지 않는다 — 권한 문제인지 공유된 프로젝트라서인지
      //   서버가 죽어서인지에 따라 사용자가 할 일이 다르다. 서버 문구를 그대로 보여 준다.
      alert(useFactoryStore.getState().projectActionError || "삭제하지 못했습니다.");
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

  // ★★★ [설계 §3.2] 프로젝트를 고르지 않았고 «경영 홈» 공간이면 Decision Canvas 를 그린다.
  //   Software Factory(런처)는 그 아래 Studio 다.
  if (!currentProjectId && space === 'enterprise') {
    return (
      <ErrorBoundary>
        <div className="afs-scope" style={{ minHeight: '100vh',
          background: 'var(--surface-page)' }}>
          {/* ★ [설계 §3.1] Top Bar **72px** · 구조색. ⑥ 상단 회사·사업부·공장 Context 는
              `CompanyContextBar` 가 담당한다(§4.1). */}
          <header style={{
            height: 72, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 16, padding: '0 24px', position: 'sticky', top: 0, zIndex: 20,
            background: 'linear-gradient(90deg, var(--bar-bg-from), var(--bar-bg-to))',
            borderBottom: '1px solid var(--bar-border)', color: 'var(--bar-fg)',
          }}>
            <CompanyContextBar />
            <div className="flex items-center gap-3 min-w-0">
              <SessionBar />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </div>
          </header>
          <EnterprisePage
            onOpenBuild={() => setSpace('build')}
            onOpenMenu={(id) => {
              if (id === 'advisor') setShowAdvisor(true);
              else if (id === 'collaboration') setShowCollaboration(true);
            }} />
        </div>
        {/* 경영 홈에서도 열 수 있어야 하는 오버레이 — 메뉴가 이 화면에도 있기 때문이다. */}
        {showAdvisor && (
          <AdvisorPanel onClose={() => setShowAdvisor(false)} onProjectCreated={fetchProjects} />
        )}
        {showCollaboration && (
          <CollaborationHub onClose={() => setShowCollaboration(false)}
            releaseIds={releases.map((r: any) => r.release_id).filter(Boolean)} />
        )}
        {showAgentGov && (
          <AgentGovernancePanel onClose={() => setShowAgentGov(false)} />
        )}
        {showDataPrep && <DataPrepPanel onClose={() => setShowDataPrep(false)} />}
        {showCalcApproval && (
          <CalcApprovalPanel onClose={() => setShowCalcApproval(false)} />)}
        {showPathCalc && <PathCalcPanel onClose={() => setShowPathCalc(false)} />}
        {showScenario && <ScenarioPanel onClose={() => setShowScenario(false)} />}
        {showDecisionPkg && <DecisionPanel onClose={() => setShowDecisionPkg(false)} />}
        {showPromotion && (
          <ReleasePromotionPanel onClose={() => setShowPromotion(false)} />
        )}
        {showKnowledgeHub && (<KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />)}
        {showTerminology && (<TerminologyGlossaryPanel onClose={() => setShowTerminology(false)} />)}
        {showMasterData && (<MasterDataPanel onClose={() => setShowMasterData(false)} />)}
        {showWorkStandard && (<WorkStandardPanel onClose={() => setShowWorkStandard(false)} />)}
        {showOrgChart && (<OrgChartPanel onClose={() => setShowOrgChart(false)} />)}
        {showCrosswalk && (<CrosswalkPanel onClose={() => setShowCrosswalk(false)} />)}
        {showTelemetry && (<TelemetryPanel onClose={() => setShowTelemetry(false)} />)}
        {showGovernance && (<GovernanceConsole onClose={() => setShowGovernance(false)} />)}
        {showSkillEvolution && (<SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />)}
        {showShadow && (<ShadowModePanel onClose={() => setShowShadow(false)} />)}
        {showWorkspace && (<WorkspacePanel onClose={() => setShowWorkspace(false)} />)}
        {showPlanning && (<PlanningPanel onClose={() => setShowPlanning(false)} />)}
        {showBriefing && (<BriefingPanel onClose={() => setShowBriefing(false)} />)}
      </ErrorBoundary>
    );
  }

  if (!currentProjectId) {
    return (
      <ErrorBoundary>
        {showSkillEvolution && (
          <SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />
        )}
        {showDataPrep && <DataPrepPanel onClose={() => setShowDataPrep(false)} />}
        {showCalcApproval && (
          <CalcApprovalPanel onClose={() => setShowCalcApproval(false)} />)}
        {showPathCalc && <PathCalcPanel onClose={() => setShowPathCalc(false)} />}
        {showScenario && <ScenarioPanel onClose={() => setShowScenario(false)} />}
        {showDecisionPkg && <DecisionPanel onClose={() => setShowDecisionPkg(false)} />}
        {showPromotion && (
          <ReleasePromotionPanel onClose={() => setShowPromotion(false)} />
        )}
        {showKnowledgeHub && (
          <KnowledgeHubPanel onClose={() => setShowKnowledgeHub(false)} />
        )}
        {showTerminology && (
          <TerminologyGlossaryPanel onClose={() => setShowTerminology(false)} />
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
        {/* [P2-2] 조직 자산은 **프로젝트가 없어도** 다루는 것이다 — 오히려 「프로젝트를 만들기
            전에 우리 조직이 어떤 에이전트를 쓸 수 있는가」를 여기서 본다. 아래쪽 Studio 와 달리
            런처에서 빼면 메뉴는 활성으로 보이는데 눌러도 아무 일이 없다. 그때 사용자는 권한
            문제로 읽지 않고 **화면 고장으로 읽는다** — 위 351행 주석이 경고한 바로 그 상태다. */}
        {showAgentGov && (
          <AgentGovernancePanel onClose={() => setShowAgentGov(false)} />
        )}
        {/* §5.2 `/build/start` — 생성은 목록면과 분리된 흐름이다. */}
        {buildStart && (
          <BuildStartDialog
            templates={templates as any}
            knowledgePacks={knowledgePacks}
            packsBlocked={packsBlocked}
            onClose={() => setBuildStart(false)}
            onCreate={async (r) => {
              const domains = r.masterDomains.split(',').map((x) => x.trim()).filter(Boolean);
              const okDone = await createProject(r.projectId, r.templateId, r.packIds,
                domains, r.mcpLiveGrounding);
              if (okDone) {
                setBuildStart(false);
                setCurrentProject(r.projectId);
              }
            }} />
        )}
        <div className="afs-scope afs-page min-h-screen w-full flex flex-col font-sans">
 <header className="h-16 afs-topbar backdrop-blur-md border-b afs-border flex items-center justify-between gap-2 px-3 xl:px-5 shrink-0 sticky top-0 z-10 overflow-hidden">
 <div className="flex items-center gap-3 shrink-0">
 {/* ★ [설계 §3.4] 「Studio 의 공통 상단 바에는 `경영 홈으로 돌아가기` 와 현재 회사 문맥을
     항상 표시한다」 — 돌아갈 길이 없으면 Studio 는 앱의 끝이 되고, 사용자는 새로고침으로
     빠져나온다. */}
 <button className="secondary-button" onClick={() => setSpace('enterprise')}
 style={{ whiteSpace: 'nowrap' }}>◀ 경영 홈</button>
 <h1 className="text-xl 2xl:text-2xl font-bold tracking-tight afs-ink flex items-center gap-2 shrink-0">
 <span className="afs-action-fg">🏭</span> Software Factory
 </h1>
 </div>
 {/* ★ 사용자 전환기는 «기능»이 아니라 «지금 누구인가»다. 메뉴 안으로 숨기지 않는다 —
 권한 범위가 사람마다 다르므로 상시 보여야 한다(채택 결정 6항). */}
 <div className="flex items-center gap-3 min-w-0">
 <SessionBar />
 <GlobalNav
 // 1차 영역 — 매일 쓰는 진입점 3개. 넘기면 다시 «나열»이 된다.
 primary={primaryNav}
 groups={navGroups}
 right={
 <div className="relative shrink-0">
 <button
 onClick={() => setShowLogPopup(v => !v)}
 title="서버 로그 보기"
 className="flex items-center gap-2 afs-bg-sunken afs-hover-raise transition-colors px-1.5 2xl:px-3 py-1.5 rounded-full border afs-border cursor-pointer"
 >
 <span className="hidden 2xl:inline text-xs afs-muted font-medium">Network</span>
 <div className={`w-2.5 h-2.5 rounded-full shadow-[0_0_8px] ${isConnected ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500 shadow-red-500/50 animate-pulse'}`} />
 </button>
 {showLogPopup && <ServerLogPopup onClose={() => setShowLogPopup(false)} />}
 </div>
 }
 />
 </div>
 </header>

 <main style={{ flex: 1, overflowY: 'auto', width: '100%' }}>
          {/* ★★★ [설계 §5.2] `/build` 는 **목록면**이다 — 상단 「새 업무 만들기」 + 진행 상태
              필터, 본문은 진행 중/내 프로젝트/Mega/Releases/Archive.
              ⚠️ 종전에는 열자마자 «신규 프로젝트 개설» 폼이 본문을 차지했다(2026-07-28 AS-IS).
                목록이 먼저 보여야 「이미 있는 것을 여는」 흔한 일이 한 번에 되고, 만들기는
                결정이 필요한 별도 흐름이 된다. 생성 폼은 `buildStart` 오버레이로 옮겼다. */}
          <BuildPage
            projects={projects as any}
            releases={releases}
            onOpenProject={(id) => setCurrentProject(id)}
            onOpenRelease={(releaseId) => viewRelease(releaseId)}
            onNewWork={() => setBuildStart(true)}
            onManageRelease={(r) => setAdminProgram({ id: r.release_id, name: r.project_name || r.release_id })}
            onDeleteProject={(id) => {
              // ⚠️ 기존 확인 문구를 그대로 쓴다 — 서버는 «표시 삭제» 이고 데이터는 남는다.
              //   여기서 새 문구를 지어내면 화면이 서버보다 무섭게 말한다.
              const p = projects.find((x) => x.id === id);
              handleDeleteProject(id, p?.name || id,
                { stopPropagation: () => {} } as React.MouseEvent);
            }}
          />
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
            {/* [트랙 E 2단계] 신규 제작 작업공간으로 들어가는 유일한 입구. 종전 화면은 그대로
                남아 있고, 닫으면 여기로 돌아온다 — «병행 카나리»가 그 뜻이다. */}
            <button
              onClick={() => setShowStudio(true)}
              className="text-xs font-bold text-orange-100 bg-orange-900/50 hover:bg-orange-800/70 border border-orange-700/60 px-3 py-1.5 rounded-lg transition-colors"
              title="새 제작 작업공간(병행 카나리) — 전체 제작 단계와 WBS 실행 구조를 실제 상태로 봅니다. 종전 통제실은 그대로 유지됩니다."
            >
              🏗 새 작업공간
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
        {showAgentGov && (
          <AgentGovernancePanel onClose={() => setShowAgentGov(false)} />
        )}
        {/* [트랙 E 2단계] 프로젝트 문맥이 있는 이 화면에만 둔다 — Studio 는 «지금 만들고 있는
            SW»를 다루므로 프로젝트가 없는 런처에서는 보여 줄 것이 없다. 위 주석이 경고한
            «모달 목록 두 벌» 중 이쪽에만 추가한 것은 실수가 아니다.
            ⚠️ 이 면책은 **Studio 에만** 해당한다. 바로 위 `AgentGovernancePanel` 은 양쪽에
            있어야 하므로 이 주석 아래로 내리지 말 것 — 주석이 가리키는 대상이 어긋나면
            다음 사람이 「한쪽에만 둔 것은 의도」라고 읽는다. */}
        {showStudio && (
          <AdaptiveProductionStudio onClose={() => setShowStudio(false)} />
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

/** ★★★ [2026-08-09] **인증 게이트 — 제품에 들어오는 유일한 문.**
 *
 * 종전에는 문이 없었다. `actingUser` 기본값이 `'admin'` 이라 앱을 열면 관리자로 들어와졌고,
 * 최상단 전환기로 아무 계정이나 골라 그 권한으로 볼 수 있었다.
 *
 * ⚠️ **세션이 살아 있는지는 서버에 묻는다**(`/auth/me`). 토큰이 localStorage 에 남아 있어도
 *   만료됐거나 서버가 세션을 끊었을 수 있다 — 화면이 토큰의 존재만 보고 «로그인됨» 으로
 *   판단하면, 그 뒤 모든 요청이 401 인데 사용자는 이유를 모른 채 빈 화면을 본다.
 * ⚠️ 서버에 닿지 못한 경우를 «미인증» 과 구분한다. 백엔드가 꺼져 있는 것을 로그인 화면으로
 *   답하면 사용자는 비밀번호를 의심한다. */
export default function App() {
  const [state, setState] = useState<'checking' | 'in' | 'out'>('checking');
  const [offline, setOffline] = useState('');

  const check = useCallback(async () => {
    setOffline('');
    if (!getSessionToken()) { setState('out'); return; }
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
        headers: { 'X-Session-Token': getSessionToken() },
      });
      if (r.ok) { setState('in'); return; }
      // 401/403 = 세션이 죽었다. 토큰을 버려야 다음 새로고침에서 또 묻지 않는다.
      setSessionToken(''); setActingUser('');
      setState('out');
    } catch {
      setOffline('서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하십시오.');
      setState('out');
    }
  }, []);

  useEffect(() => { check(); }, [check]);

  if (state === 'checking') {
    return (
      <div className="afs-scope afs-page"
        style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <span className="afs-muted">확인 중…</span>
      </div>
    );
  }
  if (state === 'out') {
    return (
      <ErrorBoundary>
        {offline && (
          <div style={{ position: 'fixed', top: 12, left: '50%', transform: 'translateX(-50%)',
            zIndex: 10, maxWidth: 520 }}>
            <Banner tone="warn" title="서버에 연결하지 못했습니다">{offline}</Banner>
          </div>
        )}
        <LoginPage onLoggedIn={() => {
          setState('in');
          // 초기 비밀번호 상태는 로그인 뒤 상단 SessionBar가 지속적으로 보여 주고 바로 옆
          // 「환경설정 · 관리자」에서 변경한다. 네이티브 alert는 첫 화면 전체를 막으므로 쓰지 않는다.
        }} />
      </ErrorBoundary>
    );
  }
  return <AppShell />;
}
