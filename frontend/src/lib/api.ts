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

// ★★★ [P0-1C · 2026-08-09] 서버가 이 헤더를 **더 이상 믿지 않는다**(`config.ORG_TRUST_HEADER`
//   기본값 false). 그러므로 기본적으로 **보내지도 않는다.**
//
//   보내도 서버가 무시하니 «무해» 하다고 볼 수도 있지만, 남겨 두면 두 가지가 나빠진다.
//     ① 개발자가 네트워크 탭에서 이 헤더를 보고 «식별은 이걸로 되는구나» 라고 읽는다 —
//        그 오해가 다음 라우트에서 헤더를 다시 신뢰하게 만든다.
//     ② 서버 스위치가 실수로 켜지는 날, 화면이 이미 헤더를 싣고 있으면 **그날 바로** 뚫린다.
//   즉 이 한 줄은 서버 쪽 실수의 «폭발 반경» 을 줄인다.
//
//   ⚠️ 개발 모드에서만 켠다. 서버의 `AFS_DEV_TRUST_HEADER` 와 **짝** 이다 — 한쪽만 켜면
//     안 되고, 둘 다 꺼진 것이 운영 상태다.
const DEV_TRUST_HEADER =
  ((import.meta as any).env?.VITE_DEV_TRUST_HEADER || '') === '1';
const STORAGE_KEY = 'factory.actingUser';

// ── [2026-08-09] 세션 토큰 — **식별의 정본** ────────────────────────────────
//
// ★★★ 종전에는 `actingUser` 기본값이 `'admin'` 이었다. 즉 **로그인 없이 열면 관리자**였고,
//   화면 최상단 전환기로 아무 계정이나 골라 그 권한으로 볼 수 있었다. `api/deps.py` 가
//   「②③ 은 인증이 아니다」라고 못박아 둔 그 상태가 제품 화면에 그대로 있었다.
//
// 이제 로그인이 세션 토큰을 주고, 서버는 **헤더보다 토큰을 먼저** 본다. 토큰이 있으면
// 사용자는 헤더로 다른 사람인 척할 수 없다.
// ⚠️ `actingUser` 는 지우지 않고 **하위호환으로 남긴다** — 토큰이 없는 경로(개발 스크립트·
//   기존 테스트)가 아직 있다. 다만 **기본값을 없앤다**: 로그인하지 않았으면 익명이다.
const SESSION_HEADER = 'X-Session-Token';
const SESSION_KEY = 'factory.sessionToken';

let sessionToken: string =
  (typeof localStorage !== 'undefined' && localStorage.getItem(SESSION_KEY)) || '';

export function getSessionToken(): string {
  return sessionToken;
}

export function setSessionToken(token: string) {
  sessionToken = (token || '').trim();
  try {
    if (sessionToken) localStorage.setItem(SESSION_KEY, sessionToken);
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    // localStorage 가 막힌 환경에서도 동작은 계속돼야 한다
  }
}

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

// ── [D-017 §9 P2-1] 전역 업무 컨텍스트 ──────────────────────────────────────
//
// ★★ 서버는 이미 `X-Enterprise-Tenant` · `X-Enterprise-Scope` · `X-Entity-Mode` 를 읽는다
//   (`api/deps.current_enterprise_context`). 그런데 **화면은 하나도 보내지 않았다.**
//   그래서 서버는 늘 「요청자의 소속 부서」로 되돌아갔고(단계적 도입 fallback), 사용자가
//   무엇을 선택하든 조회 범위는 바뀌지 않았다 — 전환기가 있어도 아무 일도 일어나지 않는 상태다.
//
// ⚠️ **여기 한 곳에서만 싣는다.** 각 API 래퍼가 자기 헤더를 붙이기 시작하면 `api.ts` 머리말이
//   경고한 그 상태(같은 백엔드를 8곳에서 다르게 부르는 것)가 컨텍스트에서 재현된다. 그때는
//   「어떤 화면은 범위가 먹고 어떤 화면은 안 먹는」 형태가 되고, 사용자는 통제가 고장났다고
//   읽는다. 그래서 인터셉터와 `apiUrl()` 둘 다 이 값을 본다.
const TENANT_HEADER = 'X-Enterprise-Tenant';
const SCOPE_HEADER = 'X-Enterprise-Scope';
const MODE_HEADER = 'X-Entity-Mode';
const CTX_KEY = 'factory.enterpriseContext';

export interface EnterpriseContextSelection {
  tenantId: string;
  scopeNodeId: string;
  /** `REAL` | `SIM` 등. 비우면 서버 기본값을 쓴다. */
  entityMode: string;
}

const EMPTY_CTX: EnterpriseContextSelection = { tenantId: '', scopeNodeId: '', entityMode: '' };

let enterpriseContext: EnterpriseContextSelection = (() => {
  try {
    const raw = typeof localStorage !== 'undefined' && localStorage.getItem(CTX_KEY);
    return raw ? { ...EMPTY_CTX, ...(JSON.parse(raw) || {}) } : { ...EMPTY_CTX };
  } catch {
    return { ...EMPTY_CTX };
  }
})();

export function getEnterpriseContext(): EnterpriseContextSelection {
  return enterpriseContext;
}

/** 전역 전환기가 부른다. 부분 갱신을 허용한다(모드만 바꾸는 경우가 흔하다). */
export function setEnterpriseContext(next: Partial<EnterpriseContextSelection>) {
  enterpriseContext = {
    tenantId: (next.tenantId ?? enterpriseContext.tenantId ?? '').trim(),
    scopeNodeId: (next.scopeNodeId ?? enterpriseContext.scopeNodeId ?? '').trim(),
    entityMode: (next.entityMode ?? enterpriseContext.entityMode ?? '').trim(),
  };
  try {
    if (enterpriseContext.tenantId || enterpriseContext.scopeNodeId || enterpriseContext.entityMode) {
      localStorage.setItem(CTX_KEY, JSON.stringify(enterpriseContext));
    } else {
      localStorage.removeItem(CTX_KEY);
    }
  } catch {
    // localStorage 가 막힌 환경에서도 동작은 계속돼야 한다
  }
  // ★★★ [G1-C1.2] **범위를 바꾸면 실시간 연결도 다시 맺어야 한다.**
  //   SSE 티켓에는 발급 시점의 조직 범위가 **봉인**돼 있다. 화면만 A 회사로 바꾸고 스트림을
  //   그대로 두면, 목록은 A 인데 실시간 이벤트는 계속 B 로 흐른다 — 사용자는 자기가 보는
  //   숫자가 어느 회사 것인지 알 수 없다. 그 어긋남은 새로고침해야만 사라진다.
  try {
    window.dispatchEvent(new CustomEvent('factory:enterprise-context-changed'));
  } catch {
    // 이벤트를 못 쏘는 환경(테스트 등)에서도 컨텍스트 저장 자체는 성공해야 한다
  }
}

// SSE(EventSource)·iframe·다운로드 링크는 헤더를 붙일 수 없다. 쿼리로 실어 보낸다.
export function apiUrl(path: string): string {
  const base = path.startsWith('http') ? path : `${API_BASE_URL}${path}`;
  const parts: string[] = [];
  // ⚠️ [P0-1C] `as_user` 를 더는 싣지 않는다. 서버가 읽지 않고(스위치 꺼짐), SSE 는 1회용
  //   접속표로 갔다(P0-1B). 남겨 두면 **다운로드 URL 이 접근 로그에 사용자 id 를 흘린다.**
  if (DEV_TRUST_HEADER && actingUser) parts.push(`as_user=${encodeURIComponent(actingUser)}`);
  // ⚠️ 쿼리 이름은 서버가 읽는 것과 **정확히** 같아야 한다
  //   (`deps.current_enterprise_context`: `enterprise_scope` · `entity_mode`).
  //   테넌트는 서버가 쿼리로는 받지 않는다 — 여기서 지어내지 않는다.
  if (enterpriseContext.scopeNodeId) {
    parts.push(`enterprise_scope=${encodeURIComponent(enterpriseContext.scopeNodeId)}`);
  }
  if (enterpriseContext.entityMode) {
    parts.push(`entity_mode=${encodeURIComponent(enterpriseContext.entityMode)}`);
  }
  if (!parts.length) return base;
  return base + (base.includes('?') ? '&' : '?') + parts.join('&');
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
      //   [P2-1] 업무 컨텍스트도 같은 판정 아래 둔다 — 「어느 조직의 무엇을 보고 있는가」는
      //   사용자 식별만큼이나 밖으로 나가면 안 되는 정보다.
      const ctx = enterpriseContext;
      const hasCtx = !!(ctx.tenantId || ctx.scopeNodeId || ctx.entityMode);
      if ((actingUser || sessionToken || hasCtx) && url && isBackendUrl(url)) {
        const headers = new Headers(
          (init && init.headers) || (input instanceof Request ? input.headers : undefined)
        );
        // ★ 이미 붙어 있으면 덮어쓰지 않는다 — 호출부가 일부러 다른 범위를 지정한 경우가 있다
        //   (예: 관리자 화면이 특정 조직을 대신 조회). 전역값이 그것을 이기면 조용히 틀어진다.
        // ★ 세션 토큰을 먼저 싣는다 — 서버가 이것을 헤더보다 우선한다.
        if (sessionToken && !headers.has(SESSION_HEADER)) {
          headers.set(SESSION_HEADER, sessionToken);
        }
        // ⚠️ 개발 모드에서만 싣는다(위 `DEV_TRUST_HEADER` 주석). 운영에서는 세션 토큰만이
        //   신원이고, 그래서 이 줄은 실행되지 않는다.
        if (DEV_TRUST_HEADER && actingUser && !headers.has(USER_HEADER)) {
          headers.set(USER_HEADER, actingUser);
        }
        if (ctx.tenantId && !headers.has(TENANT_HEADER)) headers.set(TENANT_HEADER, ctx.tenantId);
        if (ctx.scopeNodeId && !headers.has(SCOPE_HEADER)) headers.set(SCOPE_HEADER, ctx.scopeNodeId);
        if (ctx.entityMode && !headers.has(MODE_HEADER)) headers.set(MODE_HEADER, ctx.entityMode);
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
