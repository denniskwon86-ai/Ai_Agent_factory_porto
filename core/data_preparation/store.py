"""[BDR-201] 저장 계층 — DDL·멱등 마이그레이션·ACTIVE 유일성.

## 이 파일이 지키는 것 하나

★★★ **한 (Kit Instance, Dataset Contract) 당 ACTIVE 는 하나뿐이다.** 그것을 코드가
  아니라 **DB 부분 유일 인덱스**로 보장한다.

⚠️⚠️ 애플리케이션 코드로만 막으면 「먼저 종료하고 새로 활성화」 사이의 틈에서 둘이
  된다. 그리고 둘이 된 순간 「이 데이터셋은 어디서 오는가」에 답이 두 개가 되는데,
  그 상태는 **오류를 내지 않는다** — 조회하는 쪽이 아무거나 하나를 집을 뿐이다.

⚠️ 활성 교체는 **한 트랜잭션**이다. 기존 ACTIVE 종료와 신규 ACTIVE 를 나누면 그 사이에
  「활성이 하나도 없는」 순간이 생기고, 그때 들어온 요청은 「원천이 없다」를 본다.
"""
import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.data_preparation import models as m
from core.paths import data_path

_DB_PATH = data_path("data_preparation.db")

_DDL = """
CREATE TABLE IF NOT EXISTS kit_registry_versions (
    kit_version_id  TEXT PRIMARY KEY,
    kit_id          TEXT NOT NULL,
    version         TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT '',
    mode            TEXT NOT NULL DEFAULT 'DEMO/SYNTHETIC',
    source_path     TEXT NOT NULL DEFAULT '',
    fingerprint     TEXT NOT NULL,
    profile_json    TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (kit_id, version)
);

CREATE TABLE IF NOT EXISTS kit_instances (
    instance_id     TEXT PRIMARY KEY,
    kit_id          TEXT NOT NULL,
    version         TEXT NOT NULL,
    kit_fingerprint TEXT NOT NULL DEFAULT '',
    tenant_id       TEXT NOT NULL,
    scope_node_id   TEXT NOT NULL,
    entity_mode     TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',
    created_by      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kit_inst_ctx
    ON kit_instances(tenant_id, entity_mode, scope_node_id);

CREATE TABLE IF NOT EXISTS source_bindings (
    binding_id      TEXT PRIMARY KEY,
    instance_id     TEXT NOT NULL,
    dataset_contract_key TEXT NOT NULL,
    provider        TEXT NOT NULL,
    config_json     TEXT NOT NULL DEFAULT '{}',
    fingerprint     TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'DRAFT',
    tenant_id       TEXT NOT NULL,
    scope_node_id   TEXT NOT NULL,
    entity_mode     TEXT NOT NULL,
    blocked_reason  TEXT NOT NULL DEFAULT '',
    created_by      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    retired_at      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_binding_instance
    ON source_bindings(instance_id, dataset_contract_key, state);

-- ★★★ 한 (인스턴스, 데이터셋 계약) 당 ACTIVE 하나. **DB 가 보장한다.**
--   ⚠️ 부분 유일 인덱스여야 한다 — 전체 유일로 하면 후보(DRAFT·VALIDATED)를
--     여러 개 둘 수 없고, 후보를 못 두면 «비교해 고르는» 일 자체가 불가능해진다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_binding_active
    ON source_bindings(instance_id, dataset_contract_key)
    WHERE state = 'ACTIVE';

CREATE TABLE IF NOT EXISTS dataset_snapshots (
    snapshot_id     TEXT PRIMARY KEY,
    binding_id      TEXT NOT NULL,
    instance_id     TEXT NOT NULL,
    dataset_contract_key TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'RAW',
    -- ★★★ 원본은 **불변 RAW 영역**에 두고 여기에는 경로와 지문만 남긴다.
    --   ⚠️ 본문을 표에 넣으면 UPDATE 로 고칠 수 있게 되고, 그러면 「우리가 인증한
    --     그 파일」이 무엇이었는지 답할 수 없다.
    raw_path        TEXT NOT NULL DEFAULT '',
    checksum        TEXT NOT NULL DEFAULT '',
    byte_size       INTEGER NOT NULL DEFAULT 0,
    row_count       INTEGER NOT NULL DEFAULT 0,
    schema_json     TEXT NOT NULL DEFAULT '[]',
    profile_json    TEXT NOT NULL DEFAULT '{}',
    control_total_json TEXT NOT NULL DEFAULT '{}',
    quarantine_json TEXT NOT NULL DEFAULT '{}',
    data_kind       TEXT NOT NULL DEFAULT 'DEMO/SYNTHETIC',
    content_fingerprint TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',
    tenant_id       TEXT NOT NULL,
    scope_node_id   TEXT NOT NULL,
    entity_mode     TEXT NOT NULL,
    created_by      TEXT NOT NULL DEFAULT '',
    certified_at    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
-- ★★★ [2026-08-20 §7 3단계] 인증판 → **업무 객체 범위 색인**
--
-- 온톨로지 계약의 `dataset` 객체 id 는 **업무 레코드 ID**(`SHP-…`·`STK-…`)이지
-- 인증판 ID(`ds_…`)가 아니다. 그런데 범위(tenant·entity_mode·scope_node)는 인증판이
-- 들고 있다. 그 사이를 잇는 것이 없어서 Resolver 가 «영영 못 찾는» 상태였다.
--
-- ⚠️⚠️ **업무 본문을 복제하지 않는다.** 여기 있는 것은 「어느 판의 어느 행에서 왔고
--   그 범위가 무엇인가」뿐이다. 본문을 옮기면 두 벌이 되고, 두 벌은 갈라진다.
--
-- ★ 열쇠를 둘로 나눈다:
--     정체성   (namespace, object_type, object_id)              같은 SHP-001 은 같은 배
--     판 결속  (namespace, object_type, object_id, snapshot_id)  판마다 한 줄
--   ⚠️ 정체성을 판에 묶으면 `as_of` 를 바꿀 때마다 **다른 객체**가 되어 경로가 끊긴다.
CREATE TABLE IF NOT EXISTS object_scope_index (
    namespace       TEXT NOT NULL,
    object_type     TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    snapshot_id     TEXT NOT NULL,
    dataset_contract_key TEXT NOT NULL DEFAULT '',
    -- 그 판의 **어느 행**인가. 본문이 아니라 위치다.
    row_evidence    TEXT NOT NULL DEFAULT '',
    tenant_id       TEXT NOT NULL,
    -- ★★★ [2026-08-21 4.1b-0] **둘은 다른 것이다.**
    --   `scope_node_id`  어느 **ECM 조직 노드**의 데이터인가 (계층·조상 해석의 축)
    --   `owner_dept_id`  어느 **실제 부서**가 소유·관리하는가 (`org_directory` 의 부서)
    -- ⚠️⚠️ 같은 값으로 채우면 안 된다. PDP 는 `owner_dept_id in readable_dept_ids` 를
    --   보는데 그 집합은 **부서 ID** 로 만들어진다 — 노드 ID 를 넣으면 시험에서만
    --   통과하고 실제 사용자 권한에서는 거부된다(또는 그 반대로 새어 나간다).
    -- ⚠️ 지금 시연 데이터에는 부서 칸이 **없다.** 비워 두고, 그 결과 PDP 가
    --   `RESOURCE_UNBOUND` 로 막는 것이 맞다(D-014: 미지정은 전사 공용이 아니라 비노출).
    scope_node_id   TEXT NOT NULL,
    -- ★★★ [G2 Ownership Binding] `owner_dept_id` 는 **정본이 아니라 물질화된 결과**다.
    --   정본은 `dataset_ownership_bindings`(승인된 결속)이고, 여기 값은 그 결속을 물질화한
    --   사본이다. 그래서 **어느 결속에서 나왔는지**를 함께 봉인한다 —
    --   나중에 「이 색인 값은 어느 승인에서 나왔나」와 「그 결속이 그 뒤 바뀌었나」에
    --   답할 수 있어야 한다.
    -- ⚠️ 업무 데이터 행의 `owner_dept_id` 열은 **읽지 않는다.** 데이터가 자기 권한 범위를
    --   스스로 정하면 그것이 곧 자기진술 통제다(`calc_binding` 과 같은 유형).
    owner_dept_id   TEXT NOT NULL DEFAULT '',
    owner_binding_id TEXT NOT NULL DEFAULT '',
    owner_binding_fingerprint TEXT NOT NULL DEFAULT '',
    entity_mode     TEXT NOT NULL,
    data_kind       TEXT NOT NULL DEFAULT '',
    -- ★ `as_of` 로 판을 고르는 축. ⚠️ 「그냥 최신」을 쓰지 않기 위해 필요하다.
    certified_at    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    PRIMARY KEY (namespace, object_type, object_id, snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_scope_index_identity
    ON object_scope_index(namespace, object_type, object_id, certified_at);
CREATE INDEX IF NOT EXISTS idx_scope_index_snapshot
    ON object_scope_index(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_snapshot_binding ON dataset_snapshots(binding_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_state ON dataset_snapshots(instance_id, state);

CREATE TABLE IF NOT EXISTS readiness_evaluations (
    evaluation_id   TEXT PRIMARY KEY,
    instance_id     TEXT NOT NULL,
    verdict         TEXT NOT NULL DEFAULT '',
    detail_json     TEXT NOT NULL DEFAULT '{}',
    fingerprint     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',
    tenant_id       TEXT NOT NULL,
    scope_node_id   TEXT NOT NULL,
    entity_mode     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readiness_instance ON readiness_evaluations(instance_id);

CREATE TABLE IF NOT EXISTS baseline_builds (
    build_id        TEXT PRIMARY KEY,
    instance_id     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    fingerprint     TEXT NOT NULL DEFAULT '',
    detail_json     TEXT NOT NULL DEFAULT '{}',
    tenant_id       TEXT NOT NULL,
    scope_node_id   TEXT NOT NULL,
    entity_mode     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baseline_instance ON baseline_builds(instance_id);

-- ★★★ [M0-0] 계산 능력 **실행 승인**. 대상은 «결속 지문» 이지 참조 이름이 아니다.
-- ⚠️ 이름을 대상으로 삼으면 산식·판·범위를 바꿔도 승인이 살아남는다.
CREATE TABLE IF NOT EXISTS calc_execution_approvals (
    approval_id         TEXT PRIMARY KEY,
    ref                 TEXT NOT NULL,
    binding_fingerprint TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    ledger_event_id     TEXT NOT NULL,
    binding_json        TEXT NOT NULL DEFAULT '{}',
    tenant_id           TEXT NOT NULL DEFAULT '',
    entity_mode         TEXT NOT NULL DEFAULT '',
    scope_node_id       TEXT NOT NULL DEFAULT '',
    data_kind           TEXT NOT NULL DEFAULT '',
    valid_until         TEXT NOT NULL,
    approved_by         TEXT NOT NULL,
    rationale           TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cea_binding ON calc_execution_approvals(binding_fingerprint);
-- ★ 같은 결속에 살아 있는 승인은 **하나뿐**이다. 멱등을 DB 가 함께 지킨다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_cea_active
    ON calc_execution_approvals(binding_fingerprint) WHERE status='active';

-- ★★★ 키트 앱 런타임 계약. **초안과 승인이 같은 표에 산다.**
--
-- ⚠️⚠️ 이 표가 없던 동안 앱 계약을 승인할 곳이 아무 데도 없었다. 그래서 「키트로 앱
--   생성」은 통제를 다 지나고도 **부를 방법이 없었다** — 소유권 승인 경로가 없던 것과
--   같은 결함이다(「통제는 있는데 부르는 경로가 없다」).
-- ★ 같은 DB 에 둔다. 새 DB 를 만들면 시험 격리 목록과 불변식 감시 목록에 **또** 빠지고,
--   그것이 2026-08-23 협업 저장소 오염의 원인이었다.
CREATE TABLE IF NOT EXISTS kit_app_contracts (
    contract_row_id      TEXT PRIMARY KEY,
    instance_id          TEXT NOT NULL,
    app_id               TEXT NOT NULL,
    revision             INTEGER NOT NULL,
    status               TEXT NOT NULL,        -- DRAFT | APPROVED | SUPERSEDED
    semantic_fingerprint TEXT NOT NULL,
    contract_json        TEXT NOT NULL,
    drafted_by           TEXT NOT NULL,
    drafted_at           TEXT NOT NULL,
    approved_by          TEXT NOT NULL DEFAULT '',
    approved_at          TEXT NOT NULL DEFAULT '',
    ledger_event_id      TEXT NOT NULL DEFAULT '',
    tenant_id            TEXT NOT NULL DEFAULT '',
    scope_node_id        TEXT NOT NULL DEFAULT '',
    entity_mode          TEXT NOT NULL DEFAULT '',
    updated_at           TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kac_rev
    ON kit_app_contracts(instance_id, app_id, revision);
-- ★ 한 앱에 승인된 계약은 **하나뿐**이다. 둘이면 어느 쪽이 도는 앱인지 알 수 없다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_kac_approved
    ON kit_app_contracts(instance_id, app_id) WHERE status='APPROVED';
-- ★★★ **자기 승인 금지를 DB 가 함께 지킨다.**
--
-- ⚠️⚠️ 응용에만 두면 다음 호출 경로가 그 검사를 건너뛴다 — 이 저장소에서 이미
--   「예외를 한 곳만 지웠다」로 겪은 일이다. 다만 층마다 **다른 가정**에 서야 하므로,
--   여기서는 응용 정규화를 믿지 않고 값 자체를 본다(공백·대소문자까지).
CREATE TRIGGER IF NOT EXISTS trg_kac_no_self_approval_ins
BEFORE INSERT ON kit_app_contracts
WHEN NEW.status = 'APPROVED'
     AND lower(trim(NEW.approved_by)) = lower(trim(NEW.drafted_by))
BEGIN
    SELECT RAISE(ABORT, '만든 사람이 자기 계약을 승인할 수 없습니다.');
END;
CREATE TRIGGER IF NOT EXISTS trg_kac_no_self_approval_upd
BEFORE UPDATE ON kit_app_contracts
WHEN NEW.status = 'APPROVED'
     AND lower(trim(NEW.approved_by)) = lower(trim(NEW.drafted_by))
BEGIN
    SELECT RAISE(ABORT, '만든 사람이 자기 계약을 승인할 수 없습니다.');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(payload: Any) -> str:
    """내용 지문. **키 순서를 고정**해 같은 내용이 늘 같은 값을 낸다."""
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


class DataPreparationStore:
    def __init__(self, db_path: Optional[str] = None):
        """⚠️ 기본 경로를 **호출 시점에** 해석하고 파일은 아직 열지 않는다.

        [2026-08-17 결정 원장 사고] 와 같은 함정을 처음부터 피한다 — 기본 인자를 굳히면
        나중에 격리해도 이미 늦고, `__init__` 에서 파일을 열면 **import 만으로** 운영
        파일이 생긴다."""
        self.db_path = _DB_PATH if db_path is None else db_path
        self._lock = threading.Lock()
        self._prepared_for: Optional[str] = None

    # ── 인프라 ───────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        with contextlib.suppress(Exception):
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ready(self) -> None:
        """첫 사용 직전에 스키마를 준비한다. **멱등이다** — 여러 번 돌려도 같다."""
        if self._prepared_for == self.db_path:
            return
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            #: ⚠️ `CREATE TABLE IF NOT EXISTS` 는 **이미 있는 표에 새 열을 넣어 주지 않는다.**
            #:   Ownership Binding 이전에 만들어진 DB 는 봉인 열이 없으므로 여기서 채운다(멱등).
            #: ⚠️⚠️ [재감사 보정] 종전에는 `except Exception: pass` 였다. 그러면 디스크 꽉 참·
            #:   파일 손상·잠금 오류까지 **「이미 존재함」으로 삼킨다** — 스키마가 반쯤 선
            #:   상태로 서비스가 뜨고, 그 증상은 질의 시점에 엉뚱한 곳에서 터진다.
            #:   「이미 있다」만 넘기고 나머지는 올린다.
            existing = {r[1] for r in conn.execute("PRAGMA table_info(object_scope_index)")}
            for col in ("owner_binding_id", "owner_binding_fingerprint"):
                if col in existing:
                    continue
                conn.execute(
                    f"ALTER TABLE object_scope_index ADD COLUMN {col} "
                    f"TEXT NOT NULL DEFAULT ''")
            #: 소유권 «정본» 표. 색인과 같은 저장소에 두어 한 트랜잭션으로 물질화한다.
            from core.data_preparation import ownership_binding as _ob
            #: ★★★ [4.1c-B P0-2] **DDL 보다 먼저** 구버전 표를 처리한다.
            #:   `CREATE TABLE IF NOT EXISTS` 는 이미 있는 표에 열을 넣어 주지 않으므로,
            #:   `8ca029634` 형식 표가 있으면 첫 `declare()` 가 `no such column` 으로 죽는다.
            #:   ⚠️ 옛 행을 승인된 것으로 백필하지 않는다 — 격리하고 UNBOUND 로 둔다.
            _ob.migrate(conn)
            conn.executescript(_ob.DDL)
            conn.commit()
        finally:
            conn.close()
        self._prepared_for = self.db_path

    @contextlib.contextmanager
    def transaction(self):
        """조회와 기록을 **한 락·한 트랜잭션**으로 하고 연결도 반드시 닫는다.

        ``sqlite3.Connection`` 의 context manager는 commit/rollback만 수행하며
        연결 자체는 닫지 않는다.  종전 구현은 CPython의 객체 회수 시점에 종료를
        맡겨 Windows에서 DB 파일 핸들이 남았고, 일관성 검증용 사본조차 즉시 폐기할
        수 없었다.  파일 수명과 트랜잭션 수명을 여기서 함께 닫는다.
        """
        self._ready()
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    # ── Kit Registry ─────────────────────────────────────────────────────
    def upsert_kit_version(self, *, kit_id: str, version: str, name: str, mode: str,
                           source_path: str, fingerprint_value: str,
                           profile: Dict[str, Any]) -> Dict[str, Any]:
        """키트 판본을 등록한다. 같은 `(kit_id, version)` 은 **내용으로 덮는다** —
        문서가 고쳐지면 지문이 달라지고, 그 사실이 보여야 한다."""
        if mode not in m.KIT_MODES:
            raise m.DataPreparationError(
                f"키트 모드는 {list(m.KIT_MODES)} 중 하나여야 합니다 — 시연용 합성 "
                f"데이터와 실제 업무 데이터를 섞으면 둘 다 못 쓴다.")
        now = _now()
        row = {"kit_version_id": f"kv_{uuid.uuid4().hex[:14]}", "kit_id": kit_id,
               "version": version, "name": name, "mode": mode,
               "source_path": source_path, "fingerprint": fingerprint_value,
               "profile_json": json.dumps(profile, ensure_ascii=False, sort_keys=True),
               "status": "active", "created_at": now, "updated_at": now}
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT kit_version_id, created_at FROM kit_registry_versions "
                "WHERE kit_id=? AND version=?", (kit_id, version)).fetchone()
            if existing:
                row["kit_version_id"] = existing["kit_version_id"]
                row["created_at"] = existing["created_at"]
                conn.execute(
                    "UPDATE kit_registry_versions SET name=?, mode=?, source_path=?, "
                    "fingerprint=?, profile_json=?, updated_at=? WHERE kit_version_id=?",
                    (name, mode, source_path, fingerprint_value, row["profile_json"],
                     now, row["kit_version_id"]))
            else:
                cols = ", ".join(row)
                conn.execute(f"INSERT INTO kit_registry_versions ({cols}) VALUES "
                             f"({', '.join('?' * len(row))})", tuple(row.values()))
        return self._public(row)

    def list_kit_versions(self, kit_id: str = "") -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            sql = "SELECT * FROM kit_registry_versions WHERE status='active'"
            args: tuple = ()
            if kit_id:
                sql += " AND kit_id=?"
                args = (kit_id,)
            sql += " ORDER BY kit_id ASC, version ASC"
            return [self._public(dict(r)) for r in conn.execute(sql, args)]

    def get_kit_version(self, kit_id: str, version: str) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            r = conn.execute("SELECT * FROM kit_registry_versions WHERE kit_id=? AND "
                             "version=? AND status='active'", (kit_id, version)).fetchone()
        return self._public(dict(r)) if r else None

    # ── Kit Instance ─────────────────────────────────────────────────────
    def create_instance(self, *, kit_id: str, version: str, kit_fingerprint: str,
                        tenant_id: str, scope_node_id: str, entity_mode: str,
                        label: str = "", created_by: str = "") -> Dict[str, Any]:
        """키트를 조직에 적용한다. **문맥 세 값이 없으면 만들지 않는다.**

        ## ★★★ [M0-3.1] 등록된 키트 판본만 쓸 수 있다

        ⚠️⚠️ 앞 판은 `kit_id`·`version`·`kit_fingerprint` 를 **그대로 받아 적었다.** 그래서
          시험이 `KIT-VERTICAL / fp-vertical` 같은 **임의 키트를 만들어 인증**할 수 있었고,
          그 위에서 「정본 열을 썼다」고 보고했다 — 등록부와 한 번도 대조하지 않은 채로.

        ★ 이제 등록부(`kit_registry_versions`)에서 그 판본을 찾고 **지문까지 대조**한다.
          지문이 다르면 그것은 같은 이름의 **다른 키트**다.

        ⚠️ 등록되지 않은 키트는 거부한다. 「등록은 나중에」로 두면 정본이 아닌 계약으로
          인증판이 쌓이고, 그 판들은 나중에 어느 계약의 것인지 말할 수 없다."""
        m.assert_context(tenant_id, scope_node_id, entity_mode)
        self._assert_registered_kit(kit_id, version, kit_fingerprint)
        now = _now()
        row = {"instance_id": f"ki_{uuid.uuid4().hex[:14]}", "kit_id": kit_id,
               "version": version, "kit_fingerprint": kit_fingerprint,
               "tenant_id": tenant_id, "scope_node_id": scope_node_id,
               "entity_mode": entity_mode, "label": label, "status": "active",
               "created_by": created_by, "created_at": now, "updated_at": now}
        with self.transaction() as conn:
            cols = ", ".join(row)
            conn.execute(f"INSERT INTO kit_instances ({cols}) VALUES "
                         f"({', '.join('?' * len(row))})", tuple(row.values()))
        return dict(row)

    def _assert_registered_kit(self, kit_id: str, version: str,
                               kit_fingerprint: str) -> None:
        """등록부에 있는 판본인가, 그리고 **지문이 같은가.**

        ⚠️ 지문을 안 보면 같은 이름의 다른 계약으로 인증판이 쌓인다 — 나중에 그 판이
          어느 계약의 것인지 말할 수 없다."""
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT kit_id, version, fingerprint, status FROM kit_registry_versions "
                "WHERE kit_id=? AND version=?", (kit_id, version)).fetchone()
        if row is None:
            raise m.DataPreparationError(
                f"등록되지 않은 키트 판본입니다: {kit_id}/{version} — 키트를 먼저 "
                f"등록해야 합니다(임의 계약으로 인증판을 쌓지 않습니다).")
        want = str(dict(row).get("fingerprint", "") or "")
        got = str(kit_fingerprint or "")
        if want and got and want != got:
            raise m.DataPreparationError(
                f"키트 지문이 등록부와 다릅니다({kit_id}/{version}): 등록 {want[:12]}… "
                f"요청 {got[:12]}… — 같은 이름의 다른 계약입니다.")
        if want and not got:
            raise m.DataPreparationError(
                f"키트 지문이 없습니다({kit_id}/{version}) — 어느 판본을 적용하는지 "
                f"적지 않고 인스턴스를 만들지 않습니다.")

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            r = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?",
                             (instance_id,)).fetchone()
        return dict(r) if r else None

    def list_instances(self, *, tenant_id: str, entity_mode: str,
                       scope_node_ids: List[str]) -> List[Dict[str, Any]]:
        """**보이는 범위만** 돌려준다.

        ⚠️ 범위 목록이 비면 빈 결과다 — 「비었으니 전부」로 읽으면 그 순간 타 조직
          자원이 목록에 뜬다. 개수조차 누설이다."""
        #: ⚠️ SQLite 는 `IN ()` 을 빈 결과로 받아 주므로 이 줄이 없어도 «지금은»
        #:   같다. 그래도 남긴다 — 누군가 「빈 목록이면 필터를 빼자」로 최적화하는
        #:   순간 그것이 전부 조회가 되기 때문이다. 의도를 코드에 남겨 둔다.
        if not scope_node_ids:
            return []
        marks = ", ".join("?" * len(scope_node_ids))
        with self.transaction() as conn:
            rows = conn.execute(
                f"SELECT * FROM kit_instances WHERE tenant_id=? AND entity_mode=? "
                f"AND scope_node_id IN ({marks}) AND status='active' "
                f"ORDER BY created_at DESC",
                (tenant_id, entity_mode, *scope_node_ids)).fetchall()
        return [dict(r) for r in rows]

    # ── Source Binding ───────────────────────────────────────────────────
    def create_binding(self, *, instance_id: str, dataset_contract_key: str,
                       provider: str, config: Dict[str, Any], tenant_id: str,
                       scope_node_id: str, entity_mode: str,
                       created_by: str = "") -> Dict[str, Any]:
        m.assert_context(tenant_id, scope_node_id, entity_mode)
        if not m.provider_supported(provider):
            raise m.DataPreparationError(
                f"지원하지 않는 provider 입니다: {provider} (가능: {list(m.PROVIDERS)})")
        now = _now()
        row = {"binding_id": f"sb_{uuid.uuid4().hex[:14]}", "instance_id": instance_id,
               "dataset_contract_key": dataset_contract_key, "provider": provider,
               "config_json": json.dumps(config or {}, ensure_ascii=False, sort_keys=True),
               "fingerprint": fingerprint({"provider": provider, "config": config or {}}),
               "state": m.DRAFT, "tenant_id": tenant_id, "scope_node_id": scope_node_id,
               "entity_mode": entity_mode, "blocked_reason": "", "created_by": created_by,
               "created_at": now, "updated_at": now, "retired_at": ""}
        with self.transaction() as conn:
            cols = ", ".join(row)
            conn.execute(f"INSERT INTO source_bindings ({cols}) VALUES "
                         f"({', '.join('?' * len(row))})", tuple(row.values()))
        return self._public(row)

    def get_binding(self, binding_id: str) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            r = conn.execute("SELECT * FROM source_bindings WHERE binding_id=?",
                             (binding_id,)).fetchone()
        return self._public(dict(r)) if r else None

    def advance_instance_kit_fingerprint(self, instance_id: str, *,
                                         previous_fingerprint: str,
                                         next_fingerprint: str) -> Dict[str, Any]:
        """동일 키트 판본의 검증된 계약 갱신을 인스턴스에 결속한다.

        등록부가 가리키는 새 지문과 정확히 같아야 하며, 호출자가 읽었던 이전 지문도
        다시 대조한다. 다른 프로세스가 먼저 바꾼 상태를 덮지 않는다.
        """
        if not previous_fingerprint or not next_fingerprint:
            raise m.DataPreparationError("이전·다음 키트 지문은 모두 필요합니다.")
        now = _now()
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?",
                               (instance_id,)).fetchone()
            if row is None:
                raise m.DataPreparationError(f"존재하지 않는 키트 인스턴스입니다: {instance_id}")
            current = str(dict(row).get("kit_fingerprint") or "")
            if current == next_fingerprint:
                return self._public(dict(row))
            if current != previous_fingerprint:
                raise m.StateConflict("키트 인스턴스 지문이 읽은 뒤 바뀌었습니다.")
            registered = conn.execute(
                "SELECT fingerprint FROM kit_registry_versions WHERE kit_id=? AND "
                "version=? AND status='active'", (row["kit_id"], row["version"])).fetchone()
            if registered is None or str(registered["fingerprint"] or "") != next_fingerprint:
                raise m.DataPreparationError("등록부가 다음 키트 지문을 가리키지 않습니다.")
            conn.execute("UPDATE kit_instances SET kit_fingerprint=?, updated_at=? "
                         "WHERE instance_id=?", (next_fingerprint, now, instance_id))
            fresh = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?",
                                 (instance_id,)).fetchone()
        return self._public(dict(fresh))

    def list_bindings(self, instance_id: str,
                      dataset_contract_key: str = "") -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            sql = "SELECT * FROM source_bindings WHERE instance_id=?"
            args: tuple = (instance_id,)
            if dataset_contract_key:
                sql += " AND dataset_contract_key=?"
                args += (dataset_contract_key,)
            sql += " ORDER BY created_at ASC"
            return [self._public(dict(r)) for r in conn.execute(sql, args)]

    def active_binding(self, instance_id: str,
                       dataset_contract_key: str) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            r = conn.execute(
                "SELECT * FROM source_bindings WHERE instance_id=? AND "
                "dataset_contract_key=? AND state=?",
                (instance_id, dataset_contract_key, m.ACTIVE)).fetchone()
        return self._public(dict(r)) if r else None

    def transition(self, binding_id: str, target: str, *,
                   blocked_reason: str = "") -> Dict[str, Any]:
        """상태를 옮긴다. **활성화는 기존 ACTIVE 종료와 한 트랜잭션**이다.

        ⚠️ 나누면 그 사이에 「활성이 하나도 없는」 순간이 생기고, 그때 들어온 요청은
          「원천이 없다」를 본다 — 아무도 아무것도 바꾸지 않았는데."""
        target = str(target or "")
        if target == m.BLOCKED and not str(blocked_reason or "").strip():
            #: 사유 없는 차단은 나중에 「왜 막혔지?」에 답할 수 없고, 그러면 아무도
            #: 되돌리지 못한다(원장의 비활성화 사유와 같은 규칙).
            raise m.DataPreparationError(
                "차단에는 사유가 필요합니다 — 사유가 없으면 되돌릴 근거도 없습니다.")
        now = _now()
        with self.transaction() as conn:
            cur = conn.execute("SELECT * FROM source_bindings WHERE binding_id=?",
                               (binding_id,)).fetchone()
            if cur is None:
                raise m.DataPreparationError(f"존재하지 않는 결속입니다: {binding_id}")
            row = dict(cur)
            m.assert_transition(row["state"], target)

            if target == m.ACTIVE:
                #: ★ 같은 트랜잭션 안에서 기존 ACTIVE 를 먼저 내린다. DB 의 부분 유일
                #:   인덱스가 두 번째 방어선이다 — 여기서 빠뜨려도 INSERT 가 막힌다.
                conn.execute(
                    "UPDATE source_bindings SET state=?, retired_at=?, updated_at=? "
                    "WHERE instance_id=? AND dataset_contract_key=? AND state=? "
                    "AND binding_id<>?",
                    (m.RETIRED, now, now, row["instance_id"],
                     row["dataset_contract_key"], m.ACTIVE, binding_id))

            conn.execute(
                "UPDATE source_bindings SET state=?, blocked_reason=?, updated_at=?, "
                "retired_at=? WHERE binding_id=?",
                (target, blocked_reason if target == m.BLOCKED else "", now,
                 now if target == m.RETIRED else row.get("retired_at", ""), binding_id))
            out = conn.execute("SELECT * FROM source_bindings WHERE binding_id=?",
                               (binding_id,)).fetchone()
        return self._public(dict(out))

    # ── Dataset Snapshot ─────────────────────────────────────────────────
    def create_snapshot(self, **fields: Any) -> Dict[str, Any]:
        """Snapshot 한 건을 만든다. **상태는 언제나 `RAW` 로 시작한다.**

        ⚠️ 호출부가 상태를 정하게 두면 「파싱도 안 했는데 인증됨」이 만들어진다."""
        m.assert_context(fields.get("tenant_id"), fields.get("scope_node_id"),
                         fields.get("entity_mode"))
        kind = str(fields.get("data_kind") or m.DATA_KIND_DEMO)
        if kind not in m.DATA_KINDS:
            raise m.DataPreparationError(
                f"data_kind 는 {list(m.DATA_KINDS)} 중 하나여야 합니다.")
        now = _now()
        row = {
            "snapshot_id": f"ds_{uuid.uuid4().hex[:14]}",
            "binding_id": str(fields.get("binding_id", "")),
            "instance_id": str(fields.get("instance_id", "")),
            "dataset_contract_key": str(fields.get("dataset_contract_key", "")),
            "state": m.RAW,
            "raw_path": str(fields.get("raw_path", "")),
            "checksum": str(fields.get("checksum", "")),
            "byte_size": int(fields.get("byte_size", 0) or 0),
            "row_count": int(fields.get("row_count", 0) or 0),
            "schema_json": json.dumps(fields.get("schema") or [], ensure_ascii=False,
                                      sort_keys=True),
            "profile_json": "{}", "control_total_json": "{}", "quarantine_json": "{}",
            "data_kind": kind,
            "content_fingerprint": str(fields.get("content_fingerprint", "")),
            "status": "active",
            "tenant_id": str(fields.get("tenant_id", "")),
            "scope_node_id": str(fields.get("scope_node_id", "")),
            "entity_mode": str(fields.get("entity_mode", "")),
            "created_by": str(fields.get("created_by", "")),
            "certified_at": "", "created_at": now, "updated_at": now,
        }
        with self.transaction() as conn:
            cols = ", ".join(row)
            conn.execute(f"INSERT INTO dataset_snapshots ({cols}) VALUES "
                         f"({', '.join('?' * len(row))})", tuple(row.values()))
        return self._public(row)

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            r = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?",
                             (snapshot_id,)).fetchone()
        return self._public(dict(r)) if r else None

    def list_snapshots(self, instance_id: str) -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM dataset_snapshots WHERE instance_id=? "
                                "ORDER BY created_at ASC", (instance_id,)).fetchall()
        return [self._public(dict(r)) for r in rows]

    def advance_snapshot(self, snapshot_id: str, target: str,
                         on_commit: Optional[Any] = None,
                         **payload: Any) -> Dict[str, Any]:
        """Snapshot 을 다음 단계로 옮긴다.

        ★★★ [2026-08-21 P1] `on_commit(conn, row)` 은 **같은 트랜잭션 안**에서 돈다.
          상태 전환과 그에 딸린 기록(예: 범위 색인)을 **한 번에** 커밋하기 위해서다.
        ⚠️⚠️ 나누면 「인증됐는데 색인이 없는」 구간이 아무리 짧아도 생긴다. 그 사이에
          읽은 쪽은 색인 없는 인증판을 보고, 승인된 관계의 끝점이면 **503** 을 만난다 —
          아무도 아무것도 잘못하지 않았는데.

        ★★★ **인증 뒤에는 원문도 본문도 바꾸지 않는다.** `raw_path`·`checksum`·
          `row_count` 는 여기서 아예 손대지 않는다 — 갱신하는 것은 그 단계가 «새로
          알아낸 것»(프로파일·대사·격리)뿐이다.
        ⚠️ 인증 뒤 수정을 허용하면 「우리가 인증한 그 숫자」가 무엇이었는지 아무도
          답할 수 없다. 정정은 **새 Snapshot** 이다."""
        now = _now()
        with self.transaction() as conn:
            cur = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?",
                               (snapshot_id,)).fetchone()
            if cur is None:
                raise m.DataPreparationError(f"존재하지 않는 Snapshot 입니다: {snapshot_id}")
            m.assert_snapshot_transition(cur["state"], target)

            sets = ["state=?", "updated_at=?"]
            args: List[Any] = [target, now]
            for key, col in (("profile", "profile_json"),
                             ("control_total", "control_total_json"),
                             ("quarantine", "quarantine_json")):
                if key in payload:
                    sets.append(f"{col}=?")
                    args.append(json.dumps(payload[key] or {}, ensure_ascii=False,
                                           sort_keys=True))
            if target in m.CERTIFIED_STATES:
                #: ★★★ 인증 종점마다 «허용되는 자료 성격» 이 다르다. 여기서 막지 않으면
                #:   시연 자료가 원천 인증을 받거나 실물이 시연 인증을 받는다 — 둘을 섞으면
                #:   어느 것이 시연이었는지 영영 가릴 수 없다.
                #: ⚠️ 이 검사를 응용층(`snapshot_service`)에만 두지 «않는다». 저장소가
                #:   자기 상태를 지키지 못하면, 다른 경로가 하나 생기는 날 조용히 뚫린다.
                want = m.CERTIFICATION_DATA_KIND.get(target, "")
                have = str(cur["data_kind"] if "data_kind" in cur.keys() else "")
                if want and have != want:
                    raise m.StateConflict(
                        f"«{have or '성격 미상'}» 자료는 {target} 를 받을 수 없습니다 — "
                        f"이 종점은 «{want}» 전용입니다. 시연 자료와 실물이 섞이면 "
                        f"어느 것이 시연이었는지 가릴 수 없습니다.")
                sets.append("certified_at=?")
                args.append(now)
            args.append(snapshot_id)
            conn.execute(f"UPDATE dataset_snapshots SET {', '.join(sets)} "
                         f"WHERE snapshot_id=?", tuple(args))
            out = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?",
                               (snapshot_id,)).fetchone()
            if on_commit is not None:
                #: ⚠️ 여기서 예외가 나면 **상태 전환도 함께 되돌아간다.** 그것이 의도다.
                on_commit(conn, dict(out))
        return self._public(dict(out))

    def replace_demo_snapshot(self, old_snapshot_id: str, new_snapshot_id: str,
                              on_commit: Optional[Any] = None) -> Dict[str, Any]:
        """검증을 마친 새 시연판으로 기존 인증판을 **원자적으로** 교체한다.

        새 판을 먼저 인증하면 잠깐이라도 같은 객체의 인증판이 둘이 되고, 기존 판을
        먼저 철회하면 새 판 인증 실패 시 데이터가 사라진다. 두 상태 전이와 새 색인
        적재를 한 트랜잭션으로 묶어 어느 중간 상태도 독자에게 보이지 않게 한다.
        원문은 수정하지 않으며 기존 판은 ``REVOKED`` 로 보존한다.
        """
        now = _now()
        with self.transaction() as conn:
            old = conn.execute(
                "SELECT * FROM dataset_snapshots WHERE snapshot_id=?",
                (old_snapshot_id,)).fetchone()
            new = conn.execute(
                "SELECT * FROM dataset_snapshots WHERE snapshot_id=?",
                (new_snapshot_id,)).fetchone()
            if old is None or new is None:
                raise m.DataPreparationError("교체할 기존판 또는 새 판이 없습니다.")
            old_row, new_row = dict(old), dict(new)
            for key in ("instance_id", "binding_id", "dataset_contract_key",
                        "tenant_id", "scope_node_id", "entity_mode", "data_kind"):
                if str(old_row.get(key) or "") != str(new_row.get(key) or ""):
                    raise m.DataPreparationError(
                        f"서로 다른 자료는 인증판 교체로 묶을 수 없습니다: {key}")
            if old_row.get("state") != m.DEMO_CERTIFIED:
                raise m.StateConflict("기존판이 DEMO_CERTIFIED 상태가 아닙니다.")
            if new_row.get("state") != m.RECONCILED:
                raise m.StateConflict("새 판은 RECONCILED 상태에서만 교체 인증할 수 있습니다.")
            if str(new_row.get("data_kind") or "") != m.DATA_KIND_DEMO:
                raise m.StateConflict("시연용 합성 데이터만 이 교체 경로를 사용할 수 있습니다.")

            conn.execute(
                "UPDATE dataset_snapshots SET state=?, updated_at=? WHERE snapshot_id=?",
                (m.REVOKED, now, old_snapshot_id))
            conn.execute(
                "UPDATE dataset_snapshots SET state=?, certified_at=?, updated_at=? "
                "WHERE snapshot_id=?",
                (m.DEMO_CERTIFIED, now, now, new_snapshot_id))
            fresh = conn.execute(
                "SELECT * FROM dataset_snapshots WHERE snapshot_id=?",
                (new_snapshot_id,)).fetchone()
            if on_commit is not None:
                on_commit(conn, dict(fresh))
        return self._public(dict(fresh))

    # ── 공통 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _public(row: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(row)
        for key, target in (("profile_json", "profile"), ("config_json", "config"),
                            ("detail_json", "detail"), ("schema_json", "schema"),
                            ("control_total_json", "control_total"),
                            ("quarantine_json", "quarantine")):
            if key in d:
                try:
                    d[target] = json.loads(d.pop(key) or "{}")
                except Exception:
                    d[target] = {}
                    d[f"{target}_unreadable"] = True
        return d


data_preparation_store = DataPreparationStore()
