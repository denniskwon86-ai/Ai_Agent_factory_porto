// 업무·데이터 설계 상담사 API 클라이언트 (마스터 명세서 §4.6 / M0)
//
// ⚠️ 화면(AdvisorPanel.tsx)과 **의도적으로 분리**한다. 디자인 시안이 확정되면 화면을 대대적으로
//   개편할 예정이므로, 그때 이 파일은 **그대로 재사용**되어야 한다. 따라서 여기에는 표현 관련
//   코드를 절대 두지 않는다(문구·색·레이아웃 금지, 데이터 형태와 호출만).
//
// 인증: `installFetchInterceptor` 가 **세션 토큰**(`X-Session-Token`)을 자동으로 붙인다
//   (lib/api.ts). ⚠️ [P0-1C] 종전에는 `X-Factory-User` 라고 적혀 있었다 — 그 헤더는 서버가
//   더 이상 믿지 않으며 개발 모드에서만 실린다.
// ECM 문맥 헤더(X-Enterprise-Scope 등)는 전역 컨텍스트 스위처가 생기면 인터셉터에 추가한다 —
//   지금은 백엔드가 요청자의 소속 부서를 기본 범위로 쓴다(ECM-lite 단계적 도입).
import { API_BASE_URL } from './api';

// ── 타입 ─────────────────────────────────────────────────────────────────
export type PlaybookSummary = {
  playbook_id: string;
  name_ko: string;
  description: string;
  business_type: string;
  question_count: number;
  requirement_count: number;
  recommended_template_id: string;
};

export type QuestionOption = {
  label: string;
  description: string;
  recommended: boolean;
  value: string;
  unlocks_requirements?: string[];
};

export type Question = {
  id: string;
  question: string;
  why: string;
  stage: string;
  multi: boolean;
  options: QuestionOption[];
};

export type Progress = { answered: number; total: number; complete: boolean };

/** 준비도 산정 결과. `measurable_max` 가 100 미만이면 그 구간은 **측정되지 않은** 것이다
 *  (만점 처리하지 않는다 — 정의가 없는 것이 준비됐다는 뜻은 아니다). */
export type Readiness = {
  score: number;
  measurable_max: number;
  unmeasured_weight: number;
  dimensions: {
    dimension: string; name_ko: string; weight: number;
    earned: number; possible: number; measured: boolean; score: number;
  }[];
  gaps: {
    key: string; canonical_term: string; requirement_type: string; necessity: string;
    status: string; owner_department: string; impact: string; next_action: string;
    counts_toward_score: boolean;
  }[];
  blocking_gaps: Readiness['gaps'];
  evaluated_requirements: number;
};

export type Consultation = {
  consultation_id: string;
  user_id: string;
  owner_dept_id: string;
  tenant_id: string;
  enterprise_scope_id: string;
  entity_mode: string;
  scope: string;
  playbook_id: string;
  status: string;
  initial_prompt: string;
  created_at: string;
  updated_at: string;
};

export type Turn = {
  turn_no: number; speaker: string; message: string;
  question_id: string; question_type: string;
  option_set: QuestionOption[]; selected_values: string[]; created_at: string;
};

export type BlueprintRequirement = {
  key: string; canonical_term: string; requirement_type: string; necessity: string;
  data_kind: string; purpose: string; expected_grain: string; freshness_requirement: string;
  owner_department: string; source_candidates: string[]; readiness_status: string;
  gap_impact: string; next_action: string;
  external?: { grade: string; acceptable_latency: string; vintage_required: boolean;
               canonical_source_hint: string } | null;
};

export type Blueprint = {
  blueprint_id: string; consultation_id: string; title: string; business_domain: string;
  playbook_id: string; owner_dept_id: string; owner_user_id: string;
  tenant_id: string; enterprise_scope_id: string; entity_mode: string;
  business: {
    objective: string; problem: string; users: string[]; decision_makers: string[];
    in_scope: string[]; out_of_scope: string[];
  };
  kpis: { name: string; formula: string; unit: string; baseline_date: string;
          tolerance: string; data_kind: string }[];
  data_requirements: BlueprintRequirement[];
  system: { recommended_apps: string[]; screens: string[]; apis: string[];
            template_id: string; agents: string[] };
  risks: { category: string; description: string; mitigation: string }[];
  readiness_score: number;
  readiness: Readiness;
  recommended_sequence: string[];
  status: string;
  provenance: Record<string, { origin: string; confirmed: boolean; note: string }>;
  approved_by: string; approved_at: string; rejected_reason: string; version: number;
  // GET 단건에서만 채워지는 파생 필드
  unverified_kpis?: string[];
  blocking_gap_count?: number;
};

export type LedgerEvent = {
  event_id: string; seq: number; event_type: string; subject_type: string; subject_id: string;
  actor_type: string; actor_id: string; decision: string; rationale: string;
  evidence_refs: any[]; is_substantiated: boolean; created_at: string;
  enterprise_scope_id: string; entity_mode: string; event_hash: string;
};

/** 요구사항 보유 상태. `held`=보유 / `needs_verification`=검증 필요 / `missing`=부족.
 *  ⚠️ 지정하지 않으면 백엔드가 `missing` 으로 본다(모르는 것을 보유로 치지 않는다). */
export type ReqStatus = 'held' | 'needs_verification' | 'missing';

// ── 호출 ─────────────────────────────────────────────────────────────────
// ⚠️ 파라미터 프로퍼티(`public status`)를 쓰지 않는다 — 이 프로젝트는 `erasableSyntaxOnly` 라
//   빌드(`tsc -b`)에서 거부된다. `tsc --noEmit` 만으로는 안 걸리므로 실제 빌드로 확인해야 한다.
class AdvisorApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...(init || {}),
    headers: { 'Content-Type': 'application/json', ...((init && init.headers) || {}) },
  });
  let body: any = null;
  try { body = await res.json(); } catch { /* 본문 없는 응답도 있다 */ }
  if (!res.ok) {
    // 백엔드는 사람이 읽을 수 있는 한국어 사유를 detail 에 담는다. 그것을 그대로 보여준다 —
    // 임의로 다시 쓰면 "왜 막혔는지"가 흐려진다(예: 가상 문맥 생성 차단 사유, 승인 전 부트스트랩).
    throw new AdvisorApiError(body?.detail || `요청 실패 (HTTP ${res.status})`, res.status);
  }
  return (body?.data ?? body) as T;
}

export const advisorApi = {
  listPlaybooks: () => call<PlaybookSummary[]>('/api/v1/advisor/playbooks'),

  listConsultations: () => call<Consultation[]>('/api/v1/advisor/consultations'),

  start: (initial_prompt: string, playbook_id: string, scope = 'department') =>
    call<{ consultation: Consultation; next_question: Question | null; progress: Progress | null }>(
      '/api/v1/advisor/consultations',
      { method: 'POST', body: JSON.stringify({ initial_prompt, playbook_id, scope }) }),

  answer: (id: string, question_id: string, selected_values: string[], message = '') =>
    call<{ next_question: Question | null; progress: Progress | null; readiness_preview: Readiness | null }>(
      `/api/v1/advisor/consultations/${id}/messages`,
      { method: 'POST', body: JSON.stringify({ question_id, selected_values, message }) }),

  get: (id: string) =>
    call<{ consultation: Consultation; turns: Turn[]; answers: Record<string, string[]>;
           next_question: Question | null; progress: Progress | null; blueprints: any[] }>(
      `/api/v1/advisor/consultations/${id}`),

  draftBlueprint: (id: string, statuses: Record<string, ReqStatus>) =>
    call<Blueprint>(`/api/v1/advisor/consultations/${id}/blueprint`,
      { method: 'POST', body: JSON.stringify({ statuses }) }),

  getBlueprint: (id: string) => call<Blueprint>(`/api/v1/advisor/blueprints/${id}`),

  decide: (id: string, decision: 'approved' | 'rejected', reason = '') =>
    call<{ blueprint_id: string; status: string; approved_by: string; approved_at: string;
           readiness_score: number; approved_with_blocking_gaps: string[];
           unverified_kpis: string[] }>(
      `/api/v1/advisor/blueprints/${id}/approve`,
      { method: 'POST', body: JSON.stringify({ decision, reason }) }),

  bootstrapProject: (id: string, project_name: string, template_id = '') =>
    call<{ project_id: string; project_name: string; template_id: string; blueprint_id: string; entity_mode: string;
           enterprise_scope_id: string; next_step: string }>(
      `/api/v1/advisor/blueprints/${id}/bootstrap-project`,
      { method: 'POST', body: JSON.stringify({ project_name, template_id }) }),

  createDataTasks: (id: string, project_id: string) =>
    call<{ created: { task_id: string; canonical_term: string; owner_department: string;
                      necessity: string; status: string }[]; project_id?: string; message?: string }>(
      `/api/v1/advisor/blueprints/${id}/create-data-tasks?project_id=${encodeURIComponent(project_id)}`,
      { method: 'POST' }),

  /** 이 청사진에서 파생된 **모든** 결정 이력(오래된 것부터).
   *  ⚠️ `subjects/blueprint/{id}/history` 는 subject 가 blueprint 인 것만 준다 —
   *    프로젝트 생성·데이터 태스크 확정 이벤트는 subject 가 project 라서 빠진다(실측으로 확인).
   *    사용자가 보고 싶은 것은 "이 청사진으로 무슨 일이 일어났나"이므로 blueprint_id 로 묶는다. */
  ledgerHistory: async (blueprintId: string) => {
    const rows = await call<LedgerEvent[]>(
      `/api/v1/ledger/events?blueprint_id=${encodeURIComponent(blueprintId)}&limit=100`);
    return rows.slice().sort((a, b) => a.seq - b.seq);
  },
};

// ── 표시용 상수 (표현이 아니라 도메인 어휘 — 개편 후에도 같은 뜻이어야 한다) ─────
export const REQ_STATUS_KO: Record<ReqStatus, string> = {
  held: '보유', needs_verification: '검증 필요', missing: '부족',
};

export const DATA_KIND_KO: Record<string, string> = {
  actual: '실제', plan: '계획', forecast: '전망', scenario: '시나리오',
  reference: '기준정보', event: '사건', competitor: '경쟁사',
};

export const NECESSITY_KO: Record<string, string> = {
  required: '필수', recommended: '권장', optional: '선택',
};

export const REQ_TYPE_KO: Record<string, string> = {
  master: '기준정보', actual: '실적', driver: '동인', external: '외부지표',
};
