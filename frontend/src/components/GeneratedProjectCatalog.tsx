import { useEffect, useMemo, useState } from 'react';

import { Panel, ScreenHead } from '../design/HubShell';
import { API_BASE_URL } from '../lib/api';
import { useFactoryStore } from '../store/useFactoryStore';

export type GeneratedProjectLink = {
  id: string;
  name: string;
  total_tasks?: number;
  completed_tasks?: number;
};

type Usage = {
  status: 'idle' | 'loading' | 'ok' | 'failed';
  calls: number;
  successRate: number;
  durationSeconds: number;
  costUsd: number | null;
  costComplete: boolean;
  message: string;
};

const PAGE_SIZE = 10;

function progressOf(project: GeneratedProjectLink) {
  const total = Number(project.total_tasks || 0);
  const completed = Number(project.completed_tasks || 0);
  return { total, completed, percent: total > 0 ? Math.min(100, Math.round(completed / total * 100)) : 0 };
}

export function GeneratedProjectCatalog({
  kindLabel, title, description, emptyText, actionLabel, projects, onOpen,
}: {
  kindLabel: string;
  title: string;
  description: string;
  emptyText: string;
  actionLabel: string;
  projects: GeneratedProjectLink[];
  onOpen: (id: string) => void;
}) {
  const load = useFactoryStore((state) => state.projectsLoad);
  const error = useFactoryStore((state) => state.projectsError);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'all' | 'working' | 'done'>('all');
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState('');
  const [usage, setUsage] = useState<Usage>({ status: 'idle', calls: 0, successRate: 0,
    durationSeconds: 0, costUsd: null, costComplete: false, message: '' });

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    return projects.filter((project) => {
      const progress = progressOf(project);
      const matchesQuery = !q || String(project.name || '').toLocaleLowerCase().includes(q);
      const matchesStatus = status === 'all'
        || (status === 'done' ? progress.total > 0 && progress.completed >= progress.total
          : progress.total === 0 || progress.completed < progress.total);
      return matchesQuery && matchesStatus;
    });
  }, [projects, query, status]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const shown = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const selected = filtered.find((project) => project.id === selectedId) || shown[0] || null;

  useEffect(() => { setPage(1); }, [query, status]);
  useEffect(() => {
    if (selected && selected.id !== selectedId) setSelectedId(selected.id);
  }, [selected, selectedId]);

  useEffect(() => {
    if (!selected?.name) {
      setUsage({ status: 'idle', calls: 0, successRate: 0, durationSeconds: 0,
        costUsd: null, costComplete: false, message: '' });
      return;
    }
    let alive = true;
    setUsage({ status: 'loading', calls: 0, successRate: 0, durationSeconds: 0,
      costUsd: null, costComplete: false, message: '' });
    // 로그 정본의 `project` 키는 내부 프로젝트 ID다. 표시명을 보내면 실적이 있는데도 0회가
    // 된다. ID는 조회 payload에만 쓰고 화면에는 노출하지 않는다.
    fetch(`${API_BASE_URL}/api/v1/telemetry/summary?project=${encodeURIComponent(selected.id)}`)
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body?.detail || `사용실적 조회 실패 (${response.status})`);
        const totals = body?.data?.totals || {};
        if (alive) setUsage({ status: 'ok', calls: Number(totals.calls || 0),
          successRate: Number(totals.success_rate || 0),
          durationSeconds: Number(totals.total_duration_s || 0),
          costUsd: totals.cost_usd === undefined ? null : Number(totals.cost_usd),
          costComplete: Boolean(totals.cost_complete), message: '' });
      })
      .catch((reason) => {
        if (alive) setUsage({ status: 'failed', calls: 0, successRate: 0, durationSeconds: 0,
          costUsd: null, costComplete: false, message: String(reason?.message || reason) });
      });
    return () => { alive = false; };
  }, [selected?.id]);

  const selectedProgress = selected ? progressOf(selected) : null;

  return (
    <div className="product-page-content" style={{ height: '100%', overflow: 'auto' }}>
      <ScreenHead kicker="GENERATED WORK" title={title} description={description}
        chip={{ label: load === 'ok' ? `${projects.length}개 관리 중` : '목록 확인 중',
          tone: load === 'ok' ? 'data' : 'muted' }} />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <input aria-label={`${kindLabel} 검색`} value={query} onChange={(event) => setQuery(event.target.value)}
          placeholder={`${kindLabel} 이름으로 검색`} style={{ minWidth: 260, height: 38, padding: '0 12px',
            borderRadius: 7, border: '1px solid var(--surface-border)',
            background: 'var(--surface-card)', color: 'var(--surface-text)', fontSize: 13 }} />
        <div className="filter-pills" aria-label="진행 상태 필터">
          {[['all', '전체'], ['working', '진행 중'], ['done', '완료']].map(([id, label]) => (
            <button key={id} className={status === id ? 'active' : ''}
              onClick={() => setStatus(id as typeof status)}>{label}</button>
          ))}
        </div>
      </div>

      {load === 'loading' ? <div className="empty-note">목록을 불러오는 중입니다.</div>
        : load === 'failed' || load === 'forbidden'
          ? <div className="empty-note" style={{ color: 'var(--state-error-fg)' }}>
              {error || '목록을 불러오지 못했습니다.'}
            </div>
          : filtered.length === 0 ? <div className="empty-note">{query ? '검색 조건에 맞는 항목이 없습니다.' : emptyText}</div>
            : <div className="afs-master-detail">
                <aside className="afs-master-list" aria-label={`${kindLabel} 목록`}>
                  <header><div><strong>{kindLabel}</strong><span>{filtered.length}개</span></div></header>
                  <div className="afs-master-list-body">
                    {shown.map((project) => {
                      const progress = progressOf(project);
                      return <button key={project.id} className={selected?.id === project.id ? 'selected' : ''}
                        onClick={() => setSelectedId(project.id)}>
                        <span className="afs-master-selector-copy">
                          <small>{progress.total > 0 && progress.completed >= progress.total ? '완료' : '진행 중'}</small>
                          <strong>{project.name || '이름 미등록 작업'}</strong>
                          <span>{progress.total > 0 ? `${progress.completed}/${progress.total} 단계` : '작업 준비됨'}</span>
                        </span>
                        <span aria-hidden="true">›</span>
                      </button>;
                    })}
                  </div>
                  {pageCount > 1 && <footer style={{ display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', padding: '8px 10px', borderTop: '1px solid var(--surface-border)' }}>
                    <button className="secondary-button" disabled={safePage <= 1}
                      onClick={() => setPage((value) => Math.max(1, value - 1))}>이전</button>
                    <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>{safePage} / {pageCount}</span>
                    <button className="secondary-button" disabled={safePage >= pageCount}
                      onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>다음</button>
                  </footer>}
                </aside>

                {selected && selectedProgress && <article className="afs-detail-pane">
                  <Panel kicker="SELECTED" title={selected.name || '이름 미등록 작업'}
                    action={<button className="primary-button" onClick={() => onOpen(selected.id)}>{actionLabel}</button>}>
                    <div style={{ padding: 16 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(110px, 1fr))', gap: 8 }}>
                        <Metric label="제작 진행" value={selectedProgress.total > 0
                          ? `${selectedProgress.percent}%` : '준비됨'} />
                        <Metric label="AI 작업 호출" value={usage.status === 'ok' ? `${usage.calls}회`
                          : usage.status === 'loading' ? '확인 중' : usage.status === 'failed' ? '조회 불가' : '기록 없음'} />
                        <Metric label="호출 성공률" value={usage.status === 'ok' && usage.calls > 0
                          ? `${Math.round(usage.successRate * 100)}%` : '—'} />
                        <Metric label="누적 처리시간" value={usage.status === 'ok' && usage.calls > 0
                          ? `${Math.round(usage.durationSeconds)}초` : '—'} />
                      </div>
                      <div style={{ marginTop: 14, height: 7, borderRadius: 4, overflow: 'hidden',
                        background: 'var(--surface-sunken)' }}>
                        <div style={{ width: `${selectedProgress.percent}%`, height: '100%',
                          background: 'var(--ls-navy)' }} />
                      </div>
                      <p style={{ margin: '12px 0 0', color: 'var(--surface-text-muted)', fontSize: 12 }}>
                        {usage.status === 'failed' ? usage.message
                          : usage.status === 'ok' && usage.calls === 0 ? '아직 계측된 AI 작업 호출이 없습니다.'
                            : usage.status === 'ok' && usage.costUsd !== null
                              ? `추정 사용비용 $${usage.costUsd.toFixed(4)}${usage.costComplete ? '' : ' 이상'} · 실제 계측 로그 기준`
                              : '선택하면 실제 계측 로그에서 사용실적을 불러옵니다.'}
                      </p>
                    </div>
                  </Panel>
                </article>}
              </div>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div style={{ padding: '10px 12px', borderRadius: 8,
    border: '1px solid var(--surface-border)', background: 'var(--surface-raised)' }}>
    <span style={{ display: 'block', fontSize: 11, color: 'var(--surface-text-muted)' }}>{label}</span>
    <strong style={{ display: 'block', marginTop: 3, fontSize: 17,
      color: 'var(--surface-text)' }}>{value}</strong>
  </div>;
}
