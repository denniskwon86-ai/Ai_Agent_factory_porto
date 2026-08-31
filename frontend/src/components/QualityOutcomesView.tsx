import { useEffect, useState } from 'react';
import {
  ROOT_CAUSES, classifyFailure, fetchQualitySummary, fetchUnclassifiedFailures,
  type QualityOutcome, type QualitySummary, type RootCause,
} from '../lib/qualityApi';

// 품질 결과 뷰 (명세서 §10.3 `quality_outcomes` / §8.3 실패 원인 분류)
//
// ⚠️ 이 화면이 지켜야 할 단 하나: **결손을 좋은 소식처럼 보여주지 않는다.**
//   - `미분류` 는 "원인 없음(정상)"이 아니라 "아직 모른다" → 회색이 아니라 경고색, 별도 칸.
//   - `사용자 판정 없음` 은 승인이 아니다 → 승인 칸에 합치지 않고 3칸으로 나눈다.
//   ⚠️ [UIUX-AUDIT-33 §3] 이름을 «사용자 승인 없음» 으로 바꾸지 않는다. 이 칸의 요점은
//     **승인이 아니라 판정이 없다**는 것이고, 이름에 «승인»이 들어가면 다시 섞인다.
//   운영 계기판에서 이 둘이 통과·승인으로 읽히면 화면이 거짓 보고를 하는 것과 같다.
//
// 디자인 시안 확정 시 교체 대상(§ 역할 규약) — 데이터는 lib/qualityApi.ts 에 분리해 두었다.

const CAUSE_KO: Record<string, string> = {
  model_quality: '모델 품질',
  insufficient_context: '문맥 부족',
  output_contract: '출력 계약',
  external_environment: '외부 환경',
  test_harness: '테스트 하네스',
  requirement_ambiguity: '요구사항 모호성',
  unclassified: '미분류(원인 미상)',
};

export function QualityOutcomesView({ project }: { project: string }) {
  const [sum, setSum] = useState<QualitySummary | null>(null);
  const [queue, setQueue] = useState<QualityOutcome[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState('');

  const load = () => {
    setLoading(true);
    // 한 쪽이 실패해도 나머지는 보여준다 — 품질 화면이 통째로 비면 아무것도 못 본다.
    Promise.allSettled([fetchQualitySummary(project), fetchUnclassifiedFailures(project)])
      .then(([s, u]) => {
        setSum(s.status === 'fulfilled' ? s.value : null);
        setQueue(u.status === 'fulfilled' ? u.value : []);
        setErr(s.status === 'rejected' ? String(s.reason?.message || s.reason) : '');
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [project]);

  const onClassify = async (oid: string, cause: RootCause) => {
    setBusy(oid);
    try {
      await classifyFailure(oid, cause);
      load();
    } catch (e: any) {
      setErr(e?.message || '분류에 실패했습니다.');
    } finally {
      setBusy('');
    }
  };

  if (loading) {
    return <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500" /></div>;
  }
  if (!sum || sum.totals.evaluations === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <div className="text-5xl mb-3">🧪</div>
        아직 기록된 게이트 판정이 없습니다. 파이프라인이 한 번 검수 단계를 지나면 집계됩니다.
        <div className="text-xs text-gray-600 mt-2">(데이터 원천: data/quality_outcomes.jsonl · LLM 0콜)</div>
      </div>
    );
  }

  const t = sum.totals;
  const ha = sum.human_acceptance;
  const passRate = t.evaluations ? Math.round((t.passed / t.evaluations) * 100) : 0;
  const perm = sum.permission || ({} as QualitySummary['permission']);

  const kpi = (label: string, val: string, hint?: string, warn = false) => (
    <div className={`bg-gray-900 border rounded-lg p-3 flex flex-col gap-1 ${warn ? 'border-amber-600/60' : 'border-gray-700'}`}>
      <span className="text-[11px] text-gray-400">{label}</span>
      <span className={`text-xl font-bold ${warn ? 'text-amber-400' : 'text-gray-100'}`}>{val}</span>
      {hint && <span className="text-[10px] text-gray-500">{hint}</span>}
    </div>
  );

  return (
    <div className="space-y-6">
      {err && <div className="text-xs text-amber-400 bg-amber-950/30 border border-amber-800 rounded px-3 py-2">{err}</div>}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {kpi('게이트 판정', String(t.evaluations))}
        {kpi('통과율', `${passRate}%`, `통과 ${t.passed} / 실패 ${t.failed}`)}
        {kpi('사용자 승인', String(ha.accepted), `반려 ${ha.revision_requested}건`)}
        {/* ★ 승인과 절대 합치지 않는다 */}
        {kpi('사용자 판정 없음', String(ha.no_human_decision), '승인이 아니라 판정이 없는 것', ha.no_human_decision > 0)}
        {kpi('원인 미분류 실패', String(sum.unclassified_failures),
          sum.unclassified_ratio === null ? '실패 없음' : `실패의 ${Math.round(sum.unclassified_ratio * 100)}%`,
          sum.unclassified_failures > 0)}
      </div>

      {/* 실패 원인 분포 (§8.3) — 미분류를 분리 표기 */}
      <div>
        <h3 className="text-sm font-bold text-emerald-300 mb-2">
          🧭 실패 원인 분포
          <span className="text-gray-500 font-normal"> (§8.3 — 재시도 횟수만 늘리지 않기 위한 분류)</span>
        </h3>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(sum.by_root_cause).length === 0 && (
            <span className="text-xs text-gray-500">실패 기록이 없습니다.</span>
          )}
          {Object.entries(sum.by_root_cause).map(([c, n]) => (
            <div key={c}
                 className={`rounded px-3 py-2 text-sm border ${c === 'unclassified'
                   ? 'bg-amber-950/30 border-amber-700 text-amber-300'
                   : 'bg-gray-900 border-gray-700 text-gray-300'}`}>
              {CAUSE_KO[c] || c}<span className="text-gray-500"> · {n}건</span>
            </div>
          ))}
        </div>
        <div className="text-[10px] text-gray-600 mt-2">
          결정론적 근거(생성 실패 kind·빌드 로그 패턴·심판 인프라 오류)로 판정되는 것만 자동 분류합니다.
          점수 미달은 자동 분류하지 않습니다 — 원인을 추측해 채우면 통계가 근거가 아니라 창작이 됩니다.
        </div>
      </div>

      {/* 사람이 분류할 작업 큐 */}
      {queue.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-amber-300 mb-2">
            📝 원인 분류 대기 <span className="text-gray-500 font-normal">({queue.length}건 — 사람이 판단해야 합니다)</span>
          </h3>
          <div className="space-y-2">
            {queue.map((o) => (
              <div key={o.outcome_id} className="bg-gray-900 border border-gray-700 rounded p-3">
                <div className="flex justify-between items-start gap-3">
                  <div className="min-w-0">
                    <div className="text-sm text-gray-200">
                      <span className="font-bold">{o.gate_name}</span>
                      <span className="text-gray-500"> · {o.verdict}</span>
                      {o.score !== null && <span className="text-gray-500"> · 점수 {o.score}</span>}
                      {o.task_id && <span className="text-gray-500"> · 작업 연결됨</span>}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-1 break-words">
                      {o.rework_reason || (o.failed_checks?.length ? `미달 기준: ${o.failed_checks.join(', ')}` : '기록된 사유 없음')}
                    </div>
                    <div className="text-[10px] text-gray-600 mt-1">
                      {o.ts} · {o.project || '-'} · 게이트 왕복 {o.gate_loops} / 개발 재시도 {o.dev_retry_count}
                    </div>
                  </div>
                  <select
                    disabled={busy === o.outcome_id}
                    defaultValue=""
                    onChange={(e) => e.target.value && onClassify(o.outcome_id, e.target.value as RootCause)}
                    className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 shrink-0"
                  >
                    <option value="">원인 지정…</option>
                    {ROOT_CAUSES.map((c) => <option key={c} value={c}>{CAUSE_KO[c]}</option>)}
                  </select>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 게이트별 */}
      <div>
        <h3 className="text-sm font-bold text-gray-300 mb-2">게이트별</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 border-b border-gray-700 text-left">
              <th className="py-1.5">게이트</th><th>판정</th><th>통과</th><th>실패</th>
              <th>치명 롤백</th><th>최대 검수 왕복</th><th>최대 개발 재시도</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(sum.by_gate).map(([g, v]) => (
              <tr key={g} className="border-b border-gray-800">
                <td className="py-1.5 text-gray-300">{g}</td>
                <td>{v.evaluations}</td><td className="text-emerald-400">{v.passed}</td>
                <td className={v.failed ? 'text-amber-400' : ''}>{v.failed}</td>
                <td className={v.rollback ? 'text-red-400' : 'text-gray-600'}>{v.rollback}</td>
                <td>{v.max_gate_loops}</td><td>{v.max_dev_retries}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-[10px] text-gray-600">
        {sum.note}
        {perm.scope && <> · 권한 범위 {perm.scope}</>}
        {(perm.excluded_other_dept > 0 || perm.excluded_unattributed > 0) && (
          <span className="text-amber-600">
            {' '}· 권한 밖 제외 {perm.excluded_other_dept || 0}건
            {perm.excluded_unattributed > 0 && `, 부서 귀속 불가 제외 ${perm.excluded_unattributed}건`}
          </span>
        )}
      </div>
    </div>
  );
}
