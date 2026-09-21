"""[P03.1] 명시 설치 명령 · runtime DDL 분리 — 첫 경로(인증·기업문맥).

여기서 잠그는 것은 **네 가지**다.

    ① 관리 모드에서 기동·첫 조회·재조회에 **DDL 0** — 소스를 읽어서가 아니라 «세어서»
    ② 미설치·불일치는 **식별 가능한 실패** — 빈 목록으로 숨기지 않는다
    ③ 설치 명령은 계획/적용을 나누고, 원자적이고, 재실행 가능하고, 실패를 성공으로 안 적는다
    ④ **기본(비관리) 동작은 그대로** — 새 DB 도 구 schema 보강 순서도 회귀 없음

⚠️ 격리 러너는 저장소 `conftest.py` 를 읽지 않는다. 전부 `tmp_path` 위에서 논다.
⚠️ 운영 `data/` 를 열지 않는다.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys

import pytest

from core.auth import AuthStore
from core.db import managed_schema as ms
from core.enterprise_context.repository import EcmRepository

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI_PATH = os.path.join(_ROOT, "scripts", "install_first_db_schema.py")
_spec = importlib.util.spec_from_file_location("_installer_under_test", _CLI_PATH)
installer = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(installer)


def _install(tmp_path) -> str:
    folder = str(tmp_path / "db")
    result = installer.install(installer.SQLITE, list(ms.KNOWN_STORES), folder)
    assert all(e["verified"] for e in result["entries"])
    return folder


def _exercise(folder: str, managed, log):
    """기동 → 첫 조회 → 재조회. **제품 경로 그대로** 부른다."""
    auth_path = os.path.join(folder, "auth.db")
    ecm_path = os.path.join(folder, "enterprise_context.db")
    store = AuthStore(db_path=auth_path,
                      connect=ms.recording_factory(auth_path, log), managed=managed)
    store._init()
    store.verify("nobody@example.invalid", "x")
    store.verify("nobody@example.invalid", "x")
    repo = EcmRepository(db_path=ecm_path,
                         connect=ms.recording_factory(ecm_path, log), managed=managed)
    repo._query("SELECT tenant_id FROM tenants LIMIT 1")
    repo._query("SELECT tenant_id FROM tenants LIMIT 1")


# ═══ ① runtime DDL 0 ════════════════════════════════════════════════════
def test_managed_mode_runs_no_ddl_on_start_first_query_or_repeat(tmp_path):
    """★★ 「DDL 을 안 돌린다」를 **소스를 읽어서** 주장하지 않는다 — 세어 본다."""
    folder = _install(tmp_path)
    log: list = []
    _exercise(folder, True, log)
    ddl = ms.ddl_statements(log)
    assert ddl == [], ddl
    assert log, "아무 SQL 도 안 돌았다면 경로를 지나지 않은 것이다"


def test_the_control_really_is_a_control(tmp_path):
    """★★ **대조군이 진짜 대조군인지 먼저 증명한다.**

    관리 모드를 끈 같은 경로가 DDL 을 «실제로» 돌려야, 위 시험의 0 이 의미가 있다.
    안 그러면 「원래 DDL 이 없던 경로」를 막았다고 착각한다."""
    folder = _install(tmp_path)
    log: list = []
    _exercise(folder, False, log)
    assert len(ms.ddl_statements(log)) > 0, "대조군에서도 DDL 이 0이면 계측이 눈먼 것이다"


# ═══ ② 미설치는 «식별 가능한 실패» ══════════════════════════════════════
def test_missing_schema_fails_instead_of_creating_one(tmp_path):
    """⚠️ 관리 모드에서 자동 CREATE/ALTER 0 · 다른 DB 생성 0."""
    ghost = str(tmp_path / "nowhere" / "auth.db")
    store = AuthStore(db_path=ghost, managed=True)
    with pytest.raises(ms.ManagedSchemaError):
        store._init()
    assert not os.path.exists(ghost), "관리 모드가 저장소를 만들어 버렸다"


def test_a_missing_schema_is_not_reported_as_an_empty_list(tmp_path):
    """★★ 여기가 제일 중요하다.

    ⚠️ 예전에는 `_query` 가 스키마 없는 DB 에서 `[]` 를 돌려줬다. 화면에는
      **「자료가 없음」**으로 보이고, 사람은 「아직 안 넣었나 보다」라고 읽는다.
      **아무도 설치 실패를 모른다.** 관리 모드에서는 소리 내어 실패해야 한다."""
    empty = str(tmp_path / "empty.db")
    sqlite3.connect(empty).close()          # 파일은 있고 표는 없다
    repo = EcmRepository(db_path=empty, managed=True)
    with pytest.raises(Exception) as caught:
        repo._query("SELECT tenant_id FROM tenants LIMIT 1")
    assert not isinstance(caught.value, SystemExit)


def test_the_query_path_recovery_ddl_is_closed_in_managed_mode(tmp_path):
    """⚠️ 생성자만 막으면 완료가 아니다 — `_ensure_tables()` 가 **조회 경로의 뒷문**이다."""
    empty = str(tmp_path / "empty.db")
    sqlite3.connect(empty).close()
    log: list = []
    repo = EcmRepository(db_path=empty,
                         connect=ms.recording_factory(empty, log), managed=True)
    assert repo._ensure_tables() is False
    assert ms.ddl_statements(log) == [], "복구 경로가 DDL 을 돌렸다"


def test_a_failed_verification_is_not_cached_as_ready(tmp_path):
    """⚠️ 실패를 캐시가 삼키면 두 번째 호출이 그냥 통과한다 — 설치 실패가 숨는다."""
    ghost = str(tmp_path / "nope.db")
    store = AuthStore(db_path=ghost, managed=True)
    for _ in range(2):
        with pytest.raises(ms.ManagedSchemaError):
            store._init()


def test_a_partially_matching_schema_still_fails(tmp_path):
    """⚠️ 표는 있는데 **열이 없으면** 첫 요청에서 죽는다. 그것도 미설치다."""
    path = str(tmp_path / "half.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE auth_credential(user_id TEXT)")
    conn.commit()
    conn.close()
    gaps = ms.missing_objects(path, ms.STORE_AUTH)
    assert any("auth_credential.salt" in g for g in gaps), gaps
    assert any("auth_session" in g for g in gaps), gaps


# ═══ 저장소별 선언 ══════════════════════════════════════════════════════
def test_nothing_is_managed_by_default():
    """★ 설정을 주지 않으면 **오늘 동작 그대로**다."""
    assert ms.managed_stores({}) == set()
    assert ms.is_managed(ms.STORE_AUTH, {}) is False


def test_stores_are_named_one_by_one_not_one_global_switch():
    """⚠️ 전역 스위치 하나면 아직 손도 안 댄 저장소까지 «준비됨» 으로 표시된다."""
    env = {"AFS_DB_MANAGED_STORES": "auth"}
    assert ms.is_managed(ms.STORE_AUTH, env) is True
    assert ms.is_managed(ms.STORE_ENTERPRISE_CONTEXT, env) is False


def test_an_unknown_store_name_is_refused():
    """⚠️ 조용히 무시하면 오타 하나로 관리 모드가 꺼지고 기동 DDL 이 되살아난다."""
    with pytest.raises(ValueError):
        ms.managed_stores({"AFS_DB_MANAGED_STORES": "auth,enterprise_contxt"})


# ═══ ③ 설치 명령 ════════════════════════════════════════════════════════
def test_plan_writes_nothing(tmp_path):
    folder = str(tmp_path / "planned")
    result = installer.plan(installer.SQLITE, list(ms.KNOWN_STORES), folder)
    assert result["wrote_anything"] is False
    assert not os.path.exists(folder), "계획만 봤는데 디렉터리가 생겼다"


def test_apply_then_reapply_is_safe(tmp_path):
    """★ 재실행 계약 — 전부 `IF NOT EXISTS` 라 두 번 돌려도 같다."""
    folder = _install(tmp_path)
    again = installer.install(installer.SQLITE, list(ms.KNOWN_STORES), folder)
    assert all(e["verified"] for e in again["entries"])


def test_install_is_atomic_when_a_statement_fails(tmp_path):
    """⚠️⚠️ `executescript()` 는 **먼저 COMMIT 을 낸다** — 중간 실패가 반쪽으로 남는다.

    그래서 한 트랜잭션으로 직접 감쌌다. 중간에 죽으면 **아무것도 남지 않아야** 한다."""
    path = str(tmp_path / "atomic.db")
    statements = ["CREATE TABLE ok_one(a TEXT)",
                  "CREATE TABLE ok_two(b TEXT)",
                  "CREATE TABLE 문법오류(("]
    with pytest.raises(sqlite3.Error):
        installer.apply_sqlite(path, statements)
    conn = sqlite3.connect(path)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert names == set(), f"반쪽 스키마가 남았다: {names}"


def test_a_failed_verification_is_not_reported_as_success(tmp_path, monkeypatch):
    """⚠️ 적용했다고 끝내지 않는다 — 읽어서 다시 보고, 어긋나면 실패다."""
    monkeypatch.setitem(ms.REQUIRED[ms.STORE_AUTH], "auth_credential",
                        ("user_id", "존재하지_않는_컬럼"))
    with pytest.raises(ms.SchemaInstallError):
        installer.install(installer.SQLITE, [ms.STORE_AUTH], str(tmp_path / "bad"))


def test_destructive_statements_are_refused(tmp_path, monkeypatch):
    """⚠️ 설치는 «지우는 일» 이 아니다."""
    monkeypatch.setattr(installer, "sqlite_ddl_for",
                        lambda store: ["DROP TABLE auth_credential"])
    with pytest.raises(ms.SchemaInstallError):
        installer.install(installer.SQLITE, [ms.STORE_AUTH], str(tmp_path / "x"))


def test_postgres_without_connection_info_fails(tmp_path, monkeypatch):
    """⚠️ 접속 정보는 **환경변수에서만** 받는다 — 인자로 받으면 셸 기록에 남는다."""
    monkeypatch.delenv("AFS_DB_DSN", raising=False)
    monkeypatch.setattr(installer, "postgres_sql", lambda: ["CREATE TABLE t(a TEXT)"])
    with pytest.raises(ms.SchemaInstallError) as caught:
        installer.install(installer.POSTGRES, [ms.STORE_AUTH])
    assert "AFS_DB_DSN" in str(caught.value)


def test_postgres_install_refuses_a_draft_that_misses_the_first_path(monkeypatch):
    """★★ 「표가 7개 있다」를 호환 증거로 쓰지 않는다 — 접속 «전에» 막는다.

    ⚠️ 처음엔 이 시험이 `gaps` 가 비어 있지 «않음» 을 단언했다. 그건 **오늘의 값**이고,
      초안을 고치는 순간 깨졌다. 단언할 것은 「지금 구멍이 있다」가 아니라
      **「구멍이 있으면 막는다」**는 불변식이다."""
    monkeypatch.setattr(installer, "postgres_schema_gaps",
                        lambda store: ["organization_nodes.status: 컬럼 없음"])
    monkeypatch.setattr(installer, "postgres_sql", lambda: ["CREATE TABLE t(a TEXT)"])
    monkeypatch.setenv("AFS_DB_DSN", "이-값은-쓰이지-않는다")
    with pytest.raises(ms.SchemaInstallError) as caught:
        installer.install(installer.POSTGRES, [ms.STORE_ENTERPRISE_CONTEXT])
    #: ⚠️ 접속 정보 «값» 이 메시지에 실리면 안 된다.
    assert "이-값은-쓰이지-않는다" not in str(caught.value)


def test_the_first_path_columns_come_from_the_canonical_ddl():
    """★ 음성 대조 — 요구 목록이 정본 DDL 과 어긋나면 그 자체가 결함이다.

    ⚠️ 실제로 `auth_session.session_id` 라고 «기억으로» 적었다가 설치 뒤 확인에서
      걸렸다(주키는 `token` 이다)."""
    from core.auth import _DDL as auth_ddl
    for column in ms.REQUIRED[ms.STORE_AUTH]["auth_session"]:
        assert column in auth_ddl, f"{column} 이 정본 auth DDL 에 없다"


def test_cli_refuses_an_unknown_backend(capsys):
    with pytest.raises(SystemExit):
        installer.main(["--backend", "mysql", "--plan"])
    capsys.readouterr()


def test_the_splitter_matches_what_executescript_builds(tmp_path):
    """★★ 제 파서를 믿지 않는다 — **엔진이 만든 것과 같은지** 대조한다.

    ⚠️ 처음에 정규식으로 `BEGIN`/`END` 깊이를 세었더니 18문장짜리 DDL 을 **2문장으로**
      잘라 먹었다. 그대로 설치했으면 「표가 없다」로 죽었다."""
    from core.enterprise_context.process_schema import DDL as process_ddl
    from core.enterprise_context.repository import _DDL as ecm_ddl

    def objects(path):
        conn = sqlite3.connect(path)
        try:
            return sorted(f"{r[0]}:{r[1]}" for r in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        finally:
            conn.close()

    split_db = str(tmp_path / "split.db")
    script_db = str(tmp_path / "script.db")
    installer.apply_sqlite(split_db, installer.split_statements(ecm_ddl)
                           + installer.split_statements(process_ddl))
    conn = sqlite3.connect(script_db)
    conn.executescript(ecm_ddl)
    conn.executescript(process_ddl)
    conn.commit()
    conn.close()
    assert objects(split_db) == objects(script_db)


# ═══ ④ 기본 모드 회귀 ═══════════════════════════════════════════════════
def test_default_mode_still_creates_a_new_database(tmp_path):
    """★ 기존 기본 SQLite 사용을 보존한다 — 새 DB 는 여전히 스스로 선다."""
    path = str(tmp_path / "fresh" / "auth.db")
    store = AuthStore(db_path=path, managed=False)
    store._init()
    assert ms.missing_objects(path, ms.STORE_AUTH) == []


def test_default_mode_still_upgrades_an_old_schema_in_the_right_order(tmp_path):
    """⚠️⚠️ 구 schema 보강 **순서** 회귀를 막는다.

    `CREATE TABLE IF NOT EXISTS` 는 이미 있는 표에 열을 넣어 주지 않는데, 같은 `_DDL`
    안에 그 새 열을 쓰는 **인덱스**가 있다. ALTER 가 뒤였을 때 실제로 인덱스 생성이
    `no such column: token_hash` 로 죽었고 `_init()` 이 매번 터져 **로그인이 500**
    이었다. 순서를 되돌리면 기존 DB 를 쓰는 모든 환경이 죽는다 — 새 DB 로 도는
    시험은 그것을 절대 못 본다. 그래서 «옛 모양» 을 일부러 만들어 둔다."""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE auth_session (token TEXT PRIMARY KEY, "
                 "user_id TEXT NOT NULL, created_at TEXT NOT NULL, "
                 "expires_at TEXT NOT NULL)")          # token_hash 가 없다
    conn.commit()
    conn.close()

    AuthStore(db_path=path, managed=False)._init()
    conn = sqlite3.connect(path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(auth_session)")}
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()
    assert "token_hash" in columns, "구 DB 에 열 보강이 안 됐다"
    assert "idx_session_hash" in indexes, "그 열을 쓰는 인덱스가 안 만들어졌다"

# ═══ ⑤ PG 초안이 첫 경로를 덮는가 ═══════════════════════════════════════
def test_the_postgres_draft_covers_every_canonical_first_path_column(tmp_path):
    """★★ 「표가 7개 있다」가 아니라 **정본 DDL 과 컬럼 단위로** 대조한다.

    ⚠️ 첫 판은 컬럼 14개가 없고 `enterprise_entities` 는 표 자체가 없었다. 내 `REQUIRED`
      목록도 «내가 고른 것» 이라 그것만 보면 또 놓친다 — 정본이 만든 실제 스키마를 읽어
      비교한다. SQLite 에 컬럼이 하나 늘고 PG 쪽을 안 고치면 여기서 걸린다."""
    folder = _install(tmp_path)
    pg_tables = installer._pg_defined_columns()
    missing = []
    for store in ms.KNOWN_STORES:
        conn = sqlite3.connect(os.path.join(folder, installer.SQLITE_FILENAME[store]))
        try:
            for table in ms.REQUIRED[store]:
                canonical = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
                have = pg_tables.get(table, [])
                missing += [f"{table}.{c}" for c in canonical if c not in have]
        finally:
            conn.close()
    assert missing == [], missing


def test_the_postgres_draft_keeps_sqlite_time_semantics():
    """⚠️ 시간 컬럼을 `TIMESTAMPTZ` 로 «먼저» 바꾸면 기존 SQL 이 그 자리에서 깨진다.

    제품은 «없음» 을 `''` 로 쓴다(`consumed_at=''`). 타입 전환은 이관 변환과 조건절을
    **함께** 고쳐야 하는 별건이라, 지금 초안은 SQLite 의미를 그대로 둔다."""
    body = open(installer._PG_SCHEMA, encoding="utf-8").read()
    assert "consumed_at     TEXT NOT NULL DEFAULT ''" in body
    assert "WHERE consumed_at = ''" in body, "부분 인덱스 조건이 타입 결정과 어긋난다"


# ═══ ⑥ P03.3 harness — 지금은 SQLite, PG 는 DSN 만 바꿔 끼운다 ══════════
_H_PATH = os.path.join(_ROOT, "scripts", "first_path_consistency_harness.py")
_hspec = importlib.util.spec_from_file_location("_harness_under_test", _H_PATH)
harness = importlib.util.module_from_spec(_hspec)
assert _hspec and _hspec.loader
_hspec.loader.exec_module(harness)


def test_the_harness_refuses_the_operational_data_dir():
    """⚠️⚠️ 이 harness 는 **쓴다.** 운영 `data/` 를 가리키면 거절해야 한다.

    ★ 기준을 `PROJECT_ROOT` 로 고정했다 — 「지금 작업 디렉터리」로 판단하면 격리 실행이
      디렉터리를 바꿨을 때 판정이 **반대로** 뒤집힌다."""
    with pytest.raises(harness.HarnessRefused):
        harness.guard_target(os.path.join(_ROOT, "data", "auth.db"))


def test_exactly_one_of_four_independent_connections_consumes_a_ticket(tmp_path):
    """★★ [P03.3 계약] **연결을 스레드마다 새로 연다.**

    하나를 공유하면 드라이버가 직렬화해서 「정확히 하나」가 «DB 덕분» 인지
    «연결 덕분» 인지 구분할 수 없다. 같은 Python lock 으로 직렬화한 시험은 증거가 아니다."""
    folder = _install(tmp_path)
    connect = harness.sqlite_factory(os.path.join(folder, "auth.db"))
    harness.seed(connect, harness.synthetic_tickets(2))
    result = harness.concurrent_consume(connect, "probe-000", workers=4)
    assert result["succeeded"] == 1, result
    assert sorted(result["rowcounts"]) == [0, 0, 0, 1], result


def test_rejections_come_with_a_positive_control(tmp_path):
    """⚠️ 거절만 보면 「늘 0」인 코드도 통과한다 — 정상 대조를 같이 돌린다."""
    folder = _install(tmp_path)
    connect = harness.sqlite_factory(os.path.join(folder, "auth.db"))
    harness.seed(connect, harness.synthetic_tickets(2))
    matrix = harness.rejection_matrix(connect)
    assert matrix["healthy_control"] == 1, "정상 경로가 막혔다면 나머지 0은 의미가 없다"
    assert (matrix["expired"], matrix["wrong_audience"], matrix["reconsume"]) == (0, 0, 0)


def test_a_reopened_connection_sees_the_same_rows(tmp_path):
    """⚠️ 서비스의 in-memory 상태를 «유지» 의 증거로 쓰지 않는다 — 다시 열어 읽는다."""
    folder = _install(tmp_path)
    connect = harness.sqlite_factory(os.path.join(folder, "auth.db"))
    harness.seed(connect, harness.synthetic_tickets(3))
    harness.concurrent_consume(connect, "probe-000", workers=2)
    before = harness.fingerprint(connect)
    assert harness.restart_holds(connect, before)["ok"] is True
    assert before["consumed"], "아무것도 소비되지 않았다면 대사가 비어 있다"


def test_the_harness_uses_the_product_consume_statement():
    """★ 소비 문장을 harness 가 «다시 쓰면» 제품이 아닌 것을 재게 된다."""
    product = open(os.path.join(_ROOT, "core", "auth.py"), encoding="utf-8").read()
    for fragment in ("SET consumed_at=?", "consumed_at='' AND expires_at>=?",
                     "AND audience=?"):
        assert fragment in harness.CONSUME_SQL, fragment
        assert fragment in product, f"제품 SQL 이 바뀌었다: {fragment}"
