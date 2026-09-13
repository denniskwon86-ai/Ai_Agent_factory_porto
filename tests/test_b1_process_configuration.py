"""B1 정상 흐름·명령 계약·API 연결. 실제 사용자/운영 DB를 쓰지 않는다."""
import copy
import sqlite3

import pytest

from core.enterprise_context.process_configuration import ProcessConfigurationService
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError
from tests import org_seed as org


@pytest.fixture
def workspace(enforced_org):
    from core.enterprise_context.repository import ecm_repository
    boundary = ProcessBoundary(tenant_id="tenant_default", context_root_id=org.NODES[org.DEPT_ROOT],
                               entity_mode="REAL", scope_node_id=org.NODES[org.DEPT_A])
    return {"svc": ProcessConfigurationService(ecm_repository), "boundary": boundary,
            "context": {"tenant_id": "tenant_default", "entity_mode": "REAL", "scope_node_id": org.NODES[org.DEPT_A]}}


def proposal(w, commands=None, key="first", actor=org.MEMBER_A):
    base = w["svc"].resolved(boundary=w["boundary"], actor=actor, context=w["context"])
    return w["svc"].propose(boundary=w["boundary"], actor=actor, context=w["context"],
        commands=commands or [{"op": "ADD_NODE", "node": {"process_id": "purchase", "level": "L1", "label": "원료구매"}},
                             {"op": "ADD_NODE", "node": {"process_id": "plan", "level": "L2", "parent_process_id": "purchase", "label": "구매계획"}}],
        expected_head_version=base["head_version"], base_profile_id=base["profile_id"], base_fingerprint=base["digest"],
        client_request_id=key, reason="시험 변경", legacy_token=base["legacy_token"])


def approval(w, draft, actor=org.MANAGER_A):
    return w["svc"].approve(change_id=draft["change_id"], actor=actor, context=w["context"],
        expected_head_version=draft["base_head_version"], draft_digest=draft["draft_digest"], reason="독립 검토 시험")


def test_draft_is_not_the_effective_map(workspace):
    draft = proposal(workspace)
    read = workspace["svc"].resolved(boundary=workspace["boundary"], actor=org.VIEWER_A, context=workspace["context"])
    assert read["state"] == "UNCONFIGURED" and read["payload"] is None and read["head_version"] == 0
    validation = workspace["svc"].validate(change_id=draft["change_id"], actor=org.MEMBER_A,
                                          context=workspace["context"], draft_digest=draft["draft_digest"])
    assert validation["review_required"] == "DISTINCT_PUBLISHER"
    assert not validation["data_ready"] and not validation["apps_ready"]


def test_approval_revision_history_and_event_are_consistent(workspace):
    first = approval(workspace, proposal(workspace))
    draft = proposal(workspace, [{"op": "RENAME", "process_id": "plan", "label": "원료 구매계획"}], "rename")
    second = approval(workspace, draft)
    read = workspace["svc"].resolved(boundary=workspace["boundary"], actor=org.VIEWER_A, context=workspace["context"])
    assert read["head_version"] == 2 and read["profile_id"] == second["profile_id"]
    assert read["payload"]["nodes"][1]["process_id"] == "plan"
    old = workspace["svc"].resolved(boundary=workspace["boundary"], actor=org.VIEWER_A,
                                    context=workspace["context"], profile_id=first["profile_id"])
    assert old["payload"]["nodes"][1]["label"] == "구매계획"
    assert old["digest"] == first["digest"]
    assert len(workspace["svc"].events(boundary=workspace["boundary"], actor=org.VIEWER_A, context=workspace["context"])) == 2
    assert approval(workspace, draft) == second


def test_approved_and_archived_payloads_are_database_immutable(workspace):
    first = approval(workspace, proposal(workspace))
    second = approval(workspace, proposal(workspace, [{"op": "RENAME", "process_id": "plan", "label": "명칭 변경"}], "rename"))
    for pid in (first["profile_id"], second["profile_id"]):
        with workspace["svc"].repo._connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("UPDATE enterprise_profiles SET payload_json='{}' WHERE profile_id=?", (pid,))
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM enterprise_profiles WHERE profile_id=?", (pid,))


def test_usage_keeps_ids_and_denominator(workspace):
    approval(workspace, proposal(workspace))
    approval(workspace, proposal(workspace, [{"op": "SET_USAGE", "process_id": "plan", "enabled": False}], "disabled"))
    read = workspace["svc"].resolved(boundary=workspace["boundary"], actor=org.MEMBER_A, context=workspace["context"])
    assert len(read["payload"]["nodes"]) == 2
    assert read["payload"]["nodes"][1]["enabled"] is False
    assert read["payload"]["local_overrides"][-1]["command"]["enabled"] is False


def test_shortcut_does_not_duplicate_canonical_node(workspace):
    approval(workspace, proposal(workspace))
    draft = proposal(workspace, [{"op": "ADD_NODE", "node": {"process_id": "sales", "level": "L1", "label": "판매"}},
                                 {"op": "ADD_SHORTCUT", "process_id": "plan", "parent_process_id": "sales"}], "shortcut")
    approval(workspace, draft)
    read = workspace["svc"].resolved(boundary=workspace["boundary"], actor=org.MEMBER_A, context=workspace["context"])
    assert len(read["payload"]["nodes"]) == 3 and len(read["payload"]["placements"]) == 4


@pytest.mark.parametrize("command", [
    {"op": "SPLIT", "process_id": "plan"}, {"op": "MERGE"}, {"op": "SET_BINDING", "app_id": "secret"},
    {"op": "ADD_NODE", "node": {"process_id": "x", "level": "L3", "label": "잘못된 계층"}},
    {"op": "ADD_NODE", "node": {"process_id": "x", "level": "L2", "label": "부모 없음"}},
    {"op": "ADD_NODE", "node": {"process_id": "x", "level": "L1", "label": "", "origin": "STANDARD"}},
])
def test_unsupported_or_invalid_commands_leave_no_partial_rows(workspace, command):
    with pytest.raises(ProcessError) as exc:
        proposal(workspace, [command])
    assert exc.value.status_code == 422
    with workspace["svc"].repo._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM enterprise_process_heads").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM enterprise_profiles").fetchone()[0] == 0


def test_rejection_does_not_change_current_head_and_is_idempotent(workspace):
    first = approval(workspace, proposal(workspace))
    draft = proposal(workspace, [{"op": "RENAME", "process_id": "plan", "label": "반려될 이름"}], "rejected")
    request = dict(change_id=draft["change_id"], actor=org.MANAGER_A, context=workspace["context"],
                   expected_head_version=1, draft_digest=draft["draft_digest"], reason="범위 재검토")
    result = workspace["svc"].reject(**request)
    assert result == workspace["svc"].reject(**request)
    assert result["status"] == "REJECTED"
    assert workspace["svc"].resolved(boundary=workspace["boundary"], actor=org.MEMBER_A, context=workspace["context"])["profile_id"] == first["profile_id"]


def test_general_resolver_refuses_v2_lists(workspace):
    from core.enterprise_context.profile_resolver import ProfileResolver
    approval(workspace, proposal(workspace))
    with pytest.raises(ProcessError, match="v2"):
        ProfileResolver(workspace["svc"].repo).resolve(workspace["boundary"].scope_node_id, "process_profile", overlay={"nodes": []})
    assert workspace["svc"].repo.list_profiles(profile_kind="process_profile") == []


def test_existing_v1_requires_explicit_context_review(workspace):
    from core.enterprise_context.models import EnterpriseProfile
    repo = workspace["svc"].repo
    legacy = repo.upsert_profile(EnterpriseProfile(tenant_id="tenant_default", scope_node_id=org.NODES[org.DEPT_A],
        profile_kind="process_profile", payload={"nodes": [{"key": "old", "label": "기존", "overlay": None}]}))
    with pytest.raises(ProcessError) as exc:
        proposal(workspace)
    assert exc.value.reason_code == "PROCESS_CONTEXT_REVIEW_REQUIRED"
    assert repo.list_profiles()[0].payload == legacy.payload


@pytest.fixture
def client(workspace, monkeypatch):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.enterprise_context_control import router
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


def headers(actor=org.MEMBER_A, scope=None):
    return {"X-Factory-User": actor, "X-Enterprise-Scope": scope or org.NODES[org.DEPT_A]}


def test_api_create_review_approve_projection_and_old_save_block(workspace, client):
    root = workspace["boundary"].context_root_id
    body = {"context_root_id": root, "scope_node_id": org.NODES[org.DEPT_A], "commands": [
        {"op": "ADD_NODE", "node": {"process_id": "purchase", "level": "L1", "label": "原料購買"}},
        {"op": "ADD_NODE", "node": {"process_id": "order", "level": "L2", "parent_process_id": "purchase", "label": "주문"}}],
        "expected_head_version": 0, "base_profile_id": "", "base_fingerprint": "", "client_request_id": "api-1", "reason": "시험"}
    path = "/api/v1/enterprise-context"
    r = client.post(path + "/process-configurations/changes", json=body, headers=headers())
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    review = {"draft_digest": d["draft_digest"], "expected_head_version": 0, "reason": "검토"}
    r = client.post(path + f"/process-changes/{d['change_id']}/approve", json=review, headers=headers(org.MANAGER_A))
    assert r.status_code == 200, r.text
    r = client.get(path + "/profiles", params={"profile_kind": "process_profile", "scope_node_id": org.NODES[org.DEPT_A]}, headers=headers(org.VIEWER_A))
    assert r.status_code == 200, r.text
    projection = r.json()["data"][0]
    assert projection["read_only"] and projection["editor_schema_required"] == 2
    assert len(projection["payload"]["nodes"]) == 1
    r = client.post(path + "/profiles", headers=headers(org.ADMIN), json={
        "profile_id": projection["profile_id"], "profile_kind": "business_profile", "scope_node_id": org.NODES[org.DEPT_A], "payload": {"nodes": []}})
    assert r.status_code == 409 and r.json()["detail"]["reason_code"] == "PROCESS_SCHEMA_UPGRADE_REQUIRED"


def test_api_requires_explicit_scope_and_returns_hidden_404(workspace, client):
    query = {"context_root_id": workspace["boundary"].context_root_id, "scope_node_id": org.NODES[org.DEPT_A]}
    path = "/api/v1/enterprise-context/process-configurations/resolved"
    assert client.get(path, params=query, headers={"X-Factory-User": org.ADMIN}).status_code == 422
    r = client.get(path, params=query, headers=headers(org.MEMBER_B, org.NODES[org.DEPT_B]))
    assert r.status_code == 404 and r.json()["detail"]["reason_code"] == "PROCESS_NOT_FOUND"


def test_api_strict_request_does_not_accept_approval_spoof(workspace, client):
    draft = proposal(workspace)
    r = client.post(f"/api/v1/enterprise-context/process-changes/{draft['change_id']}/approve", headers=headers(org.MANAGER_A),
        json={"draft_digest": draft["draft_digest"], "expected_head_version": 0, "reason": "검토", "approved_by": org.ADMIN})
    assert r.status_code == 422


@pytest.mark.parametrize("root,mode", [("", "REAL"), ("root", "UNKNOWN")])
def test_api_invalid_boundary_is_structured_422_not_server_error(workspace, client, root, mode):
    r = client.get("/api/v1/enterprise-context/process-configurations/resolved",
        params={"context_root_id": workspace["boundary"].context_root_id if root else "", "scope_node_id": org.NODES[org.DEPT_A]},
        headers={**headers(org.ADMIN), "X-Entity-Mode": mode})
    assert r.status_code == 422
    assert r.json()["detail"]["reason_code"] == "PROCESS_CONTEXT_INVALID"


def test_b1_route_table_is_wired():
    from api.routes.enterprise_context_control import router
    from core.route_authority import ROUTE_CAPS
    from core.admin_capability import ALL_CAPABILITIES
    writes = [r for r in router.routes if "POST" in r.methods and
              any(prefix in r.path for prefix in ("/process-configurations/", "/process-changes/"))]
    assert len(writes) == 5
    for route in writes:
        assert ROUTE_CAPS[f"POST {route.path}"]
        assert all(c in ALL_CAPABILITIES for c in ROUTE_CAPS[f"POST {route.path}"])


@pytest.mark.parametrize("target_scope,legacy_scope,industry", [
    ("", "root", ""), ("child", "root", ""), ("child", "", "copper"),
    ("child", "root", "copper"),
])
def test_review_regression_detects_root_ancestor_and_industry_v1(workspace, target_scope, legacy_scope, industry):
    from core.enterprise_context.models import EnterpriseProfile
    root = org.NODES[org.DEPT_ROOT]
    boundary = workspace["boundary"].model_copy(update={"scope_node_id": org.NODES[org.DEPT_A] if target_scope else ""})
    workspace["svc"].repo.upsert_profile(EnterpriseProfile(tenant_id="tenant_default", profile_kind="process_profile",
        scope_node_id=root if legacy_scope else "", industry_code=industry, payload={"nodes": [{"key": "legacy", "label": "보존"}]}))
    with pytest.raises(ProcessError) as exc:
        workspace["svc"].propose(boundary=boundary, actor=org.MANAGER_ROOT,
            context={**workspace["context"], "scope_node_id": root}, commands=[
                {"op": "ADD_NODE", "node": {"process_id": "new", "level": "L1", "label": "새 구성"}}],
            expected_head_version=0, base_profile_id="", base_fingerprint="", client_request_id="review", reason="검토")
    assert exc.value.reason_code == "PROCESS_CONTEXT_REVIEW_REQUIRED"


@pytest.mark.parametrize("fault", ["empty-pointer", "wrong-version"])
def test_review_regression_head_damage_cannot_create_second_active(workspace, fault):
    first = approval(workspace, proposal(workspace))
    draft = proposal(workspace, [{"op": "RENAME", "process_id": "plan", "label": "수정"}], "revise")
    with workspace["svc"].repo._connect() as conn:
        if fault == "empty-pointer":
            conn.execute("UPDATE enterprise_process_heads SET active_profile_id='' WHERE configuration_id=?", (first["configuration_id"],))
        else:
            conn.execute("UPDATE enterprise_process_heads SET head_version=9 WHERE configuration_id=?", (first["configuration_id"],))
    with pytest.raises(ProcessError) as exc:
        approval(workspace, draft)
    assert exc.value.status_code == 503
    with workspace["svc"].repo._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM enterprise_profiles WHERE status='ACTIVE'").fetchone()[0] == 1
        assert conn.execute("SELECT status FROM enterprise_process_changes WHERE change_id=?", (draft["change_id"],)).fetchone()[0] == "DRAFT"


def test_review_regression_legacy_cross_tenant_id_insert_race(workspace, monkeypatch):
    from core.enterprise_context.models import EnterpriseProfile, EnterpriseEntity, OrganizationNode, EcmError
    from core.enterprise_context.repository import EcmRepository
    repo = workspace["svc"].repo
    other = EcmRepository(repo.db_path)
    ent = other.upsert_entity(EnterpriseEntity(entity_id="tenant-b-entity", tenant_id="tenant_b", name_ko="다른 회사", status="ACTIVE"))
    other.upsert_node(OrganizationNode(node_id="tenant-b-root", entity_id=ent.entity_id, tenant_id="tenant_b", node_type="business_division", name_ko="다른 회사 본사", status="ACTIVE"))
    foreign = EnterpriseProfile(profile_id="raced-id", tenant_id="tenant_b", scope_node_id="tenant-b-root", profile_kind="process_profile", payload={"nodes": [{"key": "b", "label": "보호된 업무"}]})
    class InsertBeforeWriteLock:
        def __enter__(self):
            other.upsert_profile(foreign)
        def __exit__(self, *args):
            return False
    monkeypatch.setattr(repo, "_lock", InsertBeforeWriteLock())
    with pytest.raises(EcmError):
        repo.upsert_profile(EnterpriseProfile(profile_id="raced-id", tenant_id="tenant_default", scope_node_id=org.NODES[org.DEPT_A], profile_kind="process_profile", payload={"nodes": []}))
    assert other.list_profiles(tenant_id="tenant_b")[0].payload == foreign.payload


def test_old_api_hides_v2_target_in_another_selected_scope(workspace, client):
    first = approval(workspace, proposal(workspace))
    path = "/api/v1/enterprise-context/profiles"
    for suffix, body in [("", {"profile_id": first["profile_id"], "profile_kind": "process_profile", "scope_node_id": org.NODES[org.DEPT_B], "payload": {}}),
                         (f"/{first['profile_id']}/approve", {})]:
        r = client.post(path + suffix, headers=headers(org.ADMIN, org.NODES[org.DEPT_B]), json=body)
        assert r.status_code == 404 and r.json()["detail"]["reason_code"] == "PROCESS_NOT_FOUND"


def test_virtual_clone_v2_requires_supported_reader_before_creating_assets(workspace):
    from core.enterprise_context.clone_service import CloneService
    approval(workspace, proposal(workspace))
    repo = workspace["svc"].repo
    before = [e.model_dump() for e in repo.list_entities()]
    with pytest.raises(ProcessError) as exc:
        CloneService(repository=repo).clone_to_virtual("t_entity", "합성 복제", "테스트", "2099-01-01", actor=org.ADMIN, today="2098-12-01")
    assert exc.value.reason_code == "PROCESS_SCHEMA_UPGRADE_REQUIRED"
    assert [e.model_dump() for e in repo.list_entities()] == before


def test_clone_api_preserves_structured_upgrade_error(workspace, client):
    approval(workspace, proposal(workspace))
    r = client.post("/api/v1/enterprise-context/entities/t_entity/clone", headers=headers(org.ADMIN),
                    json={"name_ko": "합성 복제", "purpose": "테스트", "valid_until": "2099-01-01"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["reason_code"] == "PROCESS_SCHEMA_UPGRADE_REQUIRED"


@pytest.mark.parametrize("action", ["validate", "approve"])
def test_corrupt_current_base_cannot_validate_or_approve_existing_draft(workspace, action):
    import json
    first = approval(workspace, proposal(workspace))
    draft = proposal(workspace, [{"op": "RENAME", "process_id": "plan", "label": "검토 대상"}], "waiting")
    with workspace["svc"].repo._connect() as conn:
        row = conn.execute("SELECT payload_json FROM enterprise_profiles WHERE profile_id=?", (first["profile_id"],)).fetchone()
        payload = json.loads(row[0])
        payload["nodes"][0]["label"] = "고장 주입: 승인 지문 불일치"
        trigger = conn.execute("SELECT sql FROM sqlite_master WHERE name='process_profile_immutable_update'").fetchone()[0]
        conn.execute("DROP TRIGGER process_profile_immutable_update")
        conn.execute("UPDATE enterprise_profiles SET payload_json=? WHERE profile_id=?", (json.dumps(payload), first["profile_id"]))
        conn.execute(trigger)
    with pytest.raises(ProcessError) as exc:
        if action == "approve":
            approval(workspace, draft)
        else:
            workspace["svc"].validate(change_id=draft["change_id"], actor=org.MEMBER_A,
                                      context=workspace["context"], draft_digest=draft["draft_digest"])
    assert exc.value.status_code == 503 and exc.value.reason_code == "PROCESS_PROFILE_UNAVAILABLE"
    with workspace["svc"].repo._connect() as conn:
        assert conn.execute("SELECT status FROM enterprise_process_changes WHERE change_id=?", (draft["change_id"],)).fetchone()[0] == "DRAFT"
        assert conn.execute("SELECT COUNT(*) FROM enterprise_process_outbox").fetchone()[0] == 1


@pytest.mark.parametrize("mode", ["REAL", "VIRTUAL", "COMPETITOR_REFERENCE"])
def test_separate_roots_and_modes_keep_independent_approved_heads(workspace, mode):
    from core.enterprise_context.models import EnterpriseEntity, OrganizationNode
    from core.org_directory import org_directory
    first = approval(workspace, proposal(workspace))
    repo = workspace["svc"].repo
    if mode == "VIRTUAL":
        root = org.NODES[org.VIRTUAL_CODE_B]
    else:
        entity = repo.upsert_entity(EnterpriseEntity(entity_id="separate-company", tenant_id="tenant_default", entity_mode=mode,
            name_ko="분리 문맥 시험", evidence_ref="test:public-evidence" if mode == "COMPETITOR_REFERENCE" else "", status="ACTIVE"))
        root = repo.upsert_node(OrganizationNode(node_id="separate-root", tenant_id="tenant_default", entity_id=entity.entity_id,
            node_type="business_division", name_ko="별도 루트", status="ACTIVE")).node_id
    publisher = "b1_publisher@test.invalid"
    org_directory.upsert_user(publisher, "격리 시험 승인자", primary_dept_id=org.DEPT_ROOT, is_admin=True)
    boundary = ProcessBoundary(tenant_id="tenant_default", context_root_id=root, entity_mode=mode)
    context = {"tenant_id": "tenant_default", "entity_mode": mode, "scope_node_id": root}
    draft = workspace["svc"].propose(boundary=boundary, actor=org.ADMIN, context=context,
        commands=[{"op": "ADD_NODE", "node": {"process_id": "purchase", "level": "L1", "label": "별도 구성"}}],
        expected_head_version=0, base_profile_id="", base_fingerprint="", client_request_id="first", reason="문맥 분리 시험")
    second = workspace["svc"].approve(change_id=draft["change_id"], actor=publisher, context=context,
        expected_head_version=0, draft_digest=draft["draft_digest"], reason="분리 문맥 검토")
    original = workspace["svc"].resolved(boundary=workspace["boundary"], actor=org.VIEWER_A, context=workspace["context"])
    assert original["profile_id"] == first["profile_id"] and original["head_version"] == 1
    assert second["configuration_id"] != first["configuration_id"]
    assert workspace["svc"].resolved(boundary=boundary, actor=publisher, context=context)["profile_id"] == second["profile_id"]
    with repo._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM enterprise_profiles WHERE status='ACTIVE'").fetchone()[0] == 2
