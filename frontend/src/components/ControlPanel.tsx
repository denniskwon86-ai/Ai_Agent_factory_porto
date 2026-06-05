import { useState, useEffect } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function ControlPanel() {
  const [idea, setIdea] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  
  const state = useFactoryStore((s) => s.state);
  const wbsData = useFactoryStore((s) => s.wbsData);
  const isWbsError = useFactoryStore((s) => s.isWbsError);
  const fetchWBS = useFactoryStore((s) => s.fetchWBS);

  // 컴포넌트 마운트 시 1회만 호출 (이후 갱신은 SSE가 알아서 처리함)
  useEffect(() => {
    fetchWBS();
  }, [fetchWBS]);

  // 🎯 진척률 계산 로직
  const totalTasks = wbsData?.tasks?.length || 0;
  const doneTasks = wbsData?.tasks?.filter((t: any) => t.status === 'DONE').length || 0;
  const progressPercent = totalTasks === 0 ? 0 : Math.round((doneTasks / totalTasks) * 100);

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
            current_sprint_task_id: targetTask.task_id,
            factory_mode: "EXECUTION", 
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
        {/* 🚨 서킷 브레이커 발동 시 에러 경고 UI */}
        {isWbsError && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-sm text-red-200">
            🚨 백엔드 서버와의 통신이 단절되었습니다. (네트워크 차단 발동 중)<br/>
            서버를 재가동하신 후 브라우저를 새로고침 해주세요.
          </div>
        )}

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
          <div className="flex flex-col gap-3">
            {/* 🎯 진척률 대시보드 UI */}
            <div className="flex flex-col mb-2 border-b border-gray-700 pb-3">
              <div className="flex justify-between items-end mb-1">
                <label className="text-sm font-semibold text-gray-400">📋 2. 일일 스프린트 통제</label>
                <span className="text-xs font-bold text-blue-400">진척률: {progressPercent}% ({doneTasks}/{totalTasks})</span>
              </div>
              <div className="w-full bg-gray-950 rounded-full h-2 mt-1 border border-gray-700">
                <div className="bg-blue-500 h-2 rounded-full transition-all duration-500 ease-out" style={{ width: `${progressPercent}%` }}></div>
              </div>
            </div>
            
            {/* 🎯 3단계 상태 시각화 카드 */}
            {wbsData.tasks.map((task: any) => {
              const isDone = task.status === 'DONE';
              const isInProgress = task.status === 'IN_PROGRESS';
              
              return (
                <div key={task.task_id} className={`p-3 rounded border transition-colors ${
                  isDone ? 'bg-gray-900 border-green-900/50 opacity-60' : 
                  isInProgress ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.2)]' : 
                  'bg-gray-800 border-gray-600'
                }`}>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-bold text-blue-300">{task.task_id}</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                      isDone ? 'bg-green-900 text-green-300' : 
                      isInProgress ? 'bg-blue-600 text-white animate-pulse' : 
                      'bg-gray-700 text-gray-300'
                    }`}>
                      {isDone ? "✅ DONE" : isInProgress ? "⚙️ IN PROGRESS" : "TODO"}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-gray-200 mb-1">{task.title}</h4>
                  <p className="text-xs text-gray-400 mb-3">{task.goal}</p>
                  
                  {!isDone && (
                    <button 
                      onClick={() => handleStartSprint(task)}
                      disabled={isStarting || !!state?.current_sprint_task_id}
                      className={`w-full text-xs font-bold py-2 rounded transition-colors ${
                        isInProgress 
                          ? 'bg-blue-800 text-blue-200 cursor-not-allowed' 
                          : 'bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white'
                      }`}
                    >
                      {isInProgress ? "▶️ 현재 작업 중 (대기 중)" : "🚀 이 스프린트 가동하기"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}