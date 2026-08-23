// [UI 설계서 §5.8] 설정·관리자 콘솔이 읽는 것.
//
// ⚠️ 화면과 분리한다 — `workspaceApi`·`shadowApi` 와 같은 관례다.
//
// ## 이 파일이 하지 않는 것
//
// **판정하지 않는다.** 강제 여부·기한·감사 건수는 전부 서버가 정한 값을 그대로 나른다.
// 화면이 다시 계산하면 「정책 파일은 켜져 있는데 화면은 꺼졌다고 말하는」 상태가 만들어진다 —
// 이 저장소가 `ORG_ENFORCE` 에서 실제로 겪은 일이다.
import { API_BASE_URL } from './api';

export type ApiError = Error & { status?: number };

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = (j as any)?.detail;
    const msg = typeof d === 'string' ? d
      : Array.isArray(d) ? d.map((e: any) => e?.msg || JSON.stringify(e)).join(' · ')
        : `요청 실패 (${r.status})`;
    const err = new Error(msg) as ApiError;
    err.status = r.status;
    throw err;
  }
  return j.data as T;
}

/** 정책 변경 이력 한 줄 — [설계 §5.8] 「운영 변경은 …감사 기록…의 5단계 상태로 표시」. */
export type PolicyHistory = {
  field: string;
  from: unknown;
  to: unknown;
  actor: string;
  reason: string;
  at?: string;
};

export type ScopePolicy = {
  legacy_grandfather_until: string;
  default: string;
  is_default: boolean;
  org_enforce: boolean;
  /** `policy` 면 정책 파일이, `code` 면 코드 기본값이 이겼다는 뜻이다. */
  org_enforce_source: string;
  //: ★ [G1-B 6] 앱 데이터 판정 전환 상태와 **출처**. 값만으로는 「관리자가 정한 것」인지
  //:   「코드 기본값」인지 알 수 없고, 그러면 화면이 「누가 이렇게 해 뒀나」에 답하지 못한다.
  app_pdp_enforce: boolean;
  app_pdp_enforce_source: string;
  history: PolicyHistory[];
};

export type EnforcePreflight = {
  ready: boolean;
  currently_enforced: boolean;
  departments: number;
  users: number;
  admins: number;
  unassigned: number;
  test_looking: number;
  blockers: string[];
  warnings: string[];
};

export type AuditStats = {
  total: number;
  by_event: Record<string, number>;
  by_actor?: Record<string, number>;
};

export type AuditRetention = {
  keep_days?: number;
  oldest?: string;
  prunable?: number;
  [k: string]: unknown;
};

export const adminApi = {
  scopePolicy: () => req<ScopePolicy>('GET', '/api/v1/admin/scope-policy'),
  enforcePreflight: () => req<EnforcePreflight>('GET', '/api/v1/admin/org-enforcement/preflight'),
  auditStats: () => req<AuditStats>('GET', '/api/v1/admin/audit/stats'),
  auditRetention: () => req<AuditRetention>('GET', '/api/v1/admin/audit/retention'),

  /** ⚠️ 강제 전환은 **전사에 즉시 영향을 준다.** 사유를 필수로 받는다 — 되돌릴 때 «왜 켰는가»
   *  를 모르면 되돌려도 되는지 판단할 수 없다. */
  setEnforcement: (enabled: boolean, reason: string) =>
    //: ⚠️⚠️ 서버가 요구하는 이름은 `enabled` 다. 종전에는 `enforce` 로 보내 **422** 가 났다 —
    //:   화면에서 조직 권한 전환을 눌러도 아무 일도 일어나지 않는 상태였다(pydantic 이
    //:   모르는 필드를 버리고 필수 필드가 없다고 답한다). 이름이 다른 것은 조용히 깨진다.
    req<ScopePolicy>('PUT', '/api/v1/admin/org-enforcement', { enabled, reason }),

  /** ★★★ [G1-B 6] 앱 데이터 판정 전환·롤백.
   *  ⚠️ 끄면 통제가 **넓어진다** — 앱 증명·매니페스트·실행 문맥 축이 관리 API 에서 빠진다.
   *    그래서 사유를 필수로 받는다(서버도 강제한다). */
  setAppPdpEnforcement: (enabled: boolean, reason: string) =>
    req<ScopePolicy>('PUT', '/api/v1/admin/app-pdp-enforcement', { enabled, reason }),

  /** 내 비밀번호. [설계 §5.8] 개인 설정은 «나에게만 적용» 이다. */
  changePassword: (currentPassword: string, newPassword: string) =>
    req<{ ok: boolean; token: string }>('POST', '/api/v1/auth/password',
      { current_password: currentPassword, new_password: newPassword }),

  /** 내 표시 이름.
   *
   * ⚠️ [2026-08-23 사용자 지적] 종전에는 이름을 바꾸는 경로가 `POST /org/users` 뿐이었고
   *   거기에는 조직 관리자 권한이 걸려 있다 — **자기 이름조차 못 바꿨다.**
   * ★ 대상 사용자를 보내지 않는다. 서버가 «세션의 주인» 으로만 판단한다. */
  changeMyDisplayName: (displayName: string) =>
    req<{ display_name: string }>('PATCH', '/api/v1/auth/me',
      { display_name: displayName }),
};
