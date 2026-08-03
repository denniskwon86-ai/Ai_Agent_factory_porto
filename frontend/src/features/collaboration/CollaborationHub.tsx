// [CL-1] 협업 허브 — 사용자에게 전달 · 받은 앱 · 내 앱
//
// ★ 작업서 §CL-FE-01: AppShell/Router 전환이 끝나지 않았으므로 **오버레이 boolean 4개를 만들지
//   않는다.** 하나의 `CollaborationHub` 안에서 내부 view 상태를 관리하고, 정식 Router 병합 시
//   `view`/`onChangeView` 를 URL adapter 로 바꾸면 이 파일 안쪽은 그대로 남는다.
//
// ★ 화면이 반드시 보여줘야 하는 두 가지(서버가 문구까지 준다 — 화면이 지어내지 않는다):
//   ① 수락 후 "데이터 접근 범위는 넓어지지 않았습니다" — 없으면 사용자는 앱을 받으면 자료도
//      보인다고 믿는다.
//   ② 401 과 404 의 구분 — "사용자를 지정하십시오"와 "그 요청은 없습니다"는 다른 행동을 요구한다.
import { useCallback, useEffect, useState } from 'react';

import {
  collaborationApi, DELIVERY_STATUS_KO, type CapabilityManifest, type Delivery, type PocketApp,
} from '../../lib/collaborationApi';

type View = 'inbox' | 'apps' | 'deliver' | 'sent';

const VIEWS: { id: View; label: string; hint: string }[] = [
  { id: 'inbox', label: '받은 앱', hint: '나에게 전달된 앱 요청' },
  { id: 'apps', label: '내 앱', hint: '수락해서 쓰고 있는 앱' },
  { id: 'deliver', label: '사용자에게 전달', hint: '릴리스를 지정한 사람에게 전달' },
  { id: 'sent', label: '보낸 요청', hint: '내가 보낸 전달과 응답 상태' },
];

const TONE: Record<string, string> = {
  amber: 'bg-amber-900/30 text-amber-300 border-amber-700/40',
  emerald: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/40',
  gray: 'bg-gray-800/60 text-gray-400 border-gray-700',
  slate: 'bg-slate-800/60 text-slate-400 border-slate-600',
  red: 'bg-red-900/30 text-red-300 border-red-700/40',
};

function StatusBadge({ status }: { status: Delivery['status'] }) {
  const s = DELIVERY_STATUS_KO[status] ?? { label: status, tone: 'gray' };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${TONE[s.tone]}`}>
      {s.label}
    </span>
  );
}

/** 앱이 요구하는 권한을 보여준다. **비어 있으면 "요구 없음"이라고 말한다** — 빈 카드를 두면
 *  사용자는 화면이 덜 만들어진 것으로 읽고 그냥 수락한다. */
function CapabilityManifestCard({ m }: { m: CapabilityManifest }) {
  const caps = m?.required_capabilities?.length
    ? m.required_capabilities
    : (m?.capabilities || []).map((c) => {
      const i = c.lastIndexOf('.');
      return i > 0 ? { resource: c.slice(0, i), actions: [c.slice(i + 1)] }
        : { resource: c, actions: [] as string[] };
    });
  return (
    <div className="mt-2 rounded-lg border border-[#2F3640] bg-[#0B0C10]/60 p-2.5 text-xs">
      <div className="text-gray-400 mb-1.5">이 앱이 요구하는 것</div>
      {caps.length === 0 ? (
        <div className="text-gray-500">요구하는 데이터 권한이 없습니다.</div>
      ) : (
        <ul className="space-y-1">
          {caps.map((c) => (
            <li key={c.resource} className="text-gray-300">
              <span className="font-mono text-cyan-300">{c.resource}</span>
              {c.actions.length > 0 && (
                <span className="text-gray-500"> · {c.actions.join(', ')}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {/* 플랫폼 인증 상속을 화면에 드러낸다 — 사용자가 "이 앱이 따로 로그인을 요구하지 않는다"를
          알아야 자체 로그인 화면을 만난 순간 이상하다고 신고할 수 있다. */}
      <div className="mt-2 pt-2 border-t border-[#1F2833] text-[11px] text-gray-500">
        인증: {m?.auth_mode === 'PLATFORM_INHERITED' ? '플랫폼 상속(별도 로그인 없음)' : (m?.auth_mode || '미지정')}
        {m?.standalone_auth === false && ' · 자체 인증 없음'}
      </div>
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

  // 전달 폼 초안 — Draft 상태만 여기 둔다(§CL-FE-03).
  const [form, setForm] = useState({ release_id: releaseIds[0] || '', recipient: '', purpose: '' });

  const load = useCallback(async () => {
    setBusy('불러오는 중...'); setErr(null);
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
  //   사용자의 목록이 화면에 그대로 남아 있고, 그것이 곧 유출이다.
  useEffect(() => {
    const h = () => { setInbox([]); setSent([]); setApps([]); load(); };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [load]);

  const act = async (label: string, fn: () => Promise<any>) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      const r = await fn();
      // 서버가 준 문구를 그대로 보여준다 — 화면이 지어내면 서버 규칙과 갈라진다.
      if (r?.scope_note) setFlash(r.scope_note);
      else if (r?.note) setFlash(r.note);
      await load();
    } catch (e: any) {
      setErr({ msg: e?.message || String(e), status: e?.status });
    } finally { setBusy(null); }
  };

  const pending = inbox.filter((d) => d.status === 'PENDING');

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-6xl h-[88vh] bg-[#0B0C10] border border-[#1F2833] rounded-xl flex flex-col overflow-hidden">
        <header className="flex items-center gap-3 px-5 py-3 border-b border-[#1F2833]">
          <h2 className="text-base font-semibold text-white">🤝 협업</h2>
          <span className="text-xs text-gray-500">
            앱 전달 · 수락 · 내 앱 — 개인 전달은 조직 공유·전사 승격과 별개입니다
          </span>
          <div className="ml-auto flex items-center gap-2">
            {busy && <span className="text-xs text-cyan-300">{busy}</span>}
            <button onClick={onClose}
              className="text-xs px-2 py-1 rounded border border-[#2F3640] text-gray-400 hover:text-white">
              닫기
            </button>
          </div>
        </header>

        <div className="flex-1 flex min-h-0">
          {/* 238px Rail (승인 UI 구성) */}
          <nav className="w-[238px] shrink-0 border-r border-[#1F2833] p-3 space-y-1 overflow-y-auto">
            {VIEWS.map((v) => (
              <button key={v.id} onClick={() => setView(v.id)}
                className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                  view === v.id
                    ? 'bg-[#1F2833] border-cyan-700/50 text-white'
                    : 'bg-transparent border-transparent text-gray-400 hover:bg-[#141a21]'}`}>
                <div className="text-sm flex items-center gap-2">
                  {v.label}
                  {v.id === 'inbox' && pending.length > 0 && (
                    <span className="text-[10px] px-1.5 rounded-full bg-amber-900/50 text-amber-300 border border-amber-700/40">
                      {pending.length}
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-gray-600 mt-0.5">{v.hint}</div>
              </button>
            ))}
          </nav>

          {/* 가변 작업면 */}
          <section className="flex-1 min-w-0 overflow-y-auto p-5">
            {err && (
              <div className="mb-3 rounded-lg border border-red-800/50 bg-red-900/20 p-3 text-xs text-red-300">
                {/* 401 과 404 는 사용자가 해야 할 일이 다르다 — 문구를 뭉개지 않는다. */}
                <b>{err.status === 401 ? '사용자 지정이 필요합니다' : err.status === 404 ? '요청을 찾을 수 없습니다' : '오류'}</b>
                <div className="mt-1 text-red-200/80">{err.msg}</div>
              </div>
            )}
            {flash && (
              <div className="mb-3 rounded-lg border border-cyan-800/50 bg-cyan-900/20 p-3 text-xs text-cyan-200">
                {flash}
              </div>
            )}

            {view === 'inbox' && (
              <Inbox list={inbox} onAccept={(d) => act('수락 중...', () => collaborationApi.accept(d.delivery_id))}
                onReject={(d, n) => act('거절 중...', () => collaborationApi.reject(d.delivery_id, n))}
                onReassign={(d, n) => act('재배정 요청 중...', () => collaborationApi.reassign(d.delivery_id, n))} />
            )}
            {view === 'apps' && (
              <MyApps list={apps}
                onPin={(a) => act('갱신 중...', () => collaborationApi.patchApp(a.pocket_id, { pinned: !a.pinned }))}
                onRename={(a, name) => act('이름 변경 중...', () => collaborationApi.patchApp(a.pocket_id, { display_name: name }))} />
            )}
            {view === 'deliver' && (
              <DeliverForm form={form} setForm={setForm} releaseIds={releaseIds}
                onSubmit={() => act('전달 중...', async () => {
                  const r = await collaborationApi.create({
                    release_id: form.release_id.trim(),
                    recipient_user_id: form.recipient.trim(),
                    purpose: form.purpose.trim(),
                    // 중복 클릭에도 하나만 생기게 — 서버가 같은 키를 재생(replay)한다.
                    idempotency_key: `${form.release_id}|${form.recipient}|${form.purpose}`.slice(0, 120),
                  });
                  setView('sent');
                  return r;
                })} />
            )}
            {view === 'sent' && (
              <Sent list={sent}
                onRevoke={(d, r) => act('회수 중...', () => collaborationApi.revoke(d.delivery_id, r))} />
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-xs text-gray-500 border border-[#2F3640] rounded-xl p-4">{children}</div>;
}

function Inbox({ list, onAccept, onReject, onReassign }: {
  list: Delivery[];
  onAccept: (d: Delivery) => void;
  onReject: (d: Delivery, note: string) => void;
  onReassign: (d: Delivery, note: string) => void;
}) {
  if (list.length === 0) {
    return <Empty>받은 앱 요청이 없습니다. 다른 사용자가 앱을 전달하면 여기에 나타납니다.</Empty>;
  }
  return (
    <ul className="space-y-3">
      {list.map((d) => (
        <li key={d.delivery_id} className="rounded-xl border border-[#2F3640] bg-[#141a21]/60 p-3.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white font-medium">{d.release_id}</span>
            <span className="text-[10px] text-gray-600 font-mono">{d.release_version}</span>
            <StatusBadge status={d.status} />
            <span className="ml-auto text-[11px] text-gray-500">
              보낸 사람 <b className="text-gray-300">{d.sender_user_id}</b>
            </span>
          </div>
          <div className="mt-1.5 text-xs text-gray-300">{d.purpose}</div>
          <div className="text-[11px] text-gray-600 mt-1">
            만료 {d.expires_at}
            {d.note && <span className="text-amber-400 ml-2">{d.note}</span>}
          </div>
          <CapabilityManifestCard m={d.manifest_snapshot} />
          {d.can_respond ? (
            <div className="mt-2.5 flex flex-wrap gap-2">
              <button onClick={() => onAccept(d)}
                className="text-xs px-3 py-1.5 rounded-lg bg-emerald-900/40 border border-emerald-700/50 text-emerald-200 hover:bg-emerald-900/60">
                수락하고 내 앱에 추가
              </button>
              <button onClick={() => {
                const n = prompt('거절 사유 (보낸 사람이 다시 판단할 근거가 됩니다)') || '';
                if (n.trim()) onReject(d, n);
              }}
                className="text-xs px-3 py-1.5 rounded-lg border border-[#2F3640] text-gray-300 hover:bg-[#1F2833]">
                거절
              </button>
              <button onClick={() => {
                const n = prompt('담당자가 아니라면 누가 담당인지 알려주십시오') || '';
                if (n.trim()) onReassign(d, n);
              }}
                className="text-xs px-3 py-1.5 rounded-lg border border-[#2F3640] text-gray-400 hover:bg-[#1F2833]">
                담당 아님 · 재배정 요청
              </button>
            </div>
          ) : (
            <div className="mt-2.5 text-[11px] text-gray-500">
              {d.responded_at ? `${d.responded_at.slice(0, 10)} 응답` : '응답할 수 없는 상태입니다'}
              {d.response_note && ` · ${d.response_note}`}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function MyApps({ list, onPin, onRename }: {
  list: PocketApp[]; onPin: (a: PocketApp) => void; onRename: (a: PocketApp, n: string) => void;
}) {
  if (list.length === 0) {
    return <Empty>수락한 앱이 없습니다. <b className="text-gray-300">받은 앱</b>에서 수락하면 여기에 담깁니다.</Empty>;
  }
  return (
    <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {list.map((a) => (
        <li key={a.pocket_id} className="rounded-xl border border-[#2F3640] bg-[#141a21]/60 p-3.5">
          <div className="flex items-center gap-2">
            <button onClick={() => onPin(a)} title={a.pinned ? '고정 해제' : '고정'}
              className={`text-sm ${a.pinned ? 'text-amber-300' : 'text-gray-600 hover:text-gray-300'}`}>
              ★
            </button>
            <span className="text-sm text-white">{a.display_name}</span>
            <button onClick={() => {
              const n = prompt('표시 이름', a.display_name) || '';
              if (n.trim() && n !== a.display_name) onRename(a, n);
            }} className="text-[10px] text-gray-600 hover:text-gray-300">이름 변경</button>
          </div>
          <div className="mt-1.5 text-[11px] text-gray-600 font-mono">{a.release_id}</div>
          <div className="text-[11px] text-gray-500 mt-1">
            {a.accepted_at ? `${a.accepted_at.slice(0, 10)} 수락` : ''}
          </div>
        </li>
      ))}
    </ul>
  );
}

function DeliverForm({ form, setForm, releaseIds, onSubmit }: {
  form: { release_id: string; recipient: string; purpose: string };
  setForm: (f: any) => void;
  releaseIds: string[];
  onSubmit: () => void;
}) {
  const ready = form.release_id.trim() && form.recipient.trim() && form.purpose.trim();
  return (
    <div className="max-w-2xl space-y-3">
      <div className="text-xs text-gray-500">
        지정한 <b className="text-gray-300">한 사람</b>에게 앱을 전달합니다. 부서 공유·전사 승격과는
        다른 경로이며, <b className="text-gray-300">수락해도 상대의 데이터 권한은 넓어지지 않습니다.</b>
      </div>
      <label className="block">
        <span className="text-xs text-gray-400">릴리스</span>
        {releaseIds.length > 0 ? (
          <select value={form.release_id} onChange={(e) => setForm({ ...form, release_id: e.target.value })}
            className="mt-1 w-full text-sm bg-[#141a21] border border-[#2F3640] rounded-lg px-3 py-2 text-gray-200">
            <option value="">— 선택 —</option>
            {releaseIds.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        ) : (
          <input value={form.release_id} onChange={(e) => setForm({ ...form, release_id: e.target.value })}
            placeholder="release_id" className="mt-1 w-full text-sm bg-[#141a21] border border-[#2F3640] rounded-lg px-3 py-2 text-gray-200" />
        )}
      </label>
      <label className="block">
        <span className="text-xs text-gray-400">받는 사람 (사용자 ID)</span>
        <input value={form.recipient} onChange={(e) => setForm({ ...form, recipient: e.target.value })}
          placeholder="예: hikwon@lsmnm.com"
          className="mt-1 w-full text-sm bg-[#141a21] border border-[#2F3640] rounded-lg px-3 py-2 text-gray-200" />
      </label>
      <label className="block">
        <span className="text-xs text-gray-400">전달 목적 (필수)</span>
        <textarea value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}
          rows={3} placeholder="받는 사람이 수락 여부를 판단할 근거가 됩니다"
          className="mt-1 w-full text-sm bg-[#141a21] border border-[#2F3640] rounded-lg px-3 py-2 text-gray-200" />
      </label>
      <button disabled={!ready} onClick={onSubmit}
        className={`text-sm px-4 py-2 rounded-lg border ${ready
          ? 'bg-cyan-900/40 border-cyan-700/50 text-cyan-200 hover:bg-cyan-900/60'
          : 'border-[#2F3640] text-gray-600 cursor-not-allowed'}`}>
        전달 요청 보내기
      </button>
    </div>
  );
}

function Sent({ list, onRevoke }: { list: Delivery[]; onRevoke: (d: Delivery, r: string) => void }) {
  if (list.length === 0) return <Empty>보낸 전달 요청이 없습니다.</Empty>;
  return (
    <ul className="space-y-2.5">
      {list.map((d) => (
        <li key={d.delivery_id} className="rounded-xl border border-[#2F3640] bg-[#141a21]/60 p-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white">{d.release_id}</span>
            <StatusBadge status={d.status} />
            <span className="text-[11px] text-gray-500">
              받는 사람 <b className="text-gray-300">{d.recipient_user_id}</b>
            </span>
            {d.can_revoke && (
              <button onClick={() => {
                const r = prompt('회수 사유 (받는 사람에게 남습니다)') || '';
                if (r.trim()) onRevoke(d, r);
              }} className="ml-auto text-[11px] px-2 py-1 rounded border border-red-800/50 text-red-300 hover:bg-red-900/30">
                회수
              </button>
            )}
          </div>
          <div className="mt-1 text-xs text-gray-400">{d.purpose}</div>
          {d.response_note && (
            <div className="mt-1 text-[11px] text-amber-300">응답: {d.response_note}</div>
          )}
        </li>
      ))}
    </ul>
  );
}
