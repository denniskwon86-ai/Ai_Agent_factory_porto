// 백엔드 접근의 단일 지점 (설계서 Phase 2).
//
// ⚠️ 왜 필요한가: 공통 클라이언트가 없어 raw fetch() 가 78곳에 흩어져 있고 API_BASE_URL 이
//   8곳에 중복 선언돼 있다. 사용자 식별 헤더를 붙이려면 78곳을 다 고쳐야 하는데, 하나라도
//   빠뜨리면 그 경로만 조용히 익명으로 나간다.
//   → fetch 를 한 번 감싸서 **코드 수정 0으로 전체를 덮는다.** 점진 리팩터링은 그 위에서 한다.

// ⚠️ 기본값이 `localhost` 가 아니라 **`127.0.0.1`** 인 이유 (2026-07-29 실측):
//   백엔드(`run.py`)는 `0.0.0.0` 에 바인딩되는데 Windows 에서 이것은 **IPv4 전용**이다.
//   그런데 브라우저는 `localhost` 를 `::1`(IPv6)로 **먼저** 해석하므로, 서버가 정상 기동한
//   상태에서도 **브라우저에서만 전 API 가 `Failed to fetch`** 가 된다.
//   서버측 스크립트·카나리는 127.0.0.1 로 붙어 멀쩡하기 때문에 원인이 프론트에 있는 것처럼
//   보이고, 프론트 코드를 아무리 봐도 답이 안 나온다.
//   ★ 서버 바인딩을 `::` 로 바꾸면 이번엔 IPv6 전용이 되어 127.0.0.1 을 쓰는 기존 스크립트가
//     전부 깨진다. 그래서 **주소를 명시**하는 쪽으로 해결한다.
//   원격 백엔드를 쓸 때는 `VITE_API_BASE_URL` 로 덮어쓴다.
export const API_BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8080';

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

// ★★★ [2026-07-31 실측 결함] **같은 백엔드를 다른 이름으로 부르면 헤더가 빠졌다.**
//
//   `KnowledgeHubPanel.tsx` 는 자기만의 `API_BASE_URL` 을 `http://localhost:8080` 으로
//   선언했다(위 주석이 경고한 "8곳 중복 선언" 중 하나다). 인터셉터는 `startsWith(API_BASE_URL)`
//   즉 `http://127.0.0.1:8080` 으로만 판정했으므로, 그 패널의 모든 호출이 **조용히 익명으로**
//   나갔다. 목록 통제를 켠 뒤 실측한 결과: 무제한 권한 관리자로 접속했는데도 지식 허브 화면이
//   "등록된 지식팩이 없습니다"였다(런처의 같은 목록은 4건이 보였다).
//
//   ⚠️ 같은 대상을 두 이름으로 부르는 것이 원인이다 — 문자열 비교는 그 둘을 다른 것으로 본다.
//     그래서 문자열이 아니라 **origin(호스트+포트)** 으로 판정하고, 같은 포트의 루프백 별칭
//     (`localhost` / `127.0.0.1` / `[::1]`)을 같은 백엔드로 취급한다. 중복 선언을 전부 찾아
//     고치는 것보다 이 한 곳을 고치는 것이 안전하다(새로 생기는 중복까지 덮는다).
//   ⚠️ 루프백에 한정한다 — 임의 호스트를 같은 것으로 보면 외부 도메인에 사용자 식별이 새어나간다.
const _LOOPBACK = ['localhost', '127.0.0.1', '[::1]'];
const _backendOrigins: Set<string> = (() => {
  const set = new Set<string>();
  try {
    const u = new URL(API_BASE_URL);
    set.add(u.origin);
    if (_LOOPBACK.includes(u.hostname)) {
      for (const h of _LOOPBACK) set.add(`${u.protocol}//${h}${u.port ? ':' + u.port : ''}`);
    }
  } catch {
    // URL 파싱 실패 시엔 아무 origin 도 등록하지 않는다 — 헤더를 못 붙이는 쪽이 안전하다
  }
  return set;
})();

/** 이 URL 이 우리 백엔드인가(호스트 표기가 달라도 같은 것으로 본다). */
export function isBackendUrl(url: string): boolean {
  try {
    return _backendOrigins.has(new URL(url, window.location.href).origin);
  } catch {
    return false;
  }
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
      if (actingUser && url && isBackendUrl(url)) {
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
