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
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

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
    version_id         TEXT PRIMARY KEY,
    dataset_id         TEXT NOT NULL,
    contract_revision  INTEGER NOT NULL DEFAULT 0,
    schema_json        TEXT NOT NULL DEFAULT '{}',
    -- ★★★ 이 판의 스키마 지문. **판은 불변**이고 이 값이 그것을 증명한다.
    schema_fingerprint TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT '',
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
    -- ★ 이 릴리스에서 앱이 부르는 이름을 **결속에 봉인**한다.
    --   데이터셋 마스터의 `name` 을 따라가게 두면, 이름을 고치는 경로가 하나라도 생기는 날
    --   이미 결속된 릴리스의 호출 이름이 함께 바뀐다.
    runtime_name    TEXT NOT NULL DEFAULT '',
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
    ("app_release_dataset_bindings", "runtime_name", "TEXT NOT NULL DEFAULT ''"),
    ("app_dataset_versions", "schema_fingerprint", "TEXT NOT NULL DEFAULT ''"),
)

#: ★★★ **유일성은 코드가 아니라 DB 가 지킨다.**
#:
#: ⚠️ 응용 계층의 「먼저 조회하고 없으면 INSERT」 는 워커가 둘이면 깨진다. 그리고 깨진
#:   결과는 **중복 행**이고, 중복이 생기면 `adopt_dataset` 같은 조회가 «둘 중 하나» 를
#:   고르게 된다 — 그 선택은 임의이고 조용하다.
#:
#: 백필 이전 데이터에 중복이 있으면 인덱스 생성이 실패한다. 그때 **조용히 넘어가지 않고**
#: `integrity_problems()` 로 드러낸다 — 유일성이 없는 채로 도는 것과, 없다는 사실을
#: 모르는 채 도는 것은 다르다.
_UNIQUE_INDEXES = (
    # 같은 앱 안에서 안정 키는 유일하다. 레거시(`app_id=''`)는 제외한다 —
    # ⚠️ 포함하면 앱 식별자가 없는 옛 데이터셋들이 서로 충돌해 마이그레이션이 통째로 멈춘다.
    ("idx_app_datasets_app_key",
     "CREATE UNIQUE INDEX IF NOT EXISTS idx_app_datasets_app_key "
     "ON app_datasets(tenant_id, app_id, dataset_key) WHERE app_id <> ''"),
    # 한 릴리스 안에서 런타임 이름은 유일하다 — 앱은 이름으로만 부르므로 둘이면 답할 수 없다.
    ("idx_app_bindings_release_name",
     "CREATE UNIQUE INDEX IF NOT EXISTS idx_app_bindings_release_name "
     "ON app_release_dataset_bindings(release_id, runtime_name) WHERE runtime_name <> ''"),
)


#: 판 지문 백필 훅. 도메인 계층(`core.app_data`)이 import 시점에 등록한다.
#: ⚠️ 저장소가 스키마 정규화 규칙을 알면 두 곳이 그것을 알게 된다 — 그러면 언젠가 갈라진다.
_VERSION_FP_HOOK = None


def set_version_fingerprint_hook(fn) -> None:
    global _VERSION_FP_HOOK
    _VERSION_FP_HOOK = fn


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
                #: ⚠️ 유일성 인덱스는 **백필 뒤**다. 먼저 걸면 옛 중복 때문에 백필이
                #:   시작도 못 하고, 그러면 데이터가 새 구조로 옮겨지지 않는다.
                self._integrity = self._add_unique_indexes(conn)
                conn.commit()
            finally:
                conn.close()
            self._ready = self.db_path
        #: ★ 판 지문 백필은 **스키마 정규화**를 알아야 하므로 도메인 계층이 준다
        #:   (`core.app_data` 가 등록한다). 여기서 하면 저장소가 도메인을 알게 된다.
        #: ⚠️ `_ready` 를 세운 **뒤**에 부른다 — 훅이 다시 `ensure_schema()` 를 부르므로
        #:   먼저 부르면 무한 재귀다.
        if _VERSION_FP_HOOK is not None:
            _VERSION_FP_HOOK(self)

    def integrity_problems(self) -> List[str]:
        """유일성 인덱스를 걸지 못한 이유들. **비어 있어야 정상**이다.

        ★ 이것을 조용히 삼키지 않는 이유: 인덱스가 없는 채로 도는 것과, 없다는 사실을
          모르는 채 도는 것은 다르다. 후자에서는 중복이 생겨도 아무도 모른다."""
        self.ensure_schema()
        return list(getattr(self, "_integrity", []))

    @staticmethod
    def _add_unique_indexes(conn: sqlite3.Connection) -> List[str]:
        problems: List[str] = []
        for name, ddl in _UNIQUE_INDEXES:
            try:
                conn.execute(ddl)
            except sqlite3.IntegrityError as e:
                problems.append(f"{name}: 기존 데이터에 중복이 있어 유일성을 걸지 못했습니다 ({e})")
            except sqlite3.OperationalError as e:      # pragma: no cover - 구형 SQLite
                problems.append(f"{name}: 인덱스를 만들 수 없습니다 ({e})")
        return problems

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
            "  (binding_id, release_id, dataset_id, version_id, runtime_name, allowed_actions, "
            "   contract_bound, created_at) "
            "SELECT 'bind_legacy_' || d.dataset_id, d.release_id, d.dataset_id, '', d.name, '', 0, "
            "       COALESCE(NULLIF(d.created_at, ''), '') "
            "  FROM app_datasets d "
            " WHERE d.release_id <> '' "
            "   AND NOT EXISTS (SELECT 1 FROM app_release_dataset_bindings b "
            "                    WHERE b.release_id = d.release_id "
            "                      AND b.dataset_id = d.dataset_id)")
        #: 이미 만들어져 있던 결속에 이름이 비어 있으면 채운다(열이 나중에 붙었으므로).
        conn.execute(
            "UPDATE app_release_dataset_bindings SET runtime_name = "
            "  (SELECT d.name FROM app_datasets d WHERE d.dataset_id = "
            "     app_release_dataset_bindings.dataset_id) "
            " WHERE runtime_name = ''")

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

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """읽기와 쓰기를 **하나의 원자 단위**로 묶는다.

        ★★★ `executemany_tx` 로는 부족한 이유: 데이터셋 생성·승계는 «조회한 뒤 그 결과에
          따라 쓴다» 이고, 그 사이가 벌어지면 두 가지가 깨진다 —

          · **고아 행**: 데이터셋만 만들어지고 결속이 실패하면, 아무 릴리스도 가리키지
            않는 데이터셋이 남는다. 그것은 이름으로 찾히지 않으므로 **다시 만들어진다.**
          · **경쟁**: 워커가 둘이면 「없다」를 동시에 보고 둘 다 INSERT 한다.

        ⚠️ `BEGIN IMMEDIATE` 다 — 쓰기 잠금을 **처음부터** 잡는다. 기본 지연 트랜잭션은
          읽기로 시작해 승격할 때 `SQLITE_BUSY` 가 나고, 그때는 이미 판단이 끝난 뒤다.

        ⚠️⚠️ **중첩 금지.** 같은 스레드에서 다시 열면 두 번째 연결이 자기 자신의 잠금을
          기다린다(`RLock` 은 재진입이지만 SQLite 잠금은 아니다). 트랜잭션 안에서는
          `_*_in_tx` 계열만 부른다."""
        self.ensure_schema()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @staticmethod
    def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """트랜잭션 안에서의 조회 — **바깥 연결을 쓰지 않는다**(그러면 원자성이 깨진다)."""
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    @classmethod
    def row(cls, conn: sqlite3.Connection, sql: str,
            params: tuple = ()) -> Optional[Dict[str, Any]]:
        got = cls.rows(conn, sql, params)
        return got[0] if got else None

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
