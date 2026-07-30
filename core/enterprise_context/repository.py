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

_DB_PATH = os.path.join("data", "enterprise_context.db")

_DDL = """
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
        if e.entity_mode == "VIRTUAL" and not e.base_entity_id:
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

    def find_node_by_code(self, code: str) -> Optional[OrganizationNode]:
        """**조직 코드**(`LS_MNM`·`MNM_BATTERY` 등)로 노드를 찾는다.

        ★ [2026-07-30 실측] 이 조회가 없어서 코드가 **제3의 미해석 형태**로 남아 있었다.
          `organization_nodes.code` 에 의미 코드가 들어 있는데(LS_MNM·MNM_BATTERY·MNM_COPPER)
          해석기는 `node_id` 와 `dept_id` 만 봤다. 그 결과 코드로 저장된 범위는 조상 해석에
          실패해 **자기 자신만** 보게 되고(fail-closed), 사업부가 전사 표준 문서를 못 보는
          상태가 **조용히** 만들어졌다 — 참고문서 등록부 68건이 실제로 그 상태였다."""
        if not code:
            return None
        rows = self._query("SELECT * FROM organization_nodes WHERE code=? AND status=? "
                           "ORDER BY updated_at DESC LIMIT 1", (code, STATUS_ACTIVE))
        return OrganizationNode.model_validate(rows[0]) if rows else None

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
        out = []
        for r in self._query(sql, tuple(params)):
            r["payload"] = json.loads(r.pop("payload_json") or "{}")
            out.append(EnterpriseProfile.model_validate(r))
        return out


ecm_repository = EcmRepository()
