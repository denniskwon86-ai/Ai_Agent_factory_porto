// 결정 종류별 서버 계약을 분리한다. 화면 입력이나 LLM 출력으로 차수를 만들지 않는다.
import { apiFetch } from '../lib/api';
import {
  getContractReviewPending, decideContractReview, reconcileContractReview,
} from '../lib/contractReviewApi';
import type {
  ContractReviewPending, ContractDecisionResult, ContractReconcileInput, ContractReconcileResult,
} from '../lib/contractReviewApi';
import { studioIdentityKey } from './studioInputMemory';
import type { ClarifyQuestionLike } from './clarifyAnswers';

export type HotlRound = {
  taskId: string;
  status: 'PENDING' | 'NOT_PENDING' | 'UNKNOWN';
  available: boolean; request_id: string; questions_digest: string;
  decision_kind: string; reason_code: string;
};
export type CapabilityDecision = {
  decision_kind?: 'CAPABILITY' | 'DATASET';
  decision_request_id?: string; expected_digest?: string;
  round_status?: string; task_id?: string; capability?: string;
  dataset_key?: string; reason?: string; status_label?: string;
  choices: string[]; differences?: unknown[];
};
export type CapabilityPending = {
  pending: boolean; capability_decisions: CapabilityDecision[];
  dataset_conflicts: CapabilityDecision[]; other_errors: unknown[];
  round_metadata_status: string;
};
export type CapabilityInput = {
  decision_request_id: string; expected_digest: string; rationale: string;
  task_id?: string; capability?: string; decision?: string;
  dataset_key?: string; winner_task_id?: string;
};
export type CapabilityReceipt = {
  decision_request_id: string; expected_digest: string; event_id: string;
  draft_applied: boolean; note?: string;
};
export type HotlInput = {
  task_id: string; feedback: string; expected_request_id: string; expected_questions_digest: string;
};
export type HostInput = {
  task_id: string; request_event_id: string; decision: 'APPROVE' | 'REJECT'; rationale: string;
};
export interface StudioDecisionApi {
  hotl(): Promise<HotlRound>;
  host(taskId: string): Promise<ContractReviewPending>;
  capabilities(): Promise<CapabilityPending>;
  resume(body: HotlInput): Promise<{ status: 'resumed'; task_id: string }>;
  decide(body: HostInput): Promise<ContractDecisionResult>;
  reconcile(body: ContractReconcileInput): Promise<ContractReconcileResult>;
  resolve(body: CapabilityInput): Promise<CapabilityReceipt>;
}

export class StudioDecisionError extends Error {
  status: number;
  reasonCode: string;
  detail: Record<string, unknown>;
  constructor(message: string, status = 0, reasonCode = '', detail: Record<string, unknown> = {}) {
    super(message); this.name = 'StudioDecisionError';
    this.status = status; this.reasonCode = reasonCode; this.detail = detail;
  }
}

export function decisionError(error: unknown): StudioDecisionError {
  if (error instanceof StudioDecisionError) return error;
  const value = error && typeof error === 'object' ? error as Record<string, unknown> : {};
  return new StudioDecisionError(typeof value.message === 'string' ? value.message : '응답을 확인하지 못했습니다.',
    typeof value.status === 'number' ? value.status : 0,
    typeof value.reasonCode === 'string' ? value.reasonCode : '',
    value.detail && typeof value.detail === 'object' ? value.detail as Record<string, unknown> : {});
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw malformed();
  return value as Record<string, unknown>;
}
function malformed() { return new StudioDecisionError('서버 응답 형식을 확인할 수 없습니다. 다시 조회하세요.', 503, 'DECISION_RESPONSE_INVALID'); }
function string(value: unknown): string { return typeof value === 'string' ? value : ''; }
export function isDecisionDigest(value: unknown): value is string { return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value); }

/** Python의 sort_keys/ensure_ascii=False와 같은 키 순서로 원본 전체를 직렬화한다.
 * 숫자 표현 차이 등 원문을 확신할 수 없는 경우에는 지문 불일치로 닫힌다. */
export function canonicalQuestionJson(value: unknown): string {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalQuestionJson).join(',')}]`;
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    const row = value as Record<string, unknown>;
    const compare = (a: string, b: string) => {
      const left = Array.from(a, c => c.codePointAt(0)!);
      const right = Array.from(b, c => c.codePointAt(0)!);
      for (let i = 0; i < Math.min(left.length, right.length); i++) if (left[i] !== right[i]) return left[i] - right[i];
      return left.length - right.length;
    };
    return `{${Object.keys(row).sort(compare).map(key => `${JSON.stringify(key)}:${canonicalQuestionJson(row[key])}`).join(',')}}`;
  }
  throw new StudioDecisionError('질문 원문을 확인할 수 없습니다. 현재 질문을 다시 조회하세요.', 409, 'HOTL_QUESTIONS_UNVERIFIED');
}

export type HotlQuestionVerification = { rawQuestions: unknown; displayedQuestions: ClarifyQuestionLike[] };

export async function verifyHotlQuestions(proof: HotlQuestionVerification, expectedDigest: string): Promise<boolean> {
  try {
    if (!isDecisionDigest(expectedDigest) || !Array.isArray(proof.rawQuestions) || !globalThis.crypto?.subtle) return false;
    const projected = proof.rawQuestions.map(value => {
      const q = object(value);
      if (typeof q.id !== 'string' || !q.id.trim() || typeof q.question !== 'string' || !q.question.trim()) throw malformed();
      const options = q.options === undefined ? [] : q.options;
      if (!Array.isArray(options)) throw malformed();
      return { id: q.id.trim(), question: q.question.trim(), multi: !!q.multi,
        options: options.map(value => {
          const option = object(value);
          if (typeof option.label !== 'string' || !option.label.trim()) throw malformed();
          return { label: option.label.trim(), description: String(option.description ?? '').trim(), recommended: !!option.recommended };
        }) };
    });
    if (canonicalQuestionJson(projected) !== canonicalQuestionJson(proof.displayedQuestions)) return false;
    const bytes = new TextEncoder().encode(canonicalQuestionJson(proof.rawQuestions));
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') === expectedDigest;
  } catch { return false; }
}

export function createStudioDecisionApi(projectId: string, identity = studioIdentityKey()): StudioDecisionApi {
  const base = `/api/v1/factory/${encodeURIComponent(projectId)}`;
  const current = () => {
    if (!projectId || studioIdentityKey() !== identity) {
      throw new StudioDecisionError('회사 또는 사용자가 바뀌었습니다. 현재 작업을 다시 여세요.', 409, 'DECISION_CONTEXT_CHANGED');
    }
  };
  const guarded = async <T,>(work: () => Promise<T>): Promise<T> => {
    current();
    try { const result = await work(); current(); return result; }
    catch (error) { current(); throw decisionError(error); }
  };
  const request = (path: string, body?: unknown) => guarded(async () => {
    const response = await apiFetch(`${base}${path}`, body === undefined ? undefined : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const raw: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = raw && typeof raw === 'object' ? (raw as Record<string, unknown>).detail : null;
      const fields = detail && typeof detail === 'object' ? detail as Record<string, unknown> : {};
      throw new StudioDecisionError(string(fields.message) || string(detail) || `요청을 처리하지 못했습니다 (${response.status}).`,
        response.status, string(fields.reason_code), fields);
    }
    return object(raw);
  });
  return {
    async hotl() {
      const raw = await request('/hotl/check');
      if (raw.status !== 'success') throw malformed();
      if (!raw.hotl_context) {
        if (raw.hotl_task_id) throw malformed();
        return { taskId: '', status: 'NOT_PENDING', available: false, request_id: '', questions_digest: '', decision_kind: '', reason_code: '' };
      }
      const context = object(raw.hotl_context);
      if (!['PENDING', 'NOT_PENDING', 'UNKNOWN'].includes(string(context.status))) throw malformed();
      const available = context.available === true && context.pending === true && context.status === 'PENDING';
      if (typeof context.pending !== 'boolean' || typeof context.available !== 'boolean'
          || context.pending !== (context.status === 'PENDING') || context.available !== context.pending) throw malformed();
      if (available && (!string(raw.hotl_task_id) || !isDecisionDigest(context.request_id)
          || !isDecisionDigest(context.questions_digest)
          || !['CLARIFICATION', 'GENERAL_HOTL'].includes(string(context.decision_kind)))) throw malformed();
      return { taskId: string(raw.hotl_task_id), status: context.status as HotlRound['status'], available,
        request_id: string(context.request_id), questions_digest: string(context.questions_digest),
        decision_kind: string(context.decision_kind), reason_code: string(context.reason_code) };
    },
    host: (taskId) => guarded(async () => {
      const row = await getContractReviewPending(projectId, taskId);
      if (!row || typeof row.pending !== 'boolean') throw malformed();
      return row;
    }),
    async capabilities() {
      const row = object((await request('/contract-decisions/pending')).data);
      if (typeof row.pending !== 'boolean' || !Array.isArray(row.capability_decisions)
          || !Array.isArray(row.dataset_conflicts) || !Array.isArray(row.other_errors)) throw malformed();
      if (row.pending !== !!(row.capability_decisions.length || row.dataset_conflicts.length)) throw malformed();
      for (const candidate of [...row.capability_decisions, ...row.dataset_conflicts]) {
        const item = object(candidate);
        if (!Array.isArray(item.choices) || item.choices.some(choice => typeof choice !== 'string')) throw malformed();
      }
      return row as unknown as CapabilityPending;
    },
    async resume(body) {
      if (!body.task_id || !isDecisionDigest(body.expected_request_id) || !isDecisionDigest(body.expected_questions_digest)) throw malformed();
      const row = await request('/hotl/resume', body);
      if (row.status !== 'resumed' || row.task_id !== body.task_id) throw malformed();
      return { status: 'resumed', task_id: body.task_id };
    },
    decide: (body) => guarded(async () => {
      const row = await decideContractReview(projectId, body);
      if (!row || row.request_event_id !== body.request_event_id || row.decision !== body.decision
          || !row.event_id || !isDecisionDigest(row.contract_fingerprint) || typeof row.state_applied !== 'boolean') throw malformed();
      return row;
    }),
    reconcile: (body) => guarded(async () => {
      const row = await reconcileContractReview(projectId, body);
      if (!row || row.event_id !== body.event_id || row.request_event_id !== body.request_event_id
          || row.contract_fingerprint !== body.compiled_fingerprint
          || typeof row.state_applied !== 'boolean' || row.execution_started !== false) throw malformed();
      return row;
    }),
    async resolve(body) {
      if (!body.decision_request_id || !isDecisionDigest(body.expected_digest)) throw malformed();
      const row = object((await request('/contract-decisions/resolve', body)).data);
      if (row.decision_request_id !== body.decision_request_id || row.expected_digest !== body.expected_digest
          || !string(row.event_id) || typeof row.draft_applied !== 'boolean') throw malformed();
      return row as unknown as CapabilityReceipt;
    },
  };
}
