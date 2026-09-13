"""독립 재검토 P1/P2의 실제 조직 회귀."""
import copy

import pytest

from core.data_preparation import certification_subject as cs, certification_authority as ca, ownership_binding as ob
from core.org_directory import org_directory
from tests import org_seed as org
from tests.test_b0_certification_subject import company, policy, request, sign


@pytest.mark.parametrize("operation", ["get", "preview", "retry"])
def test_node_department_is_not_read_ownership_fallback(company, operation):
    with company["store"].transaction() as conn:
        ob.revoke(conn, company["owner"]["binding_id"], org.ADMIN, "test-only-transfer")
    owner_args = {**company["owner_args"], "owner_dept_id": org.DEPT_B}
    approved = ob.approve(**owner_args, actor_id=org.ADMIN)
    with company["store"].transaction() as conn:
        ob.declare(conn, **owner_args, approved_by=org.ADMIN, approval_event_id=approved["approval_event_id"], effective_from=approved["effective_from"])
    doc = copy.deepcopy(company["document"])
    doc["grants"]["DATA_OWNER"][0]["dept_id"] = org.DEPT_B
    policy(company, doc)
    org_directory.set_user_roles(org.MANAGER_A, {org.DEPT_A: "manager", org.DEPT_B: "manager"}, actor="test")
    req = request(company, use="OPERATIONAL")
    sign(company, req)
    org_directory.set_user_roles(org.MANAGER_A, {org.DEPT_A: "manager"}, actor="test")
    with pytest.raises(ca.CertificationError) as exc:
        if operation == "get":
            cs.read(company["store"], company["sid"], actor=org.MANAGER_A, context=company["context"])
        elif operation == "preview":
            request(company, use="OPERATIONAL")
        else:
            sign(company, req)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("operation", ["get", "preview", "retry"])
def test_moved_root_hides_historical_subject_even_from_admin(company, operation):
    from core.enterprise_context.repository import ecm_repository as repo
    from core.enterprise_context.models import OrganizationNode, OrganizationEdge, STATUS_ACTIVE, REL_OPERATING_PARENT
    doc = copy.deepcopy(company["document"])
    doc["grants"]["DATA_OWNER"].append({"dept_id": org.DEPT_A, "role": "viewer", "scope_node_id": company["context"]["scope_node_id"]})
    org_directory.set_user_roles(org.ADMIN, {org.DEPT_ROOT: "manager", org.DEPT_A: "viewer"}, actor="test")
    policy(company, doc)
    req = request(company, org.ADMIN, use="OPERATIONAL")
    sign(company, req)
    repo.upsert_node(OrganizationNode(node_id="new-root", tenant_id="tenant_default", entity_id="t_entity", node_type="business_division", code="new-root", name_ko="합성 새 루트", status=STATUS_ACTIVE))
    for edge in repo.list_edges(relation_type=REL_OPERATING_PARENT):
        if edge.to_node_id == company["context"]["scope_node_id"]:
            edge.status = "RETIRED"
            repo.add_edge(edge)
    repo.add_edge(OrganizationEdge(edge_id="new-parent", tenant_id="tenant_default", from_node_id="new-root", to_node_id=company["context"]["scope_node_id"], relation_type=REL_OPERATING_PARENT, status=STATUS_ACTIVE))
    context = {**company["context"], "scope_node_id": "new-root"}
    with pytest.raises((ca.CertificationError,)) as exc:
        if operation == "get":
            cs.read(company["store"], company["sid"], actor=org.ADMIN, context=context)
        elif operation == "preview":
            # 완료판도 읽기 경계가 우선이다. 현재 대상과 과거 대상의 루트가 다르면404.
            cs.preview(company["store"], company["sid"], actor=org.ADMIN, context=context,
                       use_kind="OPERATIONAL", period_from="2026-08-01", period_to="2026-08-31")
        else:
            sign(company, {**req, "context": context})
    assert exc.value.status_code == 404


def test_read_exposes_stale_and_restart_persists_normalized_use(company):
    old_policy = policy(company)
    first = sign(company, request(company))
    doc = copy.deepcopy(company["document"])
    doc["min_evidence_length"] = 11
    policy(company, doc, old_policy["policy_id"])
    result = cs.read(company["store"], company["sid"], actor=org.MANAGER_A, context=company["context"])
    assert result["review_status"] == "REVIEW_STALE" and result["requires_new_revision"]
    assert result["missing"] == [] and not result["signatures_count_toward_completion"]
    args = dict(actor=org.MANAGER_A, context=company["context"], use_kind=" management ", period_from="2026-08-01", period_to="2026-08-31")
    preview = cs.preview(company["store"], company["sid"], **args, new_revision=True)
    subject = cs.restart(company["store"], company["sid"], **args, expected_subject_digest=preview["digest"], previous_subject_id=first["subject_id"])
    assert company["store"].get_snapshot(company["sid"])["certified_use_kind"] == subject["payload"]["use_kind"] == "MANAGEMENT"
