// [CL-1] 협업 API 클라이언트 — 앱 전달·수락·내 앱
//
// ★ `API_BASE_URL` 을 다시 선언하지 않는다(작업서 §CL-FE-01). 오늘 실측한 결함이 정확히 그것이다:
//   `KnowledgeHubPanel.tsx` 가 자기 `localhost:8080` 을 선언해 인터셉터(`127.0.0.1` 기준)가
//   식별 헤더를 못 붙였고, 그 화면의 모든 호출이 조용히 익명으로 나갔다.
//   → 여기서는 공용 `lib/api.ts` 만 쓴다. 사용자 식별 헤더는 인터셉터가 붙인다.
// ⚠️ 401 과 404 를 같은 문구로 뭉개지 않는다 — 사용자가 해야 할 일이 다르다.
//   401: 사용자를 지정해야 한다 / 404: 그 요청은 (내게) 없다.
// [CL-2] 그 규약은 의사결정 API 도 똑같이 쓰므로 `closedLoopFetch` 로 옮겼다(복사본 금지).
import { closedLoopFetch as req } from './closedLoopFetch';

/** 전달 상태. 만료는 **읽는 시점에** 판정되므로 서버가 준 값을 그대로 믿는다. */
export type DeliveryStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'EXPIRED' | 'REVOKED';

export type CapabilityManifest = {
  auth_mode?: string;
  enterprise_scope_mode?: string;
  audit_mode?: string;
  capabilities?: string[];
  required_capabilities?: { resource: string; actions: string[] }[];
  required_data_scopes?: string[];
  forbidden_features?: string[];
  app_class?: string;
  standalone_auth?: boolean;
};

export type Delivery = {
  delivery_id: string;
  release_id: string;
  release_version: string;
  sender_user_id: string;
  recipient_user_id: string;
  purpose: string;
  status: DeliveryStatus;
  stored_status?: DeliveryStatus;
  expires_at: string;
  manifest_snapshot: CapabilityManifest;
  manifest_fingerprint: string;
  response_note?: string;
  responded_at?: string;
  created_at: string;
  role?: 'sender' | 'recipient' | '';
  can_respond?: boolean;
  can_revoke?: boolean;
  replayed?: boolean;
  note?: string;
  // 수락 응답에만 있다 — 화면은 이 문구를 **반드시** 보여준다(권한이 넓어졌다는 오해 방지).
  scope_unchanged?: boolean;
  scope_note?: string;
  pocket?: PocketApp;
  reassign_requested?: boolean;
};

export type PocketApp = {
  pocket_id: string;
  user_id: string;
  release_id: string;
  delivery_id: string;
  display_name: string;
  status: 'ACTIVE' | 'REVOKED';
  pinned: number;
  accepted_at: string;
  last_opened_at: string;
};

export const collaborationApi = {
  // ── 전달 ────────────────────────────────────────────────────────────────
  create: (body: {
    release_id: string; recipient_user_id: string; purpose: string;
    expires_in_days?: number; idempotency_key?: string;
  }) => req<Delivery>('POST', '/api/v1/app-deliveries', body),

  inbox: (onlyPending = false) =>
    req<Delivery[]>('GET', `/api/v1/app-deliveries/inbox?only_pending=${onlyPending}`),

  outbox: () => req<Delivery[]>('GET', '/api/v1/app-deliveries/outbox'),

  get: (id: string) => req<Delivery>('GET', `/api/v1/app-deliveries/${id}`),

  accept: (id: string, displayName = '') =>
    req<Delivery>('POST', `/api/v1/app-deliveries/${id}/accept`,
      { display_name: displayName }),

  reject: (id: string, note = '') =>
    req<Delivery>('POST', `/api/v1/app-deliveries/${id}/reject`, { note }),

  reassign: (id: string, note: string) =>
    req<Delivery>('POST', `/api/v1/app-deliveries/${id}/reassign-request`, { note }),

  revoke: (id: string, reason = '') =>
    req<Delivery>('POST', `/api/v1/app-deliveries/${id}/revoke`, { reason }),

  // ── 내 앱 ───────────────────────────────────────────────────────────────
  myApps: (includeRevoked = false) =>
    req<PocketApp[]>('GET', `/api/v1/me/apps?include_revoked=${includeRevoked}`),

  patchApp: (pocketId: string, body: {
    display_name?: string; pinned?: boolean; mark_opened?: boolean;
  }) => req<PocketApp>('PATCH', `/api/v1/me/apps/${pocketId}`, body),
};

/** 상태별 한국어 표시. **만료·회수를 "거절"과 같은 색으로 두지 않는다** — 사용자가 해야 할
 *  일이 다르다(만료: 다시 보내달라고 요청 / 회수: 보낸 사람에게 확인). */
export const DELIVERY_STATUS_KO: Record<DeliveryStatus, { label: string; tone: string }> = {
  PENDING: { label: '응답 대기', tone: 'amber' },
  ACCEPTED: { label: '수락', tone: 'emerald' },
  REJECTED: { label: '거절', tone: 'gray' },
  EXPIRED: { label: '만료', tone: 'slate' },
  REVOKED: { label: '회수됨', tone: 'red' },
};
