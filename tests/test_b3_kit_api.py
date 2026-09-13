"""B3 키트 실제 FastAPI 3경로. 메인 격리 runner 전용, 이 파일에서 실행하지 않는다.

실제 parent router/current_principal/route guard/viewing_context/서비스를 사용한다.
신원 추출만 기존 B1처럼 시험용 신뢰 헤더를 켜며 dependency override는 없다.
kit은 실제 후보 load/pin·B1/B2/B0 합성 메타데이터 fixture다. 성공 build의 게시·
물질화는 이름에 명시한 임시 대역이며 실제 Host·RAW·AppData 검증으로 세지 않는다.
"""
from __future__ import annotations

import copy

import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import headers, workspace, proposal  # noqa: F401
from tests.test_b2_installation import installation  # noqa: F401
from tests.test_b3_kit_contract_v2 import kit, publisher_materializer_stub  # noqa: F401
from tests.test_b3_process_context import database
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


BASE = "/api/v1/data-preparation/instances/{instance_id}/apps/APP-03/"
SUFFIXES = ("contract/v2", "contract/v2/approve", "build/v2")


@pytest.fixture
def api_client(workspace, monkeypatch):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as preparation
    from core import app_preview
    from core.data_preparation.store import data_preparation_store
    assert preparation.store is data_preparation_store
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "")
    monkeypatch.setattr(config, "ECM_DEFAULT_TENANT_ID", workspace["boundary"].tenant_id)
    # API가 선택한 Preview 평면만 확인한다. 실제 AppData/Host는 메인 소유 시험이다.
    def preview_store(audience):
        assert audience == app_preview.AUDIENCE_PREVIEW
        return object()
    monkeypatch.setattr(app_preview, "app_data_for", preview_store)
    app = FastAPI()
    app.include_router(preparation.router)
    assert not app.dependency_overrides
    with TestClient(app) as client:
        yield client


def url(w=None, suffix="contract/v2"):
    return BASE.format(instance_id=w["instance_id"] if w else "not-existing") + suffix


def body(w=None, suffix="contract/v2"):
    if suffix == "contract/v2":
        return dict(profile_id=w["fixed"]["profile_id"] if w else "approved-profile",
            process_ids=w["fixed"]["process_ids"] if w else ["selected-process"],
            app_class="departmental", expected_revision=0)
    value = dict(revision=1, expected_fingerprint="a" * 64)
    if suffix == "contract/v2/approve":
        value["rationale"] = "합성 후보 계약 독립 검토"
    return value


def success(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "success"
    return payload["data"]


def rejected(response, code, reason=None):
    assert response.status_code == code, response.text
    if reason:
        assert response.json()["detail"]["reason_code"] == reason
    return response


def create(client, w, *, actor=org.MEMBER_A, **changes):
    return success(client.post(url(w), json={**body(w), **changes}, headers=headers(actor)))


def revision_body(row, *, approve=False):
    result = dict(revision=row["revision"], expected_fingerprint=row["semantic_fingerprint"])
    if approve:
        result["rationale"] = "API 후보 계약 원문 독립 검토"
    return result


def test_three_real_routes_publisher_materializer_stub_and_server_derived_context(api_client, kit, monkeypatch):
    from core import kit_app_contract
    from core.org_directory import org_directory
    from core.studio_release_cohort import get_release_cohort
    row = create(api_client, kit)
    contract = row["contract"]
    assert row["drafted_by"] == org.MEMBER_A
    assert contract["schema_version"] == "2.0"
    assert contract["process_context"] == kit["fixed"]
    assert contract["process_context"]["context_key"] == {
        "tenant_id": kit["boundary"].tenant_id,
        "context_root_id": kit["boundary"].context_root_id,
        "entity_mode": "REAL", "scope_node_id": kit["boundary"].scope_node_id}
    # 데이터 관리자에게 승격용 PROJECT_RELEASE가 없어도 기존 후보 승인권은 유지한다.
    org_directory.set_user_roles(org.DATA_ADMIN, {org.DEPT_ROOT: "viewer"}, actor="test")
    approved = success(api_client.post(url(kit, "contract/v2/approve"),
        json=revision_body(row, approve=True), headers=headers(org.DATA_ADMIN)))
    assert approved["approved_by"] == org.DATA_ADMIN and approved["status"] == "APPROVED"
    assert kit_app_contract.approved(kit["store"], kit["instance_id"], "APP-03") == approved
    calls = publisher_materializer_stub(kit, monkeypatch)
    built = success(api_client.post(url(kit, "build/v2"), json=revision_body(approved), headers=headers()))
    assert calls == ["publish-after-cohort", "materialize"]
    assert built["runtime_document_version"] == "2.0" and built["instance_id"] == kit["instance_id"]
    cohort = get_release_cohort(kit["store"], built["release_id"])
    assert cohort["context_key"] == contract["process_context"]["context_key"]


@pytest.mark.parametrize("suffix", list(SUFFIXES))
def test_anonymous_principal_is_401_before_unknown_instance(api_client, suffix):
    rejected(api_client.post(url(suffix=suffix), json=body(suffix=suffix)), 401)


@pytest.mark.parametrize("suffix", list(SUFFIXES))
def test_real_viewer_guard_denies_all_mutating_routes(api_client, suffix):
    rejected(api_client.post(url(suffix=suffix), json=body(suffix=suffix), headers=headers(org.VIEWER_A)), 403)


def test_member_cannot_use_approval_route(api_client):
    rejected(api_client.post(url(suffix="contract/v2/approve"),
        json=body(suffix="contract/v2/approve"), headers=headers()), 403)


@pytest.mark.parametrize("suffix,extra", [
    ("contract/v2", {"context_root_id": "caller-root"}),
    ("contract/v2", {"process_context": {"permitted_actions": ["GENERATE"]}}),
    ("contract/v2", {"actor_id": org.ADMIN}),
    ("contract/v2/approve", {"approved_by": org.ADMIN}),
    ("build/v2", {"approved_contract": {"status": "APPROVED"}}),
    ("build/v2", {"tenant_id": "other-tenant"}),
])
def test_strict_models_reject_caller_owned_server_fields(api_client, suffix, extra):
    response = api_client.post(url(suffix=suffix), json={**body(suffix=suffix), **extra}, headers=headers(org.ADMIN))
    rejected(response, 422)
    assert any(issue["type"] == "extra_forbidden" for issue in response.json()["detail"])


@pytest.mark.parametrize("suffix,changes,remove", [
    ("contract/v2", {"expected_revision": True}, None),
    ("contract/v2", {"expected_revision": "0"}, None),
    ("contract/v2", {}, "expected_revision"),
    ("contract/v2", {"process_ids": []}, None),
    ("contract/v2/approve", {"revision": True}, None),
    ("contract/v2/approve", {}, "rationale"),
    ("build/v2", {"revision": 0}, None),
    ("build/v2", {"revision": "1"}, None),
    ("build/v2", {"expected_fingerprint": "not-a-digest"}, None),
])
def test_strict_models_reject_coercion_and_missing_review_fields(api_client, suffix, changes, remove):
    value = {**body(suffix=suffix), **changes}
    if remove:
        value.pop(remove)
    rejected(api_client.post(url(suffix=suffix), json=value, headers=headers(org.ADMIN)), 422)


@pytest.mark.parametrize("suffix", list(SUFFIXES))
def test_explicit_selected_scope_required_even_for_admin(api_client, kit, suffix):
    rejected(api_client.post(url(kit, suffix), json=body(kit, suffix),
                            headers={"X-Factory-User": org.ADMIN}), 422, "PROCESS_CONTEXT_REQUIRED")


def test_wrong_selected_scope_is_hidden_even_when_admin_can_see_both(api_client, kit):
    rejected(api_client.post(url(kit), json=body(kit), headers=headers(org.ADMIN, org.NODES[org.DEPT_B])),
             404, "PROCESS_NOT_FOUND")


@pytest.mark.parametrize("field,value", [("tenant_id", "secret-other-tenant"), ("entity_mode", "VIRTUAL"),
                                         ("scope_node_id", org.DEPT_B)])
def test_other_instance_boundary_is_hidden_without_contract_details(api_client, kit, field, value):
    # 수집 시점에는 부서 키만 보존하고 fixture 실행 이후 실제 node ID를 조회한다.
    if field == "scope_node_id":
        value = org.NODES[value]
    with database(kit, "dp") as conn:
        conn.execute(f"UPDATE kit_instances SET {field}=? WHERE instance_id=?", (value, kit["instance_id"]))
    response = rejected(api_client.post(url(kit), json=body(kit), headers=headers()), 404)
    assert kit["instance_id"] not in response.text and kit["fixed"]["profile_id"] not in response.text


def test_unapproved_profile_id_cannot_be_used_as_fixed_context(api_client, kit):
    pending = proposal(kit, [{"op": "RENAME", "process_id": kit["fixed"]["process_ids"][0],
                             "label": "아직 검토 전"}], "api-unapproved-profile")
    rejected(api_client.post(url(kit), json={**body(kit), "profile_id": pending["draft_profile_id"]}, headers=headers()),
             404, "PROCESS_NOT_FOUND")


def test_actual_draft_idempotency_and_revision_cas(api_client, kit):
    from core import kit_app_contract
    first = create(api_client, kit)
    assert create(api_client, kit) == first
    rejected(api_client.post(url(kit), json={**body(kit), "app_class": "personal"}, headers=headers()),
             409, "PROCESS_CONTRACT_CONFLICT")
    second = create(api_client, kit, app_class="personal", expected_revision=1)
    assert second["revision"] == 2 and first["revision"] == 1
    rows = kit_app_contract.list_for_instance(kit["store"], kit["instance_id"])
    assert len(rows) == 2
    assert next(row for row in rows if row["revision"] == 1)["contract"] == first["contract"]


def test_approval_requires_exact_review_fingerprint_and_latest_revision(api_client, kit):
    first = create(api_client, kit)
    value = {**revision_body(first, approve=True), "expected_fingerprint": "0" * 64}
    rejected(api_client.post(url(kit, "contract/v2/approve"), json=value, headers=headers(org.ADMIN)),
             409, "PROCESS_CONTRACT_CONFLICT")
    create(api_client, kit, app_class="personal", expected_revision=1)
    rejected(api_client.post(url(kit, "contract/v2/approve"), json=revision_body(first, approve=True),
                            headers=headers(org.ADMIN)), 409, "PROCESS_CONTRACT_CONFLICT")


def test_build_route_rejects_unapproved_actual_server_row(api_client, kit, monkeypatch):
    from core import kit_app_builder
    row = create(api_client, kit)
    monkeypatch.setattr(kit_app_builder, "publish_release", lambda **_: pytest.fail("미승인 계약 게시"))
    rejected(api_client.post(url(kit, "build/v2"), json=revision_body(row), headers=headers()),
             409, "PROCESS_CONTRACT_APPROVAL_REQUIRED")


def test_current_principal_and_service_observe_role_revocation(api_client, kit):
    from core.org_directory import org_directory
    create(api_client, kit)
    org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
    rejected(api_client.post(url(kit), json=body(kit), headers=headers()), 403)


def test_duplicate_selected_ids_return_structured_service_validation(api_client, kit):
    value = copy.deepcopy(body(kit))
    value["process_ids"] = [value["process_ids"][0]] * 2
    rejected(api_client.post(url(kit), json=value, headers=headers()), 422, "PROCESS_CONTEXT_INVALID")
