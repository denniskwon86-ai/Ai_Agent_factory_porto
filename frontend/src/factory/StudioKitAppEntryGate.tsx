import { useEffect, useMemo, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { createKitAppEntryFlow } from './studioKitAppEntry';
import type { KitAppEntry, KitAppEntryState } from './studioKitAppEntry';

export function KitAppEntryStatus({ state, onRetry }: { state: KitAppEntryState; onRetry: () => void }) {
  if (state.phase === 'AVAILABLE' && state.data) return <section aria-label="업무 앱 조회 확인">
    <h2>{state.data.app_label}</h2>
    <p role="status">현재 회사·권한에서 조회 가능한 업무 앱입니다.</p>
    <p>만들기·실행·게시 가능 여부와 데이터 준비 상태는 각각의 단계에서 다시 확인합니다.</p>
  </section>;
  if (state.phase === 'BLOCKED') return <section aria-label="업무 앱 확인 필요">
    <p role="alert">{state.error?.message || '업무 앱을 확인하지 못했습니다.'}</p>
    <button type="button" onClick={onRetry}>현재 회사에서 다시 확인</button>
  </section>;
  return <p role="status" aria-live="polite">업무 앱의 회사·조회 권한을 확인하고 있습니다.</p>;
}

/** 확인 전·문맥 무효화 후에는 자식을 만들지 않는다. 조회 가능을 실행 승인으로 바꾸지 않는다. */
export function StudioKitAppEntryGate({ instanceId, appId, children }: {
  instanceId: string; appId: string; children?: (entry: KitAppEntry) => ReactNode;
}) {
  const flow = useMemo(() => createKitAppEntryFlow(instanceId, appId), [instanceId, appId]);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  useEffect(() => { flow.activate(); void flow.load(); return () => flow.dispose(); }, [flow]);
  if (state.phase === 'AVAILABLE' && state.data && flow.isCurrent()) {
    return children ? children(state.data) : <KitAppEntryStatus state={state} onRetry={() => void flow.load()} />;
  }
  const safe = state.phase === 'AVAILABLE' ? { ...state, phase: 'BLOCKED' as const, data: null, error: null } : state;
  return <KitAppEntryStatus state={safe} onRetry={() => void flow.load()} />;
}
