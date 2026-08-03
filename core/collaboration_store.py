"""[CL-1] 협업 워크플로우 운영 상태 저장소 — `data/collaboration.db`.

## 왜 새 DB 인가 (작업서 §5.1)

| 저장소 | 책임 |
|---|---|
| `data/collaboration.db`(여기) | 협업 워크플로우의 **변경 가능한 상태** SSOT |
| `data/workspace.db` | 조직 공유·전사 승격 |
| `data/decision_ledger.db` | **불변** 감사 이벤트 |

⚠️ 개인 전달을 `workspace_shares` 나 Promotion 상태에 합치지 않는다(§3-1,2). 네 가지는 다른
  것이다: **개인 전달**(사람에게 앱을 준다) · **조직 공유**(부서가 릴리스를 쓴다) ·
  **업무 배정**(할 일을 준다) · **전사 승격**(회사 표준이 된다). 하나의 enum 으로 만들면 권한
  판정이 뭉개지고, "이 사람이 왜 이걸 볼 수 있나"에 답할 수 없게 된다.

## 상태와 원장의 관계

운영 표는 상태를 **덮어쓴다**(PENDING → ACCEPTED). 그래서 "누가 언제 무엇을 수락했는가"는
덮어쓸 수 없는 곳(Decision Ledger)에도 남긴다. 상태만 있으면 지금 값은 알 수 있어도 경위는 모른다.

★ 원장 기록 실패를 숨기고 성공 응답하지 않는다(§5.2). 그러나 **원장 기록 전에 상태를 바꾸지도
  않는다** — 순서는 `상태 변경 → 원장 append`이고, 원장이 실패하면 호출자에게 올린다. 두 저장소의
  원자성은 작업서 §12 가 독립 검토 대상으로 지정했다(`.agents/TEAM_BOARD.md` 에 요청 기록).

## 마이그레이션 규약

`ensure_schema()` 는 **재실행 가능**하고 기존 데이터를 보존한다. import 시점에 실행하지 않는다 —
import 부작용으로 DB 를 만들면 테스트가 경로를 바꿔치기할 틈이 없고, 잘못된 작업 디렉터리에
파일이 생긴다(이 저장소가 겪은 유형).

LLM 0콜.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_PATH = os.path.join("data", "collaboration.db")

_DDL = """
CREATE TABLE IF NOT EXISTS app_deliveries (
    delivery_id        TEXT PRIMARY KEY,
    tenant_id          TEXT NOT NULL DEFAULT 'tenant_default',
    enterprise_scope_id TEXT NOT NULL DEFAULT '',
    release_id         TEXT NOT NULL,
    release_version    TEXT NOT NULL DEFAULT '',
    sender_user_id     TEXT NOT NULL,
    recipient_user_id  TEXT NOT NULL,
    purpose            TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'PENDING',
    expires_at         TEXT NOT NULL DEFAULT '',
    manifest_snapshot  TEXT NOT NULL DEFAULT '{}',
    manifest_fingerprint TEXT NOT NULL DEFAULT '',
    permission_snapshot TEXT NOT NULL DEFAULT '{}',
    idempotency_key    TEXT NOT NULL DEFAULT '',
    responded_at       TEXT NOT NULL DEFAULT '',
    response_note      TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
-- 같은 idempotency key 로 두 건이 생기지 않게 한다(§CL-BE-02). 빈 키는 제약에서 제외한다 —
-- 키 없는 호출까지 하나로 묶으면 서로 다른 전달이 충돌한다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_idem
    ON app_deliveries(tenant_id, sender_user_id, idempotency_key)
    WHERE idempotency_key <> '';
CREATE INDEX IF NOT EXISTS idx_delivery_recipient ON app_deliveries(recipient_user_id, status);
CREATE INDEX IF NOT EXISTS idx_delivery_sender ON app_deliveries(sender_user_id, status);

CREATE TABLE IF NOT EXISTS user_app_pocket (
    pocket_id          TEXT PRIMARY KEY,
    tenant_id          TEXT NOT NULL DEFAULT 'tenant_default',
    enterprise_scope_id TEXT NOT NULL DEFAULT '',
    user_id            TEXT NOT NULL,
    release_id         TEXT NOT NULL,
    delivery_id        TEXT NOT NULL,
    display_name       TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'ACTIVE',
    pinned             INTEGER NOT NULL DEFAULT 0,
    accepted_at        TEXT NOT NULL DEFAULT '',
    last_opened_at     TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
-- 재수락·중복 클릭에도 주머니가 하나만 생긴다(§CL-BE-02).
CREATE UNIQUE INDEX IF NOT EXISTS uq_pocket_unique
    ON user_app_pocket(user_id, release_id, delivery_id);
CREATE INDEX IF NOT EXISTS idx_pocket_user ON user_app_pocket(user_id, status);
"""


class CollaborationStoreError(ValueError):
    """저장소 규약 위반 — 4xx 로 전달한다."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(obj: Any) -> str:
    """정렬된 canonical JSON — snapshot hash 의 입력(§5.1)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:32]


class CollaborationStore:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ready = ""

    def _connect(self) -> sqlite3.Connection:
        """연결을 요청 단위로 만든다. **import 시점에 스키마를 만들지 않는다.**

        ⚠️ import 부작용으로 DB 를 만들면 테스트가 경로를 바꿔치기할 틈이 없고, 잘못된 작업
          디렉터리에 파일이 생긴다 — 이 저장소가 이미 겪은 유형이다(`db_path` 상대 경로 문제)."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        return conn

    def ensure_schema(self) -> None:
        """재실행 가능한 스키마 보장. 기존 데이터를 보존한다(§CL-BE-01).

        같은 경로에 대해 한 번만 실행하고 결과를 기억한다 — 매 요청 executescript 는 낭비다."""
        if self._ready == self.db_path:
            return
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_DDL)
                conn.commit()
            finally:
                conn.close()
            self._ready = self.db_path

    # ── 낮은 수준 접근 ────────────────────────────────────────────────────
    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        self.ensure_schema()
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        """쓰기 1건. 영향 행 수를 돌려준다."""
        self.ensure_schema()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def executemany_tx(self, statements: List[tuple]) -> None:
        """여러 쓰기를 **하나의 트랜잭션**으로. 중간 실패 시 전부 되돌린다.

        ★ 수락은 `app_deliveries` 상태 변경 + `user_app_pocket` 생성이 함께 성립해야 한다.
          하나만 남으면 "수락했는데 앱이 없다" 또는 "앱이 있는데 수락 기록이 없다"가 된다."""
        self.ensure_schema()
        with self._lock:
            conn = self._connect()
            try:
                for sql, params in statements:
                    conn.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()


collaboration_store = CollaborationStore()
