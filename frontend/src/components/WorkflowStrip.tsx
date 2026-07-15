import { useFactoryStore } from '../store/useFactoryStore';

const DEFAULT_FLOW: { key: string; label: string; agents?: string[] }[] = [
  { key: 'RFP', label: '요구정의' },
  { key: 'PLANNING', label: '기획' },
  { key: 'UI_DESIGN', label: 'UI디자인' },
  { key: 'VISION_QA', label: '비전QA' },
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

const DEFAULT_NODE_TO_IDX: Record<string, number> = {
  rfp_analyst: 0, master_pm: 1, uidesigner: 2, visionqa: 3, master_pmo: 4, architect: 5, tech_lead: 6,
  backend: 7, frontend: 7, codebuilder: 8, reviewer: 9, qa: 10, supervisor: 11, manualwriter: 12,
};
const DEFAULT_STAGE_TO_IDX: Record<string, number> = {
  RFP: 0, PLANNING: 1, UI_DESIGN: 2, VISION_QA: 3, PMO: 4, ARCHITECTURE: 5, TECH_SPEC: 6, EXECUTION: 7, BUILD: 8, CODE_REVIEW: 9, QA: 10, SUPERVISOR: 11, MANUAL: 12,
};

export default function WorkflowStrip() {
  const state = useFactoryStore((s) => s.state);
  const completed = useFactoryStore((s) => s.completed_agents).map((a: string) => a.toLowerCase());
  const activeSprintId = useFactoryStore((s) => s.activeSprintId);
  const hotlTaskId = useFactoryStore((s) => s.hotlTaskId);
  const scores = (state?.stage_scores || {}) as Record<string, number>;
  const current = state?.current_stage || '';
  const running = !!activeSprintId || !!hotlTaskId;

  const currentTemplateData = useFactoryStore((s) => s.currentTemplateData);

  let FLOW = DEFAULT_FLOW;
  let NODE_TO_IDX = DEFAULT_NODE_TO_IDX;
  let STAGE_TO_IDX = DEFAULT_STAGE_TO_IDX;

  if (currentTemplateData && currentTemplateData.agents && currentTemplateData.id !== 'default') {
    const agents = [...currentTemplateData.agents].sort((a: any, b: any) => a.order - b.order);
    FLOW = agents.map((a: any) => ({
      key: a.stage || a.id.toUpperCase(),
      label: a.name_ko || a.id
    }));
    NODE_TO_IDX = {};
    STAGE_TO_IDX = {};
    agents.forEach((a: any, i: number) => {
      NODE_TO_IDX[a.id.toLowerCase()] = i;
      STAGE_TO_IDX[a.stage || a.id.toUpperCase()] = i;
    });
  }

  // 1. 프론티어(가장 멀리 도달한 진도)는 여전히 active 상태 추론의 폴백용으로 계산합니다.
  let frontier = -1;
  completed.forEach((a: string) => { if (NODE_TO_IDX[a] != null) frontier = Math.max(frontier, NODE_TO_IDX[a]); });
  if (current && STAGE_TO_IDX[current] != null) frontier = Math.max(frontier, STAGE_TO_IDX[current]);
  Object.keys(scores).forEach((k) => { const idx = FLOW.findIndex((f) => f.key === k); if (idx >= 0) frontier = Math.max(frontier, idx); });
  if (hotlTaskId && NODE_TO_IDX[hotlTaskId.toLowerCase()] != null) frontier = Math.max(frontier, NODE_TO_IDX[hotlTaskId.toLowerCase()]);

  return (
    <div className="bg-gray-800 border-b border-gray-700 px-4 py-2 flex items-center gap-0.5 overflow-x-auto shrink-0">
      <span className="text-[10px] text-gray-500 font-bold tracking-wider mr-2 shrink-0">🔭 WORKFLOW</span>
      {FLOW.map((step, i) => {
        // 2. 정확한 상태 매핑 (단조 증가 꼼수 제거, 개별 에이전트 완료/활성 상태 명확히 추적)
        const agentsForStep = Object.keys(NODE_TO_IDX).filter(k => NODE_TO_IDX[k] === i);
        
        // [완료 조건]: 이 단계에 속한 에이전트 중 하나라도 completed_agents 에 있거나, 채점(scores) 기록이 있는 경우
        const isCompletedExact = agentsForStep.some(a => completed.includes(a)) || scores[step.key] != null;
        
        // [활성 조건]: 
        // A) 멈춰있는 HOTL(인간개입) 태스크가 현재 단계에 속하는 경우
        // B) 현재 단계(current_stage)가 정확히 일치하는 경우
        // C) 정확한 추적이 어려울 때 가장 프론티어(frontier)에 도달해 있으면서 아직 완료되지 않은 경우
        let isActiveExact = false;
        if (running) {
          if (hotlTaskId && agentsForStep.includes(hotlTaskId.toLowerCase())) isActiveExact = true;
          else if (current && STAGE_TO_IDX[current] === i) isActiveExact = true;
          else if (i === frontier && !isCompletedExact) isActiveExact = true;
        }

        const done = isCompletedExact;
        const active = isActiveExact;

        const cls = active
          ? 'bg-blue-600 text-white animate-pulse border border-blue-400'
          : done
          ? 'bg-green-900/40 text-green-300 border border-green-700/50'
          : 'bg-gray-900 text-gray-500 border border-gray-700';
        return (
          // key 는 인덱스를 붙여 고유화 — 커스텀 템플릿에서 두 에이전트가 같은 stage(예: EXECUTION)를
          // 공유하면 step.key 만으로는 중복되어 React 경고가 난다(step.key 자체는 scores 조회에 계속 사용).
          <div key={`${step.key}__${i}`} className="flex items-center shrink-0">
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
