import { useEffect, useState } from 'react';
import {
  compareScenarios, fetchAccounts, fetchBacktestPlan, fetchCashFlow,
  fetchCurrentApproved, fetchRollupCheck, fetchScenarios, fetchVariance,
  type Account, type Backtest, type CashFlow, type Integrity, type RollupCheck,
  type Scenario, type ScenarioComparison, type Submission, type Variance,
} from '../lib/planningApi';

// [M4] 경영계획 화면 (명세서 §11 / §17 첫 파일럿)
//
// ⚠️ 이 화면이 지켜야 할 단 하나: **결손을 결과처럼 보여주지 않는다.**
//   - `comparable=false`(실적 미입력) 를 "차이 0" 으로 그리면 "계획대로 됐다"로 읽힌다.
//   - `same_baseline=false` 인 비교는 **무효**인데, 숫자만 나란히 놓으면 유효해 보인다.
//   - `unmapped`(미등록 계정)·`unapplied_assumptions`(미적용 가정)은 합계가 맞아 보이는데
//     틀렸다는 유일한 단서다. 접어두거나 작게 쓰지 않는다.
//
// 디자인 시안 확정 시 교체 대상(§7 역할 규약) — 데이터는 lib/planningApi.ts 에 분리했다.

const _n = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 0 });

export function PlanningPanel({ onClose }: { onClose: () => void }) {
  const [orgId, setOrgId] = useState('MNM_BATTERY');
  const [period, setPeriod] = useState('2027');
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [cmp, setCmp] = useState<ScenarioComparison | null>(null);
  const [vr, setVr] = useState<Variance | null>(null);
  const [cf, setCf] = useState<CashFlow | null>(null);
  const [bt, setBt] = useState<Backtest | null>(null);
  const [roll, setRoll] = useState<RollupCheck | null>(null);
  const [appr, setAppr] = useState<(Submission & { integrity: Integrity }) | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // 한 쪽이 실패해도 나머지는 보여준다 — 화면이 통째로 비면 아무것도 못 본다.
    Promise.allSettled([fetchAccounts(), fetchScenarios(orgId)]).then(([a, s]) => {
      setAccounts(a.status === 'fulfilled' ? a.value : []);
      setScenarios(s.status === 'fulfilled' ? s.value : []);
    });
  }, [orgId]);

  const load = async () => {
    setBusy(true);
    setErr('');
    // ★ [2026-07-30 실측으로 발견] 계정·시나리오 목록도 **함께 다시 읽는다.**
    //   종전에는 `useEffect([orgId])` 로만 읽어서, 다른 화면·API 로 시나리오를 만든 뒤
    //   「계산」을 눌러도 목록이 갱신되지 않았다. 화면은 "등록된 시나리오가 없습니다" 라고
    //   말하는데 실제로는 3건이 있었다 — 조용한 거짓말이다.
    //   「계산」은 "지금 상태를 다시 읽는다"는 뜻이어야 한다.
    Promise.allSettled([fetchAccounts(), fetchScenarios(orgId)]).then(([a, s]) => {
      if (a.status === 'fulfilled') setAccounts(a.value);
      if (s.status === 'fulfilled') setScenarios(s.value);
    });
    // 한 쪽이 실패해도 나머지는 보여준다 — 화면이 통째로 비면 아무것도 못 본다.
    const [c, v, cfR, btR, rollR, apprR] = await Promise.allSettled([
      picked.length ? compareScenarios(picked, orgId, period) : Promise.resolve(null as any),
      fetchVariance(orgId, period),
      fetchCashFlow(orgId, period),
      fetchBacktestPlan(orgId, period),
      fetchRollupCheck(orgId, period),
      fetchCurrentApproved(orgId, period),
    ]);
    setCmp(c.status === 'fulfilled' ? c.value : null);
    setVr(v.status === 'fulfilled' ? v.value : null);
    setCf(cfR.status === 'fulfilled' ? cfR.value : null);
    setBt(btR.status === 'fulfilled' ? btR.value : null);
    setRoll(rollR.status === 'fulfilled' ? rollR.value : null);
    setAppr(apprR.status === 'fulfilled' ? apprR.value : null);
    if (c.status === 'rejected') setErr(String((c.reason as Error)?.message || c.reason));
    else if (v.status === 'rejected') setErr(String((v.reason as Error)?.message || v.reason));
    setBusy(false);
  };

  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <div className="fixed inset-0 z-50 bg-slate-950 text-slate-200 overflow-y-auto">
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <header className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">경영계획 · 실적 · 시나리오</h2>
            <p className="text-[11px] text-slate-400">
              계산은 결정론적입니다(LLM 0콜). 같은 입력이면 같은 결과가 나옵니다.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input value={orgId} onChange={(e) => setOrgId(e.target.value)}
                   placeholder="조직 코드"
                   className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs w-40" />
            <input value={period} onChange={(e) => setPeriod(e.target.value)}
                   placeholder="기간(2027 / 2027-03)"
                   className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs w-32" />
            <button onClick={load} disabled={busy}
                    className="px-3 py-1 text-xs bg-blue-600 rounded disabled:opacity-50">
              {busy ? '계산 중…' : '계산'}
            </button>
            <button onClick={onClose} className="px-3 py-1 text-xs bg-slate-600 rounded">닫기</button>
          </div>
        </header>

        {err && (
          <div className="border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs
                          rounded px-3 py-2">{err}</div>
        )}

        {/* ★★ 데이터 신뢰 경고 — 숫자보다 **위**에 온다.
            아래에 작게 쓰면 아무도 안 보고, 그러면 없는 것과 같다. */}
        {(roll?.has_conflict || (appr && appr.integrity?.intact === false)) && (
          <section className="border border-red-500/60 bg-red-500/10 rounded p-4 space-y-2">
            <h3 className="text-sm font-bold text-red-200">⚠️ 이 숫자를 그대로 쓰면 안 됩니다</h3>

            {appr && appr.integrity?.intact === false && (
              <div className="text-xs text-red-200">
                <b>승인 후 값이 변경되었습니다.</b> 상태는 <code>APPROVED</code>({appr.approved_by},
                {' '}{appr.approved_at?.slice(0, 10)})이지만 승인받은 내용과 다릅니다 — 재승인이 필요합니다.
                <div className="text-[10px] text-red-300/80 mt-1 font-mono">
                  승인 시점 {appr.integrity.approved_fingerprint} → 현재 {appr.integrity.current_fingerprint}
                </div>
              </div>
            )}

            {roll?.has_conflict && roll.conflicts.map((c) => (
              <div key={`${c.account_code}-${c.period}`} className="text-xs text-red-200">
                <b>이중 계상 위험</b> — {c.account_code}/{c.period}: 합계 행 {_n(c.total_row_amount)} 과
                {' '}상세 {c.detail_rows}건(합 {_n(c.detail_sum)})이 함께 있습니다.
                {' '}단순 합산하면 <b>{_n(c.naive_sum)}</b> 이 됩니다.
                {!c.matches && <span className="text-red-300"> (합계와 상세가 일치하지도 않습니다)</span>}
              </div>
            ))}
            {roll?.has_conflict && (
              <p className="text-[10px] text-red-300/70">{roll.note}</p>
            )}
          </section>
        )}

        {/* 승인 상태 */}
        {appr && appr.integrity?.intact !== false && (
          <section className="border border-slate-700 rounded p-4">
            <h3 className="text-sm font-bold text-slate-200 mb-1">승인 상태</h3>
            <p className="text-xs text-emerald-300">
              ✅ {appr.approved_by} 승인 ({appr.approved_at?.slice(0, 10)}) ·
              {' '}승인 시점 값과 동일합니다
              <span className="text-slate-500 font-mono"> [{appr.integrity.approved_fingerprint}]</span>
            </p>
          </section>
        )}

        {/* 시나리오 선택 */}
        <section className="border border-slate-700 rounded p-4">
          <h3 className="text-sm font-bold text-slate-200 mb-2">
            시나리오 선택
            <span className="text-slate-500 font-normal"> — 동일 기준선에서 비교합니다(§17.3)</span>
          </h3>
          {scenarios.length === 0 ? (
            <p className="text-xs text-slate-500">등록된 시나리오가 없습니다.</p>
          ) : (
            <div className="flex gap-2 flex-wrap">
              {scenarios.map((s) => (
                <button key={s.scenario_id} onClick={() => toggle(s.scenario_id)}
                        className={`px-3 py-1 text-xs rounded border ${
                          picked.includes(s.scenario_id)
                            ? 'bg-blue-600 border-blue-500 text-white'
                            : 'bg-slate-800 border-slate-600 text-slate-300'}`}>
                  {s.name} <span className="opacity-60">({s.scenario_id})</span>
                </button>
              ))}
            </div>
          )}
          <p className="text-[10px] text-slate-500 mt-2">계정 {accounts.length}개 등록됨</p>
        </section>

        {/* 시나리오 비교 */}
        {cmp && (
          <section className="border border-slate-700 rounded p-4">
            <h3 className="text-sm font-bold text-emerald-300 mb-2">시나리오 비교</h3>

            {/* ★ 기준선이 다르면 그 비교는 무효다 — 숫자보다 먼저 말한다 */}
            {!cmp.same_baseline && (
              <div className="mb-3 border border-red-500/50 bg-red-500/10 text-red-200 text-xs
                              rounded px-3 py-2">
                ⚠️ <b>서로 다른 기준선에서 계산되었습니다 — 이 비교는 무효입니다.</b>
                {' '}같은 기준선으로 다시 실행하십시오.
              </div>
            )}

            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 border-b border-slate-700 text-left">
                  <th className="py-1.5">시나리오</th><th>영업이익</th><th>당기순이익</th>
                  <th>기준선 대비</th><th>입력 지문</th><th>경고</th>
                </tr>
              </thead>
              <tbody>
                {cmp.scenarios.map((s) => (
                  <tr key={s.scenario_id} className="border-b border-slate-800">
                    <td className="py-1.5 text-slate-300">{s.scenario_id}</td>
                    <td>{_n(s.operating_profit)}</td>
                    <td className="font-semibold">{_n(s.net_profit)}</td>
                    <td className={s.delta_net >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                      {s.delta_net >= 0 ? '+' : ''}{_n(s.delta_net)}
                    </td>
                    {/* 재현성의 근거 — 같은 지문이면 같은 입력이다 */}
                    <td className="font-mono text-[10px] text-slate-500">{s.input_hash}</td>
                    <td className="text-[10px]">
                      {!s.complete && <span className="text-amber-400">미등록 계정 있음 </span>}
                      {s.unapplied_assumptions.length > 0 && (
                        <span className="text-amber-400">
                          미적용 가정 {s.unapplied_assumptions.length}
                        </span>
                      )}
                      {s.complete && s.unapplied_assumptions.length === 0 && (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-[10px] text-slate-500 mt-2">
              엔진 {cmp.engine_version} · 기준선 {cmp.baseline_kind} ·
              같은 지문 = 같은 입력. 「미적용 가정」이 있으면 의도한 가정이 전부 반영되지 않았습니다.
            </p>
          </section>
        )}

        {/* 계획 대비 실적 */}
        {vr && (
          <section className="border border-slate-700 rounded p-4">
            <h3 className="text-sm font-bold text-slate-200 mb-2">계획 대비 실적 (차이 분석)</h3>

            {/* ★★ 실적 미입력을 "차이 0" 으로 그리면 "계획대로 됐다"로 읽힌다 */}
            {!vr.comparable ? (
              <div className="border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs
                              rounded px-3 py-2">
                <b>차이를 계산하지 않았습니다</b> — {vr.reason}.
                <div className="text-amber-300/80 mt-1">{vr.note}</div>
              </div>
            ) : (
              <>
                <div className="flex gap-6 flex-wrap mb-3">
                  <div><span className="text-[11px] text-slate-400">계획 영업이익</span>
                    <div className="text-lg">{_n(vr.plan?.operating_profit)}</div></div>
                  <div><span className="text-[11px] text-slate-400">실적 영업이익</span>
                    <div className="text-lg">{_n(vr.actual?.operating_profit)}</div></div>
                  <div><span className="text-[11px] text-slate-400">차이</span>
                    <div className={`text-lg font-bold ${
                      (vr.diff?.operating_profit ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {_n(vr.diff?.operating_profit)}
                    </div></div>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-700 text-left">
                      <th className="py-1.5">계정</th><th>계획</th><th>실적</th><th>차이</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(vr.by_account || []).map((r) => (
                      <tr key={r.account_code} className="border-b border-slate-800">
                        <td className="py-1.5 text-slate-300">{r.account_code}</td>
                        <td>{_n(r.plan)}</td>
                        <td>{_n(r.actual)}</td>
                        {/* 없는 값은 0 이 아니라 '미입력' 이다 */}
                        <td className={r.diff === null ? 'text-amber-400 text-xs' : ''}>
                          {r.diff === null
                            ? (r.missing === 'actual' ? '실적 미입력' : '계획 없음')
                            : _n(r.diff)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>
        )}

        {/* 현금흐름 — 계산 못 한 것을 0 으로 그리지 않는다 */}
        {cf && (
          <section className="border border-slate-700 rounded p-4">
            <h3 className="text-sm font-bold text-slate-200 mb-2">현금흐름 (간접법)</h3>
            {!cf.computable ? (
              <div className="border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs
                              rounded px-3 py-2">
                <b>계산하지 않았습니다</b> — 필요한 항목이 없습니다:
                {' '}<code>{(cf.missing || []).join(', ')}</code>
                <div className="text-amber-300/80 mt-1">{cf.note}</div>
              </div>
            ) : (
              <div className="flex gap-6 flex-wrap">
                <div><span className="text-[11px] text-slate-400">영업</span>
                  <div className="text-lg">{_n(cf.operating_cf)}</div></div>
                <div><span className="text-[11px] text-slate-400">투자</span>
                  <div className="text-lg">{_n(cf.investing_cf)}</div></div>
                <div><span className="text-[11px] text-slate-400">재무</span>
                  <div className="text-lg">{_n(cf.financing_cf)}</div></div>
                <div><span className="text-[11px] text-slate-400">FCF</span>
                  <div className={`text-lg font-bold ${
                    (cf.free_cash_flow ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {_n(cf.free_cash_flow)}</div></div>
                {cf.pl_complete === false && (
                  <div className="text-[11px] text-amber-400 self-end">
                    ⚠️ 손익에 미등록 계정이 있어 이 현금흐름도 그만큼 불완전합니다
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* Backtest — 오차를 액면 그대로 믿게 두지 않는다 */}
        {bt && (
          <section className="border border-slate-700 rounded p-4">
            <h3 className="text-sm font-bold text-slate-200 mb-2">
              Backtest <span className="text-slate-500 font-normal">(계획 vs 실적 오차)</span>
            </h3>
            {!bt.measurable ? (
              <div className="text-xs text-slate-400">
                재지 않았습니다 — {bt.reason}. <span className="text-slate-500">{bt.note}</span>
              </div>
            ) : (
              <>
                {bt.lookahead_risk && (
                  <div className="mb-2 border border-red-500/50 bg-red-500/10 text-red-200 text-xs
                                  rounded px-3 py-2">
                    ⚠️ <b>미래 정보 누설 가능성</b> — 가정이 대상 기간 이후에 작성되었습니다.
                    {' '}이 오차는 <b>실제 예측력이 아닙니다.</b>
                  </div>
                )}
                <div className="flex gap-6 flex-wrap">
                  <div><span className="text-[11px] text-slate-400">MAPE</span>
                    <div className="text-lg">{bt.mape ?? '—'}%</div></div>
                  <div><span className="text-[11px] text-slate-400">편향(bias)</span>
                    <div className={`text-lg ${(bt.bias ?? 0) > 0 ? 'text-amber-400' : ''}`}>
                      {bt.bias === null || bt.bias === undefined ? '—' :
                        `${bt.bias > 0 ? '+' : ''}${bt.bias}%`}</div>
                    <div className="text-[10px] text-slate-500">
                      {(bt.bias ?? 0) > 0 ? '과대추정 경향' : (bt.bias ?? 0) < 0 ? '과소추정 경향' : ''}
                    </div></div>
                  {bt.worst && (
                    <div><span className="text-[11px] text-slate-400">최악 계정</span>
                      <div className="text-lg">{bt.worst.account_code}
                        <span className="text-sm text-amber-400"> {bt.worst.pct_error}%</span></div></div>
                  )}
                </div>
                {(bt.excluded_zero_actual?.length || bt.only_predicted?.length ||
                  bt.only_actual?.length) ? (
                  <p className="text-[10px] text-amber-500/80 mt-2">
                    {bt.excluded_zero_actual?.length ? `실적 0 이라 백분율에서 제외: ${bt.excluded_zero_actual.join(', ')} · ` : ''}
                    {bt.only_predicted?.length ? `계획에만 있음: ${bt.only_predicted.join(', ')} · ` : ''}
                    {bt.only_actual?.length ? `실적에만 있음: ${bt.only_actual.join(', ')}` : ''}
                  </p>
                ) : null}
                <p className="text-[10px] text-slate-500 mt-1">
                  MAPE 하나만 보지 마십시오 — 늘 한쪽으로 치우친 모델은 절대오차가 작아도 위험합니다.
                </p>
              </>
            )}
          </section>
        )}

        {!cmp && !vr && !busy && (
          <p className="text-xs text-slate-500">
            조직·기간을 입력하고 「계산」을 누르십시오. 시나리오를 선택하면 함께 비교합니다.
          </p>
        )}
      </div>
    </div>
  );
}
