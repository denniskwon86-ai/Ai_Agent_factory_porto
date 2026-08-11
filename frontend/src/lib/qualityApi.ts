// 품질 결과 API 클라이언트 (명세서 §10.3 `quality_outcomes` / §8.3 실패 원인 분류)
//
// ⚠️ 화면과 **의도적으로 분리**한다(governanceApi.ts 와 같은 관례). 디자인 시안 확정 후
//   화면은 교체 대상이지만 이 파일은 그대로 재사용된다 — 표현(문구·색·레이아웃)을 두지 않는다.
import { API_BASE_URL } from './api';

// §8.3 이 정한 여섯 가지. **여기에 없는 어휘를 화면이 만들어내면 안 된다** —
// 통계의 축이 두 벌이 되는 순간 어느 쪽이 요구사항인지 알 수 없게 된다.
export const ROOT_CAUSES = [
  'model_quality',
  'insufficient_context',
  'output_contract',
  'external_environment',
  'test_harness',
  'requirement_ambiguity',
] as const;
export type RootCause = (typeof ROOT_CAUSES)[number] | 'unclassified';

export type QualitySummary = {
  totals: { evaluations: number; passed: number; failed: number };
  by_gate: Record<string, {
    evaluations: number; passed: number; failed: number;
    rollback: number; max_gate_loops: number; max_dev_retries: number;
  }>;
  by_artifact_type: Record<string, { evaluations: number; passed: number; failed: number }>;
  by_root_cause: Record<string, number>;
  unclassified_failures: number;
  /** 실패가 0건이면 null — 0.0 으로 채우면 '미분류 없음(건강함)'으로 잘못 읽힌다. */
  unclassified_ratio: number | null;
  /** 3칸이다. `no_human_decision` 을 승인 쪽에 합치지 말 것. */
  human_acceptance: { accepted: number; revision_requested: number; no_human_decision: number };
  note: string;
  project: string;
  permission: { scope: string; excluded_unattributed: number; excluded_other_dept: number };
};

export type QualityOutcome = {
  outcome_id: string;
  ts: string;
  project: string;
  project_id: string;
  owner_dept_id: string;
  task_id: string;
  gate_name: string;
  artifact_type: string;
  verdict: string;
  pass_fail: string;
  score: number | null;
  threshold: number | null;
  gate_loops: number;
  dev_retry_count: number;
  blocking_fails: string[];
  failed_checks: string[];
  root_cause: RootCause;
  root_cause_rule: string;
  rework_reason: string;
  /** null = 사용자 판정이 **없다**(승인 아님). */
  human_acceptance: 'accepted' | 'revision_requested' | null;
  classified_by?: string;
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `요청 실패 (${r.status})`);
  return j.data as T;
}

function q(path: string, project?: string): string {
  return project ? `${path}?project=${encodeURIComponent(project)}` : path;
}

export const fetchQualitySummary = (project?: string) =>
  get<QualitySummary>(q('/api/v1/telemetry/quality/summary', project));

export const fetchUnclassifiedFailures = (project?: string) =>
  get<QualityOutcome[]>(q('/api/v1/telemetry/quality/unclassified', project));

export const fetchQualityRaw = (project?: string) =>
  get<QualityOutcome[]>(q('/api/v1/telemetry/quality/raw', project));

/** 사후 분류. 식별(로그인 세션)이 없으면 서버가 401 로 거절한다 — 익명 분류는 받지 않는다.
 *  ⚠️ [P0-1C] 종전에는 `X-Factory-User` 라고 적혀 있었다. 그 헤더로는 이제 신원이 서지 않는다. */
export async function classifyFailure(outcomeId: string, rootCause: RootCause, note = '') {
  const r = await fetch(`${API_BASE_URL}/api/v1/telemetry/quality/classify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ outcome_id: outcomeId, root_cause: rootCause, note }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `분류 실패 (${r.status})`);
  return j.data;
}
