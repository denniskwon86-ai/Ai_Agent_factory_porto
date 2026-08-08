// [D-017 §9 P2-2] Agent Governance Center — 범위 탭 · 권한 상태 · 승인 흐름.
//
// 설계 `docs/design_agent_governance_scope_permissions_2026-08-04.md` §8.3~§8.6.
//
// ## 왜 이 화면이 필요했나
//
// 조직별 자산 저장소와 승인 API 는 2026-08-04 부터 완비돼 있었는데 **프론트 소비자가
// 0건**이었다. 즉 「조직이 자기 에이전트를 만들고 승인해서 쓴다」는 계약이 **API 로만
// 존재하고 사람이 쓸 수 없는 상태**였다. 서버가 막아 주는 것과 사람이 쓸 수 있는 것은 다르다.
//
// ## 이 화면이 지키는 세 가지
//
// ① **§8.3 상단 문맥** — 회사·조직·모드 / 현재 권한을 **행동 단위**로 / 보는 범위와
//    **숨겨진 자산 수**. 「몇 건 보이는가」만 있으면 사용자는 그것을 전량으로 읽는다.
// ② **§8.4 자산 탭 6종** — 한 번 받은 목록의 파생이다(탭마다 부르면 여섯 번 왕복하고
//    그 사이 상태가 바뀌면 탭끼리 어긋난다).
// ③ **§8.6 버튼 계약** — 권한이 없으면 **숨기지 않고 비활성 + 사유**. 회색 버튼만 보이면
//    사용자는 화면 고장으로 읽고 진짜 이유는 아무에게도 도달하지 않는다.
//
// ⚠️ **없는 것을 지어내지 않았다.** §8.4 는 카드에 「사용 중인 프로젝트 수」를 요구하는데
//   서버가 그 값을 주지 않는다. 0 으로 그리면 「아무도 안 쓴다」가 되어 폐기 판단을 그르친다 —
//   그 자리에 **무엇이 없는지**를 적는다(자산 위생 P4-4 가 같은 이유로 «미사용» 을 만들지
//   않은 것과 같은 판단이다).
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { getEnterpriseContext } from '../lib/api';
import {
  ASSET_TABS, agentGovApi, inTab,
  type AssetKindPath, type AssetTab, type GovAsset, type GovCapabilities, type GovList,
} from '../lib/agentGovernanceApi';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';

const KINDS: { id: AssetKindPath; label: string }[] = [
  { id: 'agents', label: '에이전트' },
  { id: 'workflows', label: '워크플로우' },
  { id: 'skills', label: '스킬' },
];

const TAB_ICON: Record<AssetTab, RailItem['icon']> = {
  system: 'packs', enterprise: 'globe', org: 'orgtree',
  my_draft: 'revise', pending: 'inbox', retired: 'blocked',
};

const VIS_KO: Record<string, string> = {
  PERSONAL: '개인', ORG: '조직', ENTERPRISE: '전사', SYSTEM: '기본 제공',
};
const STATUS_KO: Record<string, string> = {
  DRAFT: '초안', REVIEW: '승인 대기', APPROVED: '승인됨', RETIRED: '사용 중단',
};
const STATUS_TONE: Record<string, string> = {
  DRAFT: 'muted', REVIEW: 'warn', APPROVED: 'success', RETIRED: 'danger',
};

function asLoaded<T>(e: any): Loaded<T> {
  return e?.status === 403 || e?.status === 401
    ? { status: 'forbidden', value: null, error: e?.message || '볼 권한이 없습니다.',
      httpStatus: e.status }
    : failed<T>(e);
}

export function AgentGovernancePanel({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState<AssetKindPath>('agents');
  const [tab, setTab] = useState<AssetTab>('org');
  const [caps, setCaps] = useState<Loaded<GovCapabilities>>(loading<GovCapabilities>());
  const [list, setList] = useState<Loaded<GovList>>(loading<GovList>());
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  // ⚠️ 승인·폐기는 다른 사람에게 영향을 준다 — 화면 안에서 한 번 확인한다.
  const confirmApprove = useConfirm<GovAsset>();
  const confirmRetire = useConfirm<GovAsset>();

  const loadCaps = useCallback(async () => {
    setCaps(loading<GovCapabilities>());
    try {
      const c = await agentGovApi.capabilities();
      reportRequestSuccess();
      setCaps(ok(c));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setCaps(asLoaded<GovCapabilities>(e));
    }
  }, []);

  const loadList = useCallback(async () => {
    setList(loading<GovList>());
    try {
      // 사용 중단 탭이 있으므로 **항상** 폐기분까지 받는다 — 탭은 목록의 파생이다.
      const d = await agentGovApi.list(kind, { includeRetired: true });
      reportRequestSuccess();
      setList(ok(d));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setList(asLoaded<GovList>(e));
    }
  }, [kind]);

  useEffect(() => { loadCaps(); }, [loadCaps]);
  useEffect(() => { loadList(); }, [loadList]);

  const c = caps.value;
  const d = list.value;
  const actions = c?.asset_actions?.[kind];
  const me = c?.user_id || '';
  const myScopes = useMemo(
    () => new Set<string>((d?.items || []).map((x) => x.owner_scope_id).filter(Boolean)),
    [d]);

  const rows = useMemo(
    () => (d?.items || []).filter((a) => inTab(a, tab, me, myScopes)),
    [d, tab, me, myScopes]);

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const t of ASSET_TABS) {
      out[t.id] = (d?.items || []).filter((a) => inTab(a, t.id, me, myScopes)).length;
    }
    return out;
  }, [d, me, myScopes]);

  const act = async (label: string, fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(label); setErr(''); setMsg('');
    try {
      await fn();
      setMsg(okMsg);
      await loadList();
    } catch (e: any) {
      // 서버 거절 사유를 그대로 — 요약하면 무엇을 고쳐야 할지가 사라진다.
      setErr(e?.message || '요청이 거절됐습니다.');
    } finally {
      setBusy('');
    }
  };

  /** §8.6 — 못 누르는 이유를 **항상** 들고 다닌다. */
  const why = (need: keyof NonNullable<typeof actions>, a: GovAsset): string => {
    if (!actions) return '권한을 확인하지 못했습니다.';
    if (!actions[need]) {
      return need === 'approve'
        ? '승인 권한이 없습니다 — 조직 관리자·AI 관리자가 승인합니다.'
        : '이 종류의 자산을 바꿀 권한이 없습니다.';
    }
    if (a.asset_id.startsWith('file:')) {
      return '기본 제공 정의는 직접 고치지 않습니다 — 복사해서 쓰십시오.';
    }
    return '';
  };

  const ctx = getEnterpriseContext();
  const railItems: RailItem[] = ASSET_TABS.map((t) => ({
    id: t.id, label: t.label, hint: t.hint, icon: TAB_ICON[t.id],
    count: counts[t.id] || 0,
    countLabel: `${t.label} ${counts[t.id] || 0}건`,
  }));

  /** §8.3 — 권한을 **행동 단위**로 적는다. 「AGENT_UPDATE 있음」은 사람이 읽는 말이 아니다. */
  const permissionLine = !actions ? '권한을 확인하지 못했습니다.'
    : [
        actions.create ? '초안 작성 가능' : '초안 작성 불가',
        actions.approve ? '승인 가능' : '승인 불가',
        c?.can_publish_enterprise ? '전사 공개 가능' : '전사 공개 불가',
      ].join(' · ');

  return (
    <HubDialog label="Agent Governance Center — 조직 자산의 범위·권한·승인" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>Agent Governance Center</b>
        <span>이 권한 범위 안에서 «어떤 에이전트를 만들고 운영할 것인가»를 관리합니다</span>
        <div className="bar-actions">
          {(busy || list.status === 'loading') && <span className="busy">{busy || '확인 중'}…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <HubShell
          kicker="GOVERNANCE" title="조직 자산"
          subtitle={ASSET_TABS.find((t) => t.id === tab)?.hint || ''}
          items={railItems} activeId={tab} onSelect={(id) => setTab(id as AssetTab)}
          footer={
            <div className="inheritance-card">
              <span>SCOPE</span>
              <b>보이는 것이 전부가 아닐 수 있습니다</b>
              <p>목록은 볼 수 있는 조직으로 걸러집니다. 가려진 것이 있으면 위에 표시합니다 —
                건수는 자료를 관리하는 사람에게만 보입니다.</p>
            </div>
          }
          jarvis={<JarvisRail
            contextTitle="조직 자산 거버넌스"
            contextDescription="누가 만들고 누가 승인해서 어느 범위에 쓰이는가를 관리합니다."
            context={{
              current_module: `agent-governance/${kind}/${tab}`,
              selected_object_type: 'agent_asset',
              selected_object_id: '',
              object_snapshot: {
                kind, tab, load_status: list.status,
                shown: rows.length, scoped: d?.scoped ?? null,
                hidden_present: d?.hidden_present ?? null,
              },
              available_actions: actions
                ? Object.entries(actions).filter(([, v]) => v).map(([k]) => k) : [],
              evidence_refs: [],
            }}
            evidence={list.status === 'ok' ? [
              { label: '보이는 자산', value: `${d?.total ?? 0}건` },
              { label: '범위 필터', value: d?.scoped ? '적용됨' : '없음(전량)' },
            ] : []}
            quickQuestions={[
              '이 자산을 우리 조직에서 쓰려면 무엇을 해야 합니까?',
              '승인 대기가 왜 안 넘어갑니까?',
              '기본 제공과 전사 공용은 무엇이 다릅니까?',
            ]} />}
        >
          <ScreenHead kicker="GOVERNANCE"
            title={ASSET_TABS.find((t) => t.id === tab)?.label || '조직 자산'}
            description={ASSET_TABS.find((t) => t.id === tab)?.hint}
            chip={list.status === 'loading' ? { label: '확인 중', tone: 'muted' }
              : list.status === 'forbidden' ? { label: '권한 없음', tone: 'danger' }
                : list.status === 'error' ? { label: '조회 불가', tone: 'danger' }
                  : { label: `${rows.length}건`, tone: 'data' }} />

          {err && (
            <div style={{ marginBottom: 12 }}>
              <Banner tone="error" title="진행하지 못했습니다">
                <span style={{ whiteSpace: 'pre-wrap' }}>{err}</span>
              </Banner>
            </div>
          )}
          {msg && <div style={{ marginBottom: 12 }}><Banner tone="info">{msg}</Banner></div>}

          {/* ── §8.3 상단 문맥 ────────────────────────────────────────── */}
          <Panel kicker="CONTEXT" title="지금 어디서 무엇을 할 수 있는가">
            <div className="panel-body">
              <div className="metric-row">
                <div>
                  <span>실행 문맥</span>
                  <b>{ctx.entityMode || 'REAL'}</b>
                  <small>{ctx.scopeNodeId || '조직 미지정'} · {ctx.tenantId || 'tenant_default'}</small>
                </div>
                <div>
                  <span>현재 권한</span>
                  <b style={{ fontSize: 15 }}>{actions?.create ? '작성 가능' : '읽기만'}</b>
                  <small>{permissionLine}</small>
                </div>
                <div>
                  <span>보는 범위</span>
                  <b>{d?.scoped === false ? '전량' : '범위 안'}</b>
                  <small>{d?.scoped === false
                    ? '범위 필터가 걸리지 않았습니다'
                    : '볼 수 있는 조직으로 걸러진 목록입니다'}</small>
                </div>
                <div>
                  <span>가려진 자산</span>
                  {/* ⚠️ `null` 은 «세지 못했다» — «없다» 와 다르다. 0 으로 쓰면 전량으로 읽힌다. */}
                  <b>{d?.hidden_present == null ? '—'
                    : d.hidden_present ? (d.hidden_count != null ? `${d.hidden_count}건` : '있음')
                      : '없음'}</b>
                  <small>{d?.hidden_present == null ? '세지 못했습니다 — «없음»이 아닙니다'
                    : d.hidden_present && d.hidden_count == null
                      ? '건수는 자료를 관리하는 사람에게만 표시됩니다'
                      : ''}</small>
                </div>
              </div>

              {/* 자산 종류 전환 — 탭(범위)과 축이 다르므로 같은 줄에 섞지 않는다. */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <span className="afs-muted" style={{ fontSize: 12 }}>자산 종류</span>
                {KINDS.map((k) => (
                  <button key={k.id}
                    className={kind === k.id ? 'primary-button' : 'secondary-button'}
                    onClick={() => setKind(k.id)}>{k.label}</button>
                ))}
              </div>

              {caps.status !== 'ok' && (
                <EmptyOrError state={caps.status} error={caps.error}
                  emptyText="권한 정보를 받지 못했습니다." onRetry={loadCaps} />
              )}
              {c?.bootstrap && (
                <Banner tone="warn" title="아직 관리자가 지정되지 않았습니다">
                  지금 보이는 권한은 «권한이 있어서»가 아니라 «아직 아무도 없어서»입니다 —
                  조직 관리자를 지정하면 이 화면의 권한이 달라집니다.
                </Banner>
              )}
              {c?.file_asset_migration && c.file_asset_migration.complete === false && (
                <Banner tone="warn" title="승인 이력 없이 돌고 있는 기본 제공 자산이 있습니다">
                  {c.file_asset_migration.error
                    ? `이관 현황을 읽지 못했습니다: ${String(c.file_asset_migration.error)}`
                    : '조직 자산으로 복사해 승인 이력을 만들면 «무엇으로 만들었는가»에 답할 수 있습니다.'}
                </Banner>
              )}
            </div>
          </Panel>

          {/* ── §8.4 자산 목록 ────────────────────────────────────────── */}
          <div style={{ marginTop: 14 }}>
            <Panel kicker="ASSETS"
              title={`${KINDS.find((k) => k.id === kind)?.label} · ${ASSET_TABS.find((t) => t.id === tab)?.label}`}
              action={<button className="secondary-button" onClick={loadList}>새로고침</button>}>
              <div className="panel-body">
                {list.status !== 'ok' ? (
                  // ★ 조회 실패를 «자산 없음» 으로 쓰지 않는다.
                  <EmptyOrError state={list.status} error={list.error}
                    emptyText="이 범위에 자산이 없습니다." onRetry={loadList} />
                ) : rows.length === 0 ? (
                  <p className="afs-muted" style={{ fontSize: 13 }}>
                    이 탭에 해당하는 자산이 없습니다.
                    {d?.hidden_present ? ' ⚠️ 다만 범위 밖에 가려진 자산이 있습니다.' : ''}
                  </p>
                ) : rows.map((a) => {
                  const approveWhy = why('approve', a);
                  const retireWhy = why('retire', a);
                  const submitWhy = why('update', a);
                  return (
                    <div key={a.asset_id} className="afs-border"
                      style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                        padding: '10px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8,
                        flexWrap: 'wrap' }}>
                        <b style={{ fontSize: 14 }}>{a.name_ko || a.asset_id}</b>
                        <span className={`state-chip ${STATUS_TONE[a.status] || 'muted'}`}>
                          {STATUS_KO[a.status] || a.status}
                        </span>
                        <span className="state-chip data">{VIS_KO[a.visibility] || a.visibility}</span>
                        {a.entity_mode && a.entity_mode !== 'REAL' && (
                          <span className="state-chip warn">{a.entity_mode}</span>
                        )}
                      </div>
                      {a.purpose && (
                        <p className="afs-ink" style={{ fontSize: 13, margin: '4px 0 0' }}>
                          {a.purpose}
                        </p>
                      )}
                      {/* §8.4 — 카드가 실어야 하는 것들. **없는 값은 «미상» 으로 쓴다.** */}
                      <p className="afs-muted" style={{ fontSize: 12, margin: '4px 0 0' }}>
                        소유 조직 {a.owner_scope_id || '미지정'}
                        {' · '}버전 {a.version_count || a.current_version || 0}
                        {' · '}승인자 {a.approved_by || '없음'}
                        {' · '}작성 {a.created_by || '미상'}
                        {/* ⚠️ 서버가 «사용 중인 프로젝트 수» 를 주지 않는다. 0 으로 그리면
                            「아무도 안 쓴다」가 되어 폐기 판단을 그르친다. */}
                        {' · '}사용 중인 프로젝트 — 서버가 세지 않습니다
                      </p>
                      <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                        {a.status === 'DRAFT' && (
                          <GovBtn label="승인 요청" why={submitWhy} busy={busy === '승인 요청'}
                            onClick={() => act('승인 요청',
                              () => agentGovApi.submit(kind, a.asset_id),
                              `«${a.name_ko}» 를 승인 요청했습니다.`)} />
                        )}
                        {a.status === 'REVIEW' && (
                          <GovBtn label="승인" why={approveWhy} primary busy={busy === '승인'}
                            onClick={() => confirmApprove.ask(a)} />
                        )}
                        {a.status !== 'RETIRED' && (
                          <GovBtn label="사용 중단" why={retireWhy} danger busy={busy === '사용 중단'}
                            onClick={() => confirmRetire.ask(a)} />
                        )}
                      </div>

                      {confirmApprove.open && confirmApprove.target?.asset_id === a.asset_id && (
                        <ConfirmInline open title="이 자산을 승인합니다" danger={false}
                          body={<>
                            승인하면 <b>{VIS_KO[a.visibility] || a.visibility} 범위에서 실행에
                            쓰입니다.</b> 승인 이력에 누가 언제 승인했는지 남습니다.
                          </>}
                          confirmLabel="승인"
                          onCancel={confirmApprove.cancel}
                          onConfirm={() => confirmApprove.run((t) => act('승인',
                            () => agentGovApi.approve(kind, t.asset_id),
                            `«${t.name_ko}» 를 승인했습니다.`))} />
                      )}
                      {confirmRetire.open && confirmRetire.target?.asset_id === a.asset_id && (
                        <ConfirmInline open title="이 자산을 사용 중단합니다"
                          body={<>
                            새 프로젝트가 이 정의를 쓸 수 없게 됩니다. <b>기록은 남습니다</b> —
                            이미 만들어진 산출물이 «무엇으로 만들어졌는가» 에 답할 수 있어야
                            하기 때문입니다.
                            <br />⚠️ 지금 이 정의를 쓰고 있는 프로젝트가 몇 개인지는
                            <b> 서버가 세지 않습니다</b> — 영향 범위를 모르는 채 중단하는 것입니다.
                          </>}
                          confirmLabel="사용 중단"
                          onCancel={confirmRetire.cancel}
                          onConfirm={() => confirmRetire.run((t) => act('사용 중단',
                            () => agentGovApi.retire(kind, t.asset_id),
                            `«${t.name_ko}» 를 사용 중단했습니다.`))} />
                      )}
                    </div>
                  );
                })}
              </div>
            </Panel>
          </div>
        </HubShell>
      </div>
    </HubDialog>
  );
}

/** §8.6 버튼 계약 — **권한이 없으면 숨기지 않고 비활성 + 사유.**
 *
 *  ⚠️ 이유 없이 회색으로만 두지 않는다. 회색 버튼만 보이면 사용자는 화면 고장으로 읽고
 *    진짜 이유는 아무에게도 도달하지 않는다(`factory/RunControls` 와 같은 규칙). */
function GovBtn({ label, why, busy, onClick, primary, danger }: {
  label: string; why: string; busy: boolean; onClick: () => void;
  primary?: boolean; danger?: boolean;
}) {
  const cls = danger ? 'danger-solid' : primary ? 'primary-button' : 'secondary-button';
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2 }}>
      <button className={cls} disabled={Boolean(why) || busy}
        aria-disabled={Boolean(why) || undefined} onClick={onClick}>
        {busy ? `${label} 중…` : label}
      </button>
      {why && (
        <small className="afs-warn-fg" style={{ fontSize: 12, maxWidth: 260 }}>🔒 {why}</small>
      )}
    </span>
  );
}
