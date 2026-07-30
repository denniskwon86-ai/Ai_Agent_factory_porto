// 프로그램 사용여부 API 클라이언트 (사용자 결정 2026-07-30)
//
// > "이미 생성되어 다른 사용자가 기록을 남긴 코드(프로그램)을 삭제하면 꼬일 수 있으니
// >  그냥 사용여부만 제어해서 더이상 사용하지 않는 프로그램이라고 비활성화 조치만 하는 것이
// >  좋을 것 같습니다."
//
// ⚠️ 화면과 **의도적으로 분리**한다 — 디자인 개편 때 이 파일은 그대로 재사용된다
//   (workspaceApi·shadowApi·governanceApi 와 같은 관례).
import { API_BASE_URL } from './api';

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = j?.detail;
    throw new Error(typeof d === 'string' ? d : d ? JSON.stringify(d) : `요청 실패 (${r.status})`);
  }
  return j.data as T;
}

export type ProgramStatus = 'active' | 'deprecated' | 'disabled';

export const STATUS_LABEL: Record<ProgramStatus, string> = {
  active: '사용 중',
  deprecated: '중단 예고',
  disabled: '사용 중단',
};

export type Dependents = {
  forks: string[];
  shared_to: string[];
  is_enterprise: boolean;
  count: number;
  blast_radius: 'none' | 'department' | 'enterprise';
  // ⚠️ "영향 없음"과 "영향을 못 셌음"은 다르다. 비어 있지 않으면 화면에 그대로 보여준다.
  unmeasured: string[];
};

export type StatusHistoryEntry = {
  event_id: string;
  from_status: string;
  to_status: string;
  reason: string;
  replacement_release_id: string;
  actor: string;
  at: string;
};

export type ProgramLifecycle = {
  release_id: string;
  status: ProgramStatus;
  // ★ false = 아무도 지정하지 않아 "사용 가능으로 간주"한 것이며, 관리자가 승인한 상태가
  //   아니다. 이 둘을 같게 표시하면 감사에서 거짓이 된다.
  recorded: boolean;
  reason: string;
  replacement_release_id: string;
  changed_by: string;
  changed_at: string;
  note: string;
  history?: StatusHistoryEntry[];
  dependents?: Dependents;
};

export type ChangeArgs = {
  reason: string;
  replacement_release_id?: string;
  // 의존 대상이 있을 때만 필요하다. 서버가 목록을 담은 409 로 먼저 거부한다.
  acknowledge_dependents?: boolean;
};

export const fetchProgram = (releaseId: string) =>
  req<ProgramLifecycle>('GET', `/api/v1/programs/${encodeURIComponent(releaseId)}`);

export const fetchProgramStatuses = (status = '') =>
  req<ProgramLifecycle[]>('GET', `/api/v1/programs${status ? `?status=${status}` : ''}`);

export const disableProgram = (releaseId: string, args: ChangeArgs) =>
  req<ProgramLifecycle>('POST', `/api/v1/programs/${encodeURIComponent(releaseId)}/disable`, args);

export const deprecateProgram = (releaseId: string, args: ChangeArgs) =>
  req<ProgramLifecycle>('POST', `/api/v1/programs/${encodeURIComponent(releaseId)}/deprecate`, args);

export const reactivateProgram = (releaseId: string, reason = '') =>
  req<ProgramLifecycle>('POST', `/api/v1/programs/${encodeURIComponent(releaseId)}/reactivate`,
                        { reason });
