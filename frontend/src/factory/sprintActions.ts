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

/** 명령 결과. **성공/실패를 예외가 아니라 값으로** 돌려준다 —
 *  호출부가 `try/catch` 를 빠뜨려도 «성공한 것처럼» 넘어가지 않는다. */
export type SprintResult = {
  ok: boolean;
  /** 서버가 준 문구를 그대로 들고 있는다. 화면이 지어내지 않는다. */
  message: string;
  /** 성공 시 서버가 알려 준 태스크 id(재분할처럼 서버가 정하는 경우). */
  taskId?: string;
  status?: number;
};

async function post(path: string, body?: unknown): Promise<SprintResult> {
  try {
    const r = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const j = await r.json().catch(() => ({} as any));
    if (!r.ok) {
      return {
        ok: false, status: r.status,
        // 401 과 403 을 뭉개지 않는다 — 사용자가 해야 할 일이 다르다.
        message: j?.detail
          || (r.status === 401 ? '사용자 식별이 필요합니다.'
            : r.status === 403 ? '이 작업을 할 권한이 없습니다.'
              : `요청이 실패했습니다 (${r.status}).`),
      };
    }
    return { ok: true, message: j?.message || '', taskId: j?.task_id, status: r.status };
  } catch (e: any) {
    return { ok: false, message: `서버에 연결하지 못했습니다: ${e?.message || e}` };
  }
}

// ── Sprint 시작 ─────────────────────────────────────────────────────────────
/** 기획 가동 payload. **여기가 유일한 조립 지점이다.**
 *
 *  ⚠️ `schema_version`·`factory_mode` 를 호출부에서 다시 적지 않는다. 적는 순간 두 화면이
 *    갈라지기 시작한다. */
export function buildPlanningPayload(projectId: string, idea: string, masterData: string) {
  return {
    schema_version: '5.1.0',
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
  if (!projectId) return { ok: false, message: '프로젝트가 선택되지 않았습니다.' };
  if (!idea.trim()) return { ok: false, message: '기획 아이디어를 입력해 주십시오.' };
  return post(`/api/v1/factory/${encodeURIComponent(projectId)}/sprint/start`, {
    task_id: taskId,
    project_state_payload: buildPlanningPayload(projectId, idea.trim(), masterData),
  });
}

// ── 재개 (쿼터 회복) ────────────────────────────────────────────────────────
/** ★ **처음부터 다시 돌리는 것이 아니라** 멈춘 지점부터 재개한다.
 *
 *  ⚠️ `taskId` 가 없으면 부르지 않는다 — 서버가 어느 지점을 재개할지 모르고, 그때 «처음부터»
 *    로 떨어지면 이미 쓴 LLM 비용을 다시 쓴다. */
export async function resumeAfterQuota(projectId: string, taskId: string): Promise<SprintResult> {
  if (!taskId) {
    return {
      ok: false,
      message: ('재개할 보류 지점을 모릅니다 — 화면을 새로고침해 상태를 다시 받아 주십시오. '
                + '지금 처음부터 실행하면 이미 지난 단계의 비용을 다시 쓰게 됩니다.'),
    };
  }
  const r = await post(`/api/v1/factory/${encodeURIComponent(projectId)}/sprint/resume-quota`,
    { task_id: taskId });
  if (!r.ok && !r.message.includes('쿼터')) {
    r.message += ' 쿼터가 아직 회복되지 않았을 수 있습니다.';
  }
  return r;
}

// ── 복구 (자가치유) ─────────────────────────────────────────────────────────
/** 자가치유는 store 액션(`triggerSelfHealing`)이 이미 있다. 여기서는 **부르지 않고** 호출부가
 *  그 액션을 쓰게 둔다 — 두 경로를 만들면 또 갈라진다.
 *  이 상수는 두 화면이 같은 안내 문구를 쓰게 하려고 둔다. */
export const SELF_HEAL_NOTE =
  '실패한 단계를 자동으로 다시 시도합니다. 원인이 코드가 아니라 입력이면 같은 실패가 반복됩니다.';

// ── WBS 재분할 ──────────────────────────────────────────────────────────────
/** ★ 기획 산출물(RFP·PRD·UI·아키텍처)은 **그대로 두고** 태스크 분할만 다시 한다.
 *
 *  ⚠️ 되돌릴 수 없다 — 기존 WBS 는 사라진다. 호출부가 **확인을 받은 뒤에** 부를 것. */
export async function replanWbs(projectId: string): Promise<SprintResult> {
  if (!projectId) return { ok: false, message: '프로젝트가 선택되지 않았습니다.' };
  return post(`/api/v1/factory/${encodeURIComponent(projectId)}/wbs/replan`);
}

export const REPLAN_CONFIRM =
  ('기획 산출물(RFP·PRD·UI·아키텍처)은 유지한 채 WBS 분할만 다시 수행합니다. '
   + '기존 작업 목록은 사라지며 되돌릴 수 없습니다. 진행할까요?');
