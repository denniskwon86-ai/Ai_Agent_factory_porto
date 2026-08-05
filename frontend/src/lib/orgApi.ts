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
  status: string;
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
};
