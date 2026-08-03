// [CL-2] 폐루프(협업·의사결정·발간) 공용 요청 헬퍼.
//
// 왜 별도 파일인가: CL-1(`collaborationApi`)과 CL-2(`decisionApi`)는 **같은 오류 규약**을 쓴다
// (작업서 §3-10 · `api/routes/decision_control.py` 머리말).
//   · 401 사용자 미식별  · 422 형식 오류  · 404 내 것이 아님(존재를 알리지 않는다)  · 400 정책 위반
// 복사해 두면 한쪽만 고쳐지고, 그 순간 같은 오류가 화면마다 다른 문구로 나온다.
//
// ★ `API_BASE_URL` 을 다시 선언하지 않는다. 예전에 `KnowledgeHubPanel` 이 자기 `localhost:8080`
//   을 선언해 인터셉터(`127.0.0.1` 기준)가 식별 헤더를 못 붙였고, 그 화면의 모든 호출이 조용히
//   익명으로 나갔다. 여기서는 공용 `lib/api.ts` 만 쓴다.
import { API_BASE_URL } from './api';

export type ApiError = Error & { status?: number };

export async function closedLoopFetch<T>(
  method: string, path: string, body?: unknown,
): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    // 422 는 FastAPI 가 detail 을 배열로 준다 — 그대로 `[object Object]` 로 보여주지 않는다.
    const d = (j as any)?.detail;
    const msg = typeof d === 'string' ? d
      : Array.isArray(d) ? d.map((e: any) => e?.msg || JSON.stringify(e)).join(' · ')
        : `요청 실패 (${r.status})`;
    const err = new Error(msg) as ApiError;
    err.status = r.status;
    throw err;
  }
  return (j as any).data as T;
}

/** 상태 코드별 제목. **401 과 404 를 같은 문구로 뭉개지 않는다** — 사용자가 해야 할 일이 다르다. */
export function errorTitle(status?: number): string {
  if (status === 401) return '사용자 지정이 필요합니다';
  if (status === 404) return '찾을 수 없습니다';
  if (status === 422) return '입력 형식이 올바르지 않습니다';
  if (status === 400) return '진행할 수 없는 요청입니다';
  return '오류';
}
