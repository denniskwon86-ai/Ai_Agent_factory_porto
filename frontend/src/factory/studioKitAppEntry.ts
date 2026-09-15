// B6 키트 앱 단건 진입 확인. 조회 가능은 실행·게시·준비 완료를 뜻하지 않는다.
//
// ★★★ **목록 수준**이다(사용자 결정 2026-09-15). 화면 목록이 보여 주는 것과 같은 조건으로
//   판정한다 — 목록에 보이는 앱을 링크로는 못 여는 상태를 만들지 않는다.
//
// ⚠️ `studioProjectEntry.ts` 와 흐름 구조가 같다. **공통화는 아직 하지 않았다** —
//   진입 확인 헬퍼를 언제 어떻게 뽑을지가 미결이기 때문이다
//   (`docs/design_l2_studio_entry_readers_2026-09-15.md` §4·§6-4). 합칠 때 두 파일이
//   같은 모양이어야 옮기기 쉬우므로 의도적으로 같은 구조를 유지했다.
import { apiFetch, getEnterpriseContext } from '../lib/api';
import { studioIdentityKey } from './studioInputMemory';

export type KitAppEntry = {
  instance_id: string; app_id: string; app_label: string;
  ownership: { tenant_id: string; enterprise_scope_id: string; entity_mode: string };
  viewing_context: { tenant_id: string; scope_node_id: string; entity_mode: string };
};
export class KitAppEntryError extends Error {
  readonly status: number; readonly reasonCode: string;
  constructor(message: string, status = 503, reasonCode = 'KIT_APP_ENTRY_UNAVAILABLE') {
    super(message); this.name = 'KitAppEntryError'; this.status = status; this.reasonCode = reasonCode;
  }
}
const contextChanged = () => new KitAppEntryError('회사 또는 사용자가 바뀌었습니다. 현재 문맥에서 다시 확인하세요.', 409, 'KIT_APP_ENTRY_CONTEXT_CHANGED');
const malformed = () => new KitAppEntryError('업무 앱 확인 응답이 올바르지 않습니다. 다시 확인하세요.', 503, 'KIT_APP_ENTRY_RESPONSE_INVALID');
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw malformed();
  return value as Record<string, unknown>;
}
const text = (value: unknown, allowEmpty = false): value is string => typeof value === 'string'
  && (allowEmpty || value.trim().length > 0) && value.length <= 2000;
const ID = /^[A-Za-z0-9_-]{1,160}$/;

export async function readKitAppEntry(instanceId: string, appId: string, signal?: AbortSignal): Promise<KitAppEntry> {
  if (!ID.test(instanceId) || !ID.test(appId)) throw new KitAppEntryError('업무 앱 링크를 확인하세요.', 422, 'KIT_APP_ENTRY_INVALID_TARGET');
  const identity = studioIdentityKey(), selected = { ...getEnterpriseContext() };
  const current = () => { if (signal?.aborted || identity !== studioIdentityKey()) throw contextChanged(); };
  current();
  try {
    const response = await apiFetch(
      `/api/v1/data-preparation/instances/${encodeURIComponent(instanceId)}/apps/${encodeURIComponent(appId)}/entry-metadata`,
      { method: 'GET', cache: 'no-store', signal });
    current();
    const raw: unknown = await response.json().catch(() => null);
    current();
    if (!response.ok) {
      // 비가시 자원의 서버 상세/원문은 화면 오류에 옮기지 않는다.
      const message = response.status === 401 ? '로그인이 필요합니다.'
        : response.status === 400 || response.status === 403 || response.status === 404
          ? '현재 회사·권한에서 업무 앱을 찾을 수 없습니다.'
        : response.status === 409 ? '확인 중 문맥이 바뀌었습니다. 다시 확인하세요.'
        : '업무 앱을 확인하지 못했습니다. 잠시 후 다시 확인하세요.';
      throw new KitAppEntryError(message, response.status, `KIT_APP_ENTRY_HTTP_${response.status}`);
    }
    const envelope = object(raw), row = object(envelope.data);
    const owner = object(row.ownership), view = object(row.viewing_context);
    if (envelope.status !== 'success' || row.instance_id !== instanceId || row.app_id !== appId
        || !text(row.app_label)
        || !text(owner.tenant_id) || !text(owner.enterprise_scope_id, true) || !text(owner.entity_mode)
        || !text(view.tenant_id) || !text(view.scope_node_id, true) || !text(view.entity_mode)) throw malformed();
    // ⚠️ 여기서 **소유와 조회 문맥이 같은지는 보지 않는다.** 목록 수준 판정이라 전사 조회
    //   권한에서는 둘이 다를 수 있다(설계안 §6-6 결정). project 경로와 다른 점이다 —
    //   거기서는 둘이 다르면 잘못된 응답으로 본다. 범위 판정은 서버가 한다.
    if ((selected.tenantId && selected.tenantId !== view.tenant_id)
        || (selected.scopeNodeId && selected.scopeNodeId !== view.scope_node_id)
        || (selected.entityMode && selected.entityMode !== view.entity_mode)) throw contextChanged();
    // 준비도·계약·릴리스 결속 등 확장 필드는 복사하지 않는다. 각 단계가 다시 확인한다.
    return { instance_id: instanceId, app_id: appId, app_label: row.app_label,
      ownership: { tenant_id: owner.tenant_id, enterprise_scope_id: owner.enterprise_scope_id, entity_mode: owner.entity_mode },
      viewing_context: { tenant_id: view.tenant_id, scope_node_id: view.scope_node_id, entity_mode: view.entity_mode } };
  } catch (error) {
    current();
    if (error instanceof KitAppEntryError) throw error;
    throw new KitAppEntryError('연결을 확인하지 못했습니다. 입력을 변경하지 않고 다시 조회할 수 있습니다.', 503, 'KIT_APP_ENTRY_CONNECTION_FAILED');
  }
}

export type KitAppEntryState = {
  phase: 'IDLE' | 'LOADING' | 'AVAILABLE' | 'BLOCKED'; data: KitAppEntry | null; error: KitAppEntryError | null;
};
const events = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
export function createKitAppEntryFlow(instanceId: string, appId: string) {
  let state: KitAppEntryState = { phase: 'IDLE', data: null, error: null };
  let active = false, generation = 0, identity = '', controller: AbortController | null = null;
  const listeners = new Set<() => void>();
  const emit = (next: KitAppEntryState) => { state = next; for (const listener of listeners) listener(); };
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
        const data = await readKitAppEntry(instanceId, appId, controller.signal);
        if (live()) emit({ phase: 'AVAILABLE', data, error: null });
        else if (active && version === generation) invalidate();
      } catch (error) {
        if (!active || version !== generation) return;
        emit({ phase: 'BLOCKED', data: null, error: live() && error instanceof KitAppEntryError ? error : contextChanged() });
      }
    },
  };
}
