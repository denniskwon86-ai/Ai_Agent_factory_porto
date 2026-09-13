"""B5 저장 Kit v2 읽기→타인 검토의 실제 FastAPI 회귀. 메인 격리 runner 전용.

B3 b3_kit_seed의 실제 설치·인증 정책·합성 메타데이터와 기존 HTTP fixture를
재사용한다. principal/PDP/계약/원장은 대역 없이 검증한다. B3 API fixture의
Preview AppData 대역은 유지하며, 이 파일은 실행·RAW·Host 성공을 주장하지 않는다.
운영 DB를 열거나 별도 검사 인프라를 만들지 않는다.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from core import admin_capability as caps, kit_app_contract as kc
from core.enterprise_context.process_schema import canonical
from tests import org_seed as org
from tests.test_b2_installation import _state, _tables
from tests.test_b3_kit_api import (  # noqa: F401 - 기존 function-scoped fixture 재사용
    api_client, create, enforced_org, headers, installation, kit, rejected,
    revision_body, success, url, workspace,
)
from tests.test_b3_kit_contract_v2 import hold
from tests.test_b3_process_context import database, error
from tests.test_b3_reject_api import rejection_body


@pytest.fixture
def review_api(api_client, kit):
    """적격 타인이지만 생성권은 없는 실제 역할 대조군. 권한 판정 대역 없음."""
    kit["directory"].set_user_roles(org.DATA_ADMIN, {org.DEPT_ROOT: "viewer"}, actor="test")
    rights = caps.resolve(kit["directory"].resolve_scope(org.DATA_ADMIN),
                          kit["directory"].get_user(org.DATA_ADMIN))
    assert rights.has(caps.ADMIN_DATA_ACCESS)
    assert not rights.has(caps.PROJECT_RUN)
    assert not rights.bootstrap
    return api_client


def domain_state(w):
    """기존 논리 snapshot에 같은 tmp의 원장만 포함한다. 파일 시각 비교가 아니다."""
    ledger = Path(w["ledger"].db_path).resolve()
    assert ledger.is_relative_to(w["root"]) and ledger.is_file()
    with_ledger = {**w, "paths": {**w["paths"], "ledger": ledger}}
    return {**_state(w), "ledger": _tables(with_ledger, "ledger")}


def list_url(w):
    return f"/api/v1/data-preparation/instances/{w['instance_id']}/apps"


def read_response(client, w, *, actor=org.DATA_ADMIN, revision=None, scope=None):
    return client.get(url(w), headers=headers(actor, scope),
                      params={} if revision is None else {"revision": revision})


def review_response(client, w, row, decision, *, actor=org.DATA_ADMIN, **changes):
    if decision == "APPROVED":
        suffix, body = "contract/v2/approve", revision_body(row, approve=True)
    else:
        assert decision == "REJECTED"
        suffix, body = "contract/reject", rejection_body(row)
    return client.post(url(w, suffix), json={**body, **changes}, headers=headers(actor))


def assert_original(data, row, *, status=None, actor=org.DATA_ADMIN):
    """GET은 계약을 재생성하지 않고 검토한 서버 행의 원문·정체성을 돌려준다."""
    for key in ("instance_id", "app_id", "revision", "semantic_fingerprint", "drafted_by", "approved_by"):
        assert data[key] == row[key], key
    assert data["status"] == (status or row["status"])
    assert data["contract"] == row["contract"]
    assert data["contract"]["schema_version"] == "2.0"
    assert data["principal_user_id"] == actor
    assert data["latest_revision"] >= data["revision"]
    assert set(data["permitted_actions"]) <= {"approve", "reject"}
    assert isinstance(data["review_blockers"], list)
    context = data["contract"]["process_context"]["context_key"]
    assert context["tenant_id"] == row["tenant_id"]
    assert context["entity_mode"] == row["entity_mode"]
    assert (context["scope_node_id"] or context["context_root_id"]) == row["scope_node_id"]


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_eligible_other_reviewer_lists_reads_then_reviews_exact_saved_contract(review_api, kit, decision):
    row = create(review_api, kit)
    before = domain_state(kit)
    listing = success(review_api.get(list_url(kit), headers=headers(org.DATA_ADMIN)))
    assert listing["instance_id"] == kit["instance_id"]
    listed = next(item for item in listing["apps"] if item["app_id"] == "APP-03")
    assert listed["contract_revision"] == row["revision"]
    assert listed["contract_status"] == "DRAFT"
    assert listed["contract_schema_version"] == "2.0"
    assert listed["permitted_actions"] == ["approve", "reject"]
    assert listed["built_datasets"] is None and listed["lifecycle_state"] is None
    viewed = success(read_response(review_api, kit, revision=row["revision"]))
    assert_original(viewed, row)
    assert viewed["permitted_actions"] == ["approve", "reject"]
    assert viewed["latest_revision"] == row["revision"]
    assert viewed["decision_event"] is None
    assert domain_state(kit) == before

    result = success(review_response(review_api, kit, viewed, decision))
    assert result["status"] == decision
    assert result["revision"] == viewed["revision"]
    assert result["semantic_fingerprint"] == viewed["semantic_fingerprint"]
    event = kit["ledger"].get_event_strict(result["ledger_event_id"])
    assert event["actor_id"] == org.DATA_ADMIN != row["drafted_by"]
    assert event["subject_id"] == viewed["semantic_fingerprint"]
    assert event["decision"] == decision
    assert event["event_type"] == (kc.EVENT_APPROVED if decision == "APPROVED" else kc.EVENT_REJECTED)
    if decision == "APPROVED":
        assert result["approved_by"] == org.DATA_ADMIN
    else:
        assert result["contract"] == row["contract"]
        assert not result["approved_by"] and not result["approved_at"]

    # 명시 검토 후 최신 GET으로 저장 반영을 확인한다. POST 응답만 믿지 않는다.
    settled = domain_state(kit)
    confirmed = success(read_response(review_api, kit))
    assert_original(confirmed, result)
    assert confirmed["permitted_actions"] == []
    assert confirmed["decision_event"] == {key: event[key] for key in ("event_id", "decision", "actor_id", "rationale")}
    refreshed = success(review_api.get(list_url(kit), headers=headers(org.DATA_ADMIN)))
    latest = next(item for item in refreshed["apps"] if item["app_id"] == "APP-03")
    assert latest["contract_status"] == decision and latest["contract_revision"] == row["revision"]
    assert latest["permitted_actions"] == []
    assert domain_state(kit) == settled
    assert success(review_response(review_api, kit, viewed, decision)) == result
    assert domain_state(kit) == settled


@pytest.mark.parametrize("actor", [org.MEMBER_A, org.VIEWER_A])
def test_readable_member_and_viewer_do_not_gain_review_or_build_permission(review_api, kit, actor):
    row = create(review_api, kit)
    before = domain_state(kit)
    viewed = success(read_response(review_api, kit, actor=actor, revision=row["revision"]))
    assert_original(viewed, row, actor=actor)
    assert "GENERATE" in viewed["contract"]["process_context"]["permitted_actions"]
    assert viewed["permitted_actions"] == []
    success(review_api.get(list_url(kit), headers=headers(actor)))
    for decision in ("APPROVED", "REJECTED"):
        rejected(review_response(review_api, kit, row, decision, actor=actor), 403)
    # member도 미승인 계약을 만들 수 없고 viewer는 라우트 생성권부터 없다.
    response = review_api.post(url(kit, "build/v2"), json=revision_body(row), headers=headers(actor))
    rejected(response, 409 if actor == org.MEMBER_A else 403,
             "PROCESS_CONTRACT_APPROVAL_REQUIRED" if actor == org.MEMBER_A else None)
    assert domain_state(kit) == before


def test_read_only_reviewer_never_opens_runtime_data_or_publishes(review_api, kit, monkeypatch):
    from core import app_preview, kit_app_builder as kb
    row = create(review_api, kit)

    def forbidden(*_args, **_kwargs):
        pytest.fail("계약 READ가 runtime 자료 열기·게시·물질화를 호출했습니다")
    monkeypatch.setattr(app_preview, "app_data_for", forbidden)
    monkeypatch.setattr(kb, "publish_release", forbidden)
    monkeypatch.setattr(kb.cm, "materialize", forbidden)
    before = domain_state(kit)
    for actor in (org.DATA_ADMIN, org.VIEWER_A):
        assert_original(success(read_response(review_api, kit, actor=actor)), row, actor=actor)
        listing = success(review_api.get(list_url(kit), headers=headers(actor)))
        assert listing["apps"]
        assert all(item["built_datasets"] is None and item["lifecycle_state"] is None
                   for item in listing["apps"])
    assert domain_state(kit) == before


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_author_can_read_but_cannot_self_review_even_as_platform_admin(review_api, kit, decision):
    row = create(review_api, kit, actor=org.ADMIN)
    viewed = success(read_response(review_api, kit, actor=org.ADMIN))
    assert_original(viewed, row, actor=org.ADMIN)
    assert viewed["permitted_actions"] == []
    assert "PROCESS_DISTINCT_REVIEWER_REQUIRED" in {item["reason_code"] for item in viewed["review_blockers"]}
    before = domain_state(kit)
    rejected(review_response(review_api, kit, row, decision, actor=org.ADMIN),
             403, "PROCESS_DISTINCT_REVIEWER_REQUIRED")
    assert domain_state(kit) == before


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
@pytest.mark.parametrize("stale", ["fingerprint", "revision"])
def test_review_rejects_stale_fingerprint_or_historical_revision_without_writes(review_api, kit, decision, stale):
    first = create(review_api, kit)
    viewed = success(read_response(review_api, kit, revision=first["revision"]))
    changes = {}
    if stale == "fingerprint":
        changes["expected_fingerprint" if decision == "APPROVED" else "expected_digest"] = "0" * 64
    else:
        second = create(review_api, kit, app_class="personal", expected_revision=first["revision"])
        assert second["revision"] == first["revision"] + 1
        historical = success(read_response(review_api, kit, revision=first["revision"]))
        assert_original(historical, first)
        assert historical["latest_revision"] == second["revision"]
        assert historical["permitted_actions"] == []
        assert_original(success(read_response(review_api, kit)), second)
    before = domain_state(kit)
    rejected(review_response(review_api, kit, viewed, decision, **changes), 409, "PROCESS_CONTRACT_CONFLICT")
    assert domain_state(kit) == before


@pytest.mark.parametrize("endpoint", ["body", "list"])
def test_anonymous_read_is_401_before_unknown_instance(api_client, endpoint):
    path = url() if endpoint == "body" else list_url({"instance_id": "not-existing"})
    rejected(api_client.get(path), 401)


@pytest.mark.parametrize("revision", [0, -1, "not-an-integer"])
def test_read_revision_query_rejects_invalid_values(review_api, kit, revision):
    create(review_api, kit)
    before = domain_state(kit)
    rejected(read_response(review_api, kit, revision=revision), 422)
    assert domain_state(kit) == before


def test_missing_contract_revision_is_404_not_latest_fallback(review_api, kit):
    # 후보는 존재하지만 아직 검토 원문이 없는 상태를 구분한다.
    rejected(read_response(review_api, kit), 404, "PROCESS_CONTRACT_NOT_FOUND")
    row = create(review_api, kit)
    before = domain_state(kit)
    response = rejected(read_response(review_api, kit, revision=row["revision"] + 10),
                        404, "PROCESS_CONTRACT_NOT_FOUND")
    assert row["semantic_fingerprint"] not in response.text
    assert domain_state(kit) == before


def test_admin_other_selected_scope_hides_body_and_list_without_domain_writes(review_api, kit):
    row = create(review_api, kit)
    before = domain_state(kit)
    responses = (
        read_response(review_api, kit, actor=org.ADMIN, scope=org.NODES[org.DEPT_B]),
        review_api.get(list_url(kit), headers=headers(org.ADMIN, org.NODES[org.DEPT_B])),
    )
    for response in responses:
        rejected(response, 404)
        assert row["contract_row_id"] not in response.text
        assert row["semantic_fingerprint"] not in response.text
        assert kit["fixed"]["profile_id"] not in response.text
    assert domain_state(kit) == before


def test_read_requires_explicit_selected_scope_and_does_not_fallback_to_another_app(review_api, kit):
    row = create(review_api, kit)
    before = domain_state(kit)
    rejected(review_api.get(url(kit), headers={"X-Factory-User": org.ADMIN}),
             422, "PROCESS_CONTEXT_REQUIRED")
    missing_app = url(kit).replace("/APP-03/", "/APP-NOT-PINNED/")
    response = rejected(review_api.get(missing_app, headers=headers(org.DATA_ADMIN)),
                        404, "PROCESS_CONTRACT_NOT_FOUND")
    assert row["semantic_fingerprint"] not in response.text
    assert domain_state(kit) == before


@pytest.mark.parametrize("field,value", [
    ("tenant_id", "foreign.test.invalid"), ("entity_mode", "VIRTUAL"),
    ("context_root_id", "foreign-root"),
])
def test_core_read_v2_hides_foreign_context_even_for_admin(review_api, kit, field, value):
    row = create(review_api, kit)
    before = domain_state(kit)
    exc = error(lambda: kc.read_v2(kit["store"], instance_id=kit["instance_id"], app_id="APP-03",
        actor_id=org.ADMIN, context={**kit["context"], field: value}, revision=row["revision"],
        repo=kit["svc"].repo), 404)
    assert row["contract_row_id"] not in str(exc)
    assert row["semantic_fingerprint"] not in str(exc)
    assert domain_state(kit) == before


def test_scope_read_revocation_is_observed_by_next_get(review_api, kit):
    row = create(review_api, kit)
    assert_original(success(read_response(review_api, kit, actor=org.VIEWER_A)), row, actor=org.VIEWER_A)
    kit["directory"].upsert_user(org.VIEWER_A, "합성 이동 열람자", primary_dept_id=org.DEPT_B, actor="test")
    kit["directory"].set_user_roles(org.VIEWER_A, {org.DEPT_B: "viewer"}, actor="test")
    before = domain_state(kit)
    for response in (read_response(review_api, kit, actor=org.VIEWER_A),
                     review_api.get(list_url(kit), headers=headers(org.VIEWER_A))):
        rejected(response, 404)
        assert row["semantic_fingerprint"] not in response.text
    assert domain_state(kit) == before


def test_review_authority_revocation_preserves_read_but_blocks_both_decisions(review_api, kit):
    row = create(review_api, kit)
    viewed = success(read_response(review_api, kit))
    assert viewed["permitted_actions"] == ["approve", "reject"]
    kit["directory"].upsert_user(org.DATA_ADMIN, "합성 검토권 회수", primary_dept_id=org.DEPT_ROOT,
                                 is_data_admin=False, actor="test")
    rights = caps.resolve(kit["directory"].resolve_scope(org.DATA_ADMIN),
                          kit["directory"].get_user(org.DATA_ADMIN))
    assert not rights.has(caps.ADMIN_DATA_ACCESS)
    before = domain_state(kit)
    revoked = success(read_response(review_api, kit))
    assert_original(revoked, row)
    assert revoked["permitted_actions"] == []
    assert "PROCESS_ACTION_FORBIDDEN" in {item["reason_code"] for item in revoked["review_blockers"]}
    success(review_api.get(list_url(kit), headers=headers(org.DATA_ADMIN)))
    for decision in ("APPROVED", "REJECTED"):
        rejected(review_response(review_api, kit, viewed, decision), 403)
    assert domain_state(kit) == before


@pytest.mark.parametrize("damage", ["json", "schema", "fingerprint", "row_context"])
def test_corrupt_saved_body_is_503_not_empty_draft_or_regenerated_contract(review_api, kit, damage):
    row = create(review_api, kit)
    with database(kit, "dp") as conn:
        if damage == "fingerprint":
            conn.execute("UPDATE kit_app_contracts SET semantic_fingerprint=? WHERE contract_row_id=?",
                         ("0" * 64, row["contract_row_id"]))
        elif damage == "row_context":
            conn.execute("UPDATE kit_app_contracts SET tenant_id=? WHERE contract_row_id=?",
                         ("damaged.test.invalid", row["contract_row_id"]))
        else:
            broken = copy.deepcopy(row["contract"])
            broken["datasets"][0]["fields"][0]["type"] = "invented"
            conn.execute("UPDATE kit_app_contracts SET contract_json=? WHERE contract_row_id=?",
                         ("{" if damage == "json" else canonical(broken), row["contract_row_id"]))
    before = domain_state(kit)
    response = rejected(read_response(review_api, kit), 503, "PROCESS_CONTRACT_UNAVAILABLE")
    assert "data" not in response.json()
    rejected(review_api.get(list_url(kit), headers=headers(org.DATA_ADMIN)),
             503, "PROCESS_CONTRACT_UNAVAILABLE")
    assert domain_state(kit) == before


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_missing_review_ledger_proof_is_503_and_get_never_repairs_it(review_api, kit, decision):
    row = success(review_response(review_api, kit, create(review_api, kit), decision))
    with database(kit, "dp") as conn:
        conn.execute("UPDATE kit_app_contracts SET ledger_event_id=? WHERE contract_row_id=?",
                     ("missing-b5-review-event", row["contract_row_id"]))
    before = domain_state(kit)
    rejected(read_response(review_api, kit), 503,
             "PROCESS_CONTRACT_APPROVAL_UNAVAILABLE" if decision == "APPROVED"
             else "PROCESS_CONTRACT_REJECTION_UNAVAILABLE")
    assert domain_state(kit) == before


def test_data_hold_keeps_review_readable_without_allowing_approval_or_generation(review_api, kit):
    row = create(review_api, kit)
    hold(kit)
    before = domain_state(kit)
    viewed = success(read_response(review_api, kit))
    assert_original(viewed, row)
    assert viewed["permitted_actions"] == ["reject"]
    assert "DATA_USAGE_HOLD" in {item["reason_code"] for item in viewed["review_blockers"]}
    success(review_api.get(list_url(kit), headers=headers(org.DATA_ADMIN)))
    rejected(review_response(review_api, kit, row, "APPROVED"), 409, "DATA_USAGE_HOLD")
    # READ는 원천 소비가 아니다. 실제 GENERATE 판정은 현재 보류를 다시 확인한다.
    error(lambda: kc.validated_v2(kit["store"], instance_id=kit["instance_id"], app_id="APP-03",
        revision=row["revision"], expected_fingerprint=row["semantic_fingerprint"], actor_id=org.MEMBER_A,
        context=kit["context"], for_action="GENERATE", repo=kit["svc"].repo), 409, "DATA_USAGE_HOLD")
    assert domain_state(kit) == before
    result = success(review_response(review_api, kit, row, "REJECTED"))
    assert result["status"] == "REJECTED"
    assert_original(success(read_response(review_api, kit)), result)


@pytest.mark.parametrize("state", ["DRAFT", "HELD_APPROVED", "REJECTED", "SUPERSEDED"])
def test_readable_non_executable_state_cannot_publish_or_materialize(review_api, kit, monkeypatch, state):
    from core import kit_app_builder as kb
    row = create(review_api, kit)
    expected = "PROCESS_CONTRACT_APPROVAL_REQUIRED"
    if state in ("HELD_APPROVED", "SUPERSEDED"):
        row = success(review_response(review_api, kit, row, "APPROVED"))
    if state == "HELD_APPROVED":
        hold(kit)
        expected = "DATA_USAGE_HOLD"
    elif state == "REJECTED":
        row = success(review_response(review_api, kit, row, "REJECTED"))
        expected = "PROCESS_CONTRACT_REJECTED"
    elif state == "SUPERSEDED":
        second = create(review_api, kit, app_class="personal", expected_revision=row["revision"])
        success(review_response(review_api, kit, second, "APPROVED"))
        expected = "PROCESS_CONTRACT_CONFLICT"

    def forbidden(*_args, **_kwargs):
        pytest.fail("읽기만 가능한 계약을 게시·물질화했습니다")
    monkeypatch.setattr(kb, "publish_release", forbidden)
    monkeypatch.setattr(kb.cm, "materialize", forbidden)
    before = domain_state(kit)
    viewed = success(read_response(review_api, kit, revision=row["revision"]))
    assert_original(viewed, row, status="SUPERSEDED" if state == "SUPERSEDED" else row["status"])
    assert viewed["permitted_actions"] == (["approve", "reject"] if state == "DRAFT" else [])
    rejected(review_api.post(url(kit, "build/v2"), json=revision_body(viewed), headers=headers()), 409, expected)
    assert domain_state(kit) == before


def test_legacy_list_retains_project_run_guard_while_v2_review_list_is_readable(review_api, kit):
    """레거시 권한 대조용 명시 합성 registry. 운영 키트/RAW/프로세스 팩 복제 아님."""
    from core.data_preparation.process_kit_instances import binding_for_instance
    profile = {"datasets": [{"dataset_contract_key": "B5-LEGACY", "label": "합성 자료"}],
               "outputs": [{"output": "B5-APP", "label": "합성 구형 앱", "requires": ["B5-LEGACY"]}]}
    registered = kit["store"].upsert_kit_version(kit_id="b5-legacy.test.invalid", version="1.0",
        name="합성 레거시 목록 대조", mode="REAL", source_path="b5-legacy.test.invalid",
        fingerprint_value="b" * 64, profile=profile)
    legacy = kit["store"].create_instance(kit_id=registered["kit_id"], version=registered["version"],
        kit_fingerprint=registered["fingerprint"], created_by=org.MEMBER_A, **kit["context"])
    assert binding_for_instance(kit["store"], legacy) is None
    before = domain_state(kit)
    success(review_api.get(list_url(kit), headers=headers(org.DATA_ADMIN)))
    success(review_api.get(list_url(kit), headers=headers(org.VIEWER_A)))
    for actor in (org.DATA_ADMIN, org.VIEWER_A):
        # 검토자가 실제 목록에서 v2에 진입할 수 있지만 구형 적용본을 열지는 않는다.
        instances = success(review_api.get("/api/v1/data-preparation/instances", headers=headers(actor)))
        visible_ids = {item["instance_id"] for item in instances["instances"]}
        assert kit["instance_id"] in visible_ids
        assert legacy["instance_id"] not in visible_ids
        rejected(review_api.get(list_url(legacy), headers=headers(actor)), 403)
    listed = success(review_api.get(list_url(legacy), headers=headers()))
    app = next(item for item in listed["apps"] if item["app_id"] == "B5-APP")
    assert app["contract_status"] is None and app["contract_revision"] is None
    assert domain_state(kit) == before
