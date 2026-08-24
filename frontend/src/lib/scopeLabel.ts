/**
 * 조직 범위를 **사람이 읽는 이름**으로. — 단일 지점.
 *
 * ## ⚠️⚠️ 왜 모듈로 뺐는가 (2026-08-24 사용자 지적)
 *
 * 상단바(`CompanyContextBar`)는 조직 트리를 읽어 「제련공장」이라고 적는데, 경영 홈
 * 본문은 같은 값을 **원시 id 그대로**(`node_41402723bc90`) 찍고 있었다. 사용자에게는
 * 같은 화면에 같은 것이 두 이름으로 보이고, 그중 하나는 아무 뜻도 없다.
 *
 * ★ 해석을 두 곳에서 하면 언젠가 한쪽만 고쳐진다. 여기 하나만 둔다.
 * ⚠️ 못 찾으면 **원시 id 를 그대로 돌려준다.** 「미지정」으로 바꾸지 않는다 — 고른 것이
 *   있는데 이름을 못 찾은 것과 아무것도 안 고른 것은 **다른 사실**이다.
 */
import { orgApi } from './orgApi';

export interface ScopeNode {
  dept_id: string;
  name_ko?: string;
  scope_node_id?: string;
  children?: ScopeNode[];
}

/** 트리를 편다 — 모든 계층이 후보다. */
export function flattenScopes(rows: ScopeNode[]): ScopeNode[] {
  const out: ScopeNode[] = [];
  for (const d of rows || []) {
    out.push(d);
    const kids = d.children;
    if (kids && kids.length) out.push(...flattenScopes(kids));
  }
  return out;
}

/** 고른 범위의 표시 이름. `picked` 가 비면 `''`(= 고르지 않음). */
export function labelForScope(flat: ScopeNode[], picked: string): string {
  const want = (picked || '').trim();
  if (!want) return '';
  const hit = flat.find((d) => d.dept_id === want || d.scope_node_id === want);
  return hit ? (hit.name_ko || hit.dept_id) : want;
}

/**
 * 조직 트리를 편 목록으로 읽는다.
 *
 * ★ `orgApi.tree()` 를 쓴다 — raw `fetch` 를 또 만들지 않는다. 그쪽에는 「볼 수 없다」와
 *   「없다」를 가르는 처리가 이미 있다.
 * ⚠️ 표시용이므로 실패는 **빈 목록**이다. 화면을 막지 않는다.
 */
export async function fetchScopeNodes(): Promise<ScopeNode[]> {
  try {
    const { rows } = await orgApi.tree();
    return flattenScopes((rows || []) as unknown as ScopeNode[]);
  } catch {
    return [];
  }
}
