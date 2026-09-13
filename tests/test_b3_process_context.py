"""B3 독립 계약 시험. 실행은 메인 audit 격리 runner 전용이다.

정상 업무는 실제 후보 팩 load/pin + B1/B2 승인 API로 만든다. 조직은 .invalid,
직접 SQL은 경로를 확인한 tmp DB뿐이다. 인증 시험은 합성 metadata/행의 B0 정책·
서명 경로이며 실제 RAW 파일/운영 데이터/Host 실행 검증으로 보고하지 않는다.
semantic_projection 이름의 시험만 읽기 투영 대역을 사용하며 원문 검증과 구분한다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from core.enterprise_context.process_context import ACTIONS, CONTEXT_KEYS, ProcessContextDTO, ProcessContextService
from core.enterprise_context.process_schema import ProcessError, canonical, fingerprint
from tests import org_seed as org
from tests.test_b1_process_configuration import approval, proposal, workspace  # noqa: F401
from tests.test_b2_installation import installation, _prepared, _apply, _read, _state  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


@pytest.fixture
def configured(workspace, tmp_path):
    from core.data_preparation.store import data_preparation_store
    assert Path(workspace["svc"].repo.db_path).resolve().is_relative_to(tmp_path.resolve())
    approved = approval(workspace, proposal(workspace))
    return {**workspace, "root": tmp_path.resolve(), "approved": approved,
            "ctx": ProcessContextService(workspace["svc"].repo, data_preparation_store)}


@pytest.fixture
def packed(installation):
    w = installation
    prepared = _prepared(w)
    approved = _apply(w, prepared)
    doc = _read(w)["payload"]
    return {**w, "approved": approved, "instance_id": doc["template_sources"][0]["kit_instance_ref"],
            "ids": {n["template_key"]: n["process_id"] for n in doc["nodes"]},
            "ctx": ProcessContextService(w["svc"].repo, w["store"])}


def build(w, ids=None, **overrides):
    args = dict(boundary=w["boundary"], actor=org.MEMBER_A, context=w["context"],
                profile_id=w["approved"]["profile_id"], process_ids=ids if ids is not None else ["plan"])
    return w["ctx"].build(**{**args, **overrides})


def validate(w, fixed, action="DRAFT", **overrides):
    args = dict(fixed_context=fixed, actor=org.MEMBER_A, current_context=w["context"], for_action=action)
    return w["ctx"].revalidate(**{**args, **overrides})


def error(call, status, reason=None):
    with pytest.raises(ProcessError) as exc:
        call()
    assert exc.value.status_code == status
    if reason:
        assert exc.value.reason_code == reason
    return exc.value


@contextmanager
def database(w, name="ecm"):
    path = Path(w["svc"].repo.db_path if name == "ecm" else w["store"].db_path).resolve()
    assert path.is_relative_to(w["root"]) and path.is_file()
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def edit_draft(w, change, mutate):
    """승인 전 시험용 구조 변경. 새 명령 API가 아니라 의미 비교 경계 시험이다."""
    with database(w) as conn:
        row = conn.execute("SELECT payload_json FROM enterprise_profiles WHERE profile_id=?",
                           (change["draft_profile_id"],)).fetchone()
        payload = json.loads(row[0])
        mutate(payload)
        digest = fingerprint(payload)
        conn.execute("UPDATE enterprise_profiles SET payload_json=? WHERE profile_id=?",
                     (canonical(payload), change["draft_profile_id"]))
        conn.execute("UPDATE enterprise_process_changes SET draft_digest=? WHERE change_id=?",
                     (digest, change["change_id"]))
    return {**change, "draft_digest": digest}


def test_approved_custom_context_is_four_key_requirement_draft(configured):
    out = build(configured)
    assert set(out) == set(ProcessContextDTO.model_fields)
    assert set(out["context_key"]) == set(CONTEXT_KEYS)
    assert "configuration_kind" not in out["context_key"]
    assert out["schema_version"] == 1
    assert out["profile_id"] == configured["approved"]["profile_id"]
    assert out["configuration_fingerprint"] == configured["approved"]["digest"]
    assert out["permitted_actions"] == ["READ", "DRAFT", "BOOTSTRAP"]
    assert out["verified_binding_refs"] == []
    assert "PROCESS_REQUIREMENTS_UNRESOLVED" in {b["reason_code"] for b in out["blockers"]}
    assert validate(configured, out) == out


@pytest.mark.parametrize("action", ["READ", "DRAFT", "BOOTSTRAP"])
def test_no_data_allows_only_nonmaterializing_actions(configured, action):
    assert validate(configured, build(configured), action)["verified_binding_refs"] == []


@pytest.mark.parametrize("action", ["GENERATE", "RUN", "RELEASE"])
def test_no_data_does_not_authorize_runtime_contract_or_host(configured, action):
    error(lambda: validate(configured, build(configured), action, actor=org.MANAGER_A), 409)


@pytest.mark.parametrize("ids", [[], ["plan", "plan"], [123], "plan", [""], ["x" * 161]])
def test_selection_is_explicit_strict_and_bounded(configured, ids):
    error(lambda: build(configured, ids), 422, "PROCESS_CONTEXT_INVALID")


def test_approved_profile_id_cannot_fall_back_to_head_or_draft(configured):
    error(lambda: build(configured, profile_id=""), 422)
    draft = proposal(configured, [{"op": "RENAME", "process_id": "plan", "label": "미승인"}], "unapproved")
    error(lambda: build(configured, profile_id=draft["draft_profile_id"]), 404)
    error(lambda: build(configured, profile_id="not-in-this-configuration"), 404)
    error(lambda: build(configured, ["not-in-this-profile"]), 409, "PROCESS_SELECTION_CONFLICT")


def test_selection_order_is_canonical_but_membership_is_semantic(configured):
    assert build(configured, ["plan", "purchase"]) == build(configured, ["purchase", "plan"])
    assert build(configured)["process_semantic_fingerprint"] != build(configured, ["purchase"])["process_semantic_fingerprint"]


def test_label_change_keeps_historical_profile_and_semantic_fingerprint(configured):
    w = configured
    fixed = build(w)
    newer = approval(w, proposal(w, [{"op": "RENAME", "process_id": "plan", "label": "표시명만 변경"}], "label"))
    current = build(w, profile_id=newer["profile_id"])
    assert current["configuration_fingerprint"] != fixed["configuration_fingerprint"]
    assert current["process_semantic_fingerprint"] == fixed["process_semantic_fingerprint"]
    assert validate(w, fixed) == fixed


def test_shortcut_order_hidden_and_note_do_not_change_semantics(configured):
    w = configured
    fixed = build(w)
    draft = proposal(w, [{"op": "ADD_NODE", "node": {"process_id": "sales", "level": "L1", "label": "판매"}},
                         {"op": "ADD_SHORTCUT", "process_id": "plan", "parent_process_id": "sales"}], "display")
    def mutate(doc):
        doc["nodes"].reverse()
        doc["nodes"][0]["note"] = "표시 설명 — 권한 지시가 아님"
        for placement in doc["placements"]:
            placement["position"] += 10
            placement["hidden"] = True
    approval(w, edit_draft(w, draft, mutate))
    assert validate(w, fixed) == fixed


@pytest.mark.parametrize("target", ["plan", "purchase"])
def test_selected_or_ancestor_disabled_blocks_even_draft(configured, target):
    fixed = build(configured)
    approval(configured, proposal(configured, [{"op": "SET_USAGE", "process_id": target, "enabled": False}], "off"))
    error(lambda: validate(configured, fixed), 409, "PROCESS_DISABLED")


def test_an_unselected_process_change_does_not_invalidate_selection(configured):
    fixed = build(configured)
    approval(configured, proposal(configured, [{"op": "ADD_NODE", "node": {"process_id": "other", "level": "L1", "label": "다른 업무"}}], "extra"))
    approval(configured, proposal(configured, [{"op": "SET_USAGE", "process_id": "other", "enabled": False}], "other-off"))
    assert validate(configured, fixed) == fixed


def test_reparenting_changes_ancestor_semantics(configured):
    w = configured
    fixed = build(w)
    approval(w, proposal(w, [{"op": "ADD_NODE", "node": {"process_id": "new-parent", "level": "L1", "label": "새 상위"}},
                            {"op": "MOVE_NODE", "process_id": "plan", "parent_process_id": "new-parent"}], "move"))
    error(lambda: validate(w, fixed), 409, "PROCESS_SEMANTIC_CONFLICT")


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version=True),
    lambda d: d.update(schema_version=2),
    lambda d: d.update(approved_by=org.ADMIN),
    lambda d: d["context_key"].update(configuration_kind="business_process"),
    lambda d: d["context_key"].pop("scope_node_id"),
    lambda d: d.update(process_ids=["plan", "plan"]),
])
def test_fixed_dto_cannot_smuggle_unversioned_fields(configured, mutation):
    fixed = build(configured)
    mutation(fixed)
    error(lambda: validate(configured, fixed), 422, "PROCESS_CONTEXT_INVALID")


@pytest.mark.parametrize("field", ["configuration_id", "configuration_fingerprint", "process_semantic_fingerprint"])
def test_immutable_dto_fields_are_rebuilt_from_server(configured, field):
    fixed = build(configured)
    fixed[field] = "0" * 64
    error(lambda: validate(configured, fixed), 409, "PROCESS_CONTEXT_CONFLICT")


def test_forged_permitted_actions_are_never_used(configured):
    fixed = build(configured)
    fixed["permitted_actions"] = list(ACTIONS)
    fixed["blockers"] = []
    assert validate(configured, fixed)["permitted_actions"] == ["READ", "DRAFT", "BOOTSTRAP"]
    error(lambda: validate(configured, fixed, "RUN"), 409)
    error(lambda: validate(configured, fixed, "EXECUTE"), 422)


@pytest.mark.parametrize("context_update", [
    {"tenant_id": "tenant_other"}, {"entity_mode": "VIRTUAL"},
    {"scope_node_id": "other-root"}, {"context_root_id": "other-root"}, {"scope_node_id": ""},
])
def test_current_context_mismatch_is_hidden_even_for_admin(configured, context_update):
    fixed = build(configured)
    exc = error(lambda: validate(configured, fixed, actor=org.ADMIN,
                                current_context={**configured["context"], **context_update}), 404, "PROCESS_NOT_FOUND")
    assert fixed["profile_id"] not in str(exc)


def test_fresh_authority_rechecks_another_directory_connection(configured):
    from core.org_directory import OrgDirectory, org_directory
    w = configured
    fixed = build(w)
    path = Path(org_directory.db_path).resolve()
    assert path.is_relative_to(w["root"])
    other = OrgDirectory(str(path))
    other.set_user_roles(org.MEMBER_A, {org.DEPT_B: "member"}, actor="test")
    # 기본 소속 A는 역할 회수와 별개로 읽기를 유지한다(org_directory.resolve_scope).
    # 다른 연결의 변경을 fresh로 읽어 A의 쓰기만 철회했는지 함께 검증한다.
    fresh = org_directory.resolve_scope(org.MEMBER_A, fresh=True)
    assert fresh.primary_dept_id == org.DEPT_A and fresh.can_read(org.DEPT_A)
    assert org.DEPT_A not in fresh.writable_dept_ids
    assert validate(w, fixed, "READ")["profile_id"] == fixed["profile_id"]
    error(lambda: validate(w, fixed), 403, "PROCESS_ACTION_FORBIDDEN")


def test_fresh_authority_hides_profile_after_primary_and_role_scope_removed(configured):
    from core.org_directory import OrgDirectory, org_directory
    w = configured
    fixed = build(w)
    path = Path(org_directory.db_path).resolve()
    assert path.is_relative_to(w["root"])
    other = OrgDirectory(str(path))
    other.set_user_roles(org.MEMBER_A, {org.DEPT_B: "member"}, actor="test")
    user = other.get_user(org.MEMBER_A)
    other.upsert_user(org.MEMBER_A, user["display_name"], primary_dept_id=org.DEPT_B, actor="test")
    fresh = org_directory.resolve_scope(org.MEMBER_A, fresh=True)
    assert not fresh.can_read(org.DEPT_A)
    exc = error(lambda: validate(w, fixed, "READ"), 404, "PROCESS_NOT_FOUND")
    assert fixed["profile_id"] not in str(exc)


def test_retired_actor_is_not_resurrected_by_fixed_context(configured):
    from core.org_directory import org_directory
    w = configured
    fixed = build(w)
    path = Path(org_directory.db_path).resolve()
    assert path.is_relative_to(w["root"])
    with sqlite3.connect(str(path)) as conn:
        conn.execute("UPDATE users SET status='inactive' WHERE user_id=?", (org.MEMBER_A,))
    error(lambda: validate(w, fixed), 403, "PROCESS_ACTOR_INELIGIBLE")


def test_saved_profile_schema_damage_is_unavailable_not_empty(configured):
    w = configured
    with database(w) as conn:
        conn.execute("DROP TRIGGER process_profile_immutable_update")
        conn.execute("UPDATE enterprise_profiles SET payload_json='{}' WHERE profile_id=?", (w["approved"]["profile_id"],))
    error(lambda: build(w), 503, "PROCESS_PROFILE_UNAVAILABLE")


def test_candidate_pack_context_is_read_only_and_keeps_unresolved_requirements(packed):
    w = packed
    before = _state(w)
    out = build(w, [w["ids"]["sourcing.plan"]])
    assert _state(w) == before
    assert out["verified_binding_refs"] == []
    assert out["permitted_actions"] == ["READ", "DRAFT", "BOOTSTRAP"]
    assert any(r["unresolved_requirement"] and not r["candidate_contract_keys"] for r in out["data_requirements"])
    pack = out["sources"][1]
    assert pack["artifact_digest"] == w["bundle"]["artifact_digest"]
    assert pack["pack_digest"] == w["bundle"]["pack_digest"]
    assert pack["instance_id"] == w["instance_id"]
    assert validate(w, out)["profile_id"] == out["profile_id"]
    assert _state(w) == before


def test_pack_label_change_does_not_replace_historical_sources(packed):
    w = packed
    pid = w["ids"]["sourcing.contract"]
    fixed = build(w, [pid])
    newer = approval(w, proposal(w, [{"op": "RENAME", "process_id": pid, "label": "우리 회사 계약업무"}], "pack-label"))
    assert build(w, [pid], profile_id=newer["profile_id"])["process_semantic_fingerprint"] == fixed["process_semantic_fingerprint"]
    assert validate(w, fixed)["sources"] == fixed["sources"]


def test_approved_requirement_change_is_semantic_conflict(packed):
    w = packed
    pid = w["ids"]["sourcing.contract"]
    fixed = build(w, [pid])
    draft = proposal(w, [{"op": "RENAME", "process_id": pid, "label": "요구 변경 시험"}], "requirement")
    def mutate(doc):
        ref = next(b for b in doc["bindings"] if b["kind"] == "DATA_REQUIREMENT" and b["process_id"] == pid)
        ref["mandatory"] = not ref["mandatory"]
    approval(w, edit_draft(w, draft, mutate))
    error(lambda: validate(w, fixed), 409, "PROCESS_SEMANTIC_CONFLICT")


@pytest.mark.parametrize("field", ["purpose", "input_roles", "output_roles"])
def test_semantic_projection_purpose_and_io_change_hash(packed, monkeypatch, field):
    """의미 정규화 단위 시험. 원문 재검증을 대역으로 통과했다고 세지 않는다."""
    from core.data_preparation import process_pack_artifacts as packs
    w = packed
    ids = [w["ids"]["sourcing.contract"]]
    payload = _read(w)["payload"]
    baseline = w["ctx"]._describe(payload, ids, w["boundary"])["semantic"]
    changed = copy.deepcopy(w["bundle"])
    template = next(t for t in changed["pack"]["templates"] if t["template_key"] == "sourcing.contract")
    template[field] = "의미 수정" if field == "purpose" else ["의미 수정"]
    monkeypatch.setattr(packs, "get_bundle", lambda *args: changed)
    assert w["ctx"]._describe(payload, ids, w["boundary"])["semantic"] != baseline


def test_semantic_projection_raw_display_hash_is_not_business_meaning(packed, monkeypatch):
    from core.data_preparation import process_pack_artifacts as packs
    w = packed
    ids = [w["ids"]["sourcing.contract"]]
    payload = _read(w)["payload"]
    baseline = w["ctx"]._describe(payload, ids, w["boundary"])["semantic"]
    changed = copy.deepcopy(w["bundle"])
    changed["pack_digest"] = "1" * 64
    changed["artifact_digest"] = "2" * 64
    for template in changed["pack"]["templates"]:
        template["label"] += " 표시 수정"
    source = payload["template_sources"][0]
    source["artifact_digest"] = changed["artifact_digest"]
    source["accepted_standard_digest"] = changed["pack_digest"]
    monkeypatch.setattr(packs, "get_bundle", lambda *args: changed)
    assert w["ctx"]._describe(payload, ids, w["boundary"])["semantic"] == baseline


@pytest.mark.parametrize("fault,expected", [("inactive", 409), ("identity", 503), ("tenant", 404)])
def test_exact_instance_cannot_be_replaced_by_same_named_kit(packed, fault, expected):
    w = packed
    fixed = build(w, [w["ids"]["sourcing.contract"]])
    with database(w, "dp") as conn:
        column, value = {"inactive": ("status", "retired"), "identity": ("kit_fingerprint", "0" * 64),
                         "tenant": ("tenant_id", "other-tenant")}[fault]
        conn.execute(f"UPDATE kit_instances SET {column}=? WHERE instance_id=?", (value, w["instance_id"]))
    error(lambda: validate(w, fixed), expected)


def test_pinned_artifact_corruption_is_503_without_registry_fallback(packed):
    w = packed
    with database(w, "dp") as conn:
        triggers = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='kit_process_artifacts'").fetchall()
        for trigger in triggers:
            conn.execute('DROP TRIGGER "' + trigger[0].replace('"', '""') + '"')
        conn.execute("UPDATE kit_process_artifacts SET bundle_json='{}' WHERE artifact_digest=?", (w["bundle"]["artifact_digest"],))
    error(lambda: build(w, [w["ids"]["sourcing.contract"]]), 503, "PROCESS_ARTIFACT_CORRUPT")


def add_certified(w, contract, *, existing_binding=None, use="OPERATIONAL"):
    """합성 행만 사용한 B0 메타데이터·정책·서명 시험. RAW 파일은 만들지 않는다."""
    from core.data_preparation import certification_subject as cs, models as m, ownership_binding as ob
    from core.data_preparation import snapshot_service as snapshots
    store = w["store"]
    if existing_binding is None:
        binding = store.create_binding(instance_id=w["instance_id"], dataset_contract_key=contract,
                                       provider=m.PROVIDER_FILE_SNAPSHOT, config={}, created_by=org.MANAGER_A, **w["context"])
        for state in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            binding = store.transition(binding["binding_id"], state)
        args = dict(**w["context"], dataset_contract_key=contract, owner_dept_id=org.DEPT_A,
                    evidence_ref="test-only-b3-owner-approval")
        approved = ob.approve(**args, actor_id=org.ADMIN)
        with store.transaction() as conn:
            ob.declare(conn, **args, approved_by=org.ADMIN, approval_event_id=approved["approval_event_id"],
                       effective_from=approved["effective_from"])
    else:
        binding = existing_binding
    raw = b"amount\n1\n"
    snap = store.create_snapshot(instance_id=w["instance_id"], binding_id=binding["binding_id"],
        dataset_contract_key=contract, data_kind=m.DATA_KIND_REAL, checksum=hashlib.sha256(raw).hexdigest(),
        content_fingerprint=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), row_count=1,
        schema=["amount"], created_by=org.MANAGER_A, **w["context"])
    sid, rows = snap["snapshot_id"], [{"amount": "1"}]
    snapshots.profile(store, sid, rows, ["amount"])
    snapshots.standardize(store, sid, rows)
    snapshots.reconcile(store, sid, rows, {"row_count": 1})
    args = dict(actor=org.MANAGER_A, context=w["context"], use_kind=use,
                period_from="2026-08-01", period_to="2026-08-31")
    preview = cs.preview(store, sid, **args)
    result = cs.sign(store, sid, **args, review_kind="DATA_OWNER", reconciliation_evidence="합성 원천 총계 대사 일치 확인",
                     subject_id=preview["subject_id"], expected_subject_digest=preview["digest"], client_request_id="b3-owner")
    assert result["certified"]
    return {"binding": binding, "snapshot_id": sid, "subject": preview}


@pytest.fixture
def certified(packed, monkeypatch):
    from core.data_preparation import certification_authority as ca
    from core.decision_ledger import decision_ledger
    w = packed
    monkeypatch.setattr(decision_ledger, "db_path", str(w["root"] / "b3-ledger.db"))
    monkeypatch.setattr(decision_ledger, "_prepared_for", None)
    policy_doc = {"required_reviews": {"OPERATIONAL": ["DATA_OWNER"], "MANAGEMENT": ["DATA_OWNER", "EXECUTIVE"]},
        "grants": {"DATA_OWNER": [{"dept_id": org.DEPT_A, "role": "manager", "scope_node_id": org.NODES[org.DEPT_A]}],
                   "EXECUTIVE": [{"dept_id": org.DEPT_ROOT, "role": "viewer", "scope_node_id": org.NODES[org.DEPT_ROOT]}]},
        "delegations": [], "allow_same_actor": False, "min_evidence_length": 10}
    policy = ca.approve_policy(w["store"], tenant_id=w["context"]["tenant_id"], entity_mode="REAL",
        context_root_id=w["boundary"].context_root_id, actor=org.ADMIN, evidence_ref="test-only-b3-policy", document=policy_doc)
    data = {key: add_certified(w, key) for key in ("MDM-08", "PRC-01")}
    return {**w, "data": data, "policy": policy, "policy_document": policy_doc, "ledger": decision_ledger}


def contract_context(w):
    return build(w, [w["ids"]["sourcing.contract"]])


def test_verified_refs_are_exact_instance_contract_binding_snapshot_and_policy(certified):
    w = certified
    before = _state(w)
    out = contract_context(w)
    refs = out["verified_binding_refs"]
    assert [ref["contract_key"] for ref in refs] == ["MDM-08", "PRC-01"]
    for ref in refs:
        source = w["data"][ref["contract_key"]]
        assert ref["instance_id"] == w["instance_id"]
        assert ref["artifact_digest"] == w["bundle"]["artifact_digest"]
        assert ref["binding_id"] == source["binding"]["binding_id"]
        assert ref["snapshot_id"] == source["snapshot_id"]
        assert ref["certification_subject_id"] == source["subject"]["subject_id"]
        assert ref["signing_policy_digest"] == w["policy"]["digest"]
        assert ref["certified_use_kind"] == "OPERATIONAL"
        assert "hold_revision" not in ref and "raw_path" not in ref
    assert {b["reason_code"] for b in out["blockers"]} == {"PROCESS_ACTION_FORBIDDEN"}
    assert out["permitted_actions"] == [a for a in ACTIONS if a != "RELEASE"]
    assert validate(w, out, "GENERATE") == out
    assert _state(w) == before


@pytest.mark.parametrize("actor,expected", [
    (org.VIEWER_A, ["READ", "RUN"]),
    (org.MEMBER_A, ["READ", "DRAFT", "BOOTSTRAP", "GENERATE", "RUN"]),
    (org.MANAGER_A, list(ACTIONS)),
])
def test_permitted_actions_intersect_current_capabilities_and_process_scope(certified, actor, expected):
    out = build(certified, [certified["ids"]["sourcing.contract"]], actor=actor)
    assert out["permitted_actions"] == expected
    for action in ACTIONS:
        if action in expected:
            assert validate(certified, out, action, actor=actor)["permitted_actions"] == expected
        else:
            error(lambda: validate(certified, out, action, actor=actor), 403, "PROCESS_ACTION_FORBIDDEN")


def test_manager_in_other_scope_does_not_grant_local_propose_or_generate(certified):
    from core.org_directory import org_directory
    w = certified
    org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer", org.DEPT_B: "manager"}, actor="test")
    out = contract_context(w)
    assert "DRAFT" not in out["permitted_actions"] and "GENERATE" not in out["permitted_actions"]
    assert "RUN" in out["permitted_actions"]
    error(lambda: validate(w, out, "BOOTSTRAP"), 403)


def test_function_capability_revocation_refreshes_permissions_in_saved_context(certified):
    from core.org_directory import org_directory
    w = certified
    fixed = contract_context(w)
    org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
    assert validate(w, fixed, "READ")["permitted_actions"] == ["READ", "RUN"]
    error(lambda: validate(w, fixed, "DRAFT"), 403, "PROCESS_ACTION_FORBIDDEN")


def test_fixed_snapshot_does_not_silently_select_later_certified_version(certified):
    w = certified
    old = contract_context(w)
    before = w["data"]["PRC-01"]
    new = add_certified(w, "PRC-01", existing_binding=before["binding"])
    assert new["snapshot_id"] != before["snapshot_id"]
    assert validate(w, old, "RUN")["verified_binding_refs"] == old["verified_binding_refs"]
    assert contract_context(w)["verified_binding_refs"] != old["verified_binding_refs"]


def test_source_certified_state_without_pinned_origin_proof_is_not_verified(certified):
    w = certified
    fixed = contract_context(w)
    with database(w, "dp") as conn:
        conn.execute("UPDATE dataset_snapshots SET state='SOURCE_CERTIFIED' WHERE snapshot_id=?",
                     (w["data"]["PRC-01"]["snapshot_id"],))
    rebuilt = contract_context(w)
    assert "PRC-01" not in {ref["contract_key"] for ref in rebuilt["verified_binding_refs"]}
    assert "PROCESS_SOURCE_REVALIDATION_REQUIRED" in {b["reason_code"] for b in rebuilt["blockers"]}
    assert "DRAFT" in rebuilt["permitted_actions"] and "GENERATE" not in rebuilt["permitted_actions"]
    error(lambda: validate(w, fixed, "RUN"), 409, "PROCESS_SOURCE_REVALIDATION_REQUIRED")


def test_new_data_requires_explicit_rebuild_not_automatic_draft_rebinding(certified):
    w = certified
    old = contract_context(w)
    # 서버가 저장했던 무데이터 DTO를 모사: 의미/승인판은 동일하고 참조는 아직 없음.
    old["verified_binding_refs"] = []
    old["permitted_actions"] = ["READ", "DRAFT", "BOOTSTRAP"]
    out = validate(w, old)
    assert out["verified_binding_refs"] == []
    assert "PROCESS_BINDING_REFRESH_REQUIRED" in {b["reason_code"] for b in out["blockers"]}
    error(lambda: validate(w, old, "GENERATE"), 409)


@pytest.mark.parametrize("held", [False, True])
def test_forged_fixed_ref_is_rejected_even_while_usage_is_held(certified, held):
    w = certified
    fixed = contract_context(w)
    if held:
        with database(w, "dp") as conn:
            conn.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
                         (canonical({"usage_holds": ["REHEARSAL_ONLY"]}), w["data"]["MDM-08"]["binding"]["binding_id"]))
    fixed["verified_binding_refs"][0]["checksum"] = "0" * 64
    error(lambda: validate(w, fixed), 409, "PROCESS_BINDING_CONFLICT")


def test_current_hold_blocks_runtime_but_preserves_verified_historical_draft(certified):
    w = certified
    fixed = contract_context(w)
    with database(w, "dp") as conn:
        conn.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
                     (canonical({"usage_holds": ["PRICE_VINTAGE_AND_CONVERSION_POLICY_REQUIRED"]}),
                      w["data"]["MDM-08"]["binding"]["binding_id"]))
    draft = validate(w, fixed)
    assert draft["verified_binding_refs"] == fixed["verified_binding_refs"]
    assert draft["permitted_actions"] == ["READ", "DRAFT", "BOOTSTRAP"]
    assert "DATA_USAGE_HOLD" in {b["reason_code"] for b in draft["blockers"]}
    error(lambda: validate(w, fixed, "RUN"), 409, "DATA_USAGE_HOLD")
    before = _state(w)
    rebuilt = contract_context(w)
    assert len(rebuilt["verified_binding_refs"]) == 1
    assert _state(w) == before


@pytest.mark.parametrize("config", ["{bad-json", "[]", '{"usage_holds":true}'])
def test_unreadable_usage_policy_is_503_not_permitted_draft(certified, config):
    w = certified
    with database(w, "dp") as conn:
        conn.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
                     (config, w["data"]["PRC-01"]["binding"]["binding_id"]))
    error(lambda: contract_context(w), 503, "USAGE_POLICY_UNREADABLE")


def test_completed_owner_certification_rechecks_current_signer_eligibility(certified):
    from core.org_directory import org_directory
    w = certified
    fixed = contract_context(w)
    org_directory.set_user_roles(org.MANAGER_A, {org.DEPT_A: "member"}, actor="test")
    error(lambda: validate(w, fixed, "RUN"), 409, "SIGNER_INELIGIBLE")
    rebuilt = contract_context(w)
    assert rebuilt["verified_binding_refs"] == []
    assert "SIGNER_INELIGIBLE" in {b["reason_code"] for b in rebuilt["blockers"]}


def test_completed_owner_certification_rechecks_current_company_policy(certified):
    from core.data_preparation import certification_authority as ca
    w = certified
    fixed = contract_context(w)
    doc = copy.deepcopy(w["policy_document"])
    doc["min_evidence_length"] += 1
    ca.approve_policy(w["store"], tenant_id=w["context"]["tenant_id"], entity_mode="REAL",
        context_root_id=w["boundary"].context_root_id, actor=org.ADMIN, evidence_ref="test-only-b3-policy-change",
        document=doc, expected_policy_id=w["policy"]["policy_id"])
    error(lambda: validate(w, fixed, "RUN"), 409, "REVIEW_STALE")


def test_completed_owner_certification_rechecks_revoked_ownership(certified):
    from core.data_preparation import ownership_binding as ob
    w = certified
    fixed = contract_context(w)
    with w["store"].transaction() as conn:
        ob.revoke(conn, fixed["verified_binding_refs"][0]["ownership_binding_id"], org.ADMIN, "test-only-owner-revoke")
    error(lambda: validate(w, fixed, "RUN"), 409, "OWNERSHIP_REQUIRED")


def test_retired_binding_cannot_rebind_to_latest_same_contract(certified):
    from core.data_preparation import models as m
    w = certified
    fixed = contract_context(w)
    replacement = w["store"].create_binding(instance_id=w["instance_id"], dataset_contract_key="PRC-01",
        provider=m.PROVIDER_FILE_SNAPSHOT, config={"new_source": True}, created_by=org.MANAGER_A, **w["context"])
    for stage in (m.VALIDATED, m.APPROVED, m.ACTIVE):
        w["store"].transition(replacement["binding_id"], stage)
    error(lambda: validate(w, fixed, "RUN"), 409, "PROCESS_BINDING_CONFLICT")


def test_revoked_fixed_snapshot_cannot_fall_back_to_another_version(certified):
    from core.data_preparation import models as m
    w = certified
    fixed = contract_context(w)
    row = w["data"]["PRC-01"]
    add_certified(w, "PRC-01", existing_binding=row["binding"])
    w["store"].advance_snapshot(row["snapshot_id"], m.REVOKED)
    error(lambda: validate(w, fixed, "RUN"), 409, "CERTIFIED_SNAPSHOT_REQUIRED")


def test_snapshot_identity_spoof_is_404_before_details(certified):
    w = certified
    fixed = contract_context(w)
    with database(w, "dp") as conn:
        conn.execute("UPDATE dataset_snapshots SET tenant_id='secret-other-tenant' WHERE snapshot_id=?",
                     (w["data"]["PRC-01"]["snapshot_id"],))
    exc = error(lambda: validate(w, fixed, "RUN"), 404, "PROCESS_NOT_FOUND")
    assert "secret-other-tenant" not in str(exc)


def test_metadata_corruption_after_certification_cannot_keep_old_proof(certified):
    w = certified
    fixed = contract_context(w)
    with database(w, "dp") as conn:
        conn.execute("UPDATE dataset_snapshots SET checksum=? WHERE snapshot_id=?",
                     ("0" * 64, w["data"]["PRC-01"]["snapshot_id"]))
    error(lambda: validate(w, fixed, "RUN"), 409, "REVIEW_STALE")


def test_changed_head_during_data_read_is_rechecked(configured, monkeypatch):
    w = configured
    fixed = build(w)
    original = w["ctx"]._data
    def disable_after_read(*args, **kwargs):
        out = original(*args, **kwargs)
        approval(w, proposal(w, [{"op": "SET_USAGE", "process_id": "plan", "enabled": False}], "raced-head"))
        return out
    monkeypatch.setattr(w["ctx"], "_data", disable_after_read)
    error(lambda: validate(w, fixed), 409, "PROCESS_DISABLED")
