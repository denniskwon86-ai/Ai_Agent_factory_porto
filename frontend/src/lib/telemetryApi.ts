// 운영 계기판 API 클라이언트 (§10.3 `llm_calls`).
//
// ⚠️ 화면과 **의도적으로 분리**한다(`qualityApi.ts`·`governanceApi.ts` 와 같은 관례).
//   표현(문구·색·레이아웃)을 여기 두지 않는다.
//
// ★ 종전 `TelemetryPanel` 은 화면 안에서 raw `fetch` 를 하고 `.catch(() => setData(null))`
//   로 끝냈다. 그래서 **403·네트워크 장애가 「기록된 호출이 없습니다」로 표시**됐다 —
//   운영 계기판에서 「호출 0건」은 「아무 일도 안 일어났다」로 읽히므로, 못 본 것을 없는 것으로
//   보여주는 것이 이 화면에서 가장 위험한 거짓말이다. 상태 코드를 살려 올린다.
import { closedLoopFetch } from './closedLoopFetch';

export type TelemetryProject = {
  project: string;
  project_id?: string;
  owner_dept_id?: string;
};

export type TelemetryTotals = {
  calls: number;
  success_rate?: number;
  fallback_rate?: number;
  fallback_calls?: number;
  downgraded_calls?: number;
  total_duration_s?: number;
  cost_usd?: number;
  /** false 면 총액은 **하한**이다 — 0 으로 채워 완전한 총액처럼 보이게 하지 않는다. */
  cost_complete?: boolean;
  unpriced_calls?: number;
  cost_partial_calls?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
};

export type TelemetrySummary = {
  totals: TelemetryTotals;
  by_model: Record<string, number>;
  by_stage: Record<string, { calls: number; ok: number; avg_duration_s: number;
    models?: Record<string, number> }>;
  by_requested_tier: Record<string, { calls: number; downgraded: number }>;
  by_cost_basis: Record<string, { calls: number; cost_usd?: number }>;
  by_provider: Record<string, { calls: number; cost_usd?: number }>;
  record_count: number;
  project: string;
  /** 스코프에서 빠진 건수. **조용히 빼면 집계가 작아진 줄도 모른다.** */
  permission: {
    scope?: string;
    excluded_other_dept?: number;
    excluded_unattributed?: number;
  };
};

export const telemetryApi = {
  projects: () => closedLoopFetch<TelemetryProject[]>('GET', '/api/v1/telemetry/projects'),

  summary: (project: string) => closedLoopFetch<TelemetrySummary>(
    'GET',
    `/api/v1/telemetry/summary${project ? `?project=${encodeURIComponent(project)}` : ''}`,
  ),
};
