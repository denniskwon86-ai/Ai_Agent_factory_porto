// [UI 설계서 §5.2] `/build` — **Software Factory 목록면.**
//
// ## 설계가 못박은 것
//
// · 상단: `새 업무 만들기` 와 **진행 상태 필터**
// · 본문: **진행 중 / 내 프로젝트 / Mega / Releases / Archive**
// · 프로젝트 **카드 최소 320px, 최대 3열**
// · 카드 **주 CTA 는 `열기`**, 보조 메뉴에 복제·삭제·관리
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
import { useMemo, useState } from 'react';

type Project = {
  id: string; name?: string; initial_idea?: string;
  is_mega_project?: boolean; parent_project_id?: string;
  total_tasks?: number; completed_tasks?: number;
};

type Bucket = 'active' | 'mine' | 'mega' | 'releases' | 'archive';

const BUCKETS: { id: Bucket; label: string; hint: string }[] = [
  { id: 'active', label: '진행 중', hint: '지금 돌고 있는 작업' },
  { id: 'mine', label: '내 프로젝트', hint: '내가 만든 독립 프로젝트' },
  { id: 'mega', label: 'Mega', hint: '여러 프로젝트를 묶어 운영하는 상위 단위' },
  { id: 'releases', label: 'Releases', hint: '완성되어 전달 가능한 결과물' },
  { id: 'archive', label: 'Archive', hint: '더 진행하지 않는 것' },
];

const card: React.CSSProperties = {
  background: 'var(--surface-card)', border: '1px solid var(--surface-border)',
  borderRadius: 8, padding: 18,
};

export function BuildPage({
  projects, releases, onOpenProject, onOpenRelease, onNewWork, onManageRelease, onDeleteProject,
}: {
  projects: Project[];
  releases: any[];
  onOpenProject: (id: string) => void;
  onOpenRelease: (r: any) => void;
  onNewWork: () => void;
  onManageRelease: (r: any) => void;
  onDeleteProject: (id: string) => void;
}) {
  const [bucket, setBucket] = useState<Bucket>('active');
  const [q, setQ] = useState('');

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
      background: 'var(--surface-page)', minHeight: 'calc(100vh - 72px)', padding: 24,
      display: 'flex', flexDirection: 'column', gap: 16,
    }}>
      {/* ── 상단: 새 업무 만들기 + 진행 상태 필터 (§5.2) ─────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {/* 화면당 하나의 핵심 행동 — 높이 46px(§1.3 42~48) */}
          <button onClick={onNewWork} style={{
            height: 46, padding: '0 20px', fontSize: 14, fontWeight: 700, borderRadius: 6,
            cursor: 'pointer', border: '1px solid var(--ls-navy)',
            background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
          }}>＋ 새 업무 만들기</button>

          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="이름·ID 로 찾기"
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
        {bucket === 'active' && ' — 서버가 진행 상태를 따로 주지 않아 «완료되지 않은 것»으로 봅니다.'}
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
            {releaseRows.map((r: any) => (
              <div key={r.release_id} style={card}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--surface-text)' }}>
                  📦 {r.project_name || r.release_id}
                </div>
                <div style={{ fontSize: 11, marginTop: 4,
                  fontFamily: 'var(--font-mono, monospace)',
                  color: 'var(--surface-text-faint)' }}>{r.release_id}</div>
                <div style={{ fontSize: 12, marginTop: 4, color: 'var(--surface-text-muted)' }}>
                  {r.created_at || ''}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                  <button onClick={() => onOpenRelease(r)} style={{
                    height: 36, padding: '0 16px', fontSize: 13, fontWeight: 700, borderRadius: 6,
                    cursor: 'pointer', border: '1px solid var(--ls-navy)',
                    background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
                  }}>열기</button>
                  <button onClick={() => onManageRelease(r)} style={{
                    height: 36, padding: '0 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
                    border: '1px solid var(--action-secondary-border)',
                    background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
                  }}>관리</button>
                </div>
              </div>
            ))}
          </div>
        )
      ) : filtered.length === 0 ? (
        <div style={{ ...card, maxWidth: 560 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--surface-text)' }}>
            여기에 표시할 것이 없습니다.
          </div>
          <p style={{ fontSize: 14, marginTop: 6, color: 'var(--surface-text-muted)' }}>
            {q ? '검색어와 맞는 것이 없습니다.' : '«＋ 새 업무 만들기» 로 시작하십시오.'}
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
                      borderRadius: 6, color: '#6d28d9', background: '#ede9fe' }}>Mega</span>
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

                {/* §5.2 주 CTA 는 «열기» · 보조에 복제·삭제·관리 */}
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
                  }}>삭제</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
