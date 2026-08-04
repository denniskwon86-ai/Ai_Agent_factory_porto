// [CL-3] 대내외 보고 발간 — **내보낸 것은 되돌릴 수 없다.**
//
// 앞 단계까지는 회사 안에서 일어난다. 틀렸으면 다시 하면 된다. 발간은 다르다 — 대외로 나간
// 숫자는 회수해도 이미 읽힌 뒤다. 그래서 이 화면의 규칙은 전부 "나가기 전에 보이게 한다"이다.
//
//   ① 렌더 실패를 «발간 준비 완료»로 표시하지 않는다. 실패 사유를 상태 자리에 그대로 쓴다.
//   ② 대외 발간 게이트를 **목록으로** 보여준다. 버튼만 죽여 두면 사용자는 화면 고장으로 읽는다.
//      (진짜 차단은 서버가 한다 — 이 화면은 경계가 아니라 설명이다.)
//   ③ 배포 실패를 숨기지 않는다. `FAILED` 를 안 보여주면 아무 데도 안 나간 문서를 «발간됨»으로
//      믿는다.
//   ④ 제외한 항목과 **제외 사유**를 문서와 함께 보여준다. 조용히 빼면 다음 사람은 빠진 줄
//      모르고 그대로 인용한다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Banner, Panel, ScreenHead } from '../../design/HubShell';
import { errorTitle } from '../../lib/closedLoopFetch';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded }
  from '../../design/DataState';
import { reportRequestFailure, reportRequestSuccess } from '../../lib/backendHealth';
import {
  AUDIENCE_KO, PUB_STATUS_KO, PUB_TYPE_KO, REVIEW_KO, SECURITY_KO, publicationApi,
  type Audience, type Publication, type ReviewType, type SourceType,
} from '../../lib/publicationApi';
import { decisionApi, type DecisionCase } from '../../lib/decisionApi';

export type PublicationJarvis = {
  title: string; desc: string; ev: { label: string; value: string }[];
  objectId: string; snapshot: Record<string, any>; actions: string[];
};

type Mode = 'list' | 'detail' | 'create';

function StatusChip({ p }: { p: Publication }) {
  const s = PUB_STATUS_KO[p.status] ?? { label: p.status, tone: 'muted' as const };
  // ★ 렌더 실패는 «작성 중»이 아니라 «렌더 실패»다. 같은 DRAFT 라도 사용자가 할 일이 다르다.
  if (p.status === 'DRAFT' && p.render_error) {
    return <span className="state-chip danger">렌더 실패</span>;
  }
  return <span className={`state-chip ${s.tone}`}>{s.label}</span>;
}

function SectionValue({ v }: { v: any }) {
  if (Array.isArray(v)) {
    return <ul className="section-list">{v.map((x, i) => (
      <li key={i}>{x !== null && typeof x === 'object' ? JSON.stringify(x) : String(x)}</li>))}</ul>;
  }
  if (v !== null && typeof v === 'object') {
    return <dl className="section-kv">{Object.entries(v).map(([k, val]) => (
      <div key={k}><dt>{k}</dt><dd>{typeof val === 'object' ? JSON.stringify(val) : String(val)}</dd></div>))}</dl>;
  }
  return <p className="section-text">{String(v)}</p>;
}

export function PublicationCenter({ onJarvis }: { onJarvis?: (c: PublicationJarvis) => void }) {
  const [mode, setMode] = useState<Mode>('list');
  // [UIUX-AUDIT-29 §2] «조회 실패»와 «0건»을 구분한다 — 발간 화면에서 그 둘을 뭉개면
  //   사용자는 «대외 발간 0건»을 보고 나간 문서가 없다고 믿는다.
  const [list, setList] = useState<Loaded<Publication[]>>(loading<Publication[]>());
  const [current, setCurrent] = useState<Publication | null>(null);
  const [decisions, setDecisions] = useState<DecisionCase[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy('불러오는 중'); setErr(null);
    try {
      // 발간의 원천은 결정 안건이다. 목록을 함께 받아 **실제 안건만** 고르게 한다 —
      // 자유 입력으로 두면 존재하지 않는 원천을 가리키는 발간물이 만들어진다.
      const [ps, ds] = await Promise.all([
        publicationApi.list(),
        decisionApi.queue().catch(() => [] as DecisionCase[]),
      ]);
      setList(ok(ps)); setDecisions(ds);
      reportRequestSuccess();
    } catch (e: any) {
      // ⚠️ 빈 배열로 떨어뜨리지 않는다. 실패는 실패로 남아야 «0건»과 구분된다.
      // ⚠️ 여기서 배너까지 띄우지 않는다(감사 §2: 중복 배너 금지). 목록 실패는 목록 자리에서
      //   «조회 불가 + 다시 시도»로 말한다. 배너는 **행동 실패**에만 쓴다.
      setList(failed<Publication[]>(e));
      reportRequestFailure();
    } finally { setBusy(null); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ★ 사용자가 바뀌면 이전 사용자의 발간 목록을 즉시 폐기한다(§CL-FE-03).
  useEffect(() => {
    const h = () => {
      setList(loading<Publication[]>()); setDecisions([]); setCurrent(null); setMode('list'); load();
    };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [load]);

  const open = useCallback(async (id: string) => {
    setBusy('여는 중'); setErr(null); setFlash(null);
    try { setCurrent(await publicationApi.get(id)); setMode('detail'); }
    catch (e: any) { setErr({ msg: e?.message || String(e), status: e?.status }); }
    finally { setBusy(null); }
  }, []);

  const act = async (label: string, fn: () => Promise<Publication>) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      const p = await fn();
      setCurrent(p);
      setFlash(p?.note || null);
      publicationApi.list().then((v) => setList(ok(v))).catch((e) => setList(failed(e)));
      return p;
    } catch (e: any) {
      // ⚠️ 실패해도 화면을 낙관적으로 올리지 않는다. 서버 상태를 다시 읽어 **실제 상태**를 쓴다 —
      //   특히 렌더 실패는 `render_error` 가 서버에만 있다.
      setErr({ msg: e?.message || String(e), status: e?.status });
      if (current) { try { setCurrent(await publicationApi.get(current.publication_id)); } catch { /* 유지 */ } }
      return null;
    } finally { setBusy(null); }
  };

  const rows = list.value || [];
  const stats = useMemo(() => {
    if (list.status !== 'ok') {
      return { total: null, external: null, blocked: null, failed: null } as Record<string, number | null>;
    }
    const v = list.value || [];
    return {
      total: v.length,
      external: v.filter((p) => p.audience === 'EXTERNAL').length,
      blocked: v.filter((p) => p.blockers?.length && p.status !== 'PUBLISHED').length,
      failed: v.filter((p) => p.status === 'DRAFT' && p.render_error).length,
    } as Record<string, number | null>;
  }, [list]);

  useEffect(() => {
    if (!onJarvis) return;
    if (mode === 'detail' && current) {
      onJarvis({
        title: current.title,
        desc: `${AUDIENCE_KO[current.audience].label} · ${PUB_STATUS_KO[current.status]?.label || current.status}`,
        ev: [
          { label: '독자', value: AUDIENCE_KO[current.audience].label },
          { label: '문서 버전', value: current.document_version ? `v${current.document_version}` : '없음' },
          { label: '남은 게이트', value: current.blockers.length ? `${current.blockers.length}건` : '없음' },
          { label: '원천', value: `${current.source_type} ${current.source_id}` },
        ],
        objectId: current.publication_id,
        snapshot: {
          title: current.title, audience: current.audience, status: current.status,
          document_version: current.document_version, render_error: current.render_error,
          blockers: current.blockers.map((b) => b.code),
          source: `${current.source_type}:${current.source_id}`,
        },
        actions: current.can_publish ? ['발간']
          : current.blockers.length ? ['게이트 해소'] : ['문서 생성', '검토 요청'],
      });
    } else {
      onJarvis({
        title: list.status !== 'ok' ? '발간물 — 조회 불가'
          : rows.length ? `발간물 ${rows.length}건` : '발간물 없음',
        desc: list.status !== 'ok'
          ? '목록을 가져오지 못했습니다 — «0건»이 아닙니다.'
          : '대외 발간은 책임 임원 승인과 법무·공시 검토를 모두 통과해야 나갑니다.',
        ev: rows.slice(0, 3).map((p) => ({
          label: p.title.slice(0, 22), value: PUB_STATUS_KO[p.status]?.label || p.status })),
        objectId: '', snapshot: { status: list.status, count: rows.length },
        actions: ['새 발간 초안'],
      });
    }
  }, [mode, current, list, rows, onJarvis]);

  return (
    <>
      {err && (
        <Banner tone="error" title={errorTitle(err.status)}>{err.msg}</Banner>
      )}
      {flash && <Banner tone="info">{flash}</Banner>}
      {busy && <Banner tone="info">{busy}…</Banner>}

      {mode === 'list' && (
        <ListScreen list={rows} state={list} stats={stats} onOpen={open}
          onNew={() => setMode('create')} onRetry={load} />
      )}

      {mode === 'create' && (
        <CreateScreen
          decisions={decisions}
          onCancel={() => setMode('list')}
          onSubmit={async (body) => {
            setBusy('초안 생성 중'); setErr(null);
            try {
              const p = await publicationApi.create(body);
              await load();
              await open(p.publication_id);
            } catch (e: any) {
              setErr({ msg: e?.message || String(e), status: e?.status });
            } finally { setBusy(null); }
          }} />
      )}

      {mode === 'detail' && current && (
        <DetailScreen
          p={current}
          onBack={() => { setMode('list'); setCurrent(null); load(); }}
          onRender={() => act('문서 생성 중', () => publicationApi.render(current.publication_id))}
          onRequestApproval={(t) => act('검토 요청 중',
            () => publicationApi.requestApproval(current.publication_id, t))}
          onApprove={(t, s, c) => act('검토 기록 중',
            () => publicationApi.approve(current.publication_id, t, s, c))}
          onPublish={(targets) => act('발간 중',
            () => publicationApi.publish(current.publication_id, targets))}
          onCorrect={(r) => act('정정판 생성 중',
            () => publicationApi.correct(current.publication_id, r))}
          onWithdraw={(r) => act('회수 중',
            () => publicationApi.withdraw(current.publication_id, r))} />
      )}
    </>
  );
}

// ── 목록 ─────────────────────────────────────────────────────────────────────
function ListScreen({ list, state, stats, onOpen, onNew, onRetry }: {
  list: Publication[];
  state: Loaded<Publication[]>;
  stats: Record<string, number | null>;
  onOpen: (id: string) => void; onNew: () => void; onRetry: () => void;
}) {
  const [filter, setFilter] = useState<'all' | 'EXTERNAL'>('all');
  const shown = filter === 'all' ? list : list.filter((p) => p.audience === 'EXTERNAL');

  return (
    <>
      <ScreenHead kicker="PUBLICATIONS" title="대내외 보고 발간"
        description="승인된 결정 Snapshot 에서 보고서를 만들고, 대내·대외 게이트를 통과한 것만 내보냅니다."
        chip={state.status !== 'ok'
          ? { label: state.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
          : { label: stats.external ? `대외 ${stats.external}건` : '대외 없음',
            tone: stats.external ? 'danger' : 'muted' }} />

      {/* ★★ [UIUX-AUDIT-29 §2] 조회 실패는 «0» 이 아니라 «— / 조회 불가» 다. 발간 화면에서
          그 둘을 뭉개면 «대외로 나간 문서가 없다»는 잘못된 안심을 준다. */}
      <div className="metric-row">
        <Metric label="발간물" state={state.status} value={stats.total} hint="초안 포함" />
        <Metric label="대외 발간" state={state.status} value={stats.external} hint="이중 승인 대상" />
        <Metric label="게이트 미통과" state={state.status} value={stats.blocked}
          hint={stats.blocked ? '내보낼 수 없음' : '없음'} />
        <Metric label="렌더 실패" state={state.status} value={stats.failed}
          hint={stats.failed ? '문서가 만들어지지 않음' : '없음'} />
      </div>

      <Panel kicker="LIST" title="발간물"
        action={
          <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
            <div className="filter-pills">
              <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>전체</button>
              <button className={filter === 'EXTERNAL' ? 'active' : ''} onClick={() => setFilter('EXTERNAL')}>대외만</button>
            </div>
            <button className="primary-button" style={{ minHeight: 32 }} onClick={onNew}>새 발간 초안</button>
          </div>
        }>
        {shown.length === 0 ? (
          <EmptyOrError state={state.status} error={state.error} onRetry={onRetry}
            emptyText="발간물이 없습니다. 결정이 끝난 안건을 원천으로 «새 발간 초안»을 만들 수 있습니다." />
        ) : (
          <div className="people-list" style={{ padding: 15 }}>
            {shown.map((p) => (
              <button key={p.publication_id} type="button" className="person" onClick={() => onOpen(p.publication_id)}>
                <i aria-hidden="true">{AUDIENCE_KO[p.audience].label}</i>
                <div style={{ minWidth: 0 }}>
                  <b style={{ whiteSpace: 'normal' }}>{p.title}</b>
                  <small>
                    {PUB_TYPE_KO[p.publication_type] || p.publication_type}
                    {' · '}{SECURITY_KO[p.security_class] || p.security_class}
                    {p.document_version ? ` · v${p.document_version}` : ' · 문서 없음'}
                    {p.render_error ? ` · 렌더 실패: ${p.render_error.slice(0, 40)}` : ''}
                    {p.blockers?.length ? ` · 남은 게이트 ${p.blockers.length}건` : ''}
                    {p.supersedes_id ? ' · 정정판' : ''}
                  </small>
                </div>
                <StatusChip p={p} />
              </button>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

// ── 상세 ─────────────────────────────────────────────────────────────────────
function DetailScreen({ p, onBack, onRender, onRequestApproval, onApprove, onPublish,
  onCorrect, onWithdraw }: {
  p: Publication; onBack: () => void;
  onRender: () => void;
  onRequestApproval: (types: ReviewType[]) => void;
  onApprove: (t: ReviewType, s: 'APPROVED' | 'REJECTED', comment: string) => void;
  onPublish: (targets: { target: string; channel?: string }[]) => void;
  onCorrect: (reason: string) => void;
  onWithdraw: (reason: string) => void;
}) {
  const doc = p.current_version?.document;
  const excluded = doc?.redaction?.excluded || [];
  const external = p.audience === 'EXTERNAL';

  return (
    <>
      <ScreenHead kicker="PUBLICATION" title={p.title}
        description={`${PUB_TYPE_KO[p.publication_type] || p.publication_type} · 원천 ${p.source_type} ${p.source_id}`}
        chip={{ label: AUDIENCE_KO[p.audience].label, tone: AUDIENCE_KO[p.audience].tone }} />

      <div style={{ display: 'flex', gap: 7, marginBottom: 12, alignItems: 'center' }}>
        <button className="secondary-button" onClick={onBack}>← 목록으로</button>
        <span style={{ flex: 1 }} />
        <StatusChip p={p} />
        <span className="state-chip muted">{SECURITY_KO[p.security_class] || p.security_class}</span>
      </div>

      {/* ★★ 렌더 실패를 «작성 중»으로 넘기지 않는다. 실패 사유를 문서 자리 맨 위에 쓴다. */}
      {p.render_error && (
        <Banner tone="error" title="문서가 만들어지지 않았습니다">
          {p.render_error}
          <br />이 발간물은 «발간 준비 완료»가 아닙니다 — 원천을 확인한 뒤 다시 생성하십시오.
        </Banner>
      )}

      {p.supersedes_id && (
        <Banner tone="warn" title="이 문서는 정정판입니다">
          원본({p.supersedes_id})은 «정정됨»으로 보존됩니다 — 원본을 지우면 그것을 읽고 판단한
          사람이 무엇을 봤는지 말할 수 없습니다.
        </Banner>
      )}
      {p.status === 'WITHDRAWN' && (
        <Banner tone="error" title="회수된 발간물입니다">
          {p.withdrawn_reason}
          <br />배포 이력과 버전은 그대로 남습니다 — 이미 읽은 사람이 무엇을 읽었는지는 지울 수 없습니다.
        </Banner>
      )}

      <GatePanel p={p} onRender={onRender} />
      <DocumentPanel doc={doc} excluded={excluded} version={p.current_version} external={external} />
      <ReviewPanel p={p} onRequestApproval={onRequestApproval} onApprove={onApprove} />
      <PublishPanel p={p} onPublish={onPublish} onCorrect={onCorrect} onWithdraw={onWithdraw} />
    </>
  );
}

// ── 게이트 ───────────────────────────────────────────────────────────────────
function GatePanel({ p, onRender }: { p: Publication; onRender: () => void }) {
  const canRender = !['APPROVED', 'PUBLISHED', 'WITHDRAWN', 'CORRECTED'].includes(p.status);
  return (
    <Panel kicker="GATES" title="발간 게이트"
      action={canRender && (
        <button className="secondary-button" style={{ minHeight: 32 }} onClick={onRender}>
          {p.document_version ? '문서 다시 생성' : '문서 생성'}
        </button>
      )}>
      <div style={{ padding: 15 }}>
        {/* ★ 게이트를 목록으로 보여준다. 버튼만 죽여 두면 사용자는 화면이 고장 났다고 읽고,
            진짜 이유(법무 검토가 아직이다)는 아무에게도 도달하지 않는다. */}
        <div className="people-list">
          {p.gates.map((g) => (
            <div key={g.code} className="person">
              <i aria-hidden="true" style={{ background: g.passed ? 'var(--green)' : 'var(--red)' }}>
                {g.passed ? '✓' : '!'}
              </i>
              <div style={{ minWidth: 0 }}>
                <b>{g.label}</b>
                <small>{g.passed ? '통과' : g.reason}</small>
              </div>
              <span className={`state-chip ${g.passed ? 'success' : 'danger'}`}>
                {g.passed ? '통과' : '미통과'}
              </span>
            </div>
          ))}
        </div>
        {p.audience === 'EXTERNAL' && (
          <div className="request-alert warn" style={{ marginTop: 10 }}>
            <i aria-hidden="true">!</i>
            <div>
              <b>대외 발간은 두 승인이 모두 있어야 나갑니다</b>
              <small>
                {AUDIENCE_KO.EXTERNAL.hint} 화면 버튼뿐 아니라 서버 API 도 함께 막습니다 —
                주소를 알아도 게시되지 않습니다.
              </small>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ── 문서 ─────────────────────────────────────────────────────────────────────
function DocumentPanel({ doc, excluded, version, external }: {
  doc: Publication['current_version'] extends null ? never : any;
  excluded: { key: string; reason: string }[];
  version: Publication['current_version']; external: boolean;
}) {
  return (
    <Panel kicker="DOCUMENT" title="발간 문서"
      action={version && <span className="state-chip data">v{version.version_no}</span>}>
      <div style={{ padding: 15 }}>
        {!doc ? (
          <div className="empty-note">
            아직 문서가 없습니다. 위의 «문서 생성»을 누르면 원천에서 결정론적으로 만들어집니다(LLM 0콜).
          </div>
        ) : (
          <>
            <div className="identity-bar">
              <div><span>결정 문장</span><b style={{ fontSize: 12 }}>{doc.header?.question || '없음'}</b></div>
              <div><span>결정 결과</span><b>{doc.header?.outcome || '미결'}</b></div>
              <div><span>원천 근거 지문</span>
                <b>{(version?.evidence_hash || '').slice(0, 16) || '없음'}</b></div>
              <p>
                이 문서는 원천 Decision Package 의 결정론적 투영입니다 — 원천이 바뀌어도 자동으로
                갱신되지 않고, 정정판을 새로 만들어야 합니다.
              </p>
            </div>

            {/* ★★ 제외 항목과 **사유**를 문서와 같은 화면에 둔다. 조용히 빼면 다음 사람은
                빠진 줄 모르고 그대로 인용한다(설계 §8.4). */}
            {external && (
              <div className={`request-alert ${excluded.length ? 'warn' : ''}`} style={{ marginBottom: 12 }}>
                <i aria-hidden="true">{excluded.length ? '!' : 'i'}</i>
                <div>
                  <b>{excluded.length ? `대외 제외 항목 ${excluded.length}건` : '대외 제외 항목 없음'}</b>
                  {excluded.length ? (
                    <ul style={{ margin: '4px 0 0', paddingLeft: 16 }}>
                      {excluded.map((e) => (
                        <li key={e.key}><b>{e.key}</b> — {e.reason}</li>
                      ))}
                    </ul>
                  ) : (
                    <small>이 문서에는 제외 대상 항목이 없었습니다.</small>
                  )}
                </div>
              </div>
            )}

            <div className="section-grid">
              {(doc.sections || []).map((s: any) => (
                <section key={s.key}>
                  <h4>{s.key}</h4>
                  <SectionValue v={s.value} />
                </section>
              ))}
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

// ── 검토 ─────────────────────────────────────────────────────────────────────
function ReviewPanel({ p, onRequestApproval, onApprove }: {
  p: Publication;
  onRequestApproval: (types: ReviewType[]) => void;
  onApprove: (t: ReviewType, s: 'APPROVED' | 'REJECTED', comment: string) => void;
}) {
  const [picked, setPicked] = useState<ReviewType[]>([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<{ t: ReviewType; s: 'APPROVED' | 'REJECTED'; c: string } | null>(null);
  const canRequest = ['RENDERED', 'REVIEW_REQUESTED'].includes(p.status);
  const external = p.audience === 'EXTERNAL';

  return (
    <Panel kicker="REVIEWS" title="검토와 승인"
      action={canRequest && (
        <button className="secondary-button" style={{ minHeight: 32 }} onClick={() => setOpen(!open)}>
          {open ? '접기' : '검토 요청'}
        </button>
      )}>
      <div style={{ padding: 15 }}>
        {p.reviews.length === 0 ? (
          <div className="empty-note">요청된 검토가 없습니다.</div>
        ) : (
          <div className="people-list">
            {p.reviews.map((r) => (
              <div key={r.review_type} className="person">
                <i aria-hidden="true">{REVIEW_KO[r.review_type]?.label[0] || '검'}</i>
                <div style={{ minWidth: 0 }}>
                  <b>{REVIEW_KO[r.review_type]?.label || r.review_type}</b>
                  <small>
                    {r.status === 'PENDING' ? '아직 판정하지 않았습니다'
                      : `${r.reviewer_id} · ${r.reviewed_at.slice(0, 10)}${r.comment ? ` · ${r.comment}` : ''}`}
                    {` · 대상 문서 v${r.document_version}`}
                  </small>
                  {form?.t === r.review_type && (
                    <div style={{ marginTop: 8 }}>
                      <div className="filter-pills" style={{ marginBottom: 6 }}>
                        <button className={form.s === 'APPROVED' ? 'active' : ''}
                          onClick={() => setForm({ ...form, s: 'APPROVED' })}>승인</button>
                        <button className={form.s === 'REJECTED' ? 'active' : ''}
                          onClick={() => setForm({ ...form, s: 'REJECTED' })}>반려</button>
                      </div>
                      <textarea className="afs-textarea" rows={2} value={form.c}
                        placeholder={form.s === 'REJECTED'
                          ? '반려 사유는 필수입니다 — 없으면 작성자는 무엇을 고쳐야 하는지 모릅니다'
                          : '의견(선택)'}
                        onChange={(e) => setForm({ ...form, c: e.target.value })} />
                      <div style={{ display: 'flex', gap: 7, marginTop: 8, justifyContent: 'flex-end' }}>
                        <button className="secondary-button" onClick={() => setForm(null)}>취소</button>
                        <button className="primary-button"
                          disabled={form.s === 'REJECTED' && !form.c.trim()}
                          onClick={() => { onApprove(form.t, form.s, form.c.trim()); setForm(null); }}>
                          기록
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className={`state-chip ${r.status === 'APPROVED' ? 'success'
                    : r.status === 'REJECTED' ? 'danger' : 'warn'}`}>
                    {r.status === 'APPROVED' ? '승인' : r.status === 'REJECTED' ? '반려' : '대기'}
                  </span>
                  {r.status === 'PENDING' && form?.t !== r.review_type && (
                    <button className="text-button"
                      onClick={() => setForm({ t: r.review_type, s: 'APPROVED', c: '' })}>
                      판정
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {open && canRequest && (
          <div style={{ marginTop: 14 }}>
            <label className="field-label">요청할 검토</label>
            <div className="filter-pills" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
              {(Object.keys(REVIEW_KO) as ReviewType[]).map((t) => {
                const forced = external && (t === 'EXECUTIVE' || t === 'LEGAL_DISCLOSURE');
                const on = forced || picked.includes(t);
                return (
                  <button key={t} className={on ? 'active' : ''} disabled={forced}
                    title={forced ? '대외 발간 필수 — 뺄 수 없습니다' : REVIEW_KO[t].who}
                    onClick={() => setPicked(picked.includes(t)
                      ? picked.filter((x) => x !== t) : [...picked, t])}>
                    {REVIEW_KO[t].label}{forced ? ' (필수)' : ''}
                  </button>
                );
              })}
            </div>
            {/* ⚠️ 요청자가 대외 발간에서 법무 검토를 빼는 것을 허용하지 않는다 — 뺄 수 있으면
                언젠가 바쁜 날에 빠진다. 서버도 같은 규칙을 강제한다. */}
            {external && (
              <p className="hint-line">
                대외 발간이므로 <b>책임 임원 승인</b>과 <b>법무·공시 검토</b>는 선택에서 제외할 수
                없습니다. 서버가 요청에 자동으로 포함합니다.
              </p>
            )}
            <div style={{ display: 'flex', gap: 7, justifyContent: 'flex-end' }}>
              <button className="secondary-button" onClick={() => setOpen(false)}>취소</button>
              <button className="primary-button" disabled={!external && picked.length === 0}
                onClick={() => { onRequestApproval(picked); setOpen(false); setPicked([]); }}>
                검토 요청 보내기
              </button>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ── 발간·정정·회수 ───────────────────────────────────────────────────────────
function PublishPanel({ p, onPublish, onCorrect, onWithdraw }: {
  p: Publication;
  onPublish: (targets: { target: string; channel?: string }[]) => void;
  onCorrect: (reason: string) => void;
  onWithdraw: (reason: string) => void;
}) {
  const [rows, setRows] = useState([{ target: '', channel: '' }]);
  const [reason, setReason] = useState<{ kind: 'correct' | 'withdraw'; text: string } | null>(null);
  const filled = rows.filter((r) => r.target.trim());
  const published = p.status === 'PUBLISHED' || p.status === 'CORRECTED';

  return (
    <Panel kicker="DISTRIBUTION" title="발간과 배포">
      <div style={{ padding: 15 }}>
        {p.distributions.length > 0 && (
          <div className="people-list" style={{ marginBottom: 14 }}>
            {p.distributions.map((d) => (
              <div key={d.distribution_id} className="person">
                <i aria-hidden="true" style={{ background: d.status === 'PUBLISHED' ? 'var(--green)' : 'var(--red)' }}>
                  {d.status === 'PUBLISHED' ? '✓' : '!'}
                </i>
                <div style={{ minWidth: 0 }}>
                  <b>{d.target}</b>
                  <small>
                    {d.channel || '채널 미지정'} · v{d.document_version}
                    {/* ★ 실패를 숨기지 않는다. 안 보여주면 아무 데도 안 나간 문서를
                        «발간됨»으로 믿는다. */}
                    {d.status === 'PUBLISHED' ? ` · ${d.external_ref || '외부 참조 없음'}` : ` · ${d.error}`}
                  </small>
                </div>
                <span className={`state-chip ${d.status === 'PUBLISHED' ? 'success' : 'danger'}`}>
                  {d.status === 'PUBLISHED' ? '게시됨' : '실패'}
                </span>
              </div>
            ))}
          </div>
        )}

        {!published && p.status !== 'WITHDRAWN' && (
          <>
            <label className="field-label">배포 대상</label>
            {rows.map((r, i) => (
              <div key={i} style={{ display: 'flex', gap: 7, marginBottom: 7 }}>
                <input className="afs-input" value={r.target} placeholder="대상 (예: 사내포털, ir@…)"
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, target: e.target.value } : x))} />
                <input className="afs-input" style={{ maxWidth: 180 }} value={r.channel} placeholder="채널"
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, channel: e.target.value } : x))} />
                <button className="text-button" disabled={rows.length === 1}
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}>삭제</button>
              </div>
            ))}
            <button className="text-button" onClick={() => setRows([...rows, { target: '', channel: '' }])}>
              + 대상 추가
            </button>

            {/* ★★ 버튼 옆에 이유를 그대로 쓴다. 비활성 버튼만 두면 화면 고장으로 읽힌다. */}
            {p.blockers.length > 0 && (
              <div className="request-alert warn" style={{ marginTop: 10 }}>
                <i aria-hidden="true">!</i>
                <div>
                  <b>지금은 발간할 수 없습니다</b>
                  <small>{p.blockers.map((b) => b.reason).join(' / ')}</small>
                </div>
              </div>
            )}
            <p className="hint-line">
              게시 어댑터가 연결되어 있지 않으면 배포는 <b>«실패»로 기록</b>되고 상태는 올라가지
              않습니다 — 아무 데도 나가지 않은 문서를 «발간됨»으로 두지 않기 위해서입니다.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="primary-button" disabled={!p.can_publish || !filled.length}
                onClick={() => onPublish(filled)}>
                발간하기
              </button>
            </div>
          </>
        )}

        {published && p.status !== 'CORRECTED' && (
          <div style={{ marginTop: 6 }}>
            <div style={{ display: 'flex', gap: 7 }}>
              <button className="secondary-button" onClick={() => setReason({ kind: 'correct', text: '' })}>
                정정판 만들기
              </button>
              <button className="danger-ghost" onClick={() => setReason({ kind: 'withdraw', text: '' })}>
                회수
              </button>
            </div>
            {reason && (
              <div style={{ marginTop: 10 }}>
                <label className="field-label" htmlFor="pub-reason">
                  {reason.kind === 'correct'
                    ? '정정 사유 (읽은 사람이 자신의 판단을 고칠 근거가 됩니다)'
                    : '회수 사유 (이미 읽은 사람에게 남는 기록입니다)'}
                </label>
                <textarea id="pub-reason" className="afs-textarea" rows={2} value={reason.text}
                  onChange={(e) => setReason({ ...reason, text: e.target.value })} />
                <div style={{ display: 'flex', gap: 7, marginTop: 8, justifyContent: 'flex-end' }}>
                  <button className="secondary-button" onClick={() => setReason(null)}>취소</button>
                  <button className="primary-button" disabled={!reason.text.trim()}
                    onClick={() => {
                      const t = reason.text.trim();
                      if (reason.kind === 'correct') onCorrect(t); else onWithdraw(t);
                      setReason(null);
                    }}>
                    {reason.kind === 'correct' ? '정정판 생성' : '회수하기'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

// ── 새 발간 초안 ─────────────────────────────────────────────────────────────
function CreateScreen({ decisions, onCancel, onSubmit }: {
  decisions: DecisionCase[];
  onCancel: () => void;
  onSubmit: (b: {
    title: string; source_type: SourceType; source_id: string; audience: Audience;
    publication_type: string; security_class: string;
  }) => void;
}) {
  // ★ 결정이 끝난 안건만 원천으로 제시한다(설계 §8.2-1: "실행 중인 가변 시뮬레이션이 아니라
  //   승인된 Snapshot 만 발간한다"). 진행 중 안건을 발간하면 숫자가 계속 움직인다.
  const decided = decisions.filter((d) => ['DECIDED', 'ACTIONED', 'EFFECT_MEASURED'].includes(d.status));
  const [f, setF] = useState({
    title: '', source_id: decided[0]?.decision_id || '',
    audience: 'INTERNAL' as Audience,
    publication_type: 'OPERATIONAL', security_class: 'INTERNAL',
  });
  const ready = !!f.title.trim() && !!f.source_id.trim();

  return (
    <>
      <ScreenHead kicker="NEW PUBLICATION" title="새 발간 초안"
        description="결정이 끝난 안건을 원천으로 보고서를 만듭니다. 진행 중 안건은 숫자가 계속 움직이므로 발간하지 않습니다."
        chip={{ label: ready ? '만들 준비 완료' : '입력 중', tone: ready ? 'success' : 'data' }} />

      <Panel kicker="SOURCE" title="원천">
        <div style={{ padding: 15 }}>
          <label className="field-label" htmlFor="np-src">결정 안건 (필수)</label>
          {decided.length > 0 ? (
            <select id="np-src" className="afs-select" value={f.source_id}
              onChange={(e) => setF({ ...f, source_id: e.target.value })}>
              <option value="">— 선택 —</option>
              {decided.map((d) => (
                <option key={d.decision_id} value={d.decision_id}>{d.question}</option>
              ))}
            </select>
          ) : (
            <div className="empty-note">
              결정이 끝난 안건이 없습니다. <b>의사결정 센터</b>에서 결정을 기록한 뒤에 발간할 수
              있습니다 — 결정 전 숫자를 내보내면 그 숫자는 곧 달라집니다.
            </div>
          )}
        </div>
      </Panel>

      <Panel kicker="TARGET" title="독자와 등급">
        <div style={{ padding: 15 }}>
          <label className="field-label" htmlFor="np-title">보고서 제목 (필수)</label>
          <input id="np-title" className="afs-input" value={f.title}
            onChange={(e) => setF({ ...f, title: e.target.value })} />

          <label className="field-label" style={{ marginTop: 12 }}>독자</label>
          <div className="filter-pills" style={{ marginBottom: 6 }}>
            {(Object.keys(AUDIENCE_KO) as Audience[]).map((a) => (
              <button key={a} className={f.audience === a ? 'active' : ''}
                onClick={() => setF({ ...f, audience: a })}>{AUDIENCE_KO[a].label}</button>
            ))}
          </div>
          {/* ★ 대외를 고른 순간 무엇이 달라지는지 **만들기 전에** 말한다. 나중에 알면 검토
              시간이 통째로 낭비된다. */}
          <p className="hint-line">{AUDIENCE_KO[f.audience].hint}</p>

          <div style={{ display: 'flex', gap: 7, marginTop: 10 }}>
            <div style={{ flex: 1 }}>
              <label className="field-label" htmlFor="np-type">보고 유형</label>
              <select id="np-type" className="afs-select" value={f.publication_type}
                onChange={(e) => setF({ ...f, publication_type: e.target.value })}>
                {Object.entries(PUB_TYPE_KO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label className="field-label" htmlFor="np-sec">보안등급</label>
              <select id="np-sec" className="afs-select" value={f.security_class}
                onChange={(e) => setF({ ...f, security_class: e.target.value })}>
                {Object.entries(SECURITY_KO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          </div>
        </div>
      </Panel>

      <div style={{ display: 'flex', gap: 7, justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="secondary-button" onClick={onCancel}>취소</button>
        <button className="primary-button" disabled={!ready}
          onClick={() => onSubmit({
            title: f.title.trim(), source_type: 'DECISION_CASE', source_id: f.source_id,
            audience: f.audience, publication_type: f.publication_type,
            security_class: f.security_class,
          })}>
          발간 초안 만들기
        </button>
      </div>
    </>
  );
}
