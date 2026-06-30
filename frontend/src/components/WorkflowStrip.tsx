import { useFactoryStore } from '../store/useFactoryStore';

// 전체 워크플로우 매크로 단계 (요구정의→기획→WBS→설계→구현→빌드→검수→QA→수용검수→매뉴얼)
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
  { key: 'SUPERVISOR', label: '수용검수' },
  { key: '__manual', label: '매뉴얼', agents: ['manualwriter'] },
];

// FLOW 인덱스 = 매크로 단계 순서. 에이전트/단계키 → FLOW 인덱스 매핑(프론티어 계산용).
const NODE_TO_IDX: Record<string, number> = {
  rfp_analyst: 0, master_pm: 1, master_pmo: 2, architect: 3, tech_lead: 4,
  backend: 5, frontend: 5, codebuilder: 6, reviewer: 7, qa: 8, supervisor: 9, manualwriter: 10,
};
const STAGE_TO_IDX: Record<string, number> = {
  RFP: 0, PLANNING: 1, PMO: 2, ARCHITECTURE: 3, TECH_SPEC: 4, EXECUTION: 5, BUILD: 6, CODE_REVIEW: 7, QA: 8, SUPERVISOR: 9, MANUAL: 10,
};

export default function WorkflowStrip() {
  const state = useFactoryStore((s) => s.state);
  const completed = useFactoryStore((s) => s.completed_agents).map((a: string) => a.toLowerCase());
  const activeSprintId = useFactoryStore((s) => s.activeSprintId);
  const hotlTaskId = useFactoryStore((s) => s.hotlTaskId);
  const scores = (state?.stage_scores || {}) as Record<string, number>;
  const current = state?.current_stage || '';
  const running = !!activeSprintId || !!hotlTaskId;

  // 도달한 가장 앞선 매크로 단계(프론티어). 누적 신호(완료 에이전트·current_stage·채점)를 모두 합산해
  // '단조'를 보장 → 더 뒤 단계가 done 인데 앞 단계가 active 인 모순을 구조적으로 제거.
  let frontier = -1;
  completed.forEach((a: string) => { if (NODE_TO_IDX[a] != null) frontier = Math.max(frontier, NODE_TO_IDX[a]); });
  if (current && STAGE_TO_IDX[current] != null) frontier = Math.max(frontier, STAGE_TO_IDX[current]);
  Object.keys(scores).forEach((k) => { const idx = FLOW.findIndex((f) => f.key === k); if (idx >= 0) frontier = Math.max(frontier, idx); });

  return (
    <div className="bg-gray-800 border-b border-gray-700 px-4 py-2 flex items-center gap-0.5 overflow-x-auto shrink-0">
      <span className="text-[10px] text-gray-500 font-bold tracking-wider mr-2 shrink-0">🔭 WORKFLOW</span>
      {FLOW.map((step, i) => {
        // 프론티어 이전 = 완료, 프론티어 = (가동 중이면 active, 아니면 완료), 이후 = 대기
        const done = i < frontier || (i === frontier && !running);
        const active = running && i === frontier;
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
