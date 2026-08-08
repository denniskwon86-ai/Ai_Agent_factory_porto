// [D-017 §9 P2-2] Agent Governance Center API 클라이언트.
//
// ⚠️ 화면과 **의도적으로 분리**한다(`governanceApi`·`crosswalkApi` 와 같은 관례).
//   표현(문구·색·레이아웃)을 여기 두지 않는다.
//
// ★ 서버는 2026-08-04 부터 완비돼 있었는데 **프론트 소비자가 0건**이었다 —
//   즉 조직별 자산 저장소·승인 흐름이 API 로만 존재하고 사람이 쓸 수 없는 상태였다.
import { closedLoopFetch } from './closedLoopFetch';

const X = '/api/v1/agent-governance';

/** 자산 종류의 경로 조각. 서버 `_KIND_BY_PATH` 와 같은 낱말이어야 한다. */
export type AssetKindPath = 'agents' | 'workflows' | 'skills';

export type AssetActions = {
  read: boolean; create: boolean; update: boolean; approve: boolean; retire: boolean;
};

export type GovCapabilities = {
  user_id: string;
  capabilities: string[];
  bootstrap: boolean;
  is_platform_admin: boolean;
  is_ai_admin: boolean;
  is_data_admin: boolean;
  any_admin: boolean;
  can_manage_agents: boolean;
  can_publish_enterprise: boolean;
  /** 종류별로 실제 가능한 행동. **화면은 이것만 보고 버튼을 정한다.** */
  asset_actions: Record<string, AssetActions>;
  /** 승인 이력 없이 돌고 있는 파일 자산(P1-2). 관리자에게만 온다. */
  file_asset_migration?: { complete?: boolean; error?: string; [k: string]: unknown };
};

export type GovAsset = {
  asset_id: string;
  kind: string;
  tenant_id: string;
  owner_scope_id: string;
  entity_mode: string;
  visibility: string;          // PERSONAL | ORG | ENTERPRISE | SYSTEM
  status: string;              // DRAFT | REVIEW | APPROVED | RETIRED
  name_ko: string;
  purpose: string;
  current_version: number;
  version_count: number;
  runnable: boolean;
  created_by: string;
  approved_by: string;
  created_at: string;
  updated_at: string;
};

export type GovList = {
  kind: string;
  items: GovAsset[];
  total: number;
  /** 이 목록이 **범위로 걸러졌는가.** `false` 면 전량이다. */
  scoped: boolean;
  /** 가려진 것이 있는가. ⚠️ `null` 은 «세지 못했다» — `false`(없다)와 다르다. */
  hidden_present?: boolean | null;
  /** 정확한 건수는 **자료를 관리할 사람에게만** 온다(`api/deps.hidden_envelope`). */
  hidden_count?: number;
};

export const agentGovApi = {
  capabilities: () => closedLoopFetch<GovCapabilities>('GET', `${X}/capabilities`),

  /** ⚠️ 목록 응답은 `data` 밖에 `scoped`·`hidden_*` 를 싣지 않는다 — 서버가 그 값들을
   *  `data` 안에 넣으므로 일반 `closedLoopFetch` 로 충분하다. */
  list: (kind: AssetKindPath, opts: { includeRetired?: boolean } = {}) =>
    closedLoopFetch<GovList>('GET',
      `${X}/${kind}?include_retired=${opts.includeRetired ? 'true' : 'false'}`),

  submit: (kind: AssetKindPath, assetId: string) =>
    closedLoopFetch<GovAsset>('POST', `${X}/${kind}/${encodeURIComponent(assetId)}/submit`),

  approve: (kind: AssetKindPath, assetId: string) =>
    closedLoopFetch<GovAsset>('POST', `${X}/${kind}/${encodeURIComponent(assetId)}/approve`),

  retire: (kind: AssetKindPath, assetId: string) =>
    closedLoopFetch<GovAsset>('POST', `${X}/${kind}/${encodeURIComponent(assetId)}/retire`),
};

// ── 자산 탭 (설계 §8.4) ──────────────────────────────────────────────────────
//
// ★ 서버는 목록을 **한 번** 준다. 탭은 그 목록의 파생이므로 여기서 정의한다 —
//   탭마다 따로 부르면 여섯 번 왕복하고, 그 사이 상태가 바뀌면 탭끼리 어긋난다.
export type AssetTab =
  'system' | 'enterprise' | 'org' | 'my_draft' | 'pending' | 'retired';

export const ASSET_TABS: { id: AssetTab; label: string; hint: string }[] = [
  { id: 'system', label: '기본 제공', hint: '제품이 들고 온 정의 — 직접 고치지 않고 복사해서 씁니다' },
  { id: 'enterprise', label: '전사 공용', hint: '승인을 거쳐 전 조직이 쓰는 정의' },
  { id: 'org', label: '우리 조직', hint: '우리 조직이 소유한 정의' },
  { id: 'my_draft', label: '내 초안', hint: '아직 제출하지 않은 내 작업' },
  { id: 'pending', label: '승인 대기', hint: '누군가 답해야 넘어갑니다' },
  { id: 'retired', label: '사용 중단', hint: '더 쓰지 않기로 한 정의 — 기록은 남습니다' },
];

/** 자산 하나가 이 탭에 속하는가.
 *
 * ⚠️ 탭은 **배타적이지 않다.** 전사 공용이면서 승인 대기일 수 없지만, 우리 조직 자산이
 *   승인 대기일 수는 있다. 배타적으로 만들면 「승인 대기」에서 사라진 항목을 사용자가
 *   찾지 못한다 — 답해야 할 것이 목록에서 없어지는 것이 가장 나쁘다. */
export function inTab(a: GovAsset, tab: AssetTab, me: string,
                      myScopes: Set<string>): boolean {
  const isFile = a.asset_id.startsWith('file:');
  switch (tab) {
    case 'system':
      // 파일 자산 = 제품 기본 제공. `visibility=SYSTEM` 도 함께 본다(둘 다 «내가 만든 것이 아님»).
      return isFile || a.visibility === 'SYSTEM';
    case 'enterprise':
      return a.visibility === 'ENTERPRISE';
    case 'org':
      return a.visibility === 'ORG' && (myScopes.size === 0
        || myScopes.has(a.owner_scope_id));
    case 'my_draft':
      return a.status === 'DRAFT' && a.created_by === me;
    case 'pending':
      return a.status === 'REVIEW';
    case 'retired':
      return a.status === 'RETIRED';
  }
}
