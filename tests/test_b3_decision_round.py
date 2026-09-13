"""Main-audit only: real temp draft producer/reader + real temp DecisionLedger.

No global conftest dependency. PDP callbacks below are EXPLICIT UNIT doubles;
Factory authorization, HTTP routing and project command guard belong to main's
integration tests. No LLM, production DB or source starter assets are used.
"""
from __future__ import annotations

import copy
import asyncio
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    from core import paths
    monkeypatch.setattr(paths, "DATA_DIR", str(root / "data"))
    monkeypatch.setattr(paths, "PROJECTS_DIR", str(root / "projects"))
    connect = sqlite3.connect

    def guarded_connect(database, *args, **kwargs):
        assert isinstance(database, (str, Path)) and not str(database).startswith("file:")
        assert Path(database).is_absolute() and Path(database).resolve().is_relative_to(root)
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    from core import contract_decision as cd, app_runtime_contract as arc
    from core.decision_ledger import DecisionLedger
    from nodes import contract as nodes

    class TempLedger(DecisionLedger):
        def _connect(self):
            connection = super()._connect()
            connections.append(connection)
            return connection

    connections = []
    workspace = root / "projects" / "P_ROUND"
    workspace.mkdir(parents=True)
    ledger = TempLedger(str(root / "ledger.round.test.invalid.db"))
    calls = []

    def append_event(**payload):
        # UNIT authority binding only, not a claim to exercise real current PDP.
        calls.append(copy.deepcopy(payload))
        event = ledger.append(**payload, actor_type="user", actor_id="reviewer@round.test.invalid",
                              tenant_id="tenant.round.test.invalid", enterprise_scope_id="scope.round.test.invalid",
                              entity_mode="REAL")
        assert ledger.get_event_strict(event["event_id"]) == event
        return event

    result = SimpleNamespace(root=root, ws=workspace, cd=cd, arc=arc, nodes=nodes, ledger=ledger,
                             calls=calls, append=append_event,
                             meta=workspace / "contracts" / "drafts" / "_decision_rounds.json",
                             anchor=workspace / "contracts" / ".decision_rounds_required")
    yield result
    for connection in connections:
        connection.close()


def _draft(*, action="read", capability="file.upload"):
    return {"app_class": "departmental", "datasets": [{
        "dataset_key": "shared_rows", "name": "rows", "label": "Rows", "purpose": "review",
        "allowed_actions": [action], "fields": [{"name": "id", "type": "string", "required": False,
                                                  "classification": "INTERNAL"}],
        "data_role": "ENTERPRISE_ACTUAL", "source_intent": "ENTERPRISE_READ",
        "duplicate_entry_policy": "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS", "enterprise_contract_key": "PRC-02"}],
        "capability_intents": ([{"intent_id": "i1", "requirement_ref": "FR-01", "capability": capability}]
                               if capability else [])}


def _wbs(env, ids):
    (env.ws / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [
        {"task_id": tid, "goal": "review", "artifact_kind": "APP", "status": "IN_PROGRESS",
         "required_agents": ["Tech_Lead", "Frontend"]} for tid in ids]}), encoding="utf-8")


def _seed(env, count=1, dataset=False):
    _wbs(env, [f"T{i}" for i in range(1, count + 1)])
    for i in range(1, count + 1):
        env.nodes.save_draft(str(env.ws), f"T{i}", _draft(
            action="create" if dataset and i == 2 else "read", capability="" if dataset else "file.upload"),
            require_metadata=True)


def _pending(env, dataset=False):
    result = env.cd.pending_for_workspace(env.ws, require_metadata=True)
    assert result["round_metadata_status"] == "READY"
    return result["dataset_conflicts" if dataset else "capability_decisions"][0]


def _resolve(env, pending=None, **kwargs):
    item = pending or _pending(env)
    args = {"task_id": "T1", "capability": "file.upload", "decision": "WAIT"}
    if item["decision_kind"] == "DATASET":
        args = {"dataset_key": item["dataset_key"], "winner_task_id": "T1"}
    return env.cd.resolve_for_workspace(env.ws, decision_request_id=item["decision_request_id"],
        expected_digest=item["expected_digest"], append_event=kwargs.pop("append_event", env.append),
        require_metadata=True, **{**args, **kwargs})


def _error(env, callback, status, code=None):
    with pytest.raises(env.cd.DecisionRoundError) as caught:
        callback()
    assert caught.value.status_code == status
    if code:
        assert caught.value.reason_code == code
    return caught.value


@pytest.mark.parametrize("managed", [False, True])
def test_real_producer_keeps_raw_and_runtime_v1_material(env, managed):
    draft = _draft()
    _wbs(env, ["T1"])
    path = Path(env.nodes.save_draft(str(env.ws), "T1", draft, require_metadata=managed))
    assert path.read_bytes() == json.dumps(draft, ensure_ascii=False, indent=2).replace("\n", os.linesep).encode()
    read = env.nodes.load_drafts(str(env.ws))["T1"]
    assert read == draft
    assert env.arc.canonical_json(read) == env.arc.canonical_json(draft)
    assert env.arc.semantic_fingerprint(read) == env.arc.semantic_fingerprint(draft)
    assert "decision_request_id" not in read
    assert env.cd.has_round_metadata(env.ws) is managed


def test_pending_uses_persisted_identity_without_get_uuid_or_meta_write(env, monkeypatch):
    _seed(env)
    first, raw = _pending(env), env.meta.read_bytes()
    monkeypatch.setattr(env.cd.uuid, "uuid4", lambda: pytest.fail("GET minted a new round"))
    assert _pending(env) == first
    assert env.meta.read_bytes() == raw
    assert len(first["draft_versions"]["T1"]["version_id"]) == 32


def test_same_content_new_save_has_new_uuid_and_stale_expected_409(env):
    _seed(env)
    first = _pending(env)
    path = env.ws / "contracts" / "drafts" / "T1.json"
    raw = path.read_bytes()
    env.nodes.save_draft(str(env.ws), "T1", _draft())
    second = _pending(env)
    assert path.read_bytes() == raw
    assert second["decision_request_id"] != first["decision_request_id"]
    assert second["draft_versions"]["T1"]["version_id"] != first["draft_versions"]["T1"]["version_id"]
    _error(env, lambda: _resolve(env, first), 409, "DECISION_ROUND_STALE")
    assert not env.calls


def test_llm_round_fields_are_not_server_identity(env):
    _wbs(env, ["T1"])
    forged = {**_draft(), "decision_request_id": "cdr_" + "a" * 64,
              "version_id": "b" * 32, "round_status": "APPLIED"}
    env.nodes.save_draft(str(env.ws), "T1", forged, require_metadata=True)
    pending = _pending(env)
    assert pending["decision_request_id"] != forged["decision_request_id"]
    assert pending["draft_versions"]["T1"]["version_id"] != forged["version_id"]
    assert pending["round_status"] == "PENDING"


def test_capability_ledger_before_overlay_readback_and_consumed_409(env):
    _seed(env)
    pending = _pending(env)
    original = (env.ws / "contracts" / "drafts" / "T1.json").read_bytes()

    def append(**payload):
        assert not env.nodes.draft_decisions._read_meta(env.meta)["overlays"]
        assert (env.ws / "contracts" / "drafts" / "T1.json").read_bytes() == original
        return env.append(**payload)

    result = _resolve(env, pending, append_event=append)
    assert result["draft_applied"] and result["applied_tasks"] == ["T1"]
    assert env.nodes.load_drafts(str(env.ws))["T1"]["capability_intents"][0]["user_decision"] == "WAIT"
    assert (env.ws / "contracts" / "drafts" / "T1.json").read_bytes() == original
    event = env.ledger.get_event_strict(result["event_id"])
    assert event["input_version_refs"][0]["decision_request_id"] == pending["decision_request_id"]
    _error(env, lambda: _resolve(env, pending), 409, "DECISION_ROUND_CONSUMED")
    assert len(env.calls) == 1


def test_same_content_regeneration_does_not_inherit_consumed_choice(env):
    _seed(env)
    first = _pending(env)
    _resolve(env, first)
    env.nodes.save_draft(str(env.ws), "T1", _draft())
    second = _pending(env)
    assert second["decision_request_id"] != first["decision_request_id"]
    assert "user_decision" not in env.nodes.load_drafts(str(env.ws))["T1"]["capability_intents"][0]
    _resolve(env, second)
    assert len(env.calls) == 2


def test_dataset_binds_all_three_declarations_and_atomic_overlay(env):
    _seed(env, 3, dataset=True)
    pending = _pending(env, dataset=True)
    assert pending["choices"] == ["T1", "T2", "T3"]
    before = {p.name: p.read_bytes() for p in (env.ws / "contracts" / "drafts").glob("T*.json")}
    result = _resolve(env, pending, winner_task_id="T2")
    assert result["applied_tasks"] == ["T1", "T3"]
    assert before == {p.name: p.read_bytes() for p in (env.ws / "contracts" / "drafts").glob("T*.json")}
    effective = env.nodes.load_drafts(str(env.ws))
    assert all(draft["datasets"][0]["allowed_actions"] == ["create"] for draft in effective.values())
    assert not (env.ws / "contracts" / "drafts" / "_resolutions.json").exists()
    _error(env, lambda: _resolve(env, pending), 409, "DECISION_ROUND_CONSUMED")
    env.nodes.save_draft(str(env.ws), "T3", _draft(capability=""))
    assert _pending(env, dataset=True)["decision_request_id"] != pending["decision_request_id"]


@pytest.mark.parametrize("change", ["other_generation", "new_generation", "wbs"])
def test_current_set_change_rejects_old_round_before_ledger(env, change):
    _seed(env, 2, dataset=True)
    pending = _pending(env, dataset=True)
    if change == "other_generation":
        env.nodes.save_draft(str(env.ws), "T2", _draft(action="create", capability=""))
    elif change == "new_generation":
        env.nodes.save_draft(str(env.ws), "T3", _draft(capability=""))
    else:
        _wbs(env, ["T1", "T2", "T3"])
    _error(env, lambda: _resolve(env, pending), 409, "DECISION_ROUND_STALE")
    assert not env.calls


@pytest.mark.parametrize("change", ["raw", "missing", "untracked"])
def test_untracked_or_modified_actual_files_fail_closed(env, change):
    _seed(env)
    path = env.ws / "contracts" / "drafts" / "T1.json"
    if change == "raw":
        path.write_text(json.dumps(_draft(action="create")), encoding="utf-8")
    elif change == "missing":
        path.unlink()
    else:
        path.with_name("T2.json").write_text(json.dumps(_draft()), encoding="utf-8")
    _error(env, lambda: _pending(env), 409, "DECISION_ROUND_STALE")


@pytest.mark.parametrize("loss", ["anchor", "meta", "both"])
def test_v2_metadata_loss_never_becomes_legacy(env, loss):
    _seed(env)
    if loss in {"anchor", "both"}:
        env.anchor.unlink()
    if loss in {"meta", "both"}:
        env.meta.unlink()
    _error(env, lambda: _pending(env), 503)
    _error(env, lambda: env.nodes.load_drafts(str(env.ws), require_metadata=True), 503)


def test_legacy_explicit_unprepared_and_no_round_implicit_migration(env):
    _wbs(env, ["T1"])
    directory = env.ws / "contracts" / "drafts"
    directory.mkdir(parents=True)
    (directory / "T1.json").write_text(json.dumps(_draft()), encoding="utf-8")
    result = env.cd.pending_for_workspace(env.ws)
    assert result["round_metadata_status"] == "LEGACY_UNPREPARED"
    assert "decision_request_id" not in result["capability_decisions"][0]
    assert not env.meta.exists() and not env.anchor.exists()
    assert env.nodes.load_drafts(str(env.ws))["T1"] == _draft()
    _error(env, lambda: env.cd.pending_for_workspace(env.ws, require_metadata=True), 503)


def test_old_unbound_resolution_not_inherited_by_managed_generations(env):
    _seed(env, 2, dataset=True)
    directory = env.ws / "contracts" / "drafts"
    # Simulate a leftover/imported unbound legacy overlay, not a migration.
    (directory / "_resolutions.json").write_text(json.dumps({"datasets": {"rows": "T1"}}), encoding="utf-8")
    old = (directory / "_resolutions.json").read_bytes()
    assert _pending(env, dataset=True)
    assert (directory / "_resolutions.json").read_bytes() == old
    _error(env, lambda: env.nodes.record_dataset_resolution(str(env.ws), "rows", "T1"), 409, "DECISION_ROUND_REQUIRED")


def test_tampered_metadata_checksum_rejected(env):
    _seed(env)
    document = json.loads(env.meta.read_bytes())
    document["versions"]["T1"]["version_id"] = "f" * 32
    env.meta.write_text(json.dumps(document), encoding="utf-8")
    _error(env, lambda: _pending(env), 503)


def test_invalid_choice_and_cross_target_do_not_consume(env):
    _seed(env)
    pending = _pending(env)
    before = env.meta.read_bytes()
    _error(env, lambda: _resolve(env, pending, decision="ALLOW_EVERYTHING"), 422)
    _error(env, lambda: _resolve(env, pending, task_id="T2"), 409)
    assert env.meta.read_bytes() == before and not env.calls


def test_workspace_file_lock_blocks_nested_writer_and_resolve(env):
    _seed(env)
    pending = _pending(env)
    with env.cd._workspace_lock(env.ws):
        _error(env, lambda: _resolve(env, pending), 409, "DECISION_ROUND_BUSY")
        _error(env, lambda: env.nodes.save_draft(str(env.ws), "T1", _draft()), 409, "DECISION_ROUND_BUSY")
    assert not env.calls


def test_lifecycle_status_change_is_not_a_new_draft_round(env):
    _seed(env)
    pending = _pending(env)
    path = env.ws / "00_wbs_master_plan.json"
    wbs = json.loads(path.read_bytes())
    wbs["tasks"][0].update(status="FAILED", updated_at="2030-01-02")
    path.write_text(json.dumps(wbs), encoding="utf-8")
    assert _pending(env)["decision_request_id"] == pending["decision_request_id"]
    _resolve(env, pending)
    wbs["tasks"][0]["status"] = "IN_PROGRESS"
    path.write_text(json.dumps(wbs), encoding="utf-8")
    assert env.nodes.load_drafts(str(env.ws))["T1"]["capability_intents"][0]["user_decision"] == "WAIT"


def test_ledger_failure_reserves_round_without_overlay_or_retry_append(env):
    _seed(env)
    pending = _pending(env)
    calls = []

    def unavailable(**payload):
        calls.append(payload)
        raise OSError("synthetic ledger failure")

    _error(env, lambda: _resolve(env, pending, append_event=unavailable), 503)
    assert _pending(env)["round_status"] == "RESERVED"
    _error(env, lambda: _resolve(env, pending, append_event=unavailable), 503, "DECISION_ROUND_PARTIAL")
    assert len(calls) == 1 and not env.cd._read_meta(env.meta)["overlays"]


def test_append_ack_exception_preserves_event_id_durably(env):
    _seed(env)
    pending = _pending(env)

    def lost_readback(**payload):
        event = env.append(**payload)
        error = OSError("synthetic readback failure")
        error.event_id = event["event_id"]
        raise error

    failed = _error(env, lambda: _resolve(env, pending, append_event=lost_readback), 503)
    assert failed.event_id and env.ledger.get_event_strict(failed.event_id)
    repeated = _error(env, lambda: _resolve(env, pending), 503, "DECISION_ROUND_PARTIAL")
    assert repeated.event_id == failed.event_id and len(env.calls) == 1
    assert not env.cd._read_meta(env.meta)["overlays"]


def test_overlay_write_failure_retains_ledger_ack_and_original_files(env, monkeypatch):
    _seed(env, 2, dataset=True)
    pending = _pending(env, dataset=True)
    original = env.cd._write_meta
    before = {p.name: p.read_bytes() for p in (env.ws / "contracts" / "drafts").glob("T*.json")}
    foreign = env.meta.with_name("foreign.tmp")
    foreign.write_bytes(b"preserve")

    def fail_overlay(path, doc):
        if doc.get("overlays"):
            raise OSError("synthetic overlay disk failure")
        return original(path, doc)

    monkeypatch.setattr(env.cd, "_write_meta", fail_overlay)
    failed = _error(env, lambda: _resolve(env, pending), 503)
    assert failed.event_id and env.ledger.get_event_strict(failed.event_id)
    assert before == {p.name: p.read_bytes() for p in (env.ws / "contracts" / "drafts").glob("T*.json")}
    assert foreign.read_bytes() == b"preserve"
    assert not env.cd._read_meta(env.meta)["overlays"]
    _error(env, lambda: _resolve(env, pending), 503)
    assert len(env.calls) == 1


def test_post_overlay_readback_failure_is_not_success_or_second_append(env, monkeypatch):
    _seed(env)
    pending = _pending(env)
    original = env.cd._snapshot
    once = []

    def fail_readback(*args, **kwargs):
        snapshot = original(*args, **kwargs)
        if snapshot.get("applied") and not once:
            once.append(True)
            raise OSError("synthetic committed-overlay readback failure")
        return snapshot

    monkeypatch.setattr(env.cd, "_snapshot", fail_readback)
    failed = _error(env, lambda: _resolve(env, pending), 503)
    assert failed.event_id
    _error(env, lambda: _resolve(env, pending), 409, "DECISION_ROUND_CONSUMED")
    assert len(env.calls) == 1


def test_source_changed_during_ledger_ack_returns_409_without_overlay(env):
    _seed(env)
    pending = _pending(env)

    def outside_writer(**payload):
        event = env.append(**payload)
        path = env.ws / "contracts" / "drafts" / "T1.json"
        path.write_text(json.dumps(_draft(action="create")), encoding="utf-8")
        return event

    failed = _error(env, lambda: _resolve(env, pending, append_event=outside_writer), 409, "DECISION_ROUND_STALE")
    assert failed.event_id and not env.cd._read_meta(env.meta)["overlays"]
    assert len(env.calls) == 1


@pytest.mark.parametrize("stage", ["reserved", "overlay"])
def test_unit_authority_revocation_before_each_write(env, stage):
    from fastapi import HTTPException
    _seed(env)
    pending = _pending(env)
    before = env.meta.read_bytes()
    checks = []

    def unit_pdp():
        checks.append(True)
        if len(checks) == (1 if stage == "reserved" else 2):
            raise HTTPException(403, "unit authority revoked")

    failed = _error(env, lambda: _resolve(env, pending, before_write=unit_pdp), 403 if stage == "reserved" else 503)
    if stage == "reserved":
        assert env.meta.read_bytes() == before and not env.calls
        assert not failed.event_id
    else:
        assert failed.event_id and len(env.calls) == 1
        assert not env.cd._read_meta(env.meta)["overlays"]
        assert env.cd._read_meta(env.meta)["attempts"][pending["decision_request_id"]]["state"] == "RECORDED"


def test_interrupted_producer_write_has_no_old_round_fallback(env, monkeypatch):
    _seed(env)
    original = env.cd._atomic_bytes

    def fail_draft(path, raw):
        if path.name == "T1.json":
            raise OSError("synthetic draft replacement failure")
        return original(path, raw)

    monkeypatch.setattr(env.cd, "_atomic_bytes", fail_draft)
    _error(env, lambda: env.nodes.save_draft(str(env.ws), "T1", _draft(action="create")), 503)
    _error(env, lambda: _pending(env), 503, "DECISION_ROUND_WRITE_INCOMPLETE")


@pytest.mark.parametrize("target", ["draft", "meta"])
def test_symlink_source_preserved_and_rejected(env, target):
    _seed(env)
    path = env.meta if target == "meta" else env.ws / "contracts" / "drafts" / "T1.json"
    foreign = env.root / (target + ".foreign.json")
    raw = path.read_bytes()
    foreign.write_bytes(raw)
    path.unlink()
    try:
        path.symlink_to(foreign)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink privileges unavailable: {exc}")
    _error(env, lambda: _pending(env), 503)
    assert path.is_symlink() and foreign.read_bytes() == raw


@pytest.mark.parametrize("first_action", ["decide", "regenerate"])
def test_legacy_two_drafts_first_save_does_not_strand_other_draft(env, first_action):
    """P2: a legacy A-only decision OR TechLead regeneration must not produce
    READY(A)/LEGACY(B). Actual producer/reader, pure decision application; HTTP/PDP
    are tested by main, not simulated as integration proof here.
    """
    _wbs(env, ["T1", "T2"])
    for tid in ("T1", "T2"):
        env.nodes.save_draft(str(env.ws), tid, _draft())
    before_b = (env.ws / "contracts" / "drafts" / "T2.json").read_bytes()
    a = env.nodes.load_drafts(str(env.ws))["T1"]
    if first_action == "decide":
        a, _ = env.cd.apply_capability_decision(a, capability="file.upload", decision="WAIT")
    env.nodes.save_draft(str(env.ws), "T1", a)
    assert not env.cd.has_round_metadata(env.ws)
    assert (env.ws / "contracts" / "drafts" / "T2.json").read_bytes() == before_b
    pending = env.cd.pending_for_workspace(env.ws)
    assert pending["round_metadata_status"] == "LEGACY_UNPREPARED"
    assert any(item["task_id"] == "T2" for item in pending["capability_decisions"])
    b = env.nodes.load_drafts(str(env.ws))["T2"]
    b, _ = env.cd.apply_capability_decision(b, capability="file.upload", decision="WAIT")
    env.nodes.save_draft(str(env.ws), "T2", b)
    assert not any(item["task_id"] == "T2" for item in env.cd.pending_for_workspace(env.ws)["capability_decisions"])
    env.nodes.save_draft(str(env.ws), "T1", _draft())
    assert any(item["task_id"] == "T1" for item in env.cd.pending_for_workspace(env.ws)["capability_decisions"])
    assert not env.meta.exists() and not env.anchor.exists()


def test_legacy_dataset_resolution_survives_one_draft_regeneration(env):
    _wbs(env, ["T1", "T2"])
    env.nodes.save_draft(str(env.ws), "T1", _draft(capability=""))
    env.nodes.save_draft(str(env.ws), "T2", _draft(action="create", capability=""))
    drafts = env.nodes.load_drafts(str(env.ws))
    assert env.cd.pending_for_workspace(env.ws)["dataset_conflicts"]
    changed, _ = env.cd.apply_dataset_resolution(drafts, dataset_key="shared_rows", winner_task_id="T1")
    # Legacy overlay uses display name; this test preserves that existing contract.
    env.nodes.record_dataset_resolution(str(env.ws), "rows", "T1")
    for tid, draft in changed.items():
        env.nodes.save_draft(str(env.ws), tid, draft)
    assert not env.cd.pending_for_workspace(env.ws)["dataset_conflicts"]
    env.nodes.save_draft(str(env.ws), "T2", _draft(action="create", capability=""))
    assert not env.cd.pending_for_workspace(env.ws)["dataset_conflicts"]
    assert env.nodes.load_drafts(str(env.ws))["T2"]["datasets"][0]["allowed_actions"] == ["read"]
    assert not env.cd.has_round_metadata(env.ws)


def test_explicit_one_file_legacy_migration_rejected_before_metadata_write(env):
    _wbs(env, ["T1", "T2"])
    for tid in ("T1", "T2"):
        env.nodes.save_draft(str(env.ws), tid, _draft())
    before = {path.name: path.read_bytes() for path in (env.ws / "contracts" / "drafts").glob("*.json")}
    _error(env, lambda: env.nodes.save_draft(str(env.ws), "T1", _draft(), require_metadata=True),
           409, "DECISION_ROUND_MIGRATION_REQUIRED")
    assert before == {path.name: path.read_bytes() for path in (env.ws / "contracts" / "drafts").glob("*.json")}
    assert not env.meta.exists() and not env.anchor.exists()


def test_v2_producer_cannot_downgrade_after_both_metadata_files_lost(env):
    _seed(env)
    raw = (env.ws / "contracts" / "drafts" / "T1.json").read_bytes()
    env.meta.unlink()
    env.anchor.unlink()
    _error(env, lambda: env.nodes.save_draft(str(env.ws), "T1", _draft(action="create"), require_metadata=True),
           409, "DECISION_ROUND_MIGRATION_REQUIRED")
    assert (env.ws / "contracts" / "drafts" / "T1.json").read_bytes() == raw
    _error(env, lambda: env.nodes.load_drafts(str(env.ws), require_metadata=True), 503)


def _v2_node_state(env, current_task_id):
    # Synthetic valid DTO; real schema validation, NOT a real ProcessContext/PDP.
    context = {"schema_version": 1, "configuration_id": "configuration.round.test.invalid",
        "profile_id": "profile.round.test.invalid", "process_ids": ["process.round.test.invalid"],
        "process_semantic_fingerprint": "a" * 64, "configuration_fingerprint": "b" * 64,
        "context_key": {"tenant_id": "tenant.round.test.invalid", "context_root_id": "root.round.test.invalid",
                        "entity_mode": "REAL", "scope_node_id": "scope.round.test.invalid"},
        "data_requirements": [], "verified_binding_refs": [], "blockers": [], "permitted_actions": ["DRAFT"],
        "sources": [{"kind": "PROCESS_PROFILE", "configuration_id": "configuration.round.test.invalid",
                     "profile_id": "profile.round.test.invalid", "fingerprint": "b" * 64}]}
    assert not env.arc.runtime_document_errors("2.0", context)
    return {"workspace_root": str(env.ws), "project_name": "P_ROUND", "current_sprint_task_id": current_task_id,
            "runtime_contract_profile": "v1", "runtime_document_version": "2.0", "process_context": context}


def _write_task_kinds(env, kinds):
    (env.ws / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [
        {"task_id": tid, "artifact_kind": kind, "status": "TODO", "goal": "synthetic task"}
        for tid, kind in kinds]}), encoding="utf-8")


@pytest.mark.parametrize("node", ["run_host_contract_compiler", "run_contract_review_gate"])
@pytest.mark.parametrize("future_app", [False, True])
def test_v2_library_without_metadata_is_not_applicable(env, node, future_app):
    kinds = [("LIB", "LIBRARY")] + ([("APP", "APP")] if future_app else [])
    _write_task_kinds(env, kinds)
    result = asyncio.run(getattr(env.nodes, node)(_v2_node_state(env, "LIB")))
    assert not result.get("terminal_status"), result
    assert not result.get("app_runtime_contract_fingerprint")
    assert not result.get("contract_review_request_event_id")
    assert not env.meta.exists() and not env.anchor.exists()
    assert not Path(env.ledger.db_path).exists() and not env.calls


@pytest.mark.parametrize("node", ["run_host_contract_compiler", "run_contract_review_gate"])
@pytest.mark.parametrize("kind", ["APP", "unknown", None])
def test_v2_current_contract_or_unreadable_kind_still_requires_metadata(env, node, kind):
    _write_task_kinds(env, [("T1", kind)])
    result = asyncio.run(getattr(env.nodes, node)(_v2_node_state(env, "T1")))
    assert result["terminal_status"] == "CONTRACT_BLOCKED"
    assert not env.calls


@pytest.mark.parametrize("node", ["run_host_contract_compiler", "run_contract_review_gate"])
def test_v2_library_with_present_app_draft_cannot_skip_missing_metadata(env, node):
    _write_task_kinds(env, [("LIB", "LIBRARY"), ("APP", "APP")])
    env.nodes.save_draft(str(env.ws), "APP", _draft())  # Explicit legacy source, no v2 proof.
    result = asyncio.run(getattr(env.nodes, node)(_v2_node_state(env, "LIB")))
    assert result["terminal_status"] == "CONTRACT_BLOCKED"
    assert not env.calls


@pytest.mark.parametrize("node", ["run_host_contract_compiler", "run_contract_review_gate"])
def test_v2_library_keeps_managed_marker_loss_fail_closed(env, node):
    _seed(env)
    _write_task_kinds(env, [("LIB", "LIBRARY"), ("T1", "APP")])
    env.meta.unlink()  # Anchor survives; this is not a never-created workspace.
    (env.ws / "contracts" / "drafts" / "T1.json").unlink()
    result = asyncio.run(getattr(env.nodes, node)(_v2_node_state(env, "LIB")))
    assert result["terminal_status"] == "CONTRACT_BLOCKED"
    assert not env.calls


@pytest.mark.parametrize("node", ["run_host_contract_compiler", "run_contract_review_gate"])
def test_v2_malformed_wbs_is_not_non_contract_proof(env, node):
    (env.ws / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [None]}), encoding="utf-8")
    result = asyncio.run(getattr(env.nodes, node)(_v2_node_state(env, "LIB")))
    assert result["terminal_status"] == "CONTRACT_BLOCKED"
    assert not env.calls
