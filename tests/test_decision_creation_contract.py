"""Actual FastAPI router + domain + temporary real ledger; auth identity is synthetic.

Use scripts/verify_decision_creation_isolated.py (pre-import SQLite guard).
"""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_decision_source_binding import catalog  # shared synthetic completed-run fixture
from api.deps import Principal, current_principal
from api.routes import decision_control as route
from api.routes import publication_control as pub_route
import importlib
from core.collaboration_store import CollaborationStore
from core.decision_case import DecisionCase
from core.decision_ledger import DecisionLedger
from core.decision_source_binding import bind_decision_evidence
from core.org_directory import AccessScope
from core.publication import Publication


def body(basis="SIMULATION"):
    return {"question": "합성 시험: 증설 여부", "package": {
        "baseline": "무행동", "options": ["유지", "증설"]},
        "evidence": {}, "due_at": "", "evidence_basis": basis}


@pytest.fixture
def client(catalog, tmp_path, monkeypatch):
    service = DecisionCase(CollaborationStore(str(tmp_path / "cases.db")),
                           DecisionLedger(str(tmp_path / "ledger.db")))
    monkeypatch.setattr(route, "decision_sources", catalog)
    monkeypatch.setattr(route, "decision_case", service)
    monkeypatch.setattr(importlib.import_module("core.decision_case"), "decision_case", service)
    monkeypatch.setattr(pub_route, "publication", Publication(service._store, service._ledger))
    app = FastAPI()
    actor = {"user": "requester", "scopes": frozenset({"scope-mnm"})}
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=actor["user"], scope=AccessScope(
            user_id=actor["user"], unrestricted=False, readable_scope_nodes=actor["scopes"]))
    app.include_router(route.router)
    app.include_router(pub_route.router)
    with TestClient(app) as http:
        yield http, actor, service


URL = "/api/v1/simulations/sim_server_only/decision-cases"


@pytest.mark.parametrize("basis", ["SIMULATION", "MEASURED", "EXTERNAL", "JUDGMENT"])
def test_explicit_basis_roundtrips_through_actual_router(client, basis):
    http, _, _ = client
    response = http.post(URL, json=body(basis))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["evidence_basis"] == basis
    assert data["scope_id"] == "scope-mnm"
    assert data["baseline_id"] == data["evidence"]["baseline_id"] == "bln_server_only"
    assert data["scenario_id"] == data["evidence"]["scenario_id"] == "scn_hidden"
    assert data["evidence"]["engine_version"] == "1.0.0"
    assert data["evidence"]["simulation_binding"]["input_hash"] == "fingerprint"
    saved = http.get(f'/api/v1/decisions/{data["decision_id"]}').json()["data"]
    assert saved["evidence_hash"] == data["evidence_hash"]
    assert saved["evidence_basis"] == basis


@pytest.mark.parametrize("basis", [None, "", "UNSTATED", "unknown"])
def test_no_implicit_basis_default(client, basis):
    http, _, _ = client
    payload = body(basis)
    if basis is None:
        del payload["evidence_basis"]
    response = http.post(URL, json=payload)
    assert response.status_code == (422 if basis is None else 400)
    assert http.get("/api/v1/decisions/queue").json()["data"] == []


@pytest.mark.parametrize("key", ["simulation_binding", "baseline_id", "scenario_id", "engine_version"])
def test_caller_cannot_forge_server_evidence(client, key):
    http, _, _ = client
    payload = body()
    payload["evidence"][key] = "forged"
    assert http.post(URL, json=payload).status_code == 422
    assert http.get("/api/v1/decisions/queue").json()["data"] == []


@pytest.mark.parametrize("key", ["baseline_id", "scenario_id", "scope_id"])
def test_client_cannot_supply_source_identity(client, key):
    http, _, _ = client
    assert http.post(URL, json={**body(), key: "forged"}).status_code == 422


def test_foreign_and_missing_source_are_hidden(client):
    http, actor, _ = client
    actor["scopes"] = frozenset({"other"})
    foreign = http.post(URL, json=body())
    missing = http.post(URL.replace("sim_server_only", "missing"), json=body())
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


@pytest.mark.parametrize("column", ["engine_version", "input_hash"])
def test_incomplete_seal_is_disabled_and_rechecked_on_create(client, catalog, column):
    http, _, _ = client
    assert http.get("/api/v1/decisions/sources").json()["data"][0]["bindable"] is True
    conn = catalog.store._connect()
    try:
        conn.execute(f"UPDATE simulation_runs SET {column}=''")
        conn.commit()
    finally:
        conn.close()
    option = http.get("/api/v1/decisions/sources").json()["data"][0]
    assert option["bindable"] is False
    assert option["blocked_reason"]
    assert http.post(URL, json=body()).status_code == 409


def test_evidence_binding_preserves_input_and_custom_evidence(catalog):
    source = catalog.resolve("sim_server_only", {"scope-mnm"})
    supplied = {"cost": {"value": "100", "verified": False}}
    before = deepcopy((source, supplied))
    evidence = bind_decision_evidence(source, supplied)
    assert (source, supplied) == before
    assert evidence["simulation_binding"] is not source["binding"]
    assert evidence["cost"] == supplied["cost"]


def test_simulation_create_review_decide_action_measure_and_publication_with_real_ledger(client):
    http, actor, service = client
    created = http.post(URL, json=body())
    assert created.status_code == 200, created.text
    did = created.json()["data"]["decision_id"]
    base = f"/api/v1/decisions/{did}"
    views = http.post(base + "/generate-views").json()["data"]
    assert views["same_package"] is True
    reviewed = http.post(base + "/request-review", json={"participants": [
        {"user_id": "decider", "role": "DECIDER"}]})
    assert reviewed.status_code == 200, reviewed.text
    actor["user"] = "decider"
    decided = http.post(base + "/decide", json={"outcome": "APPROVED", "rationale": "합성 검증"})
    assert decided.status_code == 200, decided.text
    assert decided.json()["data"]["status"] == "DECIDED"
    actions = http.post(base + "/create-actions", json={"actions": [
        {"action": "합성 실행", "owner_user_id": "decider", "due_at": "2026-09-30"}]})
    assert actions.status_code == 200, actions.text
    action = actions.json()["data"]["actions"][0]
    assert action["measured_effect"] == ""
    measured = http.post(base + "/measure-effect", json={
        "action_id": action["action_id"], "measured_effect": "합성 측정: 기준안 대비 0"})
    assert measured.status_code == 200, measured.text
    assert measured.json()["data"]["status"] == "EFFECT_MEASURED"
    events = service._ledger.list_events(subject_id=did)
    assert {"DECISION_CASE_CREATED", "DECISION_REVIEW_REQUESTED", "DECISION_RECORDED",
            "DECISION_ACTION_CREATED", "DECISION_EFFECT_MEASURED"}.issubset(
                {event["event_type"] for event in events})
    # Actual Publication default source loader reads this same persisted decision.
    publication = http.post("/api/v1/publications", json={
        "title": "합성 결정 보고", "source_type": "DECISION_CASE", "source_id": did,
        "scope_id": "scope-mnm"})
    assert publication.status_code == 200, publication.text
    pid = publication.json()["data"]["publication_id"]
    pub_base = f"/api/v1/publications/{pid}"
    rendered = http.post(pub_base + "/render")
    assert rendered.status_code == 200, rendered.text
    document = rendered.json()["data"]["current_version"]["document"]
    assert document["evidence"]["source_id"] == did
    assert document["evidence"]["source_evidence_hash"] == created.json()["data"]["evidence_hash"]
    assert document["header"]["outcome"] == "APPROVED"
    targets = [{"target": "synthetic.invalid", "channel": "TEST_ONLY"}]
    assert http.post(pub_base + "/publish", json={"targets": targets}).status_code == 400
    assert http.post(pub_base + "/request-approval", json={"review_types": ["EXECUTIVE"]}).status_code == 200
    assert http.post(pub_base + "/approve", json={"review_type": "EXECUTIVE"}).status_code == 200
    # No adapter: production route must record failure, never pretend external delivery happened.
    unsent = http.post(pub_base + "/publish", json={"targets": targets})
    assert unsent.status_code == 200, unsent.text
    assert unsent.json()["data"]["status"] == "APPROVED"
    assert unsent.json()["data"]["distributions"][0]["status"] == "FAILED"
    published = pub_route.publication.publish(pid, "decider", targets,
        adapter=lambda _pub, _target: "synthetic-receipt", viewer_scopes={"scope-mnm"})
    assert published["status"] == "PUBLISHED"
    assert {"PUBLICATION_PUBLISH_FAILED", "PUBLICATION_PUBLISHED"}.issubset(
        {event["event_type"] for event in service._ledger.list_events(subject_id=pid)})
