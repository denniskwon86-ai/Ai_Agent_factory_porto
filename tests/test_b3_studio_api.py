"""B3 실제 FastAPI/route guard/PDP/ProcessContext 통합. main audit 런너만 실행.

new router를 정식 advisor prefix와 실제 guard로 포함한다. HTTP 신원은 명시적으로
활성화한 개발용 합성 헤더를 실제 current_principal이 해석한다(운영 인증 시험 아님).
AdvisorStore/DecisionLedger/ECM/조직/파일은 새 temp, Factory provision만 명시적 대역.
전역 conftest·LLM·RAW·원본 Starter·운영 프로젝트를 사용하지 않는다.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from tests.test_b3_studio_drafts import (
    PATCH, _count, _db, enforced_org, isolated_stores, real_studio,  # noqa: F401
)
from tests.test_b3_studio_bootstrap import _events, _files, _make_bootstrap


PREFIX = "/api/v1/advisor"


@pytest.fixture
def studio_api(real_studio, monkeypatch):
    import config
    from fastapi import Depends, FastAPI, Request
    from fastapi.testclient import TestClient
    from api import deps
    from api.routes import studio_draft_control as routes
    from core import studio_bootstrap as bootstrap_module
    from core.enterprise_context import audit
    from core.route_authority import guard

    env = _make_bootstrap(real_studio)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "")
    monkeypatch.setattr(config, "ORG_USER_HEADER", "X-Factory-User")
    monkeypatch.setattr(config, "ECM_SCOPE_HEADER", "X-Enterprise-Scope")
    monkeypatch.setattr(config, "ECM_TENANT_HEADER", "X-Enterprise-Tenant")
    monkeypatch.setattr(config, "ECM_MODE_HEADER", "X-Entity-Mode")
    monkeypatch.setattr(audit, "_LOG_PATH", str(env.root / "api-access.test.invalid.jsonl"))
    # 서비스 로직/PDP는 실제다. 전역 singleton 대신 위의 새 temp 저장 객체만 주입한다.
    monkeypatch.setattr(routes, "StudioDraftService", lambda: env.drafts)
    monkeypatch.setattr(bootstrap_module, "StudioBootstrapService", lambda: env.bootstrap)
    seen = []
    principal = deps.current_principal

    async def capture_principal(request):
        p = await principal(request)
        requested = (request.headers.get("X-Enterprise-Scope") or request.query_params.get("enterprise_scope") or "")
        assert p.requested_scope_node_id == requested.strip()
        seen.append((p.user_id, p.requested_scope_node_id))
        return p

    # fixture-local Request에 postponed annotation을 쓰면 FastAPI가 query parameter로
    # 오인할 수 있다. 실제 Request 타입을 명시한다. 권한/주체를 대역으로 만들지는 않는다.
    capture_principal.__annotations__["request"] = Request
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX, dependencies=[Depends(guard)])
    app.dependency_overrides[deps.current_principal] = capture_principal
    with TestClient(app) as client:
        yield SimpleNamespace(**vars(env), client=client, app=app, seen=seen)


def _headers(env, actor=None, *, scope=True, **changes):
    headers = {"X-Factory-User": actor or env.author, "X-Enterprise-Tenant": "tenant_default", "X-Entity-Mode": "REAL"}
    if scope:
        headers["X-Enterprise-Scope"] = env.boundary.scope_node_id if scope is True else scope
    headers.update(changes)
    return headers


def _boundary(env):
    return {"context_root_id": env.boundary.context_root_id, "scope_node_id": env.boundary.scope_node_id}


def _save_body(env, previous=None, **changes):
    body = {**_boundary(env), "draft_id": previous["draft_id"] if previous else "",
            "expected_revision": previous["revision"] if previous else 0,
            "expected_digest": previous["digest"] if previous else "", "patch": copy.deepcopy(PATCH),
            "client_request_id": f"http-save-{previous['revision'] + 1}" if previous else "http-save-1"}
    if previous is None:
        body["process_selection"] = copy.deepcopy(env.selection)
    body.update(changes)
    return body


def _post(env, path, body, *, actor=None, headers=None):
    return env.client.post(PREFIX + path, json=body, headers=headers if headers is not None else _headers(env, actor))


def _ok(response):
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    return response.json()["data"]


def _save(env, previous=None, **changes):
    return _ok(_post(env, "/drafts", _save_body(env, previous, **changes)))


def _decide(env, draft, actor=None):
    body = {**_boundary(env), "expected_revision": draft["revision"], "draft_digest": draft["digest"],
            "decision": "APPROVED", "reason": "HTTP 실제 권한 독립 승인"}
    return _post(env, f"/drafts/{draft['draft_id']}/decision", body, actor=actor or env.reviewer)


def _bootstrap_body(env, approved):
    ref = approved.get("process_ref") or {}
    return {**_boundary(env), "approved_revision_id": approved["revision_id"], "approved_digest": approved["digest"],
            "expected_process_semantic_digest": ref.get("process_semantic_fingerprint", "a" * 64),
            "client_request_id": "http-bootstrap-1"}


def test_api_real_save_approve_bootstrap_without_data_and_repeat(studio_api):
    env = studio_api
    draft = _save(env)
    assert env.seen[-1] == (env.author, env.boundary.scope_node_id)
    assert draft["process_ref"]["verified_binding_refs"] == []
    assert "RUN" not in draft["process_ref"]["permitted_actions"]
    approved = _ok(_decide(env, draft))
    assert approved["decision_actor"] == env.reviewer
    body = _bootstrap_body(env, approved)
    completed = _ok(_post(env, "/drafts/bootstrap-project", body))
    assert completed["stage"] == "COMPLETED" and completed["approved_revision_id"] == approved["revision_id"]
    assert _ok(_post(env, "/drafts/bootstrap-project", body)) == completed
    assert len(_events(env)) == 1 and len(env.provision.calls) == 1
    assert all(value["setup_status"] == "READY" for value in _files(env, completed))
    result = env.client.get(PREFIX + f"/drafts/bootstrap-operations/{completed['operation_id']}",
                            params=_boundary(env), headers=_headers(env))
    assert _ok(result) == completed
    assert _count(env, "solution_blueprints") == 0


def test_api_missing_explicit_scope_does_not_use_principal_department_fallback(studio_api):
    env = studio_api
    response = _post(env, "/drafts", _save_body(env), headers=_headers(env, scope=False))
    assert response.status_code == 422 and response.json()["detail"]["reason_code"] == "PROCESS_CONTEXT_REQUIRED"
    assert env.seen[-1] == (env.author, "")
    assert _count(env, "advisor_v2_revisions") == 0


def test_api_missing_root_is_validation_error(studio_api):
    env = studio_api
    body = _save_body(env)
    body.pop("context_root_id")
    assert _post(env, "/drafts", body).status_code == 422
    assert _count(env, "advisor_v2_revisions") == 0


@pytest.mark.parametrize("axis", ["tenant", "root", "mode", "scope"])
def test_api_wrong_exact_context_cannot_read_or_edit_draft(studio_api, axis):
    env = studio_api
    draft = _save(env)
    body = _save_body(env, draft)
    headers = _headers(env)
    query = _boundary(env)
    if axis == "tenant":
        headers["X-Enterprise-Tenant"] = "foreign-tenant.test.invalid"
    elif axis == "root":
        body["context_root_id"] = query["context_root_id"] = "foreign-root.test.invalid"
    elif axis == "mode":
        headers["X-Entity-Mode"] = "VIRTUAL"
    else:
        body["scope_node_id"] = query["scope_node_id"] = env.org.NODES[env.org.DEPT_B]
    response = _post(env, "/drafts", body, headers=headers)
    assert response.status_code == 404, response.text
    response = env.client.get(PREFIX + f"/drafts/{draft['draft_id']}", params=query, headers=headers)
    assert response.status_code == 404, response.text
    assert draft["blueprint"]["title"] not in response.text
    assert _count(env, "advisor_v2_revisions") == 1


@pytest.mark.parametrize("field", ["actor", "author_actor", "owner_user_id", "tenant_id", "entity_mode",
    "command_digest", "approved_revision_id", "runtime_document_version", "setup_status",
    "approved_blueprint_revision_id", "approved_blueprint_digest"])
def test_api_extra_top_level_authority_fields_are_rejected(studio_api, field):
    env = studio_api
    body = _save_body(env, **{field: "forged"})
    assert _post(env, "/drafts", body).status_code == 422
    assert _count(env, "advisor_v2_revisions") == 0


@pytest.mark.parametrize("field", ["runtime_document_version", "setup_status",
                                  "approved_blueprint_revision_id", "approved_blueprint_digest"])
def test_api_patch_cannot_smuggle_server_provenance_fields(studio_api, field):
    env = studio_api
    response = _post(env, "/drafts", _save_body(env, patch=[{"op": "SET", "path": [field], "value": "forged"}]))
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["reason_code"] == "ADVISOR_AUTHORITY_FIELDS_FORBIDDEN"
    assert _count(env, "advisor_v2_revisions") == 0


def test_api_omitted_selection_preserves_and_null_clears_without_losing_draft(studio_api):
    env = studio_api
    first = _save(env)
    second_body = _save_body(env, first)
    assert "process_selection" not in second_body
    second = _ok(_post(env, "/drafts", second_body))
    assert second["process_ref"] == first["process_ref"]
    third = _save(env, second, process_selection=None)
    assert third["process_ref"] is None
    approved = _ok(_decide(env, third))
    response = _post(env, "/drafts/bootstrap-project", _bootstrap_body(env, approved))
    assert response.status_code == 409 and response.json()["detail"]["reason_code"] == "ADVISOR_PROCESS_CONTEXT_REQUIRED"
    current = env.client.get(PREFIX + f"/drafts/{first['draft_id']}", params=_boundary(env), headers=_headers(env))
    assert _ok(current) == approved
    assert _count(env, "advisor_v2_bootstraps") == 0 and not env.provision.calls


def test_api_exact_save_replay_returns_original_even_after_new_head(studio_api):
    env = studio_api
    body = _save_body(env)
    original = _ok(_post(env, "/drafts", body))
    newer = _save(env, original)
    assert _ok(_post(env, "/drafts", body)) == original
    changed = {**body, "patch": [{"op": "SET", "path": ["title"], "value": "다른 명령"}]}
    response = _post(env, "/drafts", changed)
    assert response.status_code == 409 and response.json()["detail"]["reason_code"] == "ADVISOR_IDEMPOTENCY_CONFLICT"
    assert newer["revision"] == 2 and _count(env, "advisor_v2_revisions") == 2


def test_api_real_route_guard_covers_new_write_endpoints(studio_api):
    from core.route_authority import required_caps
    env = studio_api
    for suffix in ("/drafts", "/drafts/process-context", "/drafts/{draft_id}/decision", "/drafts/bootstrap-project"):
        assert required_caps("POST", PREFIX + suffix), suffix
    response = _post(env, "/drafts", _save_body(env), actor=env.org.VIEWER_A)
    assert response.status_code == 403
    headers = _headers(env)
    headers.pop("X-Factory-User")
    assert _post(env, "/drafts", _save_body(env), headers=headers).status_code == 401
    assert _count(env, "advisor_v2_revisions") == 0


def test_api_author_cannot_approve_and_foreign_actor_cannot_read_operation(studio_api):
    env = studio_api
    draft = _save(env)
    assert _decide(env, draft, actor=env.author).status_code == 403
    approved = _ok(_decide(env, draft))
    operation = _ok(_post(env, "/drafts/bootstrap-project", _bootstrap_body(env, approved)))
    response = env.client.get(PREFIX + f"/drafts/bootstrap-operations/{operation['operation_id']}",
                               params=_boundary(env), headers=_headers(env, actor=env.other))
    assert response.status_code == 404
    assert operation["project_id"] not in response.text


def test_api_process_context_is_server_built_and_no_data_run_is_blocked(studio_api):
    env = studio_api
    body = {**_boundary(env), "profile_id": env.selection["profile_id"], "process_ids": env.selection["process_ids"]}
    result = _ok(_post(env, "/drafts/process-context", body))
    assert result["context_key"]["context_root_id"] == env.boundary.context_root_id
    assert result["verified_binding_refs"] == []
    assert "BOOTSTRAP" in result["permitted_actions"] and "RUN" not in result["permitted_actions"]
    assert _post(env, "/drafts/process-context", {**body, "permitted_actions": ["RUN"]}).status_code == 422


def test_api_completed_ledger_corruption_returns_domain_503_not_unhandled_exception(studio_api):
    env = studio_api
    approved = _ok(_decide(env, _save(env)))
    body = _bootstrap_body(env, approved)
    operation = _ok(_post(env, "/drafts/bootstrap-project", body))
    with _db(env, ledger=True) as conn:
        conn.execute("UPDATE decision_ledger_events SET event_hash=? WHERE event_id=?",
                     ("0" * 64, operation["event_id"]))
    # TestClient의 기본 raise_server_exceptions=True를 유지해 API 미처리 오류도 드러낸다.
    response = _post(env, "/drafts/bootstrap-project", body)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["reason_code"] == "ADVISOR_LEDGER_INTEGRITY"
    assert _count(env, "advisor_v2_bootstraps") == len(_events(env)) == 1
