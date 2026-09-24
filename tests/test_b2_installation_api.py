"""B2 실제 FastAPI 하위 라우터와 현재 조직 권한. 외부 앱/LLM 호출 없음."""
import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import workspace, client, headers

ROOT = "/api/v1/enterprise-context"


def register(client, workspace):
    req = dict(context_root_id=workspace["boundary"].context_root_id,
               scope_node_id=workspace["boundary"].scope_node_id,
               kit_id="KIT-MFG-NONFERROUS-PROCUREMENT", version="1.2.0")
    response = client.post(ROOT + "/process-packs/register", json=req, headers=headers(org.MANAGER_A))
    assert response.status_code == 200, response.text
    return response.json()["data"]["artifact_digest"]


def plan_body(client, workspace):
    return dict(context_root_id=workspace["boundary"].context_root_id,
                scope_node_id=workspace["boundary"].scope_node_id, artifact_digest=register(client, workspace),
                business_kit_ids=["BK-01"], expected_head_version=0, base_profile_id="", base_fingerprint="",
                reason="구매 업무 골격 검토")


def test_actual_api_plan_install_adopt_approve_and_pinned_data_profile(client, workspace):
    body = plan_body(client, workspace)
    response = client.post(ROOT + "/process-installations/plan", json=body, headers=headers())
    assert response.status_code == 200, response.text
    plan = response.json()["data"]
    assert plan["state"] == "PLANNED" and len(plan["preview"]["nodes"]) == 5
    body.update(plan_digest=plan["plan_digest"], client_request_id="api-install")
    response = client.post(ROOT + "/process-installations", json=body, headers=headers())
    assert response.status_code == 200, response.text
    operation = response.json()["data"]
    assert operation["stage"] == "AWAITING_INSTALLER"
    response = client.post(ROOT + f"/process-installations/{operation['operation_id']}/resume",
                           json={"expected_revision": operation["revision"], "adopt": True}, headers=headers(org.MANAGER_A))
    assert response.status_code == 200, response.text
    ready = response.json()["data"]
    assert ready["stage"] == "AWAITING_APPROVAL"
    change = ready["change"]
    response = client.post(ROOT + f"/process-changes/{change['change_id']}/approve", headers=headers(org.MANAGER_A),
                           json={"expected_head_version": 0, "draft_digest": change["draft_digest"], "reason": "골격만 승인"})
    assert response.status_code == 200, response.text
    result = client.get(ROOT + f"/process-installations/{operation['operation_id']}", headers=headers())
    assert result.status_code == 200
    assert result.json()["data"]["stage"] == "APPLIED"
    assert not result.json()["data"]["data_ready"]
    from core.data_preparation.store import data_preparation_store as store
    from api.routes.data_preparation_control import _kit_profile_or_503
    instance = store.get_instance(ready["kit_instance_ref"])
    profile = _kit_profile_or_503(instance)
    assert profile["version"] == "1.2.0" and profile["datasets"]
    assert store.get_kit_version(instance["kit_id"], instance["version"]) is None
    assert store.list_snapshots(instance["instance_id"]) == []
    from api.routes.data_preparation_control import router as preparation_router
    client.app.include_router(preparation_router)
    read = client.get(f"/api/v1/data-preparation/instances/{instance['instance_id']}/readiness", headers=headers(org.MANAGER_A))
    assert read.status_code == 200, read.text
    assert read.json()["data"]["data_kind"] == "REAL"
    assert read.json()["data"]["datasets"]


def test_api_current_capabilities_explicit_context_and_digest(client, workspace):
    body = plan_body(client, workspace)
    response = client.post(ROOT + "/process-installations/plan", json=body, headers=headers(org.VIEWER_A))
    assert response.status_code == 403
    response = client.post(ROOT + "/process-installations/plan", json=body, headers={"X-Factory-User": org.ADMIN})
    assert response.status_code == 422
    response = client.post(ROOT + "/process-installations/plan", json=body,
                           headers=headers(org.MEMBER_B, org.NODES[org.DEPT_B]))
    assert response.status_code == 404
    response = client.post(ROOT + "/process-installations", json={**body, "plan_digest": "f" * 64,
                           "client_request_id": "bad-digest"}, headers=headers())
    assert response.status_code == 409
    with workspace["svc"].repo._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM enterprise_process_installations").fetchone()[0] == 0


def test_api_registration_is_allowlisted_and_not_member_action(client, workspace):
    body = dict(context_root_id=workspace["boundary"].context_root_id, scope_node_id=workspace["boundary"].scope_node_id,
                kit_id="../../private", version="1.1.0")
    assert client.post(ROOT + "/process-packs/register", json=body, headers=headers()).status_code == 403
    assert client.post(ROOT + "/process-packs/register", json=body, headers=headers(org.MANAGER_A)).status_code == 404
    #: [2026-09-25] 계약을 싣지 않는 1.1.0 은 새 설치 후보가 아니다 — 설치하면 실적 인증이 막힌다.
    legacy = {**body, "kit_id": "KIT-MFG-NONFERROUS-PROCUREMENT", "version": "1.1.0"}
    assert client.post(ROOT + "/process-packs/register", json=legacy, headers=headers(org.MANAGER_A)).status_code == 404
    response = client.get(ROOT + "/process-packs", params={k: body[k] for k in ("context_root_id", "scope_node_id")}, headers=headers(org.VIEWER_A))
    assert response.status_code == 200, response.text
    item = response.json()["data"][0]
    assert item["state"] == "DOMAIN_REVIEW_REQUIRED" and item["data_class"] == "NO_DATA"
    assert len(item["business_kit_ids"]) == 8


@pytest.mark.parametrize("body", [{"expected_revision": True}, {"expected_revision": -1}, {"adopt": True}])
def test_api_resume_schema_does_not_coerce_revision(client, workspace, body):
    response = client.post(ROOT + "/process-installations/unknown/resume", json=body, headers=headers(org.MANAGER_A))
    assert response.status_code == 422


def test_approval_uses_the_explicitly_injected_data_store(workspace, tmp_path):
    from core.data_preparation.store import DataPreparationStore
    from core.data_preparation.process_pack_artifacts import load_bundle, pin_bundle, CANDIDATE_MANIFEST
    from core.enterprise_context.process_installation import ProcessInstallationService
    local_store = DataPreparationStore(str(tmp_path / "injected-preparation.db"))
    bundle = load_bundle(CANDIDATE_MANIFEST)
    pin_bundle(local_store, bundle)
    svc = ProcessInstallationService(workspace["svc"].repo, local_store)
    args = dict(boundary=workspace["boundary"], actor=org.MEMBER_A, context=workspace["context"],
                artifact_digest=bundle["artifact_digest"], business_kit_ids=["BK-01"],
                expected_head_version=0, base_profile_id="", base_fingerprint="", reason="격리 저장소")
    plan = svc.plan(**args)
    op = svc.start(**args, plan_digest=plan["plan_digest"], client_request_id="injected")
    ready = svc.resume(operation_id=op["operation_id"], actor=org.MANAGER_A, context=workspace["context"],
                       expected_revision=op["revision"], adopt=True)
    change = ready["change"]
    result = svc.approve(change_id=change["change_id"], actor=org.MANAGER_A, context=workspace["context"],
                         expected_head_version=0, draft_digest=change["draft_digest"], reason="고정 참조 확인")
    assert result["status"] == "APPLIED"
    assert local_store.get_instance(ready["kit_instance_ref"])


def test_original_author_needs_explicit_adoption_after_installer_changed(workspace, monkeypatch):
    from core.data_preparation.store import data_preparation_store
    from core.data_preparation.process_pack_artifacts import load_bundle, pin_bundle, CANDIDATE_MANIFEST
    from core.enterprise_context.process_installation import ProcessInstallationService
    from core.enterprise_context.process_schema import ProcessError
    svc = ProcessInstallationService(workspace["svc"].repo, data_preparation_store)
    bundle = load_bundle(CANDIDATE_MANIFEST)
    pin_bundle(data_preparation_store, bundle)
    args = dict(boundary=workspace["boundary"], actor=org.MANAGER_A, context=workspace["context"],
                artifact_digest=bundle["artifact_digest"], business_kit_ids=["BK-01"],
                expected_head_version=0, base_profile_id="", base_fingerprint="", reason="작성자 재인수")
    plan = svc.plan(**args)
    op = svc.start(**args, plan_digest=plan["plan_digest"], client_request_id="re-adopt")
    with monkeypatch.context() as patch:
        def fail(_):
            raise ProcessError("PROCESS_ARTIFACT_STORAGE_UNAVAILABLE", "시험 원본 장애", 503)
        patch.setattr(svc, "_bundle", fail)
        with pytest.raises(ProcessError):
            svc.resume(operation_id=op["operation_id"], actor=org.MANAGER_ROOT, context=workspace["context"],
                       expected_revision=op["revision"], adopt=True)
    current = svc.get(operation_id=op["operation_id"], actor=org.MANAGER_A, context=workspace["context"])
    assert current["installer"] == org.MANAGER_ROOT
    with pytest.raises(ProcessError) as error:
        svc.resume(operation_id=op["operation_id"], actor=org.MANAGER_A, context=workspace["context"],
                   expected_revision=current["revision"], adopt=False)
    assert error.value.reason_code == "PROCESS_INSTALLER_ADOPTION_REQUIRED"
