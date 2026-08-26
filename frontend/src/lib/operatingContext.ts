// [UI 설계서 §4.1 · 채택 결정문 §1.2 ⑥] **지금 어느 회사의 어느 조직을, 실제인지 가상인지.**
//
// ## ⚠️⚠️ [2026-08-25 실측] 왜 이 파일이 생겼는가
//
// 승인 시안의 상단 셸(`ProductShell`)로 갈아 끼우면서 **문맥을 푸는 규칙이 통째로
// 빠졌다.** 새 셸은 `getEnterpriseContext().tenantId` 를 그대로 썼는데, 그 값은
// **사용자가 조직을 고를 때만** 채워진다. 그래서 로그인 직후 화면이 이렇게 떴다:
//
//     ?  |  OPERATING CONTEXT  |  확인 중  |  REAL
//
// 회사 Context 상시 노출은 채택 결정문이 **고정 요소로 못박은** 여섯 번째 항목이다.
// 그 자리가 물음표가 됐는데 오류는 한 줄도 없었다 — 「승인 시안으로 갈아 끼우다가
// 대체물이 굳는」 전형이다.
//
// ★ 규칙 자체는 `CompanyContextBar` 가 이미 어렵게 세워 두었다(아래 주석은 그 파일에서
//   **그대로** 옮긴 것이다). 다시 쓰지 않고 **한 곳으로 빼서 둘이 같이 쓴다** —
//   복제하면 두 곳이 다른 회사 이름을 적는 날이 온다.
import { useEffect, useState } from 'react';

import { apiFetch, getEnterpriseContext, setEnterpriseContext } from './api';
import {
  getTree as getCompanyTree, listEntities, listTenants,
  type EcmNode, type Entity, type Tenant,
} from './companyApi';
import { orgApi, type Dept } from './orgApi';

const COMPANY_NAME_CACHE_KEY = 'factory.companyNameByTenant';

function cachedCompanyName(tenantId: string): string {
  if (!tenantId) return '';
  try {
    const values = JSON.parse(localStorage.getItem(COMPANY_NAME_CACHE_KEY) || '{}');
    return typeof values?.[tenantId] === 'string' ? values[tenantId].trim() : '';
  } catch { return ''; }
}

function rememberCompanyName(tenantId: string, companyName: string): void {
  if (!tenantId || !companyName) return;
  try {
    const values = JSON.parse(localStorage.getItem(COMPANY_NAME_CACHE_KEY) || '{}');
    localStorage.setItem(COMPANY_NAME_CACHE_KEY,
      JSON.stringify({ ...(values && typeof values === 'object' ? values : {}),
        [tenantId]: companyName }));
  } catch { /* 표시 캐시를 저장하지 못해도 서버 정본 조회는 계속된다 */ }
}

export type ContextStatus = 'loading' | 'verified' | 'denied' | 'stale';

export type Me = {
  primary_dept_id?: string;
  unrestricted?: boolean;
  tenant_id?: string;
  company_name?: string;
};

/** 중첩 트리를 **깊이 표시가 붙은 평평한 목록**으로 편다.
 *
 * ★★★ [2026-08-20 실측] `orgApi.tree()` 는 `children` 이 중첩된 **트리**를 준다. 그런데
 *   그것을 평평한 목록으로 `map` 하고 있었다 — 그래서 드롭다운에 **뿌리만** 떴고,
 *   사업부·공장은 권한이 있어도 **영영 고를 수 없었다.**
 * ⚠️ 깊이는 **들여쓰기 문자**로 표시한다 — 색·여백만으로 계층을 말하면 좁은 화면과
 *   흑백에서 사라진다(설계 §2.1). */
export function flattenDepts(rows: Dept[], depth = 0): (Dept & { _depth: number })[] {
  const out: (Dept & { _depth: number })[] = [];
  for (const d of rows || []) {
    out.push({ ...d, _depth: depth });
    const kids = (d as any).children as Dept[] | undefined;
    if (kids && kids.length) out.push(...flattenDepts(kids, depth + 1));
  }
  return out;
}

export type OperatingContext = {
  /** 회사 **식별자**. 지어내지 않는다 — 고른 값이 없으면 서버가 말한 값이다. */
  company: string;
  /** 회사의 **사람이 읽는 이름**. ⚠️ 없으면 빈 문자열 — 화면이 식별자를 쓴다. */
  companyName: string;
  /** 지금 실제로 보고 있는 범위를 한 마디로. */
  scopeLabel: string;
  /** REAL · VIRTUAL · COMPETITOR */
  entityMode: string;
  status: ContextStatus;
  note: string;
  depts: Dept[];
  flat: (Dept & { _depth: number })[];
  me: Me | null;
  /** 등록된 회사 목록 — 회사 전환기가 쓴다. */
  tenants: Tenant[];
};

/** 상단 문맥 한 줄을 만든다. **표시만 한다 — 문맥을 자동으로 채우지 않는다.**
 *
 * ⚠️ 자동으로 채우면 관리자의 «전체 범위» 가 «본사 하위» 로 조용히 좁아진다 —
 *   보이는 것과 권한이 달라지는 쪽이 훨씬 위험하다. */
export function useOperatingContext(): OperatingContext {
  const [revision, setRevision] = useState(0);
  const [depts, setDepts] = useState<Dept[]>([]);
  const [status, setStatus] = useState<ContextStatus>('loading');
  const [note, setNote] = useState('');
  const [me, setMe] = useState<Me | null>(null);
  //: ★★★ [2026-08-25] 회사 이름은 **저장소가 갖는다**(`tenants` 표).
  //: ⚠️ 없으면 채우지 않는다 — 식별자에서 이름을 만들어 내면(접두어 자르기 같은) 회사
  //:   이름이 코드가 되고, 이름을 바꾸려면 배포를 해야 한다.
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [companyTree, setCompanyTree] = useState<EcmNode[]>([]);
  useEffect(() => {
    const refresh = () => setRevision((v) => v + 1);
    window.addEventListener('factory:session-changed', refresh);
    window.addEventListener('factory:enterprise-context-changed', refresh);
    window.addEventListener('factory:company-configuration-changed', refresh);
    return () => {
      window.removeEventListener('factory:session-changed', refresh);
      window.removeEventListener('factory:enterprise-context-changed', refresh);
      window.removeEventListener('factory:company-configuration-changed', refresh);
    };
  }, []);

  useEffect(() => {
    let alive = true;
    listTenants()
      .then((rows) => { if (alive) setTenants(rows || []); })
      .catch(() => { /* 표시용이다 — 실패해도 앱을 막지 않는다 */ });
    listEntities()
      .then((rows) => { if (alive) setEntities(rows || []); })
      .catch(() => { /* tenant 이름이 있으면 그것만으로 표시할 수 있다 */ });
    getCompanyTree()
      .then((rows) => { if (alive) setCompanyTree(rows || []); })
      .catch(() => { /* 회사 이름표·법인 목록으로 계속 해석한다 */ });
    return () => { alive = false; };
  }, [revision]);

  useEffect(() => {
    let alive = true;
    orgApi.tree()
      .then(({ rows, blockedReason }) => {
        if (!alive) return;
        setDepts(rows || []);
        // ⚠️ 「볼 수 없다」와 「없다」를 나눈다 — 조직이 안 보이는 이유가 권한이면 그렇게 말한다.
        if (blockedReason) { setStatus('denied'); setNote(blockedReason); }
        else setStatus('verified');
      })
      .catch((e) => {
        if (!alive) return;
        setStatus('stale');
        setNote(e?.message || '조직 정보를 확인하지 못했습니다.');
      });
    return () => { alive = false; };
  }, [revision]);

  useEffect(() => {
    let alive = true;
    apiFetch('/api/v1/auth/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!alive || !j?.data) return;
        const sessionTenant = String(j.data.tenant_id || '').trim();
        const selected = getEnterpriseContext();
        if (sessionTenant && selected.tenantId !== sessionTenant) {
          // ★ 설치본/로그인 세션의 tenant가 정본이다. 브라우저에는 이전 서버에서 고른
          // tenant·scope가 남을 수 있다. tenant만 바꾸고 scope를 남기면 옛 회사의 조직
          // 노드를 새 회사에 보내므로 상단은 계속 「회사/조직 연결 필요」가 되고, API도
          // 옛 tenant 헤더로 조회한다. 회사가 바뀌는 순간 범위도 함께 비운 뒤 재조회한다.
          setEnterpriseContext({ tenantId: sessionTenant, scopeNodeId: '' });
        }
        setMe(j.data);
      })
      .catch(() => { /* 표시용이다 — 실패해도 앱을 막지 않는다 */ });
    return () => { alive = false; };
  }, [revision]);

  const ctx = getEnterpriseContext();
  const flat = flattenDepts(depts);

  /** 지금 **고른** 조직. ⚠️⚠️ [2026-08-24 실측] **빈 값으로 찾지 않는다.**
   *
   *  종전 코드는 `ctx.scopeNodeId` 가 빈 문자열이어도 그대로 `find` 에 넣었다. 그런데
   *  조직도에는 **범위가 아직 비어 있는 부서**가 있다. 그래서 «아무것도 고르지 않은»
   *  상태에서 상단바가 그 부서를 골라 「tenant-… › 테스트」라고 적었다 — 사용자는
   *  자기가 그 조직에 있다고 읽는다.
   *
   *  ★ 「비었다」는 «전부와 일치» 가 아니라 «비교하지 않는다» 다. */
  const picked = (ctx.scopeNodeId || '').trim();
  const current = picked
    ? flat.find((d) => d.dept_id === picked || (d as any).scope_node_id === picked)
    : undefined;

  /** 고른 것이 없으면 «없다» 가 아니라 «권한 범위 전체» 다 — 그것이 서버가 하는 일이다. */
  const scopeLabel = status === 'loading' ? '확인 중…'
    : current ? (current.name_ko || current.dept_id)
      // 식별자가 정본 조직도에 결속되지 않았으면 그 코드를 사람 이름처럼 내보내지 않는다.
      // 잘못된 이름을 지어내지도 않고, 사용자가 회사 구성에서 고칠 자리도 분명히 한다.
      : picked ? '조직 연결 필요'
        : me?.unrestricted ? '권한 범위 전체'
          : me?.primary_dept_id
            ? `내 소속 전체 · ${flat.find((d) => d.dept_id === me.primary_dept_id)?.name_ko
                || me.primary_dept_id}`
            : '범위 확인 중…';

  /** 소속 회사. ⚠️ [2026-08-23 사용자 지적] 「소속 회사가 첫 화면에 뜨지도 않는다」.
   *
   *  클라이언트 문맥(`ctx.tenantId`)은 **사용자가 조직을 고를 때만** 채워지므로 로그인
   *  직후에는 비어 있다. 종전에는 그 자리에 `tenant_default` 라는 **없는 값**을 지어냈고,
   *  그것을 지우자 회사가 아예 사라졌다.
   *  ★ 서버가 `/auth/me` 로 **자기가 실제로 쓰는 테넌트**를 알려 준다. 고른 값이 있으면
   *    그것을, 없으면 서버가 말한 값을 쓴다 — 어느 쪽도 지어내지 않는다. */
  // 인증 서버가 말한 설치본 테넌트가 정본이다. 브라우저 localStorage에는 이전 시연 서버의
  // tenant가 남을 수 있으므로 그것을 먼저 쓰면 새 서버에서도 옛 코드 ID가 계속 보인다.
  // 현재 제품에는 tenant 전환 API가 없고 조직/REAL·VIRTUAL 문맥만 전환하므로, 선택값은
  // 서버가 아직 답하지 못한 짧은 로딩 구간의 보조값으로만 쓴다.
  const company = (me?.tenant_id || ctx.tenantId || '').trim();

  //: ★ tenant 이름이 정본이다. 과거 자료처럼 tenant 이름표가 아직 없고 승인된 실제 법인이
  //:   정확히 하나라면 그 법인 이름도 저장된 사실이므로 쓸 수 있다. 둘 이상이면 고르지 않는다.
  const realEntities = entities.filter((e) => e.tenant_id === company
    && e.entity_mode === 'REAL' && e.status === 'ACTIVE');

  // 현재 범위/소속 부서가 속한 가장 가까운 법인. ★ 그룹 전체에 실제 법인이 여럿이어도
  // 사용자의 조직 경로는 하나이므로 `LS`나 첫 번째 법인을 임의 선택하지 않는다.
  const companyPath: EcmNode[][] = [];
  const walkCompany = (rows: EcmNode[], parents: EcmNode[] = []) => {
    for (const n of rows) {
      const path = [...parents, n];
      companyPath.push(path);
      walkCompany(n.children || [], path);
    }
  };
  walkCompany(companyTree);
  const scopeRef = (ctx.scopeNodeId || '').trim();
  const deptRef = (me?.primary_dept_id || '').trim();
  const matchedPaths = companyPath.filter((path) => {
    const leaf = path[path.length - 1];
    return scopeRef
      ? leaf.node_id === scopeRef
      : Boolean(deptRef && leaf.dept_id === deptRef);
  });
  const legalNames = [...new Set(matchedPaths.map((path) =>
    [...path].reverse().find((n) => n.node_type === 'legal_entity')?.name_ko || '')
    .filter(Boolean))];
  const contextualCompanyName = legalNames.length === 1 ? legalNames[0] : '';
  // 선택 범위로 트리가 잘려 오면 경로 안에 상위 `legal_entity` 노드가 없을 수 있다.
  // 그때 회사명을 지우지 말고, 선택 노드가 명시한 `entity_id`를 실제 법인 정본과 대조한다.
  // 이름을 node_id나 tenant_id에서 추측하지는 않는다.
  const matchedEntityIds = [...new Set(matchedPaths.map((path) =>
    path[path.length - 1]?.entity_id || '').filter(Boolean))];
  const contextualEntityNames = [...new Set(matchedEntityIds.map((entityId) =>
    realEntities.find((e) => e.entity_id === entityId)?.name_ko || '').filter(Boolean))];
  const contextualEntityName = contextualEntityNames.length === 1 ? contextualEntityNames[0] : '';
  const verifiedCompanyName = (String(me?.company_name || '').trim()
    || tenants.find((t) => t.tenant_id === company)?.name_ko
    || contextualCompanyName
    || contextualEntityName
    || (realEntities.length === 1 ? realEntities[0].name_ko : '') || '').trim();
  // 범위 선택 뒤 서버가 하위 트리만 주는 짧은 구간에도 마지막으로 확인한 이름을 유지한다.
  // 캐시는 tenant별이며, 인증 응답·tenant 정본·법인 정본 중 하나가 다시 오면 즉시 덮어쓴다.
  if (verifiedCompanyName) rememberCompanyName(company, verifiedCompanyName);
  const companyName = verifiedCompanyName || cachedCompanyName(company);

  return {
    company,
    companyName,
    tenants,
    scopeLabel,
    entityMode: (ctx.entityMode || 'REAL').toUpperCase(),
    status, note, depts, flat, me,
  };
}
