import { create } from 'zustand';

export interface ProjectState {
  project_name: string;
  factory_mode: string;
  build_status: string;
  current_sprint_task_id: string;
  needs_revision: boolean;
  human_feedback_queue: any[];
  developer_retry_count: number;
  prd_summary: string;
  architecture_summary: string;
  tech_spec_summary: string;
  frontend_code_summary: string;
  backend_code_summary: string;
  code_review_report_summary: string;
  qa_report_summary: string;
  user_manual_summary: string;
  build_error_log?: string;
  // 토론·합의 / 단계별 성공기준 / Supervisor (V5.1 관측성)
  current_stage?: string;
  stage_scores?: Record<string, number>;
  debate_rounds_used?: Record<string, number>;
  supervisor_feedback?: string;
  criteria_log?: any[];
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
  supervisorFeed: any[];
  projects: { id: string, name: string }[];
  currentProjectId: string | null;
  healingRetryCount: number;
  activeSprintId: string | null;
  hotlTaskId: string | null;
  setActiveSprintId: (id: string | null) => void;
  setCurrentProject: (id: string | null) => void;
  fetchProjects: () => Promise<void>;
  createProject: (id: string) => Promise<boolean>;
  deleteProject: (id: string) => Promise<boolean>; // 🗑️ 프로젝트 완전 삭제 기능 정의
  connectSSE: () => void;
  fetchWBS: () => Promise<void>;
  fetchLatestState: () => Promise<void>;
  checkHotl: () => Promise<void>;
  fetchFeed: () => Promise<void>;
  clearSprintData: () => void;
  triggerSelfHealing: (errorMsg: string) => Promise<void>;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// 단일 SSE 연결만 유지 — StrictMode 이중 마운트/자동 재연결 시 중복 연결로 이벤트가 2번 수신되는 것 방지
let _sseConn: EventSource | null = null;

export const useFactoryStore = create<FactoryStore>()((set, get) => ({
  state: null,
  logs: [],
  isConnected: false,
  wbsData: null,
  isWbsError: false,
  wbsErrorCount: 0,
  completed_agents: [],
  currentActivity: null,
  supervisorFeed: [],
  projects: [],
  currentProjectId: null,
  healingRetryCount: 0,
  activeSprintId: null,
  hotlTaskId: null,

  setActiveSprintId: (id) => set({ activeSprintId: id }),

  setCurrentProject: (id) => {
    set({
      currentProjectId: id, state: null, wbsData: null, logs: [],
      completed_agents: [], currentActivity: null, supervisorFeed: [], healingRetryCount: 0, activeSprintId: null, hotlTaskId: null
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

  createProject: async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: id })
      });
      if (res.ok) {
        await get().fetchProjects();
        return true;
      }
      return false;
    } catch (error) {
      console.error("프로젝트 생성 실패:", error);
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
          set({ currentProjectId: null });
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
        if (Array.isArray(r.data)) set({ supervisorFeed: r.data.slice(-200) });
      }
    } catch (error) {
      console.error("슈퍼바이저 피드 로드 실패:", error);
    }
  },

  clearSprintData: () => set({ completed_agents: [], currentActivity: null, healingRetryCount: 0 }),

  triggerSelfHealing: async (errorMsg: string) => {
    const { currentProjectId, isConnected, healingRetryCount } = get();
    if (!currentProjectId || !isConnected) return;

    if (healingRetryCount >= 3) {
       alert(`🚨 [자가 치유 실패] 3회 연속 복구에 실패했습니다.\n에러: ${errorMsg}\n수동 개입(코드 수정)이 필요합니다.`);
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
    const { currentProjectId } = get();
    if (!currentProjectId) return;

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/state/latest`);
      if (res.ok) {
        const result = await res.json();
        if (result.status === "success" && result.data) {
          set((prev) => ({ 
            state: { ...(prev.state || {}), ...result.data } as ProjectState 
          }));
        }
      }
    } catch (error) {
      console.error("최신 상태 복구 실패:", error);
    }
  },

  connectSSE: () => {
    // 기존 연결이 있으면 닫아 중복 수신 방지 (멱등)
    if (_sseConn) {
      try { _sseConn.close(); } catch (e) { /* noop */ }
      _sseConn = null;
    }
    const eventSource = new EventSource(`${API_BASE_URL}/ws/timeline`);
    _sseConn = eventSource;

    eventSource.onopen = () => { set({ isConnected: true }); get().checkHotl(); };

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      // 🔒 SSE 프로젝트 격리: 다른 프로젝트(또는 삭제된 좀비 스프린트)의 이벤트는 무시
      const evtPid = data?.payload?.project_id;
      const curPid = get().currentProjectId;
      if (evtPid && curPid && evtPid !== curPid) return;

      if (data.type === 'NODE_COMPLETED') {
        set((prev) => ({ 
            state: { ...(prev.state || {}), ...data.payload.state } as ProjectState,
            completed_agents: [...prev.completed_agents, data.payload.node] 
        }));
      } else if (data.type === 'AGENT_ACTIVITY') {
        set((prev) => ({
          currentActivity: { ...data.payload, ts: data.timestamp },
          supervisorFeed: [...prev.supervisorFeed, { ...data.payload, ts: data.timestamp }].slice(-200)
        }));
      } else if (data.type === 'HOTL_PAUSED') {
        set((prev) => ({
          state: { ...(prev.state || {}), needs_revision: true, current_sprint_task_id: data.payload.task_id } as ProjectState,
          activeSprintId: null,
          hotlTaskId: data.payload.task_id,
          currentActivity: null
        }));
      } else if (data.type === 'SPRINT_COMPLETED') {
        set((prev) => ({
          state: { ...(prev.state || {}), current_sprint_task_id: "" } as ProjectState,
          activeSprintId: null,
          hotlTaskId: null,
          currentActivity: null
        }));
        get().fetchWBS();
      } else if (data.type === 'WBS_UPDATED') {
        get().fetchWBS();
      } else if (data.type === 'SPRINT_PAUSED') {
        set({ activeSprintId: null, currentActivity: null });
      }
      
      set((prev) => ({
        logs: [...prev.logs, { timestamp: data.timestamp, type: data.type, ...data.payload }]
      }));
    };

    eventSource.onerror = () => {
      set({ isConnected: false });
      try { eventSource.close(); } catch (e) { /* noop */ }
      if (_sseConn === eventSource) _sseConn = null;
      setTimeout(() => useFactoryStore.getState().connectSSE(), 5000);
    };
  }
}));