// [CL-1 · UIUX] 협업 허브 — 승인 시안(Living Enterprise Canvas) 기준선 위에서 동작하는 실제 화면
//
// 이 화면이 반드시 보여줘야 하는 것(서버가 문구까지 준다 — 화면이 지어내지 않는다):
//   ① 수락 후 "데이터 접근 범위는 넓어지지 않았습니다" — 없으면 사용자는 앱을 받으면 자료도
//      보인다고 믿는다. 그 오해가 곧 권한 우회에 대한 잘못된 안심이다.
//   ② 401 과 404 의 구분 — "사용자를 지정하십시오"와 "그 요청은 없습니다"는 다른 행동을 요구한다.
//   ③ 앱이 요구하는 권한(Capability Manifest)과 "별도 로그인 없음" — 자체 로그인 화면을 만난
//      순간 사용자가 이상하다고 신고할 수 있어야 한다.
//
// ⚠️ 브라우저 `prompt()`/`alert()` 를 쓰지 않는다. 승인 시안에 없고, 키보드 접근·스크린리더
//   대응이 되지 않으며 스타일도 입힐 수 없다 — 화면 안 입력으로 처리한다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../../design/HubShell';
import { HubDialog } from '../../design/HubDialog';
import { JarvisRail } from '../../design/JarvisRail';
import type { JarvisContext } from '../../lib/jarvisApi';
import {
  collaborationApi, DELIVERY_STATUS_KO, type CapabilityManifest, type Delivery, type PocketApp,
} from '../../lib/collaborationApi';

type View = 'inbox' | 'apps' | 'deliver' | 'sent';

const STATUS_CHIP: Record<string, string> = {
  PENDING: 'warn', ACCEPTED: 'success', REJECTED: 'muted', EXPIRED: 'muted', REVOKED: 'danger',
};
const DOT: Record<string, string> = {
  PENDING: 'wait', ACCEPTED: 'good', REJECTED: 'off', EXPIRED: 'off', REVOKED: 'bad',
};

function StatusChip({ status }: { status: Delivery['status'] }) {
  const s = DELIVERY_STATUS_KO[status] ?? { label: status };
  return <span className={`state-chip ${STATUS_CHIP[status] || 'muted'}`}>{s.label}</span>;
}

/** 앱이 요구하는 권한. **비어 있으면 "요구 없음"이라고 말한다** — 빈 카드를 두면 사용자는
 *  화면이 덜 만들어진 것으로 읽고 그냥 수락한다. */
function CapabilityManifestCard({ m }: { m: CapabilityManifest }) {
  const caps = useMemo(() => {
    if (m?.required_capabilities?.length) return m.required_capabilities;
    return (m?.capabilities || []).map((c) => {
      const i = c.lastIndexOf('.');
      return i > 0 ? { resource: c.slice(0, i), actions: [c.slice(i + 1)] }
        : { resource: c, actions: [] as string[] };
    });
  }, [m]);
  const inherited = m?.auth_mode === 'PLATFORM_INHERITED';
  return (
    <div className="capability-manifest">
      <header>
        <b>이 앱이 요구하는 것</b>
        <span>{inherited ? '플랫폼 인증 상속' : (m?.auth_mode || '인증 방식 미지정')}</span>
      </header>
      {caps.length === 0 ? (
        <ul><li><i aria-hidden="true">–</i><div><b>요구하는 데이터 권한이 없습니다</b>
          <small>이 앱은 별도 자료 접근 없이 동작합니다.</small></div></li></ul>
      ) : (
        <ul>
          {caps.map((c) => (
            <li key={c.resource}>
              <i aria-hidden="true">✓</i>
              <div>
                <b>{c.resource}</b>
                <small>{c.actions.length ? c.actions.join(' · ') : '동작 미지정'}</small>
              </div>
            </li>
          ))}
        </ul>
      )}
      <footer>
        {inherited
          ? '별도 로그인 없이 현재 사용자·조직 권한으로 실행됩니다. 앱이 자체 로그인 화면을 띄우면 관리자에게 알려 주십시오.'
          : '인증 방식이 확인되지 않았습니다 — 관리자에게 문의하십시오.'}
        {m?.required_data_scopes?.length ? ` · 데이터 범위: ${m.required_data_scopes.join(', ')}` : ''}
      </footer>
    </div>
  );
}

export function CollaborationHub({ onClose, initialView = 'inbox', releaseIds = [] }: {
  onClose: () => void;
  initialView?: View;
  releaseIds?: string[];
}) {
  const [view, setView] = useState<View>(initialView);
  const [inbox, setInbox] = useState<Delivery[]>([]);
  const [sent, setSent] = useState<Delivery[]>([]);
  const [apps, setApps] = useState<PocketApp[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>('');

  const load = useCallback(async () => {
    setBusy('불러오는 중'); setErr(null);
    try {
      const [i, s, a] = await Promise.all([
        collaborationApi.inbox(), collaborationApi.outbox(), collaborationApi.myApps(),
      ]);
      setInbox(i); setSent(s); setApps(a);
    } catch (e: any) {
      setErr({ msg: e?.message || String(e), status: e?.status });
    } finally { setBusy(null); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ★ 사용자가 바뀌면 이전 수신함·주머니를 **즉시 폐기**한다(§CL-FE-03). 남겨 두면 다른
  //   사용자의 목록이 화면에 그대로 남고, 그것이 곧 유출이다.
  useEffect(() => {
    const h = () => { setInbox([]); setSent([]); setApps([]); setSelectedId(''); load(); };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [load]);

  const act = async (label: string, fn: () => Promise<any>) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      const r = await fn();
      // 서버가 준 문구를 그대로 보여준다 — 화면이 지어내면 서버 규칙과 갈라진다.
      setFlash(r?.scope_note || r?.note || null);
      await load();
      return r;
    } catch (e: any) {
      setErr({ msg: e?.message || String(e), status: e?.status });
    } finally { setBusy(null); }
  };

  const pending = inbox.filter((d) => d.status === 'PENDING');
  const selected = useMemo(
    () => inbox.find((d) => d.delivery_id === selectedId) || pending[0] || inbox[0] || null,
    [inbox, pending, selectedId]);

  const items: RailItem[] = [
    { id: 'inbox', label: '받은 앱', hint: '나에게 전달된 요청', mark: '받', count: pending.length },
    { id: 'apps', label: '내 앱', hint: '수락해서 쓰는 앱', mark: '앱', count: apps.length },
    { id: 'deliver', label: '사용자에게 전달', hint: '지정한 한 사람에게', mark: '전' },
    { id: 'sent', label: '보낸 요청', hint: '응답 상태와 회수', mark: '보' },
  ];

  // Jarvis 문맥 — **선택된 객체**를 그대로 넘긴다. Task ID 를 사용자에게 묻지 않는다(§3-8).
  const jarvisCtx = (() => {
    if (view === 'apps') {
      return { title: apps.length ? `내 앱 ${apps.length}개` : '내 앱 없음',
        desc: '수락한 앱은 현재 사용자·조직 권한으로 실행됩니다.',
        ev: apps.slice(0, 3).map((a) => ({ label: a.display_name, value: a.release_id })) };
    }
    if (view === 'sent') {
      return { title: sent.length ? `보낸 요청 ${sent.length}건` : '보낸 요청 없음',
        desc: '수락 전에는 언제든 회수할 수 있습니다.',
        ev: sent.slice(0, 3).map((d) => ({ label: d.recipient_user_id, value: DELIVERY_STATUS_KO[d.status]?.label || d.status })) };
    }
    if (selected) {
      return {
        title: selected.release_id,
        desc: selected.purpose,
        ev: [
          { label: '보낸 사람', value: selected.sender_user_id },
          { label: '상태', value: DELIVERY_STATUS_KO[selected.status]?.label || selected.status },
          { label: 'Manifest 지문', value: (selected.manifest_fingerprint || '').slice(0, 12) || '없음' },
          { label: '만료', value: selected.expires_at || '없음' },
        ],
      };
    }
    return { title: '협업', desc: '앱 전달·수락·내 앱을 한곳에서 다룹니다.', ev: [] };
  })();

  // ★ [지적 4] Jarvis 가 참조하는 객체 = 화면이 강조 중인 객체. 두 값이 갈라지면 사용자는
  //   A 를 보면서 B 에 대한 답을 읽는다 — 가장 발견하기 어려운 오답이다.
  const jarvisContext: JarvisContext = {
    current_module: `collaboration/${view}`,
    selected_object_type: view === 'apps' ? 'app_pocket' : 'app_delivery',
    selected_object_id: view === 'apps' ? (apps[0]?.pocket_id || '') : (selected?.delivery_id || ''),
    object_snapshot: selected ? {
      release_id: selected.release_id, purpose: selected.purpose, status: selected.status,
      expires_at: selected.expires_at, sender: selected.sender_user_id,
      capabilities: selected.manifest_snapshot?.capabilities || [],
      auth_mode: selected.manifest_snapshot?.auth_mode,
    } : { inbox_count: inbox.length, apps_count: apps.length, sent_count: sent.length },
    available_actions: selected?.can_respond
      ? ['수락', '거절', '재배정 요청'] : selected?.can_revoke ? ['회수'] : [],
    evidence_refs: selected?.manifest_fingerprint
      ? [{ manifest_fingerprint: selected.manifest_fingerprint }] : [],
  };

  return (
    // ★ [교차검토 지적 1] 손으로 만든 `fixed div` 는 모달이 아니었다 — dialog semantics·배경
    //   inert·포커스 트랩·Escape·포커스 복귀·스크롤 잠금이 모두 없었다. 셸 공통 기반으로 옮겼다.
    <HubDialog label="협업 — 앱 전달·수락·내 앱" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>협업</b>
        <span>개인 전달은 부서 공유·전사 승격과 별개이며, 수락해도 데이터 권한은 넓어지지 않습니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">{busy}…</span>}
          <button onClick={onClose} className="secondary-button" style={{ minHeight: 32 }}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
          <HubShell
            kicker="COLLABORATION"
            title="앱 전달과 공동 업무"
            subtitle="만든 앱을 사람에게 전달하고, 받은 앱을 내 주머니에서 실행합니다."
            items={items} activeId={view} onSelect={(id) => setView(id as View)}
            footer={
              <div className="inheritance-card">
                <span>APP-IN-APP</span>
                <b>플랫폼 인증 상속</b>
                <p>
                  전달된 앱은 자체 로그인을 갖지 않습니다. 현재 사용자·조직·역할로 실행되며,
                  수락해도 볼 수 있는 자료가 늘어나지 않습니다.
                </p>
              </div>
            }
            jarvis={
              // ⚠️ [지적 3] 고정 문자열 응답을 제거했다. 실제 어댑터(`lib/jarvisApi.ts`)를 호출하고
              //   대화는 레일 안에서 유지된다. 연결 실패는 숨기지 않고 그대로 표시한다.
              <JarvisRail
                contextTitle={jarvisCtx.title}
                contextDescription={jarvisCtx.desc}
                evidence={jarvisCtx.ev}
                context={jarvisContext}
                quickQuestions={[
                  '이 앱은 어떤 자료를 요구합니까?',
                  '수락하면 제 권한이 넓어집니까?',
                  '이 요청은 언제 만료됩니까?',
                ]}
              />
            }
          >
            {err && (
              <Banner tone="error"
                title={err.status === 401 ? '사용자 지정이 필요합니다'
                  : err.status === 404 ? '요청을 찾을 수 없습니다' : '오류'}>
                {err.msg}
              </Banner>
            )}
            {flash && <Banner tone="info">{flash}</Banner>}

            {view === 'inbox' && (
              <InboxScreen list={inbox} selectedId={selected?.delivery_id || ''}
                onSelect={setSelectedId}
                onAccept={(d) => act('수락 중', () => collaborationApi.accept(d.delivery_id))}
                onReject={(d, n) => act('거절 중', () => collaborationApi.reject(d.delivery_id, n))}
                onReassign={(d, n) => act('재배정 요청 중', () => collaborationApi.reassign(d.delivery_id, n))} />
            )}
            {view === 'apps' && (
              <AppsScreen list={apps}
                onPin={(a) => act('갱신 중', () => collaborationApi.patchApp(a.pocket_id, { pinned: !a.pinned }))}
                onRename={(a, n) => act('이름 변경 중', () => collaborationApi.patchApp(a.pocket_id, { display_name: n }))} />
            )}
            {view === 'deliver' && (
              <DeliverScreen releaseIds={releaseIds}
                onSubmit={async (f) => {
                  const r = await act('전달 중', () => collaborationApi.create({
                    release_id: f.release_id, recipient_user_id: f.recipient, purpose: f.purpose,
                    // 중복 클릭에도 하나만 생기게 — 서버가 같은 키를 재생한다.
                    idempotency_key: `${f.release_id}|${f.recipient}|${f.purpose}`.slice(0, 120),
                  }));
                  if (r) setView('sent');
                }} />
            )}
            {view === 'sent' && (
              <SentScreen list={sent}
                onRevoke={(d, r) => act('회수 중', () => collaborationApi.revoke(d.delivery_id, r))} />
            )}
          </HubShell>
      </div>
    </HubDialog>
  );
}

// ── 받은 앱 ──────────────────────────────────────────────────────────────────
function InboxScreen({ list, selectedId, onSelect, onAccept, onReject, onReassign }: {
  list: Delivery[]; selectedId: string; onSelect: (id: string) => void;
  onAccept: (d: Delivery) => void;
  onReject: (d: Delivery, note: string) => void;
  onReassign: (d: Delivery, note: string) => void;
}) {
  const [filter, setFilter] = useState<'all' | 'pending'>('pending');
  // 화면 안 입력 — `prompt()` 를 쓰지 않는다(키보드·스크린리더·스타일 모두 안 되기 때문).
  const [form, setForm] = useState<{ id: string; kind: 'reject' | 'reassign'; note: string } | null>(null);

  const shown = filter === 'pending' ? list.filter((d) => d.status === 'PENDING') : list;
  const pendingCount = list.filter((d) => d.status === 'PENDING').length;

  return (
    <>
      <ScreenHead kicker="INBOX" title="받은 앱"
        description="다른 사용자가 나에게 전달한 앱입니다. 수락하면 내 앱 주머니에 담기며, 데이터 접근 범위는 넓어지지 않습니다."
        chip={{ label: pendingCount ? `응답 대기 ${pendingCount}건` : '대기 없음',
          tone: pendingCount ? 'warn' : 'success' }} />

      <Panel kicker="REQUESTS" title="전달 요청"
        action={
          <div className="filter-pills">
            <button className={filter === 'pending' ? 'active' : ''} onClick={() => setFilter('pending')}>대기</button>
            <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>전체</button>
          </div>
        }>
        {shown.length === 0 ? (
          <div className="empty-note">
            {filter === 'pending'
              ? '응답을 기다리는 요청이 없습니다. 전체를 보려면 위의 «전체» 를 누르십시오.'
              : '받은 앱 요청이 없습니다. 다른 사용자가 앱을 전달하면 여기에 나타납니다.'}
          </div>
        ) : shown.map((d) => (
          <article key={d.delivery_id}
            className={`request-card ${d.delivery_id === selectedId ? 'active' : ''}`}>
            {/* ⚠️ [지적 4] 이전에는 `onMouseEnter` 로만 선택이 바뀌어 **키보드 사용자는 Jarvis
                문맥을 바꿀 수 없었다.** 명시적 선택 버튼 + focus 선택으로 바꿨다. */}
            <button type="button" className="request-select"
              aria-pressed={d.delivery_id === selectedId}
              onClick={() => onSelect(d.delivery_id)}
              onFocus={() => onSelect(d.delivery_id)}>
              <span className="app-mark" aria-hidden="true">{d.release_id.slice(-2)}</span>
              <span className="request-select-main">
                <small>{d.release_version ? `v${d.release_version}` : 'RELEASE'}</small>
                <b>{d.release_id}</b>
                <span className="purpose">{d.purpose}</span>
              </span>
              <span className="request-select-side">
                <StatusChip status={d.status} />
                <time>{(d.created_at || '').slice(0, 10)}</time>
                <em>{d.delivery_id === selectedId ? '선택됨' : '선택'}</em>
              </span>
            </button>

            <div className="request-scope">
              <div><span>보낸 사람</span><b>{d.sender_user_id}</b></div>
              <div><span>만료</span><b>{d.expires_at || '없음'}</b></div>
              <div><span>Manifest 지문</span><b>{(d.manifest_fingerprint || '').slice(0, 12) || '없음'}</b></div>
            </div>

            <div style={{ padding: '0 15px' }}>
              <CapabilityManifestCard m={d.manifest_snapshot} />
            </div>

            {/* 권한이 넓어지지 않는다는 사실을 **수락 전에** 말한다 — 수락 후에만 말하면 늦다. */}
            <div className="request-alert" style={{ marginTop: 12 }}>
              <i aria-hidden="true">i</i>
              <div>
                <b>수락해도 볼 수 있는 자료가 늘어나지 않습니다</b>
                <small>앱은 현재 사용자 권한으로 실행됩니다. 원래 보이지 않던 자료는 앱에서도 보이지 않습니다.</small>
              </div>
            </div>

            {d.note && (
              <div className="request-alert warn" style={{ marginTop: 8 }}>
                <i aria-hidden="true">!</i><div><b>{d.note}</b></div>
              </div>
            )}

            {d.can_respond ? (
              <>
                <footer>
                  <button className="secondary-button"
                    onClick={() => setForm({ id: d.delivery_id, kind: 'reassign', note: '' })}>
                    담당 아님 · 재배정 요청
                  </button>
                  <button className="danger-ghost"
                    onClick={() => setForm({ id: d.delivery_id, kind: 'reject', note: '' })}>
                    거절
                  </button>
                  <button className="primary-button" onClick={() => onAccept(d)}>
                    수락하고 내 앱에 추가
                  </button>
                </footer>
                {form?.id === d.delivery_id && (
                  <div style={{ padding: '0 15px 15px' }}>
                    <label className="field-label" htmlFor={`note-${d.delivery_id}`}>
                      {form.kind === 'reject'
                        ? '거절 사유 (보낸 사람이 다시 판단할 근거가 됩니다)'
                        : '누가 담당인지 알려 주십시오 (시스템이 자동 배정하지 않습니다)'}
                    </label>
                    <textarea id={`note-${d.delivery_id}`} className="afs-textarea" value={form.note}
                      onChange={(e) => setForm({ ...form, note: e.target.value })} />
                    <div style={{ display: 'flex', gap: 7, marginTop: 8, justifyContent: 'flex-end' }}>
                      <button className="secondary-button" onClick={() => setForm(null)}>취소</button>
                      <button className="primary-button" disabled={!form.note.trim()}
                        onClick={() => {
                          const n = form.note.trim();
                          if (!n) return;
                          if (form.kind === 'reject') onReject(d, n); else onReassign(d, n);
                          setForm(null);
                        }}>
                        {form.kind === 'reject' ? '거절 보내기' : '재배정 요청 보내기'}
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <footer style={{ justifyContent: 'flex-start', color: 'var(--muted)', fontSize: 11 }}>
                {d.responded_at ? `${d.responded_at.slice(0, 10)} 응답` : '응답할 수 없는 상태입니다'}
                {d.response_note ? ` · ${d.response_note}` : ''}
              </footer>
            )}
          </article>
        ))}
      </Panel>
    </>
  );
}

// ── 내 앱 ────────────────────────────────────────────────────────────────────
function AppsScreen({ list, onPin, onRename }: {
  list: PocketApp[]; onPin: (a: PocketApp) => void; onRename: (a: PocketApp, n: string) => void;
}) {
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const colors = ['blue', 'green', 'orange', 'violet'];
  return (
    <>
      <ScreenHead kicker="MY APPS" title="내 앱"
        description="수락한 앱입니다. 현재 사용자·조직 권한으로 실행되며 별도 로그인이 없습니다."
        chip={{ label: `${list.length}개`, tone: list.length ? 'success' : 'muted' }} />
      <Panel kicker="POCKET" title="앱 주머니">
        {list.length === 0 ? (
          <div className="empty-note">
            수락한 앱이 없습니다. <b>받은 앱</b>에서 요청을 수락하면 여기에 담깁니다.
          </div>
        ) : (
          <div className="app-pocket">
            {list.map((a, idx) => (
              <div key={a.pocket_id}>
                <i className={colors[idx % colors.length]} aria-hidden="true">
                  {a.display_name.slice(0, 2)}
                </i>
                <div>
                  {editing?.id === a.pocket_id ? (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input className="afs-input" value={editing.name} autoFocus
                        onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && editing.name.trim()) {
                            onRename(a, editing.name.trim()); setEditing(null);
                          }
                          if (e.key === 'Escape') setEditing(null);
                        }} />
                      <button className="secondary-button" style={{ minHeight: 32 }}
                        onClick={() => { if (editing.name.trim()) onRename(a, editing.name.trim()); setEditing(null); }}>
                        저장
                      </button>
                    </div>
                  ) : (
                    <>
                      <b>{a.display_name}</b>
                      <small>{a.release_id} · {a.accepted_at ? `${a.accepted_at.slice(0, 10)} 수락` : ''}</small>
                    </>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button className="text-button" onClick={() => setEditing({ id: a.pocket_id, name: a.display_name })}>
                    이름 변경
                  </button>
                  <button className={`pin-button ${a.pinned ? 'on' : ''}`} onClick={() => onPin(a)}
                    aria-label={a.pinned ? '고정 해제' : '고정'} title={a.pinned ? '고정 해제' : '고정'}>
                    ★
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

// ── 사용자에게 전달 ──────────────────────────────────────────────────────────
function DeliverScreen({ releaseIds, onSubmit }: {
  releaseIds: string[];
  onSubmit: (f: { release_id: string; recipient: string; purpose: string }) => void;
}) {
  const [f, setF] = useState({ release_id: releaseIds[0] || '', recipient: '', purpose: '' });
  const step = !f.release_id ? 0 : !f.recipient ? 1 : !f.purpose.trim() ? 2 : 3;
  const ready = step === 3;
  const steps = ['앱 선택', '받는 사람', '전달 목적', '전달'];

  return (
    <>
      <ScreenHead kicker="DELIVER" title="사용자에게 전달"
        description="지정한 한 사람에게 앱을 전달합니다. 부서 공유·전사 승격과는 다른 경로입니다."
        chip={{ label: ready ? '보낼 준비 완료' : '입력 중', tone: ready ? 'success' : 'data' }} />

      <ol className="step-line">
        {steps.map((s, i) => (
          <li key={s} className={i < step ? 'done' : i === step ? 'active' : ''}>
            <i aria-hidden="true">{i < step ? '✓' : i + 1}</i>
            <div><b>{s}</b><small>{i < step ? '완료' : i === step ? '진행 중' : '대기'}</small></div>
          </li>
        ))}
      </ol>

      <div className="delivery-grid">
        <Panel kicker="RELEASE" title="전달할 앱" className="release-card">
          <div style={{ paddingTop: 14 }}>
            <label className="field-label" htmlFor="rel">릴리스</label>
            {releaseIds.length > 0 ? (
              <select id="rel" className="afs-select" value={f.release_id}
                onChange={(e) => setF({ ...f, release_id: e.target.value })}>
                <option value="">— 선택 —</option>
                {releaseIds.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            ) : (
              <input id="rel" className="afs-input" value={f.release_id} placeholder="release_id"
                onChange={(e) => setF({ ...f, release_id: e.target.value })} />
            )}
            {releaseIds.length === 0 && (
              <div className="empty-note" style={{ margin: '10px 0 0' }}>
                게시된 릴리스가 없습니다. 프로젝트를 완료해 릴리스를 게시하면 목록에 나타납니다.
              </div>
            )}
            <div className="release-facts">
              <div><span>전달 방식</span><b>개인</b><small>한 사람에게</small></div>
              <div><span>인증</span><b>상속</b><small>별도 로그인 없음</small></div>
              <div><span>권한 확대</span><b>없음</b><small>자료는 그대로</small></div>
            </div>
          </div>
        </Panel>

        <Panel kicker="RECIPIENT" title="받는 사람과 목적">
          <div style={{ padding: 18 }}>
            <label className="field-label" htmlFor="rcp">받는 사람 (사용자 ID)</label>
            <div className="search-field">
              <span aria-hidden="true">🔍</span>
              <input id="rcp" value={f.recipient} placeholder="예: hikwon@lsmnm.com"
                onChange={(e) => setF({ ...f, recipient: e.target.value })} />
            </div>

            <label className="field-label" htmlFor="pps">전달 목적 (필수)</label>
            <textarea id="pps" className="afs-textarea" value={f.purpose}
              placeholder="받는 사람이 수락 여부를 판단할 근거가 됩니다"
              onChange={(e) => setF({ ...f, purpose: e.target.value })} />

            <div className="permission-summary">
              <b>수락 시 상대에게 생기는 것</b>
              <span>내 앱 주머니에 앱 1개</span>
              <small>
                데이터 접근 범위는 변하지 않습니다. 상대가 원래 볼 수 없던 자료는 이 앱에서도
                보이지 않습니다 — 자료 권한이 필요하면 조직 권한을 별도로 부여해야 합니다.
              </small>
            </div>

            <button className="primary-wide" disabled={!ready} onClick={() => onSubmit(f)}>
              전달 요청 보내기
            </button>
          </div>
        </Panel>
      </div>
    </>
  );
}

// ── 보낸 요청 ────────────────────────────────────────────────────────────────
function SentScreen({ list, onRevoke }: {
  list: Delivery[]; onRevoke: (d: Delivery, reason: string) => void;
}) {
  const [form, setForm] = useState<{ id: string; reason: string } | null>(null);
  const accepted = list.filter((d) => d.status === 'ACCEPTED').length;
  return (
    <>
      <ScreenHead kicker="SENT" title="보낸 요청"
        description="내가 보낸 전달과 상대의 응답 상태입니다. 수락된 앱을 회수하면 상대 주머니에 회수 사실이 남습니다."
        chip={{ label: `수락 ${accepted} / 전체 ${list.length}`, tone: 'data' }} />
      <Panel kicker="OUTBOX" title="전달 이력">
        {list.length === 0 ? (
          <div className="empty-note">보낸 전달 요청이 없습니다.</div>
        ) : (
          <div className="sent-requests">
            {list.map((d) => (
              <div key={d.delivery_id}>
                <i className={DOT[d.status] || 'off'} aria-hidden="true" />
                <div>
                  <b>{d.release_id} → {d.recipient_user_id}</b>
                  <small>
                    {d.purpose}
                    {d.response_note ? ` · 응답: ${d.response_note}` : ''}
                  </small>
                  {form?.id === d.delivery_id && (
                    <div style={{ marginTop: 8 }}>
                      <label className="field-label" htmlFor={`rv-${d.delivery_id}`}>
                        회수 사유 (받는 사람에게 남습니다)
                      </label>
                      <textarea id={`rv-${d.delivery_id}`} className="afs-textarea" value={form.reason}
                        onChange={(e) => setForm({ ...form, reason: e.target.value })} />
                      <div style={{ display: 'flex', gap: 7, marginTop: 8 }}>
                        <button className="secondary-button" onClick={() => setForm(null)}>취소</button>
                        <button className="danger-ghost" disabled={!form.reason.trim()}
                          onClick={() => { onRevoke(d, form.reason.trim()); setForm(null); }}>
                          회수하기
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <StatusChip status={d.status} />
                  {d.can_revoke && form?.id !== d.delivery_id && (
                    <button className="text-button" onClick={() => setForm({ id: d.delivery_id, reason: '' })}>
                      회수
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}
