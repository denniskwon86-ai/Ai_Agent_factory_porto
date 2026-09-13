"""B5 수정 의견의 실제 HTTP 접수·조회·소비 회귀. 실행/수집은 main 전용.

기존 입력초안의 가벼운 프로젝트/그래프 fixture와 실제 PDP·tmp SQLite를
재사용한다. 키트 seed·LLM·Host·운영 DB·새 검사 인프라는 사용하지 않는다.
접수는 실행 시작이 아니며 WBS의 고정 접수증과 TODO task를 함께 확인한다.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests import org_seed as org
from tests.test_b5_input_drafts import (  # noqa: F401 - 기존 격리 fixture를 그대로 등록
    PROJECT, TASK, api, api_change, api_save, enforced_org, headers,
    isolated_stores, target_get,
)


BASE = f"/api/v1/factory/{PROJECT}/sprint/revision-requests"
FEEDBACK = "구매 결과에 단위와 근거를 함께 표시해 주세요."
REQUEST_FIRST = "b5000000-0000-4000-8000-000000000001"
REQUEST_SECOND = "b5000000-0000-4000-8000-000000000002"
REQUEST_MISSING = "b5000000-0000-4000-8000-000000000099"


@pytest.fixture
def revision_api(api):
    from nodes.utils.wbs_manager import WBSManager
    manager = WBSManager(str(api.root))
    manager.initialize_wbs("합성 수정요청 프로젝트", [dict(
        task_id=TASK, title="원본 결과", goal="변경 전 요구", status="DONE",
        required_agents=["Tech_Lead", "Backend"], artifact_kind="APP")], runtime_contract_profile="v1")
    artifact = api.root / "result.txt"
    artifact.write_text("합성 결과 원본 A", encoding="utf-8")
    api.state["file_index"] = {"result.txt": {"path": "result.txt", "last_hash": "stale-manifest-hash"}}
    api.wbs = api.root / "00_wbs_master_plan.json"
    api.artifact = artifact
    api.wbs_manager = manager
    return api


def success(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "success"
    return payload["data"]


def rejected(response, status, reason=None):
    assert response.status_code == status, response.text
    if reason:
        assert response.json()["detail"]["reason_code"] == reason
    return response


def prepare_request(env, *, key=REQUEST_FIRST, feedback=FEEDBACK):
    descriptor = success(target_get(env, "REVISION_REQUEST"))
    row = success(api_save(env, descriptor["target"], content={"text": feedback},
                           client_request_id="save-" + key))
    body = dict(client_request_id=key, target=copy.deepcopy(row["target"]), feedback=feedback,
                input_draft={name: row[name] for name in ("draft_id", "revision", "digest")})
    return row, body


def post(env, body, *, actor=org.MEMBER_A, scope=None):
    return env.client.post(BASE, json=body, headers={} if actor is None else headers(actor, scope))


def get(env, key, *, actor=org.MEMBER_A, scope=None):
    return env.client.get(BASE + "/" + key, headers={} if actor is None else headers(actor, scope))


def stored_draft(env, row):
    from core.studio_input_drafts import InputDraftStore
    return InputDraftStore(env.env.advisor).get(boundary=row["context_key"], actor=org.MEMBER_A,
        project_id=PROJECT, draft_id=row["draft_id"])


def untouched(env, row):
    """비교 대상은 실제 원문·WBS·초안이다. lock 파일 mtime을 원자성으로 주장하지 않는다."""
    return dict(wbs=env.wbs.read_bytes(), artifact=env.artifact.read_bytes(),
                latest=(env.root / "latest_state.json").read_bytes(), state=copy.deepcopy(env.state),
                draft=stored_draft(env, row))


def tasks(env):
    return json.loads(env.wbs.read_text(encoding="utf-8"))["tasks"]


def assert_receipt(env, receipt, body):
    assert receipt["request_id"] == body["client_request_id"]
    assert receipt["submission_id"]
    assert receipt["project_id"] == PROJECT and receipt["actor_id"] == org.MEMBER_A
    assert receipt["target"] == body["target"]
    assert receipt["feedback"] == body["feedback"].strip()
    assert receipt["input_draft"] == body["input_draft"]
    assert receipt["status"] == "ACCEPTED" and receipt["execution_started"] is False
    assert receipt["created_at"]
    matching = [task for task in tasks(env) if task["task_id"] == receipt["task_id"]]
    assert len(matching) == 1
    assert matching[0]["goal"] == receipt["feedback"] and matching[0]["status"] == "TODO"
    assert matching[0]["studio_revision_submission_id"] == receipt["submission_id"]
    assert matching[0]["studio_revision_request_id"] == receipt["request_id"]
    assert matching[0]["studio_revision_target"] == receipt["target"]
    assert receipt["task_id"] != TASK


def test_actual_save_accept_get_then_explicit_consume_preserves_originals(revision_api):
    env = revision_api
    row, body = prepare_request(env, feedback="  \n" + FEEDBACK + " \n")
    before = untouched(env, row)
    receipt = success(post(env, body))
    assert_receipt(env, receipt, body)
    assert len(tasks(env)) == 2
    assert tasks(env)[0] == json.loads(before["wbs"])["tasks"][0]
    assert stored_draft(env, row) == before["draft"]  # 접수는 자동 consume이 아니다.
    assert env.artifact.read_bytes() == before["artifact"]
    assert env.state == before["state"] and not env.orchestrator.active_tasks
    recorded = untouched(env, row)
    assert success(get(env, body["client_request_id"])) == receipt
    assert untouched(env, row) == recorded
    consumed = success(api_change(env, row, "consume", submission_id=receipt["submission_id"]))
    assert consumed["status"] == "CONSUMED" and consumed["content"] is None
    assert consumed["revision"] == row["revision"] + 1
    assert success(api_change(env, row, "consume", submission_id=receipt["submission_id"])) == consumed
    assert stored_draft(env, row)["content"] == row["content"]
    assert success(get(env, body["client_request_id"])) == receipt
    assert success(post(env, body)) == receipt  # 소비 뒤 재시도도 새 task/접수가 아니다.
    assert env.wbs.read_bytes() == recorded["wbs"] and not env.orchestrator.active_tasks


def test_same_key_retry_is_identical_and_changed_body_is_409_without_second_task(revision_api):
    env = revision_api
    row, body = prepare_request(env)
    receipt = success(post(env, body))
    before = untouched(env, row)
    assert success(post(env, copy.deepcopy(body))) == receipt
    rejected(post(env, {**body, "feedback": "다른 내용"}), 409)
    changed = copy.deepcopy(body)
    changed["target"]["target_digest"] = "0" * 64
    changed["target"]["request_id"] = "artifact_" + changed["target"]["target_digest"]
    rejected(post(env, changed), 409)
    assert untouched(env, row) == before and len(tasks(env)) == 2


def test_different_request_key_for_same_saved_reference_is_409_and_keeps_first_receipt(revision_api):
    env = revision_api
    row, body = prepare_request(env)
    receipt = success(post(env, body))
    before = untouched(env, row)
    rejected(post(env, {**body, "client_request_id": REQUEST_SECOND}),
             409, "REVISION_REQUEST_DRAFT_ALREADY_SUBMITTED")
    rejected(get(env, REQUEST_SECOND), 404)
    assert success(get(env, REQUEST_FIRST)) == receipt
    assert success(post(env, body)) == receipt
    assert untouched(env, row) == before and len(tasks(env)) == 2
    assert stored_draft(env, row)["status"] == "DRAFT"
    assert success(api_change(env, row, "consume", submission_id=receipt["submission_id"]))["status"] == "CONSUMED"


def test_recorded_receipt_is_fixed_after_source_artifact_changes(revision_api):
    env = revision_api
    row, body = prepare_request(env)
    receipt = success(post(env, body))
    env.artifact.write_text("다음 차수의 결과 B", encoding="utf-8")
    current = success(target_get(env, "REVISION_REQUEST"))
    assert current["target"] != row["target"] and current["draft"] is None
    before = untouched(env, row)
    assert success(get(env, body["client_request_id"])) == receipt
    assert success(post(env, body)) == receipt
    assert untouched(env, row) == before
    # 현재 결과를 과거로 돌리는 것이 아니라 실제 접수한 원문과 초안만 소비한다.
    consumed = success(api_change(env, row, "consume", submission_id=receipt["submission_id"]))
    assert consumed["status"] == "CONSUMED"
    assert env.wbs.read_bytes() == before["wbs"] and env.artifact.read_bytes() == before["artifact"]


def test_unrecorded_server_shaped_submission_id_cannot_consume(revision_api):
    env = revision_api
    row, _ = prepare_request(env)
    before = untouched(env, row)
    rejected(api_change(env, row, "consume", submission_id="srr_" + "0" * 32),
             404, "REVISION_REQUEST_NOT_FOUND")
    assert untouched(env, row) == before and stored_draft(env, row)["status"] == "DRAFT"


def test_receipt_cannot_consume_a_later_edited_draft_revision(revision_api):
    env = revision_api
    row, body = prepare_request(env)
    receipt = success(post(env, body))
    current = success(api_save(env, row["target"], draft_id=row["draft_id"], expected_revision=row["revision"],
        expected_digest=row["digest"], client_request_id="after-accept-edit", content={"text": "접수 뒤 별도 의견"}))
    before = untouched(env, row)
    rejected(api_change(env, current, "consume", submission_id=receipt["submission_id"]), 409)
    assert untouched(env, row) == before and stored_draft(env, row)["status"] == "DRAFT"


@pytest.mark.parametrize("damage", ["receipt", "task"])
def test_receipt_or_bound_task_corruption_blocks_get_and_consume_without_repair(revision_api, damage):
    env = revision_api
    row, body = prepare_request(env)
    receipt = success(post(env, body))
    doc = json.loads(env.wbs.read_text(encoding="utf-8"))
    if damage == "receipt":
        doc["studio_revision_requests"][body["client_request_id"]]["receipt"]["feedback"] = "손상된 접수 의견"
    else:
        next(task for task in doc["tasks"] if task["task_id"] == receipt["task_id"])["goal"] = "바뀐 작업 본문"
    env.wbs.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    before = untouched(env, row)
    rejected(get(env, body["client_request_id"]), 503, "REVISION_REQUEST_RECEIPT_UNAVAILABLE")
    rejected(api_change(env, row, "consume", submission_id=receipt["submission_id"]),
             503, "REVISION_REQUEST_RECEIPT_UNAVAILABLE")
    assert untouched(env, row) == before


@pytest.mark.parametrize("change", ["artifact", "draft_revision", "draft_digest", "feedback"])
def test_stale_target_or_input_binding_never_records_or_consumes(revision_api, change):
    env = revision_api
    row, body = prepare_request(env)
    if change == "artifact":
        env.artifact.write_text("현재 결과가 이미 바뀜", encoding="utf-8")
    elif change == "draft_revision":
        success(api_save(env, row["target"], draft_id=row["draft_id"], expected_revision=row["revision"],
            expected_digest=row["digest"], client_request_id="save-new", content={"text": "새 의견"}))
    elif change == "draft_digest":
        body["input_draft"]["digest"] = "0" * 64
    else:
        body["feedback"] = "저장 초안과 다른 의견"
    before = untouched(env, row)
    rejected(post(env, body), 409)
    rejected(get(env, body["client_request_id"]), 404)
    assert untouched(env, row) == before and len(tasks(env)) == 1


@pytest.mark.parametrize("operation", ["discard", "consume"])
def test_closed_input_draft_cannot_be_submitted_as_new_request(revision_api, operation):
    env = revision_api
    row, body = prepare_request(env)
    if operation == "discard":
        success(api_change(env, row, "discard"))
    else:
        receipt = success(post(env, body))
        success(api_change(env, row, "consume", submission_id=receipt["submission_id"]))
    before = untouched(env, row)
    rejected(post(env, {**body, "client_request_id": REQUEST_SECOND}), 409)
    rejected(get(env, REQUEST_SECOND), 404)
    assert untouched(env, row) == before


@pytest.mark.parametrize("actor,status", [(None, 401), (org.VIEWER_A, 403), (org.MEMBER_B, 404), (org.MANAGER_A, 404)])
def test_post_uses_real_principal_project_scope_and_personal_draft_owner(revision_api, actor, status):
    env = revision_api
    row, body = prepare_request(env)
    before = untouched(env, row)
    rejected(post(env, body, actor=actor), status)
    assert untouched(env, row) == before
    rejected(get(env, body["client_request_id"]), 404)


@pytest.mark.parametrize('busy', ['command', 'reconcile'])
def test_invisible_project_never_leaks_command_reservation(revision_api, busy):
    from core.studio_execution_guard import command, reconcile
    env = revision_api
    row, body = prepare_request(env)
    before = untouched(env, row)
    guard = command(env.orchestrator, PROJECT, exclusive=True) if busy == 'command' else reconcile(env.orchestrator, PROJECT)
    with guard:
        result = post(env, body, actor=org.MEMBER_B)
        rejected(result, 404)
        assert 'BUSY' not in result.text and FEEDBACK not in result.text
    assert untouched(env, row) == before


def test_receipt_get_hides_other_actor_context_and_unknown_request(revision_api):
    env = revision_api
    row, body = prepare_request(env)
    receipt = success(post(env, body))
    before = untouched(env, row)
    for response in (get(env, body["client_request_id"], actor=org.MANAGER_A),
                     get(env, body["client_request_id"], scope=org.NODES[org.DEPT_B]),
                     get(env, REQUEST_MISSING)):
        rejected(response, 404)
        assert receipt["submission_id"] not in response.text and FEEDBACK not in response.text
    rejected(get(env, body["client_request_id"], actor=None), 401)
    assert untouched(env, row) == before


def test_next_post_observes_real_write_permission_revocation(revision_api):
    from core.org_directory import org_directory
    env = revision_api
    row, body = prepare_request(env)
    org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
    before = untouched(env, row)
    rejected(post(env, body), 403)
    rejected(get(env, body["client_request_id"]), 404)
    assert untouched(env, row) == before


def test_accepted_receipt_get_does_not_require_current_run_permission(revision_api):
    from core.org_directory import org_directory
    env = revision_api
    row, body = prepare_request(env)
    receipt = success(post(env, body))
    org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
    before = untouched(env, row)
    assert success(get(env, body["client_request_id"])) == receipt
    rejected(post(env, {**body, "client_request_id": REQUEST_SECOND}), 403)
    assert untouched(env, row) == before


def test_receipt_read_and_post_do_not_downgrade_unproven_managed_project_to_legacy(revision_api):
    env = revision_api
    row, body = prepare_request(env)
    success(post(env, body))
    metadata = env.root / "project_meta.json"
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    meta["runtime_document_version"] = "2.0"
    metadata.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    before = untouched(env, row)
    rejected(get(env, body["client_request_id"]), 409, "STUDIO_PROJECT_PROVENANCE_REQUIRED")
    rejected(post(env, body), 409, "STUDIO_PROJECT_PROVENANCE_REQUIRED")
    assert untouched(env, row) == before


@pytest.mark.parametrize("change,status", [("permission", 403), ("artifact", 409), ("draft", 409)])
def test_acceptance_rechecks_authority_artifact_and_draft_at_final_write(revision_api, monkeypatch, change, status):
    from core import studio_revision_requests as requests
    from core.org_directory import org_directory
    from core.studio_input_drafts import InputDraftStore
    env = revision_api
    row, body = prepare_request(env)
    original = requests.accept_request
    observed = []

    def changed_after_initial_checks(workspace_root, **kwargs):
        if change == "permission":
            org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
        elif change == "artifact":
            env.artifact.write_text("접수 직전 다른 결과", encoding="utf-8")
        else:
            InputDraftStore(env.env.advisor).mutate(boundary=row["context_key"], actor=org.MEMBER_A,
                project_id=PROJECT, operation="SAVE", draft_id=row["draft_id"], expected_revision=row["revision"],
                expected_digest=row["digest"], client_request_id="racing-draft-edit", target=row["target"],
                content={"text": "접수 직전 편집한 의견"})
        observed.append(untouched(env, row))
        return original(workspace_root, **kwargs)
    monkeypatch.setattr(requests, "accept_request", changed_after_initial_checks)
    rejected(post(env, body), status)
    assert len(observed) == 1 and untouched(env, row) == observed[0]
    rejected(get(env, body["client_request_id"]), 404)
    assert stored_draft(env, row)["status"] == "DRAFT" and len(tasks(env)) == 1


@pytest.mark.parametrize("change", ["graph_task", "wbs_task"])
def test_target_must_still_belong_to_actual_graph_and_wbs(revision_api, change):
    env = revision_api
    row, body = prepare_request(env)
    if change == "graph_task":
        env.state["current_sprint_task_id"] = "TASK-OTHER"
    else:
        doc = json.loads(env.wbs.read_text(encoding="utf-8"))
        doc["tasks"][0]["task_id"] = "TASK-OTHER"
        env.wbs.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    before = untouched(env, row)
    rejected(post(env, body), 409)
    rejected(get(env, body["client_request_id"]), 404)
    assert untouched(env, row) == before


@pytest.mark.parametrize("busy", ["active", "reserved"])
def test_running_or_reserved_execution_blocks_new_acceptance(revision_api, busy):
    from core.studio_execution_guard import command
    env = revision_api
    row, body = prepare_request(env)
    before = untouched(env, row)
    if busy == "active":
        # 실제 engine을 실행하지 않고 기존 active registry의 running 관측만 명시 대역.
        from types import SimpleNamespace
        key = PROJECT + "__" + TASK
        env.orchestrator.active_tasks[key] = SimpleNamespace(done=lambda: False)
        env.orchestrator.task_projects[key] = PROJECT
        try:
            rejected(post(env, body), 409, "STUDIO_COMMAND_BUSY")
        finally:
            env.orchestrator.active_tasks.clear()
            env.orchestrator.task_projects.clear()
    else:
        with command(env.orchestrator, PROJECT):
            rejected(post(env, body), 409, "STUDIO_COMMAND_BUSY")
    rejected(get(env, body["client_request_id"]), 404)
    assert untouched(env, row) == before


@pytest.mark.parametrize("raw", ["{", '{"tasks": {}}', '{"tasks": [{"task_id":"TASK-01"},{"task_id":"TASK-01"}]}'])
def test_corrupt_wbs_is_503_without_empty_replacement_or_consumption(revision_api, raw):
    env = revision_api
    row, body = prepare_request(env)
    env.wbs.write_text(raw, encoding="utf-8")
    before = untouched(env, row)
    rejected(post(env, body), 503)
    assert untouched(env, row) == before


def test_atomic_replace_failure_leaves_no_receipt_and_no_added_task(revision_api, monkeypatch):
    env = revision_api
    row, body = prepare_request(env)
    before = untouched(env, row)
    original = os.replace
    attempts = []

    def unavailable(source, destination):
        if Path(destination).resolve() == env.wbs.resolve():
            attempts.append(Path(source))
            raise OSError("합성 WBS 원자 교체 실패")
        return original(source, destination)
    monkeypatch.setattr(os, "replace", unavailable)
    rejected(post(env, body), 503)
    assert len(attempts) == 1
    rejected(get(env, body["client_request_id"]), 404)
    assert untouched(env, row) == before


def test_response_unknown_after_atomic_replace_is_recovered_by_get_without_duplicate(revision_api, monkeypatch):
    env = revision_api
    row, body = prepare_request(env)
    original = os.replace
    writes = []

    def lost_ack(source, destination):
        result = original(source, destination)
        if Path(destination).resolve() == env.wbs.resolve() and not writes:
            writes.append(True)
            raise OSError("합성 교체 완료 후 응답 유실")
        return result
    monkeypatch.setattr(os, "replace", lost_ack)
    rejected(post(env, body), 503)
    assert writes == [True]
    receipt = success(get(env, body["client_request_id"]))
    assert_receipt(env, receipt, body)
    before = untouched(env, row)
    assert success(post(env, body)) == receipt
    assert untouched(env, row) == before and len(tasks(env)) == 2


def test_external_wbs_edit_before_replace_is_preserved_instead_of_overwritten(revision_api, monkeypatch):
    from core import studio_revision_requests as requests
    env = revision_api
    row, body = prepare_request(env)
    original = requests.accept_request
    observed = []

    def concurrent_writer(workspace_root, **kwargs):
        check = kwargs["before_write"]

        @contextmanager
        def before_write(replay):
            with check(replay):
                if replay:
                    yield
                    return
                # FileLock을 따르지 않는 외부 편집도 최소 CAS로 덮어쓰지 않는다.
                doc = json.loads(env.wbs.read_text(encoding="utf-8"))
                doc["tasks"][0]["goal"] = "외부 작성자가 확정한 원문"
                env.wbs.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                observed.append(env.wbs.read_bytes())
                yield
        return original(workspace_root, **{**kwargs, "before_write": before_write})
    monkeypatch.setattr(requests, "accept_request", concurrent_writer)
    original_draft = stored_draft(env, row)
    rejected(post(env, body), 409, "REVISION_REQUEST_CONFLICT")
    assert len(observed) == 1 and env.wbs.read_bytes() == observed[0]
    rejected(get(env, body["client_request_id"]), 404)
    assert stored_draft(env, row) == original_draft and len(tasks(env)) == 1


@pytest.mark.parametrize("same_key", [True, False])
def test_real_wbs_lock_accepts_saved_reference_once_under_concurrent_requests(revision_api, same_key):
    """HTTP 권한/예약은 위 시험, 여기서는 독립 WBSManager 사이 실제 파일 락을 검증한다."""
    from core import studio_revision_requests as requests
    from core.studio_input_drafts import InputDraftStore
    from nodes.utils.wbs_manager import WBSManager
    env = revision_api
    row, first = prepare_request(env)
    bodies = [{**copy.deepcopy(first), "client_request_id": REQUEST_FIRST if same_key else
               f"b5000000-0000-4000-8000-{number:012d}"} for number in range(1, 5)]
    barrier = threading.Barrier(len(bodies))
    storage = InputDraftStore(env.env.advisor)
    before = untouched(env, row)

    def accept(body):
        manager = WBSManager(str(env.root))

        @contextmanager
        def before_write(replay):
            with storage.transaction() as conn:
                current = storage._get(conn, storage._key(row["context_key"], org.MEMBER_A, PROJECT), row["draft_id"])
                requests.verify_input_draft(current, body)
                yield
        barrier.wait(timeout=5)
        try:
            return manager.accept_revision_request(project_id=PROJECT, actor_id=org.MEMBER_A,
                boundary=row["context_key"], submission=body, before_write=before_write)
        except requests.ProcessError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=len(bodies)) as pool:
        futures = [pool.submit(accept, body) for body in bodies]
        results = [future.result(timeout=15) for future in futures]
    receipts = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, requests.ProcessError)]
    assert len(receipts) == (4 if same_key else 1)
    assert len(failures) == (0 if same_key else 3)
    assert all(receipt == receipts[0] for receipt in receipts)
    assert all(exc.status_code == 409 and exc.reason_code == "REVISION_REQUEST_DRAFT_ALREADY_SUBMITTED"
               for exc in failures)
    assert len(tasks(env)) == 2 and len({task["task_id"] for task in tasks(env)}) == 2
    assert tasks(env)[0] == json.loads(before["wbs"])["tasks"][0]
    assert stored_draft(env, row) == before["draft"]
    assert env.artifact.read_bytes() == before["artifact"] and env.state == before["state"]
    for body, result in zip(bodies, results):
        if isinstance(result, dict):
            assert_receipt(env, result, body)
            assert success(get(env, body["client_request_id"])) == result
        else:
            rejected(get(env, body["client_request_id"]), 404)
    assert not env.orchestrator.active_tasks


def test_http_cancellation_keeps_reservation_until_atomic_worker_finishes(revision_api, monkeypatch):
    """기존 finish_before_cancel 경계를 실제 ASGI 요청과 WBS 교체까지 연결한다."""
    import httpx
    env = revision_api
    row, body = prepare_request(env)
    original = os.replace
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def paused_replace(source, destination):
        if Path(destination).resolve() != env.wbs.resolve():
            return original(source, destination)
        entered.set()
        assert release.wait(timeout=10), "회귀가 WBS 교체 worker를 회수하지 못했습니다"
        result = original(source, destination)
        finished.set()
        return result
    monkeypatch.setattr(os, "replace", paused_replace)

    async def scenario():
        transport = httpx.ASGITransport(app=env.client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            caller = asyncio.create_task(client.post(BASE, json=body, headers=headers()))
            try:
                assert await asyncio.to_thread(entered.wait, 5), "원자 WBS 교체에 도달하지 않았습니다"
                for _ in range(2):
                    assert caller.cancel()
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)
                    assert not caller.done() and not finished.is_set()
                    competing = await client.post(BASE, json={**body, "client_request_id": REQUEST_SECOND},
                                                  headers=headers())
                    rejected(competing, 409, "STUDIO_COMMAND_BUSY")
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(asyncio.shield(caller), timeout=5)
                assert finished.is_set()
                receipt = success(await client.get(BASE + "/" + body["client_request_id"], headers=headers()))
                assert_receipt(env, receipt, body)
                rejected(await client.get(BASE + "/" + REQUEST_SECOND, headers=headers()), 404)
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(caller, return_exceptions=True), timeout=5)
    asyncio.run(scenario())
    before = untouched(env, row)
    receipt = success(get(env, body["client_request_id"]))
    assert success(post(env, body)) == receipt
    assert untouched(env, row) == before and len(tasks(env)) == 2
    assert not env.orchestrator.active_tasks
    assert not env.orchestrator._studio_commands.get(PROJECT)


@pytest.mark.parametrize("extra", [{"actor_id": org.ADMIN}, {"execution_started": True}, {"submission_id": "forged"}])
def test_closed_request_schema_rejects_server_owned_fields(revision_api, extra):
    env = revision_api
    row, body = prepare_request(env)
    before = untouched(env, row)
    rejected(post(env, {**body, **extra}), 422)
    assert untouched(env, row) == before


def test_revision_endpoint_rejects_an_actual_clarification_target(revision_api):
    env = revision_api
    row, body = prepare_request(env)
    clarification = success(target_get(env, "CLARIFICATION"))["target"]
    before = untouched(env, row)
    rejected(post(env, {**body, "target": clarification}), 422)
    assert untouched(env, row) == before
    rejected(get(env, body["client_request_id"]), 404)


@pytest.mark.parametrize("feedback", ["", " \n\t", "x" * 32001])
def test_feedback_requires_nonempty_trimmed_bounded_text(revision_api, feedback):
    env = revision_api
    row, body = prepare_request(env)
    before = untouched(env, row)
    rejected(post(env, {**body, "feedback": feedback}), 422)
    assert untouched(env, row) == before
