"""B3 saga 회귀: main audit 런너 전용, 실행하지 않은 시험 소스.

AdvisorStore/DecisionLedger/RevisionStore/파일 IO/operation_lock은 실제 임시 자원이다.
unit_* 권한/ProcessContext 및 기본 fixture의 provision은 명시적 대역이다. provision은
실제 임시 파일을 쓰지만 Factory 라우터의 템플릿/부서/메타 정책을 검증하지 않는다.
real_*는 enforced_org의 실제 ProcessContext/PDP를 연결한다. API/실행/RAW 검증 아님.
factory_bootstrap은 실제 Factory provision/메타 저장을 연결한다. 템플릿 목록/바인딩
capture 경계만 합성 대역이며 원본 registry/Starter를 읽거나 쓰지 않는다.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.test_b3_studio_drafts import (
    _approve_process, _count, _db, _decide, _error, _propose, _save,
    enforced_org, isolated_stores, real_studio, unit_studio,  # noqa: F401
)


class UnitProvision:
    """Factory provision만 대체하는 명시적 대역. 실제 파일/마커는 tmp에만 작성한다."""
    def __init__(self, root):
        self.root, self.calls, self.fail_once = root, [], None

    def __call__(self, project_id, template_id, **kwargs):
        from core.paths import workspace_path
        from core.studio_project_files import MARKER, read_json, write_json

        self.calls.append((project_id, template_id, copy.deepcopy(kwargs)))
        folder = Path(workspace_path(project_id)).resolve()
        assert folder.is_relative_to(self.root)
        context = kwargs["studio_context"]
        marker = {"project_id": project_id, "operation_id": context["bootstrap_operation_id"]}
        if folder.exists():
            if not (folder / MARKER).exists() or read_json(folder / MARKER) != marker:
                raise FileExistsError(project_id)
        else:
            folder.mkdir(parents=True)
            write_json(folder / MARKER, marker)
        if self.fail_once == "marker":
            self.fail_once = None
            raise OSError("unit provision failed after marker")
        metadata = {**{key: value for key, value in kwargs.items() if key != "studio_context"},
                    **context, "template_id": template_id, "project_id": project_id}
        write_json(folder / "project_meta.json", metadata)
        if self.fail_once == "meta":
            self.fail_once = None
            raise OSError("unit provision failed after meta")
        return template_id


def _make_bootstrap(studio):
    from core.studio_bootstrap import StudioBootstrapService
    from types import SimpleNamespace

    env = SimpleNamespace(**vars(studio))
    env.provision = UnitProvision(env.root)
    env.bootstrap = StudioBootstrapService(drafts=env.drafts, ledger=env.ledger, provision=env.provision)
    return env


@pytest.fixture
def unit_bootstrap(unit_studio):
    return _make_bootstrap(unit_studio)


def _bootstrap(env, approved, **changes):
    return env.bootstrap.bootstrap(**{"boundary": env.boundary, "actor": env.author, "context": env.context,
        "approved_revision_id": approved["revision_id"], "approved_digest": approved["digest"],
        "expected_process_semantic_digest": approved["process_ref"]["process_semantic_fingerprint"],
        "client_request_id": "bootstrap-1", **changes})


def _operation(env, actor=None):
    from core.studio_drafts import context_key
    actor = actor or env.author
    with _db(env) as conn:
        row = conn.execute("SELECT operation_id FROM advisor_v2_bootstraps WHERE actor=? ORDER BY rowid DESC LIMIT 1",
                            (actor,)).fetchone()
    assert row is not None
    return env.revisions.get(boundary=context_key(env.boundary), actor=actor, operation_id=row["operation_id"])


def _workspace(env, operation):
    from core.paths import workspace_path
    path = Path(workspace_path(operation["project_id"])).resolve()
    assert path.is_relative_to(env.root)
    return path


def _files(env, operation):
    from core.studio_project_files import read_json
    folder = _workspace(env, operation)
    return [read_json(folder / name) for name in ("project_meta.json", "latest_state.json")]


def _events(env):
    with _db(env, ledger=True) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM decision_ledger_events ORDER BY seq")]


def _reserve(env, approved):
    from core.studio_drafts import context_key
    return env.revisions.reserve_bootstrap(approved_revision_id=approved["revision_id"], digest=approved["digest"],
        context_key=context_key(env.boundary), actor=env.author, client_request_id="bootstrap-1",
        semantic_digest=approved["process_ref"]["process_semantic_fingerprint"])


def test_unit_success_and_identical_request_repeat_preserve_one_project_and_event(unit_bootstrap):
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    completed = _bootstrap(env, approved)
    assert completed["stage"] == "COMPLETED"
    assert completed["result"]["ledger_acknowledged"] is True
    assert completed["result"]["ledger_event_id"] == completed["event_id"]
    assert _bootstrap(env, approved) == completed
    assert len(env.provision.calls) == 1
    assert _count(env, "advisor_v2_bootstraps") == len(_events(env)) == 1
    for value in _files(env, completed):
        assert value["setup_status"] == "READY" and value["runtime_document_version"] == "2.0"
        assert value["approved_blueprint_revision_id"] == approved["revision_id"]
        assert value["process_context"] == approved["process_ref"]
    assert _events(env)[0]["event_id"] == completed["event_id"]


@pytest.mark.parametrize("point", ["marker", "meta"])
def test_unit_partial_provision_io_resumes_same_project_without_erasing_files(unit_bootstrap, point):
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    env.provision.fail_once = point
    _error(lambda: _bootstrap(env, approved), "STUDIO_SETUP_IO_FAILED", 503)
    failed = _operation(env)
    assert failed["stage"] == "FAILED_RETRYABLE" and failed["resume_stage"] == "PROVISIONING"
    folder = _workspace(env, failed)
    sentinel = folder / "user-preserved.test.invalid.txt"
    sentinel.write_text("사용자 입력 보존", encoding="utf-8")
    assert len(_events(env)) == 0
    completed = _bootstrap(env, approved)
    assert completed["project_id"] == failed["project_id"] and completed["event_id"] == failed["event_id"]
    assert sentinel.read_text(encoding="utf-8") == "사용자 입력 보존"
    assert len(env.provision.calls) == 2 and _count(env, "advisor_v2_bootstraps") == 1


def test_unit_initial_state_write_failure_leaves_incomplete_metadata_and_no_ledger(unit_bootstrap, monkeypatch):
    import core.studio_bootstrap as module
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    write = module.write_json

    def fail_state(path, value):
        if Path(path).name == "latest_state.json":
            raise OSError("unit initial state write failure")
        return write(path, value)

    monkeypatch.setattr(module, "write_json", fail_state)
    _error(lambda: _bootstrap(env, approved), "STUDIO_SETUP_IO_FAILED", 503)
    failed = _operation(env)
    folder = _workspace(env, failed)
    assert json.loads((folder / "project_meta.json").read_text(encoding="utf-8"))["setup_status"] == "SETUP_INCOMPLETE"
    assert not (folder / "latest_state.json").exists() and not _events(env)
    monkeypatch.setattr(module, "write_json", write)
    assert _bootstrap(env, approved)["project_id"] == failed["project_id"]


def test_unit_ledger_ack_then_ready_state_write_failure_recovers_without_new_event(unit_bootstrap, monkeypatch):
    import core.studio_bootstrap as module
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    write = module.write_json

    def fail_ready_state(path, value):
        if Path(path).name == "latest_state.json" and value.get("setup_status") == "READY":
            raise OSError("unit failure after committed ledger ack")
        return write(path, value)

    monkeypatch.setattr(module, "write_json", fail_ready_state)
    _error(lambda: _bootstrap(env, approved), "STUDIO_SETUP_IO_FAILED", 503)
    failed = _operation(env)
    event = _events(env)[0]
    assert failed["stage"] == "FAILED_RETRYABLE" and failed["resume_stage"] == "LEDGER_PENDING"
    assert "ledger_acknowledged" not in failed["result"]
    assert [value["setup_status"] for value in _files(env, failed)] == ["READY", "SETUP_INCOMPLETE"]
    monkeypatch.setattr(module, "write_json", write)
    completed = _bootstrap(env, approved)
    assert completed["project_id"] == failed["project_id"] and completed["stage"] == "COMPLETED"
    assert _events(env) == [event] and len(env.provision.calls) == 1


def test_unit_completion_db_failure_after_ready_files_retries_original_event(unit_bootstrap, monkeypatch):
    from core.advisor_revision_store import RevisionStoreError
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    advance = env.revisions.advance

    def fail_completion(**kwargs):
        if kwargs["next_stage"] == "COMPLETED":
            raise RevisionStoreError("ADVISOR_STORAGE_UNAVAILABLE", "unit completion DB failure", 503)
        return advance(**kwargs)

    monkeypatch.setattr(env.revisions, "advance", fail_completion)
    _error(lambda: _bootstrap(env, approved), "ADVISOR_STORAGE_UNAVAILABLE", 503)
    failed = _operation(env)
    event = _events(env)[0]
    assert failed["stage"] == "FAILED_RETRYABLE"
    assert all(value["setup_status"] == "READY" for value in _files(env, failed))
    monkeypatch.setattr(env.revisions, "advance", advance)
    assert _bootstrap(env, approved)["operation_id"] == failed["operation_id"]
    assert _events(env) == [event]


def test_unit_same_request_cannot_change_semantic_digest_or_approval_digest(unit_bootstrap):
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    completed = _bootstrap(env, approved)
    _error(lambda: _bootstrap(env, approved, expected_process_semantic_digest="0" * 64), "ADVISOR_PROCESS_SEMANTIC_CONFLICT")
    _error(lambda: _bootstrap(env, approved, approved_digest="0" * 64), "ADVISOR_REVISION_CONFLICT")
    assert _operation(env) == completed and len(_events(env)) == 1


def test_unit_other_actor_cannot_read_operation_and_has_distinct_idempotency_scope(unit_bootstrap):
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    first = _bootstrap(env, approved)
    _error(lambda: env.bootstrap.get(boundary=env.boundary, actor=env.other, context=env.context,
                                      operation_id=first["operation_id"]), "ADVISOR_NOT_FOUND", 404)
    second = _bootstrap(env, approved, actor=env.other)
    assert second["project_id"] != first["project_id"] and second["event_id"] != first["event_id"]
    assert _files(env, second)[0]["owner_user_id"] == approved["author_actor"]
    assert len(_events(env)) == 2


def test_unit_revoked_current_actor_cannot_replay_completed_bootstrap(unit_bootstrap):
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    completed = _bootstrap(env, approved)
    env.denied.add((env.author, "BOOTSTRAP"))
    _error(lambda: _bootstrap(env, approved), "UNIT_AUTH_DENIED", 403)
    assert _operation(env) == completed and len(_events(env)) == 1


def test_unit_current_process_is_rechecked_immediately_before_ledger(unit_bootstrap, monkeypatch):
    from core.enterprise_context.process_schema import ProcessError
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    revalidate = env.processes.revalidate
    checks = []

    def revoke_at_second_check(fixed_context, *, actor, current_context, for_action):
        if for_action == "BOOTSTRAP":
            checks.append(for_action)
            if len(checks) == 2:
                raise ProcessError("UNIT_PROCESS_REVOKED", "unit current process revoked", 403)
        return revalidate(fixed_context, actor=actor, current_context=current_context, for_action=for_action)

    monkeypatch.setattr(env.processes, "revalidate", revoke_at_second_check)
    _error(lambda: _bootstrap(env, approved), "UNIT_PROCESS_REVOKED", 403)
    assert checks == ["BOOTSTRAP", "BOOTSTRAP"]
    assert _operation(env)["stage"] == "FAILED_BLOCKED" and not _events(env)


def test_unit_real_operation_lock_blocks_duplicate_io_and_releases(unit_bootstrap):
    from core.studio_project_files import operation_lock
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    reserved = _reserve(env, approved)
    with operation_lock(reserved["project_id"]):
        _error(lambda: _bootstrap(env, approved), "STUDIO_BOOTSTRAP_BUSY")
        assert _operation(env)["stage"] == "RESERVED" and not env.provision.calls
    assert _bootstrap(env, approved)["operation_id"] == reserved["operation_id"]
    assert len(env.provision.calls) == 1


@pytest.mark.parametrize("project_id", ["../outside", "prj_manual", "", "prj_" + "g" * 32])
def test_unit_operation_lock_rejects_nonreserved_ids(isolated_stores, project_id):
    from core.studio_project_files import operation_lock

    def lock():
        with operation_lock(project_id):
            pytest.fail("invalid project ID acquired lock")
    _error(lock, "STUDIO_PROJECT_ID_INVALID", 422)
    assert not (isolated_stores.root / "data" / "studio_bootstrap_locks").exists()


def test_unit_foreign_existing_workspace_is_preserved_and_blocked(unit_bootstrap):
    from core.studio_project_files import MARKER, write_json
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    reserved = _reserve(env, approved)
    folder = _workspace(env, reserved)
    folder.mkdir(parents=True)
    original = {"project_id": reserved["project_id"], "operation_id": "foreign.test.invalid"}
    write_json(folder / MARKER, original)
    _error(lambda: _bootstrap(env, approved), "STUDIO_PROJECT_ID_CONFLICT", 409)
    assert _operation(env)["stage"] == "FAILED_BLOCKED"
    assert json.loads((folder / MARKER).read_text(encoding="utf-8")) == original
    _error(lambda: _bootstrap(env, approved), "STUDIO_BOOTSTRAP_BLOCKED")
    assert not _events(env)


@pytest.mark.parametrize("field,value", [("runtime_document_version", "1.0"), ("bootstrap_operation_id", ""),
    ("approved_blueprint_revision_id", "other.test.invalid"), ("approved_blueprint_digest", "0" * 64),
    ("context_root_id", "other.test.invalid"), ("tenant_id", "other.test.invalid"),
    ("process_context", {"forged": True}), ("owner_user_id", "other@studio.test.invalid")])
def test_unit_completed_file_reference_tampering_is_not_repaired_or_accepted(unit_bootstrap, field, value):
    from core.studio_project_files import write_json
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    completed = _bootstrap(env, approved)
    state = _files(env, completed)[1]
    state[field] = value
    path = _workspace(env, completed) / "latest_state.json"
    write_json(path, state)
    _error(lambda: _bootstrap(env, approved), "STUDIO_PROJECT_CONTEXT_CONFLICT")
    assert json.loads(path.read_text(encoding="utf-8")) == state
    assert _operation(env) == completed and len(_events(env)) == 1


def test_unit_completed_ledger_hash_tampering_blocks_replay_ack(unit_bootstrap):
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    completed = _bootstrap(env, approved)
    with _db(env, ledger=True) as conn:
        conn.execute("UPDATE decision_ledger_events SET event_hash=? WHERE event_id=?", ("0" * 64, completed["event_id"]))
    _error(lambda: _bootstrap(env, approved), "ADVISOR_LEDGER_INTEGRITY", 503)
    assert _operation(env) == completed


def test_unit_fixed_ledger_id_conflict_is_blocked_not_generic_retryable_io(unit_bootstrap):
    from core.advisor_bootstrap_ledger import append_bootstrap_once
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    reserved = _reserve(env, approved)
    payload = env.bootstrap._ledger_payload(approved, reserved, "default")
    payload["rationale"] = "합성 충돌 사건: 다른 고정 요청 본문"
    event = append_bootstrap_once(env.ledger, reserved["event_id"], **payload)
    _error(lambda: _bootstrap(env, approved), "ADVISOR_LEDGER_IDEMPOTENCY_CONFLICT", 409)
    assert _operation(env)["stage"] == "FAILED_BLOCKED"
    assert len(_events(env)) == 1 and _events(env)[0]["event_id"] == event["event_id"]
    assert all(value["setup_status"] == "SETUP_INCOMPLETE" for value in _files(env, reserved))


def test_unit_completed_missing_ledger_event_is_not_silently_recreated(unit_bootstrap):
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    completed = _bootstrap(env, approved)
    # 이 시험이 새로 만든 임시 원장만 손상시킨다. 운영/기존 데이터 삭제 없음.
    with _db(env, ledger=True) as conn:
        conn.execute("DELETE FROM decision_ledger_events WHERE event_id=?", (completed["event_id"],))
    _error(lambda: _bootstrap(env, approved), "ADVISOR_LEDGER_INTEGRITY", 503)
    assert not _events(env)


def test_unit_ledger_payload_carries_exact_four_key_context(unit_bootstrap):
    from core.studio_drafts import context_key
    env = unit_bootstrap
    approved = _decide(env, _save(env))
    reserved = _reserve(env, approved)
    payload = env.bootstrap._ledger_payload(approved, reserved, "default")
    refs = payload["evidence_refs"] + payload["input_version_refs"] + payload["output_version_refs"]
    assert any(ref.get("context_key") == context_key(env.boundary) for ref in refs), "원장 요청에 root를 포함한 exact 4키 필요"


def test_unit_later_approved_draft_never_replaces_old_fixed_approval(unit_bootstrap):
    env = unit_bootstrap
    first = _decide(env, _save(env))
    first_op = _bootstrap(env, first)
    new_draft = _save(env, first, patch=[{"op": "SET", "path": ["title"], "value": "다음 판본"}])
    second = _decide(env, new_draft)
    assert _bootstrap(env, first) == first_op
    second_op = _bootstrap(env, second)
    assert second_op["project_id"] != first_op["project_id"]
    assert _files(env, first_op)[1]["approved_blueprint_revision_id"] == first["revision_id"]
    assert _files(env, second_op)[1]["approved_blueprint_revision_id"] == second["revision_id"]
    assert _count(env, "advisor_v2_bootstraps") == len(_events(env)) == 2


def test_real_process_context_bootstrap_no_data_preserves_run_blockers(real_studio):
    env = _make_bootstrap(real_studio)
    approved = _decide(env, _save(env))
    completed = _bootstrap(env, approved)
    assert completed["stage"] == "COMPLETED" and len(_events(env)) == 1
    assert _bootstrap(env, approved) == completed
    stored_context = _files(env, completed)[1]["process_context"]
    assert stored_context == approved["process_ref"] and stored_context["verified_binding_refs"] == []
    assert "RUN" not in stored_context["permitted_actions"]
    # 준비 완료는 실행 가능 판정이 아니다. 실제 ProcessContext가 여전히 실행을 차단한다.
    _error(lambda: env.processes.revalidate(fixed_context=stored_context, actor=env.author,
                                             current_context=env.context, for_action="RUN"))


def test_real_process_semantic_change_blocks_bootstrap_before_project_io(real_studio):
    env = _make_bootstrap(real_studio)
    approved = _decide(env, _save(env))
    _approve_process(env, _propose(env, [{"op": "SET_USAGE", "process_id": "plan", "enabled": False}], "disable-before-bootstrap"))
    _error(lambda: _bootstrap(env, approved), "PROCESS_DISABLED")
    assert not env.provision.calls and _count(env, "advisor_v2_bootstraps") == 0
    assert not _events(env)


@pytest.fixture
def factory_bootstrap(real_studio, monkeypatch):
    """실제 provision + strict meta IO. 템플릿 인증/실행 가능성은 이 시험 범위가 아니다."""
    from types import SimpleNamespace
    from core import paths, agent_registry
    from api.routes import factory_control as factory

    env = _make_bootstrap(real_studio)
    assert Path(paths.PROJECTS_DIR).resolve().is_relative_to(env.root)
    monkeypatch.setattr(agent_registry, "list_templates", lambda: [{"id": "default"}])
    monkeypatch.setattr(factory, "_capture_runnable_template", lambda _tid: SimpleNamespace(fingerprint="f" * 64))
    env.provision_calls = []

    def actual_provision(project_id, template_id, **kwargs):
        assert Path(factory.workspace_path(project_id)).resolve().is_relative_to(env.root)
        env.provision_calls.append(project_id)
        return factory.provision_project(project_id, template_id, **kwargs)

    env.provision = actual_provision
    env.bootstrap.provision = actual_provision
    return env


def test_real_factory_marker_write_failure_resumes_only_empty_folder_with_same_ids(factory_bootstrap, monkeypatch):
    from core import studio_project_files as files
    env = factory_bootstrap
    approved = _decide(env, _save(env))
    write = files.write_json
    failed_markers = []

    def fail_before_first_marker_write(path, value):
        target = Path(path).resolve()
        assert target.is_relative_to(env.root)
        if target.name == files.MARKER and not failed_markers:
            failed_markers.append(copy.deepcopy(value))
            raise OSError("synthetic failure immediately before marker write")
        return write(path, value)

    monkeypatch.setattr(files, "write_json", fail_before_first_marker_write)
    _error(lambda: _bootstrap(env, approved), "STUDIO_SETUP_IO_FAILED", 503)
    failed = _operation(env)
    folder = _workspace(env, failed)
    assert failed["stage"] == "FAILED_RETRYABLE" and failed["resume_stage"] == "PROVISIONING"
    assert folder.is_dir() and list(folder.iterdir()) == []
    assert not _events(env)
    completed = _bootstrap(env, approved)
    assert completed["stage"] == "COMPLETED"
    assert completed["project_id"] == failed["project_id"] and completed["event_id"] == failed["event_id"]
    assert completed["operation_id"] == failed["operation_id"]
    assert files.read_json(folder / files.MARKER) == failed_markers[0]
    assert all(value["setup_status"] == "READY" for value in _files(env, completed))
    assert env.provision_calls == [failed["project_id"], failed["project_id"]]
    assert _count(env, "advisor_v2_bootstraps") == len(_events(env)) == 1


@pytest.mark.parametrize("entry", ["foreign.test.invalid.txt", ".foreign.test.invalid.tmp", "foreign-directory"])
def test_real_factory_missing_marker_with_foreign_entry_is_preserved_and_blocked(factory_bootstrap, entry):
    from core.studio_project_files import MARKER
    env = factory_bootstrap
    approved = _decide(env, _save(env))
    reserved = _reserve(env, approved)
    folder = _workspace(env, reserved)
    folder.mkdir(parents=True)
    foreign = folder / entry
    if entry == "foreign-directory":
        foreign.mkdir()
        sentinel = foreign / "do-not-overwrite.test.invalid.txt"
    else:
        sentinel = foreign
    sentinel.write_bytes(b"synthetic existing user content")
    _error(lambda: _bootstrap(env, approved), "STUDIO_PROJECT_ID_CONFLICT", 409)
    blocked = _operation(env)
    assert blocked["stage"] == "FAILED_BLOCKED" and blocked["project_id"] == reserved["project_id"]
    assert sentinel.read_bytes() == b"synthetic existing user content"
    assert {p.name for p in folder.iterdir()} == {entry}
    assert not (folder / MARKER).exists() and not (folder / "project_meta.json").exists()
    _error(lambda: _bootstrap(env, approved), "STUDIO_BOOTSTRAP_BLOCKED", 409)
    assert _count(env, "advisor_v2_bootstraps") == 1 and not _events(env)


def _leave_real_factory_marker_hard_kill(env, approved, monkeypatch):
    """실제 Factory의 marker 쓰기 직전/rename 전 하드킬 디스크 상태를 모사한다.

    실제 프로세스를 종료하지 않는다. marker write만 완성 tmp + BaseException으로
    대체하여 saga의 Exception 처리/실패 기록을 건너뛰고, 복구는 실제 구현을 사용한다.
    """
    import os
    from core import studio_project_files as files

    class MarkerHardKill(BaseException):
        pass

    interrupted = []
    write = files.write_json

    def leave_complete_temporary(path, value):
        target = Path(path).resolve()
        assert target.is_relative_to(env.root)
        if target.name != files.MARKER:
            return write(path, value)
        assert not interrupted and not target.exists()
        temporary = target.with_name(target.name + "." + "c" * 32 + ".tmp")
        assert temporary.is_relative_to(env.root)
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        interrupted.append((temporary, copy.deepcopy(value)))
        raise MarkerHardKill("synthetic hard kill after marker tmp flush, before rename")

    with monkeypatch.context() as crash:
        crash.setattr(files, "write_json", leave_complete_temporary)
        with pytest.raises(MarkerHardKill):
            _bootstrap(env, approved)

    stopped = _operation(env)
    folder = _workspace(env, stopped)
    temporary, marker = interrupted[0]
    assert stopped["stage"] == "PROVISIONING"
    assert marker == {"project_id": stopped["project_id"], "operation_id": stopped["operation_id"]}
    assert temporary.parent == folder and set(folder.iterdir()) == {temporary}
    assert json.loads(temporary.read_text(encoding="utf-8")) == marker
    assert not (folder / files.MARKER).exists() and not _events(env)
    assert env.provision_calls == [stopped["project_id"]]
    # 요청 로컬 상태에 의존하지 않고 새 서비스가 저장된 동일 reservation에서 재개한다.
    env.bootstrap = type(env.bootstrap)(drafts=env.drafts, ledger=env.ledger, provision=env.provision)
    return stopped, folder, temporary


def test_real_factory_complete_marker_tmp_hard_kill_recovers_same_ids(factory_bootstrap, monkeypatch):
    from core.studio_project_files import MARKER, read_json
    env = factory_bootstrap
    approved = _decide(env, _save(env))
    stopped, folder, temporary = _leave_real_factory_marker_hard_kill(env, approved, monkeypatch)
    temporary_before = temporary.read_bytes()

    completed = _bootstrap(env, approved)
    assert completed["stage"] == "COMPLETED"
    for field in ("operation_id", "project_id", "event_id"):
        assert completed[field] == stopped[field]
    assert read_json(folder / MARKER) == {
        "project_id": stopped["project_id"], "operation_id": stopped["operation_id"]}
    # recover_marker는 검증된 잔존 tmp도 삭제하지 않고 새 marker를 원자적으로 쓴다.
    assert not temporary.is_symlink() and temporary.read_bytes() == temporary_before
    assert all(value["setup_status"] == "READY" for value in _files(env, completed))
    assert completed["result"]["ledger_acknowledged"] is True
    assert completed["result"]["ledger_event_id"] == stopped["event_id"]
    events = _events(env)
    assert _count(env, "advisor_v2_bootstraps") == len(events) == 1
    assert events[0]["event_id"] == stopped["event_id"]
    assert env.provision_calls == [stopped["project_id"], stopped["project_id"]]
    assert _bootstrap(env, approved) == completed
    assert _events(env) == events and len(env.provision_calls) == 2
    assert temporary.read_bytes() == temporary_before


@pytest.mark.parametrize("residue", [
    "partial-json", "other-operation", "other-project", "extra-field",
    "invalid-tmp-name", "foreign-entry", "symlink", "dangling-symlink",
])
def test_real_factory_untrusted_marker_tmp_is_preserved_and_blocked(factory_bootstrap, monkeypatch, residue):
    from core.studio_project_files import MARKER
    env = factory_bootstrap
    approved = _decide(env, _save(env))
    stopped, folder, temporary = _leave_real_factory_marker_hard_kill(env, approved, monkeypatch)
    target = None
    target_before = None

    if residue == "partial-json":
        temporary.write_bytes(b'{"project_id":')
    elif residue in {"other-operation", "other-project", "extra-field"}:
        marker = json.loads(temporary.read_text(encoding="utf-8"))
        if residue == "extra-field":
            marker["untrusted"] = True
        else:
            field, prefix = ("operation_id", "bop_") if residue == "other-operation" else ("project_id", "prj_")
            marker[field] = prefix + ("1" if marker[field] == prefix + "0" * 32 else "0") * 32
        temporary.write_text(json.dumps(marker), encoding="utf-8")
    elif residue == "invalid-tmp-name":
        temporary = temporary.rename(folder / (MARKER + ".not-32-hex.tmp"))
    elif residue == "foreign-entry":
        (folder / "preserve-user-file.test.invalid.txt").write_bytes(b"synthetic foreign content")
    else:
        import errno
        import os
        # 링크 대상도 fixture tmp 내부다. 프로젝트 밖의 동일 JSON도 신뢰하면 안 된다.
        target = env.root / (stopped["project_id"] + ".marker-target.test.invalid.json")
        assert target.is_relative_to(env.root) and not target.exists()
        if residue == "symlink":
            temporary.rename(target)
            target_before = target.read_bytes()
        else:
            temporary.unlink()  # 이 테스트가 방금 만든 격리 tmp만 제거하여 dangling 링크를 구성한다.
        try:
            temporary.symlink_to(target)
        except OSError as exc:
            if ((os.name == "nt" and getattr(exc, "winerror", None) == 1314)
                    or exc.errno in {errno.ENOSYS, errno.EOPNOTSUPP}):
                pytest.skip("실제 symlink 생성 권한/파일시스템 미지원: main audit에서 별도 확인 필요")
            raise
        assert temporary.is_symlink()

    def snapshot():
        return {path.name: ("symlink", str(path.readlink())) if path.is_symlink()
                else ("file", path.read_bytes()) for path in folder.iterdir()}

    before = snapshot()
    _error(lambda: _bootstrap(env, approved), "STUDIO_PROJECT_ID_CONFLICT", 409)
    blocked = _operation(env)
    assert blocked["stage"] == "FAILED_BLOCKED"
    for field in ("operation_id", "project_id", "event_id"):
        assert blocked[field] == stopped[field]
    assert snapshot() == before
    assert not (folder / MARKER).exists() and not (folder / MARKER).is_symlink()
    assert not (folder / "project_meta.json").exists() and not (folder / "latest_state.json").exists()
    assert env.provision_calls == [stopped["project_id"], stopped["project_id"]]
    _error(lambda: _bootstrap(env, approved), "STUDIO_BOOTSTRAP_BLOCKED", 409)
    assert snapshot() == before and _operation(env) == blocked
    assert len(env.provision_calls) == 2
    assert _count(env, "advisor_v2_bootstraps") == 1 and not _events(env)
    if target is not None:
        if target_before is None:
            assert not target.exists()
        else:
            assert target.read_bytes() == target_before
