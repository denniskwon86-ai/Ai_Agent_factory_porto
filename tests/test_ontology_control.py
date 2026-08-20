from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import Principal, current_principal
from api.routes import ontology_control
from core import app_policy
from core import ontology_resolve
from core.ontology_runtime import ObjectRef, OntologyRuntime


@dataclass
class _Scope:
    readable_dept_ids: frozenset = frozenset({"org_demo"})
    writable_dept_ids: frozenset = frozenset({"org_demo"})
    readable_scope_nodes: frozenset = frozenset({"plant_demo"})
    unrestricted: bool = True
    can_manage_standard: bool = True


def _principal(user="steward@example.com"):
    return Principal(user_id=user, scope=_Scope(), requested_scope_node_id="plant_demo",
                     session_id="session-hash")


def _resolver(hidden):
    def resolve(ref: ObjectRef, ctx: ontology_resolve.ResolveContext):
        if ref.key in hidden:
            return ontology_resolve.found(app_policy.ResourceScope(
                tenant_id="tenant_demo", entity_mode="VIRTUAL", scope_node_id="secret_plant",
                owner_dept_id="secret_org", binding_state=app_policy.BOUND))
        return ontology_resolve.found(app_policy.ResourceScope(
            tenant_id="tenant_demo", entity_mode="VIRTUAL", scope_node_id="plant_demo",
            owner_dept_id="org_demo", binding_state=app_policy.BOUND))
    return resolve


def _contract(status="APPROVED"):
    out = {
        "contract_id": "G2-FIRST-VERTICAL-ONTOLOGY", "contract_version": "1.0.0",
        "status": status,
        "relation_types": [{"id": "AFFECTS", "name_ko": "영향을 줌",
                            "inverse": "AFFECTED_BY", "quantitative": True}],
        "constraints": [{
            "subject": "dataset:shipment", "relation": "AFFECTS",
            "object": "dataset:inventory-snapshot", "evidence": ["approved delay model"],
            "calculation_ref": "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
        }],
    }
    if status == "APPROVED":
        out["approval"] = {"approved_by": "governor@example.com",
                           "decision_ledger_id": "ledger-model-v1",
                           "effective_from": "2026-01-01T00:00:00Z"}
    return out


def _harness(tmp_path, monkeypatch, with_resolver=True, resolver_error=False):
    hidden = set()
    resolver = _resolver(hidden) if with_resolver else None
    if resolver_error:
        def resolver(ref, ctx):
            raise RuntimeError("scope store unavailable")
    runtime = OntologyRuntime(str(tmp_path / "ontology.db"),
                              resolver,
                              lambda ledger_id, action, actor, target_type="", target_id="":
                              bool(ledger_id and action and actor))
    app = FastAPI()
    app.include_router(ontology_control.create_router(runtime))
    holder = {"principal": _principal()}

    async def principal_override():
        return holder["principal"]

    app.dependency_overrides[current_principal] = principal_override
    monkeypatch.setattr(ontology_control, "viewing_context", lambda p: {
        "tenant_id": "tenant_demo", "entity_mode": "VIRTUAL", "scope_node_id": "plant_demo"})
    monkeypatch.setattr(ontology_control, "visibility_block_reason", lambda p: "")
    return TestClient(app), runtime, hidden, holder


def _proposal():
    return {
        "subject": {"namespace": "dataset", "object_type": "shipment",
                    "object_id": "SHP-001"},
        "relation_type_id": "AFFECTS",
        "object": {"namespace": "dataset", "object_type": "inventory-snapshot",
                   "object_id": "INV-001"},
        "tenant_id": "tenant_demo", "enterprise_scope_id": "plant_demo",
        "entity_mode": "VIRTUAL", "owner_organization_id": "org_demo",
        "effective_from": "2026-01-01T00:00:00Z", "origin": "derived",
        "evidence_refs": ["SNAPSHOT:LOG-02:v1"],
        "calculation_ref": "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
    }


def test_model_validation_and_atomic_install_api(tmp_path, monkeypatch):
    client, _, _, _ = _harness(tmp_path, monkeypatch)
    design = client.post("/api/v1/ontology/model/validate",
                         json={"contract": _contract("DESIGN_ONLY")})
    assert design.status_code == 200
    assert design.json()["data"]["installable"] is False

    installed = client.post("/api/v1/ontology/model/install",
                            json={"contract": _contract()})
    assert installed.status_code == 200
    assert installed.json()["data"]["installed"] is True
    status = client.get("/api/v1/ontology/model/status")
    assert status.status_code == 200
    assert status.json()["data"]["status"] == "READY"


def test_relation_lifecycle_impact_and_evidence_api(tmp_path, monkeypatch):
    client, _, _, holder = _harness(tmp_path, monkeypatch)
    assert client.post("/api/v1/ontology/model/install",
                       json={"contract": _contract()}).status_code == 200
    proposed = client.post("/api/v1/ontology/relations/propose", json=_proposal())
    assert proposed.status_code == 200
    relation_id = proposed.json()["data"]["relation_id"]
    assert client.post(f"/api/v1/ontology/relations/{relation_id}/submit").status_code == 200

    # Self approval is rejected even for an administrator.
    self_approval = client.post(f"/api/v1/ontology/relations/{relation_id}/approve",
                                json={"decision_ledger_id": "ledger-relation-v1"})
    assert self_approval.status_code == 400
    holder["principal"] = _principal("governor@example.com")
    approved = client.post(f"/api/v1/ontology/relations/{relation_id}/approve",
                           json={"decision_ledger_id": "ledger-relation-v1"})
    assert approved.status_code == 200

    impact = client.post("/api/v1/ontology/query/impact", json={
        "roots": [_proposal()["subject"]], "target_types": ["inventory-snapshot"],
        "relation_types": ["AFFECTS"], "as_of": "2026-03-01T00:00:00Z"})
    assert impact.status_code == 200
    assert impact.json()["data"]["status"] == "COMPLETE"
    assert len(impact.json()["data"]["paths"]) == 1

    evidence = client.get(f"/api/v1/ontology/relations/{relation_id}/evidence",
                          params={"as_of": "2026-03-01T00:00:00Z"})
    assert evidence.status_code == 200
    assert evidence.json()["data"]["calculation_ref"].endswith("ARRIVAL_DELAY.v1")


def test_hidden_endpoint_removes_path_and_evidence_without_count(tmp_path, monkeypatch):
    client, _, hidden, holder = _harness(tmp_path, monkeypatch)
    client.post("/api/v1/ontology/model/install", json={"contract": _contract()})
    relation_id = client.post("/api/v1/ontology/relations/propose",
                              json=_proposal()).json()["data"]["relation_id"]
    client.post(f"/api/v1/ontology/relations/{relation_id}/submit")
    holder["principal"] = _principal("governor@example.com")
    client.post(f"/api/v1/ontology/relations/{relation_id}/approve",
                json={"decision_ledger_id": "ledger-relation-v1"})

    hidden.add("dataset:inventory-snapshot:INV-001")
    impact = client.post("/api/v1/ontology/query/impact", json={
        "roots": [_proposal()["subject"]], "target_types": ["inventory-snapshot"],
        "relation_types": ["AFFECTS"], "as_of": "2026-03-01T00:00:00Z"})
    body = impact.json()["data"]
    assert body["status"] == "NO_VISIBLE_PATH"
    assert body["paths"] == []
    assert "blocked" not in body and "hidden_count" not in body
    evidence = client.get(f"/api/v1/ontology/relations/{relation_id}/evidence",
                          params={"as_of": "2026-03-01T00:00:00Z"})
    assert evidence.status_code == 404


def test_query_without_object_scope_resolver_is_503_not_empty(tmp_path, monkeypatch):
    client, _, _, _ = _harness(tmp_path, monkeypatch, with_resolver=False)
    response = client.post("/api/v1/ontology/query/impact", json={
        "roots": [_proposal()["subject"]], "target_types": [], "relation_types": [],
        "as_of": "2026-03-01T00:00:00Z"})
    assert response.status_code == 503
    assert "확인할 수 없습니다" in response.json()["detail"]


def test_scope_resolver_failure_is_503_not_no_visible_path(tmp_path, monkeypatch):
    client, _, _, _ = _harness(tmp_path, monkeypatch, resolver_error=True)
    response = client.post("/api/v1/ontology/query/impact", json={
        "roots": [_proposal()["subject"]], "target_types": [], "relation_types": [],
        "as_of": "2026-03-01T00:00:00Z"})
    assert response.status_code == 503
    assert response.json()["detail"] != "NO_VISIBLE_PATH"
