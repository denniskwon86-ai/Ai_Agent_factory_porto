// [이관 F 3/8] Shadow Mode — 병렬 검증 · 제한적 승격 (명세서 §7.3 / §7.4 · M2)
//
// 이 화면이 반드시 지켜야 하는 것 — 백엔드가 막는 것과 같은 것을 화면도 흐리지 않는다:
//   ① 승격 전 결과를 운영값처럼 보여주지 않는다 (배지로 항상 구분)
//   ② `unmeasured` 를 개선/악화와 같은 칸에 넣지 않는다 (0 이 아니라 판정 제외다)
//   ③ 비교 불가는 실패가 아니라 **판정 불가**로 표시한다 (입력을 맞춰 다시 돌려야 한다)
//   ④ 악화 항목은 체크해서 인정해야 승인 버튼이 동작한다 (백엔드가 거절하는 이유를 미리 보여준다)
//
// ## ★★★ 이관에서 드러난 것 — 조회 실패가 «등록된 run 이 없습니다» 였다
//
// 종전 `load()` 는 `Promise.allSettled` 로 받아 실패하면 `err` 문자열만 세우고 `runs` 는
// **빈 배열 그대로** 뒀다. 그래서 권한이 없거나 서버가 죽어도 목록 자리에는
// 「등록된 run 이 없습니다」가 찍혔다 — 이 화면에서 그것은 「검증할 것이 없다」로 읽힌다.
// 게다가 두 요청의 오류 문구가 같은 변수에 덮어써져 **어느 쪽이 실패했는지도 사라졌다.**
// → 요약과 목록을 각각 `Loaded<T>` 로 받는다.
//
// ## 새로 막은 것 — 「승격」이 누르는 즉시 나갔다
//
// 승격은 **운영 적용**이다(§7.3 5단계). 확인 단계 없이 버튼 하나로 나가고 있었다.
// `ConfirmInline` 으로 «어느 범위에 적용되는지» 를 다시 보여주고 확인받는다.
//
// ## 종전 구현에서 제거한 것
//
//   · 자체 `fixed inset-0` 전체화면(모달 semantics·포커스 트랩·Escape 없음) → `HubDialog`
//   · `String(e)` 를 그대로 찍어 «Error: ...» 가 사용자에게 노출되던 것 2곳
//   · **10~11px 글자 14곳** → 본문 12px 이상
//   · slate/violet 팔레트 직접 지정 → 디자인 토큰
import { useCallback, useEffect, useState } from 'react';

import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import type { MetricRow, ShadowRun, ShadowSummary } from '../lib/shadowApi';
import {
  compareRun, fetchRuns, fetchSummary, promoteRun, reviewRun,
} from '../lib/shadowApi';

type Props = { onClose: () => void };

/** ★ 미측정을 «변화 없음» 과 같은 톤으로 두면 「문제 없음」으로 읽힌다. 구분한다. */
const VERDICT: Record<string, { label: string; cls: string }> = {
  improved: { label: '개선', cls: 'afs-success-fg' },
  regressed: { label: '악화', cls: 'afs-danger-fg' },
  unchanged: { label: '변화 없음', cls: 'afs-muted' },
  unmeasured: { label: '미측정(판정 제외)', cls: 'afs-mega-fg' },
};

const REVIEW: Record<string, { label: string; tone: string }> = {
  pending_review: { label: '검토 대기', tone: 'warn' },
  approved: { label: '승인', tone: 'success' },
  rejected: { label: '반려', tone: 'danger' },
};

/** 숫자 한 칸. **«없음» 은 0 이 아니라 «—»** 다.
 *
 * ⚠️ [2026-08-07 화면 실측] 종전 `String(v)` 는 `0.91 - 0.8` 의 부동소수 잡음을 그대로 찍어
 *   차이 칸에 **`0.10999999999999999`** 가 나왔다. 17자리 숫자는 데이터가 아니라 잡음이고,
 *   그것을 본 사람은 표 전체를 의심한다. 잡음만 걷어내되 **값을 반올림해 숨기지는 않는다** —
 *   유효한 소수는 6자리까지 살린다(지표는 비율·초 단위라 그 아래는 판정에 쓰이지 않는다). */
function fmt(v: number | null | undefined) {
  if (v === null || v === undefined) return '—';
  if (!Number.isFinite(v)) return String(v);
  if (Number.isInteger(v)) return String(v);
  return String(Number(v.toFixed(6)));
}

/** 401/403 은 «없다» 가 아니라 «못 봤다» 다 — 상태를 구분해 담는다. */

export default function ShadowModePanel({ onClose }: Props) {
  const [runs, setRuns] = useState<Loaded<ShadowRun[]>>(loading<ShadowRun[]>());
  const [summary, setSummary] = useState<Loaded<ShadowSummary>>(loading<ShadowSummary>());
  const [selected, setSelected] = useState<ShadowRun | null>(null);
  const [ack, setAck] = useState<Set<string>>(new Set());
  const [scopeText, setScopeText] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  // ⚠️ 승격은 운영 적용이다 — 누르는 즉시 나가지 않게 화면 안에서 한 번 확인한다.
  const confirmPromote = useConfirm<true>();

  const load = useCallback(async () => {
    setErr('');
    setSummary(loading<ShadowSummary>());
    setRuns(loading<ShadowRun[]>());
    // ★ 둘을 **따로** 담는다. 종전에는 한 `err` 변수에 덮어써서 어느 쪽이 실패했는지 사라졌다.
    const [s, r] = await Promise.allSettled([fetchSummary(), fetchRuns()]);
    if (s.status === 'fulfilled') { reportRequestSuccess(); setSummary(ok(s.value)); }
    else { reportRequestFailure((s.reason as any)?.status); setSummary(failed<ShadowSummary>(s.reason)); }
    if (r.status === 'fulfilled') { reportRequestSuccess(); setRuns(ok(r.value)); }
    else { reportRequestFailure((r.reason as any)?.status); setRuns(failed<ShadowRun[]>(r.reason)); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const open = async (run: ShadowRun) => {
    setMsg(''); setErr(''); setAck(new Set()); setScopeText('');
    try {
      // 비교는 조회 시점에 다시 계산한다 — 저장된 결과만 보면 최신 기록이 반영되지 않는다.
      const v = await compareRun(run.run_id);
      setSelected({ ...run, variance: v });
    } catch (e: any) {
      setSelected(run);
      // ⚠️ `String(e)` 를 그대로 찍으면 «Error: ...» 가 사용자에게 나간다.
      setErr(e?.message || '비교 결과를 계산하지 못했습니다.');
    }
  };

  const act = async (fn: () => Promise<ShadowRun>, okMsg: string) => {
    setMsg(''); setErr('');
    try {
      const out = await fn();
      setSelected(out);
      setMsg(okMsg);
      load();
    } catch (e: any) {
      // 백엔드의 거절 사유를 그대로 보여준다 — 여기서 요약하면 무엇을 해야 할지 사라진다.
      setErr(e?.message || '요청이 거절됐습니다.');
    }
  };

  const sm = summary.value;
  const v = selected?.variance;
  const regressed = v?.regressed || [];
  const allAcked = regressed.every((m) => ack.has(m));

  return (
    <HubDialog label="Shadow Mode — 병렬 검증과 제한적 승격" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>Shadow Mode</b>
        <span>승격되지 않은 결과는 운영값이 아닙니다 · 같은 입력이 아니면 비교하지 않습니다(§7.3)</span>
        <div className="bar-actions">
          {(summary.status === 'loading' || runs.status === 'loading')
            && <span className="busy">확인 중…</span>}
          <button className="secondary-button" onClick={load}>새로고침</button>
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <div className="hub-main">
          <ScreenHead kicker="SHADOW" title="병렬 검증 · 제한적 승격"
            description="새 규칙·모델을 실제 데이터에 병렬 적용해 비교하고, 승인된 범위에서만 제한 적용합니다. 미측정 지표는 0이 아니라 판정에서 제외된 것입니다."
            chip={runs.status === 'loading' ? { label: '확인 중', tone: 'muted' }
              : runs.status === 'forbidden' ? { label: '권한 없음', tone: 'danger' }
                : runs.status === 'error' ? { label: '조회 불가', tone: 'danger' }
                  : { label: `run ${(runs.value || []).length}건`, tone: 'data' }} />

          {err && (
            <div style={{ marginBottom: 12 }}>
              <Banner tone="error" title="진행하지 못했습니다">
                <span style={{ whiteSpace: 'pre-wrap' }}>{err}</span>
              </Banner>
            </div>
          )}
          {msg && (
            <div style={{ marginBottom: 12 }}><Banner tone="info">{msg}</Banner></div>
          )}

          <Panel kicker="SUMMARY" title="현황">
            <div className="panel-body">
              {summary.status !== 'ok' ? (
                // ★ 요약을 못 읽었다고 목록까지 죽이지 않는다 — 따로 말한다.
                <EmptyOrError state={summary.status} error={summary.error}
                  emptyText="집계할 run 이 없습니다." onRetry={load} />
              ) : (
                <>
                  <div className="metric-row">
                    <div><span>전체 run</span><b>{sm!.total}</b><small /></div>
                    <div><span>검토 대기</span>
                      <b>{sm!.by_review_status.pending_review || 0}</b><small /></div>
                    <div><span>승격됨</span><b>{sm!.promoted}</b><small>범위 제한</small></div>
                    <div><span>판정 불가</span><b>{sm!.incomparable.length}</b>
                      <small>입력 불일치 — 실패가 아닙니다</small></div>
                  </div>
                  {sm!.note && <p className="afs-muted" style={{ fontSize: 12 }}>{sm!.note}</p>}
                </>
              )}
            </div>
          </Panel>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 320px) 1fr',
            gap: 14, marginTop: 14, alignItems: 'start' }}>
            {/* ── 목록 ─────────────────────────────────────────────────── */}
            <Panel kicker="RUNS" title="Run 목록">
              <div className="panel-body">
                {runs.status !== 'ok' ? (
                  // ★★★ 종전에는 여기가 «등록된 run 이 없습니다» 였다 — 못 본 것을 없는 것으로.
                  <EmptyOrError state={runs.status} error={runs.error}
                    emptyText="등록된 run 이 없습니다." onRetry={load} />
                ) : (runs.value || []).length === 0 ? (
                  <p className="afs-muted" style={{ fontSize: 13 }}>등록된 run 이 없습니다.</p>
                ) : (
                  (runs.value || []).map((r) => (
                    <button key={r.run_id} onClick={() => open(r)}
                      className={`afs-border ${selected?.run_id === r.run_id ? 'afs-action-border' : ''}`}
                      style={{ display: 'block', width: '100%', textAlign: 'left', fontSize: 13,
                        borderWidth: 1, borderStyle: 'solid', borderRadius: 8, padding: '8px 10px',
                        background: selected?.run_id === r.run_id
                          ? 'var(--surface-raised)' : '#fff' }}>
                      <span style={{ display: 'flex', alignItems: 'center',
                        justifyContent: 'space-between', gap: 8 }}>
                        <b style={{ overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap' }}>{r.name}</b>
                        {/* ① 승격 여부를 목록에서부터 구분한다 */}
                        <span className={`state-chip ${r.promoted ? 'success' : 'data'}`}>
                          {r.promoted ? '승격됨' : '섀도우'}
                        </span>
                      </span>
                      <span className="afs-muted"
                        style={{ display: 'block', fontSize: 12, marginTop: 3 }}>
                        {r.candidate_kind} · {r.evaluation_period} ·{' '}
                        {REVIEW[r.review_status]?.label || r.review_status}
                      </span>
                    </button>
                  ))
                )}
              </div>
            </Panel>

            {/* ── 상세 ─────────────────────────────────────────────────── */}
            <Panel kicker="DETAIL" title={selected ? selected.name : '상세'}>
              <div className="panel-body">
                {!selected ? (
                  <p className="afs-muted" style={{ fontSize: 13 }}>
                    왼쪽에서 run 을 선택하십시오.
                  </p>
                ) : (
                  <>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10,
                      justifyContent: 'space-between', flexWrap: 'wrap' }}>
                      <p className="afs-muted" style={{ fontSize: 12 }}>
                        {selected.baseline_ref || '기준선'} → {selected.candidate_ref || '후보'} ·{' '}
                        평가기간 {selected.evaluation_period} · 조직 {selected.enterprise_scope_id}
                      </p>
                      {/* ① 운영값인지 아닌지를 상세에서도 못박는다 */}
                      <span className={`state-chip ${selected.promoted ? 'success' : 'data'}`}>
                        {selected.promoted
                          ? `승격 · ${selected.promotion_scope}` : '섀도우(운영값 아님)'}
                      </span>
                    </div>

                    {/* ③ 비교 불가는 실패가 아니라 판정 불가 */}
                    {v && !v.comparable && (
                      <Banner tone="warn" title={`판정 불가 — ${v.reason || '입력 불일치'}`}>
                        {v.baseline_input_hash && (
                          <div className="afs-muted" style={{ fontSize: 12 }}>
                            기준선 {v.baseline_input_hash} ≠ 후보 {v.candidate_input_hash}
                          </div>
                        )}
                        <div>{v.note}</div>
                      </Banner>
                    )}

                    {v?.comparable && (
                      <>
                        <div className="afs-table-wrap">
                          <table className="afs-table">
                            <thead>
                              <tr>
                                <th>지표</th><th>기준선</th><th>후보</th><th>차이</th><th>판정</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(v.metrics || []).map((m: MetricRow) => (
                                <tr key={m.metric}>
                                  <td style={{ fontFamily: 'monospace' }}>{m.metric}</td>
                                  <td className="num">{fmt(m.baseline)}</td>
                                  <td className="num">{fmt(m.candidate)}</td>
                                  {/* ② 미측정에 차이값을 쓰지 않는다 — 0 으로 보이면 «변화 없음» 이 된다 */}
                                  <td className="num">
                                    {m.verdict === 'unmeasured' ? '—' : fmt(m.delta)}
                                  </td>
                                  <td className={VERDICT[m.verdict]?.cls}>
                                    {VERDICT[m.verdict]?.label}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {/* ② 미측정은 별도 문장으로 — 개선/악화와 섞지 않는다 */}
                        {!!v.unmeasured?.length && (
                          <Banner tone="warn" title="미측정 지표가 있습니다">
                            {v.unmeasured.join(', ')} — <b>0 이 아니라 판정에서 제외</b>됐습니다.
                          </Banner>
                        )}

                        {selected.review_status === 'pending_review' && (
                          <div>
                            <h4 style={{ fontSize: 13, fontWeight: 800 }}>검토 (§7.3 4단계)</h4>
                            {regressed.length > 0 && (
                              <>
                                {/* ④ 백엔드가 거절하는 이유를 미리 보여준다 */}
                                <p className="afs-danger-fg" style={{ fontSize: 13 }}>
                                  악화된 지표를 인정해야 승인할 수 있습니다 — 모르고 승격하는 것과
                                  알고 승격하는 것은 다릅니다.
                                </p>
                                {regressed.map((m) => (
                                  <label key={m} className="afs-ink" style={{ display: 'flex',
                                    alignItems: 'center', gap: 8, fontSize: 13, marginTop: 4 }}>
                                    <input type="checkbox" checked={ack.has(m)}
                                      onChange={(e) => {
                                        const n = new Set(ack);
                                        if (e.target.checked) n.add(m); else n.delete(m);
                                        setAck(n);
                                      }} />
                                    <span style={{ fontFamily: 'monospace' }}>{m}</span>
                                    <span>악화를 감수한다</span>
                                  </label>
                                ))}
                              </>
                            )}
                            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                              <button className="primary-button" disabled={!allAcked}
                                onClick={() => act(() => reviewRun(selected.run_id, {
                                  decision: 'approved',
                                  acknowledged_regressions: [...ack],
                                }), '승인했습니다. 이제 범위를 지정해 승격할 수 있습니다.')}>
                                승인
                              </button>
                              <button className="secondary-button"
                                onClick={() => act(() => reviewRun(selected.run_id,
                                  { decision: 'rejected' }), '반려했습니다.')}>
                                반려
                              </button>
                            </div>
                          </div>
                        )}

                        {selected.review_status === 'approved' && !selected.promoted && (
                          <div>
                            <h4 style={{ fontSize: 13, fontWeight: 800 }}>승격 (§7.3 5단계)</h4>
                            <p className="afs-muted" style={{ fontSize: 13 }}>
                              승인된 <b>범위에서만</b> 제한적으로 운영 적용합니다. 범위를 비우면
                              전면 적용이 되므로 거절됩니다.
                            </p>
                            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                              <input className="afs-input" style={{ flex: 1 }} value={scopeText}
                                onChange={(e) => setScopeText(e.target.value)}
                                placeholder="예: 제1공장 야간조 한정 · 2026-08 까지" />
                              <button className="primary-button"
                                onClick={() => confirmPromote.ask(true)}>승격</button>
                            </div>
                            <ConfirmInline open={confirmPromote.open}
                              title="이 후보를 지금 운영에 적용합니다"
                              body={<>
                                섀도우 결과가 <b>운영값이 됩니다</b> — 적용 범위:{' '}
                                <b>{scopeText || '(비어 있음)'}</b>.
                                {!scopeText && <><br />⚠️ 범위가 비어 있으면 전면 적용이 되므로
                                  서버가 거절합니다.</>}
                                {regressed.length > 0 && <><br />악화로 판정된 지표{' '}
                                  {regressed.join(', ')} 를 감수한 상태입니다.</>}
                              </>}
                              confirmLabel="승격"
                              onCancel={confirmPromote.cancel}
                              onConfirm={() => confirmPromote.run(() => act(
                                () => promoteRun(selected.run_id, scopeText), '승격했습니다.'))} />
                          </div>
                        )}
                      </>
                    )}

                    {selected.review_status !== 'pending_review' && (
                      <p className="afs-muted" style={{ fontSize: 13 }}>
                        검토: {REVIEW[selected.review_status]?.label || selected.review_status}
                        {selected.reviewed_by && ` · ${selected.reviewed_by}`}
                        {!!selected.acknowledged_regressions?.length
                          && ` · 감수한 악화: ${selected.acknowledged_regressions.join(', ')}`}
                      </p>
                    )}
                    {selected.note && (
                      <p className="afs-muted" style={{ fontSize: 12 }}>{selected.note}</p>
                    )}
                  </>
                )}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </HubDialog>
  );
}
