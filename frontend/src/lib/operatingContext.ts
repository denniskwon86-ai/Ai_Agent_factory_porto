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

import { API_BASE_URL, getEnterpriseContext, getSessionToken } from './api';
import { orgApi, type Dept } from './orgApi';

export type ContextStatus = 'loading' | 'verified' | 'denied' | 'stale';

export type Me = {
  primary_dept_id?: string;
  unrestricted?: boolean;
  tenant_id?: string;
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
  /** 소속 회사. **지어내지 않는다** — 고른 값이 없으면 서버가 말한 값이다. */
  company: string;
  /** 지금 실제로 보고 있는 범위를 한 마디로. */
  scopeLabel: string;
  /** REAL · VIRTUAL · COMPETITOR */
  entityMode: string;
  status: ContextStatus;
  note: string;
  depts: Dept[];
  flat: (Dept & { _depth: number })[];
  me: Me | null;
};

/** 상단 문맥 한 줄을 만든다. **표시만 한다 — 문맥을 자동으로 채우지 않는다.**
 *
 * ⚠️ 자동으로 채우면 관리자의 «전체 범위» 가 «본사 하위» 로 조용히 좁아진다 —
 *   보이는 것과 권한이 달라지는 쪽이 훨씬 위험하다. */
export function useOperatingContext(): OperatingContext {
  const [depts, setDepts] = useState<Dept[]>([]);
  const [status, setStatus] = useState<ContextStatus>('loading');
  const [note, setNote] = useState('');
  const [me, setMe] = useState<Me | null>(null);

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
  }, []);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE_URL}/api/v1/auth/me`, {
      headers: { 'X-Session-Token': getSessionToken() },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (alive && j?.data) setMe(j.data); })
      .catch(() => { /* 표시용이다 — 실패해도 앱을 막지 않는다 */ });
    return () => { alive = false; };
  }, []);

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
      : picked ? picked
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
  const company = (ctx.tenantId || me?.tenant_id || '').trim();

  return {
    company,
    scopeLabel,
    entityMode: (ctx.entityMode || 'REAL').toUpperCase(),
    status, note, depts, flat, me,
  };
}
