"""B4 실제 parent FastAPI 검토 흐름. 실행은 메인 보호 runner만 수행한다.

정상 경로는 실제 후보 artifact와 임시 ECM/DP/조직 저장소를 쓴다. 브라우저 E2E가 아니다.
"""
from types import SimpleNamespace

import pytest

from core.enterprise_context.process_installation import ProcessInstallationService
from core.enterprise_context.process_schema import ProcessError, fingerprint
from tests import org_seed as org
from tests.test_b1_process_configuration import client, headers, workspace, proposal, approval  # noqa: F401
from tests.test_b2_installation import installation, _state, _start, _resume, _get  # noqa: F401
from tests.test_b2_installation_api import plan_body
from tests.test_b4_installation_queries import _query, _ok, _error, _other_directory
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401

ROOT = "/api/v1/enterprise-context"


def _approve_body(draft):
    return {"expected_head_version": draft["base_head_version"],
            "draft_digest": draft["draft_digest"], "reason": "원문을 읽고 별도 승인"}


def test_actual_install_resume_other_author_review_approve_and_refresh(client, installation):
    w = installation
    body = plan_body(client, w)
    plan = _ok(client.post(ROOT + "/process-installations/plan", json=body, headers=headers()))
    original = {**body, "plan_digest": plan["plan_digest"], "client_request_id": "b4-review-api"}
    op = _ok(client.post(ROOT + "/process-installations", json=original, headers=headers()))
    assert op["stage"] == "AWAITING_INSTALLER" and op["permitted_actions"] == []
    url = ROOT + "/process-installations/" + op["operation_id"]
    found = _ok(client.get(ROOT + "/process-installations", params=_query(w), headers=headers(org.MANAGER_A)))
    assert found["items"][0]["permitted_actions"] == ["adopt"]
    _error(client.post(url + "/resume", json={"expected_revision": op["revision"]}, headers=headers(org.MANAGER_A)),
           403, "PROCESS_INSTALLER_ADOPTION_REQUIRED")
    ready = _ok(client.post(url + "/resume", json={"expected_revision": op["revision"], "adopt": True}, headers=headers(org.MANAGER_A)))
    assert ready["stage"] == "AWAITING_APPROVAL" and ready["permitted_actions"] == []
    _error(client.post(url + "/resume", json={"expected_revision": op["revision"], "adopt": True}, headers=headers(org.MANAGER_A)),
           409, "PROCESS_OPERATION_CONFLICT")
    before_read = _state(w)
    listing = _ok(client.get(ROOT + "/process-changes", params=_query(w), headers=headers(org.MANAGER_A)))
    summary = listing["items"][0]
    change_url = ROOT + "/process-changes/" + summary["change_id"]
    detail = _ok(client.get(change_url, params=_query(w), headers=headers(org.MANAGER_A)))
    assert detail == {**summary, "payload": detail["payload"], "base_payload": None}
    assert detail["principal_user_id"] == org.MANAGER_A and detail["actor"] == org.MEMBER_A
    assert detail["operation_id"] == op["operation_id"]
    assert detail["permitted_actions"] == ["read", "approve"] and detail["review_blockers"] == []
    assert fingerprint(detail["payload"]) == detail["draft_digest"]
    assert _state(w) == before_read
    result = _ok(client.post(change_url + "/approve", json=_approve_body(detail), headers=headers(org.MANAGER_A)))
    assert result["status"] == "APPLIED" and result["head_version"] == 1 and result["audit_delivery"] == "PENDING"
    assert result == _ok(client.post(change_url + "/approve", json=_approve_body(detail), headers=headers(org.MANAGER_A)))
    before_refresh = _state(w)
    applied = _ok(client.get(url, headers=headers()))
    assert applied["applied_result"] == result and applied["permitted_actions"] == []
    assert applied["stage"] == "APPLIED" and not applied["data_ready"] and not applied["apps_ready"]
    resolved = _ok(client.get(ROOT + "/process-configurations/resolved", params=_query(w), headers=headers()))
    assert resolved["profile_id"] == result["profile_id"] and resolved["digest"] == result["digest"]
    assert _ok(client.get(ROOT + "/process-changes", params=_query(w), headers=headers())) == {"items": [], "next_offset": None}
    archived = _ok(client.get(change_url, params=_query(w), headers=headers(org.MANAGER_A)))
    assert archived["payload"] == detail["payload"] and archived["base_payload"] is None
    assert archived["review_blockers"] == ["PROCESS_CHANGE_NOT_DRAFT"]
    assert _state(w) == before_refresh


@pytest.fixture
def principal_client(workspace, monkeypatch):
    """SSO 슬롯만 시험에서 설정하고 실제 current_principal/권한표/서비스는 그대로 사용한다."""
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.enterprise_context_control import router
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", False)
    app = FastAPI()
    @app.middleware("http")
    async def authenticated(request, call_next):
        request.state.principal_user_id = org.MANAGER_A
        return await call_next(request)
    app.include_router(router)
    with TestClient(app) as value:
        yield value


def test_server_principal_not_browser_actor_controls_self_approval(principal_client, installation):
    w, c = installation, principal_client
    draft = proposal(w, actor=org.MANAGER_A)
    forged = headers(org.MEMBER_A)
    access = _ok(c.get(ROOT + "/process-configurations/context", headers=forged))
    assert access["principal_user_id"] == org.MANAGER_A
    url = ROOT + "/process-changes/" + draft["change_id"]
    detail = _ok(c.get(url, params={**_query(w), "as_user": org.ADMIN}, headers=forged))
    assert detail["principal_user_id"] == detail["actor"] == org.MANAGER_A
    assert detail["permitted_actions"] == ["read"]
    assert detail["review_blockers"] == ["PROCESS_DISTINCT_REVIEWER_REQUIRED"]
    _error(c.post(url + "/approve", json=_approve_body(draft), headers=forged),
           403, "PROCESS_DISTINCT_REVIEWER_REQUIRED")


@pytest.mark.parametrize("dimension", ["scope", "root", "mode", "tenant"])
def test_actual_review_queries_hide_wrong_context_even_from_admin(client, installation, dimension):
    w = installation
    draft = proposal(w)
    query, selected = _query(w), headers(org.ADMIN)
    if dimension == "scope":
        selected["X-Enterprise-Scope"] = org.NODES[org.DEPT_B]
    elif dimension == "root":
        query["context_root_id"] = org.NODES[org.DEPT_B]
    elif dimension == "mode":
        selected["X-Entity-Mode"] = "VIRTUAL"
    else:
        selected["X-Enterprise-Tenant"] = "review-other-tenant"
    for path in ("/process-changes", "/process-changes/" + draft["change_id"]):
        response = client.get(ROOT + path, params=query, headers=selected)
        _error(response, 404, "PROCESS_NOT_FOUND")
        assert draft["change_id"] not in response.text and draft["draft_digest"] not in response.text


@pytest.mark.parametrize("case", ["anonymous", "scope_missing", "root_missing", "bad_status", "bad_limit"])
def test_review_query_authentication_context_and_page_validation(client, installation, monkeypatch, case):
    import config
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "")
    selected, query, expected = headers(), _query(installation), 422
    if case == "anonymous":
        selected.pop("X-Factory-User")
        expected = 401
    elif case == "scope_missing":
        selected.pop("X-Enterprise-Scope")
    elif case == "root_missing":
        query.pop("context_root_id")
    elif case == "bad_status":
        query["status"] = "ALL"
    else:
        query["limit"] = 101
    response = client.get(ROOT + "/process-changes", params=query, headers=selected)
    assert response.status_code == expected, response.text
    assert "data" not in response.json()


@pytest.mark.parametrize("bad", [{"actor": org.MANAGER_ROOT}, {"expected_head_version": True}, {"context_root_id": "injected-root"}])
def test_existing_approval_body_remains_strict(client, installation, bad):
    draft = proposal(installation)
    response = client.post(ROOT + "/process-changes/" + draft["change_id"] + "/approve",
                           json={**_approve_body(draft), **bad}, headers=headers(org.MANAGER_A))
    assert response.status_code == 422


def test_review_cannot_authorize_a_stale_head_or_different_digest(client, installation):
    w = installation
    draft = proposal(w)
    url = ROOT + "/process-changes/" + draft["change_id"]
    _error(client.post(url + "/approve", json={**_approve_body(draft), "draft_digest": "0" * 64}, headers=headers(org.MANAGER_A)),
           409, "PROCESS_DIGEST_CONFLICT")
    approval(w, proposal(w, key="other-wins"))
    detail = _ok(client.get(url, params=_query(w), headers=headers(org.MANAGER_A)))
    assert detail["payload"]["base_profile_id"] == "" and detail["base_payload"] is None
    assert detail["review_blockers"] == ["PROCESS_HEAD_CONFLICT"]
    _error(client.post(url + "/approve", json=_approve_body(draft), headers=headers(org.MANAGER_A)),
           409, "PROCESS_HEAD_CONFLICT")


def test_operation_actions_follow_current_installer_and_scope_revocation(client, installation):
    w = installation
    op = _start(w, actor=org.MANAGER_A)
    assert op["permitted_actions"] == ["resume"]
    assert _get(w, op, actor=org.MANAGER_ROOT)["permitted_actions"] == ["adopt"]
    _other_directory(w).set_user_roles(org.MANAGER_A, {org.DEPT_A: "viewer", org.DEPT_B: "manager"}, actor=org.ADMIN)
    url = ROOT + "/process-installations/" + op["operation_id"]
    result = _ok(client.get(url, headers=headers(org.MANAGER_A)))
    assert result["permitted_actions"] == []
    response = client.post(url + "/resume", json={"expected_revision": op["revision"]}, headers=headers(org.MANAGER_A))
    _error(response, 403, "PROCESS_ACTION_FORBIDDEN")


def test_operation_edit_without_project_create_does_not_offer_resume(installation, monkeypatch):
    """PROJECT_CREATE만 제거한 명시 정책 대역: 역할명이 아닌 실제 capability 결합을 검증."""
    from core.admin_capability import PROJECT_CREATE
    w = installation
    op = _start(w, actor=org.MANAGER_A)
    original = ProcessInstallationService._authorize
    def no_create(self, conn, boundary, actor, context, action="read"):
        rights = original(self, conn, boundary, actor, context, action)
        return SimpleNamespace(has=lambda cap: cap != PROJECT_CREATE and rights.has(cap))
    monkeypatch.setattr(ProcessInstallationService, "_authorize", no_create)
    assert _get(w, op, actor=org.MANAGER_A)["permitted_actions"] == []
    with pytest.raises(ProcessError) as raised:
        _resume(w, op, adopt=False)
    assert raised.value.reason_code == "PROCESS_INSTALLER_REQUIRED"


def test_scope_readers_can_load_review_but_cannot_publish(client, installation):
    w = installation
    draft = proposal(w)
    detail = _ok(client.get(ROOT + "/process-changes/" + draft["change_id"], params=_query(w), headers=headers(org.VIEWER_A)))
    assert detail["permitted_actions"] == ["read"] and "PROCESS_ACTION_FORBIDDEN" in detail["review_blockers"]
    response = client.post(ROOT + "/process-changes/" + draft["change_id"] + "/approve",
                           json=_approve_body(draft), headers=headers(org.VIEWER_A))
    assert response.status_code == 403
