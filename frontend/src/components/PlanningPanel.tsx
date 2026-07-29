import { useEffect, useState } from 'react';
import {
  compareScenarios, fetchAccounts, fetchScenarios, fetchVariance,
  type Account, type Scenario, type ScenarioComparison, type Variance,
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
    const [c, v] = await Promise.allSettled([
      picked.length ? compareScenarios(picked, orgId, period) : Promise.resolve(null as any),
      fetchVariance(orgId, period),
    ]);
    setCmp(c.status === 'fulfilled' ? c.value : null);
    setVr(v.status === 'fulfilled' ? v.value : null);
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

        {!cmp && !vr && !busy && (
          <p className="text-xs text-slate-500">
            조직·기간을 입력하고 「계산」을 누르십시오. 시나리오를 선택하면 함께 비교합니다.
          </p>
        )}
      </div>
    </div>
  );
}
