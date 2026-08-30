"""Ledger-backed releases for reference assets exposed to ontology and indexing.

Legacy ``APPROVED`` rows are deliberately not upgraded.  An effective release
must seal the current source bytes, the human governance fields and the exact
tenant/scope/entity context in one fingerprint, then bind that fingerprint to
an append-only Decision Ledger event.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.decision_ledger import DecisionLedger, DecisionLedgerError, decision_ledger


EVENT_APPROVED = "KNOWLEDGE_ASSET_APPROVED"
EVENT_REVOKED = "KNOWLEDGE_ASSET_REVOKED"
SUBJECT_TYPE = "knowledge_asset"
OBJECT_TYPE = "reference-asset"
_LOCK = threading.RLock()


class KnowledgeAssetError(RuntimeError):
    """A reference asset cannot be trusted as approved knowledge."""


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeAssetError("지식 자산 승인 시각을 읽지 못했습니다.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read(registry_path: Path) -> dict[str, Any]:
    try:
        value = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeAssetError("참고자산 등록부를 읽지 못했습니다.") from exc
    if not isinstance(value, dict) or not isinstance(value.get("assets"), list):
        raise KnowledgeAssetError("참고자산 등록부 구조가 올바르지 않습니다.")
    return value


def _write(registry: dict[str, Any], registry_path: Path) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=registry_path.name + ".", suffix=".tmp", dir=str(registry_path.parent))
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, registry_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _serialized(fn):
    """JSON registry decisions are one critical section in this service process."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    return wrapped


def _asset(registry: dict[str, Any], asset_id: str) -> dict[str, Any]:
    matches = [row for row in registry["assets"] if row.get("asset_id") == asset_id]
    if len(matches) != 1:
        raise KnowledgeAssetError("참고자산을 하나로 확정하지 못했습니다.")
    return matches[0]


def _source_path(asset: dict[str, Any], reference_root: Path) -> Path:
    root = reference_root.resolve()
    target = (root / str(asset.get("relative_path") or "")).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise KnowledgeAssetError("참고자산 원문 경로가 허용 범위를 벗어났습니다.") from exc
    if not target.is_file():
        raise KnowledgeAssetError("참고자산 원문을 찾을 수 없습니다.")
    return target


def _source_sha256(asset: dict[str, Any], reference_root: Path) -> str:
    digest = hashlib.sha256()
    try:
        with _source_path(asset, reference_root).open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise KnowledgeAssetError("참고자산 원문을 읽지 못했습니다.") from exc
    return digest.hexdigest()


def _owner_scope(asset: dict[str, Any], tenant_id: str, entity_mode: str) -> str:
    owner = str(asset.get("owner_org_id") or asset.get("scope_code") or "").strip()
    if not owner:
        raise KnowledgeAssetError("지식 자산의 소유 조직이 비어 있습니다.")
    try:
        from core.enterprise_context.resolver import ecm_resolver
        resolved = ecm_resolver.resolve_scope_ref(owner, tenant_id=tenant_id,
                                                  entity_mode=entity_mode)
    except Exception as exc:
        raise KnowledgeAssetError("지식 자산의 소유 조직을 해석하지 못했습니다.") from exc
    node_id = str((resolved or {}).get("node_id") or "").strip()
    if not (resolved or {}).get("resolved") or not node_id:
        raise KnowledgeAssetError("지식 자산의 소유 조직이 ECM 정본에 결속되지 않았습니다.")
    return node_id


def fingerprint(asset: dict[str, Any], *, tenant_id: str, scope_node_id: str,
                entity_mode: str) -> str:
    material = {
        "asset_id": str(asset.get("asset_id") or ""),
        "sha256": str(asset.get("approved_sha256") or asset.get("sha256") or ""),
        "pack_id": str(asset.get("pack_id") or ""),
        "classification": str(asset.get("classification") or ""),
        "source_kind": str(asset.get("source_kind") or ""),
        "tenant_id": str(tenant_id or ""),
        "scope_node_id": str(scope_node_id or ""),
        "entity_mode": str(entity_mode or ""),
    }
    if not all(material.values()):
        raise KnowledgeAssetError("지식 자산 승인 지문에 필요한 값이 비어 있습니다.")
    payload = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@_serialized
def approve(asset_id: str, actor: str, rationale: str, *, tenant_id: str,
            scope_node_id: str, entity_mode: str, registry_path: Path,
            reference_root: Path, ledger: Optional[DecisionLedger] = None) -> dict[str, Any]:
    ledger = ledger or decision_ledger
    if not all(str(value or "").strip() for value in
               (asset_id, actor, rationale, tenant_id, scope_node_id, entity_mode)):
        raise KnowledgeAssetError("승인자·사유·tenant·조직 범위·실행 문맥이 모두 필요합니다.")
    registry = _read(registry_path)
    asset = _asset(registry, asset_id)
    if asset.get("extraction_status") != "SUPPORTED":
        raise KnowledgeAssetError("추출 가능한 원문만 승인 지식으로 결속할 수 있습니다.")
    owner_scope = _owner_scope(asset, tenant_id, entity_mode)
    if owner_scope != scope_node_id:
        raise KnowledgeAssetError("선택한 조직 문맥과 지식 자산의 정본 소유 범위가 다릅니다.")
    actual_sha = _source_sha256(asset, reference_root)
    if actual_sha != str(asset.get("sha256") or ""):
        raise KnowledgeAssetError("등록부 지문과 현재 원문 지문이 다릅니다. 먼저 재스캔하십시오.")
    sealed = {**asset, "approved_sha256": actual_sha}
    fp = fingerprint(sealed, tenant_id=tenant_id, scope_node_id=scope_node_id,
                     entity_mode=entity_mode)
    if (asset.get("approval_status") == "APPROVED"
            and asset.get("approval_fingerprint") == fp
            and effective_asset(asset_id, registry_path=registry_path,
                                reference_root=reference_root, ledger=ledger)):
        return {**asset, "idempotent": True}
    if asset.get("approval_event_id"):
        raise KnowledgeAssetError("이미 결속된 다른 승인 판본이 있습니다. 먼저 철회하십시오.")
    event = ledger.append(
        event_type=EVENT_APPROVED, subject_type=SUBJECT_TYPE, subject_id=fp,
        actor_type="user", actor_id=actor.strip(), decision="APPROVE",
        rationale=rationale.strip(),
        evidence_refs=[{"asset_id": asset_id, "sha256": actual_sha,
                        "pack_id": str(asset.get("pack_id") or "")}],
        tenant_id=tenant_id, enterprise_scope_id=scope_node_id, entity_mode=entity_mode)
    asset.update({
        "approval_status": "APPROVED", "approved_by": actor.strip(),
        "approved_at": str(event["created_at"]), "approved_sha256": actual_sha,
        "approval_fingerprint": fp, "approval_event_id": str(event["event_id"]),
        "approval_tenant_id": tenant_id, "approval_scope_node_id": scope_node_id,
        "approval_entity_mode": entity_mode, "notes": rationale.strip(),
    })
    registry.setdefault("summary", {})["pending_review"] = sum(
        row.get("approval_status") == "PENDING_REVIEW" for row in registry["assets"])
    try:
        _write(registry, registry_path)
    except Exception as exc:
        ledger.append(
            event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE, subject_id=fp,
            actor_type="system", actor_id=actor.strip(), decision="COMPENSATE",
            rationale=f"지식 자산 등록 실패: {type(exc).__name__}",
            parent_event_id=str(event["event_id"]), tenant_id=tenant_id,
            enterprise_scope_id=scope_node_id, entity_mode=entity_mode)
        raise KnowledgeAssetError("승인 사건 이후 지식 자산 등록에 실패했습니다.") from exc
    return {**asset, "idempotent": False}


def effective_asset(asset_id: str, as_of: str = "", *, registry_path: Path,
                    reference_root: Path, ledger: Optional[DecisionLedger] = None
                    ) -> Optional[dict[str, Any]]:
    ledger = ledger or decision_ledger
    registry = _read(registry_path)
    asset = _asset(registry, asset_id)
    if asset.get("approval_status") != "APPROVED":
        return None
    required = ("approved_sha256", "approval_fingerprint", "approval_event_id",
                "approval_tenant_id", "approval_scope_node_id", "approval_entity_mode",
                "approved_by", "approved_at")
    if not all(str(asset.get(key) or "").strip() for key in required):
        return None                         # legacy approval: explicit reapproval required
    cutoff = _instant(as_of) if str(as_of or "").strip() else datetime.now(timezone.utc)
    if _instant(str(asset["approved_at"])) > cutoff:
        return None
    actual_sha = _source_sha256(asset, reference_root)
    if not (actual_sha == asset.get("sha256") == asset.get("approved_sha256")):
        raise KnowledgeAssetError("승인 뒤 지식 자산 원문 또는 등록부 지문이 변경됐습니다.")
    tenant_id = str(asset["approval_tenant_id"])
    scope_node_id = str(asset["approval_scope_node_id"])
    entity_mode = str(asset["approval_entity_mode"])
    if _owner_scope(asset, tenant_id, entity_mode) != scope_node_id:
        raise KnowledgeAssetError("승인 뒤 지식 자산의 정본 소유 범위가 변경됐습니다.")
    if fingerprint(asset, tenant_id=tenant_id, scope_node_id=scope_node_id,
                   entity_mode=entity_mode) != asset["approval_fingerprint"]:
        raise KnowledgeAssetError("지식 자산 승인 판본의 내용 지문이 일치하지 않습니다.")
    try:
        event = ledger.get_event_strict(str(asset["approval_event_id"]))
        invalid = ledger.has_invalidating_child(
            str(asset["approval_event_id"]), (EVENT_REVOKED,), as_of=cutoff.isoformat())
    except (DecisionLedgerError, sqlite3.Error) as exc:
        raise KnowledgeAssetError("지식 자산 승인 원장을 확인하지 못했습니다.") from exc
    if not event or (event.get("event_type"), event.get("subject_type"), event.get("subject_id")) != (
            EVENT_APPROVED, SUBJECT_TYPE, asset["approval_fingerprint"]):
        raise KnowledgeAssetError("지식 자산 판본과 승인 사건의 대상이 일치하지 않습니다.")
    event_binding = tuple(str(event.get(key) or "") for key in
                          ("actor_id", "tenant_id", "enterprise_scope_id", "entity_mode", "created_at"))
    asset_binding = tuple(str(asset.get(key) or "") for key in
                          ("approved_by", "approval_tenant_id", "approval_scope_node_id",
                           "approval_entity_mode", "approved_at"))
    if event_binding != asset_binding:
        raise KnowledgeAssetError("지식 자산 판본과 원장의 승인 결속값이 일치하지 않습니다.")
    return None if invalid else asset


@_serialized
def revoke(asset_id: str, actor: str, rationale: str, *, registry_path: Path,
           reference_root: Path, ledger: Optional[DecisionLedger] = None) -> dict[str, Any]:
    ledger = ledger or decision_ledger
    if not str(actor or "").strip() or not str(rationale or "").strip():
        raise KnowledgeAssetError("철회자와 철회 사유가 모두 필요합니다.")
    asset = effective_asset(asset_id, registry_path=registry_path,
                            reference_root=reference_root, ledger=ledger)
    if not asset:
        raise KnowledgeAssetError("철회할 원장 결속 승인 판본이 없습니다.")
    event = ledger.append(
        event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE,
        subject_id=str(asset["approval_fingerprint"]), actor_type="user",
        actor_id=actor.strip(), decision="REVOKE", rationale=rationale.strip(),
        parent_event_id=str(asset["approval_event_id"]),
        tenant_id=str(asset["approval_tenant_id"]),
        enterprise_scope_id=str(asset["approval_scope_node_id"]),
        entity_mode=str(asset["approval_entity_mode"]))
    registry = _read(registry_path)
    target = _asset(registry, asset_id)
    target.update({"approval_status": "REJECTED", "revoked_by": actor.strip(),
                   "revoked_at": str(event["created_at"]),
                   "revocation_event_id": str(event["event_id"]), "notes": rationale.strip()})
    _write(registry, registry_path)
    return target


def current_object_types(*, registry_path: Path, reference_root: Path,
                         ledger: Optional[DecisionLedger] = None) -> tuple[str, ...]:
    registry = _read(registry_path)
    for asset in registry["assets"]:
        if asset.get("approval_status") != "APPROVED":
            continue
        if effective_asset(str(asset.get("asset_id") or ""), registry_path=registry_path,
                           reference_root=reference_root, ledger=ledger):
            return (OBJECT_TYPE,)
    return ()
