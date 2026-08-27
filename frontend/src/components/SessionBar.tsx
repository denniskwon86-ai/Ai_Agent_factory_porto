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

/**
 * ★ [2026-08-25] `openConsole` 를 **밖에서 열 수 있게** 했다.
 *
 * ⚠️ 승인 시안의 상단 셸에는 ⚙ 버튼이 셸 자체에 있다(`afs-icon-action`). 그런데 관리자
 *   콘솔은 이 컴포넌트가 자기 상태로 들고 있어서 셸이 열 방법이 없었다.
 * ★ 상태를 옮기지 않고 **문을 하나 낸다** — 여기 있는 이유(내 정보·로그아웃과 한 묶음)는
 *   그대로 두고, 셸이 부를 수 있게만 한다.
 */
export function SessionBar({ onGoToOrg, openConsole, onConsoleHandled }: {
  /** 밖(셸의 ⚙)에서 열라는 신호. ⚠️ 열고 나면 `onConsoleHandled` 로 되돌린다 —
   *  안 되돌리면 콘솔을 닫아도 다시 열린다. */
  openConsole?: boolean;
  onConsoleHandled?: () => void;
  /** ★ 관리자 콘솔의 「조직·권한 화면 열기」 — 여기까지 이어 준다.
   *  ⚠️ 콘솔이 스스로 열 수 없다. 어느 화면을 여는가는 App 이 쥔 상태다. */
  onGoToOrg: () => void;
}) {
  const [me, setMe] = useState<Me | null>(null);
  //: [설계 §5.8] 「**상단 사용자 영역의 `환경설정·관리자` 에서 진입**하며 일반 업무
  //  내비게이션과 혼합하지 않는다」 — 그래서 좌측 업무 레일이 아니라 여기서만 연다.
  const [console_, setConsole] = useState(false);
  useEffect(() => {
    if (openConsole) { setConsole(true); onConsoleHandled?.(); }
  }, [openConsole, onConsoleHandled]);

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
      <span className="afs-session-name afs-muted"
        title={me ? (me.display_name || me.user_id) : '사용자 확인 중'}
        style={{ fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden',
          textOverflow: 'ellipsis', maxWidth: 200 }}>
        {me ? (me.display_name || me.user_id) : '확인 중…'}
      </span>
      {/* ⚠️ [설계 §1.3 · §11 공통] 아래 칩은 11px 였다. 10~11px 는 **해시·ID·타임스탬프 같은
          기술 메타데이터에만** 허용된다 — 「초기 비밀번호를 쓰고 있다」는 사용자가 **행동해야
          하는 경고**이지 메타데이터가 아니다. 가장 작게 그려 놓고 바꾸라고 할 수는 없다.
          ⚠️ 이 주석을 `cond && (` **안쪽**에 두면 빌드가 깨진다 — 거기는 JSX 자식 자리가
            아니라 표현식 자리다(이번 세션에서 prop 자리에 이어 두 번째로 같은 실수를 했다). */}
      {me?.must_change_password && (
        <span className="state-chip warn" style={{ fontSize: 12 }}
          title="초기 비밀번호를 사용 중입니다 — 바꾸십시오.">초기 비밀번호</span>
      )}
      {/* ★★★ [2026-08-25] **⚙ 을 여기서 뺐다 — 셸에 이미 있다.**
          ⚠️⚠️ 실측: 상단 행동 칸에 ⚙ 이 **두 개**였다(셸 38px + 여기 131px). 같은 콘솔을
            여는 버튼이 나란히 둘 있으면 사용자는 둘이 다른 것이라고 읽는다. 그리고 그
            131px 이 전역 내비를 눌렀다.
          ★ 여는 방법은 그대로다 — 셸의 ⚙ 이 `openConsole` 로 이 컴포넌트를 부른다.
          ⚠️ [2026-08-23] 로그아웃은 **글자만 접고 아이콘을 남긴다**. 버튼 자체를 지우면
            로그아웃할 방법이 화면에서 사라진다 — 접는 것과 없애는 것은 다르다.
            `title`/`aria-label` 은 그대로라 무엇인지 계속 읽힌다. */}
      <button className="secondary-button" onClick={logout} aria-label="로그아웃"
        title="로그아웃" style={{ fontSize: 12, padding: '4px 8px' }}>
        ⏻
      </button>

      {console_ && <AdminConsolePanel me={me} onClose={() => setConsole(false)}
        onGoToOrg={() => { setConsole(false); onGoToOrg(); }} />}
    </div>
  );
}
