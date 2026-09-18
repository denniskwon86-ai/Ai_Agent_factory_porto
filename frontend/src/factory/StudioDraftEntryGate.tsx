import { useEffect, useMemo, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { createDraftEntryFlow } from './studioDraftEntry';
import type { DraftEntry, DraftEntryState } from './studioDraftEntry';

export function DraftEntryStatus({ state, onRetry }: { state: DraftEntryState; onRetry: () => void }) {
  if (state.phase === 'AVAILABLE' && state.data) return <section aria-label="초안 조회 확인">
    <h2>{state.data.revision}판 요구사항 초안</h2>
    <p role="status">현재 회사·권한에서 조회 가능한 초안입니다.</p>
    <p>편집·승인·프로젝트 승격 가능 여부는 각각의 단계에서 다시 확인합니다.</p>
  </section>;
  if (state.phase === 'BLOCKED') return <section aria-label="초안 확인 필요">
    <p role="alert">{state.error?.message || '초안을 확인하지 못했습니다.'}</p>
    <button type="button" onClick={onRetry}>현재 회사에서 다시 확인</button>
  </section>;
  return <p role="status" aria-live="polite">초안의 회사·조회 권한을 확인하고 있습니다.</p>;
}

/** 확인 전/문맥 무효화 후에는 자식을 만들지 않는다 — `project`·`kit_app` 과 같은 규칙이다. */
export function StudioDraftEntryGate({ draftId, draftKind, revision, children }: {
  draftId: string; draftKind: string; revision: number;
  children?: (entry: DraftEntry) => ReactNode;
}) {
  //: ★ 셋 다 **질문의 일부**다. 하나라도 바뀌면 이전 flow·응답을 버린다 — 옛 확인
  //:   결과로 다른 초안·다른 판본을 여는 길을 만들지 않는다.
  const flow = useMemo(() => createDraftEntryFlow(draftId, draftKind, revision),
    [draftId, draftKind, revision]);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  useEffect(() => { flow.activate(); void flow.load(); return () => flow.dispose(); }, [flow]);
  if (state.phase === 'AVAILABLE' && state.data && flow.isCurrent()) {
    return children ? children(state.data) : <DraftEntryStatus state={state} onRetry={() => void flow.load()} />;
  }
  const safe = state.phase === 'AVAILABLE' ? { ...state, phase: 'BLOCKED' as const, data: null, error: null } : state;
  return <DraftEntryStatus state={safe} onRetry={() => void flow.load()} />;
}
