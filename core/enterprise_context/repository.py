"""ECM 저장소 — `docs/design_enterprise_context_master.md` §4.2 / E1.

인프라 규약은 `core/master_data.py`·`core/advisor_store.py` 와 동일하다(멱등 DDL + WAL +
busy_timeout + 스레드 락 + `_ensure_tables` 복원력). 새 인프라를 들이지 않는 이유는 운영·백업·
마이그레이션 경로를 하나로 유지하기 위해서다.

⚠️ `core/org_directory.py`(부서·사용자·권한)를 **교체하지 않는다**(§10.1). ECM 은 공통 범위
  해석 계층으로 먼저 얹히고, 부서는 `organization_nodes.dept_id` 로 **매핑**된다. 교체하면
  Phase 1~5 에서 세운 권한이 전부 흔들린다.
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.enterprise_context.models import (INHERITANCE_MODES, NODE_TYPES, PROFILE_KINDS,
                                            RELATION_TYPES, STATUS_ACTIVE, STATUSES,
                                            EcmError, EnterpriseEntity, EnterpriseProfile,
                                            OrganizationEdge, OrganizationNode)
from core.paths import data_path

_DB_PATH = data_path("enterprise_context.db")

_DDL = """
-- ★★★ [2026-08-25] **회사(tenant)의 사람이 읽는 이름.**
--
-- ⚠️⚠️ 종전에는 `tenant_id` 밖에 없었다. 그래서 상단 문맥이
--   「tenant-afs-demo-materials」라는 **기계 식별자**를 사람에게 그대로 보여 줬다.
--   승인 시안의 그 자리는 「LS MnM」이다.
-- ★ 이름은 «있는 곳» 이 있어야 한다. 클라이언트가 id 에서 만들어 내면(예: 접두어 자르기)
--   회사 이름이 코드가 되고, 이름을 바꾸려면 배포를 해야 한다.
-- ⚠️ `enterprise_entities`(법인)와 **다른 층**이다. 한 tenant 안에 법인이 여럿일 수 있고,
--   그때 「어느 법인 이름을 회사 이름으로 쓸까」는 답이 없다. tenant 이름은 tenant 가 갖는다.
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name_ko     TEXT NOT NULL,
    legal_name  TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enterprise_entities (
    entity_id       TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    entity_type     TEXT NOT NULL DEFAULT 'legal_entity',
    entity_mode     TEXT NOT NULL DEFAULT 'REAL',
    legal_name      TEXT DEFAULT '',
    name_ko         TEXT NOT NULL,
    industry_code   TEXT DEFAULT '',
    base_entity_id  TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    effective_from  TEXT DEFAULT '',
    effective_to    TEXT DEFAULT '',
    version         INTEGER NOT NULL DEFAULT 1,
    approved_by     TEXT DEFAULT '',
    approved_at     TEXT DEFAULT '',
    source_ref      TEXT DEFAULT '',
    evidence_ref    TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ent_ctx ON enterprise_entities(tenant_id, entity_mode, status);
CREATE INDEX IF NOT EXISTS idx_ent_base ON enterprise_entities(base_entity_id);

CREATE TABLE IF NOT EXISTS organization_nodes (
    node_id         TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    node_type       TEXT NOT NULL,
    code            TEXT DEFAULT '',
    name_ko         TEXT NOT NULL,
    default_parent_id TEXT DEFAULT '',
    path_hint       TEXT DEFAULT '',
    dept_id         TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    effective_from  TEXT DEFAULT '',
    effective_to    TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_node_parent ON organization_nodes(default_parent_id);
CREATE INDEX IF NOT EXISTS idx_node_entity ON organization_nodes(entity_id);
CREATE INDEX IF NOT EXISTS idx_node_dept ON organization_nodes(dept_id);
CREATE INDEX IF NOT EXISTS idx_node_ctx ON organization_nodes(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_node_code ON organization_nodes(code, status);

-- [D-018 ⑦] 업무 코드의 **변경 이력과 별칭.**
--   `code` 는 사람이 쓰는 업무키이고 조직 개편·회사별 코드 체계에 따라 **바뀔 수 있다**
--   (`LS_MNM` → `LS_METALS`). 정본 `node_id` 는 그대로이므로 내부 관계는 안전하지만,
--   **옛 코드로 저장된 외부 연계·문서·사람의 기억**은 그 순간 끊긴다.
--   ⚠️ 끊긴 참조는 조용하다 — 조회가 «없음» 을 돌려주고, 그것은 «권한이 없다» 와 구분되지
--     않는다. 그래서 옛 코드를 버리지 않고 여기 남겨 계속 해석되게 한다.
--   ★ 별칭으로 찾은 것도 **정본 `node_id` 로 정규화**되므로 판정은 언제나 정본을 탄다.
CREATE TABLE IF NOT EXISTS organization_node_code_aliases (
    alias_id        TEXT PRIMARY KEY,
    node_id         TEXT NOT NULL,
    code            TEXT NOT NULL,            -- 과거에 쓰였던 코드
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    replaced_by     TEXT NOT NULL DEFAULT '', -- 이 코드를 대체한 새 코드
    reason          TEXT NOT NULL DEFAULT '', -- 왜 바뀌었는가(조직 개편·표준화 등)
    recorded_at     TEXT NOT NULL,
    UNIQUE (node_id, code)
);
CREATE INDEX IF NOT EXISTS idx_alias_code ON organization_node_code_aliases(code, tenant_id);

CREATE TABLE IF NOT EXISTS organization_edges (
    edge_id         TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    from_node_id    TEXT NOT NULL,
    to_node_id      TEXT NOT NULL,
    relation_type   TEXT NOT NULL,
    weight          REAL DEFAULT 1.0,
    effective_from  TEXT DEFAULT '',
    effective_to    TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at      TEXT NOT NULL,
    UNIQUE (from_node_id, to_node_id, relation_type, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_edge_from ON organization_edges(from_node_id, relation_type, status);
CREATE INDEX IF NOT EXISTS idx_edge_to ON organization_edges(to_node_id, relation_type, status);

CREATE TABLE IF NOT EXISTS enterprise_profiles (
    profile_id      TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    scope_node_id   TEXT DEFAULT '',
    industry_code   TEXT DEFAULT '',
    profile_kind    TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    inheritance_mode TEXT NOT NULL DEFAULT 'merge',
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    version         INTEGER NOT NULL DEFAULT 1,
    approved_by     TEXT DEFAULT '',
    approved_at     TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prof_scope ON enterprise_profiles(scope_node_id, profile_kind, status);
CREATE INDEX IF NOT EXISTS idx_prof_industry ON enterprise_profiles(industry_code, profile_kind, status);
"""


class EcmRepository:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ── 인프라 ────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    def _ensure_tables(self) -> bool:
        """`org_directory._ensure_tables` 와 같은 복원력 규약 — 상대 경로 DB 라 작업 디렉터리가
        바뀌면 테이블 없는 파일을 가리킨다. 조회 경로에서 한 번 복구를 시도한다."""
        try:
            self._init_db()
            return True
        except Exception:
            return False

    def _query(self, sql: str, params=()) -> List[Dict[str, Any]]:
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    return [dict(r) for r in conn.execute(sql, params).fetchall()]
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return []
        return []

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _uid(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    # ── 회사(tenant) 이름 ─────────────────────────────────────────────────
    def upsert_tenant(self, tenant_id: str, name_ko: str, legal_name: str = "",
                      status: str = STATUS_ACTIVE) -> Dict[str, Any]:
        """회사 이름을 세운다. **이름은 필수다** — 빈 이름을 저장하면 화면이 다시 id 를 쓴다."""
        tid = str(tenant_id or "").strip()
        name = str(name_ko or "").strip()
        if not tid:
            raise EcmError("tenant_id 가 필요합니다.")
        if not name:
            raise EcmError("회사 이름이 필요합니다 — 빈 이름은 화면에서 식별자로 되돌아갑니다.")
        now = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO tenants (tenant_id, name_ko, legal_name, status, "
                "                     created_at, updated_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(tenant_id) DO UPDATE SET "
                "  name_ko=excluded.name_ko, legal_name=excluded.legal_name, "
                "  status=excluded.status, updated_at=excluded.updated_at",
                (tid, name, str(legal_name or "").strip(), str(status), now, now))
        got = self.get_tenant(tid)
        assert got is not None                                   # pragma: no cover
        return got

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """⚠️ 없으면 `None` 이다 — 이름을 **지어내지 않는다.** 화면이 그때 id 를 쓴다."""
        rows = self._query("SELECT * FROM tenants WHERE tenant_id=?",
                           (str(tenant_id or "").strip(),))
        return rows[0] if rows else None

    def list_tenants(self, status: str = "") -> List[Dict[str, Any]]:
        if status:
            return self._query("SELECT * FROM tenants WHERE status=? ORDER BY name_ko",
                               (str(status),))
        return self._query("SELECT * FROM tenants ORDER BY name_ko")

    # ── 엔터티 ────────────────────────────────────────────────────────────
    def upsert_entity(self, e: EnterpriseEntity) -> EnterpriseEntity:
        from core.enterprise_context.context import ENTITY_MODES
        if e.entity_type not in NODE_TYPES:
            raise EcmError(f"entity_type 은 {NODE_TYPES} 중 하나여야 합니다.")
        if e.entity_mode not in ENTITY_MODES:
            raise EcmError(f"entity_mode 는 {ENTITY_MODES} 중 하나여야 합니다.")
        if e.status not in STATUSES:
            raise EcmError(f"status 는 {STATUSES} 중 하나여야 합니다.")
        if not e.name_ko:
            raise EcmError("name_ko 는 필수입니다.")
        # 가상·경쟁사는 원본 또는 근거가 있어야 한다 (§2.1-4, §7.3)
        #
        # ★★ [G1-C1.1] **검증 샌드박스만 예외다.** 이 규칙의 목적은 §7.1 계보 — 「이 가상 조직이
        #   어느 실제 조직에서 나왔는가」를 잃지 않는 것이다. 그런데 검증 샌드박스는 **어떤 실제
        #   조직도 본뜬 것이 아니다.** 과거 시험 산출물을 담아 두는 격벽일 뿐이다.
        #   ⚠️ 여기서 아무 실제 법인이나 `base_entity_id` 로 적으면 **거짓 계보**가 생기고,
        #     나중에 「이 가상 조직은 LS MnM 의 복제본」이라는 잘못된 답이 집계에 섞인다.
        #     없는 원본을 지어내는 것보다 유형을 좁혀 예외로 두는 편이 정직하다.
        if (e.entity_mode == "VIRTUAL" and not e.base_entity_id
                and e.entity_type != "validation_sandbox"):
            raise EcmError("가상 조직은 복제 원본(base_entity_id)이 있어야 합니다.")
        if e.entity_mode == "COMPETITOR_REFERENCE" and not e.evidence_ref:
            raise EcmError("경쟁사 모델은 공개·승인된 근거(evidence_ref)가 있어야 합니다.")
        now = self._now()
        if not e.entity_id:
            e.entity_id = self._uid("ent")
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO enterprise_entities (entity_id, tenant_id, entity_type, entity_mode, "
                "legal_name, name_ko, industry_code, base_entity_id, status, effective_from, "
                "effective_to, version, approved_by, approved_at, source_ref, evidence_ref, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(entity_id) DO UPDATE SET tenant_id=excluded.tenant_id, "
                "entity_type=excluded.entity_type, entity_mode=excluded.entity_mode, "
                "legal_name=excluded.legal_name, name_ko=excluded.name_ko, "
                "industry_code=excluded.industry_code, base_entity_id=excluded.base_entity_id, "
                "status=excluded.status, effective_from=excluded.effective_from, "
                "effective_to=excluded.effective_to, version=excluded.version, "
                "approved_by=excluded.approved_by, approved_at=excluded.approved_at, "
                "source_ref=excluded.source_ref, evidence_ref=excluded.evidence_ref, "
                "updated_at=excluded.updated_at",
                (e.entity_id, e.tenant_id, e.entity_type, e.entity_mode, e.legal_name, e.name_ko,
                 e.industry_code, e.base_entity_id, e.status, e.effective_from, e.effective_to,
                 int(e.version), e.approved_by, e.approved_at, e.source_ref, e.evidence_ref,
                 now, now))
        return e

    def get_entity(self, entity_id: str) -> Optional[EnterpriseEntity]:
        rows = self._query("SELECT * FROM enterprise_entities WHERE entity_id=?", (entity_id,))
        return EnterpriseEntity.model_validate(rows[0]) if rows else None

    def list_entities(self, tenant_id: str = "", entity_mode: str = "",
                      status: str = "") -> List[EnterpriseEntity]:
        sql, params = "SELECT * FROM enterprise_entities", []
        where = []
        for col, val in (("tenant_id", tenant_id), ("entity_mode", entity_mode),
                         ("status", status)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY entity_type, name_ko"
        return [EnterpriseEntity.model_validate(r) for r in self._query(sql, tuple(params))]

    def approve_entity(self, entity_id: str, actor: str) -> Optional[EnterpriseEntity]:
        """승인 = 상태를 ACTIVE 로 올리고 승인자·시각을 남긴다(§4.1 승인 가능한 버전)."""
        e = self.get_entity(entity_id)
        if not e:
            return None
        e.status, e.approved_by, e.approved_at = STATUS_ACTIVE, actor or "", self._now()
        return self.upsert_entity(e)

    # ── 노드 ──────────────────────────────────────────────────────────────
    def upsert_node(self, n: OrganizationNode) -> OrganizationNode:
        if n.node_type not in NODE_TYPES:
            raise EcmError(f"node_type 은 {NODE_TYPES} 중 하나여야 합니다.")
        if n.status not in STATUSES:
            raise EcmError(f"status 는 {STATUSES} 중 하나여야 합니다.")
        if not n.entity_id or not self.get_entity(n.entity_id):
            raise EcmError(f"존재하지 않는 entity_id 입니다: {n.entity_id}")
        if not n.name_ko:
            raise EcmError("name_ko 는 필수입니다.")
        now = self._now()
        if not n.node_id:
            n.node_id = self._uid("node")
        if n.default_parent_id == n.node_id:
            raise EcmError("자기 자신을 부모로 둘 수 없습니다.")

        # ── [D-018 ⑦] 코드 유일성 + 변경 이력 ────────────────────────────
        # ⚠️ DB `UNIQUE` 로 걸 수 없다: 유일성 범위가 `(tenant_id, entity_mode, code)` 인데
        #   `entity_mode` 는 다른 표(`enterprise_entities`)에 있다. 그래서 여기서 검증한다 —
        #   저장 시점에 막지 않으면 «조회가 fail-closed 로 거부» 만 남고, 그때는 이미 두 노드가
        #   같은 코드를 갖고 있어 **어느 쪽을 고쳐야 하는지** 사람이 판단해야 한다.
        prev = self.get_node(n.node_id)
        if (n.code or "").strip():
            mode = self._entity_mode_of(n.entity_id)
            for other in self.find_nodes_by_code(n.code, tenant_id=n.tenant_id,
                                                 entity_mode=mode):
                if other.node_id != n.node_id:
                    raise EcmError(
                        f"조직 코드 '{n.code}' 가 이미 쓰이고 있습니다"
                        f"(tenant={n.tenant_id} · mode={mode or '(전체)'} · "
                        f"node={other.node_id} · {other.name_ko}). "
                        f"코드는 그 문맥 안에서 유일해야 합니다 — 다른 코드를 쓰거나 기존 노드를 "
                        f"고치십시오.")
        # 코드가 바뀌면 **옛 코드를 별칭으로 남긴다**(버리지 않는다).
        if prev and (prev.code or "").strip() and prev.code != (n.code or ""):
            self._record_code_alias(prev.node_id, prev.code, n.tenant_id,
                                    replaced_by=(n.code or ""), reason="code_changed")

        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO organization_nodes (node_id, entity_id, tenant_id, node_type, code, "
                "name_ko, default_parent_id, path_hint, dept_id, status, effective_from, "
                "effective_to, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(node_id) DO UPDATE SET entity_id=excluded.entity_id, "
                "tenant_id=excluded.tenant_id, node_type=excluded.node_type, code=excluded.code, "
                "name_ko=excluded.name_ko, default_parent_id=excluded.default_parent_id, "
                "path_hint=excluded.path_hint, dept_id=excluded.dept_id, status=excluded.status, "
                "effective_from=excluded.effective_from, effective_to=excluded.effective_to, "
                "updated_at=excluded.updated_at",
                (n.node_id, n.entity_id, n.tenant_id, n.node_type, n.code, n.name_ko,
                 n.default_parent_id, n.path_hint, n.dept_id, n.status, n.effective_from,
                 n.effective_to, now, now))
        return n

    def get_node(self, node_id: str) -> Optional[OrganizationNode]:
        rows = self._query("SELECT * FROM organization_nodes WHERE node_id=?", (node_id,))
        return OrganizationNode.model_validate(rows[0]) if rows else None

    def find_node_by_dept(self, dept_id: str) -> Optional[OrganizationNode]:
        """부서 id 로 ECM 노드를 찾는다 — 기존 `enterprise_scope_id`(부서 id)를 노드로 승격하는
        경로(ECM-lite → E1 이행). 매핑이 없으면 None 이고 호출부는 부서 체계를 그대로 쓴다.

        ⚠️ 같은 `dept_id` 를 여러 노드가 공유한다(실측: `production` 을 4개 노드가 쓴다).
          그래서 이 조회는 "대표 노드 하나"를 돌려주는 것이며 권한 판정의 1차 근거로는 약하다 —
          `code` 로 찾는 `find_node_by_code()` 가 있으면 그쪽이 정확하다."""
        if not dept_id:
            return None
        rows = self._query("SELECT * FROM organization_nodes WHERE dept_id=? AND status=? "
                           "ORDER BY updated_at DESC LIMIT 1", (dept_id, STATUS_ACTIVE))
        return OrganizationNode.model_validate(rows[0]) if rows else None

    def find_nodes_by_dept(self, dept_id: str) -> List[OrganizationNode]:
        """부서 id 에 매핑된 **모든** 활성 노드.

        ★ [2026-07-30 실측] 하나를 고르는 조회(`find_node_by_dept`)만 있으면 중복 매핑이 보이지
          않는다. 실제 데이터에서 `production` 하나에 **형제 사업부 2개(배터리·동제련) + 공장
          2개**가 매달려 있었고 `updated_at` 이 전부 같아서 `LIMIT 1` 의 승자가 비결정적이었다 —
          즉 어느 사업부 데이터를 보게 되는지가 tie-break 로 갈렸다."""
        if not dept_id:
            return []
        rows = self._query("SELECT * FROM organization_nodes WHERE dept_id=? AND status=? "
                           "ORDER BY updated_at DESC, node_id", (dept_id, STATUS_ACTIVE))
        return [OrganizationNode.model_validate(r) for r in rows]

    def dept_mapping_conflicts(self) -> List[Dict[str, Any]]:
        """한 부서 id 에 여러 노드가 매달린 목록 — **데이터를 고쳐야 하는 일감**이다.

        ★ 코드에서 우회(모호하면 해석 실패로 처리)하는 것과 데이터를 바로잡는 것은 다르다.
          우회만 하면 그 부서 사용자는 영원히 조직 상속을 못 받는다."""
        rows = self._query(
            "SELECT dept_id, COUNT(*) AS n, GROUP_CONCAT(code) AS codes "
            "FROM organization_nodes WHERE dept_id<>'' AND status=? "
            "GROUP BY dept_id HAVING n > 1 ORDER BY n DESC", (STATUS_ACTIVE,))
        return [{"dept_id": r["dept_id"], "node_count": r["n"],
                 "codes": sorted((r["codes"] or "").split(","))} for r in rows]

    def _entity_mode_of(self, entity_id: str) -> str:
        """이 노드가 속한 엔티티의 모드. 못 찾으면 빈 문자열(= 문맥 없이 비교)."""
        rows = self._query("SELECT entity_mode FROM enterprise_entities WHERE entity_id=?",
                           (entity_id,))
        return str(rows[0].get("entity_mode") or "") if rows else ""

    def _record_code_alias(self, node_id: str, code: str, tenant_id: str,
                           replaced_by: str = "", reason: str = "") -> None:
        """[D-018 ⑦] 옛 코드를 별칭으로 남긴다.

        ⚠️ 실패를 삼키지 않는다 — 별칭을 못 남기면 그 코드로 저장된 외부 연계가 **조용히**
          끊기고, 조회는 «없음» 을 돌려준다(«권한 없음» 과 구분되지 않는다)."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO organization_node_code_aliases "
                "(alias_id, node_id, code, tenant_id, replaced_by, reason, recorded_at) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(node_id, code) DO UPDATE SET replaced_by=excluded.replaced_by, "
                "reason=excluded.reason, recorded_at=excluded.recorded_at",
                (self._uid("alias"), node_id, code, tenant_id, replaced_by, reason,
                 self._now()))

    def code_aliases_of(self, node_id: str) -> List[Dict[str, Any]]:
        """이 노드가 과거에 쓰던 코드들(최근 순). «왜 바뀌었는가» 를 함께 준다."""
        return self._query(
            "SELECT code, replaced_by, reason, recorded_at FROM organization_node_code_aliases "
            "WHERE node_id=? ORDER BY recorded_at DESC", (node_id,))

    def find_nodes_by_code_alias(self, code: str, tenant_id: str = "",
                                 entity_mode: str = "") -> List[OrganizationNode]:
        """**옛 코드**로 노드를 찾는다. 현재 코드로 찾지 못했을 때의 두 번째 경로다.

        ⚠️ 별칭이 여러 노드에 걸릴 수 있다(코드가 재사용된 경우) — 현재 코드와 **같은 규칙**으로
          호출부가 fail-closed 처리한다. 여기서 하나를 고르지 않는다."""
        if not code:
            return []
        sql = ("SELECT n.* FROM organization_node_code_aliases a "
               "JOIN organization_nodes n ON n.node_id = a.node_id "
               "JOIN enterprise_entities e ON e.entity_id = n.entity_id "
               "WHERE a.code=? AND n.status=?")
        params: List[Any] = [code, STATUS_ACTIVE]
        if tenant_id:
            sql += " AND n.tenant_id=?"
            params.append(tenant_id)
        if entity_mode:
            sql += " AND e.entity_mode=?"
            params.append(entity_mode)
        sql += " ORDER BY n.node_id"
        return [OrganizationNode.model_validate(r) for r in self._query(sql, tuple(params))]

    def find_nodes_by_code(self, code: str, tenant_id: str = "",
                           entity_mode: str = "") -> List[OrganizationNode]:
        """[D-018 ④] 조직 코드에 해당하는 **모든** 활성 노드. 문맥으로 좁힐 수 있다.

        ★ 복수 반환이 기본인 이유는 `find_nodes_by_dept` 와 같다 — 하나를 고르는 조회만 있으면
          **중복이 보이지 않는다.** 코드는 `node_id` 와 달리 유일성 제약이 없고(PK 도 UNIQUE 도
          아니다), 조직 개편·가상 복제·회사별 코드 체계에서 겹칠 수 있다.
        ⚠️ `entity_mode` 는 `enterprise_entities` 에 있으므로 JOIN 한다(`list_nodes` 와 같은 방식).
          실제/가상/경쟁사가 한 트리에 섞이면 안 된다."""
        if not code:
            return []
        sql = ("SELECT n.* FROM organization_nodes n "
               "JOIN enterprise_entities e ON e.entity_id = n.entity_id "
               "WHERE n.code=? AND n.status=?")
        params: List[Any] = [code, STATUS_ACTIVE]
        if tenant_id:
            sql += " AND n.tenant_id=?"
            params.append(tenant_id)
        if entity_mode:
            sql += " AND e.entity_mode=?"
            params.append(entity_mode)
        sql += " ORDER BY n.node_id"          # 결정적 순서(진단·비교용) — 선택 근거는 아니다
        return [OrganizationNode.model_validate(r) for r in self._query(sql, tuple(params))]

    def find_node_by_code(self, code: str, tenant_id: str = "",
                          entity_mode: str = "") -> Optional[OrganizationNode]:
        """**조직 코드**(`LS_MNM`·`MNM_BATTERY` 등)로 노드를 찾는다. **단일 후보만 돌려준다.**

        ★ [2026-07-30 실측] 이 조회가 없어서 코드가 **제3의 미해석 형태**로 남아 있었다.
          `organization_nodes.code` 에 의미 코드가 들어 있는데(LS_MNM·MNM_BATTERY·MNM_COPPER)
          해석기는 `node_id` 와 `dept_id` 만 봤다. 그 결과 코드로 저장된 범위는 조상 해석에
          실패해 **자기 자신만** 보게 되고(fail-closed), 사업부가 전사 표준 문서를 못 보는
          상태가 **조용히** 만들어졌다 — 참고문서 등록부 68건이 실제로 그 상태였다.

        ★★★ [2026-08-05 / D-018 ②] **`ORDER BY updated_at DESC LIMIT 1` 을 걷어냈다.**
          종전에는 같은 코드가 둘 이상이면 «최근에 고쳐진 것» 이 이겼다. 그것은 선택이 아니라
          **tie-break 가 조직 권한을 결정하는 것**이다 — 부서 1:N 매핑에서 이미 같은 사고를
          겪었고(`find_nodes_by_dept` 주석), 코드에서도 같은 형태가 남아 있었다.
          지금은 후보가 둘 이상이면 **`None` 을 돌려주고 경고를 남긴다**(fail-closed).
        ⚠️ 호출부가 «없음» 과 «모호함» 을 구분해야 하면 `find_nodes_by_code()` 를 직접 쓴다 —
          `resolver.resolve_scope_ref()` 가 그렇게 해서 `code_ambiguous` 를 돌려준다.
        ★ 지금 데이터에서 코드는 유일하다(실측 2026-08-05: 16개 노드, tenant+mode+code 중복 0).
          가상 복제가 `V{n}_원본코드` 접두사를 붙여 충돌을 **회피**하기 때문이다
          (`clone_service` 참조). 이 변경은 그 관행이 깨지는 날 조용히 틀리지 않게 하는 것이다."""
        rows = self.find_nodes_by_code(code, tenant_id=tenant_id, entity_mode=entity_mode)
        if len(rows) > 1:
            print(f"⚠️ [ECM] 조직 코드 '{code}' 가 노드 {len(rows)}개에 걸려 있어 하나를 고를 수 "
                  f"없습니다({', '.join(r.node_id for r in rows)}) — 해석하지 않습니다"
                  f"(tenant_id·entity_mode 로 좁히거나 코드 중복을 정리하십시오).")
            return None
        return rows[0] if rows else None

    def list_nodes(self, tenant_id: str = "", status: str = "",
                   entity_mode: str = "") -> List[OrganizationNode]:
        """`entity_mode` 를 주면 그 문맥의 노드만 — 실제/가상/경쟁사가 한 트리에 섞이면 안 된다."""
        sql = ("SELECT n.* FROM organization_nodes n "
               "JOIN enterprise_entities e ON e.entity_id = n.entity_id")
        where, params = [], []
        if tenant_id:
            where.append("n.tenant_id=?"); params.append(tenant_id)
        if status:
            where.append("n.status=?"); params.append(status)
        if entity_mode:
            where.append("e.entity_mode=?"); params.append(entity_mode)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY n.node_type, n.name_ko"
        return [OrganizationNode.model_validate(r) for r in self._query(sql, tuple(params))]

    def node_entity_mode(self, node_id: str) -> str:
        rows = self._query(
            "SELECT e.entity_mode FROM organization_nodes n "
            "JOIN enterprise_entities e ON e.entity_id = n.entity_id WHERE n.node_id=?", (node_id,))
        return rows[0]["entity_mode"] if rows else ""

    # ── 엣지 ──────────────────────────────────────────────────────────────
    def add_edge(self, e: OrganizationEdge) -> OrganizationEdge:
        if e.relation_type not in RELATION_TYPES:
            raise EcmError(f"relation_type 은 {RELATION_TYPES} 중 하나여야 합니다.")
        if not self.get_node(e.from_node_id) or not self.get_node(e.to_node_id):
            raise EcmError("존재하지 않는 노드를 연결할 수 없습니다.")
        if e.from_node_id == e.to_node_id:
            raise EcmError("자기 자신과 연결할 수 없습니다.")
        # 순환 방지 — 같은 관계 유형에서 to → from 경로가 이미 있으면 사이클이 된다.
        #   사이클이 생기면 범위 전개가 무한 재귀에 빠진다(실제로 방어하지 않으면 서버가 멈춘다).
        if self._reaches(e.to_node_id, e.from_node_id, e.relation_type):
            raise EcmError("순환 관계는 만들 수 없습니다.")
        if not e.edge_id:
            e.edge_id = self._uid("edge")
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO organization_edges (edge_id, tenant_id, from_node_id, to_node_id, "
                "relation_type, weight, effective_from, effective_to, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(from_node_id, to_node_id, relation_type, effective_from) "
                "DO UPDATE SET weight=excluded.weight, effective_to=excluded.effective_to, "
                "status=excluded.status",
                (e.edge_id, e.tenant_id, e.from_node_id, e.to_node_id, e.relation_type,
                 float(e.weight), e.effective_from, e.effective_to, e.status, self._now()))
        return e

    def _reaches(self, start: str, target: str, relation_type: str) -> bool:
        """`start` 에서 `relation_type` 을 따라 내려가 `target` 에 닿는가(사이클 검사)."""
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur == target:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(r["to_node_id"] for r in self._query(
                "SELECT to_node_id FROM organization_edges WHERE from_node_id=? "
                "AND relation_type=? AND status=?", (cur, relation_type, STATUS_ACTIVE)))
        return False

    def children(self, node_id: str, relation_type: str) -> List[str]:
        return [r["to_node_id"] for r in self._query(
            "SELECT to_node_id FROM organization_edges WHERE from_node_id=? AND relation_type=? "
            "AND status=?", (node_id, relation_type, STATUS_ACTIVE))]

    def parents(self, node_id: str, relation_type: str) -> List[str]:
        return [r["from_node_id"] for r in self._query(
            "SELECT from_node_id FROM organization_edges WHERE to_node_id=? AND relation_type=? "
            "AND status=?", (node_id, relation_type, STATUS_ACTIVE))]

    def list_edges(self, tenant_id: str = "", relation_type: str = "") -> List[OrganizationEdge]:
        sql, where, params = "SELECT * FROM organization_edges", [], []
        if tenant_id:
            where.append("tenant_id=?"); params.append(tenant_id)
        if relation_type:
            where.append("relation_type=?"); params.append(relation_type)
        if where:
            sql += " WHERE " + " AND ".join(where)
        return [OrganizationEdge.model_validate(r) for r in self._query(sql, tuple(params))]

    # ── 프로필 (E1 은 저장·조회만 — 상속 병합은 E2) ─────────────────────────
    @staticmethod
    def _row_to_profile(row: Dict[str, Any]) -> EnterpriseProfile:
        """행 → 프로필. ★ **한 곳**에서 변환한다 — 두 벌이면 한쪽만 고쳐지는 날이 온다."""
        r = dict(row)
        r["payload"] = json.loads(r.pop("payload_json", "") or "{}")
        return EnterpriseProfile.model_validate(r)

    def approve_profile(self, profile_id: str, actor: str) -> Optional[EnterpriseProfile]:
        """프로필 승인 = 상태를 ACTIVE 로 올리고 **승인자·시각을 남긴다.**

        ★★★ [2026-08-25] 이 메서드가 없어서 프로필은 **영원히 상속에 참여하지 못했다.**
          `EnterpriseProfile.is_effective` 는 `status == ACTIVE` **와** `approved_at` 을
          함께 요구하는데, `ProfileIn` 은 `approved_at` 을 받지 않는다. 즉 status 만
          ACTIVE 로 보내도 `is_effective` 는 계속 False 다.
        ⚠️ 엔터티에는 `approve_entity` 가 있는데 프로필에는 없었다 — 「통제는 있는데
          부르는 경로가 없다」의 또 한 자리다."""
        rows = self._query("SELECT * FROM enterprise_profiles WHERE profile_id=?",
                           (str(profile_id or "").strip(),))
        if not rows:
            return None
        pr = self._row_to_profile(rows[0])
        pr.status, pr.approved_by, pr.approved_at = STATUS_ACTIVE, actor or "", self._now()
        return self.upsert_profile(pr)

    def upsert_profile(self, p: EnterpriseProfile) -> EnterpriseProfile:
        if p.profile_kind not in PROFILE_KINDS:
            raise EcmError(f"profile_kind 는 {PROFILE_KINDS} 중 하나여야 합니다.")
        if p.inheritance_mode not in INHERITANCE_MODES:
            raise EcmError(f"inheritance_mode 는 {INHERITANCE_MODES} 중 하나여야 합니다.")
        if not p.scope_node_id and not p.industry_code:
            # 범위도 업종도 없으면 어디에 적용되는지 알 수 없다 → 상속 체인에 자리가 없다.
            raise EcmError("scope_node_id 또는 industry_code 중 하나는 있어야 합니다.")
        if p.scope_node_id and not self.get_node(p.scope_node_id):
            raise EcmError(f"존재하지 않는 노드입니다: {p.scope_node_id}")
        now = self._now()
        if not p.profile_id:
            p.profile_id = self._uid("prof")
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO enterprise_profiles (profile_id, tenant_id, scope_node_id, "
                "industry_code, profile_kind, payload_json, inheritance_mode, status, version, "
                "approved_by, approved_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(profile_id) DO UPDATE SET payload_json=excluded.payload_json, "
                "inheritance_mode=excluded.inheritance_mode, status=excluded.status, "
                "version=excluded.version, approved_by=excluded.approved_by, "
                "approved_at=excluded.approved_at, updated_at=excluded.updated_at",
                (p.profile_id, p.tenant_id, p.scope_node_id, p.industry_code, p.profile_kind,
                 json.dumps(p.payload, ensure_ascii=False), p.inheritance_mode, p.status,
                 int(p.version), p.approved_by, p.approved_at, now, now))
        return p

    def list_profiles(self, scope_node_id: str = "", industry_code: str = "",
                      profile_kind: str = "") -> List[EnterpriseProfile]:
        sql, where, params = "SELECT * FROM enterprise_profiles", [], []
        for col, val in (("scope_node_id", scope_node_id), ("industry_code", industry_code),
                         ("profile_kind", profile_kind)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if where:
            sql += " WHERE " + " AND ".join(where)
        return [self._row_to_profile(r) for r in self._query(sql, tuple(params))]


ecm_repository = EcmRepository()
