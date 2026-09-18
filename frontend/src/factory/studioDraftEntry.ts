/** [DRAFT-ENTRY-01] 초안 단건 진입 확인. 조회 가능은 편집·승인·승격을 뜻하지 않는다.
 *
 *  ## ★★★ 기존 `studioRequirementDraft` 와 결정적으로 다른 점
 *
 *  그쪽은 `GET /drafts/{id}?context_root_id=…&scope_node_id=…` 로 **경계를 실어 보낸다**
 *  (`studioRequirementDraft.ts:223`). 그건 «이미 그 문맥에서 일하고 있는» 화면이라
 *  맞는 방식이다 — 자기가 만든 초안을 자기 문맥으로 읽는다.
 *
 *  ⚠️⚠️ **URL 로 들어온 초안은 다르다.** 프런트는 그 초안이 어느 문맥 것인지 모른다.
 *    경계를 «지어내서» 보내면 그 값이 사용자의 현재 선택과 다를 때 **다른 문맥의 초안을
 *    여는 길**이 열린다. 그래서 이 모듈은 경계를 **보내지 않는다** — 서버가 초안의 소유
 *    문맥을 찾아 선택 문맥과 대조한다.
 */
import { apiFetch, getEnterpriseContext } from '../lib/api';
import { studioIdentityKey } from './studioInputMemory';
import { createEntryFlow } from './studioEntryFlow';
import type { EntryState } from './studioEntryFlow';

export type DraftKind = 'consultation' | 'blueprint';
export type DraftEntry = {
  draft_id: string; draft_kind: DraftKind; revision: number;
  ownership: { tenant_id: string; context_root_id: string; entity_mode: string; scope_node_id: string };
  viewing_context: { tenant_id: string; scope_node_id: string; entity_mode: string };
};
export class DraftEntryError extends Error {
  readonly status: number; readonly reasonCode: string;
  constructor(message: string, status = 503, reasonCode = 'ENTRY_UNAVAILABLE') {
    super(message); this.name = 'DraftEntryError'; this.status = status; this.reasonCode = reasonCode;
  }
}
const contextChanged = () => new DraftEntryError('회사 또는 사용자가 바뀌었습니다. 현재 문맥에서 다시 확인하세요.', 409, 'ENTRY_CONTEXT_CHANGED');
const malformed = () => new DraftEntryError('초안 확인 응답이 올바르지 않습니다. 다시 확인하세요.', 503, 'ENTRY_RESPONSE_INVALID');
const invalidTarget = () => new DraftEntryError('초안 링크를 확인하세요.', 422, 'ENTRY_INVALID_TARGET');

/** 서버가 「이 종류는 아직 진입 확인이 없다」고 **말한** 경우.
 *
 *  ⚠️ 「없다」와 **구분해서** 보여 준다. 같은 문구로 접으면 사용자는 자기 초안이
 *    사라진 줄 알고 찾아다닌다 — 없는 게 아니라 **아직 이 길이 없는** 것이다. */
const unsupportedKind = () => new DraftEntryError(
  '이 종류의 초안은 아직 링크로 열 수 없습니다. 목록에서 선택하세요.', 422, 'ENTRY_KIND_UNSUPPORTED');

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw malformed();
  return value as Record<string, unknown>;
}
const text = (value: unknown, allowEmpty = false): value is string => typeof value === 'string'
  && (allowEmpty || value.trim().length > 0) && value.length <= 2000;
const ID = /^[A-Za-z0-9_-]{1,160}$/;
const KINDS: readonly DraftKind[] = ['consultation', 'blueprint'];
//: 서버가 쓰는 사유 코드 중 **화면이 달리 말해야 하는 것만** 좁게 받는다.
//: ⚠️ 서버의 메시지 원문은 절대 옮기지 않는다 — 코드로만 갈라서 우리 문구를 쓴다.
const UNSUPPORTED = 'STUDIO_DRAFT_KIND_UNSUPPORTED';
/** ⚠️⚠️ [2026-09-16 실화면 실측] 회사·조직을 아직 고르지 않은 상태로 링크를 열면 서버가
 *  이것으로 답한다. 종전에는 422 를 몽땅 「초안 링크를 확인하세요」로 접었는데 — **링크는
 *  멀쩡한데 링크를 의심하게 만든다.** 브라우저로 실제로 눌러 보고서야 알았다. */
const CONTEXT_REQUIRED = 'PROCESS_CONTEXT_REQUIRED';

export async function readDraftEntry(draftId: string, kind: string, revision: number,
                                     signal?: AbortSignal): Promise<DraftEntry> {
  if (!ID.test(draftId)) throw invalidTarget();
  if (!KINDS.includes(kind as DraftKind)) throw invalidTarget();
  if (!Number.isSafeInteger(revision) || revision < 1) throw invalidTarget();
  const identity = studioIdentityKey(), selected = { ...getEnterpriseContext() };
  const current = () => { if (signal?.aborted || identity !== studioIdentityKey()) throw contextChanged(); };
  current();
  try {
    // ★ 경계를 싣지 않는다. 종류·판본만 «무엇을 물었는지» 로 보낸다.
    const query = `kind=${encodeURIComponent(kind)}&revision=${encodeURIComponent(String(revision))}`;
    const response = await apiFetch(
      `/api/v1/advisor/drafts/${encodeURIComponent(draftId)}/entry-metadata?${query}`, {
      method: 'GET', cache: 'no-store', signal,
    });
    current();
    const raw: unknown = await response.json().catch(() => null);
    current();
    if (!response.ok) {
      const detail = raw && typeof raw === 'object' ? (raw as Record<string, unknown>).detail : null;
      const code = detail && typeof detail === 'object'
        ? String((detail as Record<string, unknown>).reason_code || '') : '';
      if (code === UNSUPPORTED) throw unsupportedKind();
      if (code === CONTEXT_REQUIRED) {
        throw new DraftEntryError(
          '회사·조직을 먼저 선택하십시오. 조직 범위를 고른 뒤 다시 확인하면 이 초안이 열립니다.',
          422, 'ENTRY_CONTEXT_NOT_SELECTED');
      }
      // 비가시 자원의 서버 상세·원문은 화면 오류에 옮기지 않는다.
      const message = response.status === 401 ? '로그인이 필요합니다.'
        : response.status === 403 || response.status === 404 ? '현재 회사·권한에서 초안을 찾을 수 없습니다.'
        : response.status === 409 ? '확인 중 문맥이 바뀌었습니다. 다시 확인하세요.'
        : response.status === 422 ? '초안 링크를 확인하세요.'
        : '초안을 확인하지 못했습니다. 잠시 후 다시 확인하세요.';
      throw new DraftEntryError(message, response.status, `ENTRY_HTTP_${response.status}`);
    }
    const envelope = object(raw), row = object(envelope.data);
    const owner = object(row.ownership), view = object(row.viewing_context);
    // ⚠️ **물어본 것이 돌아왔는지** 본다. 다른 초안·다른 종류·다른 판본이면 계약 위반이다.
    if (envelope.status !== 'success' || row.draft_id !== draftId || row.draft_kind !== kind
        || row.revision !== revision
        || !text(owner.tenant_id) || !text(owner.context_root_id) || !text(owner.entity_mode)
        || !text(owner.scope_node_id, true)
        || !text(view.tenant_id) || !text(view.scope_node_id, true) || !text(view.entity_mode)
        || owner.tenant_id !== view.tenant_id || owner.entity_mode !== view.entity_mode) throw malformed();
    if ((selected.tenantId && selected.tenantId !== view.tenant_id)
        || (selected.scopeNodeId && selected.scopeNodeId !== view.scope_node_id)
        || (selected.entityMode && selected.entityMode !== view.entity_mode)) throw contextChanged();
    // 초안 원문·지문·승인 상태 등 확장 필드는 복사하지 않는다. 판정은 서버가 한다.
    return { draft_id: draftId, draft_kind: kind as DraftKind, revision,
      ownership: { tenant_id: owner.tenant_id, context_root_id: owner.context_root_id,
        entity_mode: owner.entity_mode, scope_node_id: owner.scope_node_id },
      viewing_context: { tenant_id: view.tenant_id, scope_node_id: view.scope_node_id,
        entity_mode: view.entity_mode } };
  } catch (error) {
    current();
    if (error instanceof DraftEntryError) throw error;
    throw new DraftEntryError('연결을 확인하지 못했습니다. 입력을 변경하지 않고 다시 조회할 수 있습니다.', 503, 'ENTRY_CONNECTION_FAILED');
  }
}

export type DraftEntryState = EntryState<DraftEntry, DraftEntryError>;

export function createDraftEntryFlow(draftId: string, kind: string, revision: number) {
  return createEntryFlow<DraftEntry, DraftEntryError>({
    read: signal => readDraftEntry(draftId, kind, revision, signal),
    contextChanged, isOwnError: error => error instanceof DraftEntryError,
  });
}
