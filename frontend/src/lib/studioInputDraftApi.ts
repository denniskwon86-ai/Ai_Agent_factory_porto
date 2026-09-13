import { apiFetch } from './api';
import { studioIdentityKey } from '../factory/studioInputMemory';

export type InputDraftTarget = {
  kind: 'CLARIFICATION' | 'DECISION_COMMENT' | 'REVISION_REQUEST'; task_id: string;
  decision_kind: '' | 'GENERAL_HOTL' | 'HOST_CONTRACT' | 'CAPABILITY' | 'DATASET';
  request_id: string; target_digest: string; subject_id: string;
};
export type InputDraftSelector = Pick<InputDraftTarget, 'kind' | 'task_id'>
  & Partial<Pick<InputDraftTarget, 'decision_kind' | 'request_id' | 'subject_id'>>;
export type InputDraftContent = { text: string; decision: string; selections?: Record<string, string[]> };
export type InputDraft = {
  draft_id: string; project_id: string; target: InputDraftTarget; content: InputDraftContent | null;
  revision: number; digest: string; status: 'DRAFT' | 'CONSUMED' | 'DISCARDED'; restorable: boolean;
};
export type InputDraftSave = { target: InputDraftTarget; content: InputDraftContent; draft_id: string;
  expected_revision: number; expected_digest: string; client_request_id: string };
export const sameInputDraftTarget = (left: InputDraftTarget, right: InputDraftTarget) =>
  (['kind', 'task_id', 'decision_kind', 'request_id', 'target_digest', 'subject_id'] as const).every(key => left?.[key] === right?.[key]);
export class InputDraftApiError extends Error {
  status: number;
  reasonCode: string;
  constructor(message: string, status = 0, reasonCode = '') { super(message); this.status = status; this.reasonCode = reasonCode; }
}
export function createInputDraftApi(projectId: string, identity = studioIdentityKey()) {
  const current = () => {
    if (!projectId || identity !== studioIdentityKey()) throw new InputDraftApiError('현재 회사·사용자에서 작업을 다시 여세요.', 409, 'CONTEXT_CHANGED');
  };
  async function request<T>(path: string, body?: unknown): Promise<T> {
    current();
    const response = await apiFetch(`/api/v1/factory/${encodeURIComponent(projectId)}/input-drafts${path}`,
      body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    current();
    const json = await response.json().catch(() => null); current();
    if (!response.ok) throw new InputDraftApiError(typeof json?.detail === 'string' ? json.detail
      : json?.detail?.message || `초안 요청을 처리하지 못했습니다 (${response.status}).`, response.status, json?.detail?.reason_code || '');
    if (json?.status !== 'success' || !json.data) throw new InputDraftApiError('초안 응답을 확인하지 못했습니다. 입력을 보존합니다.', 503, 'RESPONSE_INVALID');
    return json.data as T;
  }
  const validate = (draft: InputDraft): InputDraft => {
    if (draft.project_id !== projectId || !draft.draft_id || !Number.isInteger(draft.revision) || draft.revision < 1
        || !/^[a-f0-9]{64}$/.test(draft.digest) || !['DRAFT', 'CONSUMED', 'DISCARDED'].includes(draft.status)
        || draft.restorable !== (draft.status === 'DRAFT')) throw new InputDraftApiError('초안의 프로젝트·판본을 확인하지 못했습니다.', 503, 'RESPONSE_INVALID');
    return draft;
  };
  return {
    async target(selector: InputDraftSelector) {
      const q = new URLSearchParams(Object.entries(selector).map(([k, v]) => [k, String(v)]));
      const result = await request<{ target: InputDraftTarget; draft: InputDraft | null; consume_supported: boolean }>(`/target?${q}`);
      if (!result.target || Object.entries(selector).some(([key, value]) => result.target[key as keyof InputDraftTarget] !== value)
          || !result.target.request_id || !/^[a-f0-9]{64}$/.test(result.target.target_digest)) throw new InputDraftApiError('현재 입력 대상이 다릅니다.', 409, 'TARGET_CHANGED');
      if (result.draft) {
        validate(result.draft);
        if (!sameInputDraftTarget(result.draft.target, result.target)) throw new InputDraftApiError('저장된 입력의 대상·차수가 현재 조회와 다릅니다.', 409, 'TARGET_CHANGED');
      }
      return result;
    },
    save: async (body: InputDraftSave) => validate(await request<InputDraft>('', body)),
    discard: async (id: string, body: { expected_revision: number; expected_digest: string; client_request_id: string }) =>
      validate(await request<InputDraft>(`/${encodeURIComponent(id)}/discard`, body)),
    consume: async (id: string, body: { expected_revision: number; expected_digest: string; client_request_id: string; submission_id: string }) =>
      validate(await request<InputDraft>(`/${encodeURIComponent(id)}/consume`, body)),
  };
}
