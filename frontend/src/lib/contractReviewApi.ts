// [I-4 4c-3] 계약 검토 승인·반려 — **파이프라인이 여기서 사람을 기다린다.**
//
// ## ⚠️⚠️ [2026-08-25 실측] 왜 이 파일이 생겼는가
//
// 서버에는 경로가 둘 다 있었다:
//
//     GET  /api/v1/factory/{project_id}/contract-review/pending?task_id=…
//     POST /api/v1/factory/{project_id}/contract-review/decision
//
// 그런데 **프런트에서 부르는 곳이 0건이었다**(전수 확인). SW 생성기가 계약 검토
// 게이트에 닿으면 `ContractReviewPending` 에서 멈추는데, 사용자는 승인할 방법이
// 화면에 없었다 — 「통제는 있는데 부르는 경로가 없다」의 네 번째 자리다.
//
// ★ 지문·승인자·테넌트는 **서버가 파생한다.** 클라이언트가 지문을 실어 보낼 수 있으면
//   「사람이 A 를 보고 B 를 승인하는」 경로가 열린다 — 그래서 보내는 것은 셋뿐이다.
import { apiFetch } from './api';

const BASE = '/api/v1/factory';

async function unwrap<T>(res: Response, what: string): Promise<T> {
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json())?.detail || ''; } catch { /* JSON 이 아닐 수 있다 */ }
    // ⚠️ 실패를 «없음» 으로 바꾸지 않는다 — 409(상태 불일치)와 403(권한)은 할 일이 다르다.
    throw Object.assign(new Error(detail || `${what}에 실패했습니다.`), { status: res.status });
  }
  return (await res.json())?.data as T;
}

export type ContractReviewPending = {
  pending: boolean;
  verdict: string;
  reason: string;
  compiled_fingerprint?: string;
  previous_approved_fingerprint?: string;
  request_event_id?: string;
  requested_at?: string;
  /** ★ **지금 승인을 누를 수 있는가.** 「검토가 필요하다」와 다르다 — 검토 요청은
   *  게이트 노드가 열고, 그래프가 거기 닿기 전에는 열린 요청이 없다. 그때 버튼을
   *  살려 두면 사용자는 누르고 409 를 본다(2026-08-26 실측). */
  actionable?: boolean;
  not_actionable_reason?: string;
};

/** ⚠️ 읽기지만 **쓰기 권한**을 요구한다(서버 규칙) — 승인할 수 없는 사람에게
 *  「승인할 것이 있다」를 알릴 이유가 없다. 403 이면 그 사실을 그대로 전한다. */
export async function getContractReviewPending(projectId: string, taskId: string) {
  const q = new URLSearchParams({ task_id: taskId });
  return unwrap<ContractReviewPending>(
    await apiFetch(`${BASE}/${encodeURIComponent(projectId)}/contract-review/pending?${q}`),
    '계약 검토 확인');
}

export type ContractDecisionResult = {
  decision: string;
  event_id: string;
  request_event_id: string;
  contract_fingerprint: string;
  /** ⚠️ `false` 면 **결정은 원장에 남았지만** 파이프라인 상태 반영이 안 됐다.
   *  다시 승인하면 안 된다 — 재개만 다시 시도한다. */
  state_applied: boolean;
  note?: string;
};

export async function decideContractReview(
  projectId: string, body: { task_id: string; request_event_id: string;
                             decision: 'APPROVE' | 'REJECT'; rationale?: string },
) {
  return unwrap<ContractDecisionResult>(
    await apiFetch(`${BASE}/${encodeURIComponent(projectId)}/contract-review/decision`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), '계약 검토 결정');
}
