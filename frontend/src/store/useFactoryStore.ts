import { create } from 'zustand';

export interface ProjectState {
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
  selectedFormatId: string;
  showFormatPanel: boolean;
  projects: { id: string, name: string, initial_idea?: string, is_mega_project?: boolean, parent_project_id?: string, template_id?: string, total_tasks?: number, completed_tasks?: number }[];
  currentProjectId: string | null;
  healingRetryCount: number;
  activeSprintId: string | null;
  hotlTaskId: string | null;
  currentTemplateData: any | null;
  setActiveSprintId: (id: string | null) => void;
  setCurrentProject: (id: string | null) => void;
  fetchProjects: () => Promise<void>;
  createProject: (id: string, templateId?: string, knowledgePackIds?: string[], masterDomains?: string[], mcpLiveGrounding?: boolean) => Promise<boolean>;
  createMegaProject: (id: string, templateId?: string) => Promise<boolean>;
  copyProject: (id: string, newId: string) => Promise<boolean>;
  deleteProject: (id: string) => Promise<boolean>; // 🗑️ 프로젝트 완전 삭제 기능 정의
  connectSSE: () => void;
  fetchWBS: () => Promise<void>;
  fetchLatestState: () => Promise<void>;
  checkHotl: () => Promise<void>;
  fetchFeed: () => Promise<void>;
  fetchReleases: () => Promise<void>;
  saveRelease: (projectId: string) => Promise<string | null>;
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
  selectEditingTemplate: (id: string) => Promise<void>;
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
  triggerSelfHealing: (errorMsg: string) => Promise<void>;
  stopSprint: (projectId: string, taskId: string) => Promise<void>;
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080';

// [CL-4] 사용자 식별을 쿼리로 싣는 공용 헬퍼. 여기서 다시 구현하지 않는다.
import { apiUrl } from '../lib/api';

// 단일 SSE 연결만 유지 — StrictMode 이중 마운트/자동 재연결 시 중복 연결로 이벤트가 2번 수신되는 것 방지
let _sseConn: EventSource | null = null;
let _sseReconnectTimer: ReturnType<typeof setTimeout> | null = null;

export const useFactoryStore = create<FactoryStore>()((set, get) => ({
  state: null,
  logs: [],
  isConnected: false,
  wbsData: null,
  isWbsError: false,
  wbsErrorCount: 0,
  completed_agents: [],
  currentActivity: null,
  lastSprintFailure: null,
  isSuspendedQuota: false,
  suspendedTaskId: null,
  supervisorFeed: [],
  releases: [],
  viewingRelease: null,
  agentRegistry: null,
  agentRegistryError: '',
  agentActionError: '',
  showAgentPanel: false,
  templates: [],
  selectedTemplateId: 'default',
  editingTemplateId: 'default',
  formats: [],
  selectedFormatId: 'default',
  showFormatPanel: false,
  projects: [],
  currentProjectId: null,
  healingRetryCount: 0,
  activeSprintId: null,
  hotlTaskId: null,
  currentTemplateData: null,

  setActiveSprintId: (id) => set({ activeSprintId: id }),

  setCurrentProject: (id) => {
    set({
      currentProjectId: id, state: null, wbsData: null, logs: [],
      completed_agents: [], currentActivity: null, lastSprintFailure: null, supervisorFeed: [], healingRetryCount: 0, activeSprintId: null, hotlTaskId: null, currentTemplateData: null
    });
    if (id) {
      get().fetchWBS();
      get().fetchLatestState();
      get().checkHotl();
      get().fetchFeed();
    }
  },

  fetchProjects: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects`);
      if (res.ok) {
        const result = await res.json();
        if (result.status === "success") {
          set({ projects: result.data });
        }
      }
    } catch (error) {
      console.error("프로젝트 목록 로드 실패:", error);
    }
  },

  createProject: async (id: string, templateId?: string, knowledgePackIds?: string[], masterDomains?: string[], mcpLiveGrounding?: boolean) => {
    try {

      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: id,
          template_id: templateId || get().selectedTemplateId || 'default',
          knowledge_pack_ids: knowledgePackIds || [],
          master_domains: masterDomains || [],
          mcp_live_grounding: mcpLiveGrounding || false
        })
      });
      if (res.ok) {
        await get().fetchProjects();
        return true;
      }
      // 백엔드 검증 실패(404 미존재 템플릿 / 400 형식 / 409 중복)는 사유를 표면화
      let msg = "프로젝트 생성에 실패했습니다. (중복된 ID일 수 있습니다)";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("프로젝트 생성 실패:", error);
      return false;
    }
  },

  createMegaProject: async (id: string, templateId?: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects/mega`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          mega_project_id: id, 
          template_id: templateId || get().selectedTemplateId || 'manufacturing-production'
        })
      });
      if (res.ok) {
        await get().fetchProjects();
        return true;
      }
      let msg = "메가 프로젝트 생성에 실패했습니다. (중복된 ID일 수 있습니다)";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("메가 프로젝트 생성 실패:", error);
      return false;
    }
  },

  stopSprint: async (projectId: string, taskId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${projectId}/sprint/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId })
      });
      if (!res.ok) {
        alert("스프린트 중지 요청이 서버에서 거부되었습니다.");
      }
    } catch (error) {
      console.error('Stop sprint API failed, but UI state will be forcefully cleared:', error);
      alert("서버에 연결할 수 없어 강제로 UI 상태를 초기화합니다.");
    } finally {
      // API 통신 성공/실패 여부와 관계없이 무조건 프론트엔드의 진행 중 상태를 초기화하여 UI 블로킹 해제
      // needs_revision/current_sprint_task_id 까지 지워야 정지 후 'HOTL 대기 중' 유령 배너와
      // 죽은 태스크에 대한 승인(resume) 버튼이 남지 않는다
      set((prev) => ({
        activeSprintId: null, hotlTaskId: null, currentActivity: null,
        state: prev.state ? ({ ...prev.state, needs_revision: false, current_sprint_task_id: "" } as ProjectState) : null,
      }));
    }
  },

  copyProject: async (id: string, newId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects/${id}/copy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_project_id: newId })
      });
      if (res.ok) {
        await get().fetchProjects();
        return true;
      }
      let msg = "시나리오 복제에 실패했습니다.";
      try { const r = await res.json(); if (r?.detail) msg = `❌ ${r.detail}`; } catch { /* noop */ }
      set({ agentActionError: msg });
      return false;
    } catch (error) {
      console.error("프로젝트 복제 실패:", error);
      return false;
    }
  },

  // 🗑️ 백엔드 라우터 API 명세와 연동되는 프로젝트 완전 삭제 기능 구현
  deleteProject: async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        await get().fetchProjects();
        if (get().currentProjectId === id) {
          // 삭제된 프로젝트의 state가 스토어에 남아 다른 화면(릴리스 보기 등)에 노출되지 않도록 함께 비운다
          set({ currentProjectId: null, state: null, wbsData: null });
        }
        return true;
      }
      return false;
    } catch (error) {
      console.error("프로젝트 삭제 실패:", error);
      return false;
    }
  },

  checkHotl: async () => {
    const pid = get().currentProjectId;
    if (!pid) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${pid}/hotl/check`);
      if (res.ok) {
        const r = await res.json();
        // 전환 중 늦게 도착한 '이전 프로젝트' 응답이 새 프로젝트에 HOTL 대기를 주입하지 않도록 재검증
        if (get().currentProjectId !== pid) return;
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
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${pid}/feed`);
      if (res.ok) {
        const r = await res.json();
        if (get().currentProjectId !== pid) return; // 프로젝트 전환 중 stale 응답 차단
        if (Array.isArray(r.data)) set({ supervisorFeed: r.data.slice(-200) });
      }
    } catch (error) {
      console.error("슈퍼바이저 피드 로드 실패:", error);
    }
  },

  fetchReleases: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/library/list`);
      if (res.ok) {
        const r = await res.json();
        set({ releases: Array.isArray(r.data) ? r.data : [] });
      }
    } catch (error) {
      console.error("라이브러리 목록 로드 실패:", error);
    }
  },

  saveRelease: async (projectId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${projectId}/release`, { method: 'POST' });
      if (res.ok) {
        const r = await res.json();
        await get().fetchReleases();
        return r.release_id || null;
      }
    } catch (error) {
      console.error("최종 결과물 저장 실패:", error);
    }
    return null;
  },

  viewRelease: async (releaseId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/library/item/${releaseId}`);
      if (res.ok) {
        const r = await res.json();
        set({ viewingRelease: r.data });
      }
    } catch (error) {
      console.error("결과물 로드 실패:", error);
    }
  },

  closeRelease: () => set({ viewingRelease: null }),

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
      } else {
        set({ agentRegistryError: res.status === 403
          ? '이 템플릿을 볼 권한이 없습니다.'
          : `템플릿을 가져오지 못했습니다(서버 ${res.status}).` });
      }
    } catch (error: any) {
      set({ agentRegistryError: `템플릿 조회 실패: ${error?.message || error}` });
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
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/formats`);
      if (res.ok) { const r = await res.json(); set({ formats: r.data || [] }); }
    } catch (error) {
      console.error("포맷 목록 로드 실패:", error);
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
    if (!currentProjectId || !isConnected) return;

    if (healingRetryCount >= 3) {
       // window.onerror 는 에러마다 반복 발화하므로 경고는 정확히 1회만(alert 폭풍 방지)
       if (healingRetryCount === 3) {
         set({ healingRetryCount: 4 });
         alert(`🚨 [자가 치유 실패] 3회 연속 복구에 실패했습니다.\n에러: ${errorMsg}\n수동 개입(코드 수정)이 필요합니다.`);
       }
       return;
    }

    set({ healingRetryCount: healingRetryCount + 1 });
    console.warn(`🩹 [자가 치유 가동] AI가 에러를 감지하고 스스로 복구를 시도합니다. (시도: ${healingRetryCount + 1}/3)`);

    try {
      await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/heal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error_log: errorMsg })
      });
    } catch (error) {
      console.error("자가 치유 트리거 실패:", error);
    }
  },

  fetchWBS: async () => {
    const { currentProjectId, isWbsError } = get();
    if (isWbsError || !currentProjectId) return;

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/wbs`);
      if (!res.ok) throw new Error("Fetch Fail");
      const result = await res.json();
      if (get().currentProjectId !== currentProjectId) return; // 프로젝트 전환 중 stale 응답 차단
      if (result.status === "success") {
        set({ wbsData: result.data, wbsErrorCount: 0 });
      } else if (result.status === "not_found") {
        set({ wbsData: null, wbsErrorCount: 0 }); 
      }
    } catch (error) {
      const newCount = get().wbsErrorCount + 1;
      set({ wbsErrorCount: newCount, isWbsError: newCount >= 3 });
    }
  },

  fetchLatestState: async () => {
    const pid = get().currentProjectId;
    if (!pid) return;

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${pid}/state/latest`);
      if (!res.ok) return;
      const result = await res.json();
      // 전환 중 늦게 도착한 '이전 프로젝트' 응답을 새 프로젝트 store 에 덮지 않도록 재검증
      if (get().currentProjectId !== pid) return;
      if (result.status === "success" && result.data) {
        // 머지(...prev.state) 금지 — 전체 교체. 빈 누적 필드가 이전 프로젝트 값으로 남는 stale 누수 차단.
        set({ state: { ...result.data } as ProjectState });
        const tid = result.data.template_id || 'default';
        try {
          const tRes = await fetch(`${API_BASE_URL}/api/v1/factory/templates/${tid}`);
          if (tRes.ok) {
            const tData = await tRes.json();
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
              set({ state: null, currentTemplateData: tData.data });
            } else {
              set({ state: null, currentTemplateData: null });
            }
          } catch(e) { 
            console.error("템플릿 정보 로드 실패", e);
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

  connectSSE: () => {
    // 대기 중인 재연결 타이머 취소(수동/재연결 경합으로 인한 이중 연결 방지)
    if (_sseReconnectTimer) { clearTimeout(_sseReconnectTimer); _sseReconnectTimer = null; }
    // 기존 연결이 있으면 닫아 중복 수신 방지 (멱등)
    if (_sseConn) {
      try { _sseConn.close(); } catch (e) { /* noop */ }
      _sseConn = null;
    }
    // [CL-4] ★★ `apiUrl()` 로 만든다 — EventSource 는 헤더를 못 붙이므로 사용자 식별이
    //   `?as_user=` 쿼리로 실려야 한다. 예전처럼 `API_BASE_URL` 만 쓰면 이 연결은 **항상
    //   익명**이고, 서버는 익명 구독자에게 지정 수신자 이벤트를 보내지 않는다 —
    //   즉 전달·결정·발간 알림이 브라우저에 영원히 도착하지 않는다(2026-08-04 실측).
    const eventSource = new EventSource(apiUrl('/ws/timeline'));
    _sseConn = eventSource;

    eventSource.onopen = () => { set({ isConnected: true }); get().checkHotl(); };

    eventSource.onmessage = (event) => {
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
          return {
            logs,
            state: { ...(prev.state || {}), ...data.payload.state } as ProjectState,
            completed_agents: [...prev.completed_agents, data.payload.node]
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
        if (data.type === 'QUOTA_EXHAUSTED') {
          return {
            logs,
            isSuspendedQuota: true,
            suspendedTaskId: data.payload?.task_id || prev.suspendedTaskId,
            activeSprintId: null,
            currentActivity: { node: "System", step: "일시 정지", activity: "LLM 할당량 소진으로 태스크 보류됨" }
          };
        }
        if (data.type === 'SPRINT_COMPLETED') {
          return {
            logs,
            state: { ...(prev.state || {}), current_sprint_task_id: "" } as ProjectState,
            activeSprintId: null,
            hotlTaskId: null,
            currentActivity: null
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
      set({ isConnected: false });
      try { eventSource.close(); } catch (e) { /* noop */ }
      if (_sseConn === eventSource) _sseConn = null;
      // 재연결 타이머는 항상 1개만 유지 - 이전 타이머가 건강한 새 연결을 5초 뒤 찢는 것 방지
      if (_sseReconnectTimer) clearTimeout(_sseReconnectTimer);
      _sseReconnectTimer = setTimeout(() => { _sseReconnectTimer = null; useFactoryStore.getState().connectSSE(); }, 5000);
    };
  }
}));