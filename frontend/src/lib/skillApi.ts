// [이관 8/10] 스킬 개선안 API 어댑터
//
// ⚠️ 종전 `SkillEvolutionPanel` 은 `if (res.ok)` 만 처리하고 **else 를 버렸다.** 그래서 403 이어도
//   `proposals` 가 빈 배열로 남아 화면이 «스킬 개선 제안이 없습니다» 라고 말했다.
//   승인 대기열에서 «없다»와 «못 봤다»를 섞으면, 검토해야 할 제안을 아무도 보지 못한 채
//   «대기열이 비었다»고 믿는다. 그건 관문이 조용히 열린 것과 같다.
//
// ★ 경로에 `/api/v1` 이 없다. `skill_control` 라우터의 prefix 가 `/skills` 이고 프론트가 그 경로를
//   부르기 때문이다(2026-08-04 실측). 여기 한 곳에만 적어 두고 화면은 이 어댑터만 쓴다.
import { API_BASE_URL } from './api';

export type SkillProposal = {
  id: string;
  agent_id: string;
  proposed_rules: string[];
  analysis: string;
  created_at: string;
  status: string;
  //: [설계 §5.7] 제안 카드 필수 — 현재 규칙 · 영향 Agent · 대상 파일.
  skill_file?: string;
  current_rules?: string;
  /** ⚠️ `false` 면 «규칙 없음» 이 아니라 **읽지 못했다**는 뜻이다. 둘을 뭉치지 않는다. */
  current_rules_readable?: boolean;
  affected_agents?: string[];
};

export type SkillApiError = Error & { status?: number };

async function call<T>(method: string, path: string): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, { method });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(j?.detail || `요청 실패 (${r.status})`) as SkillApiError;
    e.status = r.status;
    throw e;
  }
  return (j?.data ?? j) as T;
}

export const skillApi = {
  proposals: () => call<SkillProposal[]>('GET', '/skills/proposals'),
  approve: (id: string) =>
    call<unknown>('POST', `/skills/proposals/${encodeURIComponent(id)}/approve`),
  reject: (id: string) =>
    call<unknown>('POST', `/skills/proposals/${encodeURIComponent(id)}/reject`),
};
