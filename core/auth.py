"""로그인·세션 — **사용자가 «누구인지» 를 스스로 증명하는 유일한 지점.**

## 왜 필요한가

지금까지 식별은 `X-Factory-User` 헤더였다. 그것은 **브라우저가 임의 값을 보낼 수 있는** 값이고
(`api/deps.py` 머리말이 「②③ 은 인증이 아니다」라고 못박아 두었다), 화면 최상단의 계정
전환기로 아무나 관리자로 갈아탈 수 있었다. SSO 가 붙기 전까지의 임시 장치였는데 그 임시가
제품 화면에 그대로 남아 있었다.

→ 이 모듈이 그 자리를 대신한다. 로그인하면 **세션 토큰**이 나오고, `api/deps` 의 SSO 슬롯
  (`request.state.principal_user_id`)에 그 결과가 실린다. 그 슬롯은 설계가 처음부터 비워 둔
  자리이므로 **기존 라우트를 하나도 고치지 않는다.**

## ⚠️ 지금은 «개발 단계 인증» 이다 — 숨기지 않는다

· 초기 비밀번호는 **전 계정 공통**(`DEFAULT_PASSWORD`)이다. 사용자 지시(2026-08-09)이며
  「실제 돌아가는 것을 먼저 보고 보안은 테스트하며 잡는다」는 방침에 따른 것이다.
· 그래서 **비밀번호를 평문으로 저장하지 않는다.** 지금 편하자고 평문을 쓰면 나중에 정책을
  올릴 때 저장분을 전부 버려야 하고, 그 사이 유출되면 되돌릴 수 없다. 해시는 지금 넣는 것이
  가장 싸다(`pbkdf2_hmac`, 표준 라이브러리).
· 세션은 서버가 들고 있다(DB). 토큰 자체에 권한을 싣지 않는다 — 권한은 매 요청 `org_directory`
  에서 다시 해석한다. 토큰에 권한을 담으면 **권한을 회수해도 토큰이 살아 있는 동안 유효**하다.

⬜ SSO 를 붙일 때: `verify()` 를 SSO 검증으로 바꾸고 이 파일의 나머지는 그대로 둔다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.paths import data_path

_DB_PATH = data_path("auth.db")

#: ★ 전 계정 공통 초기 비밀번호(사용자 지시 2026-08-09). 계정마다 저장된 해시가 없으면 이 값과
#:   대조한다 — 21개 계정에 미리 행을 만들어 둘 필요가 없고, 나중에 각자 바꾸면 그때부터
#:   저장분이 우선한다.
#:   ⚠️ 운영 전에 반드시 바꿔야 하는 값이다. 그 사실을 코드에 남겨 두어야 «임시» 가 «영구» 가
#:     되지 않는다(이 저장소가 한시 예외에서 배운 것과 같은 이유).
DEFAULT_PASSWORD = "pass:"

#: 세션 수명. 짧으면 작업 중 튕기고, 길면 자리를 비운 화면이 계속 열려 있다.
SESSION_HOURS = 12

_ITERATIONS = 120_000

_DDL = """
CREATE TABLE IF NOT EXISTS auth_credential (
    user_id     TEXT PRIMARY KEY,
    salt        TEXT NOT NULL,
    hash        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_session (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_user ON auth_session(user_id);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt), _ITERATIONS).hex()


class AuthStore:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ready = ""

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        if self._ready == self.db_path:
            return
        with self._lock, self._connect() as conn:
            conn.executescript(_DDL)
            conn.commit()
        self._ready = self.db_path

    # ── 비밀번호 ──────────────────────────────────────────────────────────
    def set_password(self, user_id: str, password: str) -> None:
        """비밀번호를 **해시로** 저장한다. 평문은 어디에도 남기지 않는다."""
        uid = (user_id or "").strip()
        if not uid:
            raise ValueError("user_id 가 필요합니다.")
        if not password:
            raise ValueError("비밀번호가 비어 있습니다.")
        salt = secrets.token_bytes(16).hex()
        self._init()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_credential (user_id, salt, hash, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET salt=excluded.salt, hash=excluded.hash, "
                "updated_at=excluded.updated_at",
                (uid, salt, _digest(password, salt), _iso(_now())))
            conn.commit()

    def verify(self, user_id: str, password: str) -> bool:
        """비밀번호가 맞는가.

        ★ 저장된 해시가 없으면 **초기 공통 비밀번호**와 대조한다. 21개 계정에 미리 행을 만들지
          않아도 되고, 사용자가 바꾸는 순간부터 저장분이 우선한다.
        ⚠️ 비교는 `hmac.compare_digest` 로 한다 — 문자열 `==` 는 앞자리부터 다른 시점에 끝나므로
          응답 시간으로 정답 길이를 짐작할 여지를 준다."""
        uid = (user_id or "").strip()
        if not uid or not password:
            return False
        self._init()
        with self._connect() as conn:
            r = conn.execute("SELECT salt, hash FROM auth_credential WHERE user_id=?",
                             (uid,)).fetchone()
        if r is None:
            return hmac.compare_digest(password, DEFAULT_PASSWORD)
        return hmac.compare_digest(_digest(password, r["salt"]), r["hash"])

    def uses_default_password(self, user_id: str) -> bool:
        """아직 초기 비밀번호를 쓰는가 — 관리자 화면이 «바꿔야 할 계정» 을 셀 수 있게."""
        self._init()
        with self._connect() as conn:
            r = conn.execute("SELECT 1 FROM auth_credential WHERE user_id=?",
                             ((user_id or "").strip(),)).fetchone()
        return r is None

    # ── 세션 ──────────────────────────────────────────────────────────────
    def create_session(self, user_id: str) -> Dict[str, Any]:
        uid = (user_id or "").strip()
        token = secrets.token_urlsafe(32)
        now = _now()
        exp = now + timedelta(hours=SESSION_HOURS)
        self._init()
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO auth_session (token, user_id, created_at, expires_at) "
                         "VALUES (?,?,?,?)", (token, uid, _iso(now), _iso(exp)))
            conn.commit()
        return {"token": token, "user_id": uid, "expires_at": _iso(exp)}

    def resolve(self, token: str) -> str:
        """토큰 → user_id. 없거나 만료면 빈 문자열.

        ⚠️ 만료를 **읽는 쪽에서** 판정한다. 만료 청소를 배치에 맡기면 그 배치가 멈춘 동안
          죽은 세션이 살아 있다."""
        t = (token or "").strip()
        if not t:
            return ""
        try:
            self._init()
            with self._connect() as conn:
                r = conn.execute("SELECT user_id, expires_at FROM auth_session WHERE token=?",
                                 (t,)).fetchone()
            if r is None:
                return ""
            if _iso(_now()) > str(r["expires_at"]):
                self.destroy(t)
                return ""
            return str(r["user_id"])
        except Exception:
            return ""                   # 인증 저장소 장애를 «인증됨» 으로 바꾸지 않는다

    def destroy(self, token: str) -> None:
        try:
            self._init()
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM auth_session WHERE token=?", ((token or "").strip(),))
                conn.commit()
        except Exception:
            pass

    def destroy_all_for(self, user_id: str) -> int:
        """그 사용자의 모든 세션을 끊는다 — 권한을 회수했을 때 쓴다."""
        self._init()
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM auth_session WHERE user_id=?",
                               ((user_id or "").strip(),))
            conn.commit()
            return cur.rowcount or 0


auth_store = AuthStore()
