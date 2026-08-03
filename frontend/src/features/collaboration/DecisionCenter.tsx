// [CL-2] 의사결정 센터 — 시뮬레이션 결과에서 Decision Package 를 만들고, 세 관점으로 검토하고,
// 회의를 요청하고, 결정하고, 실행과제와 효과까지 잇는 화면.
//
// 이 화면이 지키는 다섯 가지(모두 백엔드가 이미 강제한다 — 화면은 그것을 **보이게** 만든다):
//
//   ① 세 관점은 같은 문서다. `package_version` 과 `evidence_hash` 를 탭 위에 상시 노출한다.
//      세 사람이 서로 다른 숫자를 보면서 같은 안건을 논의하는 것이 이 기능이 막으려는 사고다.
//   ② 비어 있는 섹션을 숨기지 않는다. 숨기면 검토자는 그 항목이 검토됐다고 믿는다.
//   ③ 결정 차단 사유를 결정 버튼 **옆에** 쓴다. 버튼만 비활성화하면 사용자는 화면 고장으로 읽고,
//      진짜 이유("참석자가 읽은 숫자와 다릅니다")는 아무에게도 도달하지 않는다.
//   ④ 회의는 **요청**까지다. 외부 캘린더에 아무것도 쓰지 않았다는 사실을 화면이 직접 말한다.
//   ⑤ 미측정과 0 을 다르게 표시한다. 0 은 "효과가 없었다"이고 미측정은 "아직 모른다"다.
//
// ⚠️ `prompt()`/`alert()` 을 쓰지 않는다(키보드·스크린리더·스타일 모두 불가). 화면 안 입력만 쓴다.
// ⚠️ 모달 semantics·포커스 트랩을 여기서 다시 구현하지 않는다 — 셸(`HubDialog`)에 이미 있다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Banner, Panel, ScreenHead } from '../../design/HubShell';
import {
  decisionApi, DECISION_STATUS_KO, OUTCOME_KO, PACKAGE_FIELDS, RESPONSE_KO, ROLE_KO, VIEW_KO,
  type DecisionAction, type DecisionCase, type DecisionRole, type Outcome, type ResponseStatus,
  type ViewKey, type ViewSection, type ViewsBundle,
} from '../../lib/decisionApi';
import { errorTitle } from '../../lib/closedLoopFetch';

export type DecisionJarvis = {
  title: string; desc: string; ev: { label: string; value: string }[];
  objectId: string; snapshot: Record<string, any>; actions: string[];
};

type Mode = 'list' | 'detail' | 'create';

function StatusChip({ status }: { status: DecisionCase['status'] }) {
  const s = DECISION_STATUS_KO[status] ?? { label: status, tone: 'muted' };
  return <span className={`state-chip ${s.tone}`}>{s.label}</span>;
}

/** 섹션 값. 문자열·목록·표를 모두 받는다.
 *  ★ 값이 없으면 **"아직 채워지지 않았습니다"라고 쓴다.** 빈칸으로 두면 검토자는 그 항목이
 *    검토됐다고 믿는다(도메인 §7.2). */
function SectionValue({ s }: { s: ViewSection }) {
  if (s.missing) {
    return <p className="section-missing">아직 채워지지 않았습니다 — 이 항목은 검토되지 않았습니다.</p>;
  }
  const v = s.value;
  if (Array.isArray(v)) {
    return (
      <ul className="section-list">
        {v.map((item, i) => (
          <li key={i}>
            {item !== null && typeof item === 'object'
              ? Object.entries(item).map(([k, val]) => (
                <span key={k}><b>{k}</b> {String(val)}</span>))
              : String(item)}
          </li>
        ))}
      </ul>
    );
  }
  if (v !== null && typeof v === 'object') {
    return (
      <dl className="section-kv">
        {Object.entries(v).map(([k, val]) => (
          <div key={k}><dt>{k}</dt><dd>{typeof val === 'object' ? JSON.stringify(val) : String(val)}</dd></div>
        ))}
      </dl>
    );
  }
  return <p className="section-text">{String(v)}</p>;
}

export function DecisionCenter({ onJarvis, simulationRunIds = [] }: {
  onJarvis?: (c: DecisionJarvis) => void;
  simulationRunIds?: string[];
}) {
  const [mode, setMode] = useState<Mode>('list');
  const [queue, setQueue] = useState<DecisionCase[]>([]);
  const [current, setCurrent] = useState<DecisionCase | null>(null);
  const [views, setViews] = useState<ViewsBundle | null>(null);
  const [view, setView] = useState<ViewKey>('decider');
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const loadQueue = useCallback(async () => {
    setBusy('불러오는 중'); setErr(null);
    try { setQueue(await decisionApi.queue()); }
    catch (e: any) { setErr({ msg: e?.message || String(e), status: e?.status }); }
    finally { setBusy(null); }
  }, []);

  const open = useCallback(async (id: string) => {
    setBusy('안건을 여는 중'); setErr(null); setFlash(null);
    try {
      // 상세와 세 관점을 함께 받는다 — 관점 탭을 눌러야만 로드하면, 참석자는 "같은 문서인가"를
      // 확인하기 전에 한 관점만 읽고 회의에 들어간다.
      const [d, v] = await Promise.all([decisionApi.get(id), decisionApi.views(id)]);
      setCurrent(d); setViews(v);
      setView(d.my_role === 'AFFECTED' ? 'affected' : d.my_role === 'REQUESTER' ? 'requester' : 'decider');
      setMode('detail');
    } catch (e: any) {
      setErr({ msg: e?.message || String(e), status: e?.status });
    } finally { setBusy(null); }
  }, []);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  // ★ 사용자가 바뀌면 이전 사용자의 안건·검토서를 **즉시 폐기**한다(§CL-FE-03). 남겨 두면 다른
  //   사용자의 결정 목록이 화면에 그대로 남고, 그것이 곧 유출이다.
  useEffect(() => {
    const h = () => { setQueue([]); setCurrent(null); setViews(null); setMode('list'); loadQueue(); };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [loadQueue]);

  /** 서버가 돌려준 최신 안건으로 갱신한다. 응답의 `note` 는 **서버 문구 그대로** 보여준다 —
   *  화면이 지어내면 서버 규칙과 갈라진다(회의 요청의 "외부에 아무것도 보내지 않았다"가 그 예다). */
  const act = async (label: string, fn: () => Promise<DecisionCase>) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      const d = await fn();
      setCurrent(d);
      setFlash(d?.note || null);
      // 근거·상태가 바뀌면 세 관점도 같이 바뀐다. 옛 검토서를 남겨 두지 않는다.
      try { setViews(await decisionApi.views(d.decision_id)); } catch { setViews(null); }
      loadQueue();
      return d;
    } catch (e: any) {
      setErr({ msg: e?.message || String(e), status: e?.status });
      return null;
    } finally { setBusy(null); }
  };

  // Jarvis 문맥 — **화면이 강조 중인 객체**를 그대로 넘긴다(§3-8: Task ID 를 묻지 않는다).
  useEffect(() => {
    if (!onJarvis) return;
    if (mode === 'detail' && current) {
      onJarvis({
        title: current.question,
        desc: `${DECISION_STATUS_KO[current.status]?.label || current.status} · ${ROLE_KO[current.my_role as DecisionRole] || '참여자'} 관점`,
        ev: [
          { label: '문서 버전', value: `v${current.package_version}` },
          { label: '근거 지문', value: (current.evidence_hash || '').slice(0, 12) || '없음' },
          { label: '기준선', value: current.baseline_id || '없음' },
          { label: '결정 차단', value: current.blockers.length ? `${current.blockers.length}건` : '없음' },
        ],
        objectId: current.decision_id,
        snapshot: {
          question: current.question, status: current.status,
          package_version: current.package_version, evidence_hash: current.evidence_hash,
          baseline_id: current.baseline_id, simulation_run_id: current.simulation_run_id,
          blockers: current.blockers.map((b) => b.code),
          participants: current.participants.map((p) => `${p.user_id}(${p.role})`),
        },
        actions: current.can_decide ? ['결정 기록']
          : current.blockers.length ? ['차단 사유 해소'] : ['검토 요청', '회의 요청', '의견 남기기'],
      });
    } else {
      onJarvis({
        title: queue.length ? `내 결정 ${queue.length}건` : '내 결정 없음',
        desc: '내가 참여자로 지정된 안건만 보입니다.',
        ev: queue.slice(0, 3).map((d) => ({
          label: d.question.slice(0, 24),
          value: DECISION_STATUS_KO[d.status]?.label || d.status,
        })),
        objectId: '',
        snapshot: { queue_count: queue.length },
        actions: ['새 안건 만들기'],
      });
    }
  }, [mode, current, queue, onJarvis]);

  const stats = useMemo(() => ({
    total: queue.length,
    mine: queue.filter((d) => d.my_role === 'DECIDER'
      && ['REVIEW_REQUESTED', 'IN_REVIEW', 'MEETING_REQUESTED'].includes(d.status)).length,
    changed: queue.filter((d) => d.status === 'EVIDENCE_CHANGED').length,
    overdue: queue.filter((d) => d.overdue).length,
  }), [queue]);

  return (
    <>
      {err && (
        <Banner tone="error" title={errorTitle(err.status)}>
          {err.msg}
          {err.status === 404 && ' — 내가 참여자가 아닌 안건은 존재 여부도 알려 주지 않습니다.'}
        </Banner>
      )}
      {flash && <Banner tone="info">{flash}</Banner>}
      {busy && <Banner tone="info">{busy}…</Banner>}

      {mode === 'list' && (
        <QueueScreen list={queue} stats={stats} onOpen={open} onNew={() => setMode('create')} />
      )}

      {mode === 'create' && (
        <CreateScreen
          runIds={simulationRunIds}
          onCancel={() => setMode('list')}
          onSubmit={async (runId, body) => {
            setBusy('안건 생성 중'); setErr(null);
            try {
              const d = await decisionApi.create(runId, body);
              await loadQueue();
              await open(d.decision_id);
            } catch (e: any) {
              setErr({ msg: e?.message || String(e), status: e?.status });
            } finally { setBusy(null); }
          }} />
      )}

      {mode === 'detail' && current && (
        <DetailScreen
          d={current} views={views} view={view} onView={setView}
          onBack={() => { setMode('list'); setCurrent(null); setViews(null); loadQueue(); }}
          onRequestReview={(ps) => act('검토 요청 중', () => decisionApi.requestReview(current.decision_id, ps))}
          onRespond={(s, t) => act('의견 저장 중', () => decisionApi.respond(current.decision_id, s, t))}
          onMeeting={(b) => act('회의 요청 중', () => decisionApi.requestMeeting(current.decision_id, b))}
          onDecide={(b) => act('결정 기록 중', () => decisionApi.decide(current.decision_id, b))}
          onActions={(a) => act('실행과제 생성 중', () => decisionApi.createActions(current.decision_id, a))}
          onMeasure={(aid, v) => act('효과 기록 중', () => decisionApi.measureEffect(current.decision_id, aid, v))}
        />
      )}
    </>
  );
}

// ── 목록 ─────────────────────────────────────────────────────────────────────
function QueueScreen({ list, stats, onOpen, onNew }: {
  list: DecisionCase[];
  stats: { total: number; mine: number; changed: number; overdue: number };
  onOpen: (id: string) => void; onNew: () => void;
}) {
  const [filter, setFilter] = useState<'open' | 'all'>('open');
  const CLOSED = ['DECIDED', 'ACTIONED', 'EFFECT_MEASURED', 'CANCELLED'];
  const shown = filter === 'open' ? list.filter((d) => !CLOSED.includes(d.status)) : list;

  return (
    <>
      <ScreenHead kicker="DECISIONS" title="의사결정 센터"
        description="시뮬레이션 결과를 하나의 Decision Package 로 만들고, 요청자·의사결정자·영향부서가 같은 문서를 관점별로 봅니다."
        chip={{ label: stats.mine ? `내가 결정할 것 ${stats.mine}건` : '내 결정 대기 없음',
          tone: stats.mine ? 'warn' : 'success' }} />

      <div className="metric-row">
        <div><span>내가 관여한 안건</span><b>{stats.total}</b><small>참여자로 지정된 것만</small></div>
        <div><span>내가 결정할 것</span><b>{stats.mine}</b><small>의사결정자 역할</small></div>
        <div><span>근거가 바뀐 안건</span><b>{stats.changed}</b>
          <small>{stats.changed ? '결정 전 재검토 필요' : '없음'}</small></div>
        <div><span>기한 초과</span><b>{stats.overdue}</b><small>미결 기준</small></div>
      </div>

      <Panel kicker="QUEUE" title="내 결정 대기"
        action={
          <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
            <div className="filter-pills">
              <button className={filter === 'open' ? 'active' : ''} onClick={() => setFilter('open')}>진행 중</button>
              <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>전체</button>
            </div>
            <button className="primary-button" style={{ minHeight: 32 }} onClick={onNew}>새 안건 만들기</button>
          </div>
        }>
        {shown.length === 0 ? (
          <div className="empty-note">
            {filter === 'open'
              ? '진행 중인 안건이 없습니다. 전체를 보려면 위의 «전체» 를 누르십시오.'
              : '내가 참여자로 지정된 안건이 없습니다. 시뮬레이션 결과에서 «새 안건 만들기» 로 Decision Package 를 만들 수 있습니다.'}
          </div>
        ) : (
          <div className="people-list" style={{ padding: 15 }}>
            {shown.map((d) => (
              <button key={d.decision_id} type="button" className="person" onClick={() => onOpen(d.decision_id)}>
                <i aria-hidden="true">{(ROLE_KO[d.my_role as DecisionRole] || '참여')[0]}</i>
                <div style={{ minWidth: 0 }}>
                  <b style={{ whiteSpace: 'normal' }}>{d.question}</b>
                  <small>
                    v{d.package_version} · 근거 {(d.evidence_hash || '').slice(0, 8) || '없음'}
                    {' · '}{ROLE_KO[d.my_role as DecisionRole] || '참여자'}
                    {d.due_at ? ` · 기한 ${d.due_at}` : ''}
                    {d.overdue ? ' · 기한 초과' : ''}
                    {d.blockers?.length ? ` · 결정 차단 ${d.blockers.length}건` : ''}
                  </small>
                </div>
                <StatusChip status={d.status} />
              </button>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

// ── 상세 ─────────────────────────────────────────────────────────────────────
function DetailScreen({ d, views, view, onView, onBack, onRequestReview, onRespond, onMeeting,
  onDecide, onActions, onMeasure }: {
  d: DecisionCase; views: ViewsBundle | null; view: ViewKey; onView: (v: ViewKey) => void;
  onBack: () => void;
  onRequestReview: (ps: { user_id: string; role: DecisionRole }[]) => void;
  onRespond: (s: ResponseStatus, text: string) => void;
  onMeeting: (b: { title: string; schedule?: string; channel?: string }) => void;
  onDecide: (b: { outcome: Outcome; rationale: string; conditions?: string }) => void;
  onActions: (a: { action: string; owner_user_id: string; due_at: string }[]) => void;
  onMeasure: (actionId: string, v: string) => void;
}) {
  const rv = views?.views?.[view] || null;

  return (
    <>
      <ScreenHead kicker="DECISION PACKAGE" title={d.question}
        description={`시뮬레이션 ${d.simulation_run_id || '(연결 없음)'} · 기준선 ${d.baseline_id || '(없음)'}`}
        chip={{ label: DECISION_STATUS_KO[d.status]?.label || d.status,
          tone: DECISION_STATUS_KO[d.status]?.tone || 'muted' }} />

      <div style={{ display: 'flex', gap: 7, marginBottom: 12 }}>
        <button className="secondary-button" onClick={onBack}>← 목록으로</button>
        <span style={{ flex: 1 }} />
        <span className="state-chip muted">
          {ROLE_KO[d.my_role as DecisionRole] || '참여자 아님'} · {d.created_by} 요청
        </span>
      </div>

      {/* ★ 같은 문서라는 **증거**를 항상 위에 둔다. 이 값이 관점마다 다르면 세 사람이 서로 다른
          숫자를 보고 회의에 들어간 것이고, 그 회의록은 나중에 재현할 수 없다. */}
      <div className={`identity-bar ${views && !views.same_package ? 'broken' : ''}`}>
        <div><span>문서 버전</span><b>v{d.package_version}</b></div>
        <div><span>근거 지문</span><b title={d.evidence_hash}>{(d.evidence_hash || '').slice(0, 16) || '없음'}</b></div>
        <div><span>세 관점 동일성</span>
          <b>{!views ? '확인 불가' : views.same_package ? '같은 문서' : '⚠ 불일치'}</b></div>
        <p>
          {rv?.identity_note
            || '세 관점은 같은 Decision Package 의 다른 렌더링입니다 — package_version 과 evidence_hash 가 같아야 같은 문서입니다.'}
        </p>
      </div>

      {/* ★ 차단 사유는 결정 버튼 옆이 아니라 **문서 위**에도 쓴다. 검토를 시작하기 전에 알아야
          하는 정보다(이미 읽고 나서 "결정할 수 없다"를 알면 시간이 낭비된다). */}
      {d.blockers.length > 0 && (
        <Banner tone="error" title={`이 안건은 지금 결정할 수 없습니다 (${d.blockers.length}건)`}>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {d.blockers.map((b) => (
              <li key={b.code}><b>{b.code}</b> — {b.reason}</li>
            ))}
          </ul>
        </Banner>
      )}

      {/* ── 세 관점 ─────────────────────────────────────────────────────── */}
      <Panel kicker="ONE PACKAGE · THREE VIEWS" title="관점별 검토서"
        action={
          <div className="filter-pills">
            {(Object.keys(VIEW_KO) as ViewKey[]).map((k) => (
              <button key={k} className={view === k ? 'active' : ''} onClick={() => onView(k)}>
                {VIEW_KO[k].label}
              </button>
            ))}
          </div>
        }>
        <div style={{ padding: 15 }}>
          <p className="view-who">{VIEW_KO[view].who}</p>
          {!rv ? (
            <div className="empty-note">검토서를 불러오지 못했습니다. 목록으로 돌아갔다가 다시 여십시오.</div>
          ) : (
            <div className="section-grid">
              {rv.sections.map((s) => (
                <section key={s.key} className={s.missing ? 'missing' : ''}>
                  <h4>{s.label}{s.missing && <em>미작성</em>}</h4>
                  <SectionValue s={s} />
                </section>
              ))}
            </div>
          )}
        </div>
      </Panel>

      <ParticipantPanel d={d} onRequestReview={onRequestReview} onRespond={onRespond} />
      <MeetingPanel d={d} onMeeting={onMeeting} />
      <DecidePanel d={d} onDecide={onDecide} />
      {['DECIDED', 'ACTIONED', 'EFFECT_MEASURED'].includes(d.status) && (
        <ActionPanel d={d} onActions={onActions} onMeasure={onMeasure} />
      )}
    </>
  );
}

// ── 참여자·의견 ──────────────────────────────────────────────────────────────
function ParticipantPanel({ d, onRequestReview, onRespond }: {
  d: DecisionCase;
  onRequestReview: (ps: { user_id: string; role: DecisionRole }[]) => void;
  onRespond: (s: ResponseStatus, text: string) => void;
}) {
  const [rows, setRows] = useState<{ user_id: string; role: DecisionRole }[]>(
    [{ user_id: '', role: 'DECIDER' }]);
  const [open, setOpen] = useState(false);
  const [resp, setResp] = useState<{ s: ResponseStatus | ''; text: string }>({ s: '', text: '' });

  const canRequest = ['DRAFT', 'REVIEW_REQUESTED', 'EVIDENCE_CHANGED'].includes(d.status);
  const hasDecider = d.participants.some((p) => p.role === 'DECIDER')
    || rows.some((r) => r.role === 'DECIDER' && r.user_id.trim());
  const filled = rows.filter((r) => r.user_id.trim());
  // 조건부·반대·정보 부족에는 내용이 필요하다(서버도 막는다) — 여기서 먼저 알려준다.
  const needsText = resp.s === 'CONDITIONAL' || resp.s === 'DISAGREE' || resp.s === 'NEED_INFO';
  const mine = d.participants.find((p) => p.user_id && p.role === d.my_role && d.my_role);

  return (
    <Panel kicker="PARTICIPANTS" title="참여자와 의견"
      action={canRequest && (
        <button className="secondary-button" style={{ minHeight: 32 }} onClick={() => setOpen(!open)}>
          {open ? '접기' : '검토 요청'}
        </button>
      )}>
      <div style={{ padding: 15 }}>
        {d.participants.length === 0 ? (
          <div className="empty-note">참여자가 없습니다. 검토를 요청하면 여기에 나타납니다.</div>
        ) : (
          <div className="people-list">
            {d.participants.map((p) => {
              const r = p.response_status ? RESPONSE_KO[p.response_status] : null;
              return (
                <div key={`${p.user_id}-${p.role}`} className="person">
                  <i aria-hidden="true">{ROLE_KO[p.role][0]}</i>
                  <div style={{ minWidth: 0 }}>
                    <b>{p.user_id}</b>
                    <small>
                      {ROLE_KO[p.role]}
                      {/* ⚠️ 무응답을 '동의'처럼 보이게 두지 않는다 — 침묵은 동의가 아니다. */}
                      {p.response_status
                        ? ` · ${p.response}${p.responded_at ? ` (${p.responded_at.slice(0, 10)})` : ''}`
                        : ' · 아직 응답하지 않았습니다'}
                    </small>
                  </div>
                  <span className={`state-chip ${r ? r.tone : 'muted'}`}>{r ? r.label : '무응답'}</span>
                </div>
              );
            })}
          </div>
        )}

        {open && canRequest && (
          <div style={{ marginTop: 14 }}>
            <label className="field-label">참여자 지정 (역할을 섞지 않습니다 — 요청자·의사결정자·영향부서는 서로 다른 일을 합니다)</label>
            {rows.map((r, i) => (
              <div key={i} style={{ display: 'flex', gap: 7, marginBottom: 7 }}>
                <input className="afs-input" value={r.user_id} placeholder="사용자 ID (예: hikwon@lsmnm.com)"
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, user_id: e.target.value } : x))} />
                <select className="afs-select" style={{ maxWidth: 160 }} value={r.role}
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, role: e.target.value as DecisionRole } : x))}>
                  {(Object.keys(ROLE_KO) as DecisionRole[]).map((k) => (
                    <option key={k} value={k}>{ROLE_KO[k]}</option>
                  ))}
                </select>
                <button className="text-button" onClick={() => setRows(rows.filter((_, j) => j !== i))}
                  disabled={rows.length === 1}>삭제</button>
              </div>
            ))}
            <button className="text-button" onClick={() => setRows([...rows, { user_id: '', role: 'AFFECTED' }])}>
              + 참여자 추가
            </button>
            {!hasDecider && (
              <div className="request-alert warn" style={{ marginTop: 8 }}>
                <i aria-hidden="true">!</i>
                <div><b>의사결정자가 지정되지 않았습니다</b>
                  <small>결정자 없는 안건은 회의만 만들고 아무것도 끝내지 못합니다.</small></div>
              </div>
            )}
            <div style={{ display: 'flex', gap: 7, marginTop: 10, justifyContent: 'flex-end' }}>
              <button className="secondary-button" onClick={() => setOpen(false)}>취소</button>
              <button className="primary-button" disabled={!filled.length || !hasDecider}
                onClick={() => { onRequestReview(filled); setOpen(false); }}>
                검토 요청 보내기
              </button>
            </div>
          </div>
        )}

        {/* 내 의견 — 참여자일 때만. 참여자가 아니면 서버가 404 로 숨긴다. */}
        {d.my_role && (
          <div style={{ marginTop: 16, borderTop: '1px solid var(--line)', paddingTop: 14 }}>
            <label className="field-label">
              내 의견 ({ROLE_KO[d.my_role as DecisionRole]})
              {mine?.response_status ? ` · 현재 «${RESPONSE_KO[mine.response_status].label}»` : ''}
            </label>
            <div className="filter-pills" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
              {(Object.keys(RESPONSE_KO) as ResponseStatus[]).map((k) => (
                <button key={k} className={resp.s === k ? 'active' : ''}
                  onClick={() => setResp({ ...resp, s: k })} title={RESPONSE_KO[k].hint}>
                  {RESPONSE_KO[k].label}
                </button>
              ))}
            </div>
            {/* ★ '정보 부족'을 1급 선택지로 둔다 — 없으면 모르는 부서가 '동의'를 누르고,
                그 동의가 결정의 근거로 쓰인다. */}
            <p className="hint-line">
              {resp.s ? RESPONSE_KO[resp.s].hint
                : '모르면 «정보 부족»이 정당한 답입니다 — 모르는 상태의 동의가 근거로 쓰이는 것이 더 위험합니다.'}
            </p>
            <textarea className="afs-textarea" value={resp.text} rows={3}
              placeholder={needsText ? '내용을 적어야 저장됩니다' : '필요하면 설명을 적으십시오'}
              onChange={(e) => setResp({ ...resp, text: e.target.value })} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="primary-button"
                disabled={!resp.s || (needsText && !resp.text.trim())}
                onClick={() => { if (resp.s) { onRespond(resp.s, resp.text.trim()); setResp({ s: '', text: '' }); } }}>
                의견 저장
              </button>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ── 회의 ─────────────────────────────────────────────────────────────────────
function MeetingPanel({ d, onMeeting }: {
  d: DecisionCase; onMeeting: (b: { title: string; schedule?: string; channel?: string }) => void;
}) {
  const [f, setF] = useState({ title: '', schedule: '', channel: '' });
  const [open, setOpen] = useState(false);
  const can = !['DECIDED', 'ACTIONED', 'EFFECT_MEASURED', 'CANCELLED'].includes(d.status);

  return (
    <Panel kicker="MEETING" title="회의"
      action={can && (
        <button className="secondary-button" style={{ minHeight: 32 }} onClick={() => setOpen(!open)}>
          {open ? '접기' : '회의 요청'}
        </button>
      )}>
      <div style={{ padding: 15 }}>
        {d.meetings.length === 0 ? (
          <div className="empty-note">요청된 회의가 없습니다.</div>
        ) : (
          <div className="people-list">
            {d.meetings.map((m) => (
              <div key={m.meeting_id} className="person">
                <i aria-hidden="true">회</i>
                <div style={{ minWidth: 0 }}>
                  <b>{m.title}</b>
                  <small>
                    {m.schedule || '일정 미정'} · {m.channel || '채널 미정'} · {m.requested_by} 요청
                    {/* ★ 외부 캘린더에 만들어졌는지 여부를 **명시**한다. 시스템이 만든 줄 알고
                        기다리다 회의가 열리지 않는 것이 이 화면이 막으려는 사고다. */}
                    {m.external_created ? ` · 외부 일정 ${m.external_ref}` : ` · ${m.note || '외부 캘린더 미생성'}`}
                  </small>
                </div>
                <span className={`state-chip ${m.external_created ? 'success' : 'warn'}`}>
                  {m.external_created ? '외부 생성됨' : '요청만'}
                </span>
              </div>
            ))}
          </div>
        )}

        {open && can && (
          <div style={{ marginTop: 14 }}>
            <label className="field-label" htmlFor="mt-title">회의 제목 (필수)</label>
            <input id="mt-title" className="afs-input" value={f.title}
              onChange={(e) => setF({ ...f, title: e.target.value })} />
            <div style={{ display: 'flex', gap: 7, marginTop: 8 }}>
              <div style={{ flex: 1 }}>
                <label className="field-label" htmlFor="mt-sch">일정</label>
                <input id="mt-sch" className="afs-input" value={f.schedule} placeholder="예: 2026-08-10 14:00"
                  onChange={(e) => setF({ ...f, schedule: e.target.value })} />
              </div>
              <div style={{ flex: 1 }}>
                <label className="field-label" htmlFor="mt-ch">채널</label>
                <input id="mt-ch" className="afs-input" value={f.channel} placeholder="예: 본관 3층 회의실"
                  onChange={(e) => setF({ ...f, channel: e.target.value })} />
              </div>
            </div>
            <div className="request-alert" style={{ marginTop: 10 }}>
              <i aria-hidden="true">i</i>
              <div><b>외부 캘린더·메시지에는 아무것도 보내지 않습니다</b>
                <small>회의 요청만 기록됩니다. 실제 초대는 사람이 만들어야 합니다 — 시스템이 먼저 보내면 되돌릴 수 없습니다.</small></div>
            </div>
            <div style={{ display: 'flex', gap: 7, marginTop: 10, justifyContent: 'flex-end' }}>
              <button className="secondary-button" onClick={() => setOpen(false)}>취소</button>
              <button className="primary-button" disabled={!f.title.trim()}
                onClick={() => { onMeeting({ ...f, title: f.title.trim() }); setOpen(false); setF({ title: '', schedule: '', channel: '' }); }}>
                회의 요청 기록
              </button>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ── 결정 ─────────────────────────────────────────────────────────────────────
function DecidePanel({ d, onDecide }: {
  d: DecisionCase; onDecide: (b: { outcome: Outcome; rationale: string; conditions?: string }) => void;
}) {
  const [f, setF] = useState<{ outcome: Outcome | ''; rationale: string; conditions: string }>(
    { outcome: '', rationale: '', conditions: '' });

  if (d.status === 'DECIDED' || d.status === 'ACTIONED' || d.status === 'EFFECT_MEASURED') {
    return (
      <Panel kicker="DECIDED" title="결정 기록">
        <div style={{ padding: 15 }}>
          <div className="release-facts" style={{ marginTop: 0 }}>
            <div><span>결과</span><b>{OUTCOME_KO[d.outcome as Outcome]?.label || d.outcome}</b>
              <small>{d.decided_at ? d.decided_at.slice(0, 10) : ''}</small></div>
            <div><span>결정자</span><b>{d.decided_by || '없음'}</b><small>이 기록이 원장에 남습니다</small></div>
            <div><span>근거 지문</span><b>{(d.evidence_hash || '').slice(0, 12)}</b>
              <small>결정 시점의 근거</small></div>
          </div>
          {d.outcome_conditions && (
            <div className="request-alert warn" style={{ marginTop: 10 }}>
              <i aria-hidden="true">!</i>
              <div><b>승인 조건</b><small>{d.outcome_conditions}</small></div>
            </div>
          )}
        </div>
      </Panel>
    );
  }

  // 결정자가 아니면 결정 폼을 아예 두지 않는다 — 눌러 보고 실패하는 버튼은 화면의 거짓말이다.
  if (d.my_role !== 'DECIDER') {
    return (
      <Panel kicker="DECISION" title="결정">
        <div className="empty-note">
          이 안건의 의사결정자만 결정을 기록할 수 있습니다. 현재 내 역할은
          «{ROLE_KO[d.my_role as DecisionRole] || '참여자 아님'}» 입니다.
        </div>
      </Panel>
    );
  }

  const needsConditions = f.outcome === 'CONDITIONAL';
  const ready = !!f.outcome && !!f.rationale.trim() && (!needsConditions || !!f.conditions.trim());

  return (
    <Panel kicker="DECISION" title="결정 기록">
      <div style={{ padding: 15 }}>
        {/* ★ 차단 사유를 버튼 옆에 그대로 쓴다. 비활성 버튼만 두면 사용자는 화면이 고장 났다고
            읽고, 진짜 이유는 아무에게도 도달하지 않는다. */}
        {d.blockers.length > 0 && (
          <div className="request-alert warn" style={{ marginBottom: 12 }}>
            <i aria-hidden="true">!</i>
            <div>
              <b>지금은 결정할 수 없습니다</b>
              <small>{d.blockers.map((b) => b.reason).join(' / ')}</small>
            </div>
          </div>
        )}
        {!['REVIEW_REQUESTED', 'IN_REVIEW', 'MEETING_REQUESTED'].includes(d.status) && (
          <div className="request-alert warn" style={{ marginBottom: 12 }}>
            <i aria-hidden="true">!</i>
            <div><b>검토 요청 후에 결정합니다</b>
              <small>현재 «{DECISION_STATUS_KO[d.status]?.label}» 상태입니다.</small></div>
          </div>
        )}

        <label className="field-label">결정 결과</label>
        <div className="filter-pills" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
          {(Object.keys(OUTCOME_KO) as Outcome[]).map((k) => (
            <button key={k} className={f.outcome === k ? 'active' : ''}
              onClick={() => setF({ ...f, outcome: k })} title={OUTCOME_KO[k].hint}>
              {OUTCOME_KO[k].label}
            </button>
          ))}
        </div>
        <p className="hint-line">{f.outcome ? OUTCOME_KO[f.outcome].hint : '보류와 기각을 구분합니다 — 「일단 승인」이 조건부를 삼키지 않도록.'}</p>

        <label className="field-label" htmlFor="dc-rat">결정 근거 (필수)</label>
        <textarea id="dc-rat" className="afs-textarea" rows={3} value={f.rationale}
          placeholder="근거 없는 승인은 나중에 설명할 수 없습니다"
          onChange={(e) => setF({ ...f, rationale: e.target.value })} />

        {needsConditions && (
          <>
            <label className="field-label" htmlFor="dc-cond" style={{ marginTop: 10 }}>
              승인 조건 (조건부 승인에는 필수)
            </label>
            <textarea id="dc-cond" className="afs-textarea" rows={2} value={f.conditions}
              placeholder="조건 없는 조건부는 그냥 승인이고, 실행 단계에서 아무도 조건을 확인하지 않습니다"
              onChange={(e) => setF({ ...f, conditions: e.target.value })} />
          </>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
          <button className="primary-button" disabled={!ready || !d.can_decide}
            onClick={() => f.outcome && onDecide({
              outcome: f.outcome, rationale: f.rationale.trim(),
              conditions: f.conditions.trim() || undefined,
            })}>
            결정 기록하기
          </button>
        </div>
      </div>
    </Panel>
  );
}

// ── 실행과제·효과 ────────────────────────────────────────────────────────────
function ActionPanel({ d, onActions, onMeasure }: {
  d: DecisionCase;
  onActions: (a: { action: string; owner_user_id: string; due_at: string }[]) => void;
  onMeasure: (actionId: string, v: string) => void;
}) {
  const [rows, setRows] = useState([{ action: '', owner_user_id: '', due_at: '' }]);
  const [open, setOpen] = useState(false);
  const [measuring, setMeasuring] = useState<{ id: string; v: string } | null>(null);
  const filled = rows.filter((r) => r.action.trim() && r.owner_user_id.trim() && r.due_at.trim());

  const measured = d.actions.filter((a: DecisionAction) => a.status === 'MEASURED').length;

  return (
    <Panel kicker="EXECUTION" title="실행과제와 효과"
      action={
        <button className="secondary-button" style={{ minHeight: 32 }} onClick={() => setOpen(!open)}>
          {open ? '접기' : '실행과제 추가'}
        </button>
      }>
      <div style={{ padding: 15 }}>
        {d.actions.length === 0 ? (
          <div className="empty-note">
            실행과제가 없습니다. 결정이 실행으로 이어지지 않는 가장 흔한 경로가 여기입니다 —
            담당과 기한을 가진 과제를 만드십시오.
          </div>
        ) : (
          <>
            <p className="hint-line">
              {/* ⚠️ 미측정과 0 을 같은 색으로 두지 않는다. 0 은 "효과가 없었다"이고 미측정은
                  "아직 모른다"다 — 실패한 결정과 측정하지 않은 결정이 같아 보이면 안 된다. */}
              전체 {d.actions.length}건 중 <b>{measured}건 측정 완료</b> · 나머지 {d.actions.length - measured}건은
              «미측정»입니다(효과 없음이 아닙니다).
            </p>
            <div className="people-list">
              {d.actions.map((a) => (
                <div key={a.action_id} className="person">
                  <i aria-hidden="true">{a.status === 'MEASURED' ? '측' : '과'}</i>
                  <div style={{ minWidth: 0 }}>
                    <b style={{ whiteSpace: 'normal' }}>{a.action}</b>
                    <small>
                      담당 {a.owner_user_id} · 기한 {a.due_at}
                      {a.status === 'MEASURED'
                        ? ` · 효과: ${a.measured_effect}${a.measured_at ? ` (${a.measured_at.slice(0, 10)})` : ''}`
                        : ' · 효과 미측정 — 아직 모릅니다'}
                    </small>
                    {measuring?.id === a.action_id && (
                      <div style={{ marginTop: 8 }}>
                        <label className="field-label" htmlFor={`ms-${a.action_id}`}>
                          측정값 (결정 당시 기준선 {d.baseline_id || '(없음)'} 대비)
                        </label>
                        <textarea id={`ms-${a.action_id}`} className="afs-textarea" rows={2} value={measuring.v}
                          placeholder="빈 값을 0 으로 저장하지 않습니다 — 모르면 미측정으로 두십시오"
                          onChange={(e) => setMeasuring({ ...measuring, v: e.target.value })} />
                        <div style={{ display: 'flex', gap: 7, marginTop: 8, justifyContent: 'flex-end' }}>
                          <button className="secondary-button" onClick={() => setMeasuring(null)}>취소</button>
                          <button className="primary-button" disabled={!measuring.v.trim()}
                            onClick={() => { onMeasure(a.action_id, measuring.v.trim()); setMeasuring(null); }}>
                            효과 기록
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className={`state-chip ${a.status === 'MEASURED' ? 'success' : 'muted'}`}>
                      {a.status === 'MEASURED' ? '측정됨' : '미측정'}
                    </span>
                    {measuring?.id !== a.action_id && (
                      <button className="text-button" onClick={() => setMeasuring({ id: a.action_id, v: '' })}>
                        효과 기록
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {open && (
          <div style={{ marginTop: 14 }}>
            <label className="field-label">
              실행과제 — 담당과 기한이 없으면 만들지 않습니다
            </label>
            {rows.map((r, i) => (
              <div key={i} style={{ display: 'flex', gap: 7, marginBottom: 7 }}>
                <input className="afs-input" value={r.action} placeholder="무엇을 합니까"
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, action: e.target.value } : x))} />
                <input className="afs-input" style={{ maxWidth: 200 }} value={r.owner_user_id} placeholder="담당자 ID"
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, owner_user_id: e.target.value } : x))} />
                <input className="afs-input" style={{ maxWidth: 150 }} type="date" value={r.due_at}
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, due_at: e.target.value } : x))} />
                <button className="text-button" disabled={rows.length === 1}
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}>삭제</button>
              </div>
            ))}
            <button className="text-button"
              onClick={() => setRows([...rows, { action: '', owner_user_id: '', due_at: '' }])}>
              + 과제 추가
            </button>
            <div style={{ display: 'flex', gap: 7, marginTop: 10, justifyContent: 'flex-end' }}>
              <button className="secondary-button" onClick={() => setOpen(false)}>취소</button>
              <button className="primary-button" disabled={!filled.length}
                onClick={() => { onActions(filled); setOpen(false); setRows([{ action: '', owner_user_id: '', due_at: '' }]); }}>
                실행과제 생성
              </button>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ── 새 안건 ──────────────────────────────────────────────────────────────────
function CreateScreen({ runIds, onCancel, onSubmit }: {
  runIds: string[];
  onCancel: () => void;
  onSubmit: (runId: string, body: {
    question: string; package: Record<string, any>; evidence: Record<string, any>;
    baseline_id: string; scenario_id: string; due_at: string;
  }) => void;
}) {
  const [head, setHead] = useState({
    run_id: runIds[0] || '', question: '', baseline_id: '', scenario_id: '', due_at: '',
  });
  const [fields, setFields] = useState<Record<string, string>>({});
  const [ev, setEv] = useState<{ key: string; value: string; verified: boolean }[]>([]);
  const [showAll, setShowAll] = useState(false);

  const required = PACKAGE_FIELDS.filter((f) => f.required);
  const optional = PACKAGE_FIELDS.filter((f) => !f.required);
  const ready = !!head.run_id.trim() && !!head.question.trim()
    && required.every((f) => (fields[f.key] || '').trim());

  const build = () => {
    const pkg: Record<string, any> = {};
    for (const f of PACKAGE_FIELDS) {
      const raw = (fields[f.key] || '').trim();
      if (!raw) continue;
      // 여러 줄이면 목록으로 보낸다 — 대안 비교는 목록이라야 검토서에서 나란히 읽힌다.
      const lines = raw.split('\n').map((x) => x.trim()).filter(Boolean);
      pkg[f.key] = lines.length > 1 ? lines : raw;
    }
    const evidence: Record<string, any> = {};
    for (const e of ev) {
      const k = e.key.trim();
      if (!k) continue;
      // `verified: false` 는 서버에서 **결정 차단** 사유가 된다 — 그 사실을 화면이 미리 말한다.
      evidence[k] = { value: e.value.trim(), verified: e.verified };
    }
    return { pkg, evidence };
  };

  const unverified = ev.filter((e) => e.key.trim() && !e.verified).length;

  return (
    <>
      <ScreenHead kicker="NEW PACKAGE" title="새 Decision Package"
        description="시뮬레이션 결과를 하나의 문서로 만듭니다. 세 관점 검토서를 따로 만들지 않습니다 — 이 문서 하나를 관점별로 렌더링합니다."
        chip={{ label: ready ? '만들 준비 완료' : '입력 중', tone: ready ? 'success' : 'data' }} />

      <Panel kicker="SOURCE" title="근거가 되는 시뮬레이션">
        <div style={{ padding: 15 }}>
          <label className="field-label" htmlFor="nc-run">시뮬레이션 실행 ID (필수)</label>
          {runIds.length > 0 ? (
            <select id="nc-run" className="afs-select" value={head.run_id}
              onChange={(e) => setHead({ ...head, run_id: e.target.value })}>
              <option value="">— 선택 —</option>
              {runIds.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          ) : (
            <>
              <input id="nc-run" className="afs-input" value={head.run_id} placeholder="run_id"
                onChange={(e) => setHead({ ...head, run_id: e.target.value })} />
              {/* ★ 선택 목록을 지어내지 않는다. 시뮬레이션 실행을 열거하는 API 가 아직 없으므로
                  «없다»고 말하고 붙여 넣게 한다 — 그럴듯한 가짜 목록을 두면 사용자는 존재하지
                  않는 실행을 근거로 안건을 만든다. */}
              <p className="hint-line">
                시뮬레이션 실행 목록을 제공하는 API 가 아직 없습니다 — 결과 화면의 실행 ID 를
                붙여 넣으십시오. 이 값은 나중에 «이 결정의 근거가 어느 실행이었는가»를 되짚는
                유일한 연결입니다.
              </p>
            </>
          )}

          <div style={{ display: 'flex', gap: 7, marginTop: 10 }}>
            <div style={{ flex: 1 }}>
              <label className="field-label" htmlFor="nc-base">기준선 ID</label>
              <input id="nc-base" className="afs-input" value={head.baseline_id}
                onChange={(e) => setHead({ ...head, baseline_id: e.target.value })} />
            </div>
            <div style={{ flex: 1 }}>
              <label className="field-label" htmlFor="nc-scn">시나리오 ID</label>
              <input id="nc-scn" className="afs-input" value={head.scenario_id}
                onChange={(e) => setHead({ ...head, scenario_id: e.target.value })} />
            </div>
            <div style={{ flex: 1 }}>
              <label className="field-label" htmlFor="nc-due">기한</label>
              <input id="nc-due" className="afs-input" type="date" value={head.due_at}
                onChange={(e) => setHead({ ...head, due_at: e.target.value })} />
            </div>
          </div>

          {/* ★ 기준선 없이 만들 수는 있지만 **결정은 막힌다**. 그 사실을 만들기 전에 말한다 —
              나중에 결정 단계에서 알면 검토 시간이 통째로 낭비된다. */}
          {!head.baseline_id.trim() && (
            <div className="request-alert warn" style={{ marginTop: 10 }}>
              <i aria-hidden="true">!</i>
              <div><b>기준선이 없으면 결정 단계에서 막힙니다</b>
                <small>무엇과 비교해 결정하는지 알 수 없기 때문입니다. 지금 넣어 두는 편이 낫습니다.</small></div>
            </div>
          )}
        </div>
      </Panel>

      <Panel kicker="QUESTION" title="결정 문장">
        <div style={{ padding: 15 }}>
          <label className="field-label" htmlFor="nc-q">무엇을 승인·기각합니까 (필수)</label>
          <textarea id="nc-q" className="afs-textarea" rows={2} value={head.question}
            placeholder="예: 2공정 정련로 2호기 가동률을 78% → 85% 로 상향하고 8월부터 적용할 것인가"
            onChange={(e) => setHead({ ...head, question: e.target.value })} />
          <p className="hint-line">
            «검토 요청» 같은 제목만 있으면 참석자는 무엇을 결정하는지 모르고, 회의록에는 «논의함»만 남습니다.
          </p>
        </div>
      </Panel>

      <Panel kicker="PACKAGE" title="문서 내용"
        action={
          <button className="secondary-button" style={{ minHeight: 32 }} onClick={() => setShowAll(!showAll)}>
            {showAll ? '필수만 보기' : `선택 항목 ${optional.length}개 펼치기`}
          </button>
        }>
        <div style={{ padding: 15 }}>
          {required.map((f) => (
            <div key={f.key} style={{ marginBottom: 12 }}>
              <label className="field-label" htmlFor={`pk-${f.key}`}>
                {f.label} (필수 · {VIEW_KO[f.view].label})
              </label>
              <textarea id={`pk-${f.key}`} className="afs-textarea" rows={3} value={fields[f.key] || ''}
                placeholder={f.key === 'options'
                  ? '한 줄에 대안 하나씩 적으십시오 — 목록으로 저장되어 검토서에서 나란히 읽힙니다'
                  : '무행동(아무것도 하지 않을 때)을 포함해 적으십시오'}
                onChange={(e) => setFields({ ...fields, [f.key]: e.target.value })} />
            </div>
          ))}
          <p className="hint-line">
            기준안과 대안이 없으면 비교할 것이 없고, 결정은 «하자/말자»만 남습니다.
            나머지 항목은 비워 두어도 되지만, 검토서에 <b>«미작성»으로 그대로 표시</b>됩니다 —
            숨기지 않는 이유는 검토자가 그 항목이 검토됐다고 오해하지 않게 하기 위함입니다.
          </p>

          {showAll && (
            <div style={{ marginTop: 14, borderTop: '1px solid var(--line)', paddingTop: 14 }}>
              {(Object.keys(VIEW_KO) as ViewKey[]).map((vk) => (
                <div key={vk} style={{ marginBottom: 12 }}>
                  <p className="view-who" style={{ marginBottom: 8 }}>{VIEW_KO[vk].label} — {VIEW_KO[vk].who}</p>
                  {optional.filter((f) => f.view === vk).map((f) => (
                    <div key={f.key} style={{ marginBottom: 10 }}>
                      <label className="field-label" htmlFor={`pk-${f.key}`}>{f.label}</label>
                      <textarea id={`pk-${f.key}`} className="afs-textarea" rows={2} value={fields[f.key] || ''}
                        onChange={(e) => setFields({ ...fields, [f.key]: e.target.value })} />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>

      <Panel kicker="EVIDENCE" title="핵심 근거"
        action={
          <button className="secondary-button" style={{ minHeight: 32 }}
            onClick={() => setEv([...ev, { key: '', value: '', verified: true }])}>
            + 근거 추가
          </button>
        }>
        <div style={{ padding: 15 }}>
          {ev.length === 0 ? (
            <div className="empty-note">
              등록된 근거가 없습니다. 근거는 지문(hash)으로 고정되며, 등록 뒤 내용이 바뀌면
              결정이 막힙니다 — 참석자가 읽은 숫자와 결정된 숫자가 달라지지 않게 하기 위함입니다.
            </div>
          ) : ev.map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 7, marginBottom: 7, alignItems: 'flex-start' }}>
              <input className="afs-input" style={{ maxWidth: 200 }} value={e.key} placeholder="근거 이름"
                onChange={(x) => setEv(ev.map((y, j) => j === i ? { ...y, key: x.target.value } : y))} />
              <input className="afs-input" value={e.value} placeholder="값·출처"
                onChange={(x) => setEv(ev.map((y, j) => j === i ? { ...y, value: x.target.value } : y))} />
              <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, whiteSpace: 'nowrap', padding: '9px 0' }}>
                <input type="checkbox" checked={e.verified}
                  onChange={(x) => setEv(ev.map((y, j) => j === i ? { ...y, verified: x.target.checked } : y))} />
                검증됨
              </label>
              <button className="text-button" onClick={() => setEv(ev.filter((_, j) => j !== i))}>삭제</button>
            </div>
          ))}
          {unverified > 0 && (
            <div className="request-alert warn" style={{ marginTop: 8 }}>
              <i aria-hidden="true">!</i>
              <div><b>검증되지 않은 근거 {unverified}건</b>
                <small>검증 표시가 없으면 결정 단계에서 막힙니다. 지금 검증하거나, 근거에서 빼십시오.</small></div>
            </div>
          )}
        </div>
      </Panel>

      <div style={{ display: 'flex', gap: 7, justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="secondary-button" onClick={onCancel}>취소</button>
        <button className="primary-button" disabled={!ready}
          onClick={() => {
            const { pkg, evidence } = build();
            onSubmit(head.run_id.trim(), {
              question: head.question.trim(), package: pkg, evidence,
              baseline_id: head.baseline_id.trim(), scenario_id: head.scenario_id.trim(),
              due_at: head.due_at,
            });
          }}>
          Decision Package 만들기
        </button>
      </div>
    </>
  );
}
