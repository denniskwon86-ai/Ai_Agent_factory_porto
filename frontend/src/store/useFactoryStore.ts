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
}

interface FactoryStore {
  state: ProjectState | null;
  logs: any[];
  isConnected: boolean;
  wbsData: any;
  isWbsError: boolean;
  wbsErrorCount: number;
  completed_agents: string[];

  connectSSE: () => void;
  fetchWBS: () => Promise<void>;
  clearSprintData: () => void;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const useFactoryStore = create<FactoryStore>()((set, get) => ({
  state: null,
  logs: [],
  isConnected: false,
  wbsData: null,
  isWbsError: false,
  wbsErrorCount: 0,
  completed_agents: [],

  // 🚨 [핵심 요건 반영] PM님의 상시 관전 지시에 따라 state(코드, 리뷰 기록)는 절대 지우지 않습니다.
  // 새 스프린트 시작 시 '에이전트 노선도'를 위해 completed_agents 배열만 롤백합니다.
  clearSprintData: () => set({ completed_agents: [] }),

  fetchWBS: async () => {
    if (get().isWbsError) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/wbs`);
      if (!res.ok) throw new Error("Fetch Fail");
      const result = await res.json();
      if (result.status === "success") {
        set({ wbsData: result.data, wbsErrorCount: 0 });
      }
    } catch (error) {
      const newCount = get().wbsErrorCount + 1;
      set({ wbsErrorCount: newCount, isWbsError: newCount >= 3 });
    }
  },

  connectSSE: () => {
    const eventSource = new EventSource(`${API_BASE_URL}/ws/timeline`);

    eventSource.onopen = () => set({ isConnected: true });

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'NODE_COMPLETED') {
        set((prev) => ({ 
            state: { ...(prev.state || {}), ...data.payload.state } as ProjectState,
            completed_agents: [...prev.completed_agents, data.payload.node] 
        }));
      } else if (data.type === 'HOTL_PAUSED') {
        set((prev) => ({
          state: { ...(prev.state || {}), needs_revision: true, current_sprint_task_id: data.payload.task_id } as ProjectState
        }));
      } else if (data.type === 'SPRINT_COMPLETED') {
        set((prev) => ({ state: { ...(prev.state || {}), current_sprint_task_id: "" } as ProjectState }));
        get().fetchWBS();
      } else if (data.type === 'WBS_UPDATED') {
        get().fetchWBS();
      }
      
      set((prev) => ({
        logs: [...prev.logs, { timestamp: data.timestamp, type: data.type, ...data.payload }]
      }));
    };

    eventSource.onerror = () => {
      set({ isConnected: false });
      eventSource.close();
      setTimeout(() => useFactoryStore.getState().connectSSE(), 5000);
    };
  }
}));