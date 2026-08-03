// [CL-4 선행] Jarvis 문맥 계약 — **화면마다 임시 응답을 복제하지 않기 위한 단일 지점**
//
// ⚠️ 교차검토 지적 3: CL-1 의 Jarvis 는 고정 질문 3개를 문자열 조건으로 판별해 정해진 답을
//   출력하고 있었다. 그 상태로 CL-2~5 를 만들면 **화면 5개에 각자 다른 가짜 응답**이 생긴다.
//   그래서 문맥 계약과 호출을 여기 한 곳에 둔다.
//
// ★ 서버는 이 문맥을 **그대로 신뢰하지 않는다.** 회사 범위·사용자는 서버가 다시 판정해 덮어쓴다
//   (`api/routes/jarvis_control.py`). 여기서 보내는 것은 "화면이 무엇을 보고 있는가"뿐이다.
import { API_BASE_URL } from './api';

export type JarvisContext = {
  /** 'collaboration' | 'decision' | 'publication' … 화면 식별자 */
  current_module: string;
  /** 'app_delivery' | 'decision_case' | 'release' … */
  selected_object_type?: string;
  /** ⚠️ 화면이 **강조 중인** 객체와 같아야 한다. 다르면 사용자는 A 를 보면서 B 의 답을 읽는다. */
  selected_object_id?: string;
  object_snapshot?: Record<string, unknown>;
  available_actions?: string[];
  evidence_refs?: Record<string, unknown>[];
};

export type JarvisTurn = {
  role: 'user' | 'assistant';
  text: string;
  at: string;
  /** 그 답이 어떤 객체에 대한 것이었는지 — 나중에 대화를 되짚을 때 필요하다. */
  objectId?: string;
};

export type JarvisAnswer = { reply: string; intervene: boolean };

async function req<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(j?.detail || `요청 실패 (${r.status})`) as Error & { status?: number };
    e.status = r.status;
    throw e;
  }
  return j.data as T;
}

export const jarvisApi = {
  /** 기존 Supervisor(=Jarvis) 엔진에 문맥을 붙여 넘긴다. 새 엔진이 아니다(§3). */
  ask: (message: string, context: JarvisContext, projectId = '') =>
    req<JarvisAnswer>('/api/v1/jarvis/ask', { message, context, project_id: projectId }),

  contract: () => req<{ fields: string[]; task_id_required: boolean }>(
    '/api/v1/jarvis/context-contract'),
};

// ── 전역 대화 이력 ──────────────────────────────────────────────────────────
// ★ 화면을 옮겨도 대화가 초기화되지 않아야 한다(§CL-FE-02). 그래서 이력을 **모듈 스코프**에 둔다 —
//   컴포넌트 state 에 두면 화면 전환마다 사라지고, 사용자는 같은 질문을 다시 해야 한다.
// ⚠️ 사용자가 바뀌면 반드시 비운다. 남겨 두면 다른 사용자의 대화가 화면에 남는다.
let turns: JarvisTurn[] = [];
const listeners = new Set<() => void>();

function emit() { listeners.forEach((l) => l()); }

export const jarvisSession = {
  turns: () => turns,
  // cleanup 은 **void** 를 돌려야 한다 — `Set.delete` 의 boolean 을 그대로 반환하면
  //   React 가 그것을 Destructor 로 받지 못한다(tsc 가 잡았다).
  subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn); }; },
  push(turn: JarvisTurn) { turns = [...turns, turn].slice(-40); emit(); },
  clear() { turns = []; emit(); },
};

if (typeof window !== 'undefined') {
  // 사용자 전환 = 문맥이 완전히 바뀐 것. 이전 대화를 남기지 않는다.
  window.addEventListener('factory:acting-user-changed', () => jarvisSession.clear());
}
