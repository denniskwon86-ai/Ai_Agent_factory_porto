# -*- coding: utf-8 -*-
"""[P03.1] **첫 경로 스키마 설치 명령** — 스키마를 만드는 주체를 기동 경로에서 뗀다.

## 왜 명령이 따로 있어야 하나

지금은 스키마를 만드는 주체가 **「먼저 쓰는 요청」**이다. `import` 만 해도 DDL 이 돈다
(`ecm_repository = EcmRepository()` 가 모듈 수준이고 생성자가 `_init_db()` 를 부른다).
그래서 ① 인스턴스가 둘 이상이면 같은 DDL 이 동시에 돌고 ② Blue/Green 에서 새 버전이
켜지는 순간 옛 버전이 모르는 열이 생기며 ③ 「스키마를 언제 누가 바꿨는가」에 답할 수 없다.

## 이 명령이 지키는 것

    계획과 적용을 나눈다   --plan 은 **아무것도 쓰지 않는다**
    원자적으로 넣는다      한 트랜잭션. 중간에 죽으면 **반쪽 스키마를 남기지 않는다**
    다시 돌려도 같다       전부 `IF NOT EXISTS` — 재실행이 안전하다
    실패를 성공으로 안 적는다  적용 뒤 **읽기로 다시 확인**하고, 어긋나면 0 이 아닌 코드
    부수지 않는다          DROP·TRUNCATE·자동 삭제는 이 명령의 범위가 아니다

⚠️ **접속 문자열·토큰을 출력하지 않는다.** PostgreSQL DSN 은 인자로 받지 않고 환경변수
  `AFS_DB_DSN` 에서만 읽는다 — 인자로 받으면 셸 기록과 프로세스 목록에 남는다.

사용:
    python scripts/install_first_db_schema.py --backend sqlite --sqlite-dir <dir> --plan
    python scripts/install_first_db_schema.py --backend sqlite --sqlite-dir <dir> --apply
    AFS_DB_DSN=... python scripts/install_first_db_schema.py --backend postgres --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db.managed_schema import (  # noqa: E402
    KNOWN_STORES, STORE_AUTH, STORE_ENTERPRISE_CONTEXT, SchemaInstallError,
    missing_objects,
)

SQLITE, POSTGRES = "sqlite", "postgres"
BACKENDS = (SQLITE, POSTGRES)

#: 저장소별 SQLite 파일 이름. 제품이 `data_path(...)` 로 여는 바로 그 이름이다.
SQLITE_FILENAME = {STORE_AUTH: "auth.db",
                   STORE_ENTERPRISE_CONTEXT: "enterprise_context.db"}

#: ★★ 인자를 생략했을 때의 범위. **업무 첫 경로 둘뿐**이다.
#:   ⚠️ `KNOWN_STORES` 를 기본값으로 쓰지 않는다. 목록에 저장소가 하나 추가되는 순간,
#:     `--store` 를 생략한 **기존 명령의 범위가 조용히 넓어진다** — 아무도 명령을
#:     바꾸지 않았는데. 인자를 빠뜨리는 쪽이 넓어지는 설계는 언젠가 사고가 된다.
DEFAULT_STORES = (STORE_AUTH, STORE_ENTERPRISE_CONTEXT)

_DSN_ENV = "AFS_DB_DSN"
_PG_SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "core", "db", "schema", "001_auth_and_context.sql")


# ── DDL 을 «문장 단위» 로 가른다 ────────────────────────────────────────
def split_statements(sql: str) -> List[str]:
    """`;` 로 자르되 **따옴표 안과 트리거 본문은 건드리지 않는다.**

    ⚠️ `process_schema.DDL` 에는 `CREATE TRIGGER … BEGIN … END;` 가 7개 있다.
      단순히 `;` 로 자르면 트리거가 조각나서 설치가 깨진다.

    ★★ 그래서 **직접 파서를 쓰지 않는다.** 처음에 정규식으로 `BEGIN`/`END` 깊이를
      세어 봤더니 18문장짜리 DDL 을 **2문장으로** 잘라 먹었고, 그대로 설치했으면
      「표가 없다」로 죽었다. `sqlite3.complete_statement()` 는 **엔진이 가진 판정기**라
      트리거도 따옴표도 이미 안다. 두 번째 파서를 만들지 않는다.

    ⚠️ PostgreSQL SQL 에도 이 판정기를 쓴다 — 어휘 수준 판정이라 평범한 DDL 에는
      맞지만, PG 전용 문법(`$$ … $$` 함수 본문 등)이 들어오면 맞지 않을 수 있다.
      지금 첫 슬라이스 스키마에는 그런 문장이 없다."""
    statements: List[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    tail = buffer.strip()
    if tail:
        statements.append(tail)
    #: 주석만 있는 조각은 버린다 — 실행할 것이 없다.
    return [s for s in statements
            if any(l.strip() and not l.strip().startswith("--")
                   for l in s.splitlines())]


def _forbidden(statements: Sequence[str]) -> List[str]:
    """⚠️ 파괴적 문장은 이 명령으로 실행하지 않는다 — 설치는 «지우는 일» 이 아니다."""
    bad = []
    for statement in statements:
        head = statement.lstrip().upper()
        if head.startswith(("DROP ", "TRUNCATE ", "DELETE ")):
            bad.append(statement[:60])
    return bad


# ── 설치할 SQL 을 «기존 경로에서» 가져온다 ──────────────────────────────
_MANAGED_ENV = "AFS_DB_MANAGED_STORES"


@contextmanager
def _import_guard():
    """제품 모듈을 import 하는 **그 순간에만** 관리 모드를 켠다.

    ⚠️⚠️ `ecm_repository = EcmRepository()` 가 모듈 수준이라, 설치 SQL 을 가져오려고
      그 모듈을 import 하는 순간 생성자가 `_init_db()` 를 돌린다 — 「계획만 보겠다」는
      요청에도 운영 스키마가 바뀐다. 그래서 import 를 이 문 안에서 한다.

    ⚠️ 그리고 **반드시 되돌린다.** 처음에는 모듈 맨 위에서 `os.environ[...] = ...` 로
      켜 뒀는데, 이 파일을 라이브러리로 import 한 **pytest 세션 전체**가 관리 모드가
      되어 무관한 시험 22건이 무너졌다. 라이브러리 import 는 전역을 바꾸면 안 된다."""
    previous = os.environ.get(_MANAGED_ENV)
    os.environ[_MANAGED_ENV] = "auth,enterprise_context"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_MANAGED_ENV, None)
        else:
            os.environ[_MANAGED_ENV] = previous


def sqlite_ddl_for(store: str) -> List[str]:
    """기존 설치 SQL 을 그대로 재사용한다. **두 벌을 만들지 않는다.**"""
    if store == STORE_AUTH:
        with _import_guard():
            from core.auth import _DDL as auth_ddl
        return split_statements(auth_ddl)
    if store == STORE_ENTERPRISE_CONTEXT:
        with _import_guard():
            from core.enterprise_context.repository import _DDL as ecm_ddl
            from core.enterprise_context.process_schema import DDL as process_ddl
        return split_statements(ecm_ddl) + split_statements(process_ddl)
    raise ValueError(f"모르는 저장소 이름입니다: {store}")


#: 트랜잭션은 **드라이버가** 연다. 파일에 적힌 것을 문장으로 또 보내면 안 된다.
_TRANSACTION_CONTROL = ("BEGIN", "COMMIT", "ROLLBACK", "END", "START TRANSACTION")


def _is_transaction_control(statement: str) -> bool:
    body = chr(10).join(l for l in statement.splitlines()
                        if l.strip() and not l.strip().startswith("--")).strip()
    return body.rstrip(";").strip().upper() in _TRANSACTION_CONTROL


def postgres_sql() -> List[str]:
    """설치 SQL 을 문장으로 나눈다. **트랜잭션 제어 문장은 뺀다.**

    ⚠️⚠️ 파일은 사람이 읽기 좋게 `BEGIN; … COMMIT;` 으로 감싸 두었다. 그런데 그것을
      문장 단위로 잘라 psycopg 에 그대로 보내면, 드라이버가 **이미 연** 트랜잭션 안에서
      `COMMIT` 이 «먼저» 터진다 — 뒤 문장들이 트랜잭션 밖으로 나가고, 중간에 실패해도
      앞부분이 남는다. 「한 번에 들어가거나 아무것도 안 들어간다」가 그 자리에서 깨진다.
      ★ 실제 PG 에 붙이기 «전에» 잡았다. 트랜잭션 경계는 드라이버 하나만 잡는다."""
    if not os.path.isfile(_PG_SCHEMA):
        raise SchemaInstallError("PostgreSQL 설치 스키마 파일이 없습니다.")
    with open(_PG_SCHEMA, "r", encoding="utf-8") as handle:
        statements = split_statements(handle.read())
    return [s for s in statements if not _is_transaction_control(s)]


def _pg_defined_columns() -> Dict[str, List[str]]:
    """PG 초안이 «정의한» 표·컬럼을 읽는다. 접속 없이 파일만 본다."""
    with open(_PG_SCHEMA, "r", encoding="utf-8") as handle:
        body = handle.read()
    tables: Dict[str, List[str]] = {}
    for match in re.finditer(
            r"CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)\s*\((.*?)\n\);",
            body, re.S | re.I):
        columns = []
        for line in match.group(2).splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            if re.match(r"(?i)(primary|unique|foreign|check|constraint)\b", line):
                continue
            columns.append(line.split()[0].strip('"'))
        tables[match.group(1)] = columns
    return tables


def postgres_schema_gaps(store: str) -> List[str]:
    """★★ **「표가 7개 있다」를 호환 증거로 쓰지 않는다.**

    첫 경로가 «실제로 읽고 쓰는» 표·컬럼이 PG 초안에 있는지 대조한다.
    실측(2026-09-21): 컬럼 14개가 없고 `enterprise_entities` 는 표 자체가 없다 —
    이 초안으로 설치하면 로그인·문맥 조회가 **첫 요청에서** 죽는다."""
    from core.db.managed_schema import REQUIRED
    defined = _pg_defined_columns()
    gaps: List[str] = []
    for table, columns in REQUIRED[store].items():
        have = defined.get(table)
        if have is None:
            gaps.append(f"{table}: 표 없음")
            continue
        gaps.extend(f"{table}.{c}: 컬럼 없음" for c in columns if c not in have)
    return gaps


# ── 적용 ────────────────────────────────────────────────────────────────
def apply_sqlite(db_path: str, statements: Sequence[str]) -> int:
    """**한 트랜잭션**으로 넣는다. 중간에 죽으면 반쪽 스키마를 남기지 않는다.

    ⚠️ `executescript()` 를 쓰지 않는 이유: 그것은 **먼저 COMMIT 을 내보낸다.**
      그러면 중간 실패가 반쪽 적용으로 남고, 다음 기동이 그 위에서 또 돈다.
      SQLite 는 DDL 도 트랜잭션 안에서 돌릴 수 있으므로 직접 감싼다."""
    folder = os.path.dirname(db_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.isolation_level = None
        conn.execute("BEGIN")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return len(statements)


def apply_postgres(store: str, statements: Sequence[str], connect=None) -> int:
    """적용 **그리고 같은 연결에서 확인**.

    ★ [2026-09-21 실측] 격리 로컬 PG 16.15 에 `afs_installer` 역할로 실제 적용했다 —
      store 마다 22문장, commit 전 확인 통과(`verified: true`).

    ★★ 예전 판은 문장을 던지고 `verified: false` 를 넣으면서도 `ok: true` / exit0 을
      냈다. 「설치했는데 확인은 안 했다」를 성공으로 보고한 것이다 — 그 거짓 초록 위에서
      다음 단계가 시작된다. 이제 **확인 전에는 성공이라고 하지 않는다.**

    ⚠️ 연결은 방언을 «스스로 말하는» factory 에서 얻는다. 환경변수로 추측하지 않고,
      행 형식(dict)도 그 factory 가 고정한다. 접속 정보 «값» 은 어떤 메시지에도 없다."""
    from core.db.managed_schema import POSTGRES_BACKEND, missing_objects_on
    if connect is None:
        from core.db import postgres_factory
        connect = postgres_factory()
    conn = connect()
    try:
        for statement in statements:
            conn.execute(statement)
        #: ★★ 확인을 **commit 전에** 한다. PostgreSQL 은 DDL 도 트랜잭션 안에서 돌고
        #:   같은 트랜잭션에서는 방금 만든 것이 보인다 — 확인이 실패하면 되돌려
        #:   **아무것도 남기지 않는다.** (SQLite 쪽은 `executescript` 계열 제약 때문에
        #:   확인이 commit 뒤라 행이 남을 수 있다고 이미 적어 두었다. PG 는 더 강하다.)
        gaps = missing_objects_on(conn, store, POSTGRES_BACKEND)
        if gaps:
            conn.rollback()
            raise SchemaInstallError(
                f"'{store}' PG 설치 뒤 확인에서 {len(gaps)}건이 비었습니다: "
                f"{', '.join(gaps[:4])}")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001 — 되돌리기 실패를 원래 오류로 덮지 않는다
            pass
        raise
    finally:
        conn.close()
    return len(statements)


# ── 계획 / 실행 ─────────────────────────────────────────────────────────
def plan(backend: str, stores: Sequence[str],
         sqlite_dir: str = "") -> Dict[str, object]:
    """**아무것도 쓰지 않는다.** 무엇이 어디에 들어갈지만 답한다."""
    entries = []
    for store in stores:
        if backend == SQLITE:
            statements = sqlite_ddl_for(store)
            target = os.path.join(sqlite_dir, SQLITE_FILENAME[store])
            exists = os.path.isfile(target)
            entries.append({"store": store, "target": target,
                            "target_exists": exists,
                            "statements": len(statements),
                            "gaps_now": missing_objects(target, store)})
        else:
            statements = postgres_sql()
            #: ⚠️ DSN 은 적지 않는다. 「환경변수에서 읽는다」까지만 말한다.
            entries.append({"store": store, "target": f"postgres(<{_DSN_ENV}>)",
                            "target_exists": None,
                            "statements": len(statements),
                            "gaps_now": ["실제 PG 미실행 — NOT_RUN"]})
    return {"backend": backend, "mode": "plan", "wrote_anything": False,
            "entries": entries}


def install(backend: str, stores: Sequence[str],
            sqlite_dir: str = "") -> Dict[str, object]:
    """적용하고 **읽기로 다시 확인**한다. 확인이 안 되면 성공이라고 하지 않는다."""
    entries = []
    for store in stores:
        statements = (sqlite_ddl_for(store) if backend == SQLITE
                      else postgres_sql())
        blocked = _forbidden(statements)
        if blocked:
            raise SchemaInstallError(
                f"설치 SQL 에 파괴적 문장이 있습니다: {', '.join(blocked)}")
        if backend == SQLITE:
            target = os.path.join(sqlite_dir, SQLITE_FILENAME[store])
            count = apply_sqlite(target, statements)
            #: ★ 적용했다고 끝내지 않는다 — **읽어서** 요구 표·컬럼을 다시 본다.
            gaps = missing_objects(target, store)
            if gaps:
                raise SchemaInstallError(
                    f"'{store}' 설치 뒤 확인에서 {len(gaps)}건이 비었습니다: "
                    f"{', '.join(gaps[:4])}")
            entries.append({"store": store, "target": target,
                            "applied_statements": count, "verified": True})
        else:
            if not os.environ.get(_DSN_ENV, "").strip():
                raise SchemaInstallError(
                    f"PostgreSQL 접속 정보가 없습니다 — 환경변수 {_DSN_ENV} 로 "
                    f"주십시오(인자로 받지 않습니다).")
            #: ★ 접속하기 «전에» 초안을 본다 — 안 맞는 초안을 깔고 「설치 성공」이라고
            #:   적으면 그 거짓 초록 위에서 다음 단계가 시작된다.
            gaps = postgres_schema_gaps(store)
            if gaps:
                raise SchemaInstallError(
                    f"'{store}' PG 설치 스키마가 첫 경로 요구를 충족하지 않습니다 "
                    f"({len(gaps)}건: {', '.join(gaps[:4])}"
                    f"{' …' if len(gaps) > 4 else ''}). 초안을 먼저 맞추십시오.")
            #: `dsn` 값은 여기서도 쓰지 않는다 — factory 가 환경에서 직접 읽는다.
            count = apply_postgres(store, statements)
            entries.append({"store": store, "target": f"postgres(<{_DSN_ENV}>)",
                            "applied_statements": count,
                            #: ★ 여기까지 왔다는 것은 «확인을 통과했다» 는 뜻이다.
                            #:   확인이 실패하면 위에서 예외가 나 이 줄에 닿지 못한다.
                            "verified": True,
                            "note": "실제 PG 실행 이력 없음 — 이 값은 «이번 실행에서» "
                                    "확인했다는 뜻이다"})
    return {"backend": backend, "mode": "apply", "entries": entries}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="첫 경로(인증·기업문맥) 스키마를 «명시적으로» 설치한다.")
    ap.add_argument("--backend", required=True, choices=BACKENDS,
                    help="설치 대상 backend")
    ap.add_argument("--store", action="append", choices=list(KNOWN_STORES),
                    help="설치할 저장소(여러 번). 생략하면 첫 슬라이스 전부")
    ap.add_argument("--sqlite-dir", default="",
                    help="SQLite 파일을 둘 디렉터리 (backend=sqlite 일 때 필수)")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true",
                       help="무엇을 할지만 본다 — **쓰지 않는다**")
    group.add_argument("--apply", action="store_true", help="실제로 설치한다")
    args = ap.parse_args(argv)

    #: ⚠️ 기본 범위는 **업무 첫 경로 둘**로 못박는다(§DEFAULT_STORES).
    stores = args.store or list(DEFAULT_STORES)
    if args.backend == SQLITE and not args.sqlite_dir.strip():
        print("backend=sqlite 에는 --sqlite-dir 가 필요합니다.", file=sys.stderr)
        return 2

    try:
        result = (plan(args.backend, stores, args.sqlite_dir) if args.plan
                  else install(args.backend, stores, args.sqlite_dir))
    except (SchemaInstallError, ValueError) as exc:
        #: ⚠️ 실패를 성공·ready 로 적지 않는다. 메시지에 접속 정보를 싣지 않는다.
        print(json.dumps({"ok": False, "error": str(exc)},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    result["ok"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
