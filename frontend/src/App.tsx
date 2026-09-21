import React, { useCallback, useEffect, useState } from 'react';

import { useFactoryStore } from './store/useFactoryStore';

import { Group, Panel, Separator } from 'react-resizable-panels';

import ControlPanel from './components/ControlPanel';
import { AdaptiveProductionStudio } from './factory/AdaptiveProductionStudio';
import { parseStudioLocation, serializeStudioLocation } from './factory/studioLocation';
import type { StudioTarget } from './factory/studioLocation';
import { StudioProjectEntryGate } from './factory/StudioProjectEntryGate';
import { StudioDraftEntryGate } from './factory/StudioDraftEntryGate';
import { openDraftRevision } from './lib/studioRequirementDraft';
import { canLeaveNow, confirmLeave } from './factory/studioLeaveGuard';
import type { ProjectEntry } from './factory/studioProjectEntry';
import { StudioKitAppEntryGate } from './factory/StudioKitAppEntryGate';
import type { KitAppEntry } from './factory/studioKitAppEntry';
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
import { KnowledgeHubPanel, type KnowledgeView } from './components/KnowledgeHubPanel';
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
// [I-4 7 / Wave H-4] 운영 승격 — 후보를 운영으로 올리는 단 하나의 문
import { ReleasePromotionPanel } from './components/ReleasePromotionPanel';
import { CompanySetupPanel } from './components/CompanySetupPanel';
import { OperatingContextSwitcher } from './components/OperatingContextSwitcher';
import { OperatingContextChip, ProductShell } from './components/ProductShell';
import { SystemAboutPage } from './components/SystemAboutPage';
import { KitOperationsPanel } from './components/KitOperationsPanel';
import { SimulationGovernanceShell } from './components/SimulationGovernanceShell';
import { OperationsGovernanceShell } from './components/OperationsGovernanceShell';
//: ★★★ [2026-08-25] 문맥을 푸는 규칙은 **한 곳**에 있다(`lib/operatingContext`).
//: ⚠️ 종전에는 여기서 `getEnterpriseContext().tenantId` 를 그대로 썼다. 그 값은 사용자가
//:   조직을 고를 때만 채워지므로 로그인 직후 상단이 「? · 확인 중」이었다 —
//:   회사 Context 상시 노출은 채택 결정문이 고정 요소로 못박은 항목이다.
import { useOperatingContext } from './lib/operatingContext';
import { BuildPage } from './components/BuildPage';
import { BuildStartDialog, type BuildDeliverableType } from './components/BuildStartDialog';
import { Banner } from './design/HubShell';
import { HomeNavContext } from './design/HubDialog';
import {
  API_BASE_URL, getEnterpriseContext, getSessionToken, setActingUser,
  setEnterpriseContext, setSessionToken,
} from './lib/api';


/** [B6] 최초 URL 의 Studio 진입 대상을 한 번만 읽는다.
 *
 *  ⚠️ 문법 판정은 `parseStudioLocation` 한 곳에서만 한다. 여기서 쿼리를 다시 해석하면
 *    대상 규칙이 갈라지고, 갈라지면 한쪽만 고쳐도 조용히 다른 답을 준다.
 *  ★ `new` 는 **만들기 흐름**이라 조회할 대상이 없다 — 서버 진입 확인을 태우지 않는다.
 *    실제 생성 POST 는 사용자가 폼에서 눌러야 나간다. */
type StudioEntry = {
  project: string | null; isNew: boolean; release: string | null;
  kitApp: { instanceId: string; appId: string } | null;
  mega: { megaProjectId: string; childProjectId: string } | null;
  draft: { draftId: string; draftKind: string; revision: number } | null;
};
function readStudioEntry(): StudioEntry {
  const none: StudioEntry = { project: null, isNew: false, release: null, kitApp: null, mega: null, draft: null };
  if (typeof window === 'undefined') return none;
  const parsed = parseStudioLocation(window.location.search);
  if (parsed.kind !== 'MATCH') return none;
  const target = parsed.location.target;
  return {
    project: target.kind === 'project' ? target.projectId : null,
    isNew: target.kind === 'new',
    release: target.kind === 'release' ? target.releaseId : null,
    //   ★ `releaseId` 는 진입 확인 범위 밖이다(설계안 §6-2 미결). 문법으로 받되 여기서는
    //     쓰지 않는다 — 결정 전에 의미를 임의로 부여하지 않는다.
    kitApp: target.kind === 'kit_app' ? { instanceId: target.instanceId, appId: target.appId } : null,
    //   ★ [MEGA-ENTRY-01] 메가는 `project` 의 한 종류다. 같은 확인 경로를 쓰되 자식을
    //     함께 넘겨 **서버가 관계까지** 판정하게 한다(설계안 §10).
    mega: target.kind === 'mega'
      ? { megaProjectId: target.megaProjectId, childProjectId: target.childProjectId || '' } : null,
    //   ★ [DRAFT-ENTRY-01] 초안은 **경계를 URL 에 싣지 않는다** — 종류·판본만 질문이고
    //     소유 문맥은 서버가 찾는다(설계안 §12).
    draft: target.kind === 'draft'
      ? { draftId: target.draftId, draftKind: target.draftKind, revision: target.revision } : null,
  };
}

/** [FIX1 · 지시 2] URL 의 `space` 판독. **초기 마운트와 popstate 복원이 같은 규칙을 쓴다.**
 *
 *  ⚠️ 종전에는 초기식 안에만 있었다 — 뒤로/앞으로가 목록·홈 주소로 돌아와도 그 화면으로
 *    전환할 방법이 없었고, 그래서 주소창과 화면이 어긋났다. */
const STUDIO_SPACES = ['enterprise', 'about', 'build', 'operate', 'twin', 'report', 'knowledge',
  'agent', 'advisor', 'data', 'calc', 'path', 'briefing', 'master', 'terminology', 'crosswalk',
  'governance', 'planning', 'shadow', 'promotion', 'workspace', 'company', 'org', 'standard',
  'agentgov', 'skills', 'telemetry'] as const;
type StudioSpace = (typeof STUDIO_SPACES)[number];
function readSpaceFromUrl(): StudioSpace {
  if (typeof window === 'undefined') return 'enterprise';
  const value = new URLSearchParams(window.location.search).get('space') || '';
  return (STUDIO_SPACES as readonly string[]).includes(value) ? value as StudioSpace : 'enterprise';
}

/** [B6] 서버가 확인해 준 진입 대상만 실제 선택으로 옮긴다.
 *
 *  ⚠️ 렌더 중에 store 를 바꾸지 않는다 — effect 에서만 옮기고, 옮겨지기 전에는 아무것도
 *    그리지 않는다. 조회 가능은 실행·게시 승인이 아니므로 여기서 더 하는 일은 없다. */
function StudioEntryCommit({ entry, onCommit }: { entry: ProjectEntry; onCommit: (id: string) => void }) {
  //: ★ [MEGA-ENTRY-01] 자식이 **확인돼 왔으면** 그 자식으로 들어간다. 메가 회의실의
  //:   「상세 뷰 진입」 버튼이 하는 일과 같은 자리이고, 다른 점은 **관계를 서버가
  //:   확인해 줬다**는 것뿐이다. 확인이 안 된 자식은 애초에 여기까지 오지 않는다.
  const target = entry.child ? entry.child.project_id : entry.project_id;
  //: ⚠️⚠️ [2026-09-16] **콜백을 의존성에 넣지 않는다.** 부모가 JSX 안에서 인라인
  //:   화살표로 넘기므로 렌더마다 신원이 바뀌고, 그러면 이 효과가 **다시 돈다** —
  //:   `setCurrentProject` 가 반복되고 그것이 wbs·state·hotl·feed 네 요청을 다시 쏜다.
  //: ★ 최신 콜백은 ref 로 들고, 의존성은 «무엇을 열 것인가» 하나로 둔다.
  const commit = React.useRef(onCommit);
  commit.current = onCommit;
  useEffect(() => { commit.current(target); }, [target]);
  return null;
}

/** [B6] 확인된 업무 앱을 기존 시뮬레이션 진입과 **같은 자리**로 넘긴다. */
function KitAppEntryCommit({ entry, onCommit }: {
  entry: KitAppEntry; onCommit: (instanceId: string, appId: string) => void;
}) {
  //: ⚠️ 위와 같은 이유로 콜백은 ref 로 들고 의존성에서 뺀다.
  const commit = React.useRef(onCommit);
  commit.current = onCommit;
  useEffect(() => { commit.current(entry.instance_id, entry.app_id); },
    [entry.instance_id, entry.app_id]);
  return null;
}

/** [DRAFT-OPEN-01] **확인된 초안을 실제로 연다.**
 *
 *  ⚠️ 렌더 중에 부르지 않는다 — effect 에서만. 그리고 «확인된 뒤에만» 온다(Gate 가
 *    AVAILABLE 일 때만 children 을 만든다). 조회 가능은 편집·승인 허가가 아니므로
 *    여기서 더 하는 일은 없다: 불러와서 기존 요구사항 화면에 넘길 뿐이다.
 *  ⚠️ 미저장 입력이 있으면 `openDraftRevision` 이 **멈춘다.** 그때는 사용자에게 묻고,
 *    「계속」을 누른 경우에만 `replaceUnsaved` 로 다시 부른다. */
function DraftOpenCommit({ entry, onOpened }: {
  entry: { draft_id: string; revision: number;
    ownership: { tenant_id: string; context_root_id: string; entity_mode: string; scope_node_id: string } };
  onOpened: (deliverable: 'software_app' | 'hybrid_simulation' | 'document_report') => void;
}) {
  const [error, setError] = useState<{ message: string; replaceable: boolean } | null>(null);
  const [busy, setBusy] = useState(true);
  //: ⚠️ 콜백 신원이 바뀌어도 다시 불러오지 않는다 — 같은 이유다.
  const opened = React.useRef(onOpened);
  opened.current = onOpened;
  const own = entry.ownership;
  const ownershipKey = `${own.tenant_id}|${own.context_root_id}|${own.entity_mode}|${own.scope_node_id}`;
  //: ★★★ [FIX1 · P1] **자동 진입과 재시도 버튼이 «같은» 취소 수명을 쓴다.**
  //:
  //: ⚠️⚠️ 종전에는 `open()` 이 돌려준 정리 함수를 `useEffect` 만 썼다 — 버튼으로 시작한
  //:   요청은 아무도 취소하지 않아, 화면이 사라진 뒤에도 콜백이 돌 수 있었다.
  //: ⚠️ 그리고 취소는 **거들 뿐**이다. 실제 오염 차단은 `openDraftRevision` 안에서
  //:   문맥·세대를 adopt 직전에 다시 보는 쪽이 한다.
  const request = React.useRef<AbortController | null>(null);
  const open = React.useCallback((replaceUnsaved: boolean) => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const live = () => request.current === controller && !controller.signal.aborted;
    setBusy(true); setError(null);
    void openDraftRevision(
      { draftId: entry.draft_id, revision: entry.revision, ownership: entry.ownership },
      { replaceUnsaved, signal: controller.signal })
      .then((result) => { if (live()) opened.current(result.deliverable); })
      .catch((failure: unknown) => {
        if (!live()) return;
        const reason = (failure as { reasonCode?: string })?.reasonCode || '';
        const message = (failure as { message?: string })?.message || '초안을 불러오지 못했습니다.';
        setError({ message, replaceable: reason === 'STUDIO_UNSAVED_INPUT' });
      })
      .finally(() => { if (live()) setBusy(false); });
    return () => controller.abort();
    //: ⚠️⚠️ [2026-09-16 실화면 실측] 의존성에 `entry.ownership` **객체**를 넣었더니
    //:   렌더마다 새 신원이 되어 effect 가 다시 돌았다 — 같은 GET 이 **6번** 나갔다.
    //:   조회라 해가 없어 보이지만 같은 실수가 쓰기 경로에 있으면 중복 실행이 된다.
  }, [entry.draft_id, entry.revision, ownershipKey]);
  useEffect(() => open(false), [open]);
  //: 화면이 사라지면 **버튼으로 시작한 요청도** 함께 폐기한다.
  useEffect(() => () => request.current?.abort(), []);
  if (busy) return <p role="status" aria-live="polite">초안 {entry.revision}판을 불러오는 중입니다.</p>;
  if (!error) return null;
  return (
    <section aria-label="초안 불러오기 실패">
      <p role="alert">{error.message}</p>
      {error.replaceable && (
        <button type="button" onClick={() => open(true)}>지금 입력을 버리고 불러오기</button>
      )}
      <button type="button" onClick={() => open(false)}>다시 시도</button>
    </section>
  );
}

function AppShell() {
  const connectSSE = useFactoryStore((state) => state.connectSSE);
  const isConnected = useFactoryStore((state) => state.isConnected);
  const projects = useFactoryStore((state) => state.projects);
  const currentProjectId = useFactoryStore((state) => state.currentProjectId);
  const fetchProjects = useFactoryStore((state) => state.fetchProjects);
  const createProject = useFactoryStore((state) => state.createProject);
  const createMegaProject = useFactoryStore((state) => state.createMegaProject);
  const deleteProject = useFactoryStore((state) => state.deleteProject);
  const setCurrentProject = useFactoryStore((state) => state.setCurrentProject);
  const statePayload = useFactoryStore((state) => state.state);
  const releases = useFactoryStore((state) => state.releases);
  const viewingRelease = useFactoryStore((state) => state.viewingRelease);
  const fetchReleases = useFactoryStore((state) => state.fetchReleases);
  const viewRelease = useFactoryStore((state) => state.viewRelease);
  const closeRelease = useFactoryStore((state) => state.closeRelease);
  const releaseLoad = useFactoryStore((state) => state.releaseLoad);
  const releaseError = useFactoryStore((state) => state.releaseError);
  // deleteRelease 는 더 이상 목록에서 쓰지 않는다 — 서버가 삭제를 거부하고 사용 중단을
  //   안내한다(사용자 결정 2026-07-30). 스토어 액션 자체는 남겨둔다.
  const showAgentPanel = useFactoryStore((state) => state.showAgentPanel);
  const closeAgentPanel = useFactoryStore((state) => state.closeAgentPanel);
  const showFormatPanel = useFactoryStore((state) => state.showFormatPanel);
  const templates = useFactoryStore((state) => state.templates);
  const fetchTemplates = useFactoryStore((state) => state.fetchTemplates);

  // ★★★ [UI 설계서 §3.2 · §3.4] **첫 화면은 경영 홈(Decision Canvas)이다.**
  //   Software Factory 는 거기서 들어가는 Immersive Studio 다 — 설계는 「경영 홈에서 Studio 로
  //   이동한다」고 방향을 못박았는데, 실제로는 「신규 프로젝트 개설」 폼이 첫 화면이었다
  //   (2026-07-28 리버스엔지니어링 AS-IS 그대로. 화면 이관은 개별 화면만 옮겼다).
  //   React Router 를 새로 들이지 않고도 최소 URL 상태 계약을 지킨다. `space`와 `project`는
  //   새로고침·공유 뒤 같은 제작 문맥을 복원한다. 인증·권한 검사는 URL 이 아니라 서버가 한다.
  //   ★ [B6] URL 해석은 순수 문법 모듈(`studioLocation`)에 맡긴다. 여기서 직접
  //     `URLSearchParams` 를 읽으면 대상 판정 규칙이 두 곳으로 갈라지고, 갈라지면
  //     한쪽만 고쳐도 조용히 다른 답을 준다. legacy `?project=` 단독은 그 모듈이
  //     `kind:'project'` 로 정규화하므로 기존 링크 동작은 그대로다.
  const initialEntry = React.useRef(readStudioEntry());
  //   ★ [MEGA-ENTRY-01] 메가도 **같은 진입 확인**을 탄다 — 부모가 곧 확인 대상이다.
  const initialProject = React.useRef<string | null>(
    initialEntry.current.project ?? initialEntry.current.mega?.megaProjectId ?? null);
  const [space, setSpace] = useState<'enterprise' | 'about' | 'build' | 'operate' | 'twin' | 'report' | 'knowledge' | 'agent'
    | 'advisor' | 'data' | 'calc' | 'path' | 'briefing'
    | 'master' | 'terminology' | 'crosswalk' | 'governance' | 'planning' | 'shadow'
    | 'promotion' | 'workspace' | 'company' | 'org' | 'standard' | 'agentgov' | 'skills'
    | 'telemetry'>(() => {
    if (initialProject.current) return 'build';
    return readSpaceFromUrl();
  });
  //   ★★★ [2026-09-16 실화면 실측] **확인이 끝날 때까지 URL 대상을 지우지 않는다.**
  //
  //   ⚠️⚠️ 종전에는 `initialProject.current === null` 만 봤다. 그 값은 **project·mega 만**
  //     채운다 — 그래서 `kit_app`·`draft` 로 들어오면 시작부터 `true` 였고, 아래 효과가
  //     **게이트가 확인을 끝내기도 전에** URL 의 대상 키를 지웠다. 그 상태에서 새로고침하면
  //     진입 대상이 **사라진다**(브라우저로 초안 링크를 눌러 보고서야 드러났다).
  //   ★ 닫는 쪽은 이미 셋 다 `setRouteRestored(true)` 를 부르고 있었다 — 의도는 처음부터
  //     이것이었고 초기값만 빠져 있었다.
  const [routeRestored, setRouteRestored] = useState(
    initialProject.current === null && initialEntry.current.kitApp === null
    && initialEntry.current.draft === null);
  //   ★★★ [B6] 직접 링크로 들어온 프로젝트는 **서버가 확인하기 전에 열지 않는다.**
  //     종전에는 여기서 곧바로 `setCurrentProject()` 를 불렀고, 그것이 wbs·state·hotl·feed
  //     네 요청을 즉시 쏘았다. 없는 프로젝트여도 화면은 열렸고 404 네 건은 「서버 연결 끊김」
  //     으로 보였다(실측: docs/handoff/L2_STUDIO_BROWSER_BASELINE_2026-09-15.md §4).
  //   ⚠️ 목록에서 눌러 여는 경로(`onOpenProject`)는 **건드리지 않는다** — 그쪽은 서버가 준
  //     목록에서 고른 것이라 진입 확인을 한 번 더 할 이유가 없다.
  const [entryGateId, setEntryGateId] = useState<string | null>(initialProject.current);
  const [kitAppGate, setKitAppGate] = useState<{ instanceId: string; appId: string } | null>(initialEntry.current.kitApp);
  //   ★★★ [FIX1 · 보완1] **«메가로 요청했다»는 사실 자체를 보존한다.** 자식 id 만
  //     넘기면 「자식 없는 메가 링크」가 일반 프로젝트 요청과 구분되지 않는다 —
  //     그러면 메가 링크로 일반 프로젝트가 열린다(검토에서 지적된 그대로였다).
  //   ⚠️ 게이트가 닫힐 때 함께 비운다. 남겨 두면 다음 확인에 옛 요청이 딸려 간다.
  const [megaRequest, setMegaRequest] = useState<{ childProjectId: string } | null>(
    initialEntry.current.mega ? { childProjectId: initialEntry.current.mega.childProjectId } : null);
  const [draftGate, setDraftGate] = useState(initialEntry.current.draft);
  //   ★★★ [FIX1 · 지시 3 / 결정서 §3] **열린 대상은 새로고침으로 재현 가능해야 한다.**
  //
  //   ⚠️⚠️ 종전에는 확인이 끝나면 URL 의 대상 키를 «전부» 지우고 legacy `project` 만 남겼다.
  //     그래서 메가의 부모/자식, 초안의 종류·판본, 업무앱의 instance/app, 릴리스 ID 가
  //     **새로고침에서 사라졌다.** 「확인 중 보존」과 「열린 뒤 보존」은 다른 문제다.
  //   ★ 직렬화는 문법 모듈(`serializeStudioLocation`)에 맡긴다 — 정규형을 두 곳에서 만들면
  //     한쪽만 고쳐도 조용히 다른 주소가 된다.
  const [openedMega, setOpenedMega] = useState<{ megaProjectId: string; childProjectId: string } | null>(null);
  const [openedKitApp, setOpenedKitApp] = useState<{ instanceId: string; appId: string } | null>(null);
  const [openedDraft, setOpenedDraft] = useState<{ draftId: string; draftKind: string; revision: number } | null>(null);
  //: 릴리스는 조회가 끝나야 `viewingRelease` 가 찬다. 그 «사이» 에도 목적지를 잃지 않게 붙든다.
  const [pendingRelease, setPendingRelease] = useState<string | null>(initialEntry.current.release);
  //: `openTarget` 이 `new` 를 읽어야 하므로 «주소 계산보다 위» 에 둔다(선언 순서).
  //: ★★★ [FIX2 · 실화면 실측] **첫 렌더부터 켜져 있어야 한다.** effect 로 뒤늦게 켜면
  //:   그 «사이» 렌더에서 `openTarget` 이 비어, URL 동기화가 목록 주소를 **새 칸으로 밀어
  //:   넣는다.** 실제로 `?target=new` 로 들어가면 칸이 둘 생겼고 뒤로가기가 중간의
  //:   `?space=build` 로 갔다. 릴리스(`pendingRelease`)와 같은 이유·같은 처방이다.
  const [buildStart, setBuildStart] = useState(initialEntry.current.isNew);
  /** ★★★ [FIX2 · 지시 3] 릴리스의 **열기·닫기를 한 계약으로 묶는다.**
   *
   *  ⚠️ 종전에는 `viewRelease` 만 부르고 주소는 `viewingRelease` 가 차기를 기다렸다.
   *    조회 중·실패 중에는 그 값이 **비어 있어** 목적지 주소를 잃었다.
   *  ⚠️ 반대로 닫을 때 `closeRelease()` 만 부르면 주소에 대상이 **남는다.** 두 값을
   *    따로 만지는 자리를 늘리지 않고 여기 둘로 모은다. */
  const openRelease = useCallback((releaseId: string) => {
    setPendingRelease(releaseId); void viewRelease(releaseId);
  }, [viewRelease]);
  const leaveRelease = useCallback(() => {
    setPendingRelease(null); closeRelease();
  }, [closeRelease]);
  //: ★ 저장소는 **스스로도** 릴리스를 닫는다(세션·행위자·회사 문맥 변경). 그때 의도만
  //:   남으면 화면은 비었는데 주소는 그 릴리스를 가리킨다 — 같은 신호를 함께 듣는다.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const drop = () => setPendingRelease(null);
    const events = ['factory:session-changed', 'factory:acting-user-changed',
                    'factory:enterprise-context-changed'];
    for (const name of events) window.addEventListener(name, drop);
    return () => { for (const name of events) window.removeEventListener(name, drop); };
  }, []);
  const closeEntryGate = useCallback(() => {
    setEntryGateId(null);
    setMegaRequest(null);
    setDraftGate(null);
    // 확인이 끝났으므로 이제 URL 을 현재 선택 상태로 다시 써도 된다.
    setRouteRestored(true);
  }, []);
  //   ★★★ [B6] 회사·사용자가 바뀌면 **열려 있던 Studio 를 즉시 내리고 다시 확인한다.**
  //     종전에는 SSE 만 다시 맺고 `currentProjectId` 를 그대로 두었다 — 바뀐 문맥에서 볼 수
  //     없는 프로젝트가 화면에 남고, 그 위의 숫자가 어느 회사 것인지 알 수 없게 된다.
  //   ⚠️ 닫기만 하지 않고 **같은 프로젝트를 새 문맥으로 다시 확인**한다. 상위/하위 조직으로
  //     옮긴 경우처럼 여전히 볼 수 있으면 확인 뒤 그대로 열리고, 볼 수 없으면 거절 화면이
  //     뜬다. 판정은 서버가 한다 — 여기서 조직 ID 를 비교해 흉내 내지 않는다.
  /** ★★★ [B6-CONTEXT-SSE-01 · 사용자 결정 ②] 회사·행위자가 바뀌면 **열린 대상을 다시 확인한다.**
   *
   *  ⚠️⚠️ 종전에는 `project` **하나만** 다시 확인했다(`currentProjectId` 가 있을 때만).
   *    초안·업무앱·메가·릴리스가 열려 있으면 **옛 문맥의 화면이 그대로 남았다** — 권한이
   *    좁아진 문맥에서도 보이던 것이 계속 보인다. 여섯 대상에 분기를 여섯 개 다는 대신
   *    **이미 있는 단 하나의 진입 경로**(`applyStudioEntry`)로 되돌린다.
   *  ★ 대상의 정본은 **URL** 이다(FIX2 이후 열린 대상은 언제나 주소에 있다). 그래서
   *    「지금 주소가 가리키는 것」을 새 권한으로 다시 확인하면 그것이 곧 재확인이다.
   *  ⚠️ URL 은 건드리지 않는다 — 확인이 끝날 때까지 `routeRestored=false` 이므로 주소를
   *    다시 쓰지 않고, 따라서 히스토리 칸도 늘지 않는다.
   *  ⚠️ 목록·홈이면 확인할 것이 없다. 괜히 화면을 흔들지 않는다. */
  const revalidateOpenEntry = useCallback(() => {
    if (typeof window === 'undefined') return;
    //: ⚠️ 주소와 화면이 어긋난 동안에는 URL 이 «지금 열린 대상» 이 아니다. 그 값으로 다시
    //:   확인하면 엉뚱한 것을 확인한다 — 안전하게 **정리만** 하고 아무것도 열지 않는다.
    if (strandedRef.current) {
      applyStudioEntryRef.current(
        { project: null, isNew: false, release: null, kitApp: null, mega: null, draft: null });
      return;
    }
    const next = readStudioEntry();
    const open = next.project || next.mega || next.draft || next.kitApp || next.release;
    if (!open) return;
    applyStudioEntryRef.current(next);
  }, []);
  //   ★★★ [SINGLE-ENTRY-01 · 사용자 결정 A] **뒤로/앞으로는 진입을 «다시 실행»한다.**
  //
  //   ⚠️ 다시 «여는» 것이 아니라 다시 «확인하는» 것이다 — 그 사이 권한·문맥이 바뀌었을 수 있다.
  //   ★ [FIX1 · 지시 2] 대상이 없는 주소로 돌아오면 **그 주소가 가리키는 화면으로 전환**한다.
  //     종전에는 게이트만 닫아 기존 화면이 남았고 주소창과 어긋났다. `release`·`new` 도 복원한다.
  //: `revalidateOpenEntry` 가 **위에서** 이것을 부른다. 선언 순서와 의존성 고리를 만들지
  //: 않으려고 ref 로 최신 것을 가리킨다.
  const applyStudioEntryRef = React.useRef<(next: StudioEntry) => void>(() => {});
  const applyStudioEntry = useCallback((next: StudioEntry) => {
    const project = next.project ?? next.mega?.megaProjectId ?? null;
    if (project || next.kitApp || next.draft) {
      // 확인이 끝날 때까지 편집기·선택을 내린다 — 확인 전에는 아무것도 열지 않는다.
      //: ★★★ [FIX2 · 지시 3] **이전 대상을 «함께» 정리한다.** 종전에는 릴리스·업무앱 화면을
      //:   그대로 두어, 릴리스에서 초안으로 가도 `openTarget` 이 릴리스를 먼저 고르고
      //:   **새 주소를 옛 릴리스가 덮었다.** 대상은 배타적이다.
      setBuildStart(false); setOpenedDraft(null);
      setOpenedKitApp(null); setOpenedMega(null); setShowPathCalc(false);
      leaveRelease();
      setCurrentProject(null);
      setEntryGateId(project);
      setMegaRequest(next.mega ? { childProjectId: next.mega.childProjectId } : null);
      setKitAppGate(next.kitApp);
      setDraftGate(next.draft);
      // URL 의 대상 키를 지우지 않는다 — 확인 중에 새로고침해도 잃지 않게.
      setRouteRestored(false);
      return;
    }
    //: 대상 없음 — 떠나는 화면을 정리하고 **URL 의 목적지**로 간다.
    setEntryGateId(null); setMegaRequest(null); setDraftGate(null); setKitAppGate(null);
    setOpenedMega(null); setOpenedKitApp(null); setOpenedDraft(null);
    setShowPathCalc(false);
    setCurrentProject(null);
    setBuildStart(false);
    leaveRelease();
    //: ★ [FIX2 · 지시 3] 릴리스는 **조회가 끝나기 전에도 주소를 지킨다.** 종전에는
    //:   `viewingRelease` 가 빌 동안 목적지 주소를 잃었다(로딩·실패 모두 `openTarget` 을 비웠다).
    if (next.release) { setSpace('build'); openRelease(next.release); }
    else if (next.isNew) { setSpace('build'); setBuildStartType('software_app'); setBuildStart(true); }
    else setSpace(readSpaceFromUrl());
    setRouteRestored(true);
  }, [leaveRelease, openRelease, setCurrentProject]);
  applyStudioEntryRef.current = applyStudioEntry;
  //   ★★★ [FIX2 · 지시 1] **앱이 만든 항목에 번호를 붙인다 — 그래야 «방향과 칸 수»를 안다.**
  //
  //   ⚠️⚠️ 종전에는 모든 취소를 `go(1)` 로 되돌렸다. 「뒤로 한 칸」만 가정한 것이라
  //     **앞으로 이동을 취소하면 더 앞으로 갔고**, 마지막 항목이면 아무 일도 안 일어나
  //     `skipNextPop` 만 남았다. 두 칸 이동도 원위치로 못 돌아왔다.
  //   ★ 번호는 우리가 만든 항목에만 붙인다. **없는 번호를 지어내지 않는다** — 번호가 없는
  //     항목으로 가는 것은 「앱 밖으로 나가는 정상 이동」이고 붙잡지 않는다(문서 이탈은
  //     기존 `beforeunload` 가 맡는다).
  const historyIndex = React.useRef<number | null>(null);
  /** ★★★ [FIX4 · 검토 A] **번호가 같아도 «같은 구간»이 아닐 수 있다.**
   *
   *  ⚠️ 번호를 잃은 뒤 우리는 0 부터 다시 센다. 그러면 옛 칸의 5 와 새 칸의 0 사이에
   *    「−5」라는 **그럴듯한 정수 차이**가 생긴다. 그 차이로 방향·칸 수를 계산하면
   *    엉뚱한 곳으로 이동시킨다 — 검토가 짚은 「관리 구간이 다른 항목 간 정수 차이만으로
   *    방향을 추정하지 않는다」가 이것이다.
   *  ★ 그래서 칸마다 **구간 표시**를 함께 찍고, 같은 구간일 때만 차이를 쓴다. */
  const historyEpoch = React.useRef<string>('');
  const newEpoch = React.useCallback(() => {
    historyEpoch.current = Math.random().toString(36).slice(2, 10);
    return historyEpoch.current;
  }, []);
  const skipNextPop = React.useRef(false);
  const leavingAnyway = React.useRef(false);
  //: 복원 popstate 가 끝나기 «전» 에 승인 클릭이 오면 여기 담아 두었다가 그 뒤에 실행한다.
  //: ⚠️ 빠른 클릭이 잘못된 이동을 만들지 않게 하는 순서 제어다.
  const pendingApproval = React.useRef<number | null>(null);
  const restoringFromPop = React.useRef(false);
  /** ★★★ [FIX3 · 검토 §4] **위치를 모르는 이동**에서 화면을 지키지 못한 주소.
   *
   *  ⚠️ 번호가 없다는 것은 「앱 밖」이라는 증거가 **아니다.** 같은 문서에서 다른 코드가
   *    만든 항목일 수도 있고, 그때 `beforeunload` 는 **뜨지 않는다.** 종전에는 그런
   *    항목으로 오면 묻지도 않고 편집기를 내렸다 — 미저장 입력이 그대로 사라진다.
   *  ★ 그렇다고 방향·칸 수를 **지어내지 않는다.** 되돌릴 수 없으면 되돌리는 «시늉» 대신
   *    어긋난 사실을 **보이게 두고** 사용자가 고르게 한다. 주소와 화면이 다른 것을
   *    조용히 덮지 않는다. */
  const [strandedEntry, setStrandedEntry] = useState<StudioEntry | null>(null);
  //: 안정된 콜백 안에서 «지금» 값을 보려면 ref 가 필요하다(렌더 값은 그 시점에 굳는다).
  const strandedRef = React.useRef<StudioEntry | null>(null);
  strandedRef.current = strandedEntry;
  //: 주소를 «다시 쓸» 필요가 생겼을 때만 URL 효과를 한 번 더 돌린다(칸은 늘리지 않는다).
  const [addressNonce, setAddressNonce] = useState(0);
  useEffect(() => {
    if (typeof window === 'undefined' || historyIndex.current !== null) return;
    //: 이 문서의 «현재» 항목을 우리 것으로 표시한다 — 새 칸을 만들지 않고 기존 state 도 보존한다.
    const state = (window.history.state || {}) as Record<string, unknown>;
    //: 새로고침으로 돌아온 «우리 칸» 이면 번호와 구간을 그대로 이어받는다.
    if (Number.isSafeInteger(state.__studioIndex) && typeof state.__studioEpoch === 'string'
        && state.__studioEpoch) {
      historyIndex.current = state.__studioIndex as number;
      historyEpoch.current = state.__studioEpoch;
      return;
    }
    historyIndex.current = 0;
    window.history.replaceState({ ...state, __studioIndex: 0, __studioEpoch: newEpoch() }, '',
      `${window.location.pathname}${window.location.search}${window.location.hash}`);
  }, [newEpoch]);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onPopState = (event: PopStateEvent) => {
      if (skipNextPop.current) {
        skipNextPop.current = false;
        const redo = pendingApproval.current;
        pendingApproval.current = null;
        if (redo) { leavingAnyway.current = true; window.history.go(redo); }
        return;
      }
      const state = (event.state || {}) as Record<string, unknown>;
      //: ⚠️ 번호는 **정수**여야 쓴다. 남이 넣은 값·소수·NaN 을 그대로 빼면 엉뚱한 칸으로 간다.
      const raw = state.__studioIndex;
      //: ⚠️ 구간이 다르면 번호는 **남의 눈금**이다. 정수 차이가 그럴듯해도 쓰지 않는다.
      const sameRange = typeof state.__studioEpoch === 'string'
        && state.__studioEpoch !== '' && state.__studioEpoch === historyEpoch.current;
      const incoming = sameRange && typeof raw === 'number' && Number.isSafeInteger(raw) ? raw : null;
      const here = historyIndex.current;
      const move = () => {
        leavingAnyway.current = false;
        historyIndex.current = incoming;
        //: 남의 칸으로 왔으면 우리 눈금은 **거기서 끝난다.** 새 구간을 열어야 다음에
        //: 우리가 만든 칸이 옛 눈금과 섞이지 않는다.
        if (incoming === null) newEpoch();
        restoringFromPop.current = true;
        setStrandedEntry(null); setContextBlocked(false);
        applyStudioEntry(readStudioEntry());
      };
      //: ★★★ [FIX3 · 검토 §4] **되돌릴 칸 수를 믿을 수 있을 때만** 붙잡는다.
      //:   · 양쪽 번호를 알아야 한다.
      //:   · `delta === 0` 이면 안 된다 — `history.go(0)` 은 **문서를 다시 읽는다.**
      //:     되돌리려다 입력을 통째로 잃는다. 번호가 겹쳤다는 것 자체가 「모른다」는 뜻이다.
      //:   · 칸 수가 이 문서의 히스토리보다 클 수 없다.
      const delta = incoming !== null && here !== null ? incoming - here : 0;
      const trusted = delta !== 0 && Math.abs(delta) < window.history.length;
      //: 잃을 것이 없으면 그대로 간다 — 물을 이유가 없다.
      if (leavingAnyway.current || canLeaveNow()) { move(); return; }
      if (!trusted) {
        //: ★ 위치를 모른다. **추측하지 않는다** — `go()` 를 부르지 않고 화면·입력도 그대로 둔다.
        //:   확인 전에는 아무것도 적용하지 않고, 어긋난 주소를 배너로 «보이게» 남긴다.
        setStrandedEntry(readStudioEntry());
        return;
      }
      //: ★★★ [지시 4 유지] 이동 «전» 에 묻는다.
      //: ⚠️ 취소는 **온 만큼 그대로** 되돌린다. `pushState` 로 되돌리면 항목이 늘어난다.
      skipNextPop.current = true;
      window.history.go(-delta);
      confirmLeave(() => {
        //: 복원 popstate 가 아직 안 왔으면 담아 두었다가 그 뒤에 간다.
        if (skipNextPop.current) { pendingApproval.current = delta; return; }
        leavingAnyway.current = true;
        window.history.go(delta);
      });
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, [applyStudioEntry]);
  //   ★★★ [FIX1 · 지시 3 / 결정서 §2·§3] **열린 대상을 주소에 유지하고, 히스토리는 아껴 쓴다.**
  //
  //   ⚠️ 정규형은 문법 모듈이 만든다. 여기서 손으로 조립하면 파서와 조용히 갈라진다.
  //   ⚠️ 관련 없는 쿼리와 hash 는 **그대로 둔다**(결정서 §3) — 직렬화 결과를 통째로
  //     덮어쓰지 않고 «대상 키만» 바꿔 끼운다.
  const openTarget = React.useMemo<StudioTarget | null>(() => {
    const release = (viewingRelease as { release_id?: string } | null)?.release_id || pendingRelease;
    if (release) return { kind: 'release', releaseId: release };
    if (openedDraft && (openedDraft.draftKind === 'blueprint' || openedDraft.draftKind === 'consultation')) {
      return { kind: 'draft', draftKind: openedDraft.draftKind,
        draftId: openedDraft.draftId, revision: openedDraft.revision };
    }
    if (openedKitApp) return { kind: 'kit_app', instanceId: openedKitApp.instanceId, appId: openedKitApp.appId };
    if (openedMega && currentProjectId) {
      return { kind: 'mega', megaProjectId: openedMega.megaProjectId,
        ...(openedMega.childProjectId ? { childProjectId: openedMega.childProjectId } : {}) };
    }
    if (currentProjectId) return { kind: 'project', projectId: currentProjectId };
    //: ★ [FIX2 · 지시 3] `new` 도 주소로 재현된다. 빠뜨리면 만들기 화면이 열려 있는데
    //:   URL 은 목록을 가리켜, 새로고침하면 입력하던 화면이 사라진다.
    if (buildStart) return { kind: 'new' };
    return null;
  }, [viewingRelease, pendingRelease, openedDraft, openedKitApp, openedMega, currentProjectId, buildStart]);
  useEffect(() => {
    if (!routeRestored || typeof window === 'undefined') return;
    //: ★★★ [FIX2 · 지시 2] **«복원 완료» 와 «쓰기 필요» 를 분리한다.**
    //:
    //: ⚠️⚠️ 종전에는 URL 이 이미 같으면 여기서 일찍 `return` 하고 표시를 그 «뒤» 에서
    //:   껐다. 정상 복원은 대개 URL 이 같으므로 표시가 **다음 클릭까지 남았고**, 그
    //:   클릭이 추가(push) 대신 교체(replace)가 되어 **기록을 잃었다.**
    const restoring = restoringFromPop.current;
    restoringFromPop.current = false;
    const next = new URL(window.location.href);
    for (const key of ['space', 'target', 'draft_kind', 'draft', 'revision', 'instance', 'app',
                       'release', 'mega', 'child', 'project']) next.searchParams.delete(key);
    if (openTarget) {
      try {
        new URLSearchParams(serializeStudioLocation({ target: openTarget }).slice(1))
          .forEach((value, key) => next.searchParams.set(key, value));
      } catch {
        return;            // 정규형을 만들 수 없으면 주소를 건드리지 않는다
      }
    } else if (space !== 'enterprise') next.searchParams.set('space', space);
    const search = next.search;
    if (search === window.location.search) return;      // 같은 주소면 기록하지 않는다
    const url = `${next.pathname}${search}${next.hash}`;
    const state = (window.history.state || {}) as Record<string, unknown>;
    if (restoring) {
      //: 복원은 «현재 칸을 교체» 한다 — 번호도 그대로 둔다.
      window.history.replaceState(state, '', url);
    } else {
      //: ⚠️ 번호를 «잃은» 상태(우리 것이 아닌 항목 위)에서는 0 부터 다시 센다. 1 로 시작하면
      //:   실제 위치와 어긋난 채로 `go(delta)` 를 계산하게 된다.
      const index = (historyIndex.current ?? -1) + 1;
      window.history.pushState(
        { ...state, __studioIndex: index, __studioEpoch: historyEpoch.current || newEpoch() },
        '', url);
      historyIndex.current = index;
    }
  }, [openTarget, routeRestored, space, addressNonce, newEpoch]);
  // 경영 홈 → Factory, 목록 → 프로젝트처럼 화면 문맥이 바뀔 때 이전 화면의 스크롤 위치를
  // 가져오면 핵심 행동과 헤더가 화면 밖에서 시작한다. 새 화면은 항상 문서 맨 위에서 시작한다.
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [space, currentProjectId]);
  // §5.2 «새 업무 만들기» — 생성은 목록면에서 분리된 별도 흐름이다(설계 `/build/start`).
  const [buildStartType, setBuildStartType] = useState<BuildDeliverableType>('software_app');
  const openBuildStart = (type: BuildDeliverableType) => {
    setBuildStartType(type);
    setBuildStart(true);
  };
  //   ★ [B6] `?space=build&target=new` 로 들어오면 만들기 흐름을 연다. 조회 대상이 없으므로
  //     진입 확인 게이트를 태우지 않는다 — 확인할 것이 없는 곳에 확인 화면을 띄우지 않는다.
  //   ⚠️ 여는 자리는 **첫 렌더의 초기값**이다(위 `buildStart` 선언). effect 로 옮기면
  //     그 사이 렌더가 주소를 목록으로 밀어 히스토리에 군더더기 칸이 생긴다 — 실측으로 봤다.
  //   ★ 닫으면 `onClose` 가 주소에서 `target=new` 를 걷어 내므로, 닫은 뒤 새로고침해도
  //     폼이 되살아나지 않는다. 「열려 있으면 주소에도 있다」가 이제 양쪽으로 성립한다.
  useEffect(() => {
    if (initialEntry.current.isNew) initialEntry.current = { ...initialEntry.current, isNew: false };
  }, []);
  //   ★ [B6] `?space=build&target=release&release=<id>` 직접 링크. `viewRelease` 가 서버에
  //     묻고 실패를 상태로 남기므로 별도 게이트를 두지 않는다 — 판정은 서버가 한다.
  useEffect(() => {
    const target = initialEntry.current.release;
    if (!target) return;
    initialEntry.current = { ...initialEntry.current, release: null };
    openRelease(target);
  }, [openRelease]);
  const [showSkillEvolution, setShowSkillEvolution] = useState(false);
  const [showKnowledgeHub, setShowKnowledgeHub] = useState(false);
  const [knowledgeInitialView, setKnowledgeInitialView] = useState<KnowledgeView>('packs');
  const [showDataPrep, setShowDataPrep] = useState(false);
  const [dataPrepInitialView, setDataPrepInitialView] = useState<'overview' | 'readiness'>('overview');
  const [showCalcApproval, setShowCalcApproval] = useState(false);
  const [showPathCalc, setShowPathCalc] = useState(false);
  const [pathCalcInitialInstanceId, setPathCalcInitialInstanceId] = useState('');
  const [pathCalcInitialAppId, setPathCalcInitialAppId] = useState('');
  const [showScenario, setShowScenario] = useState(false);
  const [showPromotion, setShowPromotion] = useState(false);
  const [showKitOperations, setShowKitOperations] = useState(false);
  // 기술·제품 용어 전환 사전 — 사용자 권장 용어와 현재 기술 용어를 함께 확인하는 임시 페이지.
  const [showTerminology, setShowTerminology] = useState(false);
  const [showMasterData, setShowMasterData] = useState(false);
  const [showWorkStandard, setShowWorkStandard] = useState(false);
  const [showOrgChart, setShowOrgChart] = useState(false);
  const [showContextSwitcher, setShowContextSwitcher] = useState(false);
  //: 어긋난 주소가 떠 있는데 전환을 누른 경우 — 배너에 한 줄을 덧붙여 «먼저 고르라» 고 말한다.
  const [contextBlocked, setContextBlocked] = useState(false);
  /** ★★★ [B6-CONTEXT · 결정 1] 문맥 전환을 여는 **단 하나의 문.**
   *
   *  ⚠️ 대상을 연 화면에도 칩을 달았으므로, 미저장 입력을 든 채로 눌릴 수 있다.
   *    **기존 보호 정책을 그대로** 태운다 — 새 정책을 만들지 않는다. 사용자가 취소하면
   *    전환 창이 열리지 않고, 따라서 **문맥 자체가 바뀌지 않는다.**
   *  ⚠️⚠️ 주소와 화면이 어긋난 동안(경계 배너)에는 **URL 이 열린 대상이라는 가정을 쓸 수 없다.**
   *    그 상태로 전환하면 「무엇을 다시 확인해야 하는지」를 모른 채 확인하게 된다.
   *    그래서 **먼저 그 불일치를 고르게** 한다. */
  const openContextSwitcher = useCallback(() => {
    if (strandedEntry) { setContextBlocked(true); return; }
    confirmLeave(() => setShowContextSwitcher(true));
  }, [strandedEntry]);
  const [showCollaboration, setShowCollaboration] = useState(false);
  // 핵심 여정의 «의사결정 안건»은 계산 결과에 결속된 Decision Case를 검토하는 곳이다.
  // 협업 메뉴는 수신함에서, 핵심 여정 4단계는 의사결정 센터에서 시작한다.
  const [collaborationInitialView, setCollaborationInitialView] = useState<'inbox' | 'decisions'>('inbox');
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
  // ★ 계산 능력 승인·시연 초기화는 `ADMIN_SECURITY`, 즉 시스템 관리자 전용이다.
  // `unrestricted`를 화면에서 새로 해석하지 않고 `/org/me`가 준 `is_admin`을 그대로 쓴다.
  const calcAdminBlocked = !scope
    ? '권한을 확인하는 중입니다 — 잠시 후 다시 시도하십시오.'
    : scope.isAdmin ? '' : '시스템 관리자만 계산 실행을 승인하거나 시연 자료를 초기화할 수 있습니다.';
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
      // [B6] 사용자가 바뀌면 열려 있던 **대상**도 새 권한으로 다시 확인한다(여섯 종류 모두).
      revalidateOpenEntry();
    };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [connectSSE, revalidateOpenEntry]);

  // ★★★ [G1-C1.2] 회사·사업부를 바꾸면 **SSE 를 다시 맺는다.**
  //   티켓에 조직 범위가 봉인돼 있어서, 스트림을 그대로 두면 목록은 A 인데 실시간 이벤트는
  //   계속 B 로 흐른다. 회사 선택기와 실시간 데이터 범위가 어긋나면 사용자는 자기가 보는
  //   숫자가 어느 회사 것인지 알 수 없다 — 경영 화면에서 그것은 오답보다 나쁘다.
  useEffect(() => {
    const h = () => { connectSSE(); revalidateOpenEntry(); };
    window.addEventListener('factory:enterprise-context-changed', h);
    return () => window.removeEventListener('factory:enterprise-context-changed', h);
  }, [connectSSE, revalidateOpenEntry]);

  useEffect(() => {
    // 런처 진입 시 지식팩 목록 로드(생성 폼의 선택지)
    fetch(`${API_BASE_URL}/api/v1/knowledge/packs`).then(r => r.ok ? r.json() : null)
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
      onSelect: () => { setShowAdvisor(false); setSpace('advisor'); } },
    { id: 'collaboration', icon: '🤝', label: '협업·의사결정·발간',
      desc: '앱 전달·수락, 의사결정 패키지, 대내외 발간을 한 곳에서 — 수락해도 데이터 권한은 넓어지지 않습니다',
      onSelect: () => {
        setCollaborationInitialView('inbox');
        setShowCollaboration(false);
        setSpace('report');
      } },
  ];

  // ── 메뉴 묶음 ─────────────────────────────────────────────────────────────
  //
  // ## ⚠️⚠️ [2026-08-24 사용자 지적] 왜 다시 묶었는가
  //
  // > 이 시스템에 접속했을 때 주요 기능이 뭔지, 그 기능이 어디에 있는지, 무슨 버튼을
  // > 클릭해서 실행할 수 있는지를 알 수 없다.
  //
  // 종전 묶음(「데이터 기반」 10개 / 「업무 기준과 조직」 5 / 「운영과 검증」 5)은
  // **성격별 분류**였다. 그래서 「업무 데이터 준비 → 계산 실행 승인 → 경로 계산 →
  // 의사결정 안건」이라는 **하나의 여정**이 10개 목록 안에 흩어져 있었고, 사이에
  // 「시나리오」·「운영 승격」 같은 다른 일이 끼어 있었다. 처음 여는 사람은 그 넷이
  // 이어진 것인 줄 알 수 없다.
  //
  // ★★★ **순서가 있는 것은 순서대로 놓는다.** 첫 묶음이 여정이고, 번호를 붙였다.
  //   나머지 묶음은 「그 여정을 받쳐 주는 것」·「결과를 다르게 돌려 보는 것」·
  //   「내보내는 것」·「누가 판단하는가」로 나눴다.
  // 온톨로지·대외 인텔리전스처럼 제품 화면이 생긴 기능은 이 목록에서 직접 찾을 수 있어야
  // 한다. 숨기는 것은 통제가 아니며 실제 권한은 서버 `route_authority` 표가 막는다.
  //: ★ 상단 셸이 쓰는 문맥. ⚠️ 회사·범위 이름은 **한 곳**에서 얻는다
  //:   (`lib/scopeLabel`) — 화면마다 따로 풀면 같은 것이 두 이름으로 보인다.
  const [openConsole, setOpenConsole] = useState(false);
  //: ★ [2026-08-25] 회사 구성 — 회사 이름·법인/가상회사·업무 연결구성.
  const [showCompany, setShowCompany] = useState(false);
  //: ★ 회사는 `/auth/me`, 범위는 조직도가 답한다 — 어느 쪽도 지어내지 않는다.
  const shellCtx = useOperatingContext();
  // 회사 이름표와 실행 테넌트가 결속되지 않았을 때 내부 식별자를 회사명처럼 보이지 않는다.
  // 실제 결속은 회사 구성에서 고쳐야 하며, 화면은 그 상태를 숨기지 않는다.
  const shellCompanyName = shellCtx.companyName || '회사 연결 필요';

  const navGroups: NavGroup[] = [
    {
      title: '핵심 여정 — 이 다섯을 순서대로',
      hint: '먼저 좌상단 «조직 전환»에서 조직을 고르십시오. 그 다음 아래 다섯을 차례로 지나면 '
        + '데이터 준비부터 경영 브리핑까지 한 흐름으로 닫힙니다.',
      items: [
        { id: 'dataprep', icon: '1️⃣', label: '업무 데이터 준비',
          desc: '샘플 패키지를 조직에 적용하고 · 업무기능별 원천을 연결하고 · 데이터 판을 인증합니다 — 여기가 «준비됨» 이어야 뒤가 돕니다',
          onSelect: () => {
            setDataPrepInitialView('overview'); setShowDataPrep(false); setSpace('data');
          } },
        { id: 'calc-approval', icon: '2️⃣', label: '계산 실행 승인',
          desc: '산식을 실제로 돌려도 되는지 사람이 승인합니다 — 누르기 전까지 계산은 «막힘» 으로 답합니다',
          // ⚠️ 시스템 관리자 전용이다. 화면에서 숨기는 것은 **편의**이고, 실제로 막는 것은
          //   서버(`route_authority` 표의 `ADMIN_SECURITY`)다 — 숨김을 통제로 믿지 않는다.
          disabledReason: calcAdminBlocked,
          onSelect: () => { setShowCalcApproval(false); setSpace('calc'); } },
        { id: 'path-calc', icon: '3️⃣', label: '경로 계산',
          desc: '승인된 관계를 따라가 부족량·생산가능량·매출 이연을 계산합니다 — 막히면 무엇이 없는지 말합니다',
          onSelect: () => {
            //: ★ 모달을 닫고 전체 화면으로 간다 — 대상도 함께 놓는다(위 goHome 과 같은 짝).
            setPathCalcInitialAppId(''); setShowPathCalc(false); setOpenedKitApp(null);
            setSpace('path');
          } },
        { id: 'decision-pkg', icon: '4️⃣', label: '의사결정 안건',
          desc: '경로 계산에서 만든 안건을 세 관점으로 검토하고 · 실행 책임자와 기한을 확정하고 · 근거 계보를 확인합니다',
          onSelect: () => {
            setCollaborationInitialView('decisions');
            setShowCollaboration(false);
            setSpace('report');
          } },
        { id: 'briefing', icon: '5️⃣', label: '경영 브리핑',
          desc: '결정할 일·막힌 일·데이터 결손과 근거를 권한 범위 안에서 확인합니다 (LLM 0콜)',
          onSelect: () => { setShowBriefing(false); setSpace('briefing'); } },
      ],
    },
    {
      title: '근거가 되는 자료',
      hint: '위 넷이 «무엇을 보고» 답하는지를 정하는 곳입니다. 자료가 비면 위에서 막힙니다.',
      items: [
        { id: 'master', icon: '🗂', label: '기준정보 마스터',
          desc: '자재·공정·설비·KPI 골든 레코드 — 확정 조회로 모든 에이전트에 주입(모델 불변)',
          onSelect: () => { setShowMasterData(false); setSpace('master'); } },
        { id: 'knowledge', icon: '📚', label: '지식 허브',
          desc: '도메인 참고자료(표준·논문·데이터)를 등록하고 프로젝트에 연결',
          onSelect: () => { setKnowledgeInitialView('packs'); setShowKnowledgeHub(false); setSpace('knowledge'); } },
        { id: 'ontology', icon: '🕸', label: '업무 온톨로지',
          desc: '승인된 업무 객체·관계를 따라 영향 경로와 결속된 데이터 판을 확인',
          onSelect: () => { setKnowledgeInitialView('ontology'); setShowKnowledgeHub(false); setSpace('knowledge'); } },
        { id: 'external-intelligence', icon: '🌐', label: '대외 인텔리전스',
          desc: '승인 원천·확정 대외지표·발표 시점별 관측값과 기준계획 사용 가능 여부',
          onSelect: () => { setKnowledgeInitialView('external'); setShowKnowledgeHub(false); setSpace('knowledge'); } },
        { id: 'terminology', icon: '📖', label: '기술·제품 용어집',
          desc: '현재 용어·권장 사용자 용어·기술 표준명을 함께 보는 전환 사전',
          onSelect: () => { setShowTerminology(false); setSpace('terminology'); } },
        { id: 'crosswalk', icon: '🔗', label: '연계/크로스워크',
          desc: '외부 시스템(ERP/MES 등)의 키·필드를 기준정보와 매핑 — 초안→사용자 승인',
          onSelect: () => { setShowCrosswalk(false); setSpace('crosswalk'); } },
        { id: 'governance', icon: '🛡️', label: '데이터 거버넌스',
          desc: '조직 범위 노출·중복 기준정보·카탈로그 결손·데이터 계약·외부지표 준비도',
          // ★ 서버가 403 을 줄 자리를 **누르기 전에** 말한다(설계 §10 수용 기준).
          disabledReason: govBlocked,
          onSelect: () => { setShowGovernance(false); setSpace('governance'); } },
      ],
    },
    {
      title: '다르게 돌려 보기',
      hint: '같은 자료로 «만약 이렇다면» 을 계산해 봅니다.',
      items: [
        { id: 'scenario', icon: '📈', label: '시나리오 시뮬레이션',
          desc: '환율·도입 지연·전력단가 → 생산량·재고·현금·손익 (고정 기준선 기준)',
          onSelect: () => { setShowScenario(false); setSpace('twin'); } },
        { id: 'planning', icon: '📊', label: '경영계획',
          desc: '계획·실적·시나리오를 동일 기준선에서 비교 (결정론적 계산, LLM 0콜)',
          onSelect: () => { setShowPlanning(false); setSpace('planning'); } },
        { id: 'shadow', icon: '🧪', label: 'Shadow Mode',
          desc: '새 규칙·모델을 지금 규칙과 «나란히» 돌려 결과를 비교합니다 — 승인 전에는 운영에 쓰이지 않습니다',
          onSelect: () => { setShowShadow(false); setSpace('shadow'); } },
      ],
    },
    {
      title: '만든 것을 내보내기',
      hint: '시연·후보 상태의 것을 실제 업무에 쓰도록 올립니다.',
      items: [
        { id: 'promotion', icon: '🚀', label: '운영 승격',
          desc: '후보 판을 운영으로 — 계약·물질화·정적검사·승인·데이터 준비도 다섯 검사',
          onSelect: () => { setShowPromotion(false); setSpace('promotion'); } },
        { id: 'workspace', icon: '🏢', label: '워크스페이스',
          desc: '부서 앱의 공유·복제와 전사 승격 게이트 — 계약·보안·품질·소유자 승인을 모두 통과해야 승격',
          onSelect: () => { setShowWorkspace(false); setSpace('workspace'); } },
      ],
    },
    {
      title: '누가 무엇을 판단하는가',
      hint: '사람과 에이전트의 권한·기준을 정합니다.',
      items: [
        //: ★★★ [2026-08-25 사용자 지적] 「회사 구성 정보를 등록하는 화면이 없다」.
        //: ⚠️ `조직·권한` 은 **부서·사용자**다. 회사(법인·가상회사) 자체를 등록하는 곳은
        //:   따로 없었다 — 백엔드는 다 있는데 부르는 화면이 없었다.
        //: ⚠️ 여기는 **배열 리터럴**이라 `{/* */}` JSX 주석을 쓰면 빌드가 깨진다
        //:   (`SessionBar` 주석이 같은 실수를 이미 적어 두었다 — 세 번째다).
        { id: 'company', icon: '🏛', label: '회사 구성',
          desc: '회사 이름 · 법인과 가상회사 등록·승인 · 업무 연결구성(Digital Thread) — 실제와 가상은 섞이지 않습니다',
          onSelect: () => { setShowCompany(false); setSpace('company'); } },
        { id: 'org', icon: '🏢', label: '조직·권한',
          desc: '부서·사용자·권한 — 부서는 기준정보라 개편하면 새 버전이 되고 구판은 이력으로 남습니다',
          onSelect: () => { setShowOrgChart(false); setSpace('org'); } },
        { id: 'standard', icon: '📜', label: '업무표준',
          desc: '에이전트의 법규·사규 — 무엇을 어떤 기준으로 평가해 다음 단계로 넘기는지. 개정 시 구판 보존',
          onSelect: () => { setShowWorkStandard(false); setSpace('standard'); } },
        { id: 'agents', icon: '⚙️', label: '에이전트 통제소',
          desc: '각 에이전트의 역할·스킬·모델·순서·HOTL(전문가 개입)을 설정',
          onSelect: () => { closeAgentPanel(); setSpace('agent'); } },
        { id: 'agent-gov', icon: '🏛', label: 'Agent Governance Center',
          desc: '조직 자산의 범위·권한·승인 — 누가 만들고 누가 승인해서 어디에 쓰이는가',
          // ⚠️ 여기는 「내 업무」다 — viewer 도 자기 범위의 자산을 볼 수 있어야 하므로
          //   거버넌스 콘솔(전사 정비 상태)과 달리 막지 않는다. 자격은 화면 안에서
          //   행동 단위로 표시하고, 못 누르는 버튼마다 사유를 붙인다(§8.6).
          onSelect: () => { setShowAgentGov(false); setSpace('agentgov'); } },
        { id: 'skills', icon: '🧬', label: 'AI 스킬 진화',
          desc: '에이전트가 스스로 제안한 스킬 개선안 승인/반려',
          onSelect: () => { setShowSkillEvolution(false); setSpace('skills'); } },
      ],
    },
    {
      title: '점검',
      hint: '실제로 무엇이 돌았는지 확인합니다.',
      items: [
        { id: 'telemetry', icon: '📈', label: 'LLM 텔레메트리',
          desc: '실제 사용 모델·폴백·소요시간 — 모델 불변성 실측',
          // ⚠️ 이 화면의 «품질 결과» 탭과 에이전트 집계는 거버넌스 관문을 지난다 —
          //   `/telemetry/agents` 가 형제 둘과 갈라져 익명에게 열려 있던 것을 함께 고쳤다.
          disabledReason: govBlocked,
          onSelect: () => { setShowTelemetry(false); setSpace('telemetry'); } },
      ],
    },
  ];

  const currentProject = projects.find(p => p.id === currentProjectId);
  const currentTemplateId = String((currentProject as any)?.template_id || 'default');
  const deliverableByTemplate = new Map((templates as any[]).map((template) => [
    String(template?.template_id || template?.id || ''),
    String(template?.deliverable_type || 'software_app'),
  ]));
  const projectsFor = (type: BuildDeliverableType) => templates.length === 0 ? [] : projects.filter(
    (project) => String(deliverableByTemplate.get(String(project.template_id || 'default'))
      || 'software_app') === type);
  const appProjects = projectsFor('software_app');
  const simulationProjects = projectsFor('hybrid_simulation');
  const reportProjects = projectsFor('document_report');
  const currentTemplate = (templates as any[]).find((t) => (
    String(t?.template_id || t?.id || '') === currentTemplateId
  ));
  const currentDeliverableType = String(currentTemplate?.deliverable_type || 'software_app');
  const workbenchParent = currentDeliverableType === 'hybrid_simulation' ? 'twin'
    : currentDeliverableType === 'document_report' ? 'report' : 'build';
  const workbenchParentLabel = currentDeliverableType === 'hybrid_simulation' ? '시뮬레이션'
    : currentDeliverableType === 'document_report' ? '결정·보고' : '앱 제작';
  const workbenchLabel = currentDeliverableType === 'hybrid_simulation' ? '시뮬레이터 제작 작업공간'
    : currentDeliverableType === 'document_report' ? '보고서 제작 작업공간' : '앱 제작 작업공간';
  const isMegaProject = currentProject?.is_mega_project === true;

  // 보고서 목록뿐 아니라 새로고침·직접 URL 복원에서도 결과 검토 화면을 연다.
  // 구형 3패널은 SW 제작용이라 범용 artifacts 를 표시하지 못한다.
  useEffect(() => {
    if (currentProjectId && currentDeliverableType === 'document_report') {
      setShowStudio(true);
    }
  }, [currentProjectId, currentDeliverableType]);

  const handleShellNav = (id: Parameters<React.ComponentProps<typeof ProductShell>['onNav']>[0]) => {
    if (id === 'enterprise') { setSpace('enterprise'); return; }
    if (id === 'factory') { setSpace('build'); return; }
    // 「결정·보고」는 협업 허브의 받은함이 아니라 의사결정 패키지에서 시작한다.
    // 상단 메뉴 이름과 첫 화면이 다르면 사용자는 잘못 열린 것으로 판단한다.
    if (id === 'report') {
      setCollaborationInitialView('decisions');
      setShowCollaboration(false);
      setSpace('report');
      return;
    }
    if (id === 'operate') { setShowKitOperations(false); setSpace('operate'); return; }
    if (id === 'twin') { setShowScenario(false); setSpace('twin'); return; }
    if (id === 'knowledge') {
      setKnowledgeInitialView('packs'); setShowKnowledgeHub(false); setSpace('knowledge'); return;
    }
    if (id === 'agent') { closeAgentPanel(); setSpace('agent'); return; }
    const map: Record<string, string> = {};
    const hit = [...primaryNav, ...navGroups.flatMap((g) => g.items)]
      .find((it) => it.id === map[id]);
    if (hit) hit.onSelect();
  };

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

  // ★★★ [2026-08-23 실측] **오버레이 목록은 한 벌만 둔다.**
  //
  // ## 무엇이 고장나 있었는가
  //
  // 이 파일에는 최상위 `return` 이 셋 있고(경영 홈 / 런처 / Studio), **각자 자기 모달
  // 목록을 손으로** 들고 있었다. 세 목록을 실제로 비교해 보니:
  //
  //   · 경영 홈  22개 — `showAgentPanel` 이 빠져 「⚙️ 에이전트 통제소」가 **안 열렸다**
  //   · 런처     24개
  //   · Studio   10개 — **14개가 빠져** 업무 데이터 준비·경로 계산·계산 실행 승인·
  //     의사결정 안건·기준정보 마스터·지식 허브·용어집·업무표준·조직·권한·크로스워크·
  //     시나리오·운영 승격·스킬 진화·텔레메트리가 전부 **눌러도 아무 일이 없었다**
  //
  // ★ 메뉴는 세 화면에서 **똑같은 목록**을 보여 준다. 즉 화면은 「있다」고 말하고 실제로는
  //   없었다. 사용자는 그것을 권한 문제로 읽지 않고 **고장으로 읽는다**.
  //
  // ⚠️ 이 파일의 495행 주석이 이미 같은 사고를 한 번 기록했고(「런처에서 빼면 메뉴는
  //   활성으로 보이는데 눌러도 아무 일이 없다」), 473행 주석은 「기존 중복이며 정리
  //   대상이다」라고 적어 두었다. 목록이 여러 벌인 한 같은 사고가 반복된다.
  //
  // ★ 컴포넌트가 아니라 **엘리먼트 상수**로 둔다. 렌더 함수 안에서 컴포넌트를 정의하면
  //   매 렌더마다 타입이 달라져 하위 트리가 통째로 다시 마운트된다(입력 중이던 값이 사라진다).
  //: ★★★ [2026-08-25] **모든 대화상자가 「경영 홈」으로 돌아갈 수 있게** 한 곳에서 준다.
  //: ⚠️ 화면 24개가 각자 머리 바를 그리므로 버튼을 화면마다 달면 반드시 빠뜨린다.
  //:   `HubDialog` 가 그리는 문맥 띠에 넣고, 손잡이만 여기서 내려보낸다.
  //: ★ 열려 있는 것을 **닫고** 홈으로 간다 — 닫지 않으면 홈 위에 창이 그대로 남는다.
  const goHome = useCallback(() => {
    //: ★ 열려 있는 것을 **전부 닫는다.** 닫지 않으면 홈 위에 창이 그대로 남아,
    //:   「홈으로 갔는데 화면이 그대로」가 된다.
    //: ⚠️ 목록을 손으로 들고 있으면 새 화면이 생길 때 빠뜨린다 — 위 `show*` 상태
    //:   선언과 **같은 순서**로 적어 두고, 새 화면을 더할 때 여기도 더한다.
    setShowSkillEvolution(false);
    setShowKnowledgeHub(false);
    setShowDataPrep(false);
    setShowCalcApproval(false);
    //: ★★★ [FIX3 · 2026-09-18 실화면 실측] 업무앱은 **화면과 대상을 «함께»** 놓는다.
    //:   ⚠️ 종전에는 이 줄이 `setShowPathCalc(false)` 뿐이었다. 화면은 닫히는데
    //:     `openedKitApp` 이 남아 **주소는 계속 업무앱을 가리켰다** — 실제로 「⌂ 경영 홈」
    //:     을 눌러 홈으로 갔는데 URL 은 `target=kit_app…` 이었고, 새로고침하면 방금
    //:     떠난 화면이 다시 열린다. 이 머리말이 경고한 「새 화면을 더할 때 여기도 더한다」
    //:     를 내가 빠뜨린 것이다.
    setShowPathCalc(false); setOpenedKitApp(null);
    setShowScenario(false);
    setShowPromotion(false);
    setShowKitOperations(false);
    setShowTerminology(false);
    setShowMasterData(false);
    setShowWorkStandard(false);
    setShowOrgChart(false);
    setShowCollaboration(false);
    setShowCrosswalk(false);
    setShowTelemetry(false);
    setShowAdvisor(false);
    setShowGovernance(false);
    setShowShadow(false);
    setShowWorkspace(false);
    setShowPlanning(false);
    setShowBriefing(false);
    setShowStudio(false);
    setShowAgentGov(false);
    setShowLogPopup(false);
    setShowCompany(false);
    setCurrentProject(null);
    // [B6] 직접 링크 진입 게이트도 함께 닫는다 — 남겨 두면 확인 화면이 다시 뜬다.
    setEntryGateId(null);
    setRouteRestored(true);
    setSpace('enterprise');
  }, []);

  const overlays = (
    <HomeNavContext.Provider value={goHome}>
      {/*: ★★★ [FIX3 · 검토 §4] **주소와 화면이 어긋난 채로 둔다 — 대신 보이게 둔다.**
            뒤로/앞으로가 «번호를 모르는» 항목으로 갔고, 저장하지 않은 입력이 있어 화면을
            내리지 않았다. 되돌릴 칸 수를 모르므로 `history.go()` 로 되돌리는 시늉을 하지
            않는다(잘못 세면 엉뚱한 곳으로 가고, `go(0)` 은 문서를 다시 읽어 입력을 잃는다).
            ★ 그래서 **고르는 것은 사용자**다. 둘 다 명시적이고, 둘 다 칸을 늘리지 않는다. */}
      {strandedEntry && (
        <div className="afs-stranded-address" style={{ position: 'fixed', left: 16, right: 16, bottom: 16, zIndex: 60 }}>
          <Banner tone="warn" title="주소창이 이 화면과 다릅니다">
            저장하지 않은 입력이 있어 화면을 그대로 두었습니다. 어떻게 할까요?
            {contextBlocked && (
              <div style={{ marginTop: 6, fontWeight: 700 }}>
                주소와 화면이 다른 동안에는 회사·범위를 바꿀 수 없습니다 — 먼저 아래에서 골라 주십시오.
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <button type="button" className="primary-button" onClick={() => {
                //: 주소가 가리키는 곳으로 간다 — **입력 정책은 기존 확인 UI 가 그대로** 가진다.
                const target = strandedEntry;
                confirmLeave(() => {
                  const st = (window.history.state || {}) as Record<string, unknown>;
                  const at = st.__studioIndex, ep = st.__studioEpoch;
                  if (Number.isSafeInteger(at) && typeof ep === 'string' && ep) {
                    historyIndex.current = at as number; historyEpoch.current = ep;
                  } else { historyIndex.current = null; newEpoch(); }
                  restoringFromPop.current = true;
                  setStrandedEntry(null); setContextBlocked(false);
                  applyStudioEntry(target);
                });
              }}>주소가 가리키는 화면으로 이동</button>
              <button type="button" className="secondary-button" onClick={() => {
                //: 이 화면을 지킨다. **현재 칸의 주소만 바꿔 끼운다** — 새 칸을 만들지 않고
                //: 없는 번호도 지어내지 않는다(기존 state 를 그대로 둔 채 교체한다).
                //: ★★★ [FIX4 · 검토 A] 그리고 **우리 눈금을 «이 칸» 에 맞춘다.**
                //:   ⚠️ 종전에는 옛 화면의 번호가 그대로 남았다. 그 상태로 다음 이동을 하면
                //:     엉뚱한 번호를 붙이고, 그 뒤 뒤로/앞으로가 남의 눈금으로 계산된다.
                //:   ★ 이 칸에 번호가 없으면 **없는 채로 둔다**(지어내지 않는다). 그러면
                //:     다음에 우리가 만드는 칸이 0 부터 새 구간으로 시작한다.
                const st = (window.history.state || {}) as Record<string, unknown>;
                const at = st.__studioIndex, ep = st.__studioEpoch;
                if (Number.isSafeInteger(at) && typeof ep === 'string' && ep) {
                  historyIndex.current = at as number; historyEpoch.current = ep;
                } else { historyIndex.current = null; newEpoch(); }
                setStrandedEntry(null); setContextBlocked(false);
                restoringFromPop.current = true;
                setAddressNonce((n) => n + 1);
              }}>이 화면의 주소로 되돌리기</button>
            </div>
          </Banner>
        </div>
      )}
      {buildStart && (
        <BuildStartDialog
          deliverableType={buildStartType}
          templates={templates as any}
          knowledgePacks={knowledgePacks}
          packsBlocked={packsBlocked}
          /*: ⚠️⚠️ [2026-09-16 실화면 실측] **닫으면 주소도 그 초안을 놓아야 한다**(결정서 §4).
              종전에는 편집기를 닫아도 `openedDraft` 가 남아 URL 이 계속 「초안이 열려 있다」고
              말했다 — 화면은 목록인데 새로고침하면 초안이 다시 열린다. 주소가 거짓말을 한다. */
          /*: ★ [B6-CONTEXT · 결정 1] 초안 편집기 안에서도 회사 문맥을 보고 바꾼다.
               셸과 같은 컴포넌트를 «부모가» 넣는다 — 대화상자가 스스로 만들면 갈라진다. */
          contextChip={<OperatingContextChip company={shellCompanyName}
            scope={shellCtx.scopeLabel} entityMode={shellCtx.entityMode}
            onContext={openContextSwitcher} />}
          onClose={() => { setBuildStart(false); setOpenedDraft(null); }}
          onOpenDataPrep={() => { setBuildStart(false); setOpenedDraft(null); setShowDataPrep(true); }}
          onCreate={async (r) => {
            const domains = r.masterDomains.split(',').map((x) => x.trim()).filter(Boolean);
            const createdProjectId = r.isMega
              ? await createMegaProject(r.projectName, r.templateId)
              : await createProject(r.projectName, r.templateId, r.packIds,
                  domains, r.mcpLiveGrounding, r.kitInstanceId);
            if (createdProjectId) {
              setBuildStart(false);
              setCurrentProject(createdProjectId);
            }
          }} />
      )}
      {showSkillEvolution && (
        <SkillEvolutionPanel onClose={() => setShowSkillEvolution(false)} />
      )}
      {showDataPrep && (
        <DataPrepPanel initialView={dataPrepInitialView}
          onClose={() => setShowDataPrep(false)} />)}
      {showCalcApproval && (
        <CalcApprovalPanel onClose={() => setShowCalcApproval(false)} />)}
      {showPathCalc && <PathCalcPanel
        initialInstanceId={pathCalcInitialInstanceId}
        initialAppId={pathCalcInitialAppId}
        /*: ⚠️ [FIX2 · 지시 3] 닫으면 **주소도 그 업무앱을 놓는다** — 초안 닫기와 같은 문제였다. */
        onClose={() => { setShowPathCalc(false); setOpenedKitApp(null); }} />}
      {showScenario && <ScenarioPanel onClose={() => setShowScenario(false)} />}
      {showPromotion && (
        <ReleasePromotionPanel onClose={() => setShowPromotion(false)} />
      )}
      {showKitOperations && (
        <KitOperationsPanel
          onClose={() => setShowKitOperations(false)}
          onOpenBuild={() => {
            setShowKitOperations(false);
            setSpace('build');
            openBuildStart('software_app');
          }}
          onOpenSimulation={(instanceId, appId) => {
            setPathCalcInitialInstanceId(instanceId);
            setPathCalcInitialAppId(appId);
            setShowKitOperations(false);
            //: ★ [FIX2 · 지시 3] 주소로 «열 때» 와 «같은 대상» 을 기록한다. 한쪽만 기록하면
            //:   화면은 업무앱인데 주소는 목록이고, 새로고침이 화면을 버린다.
            setOpenedKitApp({ instanceId, appId });
            setShowPathCalc(true);
          }}
        />
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
      {showContextSwitcher && (
        <OperatingContextSwitcher
          onClose={() => setShowContextSwitcher(false)}
          onManageOrg={() => { setShowContextSwitcher(false); setShowOrgChart(true); }}
          onManageCompany={() => { setShowContextSwitcher(false); setShowCompany(true); }} />
      )}
      {showCompany && (
        <CompanySetupPanel onClose={() => setShowCompany(false)} />
      )}
      {showCollaboration && (
        <CollaborationHub
          onClose={() => setShowCollaboration(false)}
          initialView={collaborationInitialView}
          // 라이브러리에 있는 릴리스를 그대로 선택지로 넘긴다 — 화면이 id 를 지어내지 않는다.
          releaseOptions={releases.filter((r: any) => r.release_id).map((r: any) => ({
            id: r.release_id,
            label: r.display_name || r.project_name || '이름 미등록 앱',
          }))}
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
        <WorkspacePanel onClose={() => setShowWorkspace(false)}
          releaseOptions={releases.filter((r: any) => r.release_id).map((r: any) => ({
            id: r.release_id,
            label: r.display_name || r.project_name || '이름 미등록 릴리스',
            projectId: r.project_id || '',
          }))} />
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
    </HomeNavContext.Provider>
  );


  //   [B6] 조회 실패를 빈 화면으로 두지 않는다. 결과물을 못 열었으면 그렇게 말하고
  //     되돌아갈 길과 다시 시도할 길을 함께 준다.
  if (!viewingRelease && (releaseLoad === 'loading' || releaseLoad === 'failed' || releaseLoad === 'forbidden')) {
    return (
      <ErrorBoundary>
        {overlays}
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <div className="flex items-center gap-3 px-4 py-3 border-b afs-border">
            <button
              onClick={() => { leaveRelease(); setSpace('enterprise'); }}
              className="text-sm font-bold text-gray-100 hover:text-white bg-indigo-700 hover:bg-indigo-600 px-3 py-1.5 rounded transition-colors"
            >⌂ 경영 홈</button>
            <button
              onClick={() => { leaveRelease(); setSpace('build'); }}
              className="text-sm font-bold text-gray-400 hover:text-gray-100 bg-gray-700 px-3 py-1.5 rounded transition-colors"
            >◀ 앱 제작</button>
          </div>
          <main className="flex-1 min-h-0 overflow-auto p-6">
            <section aria-label={releaseLoad === 'loading' ? '결과물 조회 중' : '결과물 확인 필요'}>
              {releaseLoad === 'loading' ? (
                <>
                  <p role="status">결과물을 불러오는 중입니다.</p>
                  <button onClick={leaveRelease}
                    className="mt-4 text-sm px-3 py-2 rounded bg-gray-700 text-gray-100">조회 취소</button>
                </>
              ) : <p role="alert">{releaseError || '결과물을 확인하지 못했습니다.'}</p>}
            </section>
          </main>
        </div>
      </ErrorBoundary>
    );
  }

  if (viewingRelease) {
    return (
      <ErrorBoundary>
        <div className="h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans overflow-hidden">
          <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6 shrink-0">
            <div className="flex items-center gap-4 min-w-0">
              <button onClick={leaveRelease} className="text-sm font-bold text-gray-400 hover:text-gray-100 bg-gray-700 px-3 py-1.5 rounded transition-colors shrink-0">◀ 라이브러리</button>
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

  // 핵심 여정은 앱 제작·운영·시뮬레이션과 같은 ProductShell 아래의 독립 페이지다.
  // 홈 위 전체화면 대화상자로 열면 상단 메뉴·회사 문맥·행동 영역이 사라져 같은 제품의
  // 화면으로 읽히지 않는다. 프로젝트 작업공간에서 여는 보조 진입만 기존 대화상자를 유지한다.
  const journeyPage = space === 'advisor'
    ? <AdvisorPanel page onClose={() => setSpace('enterprise')} onProjectCreated={fetchProjects} />
    : space === 'data'
      ? <DataPrepPanel page initialView={dataPrepInitialView} onClose={() => setSpace('enterprise')} />
      : space === 'calc'
        ? <CalcApprovalPanel page onClose={() => setSpace('enterprise')} />
        : space === 'path'
          ? <PathCalcPanel page initialInstanceId={pathCalcInitialInstanceId}
              initialAppId={pathCalcInitialAppId}
              onClose={() => setSpace('enterprise')} />
          : space === 'briefing'
            ? <BriefingPanel page onClose={() => setSpace('enterprise')} />
            : space === 'master'
              ? <MasterDataPanel page onClose={() => setSpace('knowledge')} />
              : space === 'terminology'
                ? <TerminologyGlossaryPanel page onClose={() => setSpace('knowledge')} />
                : space === 'crosswalk'
                  ? <CrosswalkPanel page onClose={() => setSpace('knowledge')} />
                  : space === 'governance'
                  ? <GovernanceConsole page onClose={() => setSpace('knowledge')} />
                  : space === 'planning'
                    ? <SimulationGovernanceShell kind="planning">
                        <PlanningPanel page onClose={() => setSpace('twin')} />
                      </SimulationGovernanceShell>
                    : space === 'shadow'
                      ? <SimulationGovernanceShell kind="shadow">
                          <ShadowModePanel page onClose={() => setSpace('twin')} />
                        </SimulationGovernanceShell>
                      : space === 'promotion'
                        ? <OperationsGovernanceShell kind="promotion">
                            <ReleasePromotionPanel page onClose={() => setSpace('operate')} />
                          </OperationsGovernanceShell>
                        : space === 'workspace'
                          ? <OperationsGovernanceShell kind="workspace">
                              <WorkspacePanel page onClose={() => setSpace('operate')}
                                releaseOptions={releases.filter((r: any) => r.release_id).map((r: any) => ({
                                  id: r.release_id,
                                  label: r.display_name || r.project_name || '이름 미등록 릴리스',
                                  projectId: r.project_id || '',
                                  //: 같은 이름의 두 판을 가르는 값. 서버가 안 주면 빈 값으로
                                  //:   두고 화면이 「시각 미기록」이라고 적는다(지어내지 않는다).
                                  createdAt: r.created_at || '',
                                }))} />
                            </OperationsGovernanceShell>
                          : space === 'company'
                            ? <CompanySetupPanel page onClose={() => setSpace('enterprise')} />
                            : space === 'org'
                              ? <OrgChartPanel page onClose={() => setSpace('enterprise')} />
                              : space === 'standard'
                                ? <WorkStandardPanel page onClose={() => setSpace('knowledge')} />
                                : space === 'agentgov'
                                  ? <AgentGovernancePanel page onClose={() => setSpace('agent')} />
                                  : space === 'skills'
                                    ? <SkillEvolutionPanel page onClose={() => setSpace('agent')} />
                                    : space === 'telemetry'
                                      ? <TelemetryPanel page onClose={() => setSpace('agent')} />
            : null;
  const journeyModule = space === 'advisor' ? 'advisor'
    : space === 'data' ? 'data'
      : space === 'calc' ? 'calc'
        : space === 'path' ? 'path'
          : space === 'briefing' ? 'briefing' : null;
  const foundationModule = space === 'master' ? 'master'
    : space === 'terminology' ? 'terminology'
      : space === 'crosswalk' ? 'crosswalk'
      : space === 'governance' ? 'governance' : null;
  const decisionModule = space === 'planning' ? 'planning'
    : space === 'shadow' ? 'shadow'
      : space === 'promotion' ? 'promotion'
        : space === 'workspace' ? 'workspace' : null;
  const governanceModule = space === 'company' ? 'company'
    : space === 'org' ? 'org'
      : space === 'standard' ? 'standard'
        : space === 'agentgov' ? 'agentgov'
          : space === 'skills' ? 'skills' : null;
  const inspectionModule = space === 'telemetry' ? 'telemetry' : null;

  if (!currentProjectId && journeyPage
    && (journeyModule || foundationModule || decisionModule || governanceModule || inspectionModule)) {
    return (
      <ErrorBoundary>
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <ProductShell module={journeyModule || foundationModule || decisionModule
            || governanceModule || inspectionModule!}
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => setSpace('build')}
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', width: '100%' }}>
            {journeyPage}
          </main>
        </div>
        {overlays}
      </ErrorBoundary>
    );
  }

  if (!currentProjectId && space === 'about') {
    return (
      <ErrorBoundary>
        <div className="afs-scope" style={{ minHeight: '100vh', background: 'var(--surface-page)' }}>
          <ProductShell module="about"
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => setSpace('build')}
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <SystemAboutPage company={shellCompanyName}
            onBack={() => setSpace('enterprise')}
            onCompanySetup={() => setShowCompany(true)} />
        </div>
        {overlays}
      </ErrorBoundary>
    );
  }

  // ★★★ [설계 §3.2] 프로젝트를 고르지 않았고 «경영 홈» 공간이면 Decision Canvas 를 그린다.
  //   Software Factory(런처)는 그 아래 Studio 다.
  if (!currentProjectId && space === 'enterprise') {
    return (
      <ErrorBoundary>
        <div className="afs-scope enterprise-home">
          {/* ★ [설계 §3.1] Top Bar **72px** · 구조색. ⑥ 상단 회사·사업부·공장 Context 는
              `CompanyContextBar` 가 담당한다(§4.1).
              ⚠️⚠️ [2026-08-23 실측] `afs-topbar` 를 **반드시 붙인다.** 이 바는 구조색(남색)
                위인데, 클래스가 없으면 `afs.css` 의 「바 위에서는 유틸리티를 다시 해석한다」
                규칙(`.afs-scope .afs-topbar .afs-muted` 등)이 전부 건너뛰어진다. 그러면 안에
                있는 `CompanyContextBar`·`SessionBar`·`GlobalNav` 가 **본문용 어두운 색**을
                그대로 써서 어두운 바에 얹힌다 — 로그인한 사람 이름「권희권」이 2.22:1,
                구분자 `│` 가 1.01:1 로 측정됐다(사실상 안 보인다).
                ★ 배경·테두리는 아래 인라인이 이미 정하므로 클래스는 **재해석만** 켠다. */}
          {/* ★★★ [2026-08-25] 승인 시안의 상단 셸을 **그대로** 쓴다.
              ⚠️ 종전에는 우리가 만든 72px 바에 회사문맥바+세션바+검색메뉴를 나열했다 —
                높이도 색도 배치도 시안과 달랐다(사용자 지적). 시안은 네 칸 그리드다:
                브랜드 210 · 회사 문맥 270 · 전역 내비 1fr · 행동 auto. */}
          <ProductShell
            module="enterprise"
            //: ★ 사람에게는 이름을, 없으면 식별자를 — 지어내지 않는다.
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => setSpace('build')}
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)}
                openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <EnterprisePage
            onOpenBuild={() => setSpace('build')}
            onOpenDataReadiness={() => {
              setDataPrepInitialView('readiness');
              setShowDataPrep(true);
            }}
            //: ⚠️ 여기서 id 를 **하나씩 손으로** 잇지 않는다 — 종전에 그렇게 두었다가
            //:   화면마다 목록이 갈라져 「메뉴에 있는데 눌러도 아무 일이 없는」 항목이
            //:   14개 생겼다(이 파일 위쪽 주석). 메뉴 정의를 그대로 뒤진다.
            onOpenMenu={(id) => {
              const hit = [...primaryNav, ...navGroups.flatMap((g) => g.items)]
                .find((it) => it.id === id);
              if (hit) hit.onSelect();
            }} />
        </div>
        {/* ★ 오버레이는 **한 벌**이다 — 위 `overlays` 선언 참조. 화면마다 목록을
            손으로 들고 있었더니 화면에 따라 열리는 것이 달랐다(2026-08-23). */}
        {overlays}
      </ErrorBoundary>
    );
  }

  // 에이전트는 역할·모델·스킬·실행 순서와 사람 확인 지점을 정하는 독립 제품공간이다.
  // 전체 메뉴의 관리 모달은 유지하되, 상단 핵심 메뉴에서는 공통 ProductShell 안에서 연다.
  if (!currentProjectId && space === 'agent') {
    return (
      <ErrorBoundary>
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <ProductShell module="agent"
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => setSpace('build')}
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', width: '100%' }}>
            <AgentMasterPanel page onClose={() => setSpace('enterprise')} />
          </main>
        </div>
        {overlays}
      </ErrorBoundary>
    );
  }

  // 지식은 모든 앱·에이전트가 참고할 근거를 다루는 독립 제품공간이다. 전체 메뉴에서 여는
  // 지식 허브 모달은 유지하되, 상단 핵심 메뉴는 공통 ProductShell 안에서 연다.
  if (!currentProjectId && space === 'knowledge') {
    return (
      <ErrorBoundary>
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <ProductShell module="knowledge"
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => setSpace('build')}
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', width: '100%' }}>
            <KnowledgeHubPanel page initialView={knowledgeInitialView}
              onClose={() => setSpace('enterprise')} />
          </main>
        </div>
        {overlays}
      </ErrorBoundary>
    );
  }

  // 결정·보고는 제품 수명주기의 독립 공간이다. 전체 메뉴의 협업 허브는 모달로 유지하지만,
  // 상단 핵심 메뉴는 ProductShell과 3열 작업면을 유지한다.
  if (!currentProjectId && space === 'report') {
    return (
      <ErrorBoundary>
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <ProductShell module="report"
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => openBuildStart('document_report')}
            primaryActionLabel="＋ 새 보고서"
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', width: '100%' }}>
            <CollaborationHub page initialView={collaborationInitialView}
              onClose={() => setSpace('enterprise')}
              generatedProjects={reportProjects as any}
              onOpenGeneratedProject={(id) => {
                setCurrentProject(id);
                setShowStudio(true);
              }}
              releaseOptions={releases.filter((r: any) => r.release_id).map((r: any) => ({
                id: r.release_id,
                label: r.display_name || r.project_name || '이름 미등록 앱',
              }))} />
          </main>
        </div>
        {overlays}
      </ErrorBoundary>
    );
  }

  // 시뮬레이션은 기준선·가정·결과를 함께 다루는 주요 제품 공간이다. 홈 위 대화상자가
  // 아니라 공통 ProductShell 아래의 독립 페이지로 유지한다.
  if (!currentProjectId && space === 'twin') {
    return (
      <ErrorBoundary>
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <ProductShell module="twin"
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => openBuildStart('hybrid_simulation')}
            primaryActionLabel="＋ 새 시뮬레이터"
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', width: '100%' }}>
            <ScenarioPanel page onClose={() => setSpace('enterprise')}
              generatedProjects={simulationProjects as any}
              onOpenGeneratedProject={(id) => setCurrentProject(id)} />
          </main>
        </div>
        {overlays}
      </ErrorBoundary>
    );
  }

  // 앱 운영은 앱 제작과 같은 제품 수명주기 화면이다. 홈 위에 뜨는 대화상자가 아니라
  // 동일한 ProductShell 아래의 독립 페이지로 유지한다.
  if (!currentProjectId && space === 'operate') {
    return (
      <ErrorBoundary>
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <ProductShell module="operate"
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => { setSpace('build'); openBuildStart('software_app'); }}
            primaryActionLabel="＋ 새 앱"
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
            </>} />
          <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', width: '100%' }}>
            <KitOperationsPanel page onOpenBuild={() => {
              setSpace('build');
              openBuildStart('software_app');
            }} onOpenSimulation={(instanceId, appId) => {
              setPathCalcInitialInstanceId(instanceId);
              setPathCalcInitialAppId(appId);
              setSpace('path');
            }} />
          </main>
        </div>
        {overlays}
      </ErrorBoundary>
    );
  }

  // ★ [B6] 업무 앱 직접 링크 — 서버가 확인해 준 뒤에만 시뮬레이션으로 넘긴다.
  //   확인 전에는 목록을 보여 주지 않는다. 조회 가능은 실행 승인이 아니므로 여기서 더
  //   하는 일은 없고, 확인되면 기존 「키트 운영 → 시뮬레이션」과 같은 자리로 넘어간다.
  if (kitAppGate && !showPathCalc) {
    return (
      <ErrorBoundary>
        {overlays}
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <div className="flex items-center gap-3 px-4 py-3 border-b afs-border">
            <button
              onClick={() => { setKitAppGate(null); setRouteRestored(true); setSpace('enterprise'); }}
              className="text-sm font-bold text-gray-100 hover:text-white bg-indigo-700 hover:bg-indigo-600 px-3 py-1.5 rounded transition-colors"
            >⌂ 경영 홈</button>
          </div>
          <main className="flex-1 min-h-0 overflow-auto p-6">
            <StudioKitAppEntryGate instanceId={kitAppGate.instanceId} appId={kitAppGate.appId}>
              {(entry) => (
                <KitAppEntryCommit entry={entry} onCommit={(instanceId, appId) => {
                  //: 업무앱도 instance/app 을 주소에 남긴다(결정서 §3).
                  setOpenedKitApp({ instanceId, appId });
                  setOpenedMega(null); setOpenedDraft(null);
                  setPathCalcInitialInstanceId(instanceId);
                  setPathCalcInitialAppId(appId);
                  setShowPathCalc(true);
                  setKitAppGate(null);
                  setRouteRestored(true);
                }} />
              )}
            </StudioKitAppEntryGate>
          </main>
        </div>
      </ErrorBoundary>
    );
  }

  // ★★★ [B6] 직접 링크 진입 — 서버 확인 전에는 목록도 Studio 도 보여 주지 않는다.
  //   확인 중·거절 표시는 `StudioProjectEntryGate` 가 맡고, 여기서는 그 화면에서
  //   빠져나갈 길(경영 홈·목록)만 함께 둔다. 확인되면 아래 기존 흐름으로 넘어간다.
  if ((entryGateId || draftGate) && !currentProjectId) {
    return (
      <ErrorBoundary>
        {overlays}
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 border-b afs-border">
            <button
              onClick={() => { closeEntryGate(); setSpace('enterprise'); }}
              className="text-sm font-bold text-gray-100 hover:text-white flex items-center gap-1 bg-indigo-700 hover:bg-indigo-600 px-3 py-1.5 rounded transition-colors"
              title="경영 홈으로 — 처음 화면으로 돌아갑니다"
            >
              ⌂ 경영 홈
            </button>
            <button
              onClick={() => { closeEntryGate(); setSpace('build'); }}
              className="text-sm font-bold text-gray-400 hover:text-gray-100 flex items-center gap-1 bg-gray-700 px-3 py-1.5 rounded transition-colors"
              title="앱 제작 목록으로 돌아갑니다"
            >
              ◀ 앱 제작
            </button>
            {/*: ★★★ [B6-CONTEXT · 검토 §3] **거절 화면에서도 «되돌아올» 수 있어야 한다.**
                 ⚠️ 종전에는 여기 칩이 없어, 권한 있는 범위로 돌아가려면 홈으로 나갔다가
                   다시 들어와야 했다. 주소는 대상을 지키고 있는데 사용자는 그 길을 잃는다.
                 ★ **새 전환 창을 만들지 않는다** — 셸·작업공간과 같은 칩, 같은 문
                   (`openContextSwitcher`)이다. 미저장 보호·주소 불일치 차단도 그대로 탄다. */}
            <div className="shrink-0">
              <OperatingContextChip company={shellCompanyName} scope={shellCtx.scopeLabel}
                entityMode={shellCtx.entityMode} onContext={openContextSwitcher} />
            </div>
          </div>
          <main className="flex-1 min-h-0 overflow-auto p-6">
            {entryGateId ? (
              <StudioProjectEntryGate projectId={entryGateId}
                childId={megaRequest?.childProjectId || ''} requireMega={megaRequest !== null}>
                {(entry) => (
                  <StudioEntryCommit entry={entry} onCommit={(id) => {
                    //: 메가로 들어왔으면 **부모/자식을 잃지 않는다**(결정서 §3).
                    setOpenedMega(megaRequest && entryGateId
                      ? { megaProjectId: entryGateId, childProjectId: megaRequest.childProjectId } : null);
                    setOpenedKitApp(null); setOpenedDraft(null);
                    setCurrentProject(id);
                    closeEntryGate();
                  }} />
                )}
              </StudioProjectEntryGate>
            ) : draftGate ? (
              /* ⚠️ 확인까지가 이번 범위다. 확인된 초안을 **여는 화면**(앱 제작 시작에
                 그 판본을 실어 넘기는 자리)은 아직 없다 — 없는 화면을 지어내지 않는다.
                 서버가 「볼 수 있다」고 한 사실만 보이고, 나머지는 인계한다. */
              <StudioDraftEntryGate draftId={draftGate.draftId}
                draftKind={draftGate.draftKind} revision={draftGate.revision}>
                {(entry) => (
                  <DraftOpenCommit entry={entry} onOpened={(deliverable) => {
                    //: 초안은 **종류·판본까지** 주소에 남는다.
                    setOpenedDraft(draftGate);
                    setOpenedMega(null); setOpenedKitApp(null);
                    setBuildStartType(deliverable);
                    setBuildStart(true);
                    closeEntryGate();
                  }} />
                )}
              </StudioDraftEntryGate>
            ) : null}
          </main>
        </div>
      </ErrorBoundary>
    );
  }

  if (!currentProjectId) {
    return (
      <ErrorBoundary>
        {overlays}
        <div className="afs-scope afs-page h-screen w-full flex flex-col overflow-hidden font-sans">
          {/* 앱 제작도 경영 홈과 같은 제품 셸을 쓴다. 화면마다 별도 머리 바를 만들면
              브랜드·회사 문맥·메뉴 명칭이 다시 갈라진다. */}
          <ProductShell module="factory"
            company={shellCompanyName}
            scope={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onNav={handleShellNav}
            onContext={openContextSwitcher}
            onAbout={() => setSpace('about')}
            onSettings={() => setOpenConsole(true)}
            onNewWork={() => openBuildStart('software_app')}
            primaryActionLabel="＋ 새 앱"
            right={<>
              <SessionBar onGoToOrg={() => setShowOrgChart(true)} openConsole={openConsole}
                onConsoleHandled={() => setOpenConsole(false)} />
              <GlobalNav primary={primaryNav} groups={navGroups} right={null} />
              <div className="relative shrink-0">
                <button onClick={() => setShowLogPopup(v => !v)} title="서버 연결 상태"
                  aria-label="서버 연결 상태"
                  className="flex items-center afs-bg-sunken afs-hover-raise transition-colors p-2 rounded-full border afs-border cursor-pointer">
                  <span className={`w-2.5 h-2.5 rounded-full shadow-[0_0_8px] ${isConnected ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500 shadow-red-500/50 animate-pulse'}`} />
                </button>
                {showLogPopup && <ServerLogPopup onClose={() => setShowLogPopup(false)} />}
              </div>
            </>} />

 <main style={{ flex: 1, minHeight: 0, overflow: 'hidden', width: '100%' }}>
          {/* ★★★ [설계 §5.2] `/build` 는 **목록면**이다 — 상단 「새 업무 만들기」 + 진행 상태
              필터, 본문은 진행 중/내 프로젝트/Mega/Releases/Archive.
              ⚠️ 종전에는 열자마자 «신규 프로젝트 개설» 폼이 본문을 차지했다(2026-07-28 AS-IS).
                목록이 먼저 보여야 「이미 있는 것을 여는」 흔한 일이 한 번에 되고, 만들기는
                결정이 필요한 별도 흐름이 된다. 생성 폼은 `buildStart` 오버레이로 옮겼다. */}
          <BuildPage
            projects={appProjects as any}
            releases={releases}
            companyName={shellCompanyName}
            scopeLabel={shellCtx.scopeLabel}
            entityMode={shellCtx.entityMode}
            onOpenProject={(id) => setCurrentProject(id)}
            onOpenRelease={(releaseId) => openRelease(releaseId)}
            onManageRelease={(r) => setAdminProgram({
              id: r.release_id, name: r.display_name || r.project_name || r.release_id,
            })}
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
      {/* ★★★ [사용자 결정 2026-08-23 「(나)로 진행」] **통제실은 어두운 작업면으로 유지하되
          토큰 체계 안에 넣는다.** `afs-workbench` 가 그 범위다 — `afs.css` 의 같은 이름 절이
          이 안에서만 회색 유틸리티를 다시 해석한다.
          ⚠️ `afs-scope` 를 붙이지 않는다. 그것은 **라이트** 표면 계열이라 여기 오면 배경과
            글자가 뒤집힌다(실측: 뿌리에 `afs-product-shell` 을 붙였더니 결함 26 → 28건). */}
      <div className="afs-workbench h-screen w-screen bg-gray-950 text-gray-100 flex flex-col font-sans overflow-hidden">
        {/*: ⚠️ [B6-CONTEXT] 좁은 화면에서 좌/우 묶음이 **서로 덮였다**(실측: 문맥 칩이
             다른 버튼 아래로 들어가 눌리지 않았다). 줄바꿈을 허용해 «가려지는 대신 내려가게»
             한다 — 상단 바가 한 줄이어야 할 이유는 없다. */}
        <header className="min-h-14 bg-gray-950/95 backdrop-blur border-b border-gray-700 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-2 shrink-0 z-20">
          <div className="flex items-center gap-3 min-w-0">
            {/* ★★★ [2026-08-25 사용자 지적] 「각 화면에서 홈으로 돌아가는 버튼이 없다」.
                ⚠️⚠️ 통제실에는 «런처 복귀» 만 있었다. 그것은 Software Factory 로 가는
                  것이지 **경영 홈이 아니다** — 홈까지 가려면 두 번 눌러야 했고, 그 사실을
                  아는 사람만 돌아갈 수 있었다. 설계 §3.4 는 「공통 상단 바에 `경영 홈으로
                  돌아가기` 를 **항상** 표시한다」고 못박았다.
                ★ 둘을 **함께** 둔다. 「한 칸 뒤로」와 「처음으로」는 다른 행동이다. */}
            <button
              onClick={() => { setCurrentProject(null); closeEntryGate(); setSpace('enterprise'); }}
              className="text-sm font-bold text-gray-100 hover:text-white flex items-center gap-1 bg-indigo-700 hover:bg-indigo-600 px-3 py-1.5 rounded transition-colors"
              title="경영 홈으로 — 처음 화면으로 돌아갑니다"
            >
              ⌂ 경영 홈
            </button>
            <button 
              onClick={() => { setCurrentProject(null); closeEntryGate(); setSpace(workbenchParent); }}
              className="text-sm font-bold text-gray-400 hover:text-gray-100 flex items-center gap-1 bg-gray-700 px-3 py-1.5 rounded transition-colors"
              title={`${workbenchParentLabel} 목록으로 돌아갑니다`}
            >
              ◀ {workbenchParentLabel}
            </button>
            <h1 className="text-lg font-bold tracking-tight text-gray-100 flex items-center gap-2 truncate max-w-lg">
              <span className="text-blue-300 truncate">{currentProject?.name || currentProjectId}</span>
              <span className="text-gray-400 text-sm font-semibold shrink-0">· {workbenchLabel}</span>
            </h1>
            {/*: ★★★ [B6-CONTEXT · 결정 1] **작업공간에도 회사 문맥이 보이고 바뀐다.**
                 ⚠️ 종전에는 대상을 열면 칩이 사라져 「지금 어느 회사·범위인지」 알 수도,
                   바꿀 수도 없었다. 실측으로 확인한 결함이다(2026-09-18).
                 ★ 셸과 **같은 컴포넌트·같은 상태 출처·같은 접근 이름**을 쓴다. 전환 창도
                   기존 것 하나다. 미저장 보호는 `openContextSwitcher` 가 맡는다. */}
            {/*: ⚠️ 이 줄은 `min-w-0` 인 flex 다 — 그대로 두면 칩이 22px 로 **찌그러져
                 다른 버튼에 덮인다**(실측). 칩은 제 크기를 지킨다. */}
            <div className="shrink-0">
              <OperatingContextChip company={shellCompanyName} scope={shellCtx.scopeLabel}
                entityMode={shellCtx.entityMode} onContext={openContextSwitcher} />
            </div>
          </div>
          <div className="relative flex items-center justify-end gap-2 overflow-x-auto shrink-0">
            <button
              onClick={() => setShowAdvisor(true)}
              className="text-xs font-bold text-indigo-200 bg-indigo-900/50 hover:bg-indigo-800/70 border border-indigo-700/60 px-3 py-1.5 rounded-lg transition-colors"
              title="업무·데이터 설계 상담 — 필요한 데이터와 추진 순서를 선택형 대화로 정합니다"
            >
              🧭 기획·설계 상담
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
              title="새 제작 화면 — 전체 제작 단계와 작업 실행 구조를 실제 상태로 봅니다. 기존 작업 화면은 그대로 유지됩니다."
            >
              🏗 새 제작 화면
            </button>
            <button
              onClick={() => setShowShadow(true)}
              className="text-xs font-bold text-slate-200 bg-slate-800/70 hover:bg-slate-700/70 border border-slate-600/60 px-3 py-1.5 rounded-lg transition-colors"
              title="후보 병렬 검증 · 제한적 승격(§7.3)"
            >
              🧪 병렬 검증
            </button>
            <button
              onClick={() => setShowWorkspace(true)}
              className="text-xs font-bold text-slate-200 bg-slate-800/70 hover:bg-slate-700/70 border border-slate-600/60 px-3 py-1.5 rounded-lg transition-colors"
              title="공유·복제·전사 승격 게이트(§9.3)"
            >
              🏢 공유·승격
            </button>
            <button 
              onClick={() => setShowLogPopup(v => !v)}
              title="서버 로그 보기"
              className="flex items-center gap-3 hover:bg-white/10 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
            >
              <span className="text-xs text-gray-400 font-medium">서버 연결</span>
              <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
            </button>
            {showLogPopup && <ServerLogPopup onClose={() => setShowLogPopup(false)} />}
          </div>
        </header>

        {overlays}
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
  const [state, setState] = useState<'checking' | 'in' | 'out' | 'offline'>('checking');
  const [offline, setOffline] = useState('');

  const check = useCallback(async () => {
    setOffline('');
    if (!getSessionToken()) { setState('out'); return; }
    setState('checking');
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
        headers: { 'X-Session-Token': getSessionToken() },
      });
      if (r.ok) {
        const payload = await r.json();
        const sessionTenant = String(payload?.data?.tenant_id || '').trim();
        const selected = getEnterpriseContext();
        if (sessionTenant && selected.tenantId !== sessionTenant) {
          // 인증 게이트가 세션의 회사 tenant를 먼저 적용해야, 바로 뒤에 마운트되는 모든
          // 회사·조직 조회가 이전 브라우저 tenant 헤더로 나가지 않는다. 회사가 바뀌면
          // 이전 회사의 조직 범위도 함께 비운다 — 그 둘을 섞는 것은 유효한 문맥이 아니다.
          setEnterpriseContext({ tenantId: sessionTenant, scopeNodeId: '' });
        }
        setState('in'); return;
      }
      // 401/403 = 세션이 죽었다. 토큰을 버려야 다음 새로고침에서 또 묻지 않는다.
      setSessionToken(''); setActingUser('');
      setState('out');
    } catch {
      setOffline('현재 서비스에 연결할 수 없습니다. 저장된 로그인 정보는 유지됩니다. 잠시 후 다시 시도하거나 시스템 관리자에게 문의하십시오.');
      setState('offline');
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
  if (state === 'offline') {
    return (
      <div className="afs-scope afs-page"
        style={{ minHeight: '100dvh', width: '100%', display: 'grid', placeItems: 'center', padding: 24 }}>
        <section aria-label="서비스 연결 장애"
          style={{
            width: 'min(520px, 100%)', display: 'flex', flexDirection: 'column', gap: 18,
            padding: '34px 36px', border: '1px solid var(--surface-border)', borderRadius: 12,
            background: 'var(--surface-card)', boxShadow: 'var(--surface-shadow)', textAlign: 'center',
          }}>
          <img src="/brand/laxs-logo-primary-on-white-v5.png" alt="LAXS"
            style={{ display: 'block', width: 250, maxWidth: '82%', height: 'auto', margin: '0 auto 4px' }} />
          <Banner tone="warn" title="서비스 연결을 확인할 수 없습니다">{offline}</Banner>
          <p className="afs-muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.6 }}>
            비밀번호를 다시 입력할 필요가 없습니다. 연결이 복구되면 같은 업무 문맥으로 돌아갑니다.
          </p>
          <button className="primary-button" type="button" onClick={check}
            style={{ minHeight: 44, fontSize: 15 }}>
            다시 연결하기
          </button>
        </section>
      </div>
    );
  }
  if (state === 'out') {
    return (
      <ErrorBoundary>
        <LoginPage onLoggedIn={() => {
          // 새로고침과 동일한 인증·회사 보정을 먼저 끝낸다. 옛 회사 문맥으로
          // 직접 링크를 소비하면 뒤이은 문맥 보정에서 그 조회가 취소된다.
          void check();
          // 초기 비밀번호 상태는 로그인 뒤 상단 SessionBar가 지속적으로 보여 주고 바로 옆
          // 「환경설정 · 관리자」에서 변경한다. 네이티브 alert는 첫 화면 전체를 막으므로 쓰지 않는다.
        }} />
      </ErrorBoundary>
    );
  }
  return <AppShell />;
}
