"""B3 키트 2.0 독립 시험. 실행은 메인 audit 격리 runner 전용이다.

정상 후보는 실제 process pack load/pin과 B1/B2 승인 경로를 쓴다. 모든 조직은
.invalid, DB는 검증한 tmp 경로다. 인증은 합성 메타데이터·B0 정책/서명 시험이며
RAW/운영 데이터/Host 실행 증거가 아니다. publisher_materializer_stub 시험은
저장 readback·호출 순서 검증용 대역으로, 실제 물질화 시험과 구별한다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core import app_manifest, app_runtime_contract as arc
from core import kit_app_builder as kb, kit_app_contract as kc, project_data_context as pdc
from core.enterprise_context.process_context import ProcessContextService, snapshot_fingerprint
from core.enterprise_context.process_schema import ProcessError, canonical
from tests import org_seed as org
from tests.test_b1_process_configuration import approval, proposal, workspace  # noqa: F401
from tests.test_b2_installation import installation, _plan, _prepared, _apply, _read, _state  # noqa: F401
from tests.test_b3_process_context import build as process_build, database, error
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


TEMPLATES = ("inventory.availability", "inventory.movement", "production.planning",
             "production.execution", "production.capacity")
DATA_KEYS = ("INV-01", "INV-02", "MDM-05", "MDM-06", "MFG-01", "MFG-02", "MFG-03", "QLT-01")
APP_KEYS = {"INV-01", "INV-02", "MFG-01", "MFG-02", "MFG-03", "QLT-01"}


def metadata_certified(w, key, *, existing_binding=None, column="amount"):
    """RAW 생성 없이 합성 행의 schema·정책·서명 메타데이터만 준비한다."""
    from core.data_preparation import certification_subject as cs, models as m, ownership_binding as ob
    from core.data_preparation import snapshot_service as ss
    store = w["store"]
    if existing_binding is None:
        binding = store.create_binding(instance_id=w["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={}, created_by=org.MANAGER_A, **w["context"])
        for stage in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            binding = store.transition(binding["binding_id"], stage)
        args = dict(**w["context"], dataset_contract_key=key, owner_dept_id=org.DEPT_A,
                    evidence_ref="test-only-b3-kit-owner")
        approved = ob.approve(**args, actor_id=org.ADMIN)
        with store.transaction() as conn:
            ob.declare(conn, **args, approved_by=org.ADMIN, approval_event_id=approved["approval_event_id"],
                       effective_from=approved["effective_from"])
    else:
        binding = existing_binding
    raw = (column + "\n1\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = store.create_snapshot(instance_id=w["instance_id"], binding_id=binding["binding_id"],
        dataset_contract_key=key, data_kind=m.DATA_KIND_REAL, checksum=digest, content_fingerprint=digest,
        byte_size=len(raw), row_count=1, schema=[{"name": column, "type": "number"}],
        created_by=org.MANAGER_A, **w["context"])
    sid, rows = snapshot["snapshot_id"], [{column: "1"}]
    ss.profile(store, sid, rows, [column])
    ss.standardize(store, sid, rows)
    ss.reconcile(store, sid, rows, {"row_count": 1})
    args = dict(actor=org.MANAGER_A, context=w["context"], use_kind="OPERATIONAL",
                period_from="2026-08-01", period_to="2026-08-31")
    preview = cs.preview(store, sid, **args)
    signed = cs.sign(store, sid, **args, review_kind="DATA_OWNER",
        reconciliation_evidence="합성 표 총계와 원천 대사 일치 확인", subject_id=preview["subject_id"],
        expected_subject_digest=preview["digest"], client_request_id="b3-kit-" + sid)
    assert signed["certified"]
    return {"binding": binding, "snapshot_id": sid}


def cold_kit(installation, monkeypatch):
    """실제 설치·정책 승인·8개 인증을 수행하는 cold 경로. seed 생성과 등가 시험이 쓴다."""
    from core.data_preparation import certification_authority as ca
    from core.decision_ledger import decision_ledger
    w = installation
    prepared = _prepared(w, _plan(w, business_kit_ids=["BK-03", "BK-04"]))
    approved = _apply(w, prepared)
    doc = _read(w)["payload"]
    w = {**w, "approved": approved, "instance_id": doc["template_sources"][0]["kit_instance_ref"],
         "ids": {n["template_key"]: n["process_id"] for n in doc["nodes"]},
         "ctx": ProcessContextService(w["svc"].repo, w["store"])}
    monkeypatch.setattr(decision_ledger, "db_path", str(w["root"] / "b3-kit-ledger.db"))
    monkeypatch.setattr(decision_ledger, "_prepared_for", None)
    assert Path(decision_ledger.db_path).resolve().is_relative_to(w["root"])
    policy = {"required_reviews": {"OPERATIONAL": ["DATA_OWNER"], "MANAGEMENT": ["DATA_OWNER", "EXECUTIVE"]},
        "grants": {"DATA_OWNER": [{"dept_id": org.DEPT_A, "role": "manager", "scope_node_id": org.NODES[org.DEPT_A]}],
                   "EXECUTIVE": [{"dept_id": org.DEPT_ROOT, "role": "viewer", "scope_node_id": org.NODES[org.DEPT_ROOT]}]},
        "delegations": [], "allow_same_actor": False, "min_evidence_length": 10}
    ca.approve_policy(w["store"], tenant_id=w["context"]["tenant_id"], entity_mode="REAL",
        context_root_id=w["boundary"].context_root_id, actor=org.ADMIN,
        evidence_ref="test-only-b3-kit-policy", document=policy)
    w["data"] = {key: metadata_certified(w, key) for key in DATA_KEYS}
    w["fixed"] = process_build(w, [w["ids"][key] for key in TEMPLATES])
    w["ledger"] = decision_ledger
    assert "GENERATE" in w["fixed"]["permitted_actions"]
    assert "RELEASE" not in w["fixed"]["permitted_actions"]
    return w


@pytest.fixture
def kit(installation, monkeypatch, request, tmp_path_factory):
    from tests.b3_kit_seed import cached_kit
    return cached_kit(request, installation, monkeypatch, tmp_path_factory, cold_kit)


def producer(w, **changes):
    args = dict(instance_id=w["instance_id"], app_id="APP-03", actor_id=org.MEMBER_A, context=w["context"],
                process_context=w["fixed"], app_class="departmental", repo=w["svc"].repo)
    return kb.contract_from_process_context(w["store"], **{**args, **changes})


def draft(w, **changes):
    args = dict(instance_id=w["instance_id"], app_id="APP-03", actor_id=org.MEMBER_A, context=w["context"],
        process_context=w["fixed"], app_class="departmental", expected_revision=0, repo=w["svc"].repo)
    return kc.draft_v2(w["store"], **{**args, **changes})


def approve(w, row, **changes):
    args = dict(instance_id=w["instance_id"], app_id="APP-03", revision=row["revision"],
        expected_fingerprint=row["semantic_fingerprint"], actor_id=org.ADMIN, context=w["context"],
        rationale="합성 메타데이터 후보 계약 독립 검토", repo=w["svc"].repo)
    return kc.approve_v2(w["store"], **{**args, **changes})


def validated(w, row, **changes):
    args = dict(instance_id=w["instance_id"], app_id="APP-03", revision=row["revision"],
        expected_fingerprint=row["semantic_fingerprint"], actor_id=org.MEMBER_A,
        context=w["context"], require_approved=True, repo=w["svc"].repo)
    return kc.validated_v2(w["store"], **{**args, **changes})


def build_app(w, row, **changes):
    args = dict(store=w["store"], app_data=object(), instance_id=w["instance_id"], app_id="APP-03",
        revision=row["revision"], expected_fingerprint=row["semantic_fingerprint"], actor_id=org.MEMBER_A,
        context=w["context"], repo=w["svc"].repo)
    return kb.build_v2(**{**args, **changes})


def hold(w):
    with database(w, "dp") as conn:
        conn.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
            (canonical({"usage_holds": ["REHEARSAL_ONLY"]}), w["data"]["INV-01"]["binding"]["binding_id"]))


def test_actual_pinned_candidate_produces_read_only_v2_without_side_effects(kit):
    before = _state(kit)
    contract = producer(kit)
    assert _state(kit) == before
    assert contract["schema_version"] == "2.0" and contract["status"] == "DRAFT"
    assert arc.validate(contract) == []
    assert contract["process_context"] == kit["fixed"]
    assert {d["enterprise_contract_key"] for d in contract["datasets"]} == APP_KEYS
    assert all(d["allowed_actions"] == ["read"] and d["fields"][0]["name"] == "amount"
               and d["fields"][0]["type"] == "number" for d in contract["datasets"])
    assert contract["process_context"]["sources"][1]["artifact_digest"] == kit["bundle"]["artifact_digest"]


def test_v1_pure_producer_bytes_and_global_version_do_not_change(kit):
    blueprint = {"app_id": "LEGACY", "datasets": ["PRC-01"]}
    args = dict(project_id="legacy-synthetic", app_class="departmental",
                schema_for=lambda _: [{"name": "amount", "type": "number"}])
    before = canonical(kb.contract_from_blueprint(blueprint, **args)).encode()
    producer(kit)
    assert canonical(kb.contract_from_blueprint(blueprint, **args)).encode() == before
    assert arc.SCHEMA_VERSION == "1.0"


def test_mutable_permission_advice_does_not_change_contract_fingerprint(kit):
    member, manager = producer(kit), producer(kit, actor_id=org.MANAGER_A)
    assert member["process_context"]["permitted_actions"] != manager["process_context"]["permitted_actions"]
    assert member["semantic_fingerprint"] == manager["semantic_fingerprint"]


def test_selected_processes_must_cover_all_candidate_data(kit):
    fixed = process_build(kit, [kit["ids"]["inventory.availability"]])
    error(lambda: producer(kit, process_context=fixed), 409, "PROCESS_BLUEPRINT_REQUIREMENTS_UNRESOLVED")


def test_candidate_from_unselected_process_is_not_an_automatic_app(kit):
    error(lambda: producer(kit, app_id="APP-01"), 409, "PROCESS_BLUEPRINT_PROCESS_MISMATCH")


def test_unknown_pinned_candidate_is_not_registry_fallback(kit):
    error(lambda: producer(kit, app_id="APP-NOT-PINNED"), 404, "PROCESS_BLUEPRINT_NOT_FOUND")


@pytest.mark.parametrize("schema", [[], ["amount"], [{"name": "amount", "type": "invented"}],
    [{"name": "record_id", "type": "string"}],
    [{"name": "amount", "type": "number"}, {"name": "amount", "type": "number"}]])
def test_schema_projection_unit_does_not_invent_empty_or_unknown_fields(schema):
    """schema 변환 단위 대역이다. 인증·원본 검증 시험으로 세지 않는다."""
    # 실제 fingerprint/_fixed_schema는 유지하고 인증 fixture와 DB만 제거한다.
    raw = {"snapshot_id": "projection-only", "binding_id": "projection-binding",
        "instance_id": "projection-instance", "dataset_contract_key": "INV-01",
        "tenant_id": "projection.test.invalid", "scope_node_id": "projection-scope",
        "entity_mode": "REAL", "state": "SOURCE_CERTIFIED", "data_kind": "REAL",
        "checksum": "a" * 64, "content_fingerprint": "a" * 64, "byte_size": 9, "row_count": 1,
        "schema_json": canonical(schema), "profile_json": "{}", "control_total_json": "{}",
        "quarantine_json": "{}", "period_from": "2026-08-01", "period_to": "2026-08-31",
        "certified_use_kind": "OPERATIONAL", "certified_by": "projection@test.invalid",
        "certified_at": "2026-09-13T00:00:00Z"}
    ref = {"snapshot_id": raw["snapshot_id"], "snapshot_fingerprint": snapshot_fingerprint(raw)}
    class ProjectionConnection:
        def execute(self, *_args):
            return self
        def fetchone(self):
            return raw
    error(lambda: kb._fixed_schema(ProjectionConnection(), ref), 503, "PROCESS_SCHEMA_UNAVAILABLE")


def test_later_certified_schema_does_not_replace_fixed_snapshot(kit):
    old = producer(kit)
    newer = metadata_certified(kit, "INV-01", existing_binding=kit["data"]["INV-01"]["binding"], column="new_amount")
    assert newer["snapshot_id"] != kit["data"]["INV-01"]["snapshot_id"]
    assert producer(kit) == old


def test_label_only_head_change_keeps_historical_contract_meaning(kit):
    old = producer(kit)
    approval(kit, proposal(kit, [{"op": "RENAME", "process_id": kit["ids"]["production.planning"],
                               "label": "현업 표시 이름 변경"}], "kit-label-only"))
    assert producer(kit) == old


def test_disabled_process_blocks_old_fixed_contract(kit):
    approval(kit, proposal(kit, [{"op": "SET_USAGE", "process_id": kit["ids"]["production.planning"],
                               "enabled": False}], "kit-disable"))
    error(lambda: producer(kit), 409, "PROCESS_DISABLED")


def test_draft_same_expected_revision_same_body_is_idempotent(kit):
    first = draft(kit)
    before = _state(kit)
    assert draft(kit) == first
    assert _state(kit) == before
    assert first["revision"] == 1


def test_draft_stale_expected_revision_different_body_conflicts(kit):
    draft(kit)
    error(lambda: draft(kit, app_class="personal"), 409, "PROCESS_CONTRACT_CONFLICT")


def test_new_revision_preserves_prior_draft_original_bytes(kit):
    first = draft(kit)
    with database(kit, "dp") as conn:
        before = conn.execute("SELECT contract_json FROM kit_app_contracts WHERE contract_row_id=?",
                              (first["contract_row_id"],)).fetchone()[0]
    second = draft(kit, app_class="personal", expected_revision=1)
    assert second["revision"] == 2
    with database(kit, "dp") as conn:
        assert conn.execute("SELECT contract_json FROM kit_app_contracts WHERE contract_row_id=?",
                            (first["contract_row_id"],)).fetchone()[0] == before


def test_concurrent_different_drafts_have_one_revision_winner(kit, monkeypatch):
    barrier, real = threading.Barrier(2), kb.contract_from_process_context
    def simultaneous(*args, **kwargs):
        value = real(*args, **kwargs)
        barrier.wait(timeout=20)
        return value
    monkeypatch.setattr(kb, "contract_from_process_context", simultaneous)
    def submit(app_class):
        try:
            return draft(kit, app_class=app_class)
        except ProcessError as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(submit, ["personal", "departmental"]))
    assert sum(isinstance(item, dict) for item in result) == 1
    assert result.count(409) == 1
    assert len(kc.list_for_instance(kit["store"], kit["instance_id"])) == 1


def test_distinct_approval_and_retry_are_server_verified_and_viewer_can_run(kit):
    row = approve(kit, draft(kit))
    before = _state(kit)
    assert approve(kit, row) == row
    assert validated(kit, row, actor_id=org.VIEWER_A, for_action="RUN") == row
    assert _state(kit) == before
    assert row["status"] == "APPROVED" and row["approved_by"] != row["drafted_by"]


def test_stale_approval_fingerprint_does_not_approve(kit):
    row = draft(kit)
    error(lambda: approve(kit, row, expected_fingerprint="0" * 64), 409, "PROCESS_CONTRACT_CONFLICT")
    assert kc.latest(kit["store"], kit["instance_id"], "APP-03")["status"] == "DRAFT"


def test_author_cannot_approve_even_when_platform_admin(kit):
    row = draft(kit, actor_id=org.ADMIN)
    error(lambda: approve(kit, row), 403, "PROCESS_DISTINCT_REVIEWER_REQUIRED")


def test_member_cannot_approve_and_viewer_cannot_generate(kit):
    row = draft(kit)
    error(lambda: approve(kit, row, actor_id=org.MEMBER_A), 403, "PROCESS_ACTION_FORBIDDEN")
    assert kc.latest(kit["store"], kit["instance_id"], "APP-03") == row
    error(lambda: producer(kit, actor_id=org.VIEWER_A), 403)


@pytest.mark.parametrize("failure", ["unavailable", "integrity"])
def test_approval_authority_storage_fault_remains_503_not_permission_denial(kit, monkeypatch, failure):
    from core.data_preparation import ownership_binding as ob
    row = draft(kit)
    def unavailable(_actor):
        kind = ob.OwnershipUnavailable if failure == "unavailable" else ob.OwnershipIntegrityError
        raise kind("synthetic authority storage failure")
    monkeypatch.setattr(ob, "require_approval_authority", unavailable)
    error(lambda: approve(kit, row), 503, "PROCESS_CONTEXT_UNAVAILABLE")
    assert kc.latest(kit["store"], kit["instance_id"], "APP-03") == row


def test_data_admin_can_approve_candidate_without_release_permission(kit):
    from core.org_directory import org_directory
    org_directory.set_user_roles(org.DATA_ADMIN, {org.DEPT_ROOT: "viewer"}, actor="test")
    fixed = process_build(kit, [kit["ids"][key] for key in TEMPLATES], actor=org.DATA_ADMIN)
    assert "RELEASE" not in fixed["permitted_actions"]
    row = approve(kit, draft(kit), actor_id=org.DATA_ADMIN)
    assert row["approved_by"] == org.DATA_ADMIN and row["status"] == "APPROVED"


def test_new_hold_blocks_approval_without_rebinding(kit):
    row = draft(kit)
    hold(kit)
    error(lambda: approve(kit, row), 409, "DATA_USAGE_HOLD")
    assert kc.latest(kit["store"], kit["instance_id"], "APP-03")["status"] == "DRAFT"


def test_ledger_failure_leaves_draft_unapproved(kit, monkeypatch):
    row = draft(kit)
    def unavailable(**_kwargs):
        raise OSError("synthetic ledger failure")
    monkeypatch.setattr(kit["ledger"], "append", unavailable)
    error(lambda: approve(kit, row), 503, "PROCESS_CONTRACT_APPROVAL_UNAVAILABLE")
    assert kc.latest(kit["store"], kit["instance_id"], "APP-03") == row


def test_dp_failure_after_ledger_keeps_draft_and_retry_recovers(kit):
    row = draft(kit)
    with database(kit, "dp") as conn:
        conn.execute("CREATE TRIGGER b3_kit_fail BEFORE UPDATE ON kit_app_contracts "
                     "BEGIN SELECT RAISE(ABORT,'synthetic update failure'); END")
    error(lambda: approve(kit, row), 503)
    assert kc.latest(kit["store"], kit["instance_id"], "APP-03") == row
    with database(kit, "dp") as conn:
        conn.execute("DROP TRIGGER b3_kit_fail")
    assert approve(kit, row)["status"] == "APPROVED"


def test_superseded_contract_cannot_be_used_for_build(kit):
    first = approve(kit, draft(kit))
    second = approve(kit, draft(kit, expected_revision=1, app_class="personal"))
    assert second["revision"] == 2
    error(lambda: validated(kit, first), 409, "PROCESS_CONTRACT_CONFLICT")


def test_corrupt_saved_original_cannot_pass_idempotent_draft(kit):
    row = draft(kit)
    with database(kit, "dp") as conn:
        damaged = copy.deepcopy(row["contract"])
        damaged["datasets"][0]["fields"][0]["type"] = "invented"
        conn.execute("UPDATE kit_app_contracts SET contract_json=? WHERE contract_row_id=?",
                     (canonical(damaged), row["contract_row_id"]))
    error(lambda: draft(kit), 503, "PROCESS_CONTRACT_UNAVAILABLE")


@pytest.mark.parametrize("field,value", [("tenant_id", "other-tenant"), ("entity_mode", "DEMO"),
    ("scope_node_id", org.DEPT_B), ("context_root_id", "other-root")])
def test_invisible_boundary_hides_contract_details(kit, field, value):
    # org.NODES는 enforced_org fixture가 seed한 후에만 해석한다.
    context = {field: org.NODES[value] if field == "scope_node_id" else value}
    row = draft(kit)
    exc = error(lambda: validated(kit, row, context={**kit["context"], **context}), 404)
    assert row["contract_row_id"] not in str(exc)


def test_project_v2_binding_preserves_exact_seals_and_allows_viewer_run(kit):
    binding = pdc.bind_process_instance(kit["store"], kit["instance_id"], actor_id=org.MEMBER_A,
        context=kit["context"], process_context=kit["fixed"], repo=kit["svc"].repo)
    assert binding["sealed_snapshots"] == {key: value["snapshot_id"] for key, value in kit["data"].items()}
    assert pdc.validate_process_binding(kit["store"], binding, actor_id=org.VIEWER_A,
        context=kit["context"], for_action="RUN", repo=kit["svc"].repo) == binding


def test_project_v2_hash_forgery_is_not_accepted(kit):
    binding = pdc.bind_process_instance(kit["store"], kit["instance_id"], actor_id=org.MEMBER_A,
        context=kit["context"], process_context=kit["fixed"], repo=kit["svc"].repo)
    binding["sealed_snapshots"]["INV-01"] = "another-snapshot"
    error(lambda: pdc.validate_process_binding(kit["store"], binding, actor_id=org.MEMBER_A,
        context=kit["context"], repo=kit["svc"].repo), 409, "PROCESS_DATA_BINDING_CONFLICT")


def test_real_project_binding_does_not_enable_external_prompt_egress(kit, monkeypatch):
    binding = pdc.bind_process_instance(kit["store"], kit["instance_id"], actor_id=org.MEMBER_A,
        context=kit["context"], process_context=kit["fixed"], repo=kit["svc"].repo)
    def forbidden(*_args, **_kwargs):
        pytest.fail("REAL prompt gate 전에 RAW 소비를 시도했습니다")
    monkeypatch.setattr(pdc, "load_sealed", forbidden)
    with pytest.raises(pdc.ProjectDataBindingError):
        pdc.render_agent_context(kit["store"], binding, ["INV-01"], actor_id=org.MEMBER_A,
                                 context=kit["context"], repo=kit["svc"].repo)


def test_build_requires_real_server_approval_before_publishing(kit, monkeypatch):
    row = draft(kit)
    monkeypatch.setattr(kb, "publish_release", lambda **_: pytest.fail("미승인 계약 게시"))
    error(lambda: build_app(kit, row), 409, "PROCESS_CONTRACT_APPROVAL_REQUIRED")


def publisher_materializer_stub(w, monkeypatch, *, corrupt=None, wrong_result=False):
    """원본 인증/권한/계약/CAS/plan/cohort는 실제 경로, FS 게시·AppData만 임시 대역."""
    from core import library_paths
    from core.studio_release_cohort import get_release_cohort
    calls = []
    def directory(release_id):
        target = (w["root"] / "test-releases" / release_id).resolve()
        assert target.is_relative_to(w["root"])
        return str(target)
    monkeypatch.setattr(library_paths, "release_dir", directory)
    def publish(**kwargs):
        release_id, contract = kwargs["release_id"], kwargs["contract"]
        cohort = get_release_cohort(w["store"], release_id)
        assert cohort["instance_id"] == kwargs["instance_id"]
        assert cohort["context_key"] == contract["process_context"]["context_key"]
        calls.append("publish-after-cohort")
        result = dict(release_id=release_id, project_id=release_id, app_id=kwargs["app_id"],
            instance_id=kwargs["instance_id"], tenant_id=kwargs["tenant_id"], entity_mode=kwargs["entity_mode"],
            enterprise_scope_id=kwargs["scope_node_id"], runtime_document_version="2.0",
            runtime_contract=copy.deepcopy(contract), manifest=app_manifest.snapshot(contract["manifest"]),
            owner_dept_id=org.DEPT_A)
        saved = copy.deepcopy(result)
        if corrupt:
            saved[corrupt] = None
        path = Path(directory(release_id)) / "release.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        return result
    def materialize(contract, **kwargs):
        calls.append("materialize")
        return kb.cm.Result(datasets=[dict(name=d["name"], release_id="wrong" if wrong_result else kwargs["release_id"])
                                      for d in contract["datasets"]], resolved=[])
    monkeypatch.setattr(kb, "publish_release", publish)
    monkeypatch.setattr(kb.cm, "materialize", materialize)
    return calls


def test_member_build_publisher_materializer_stub_pins_cohort_before_publish(kit, monkeypatch):
    row = approve(kit, draft(kit))
    calls = publisher_materializer_stub(kit, monkeypatch)
    out = build_app(kit, row)
    assert calls == ["publish-after-cohort", "materialize"]
    assert out["release_id"] == kb.release_id_for(kit["instance_id"], "APP-03")
    assert out["runtime_document_version"] == "2.0"


@pytest.mark.parametrize("field", ["release_id", "manifest", "runtime_contract", "runtime_document_version"])
def test_publisher_materializer_stub_readback_failure_prevents_materialization(kit, monkeypatch, field):
    row = approve(kit, draft(kit))
    calls = publisher_materializer_stub(kit, monkeypatch, corrupt=field)
    error(lambda: build_app(kit, row), 503, "PROCESS_RELEASE_WRITE_UNAVAILABLE")
    assert calls == ["publish-after-cohort"]


def test_publisher_materializer_stub_checks_returned_dataset_release_ids(kit, monkeypatch):
    row = approve(kit, draft(kit))
    publisher_materializer_stub(kit, monkeypatch, wrong_result=True)
    error(lambda: build_app(kit, row), 503, "PROCESS_MATERIALIZATION_UNAVAILABLE")


def test_stable_release_id_keeps_cohort_across_approved_revisions_publisher_materializer_stub(kit, monkeypatch):
    from core.studio_release_cohort import get_release_cohort
    publisher_materializer_stub(kit, monkeypatch)
    first = build_app(kit, approve(kit, draft(kit)))
    cohort = get_release_cohort(kit["store"], first["release_id"])
    second = build_app(kit, approve(kit, draft(kit, expected_revision=1, app_class="personal")))
    assert second["release_id"] == first["release_id"]
    assert get_release_cohort(kit["store"], second["release_id"]) == cohort


def test_cohort_pin_failure_prevents_publishing(kit, monkeypatch):
    from core import studio_release_cohort as cohorts
    row = approve(kit, draft(kit))
    def failure(*_args, **_kwargs):
        raise ProcessError("PROCESS_RELEASE_COHORT_UNAVAILABLE", "synthetic pin failure", 503)
    monkeypatch.setattr(cohorts, "pin_release_cohort", failure)
    monkeypatch.setattr(kb, "publish_release", lambda **_: pytest.fail("cohort 실패 후 게시"))
    error(lambda: build_app(kit, row), 503, "PROCESS_RELEASE_COHORT_UNAVAILABLE")


def test_legacy_draft_and_approval_cannot_bypass_b2_context(kit):
    error(lambda: kc.draft(kit["store"], blueprint={"app_id": "APP-03", "datasets": ["INV-01"]},
        instance_id=kit["instance_id"], actor_id=org.MEMBER_A, app_class="departmental", **kit["context"]),
        409, "PROCESS_CONTEXT_REQUIRED")
    row = draft(kit)
    error(lambda: kc.approve(kit["store"], instance_id=kit["instance_id"], app_id="APP-03",
        revision=row["revision"], actor_id=org.ADMIN, rationale="구 API 우회 시험"), 409, "PROCESS_CONTEXT_REQUIRED")


def test_old_build_dispatch_does_not_trust_caller_forged_approval(kit, monkeypatch):
    row = draft(kit)
    forged = copy.deepcopy(row["contract"])
    forged["status"] = "APPROVED"
    monkeypatch.setattr(kb, "publish_release", lambda **_: pytest.fail("위조 승인 게시"))
    error(lambda: kb.build(blueprint={"app_id": "APP-03"}, instance_id=kit["instance_id"], outputs=[],
        actor_id=org.MEMBER_A, store=kit["store"], app_data=object(), approved_contract=forged,
        context=kit["context"], repo=kit["svc"].repo, **kit["context"]),
        409, "PROCESS_CONTRACT_APPROVAL_REQUIRED")


def test_real_temp_publisher_materializes_and_retry_reuses_identical_datasets(kit, monkeypatch):
    """실제 publisher/lifecycle/AppData/물질화 경로. 경로·저장소만 임시 주입한다.

    인증 RAW·Host 실행·LLM은 이 시험 범위가 아니다. 실제 생성된 것은 승인 계약의
    읽기 전용 데이터셋 schema/결속과 Preview 후보 release/lifecycle 기록이다.
    """
    from core import paths, library_paths
    from core.app_data import AppDataService, normalize_schema
    from core.app_data_store import AppDataStore
    w = kit
    targets = {name: (w["root"] / name).resolve() for name in (
        "publisher-library", "publisher-data", "publisher-appdata.db", "publisher-lifecycle.db",
        "publisher-workspace.db", "publisher-audit.jsonl")}
    assert all(path.is_relative_to(w["root"]) for path in targets.values())
    # 다른 모듈이 늦게 import돼도 operational data 경로를 만들 수 없게 한정한다.
    monkeypatch.setattr(paths, "DATA_DIR", str(targets["publisher-data"]))
    monkeypatch.setattr(library_paths, "_LIBRARY_DIR", str(targets["publisher-library"]))
    from core import program_lifecycle as lifecycle_module, workspace_promotion as workspace_module
    from core.enterprise_context import audit
    from core.studio_release_cohort import get_release_cohort
    lifecycle = lifecycle_module.ProgramLifecycle(str(targets["publisher-lifecycle.db"]))
    workspace_store = workspace_module.WorkspacePromotion(str(targets["publisher-workspace.db"]))
    monkeypatch.setattr(lifecycle_module, "program_lifecycle", lifecycle)
    monkeypatch.setattr(workspace_module, "workspace", workspace_store)
    monkeypatch.setattr(audit, "_LOG_PATH", str(targets["publisher-audit.jsonl"]))
    data_store = AppDataStore(str(targets["publisher-appdata.db"]))
    plane = AppDataService(data_store)
    assert Path(data_store.db_path).resolve().is_relative_to(w["root"])
    assert Path(lifecycle.db_path).resolve().is_relative_to(w["root"])
    assert Path(workspace_store.db_path).resolve().is_relative_to(w["root"])
    row = approve(w, draft(w))
    first = build_app(w, row, app_data=plane)
    rid = first["release_id"]
    release_path = Path(library_paths.release_json(rid)).resolve()
    assert release_path.is_relative_to(targets["publisher-library"])
    release = json.loads(release_path.read_text(encoding="utf-8"))
    assert release["release_id"] == release["project_id"] == rid
    assert release["instance_id"] == w["instance_id"] and release["app_id"] == "APP-03"
    assert release["runtime_document_version"] == "2.0"
    assert release["runtime_contract"] == row["contract"]
    assert release["manifest"] == app_manifest.snapshot(row["contract"]["manifest"])
    assert release["not_for_management_decision"] is True
    assert release["owner_dept_id"] == org.DEPT_A
    cohort = get_release_cohort(w["store"], rid)
    assert cohort["context_key"] == w["fixed"]["context_key"]
    status = lifecycle.get_status(rid)
    assert status["status"] == lifecycle_module.CANDIDATE and status["recorded"]
    history = lifecycle.history(rid)
    assert len(history) == 1 and history[0]["to_status"] == lifecycle_module.CANDIDATE
    assert history[0]["dependents"]["unmeasured"] == []
    datasets = {dataset["name"]: dataset for dataset in plane.list_datasets(rid)}
    expected = {dataset["name"]: dataset for dataset in row["contract"]["datasets"]}
    assert set(datasets) == set(first["datasets"]) == set(expected)
    assert len(datasets) == len(APP_KEYS)
    bindings = {}
    for name, dataset in datasets.items():
        assert dataset["release_id"] == rid and dataset["app_id"] == rid
        assert dataset["tenant_id"] == w["context"]["tenant_id"]
        expected_schema = normalize_schema({"fields": expected[name]["fields"]})
        assert dataset["schema"] == expected_schema
        binding = plane.binding_for(rid, dataset["dataset_id"])
        assert binding["contract_bound"] and binding["allowed_actions"] == ("read",)
        assert binding["enterprise_contract_key"] == expected[name]["enterprise_contract_key"]
        assert binding["kit_instance_id"] == w["instance_id"]
        # 판은 결속 행이 아니라 version 행에 있다. 런타임 공개 읽기로 봉인 판까지 확인한다.
        bound = plane.find_dataset(rid, name)
        assert bound["dataset_id"] == dataset["dataset_id"]
        assert bound["contract_revision"] == row["revision"]
        assert bound["bound_version_id"] == binding["version_id"]
        assert bound["schema"] == expected_schema and bound["schema_fingerprint"]
        bindings[name] = (dataset["dataset_id"], binding["version_id"])
    assert data_store.scalar("SELECT COUNT(*) FROM app_records") == 0
    second = build_app(w, row, app_data=plane)
    assert second == first
    after = {dataset["name"]: dataset for dataset in plane.list_datasets(rid)}
    assert set(after) == set(datasets)
    assert {name: (dataset["dataset_id"], plane.binding_for(rid, dataset["dataset_id"])["version_id"])
            for name, dataset in after.items()} == bindings
    assert data_store.scalar("SELECT COUNT(*) FROM app_datasets") == len(APP_KEYS)
    assert get_release_cohort(w["store"], rid) == cohort
    assert lifecycle.history(rid) == history
    reread = json.loads(release_path.read_text(encoding="utf-8"))
    assert reread["runtime_contract"] == row["contract"] and reread["runtime_document_version"] == "2.0"
