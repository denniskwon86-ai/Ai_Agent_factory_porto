import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../store/useFactoryStore';

// 운영 계기판 (Phase 4) — LLM 호출 텔레메트리 뷰어.
// 1순위 축은 '실제 사용 모델(used)' — 이 산출물을 어느 제공사/모델이 만들었나 = 모델 불변성 실측.
export function TelemetryPanel({ onClose }: { onClose: () => void }) {
  const [projects, setProjects] = useState<string[]>([]);
  const [project, setProject] = useState('');   // '' = 전역
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

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
  const modelEntries = Object.entries(byModel).sort((a, b) => b[1] - a[1]);
  const maxModel = modelEntries.length ? modelEntries[0][1] : 1;

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
            <h2 className="text-lg font-bold">운영 계기판 (LLM 텔레메트리)</h2>
            <select
              value={project} onChange={e => setProject(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
            >
              <option value="">전역 (모든 프로젝트)</option>
              {projects.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          {loading ? (
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
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {kpi('총 호출', String(t.calls))}
                {kpi('성공률', `${Math.round((t.success_rate || 0) * 100)}%`)}
                {kpi('폴백률', `${Math.round((t.fallback_rate || 0) * 100)}%`, `${t.fallback_calls || 0}건`)}
                {kpi('Pro 강등', String(t.downgraded_calls || 0), '브레이커 강등 호출')}
                {kpi('총 소요', `${t.total_duration_s || 0}s`)}
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
              <div className="text-[10px] text-gray-600">집계 레코드 {data.record_count}건 · 폴백률 = 시도 2회 이상 호출 비율 · 토큰 계측은 v2 예정</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
