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
import { getEnterpriseContext , API_BASE_URL} from '../lib/api';
import {
  SECTION_LABELS, fetchBriefing, type Briefing, type BriefingItem,
} from '../lib/briefingApi';
import { getReadiness, listInstances } from '../lib/dataPrepApi';
import { orgApi, type Dept } from '../lib/orgApi';
import { DecisionDrawer } from './DecisionDrawer';
import { ServerText } from '../design/ServerText';
import { CoreJourney } from './CoreJourney';
import { EnterpriseThread } from './EnterpriseThread';
import { fetchCanvas, type Canvas } from '../lib/canvasApi';
import { fetchScopeNodes, labelForScope, type ScopeNode } from '../lib/scopeLabel';

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
//: ⚠️ [설계 §9.1 WCAG AA] **브랜드 원색을 그대로 쓰면 안 된다.** 이 칩은 켜졌을 때 색 면
//  위에 흰 글자를 얹고, 꺼졌을 때는 그 색을 글자로 쓴다. 원색은 흰색 대비가 cyan 3.31 ·
//  orange 3.12 로 둘 다 4.5:1 에 못 미친다(실측으로 잡았다). 면·글자 모두 어두운 변형을 쓴다 —
//  원색은 테두리·아이콘처럼 **글자가 얹히지 않는 자리**에만 남긴다.
const LAYERS: { id: Layer; label: string; desc: string; color: string }[] = [
  { id: 'DATA', label: 'DATA', desc: '자산·Master·지식팩·외부지표·최신성',
    color: 'var(--ls-cyan-fg)' },
  { id: 'SW', label: 'SW', desc: '프로젝트·릴리스·운영 상태·담당 Agent',
    color: 'var(--ls-orange-fg)' },
  { id: 'TWIN', label: 'TWIN', desc: '시나리오·기준선·영향·Backtest',
    color: 'var(--ls-green-fg)' },
];

/** §4.6 TrustFoundationStrip 의 카드 4종. 설계가 지정한 이름·핵심 정보·경고 그대로. */
type TrustCard = {
  key: string; title: string;
  /** ★ KPI 가 쓰는 숫자. **카드와 KPI 가 같은 조회를 두 번 하지 않게** 여기 남긴다.
   *  ⚠️ `null` = 아직/못 읽음. 0 으로 채우면 「없다」와 「모른다」가 같아진다. */
  n?: number | null;
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
  //: §5.1 Decision Drawer — 안건 하나를 끝까지 처리하는 자리(520px).
  const [drawer, setDrawer] = useState<QueueRow | null>(null);
  //: ★★★ [로드맵 §4.2] Javis 가 「필요한 데이터셋과 누락 항목을 선제안」하려면 준비도를
  //:   **알아야** 한다. 종전에는 `{queue, layers}` 만 실어서, 비서는 우리 데이터를 하나도
  //:   모른 채 「확인할 수 없습니다」만 답했다(2026-08-20 실측).
  //: ⚠️ `null` = 아직 못 읽음, `[]` = 정말 0건. 둘을 같게 실으면 비서가 「데이터가 없다」로
  //:   말하고, 그것은 «조회 실패 ≠ 0건» 규칙이 비서 답변에서 무너지는 것이다.
  const [readiness, setReadiness] = useState<any[] | null>(null);

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
    const j = (p: string) => fetch(`${API_BASE_URL}${p}`).then((r) => (r.ok ? r.json() : Promise.reject(r)));

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
      .then((r) => put('mdm', { state: 'ok', n: (r.data || []).length,
        headline: `유형 ${(r.data || []).length}종 등록`,
        detail: '연결 도메인·범위 커버리지' }))
      .catch(() => put('mdm', { state: 'error', headline: '확인하지 못했습니다',
        detail: '0 건이 아니라 조회 실패입니다' }));

    j('/api/v1/crosswalk/systems/coverage')
      .then((r) => {
        const d = r.data || {};
        const un = Number(d.unscoped || 0);
        put('ops', {
          state: un > 0 ? 'warn' : 'ok',
          n: d.total ?? null,
          headline: `연결 시스템 ${d.total ?? 0}개`,
          detail: `범위 지정 ${d.scoped ?? 0} · 미지정 ${un}`,
          warn: un > 0 ? '범위 미지정 시스템이 있습니다 — 모든 조직에 노출됩니다.' : '',
        });
      })
      .catch(() => put('ops', { state: 'error', headline: '확인하지 못했습니다', detail: '' }));

    j('/api/v1/knowledge/packs')
      .then((r) => {
        const packs = r.data || [];
        put('knowledge', { state: 'ok', n: packs.length,
          headline: `승인 팩 ${packs.length}개`,
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

  //: 준비도를 읽어 **요약만** 싣는다.
  //: ⚠️ 원본 행을 통째로 실으면 프롬프트가 길어지고, 비서가 사람 화면에 없는 값을 인용한다.
  //: ⚠️ 실패해도 홈 화면을 죽이지 않는다 — 다만 «못 읽었다» 를 `null` 로 남긴다.
  useEffect(() => {
    let alive = true;
    listInstances()
      .then(async (d) => {
        const out: any[] = [];
        //: 최대 3개까지만 본다 — 홈 화면이 느려지면 아무도 안 쓴다.
        for (const it of (d.instances || []).slice(0, 3)) {
          try {
            const r = await getReadiness(it.instance_id);
            out.push({
              업무키트: it.label || it.kit_id,
              조직: it.scope_node_id,
              준비상태: r.status,
              필요: r.coverage?.required, 준비됨: r.coverage?.ready,
              막힘: r.coverage?.blocked,
              //: ★ 「무엇을 해야 하는가」가 핵심이다 — 상태만 주면 비서도 상태만 말한다.
              다음행동: (r.datasets || [])
                .filter((x: any) => x.next_action)
                .map((x: any) => `${x.label || x.dataset_contract_key}: ${x.next_action}`)
                .slice(0, 6),
              가능한산출물: r.available_outputs || [],
              막힌산출물: (r.blocked_outputs || []).map((o: any) => o.output),
            });
          } catch {
            //: 이 인스턴스만 못 읽었다 — 그 사실을 적는다(빠뜨리면 «없는 것» 이 된다).
            out.push({ 업무키트: it.label || it.instance_id, 준비상태: '조회 실패' });
          }
        }
        if (alive) setReadiness(out);
      })
      .catch(() => { if (alive) setReadiness(null); });
    return () => { alive = false; };
  }, []);

  /**
   * §5.1 상단 KPI **최대 4개** — 설계서 기본은
   * 「업무 도메인 / Master Data / 연결 / 근거 충실도」다.
   *
   * ## ⚠️⚠️ [2026-08-24] 왜 되돌렸는가
   *
   * 종전에는 「내가 결정할 것 / 막혀 있는 것 / 업무 도메인 / **LLM 비용**」이었다.
   * `LLM 비용` 은 **설계서 어디에도 없다** — 설계서는 비용을 §5.7 Agent 화면과
   * 「AI/품질 관리자」의 일로 배정한다. 경영 홈은 경영진·부서장의 결정 화면이고,
   * 경영자가 `$0.00 · 0콜` 을 보고 할 수 있는 일이 없다. **네 칸을 채우려고 넣은
   * 숫자**였다.
   *
   * ★ 「내가 결정할 것 / 막혀 있는 것」은 바로 아래 의사결정 대기열이 **제목과 함께**
   *   보여 준다. KPI 로 한 번 더 세면 같은 것을 두 번 말하면서 자리는 잃는다.
   * ⚠️ 값은 신뢰 기반(§4.6)이 이미 조회한 것을 **그대로 쓴다** — 같은 것을 두 곳에서
   *   따로 세면 언젠가 두 숫자가 갈라진다.
   */
  const kpis = useMemo(() => {
    const t = (k: string) => trust.find((c) => c.key === k);
    const val = (k: string) => {
      const c = t(k);
      //: 조회 실패·미완료는 `null` 이다 — 0 으로 떨어뜨리지 않는다.
      return c && c.state !== 'loading' && c.state !== 'error' ? (c.n ?? null) : null;
    };
    return [
      //: ⚠️ 조직을 **못 읽었으면** 개수를 쓰지 않는다. 종전에는 `nodes.length` 를 그냥
      //:   썼는데, 권한으로 막히면 그것이 0 이 되어 「업무 도메인 0」으로 보인다 —
      //:   「없다」와 「못 봤다」가 같아진다(`nodeNote` 가 그 구분을 들고 있다).
      { label: '업무 도메인', value: nodeNote ? null : (nodes.length || null),
        hint: nodeNote ? '조직을 확인하지 못했습니다' : '조직 트리 기준' },
      { label: 'Master Data', value: val('mdm'), hint: '등록된 기준정보 유형' },
      { label: '연결', value: val('ops'), hint: '연결된 외부 시스템' },
      { label: '근거 충실도', value: val('knowledge'), hint: '승인된 지식팩' },
    ];
  }, [trust, nodes, nodeNote]);

  const ctx = getEnterpriseContext();
  //: ★ 조직 이름은 **상단바와 같은 곳**에서 얻는다(`lib/scopeLabel`).
  //: ⚠️ 종전에는 `ctx.scopeNodeId` 원시 id 를 그대로 찍어 `node_41402723bc90` 처럼
  //:   아무 뜻 없는 값이 화면 맨 위에 떴다(2026-08-24 사용자 지적).
  //: ★★★ [LE-01] 승인 시안의 중앙 축 — **수주→손익 일곱 단계.**
  //: ⚠️ 종전에는 조직 트리로 대체돼 있었다(줄 API 가 없어서). 이제 단일 Read Model 이 준다.
  const [canvas, setCanvas] = useState<Canvas | null>(null);
  const [canvasErr, setCanvasErr] = useState('');
  const [pickedNode, setPickedNode] = useState('');
  useEffect(() => {
    let alive = true;
    fetchCanvas()
      .then((c) => { if (alive) { setCanvas(c); setCanvasErr(''); } })
      //: ⚠️ 실패를 빈 화면으로 접지 않는다 — 「없다」와 「못 읽었다」는 다르다.
      .catch((e) => { if (alive) setCanvasErr(e?.message || '불러오지 못했습니다.'); });
    return () => { alive = false; };
  }, []);

  const [scopeNodes, setScopeNodes] = useState<ScopeNode[]>([]);
  useEffect(() => {
    let alive = true;
    void fetchScopeNodes().then((rows) => { if (alive) setScopeNodes(rows); });
    return () => { alive = false; };
  }, []);
  const scopeName = labelForScope(scopeNodes, ctx.scopeNodeId || '');
  const card: React.CSSProperties = {
    background: 'var(--surface-card)', border: '1px solid var(--surface-border)',
    borderRadius: 8, padding: 18,           // §2.4 카드 내부 16~20
  };

  return (
    /* ★ [설계 §3.1 · §9.2] 폭 규칙은 **인라인 style 로 쓸 수 없다** — 미디어 쿼리가 안 먹기
       때문이다. 실측(1024px): 3열이 그대로 유지돼 문서 폭이 1206px 로 **가로 스크롤**이
       생겼다. §9.2 는 1024~1279 구간에서 「Decision Queue 또는 Atlas 를 drawer 로 전환」
       하라고 정했다. 클래스로 옮겨 폭 구간을 CSS 가 정하게 한다. */
    <div className="afs-scope enterprise-canvas">
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
                <button key={`${r.ref}-${i}`}
                  onClick={() => { if (selected === r) setDrawer(r); else setSelected(r); }}
                  title="한 번 누르면 아래에 요약, 다시 누르면 상세를 엽니다"
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
                    color: 'var(--surface-text-muted)' }}><ServerText text={r.why} /></span>
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
        {/* ★★★ [2026-08-24 사용자 지적] **머리에 둔다.**
            ⚠️ 종전에는 본문 **맨 아래**에 깔려 있었다. 「지금 무엇을 보고 있는가」
              (기준시각·실행 문맥·조직)와 「여기서 할 수 있는 일」은 화면을 끝까지
              내려야 보였고, 그래서 첫 화면에서 그 둘이 없는 것과 같았다. */}
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
          paddingBottom: 16, borderBottom: '1px solid var(--surface-border)',
        }}>
          <div style={{ fontSize: 12, fontFamily: 'var(--font-mono, monospace)',
            color: 'var(--surface-text-muted)', textAlign: 'center' }}>
            기준시각 {d?.generated_at ? new Date(d.generated_at).toLocaleString() : '—'}
            {' · '}실행 문맥 {ctx.entityMode || 'REAL'} · {scopeName || '조직 미지정'}
          </div>

          {/* ★★★ [2026-08-24 사용자 지적] **핵심 넷을 꺼내 놓는다.**
              「전체 메뉴」를 정리한 것은 찾을 수 있게 한 것이지 보이게 한 것이 아니다.
              처음 여는 사람은 메뉴가 있다는 것조차 모른다. */}
          <CoreJourney onOpen={onOpenMenu} />

          {/* ★★★ [2026-08-24 사용자 지적] **두 줄을 눈으로 갈라 놓는다.**
              위 넷은 «이 시스템의 일»이고, 아래 셋은 «다른 입구»다. 나란히 두었더니
              상단에 같은 무게의 버튼이 일곱 개가 되어 어느 것이 본줄기인지 사라졌다.
              ⚠️ 아래 셋을 없애지 않는다 — 없애면 그 기능을 찾을 길이 메뉴뿐이다.
                **작게 하고 이름을 붙여** 다른 층이라는 것만 보이게 한다. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%',
            marginTop: 4 }}>
            <span style={{ flex: 1, height: 1, background: 'var(--surface-border)' }} />
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.06em',
              color: 'var(--surface-text-faint)' }}>다른 입구</span>
            <span style={{ flex: 1, height: 1, background: 'var(--surface-border)' }} />
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap',
            justifyContent: 'center' }}>
          <button onClick={onOpenBuild} style={{
            height: 34, padding: '0 14px', fontSize: 13, borderRadius: 6,
            cursor: 'pointer', border: '1px solid var(--surface-border-control)',
            background: 'transparent', color: 'var(--surface-text)',
          }}>🏭 업무 SW 만들기</button>
          <button onClick={() => onOpenMenu('advisor')} style={{
            height: 34, padding: '0 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--surface-border-control)',
            background: 'transparent', color: 'var(--surface-text)',
          }}>🧭 무엇을 만들지 상담</button>
          <button onClick={() => onOpenMenu('collaboration')} style={{
            height: 34, padding: '0 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--surface-border-control)',
            background: 'transparent', color: 'var(--surface-text)',
          }}>🤝 협업·의사결정·발간</button>
          </div>
        </div>

        {/* §5.1 KPI 최대 4개 — KPI 22px 이상(§1.3) */}
        <div style={{ display: 'grid', gap: 16,
          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
          {kpis.map((k) => (
            <div key={k.label} style={card}>
              <div style={{ fontSize: 12.5, color: 'var(--surface-text-muted)' }}>{k.label}</div>
              {/* §1.3 KPI 22px 이상 */}
              <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1.2, marginTop: 2,
                color: 'var(--surface-text)' }}>
                {/* ⚠️ 「모른다」를 0 으로 쓰지 않는다 — 0 은 «없다» 이고 «못 셌다» 와 다르다. */}
                {k.value === null || k.value === undefined ? '—' : k.value}
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
            <div>
              {/* ★ 승인 시안의 제목을 그대로 쓴다 — 「업무 흐름」은 우리가 붙인 이름이었다. */}
              <b style={{ fontSize: 15, color: 'var(--surface-text)' }}>
                ENTERPRISE DIGITAL THREAD
              </b>
              <div style={{ fontSize: 12.5, color: 'var(--surface-text-muted)', marginTop: 2 }}>
                업무·데이터·AI 가 하나의 경영 결과로 이어집니다 — 수주에서 손익까지 일곱 단계.
              </div>
            </div>
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

          {/* §4.3–4.4 Enterprise Digital Thread — 승인 시안의 일곱 단계 */}
          {canvasErr ? (
            <p style={{ fontSize: 13, color: 'var(--state-error-fg)' }}>{canvasErr}</p>
          ) : !canvas ? (
            <p style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>불러오는 중…</p>
          ) : (
            <EnterpriseThread
              nodes={canvas.domain_nodes}
              selected={pickedNode}
              onSelect={setPickedNode}
              systemsVerified={canvas.systems_verified} />
          )}
          {/* ★ 종전 「공정 프로필이 없어 조직 트리로 대체합니다」 안내를 지웠다 —
              이제 대체가 아니라 시안이 정한 일곱 단계를 그린다. */}
        </section>

        {/* Decision Focus */}
        <section style={{ ...card, minHeight: 180 }}>
          <div style={{ fontSize: 12, letterSpacing: '.08em',
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
                color: 'var(--surface-text)' }}><ServerText text={selected.why} /></p>
              {selected.suggested_action && (
                <div style={{ background: 'var(--surface-raised)',
                  border: '1px solid var(--surface-border)', borderRadius: 8, padding: 16 }}>
                  <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>다음 행동</div>
                  <div style={{ fontSize: 14, marginTop: 2,
                    color: 'var(--surface-text)' }}>
                    <ServerText text={selected.suggested_action} />
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <button onClick={() => setDrawer(selected)} style={{
                  height: 36, padding: '0 16px', fontSize: 13, fontWeight: 700, borderRadius: 6,
                  cursor: 'pointer', border: '1px solid var(--ls-navy)',
                  background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
                }}>상세 열기</button>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)',
                  color: 'var(--surface-text-faint)' }}>
                  {selected.ref_type ? `${selected.ref_type} · ` : ''}{selected.ref || 'ref 없음'}
                </span>
              </div>
            </div>
          )}
        </section>

        {/* ── ④ Trust Foundation (§4.6) — 숫자보다 «상태의 완전성» 을 먼저 ── */}
        <section>
          <div style={{ fontSize: 12, letterSpacing: '.08em', marginBottom: 8,
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
                  color: 'var(--surface-text)' }}><ServerText text={c.headline} /></div>
                {c.detail && (
                  <div style={{ fontSize: 12, marginTop: 4,
                    color: 'var(--surface-text-muted)' }}><ServerText text={c.detail} /></div>
                )}
                {c.warn && (
                  <div style={{ fontSize: 12, marginTop: 8, color: 'var(--state-warn-fg)' }}>
                    ⚠️ <ServerText text={c.warn} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

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
            object_snapshot: {
              ...(selected
                ? { title: selected.title, severity: selected.severity,
                    section: selected.section }
                : { queue: rows.length, layers }),
              //: ★★★ 준비도를 함께 싣는다. 이것이 없으면 비서는 「무엇이 필요한가」에
              //:   답할 재료가 없다.
              //: ⚠️ 못 읽었으면 **그렇게 적는다** — 빈 배열로 실으면 비서가 「업무
              //:   데이터가 없습니다」라고 단정한다.
              업무데이터_준비도: readiness === null
                ? '조회 실패 — 지금 확인하지 못했습니다(없다는 뜻이 아닙니다)'
                : readiness,
            },
            available_actions: [],
            evidence_refs: [],
          }}
          evidence={data.status === 'ok' ? [
            { label: '결정 대기', value: `${rows.length}건` },
            { label: '업무 노드', value: `${nodes.length}개` },
            //: ★ 사람도 같은 근거를 본다 — 비서만 아는 값이 있으면 답을 검증할 수 없다.
            { label: '업무 데이터',
              value: readiness === null ? '확인하지 못함'
                : readiness.length === 0 ? '적용된 업무키트 없음'
                  : readiness.map((x: any) => `${x.업무키트} ${x.준비상태}`).join(' · ') },
          ] : []}
          quickQuestions={[
            //: ★ 로드맵 §3 의 2번 칸이 정한 질문을 화면이 먼저 제안한다.
            '원료 도입계획을 관리하려면 무엇이 필요한가?',
            '왜 이 판단입니까?',
            '데이터가 부족합니까?',
            '관련 SW·에이전트 상태는 어떻습니까?',
            '시나리오로 보면 어떻게 됩니까?',
          ]} />
      </aside>

      {/* §5.1 Decision Drawer — 520px · Summary→Impact→Evidence→Related→Approval→History */}
      {drawer && (
        <DecisionDrawer item={drawer} onClose={() => setDrawer(null)}
          onOpenRef={(refType) => {
            //: 참조 종류로 «어느 화면으로 가야 하는가» 를 정한다. 모르는 종류는 서랍을 닫지
            //: 않는다 — 아무 데도 못 가면서 화면만 닫히면 사용자는 무엇이 됐는지 모른다.
            const t = (refType || '').toLowerCase();
            if (t.includes('release') || t.includes('promotion')) onOpenMenu('workspace');
            else if (t.includes('contract') || t.includes('data')) onOpenMenu('governance');
            else if (t.includes('agent') || t.includes('asset')) onOpenMenu('agentgov');
            else onOpenMenu('briefing');
          }} />
      )}
    </div>
  );
}
