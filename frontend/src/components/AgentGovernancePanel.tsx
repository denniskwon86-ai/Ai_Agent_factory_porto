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
  ASSET_TABS, ORG_VISIBILITIES, agentGovApi, inTab,
  type AssetKindPath, type AssetTab, type GovAsset, type GovAssetUsage,
  type GovCapabilities, type GovList, type GovUsage,
} from '../lib/agentGovernanceApi';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import { AgentAssetWizard } from './AgentAssetWizard';

const KINDS: { id: AssetKindPath; label: string }[] = [
  { id: 'agents', label: '에이전트' },
  { id: 'workflows', label: '워크플로우' },
  { id: 'skills', label: '스킬' },
];

const TAB_ICON: Record<AssetTab, RailItem['icon']> = {
  system: 'packs', enterprise: 'globe', org: 'orgtree',
  my_draft: 'revise', pending: 'inbox', retired: 'blocked',
};

//: ⚠️ **서버 상수와 같은 낱말이어야 한다**(`core/agent_assets.VIS_*`). 조직 자산은 `ORG` 가
//:   아니라 `SCOPE`(하위까지면 `DESCENDANTS`)다. 없는 낱말을 적으면 배지에 코드가 그대로
//:   노출되고, 탭 판정은 아무것도 못 고른다(2026-08-08 실측으로 둘 다 발견).
const VIS_KO: Record<string, string> = {
  PERSONAL: '개인', SCOPE: '조직', DESCENDANTS: '조직·하위',
  ENTERPRISE: '전사', SYSTEM: '기본 제공',
};
const STATUS_KO: Record<string, string> = {
  DRAFT: '초안', REVIEW: '승인 대기', APPROVED: '승인됨', RETIRED: '사용 중단',
};
const STATUS_TONE: Record<string, string> = {
  DRAFT: 'muted', REVIEW: 'warn', APPROVED: 'success', RETIRED: 'danger',
};


export function AgentGovernancePanel({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState<AssetKindPath>('agents');
  const [tab, setTab] = useState<AssetTab>('org');
  const [caps, setCaps] = useState<Loaded<GovCapabilities>>(loading<GovCapabilities>());
  const [list, setList] = useState<Loaded<GovList>>(loading<GovList>());
  //: ★ 사용 현황은 **목록과 따로** 싣는다. 프로젝트 작업공간을 훑는 일이라 목록에 묶으면
  //:   목록이 느려지고, 스캔이 실패하면 목록까지 함께 죽는다. `null` 은 «아직 못 받았다» 다.
  const [usage, setUsage] = useState<GovUsage | null>(null);
  const [usageErr, setUsageErr] = useState('');
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [wizard, setWizard] = useState(false);

  // ⚠️ 승인·폐기·승격·복사는 다른 사람에게 영향을 준다 — 화면 안에서 한 번 확인한다.
  const confirmApprove = useConfirm<GovAsset>();
  const confirmRetire = useConfirm<GovAsset>();
  const confirmPromote = useConfirm<GovAsset>();
  const confirmCopy = useConfirm<GovAsset>();
  const confirmPublish = useConfirm<GovAsset>();

  const loadCaps = useCallback(async () => {
    setCaps(loading<GovCapabilities>());
    try {
      const c = await agentGovApi.capabilities();
      reportRequestSuccess();
      setCaps(ok(c));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setCaps(failed<GovCapabilities>(e));
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
      setList(failed<GovList>(e));
    }
  }, [kind]);

  const loadUsage = useCallback(async () => {
    setUsage(null); setUsageErr('');
    try {
      setUsage(await agentGovApi.usage(kind));
    } catch (e: any) {
      // ★ 사용 집계 실패가 목록을 죽이지 않는다 — 다만 «못 받았다» 를 남긴다. 조용히 비우면
      //   화면은 「아무도 안 쓴다」와 구분되지 않는다.
      setUsageErr(e?.message || '사용 현황을 받지 못했습니다.');
    }
  }, [kind]);

  useEffect(() => { loadCaps(); }, [loadCaps]);
  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadUsage(); }, [loadUsage]);

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
      //: ⚠️ 빈 문자열이면 **덮어쓰지 않는다.** 승격처럼 서버 답(확정/요청)에 따라 문구가
      //:   달라지는 행동은 `fn` 안에서 이미 메시지를 세웠고, 여기서 빈 값으로 덮으면 그
      //:   문구가 사라져 사용자는 무엇이 일어났는지 모른 채 목록만 새로고침된 것을 본다.
      if (okMsg) setMsg(okMsg);
      await loadList();
      // 자산이 늘거나 폐기되면 사용 현황의 분모도 달라진다 — 함께 새로 받는다.
      await loadUsage();
    } catch (e: any) {
      // 서버 거절 사유를 그대로 — 요약하면 무엇을 고쳐야 할지가 사라진다.
      setErr(e?.message || '요청이 거절됐습니다.');
    } finally {
      setBusy('');
    }
  };

  /** §8.6 — 못 누르는 이유를 **항상** 들고 다닌다.
   *
   * ★★★ 판정은 **서버가 자산마다 준다**(`a.blocked`). 화면은 그 문장을 그대로 붙일 뿐
   *   자기 규칙을 만들지 않는다 — 만들면 서버와 서서히 갈라져 「버튼은 보이는데 서버는
   *   거부」가 생긴다. 2026-08-08 감사에서 실제로 그 상태를 발견했다: 부서원에게 남의 조직
   *   자산의 «승인 요청» 이 활성으로 보였고, 누르면 403 이었다(설계 §10 UI 위반).
   *
   * ⚠️ 서버가 `blocked` 를 안 준 경우(옛 응답)에는 **종류 단위 권한으로 물러난다.** 그때는
   *   자산 단위 사정을 모르므로 눌러서 서버 사유를 받는 편이 낫다 — 여기서 넘겨짚어 막으면
   *   할 수 있는 일까지 막힌다. */
  const why = (need: keyof NonNullable<GovAsset['blocked']>, a: GovAsset): string => {
    if (a.blocked) return a.blocked[need] || '';
    if (!actions) return '권한을 확인하지 못했습니다.';
    const kindLevel: Record<string, boolean> = {
      update: actions.update, submit: actions.update, approve: actions.approve,
      retire: actions.retire, publish_to_org: actions.create,
      promote: actions.approve, copy: actions.create,
    };
    if (!kindLevel[need]) {
      return need === 'approve' || need === 'promote'
        ? '승인 권한이 없습니다 — 조직 관리자·AI 관리자가 승인합니다.'
        : need === 'copy'
          ? '자산을 만들 권한이 없습니다 — 읽기만 가능합니다.'
          : '이 종류의 자산을 바꿀 권한이 없습니다.';
    }
    return '';
  };

  /** 이 자산의 사용 현황. ⚠️ `undefined` 는 «아직 못 받았다» 이고 `countable=false` 는
   *  «셀 수 없다» 다. 둘 다 «0개가 쓴다» 가 아니다. */
  const usageOf = (a: GovAsset): GovAssetUsage | undefined => usage?.usage?.[a.asset_id];

  /** 카드·확인 대화가 함께 쓰는 한 문장. 세 상태를 **다른 말**로 가른다. */
  const usageText = (a: GovAsset): string => {
    if (usageErr) return '사용 중인 프로젝트 — 조회 실패';
    if (!usage) return '사용 중인 프로젝트 — 확인 중';
    if (!usage.available) return '사용 중인 프로젝트 — 집계 실패';
    const u = usageOf(a);
    if (!u || !u.countable) {
      return `사용 중인 프로젝트 — 아직 모름(구성을 기록한 프로젝트 ${usage.axis_observed}/${usage.projects_total})`;
    }
    return `사용 중인 프로젝트 ${u.project_count}개`;
  };

  const ctx = getEnterpriseContext();
  const railItems: RailItem[] = ASSET_TABS.map((t) => ({
    id: t.id, label: t.label, hint: t.hint, icon: TAB_ICON[t.id],
    count: counts[t.id] || 0,
    countLabel: `${t.label} ${counts[t.id] || 0}건`,
  }));

  /** ★★★ 목록이 401/403 이면 «권한» 을 말하기 전에 **그 사실**을 말한다.
   *
   *  ⚠️ 2026-08-08 감사에서 익명 사용자에게 「현재 권한 읽기만」이 표시되는 것을 발견했다 —
   *    그런데 목록은 401 이라 **읽기도 안 된다.** `capabilities` 만 통과하고 목록은 막히는
   *    상태였고(서버가 강제 여부를 두 곳에서 다르게 읽는다), 화면은 앞의 성공만 보고 뒤의
   *    실패를 무시했다. 화면이 「할 수 있다」고 적은 것을 서버가 거부하면 그것은 통제가
   *    아니라 거짓말이다. */
  const identityProblem = list.status === 'forbidden'
    ? (list.httpStatus === 401
      ? '사용자로 식별되지 않았습니다 — 로그인해야 목록을 볼 수 있습니다.'
      : '이 자산 종류를 볼 권한이 없습니다.')
    : '';

  /** §8.3 — 권한을 **행동 단위**로 적는다. 「AGENT_UPDATE 있음」은 사람이 읽는 말이 아니다. */
  const permissionLine = identityProblem ? identityProblem
    : !actions ? '권한을 확인하지 못했습니다.'
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
                  <b style={{ fontSize: 15 }}>{identityProblem ? '확인 불가'
                    : actions?.create ? '작성 가능' : '읽기만'}</b>
                  <small>{permissionLine}</small>
                </div>
                <div>
                  <span>보는 범위</span>
                  {/* ⚠️ 목록을 못 받았으면 범위도 **모른다.** 「범위 안」이라고 적으면 걸러진
                      목록이 있는 것처럼 읽히는데, 실제로는 아무것도 못 받은 상태다. */}
                  <b>{!d ? '확인 불가' : d.scoped === false ? '전량' : '범위 안'}</b>
                  <small>{!d ? '목록을 받지 못했습니다'
                    : d.scoped === false
                      ? '범위 필터가 걸리지 않았습니다'
                      : '볼 수 있는 조직으로 걸러진 목록입니다'}</small>
                </div>
                <div>
                  <span>가려진 자산</span>
                  {/* ★★ 세 상태를 가른다. ⚠️ 종전에는 «봉투 없음» 을 전부 «세지 못했다» 로
                      읽어, **전량을 보는 관리자에게도 경고**가 떴다(2026-08-08 감사에서 발견).
                      경고가 늘 떠 있으면 진짜로 가려진 날에도 아무도 안 본다.
                      · 범위 필터가 없다(`scoped=false`) → 가릴 것이 **없다**
                      · 필터가 있는데 값이 없다              → **세지 못했다**(«없다» 아님)
                      · 필터가 있고 값이 있다                → 있음/없음, 건수는 자격자에게만 */}
                  <b>{!d ? '확인 불가'
                    : d.scoped === false ? '해당 없음'
                      : d.hidden_present == null ? '—'
                        : d.hidden_present ? (d.hidden_count != null ? `${d.hidden_count}건` : '있음')
                          : '없음'}</b>
                  <small>{!d ? '목록을 받지 못했습니다'
                    : d.scoped === false
                      ? '전량을 보므로 가려진 것이 없습니다'
                      : d.hidden_present == null ? '세지 못했습니다 — «없음»이 아닙니다'
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
              action={<span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                {/* §8.5 — 만들기. ⚠️ 권한이 없으면 **숨기지 않고 비활성 + 사유**(§8.6).
                    숨기면 「왜 나는 못 만드나」를 물을 곳이 없다. */}
                <GovBtn label="새로 만들기" primary busy={false}
                  why={actions?.create ? '' : '자산을 만들 권한이 없습니다 — 읽기만 가능합니다.'}
                  onClick={() => setWizard(true)} />
                <button className="secondary-button"
                  onClick={() => { loadList(); loadUsage(); }}>새로고침</button>
              </span>}>
              <div className="panel-body">
                {/* ★ 사용 현황을 못 받은 것은 **목록과 다른 상태**다. 조용히 넘기면 카드의
                    「아직 모름」이 왜 나오는지 알 수 없다. */}
                {(usageErr || (usage && !usage.available)) && (
                  <Banner tone="warn" title="사용 현황을 받지 못했습니다">
                    {usageErr || usage?.error || '집계에 실패했습니다.'}
                    {' '}폐기 여부를 판단하려면 <b>영향 범위를 먼저 확인</b>하십시오 —
                    지금은 «쓰는 곳이 없다» 와 «모른다» 를 구분할 수 없습니다.
                  </Banner>
                )}
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
                  const submitWhy = why('submit', a);
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
                        {/* ★ 「0개가 쓴다」와 「아직 모른다」를 **다른 말**로 가른다 —
                            둘을 같은 «0» 으로 쓰면 폐기 판단이 눈을 감는다. */}
                        {' · '}{usageText(a)}
                      </p>
                      {a.promotion_requested_by && (
                        <p className="afs-warn-fg" style={{ fontSize: 12, margin: '4px 0 0' }}>
                          ⏳ 전사 승격 요청됨 — {a.promotion_requested_by} · AI 거버넌스 관리자가
                          확정해야 전사에 공개됩니다(요청만으로는 공개되지 않습니다).
                        </p>
                      )}
                      {/* ── §8.6 버튼 계약 — 저장·승인 요청·조직 공개·전사 승격을 **분리한다.**
                          한 버튼에 묶으면 사용자는 자기가 무엇을 여는지 모른 채 누른다. ── */}
                      <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                        {/* ★ 복사 — 「기본 제공은 복사해서 쓰십시오」라는 안내의 **도착지**다.
                            이 버튼이 없으면 그 안내가 막다른 길로 끝난다. */}
                        <GovBtn label="복사해서 내 초안으로" why={why('copy', a)}
                          busy={busy === '복사'} onClick={() => confirmCopy.ask(a)} />
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
                        {/* 조직 공개 — 내 초안을 조직 자산으로 **옮긴다**(복사가 아니다). */}
                        {a.visibility === 'PERSONAL' && a.status !== 'RETIRED' && (
                          <GovBtn label="조직에 공개" why={why('publish_to_org', a)}
                            busy={busy === '조직 공개'} onClick={() => confirmPublish.ask(a)} />
                        )}
                        {ORG_VISIBILITIES.includes(a.visibility) && a.status !== 'RETIRED' && (
                          <GovBtn
                            label={caps.value?.can_publish_enterprise
                              ? '전사로 승격' : '전사 승격 요청'}
                            why={why('promote', a)} busy={busy === '전사 승격'}
                            onClick={() => confirmPromote.ask(a)} />
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
                            <br />
                            {/* ★ 영향 범위를 **아는 만큼만** 말한다. 세 상태가 각각 다른 결정을
                                낳는다: 쓰는 곳이 있다 / 없다 / 아직 모른다. */}
                            {(() => {
                              const u = usageOf(a);
                              if (usageErr || !usage || !usage.available) {
                                return <>⚠️ 사용 현황을 <b>받지 못했습니다</b> — 영향 범위를
                                  모르는 채 중단하는 것입니다.</>;
                              }
                              if (!u || !u.countable) {
                                return <>⚠️ 아직 <b>어느 프로젝트도 구성을 기록하지 않았습니다</b>
                                  ({usage.axis_observed}/{usage.projects_total}). 「아무도 안
                                  쓴다」가 아니라 <b>모르는 상태</b>입니다.</>;
                              }
                              if (u.project_count === 0) {
                                return <>기록된 프로젝트 {usage.axis_observed}개 중{' '}
                                  <b>이 정의를 쓰는 곳은 없습니다.</b></>;
                              }
                              return <>⚠️ <b>{u.project_count}개 프로젝트가 지금 이 정의를 쓰고
                                있습니다</b>
                                {u.projects?.length ? ` — ${u.projects.join(', ')}` : ''}.</>;
                            })()}
                          </>}
                          confirmLabel="사용 중단"
                          onCancel={confirmRetire.cancel}
                          onConfirm={() => confirmRetire.run((t) => act('사용 중단',
                            () => agentGovApi.retire(kind, t.asset_id),
                            `«${t.name_ko}» 를 사용 중단했습니다.`))} />
                      )}

                      {confirmCopy.open && confirmCopy.target?.asset_id === a.asset_id && (
                        <ConfirmInline open danger={false} title="이 정의를 복사합니다"
                          body={<>
                            «{a.name_ko}» 를 <b>내 개인 초안</b>으로 복사합니다. 원본은 바뀌지
                            않으므로, 복사본을 고쳐 쓰다가 조직에 공개하면 됩니다.
                          </>}
                          confirmLabel="복사"
                          onCancel={confirmCopy.cancel}
                          onConfirm={() => confirmCopy.run((t) => act('복사',
                            () => agentGovApi.copy(kind, t.asset_id, { visibility: 'PERSONAL' }),
                            `«${t.name_ko}» 를 내 초안으로 복사했습니다 — «내 초안» 탭에 있습니다.`))} />
                      )}

                      {confirmPublish.open && confirmPublish.target?.asset_id === a.asset_id && (
                        <ConfirmInline open danger={false} title="이 초안을 조직에 공개합니다"
                          body={<>
                            «{a.name_ko}» 를 <b>{ctx.scopeNodeId || '현재 조직'}</b> 소유로
                            <b> 옮깁니다</b> — 복사가 아니므로 개인 초안 목록에서는 사라집니다.
                            {a.status === 'APPROVED' && (
                              <><br />⚠️ 이 자산은 승인돼 있는데, 조직에 공개하면
                              <b> 「승인 대기」로 되돌아갑니다</b> — 개인 자산의 승인은 자기가
                              자기 것을 승인한 것이고, 조직 범위에서는 조직이 다시 답해야 합니다.</>
                            )}
                            {!ctx.scopeNodeId && (
                              <><br />⚠️ 지금 실행 문맥에 조직이 지정돼 있지 않습니다 — 서버가
                              거절하면 그 사유가 그대로 표시됩니다.</>
                            )}
                          </>}
                          confirmLabel="조직에 공개"
                          onCancel={confirmPublish.cancel}
                          onConfirm={() => confirmPublish.run((t) => act('조직 공개',
                            () => agentGovApi.publishToOrg(kind, t.asset_id, ctx.scopeNodeId || ''),
                            `«${t.name_ko}» 를 조직 자산으로 옮겼습니다.`))} />
                      )}

                      {confirmPromote.open && confirmPromote.target?.asset_id === a.asset_id && (
                        <ConfirmInline open danger={false}
                          title={caps.value?.can_publish_enterprise
                            ? '이 자산을 전사로 올립니다' : '전사 승격을 요청합니다'}
                          body={caps.value?.can_publish_enterprise ? (
                            <>
                              «{a.name_ko}» 가 <b>모든 조직에 공개</b>됩니다.
                              <br />★ 상태는 <b>「승인 대기」로 되돌아갑니다</b> — 조직 승인과
                              전사 승인은 다른 자격이므로, 전사 자산으로서 한 번 더 승인을
                              받아야 누가 전사에 내보냈는지가 기록에 남습니다.
                            </>
                          ) : (
                            <>
                              AI 거버넌스 관리자에게 «{a.name_ko}» 의 전사 승격을 요청합니다.
                              <br />⚠️ <b>요청만으로는 공개되지 않습니다</b> — 지금 공개 범위는
                              그대로이고, 관리자가 확정할 때 전사에 나갑니다.
                            </>
                          )}
                          confirmLabel={caps.value?.can_publish_enterprise ? '전사로 올리기' : '승격 요청'}
                          onCancel={confirmPromote.cancel}
                          onConfirm={() => confirmPromote.run((t) => act('전사 승격',
                            async () => {
                              const r = await agentGovApi.promote(kind, t.asset_id);
                              // 서버가 «확정» 인지 «요청» 인지 답한다 — 화면이 추측하지 않는다.
                              setMsg(r.promotion_outcome === '확정'
                                ? `«${t.name_ko}» 를 전사로 올렸습니다 — 전사 승인이 한 번 더 필요합니다.`
                                : `«${t.name_ko}» 의 전사 승격을 요청했습니다 — 공개 범위는 아직 그대로입니다.`);
                              return r;
                            }, ''))} />
                      )}
                    </div>
                  );
                })}
              </div>
            </Panel>
          </div>
        </HubShell>
      </div>

      {wizard && (
        <AgentAssetWizard kind={kind} caps={caps.value} onClose={() => setWizard(false)}
          onCreated={(a) => {
            setMsg(`«${a.name_ko}» 를 만들었습니다 — «내 초안» 탭에 있습니다.`);
            // 새 자산이 어느 탭에 들어갔는지 찾아 헤매지 않도록 그 탭으로 옮겨 준다.
            setTab(a.status === 'REVIEW' ? 'pending' : 'my_draft');
            loadList(); loadUsage();
          }} />
      )}
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
