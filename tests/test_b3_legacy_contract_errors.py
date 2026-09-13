"""Legacy 계약 API의 ProcessError 분류 보존 시험. 실행은 main 격리 runner 전용.

실제 parent FastAPI router/current_principal/권한표/조직 scope 검사를 사용한다.
instance 조회·profile·blueprint 및 kc.draft/approve는 명시적 대역이다. 계약 생성,
승인, 원장, 게시, 인증 데이터의 서비스 E2E를 검증했다고 주장하지 않는다.
신뢰 헤더는 기존 api_client fixture만 사용하며 dependency override는 없다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import headers, workspace  # noqa: F401
from tests.test_b3_kit_api import api_client  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


BASE = "/api/v1/data-preparation/instances/{instance_id}/apps/{app_id}/"
SUFFIXES = ("contract", "contract/approve")


def url(w, suffix):
    return BASE.format(instance_id=w["instance"]["instance_id"], app_id=w["blueprint"]["app_id"]) + suffix


def body(suffix):
    if suffix == "contract":
        return {"app_class": "departmental"}
    return {"revision": 7, "rationale": "합성 legacy HTTP 오류 분류 검토"}


@pytest.fixture
def legacy_error_stubs(api_client, workspace, tmp_path, monkeypatch):
    from api.routes import data_preparation_control as preparation
    from core import kit_app_contract as kc
    from core.enterprise_context.process_schema import ProcessError
    from core.org_directory import org_directory

    # legacy cohort guard는 대역으로 바꾸지 않는다. 조회되는 저장소는 모두 tmp다.
    root = tmp_path.resolve()
    for source in (preparation.store, workspace["svc"].repo, org_directory):
        assert Path(source.db_path).resolve().is_relative_to(root)
    assert not api_client.app.dependency_overrides
    instance = {"instance_id": "test-legacy-contract-error-instance",
                "kit_id": "TEST-LEGACY-ERROR-STUB", "version": "1.0",
                "kit_fingerprint": "synthetic-lookup-only", "status": "active",
                **workspace["context"]}
    profile = {"datasets": [{"dataset_contract_key": "LEGACY-INPUT",
                             "label": "합성 입력", "purpose": "오류 매핑 시험"}]}
    blueprint = {"app_id": "APP-LEGACY-ERROR", "datasets": ["LEGACY-INPUT"]}
    state = {"instance": instance, "profile": profile, "blueprint": blueprint,
             "calls": [], "service_calls": [],
             "failure": ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "명시적 서비스 오류 대역", 503)}

    def instance_stub(instance_id):
        state["calls"].append("instance")
        assert instance_id == instance["instance_id"]
        return dict(instance)

    def profile_stub(actual_instance):
        state["calls"].append("profile")
        assert actual_instance == instance
        return profile

    def blueprint_stub(actual_profile, app_id):
        state["calls"].append("blueprint")
        assert actual_profile is profile and app_id == blueprint["app_id"]
        return blueprint

    def fail_service(action, actual_store, kwargs):
        state["calls"].append(action)
        assert actual_store is preparation.store
        state["service_calls"].append({"action": action, **kwargs})
        raise state["failure"]

    def draft_stub(actual_store, **kwargs):
        return fail_service("draft", actual_store, kwargs)

    def approve_stub(actual_store, **kwargs):
        return fail_service("approve", actual_store, kwargs)

    # _instance_or_404/current_principal/require_caps/권한표/오류 변환기는 실제 코드다.
    monkeypatch.setattr(preparation.store, "get_instance", instance_stub)
    monkeypatch.setattr(preparation, "_kit_profile_or_503", profile_stub)
    monkeypatch.setattr(preparation, "_blueprint_or_404", blueprint_stub)
    monkeypatch.setattr(kc, "draft", draft_stub)
    monkeypatch.setattr(kc, "approve", approve_stub)
    return state


@pytest.mark.parametrize("suffix", SUFFIXES)
@pytest.mark.parametrize("status,reason", [
    (409, "PROCESS_CONTRACT_CONFLICT"),
    (503, "PROCESS_CONTRACT_UNAVAILABLE"),
])
def test_legacy_http_preserves_process_error_from_explicit_service_stub(
        api_client, legacy_error_stubs, suffix, status, reason):
    from core import admin_capability as caps, route_authority
    from core.enterprise_context.process_schema import ProcessError

    w = legacy_error_stubs
    is_draft = suffix == "contract"
    actor = org.MEMBER_A if is_draft else org.DATA_ADMIN
    expected_cap = caps.PROJECT_RUN if is_draft else caps.ADMIN_DATA_ACCESS
    assert route_authority.required_caps("POST", BASE + suffix) == (expected_cap,)
    message = "합성 legacy 계약 오류: 입력과 최신 승인판을 보존하십시오."
    w["failure"] = ProcessError(reason, message, status)

    response = api_client.post(url(w, suffix), json=body(suffix), headers=headers(actor))

    assert response.status_code == status, response.text
    payload = response.json()
    assert "data" not in payload and payload.get("status") != "success"
    assert payload["detail"]["reason_code"] == reason
    assert payload["detail"]["message"] == message
    assert isinstance(payload["detail"]["next_action"], str) and payload["detail"]["next_action"]
    assert w["calls"] == (["instance", "profile", "blueprint", "draft"] if is_draft
                           else ["instance", "approve"])
    assert len(w["service_calls"]) == 1
    call = w["service_calls"][0]
    assert call["actor_id"] == actor and call["instance_id"] == w["instance"]["instance_id"]
    if is_draft:
        assert call["blueprint"] == w["blueprint"] and call["app_class"] == "departmental"
        assert {key: call[key] for key in ("tenant_id", "entity_mode", "scope_node_id")} == {
            key: w["instance"][key] for key in ("tenant_id", "entity_mode", "scope_node_id")}
        assert call["labels"] == {"LEGACY-INPUT": {"label": "합성 입력", "purpose": "오류 매핑 시험"}}
    else:
        assert call["app_id"] == w["blueprint"]["app_id"]
        assert call["revision"] == 7 and call["rationale"] == body(suffix)["rationale"]


@pytest.mark.parametrize("suffix,actor,status", [
    ("contract", None, 401),
    ("contract/approve", None, 401),
    ("contract", org.VIEWER_A, 403),
    ("contract/approve", org.VIEWER_A, 403),
    ("contract/approve", org.MEMBER_A, 403),
    ("contract/approve", org.MANAGER_A, 403),
])
def test_legacy_real_authority_denies_before_lookup_or_service_stub(
        api_client, legacy_error_stubs, suffix, actor, status):
    w = legacy_error_stubs
    response = api_client.post(url(w, suffix), json=body(suffix),
                               headers=headers(actor) if actor else {})
    assert response.status_code == status, response.text
    assert w["calls"] == [] and w["service_calls"] == []
    assert "PROCESS_CONTRACT_UNAVAILABLE" not in response.text
