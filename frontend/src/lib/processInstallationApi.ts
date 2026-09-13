// B4: v2 설치 전용 계약. 기존 평면 프로필 writer와 분리한다.
import { apiFetch, getActingUser, getEnterpriseContext, getSessionToken } from './api';

export type ProcessBoundary = {
  tenant_id: string; context_root_id: string; entity_mode: string;
  scope_node_id: string; configuration_kind: 'business_process';
};
export type ProcessAccess = {
  boundary: ProcessBoundary;
  principal_user_id: string;
  permitted_actions: string[];
  target_label?: string; context_root_label?: string;
};
export type ProcessNode = {
  process_id: string; level: 'L1' | 'L2'; parent_process_id: string;
  label: string; note: string; enabled: boolean;
};
export type ProcessDocument = {
  nodes: ProcessNode[];
  placements: { placement_id: string; process_id: string; parent_process_id: string;
    position: number; hidden: boolean; kind: 'CANONICAL' | 'SHORTCUT' }[];
  template_sources: { artifact_digest: string; kit_instance_ref: string }[];
};
export type ResolvedProcesses = {
  boundary: ProcessBoundary; configuration_id: string; head_version: number;
  profile_id: string; digest: string; state: string; payload: ProcessDocument | null;
  legacy_review_required: boolean;
};
export type ProcessPack = {
  kit_id: string; version: string; artifact_digest: string; name: string;
  state: string; data_class: string; setup_only: boolean; business_kit_ids: string[];
  business_kits?: { business_kit_id: string; label: string }[];
};
export type LegacySource = {
  profile_id: string; source_digest: string; status: string;
  payload: { nodes?: { key: string; label?: string }[] };
};
export type LegacyDecision = {
  profile_id: string; source_digest: string; decision: 'KEEP_LEGACY' | 'MIGRATE';
  confirmed_context: ProcessBoundary; key_mapping: Record<string, string>;
};
export type InstallationInput = {
  context_root_id: string; scope_node_id: string; artifact_digest: string;
  business_kit_ids: string[]; expected_head_version: number;
  base_profile_id: string; base_fingerprint: string; legacy_decisions: LegacyDecision[];
  template_mapping: Record<string, string>; instance_id: string; reason: string;
};
export type InstallationPlan = {
  plan_digest: string; preview: ProcessDocument; state: string; warnings: string[];
  data_ready: boolean; apps_ready: boolean;
};
export type InstallationOperation = {
  operation_id: string; configuration_id: string; plan_digest: string; stage: string;
  error_code: string; kit_instance_ref: string; change_id: string; actor: string;
  installer: string; revision: number; applied_profile_id: string;
  data_ready: boolean; apps_ready: boolean;
  permitted_actions?: string[];
};
export type InstallationPage = { items: InstallationOperation[]; next_offset: number | null };
export type ProcessChangeSummary = {
  change_id: string; configuration_id: string; base_head_version: number;
  draft_profile_id: string; draft_digest: string; actor: string; reason: string; status: string;
  boundary: ProcessBoundary; current_head_version: number; principal_user_id: string;
  permitted_actions: string[]; review_blockers: string[]; operation_id: string | null;
};
export type ProcessChangeReview = ProcessChangeSummary & {
  payload: ProcessDocument; base_payload: ProcessDocument | null;
};
export type ProcessChangePage = { items: ProcessChangeSummary[]; next_offset: number | null };
export type ProcessDisplayCommand =
  | { op: 'RENAME'; process_id: string; label: string }
  | { op: 'SET_NOTE'; process_id: string; note: string }
  | { op: 'REORDER_PLACEMENTS'; parent_process_id: string; placement_ids: string[] };
export type ProcessStructureCommand =
  | { op: 'ADD_NODE'; node: Pick<ProcessNode, 'process_id' | 'level' | 'parent_process_id' | 'label' | 'note'> }
  | { op: 'SET_USAGE'; process_id: string; enabled: boolean }
  | { op: 'MOVE_NODE'; process_id: string; parent_process_id: string }
  | { op: 'ADD_SHORTCUT'; process_id: string; parent_process_id: string }
  | { op: 'REMOVE_SHORTCUT'; placement_id: string };
export type ProcessCommand = ProcessDisplayCommand | ProcessStructureCommand;
export type ProcessEditInput = {
  context_root_id: string; scope_node_id: string; commands: ProcessCommand[];
  expected_head_version: number; base_profile_id: string; base_fingerprint: string;
  client_request_id: string; reason: string;
};
export type ProcessChangeReceipt = Pick<ProcessChangeSummary, 'change_id' | 'configuration_id'
  | 'base_head_version' | 'draft_profile_id' | 'draft_digest' | 'actor' | 'reason' | 'status'>;
export type ProcessApprovalInput = { expected_head_version: number; draft_digest: string; reason: string };
export type ProcessApprovalReceipt = {
  change_id: string; configuration_id: string; status: string; profile_id: string;
  head_version: number; digest: string; event_id: string; audit_delivery: string;
};

export class ProcessApiError extends Error {
  readonly status: number;
  readonly reasonCode: string;
  readonly nextAction: string;
  constructor(status: number, message: string, reasonCode = '', nextAction = '') {
    super(message); this.status = status; this.reasonCode = reasonCode; this.nextAction = nextAction;
  }
}

// 토큰은 메모리 비교에만 사용한다. URL·저장소·로그에 복사하지 않는다.
export function processContextIdentity(): string {
  const c = getEnterpriseContext();
  return JSON.stringify([c.tenantId, c.scopeNodeId, c.entityMode, getActingUser(), getSessionToken()]);
}

export async function unwrapProcessResponse<T>(response: Response): Promise<T> {
  let body: { detail?: unknown; status?: string; data?: T };
  try { body = await response.json(); }
  catch { throw new ProcessApiError(response.status || 503, '서버 응답을 읽지 못했습니다. 입력을 보존했습니다.'); }
  if (!response.ok) {
    const detail = body.detail;
    const value = detail && typeof detail === 'object' && !Array.isArray(detail)
      ? detail as Record<string, unknown> : {};
    throw new ProcessApiError(response.status,
      typeof value.message === 'string' ? value.message : typeof detail === 'string'
        ? detail : '요청을 처리하지 못했습니다. 입력과 설치 상태를 확인해 주세요.',
      typeof value.reason_code === 'string' ? value.reason_code : '',
      typeof value.next_action === 'string' ? value.next_action : '');
  }
  if (body.status !== 'success' || body.data === undefined || body.data === null) {
    throw new ProcessApiError(503, '응답 형식을 확인할 수 없습니다. 빈 구성으로 표시하지 않습니다.');
  }
  return body.data;
}

const BASE = '/api/v1/enterprise-context';
export function createProcessInstallationApi(identity = processContextIdentity()) {
  function assertCurrent() {
    if (processContextIdentity() !== identity) {
      throw new ProcessApiError(409, '회사·조직 또는 사용자가 바뀌었습니다. 새 문맥에서 다시 확인해 주세요.', 'CLIENT_CONTEXT_CHANGED');
    }
  }
  async function call<T>(path: string, body?: unknown): Promise<T> {
    assertCurrent();
    const response = await apiFetch(BASE + path, body === undefined ? undefined : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    assertCurrent();
    const result = await unwrapProcessResponse<T>(response);
    assertCurrent();
    return result;
  }
  const query = (b: ProcessBoundary) => new URLSearchParams({
    context_root_id: b.context_root_id, scope_node_id: b.scope_node_id,
  }).toString();
  return {
    access: (companyWide: boolean) => call<ProcessAccess>(`/process-configurations/context?company_wide=${companyWide}`),
    resolved: (b: ProcessBoundary) => call<ResolvedProcesses>(`/process-configurations/resolved?${query(b)}`),
    catalog: (b: ProcessBoundary) => call<ProcessPack[]>(`/process-packs?${query(b)}`),
    legacy: (b: ProcessBoundary) => call<{ sources: LegacySource[] }>(`/process-installations/legacy-preview?${query(b)}`),
    register: (b: ProcessBoundary, pack: ProcessPack) => call<{ artifact_digest: string }>(
      '/process-packs/register', { context_root_id: b.context_root_id, scope_node_id: b.scope_node_id,
        kit_id: pack.kit_id, version: pack.version }),
    plan: (body: InstallationInput) => call<InstallationPlan>('/process-installations/plan', body),
    // 계획 응답을 펼치지 않는다. 검토 당시 원래 요청·지문·키만 전송한다.
    start: (body: InstallationInput, digest: string, requestId: string) => call<InstallationOperation>(
      '/process-installations', { ...body, plan_digest: digest, client_request_id: requestId }),
    list: (b: ProcessBoundary, offset = 0) => call<InstallationPage>(
      `/process-installations?${query(b)}&limit=20&offset=${offset}`),
    get: (operationId: string) => call<InstallationOperation>(`/process-installations/${encodeURIComponent(operationId)}`),
    resume: (operationId: string, expectedRevision: number, adopt: boolean) => call<InstallationOperation>(
      `/process-installations/${encodeURIComponent(operationId)}/resume`, { expected_revision: expectedRevision, adopt }),
    changes: (b: ProcessBoundary, offset = 0) => call<ProcessChangePage>(
      `/process-changes?${query(b)}&status=DRAFT&limit=20&offset=${offset}`),
    propose: (_b: ProcessBoundary, body: ProcessEditInput) => call<ProcessChangeReceipt>(
      '/process-configurations/changes', body),
    change: (b: ProcessBoundary, changeId: string) => call<ProcessChangeReview>(
      `/process-changes/${encodeURIComponent(changeId)}?${query(b)}`),
    approve: (_b: ProcessBoundary, changeId: string, body: ProcessApprovalInput) => call<ProcessApprovalReceipt>(
      `/process-changes/${encodeURIComponent(changeId)}/approve`, body),
  };
}
export type ProcessInstallationApi = ReturnType<typeof createProcessInstallationApi>;
