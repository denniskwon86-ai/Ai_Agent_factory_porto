// [이관 9/10] 전사 브리핑 — 권한 범위 안의 상태 1장(LLM 0콜)
//
// ⚠️ 종전 구현이 이미 잘하던 것 — 그대로 유지한다:
//   1. **`complete=false` 를 숨기지 않는다.** «위험 0건»과 «위험을 못 읽었다»는 다른 사실이고,
//      후자를 초록불로 그리면 그 순간 이 화면은 거짓 보고를 한다.
//   2. **항목마다 «무엇을 하면 풀리는가»를 함께 보여준다.** 상태만 나열하면 대시보드지 보좌가 아니다.
//   3. **비용 총액이 하한이면 `≥` 를 붙인다.** 단가 미등록 호출이 있는데 완전한 총액처럼 보이면
//      예산 판단이 틀린다.
//
// ★★★ 이관하면서 새로 지킨 것: **`withheld` 섹션**.
//   2026-08-04 실측에서 익명이 이 화면으로 «데이터 계약 breached — 생산자 자산이 폐기됐다»를
//   그대로 봤다. 5/10 에서 거버넌스 지표를 막았는데 브리핑이 같은 자료를 다시 모아 통제를
//   우회한 것이다. 서버가 이제 권한 없는 섹션을 `withheld` 로 표시해 보내는데, 화면이 그것을
//   «0건»으로 그리면 우회를 막은 의미가 사라진다 — 그래서 별도 상태로 말한다.
//
// ⚠️ 종전 구현에서 제거한 것: 자체 `fixed inset-0` 전체화면 · 9~11px 글자 ·
//   조직 범위를 **자유 입력**으로 받던 것(코드 오타를 잡을 자리가 없었다 → 선택 목록).
import { useCallback, useEffect, useState } from 'react';

import { EvidenceStrip, FoundationToolbar } from '../design/DataFoundationShell';
import { Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import type { RailIconName } from '../design/RailIcon';
import { severityKo } from '../design/terms';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import {
  SECTION_LABELS, fetchBriefing,
  type Briefing, type BriefingItem, type BriefingSection, type CostSection,
} from '../lib/briefingApi';
import { fetchOrgNodes, type FlatNode } from '../lib/governanceApi';

type View = 'top' | BriefingSection;

// ⚠️ 레일 라벨은 **짧게** 쓴다. 220px 레일에서 «내가 결정해야 하는 것»은 «것» 한 글자만 다음
//   줄에 남는다(실측). 화면 제목은 `SECTION_LABELS` 를 그대로 쓰고(서버 계약·다른 화면과 공유),
//   레일에서만 줄인다 — 같은 문구를 두 곳에 두는 것보다 «어디에 쓰는 이름인지»를 나누는 편이 낫다.
const RAIL: { id: View; label: string; hint: string; icon: RailIconName }[] = [
  { id: 'top', label: '먼저 볼 것', hint: '가장 급한 것부터', icon: 'alert' },
  { id: 'my_decisions', label: '내 결정', hint: '사람이 결정해야 한다', icon: 'checklist' },
  { id: 'blocked', label: '막힌 것', hint: '멈춰 있다', icon: 'blocked' },
  { id: 'data_health', label: '데이터 상태', hint: '정비가 필요하다', icon: 'gap' },
  { id: 'programs', label: '프로그램', hint: '가동 상태', icon: 'apps' },
  { id: 'cost', label: '비용', hint: '하한이면 ≥ 표시', icon: 'cost' },
];

/** 화면 제목·배너에 쓰는 정식 이름(서버 계약과 같은 문구). */
const FULL_LABEL: Record<View, string> = {
  top: '먼저 볼 것',
  my_decisions: SECTION_LABELS.my_decisions,
  blocked: SECTION_LABELS.blocked,
  data_health: SECTION_LABELS.data_health,
  programs: SECTION_LABELS.programs,
  cost: SECTION_LABELS.cost,
};

/** 항목 하나. **상태만 쓰지 않고 «다음 행동»을 같은 자리에 둔다.** */
function Item({ it }: { it: BriefingItem }) {
  const cls = it.severity === 'high' ? 'danger' : it.severity === 'medium' ? 'warn' : '';
  return (
    <div className={`request-alert ${cls}`} style={{ margin: '0 0 8px' }}>
      <i aria-hidden="true">{it.severity === 'low' || it.severity === 'info' ? 'i' : '!'}</i>
      <div style={{ minWidth: 0 }}>
        <b>{it.title}</b>
        <small>{it.why}</small>
        {it.suggested_action && (
          <small style={{ marginTop: 4 }}><b>다음 행동</b> — {it.suggested_action}</small>
        )}
        {it.ref && <small style={{ marginTop: 3 }}>{it.ref_type}: {it.ref}</small>}
        <small style={{ marginTop: 3 }}>심각도 {severityKo(it.severity)}</small>
      </div>
    </div>
  );
}

function CostBlock({ c }: { c: CostSection }) {
  // ⚠️ 권한 때문에 담지 않은 것과 «비용 0» 을 구분한다.
  if (c?.withheld) {
    return (
      <div style={{ padding: 14 }}>
        <Banner tone="warn" title="비용은 표시하지 않았습니다">
          {c.withheld_reason || '이 정보를 볼 권한이 없습니다.'} — <b>«비용 0»이 아닙니다.</b>
        </Banner>
      </div>
    );
  }
  if (!c?.available) {
    return (
      <div style={{ padding: 14 }}>
        <Banner tone="warn" title="비용을 읽지 못했습니다">
          {c?.reason || '원인 미상'} — <b>0 으로 표시하지 않습니다.</b>
        </Banner>
      </div>
    );
  }
  const lower = c.cost_complete === false;
  return (
    <div style={{ padding: 14 }}>
      <EvidenceStrip items={[
        { label: 'LLM 비용', value: `${lower ? '≥ ' : ''}$${(c.cost_usd ?? 0).toFixed(4)}` },
        { label: '호출', value: (c.calls ?? 0).toLocaleString() },
        { label: '단가 미등록', value: `${c.unpriced_calls ?? 0}건` },
      ]} note={lower
        ? '단가가 등록되지 않은 호출이 있어 총액은 하한입니다 — 실제 비용은 이보다 큽니다.'
        : '모든 호출에 단가가 등록되어 총액이 완전합니다.'} />
    </div>
  );
}

export function BriefingPanel({ onClose }: { onClose: () => void }) {
  const [view, setView] = useState<View>('top');
  const [scopeNode, setScopeNode] = useState('');
  const [nodes, setNodes] = useState<FlatNode[]>([]);
  const [state, setState] = useState<Loaded<Briefing>>(loading<Briefing>());
  const [perm, setPerm] = useState<{ scope?: string; actor?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setState(loading<Briefing>());
    try {
      const r = await fetchBriefing(scopeNode || undefined);
      reportRequestSuccess();
      setState(ok(r.data));
      setPerm(r.permission || null);
    } catch (e: any) {
      const status = e?.status;
      reportRequestFailure(status);
      setState(status === 403 || status === 401
        ? { status: 'forbidden', value: null, error: e?.message || '브리핑을 볼 권한이 없습니다.',
          httpStatus: status }
        : failed<Briefing>(e));
    } finally { setBusy(false); }
  }, [scopeNode]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { fetchOrgNodes().then(setNodes).catch(() => setNodes([])); }, []);
  useEffect(() => {
    const onUser = () => {
      fetchOrgNodes().then(setNodes).catch(() => setNodes([]));
      load();
    };
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [load]);

  const b = state.value;
  const topCount = b?.top?.length ?? 0;
  const sections = (b?.sections || {}) as Record<string, any>;
  const withheld = (name: View) => name !== 'top' && Boolean(sections[name]?.withheld);
  const withheldReason = (name: View) =>
    (name !== 'top' && sections[name]?.withheld_reason) || '';

  const countOf = (name: View): number | null => {
    if (state.status !== 'ok' || !b) return null;
    if (name === 'top') return b.top?.length ?? 0;
    if (withheld(name)) return null;                 // «모른다» — 0 이 아니다
    if (name === 'cost') return null;                // 비용은 건수가 아니다
    return sections[name]?.count ?? 0;
  };

  const railItems: RailItem[] = RAIL.map((r) => {
    const n = countOf(r.id);
    return {
      id: r.id, label: r.label, icon: r.icon,
      // 권한 때문에 못 본 섹션은 **힌트로 그 사실을 말한다** — 배지 0 으로 두면 «없음»이 된다.
      hint: withheld(r.id) ? '권한 없음' : r.hint,
      count: n && n > 0 ? n : undefined,
      countLabel: n ? `${r.label} ${n}건` : undefined,
    };
  });

  const current = RAIL.find((r) => r.id === view)!;
  const items: BriefingItem[] = view === 'top'
    ? (b?.top || [])
    : (sections[view]?.items || []);
  const anyWithheld = (b?.withheld_sections || []).length > 0;

  return (
    <HubDialog label="전사 브리핑 — 권한 범위 안의 상태 1장" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>전사 브리핑</b>
        <span>결정론적으로 모았습니다(LLM 0콜) — 못 읽은 것은 숨기지 않습니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">집계 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <HubShell
          kicker="BRIEFING" title={FULL_LABEL[view]} subtitle={current.hint}
          items={railItems} activeId={view} onSelect={(id) => setView(id as View)}
          footer={
            <div className="inheritance-card">
              <span>NOT ZERO</span>
              <b>못 읽은 것은 0건이 아닙니다</b>
              <p>권한이 없거나 소스를 읽지 못하면 그 사실을 그대로 말합니다 — 초록불로 그리지 않습니다.</p>
            </div>
          }
          jarvis={<JarvisRail
            contextTitle={state.status === 'ok'
              ? (topCount > 0 ? `먼저 볼 것 ${topCount}건` : '먼저 볼 것 없음')
              : state.status === 'forbidden' ? '권한 없음'
                : state.status === 'error' ? '조회 불가' : '집계 중'}
            contextDescription={state.status === 'ok'
              ? `${b?.generated_at?.slice(0, 16) || '시각 미상'} 기준`
                + (b?.scope?.filtered
                  ? ` · ${perm?.scope || b?.scope?.scope_node_id} 범위` : ' · 전체')
                + (b?.complete === false ? ' — 이 브리핑은 완전하지 않습니다' : '')
              : state.status === 'forbidden'
                ? '전사 브리핑을 볼 권한이 없습니다 — «문제 없음»이 아닙니다.'
                : state.status === 'error'
                  ? '브리핑을 가져오지 못했습니다 — «문제 없음»이 아닙니다.'
                  : '상태를 모으고 있습니다.'}
            context={{
              current_module: `briefing/${view}`,
              selected_object_type: 'briefing_section',
              selected_object_id: '',
              object_snapshot: {
                load_status: state.status, attention: b?.attention_count ?? null,
                complete: b?.complete ?? null,
              },
              available_actions: [],
              evidence_refs: [],
            }}
            evidence={state.status === 'ok' ? [
              { label: '집계 시각', value: b?.generated_at?.slice(0, 16) || '미상' },
              { label: '보는 범위', value: b?.scope?.filtered
                ? (perm?.scope || b?.scope?.scope_node_id || '미상') : '전체' },
              { label: '완전성', value: b?.complete ? '완전' : '불완전' },
            ] : []}
            quickQuestions={[
              '지금 가장 급한 것은 무엇입니까?',
              '이 브리핑에서 빠진 것은 무엇입니까?',
              '이것을 풀면 무엇이 달라집니까?',
            ]} />}
        >
          {state.status === 'forbidden' && (
            <Banner tone="warn" title="전사 브리핑을 볼 권한이 없습니다">
              {state.error} — <b>«문제 없음»이 아닙니다.</b>
            </Banner>
          )}
          {state.status === 'error' && (
            <Banner tone="error" title="브리핑을 가져오지 못했습니다">
              {state.error} — <b>«문제 없음»이 아닙니다.</b>{' '}
              <button className="text-button" onClick={load}>다시 시도</button>
            </Banner>
          )}

          {/* ★★ 불완전한 브리핑을 초록불로 그리지 않는다 — 숫자보다 **위**에 온다. */}
          {b && b.complete === false && (
            <Banner tone="error" title="이 브리핑은 완전하지 않습니다">
              {b.note}
              {(b.unavailable?.length ?? 0) > 0 && (
                <ul className="section-list" style={{ marginTop: 6 }}>
                  {b.unavailable.map((u, i) => (
                    <li key={`${u.section}-${i}`}>
                      <b>{SECTION_LABELS[u.section as BriefingSection] || u.section}</b>
                      <span> — {u.source}: {u.error}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Banner>
          )}

          {/* 권한 때문에 담지 않은 섹션이 있으면 그 사실을 화면에 남긴다. */}
          {anyWithheld && (
            <Banner tone="warn" title="권한 때문에 표시하지 않은 항목이 있습니다">
              {(b?.withheld_sections || [])
                .map((n) => SECTION_LABELS[n as BriefingSection] || n).join(' · ')}
              {' '}— 전사 정비 상태는 데이터 관리자·조직 관리자·경영진에게만 표시됩니다.
              {' '}<b>«문제 없음»이 아닙니다.</b>
            </Banner>
          )}

          <ScreenHead kicker="BRIEFING" title={FULL_LABEL[view]} description={current.hint}
            chip={state.status !== 'ok'
              ? state.status === 'loading'
                ? { label: '집계 중', tone: 'muted' }
                : { label: state.status === 'forbidden' ? '권한 없음' : '조회 불가', tone: 'danger' }
                : withheld(view)
                ? { label: '권한 없음', tone: 'danger' }
                : (b?.attention_count ?? 0) > 0
                  ? { label: `보통 이상 ${b?.attention_count}건`, tone: 'warn' }
                  : { label: '보통 이상 없음', tone: 'success' }} />

          <div className="metric-row">
            <Metric label="심각도 보통 이상" state={state.status}
              value={state.status === 'ok' ? (b?.attention_count ?? 0) : null}
              notes={{ forbidden: '권한 없음', error: '조회 불가', loading: '집계 중' }}
              hint={b && b.complete === false ? '불완전한 집계입니다' : '높음 + 보통'} />
            {(['high', 'medium', 'low'] as const).map((sev) => (
              <Metric key={sev} label={`심각도 ${severityKo(sev)}`} state={state.status}
                value={state.status === 'ok' ? (b?.by_severity?.[sev] ?? 0) : null}
                notes={{ forbidden: '권한 없음', error: '조회 불가', loading: '집계 중' }} />
            ))}
          </div>

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
              : '범위를 고르면 그 조직 기준으로 좁혀 봅니다 — 자유 입력이 아니라 목록에서 고릅니다.'} />

          <Panel kicker={view === 'top' ? 'FIRST' : 'SECTION'} title={FULL_LABEL[view]}>
            {view === 'cost' ? (
              state.status !== 'ok'
                ? <div className="empty-note">비용을 확인할 수 없습니다 — «비용 0»이 아닙니다.</div>
                : <CostBlock c={sections.cost as CostSection} />
            ) : withheld(view) ? (
              <div style={{ padding: 14 }}>
                <Banner tone="warn" title="이 항목은 표시하지 않았습니다">
                  {withheldReason(view) || '이 정보를 볼 권한이 없습니다.'}
                  {' '}<b>«해당 항목 없음»이 아닙니다.</b>
                </Banner>
              </div>
            ) : state.status !== 'ok' ? (
              <div className="empty-note">
                {state.status === 'loading' ? '집계하고 있습니다…'
                  : '이 항목을 가져오지 못했습니다 — «없음»이 아닙니다.'}
              </div>
            ) : items.length === 0 ? (
              <div className="empty-note">
                {view === 'top'
                  ? '먼저 볼 것이 없습니다 — 지금 급한 항목이 없다는 뜻입니다.'
                  : '해당 항목이 없습니다.'}
              </div>
            ) : (
              <div style={{ padding: 14 }}>
                {items.map((it, i) => <Item key={`${it.kind}-${i}`} it={it} />)}
              </div>
            )}
          </Panel>
        </HubShell>
      </div>
    </HubDialog>
  );
}
