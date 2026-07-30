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
export function UserSwitcher() {
  const [users, setUsers] = useState<OrgUser[]>([]);
  const [cur, setCur] = useState(getActingUser());
  const [scope, setScope] = useState<Scope | null>(null);

  const loadScope = async () => {
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/org/me`);
      setScope((await r.json())?.data || null);
    } catch { setScope(null); }
  };

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API_BASE_URL}/api/v1/org/users`);
        setUsers((await r.json())?.data || []);
      } catch { setUsers([]); }
      await loadScope();
    })();
  }, []);

  const change = async (uid: string) => {
    setCur(uid);
    setActingUser(uid);
    await loadScope();
    // SSE 는 ?as_user= 가 URL 에 박히므로 재연결이 필요하다. 목록도 권한에 따라 달라진다.
    window.dispatchEvent(new CustomEvent('factory:acting-user-changed', { detail: { userId: uid } }));
  };

  if (users.length === 0) return null;   // 조직 미도입이면 표시할 이유가 없다

  // ★★ [2026-07-30] 권한 강제가 켜졌는데 식별되지 않았다 = **목록이 전부 빈다.**
  //   그 상태를 조용히 두면 사용자는 자료가 없다고 믿는다 — 빈 화면의 이유를 화면이 말해야 한다.
  const blocked = !!scope?.org_enforced && (!scope?.identified || !scope?.registered);

  const badge =
    blocked ? { t: '접근 불가', c: 'text-red-300 bg-red-900/40 border-red-700/50' }
    : scope?.unrestricted ? { t: '무제한', c: 'text-emerald-300 bg-emerald-900/40 border-emerald-700/50' }
    : scope?.can_edit_org ? { t: '관리자', c: 'text-amber-300 bg-amber-900/40 border-amber-700/50' }
    : scope?.can_run_enterprise ? { t: '경영진', c: 'text-sky-300 bg-sky-900/40 border-sky-700/50' }
    : scope?.can_manage_standard ? { t: 'DA', c: 'text-violet-300 bg-violet-900/40 border-violet-700/50' }
    : { t: `${scope?.readable_dept_ids?.length ?? 0}개 부서`, c: 'text-gray-400 bg-[#1F2833] border-[#1F2833]' };

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5" title="이 사용자의 권한으로 화면과 API 응답이 결정됩니다">
        <select
          value={cur}
          onChange={(e) => change(e.target.value)}
          className={`text-xs bg-[#141a21] border rounded px-2 py-1.5 text-gray-300 ${
            blocked ? 'border-red-700/60' : 'border-[#1F2833]'
          }`}
        >
          <option value="">(익명)</option>
          {users.map((u) => (
            <option key={u.user_id} value={u.user_id}>{u.display_name}</option>
          ))}
        </select>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.c}`}>{badge.t}</span>
      </div>
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
