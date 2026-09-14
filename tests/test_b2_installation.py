"""B2 독립 설치 시험. 메인 audit 격리 runner만 실행한다.

정상 경로는 Hooke 후보 manifest 원본을 load_bundle/pin_bundle로 검증·고정한다.
이 파일은 임시 팩 JSON을 정상 원본처럼 만들지 않는다. bundle_stub 명칭의 두
부정시험만 서비스 경계 고장/정책 주입이며 원본 검증 통과 증거가 아니다.
운영 DB/RAW/로그를 읽거나 쓰지 않고 .invalid 합성 조직 fixture를 재사용한다.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import approval, proposal, workspace  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


@pytest.fixture
def installation(workspace, tmp_path):
    from core.data_preparation.process_pack_artifacts import CANDIDATE_MANIFEST, load_bundle, pin_bundle
    from core.data_preparation.store import data_preparation_store
    from core.enterprise_context.process_installation import ProcessInstallationService
    from core.org_directory import org_directory

    paths = {"ecm": Path(workspace["svc"].repo.db_path).resolve(),
             "dp": Path(data_preparation_store.db_path).resolve(),
             "org": Path(org_directory.db_path).resolve()}
    assert all(path.is_relative_to(tmp_path.resolve()) for path in paths.values())
    # 후보가 없거나 깨졌다면 실패해야 한다. 합성 대역/skip으로 정상 검증을 대체하지 않는다.
    bundle = load_bundle(CANDIDATE_MANIFEST)
    assert bundle["profile"]["mode"] == "REAL"
    assert bundle["profile"]["data_class"] == "NO_DATA"
    assert pin_bundle(data_preparation_store, bundle) == bundle
    return {**workspace, "store": data_preparation_store, "bundle": bundle,
            "root": tmp_path.resolve(), "paths": paths, "directory": org_directory,
            "install": ProcessInstallationService(workspace["svc"].repo, data_preparation_store)}


@contextmanager
def _db(w, name="ecm"):
    path = w["paths"][name].resolve()
    assert path.is_relative_to(w["root"]) and path.is_file()
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _tables(w, name="ecm"):
    """한 임시 DB의 논리 내용을 비교한다. WAL/mtime을 무부작용 증거로 삼지 않는다."""
    with _db(w, name) as conn:
        conn.execute("BEGIN")
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        result = {}
        for table in names:
            quoted = '"' + table.replace('"', '""') + '"'
            result[table] = sorted([dict(row) for row in conn.execute(f"SELECT * FROM {quoted}")],
                                   key=lambda row: json.dumps(row, sort_keys=True))
        return result


def _state(w):
    return {name: _tables(w, name) for name in ("ecm", "dp", "org")}


def _events(w, event_type="PROCESS_CONFIGURATION_APPROVED"):
    return [row for row in _tables(w)["enterprise_process_outbox"] if row["event_type"] == event_type]


def _read(w):
    return w["svc"].resolved(boundary=w["boundary"], actor=org.MEMBER_A, context=w["context"])


def _plan(w, **overrides):
    base = _read(w)
    request = dict(artifact_digest=w["bundle"]["artifact_digest"], business_kit_ids=["BK-01"],
                   expected_head_version=base["head_version"], base_profile_id=base["profile_id"],
                   base_fingerprint=base["digest"], reason="격리된 BK-01 업무 설치 검토")
    request.update(overrides)
    preview = w["install"].plan(boundary=w["boundary"], actor=org.MEMBER_A,
                               context=w["context"], **request)
    return request, preview


def _start(w, planned=None, *, key="install-first", actor=org.MEMBER_A, **changes):
    request, preview = planned if planned is not None else _plan(w)
    return w["install"].start(boundary=w["boundary"], actor=actor, context=w["context"],
                              plan_digest=preview["plan_digest"], client_request_id=key,
                              **{**request, **changes})


def _resume(w, operation, **overrides):
    args = dict(operation_id=operation["operation_id"], actor=org.MANAGER_A,
                context=w["context"], expected_revision=operation["revision"], adopt=True)
    return w["install"].resume(**{**args, **overrides})


def _get(w, operation, **overrides):
    args = dict(operation_id=operation["operation_id"], actor=org.MEMBER_A, context=w["context"])
    return w["install"].get(**{**args, **overrides})


def _prepared(w, planned=None):
    return _resume(w, _start(w, planned))


def _apply(w, operation):
    return approval(w, operation["change"], actor=org.MANAGER_ROOT)


def _error(call, status, reason, hidden=()):
    from core.data_preparation.process_pack_artifacts import ProcessPackError
    from core.enterprise_context.process_schema import ProcessError

    with pytest.raises((ProcessError, ProcessPackError)) as raised:
        call()
    assert raised.value.status_code == status
    assert raised.value.reason_code == reason
    text = f"{raised.value.reason_code} {raised.value}"
    assert all(value not in text for value in hidden if value)


def _legacy(w):
    from core.enterprise_context.models import EnterpriseProfile

    payload = {"nodes": [
        {"key": "legacy_sourcing", "label": "회사 기존 구매", "note": None, "overlay": None},
        {"key": "legacy_support", "label": "회사 기존 지원"},
    ], "company_overlay": None, "custom_note": "원문 전체 보존"}
    profile = w["svc"].repo.upsert_profile(EnterpriseProfile(
        profile_id="b2-legacy-company", tenant_id=w["boundary"].tenant_id,
        scope_node_id="", profile_kind="process_profile", payload=payload,
    ))
    preview = w["install"].legacy_preview(boundary=w["boundary"], actor=org.MEMBER_A,
                                          context=w["context"])
    source = next(row for row in preview["sources"] if row["profile_id"] == profile.profile_id)
    decision = dict(profile_id=profile.profile_id, source_digest=source["source_digest"],
                    decision="MIGRATE", confirmed_context=w["boundary"].model_dump(),
                    key_mapping={node["key"]: node["key"] for node in payload["nodes"]})
    return profile, payload, decision


def test_candidate_plan_is_read_only_and_keeps_optional_and_uninstalled_references(installation):
    w = installation
    before = _state(w)
    _, preview = _plan(w)
    assert _state(w) == before
    assert preview["state"] == "PLANNED"
    assert preview["data_ready"] is False and preview["apps_ready"] is False
    nodes = {node["template_key"]: node for node in preview["preview"]["nodes"]}
    assert set(nodes) == {"sourcing", "sourcing.plan", "sourcing.contract",
                          "sourcing.purchase_order", "sourcing.supplier_selection"}
    assert sum(node["level"] == "L2" for node in nodes.values()) == 4
    assert nodes["sourcing.supplier_selection"]["enabled"] is False
    refs = preview["preview"]["relations"]
    assert {ref["target_business_kit_id"] for ref in refs} == {"BK-02", "BK-03", "BK-07"}
    assert all(ref["state"] == "UNINSTALLED" and not ref["target_process_id"] for ref in refs)


def test_candidate_member_proposal_installer_adoption_and_distinct_approval_are_separate(installation):
    w = installation
    op = _start(w)
    assert op["stage"] == "AWAITING_INSTALLER"
    assert op["revision"] == 0
    assert op["actor"] == org.MEMBER_A and not op["installer"]
    assert not op["kit_instance_ref"] and not op["change_id"]
    assert _tables(w, "dp")["kit_instances"] == []
    prepared = _resume(w, op)
    assert prepared["stage"] == "AWAITING_APPROVAL"
    assert prepared["installer"] == org.MANAGER_A and prepared["change"]["actor"] == org.MEMBER_A
    assert _read(w)["state"] == "UNCONFIGURED"
    approved = _apply(w, prepared)
    applied = _get(w, op)
    assert applied["stage"] == "APPLIED" and applied["applied_result"] == approved
    assert applied["applied_profile_id"] == approved["profile_id"] and applied["applied_at"]
    assert applied["data_ready"] is False and applied["apps_ready"] is False
    resolved = _read(w)
    assert resolved["profile_id"] == approved["profile_id"] and resolved["head_version"] == 1
    assert "process_config.propose" in resolved["capabilities"]
    source = resolved["payload"]["template_sources"][0]
    assert source["artifact_digest"] == w["bundle"]["artifact_digest"]
    assert source["kit_instance_ref"] == applied["kit_instance_ref"]
    assert source["accepted_standard_digest"] == source["initial_standard_digest"]
    assert source["accepted_standard_digest"] == w["bundle"]["pack_digest"]
    assert all(binding["state"] in {"UNRESOLVED", "CANDIDATE_ONLY"}
               for binding in resolved["payload"]["bindings"])
    dp = _tables(w, "dp")
    assert len(dp["kit_instances"]) == len(dp["kit_process_instances"]) == 1
    assert dp["dataset_snapshots"] == dp["kit_registry_versions"] == dp["kit_app_contracts"] == []
    assert len(_events(w)) == 1 and _events(w)[0]["event_id"] == approved["event_id"]
    assert len(_events(w, "PROCESS_INSTALLATION_RESUMED")) == 1


def test_same_start_key_and_body_return_same_operation_without_new_rows(installation):
    w = installation
    planned = _plan(w)
    initial = _start(w, planned)
    before = _state(w)
    assert _start(w, planned) == initial
    assert _state(w) == before


def test_same_start_key_different_body_returns_409_without_replacing_plan(installation):
    w = installation
    planned = _plan(w)
    _start(w, planned)
    before = _state(w)
    _error(lambda: _start(w, planned, reason="같은 키의 다른 설치 이유"),
           409, "PROCESS_IDEMPOTENCY_CONFLICT")
    assert _state(w) == before


def test_stale_plan_digest_does_not_reserve_head_or_instance(installation):
    w = installation
    request, preview = _plan(w)
    before = _state(w)
    _error(lambda: _start(w, (request, {**preview, "plan_digest": "0" * 64})),
           409, "PROCESS_PLAN_CONFLICT")
    assert _state(w) == before


def test_member_cannot_execute_own_installation_proposal(installation):
    w = installation
    op = _start(w)
    before = _state(w)
    _error(lambda: _resume(w, op, actor=org.MEMBER_A), 403, "PROCESS_ACTION_FORBIDDEN")
    assert _state(w) == before


def test_manager_must_explicitly_adopt_another_authors_plan(installation):
    w = installation
    op = _start(w)
    before = _state(w)
    _error(lambda: _resume(w, op, adopt=False), 403, "PROCESS_INSTALLER_ADOPTION_REQUIRED")
    assert _state(w) == before
    assert _resume(w, op)["stage"] == "AWAITING_APPROVAL"


def test_two_ecm_and_dp_repository_instances_resume_one_operation_once(installation):
    from core.data_preparation.store import DataPreparationStore
    from core.enterprise_context.process_installation import ProcessInstallationService
    from core.enterprise_context.repository import EcmRepository
    from core.enterprise_context.process_schema import ProcessError

    w = installation
    op = _start(w)
    other_repo = EcmRepository(str(w["paths"]["ecm"]))
    other_store = DataPreparationStore(str(w["paths"]["dp"]))
    other_store._ready()
    other = ProcessInstallationService(other_repo, other_store)
    assert other.repo._lock is not w["svc"].repo._lock
    assert other.store._lock is not w["store"]._lock
    barrier = threading.Barrier(2)

    def resume(service):
        barrier.wait(timeout=10)
        try:
            return service.resume(operation_id=op["operation_id"], actor=org.MANAGER_A,
                                  context=w["context"], expected_revision=op["revision"], adopt=True)
        except ProcessError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(resume, service) for service in (w["install"], other)]
        results = [job.result(timeout=30) for job in jobs]
    successes = [result for result in results if isinstance(result, dict)]
    conflicts = [result for result in results if isinstance(result, ProcessError)]
    assert len(successes) == len(conflicts) == 1
    assert conflicts[0].status_code == 409 and conflicts[0].reason_code == "PROCESS_OPERATION_CONFLICT"
    assert successes[0]["stage"] == "AWAITING_APPROVAL"
    assert successes[0]["revision"] > op["revision"]
    assert _get(w, op) == successes[0]
    ecm, dp = _tables(w), _tables(w, "dp")
    assert len(ecm["enterprise_process_changes"]) == len(ecm["enterprise_profiles"]) == 1
    assert len(dp["kit_instances"]) == len(dp["kit_process_instances"]) == 1
    assert dp["kit_process_instances"][0]["operation_id"] == op["operation_id"]
    assert _events(w) == []
    assert len(_events(w, "PROCESS_INSTALLATION_RESUMED")) == 1


def test_profile_insert_fault_keeps_dp_instance_and_recovers_same_operation(installation, monkeypatch):
    w = installation
    op = _start(w)
    original = _tables(w)

    def fail_profile(*_args, **_kwargs):
        raise sqlite3.OperationalError("B2 합성 profile INSERT 실패")

    with monkeypatch.context() as patch:
        patch.setattr(w["install"], "_insert_profile", fail_profile)
        _error(lambda: _resume(w, op), 503, "PROCESS_STORAGE_UNAVAILABLE")
    failed = _get(w, op)
    assert failed["stage"] == "FAILED_RETRYABLE"
    assert failed["error_code"] == "PROCESS_STORAGE_UNAVAILABLE"
    assert not failed["change_id"]
    ecm = _tables(w)
    for table in ("enterprise_profiles", "enterprise_process_heads", "enterprise_process_changes"):
        assert ecm[table] == original[table]
    assert _events(w) == []
    assert len(_events(w, "PROCESS_INSTALLATION_RESUMED")) == 1
    dp = _tables(w, "dp")
    assert len(dp["kit_instances"]) == len(dp["kit_process_instances"]) == 1
    preserved_id = dp["kit_instances"][0]["instance_id"]
    recovered = _resume(w, failed)
    assert recovered["operation_id"] == op["operation_id"]
    assert recovered["kit_instance_ref"] == preserved_id
    assert recovered["stage"] == "AWAITING_APPROVAL"
    assert _tables(w, "dp") == dp
    _apply(w, recovered)
    assert _get(w, op)["stage"] == "APPLIED"


def test_outbox_fault_rolls_back_installation_applied_and_head_together(installation):
    w = installation
    op = _prepared(w)
    before = _state(w)
    with _db(w) as conn:
        conn.execute("""CREATE TRIGGER b2_test_outbox_failure BEFORE INSERT ON enterprise_process_outbox
                        BEGIN SELECT RAISE(ABORT, 'B2 합성 outbox 실패'); END""")
    _error(lambda: _apply(w, op), 503, "PROCESS_STORAGE_UNAVAILABLE")
    assert _state(w) == before
    assert _get(w, op)["stage"] == "AWAITING_APPROVAL"
    assert _read(w)["state"] == "UNCONFIGURED"
    with _db(w) as conn:
        conn.execute("DROP TRIGGER b2_test_outbox_failure")
    assert _resume(w, op) == _get(w, op)
    approved = _apply(w, op)
    assert _get(w, op)["applied_result"] == approved
    assert _read(w)["profile_id"] == approved["profile_id"]
    assert len(_events(w)) == 1


def test_explicit_v1_mapping_preserves_keys_null_absence_and_original_payload(installation):
    w = installation
    profile, payload, decision = _legacy(w)
    original = next(row for row in _tables(w)["enterprise_profiles"] if row["profile_id"] == profile.profile_id)
    planned = _plan(w, legacy_decisions=[decision], template_mapping={"sourcing": "legacy_sourcing"})
    op = _prepared(w, planned)
    _apply(w, op)
    document = _read(w)["payload"]
    nodes = {node["process_id"]: node for node in document["nodes"]}
    assert nodes["legacy_sourcing"]["label"] == "회사 기존 구매"
    assert nodes["legacy_sourcing"]["template_key"] == "sourcing"
    assert nodes["legacy_sourcing"]["legacy_fields"] == payload["nodes"][0]
    assert nodes["legacy_sourcing"]["legacy_fields"]["overlay"] is None
    assert nodes["legacy_support"]["legacy_fields"] == payload["nodes"][1]
    assert "overlay" not in nodes["legacy_support"]["legacy_fields"]
    assert document["migration_map"][0]["source_payload"] == payload
    assert next(row for row in _tables(w)["enterprise_profiles"] if row["profile_id"] == profile.profile_id) == original


def test_v1_without_explicit_context_mapping_is_not_automatically_migrated(installation):
    w = installation
    _legacy(w)
    before = _state(w)
    _error(lambda: _plan(w), 409, "PROCESS_CONTEXT_REVIEW_REQUIRED")
    assert _state(w) == before


@pytest.mark.parametrize("phase", ["before-resume", "before-approve"])
def test_v1_source_change_after_plan_blocks_installation_without_partial_apply(installation, phase):
    w = installation
    profile, _, decision = _legacy(w)
    planned = _plan(w, legacy_decisions=[decision])
    op = _start(w, planned)
    if phase == "before-approve":
        op = _resume(w, op)
    profile.payload["custom_note"] = "계획 고정 후 바뀐 원문"
    w["svc"].repo.upsert_profile(profile)
    before = _state(w)
    call = (lambda: _resume(w, op)) if phase == "before-resume" else (lambda: _apply(w, op))
    _error(call, 409, "PROCESS_LEGACY_CONFLICT")
    assert _state(w) == before
    assert _get(w, op)["stage"] != "APPLIED"
    assert _read(w)["head_version"] == 0


@pytest.mark.parametrize("dimension", ["tenant", "root", "mode", "scope"])
def test_other_context_cannot_get_resume_or_cancel_known_installation(installation, dimension):
    from core.enterprise_context.models import OrganizationNode

    w = installation
    op = _prepared(w)
    context = dict(w["context"])
    if dimension == "tenant":
        context["tenant_id"] = "b2-other-tenant"
    elif dimension == "root":
        w["svc"].repo.upsert_node(OrganizationNode(
            node_id="b2-other-root", entity_id="t_entity", tenant_id="tenant_default",
            node_type="business_division", name_ko="B2 합성 다른 루트", status="ACTIVE"))
        context["scope_node_id"] = "b2-other-root"
    elif dimension == "mode":
        context.update(entity_mode="VIRTUAL", scope_node_id=org.NODES[org.VIRTUAL_CODE_B])
    else:
        context["scope_node_id"] = org.NODES[org.DEPT_B]
    before = _state(w)
    hidden = (op["operation_id"], op["configuration_id"], op["kit_instance_ref"], op["change_id"])
    _error(lambda: _get(w, op, actor=org.ADMIN, context=context), 404, "PROCESS_NOT_FOUND", hidden)
    _error(lambda: _resume(w, op, actor=org.ADMIN, context=context), 404, "PROCESS_NOT_FOUND", hidden)
    _error(lambda: w["install"].cancel(operation_id=op["operation_id"], actor=org.ADMIN, context=context),
           404, "PROCESS_NOT_FOUND", hidden)
    assert _state(w) == before


def test_role_revoked_in_other_directory_blocks_resume_using_fresh_scope(installation):
    from core.org_directory import OrgDirectory

    w = installation
    op = _start(w)
    directory = w["directory"]
    directory.set_user_roles(org.MANAGER_A, {org.DEPT_A: "manager", org.DEPT_B: "manager"}, actor=org.ADMIN)
    cached = directory.resolve_scope(org.MANAGER_A)
    assert org.DEPT_A in cached.manageable_dept_ids
    other = OrgDirectory(str(w["paths"]["org"]))
    other.set_user_roles(org.MANAGER_A, {org.DEPT_A: "viewer", org.DEPT_B: "manager"}, actor=org.ADMIN)
    assert directory.resolve_scope(org.MANAGER_A) is cached
    before = _state(w)
    _error(lambda: _resume(w, op), 403, "PROCESS_ACTION_FORBIDDEN")
    assert _state(w) == before


def test_retired_installer_cannot_resume_pending_operation(installation):
    from core.org_directory import OrgDirectory

    w = installation
    op = _start(w)
    w["directory"].resolve_scope(org.MANAGER_A)
    assert OrgDirectory(str(w["paths"]["org"])).delete_user(org.MANAGER_A, actor=org.ADMIN)
    before = _state(w)
    _error(lambda: _resume(w, op), 403, "PROCESS_ACTOR_INELIGIBLE")
    assert _state(w) == before


def test_applied_operation_retry_keeps_original_result_after_later_head_revision(installation):
    w = installation
    planned = _plan(w)
    op = _prepared(w, planned)
    installed = _apply(w, op)
    original_result = _get(w, op)
    process_id = next(node["process_id"] for node in _read(w)["payload"]["nodes"]
                      if node["template_key"] == "sourcing.plan")
    change = proposal(w, [{"op": "RENAME", "process_id": process_id, "label": "회사 후속 구매계획"}], key="later-head")
    new_head = approval(w, change, actor=org.MANAGER_ROOT)
    assert new_head["profile_id"] != installed["profile_id"]
    before = _state(w)
    assert _get(w, op) == original_result
    assert _resume(w, original_result) == original_result
    assert _start(w, planned) == original_result
    assert _read(w)["profile_id"] == new_head["profile_id"]
    assert _state(w) == before


def test_author_can_cancel_waiting_proposal_idempotently_without_deleting_data(installation):
    w = installation
    op = _start(w)
    args = dict(operation_id=op["operation_id"], actor=org.MEMBER_A, context=w["context"])
    cancelled = w["install"].cancel(**args)
    assert cancelled["stage"] == "CANCELLED"
    assert w["install"].cancel(**args) == cancelled
    assert _tables(w, "dp")["kit_instances"] == []
    before = _state(w)
    _error(lambda: _resume(w, cancelled), 409, "PROCESS_INSTALLATION_BLOCKED")
    assert _state(w) == before
    assert len(_tables(w)["enterprise_process_installations"]) == 1


def test_applied_installation_cannot_be_cancelled_or_deleted(installation):
    w = installation
    op = _prepared(w)
    _apply(w, op)
    before = _state(w)
    _error(lambda: w["install"].cancel(operation_id=op["operation_id"], actor=org.MEMBER_A,
                                      context=w["context"]), 409, "PROCESS_INSTALLATION_CONFLICT")
    assert _state(w) == before


def test_different_author_cannot_cancel_visible_pending_proposal(installation):
    w = installation
    op = _start(w)
    before = _state(w)
    _error(lambda: w["install"].cancel(operation_id=op["operation_id"], actor=org.MANAGER_A,
                                      context=w["context"]), 403, "PROCESS_ACTION_FORBIDDEN")
    assert _state(w) == before


def test_next_business_kit_reuses_explicit_instance_and_resolves_existing_shortcut(installation):
    w = installation
    first = _prepared(w)
    _apply(w, first)
    planned = _plan(w, business_kit_ids=["BK-02"], instance_id=first["kit_instance_ref"])
    second = _resume(w, _start(w, planned, key="install-logistics"))
    _apply(w, second)
    assert second["kit_instance_ref"] == first["kit_instance_ref"]
    assert len(_tables(w, "dp")["kit_instances"]) == 1
    doc = _read(w)["payload"]
    shipment = next(ref for ref in doc["relations"] if ref["target_template_key"] == "logistics.shipment")
    assert shipment["state"] == "RESOLVED" and shipment["target_process_id"]
    assert len({node["process_id"] for node in doc["nodes"]}) == len(doc["nodes"])
    optional = next(node for node in doc["nodes"] if node["template_key"] == "sourcing.supplier_selection")
    assert optional["enabled"] is False


def test_old_writer_on_installed_pack_keeps_l2_and_every_binding(installation):
    """구 편집기의 평면 저장은 409 다. 설치가 만든 L2 와 바인딩이 하나도 사라지지 않는다."""
    from core.enterprise_context.models import EnterpriseProfile
    from core.enterprise_context.repository import EcmRepository
    w = installation
    _apply(w, _prepared(w))
    before = _read(w)["payload"]
    # 합성 ADD_NODE 문서가 아니라 실제 팩 설치판이어야 이 회귀가 의미를 갖는다.
    assert {node["level"] for node in before["nodes"]} == {"L1", "L2"}
    assert before["bindings"] and {binding["kind"] for binding in before["bindings"]}
    state = _state(w)
    other = EcmRepository(db_path=str(w["paths"]["ecm"]))
    _error(lambda: other.upsert_profile(EnterpriseProfile(
        tenant_id=w["boundary"].tenant_id, scope_node_id=w["boundary"].scope_node_id,
        profile_kind="process_profile", payload={"nodes": []})), 409, "PROCESS_SCHEMA_UPGRADE_REQUIRED")
    assert _state(w) == state
    assert _read(w)["payload"] == before


def test_same_standard_task_reuses_one_canonical_node_and_never_duplicates(installation):
    """같은 표준 업무는 한 정본으로 재사용한다. 재설치가 업무를 늘리지 않는다."""
    w = installation
    first = _prepared(w)
    _apply(w, first)
    before = {node["process_id"]: node["template_key"] for node in _read(w)["payload"]["nodes"]}
    planned = _plan(w, business_kit_ids=["BK-01"], instance_id=first["kit_instance_ref"],
                    reason="같은 업무키트 재설치")
    _apply(w, _resume(w, _start(w, planned, key="install-same-kit")))
    assert {node["process_id"]: node["template_key"] for node in _read(w)["payload"]["nodes"]} == before


@pytest.mark.parametrize("case,message", [("fixed_mapping", "이미 고정된"), ("level", "계층·부모"),
                                          ("already_bound", "이미 다른 표준")])
def test_standard_task_mapping_conflict_is_explicit_and_never_merges_by_name(installation, case, message):
    """표준 업무를 이름으로 합치지 않는다. 어긋난 대응은 계획 단계에서 갈래별로 막는다."""
    from core.enterprise_context.process_schema import ProcessError
    w = installation
    first = _prepared(w)
    _apply(w, first)
    before = _state(w)
    keys = {node["template_key"]: node["process_id"] for node in _read(w)["payload"]["nodes"]}
    kits, mapping = {
        "fixed_mapping": (["BK-01"], {"sourcing": "proc_" + "0" * 32}),
        "level": (["BK-02"], {"logistics": keys["sourcing.plan"]}),
        "already_bound": (["BK-02"], {"logistics": keys["sourcing"]}),
    }[case]
    with pytest.raises(ProcessError) as raised:
        _plan(w, business_kit_ids=kits, instance_id=first["kit_instance_ref"],
              template_mapping=mapping, reason="표준 업무 대응 검토")
    assert raised.value.reason_code == "PROCESS_MAPPING_CONFLICT" and raised.value.status_code == 409
    assert message in str(raised.value)
    assert _state(w) == before


def test_bundle_stub_synthetic_mode_never_installs_into_real_context(installation, monkeypatch):
    w = installation
    stub = copy.deepcopy(w["bundle"])
    stub["profile"]["mode"] = "DEMO/SYNTHETIC"
    # 서비스의 모드 경계만 주입한다. 위조 bundle pin/원문 검증의 성공을 주장하지 않는다.
    monkeypatch.setattr(w["install"], "_bundle", lambda _digest: stub)
    before = _state(w)
    _error(lambda: _plan(w), 422, "PROCESS_PACK_MODE_MISMATCH")
    assert _state(w) == before


def test_bundle_stub_read_failure_records_retryable_state_and_recovers_same_operation(installation, monkeypatch):
    from core.data_preparation.process_pack_artifacts import ProcessPackError

    w = installation
    op = _start(w)

    def unavailable(_digest):
        raise ProcessPackError("PROCESS_ARTIFACT_STORAGE_UNAVAILABLE", "B2 합성 원본 조회 장애", 503)

    with monkeypatch.context() as patch:
        patch.setattr(w["install"], "_bundle", unavailable)
        _error(lambda: _resume(w, op), 503, "PROCESS_ARTIFACT_STORAGE_UNAVAILABLE")
    failed = _get(w, op)
    assert failed["stage"] == "FAILED_RETRYABLE"
    assert failed["error_code"] == "PROCESS_ARTIFACT_STORAGE_UNAVAILABLE"
    assert _tables(w, "dp")["kit_instances"] == []
    assert _tables(w)["enterprise_process_changes"] == []
    recovered = _resume(w, failed)
    assert recovered["operation_id"] == op["operation_id"] and recovered["stage"] == "AWAITING_APPROVAL"
    assert len(_tables(w, "dp")["kit_instances"]) == 1


def test_same_artifact_without_explicit_instance_is_rejected_during_plan(installation):
    w = installation
    _apply(w, _prepared(w))
    before = _state(w)
    _error(lambda: _plan(w, business_kit_ids=["BK-02"]),
           409, "PROCESS_INSTANCE_SELECTION_REQUIRED")
    assert _state(w) == before
    assert len(_tables(w, "dp")["kit_instances"]) == 1


def test_old_attempt_failure_cannot_overwrite_new_installer_preparing_attempt(installation, monkeypatch):
    from core.data_preparation import process_kit_instances

    w = installation
    op = _start(w)
    original_create = process_kit_instances.create_or_get
    old_entered, new_entered = threading.Event(), threading.Event()
    release_old, release_new = threading.Event(), threading.Event()

    def gated_create(store, **kwargs):
        if kwargs["actor"] == org.MANAGER_A:
            old_entered.set()
            assert release_old.wait(timeout=20), "이전 시도 해제 신호가 없습니다."
            raise sqlite3.OperationalError("B2 이전 attempt의 늦은 실패")
        assert kwargs["actor"] == org.MANAGER_ROOT
        new_entered.set()
        assert release_new.wait(timeout=20), "새 시도 해제 신호가 없습니다."
        return original_create(store, **kwargs)

    monkeypatch.setattr(process_kit_instances, "create_or_get", gated_create)
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            old_job = pool.submit(_resume, w, op)
            assert old_entered.wait(timeout=20)
            old_preparing = _get(w, op)
            assert old_preparing["stage"] == "PREPARING"
            new_job = pool.submit(_resume, w, old_preparing, actor=org.MANAGER_ROOT)
            assert new_entered.wait(timeout=20)
            newer = _get(w, op)
            assert newer["stage"] == "PREPARING" and newer["installer"] == org.MANAGER_ROOT
            assert newer["revision"] > old_preparing["revision"]
            before_old_failure = _tables(w)["enterprise_process_installations"]
            assert before_old_failure[0]["attempt_id"]
            release_old.set()
            _error(lambda: old_job.result(timeout=20), 503, "PROCESS_STORAGE_UNAVAILABLE")
            # stage만 PREPARING인지 보는 guard로는 부족하다. 새 attempt/revision 자체가 보존돼야 한다.
            assert _get(w, op) == newer
            assert _tables(w)["enterprise_process_installations"] == before_old_failure
            assert _tables(w, "dp")["kit_instances"] == []
            release_new.set()
            completed = new_job.result(timeout=20)
        finally:
            release_old.set()
            release_new.set()
    assert completed["stage"] == "AWAITING_APPROVAL"
    assert completed["installer"] == org.MANAGER_ROOT
    assert completed["revision"] > newer["revision"]
    dp = _tables(w, "dp")
    assert len(dp["kit_instances"]) == 1 and dp["kit_instances"][0]["created_by"] == org.MANAGER_ROOT
    events = [json.loads(row["payload_json"]) for row in _events(w, "PROCESS_INSTALLATION_RESUMED")]
    assert len(events) == 2
    adopted = next(event for event in events if event["installer"] == org.MANAGER_ROOT)
    assert adopted["previous_installer"] == org.MANAGER_A and adopted["adopted"] is True


@pytest.mark.parametrize("damage,status,reason", [
    ("inactive", 409, "PROCESS_INSTANCE_CONFLICT"),
    ("identity", 503, "PROCESS_INSTANCE_CONFLICT"),
    ("artifact", 503, "PROCESS_ARTIFACT_CORRUPT"),
])
def test_approval_rechecks_dp_instance_and_pinned_artifact_before_any_apply(installation, damage, status, reason):
    w = installation
    op = _prepared(w)
    with _db(w, "dp") as conn:
        if damage == "inactive":
            conn.execute("UPDATE kit_instances SET status='inactive' WHERE instance_id=?", (op["kit_instance_ref"],))
        elif damage == "identity":
            conn.execute("UPDATE kit_instances SET kit_fingerprint=? WHERE instance_id=?",
                         ("0" * 64, op["kit_instance_ref"]))
        else:
            # 실제 tmp 저장 원본 손상. 트리거 원형을 즉시 복구하며 후보 파일은 건드리지 않는다.
            trigger = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' "
                                   "AND name='kit_process_artifacts_no_update'").fetchone()
            assert trigger and trigger[0]
            conn.execute("DROP TRIGGER kit_process_artifacts_no_update")
            conn.execute("UPDATE kit_process_artifacts SET bundle_json='{}' WHERE artifact_digest=?",
                         (w["bundle"]["artifact_digest"],))
            conn.execute(trigger[0])
    before = _state(w)
    _error(lambda: _apply(w, op), status, reason)
    assert _state(w) == before
    assert _get(w, op)["stage"] == "AWAITING_APPROVAL"
    assert _read(w)["head_version"] == 0
    assert _events(w) == []
