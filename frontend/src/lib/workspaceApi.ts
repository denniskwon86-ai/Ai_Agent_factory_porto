// 부서 워크스페이스 API 클라이언트 (명세서 §9 / §14 M3)
//
// ⚠️ 화면과 분리한다 — 디자인 개편 때 그대로 재사용된다(advisorApi·shadowApi 와 같은 관례).
import { API_BASE_URL } from './api';

/** ⚠️ [이관 F 5/8] 상태 코드를 실어 던진다 — 화면이 «권한이 없어 못 봤다» 와 «서버가 죽었다»
 *  를 구분해야 한다. `closedLoopFetch.ApiError`·`shadowApi` 와 같은 규약이다. */
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

// `unverifiable` 은 통과가 아니라 **확인하지 못한 것**이며 승격을 막는다.
export type GateState = 'pass' | 'fail' | 'unverifiable';

export type GateCheck = {
  check: 'asset_linkage' | 'data_contract' | 'security' | 'quality' | 'data_owner_approval';
  state: GateState;
  why: string;
  suggested_action?: string;
};

export type Gate = {
  release_id: string;
  target_scope: string;
  linked_assets: string[];
  checks: GateCheck[];
  failed: string[];
  unverifiable: string[];
  promotable: boolean;
  note: string;
};

export type Promotion = {
  promotion_id: string;
  release_id: string;
  from_scope: string;
  target_scope: string;
  project_id: string;
  status: 'draft' | 'requested' | 'approved' | 'rejected' | 'promoted';
  requested_by: string;
  data_owner_approved_by: string;
  owner_note: string;
  promoted_by: string;
  promoted_at: string;
  rejected_reason: string;
  gate_snapshot: Gate | null;
};

export type Share = {
  share_id: string; release_id: string; from_scope: string; to_scope: string;
  mode: string; shared_by: string; reason: string; status: string; created_at: string;
};

export type Fork = {
  fork_id: string; source_release_id: string; new_project_id: string;
  owner_scope: string; forked_by: string; created_at: string;
};

export const fetchPromotions = (status = '') =>
  req<Promotion[]>('GET', `/api/v1/workspace/promotions${status ? `?status=${status}` : ''}`);

export const fetchGate = (releaseId: string, projectId = '') =>
  req<Gate>('GET', `/api/v1/workspace/promotions/gate?release_id=${encodeURIComponent(releaseId)}`
    + (projectId ? `&project_id=${encodeURIComponent(projectId)}` : ''));

export const requestPromotion = (body: {
  release_id: string; from_scope: string; project_id?: string; target_scope?: string;
}) => req<Promotion>('POST', '/api/v1/workspace/promotions', body);

export const ownerApprove = (releaseId: string, note = '') =>
  req<Promotion>('POST', '/api/v1/workspace/promotions/owner-approve',
                 { release_id: releaseId, note });

export const rejectPromotion = (releaseId: string, reason: string) =>
  req<Promotion>('POST', '/api/v1/workspace/promotions/reject',
                 { release_id: releaseId, reason });

export const promoteRelease = (releaseId: string) =>
  req<Promotion>('POST', '/api/v1/workspace/promotions/promote', { release_id: releaseId });

export const fetchShares = (releaseId = '') =>
  req<Share[]>('GET', `/api/v1/workspace/shares${releaseId ? `?release_id=${encodeURIComponent(releaseId)}` : ''}`);

export const createShare = (body: {
  release_id: string; from_scope: string; to_scope: string; mode?: string; reason?: string;
}) => req<Share>('POST', '/api/v1/workspace/shares', body);

export const revokeShare = (shareId: string) =>
  req<{ share_id: string }>('DELETE', `/api/v1/workspace/shares/${shareId}`);

export const fetchForks = (releaseId = '') =>
  req<Fork[]>('GET', `/api/v1/workspace/forks${releaseId ? `?source_release_id=${encodeURIComponent(releaseId)}` : ''}`);

// ── 운영 준비 (§8.2 / §14 M3) ────────────────────────────────────────────
// `not_required` 는 §8.2 가 해당 종류에 요구하지 않은 단계다(Shadow Mode).
// `unverifiable` 은 통과가 아니라 확인하지 못한 것이며 operations_ready 를 막는다.
export type StepState = 'pass' | 'fail' | 'unverifiable' | 'not_required';

export type ChecklistStep = {
  step: string;
  state: StepState;
  why: string;
  suggested_action?: string;
};

export type Checklist = {
  release_id: string;
  project_id: string;
  steps: ChecklistStep[];
  failed: string[];
  unverifiable: string[];
  operations_ready: boolean;
  note: string;
};

export type RollbackResult = {
  rollback_id: string;
  release_id: string;
  revoked_promotion: boolean;
  actor: string;
  reason: string;
  created_at: string;
  // ⚠️ 화면에 반드시 그대로 보여준다 — "롤백했다"가 실제보다 크게 읽히면 아무도 후속
  //   조치를 하지 않는다.
  limitation: string;
};

export type ChangeImpact = {
  impacted_count: number;
  releases: { release_id: string; depth: number; is_enterprise: boolean }[];
  projects: { project_id: string; depth: number }[];
  enterprise_releases: { release_id: string }[];
  blast_radius: 'none' | 'department' | 'enterprise';
  limitation: string;
};

export const fetchChecklist = (releaseId: string, projectId = '', liveIntegration = false) =>
  req<Checklist>('GET', `/api/v1/readiness/checklist?release_id=${encodeURIComponent(releaseId)}`
    + (projectId ? `&project_id=${encodeURIComponent(projectId)}` : '')
    + (liveIntegration ? '&requires_live_integration=true' : ''));

export const rollbackRelease = (releaseId: string, reason: string, toReleaseId = '') =>
  req<RollbackResult>('POST', '/api/v1/readiness/rollback',
                      { release_id: releaseId, reason, to_release_id: toReleaseId });

export const fetchChangeImpact = (nodeType: string, nodeId: string) =>
  req<ChangeImpact>('GET', `/api/v1/readiness/impact?node_type=${encodeURIComponent(nodeType)}`
    + `&node_id=${encodeURIComponent(nodeId)}`);
