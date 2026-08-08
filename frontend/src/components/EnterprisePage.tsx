// [UI 설계서 §3.1 · §5.1] `/enterprise` — **경영 홈(Decision Canvas).**
//
// ## 왜 이 화면이 첫 화면인가
//
// 설계서 §3.2 는 화면을 두 유형으로 나눈다: **Decision Canvas(경영 홈)** 와
// **Immersive Studio**(Software Factory·Agent Studio·Digital Twin). 그리고 §3.4 는
// 「경영 홈에서 Studio 로 이동한다」고 방향을 못박는다.
//
// 그런데 실제 첫 화면은 **「신규 프로젝트 개설」 폼**이었다 — 2026-07-28 리버스엔지니어링
// 문서가 기술한 AS-IS 그대로다. 화면 이관(트랙 C·F)은 개별 화면을 허브로 옮겼을 뿐
// **첫 화면 구조는 손대지 않았다.** 그래서 제품을 열면 「무엇을 결정해야 하는가」가 아니라
// 「프로젝트 ID 를 입력하십시오」가 먼저 나왔다.
//
// ## 레이아웃 (§3.1 데스크톱 기준)
//
//   Top Bar 72 / Decision Rail 280 / 중앙 최소 720 / Atlas Rail 360
//
// ## ⚠️ 데이터를 지어내지 않는다
//
// Decision Queue·Trust Foundation 은 **전사 브리핑**(`/api/v1/briefing`)이 이미 주는 것을
// 쓴다 — 「내가 결정할 것 · 막힌 것 · 데이터 상태 · 비용」이 설계의 구획과 그대로 맞는다.
// 없는 지표를 만들어 채우지 않고, 못 받은 구획은 **왜 비었는지**를 적는다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { Banner } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import {
  SECTION_LABELS, fetchBriefing,
  type Briefing, type BriefingItem,
} from '../lib/briefingApi';
import { getEnterpriseContext } from '../lib/api';

/** §4.2 DecisionQueue 의 상태. 색만으로 전달하지 않는다(§4.1 금지 조항과 같은 사상). */
const SEVERITY: Record<string, { label: string; tone: string }> = {
  high: { label: '긴급', tone: 'danger' },
  medium: { label: '확인 필요', tone: 'warn' },
  low: { label: '참고', tone: 'muted' },
  info: { label: '정보', tone: 'data' },
};

type QueueRow = BriefingItem & { section: string };

export function EnterprisePage({ onOpenBuild, onOpenMenu }: {
  onOpenBuild: () => void;
  onOpenMenu: (id: string) => void;
}) {
  const [data, setData] = useState<Loaded<Briefing>>(loading<Briefing>());
  const [selected, setSelected] = useState<QueueRow | null>(null);

  const load = useCallback(async () => {
    setData(loading<Briefing>());
    try {
      //: ⚠️ `fetchBriefing()` 은 **`{ data, permission }` 봉투**를 돌려준다 — 봉투째 넣으면
      //:   `sections` 가 undefined 가 되어 화면이 **오류 없이 전부 «—»** 를 그린다.
      //:   (2026-08-09: 오전에 `agent-governance` 에서 고친 것과 같은 유형을 여기서 반복했다.
      //:    봉투를 벗기는 곳이 API 래퍼마다 다르면 소비자가 매번 틀린다.)
      const r = await fetchBriefing();
      setData(ok(r.data));
    } catch (e) {
      setData(failed<Briefing>(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const d = data.value;

  /** §4.2 — 큐는 「내가 결정할 것」과 「막힌 것」을 합친다. 둘은 사용자가 **답해야 하는** 점에서
   *  같고, 나눠 두면 어느 쪽을 먼저 볼지 사용자가 매번 고르게 된다. */
  const rows = useMemo<QueueRow[]>(() => {
    if (!d) return [];
    const out: QueueRow[] = [];
    for (const key of ['my_decisions', 'blocked'] as const) {
      const sec = (d.sections as any)?.[key];
      for (const it of (sec?.items || [])) out.push({ ...it, section: key });
    }
    const order = { high: 0, medium: 1, low: 2, info: 3 } as Record<string, number>;
    return out.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9));
  }, [d]);

  useEffect(() => {
    if (!selected && rows.length) setSelected(rows[0]);
  }, [rows, selected]);

  /** §5.1 — 상단 KPI 는 **최대 4개**. 「업무 도메인 / Master Data / 연결 / 근거 충실도」가
   *  기본이지만, 서버가 주지 않는 값을 지어내지 않고 **브리핑이 실제로 세는 것**을 쓴다. */
  const kpis = useMemo(() => {
    const sec = (k: string) => (d?.sections as any)?.[k];
    const cost = sec('cost') || {};
    return [
      { label: '내가 결정할 것', value: sec('my_decisions')?.count ?? null,
        hint: '답해야 넘어갑니다' },
      { label: '막혀 있는 것', value: sec('blocked')?.count ?? null,
        hint: '누군가 풀어야 합니다' },
      { label: '데이터 상태', value: sec('data_health')?.count ?? null,
        hint: '계약·최신성 경고' },
      {
        label: 'LLM 비용',
        value: cost.available === false ? null : (cost.cost_usd ?? null),
        hint: cost.available === false ? (cost.reason || '집계할 수 없습니다')
          : `${cost.calls ?? 0}콜${cost.cost_complete === false ? ' · 일부 미가격' : ''}`,
        money: true,
      },
    ];
  }, [d]);

  const ctx = getEnterpriseContext();

  return (
    <div className="afs-scope afs-page" style={{ minHeight: '100vh' }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(240px, 280px) minmax(0, 1fr) minmax(300px, 360px)',
        gap: 0, alignItems: 'stretch', minHeight: 'calc(100vh - 72px)',
      }}>
        {/* ── 좌 280: Decision Queue (§4.2) ─────────────────────────── */}
        <aside className="afs-border" style={{
          borderRightWidth: 1, borderRightStyle: 'solid', padding: '14px 12px',
          display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <b style={{ fontSize: 14 }}>결정 대기</b>
            <span className="afs-muted" style={{ fontSize: 12 }}>
              {data.status === 'ok' ? `${rows.length}건` : ''}
            </span>
          </div>

          {data.status !== 'ok' ? (
            <EmptyOrError state={data.status} error={data.error}
              emptyText="지금 답해야 할 것이 없습니다." onRetry={load} />
          ) : rows.length === 0 ? (
            <p className="afs-muted" style={{ fontSize: 13 }}>
              지금 답해야 할 것이 없습니다.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
              {rows.map((r, i) => {
                const sev = SEVERITY[r.severity] || SEVERITY.info;
                const on = selected === r;
                return (
                  <button key={`${r.ref}-${i}`} onClick={() => setSelected(r)}
                    className="afs-border"
                    style={{
                      /* §4.2 행 높이 최소 84px */
                      minHeight: 84, textAlign: 'left', padding: '10px 11px',
                      borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                      background: on ? 'var(--afs-bg-raised, rgba(127,127,127,.12))' : 'transparent',
                      display: 'flex', flexDirection: 'column', gap: 5, cursor: 'pointer',
                    }}>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <span className={`state-chip ${sev.tone}`} style={{ fontSize: 11 }}>
                        {sev.label}
                      </span>
                      <span className="afs-muted" style={{ fontSize: 11 }}>
                        {SECTION_LABELS[r.section as keyof typeof SECTION_LABELS] || r.section}
                      </span>
                    </div>
                    <span style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.35 }}>
                      {r.title}
                    </span>
                    <span className="afs-muted" style={{ fontSize: 11.5, lineHeight: 1.35 }}>
                      {r.why}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        {/* ── 중앙: KPI + 업무 노드 + Decision Focus + Trust Foundation ── */}
        <main style={{ padding: '14px 16px', minWidth: 0, display: 'flex',
          flexDirection: 'column', gap: 14 }}>
          {/* §5.1 상단 KPI 최대 4개 */}
          <div style={{ display: 'grid', gap: 10,
            gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
            {kpis.map((k) => (
              <div key={k.label} className="afs-border" style={{
                borderWidth: 1, borderStyle: 'solid', borderRadius: 10, padding: '10px 12px',
              }}>
                <div className="afs-muted" style={{ fontSize: 11.5 }}>{k.label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.2 }}>
                  {/* ⚠️ 「모른다」를 0 으로 쓰지 않는다 — 0 은 «없다» 이고 «못 셌다» 와 다르다. */}
                  {k.value === null || k.value === undefined ? '—'
                    : k.money ? `$${Number(k.value).toFixed(2)}` : k.value}
                </div>
                <div className="afs-muted" style={{ fontSize: 11 }}>{k.hint}</div>
              </div>
            ))}
          </div>

          {/* §5.1 중앙 하단: Decision Focus */}
          <section className="afs-border" style={{
            borderWidth: 1, borderStyle: 'solid', borderRadius: 10, padding: 14,
            display: 'flex', flexDirection: 'column', gap: 8, minHeight: 190,
          }}>
            <div className="afs-muted" style={{ fontSize: 11, letterSpacing: '.08em' }}>
              DECISION FOCUS
            </div>
            {!selected ? (
              <p className="afs-muted" style={{ fontSize: 13, margin: 0 }}>
                왼쪽에서 하나를 고르면 여기에 근거와 다음 행동이 나옵니다.
              </p>
            ) : (
              <>
                <h2 style={{ fontSize: 17, margin: 0, lineHeight: 1.35 }}>{selected.title}</h2>
                <p style={{ fontSize: 13, margin: 0, lineHeight: 1.55 }}>{selected.why}</p>
                {selected.suggested_action && (
                  <div className="afs-border" style={{
                    borderWidth: 1, borderStyle: 'solid', borderRadius: 8, padding: '9px 11px',
                  }}>
                    <div className="afs-muted" style={{ fontSize: 11 }}>다음 행동</div>
                    <div style={{ fontSize: 13 }}>{selected.suggested_action}</div>
                  </div>
                )}
                <div className="afs-muted" style={{ fontSize: 11.5 }}>
                  {selected.ref_type ? `${selected.ref_type} · ` : ''}{selected.ref || '참조 없음'}
                </div>
              </>
            )}
          </section>

          {/* §4.6 TrustFoundationStrip — 숫자보다 «상태의 완전성과 기준시각» 을 먼저 */}
          <section>
            <div className="afs-muted" style={{ fontSize: 11, letterSpacing: '.08em',
              marginBottom: 6 }}>TRUST FOUNDATION</div>
            <div style={{ display: 'grid', gap: 10,
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
              {(['data_health', 'programs'] as const).map((key) => {
                const sec = (d?.sections as any)?.[key];
                const n = sec?.count;
                return (
                  <div key={key} className="afs-border" style={{
                    borderWidth: 1, borderStyle: 'solid', borderRadius: 10, padding: '10px 12px',
                  }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700 }}>
                      {SECTION_LABELS[key]}
                    </div>
                    <div className="afs-muted" style={{ fontSize: 12, marginTop: 4 }}>
                      {data.status !== 'ok' ? '확인하지 못했습니다'
                        : n === undefined ? '집계 없음'
                          : n === 0 ? '경고 없음'
                            : `${n}건 확인 필요`}
                    </div>
                    {(sec?.items || []).slice(0, 2).map((it: BriefingItem, i: number) => (
                      <div key={i} className="afs-muted"
                        style={{ fontSize: 11.5, marginTop: 5, lineHeight: 1.35 }}>
                        · {it.title}
                      </div>
                    ))}
                  </div>
                );
              })}
              <div className="afs-border" style={{
                borderWidth: 1, borderStyle: 'solid', borderRadius: 10, padding: '10px 12px',
              }}>
                <div style={{ fontSize: 12.5, fontWeight: 700 }}>기준시각</div>
                <div className="afs-muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {d?.generated_at ? new Date(d.generated_at).toLocaleString() : '—'}
                </div>
                <div className="afs-muted" style={{ fontSize: 11.5, marginTop: 5 }}>
                  실행 문맥 {ctx.entityMode || 'REAL'} · {ctx.scopeNodeId || '조직 미지정'}
                </div>
              </div>
            </div>
          </section>

          {/* §3.4 — 경영 홈에서 Studio 로 이동한다. 그 방향을 화면에 남긴다. */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="primary-button" onClick={onOpenBuild}>
              🏭 업무 SW 만들기 — Software Factory
            </button>
            <button className="secondary-button" onClick={() => onOpenMenu('advisor')}>
              🧭 무엇을 만들지 상담
            </button>
            <button className="secondary-button" onClick={() => onOpenMenu('collaboration')}>
              🤝 협업·의사결정·발간
            </button>
          </div>
        </main>

        {/* ── 우 360: Atlas (§4.7) ──────────────────────────────────── */}
        <aside className="afs-border" style={{
          borderLeftWidth: 1, borderLeftStyle: 'solid', minWidth: 0, padding: 10,
        }}>
          <JarvisRail
            contextTitle="경영 홈"
            contextDescription="지금 답해야 할 것과 그 근거를 봅니다."
            context={{
              current_module: 'enterprise',
              selected_object_type: selected?.ref_type || '',
              selected_object_id: selected?.ref || '',
              object_snapshot: selected ? {
                title: selected.title, severity: selected.severity, section: selected.section,
              } : { queue: rows.length },
              available_actions: [],
              evidence_refs: [],
            }}
            evidence={data.status === 'ok' ? [
              { label: '결정 대기', value: `${rows.length}건` },
              { label: '기준시각', value: d?.generated_at
                ? new Date(d.generated_at).toLocaleTimeString() : '—' },
            ] : []}
            quickQuestions={[
              '왜 이 판단입니까?',
              '데이터가 부족합니까?',
              '관련 SW·에이전트 상태는 어떻습니까?',
              '시나리오로 보면 어떻게 됩니까?',
            ]} />
        </aside>
      </div>
    </div>
  );
}
