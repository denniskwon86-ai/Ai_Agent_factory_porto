"""B5 입력 초안 집중 시험. 실행은 main의 기존 격리 런너만 담당한다.

기존 tmp SQLite/PDP fixture를 사용한다. 그래프만 명시 메모리 대역이며
실제 LLM·운영DB·새 검증 인프라를 사용하지 않는다.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import org_seed as org
from tests.test_b3_studio_drafts import isolated_stores, enforced_org  # noqa: F401
from tests.test_b1_process_configuration import headers


PROJECT, TASK = "B5_INPUT_TEST", "TASK-01"
URL = f"/api/v1/factory/{PROJECT}/input-drafts"
QUESTIONS = [{"id": "Q1", "question": "범위?", "multi": False,
              "options": [{"label": "구매"}, {"label": "재고"}]},
             {"id": "Q2", "question": "대상?", "multi": True,
              "options": [{"label": "원료"}, {"label": "부자재"}]}]


@pytest.fixture
def storage(isolated_stores):
    from core.studio_input_drafts import InputDraftStore, digest
    boundary = dict(ownership=dict(tenant_id="test-tenant", enterprise_scope_id="scope-A", entity_mode="REAL"),
                    viewing_context=dict(tenant_id="test-tenant", scope_node_id="scope-A", entity_mode="REAL"), process_context={})
    target = dict(kind="CLARIFICATION", task_id=TASK, decision_kind="", subject_id="",
                  request_id="round-A", target_digest=digest(QUESTIONS))
    args = dict(boundary=boundary, actor="author@test.invalid", project_id=PROJECT)
    body = dict(operation="SAVE", draft_id="", expected_revision=0, expected_digest="",
                client_request_id="save-1", target=target,
                content=dict(text="추가 의견", decision="", selections={"Q1": ["구매"]}))
    return SimpleNamespace(env=isolated_stores, store=InputDraftStore(isolated_stores.advisor), args=args, body=body)


def save_store(env, **changes):
    return env.store.mutate(**env.args, **{**env.body, **changes})


def change_store(env, row, operation="DISCARD", **changes):
    return env.store.mutate(**env.args, **dict(operation=operation, draft_id=row["draft_id"],
        expected_revision=row["revision"], expected_digest=row["digest"], client_request_id="close-1", **changes))


def test_store_saved_selection_survives_new_store_and_same_request_retry(storage):
    from core.studio_input_drafts import InputDraftStore
    row = save_store(storage)
    reopened = InputDraftStore(storage.env.advisor)
    current = reopened.get(**storage.args, draft_id=row["draft_id"])
    assert reopened.public(current) == row
    assert save_store(storage) == row and row["revision"] == 1
    assert row["content"]["selections"] == {"Q1": ["구매"]}
    with storage.env.advisor._connect() as conn:
        for table in ("solution_blueprints", "advisor_v2_drafts", "advisor_v2_bootstraps"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("changes", [{"actor": "other@test.invalid"}, {"project_id": "other-project"},
    {"boundary": {"ownership": {"tenant_id": "other"}}}])
def test_store_exact_user_project_context_isolation(storage, changes):
    from core.studio_input_drafts import InputDraftError
    row = save_store(storage)
    with pytest.raises(InputDraftError) as exc:
        storage.store.get(**{**storage.args, **changes}, draft_id=row["draft_id"])
    assert exc.value.status_code == 404


def test_store_cas_conflict_and_reused_request_with_changed_input(storage):
    from core.studio_input_drafts import InputDraftError
    row = save_store(storage)
    with pytest.raises(InputDraftError, match="같은 요청"):
        save_store(storage, content={"text": "덮어쓰기"})
    updated = save_store(storage, draft_id=row["draft_id"], expected_revision=1, expected_digest=row["digest"],
                         client_request_id="save-2", content={"text": "두 번째"})
    with pytest.raises(InputDraftError) as exc:
        save_store(storage, draft_id=row["draft_id"], expected_revision=1, expected_digest=row["digest"], client_request_id="stale")
    assert exc.value.reason_code == "INPUT_DRAFT_REVISION_CONFLICT"
    with pytest.raises(InputDraftError) as exc:
        save_store(storage)
    assert exc.value.reason_code == "INPUT_DRAFT_REQUEST_SUPERSEDED"
    assert updated["revision"] == 2


def test_store_cannot_duplicate_active_target_or_copy_draft_to_new_round(storage):
    from core.studio_input_drafts import InputDraftError
    row = save_store(storage)
    with pytest.raises(InputDraftError) as exc:
        save_store(storage, client_request_id="duplicate")
    assert exc.value.reason_code == "INPUT_DRAFT_ACTIVE_EXISTS"
    with pytest.raises(InputDraftError) as exc:
        save_store(storage, draft_id=row["draft_id"], expected_revision=1, expected_digest=row["digest"],
                   client_request_id="copy", target={**row["target"], "request_id": "new-round"})
    assert exc.value.reason_code == "INPUT_DRAFT_TARGET_CONFLICT"


def test_store_discard_is_explicit_cas_and_preserves_server_content(storage):
    row = save_store(storage)
    closed = change_store(storage, row)
    assert closed["status"] == "DISCARDED" and not closed["restorable"] and closed["content"] is None
    assert change_store(storage, row) == closed
    stored = storage.store.get(**storage.args, draft_id=row["draft_id"])
    assert stored["content"] == row["content"]
    assert storage.store.active(**storage.args, target=row["target"]) is None


def test_store_consume_requires_exact_server_verified_submission(storage):
    from core.studio_input_drafts import InputDraftError
    row = save_store(storage)
    for proof in (None, {"submitted": True}, {"submission_id": "event", "draft_id": row["draft_id"], "draft_digest": "wrong"}):
        with pytest.raises(InputDraftError) as exc:
            change_store(storage, row, "CONSUME", submission_id="event", verified=proof)
        assert exc.value.status_code == 503
    assert storage.store.get(**storage.args, draft_id=row["draft_id"])["status"] == "DRAFT"


@pytest.mark.parametrize("selections", [{"fake": ["구매"]}, {"Q1": ["위조"]}, {"Q1": ["구매", "재고"]},
                                        {"Q2": ["원료", "원료"]}])
def test_selection_validation_uses_actual_question_id_label_and_multi(storage, selections):
    from core.studio_input_drafts import InputDraftError, validate_selections
    with pytest.raises(InputDraftError) as exc:
        validate_selections(storage.body["target"], {"selections": selections}, QUESTIONS)
    assert exc.value.status_code == 422


def test_selections_allow_partial_empty_and_multiple_where_server_allows(storage):
    from core.studio_input_drafts import validate_selections
    for selections in ({}, {"Q1": []}, {"Q2": ["원료", "부자재"]}):
        validate_selections(storage.body["target"], {"selections": selections}, QUESTIONS)


@pytest.fixture
def api(isolated_stores, enforced_org, monkeypatch):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import factory_control as factory
    from core import advisor_store, decision_ledger
    from core.async_orchestrator import AsyncFactoryOrchestrator
    from core.paths import workspace_path

    env = isolated_stores
    monkeypatch.setattr(advisor_store, "advisor_store", env.advisor)
    monkeypatch.setattr(decision_ledger, "decision_ledger", env.ledger)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "")
    monkeypatch.setattr(config, "ECM_DEFAULT_TENANT_ID", "tenant_default")
    root = Path(workspace_path(PROJECT))
    root.mkdir(parents=True)
    boundary = dict(tenant_id="tenant_default", enterprise_scope_id=org.NODES[org.DEPT_A], entity_mode="REAL")
    meta = {**boundary, "runtime_document_version": "1.0", "owner_dept_id": org.DEPT_A,
            "owner_user_id": "", "visibility": "dept"}
    (root / "project_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    state = dict(workspace_root=str(root), runtime_document_version="1.0", current_sprint_task_id=TASK,
                 factory_mode="PLANNING", current_stage="CLARIFICATION", clarification_questions=copy.deepcopy(QUESTIONS),
                 artifacts={"Reviewer": "합성 현재 결과"}, file_index={})
    (root / "latest_state.json").write_text(json.dumps(state), encoding="utf-8")
    snapshot = SimpleNamespace(values=state, next=("rfp",), config={"configurable": {"checkpoint_id": "checkpoint-A"}})
    engine_calls = []
    async def aget_state(cfg):
        assert cfg["configurable"]["thread_id"] == f"sprint_{PROJECT}__{TASK}"
        engine_calls.append(cfg)
        return snapshot
    async def no_write(*args, **kwargs):
        pytest.fail("초안 API는 그래프 상태를 쓰거나 실행할 수 없다")
    engine = SimpleNamespace(aget_state=aget_state, aupdate_state=no_write, astream=no_write)
    orchestrator = AsyncFactoryOrchestrator()
    async def bound(project_id):
        assert project_id == PROJECT
        return engine
    monkeypatch.setattr(orchestrator, "_bound_engine", bound)
    monkeypatch.setattr(factory, "orchestrator", orchestrator)
    app = FastAPI()
    app.include_router(factory.router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, root=root, env=env, boundary=boundary, state=state,
                              snapshot=snapshot, orchestrator=orchestrator, calls=engine_calls)


def target_get(api, kind="CLARIFICATION", actor=None, **query):
    return api.client.get(URL + "/target", params=dict(kind=kind, task_id=TASK, **query),
                          headers=headers(actor or org.MEMBER_A))


def api_save(api, target=None, **changes):
    if target is None:
        response = target_get(api)
        assert response.status_code == 200, response.text
        target = response.json()["data"]["target"]
    body = dict(target=target, content={"text": "추가 의견", "selections": {"Q1": ["구매"]}},
                draft_id="", expected_revision=0, expected_digest="", client_request_id="api-save")
    return api.client.post(URL, json={**body, **changes}, headers=headers(org.MEMBER_A))


def api_change(api, row, operation, **fields):
    return api.client.post(URL + f"/{row['draft_id']}/{operation}", json=dict(expected_revision=row["revision"],
        expected_digest=row["digest"], client_request_id="api-" + operation, **fields), headers=headers(org.MEMBER_A))


def test_api_current_target_get_is_read_only_then_restores_structured_selection(api):
    first = target_get(api)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["draft"] is None
    with api.env.advisor._connect() as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='studio_input_drafts'").fetchone() is None
    response = api_save(api)
    assert response.status_code == 200, response.text
    row = response.json()["data"]
    assert api_save(api).json()["data"] == row
    get = api.client.get(URL + "/" + row["draft_id"], headers=headers(org.MEMBER_A))
    assert get.status_code == 200, get.text
    assert get.json()["data"]["content"]["selections"] == {"Q1": ["구매"]}
    assert target_get(api).json()["data"]["draft"] == row
    assert not api.orchestrator.active_tasks


def test_api_same_questions_new_checkpoint_cannot_restore_or_copy_old_input(api):
    row = api_save(api).json()["data"]
    api.snapshot.config["configurable"]["checkpoint_id"] = "checkpoint-B"
    response = api.client.get(URL + "/" + row["draft_id"], headers=headers(org.MEMBER_A))
    assert response.status_code == 409 and "추가 의견" not in response.text
    target = target_get(api).json()["data"]
    assert target["draft"] is None and target["target"]["request_id"] != row["target"]["request_id"]
    copied = api_save(api, target["target"], draft_id=row["draft_id"], expected_revision=1,
                      expected_digest=row["digest"], client_request_id="copy")
    assert copied.status_code == 409
    assert api_change(api, row, "discard").status_code == 200


@pytest.mark.parametrize("content", [{"text": "", "selections": {"Q1": ["없는 선택"]}},
    {"text": "", "selections": {"없는 질문": []}}, {"text": "", "actor": "other"},
    {"text": "", "selections": {"Q1": ["구매", "재고"]}}, {"text": "", "decision": "APPROVE"}])
def test_api_invalid_clarification_content_is_422_without_save(api, content):
    response = api_save(api, content=content)
    assert response.status_code == 422, response.text
    assert target_get(api).json()["data"]["draft"] is None


def test_api_current_artifact_descriptor_changes_with_actual_file_bytes(api):
    from core.studio_input_drafts import InputDraftStore
    file = api.root / "result.txt"
    file.write_text("합성 결과 A", encoding="utf-8")
    api.state["file_index"] = {"result.txt": {"path": "result.txt", "last_hash": "old-hash"}}
    first = target_get(api, "REVISION_REQUEST").json()["data"]
    assert first["consume_supported"] is True
    saved = api_save(api, first["target"], content={"text": "이 결과의 수정 의견"}).json()["data"]
    store = InputDraftStore(api.env.advisor)
    identity = dict(boundary=saved["context_key"], actor=org.MEMBER_A, project_id=PROJECT, draft_id=saved["draft_id"])
    before = store.get(**identity)
    file.write_text("합성 결과 B", encoding="utf-8")
    second = target_get(api, "REVISION_REQUEST").json()["data"]
    assert first["target"]["target_digest"] != second["target"]["target_digest"] and second["draft"] is None
    assert api.client.get(URL + "/" + saved["draft_id"], headers=headers(org.MEMBER_A)).status_code == 409
    # 실제 WBS에 구형 작업 ID가 있어도, 고정 접수증 없이 제출 증거가 되지는 않는다.
    (api.root / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [
        {"task_id": TASK}, {"task_id": "TASK_REV_01"}], "total_tasks": 2}), encoding="utf-8")
    result = api_change(api, saved, "consume", submission_id="TASK_REV_01")
    assert result.status_code == 422, result.text
    assert result.json()["detail"]["reason_code"] == "REVISION_REQUEST_INVALID"
    after = store.get(**identity)
    assert after == before and after["status"] == "DRAFT"
    assert after["content"] == saved["content"] and after["target"] == saved["target"]
    assert not api.orchestrator.active_tasks


def test_api_artifact_path_escape_and_foreign_checkpoint_are_rejected(api):
    api.state["file_index"] = {"outside": {"path": "../outside.txt"}}
    assert target_get(api, "REVISION_REQUEST").status_code == 503
    api.state["workspace_root"] = str(api.root.parent / "other")
    assert target_get(api).status_code == 409


def test_api_clarification_submission_claim_cannot_consume(api):
    row = api_save(api).json()["data"]
    response = api_change(api, row, "consume", submission_id="claimed-resume")
    assert response.status_code == 409
    assert target_get(api).json()["data"]["draft"]["status"] == "DRAFT"


@pytest.mark.parametrize("actor,expected", [(None, 401), (org.VIEWER_A, 403), (org.MEMBER_B, 404)])
def test_api_actual_principal_write_and_cross_department_boundary(api, actor, expected):
    target = target_get(api).json()["data"]["target"]
    body = dict(target=target, content={"text": "침범"}, draft_id="", expected_revision=0,
                expected_digest="", client_request_id="bad-actor")
    response = api.client.post(URL, json=body, headers=headers(actor) if actor else {})
    assert response.status_code == expected, response.text


def test_api_legacy_read_does_not_require_run_but_other_users_draft_is_hidden(api):
    row = api_save(api).json()["data"]
    response = target_get(api, actor=org.VIEWER_A)
    assert response.status_code == 200 and response.json()["data"]["draft"] is None
    assert api.client.get(URL + "/" + row["draft_id"], headers=headers(org.MANAGER_A)).status_code == 404


def test_api_unknown_questions_never_returns_empty_success_or_deletes_draft(api):
    row = api_save(api).json()["data"]
    api.snapshot.config = {}
    assert target_get(api).status_code == 503
    assert api.client.get(URL + "/" + row["draft_id"], headers=headers(org.MEMBER_A)).status_code == 503


def test_api_real_host_ledger_record_is_required_for_consume_even_if_projection_failed(api):
    from core import contract_review_gate as gate
    fp = "a" * 64
    decision = gate.evaluate(requires_contract=True, compiled_fingerprint=fp, approved_fingerprint="")
    request, _ = gate.ensure_review_request(api.env.ledger, decision, project_id=PROJECT, task_ids=[TASK], **api.boundary)
    api.state.update(current_stage="TECH_LEAD", runtime_contract_profile="v1", app_runtime_contract_fingerprint=fp,
                     approved_contract_fingerprint="", app_runtime_contract_status="COMPILED",
                     contract_review_request_event_id=request["event_id"])
    response = target_get(api, "DECISION_COMMENT", decision_kind="HOST_CONTRACT")
    assert response.status_code == 200, response.text
    target = response.json()["data"]["target"]
    response = api_save(api, target, content={"text": "실제 승인 의견", "decision": "APPROVE"})
    assert response.status_code == 200, response.text
    row = response.json()["data"]
    missing = api_change(api, row, "consume", submission_id="missing-event")
    assert missing.status_code == 503
    event = gate.record_decision(api.env.ledger, decision, project_id=PROJECT, request_event_id=request["event_id"],
        approved=True, actor_id=org.MEMBER_A, rationale="실제 승인 의견", task_id=TASK, **api.boundary)
    result = api_change(api, row, "consume", submission_id=event["event_id"])
    assert result.status_code == 200, result.text
    assert result.json()["data"]["status"] == "CONSUMED" and result.json()["data"]["content"] is None
    assert api_change(api, row, "consume", submission_id=event["event_id"]).json()["data"] == result.json()["data"]
    assert len(api.env.ledger.list_events(project_id=PROJECT)) == 2 and not api.orchestrator.active_tasks


def test_api_fresh_permission_revocation_during_target_check_prevents_save(api, monkeypatch):
    from api.routes import studio_input_draft_control as routes
    from core.org_directory import org_directory
    target = target_get(api).json()["data"]["target"]
    original = routes._current
    async def revoke(*args, **kwargs):
        await original(*args, **kwargs)
        org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
    monkeypatch.setattr(routes, "_current", revoke)
    response = api_save(api, target)
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("dataset", [False, True])
def test_api_real_round_decision_consumes_only_matching_actor_content_and_subject(api, dataset):
    from nodes.contract import save_draft
    from core import contract_decision as cd
    from tests.test_b3_decision_round import _draft
    ids = [TASK, "TASK-02"] if dataset else [TASK]
    (api.root / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [
        {"task_id": tid, "artifact_kind": "APP"} for tid in ids]}), encoding="utf-8")
    for tid in ids:
        save_draft(str(api.root), tid, _draft(action="create" if tid == "TASK-02" else "read",
                                            capability="" if dataset else "file.upload"), require_metadata=True)
    pending = cd.pending_for_workspace(api.root, require_metadata=True)
    item = pending["dataset_conflicts" if dataset else "capability_decisions"][0]
    kind = "DATASET" if dataset else "CAPABILITY"
    subject = item["dataset_key"] if dataset else item["capability"]
    query = dict(decision_kind=kind, request_id=item["decision_request_id"], subject_id=subject)
    response = target_get(api, "DECISION_COMMENT", **query)
    assert response.status_code == 200, response.text
    target = response.json()["data"]["target"]
    response = api_save(api, target, content={"text": "이번 차수의 결정 의견", "decision": TASK if dataset else "REDUCE"})
    assert response.status_code == 200, response.text
    row = response.json()["data"]
    args = dict(dataset_key=subject, winner_task_id=TASK) if dataset else dict(task_id=TASK, capability=subject, decision="REDUCE")
    result = api.client.post(f"/api/v1/factory/{PROJECT}/contract-decisions/resolve", json=dict(
        **args, rationale="이번 차수의 결정 의견", decision_request_id=item["decision_request_id"],
        expected_digest=item["expected_digest"]), headers=headers(org.MEMBER_A))
    assert result.status_code == 200, result.text
    event_id = result.json()["data"]["event_id"]
    event = api.env.ledger.get_event_strict(event_id)
    from core.studio_input_drafts import InputDraftError, InputDraftStore, verify_decision_submission
    stored = InputDraftStore(api.env.advisor).get(boundary=row["context_key"], actor=org.MEMBER_A,
                                                 project_id=PROJECT, draft_id=row["draft_id"])
    if dataset:
        # 실제 producer 계약: winner는 입력 판에 있고 변경 task 증거에는 없다.
        assert "task:" + TASK not in event["evidence_refs"]
        assert "task:TASK-02" in event["evidence_refs"]
        assert set(event["input_version_refs"][0]["draft_versions"]) == {TASK, "TASK-02"}
        # 저장 target이 변경 task 쪽이어도 같은 차수·선택의 실제 사건에 결속된다.
        changed_target = copy.deepcopy(stored)
        changed_target["target"]["task_id"] = "TASK-02"
        assert verify_decision_submission(changed_target, event)["submission_id"] == event_id
        for removed in (TASK, "TASK-02"):
            broken = copy.deepcopy(event)
            del broken["input_version_refs"][0]["draft_versions"][removed]
            with pytest.raises(InputDraftError) as exc:
                verify_decision_submission(stored, broken)
            assert exc.value.status_code == 409
        for evidence in (["project:" + PROJECT], ["project:" + PROJECT, "task:" + TASK],
                         ["project:" + PROJECT, "task:FOREIGN_TASK"], ["task:TASK-02"]):
            with pytest.raises(InputDraftError) as exc:
                verify_decision_submission(stored, {**event, "evidence_refs": evidence})
            assert exc.value.status_code == 409
    for field, value in (("decision_request_id", "다른 차수"), ("digest", "f" * 64)):
        broken = copy.deepcopy(event)
        broken["input_version_refs"][0][field] = value
        with pytest.raises(InputDraftError) as exc:
            verify_decision_submission(stored, broken)
        assert exc.value.status_code == 409
    for field, value in (("actor_id", org.MANAGER_A), ("rationale", "다른 의견"), ("subject_id", "다른 대상"),
                         ("tenant_id", "다른 회사"), ("input_version_refs", []), ("evidence_refs", [])):
        with pytest.raises(InputDraftError) as exc:
            verify_decision_submission(stored, {**event, field: value})
        assert exc.value.status_code == 409
    consumed = api_change(api, row, "consume", submission_id=event_id)
    assert consumed.status_code == 200, consumed.text
    assert consumed.json()["data"]["status"] == "CONSUMED"
    assert len(api.env.ledger.list_events(project_id=PROJECT)) == 1


def test_api_managed_marker_without_server_provenance_never_downgrades_to_legacy(api):
    path = api.root / "project_meta.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["runtime_document_version"] = "2.0"
    path.write_text(json.dumps(meta), encoding="utf-8")
    response = target_get(api)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason_code"] == "STUDIO_PROJECT_PROVENANCE_REQUIRED"


def test_store_tampered_content_digest_is_not_restored(storage):
    from core.studio_input_drafts import InputDraftError
    row = save_store(storage)
    with storage.env.advisor._connect() as conn:
        conn.execute("UPDATE studio_input_drafts SET result_json=? WHERE draft_id=?", ('{}', row["draft_id"]))
    with pytest.raises(InputDraftError) as exc:
        storage.store.get(**storage.args, draft_id=row["draft_id"])
    assert exc.value.status_code == 503
