import { useState, useEffect } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function ControlPanel() {
  const [idea, setIdea] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [wbsData, setWbsData] = useState<any>(null);
  
  const state = useFactoryStore((s) => s.state);

  // 컴포넌트 마운트 시 & 주기적으로 WBS 현황을 백엔드에서 폴링
  const fetchWBS = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/wbs`);
      const result = await res.json();
      if (result.status === "success") {
        setWbsData(result.data);
      }
    } catch (error) {
      console.error("WBS 로드 실패:", error);
    }
  };

  useEffect(() => {
    fetchWBS();
    // 5초마다 WBS 갱신 (에이전트가 WBS 상태를 업데이트할 때 UI에 반영하기 위함)
    const interval = setInterval(fetchWBS, 5000);
    return () => clearInterval(interval);
  }, []);

  // [Track 0] 기획 파이프라인 가동 (최초 1회)
  const handleStartPlanning = async () => {
    if (!idea.trim()) {
      alert("💡 기획 아이디어를 입력해주세요.");
      return;
    }
    setIsStarting(true);
    try {
      await fetch(`${API_BASE_URL}/api/v1/factory/sprint/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: "PLANNING_TRACK",
          project_state_payload: {
            schema_version: "5.1.0",
            project_name: "Auto-Generated Project",
            initial_idea: idea,
            factory_mode: "PLANNING",
          }
        })
      });
      setIdea(""); 
    } catch (error) {
      console.error("기획 가동 실패:", error);
    } finally {
      setIsStarting(false);
    }
  };

  // [Track 1] 특정 스프린트(Task) 실행 파이프라인 가동
  const handleStartSprint = async (targetTask: any) => {
    if (!confirm(`[${targetTask.task_id}] ${targetTask.title}\n해당 스프린트를 가동하시겠습니까?`)) return;
    
    setIsStarting(true);
    try {
      await fetch(`${API_BASE_URL}/api/v1/factory/sprint/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: targetTask.task_id,
          project_state_payload: {
            schema_version: "5.1.0",
            project_name: wbsData.project_name,
            current_sprint_task_id: targetTask.task_id, // 선택한 Task ID 주입
            factory_mode: "EXECUTION", // 기획을 건너뛰고 바로 실행(코드 작성) 모드로 진입
          }
        })
      });
    } catch (error) {
      console.error("스프린트 가동 실패:", error);
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-800 text-gray-200">
      <div className="p-4 border-b border-gray-700 bg-gray-900 shrink-0">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          ⚙️ 팩토리 제어반
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {/* WBS가 없을 때만 기획(Track 0) 입력창 표시 */}
        {!wbsData ? (
          <div className="flex flex-col gap-2">
            <label className="text-sm font-semibold text-gray-400">💡 1. 신규 기획 (Track 0)</label>
            <p className="text-xs text-gray-500 mb-1">PM과 PMO가 Master PRD와 WBS를 작성합니다.</p>
            <textarea 
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              disabled={isStarting}
              placeholder="프로젝트 아이디어를 입력하세요..."
              className="w-full h-32 bg-gray-950 border border-gray-700 rounded p-3 text-sm focus:outline-none focus:border-blue-500 resize-none"
            />
            <button 
              onClick={handleStartPlanning}
              disabled={isStarting || !idea.trim()}
              className="mt-2 w-full bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 font-bold py-3 rounded transition-colors"
            >
              {isStarting ? "가동 중..." : "🎯 기획 및 WBS 분할 가동"}
            </button>
          </div>
        ) : (
          /* WBS가 존재하면 스프린트(Track 1) 목록 표시 */
          <div className="flex flex-col gap-3">
            <div className="flex justify-between items-end mb-2 border-b border-gray-700 pb-2">
              <label className="text-sm font-semibold text-gray-400">📋 2. 일일 스프린트 제어 (Track 1)</label>
              <span className="text-xs text-blue-400">프로젝트: {wbsData.project_name}</span>
            </div>
            
            {wbsData.tasks.map((task: any) => (
              <div key={task.task_id} className={`p-3 rounded border ${task.status === 'DONE' ? 'bg-gray-900 border-green-900/50 opacity-60' : 'bg-gray-800 border-gray-600'}`}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs font-bold text-blue-300">{task.task_id}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${task.status === 'DONE' ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'}`}>
                    {task.status || "TODO"}
                  </span>
                </div>
                <h4 className="text-sm font-bold text-gray-200 mb-1">{task.title}</h4>
                <p className="text-xs text-gray-400 mb-3">{task.goal}</p>
                
                {task.status !== 'DONE' && (
                  <button 
                    onClick={() => handleStartSprint(task)}
                    disabled={isStarting || state?.current_sprint_task_id === task.task_id}
                    className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-xs font-bold py-2 rounded transition-colors"
                  >
                    {state?.current_sprint_task_id === task.task_id ? "▶️ 현재 실행 중" : "🚀 이 스프린트 가동하기"}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}