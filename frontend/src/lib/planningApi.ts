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

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `요청 실패 (${r.status})`);
  return j.data as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `요청 실패 (${r.status})`);
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
