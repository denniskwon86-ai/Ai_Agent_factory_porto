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


# ── [M0-4] 시작점 목록 — 화면이 손으로 치지 않게 한다 ──────────────────────

def _approved_graph(client, holder):
    """관계 하나를 승인 상태로 세우고 relation_id 를 돌려준다."""
    assert client.post("/api/v1/ontology/model/install",
                       json={"contract": _contract()}).status_code == 200
    proposed = client.post("/api/v1/ontology/relations/propose", json=_proposal())
    rid = proposed.json()["data"]["relation_id"]
    client.post(f"/api/v1/ontology/relations/{rid}/submit")
    holder["principal"] = _principal("governor@example.com")
    assert client.post(f"/api/v1/ontology/relations/{rid}/approve",
                       json={"decision_ledger_id": "ledger-relation-v1"}).status_code == 200
    return rid


def test_objects_endpoint_lists_selectable_roots(tmp_path, monkeypatch):
    """★★★ [M0-4] 시작점을 고를 방법이 없어 사용자가 `dataset:shipment:SHP-001` 을
    손으로 쳐야 했다 — 그것은 「개발자 도구 없이 완주」가 아니다."""
    client, _, _, holder = _harness(tmp_path, monkeypatch)
    _approved_graph(client, holder)

    res = client.get("/api/v1/ontology/objects",
                     params={"as_of": "2026-03-01T00:00:00Z"})
    assert res.status_code == 200
    data = res.json()["data"]
    keys = {f"{o['namespace']}:{o['object_type']}:{o['object_id']}"
            for o in data["objects"]}
    #: 승인된 관계의 **양 끝**이 후보다.
    assert keys == {"dataset:shipment:SHP-001", "dataset:inventory-snapshot:INV-001"}
    assert set(data["object_types"]) == {"shipment", "inventory-snapshot"}
    assert data["truncated"] is False


def test_objects_endpoint_hides_what_impact_hides(tmp_path, monkeypatch):
    """★★★ **목록과 질의의 가시성이 같아야 한다.**

    ⚠️ 두 벌로 만들면 목록에는 뜨는데 질의하면 빈 결과가 나오고, 사용자는 그것을
      고장으로 읽는다. 그리고 못 본 것의 **수를 세어 주지 않는다** — 「권한 밖 1건」은
      그 자체로 「그 조직에 1건이 있다」를 알려 준다."""
    client, _, hidden, holder = _harness(tmp_path, monkeypatch)
    _approved_graph(client, holder)
    hidden.add("dataset:inventory-snapshot:INV-001")

    res = client.get("/api/v1/ontology/objects",
                     params={"as_of": "2026-03-01T00:00:00Z"})
    data = res.json()["data"]
    keys = {f"{o['namespace']}:{o['object_type']}:{o['object_id']}"
            for o in data["objects"]}
    assert keys == {"dataset:shipment:SHP-001"}, "가려진 끝점이 목록에 남았다"
    #: 개수를 누설하지 않는다 — 응답 어디에도 «숨긴 수» 가 없다.
    assert "hidden" not in res.text and "denied" not in res.text

    impact = client.post("/api/v1/ontology/query/impact", json={
        "roots": [_proposal()["subject"]], "target_types": ["inventory-snapshot"],
        "relation_types": ["AFFECTS"], "as_of": "2026-03-01T00:00:00Z"})
    assert impact.json()["data"]["paths"] == [], "목록은 가렸는데 질의는 열려 있다"


def test_objects_endpoint_needs_resolver(tmp_path, monkeypatch):
    """⚠️ 범위 해석기가 없으면 **가시성을 판정할 수 없다** — 빈 목록이 아니라 503 이다."""
    client, _, _, _ = _harness(tmp_path, monkeypatch, with_resolver=False)
    res = client.get("/api/v1/ontology/objects",
                     params={"as_of": "2026-03-01T00:00:00Z"})
    assert res.status_code == 503, res.text[:200]


def test_objects_endpoint_filters_by_type(tmp_path, monkeypatch):
    """★ 화면이 「이 질문에 쓸 수 있는 시작점」만 보여 줄 수 있어야 한다."""
    client, _, _, holder = _harness(tmp_path, monkeypatch)
    _approved_graph(client, holder)
    res = client.get("/api/v1/ontology/objects",
                     params={"as_of": "2026-03-01T00:00:00Z", "object_type": "shipment"})
    data = res.json()["data"]
    assert [o["object_id"] for o in data["objects"]] == ["SHP-001"]
