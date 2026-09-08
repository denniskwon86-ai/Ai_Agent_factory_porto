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
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { useLatestOnly } from '../design/useLatestOnly';
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import { fetchOrgNodes, type FlatNode } from '../lib/governanceApi';
import { createRollbackRunner } from '../lib/releaseRollback';
import type {
  Checklist, ChecklistStep, Fork, Gate, GateCheck, Promotion, RollbackResult, Share,
} from '../lib/workspaceApi';
import {
  createShare, fetchChecklist, fetchForks, fetchGate, fetchPromotions, fetchShares,
  ownerApprove, promoteRelease, rejectPromotion, requestPromotion, revokeShare,
  rollbackRelease,
} from '../lib/workspaceApi';

export type WorkspaceReleaseOption = {
  id: string;
  label: string;
  projectId?: string;
};

type Props = { onClose: () => void; page?: boolean; releaseOptions?: WorkspaceReleaseOption[] };

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
  revoked: { label: '승격 철회', tone: 'muted' },
};

/** [설계 §5.4 `/operate/workspace`] 좌측 필터의 세 축. */
type OperateFilter = { scope: string; status: string; target: string };

/** 좌측 필터 컬럼 — 부서(소유 범위) · 상태 · 유형(목표 범위).
 *
 * ⚠️ **선택지는 실제 데이터에서 만든다.** 상태 목록을 여기에 손으로 적으면 서버가 새 상태를
 *   추가했을 때 그 항목은 필터에서 영영 빠지고, 사용자는 「그런 건이 없다」로 읽는다.
 *   상태만은 `PROMO` 순서를 따르되 **데이터에 있는 것만** 노출한다.
 *
 * ⚠️ 목록을 못 읽었을 때 필터를 「없음」으로 그리지 않는다 — 조회 실패와 0건은 다르다. */
function OperateFilters({ rows, filter, onChange, scopeLabel }: {
  rows: Promotion[]; filter: OperateFilter; onChange: (f: OperateFilter) => void;
  scopeLabel?: (id: string) => string;
}) {
  const uniq = (pick: (p: Promotion) => string) =>
    Array.from(new Set(rows.map(pick).filter(Boolean))).sort();
  const scopes = uniq((p) => p.from_scope);
  const targets = uniq((p) => p.target_scope);
  const present = new Set(rows.map((p) => p.status));
  const statuses = Object.keys(PROMO).filter((s) => present.has(s as Promotion['status']));

  const group = (title: string, key: keyof OperateFilter, opts: string[],
                 label: (v: string) => string) => (
    <div className="filter-group">
      <div className="filter-title">{title}</div>
      {opts.length === 0 ? (
        <p className="afs-muted" style={{ fontSize: 12, margin: 0 }}>
          목록에 값이 없습니다.
        </p>
      ) : (
        <>
          <button className={`filter-chip ${filter[key] === '' ? 'on' : ''}`}
            onClick={() => onChange({ ...filter, [key]: '' })}>전체</button>
          {opts.map((v) => (
            <button key={v} className={`filter-chip ${filter[key] === v ? 'on' : ''}`}
              onClick={() => onChange({ ...filter, [key]: filter[key] === v ? '' : v })}>
              {label(v)}
            </button>
          ))}
        </>
      )}
    </div>
  );

  return (
    <aside className="operate-filters" aria-label="필터">
      {group('부서 (소유 범위)', 'scope', scopes, (v) => scopeLabel?.(v) || '조직 이름 미확인')}
      {group('상태', 'status', statuses, (v) => PROMO[v]?.label || v)}
      {group('유형 (목표 범위)', 'target', targets,
        (v) => v === 'enterprise' ? '전사' : (scopeLabel?.(v) || '조직 이름 미확인'))}
    </aside>
  );
}


export default function WorkspacePanel({ onClose, page = false, releaseOptions = [] }: Props) {
  const [promotions, setPromotions] = useState<Loaded<Promotion[]>>(loading<Promotion[]>());
  const [orgNodes, setOrgNodes] = useState<FlatNode[]>([]);
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
  const [rollbackBusy, setRollbackBusy] = useState(false);
  const runRollback = useMemo(createRollbackRunner, []);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  //: [설계 §5.4] 좌측 필터 — 부서(소유 범위) / 상태 / 유형(목표 범위).
  const [filter, setFilter] = useState<OperateFilter>({ scope: '', status: '', target: '' });

  // ⚠️ 되돌리기 어렵거나 남에게 영향을 주는 행동은 화면 안에서 한 번 확인한다.
  //: [설계 §6.1] 늦게 온 응답을 버리는 표. 릴리스를 바꿔 가며 볼 때 필수다.
  const claim = useLatestOnly();

  const confirmPromote = useConfirm<true>();
  const confirmRollback = useConfirm<{ releaseId: string; projectId: string }>();
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
      setPromotions(failed<Promotion[]>(e));
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => {
    fetchOrgNodes().then(setOrgNodes).catch(() => setOrgNodes([]));
  }, []);

  const inspect = useCallback(async (rid: string, pid = '', live = liveIntegration, refreshOnly = false) => {
    if (!rid.trim()) { setErr('점검할 릴리스를 선택하십시오.'); return; }
    const isCurrent = claim();   // §6.1 — 요청 직전에 표를 뽑는다
    if (!refreshOnly) { setErr(''); setMsg(''); setRollbackOut(null); confirmRollback.cancel(); }
    setReleaseId(rid); setProjectId(pid);
    setGate(loading<Gate>());
    setShares(loading<Share[]>());
    setForks(loading<Fork[]>());
    setChecklist(loading<Checklist>());
    const [g, s, f, c] = await Promise.allSettled([
      fetchGate(rid, pid), fetchShares(rid), fetchForks(rid), fetchChecklist(rid, pid, live),
    ]);
    // ★★ [설계 §6.1] 릴리스를 빠르게 두 번 바꾸면 **앞의 응답이 뒤에 도착**할 수 있다.
    //   그러면 화면 제목은 새 릴리스인데 게이트 판정은 옛 릴리스의 것이 된다 — 「승격 가능」을
    //   엉뚱한 릴리스에 대해 읽고 그대로 승격한다. 늦게 온 응답은 조용히 버린다.
    if (!isCurrent()) return;
    // ★★★ 넷을 **각각** 담는다. 종전에는 실패를 전부 «빈 배열/ null» 로 바꿨다.
    setGate(g.status === 'fulfilled' ? ok(g.value) : failed<Gate>(g.reason));
    setShares(s.status === 'fulfilled' ? ok(s.value || []) : failed<Share[]>(s.reason));
    setForks(f.status === 'fulfilled' ? ok(f.value || []) : failed<Fork[]>(f.reason));
    setChecklist(c.status === 'fulfilled' ? ok(c.value) : failed<Checklist>(c.reason));
  }, [liveIntegration, claim]);

  const act = async (fn: () => Promise<unknown>, okMsg: string) => {
    setMsg(''); setErr('');
    try {
      await fn();
      await inspect(releaseId, projectId);
      setMsg(okMsg);
      loadList();
    } catch (e: any) {
      // 백엔드 거절 사유를 그대로 — 요약하면 무엇을 고쳐야 할지가 사라진다.
      setErr(e?.message || '요청이 거절됐습니다.');
    }
  };

  const g = gate?.value;
  const cl = checklist.value;
  const current = (promotions.value || []).find((p) => p.release_id === releaseId);
  const releaseNames = useMemo(() => new Map(
    releaseOptions.map((row) => [row.id, row.label || '이름 미등록 릴리스']),
  ), [releaseOptions]);
  const releaseLabel = (id: string) => releaseNames.get(id) || '이름 미등록 릴리스';
  const scopeNames = useMemo(() => new Map(orgNodes.map((row) => [row.node_id, row.label])), [orgNodes]);
  const scopeLabel = (id: string) => {
    if (!id) return '미지정';
    if (id === 'enterprise') return '전사';
    return scopeNames.get(id) || '조직 이름 미확인';
  };
  //: 좌측 필터가 걸러 낸 중앙 목록. **선택된 릴리스는 필터와 무관하게 우측에 그대로 남는다** —
  //  보고 있던 상세가 필터 한 번에 사라지면 사용자는 화면이 고장 난 것으로 읽는다.
  /** [설계 §5.4] **지금 눌러야 할 것 하나.** 상태가 다음에 요구하는 행동을 주 CTA 로 삼는다.
   *
   * ⚠️ 게이트를 통과하지 못했으면 «승격» 을 주 CTA 로 두지 않는다 — 강조된 버튼이 눌리지
   *   않으면 사용자는 화면 고장으로 읽는다. 그때 할 일은 막힌 항목을 고치는 것이다. */
  const primaryCta: 'request' | 'approve' | 'promote' | '' = (() => {
    const st = current?.status;
    if (st === 'promoted') return '';
    if (st === 'approved') return g?.promotable ? 'promote' : '';
    if (st === 'requested') return 'approve';
    return 'request';   // 없음 · draft · rejected
  })();

  const shownPromotions = (promotions.value || []).filter((p) =>
    (!filter.scope || p.from_scope === filter.scope)
    && (!filter.status || p.status === filter.status)
    && (!filter.target || p.target_scope === filter.target));

  return (
    <HubDialog label="부서 워크스페이스 — 공유·복제·전사 승격" onClose={onClose} page={page}>
      {!page && <div className="afs-dialog-bar">
        <b>부서 워크스페이스</b>
        <span>공유는 승격이 아닙니다 · 전사 승격은 데이터 계약·보안·품질·소유자 승인을 모두 통과해야 합니다(§9.3)</span>
        <div className="bar-actions">
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>}

      {/* ★ [UI 설계서 §5.4 `/operate/workspace`] 「좌: 부서/상태/유형 필터 · 중앙: 프로그램·
          릴리스 목록 · 우: 선택 자산 상세와 공유/승격 흐름」.
          ⚠️ 이전에는 전부 한 줄(단일 컬럼)이었다. 그러면 목록을 찾으려고 스크롤하고, 상세를
            보려고 또 스크롤한다 — 「어느 릴리스를 보고 있는가」가 화면에서 사라진다. */}
      <div className="afs-dialog-body operate-workspace">
        <OperateFilters rows={promotions.value || []} filter={filter} onChange={setFilter}
          scopeLabel={scopeLabel} />

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
                <select className="afs-select" aria-label="점검할 릴리스" style={{ flex: 1, minWidth: 260 }}
                  disabled={rollbackBusy}
                  value={releaseId} onChange={(e) => {
                    const id = e.target.value;
                    const picked = releaseOptions.find((row) => row.id === id);
                    setReleaseId(id);
                    setProjectId(picked?.projectId || '');
                    claim(); setGate(null); setRollbackOut(null); setMsg(''); setErr('');
                    confirmRollback.cancel(); setRollbackReason('');
                  }}>
                  <option value="">— 릴리스 선택 —</option>
                  {releaseOptions.map((row) => (
                    <option key={row.id} value={row.id}>{row.label || '이름 미등록 릴리스'}</option>
                  ))}
                </select>
                <button className="primary-button" disabled={rollbackBusy}
                  onClick={() => inspect(releaseId, projectId)}>게이트 점검</button>
              </div>
              {promotions.status !== 'ok' ? (
                // ★ 신청 목록을 못 읽었으면 «신청이 없다» 로 보이지 않게 한다.
                <EmptyOrError state={promotions.status} error={promotions.error}
                  emptyText="승격 신청 기록이 없습니다." onRetry={loadList} />
              ) : shownPromotions.length === 0 ? (
                //: ⚠️ 필터 때문에 비었는지, 원래 없는지를 **구분해서** 말한다. 뭉치면 사용자는
                //  자기가 켜 둔 필터를 잊고 「승격 신청이 없다」로 읽는다.
                <p className="afs-muted" style={{ fontSize: 13 }}>
                  {(promotions.value || []).length > 0
                    ? '이 필터에 맞는 릴리스가 없습니다 — 왼쪽에서 «전체» 를 누르면 다시 보입니다.'
                    : '승격 신청 기록이 없습니다.'}
                </p>
              ) : (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {shownPromotions.map((p) => (
                    <button key={p.promotion_id} className="secondary-button" disabled={rollbackBusy}
                      onClick={() => inspect(p.release_id, p.project_id)}>
                      {releaseLabel(p.release_id)}{' '}
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
            <fieldset disabled={rollbackBusy} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
              {/* ★ [설계 §5.4 promotions] 「상단: 릴리스·**소유 범위·목표 범위**」.
                  승격은 «어디서 어디로» 가 전부인데, 그동안 화면 어디에도 없었다. */}
              <div className="promotion-head">
                <div><span>릴리스</span><b>{releaseId ? releaseLabel(releaseId) : '미선택'}</b></div>
                <div><span>소유 범위</span>
                  <b>{scopeLabel(current?.from_scope || fromScope)}</b></div>
                <div><span>목표 범위</span>
                  <b>{scopeLabel(current?.target_scope || 'enterprise')}</b></div>
                <div><span>상태</span>
                  <b className={`state-chip ${PROMO[current?.status || '']?.tone || 'muted'}`}>
                    {current ? (PROMO[current.status]?.label || current.status) : '신청 없음'}
                  </b></div>
              </div>

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

                        {/* ★★ [설계 §5.4] 「하단: 신청/오너 승인/반려/승격 버튼. **현재 상태에
                            맞는 하나의 주 CTA 만 강조**」.
                            ⚠️ 이전에는 상태와 무관하게 «전사 승격» 만 채워진 주 버튼이었다.
                              초안 상태에서도 승격이 강조되니, 사용자는 신청을 건너뛰고 승격을
                              눌렀다가 거절당한다 — 다음에 무엇을 해야 하는지를 버튼이 알려
                              주지 못하면 네 개를 차례로 눌러 보게 된다. */}
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          <button className={primaryCta === 'request' ? 'primary-button' : 'secondary-button'}
                            onClick={() => act(() => requestPromotion({
                              release_id: releaseId, from_scope: fromScope || 'unknown',
                              project_id: projectId,
                            }), '승격을 신청했습니다.')}>
                            {current?.status === 'rejected' ? '고쳐서 다시 신청' : '승격 신청'}
                          </button>
                          <button className={primaryCta === 'approve' ? 'primary-button' : 'secondary-button'}
                            onClick={() => act(() => ownerApprove(releaseId),
                              '데이터 오너가 승인했습니다.')}>데이터 오너 승인</button>
                          <button className="secondary-button"
                            onClick={() => confirmReject.ask(true)}>반려</button>
                          {/* ③ 통과 못 하면 잠근다 — 백엔드가 409 를 주지만 누르기 전에 알아야 한다 */}
                          <button className={primaryCta === 'promote' ? 'primary-button' : 'secondary-button'}
                            disabled={!g!.promotable}
                            onClick={() => confirmPromote.ask(true)}>전사 승격</button>
                        </div>
                        {current?.status === 'promoted' && (
                          <p className="afs-muted" style={{ fontSize: 12 }}>
                            이미 전사 승격된 릴리스입니다 — 지금 눌러야 할 것이 없습니다.
                          </p>
                        )}

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

                        {/* ★ [설계 §6.5] 승격은 확인 Sheet 5요소를 전부 채운다. */}
                        <ConfirmInline open={confirmPromote.open}
                          title="이 릴리스를 전사에 승격합니다"
                          changes={<>{releaseLabel(releaseId)}가 <b>{scopeLabel(current?.from_scope || fromScope)}</b>
                            {' '}범위에서 <b>{scopeLabel(current?.target_scope || 'enterprise')}</b> 범위로 올라갑니다.</>}
                          affects={<>전 조직이 이 프로그램을 볼 수 있게 됩니다.
                            {/* ⚠️ 아는 만큼만 적는다 — 조회 실패를 «없음» 으로 쓰지 않는다. */}
                            {shares.status === 'ok'
                              ? ` 현재 공유 ${(shares.value || []).length}곳`
                              : ' 현재 공유 현황은 확인하지 못했습니다(0곳이 아닙니다)'}
                            {forks.status === 'ok'
                              ? ` · 복제 ${(forks.value || []).length}건이 영향을 받습니다.`
                              : ' · 복제 현황도 확인하지 못했습니다.'}</>}
                          reversible={<><b>사실상 되돌릴 수 없습니다.</b> 철회해도 이미 본
                            사람이 있고, 그들이 만든 산출물은 남습니다.</>}
                          approval={<>데이터 오너 승인 완료
                            {current?.data_owner_approved_by ? ` (${current.data_owner_approved_by})` : ''}
                            {' · '}승격 시점의 게이트 판정이 스냅샷으로 보관됩니다.</>}
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
                      {/* ⚠️ 사유 입력란을 여기에도 두었더니 **같은 값을 두 곳에서** 받게
                          됐다(§6.5 로 Sheet 안에 옮긴 뒤에도 남아 있었다). 두 곳에 있으면
                          어느 쪽이 실제로 전송되는지 사용자가 알 수 없다 — Sheet 한 곳에서만
                          받는다. */}
                      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <button className="danger-solid"
                          disabled={rollbackBusy || rollbackOut?.outcome === 'complete'}
                          onClick={() => { setRollbackReason(''); confirmRollback.ask({ releaseId, projectId }); }}>
                          {rollbackBusy ? '사용 중단 처리 중…' : rollbackOut?.outcome === 'complete' ? '사용 중단 완료' : '운영에서 내리기'}
                        </button>
                      </div>
                      {/* ★ [§6.5] 사유를 «비어 있다» 고 경고만 하지 않고 **여기서 받는다** —
                          경고는 읽고 그냥 누를 수 있지만, 입력 자리는 비우면 진행되지 않는다. */}
                      <ConfirmInline open={confirmRollback.open}
                        title="이 릴리스를 운영에서 내립니다"
                        changes={<>{releaseLabel(releaseId)}가 운영에서 내려갑니다. 전사 승격 상태였다면
                          <b> 함께 철회</b>됩니다.</>}
                        affects={<>쓰고 있는 쪽은 <b>즉시</b> 막힙니다.
                          {shares.status === 'ok'
                            ? ` 공유 ${(shares.value || []).length}곳이 끊깁니다.`
                            : ' 공유 현황을 확인하지 못했습니다 — 끊기는 곳이 없다는 뜻이 아닙니다.'}</>}
                        reversible={<>코드·데이터·이력은 보관됩니다. 이전 버전으로 자동 복원하거나
                          자료를 삭제하는 동작은 아닙니다. 재사용은 별도 검토 후 처리합니다.</>}
                        approval="운영 담당 권한이 필요합니다. 사유는 감사 기록에 남습니다."
                        reason={{
                          value: rollbackReason,
                          onChange: setRollbackReason,
                          required: true,
                          placeholder: '예: 입고 수량이 이중 계상되어 즉시 중단합니다',
                          label: <>롤백 사유 <b>(필수)</b> — 없으면 같은 문제를 반복합니다</>,
                        }}
                        confirmLabel="사유를 기록하고 사용 중단"
                        onCancel={confirmRollback.cancel}
                        onConfirm={() => confirmRollback.run(async (target) => {
                          setMsg(''); setErr(''); setRollbackOut(null);
                          const feedback = await runRollback({
                            perform: () => rollbackRelease(target.releaseId, rollbackReason.trim()),
                            refresh: () => Promise.all([
                              inspect(target.releaseId, target.projectId, liveIntegration, true), loadList(),
                            ]),
                            onBusy: setRollbackBusy,
                          });
                          if (!feedback) return;
                          setRollbackOut(feedback.result);
                          setMsg(feedback.message); setErr(feedback.error);
                          if (feedback.result?.outcome === 'complete') setRollbackReason('');
                        })} />
                      {rollbackOut && (
                        <Banner tone={rollbackOut.outcome === 'complete' ? 'info' : 'error'}
                          title={rollbackOut.message}>
                          {rollbackOut.limitation}
                        </Banner>
                      )}
                    </div>
                  </div>
                </Panel>
              </div>

              {/* ── ④ 공유는 승격과 분리해서 보여준다 ───────────────────
                  [설계 §5.4 promotions] 「우: **영향 범위·의존 대상**·승인 이력」 —
                  공유는 지금 누가 쓰고 있는가(영향 범위), 포크는 무엇이 딸려 있는가(의존)다. */}
              <div className="operate-detail">
                <Panel kicker="SHARE" title="부서 공유"
                  action={<span className="afs-muted" style={{ fontSize: 12 }}>승격이 아닙니다</span>}>
                  <div className="panel-body">
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <select className="afs-select" aria-label="소유 조직" style={{ flex: 1, minWidth: 160 }}
                        value={fromScope} onChange={(e) => setFromScope(e.target.value)}>
                        <option value="">— 소유 조직 선택 —</option>
                        {orgNodes.map((node) => <option key={node.node_id} value={node.node_id}>{node.label}</option>)}
                      </select>
                      <select className="afs-select" aria-label="공유 대상 조직" style={{ flex: 1, minWidth: 160 }}
                        value={toScope} onChange={(e) => setToScope(e.target.value)}>
                        <option value="">— 공유 대상 선택 —</option>
                        {orgNodes.map((node) => <option key={node.node_id} value={node.node_id}>{node.label}</option>)}
                      </select>
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
                          <span>{scopeLabel(s.to_scope)} · {s.mode}</span>
                          <button className="secondary-button"
                            onClick={() => confirmRevoke.ask(s)}>회수</button>
                        </div>
                      ))
                    )}
                    <ConfirmInline open={confirmRevoke.open} title="이 공유를 회수합니다"
                      changes={<>{scopeLabel(confirmRevoke.target?.to_scope || '')}에 준 공유가 해제됩니다.</>}
                      affects={<><b>{scopeLabel(confirmRevoke.target?.to_scope || '')}</b>의 접근이 끊깁니다 —
                        지금 쓰고 있다면 그쪽은 <b>원인을 모른 채</b> 막힙니다.</>}
                      reversible="다시 공유하면 복구됩니다."
                      approval="이 릴리스의 소유 조직 권한이 필요합니다."
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
                          복제 프로젝트{' '}
                          <span className="afs-muted">· {scopeLabel(f.owner_scope)}</span>
                        </div>
                      ))
                    )}
                  </div>
                </Panel>
              </div>
            </fieldset>
          )}
        </div>
      </div>
    </HubDialog>
  );
}
