import { useState, useEffect } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// 실행 스프린트 전체 파이프라인 정의 (노드 id ↔ 라벨 ↔ 배정 에이전트명)
const EXEC_PIPELINE = [
  { id: 'architect', label: 'Architect', agent: 'Architect' },
  { id: 'tech_lead', label: 'Tech Lead', agent: 'Tech_Lead' },
  { id: 'backend', label: 'Backend', agent: 'Backend' },
  { id: 'frontend', label: 'Frontend', agent: 'Frontend' },
  { id: 'codebuilder', label: 'Builder', agent: null as string | null },
  { id: 'reviewer', label: 'Supervisor', agent: null as string | null },
  { id: 'qa', label: 'QA', agent: 'QA' },
  { id: 'manualwriter', label: 'Manual', agent: null as string | null },
];

// 노드 id → Supervisor 채점 단계 키 (배지 표시용)
const STAGE_BY_NODE: Record<string, string> = {
  architect: 'ARCHITECTURE',
  tech_lead: 'TECH_SPEC',
  reviewer: 'CODE_REVIEW',
};

// 태스크에 배정된 required_agents 기준으로, 그 태스크가 실제 거치는 노드만 추려낸다.
const buildTaskPipeline = (requiredAgents: string[]) => {
  const ra = (requiredAgents || []).map((a) => a.toLowerCase());
  const has = (agent: string) => ra.some((r) => r.includes(agent.toLowerCase()));
  const hasCode = has('Backend') || has('Frontend');
  return EXEC_PIPELINE.filter((n) => {
    if (n.id === 'codebuilder') return hasCode;          // 코드가 있을 때만 빌더
    if (n.id === 'reviewer') return true;                 // Supervisor 게이트는 항상
    if (n.id === 'manualwriter') return has('Frontend');  // 프론트가 있을 때만 매뉴얼
    return n.agent ? has(n.agent) : false;                // 그 외엔 배정된 에이전트만
  });
};

// 토론·채점 단계(phase) → 표시 아이콘 (LIVE 배너용)
const PHASE_ICON: Record<string, string> = {
  draft: '✍️', critique: '🔍', revise: '♻️', scoring: '📊', scored: '✅',
};

export default function ControlPanel() {
  const [idea, setIdea] = useState("");
  const [feedback, setFeedback] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  
  const state = useFactoryStore((s) => s.state);
  const wbsData = useFactoryStore((s) => s.wbsData);
  const isWbsError = useFactoryStore((s) => s.isWbsError);
  const fetchWBS = useFactoryStore((s) => s.fetchWBS);
  const currentProjectId = useFactoryStore((s) => s.currentProjectId);
  const saveRelease = useFactoryStore((s) => s.saveRelease);
  
  const completedAgents = useFactoryStore((s) => s.completed_agents);
  const currentActivity = useFactoryStore((s) => s.currentActivity);
  const isWaitingForHuman = useFactoryStore((s) => s.state?.needs_revision);
  const clearSprintData = useFactoryStore((s) => s.clearSprintData);
  const activeSprintId = useFactoryStore((s) => s.activeSprintId);
  const setActiveSprintId = useFactoryStore((s) => s.setActiveSprintId);
  const hotlTaskId = useFactoryStore((s) => s.hotlTaskId);

  useEffect(() => {
    if (currentProjectId) fetchWBS();
  }, [fetchWBS, currentProjectId]);

  const totalTasks = wbsData?.tasks?.length || 0;
  const doneTasks = wbsData?.tasks?.filter((t: any) => t.status === 'DONE').length || 0;
  const progressPercent = totalTasks === 0 ? 0 : Math.round((doneTasks / totalTasks) * 100);

  const handleStartPlanning = async () => {
    if (!idea.trim()) return alert("💡 기획 아이디어를 입력해주세요.");
    if (!currentProjectId) return alert("프로젝트가 선택되지 않았습니다.");
    
    setIsStarting(true);
    const uniquePlanningId = `PLANNING_${Date.now()}`;
    setActiveSprintId(uniquePlanningId);
    
    try {
      await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: uniquePlanningId,
          project_state_payload: {
            schema_version: "5.1.0",
            project_name: currentProjectId,
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
    if (!confirm(`[${targetTask.task_id}] ${targetTask.title}\n해당 스프린트를 가동/재가동하시겠습니까?`)) return;
    if (!currentProjectId) return;
    
    setIsStarting(true);
    clearSprintData();
    setActiveSprintId(targetTask.task_id);

    try {
      await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: targetTask.task_id,
          project_state_payload: {
            ...(state || {}),
            schema_version: "5.1.0",
            project_name: wbsData.project_name || currentProjectId,
            current_sprint_task_id: targetTask.task_id,
            factory_mode: targetTask.task_id.startsWith('TASK_REV_') ? "REVISION" : "EXECUTION",
          }
        })
      });
    } catch (error) {
      console.error("스프린트 가동 실패:", error);
    } finally {
      setIsStarting(false);
    }
  };

  const handlePauseSprint = async (targetTask: any) => {
    if (!currentProjectId) return;
    try {
      await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: targetTask.task_id })
      });
      setActiveSprintId(null);
    } catch (error) {
      console.error("스프린트 일시정지 실패:", error);
    }
  };

  const handleSubmitFeedback = async () => {
    if (!feedback.trim()) return alert("수정 사항을 입력해주세요.");
    if (!currentProjectId) return;
    
    setIsStarting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/sprint/revision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback })
      });
      if (res.ok) {
        setFeedback("");
        fetchWBS();
      }
    } catch (error) {
      console.error("피드백 전송 실패:", error);
    } finally {
      setIsStarting(false);
    }
  };

  const renderPipelineTracker = (isPaused: boolean, task: any) => {
    // 이 태스크에 배정된 에이전트만으로 파이프라인 구성 (PMO Task별 매핑 반영)
    const pipeline = buildTaskPipeline(task?.required_agents || []);
    const currentAgentIdx = pipeline.findIndex(a => !completedAgents.map((ca: string) => ca.toLowerCase()).includes(a.id));

    // 단계별 최신 Supervisor 판정 맵 (criteria_log에서 추출)
    const verdictByStage: Record<string, string> = {};
    ((state?.criteria_log as any[]) || []).forEach((e) => { if (e?.stage) verdictByStage[e.stage] = e.verdict; });
    const supFb = state?.supervisor_feedback || '';
    const assigned = (task?.required_agents || []).join(', ') || '—';

    return (
      <div className={`mt-3 pt-3 border-t ${isPaused ? 'border-orange-900/50' : 'border-blue-900/50'}`}>
        <div className={`text-[10px] mb-1 font-bold tracking-wider ${isPaused ? 'text-orange-300' : 'text-blue-300'}`}>
          🤖 AGENT PIPELINE STATUS
        </div>
        <div className="text-[9px] text-gray-500 mb-3">배정 에이전트: <span className="text-gray-300">{assigned}</span></div>
        <div className="flex justify-between items-center relative px-2 mb-2">
          <div className="absolute top-2.5 left-3 right-3 h-[2px] bg-gray-700 -z-10"></div>
          {pipeline.map((agent, idx) => {
            const isCompleted = completedAgents.map((ca: string) => ca.toLowerCase()).includes(agent.id);
            const isCurrent = currentAgentIdx === idx || (currentAgentIdx === -1 && idx === pipeline.length - 1 && !isCompleted);
            const isBottleneck = isCurrent && isWaitingForHuman && !isPaused;

            let circleClass = "bg-gray-800 border-gray-600";
            let textClass = "text-gray-500";

            if (isCompleted) {
              circleClass = "bg-green-500 border-green-400 opacity-50"; textClass = "text-green-500 opacity-50";
            } else if (isPaused && isCurrent) {
              circleClass = "bg-orange-500 border-orange-400"; textClass = "text-orange-400 font-bold";
            } else if (isBottleneck) {
              circleClass = "bg-red-500 border-red-400 animate-pulse"; textClass = "text-red-400 font-bold";
            } else if (isCurrent) {
              circleClass = "bg-blue-500 border-blue-400 animate-pulse"; textClass = "text-blue-300 font-bold";
            }

            // Supervisor 채점 배지 (점수 + 판정색 + 토론 라운드)
            const stageKey = STAGE_BY_NODE[agent.id];
            const score = stageKey ? state?.stage_scores?.[stageKey] : undefined;
            const verdict = stageKey ? verdictByStage[stageKey] : undefined;
            const rounds = stageKey ? state?.debate_rounds_used?.[stageKey] : undefined;
            let badgeColor = 'text-gray-400';
            if (verdict === 'PASS') badgeColor = 'text-green-400';
            else if (verdict === 'REWORK') badgeColor = 'text-amber-400';
            else if (verdict === 'ROLLBACK') badgeColor = 'text-red-400';
            const hasBadge = stageKey && typeof score === 'number';

            return (
              <div key={agent.id} className="flex flex-col items-center gap-1 z-10 relative bg-gray-800">
                <div className={`w-5 h-5 rounded-full border-2 ${circleClass}`}></div>
                <span className={`text-[9px] absolute top-6 whitespace-nowrap ${textClass}`}>{agent.label}</span>
                {hasBadge && (
                  <span
                    className={`text-[8px] absolute top-11 whitespace-nowrap font-bold ${badgeColor}`}
                    title={verdict ? `${stageKey} 채점: ${(score as number).toFixed(2)} / ${verdict}${rounds ? ` · 토론 ${rounds}R` : ''}${verdict !== 'PASS' && supFb ? ` · ${supFb}` : ''}` : ''}
                  >
                    {(score as number).toFixed(1)}{rounds ? ` ×${rounds}` : ''} {verdict === 'PASS' ? '✓' : verdict ? '!' : ''}
                  </span>
                )}
              </div>
            );
          })}
        </div>
        <div className="h-12"></div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-gray-800 text-gray-200">
      <div className="p-4 border-b border-gray-700 bg-gray-900 shrink-0">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">⚙️ 팩토리 제어반</h2>
      </div>

      {currentActivity && (
        <div className="px-4 py-2 bg-blue-950/60 border-b border-blue-800 flex items-center gap-2 shrink-0">
          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse shrink-0"></span>
          <span className="text-[10px] text-red-300 font-bold tracking-widest shrink-0">LIVE</span>
          <span className="text-xs text-gray-100 truncate">
            {(PHASE_ICON[currentActivity.phase] || '⚙️')} {currentActivity.detail}
          </span>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4">
        {isWbsError && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500 rounded text-sm text-red-200">
            🚨 서버 통신 단절. 새로고침 해주세요.
          </div>
        )}

        {!wbsData ? (
          <div className="flex flex-col gap-2">
            <label className="text-sm font-semibold text-gray-400">💡 1. 신규 기획 (Track 0)</label>
            <textarea 
              value={idea} onChange={(e) => setIdea(e.target.value)} disabled={isStarting || activeSprintId !== null}
              placeholder="프로젝트 아이디어를 입력하세요..."
              className="w-full h-32 bg-gray-950 border border-gray-700 rounded p-3 text-sm focus:outline-none focus:border-blue-500 resize-none disabled:opacity-50"
            />
            <button 
              onClick={handleStartPlanning} disabled={isStarting || !idea.trim() || activeSprintId !== null}
              className="mt-2 w-full bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 font-bold py-3 rounded transition-colors"
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

            {/* 🚀 모든 단계 완료 시 — 최종 결과물 저장(배포) */}
            {progressPercent === 100 && currentProjectId && (
              <button
                onClick={async () => {
                  if (!confirm("이 프로젝트의 최종 결과물을 라이브러리에 저장(배포)하시겠습니까?")) return;
                  const rid = await saveRelease(currentProjectId);
                  if (rid) {
                    alert("✅ 최종 결과물이 라이브러리에 저장되었습니다.\n런처(프로젝트 선택) 화면의 '📦 결과물 라이브러리'에서 다시 실행/미리보기 할 수 있습니다.");
                  } else {
                    alert("❌ 결과물 저장에 실패했습니다.");
                  }
                }}
                className="w-full bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500 text-white font-bold py-3 rounded-lg shadow-lg transition-all border border-emerald-400/30 mb-1"
              >
                🚀 최종 결과물 저장 (배포)
              </button>
            )}

            {wbsData.tasks.map((task: any) => {
              const isDone = task.status === 'DONE';
              const isInProgress = task.status === 'IN_PROGRESS';
              const isRunning = isInProgress && activeSprintId === task.task_id;
              const isPaused = isInProgress && activeSprintId !== task.task_id;
              const isIdle = !isDone && !isInProgress;
              const isHotl = task.task_id === hotlTaskId;

              return (
                <div key={task.task_id} className={`p-3 rounded border transition-colors ${
                  isDone ? 'bg-gray-900 border-green-900/50 opacity-60' :
                  isRunning ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.2)]' :
                  isHotl ? 'bg-amber-900/20 border-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.2)]' :
                  isPaused ? 'bg-orange-900/20 border-orange-500' : 'bg-gray-800 border-gray-600'
                }`}>
                  <div className="flex justify-between items-center mb-2">
                    <span className={`text-xs font-bold ${isHotl ? 'text-amber-300' : isPaused ? 'text-orange-300' : 'text-blue-300'}`}>{task.task_id}</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                      isDone ? 'bg-green-900 text-green-300' :
                      isRunning ? 'bg-blue-600 text-white animate-pulse' :
                      isHotl ? 'bg-amber-500 text-white animate-pulse' :
                      isPaused ? 'bg-orange-600 text-white' : 'bg-gray-700 text-gray-300'
                    }`}>
                      {isDone ? "✅ DONE" : isRunning ? "⚙️ RUNNING" : isHotl ? "⚠️ HOTL REVIEW" : isPaused ? "⏸️ PAUSED" : "TODO"}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-gray-200 mb-1">{task.title}</h4>
                  <p className="text-xs text-gray-400 mb-3">{task.goal}</p>
                  
                  {isIdle && (
                    <button onClick={() => handleStartSprint(task)} disabled={isStarting || activeSprintId !== null} className="w-full text-xs font-bold py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white">🚀 신규 가동</button>
                  )}
                  {isPaused && (
                    <button onClick={() => handleStartSprint(task)} disabled={isStarting || activeSprintId !== null} className="w-full text-xs font-bold py-2 rounded bg-orange-600 hover:bg-orange-500 disabled:bg-gray-700 text-white">▶️ 이어서 재가동 (Resume)</button>
                  )}
                  {isRunning && (
                    <div className="flex flex-col gap-2">
                      <button onClick={() => handlePauseSprint(task)} className="w-full text-xs font-bold py-2 rounded bg-red-600 hover:bg-red-500 text-white">🛑 강제 일시정지 (Pause)</button>
                      {renderPipelineTracker(false, task)}
                    </div>
                  )}
                  {isPaused && renderPipelineTracker(true, task)}
                </div>
              );
            })}

            {doneTasks > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-700 flex flex-col gap-2">
                <label className="text-sm font-semibold text-yellow-500">🎯 3. 고객 리뷰 및 수정 지시 (Track 2)</label>
                <textarea 
                  value={feedback} onChange={(e) => setFeedback(e.target.value)} disabled={isStarting || activeSprintId !== null}
                  placeholder="디자인이나 기능 수정 요구사항을 입력하세요..."
                  className="w-full h-24 bg-gray-950 border border-gray-700 rounded p-3 text-sm focus:outline-none focus:border-yellow-500 resize-none disabled:opacity-50"
                />
                <button 
                  onClick={handleSubmitFeedback} disabled={isStarting || !feedback.trim() || activeSprintId !== null}
                  className="mt-1 w-full bg-yellow-600 hover:bg-yellow-500 disabled:bg-gray-700 font-bold py-3 rounded text-white"
                >
                  {isStarting ? "처리 중..." : "📨 피드백 백로그 발행 (WBS 추가)"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}