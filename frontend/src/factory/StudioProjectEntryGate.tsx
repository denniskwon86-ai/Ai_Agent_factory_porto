import { useEffect, useMemo, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { createProjectEntryFlow } from './studioProjectEntry';
import type { ProjectEntry, ProjectEntryState } from './studioProjectEntry';

export function ProjectEntryStatus({ state, onRetry }: { state: ProjectEntryState; onRetry: () => void }) {
  if (state.phase === 'AVAILABLE' && state.data) return <section aria-label="프로젝트 조회 확인">
    <h2>{state.data.project_name}</h2>
    <p role="status">현재 회사·권한에서 조회 가능한 프로젝트입니다.</p>
    <p>실행·게시 가능 여부와 데이터 준비 상태는 각각의 단계에서 다시 확인합니다.</p>
  </section>;
  if (state.phase === 'BLOCKED') return <section aria-label="프로젝트 확인 필요">
    <p role="alert">{state.error?.message || '프로젝트를 확인하지 못했습니다.'}</p>
    <button type="button" onClick={onRetry}>현재 회사에서 다시 확인</button>
  </section>;
  return <p role="status" aria-live="polite">프로젝트의 회사·조회 권한을 확인하고 있습니다.</p>;
}

/** 전역 mount는 다음 배치. 확인 전/문맥 무효화 후에는 자식 Studio를 만들지 않는다. */
export function StudioProjectEntryGate({ projectId, childId = '', requireMega = false, children }: {
  projectId: string; childId?: string; requireMega?: boolean;
  children?: (entry: ProjectEntry) => ReactNode;
}) {
  //: ★ [MEGA-ENTRY-01] 자식이 바뀌면 **확인도 다시 한다** — 같은 부모라도 다른 자식은
  //:   다른 질문이다. `childId` 를 의존성에서 빼면 옛 확인 결과로 새 자식을 연다.
  //: ★ [FIX1 · 보완1] `requireMega` 도 **질문의 일부**다. 대상 종류가 바뀌면 이전
  //:   flow·응답을 버린다 — 일반 프로젝트로 확인해 둔 결과로 메가 링크를 열면 안 된다.
  const flow = useMemo(() => createProjectEntryFlow(projectId, childId, requireMega),
    [projectId, childId, requireMega]);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  useEffect(() => { flow.activate(); void flow.load(); return () => flow.dispose(); }, [flow]);
  if (state.phase === 'AVAILABLE' && state.data && flow.isCurrent()) {
    return children ? children(state.data) : <ProjectEntryStatus state={state} onRetry={() => void flow.load()} />;
  }
  const safe = state.phase === 'AVAILABLE' ? { ...state, phase: 'BLOCKED' as const, data: null, error: null } : state;
  return <ProjectEntryStatus state={safe} onRetry={() => void flow.load()} />;
}
