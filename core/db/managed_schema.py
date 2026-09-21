# -*- coding: utf-8 -*-
"""[P03.1] **관리 스키마 모드** — 스키마를 만드는 주체를 기동 경로에서 떼어 낸다.

## 지금 무슨 일이 일어나고 있나

스키마를 만드는 주체가 **「먼저 쓰는 요청」**이다. `AuthStore._init` 은 ALTER 4건 뒤
`executescript(_DDL)` 을 돌리고, `EcmRepository` 는 **생성자에서** DDL 을 돌린 다음
조회가 실패하면 `_ensure_tables()` 로 **또 한 번** 돌린다. 그러고도 안 되면 `_query` 가
**빈 목록**을 돌려준다.

★★ 마지막이 제일 나쁘다 — **스키마가 없는데 화면에는 「자료가 없음」으로 보인다.**
  사람은 「아직 안 넣었나 보다」라고 읽고, 아무도 설치 실패를 모른다.

## 이 모듈이 세우는 계약

    관리 모드가 아니면   오늘과 한 글자도 다르지 않다 (기본값)
    관리 모드이면        기동·첫 조회·재조회에 **DDL 0**
                         미설치·불일치는 **식별 가능한 실패** (빈 목록 아님)
                         자동 CREATE/ALTER 0 · 다른 DB 로의 fallback 0

## ⚠️ 전역 스위치 하나로 «전부 준비됨» 이라고 말하지 않는다

13저장소 중 첫 경로 둘만 이관된 상태에서 전역 플래그를 켜면, 아직 손도 안 댄 저장소까지
「관리되고 있다」고 표시된다. 그래서 **저장소 이름을 하나씩 적는다.**

    AFS_DB_MANAGED_STORES=auth,enterprise_context

적히지 않은 저장소는 **오늘 동작 그대로** 간다. 이름을 모르면 거절한다 — 오타 하나로
「관리 중」이 조용히 「관리 안 함」이 되면 그 순간 기동 DDL 이 되살아난다.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

#: 이관 첫 슬라이스. **닫힌 목록**이다 — 여기 없는 이름은 거절한다.
STORE_AUTH = "auth"
STORE_ENTERPRISE_CONTEXT = "enterprise_context"
KNOWN_STORES = (STORE_AUTH, STORE_ENTERPRISE_CONTEXT)

_MANAGED_ENV = "AFS_DB_MANAGED_STORES"

#: 방언 이름 — `core.db` 와 같은 값을 쓴다(두 벌로 갈리지 않게).
SQLITE_BACKEND = "sqlite"
POSTGRES_BACKEND = "postgres"

#: DDL 로 세는 첫 낱말. 기동 경로에서 이것들이 보이면 계약 위반이다.
_DDL_VERBS = ("create", "alter", "drop", "truncate", "rename", "reindex", "vacuum")


class ManagedSchemaError(RuntimeError):
    """관리 모드인데 스키마가 없거나 요구와 다르다. **빈 결과로 접지 않는다.**"""


class SchemaInstallError(RuntimeError):
    """설치가 끝나지 못했다. 실패한 설치를 성공·ready 로 적지 않는다."""


# ── 어느 저장소가 «관리» 되는가 ─────────────────────────────────────────
def managed_stores(env: Optional[Mapping[str, str]] = None) -> Set[str]:
    """이름을 적은 저장소만 관리 모드다. 기본값은 **빈 집합**(= 오늘 동작)."""
    raw = (env if env is not None else os.environ).get(_MANAGED_ENV, "")
    names = [n.strip() for n in raw.split(",") if n.strip()]
    unknown = [n for n in names if n not in KNOWN_STORES]
    if unknown:
        #: ⚠️ 조용히 무시하면 오타 하나로 관리 모드가 꺼지고 기동 DDL 이 되살아난다.
        raise ValueError(
            f"모르는 저장소 이름입니다: {', '.join(unknown)} "
            f"(허용: {', '.join(KNOWN_STORES)})")
    return set(names)


def is_managed(store: str, env: Optional[Mapping[str, str]] = None) -> bool:
    return store in managed_stores(env)


# ── 첫 경로가 «실제로 쓰는» 표·컬럼 ─────────────────────────────────────
#: ⚠️ 「표가 7개 있다」를 호환 증거로 쓰지 않는다. 여기 적는 것은 로그인·문맥·티켓
#:   경로의 SQL 이 실제로 읽고 쓰는 컬럼이고, 정본 DDL 에서 확인한 이름이다.
REQUIRED: Dict[str, Dict[str, Tuple[str, ...]]] = {
    STORE_AUTH: {
        "auth_credential": ("user_id", "salt", "hash", "updated_at"),
        #: ⚠️ 주키는 `token` 이다 — 처음에 `session_id` 라고 «기억으로» 적었다가
        #:   설치 뒤 확인에서 걸렸다. 요구 목록은 정본 DDL 을 읽고 적는다.
        "auth_session": ("token", "user_id", "created_at", "expires_at",
                         "token_hash"),
        "auth_sse_ticket": ("token_hash", "user_id", "session_id", "tenant_id",
                            "scope_node_id", "entity_mode", "context_version",
                            "audience", "expires_at", "consumed_at"),
    },
    STORE_ENTERPRISE_CONTEXT: {
        "tenants": ("tenant_id",),
        "enterprise_entities": ("entity_id", "tenant_id", "entity_mode", "status"),
        "organization_nodes": ("node_id", "entity_id", "tenant_id", "node_type",
                               "status"),
        "organization_edges": ("from_node_id", "to_node_id", "relation_type",
                               "status"),
        "organization_node_code_aliases": ("node_id", "code", "tenant_id"),
    },
}


# ── 읽기 전용 확인 ──────────────────────────────────────────────────────
def _open_readonly(db_path: str) -> sqlite3.Connection:
    """⚠️ **없는 파일을 만들지 않는다.** 확인이 저장소를 만들면 그게 곧 사고다.

    ⚠️ URI 를 문자열로 이어 붙이지 않는다 — Windows 역슬래시 경로는 URI 가 아니고,
      경로에 `#` 가 있으면 거기서 잘린다."""
    return sqlite3.connect(Path(os.path.abspath(db_path)).as_uri() + "?mode=ro",
                           uri=True, timeout=5)


def missing_objects(db_path: str, store: str) -> List[str]:
    """요구한 표·컬럼 중 **없는 것**. 읽기만 한다.

    파일 자체가 없으면 `"<store>: 저장소 없음"` 한 줄을 돌려준다 — 연결해서 확인하면
    그 연결이 파일을 만들어 버린다."""
    required = REQUIRED.get(store)
    if required is None:
        raise ValueError(f"모르는 저장소 이름입니다: {store}")
    if not db_path or not os.path.isfile(db_path):
        return [f"{store}: 저장소 없음"]
    gaps: List[str] = []
    conn = _open_readonly(db_path)
    try:
        present = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for table, columns in required.items():
            if table not in present:
                gaps.append(f"{table}: 표 없음")
                continue
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for column in columns:
                if column not in have:
                    gaps.append(f"{table}.{column}: 컬럼 없음")
    finally:
        conn.close()
    return gaps


# ── ★★ [CR-1] 검사 대상을 «실제 연결» 에 결속한다 ─────────────────────
#
#   처음 판은 `assert_installed(self.db_path, ...)` 로 **파일을 직접 열어** 검사했다.
#   그런데 두 store 는 `connect=` 로 연결을 주입받는다 — 검사한 대상과 이후 SQL 을
#   실행하는 대상이 같다는 보장이 **어디에도 없었다.** SQLite 두 개만으로 재현된다:
#
#     주입 연결=설치된 A, db_path=없는 B  → 멀쩡한 연결을 써 보기도 전에 거절
#     db_path=설치된 A, 주입 연결=빈 B    → «준비 완료» 로 캐시된 뒤 첫 질의에서 터짐
#
#   ★ 둘째가 특히 나쁘다. 관문이 초록을 주고 실제 대상은 비어 있다.
#   그래서 **연결을 먼저 얻고, 그 연결 위에서** 확인한다. 쓰는 곳과 찾는 곳의 출처를
#   하나로 만든다.

def backend_of(conn, factory=None) -> str:
    """이 연결의 방언. **환경변수로 추측하지 않는다.**

    ★★ 순서: ① factory 가 «스스로 말한» 값 → ② 연결 객체의 «실제 형» →
      ③ 그래도 모르면 **거절**.
      `AFS_DB_BACKEND` 를 읽어 맞히면, 환경은 PG 인데 실제로는 SQLite 를 물고 있는
      조합에서 SQLite 전용 문장을 PG 로 보내거나 그 반대가 된다."""
    declared = str(getattr(factory, "backend", "") or "")
    if declared:
        return declared
    raw = getattr(conn, "_raw", conn)
    #: wrapper 가 겹쳐 있을 수 있다(계측용 등) — 끝까지 벗긴다.
    seen = 0
    while hasattr(raw, "_raw") and seen < 5:
        raw = raw._raw
        seen += 1
    if isinstance(raw, sqlite3.Connection):
        return SQLITE_BACKEND
    raise ManagedSchemaError(
        "연결의 방언을 알 수 없습니다 — 방언을 «스스로 말하는» factory 를 주십시오"
        "(core.db.sqlite_factory / postgres_factory).")


def target_identity(conn, backend: str = SQLITE_BACKEND) -> str:
    """이 연결이 «실제로» 무엇을 보고 있는가. 캐시 키이자 증거다.

    ⚠️ 못 알아내면 빈 문자열이다 — 그때는 「같은 대상」이라고 주장하지 않는다.

    ⚠️⚠️ **SQLite 가 아니면 아무 질의도 하지 않는다.** 처음 판은 backend 와 무관하게
      `PRAGMA database_list` 를 돌리고 예외를 삼켰다. PostgreSQL 에서 그 문장은 실패하고,
      **그 순간 트랜잭션이 실패 상태로 남아** 뒤따르는 정상 질의까지 전부 죽는다.
      「예외를 삼켰으니 안전하다」가 아니다 — 연결이 이미 오염된다.
      ~~★ 아직 «PG 대상 신원을 PG 읽기 질의로 구하는» 구현은 하지 않았다.~~ —
        **2026-09-21 [P03.2] 완료.** `current_database()/current_schema()` 로 구하고,
        실제 PG 에서 `afs_trial_local/app` 를 확인했다."""
    if backend == POSTGRES_BACKEND:
        #: ★ [2026-09-21 실측] 실제 PG 에서 `afs_trial_local/app` 를 돌려줬다.
        #:   PG 신원은 PG «읽기 질의» 로 구한다 —
        #:   SQLite 전용 문장을 던져 보고 실패로 알아내는 방식은 쓰지 않는다(트랜잭션이
        #:   실패 상태로 남는다).
        try:
            row = conn.execute(
                "SELECT current_database() AS db, current_schema() AS schema").fetchone()
        except Exception:  # noqa: BLE001
            return ""
        if row is None:
            return ""
        database, schema = _row_values(row, ("db", "schema"))
        return f"{database}/{schema}" if database else ""
    if backend != SQLITE_BACKEND:
        return ""
    try:
        for row in conn.execute("PRAGMA database_list").fetchall():
            if str(row[1]) == "main":
                return str(row[2] or ":memory:")
    except Exception:  # noqa: BLE001 — 읽지 못하면 «모른다» 로 둔다
        pass
    return ""


def _row_values(row, names: Sequence[str]) -> Tuple[str, ...]:
    """행에서 이름으로 값을 꺼낸다.

    ⚠️ 우리 PG factory 는 `dict_row` 를 붙이므로 행은 **매핑**이다. 튜플이 오면
      행 형식이 어긋난 것이고, 그걸 자리 번호로 «맞춰서» 넘기지 않는다 — 조용히
      엉뚱한 컬럼을 읽게 된다."""
    try:
        return tuple(str(row[name] if row[name] is not None else "") for name in names)
    except (TypeError, KeyError, IndexError) as exc:
        raise ManagedSchemaError(
            "행 형식이 기대와 다릅니다 — PostgreSQL 연결에 dict 행 형식이 "
            "붙어 있는지 확인하십시오(core.db.postgres_factory).") from exc


def _tables_and_columns(conn, backend: str) -> Dict[str, Set[str]]:
    """살아 있는 연결에서 표·컬럼을 읽는다. **읽기 질의뿐이다.**"""
    found: Dict[str, Set[str]] = {}
    if backend == POSTGRES_BACKEND:
        #: ★ [2026-09-21 실측] 실제 PG 에서 돌았다 — 설치 직후 확인과 runtime 조회가
        #:   이 가지로 `missing_objects_on(...) == []` 를 냈다.
        #: ⚠️ `for table, column in rows` 로 풀지 않는다 — `dict_row` 행을 그렇게 풀면
        #:   **키가 풀려** table/column 대신 컬럼 «이름» 이 들어온다. 이름으로 꺼낸다.
        rows = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()").fetchall()
        for row in rows:
            table, column = _row_values(row, ("table_name", "column_name"))
            found.setdefault(table, set()).add(column)
        return found
    names = [str(r[0]) for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for name in names:
        found[name] = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({name})")}
    return found


def missing_objects_on(conn, store: str, backend: str = "") -> List[str]:
    """★ **연결 위에서** 요구 표·컬럼을 확인한다. 파일을 따로 열지 않는다."""
    required = REQUIRED.get(store)
    if required is None:
        raise ValueError(f"모르는 저장소 이름입니다: {store}")
    if not backend:
        backend = backend_of(conn)
    try:
        present = _tables_and_columns(conn, backend)
    except Exception as exc:  # noqa: BLE001
        #: 확인 자체를 못 했으면 «통과» 가 아니다 — 닫는다.
        raise ManagedSchemaError(
            f"'{store}' 스키마를 확인하지 못했습니다: {type(exc).__name__}") from exc
    gaps: List[str] = []
    for table, columns in required.items():
        have = present.get(table)
        if have is None:
            gaps.append(f"{table}: 표 없음")
            continue
        gaps.extend(f"{table}.{c}: 컬럼 없음" for c in columns if c not in have)
    return gaps


def assert_installed_on(conn, store: str, backend: str = "") -> str:
    """관리 모드의 «진짜» 관문. 통과하면 확인한 대상 식별자를 돌려준다.

    ⚠️ 연결은 **닫지 않는다** — 부르는 쪽이 계속 쓴다. 실패했을 때 닫는 책임도
      부르는 쪽에 있다(연결을 받은 적이 없는 호출자에게 넘기지 않기 위해서다)."""
    if not backend:
        backend = backend_of(conn)
    gaps = missing_objects_on(conn, store, backend)
    if gaps:
        raise ManagedSchemaError(
            f"'{store}' 스키마가 설치돼 있지 않거나 요구와 다릅니다 "
            f"({len(gaps)}건: {', '.join(gaps[:4])}"
            f"{' …' if len(gaps) > 4 else ''}). "
            f"설치 명령으로 먼저 설치하십시오 — 자동으로 만들지 않습니다.")
    return target_identity(conn, backend)


def assert_installed(db_path: str, store: str) -> None:
    """관리 모드의 관문. **여기서 멈추는 것이 빈 목록보다 낫다.**

    ⚠️ 메시지에 경로를 싣지 않는다 — 실패 문구가 내부 구조를 알려 주는 창구가 된다."""
    gaps = missing_objects(db_path, store)
    if gaps:
        raise ManagedSchemaError(
            f"'{store}' 스키마가 설치돼 있지 않거나 요구와 다릅니다 "
            f"({len(gaps)}건: {', '.join(gaps[:4])}"
            f"{' …' if len(gaps) > 4 else ''}). "
            f"설치 명령으로 먼저 설치하십시오 — 자동으로 만들지 않습니다.")


# ── 계측: 기동 경로에서 DDL 이 도는지 «관측» 한다 ───────────────────────
def looks_like_ddl(sql: str) -> bool:
    head = (sql or "").lstrip().lstrip("(").lstrip().lower()
    return head.startswith(_DDL_VERBS)


class RecordingConnection:
    """실행된 SQL 을 그대로 적어 두는 얇은 껍데기.

    ★ 「DDL 을 안 돌린다」는 주장을 **소스를 읽어서** 하지 않는다. 실제로 store 를
      돌려 보고 **무엇이 실행됐는지 센다.** 소스 문자열 검사는 동작 증거가 아니다."""

    def __init__(self, raw, log: List[str]):
        self._raw = raw
        self._log = log

    def execute(self, sql, *args, **kwargs):
        self._log.append(sql)
        return self._raw.execute(sql, *args, **kwargs)

    def executemany(self, sql, *args, **kwargs):
        self._log.append(sql)
        return self._raw.executemany(sql, *args, **kwargs)

    def executescript(self, sql, *args, **kwargs):
        #: `executescript` 는 여러 문장을 한 번에 돌린다 — 통째로 적어 둔다.
        self._log.append(sql)
        return self._raw.executescript(sql, *args, **kwargs)

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, *exc):
        return self._raw.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._raw, name)


def ddl_statements(log: Iterable[str]) -> List[str]:
    """적힌 SQL 중 DDL 로 보이는 것. `executescript` 본문의 «각 줄» 도 본다."""
    found: List[str] = []
    for entry in log:
        for statement in str(entry).split(";"):
            if looks_like_ddl(statement):
                found.append(statement.strip()[:80])
    return found


def recording_factory(db_path: str, log: List[str]):
    """계측용 연결 팩토리. 평소 경로와 **같은 연결**을 쓰되 기록만 더한다."""
    def factory():
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return RecordingConnection(conn, log)
    return factory
