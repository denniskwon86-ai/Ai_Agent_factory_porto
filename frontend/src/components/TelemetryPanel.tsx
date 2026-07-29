import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../store/useFactoryStore';
import { QualityOutcomesView } from './QualityOutcomesView';

// 운영 계기판 (Phase 4) — LLM 호출 텔레메트리 뷰어.
// 1순위 축은 '실제 사용 모델(used)' — 이 산출물을 어느 제공사/모델이 만들었나 = 모델 불변성 실측.
// 목록 항목 — 이름은 바뀌거나 중복될 수 있어 project_id·소유 부서를 함께 받는다.
type ProjItem = { project: string; project_id?: string; owner_dept_id?: string };

export function TelemetryPanel({ onClose }: { onClose: () => void }) {
  const [projects, setProjects] = useState<ProjItem[]>([]);
  const [project, setProject] = useState('');   // '' = 전역
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  // §10.3 은 텔레메트리를 `llm_calls` 와 `quality_outcomes` 두 축으로 규정한다. 같은 계기판에
  // 두되 **한 화면에 섞지 않는다** — "얼마 썼나"와 "통과했나"는 읽는 목적이 다르다.
  const [tab, setTab] = useState<'llm' | 'quality'>('llm');

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/v1/telemetry/projects`)
      .then(r => r.json()).then(j => setProjects(j.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const q = project ? `?project=${encodeURIComponent(project)}` : '';
    fetch(`${API_BASE_URL}/api/v1/telemetry/summary${q}`)
      .then(r => r.json())
      .then(j => setData(j.status === 'success' ? j.data : null))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [project]);

  const t = data?.totals || {};
  const byModel: Record<string, number> = data?.by_model || {};
  const byStage: Record<string, any> = data?.by_stage || {};
  const byReq: Record<string, any> = data?.by_requested_tier || {};
  const byBasis: Record<string, any> = data?.by_cost_basis || {};
  const byProvider: Record<string, any> = data?.by_provider || {};
  const perm = data?.permission || {};
  const modelEntries = Object.entries(byModel).sort((a, b) => b[1] - a[1]);
  const maxModel = modelEntries.length ? modelEntries[0][1] : 1;

  // 비용 표기 — 미산정이 하나라도 있으면 합계는 **하한**이므로 '≥' 를 붙인다.
  // 0 으로 채워 완전한 총액처럼 보이게 하는 것이 이 화면에서 가장 위험한 거짓말이다.
  const costLabel = `${t.cost_complete === false ? '≥ ' : ''}$${(t.cost_usd || 0).toFixed(4)}`;
  const costHint = t.cost_complete === false
    ? `미산정 ${t.unpriced_calls || 0}건 (단가 미등록)`
    : (t.cost_partial_calls ? `${t.cost_partial_calls}건은 단가 일부만 등록(과소)` : '전 호출 산정됨');
  // 산정 근거 라벨 — 무료 0 과 '모름'을 사람이 구분할 수 있어야 한다.
  const basisKo: Record<string, string> = {
    free_tier: '무료 티어(과금 0)', cache_hit: '캐시 적중(호출 없음)',
    paid: '유료(산정)', paid_partial: '유료(단가 일부)', unpriced: '유료·단가 미등록',
  };

  const kpi = (label: string, val: string, hint?: string) => (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 flex flex-col gap-1">
      <span className="text-[11px] text-gray-400">{label}</span>
      <span className="text-xl font-bold text-gray-100">{val}</span>
      {hint && <span className="text-[10px] text-gray-500">{hint}</span>}
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-70 p-4">
      <div className="bg-gray-800 rounded-xl shadow-2xl border border-gray-700 w-full max-w-4xl max-h-[90vh] flex flex-col text-gray-200">
        <div className="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-900 rounded-t-xl">
          <div className="flex items-center gap-3">
            <span className="text-xl">📊</span>
            <h2 className="text-lg font-bold">운영 계기판</h2>
            <div className="flex rounded overflow-hidden border border-gray-700 text-xs">
              {([['llm', 'LLM 호출'], ['quality', '품질 결과']] as const).map(([k, label]) => (
                <button key={k} onClick={() => setTab(k)}
                        className={`px-3 py-1 ${tab === k ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'}`}>
                  {label}
                </button>
              ))}
            </div>
            <select
              value={project} onChange={e => setProject(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
            >
              <option value="">전역 (모든 프로젝트)</option>
              {projects.map(p => (
                <option key={p.project} value={p.project}>
                  {p.project}{p.owner_dept_id ? ` (${p.owner_dept_id})` : ''}
                </option>
              ))}
            </select>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          {tab === 'quality' ? (
            <QualityOutcomesView project={project} />
          ) : loading ? (
            <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" /></div>
          ) : !data || t.calls === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <div className="text-5xl mb-3">📊</div>
              아직 기록된 LLM 호출이 없습니다. 파이프라인을 한 번 가동하면 여기 집계됩니다.
              <div className="text-xs text-gray-600 mt-2">(데이터 원천: data/llm_call_log.jsonl)</div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* KPI */}
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                {kpi('총 호출', String(t.calls))}
                {kpi('성공률', `${Math.round((t.success_rate || 0) * 100)}%`)}
                {kpi('폴백률', `${Math.round((t.fallback_rate || 0) * 100)}%`, `${t.fallback_calls || 0}건`)}
                {kpi('Pro 강등', String(t.downgraded_calls || 0), '브레이커 강등 호출')}
                {kpi('총 소요', `${t.total_duration_s || 0}s`)}
                {kpi('LLM 비용', costLabel, costHint)}
              </div>

              {/* 비용 산정 근거 — '무료라서 0' 과 '몰라서 0' 을 구분해 보여준다 */}
              <div>
                <h3 className="text-sm font-bold text-emerald-300 mb-2">
                  💰 비용 산정 근거
                  <span className="text-gray-500 font-normal"> (§10.1 승인된 결과물 1건당 비용의 기초 계측)</span>
                </h3>
                <div className="flex gap-3 flex-wrap">
                  {Object.entries(byBasis).map(([b, v]: any) => (
                    <div key={b} className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm">
                      <span className={b === 'unpriced' ? 'text-amber-400' : 'text-gray-300'}>
                        {basisKo[b] || b}
                      </span>
                      <span className="text-gray-500"> · {v.calls}건</span>
                      {b === 'unpriced'
                        ? <span className="text-amber-500"> · 산정 불가</span>
                        : <span className="text-gray-400"> · ${(v.cost_usd || 0).toFixed(4)}</span>}
                    </div>
                  ))}
                </div>
                {t.unpriced_calls > 0 && (
                  <div className="text-[10px] text-amber-500/80 mt-2">
                    ⚠️ 단가가 등록되지 않은 유료 모델이 있어 총액은 하한입니다.
                    추정으로 메우지 않습니다 — <code className="text-gray-400">config.LLM_PRICE_PER_MTOK</code> 에
                    제공사 가격을 근거와 함께 등록하면 과거 로그까지 소급 산정됩니다.
                  </div>
                )}
                {Object.keys(byProvider).length > 0 && (
                  <div className="flex gap-2 flex-wrap mt-2">
                    {Object.entries(byProvider).map(([pv, v]: any) => (
                      <span key={pv} className="text-[11px] bg-gray-900 border border-gray-800 rounded px-2 py-1 text-gray-400">
                        {pv} · {v.calls}건 · ${(v.cost_usd || 0).toFixed(4)}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* 실제 사용 모델 분포 — 핵심 지표 */}
              <div>
                <h3 className="text-sm font-bold text-blue-300 mb-3">🎯 실제 사용 모델 분포 <span className="text-gray-500 font-normal">(모델 불변성 실측 — 어느 모델이 산출물을 만들었나)</span></h3>
                <div className="space-y-2">
                  {modelEntries.map(([m, n]) => (
                    <div key={m} className="flex items-center gap-3">
                      <span className="text-xs font-mono text-gray-300 w-64 truncate" title={m}>{m}</span>
                      <div className="flex-1 bg-gray-900 rounded h-5 overflow-hidden border border-gray-700">
                        <div className="h-full bg-gradient-to-r from-blue-600 to-indigo-500 flex items-center justify-end pr-2"
                             style={{ width: `${Math.max(6, (n / maxModel) * 100)}%` }}>
                          <span className="text-[10px] font-bold text-white">{n}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 요청 티어 vs 강등 */}
              <div>
                <h3 className="text-sm font-bold text-gray-300 mb-2">요청 티어별 (강등 = Pro 원했으나 Flash로)</h3>
                <div className="flex gap-3 flex-wrap">
                  {Object.entries(byReq).map(([tier, v]: any) => (
                    <div key={tier} className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm">
                      <span className="font-mono text-gray-300">{tier}</span>
                      <span className="text-gray-500"> · {v.calls}건</span>
                      {v.downgraded > 0 && <span className="text-amber-400"> · 강등 {v.downgraded}</span>}
                    </div>
                  ))}
                </div>
              </div>

              {/* 단계별 */}
              <div>
                <h3 className="text-sm font-bold text-gray-300 mb-2">단계별</h3>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-500 border-b border-gray-700 text-left">
                      <th className="py-1.5">단계</th><th>호출</th><th>성공</th><th>평균 소요</th><th>주 사용 모델</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(byStage).map(([stage, s]: any) => {
                      const top = Object.entries(s.models || {}).sort((a: any, b: any) => b[1] - a[1])[0];
                      return (
                        <tr key={stage} className="border-b border-gray-800">
                          <td className="py-1.5 text-gray-300">{stage}</td>
                          <td>{s.calls}</td><td>{s.ok}</td><td>{s.avg_duration_s}s</td>
                          <td className="font-mono text-xs text-gray-400">{top ? `${top[0]} (${top[1]})` : '-'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="text-[10px] text-gray-600">
                집계 레코드 {data.record_count}건 · 폴백률 = 시도 2회 이상 호출 비율 ·
                토큰 {(t.total_input_tokens || 0).toLocaleString()} in / {(t.total_output_tokens || 0).toLocaleString()} out
                {perm.scope && <> · 권한 범위 {perm.scope}</>}
                {/* 스코프에서 빠진 건수를 밝힌다 — 조용히 빼면 집계가 작아진 줄도 모른다 */}
                {(perm.excluded_other_dept > 0 || perm.excluded_unattributed > 0) && (
                  <span className="text-amber-600">
                    {' '}· 권한 밖 제외 {perm.excluded_other_dept || 0}건
                    {perm.excluded_unattributed > 0 && `, 부서 귀속 불가 제외 ${perm.excluded_unattributed}건`}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
