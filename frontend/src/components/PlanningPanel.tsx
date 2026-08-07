// [이관 F 6/8] 경영계획 · 실적 · 시나리오 (명세서 §11 / §17 첫 파일럿)
//
// ⚠️ 이 화면이 지켜야 할 단 하나: **결손을 결과처럼 보여주지 않는다.**
//   · `comparable=false`(실적 미입력)를 「차이 0」으로 그리면 「계획대로 됐다」로 읽힌다.
//   · `same_baseline=false` 인 비교는 **무효**인데, 숫자만 나란히 놓으면 유효해 보인다.
//   · `unmapped`(미등록 계정)·`unapplied_assumptions`(미적용 가정)은 합계가 맞아 보이는데
//     틀렸다는 유일한 단서다. 접어두거나 작게 쓰지 않는다.
//
// ## ★★★ 이관에서 드러난 것 — **주석이 경고한 그 결함이 실패 경로에 남아 있었다**
//
// 종전 코드 48~52행 주석:
//   「화면은 "등록된 시나리오가 없습니다" 라고 말하는데 실제로는 3건이 있었다 — 조용한 거짓말이다」
//
// 그 주석 바로 아래에서:
//   setScenarios(s.status === 'fulfilled' ? s.value : []);
//
// 즉 **조회가 실패하면 여전히 「등록된 시나리오가 없습니다」** 였다. 새로고침 누락은 고쳤지만
// 같은 거짓말의 다른 입구는 열려 있었다. 그리고 나머지 여섯 조회는 실패하면 `null` 이 되어
// **해당 구획이 통째로 사라졌다** — 사용자는 그 지표가 없는 줄 안다.
// → 전부 `Loaded<T>` 로 담고, 실패한 구획은 «확인 불가» 로 **자리를 지킨 채** 말한다.
//
// ## 종전 구현에서 제거한 것
//
//   · 자체 `fixed inset-0` 전체화면(모달 semantics·포커스 트랩·Escape 없음) → `HubDialog`
//   · **10~11px 글자 21곳** → 본문 12px 이상
//   · slate/amber 팔레트 직접 지정 → 디자인 토큰
import { useCallback, useEffect, useState } from 'react';

import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import {
  compareScenarios, fetchAccounts, fetchBacktestPlan, fetchCashFlow,
  fetchCurrentApproved, fetchRollupCheck, fetchScenarios, fetchVariance,
  type Account, type Backtest, type CashFlow, type Integrity, type RollupCheck,
  type Scenario, type ScenarioComparison, type Submission, type Variance,
} from '../lib/planningApi';

/** 없는 값은 **0 이 아니라 «—»** 다. */
const _n = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 0 });

function asLoaded<T>(e: any): Loaded<T> {
  return e?.status === 403 || e?.status === 401
    ? { status: 'forbidden', value: null, error: e?.message || '볼 권한이 없습니다.',
      httpStatus: e.status }
    : failed<T>(e);
}

/** `Promise.allSettled` 결과 하나를 `Loaded<T>` 로. **실패를 빈 값으로 바꾸지 않는다.** */
function settled<T>(r: PromiseSettledResult<T>): Loaded<T> {
  return r.status === 'fulfilled' ? ok(r.value) : asLoaded<T>(r.reason);
}

export function PlanningPanel({ onClose }: { onClose: () => void }) {
  const [orgId, setOrgId] = useState('MNM_BATTERY');
  const [period, setPeriod] = useState('2027');
  const [accounts, setAccounts] = useState<Loaded<Account[]>>(loading<Account[]>());
  const [scenarios, setScenarios] = useState<Loaded<Scenario[]>>(loading<Scenario[]>());
  const [picked, setPicked] = useState<string[]>([]);
  const [cmp, setCmp] = useState<Loaded<ScenarioComparison | null> | null>(null);
  const [vr, setVr] = useState<Loaded<Variance> | null>(null);
  const [cf, setCf] = useState<Loaded<CashFlow> | null>(null);
  const [bt, setBt] = useState<Loaded<Backtest> | null>(null);
  const [roll, setRoll] = useState<Loaded<RollupCheck> | null>(null);
  // ⚠️ 서버가 «승인본 없음» 을 `null` 로 준다 — 조회 실패(`status !== 'ok'`)와 **다른 것**이다.
  const [appr, setAppr] =
    useState<Loaded<(Submission & { integrity: Integrity }) | null> | null>(null);
  const [busy, setBusy] = useState(false);

  /** 계정·시나리오 목록. **「계산」은 «지금 상태를 다시 읽는다» 는 뜻이어야 한다.** */
  const loadLists = useCallback(async () => {
    const [a, s] = await Promise.allSettled([fetchAccounts(), fetchScenarios(orgId)]);
    if (a.status === 'fulfilled') reportRequestSuccess();
    else reportRequestFailure((a.reason as any)?.status);
    // ★★★ 종전에는 실패를 `[]` 로 바꿔 「등록된 시나리오가 없습니다」가 됐다 —
    //   이 파일 주석이 «조용한 거짓말» 이라고 부른 바로 그것이다.
    setAccounts(settled(a));
    setScenarios(settled(s));
  }, [orgId]);

  useEffect(() => { loadLists(); }, [loadLists]);

  const load = async () => {
    setBusy(true);
    await loadLists();
    const [c, v, cfR, btR, rollR, apprR] = await Promise.allSettled([
      picked.length ? compareScenarios(picked, orgId, period)
        : Promise.resolve(null as unknown as ScenarioComparison),
      fetchVariance(orgId, period),
      fetchCashFlow(orgId, period),
      fetchBacktestPlan(orgId, period),
      fetchRollupCheck(orgId, period),
      fetchCurrentApproved(orgId, period),
    ]);
    // ★ 여섯 구획을 **각각** 담는다. 종전에는 실패하면 `null` 이 되어 구획이 통째로 사라졌고,
    //   사용자는 그 지표가 «없는» 줄 알았다.
    setCmp(settled(c));
    setVr(settled(v));
    setCf(settled(cfR));
    setBt(settled(btR));
    setRoll(settled(rollR));
    setAppr(settled(apprR));
    setBusy(false);
  };

  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const rollV = roll?.value;
  const apprV = appr?.value;
  const cmpV = cmp?.value;
  const vrV = vr?.value;
  const cfV = cf?.value;
  const btV = bt?.value;

  /** 신뢰 경고를 띄울 조건. ⚠️ **못 읽은 것은 «문제 없음» 이 아니다** — 따로 말한다. */
  const distrust = rollV?.has_conflict || (apprV && apprV.integrity?.intact === false);
  const integrityUnknown = (roll && roll.status !== 'ok') || (appr && appr.status !== 'ok');

  return (
    <HubDialog label="경영계획 — 계획·실적·시나리오를 동일 기준선에서 비교" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>경영계획 · 실적 · 시나리오</b>
        <span>계산은 결정론적입니다(LLM 0콜) — 같은 입력이면 같은 결과가 나옵니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">계산 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <div className="hub-main">
          <ScreenHead kicker="PLANNING" title="계획 · 실적 · 시나리오"
            description="결손을 결과처럼 보여주지 않습니다. 실적 미입력을 「차이 0」으로 그리면 「계획대로 됐다」로 읽히고, 기준선이 다른 비교는 숫자만 나란히 놓으면 유효해 보입니다."
            chip={busy ? { label: '계산 중', tone: 'muted' }
              : distrust ? { label: '이 숫자를 그대로 쓰지 마십시오', tone: 'danger' }
                : { label: `${orgId} · ${period}`, tone: 'data' }} />

          {/* ── 조회 조건 ─────────────────────────────────────────────── */}
          <Panel kicker="SCOPE" title="조직 · 기간">
            <div className="panel-body">
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input className="afs-input" style={{ width: 180 }} value={orgId}
                  onChange={(e) => setOrgId(e.target.value)} placeholder="조직 코드" />
                <input className="afs-input" style={{ width: 160 }} value={period}
                  onChange={(e) => setPeriod(e.target.value)} placeholder="기간 (2027 / 2027-03)" />
                <button className="primary-button" onClick={load} disabled={busy}>
                  {busy ? '계산 중…' : '계산'}
                </button>
              </div>
            </div>
          </Panel>

          {/* ── ★★ 데이터 신뢰 경고 — 숫자보다 **위**에 온다 ────────────
              아래에 작게 쓰면 아무도 안 보고, 그러면 없는 것과 같다. */}
          {distrust && (
            <div style={{ marginTop: 14 }}>
              <Banner tone="error" title="⚠️ 이 숫자를 그대로 쓰면 안 됩니다">
                {apprV && apprV.integrity?.intact === false && (
                  <div style={{ marginBottom: 6 }}>
                    <b>승인 후 값이 변경되었습니다.</b> 상태는 <code>APPROVED</code>
                    ({apprV.approved_by}, {apprV.approved_at?.slice(0, 10)})이지만 승인받은
                    내용과 다릅니다 — 재승인이 필요합니다.
                    <div className="afs-muted" style={{ fontFamily: 'monospace', fontSize: 12 }}>
                      승인 시점 {apprV.integrity.approved_fingerprint} → 현재{' '}
                      {apprV.integrity.current_fingerprint}
                    </div>
                  </div>
                )}
                {rollV?.has_conflict && rollV.conflicts.map((c) => (
                  <div key={`${c.account_code}-${c.period}`} style={{ marginBottom: 4 }}>
                    <b>이중 계상 위험</b> — {c.account_code}/{c.period}: 합계 행{' '}
                    {_n(c.total_row_amount)} 과 상세 {c.detail_rows}건(합 {_n(c.detail_sum)})이
                    함께 있습니다. 단순 합산하면 <b>{_n(c.naive_sum)}</b> 이 됩니다.
                    {!c.matches && <span> (합계와 상세가 일치하지도 않습니다)</span>}
                  </div>
                ))}
                {rollV?.has_conflict && <p className="afs-muted" style={{ fontSize: 12 }}>{rollV.note}</p>}
              </Banner>
            </div>
          )}

          {/* ★ 무결성 검사 자체를 못 읽었으면 그것도 말한다 — «문제 없음» 이 아니다. */}
          {integrityUnknown && (
            <div style={{ marginTop: 14 }}>
              <Banner tone="warn" title="무결성 검사를 확인하지 못했습니다">
                승인 무결성·이중 계상 검사를 읽지 못했습니다 — <b>«문제 없음» 이라는 뜻이
                아닙니다.</b> 아래 숫자를 판단 근거로 쓰기 전에 다시 계산하십시오.
              </Banner>
            </div>
          )}

          {/* ── 승인 상태 ─────────────────────────────────────────────── */}
          {appr && appr.status === 'ok' && apprV && apprV.integrity?.intact !== false && (
            <div style={{ marginTop: 14 }}>
              <Panel kicker="APPROVAL" title="승인 상태">
                <div className="panel-body">
                  <p className="afs-success-fg" style={{ fontSize: 13 }}>
                    ✅ {apprV.approved_by} 승인 ({apprV.approved_at?.slice(0, 10)}) ·
                    승인 시점 값과 동일합니다
                    <span className="afs-muted" style={{ fontFamily: 'monospace' }}>
                      {' '}[{apprV.integrity.approved_fingerprint}]
                    </span>
                  </p>
                </div>
              </Panel>
            </div>
          )}

          {/* ── 시나리오 선택 ─────────────────────────────────────────── */}
          <div style={{ marginTop: 14 }}>
            <Panel kicker="SCENARIOS" title="시나리오 선택"
              action={<span className="afs-muted" style={{ fontSize: 12 }}>
                동일 기준선에서 비교합니다(§17.3)
              </span>}>
              <div className="panel-body">
                {scenarios.status !== 'ok' ? (
                  // ★★★ 이 파일 주석이 «조용한 거짓말» 이라 부른 바로 그 자리다.
                  <EmptyOrError state={scenarios.status} error={scenarios.error}
                    emptyText="등록된 시나리오가 없습니다." onRetry={loadLists} />
                ) : (scenarios.value || []).length === 0 ? (
                  <p className="afs-muted" style={{ fontSize: 13 }}>등록된 시나리오가 없습니다.</p>
                ) : (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {(scenarios.value || []).map((s) => (
                      <button key={s.scenario_id} onClick={() => toggle(s.scenario_id)}
                        className={picked.includes(s.scenario_id)
                          ? 'primary-button' : 'secondary-button'}>
                        {s.name}{' '}
                        <span style={{ opacity: .7 }}>({s.scenario_id})</span>
                      </button>
                    ))}
                  </div>
                )}
                <p className="afs-muted" style={{ fontSize: 12 }}>
                  {accounts.status === 'ok'
                    ? `계정 ${(accounts.value || []).length}개 등록됨`
                    : '계정 목록을 확인하지 못했습니다 — «0개» 가 아닙니다.'}
                </p>
              </div>
            </Panel>
          </div>

          {/* ── 시나리오 비교 ─────────────────────────────────────────── */}
          {cmp && (picked.length > 0 || cmp.status !== 'ok') && (
            <div style={{ marginTop: 14 }}>
              <Panel kicker="COMPARE" title="시나리오 비교">
                <div className="panel-body">
                  {cmp.status !== 'ok' ? (
                    <EmptyOrError state={cmp.status} error={cmp.error}
                      emptyText="비교할 시나리오를 선택하십시오." onRetry={load} />
                  ) : !cmpV ? (
                    <p className="afs-muted" style={{ fontSize: 13 }}>
                      비교할 시나리오를 선택하고 「계산」을 누르십시오.
                    </p>
                  ) : (
                    <>
                      {/* ★ 기준선이 다르면 그 비교는 무효다 — 숫자보다 먼저 말한다 */}
                      {!cmpV.same_baseline && (
                        <Banner tone="error" title="서로 다른 기준선에서 계산되었습니다">
                          <b>이 비교는 무효입니다.</b> 같은 기준선으로 다시 실행하십시오.
                        </Banner>
                      )}
                      <div className="afs-table-wrap">
                        <table className="afs-table">
                          <thead>
                            <tr>
                              <th>시나리오</th><th>영업이익</th><th>당기순이익</th>
                              <th>기준선 대비</th><th>입력 지문</th><th>경고</th>
                            </tr>
                          </thead>
                          <tbody>
                            {cmpV.scenarios.map((s) => (
                              <tr key={s.scenario_id}>
                                <td>{s.scenario_id}</td>
                                <td className="num">{_n(s.operating_profit)}</td>
                                <td className="num"><b>{_n(s.net_profit)}</b></td>
                                <td className={`num ${s.delta_net >= 0 ? 'afs-success-fg' : 'afs-danger-fg'}`}>
                                  {s.delta_net >= 0 ? '+' : ''}{_n(s.delta_net)}
                                </td>
                                {/* 재현성의 근거 — 같은 지문이면 같은 입력이다 */}
                                <td className="afs-muted" style={{ fontFamily: 'monospace', fontSize: 12 }}>
                                  {s.input_hash}
                                </td>
                                <td style={{ fontSize: 12 }}>
                                  {!s.complete && <span className="afs-warn-fg">미등록 계정 있음 </span>}
                                  {s.unapplied_assumptions.length > 0 && (
                                    <span className="afs-warn-fg">
                                      미적용 가정 {s.unapplied_assumptions.length}
                                    </span>
                                  )}
                                  {s.complete && s.unapplied_assumptions.length === 0 && (
                                    <span className="afs-muted">—</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="afs-muted" style={{ fontSize: 12 }}>
                        엔진 {cmpV.engine_version} · 기준선 {cmpV.baseline_kind} ·
                        같은 지문 = 같은 입력. 「미적용 가정」이 있으면 의도한 가정이 전부
                        반영되지 않았습니다.
                      </p>
                    </>
                  )}
                </div>
              </Panel>
            </div>
          )}

          {/* ── 계획 대비 실적 ─────────────────────────────────────────── */}
          {vr && (
            <div style={{ marginTop: 14 }}>
              <Panel kicker="VARIANCE" title="계획 대비 실적 (차이 분석)">
                <div className="panel-body">
                  {vr.status !== 'ok' ? (
                    <EmptyOrError state={vr.status} error={vr.error}
                      emptyText="차이 분석 결과가 없습니다." onRetry={load} />
                  ) : !vrV!.comparable ? (
                    /* ★★ 실적 미입력을 「차이 0」으로 그리면 「계획대로 됐다」로 읽힌다 */
                    <Banner tone="warn" title="차이를 계산하지 않았습니다">
                      {vrV!.reason}
                      <div className="afs-muted">{vrV!.note}</div>
                    </Banner>
                  ) : (
                    <>
                      <div className="metric-row">
                        <div><span>계획 영업이익</span><b>{_n(vrV!.plan?.operating_profit)}</b><small /></div>
                        <div><span>실적 영업이익</span><b>{_n(vrV!.actual?.operating_profit)}</b><small /></div>
                        <div><span>차이</span>
                          <b className={(vrV!.diff?.operating_profit ?? 0) >= 0
                            ? 'afs-success-fg' : 'afs-danger-fg'}>
                            {_n(vrV!.diff?.operating_profit)}
                          </b><small /></div>
                      </div>
                      <div className="afs-table-wrap">
                        <table className="afs-table">
                          <thead>
                            <tr><th>계정</th><th>계획</th><th>실적</th><th>차이</th></tr>
                          </thead>
                          <tbody>
                            {(vrV!.by_account || []).map((r) => (
                              <tr key={r.account_code}>
                                <td>{r.account_code}</td>
                                <td className="num">{_n(r.plan)}</td>
                                <td className="num">{_n(r.actual)}</td>
                                {/* 없는 값은 0 이 아니라 «미입력» 이다 */}
                                <td className={r.diff === null ? 'afs-warn-fg' : 'num'}>
                                  {r.diff === null
                                    ? (r.missing === 'actual' ? '실적 미입력' : '계획 없음')
                                    : _n(r.diff)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              </Panel>
            </div>
          )}

          {/* ── 현금흐름 — 계산 못 한 것을 0 으로 그리지 않는다 ──────────── */}
          {cf && (
            <div style={{ marginTop: 14 }}>
              <Panel kicker="CASH FLOW" title="현금흐름 (간접법)">
                <div className="panel-body">
                  {cf.status !== 'ok' ? (
                    <EmptyOrError state={cf.status} error={cf.error}
                      emptyText="현금흐름 결과가 없습니다." onRetry={load} />
                  ) : !cfV!.computable ? (
                    <Banner tone="warn" title="계산하지 않았습니다">
                      필요한 항목이 없습니다: <code>{(cfV!.missing || []).join(', ')}</code>
                      <div className="afs-muted">{cfV!.note}</div>
                    </Banner>
                  ) : (
                    <>
                      <div className="metric-row">
                        <div><span>영업</span><b>{_n(cfV!.operating_cf)}</b><small /></div>
                        <div><span>투자</span><b>{_n(cfV!.investing_cf)}</b><small /></div>
                        <div><span>재무</span><b>{_n(cfV!.financing_cf)}</b><small /></div>
                        <div><span>FCF</span>
                          <b className={(cfV!.free_cash_flow ?? 0) >= 0
                            ? 'afs-success-fg' : 'afs-danger-fg'}>
                            {_n(cfV!.free_cash_flow)}
                          </b><small /></div>
                      </div>
                      {cfV!.pl_complete === false && (
                        <Banner tone="warn" title="이 현금흐름도 그만큼 불완전합니다">
                          손익에 미등록 계정이 있습니다.
                        </Banner>
                      )}
                    </>
                  )}
                </div>
              </Panel>
            </div>
          )}

          {/* ── Backtest — 오차를 액면 그대로 믿게 두지 않는다 ─────────── */}
          {bt && (
            <div style={{ marginTop: 14 }}>
              <Panel kicker="BACKTEST" title="Backtest"
                action={<span className="afs-muted" style={{ fontSize: 12 }}>
                  계획 vs 실적 오차
                </span>}>
                <div className="panel-body">
                  {bt.status !== 'ok' ? (
                    <EmptyOrError state={bt.status} error={bt.error}
                      emptyText="Backtest 결과가 없습니다." onRetry={load} />
                  ) : !btV!.measurable ? (
                    <p className="afs-muted" style={{ fontSize: 13 }}>
                      재지 않았습니다 — {btV!.reason}. {btV!.note}
                    </p>
                  ) : (
                    <>
                      {btV!.lookahead_risk && (
                        <Banner tone="error" title="미래 정보 누설 가능성">
                          가정이 대상 기간 이후에 작성되었습니다 —
                          이 오차는 <b>실제 예측력이 아닙니다.</b>
                        </Banner>
                      )}
                      <div className="metric-row">
                        <div><span>MAPE</span><b>{btV!.mape ?? '—'}%</b><small /></div>
                        <div><span>편향(bias)</span>
                          <b className={(btV!.bias ?? 0) > 0 ? 'afs-warn-fg' : undefined}>
                            {btV!.bias === null || btV!.bias === undefined ? '—'
                              : `${btV!.bias > 0 ? '+' : ''}${btV!.bias}%`}
                          </b>
                          <small>{(btV!.bias ?? 0) > 0 ? '과대추정 경향'
                            : (btV!.bias ?? 0) < 0 ? '과소추정 경향' : ''}</small></div>
                        {btV!.worst && (
                          <div><span>최악 계정</span><b>{btV!.worst.account_code}</b>
                            <small>{btV!.worst.pct_error}%</small></div>
                        )}
                      </div>
                      {(btV!.excluded_zero_actual?.length || btV!.only_predicted?.length
                        || btV!.only_actual?.length) ? (
                          <p className="afs-warn-fg" style={{ fontSize: 12 }}>
                            {btV!.excluded_zero_actual?.length
                              ? `실적 0 이라 백분율에서 제외: ${btV!.excluded_zero_actual.join(', ')} · ` : ''}
                            {btV!.only_predicted?.length
                              ? `계획에만 있음: ${btV!.only_predicted.join(', ')} · ` : ''}
                            {btV!.only_actual?.length
                              ? `실적에만 있음: ${btV!.only_actual.join(', ')}` : ''}
                          </p>
                        ) : null}
                      <p className="afs-muted" style={{ fontSize: 12 }}>
                        MAPE 하나만 보지 마십시오 — 늘 한쪽으로 치우친 모델은 절대오차가 작아도
                        위험합니다.
                      </p>
                    </>
                  )}
                </div>
              </Panel>
            </div>
          )}

          {!cmp && !vr && !busy && (
            <p className="afs-muted" style={{ fontSize: 13, marginTop: 14 }}>
              조직·기간을 입력하고 「계산」을 누르십시오. 시나리오를 선택하면 함께 비교합니다.
            </p>
          )}
        </div>
      </div>
    </HubDialog>
  );
}
