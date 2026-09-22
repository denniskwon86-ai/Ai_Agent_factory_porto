import { create } from 'zustand';
import {
  startExistingTask, pauseSprint as requestPauseSprint, stopSprint as requestStopSprint,
  requestSelfHealing, saveProjectRelease, rejectedCommand, isProjectCommandPending,
} from '../factory/sprintActions';
import type { ExistingTaskInput, SprintResult, HealingResult, ReleaseResult } from '../factory/sprintActions';

export interface ProjectState {
  studio_execution_state?: { task_id: string; running: boolean;
    pause: { status: string; resumable: boolean; reason_code: string } };
  project_name: string;
  template_id?: string;
  initial_idea?: string;
  factory_mode: string;
  build_status: string;
  current_sprint_task_id: string;
  needs_revision: boolean;
  human_feedback_queue: any[];
  developer_retry_count: number;
  rfp_summary: string;
  prd_summary: string;
  architecture_summary: string;
  tech_spec_summary: string;
  frontend_code_summary: string;
  backend_code_summary: string;
  code_review_report_summary: string;
  qa_report_summary: string;
  qa_verdict?: string;  // "" | "PASS" | "FAIL" — QA(수행사 통합검수) 판정
  supervisor_report_summary?: string;  // 고객사 대리인 최종 수용검수 리포트
  supervisor_verdict?: string;  // "" | "PASS" | "REJECT" — 최종 수용검수(완료/배포 게이트)
  user_manual_summary: string;
  build_error_log?: string;
  // 토론·합의 / 단계별 성공기준 / Supervisor (V5.1 관측성)
  current_stage?: string;
  stage_scores?: Record<string, number>;
  debate_rounds_used?: Record<string, number>;
  supervisor_feedback?: string;
  criteria_log?: any[];
  artifacts?: Record<string, string>;
  terminal_status?: string;
  terminal_reason?: string;
  // 메가 프로젝트 / 시뮬레이션 확장 변수
  is_mega_project?: boolean;
  sub_projects_map?: Record<string, string>;
  master_data?: string;
  sim_cycle_count?: number;
}

// 워크플로우 템플릿(범용 플랫폼 Copy 모델) — 목록 요약 및 상세 레지스트리
export interface WorkflowTemplate {
  id: string;
  name?: string;
  description?: string;
  agent_count?: number;
  builtin?: boolean;
}

export interface OutputFormat {
  id: string;
  name: string;
  description: string;
  prompt_injection: string;
  view_type?: 'react_app' | 'markdown' | 'json' | 'slide' | 'mermaid';
}

interface FactoryStore {
  state: ProjectState | null;
  logs: any[];
  isConnected: boolean;
  wbsData: any;
  isWbsError: boolean;
  wbsErrorCount: number;
  completed_agents: string[];
  /** ★ [CR-W03-2C] 마지막 «정본 저장» 실패. 계산 완료와 저장 완료는 다른 사건이다.
   *  값이 있으면 화면이 보고 있는 판본이 서버 정본이 아닐 수 있다는 뜻이다. */
  lastStateSaveError: { node: string; error: string; stale: boolean } | null;
  currentActivity: any | null;
  // 빌드 자가복구(3회) 소진 등 스프린트 최종 실패 정보 - ControlPanel 실패 배너/재시도 UI 용
  lastSprintFailure: { taskId: string; error: string; detail?: string } | null;
  clearSprintFailure: () => void;
  isSuspendedQuota: boolean;
  suspendedTaskId: string | null;  // 쿼터 회복 재개(resume-quota) 대상 태스크
  clearSuspendedQuota: () => void;
  supervisorFeed: any[];
  releases: any[];
  viewingRelease: any | null;
  /** [B6] 결과물 조회의 진행·실패. `viewingRelease` 가 null 인 것만으로는
   *  「아직 안 열었다」와 「열려다 실패했다」를 구분할 수 없다. */
  releaseLoad: 'idle' | 'loading' | 'failed' | 'forbidden';
  releaseError: string;
  agentRegistry: any | null;
  /** [UIUX-AUDIT-30 §5] 로드 실패 사유. 비어 있으면 «아직 안 왔다», 차 있으면 «못 가져왔다». */
  agentRegistryError: string;
  /** 저장·복사·삭제·초기화가 실패한 이유. ⚠️ 조회 실패(`agentRegistryError`)와 섞지 않는다 —
   *  «못 읽었다»와 «못 바꿨다»는 사용자가 해야 할 다음 행동이 다르다. */
  agentActionError: string;
  clearAgentActionError: () => void;
  showAgentPanel: boolean;
  // 워크플로우 템플릿(T2-c)
  templates: WorkflowTemplate[];
  selectedTemplateId: string;   // 신규 프로젝트 생성 시 선택된 템플릿
  editingTemplateId: string;    // 마스터 제어판이 현재 편집 중인 템플릿
  // 출력 포맷 마스터 (Two-Track Harness)
  formats: OutputFormat[];
  /** 서식 목록을 **못 읽었을 때** 그 이유. 빈 문자열이면 조회에 성공한 것이다.
   *  ⚠️ `formats.length === 0` 만 보면 «없다» 와 «못 읽었다» 가 같은 화면이 된다. */
  formatsError: string;
  selectedFormatId: string;
  showFormatPanel: boolean;
  projects: { id: string, name: string, initial_idea?: string, is_mega_project?: boolean, parent_project_id?: string, template_id?: string, total_tasks?: number, completed_tasks?: number }[];
  //: ★★★ [G1-C3] 「몇 건 보이는가」만으로는 부족하다. 조회 실패·권한 없음·문맥 밖·정말 0건이
  //:   화면에서 **서로 다른 상태**여야 한다(설계 §6.4 「조회 실패를 0으로 대체하지 않는다」).
  projectsLoad: 'loading' | 'ok' | 'failed' | 'forbidden';
  projectsError: string;
  //: 지금 어느 회사·조직·실행 모드로 보고 있는가. 표시하지 못하면 사용자는 자기가 보는
  //: 숫자가 어느 문맥의 것인지 알 수 없다(설계 §11 공통 체크리스트).
  viewingContext: { tenant_id?: string; scope_node_id?: string; entity_mode?: string } | null;
  //: ⚠️ `null` 은 «서버가 알려 주지 않았다» 이고 `0` 은 «가려진 것이 없다» 다. 뭉개지 말 것.
  contextBlocked: number | null;
  contextNeedsAttention: number | null;
  contextBlockedReasons: Record<string, number> | null;
  currentProjectId: string | null;
  healingRetryCount: number;
  activeSprintId: string | null;
  hotlTaskId: string | null;
  currentTemplateData: any | null;
  setActiveSprintId: (id: string | null) => void;
  setCurrentProject: (id: string | null) => void;
  fetchProjects: () => Promise<void>;
  createProject: (name: string, templateId?: string, knowledgePackIds?: string[], masterDomains?: string[], mcpLiveGrounding?: boolean, kitInstanceId?: string) => Promise<string | null>;
  createMegaProject: (name: string, templateId?: string) => Promise<string | null>;
  copyProject: (id: string, newName: string) => Promise<string | null>;
  /** 프로젝트 삭제. 기본은 **표시 삭제**(데이터는 남는다), `purge=true` 는 실제 삭제(관리자만). */
  deleteProject: (id: string, purge?: boolean) => Promise<boolean>;
  /** 표시 삭제 되돌리기. */
  restoreProject: (id: string) => Promise<boolean>;
  /** 삭제·되돌리기가 **왜** 안 됐는지. 빈 문자열이면 문제 없음.
   *  ⚠️ `false` 만 돌려주면 화면은 「실패」라고만 말할 수 있고, 사용자는 권한 문제인지
   *  공유된 프로젝트라서인지 서버 문제인지 구분할 수 없다 — 셋은 할 일이 다르다. */
  projectActionError: string;
  connectSSE: () => void | Promise<void>;
  fetchWBS: (force?: boolean) => Promise<void>;
  fetchLatestState: () => Promise<void>;
  checkHotl: () => Promise<void>;
  fetchFeed: () => Promise<void>;
  fetchReleases: () => Promise<void>;
  /** 성공/실패와 **이유**를 함께 돌려준다 — `null` 하나로 뭉개면 화면이 원인을 지어낸다. */
  saveRelease: (projectId: string) =>
    Promise<ReleaseResult>;
  viewRelease: (releaseId: string) => Promise<void>;
  closeRelease: () => void;
  deleteRelease: (releaseId: string) => Promise<void>;
  fetchAgentRegistry: () => Promise<void>;
  saveAgentRegistry: (reg: any) => Promise<boolean>;
  resetAgentRegistry: () => Promise<void>;
  restoreAgentRegistry: () => Promise<boolean>;
  openAgentPanel: () => void;
  closeAgentPanel: () => void;
  // 템플릿 관리(T2-c)
  fetchTemplates: () => Promise<void>;
  setSelectedTemplate: (id: string) => void;
  /** 편집 템플릿을 읽어 실제 레지스트리까지 결속했을 때만 true. 실패 시 이전 레지스트리를 지운다. */
  selectEditingTemplate: (id: string) => Promise<boolean>;
  saveTemplateRegistry: (id: string, reg: any) => Promise<boolean>;
  copyTemplate: (srcId: string, newId: string, newName?: string) => Promise<boolean>;
  deleteTemplate: (id: string) => Promise<boolean>;
  // 출력 포맷 관리
  fetchFormats: () => Promise<void>;
  setSelectedFormat: (id: string) => void;
  saveFormat: (fmt: OutputFormat) => Promise<boolean>;
  deleteFormat: (id: string) => Promise<boolean>;
  openFormatPanel: () => void;
  closeFormatPanel: () => void;
  clearSprintData: () => void;
  triggerSelfHealing: (errorMsg: string) => Promise<HealingResult>;
  startSprint: (projectId: string, taskId: string, input?: ExistingTaskInput, feedback?: string) => Promise<SprintResult>;
  pauseSprint: (projectId: string, taskId: string) => Promise<SprintResult>;
  stopSprint: (projectId: string, taskId: string) => Promise<SprintResult>;
}

//: ★★★ [WEB-1] **API 주소는 `lib/api.ts` 한 곳에서만 정한다.**
//: ⚠️ 각자 `|| 'http://127.0.0.1:8080'` 을 선언하면 same-origin 빌드가 성립하지
//:   않는다 — 한 곳을 고쳐도 나머지가 개발 주소를 번들에 박고, 배포한 화면이
//:   방문자의 자기 PC 를 부른다.
//: ⚠️ `export … from` 만 쓰면 **이 파일 안에서는 그 이름을 못 쓴다.** 재수출과
//:   지역 사용은 다른 일이다 — 둘 다 필요하다.
import { API_BASE_URL } from '../lib/api';
export { API_BASE_URL };

// [CL-4] 사용자 식별을 쿼리로 싣는 공용 헬퍼. 여기서 다시 구현하지 않는다.
//: [P0-1C] `apiUrl` 은 더 이상 쓰지 않는다 — 마지막 사용처였던 SSE 가 1회용 접속표로
//  옮겨 갔다(P0-1B). 남겨 두면 «쿼리로 신원을 싣는 방법이 아직 있다» 로 읽힌다.
import { getActingUser, getEnterpriseContext, getSessionToken } from '../lib/api';

// 단일 SSE 연결만 유지 — StrictMode 이중 마운트/자동 재연결 시 중복 연결로 이벤트가 2번 수신되는 것 방지
let _sseConn: EventSource | null = null;
/** ★★ [P0-1B 보정] SSE 연결 세대.
 *
 * 티켓 발급이 **비동기**가 되면서, 표를 기다리는 사이에 다른 `connectSSE()` 가 들어올 수 있다
 * (사용자 전환 · 재연결 타이머 · 수동 연결이 겹친다). 그러면 두 호출이 각각 표를 받아 각각
 * `EventSource` 를 만들고, **앞의 것이 `_sseConn` 에서 밀려나 추적되지 않는 고아 연결**이
 * 된다 — 닫히지도 않고 이벤트는 계속 받는다.
 *
 * 그래서 시도마다 번호를 매기고, 표를 받아 온 뒤 **자기가 아직 최신인지** 확인한다. */
let _sseGeneration = 0;
let _sseReconnectTimer: ReturnType<typeof setTimeout> | null = null;

/** ★ [G1-C1.1] 마지막으로 받아 온 상태 판본. `NODE_COMPLETED` 가 같은 판본을 다시 알리면
 *  조회하지 않는다 — 서버가 상태 전체를 밀어 주지 않게 되면서, 그 대신 화면이 가져와야
 *  하는데 매 노드마다 전부 다시 받으면 종전보다 느려진다.
 *  ⚠️ 프로젝트를 바꾸면 반드시 비운다. 안 비우면 새 프로젝트의 첫 판본이 «이미 가진 것» 으로
 *    읽혀 **첫 갱신을 통째로 건너뛴다.** */
let _lastStateVersion = '';

// 프로젝트 A→B→A와 같은 값으로 돌아온 경우도 이전 요청을 재사용하지 않는다.
let _projectGeneration = 0;
let _identityGeneration = 0;
const _readGeneration = { wbs: 0, state: 0, hotl: 0, feed: 0, releases: 0 };
let _healingInFlight: (() => boolean) | null = null;
// 릴리스는 프로젝트 선택과 별개다. 닫기·재조회·문맥 전환마다 표시 요청을 무효화한다.
let _releaseGeneration = 0;
let _releaseAbort: AbortController | null = null;
function invalidateReleaseRequest() {
  _releaseGeneration += 1;
  _releaseAbort?.abort();
  _releaseAbort = null;
}
function releaseIdentity(): string {
  const c = getEnterpriseContext();
  return JSON.stringify([getSessionToken(), getActingUser(), c.tenantId, c.scopeNodeId, c.entityMode]);
}
if (typeof window !== 'undefined') {
  const invalidateIdentity = () => {
    _identityGeneration += 1;
    // 이벤트는 store 초기화 뒤 발생한다. 이전 사용자의 원문도 즉시 제거하며 재조회하지 않는다.
    useFactoryStore.getState().closeRelease();
  };
  window.addEventListener('factory:session-changed', invalidateIdentity);
  window.addEventListener('factory:acting-user-changed', invalidateIdentity);
  window.addEventListener('factory:enterprise-context-changed', invalidateIdentity);
}

/** 표시 수명 검사이지 권한 판정이 아니다. 서버 PDP는 모든 요청에서 그대로 수행된다. */
function currentProjectRequest(
  get: () => FactoryStore, projectId: string | null,
  reader?: keyof typeof _readGeneration,
): () => boolean {
  const projectGeneration = _projectGeneration;
  const identityGeneration = _identityGeneration;
  const session = getSessionToken();
  const actor = getActingUser();
  const context = getEnterpriseContext();
  const contextValues = [context.tenantId, context.scopeNodeId, context.entityMode];
  const readGeneration = reader ? ++_readGeneration[reader] : 0;
  return () => {
    const currentContext = getEnterpriseContext();
    return get().currentProjectId === projectId && _projectGeneration === projectGeneration
      && _identityGeneration === identityGeneration && getSessionToken() === session
      && getActingUser() === actor && currentContext === context
      && currentContext.tenantId === contextValues[0] && currentContext.scopeNodeId === contextValues[1]
      && currentContext.entityMode === contextValues[2]
      && (!reader || _readGeneration[reader] === readGeneration);
  };
}

function refreshExecution(get: () => FactoryStore) {
  // 쓰기 재전송 없음. 조회 실패가 원래 명령의 접수/거절 결과를 덮지 않는다.
  void Promise.allSettled([get().fetchLatestState(), get().fetchWBS(true), get().checkHotl()]);
}

async function currentSprintCommand(
  get: () => FactoryStore, projectId: string, send: () => Promise<SprintResult>,
): Promise<SprintResult> {
  if (!projectId || get().currentProjectId !== projectId) {
    return rejectedCommand('현재 선택한 프로젝트의 작업만 요청할 수 있습니다.', 'CURRENT_PROJECT_REQUIRED');
  }
  const isCurrent = currentProjectRequest(get, projectId);
  const result = await send();
  if (!isCurrent()) return { ok: false, outcome: 'UNKNOWN', status: result.status,
    requestId: result.requestId,
    reasonCode: 'CONTEXT_CHANGED',
    message: '요청 중 프로젝트 또는 사용자 문맥이 변경되었습니다. 원래 프로젝트에서 결과를 확인하십시오.' };
  if (result.outcome === 'ACCEPTED' || result.outcome === 'CONFIRMED' || result.outcome === 'UNKNOWN') refreshExecution(get);
  // 접수 응답으로 active/HOTL/실패 근거를 초기화하지 않는다. 실제 이벤트/조회가 담당한다.
  return result;
}

export const useFactoryStore = create<FactoryStore>()((set, get) => ({
  state: null,
  logs: [],
  isConnected: false,
  wbsData: null,
  isWbsError: false,
  wbsErrorCount: 0,
  completed_agents: [],
  lastStateSaveError: null,
  currentActivity: null,
  lastSprintFailure: null,
  isSuspendedQuota: false,
  suspendedTaskId: null,
  supervisorFeed: [],
  releases: [],
  viewingRelease: null,
  releaseLoad: 'idle',
  releaseError: '',
  agentRegistry: null,
  agentRegistryError: '',
  agentActionError: '',
  showAgentPanel: false,
  templates: [],
  selectedTemplateId: 'default',
  editingTemplateId: 'default',
  formats: [],
  formatsError: '',
  projectActionError: '',
  selectedFormatId: 'default',
  showFormatPanel: false,
  projects: [],
  projectsLoad: 'loading',
  projectsError: '',
  viewingContext: null,
  contextBlocked: null,
  contextNeedsAttention: null,
  contextBlockedReasons: null,
  currentProjectId: null,
  healingRetryCount: 0,
  activeSprintId: null,
  hotlTaskId: null,
  currentTemplateData: null,

  setActiveSprintId: (id) => set({ activeSprintId: id }),

  setCurrentProject: (id) => {
    _projectGeneration += 1;
    //: ⚠️ [G1-C1.1] 상태 판본을 **반드시 비운다.** 남겨 두면 새 프로젝트의 첫
    //   `NODE_COMPLETED` 판본이 «이미 가진 것» 으로 읽혀 첫 갱신을 통째로 건너뛴다.
    _lastStateVersion = '';
    set({
      currentProjectId: id, state: null, wbsData: null, logs: [],
      isWbsError: false, wbsErrorCount: 0, isSuspendedQuota: false, suspendedTaskId: null,
      completed_agents: [], currentActivity: null, lastSprintFailure: null, supervisorFeed: [], healingRetryCount: 0, activeSprintId: null, hotlTaskId: null, currentTemplateData: null,
      // ⚠️ [10.2-C] 프로젝트를 바꾸면 앞 프로젝트의 저장 실패 안내도 내린다 —
      //   남겨 두면 엉뚱한 프로젝트의 경고로 읽힌다.
      lastStateSaveError: null
    });
    if (id) {
      get().fetchWBS();
      get().fetchLatestState();
      get().checkHotl();
      get().fetchFeed();
    }
  },

  fetchProjects: async () => {
    // ★★★ [G1-C3] 서버는 이제 「무엇이 보이는가」와 **「왜 안 보이는가」**를 함께 준다.
    //   봉투를 버리면 화면은 사라진 자료를 «0건» 으로 그리고, 그것이 이 배선이 막으려던
    //   상태 그대로다(실측: 관리자에게 59건이 실행 문맥 격리로 빠진다).
    // ⚠️ 종전에는 실패도 `console.error` 로 끝나 **조회 실패와 «프로젝트 없음» 이 같은 화면**
    //   이었다. 트랙 F 가 8개 화면에서 고친 것과 같은 유형이다.
    set({ projectsLoad: 'loading', projectsError: '' });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects`);
      if (!res.ok) {
        let msg = `목록을 불러오지 못했습니다 (HTTP ${res.status}).`;
        try { const r = await res.json(); if (r?.detail) msg = String(r.detail); } catch { /* noop */ }
        set({ projectsLoad: res.status === 401 || res.status === 403 ? 'forbidden' : 'failed',
              projectsError: msg });
        return;
      }
      const result = await res.json();
      if (result.status !== "success") {
        set({ projectsLoad: 'failed', projectsError: '서버가 성공을 알리지 않았습니다.' });
        return;
      }
      set({
        projects: result.data,
        projectsLoad: 'ok',
        projectsError: '',
        viewingContext: result.viewing_context ?? null,
        // ⚠️ `?? null` 이다. `?? 0` 으로 두면 **옛 서버(값을 안 주는)** 와 «가려진 것이 없다» 가
        //   구분되지 않는다 — 화면이 「없음」이라고 단정하게 된다.
        contextBlocked: result.context_blocked_count ?? null,
        contextNeedsAttention: result.context_needs_attention ?? null,
        contextBlockedReasons: result.context_blocked_reasons ?? null,
      });
    } catch (error) {
      console.error("프로젝트 목록 로드 실패:", error);
      set({ projectsLoad: 'failed',
            projectsError: '서버에 연결하지 못했습니다. 백엔드가 떠 있는지 확인하십시오.' });
    }
  },

  createProject: async (name: string, templateId?: string, knowledgePackIds?: string[], masterDomains?: string[], mcpLiveGrounding?: boolean, kitInstanceId?: string) => {
    try {

      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: name,
          template_id: templateId || get().selectedTemplateId || 'default',
          knowledge_pack_ids: knowledgePackIds || [],
          master_domains: masterDomains || [],
          mcp_live_grounding: mcpLiveGrounding || false,
          kit_instance_id: kitInstanceId || ''
        })
      });
      if (res.ok) {
        const created = await res.json();
        await get().fetchProjects();
        return String(created?.project_id || '') || null;
      }
      // 백엔드 검증 실패(404 미존재 템플릿 / 400 형식 / 409 중복)는 사유를 표면화
      let msg = "프로젝트 생성에 실패했습니다. (중복된 ID일 수 있습니다)";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return null;
    } catch (error) {
      console.error("프로젝트 생성 실패:", error);
      return null;
    }
  },

  createMegaProject: async (name: string, templateId?: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects/mega`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          mega_project_name: name,
          template_id: templateId || get().selectedTemplateId || 'manufacturing-production'
        })
      });
      if (res.ok) {
        const created = await res.json();
        await get().fetchProjects();
        return String(created?.mega_project_id || '') || null;
      }
      let msg = "메가 프로젝트 생성에 실패했습니다. (중복된 ID일 수 있습니다)";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return null;
    } catch (error) {
      console.error("메가 프로젝트 생성 실패:", error);
      return null;
    }
  },

  startSprint: (projectId, taskId, input, feedback) =>
    currentSprintCommand(get, projectId, () => startExistingTask(projectId, taskId, input, feedback)),

  pauseSprint: (projectId, taskId) =>
    currentSprintCommand(get, projectId, () => requestPauseSprint(projectId, taskId)),

  stopSprint: (projectId, taskId) =>
    currentSprintCommand(get, projectId, () => requestStopSprint(projectId, taskId)),

  copyProject: async (id: string, newName: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects/${id}/copy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_project_name: newName })
      });
      if (res.ok) {
        const created = await res.json();
        await get().fetchProjects();
        return String(created?.new_project_id || '') || null;
      }
      let msg = "시나리오 복제에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return null;
    } catch (error) {
      console.error("프로젝트 복제 실패:", error);
      return null;
    }
  },

  // 🗑️ 프로젝트 삭제 (사용자 결정 2026-08-07)
  //
  // ★ 기본은 **표시 삭제**다 — 서버가 `project_meta.json` 에 표시만 남기고 파일은 지우지
  //   않는다. 실제 삭제(`purge=true`)는 관리자만 할 수 있다.
  // ⚠️ 종전에는 `res.ok` 가 아니면 `false` 만 돌려주고 **이유를 버렸다.** 그러면 화면은
  //   「삭제 실패」라고만 말할 수 있고, 사용자는 «권한이 없어서» 인지 «공유된 프로젝트라서»
  //   인지 «서버가 죽어서» 인지 알 수 없다 — 셋은 해야 할 일이 완전히 다르다.
  deleteProject: async (id: string, purge = false) => {
    try {
      const q = purge ? '?purge=true' : '';
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects/${id}${q}`, {
        method: 'DELETE',
      });
      const body = await res.json().catch(() => ({} as any));
      if (res.ok) {
        set({ projectActionError: '' });
        await get().fetchProjects();
        if (get().currentProjectId === id) {
          // 삭제된 프로젝트의 state가 스토어에 남아 다른 화면(릴리스 보기 등)에 노출되지 않도록 함께 비운다
          set({ currentProjectId: null, state: null, wbsData: null });
        }
        return true;
      }
      // 서버 문구를 그대로 보여 준다 — 화면이 지어내면 서버 규칙과 갈라진다.
      set({ projectActionError: body?.detail
        || (res.status === 401 ? '삭제하려면 우측 상단에서 사용자를 지정하십시오.'
          : `삭제하지 못했습니다 (${res.status}).`) });
      return false;
    } catch (error) {
      console.error("프로젝트 삭제 실패:", error);
      set({ projectActionError: '서버에 연결하지 못해 삭제하지 못했습니다.' });
      return false;
    }
  },

  /** 표시 삭제를 되돌린다. 데이터를 남겨 둔 이유가 이것이다. */
  restoreProject: async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects/${id}/restore`,
        { method: 'POST' });
      const body = await res.json().catch(() => ({} as any));
      if (res.ok) {
        set({ projectActionError: '' });
        await get().fetchProjects();
        return true;
      }
      set({ projectActionError: body?.detail || `되돌리지 못했습니다 (${res.status}).` });
      return false;
    } catch (error) {
      console.error("프로젝트 되돌리기 실패:", error);
      set({ projectActionError: '서버에 연결하지 못해 되돌리지 못했습니다.' });
      return false;
    }
  },

  checkHotl: async () => {
    const pid = get().currentProjectId;
    if (!pid) return;
    const isCurrent = currentProjectRequest(get, pid, 'hotl');
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${pid}/hotl/check`);
      if (res.ok) {
        const r = await res.json();
        // 전환 중 늦게 도착한 '이전 프로젝트' 응답이 새 프로젝트에 HOTL 대기를 주입하지 않도록 재검증
        if (!isCurrent()) return;
        if (r.hotl_task_id) {
          set((prev) => ({
            hotlTaskId: r.hotl_task_id,
            activeSprintId: null,
            state: { ...(prev.state || {}), needs_revision: true, current_sprint_task_id: r.hotl_task_id } as ProjectState,
          }));
        }
      }
    } catch (error) {
      console.error("HOTL 상태 확인 실패:", error);
    }
  },

  fetchFeed: async () => {
    const pid = get().currentProjectId;
    if (!pid) return;
    const isCurrent = currentProjectRequest(get, pid, 'feed');
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${pid}/feed`);
      if (res.ok) {
        const r = await res.json();
        if (!isCurrent()) return;
        if (Array.isArray(r.data)) set({ supervisorFeed: r.data.slice(-200) });
      }
    } catch (error) {
      console.error("슈퍼바이저 피드 로드 실패:", error);
    }
  },

  fetchReleases: async () => {
    const isCurrent = currentProjectRequest(get, get().currentProjectId, 'releases');
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/library/list`);
      if (res.ok) {
        const r = await res.json();
        if (isCurrent()) set({ releases: Array.isArray(r.data) ? r.data : [] });
      }
    } catch (error) {
      console.error("라이브러리 목록 로드 실패:", error);
    }
  },

  /** ★★ [2026-08-07 오프라인 검증] **실패 이유를 돌려준다.**
   *
   *  종전에는 네트워크 오류·403·409·500 을 전부 `null` 하나로 뭉갰고, 화면은 그것을 받아
   *  「산출물이 아직 준비되지 않았거나 권한이 없습니다」라는 **그럴듯한 원인을 지어냈다.**
   *  백엔드를 내린 상태에서 실측하니 서버가 죽었는데도 그 문구가 나왔다 — 사용자는 산출물과
   *  권한을 확인하러 가고, 거기엔 아무 문제가 없다.
   *
   *  ⚠️ 반환 타입을 바꿨으므로 호출부 둘(`ControlPanel`·`RunControls`)을 **함께** 고쳤다.
   *    한쪽만 고치면 그 화면만 계속 원인을 지어낸다. */
  saveRelease: async (projectId: string) => {
    if (!projectId || get().currentProjectId !== projectId) {
      return { ...rejectedCommand('현재 선택한 프로젝트의 릴리스만 저장할 수 있습니다.', 'CURRENT_PROJECT_REQUIRED'),
        releaseId: null };
    }
    const isCurrent = currentProjectRequest(get, projectId);
    const result = await saveProjectRelease(projectId);
    if (!isCurrent()) return { ok: false, outcome: 'UNKNOWN', releaseId: null,
      reasonCode: 'CONTEXT_CHANGED', status: result.status,
      message: '저장 요청 중 문맥이 변경되었습니다. 원래 프로젝트의 릴리스 목록에서 결과를 확인하십시오.' };
    if (result.outcome === 'ACCEPTED' || result.outcome === 'UNKNOWN') void get().fetchReleases();
    return result;
  },

  //: ⚠️⚠️ [B6] 종전에는 `res.ok` 가 아니면 **아무 일도 하지 않았다** — console 에만 남고
  //:   화면은 반응이 없었다. 목록에서 눌러 여는 동안에는 잘 드러나지 않지만, 직접 링크로
  //:   들어오면 사용자는 **멎은 화면**을 본다. 조회 실패와 「아직 안 열었다」가 같아진다.
  //: ★ 401·403·404 는 **같은 문구**로 답한다. 나누면 존재 여부가 응답으로 새고, 사용자가
  //:   할 일은 어느 쪽이든 같다.
  viewRelease: async (releaseId: string) => {
    invalidateReleaseRequest();
    const generation = _releaseGeneration;
    const identity = releaseIdentity();
    const isCurrent = () => {
      if (generation !== _releaseGeneration) return false;
      if (identity !== releaseIdentity()) {
        // 이벤트 없이 값이 바뀐 경로에서도 이전 원문/로딩을 남기지 않는다.
        get().closeRelease();
        return false;
      }
      return true;
    };
    set({ viewingRelease: null, releaseLoad: 'loading', releaseError: '' });
    if (typeof releaseId !== 'string' || !/^[A-Za-z0-9_-]+$/.test(releaseId)) {
      set({ releaseLoad: 'failed', releaseError: '결과물 주소를 확인하십시오.' });
      return;
    }
    const controller = new AbortController();
    _releaseAbort = controller;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/library/item/${encodeURIComponent(releaseId)}`,
        { method: 'GET', cache: 'no-store', signal: controller.signal });
      // 취소를 무시하는 통신 구현과 이미 도착한 본문도 요청 세대로 차단한다.
      if (!isCurrent()) return;
      if (!res.ok) {
        const hidden = res.status === 401 || res.status === 403 || res.status === 404;
        set({ viewingRelease: null,
              releaseLoad: hidden ? 'forbidden' : 'failed',
              releaseError: hidden
                ? '현재 회사·권한에서 결과물을 찾을 수 없습니다.'
                : `결과물을 불러오지 못했습니다 (HTTP ${res.status}). 잠시 후 다시 확인하십시오.` });
        return;
      }
      const r = await res.json();
      if (!isCurrent()) return;
      if (!r || r.status !== 'success' || !r.data || typeof r.data !== 'object'
          || Array.isArray(r.data) || r.data.release_id !== releaseId) {
        set({ viewingRelease: null, releaseLoad: 'failed',
              releaseError: '서버가 결과물을 확인해 주지 않았습니다. 다시 확인하십시오.' });
        return;
      }
      set({ viewingRelease: r.data, releaseLoad: 'idle', releaseError: '' });
    } catch (error) {
      if (!isCurrent()) return;
      set({ viewingRelease: null, releaseLoad: 'failed',
            releaseError: '연결을 확인하지 못했습니다. 다시 확인하십시오.' });
    } finally {
      if (generation === _releaseGeneration) _releaseAbort = null;
    }
  },

  closeRelease: () => {
    invalidateReleaseRequest();
    set({ viewingRelease: null, releaseLoad: 'idle', releaseError: '' });
  },

  // ⚠️ [사용자 결정 2026-07-30] 서버는 기본적으로 **삭제를 거부**한다(409).
  //   배포된 프로그램을 지우면 다른 사용자가 남긴 기록이 고아가 되기 때문이며,
  //   필요한 조치는 `POST /api/v1/programs/{id}/disable`(사용 중단)이다.
  //   목록 화면의 삭제 버튼은 그래서 사용여부 제어(⚙)로 대체됐다. 이 함수는 남겨두되
  //   서버의 거부 안내를 **그대로** 보여준다 — 409 의 detail 은 객체다.
  deleteRelease: async (releaseId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/library/item/${releaseId}`, { method: 'DELETE' });
      // 500(파일 잠김 등)은 사용자에게 알린다. 404(이미 삭제됨)는 목록 갱신으로 흡수.
      if (!res.ok && res.status !== 404) {
        let msg = "결과물 삭제에 실패했습니다.";
        try {
          const r = await res.json();
          const d = r?.detail;
          // 객체를 그대로 문자열화하면 "[object Object]" 가 되어 안내가 사라진다.
          if (d) msg = `❌ ${typeof d === 'string' ? d
                          : [d.message, d.why, d.do_this_instead && `→ ${d.do_this_instead}`,
                             d.if_you_really_must].filter(Boolean).join('\n\n')}`;
        } catch { /* noop */ }
        alert(msg);
      }
      await get().fetchReleases();
    } catch (error) {
      console.error("결과물 삭제 실패:", error);
    }
  },

  clearAgentActionError: () => set({ agentActionError: '' }),

  fetchAgentRegistry: async () => {
    // ★★ [UIUX-AUDIT-30 §5] 실패를 콘솔에만 남기지 않는다. 예전에는 `agentRegistry` 가 `null`
    //   그대로여서 화면이 «에이전트 레지스트리 로딩 중…» 을 **영원히** 띄웠다. 사용자는
    //   기다리면 된다고 믿고, 실제로는 아무 일도 일어나지 않는다.
    set({ agentRegistryError: '' });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/agents`);
      if (res.ok) {
        const r = await res.json();
        set({ agentRegistry: r.data, agentRegistryError: '' });
      } else {
        // ★★★ [2026-08-04 이관 6/10 실측] **이전 사용자의 구성을 남기지 않는다.**
        //   종전에는 오류만 담고 `agentRegistry` 를 그대로 뒀다. 그래서 관리자로 보다가
        //   익명으로 바꾸면 «403 으로 못 읽었다» 는 배너와 **이전 사용자의 에이전트 목록**이
        //   같은 화면에 함께 떴다. 권한 잔상은 통제가 있는데도 없는 것처럼 보이게 만든다.
        set({
          agentRegistry: null,
          agentRegistryError: res.status === 403 || res.status === 401
            ? '에이전트 구성을 볼 권한이 없습니다 — 우측 상단에서 사용자를 지정하십시오.'
            : `서버가 ${res.status} 로 응답했습니다.`,
        });
      }
    } catch (error: any) {
      set({ agentRegistry: null, agentRegistryError: error?.message || String(error) });
    }
  },

  saveAgentRegistry: async (reg: any) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/agents`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reg),
      });
      if (res.ok) { const r = await res.json(); set({ agentRegistry: r.data }); return true; }
      let msg = "레지스트리 저장에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("에이전트 레지스트리 저장 실패:", error);
      return false;
    }
  },

  resetAgentRegistry: async () => {
    set({ agentActionError: '' });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/agents/reset`, { method: 'POST' });
      if (res.ok) {
        const r = await res.json();
        set({ agentRegistry: r.data, editingTemplateId: 'default' });
        return;
      }
      // ⚠️ 조용히 넘기면 사용자는 초기화가 된 줄 안다. 실패는 반드시 말한다.
      let msg = `초기화하지 못했습니다(서버 ${res.status}).`;
      if (res.status === 403) msg = '에이전트 구성을 초기화할 권한이 없습니다.';
      try { const r = await res.json(); if (r?.detail) msg = String(r.detail); } catch { /* noop */ }
      set({ agentActionError: msg });
    } catch (error: any) {
      set({ agentActionError: `초기화 실패: ${error?.message || error}` });
    }
  },

  /** 마지막 초기화 **직전** 구성으로 되돌린다. 백업이 없으면 서버가 404 로 알린다. */
  restoreAgentRegistry: async () => {
    set({ agentActionError: '' });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/agents/restore`, { method: 'POST' });
      if (res.ok) {
        const r = await res.json();
        set({ agentRegistry: r.data, editingTemplateId: 'default' });
        return true;
      }
      let msg = `되돌리지 못했습니다(서버 ${res.status}).`;
      try { const r = await res.json(); if (r?.detail) msg = String(r.detail); } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error: any) {
      set({ agentActionError: `복원 실패: ${error?.message || error}` });
      return false;
    }
  },

  openAgentPanel: () => {
    const tid = get().currentTemplateData?.id || 'default';
    set({ showAgentPanel: true, editingTemplateId: tid });
    get().fetchTemplates();
    get().fetchAgentRegistry();
  },
  closeAgentPanel: () => set({ showAgentPanel: false }),

  // ── 워크플로우 템플릿 관리(T2-c) ──────────────────────────────────────────────
  fetchTemplates: async () => {
    // ★★ [이관 6/10] 실패를 `console.error` 로 삼키면 화면이 «템플릿 없음»으로 보인다.
    //   백엔드에 자격 검사를 넣은 뒤로는 403 이 정상적으로 발생하므로 반드시 구분해야 한다.
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/templates`);
      if (res.ok) { const r = await res.json(); set({ templates: r.data || [], agentRegistryError: '' }); }
      else {
        set({ templates: [], agentRegistryError: res.status === 403
          ? '워크플로우 템플릿을 볼 권한이 없습니다 — «템플릿 없음»이 아닙니다.'
          : `템플릿 목록을 가져오지 못했습니다(서버 ${res.status}).` });
      }
    } catch (error: any) {
      set({ templates: [], agentRegistryError: `템플릿 목록 조회 실패: ${error?.message || error}` });
    }
  },

  setSelectedTemplate: (id: string) => set({ selectedTemplateId: id || 'default' }),

  // 제어판이 편집할 템플릿을 전환 — 해당 템플릿 레지스트리를 agentRegistry 로 로드
  selectEditingTemplate: async (id: string) => {
    const tid = id || 'default';
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/templates/${tid}`);
      if (res.ok) {
        const r = await res.json();
        set({ agentRegistry: r.data, editingTemplateId: tid, agentRegistryError: '' });
        return true;
      } else {
        // 이전 템플릿을 남기면 목록은 B인데 에이전트·그래프는 A인 상태가 된다.
        set({ agentRegistry: null, agentRegistryError: res.status === 403
          ? '이 템플릿을 볼 권한이 없습니다.'
          : `템플릿을 가져오지 못했습니다(서버 ${res.status}).` });
        return false;
      }
    } catch (error: any) {
      set({ agentRegistry: null,
        agentRegistryError: `템플릿 조회 실패: ${error?.message || error}` });
      return false;
    }
  },

  // 편집 중인 템플릿 저장 — PUT /templates/{id} (id=default 면 백엔드가 기본 레지스트리로 위임)
  saveTemplateRegistry: async (id: string, reg: any) => {
    const tid = id || 'default';
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/templates/${tid}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reg),
      });
      if (res.ok) {
        const r = await res.json();
        set({ agentRegistry: r.data });
        await get().fetchTemplates();
        return true;
      }
      let msg = "템플릿 저장에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("템플릿 저장 실패:", error);
      return false;
    }
  },

  copyTemplate: async (srcId: string, newId: string, newName?: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/templates/copy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ src_id: srcId || 'default', new_id: newId, new_name: newName || '' }),
      });
      if (res.ok) {
        await get().fetchTemplates();
        await get().selectEditingTemplate(newId);  // 복사본을 바로 편집 대상으로
        return true;
      }
      let msg = "템플릿 복사에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("템플릿 복사 실패:", error);
      return false;
    }
  },

  deleteTemplate: async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/templates/${id}`, { method: 'DELETE' });
      if (res.ok) {
        await get().fetchTemplates();
        // 편집 중이던 템플릿을 지웠으면 default 로 복귀
        if (get().editingTemplateId === id) await get().selectEditingTemplate('default');
        if (get().selectedTemplateId === id) set({ selectedTemplateId: 'default' });
        return true;
      }
      let msg = "템플릿 삭제에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("템플릿 삭제 실패:", error);
      return false;
    }
  },

  // ── 출력 포맷 관리 (Two-Track Harness) ──────────────────────────────────────────────
  fetchFormats: async () => {
    // ★★ [2026-08-07 · 트랙 G] **조회 실패를 0건으로 두지 않는다.**
    //   서식 API 를 봉합해 익명은 401 을 받는다. 종전 코드는 `res.ok` 가 아니면 조용히
    //   지나갔고, 그러면 화면은 이전 값(초기 `[]`)을 그대로 들고 «저장된 양식 (0)» 을 보여 준다.
    //   ⚠️ «서식이 하나도 없다» 와 «서식을 못 읽었다» 는 사용자가 해야 할 일이 다르다 —
    //     전자는 만들면 되고, 후자는 사용자를 지정해야 한다. 이 저장소가 반복해서 지키는 규칙이다.
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/formats`);
      if (res.ok) {
        const r = await res.json();
        set({ formats: r.data || [], formatsError: '' });
        return;
      }
      set({
        formatsError: res.status === 401
          ? '서식 목록을 보려면 우측 상단에서 사용자를 지정하십시오.'
          : res.status === 403
            ? '이 계정에는 산출물 서식을 볼 권한이 없습니다.'
            : `서식 목록을 불러오지 못했습니다 (${res.status}).`,
      });
    } catch (error) {
      console.error("포맷 목록 로드 실패:", error);
      set({ formatsError: '서버에 연결하지 못해 서식 목록을 불러오지 못했습니다.' });
    }
  },

  setSelectedFormat: (id: string) => set({ selectedFormatId: id || 'default' }),

  saveFormat: async (fmt: OutputFormat) => {
    try {
      // 신규 등록인지 수정인지 판별하여 POST/PUT 처리 가능 (단순화를 위해 PUT/POST)
      const existing = get().formats.find(f => f.id === fmt.id);
      const method = existing ? 'PUT' : 'POST';
      const url = existing ? `${API_BASE_URL}/api/v1/factory/formats/${fmt.id}` : `${API_BASE_URL}/api/v1/factory/formats`;
      
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fmt),
      });
      if (res.ok) {
        await get().fetchFormats();
        return true;
      }
      let msg = "포맷 저장에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("포맷 저장 실패:", error);
      return false;
    }
  },

  deleteFormat: async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/formats/${id}`, { method: 'DELETE' });
      if (res.ok) {
        await get().fetchFormats();
        if (get().selectedFormatId === id) set({ selectedFormatId: 'default' });
        return true;
      }
      let msg = "포맷 삭제에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("포맷 삭제 실패:", error);
      return false;
    }
  },

  openFormatPanel: () => {
    set({ showFormatPanel: true });
    get().fetchFormats();
  },
  
  closeFormatPanel: () => set({ showFormatPanel: false }),

  clearSprintData: () => set({ completed_agents: [], currentActivity: null, healingRetryCount: 0, lastSprintFailure: null }),

  clearSprintFailure: () => set({ lastSprintFailure: null }),
  clearSuspendedQuota: () => set({ isSuspendedQuota: false, suspendedTaskId: null }),

  triggerSelfHealing: async (errorMsg: string) => {
    const { currentProjectId, isConnected, healingRetryCount } = get();
    if (!currentProjectId) return { ok: false, outcome: 'LOCAL_BLOCKED', reasonCode: 'PROJECT_REQUIRED',
      message: '복구할 프로젝트를 선택하십시오.' };
    if (!isConnected) return { ok: false, outcome: 'LOCAL_BLOCKED', reasonCode: 'CONNECTION_REQUIRED',
      message: '연결이 끊겨 복구를 요청하지 않았습니다. 연결과 현재 상태를 확인하십시오.' };
    if (healingRetryCount >= 3) return { ok: false, outcome: 'LOCAL_BLOCKED', reasonCode: 'LOCAL_RETRY_LIMIT',
      message: '현재 화면의 복구 요청 3회 제한에 도달했습니다. 실패 근거를 확인하고 수동 검토하십시오.' };
    if (_healingInFlight?.()) return { ok: false, outcome: 'LOCAL_BLOCKED', reasonCode: 'HEAL_IN_FLIGHT',
      message: '복구 요청의 응답을 기다리고 있습니다. 중복 요청하지 마십시오.' };
    if (isProjectCommandPending(currentProjectId)) return { ok: false, outcome: 'LOCAL_BLOCKED', reasonCode: 'COMMAND_PENDING',
      message: '이 프로젝트의 다른 요청 결과를 기다리고 있어 복구 요청을 보내지 않았습니다.' };
    const isCurrent = currentProjectRequest(get, currentProjectId);
    _healingInFlight = isCurrent;
    // 로컬 요청 횟수일 뿐, 서버 복구 예산이나 성공/실패 횟수의 증거가 아니다.
    set({ healingRetryCount: healingRetryCount + 1 });
    try {
      const result = await requestSelfHealing(currentProjectId, errorMsg, get().lastSprintFailure?.taskId || 'sprint_init');
      if (!isCurrent()) return { ok: false, outcome: 'UNKNOWN', reasonCode: 'CONTEXT_CHANGED',
        requestId: result.requestId,
        message: '복구 요청 중 문맥이 변경되었습니다. 원래 프로젝트에서 작업 생성 여부를 확인하십시오.' };
      // 반환 taskId는 새 관찰 대상이며, 원래 실패 task/근거를 지우거나 실행 완료로 간주하지 않는다.
      if (result.outcome === 'HEAL_STARTED' || result.outcome === 'HOTL_PENDING' || result.outcome === 'UNKNOWN') {
        refreshExecution(get);
      }
      return result;
    } finally {
      if (_healingInFlight === isCurrent) _healingInFlight = null;
    }
  },

  fetchWBS: async (force = false) => {
    const { currentProjectId, isWbsError } = get();
    if ((isWbsError && !force) || !currentProjectId) return;
    const isCurrent = currentProjectRequest(get, currentProjectId, 'wbs');

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/wbs`);
      if (!res.ok) throw new Error("Fetch Fail");
      const result = await res.json();
      if (!isCurrent()) return;
      if (result.status === "success") {
        set({ wbsData: result.data, wbsErrorCount: 0, isWbsError: false });
      } else if (result.status === "not_found") {
        set({ wbsData: null, wbsErrorCount: 0, isWbsError: false });
      }
    } catch (error) {
      if (!isCurrent()) return;
      const newCount = get().wbsErrorCount + 1;
      set({ wbsErrorCount: newCount, isWbsError: newCount >= 3 });
    }
  },

  fetchLatestState: async () => {
    const pid = get().currentProjectId;
    if (!pid) return;
    const isCurrent = currentProjectRequest(get, pid, 'state');

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${pid}/state/latest`);
      if (!res.ok) return;
      const result = await res.json();
      // 전환 중 늦게 도착한 '이전 프로젝트' 응답을 새 프로젝트 store 에 덮지 않도록 재검증
      if (!isCurrent()) return;
      if (result.status === "success" && result.data) {
        // 머지(...prev.state) 금지 — 전체 교체. 빈 누적 필드가 이전 프로젝트 값으로 남는 stale 누수 차단.
        // ★★ [10.2-C] **재조회가 성공했으면 저장 실패 안내를 해제한다.**
        //   서버가 준 것이 지금 정본이므로 화면은 더 이상 «미확정» 이 아니다.
        //   안내를 걸기만 하고 내리지 않으면 그 안내는 곧 소음이 된다.
        set({ state: { ...result.data } as ProjectState, lastStateSaveError: null });
        const execution = result.data.studio_execution_state;
        if (execution && execution.task_id === result.data.current_sprint_task_id && typeof execution.running === 'boolean') {
          if (execution.running) set({ activeSprintId: execution.task_id });
          else if (get().activeSprintId === execution.task_id) set({ activeSprintId: null, currentActivity: null });
        }
        const tid = result.data.template_id || 'default';
        try {
          const tRes = await fetch(`${API_BASE_URL}/api/v1/factory/templates/${tid}`);
          if (tRes.ok) {
            const tData = await tRes.json();
            if (!isCurrent()) return;
            let templateData = tData.data;
            // 🎯 [서브 프로젝트 에이전트 필터링] domain_agents가 존재하면 해당 에이전트 + 프레임워크 에이전트만 남김
            const domainAgents: string[] = result.data.domain_agents || [];
            if (domainAgents.length > 0 && templateData?.agents) {
              templateData = {
                ...templateData,
                agents: templateData.agents.filter((a: any) =>
                  domainAgents.includes(a.id) || a.is_framework === true
                )
              };
            }
            set({ currentTemplateData: templateData });
          }
        } catch(e) { console.error("템플릿 정보 로드 실패", e); }
        } else if (result.status === "not_found") {
          const tid = result.data?.template_id || 'default';
          try {
            const tRes = await fetch(`${API_BASE_URL}/api/v1/factory/templates/${tid}`);
            if (tRes.ok) {
              const tData = await tRes.json();
              if (!isCurrent()) return;
              set({ state: null, currentTemplateData: tData.data });
            } else {
              if (!isCurrent()) return;
              set({ state: null, currentTemplateData: null });
            }
          } catch(e) { 
            console.error("템플릿 정보 로드 실패", e);
            if (!isCurrent()) return;
            set({ state: null, currentTemplateData: null }); 
          }
        } else {
          // 기타 에러 (명시적 비움)
          set({ state: null, currentTemplateData: null });
        }
    } catch (error) {
      console.error("최신 상태 복구 실패:", error);
    }
  },

  connectSSE: async () => {
    // 대기 중인 재연결 타이머 취소(수동/재연결 경합으로 인한 이중 연결 방지)
    if (_sseReconnectTimer) { clearTimeout(_sseReconnectTimer); _sseReconnectTimer = null; }
    // 기존 연결이 있으면 닫아 중복 수신 방지 (멱등)
    if (_sseConn) {
      try { _sseConn.close(); } catch (e) { /* noop */ }
      _sseConn = null;
    }
    // ★★★ [P0-1B] `?as_user=` 를 버리고 **1회용 접속표**로 바꿨다.
    //
    // 종전 주석은 「EventSource 는 헤더를 못 붙이므로 `as_user` 쿼리로 식별한다」였다. 그것은
    // 인증이 아니라 **자기 신고**였고, 다른 사람 ID 를 적으면 그 사람 알림을 받을 수 있었다.
    // 이제 세션 토큰으로 표를 받아(헤더가 붙는 평범한 POST) 그 표로만 연결한다.
    //
    // ⚠️ 표는 **연결할 때마다 새로 받는다.** 재사용하면 서버가 거절한다(1회 소비).
    // ⚠️ 발급에 실패하면 **연결하지 않는다** — `as_user` 로 되돌아가면 그것이 곧 우회로다.
    const myGen = ++_sseGeneration;
    const identityGeneration = _identityGeneration;

    // ⚠️ 세션이 없으면 **아예 시도하지 않는다.** 로그인 전에 5초마다 발급 API 를 두드리면
    //   서버 로그가 401 로 뒤덮이고, 정작 진짜 문제가 묻힌다. 로그인하면 화면이 다시 부른다.
    if (!getSessionToken()) { set({ isConnected: false }); return; }

    let ticket = '';
    try {
      // ★★★ [G1-C1.2] 화면이 **고른 조직 범위**를 함께 보낸다.
      //   종전에는 아무것도 보내지 않았고, 서버가 «주 부서» 로 추정했다. 그래서 여러 계열사
      //   권한을 가진 사람이 A 회사를 골라도 B 회사 이벤트가 오고, 가상회사 문맥을 골라도
      //   REAL 로 연결됐다 — **회사 선택기와 실시간 데이터 범위가 어긋났다.**
      //   ⚠️ 서버는 이 값을 그대로 믿지 않는다. 「그 사용자가 읽을 수 있는 범위인가」를 확인하고
      //     통과한 것만 티켓에 봉인한다(403 이면 고를 수 없는 범위를 고른 것이다).
      const r = await fetch(`${API_BASE_URL}/api/v1/auth/sse-ticket`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': getSessionToken() },
        body: JSON.stringify({ scope_node_id: getEnterpriseContext().scopeNodeId || '' }),
      });
      if (!r.ok) throw new Error(`ticket ${r.status}`);
      ticket = ((await r.json())?.data?.ticket) || '';
    } catch (e) {
      // 세션이 끊겼거나 서버가 죽었다. 조용히 익명 연결하지 않는다.
      if (myGen !== _sseGeneration || identityGeneration !== _identityGeneration) return;
      set({ isConnected: false });
      if (!_sseReconnectTimer) {
        _sseReconnectTimer = setTimeout(() => { _sseReconnectTimer = null; get().connectSSE(); }, 5000);
      }
      return;
    }

    // ★ 표를 받아 오는 사이에 더 새 시도가 시작됐다면 **여기서 멈춘다.**
    //   그대로 진행하면 고아 EventSource 가 생긴다(닫히지 않고 이벤트는 계속 받는다).
    if (myGen !== _sseGeneration || identityGeneration !== _identityGeneration) return;
    if (!ticket) { set({ isConnected: false }); return; }

    const eventSource = new EventSource(
      `${API_BASE_URL}/ws/timeline?ticket=${encodeURIComponent(ticket)}`);
    _sseConn = eventSource;

    const isCurrentConnection = () => _sseConn === eventSource && myGen === _sseGeneration
      && identityGeneration === _identityGeneration;
    eventSource.onopen = () => {
      if (!isCurrentConnection()) return;
      set({ isConnected: true }); get().checkHotl();
    };

    eventSource.onmessage = (event) => {
      if (!isCurrentConnection()) return;
      const data = JSON.parse(event.data);

      // 🔒 SSE 프로젝트 격리(fail-closed): 프로젝트를 보고 있는데 이벤트의 project_id 가
      // 현재 프로젝트와 정확히 일치하지 않으면(없거나 다르면) 전부 폐기 — 타 프로젝트/좀비
      // 스프린트의 상태·로그·피드가 새 프로젝트 화면으로 새는 것을 차단. (런처 화면 curPid=null 은
      // 그릴 프로젝트가 없어 무해하므로 통과)
      const evtPid = data?.payload?.project_id;
      const curPid = get().currentProjectId;
      if (curPid && evtPid !== curPid) return;

      // 이벤트당 set() 은 1회만 - 타입별 갱신과 로그 누적을 한 트랜잭션으로 합쳐
      // 모든 구독 컴포넌트가 이벤트마다 두 번씩 렌더되던 낭비를 제거
      const logEntry = { timestamp: data.timestamp, type: data.type, ...data.payload };
      set((prev) => {
        // 로그는 상한(500)을 두고 누적 - 장시간 세션에서 무제한 메모리 증가 방지
        const logs = [...prev.logs, logEntry].slice(-500);
        if (data.type === 'NODE_COMPLETED') {
          // ★★★ [G1-C1.1] 종전에는 `data.payload.state` 를 그대로 병합했다. 서버가 노드
          //   산출 상태를 **통째로** 실어 보냈기 때문이다. 이제 이벤트는 «무엇이 바뀌었는가»
          //   만 싣고(`changed_fields` · `state_version`), 상세는 **권한 검사가 붙은**
          //   `/state/latest` 로 가져온다. 이벤트에 실어 보내면 그 검사를 건너뛴다.
          //
          // ⚠️ `state_version` 으로 중복 조회를 거른다 — 노드가 끝날 때마다 전체 상태를
          //   다시 받으면 오히려 느려진다. 판본이 같으면 이미 가진 것이다.
          // ★★ [CR-W03-2C] **저장이 실패했으면 그 판본을 «확인된 최신» 으로 적지 않는다.**
          //   예전에는 `state_saved` 를 보지 않고 판본을 기록했다. 그러면 서버 정본은
          //   옛 판본인데 화면은 새 판본을 가졌다고 믿고, 같은 번호가 다시 와도
          //   «이미 가진 것» 이라며 재조회하지 않는다 — 옛 상태가 고정된다.
          const saveOk = data.payload?.state_saved !== false;
          const version = String(data.payload?.state_version || '');
          if (version && (version !== _lastStateVersion || !saveOk)) {
            if (saveOk) _lastStateVersion = version;
            // ⚠️ 여기서 await 하지 않는다 — 이 함수는 이벤트 축소(reducer)이고, 안에서
            //   네트워크를 기다리면 뒤따르는 이벤트 처리가 밀린다.
            void useFactoryStore.getState().fetchLatestState();
          }
          return {
            logs,
            // 계산은 끝났다 — 그건 그대로 센다. 저장 실패는 «따로» 남긴다.
            completed_agents: [...prev.completed_agents, data.payload.node],
            lastStateSaveError: saveOk ? null : {
              node: String(data.payload?.node || ''),
              error: String(data.payload?.state_save_error || ''),
              stale: Boolean(data.payload?.state_save_stale),
            },
          };
        }
        if (data.type === 'AGENT_ACTIVITY') {
          return {
            logs,
            currentActivity: { ...data.payload, ts: data.timestamp },
            supervisorFeed: [...prev.supervisorFeed, { ...data.payload, ts: data.timestamp }].slice(-200)
          };
        }
        if (data.type === 'HOTL_PAUSED') {
          return {
            logs,
            state: { ...(prev.state || {}), needs_revision: true, current_sprint_task_id: data.payload.task_id } as ProjectState,
            activeSprintId: null,
            hotlTaskId: data.payload.task_id,
            currentActivity: { node: "System", step: "인간 개입 필요", activity: "HOTL 게이트 대기 중..." }
          };
        }
        // ★★★ [2026-08-25] **계약 승인 대기.** 종전에는 이 갈래가 없어 서버가 멈춰도
        //   화면은 «완료» 로 보였다(오케스트레이터가 DONE 을 쐈다 — 그쪽도 함께 고쳤다).
        // ⚠️ 「대기」는 실패가 아니다 — 실패 배너를 띄우지 않고 승인 자리를 연다.
        if (data.type === 'CONTRACT_REVIEW_PENDING') {
          window.dispatchEvent(new CustomEvent('factory:contract-review-pending'));
          return {
            logs,
            state: { ...(prev.state || {}),
              current_sprint_task_id: data.payload?.task_id } as ProjectState,
            activeSprintId: null,
            currentActivity: { node: 'ContractReview', step: '계약 승인 대기',
              activity: '사람이 계약을 승인해야 코드로 넘어갑니다.' },
          };
        }
        if (data.type === 'QUOTA_EXHAUSTED') {
          // ★★ [10.2-C] 중단 상태를 정본에 못 적었으면 «보류됨» 만 보여 주고
          //   끝내지 않는다 — 재개를 판단할 근거가 서버에 없는 상태이기 때문이다.
          const quotaSaved = data.payload?.state_saved !== false;
          return {
            logs,
            lastStateSaveError: quotaSaved ? prev.lastStateSaveError : {
              node: 'QUOTA_EXHAUSTED', error: '중단 상태를 저장하지 못했습니다', stale: false,
            },
            isSuspendedQuota: true,
            suspendedTaskId: data.payload?.task_id || prev.suspendedTaskId,
            activeSprintId: null,
            currentActivity: { node: "System", step: "일시 정지", activity: "LLM 할당량 소진으로 태스크 보류됨" }
          };
        }
        if (data.type === 'SPRINT_COMPLETED') {
          // ★★★ [10.2-C] **계산 완료와 저장 미확정을 가른다.**
          //   마지막 저장이 실패한 채 완료 표시를 하면 화면은 「끝났고 저장도
          //   됐다」로 읽고, 새로고침하면 옛 판본이 온다. 실패면 **다시 물어본다.**
          const doneSaved = data.payload?.state_saved !== false;
          if (!doneSaved) {
            _lastStateVersion = '';            // 재조회를 막던 빗장을 푸다
            void useFactoryStore.getState().fetchLatestState();
          }
          return {
            logs,
            state: { ...(prev.state || {}), current_sprint_task_id: "" } as ProjectState,
            activeSprintId: null,
            hotlTaskId: null,
            currentActivity: null,
            lastStateSaveError: doneSaved ? prev.lastStateSaveError : {
              node: 'SPRINT_COMPLETED',
              error: String(data.payload?.state_save_error || ''),
              stale: false,
            },
          };
        }
        if (data.type === 'SPRINT_PAUSED') {
          return { logs, activeSprintId: null, currentActivity: null };
        }
        if (data.type === 'SPRINT_FAILED') {
          // 백엔드 스프린트 최종 실패 - '영원히 가동 중' 상태 해제 + 실패 배너(재시도 UI)용 정보 보존
          return {
            logs, activeSprintId: null, hotlTaskId: null, currentActivity: null,
            lastSprintFailure: {
              taskId: data.payload.task_id || '',
              error: data.payload.error || '스프린트 실패',
              detail: data.payload.detail || ''
            }
          };
        }
        return { logs };
      });
      if (data.type === 'SPRINT_COMPLETED' || data.type === 'WBS_UPDATED') {
        get().fetchWBS();
      }
    };

    eventSource.onerror = () => {
      if (!isCurrentConnection()) return;
      set({ isConnected: false });
      try { eventSource.close(); } catch (e) { /* noop */ }
      if (_sseConn === eventSource) _sseConn = null;
      // 재연결 타이머는 항상 1개만 유지 - 이전 타이머가 건강한 새 연결을 5초 뒤 찢는 것 방지
      if (_sseReconnectTimer) clearTimeout(_sseReconnectTimer);
      _sseReconnectTimer = setTimeout(() => { _sseReconnectTimer = null; useFactoryStore.getState().connectSSE(); }, 5000);
    };
  }
}));
