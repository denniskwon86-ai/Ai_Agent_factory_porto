// [2026-08-09] 로그인 — **제품에 들어오는 유일한 문.**
//
// ## 왜 생겼나
//
// 종전에는 문이 없었다. 앱을 열면 기본값 `admin` 으로 들어와졌고, 화면 최상단의 계정
// 전환기로 아무 계정이나 골라 그 권한으로 볼 수 있었다. `api/deps.py` 가 「②③ 은 인증이
// 아니다」라고 못박아 둔 임시 장치가 제품 화면에 그대로 남아 있던 것이다.
//
// ## 이 화면이 지키는 것
//
// ① **신규 가입이 없다.** 계정은 관리자가 만든다 — 가입 경로를 열면 조직도에 없는 사용자가
//    생기고, 그러면 범위·권한 판정이 전부 «모르는 사람» 으로 떨어진다.
// ② **실패 사유를 «아이디가 없다/비밀번호가 틀렸다» 로 나누지 않는다.** 나누면 그 응답으로
//    계정 목록을 만들어 낼 수 있다. 서버가 이미 한 문장으로 답하고, 화면은 그것을 그대로 쓴다.
// ③ **초기 비밀번호를 쓰는 계정에는 바꾸라고 말한다.** 알리지 않으면 「전 계정 공통 비밀번호」가
//    그대로 운영에 들어간다.
import { useEffect, useRef, useState } from 'react';

import { Banner } from '../design/HubShell';
import { API_BASE_URL, setActingUser, setSessionToken } from '../lib/api';
import '../design/afs.css';
import { PRODUCT_NAME } from '../lib/brand';

export type LoginResult = {
  user_id: string;
  display_name: string;
  must_change_password: boolean;
};

export function LoginPage({ onLoggedIn }: { onLoggedIn: (r: LoginResult) => void }) {
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const idRef = useRef<HTMLInputElement>(null);

  useEffect(() => { idRef.current?.focus(); }, []);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!userId.trim() || !password) {
      setErr('아이디와 비밀번호를 입력하십시오.');
      return;
    }
    setBusy(true); setErr('');
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId.trim(), password }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        // 서버 문구를 그대로 — 화면이 요약하면 무엇을 해야 할지가 사라진다.
        setErr(String(j?.detail || '로그인하지 못했습니다.'));
        return;
      }
      const d = j?.data || {};
      setSessionToken(String(d.token || ''));
      //: 하위호환 — 토큰을 못 읽는 옛 경로가 아직 있다. 서버는 토큰을 우선한다.
      setActingUser(String(d.user_id || ''));
      onLoggedIn({
        user_id: String(d.user_id || ''),
        display_name: String(d.display_name || d.user_id || ''),
        must_change_password: Boolean(d.must_change_password),
      });
    } catch {
      // ⚠️ 「서버가 죽었다」와 「비밀번호가 틀렸다」는 다르다 — 사용자가 할 일이 다르다.
      setErr('서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하십시오.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="afs-scope afs-page"
      style={{ minHeight: '100dvh', width: '100%', display: 'grid', placeItems: 'center', padding: 24 }}>
      <form onSubmit={submit}
        aria-label="LAXS 로그인"
        style={{
          width: 'min(440px, 100%)', display: 'flex', flexDirection: 'column', gap: 16,
          padding: '32px 34px', border: '1px solid var(--surface-border)', borderRadius: 12,
          background: 'var(--surface-card)', boxShadow: 'var(--surface-shadow)',
        }}>
        <div style={{ textAlign: 'center', marginBottom: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
            minHeight: 60 }}>
            <img src="/brand/laxs-logo-primary-on-white-v5.png" alt={PRODUCT_NAME}
              style={{ display: 'block', width: 286, maxWidth: '86%', height: 'auto' }} />
          </div>
          <p className="afs-muted" style={{ fontSize: 14, lineHeight: 1.55, margin: '8px 0 0' }}>
            현업의 실행과 경영의 판단을 AX로 연결합니다.<br />
            회사 계정으로 로그인하십시오.
          </p>
        </div>

        {err && <Banner tone="error" title="로그인하지 못했습니다">{err}</Banner>}

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="field-label">아이디</span>
          <input ref={idRef} className="afs-input" value={userId} autoComplete="username"
            onChange={(e) => setUserId(e.target.value)}
            placeholder="예: name@company.com" />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="field-label">비밀번호</span>
          <input className="afs-input" type="password" value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)} />
        </label>

        <button className="primary-button" type="submit" disabled={busy}
          style={{ marginTop: 4, minHeight: 44, padding: '10px 0', fontSize: 15 }}>
          {busy ? '확인 중…' : '로그인'}
        </button>

        {/* ⚠️ 가입 링크를 두지 않는다 — 계정은 관리자가 만든다. 링크만 있고 동작하지 않으면
            사용자는 자기 계정이 없는 이유를 여기서 찾다가 시간을 버린다. */}
        <p className="afs-muted" style={{ fontSize: 12, textAlign: 'center', margin: 0 }}>
          계정은 관리자가 만듭니다. 접속이 안 되면 시스템 관리자에게 문의하십시오.
        </p>
      </form>
    </div>
  );
}
