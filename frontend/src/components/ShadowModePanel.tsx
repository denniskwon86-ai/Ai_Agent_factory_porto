// Shadow Mode 화면 (명세서 §7.3 / §7.4 · M2)
//
// ⚠️ 기능 확인용 최소 화면이다. 디자인 확정 후 개편될 것을 전제로 표현을 최소화하고
//   데이터 계층(`lib/shadowApi.ts`)만 재사용 가능하게 두었다.
//
// 이 화면이 반드시 지켜야 하는 것 — 백엔드가 막는 것과 같은 것을 화면도 흐리지 않는다:
//   ① 승격 전 결과를 운영값처럼 보여주지 않는다 (배지로 항상 구분)
//   ② `unmeasured` 를 개선/악화와 같은 칸에 넣지 않는다 (0 이 아니라 판정 제외다)
//   ③ 비교 불가는 실패가 아니라 **판정 불가**로 표시한다 (입력을 맞춰 다시 돌려야 한다)
//   ④ 악화 항목은 체크해서 인정해야 승인 버튼이 동작한다 (백엔드가 거절하는 이유를 미리 보여준다)
import { useCallback, useEffect, useState } from 'react';
import type { MetricRow, ShadowRun, ShadowSummary } from '../lib/shadowApi';
import {
  compareRun, fetchRuns, fetchSummary, promoteRun, reviewRun,
} from '../lib/shadowApi';

type Props = { onClose: () => void };

const VERDICT: Record<string, { label: string; cls: string }> = {
  improved: { label: '개선', cls: 'text-emerald-400' },
  regressed: { label: '악화', cls: 'text-red-400' },
  unchanged: { label: '변화 없음', cls: 'text-slate-400' },
  // ★ 미측정을 회색 '변화 없음'과 같은 톤으로 두면 "문제 없음"으로 읽힌다. 구분한다.
  unmeasured: { label: '미측정(판정 제외)', cls: 'text-violet-300' },
};

const REVIEW: Record<string, { label: string; cls: string }> = {
  pending_review: { label: '검토 대기', cls: 'text-amber-300' },
  approved: { label: '승인', cls: 'text-emerald-400' },
  rejected: { label: '반려', cls: 'text-red-400' },
};

function fmt(v: number | null | undefined) {
  return v === null || v === undefined ? '—' : String(v);
}

export default function ShadowModePanel({ onClose }: Props) {
  const [runs, setRuns] = useState<ShadowRun[]>([]);
  const [summary, setSummary] = useState<ShadowSummary | null>(null);
  const [selected, setSelected] = useState<ShadowRun | null>(null);
  const [ack, setAck] = useState<Set<string>>(new Set());
  const [scopeText, setScopeText] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setErr('');
    const [s, r] = await Promise.allSettled([fetchSummary(), fetchRuns()]);
    if (s.status === 'fulfilled') setSummary(s.value); else setErr('요약을 불러오지 못했습니다.');
    if (r.status === 'fulfilled') setRuns(r.value); else setErr('목록을 불러오지 못했습니다.');
  }, []);

  useEffect(() => { load(); }, [load]);

  const open = async (run: ShadowRun) => {
    setMsg(''); setErr(''); setAck(new Set()); setScopeText('');
    try {
      // 비교는 조회 시점에 다시 계산한다 — 저장된 결과만 보면 최신 기록이 반영되지 않는다.
      const v = await compareRun(run.run_id);
      setSelected({ ...run, variance: v });
    } catch (e) {
      setSelected(run);
      setErr(String(e));
    }
  };

  const act = async (fn: () => Promise<ShadowRun>, ok: string) => {
    setMsg(''); setErr('');
    try {
      const out = await fn();
      setSelected(out);
      setMsg(ok);
      load();
    } catch (e) {
      // 백엔드의 거절 사유를 그대로 보여준다 — 여기서 요약하면 무엇을 해야 할지 사라진다.
      setErr(String(e).replace(/^Error:\s*/, ''));
    }
  };

  const v = selected?.variance;
  const regressed = v?.regressed || [];
  const allAcked = regressed.every((m) => ack.has(m));

  return (
    <div className="fixed inset-0 z-50 bg-slate-950 text-slate-200 overflow-y-auto">
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <header className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">Shadow Mode — 병렬 검증 · 제한적 승격</h2>
            <p className="text-[11px] text-slate-400">
              승격되지 않은 결과는 <span className="text-violet-300">운영값이 아닙니다</span>.
              같은 입력이 아니면 비교하지 않습니다(§7.3).
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={load} className="px-3 py-1 text-xs bg-slate-700 rounded">새로고침</button>
            <button onClick={onClose} className="px-3 py-1 text-xs bg-slate-600 rounded">닫기</button>
          </div>
        </header>

        {summary && (
          <div className="border border-slate-700 rounded-lg p-4 bg-slate-900/60 flex gap-6 flex-wrap">
            <div><div className="text-2xl font-semibold">{summary.total}</div>
              <div className="text-[11px] text-slate-400">전체 run</div></div>
            <div><div className="text-2xl font-semibold text-amber-300">
              {summary.by_review_status.pending_review || 0}</div>
              <div className="text-[11px] text-slate-400">검토 대기</div></div>
            <div><div className="text-2xl font-semibold text-emerald-400">{summary.promoted}</div>
              <div className="text-[11px] text-slate-400">승격됨(범위 제한)</div></div>
            <div><div className="text-2xl font-semibold text-violet-300">
              {summary.incomparable.length}</div>
              <div className="text-[11px] text-slate-400">판정 불가(입력 불일치)</div></div>
            <p className="text-[11px] text-slate-500 basis-full">{summary.note}</p>
          </div>
        )}

        {err && <div className="border border-red-500/40 bg-red-500/10 text-red-200 text-xs
                                rounded px-3 py-2 whitespace-pre-wrap">{err}</div>}
        {msg && <div className="border border-emerald-500/40 bg-emerald-500/10 text-emerald-200
                                text-xs rounded px-3 py-2">{msg}</div>}

        <div className="grid md:grid-cols-[320px_1fr] gap-4">
          {/* 목록 */}
          <section className="border border-slate-700 rounded-lg p-3 bg-slate-900/60">
            <h3 className="text-sm font-semibold mb-2">Run 목록</h3>
            {runs.length === 0 && <p className="text-xs text-slate-500">등록된 run 이 없습니다.</p>}
            <ul className="space-y-1.5">
              {runs.map((r) => (
                <li key={r.run_id}>
                  <button
                    onClick={() => open(r)}
                    className={`w-full text-left text-xs border rounded px-2 py-1.5
                      ${selected?.run_id === r.run_id
                        ? 'border-indigo-500 bg-indigo-500/10' : 'border-slate-700'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">{r.name}</span>
                      {/* ① 승격 여부를 목록에서부터 구분한다 */}
                      {r.promoted
                        ? <span className="text-[10px] text-emerald-400 shrink-0">승격됨</span>
                        : <span className="text-[10px] text-violet-300 shrink-0">섀도우</span>}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      {r.candidate_kind} · {r.evaluation_period} ·{' '}
                      <span className={REVIEW[r.review_status]?.cls}>
                        {REVIEW[r.review_status]?.label}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {/* 상세 */}
          <section className="border border-slate-700 rounded-lg p-4 bg-slate-900/60">
            {!selected && <p className="text-xs text-slate-500">왼쪽에서 run 을 선택하십시오.</p>}
            {selected && (
              <>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <h3 className="text-sm font-semibold">{selected.name}</h3>
                    <p className="text-[11px] text-slate-400">
                      {selected.baseline_ref || '기준선'} → {selected.candidate_ref || '후보'} ·{' '}
                      평가기간 {selected.evaluation_period} · 조직 {selected.enterprise_scope_id}
                    </p>
                  </div>
                  <span className={`text-[11px] px-2 py-1 rounded border ${selected.promoted
                    ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
                    : 'text-violet-300 border-violet-500/40 bg-violet-500/10'}`}>
                    {selected.promoted ? `승격 · ${selected.promotion_scope}` : '섀도우(운영값 아님)'}
                  </span>
                </div>

                {/* ③ 비교 불가는 실패가 아니라 판정 불가 */}
                {v && !v.comparable && (
                  <div className="mt-3 border border-violet-500/40 bg-violet-500/10 rounded
                                  px-3 py-2 text-xs">
                    <div className="font-medium text-violet-200">판정 불가 — {v.reason}</div>
                    {v.baseline_input_hash && (
                      <div className="text-slate-400 mt-1">
                        기준선 {v.baseline_input_hash} ≠ 후보 {v.candidate_input_hash}
                      </div>
                    )}
                    <div className="text-slate-300 mt-1">{v.note}</div>
                  </div>
                )}

                {v?.comparable && (
                  <>
                    <table className="w-full text-xs mt-3">
                      <thead className="text-slate-400">
                        <tr className="text-left">
                          <th className="py-1">지표</th><th>기준선</th><th>후보</th>
                          <th>차이</th><th>판정</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(v.metrics || []).map((m: MetricRow) => (
                          <tr key={m.metric} className="border-t border-slate-800">
                            <td className="py-1 font-mono">{m.metric}</td>
                            <td>{fmt(m.baseline)}</td>
                            <td>{fmt(m.candidate)}</td>
                            <td>{m.verdict === 'unmeasured' ? '—' : fmt(m.delta)}</td>
                            <td className={VERDICT[m.verdict]?.cls}>
                              {VERDICT[m.verdict]?.label}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {/* ② 미측정은 별도 문장으로 — 개선/악화와 섞지 않는다 */}
                    {!!v.unmeasured?.length && (
                      <p className="text-[11px] text-violet-300 mt-2">
                        미측정 {v.unmeasured.join(', ')} — 0 이 아니라 판정에서 제외됐습니다.
                      </p>
                    )}

                    {selected.review_status === 'pending_review' && (
                      <div className="mt-4 border-t border-slate-700 pt-3">
                        <h4 className="text-xs font-semibold">검토 (§7.3 4단계)</h4>
                        {regressed.length > 0 && (
                          <div className="mt-2">
                            {/* ④ 백엔드가 거절하는 이유를 미리 보여준다 */}
                            <p className="text-[11px] text-red-300">
                              악화된 지표를 인정해야 승인할 수 있습니다 — 모르고 승격하는 것과
                              알고 승격하는 것은 다릅니다.
                            </p>
                            {regressed.map((m) => (
                              <label key={m} className="flex items-center gap-2 text-xs mt-1">
                                <input type="checkbox" checked={ack.has(m)}
                                  onChange={(e) => {
                                    const n = new Set(ack);
                                    e.target.checked ? n.add(m) : n.delete(m);
                                    setAck(n);
                                  }} />
                                <span className="font-mono">{m}</span> 악화를 감수한다
                              </label>
                            ))}
                          </div>
                        )}
                        <div className="flex gap-2 mt-3">
                          <button
                            disabled={!allAcked}
                            onClick={() => act(() => reviewRun(selected.run_id, {
                              decision: 'approved',
                              acknowledged_regressions: [...ack],
                            }), '승인했습니다. 이제 범위를 지정해 승격할 수 있습니다.')}
                            className={`px-3 py-1 text-xs rounded ${allAcked
                              ? 'bg-emerald-700 hover:bg-emerald-600'
                              : 'bg-slate-700 opacity-50 cursor-not-allowed'}`}>
                            승인
                          </button>
                          <button
                            onClick={() => act(() => reviewRun(selected.run_id,
                              { decision: 'rejected' }), '반려했습니다.')}
                            className="px-3 py-1 text-xs bg-slate-700 rounded">반려</button>
                        </div>
                      </div>
                    )}

                    {selected.review_status === 'approved' && !selected.promoted && (
                      <div className="mt-4 border-t border-slate-700 pt-3">
                        <h4 className="text-xs font-semibold">승격 (§7.3 5단계)</h4>
                        <p className="text-[11px] text-slate-400 mt-1">
                          승인된 <b>범위에서만</b> 제한적으로 운영 적용합니다. 범위를 비우면
                          전면 적용이 되므로 거절됩니다.
                        </p>
                        <div className="flex gap-2 mt-2">
                          <input
                            value={scopeText}
                            onChange={(e) => setScopeText(e.target.value)}
                            placeholder="예: 제1공장 야간조 한정 · 2026-08 까지"
                            className="flex-1 bg-slate-800 border border-slate-600 rounded
                                       px-2 py-1 text-xs" />
                          <button
                            onClick={() => act(() => promoteRun(selected.run_id, scopeText),
                                               '승격했습니다.')}
                            className="px-3 py-1 text-xs bg-indigo-700 hover:bg-indigo-600 rounded">
                            승격
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {selected.review_status !== 'pending_review' && (
                  <p className="text-[11px] text-slate-400 mt-3">
                    검토: <span className={REVIEW[selected.review_status]?.cls}>
                      {REVIEW[selected.review_status]?.label}
                    </span>
                    {selected.reviewed_by && ` · ${selected.reviewed_by}`}
                    {!!selected.acknowledged_regressions?.length &&
                      ` · 감수한 악화: ${selected.acknowledged_regressions.join(', ')}`}
                  </p>
                )}
                <p className="text-[11px] text-slate-500 mt-2">{selected.note}</p>
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
