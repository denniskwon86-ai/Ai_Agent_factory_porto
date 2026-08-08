// [D-017 §9 P2-2] Agent Governance Center API 클라이언트.
//
// ⚠️ 화면과 **의도적으로 분리**한다(`governanceApi`·`crosswalkApi` 와 같은 관례).
//   표현(문구·색·레이아웃)을 여기 두지 않는다.
//
// ★ 서버는 2026-08-04 부터 완비돼 있었는데 **프론트 소비자가 0건**이었다 —
//   즉 조직별 자산 저장소·승인 흐름이 API 로만 존재하고 사람이 쓸 수 없는 상태였다.
import { closedLoopEnvelopeFetch } from './closedLoopFetch';

const X = '/api/v1/agent-governance';

/** ★★★ 이 라우터는 `{data: …}` 봉투를 **쓰지 않는다** — 응답이 곧 본문이다.
 *
 * ⚠️⚠️ 그래서 `closedLoopFetch` 를 그대로 쓰면 안 된다. 그 헬퍼는 `.data` 를 꺼내므로 이
 *   라우터에서는 **항상 `undefined` 를 돌려준다.** 그러면 화면은 `d?.items || []` 로 흘러
 *   **오류 없이 빈 목록**을 그리고, 사용자도 개발자도 원인을 묻지 않는다 — 조회 실패는
 *   눈에 띄지만 «조용히 비어 있음» 은 아무 신호도 남기지 않는다.
 *   (2026-08-08 실측으로 발견. 그때까지 이 경로는 CORS 에 막혀 한 번도 성공한 적이 없었다.)
 *
 * ★ 봉투를 쓰는 라우트가 나중에 생겨도 깨지지 않도록 **둘 다** 받는다. 여기서 한쪽만 고르면
 *   그 순간 다른 쪽 라우트가 조용히 undefined 가 된다. */
async function govFetch<T>(method: string, path: string, body?: unknown): Promise<T> {
  const j = await closedLoopEnvelopeFetch<T>(method, path, body);
  const d = (j as { data?: T })?.data;
  return d !== undefined && d !== null ? d : (j as unknown as T);
}

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
  //: ⚠️ **서버 상수 그대로다**(`core/agent_assets.VIS_*`). 조직 자산은 `ORG` 가 아니라
  //:   **`SCOPE`** 이고, 하위 조직까지면 `DESCENDANTS` 다. 낱말을 여기서 지어내면 탭 판정이
  //:   조용히 아무것도 못 고른다 — 오류도 안 나고 목록만 늘 비어 있다.
  visibility: string;          // PERSONAL | SCOPE | DESCENDANTS | ENTERPRISE | SYSTEM
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
  /** 전사 승격을 요청한 사람. ⚠️ 요청은 **가시성을 바꾸지 않는다** — 이 값이 있다고 해서
   *  전사에 공개된 것이 아니다(그때는 `visibility` 가 `ENTERPRISE` 가 된다). */
  promotion_requested_by?: string;
  promotion_requested_at?: string;
  /** ★★★ 「지금 이 자산에 이 행동을 할 수 있는가」 — **서버가 자산마다 답한다.**
   *
   *  빈 문자열이면 할 수 있고, 아니면 그 문장이 곧 못 하는 이유다. 화면은 이것을 그대로
   *  버튼에 붙인다. ⚠️ **여기서 판정을 다시 만들지 말 것** — 화면이 자기 규칙을 만들면
   *  서버와 서서히 갈라져 「버튼은 보이는데 서버는 거부」가 생기고, 그때 사용자는 통제가
   *  고장났다고 읽는다(2026-08-08 감사에서 실제로 그 상태를 발견했다). */
  blocked?: { update: string; submit: string; approve: string; retire: string;
              publish_to_org: string; promote: string; copy: string };
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

/** 자산 하나의 사용 현황.
 *
 * ⚠️⚠️ **`project_count` 를 혼자 읽지 말 것.** `countable=false` 면 그 0 은 「쓰이지 않는다」가
 *   아니라 **「아직 모른다」** 이다(프로젝트가 구성을 기록하기 전 상태). 0 을 그대로 그리면
 *   사용자는 전부 폐기해도 된다고 읽는다. */
export type GovAssetUsage = {
  project_count: number;
  /** 어느 프로젝트인지는 **자산을 관리할 사람에게만** 온다 — 없을 수 있다. */
  projects?: string[];
  countable: boolean;
};

export type GovUsage = {
  kind: string;
  /** 스캔 자체가 됐는가. `false` 면 «사용 0건» 이 아니라 «집계 실패» 다. */
  available: boolean;
  error: string;
  /** 프로젝트가 몇 개인가. */
  projects_total: number;
  /** 그중 **구성을 기록한** 프로젝트가 몇 개인가. 이것이 분모다. */
  projects_observed: number;
  /** 이 종류를 실제로 셀 수 있는 스냅샷 수. 스킬은 축이 늦게 생겨 더 작을 수 있다. */
  axis_observed: number;
  axis: string;
  usage: Record<string, GovAssetUsage>;
};

export type AssetCreatePayload = {
  name_ko: string;
  purpose?: string;
  visibility: string;
  owner_scope_id?: string;
  body?: Record<string, unknown>;
};

export const agentGovApi = {
  capabilities: () => govFetch<GovCapabilities>('GET', `${X}/capabilities`),

  /** 목록. `scoped`·`hidden_*` 가 본문에 함께 실려 온다(위 `govFetch` 주석 참조). */
  list: (kind: AssetKindPath, opts: { includeRetired?: boolean } = {}) =>
    govFetch<GovList>('GET',
      `${X}/${kind}?include_retired=${opts.includeRetired ? 'true' : 'false'}`),

  /** ★ 목록과 **따로** 부른다. 프로젝트 작업공간을 훑는 일이라 목록에 묶으면 목록이 느려지고,
   *  스캔이 실패했을 때 목록까지 함께 죽는다 — 목록은 있는데 사용 수만 없는 것은 정상이다. */
  usage: (kind: AssetKindPath) =>
    govFetch<GovUsage>('GET', `${X}/${kind}/usage`),

  create: (kind: AssetKindPath, payload: AssetCreatePayload) =>
    govFetch<GovAsset>('POST', `${X}/${kind}`, payload),

  /** 개정 — **승인이 풀린다**(저장소 계약). 내용이 바뀐 뒤에도 승인이 남으면 그 승인은
   *  읽지 않은 문서에 대한 승인이다. */
  revise: (kind: AssetKindPath, assetId: string, body: Record<string, unknown>) =>
    govFetch<GovAsset>('PUT', `${X}/${kind}/${encodeURIComponent(assetId)}`, { body }),

  /** ★ 제품 기본 정의를 쓰는 **유일한 방법**이다. 이것이 없으면 「복사해서 쓰십시오」라는
   *  안내가 막다른 길로 끝난다. */
  copy: (kind: AssetKindPath, assetId: string,
         payload: { name_ko?: string; visibility: string; owner_scope_id?: string }) =>
    govFetch<GovAsset & { copied_from: string }>(
      'POST', `${X}/${kind}/${encodeURIComponent(assetId)}/copy`, payload),

  submit: (kind: AssetKindPath, assetId: string) =>
    govFetch<GovAsset>('POST', `${X}/${kind}/${encodeURIComponent(assetId)}/submit`),

  approve: (kind: AssetKindPath, assetId: string) =>
    govFetch<GovAsset>('POST', `${X}/${kind}/${encodeURIComponent(assetId)}/approve`),

  retire: (kind: AssetKindPath, assetId: string) =>
    govFetch<GovAsset>('POST', `${X}/${kind}/${encodeURIComponent(assetId)}/retire`),

  /** 내 초안을 **우리 조직 자산으로 옮긴다.** ⚠️ 복사가 아니라 **이동**이다 — 같은 정의가
   *  두 벌이 되면 어느 쪽이 정본인지 아무도 모르고 한쪽만 고쳐진 채 승인된다.
   *  승인돼 있던 개인 자산은 「승인 대기」로 되돌아간다(조직이 다시 답해야 한다). */
  publishToOrg: (kind: AssetKindPath, assetId: string, ownerScopeId: string) =>
    govFetch<GovAsset>('POST', `${X}/${kind}/${encodeURIComponent(assetId)}/publish-to-org`,
      { owner_scope_id: ownerScopeId }),

  /** 전사 승격. **자격이 답을 정한다** — AI 거버넌스 관리자는 확정하고, 조직 승인자는
   *  요청한다. ⚠️ 요청은 가시성을 바꾸지 않는다(서버 계약). */
  promote: (kind: AssetKindPath, assetId: string) =>
    govFetch<GovAsset & { promotion_outcome: '확정' | '요청' }>(
      'POST', `${X}/${kind}/${encodeURIComponent(assetId)}/promote`),
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

/** 조직 소유 자산의 공개 범위. **서버 상수와 같은 낱말이어야 한다**(`VIS_SCOPE`·
 *  `VIS_DESCENDANTS`). ⚠️ `'ORG'` 가 아니다 — 그렇게 적으면 「우리 조직」 탭이 **영원히
 *  비어 있고**, 오류가 없으므로 아무도 원인을 묻지 않는다(2026-08-08 실측으로 발견). */
export const ORG_VISIBILITIES = ['SCOPE', 'DESCENDANTS'];

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
      return ORG_VISIBILITIES.includes(a.visibility) && (myScopes.size === 0
        || myScopes.has(a.owner_scope_id));
    case 'my_draft':
      // ★ 개인 초안도 여기 온다 — 「아직 제출하지 않은 내 작업」이 탭의 뜻이고, 공개 범위가
      //   무엇이든 내가 손대야 넘어간다. 범위로 거르면 자기 초안을 못 찾는다.
      return a.status === 'DRAFT' && a.created_by === me;
    case 'pending':
      return a.status === 'REVIEW';
    case 'retired':
      return a.status === 'RETIRED';
  }
}
