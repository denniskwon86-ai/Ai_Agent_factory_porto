// [이관 4/10] 조직·권한 API 어댑터
//
// ⚠️ 종전 `OrgChartPanel` 은 `API_BASE_URL` 을 자기 파일에 다시 선언하고(저장소에서 열 번째)
//   `fetch` 를 직접 불렀다. 그래서 응답 봉투의 통제 메타데이터를 버렸고, 실패와 «없음»이 같은
//   코드로 흘러 403 상태에서도 «등록된 부서가 없습니다» 가 떴다.
import { closedLoopEnvelopeFetch } from './closedLoopFetch';

const O = '/api/v1/org';

export type Dept = {
  dept_id: string;
  name_ko: string;
  parent_id: string;
  path: string;
  depth: number;
  master_domains: string[];
  default_template_id: string;
  domain_agents: string[];
  legacy_domain: string;
  version: number;
  status: string;
  valid_from: string;
  /** 이 부서가 대응하는 조직 노드. **비면 그 부서 사람들에게 조직 소유 자료가 보이지 않는다.** */
  scope_node_id: string;
  children?: Dept[];
};

export type OrgUser = {
  user_id: string;
  display_name: string;
  primary_dept_id: string;
  is_executive: boolean;
  is_admin: boolean;
  is_data_admin: boolean;
  /** ⚠️ [2026-08-23] 서버는 이 칸을 **보내고 있었는데 타입에 없었다.** 타입에 없으면
   *  화면은 그 권한이 존재하는지조차 모르고, 「권한 표식」 목록에서 조용히 빠진다 —
   *  AI 관리자를 «권한 없음» 으로 그리게 된다. 서버 응답과 맞춘다. */
  is_ai_admin: boolean;
  status: string;
  created_at?: string;
  roles: Record<string, string>;
};

export type MyScope = {
  user_id: string;
  display_name: string;
  unrestricted: boolean;
  can_edit_org: boolean;
  can_run_enterprise: boolean;
  can_manage_standard: boolean;
  is_executive: boolean;
  is_admin: boolean;
  is_data_admin: boolean;
  identified: boolean;
  registered: boolean;
  retired?: boolean;
  org_enforced: boolean;
  primary_dept_id: string;
  readable_dept_ids: string[];
  writable_dept_ids: string[];
  readable_scope_nodes: string[];
  /** 서버가 만든 안내문. «왜 안 보이는가»의 답이 여기 있다. */
  access_note: string;
};

/** 목록 응답 — 통제 메타데이터를 버리지 않는다. */
export type OrgList<T> = { rows: T[]; blockedReason: string };
export type UserList = OrgList<OrgUser> & {
  hiddenPresent: boolean;
  /** 조직 편집 권한자에게만 온다. `null` 은 «모른다»이며 0 과 다르다. */
  hiddenCount: number | null;
};

export const orgApi = {
  tree: async (): Promise<OrgList<Dept>> => {
    const e = await closedLoopEnvelopeFetch<Dept[]>('GET', `${O}/tree`);
    return { rows: e.data || [], blockedReason: String(e.blocked_reason || '') };
  },

  departments: async (): Promise<OrgList<Dept>> => {
    const e = await closedLoopEnvelopeFetch<Dept[]>('GET', `${O}/departments`);
    return { rows: e.data || [], blockedReason: String(e.blocked_reason || '') };
  },

  deptHistory: async (deptId: string): Promise<Dept[]> => {
    const e = await closedLoopEnvelopeFetch<Dept[]>(
      'GET', `${O}/departments/${encodeURIComponent(deptId)}/history`);
    return e.data || [];
  },

  users: async (): Promise<UserList> => {
    const e = await closedLoopEnvelopeFetch<OrgUser[]>('GET', `${O}/users`);
    return {
      rows: e.data || [],
      blockedReason: String(e.blocked_reason || ''),
      hiddenPresent: Boolean(e.hidden_present),
      hiddenCount: e.hidden_count === undefined || e.hidden_count === null
        ? null : Number(e.hidden_count),
    };
  },

  me: async (): Promise<MyScope> => {
    const e = await closedLoopEnvelopeFetch<MyScope>('GET', `${O}/me`);
    return e.data;
  },

  createDept: (body: { dept_id: string; name_ko: string; parent_id?: string }) =>
    closedLoopEnvelopeFetch<Dept>('POST', `${O}/departments`, body),

  updateDept: (deptId: string, body: Partial<Pick<Dept,
    'name_ko' | 'parent_id' | 'scope_node_id' | 'default_template_id'>>) =>
    closedLoopEnvelopeFetch<Dept>('PUT', `${O}/departments/${encodeURIComponent(deptId)}`, body),

  retireDept: (deptId: string) =>
    closedLoopEnvelopeFetch<unknown>('DELETE', `${O}/departments/${encodeURIComponent(deptId)}`),

  upsertUser: (body: Record<string, unknown>) =>
    closedLoopEnvelopeFetch<OrgUser>('POST', `${O}/users`, body),

  setRoles: (userId: string, roles: Record<string, string>) =>
    closedLoopEnvelopeFetch<OrgUser>(
      'PUT', `${O}/users/${encodeURIComponent(userId)}/roles`, { roles }),

  seedDepartments: () => closedLoopEnvelopeFetch<unknown>('POST', `${O}/seed`, {}),

  /** [설계 §5.8 Enterprise Structure] 의미 그래프 — 소유·운영·공유·연결 관계.
   *
   * ⚠️ `grants_authority` 는 **서버가 판정한 값**이다. 화면이 관계 이름으로 추측하면 관계
   *   종류가 늘어날 때 조용히 틀린다 — 권한 상속은 OPERATING_PARENT 만이다. */
  //: ⚠️⚠️ 봉투를 **여기서** 벗긴다. 처음에 화면이 `closedLoopEnvelopeFetch` 의 결과에서
  //  `.rows` 를 읽었는데, 이 헬퍼가 주는 것은 `{status, data, permission}` 이다 — `.rows` 는
  //  없으므로 `undefined → []` 가 되어 **관계 16건이 「0건」으로 그려졌다.** 서버는 200 을
  //  주고 있었다. 조회 실패도 아니고 빈 것도 아닌, 그냥 잘못 읽은 것이다.
  //  (같은 실수를 이 저장소에서 세 번째 했다 — 봉투는 반드시 클라이언트 계층에서 벗긴다.)
  edges: async (): Promise<OrgList<OrgEdge>> => {
    const e = await closedLoopEnvelopeFetch<OrgEdge[]>(
      'GET', '/api/v1/enterprise-context/edges');
    return { rows: e.data || [], blockedReason: String((e as any).blocked_reason || '') };
  },
};

/** 조직 관계 한 줄.
 *
 * ⚠️ 필드명은 서버 응답 그대로 `from_node_id` / `to_node_id` 다. 처음에 `parent_/child_` 로
 *   써 두었더니 타입 검사는 통과하고 **표의 두 칸이 빈칸으로** 나왔다 — 이름을 짐작하지 않고
 *   실제 응답에서 가져온다. */
export type OrgEdge = {
  edge_id?: string;
  from_node_id: string;
  to_node_id: string;
  relation_type: string;
  /** 서버 판정. 권한을 물려주는 관계는 OPERATING_PARENT 하나뿐이다. */
  grants_authority: boolean;
  status?: string;
  effective_from?: string;
  effective_to?: string;
};
