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
