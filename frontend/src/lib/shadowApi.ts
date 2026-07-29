// Shadow Mode API 클라이언트 (명세서 §7.3 / §7.4 · M2)
//
// ⚠️ 화면(ShadowModePanel.tsx)과 **의도적으로 분리**한다. 디자인 개편 때 이 파일은 그대로
//   재사용된다. 표현 관련 코드를 두지 않는다(문구·색·레이아웃 금지).
import { API_BASE_URL } from './api';

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `요청 실패 (${r.status})`);
  return j.data as T;
}

// ── 타입 ─────────────────────────────────────────────────────────────────
export type MetricRow = {
  metric: string;
  baseline: number | null;
  candidate: number | null;
  delta?: number;
  delta_pct?: number | null;
  higher_is_better?: boolean;
  // `unmeasured` 는 판정에서 제외된 것이지 0 이 아니다 — 화면에서 섞으면 안 된다.
  verdict: 'improved' | 'regressed' | 'unchanged' | 'unmeasured';
  why?: string;
};

export type Variance = {
  comparable: boolean;
  reason?: string;
  note?: string;
  input_hash?: string;
  baseline_input_hash?: string;
  candidate_input_hash?: string;
  metrics?: MetricRow[];
  improved?: string[];
  regressed?: string[];
  unchanged?: string[];
  unmeasured?: string[];
  verdict?: 'improved' | 'regressed' | 'no_difference';
};

export type ShadowRun = {
  run_id: string;
  name: string;
  candidate_kind: string;
  candidate_ref: string;
  baseline_ref: string;
  evaluation_period: string;
  status: string;
  review_status: 'pending_review' | 'approved' | 'rejected';
  reviewed_by: string;
  review_note: string;
  acknowledged_regressions: string[];
  promotion_scope: string;
  promoted_by: string;
  promoted: boolean;
  enterprise_scope_id: string;
  baseline: { metrics: Record<string, number | null>; input_hash: string } | null;
  candidate: { metrics: Record<string, number | null>; input_hash: string } | null;
  variance: Variance | null;
  note: string;
  created_at: string;
};

export type ShadowSummary = {
  total: number;
  by_review_status: Record<string, number>;
  by_status: Record<string, number>;
  promoted: number;
  incomparable: { run_id: string; name: string; reason: string }[];
  note: string;
};

// ── 호출 ─────────────────────────────────────────────────────────────────
export const fetchSummary = (scopeNodeId = '') =>
  req<ShadowSummary>('GET', `/api/v1/shadow/summary${scopeNodeId ? `?scope_node_id=${encodeURIComponent(scopeNodeId)}` : ''}`);

export const fetchRuns = (scopeNodeId = '') =>
  req<ShadowRun[]>('GET', `/api/v1/shadow/runs${scopeNodeId ? `?scope_node_id=${encodeURIComponent(scopeNodeId)}` : ''}`);

export const fetchRun = (runId: string) =>
  req<ShadowRun>('GET', `/api/v1/shadow/runs/${runId}`);

export const compareRun = (runId: string) =>
  req<Variance>('GET', `/api/v1/shadow/runs/${runId}/compare`);

export const createRun = (body: {
  name: string; candidate_kind: string; enterprise_scope_id: string;
  evaluation_period: string; baseline_ref?: string; candidate_ref?: string;
}) => req<ShadowRun>('POST', '/api/v1/shadow/runs', body);

export const recordSide = (runId: string, body: {
  side: 'baseline' | 'candidate';
  metrics: Record<string, number | null>;
  input_hash?: string; input_snapshot?: unknown; note?: string;
}) => req<ShadowRun>('POST', `/api/v1/shadow/runs/${runId}/sides`, body);

// 악화 항목을 인정하지 않으면 백엔드가 승인을 거절한다 — 그 이유가 오류 메시지로 온다.
export const reviewRun = (runId: string, body: {
  decision: 'approved' | 'rejected'; note?: string; acknowledged_regressions?: string[];
}) => req<ShadowRun>('POST', `/api/v1/shadow/runs/${runId}/review`, body);

export const promoteRun = (runId: string, promotionScope: string) =>
  req<ShadowRun>('POST', `/api/v1/shadow/runs/${runId}/promote`,
                 { promotion_scope: promotionScope });
