// 키트 v2 검토 reader와 기존 승인·반려 writer. 실행/생성 API를 호출하지 않는다.
import { apiFetch } from './api';
import { studioIdentityKey } from '../factory/studioInputMemory';

export type KitReviewDecision = 'APPROVE' | 'REJECT';
export type KitDecisionEvent = { event_id: string; decision: 'APPROVED' | 'REJECTED'; actor_id: string; rationale: string };
export type KitContractReview = {
  instance_id: string; app_id: string; revision: number; latest_revision: number;
  status: 'DRAFT' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED'; semantic_fingerprint: string;
  contract: Record<string, unknown>; drafted_by: string; approved_by: string; principal_user_id: string;
  review_blockers: { reason_code: string; message: string }[];
  permitted_actions: ('approve' | 'reject')[]; decision_event: KitDecisionEvent | null;
};
export type KitReviewCommand = { decision: KitReviewDecision; revision: number; fingerprint: string; rationale: string; actorId: string };
export type KitReviewReceipt = { event_id: string; actor_id: string; decision: KitReviewDecision; revision: number; fingerprint: string };
export class KitReviewError extends Error {
  status: number; reasonCode: string;
  constructor(message: string, status = 0, reasonCode = '') { super(message); this.status = status; this.reasonCode = reasonCode; }
}
export const kitReviewError = (value: unknown): KitReviewError => value instanceof KitReviewError ? value
  : new KitReviewError(value instanceof Error ? value.message : '계약 검토 요청을 확인하지 못했습니다.');
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value)
  ? value as Record<string, unknown> : {};
const text = (value: unknown): value is string => typeof value === 'string' && !!value.trim();
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const invalid = () => new KitReviewError('계약 응답의 대상·판본·증명을 확인하지 못했습니다. 다시 조회하세요.', 503, 'KIT_REVIEW_RESPONSE_INVALID');

export function createKitContractReviewApi(instanceId: string, appId: string, identity = studioIdentityKey()) {
  let principal = '';
  const current = () => {
    if (!instanceId || !appId || studioIdentityKey() !== identity) throw new KitReviewError('현재 사용자·회사에서 키트 앱을 다시 여세요.', 409, 'CONTEXT_CHANGED');
  };
  const base = `/api/v1/data-preparation/instances/${encodeURIComponent(instanceId)}/apps/${encodeURIComponent(appId)}/contract`;
  async function request(path: string, body?: unknown): Promise<Record<string, unknown>> {
    current();
    const response = await apiFetch(base + path, body === undefined ? undefined : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    current();
    const json = object(await response.json().catch(() => null)); current();
    if (!response.ok) {
      const detail = object(json.detail);
      throw new KitReviewError(typeof detail.message === 'string' ? detail.message
        : typeof json.detail === 'string' ? json.detail : `계약 요청을 처리하지 못했습니다 (${response.status}).`,
      response.status, typeof detail.reason_code === 'string' ? detail.reason_code : '');
    }
    if (json.status !== 'success' || !json.data || typeof json.data !== 'object' || Array.isArray(json.data)) throw invalid();
    return json.data as Record<string, unknown>;
  }
  return {
    async read(revision?: number): Promise<KitContractReview> {
      if (revision !== undefined && (!Number.isInteger(revision) || revision < 1)) throw new KitReviewError('조회할 계약 판본을 확인하세요.', 422);
      const row = await request(`/v2${revision === undefined ? '' : `?revision=${revision}`}`);
      const contract = object(row.contract);
      const actions = row.permitted_actions;
      const blockers = row.review_blockers;
      if (row.instance_id !== instanceId || row.app_id !== appId || !Number.isInteger(row.revision) || Number(row.revision) < 1
          || (revision !== undefined && row.revision !== revision) || !Number.isInteger(row.latest_revision) || Number(row.latest_revision) < Number(row.revision)
          || !['DRAFT', 'APPROVED', 'REJECTED', 'SUPERSEDED'].includes(String(row.status)) || !digest(row.semantic_fingerprint)
          || contract.schema_version !== '2.0' || contract.project_id !== instanceId || contract.task_id !== appId
          || contract.revision !== row.revision || contract.semantic_fingerprint !== row.semantic_fingerprint
          || !text(row.drafted_by) || typeof row.approved_by !== 'string' || !text(row.principal_user_id)
          || !Array.isArray(actions) || actions.some(action => !['approve', 'reject'].includes(String(action)))
          || !Array.isArray(blockers) || blockers.some(item => !text(object(item).reason_code) || !text(object(item).message))) throw invalid();
      if (actions.length && (row.status !== 'DRAFT' || row.revision !== row.latest_revision
          || row.drafted_by.trim().toLowerCase() === row.principal_user_id.trim().toLowerCase())) throw invalid();
      const expectedBodyStatus = row.status === 'REJECTED' ? 'DRAFT' : row.status === 'SUPERSEDED' ? 'APPROVED' : row.status;
      if (contract.status !== expectedBodyStatus) throw invalid();
      if (principal && principal !== row.principal_user_id) throw new KitReviewError('조회 중 실제 사용자가 바뀌었습니다. 작업을 다시 여세요.', 409, 'CONTEXT_CHANGED');
      principal = row.principal_user_id;
      if (row.decision_event !== null) {
        const event = object(row.decision_event);
        if (!text(event.event_id) || !text(event.actor_id) || typeof event.rationale !== 'string'
            || !['APPROVED', 'REJECTED'].includes(String(event.decision))
            || row.status === 'DRAFT' || (row.status === 'REJECTED') !== (event.decision === 'REJECTED')) throw invalid();
      } else if (row.status !== 'DRAFT') throw invalid();
      return structuredClone(row) as KitContractReview;
    },
    async decide(command: KitReviewCommand): Promise<KitReviewReceipt> {
      if (!['APPROVE', 'REJECT'].includes(command.decision) || !Number.isInteger(command.revision) || command.revision < 1
          || !digest(command.fingerprint) || !text(command.rationale) || command.rationale.length > 4000
          || !principal || command.actorId !== principal) throw new KitReviewError('현재 검토 대상과 결정 이유를 확인하세요.', 422, 'KIT_REVIEW_INPUT_INVALID');
      const body = command.decision === 'APPROVE'
        ? { revision: command.revision, expected_fingerprint: command.fingerprint, rationale: command.rationale }
        : { revision: command.revision, expected_digest: command.fingerprint, rationale: command.rationale };
      const row = await request(command.decision === 'APPROVE' ? '/v2/approve' : '/reject', body);
      const contract = object(row.contract);
      const rejection = object(row.rejection);
      const eventId = command.decision === 'APPROVE' ? row.ledger_event_id : rejection.decision_ledger_id;
      const actor = command.decision === 'APPROVE' ? row.approved_by : rejection.rejected_by;
      if (row.instance_id !== instanceId || row.app_id !== appId || row.revision !== command.revision
          || row.semantic_fingerprint !== command.fingerprint || !text(eventId) || actor !== command.actorId
          || row.status !== (command.decision === 'APPROVE' ? 'APPROVED' : 'REJECTED')
          || contract.project_id !== instanceId || contract.task_id !== appId || contract.revision !== command.revision
          || contract.semantic_fingerprint !== command.fingerprint || contract.schema_version !== '2.0'
          || (command.decision === 'APPROVE' && object(contract.approval).decision_ledger_id !== eventId)
          || (command.decision === 'REJECT' && rejection.rationale !== command.rationale)) throw invalid();
      return { event_id: eventId, actor_id: String(actor), revision: command.revision, fingerprint: command.fingerprint, decision: command.decision };
    },
  };
}
export type KitContractReviewApi = ReturnType<typeof createKitContractReviewApi>;
