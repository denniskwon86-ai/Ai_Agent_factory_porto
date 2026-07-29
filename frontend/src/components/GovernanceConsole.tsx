// 데이터 거버넌스 콘솔 (명세서 §6 / §12 · M1)
//
// ⚠️ **기능 확인용 최소 화면이다.** 디자인 시안 확정 후 대대적으로 개편될 것을 전제로,
//   표현은 최소화하고 데이터 계층(`lib/governanceApi.ts`)만 재사용 가능하게 두었다.
//   그래서 여기에는 정교한 레이아웃·상태관리를 넣지 않는다 — 버려질 코드에 드는 비용이다.
//
// 이 화면이 답하는 질문 다섯:
//   ① 어떤 기준정보·자산이 조직 범위 없이 **모든 조직에 노출**돼 있나
//   ② 같은 대상이 두 벌로 등록돼 **두 기준값이 함께 주입**되고 있나
//   ③ 카탈로그가 책임·갱신·민감도를 담지 못한 곳은 어디인가
//   ④ 데이터 계약이 지금 지켜지고 있나 (**`unverifiable` 은 통과가 아니다**)
//   ⑤ 어떤 외부지표가 아직 기준 계획에 쓸 수 없나
import { useCallback, useEffect, useState } from 'react';
// `verbatimModuleSyntax` 가 켜져 있어 타입은 반드시 `import type` 으로 분리해야 한다.
import type {
  ContractEvaluation,
  DuplicateCandidate,
  ExternalIndicatorReadiness,
  FlatNode,
  GovernanceGap,
  MasterCoverage,
  SystemsCoverage,
  QualityFinding,
  ScopeCoverage,
} from '../lib/governanceApi';
import {
  fetchContractEvaluations,
  fetchDocumentQuality,
  fetchDuplicates,
  fetchExternalReadiness,
  fetchGovernanceGaps,
  fetchMasterCoverage,
  fetchSystemsCoverage,
  fetchOrgNodes,
  fetchScopeCoverage,
} from '../lib/governanceApi';

type Props = { onClose: () => void };

const SEV: Record<string, string> = {
  high: 'text-red-400 border-red-500/40 bg-red-500/10',
  medium: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
  low: 'text-slate-300 border-slate-500/40 bg-slate-500/10',
};

// 계약 상태 4종. `unverifiable` 을 `kept` 와 같은 색으로 두면 "확인 못 한 것"이 "지켜진 것"으로
//   읽힌다 — 이 화면에서 가장 조심해야 할 오독이다.
const CONTRACT_STATE: Record<string, { label: string; cls: string }> = {
  kept: { label: '지켜짐', cls: 'text-emerald-400' },
  at_risk: { label: '주의', cls: 'text-amber-300' },
  breached: { label: '위반', cls: 'text-red-400' },
  unverifiable: { label: '확인 불가', cls: 'text-violet-300' },
};

function Section({ title, hint, children }: {
  title: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <section className="border border-slate-700 rounded-lg p-4 bg-slate-900/60">
      <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
      {hint && <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="flex-1 min-w-[110px]">
      <div className={`text-2xl font-semibold ${tone || 'text-slate-100'}`}>{value}</div>
      <div className="text-[11px] text-slate-400">{label}</div>
    </div>
  );
}

export default function GovernanceConsole({ onClose }: Props) {
  const [scope, setScope] = useState('');
  const [nodes, setNodes] = useState<FlatNode[]>([]);
  const [masterCov, setMasterCov] = useState<MasterCoverage | null>(null);
  const [scopeCov, setScopeCov] = useState<ScopeCoverage | null>(null);
  const [sysCov, setSysCov] = useState<SystemsCoverage | null>(null);
  const [dups, setDups] = useState<DuplicateCandidate[]>([]);
  const [docFindings, setDocFindings] = useState<QualityFinding[]>([]);
  const [gaps, setGaps] = useState<GovernanceGap[]>([]);
  const [contracts, setContracts] = useState<ContractEvaluation[]>([]);
  const [ext, setExt] = useState<ExternalIndicatorReadiness[]>([]);
  const [extMeta, setExtMeta] = useState({ blocked: 0, usable: 0, sources: 0 });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    // 한 섹션이 실패해도 나머지는 보여준다 — 거버넌스 화면이 통째로 비면 아무것도 못 본다.
    const results = await Promise.allSettled([
      fetchMasterCoverage(), fetchScopeCoverage(), fetchDuplicates(), fetchDocumentQuality(),
      fetchGovernanceGaps(scope), fetchContractEvaluations(), fetchExternalReadiness(),
      fetchSystemsCoverage(),
    ]);
    const failed: string[] = [];
    const pick = <T,>(i: number, name: string): T | null => {
      const r = results[i];
      if (r.status === 'fulfilled') return r.value as T;
      failed.push(name);
      return null;
    };
    setMasterCov(pick<MasterCoverage>(0, '기준정보 커버리지'));
    setScopeCov(pick<ScopeCoverage>(1, '자산 범위 커버리지'));
    setDups(pick<{ candidates: DuplicateCandidate[] }>(2, '중복 후보')?.candidates || []);
    setDocFindings(pick<{ findings: QualityFinding[] }>(3, '문서 품질')?.findings || []);
    setGaps(pick<{ gaps: GovernanceGap[] }>(4, '거버넌스 결손')?.gaps || []);
    const cv = pick<{ results: ContractEvaluation[] }>(5, '계약 평가');
    setContracts(cv?.results || []);
    const ex = pick<{
      indicators: ExternalIndicatorReadiness[]; blocked: number;
      usable_for_baseline: number; approved_sources: number;
    }>(6, '외부지표 준비도');
    setExt(ex?.indicators || []);
    setExtMeta({ blocked: ex?.blocked ?? 0, usable: ex?.usable_for_baseline ?? 0,
                 sources: ex?.approved_sources ?? 0 });
    setSysCov(pick<SystemsCoverage>(7, '연계 시스템 커버리지'));
    if (failed.length) setErr(`불러오지 못한 항목: ${failed.join(', ')}`);
    setLoading(false);
  }, [scope]);

  useEffect(() => { fetchOrgNodes().then(setNodes); }, []);
  useEffect(() => { load(); }, [load]);

  const highDups = dups.filter((d) => d.confidence === 'high');
  const highGaps = gaps.filter((g) => g.severity === 'high');
  const badContracts = contracts.filter((c) => c.state === 'breached' || c.state === 'at_risk');
  const unverifiable = contracts.filter((c) => c.state === 'unverifiable');

  return (
    <div className="fixed inset-0 z-50 bg-slate-950 text-slate-200 overflow-y-auto">
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <header className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">데이터 거버넌스 콘솔</h2>
            <p className="text-[11px] text-slate-400">
              기능 확인용 화면입니다. 디자인 확정 후 개편됩니다.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs"
            >
              <option value="">전체 (범위 필터 없음)</option>
              {nodes.map((n) => (
                <option key={n.node_id} value={n.node_id} disabled={!n.readable}>
                  {' '.repeat(n.depth * 2)}{n.label}{n.readable ? '' : ' (열람 불가)'}
                </option>
              ))}
            </select>
            <button onClick={load} className="px-3 py-1 text-xs bg-slate-700 rounded">
              새로고침
            </button>
            <button onClick={onClose} className="px-3 py-1 text-xs bg-slate-600 rounded">
              닫기
            </button>
          </div>
        </header>

        {err && (
          <div className="border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs
                          rounded px-3 py-2">
            {err} — 나머지 항목은 아래에 표시됩니다.
          </div>
        )}
        {loading && <div className="text-xs text-slate-400">불러오는 중…</div>}

        {/* ① 조직 범위 노출 — 조용한 노출이 가장 위험하다 */}
        <Section
          title="① 조직 범위 노출"
          hint="범위가 지정되지 않은 항목은 모든 조직의 프롬프트·목록에 들어갑니다(점진 도입 규칙).
                의도한 전사 공용이면 정상이고, 아니면 소유 조직을 지정하십시오."
        >
          <div className="flex gap-6 flex-wrap">
            <Stat label="기준정보 전체" value={masterCov?.total_records ?? '—'} />
            <Stat
              label="기준정보 전 조직 노출"
              value={masterCov?.exposed_records ?? '—'}
              tone={masterCov && masterCov.exposed_records > 0 ? 'text-red-400' : undefined}
            />
            <Stat label="자산 전체" value={scopeCov?.total ?? '—'} />
            <Stat
              label="자산 범위 미지정"
              value={scopeCov?.unscoped ?? '—'}
              tone={scopeCov && scopeCov.unscoped > 0 ? 'text-red-400' : undefined}
            />
            {/* 연계 시스템은 실측값이 프롬프트에 병기되므로 노출 대가가 가장 크다 */}
            <Stat label="연계 시스템 전체" value={sysCov?.total ?? '—'} />
            <Stat
              label="연계 시스템 범위 미지정"
              value={sysCov?.unscoped ?? '—'}
              tone={sysCov && sysCov.unscoped > 0 ? 'text-red-400' : undefined}
            />
          </div>
          {!!sysCov?.unscoped_systems.length && (
            <p className="mt-2 text-[11px] text-slate-400 break-all">
              범위 미지정 연계 시스템: {sysCov.unscoped_systems.join(', ')}
              {' '}— 이 시스템의 실측값은 모든 조직의 프롬프트에 병기될 수 있습니다.
            </p>
          )}
          {!!masterCov?.exposed_codes.length && (
            <p className="mt-3 text-[11px] text-slate-400 break-all">
              노출 기준정보: {masterCov.exposed_codes.slice(0, 20).join(', ')}
              {masterCov.exposed_codes.length > 20 && ` 외 ${masterCov.exposed_codes.length - 20}건`}
            </p>
          )}
        </Section>

        {/* ② 중복 — 둘 다 활성이면 두 기준값이 함께 주입된다 */}
        <Section
          title={`② 중복 기준정보 후보 (high ${highDups.length} / 전체 ${dups.length})`}
          hint="둘 다 활성이면 두 기준값이 함께 프롬프트에 들어갑니다. 자동 병합하지 않습니다 —
                정본 판단은 현업 몫입니다. low 는 대개 의도된 사업부별 분리입니다."
        >
          {dups.length === 0 ? (
            <p className="text-xs text-slate-500">후보 없음</p>
          ) : (
            <ul className="space-y-1.5">
              {dups.slice(0, 12).map((d) => (
                <li key={d.codes.join('|')}
                    className={`text-xs border rounded px-2 py-1.5 ${SEV[d.confidence]}`}>
                  <span className="font-mono">{d.codes[0]}</span>
                  <span className="mx-1 opacity-60">↔</span>
                  <span className="font-mono">{d.codes[1]}</span>
                  <span className="ml-2 opacity-70">{d.kind}</span>
                  <div className="text-slate-300 mt-0.5">{d.suggested_action}</div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* ③ 카탈로그 결손 + 문서 보정 목록 */}
        <Section
          title={`③ 보정 목록 (카탈로그 결손 ${gaps.length} · 문서 품질 ${docFindings.length})`}
          hint="자동으로 채우지 않습니다. 소유자를 시스템이 추측해 넣으면 아무도 책임지지 않는
                자산이 책임자가 있는 것처럼 보이고, 그건 없는 것보다 나쁩니다."
        >
          <div className="flex gap-6 flex-wrap mb-3">
            <Stat label="카탈로그 결손(high)" value={highGaps.length}
                  tone={highGaps.length ? 'text-red-400' : undefined} />
            <Stat label="문서 품질 보정" value={docFindings.length} />
          </div>
          <ul className="space-y-1.5">
            {[...gaps.slice(0, 6).map((g) => ({
              key: `${g.asset_id}-${g.kind}`, sev: g.severity,
              head: `${g.asset} · ${g.kind}`, body: g.why,
            })), ...docFindings.slice(0, 6).map((f) => ({
              key: `${f.subject}-${f.kind}`, sev: f.severity,
              head: `${f.subject} · ${f.kind}`, body: f.suggested_action,
            }))].map((r) => (
              <li key={r.key} className={`text-xs border rounded px-2 py-1.5 ${SEV[r.sev]}`}>
                <div className="font-medium">{r.head}</div>
                <div className="text-slate-300 mt-0.5">{r.body}</div>
              </li>
            ))}
          </ul>
        </Section>

        {/* ④ 계약 — unverifiable 을 kept 와 섞지 않는다 */}
        <Section
          title={`④ 데이터 계약 (활성 ${contracts.length})`}
          hint="‘확인 불가’는 통과가 아닙니다 — 품질 프로파일이 없어 검증하지 못한 상태입니다.
                지켜짐과 같은 것으로 읽으면 '계약 준수 중'이라는 거짓 안심이 생깁니다."
        >
          <div className="flex gap-6 flex-wrap mb-3">
            {(['kept', 'at_risk', 'breached', 'unverifiable'] as const).map((s) => (
              <Stat key={s} label={CONTRACT_STATE[s].label}
                    value={contracts.filter((c) => c.state === s).length}
                    tone={CONTRACT_STATE[s].cls} />
            ))}
          </div>
          {[...badContracts, ...unverifiable].slice(0, 8).map((c) => (
            <div key={c.contract_id} className="text-xs border border-slate-700 rounded
                                                px-2 py-1.5 mb-1.5">
              <span className={CONTRACT_STATE[c.state]?.cls}>
                [{CONTRACT_STATE[c.state]?.label}]
              </span>
              <span className="ml-2">{c.consumer} · v{c.version}</span>
              <div className="text-slate-300 mt-0.5">
                {(c.findings[0]?.why) || (c.unverifiable[0]?.why) || ''}
              </div>
            </div>
          ))}
          {contracts.length === 0 && <p className="text-xs text-slate-500">활성 계약 없음</p>}
        </Section>

        {/* ⑤ 외부지표 — 수집기는 없다. 무엇이 없는지 아는 것이 산출물이다 */}
        <Section
          title={`⑤ 외부지표 준비도 (사용 가능 ${extMeta.usable} / 차단 ${extMeta.blocked})`}
          hint="수집기·스케줄러는 만들지 않았습니다 — 승인된 원천이 없는 상태의 수집기는 죽은
                코드이거나 값을 지어내는 경로가 됩니다. 지금 필요한 것은 원천 승인입니다."
        >
          <div className="flex gap-6 flex-wrap mb-3">
            <Stat label="승인된 원천" value={extMeta.sources}
                  tone={extMeta.sources === 0 ? 'text-red-400' : 'text-emerald-400'} />
            <Stat label="기준계획 사용 가능" value={extMeta.usable} />
            <Stat label="차단" value={extMeta.blocked}
                  tone={extMeta.blocked ? 'text-amber-300' : undefined} />
          </div>
          <ul className="space-y-1.5">
            {ext.map((i) => (
              <li key={i.code} className="text-xs border border-slate-700 rounded px-2 py-1.5">
                <span className={i.usable_for_baseline ? 'text-emerald-400' : 'text-amber-300'}>
                  {i.usable_for_baseline ? '가용' : '차단'}
                </span>
                <span className="ml-2 font-mono">{i.code}</span>
                <span className="ml-2 opacity-70">{i.name} · {i.required_grade}</span>
                {!i.usable_for_baseline && (
                  <div className="text-slate-300 mt-0.5">{i.next_action || i.reason}</div>
                )}
              </li>
            ))}
            {ext.length === 0 && (
              <p className="text-xs text-slate-500">
                등록된 외부지표 없음 — 플레이북에서 시드하십시오.
              </p>
            )}
          </ul>
        </Section>
      </div>
    </div>
  );
}
