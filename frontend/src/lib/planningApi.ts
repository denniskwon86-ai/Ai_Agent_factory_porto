// [M4] 경영계획 API 클라이언트 (명세서 §11 / §17)
//
// ⚠️ 화면과 분리한다(governanceApi·qualityApi 와 같은 관례). 디자인 시안 확정 후 화면은
//   교체 대상이지만 이 파일은 재사용된다 — 표현(문구·색·레이아웃)을 두지 않는다.
import { API_BASE_URL } from './api';

/** §11.3 — 이 넷을 절대 섞지 않는다. */
export const VALUE_KINDS = ['ACTUAL', 'PLAN', 'FORECAST', 'SCENARIO'] as const;
export type ValueKind = (typeof VALUE_KINDS)[number];

export type PLResult = {
  lines: Record<string, number>;
  gross_profit: number;
  operating_profit: number;
  pretax_profit: number;
  net_profit: number;
  /** 등록되지 않은 계정 — 비어 있지 않으면 **합계에서 빠진 금액이 있다**. */
  unmapped: { account_code: string; amount: number; why?: string }[];
  complete: boolean;
  engine_version: string;
};

export type ScenarioRun = {
  run_id: string;
  /** 서버가 발급한 결속용 기준선 식별자. 화면에는 기간·기준선명으로 표시한다. */
  baseline_id: string;
  scenario_id: string;
  input_hash: string;
  engine_version: string;
  baseline: PLResult;
  result: PLResult;
  delta: { gross_profit: number; operating_profit: number; net_profit: number };
  /** 적용되지 않은 가정 — "넣었는데 결과가 그대로"의 유일한 단서. */
  unapplied_assumptions: string[];
  assumptions_count: number;
};

export type ScenarioComparison = {
  org_id: string;
  period: string;
  baseline_kind: string;
  engine_version: string;
  scenarios: {
    scenario_id: string; run_id: string; input_hash: string;
    operating_profit: number; net_profit: number; delta_net: number;
    unapplied_assumptions: string[]; complete: boolean;
  }[];
  /** false 면 서로 다른 기준선에서 계산된 것이다 — **그 비교는 무효다**. */
  same_baseline: boolean;
};

export type Variance = {
  org_id: string;
  period: string;
  /** false 면 한쪽 데이터가 없어 **차이를 계산하지 않았다**(0 이 아니다). */
  comparable: boolean;
  reason?: string;
  note?: string;
  plan?: PLResult;
  actual?: PLResult;
  diff?: { operating_profit: number; net_profit: number };
  by_account?: {
    account_code: string; plan: number | null; actual: number | null;
    diff: number | null; missing: string;
  }[];
};

export type Account = {
  account_code: string; name: string; category: string; sign: number;
};

export type Scenario = {
  scenario_id: string; name: string; org_id: string; baseline_kind: string; status: string;
};

/** ⚠️ [이관 F 6/8] 상태 코드를 실어 던진다 — 화면이 «권한이 없어 못 봤다» 와 «서버가 죽었다»
 *  를 구분해야 한다. `closedLoopFetch.ApiError`·`shadowApi`·`workspaceApi` 와 같은 규약이다. */
export type ApiError = Error & { status?: number };

function fail(status: number, j: any): never {
  const d = j?.detail;
  const msg = typeof d === 'string' ? d
    : Array.isArray(d) ? d.map((e: any) => e?.msg || JSON.stringify(e)).join(' · ')
      : `요청 실패 (${status})`;
  const err = new Error(msg) as ApiError;
  err.status = status;
  throw err;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) fail(r.status, j);
  return j.data as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) fail(r.status, j);
  return j.data as T;
}

export const fetchAccounts = () => get<Account[]>('/api/v1/planning/accounts');

export const fetchScenarios = (orgId?: string) =>
  get<Scenario[]>(`/api/v1/planning/scenarios${orgId ? `?org_id=${encodeURIComponent(orgId)}` : ''}`);

export const fetchFacts = (orgId: string, period: string, valueKind?: ValueKind) =>
  get<any[]>(`/api/v1/planning/facts?org_id=${encodeURIComponent(orgId)}` +
    `&period=${encodeURIComponent(period)}${valueKind ? `&value_kind=${valueKind}` : ''}`);

export const runScenario = (scenarioId: string, orgId: string, period: string) =>
  post<ScenarioRun>(`/api/v1/planning/scenarios/${encodeURIComponent(scenarioId)}/run`,
    { org_id: orgId, period });

export const compareScenarios = (scenarioIds: string[], orgId: string, period: string) =>
  post<ScenarioComparison>('/api/v1/planning/scenarios/compare',
    { scenario_ids: scenarioIds, org_id: orgId, period });

export const fetchVariance = (orgId: string, period: string) =>
  get<Variance>(`/api/v1/planning/variance?org_id=${encodeURIComponent(orgId)}` +
    `&period=${encodeURIComponent(period)}`);

// ── 승인 흐름 ─────────────────────────────────────────────────────────────
export type Submission = {
  submission_id: string; org_id: string; period: string; value_kind: string;
  status: 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED';
  submitted_by: string; submitted_at: string;
  approved_by: string; approved_at: string; approved_fingerprint: string;
  reject_reason: string;
};

/** 승인 후 값이 바뀌었는가. **상태(APPROVED)만 보면 알 수 없다.** */
export type Integrity = {
  submission_id: string; status: string;
  /** false = 승인된 제출이 아니라 판정 자체가 불가 — '이상 없음'이 아니다. */
  verifiable: boolean;
  intact?: boolean;
  approved_fingerprint?: string; current_fingerprint?: string;
  approved_by?: string; approved_at?: string;
  message?: string; reason?: string; note?: string;
};

export const fetchSubmissions = (orgId: string, period: string) =>
  get<Submission[]>(`/api/v1/planning/submissions?org_id=${encodeURIComponent(orgId)}` +
    `&period=${encodeURIComponent(period)}`);

export const fetchCurrentApproved = (orgId: string, period: string) =>
  get<(Submission & { integrity: Integrity }) | null>(
    `/api/v1/planning/submissions/current?org_id=${encodeURIComponent(orgId)}` +
    `&period=${encodeURIComponent(period)}`);

// ── 현금흐름 ──────────────────────────────────────────────────────────────
/** `computable=false` 는 **계산하지 않은 것**이다(0 이 아니다). */
export type CashFlow = {
  computable: boolean;
  missing?: string[];
  reason?: string; note?: string;
  net_profit?: number;
  operating_cf?: number; investing_cf?: number; financing_cf?: number;
  free_cash_flow?: number; net_change?: number;
  components?: Record<string, number>;
  pl_complete?: boolean;
};

export const fetchCashFlow = (orgId: string, period: string, valueKind: ValueKind = 'PLAN') =>
  get<CashFlow>(`/api/v1/planning/cash-flow?org_id=${encodeURIComponent(orgId)}` +
    `&period=${encodeURIComponent(period)}&value_kind=${valueKind}`);

// ── Backtest ──────────────────────────────────────────────────────────────
export type Backtest = {
  measurable: boolean;
  reason?: string; note?: string;
  mape?: number | null;
  /** 부호 오차 — 늘 과대추정하는 모델은 절대오차가 작아도 위험하다. */
  bias?: number | null;
  worst?: { account_code: string; pct_error: number } | null;
  by_account?: {
    account_code: string; predicted: number; actual: number;
    error: number; pct_error: number | null;
  }[];
  excluded_zero_actual?: string[];
  only_predicted?: string[]; only_actual?: string[];
  /** true = 가정이 대상 기간 이후에 작성됨 — 그 오차는 실제 예측력이 아니다. */
  lookahead_risk?: boolean;
  warnings?: string[];
};

export const fetchBacktestPlan = (orgId: string, period: string) =>
  get<Backtest>(`/api/v1/planning/backtest/plan?org_id=${encodeURIComponent(orgId)}` +
    `&period=${encodeURIComponent(period)}`);

// ── 롤업 충돌(이중 계상) ──────────────────────────────────────────────────
export type RollupCheck = {
  has_conflict: boolean;
  conflicts: {
    org_id: string; account_code: string; period: string; value_kind: string;
    total_row_amount: number; detail_sum: number; detail_rows: number;
    naive_sum: number; matches: boolean; why: string;
  }[];
  note: string;
};

export const fetchRollupCheck = (orgId: string, period: string, valueKind: ValueKind = 'PLAN') =>
  get<RollupCheck>(`/api/v1/planning/rollup-check?org_id=${encodeURIComponent(orgId)}` +
    `&period=${encodeURIComponent(period)}&value_kind=${valueKind}`);
