/**
 * 상단 제품 셸의 회사·조직 선택기.
 *
 * 조직도 «관리»와 현재 조회 문맥 «선택»은 다른 행동이다. ProductShell의 문맥 버튼이
 * OrgChartPanel을 바로 열면 사용자는 어느 항목을 눌러야 현재 범위가 바뀌는지 알 수 없고,
 * 관리 권한이 없는 사용자에게는 선택 경로 자체가 사라진다. 이 창은 서버가 이미 가려서 준
 * 조직만 보여 주고, `POST /contexts/select` 검증을 통과한 값만 공통 요청 문맥에 저장한다.
 */
import { useState } from 'react';

import { Banner } from '../design/HubShell';
import { HubDialog } from '../design/HubDialog';
import { getEnterpriseContext, setEnterpriseContext } from '../lib/api';
import { selectContext } from '../lib/companyApi';
import { useOperatingContext } from '../lib/operatingContext';

export function OperatingContextSwitcher({ onClose, onManageCompany, onManageOrg }: {
  onClose: () => void;
  onManageCompany: () => void;
  onManageOrg: () => void;
}) {
  const ctx = useOperatingContext();
  const selected = getEnterpriseContext();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const apply = async (scopeNodeId: string, label: string) => {
    setBusy(scopeNodeId || '__all__');
    setError('');
    try {
      if (scopeNodeId) {
        const verified = await selectContext(scopeNodeId, ctx.entityMode || 'REAL');
        const verifiedScope = String(
          verified?.headers?.['X-Enterprise-Scope'] || '').trim();
        if (verifiedScope !== scopeNodeId) {
          throw new Error('서버가 확인한 조직 범위가 선택한 값과 일치하지 않습니다.');
        }
        setEnterpriseContext({
          tenantId: String(verified?.tenant_id || ctx.company || '').trim(),
          scopeNodeId: verifiedScope,
          entityMode: String(verified?.entity_mode || ctx.entityMode || 'REAL').trim(),
        });
      } else {
        // 빈 값은 «미지정»이 아니라 서버가 확정한 내 권한 전체다. 임의 조직 id를 만들지 않는다.
        setEnterpriseContext({ tenantId: ctx.company, scopeNodeId: '', entityMode: ctx.entityMode });
      }
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : `${label} 문맥을 선택하지 못했습니다.`);
    } finally {
      setBusy('');
    }
  };

  return (
    <HubDialog label="회사·조직 선택" onClose={onClose}
      subtitle="권한이 있는 범위만 표시되며, 선택한 문맥은 모든 제품 화면과 조회에 함께 적용됩니다.">
      <div className="afs-dialog-body" style={{ padding: 18, minWidth: 0, display: 'grid', gap: 14 }}>
        <section style={{
          display: 'grid', gap: 3, padding: '12px 14px', borderRadius: 8,
          background: 'var(--surface-raised)', border: '1px solid var(--surface-border)',
        }}>
          <small style={{ color: 'var(--surface-text-muted)', fontWeight: 700 }}>현재 회사</small>
          <strong style={{ fontSize: 17 }}>{ctx.companyName || '회사 연결 필요'}</strong>
          <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
            {ctx.scopeLabel} · {ctx.entityMode || 'REAL'}
          </span>
        </section>

        {!ctx.companyName && (
          <Banner tone="warn" title="회사 이름이 현재 설치 문맥과 연결되지 않았습니다">
            조직 범위는 선택할 수 있습니다. 회사 이름과 법인 연결은 아래 «회사 구성 관리»에서
            정본으로 등록하십시오.
          </Banner>
        )}
        {error && <Banner tone="error" title="문맥을 바꾸지 못했습니다">{error}</Banner>}

        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10,
            alignItems: 'baseline', marginBottom: 8 }}>
            <strong>조회할 조직 범위</strong>
            <small style={{ color: 'var(--surface-text-muted)' }}>조직 코드를 직접 입력하지 않습니다</small>
          </div>
          <div style={{ display: 'grid', gap: 6, maxHeight: 330, overflowY: 'auto' }}>
            <button type="button"
              className={!selected.scopeNodeId ? 'primary-button' : 'secondary-button'}
              disabled={!!busy} onClick={() => apply('', '내 권한 전체')}
              style={{ textAlign: 'left', justifyContent: 'space-between' }}>
              <span>내 권한 전체</span>
              <small>{ctx.me?.unrestricted ? '전사 조회 권한' : '소속·역할 기준'}</small>
            </button>
            {ctx.flat.map((d) => {
              const ref = String(d.scope_node_id || d.dept_id || '').trim();
              const active = Boolean(ref && ref === selected.scopeNodeId);
              return (
                <button key={d.dept_id} type="button"
                  className={active ? 'primary-button' : 'secondary-button'}
                  disabled={!ref || !!busy}
                  onClick={() => apply(ref, d.name_ko || '이름 미등록 조직')}
                  style={{ textAlign: 'left', justifyContent: 'flex-start',
                    paddingLeft: 12 + d._depth * 18 }}>
                  {d._depth > 0 && <span aria-hidden>└</span>}
                  <span>{d.name_ko || '이름 미등록 조직'}</span>
                  {!d.scope_node_id && <small>부서 기준</small>}
                  {busy === ref && <small>확인 중…</small>}
                </button>
              );
            })}
          </div>
          {ctx.status !== 'verified' && (
            <p style={{ margin: '8px 0 0', color: 'var(--state-warn-fg)', fontSize: 12 }}>
              {ctx.note || '조직 목록을 완전히 확인하지 못했습니다.'}
            </p>
          )}
        </section>

        <footer style={{ display: 'flex', justifyContent: 'space-between', gap: 8,
          paddingTop: 10, borderTop: '1px solid var(--surface-border)' }}>
          <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
            회사·조직 기준정보 변경은 현재 문맥 선택과 분리됩니다.
          </span>
          <div style={{ display: 'flex', gap: 7 }}>
            <button className="secondary-button" type="button" onClick={onManageOrg}>조직·권한 관리</button>
            <button className="secondary-button" type="button" onClick={onManageCompany}>회사 구성 관리</button>
          </div>
        </footer>
      </div>
    </HubDialog>
  );
}
