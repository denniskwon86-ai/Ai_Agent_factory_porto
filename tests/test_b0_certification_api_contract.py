"""정책 관리 API와 보류 중 감사 조회 계약."""
import pytest

from core.data_preparation import certification_subject as cs, snapshot_service as svc
from tests import org_seed as org
from tests.test_b0_certification_subject import company, policy, request, sign


@pytest.fixture
def client(company, monkeypatch):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as route
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(route, "store", company["store"])
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as result:
        yield result


def test_hold_allows_authorized_history_but_blocks_new_signature(company, client):
    policy(company)
    sign(company, request(company))
    executive = request(company, org.EXEC, "EXECUTIVE")
    with company["store"].transaction() as conn:
        conn.execute("UPDATE source_bindings SET config_json=?", ('{"usage_holds":["REHEARSAL_ONLY"]}',))
    base = f"/api/v1/data-preparation/snapshots/{company['sid']}/certifications"
    headers = {"X-Factory-User": org.EXEC, "X-Enterprise-Scope": company["context"]["scope_node_id"]}
    result = client.get(base, headers=headers)
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["review_status"] == "ON_HOLD" and data["usage_holds"] == ["REHEARSAL_ONLY"]
    assert len(data["signatures"]) == 1 and not data["signatures_count_toward_completion"]
    body = {key: value for key, value in executive.items() if key not in ("context", "actor")}
    denied = client.post(base, headers=headers, json=body)
    assert denied.status_code == 409 and denied.json()["detail"]["reason_code"] == "DATA_USAGE_HOLD"
    assert len(svc.actual_certifications(company["store"], company["sid"])) == 1


def test_company_policy_api_requires_admin_and_cas(company, client):
    base = "/api/v1/data-preparation/certification-policies"
    headers = {"X-Factory-User": org.MANAGER_A, "X-Enterprise-Scope": company["root"]}
    body = {"document": company["document"], "evidence_ref": "test-only-explicit-company-approval"}
    assert client.post(base, headers=headers, json=body).status_code == 403
    headers["X-Factory-User"] = org.ADMIN
    created = client.post(base, headers=headers, json=body)
    assert created.status_code == 200, created.text
    current = client.get(base, headers=headers)
    assert current.status_code == 200 and current.json()["data"] == created.json()["data"]
    assert client.post(base, headers=headers, json=body).status_code == 409
    body["expected_policy_id"] = created.json()["data"]["policy_id"]
    revised = client.post(base, headers=headers, json=body)
    assert revised.status_code == 200 and revised.json()["data"]["revision"] == 2


def test_certification_mutations_are_explicit_in_route_authority_table():
    from core.route_authority import ROUTE_CAPS, EXEMPT
    from core.admin_capability import ADMIN_DATA_ACCESS
    assert ROUTE_CAPS["POST /api/v1/data-preparation/certification-policies"] == (ADMIN_DATA_ACCESS,)
    for suffix in ("certifications", "certification-subject-revisions"):
        assert "can_sign" in EXEMPT["POST /api/v1/data-preparation/snapshots/{snapshot_id}/" + suffix]


def test_hidden_certification_attempt_records_actor_and_target(company, client, monkeypatch):
    from api.routes import data_preparation_control as route
    captured = []
    monkeypatch.setattr(route, "_audit", lambda event, **fields: captured.append((event, fields)))
    response = client.get(f"/api/v1/data-preparation/snapshots/{company['sid']}/certifications",
                          headers={"X-Factory-User": org.MEMBER_B, "X-Enterprise-Scope": org.NODES[org.DEPT_B]})
    assert response.status_code == 404
    assert captured[-1][1]["actor"] == org.MEMBER_B
    assert captured[-1][1]["resource_id"] == company["sid"]
    assert captured[-1][1]["outcome"] == "denied"
