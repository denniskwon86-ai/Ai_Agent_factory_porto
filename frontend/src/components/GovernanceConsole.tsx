// [이관 5/10] 데이터 거버넌스 콘솔 — «무엇이 안 되어 있는가»를 모으는 화면
//
// 이 화면이 답하는 질문 다섯:
//   ① 어떤 기준정보·자산·연계 시스템이 조직 범위 없이 **모든 조직에 노출**돼 있나
//   ② 같은 대상이 두 벌로 등록돼 **두 기준값이 함께 주입**되고 있나
//   ③ 카탈로그가 책임·갱신·민감도를 담지 못한 곳은 어디인가
//   ④ 데이터 계약이 지금 지켜지고 있나 (**«확인 불가»는 통과가 아니다**)
//   ⑤ 어떤 외부지표가 아직 기준 계획에 쓸 수 없나
//
// ★★★ 이 화면에서 가장 위험한 오독은 «없음»이다. 다섯 섹션 모두 «0건»이 좋은 소식으로 읽히는데,
//   조회가 막혔거나 실패해도 종전 구현은 똑같이 «후보 없음»·«활성 계약 없음»을 표시했다.
//   그러면 사용자는 정비가 끝났다고 믿는다 — 실제로는 아무것도 확인하지 못한 상태다.
//   → 상태를 셋으로 나눈다: **정비 완료(0건)** · **권한 없음** · **조회 실패**.
//
// ⚠️ 종전 구현에서 제거한 것:
//   · 자체 `fixed inset-0` 전체화면(모달 semantics·포커스 트랩·Escape 없음) → `HubDialog`
//   · 실패 목록을 문자열 하나로 합쳐 상단에 뿌리던 것 → 섹션마다 자기 상태를 말한다
//   · 내부 슬러그(`kind` · `required_grade` · `severity`)를 그대로 노출 → `design/terms.ts`
//   · 다섯 섹션을 한 페이지에 쌓던 구조 → 셸 레일 다섯 항목(한 번에 하나를 본다)
import { useCallback, useEffect, useMemo, useState } from 'react';

import { EvidenceStrip, FoundationToolbar } from '../design/DataFoundationShell';
// ★ [2026-08-05] `EmptyOrError` 와 `errorTitle` 은 import 만 남고 쓰이지 않아 빌드를 깨뜨렸다
//   (TS6133). 이 화면은 `Metric` 의 `notes` 로 빈 상태·권한없음·오류를 각각 말하고 있어서
//   그 둘이 필요 없다 — 지운다. 다시 필요해지면 그때 가져온다.
import { Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { contractStateKo, dataGradeKo, findingKindKo, severityKo } from '../design/terms';
import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import type {
  ContractEvaluation, DuplicateCandidate, ExternalIndicatorReadiness, FlatNode, GovernanceGap,
  MasterCoverage, QualityFinding, ScopeCoverage, SystemsCoverage,
} from '../lib/governanceApi';
import {
  fetchContractEvaluations, fetchDocumentQuality, fetchDuplicates, fetchExternalReadiness,
  fetchGovernanceGaps, fetchMasterCoverage, fetchOrgNodes, fetchScopeCoverage,
  fetchSystemsCoverage,
} from '../lib/governanceApi';

type View = 'exposure' | 'duplicates' | 'catalog' | 'contracts' | 'external';

const MODULE: Record<View, { kicker: string; title: string; subtitle: string; desc: string }> = {
  exposure: {
    kicker: 'EXPOSURE', title: '조직 범위 노출',
    subtitle: '범위가 없는 항목은 모든 조직에 들어갑니다.',
    desc: '의도한 전사 공용이면 정상입니다. 아니면 소유 조직을 지정하십시오 — 조용한 노출이 가장 위험합니다.',
  },
  duplicates: {
    kicker: 'DUPLICATES', title: '중복 기준정보',
    subtitle: '둘 다 활성이면 두 기준값이 함께 주입됩니다.',
    desc: '자동 병합하지 않습니다 — 어느 쪽이 정본인지는 현업이 정합니다. 낮은 확신은 대개 의도된 사업부별 분리입니다.',
  },
  catalog: {
    kicker: 'CATALOG', title: '보정 목록',
    subtitle: '카탈로그가 책임·갱신·민감도를 담지 못한 곳.',
    desc: '자동으로 채우지 않습니다. 소유자를 시스템이 추측해 넣으면 아무도 책임지지 않는 자산이 책임자가 있는 것처럼 보입니다.',
  },
  contracts: {
    kicker: 'CONTRACTS', title: '데이터 계약',
    subtitle: '«확인 불가»는 통과가 아닙니다.',
    desc: '확인 불가는 검증할 품질 프로파일이 없는 상태입니다. 지켜짐과 같이 읽으면 거짓 안심이 생깁니다.',
  },
  external: {
    kicker: 'EXTERNAL', title: '외부지표 준비도',
    subtitle: '무엇을 아직 쓸 수 없는지 봅니다.',
    desc: '수집기·스케줄러를 만들지 않았습니다 — 승인된 원천이 없는 수집기는 값을 지어내는 경로가 됩니다.',
  },
};

/** 다섯 섹션이 공유하는 «조회 상태». `Loaded` 를 그대로 쓰되, 403 은 `forbidden` 으로 담는다. */
function toLoaded<T>(r: PromiseSettledResult<T>): Loaded<T> {
  if (r.status === 'fulfilled') { reportRequestSuccess(); return ok(r.value); }
  const status = (r.reason as { status?: number })?.status;
  reportRequestFailure(status);
  if (status === 403 || status === 401) {
    return { status: 'forbidden', value: null, error: (r.reason as Error)?.message
      || '이 지표를 볼 권한이 없습니다.', httpStatus: status };
  }
  return failed<T>(r.reason);
}

export default function GovernanceConsole({ onClose }: { onClose: () => void }) {
  const [view, setView] = useState<View>('exposure');
  const [scopeNode, setScopeNode] = useState('');
  const [nodes, setNodes] = useState<FlatNode[]>([]);
  const [masterCov, setMasterCov] = useState<Loaded<MasterCoverage>>(loading<MasterCoverage>());
  const [scopeCov, setScopeCov] = useState<Loaded<ScopeCoverage>>(loading<ScopeCoverage>());
  const [sysCov, setSysCov] = useState<Loaded<SystemsCoverage>>(loading<SystemsCoverage>());
  const [dups, setDups] = useState<Loaded<{ candidates: DuplicateCandidate[] }>>(
    loading<{ candidates: DuplicateCandidate[] }>());
  const [docQ, setDocQ] = useState<Loaded<{ findings: QualityFinding[] }>>(
    loading<{ findings: QualityFinding[] }>());
  const [gaps, setGaps] = useState<Loaded<{ gaps: GovernanceGap[] }>>(
    loading<{ gaps: GovernanceGap[] }>());
  const [contracts, setContracts] = useState<Loaded<{ results: ContractEvaluation[] }>>(
    loading<{ results: ContractEvaluation[] }>());
  const [ext, setExt] = useState<Loaded<{
    indicators: ExternalIndicatorReadiness[]; blocked: number;
    usable_for_baseline: number; approved_sources: number;
  }>>(loading());
  const [scope, setScope] = useState<ActingScope | null>(actingScope.peek());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setMasterCov(loading()); setScopeCov(loading()); setSysCov(loading());
    setDups(loading()); setDocQ(loading()); setGaps(loading());
    setContracts(loading()); setExt(loading());
    // 한 섹션이 막혀도 나머지는 보여준다 — 거버넌스 화면이 통째로 비면 아무것도 못 본다.
    const [mc, sc, dp, dq, gp, ct, ex, sy] = await Promise.allSettled([
      fetchMasterCoverage(), fetchScopeCoverage(), fetchDuplicates(), fetchDocumentQuality(),
      fetchGovernanceGaps(scopeNode), fetchContractEvaluations(), fetchExternalReadiness(),
      fetchSystemsCoverage(),
    ]);
    setMasterCov(toLoaded(mc)); setScopeCov(toLoaded(sc)); setSysCov(toLoaded(sy));
    setDups(toLoaded(dp)); setDocQ(toLoaded(dq)); setGaps(toLoaded(gp));
    setContracts(toLoaded(ct)); setExt(toLoaded(ex));
    setBusy(false);
  }, [scopeNode]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    // 노드 목록은 실패해도 화면을 막지 않는다(범위 필터가 없을 뿐이다).
    fetchOrgNodes().then(setNodes).catch(() => setNodes([]));
  }, []);
  useEffect(() => { actingScope.load().then(setScope).catch(() => setScope(UNKNOWN_SCOPE)); }, []);
  useEffect(() => actingScope.subscribe(setScope), []);
  useEffect(() => {
    const onUser = () => {
      setNodes([]); fetchOrgNodes().then(setNodes).catch(() => setNodes([]));
      actingScope.load().then(setScope).catch(() => setScope(UNKNOWN_SCOPE));
      load();
    };
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [load]);

  // ── 파생 ────────────────────────────────────────────────────────────────
  const dupRows = dups.value?.candidates || [];
  const gapRows = gaps.value?.gaps || [];
  const docRows = docQ.value?.findings || [];
  const contractRows = contracts.value?.results || [];
  const extRows = ext.value?.indicators || [];

  const exposedTotal = (masterCov.value?.exposed_records ?? 0)
    + (scopeCov.value?.unscoped ?? 0) + (sysCov.value?.unscoped ?? 0);
  const highDups = dupRows.filter((d) => d.confidence === 'high');
  const highGaps = gapRows.filter((g) => g.severity === 'high');
  const badContracts = contractRows.filter((c) => c.state === 'breached' || c.state === 'at_risk');
  const unverifiable = contractRows.filter((c) => c.state === 'unverifiable');

  /** 섹션 상태를 하나로 접는다. 여러 조회가 한 섹션을 이루는 곳이 있다(노출은 셋). */
  const worst = (...states: Loaded<unknown>[]) => {
    if (states.some((s) => s.status === 'loading')) return 'loading' as const;
    if (states.some((s) => s.status === 'error')) return 'error' as const;
    if (states.some((s) => s.status === 'forbidden')) return 'forbidden' as const;
    return 'ok' as const;
  };
  const exposureState = worst(masterCov, scopeCov, sysCov);
  const catalogState = worst(gaps, docQ);

  const VIEW_STATE: Record<View, ReturnType<typeof worst>> = {
    exposure: exposureState,
    duplicates: dups.status,
    catalog: catalogState,
    contracts: contracts.status,
    external: ext.status,
  };
  const state = VIEW_STATE[view];

  /** 이 섹션이 «지금 손봐야 할 건수». ⚠️ 조회가 막혔으면 0 이 아니라 «모른다»다. */
  const openCount: Record<View, number | null> = {
    exposure: exposureState === 'ok' ? exposedTotal : null,
    duplicates: dups.status === 'ok' ? highDups.length : null,
    catalog: catalogState === 'ok' ? highGaps.length + docRows.length : null,
    contracts: contracts.status === 'ok' ? badContracts.length + unverifiable.length : null,
    external: ext.status === 'ok' ? (ext.value?.blocked ?? 0) : null,
  };

  const railItems: RailItem[] = [
    { id: 'exposure', label: '조직 범위 노출', hint: '조용한 노출이 가장 위험', icon: 'alert',
      count: openCount.exposure || undefined, countLabel: `범위 미지정 ${openCount.exposure}건` },
    { id: 'duplicates', label: '중복 기준정보', hint: '두 기준값이 함께 주입', icon: 'duplicate',
      count: openCount.duplicates || undefined, countLabel: `확신 높은 중복 ${openCount.duplicates}건` },
    { id: 'catalog', label: '보정 목록', hint: '책임·갱신·민감도', icon: 'gap',
      count: openCount.catalog || undefined, countLabel: `보정 대상 ${openCount.catalog}건` },
    { id: 'contracts', label: '데이터 계약', hint: '확인 불가는 통과가 아니다', icon: 'contract',
      count: openCount.contracts || undefined, countLabel: `주의·위반·확인불가 ${openCount.contracts}건` },
    { id: 'external', label: '외부지표 준비도', hint: '아직 쓸 수 없는 것', icon: 'globe',
      count: openCount.external || undefined, countLabel: `차단된 지표 ${openCount.external}개` },
  ];

  // 정비를 **할 수 있는 사람**에게만 행동을 안내한다.
  const canFix = Boolean(scope?.canManageStandard || scope?.canEditOrg || scope?.unrestricted);
  const jarvisContext = {
    current_module: `governance/${view}`,
    selected_object_type: 'governance_metric',
    // ⚠️ 뷰 id(`exposure` 등)를 객체 id 로 쓰지 않는다 — 화면에 뜻 없는 영문이 나간다(실측).
    //   이 화면에는 «선택한 객체»가 없다. 없다고 말하는 것이 정확하다.
    selected_object_id: '',
    object_snapshot: { load_status: state, open: openCount[view], scope_node: scopeNode || '전체' },
    available_actions: canFix
      ? ['조직 범위 지정', '카탈로그 책임자 지정', '중복 정본 판단']
      : [],
    evidence_refs: [],
  };

  const nodeLabel = nodes.find((n) => n.node_id === scopeNode)?.label || '';
  const jarvisTitle = state === 'ok' ? MODULE[view].title
    : state === 'forbidden' ? '권한 없음' : state === 'error' ? '조회 불가' : '확인 중';
  const jarvisDesc = state === 'ok'
    ? (openCount[view]
      ? `지금 손봐야 할 것 ${openCount[view]}건${nodeLabel ? ` · ${nodeLabel} 범위` : ''}`
      : '이 항목에는 지금 손볼 것이 없습니다.')
    : state === 'forbidden'
      ? '이 지표를 볼 권한이 없습니다 — «문제 없음»이 아닙니다.'
      : state === 'error'
        ? '지표를 가져오지 못했습니다 — «문제 없음»이 아닙니다.'
        : '지표를 확인하고 있습니다.';

  /** ★★ 섹션 공통 상태 표시. «0건»과 «못 봤다»를 절대 같게 쓰지 않는다. */
  const StateNote = ({ s, what, clean }: {
    s: ReturnType<typeof worst>; what: string; clean: string;
  }) => {
    if (s === 'loading') return <div className="empty-note">{what}를 확인하고 있습니다…</div>;
    if (s === 'forbidden') {
      return (
        <Banner tone="warn" title="이 지표를 볼 권한이 없습니다">
          «{what} 없음»이 아닙니다 — <b>확인하지 못한 것</b>입니다. 전사 정비 상태는 데이터
          관리자·조직 관리자·경영진에게만 표시됩니다.
        </Banner>
      );
    }
    if (s === 'error') {
      return (
        <Banner tone="error" title={`${what}를 가져오지 못했습니다`}>
          «{what} 없음»이 아닙니다. 새로고침으로 다시 시도하십시오.
        </Banner>
      );
    }
    return <div className="empty-note">{clean}</div>;
  };

  const findingRows = useMemo(() => [
    ...gapRows.map((g) => ({
      key: `gap-${g.asset_id}-${g.kind}`, sev: g.severity,
      head: `${g.asset} · ${findingKindKo(g.kind)}`, body: g.why,
    })),
    ...docRows.map((f) => ({
      key: `doc-${f.subject}-${f.kind}`, sev: f.severity,
      head: `${f.subject} · ${findingKindKo(f.kind)}`, body: f.suggested_action,
    })),
  ], [gapRows, docRows]);

  return (
    <HubDialog label="데이터 거버넌스 — 무엇이 안 되어 있는가" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>데이터 거버넌스</b>
        <span>«없음»과 «확인하지 못함»을 구분해 표시합니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">확인 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <HubShell
          kicker={MODULE[view].kicker} title={MODULE[view].title} subtitle={MODULE[view].subtitle}
          items={railItems} activeId={view} onSelect={(id) => setView(id as View)}
          footer={
            <div className="inheritance-card">
              <span>ZERO</span>
              <b>«0건»과 «못 봤다»는 다릅니다</b>
              <p>권한이 없거나 조회가 실패하면 0건으로 쓰지 않습니다 — 그 구분이 이 화면의 전부입니다.</p>
            </div>
          }
          jarvis={<JarvisRail contextTitle={jarvisTitle} contextDescription={jarvisDesc}
            context={jarvisContext}
            evidence={state === 'ok' ? [
              { label: '보는 범위', value: nodeLabel || '전체' },
              { label: '손볼 것', value: `${openCount[view] ?? 0}건` },
            ] : []}
            quickQuestions={[
              '이 노출을 지금 막으면 무엇이 달라집니까?',
              '«확인 불가»와 «지켜짐»은 어떻게 다릅니까?',
              '어느 것부터 손대야 합니까?',
            ]} />}
        >
          <ScreenHead kicker={MODULE[view].kicker} title={MODULE[view].title}
            description={MODULE[view].desc}
            chip={state === 'loading' ? { label: '확인 중', tone: 'muted' }
              : state === 'forbidden' ? { label: '권한 없음', tone: 'danger' }
                : state === 'error' ? { label: '조회 불가', tone: 'danger' }
                  : openCount[view]
                    ? { label: `손볼 것 ${openCount[view]}건`, tone: 'warn' }
                    : { label: '지금 손볼 것 없음', tone: 'success' }} />

          {/* 이 화면은 검색이 아니라 **조직 범위**로 좁힌다 — 그래서 검색 칸을 두지 않는다. */}
          <FoundationToolbar
            actions={
              <>
                <select className="afs-select" style={{ maxWidth: 260 }}
                  aria-label="조직 범위로 좁히기"
                  value={scopeNode} onChange={(e) => setScopeNode(e.target.value)}>
                  <option value="">전체 (범위 필터 없음)</option>
                  {nodes.map((n) => (
                    <option key={n.node_id} value={n.node_id} disabled={!n.readable}>
                      {n.label}{n.readable ? '' : ' (열람 불가)'}
                    </option>
                  ))}
                </select>
                <button className="secondary-button" disabled={busy} onClick={load}>새로고침</button>
              </>
            }
            hint={nodes.length === 0
              ? '조직 범위 목록을 가져오지 못했습니다 — 전체 기준으로만 볼 수 있습니다.'
              : '범위를 고르면 그 조직 기준으로 결손을 좁혀 봅니다.'} />

          {view === 'exposure' && (
            <>
              <div className="metric-row">
                <Metric label="기준정보 전 조직 노출" state={masterCov.status}
                  value={masterCov.value?.exposed_records ?? null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '노출 없음' }}
                  hint={`전체 ${masterCov.value?.total_records ?? '—'}건 중`} />
                <Metric label="자산 범위 미지정" state={scopeCov.status}
                  value={scopeCov.value?.unscoped ?? null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '미지정 없음' }}
                  hint={`전체 ${scopeCov.value?.total ?? '—'}건 중`} />
                <Metric label="연계 시스템 범위 미지정" state={sysCov.status}
                  value={sysCov.value?.unscoped ?? null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '미지정 없음' }}
                  hint="실측값이 프롬프트에 병기됩니다" />
                <Metric label="숨겨진 미지정" state={sysCov.status}
                  value={sysCov.value?.hidden_unscoped ?? null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '없음' }}
                  hint="범위가 없어 목록에서 빠진 것" />
              </div>

              <Panel kicker="EXPOSED" title="지금 모든 조직에 보이는 것">
                {exposureState !== 'ok' ? (
                  <div style={{ padding: 14 }}>
                    <StateNote s={exposureState} what="노출 항목" clean="" />
                  </div>
                ) : exposedTotal === 0 ? (
                  <div className="empty-note">
                    범위가 지정되지 않은 항목이 없습니다 — 모든 자료에 소유 조직이 있습니다.
                  </div>
                ) : (
                  <div style={{ padding: 14 }}>
                    {!!masterCov.value?.exposed_codes.length && (
                      <div style={{ marginBottom: 12 }}>
                        <span className="field-label">기준정보</span>
                        <p className="section-text">
                          {masterCov.value.exposed_codes.slice(0, 20).join(', ')}
                          {masterCov.value.exposed_codes.length > 20
                            && ` 외 ${masterCov.value.exposed_codes.length - 20}건`}
                        </p>
                      </div>
                    )}
                    {!!sysCov.value?.unscoped_systems.length && (
                      <div>
                        <span className="field-label">연계 시스템</span>
                        <p className="section-text">
                          {sysCov.value.unscoped_systems.join(', ')}
                          {' '}— 이 시스템의 실측값은 모든 조직의 프롬프트에 병기될 수 있습니다.
                        </p>
                      </div>
                    )}
                    {!masterCov.value?.exposed_codes.length
                      && !sysCov.value?.unscoped_systems.length && (
                      <p className="hint-line">
                        집계는 노출을 가리키지만 구체 목록은 이 응답에 없습니다 — 자산 목록 화면에서
                        범위 미지정 자산을 확인하십시오.
                      </p>
                    )}
                  </div>
                )}
              </Panel>
            </>
          )}

          {view === 'duplicates' && (
            <>
              <div className="metric-row">
                <Metric label="확신 높음" state={dups.status}
                  value={dups.status === 'ok' ? highDups.length : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가' }}
                  hint="둘 다 활성이면 함께 주입됩니다" />
                <Metric label="후보 전체" state={dups.status}
                  value={dups.status === 'ok' ? dupRows.length : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가' }} />
              </div>
              <Panel kicker="DUPLICATES" title="중복 후보">
                {dups.status !== 'ok' ? (
                  <div style={{ padding: 14 }}><StateNote s={dups.status} what="중복 후보" clean="" /></div>
                ) : dupRows.length === 0 ? (
                  <div className="empty-note">중복 후보가 없습니다.</div>
                ) : (
                  <ul className="section-list" style={{ padding: 14 }}>
                    {dupRows.slice(0, 20).map((d) => (
                      <li key={d.codes.join('|')}>
                        <b>{d.codes[0]}</b> ↔ <b>{d.codes[1]}</b>
                        <span> · {findingKindKo(d.kind)} · 확신 {severityKo(d.confidence)}</span>
                        <div className="section-text">{d.suggested_action}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          )}

          {view === 'catalog' && (
            <>
              <div className="metric-row">
                <Metric label="카탈로그 결손(높음)" state={gaps.status}
                  value={gaps.status === 'ok' ? highGaps.length : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '결손 없음' }} />
                <Metric label="카탈로그 결손 전체" state={gaps.status}
                  value={gaps.status === 'ok' ? gapRows.length : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '결손 없음' }} />
                <Metric label="문서 품질 보정" state={docQ.status}
                  value={docQ.status === 'ok' ? docRows.length : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '보정 없음' }} />
              </div>
              <Panel kicker="FINDINGS" title="보정이 필요한 것">
                {catalogState !== 'ok' ? (
                  <div style={{ padding: 14 }}><StateNote s={catalogState} what="보정 목록" clean="" /></div>
                ) : findingRows.length === 0 ? (
                  <div className="empty-note">보정이 필요한 항목이 없습니다.</div>
                ) : (
                  <ul className="section-list" style={{ padding: 14 }}>
                    {findingRows.slice(0, 24).map((r) => (
                      <li key={r.key}>
                        <b>{r.head}</b><span> · 심각도 {severityKo(r.sev)}</span>
                        <div className="section-text">{r.body}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          )}

          {view === 'contracts' && (
            <>
              <div className="metric-row">
                {(['kept', 'at_risk', 'breached', 'unverifiable'] as const).map((s) => (
                  <Metric key={s} label={contractStateKo(s)} state={contracts.status}
                    value={contracts.status === 'ok'
                      ? contractRows.filter((c) => c.state === s).length : null}
                    notes={{ forbidden: '권한 없음', error: '조회 불가' }}
                    hint={s === 'unverifiable' ? '통과가 아닙니다' : undefined} />
                ))}
              </div>
              <Panel kicker="CONTRACTS" title="손봐야 할 계약">
                {contracts.status !== 'ok' ? (
                  <div style={{ padding: 14 }}>
                    <StateNote s={contracts.status} what="계약 평가" clean="" />
                  </div>
                ) : contractRows.length === 0 ? (
                  <div className="empty-note">활성 계약이 없습니다.</div>
                ) : badContracts.length + unverifiable.length === 0 ? (
                  <div className="empty-note">
                    모든 활성 계약이 지켜지고 있습니다({contractRows.length}건 확인).
                  </div>
                ) : (
                  <ul className="section-list" style={{ padding: 14 }}>
                    {[...badContracts, ...unverifiable].slice(0, 20).map((c) => (
                      <li key={c.contract_id}>
                        <b>{contractStateKo(c.state)}</b>
                        <span> · {c.consumer} · v{c.version}</span>
                        <div className="section-text">
                          {c.findings[0]?.why || c.unverifiable[0]?.why || c.note || ''}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          )}

          {view === 'external' && (
            <>
              <div className="metric-row">
                <Metric label="승인된 원천" state={ext.status}
                  value={ext.status === 'ok' ? (ext.value?.approved_sources ?? 0) : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가' }}
                  hint={ext.status === 'ok' && !ext.value?.approved_sources
                    ? '원천 승인이 먼저 필요합니다' : undefined} />
                <Metric label="기준계획 사용 가능" state={ext.status}
                  value={ext.status === 'ok' ? (ext.value?.usable_for_baseline ?? 0) : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가' }} />
                <Metric label="차단된 지표" state={ext.status}
                  value={ext.status === 'ok' ? (ext.value?.blocked ?? 0) : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '차단 없음' }} />
                <Metric label="등록된 지표" state={ext.status}
                  value={ext.status === 'ok' ? extRows.length : null}
                  notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '등록 없음' }} />
              </div>
              <Panel kicker="INDICATORS" title="지표별 준비 상태">
                {ext.status !== 'ok' ? (
                  <div style={{ padding: 14 }}>
                    <StateNote s={ext.status} what="외부지표 준비도" clean="" />
                  </div>
                ) : extRows.length === 0 ? (
                  <div className="empty-note">
                    등록된 외부지표가 없습니다 — 플레이북에서 시드하십시오.
                  </div>
                ) : (
                  <div style={{ padding: 14 }}>
                    <EvidenceStrip items={[
                      { label: '사용 가능', value: ext.value?.usable_for_baseline ?? 0 },
                      { label: '차단', value: ext.value?.blocked ?? 0 },
                      { label: '승인 원천', value: ext.value?.approved_sources ?? 0 },
                    ]} note="차단은 «값이 없다»가 아니라 «기준 계획에 쓸 수 없다»는 뜻입니다." />
                    <ul className="section-list" style={{ marginTop: 12 }}>
                      {extRows.map((i) => (
                        <li key={i.code}>
                          <b>{i.name}</b>
                          <span> · {i.code} · 필요 등급 {dataGradeKo(i.required_grade)}</span>
                          <div className="section-text">
                            {i.usable_for_baseline
                              ? '기준 계획에 사용할 수 있습니다.'
                              : (i.next_action || i.reason || '사용할 수 없습니다.')}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Panel>
            </>
          )}

          {/* 조회가 하나라도 막혔으면 화면 아래에도 그 사실을 남긴다 — 탭을 옮겨 다니다
              «어디는 봤고 어디는 못 봤는지»를 잊게 되면 «전반적으로 괜찮다»고 오해한다. */}
          {(['exposure', 'duplicates', 'catalog', 'contracts', 'external'] as View[])
            .some((v) => VIEW_STATE[v] === 'forbidden' || VIEW_STATE[v] === 'error') && (
            <Banner tone="warn" title="확인하지 못한 항목이 있습니다">
              {(['exposure', 'duplicates', 'catalog', 'contracts', 'external'] as View[])
                .filter((v) => VIEW_STATE[v] === 'forbidden' || VIEW_STATE[v] === 'error')
                .map((v) => `${MODULE[v].title}(${VIEW_STATE[v] === 'forbidden' ? '권한 없음' : '조회 실패'})`)
                .join(' · ')}
              {' '}— 이 항목들은 «문제 없음»이 아닙니다.
            </Banner>
          )}
        </HubShell>
      </div>
    </HubDialog>
  );
}
