// [G2 M0-0 · M0-5] 경로 계산 — 준비도 · 실행 승인 · 시연 초기화 API 클라이언트.
//
// ⚠️ 여기서 판정하지 않는다. 서버가 준 상태·사유·다음 행동을 **그대로 화면에 옮긴다** —
//   화면이 자기 규칙으로 다시 판단하면 두 판정이 갈라지고, 갈린 날 사용자는 서버가
//   막은 것을 화면이 허용하는 상태를 본다.
//
// ⚠️⚠️ **지문을 화면에서 만들지 않는다.** 승인 대상 지문(`binding_fingerprint`)과 초기화
//   계획 지문(`plan_fingerprint`)은 서버가 산출하고, 화면은 **받은 값을 되돌려 줄 뿐**이다.
//   화면이 만들면 「무엇을 승인했는가」가 화면의 주장이 된다.
import { apiFetch } from './api';

const BASE = '/api/v1/calculation';

export class CalculationError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'CalculationError';
    this.status = status;
  }
}

async function unwrap<T>(res: Response, what: string): Promise<T> {
  if (!res.ok) {
    let detail = '';
    try {
      detail = (await res.json())?.detail || '';
    } catch {
      /* JSON 이 아니면 상태 코드만으로 말한다 */
    }
    // ★ 상태 코드를 그대로 실어 보낸다 — 화면이 403(환경 아님)·404(없음)·409(그 사이
    //   바뀜)·503(못 읽음)을 **다르게** 그려야 한다. 뭉치면 사용자가 할 일이 안 정해진다.
    throw new CalculationError(detail || `${what}을(를) 불러오지 못했습니다.`, res.status);
  }
  const body = await res.json();
  // ★ 봉투를 벗긴다. `{status, data}` 를 그대로 읽으면 `undefined` 가 나온다.
  return (body?.data ?? body) as T;
}

// ── 준비도 ────────────────────────────────────────────────────────────────

/** 서버 어휘 그대로. ★ `UNKNOWN` 은 **판정하지 않았다**는 뜻이다 — 「아직 안 했다」가 아니다. */
export type GateState = 'READY' | 'NOT_YET' | 'FAILED' | 'UNKNOWN';

export interface Gate {
  gate: string;
  state: GateState;
  summary: string;
  next_action: string;
  detail: Record<string, any>;
}

export interface Readiness {
  status: GateState;
  gates: Gate[];
  next_action: string;
  counts: { ready: number; not_yet: number; failed: number; unknown: number };
}

export async function getReadiness(instanceId: string) {
  const q = instanceId ? `?instance_id=${encodeURIComponent(instanceId)}` : '';
  return unwrap<Readiness>(await apiFetch(`${BASE}/readiness${q}`), '계산 준비 상태');
}

// ── 실행 승인 ─────────────────────────────────────────────────────────────

export interface OutputSpec {
  metric: string;
  unit: string;
  unit_display: string;
  direction: 'UP' | 'DOWN';
}

export interface CapabilityProposalItem {
  ref: string;
  state: string;
  blocked_reason: string;
  definition: {
    relation: string;
    model_version: string;
    outputs: OutputSpec[];
    required_datasets: string[];
    canonical_rules: string[];
  };
  binding: Record<string, any>;
  binding_fingerprint: string;
  /** 인증판이 없는 계약키가 있으면 `false` — 무엇으로 계산할지 모르는 채 승인할 수 없다. */
  approvable: boolean;
  missing_contract_keys: string[];
}

export interface LiveApproval {
  approval_id: string;
  ref: string;
  status: string;
  binding_fingerprint: string;
  valid_until: string;
  approved_by: string;
  data_kind: string;
  entity_mode: string;
}

export interface CapabilityProposal {
  scope: {
    data_kind: string; entity_mode: string; tenant_id: string;
    scope_node_id: string; instance_id: string;
  };
  valid_days: number;
  valid_until: string;
  generated_at: string;
  items: CapabilityProposalItem[];
  approvals: LiveApproval[];
  /** ★ 화면은 이 문장을 **그대로** 보여 준다. 요약하거나 다시 쓰지 않는다. */
  notice: string;
}

export async function getCapabilityProposal(opts: {
  instanceId: string; dataKind?: string; entityMode?: string; validDays?: number;
}) {
  const p = new URLSearchParams({ instance_id: opts.instanceId });
  if (opts.dataKind) p.set('data_kind', opts.dataKind);
  if (opts.entityMode) p.set('entity_mode', opts.entityMode);
  if (opts.validDays) p.set('valid_days', String(opts.validDays));
  return unwrap<CapabilityProposal>(
    await apiFetch(`${BASE}/capabilities?${p}`), '실행 승인 제안서');
}

export async function approveCapabilities(body: {
  instance_id: string;
  refs: string[];
  rationale: string;
  data_kind?: string;
  entity_mode?: string;
  valid_days?: number;
  /** ★★★ **화면이 본 지문.** 사람이 읽고 누르는 사이에 판이 바뀌면 서버가 409 로 되돌린다. */
  seen_fingerprints: Record<string, string>;
}) {
  return unwrap<{ approved: any[]; valid_until: string }>(
    await apiFetch(`${BASE}/capabilities/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), '실행 승인');
}

export async function revokeCapability(approvalId: string, reason: string) {
  return unwrap<any>(
    await apiFetch(`${BASE}/capabilities/${encodeURIComponent(approvalId)}/revoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }), '실행 승인 철회');
}

// ── 시연 초기화 ───────────────────────────────────────────────────────────

export interface ResetBucket {
  kind: string;
  table: string;
  ids?: string[];
  count: number;
  reason?: string;
}

export interface ResetPlan {
  target: {
    instance_id: string; kit_id: string; kit_version: string; kit_mode: string;
    tenant_id: string; scope_node_id: string; entity_mode: string;
  };
  delete: ResetBucket[];
  retain: ResetBucket[];
  /** ⚠️ `count` 가 `null` 이면 **세지 못한 것**이다 — 0 으로 그리지 않는다. */
  preserve: { kind: string; count: number | null; error?: string }[];
  preview: { path_exists: boolean; bytes: number };
  plan_fingerprint: string;
  planned_at: string;
}

export async function getResetPlan(instanceId: string) {
  return unwrap<ResetPlan>(
    await apiFetch(`${BASE}/reset/plan?instance_id=${encodeURIComponent(instanceId)}`),
    '초기화 대상 목록');
}

export interface ResetResult {
  reset_id: string;
  requested_event_id: string;
  completed_event_id: string;
  deleted: Record<string, number>;
  preview_cleared: boolean;
  retained: ResetBucket[];
  preserved: { kind: string; count: number | null }[];
  before_fingerprint: string;
  after_fingerprint: string;
  reset_at: string;
}

export async function runReset(body: {
  instance_id: string;
  reason: string;
  /** ★★★ **재확인.** `getResetPlan` 이 낸 값 그대로 — 화면이 지어내지 않는다. */
  confirm_fingerprint: string;
}) {
  return unwrap<ResetResult>(
    await apiFetch(`${BASE}/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), '시연 초기화');
}

// ── 온톨로지 시작점 · 경로 계산 실행 ─────────────────────────────────────

export interface OntologyObject {
  namespace: string;
  object_type: string;
  object_id: string;
}

export interface ObjectList {
  as_of: string;
  /** ⚠️ `true` 면 목록이 전부가 아니다 — 화면이 그렇게 말해야 한다. */
  truncated: boolean;
  objects: OntologyObject[];
  object_types: string[];
}

export async function listOntologyObjects(opts: {
  asOf: string; objectType?: string; relationTypes?: string[];
}) {
  const p = new URLSearchParams({ as_of: opts.asOf });
  if (opts.objectType) p.set('object_type', opts.objectType);
  if (opts.relationTypes?.length) p.set('relation_types', opts.relationTypes.join(','));
  return unwrap<ObjectList>(
    await apiFetch(`/api/v1/ontology/objects?${p}`), '온톨로지 객체 목록');
}

export interface CalcResult {
  status: 'COMPLETE' | 'BLOCKED';
  query_id: string;
  path_fingerprint: string;
  required_relation_ids: string[];
  request_fingerprint: string;
  result_fingerprint?: string;
  /** ⚠️ `BLOCKED` 면 **비어 있다.** 빈 값을 0 으로 그리지 않는다. */
  metrics: Record<string, Record<string, number | string>>;
  segment_outputs: Record<string, string[]>;
  segment_model_versions: Record<string, string>;
  used_snapshots: Record<string, string>;
  path_model_version?: string;
  blocked?: { public_reason: string; internal_reasons: string[] };
}

export async function runPathCalculation(body: {
  roots: OntologyObject[];
  target_types: string[];
  relation_types: string[];
  as_of: string;
  instance_id: string;
  path_fingerprint?: string;
  assumptions?: Record<string, unknown>;
}) {
  return unwrap<CalcResult>(
    await apiFetch(`${BASE}/path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), '경로 계산');
}


export interface ImpactPath {
  nodes: OntologyObject[];
  edges: { relation_id: string; relation_type_id: string; calculation_ref: string }[];
  path_fingerprint: string;
}

export interface ImpactResult {
  query_id: string;
  status: string;
  as_of: string;
  paths: ImpactPath[];
}

/** 영향 경로 찾기. 계산 **전에** 부른다 — 경로가 여럿이면 사람이 골라야 한다. */
export async function findImpactPaths(body: {
  roots: OntologyObject[];
  target_types: string[];
  relation_types: string[];
  as_of: string;
}) {
  return unwrap<ImpactResult>(
    await apiFetch('/api/v1/ontology/query/impact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, max_depth: 6, max_paths: 20 }),
    }), '영향 경로');
}


export interface DecisionResult {
  decision: null | {
    title: string;
    owner: string;
    due: string;
    evidence: Record<string, any>;
    briefing: string[];
    /** ★ 저장된 안건 id — 이것으로 검토·발간으로 이어 간다. */
    decision_id: string;
    [k: string]: any;
  };
  calculation: CalcResult;
}

/** [G5] 계산 결과를 안건으로. ⚠️ `BLOCKED` 이면 `decision` 이 `null` 로 온다 —
 *  오류가 아니라 **답**이고, 화면은 사유를 그대로 보여 준다. */
export async function runPathDecision(body: {
  roots: OntologyObject[];
  target_types: string[];
  relation_types: string[];
  as_of: string;
  instance_id: string;
  path_fingerprint: string;
  assumptions?: Record<string, unknown>;
  title: string;
  owner: string;
  due: string;
  /** ★★★ 결정 문장 — 제목이 아니다. 「무엇을 승인·기각하는가」. */
  question: string;
  snapshot_ids: string[];
  base_values: Record<string, number>;
  scenario_assumptions: Record<string, number>;
}) {
  return unwrap<DecisionResult>(
    await apiFetch(`${BASE}/path/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), '의사결정 안건');
}
