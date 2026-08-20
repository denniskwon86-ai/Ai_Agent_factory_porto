"""Manufacturing management ontology runtime (G2-D2/D3).

This module is deliberately separate from ``data_lineage``.  Lineage explains
technical derivation and currently overwrites an edge with the same key; the
management ontology must preserve proposals, approvals, versions and effective
periods side by side.

The store owns semantic relations only.  Referenced business objects remain in
ECM, MDM, approved datasets, G4 and the decision ledger.  A caller must provide
an object-scope resolver.  If an endpoint cannot be resolved or authorised the
whole path is removed; hidden middle nodes are never skipped.

LLM calls: zero.  Path selection and fingerprints are deterministic.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from core import app_policy
from core.paths import data_path


APPROVAL_STATES = (
    "DRAFT", "IN_REVIEW", "APPROVED", "REJECTED", "SUPERSEDED", "RETIRED",
)
ORIGINS = ("user", "derived", "suggested")
NAMESPACES = ("ecm", "mdm", "dataset", "external", "g4", "decision", "knowledge")
MAX_DEPTH = 6
MAX_PATHS = 20


class OntologyError(ValueError):
    """Invalid request or illegal governance transition."""


class OntologyIntegrityError(RuntimeError):
    """Stored ontology state is unreadable; callers should fail closed."""


class OntologyAccessError(OntologyError):
    """Access failure whose HTTP representation must hide resource existence."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_time(value: str, field: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise OntologyError(f"{field} is required.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OntologyError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normal_time(value: str, field: str) -> str:
    return _parse_time(value, field).isoformat()


@dataclass(frozen=True, order=True)
class ObjectRef:
    namespace: str
    object_type: str
    object_id: str

    def __post_init__(self) -> None:
        if self.namespace not in NAMESPACES:
            raise OntologyError(f"namespace must be one of {NAMESPACES}.")
        if not self.object_type.strip() or not self.object_id.strip():
            raise OntologyError("object_type and object_id are required.")

    @property
    def key(self) -> str:
        return f"{self.namespace}:{self.object_type}:{self.object_id}"

    def to_dict(self) -> dict:
        return {"namespace": self.namespace, "object_type": self.object_type,
                "object_id": self.object_id}


@dataclass(frozen=True)
class RelationProposal:
    subject: ObjectRef
    relation_type_id: str
    object: ObjectRef
    tenant_id: str
    enterprise_scope_id: str
    entity_mode: str
    owner_organization_id: str
    effective_from: str
    effective_to: str = ""
    origin: str = "user"
    evidence_refs: Tuple[str, ...] = ()
    source_lineage: Tuple[str, ...] = ()
    calculation_ref: str = ""
    classification: str = "INTERNAL"
    scope_type: str = "ORG_PRIVATE"
    scope_assignments: Tuple[str, ...] = ()
    supersedes_relation_id: str = ""


ObjectScopeResolver = Callable[[ObjectRef], Optional[app_policy.ResourceScope]]
ApprovalResolver = Callable[[str, str, str], bool]


_DDL = """
CREATE TABLE IF NOT EXISTS semantic_relation_types (
    relation_type_id TEXT PRIMARY KEY,
    name_ko TEXT NOT NULL,
    inverse_relation_type_id TEXT NOT NULL DEFAULT '',
    quantitative INTEGER NOT NULL DEFAULT 0,
    schema_version TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    approved_by TEXT NOT NULL DEFAULT '',
    ledger_correlation_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_relation_constraints (
    constraint_id TEXT PRIMARY KEY,
    subject_namespace TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    relation_type_id TEXT NOT NULL,
    object_namespace TEXT NOT NULL,
    object_type TEXT NOT NULL,
    required_evidence_json TEXT NOT NULL DEFAULT '[]',
    calculation_ref TEXT NOT NULL DEFAULT '',
    approval_status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(subject_namespace,subject_type,relation_type_id,object_namespace,object_type)
);

CREATE TABLE IF NOT EXISTS semantic_relations (
    relation_id TEXT PRIMARY KEY,
    subject_namespace TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    relation_type_id TEXT NOT NULL,
    object_namespace TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    supersedes_relation_id TEXT NOT NULL DEFAULT '',
    effective_from TEXT NOT NULL,
    effective_to TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL,
    enterprise_scope_id TEXT NOT NULL,
    entity_mode TEXT NOT NULL,
    scope_type TEXT NOT NULL DEFAULT 'ORG_PRIVATE',
    owner_organization_id TEXT NOT NULL,
    scope_assignments_json TEXT NOT NULL DEFAULT '[]',
    classification TEXT NOT NULL DEFAULT 'INTERNAL',
    approval_status TEXT NOT NULL,
    submitted_by TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL,
    confidence REAL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_lineage_json TEXT NOT NULL DEFAULT '[]',
    calculation_ref TEXT NOT NULL DEFAULT '',
    ledger_correlation_id TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_semantic_relations_path
  ON semantic_relations(subject_namespace,subject_type,subject_id,approval_status,effective_from);
CREATE INDEX IF NOT EXISTS idx_semantic_relations_context
  ON semantic_relations(tenant_id,entity_mode,enterprise_scope_id,approval_status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_semantic_relation_version
  ON semantic_relations(subject_namespace,subject_type,subject_id,relation_type_id,
                        object_namespace,object_type,object_id,tenant_id,entity_mode,
                        enterprise_scope_id,version);

CREATE TABLE IF NOT EXISTS semantic_relation_events (
    event_id TEXT PRIMARY KEY,
    relation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    ledger_correlation_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_semantic_relation_events
  ON semantic_relation_events(relation_id,created_at);

CREATE TABLE IF NOT EXISTS semantic_model_contracts (
    contract_id TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    contract_fingerprint TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    ledger_correlation_id TEXT NOT NULL,
    installed_by TEXT NOT NULL,
    installed_at TEXT NOT NULL,
    contract_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(contract_id,contract_version)
);
"""


class OntologyRuntime:
    """Versioned relation governance plus deterministic path traversal."""

    def __init__(self, db_path: str = data_path("ontology.db"),
                 object_scope_resolver: Optional[ObjectScopeResolver] = None,
                 approval_resolver: Optional[ApprovalResolver] = None):
        self.db_path = db_path
        self.object_scope_resolver = object_scope_resolver
        self.approval_resolver = approval_resolver
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_DDL)
            columns = {str(r[1]) for r in conn.execute(
                "PRAGMA table_info(semantic_model_contracts)").fetchall()}
            if "contract_json" not in columns:
                conn.execute("ALTER TABLE semantic_model_contracts "
                             "ADD COLUMN contract_json TEXT NOT NULL DEFAULT '{}'")

    # -- approved model contract -----------------------------------------
    def install_model_contract(self, contract: dict, actor: str) -> dict:
        """Validate and atomically install one approved ontology model contract.

        A design document is not an approved model.  The caller must provide an
        explicit approval envelope and the install is rejected unless the
        contract is ``APPROVED``.  Relation types and constraints are installed
        in the same transaction as the model fingerprint, so a half-installed
        dictionary can never be reported as ready.

        The current MVP schema has one row per ``relation_type_id``.  Therefore
        a second semantic version cannot safely coexist yet; a different model
        version is refused rather than retrospectively changing old relations.
        """
        compiled = self._compile_model_contract(contract)
        actor = (actor or "").strip()
        if not actor:
            raise OntologyError("model installation requires an actor.")
        if compiled["status"] != "APPROVED":
            raise OntologyError("only an APPROVED ontology model contract can be installed.")
        self._assert_approval(compiled["ledger_correlation_id"], "MODEL_INSTALL",
                              compiled["approved_by"])
        now = _utcnow()
        with self._lock, self._connect() as conn:
            other = conn.execute(
                "SELECT contract_version,contract_fingerprint FROM semantic_model_contracts "
                "WHERE contract_id=? AND contract_version<>?",
                (compiled["contract_id"], compiled["contract_version"])).fetchone()
            if other is not None:
                raise OntologyIntegrityError(
                    "ontology model upgrades require versioned relation dictionaries; "
                    "the current MVP refuses an in-place semantic rewrite.")

            existing = conn.execute(
                "SELECT * FROM semantic_model_contracts WHERE contract_id=? AND contract_version=?",
                (compiled["contract_id"], compiled["contract_version"])).fetchone()
            if existing is not None:
                if existing["contract_fingerprint"] != compiled["contract_fingerprint"]:
                    raise OntologyIntegrityError(
                        "the same ontology contract id/version has different content.")
                self._assert_model_materialized(conn, compiled)
                result = dict(existing)
                result.pop("contract_json", None)
                return {**result, "installed": False, "idempotent": True}

            for item in compiled["relation_types"]:
                row = conn.execute(
                    "SELECT * FROM semantic_relation_types WHERE relation_type_id=?",
                    (item["id"],)).fetchone()
                expected = (item["name_ko"], item["inverse"], int(item["quantitative"]),
                            compiled["contract_version"])
                if row is not None:
                    actual = (row["name_ko"], row["inverse_relation_type_id"],
                              int(row["quantitative"]), row["schema_version"])
                    if actual != expected or row["approval_status"] != "APPROVED":
                        raise OntologyIntegrityError(
                            f"relation type {item['id']} conflicts with the approved model.")
                    continue
                conn.execute(
                    "INSERT INTO semantic_relation_types VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item["id"], item["name_ko"], item["inverse"],
                     int(item["quantitative"]), compiled["contract_version"], "APPROVED",
                     compiled["effective_from"], "", actor, compiled["approved_by"],
                     compiled["ledger_correlation_id"], now, now))

            for item in compiled["constraints"]:
                row = conn.execute(
                    "SELECT * FROM semantic_relation_constraints WHERE subject_namespace=? AND "
                    "subject_type=? AND relation_type_id=? AND object_namespace=? AND object_type=?",
                    (item["subject_namespace"], item["subject_type"], item["relation"],
                     item["object_namespace"], item["object_type"])).fetchone()
                evidence_json = _canonical_json(tuple(item["evidence"]))
                if row is not None:
                    if (row["required_evidence_json"] != evidence_json
                            or row["calculation_ref"] != item["calculation_ref"]
                            or row["approval_status"] != "APPROVED"):
                        raise OntologyIntegrityError(
                            "an existing relation constraint conflicts with the approved model.")
                    continue
                cid = "orc_" + hashlib.sha256(
                    (f"{item['subject_namespace']}:{item['subject_type']}|{item['relation']}|"
                     f"{item['object_namespace']}:{item['object_type']}").encode()
                ).hexdigest()[:16]
                conn.execute(
                    "INSERT INTO semantic_relation_constraints VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, item["subject_namespace"], item["subject_type"], item["relation"],
                     item["object_namespace"], item["object_type"], evidence_json,
                     item["calculation_ref"], "APPROVED", actor, now))

            conn.execute(
                "INSERT INTO semantic_model_contracts VALUES(?,?,?,?,?,?,?,?,?,?)",
                (compiled["contract_id"], compiled["contract_version"],
                 compiled["contract_fingerprint"], "APPROVED", compiled["effective_from"],
                 compiled["approved_by"], compiled["ledger_correlation_id"], actor, now,
                 _canonical_json({"relation_types": compiled["relation_types"],
                                  "constraints": compiled["constraints"]})))
            return {
                "contract_id": compiled["contract_id"],
                "contract_version": compiled["contract_version"],
                "contract_fingerprint": compiled["contract_fingerprint"],
                "approval_status": "APPROVED", "effective_from": compiled["effective_from"],
                "approved_by": compiled["approved_by"],
                "ledger_correlation_id": compiled["ledger_correlation_id"],
                "installed_by": actor, "installed_at": now,
                "relation_type_count": len(compiled["relation_types"]),
                "constraint_count": len(compiled["constraints"]),
                "installed": True, "idempotent": False,
            }

    @staticmethod
    def _assert_model_materialized(conn: sqlite3.Connection, compiled: dict) -> None:
        """An install marker is not readiness; all dictionary rows must still match."""
        for item in compiled["relation_types"]:
            row = conn.execute(
                "SELECT * FROM semantic_relation_types WHERE relation_type_id=?", (item["id"],)
            ).fetchone()
            expected = (item["name_ko"], item["inverse"], int(item["quantitative"]),
                        compiled["contract_version"], "APPROVED")
            actual = ((row["name_ko"], row["inverse_relation_type_id"],
                       int(row["quantitative"]), row["schema_version"], row["approval_status"])
                      if row is not None else None)
            if actual != expected:
                raise OntologyIntegrityError(
                    f"installed ontology model is missing or has changed relation type {item['id']}.")
        for item in compiled["constraints"]:
            row = conn.execute(
                "SELECT * FROM semantic_relation_constraints WHERE subject_namespace=? AND "
                "subject_type=? AND relation_type_id=? AND object_namespace=? AND object_type=?",
                (item["subject_namespace"], item["subject_type"], item["relation"],
                 item["object_namespace"], item["object_type"])).fetchone()
            expected = (_canonical_json(tuple(item["evidence"])), item["calculation_ref"],
                        "APPROVED")
            actual = ((row["required_evidence_json"], row["calculation_ref"],
                       row["approval_status"]) if row is not None else None)
            if actual != expected:
                raise OntologyIntegrityError(
                    "installed ontology model is missing or has changed a relation constraint.")

    def validate_model_contract(self, contract: dict) -> dict:
        """Return deterministic validation metadata without changing the DB."""
        compiled = self._compile_model_contract(contract)
        return {
            "contract_id": compiled["contract_id"],
            "contract_version": compiled["contract_version"],
            "status": compiled["status"],
            "contract_fingerprint": compiled["contract_fingerprint"],
            "relation_type_count": len(compiled["relation_types"]),
            "constraint_count": len(compiled["constraints"]),
            "installable": compiled["status"] == "APPROVED",
        }

    def model_status(self, contract_id: str = "") -> dict:
        """Report installed model contracts and verify their dictionary rows still match."""
        sql = "SELECT * FROM semantic_model_contracts"
        params: Tuple[object, ...] = ()
        if (contract_id or "").strip():
            sql += " WHERE contract_id=?"
            params = ((contract_id or "").strip(),)
        sql += " ORDER BY contract_id,contract_version"
        contracts: List[dict] = []
        ready = True
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
            for row in rows:
                try:
                    material = json.loads(row.pop("contract_json") or "{}")
                    compiled = {
                        "contract_version": row["contract_version"],
                        "relation_types": material.get("relation_types") or [],
                        "constraints": material.get("constraints") or [],
                    }
                    if not compiled["relation_types"] or not compiled["constraints"]:
                        raise OntologyIntegrityError("installed model material is missing.")
                    self._assert_model_materialized(conn, compiled)
                    row["integrity_status"] = "READY"
                except Exception:
                    ready = False
                    row["integrity_status"] = "NOT_READY"
                contracts.append(row)
        status = "NOT_INSTALLED" if not rows else ("READY" if ready else "NOT_READY")
        return {"status": status, "contracts": contracts, "count": len(contracts)}

    @staticmethod
    def _compile_model_contract(contract: dict) -> dict:
        if not isinstance(contract, dict):
            raise OntologyError("ontology model contract must be an object.")
        contract_id = str(contract.get("contract_id", "") or "").strip()
        version = str(contract.get("contract_version", "") or "").strip()
        status = str(contract.get("status", "") or "").strip().upper()
        approval = contract.get("approval") if isinstance(contract.get("approval"), dict) else {}
        approved_by = str(approval.get("approved_by", "") or "").strip()
        ledger = str(approval.get("decision_ledger_id", "") or "").strip()
        effective_from = str(approval.get("effective_from", "") or "").strip()
        if not contract_id or not version or status not in ("DESIGN_ONLY", "APPROVED"):
            raise OntologyError("contract id, version and a known status are required.")
        if status == "APPROVED" and (not approved_by or not ledger or not effective_from):
            raise OntologyError(
                "approved model contracts require approver, decision ledger and effective_from.")
        normal_effective = (_normal_time(effective_from, "effective_from")
                            if effective_from else "")

        raw_types = contract.get("relation_types")
        raw_constraints = contract.get("constraints")
        if not isinstance(raw_types, list) or not raw_types:
            raise OntologyError("relation_types must be a non-empty list.")
        if not isinstance(raw_constraints, list) or not raw_constraints:
            raise OntologyError("constraints must be a non-empty list.")

        relation_types: List[dict] = []
        type_ids = set()
        for raw in raw_types:
            if not isinstance(raw, dict):
                raise OntologyError("each relation type must be an object.")
            rid = str(raw.get("id", "") or "").strip().upper()
            name = str(raw.get("name_ko", "") or "").strip()
            inverse = str(raw.get("inverse", "") or "").strip().upper()
            if not rid or not name or not inverse or rid in type_ids:
                raise OntologyError("relation type ids, names and inverses must be unique and present.")
            type_ids.add(rid)
            relation_types.append({"id": rid, "name_ko": name, "inverse": inverse,
                                   "quantitative": bool(raw.get("quantitative", False))})

        constraints: List[dict] = []
        constraint_keys = set()
        quantitative = {r["id"] for r in relation_types if r["quantitative"]}
        for raw in raw_constraints:
            if not isinstance(raw, dict):
                raise OntologyError("each constraint must be an object.")
            subject = str(raw.get("subject", "") or "").strip()
            obj = str(raw.get("object", "") or "").strip()
            relation = str(raw.get("relation", "") or "").strip().upper()
            if subject.count(":") != 1 or obj.count(":") != 1:
                raise OntologyError("constraint endpoints must use namespace:type.")
            s_ns, s_type = subject.split(":", 1)
            o_ns, o_type = obj.split(":", 1)
            ObjectRef(s_ns, s_type, "_contract")
            ObjectRef(o_ns, o_type, "_contract")
            if relation not in type_ids:
                raise OntologyError(f"constraint refers to unknown relation type {relation}.")
            evidence = tuple(sorted({str(v).strip() for v in (raw.get("evidence") or [])
                                     if str(v).strip()}))
            calc = str(raw.get("calculation_ref", "") or "").strip()
            if not evidence:
                raise OntologyError("every relation constraint requires evidence.")
            if relation in quantitative and not calc:
                raise OntologyError("quantitative relation constraints require calculation_ref.")
            key = (s_ns, s_type, relation, o_ns, o_type)
            if key in constraint_keys:
                raise OntologyError("duplicate relation constraint.")
            constraint_keys.add(key)
            constraints.append({
                "subject_namespace": s_ns, "subject_type": s_type, "relation": relation,
                "object_namespace": o_ns, "object_type": o_type,
                "evidence": evidence, "calculation_ref": calc,
            })

        relation_types.sort(key=lambda v: v["id"])
        constraints.sort(key=lambda v: (v["subject_namespace"], v["subject_type"],
                                        v["relation"], v["object_namespace"], v["object_type"]))
        material = {"contract_id": contract_id, "contract_version": version,
                    "relation_types": relation_types, "constraints": constraints}
        return {
            **material, "status": status, "approved_by": approved_by,
            "ledger_correlation_id": ledger, "effective_from": normal_effective,
            "contract_fingerprint": hashlib.sha256(
                _canonical_json(material).encode()).hexdigest(),
        }

    # -- model dictionary -------------------------------------------------
    def register_relation_type(self, relation_type_id: str, name_ko: str,
                               inverse_relation_type_id: str, quantitative: bool,
                               schema_version: str, actor: str,
                               effective_from: str, approval_status: str = "APPROVED",
                               ledger_correlation_id: str = "") -> dict:
        rid = (relation_type_id or "").strip().upper()
        if not rid or not name_ko.strip() or not schema_version.strip() or not actor.strip():
            raise OntologyError("relation type id, name, schema version and actor are required.")
        if approval_status not in APPROVAL_STATES:
            raise OntologyError("invalid approval status.")
        if approval_status == "APPROVED" and not ledger_correlation_id.strip():
            raise OntologyError("approved relation types require a decision-ledger correlation id.")
        now = _utcnow()
        start = _normal_time(effective_from, "effective_from")
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO semantic_relation_types VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(relation_type_id) DO UPDATE SET "
                "name_ko=excluded.name_ko,inverse_relation_type_id=excluded.inverse_relation_type_id,"
                "quantitative=excluded.quantitative,schema_version=excluded.schema_version,"
                "approval_status=excluded.approval_status,effective_from=excluded.effective_from,"
                "approved_by=excluded.approved_by,ledger_correlation_id=excluded.ledger_correlation_id,"
                "updated_at=excluded.updated_at",
                (rid, name_ko.strip(), inverse_relation_type_id.strip().upper(), int(quantitative),
                 schema_version.strip(), approval_status, start, "", actor.strip(),
                 actor.strip() if approval_status == "APPROVED" else "",
                 ledger_correlation_id.strip(), now, now))
            return dict(conn.execute(
                "SELECT * FROM semantic_relation_types WHERE relation_type_id=?", (rid,)).fetchone())

    def register_constraint(self, subject_namespace: str, subject_type: str,
                            relation_type_id: str, object_namespace: str,
                            object_type: str, evidence: Sequence[str], actor: str,
                            calculation_ref: str = "") -> dict:
        s = ObjectRef(subject_namespace, subject_type, "_contract")
        o = ObjectRef(object_namespace, object_type, "_contract")
        rid = relation_type_id.strip().upper()
        if not actor.strip() or not rid:
            raise OntologyError("actor and relation type are required.")
        evid = tuple(sorted({str(v).strip() for v in evidence if str(v).strip()}))
        cid = "orc_" + hashlib.sha256(
            f"{s.namespace}:{s.object_type}|{rid}|{o.namespace}:{o.object_type}".encode()
        ).hexdigest()[:16]
        now = _utcnow()
        with self._lock, self._connect() as conn:
            rt = conn.execute("SELECT approval_status FROM semantic_relation_types "
                              "WHERE relation_type_id=?", (rid,)).fetchone()
            if rt is None or rt["approval_status"] != "APPROVED":
                raise OntologyError("the relation type is not approved.")
            conn.execute(
                "INSERT INTO semantic_relation_constraints VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(subject_namespace,subject_type,relation_type_id,object_namespace,object_type) "
                "DO UPDATE SET required_evidence_json=excluded.required_evidence_json,"
                "calculation_ref=excluded.calculation_ref,approval_status='APPROVED'",
                (cid, s.namespace, s.object_type, rid, o.namespace, o.object_type,
                 _canonical_json(evid), calculation_ref.strip(), "APPROVED", actor.strip(), now))
            return dict(conn.execute("SELECT * FROM semantic_relation_constraints "
                                     "WHERE constraint_id=?", (cid,)).fetchone())

    # -- relation lifecycle ----------------------------------------------
    def propose_relation(self, proposal: RelationProposal, actor: str,
                         subject: app_policy.Subject) -> dict:
        if not actor.strip():
            raise OntologyError("actor is required.")
        if proposal.origin not in ORIGINS:
            raise OntologyError(f"origin must be one of {ORIGINS}.")
        if not proposal.tenant_id.strip() or not proposal.enterprise_scope_id.strip():
            raise OntologyError("tenant and enterprise scope are required; unbound is not shared.")
        if not proposal.entity_mode.strip() or not proposal.owner_organization_id.strip():
            raise OntologyError("entity mode and owner organisation are required.")
        start = _normal_time(proposal.effective_from, "effective_from")
        end = (_normal_time(proposal.effective_to, "effective_to")
               if proposal.effective_to.strip() else "")
        if end and _parse_time(end, "effective_to") <= _parse_time(start, "effective_from"):
            raise OntologyError("effective_to must be later than effective_from.")
        rid = proposal.relation_type_id.strip().upper()
        self._assert_proposal_access(subject, proposal)
        with self._lock, self._connect() as conn:
            constraint = self._constraint(conn, proposal.subject, rid, proposal.object)
            required = tuple(json.loads(constraint["required_evidence_json"] or "[]"))
            evidence = tuple(sorted({v.strip() for v in proposal.evidence_refs if v.strip()}))
            if required and not evidence:
                raise OntologyError("this relation requires evidence.")
            calc = proposal.calculation_ref.strip()
            expected_calc = str(constraint["calculation_ref"] or "").strip()
            if expected_calc and calc != expected_calc:
                raise OntologyError("the approved calculation reference is required.")
            relation_id = "or_" + uuid.uuid4().hex
            version = self._next_version(conn, proposal, rid)
            now = _utcnow()
            confidence = None if proposal.origin == "user" else 1.0
            conn.execute(
                "INSERT INTO semantic_relations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (relation_id, proposal.subject.namespace, proposal.subject.object_type,
                 proposal.subject.object_id, rid, proposal.object.namespace,
                 proposal.object.object_type, proposal.object.object_id, version,
                 proposal.supersedes_relation_id.strip(), start, end, proposal.tenant_id.strip(),
                 proposal.enterprise_scope_id.strip(), proposal.entity_mode.strip(),
                 proposal.scope_type.strip() or "ORG_PRIVATE", proposal.owner_organization_id.strip(),
                 _canonical_json(tuple(proposal.scope_assignments)), proposal.classification.strip(),
                 "DRAFT", "", "", "", proposal.origin, confidence,
                 _canonical_json(evidence), _canonical_json(tuple(proposal.source_lineage)), calc,
                 "", actor.strip(), now, now))
            self._event(conn, relation_id, "PROPOSED", "", "DRAFT", actor, "", "")
            return self._relation(conn, relation_id)

    def submit(self, relation_id: str, actor: str, subject: app_policy.Subject) -> dict:
        return self._transition(relation_id, actor, subject, "DRAFT", "IN_REVIEW", "SUBMITTED")

    def approve(self, relation_id: str, actor: str, ledger_correlation_id: str,
                subject: app_policy.Subject) -> dict:
        if not ledger_correlation_id.strip():
            raise OntologyError("approval requires a decision-ledger correlation id.")
        self._assert_approval(ledger_correlation_id, "RELATION_APPROVE", actor)
        with self._lock, self._connect() as conn:
            row = self._relation(conn, relation_id)
            self._assert_relation_access(subject, row, app_policy.MANAGE)
            if row["approval_status"] != "IN_REVIEW":
                raise OntologyError("only IN_REVIEW relations can be approved.")
            if row["submitted_by"] == actor.strip():
                raise OntologyError("self approval is forbidden.")
            if not json.loads(row["evidence_refs_json"] or "[]"):
                raise OntologyError("a relation without evidence cannot be approved.")
            self._assert_no_overlap(conn, row)
            now = _utcnow()
            conn.execute("UPDATE semantic_relations SET approval_status='APPROVED',approved_by=?,"
                         "approved_at=?,ledger_correlation_id=?,updated_at=? WHERE relation_id=?",
                         (actor.strip(), now, ledger_correlation_id.strip(), now, relation_id))
            self._event(conn, relation_id, "APPROVED", "IN_REVIEW", "APPROVED", actor,
                        "", ledger_correlation_id)
            return self._relation(conn, relation_id)

    def reject(self, relation_id: str, actor: str, reason: str,
               subject: app_policy.Subject) -> dict:
        if not reason.strip():
            raise OntologyError("rejection reason is required.")
        return self._transition(relation_id, actor, subject, "IN_REVIEW", "REJECTED",
                                "REJECTED", reason)

    def retire(self, relation_id: str, actor: str, reason: str,
               ledger_correlation_id: str, subject: app_policy.Subject) -> dict:
        if not reason.strip() or not ledger_correlation_id.strip():
            raise OntologyError("retirement reason and ledger correlation are required.")
        self._assert_approval(ledger_correlation_id, "RELATION_RETIRE", actor)
        return self._transition(relation_id, actor, subject, "APPROVED", "RETIRED", "RETIRED",
                                reason, ledger_correlation_id)

    # -- deterministic paths ---------------------------------------------
    def find_paths(self, subject: app_policy.Subject, roots: Sequence[ObjectRef],
                   target_types: Sequence[str], relation_types: Sequence[str], as_of: str,
                   max_depth: int = MAX_DEPTH, max_paths: int = MAX_PATHS) -> dict:
        if self.object_scope_resolver is None:
            raise OntologyIntegrityError("object scope resolver is not configured.")
        if not roots:
            raise OntologyError("at least one root is required.")
        if not (1 <= int(max_depth) <= MAX_DEPTH):
            raise OntologyError(f"max_depth must be between 1 and {MAX_DEPTH}.")
        instant = _normal_time(as_of, "as_of")
        allowed_relations = tuple(sorted({v.strip().upper() for v in relation_types if v.strip()}))
        targets = frozenset(v.strip() for v in target_types if v.strip())
        edges = self._visible_edges(subject, instant, allowed_relations)
        adjacency: Dict[ObjectRef, List[dict]] = {}
        for edge in edges:
            adjacency.setdefault(self._subject_ref(edge), []).append(edge)
        for values in adjacency.values():
            values.sort(key=lambda e: (e["relation_type_id"], e["object_namespace"],
                                       e["object_type"], e["object_id"], e["relation_id"]))

        paths: List[dict] = []
        for root in sorted(set(roots)):
            if not self._object_visible(subject, root):
                continue
            queue = deque([(root, tuple(), (root,))])
            while queue and len(paths) < min(max_paths, MAX_PATHS):
                node, path_edges, path_nodes = queue.popleft()
                if len(path_edges) >= max_depth:
                    continue
                for edge in adjacency.get(node, ()):  # no hidden-node bypass
                    nxt = self._object_ref(edge)
                    if nxt in path_nodes or not self._object_visible(subject, nxt):
                        continue
                    next_edges = path_edges + (edge,)
                    next_nodes = path_nodes + (nxt,)
                    if not targets or nxt.object_type in targets:
                        paths.append(self._path(next_nodes, next_edges))
                        if len(paths) >= min(max_paths, MAX_PATHS):
                            break
                    queue.append((nxt, next_edges, next_nodes))

        paths.sort(key=lambda p: (len(p["edges"]), p["path_fingerprint"]))
        query_payload = {
            "roots": [r.to_dict() for r in sorted(set(roots))],
            "target_types": sorted(targets), "relation_types": list(allowed_relations),
            "as_of": instant, "max_depth": int(max_depth),
            "context": self._context_fingerprint(subject),
        }
        query_id = "oq_" + hashlib.sha256(_canonical_json(query_payload).encode()).hexdigest()[:24]
        return {
            "query_id": query_id,
            "status": "COMPLETE" if paths else "NO_VISIBLE_PATH",
            "as_of": instant,
            "paths": paths,
            # Do not expose denied or unapproved counts.  Context omission needs a separate
            # positive entitlement check and is intentionally absent in this minimal runtime.
            "context_omitted": None,
            "warnings": [],
        }

    def relation_evidence(self, subject: app_policy.Subject, relation_id: str,
                          as_of: str) -> Optional[dict]:
        """Return one authorised relation with evidence, or ``None`` without a side channel."""
        if self.object_scope_resolver is None:
            raise OntologyIntegrityError("object scope resolver is not configured.")
        instant_text = _normal_time(as_of, "as_of")
        instant = _parse_time(instant_text, "as_of")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM semantic_relations WHERE relation_id=?",
                               ((relation_id or "").strip(),)).fetchone()
        if row is None:
            return None
        item = dict(row)
        if item["approval_status"] != "APPROVED" or not self._active_at(item, instant):
            return None
        if not app_policy.decide(subject, self._relation_scope(item), app_policy.READ).allowed:
            return None
        sref, oref = self._subject_ref(item), self._object_ref(item)
        if not self._object_visible(subject, sref) or not self._object_visible(subject, oref):
            return None
        return {
            "relation_id": item["relation_id"], "relation_type_id": item["relation_type_id"],
            "subject": sref.to_dict(), "object": oref.to_dict(), "version": item["version"],
            "effective_from": item["effective_from"], "effective_to": item["effective_to"],
            "origin": item["origin"], "evidence_refs": json.loads(item["evidence_refs_json"]),
            "source_lineage": json.loads(item["source_lineage_json"]),
            "calculation_ref": item["calculation_ref"],
            "ledger_correlation_id": item["ledger_correlation_id"],
            "as_of": instant_text,
        }

    # -- internals --------------------------------------------------------
    def _constraint(self, conn: sqlite3.Connection, s: ObjectRef, rid: str,
                    o: ObjectRef) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM semantic_relation_constraints WHERE subject_namespace=? AND "
            "subject_type=? AND relation_type_id=? AND object_namespace=? AND object_type=? "
            "AND approval_status='APPROVED'",
            (s.namespace, s.object_type, rid, o.namespace, o.object_type)).fetchone()
        if row is None:
            raise OntologyError("the subject-relation-object combination is not approved.")
        return row

    def _next_version(self, conn: sqlite3.Connection, p: RelationProposal, rid: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(version),0) AS v FROM semantic_relations WHERE "
            "subject_namespace=? AND subject_type=? AND subject_id=? AND relation_type_id=? "
            "AND object_namespace=? AND object_type=? AND object_id=? AND tenant_id=? "
            "AND entity_mode=? AND enterprise_scope_id=?",
            (p.subject.namespace, p.subject.object_type, p.subject.object_id, rid,
             p.object.namespace, p.object.object_type, p.object.object_id, p.tenant_id,
             p.entity_mode, p.enterprise_scope_id)).fetchone()
        return int(row["v"]) + 1

    def _relation(self, conn: sqlite3.Connection, relation_id: str) -> dict:
        row = conn.execute("SELECT * FROM semantic_relations WHERE relation_id=?",
                           (relation_id,)).fetchone()
        if row is None:
            raise OntologyError("relation was not found.")
        return dict(row)

    def _event(self, conn: sqlite3.Connection, relation_id: str, event_type: str,
               old: str, new: str, actor: str, reason: str, ledger: str) -> None:
        conn.execute("INSERT INTO semantic_relation_events VALUES(?,?,?,?,?,?,?,?,?)",
                     ("ore_" + uuid.uuid4().hex, relation_id, event_type, old, new,
                      actor.strip(), reason.strip(), ledger.strip(), _utcnow()))

    def _transition(self, relation_id: str, actor: str, subject: app_policy.Subject,
                    old: str, new: str,
                    event: str, reason: str = "", ledger: str = "") -> dict:
        if not actor.strip():
            raise OntologyError("actor is required.")
        with self._lock, self._connect() as conn:
            row = self._relation(conn, relation_id)
            self._assert_relation_access(subject, row, app_policy.WRITE)
            if row["approval_status"] != old:
                raise OntologyError(f"only {old} relations can transition to {new}.")
            now = _utcnow()
            submitted = actor.strip() if new == "IN_REVIEW" else row["submitted_by"]
            conn.execute("UPDATE semantic_relations SET approval_status=?,submitted_by=?,"
                         "ledger_correlation_id=CASE WHEN ?<>'' THEN ? ELSE ledger_correlation_id END,"
                         "updated_at=? WHERE relation_id=?",
                         (new, submitted, ledger, ledger, now, relation_id))
            self._event(conn, relation_id, event, old, new, actor, reason, ledger)
            return self._relation(conn, relation_id)

    def _assert_proposal_access(self, subject: app_policy.Subject,
                                proposal: RelationProposal) -> None:
        """A proposal needs both endpoint visibility and write access to its scope."""
        if self.object_scope_resolver is None:
            raise OntologyIntegrityError("object scope resolver is not configured.")
        if not self._object_visible(subject, proposal.subject):
            raise OntologyAccessError("the relation endpoints are not available in this context.")
        if not self._object_visible(subject, proposal.object):
            raise OntologyAccessError("the relation endpoints are not available in this context.")
        scope = app_policy.ResourceScope(
            tenant_id=proposal.tenant_id, entity_mode=proposal.entity_mode,
            scope_node_id=proposal.enterprise_scope_id,
            owner_dept_id=proposal.owner_organization_id,
            binding_state=app_policy.BOUND, status="active")
        if not app_policy.decide(subject, scope, app_policy.WRITE).allowed:
            raise OntologyAccessError("the relation cannot be changed in this context.")

    @staticmethod
    def _relation_scope(row: dict) -> app_policy.ResourceScope:
        return app_policy.ResourceScope(
            tenant_id=row["tenant_id"], entity_mode=row["entity_mode"],
            scope_node_id=row["enterprise_scope_id"],
            owner_dept_id=row["owner_organization_id"],
            binding_state=app_policy.BOUND, status="active")

    def _assert_relation_access(self, subject: app_policy.Subject, row: dict,
                                action: str) -> None:
        if not app_policy.decide(subject, self._relation_scope(row), action).allowed:
            raise OntologyAccessError("the relation cannot be changed in this context.")
        if self.object_scope_resolver is None:
            raise OntologyIntegrityError("object scope resolver is not configured.")
        if not self._object_visible(subject, self._subject_ref(row)):
            raise OntologyAccessError("the relation endpoints are not available in this context.")
        if not self._object_visible(subject, self._object_ref(row)):
            raise OntologyAccessError("the relation endpoints are not available in this context.")

    def _assert_approval(self, ledger_id: str, action: str, actor: str) -> None:
        """A correlation string is not approval; an external ledger must attest it."""
        if self.approval_resolver is None:
            raise OntologyIntegrityError("decision-ledger approval resolver is not configured.")
        try:
            approved = bool(self.approval_resolver(
                (ledger_id or "").strip(), (action or "").strip(), (actor or "").strip()))
        except Exception as exc:
            raise OntologyIntegrityError("decision-ledger approval could not be verified.") from exc
        if not approved:
            raise OntologyError("the decision-ledger approval is not valid for this action.")

    def _assert_no_overlap(self, conn: sqlite3.Connection, candidate: dict) -> None:
        start = _parse_time(candidate["effective_from"], "effective_from")
        end = (_parse_time(candidate["effective_to"], "effective_to")
               if candidate["effective_to"] else datetime.max.replace(tzinfo=timezone.utc))
        rows = conn.execute(
            "SELECT * FROM semantic_relations WHERE approval_status='APPROVED' AND "
            "subject_namespace=? AND subject_type=? AND subject_id=? AND relation_type_id=? AND "
            "object_namespace=? AND object_type=? AND object_id=? AND tenant_id=? AND entity_mode=? "
            "AND enterprise_scope_id=? AND relation_id<>?",
            (candidate["subject_namespace"], candidate["subject_type"], candidate["subject_id"],
             candidate["relation_type_id"], candidate["object_namespace"], candidate["object_type"],
             candidate["object_id"], candidate["tenant_id"], candidate["entity_mode"],
             candidate["enterprise_scope_id"], candidate["relation_id"])).fetchall()
        for row in rows:
            other_start = _parse_time(row["effective_from"], "effective_from")
            other_end = (_parse_time(row["effective_to"], "effective_to")
                         if row["effective_to"] else datetime.max.replace(tzinfo=timezone.utc))
            if start < other_end and other_start < end:
                raise OntologyError("an approved relation already covers this effective period.")

    @staticmethod
    def _active_at(row: dict, instant: datetime) -> bool:
        start = _parse_time(row["effective_from"], "effective_from")
        end = (_parse_time(row["effective_to"], "effective_to")
               if row["effective_to"] else datetime.max.replace(tzinfo=timezone.utc))
        return start <= instant < end

    def _visible_edges(self, subject: app_policy.Subject, as_of: str,
                       relation_types: Tuple[str, ...]) -> List[dict]:
        ctx = subject.ctx or {}
        tenant = str(ctx.get("tenant_id", "") or "").strip()
        mode = str(ctx.get("entity_mode", "") or "").strip()
        if not tenant or not mode:
            raise OntologyIntegrityError("subject context is incomplete.")
        sql = "SELECT * FROM semantic_relations WHERE approval_status='APPROVED' AND tenant_id=? AND entity_mode=?"
        params: List[object] = [tenant, mode]
        if relation_types:
            sql += " AND relation_type_id IN (%s)" % ",".join("?" for _ in relation_types)
            params.extend(relation_types)
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
        instant = _parse_time(as_of, "as_of")
        visible: List[dict] = []
        for row in rows:
            if not self._active_at(row, instant):
                continue
            scope = app_policy.ResourceScope(
                tenant_id=row["tenant_id"], entity_mode=row["entity_mode"],
                scope_node_id=row["enterprise_scope_id"],
                owner_dept_id=row["owner_organization_id"], binding_state=app_policy.BOUND,
                status="active")
            if app_policy.decide(subject, scope, app_policy.READ).allowed:
                visible.append(row)
        return visible

    def _object_visible(self, subject: app_policy.Subject, ref: ObjectRef) -> bool:
        try:
            scope = self.object_scope_resolver(ref) if self.object_scope_resolver else None
        except Exception as exc:
            raise OntologyIntegrityError("object scope resolution failed.") from exc
        return bool(scope and app_policy.decide(subject, scope, app_policy.READ).allowed)

    @staticmethod
    def _subject_ref(row: dict) -> ObjectRef:
        return ObjectRef(row["subject_namespace"], row["subject_type"], row["subject_id"])

    @staticmethod
    def _object_ref(row: dict) -> ObjectRef:
        return ObjectRef(row["object_namespace"], row["object_type"], row["object_id"])

    @staticmethod
    def _context_fingerprint(subject: app_policy.Subject) -> str:
        ctx = subject.ctx or {}
        payload = {"user_id": subject.user_id, "tenant_id": ctx.get("tenant_id", ""),
                   "entity_mode": ctx.get("entity_mode", ""),
                   "scope_node_id": ctx.get("scope_node_id", "")}
        return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()

    @staticmethod
    def _path(nodes: Sequence[ObjectRef], edges: Sequence[dict]) -> dict:
        edge_payload = [{
            "relation_id": e["relation_id"], "relation_type_id": e["relation_type_id"],
            "version": e["version"], "evidence_refs": json.loads(e["evidence_refs_json"]),
            "calculation_ref": e["calculation_ref"], "effective_from": e["effective_from"],
            "effective_to": e["effective_to"], "ledger_correlation_id": e["ledger_correlation_id"],
        } for e in edges]
        payload = {"nodes": [n.to_dict() for n in nodes], "edges": edge_payload}
        return {**payload, "path_fingerprint": hashlib.sha256(
            _canonical_json(payload).encode()).hexdigest()}


ontology_runtime = OntologyRuntime()
