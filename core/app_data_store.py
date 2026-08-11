"""[트랙 I-1] 생성 앱 데이터 평면 저장소 — `data/app_data.db`.

## 왜 새 DB 인가

| 저장소 | 책임 |
|---|---|
| `data/app_data.db`(여기) | **생성된 앱이 쌓는 업무 데이터** |
| `data/collaboration.db` | 앱을 누구에게 전달했는가(운영 상태) |
| `data/workspace.db` | 조직 공유·전사 승격 |
| `data/decision_ledger.db` | **불변** 감사 이벤트 |

⚠️ 업무 데이터를 위 셋 중 어디에도 섞지 않는다. 협업 상태나 감사 이벤트와 같은 DB 에 두면
  **레코드 수십만 건이 운영 표를 밀어내고**, 백업·보존 정책이 서로 다른 것을 한 파일에 묶게 된다
  (감사 원장은 영구 보존, 업무 데이터는 앱 수명주기를 따른다).

## 이 저장소가 존재하는 이유 (`docs/design_app_data_plane_2026-08-08.md` §2)

`core/app_manifest.py`(CL-0)가 생성 앱에 대해 **자체 로그인·자체 사용자 저장소를 금지**하고
`auth_mode=PLATFORM_INHERITED` 를 고정값으로 못 박았다. 그것은 «앱의 데이터는 플랫폼이
관리한다» 는 선언인데, **그 선언을 이행할 저장소가 없었다.** 이 파일이 그 자리다.

## 마이그레이션 규약

`ensure_schema()` 는 **재실행 가능**하고 기존 데이터를 보존한다. import 시점에 실행하지 않는다 —
import 부작용으로 DB 를 만들면 테스트가 경로를 바꿔치기할 틈이 없고, 잘못된 작업 디렉터리에
파일이 생긴다(이 저장소가 겪은 유형).

LLM 0콜.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from core.paths import data_path

_DB_PATH = data_path("app_data.db")

_DDL = """
CREATE TABLE IF NOT EXISTS app_datasets (
    dataset_id      TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    release_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    schema_json     TEXT NOT NULL DEFAULT '{}',
    app_class       TEXT NOT NULL DEFAULT '',
    owner_dept_id   TEXT NOT NULL DEFAULT '',
    scope_node_id   TEXT NOT NULL DEFAULT '',
    created_by      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT '',
    retired_at      TEXT NOT NULL DEFAULT ''
);
-- 같은 앱 안에서 데이터셋 이름은 유일하다. 앱은 이름으로만 부르므로(§7 규칙 4)
-- 중복이 생기면 어느 것을 주어야 할지 판정할 수 없다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_datasets_release_name
    ON app_datasets(release_id, name);
CREATE INDEX IF NOT EXISTS idx_app_datasets_dept ON app_datasets(owner_dept_id);

CREATE TABLE IF NOT EXISTS app_records (
    record_id       TEXT PRIMARY KEY,
    dataset_id      TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT '',
    updated_by      TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT '',
    deleted_by      TEXT NOT NULL DEFAULT '',
    deleted_at      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (dataset_id) REFERENCES app_datasets(dataset_id)
);
-- 조회는 거의 전부 «이 데이터셋의 살아 있는 레코드» 다.
CREATE INDEX IF NOT EXISTS idx_app_records_dataset
    ON app_records(dataset_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_app_records_creator ON app_records(created_by);
"""


class AppDataStore:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ready = ""

    def _connect(self) -> sqlite3.Connection:
        """연결을 요청 단위로 만든다. **import 시점에 스키마를 만들지 않는다.**"""
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
        """재실행 가능한 스키마 보장. 기존 데이터를 보존한다.

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

    def scalar(self, sql: str, params: tuple = ()) -> Any:
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

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
        """여러 쓰기를 **하나의 트랜잭션**으로. 중간 실패 시 전부 되돌린다."""
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


app_data_store = AppDataStore()
