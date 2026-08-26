import { useCallback, useEffect, useRef, useState } from 'react';

// ★★★ 손수 모달을 만들지 않는다 — 승인된 제품 셸을 쓴다(설계 §12 UI 규칙).
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel } from '../design/HubShell';
import { listInstances } from '../lib/dataPrepApi';
import {
  approveCapabilities, CalculationError, getCapabilityProposal, getReadiness,
  getResetPlan, revokeCapability, runReset,
  type CapabilityProposal, type Gate, type GateState, type Readiness,
  type ResetPlan, type ResetResult,
} from '../lib/calculationApi';

// [G2 M0-0 · M0-5] 계산 실행 승인 · 시연 초기화 — **시스템 관리자 화면.**
//
// ## 이 화면이 지켜야 할 것
//
// ① **누르기 전까지 아무것도 승인되지 않는다.** 제안서는 제안서이고, 서버가 준
//    `notice` 를 그대로 보여 준다.
// ② **셋을 갈라 그린다**: 준비됨 / 아직 안 함 / **확인하지 못함**. 마지막을 「아직」으로
//    그리면 원장이 죽은 동안 사용자가 승인을 다시 요청하고, 몇 번을 해도 같다.
// ③ **판정하지 않는다.** 서버가 준 상태·사유·다음 행동을 그대로 옮긴다.
// ④ **지문을 화면이 만들지 않는다.** 받은 값을 되돌려 줄 뿐이다 — 그것이 「내가 본 것과
//    지금 승인되는 것이 같은가」를 서버가 확인하는 방법이다.
// ⑤ **초기화는 목록을 보여 준 뒤에만** 누를 수 있다. 무엇이 지워지는지 보지 않고
//    지우게 하지 않는다.
//
// ⚠️ 색만으로 구분하지 않는다(§12) — 이름표와 기호를 함께 단다.

const GATE_VIEW: Record<GateState, { label: string; mark: string; tone: string }> = {
  READY:   { label: '준비됨',        mark: '●', tone: 'var(--state-success-fg)' },
  NOT_YET: { label: '아직 안 함',    mark: '◐', tone: 'var(--state-warn-fg)' },
  FAILED:  { label: '확인하지 못함', mark: '⚠', tone: 'var(--state-error-fg)' },
  UNKNOWN: { label: '판정 안 함',    mark: '○', tone: 'var(--surface-text-muted)' },
};

const GATE_LABEL: Record<string, string> = {
  kit: '정본 키트 등록',
  instance: '키트 인스턴스',
  snapshots: '필수 자료 인증판',
  baseline: '계산 기준선 봉인',
  capabilities: '계산 실행 승인',
};

const DIRECTION_LABEL: Record<string, string> = { UP: '↑ 클수록 증가', DOWN: '↓ 클수록 감소' };

function Err({ error }: { error: CalculationError }) {
  // ⚠️ 상태 코드마다 **사용자가 할 일이 다르다.** 하나로 뭉치면 아무것도 못 한다.
  const hint =
    error.status === 403 ? '권한이 없거나, 시연 환경이 아닌 대상입니다.'
    : error.status === 404 ? '찾을 수 없습니다 — 조직 범위를 확인해 주십시오.'
    : error.status === 409 ? '그 사이에 대상이 바뀌었습니다 — 다시 확인한 뒤 진행하십시오.'
    : error.status === 503 ? '데이터가 없는 것이 아니라 지금 확인하지 못한 상태입니다.'
    : '';
  return (
    <div style={{
      padding: 12, border: '1px solid var(--state-error-fg)', borderRadius: 6,
      background: 'var(--state-error-bg)', fontSize: 14, marginBottom: 12,
    }}>
      <strong style={{ color: 'var(--state-error-fg)' }}>진행하지 못했습니다 ({error.status})</strong>
      <div style={{ marginTop: 4 }}>{error.message}</div>
      {hint && <div style={{ marginTop: 4, fontSize: 13, color: 'var(--surface-text-muted)' }}>{hint}</div>}
    </div>
  );
}

function GateRow({ gate }: { gate: Gate }) {
  const v = GATE_VIEW[gate.state] ?? {
    // ⚠️ 모르는 상태를 «준비됨» 으로 떨어뜨리지 않는다.
    label: `알 수 없는 상태(${gate.state})`, mark: '⚠', tone: 'var(--state-error-fg)',
  };
  return (
    <tr style={{ borderBottom: '1px solid var(--surface-border)' }}>
      <td style={{ padding: '10px 8px', fontSize: 14, whiteSpace: 'nowrap' }}>
        {GATE_LABEL[gate.gate] ?? gate.gate}
      </td>
      <td style={{ padding: '10px 8px', color: v.tone, whiteSpace: 'nowrap' }}>
        <span aria-hidden style={{ marginRight: 6 }}>{v.mark}</span>{v.label}
      </td>
      <td style={{ padding: '10px 8px', fontSize: 13 }}>
        <div>{gate.summary}</div>
        {gate.next_action && (
          <div style={{ marginTop: 2, color: 'var(--action-primary-bg)' }}>→ {gate.next_action}</div>
        )}
      </td>
    </tr>
  );
}

export function CalcApprovalPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<'readiness' | 'approve' | 'reset'>('readiness');
  const [instances, setInstances] = useState<any[] | null>(null);
  const [instanceId, setInstanceId] = useState('');
  const [error, setError] = useState<CalculationError | null>(null);
  const [busy, setBusy] = useState('');

  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [proposal, setProposal] = useState<CapabilityProposal | null>(null);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [rationale, setRationale] = useState('');
  const [approved, setApproved] = useState<string>('');
  //: ★★★ **실행 모드는 고르지 않는다** — 인스턴스가 정본이고 서버가 거기서 파생한다.
  //: ⚠️ 종전에는 여기서 골랐고 기본값이 `VIRTUAL` 이었다. `REAL` 인스턴스에 승인을 눌러도
  //:   관문은 계속 「승인 없음」이었다 — 200 과 원장 사건까지 남는데 아무 데도 오류가
  //:   나지 않으니, 사람은 자기가 승인했다고 믿는다.
  const [scopeKind, setScopeKind] = useState('');
  const [validDays, setValidDays] = useState(0);
  const [revoking, setRevoking] = useState('');
  const [revokeReason, setRevokeReason] = useState<Record<string, string>>({});

  const [plan, setPlan] = useState<ResetPlan | null>(null);
  const [resetReason, setResetReason] = useState('');
  const [resetDone, setResetDone] = useState<ResetResult | null>(null);

  useEffect(() => {
    listInstances()
      .then((r) => setInstances(r.instances || []))
      // ⚠️ 조회 실패를 빈 목록으로 그리지 않는다 — 「인스턴스가 없다」로 읽힌다.
      .catch((e) => setError(new CalculationError(
        e?.message || '키트 인스턴스 목록을 불러오지 못했습니다.', e?.status ?? 0)));
  }, []);

  //: ⚠️ **늦게 온 응답이 새 상태를 덮지 않게 한다.** 탭·인스턴스를 빠르게 바꾸면 앞선
  //:   요청이 나중에 도착해 «지금 고른 것» 이 아닌 자료를 그린다 — 화면은 멀쩡해 보이고
  //:   사용자는 그것이 자기가 고른 대상이라고 믿는다.
  const reqRef = useRef(0);

  const load = useCallback(async (which: typeof tab) => {
    if (!instanceId.trim()) return;
    const seq = ++reqRef.current;
    const fresh = () => reqRef.current === seq;
    setError(null);
    setBusy('load');
    try {
      if (which === 'readiness') {
        const got = await getReadiness(instanceId.trim());
        if (fresh()) setReadiness(got);
      }
      if (which === 'approve') {
        const got = await getCapabilityProposal({
          instanceId: instanceId.trim(),
          dataKind: scopeKind || undefined, validDays: validDays || undefined });
        if (fresh()) { setProposal(got); setPicked({}); setApproved(''); }
      }
      if (which === 'reset') {
        const got = await getResetPlan(instanceId.trim());
        if (fresh()) { setPlan(got); setResetDone(null); }
      }
    } catch (e: any) {
      if (fresh()) {
        setError(e instanceof CalculationError ? e
          : new CalculationError(e?.message || '불러오지 못했습니다.', 0));
      }
    } finally {
      if (fresh()) setBusy('');
    }
  }, [instanceId, scopeKind, validDays]);

  useEffect(() => {
    //: ★ 효과 본문에서 **동기로** setState 하지 않는다 — 한 틱 뒤에 시작한다.
    let alive = true;
    void Promise.resolve().then(() => { if (alive) return load(tab); });
    return () => { alive = false; };
  }, [tab, load]);

  const chosen = proposal?.items.filter((i) => picked[i.ref]) ?? [];
  const activeApprovalCount = proposal?.approvals.filter((a) => a.status === 'active').length ?? 0;

  async function onApprove() {
    if (!proposal || !chosen.length) return;
    setError(null);
    setBusy('approve');
    try {
      const res = await approveCapabilities({
        instance_id: instanceId.trim(),
        refs: chosen.map((i) => i.ref),
        rationale,
        data_kind: proposal.scope.data_kind,
        entity_mode: proposal.scope.entity_mode,
        valid_days: proposal.valid_days,
        // ★★★ **화면이 본 지문을 그대로 되돌려 준다.** 그 사이에 판이 바뀌면 409 다.
        seen_fingerprints: Object.fromEntries(
          chosen.map((i) => [i.ref, i.binding_fingerprint])),
      });
      setApproved(`${res.approved.length}건 승인됨 · 유효기간 ${res.valid_until.slice(0, 10)}`);
      setRationale('');
      await load('approve');
    } catch (e: any) {
      setError(e instanceof CalculationError ? e
        : new CalculationError(e?.message || '승인하지 못했습니다.', 0));
    } finally {
      setBusy('');
    }
  }

  async function onRevoke(approvalId: string) {
    // ⚠️ `window.prompt` 를 쓰지 않는다(설계 §12) — 승인 시안에 없고, 키보드 접근·
    //   스크린리더 대응이 되지 않으며, 스타일을 입힐 수 없다.
    const reason = (revokeReason[approvalId] || '').trim();
    if (!reason) {
      setError(new CalculationError(
        '철회 사유가 필요합니다 — 사유 없는 철회는 나중에 「왜 껐나」에 답할 수 없습니다.',
        422));
      return;
    }
    setError(null);
    setBusy(approvalId);
    try {
      await revokeCapability(approvalId, reason);
      setRevoking('');
      setRevokeReason({ ...revokeReason, [approvalId]: '' });
      await load('approve');
    } catch (e: any) {
      setError(e instanceof CalculationError ? e
        : new CalculationError(e?.message || '철회하지 못했습니다.', 0));
    } finally {
      setBusy('');
    }
  }

  async function onReset() {
    if (!plan) return;
    setError(null);
    setBusy('reset');
    try {
      const res = await runReset({
        instance_id: instanceId.trim(),
        reason: resetReason,
        // ★★★ **재확인** — 방금 본 그 계획이어야 한다.
        confirm_fingerprint: plan.plan_fingerprint,
      });
      setResetDone(res);
      setResetReason('');
      await load('reset');
    } catch (e: any) {
      setError(e instanceof CalculationError ? e
        : new CalculationError(e?.message || '초기화하지 못했습니다.', 0));
    } finally {
      setBusy('');
    }
  }

  const totalDelete = plan?.delete.reduce((n, d) => n + d.count, 0) ?? 0;

  return (
    // ⚠️ `subtitle` 을 주면 셸이 머리 바(제목 + 「닫기 (Esc)」)를 그린다. 빠뜨리면
    //   제목도 닫기도 없는 전체화면 창이 된다 — 실제로 그랬다(2026-08-23).
    <HubDialog label="계산 실행 승인 · 시연 초기화" onClose={onClose}
      subtitle="누르기 전까지 계산은 «막힘» 으로 답합니다. 승인은 능력마다 별도 원장 사건으로 남습니다">
      <div style={{ padding: 20, maxHeight: '82vh', overflow: 'auto' }}>
        <Panel kicker="시스템 관리자" title="계산 실행 승인 · 시연 초기화">
          <p style={{ fontSize: 13, color: 'var(--surface-text-muted)', margin: '0 0 12px' }}>
            승인된 자료로 경영 판단용 숫자를 내도 되는지 정하는 곳입니다.
            <b> 되돌려도 이미 그 숫자를 본 사람이 있습니다.</b>
          </p>

          {/* ── 대상 인스턴스 ─────────────────────────────────────────── */}
          <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
            대상 키트 인스턴스
          </label>
          {instances === null ? (
            <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>불러오는 중…</div>
          ) : instances.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
              내 범위에 키트 인스턴스가 없습니다 — 「업무 데이터 준비」에서 먼저 만드십시오.
            </div>
          ) : (
            <select value={instanceId} onChange={(e) => setInstanceId(e.target.value)}
              style={{ padding: 6, fontSize: 14, minWidth: 420 }}>
              <option value="">— 고르십시오 —</option>
              {instances.map((i) => (
                <option key={i.instance_id} value={i.instance_id}>
                  {/* ★ 기술 ID 를 앞세우지 않는다(§12) — 사람이 읽는 이름이 먼저다. */}
                  {i.label || `${i.kit_id} ${i.version}`} · {i.scope_node_id}
                </option>
              ))}
            </select>
          )}

          {/* ── 탭 ────────────────────────────────────────────────────── */}
          <div style={{ display: 'flex', gap: 6, margin: '16px 0 12px' }}>
            {([['readiness', '준비 상태'], ['approve', '실행 승인'],
               ['reset', '시연 초기화']] as const).map(([id, label]) => (
              <button key={id} onClick={() => setTab(id)}
                style={{
                  padding: '6px 14px', fontSize: 14, borderRadius: 6, cursor: 'pointer',
                  border: `1px solid ${tab === id ? 'var(--action-primary-bg)' : 'var(--surface-border)'}`,
                  background: tab === id ? 'var(--state-info-bg)' : '#fff',
                  color: tab === id ? 'var(--action-primary-bg)' : 'var(--surface-text)',
                }}>{label}</button>
            ))}
          </div>

          {error && <Err error={error} />}
          {!instanceId.trim() && (
            <div style={{ fontSize: 14, color: 'var(--surface-text-muted)' }}>
              대상 인스턴스를 고르면 내용이 표시됩니다.
            </div>
          )}

          {/* ── ① 준비 상태 ───────────────────────────────────────────── */}
          {tab === 'readiness' && instanceId.trim() && readiness && (
            <>
              <Banner tone={readiness.status === 'FAILED' ? 'error'
                : readiness.status === 'READY' ? 'info' : 'warn'}>
                {readiness.status === 'READY'
                  ? '모든 관문이 섰습니다 — 계산할 수 있습니다.'
                  : readiness.next_action || '남은 일이 있습니다.'}
              </Banner>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--surface-border)', textAlign: 'left' }}>
                    <th style={{ padding: 8, fontSize: 13 }}>관문</th>
                    <th style={{ padding: 8, fontSize: 13 }}>상태</th>
                    <th style={{ padding: 8, fontSize: 13 }}>내용</th>
                  </tr>
                </thead>
                <tbody>
                  {readiness.gates.map((g) => <GateRow key={g.gate} gate={g} />)}
                </tbody>
              </table>
              {/* ⚠️ 「판정 안 함」을 남은 일로 세지 않는다 — 앞 관문을 풀면 이미 서 있을
                  수도 있다. 서버가 그렇게 세고, 화면은 그대로 옮긴다. */}
              <p style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginTop: 8 }}>
                준비 {readiness.counts.ready} · 남음 {readiness.counts.not_yet} ·
                확인 못 함 {readiness.counts.failed} · 판정 안 함 {readiness.counts.unknown}
                <br />
                「판정 안 함」은 앞 관문이 서지 않아 <b>확인하지 않은</b> 것입니다 — 남은
                일로 세지 않습니다.
              </p>
            </>
          )}

          {/* ── ② 실행 승인 ───────────────────────────────────────────── */}
          {tab === 'approve' && instanceId.trim() && proposal && (
            <>
              <Banner tone={activeApprovalCount ? 'info' : 'warn'}
                title={activeApprovalCount
                  ? `현재 ${activeApprovalCount}건이 실행 승인되어 있습니다`
                  : '아직 실행 승인된 계산이 없습니다'}>
                {activeApprovalCount
                  ? '아래의 살아 있는 승인이 현재 실행 범위입니다. 새 승인은 선택한 산식에만 추가됩니다.'
                  : proposal.notice}
              </Banner>
              <div style={{
                display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap',
                margin: '10px 0', padding: 10, background: 'var(--surface-raised)', borderRadius: 6,
              }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                    자료 성격
                  </label>
                  <select value={scopeKind || proposal.scope.data_kind}
                    onChange={(e) => setScopeKind(e.target.value)}
                    style={{ padding: 4, fontSize: 13 }}>
                    <option value="DEMO/SYNTHETIC">DEMO/SYNTHETIC</option>
                    <option value="REAL">REAL</option>
                  </select>
                </div>
                {/* ★★★ 고르는 자리가 아니다 — **인스턴스가 정본**이다.
                    ⚠️ 2026-08-24 까지 여기서 고를 수 있었고 기본값이 `VIRTUAL` 이라,
                      `REAL` 인스턴스에 승인을 눌러도 관문은 계속 「승인 없음」이었다.
                      서버가 인스턴스에서 파생하도록 고쳤으므로 여기서는 **보여만 준다.** */}
                <div>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                    실행 모드
                  </label>
                  <div style={{ padding: '4px 0', fontSize: 13, fontWeight: 600 }}
                    title="인스턴스에서 정해집니다 — 승인 범위를 따로 고를 수 없습니다.">
                    {proposal.scope.entity_mode}
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                    유효기간(일)
                  </label>
                  <input type="number" min={1} max={90}
                    value={validDays || proposal.valid_days}
                    onChange={(e) => setValidDays(Number(e.target.value) || 0)}
                    style={{ padding: 4, fontSize: 13, width: 80 }} />
                </div>
                <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                  조직 {proposal.scope.scope_node_id}
                  {' · '}~{proposal.valid_until.slice(0, 10)} 까지
                </div>
              </div>
              {proposal.items.map((item) => (
                <div key={item.ref} style={{
                  border: '1px solid var(--surface-border)', borderRadius: 8, padding: 12,
                  marginBottom: 10, background: item.approvable ? '#fff' : 'var(--surface-raised)',
                }}>
                  <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <input type="checkbox" disabled={!item.approvable}
                      checked={!!picked[item.ref]}
                      onChange={(e) => setPicked({ ...picked, [item.ref]: e.target.checked })}
                      style={{ marginTop: 4 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>{item.ref}</div>
                      <div style={{ fontSize: 13, color: 'var(--surface-text)', marginTop: 2 }}>
                        {item.definition.relation} · 산식 판 {item.definition.model_version}
                      </div>
                      {/* ★ 정의·단위·부호를 그대로 보여 준다 — 무엇을 승인하는지 알아야 한다. */}
                      <ul style={{ margin: '6px 0', paddingLeft: 18, fontSize: 13 }}>
                        {item.definition.outputs.map((o) => (
                          <li key={o.metric}>
                            <b>{o.metric}</b> — 단위 {o.unit_display}({o.unit}) ·
                            {' '}{DIRECTION_LABEL[o.direction] ?? o.direction}
                          </li>
                        ))}
                      </ul>
                      <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                        필요 자료 {item.definition.required_datasets.join(', ')}
                        {' · '}정본 규칙 {item.definition.canonical_rules.join(', ')}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--surface-text-faint)', marginTop: 4 }}>
                        승인 대상 지문 {item.binding_fingerprint.slice(0, 16)}…
                      </div>
                      {!item.approvable && (
                        <div style={{ fontSize: 13, color: 'var(--state-error-fg)', marginTop: 6 }}>
                          인증판이 없는 계약키가 있어 승인할 수 없습니다
                          {' '}({item.missing_contract_keys.join(', ')}) — 무엇으로 계산할지
                          모르는 채 승인하면 그 승인은 아무 판에나 붙습니다.
                        </div>
                      )}
                    </div>
                  </label>
                </div>
              ))}

              <label style={{ display: 'block', fontSize: 13, margin: '12px 0 4px' }}>
                승인 사유 <span style={{ color: 'var(--state-error-fg)' }}>*</span>
              </label>
              <textarea value={rationale} onChange={(e) => setRationale(e.target.value)}
                rows={2} placeholder="왜 이 산식으로 계산해도 되는가"
                style={{ width: '100%', padding: 8, fontSize: 14, boxSizing: 'border-box' }} />
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 8 }}>
                <button disabled={!chosen.length || !rationale.trim() || busy === 'approve'}
                  onClick={onApprove}
                  style={{
                    padding: '8px 18px', fontSize: 14, borderRadius: 6,
                    /* ⚠️ [2026-08-23] 초록이 아니라 **구조색**이다. `tokens.css` 가 못박은 규칙:
                       「`action/*` 과 `state/*` 를 섞지 않는다 — 초록 버튼을 누르면 초록 성공
                       배너가 뜨는 화면은 «성공했다»와 «누를 수 있다»를 구분할 수 없다.」 */
                    border: '1px solid var(--action-primary-bg)',
                    background: (!chosen.length || !rationale.trim()) ? 'var(--surface-sunken)' : 'var(--action-primary-bg)',
                    color: (!chosen.length || !rationale.trim()) ? 'var(--surface-text-faint)' : '#fff',
                    cursor: (!chosen.length || !rationale.trim()) ? 'not-allowed' : 'pointer',
                  }}>
                  {busy === 'approve' ? '승인 중…' : `선택한 ${chosen.length}건 실행 승인`}
                </button>
                {/* ⚠️ 못 누르는 버튼에는 **사유**를 붙인다(§8.6) — 「고장」으로 읽히지 않게. */}
                {!chosen.length && (
                  <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>승인할 계산을 고르십시오.</span>
                )}
                {!!chosen.length && !rationale.trim() && (
                  <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>승인 사유가 필요합니다.</span>
                )}
              </div>
              {approved && (
                <div style={{ marginTop: 8, fontSize: 14, color: 'var(--state-success-fg)' }}>{approved}</div>
              )}

              <h4 style={{ margin: '18px 0 6px', fontSize: 15 }}>지금 살아 있는 승인</h4>
              {proposal.approvals.length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
                  없습니다 — 계산은 계속 «막힘» 으로 답합니다.
                </div>
              ) : (
                <ul style={{ paddingLeft: 18, margin: 0 }}>
                  {proposal.approvals.map((a) => (
                    <li key={a.approval_id} style={{ fontSize: 13, marginBottom: 6 }}>
                      {a.ref} · {a.status} · {a.data_kind}/{a.entity_mode} ·
                      {' '}~{a.valid_until.slice(0, 10)} · 승인 {a.approved_by}
                      {a.status === 'active' && revoking !== a.approval_id && (
                        <button onClick={() => setRevoking(a.approval_id)}
                          style={{
                            marginLeft: 8, padding: '2px 10px', fontSize: 12,
                            border: '1px solid var(--state-error-fg)', background: '#fff',
                            color: 'var(--state-error-fg)', borderRadius: 6, cursor: 'pointer',
                          }}>철회</button>
                      )}
                      {revoking === a.approval_id && (
                        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                          <input autoFocus value={revokeReason[a.approval_id] || ''}
                            onChange={(e) => setRevokeReason({
                              ...revokeReason, [a.approval_id]: e.target.value })}
                            placeholder="철회 사유"
                            style={{ flex: 1, padding: 4, fontSize: 13, maxWidth: 320 }} />
                          <button disabled={busy === a.approval_id
                            || !(revokeReason[a.approval_id] || '').trim()}
                            onClick={() => onRevoke(a.approval_id)}
                            style={{
                              padding: '2px 10px', fontSize: 12,
                              border: '1px solid var(--state-error-fg)',
                              background: (revokeReason[a.approval_id] || '').trim()
                                ? 'var(--state-error-fg)' : 'var(--surface-sunken)',
                              color: (revokeReason[a.approval_id] || '').trim()
                                ? '#fff' : 'var(--surface-text-faint)',
                              borderRadius: 6, cursor: 'pointer',
                            }}>
                            {busy === a.approval_id ? '철회 중…' : '철회 확정'}
                          </button>
                          <button onClick={() => setRevoking('')}
                            style={{
                              padding: '2px 10px', fontSize: 12, border: '1px solid var(--surface-border)',
                              background: '#fff', borderRadius: 6, cursor: 'pointer',
                            }}>취소</button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {/* ── ③ 시연 초기화 ─────────────────────────────────────────── */}
          {tab === 'reset' && instanceId.trim() && plan && (
            <>
              <Banner tone="warn" title="이번 시연에서 만든 실행 결과만 되돌립니다">
                정본과 통제는 유지됩니다 — 원장·인증판·소유권·온톨로지·계산 승인·조직.
                <b> 전체 정본 재생성은 이 버튼에 없습니다.</b>
              </Banner>
              <div style={{ fontSize: 13, color: 'var(--surface-text)', margin: '10px 0' }}>
                대상 {plan.target.kit_id} {plan.target.kit_version} ·
                {' '}키트 모드 <b>{plan.target.kit_mode}</b> · {plan.target.scope_node_id}
              </div>

              <h4 style={{ margin: '12px 0 6px', fontSize: 15, color: 'var(--state-error-fg)' }}>
                지웁니다 ({totalDelete}건)
              </h4>
              <ul style={{ paddingLeft: 18, margin: 0, fontSize: 13 }}>
                {plan.delete.map((d) => (
                  <li key={d.table} style={{ marginBottom: 2 }}>
                    {d.kind} — <b>{d.count}건</b>
                    {d.count > 0 && d.ids && (
                      <span style={{ color: 'var(--surface-text-muted)' }}> ({d.ids.slice(0, 5).join(', ')}
                        {d.ids.length > 5 ? ` 외 ${d.ids.length - 5}건` : ''})</span>
                    )}
                  </li>
                ))}
                <li>미리보기 임시 상태 — {plan.preview.path_exists ? '있음' : '없음'}</li>
              </ul>

              <h4 style={{ margin: '12px 0 6px', fontSize: 15, color: 'var(--state-warn-fg)' }}>
                남깁니다
              </h4>
              <ul style={{ paddingLeft: 18, margin: 0, fontSize: 13 }}>
                {plan.retain.map((r) => (
                  <li key={r.table} style={{ marginBottom: 2 }}>
                    {r.kind} — <b>{r.count}건</b>
                    {r.reason && <span style={{ color: 'var(--surface-text-muted)' }}> · {r.reason}</span>}
                  </li>
                ))}
              </ul>

              <h4 style={{ margin: '12px 0 6px', fontSize: 15, color: 'var(--state-success-fg)' }}>
                건드리지 않습니다
              </h4>
              <ul style={{ paddingLeft: 18, margin: 0, fontSize: 13 }}>
                {plan.preserve.map((p) => (
                  <li key={p.kind}>
                    {p.kind} —{' '}
                    {/* ⚠️ 「세지 못함」을 0 으로 그리지 않는다. */}
                    {p.count === null
                      ? <b style={{ color: 'var(--state-error-fg)' }}>세지 못했습니다</b>
                      : <b>{p.count}건</b>}
                  </li>
                ))}
              </ul>

              <label style={{ display: 'block', fontSize: 13, margin: '14px 0 4px' }}>
                초기화 사유 <span style={{ color: 'var(--state-error-fg)' }}>*</span>
              </label>
              <textarea value={resetReason} onChange={(e) => setResetReason(e.target.value)}
                rows={2} placeholder="예: 3회 리허설 2회차 준비"
                style={{ width: '100%', padding: 8, fontSize: 14, boxSizing: 'border-box' }} />
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 8 }}>
                <button disabled={!resetReason.trim() || busy === 'reset'} onClick={onReset}
                  style={{
                    padding: '8px 18px', fontSize: 14, borderRadius: 6,
                    /* ★ 되돌릴 수 없는 행동 — danger 가 맞다. 다만 «시스템이 말하는 오류»가
                       아니라 «사람이 누르는 위험 행동»이므로 `action/*` 쪽 토큰을 쓴다. */
                    border: '1px solid var(--action-danger-bg)',
                    background: resetReason.trim() ? 'var(--action-danger-bg)' : 'var(--surface-sunken)',
                    color: resetReason.trim() ? '#fff' : 'var(--surface-text-faint)',
                    cursor: resetReason.trim() ? 'pointer' : 'not-allowed',
                  }}>
                  {busy === 'reset' ? '초기화 중…'
                    : `위 목록을 지우고 시연을 처음으로 (${totalDelete}건${
                        plan.preview.path_exists ? ' + 미리보기' : ''})`}
                </button>
                {!resetReason.trim() && (
                  <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>초기화 사유가 필요합니다.</span>
                )}
              </div>
              <p style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginTop: 6 }}>
                {/* ★ 재확인이 무엇인지 사람에게 말한다 — 숨기면 409 가 「고장」으로 읽힌다. */}
                이 목록을 확인한 시각의 상태로 지웁니다. 그 사이에 자료가 바뀌면 초기화가
                거부되고 목록을 다시 보여 드립니다.
              </p>

              {resetDone && (
                <div style={{
                  marginTop: 12, padding: 12, border: '1px solid var(--state-success-fg)',
                  background: 'var(--state-success-bg)', borderRadius: 6, fontSize: 13,
                }}>
                  <b style={{ color: 'var(--state-success-fg)' }}>초기화했습니다.</b>
                  <div style={{ marginTop: 4 }}>
                    {Object.entries(resetDone.deleted)
                      .map(([t, n]) => `${t} ${n}건`).join(' · ')}
                    {resetDone.preview_cleared ? ' · 미리보기 임시 상태' : ''}
                  </div>
                  <div style={{ marginTop: 4, color: 'var(--surface-text)' }}>
                    {/* ★★★ 유지 대상이 그대로임을 **지문으로** 보인다. */}
                    유지 대상 지문{' '}
                    {resetDone.before_fingerprint === resetDone.after_fingerprint
                      ? <b style={{ color: 'var(--state-success-fg)' }}>변동 없음 ✓</b>
                      : <b style={{ color: 'var(--state-error-fg)' }}>바뀌었습니다 — 점검이 필요합니다</b>}
                  </div>
                  <div style={{ marginTop: 4, color: 'var(--surface-text-muted)', fontSize: 12 }}>
                    원장 사건 {resetDone.requested_event_id} → {resetDone.completed_event_id}
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>
      </div>
    </HubDialog>
  );
}
