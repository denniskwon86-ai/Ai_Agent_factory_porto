"""B1 업무지도 v2 계약. 업무 정의는 ECM profile payload 한 곳에만 둔다."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.enterprise_context.models import EcmError


class ProcessError(EcmError):
    def __init__(self, reason_code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.reason_code, self.status_code = reason_code, status_code


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProcessBoundary(StrictModel):
    tenant_id: str = Field(min_length=1)
    context_root_id: str = Field(min_length=1)
    entity_mode: Literal["REAL", "VIRTUAL", "COMPETITOR_REFERENCE"]
    scope_node_id: str = ""
    configuration_kind: Literal["business_process"] = "business_process"

    def key(self) -> tuple:
        return (self.tenant_id, self.context_root_id, self.entity_mode,
                self.scope_node_id, self.configuration_kind)


class ProcessNode(StrictModel):
    process_id: str = Field(min_length=1, max_length=160)
    level: Literal["L1", "L2"]
    parent_process_id: str = ""
    label: str = Field(min_length=1, max_length=200)
    note: str = ""
    origin: Literal["CUSTOM", "LEGACY", "STANDARD"] = "CUSTOM"
    enabled: bool = True
    template_key: str = ""
    owner_scope_node_id: str = ""
    source_ref: str = ""
    recorded_at: str = ""
    # 구 ThreadNode의 명시적 null과 누락은 legacy_fields에 원형 보존한다.
    legacy_fields: dict[str, Any] = Field(default_factory=dict)


class ProcessPlacement(StrictModel):
    placement_id: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    parent_process_id: str = ""
    kind: Literal["CANONICAL", "SHORTCUT"] = "CANONICAL"
    position: int = Field(ge=0)
    hidden: bool = False


class ProcessDocument(StrictModel):
    schema_version: Literal[2] = 2
    configuration_id: str = Field(min_length=1)
    base_profile_id: str = ""
    base_fingerprint: str = ""
    template_sources: list[dict[str, Any]] = Field(default_factory=list)
    nodes: list[ProcessNode] = Field(default_factory=list)
    placements: list[ProcessPlacement] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    bindings: list[dict[str, Any]] = Field(default_factory=list)
    local_overrides: list[dict[str, Any]] = Field(default_factory=list)
    migration_map: list[dict[str, Any]] = Field(default_factory=list)


def validate_document(payload: dict) -> dict:
    """완전한 승인판을 검증한다. 일반 리스트 상속·자동 실행·권한 승격은 없다."""
    try:
        doc = ProcessDocument.model_validate(payload).model_dump()
        nodes = {n["process_id"]: n for n in doc["nodes"]}
        if len(nodes) != len(doc["nodes"]):
            raise ValueError("duplicate process_id")
        for n in nodes.values():
            parent = nodes.get(n["parent_process_id"])
            if (n["level"] == "L1" and n["parent_process_id"]) or (
                    n["level"] == "L2" and (not parent or parent["level"] != "L1")):
                raise ValueError("parent")
            if not n["label"].strip():
                raise ValueError("label")
        placements, canonical_nodes = set(), set()
        for p in doc["placements"]:
            if p["placement_id"] in placements or p["process_id"] not in nodes:
                raise ValueError("placement")
            placements.add(p["placement_id"])
            n = nodes[p["process_id"]]
            if p["kind"] == "CANONICAL":
                if p["process_id"] in canonical_nodes or p["parent_process_id"] != n["parent_process_id"]:
                    raise ValueError("canonical placement")
                canonical_nodes.add(p["process_id"])
            elif (n["level"] != "L2" or p["parent_process_id"] not in nodes
                  or nodes[p["parent_process_id"]]["level"] != "L1"
                  or p["parent_process_id"] == n["parent_process_id"]):
                raise ValueError("shortcut")
        if canonical_nodes != set(nodes):
            raise ValueError("canonical placement missing")
        from core.enterprise_context.process_references import validate_references
        validate_references(doc, nodes)
        return doc
    except (ValueError, TypeError, KeyError) as exc:
        raise ProcessError("PROCESS_DOCUMENT_INVALID", "업무 구조·부모·배치·지원 참조를 확인하십시오.", 422) from exc


DDL = """
CREATE TABLE IF NOT EXISTS enterprise_process_installations (
 operation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, context_root_id TEXT NOT NULL,
 entity_mode TEXT NOT NULL, scope_node_id TEXT NOT NULL, configuration_kind TEXT NOT NULL,
 configuration_id TEXT NOT NULL, plan_digest TEXT NOT NULL, plan_json TEXT NOT NULL,
 actor TEXT NOT NULL, installer TEXT NOT NULL DEFAULT '', client_request_id TEXT NOT NULL,
 request_fingerprint TEXT NOT NULL, stage TEXT NOT NULL, error_code TEXT NOT NULL DEFAULT '',
 revision INTEGER NOT NULL DEFAULT 0, attempt_id TEXT NOT NULL DEFAULT '',
 kit_instance_ref TEXT NOT NULL DEFAULT '', change_id TEXT NOT NULL DEFAULT '',
 applied_profile_id TEXT NOT NULL DEFAULT '', applied_at TEXT NOT NULL DEFAULT '',
 result_json TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(tenant_id,context_root_id,entity_mode,scope_node_id,client_request_id)
);
CREATE TRIGGER IF NOT EXISTS process_installation_immutable_update
BEFORE UPDATE ON enterprise_process_installations
WHEN OLD.stage='APPLIED' OR NEW.operation_id<>OLD.operation_id OR NEW.plan_json<>OLD.plan_json
 OR NEW.plan_digest<>OLD.plan_digest OR NEW.actor<>OLD.actor
 OR NEW.configuration_id<>OLD.configuration_id OR NEW.tenant_id<>OLD.tenant_id
 OR NEW.context_root_id<>OLD.context_root_id OR NEW.entity_mode<>OLD.entity_mode
 OR NEW.scope_node_id<>OLD.scope_node_id OR NEW.configuration_kind<>OLD.configuration_kind
 OR NEW.client_request_id<>OLD.client_request_id OR NEW.request_fingerprint<>OLD.request_fingerprint
BEGIN SELECT RAISE(ABORT, 'immutable process installation'); END;
CREATE TRIGGER IF NOT EXISTS process_installation_no_replace
BEFORE INSERT ON enterprise_process_installations WHEN EXISTS (
 SELECT 1 FROM enterprise_process_installations WHERE operation_id=NEW.operation_id)
BEGIN SELECT RAISE(ABORT, 'immutable process installation'); END;
CREATE TRIGGER IF NOT EXISTS process_installation_immutable_delete
BEFORE DELETE ON enterprise_process_installations
BEGIN SELECT RAISE(ABORT, 'immutable process installation'); END;
CREATE TABLE IF NOT EXISTS enterprise_process_heads (
 configuration_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL, context_root_id TEXT NOT NULL, entity_mode TEXT NOT NULL,
 scope_node_id TEXT NOT NULL, configuration_kind TEXT NOT NULL,
 active_profile_id TEXT NOT NULL DEFAULT '', head_version INTEGER NOT NULL DEFAULT 0,
 UNIQUE(tenant_id,context_root_id,entity_mode,scope_node_id,configuration_kind)
);
CREATE TABLE IF NOT EXISTS enterprise_process_changes (
 change_id TEXT PRIMARY KEY, configuration_id TEXT NOT NULL,
 base_head_version INTEGER NOT NULL, draft_profile_id TEXT NOT NULL UNIQUE,
 draft_digest TEXT NOT NULL, patch_json TEXT NOT NULL, legacy_token TEXT NOT NULL,
 actor TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
 client_request_id TEXT NOT NULL, request_fingerprint TEXT NOT NULL,
 review_by TEXT NOT NULL DEFAULT '', review_reason TEXT NOT NULL DEFAULT '',
 result_json TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
 UNIQUE(configuration_id,actor,client_request_id)
);
CREATE TABLE IF NOT EXISTS enterprise_process_outbox (
 event_id TEXT PRIMARY KEY, configuration_id TEXT NOT NULL, change_id TEXT NOT NULL,
 event_type TEXT NOT NULL, payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL,
 delivery_status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS process_profile_immutable_update
BEFORE UPDATE ON enterprise_profiles
WHEN OLD.configuration_id <> '' AND (OLD.approved_at <> '' OR OLD.status IN ('ACTIVE','ARCHIVED'))
AND NOT (NEW.status='ARCHIVED' AND OLD.status='ACTIVE'
 AND NEW.profile_id=OLD.profile_id AND NEW.tenant_id=OLD.tenant_id
 AND NEW.context_root_id=OLD.context_root_id AND NEW.entity_mode=OLD.entity_mode
 AND NEW.configuration_id=OLD.configuration_id AND NEW.scope_node_id=OLD.scope_node_id
 AND NEW.profile_kind=OLD.profile_kind AND NEW.industry_code=OLD.industry_code
 AND NEW.payload_json=OLD.payload_json AND NEW.inheritance_mode=OLD.inheritance_mode
 AND NEW.version=OLD.version AND NEW.approved_by=OLD.approved_by
 AND NEW.approved_at=OLD.approved_at AND NEW.created_at=OLD.created_at)
BEGIN SELECT RAISE(ABORT, 'immutable process profile'); END;
CREATE TRIGGER IF NOT EXISTS process_profile_immutable_delete
BEFORE DELETE ON enterprise_profiles WHEN OLD.configuration_id <> ''
BEGIN SELECT RAISE(ABORT, 'immutable process profile'); END;
CREATE TRIGGER IF NOT EXISTS process_outbox_immutable_update
BEFORE UPDATE ON enterprise_process_outbox
WHEN NEW.event_id<>OLD.event_id OR NEW.configuration_id<>OLD.configuration_id
 OR NEW.change_id<>OLD.change_id OR NEW.event_type<>OLD.event_type
 OR NEW.payload_json<>OLD.payload_json OR NEW.payload_digest<>OLD.payload_digest
 OR NEW.created_at<>OLD.created_at
BEGIN SELECT RAISE(ABORT, 'immutable process event'); END;
CREATE TRIGGER IF NOT EXISTS process_outbox_immutable_delete
BEFORE DELETE ON enterprise_process_outbox
BEGIN SELECT RAISE(ABORT, 'immutable process event'); END;
"""
