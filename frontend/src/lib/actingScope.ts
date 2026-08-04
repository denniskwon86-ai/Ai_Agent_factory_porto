// [이관 3/10] 지금 활동 중인 사용자가 **실제로 할 수 있는 일** — 화면 공용 단일 지점
//
// ★★ 왜 만들었는가(2026-08-04 실측 결함):
//   Jarvis 가 익명 사용자에게 «할 수 있는 일: 유형 생성 · 레코드 등록» 을 그대로 말했다.
//   누르면 403 이다. 비서가 «된다»고 한 것이 안 되면 사용자는 권한 문제를 자기 조작 실수로
//   오해하고, 같은 조작을 반복한다. 그때는 목록 조회 상태(`Loaded.status`)로 우회했지만,
//   그건 «읽을 수 있는가»일 뿐 «쓸 수 있는가»가 아니다 — 읽기는 되고 쓰기는 안 되는 사용자가
//   대다수다(일반 사용자 전원).
//
// ⚠️ **권한을 여기서 새로 판정하지 않는다.** 판정은 서버(`api/deps.py`)가 하고, 이 모듈은
//   `/api/v1/org/me` 가 준 결과를 옮기기만 한다. 화면이 자기 규칙을 세우면 서버가 통제를
//   바꿀 때 화면만 옛 규칙으로 남고, 그 어긋남은 «버튼은 보이는데 403» 으로 나타난다.
//
// 캐시는 모듈 스코프 1개다. 사용자가 바뀌면 즉시 버린다 — 이전 사용자의 권한으로 다음 사용자의
// 화면을 그리는 것이 가장 위험한 잔상이다.
import { API_BASE_URL } from './api';

export type ActingScope = {
  userId: string;
  displayName: string;
  /** 서버가 이 요청자를 식별했는가(익명이 아닌가). */
  identified: boolean;
  /** 조직도에 등록된 계정인가. 식별됐지만 미등록일 수 있다. */
  registered: boolean;
  retired: boolean;
  unrestricted: boolean;
  /** 업무표준·기준정보를 개정할 수 있는가(DA·관리자). */
  canManageStandard: boolean;
  canEditOrg: boolean;
  canRunEnterprise: boolean;
};

/** 아직 모르는 상태. ⚠️ 기본값은 **모두 거짓**이다 — 모르는 동안 «할 수 있다»고 그리면
 *  그 짧은 순간에 사용자가 누르고 403 을 받는다(관문 A 의 «미지정 = 비노출»과 같은 이유). */
export const UNKNOWN_SCOPE: ActingScope = {
  userId: '', displayName: '', identified: false, registered: false, retired: false,
  unrestricted: false, canManageStandard: false, canEditOrg: false, canRunEnterprise: false,
};

function parse(d: any): ActingScope {
  return {
    userId: String(d?.user_id || ''),
    displayName: String(d?.display_name || ''),
    identified: Boolean(d?.identified),
    registered: Boolean(d?.registered),
    retired: Boolean(d?.retired),
    unrestricted: Boolean(d?.unrestricted),
    canManageStandard: Boolean(d?.can_manage_standard),
    canEditOrg: Boolean(d?.can_edit_org),
    canRunEnterprise: Boolean(d?.can_run_enterprise),
  };
}

let cached: ActingScope | null = null;
let inflight: Promise<ActingScope> | null = null;
const listeners = new Set<(s: ActingScope) => void>();

async function fetchScope(): Promise<ActingScope> {
  const r = await fetch(`${API_BASE_URL}/api/v1/org/me`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`권한 조회 실패 (${r.status})`);
  return parse(j?.data);
}

export const actingScope = {
  /** 지금 아는 값. 아직 모르면 `null` — «권한 없음»(UNKNOWN_SCOPE)과 구분한다. */
  peek: (): ActingScope | null => cached,

  /** 한 번만 조회한다. 여러 화면이 동시에 열려도 요청은 하나다. */
  load: (): Promise<ActingScope> => {
    if (cached) return Promise.resolve(cached);
    if (!inflight) {
      inflight = fetchScope()
        .then((s) => { cached = s; listeners.forEach((f) => f(s)); return s; })
        .finally(() => { inflight = null; });
    }
    return inflight;
  },

  subscribe: (fn: (s: ActingScope) => void): (() => void) => {
    listeners.add(fn);
    // ⚠️ `Set.delete` 는 boolean 을 돌려준다. 그대로 반환하면 React 가 정리 함수로 오인해
    //   타입 오류가 난다(2026-08-04 `jarvisSession` 에서 실제로 겪었다).
    return () => { listeners.delete(fn); };
  },

  /** 사용자 전환 시 즉시 폐기. 다음 조회는 새로 나간다. */
  clear: () => { cached = null; inflight = null; listeners.forEach((f) => f(UNKNOWN_SCOPE)); },
};

if (typeof window !== 'undefined') {
  window.addEventListener('factory:acting-user-changed', () => actingScope.clear());
}
