// 백엔드 접근의 단일 지점 (설계서 Phase 2).
//
// ⚠️ 왜 필요한가: 공통 클라이언트가 없어 raw fetch() 가 78곳에 흩어져 있고 API_BASE_URL 이
//   8곳에 중복 선언돼 있다. 사용자 식별 헤더를 붙이려면 78곳을 다 고쳐야 하는데, 하나라도
//   빠뜨리면 그 경로만 조용히 익명으로 나간다.
//   → fetch 를 한 번 감싸서 **코드 수정 0으로 전체를 덮는다.** 점진 리팩터링은 그 위에서 한다.

export const API_BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8080';

const USER_HEADER = 'X-Factory-User';
const STORAGE_KEY = 'factory.actingUser';

let actingUser: string =
  (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY)) || '';

export function getActingUser(): string {
  return actingUser;
}

export function setActingUser(userId: string) {
  actingUser = (userId || '').trim();
  try {
    if (actingUser) localStorage.setItem(STORAGE_KEY, actingUser);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // localStorage 가 막힌 환경(사파리 프라이빗 등)에서도 동작은 계속돼야 한다
  }
}

// SSE(EventSource)·iframe·다운로드 링크는 헤더를 붙일 수 없다. 쿼리로 실어 보낸다.
export function apiUrl(path: string): string {
  const base = path.startsWith('http') ? path : `${API_BASE_URL}${path}`;
  if (!actingUser) return base;
  return base + (base.includes('?') ? '&' : '?') + `as_user=${encodeURIComponent(actingUser)}`;
}

let installed = false;

/** window.fetch 를 1회 래핑해 우리 백엔드 요청에만 식별 헤더를 붙인다. */
export function installFetchInterceptor() {
  if (installed || typeof window === 'undefined' || !window.fetch) return;
  installed = true;
  const original = window.fetch.bind(window);

  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    try {
      const url =
        typeof input === 'string' ? input
        : input instanceof URL ? input.toString()
        : (input as Request).url;

      // ⚠️ 우리 백엔드로 가는 요청에만 붙인다. 외부 도메인에 사용자 식별을 흘리면 안 된다.
      if (actingUser && url && url.startsWith(API_BASE_URL)) {
        const headers = new Headers(
          (init && init.headers) || (input instanceof Request ? input.headers : undefined)
        );
        if (!headers.has(USER_HEADER)) headers.set(USER_HEADER, actingUser);
        return original(input as any, { ...(init || {}), headers });
      }
    } catch {
      // 인터셉터 버그가 앱 전체의 통신을 죽이면 안 된다 — 원본으로 통과시킨다
    }
    return original(input as any, init);
  }) as typeof window.fetch;
}

/** 명시적으로 쓰고 싶을 때의 얇은 헬퍼. 인터셉터가 이미 헤더를 붙이므로 편의용이다. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path.startsWith('http') ? path : `${API_BASE_URL}${path}`, init);
}
