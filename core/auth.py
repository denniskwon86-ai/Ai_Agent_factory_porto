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

#: [P0-1B] SSE 티켓 수명. 짧을수록 좋지만 **너무 짧으면 느린 회선에서 연결 전에 죽는다.**
SSE_TICKET_SECONDS = 30
#: 티켓 청중(audience). 세션 토큰과 **용도가 다르다** — 티켓으로 일반 API 를 부를 수 없다.
SSE_AUDIENCE = "sse"
#: [G1-C1.2] SSE 문맥 규약 판본. 티켓에 봉인하고 소비 때 대조한다.
#: ⚠️ 문맥 필드를 늘리거나 뜻을 바꾸면 **반드시 올린다** — 안 올리면 옛 규약으로 발급된 표가
#:   새 규약인 척 통과하고, 그 표에는 지금 필요한 값이 없다.
SSE_CONTEXT_VERSION = "g1c12"

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
    expires_at  TEXT NOT NULL,
    -- ★★ [G1-C1.3] SSE 티켓에는 세션 **해시**가 봉인된다. 이벤트를 보낼 때마다 「그 세션이
    --   아직 살아 있는가」를 물어야 하는데, 원문 토큰으로만 찾을 수 있으면 전 세션을 훑어야
    --   한다. 조회용 해시를 함께 둔다.
    token_hash  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_session_hash ON auth_session(token_hash);
CREATE INDEX IF NOT EXISTS idx_session_user ON auth_session(user_id);

-- ★★★ [P0-1B] SSE 접속표.
--
-- EventSource 는 헤더를 붙일 수 없어 지금까지 `?as_user=` 로 «누구인지» 를 말했다. 그것은
-- 인증이 아니라 **자기 신고**였고, 다른 사람 ID 를 적으면 그 사람으로 구독됐다.
--
-- ⚠️ **원문을 저장하지 않는다.** 티켓은 URL 로 오가므로 접근 로그·리퍼러·브라우저 히스토리에
--   남을 수 있다. 저장소까지 원문을 두면 유출면이 하나 더 늘어난다 — 해시만 둔다.
-- ⚠️ **프로세스 메모리에 두지 않는다.** 워커가 둘이면 A 워커가 발급한 티켓을 B 워커가 모르고,
--   반대로 «이미 쓴 티켓» 을 다른 워커가 다시 받아 준다. DB 한 곳에서 원자적으로 소비한다.
CREATE TABLE IF NOT EXISTS auth_sse_ticket (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    tenant_id   TEXT NOT NULL DEFAULT '',
    -- ★★ [G1-C1.1] 실행 문맥을 표에 **함께 묶는다.** 신원만으로는 부족하다 —
    --   같은 사람이라도 어느 테넌트·어느 조직 범위·REAL 인지 VIRTUAL 인지에 따라
    --   받아야 할 이벤트가 다르다. 구독 뒤에 화면이 문맥을 바꿔 신고하면 그것이 곧 우회로다.
    scope_node_id TEXT NOT NULL DEFAULT '',
    entity_mode   TEXT NOT NULL DEFAULT '',
    -- ★★ [G1-C1.2] 이 표를 발급할 때의 문맥 규약 판본. 규약이 바뀌면 옛 표는 거절한다 —
    --   호환을 남기면 «문맥 없는 구형 티켓» 이 영원히 통하는 우회로가 된다.
    context_version TEXT NOT NULL DEFAULT '',
    audience    TEXT NOT NULL DEFAULT 'sse',
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    consumed_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ticket_expires ON auth_sse_ticket(expires_at);
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
            # ★★★ [2026-08-13 실측 회귀 수정] **컬럼 보강을 `executescript` 보다 먼저** 한다.
            #
            #   ⚠️ `CREATE TABLE IF NOT EXISTS` 는 이미 있는 표에 새 컬럼을 넣어 주지 않는다.
            #     그런데 `_DDL` 안에는 그 새 컬럼을 쓰는 **인덱스 생성**이 함께 들어 있다
            #     (`idx_session_hash ON auth_session(token_hash)`). 순서가 뒤였을 때 실제로
            #     일어난 일: 옛 DB 에서 그 인덱스 문이 `no such column: token_hash` 로 죽고,
            #     `executescript` 전체가 예외로 끝나 **뒤의 ALTER 에 영원히 도달하지 못했다.**
            #     즉 보강 코드는 있는데 실행되지 않았고, `_init()` 이 매번 터져
            #     **로그인이 500** 이었다(2026-08-12 `3641a02e9` 이후 계속).
            #
            #   ★ 새 DB 에서는 이 ALTER 들이 «표가 없다» 로 조용히 실패하고, 바로 아래
            #     `executescript` 가 처음부터 옳은 스키마로 만든다 — 양쪽 다 성립한다.
            #   ⚠️ 순서를 되돌리지 말 것. 되돌리면 **기존 DB 를 쓰는 모든 환경에서 로그인이
            #     죽는다** — 그리고 새로 만든 DB 로 도는 테스트는 그것을 절대 못 본다.
            for table, col, ddl in (
                    ("auth_sse_ticket", "scope_node_id", "TEXT NOT NULL DEFAULT ''"),
                    ("auth_sse_ticket", "entity_mode", "TEXT NOT NULL DEFAULT ''"),
                    ("auth_sse_ticket", "context_version", "TEXT NOT NULL DEFAULT ''"),
                    ("auth_session", "token_hash", "TEXT NOT NULL DEFAULT ''")):
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                except Exception:
                    pass                 # 표가 없거나(새 DB) 이미 있으면(재기동) 그만이다
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
            #: [G1-C1.3] 조회용 해시를 함께 적는다 — SSE 가 «이 세션이 살아 있는가» 를 묻는다.
            conn.execute("INSERT INTO auth_session (token, user_id, created_at, expires_at, "
                         "token_hash) VALUES (?,?,?,?,?)",
                         (token, uid, _iso(now), _iso(exp), self._ticket_hash(token)))
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

    # ── [P0-1B] SSE 접속표 ────────────────────────────────────────────────
    def session_hash(self, session_token: str) -> str:
        """세션 토큰 → `auth_session.token_hash` 와 **같은 값**.

        ★ [G1-B 3.5] 앱 증명을 세션에 묶는 축이다. 같은 함수를 쓰는 것이 요점이다 —
          다른 함수로 만들면 로그아웃이 지운 행과 증명이 가리키는 세션이 **다른 것**이 되고,
          그러면 회수가 조용히 실패한다."""
        return self._ticket_hash(session_token)

    @staticmethod
    def _ticket_hash(raw: str) -> str:
        """티켓 원문 → 저장용 해시.

        ⚠️ 비밀번호가 아니므로 pbkdf2 를 쓰지 않는다. 티켓은 **256비트 난수**이고 30초만 산다 —
          사전 공격 대상이 아니다. 대신 **소비 경로가 빨라야** 한다(연결마다 1회)."""
        return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()

    def issue_sse_ticket(self, user_id: str, session_token: str,
                         tenant_id: str = "", scope_node_id: str = "",
                         entity_mode: str = "") -> Dict[str, Any]:
        """SSE 1회용 티켓 발급. **원문은 여기서 한 번만 돌려준다.**

        ⚠️ `user_id` 를 호출자가 정하게 두지 않는다 — 라우트가 **세션에서 확인한 값**만 넘긴다.
          그렇지 않으면 티켓 발급 자체가 새로운 사칭 경로가 된다."""
        uid = (user_id or "").strip()
        if not uid:
            raise ValueError("세션에서 확인된 사용자 없이 티켓을 발급할 수 없습니다.")
        raw = secrets.token_urlsafe(32)          # 256비트
        now = _now()
        exp = now + timedelta(seconds=SSE_TICKET_SECONDS)
        self._init()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_sse_ticket (token_hash, user_id, session_id, tenant_id, "
                "scope_node_id, entity_mode, context_version, audience, created_at, expires_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (self._ticket_hash(raw), uid, self._ticket_hash(session_token or ""),
                 (tenant_id or "").strip(), (scope_node_id or "").strip(),
                 (entity_mode or "").strip(), SSE_CONTEXT_VERSION,
                 SSE_AUDIENCE, _iso(now), _iso(exp)))
            #: 만료된 표는 그때그때 치운다 — 배치에 맡기면 그 배치가 멈춘 동안 쌓인다.
            conn.execute("DELETE FROM auth_sse_ticket WHERE expires_at < ?", (_iso(now),))
            conn.commit()
        return {"ticket": raw, "expires_at": _iso(exp),
                "expires_in": SSE_TICKET_SECONDS, "audience": SSE_AUDIENCE}

    def consume_sse_ticket(self, raw: str) -> Dict[str, str]:
        """티켓 → **실행 문맥**. 실패하면 빈 사전. **성공은 정확히 한 번만 일어난다.**

        ★★ [G1-C1.1] 종전에는 `user_id` 문자열만 돌려줬다. 신원만으로는 이벤트를 가를 수 없다 —
          같은 사람이라도 어느 테넌트·어느 조직 범위·REAL 인지 VIRTUAL 인지에 따라 받아야 할
          것이 다르다. 그 문맥을 **발급 시점에 표에 묶어** 두고 여기서 함께 돌려준다.
          화면이 구독 뒤에 문맥을 바꿔 신고할 수 있으면 그것이 곧 우회로다.

        ★★ 원자성: `UPDATE ... WHERE consumed_at=''` 한 문장으로 소비를 표시하고 **바뀐 행 수**로
          판정한다. 「읽고 → 확인하고 → 쓰기」로 나누면 두 요청이 그 사이를 통과해 **같은 표로
          둘 다 연결**된다(다중 워커에서는 더 쉽게 일어난다).

        ⚠️ 실패 사유를 나누지 않는다 — 없음·만료·이미 씀 모두 빈 문자열이다. 호출자가 할 일은
          어느 쪽이든 «새 티켓을 받아 다시 연결» 하나뿐이다."""
        t = (raw or "").strip()
        if not t:
            return {}
        h = self._ticket_hash(t)
        now = _iso(_now())
        try:
            self._init()
            with self._lock, self._connect() as conn:
                cur = conn.execute(
                    "UPDATE auth_sse_ticket SET consumed_at=? "
                    "WHERE token_hash=? AND consumed_at='' AND expires_at>=? AND audience=?",
                    (now, h, now, SSE_AUDIENCE))
                if cur.rowcount != 1:
                    conn.commit()
                    return {}
                r = conn.execute(
                    "SELECT user_id, tenant_id, scope_node_id, entity_mode, session_id, "
                    "context_version FROM auth_sse_ticket WHERE token_hash=?", (h,)).fetchone()
                conn.commit()
            if not r:
                return {}
            # ⚠️ [G1-C1.2] 규약 판본이 다르면 **거절한다.** 옛 표에는 지금 필요한 문맥이 없고,
            #   「없으면 통과」로 두면 그것이 영구 우회로가 된다. 화면은 새 표를 받으면 된다.
            if str(r["context_version"] or "") != SSE_CONTEXT_VERSION:
                return {}
            return {"user_id": str(r["user_id"] or ""),
                    "tenant_id": str(r["tenant_id"] or ""),
                    "scope_node_id": str(r["scope_node_id"] or ""),
                    "entity_mode": str(r["entity_mode"] or ""),
                    "session_id": str(r["session_id"] or ""),
                    "context_version": str(r["context_version"] or "")}
        except Exception:
            return {}                   # 저장소 장애를 «인증됨» 으로 바꾸지 않는다

    def session_alive_by_hash(self, session_hash: str) -> bool:
        """[G1-C1.3] **이 세션이 아직 살아 있는가.** 티켓에 봉인된 해시로 묻는다.

        ★★ SSE 는 한 번 열리면 최대 12시간 산다. 그래서 로그아웃·비밀번호 변경·관리자의 세션
          강제 폐기가 **이미 열린 스트림에는 닿지 않았다** — 사용자는 로그아웃했다고 믿는데
          그 브라우저는 계속 이벤트를 받는다. 「나갔다」와 「안 보인다」가 다르면 그것은 유출이다.

        ⚠️ 원문 토큰이 아니라 **해시**로 묻는다. 티켓 표에는 해시만 있고, 그것으로 충분하다.
        ⚠️ 조회 실패를 «살아 있다» 로 답하지 않는다 — 저장소가 흔들리는 순간이 곧 유출 구간이 된다."""
        h = (session_hash or "").strip()
        if not h:
            return False
        try:
            self._init()
            now = _iso(_now())
            with self._lock, self._connect() as conn:
                r = conn.execute(
                    "SELECT 1 FROM auth_session WHERE token_hash=? AND expires_at>=?",
                    (h, now)).fetchone()
            return bool(r)
        except Exception:
            return False

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
