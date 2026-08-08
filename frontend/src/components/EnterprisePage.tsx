// [UI 설계서 §3.1 · §4 · §5.1] `/enterprise` — **경영 홈(Decision Canvas).**
//
// ## §1.2 승인 시안에서 «고정할 요소» 7가지를 이 화면이 전부 들고 있어야 한다
//
//   ① 좌측 역할 기반 의사결정 대기열     ② 중앙 Enterprise Digital Thread
//   ③ 업무 위의 DATA·SW·TWIN 레이어      ④ 하단 Trust Foundation
//   ⑤ 우측 회사 범위 Atlas               ⑥ 상단 회사·사업부·공장 Context
//   ⑦ LS Blue 는 구조, LS Red 는 결정·주의·핵심 행동에 **제한** 사용
//
// ⚠️ 첫 구현(2026-08-09 오전)은 ①④⑤ 만 만들고 ②③⑥ 을 빠뜨렸으며, 토큰 대신 인라인 색을
//   쓰고(존재하지 않는 `--afs-border` 를 참조했다) §1.3 최소 글자 크기도 어겼다.
//   「큰 모양은 맞는데 세부가 틀리다」는 지적이 정확했다. 이 파일은 그 재작성이다.
//
// ## §1.3 프로덕션 보정 — 프로토타입의 8~11px 를 그대로 쓰지 않는다
//
//   본문 14px+ / 폼 라벨·보조문 12px+ / 버튼 13px+·높이 36px+ / 핵심 행동 42~48px /
//   KPI 22px+ / **10~11px 는 해시·ID·타임스탬프 같은 기술 메타데이터에만**
//
// ## §2.4 간격 — 화면 24~32, 카드 내부 16~20, 패널 gap 16, 버튼 r6, 카드 r8
//
// ## ⚠️ 데이터를 지어내지 않는다
//
// 큐·KPI 는 전사 브리핑이, Trust 4카드는 각 도메인 API 가 실제로 주는 것을 쓴다. 서버가 주지
// 않는 값(담당 역할·기한·공정 프로필)은 **«미지정» 으로 적고 빈칸을 만들지 않는다.**
import { useCallback, useEffect, useMemo, useState } from 'react';

import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { JarvisRail } from '../design/JarvisRail';
import { getEnterpriseContext } from '../lib/api';
import {
  SECTION_LABELS, fetchBriefing, type Briefing, type BriefingItem,
} from '../lib/briefingApi';
import { crosswalkApi } from '../lib/crosswalkApi';
import { orgApi, type Dept } from '../lib/orgApi';

/** §4.2 상태. **색만으로 전달하지 않는다**(§2.1) — 낱말을 함께 싣는다. */
const SEVERITY: Record<string, { label: string; fg: string; bg: string }> = {
  high: { label: '긴급', fg: 'var(--state-error-fg)', bg: 'var(--state-error-bg)' },
  medium: { label: '확인 필요', fg: 'var(--state-warn-fg)', bg: 'var(--state-warn-bg)' },
  low: { label: '참고', fg: 'var(--state-unknown-fg)', bg: 'var(--state-unknown-bg)' },
  info: { label: '정보', fg: 'var(--state-info-fg)', bg: 'var(--state-info-bg)' },
};

type QueueRow = BriefingItem & { section: string };

/** §4.5 LayerOverlay — DATA·SW·TWIN. **모두 끄는 것도 허용한다.** */
type Layer = 'DATA' | 'SW' | 'TWIN';
const LAYERS: { id: Layer; label: string; desc: string; color: string }[] = [
  { id: 'DATA', label: 'DATA', desc: '자산·Master·지식팩·외부지표·최신성',
    color: 'var(--ls-cyan)' },
  { id: 'SW', label: 'SW', desc: '프로젝트·릴리스·운영 상태·담당 Agent',
    color: 'var(--ls-orange)' },
  { id: 'TWIN', label: 'TWIN', desc: '시나리오·기준선·영향·Backtest',
    color: 'var(--ls-green)' },
];

/** §4.6 TrustFoundationStrip 의 카드 4종. 설계가 지정한 이름·핵심 정보·경고 그대로. */
type TrustCard = {
  key: string; title: string;
  state: 'loading' | 'ok' | 'warn' | 'error';
  headline: string;      // 상태의 완전성 — 숫자보다 먼저
  detail: string;        // 핵심 정보
  warn?: string;         // 설계가 지정한 경고
};

export function EnterprisePage({ onOpenBuild, onOpenMenu }: {
  onOpenBuild: () => void;
  onOpenMenu: (id: string) => void;
}) {
  const [data, setData] = useState<Loaded<Briefing>>(loading<Briefing>());
  const [selected, setSelected] = useState<QueueRow | null>(null);
  const [layers, setLayers] = useState<Layer[]>(['DATA', 'SW', 'TWIN']);
  const [nodes, setNodes] = useState<Dept[]>([]);
  const [nodeNote, setNodeNote] = useState('');
  const [trust, setTrust] = useState<TrustCard[]>([]);

  const load = useCallback(async () => {
    setData(loading<Briefing>());
    try {
      //: ⚠️ `fetchBriefing()` 은 **`{ data, permission }` 봉투**를 돌려준다 — 봉투째 넣으면
      //:   `sections` 가 undefined 가 되어 화면이 오류 없이 전부 «—» 를 그린다(실측으로 잡았다).
      const r = await fetchBriefing();
      setData(ok(r.data));
    } catch (e) {
      setData(failed<Briefing>(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  /** §4.3 EnterpriseThreadCanvas — 업무 노드.
   *
   * ⚠️ 설계는 「**process profile** 기반 동적 렌더링」을 요구하는데 서버에 그 원천이 없다
   *   (`/master/domains` 404). 지어내지 않고 **조직 트리**를 업무 축으로 쓰고, 그것이
   *   공정 프로필이 아니라는 사실을 화면에 적는다. */
  useEffect(() => {
    let alive = true;
    orgApi.tree()
      .then(({ rows, blockedReason }) => {
        if (!alive) return;
        setNodes(rows || []);
        setNodeNote(blockedReason || '');
      })
      .catch((e) => { if (alive) setNodeNote(e?.message || '업무 노드를 받지 못했습니다.'); });
    return () => { alive = false; };
  }, []);

  /** §4.6 Trust Foundation 4카드 — 각 도메인 API 를 실제로 부른다. */
  useEffect(() => {
    let alive = true;
    const base = (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8080';
    const j = (p: string) => fetch(`${base}${p}`).then((r) => (r.ok ? r.json() : Promise.reject(r)));

    const cards: TrustCard[] = [
      { key: 'mdm', title: 'MDM', state: 'loading', headline: '확인 중', detail: '' },
      { key: 'ops', title: '운영 데이터', state: 'loading', headline: '확인 중', detail: '' },
      { key: 'knowledge', title: '지식', state: 'loading', headline: '확인 중', detail: '' },
      { key: 'external', title: '외부지표', state: 'loading', headline: '확인 중', detail: '' },
    ];
    setTrust(cards);
    const put = (key: string, patch: Partial<TrustCard>) => {
      if (!alive) return;
      setTrust((prev) => prev.map((c) => (c.key === key ? { ...c, ...patch } : c)));
    };

    j('/api/v1/master/types')
      .then((r) => put('mdm', { state: 'ok', headline: `유형 ${(r.data || []).length}종 등록`,
        detail: '연결 도메인·범위 커버리지' }))
      .catch(() => put('mdm', { state: 'error', headline: '확인하지 못했습니다',
        detail: '0 건이 아니라 조회 실패입니다' }));

    j('/api/v1/crosswalk/systems/coverage')
      .then((r) => {
        const d = r.data || {};
        const un = Number(d.unscoped || 0);
        put('ops', {
          state: un > 0 ? 'warn' : 'ok',
          headline: `연결 시스템 ${d.total ?? 0}개`,
          detail: `범위 지정 ${d.scoped ?? 0} · 미지정 ${un}`,
          warn: un > 0 ? '범위 미지정 시스템이 있습니다 — 모든 조직에 노출됩니다.' : '',
        });
      })
      .catch(() => put('ops', { state: 'error', headline: '확인하지 못했습니다', detail: '' }));

    j('/api/v1/knowledge/packs')
      .then((r) => {
        const packs = r.data || [];
        put('knowledge', { state: 'ok', headline: `승인 팩 ${packs.length}개`,
          detail: '문서·청크·검토 대기' });
      })
      .catch(() => put('knowledge', { state: 'error', headline: '확인하지 못했습니다', detail: '' }));

    j('/api/v1/external/readiness')
      .then((r) => {
        const d = r.data || {};
        const blocked = Number(d.blocked || 0);
        put('external', {
          state: blocked > 0 ? 'warn' : 'ok',
          headline: `지표 ${d.total ?? 0}개 중 사용 가능 ${d.usable_for_baseline ?? 0}개`,
          detail: 'vintage·지연 확인 필요',
          warn: blocked > 0 ? `${blocked}개가 기준선 사용 차단 상태입니다.` : '',
        });
      })
      .catch(() => put('external', { state: 'error', headline: '확인하지 못했습니다', detail: '' }));

    return () => { alive = false; };
  }, []);

  const d = data.value;

  const rows = useMemo<QueueRow[]>(() => {
    if (!d) return [];
    const out: QueueRow[] = [];
    for (const key of ['my_decisions', 'blocked'] as const) {
      const sec = (d.sections as any)?.[key];
      for (const it of (sec?.items || [])) out.push({ ...it, section: key });
    }
    const order: Record<string, number> = { high: 0, medium: 1, low: 2, info: 3 };
    return out.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9));
  }, [d]);

  useEffect(() => { if (!selected && rows.length) setSelected(rows[0]); }, [rows, selected]);

  /** §5.1 상단 KPI **최대 4개**. 「업무 도메인 / Master Data / 연결 / 근거 충실도」를 기본으로
   *  하되 **회사 프로필에 따라 교체**한다 — 여기서는 브리핑이 실제로 세는 축을 쓴다. */
  const kpis = useMemo(() => {
    const sec = (k: string) => (d?.sections as any)?.[k];
    const cost = sec('cost') || {};
    return [
      { label: '내가 결정할 것', value: sec('my_decisions')?.count ?? null, hint: '답해야 넘어갑니다' },
      { label: '막혀 있는 것', value: sec('blocked')?.count ?? null, hint: '누군가 풀어야 합니다' },
      { label: '업무 도메인', value: nodes.length || null, hint: '조직 트리 기준' },
      {
        label: 'LLM 비용',
        value: cost.available === false ? null : (cost.cost_usd ?? null),
        hint: cost.available === false ? (cost.reason || '집계할 수 없습니다')
          : `${cost.calls ?? 0}콜${cost.cost_complete === false ? ' · 일부 미가격' : ''}`,
        money: true,
      },
    ];
  }, [d, nodes]);

  const ctx = getEnterpriseContext();
  const card: React.CSSProperties = {
    background: 'var(--surface-card)', border: '1px solid var(--surface-border)',
    borderRadius: 8, padding: 18,           // §2.4 카드 내부 16~20
  };

  return (
    <div className="afs-scope" style={{
      background: 'var(--surface-page)', minHeight: 'calc(100vh - 72px)',
      display: 'grid',
      // §3.1 Decision Rail 280 / 중앙 최소 720 / Atlas Rail 360
      gridTemplateColumns: 'minmax(260px, 280px) minmax(0, 1fr) minmax(320px, 360px)',
      alignItems: 'stretch',
    }}>
      {/* ── ① 좌 280: Decision Queue (§4.2) · surface-warm ──────────────── */}
      <aside style={{
        background: 'var(--surface-sunken)', borderRight: '1px solid var(--surface-border)',
        padding: 20, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <b style={{ fontSize: 15, color: 'var(--surface-text)' }}>의사결정 대기</b>
          <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
            {data.status === 'ok' ? `${rows.length}건` : ''}
          </span>
        </div>

        {data.status !== 'ok' ? (
          <EmptyOrError state={data.status} error={data.error}
            emptyText="지금 답해야 할 것이 없습니다." onRetry={load} />
        ) : rows.length === 0 ? (
          <p style={{ fontSize: 14, color: 'var(--surface-text-muted)' }}>
            지금 답해야 할 것이 없습니다.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
            {rows.map((r, i) => {
              const sev = SEVERITY[r.severity] || SEVERITY.info;
              const on = selected === r;
              return (
                <button key={`${r.ref}-${i}`} onClick={() => setSelected(r)}
                  style={{
                    minHeight: 84,                       // §4.2 행 높이 최소 84px
                    textAlign: 'left', padding: '12px 14px', cursor: 'pointer',
                    background: 'var(--surface-card)',
                    border: '1px solid var(--surface-border)',
                    // §2.4 «선택은 그림자보다 좌측 bar·border·배경 대비로»
                    borderLeft: `4px solid ${on ? 'var(--ls-navy)' : 'transparent'}`,
                    borderRadius: 8,
                    display: 'flex', flexDirection: 'column', gap: 6,
                  }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 12, fontWeight: 700, padding: '1px 7px',
                      borderRadius: 6, color: sev.fg, background: sev.bg }}>{sev.label}</span>
                    <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                      {SECTION_LABELS[r.section as keyof typeof SECTION_LABELS] || r.section}
                    </span>
                  </div>
                  <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4,
                    color: 'var(--surface-text)' }}>{r.title}</span>
                  <span style={{ fontSize: 12.5, lineHeight: 1.45,
                    color: 'var(--surface-text-muted)' }}>{r.why}</span>
                  {/* §4.2 필드: 담당 역할·기한. ⚠️ 서버가 주지 않는다 — 빈칸 대신 «미지정». */}
                  <span style={{ fontSize: 12, color: 'var(--surface-text-faint)' }}>
                    담당 미지정 · 기한 미지정
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </aside>

      {/* ── 중앙: Digital Thread + 레이어 + Decision Focus + Trust ───────── */}
      <main style={{ padding: 24, minWidth: 0, display: 'flex', flexDirection: 'column',
        gap: 16 }}>
        {/* §5.1 KPI 최대 4개 — KPI 22px 이상(§1.3) */}
        <div style={{ display: 'grid', gap: 16,
          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
          {kpis.map((k) => (
            <div key={k.label} style={card}>
              <div style={{ fontSize: 12.5, color: 'var(--surface-text-muted)' }}>{k.label}</div>
              <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1.2, marginTop: 2,
                color: 'var(--surface-text)',
                fontFamily: k.money ? 'var(--font-mono, monospace)' : undefined }}>
                {/* ⚠️ 「모른다」를 0 으로 쓰지 않는다 — 0 은 «없다» 이고 «못 셌다» 와 다르다. */}
                {k.value === null || k.value === undefined ? '—'
                  : k.money ? `$${Number(k.value).toFixed(2)}` : k.value}
              </div>
              <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginTop: 2 }}>
                {k.hint}
              </div>
            </div>
          ))}
        </div>

        {/* ── ② Enterprise Digital Thread + ③ DATA/SW/TWIN 레이어 ───────── */}
        <section style={card}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
            <b style={{ fontSize: 15, color: 'var(--surface-text)' }}>업무 흐름</b>
            {/* §4.5 LayerOverlay — 모두 끄는 것도 허용한다 */}
            <div style={{ display: 'flex', gap: 8 }}>
              {LAYERS.map((l) => {
                const on = layers.includes(l.id);
                return (
                  <button key={l.id} title={l.desc}
                    onClick={() => setLayers((prev) => prev.includes(l.id)
                      ? prev.filter((x) => x !== l.id) : [...prev, l.id])}
                    style={{
                      fontSize: 13, height: 36, padding: '0 14px', borderRadius: 6,  // §1.3
                      cursor: 'pointer',
                      border: `1px solid ${on ? l.color : 'var(--surface-border)'}`,
                      background: on ? l.color : 'var(--surface-card)',
                      color: on ? '#fff' : 'var(--surface-text-muted)',
                      fontWeight: on ? 700 : 500,
                    }}>
                    {l.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* §4.4 DomainNode — 선택 면적 최소 64×64px */}
          {nodeNote ? (
            <p style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>{nodeNote}</p>
          ) : nodes.length === 0 ? (
            <p style={{ fontSize: 14, color: 'var(--surface-text-muted)' }}>
              업무 노드를 아직 받지 못했습니다.
            </p>
          ) : (
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {/* §4.3 노드 12개 초과 시 상위 그룹 — 여기서는 상위 12개만 그리고 나머지는 수로 */}
              {nodes.slice(0, 12).map((n, i) => (
                <button key={n.dept_id} onClick={() => onOpenMenu('org')}
                  style={{
                    minWidth: 64, minHeight: 64, padding: '10px 14px', cursor: 'pointer',
                    borderRadius: 8, border: '1px solid var(--surface-border)',
                    background: 'var(--surface-raised)', textAlign: 'left',
                    display: 'flex', flexDirection: 'column', gap: 4,
                  }}>
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)',
                    color: 'var(--surface-text-faint)' }}>{String(i + 1).padStart(2, '0')}</span>
                  <span style={{ fontSize: 13.5, fontWeight: 600,
                    color: 'var(--surface-text)' }}>{n.name_ko || n.dept_id}</span>
                  {layers.includes('DATA') && (
                    <span style={{ fontSize: 12, color: 'var(--ls-cyan)' }}>
                      도메인 {(n.master_domains || []).length}
                    </span>
                  )}
                  {layers.includes('SW') && (
                    <span style={{ fontSize: 12, color: 'var(--ls-orange)' }}>
                      템플릿 {n.default_template_id ? '지정' : '미지정'}
                    </span>
                  )}
                  {layers.includes('TWIN') && (
                    <span style={{ fontSize: 12, color: 'var(--ls-green)' }}>
                      에이전트 {(n.domain_agents || []).length}
                    </span>
                  )}
                </button>
              ))}
              {nodes.length > 12 && (
                <span style={{ alignSelf: 'center', fontSize: 13,
                  color: 'var(--surface-text-muted)' }}>+{nodes.length - 12}개 더</span>
              )}
            </div>
          )}
          {/* ⚠️ 설계가 요구한 «process profile» 이 서버에 없다는 사실을 숨기지 않는다. */}
          <p style={{ fontSize: 12, color: 'var(--surface-text-faint)', marginTop: 10 }}>
            공정 프로필(process profile)이 아직 서버에 없어 <b>조직 트리</b>를 업무 축으로
            표시합니다 — 공정 단위 흐름이 아닙니다.
          </p>
        </section>

        {/* Decision Focus */}
        <section style={{ ...card, minHeight: 180 }}>
          <div style={{ fontSize: 11, letterSpacing: '.08em',
            color: 'var(--surface-text-faint)', fontFamily: 'var(--font-mono, monospace)' }}>
            DECISION FOCUS
          </div>
          {!selected ? (
            <p style={{ fontSize: 14, color: 'var(--surface-text-muted)', marginTop: 8 }}>
              왼쪽에서 하나를 고르면 여기에 근거와 다음 행동이 나옵니다.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
              <h2 style={{ fontSize: 18, margin: 0, lineHeight: 1.4,
                color: 'var(--surface-text)' }}>{selected.title}</h2>
              <p style={{ fontSize: 14, margin: 0, lineHeight: 1.6,
                color: 'var(--surface-text)' }}>{selected.why}</p>
              {selected.suggested_action && (
                <div style={{ background: 'var(--surface-raised)',
                  border: '1px solid var(--surface-border)', borderRadius: 8, padding: 16 }}>
                  <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>다음 행동</div>
                  <div style={{ fontSize: 14, marginTop: 2,
                    color: 'var(--surface-text)' }}>{selected.suggested_action}</div>
                </div>
              )}
              <div style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)',
                color: 'var(--surface-text-faint)' }}>
                {selected.ref_type ? `${selected.ref_type} · ` : ''}{selected.ref || 'ref 없음'}
              </div>
            </div>
          )}
        </section>

        {/* ── ④ Trust Foundation (§4.6) — 숫자보다 «상태의 완전성» 을 먼저 ── */}
        <section>
          <div style={{ fontSize: 11, letterSpacing: '.08em', marginBottom: 8,
            color: 'var(--surface-text-faint)', fontFamily: 'var(--font-mono, monospace)' }}>
            TRUST FOUNDATION
          </div>
          <div style={{ display: 'grid', gap: 16,
            gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))' }}>
            {trust.map((c) => (
              <div key={c.key} style={{
                ...card,
                borderLeft: `4px solid ${c.state === 'error' ? 'var(--state-error-fg)'
                  : c.state === 'warn' ? 'var(--state-warn-fg)'
                    : c.state === 'ok' ? 'var(--state-success-fg)' : 'var(--state-unknown-fg)'}`,
              }}>
                <div style={{ fontSize: 14, fontWeight: 700,
                  color: 'var(--surface-text)' }}>{c.title}</div>
                <div style={{ fontSize: 13, marginTop: 6,
                  color: 'var(--surface-text)' }}>{c.headline}</div>
                {c.detail && (
                  <div style={{ fontSize: 12, marginTop: 4,
                    color: 'var(--surface-text-muted)' }}>{c.detail}</div>
                )}
                {c.warn && (
                  <div style={{ fontSize: 12, marginTop: 8, color: 'var(--state-warn-fg)' }}>
                    ⚠️ {c.warn}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, marginTop: 8, fontFamily: 'var(--font-mono, monospace)',
            color: 'var(--surface-text-faint)' }}>
            기준시각 {d?.generated_at ? new Date(d.generated_at).toLocaleString() : '—'}
            {' · '}실행 문맥 {ctx.entityMode || 'REAL'} · {ctx.scopeNodeId || '조직 미지정'}
          </div>
        </section>

        {/* §3.4 경영 홈 → Studio. ⑦ LS Red 는 «화면당 하나의 핵심 행동» 에만 — 여기서는
            1차 행동이 구조색(Navy)이고 Red 를 쓰지 않는다(위험한 행동이 아니다). */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button onClick={onOpenBuild} style={{
            height: 46, padding: '0 20px', fontSize: 14, fontWeight: 700, borderRadius: 6,
            cursor: 'pointer', border: '1px solid var(--ls-navy)',
            background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
          }}>🏭 업무 SW 만들기 — Software Factory</button>
          <button onClick={() => onOpenMenu('advisor')} style={{
            height: 46, padding: '0 18px', fontSize: 14, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--action-secondary-border)',
            background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
          }}>🧭 무엇을 만들지 상담</button>
          <button onClick={() => onOpenMenu('collaboration')} style={{
            height: 46, padding: '0 18px', fontSize: 14, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--action-secondary-border)',
            background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
          }}>🤝 협업·의사결정·발간</button>
        </div>
      </main>

      {/* ── ⑤ 우 360: Atlas (§4.7) ──────────────────────────────────────── */}
      <aside style={{ borderLeft: '1px solid var(--surface-border)', minWidth: 0, padding: 12 }}>
        <JarvisRail
          contextTitle="경영 홈"
          contextDescription="지금 답해야 할 것과 그 근거를 봅니다."
          context={{
            current_module: 'enterprise',
            selected_object_type: selected?.ref_type || '',
            selected_object_id: selected?.ref || '',
            object_snapshot: selected ? {
              title: selected.title, severity: selected.severity, section: selected.section,
            } : { queue: rows.length, layers },
            available_actions: [],
            evidence_refs: [],
          }}
          evidence={data.status === 'ok' ? [
            { label: '결정 대기', value: `${rows.length}건` },
            { label: '업무 노드', value: `${nodes.length}개` },
          ] : []}
          quickQuestions={[
            '왜 이 판단입니까?',
            '데이터가 부족합니까?',
            '관련 SW·에이전트 상태는 어떻습니까?',
            '시나리오로 보면 어떻게 됩니까?',
          ]} />
      </aside>
    </div>
  );
}
