"""회사 승인 서명권 정본. 직함/관리자 플래그만으로 서명권을 만들지 않는다.

정책과 head는 DP DB에, 승인 증명은 기존 Decision Ledger에 둔다. 서로 다른
DB의 분산 원자성을 주장하지 않는다. 미결속 원장 사건은 서명권이 아니며,
사용할 때마다 원장·조직·PDP를 다시 검사한다. 운영 정책 자동 시드는 없다.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from core.data_preparation import models as m

KINDS = ("DATA_OWNER", "EXECUTIVE")
USES = ("OPERATIONAL", "MANAGEMENT")
APPROVED = "CERTIFICATION_POLICY_APPROVED"
REVOKED = "CERTIFICATION_POLICY_REVOKED"
SUBJECT_TYPE = "certification_policy"
DDL = """
CREATE TABLE IF NOT EXISTS certification_policies (
 policy_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
 tenant_id TEXT NOT NULL, context_root_id TEXT NOT NULL, entity_mode TEXT NOT NULL,
 digest TEXT NOT NULL UNIQUE, document_json TEXT NOT NULL,
 approval_event_id TEXT NOT NULL, approved_by TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(tenant_id, context_root_id, entity_mode, revision)
);
CREATE TABLE IF NOT EXISTS certification_policy_heads (
 tenant_id TEXT NOT NULL, context_root_id TEXT NOT NULL, entity_mode TEXT NOT NULL,
 policy_id TEXT NOT NULL,
 PRIMARY KEY(tenant_id, context_root_id, entity_mode)
);
CREATE TRIGGER IF NOT EXISTS certification_policy_no_update
BEFORE UPDATE ON certification_policies BEGIN SELECT RAISE(ABORT, 'immutable certification policy'); END;
CREATE TRIGGER IF NOT EXISTS certification_policy_no_delete
BEFORE DELETE ON certification_policies BEGIN SELECT RAISE(ABORT, 'immutable certification policy'); END;
"""


class CertificationError(m.DataPreparationError):
    def __init__(self, reason_code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def instant(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise CertificationError("POLICY_INVALID", "시간대가 명시된 유효 시각이 필요합니다.", 422) from exc


def context_root(tenant_id: str, entity_mode: str, scope_node_id: str) -> str:
    """표시용 default_parent가 아닌 살아 있는 OPERATING_PARENT 정본을 따른다."""
    from core.enterprise_context.repository import ecm_repository
    from core.enterprise_context.models import REL_OPERATING_PARENT, STATUS_ACTIVE
    seen = set()
    current = scope_node_id
    try:
        while current and current not in seen:
            seen.add(current)
            node = ecm_repository.get_node(current)
            entity = ecm_repository.get_entity(node.entity_id) if node else None
            if (not node or not entity or node.status != STATUS_ACTIVE or entity.status != STATUS_ACTIVE
                    or node.tenant_id != tenant_id or entity.tenant_id != tenant_id
                    or entity.entity_mode != entity_mode):
                break
            parents = ecm_repository.parents(current, REL_OPERATING_PARENT)
            if not parents:
                return current
            if len(parents) != 1:
                break
            current = parents[0]
    except Exception as exc:
        raise CertificationError("CONTEXT_UNAVAILABLE", "조직 문맥을 확인하지 못했습니다.", 503) from exc
    raise CertificationError("CONTEXT_UNAVAILABLE", "단일한 활성 조직 루트를 확정할 수 없습니다.", 503)


def _active_user(actor: str) -> dict:
    from core.data_preparation import ownership_binding as ob
    try:
        return ob._require_active_user(actor)
    except ob.OwnershipError as exc:
        raise CertificationError("SIGNER_INELIGIBLE", "활성 등록 사용자만 서명할 수 있습니다.", 403) from exc
    except (ob.OwnershipUnavailable, ob.OwnershipIntegrityError) as exc:
        raise CertificationError("AUTHORITY_UNAVAILABLE", "사용자 정본을 확인하지 못했습니다.", 503) from exc


def require_context(subject: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    """소유권 상세 조회보다 먼저 현재 문맥과 저장된 subject 루트를 검사한다."""
    from core.app_policy import _scope_covers
    if (not context or context.get("tenant_id") != subject.get("tenant_id")
            or context.get("entity_mode") != subject.get("entity_mode")):
        raise CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    selected = str(context.get("scope_node_id") or "")
    if not selected:
        raise CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    root = context_root(str(context["tenant_id"]), str(context["entity_mode"]), selected)
    actual_root = context_root(str(subject["tenant_id"]), str(subject["entity_mode"]), str(subject["scope_node_id"]))
    if root != actual_root or (subject.get("context_root_id") and root != subject["context_root_id"]):
        raise CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    covers, failed = _scope_covers(selected, str(subject["scope_node_id"]))
    if failed:
        raise CertificationError("CONTEXT_UNAVAILABLE", "현재 선택 범위를 확인하지 못했습니다.", 503)
    if not covers:
        raise CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    return root


def require_read(subject: Mapping[str, Any], actor: str, context: Mapping[str, Any]) -> dict:
    """현재 승인 소유부서에 대한 PDP를 검사한다. 관리자도 문맥에서 면제하지 않는다."""
    from core import app_policy as pdp
    from core.org_directory import org_directory
    root = require_context(subject, context)
    user = _active_user(actor)
    try:
        scope = org_directory.resolve_scope(actor, fresh=True)
        result = pdp.decide(pdp.Subject(user_id=actor, scope=scope, ctx=dict(context)),
                            pdp.ResourceScope(tenant_id=subject["tenant_id"], entity_mode=subject["entity_mode"],
                                              scope_node_id=subject["scope_node_id"],
                                              owner_dept_id=subject["owner_dept_id"], binding_state=pdp.BOUND), pdp.READ)
    except Exception as exc:
        raise CertificationError("AUTHORITY_UNAVAILABLE", "현재 자료 접근권을 확인하지 못했습니다.", 503) from exc
    if not result.allowed:
        raise CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    return {"user": user, "scope": scope, "context_root_id": root}


def validate_document(document: Mapping[str, Any]) -> dict:
    """정책 전체를 명시한다. 빠진 필드는 권한 기본값으로 보충하지 않는다."""
    try:
        doc = json.loads(canonical(document))
        if set(doc) != {"required_reviews", "grants", "delegations", "allow_same_actor", "min_evidence_length"}:
            raise ValueError("fields")
        if type(doc["allow_same_actor"]) is not bool or type(doc["min_evidence_length"]) is not int or doc["min_evidence_length"] < 1:
            raise ValueError("validation")
        if not isinstance(doc["required_reviews"], dict) or not isinstance(doc["grants"], dict):
            raise ValueError("mapping objects required")
        if set(doc["required_reviews"]) != set(USES) or set(doc["grants"]) != set(KINDS):
            raise ValueError("kinds")
        for kinds in doc["required_reviews"].values():
            if (not isinstance(kinds, list) or "DATA_OWNER" not in kinds or len(set(kinds)) != len(kinds)
                    or any(k not in KINDS for k in kinds)):
                raise ValueError("reviews")
        for kind, grants in doc["grants"].items():
            if not isinstance(grants, list) or not grants:
                raise ValueError("grants")
            for grant in grants:
                if not isinstance(grant, dict) or set(grant) != {"dept_id", "role", "scope_node_id"}:
                    raise ValueError("grant fields")
                if (grant["role"] not in ("viewer", "member", "manager")
                        or not isinstance(grant["dept_id"], str) or not grant["dept_id"].strip()
                        or not isinstance(grant["scope_node_id"], str) or not grant["scope_node_id"].strip()):
                    raise ValueError("grant")
        if not isinstance(doc["delegations"], list):
            raise ValueError("delegations")
        for delegation in doc["delegations"]:
            if not isinstance(delegation, dict) or set(delegation) != {"actor", "delegator", "review_kind", "scope_node_id", "valid_from", "valid_to", "evidence_ref"}:
                raise ValueError("delegation fields")
            if any(not isinstance(v, str) or not v.strip() for v in delegation.values()):
                raise ValueError("delegation values")
            if (delegation["review_kind"] not in KINDS or delegation["actor"] == delegation["delegator"]
                    or instant(delegation["valid_from"]) >= instant(delegation["valid_to"])):
                raise ValueError("delegation")
        return doc
    except (ValueError, TypeError, KeyError) as exc:
        raise CertificationError("POLICY_INVALID", "회사 서명 정책의 필드·서명 종류·역할·위임을 확인하십시오.", 422) from exc


def approve_policy(store: Any, *, tenant_id: str, entity_mode: str, context_root_id: str,
                   document: Mapping[str, Any], actor: str, evidence_ref: str,
                   expected_policy_id: str = "") -> dict:
    """명시 회사 승인 근거를 등록하는 관리 명령. 서명권 자체와 구분한다.

    기존 표준 승인 관리권을 재사용한다. 본인이 관리자라는 이유로 어떤 서명
    grant도 자동 추가하지 않는다. 호출 자체가 승인 행위이므로 자동 실행 금지.
    """
    from core.data_preparation import ownership_binding as ob
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.repository import ecm_repository
    ob.require_approval_authority(actor)
    doc = validate_document(document)
    if not evidence_ref.strip():
        raise CertificationError("APPROVAL_EVIDENCE_REQUIRED", "회사 승인 근거가 필요합니다.", 422)
    if context_root(tenant_id, entity_mode, context_root_id) != context_root_id:
        raise CertificationError("POLICY_INVALID", "정책은 실제 조직 루트에 귀속되어야 합니다.", 422)
    root_node = ecm_repository.get_node(context_root_id)
    for grants in doc["grants"].values():
        for grant in grants:
            if context_root(tenant_id, entity_mode, grant["scope_node_id"]) != context_root_id:
                raise CertificationError("POLICY_INVALID", "다른 회사 범위에 서명권을 부여할 수 없습니다.", 422)
            alive, failed = ob._dept_alive(grant["dept_id"])
            if failed or not alive:
                raise CertificationError("POLICY_INVALID", "서명 역할의 활성 부서가 필요합니다.", 422)
    for delegation in doc["delegations"]:
        if context_root(tenant_id, entity_mode, delegation["scope_node_id"]) != context_root_id:
            raise CertificationError("POLICY_INVALID", "위임 범위가 회사 루트와 다릅니다.", 422)
        _active_user(delegation["actor"])
        _active_user(delegation["delegator"])
    with store.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT policy_id FROM certification_policy_heads WHERE tenant_id=? AND context_root_id=? AND entity_mode=?",
                               (tenant_id, context_root_id, entity_mode)).fetchone()
        if (current[0] if current else "") != expected_policy_id:
            raise CertificationError("POLICY_CONFLICT", "현재 정책이 변경되었습니다. 다시 읽고 승인하십시오.")
        revision = conn.execute("SELECT COALESCE(MAX(revision),0)+1 FROM certification_policies WHERE tenant_id=? AND context_root_id=? AND entity_mode=?",
                                (tenant_id, context_root_id, entity_mode)).fetchone()[0]
        policy = {"policy_id": str(uuid.uuid4()), "revision": revision, "tenant_id": tenant_id,
                  "context_root_id": context_root_id, "entity_mode": entity_mode, "document": doc,
                  "approved_by": actor, "evidence_ref": evidence_ref.strip(), "created_at": now()}
        fp = digest(policy)
        try:
            event = decision_ledger.append(event_type=APPROVED, subject_type=SUBJECT_TYPE, subject_id=fp,
                                           actor_type="user", actor_id=actor, decision="APPROVED",
                                           evidence_refs=[evidence_ref.strip()], tenant_id=tenant_id,
                                           enterprise_scope_id=root_node.dept_id, entity_mode=entity_mode)
        except Exception as exc:
            raise CertificationError("POLICY_UNAVAILABLE", "회사 정책 승인 증명을 기록하지 못했습니다.", 503) from exc
        conn.execute("INSERT INTO certification_policies VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (policy["policy_id"], revision, tenant_id, context_root_id, entity_mode, fp,
                      canonical(policy), event["event_id"], actor, policy["created_at"]))
        conn.execute("INSERT INTO certification_policy_heads VALUES(?,?,?,?) ON CONFLICT(tenant_id,context_root_id,entity_mode) DO UPDATE SET policy_id=excluded.policy_id",
                     (tenant_id, context_root_id, entity_mode, policy["policy_id"]))
        return {**policy, "digest": fp, "approval_event_id": event["event_id"]}


def resolve_policy(conn: Any, *, tenant_id: str, entity_mode: str, context_root_id: str) -> dict:
    from core.decision_ledger import decision_ledger
    row = conn.execute("SELECT p.* FROM certification_policy_heads h LEFT JOIN certification_policies p ON p.policy_id=h.policy_id WHERE h.tenant_id=? AND h.context_root_id=? AND h.entity_mode=?",
                       (tenant_id, context_root_id, entity_mode)).fetchone()
    if row is None:
        raise CertificationError("ROLE_MAPPING_REQUIRED", "회사에서 승인한 종류별 서명권 매핑을 먼저 등록하십시오.")
    try:
        policy = json.loads(row["document_json"])
        validate_document(policy["document"])
        event = decision_ledger.get_event_strict(row["approval_event_id"])
        revoked = decision_ledger.has_invalidating_child(row["approval_event_id"], (REVOKED,))
        if (digest(policy) != row["digest"] or policy["policy_id"] != row["policy_id"]
                or policy["tenant_id"] != tenant_id or policy["entity_mode"] != entity_mode
                or policy["context_root_id"] != context_root_id
                or policy["revision"] != row["revision"] or policy["approved_by"] != row["approved_by"]
                or not event or event["event_type"] != APPROVED or event["subject_type"] != SUBJECT_TYPE
                or event["subject_id"] != row["digest"] or event["actor_id"] != policy["approved_by"]
                or event["decision"] != "APPROVED" or event["tenant_id"] != tenant_id
                or event["entity_mode"] != entity_mode or revoked):
            raise ValueError("approval mismatch or revoked")
    except Exception as exc:
        raise CertificationError("POLICY_UNAVAILABLE", "서명 정책 또는 승인 증명의 무결성을 확인하지 못했습니다.", 503) from exc
    return {**policy, "digest": row["digest"], "approval_event_id": row["approval_event_id"]}


def _direct_grant(policy: dict, subject: Mapping[str, Any], user: dict, kind: str) -> bool:
    from core.app_policy import _scope_covers
    from core.data_preparation import ownership_binding as ob
    for grant in policy["document"]["grants"][kind]:
        if kind == "DATA_OWNER" and grant["dept_id"] != subject["owner_dept_id"]:
            continue
        alive, failed = ob._dept_alive(grant["dept_id"])
        covers, lookup_failed = _scope_covers(grant["scope_node_id"], subject["scope_node_id"])
        if failed or lookup_failed:
            raise CertificationError("AUTHORITY_UNAVAILABLE", "서명 역할 범위를 확인하지 못했습니다.", 503)
        if alive and covers and user.get("roles", {}).get(grant["dept_id"]) == grant["role"]:
            return True
    return False


def can_sign(subject: Mapping[str, Any], actor: str, review_kind: str, *, policy: dict, context: Mapping[str, Any]) -> dict:
    """종류별 회사 매핑 ∩ 현재 활성 사용자/역할/위임 ∩ 현재 PDP 읽기 범위."""
    from core.app_policy import _scope_covers
    if review_kind not in KINDS:
        raise CertificationError("SIGNER_INELIGIBLE", "지원하지 않는 서명 종류입니다.", 403)
    facts = require_read(subject, actor, context)
    if any(policy[key] != subject[key] for key in ("tenant_id", "entity_mode", "context_root_id")):
        raise CertificationError("SIGNER_INELIGIBLE", "서명 정책의 회사 문맥이 다릅니다.", 403)
    eligible = _direct_grant(policy, subject, facts["user"], review_kind)
    delegated_by = ""
    at = datetime.now(timezone.utc)
    if not eligible:
        for delegation in policy["document"]["delegations"]:
            if delegation["actor"] != actor or delegation["review_kind"] != review_kind:
                continue
            if not (instant(delegation["valid_from"]) <= at < instant(delegation["valid_to"])):
                continue
            covers, failed = _scope_covers(delegation["scope_node_id"], subject["scope_node_id"])
            if failed:
                raise CertificationError("AUTHORITY_UNAVAILABLE", "위임 범위를 확인하지 못했습니다.", 503)
            if not covers:
                continue
            try:
                delegator = require_read(subject, delegation["delegator"], context)
            except CertificationError as exc:
                if exc.status_code in (403, 404):
                    continue  # 확정 부적격 후보만 제외한다. 판독 불가는 전체 차단.
                raise
            if _direct_grant(policy, subject, delegator["user"], review_kind):
                eligible, delegated_by = True, delegation["delegator"]
                break
    if not eligible:
        raise CertificationError("SIGNER_INELIGIBLE", "이 종류의 회사 서명권 또는 유효한 위임이 없습니다.", 403)
    scope_facts = {key: sorted(value) if isinstance(value, (set, frozenset)) else value
                   for key, value in vars(facts["scope"]).items()}
    return {"actor": actor, "review_kind": review_kind, "policy_id": policy["policy_id"],
            "policy_digest": policy["digest"], "delegated_by": delegated_by, "checked_at": now(),
            "scope_digest": digest(scope_facts), "authority_contract": "certification-signing/1",
            "authority_digest": digest({"user": facts["user"], "delegated_by": delegated_by,
                                        "policy_digest": policy["digest"], "context": dict(context)})}
