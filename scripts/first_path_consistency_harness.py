# -*- coding: utf-8 -*-
"""[P03.3 준비] 첫 경로 **동시 소비 · 대사 · 재시작** harness — backend 를 갈아 끼운다.

## 왜 harness 를 따로 두나

P03.3 이 요구하는 것은 「**서로 독립된 연결**에서 동시에 티켓을 소비하면 정확히 하나만
성공한다」이다. 같은 프로세스의 Python lock 으로 직렬화한 시험은 그 증거가 **아니다** —
운영에서는 인스턴스가 여럿이고 그런 lock 이 존재하지 않는다.

그래서 판정 코드를 **연결 팩토리만 받는 형태**로 떼어 둔다. 지금은 SQLite 로 돌려
harness 자신이 맞는지 보이고, PG 가 생기면 **같은 코드에 DSN 만** 끼운다.
PG 로 돌린 적이 없으면 그 결과는 언제나 `NOT_RUN` 이다.

## 무엇을 재나

    소비    동시 N 연결 → 성공 «정확히 1». 성공 행 수와 실패 결과를 함께 적는다
    거절    만료 · 다른 audience · 재소비 → 0건. **정상 대조**를 함께 돌린다
    대사    키 집합 · 건수 · 중요 필드가 그대로인가
    재시작  «새 연결» 로 다시 열어도 같은가 — 프로세스 메모리를 증거로 쓰지 않는다

⚠️ 이 harness 는 **쓴다.** 그래서 운영 `data/` 아래를 가리키면 **거절한다.**
⚠️ 접속 정보는 환경변수 `AFS_DB_DSN` 으로만 받는다. 출력하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OPERATIONAL = os.path.join(PROJECT_ROOT, "data")
_DSN_ENV = "AFS_DB_DSN"

#: 제품이 쓰는 바로 그 문장. **여기서 다시 쓰지 않는다** — 다시 쓰면 제품이 아닌 것을 잰다.
CONSUME_SQL = ("UPDATE auth_sse_ticket SET consumed_at=? "
               "WHERE token_hash=? AND consumed_at='' AND expires_at>=? "
               "AND audience=?")

FAR_FUTURE = "2999-01-01T00:00:00+00:00"
NOW = "2026-09-21T00:00:00+00:00"


class HarnessRefused(RuntimeError):
    """운영 자산을 가리켰거나 접속 정보가 없다."""


def guard_target(db_path: str) -> str:
    """⚠️ **운영 `data/` 를 가리키면 거절한다.**

    ★ 기준을 `PROJECT_ROOT` 로 고정한다 — 「지금 작업 디렉터리」로 판단하면 격리
      실행이 디렉터리를 바꿨을 때 판정이 **반대로** 뒤집힌다."""
    resolved = os.path.abspath(db_path)
    try:
        inside = os.path.commonpath([resolved, _OPERATIONAL]) == _OPERATIONAL
    except ValueError:
        #: 드라이브가 다르면 `commonpath` 가 터진다 — 그건 «운영 밖» 이라는 뜻이다.
        inside = False
    if inside:
        raise HarnessRefused(
            "운영 data/ 아래는 이 harness 의 대상이 아닙니다 — 격리 경로를 주십시오.")
    return resolved


# ── 합성 자료 ───────────────────────────────────────────────────────────
def seed(connect: Callable[[], Any], tickets: Sequence[Dict[str, str]]) -> None:
    """합성 티켓을 넣는다. **실제 사용자·실자료를 쓰지 않는다**(`.invalid` 계정)."""
    conn = connect()
    try:
        for t in tickets:
            conn.execute(
                "INSERT INTO auth_sse_ticket (token_hash, user_id, session_id, "
                "tenant_id, scope_node_id, entity_mode, context_version, audience, "
                "created_at, expires_at, consumed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (t["token_hash"], t.get("user_id", "probe@example.invalid"),
                 t.get("session_id", "s-probe"), t.get("tenant_id", "tenant_probe"),
                 t.get("scope_node_id", ""), t.get("entity_mode", "REAL"),
                 t.get("context_version", "v1"), t.get("audience", "sse"),
                 NOW, t.get("expires_at", FAR_FUTURE), ""))
        conn.commit()
    finally:
        conn.close()


def synthetic_tickets(count: int) -> List[Dict[str, str]]:
    rows = [{"token_hash": f"probe-{i:03d}"} for i in range(count)]
    rows.append({"token_hash": "probe-expired", "expires_at": "2000-01-01T00:00:00+00:00"})
    rows.append({"token_hash": "probe-other-audience", "audience": "not-sse"})
    return rows


# ── ① 동시 소비 — 독립 연결 ─────────────────────────────────────────────
def concurrent_consume(connect: Callable[[], Any], token_hash: str,
                       workers: int = 4) -> Dict[str, Any]:
    """★★ **연결을 스레드마다 새로 연다.** 하나를 공유하면 드라이버가 직렬화해 버려서
    「정확히 하나」가 «DB 덕분» 인지 «연결 덕분» 인지 구분할 수 없다."""
    wins: List[int] = []
    errors: List[str] = []
    lock = threading.Lock()
    gate = threading.Barrier(workers)

    def attempt() -> None:
        conn = connect()
        try:
            gate.wait()
            cur = conn.execute(CONSUME_SQL, (NOW, token_hash, NOW, "sse"))
            conn.commit()
            with lock:
                wins.append(cur.rowcount)
        except Exception as exc:  # noqa: BLE001 — 경쟁 실패도 결과다
            with lock:
                errors.append(type(exc).__name__)
        finally:
            conn.close()

    threads = [threading.Thread(target=attempt) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    succeeded = sum(1 for w in wins if w == 1)
    return {"workers": workers, "rowcounts": sorted(wins), "errors": errors,
            "succeeded": succeeded, "ok": succeeded == 1}


# ── ② 거절 + 정상 대조 ──────────────────────────────────────────────────
def rejection_matrix(connect: Callable[[], Any]) -> Dict[str, Any]:
    """⚠️ 거절만 보면 「늘 0」인 코드도 통과한다 — **정상 대조를 같이** 돌린다."""
    conn = connect()
    try:
        expired = conn.execute(CONSUME_SQL,
                               (NOW, "probe-expired", NOW, "sse")).rowcount
        wrong_audience = conn.execute(CONSUME_SQL,
                                      (NOW, "probe-other-audience", NOW, "sse")).rowcount
        healthy = conn.execute(CONSUME_SQL, (NOW, "probe-000", NOW, "sse")).rowcount
        reconsume = conn.execute(CONSUME_SQL, (NOW, "probe-000", NOW, "sse")).rowcount
        conn.commit()
    finally:
        conn.close()
    return {"expired": expired, "wrong_audience": wrong_audience,
            "healthy_control": healthy, "reconsume": reconsume,
            "ok": (expired, wrong_audience, healthy, reconsume) == (0, 0, 1, 0)}


# ── ③ 대사 + ④ 재시작 ──────────────────────────────────────────────────
def fingerprint(connect: Callable[[], Any]) -> Dict[str, Any]:
    """키 집합·건수·중요 필드. **새 연결로** 읽는다."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT token_hash, audience, expires_at, consumed_at "
            "FROM auth_sse_ticket ORDER BY token_hash").fetchall()
    finally:
        conn.close()
    keys = [str(r[0]) for r in rows]
    consumed = [str(r[0]) for r in rows if str(r[3])]
    return {"count": len(keys), "keys": keys, "consumed": consumed}


def restart_holds(connect: Callable[[], Any], before: Dict[str, Any]) -> Dict[str, Any]:
    """⚠️ 서비스의 in-memory 상태를 «유지» 의 증거로 쓰지 않는다 — 다시 열어 읽는다."""
    after = fingerprint(connect)
    return {"before_count": before["count"], "after_count": after["count"],
            "consumed_preserved": before["consumed"] == after["consumed"],
            "keys_preserved": before["keys"] == after["keys"],
            "ok": before == after}


# ── 실행 ────────────────────────────────────────────────────────────────
def sqlite_factory(db_path: str) -> Callable[[], sqlite3.Connection]:
    resolved = guard_target(db_path)

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(resolved, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn
    return factory


def postgres_factory() -> Callable[[], Any]:
    """⚠️ **한 번도 실행된 적이 없다.** 접속 정보 값은 출력하지 않는다."""
    dsn = os.environ.get(_DSN_ENV, "").strip()
    if not dsn:
        raise HarnessRefused(
            f"PostgreSQL 접속 정보가 없습니다 — 환경변수 {_DSN_ENV} 로 주십시오.")
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise HarnessRefused("PostgreSQL 드라이버(psycopg)가 없습니다.") from exc

    def factory():  # pragma: no cover - 실제 PG 없음
        from core.db import POSTGRES_DIALECT, TranslatingConnection
        return TranslatingConnection(psycopg.connect(dsn), POSTGRES_DIALECT)
    return factory


def run(connect: Callable[[], Any], workers: int = 4) -> Dict[str, Any]:
    seed(connect, synthetic_tickets(3))
    before = fingerprint(connect)
    concurrency = concurrent_consume(connect, "probe-001", workers)
    rejects = rejection_matrix(connect)
    after = fingerprint(connect)
    restart = restart_holds(connect, after)
    return {"seeded": before["count"],
            "concurrent_consume": concurrency,
            "rejection_matrix": rejects,
            "restart": restart,
            "ok": concurrency["ok"] and rejects["ok"] and restart["ok"]}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="첫 경로 동시 소비·대사·재시작 harness (합성 자료 전용)")
    ap.add_argument("--backend", required=True, choices=("sqlite", "postgres"))
    ap.add_argument("--sqlite-path", default="",
                    help="격리된 auth.db 경로 (backend=sqlite 일 때 필수)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    try:
        if args.backend == "sqlite":
            if not args.sqlite_path.strip():
                raise HarnessRefused("--sqlite-path 가 필요합니다.")
            connect = sqlite_factory(args.sqlite_path)
        else:
            connect = postgres_factory()
        result = run(connect, args.workers)
    except HarnessRefused as exc:
        print(json.dumps({"ok": False, "error": str(exc)},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    result["backend"] = args.backend
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
