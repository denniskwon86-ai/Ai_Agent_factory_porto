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

-- ★★★ [I-4 2단계] 데이터셋을 릴리스에서 떼어 낸다.
--
-- 종전에는 `app_datasets.release_id` 가 곧 소속이었다. 그래서 **앱을 한 번 개정하면**
-- `find_dataset(새 release, 같은 이름)` 이 아무것도 못 찾고 새 데이터셋을 만들었다 —
-- 즉 **현업이 쌓은 레코드가 승계되지 않았다.** 화면에는 오류가 아니라 «데이터 0건» 이
-- 뜬다. 그것이 이 저장소에서 가장 조용한 종류의 사고다.
--
-- 이제 데이터셋은 **앱**에 속하고, 릴리스는 «어느 판을 쓰는가» 만 가리킨다(bindings).
-- `app_records.dataset_id` 는 릴리스를 넘어 그대로 살아남는다.

CREATE TABLE IF NOT EXISTS app_dataset_versions (
    version_id        TEXT PRIMARY KEY,
    dataset_id        TEXT NOT NULL,
    contract_revision INTEGER NOT NULL DEFAULT 0,
    schema_json       TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (dataset_id) REFERENCES app_datasets(dataset_id)
);
-- 한 데이터셋의 한 계약 판은 하나다 — 둘이면 어느 스키마로 검증할지 알 수 없다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_dataset_versions_rev
    ON app_dataset_versions(dataset_id, contract_revision);

CREATE TABLE IF NOT EXISTS app_release_dataset_bindings (
    binding_id      TEXT PRIMARY KEY,
    release_id      TEXT NOT NULL,
    dataset_id      TEXT NOT NULL,
    version_id      TEXT NOT NULL DEFAULT '',
    -- 쉼표로 이은 계약상 허용 행동(read,create,update,delete).
    -- ⚠️ 빈 문자열과 «행동 없음» 은 다른 뜻이므로 `contract_bound` 로 가른다.
    allowed_actions TEXT NOT NULL DEFAULT '',
    -- 0 = 계약 이전(레거시) 릴리스 · 1 = 계약이 이 데이터셋의 행동을 정했다
    contract_bound  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (dataset_id) REFERENCES app_datasets(dataset_id)
);
-- 한 릴리스가 같은 데이터셋을 두 번 가리키면 어느 판·어느 권한인지 알 수 없다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_bindings_release_dataset
    ON app_release_dataset_bindings(release_id, dataset_id);
CREATE INDEX IF NOT EXISTS idx_app_bindings_dataset
    ON app_release_dataset_bindings(dataset_id);
"""

#: 나중에 더한 열 — `CREATE TABLE IF NOT EXISTS` 로는 기존 표에 붙지 않는다.
#: (열 이름, 선언). ⚠️ `ALTER TABLE ADD COLUMN` 은 재실행 가능하지 않으므로 있는지 먼저 본다.
_ADDED_COLUMNS = (
    # 앱의 안정 식별자. 릴리스가 바뀌어도 같다 — 데이터셋의 실제 소속이다.
    ("app_datasets", "app_id", "TEXT NOT NULL DEFAULT ''"),
    # 계약상 불변 키. ⚠️ ACTIVE 이후 변경 불가 — 바꿀 수 있게 하면 「이름이 같은 다른 것」과
    # 「이름이 다른 같은 것」을 구분할 방법이 사라진다.
    ("app_datasets", "dataset_key", "TEXT NOT NULL DEFAULT ''"),
)


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
                self._add_missing_columns(conn)
                self._backfill_bindings(conn)
                conn.commit()
            finally:
                conn.close()
            self._ready = self.db_path

    @staticmethod
    def _add_missing_columns(conn: sqlite3.Connection) -> None:
        """나중에 더한 열을 붙인다. **있으면 건너뛴다**(재실행 가능해야 한다)."""
        for table, column, decl in _ADDED_COLUMNS:
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    @staticmethod
    def _backfill_bindings(conn: sqlite3.Connection) -> None:
        """기존 데이터셋을 새 구조로 **옮기지 않고 잇는다.**

        ★ 기존 행을 다시 쓰지 않는다 — `release_id` 열은 그대로 두고, 그 값으로 결속을
          만들어 준다. 그래야 마이그레이션이 실패해도 원본이 남는다.

        ⚠️⚠️ 만들어지는 결속은 **`contract_bound=0`**(계약 이전)이다. `1` 로 채우면
          「계약이 이 행동들만 허용했다」는 거짓 사실이 생기고, 그 뒤로 판정은 그 거짓을
          근거로 삼는다. 레거시는 **레거시라고 적는다.**"""
        conn.execute(
            "UPDATE app_datasets SET dataset_key=name WHERE dataset_key=''")
        conn.execute(
            "INSERT INTO app_release_dataset_bindings "
            "  (binding_id, release_id, dataset_id, version_id, allowed_actions, "
            "   contract_bound, created_at) "
            "SELECT 'bind_legacy_' || d.dataset_id, d.release_id, d.dataset_id, '', '', 0, "
            "       COALESCE(NULLIF(d.created_at, ''), '') "
            "  FROM app_datasets d "
            " WHERE d.release_id <> '' "
            "   AND NOT EXISTS (SELECT 1 FROM app_release_dataset_bindings b "
            "                    WHERE b.release_id = d.release_id "
            "                      AND b.dataset_id = d.dataset_id)")

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
