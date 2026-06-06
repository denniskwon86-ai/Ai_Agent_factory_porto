import { useState, useEffect } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const PIPELINE = [
  { id: 'architect', label: 'Architect' },
  { id: 'tech_lead', label: 'Tech Lead' },
  { id: 'backend_worker', label: 'Backend' },
  { id: 'code_builder', label: 'Builder' },
  { id: 'reviewer', label: 'Reviewer' }
];

export default function ControlPanel() {
  const [idea, setIdea] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  
  const state = useFactoryStore((s) => s.state);
  const wbsData = useFactoryStore((s) => s.wbsData);
  const isWbsError = useFactoryStore((s) => s.isWbsError);
  const fetchWBS = useFactoryStore((s) => s.fetchWBS);
  
  const completedAgents = useFactoryStore((s) => s.completed_agents);
  const isWaitingForHuman = useFactoryStore((s) => s.state?.needs_revision);
  const clearSprintData = useFactoryStore((s) => s.clearSprintData);

  useEffect(() => {
    fetchWBS();
  }, [fetchWBS]);

  const totalTasks = wbsData?.tasks?.length || 0;
  const doneTasks = wbsData?.tasks?.filter((t: any) => t.status === 'DONE').length || 0;
  const progressPercent = totalTasks === 0 ? 0 : Math.round((doneTasks / totalTasks) * 100);

  const handleStartPlanning = async () => {
    if (!idea.trim()) {
      alert("💡 기획 아이디어를 입력해주세요.");
      return;
    }
    setIsStarting(true);
    
    // 🚨 [원인 해결 2] LangGraph 쓰레드가 옛날 기억을 살려내지 못하도록 매번 고유한 타임스탬프 ID 부여
    const uniquePlanningId = `PLANNING_${Date.now()}`;
    
    try {
      await fetch(`${API_BASE_URL}/api/v1/factory/sprint/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: uniquePlanningId,
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
    clearSprintData();

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

  const renderPipelineTracker = () => {
    const currentAgentIdx = PIPELINE.findIndex(a => !completedAgents.map(ca => ca.toLowerCase()).includes(a.id));

    return (
      <div className="mt-3 pt-3 border-t border-blue-900/50">
        <div className="text-[10px] text-blue-300 mb-3 font-bold tracking-wider">🤖 AGENT PIPELINE STATUS</div>
        <div className="flex justify-between items-center relative px-2 mb-2">
          <div className="absolute top-2.5 left-3 right-3 h-[2px] bg-gray-700 -z-10"></div>
          
          {PIPELINE.map((agent, idx) => {
            const isCompleted = completedAgents.map(ca => ca.toLowerCase()).includes(agent.id);
            const isCurrent = currentAgentIdx === idx || (currentAgentIdx === -1 && idx === PIPELINE.length - 1 && !isCompleted);
            const isBottleneck = isCurrent && isWaitingForHuman;

            let circleClass = "bg-gray-800 border-gray-600";
            let textClass = "text-gray-500";

            if (isCompleted) {
              circleClass = "bg-green-500 border-green-400";
              textClass = "text-green-400";
            } else if (isBottleneck) {
              circleClass = "bg-red-500 border-red-400 animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.8)]";
              textClass = "text-red-400 font-bold";
            } else if (isCurrent) {
              circleClass = "bg-blue-500 border-blue-400 animate-pulse shadow-[0_0_10px_rgba(59,130,246,0.8)]";
              textClass = "text-blue-300 font-bold";
            }

            return (
              <div key={agent.id} className="flex flex-col items-center gap-1 z-10 relative bg-blue-900/20">
                <div className={`w-5 h-5 rounded-full border-2 ${circleClass}`}></div>
                <span className={`text-[9px] absolute top-6 whitespace-nowrap ${textClass}`}>
                  {agent.label}
                </span>
              </div>
            );
          })}
        </div>
        <div className="h-4"></div> 
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-gray-800 text-gray-200">
      <div className="p-4 border-b border-gray-700 bg-gray-900 shrink-0">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          ⚙️ 팩토리 제어반
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {isWbsError && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-sm text-red-200">
            🚨 백엔드 서버와의 통신 단절. 서버 재가동 후 새로고침 해주세요.
          </div>
        )}

        {!wbsData ? (
          <div className="flex flex-col gap-2">
            <label className="text-sm font-semibold text-gray-400">💡 1. 신규 기획 (Track 0)</label>
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
              className="mt-2 w-full bg-purple-600 hover:bg-purple-500 font-bold py-3 rounded transition-colors"
            >
              {isStarting ? "가동 중..." : "🎯 기획 및 WBS 분할 가동"}
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col mb-2 border-b border-gray-700 pb-3">
              <div className="flex justify-between items-end mb-1">
                <label className="text-sm font-semibold text-gray-400">📋 2. 일일 스프린트 통제</label>
                <span className="text-xs font-bold text-blue-400">진척률: {progressPercent}% ({doneTasks}/{totalTasks})</span>
              </div>
              <div className="w-full bg-gray-950 rounded-full h-2 mt-1 border border-gray-700">
                <div className="bg-blue-500 h-2 rounded-full transition-all duration-500 ease-out" style={{ width: `${progressPercent}%` }}></div>
              </div>
            </div>
            
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
                  
                  {!isDone && !isInProgress && (
                    <button 
                      onClick={() => handleStartSprint(task)}
                      disabled={isStarting || !!state?.current_sprint_task_id}
                      className="w-full text-xs font-bold py-2 rounded transition-colors bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white"
                    >
                      🚀 이 스프린트 가동하기
                    </button>
                  )}

                  {isInProgress && renderPipelineTracker()}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}