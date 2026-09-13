"""키트 명시 반려: 실행은 main audit 격리 runner 전용이다.

2.0은 기존 실제 후보팩/B0 인증 metadata fixture를 사용한다. 1.0은 합성 registry와
schema reader 대역을 명시한 계약 흐름 시험이며 실제 인증·RAW·Host/LLM 시험이 아니다.
모든 계정은 org_seed의 .invalid, 저장소는 검증한 tmp 경로만 사용한다.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from core import kit_app_contract as kc, kit_app_builder as kb, app_runtime_contract as arc
from core.enterprise_context.process_schema import ProcessError
from tests import org_seed as org
from tests.test_b1_process_configuration import workspace  # noqa: F401
from tests.test_b2_installation import installation  # noqa: F401
from tests.test_b3_kit_contract_v2 import kit, draft as draft_v2, approve as approve_v2, build_app, hold  # noqa: F401
from tests.test_b3_process_context import database, error
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


@pytest.fixture(params=["1.0", "2.0"])
def review_case(request, workspace, tmp_path, monkeypatch):
    if request.param == "2.0":
        return {**request.getfixturevalue("kit"), "document_version": "2.0", "app_id": "APP-03"}
    from core.data_preparation.store import data_preparation_store as store
    from core.decision_ledger import decision_ledger
    root = tmp_path.resolve()
    assert Path(store.db_path).resolve().is_relative_to(root)
    assert Path(workspace["svc"].repo.db_path).resolve().is_relative_to(root)
    monkeypatch.setattr(decision_ledger, "db_path", str(root / "rejection-ledger.db"))
    monkeypatch.setattr(decision_ledger, "_prepared_for", None)
    assert Path(decision_ledger.db_path).resolve().is_relative_to(root)
    store.upsert_kit_version(kit_id="TEST-REJECTION", version="1.0", name="합성 반려 계약 fixture",
        mode="REAL", source_path="test-only", fingerprint_value="test-rejection-original",
        profile={"kit_id": "TEST-REJECTION", "version": "1.0"})
    instance = store.create_instance(kit_id="TEST-REJECTION", version="1.0",
        kit_fingerprint="test-rejection-original", label="합성 반려 시험", created_by=org.MEMBER_A,
        **workspace["context"])
    # 인증을 대역 성공으로 주장하지 않는다. 이 legacy 시험은 schema 제공 이후 계약 검토 경계다.
    monkeypatch.setattr(kb, "fields_from_certified", lambda *_: [{"name": "amount", "type": "number"}])
    return {**workspace, "root": root, "store": store, "ledger": decision_ledger,
            "instance_id": instance["instance_id"], "document_version": "1.0", "app_id": "APP-LEGACY",
            "blueprint": {"app_id": "APP-LEGACY", "datasets": ["PRC-01"]}}


def save(w, **changes):
    if w["document_version"] == "2.0":
        return draft_v2(w, **changes)
    changes.pop("expected_revision", None)
    args = dict(blueprint=w["blueprint"], instance_id=w["instance_id"], actor_id=org.MEMBER_A,
                app_class="departmental", **w["context"])
    return kc.draft(w["store"], **{**args, **changes})


def approve(w, row, **changes):
    if w["document_version"] == "2.0":
        return approve_v2(w, row, **changes)
    args = dict(instance_id=w["instance_id"], app_id=w["app_id"], revision=row["revision"],
                actor_id=org.ADMIN, rationale="합성 계약 독립 승인")
    return kc.approve(w["store"], **{**args, **changes})


def reject(w, row, **changes):
    fn = kc.reject_v2 if w["document_version"] == "2.0" else kc.reject
    args = dict(instance_id=w["instance_id"], app_id=w["app_id"], revision=row["revision"],
        expected_fingerprint=row["semantic_fingerprint"], actor_id=org.ADMIN, context=w["context"],
        rationale="입력 범위와 결과 설명을 보완해 다시 제안하십시오.", repo=w["svc"].repo)
    return fn(w["store"], **{**args, **changes})


def stored(w, row):
    with database(w, "dp") as conn:
        return dict(conn.execute("SELECT * FROM kit_app_contracts WHERE contract_row_id=?",
                                 (row["contract_row_id"],)).fetchone())


def rejection_events(w, row):
    return w["ledger"].list_events(event_type=kc.EVENT_REJECTED, subject_type=kc.SUBJECT_TYPE,
                                    subject_id=row["semantic_fingerprint"])


def test_rejection_preserves_original_bytes_and_records_real_ledger(review_case):
    w = review_case
    row = save(w)
    before = stored(w, row)
    rejected = reject(w, row)
    after = stored(w, row)
    assert rejected["status"] == "REJECTED" and rejected["contract"] == row["contract"]
    assert after["contract_json"].encode() == before["contract_json"].encode()
    assert after["semantic_fingerprint"] == before["semantic_fingerprint"]
    assert not after["approved_by"] and not after["approved_at"]
    assert arc.validate(rejected["contract"]) == [] and arc.SCHEMA_VERSION == "1.0"
    event = w["ledger"].get_event_strict(after["ledger_event_id"])
    assert event["event_type"] == "APP_CONTRACT_REJECTED" and event["decision"] == "REJECTED"
    assert event["subject_type"] == "app_contract" and event["subject_id"] == row["semantic_fingerprint"]
    assert event["actor_id"] == org.ADMIN and event["actor_id"] != row["drafted_by"]
    assert event["tenant_id"] == w["context"]["tenant_id"]
    assert event["enterprise_scope_id"] == w["context"]["scope_node_id"]
    assert rejected["rejection"]["decision_ledger_id"] == event["event_id"]
    assert rejected["rejection"]["rationale"] == event["rationale"]


def test_same_rejection_replays_and_same_content_redraft_gets_new_revision(review_case):
    w = review_case
    row = save(w)
    rejected = reject(w, row)
    assert reject(w, row) == rejected
    second = save(w, expected_revision=row["revision"])
    assert second["revision"] == row["revision"] + 1 and second["status"] == "DRAFT"
    assert second["semantic_fingerprint"] == row["semantic_fingerprint"]
    assert reject(w, row) == rejected  # 완료한 검토 재조회는 새 초안을 반려하지 않는다.
    assert len(rejection_events(w, row)) == 1
    assert kc.latest(w["store"], w["instance_id"], w["app_id"])["revision"] == second["revision"]


def test_replay_with_different_actor_or_rationale_conflicts(review_case):
    w = review_case
    row = save(w)
    reject(w, row)
    before = stored(w, row)
    error(lambda: reject(w, row, rationale="다른 반려 사유"), 409, "PROCESS_CONTRACT_CONFLICT")
    error(lambda: reject(w, row, actor_id=org.DATA_ADMIN), 409, "PROCESS_CONTRACT_CONFLICT")
    assert stored(w, row) == before and len(rejection_events(w, row)) == 1


def test_rejection_validates_revision_fingerprint_and_reason(review_case):
    w = review_case
    row = save(w)
    for args in ({"revision": True}, {"expected_fingerprint": "bad"}, {"rationale": " "}):
        error(lambda: reject(w, row, **args), 422, "PROCESS_CONTRACT_INVALID")
    error(lambda: reject(w, row, expected_fingerprint="0" * 64), 409, "PROCESS_CONTRACT_CONFLICT")
    assert stored(w, row)["status"] == "DRAFT" and rejection_events(w, row) == []


def test_member_and_self_review_cannot_reject(review_case):
    w = review_case
    row = save(w, actor_id=org.ADMIN)
    error(lambda: reject(w, row, actor_id=org.MEMBER_A), 403, "PROCESS_ACTION_FORBIDDEN")
    error(lambda: reject(w, row, actor_id=org.ADMIN), 403, "PROCESS_DISTINCT_REVIEWER_REQUIRED")
    assert stored(w, row)["status"] == "DRAFT" and rejection_events(w, row) == []


def test_cross_boundary_is_hidden_without_ledger_or_state_change(review_case):
    w = review_case
    row = save(w)
    for changed in ({"tenant_id": "other-tenant"}, {"entity_mode": "VIRTUAL"},
                    {"scope_node_id": org.NODES[org.DEPT_B]}, {"context_root_id": "other-root"}):
        exc = error(lambda: reject(w, row, context={**w["context"], **changed}), 404)
        assert row["contract_row_id"] not in str(exc)
    assert stored(w, row)["status"] == "DRAFT" and rejection_events(w, row) == []


def test_only_latest_draft_can_be_rejected(review_case):
    w = review_case
    first = save(w)
    second = save(w, expected_revision=first["revision"], app_class="personal")
    assert second["revision"] == first["revision"] + 1
    error(lambda: reject(w, first), 409, "PROCESS_CONTRACT_CONFLICT")
    assert stored(w, first)["status"] == "DRAFT" and rejection_events(w, first) == []


def test_rejecting_new_draft_cannot_change_existing_approved_revision(review_case):
    w = review_case
    first = approve(w, save(w))
    before = stored(w, first)
    error(lambda: reject(w, first), 409, "PROCESS_CONTRACT_CONFLICT")
    newer = save(w, expected_revision=first["revision"], app_class="personal")
    reject(w, newer)
    assert stored(w, first) == before
    assert kc.approved(w["store"], w["instance_id"], w["app_id"])["revision"] == first["revision"]


def test_rejected_revision_cannot_be_approved_or_built(review_case):
    w = review_case
    row = save(w)
    rejected = reject(w, row)
    error(lambda: approve(w, row), 409, "PROCESS_CONTRACT_REJECTED")
    if w["document_version"] == "2.0":
        error(lambda: build_app(w, row), 409, "PROCESS_CONTRACT_REJECTED")
    else:
        with pytest.raises(kb.KitAppError, match="승인"):
            kb.build(blueprint=w["blueprint"], instance_id=w["instance_id"],
                outputs=[{"output": w["app_id"], "state": kb.readiness.AVAILABLE}],
                actor_id=org.MEMBER_A, store=w["store"], app_data=object(),
                approved_contract=rejected["contract"], **w["context"])
    assert kc.approved(w["store"], w["instance_id"], w["app_id"]) is None


def test_ledger_failure_leaves_draft_not_rejected(review_case, monkeypatch):
    w = review_case
    row = save(w)
    before = stored(w, row)
    @contextmanager
    def unavailable():
        raise RuntimeError("synthetic rejection ledger unavailable")
        yield  # pragma: no cover
    monkeypatch.setattr(w["ledger"], "transaction", unavailable)
    error(lambda: reject(w, row), 503, "PROCESS_CONTRACT_REJECTION_UNAVAILABLE")
    assert stored(w, row) == before


def test_dp_failure_cannot_report_success_and_retry_reuses_ledger_event(review_case):
    w = review_case
    row = save(w)
    before = stored(w, row)
    with database(w, "dp") as conn:
        conn.execute("CREATE TRIGGER rejection_fault BEFORE UPDATE ON kit_app_contracts "
                     "WHEN NEW.status='REJECTED' BEGIN SELECT RAISE(ABORT,'synthetic rejection fault'); END")
    error(lambda: reject(w, row), 503)
    assert stored(w, row) == before
    events = rejection_events(w, row)
    assert len(events) == 1  # 원장 기록 자체를 DB rollback으로 되돌렸다고 주장하지 않는다.
    with database(w, "dp") as conn:
        conn.execute("DROP TRIGGER rejection_fault")
    rejected = reject(w, row)
    assert rejected["ledger_event_id"] == events[0]["event_id"]
    assert len(rejection_events(w, row)) == 1


def test_approval_and_rejection_race_has_one_state_winner(review_case, monkeypatch):
    from core.data_preparation import ownership_binding as ob
    from core.data_preparation.store import DataPreparationStore
    w = review_case
    row = save(w)
    other = {**w, "store": DataPreparationStore(w["store"].db_path)}
    assert Path(other["store"].db_path).resolve().is_relative_to(w["root"])
    gate, local = threading.Barrier(2), threading.local()
    original = ob.require_approval_authority
    def synchronized(actor):
        result = original(actor)
        if not getattr(local, "ready", False):
            local.ready = True
            gate.wait(timeout=20)
        return result
    monkeypatch.setattr(ob, "require_approval_authority", synchronized)
    def run(call):
        try:
            return call()["status"]
        except ProcessError as exc:
            assert exc.status_code == 409
            return "CONFLICT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, lambda: approve(w, row)), pool.submit(run, lambda: reject(other, row))]
        results = [future.result(timeout=40) for future in futures]
    assert results.count("CONFLICT") == 1
    final = stored(w, row)
    assert final["status"] in ("APPROVED", "REJECTED") and final["status"] in results
    if final["status"] == "REJECTED":
        assert kc.approved(w["store"], w["instance_id"], w["app_id"]) is None


def test_missing_rejection_proof_cannot_replay_or_redraft(review_case):
    w = review_case
    row = save(w)
    reject(w, row)
    with database(w, "dp") as conn:
        conn.execute("UPDATE kit_app_contracts SET ledger_event_id='missing-proof' WHERE contract_row_id=?",
                     (row["contract_row_id"],))
    error(lambda: reject(w, row), 503, "PROCESS_CONTRACT_REJECTION_UNAVAILABLE")
    error(lambda: save(w, expected_revision=row["revision"]), 503, "PROCESS_CONTRACT_REJECTION_UNAVAILABLE")


def test_current_read_allows_rejecting_held_v2_without_allowing_build(kit):
    w = {**kit, "document_version": "2.0", "app_id": "APP-03"}
    row = save(w)
    hold(w)
    rejected = reject(w, row)
    assert rejected["status"] == "REJECTED"
    error(lambda: build_app(w, row), 409, "PROCESS_CONTRACT_REJECTED")


@pytest.mark.parametrize("revoked", ["read", "reviewer"])
def test_permission_revoked_after_review_is_rechecked_before_write(review_case, monkeypatch, revoked):
    from core.org_directory import OrgDirectory, org_directory
    w = review_case
    row = save(w)
    path = Path(org_directory.db_path).resolve()
    assert path.is_relative_to(w["root"])
    other = OrgDirectory(str(path))
    before = stored(w, row)
    initial = org_directory.resolve_scope(org.DATA_ADMIN)
    assert initial.is_data_admin and not initial.unrestricted
    assert initial.can_read(org.DEPT_A) and w["context"]["scope_node_id"] in initial.readable_scope_nodes
    original, calls = kc._rejection_reviewer, []
    def revoke_after_first_check(actor, candidate):
        calls.append(actor)
        original(actor, candidate)
        if len(calls) == 1:
            user = other.get_user(org.DATA_ADMIN)
            # DA는 부서와 무관하게 전사 READ를 갖는다. 실제 회수는 플래그와
            # ROOT 상속 경로를 모두 제거해야 하며, 검토권만 회수할 때는 ROOT를 남긴다.
            other.upsert_user(org.DATA_ADMIN, user["display_name"],
                primary_dept_id=org.DEPT_B if revoked == "read" else org.DEPT_ROOT,
                is_data_admin=False, is_admin=False, is_executive=False, is_ai_admin=False, actor="test")
            other.set_user_roles(org.DATA_ADMIN,
                {org.DEPT_B: "viewer"} if revoked == "read" else {org.DEPT_ROOT: "manager"}, actor="test")
            assert other.get_user(org.DATA_ADMIN)["status"] == "active"
            fresh = other.resolve_scope(org.DATA_ADMIN, fresh=True)
            assert not (fresh.is_data_admin or fresh.is_admin or fresh.is_executive or fresh.unrestricted)
            assert fresh.can_read(org.DEPT_A) == (revoked != "read")
            assert (w["context"]["scope_node_id"] in fresh.readable_scope_nodes) == (revoked != "read")
            # 별도 연결의 변경은 기존 singleton 캐시를 갱신하지 않는다.
            assert org_directory.resolve_scope(org.DATA_ADMIN).can_read(org.DEPT_A)
    monkeypatch.setattr(kc, "_rejection_reviewer", revoke_after_first_check)
    error(lambda: reject(w, row, actor_id=org.DATA_ADMIN), 404 if revoked == "read" else 403,
          "PROCESS_NOT_FOUND" if revoked == "read" else "PROCESS_ACTION_FORBIDDEN")
    # READ 소실은 두 번째 reviewer 검사보다 앞에서 404여야 한다. 403으로 완화하지 않는다.
    assert calls == [org.DATA_ADMIN] * (1 if revoked == "read" else 2)
    assert stored(w, row) == before and rejection_events(w, row) == []


def test_data_admin_keeps_read_after_primary_and_roles_move_to_other_scope(review_case, monkeypatch):
    from core.org_directory import OrgDirectory, org_directory
    w = review_case
    row = save(w)
    before = stored(w, row)
    path = Path(org_directory.db_path).resolve()
    assert path.is_relative_to(w["root"])
    other = OrgDirectory(str(path))
    original, calls = kc._rejection_reviewer, []
    def move_after_first_check(actor, candidate):
        calls.append(actor)
        original(actor, candidate)
        if len(calls) == 1:
            user = other.get_user(org.DATA_ADMIN)
            other.upsert_user(org.DATA_ADMIN, user["display_name"], primary_dept_id=org.DEPT_B,
                is_data_admin=True, is_admin=False, is_executive=False, is_ai_admin=False, actor="test")
            other.set_user_roles(org.DATA_ADMIN, {org.DEPT_B: "viewer"}, actor="test")
            updated = other.get_user(org.DATA_ADMIN)
            assert updated["status"] == "active" and updated["roles"] == {org.DEPT_B: "viewer"}
            fresh = other.resolve_scope(org.DATA_ADMIN, fresh=True)
            assert fresh.primary_dept_id == org.DEPT_B and fresh.is_data_admin
            assert not (fresh.is_admin or fresh.is_executive or fresh.unrestricted)
            assert fresh.can_read(org.DEPT_A) and w["context"]["scope_node_id"] in fresh.readable_scope_nodes
    monkeypatch.setattr(kc, "_rejection_reviewer", move_after_first_check)
    rejected = reject(w, row, actor_id=org.DATA_ADMIN)
    assert rejected["status"] == "REJECTED" and calls == [org.DATA_ADMIN, org.DATA_ADMIN]
    assert rejected["rejection"]["rejected_by"] == org.DATA_ADMIN
    assert stored(w, row)["contract_json"] == before["contract_json"]
    assert len(rejection_events(w, row)) == 1


def test_concurrent_same_rejection_returns_one_original_event(review_case, monkeypatch):
    from core.data_preparation import ownership_binding as ob
    from core.data_preparation.store import DataPreparationStore
    w = review_case
    row = save(w)
    other = {**w, "store": DataPreparationStore(w["store"].db_path)}
    assert Path(other["store"].db_path).resolve().is_relative_to(w["root"])
    gate, local = threading.Barrier(2), threading.local()
    original = ob.require_approval_authority
    def synchronized(actor):
        result = original(actor)
        if not getattr(local, "ready", False):
            local.ready = True
            gate.wait(timeout=20)
        return result
    monkeypatch.setattr(ob, "require_approval_authority", synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reject, target, row) for target in (w, other)]
        results = [future.result(timeout=40) for future in futures]
    assert results[0] == results[1] and len(rejection_events(w, row)) == 1
