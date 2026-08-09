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
  setEnforcement: (enforce: boolean, reason: string) =>
    req<ScopePolicy>('PUT', '/api/v1/admin/org-enforcement', { enforce, reason }),

  /** 내 비밀번호. [설계 §5.8] 개인 설정은 «나에게만 적용» 이다. */
  changePassword: (currentPassword: string, newPassword: string) =>
    req<{ ok: boolean; token: string }>('POST', '/api/v1/auth/password',
      { current_password: currentPassword, new_password: newPassword }),
};
