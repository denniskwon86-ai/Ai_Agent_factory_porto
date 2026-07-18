import { useEffect, useMemo, useRef } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';
import HOTLInput from './HOTLInput';

// 토론·채점 단계(phase) → 아이콘/색상
const PHASE_META: Record<string, { icon: string; color: string }> = {
  draft:           { icon: '✍️', color: 'text-blue-300' },
  critique:        { icon: '🔍', color: 'text-purple-300' },
  critique_result: { icon: '🔎', color: 'text-purple-200' },
  revise:          { icon: '♻️', color: 'text-amber-300' },
  scoring:         { icon: '📊', color: 'text-cyan-300' },
  scored:          { icon: '🧭', color: 'text-green-300' },
};

function verdictBadge(v?: string) {
  if (v === 'PASS') return { label: '통과', cls: 'text-green-300 border-green-700/50 bg-green-900/40' };
  if (v === 'REWORK') return { label: '재작업', cls: 'text-amber-300 border-amber-700/50 bg-amber-900/40' };
  if (v === 'ROLLBACK') return { label: '회송', cls: 'text-red-300 border-red-700/50 bg-red-900/40' };
  return { label: v || '-', cls: 'text-gray-300 border-gray-700/50 bg-gray-800' };
}

const NODE_KO_MAP: Record<string, string> = {
  FORECAST: "수요 예측",
  MRP: "자재 수급",
  SCHEDULING: "생산 스케줄링",
  INVENTORY: "재고/물류 관리",
  REVIEW: "검수 및 리뷰",
  IDEA: "초안 기획",
  DESIGN: "시스템 설계",
  DEV: "기능 개발",
  TEST: "품질 테스트",
  DEPLOY: "최종 배포"
};

export default function TimelinePanel() {
  const feed = useFactoryStore((s) => s.supervisorFeed);
  const logs = useFactoryStore((s) => s.logs);
  const completedAgents = useFactoryStore((s) => s.completed_agents);
  const endRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // 토론/채점 내레이션 + 노드 완료 마일스톤을 시간순으로 병합
  // useMemo: SSE 이벤트마다 O(n log n) 재정렬이 모든 렌더에서 반복되던 낭비 제거
  const items = useMemo(() => [
    ...feed.map((e: any) => ({ kind: 'feed', t: e.ts || '', ...e })),
    ...logs
      .filter((l: any) => ['NODE_COMPLETED', 'HOTL_PAUSED', 'SPRINT_COMPLETED'].includes(l.type))
      .map((l: any) => ({ kind: 'milestone', t: l.timestamp || '', type: l.type, node: l.node, task_id: l.task_id })),
  ].sort((a: any, b: any) => String(a.t).localeCompare(String(b.t))), [feed, logs]);

  useEffect(() => {
    // 사용자가 위로 스크롤해 과거 기록을 보는 중이면 강제 스크롤로 빼앗지 않는다
    const el = listRef.current;
    const nearBottom = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items.length]);

  return (
    <div className="flex flex-col h-full bg-gray-900 overflow-hidden">
      <div className="p-4 border-b border-gray-700 bg-gray-800 shrink-0">
        <h2 className="text-sm font-bold text-gray-200 tracking-wider flex items-center gap-2">
          🧭 Supervisor Console
          <span className="text-[10px] text-gray-500 font-normal">— 모든 에이전트를 관장하는 자비스</span>
        </h2>
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto p-4 space-y-2 text-xs">
        {items.map((e: any, i: number) => {
          if (e.kind === 'milestone') {
            const nodeName = NODE_KO_MAP[e.node] || e.node;
            let txt = `${nodeName} 단계 완료`;
            if (e.type === 'HOTL_PAUSED') txt = 'HOTL (전문가 개입) 대기 중';
            if (e.type === 'SPRINT_COMPLETED') txt = '스프린트 완료';
            const ico = e.type === 'HOTL_PAUSED' ? '⏸️' : e.type === 'SPRINT_COMPLETED' ? '🏁' : '▸';
            return (
              <div key={i} className="flex gap-2 items-center text-[11px] text-gray-500 pl-1">
                <span className="shrink-0">{ico}</span>
                <span>{txt}</span>
              </div>
            );
          }
          const pm = PHASE_META[e.phase] || { icon: '•', color: 'text-gray-400' };
          const failed = Array.isArray(e.meta?.checks) ? e.meta.checks.filter((c: any) => !c.pass) : [];
          return (
            <div key={i} className="flex gap-2 border-b border-gray-800/60 pb-2">
              <span className="shrink-0 mt-0.5">{pm.icon}</span>
              <div className="flex flex-col gap-1 min-w-0 flex-1">
                <span className={`${pm.color} leading-relaxed`}>{e.detail}</span>

                {e.phase === 'scored' && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-bold ${verdictBadge(e.meta?.verdict).cls}`}>
                      {verdictBadge(e.meta?.verdict).label} · {e.meta?.score}
                    </span>
                    {Object.entries(e.meta?.per_check || {}).map(([k, v]: any, j: number) => (
                      <span key={j} className="px-1.5 py-0.5 rounded bg-gray-800 border border-gray-700 text-[9px] text-gray-400">
                        {k} {v}
                      </span>
                    ))}
                  </div>
                )}

                {e.phase === 'critique_result' && failed.length > 0 && (
                  <div className="flex flex-col gap-0.5 mt-0.5 pl-2 border-l-2 border-purple-800/50">
                    {failed.slice(0, 4).map((c: any, j: number) => (
                      <span key={j} className="text-[10px] text-gray-400 leading-snug">
                        <span className="text-purple-300">[{c.id}]</span> {c.evidence}
                        {c.severity && <span className="text-red-400/70"> ({c.severity})</span>}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {items.length === 0 && (
          <div className="text-gray-600 italic text-center mt-10 p-4 border border-dashed border-gray-700 rounded-lg">
            슈퍼바이저 대기 중.<br />기획을 가동하면 토론·평가 과정을 실시간으로 중계합니다.
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="px-4 py-3 bg-gray-800 border-t border-gray-700 shrink-0">
        <div className="text-[10px] text-gray-500 mb-2 font-bold tracking-wider">✅ COMPLETED AGENTS ({completedAgents.length})</div>
        {/* 높이 제한 + 내부 스크롤 — 길어져도 피드·승인버튼을 밀어내지 않음 */}
        <div className="flex flex-wrap gap-2 max-h-16 overflow-y-auto pr-1">
          {completedAgents.length > 0 ? (
            completedAgents.map((agent: string, i: number) => (
              <span key={i} className="px-2 py-1 bg-green-900/30 text-green-400 border border-green-700/50 rounded text-[10px] font-bold shadow-sm h-fit">
                {agent.toUpperCase()}
              </span>
            ))
          ) : (
            <span className="text-gray-600 text-xs italic">대기 중...</span>
          )}
        </div>
      </div>

      <HOTLInput />
    </div>
  );
}
