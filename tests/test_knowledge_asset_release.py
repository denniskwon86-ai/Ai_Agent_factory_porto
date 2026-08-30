from __future__ import annotations

import hashlib
import json

import pytest

from core import knowledge_asset_release as release
from core import ontology_resolve
from core import ontology_resolvers as resolvers
from core.decision_ledger import DecisionLedger
from core.ontology_runtime import ObjectRef


def _fixture(tmp_path, monkeypatch):
    root = tmp_path / "reference"
    root.mkdir()
    source = root / "공급망 운영 기준.pdf"
    source.write_bytes(b"%PDF-1.4\ntrusted knowledge\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    registry_path = tmp_path / "reference_registry.json"
    registry_path.write_text(json.dumps({
        "registry_version": "1.1", "summary": {"pending_review": 1},
        "assets": [{
            "asset_id": "REF-ASSET-1", "relative_path": source.name,
            "filename": source.name, "sha256": digest,
            "source_kind": "TRAINING_OR_GUIDE", "pack_id": "scm-pack",
            "scope_code": "MNM_COPPER", "owner_org_id": "MNM_COPPER",
            "classification": "INTERNAL", "extraction_status": "SUPPORTED",
            "ingestion_status": "REGISTERED", "approval_status": "PENDING_REVIEW",
            "approved_by": "", "approved_at": "", "approved_sha256": "",
        }],
    }, ensure_ascii=False), encoding="utf-8")
    from core.enterprise_context.resolver import ecm_resolver
    monkeypatch.setattr(ecm_resolver, "resolve_scope_ref", lambda *a, **k: {
        "resolved": True, "node_id": "node-copper", "kind": "ecm_code",
    })
    ledger = DecisionLedger(str(tmp_path / "ledger.db"))
    return root, registry_path, source, ledger


def _approve(tmp_path, monkeypatch):
    root, registry, source, ledger = _fixture(tmp_path, monkeypatch)
    row = release.approve(
        "REF-ASSET-1", "approver@test.invalid", "시연 공급망 기준으로 검토 완료",
        tenant_id="tenant-a", scope_node_id="node-copper", entity_mode="REAL",
        registry_path=registry, reference_root=root, ledger=ledger)
    return root, registry, source, ledger, row


def test_legacy_approved_string_is_not_an_effective_release(tmp_path, monkeypatch):
    root, registry, _, ledger = _fixture(tmp_path, monkeypatch)
    doc = json.loads(registry.read_text(encoding="utf-8"))
    doc["assets"][0].update({"approval_status": "APPROVED",
                             "approved_by": "legacy@test.invalid",
                             "approved_at": "2026-08-01T00:00:00+00:00"})
    registry.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert release.effective_asset(
        "REF-ASSET-1", registry_path=registry, reference_root=root, ledger=ledger) is None


def test_approval_seals_source_scope_and_ledger(tmp_path, monkeypatch):
    root, registry, _, ledger, row = _approve(tmp_path, monkeypatch)
    assert len(row["approval_fingerprint"]) == 64
    assert row["approved_sha256"] == row["sha256"]
    event = ledger.get_event_strict(row["approval_event_id"])
    assert event["event_type"] == release.EVENT_APPROVED
    assert event["subject_id"] == row["approval_fingerprint"]
    effective = release.effective_asset(
        row["asset_id"], registry_path=registry, reference_root=root, ledger=ledger)
    assert effective and effective["approval_scope_node_id"] == "node-copper"


def test_source_change_invalidates_the_release(tmp_path, monkeypatch):
    root, registry, source, ledger, row = _approve(tmp_path, monkeypatch)
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(release.KnowledgeAssetError, match="변경"):
        release.effective_asset(
            row["asset_id"], registry_path=registry, reference_root=root, ledger=ledger)


def test_registry_meaning_change_invalidates_the_release(tmp_path, monkeypatch):
    root, registry, _, ledger, row = _approve(tmp_path, monkeypatch)
    doc = json.loads(registry.read_text(encoding="utf-8"))
    doc["assets"][0]["classification"] = "CONFIDENTIAL"
    registry.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(release.KnowledgeAssetError, match="내용 지문"):
        release.effective_asset(
            row["asset_id"], registry_path=registry, reference_root=root, ledger=ledger)


def test_revocation_keeps_history_and_removes_effective_release(tmp_path, monkeypatch):
    root, registry, _, ledger, row = _approve(tmp_path, monkeypatch)
    revoked = release.revoke(
        row["asset_id"], "approver@test.invalid", "기준 개정으로 철회",
        registry_path=registry, reference_root=root, ledger=ledger)
    assert revoked["approval_status"] == "REJECTED"
    event = ledger.get_event_strict(revoked["revocation_event_id"])
    assert event["parent_event_id"] == row["approval_event_id"]
    assert release.effective_asset(
        row["asset_id"], registry_path=registry, reference_root=root, ledger=ledger) is None


def test_approval_requires_the_assets_canonical_owner_scope(tmp_path, monkeypatch):
    root, registry, _, ledger = _fixture(tmp_path, monkeypatch)
    with pytest.raises(release.KnowledgeAssetError, match="소유 범위"):
        release.approve(
            "REF-ASSET-1", "approver@test.invalid", "검토 완료",
            tenant_id="tenant-a", scope_node_id="other-node", entity_mode="REAL",
            registry_path=registry, reference_root=root, ledger=ledger)


def _ctx():
    return ontology_resolve.ResolveContext(
        ontology_resolve.ROOT_LOOKUP, tenant_id="tenant-a", entity_mode="REAL")


def test_knowledge_resolver_is_unbound_until_reapproved(monkeypatch):
    monkeypatch.setattr(release, "effective_asset", lambda *a, **k: None)
    result = resolvers.product_object_scope_resolver(
        ObjectRef("knowledge", "reference-asset", "opaque"), _ctx())
    assert result.status == ontology_resolve.UNBOUND


def test_knowledge_resolver_returns_scope_and_human_description(monkeypatch):
    monkeypatch.setattr(release, "effective_asset", lambda *a, **k: {
        "filename": "공급망 운영 기준.pdf", "pack_id": "scm-pack",
        "classification": "INTERNAL", "approved_sha256": "a" * 64,
        "approval_fingerprint": "b" * 64, "approved_at": "2026-08-28T00:00:00Z",
        "approval_event_id": "evt-1", "approval_tenant_id": "tenant-a",
        "approval_scope_node_id": "node-copper", "approval_entity_mode": "REAL",
        "approved_by": "approver@test.invalid",
    })
    result = resolvers.product_object_scope_resolver(
        ObjectRef("knowledge", "reference-asset", "opaque"), _ctx())
    assert result.status == ontology_resolve.FOUND
    assert result.resource_scope.scope_node_id == "node-copper"
    assert result.display_name == "승인 지식 · 공급망 운영 기준"
    assert "opaque" not in result.display_name
    assert result.snapshot_id == "b" * 64


def test_knowledge_store_failure_is_not_reported_as_absence(monkeypatch):
    def broken(*args, **kwargs):
        raise release.KnowledgeAssetError("ledger unavailable")
    monkeypatch.setattr(release, "effective_asset", broken)
    result = resolvers.product_object_scope_resolver(
        ObjectRef("knowledge", "reference-asset", "opaque"), _ctx())
    assert result.status == ontology_resolve.UNAVAILABLE
