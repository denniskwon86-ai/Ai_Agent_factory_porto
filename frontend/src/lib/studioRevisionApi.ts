// 수정 요청 접수·조회만 수행한다. 작업 실행과 초안 사용 완료는 별도다.
import { apiFetch } from './api';
import { studioIdentityKey } from '../factory/studioInputMemory';
import { sameInputDraftTarget } from './studioInputDraftApi';
import type { InputDraft, InputDraftTarget } from './studioInputDraftApi';

export type RevisionDraftRef = { draft_id: string; revision: number; digest: string };
export type RevisionCommand = { client_request_id: string; target: InputDraftTarget; feedback: string; input_draft: RevisionDraftRef };
export type RevisionReceipt = { request_id: string; submission_id: string; project_id: string; actor_id: string;
  target: InputDraftTarget; feedback: string; input_draft: RevisionDraftRef; task_id: string;
  status: 'ACCEPTED'; execution_started: false; created_at: string };
export class RevisionApiError extends Error {
  status: number; reasonCode: string;
  constructor(message: string, status = 0, reasonCode = '') { super(message); this.status = status; this.reasonCode = reasonCode; }
}
export const revisionError = (error: unknown) => error instanceof RevisionApiError ? error : new RevisionApiError(
  error instanceof Error ? error.message : '수정 요청의 처리 결과를 확인하지 못했습니다.',
  error && typeof error === 'object' && 'status' in error && typeof error.status === 'number' ? error.status : 0,
  error && typeof error === 'object' && 'reasonCode' in error && typeof error.reasonCode === 'string' ? error.reasonCode : '');
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = (value: unknown): value is string => typeof value === 'string' && !!value.trim();
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const isRevisionTarget = (target: InputDraftTarget): boolean => !!target && target.kind === 'REVISION_REQUEST'
  && typeof target.task_id === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(target.task_id)
  && target.decision_kind === '' && target.subject_id === '' && sha(target.target_digest)
  && target.request_id === `artifact_${target.target_digest}`;
const validRef = (ref: RevisionDraftRef) => !!ref && text(ref.draft_id) && ref.draft_id.length <= 128
  && Number.isInteger(ref.revision) && ref.revision > 0 && sha(ref.digest);
export const sameRevisionRef = (left: RevisionDraftRef, right: RevisionDraftRef) => !!left && !!right
  && left.draft_id === right.draft_id && left.revision === right.revision && left.digest === right.digest;
export function matchesRevisionDraft(projectId: string, target: InputDraftTarget, feedback: string, draft: InputDraft | null): draft is InputDraft {
  return !!(draft && validRef(draft) && draft.project_id === projectId && draft.status === 'DRAFT' && draft.restorable
    && sameInputDraftTarget(draft.target, target) && draft.content && draft.content.text.trim() === feedback.trim()
    && draft.content.decision === '' && !Object.keys(draft.content.selections || {}).length);
}
export const sameRevisionCommand = (left: RevisionCommand, right: RevisionCommand) =>
  sameInputDraftTarget(left.target, right.target) && left.feedback === right.feedback && sameRevisionRef(left.input_draft, right.input_draft);
const invalid = () => new RevisionApiError('수정 접수증의 프로젝트·기준·입력·작업을 확인하지 못했습니다. 원래 요청을 보존하고 다시 조회하세요.', 503, 'REVISION_RESPONSE_INVALID');

export function createStudioRevisionApi(projectId: string, identity = studioIdentityKey()) {
  const current = () => {
    if (!projectId || identity !== studioIdentityKey()) throw new RevisionApiError('현재 회사·사용자에서 수정 요청을 다시 여세요.', 409, 'CONTEXT_CHANGED');
  };
  function validateCommand(command: RevisionCommand) {
    if (!text(command.client_request_id) || command.client_request_id.length > 160 || !isRevisionTarget(command.target)
        || !text(command.feedback) || command.feedback !== command.feedback.trim() || command.feedback.length > 32000 || !validRef(command.input_draft))
      throw new RevisionApiError('저장한 초안과 수정 기준을 확인하세요.', 422, 'REVISION_INPUT_INVALID');
  }
  async function request(command: RevisionCommand, write: boolean, expected?: RevisionReceipt): Promise<RevisionReceipt> {
    current(); validateCommand(command);
    const path = `/api/v1/factory/${encodeURIComponent(projectId)}/sprint/revision-requests`;
    const response = await apiFetch(path + (write ? '' : `/${encodeURIComponent(command.client_request_id)}`), write
      ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command) } : undefined);
    current();
    const json = object(await response.json().catch(() => null)); current();
    if (!response.ok) {
      const detail = object(json.detail);
      throw new RevisionApiError(typeof detail.message === 'string' ? detail.message : typeof json.detail === 'string'
        ? json.detail : `수정 요청을 확인하지 못했습니다 (${response.status}).`, response.status,
      typeof detail.reason_code === 'string' ? detail.reason_code : '');
    }
    const row = object(json.data);
    if (json.status !== 'success' || row.request_id !== command.client_request_id || row.project_id !== projectId
        || row.status !== 'ACCEPTED' || row.execution_started !== false || !text(row.submission_id) || !text(row.actor_id)
        || !text(row.task_id) || !/^TASK_REV_[A-Za-z0-9_-]+$/.test(row.task_id) || row.task_id === command.target.task_id
        || !text(row.created_at) || !Number.isFinite(Date.parse(row.created_at))
        || !sameInputDraftTarget(row.target as InputDraftTarget, command.target) || row.feedback !== command.feedback
        || !sameRevisionRef(row.input_draft as RevisionDraftRef, command.input_draft)) throw invalid();
    if (expected && (row.submission_id !== expected.submission_id || row.actor_id !== expected.actor_id
        || row.task_id !== expected.task_id || row.created_at !== expected.created_at)) throw invalid();
    return structuredClone(row) as RevisionReceipt;
  }
  return { submit: (command: RevisionCommand) => request(command, true),
    read: (command: RevisionCommand, expected?: RevisionReceipt) => request(command, false, expected) };
}
export type StudioRevisionApi = ReturnType<typeof createStudioRevisionApi>;
