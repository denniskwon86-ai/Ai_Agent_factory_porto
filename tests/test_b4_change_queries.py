"""B4 고정 검토 조회. 메인 격리 runner 전용이며 DB는 기존 pytest tmp fixture뿐이다."""
import json
import sqlite3

import pytest

from core.enterprise_context.process_configuration import ProcessConfigurationService
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError, canonical, fingerprint
from tests import org_seed as org
from tests.test_b1_process_configuration import approval, proposal, workspace  # noqa: F401
from tests.test_b2_installation import installation, _db, _state, _start, _resume  # noqa: F401
from tests.test_b4_installation_queries import _other_directory
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


def _list(w, actor=org.MANAGER_A, **kwargs):
    return w["svc"].list_changes(boundary=w["boundary"], actor=actor, context=w["context"], **kwargs)


def _detail(w, draft, actor=org.MANAGER_A, **kwargs):
    return w["svc"].get_change(change_id=draft["change_id"], actor=actor,
                               **{"boundary": w["boundary"], "context": w["context"], **kwargs})


@pytest.mark.parametrize("actor,actions", [(org.VIEWER_A, ["read"]), (org.MEMBER_A, ["read"]),
    (org.MANAGER_A, ["read", "approve"]), (org.MANAGER_ROOT, ["read", "approve"])])
def test_readers_discover_other_authors_with_exact_review_actions(installation, actor, actions):
    w = installation
    draft = proposal(w)
    before = _state(w)
    summary = _list(w, actor)["items"][0]
    detail = _detail(w, draft, actor)
    assert {k: summary[k] for k in draft} == draft
    assert summary["boundary"] == w["boundary"].model_dump()
    assert summary["principal_user_id"] == actor and summary["actor"] == org.MEMBER_A
    assert summary["permitted_actions"] == actions
    assert summary["operation_id"] is None and summary["current_head_version"] == 0
    assert "payload" not in summary and "base_payload" not in summary
    assert detail == {**summary, "payload": detail["payload"], "base_payload": None}
    assert fingerprint(detail["payload"]) == draft["draft_digest"]
    assert _state(w) == before


def test_qualified_author_is_not_their_own_reviewer(installation):
    w = installation
    draft = proposal(w, actor=org.MANAGER_A)
    result = _detail(w, draft)
    assert result["review_blockers"] == ["PROCESS_DISTINCT_REVIEWER_REQUIRED"]
    assert result["permitted_actions"] == ["read"]
    assert _detail(w, draft, org.MANAGER_ROOT)["permitted_actions"] == ["read", "approve"]


def test_fixed_base_diff_survives_later_head_and_approval_is_stale(installation):
    w = installation
    first = approval(w, proposal(w))
    draft = proposal(w, [{"op": "RENAME", "process_id": "plan", "label": "제안 명칭"}], "candidate")
    original = _detail(w, draft)
    later = approval(w, proposal(w, [{"op": "RENAME", "process_id": "plan", "label": "새 승인 명칭"}], "winner"))
    before = _state(w)
    current = _detail(w, draft)
    assert current["base_payload"] == original["base_payload"]
    assert current["payload"] == original["payload"]
    assert fingerprint(current["base_payload"]) == first["digest"]
    assert current["payload"]["base_profile_id"] == first["profile_id"]
    assert current["current_head_version"] == later["head_version"] == 2
    assert current["review_blockers"] == ["PROCESS_HEAD_CONFLICT"]
    assert current["permitted_actions"] == ["read"]
    with pytest.raises(ProcessError) as raised:
        approval(w, draft)
    assert raised.value.reason_code == "PROCESS_HEAD_CONFLICT"
    assert _state(w) == before


def test_status_filter_and_stable_boundary_pagination(installation):
    w = installation
    drafts = [proposal(w, key=f"page-{i}") for i in range(4)]
    with _db(w) as conn:
        conn.execute("UPDATE enterprise_process_changes SET created_at='same-time'")
    ordered = sorted((d["change_id"] for d in drafts), reverse=True)
    one, two = _list(w, limit=2), _list(w, limit=2, offset=2)
    assert [r["change_id"] for r in one["items"] + two["items"]] == ordered
    assert one["next_offset"] == 2 and two["next_offset"] is None
    assert _list(w, offset=99) == {"items": [], "next_offset": None}
    approval(w, drafts[0])
    assert [r["change_id"] for r in _list(w, status="APPLIED")["items"]] == [drafts[0]["change_id"]]
    assert len(_list(w)["items"]) == 3
    assert _detail(w, drafts[0])["review_blockers"] == ["PROCESS_CHANGE_NOT_DRAFT"]


@pytest.mark.parametrize("page", [{"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": 1.5},
    {"offset": -1}, {"offset": True}, {"offset": 2**63}, {"status": "ALL"}, {"status": []}])
def test_list_rejects_unsafe_or_ambiguous_page_inputs(installation, page):
    with pytest.raises(ProcessError) as raised:
        _list(installation, **page)
    assert raised.value.status_code == 422


@pytest.mark.parametrize("dimension", ["scope", "company", "root", "mode", "tenant"])
def test_admin_never_merges_or_reads_another_exact_boundary(installation, dimension):
    from core.enterprise_context.models import EnterpriseEntity, OrganizationNode
    w = installation
    own = proposal(w)
    values = w["boundary"].model_dump()
    if dimension == "scope":
        values["scope_node_id"] = org.NODES[org.DEPT_B]
    elif dimension == "company":
        values["scope_node_id"] = ""
    else:
        tenant = "b4-review-tenant" if dimension == "tenant" else values["tenant_id"]
        mode = "VIRTUAL" if dimension == "mode" else "REAL"
        base = w["svc"].repo.get_node(w["boundary"].scope_node_id).entity_id if dimension == "mode" else ""
        entity = w["svc"].repo.upsert_entity(EnterpriseEntity(entity_id="review-other-entity", tenant_id=tenant,
            entity_mode=mode, base_entity_id=base, name_ko="다른 합성 문맥", status="ACTIVE"))
        node = w["svc"].repo.upsert_node(OrganizationNode(node_id="review-other-root", entity_id=entity.entity_id,
            tenant_id=tenant, code="review-other-root", name_ko="다른 합성 루트", status="ACTIVE"))
        values.update(tenant_id=tenant, entity_mode=mode, context_root_id=node.node_id, scope_node_id=node.node_id)
    other = ProcessBoundary(**values)
    context = {"tenant_id": other.tenant_id, "entity_mode": other.entity_mode,
               "scope_node_id": other.scope_node_id or other.context_root_id}
    foreign = proposal({**w, "boundary": other, "context": context}, actor=org.ADMIN)
    result = _list(w, org.ADMIN, limit=1)
    assert [r["change_id"] for r in result["items"]] == [own["change_id"]]
    assert result["next_offset"] is None and foreign["draft_digest"] not in canonical(result)
    with pytest.raises(ProcessError) as raised:
        _detail(w, foreign, org.ADMIN)
    assert raised.value.status_code == 404 and foreign["change_id"] not in str(raised.value)


@pytest.mark.parametrize("damage", ["payload", "digest", "base", "version", "patch"])
def test_corrupt_change_is_503_not_partial_review_or_approve_action(installation, damage):
    w = installation
    draft = proposal(w)
    with _db(w) as conn:
        if damage == "payload":
            conn.execute("UPDATE enterprise_profiles SET payload_json='{}' WHERE profile_id=?", (draft["draft_profile_id"],))
        elif damage == "digest":
            conn.execute("UPDATE enterprise_process_changes SET draft_digest=?", ("0" * 64,))
        elif damage == "base":
            raw = conn.execute("SELECT payload_json FROM enterprise_profiles WHERE profile_id=?", (draft["draft_profile_id"],)).fetchone()[0]
            payload = json.loads(raw)
            payload["base_profile_id"] = "foreign-secret-profile"
            conn.execute("UPDATE enterprise_profiles SET payload_json=? WHERE profile_id=?", (canonical(payload), draft["draft_profile_id"]))
            conn.execute("UPDATE enterprise_process_changes SET draft_digest=?", (fingerprint(payload),))
        elif damage == "version":
            conn.execute("UPDATE enterprise_profiles SET version=99 WHERE profile_id=?", (draft["draft_profile_id"],))
        else:
            conn.execute("UPDATE enterprise_process_changes SET patch_json='{' ")
    before = _state(w)
    for call in (lambda: _list(w), lambda: _detail(w, draft)):
        with pytest.raises(ProcessError) as raised:
            call()
        assert raised.value.status_code == 503 and "foreign-secret" not in str(raised.value)
    assert _state(w) == before


def test_installation_reference_and_retirement_are_reviewed_without_get_writes(installation):
    w = installation
    ready = _resume(w, _start(w))
    detail = _detail(w, ready["change"])
    assert detail["operation_id"] == ready["operation_id"]
    assert detail["permitted_actions"] == ["read", "approve"]
    with _db(w, "dp") as conn:
        conn.execute("UPDATE kit_instances SET status='inactive' WHERE instance_id=?", (ready["kit_instance_ref"],))
    before = _state(w)
    detail = _detail(w, ready["change"])
    assert detail["review_blockers"] == ["PROCESS_INSTANCE_CONFLICT"]
    assert detail["permitted_actions"] == ["read"]
    with pytest.raises(ProcessError) as raised:
        approval(w, ready["change"])
    assert raised.value.reason_code == "PROCESS_INSTANCE_CONFLICT"
    assert _state(w) == before


@pytest.mark.parametrize("query", ["list", "detail"])
def test_read_is_rechecked_after_loading_documents(installation, monkeypatch, query):
    w = installation
    draft = proposal(w)
    w["directory"].set_user_roles(org.MEMBER_B, {org.DEPT_A: "viewer", org.DEPT_B: "member"}, actor=org.ADMIN)
    assert w["directory"].resolve_scope(org.MEMBER_B).can_read(org.DEPT_A)
    original = ProcessConfigurationService._review_documents
    calls = []
    def revoke(self, *args):
        result = original(self, *args)
        _other_directory(w).set_user_roles(org.MEMBER_B, {org.DEPT_B: "member"}, actor=org.ADMIN)
        calls.append(True)
        return result
    monkeypatch.setattr(ProcessConfigurationService, "_review_documents", revoke)
    with pytest.raises(ProcessError) as raised:
        _list(w, org.MEMBER_B) if query == "list" else _detail(w, draft, org.MEMBER_B)
    assert calls and raised.value.status_code == 404


def test_publish_revoke_during_load_is_not_masked_by_role_in_another_scope(installation, monkeypatch):
    w = installation
    draft = proposal(w)
    original = ProcessConfigurationService._review_documents
    def revoke(self, *args):
        result = original(self, *args)
        _other_directory(w).set_user_roles(org.MANAGER_A, {org.DEPT_A: "viewer", org.DEPT_B: "manager"}, actor=org.ADMIN)
        return result
    monkeypatch.setattr(ProcessConfigurationService, "_review_documents", revoke)
    result = _detail(w, draft)
    assert result["permitted_actions"] == ["read"]
    assert result["review_blockers"] == ["PROCESS_ACTION_FORBIDDEN"]


def test_authority_failure_is_not_empty_actions_or_an_empty_list(installation, monkeypatch):
    from core.org_directory import OrgDirectory
    w = installation
    draft = proposal(w)
    original = OrgDirectory.resolve_scope
    def broken(self, user_id="", *, fresh=False):
        if fresh:
            raise sqlite3.OperationalError("합성 권한 장애")
        return original(self, user_id)
    monkeypatch.setattr(OrgDirectory, "resolve_scope", broken)
    for call in (lambda: _list(w), lambda: _detail(w, draft)):
        with pytest.raises(ProcessError) as raised:
            call()
        assert raised.value.status_code == 503 and raised.value.reason_code == "PROCESS_AUTHORITY_UNAVAILABLE"


def test_approval_rechecks_publish_after_reference_validation_before_writes(installation, monkeypatch):
    from core.enterprise_context import process_installation as module
    w = installation
    draft = proposal(w)
    before = _state(w)
    original = module.validate_installation_references
    calls = []
    def revoke(*args, **kwargs):
        original(*args, **kwargs)
        _other_directory(w).set_user_roles(org.MANAGER_A, {org.DEPT_A: "viewer", org.DEPT_B: "manager"}, actor=org.ADMIN)
        calls.append(True)
    monkeypatch.setattr(module, "validate_installation_references", revoke)
    with pytest.raises(ProcessError) as raised:
        approval(w, draft)
    assert calls and raised.value.reason_code == "PROCESS_ACTION_FORBIDDEN"
    after = _state(w)
    assert after["ecm"] == before["ecm"] and after["dp"] == before["dp"]
