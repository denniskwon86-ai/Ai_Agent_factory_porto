import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  CalculationError,
  approveFinancialBridgeContract,
  createFinancialBridgeDraft,
  getFinancialBridgeProposal,
  listFinancialBridgeContracts,
  revokeFinancialBridgeContract,
  type FinancialBridgeContract,
  type FinancialBridgeProposal,
} from '../lib/calculationApi';
import type { ActingScope } from '../lib/actingScope';

const STATE_LABEL: Record<string, string> = {
  DRAFT: '검토 대기',
  APPROVED: '적용 중',
  SUPERSEDED: '이전 판',
  REVOKED: '철회됨',
};

export function FinancialBridgePanel({
  instanceId, effectiveFrom, operatorScope, onChanged,
}: {
  instanceId: string;
  effectiveFrom: string;
  operatorScope: ActingScope | null;
  onChanged: () => Promise<void>;
}) {
  const [proposal, setProposal] = useState<FinancialBridgeProposal | null>(null);
  const [contracts, setContracts] = useState<FinancialBridgeContract[]>([]);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!instanceId || !operatorScope?.isAdmin) return;
    setBusy('load'); setError('');
    try {
      const [nextProposal, listed] = await Promise.all([
        getFinancialBridgeProposal(instanceId),
        listFinancialBridgeContracts(instanceId),
      ]);
      setProposal(nextProposal);
      setContracts(listed.contracts || []);
    } catch (e: any) {
      setProposal(null);
      setError(e instanceof CalculationError ? e.message
        : (e?.message || '업무-회계 변환 기준을 불러오지 못했습니다.'));
    } finally {
      setBusy('');
    }
  }, [instanceId, operatorScope?.isAdmin]);

  useEffect(() => { void load(); }, [load]);

  const draft = useMemo(
    () => contracts.find((row) => row.status === 'DRAFT') || null,
    [contracts],
  );
  const approved = useMemo(
    () => contracts.find((row) => row.status === 'APPROVED') || null,
    [contracts],
  );

  async function createDraft() {
    if (!proposal || !effectiveFrom) return;
    setBusy('draft'); setError(''); setNotice('');
    try {
      await createFinancialBridgeDraft({
        instance_id: instanceId,
        effective_from: effectiveFrom,
        seen_proposal_fingerprint: proposal.proposal_fingerprint,
      });
      setNotice('인증된 계정과목과 환율 기준정보로 검토 초안을 만들었습니다.');
      await load();
    } catch (e: any) {
      setError(e instanceof CalculationError ? e.message
        : (e?.message || '검토 초안을 만들지 못했습니다.'));
    } finally {
      setBusy('');
    }
  }

  async function approveDraft() {
    if (!draft || !reason.trim()) return;
    setBusy('approve'); setError(''); setNotice('');
    try {
      await approveFinancialBridgeContract(draft.contract_id, {
        instance_id: instanceId,
        seen_fingerprint: draft.fingerprint,
        rationale: reason.trim(),
      });
      setReason('');
      setNotice('검토한 변환 계약을 적용했습니다.');
      await load();
      await onChanged();
    } catch (e: any) {
      setError(e instanceof CalculationError ? e.message
        : (e?.message || '변환 계약을 적용하지 못했습니다.'));
    } finally {
      setBusy('');
    }
  }

  async function revokeApproved() {
    if (!approved || !reason.trim()) return;
    setBusy('revoke'); setError(''); setNotice('');
    try {
      await revokeFinancialBridgeContract(approved.contract_id, {
        instance_id: instanceId,
        rationale: reason.trim(),
      });
      setReason('');
      setNotice('변환 계약을 철회했습니다. 재무 영향은 다시 차단됩니다.');
      await load();
      await onChanged();
    } catch (e: any) {
      setError(e instanceof CalculationError ? e.message
        : (e?.message || '변환 계약을 철회하지 못했습니다.'));
    } finally {
      setBusy('');
    }
  }

  if (!operatorScope?.isAdmin) {
    return (
      <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
        손익·현금흐름 연결 기준은 시스템 관리자가 검토·적용합니다.
      </div>
    );
  }

  return (
    <section style={{
      border: '1px solid var(--surface-border)', borderRadius: 8,
      padding: 12, background: 'var(--surface-sunken)', display: 'grid', gap: 10,
    }}>
      <div>
        <b style={{ fontSize: 14 }}>업무 결과를 회계 영향으로 연결하는 기준</b>
        <div style={{ marginTop: 3, fontSize: 12, color: 'var(--surface-text-muted)' }}>
          사용자가 코드나 ID를 입력하지 않습니다. 인증된 계정과목과 환율 기준정보에서
          시스템이 제안하고, 작성자와 다른 관리자가 검토한 뒤 적용합니다.
        </div>
      </div>

      {busy === 'load' && <div style={{ fontSize: 13 }}>기준정보 확인 중…</div>}
      {proposal && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
          gap: 8 }}>
          {proposal.rule_summaries.map((rule) => (
            <div key={rule.rule_id} style={{
              padding: 9, borderRadius: 6, border: '1px solid var(--surface-border)',
              background: 'var(--surface-card)',
            }}>
              <b style={{ fontSize: 13 }}>{rule.label}</b>
              <div style={{ marginTop: 4, fontSize: 12, color: 'var(--surface-text-muted)' }}>
                {rule.target_accounts.map((account) => account.name).join(' · ')}
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {!draft && !approved && (
          <button type="button" className="primary-button" onClick={createDraft}
            disabled={!proposal || busy !== ''}>
            {busy === 'draft' ? '초안 만드는 중…' : '검토 초안 만들기'}
          </button>
        )}
        {(draft || approved) && (
          <span style={{ fontSize: 13, fontWeight: 700,
            color: approved ? 'var(--state-success-fg)' : 'var(--state-warn-fg)' }}>
            {STATE_LABEL[(approved || draft)?.status || ''] || '상태 확인 필요'}
            {' · '}제 {(approved || draft)?.revision}판
          </span>
        )}
      </div>

      {draft && (
        <div style={{ display: 'grid', gap: 7 }}>
          {draft.drafted_by === operatorScope.userId ? (
            <div style={{ fontSize: 12, color: 'var(--state-warn-fg)' }}>
              작성자는 같은 계약을 적용할 수 없습니다. 다른 시스템 관리자가 검토해야 합니다.
            </div>
          ) : (
            <>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="검토 근거를 입력하십시오" rows={2}
                style={{ padding: 8, resize: 'vertical' }} />
              <button type="button" className="primary-button" onClick={approveDraft}
                disabled={!reason.trim() || busy !== ''}>
                {busy === 'approve' ? '적용 중…' : '검토 완료 후 적용'}
              </button>
            </>
          )}
        </div>
      )}

      {approved && (
        <details>
          <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--surface-text-muted)' }}>
            적용 중인 기준 철회
          </summary>
          <div style={{ marginTop: 8, display: 'grid', gap: 7 }}>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="철회 사유를 입력하십시오" rows={2}
              style={{ padding: 8, resize: 'vertical' }} />
            <button type="button" onClick={revokeApproved}
              disabled={!reason.trim() || busy !== ''}>
              {busy === 'revoke' ? '철회 중…' : '적용 철회'}
            </button>
          </div>
        </details>
      )}

      {notice && <div style={{ fontSize: 12, color: 'var(--state-success-fg)' }}>{notice}</div>}
      {error && <div style={{ fontSize: 12, color: 'var(--state-error-fg)' }}>{error}</div>}
    </section>
  );
}
