"""B3 서버 cohort·실행 경계 회귀. 실제 임시 승인 저장소/PDP, 실행 엔진은 호출하지 않는다."""
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_b3_studio_drafts import isolated_stores, real_studio, _save, _decide  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


@pytest.fixture
def project(real_studio):
    from core.studio_bootstrap import StudioBootstrapService
    from core.studio_project_files import write_json
    from core.paths import workspace_path

    env = real_studio
    approved = _decide(env, _save(env))

    def provision(project_id, template_id, **fields):
        # 템플릿 해석/오케스트레이터를 대역으로 분리. 승인 DB/PDP/원장/파일 read-back은 실제다.
        root = Path(workspace_path(project_id))
        root.mkdir(parents=True, exist_ok=True)
        meta = {**fields.pop("studio_context"), **fields, "template_id": template_id}
        write_json(root / "project_meta.json", meta)

    service = StudioBootstrapService(drafts=env.drafts, ledger=env.ledger, provision=provision)
    operation = service.bootstrap(boundary=env.boundary, actor=env.author, context=env.context,
        approved_revision_id=approved["revision_id"], approved_digest=approved["digest"],
        expected_process_semantic_digest=approved["process_ref"]["process_semantic_fingerprint"],
        client_request_id="execution-project")
    return SimpleNamespace(**vars(env), operation=operation, approved=approved,
                           project_id=operation["project_id"], workspace=Path(workspace_path(operation["project_id"])))


@pytest.fixture
def incomplete(real_studio, monkeypatch):
    """원장 접수 직전에서 멈춘 프로젝트. 고정 파일은 다 쓰였고 준비만 끝나지 않았다."""
    from tests.test_b3_studio_bootstrap import _make_bootstrap, _bootstrap, _operation
    from core.advisor_revision_store import RevisionStoreError
    from core.paths import workspace_path

    env = _make_bootstrap(real_studio)
    approved = _decide(env, _save(env))

    def unacknowledged(*_, **__):
        raise OSError("원장 접수 실패")

    monkeypatch.setattr(env.bootstrap, "_append_event", unacknowledged)
    with pytest.raises(RevisionStoreError):
        _bootstrap(env, approved)
    operation = _operation(env)
    assert operation["stage"] != "COMPLETED" and operation["resume_stage"] == "LEDGER_PENDING"
    return SimpleNamespace(**vars(env), operation=operation, approved=approved,
                           project_id=operation["project_id"], workspace=Path(workspace_path(operation["project_id"])))


def check(env, action="DRAFT", **changes):
    from core.studio_project_context import project_context
    return project_context(env.project_id, **{"actor": env.author, "context": env.context,
        "for_action": action, "revisions": env.revisions, "processes": env.drafts.processes, **changes})


def test_approved_project_has_server_v2_context_and_real_current_pdp(project):
    result = check(project)
    assert result["runtime_document_version"] == "2.0"
    assert result["process_context"] == project.approved["process_ref"]
    assert result["setup_status"] == "READY"


def test_no_data_project_cannot_generate_or_run_or_release(project):
    from core.enterprise_context.process_schema import ProcessError
    for action in ("GENERATE", "RUN", "RELEASE"):
        with pytest.raises(ProcessError):
            check(project, action, actor=project.reviewer)


def test_incomplete_setup_blocks_every_action_even_with_intact_files(incomplete):
    """저장소는 미완료 단계도 반환한다. 실행 허용 단계 확인은 이 경계의 책임이다."""
    from core.studio_project_files import read_json
    from core.advisor_revision_store import RevisionStoreError
    # 고정 파일은 온전하다. 막는 근거는 파일 손상이 아니라 준비 단계다.
    assert read_json(incomplete.workspace / "project_meta.json")["process_context"] == incomplete.approved["process_ref"]
    for action in ("DRAFT", "GENERATE", "RUN", "RELEASE"):
        with pytest.raises(RevisionStoreError, match="준비"):
            check(incomplete, action, actor=incomplete.reviewer)


@pytest.mark.parametrize("meta", [None, {"runtime_document_version": "1.0"}])
def test_unindexed_restored_state_cannot_downgrade_to_legacy(isolated_stores, meta):
    from core.studio_project_context import project_context
    from core.studio_project_files import write_json
    from core.advisor_revision_store import RevisionStoreError
    from core.paths import workspace_path
    folder = Path(workspace_path("restored-b3-test"))
    folder.mkdir(parents=True)
    write_json(folder / "latest_state.json", {"runtime_document_version": "2.0"})
    if meta is not None:
        write_json(folder / "project_meta.json", meta)
    with pytest.raises(RevisionStoreError, match="복원"):
        project_context("restored-b3-test", actor="test.invalid", context={}, for_action="DRAFT",
                        revisions=isolated_stores.revisions, processes=object())


@pytest.mark.parametrize("release", [None, {}, {"project_id": "legacy", "runtime_contract": {"schema_version": "1.0"}}])
def test_general_release_trusted_id_retains_server_cohort_even_when_markers_lost(project, monkeypatch, release):
    from core.studio_release_context import require_release_context
    from core.advisor_revision_store import RevisionStoreError
    monkeypatch.setattr("core.studio_release_cohort.get_release_cohort", lambda *a: None)
    with pytest.raises(RevisionStoreError):
        require_release_context(release, release_id=project.project_id + "_20260913_000000",
            actor=project.author, context=project.context, revisions=project.revisions,
            processes=project.drafts.processes, store=object())


@pytest.mark.parametrize("name,field", [("project_meta.json", "runtime_document_version"),
    ("project_meta.json", "process_context"), ("latest_state.json", "approved_blueprint_revision_id"),
    ("latest_state.json", "process_context"), ("project_meta.json", "setup_status")])
def test_lost_fixed_fields_never_downgrade_to_legacy(project, name, field):
    from core.studio_project_files import read_json, write_json
    from core.advisor_revision_store import RevisionStoreError
    path = project.workspace / name
    value = read_json(path)
    value.pop(field)
    write_json(path, value)
    with pytest.raises(RevisionStoreError):
        check(project)
    assert project.revisions.is_v2_project(project.project_id)


@pytest.mark.parametrize("field,value", [("approved_blueprint_digest", "f" * 64),
    ("bootstrap_operation_id", "bop_other"), ("owner_user_id", "other@test.invalid"),
    ("tenant_id", "tenant_other")])
def test_matching_tampered_files_cannot_replace_server_provenance(project, field, value):
    from core.studio_project_files import read_json, write_json
    from core.advisor_revision_store import RevisionStoreError
    for name in ("project_meta.json", "latest_state.json"):
        path = project.workspace / name
        document = read_json(path)
        document[field] = value
        write_json(path, document)
    with pytest.raises(RevisionStoreError):
        check(project)


def test_current_context_must_be_explicit_and_foreign_scope_is_hidden(project):
    from core.enterprise_context.process_schema import ProcessError
    for context in ({}, {**project.context, "scope_node_id": ""}, {**project.context, "tenant_id": "other"}):
        with pytest.raises(ProcessError):
            check(project, context=context)


def test_new_head_display_change_does_not_rewrite_fixed_project(project):
    from tests.test_b3_studio_drafts import _approve_process
    env = project
    # B1 명령 API를 실제로 사용한다. 문구 변경은 계약의 의미 변경이 아니다.
    resolved = env.drafts.configurations.resolved(boundary=env.boundary, actor=env.author, context=env.context)
    change = env.drafts.configurations.propose(boundary=env.boundary, actor=env.author, context=env.context,
        commands=[{"op": "RENAME", "process_id": env.selection["process_ids"][0], "label": "이름만 변경"}],
        expected_head_version=resolved["version"], base_profile_id=resolved["profile_id"],
        base_fingerprint=resolved["digest"], client_request_id="execution-rename", reason="표시명 수정")
    _approve_process(env, change)
    assert check(env)["process_context"] == env.approved["process_ref"]


def test_factory_start_ignores_client_cohort_and_context(monkeypatch, isolated_stores):
    from api.routes import factory_control as factory
    from core import studio_project_context
    from core.studio_project_files import STUDIO_FIELDS

    monkeypatch.setattr(factory, "assert_project_writable", lambda *_: None)
    monkeypatch.setattr(studio_project_context, "for_principal", lambda *_: None)
    def stop(_):
        raise RuntimeError("STOP_AFTER_SERVER_INJECTION")
    monkeypatch.setattr(factory, "_read_project_template", stop)
    payload = {k: "FORGED" for k in STUDIO_FIELDS}
    req = factory.SprintStartRequest(task_id="PLANNING_1", project_state_payload=payload)
    with pytest.raises(RuntimeError, match="STOP_AFTER_SERVER_INJECTION"):
        asyncio.run(factory.start_sprint("legacy-unit", req, SimpleNamespace(user_id="member@test.invalid")))
    assert req.project_state_payload["runtime_document_version"] == "1.0"
    assert req.project_state_payload["process_context"] == {}
    assert req.project_state_payload["bootstrap_operation_id"] == ""


def test_resume_rejects_missing_checkpoint_context_before_execution(monkeypatch, isolated_stores):
    from api.routes import factory_control as factory
    from core import studio_project_context
    from fastapi import HTTPException

    server = {"runtime_document_version": "2.0", "process_context": {"server": True},
              "approved_blueprint_revision_id": "ar", "approved_blueprint_digest": "a" * 64,
              "bootstrap_operation_id": "op"}
    monkeypatch.setattr(studio_project_context, "for_principal", lambda *_: server)
    async def checkpoint(*_):
        return {"runtime_document_version": "1.0"}
    monkeypatch.setattr(factory.orchestrator, "read_reconcile_state", checkpoint)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(factory._assert_resumable("new-unit", SimpleNamespace(user_id="member@test.invalid"), "TASK_1"))
    assert exc.value.status_code == 409


def test_host_issue_gate_checks_process_before_materialization(monkeypatch, isolated_stores):
    from core import app_contract_gate, studio_release_context
    from core.enterprise_context.process_schema import ProcessError

    def deny(*_, **__):
        raise ProcessError("PROCESS_DISABLED", "현재 업무 사용 중지")
    monkeypatch.setattr(studio_release_context, "require_release_context", deny)
    monkeypatch.setattr(app_contract_gate, "_materialized", lambda *_: pytest.fail("거부 뒤 물질화 조회 금지"))
    verdict = app_contract_gate.evaluate({"runtime_document_version": "2.0"}, "release.test.invalid", actor="a", context={})
    assert not verdict.ok and verdict.reasons == ["PROCESS_DISABLED"]
