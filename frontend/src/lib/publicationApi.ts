// [CL-3] 대내외 발간 API 클라이언트 — 작업서 §CL-BE-04.
//
// 이 화면이 반드시 지켜야 하는 것(서버가 이미 강제한다 — 화면이 무너뜨리지 않는다):
//   ① **렌더 실패를 «발간 준비 완료»로 표시하지 않는다.** 실패는 400 이고 상태는 `DRAFT` 에
//      머문다. 화면이 낙관적으로 «완료»를 띄우면 사용자는 내용 없는 문서에 승인을 누른다.
//   ② **대외 발간 버튼은 게이트가 열릴 때까지 비활성**이고, 그 옆에 이유를 그대로 쓴다.
//      버튼만 죽여 두면 사용자는 화면 고장으로 읽는다. (차단의 진짜 경계는 서버다 — 화면은
//      경계가 아니라 설명이다.)
//   ③ **게시 실패를 성공으로 보여주지 않는다.** 배포 목록의 `FAILED` 를 숨기면 아무 데도
//      안 나간 문서를 «발간됨»으로 믿는다.
import { closedLoopFetch as req } from './closedLoopFetch';
import type { ChipTone } from '../design/HubShell';

export type PubStatus =
  | 'DRAFT' | 'RENDERED' | 'REVIEW_REQUESTED' | 'APPROVED' | 'PUBLISHED'
  | 'CORRECTED' | 'WITHDRAWN';

export type Audience = 'INTERNAL' | 'EXTERNAL';
export type ReviewType = 'EXECUTIVE' | 'LEGAL_DISCLOSURE' | 'SECURITY' | 'DATA_OWNER';
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export type SourceType = 'DECISION_CASE' | 'SIMULATION_RUN';

export type Gate = { code: string; label: string; passed: boolean; reason: string };

export type PubReview = {
  publication_id: string; review_type: ReviewType; reviewer_id: string;
  status: ReviewStatus; comment: string; document_version: number;
  requested_at: string; reviewed_at: string;
};

export type Distribution = {
  distribution_id: string; publication_id: string; target: string; channel: string;
  status: 'PENDING' | 'PUBLISHED' | 'FAILED'; external_ref: string; error: string;
  document_version: number; published_at: string; created_at: string;
};

export type PubVersion = {
  version_id: string; publication_id: string; version_no: number;
  document: {
    title?: string; audience?: string; security_class?: string;
    header?: Record<string, any>;
    sections?: { key: string; value: any }[];
    redaction?: { policy: string; excluded: { key: string; reason: string }[] };
    evidence?: Record<string, any>;
  };
  files: any[]; evidence_hash: string;
  redaction: { policy?: string; excluded?: { key: string; reason: string }[] };
  supersedes_version_id: string; created_at: string;
};

export type Publication = {
  publication_id: string; tenant_id: string; scope_id: string; title: string;
  publication_type: string; audience: Audience; security_class: string;
  source_type: SourceType; source_id: string; status: PubStatus;
  document_version: number; render_error: string; embargo_at: string; published_at: string;
  supersedes_id: string; withdrawn_reason: string;
  created_by: string; created_at: string; updated_at: string;
  versions: PubVersion[]; current_version: PubVersion | null;
  reviews: PubReview[]; distributions: Distribution[];
  gates: Gate[]; blockers: Gate[]; can_publish: boolean;
  note?: string;
};

export const publicationApi = {
  create: (body: {
    title: string; source_type: SourceType; source_id: string; audience?: Audience;
    publication_type?: string; security_class?: string; scope_id?: string; embargo_at?: string;
  }) => req<Publication>('POST', '/api/v1/publications', body),

  list: (q: { audience?: string; status?: string } = {}) => {
    const p = new URLSearchParams();
    if (q.audience) p.set('audience', q.audience);
    if (q.status) p.set('status', q.status);
    const s = p.toString();
    return req<Publication[]>('GET', `/api/v1/publications${s ? `?${s}` : ''}`);
  },

  get: (id: string) => req<Publication>('GET', `/api/v1/publications/${id}`),

  render: (id: string) => req<Publication>('POST', `/api/v1/publications/${id}/render`),

  requestApproval: (id: string, review_types: ReviewType[] = []) =>
    req<Publication>('POST', `/api/v1/publications/${id}/request-approval`, { review_types }),

  approve: (id: string, review_type: ReviewType, status: 'APPROVED' | 'REJECTED', comment = '') =>
    req<Publication>('POST', `/api/v1/publications/${id}/approve`,
      { review_type, status, comment }),

  publish: (id: string, targets: { target: string; channel?: string }[]) =>
    req<Publication>('POST', `/api/v1/publications/${id}/publish`, { targets }),

  correct: (id: string, reason: string) =>
    req<Publication>('POST', `/api/v1/publications/${id}/correct`, { reason }),

  withdraw: (id: string, reason: string) =>
    req<Publication>('POST', `/api/v1/publications/${id}/withdraw`, { reason }),
};

/** 상태 표시.
 *  ★ `DRAFT` 를 «작성 중»이라고만 쓰지 않는다 — 렌더 실패도 여기 머문다. 화면은 `render_error`
 *    를 함께 봐야 하고, 그래서 이 표는 색만 준다. */
export const PUB_STATUS_KO: Record<PubStatus, { label: string; tone: ChipTone }> = {
  DRAFT: { label: '작성 중', tone: 'muted' },
  RENDERED: { label: '문서 생성됨', tone: 'data' },
  REVIEW_REQUESTED: { label: '검토 중', tone: 'warn' },
  APPROVED: { label: '승인 완료', tone: 'success' },
  PUBLISHED: { label: '발간됨', tone: 'success' },
  CORRECTED: { label: '정정됨(구판)', tone: 'warn' },
  WITHDRAWN: { label: '회수됨', tone: 'danger' },
};

export const AUDIENCE_KO: Record<Audience, { label: string; hint: string; tone: ChipTone }> = {
  INTERNAL: { label: '대내', hint: '사내 독자. 원본 항목을 그대로 싣습니다.', tone: 'data' },
  EXTERNAL: {
    label: '대외',
    hint: '책임 임원 승인과 법무·공시 검토를 모두 통과해야 나갑니다. 손익·반대의견 등은 자동 제외됩니다.',
    tone: 'danger',
  },
};

export const REVIEW_KO: Record<ReviewType, { label: string; who: string }> = {
  EXECUTIVE: { label: '책임 임원 승인', who: '대외 발간 필수' },
  LEGAL_DISCLOSURE: { label: '법무·공시 검토', who: '대외 발간 필수' },
  SECURITY: { label: '보안 검토', who: '선택' },
  DATA_OWNER: { label: '데이터 오너 확인', who: '선택' },
};

export const PUB_TYPE_KO: Record<string, string> = {
  OPERATIONAL: '내부 운영 보고',
  MANAGEMENT: '경영 보고',
  COMPANY_WIDE: '전사 공유 보고',
  EXTERNAL_LIMITED: '대외 제한 보고',
  EXTERNAL_PUBLIC: '대외 공개 보고',
};

export const SECURITY_KO: Record<string, string> = {
  PUBLIC: '공개', INTERNAL: '내부', CONFIDENTIAL: '대외비', RESTRICTED: '제한',
};
