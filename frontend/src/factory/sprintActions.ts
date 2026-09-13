// [트랙 E · 7단계 전제] Sprint 실행 명령의 **단일 지점**.
//
// ## 왜 이 파일이 필요한가
//
// `ControlPanel.tsx` 는 Sprint 시작 payload 를 손으로 조립하고, 재개·재분할은 생 `fetch` 로
// 부른다. 새 Studio 가 같은 일을 하려면 두 가지 길이 있다 — **복사하거나, 함께 부르거나.**
//
// ⚠️⚠️ 복사하면 두 화면이 **서로 다른 payload** 를 보낸다. 스키마 버전·`factory_mode`·
//   `master_data` 를 한쪽만 고치는 날이 오고, 그때 「두 화면이 다른 프로젝트를 만든다」가 된다.
//   이 저장소에서 가장 비쌌던 결함 유형이고(WBS 진행 상태가 두 곳에서 다르게 보인 것과 같은
//   구조), 2026-08-06 인수인계가 §4.1 에서 명시적으로 경고한 것이다.
//
// ★ 그래서 **조립과 호출을 여기 하나로 모으고 양쪽이 같은 함수를 부른다.**
//   `clarifyAnswers.ts`(요구 확인 답변 직렬화)와 같은 방식이다.
//
// ## 이 파일이 하지 않는 것
//
// - store 를 읽거나 쓰지 않는다. 순수 함수 + fetch 뿐이다 — 호출부가 자기 상태를 갱신한다.
// - `alert()` 을 쓰지 않는다. 결과를 돌려주고 **문구는 호출부가 화면에 맞게** 보여 준다
//   (Studio 는 화면 안 배너, 종전 통제실은 기존 `alert`).
import { API_BASE_URL } from '../lib/api';
import { executeStudioCommand, hasExecutionPending } from '../lib/studioExecutionApi';
import type { ExecutionOperation, ExecutionRequest } from '../lib/studioExecutionApi';

/** 명령 결과. **성공/실패를 예외가 아니라 값으로** 돌려준다 —
 *  호출부가 `try/catch` 를 빠뜨려도 «성공한 것처럼» 넘어가지 않는다. */
export type CommandOutcome = 'REJECTED' | 'ACCEPTED' | 'UNKNOWN' | 'CONFIRMED';

export type SprintResult = {
  ok: boolean;
  /** 접수와 실제 결과 확인을 구별한다. HTTP 접수만으로 CONFIRMED를 만들지 않는다. */
  outcome: CommandOutcome;
  /** 서버가 준 문구를 그대로 들고 있는다. 화면이 지어내지 않는다. */
  message: string;
  /** 성공 시 서버가 알려 준 태스크 id(재분할처럼 서버가 정하는 경우). */
  taskId?: string;
  hotlTaskId?: string;
  status?: number;
  reasonCode?: string;
  requestId?: string;
};

export type HealingResult =
  | { ok: true; outcome: 'HEAL_STARTED'; taskId: string; message: string; status?: number; requestId?: string }
  | { ok: true; outcome: 'HOTL_PENDING'; hotlTaskId: string; message: string; status?: number; requestId?: string }
  | { ok: false; outcome: 'LOCAL_BLOCKED' | 'REJECTED' | 'UNKNOWN'; message: string;
      reasonCode?: string; status?: number; requestId?: string };

export type ReleaseResult = SprintResult & { releaseId: string | null };
type Reply = Record<string, unknown>;
type AcceptedFields = { taskId?: string; hotlTaskId?: string; releaseId?: string; message?: string };
type HttpResult = SprintResult & { releaseId?: string };

// 같은 브라우저의 Header/RunControls/store가 같은 POST에 동시에 진입하지 않게 한다.
// 서버 멱등성이나 다른 탭의 실행 잠금을 대신하지 않는다.
const pendingProjects = new Set<string>();

export function isProjectCommandPending(projectId: string): boolean {
  return pendingProjects.has(encodeURIComponent(projectId)) || hasExecutionPending(projectId);
}

async function postExecution(projectId: string, operation: ExecutionOperation, taskId: string,
  input: ExecutionRequest['input'], accepted: (reply: Reply) => AcceptedFields | null): Promise<HttpResult> {
  const attempt = await executeStudioCommand(projectId, operation, taskId, input);
  const result = attempt.receipt?.result;
  const reply = record(result?.response);
  const fields = attempt.outcome === 'CONFIRMED' ? accepted(reply) : null;
  const detail = record(reply.detail);
  return { ok: !!fields, outcome: attempt.outcome === 'CONFIRMED' && !fields ? 'UNKNOWN' : attempt.outcome,
    requestId: attempt.request.client_request_id, status: result?.http_status,
    reasonCode: typeof detail.reason_code === 'string' ? detail.reason_code : undefined,
    message: fields ? attempt.message : attempt.outcome === 'CONFIRMED'
      ? '접수 기록은 있으나 실행 결과 형식을 확인하지 못했습니다. 원래 요청을 확인하세요.' : attempt.message,
    ...fields };
}

function record(value: unknown): Reply {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Reply : {};
}

function nonempty(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

export function rejectedCommand(message: string, reasonCode: string): SprintResult {
  return { ok: false, outcome: 'REJECTED', message, reasonCode };
}

/** 5xx는 쓰기 처리 후 실패일 수도 있다. 실패를 무부작용이나 재시도 허가로 해석하지 않는다. */
async function post(
  path: string, body: unknown,
  accepted: (reply: Reply) => AcceptedFields | null,
): Promise<HttpResult> {
  const projectKey = /^\/api\/v1\/factory\/([^/]+)\//.exec(path)?.[1];
  if (!projectKey) return rejectedCommand('명령 대상 경로를 확인하십시오.', 'INVALID_COMMAND_TARGET');
  if (pendingProjects.has(projectKey)) return rejectedCommand(
    '이 프로젝트의 다른 요청 결과를 기다리고 있습니다. 중복 요청하지 마십시오.', 'COMMAND_PENDING');
  // 첫 await 전에 획득하므로 서로 다른 호출부에서도 검사와 획득 사이 경합이 없다.
  pendingProjects.add(projectKey);
  try {
    const r = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const j = record(await r.json().catch(() => null));
    const detail = record(j.detail);
    const serverMessage = [j.detail, detail.message, j.message].find(nonempty);
    const reasonCode = [detail.reason_code, detail.code, j.reason_code].find(nonempty);
    if (!r.ok) {
      const explicit = r.status >= 400 && r.status < 500;
      return {
        ok: false, outcome: explicit ? 'REJECTED' : 'UNKNOWN', status: r.status,
        reasonCode: reasonCode || (explicit ? 'HTTP_REJECTED' : 'SERVER_RESULT_UNKNOWN'),
        message: (serverMessage
          || (r.status === 401 ? '사용자 식별이 필요합니다.'
            : r.status === 403 ? '이 작업을 할 권한이 없습니다.'
              : `요청이 실패했습니다 (${r.status}).`))
          + (explicit ? '' : ' 처리 결과가 미확정입니다. 다시 요청하기 전에 상태를 확인하십시오.'),
      };
    }
    const fields = accepted(j);
    if (!fields) return { ok: false, outcome: 'UNKNOWN', status: r.status,
      reasonCode: 'UNEXPECTED_RESPONSE',
      message: '서버 응답에서 결과를 확인하지 못했습니다. 재전송하지 말고 상태를 확인하십시오.' };
    return { ok: true, outcome: 'ACCEPTED', status: r.status,
      message: serverMessage || '요청이 접수되었습니다. 실제 상태를 확인하십시오.', ...fields };
  } catch {
    return { ok: false, outcome: 'UNKNOWN', reasonCode: 'RESPONSE_LOST',
      message: '응답을 받지 못해 처리 결과가 미확정입니다. 같은 요청을 다시 보내기 전에 상태를 확인하십시오.' };
  } finally {
    // 해제하는 것은 통신 잠금뿐이다. 실행/HOTL/결과 참조는 여기서 변경하지 않는다.
    pendingProjects.delete(projectKey);
  }
}

function taskReply(status: string, taskId?: string) {
  return (reply: Reply): AcceptedFields | null =>
    reply.status === status && nonempty(reply.task_id)
      && (taskId === undefined || reply.task_id === taskId)
      ? { taskId: reply.task_id } : null;
}

function targetError(projectId: string, taskId?: string): SprintResult | null {
  if (!nonempty(projectId)) return rejectedCommand('프로젝트가 선택되지 않았습니다.', 'PROJECT_REQUIRED');
  if (taskId !== undefined && !nonempty(taskId)) {
    return rejectedCommand('대상 작업을 선택한 뒤 다시 확인하십시오.', 'TASK_REQUIRED');
  }
  return null;
}

// ── Sprint 시작 ─────────────────────────────────────────────────────────────
/** 기획 가동 payload. **여기가 유일한 조립 지점이다.**
 *
 *  ⚠️ `factory_mode` 를 호출부에서 다시 적지 않는다. 적는 순간 두 화면이 갈라지기 시작한다.
 *
 *  ⚠️⚠️ `schema_version` 은 **보내지 않는다.** 상태 스키마는 서버가 정한다 — 오래 열어 둔
 *    브라우저가 옛 버전을 다시 실어 보내면 서버 상태를 **다운그레이드**하게 되고, 그때
 *    화면은 아무 오류도 내지 않는다. */
export function buildPlanningPayload(projectId: string, idea: string, masterData: string) {
  return {
    project_name: projectId,
    initial_idea: idea,
    master_data: masterData,
    factory_mode: 'PLANNING',
  };
}

/** 태스크 id 를 만든다. 시작 시각이 들어가므로 **호출부가 같은 규칙을 쓰게** 모아 둔다. */
export function newPlanningTaskId(): string {
  return `PLANNING_${Date.now()}`;
}

export async function startPlanning(
  projectId: string, idea: string, masterData: string, taskId: string,
): Promise<SprintResult> {
  const invalid = targetError(projectId, taskId);
  if (invalid) return invalid;
  if (!nonempty(idea)) return rejectedCommand('기획 아이디어를 입력해 주십시오.', 'IDEA_REQUIRED');
  if (!taskId.startsWith('PLANNING') || taskId.split('_').length !== 2) {
    return rejectedCommand('새 기획 작업 ID가 필요합니다.', 'PLANNING_TASK_REQUIRED');
  }
  return postExecution(projectId, 'START', taskId,
    { initial_idea: idea.trim(), master_data: masterData }, taskReply('started', taskId));
}

/** 누적 산출물·권한·승인 문맥은 서버 원본을 사용하며 사용자 입력 두 필드만 허용한다. */
export type ExistingTaskInput = { initial_idea?: string; master_data?: string };

export function buildExistingTaskPayload(
  projectId: string, taskId: string, input: ExistingTaskInput = {}, feedback = '',
) {
  const payload: Record<string, unknown> = {
    project_name: projectId,
    current_sprint_task_id: taskId,
    factory_mode: taskId.startsWith('TASK_REV_') ? 'REVISION' : 'EXECUTION',
  };
  // state/schema spread 금지. 알 수 없는 속성은 런타임에서도 전송하지 않는다.
  if (typeof input?.initial_idea === 'string') payload.initial_idea = input.initial_idea;
  if (typeof input?.master_data === 'string') payload.master_data = input.master_data;
  if (nonempty(feedback)) {
    payload.reviewer_decision = 'REWORK_DEV';
    payload.reviewer_feedback = `[사용자 재시도 지시]\n${feedback.trim()}`;
    payload.human_feedback_queue = [{ task_id: taskId, feedback: feedback.trim() }];
  }
  return payload;
}

export async function startExistingTask(
  projectId: string, taskId: string, input: ExistingTaskInput = {}, feedback = '',
): Promise<SprintResult> {
  const invalid = targetError(projectId, taskId);
  if (invalid) return invalid;
  if (taskId.startsWith('PLANNING')) {
    if (feedback.trim()) return rejectedCommand('멈춘 기획은 저장된 내용 그대로 재개합니다. 의견은 별도 수정 요청으로 남기세요.', 'RESUME_INPUT_FIXED');
    return postExecution(projectId, 'RESUME', taskId, {}, taskReply('resumed', taskId));
  }
  const content: ExecutionRequest['input'] = {};
  if (typeof input.initial_idea === 'string') content.initial_idea = input.initial_idea;
  if (typeof input.master_data === 'string') content.master_data = input.master_data;
  if (feedback.trim()) content.feedback = feedback.trim();
  return postExecution(projectId, 'START', taskId, content, taskReply('started', taskId));
}

/** 일반 중단/실패 후 동일 작업의 재가동. PLANNING은 저장된 체크포인트의 비파괴 재개만 허용한다.
 * REPLAN은 서버가 같은 ID를 Master_PMO로 라우팅하므로 EXECUTION으로 전송한다. */
export function restartExistingTask(
  projectId: string, taskId: string, input: ExistingTaskInput = {}, feedback = '',
): Promise<SprintResult> {
  return startExistingTask(projectId, taskId, input, feedback);
}

/** 수동 정지 또는 실제 노드 오류 판본의 비파괴 재개. 새 입력/승인은 받지 않는다. */
export async function resumeExistingTask(projectId: string, taskId: string): Promise<SprintResult> {
  const invalid = targetError(projectId, taskId);
  return invalid || postExecution(projectId, 'RESUME', taskId, {}, taskReply('resumed', taskId));
}

export async function pauseSprint(projectId: string, taskId: string): Promise<SprintResult> {
  const invalid = targetError(projectId, taskId);
  if (invalid) return invalid;
  return postExecution(projectId, 'PAUSE', taskId, {}, taskReply('paused', taskId));
}

export async function stopSprint(projectId: string, taskId: string): Promise<SprintResult> {
  const invalid = targetError(projectId, taskId);
  if (invalid) return invalid;
  return postExecution(projectId, 'STOP', taskId, {}, taskReply('stopped', taskId));
}

// ── 재개 (쿼터 회복) ────────────────────────────────────────────────────────
/** ★ **처음부터 다시 돌리는 것이 아니라** 멈춘 지점부터 재개한다.
 *
 *  ⚠️ `taskId` 가 없으면 부르지 않는다 — 서버가 어느 지점을 재개할지 모르고, 그때 «처음부터»
 *    로 떨어지면 이미 쓴 LLM 비용을 다시 쓴다. */
export async function resumeAfterQuota(projectId: string, taskId: string): Promise<SprintResult> {
  const invalid = targetError(projectId, taskId);
  if (invalid) return invalid;
  return postExecution(projectId, 'RESUME_QUOTA', taskId, {}, taskReply('resumed', taskId));
}

// ── 복구 (자가치유) ─────────────────────────────────────────────────────────
/** 화면은 로컬 검사와 관찰을 담당하는 store의 triggerSelfHealing을 사용한다. */
export const SELF_HEAL_NOTE =
  '복구는 새 수정 작업을 요청합니다. 기존 승인 대기가 있으면 먼저 그 결정을 확인합니다. 원래 실패 근거는 유지됩니다.';

export async function requestSelfHealing(projectId: string, errorLog: string, sourceTaskId = 'sprint_init'): Promise<HealingResult> {
  const invalid = targetError(projectId);
  if (invalid) return { ok: false, outcome: 'REJECTED', message: invalid.message, reasonCode: invalid.reasonCode };
  const result = await postExecution(projectId, 'HEAL', sourceTaskId, { error_log: errorLog }, reply => {
      if (reply.status === 'healing_started' && nonempty(reply.task_id) && !reply.hotl_task_id) {
        return { taskId: reply.task_id };
      }
      if (reply.status === 'success' && nonempty(reply.hotl_task_id) && !reply.task_id) {
        return { hotlTaskId: reply.hotl_task_id };
      }
      return null;
    });
  if (result.ok && result.taskId) return { ok: true, outcome: 'HEAL_STARTED', taskId: result.taskId,
    status: result.status, requestId: result.requestId, message: '새 복구 작업의 접수를 확인했습니다. 실제 진행 상태를 확인하십시오.' };
  if (result.ok && result.hotlTaskId) return { ok: true, outcome: 'HOTL_PENDING', hotlTaskId: result.hotlTaskId,
    status: result.status, requestId: result.requestId, message: '기존 승인 대기의 확인이 먼저 필요합니다. 새 복구 실행은 시작되지 않았습니다.' };
  return { ok: false, outcome: result.outcome === 'REJECTED' ? 'REJECTED' : 'UNKNOWN',
    message: result.message, status: result.status, reasonCode: result.reasonCode, requestId: result.requestId };
}

export async function saveProjectRelease(projectId: string): Promise<ReleaseResult> {
  const invalid = targetError(projectId);
  if (invalid) return { ...invalid, releaseId: null };
  const result = await post(`/api/v1/factory/${encodeURIComponent(projectId)}/release`, undefined,
    reply => reply.status === 'success' && nonempty(reply.release_id)
      ? { releaseId: reply.release_id,
          message: nonempty(reply.note) ? reply.note : '릴리스 저장 응답을 받았습니다. 목록에서 결과를 확인하십시오.' }
      : null);
  return { ...result, releaseId: result.releaseId || null };
}

// ── WBS 재분할 ──────────────────────────────────────────────────────────────
/** ★ 기획 산출물(RFP·PRD·UI·아키텍처)은 **그대로 두고** 태스크 분할만 다시 한다.
 *
 *  ⚠️ 되돌릴 수 없다 — 기존 WBS 는 사라진다. 호출부가 **확인을 받은 뒤에** 부를 것. */
export async function replanWbs(projectId: string): Promise<SprintResult> {
  const invalid = targetError(projectId);
  if (invalid) return invalid;
  return post(`/api/v1/factory/${encodeURIComponent(projectId)}/wbs/replan`, undefined, taskReply('started'));
}

export const REPLAN_CONFIRM =
  ('기획 산출물(RFP·PRD·UI·아키텍처)은 유지한 채 WBS 분할만 다시 수행합니다. '
   + '기존 작업 목록은 사라지며 되돌릴 수 없습니다. 진행할까요?');

// ── 피드백 백로그 발행 (Track 2 고객 리뷰 → WBS 추가) ────────────────────────
/** 완료된 산출물을 보고 **수정 요구**를 내면 그것이 새 WBS 작업이 된다.
 *
 * ★ [2026-08-07 전환 게이트] 신규 Studio 에 이 기능이 **없어서** 승격이 막혔다.
 *   §8 기능 게이트의 「HOTL 질문·승인·**수정 요구** 가 보존된다」에 해당한다.
 *   ⚠️ Decision Dock 의 «승인 조건이나 수정 요청» 과 **다른 경로**다 —
 *     그쪽은 지금 멈춰 선 HOTL 작업에 답하는 것(`/hotl/resume`)이고,
 *     이쪽은 이미 끝난 것을 보고 **새 작업을 만드는 것**(`/sprint/revision`)이다.
 *     같은 칸에 묶으면 사용자는 「승인했는데 왜 새 작업이 생겼나」를 묻게 된다.
 */
export async function publishRevisionBacklog(
  projectId: string, feedback: string,
): Promise<SprintResult> {
  const invalid = targetError(projectId);
  if (invalid) return invalid;
  if (!nonempty(feedback)) return rejectedCommand('수정 요구 내용을 입력하십시오.', 'FEEDBACK_REQUIRED');
  return post(`/api/v1/factory/${encodeURIComponent(projectId)}/sprint/revision`,
    { feedback: feedback.trim() }, reply => {
      if (reply.status !== 'success') return null;
      if (nonempty(reply.task_id) && !reply.hotl_task_id) return { taskId: reply.task_id };
      if (nonempty(reply.hotl_task_id) && !reply.task_id) return { hotlTaskId: reply.hotl_task_id,
        message: '기존 승인 대기의 확인이 먼저 필요합니다. 새 수정 작업은 추가되지 않았습니다.' };
      return null;
    });
}

export const REVISION_NOTE =
  ('완료된 산출물에 대한 수정 요구를 새 WBS 작업으로 추가합니다. '
   + '지금 멈춰 선 결정에 답하는 것이 아니라 **다음에 할 일**을 만드는 것입니다.');

// ── Export (산출물 ZIP) ─────────────────────────────────────────────────────
/** 생성된 코드·문서를 zip 으로 내려받는 주소. **fetch 하지 않고 링크로 연다** —
 *  서버가 `Content-Disposition` 으로 파일명을 정하고, 브라우저가 그대로 저장한다.
 *
 *  ★ [2026-08-07 전환 게이트] §8 「Export 가 보존된다」가 신규 Studio 에서 빠져 있었다
 *    (`StageArtifactCanvas` 가 「종전 통제실에서 하십시오」라고 스스로 적어 두었다).
 *  ⚠️ 종전 통제실과 **같은 엔드포인트**를 쓴다 — 여기서 다른 주소를 만들면 두 화면이
 *    다른 것을 내려받게 되고, 그때 어느 쪽이 «진짜 산출물» 인지 알 수 없다. */
export function exportArchiveUrl(projectId: string): string {
  return `${API_BASE_URL}/api/v1/factory/${encodeURIComponent(projectId)}/export`;
}
