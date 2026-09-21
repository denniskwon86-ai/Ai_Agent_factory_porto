# -*- coding: utf-8 -*-
"""[DB-1] 저장소 방언을 **한 곳에서** 흡수한다 — PostgreSQL 이관의 첫 adapter.

## 왜 여기인가

이관을 각 store 안에서 하면 `?`·`%s`·UPSERT·트랜잭션 시작 구문이 **17개 파일에 흩어진다.**
한 곳만 고쳐지는 날이 오고, 그때 어느 쪽이 맞는지 아무도 모른다. 방언 차이는 여기 모은다.

## 이 판이 **하지 않는** 것

⚠️ **기존 SQL 을 고치지 않는다.** `core/auth.py` 같은 store 는 지금 쓰는 `?` 자리표시자를
  그대로 쓴다 — 연결 wrapper 가 실행 직전에 옮긴다. 로그인 경로의 SQL 을 손으로 다시 쓰는 것은
  이관의 첫 걸음에서 **가장 위험한 일**이다.
⚠️ **기동 중 DDL 을 옮겨 심지 않는다.** PostgreSQL 스키마는 `schema/` 의 설치 산출물이고,
  제품이 뜨면서 `CREATE TABLE` 을 돌리지 않는다(다중 인스턴스에서 동시에 도는 DDL 은 사고다).
⚠️ **기본값은 지금 그대로 SQLite 다.** 설정을 주지 않으면 동작이 한 글자도 달라지지 않는다.

## 실행 환경

~~⚠️ 이 저장소에는 **PostgreSQL 실행 환경이 없다.** 아래 PG 경로는 한 번도 실행되지
않았다.~~ — **2026-09-21 해소.** 격리 로컬 PostgreSQL 16.15 에서 실제로 돌았다
(`scripts/p03_pg_consumption.py`): 설치 역할로 스키마를 넣고, runtime 역할로 로그인·
세션·조직 문맥 조회·SSE 티켓 단일/동시 소비·프로세스 재시작까지 통과했다.

⚠️ 다만 **범위를 넘겨 읽지 말 것.** 확인한 것은 첫 경로 두 store(`auth`,
  `enterprise_context`)이고 합성 자료다. 나머지 store 와 운영 규모·운영 자료는
  아직이다 — 「PostgreSQL 이관이 끝났다」가 아니라 「첫 경로가 실제로 돌았다」이다.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

SQLITE = "sqlite"
POSTGRES = "postgres"

#: 설정은 환경변수 하나로 읽는다. 없으면 SQLite — 지금 동작 그대로다.
_BACKEND_ENV = "AFS_DB_BACKEND"
_DSN_ENV = "AFS_DB_DSN"


def configured_backend() -> str:
    """지금 쓰기로 되어 있는 저장소. **모르는 값이면 SQLite 로 떨어지지 않고 거절한다.**

    ⚠️ 오타 하나로 조용히 SQLite 로 돌아가면, 「PostgreSQL 로 돌고 있다」고 믿는 채
      파일 DB 에 쓰게 된다. 그 사고는 한참 뒤에 발견된다."""
    raw = (os.environ.get(_BACKEND_ENV) or SQLITE).strip().lower()
    if raw not in (SQLITE, POSTGRES):
        raise ValueError(
            f"{_BACKEND_ENV} 값을 알 수 없습니다: {raw!r} (허용: {SQLITE}, {POSTGRES})")
    return raw


def translate_placeholders(sql: str) -> str:
    """`?` 자리표시자를 `%s` 로 옮긴다 — **문자열 리터럴 안은 건드리지 않는다.**

    ⚠️⚠️ 단순 `sql.replace('?', '%s')` 는 `WHERE note LIKE '왜?'` 같은 리터럴 안의 물음표까지
      바꾼다. 그러면 파라미터 개수가 어긋나 **런타임에야** 터지고, 그 SQL 은 대개 드문 분기다.
    ⚠️ `%` 도 함께 처리한다. psycopg 의 `format` paramstyle 에서 `LIKE '%x%'` 의 `%` 는
      자리표시자로 읽혀 깨진다 — 리터럴 안의 `%` 는 `%%` 로 escape 한다.

    ⚠️⚠️ **주석 안도 건드리지 않는다.** 실제로 여기서 터졌다: 설치 스키마의
      `auth_sse_ticket` 앞 주석에 소비 SQL 예시를 적어 두었는데 거기 `?` 가 4개였고,
      번역기가 그걸 `%s` 로 바꿔 **psycopg 가 「자리표시자 4개인데 파라미터 0개」로
      거절**했다. SQLite 에서는 번역을 안 하니 끝까지 안 보였고, 실제 PG 첫 적용에서야
      드러났다. 설명을 적었다는 이유로 SQL 이 깨지면 안 된다.
    """
    out: list[str] = []
    quote: Optional[str] = None
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if quote is None:
            #: `--` 는 줄 끝까지, `/* */` 는 닫힐 때까지 **그대로** 흘려보낸다.
            if ch == "-" and sql.startswith("--", i):
                end = sql.find(chr(10), i)
                end = n if end == -1 else end
                out.append(sql[i:end]); i = end; continue
            if ch == "/" and sql.startswith("/*", i):
                end = sql.find("*/", i + 2)
                end = n if end == -1 else end + 2
                out.append(sql[i:end]); i = end; continue
        if quote:
            #: 리터럴 안 — SQL 은 따옴표를 겹쳐서 escape 한다('' / "").
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:
                    out.append(ch); out.append(ch); i += 2; continue
                quote = None
            out.append("%%" if ch == "%" else ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "?":
            out.append("%s")
        elif ch == "%":
            out.append("%%")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


@dataclass(frozen=True)
class Dialect:
    """방언 차이 — **세 가지뿐**이다. 더 늘리기 전에 정말 필요한지 묻는다."""
    name: str
    #: 쓰기 잠금을 «먼저» 잡는 트랜잭션 시작. 재개의 CAS 가 이것에 기댄다.
    begin_immediate: str
    #: 실행 직전 SQL 변환. SQLite 는 그대로 둔다(변환 비용 0 · 위험 0).
    translate: Callable[[str], str]


SQLITE_DIALECT = Dialect(name=SQLITE, begin_immediate="BEGIN IMMEDIATE",
                         translate=lambda sql: sql)
#: PostgreSQL 에는 `BEGIN IMMEDIATE` 가 없다. 쓰기 잠금을 먼저 잡는 같은 효과는
#: `SELECT … FOR UPDATE` 나 직렬화 수준으로 낸다 — **그 선택은 store 마다 다르므로**
#: 여기서는 평범한 `BEGIN` 만 주고, 잠금 방식은 부르는 쪽이 명시한다.
POSTGRES_DIALECT = Dialect(name=POSTGRES, begin_immediate="BEGIN",
                           translate=translate_placeholders)


def dialect_for(backend: Optional[str] = None) -> Dialect:
    return SQLITE_DIALECT if (backend or configured_backend()) == SQLITE else POSTGRES_DIALECT


class TranslatingConnection:
    """실행 직전에 SQL 을 방언으로 옮기는 얇은 wrapper.

    ★ store 가 쓰는 `execute`·`executemany`·`commit`·`close`·컨텍스트 매니저만 감싼다.
      DB-API 전체를 흉내 내지 않는다 — 흉내 내기 시작하면 그것이 두 번째 드라이버가 된다.
    ⚠️ `executescript` 는 **감싸지 않는다.** 여러 문장을 한 번에 도는 DDL 은 설치 단계의
      일이고, 이관에서는 그 경로 자체를 없애는 것이 목표다."""

    def __init__(self, raw: Any, dialect: Dialect):
        self._raw = raw
        self._dialect = dialect

    # ── DB-API 위임 ──────────────────────────────────────────────────
    def execute(self, sql: str, params: Optional[Sequence[Any]] = None):
        #: ⚠️ 파라미터가 없으면 **`None` 으로 넘긴다.** 빈 튜플을 주면 psycopg 가
        #:   결합 경로를 타면서 SQL 본문의 `%`/`%s` 를 자리표시자로 읽는다. DDL 처럼
        #:   파라미터가 없는 문장은 결합을 아예 지나지 않아야 한다(둘째 층).
        translated = self._dialect.translate(sql)
        if params is None:
            return self._raw.execute(translated)
        return self._raw.execute(translated, params)

    def executemany(self, sql: str, seq):
        return self._raw.executemany(self._dialect.translate(sql), seq)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()

    def cursor(self):
        return self._raw.cursor()

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, *exc):
        return self._raw.__exit__(*exc)

    def __getattr__(self, name):
        #: 나머지는 그대로 통과시킨다(`row_factory`, `isolation_level` 등).
        return getattr(self._raw, name)


def connect_sqlite(db_path: str, timeout: float = 5.0) -> sqlite3.Connection:
    """지금 쓰는 그 연결. **동작을 바꾸지 않는다.**"""
    folder = os.path.dirname(db_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn


class ConnectionFactory:
    """부를 수 있고, **자기 방언을 스스로 말한다.**

    ★★ [P03.2 준비] 방언을 «런타임 환경값» 으로 추측하지 않기 위해서다. 주입된 연결이
      무엇인지는 그 연결을 만든 쪽만 안다 — `AFS_DB_BACKEND` 를 읽어 맞히면, 환경은
      PG 인데 실제로는 SQLite 를 물고 있는 조합에서 **SQLite 전용 문장을 PG 로 보내거나
      그 반대**가 된다. 그래서 factory 가 `backend` 를 들고 다닌다.

    ⚠️ `describe` 에 접속 정보 «값» 을 넣지 않는다 — 로그·보고로 새는 첫 경로가 된다."""

    def __init__(self, backend: str, make, describe: str):
        self.backend = backend
        self.describe = describe
        self._make = make

    def __call__(self):
        return self._make()

    def __repr__(self) -> str:  # pragma: no cover - 표시용
        return f"<ConnectionFactory {self.backend} {self.describe}>"


def sqlite_factory(db_path: str, timeout: float = 5.0) -> ConnectionFactory:
    return ConnectionFactory(SQLITE, lambda: connect_sqlite(db_path, timeout),
                             describe="sqlite(file)")


def postgres_factory(dsn: str = "", timeout: float = 10.0) -> ConnectionFactory:
    """★ [2026-09-21 실측] 격리 로컬 PG 16.15 에서 제품 경로가 이 팩토리로 돌았다.

    ★★ 행 형식을 **여기서 고정한다.** 제품의 ECM 은 조회 결과에 `dict(row)` 를 하고
      auth 는 `row["user_id"]` 로 읽는다. psycopg 의 기본 행은 **튜플**이라 그대로 두면
      `dict(row)` 가 그 자리에서 깨진다. 그래서 `dict_row` 를 붙인다 — 제품 SQL 을
      고치는 대신 **연결을 제품이 기대하는 모양으로** 맞춘다."""
    target = dsn or os.environ.get(_DSN_ENV) or ""
    if not target:
        raise RuntimeError(
            f"PostgreSQL 접속 정보가 없습니다 — {_DSN_ENV} 를 설정하십시오. "
            f"(접속 정보 자체는 로그·문서에 남기지 않습니다.)")

    def make():
        try:
            import psycopg                               # type: ignore
            from psycopg.rows import dict_row            # type: ignore
        except ImportError as exc:                       # pragma: no cover
            raise RuntimeError(
                "PostgreSQL 드라이버(psycopg)가 설치되어 있지 않습니다 — SQLite 로 "
                "조용히 돌아가지 않고 여기서 멈춥니다.") from exc
        raw = psycopg.connect(target, row_factory=dict_row, connect_timeout=int(timeout))
        return TranslatingConnection(raw, POSTGRES_DIALECT)

    return ConnectionFactory(POSTGRES, make, describe="postgres(<AFS_DB_DSN>)")


def connect(db_path: str = "", *, backend: Optional[str] = None,

            dsn: Optional[str] = None, timeout: float = 5.0):
    """저장소 연결 하나. 기본은 SQLite — 설정을 주지 않으면 지금과 같다.

    ⚠️ 드라이버가 없으면 여기서 분명히 거절한다 — 조용히 SQLite 로 떨어지면
      「PG 로 돌고 있다」는 거짓 믿음이 생긴다.
    ★ [2026-09-21] PG 경로는 격리 로컬 PG 16.15 에서 실제로 돌았다. 다만 이 함수가
      아니라 `postgres_factory()` 로 돌았다 — **이 진입점 자체는 아직 미실행**이다."""
    chosen = backend or configured_backend()
    if chosen == SQLITE:
        return connect_sqlite(db_path, timeout=timeout)
    target = dsn or os.environ.get(_DSN_ENV) or ""
    if not target:
        raise RuntimeError(
            f"PostgreSQL 을 쓰기로 되어 있으나 접속 정보가 없습니다 — {_DSN_ENV} 를 "
            f"설정하십시오. (접속 정보 자체는 로그·문서에 남기지 않습니다.)")
    try:
        import psycopg                                   # type: ignore
    except ImportError as exc:                           # pragma: no cover - 환경 의존
        raise RuntimeError(
            "PostgreSQL 드라이버(psycopg)가 설치되어 있지 않습니다 — SQLite 로 "
            "조용히 돌아가지 않고 여기서 멈춥니다.") from exc
    return TranslatingConnection(psycopg.connect(target), POSTGRES_DIALECT)
