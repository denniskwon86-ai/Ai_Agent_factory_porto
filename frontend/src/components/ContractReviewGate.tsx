import { useCallback, useEffect, useState } from 'react';

import {
  decideContractReview, getContractReviewPending, type ContractReviewPending,
} from '../lib/contractReviewApi';
import { useFactoryStore } from '../store/useFactoryStore';

// [I-4 4c-3] **계약 검토 승인 자리.**
//
// ## ⚠️⚠️ [2026-08-25 실측] 왜 이 화면이 생겼는가
//
// SW 생성기는 Tech Lead 다음에 계약을 컴파일하고 **사람의 검토**를 받는다. 승인 전에는
// 코드로 넘어가지 않는다 — 검토를 지나지 않은 권한이 DB 에 들어가면 안 되기 때문이다.
//
// 그 게이트는 `ContractReviewPending` 노드에서 **멈춘다.** 서버에는 승인 API 가 둘 다
// 있었는데 **화면에서 부르는 곳이 0건이었다** — 즉 파이프라인이 멈추면 사용자는
// 되살릴 방법이 없었다. 「앱이 처음부터 끝까지 만들어지지 않는」 이유의 하나다.
//
// ★ 일반 HOTL 재개(`/hotl/resume`)로는 지날 수 없다([4c-4]) — **빈 피드백을 승인으로
//   해석하지 않는다.** 그래서 전용 결정 API 를 쓴다.

export function ContractReviewGate() {
  const projectId = useFactoryStore((s) => s.currentProjectId);
  const state = useFactoryStore((s) => s.state);
  const hotlTaskId = useFactoryStore((s) => s.hotlTaskId);
  const taskId = (state?.current_sprint_task_id || hotlTaskId || '') as string;

  const [row, setRow] = useState<ContractReviewPending | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState('');
  const [rationale, setRationale] = useState('');
  const [done, setDone] = useState('');

  const load = useCallback(async () => {
    if (!projectId || !taskId) { setRow(null); return; }
    try {
      setRow(await getContractReviewPending(projectId, taskId));
      setErr('');
    } catch (e: any) {
      // ⚠️ 403 은 「승인 권한이 없다」다 — 「검토가 없다」와 다르다. 섞으면 사용자는
      //   기다리기만 하고, 승인할 수 있는 사람을 부르지 않는다.
      setRow(null);
      setErr(e?.status === 403
        ? '이 프로젝트의 계약을 승인할 권한이 없습니다 — 담당자에게 요청하십시오.'
        : '');
    }
  }, [projectId, taskId]);

  useEffect(() => { void load(); }, [load]);

  //: ★ 파이프라인이 멈출 때 서버가 보내는 신호를 듣는다. 안 들으면 사용자가 새로고침해야
  //:   승인 자리가 나타난다 — 그때는 이미 「멈춰 있는데 아무 말이 없는」 시간이 지난 뒤다.
  useEffect(() => {
    const onPending = () => { void load(); };
    window.addEventListener('factory:contract-review-pending', onPending);
    return () => window.removeEventListener('factory:contract-review-pending', onPending);
  }, [load]);

  if (err) {
    return (
      <div style={{
        margin: 12, padding: 12, borderRadius: 8,
        border: '1px solid var(--state-warn-fg, #b45309)', fontSize: 13,
      }}>{err}</div>
    );
  }
  if (!row?.pending) return null;

  const decide = async (decision: 'APPROVE' | 'REJECT') => {
    if (!projectId) return;
    // ⚠️ 반려에는 사유가 필요하다 — 「왜 안 되는지」 없이 반려하면 다음 사람이 같은 것을
    //   다시 올린다. 승인은 사유가 선택이다(승인은 «이대로 간다» 이므로).
    if (decision === 'REJECT' && !rationale.trim()) {
      setErr('반려 사유를 적어 주십시오.');
      return;
    }
    setBusy(decision); setErr(''); setDone('');
    try {
      const r = await decideContractReview(projectId, {
        task_id: taskId, request_event_id: row.request_event_id || '',
        decision, rationale: rationale.trim(),
      });
      // ★★★ `state_applied=false` 는 **결정은 남았는데 파이프라인 반영이 실패**한 것이다.
      //   다시 승인하면 원장에 두 번 남는다 — 재개만 다시 하도록 그대로 말한다.
      setDone(r.state_applied
        ? (decision === 'APPROVE'
          ? '승인했습니다 — 다시 가동하면 이 계약으로 이어서 만듭니다.'
          : '반려했습니다 — Tech Lead 가 계약을 다시 만들어야 합니다.')
        : (r.note || '결정은 기록됐지만 파이프라인 반영에 실패했습니다 — 다시 승인하지 마시고 재개를 다시 시도하십시오.'));
      await load();
    } catch (e: any) {
      setErr(e?.status === 409
        ? `지금 결정할 계약 검토가 없습니다 — ${e.message}`
        : (e?.message || '결정을 기록하지 못했습니다.'));
    } finally { setBusy(''); }
  };

  const changed = !!row.previous_approved_fingerprint
    && row.previous_approved_fingerprint !== row.compiled_fingerprint;

  return (
    <div style={{
      margin: 12, padding: 14, borderRadius: 8, display: 'grid', gap: 8,
      border: '2px solid var(--ls-red, #fa002d)',
      background: 'var(--state-error-bg, #fff5f6)',
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 15 }}>계약 승인이 필요합니다</strong>
        <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
          {changed ? '이전에 승인한 계약과 내용이 달라졌습니다' : '이 프로젝트의 첫 계약입니다'}
        </span>
      </div>
      {/* ★ 서버가 준 사유를 그대로 옮긴다 — 화면이 다시 설명하지 않는다. */}
      <div style={{ fontSize: 13 }}>{row.reason}</div>
      <div style={{ fontSize: 11, color: 'var(--surface-text-muted)' }}>
        {/* ⚠️ 지문은 **기술 메타데이터**다 — 짧게 보여 주되 사용자가 외울 것은 아니다. */}
        계약 지문 {String(row.compiled_fingerprint || '').slice(0, 12)}…
        {row.requested_at ? ` · 요청 ${row.requested_at.slice(0, 16).replace('T', ' ')}` : ''}
      </div>
      <input value={rationale} onChange={(e) => setRationale(e.target.value)}
        placeholder="사유 — 반려할 때는 반드시 적습니다"
        style={{ fontSize: 13, padding: '6px 9px' }} />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" disabled={!!busy}
          onClick={() => void decide('APPROVE')}
          style={{ fontSize: 13, padding: '7px 16px', fontWeight: 700 }}>
          {busy === 'APPROVE' ? '승인하는 중…' : '승인하고 계속 만들기'}
        </button>
        <button type="button" disabled={!!busy}
          onClick={() => void decide('REJECT')}
          style={{ fontSize: 13, padding: '7px 16px' }}>
          {busy === 'REJECT' ? '반려하는 중…' : '반려'}
        </button>
      </div>
      {done && (
        <div style={{ fontSize: 13, color: 'var(--state-success-fg, #15803d)' }}>{done}</div>
      )}
    </div>
  );
}
