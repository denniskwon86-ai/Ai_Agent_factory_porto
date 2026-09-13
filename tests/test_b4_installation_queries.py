"""B4 첫 설치·탐색의 실제 parent FastAPI 계약. 실행은 메인 격리 runner 전용.

조직은 .invalid seed, DB는 pytest tmp만 사용한다. 운영자료·LLM 호출 없음.
GET의 무부작용은 임시 DB의 논리 행으로 비교하며 HTTP 성공을 UI 수용으로 주장하지 않는다.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from core.enterprise_context.process_configuration import ProcessConfigurationService
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError, canonical, fingerprint
from tests import org_seed as org
from tests.test_b1_process_configuration import client, headers, workspace  # noqa: F401
from tests.test_b2_installation import installation, _db, _state  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401

ROOT = "/api/v1/enterprise-context"


def _query(w):
    return {k: getattr(w["boundary"], k) for k in ("context_root_id", "scope_node_id")}


def _ok(response):
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    return response.json()["data"]


def _error(response, status, reason):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["reason_code"] == reason
    assert "data" not in response.json()


def _start(w, key="query-first", *, boundary=None, actor=org.MEMBER_A, context=None):
    boundary, context = boundary or w["boundary"], context or w["context"]
    current = w["svc"].resolved(boundary=boundary, actor=actor, context=context)
    args = dict(boundary=boundary, actor=actor, context=context,
                artifact_digest=w["bundle"]["artifact_digest"], business_kit_ids=["BK-01"],
                expected_head_version=current["head_version"], base_profile_id=current["profile_id"],
                base_fingerprint=current["digest"], reason="B4 합성 설치 검토")
    plan = w["install"].plan(**args)
    return w["install"].start(**args, plan_digest=plan["plan_digest"], client_request_id=key)


def _other_directory(w):
    from core.org_directory import OrgDirectory
    path = Path(w["directory"].db_path).resolve()
    assert path.is_relative_to(w["root"])
    return OrgDirectory(str(path))


@pytest.mark.parametrize("actor,expected", [
    (org.VIEWER_A, ["read"]), (org.MEMBER_A, ["read", "propose"]),
    (org.MANAGER_A, ["read", "propose", "edit", "approve"]),
    (org.MANAGER_ROOT, ["read", "propose", "edit", "approve"]),
])
def test_context_projects_exact_scope_actions(client, workspace, actor, expected):
    result = _ok(client.get(ROOT + "/process-configurations/context", headers=headers(actor)))
    assert result["boundary"] == workspace["boundary"].model_dump()
    assert result["permitted_actions"] == expected
    assert result["selected_scope_node_id"] == org.NODES[org.DEPT_A]
    assert result["company_wide"] is False
    assert result["target_label"] == "시험 알파사업부" and result["context_root_label"] == "시험 본사"


@pytest.mark.parametrize("company_wide", [False, True])
def test_root_selected_and_company_wide_are_distinct_explicit_boundaries(client, workspace, company_wide):
    root = org.NODES[org.DEPT_ROOT]
    result = _ok(client.get(ROOT + "/process-configurations/context", params={"company_wide": company_wide},
                            headers=headers(org.MANAGER_ROOT, root)))
    assert result["boundary"]["context_root_id"] == root
    assert result["boundary"]["scope_node_id"] == ("" if company_wide else root)
    assert result["selected_scope_node_id"] == root
    assert result["company_wide"] is company_wide
    assert result["target_label"] == result["context_root_label"] == "시험 본사"


def test_company_wide_does_not_promote_a_department_context_even_for_admin(client):
    response = client.get(ROOT + "/process-configurations/context", params={"company_wide": True}, headers=headers(org.ADMIN))
    _error(response, 404, "PROCESS_NOT_FOUND")


def test_context_accepts_canonicalized_explicit_alias_not_client_root(client, workspace):
    result = _ok(client.get(ROOT + "/process-configurations/context",
        params={"context_root_id": "forged-root"}, headers=headers(org.MEMBER_A, org.DEPT_A)))
    assert result["boundary"] == workspace["boundary"].model_dump()


@pytest.mark.parametrize("path", ["/process-configurations/context", "/process-installations"])
def test_queries_require_login_and_explicit_scope(client, workspace, monkeypatch, path):
    import config
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "")
    query = _query(workspace) if path == "/process-installations" else {}
    response = client.get(ROOT + path, params=query, headers={"X-Enterprise-Scope": org.NODES[org.DEPT_A]})
    assert response.status_code == 401
    _error(client.get(ROOT + path, params=query, headers={"X-Factory-User": org.ADMIN}),
           422, "PROCESS_CONTEXT_REQUIRED")


def test_default_parent_display_does_not_choose_root(client, installation):
    with _db(installation) as conn:
        conn.execute("UPDATE organization_nodes SET default_parent_id=? WHERE node_id=?",
                     (org.NODES[org.DEPT_B], org.NODES[org.DEPT_A]))
    result = _ok(client.get(ROOT + "/process-configurations/context", headers=headers()))
    assert result["boundary"]["context_root_id"] == org.NODES[org.DEPT_ROOT]


@pytest.mark.parametrize("case", ["future", "expired", "shared", "multiple", "cycle"])
def test_boundary_uses_active_effective_operating_chain(client, installation, case):
    from core.enterprise_context.models import OrganizationEdge
    kwargs = {"from_node_id": org.NODES[org.DEPT_B], "to_node_id": org.NODES[org.DEPT_A]}
    if case == "future":
        kwargs["effective_from"] = "2999-01-01"
    elif case == "expired":
        kwargs["effective_to"] = "2000-01-01"
    elif case == "shared":
        kwargs["relation_type"] = "SHARED_SERVICE"
    elif case == "cycle":
        kwargs.update(from_node_id=org.NODES[org.DEPT_A], to_node_id=org.NODES[org.DEPT_ROOT])
    # 부정 그래프는 tmp ECM에만 구성한다. 저장소의 그래프 생성 guard를 시험하는 사례가 아니다.
    edge = OrganizationEdge(edge_id="query-edge", **kwargs).model_dump()
    with _db(installation) as conn:
        conn.execute("INSERT INTO organization_edges(edge_id,tenant_id,from_node_id,to_node_id,relation_type,weight,effective_from,effective_to,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     tuple(edge[k] for k in ("edge_id", "tenant_id", "from_node_id", "to_node_id", "relation_type", "weight", "effective_from", "effective_to", "status")) + ("",))
    response = client.get(ROOT + "/process-configurations/context", headers=headers())
    if case in ("multiple", "cycle"):
        _error(response, 503, "PROCESS_CONTEXT_UNAVAILABLE")
    else:
        assert _ok(response)["boundary"]["context_root_id"] == org.NODES[org.DEPT_ROOT]


def test_role_union_does_not_grant_actions_after_other_connection_revoke(client, installation):
    w = installation
    directory = w["directory"]
    directory.set_user_roles(org.MANAGER_A, {org.DEPT_A: "manager", org.DEPT_B: "manager"}, actor=org.ADMIN)
    cached = directory.resolve_scope(org.MANAGER_A)
    assert org.DEPT_A in cached.manageable_dept_ids
    _other_directory(w).set_user_roles(org.MANAGER_A, {org.DEPT_A: "viewer", org.DEPT_B: "manager"}, actor=org.ADMIN)
    assert directory.resolve_scope(org.MANAGER_A) is cached
    result = _ok(client.get(ROOT + "/process-configurations/context", headers=headers(org.MANAGER_A)))
    assert result["permitted_actions"] == ["read"]


@pytest.mark.parametrize("path", ["/process-configurations/context", "/process-installations"])
def test_fresh_read_revocation_hides_queries_despite_cached_scope(client, installation, path):
    w = installation
    _start(w)
    w["directory"].set_user_roles(org.MEMBER_B, {org.DEPT_A: "viewer", org.DEPT_B: "member"}, actor=org.ADMIN)
    cached = w["directory"].resolve_scope(org.MEMBER_B)
    assert cached.can_read(org.DEPT_A)
    _other_directory(w).set_user_roles(org.MEMBER_B, {org.DEPT_B: "member"}, actor=org.ADMIN)
    assert w["directory"].resolve_scope(org.MEMBER_B) is cached
    response = client.get(ROOT + path, params=_query(w), headers=headers(org.MEMBER_B))
    _error(response, 404, "PROCESS_NOT_FOUND")


@pytest.mark.parametrize("path", ["/process-configurations/context", "/process-installations"])
def test_authority_query_failure_is_503_not_empty_permissions_or_list(client, installation, monkeypatch, path):
    from core.org_directory import OrgDirectory
    original = OrgDirectory.resolve_scope
    def broken(self, user_id="", *, fresh=False):
        if fresh:
            raise sqlite3.OperationalError("합성 fresh 권한 조회 장애")
        return original(self, user_id)
    # 인스턴스에 bound method를 복원하면 다음 시험의 copy.copy(fresh)가 원래 캐시로 되돌아간다.
    # 클래스 descriptor를 주입·복원하여 복사본의 self 결속과 시험 간 격리를 유지한다.
    monkeypatch.setattr(OrgDirectory, "resolve_scope", broken)
    _error(client.get(ROOT + path, params=_query(installation), headers=headers()),
           503, "PROCESS_AUTHORITY_UNAVAILABLE")


def test_probe_failure_after_read_is_not_partial_success(client, workspace, monkeypatch):
    original = ProcessConfigurationService._authorize
    def broken(self, conn, boundary, actor, context, action="read"):
        if action == "edit":
            raise ProcessError("PROCESS_AUTHORITY_UNAVAILABLE", "합성 중간 권한 조회 장애", 503)
        return original(self, conn, boundary, actor, context, action)
    monkeypatch.setattr(ProcessConfigurationService, "_authorize", broken)
    _error(client.get(ROOT + "/process-configurations/context", headers=headers()),
           503, "PROCESS_AUTHORITY_UNAVAILABLE")


def test_legacy_preview_keeps_null_absent_and_exact_confirmation_boundary(client, installation):
    from core.enterprise_context.models import EnterpriseProfile
    w = installation
    payload = {"nodes": [{"key": "old-a", "label": "합성 업무 A", "note": None},
                         {"key": "old-b", "label": "합성 업무 B"}], "extra": None}
    legacy = w["svc"].repo.upsert_profile(EnterpriseProfile(tenant_id=w["boundary"].tenant_id,
        scope_node_id=w["boundary"].scope_node_id, profile_kind="process_profile", payload=payload))
    before = _state(w)
    result = _ok(client.get(ROOT + "/process-installations/legacy-preview", params=_query(w), headers=headers()))
    assert result["context"] == w["boundary"].model_dump()
    assert result["sources"][0]["profile_id"] == legacy.profile_id
    assert result["sources"][0]["payload"] == payload
    assert result["sources"][0]["payload"]["nodes"][0]["note"] is None
    assert "note" not in result["sources"][0]["payload"]["nodes"][1]
    assert result["sources"][0]["review_required"] == "EXPLICIT_CONTEXT_AND_KEY_MAPPING"
    assert len(result["sources"][0]["source_digest"]) == 64
    resolved = _ok(client.get(ROOT + "/process-configurations/resolved", params=_query(w), headers=headers()))
    assert resolved["legacy_review_required"] and resolved["legacy_token"] == result["legacy_token"]
    assert _state(w) == before


@pytest.mark.parametrize("path", ["/process-configurations/context", "/process-installations"])
def test_retired_actor_cannot_query_with_a_warmed_cache(client, installation, path):
    w = installation
    w["directory"].resolve_scope(org.MEMBER_A)
    _other_directory(w).delete_user(org.MEMBER_A, actor=org.ADMIN)
    _error(client.get(ROOT + path, params=_query(w), headers=headers()), 403, "PROCESS_ACTOR_INELIGIBLE")


def test_empty_queries_and_candidate_discovery_create_no_head_operation_or_instance(client, installation):
    before = _state(installation)
    context = _ok(client.get(ROOT + "/process-configurations/context", headers=headers()))
    assert context["permitted_actions"] == ["read", "propose"]
    query = _query(installation)
    assert _ok(client.get(ROOT + "/process-installations", params=query, headers=headers())) == {"items": [], "next_offset": None}
    resolved = _ok(client.get(ROOT + "/process-configurations/resolved", params=query, headers=headers()))
    assert (resolved["head_version"], resolved["profile_id"], resolved["digest"], resolved["payload"]) == (0, "", "", None)
    legacy = _ok(client.get(ROOT + "/process-installations/legacy-preview", params=query, headers=headers()))
    assert legacy["sources"] == [] and legacy["legacy_token"] == resolved["legacy_token"]
    candidate = _ok(client.get(ROOT + "/process-packs", params=query, headers=headers(org.VIEWER_A)))[0]
    assert candidate["data_class"] == "NO_DATA" and candidate["setup_only"] is True
    assert candidate["state"] == "DOMAIN_REVIEW_REQUIRED" and "BK-01" in candidate["business_kit_ids"]
    roots = sorted((t for t in installation["bundle"]["pack"]["templates"] if t["level"] == "L1"), key=lambda t: t["business_kit_id"])
    assert candidate["business_kits"] == [{"business_kit_id": t["business_kit_id"], "label": t["label"]} for t in roots]
    assert [item["business_kit_id"] for item in candidate["business_kits"]] == candidate["business_kit_ids"]
    assert _state(installation) == before


def test_business_kit_label_projection_uses_metadata_not_bk_code_mapping(workspace):
    from api.routes.process_installation_control import _business_kits
    # 표시 투영만의 단위 사례다. 원본 artifact 검증 시험을 대체하지 않는다.
    bundle = {"pack": {"templates": [{"business_kit_id": "BK-01", "level": "L1", "label": "다른 표준 명칭"}]}}
    assert _business_kits(bundle) == [{"business_kit_id": "BK-01", "label": "다른 표준 명칭"}]
    bundle["pack"]["templates"].append({"business_kit_id": "BK-01", "level": "L1", "label": "모호한 두 번째 이름"})
    with pytest.raises(ProcessError) as exc:
        _business_kits(bundle)
    assert exc.value.status_code == 503


def test_actual_http_register_plan_start_and_reconnect_without_resume(client, installation):
    w = installation
    query = _query(w)
    digest = _ok(client.post(ROOT + "/process-packs/register", headers=headers(org.MANAGER_A),
        json={**query, "kit_id": w["bundle"]["kit_id"], "version": w["bundle"]["version"]}))["artifact_digest"]
    body = {**query, "artifact_digest": digest, "business_kit_ids": ["BK-01"], "expected_head_version": 0,
            "base_profile_id": "", "base_fingerprint": "", "reason": "B4 원래 입력 보존"}
    before = _state(w)
    plan = _ok(client.post(ROOT + "/process-installations/plan", json=body, headers=headers()))
    assert _state(w) == before
    request = {**body, "plan_digest": plan["plan_digest"], "client_request_id": "http-b4-first"}
    operation = _ok(client.post(ROOT + "/process-installations", json=request, headers=headers()))
    assert operation["stage"] == "AWAITING_INSTALLER" and operation["revision"] == 0
    after_start = _state(w)
    page = _ok(client.get(ROOT + "/process-installations", params=query, headers=headers(org.VIEWER_A)))
    assert page == {"items": [operation], "next_offset": None}
    assert _ok(client.get(ROOT + "/process-installations/" + operation["operation_id"], headers=headers())) == operation
    assert _state(w) == after_start
    # 재접수도 새 작업을 만들지 않는다. GET만으로 준비·승인 상태로 넘어가지 않는다.
    assert _ok(client.post(ROOT + "/process-installations", json=request, headers=headers())) == operation


def test_list_has_bounded_pages_stable_tiebreak_and_same_get_dto(client, installation):
    w = installation
    operations = [_start(w, "page-" + str(i)) for i in range(3)]
    with _db(w) as conn:
        conn.execute("UPDATE enterprise_process_installations SET created_at='2026-09-13T00:00:00Z'")
    expected = sorted(operations, key=lambda item: item["operation_id"], reverse=True)
    before = _state(w)
    first = _ok(client.get(ROOT + "/process-installations", params={**_query(w), "limit": 2}, headers=headers()))
    assert first == {"items": expected[:2], "next_offset": 2}
    second = _ok(client.get(ROOT + "/process-installations", params={**_query(w), "limit": 2, "offset": 2}, headers=headers()))
    assert second == {"items": expected[2:], "next_offset": None}
    for operation in first["items"] + second["items"]:
        assert _ok(client.get(ROOT + "/process-installations/" + operation["operation_id"], headers=headers())) == operation
    assert _ok(client.get(ROOT + "/process-installations", params={**_query(w), "offset": 99}, headers=headers()))["items"] == []
    assert _state(w) == before


@pytest.mark.parametrize("page", [{"limit": 0}, {"limit": 101}, {"limit": "x"}, {"offset": -1}, {"offset": "x"}])
def test_api_rejects_invalid_pagination(client, workspace, page):
    response = client.get(ROOT + "/process-installations", params={**_query(workspace), **page}, headers=headers())
    assert response.status_code == 422


@pytest.mark.parametrize("page", [{"limit": True}, {"offset": True}, {"limit": 1.5}, {"offset": 2**64}])
def test_service_pagination_rejects_coercion_and_sqlite_overflow(installation, page):
    with pytest.raises(ProcessError) as exc:
        installation["install"].list_operations(boundary=installation["boundary"], actor=org.MEMBER_A,
                                                context=installation["context"], **page)
    assert exc.value.status_code == 422 and exc.value.reason_code == "PROCESS_PAGE_INVALID"


@pytest.mark.parametrize("other", ["scope", "root", "mode", "tenant", "company"])
def test_list_never_counts_or_returns_other_boundary_operations(client, installation, other):
    from core.enterprise_context.models import EnterpriseEntity, OrganizationNode
    w = installation
    own = _start(w)
    values = w["boundary"].model_dump()
    if other == "scope":
        values["scope_node_id"] = org.NODES[org.DEPT_B]
    elif other == "company":
        values["scope_node_id"] = ""
    else:
        tenant = "query-tenant" if other == "tenant" else values["tenant_id"]
        mode = "VIRTUAL" if other == "mode" else "REAL"
        base_entity_id = w["svc"].repo.get_node(w["boundary"].scope_node_id).entity_id if other == "mode" else ""
        entity = w["svc"].repo.upsert_entity(EnterpriseEntity(entity_id="query-entity", tenant_id=tenant,
            entity_mode=mode, base_entity_id=base_entity_id, name_ko="다른 합성 문맥", status="ACTIVE"))
        node = w["svc"].repo.upsert_node(OrganizationNode(node_id="query-root", entity_id=entity.entity_id,
            tenant_id=tenant, code="query-root", name_ko="다른 합성 루트", status="ACTIVE"))
        values.update(tenant_id=tenant, entity_mode=mode, context_root_id=node.node_id, scope_node_id=node.node_id)
    boundary = ProcessBoundary(**values)
    context = {"tenant_id": boundary.tenant_id, "entity_mode": boundary.entity_mode,
               "scope_node_id": boundary.scope_node_id or boundary.context_root_id}
    hidden = _start(w, "other-operation", boundary=boundary, context=context, actor=org.ADMIN)
    # 넓은 읽기 권한의 관리자라도 정확한 scope/전사 빈 범위를 합쳐 반환하지 않는다.
    before = _state(w)
    response = client.get(ROOT + "/process-installations", params={**_query(w), "limit": 1}, headers=headers(org.ADMIN))
    # 설치 기록은 같고 표시 행동만 조회자의 현재 권한에 따라 달라진다.
    assert own["permitted_actions"] == []
    expected_for_admin = {**own, "permitted_actions": ["adopt"]}
    assert _ok(response) == {"items": [expected_for_admin], "next_offset": None}
    detail = _ok(client.get(ROOT + "/process-installations/" + own["operation_id"], headers=headers(org.ADMIN)))
    assert detail == expected_for_admin
    assert hidden["operation_id"] not in response.text
    assert _state(w) == before


@pytest.mark.parametrize("wrong", ["scope", "root", "mode", "tenant"])
def test_list_wrong_selected_context_is_hidden_404(client, installation, wrong):
    operation = _start(installation)
    query, selected = _query(installation), headers(org.ADMIN)
    if wrong == "scope":
        selected["X-Enterprise-Scope"] = org.NODES[org.DEPT_B]
    elif wrong == "root":
        query["context_root_id"] = org.NODES[org.DEPT_B]
    elif wrong == "mode":
        selected["X-Entity-Mode"] = "VIRTUAL"
    else:
        selected["X-Enterprise-Tenant"] = "query-other-tenant"
    response = client.get(ROOT + "/process-installations", params=query, headers=selected)
    _error(response, 404, "PROCESS_NOT_FOUND")
    assert operation["operation_id"] not in response.text and operation["plan_digest"] not in response.text


@pytest.mark.parametrize("damage", ["json", "digest", "boundary", "head", "stage", "result", "change"])
def test_corrupt_installation_is_503_without_partial_list_or_foreign_detail(client, installation, damage):
    w = installation
    operation = _start(w)
    with _db(w) as conn:
        # 손상 시험용 trigger 해제는 이 fixture의 임시 ECM만 대상으로 한다.
        conn.execute("DROP TRIGGER process_installation_immutable_update")
        if damage in ("json", "digest", "boundary"):
            row = conn.execute("SELECT plan_json FROM enterprise_process_installations WHERE operation_id=?", (operation["operation_id"],)).fetchone()
            value = json.loads(row[0])
            value["boundary"]["scope_node_id"] = "foreign-secret-scope"
            raw = "{" if damage == "json" else canonical(value)
            digest = fingerprint(value) if damage == "boundary" else operation["plan_digest"]
            conn.execute("UPDATE enterprise_process_installations SET plan_json=?,plan_digest=? WHERE operation_id=?", (raw, digest, operation["operation_id"]))
        elif damage == "head":
            conn.execute("UPDATE enterprise_process_installations SET configuration_id='foreign-secret-config'")
        elif damage == "stage":
            conn.execute("UPDATE enterprise_process_installations SET stage='UNKNOWN'")
        elif damage == "result":
            conn.execute("UPDATE enterprise_process_installations SET result_json='{}'")
        else:
            conn.execute("UPDATE enterprise_process_installations SET stage='AWAITING_APPROVAL',change_id='foreign-secret-change'")
    for path, query in (("/process-installations", _query(w)), ("/process-installations/" + operation["operation_id"], {})):
        response = client.get(ROOT + path, params=query, headers=headers())
        assert response.status_code == 503, response.text
        assert "data" not in response.json() and "foreign-secret" not in response.text


def test_approved_list_keeps_fixed_result_after_later_head_and_is_read_only(client, installation):
    from tests.test_b1_process_configuration import approval, proposal
    w = installation
    operation = _start(w)
    ready = w["install"].resume(operation_id=operation["operation_id"], actor=org.MANAGER_A,
        context=w["context"], expected_revision=operation["revision"], adopt=True)
    approval(w, ready["change"])
    fixed = _ok(client.get(ROOT + "/process-installations/" + operation["operation_id"], headers=headers()))
    current = w["svc"].resolved(boundary=w["boundary"], actor=org.MEMBER_A, context=w["context"])
    pid = current["payload"]["nodes"][0]["process_id"]
    approval(w, proposal(w, [{"op": "RENAME", "process_id": pid, "label": "후속 표시 수정"}], "next-head"))
    before = _state(w)
    page = _ok(client.get(ROOT + "/process-installations", params=_query(w), headers=headers(org.VIEWER_A)))
    assert page == {"items": [fixed], "next_offset": None}
    assert fixed["applied_result"]["head_version"] == 1
    assert not fixed["data_ready"] and not fixed["apps_ready"]
    assert _state(w) == before


def test_list_cross_scope_change_reference_never_returns_foreign_reason(client, installation):
    w = installation
    own = _start(w)
    boundary = w["boundary"].model_copy(update={"scope_node_id": org.NODES[org.DEPT_B]})
    context = {**w["context"], "scope_node_id": boundary.scope_node_id}
    other = _start(w, "other-ready", boundary=boundary, actor=org.ADMIN, context=context)
    ready = w["install"].resume(operation_id=other["operation_id"], actor=org.ADMIN, context=context,
                               expected_revision=other["revision"])
    with _db(w) as conn:
        conn.execute("UPDATE enterprise_process_installations SET stage='AWAITING_APPROVAL',change_id=?,kit_instance_ref=? WHERE operation_id=?",
                     (ready["change_id"], ready["kit_instance_ref"], own["operation_id"]))
    response = client.get(ROOT + "/process-installations", params=_query(w), headers=headers())
    _error(response, 503, "PROCESS_INSTALLATION_UNAVAILABLE")
    assert ready["change_id"] not in response.text and ready["change"]["reason"] not in response.text


def test_list_rechecks_read_after_loading_rows(client, installation, monkeypatch):
    from core.enterprise_context.process_installation import ProcessInstallationService
    w = installation
    _start(w)
    w["directory"].set_user_roles(org.MEMBER_B, {org.DEPT_A: "viewer", org.DEPT_B: "member"}, actor=org.ADMIN)
    cached = w["directory"].resolve_scope(org.MEMBER_B)
    assert cached.can_read(org.DEPT_A)
    revoked = []
    original = ProcessInstallationService._verified_result
    def revoke(self, row, conn, boundary):
        result = original(self, row, conn, boundary)
        _other_directory(w).set_user_roles(org.MEMBER_B, {org.DEPT_B: "member"}, actor=org.ADMIN)
        assert w["directory"].get_user(org.MEMBER_B)["roles"] == {org.DEPT_B: "member"}
        fresh = w["directory"].resolve_scope(org.MEMBER_B, fresh=True)
        assert not fresh.can_read(org.DEPT_A)
        assert org.NODES[org.DEPT_A] not in fresh.readable_scope_nodes
        # 전역 캐시는 여전히 과거 판: 최종 서비스 판정이 fresh를 빠뜨리면 반드시 실패한다.
        assert w["directory"].resolve_scope(org.MEMBER_B) is cached
        assert cached.can_read(org.DEPT_A)
        revoked.append(row["operation_id"])
        return result
    monkeypatch.setattr(ProcessInstallationService, "_verified_result", revoke)
    response = client.get(ROOT + "/process-installations", params=_query(w), headers=headers(org.MEMBER_B))
    assert len(revoked) == 1
    _error(response, 404, "PROCESS_NOT_FOUND")
