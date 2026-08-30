// [이관 2/10] 기준정보 마스터 API 클라이언트
//
// 화면이 직접 fetch 하면 실패를 빈 배열로 바꾸기 쉽고, 사용자 식별·오류 문구도 화면마다
// 달라진다. JSON 요청은 공용 계약을 사용하고, FormData 인 CSV 업로드만 별도로 처리한다.
import { API_BASE_URL } from './api';
import {
  closedLoopEnvelopeFetch, closedLoopFetch as req, type ApiError,
} from './closedLoopFetch';

export type MasterType = {
  type_id: string;
  name_ko: string;
  description: string;
  attr_schema: Record<string, unknown>;
  relations: unknown[];
  created_at: string;
};

export type RecordHistory = {
  version: number;
  status: string;
  valid_from: string;
  valid_to: string | null;
  supersedes: string | null;
  source: string;
  updated_at: string;
};

export type MasterRecord = {
  master_code: string;
  type_id: string;
  name: string;
  attributes: Record<string, unknown>;
  domains: string[];
  aliases: string[];
  is_core: boolean;
  version: number;
  valid_from: string;
  valid_to: string | null;
  supersedes: string | null;
  status: string;
  source: string;
  updated_at: string;
  history?: RecordHistory[];
};

export type RecordInput = {
  type_id: string;
  name: string;
  attributes?: Record<string, unknown>;
  domains?: string[];
  aliases?: string[];
  is_core?: boolean;
  rationale?: string;
};

export type MasterRecordProposal = RecordInput & {
  proposal_id: string;
  status: 'pending' | 'approved' | 'rejected';
  proposed_by: string;
  reviewed_by: string;
  review_reason: string;
  reviewed_at: string;
  created_at: string;
};

export type GroundingPreview = {
  block: string;
  matched: string[];
  stats?: Record<string, unknown>;
};

export type CsvImportReport = {
  imported: number;
  total: number;
  failed: { row: number; error: string }[];
};

export type MasterList<T> = {
  rows: T[];
  blockedReason: string;
  /** 가려진 것이 **있는가**. 누구에게나 온다 — 모르면 본 목록을 전량으로 믿는다. */
  hiddenPresent: boolean;
  /** 가려진 것이 **몇 건인가**. DA·관리자에게만 온다(`api.deps.hidden_envelope`).
   *  ⚠️ `0` 과 «모른다»를 구분해야 하므로 `null` 이다. 0 으로 두면 "가린 것 없음"으로 읽힌다. */
  hiddenCount: number | null;
};

async function listRequest<T>(path: string): Promise<MasterList<T>> {
  const envelope = await closedLoopEnvelopeFetch<T[]>('GET', path);
  return {
    rows: envelope.data || [],
    blockedReason: String(envelope.blocked_reason || ''),
    hiddenPresent: Boolean(envelope.hidden_present),
    hiddenCount: envelope.hidden_count === undefined || envelope.hidden_count === null
      ? null : Number(envelope.hidden_count),
  };
}

async function formRequest<T>(path: string, form: FormData): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, { method: 'POST', body: form });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail = (j as any)?.detail;
    const err = new Error(typeof detail === 'string' ? detail : `요청 실패 (${r.status})`) as ApiError;
    err.status = r.status;
    throw err;
  }
  return (j as any).data as T;
}

export const masterDataApi = {
  types: () => listRequest<MasterType>('/api/v1/master/types'),
  createType: (body: {
    type_id: string; name_ko: string; description?: string;
    attr_schema?: Record<string, unknown>;
  }) => req<MasterType>('POST', '/api/v1/master/types', body),

  records: (typeId: string, query = '') => {
    const q = new URLSearchParams({ type_id: typeId });
    if (query.trim()) q.set('q', query.trim());
    return listRequest<MasterRecord>(`/api/v1/master/records?${q.toString()}`);
  },
  record: (code: string) =>
    req<MasterRecord>('GET', `/api/v1/master/records/${encodeURIComponent(code)}`),
  proposeRecord: (body: RecordInput) =>
    req<MasterRecordProposal>('POST', '/api/v1/master/records/proposals', body),
  reviseRecord: (masterCode: string, body: Omit<RecordInput, 'type_id' | 'rationale'>) =>
    req<MasterRecord>('PUT', `/api/v1/master/records/${encodeURIComponent(masterCode)}`, body),
  proposals: (status: 'pending' | 'approved' | 'rejected' | 'all' = 'pending') =>
    req<MasterRecordProposal[]>('GET', `/api/v1/master/records/proposals?status=${status}`),
  approveProposal: (proposalId: string, reason = '') =>
    req<{ proposal: MasterRecordProposal; record: MasterRecord }>(
      'POST', `/api/v1/master/records/proposals/${encodeURIComponent(proposalId)}/approve`, { reason }),
  rejectProposal: (proposalId: string, reason: string) =>
    req<MasterRecordProposal>(
      'POST', `/api/v1/master/records/proposals/${encodeURIComponent(proposalId)}/reject`, { reason }),
  retireRecord: (code: string) =>
    req<unknown>('DELETE', `/api/v1/master/records/${encodeURIComponent(code)}`),
  addAlias: (code: string, alias: string) =>
    req<MasterRecord>('POST', `/api/v1/master/records/${encodeURIComponent(code)}/aliases`,
      { aliases: [alias] }),
  removeAlias: (code: string, alias: string) =>
    req<MasterRecord>('DELETE',
      `/api/v1/master/records/${encodeURIComponent(code)}/aliases/${encodeURIComponent(alias)}`),

  preview: (text: string, domains: string[], scopeNodeId = '') =>
    req<GroundingPreview>('POST', '/api/v1/master/grounding/preview', {
      text, domains, scope_node_id: scopeNodeId || undefined,
    }),
  importCsv: (typeId: string, file: File) => {
    const form = new FormData();
    form.append('type_id', typeId);
    form.append('file', file);
    return formRequest<CsvImportReport>('/api/v1/master/import/csv', form);
  },
};
