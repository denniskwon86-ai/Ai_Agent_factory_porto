"""[DB-1] 첫 adapter — 방언 번역·기본값 불변·티켓 1회 소비 계약.

⚠️ **PostgreSQL 서버는 없다.** 여기서 잠그는 것은 ① 자리표시자 번역이 정확한가
  ② 설정을 주지 않으면 지금 동작이 한 글자도 안 바뀌는가 ③ 「정확히 한 번 소비」 계약이
  방언과 무관하게 성립하는가 — **세 가지뿐**이다. 「PostgreSQL 에서 된다」는 증거가 아니다.
"""
from __future__ import annotations

import os
import sqlite3
import threading

import pytest

from core import db as dbmod


# ── ① 자리표시자 번역 ────────────────────────────────────────────────────
def test_placeholders_become_percent_s():
    assert dbmod.translate_placeholders(
        "SELECT a FROM t WHERE b=? AND c=?") == "SELECT a FROM t WHERE b=%s AND c=%s"


def test_question_mark_inside_a_literal_is_left_alone():
    """⚠️ 단순 replace 는 리터럴 안의 물음표까지 바꾼다 — 그러면 파라미터 수가 어긋나고

    **드문 분기에서 런타임에야** 터진다."""
    out = dbmod.translate_placeholders("SELECT * FROM t WHERE note='왜?' AND id=?")
    assert out == "SELECT * FROM t WHERE note='왜?' AND id=%s"
    assert out.count("%s") == 1


def test_escaped_quote_inside_a_literal_does_not_end_it():
    out = dbmod.translate_placeholders("SELECT '그''는 ?' , x FROM t WHERE y=?")
    assert out.count("%s") == 1, out


def test_percent_is_escaped_for_format_paramstyle():
    """⚠️ psycopg 의 `format` 에서 `LIKE '%x%'` 의 `%` 는 자리표시자로 읽혀 깨진다."""
    out = dbmod.translate_placeholders("SELECT * FROM t WHERE n LIKE '%수%' AND id=?")
    assert "%%수%%" in out and out.count("%s") == 1


def test_question_mark_inside_a_line_comment_is_left_alone():
    """★★ [2026-09-21 실측] **실제 PG 설치가 여기서 멈췄다.**

    `001_auth_and_context.sql` 의 `auth_sse_ticket` 위 주석에 예시 SQL 이 있고 거기
    물음표가 네 개 있었다. 번역이 그것까지 `%s` 로 바꾸는 바람에 psycopg 가
    «자리표시자 4개인데 파라미터가 0개» 라며 설치를 거절했다. 주석은 **실행되지 않는
    글**이므로 번역기가 손대면 안 된다."""
    out = dbmod.translate_placeholders(
        "-- VALUES (?,?,?,?) 처럼 쓴다" + chr(10) + "SELECT a FROM t WHERE b=?")
    assert out.count("%s") == 1, out
    assert "(?,?,?,?)" in out, "주석 안의 물음표를 건드렸다"


def test_question_mark_inside_a_block_comment_is_left_alone():
    out = dbmod.translate_placeholders(
        "/* 예: WHERE x=? AND y=? */ SELECT a FROM t WHERE b=?")
    assert out.count("%s") == 1, out
    assert "x=? AND y=?" in out


def test_a_comment_does_not_swallow_the_rest_of_the_statement():
    """⚠️ 주석을 건너뛰다가 끝을 잘못 잡으면 **뒤의 진짜 자리표시자까지** 사라진다.

    그러면 이번엔 반대 방향으로 «파라미터는 있는데 자리표시자가 없다» 가 된다."""
    out = dbmod.translate_placeholders(
        "SELECT a FROM t -- 주석 ?" + chr(10) + "WHERE b=? AND c=?")
    assert out.count("%s") == 2, out


def test_install_ddl_translates_to_zero_placeholders():
    """★★ 파일 단위 불변식: **설치 DDL 에는 파라미터가 없다.**

    번역 결과에 `%s` 가 하나라도 생겼다면 실행되지 않을 무언가(주석·리터럴)를
    자리표시자로 오독한 것이다. 단위 시험이 못 본 새 문장이 들어와도 여기서 걸린다."""
    schema = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "core", "db", "schema", "001_auth_and_context.sql")
    sql = open(schema, encoding="utf-8").read()
    out = dbmod.translate_placeholders(sql)
    assert "%s" not in out, "설치 DDL 에서 자리표시자를 만들어 냈다"


def test_execute_without_params_does_not_pass_an_empty_tuple():
    """★★ 둘째 층. 빈 튜플을 주면 psycopg 가 결합 경로를 타면서 본문의 `%` 를 다시
    자리표시자로 읽는다. 파라미터가 없는 문장은 결합을 **아예 지나지 않아야** 한다."""
    seen = []

    class Raw:
        def execute(self, sql, *args):
            seen.append(args)
            return None

    conn = dbmod.TranslatingConnection(Raw(), dbmod.POSTGRES_DIALECT)
    conn.execute("CREATE TABLE t(a text)")
    assert seen == [()], f"파라미터 없이 부른 문장에 무언가를 딸려 보냈다: {seen}"


def test_sqlite_dialect_does_not_touch_sql():
    """★ SQLite 쪽은 **변환하지 않는다** — 비용 0 · 위험 0."""
    sql = "SELECT * FROM t WHERE a=? AND n LIKE '%x%'"
    assert dbmod.SQLITE_DIALECT.translate(sql) == sql


# ── ② 설정을 주지 않으면 지금 그대로 ──────────────────────────────────────
def test_default_backend_is_sqlite(monkeypatch):
    monkeypatch.delenv(dbmod._BACKEND_ENV, raising=False)
    assert dbmod.configured_backend() == dbmod.SQLITE
    assert dbmod.dialect_for() is dbmod.SQLITE_DIALECT


def test_unknown_backend_is_refused_not_silently_sqlite(monkeypatch):
    """⚠️ 오타 하나로 조용히 SQLite 로 떨어지면 「PG 로 돌고 있다」고 믿는 채 파일에 쓴다."""
    monkeypatch.setenv(dbmod._BACKEND_ENV, "postgre")
    with pytest.raises(ValueError):
        dbmod.configured_backend()


def test_connect_returns_a_plain_sqlite_connection(tmp_path, monkeypatch):
    """★ 기본 경로는 **감싸지 않는다** — 지금 동작과 같아야 한다."""
    monkeypatch.delenv(dbmod._BACKEND_ENV, raising=False)
    conn = dbmod.connect(str(tmp_path / "x.db"))
    try:
        assert isinstance(conn, sqlite3.Connection)
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_postgres_without_dsn_refuses_loudly(monkeypatch):
    """⚠️ 접속 정보가 없으면 **여기서 멈춘다.** 조용히 SQLite 로 돌아가지 않는다."""
    monkeypatch.setenv(dbmod._BACKEND_ENV, dbmod.POSTGRES)
    monkeypatch.delenv(dbmod._DSN_ENV, raising=False)
    with pytest.raises(RuntimeError) as caught:
        dbmod.connect("ignored.db")
    #: 접속 정보 «값» 은 메시지에 싣지 않는다.
    assert "DSN" in str(caught.value) or "접속 정보" in str(caught.value)


# ── ③ 「정확히 한 번 소비」 계약 ─────────────────────────────────────────
#: ⚠️ 이 계약이 이관에서 가장 잃기 쉽다. 방언이 바뀌어도 **조건절이 그대로** 가야 한다.
CONSUME = ("UPDATE auth_sse_ticket SET consumed_at=? "
           "WHERE token_hash=? AND consumed_at='' AND expires_at>=? AND audience=?")


def _ticket_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "t.db"), timeout=5)
    conn.execute("CREATE TABLE auth_sse_ticket (token_hash TEXT PRIMARY KEY, "
                 "audience TEXT NOT NULL, expires_at TEXT NOT NULL, "
                 "consumed_at TEXT NOT NULL DEFAULT '')")
    conn.execute("INSERT INTO auth_sse_ticket VALUES (?,?,?,'')",
                 ("h1", "sse", "2999-01-01"))
    conn.commit()
    return conn


def test_single_update_consumes_exactly_once(tmp_path):
    conn = _ticket_db(tmp_path)
    try:
        first = conn.execute(CONSUME, ("now", "h1", "2026-01-01", "sse")).rowcount
        second = conn.execute(CONSUME, ("now", "h1", "2026-01-01", "sse")).rowcount
        conn.commit()
        assert (first, second) == (1, 0), "두 번째 소비가 통과했다"
    finally:
        conn.close()


def test_expired_or_wrong_audience_never_consumes(tmp_path):
    """★ 음성 대조 — 만료·다른 청중은 통과하지 않는다(위 시험이 «늘 1» 이 아님을 보인다)."""
    conn = _ticket_db(tmp_path)
    try:
        assert conn.execute(CONSUME, ("now", "h1", "3999-01-01", "sse")).rowcount == 0
        assert conn.execute(CONSUME, ("now", "h1", "2026-01-01", "other")).rowcount == 0
        conn.commit()
    finally:
        conn.close()


def test_two_threads_cannot_both_consume(tmp_path):
    """★ 「읽고 → 확인하고 → 쓰기」로 나누면 둘 다 통과한다. 한 문장이라 그렇지 않다.

    ⚠️ 응용 메모리 lock 없이도 성립해야 한다 — 다중 인스턴스에서는 lock 이 없다."""
    path = str(tmp_path / "race.db")
    setup = sqlite3.connect(path)
    setup.execute("CREATE TABLE auth_sse_ticket (token_hash TEXT PRIMARY KEY, "
                  "audience TEXT NOT NULL, expires_at TEXT NOT NULL, "
                  "consumed_at TEXT NOT NULL DEFAULT '')")
    setup.execute("INSERT INTO auth_sse_ticket VALUES ('h1','sse','2999-01-01','')")
    setup.commit()
    setup.close()

    wins: list[int] = []
    gate = threading.Barrier(2)

    def consume():
        conn = sqlite3.connect(path, timeout=10)
        try:
            gate.wait()
            cur = conn.execute(CONSUME, ("now", "h1", "2026-01-01", "sse"))
            conn.commit()
            wins.append(cur.rowcount)
        finally:
            conn.close()

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert sorted(wins) == [0, 1], f"정확히 하나만 성공해야 한다 — 실제 {wins}"


# ── 설치 스키마는 «설치» 산출물이다 ──────────────────────────────────────
def test_postgres_schema_is_an_install_artifact_not_boot_ddl():
    """⚠️ 제품 기동 경로가 이 파일을 읽어 돌리면 다중 인스턴스에서 DDL 이 동시에 돈다."""
    path = os.path.join(os.path.dirname(os.path.abspath(dbmod.__file__)),
                        "schema", "001_auth_and_context.sql")
    assert os.path.exists(path), "첫 슬라이스 스키마가 없다"
    body = open(path, encoding="utf-8").read()
    for table in ("auth_credential", "auth_session", "auth_sse_ticket",
                  "tenants", "organization_nodes", "organization_edges",
                  "organization_node_code_aliases"):
        assert table in body, f"{table} 가 첫 슬라이스 스키마에 없다"
    #: 제품 코드가 이 스키마를 기동 중에 읽지 않는다.
    assert "001_auth_and_context" not in open(dbmod.__file__, encoding="utf-8").read()


# ── ④ 주입점 — 세 저장소가 «같은 방식» 으로 연결을 받는다 ────────────────
#: ⚠️ 주입점이 저장소마다 다른 이름·다른 모양이면 이관할 때 각자 다르게 고쳐진다.
STORES = (
    ("core.auth", "AuthStore"),
    ("core.enterprise_context.repository", "EcmRepository"),
    ("core.program_lifecycle", "ProgramLifecycle"),
)


@pytest.mark.parametrize("module_name,class_name", STORES)
def test_every_store_takes_a_connect_factory(module_name, class_name):
    import importlib
    import inspect

    cls = getattr(importlib.import_module(module_name), class_name)
    params = inspect.signature(cls.__init__).parameters
    assert "connect" in params, f"{class_name} 에 연결 주입점이 없다"
    assert params["connect"].default is None, f"{class_name} 의 기본값이 None 이 아니다"


@pytest.mark.parametrize("module_name,class_name", STORES)
def test_injected_factory_is_actually_used(tmp_path, module_name, class_name):
    """★ 「인자를 받는다」와 「그것을 쓴다」는 다르다 — 실제로 불리는지 센다."""
    import importlib

    cls = getattr(importlib.import_module(module_name), class_name)
    calls = {"n": 0}
    path = str(tmp_path / f"{class_name}.db")

    def factory():
        calls["n"] += 1
        return dbmod.connect_sqlite(path)

    store = cls(path, connect=factory)
    #: 생성자에서 이미 부르는 저장소도 있고(EcmRepository 는 `_init_db`), 아닌 것도 있다.
    if calls["n"] == 0:
        store._connect().close()
    assert calls["n"] >= 1, f"{class_name} 이 주입된 연결을 쓰지 않는다"


def test_begin_immediate_is_not_hardcoded_in_program_lifecycle(tmp_path):
    """⚠️ `BEGIN IMMEDIATE` 는 **SQLite 전용 문장**이다 — PostgreSQL 에는 없다.

    문자열로 박혀 있으면 이관 때 이 한 줄이 조용히 남아 터진다."""
    from core import program_lifecycle as pl

    seen: list[str] = []
    path = str(tmp_path / "pl.db")

    class Spy:
        def __init__(self, raw):
            self._raw = raw

        def execute(self, sql, *a, **k):
            seen.append(sql)
            #: 방언 상수를 그대로 흘려보내면 SQLite 가 모르는 문장에서 죽는다 —
            #: 주입된 문장을 «쓰는지» 만 보고 실제 실행은 SQLite 문법으로 바꿔 준다.
            if sql == "BEGIN DEFERRED":
                sql = "BEGIN"
            return self._raw.execute(sql, *a, **k)

        def __getattr__(self, name):
            return getattr(self._raw, name)

    life = pl.ProgramLifecycle(path, connect=lambda: Spy(dbmod.connect_sqlite(path)),
                               begin_immediate="BEGIN DEFERRED")
    folder = tmp_path / "library" / "rel_x"
    folder.mkdir(parents=True)
    (folder / "release.json").write_text('{"release_id": "rel_x"}', encoding="utf-8")
    from core import library_paths
    original = library_paths.library_dir
    library_paths.library_dir = lambda: str(tmp_path / "library")
    try:
        life.set_status("rel_x", pl.ACTIVE, "admin", "")
    finally:
        library_paths.library_dir = original

    assert "BEGIN DEFERRED" in seen, "주입한 트랜잭션 시작 문장을 쓰지 않았다"
    assert "BEGIN IMMEDIATE" not in seen, "SQLite 전용 문장이 그대로 박혀 있다"
