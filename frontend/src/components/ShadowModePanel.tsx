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
import { EmptyOrError, Refreshing, failed, loading, ok, refreshing, type Loaded } from '../design/DataState';
import { useLatestOnly } from '../design/useLatestOnly';
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import type { MetricRow, ShadowRun, ShadowSummary } from '../lib/shadowApi';
import {
  compareRun, fetchRuns, fetchSummary, promoteRun, reviewRun,
} from '../lib/shadowApi';

type Props = { onClose: () => void; page?: boolean };

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

export default function ShadowModePanel({ onClose, page = false }: Props) {
  //: [설계 §6.1] 늦게 온 응답을 버리는 표 — 다른 것을 고른 뒤 옛 응답이 그려지지 않게.
  const claim = useLatestOnly();

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
    // ★ [설계 §6.2] 재조회는 **값을 비우지 않는다** — 행동 뒤 목록이 사라졌다
    //   돌아오면 방금 무엇이 바뀌었는지 비교할 수 없고 스크롤 위치도 잃는다.
    setSummary(refreshing); setRuns(refreshing);
    // ★ 둘을 **따로** 담는다. 종전에는 한 `err` 변수에 덮어써서 어느 쪽이 실패했는지 사라졌다.
    const [s, r] = await Promise.allSettled([fetchSummary(), fetchRuns()]);
    if (s.status === 'fulfilled') { reportRequestSuccess(); setSummary(ok(s.value)); }
    else { reportRequestFailure((s.reason as any)?.status); setSummary(failed<ShadowSummary>(s.reason)); }
    if (r.status === 'fulfilled') { reportRequestSuccess(); setRuns(ok(r.value)); }
    else { reportRequestFailure((r.reason as any)?.status); setRuns(failed<ShadowRun[]>(r.reason)); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const open = async (run: ShadowRun) => {
    const isCurrent = claim();   // §6.1 — 요청 직전에 표를 뽑는다
    setMsg(''); setErr(''); setAck(new Set()); setScopeText('');
    try {
      // 비교는 조회 시점에 다시 계산한다 — 저장된 결과만 보면 최신 기록이 반영되지 않는다.
      const v = await compareRun(run.run_id);
      // ★★ [§6.1] 실행을 빠르게 두 번 고르면 앞의 비교가 뒤에 도착할 수 있다. 그러면 제목은
      //   새 실행인데 **개선·악화 판정은 옛 실행의 것**이 된다 — 그 판정으로 승격한다.
      if (!isCurrent()) return;
      setSelected({ ...run, variance: v });
    } catch (e: any) {
      if (!isCurrent()) return;
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
    <HubDialog label="Shadow Mode — 병렬 검증과 제한적 승격" onClose={onClose} page={page}>
      {!page && <div className="afs-dialog-bar">
        <b>Shadow Mode</b>
        <span>승격되지 않은 결과는 운영값이 아닙니다 · 같은 입력이 아니면 비교하지 않습니다(§7.3)</span>
        <div className="bar-actions">
          {(summary.status === 'loading' || runs.status === 'loading')
            && <span className="busy">확인 중…</span>}
          <Refreshing on={summary.refreshing || runs.refreshing} />
          <button className="secondary-button" onClick={load}>새로고침</button>
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>}

      <div className="afs-dialog-body">
        <div className="hub-main">
          <ScreenHead kicker="SHADOW" title="병렬 검증 · 제한적 승격"
            description="새 규칙·모델을 실제 데이터에 병렬 적용해 비교하고, 승인된 범위에서만 제한 적용합니다. 미측정 지표는 0이 아니라 판정에서 제외된 것입니다."
            chip={runs.status === 'loading' ? { label: '확인 중', tone: 'muted' }
              : runs.status === 'forbidden' ? { label: '권한 없음', tone: 'danger' }
                : runs.status === 'error' ? { label: '조회 불가', tone: 'danger' }
                  : { label: `비교 ${(runs.value || []).length}건`, tone: 'data' }} />

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
                  emptyText="아직 비교해 본 것이 없습니다." onRetry={load} />
              ) : (
                <>
                  <div className="metric-row">
                    {/* ⚠️⚠️ [2026-08-24 사용자 지적] `run`·`판정 불가`·`입력 불일치` 는
                        전부 우리 안에서만 쓰는 말이다. 업무 낱말로 바꾼다. */}
                    <div><span>비교해 본 것</span><b>{sm!.total}</b><small /></div>
                    <div><span>검토 대기</span>
                      <b>{sm!.by_review_status.pending_review || 0}</b>
                      <small>사람이 아직 안 봄</small></div>
                    <div><span>채택됨</span><b>{sm!.promoted}</b>
                      <small>정해진 범위에서만</small></div>
                    <div><span>견줄 수 없었음</span><b>{sm!.incomparable.length}</b>
                      <small>서로 다른 자료로 돌았음 — 실패가 아닙니다</small></div>
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
                    emptyText="아직 비교해 본 것이 없습니다." onRetry={load} />
                ) : (runs.value || []).length === 0 ? (
                  <p className="afs-muted" style={{ fontSize: 13 }}>
                    아직 비교해 본 것이 없습니다 — 새 규칙·모델을 지금 것과 나란히 돌리면
                    여기에 결과가 쌓입니다.
                  </p>
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

                    {/* ③ 견줄 수 없는 것은 «실패» 가 아니다 — 판단할 근거가 없는 것이다.
                        ⚠️ 해시 두 개를 나란히 보여 주던 자리를 없앴다. 사용자는 그 값으로
                          할 수 있는 일이 없고, 「≠」 하나만 남아 겁만 준다. */}
                    {v && !v.comparable && (
                      <Banner tone="warn" title="이번 비교는 결과를 쓸 수 없습니다">
                        <div>
                          새 방식과 지금 방식이 <b>서로 다른 자료</b>로 돌아서 나란히 놓고
                          견줄 수가 없습니다. 새 방식이 틀렸다는 뜻이 아니라, 아직 좋고
                          나쁨을 말할 근거가 없다는 뜻입니다.
                        </div>
                        <div style={{ marginTop: 6 }}>
                          <b>다음 할 일</b> — 두 방식이 같은 자료를 보도록 맞춘 뒤 다시
                          돌리십시오.
                        </div>
                        {v.reason && (
                          <div className="afs-muted" style={{ fontSize: 12, marginTop: 6 }}>
                            확인된 차이: {v.reason}
                          </div>
                        )}
                        {v.note && <div style={{ marginTop: 6 }}>{v.note}</div>}
                      </Banner>
                    )}

                    {v?.comparable && (
                      <>
                        <div className="afs-table-wrap">
                          <table className="afs-table">
                            {/* ★ [설계 §5.4 `/operate/shadow/:runId`] 「**좌 baseline, 우
                                candidate, 중앙 delta**」 — 차이를 두 값 **사이**에 둔다.
                                끝에 두면 「얼마나 바뀌었나」를 읽으려고 시선이 표를 가로질러
                                왕복하고, 그러다 기준선과 후보를 헷갈린다. */}
                            <thead>
                              <tr>
                                <th>지표</th><th>기준선</th><th>차이</th><th>후보</th><th>판정</th>
                                {regressed.length > 0 && selected.review_status === 'pending_review'
                                  && <th>악화 인지</th>}
                              </tr>
                            </thead>
                            <tbody>
                              {(v.metrics || []).map((m: MetricRow) => (
                                <tr key={m.metric}>
                                  <td style={{ fontFamily: 'monospace' }}>{m.metric}</td>
                                  <td className="num">{fmt(m.baseline)}</td>
                                  {/* ② 미측정에 차이값을 쓰지 않는다 — 0 으로 보이면 «변화 없음» 이 된다 */}
                                  <td className="num">
                                    {m.verdict === 'unmeasured' ? '—' : fmt(m.delta)}
                                  </td>
                                  <td className="num">{fmt(m.candidate)}</td>
                                  <td className={VERDICT[m.verdict]?.cls}>
                                    {VERDICT[m.verdict]?.label}
                                  </td>
                                  {/* ★★ [설계 §5.4] 「악화 항목 인지 체크는 **지표와 같은 행**」.
                                      ⚠️ 이전에는 표 아래에 지표 이름만 늘어놓은 체크박스가
                                        따로 있었다. 그러면 «무엇이 얼마나 나빠졌는지» 를 보지
                                        않고 이름만 보고 체크한다 — 인지 체크의 목적이 정확히
                                        그 반대다. 숫자 옆에서 체크하게 한다. */}
                                  {regressed.length > 0 && selected.review_status === 'pending_review' && (
                                    <td>
                                      {m.verdict === 'regressed' ? (
                                        <label style={{ display: 'flex', alignItems: 'center',
                                          gap: 6, fontSize: 13 }}>
                                          <input type="checkbox" checked={ack.has(m.metric)}
                                            onChange={(e) => {
                                              const n = new Set(ack);
                                              if (e.target.checked) n.add(m.metric);
                                              else n.delete(m.metric);
                                              setAck(n);
                                            }} />
                                          <span>감수한다</span>
                                        </label>
                                      ) : <span className="afs-muted">—</span>}
                                    </td>
                                  )}
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
                              // ④ 백엔드가 거절하는 이유를 미리 보여준다.
                              //   체크박스 자체는 **위 비교표의 해당 행**에 있다(설계 §5.4).
                              <p className="afs-danger-fg" style={{ fontSize: 13 }}>
                                악화 {regressed.length}건을 인정해야 승인할 수 있습니다
                                (인정 {ack.size}건) — 위 비교표에서 해당 지표의 «감수한다» 를
                                체크하십시오. 모르고 승격하는 것과 알고 승격하는 것은 다릅니다.
                              </p>
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
                            {/* ★ [설계 §6.5] Shadow 승격은 확인 Sheet 대상으로 명시된 행동이다. */}
                            <ConfirmInline open={confirmPromote.open}
                              title="이 후보를 지금 운영에 적용합니다"
                              changes={<>섀도우 결과가 <b>운영값이 됩니다.</b> 지금까지는 비교용
                                숫자였고, 적용 후에는 실제 업무가 이 값으로 돌아갑니다.</>}
                              affects={<>적용 범위: <b>{scopeText || '(비어 있음)'}</b>.
                                {!scopeText && <> ⚠️ 범위가 비어 있으면 전면 적용이 되므로 서버가
                                  거절합니다.</>}
                                {v?.unmeasured?.length ? <> 미측정 지표 {v.unmeasured.length}개는
                                  판정에서 제외됐습니다 — 그 축의 영향은 알 수 없습니다.</> : null}</>}
                              reversible={<>범위를 되돌리면 적용은 멈추지만, 그 사이 이 값으로
                                내려간 판단과 산출물은 남습니다.</>}
                              approval={regressed.length > 0
                                ? <>악화 지표 {regressed.join(', ')} 를 <b>감수한 상태</b>입니다
                                  (인정 {ack.size}/{regressed.length}건).</>
                                : '악화로 판정된 지표가 없습니다.'}
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
