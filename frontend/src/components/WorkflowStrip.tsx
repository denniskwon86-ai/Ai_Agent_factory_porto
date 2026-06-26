import { useFactoryStore } from '../store/useFactoryStore';

// 전체 워크플로우 매크로 단계 (요구정의→기획→WBS→설계→구현→빌드→검수→QA→매뉴얼)
const FLOW: { key: string; label: string; agents?: string[] }[] = [
  { key: 'RFP', label: '요구정의' },
  { key: 'PLANNING', label: '기획' },
  { key: 'PMO', label: 'WBS분할' },
  { key: 'ARCHITECTURE', label: '아키텍처' },
  { key: 'TECH_SPEC', label: '기술설계' },
  { key: '__code', label: '구현', agents: ['backend', 'frontend'] },
  { key: '__build', label: '빌드', agents: ['codebuilder'] },
  { key: 'CODE_REVIEW', label: '검수' },
  { key: 'QA', label: 'QA' },
  { key: '__manual', label: '매뉴얼', agents: ['manualwriter'] },
];

export default function WorkflowStrip() {
  const state = useFactoryStore((s) => s.state);
  const completed = useFactoryStore((s) => s.completed_agents).map((a: string) => a.toLowerCase());
  const scores = (state?.stage_scores || {}) as Record<string, number>;
  const current = state?.current_stage || '';

  const isDone = (step: { key: string; agents?: string[] }) =>
    step.agents ? step.agents.some((a) => completed.includes(a)) : step.key in scores;
  const isActive = (step: { key: string }) => !!current && step.key === current;

  return (
    <div className="bg-gray-800 border-b border-gray-700 px-4 py-2 flex items-center gap-0.5 overflow-x-auto shrink-0">
      <span className="text-[10px] text-gray-500 font-bold tracking-wider mr-2 shrink-0">🔭 WORKFLOW</span>
      {FLOW.map((step, i) => {
        const done = isDone(step);
        const active = isActive(step);
        const cls = active
          ? 'bg-blue-600 text-white animate-pulse border border-blue-400'
          : done
          ? 'bg-green-900/40 text-green-300 border border-green-700/50'
          : 'bg-gray-900 text-gray-500 border border-gray-700';
        return (
          <div key={step.key} className="flex items-center shrink-0">
            <span className={`px-2 py-1 rounded text-[10px] font-bold whitespace-nowrap ${cls}`}>
              {done && !active ? '✓ ' : ''}{step.label}
            </span>
            {i < FLOW.length - 1 && <span className="text-gray-600 mx-0.5 text-[10px]">›</span>}
          </div>
        );
      })}
    </div>
  );
}
