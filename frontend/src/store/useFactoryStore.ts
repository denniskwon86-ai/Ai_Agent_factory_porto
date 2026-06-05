import { create } from 'zustand';

// 백엔드의 state_models.py와 동기화되는 프론트엔드 타입 정의
export interface ProjectState {
  project_name: string;
  factory_mode: string;
  build_status: string;
  current_sprint_task_id: string;
  needs_revision: boolean;
  human_feedback_queue: any[];
  developer_retry_count: number;
  
  // 🚨 PreviewPanel 출력을 위한 에이전트 산출물 속성 추가
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
  connectSSE: () => void;
}

export const useFactoryStore = create<FactoryStore>()((set) => ({
  state: null,
  logs: [],
  isConnected: false,

  connectSSE: () => {
    const eventSource = new EventSource('http://localhost:8000/ws/timeline');

    eventSource.onopen = () => {
      console.log('✅ AI Factory 관제 센터 통신망 연결 완료');
      set({ isConnected: true });
    };

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'NODE_COMPLETED') {
        set((prev) => ({ 
          // prev.state가 null일 경우를 대비해 빈 객체로 안전하게 언래핑
          state: { ...(prev.state || {}), ...data.payload.state } as ProjectState
        }));
      } else if (data.type === 'HOTL_PAUSED') {
        set((prev) => ({
          state: { 
            ...(prev.state || {}), 
            needs_revision: true,
            current_sprint_task_id: "data.payload.task_id" // 🚨 핵심 조치: 백엔드 이벤트에서 직접 Task ID를 구출해 주입!
          } as ProjectState
        }));
      
      } else if (data.type === 'SPRINT_COMPLETED') {
        // 🚨 [추가된 로직] 스프린트가 완전히 종료되면, 현재 진행 중인 Task ID를 비워 UI 잠금을 해제합니다.
        set((prev) => ({
          state: { 
            ...(prev.state || {}), 
            current_sprint_task_id: "" 
          } as ProjectState
        }));
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