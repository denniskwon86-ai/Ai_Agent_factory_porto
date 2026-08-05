import { useEffect, useState } from 'react';
import { API_BASE_URL, getActingUser, setActingUser } from '../lib/api';

interface OrgUser {
  user_id: string; display_name: string;
  is_admin: boolean; is_executive: boolean; is_data_admin: boolean;
}
interface Scope {
  unrestricted: boolean; can_edit_org: boolean;
  can_run_enterprise: boolean; can_manage_standard: boolean;
  readable_dept_ids: string[];
  // [2026-07-30] 강제 여부·식별 상태. 강제를 켠 뒤 식별되지 않은 사용자는 목록이 전부 비는데,
  //   그 이유를 화면이 말하지 못하면 사용자는 "시스템이 고장났다"고 판단한다.
  org_enforced?: boolean; identified?: boolean; registered?: boolean;
  access_note?: string;
}

// 누구로 접속했는지 고르고 그 권한을 즉시 확인하는 위젯.
// ⚠️ 이건 인증이 아니라 **전환 도구**다. SSO 이행 전까지 권한 동작을 확인하기 위한 것이며,
//    실제 인증은 백엔드 미들웨어가 request.state.principal_user_id 를 채우는 형태가 최종이다.
//
// ★★★ [2026-08-04 이관 4/10] **통제가 로그인 경로를 막았다.**
//   사용자 명부에 자격 검사를 넣자(익명 403) 이 위젯이 `users.length === 0` 조건으로 스스로
//   사라졌다. 결과: 익명 사용자는 «우측 상단에서 사용자를 지정하십시오» 라는 안내를 읽지만
//   지정할 수단이 화면에 없다. 아무도 진입할 수 없는 상태였다.
//   → 목록을 못 받아도 **계정을 직접 입력**해 진입할 수 있게 한다. 형태가 실제 로그인과 같고,
//     명부를 노출하지 않는다. 목록은 «권한이 있을 때 편해지는 것»이지 진입 조건이 아니다.
export function UserSwitcher() {
  const [users, setUsers] = useState<OrgUser[]>([]);
  /** 명부를 **왜** 못 받았는가. `forbidden`(권한 없음)과 `empty`(조직 미도입)는 정반대다. */
  const [listState, setListState] = useState<'loading' | 'ok' | 'forbidden' | 'error'>('loading');
  const [cur, setCur] = useState(getActingUser());
  const [scope, setScope] = useState<Scope | null>(null);
  const [draft, setDraft] = useState('');

  const loadScope = async () => {
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/org/me`);
      setScope((await r.json())?.data || null);
    } catch { setScope(null); }
  };

  const loadUsers = async () => {
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/org/users`);
      if (r.status === 403 || r.status === 401) { setUsers([]); setListState('forbidden'); return; }
      if (!r.ok) { setUsers([]); setListState('error'); return; }
      setUsers((await r.json())?.data || []);
      setListState('ok');
    } catch { setUsers([]); setListState('error'); }
  };

  useEffect(() => { (async () => { await loadUsers(); await loadScope(); })(); }, []);

  const change = async (uid: string) => {
    setCur(uid);
    setActingUser(uid);
    await loadUsers();
    await loadScope();
    // SSE 는 ?as_user= 가 URL 에 박히므로 재연결이 필요하다. 목록도 권한에 따라 달라진다.
    window.dispatchEvent(new CustomEvent('factory:acting-user-changed', { detail: { userId: uid } }));
  };

  // 조직을 아직 도입하지 않은 상태(목록 조회는 됐고 0명)에서는 표시할 이유가 없다.
  // ⚠️ «권한이 없어서 0명»과 구분한다 — 그 경우에는 반드시 보여야 한다(진입 수단이므로).
  if (listState === 'ok' && users.length === 0) return null;
  if (listState === 'loading') return null;

  // ★★ [2026-07-30] 권한 강제가 켜졌는데 식별되지 않았다 = **목록이 전부 빈다.**
  //   그 상태를 조용히 두면 사용자는 자료가 없다고 믿는다 — 빈 화면의 이유를 화면이 말해야 한다.
  const blocked = !!scope?.org_enforced && (!scope?.identified || !scope?.registered);

  const badge =
    blocked ? { t: '접근 불가', c: 'text-red-300 bg-red-900/40 border-red-700/50' }
    : scope?.unrestricted ? { t: '무제한', c: 'text-emerald-300 bg-emerald-900/40 border-emerald-700/50' }
    : scope?.can_edit_org ? { t: '관리자', c: 'text-amber-300 bg-amber-900/40 border-amber-700/50' }
    : scope?.can_run_enterprise ? { t: '경영진', c: 'text-sky-300 bg-sky-900/40 border-sky-700/50' }
    : scope?.can_manage_standard ? { t: 'DA', c: 'text-violet-300 bg-violet-900/40 border-violet-700/50' }
    : { t: `${scope?.readable_dept_ids?.length ?? 0}개 부서`, c: 'text-gray-400 bg-gray-800 border-gray-700' };

  const submitDraft = () => {
    const v = draft.trim();
    if (v) change(v);
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5" title="이 사용자의 권한으로 화면과 API 응답이 결정됩니다">
        {/* 목록은 «있으면 편한 것»이다. 권한이 없어 못 받았으면 그 자리를 비워 두지 않고
            아래 입력으로 진입할 수 있게 한다. */}
        {users.length > 0 && (
          <select
            value={users.some((u) => u.user_id === cur) ? cur : ''}
            onChange={(e) => change(e.target.value)}
            aria-label="활동 사용자 선택"
            className={`text-xs bg-gray-900 border rounded px-2 py-1.5 text-gray-300 ${
              blocked ? 'border-red-700/60' : 'border-gray-700'
            }`}
          >
            <option value="">(익명)</option>
            {users.map((u) => (
              <option key={u.user_id} value={u.user_id}>{u.display_name}</option>
            ))}
          </select>
        )}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submitDraft(); }}
          placeholder={cur || '계정 입력 (예: hikwon@lsmnm.com)'}
          aria-label="활동 사용자 직접 입력"
          className={`text-xs bg-gray-900 border rounded px-2 py-1.5 text-gray-300 w-52 ${
            blocked ? 'border-red-700/60' : 'border-gray-700'
          }`}
        />
        <button type="button" onClick={submitDraft} disabled={!draft.trim()}
          className="text-xs px-2 py-1.5 rounded border border-gray-700 bg-gray-800
                     text-gray-300 hover:bg-gray-700 disabled:opacity-40">
          전환
        </button>
        {cur && (
          <button type="button" onClick={() => change('')}
            title="익명으로 돌아갑니다"
            className="text-xs px-2 py-1.5 rounded border border-gray-700 bg-gray-900
                       text-gray-400 hover:bg-gray-800">
            익명
          </button>
        )}
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.c}`}>{badge.t}</span>
      </div>
      {listState === 'forbidden' && (
        <div className="max-w-[420px] text-[10px] leading-snug text-gray-400 bg-gray-900
                        border border-gray-700 rounded px-2 py-1">
          사용자 명부는 권한이 있는 계정에만 보입니다 — 계정을 직접 입력해 진입하십시오.
        </div>
      )}
      {blocked && scope?.access_note && (
        // 빈 목록의 **이유**와 **다음 행동**을 함께 준다. 이유 없는 빈 화면은 고장으로 읽힌다.
        <div className="max-w-[420px] text-[10px] leading-snug text-red-200 bg-red-950/40
                        border border-red-800/50 rounded px-2 py-1"
             title={scope.access_note}>
          {scope.access_note.replace(/\*\*/g, '')}
        </div>
      )}
    </div>
  );
}
