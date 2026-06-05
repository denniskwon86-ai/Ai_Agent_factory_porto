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
  
  // 🚨 [추가] WBS 및 서킷 브레이커 전역 상태
  wbsData: any;
  isWbsError: boolean;
  wbsErrorCount: number;
  
  connectSSE: () => void;
  fetchWBS: () => Promise<void>;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const useFactoryStore = create<FactoryStore>()((set, get) => ({
  state: null,
  logs: [],
  isConnected: false,
  wbsData: null,
  isWbsError: false,
  wbsErrorCount: 0,

  // 🚨 능동적 API 폴링 함수 (서킷 브레이커 내장)
  fetchWBS: async () => {
    // 이미 에러가 3번 나서 차단기가 내려갔다면 더 이상 요청하지 않음
    if (get().isWbsError) return;
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/wbs`);
      if (!res.ok) throw new Error("Fetch Fail");
      const result = await res.json();
      if (result.status === "success") {
        set({ wbsData: result.data, wbsErrorCount: 0 }); // 성공 시 에러 카운트 초기화
      }
    } catch (error) {
      const newCount = get().wbsErrorCount + 1;
      // 3회 이상 실패 시 서킷 브레이커 작동
      set({ wbsErrorCount: newCount, isWbsError: newCount >= 3 });
      console.error("🚨 WBS 로드 실패. 누적 에러:", newCount);
    }
  },

  connectSSE: () => {
    const eventSource = new EventSource(`${API_BASE_URL}/ws/timeline`);

    eventSource.onopen = () => {
      console.log('✅ AI Factory 관제 센터 통신망 연결 완료');
      set({ isConnected: true });
    };

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'NODE_COMPLETED') {
        set((prev) => ({ state: { ...(prev.state || {}), ...data.payload.state } as ProjectState }));
      } else if (data.type === 'HOTL_PAUSED') {
        set((prev) => ({
          state: { ...(prev.state || {}), needs_revision: true, current_sprint_task_id: data.payload.task_id } as ProjectState
        }));
      } else if (data.type === 'SPRINT_COMPLETED') {
        set((prev) => ({ state: { ...(prev.state || {}), current_sprint_task_id: "" } as ProjectState }));
        get().fetchWBS(); // 스프린트 종료 시 WBS 갱신
      } else if (data.type === 'WBS_UPDATED') {
        // 🚨 [핵심] 백엔드에서 WBS 상태가 바뀌었다고 방송(SSE)하면, 그때만 딱 1번 WBS를 새로 읽어옴!
        get().fetchWBS();
      }
      
      set((prev) => ({
        logs: [...prev.logs, { timestamp: data.timestamp, type: data.type, ...data.payload }]
      }));
    };

    eventSource.onerror = () => {
      console.error('🚨 통신 단절. 재연결을 시도합니다...');
      set({ isConnected: false });
      eventSource.close();
      setTimeout(() => useFactoryStore.getState().connectSSE(), 5000);
    };
  }
}));