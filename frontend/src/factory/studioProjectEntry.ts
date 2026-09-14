// B6 단건 진입 확인. 조회 가능은 실행·게시·준비 완료를 뜻하지 않는다.
import { apiFetch, getEnterpriseContext } from '../lib/api';
import { studioIdentityKey } from './studioInputMemory';

export type ProjectEntry = {
  project_id: string; project_name: string; runtime_document_version: '1.0' | '2.0';
  ownership: { tenant_id: string; enterprise_scope_id: string; entity_mode: string };
  viewing_context: { tenant_id: string; scope_node_id: string; entity_mode: string };
};
export class ProjectEntryError extends Error {
  readonly status: number; readonly reasonCode: string;
  constructor(message: string, status = 503, reasonCode = 'ENTRY_UNAVAILABLE') {
    super(message); this.name = 'ProjectEntryError'; this.status = status; this.reasonCode = reasonCode;
  }
}
const contextChanged = () => new ProjectEntryError('회사 또는 사용자가 바뀌었습니다. 현재 문맥에서 다시 확인하세요.', 409, 'ENTRY_CONTEXT_CHANGED');
const malformed = () => new ProjectEntryError('프로젝트 확인 응답이 올바르지 않습니다. 다시 확인하세요.', 503, 'ENTRY_RESPONSE_INVALID');
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw malformed();
  return value as Record<string, unknown>;
}
const text = (value: unknown, allowEmpty = false): value is string => typeof value === 'string'
  && (allowEmpty || value.trim().length > 0) && value.length <= 2000;

export async function readProjectEntry(projectId: string, signal?: AbortSignal): Promise<ProjectEntry> {
  if (!/^[A-Za-z0-9_-]{1,160}$/.test(projectId)) throw new ProjectEntryError('프로젝트 링크를 확인하세요.', 422, 'ENTRY_INVALID_TARGET');
  const identity = studioIdentityKey(), selected = { ...getEnterpriseContext() };
  const current = () => { if (signal?.aborted || identity !== studioIdentityKey()) throw contextChanged(); };
  current();
  try {
    const response = await apiFetch(`/api/v1/factory/${encodeURIComponent(projectId)}/entry-metadata`, {
      method: 'GET', cache: 'no-store', signal,
    });
    current();
    const raw: unknown = await response.json().catch(() => null);
    current();
    if (!response.ok) {
      // 비가시 자원의 서버 상세/원문은 화면 오류에 옮기지 않는다.
      const message = response.status === 401 ? '로그인이 필요합니다.'
        : response.status === 403 || response.status === 404 ? '현재 회사·권한에서 프로젝트를 찾을 수 없습니다.'
        : response.status === 409 ? '확인 중 프로젝트 문맥이 바뀌었습니다. 다시 확인하세요.'
        : '프로젝트를 확인하지 못했습니다. 잠시 후 다시 확인하세요.';
      throw new ProjectEntryError(message, response.status, `ENTRY_HTTP_${response.status}`);
    }
    const envelope = object(raw), row = object(envelope.data);
    const owner = object(row.ownership), view = object(row.viewing_context);
    if (envelope.status !== 'success' || row.project_id !== projectId || !text(row.project_name)
        || (row.runtime_document_version !== '1.0' && row.runtime_document_version !== '2.0')
        || !text(owner.tenant_id) || !text(owner.enterprise_scope_id, true) || !text(owner.entity_mode)
        || !text(view.tenant_id) || !text(view.scope_node_id, true) || !text(view.entity_mode)
        || owner.tenant_id !== view.tenant_id || owner.entity_mode !== view.entity_mode) throw malformed();
    if ((selected.tenantId && selected.tenantId !== view.tenant_id)
        || (selected.scopeNodeId && selected.scopeNodeId !== view.scope_node_id)
        || (selected.entityMode && selected.entityMode !== view.entity_mode)) throw contextChanged();
    // 전체 상태/권한 플래그 등 확장 필드는 복사하지 않는다. 범위 계층은 서버가 판정한다.
    return { project_id: projectId, project_name: row.project_name,
      runtime_document_version: row.runtime_document_version as ProjectEntry['runtime_document_version'],
      ownership: { tenant_id: owner.tenant_id, enterprise_scope_id: owner.enterprise_scope_id, entity_mode: owner.entity_mode },
      viewing_context: { tenant_id: view.tenant_id, scope_node_id: view.scope_node_id, entity_mode: view.entity_mode } };
  } catch (error) {
    current();
    if (error instanceof ProjectEntryError) throw error;
    throw new ProjectEntryError('연결을 확인하지 못했습니다. 입력을 변경하지 않고 다시 조회할 수 있습니다.', 503, 'ENTRY_CONNECTION_FAILED');
  }
}

export type ProjectEntryState = {
  phase: 'IDLE' | 'LOADING' | 'AVAILABLE' | 'BLOCKED'; data: ProjectEntry | null; error: ProjectEntryError | null;
};
const events = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
export function createProjectEntryFlow(projectId: string) {
  let state: ProjectEntryState = { phase: 'IDLE', data: null, error: null };
  let active = false, generation = 0, identity = '', controller: AbortController | null = null;
  const listeners = new Set<() => void>();
  const emit = (next: ProjectEntryState) => { state = next; for (const listener of listeners) listener(); };
  const invalidate = () => {
    generation++; controller?.abort(); controller = null;
    emit({ phase: 'BLOCKED', data: null, error: contextChanged() });
  };
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    isCurrent: () => active && identity === studioIdentityKey(),
    activate() {
      if (active) return;
      active = true;
      if (typeof window !== 'undefined') for (const event of events) window.addEventListener(event, invalidate);
    },
    dispose() {
      active = false; generation++; controller?.abort(); controller = null;
      if (typeof window !== 'undefined') for (const event of events) window.removeEventListener(event, invalidate);
      emit({ phase: 'IDLE', data: null, error: null });
    },
    invalidate,
    async load() {
      if (!active) return;
      const version = ++generation;
      controller?.abort(); controller = new AbortController();
      identity = studioIdentityKey();
      const requestIdentity = identity;
      const live = () => active && version === generation && requestIdentity === studioIdentityKey();
      emit({ phase: 'LOADING', data: null, error: null });
      try {
        const data = await readProjectEntry(projectId, controller.signal);
        if (live()) emit({ phase: 'AVAILABLE', data, error: null });
        else if (active && version === generation) invalidate();
      } catch (error) {
        if (!active || version !== generation) return;
        emit({ phase: 'BLOCKED', data: null, error: live() && error instanceof ProjectEntryError ? error : contextChanged() });
      }
    },
  };
}
