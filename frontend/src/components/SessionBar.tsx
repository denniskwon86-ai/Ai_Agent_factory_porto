// [2026-08-09] 지금 누구인가 + 로그아웃. **계정 전환기를 대신한다.**
//
// ## 왜 전환기를 없앴나
//
// 종전 `UserSwitcher` 는 SSO 가 붙기 전 임시 장치였다(2026-07-30 Phase 2). 화면 최상단에서
// **아무 계정이나 골라 그 권한으로** 볼 수 있었고, `api/deps.py` 가 「②③ 은 인증이 아니다」
// 라고 못박아 둔 그 상태가 제품 화면에 그대로 남아 있었다.
//
// 이제 로그인이 식별의 정본이므로, 이 자리는 **바꾸는 곳이 아니라 확인하는 곳**이다.
// ⚠️ 권한 배지를 여기 늘어놓지 않는다 — 「내가 무엇을 할 수 있는가」는 각 화면이 행동 단위로
//   답하고(§8.6), 상단 배지는 그것과 어긋나기 시작하면 사용자를 헷갈리게 한다.
import { useEffect, useState } from 'react';

import { API_BASE_URL, getSessionToken, setActingUser, setSessionToken } from '../lib/api';

import { AdminConsolePanel } from './AdminConsolePanel';

type Me = {
  user_id: string; display_name: string; must_change_password?: boolean;
  is_admin?: boolean; is_data_admin?: boolean;
};

export function SessionBar() {
  const [me, setMe] = useState<Me | null>(null);
  //: [설계 §5.8] 「**상단 사용자 영역의 `환경설정·관리자` 에서 진입**하며 일반 업무
  //  내비게이션과 혼합하지 않는다」 — 그래서 좌측 업무 레일이 아니라 여기서만 연다.
  const [console_, setConsole] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE_URL}/api/v1/auth/me`, {
      headers: { 'X-Session-Token': getSessionToken() },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (alive && j?.data) setMe(j.data as Me); })
      .catch(() => { /* 표시용이다 — 실패해도 앱을 막지 않는다 */ });
    return () => { alive = false; };
  }, []);

  const logout = async () => {
    try {
      await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
        method: 'POST', headers: { 'X-Session-Token': getSessionToken() },
      });
    } catch { /* 서버가 못 받아도 이쪽 세션은 버린다 */ }
    setSessionToken('');
    setActingUser('');
    window.location.reload();
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
      <span className="afs-muted" style={{ fontSize: 12, whiteSpace: 'nowrap',
        overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 200 }}>
        {me ? (me.display_name || me.user_id) : '확인 중…'}
      </span>
      {me?.must_change_password && (
        <span className="state-chip warn" style={{ fontSize: 11 }}
          title="초기 비밀번호를 사용 중입니다 — 바꾸십시오.">초기 비밀번호</span>
      )}
      <button className="secondary-button" onClick={() => setConsole(true)}
        style={{ fontSize: 12, padding: '4px 10px' }}
        title="개인 설정과 전사 관리 — 업무 화면과 분리되어 있습니다">환경설정 · 관리자</button>
      <button className="secondary-button" onClick={logout}
        style={{ fontSize: 12, padding: '4px 10px' }}>로그아웃</button>

      {console_ && <AdminConsolePanel me={me} onClose={() => setConsole(false)} />}
    </div>
  );
}
