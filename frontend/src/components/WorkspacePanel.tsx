// [이관 F 5/8] 부서 워크스페이스 — 공유 · 복제 · 전사 승격 (명세서 §9 / §14 M3)
//
// 이 화면의 목적은 «승격 버튼» 이 아니라 **왜 막혔는지 보여주는 것**이다.
// 게이트가 막았는데 이유를 못 보면 사용자는 우회로를 찾거나 포기한다. 둘 다 나쁘다.
//   ① 5개 검사 항목의 상태와 **다음 조치**를 그대로 노출한다
//   ② `unverifiable` 을 `pass` 와 다른 색으로 둔다 — 확인 못 한 것은 통과가 아니다
//   ③ 통과하지 못하면 승격 버튼이 잠긴다(백엔드가 어차피 409 지만, 누르기 전에 알아야 한다)
//   ④ 공유와 승격을 화면에서도 분리한다 — 묶어 보이면 같은 행위로 오해한다
//
// ## ★★★ 이관에서 드러난 것 — 조회 실패가 «공유 없음»·«복제 없음» 이었다
//
//   setShares(s.status === 'fulfilled' ? s.value : []);
//   setForks(f.status === 'fulfilled' ? f.value : []);
//
// 403 이든 500 이든 **빈 배열**이 됐고, 화면에는 「공유 없음」·「복제 없음」이 찍혔다.
// 이 화면에서 그것은 「이 릴리스는 아무 데도 안 나갔다」로 읽힌다 — 실제로는 여러 부서가
// 쓰고 있을 수 있고, 그 상태로 롤백하면 끊기는 쪽이 원인을 모른다.
// → 각 목록을 `Loaded<T>` 로 담는다.
//
// ## 새로 막은 것
//
//   · **전사 승격·롤백·공유 회수에 확인이 없었다.** 승격은 회수해도 이미 본 사람이 있고,
//     롤백은 운영에서 내리는 행동이며, 회수는 남의 부서 접근을 끊는다. 전부 ConfirmInline.
//   · **반려 사유가 하드코딩(`'검토 결과 보류'`)이었다.** 신청자는 무엇을 고쳐야 하는지
//     영영 알 수 없다 — 입력으로 받는다.
//
// ## 종전 구현에서 제거한 것
//
//   · 자체 `fixed inset-0` 전체화면(모달 semantics·포커스 트랩·Escape 없음) → `HubDialog`
//   · `String(e)` 를 그대로 찍어 «Error: ...» 가 노출되던 것
//   · **10~11px 글자 16곳** → 본문 12px 이상
import { useCallback, useEffect, useState } from 'react';

import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import type {
  Checklist, ChecklistStep, Fork, Gate, GateCheck, Promotion, RollbackResult, Share,
} from '../lib/workspaceApi';
import {
  createShare, fetchChecklist, fetchForks, fetchGate, fetchPromotions, fetchShares,
  ownerApprove, promoteRelease, rejectPromotion, requestPromotion, revokeShare,
  rollbackRelease,
} from '../lib/workspaceApi';

type Props = { onClose: () => void };

/** ★ 통과와 같은 톤이면 «확인 못 한 것» 이 «괜찮은 것» 으로 읽힌다. */
const STATE: Record<string, { label: string; cls: string }> = {
  pass: { label: '통과', cls: 'afs-success-fg' },
  fail: { label: '차단', cls: 'afs-danger-fg' },
  unverifiable: { label: '확인 불가(통과 아님)', cls: 'afs-mega-fg' },
};

const CHECK_LABEL: Record<string, string> = {
  asset_linkage: '사용 자산 연결',
  data_contract: '데이터 계약',
  security: '보안(민감도·PII)',
  quality: '품질 게이트',
  data_owner_approval: '데이터 오너 승인',
};

const STEP_STATE: Record<string, { label: string; cls: string }> = {
  pass: { label: '통과', cls: 'afs-success-fg' },
  fail: { label: '차단', cls: 'afs-danger-fg' },
  unverifiable: { label: '확인 불가(통과 아님)', cls: 'afs-mega-fg' },
  // ★ «해당 없음» 을 통과와 같은 색으로 두면 검사한 것처럼 읽힌다.
  not_required: { label: '해당 없음(§8.2)', cls: 'afs-muted' },
};

const STEP_LABEL: Record<string, string> = {
  artifacts: '① 코드·문서·스키마',
  traceability: '② 요구사항 추적성',
  tests: '③ 핵심 업무 테스트',
  permission_contract: '④ 권한·데이터 계약',
  acceptance: '⑤ 사용자 수용검수',
  shadow_mode: '⑥ Shadow Mode',
  release_approval: '⑦ 릴리스 승인',
};

const PROMO: Record<string, { label: string; tone: string }> = {
  draft: { label: '초안', tone: 'muted' },
  requested: { label: '신청됨', tone: 'warn' },
  approved: { label: '오너 승인', tone: 'data' },
  rejected: { label: '반려', tone: 'danger' },
  promoted: { label: '전사 승격', tone: 'success' },
};

function asLoaded<T>(e: any): Loaded<T> {
  return e?.status === 403 || e?.status === 401
    ? { status: 'forbidden', value: null, error: e?.message || '볼 권한이 없습니다.',
      httpStatus: e.status }
    : failed<T>(e);
}

export default function WorkspacePanel({ onClose }: Props) {
  const [promotions, setPromotions] = useState<Loaded<Promotion[]>>(loading<Promotion[]>());
  const [releaseId, setReleaseId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [fromScope, setFromScope] = useState('');
  const [gate, setGate] = useState<Loaded<Gate> | null>(null);
  const [shares, setShares] = useState<Loaded<Share[]>>(loading<Share[]>());
  const [forks, setForks] = useState<Loaded<Fork[]>>(loading<Fork[]>());
  const [toScope, setToScope] = useState('');
  const [checklist, setChecklist] = useState<Loaded<Checklist>>(loading<Checklist>());
  const [liveIntegration, setLiveIntegration] = useState(false);
  const [rollbackReason, setRollbackReason] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [rollbackOut, setRollbackOut] = useState<RollbackResult | null>(null);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  // ⚠️ 되돌리기 어렵거나 남에게 영향을 주는 행동은 화면 안에서 한 번 확인한다.
  const confirmPromote = useConfirm<true>();
  const confirmRollback = useConfirm<true>();
  const confirmReject = useConfirm<true>();
  const confirmRevoke = useConfirm<Share>();

  const loadList = useCallback(async () => {
    setPromotions(loading<Promotion[]>());
    try {
      const rows = await fetchPromotions();
      reportRequestSuccess();
      setPromotions(ok(rows || []));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setPromotions(asLoaded<Promotion[]>(e));
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  const inspect = useCallback(async (rid: string, pid = '', live = liveIntegration) => {
    if (!rid.trim()) { setErr('release_id 를 입력하십시오.'); return; }
    setErr(''); setMsg('');
    setReleaseId(rid); setProjectId(pid);
    setRollbackOut(null);
    setGate(loading<Gate>());
    setShares(loading<Share[]>());
    setForks(loading<Fork[]>());
    setChecklist(loading<Checklist>());
    const [g, s, f, c] = await Promise.allSettled([
      fetchGate(rid, pid), fetchShares(rid), fetchForks(rid), fetchChecklist(rid, pid, live),
    ]);
    // ★★★ 넷을 **각각** 담는다. 종전에는 실패를 전부 «빈 배열/ null» 로 바꿨다.
    setGate(g.status === 'fulfilled' ? ok(g.value) : asLoaded<Gate>(g.reason));
    setShares(s.status === 'fulfilled' ? ok(s.value || []) : asLoaded<Share[]>(s.reason));
    setForks(f.status === 'fulfilled' ? ok(f.value || []) : asLoaded<Fork[]>(f.reason));
    setChecklist(c.status === 'fulfilled' ? ok(c.value) : asLoaded<Checklist>(c.reason));
  }, [liveIntegration]);

  const act = async (fn: () => Promise<unknown>, okMsg: string) => {
    setMsg(''); setErr('');
    try {
      await fn();
      setMsg(okMsg);
      await inspect(releaseId, projectId);
      loadList();
    } catch (e: any) {
      // 백엔드 거절 사유를 그대로 — 요약하면 무엇을 고쳐야 할지가 사라진다.
      setErr(e?.message || '요청이 거절됐습니다.');
    }
  };

  const g = gate?.value;
  const cl = checklist.value;
  const current = (promotions.value || []).find((p) => p.release_id === releaseId);

  return (
    <HubDialog label="부서 워크스페이스 — 공유·복제·전사 승격" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>부서 워크스페이스</b>
        <span>공유는 승격이 아닙니다 · 전사 승격은 데이터 계약·보안·품질·소유자 승인을 모두 통과해야 합니다(§9.3)</span>
        <div className="bar-actions">
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <div className="hub-main">
          <ScreenHead kicker="WORKSPACE" title="공유 · 복제 · 전사 승격"
            description="이 화면의 목적은 승격 버튼이 아니라 «왜 막혔는지»입니다. 확인하지 못한 항목은 통과가 아니며 승격을 막습니다."
            chip={gate?.status === 'ok'
              ? { label: g!.promotable ? '게이트 통과' : '게이트 차단',
                tone: g!.promotable ? 'success' : 'danger' }
              : { label: '릴리스를 점검하십시오', tone: 'muted' }} />

          {err && (
            <div style={{ marginBottom: 12 }}>
              <Banner tone="error" title="진행하지 못했습니다">
                <span style={{ whiteSpace: 'pre-wrap' }}>{err}</span>
              </Banner>
            </div>
          )}
          {msg && <div style={{ marginBottom: 12 }}><Banner tone="info">{msg}</Banner></div>}

          {/* ── 조회 ─────────────────────────────────────────────────── */}
          <Panel kicker="INSPECT" title="릴리스 점검">
            <div className="panel-body">
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <input className="afs-input" style={{ flex: 1, minWidth: 220 }} value={releaseId}
                  onChange={(e) => setReleaseId(e.target.value)} placeholder="release_id" />
                <input className="afs-input" style={{ flex: 1, minWidth: 200 }} value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  placeholder="project_id (품질 기록 조회 키)" />
                <button className="primary-button"
                  onClick={() => inspect(releaseId, projectId)}>게이트 점검</button>
              </div>
              {promotions.status !== 'ok' ? (
                // ★ 신청 목록을 못 읽었으면 «신청이 없다» 로 보이지 않게 한다.
                <EmptyOrError state={promotions.status} error={promotions.error}
                  emptyText="승격 신청 기록이 없습니다." onRetry={loadList} />
              ) : (promotions.value || []).length > 0 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {(promotions.value || []).map((p) => (
                    <button key={p.promotion_id} className="secondary-button"
                      onClick={() => inspect(p.release_id, p.project_id)}>
                      {p.release_id}{' '}
                      <span className={`state-chip ${PROMO[p.status]?.tone || 'muted'}`}>
                        {PROMO[p.status]?.label || p.status}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </Panel>

          {gate && (
            <>
              {/* ── ① 게이트 — 왜 막혔는지가 이 화면의 목적이다 ──────── */}
              <div style={{ marginTop: 14 }}>
                <Panel kicker="GATE" title="전사 승격 게이트 (§9.3)"
                  action={gate.status === 'ok' && (
                    <span className="afs-muted" style={{ fontSize: 12 }}>
                      사용 자산 {g!.linked_assets.length}건
                    </span>)}>
                  <div className="panel-body">
                    {gate.status !== 'ok' ? (
                      <EmptyOrError state={gate.status} error={gate.error}
                        emptyText="게이트 판정을 받지 못했습니다."
                        onRetry={() => inspect(releaseId, projectId)} />
                    ) : (
                      <>
                        {g!.checks.map((c: GateCheck) => (
                          <div key={c.check} className="afs-border"
                            style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                              padding: '8px 10px', fontSize: 13 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <b className={STATE[c.state]?.cls}>[{STATE[c.state]?.label}]</b>
                              <b>{CHECK_LABEL[c.check] || c.check}</b>
                            </div>
                            <div className="afs-ink">{c.why}</div>
                            {/* 막혔으면 무엇을 해야 하는지가 반드시 보여야 한다 */}
                            {c.state !== 'pass' && c.suggested_action && (
                              <div className="afs-warn-fg">→ {c.suggested_action}</div>
                            )}
                          </div>
                        ))}
                        <p className="afs-muted" style={{ fontSize: 12 }}>{g!.note}</p>

                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          <button className="secondary-button"
                            onClick={() => act(() => requestPromotion({
                              release_id: releaseId, from_scope: fromScope || 'unknown',
                              project_id: projectId,
                            }), '승격을 신청했습니다.')}>승격 신청</button>
                          <button className="secondary-button"
                            onClick={() => act(() => ownerApprove(releaseId),
                              '데이터 오너가 승인했습니다.')}>데이터 오너 승인</button>
                          <button className="secondary-button"
                            onClick={() => confirmReject.ask(true)}>반려</button>
                          {/* ③ 통과 못 하면 잠근다 — 백엔드가 409 를 주지만 누르기 전에 알아야 한다 */}
                          <button className="primary-button" disabled={!g!.promotable}
                            onClick={() => confirmPromote.ask(true)}>전사 승격</button>
                        </div>

                        {/* ★ 반려 사유가 하드코딩('검토 결과 보류')이었다 — 신청자는 무엇을
                            고쳐야 하는지 영영 알 수 없었다. */}
                        <ConfirmInline open={confirmReject.open} title="이 승격 신청을 반려합니다"
                          body={<>
                            <label htmlFor="ws-reject" style={{ display: 'block', marginBottom: 4 }}>
                              반려 사유 — <b>신청자가 무엇을 고쳐야 하는지</b> 이 문장으로만 압니다.
                            </label>
                            <input id="ws-reject" className="afs-input" style={{ width: '100%' }}
                              value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
                              placeholder="예: 데이터 계약에 PII 항목이 선언되지 않았습니다" />
                          </>}
                          confirmLabel="반려"
                          onCancel={() => { confirmReject.cancel(); setRejectReason(''); }}
                          onConfirm={() => confirmReject.run(() => {
                            act(() => rejectPromotion(releaseId,
                              rejectReason.trim() || '(사유 미기재)'), '반려했습니다.');
                            setRejectReason('');
                          })} />

                        <ConfirmInline open={confirmPromote.open}
                          title="이 릴리스를 전사에 승격합니다"
                          body={<>
                            승격되면 <b>전 조직이 이 프로그램을 볼 수 있습니다.</b> 되돌려도
                            이미 본 사람이 있습니다. 승격 시점의 게이트 판정이 스냅샷으로
                            보관됩니다.
                          </>}
                          confirmLabel="전사 승격"
                          onCancel={confirmPromote.cancel}
                          onConfirm={() => confirmPromote.run(() => act(
                            () => promoteRelease(releaseId), '전사 승격했습니다.'))} />

                        {current?.status === 'promoted' && (
                          <p className="afs-success-fg" style={{ fontSize: 13 }}>
                            전사 승격됨 · {current.promoted_by} · 승격 시점 게이트 판정이
                            스냅샷으로 보관됩니다.
                          </p>
                        )}
                        {current?.rejected_reason && (
                          <p className="afs-danger-fg" style={{ fontSize: 13 }}>
                            반려: {current.rejected_reason}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </Panel>
              </div>

              {/* ── 운영 준비 (§8.2) ─────────────────────────────────── */}
              <div style={{ marginTop: 14 }}>
                <Panel kicker="OPERATIONS" title="운영 준비 체크리스트 (§8.2)"
                  action={
                    <label className="afs-ink" style={{ display: 'flex', alignItems: 'center',
                      gap: 6, fontSize: 13 }}>
                      <input type="checkbox" checked={liveIntegration}
                        onChange={(e) => {
                          setLiveIntegration(e.target.checked);
                          inspect(releaseId, projectId, e.target.checked);
                        }} />
                      실운영 연계형 (Shadow Mode 요구)
                    </label>}>
                  <div className="panel-body">
                    {checklist.status !== 'ok' ? (
                      <EmptyOrError state={checklist.status} error={checklist.error}
                        emptyText="체크리스트가 없습니다."
                        onRetry={() => inspect(releaseId, projectId)} />
                    ) : (
                      <>
                        <p className={cl!.operations_ready ? 'afs-success-fg' : 'afs-danger-fg'}
                          style={{ fontSize: 13 }}>
                          <b>{cl!.operations_ready ? '준비됨' : '미준비'}</b>
                        </p>
                        {cl!.steps.map((s2: ChecklistStep) => (
                          <div key={s2.step} className="afs-border"
                            style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                              padding: '8px 10px', fontSize: 13 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <b className={STEP_STATE[s2.state]?.cls}>
                                [{STEP_STATE[s2.state]?.label}]
                              </b>
                              <b>{STEP_LABEL[s2.step] || s2.step}</b>
                            </div>
                            <div className="afs-ink">{s2.why}</div>
                            {s2.state !== 'pass' && s2.state !== 'not_required'
                              && s2.suggested_action && (
                              <div className="afs-warn-fg">→ {s2.suggested_action}</div>
                            )}
                          </div>
                        ))}
                        <p className="afs-muted" style={{ fontSize: 12 }}>{cl!.note}</p>
                      </>
                    )}

                    {/* 롤백 — 한계를 반드시 함께 보여준다 */}
                    <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
                      <h4 style={{ fontSize: 13, fontWeight: 800 }}>운영에서 내리기(롤백)</h4>
                      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <input className="afs-input" style={{ flex: 1 }} value={rollbackReason}
                          onChange={(e) => setRollbackReason(e.target.value)}
                          placeholder="사유 (필수 — 없으면 같은 문제를 반복합니다)" />
                        <button className="danger-solid"
                          onClick={() => confirmRollback.ask(true)}>롤백</button>
                      </div>
                      <ConfirmInline open={confirmRollback.open}
                        title="이 릴리스를 운영에서 내립니다"
                        body={<>
                          쓰고 있는 쪽은 <b>즉시</b> 막힙니다. 전사 승격 상태였다면 함께
                          철회됩니다.
                          {!rollbackReason.trim() && <><br />⚠️ 사유가 비어 있습니다 — 사유가
                            없으면 같은 문제를 반복합니다.</>}
                        </>}
                        confirmLabel="롤백"
                        onCancel={confirmRollback.cancel}
                        onConfirm={() => confirmRollback.run(async () => {
                          setMsg(''); setErr('');
                          try {
                            setRollbackOut(await rollbackRelease(releaseId, rollbackReason));
                            setMsg('롤백을 기록했습니다.');
                            await inspect(releaseId, projectId);
                            loadList();
                          } catch (e: any) {
                            setErr(e?.message || '롤백하지 못했습니다.');
                          }
                        })} />
                      {rollbackOut && (
                        <Banner tone="warn" title="롤백의 한계">
                          {rollbackOut.revoked_promotion ? '전사 승격을 철회했습니다. ' : ''}
                          {rollbackOut.limitation}
                        </Banner>
                      )}
                    </div>
                  </div>
                </Panel>
              </div>

              {/* ── ④ 공유는 승격과 분리해서 보여준다 ─────────────────── */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
                gap: 14, marginTop: 14, alignItems: 'start' }}>
                <Panel kicker="SHARE" title="부서 공유"
                  action={<span className="afs-muted" style={{ fontSize: 12 }}>승격이 아닙니다</span>}>
                  <div className="panel-body">
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <input className="afs-input" style={{ flex: 1, minWidth: 120 }}
                        value={fromScope} onChange={(e) => setFromScope(e.target.value)}
                        placeholder="소유 조직" />
                      <input className="afs-input" style={{ flex: 1, minWidth: 120 }}
                        value={toScope} onChange={(e) => setToScope(e.target.value)}
                        placeholder="공유 대상 조직" />
                      <button className="secondary-button"
                        onClick={() => act(() => createShare({
                          release_id: releaseId, from_scope: fromScope, to_scope: toScope,
                        }), '공유했습니다.')}>공유</button>
                    </div>
                    {shares.status !== 'ok' ? (
                      // ★★★ 종전에는 여기가 «공유 없음» 이었다 — 여러 부서가 쓰고 있어도.
                      <EmptyOrError state={shares.status} error={shares.error}
                        emptyText="공유 없음" onRetry={() => inspect(releaseId, projectId)} />
                    ) : (shares.value || []).length === 0 ? (
                      <p className="afs-muted" style={{ fontSize: 13 }}>공유 없음</p>
                    ) : (
                      (shares.value || []).map((s) => (
                        <div key={s.share_id} className="afs-border"
                          style={{ display: 'flex', alignItems: 'center',
                            justifyContent: 'space-between', gap: 8, borderWidth: 1,
                            borderStyle: 'solid', borderRadius: 8, padding: '6px 10px',
                            fontSize: 13 }}>
                          <span>{s.to_scope} · {s.mode}</span>
                          <button className="secondary-button"
                            onClick={() => confirmRevoke.ask(s)}>회수</button>
                        </div>
                      ))
                    )}
                    <ConfirmInline open={confirmRevoke.open} title="이 공유를 회수합니다"
                      body={<>
                        <b>{confirmRevoke.target?.to_scope}</b> 의 접근이 끊깁니다 — 지금 쓰고
                        있다면 그쪽은 원인을 모른 채 막힙니다.
                      </>}
                      confirmLabel="회수"
                      onCancel={confirmRevoke.cancel}
                      onConfirm={() => confirmRevoke.run((t) => act(
                        () => revokeShare(t.share_id), '회수했습니다.'))} />
                  </div>
                </Panel>

                <Panel kicker="FORKS" title="복제(포크) 계보">
                  <div className="panel-body">
                    <p className="afs-muted" style={{ fontSize: 13 }}>
                      원본이 바뀌면 아래 프로젝트가 영향을 받습니다.
                    </p>
                    {forks.status !== 'ok' ? (
                      // ★★★ 종전에는 «복제 없음» — 영향받는 프로젝트가 있어도 안 보였다.
                      <EmptyOrError state={forks.status} error={forks.error}
                        emptyText="복제 없음" onRetry={() => inspect(releaseId, projectId)} />
                    ) : (forks.value || []).length === 0 ? (
                      <p className="afs-muted" style={{ fontSize: 13 }}>복제 없음</p>
                    ) : (
                      (forks.value || []).map((f) => (
                        <div key={f.fork_id} className="afs-border"
                          style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                            padding: '6px 10px', fontSize: 13 }}>
                          {f.new_project_id}{' '}
                          <span className="afs-muted">· {f.owner_scope}</span>
                        </div>
                      ))
                    )}
                  </div>
                </Panel>
              </div>
            </>
          )}
        </div>
      </div>
    </HubDialog>
  );
}
