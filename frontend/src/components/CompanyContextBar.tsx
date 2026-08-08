// [UI 설계서 §4.1] `CompanyContextBar` — 상단 회사·사업부·공장 Context.
//
// §1.2 「승인 시안에서 고정할 요소」 6번이 이것이다. 화면 어디에 있든 **지금 어느 회사의
// 어느 조직을, 실제인지 가상인지** 알 수 있어야 한다.
//
// ## 설계가 못박은 것
//
// · 구성: CI, 회사명, 문맥 breadcrumb, REAL/VIRTUAL/COMPETITOR 배지, 회사 전환
// · 상태: loading, verified, denied, stale
// · **금지: 문맥 ID 를 사용자가 직접 텍스트 입력하게 하지 않는다**
// · REAL 은 네이비·브랜드색, VIRTUAL 은 보라 계열 배지로 구분하되 **색만으로 상태를 전달하지
//   않는다**(§2.1 공통 규칙)
import { useEffect, useState } from 'react';

import { getEnterpriseContext, setEnterpriseContext } from '../lib/api';
import { orgApi, type Dept } from '../lib/orgApi';

type Status = 'loading' | 'verified' | 'denied' | 'stale';

const MODE_KO: Record<string, string> = {
  REAL: '실제', VIRTUAL: '가상', COMPETITOR: '경쟁사',
};

export function CompanyContextBar() {
  const [depts, setDepts] = useState<Dept[]>([]);
  const [status, setStatus] = useState<Status>('loading');
  const [note, setNote] = useState('');
  const [open, setOpen] = useState(false);
  const ctx = getEnterpriseContext();
  const mode = (ctx.entityMode || 'REAL').toUpperCase();

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

  const current = depts.find((d) => d.dept_id === ctx.scopeNodeId
    || (d as any).scope_node_id === ctx.scopeNodeId);

  const pick = (d: Dept) => {
    // §4.1 동작: 전환 → 공통 헤더 갱신 → 모든 Read Model 재조회.
    // ⚠️ 여기서 화면을 직접 새로 그리지 않고 **문맥만 바꾸고 새로고침**한다. 화면마다 자기
    //   캐시를 갖고 있어서, 문맥만 바꾸면 **이전 조직의 목록이 그대로 남는다.**
    setEnterpriseContext({ scopeNodeId: (d as any).scope_node_id || d.dept_id });
    window.location.reload();
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, position: 'relative' }}>
      {/* CI + 제품명 */}
      <span style={{ fontSize: 15, fontWeight: 800, whiteSpace: 'nowrap',
        color: 'var(--bar-fg)' }}>
        🏭 AI Factory Studio
      </span>

      <span style={{ color: 'var(--bar-border)' }}>│</span>

      {/* 문맥 breadcrumb — 회사 › 조직 */}
      <span style={{ fontSize: 13, color: 'var(--bar-fg-muted)', whiteSpace: 'nowrap',
        overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 260 }}>
        {ctx.tenantId || 'tenant_default'}
        {' › '}
        {status === 'loading' ? '확인 중…'
          : current ? (current.name_ko || current.dept_id)
            : (ctx.scopeNodeId || '조직 미지정')}
      </span>

      {/* REAL / VIRTUAL 배지 — 색만으로 전달하지 않으므로 낱말을 함께 적는다 */}
      <span style={{
        fontSize: 12, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
        whiteSpace: 'nowrap',
        background: mode === 'REAL' ? 'rgba(255,255,255,.14)' : 'rgba(167,139,250,.22)',
        color: mode === 'REAL' ? 'var(--bar-fg)' : '#ddd6fe',
        border: `1px solid ${mode === 'REAL' ? 'var(--bar-border)' : '#8b5cf6'}`,
      }}>
        {mode === 'REAL' ? '실제' : `⚠️ ${MODE_KO[mode] || mode}`}
      </span>

      {/* 상태 — verified 가 아니면 **왜** 인지 말한다 */}
      {status !== 'verified' && (
        <span title={note} style={{ fontSize: 12, color: 'var(--health-degraded)',
          whiteSpace: 'nowrap' }}>
          {status === 'loading' ? '확인 중' : status === 'denied' ? '조직 조회 권한 없음' : '확인 실패'}
        </span>
      )}

      {/* 회사·조직 전환. ⚠️ **텍스트 입력을 주지 않는다**(§4.1 금지) — 고르는 것만 허용한다. */}
      <button onClick={() => setOpen((v) => !v)} className="secondary-button"
        style={{ fontSize: 12, padding: '4px 10px', whiteSpace: 'nowrap' }}
        disabled={status === 'loading' || depts.length === 0}>
        조직 전환 ▾
      </button>

      {open && depts.length > 0 && (
        <div className="afs-scope" style={{
          position: 'absolute', top: '100%', left: 0, marginTop: 6, zIndex: 40,
          background: 'var(--surface-card)', border: '1px solid var(--surface-border)',
          borderRadius: 8, boxShadow: 'var(--surface-shadow)', minWidth: 260,
          maxHeight: 320, overflowY: 'auto', padding: 6,
        }}>
          {depts.map((d) => (
            <button key={d.dept_id} onClick={() => pick(d)}
              style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '8px 10px',
                fontSize: 13, borderRadius: 6, border: 'none', background: 'transparent',
                color: 'var(--surface-text)', cursor: 'pointer',
              }}>
              {d.name_ko || d.dept_id}
            </button>
          ))}
          <div style={{ borderTop: '1px solid var(--surface-border)', marginTop: 6,
            paddingTop: 6 }}>
            {/* §4.1 — 드롭다운 마지막에 「회사 구조·가상회사 관리」 진입을 **고정**한다. */}
            <span style={{ display: 'block', padding: '6px 10px', fontSize: 12,
              color: 'var(--surface-text-muted)' }}>
              회사 구조·가상회사 관리는 «조직·권한» 화면에서 합니다.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
