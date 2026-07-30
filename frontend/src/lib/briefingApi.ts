// [M5] 전사 브리핑 API 클라이언트 (제품 성경 §5.5 / 명세서 §14 M5)
//
// ⚠️ 화면과 분리한다(planningApi·qualityApi·governanceApi 관례). 디자인 시안 확정 후 화면은
//   교체 대상이지만 이 파일은 재사용된다 — 표현(문구·색·레이아웃)을 두지 않는다.
import { API_BASE_URL } from './api';

/** 섹션 순서는 백엔드 `SECTIONS` 를 따른다 — 화면이 임의로 재정의하면 두 벌이 된다. */
export const BRIEFING_SECTIONS = [
  'my_decisions', 'blocked', 'data_health', 'programs', 'cost',
] as const;
export type BriefingSection = (typeof BRIEFING_SECTIONS)[number];

export const SECTION_LABELS: Record<BriefingSection, string> = {
  my_decisions: '내가 결정해야 하는 것',
  blocked: '막혀 있는 것',
  data_health: '데이터 상태',
  programs: '프로그램',
  cost: '비용',
};

export type BriefingItem = {
  kind: string;
  severity: 'high' | 'medium' | 'low' | 'info';
  title: string;
  /** 왜 이것이 문제인가. */
  why: string;
  /** 그래서 무엇을 하면 풀리는가 — 상태만 나열하면 대시보드지 보좌가 아니다. */
  suggested_action: string;
  ref: string;
  ref_type: string;
};

export type CostSection = {
  available: boolean;
  reason?: string;
  calls?: number;
  cost_usd?: number;
  priced_calls?: number;
  unpriced_calls?: number;
  /** false 면 총액은 **하한**이다(단가 미등록 호출이 있음) — 완전한 총액으로 읽히면 예산 판단이 틀린다. */
  cost_complete?: boolean;
};

export type SectionData = {
  items: BriefingItem[];
  count: number;
  unavailable?: { source: string; error: string }[];
  complete?: boolean;
};

export type Briefing = {
  generated_at: string;
  actor: string;
  scope: { scope_node_id: string; tenant_id: string; entity_mode: string; filtered: boolean };
  sections: Record<string, SectionData> & { cost: CostSection };
  attention_count: number;
  by_severity: Record<string, number>;
  top: BriefingItem[];
  /** 읽지 못한 소스. 비어 있지 않으면 이 브리핑은 **전부가 아니다**. */
  unavailable: { section: string; source: string; error: string }[];
  complete: boolean;
  note: string;
};

async function get<T>(path: string): Promise<{ data: T; permission?: any }> {
  const r = await fetch(`${API_BASE_URL}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail || `요청 실패 (${r.status})`);
  return { data: j.data as T, permission: j.permission };
}

export const fetchBriefing = (scopeNodeId?: string) =>
  get<Briefing>(`/api/v1/briefing${scopeNodeId
    ? `?scope_node_id=${encodeURIComponent(scopeNodeId)}` : ''}`);

export const fetchBriefingSection = (section: BriefingSection, scopeNodeId?: string) =>
  get<SectionData & { cost?: CostSection }>(
    `/api/v1/briefing/sections/${section}${scopeNodeId
      ? `?scope_node_id=${encodeURIComponent(scopeNodeId)}` : ''}`);
