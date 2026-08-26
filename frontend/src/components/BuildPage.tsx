// [UI 설계서 §5.2] `/build` — **Software Factory 목록면.**
//
// ## 설계가 못박은 것
//
// · 상단: `새 업무 만들기` 와 **진행 상태 필터**
// · 본문: **미완료 / 내 프로젝트 / Mega / Releases / Archive**
// · 프로젝트 **카드 최소 320px, 최대 3열**
// · 카드 **주 CTA 는 `열기`**, 보조 메뉴에 목록에서 내리기·관리
//
// ## 왜 다시 만드는가
//
// 종전 화면은 열자마자 **「신규 프로젝트 개설」 폼**이 본문을 차지했다(2026-07-28 AS-IS).
// 설계는 `/build` 를 **목록면**으로 규정하고 생성은 `새 업무 만들기` → `/build/start` 로
// 분리한다 — 목록이 먼저 보여야 「이미 있는 것을 여는」 흔한 일이 한 번에 되고, 만들기는
// 결정이 필요한 별도 흐름이 된다.
//
// ⚠️ §1.3 최소 크기: 본문 14px+ / 보조 12px+ / 버튼 13px+·36px+ / 핵심 42~48px.
// ⚠️ §2.4 간격: 화면 24~32 · 카드 내부 16~20 · gap 16 · 버튼 r6 · 카드 r8.
import { useEffect, useMemo, useState } from 'react';

import { useFactoryStore } from '../store/useFactoryStore';
import { shortId } from '../lib/displayId';
import { listInstances, listKitApps, type KitAppRow } from '../lib/dataPrepApi';

//: 문맥 축에서 막힌 사유를 사람 말로. **정상 격리**와 **점검 대상**을 다르게 말한다.
const CTX_KO: Record<string, string> = {
  TENANT_MISMATCH: '다른 회사 문맥의 자료',
  MODE_MISMATCH: '다른 실행 문맥(가상·검증 샌드박스)',
  SCOPE_OUTSIDE: '선택한 조직 범위 밖',
  RESOURCE_UNBOUND: '⚠️ 소유 조직이 기록되지 않음 — 점검 필요',
  CONTEXT_MISSING: '⚠️ 실행 문맥을 확정하지 못함 — 점검 필요',
  LOOKUP_FAILED: '⚠️ 조직 계층을 읽지 못함 — 점검 필요',
};

const MODE_KO: Record<string, string> = {
  REAL: '실제 운영', VIRTUAL: '가상', SANDBOX: '검증 샌드박스',
};

/** ★★★ [G1-C3] **「왜 안 보이는가」를 화면이 말한다.**
 *
 * 서버는 목록과 함께 `viewing_context`·`context_blocked_count`·사유별 집계를 준다. 그것을
 * 그리지 않으면 **격리된 자료가 그냥 「0건」으로 보이고**, 사용자는 통제를 고장으로 읽는다.
 * 실측(2026-08-13, 관리자): 보임 2건 · 차단 **59건**(전부 다른 실행 문맥). 즉 이 안내가 없으면
 * 화면은 「프로젝트가 두 개뿐인 제품」처럼 보인다.
 *
 * ⚠️ 조회 실패를 «0건» 으로 그리지 않는다(§6.4). 트랙 F 가 8개 화면에서 고친 결함 유형이며,
 *   여기서 다시 만들지 않는다.
 * ⚠️ 서버가 값을 안 주면(`null`) **아무 말도 하지 않는다** — 「가려진 것 없음」이라고 단정하면
 *   옛 서버에 붙었을 때 거짓말이 된다. */
function ProjectVisibilityNotice({ companyName, scopeLabel, entityMode }: {
  companyName: string; scopeLabel: string; entityMode: string;
}) {
  const load = useFactoryStore((s) => s.projectsLoad);
  const err = useFactoryStore((s) => s.projectsError);
  const ctx = useFactoryStore((s) => s.viewingContext);
  const blocked = useFactoryStore((s) => s.contextBlocked);
  const attention = useFactoryStore((s) => s.contextNeedsAttention);
  const reasons = useFactoryStore((s) => s.contextBlockedReasons);
  const refetch = useFactoryStore((s) => s.fetchProjects);

  const box = (tone: 'error' | 'warn' | 'info', body: React.ReactNode) => (
    <div style={{
      border: `1px solid var(--${tone === 'error' ? 'state-danger' : tone === 'warn' ? 'state-warn' : 'surface-border'})`,
      background: 'var(--surface-card)', color: 'var(--surface-text)',
      borderRadius: 8, padding: '12px 16px', fontSize: 13, lineHeight: 1.6,
    }}>{body}</div>
  );

  if (load === 'loading') return null;                 // 로딩은 목록 자리가 이미 말한다
  if (load === 'forbidden') {
    return box('error', <><b>목록을 볼 권한이 없습니다.</b>{' '}
      <span style={{ opacity: .85 }}>{err}</span>{' '}
      <span style={{ opacity: .7 }}>— 자료가 없는 것이 아닙니다.</span></>);
  }
  if (load === 'failed') {
    return box('error', <>
      <b>목록을 불러오지 못했습니다 — 「0건」이 아닙니다.</b>{' '}
      <span style={{ opacity: .85 }}>{err}</span>{' '}
      <button onClick={() => { void refetch(); }} style={{
        marginLeft: 8, height: 30, padding: '0 12px', fontSize: 13, borderRadius: 6,
        cursor: 'pointer', border: '1px solid var(--surface-border)',
        background: 'var(--surface-page)', color: 'var(--surface-text)',
      }}>다시 시도</button></>);
  }

  const modeKo = MODE_KO[String(entityMode || ctx?.entity_mode || '')]
    || entityMode || ctx?.entity_mode || '';
  const contextTxt = [companyName, scopeLabel].filter(Boolean).join(' · ');
  const hasBlocked = typeof blocked === 'number' && blocked > 0;
  const needsFix = typeof attention === 'number' && attention > 0;

  if (!ctx && !hasBlocked) return null;                // 서버가 아무것도 알려 주지 않았다

  return box(needsFix ? 'warn' : 'info', <>
    {ctx && (
      <div style={{ fontSize: 12, opacity: .8 }}>
        지금 보는 문맥 — <b>{modeKo}</b>{contextTxt ? ` · ${contextTxt}` : ''}
      </div>
    )}
    {hasBlocked && (
      <div style={{ marginTop: ctx ? 6 : 0 }}>
        이 문맥 밖이라 <b>{blocked}건</b>을 목록에서 제외했습니다
        {needsFix ? <> — 그중 <b style={{ color: 'var(--state-warn)' }}>{attention}건은 점검이 필요</b>합니다</> : null}.
        {reasons && <details style={{ marginTop: 5, fontSize: 12 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--surface-text-muted)' }}>
            제외 사유 보기
          </summary>
          <ul style={{ margin: '5px 0 0', paddingLeft: 18, opacity: .9 }}>
            {Object.entries(reasons).map(([k, n]) => (
              <li key={k}>{CTX_KO[k] || k} — {n}건</li>
            ))}
          </ul>
        </details>}
      </div>
    )}
  </>);
}

type Project = {
  id: string; name?: string; initial_idea?: string;
  is_mega_project?: boolean; parent_project_id?: string;
  total_tasks?: number; completed_tasks?: number;
};

type Bucket = 'active' | 'mine' | 'mega' | 'releases' | 'archive';

const BUCKETS: { id: Bucket; label: string; hint: string }[] = [
  { id: 'active', label: '미완료', hint: '완료되지 않았거나 진행률을 아직 집계하지 못한 작업' },
  { id: 'mine', label: '내 프로젝트', hint: '내가 만든 독립 프로젝트' },
  { id: 'mega', label: '통합 프로젝트', hint: '여러 프로젝트를 묶어 운영하는 상위 단위' },
  { id: 'releases', label: '릴리스', hint: '게시된 결과물과 현재 운영 상태' },
  { id: 'archive', label: '보관함', hint: '더 진행하지 않는 것' },
];

const card: React.CSSProperties = {
  background: 'var(--surface-card)', border: '1px solid var(--surface-border)',
  borderRadius: 8, padding: 18,
};

function localTime(raw: string): string {
  const value = String(raw || '').trim();
  if (!value) return '게시 시각 미기록';
  // 시간대가 적힌 값만 현지시각으로 바꾼다. 시간대 없는 옛 기록을 UTC라고 추측하면
  // 실제보다 9시간 밀린 시각을 사람이 사실로 읽는다.
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

function lifecycleView(row: any, kitApp?: KitAppRow) {
  if (row.lifecycle_status === 'disabled') {
    return { label: '사용 중단', tone: 'var(--state-error-fg)', detail: row.lifecycle_reason || '' };
  }
  if (row.lifecycle_status === 'deprecated') {
    return { label: '중단 예고', tone: 'var(--state-warn-fg)', detail: row.lifecycle_reason || '' };
  }
  if (kitApp?.lifecycle_state === 'active' || row.is_enterprise) {
    return { label: '운영 중', tone: 'var(--state-success-fg)', detail: '인증된 업무 데이터를 읽습니다.' };
  }
  if (kitApp?.lifecycle_state === 'candidate') {
    return { label: '운영 후보', tone: 'var(--state-warn-fg)', detail: '운영 전환 전의 후보 판입니다.' };
  }
  return {
    label: row.lifecycle_recorded ? '사용 가능' : '사용 상태 미기록',
    tone: row.lifecycle_recorded ? 'var(--state-success-fg)' : 'var(--surface-text-muted)',
    detail: row.lifecycle_recorded ? '' : '기존 릴리스로, 관리자의 사용 상태 기록이 없습니다.',
  };
}

export function BuildPage({
  projects, releases, companyName, scopeLabel, entityMode,
  onOpenProject, onOpenRelease, onManageRelease, onDeleteProject,
}: {
  projects: Project[];
  releases: any[];
  companyName: string;
  scopeLabel: string;
  entityMode: string;
  onOpenProject: (id: string) => void;
  onOpenRelease: (releaseId: string) => void;
  onManageRelease: (r: any) => void;
  onDeleteProject: (id: string) => void;
}) {
  const [bucket, setBucket] = useState<Bucket>('active');
  const [q, setQ] = useState('');
  const [kitApps, setKitApps] = useState<Record<string, KitAppRow>>({});

  // 키트 앱 릴리스는 `project_name`이 내부 release_id와 같을 수 있다. 그 문자열을 잘라
  // 이름을 만들지 않고, 현재 조직에서 볼 수 있는 적용본의 앱 계약이 준 이름을 결속한다.
  useEffect(() => {
    let alive = true;
    listInstances()
      .then(async (d) => {
        const groups = await Promise.allSettled(
          (d.instances || []).map((row: any) => listKitApps(String(row.instance_id || ''))),
        );
        if (!alive) return;
        const next: Record<string, KitAppRow> = {};
        for (const group of groups) {
          if (group.status !== 'fulfilled') continue;
          for (const app of group.value.apps || []) {
            if (app.release_id) next[app.release_id] = app;
          }
        }
        setKitApps(next);
      })
      .catch(() => { /* 이름 보강 실패가 릴리스 목록 자체를 0건으로 만들면 안 된다 */ });
    return () => { alive = false; };
  }, []);

  const progress = (p: Project) => {
    const t = Number(p.total_tasks || 0);
    const c = Number(p.completed_tasks || 0);
    return { t, c, pct: t > 0 ? Math.round((c / t) * 100) : null };
  };

  const filtered = useMemo(() => {
    const key = q.trim().toLowerCase();
    const match = (p: Project) => !key
      || (p.id || '').toLowerCase().includes(key)
      || (p.name || '').toLowerCase().includes(key);
    const list = (projects || []).filter(match);
    if (bucket === 'mega') return list.filter((p) => p.is_mega_project);
    if (bucket === 'mine') return list.filter((p) => !p.is_mega_project);
    if (bucket === 'active') {
      // ⚠️ 「진행 중」의 정의를 지어내지 않는다 — 서버가 진행 상태를 따로 주지 않으므로
      //   **완료되지 않은 것**으로 본다. 그 기준을 화면에 적는다.
      return list.filter((p) => {
        const { t, c } = progress(p);
        return t === 0 || c < t;
      });
    }
    if (bucket === 'archive') {
      return list.filter((p) => {
        const { t, c } = progress(p);
        return t > 0 && c >= t;
      });
    }
    return list;
  }, [projects, bucket, q]);

  const releaseRows = useMemo(() => {
    const key = q.trim().toLowerCase();
    return (releases || []).filter((r: any) => !key
      || String(r.release_id || '').toLowerCase().includes(key)
      || String(r.project_name || '').toLowerCase().includes(key));
  }, [releases, q]);

  const count = (b: Bucket) => {
    if (b === 'releases') return (releases || []).length;
    const list = projects || [];
    if (b === 'mega') return list.filter((p) => p.is_mega_project).length;
    if (b === 'mine') return list.filter((p) => !p.is_mega_project).length;
    if (b === 'active') return list.filter((p) => {
      const { t, c } = progress(p); return t === 0 || c < t;
    }).length;
    return list.filter((p) => { const { t, c } = progress(p); return t > 0 && c >= t; }).length;
  };

  return (
    <div className="afs-scope" style={{
      background: 'var(--surface-page)', minHeight: 'calc(100vh - 74px)', padding: 24,
      display: 'flex', flexDirection: 'column', gap: 16,
    }}>
      <div>
        <small style={{ display: 'block', color: 'var(--ls-red)', fontSize: 11,
          fontWeight: 800, letterSpacing: '.1em' }}>APP FACTORY</small>
        <h1 style={{ margin: '5px 0 4px', color: 'var(--surface-text)',
          fontSize: 26, lineHeight: 1.25 }}>앱 제작</h1>
        <p style={{ margin: 0, color: 'var(--surface-text-muted)', fontSize: 14 }}>
          현업의 요구를 앱과 시뮬레이터로 만들고, 진행 상태와 릴리스를 관리합니다.
        </p>
      </div>

      <ProjectVisibilityNotice companyName={companyName} scopeLabel={scopeLabel}
        entityMode={entityMode} />

      {/* ── 상단: 찾기 + 진행 상태 필터 (§5.2) ───────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="이름 또는 ID로 찾기"
            style={{
              height: 38, minWidth: 220, padding: '0 12px', fontSize: 14, borderRadius: 6,
              border: '1px solid var(--surface-border)', background: 'var(--surface-card)',
              color: 'var(--surface-text)',
            }} />
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {BUCKETS.map((b) => {
            const on = bucket === b.id;
            return (
              <button key={b.id} onClick={() => setBucket(b.id)} title={b.hint}
                style={{
                  height: 36, padding: '0 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
                  border: `1px solid ${on ? 'var(--ls-navy)' : 'var(--surface-border)'}`,
                  background: on ? 'var(--action-primary-bg)' : 'var(--surface-card)',
                  color: on ? 'var(--action-primary-fg)' : 'var(--surface-text-muted)',
                  fontWeight: on ? 700 : 500,
                }}>
                {b.label} <span style={{ opacity: .8 }}>{count(b.id)}</span>
              </button>
            );
          })}
        </div>
      </div>

      <p style={{ fontSize: 12, color: 'var(--surface-text-faint)', margin: 0 }}>
        {BUCKETS.find((b) => b.id === bucket)?.hint}
        {bucket === 'active' && ' — 서버가 실행 상태를 제공하지 않은 항목은 «진행률 집계 전»으로 구분합니다.'}
      </p>

      {/* ── 본문: 카드 최소 320px · 최대 3열 (§5.2) ───────────────────── */}
      {bucket === 'releases' ? (
        releaseRows.length === 0 ? (
          <p style={{ fontSize: 14, color: 'var(--surface-text-muted)' }}>
            전달 가능한 결과물이 없습니다.
          </p>
        ) : (
          <div style={{ display: 'grid', gap: 16,
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', maxWidth: 1180 }}>
            {releaseRows.map((r: any) => {
              const kitApp = kitApps[String(r.release_id || '')];
              const displayName = kitApp?.label || r.project_name || '이름 없는 릴리스';
              const state = lifecycleView(r, kitApp);
              return (
              <div key={r.release_id} style={card}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--surface-text)' }}>
                  📦 {displayName}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
                  marginTop: 5, fontSize: 12 }}>
                  {kitApp?.app_id && <span style={{ color: 'var(--surface-text-muted)' }}>
                    업무 앱 {kitApp.app_id}
                  </span>}
                  <strong style={{ color: state.tone }}>{state.label}</strong>
                </div>
                {state.detail && <div style={{ fontSize: 12, marginTop: 4,
                  color: 'var(--surface-text-muted)' }}>{state.detail}</div>}
                <div style={{ fontSize: 12, marginTop: 4, color: 'var(--surface-text-muted)' }}>
                  게시 {localTime(r.created_at)}
                </div>
                <details style={{ fontSize: 11, marginTop: 7, color: 'var(--surface-text-faint)' }}>
                  <summary style={{ cursor: 'pointer' }}>식별 정보</summary>
                  <div style={{ fontFamily: 'var(--font-mono, monospace)', marginTop: 3 }}
                    title={r.release_id}>{shortId(r.release_id)}</div>
                </details>
                <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                  <button onClick={() => onOpenRelease(String(r.release_id || ''))} style={{
                    height: 36, padding: '0 16px', fontSize: 13, fontWeight: 700, borderRadius: 6,
                    cursor: 'pointer', border: '1px solid var(--ls-navy)',
                    background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
                  }} title="게시된 앱 또는 결과 화면을 엽니다">앱 실행</button>
                  <button onClick={() => onManageRelease({ ...r, display_name: displayName })} style={{
                    height: 36, padding: '0 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
                    border: '1px solid var(--action-secondary-border)',
                    background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
                  }} title="사용 상태·운영 승격·중단 이력을 관리합니다">릴리스 관리</button>
                </div>
                <div style={{ fontSize: 11.5, marginTop: 7, color: 'var(--surface-text-faint)' }}>
                  앱 실행은 결과 화면 · 릴리스 관리는 사용 상태와 운영 전환
                </div>
              </div>
            );})}
          </div>
        )
      ) : filtered.length === 0 ? (
        <div style={{ ...card, maxWidth: 560 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--surface-text)' }}>
            여기에 표시할 것이 없습니다.
          </div>
          <p style={{ fontSize: 14, marginTop: 6, color: 'var(--surface-text-muted)' }}>
            {q ? '검색어와 맞는 것이 없습니다.' : '상단의 «＋ 새 업무»로 시작하십시오.'}
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 16,
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', maxWidth: 1180 }}>
          {filtered.map((p) => {
            const { t, c, pct } = progress(p);
            return (
              <div key={p.id} style={card}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  {p.is_mega_project && (
                    <span style={{ fontSize: 12, fontWeight: 700, padding: '1px 7px',
                      borderRadius: 6, color: '#6d28d9', background: '#ede9fe' }}>통합</span>
                  )}
                  <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--surface-text)' }}>
                    {p.name || p.id}
                  </span>
                </div>
                <div style={{ fontSize: 11, marginTop: 4, fontFamily: 'var(--font-mono, monospace)',
                  color: 'var(--surface-text-faint)' }}>{p.id}</div>
                {p.initial_idea && (
                  <p style={{ fontSize: 13, marginTop: 8, lineHeight: 1.5,
                    color: 'var(--surface-text-muted)',
                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                    overflow: 'hidden' }}>{p.initial_idea}</p>
                )}

                {/* 진행률 — ⚠️ 총 태스크가 0이면 «0%» 가 아니라 «집계 전» 이다. */}
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                    {pct === null ? '진행률 집계 전' : `${c} / ${t} 단계 · ${pct}%`}
                  </div>
                  <div style={{ height: 6, borderRadius: 3, marginTop: 6,
                    background: 'var(--surface-sunken)', overflow: 'hidden' }}>
                    <div style={{ width: `${pct ?? 0}%`, height: '100%',
                      background: pct === 100 ? 'var(--state-success-fg)' : 'var(--ls-navy)' }} />
                  </div>
                </div>

                {/* §5.2 주 CTA 는 «열기». 이 동작은 삭제가 아니라 목록 비노출이므로 이름도 사실대로 쓴다. */}
                <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
                  <button onClick={() => onOpenProject(p.id)} style={{
                    height: 36, padding: '0 18px', fontSize: 13, fontWeight: 700, borderRadius: 6,
                    cursor: 'pointer', border: '1px solid var(--ls-navy)',
                    background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
                  }}>열기</button>
                  <button onClick={() => onDeleteProject(p.id)} style={{
                    height: 36, padding: '0 12px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
                    border: '1px solid var(--action-secondary-border)',
                    background: 'var(--action-secondary-bg)',
                    color: 'var(--action-danger-quiet-fg)',
                  }}>목록에서 내리기</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
