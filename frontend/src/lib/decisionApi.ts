// [CL-2] Decision Package API 클라이언트 — 작업서 §CL-BE-03.
//
// 이 화면이 반드시 지켜야 하는 것(백엔드가 이미 그렇게 만들어져 있다 — 화면이 무너뜨리지 않는다):
//   ① 세 관점은 **하나의 문서의 다른 렌더링**이다. 화면은 `package_version`·`evidence_hash` 를
//      항상 함께 보여 참석자가 같은 근거를 보고 있음을 눈으로 확인할 수 있어야 한다.
//   ② `missing: true` 섹션을 **숨기지 않는다.** 숨기면 검토자는 그 항목이 검토됐다고 믿는다.
//   ③ 결정 차단 사유(`blockers`)를 결정 버튼 옆에 그대로 노출한다. 버튼만 비활성화하면
//      사용자는 화면이 고장 났다고 생각하고, 진짜 이유(근거가 바뀌었다)는 전달되지 않는다.
//   ④ **미측정을 0 으로 표시하지 않는다.** 0 은 "효과가 없었다"이고 미측정은 "아직 모른다"다.
import { closedLoopFetch as req } from './closedLoopFetch';
import type { ChipTone } from '../design/HubShell';

export type DecisionStatus =
  | 'DRAFT' | 'REVIEW_REQUESTED' | 'IN_REVIEW' | 'MEETING_REQUESTED'
  | 'EVIDENCE_CHANGED' | 'DECIDED' | 'ACTIONED' | 'EFFECT_MEASURED' | 'CANCELLED';

export type DecisionRole = 'REQUESTER' | 'DECIDER' | 'AFFECTED';
export type ResponseStatus = 'AGREE' | 'CONDITIONAL' | 'DISAGREE' | 'NEED_INFO';
export type Outcome = 'APPROVED' | 'CONDITIONAL' | 'REJECTED' | 'DEFERRED';
export type ViewKey = 'requester' | 'decider' | 'affected';

export type Blocker = { code: string; reason: string };

export type Participant = {
  decision_id: string; user_id: string; role: DecisionRole; scope_id: string;
  response_status: '' | ResponseStatus; response: string; responded_at: string;
};

export type Meeting = {
  meeting_id: string; decision_id: string; title: string; schedule: string; channel: string;
  status: string; external_ref: string; requested_by: string; created_at: string;
  agenda: Record<string, any>; external_created: boolean; note?: string;
};

export type DecisionAction = {
  action_id: string; decision_id: string; owner_scope_id: string; owner_user_id: string;
  action: string; due_at: string; status: 'OPEN' | 'MEASURED' | string;
  measured_effect: string; measured_at: string;
};

export type DecisionCase = {
  decision_id: string; tenant_id: string; scope_id: string; simulation_run_id: string;
  baseline_id: string; scenario_id: string; question: string;
  package: Record<string, any>; evidence: Record<string, any>;
  evidence_hash: string; package_version: number;
  status: DecisionStatus; due_at: string; overdue: boolean;
  outcome: '' | Outcome; outcome_conditions: string; decided_by: string; decided_at: string;
  created_by: string; created_at: string; updated_at: string;
  participants: Participant[]; meetings: Meeting[]; actions: DecisionAction[];
  my_role: '' | DecisionRole; blockers: Blocker[]; can_decide: boolean;
  note?: string;
};

export type DecisionSourceOption = {
  /** 내부 결속용이며 화면에 문자열로 표시하지 않는다. */
  run_id: string;
  label: string;
  scenario_label: string;
  baseline_label: string;
  completed_at: string;
  engine_version: string;
  bindable: boolean;
  blocked_reason: string;
};

export type ViewSection = { key: string; label: string; value: any; missing: boolean };

export type RenderedView = {
  decision_id: string; view: ViewKey; package_version: number; evidence_hash: string;
  question: string; status: DecisionStatus; due_at: string; baseline_id: string;
  simulation_run_id: string; identity_note: string;
  sections: ViewSection[]; blockers: Blocker[];
  decision_form?: { outcomes: Outcome[]; requires_conditions_for: Outcome[] };
  response_form?: { options: ResponseStatus[]; note: string };
};

export type ViewsBundle = {
  views: Record<ViewKey, RenderedView>;
  /** 세 관점이 같은 문서인지 **서버가 판정한 값**. 화면이 다시 계산하지 않는다. */
  same_package: boolean;
  package_version: number | null;
  evidence_hash: string | null;
};

export const decisionApi = {
  sources: () => req<DecisionSourceOption[]>('GET', '/api/v1/decisions/sources'),

  create: (runId: string, body: {
    question: string; package: Record<string, any>; evidence?: Record<string, any>;
    due_at?: string;
  }) => req<DecisionCase>(
    'POST', `/api/v1/simulations/${encodeURIComponent(runId)}/decision-cases`, body),

  queue: () => req<DecisionCase[]>('GET', '/api/v1/decisions/queue'),

  get: (id: string) => req<DecisionCase>('GET', `/api/v1/decisions/${id}`),

  views: (id: string) => req<ViewsBundle>('POST', `/api/v1/decisions/${id}/generate-views`),

  requestReview: (id: string, participants: { user_id: string; role: DecisionRole; scope_id?: string }[]) =>
    req<DecisionCase>('POST', `/api/v1/decisions/${id}/request-review`, { participants }),

  requestMeeting: (id: string, body: { title: string; schedule?: string; channel?: string }) =>
    req<DecisionCase>('POST', `/api/v1/decisions/${id}/request-meeting`, body),

  respond: (id: string, response_status: ResponseStatus, response = '') =>
    req<DecisionCase>('POST', `/api/v1/decisions/${id}/participant-response`,
      { response_status, response }),

  decide: (id: string, body: { outcome: Outcome; rationale: string; conditions?: string }) =>
    req<DecisionCase>('POST', `/api/v1/decisions/${id}/decide`, body),

  createActions: (id: string, actions: {
    action: string; owner_user_id: string; due_at: string; owner_scope_id?: string;
  }[]) => req<DecisionCase>('POST', `/api/v1/decisions/${id}/create-actions`, { actions }),

  measureEffect: (id: string, action_id: string, measured_effect: string) =>
    req<DecisionCase>('POST', `/api/v1/decisions/${id}/measure-effect`,
      { action_id, measured_effect }),
};

/** 상태 표시. **`EVIDENCE_CHANGED` 를 단순 경고가 아니라 빨강으로 둔다** — 그 상태의 안건은
 *  참석자가 읽은 숫자와 저장된 숫자가 다르다는 뜻이고, 그대로 결정하면 회의록이 거짓이 된다. */
export const DECISION_STATUS_KO: Record<DecisionStatus, { label: string; tone: ChipTone }> = {
  DRAFT: { label: '작성 중', tone: 'muted' },
  REVIEW_REQUESTED: { label: '검토 요청됨', tone: 'warn' },
  IN_REVIEW: { label: '검토 중', tone: 'data' },
  MEETING_REQUESTED: { label: '회의 요청됨', tone: 'data' },
  EVIDENCE_CHANGED: { label: '근거 변경됨', tone: 'danger' },
  DECIDED: { label: '결정됨', tone: 'success' },
  ACTIONED: { label: '실행과제 생성', tone: 'success' },
  EFFECT_MEASURED: { label: '효과 측정됨', tone: 'success' },
  CANCELLED: { label: '취소됨', tone: 'muted' },
};

export const ROLE_KO: Record<DecisionRole, string> = {
  REQUESTER: '요청자', DECIDER: '의사결정자', AFFECTED: '영향부서',
};

export const VIEW_KO: Record<ViewKey, { label: string; who: string }> = {
  requester: { label: '요청자 검토서', who: '무엇을 왜 요청했는가' },
  decider: { label: '의사결정자 검토서', who: '무엇을 승인·기각하는가' },
  affected: { label: '영향부서 검토서', who: '우리 업무가 어떻게 바뀌는가' },
};

/** 영향부서 의견. **'정보 부족'이 1급 선택지인 것이 요점이다** — 없으면 모르는 부서가 '동의'를
 *  누르고, 그 동의가 결정의 근거로 쓰인다(도메인 §7.5). */
export const RESPONSE_KO: Record<ResponseStatus, { label: string; hint: string; tone: ChipTone }> = {
  AGREE: { label: '동의', hint: '이대로 진행해도 됩니다', tone: 'success' },
  CONDITIONAL: { label: '조건부 동의', hint: '조건을 적어야 합니다', tone: 'warn' },
  DISAGREE: { label: '반대', hint: '이유를 적어야 합니다', tone: 'danger' },
  NEED_INFO: { label: '정보 부족', hint: '무엇이 더 필요한지 적어야 합니다', tone: 'data' },
};

export const OUTCOME_KO: Record<Outcome, { label: string; hint: string }> = {
  APPROVED: { label: '승인', hint: '조건 없이 진행합니다' },
  CONDITIONAL: { label: '조건부 승인', hint: '조건을 반드시 적습니다 — 조건 없는 조건부는 그냥 승인입니다' },
  REJECTED: { label: '기각', hint: '진행하지 않습니다' },
  DEFERRED: { label: '보류', hint: '지금 결정하지 않습니다' },
};

/** 새 안건 작성 폼의 섹션 목록.
 *
 * ⚠️ 이 라벨의 **원본은 `core/decision_case.py` 의 `render_view()`** 다. 여기 있는 것은 작성
 *   폼용 사본이고, 화면에 보이는 검토서는 항상 서버가 준 `sections` 를 렌더링한다 — 사본이
 *   낡아도 검토서가 틀려지지는 않는다(작성 폼의 안내 문구만 낡는다). */
export const PACKAGE_FIELDS: { key: string; label: string; view: ViewKey; required?: boolean }[] = [
  { key: 'baseline', label: '기준안(무행동 포함)', view: 'decider', required: true },
  { key: 'options', label: '권고안·대안 비교', view: 'decider', required: true },
  { key: 'problem', label: '현업 문제와 배경', view: 'requester' },
  { key: 'why_simulated', label: '시뮬레이션을 수행한 이유', view: 'requester' },
  { key: 'recommendation', label: '요청자의 권고안', view: 'requester' },
  { key: 'asks', label: '요청 예산·정책·인력·설비·일정', view: 'requester' },
  { key: 'expected_effect', label: '기대효과', view: 'requester' },
  { key: 'open_risks', label: '미결 리스크', view: 'requester' },
  { key: 'followups', label: '요청자가 책임질 후속 행동', view: 'requester' },
  { key: 'impact_if_rejected', label: '반려·지연 시 업무 영향', view: 'requester' },
  { key: 'executive_brief', label: '1페이지 요약', view: 'decider' },
  { key: 'financial_impact', label: '손익·현금·투자회수', view: 'decider' },
  { key: 'sensitivity', label: '최악/기준/최선과 민감도', view: 'decider' },
  { key: 'reversible', label: '되돌릴 수 있는 결정인가', view: 'decider' },
  { key: 'compliance_risk', label: '규정·안전·품질·평판 리스크', view: 'decider' },
  { key: 'dissent', label: '반대 의견과 불확실성', view: 'decider' },
  { key: 'approval_conditions', label: '승인 시 조건과 중간 점검 기준', view: 'decider' },
  { key: 'dept_changes', label: '바뀌는 업무·KPI·책임', view: 'affected' },
  { key: 'data_to_provide', label: '제공해야 할 데이터', view: 'affected' },
  { key: 'resource_impact', label: '인력·설비·재고·일정·원가 영향', view: 'affected' },
  { key: 'dependencies', label: '선행·후행 부서 의존성', view: 'affected' },
  { key: 'conflicts', label: '예상 충돌·병목·예외', view: 'affected' },
];
