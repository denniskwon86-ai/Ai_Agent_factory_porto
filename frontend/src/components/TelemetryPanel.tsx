// [이관 F 1/8] 운영 계기판 — LLM 호출 텔레메트리.
//
// 1순위 축은 «실제 사용 모델(used)» — 이 산출물을 어느 제공사/모델이 만들었나 = 모델 불변성 실측.
//
// ## ★★★ 이 화면에서 가장 위험한 거짓말은 «0» 이다
//
// 운영 계기판에서 「호출 0건」은 사람이 「아무 일도 안 일어났다」로 읽는다. 그런데 종전 구현은
// `.catch(() => setData(null))` 하나로 끝냈다 — **403 도, 네트워크 장애도, 서버 500 도 전부
// 「아직 기록된 LLM 호출이 없습니다」로 표시됐다.** 못 본 것을 없는 것으로 보여준 것이다.
// 이것은 이 저장소가 백엔드에서 `Metric`(값 + «읽었는가»)으로 막아 온 결함과 같은 것이며,
// 화면이 그 구분을 지우면 백엔드가 지킨 것이 소용없어진다.
//
// → 조회는 `Loaded<T>` 로 받는다. 401/403 은 «없다» 가 아니라 «못 봤다» 로 따로 담는다.
//
// ## 종전 구현에서 제거한 것
//
//   · 자체 `fixed inset-0` 모달 — `role="dialog"`·`aria-modal`·포커스 트랩·Escape·배경
//     `inert` 가 **전부 없었다.** Tab 을 누르면 보이지 않는 뒤쪽 버튼으로 포커스가 사라진다.
//     → `HubDialog`(셸이 한 번만 푼다).
//   · 실패를 삼키던 `catch` 2곳 · 10px 글자 4곳(본문 12px 이상 규칙) · Tailwind 회색 팔레트
//     직접 지정(디자인 토큰으로 모았다).
import { useCallback, useEffect, useState } from 'react';

import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import { errorTitle } from '../lib/closedLoopFetch';
import { telemetryApi, type TelemetryProject, type TelemetrySummary } from '../lib/telemetryApi';
import { QualityOutcomesView } from './QualityOutcomesView';

type View = 'llm' | 'quality';

// §10.3 은 텔레메트리를 `llm_calls` 와 `quality_outcomes` 두 축으로 규정한다. 같은 계기판에
// 두되 **한 화면에 섞지 않는다** — 「얼마 썼나」와 「통과했나」는 읽는 목적이 다르다.
const MODULE: Record<View, { kicker: string; title: string; subtitle: string; desc: string }> = {
  llm: {
    kicker: 'LLM CALLS', title: 'LLM 호출', subtitle: '무엇이 얼마나 돌았나',
    desc: '실제로 어느 모델이 산출물을 만들었는지와 그 비용을 봅니다. 단가를 모르는 호출은 '
      + '0원으로 더하지 않습니다 — 0으로 두면 「공짜였다」는 거짓이 됩니다.',
  },
  quality: {
    kicker: 'QUALITY', title: '품질 결과', subtitle: '통과했나, 왜 실패했나',
    desc: '게이트별 통과·실패와 실패 원인 분류입니다. 미분류는 결손이며 통과 쪽에 합산하지 않습니다.',
  },
};

/** 산정 근거 라벨 — **무료 0 과 «모름» 을 사람이 구분할 수 있어야 한다.** */
const BASIS_KO: Record<string, string> = {
  free_tier: '무료 티어(과금 0)', cache_hit: '캐시 적중(호출 없음)',
  paid: '유료(산정)', paid_partial: '유료(단가 일부)', unpriced: '유료·단가 미등록',
};

export function TelemetryPanel({ onClose }: { onClose: () => void }) {
  const [view, setView] = useState<View>('llm');
  const [project, setProject] = useState('');            // '' = 전역
  const [projects, setProjects] = useState<Loaded<TelemetryProject[]>>(
    loading<TelemetryProject[]>());
  const [sum, setSum] = useState<Loaded<TelemetrySummary>>(loading<TelemetrySummary>());

  /** 401/403 은 «없다» 가 아니라 «못 봤다» 다 — 상태를 구분해 담는다. */
  const asLoaded = <T,>(e: any): Loaded<T> => (
    e?.status === 403 || e?.status === 401
      ? { status: 'forbidden', value: null, error: e?.message || '볼 권한이 없습니다.',
        httpStatus: e.status }
      : failed<T>(e));

  useEffect(() => {
    let alive = true;
    telemetryApi.projects()
      .then((rows) => { if (alive) { reportRequestSuccess(); setProjects(ok(rows || [])); } })
      .catch((e) => {
        if (!alive) return;
        reportRequestFailure(e?.status);
        setProjects(asLoaded<TelemetryProject[]>(e));
      });
    return () => { alive = false; };
  }, []);

  const load = useCallback(async () => {
    setSum(loading<TelemetrySummary>());
    try {
      const d = await telemetryApi.summary(project);
      reportRequestSuccess();
      setSum(ok(d));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setSum(asLoaded<TelemetrySummary>(e));
    }
  }, [project]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const onUser = () => load();
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [load]);

  const d = sum.value;
  const t = d?.totals || ({} as TelemetrySummary['totals']);
  const perm = d?.permission || {};
  const modelEntries = Object.entries(d?.by_model || {}).sort((a, b) => b[1] - a[1]);
  const maxModel = modelEntries.length ? modelEntries[0][1] : 1;

  // 비용 표기 — 미산정이 하나라도 있으면 합계는 **하한**이므로 '≥' 를 붙인다.
  const costLabel = `${t.cost_complete === false ? '≥ ' : ''}$${(t.cost_usd || 0).toFixed(4)}`;
  const costHint = t.cost_complete === false
    ? `미산정 ${t.unpriced_calls || 0}건 (단가 미등록)`
    : (t.cost_partial_calls ? `${t.cost_partial_calls}건은 단가 일부만 등록(과소)` : '전 호출 산정됨');

  const railItems: RailItem[] = [
    { id: 'llm', label: 'LLM 호출', hint: '모델·비용·폴백', icon: 'cost' },
    { id: 'quality', label: '품질 결과', hint: '게이트·실패 원인', icon: 'checklist' },
  ];

  const headChip = sum.status === 'loading' ? { label: '확인 중', tone: 'muted' as const }
    : sum.status === 'forbidden' ? { label: '권한 없음', tone: 'danger' as const }
      : sum.status === 'error' ? { label: '조회 불가', tone: 'danger' as const }
        : { label: `호출 ${t.calls ?? 0}건`, tone: 'data' as const };

  return (
    <HubDialog label="운영 계기판 — 무엇이 얼마나 돌았고 얼마가 들었나" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>운영 계기판</b>
        <span>«0건»과 «확인하지 못함»을 구분해 표시합니다</span>
        <div className="bar-actions">
          {sum.status === 'loading' && <span className="busy">확인 중…</span>}
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
              <p>권한이 없거나 조회가 실패하면 0건으로 쓰지 않습니다. 단가를 모르는 호출도
                0원으로 더하지 않습니다.</p>
            </div>
          }
          jarvis={<JarvisRail
            contextTitle={MODULE[view].title}
            contextDescription={MODULE[view].desc}
            context={{
              current_module: `telemetry/${view}`,
              selected_object_type: 'telemetry_summary',
              // ⚠️ 이 화면에는 «선택한 객체»가 없다 — 뷰 id 를 객체 id 로 쓰면 화면에
              //   뜻 없는 영문이 나간다(거버넌스 콘솔 실측). 없다고 말하는 것이 정확하다.
              selected_object_id: '',
              object_snapshot: {
                load_status: sum.status,
                project: project || '(전역)',
                calls: t.calls ?? null,
                // ★ 비용은 «하한일 수 있다» 를 문맥에도 실어야 Jarvis 가 총액처럼 답하지 않는다.
                cost_is_lower_bound: t.cost_complete === false,
              },
              available_actions: [],
              evidence_refs: [],
            }}
            evidence={sum.status === 'ok' ? [
              { label: '집계 레코드', value: `${d?.record_count ?? 0}건` },
              { label: 'LLM 비용', value: costLabel },
              { label: '보는 범위', value: perm.scope || '미상' },
            ] : []}
            quickQuestions={[
              '비용이 «하한»이라는 것은 무슨 뜻입니까?',
              '어느 모델이 이 산출물을 만들었습니까?',
              '권한 밖으로 빠진 호출은 몇 건입니까?',
            ]} />}
        >
          <ScreenHead kicker={MODULE[view].kicker} title={MODULE[view].title}
            description={MODULE[view].desc} chip={headChip} />

          {/* 프로젝트 선택 — 조회에 실패했으면 **빈 목록으로 두지 않는다.** */}
          <Panel kicker="SCOPE" title="집계 범위">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <label htmlFor="tp-project" className="afs-muted" style={{ fontSize: 12 }}>
                프로젝트
              </label>
              <select id="tp-project" className="afs-input" value={project}
                onChange={(e) => setProject(e.target.value)}>
                <option value="">전역 (모든 프로젝트)</option>
                {(projects.value || []).map((p) => (
                  <option key={p.project} value={p.project}>
                    {p.project}{p.owner_dept_id ? ` (${p.owner_dept_id})` : ''}
                  </option>
                ))}
              </select>
              {projects.status !== 'ok' && projects.status !== 'loading' && (
                <span className="afs-muted" style={{ fontSize: 12 }}>
                  ⚠️ 프로젝트 목록을 불러오지 못했습니다 — 전역 집계만 볼 수 있습니다
                  ({errorTitle(projects.httpStatus)}).
                </span>
              )}
            </div>
          </Panel>

          {view === 'quality' ? (
            <QualityOutcomesView project={project} />
          ) : sum.status !== 'ok' ? (
            // ★ 조회 실패를 «호출이 없습니다» 로 쓰지 않는다.
            <Panel>
              <EmptyOrError state={sum.status} error={sum.error}
                emptyText="아직 기록된 LLM 호출이 없습니다. 파이프라인을 한 번 가동하면 여기 집계됩니다."
                onRetry={load} />
            </Panel>
          ) : (t.calls ?? 0) === 0 ? (
            <Panel>
              <EmptyOrError state="ok"
                emptyText="아직 기록된 LLM 호출이 없습니다. 파이프라인을 한 번 가동하면 여기 집계됩니다(원천: data/llm_call_log.jsonl)."
                onRetry={load} />
            </Panel>
          ) : (
            <>
              <Panel kicker="TOTALS" title="총계">
                <div className="metric-row">
                  <Metric label="총 호출" state={sum.status} value={t.calls} unit="건" />
                  <Metric label="성공률" state={sum.status}
                    value={Math.round((t.success_rate || 0) * 100)} unit="%" />
                  <Metric label="폴백률" state={sum.status}
                    value={Math.round((t.fallback_rate || 0) * 100)} unit="%"
                    hint={`${t.fallback_calls || 0}건`} />
                  <Metric label="Pro 강등" state={sum.status} value={t.downgraded_calls || 0}
                    unit="건" hint="브레이커 강등 호출" />
                  <Metric label="총 소요" state={sum.status} value={t.total_duration_s || 0}
                    unit="s" />
                  <Metric label="LLM 비용" state={sum.status} value={costLabel} hint={costHint} />
                </div>
              </Panel>

              {/* 비용 산정 근거 — «무료라서 0» 과 «몰라서 0» 을 구분해 보여준다 */}
              <Panel kicker="COST BASIS" title="비용 산정 근거"
                action={<span className="afs-muted" style={{ fontSize: 12 }}>
                  §10.1 승인된 결과물 1건당 비용의 기초 계측
                </span>}>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {Object.entries(d?.by_cost_basis || {}).map(([b, v]) => (
                    <div key={b} className="afs-bg-sunken afs-border"
                      style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 6,
                        padding: '8px 12px', fontSize: 13 }}>
                      <span className={b === 'unpriced' ? 'afs-warn-fg' : 'afs-ink'}>
                        {BASIS_KO[b] || b}
                      </span>
                      <span className="afs-muted"> · {v.calls}건</span>
                      {b === 'unpriced'
                        ? <span className="afs-warn-fg"> · 산정 불가</span>
                        : <span className="afs-muted"> · ${(v.cost_usd || 0).toFixed(4)}</span>}
                    </div>
                  ))}
                </div>
                {(t.unpriced_calls || 0) > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <Banner tone="warn" title="총액은 하한입니다">
                      단가가 등록되지 않은 유료 모델이 있습니다. 추정으로 메우지 않습니다 —
                      <code> config.LLM_PRICE_PER_MTOK </code>
                      에 제공사 가격을 근거와 함께 등록하면 과거 로그까지 소급 산정됩니다.
                    </Banner>
                  </div>
                )}
                {Object.keys(d?.by_provider || {}).length > 0 && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                    {Object.entries(d?.by_provider || {}).map(([pv, v]) => (
                      <span key={pv} className="afs-muted afs-bg-sunken afs-border"
                        style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 6,
                          padding: '4px 8px', fontSize: 12 }}>
                        {pv} · {v.calls}건 · ${(v.cost_usd || 0).toFixed(4)}
                      </span>
                    ))}
                  </div>
                )}
              </Panel>

              {/* 실제 사용 모델 분포 — 핵심 지표 */}
              <Panel kicker="MODELS" title="실제 사용 모델 분포"
                action={<span className="afs-muted" style={{ fontSize: 12 }}>
                  모델 불변성 실측 — 어느 모델이 산출물을 만들었나
                </span>}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {modelEntries.map(([m, n]) => (
                    <div key={m} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span className="afs-ink" title={m}
                        style={{ fontFamily: 'monospace', fontSize: 12, width: 256,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {m}
                      </span>
                      <div className="afs-bg-sunken afs-border" style={{ flex: 1, height: 20,
                        borderWidth: 1, borderStyle: 'solid', borderRadius: 4, overflow: 'hidden' }}>
                        <div className="afs-action-bg" style={{ height: '100%', display: 'flex',
                          alignItems: 'center', justifyContent: 'flex-end', paddingRight: 6,
                          width: `${Math.max(6, (n / maxModel) * 100)}%`,
                          background: 'var(--action-primary-bg)' }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>{n}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel kicker="TIERS" title="요청 티어별"
                action={<span className="afs-muted" style={{ fontSize: 12 }}>
                  강등 = Pro 원했으나 Flash 로
                </span>}>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {Object.entries(d?.by_requested_tier || {}).map(([tier, v]) => (
                    <div key={tier} className="afs-bg-sunken afs-border"
                      style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 6,
                        padding: '8px 12px', fontSize: 13 }}>
                      <span className="afs-ink" style={{ fontFamily: 'monospace' }}>{tier}</span>
                      <span className="afs-muted"> · {v.calls}건</span>
                      {v.downgraded > 0 && <span className="afs-warn-fg"> · 강등 {v.downgraded}</span>}
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel kicker="STAGES" title="단계별">
                <div className="afs-table-wrap"><table className="afs-table">
                  <thead>
                    <tr>
                      <th>단계</th><th>호출</th><th>성공</th><th>평균 소요</th><th>주 사용 모델</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(d?.by_stage || {}).map(([stage, s]) => {
                      const top = Object.entries(s.models || {})
                        .sort((a, b) => b[1] - a[1])[0];
                      return (
                        <tr key={stage}>
                          <td className="afs-ink">{stage}</td>
                          <td className="num">{s.calls}</td><td className="num">{s.ok}</td>
                          <td className="num">{s.avg_duration_s}s</td>
                          <td className="afs-muted" style={{ fontFamily: 'monospace', fontSize: 12 }}>
                            {top ? `${top[0]} (${top[1]})` : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table></div>
              </Panel>

              <p className="afs-muted" style={{ fontSize: 12 }}>
                집계 레코드 {d?.record_count ?? 0}건 · 폴백률 = 시도 2회 이상 호출 비율 ·
                토큰 {(t.total_input_tokens || 0).toLocaleString()} in
                / {(t.total_output_tokens || 0).toLocaleString()} out
                {perm.scope && <> · 권한 범위 {perm.scope}</>}
                {/* 스코프에서 빠진 건수를 밝힌다 — 조용히 빼면 집계가 작아진 줄도 모른다 */}
                {((perm.excluded_other_dept || 0) > 0 || (perm.excluded_unattributed || 0) > 0) && (
                  <span className="afs-warn-fg">
                    {' '}· 권한 밖 제외 {perm.excluded_other_dept || 0}건
                    {(perm.excluded_unattributed || 0) > 0
                      && `, 부서 귀속 불가 제외 ${perm.excluded_unattributed}건`}
                  </span>
                )}
              </p>
            </>
          )}
        </HubShell>
      </div>
    </HubDialog>
  );
}
