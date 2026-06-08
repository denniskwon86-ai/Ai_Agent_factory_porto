import { useFactoryStore } from '../store/useFactoryStore';
// 🚨 [수정 1] 복원된 HOTLInput 컴포넌트 임포트
import HOTLInput from './HOTLInput'; 

export default function TimelinePanel() {
  const logs = useFactoryStore((state) => state.logs);
  const completedAgents = useFactoryStore((state) => state.completed_agents);

  return (
    <div className="flex flex-col h-full bg-gray-900 overflow-hidden">
      <div className="p-4 border-b border-gray-700 bg-gray-800 shrink-0">
        <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          ⏱️ Execution Pipeline
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-xs">
        {logs.map((log, i) => (
          <div key={i} className="flex gap-3 border-b border-gray-800 pb-3 hover:bg-gray-800/50 p-2 rounded transition-colors">
            <span className="text-gray-500 shrink-0 mt-0.5">[{log.timestamp}]</span>
            <div className="flex flex-col gap-1">
              <span className="text-blue-400 font-bold">{log.type}</span>
              {log.node && (
                <span className="text-gray-300">
                  <span className="text-gray-500">Node: </span>
                  {log.node}
                </span>
              )}
              {log.task_id && (
                <span className="text-yellow-400/80">
                  <span className="text-gray-500">Task: </span>
                  {log.task_id}
                </span>
              )}
            </div>
          </div>
        ))}
        {logs.length === 0 && (
          <div className="text-gray-600 italic text-center mt-10 p-4 border border-dashed border-gray-700 rounded-lg">
            새 프로젝트 볼트에 진입했습니다.<br />기획을 입력하여 파이프라인을 가동해주세요.
          </div>
        )}
      </div>

      <div className="p-4 bg-gray-800 border-t border-gray-700 shrink-0">
        <div className="text-[10px] text-gray-500 mb-2 font-bold tracking-wider">✅ COMPLETED AGENTS</div>
        <div className="flex flex-wrap gap-2">
          {completedAgents.length > 0 ? (
            completedAgents.map((agent: string, i: number) => (
              <span key={i} className="px-2 py-1 bg-green-900/30 text-green-400 border border-green-700/50 rounded text-[10px] font-bold shadow-sm">
                {agent.toUpperCase()}
              </span>
            ))
          ) : (
            <span className="text-gray-600 text-xs italic">대기 중...</span>
          )}
        </div>
      </div>

      {/* 🚨 [수정 2] HOTLInput Embed: 인간의 통제권을 타임라인 로그 바로 아래에 일체화시켜 시야 분산을 막음 */}
      <HOTLInput />
    </div>
  );
}