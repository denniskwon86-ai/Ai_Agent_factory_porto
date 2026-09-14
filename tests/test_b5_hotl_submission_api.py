"""B5 저장→실제 HTTP 제출→조회→소비. 조직/PDP/SQLite는 실제 격리 자산이다.

LLM 실행만 명시 대역이며 v2 업무 문맥 시험은 고정 DTO를 주입한다.
scripts/verify_data_usage_holds.py --strict-writes --target으로만 실행한다.
"""
import asyncio
import copy
import uuid

import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import headers
from tests.test_b5_input_drafts import (
    api, isolated_stores, enforced_org, api_save, api_change, target_get,
    PROJECT, TASK, QUESTIONS,
)

BASE = f"/api/v1/factory/{PROJECT}"


@pytest.fixture
def submission(api, monkeypatch):
    from api.routes import factory_control as factory
    from core import contract_review_gate as gate
    calls = []
    async def resumable(*args):
        return None
    async def review(*args, **kwargs):
        return gate.evaluate(requires_contract=False, compiled_fingerprint="", approved_fingerprint=""), {}
    async def resume(*args, **kwargs):
        calls.append((args, kwargs))
        return True
    monkeypatch.setattr(factory, "_assert_resumable", resumable)
    monkeypatch.setattr(factory, "_contract_review_context", review)
    monkeypatch.setattr(api.orchestrator, "resume_hotl", resume)
    api.resume_calls = calls
    return api


def saved_request(api, *, clarify=True):
    from core.clarify_answers import serialize
    if clarify:
        response = api_save(api)
    else:
        api.state["current_stage"] = "QA"
        target = target_get(api, "DECISION_COMMENT", decision_kind="GENERAL_HOTL").json()["data"]["target"]
        response = api_save(api, target, content={"text": "일반 검토 의견"})
    assert response.status_code == 200, response.text
    row = response.json()["data"]
    feedback = serialize(QUESTIONS, row["content"]["selections"], row["content"]["text"]) if clarify else row["content"]["text"]
    body = dict(task_id=TASK, feedback=feedback, expected_request_id=row["target"]["request_id"],
        expected_questions_digest=row["target"]["target_digest"], client_request_id=str(uuid.uuid4()),
        input_draft={k: row[k] for k in ("draft_id", "revision", "digest")})
    return row, body


def submit(api, body, actor=org.MEMBER_A):
    return api.client.post(BASE + "/hotl/resume", json=body, headers=headers(actor))


@pytest.mark.parametrize("mode", ["legacy-clarify", "managed-clarify", "general"])
def test_saved_draft_http_submit_read_consume_and_replay_after_round_disappears(submission, monkeypatch, mode):
    api = submission
    if mode == "managed-clarify":
        from core import studio_project_context
        studio = dict(runtime_document_version="2.0", process_context={"synthetic": True},
            approved_blueprint_revision_id="r", approved_blueprint_digest="a" * 64, bootstrap_operation_id="b")
        api.state.update(studio)
        # 실제 승인 승격 서비스의 시험은 B3가 담당. 여기서는 DTO→checkpoint 경계를 검증한다.
        monkeypatch.setattr(studio_project_context, "for_principal", lambda *args: studio)
    row, body = saved_request(api, clarify=mode != "general")
    response = submit(api, body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resumed"
    assert response.json()["submission"]["status"] == "ACCEPTED"
    assert len(api.resume_calls) == 1
    api.state["clarification_questions"] = []
    api.snapshot.next = ()
    receipt = api.client.get(BASE + "/hotl/submissions/" + body["client_request_id"], headers=headers())
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["submission"]["input_draft"] == body["input_draft"]
    consumed = api_change(api, row, "consume", submission_id=body["client_request_id"])
    assert consumed.status_code == 200, consumed.text
    assert consumed.json()["data"]["status"] == "CONSUMED"
    replay = submit(api, body)
    assert replay.status_code == 200 and replay.json() == response.json(), replay.text
    assert len(api.resume_calls) == 1


def test_engine_cancel_records_unknown_and_never_reexecutes(submission, monkeypatch):
    from api.deps import Principal
    from api.routes import factory_control as factory
    from core.org_directory import org_directory
    api = submission
    _, body = saved_request(api)
    principal = Principal(org.MEMBER_A, org_directory.resolve_scope(org.MEMBER_A, fresh=True), org.NODES[org.DEPT_A])
    async def cancelled(*args, **kwargs):
        api.resume_calls.append((args, kwargs))
        raise asyncio.CancelledError()
    monkeypatch.setattr(api.orchestrator, "resume_hotl", cancelled)
    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await factory.resume_from_hotl(PROJECT, factory.HOTLResumeRequest(**body), principal)
    api.client.portal.call(scenario)
    receipt = api.client.get(BASE + "/hotl/submissions/" + body["client_request_id"], headers=headers())
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["submission"]["status"] == "UNKNOWN"
    replay = submit(api, body)
    assert replay.status_code == 200 and replay.json()["status"] == "submission_recorded", replay.text
    assert len(api.resume_calls) == 1


@pytest.mark.parametrize("clarify", [True, False])
def test_mismatched_saved_body_is_rejected_before_execution_or_receipt(submission, clarify):
    from core.studio_hotl_submissions import HOTLSubmissionError, HOTLSubmissionStore
    api = submission
    row, body = saved_request(api, clarify=clarify)
    body["feedback"] = "저장하지 않은 다른 답변"
    response = submit(api, body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason_code"] == "STUDIO_HOTL_DRAFT_CONFLICT"
    assert not api.resume_calls
    with pytest.raises(HOTLSubmissionError) as exc:
        HOTLSubmissionStore(api.env.advisor).get(project_id=PROJECT, actor_id=org.MEMBER_A,
            boundary=row["context_key"], request_id=body["client_request_id"])
    assert exc.value.status_code == 404


@pytest.mark.parametrize("status", ["PROCESSING", "UNKNOWN", "REJECTED"])
def test_nonaccepted_receipt_replay_is_not_reported_as_resumed_or_consumable(submission, status):
    from core.studio_hotl_submissions import HOTLSubmissionStore
    api = submission
    row, body = saved_request(api)
    store = HOTLSubmissionStore(api.env.advisor)
    identity = dict(project_id=PROJECT, actor_id=org.MEMBER_A, boundary=row["context_key"])
    store.begin(**identity, submission=dict(client_request_id=body["client_request_id"], task_id=TASK,
        target=row["target"], feedback=body["feedback"], input_draft=body["input_draft"]))
    if status != "PROCESSING":
        store.finish(**identity, request_id=body["client_request_id"], outcome=status, result={"synthetic": True})
    api.snapshot.next = ()
    response = submit(api, body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "submission_recorded"
    assert response.json()["submission"]["status"] == status and not api.resume_calls
    assert api_change(api, row, "consume", submission_id=body["client_request_id"]).status_code == 503


@pytest.mark.parametrize("operation", ["SAVE", "DISCARD"])
def test_draft_changed_after_body_check_is_rejected_atomically(submission, monkeypatch, operation):
    from api.routes import factory_control as factory, studio_input_draft_control as drafts
    from core.studio_hotl_submissions import HOTLSubmissionError
    api = submission
    row, body = saved_request(api)
    store = factory._hotl_submission_store()
    original = store.begin
    def changed_before_begin(**kwargs):
        drafts._storage().mutate(boundary=row["context_key"], actor=org.MEMBER_A, project_id=PROJECT,
            operation=operation, draft_id=row["draft_id"], expected_revision=row["revision"],
            expected_digest=row["digest"], client_request_id="competing-" + operation,
            target=row["target"], content={"text": "다른 탭에서 수정", "selections": {"Q1": ["구매"]}})
        return original(**kwargs)
    monkeypatch.setattr(store, "begin", changed_before_begin)
    monkeypatch.setattr(factory, "_hotl_submission_store", lambda: store)
    response = submit(api, body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason_code"] == "STUDIO_HOTL_DRAFT_CONFLICT"
    assert not api.resume_calls
    with pytest.raises(HOTLSubmissionError) as exc:
        store.get(project_id=PROJECT, actor_id=org.MEMBER_A, boundary=row["context_key"],
                  request_id=body["client_request_id"])
    assert exc.value.status_code == 404


@pytest.mark.parametrize("field", ["feedback", "task_id", "expected_request_id", "expected_questions_digest", "input_draft"])
def test_replay_rejects_changed_original_input(submission, field):
    api = submission
    _, body = saved_request(api)
    assert submit(api, body).status_code == 200
    changed = copy.deepcopy(body)
    changed[field] = {**body[field], "revision": 99} if field == "input_draft" else "changed"
    response = submit(api, changed)
    assert response.status_code == 409, response.text
    assert len(api.resume_calls) == 1


def test_submission_get_rechecks_visibility_after_store_read(submission, monkeypatch):
    from api.routes import factory_control as factory
    from core.org_directory import org_directory
    api = submission
    _, body = saved_request(api)
    assert submit(api, body).status_code == 200
    store = factory._hotl_submission_store()
    original = store.get
    def revoked_read(**kwargs):
        result = original(**kwargs)
        # 부서 역할만 바꾸면 primary_dept의 읽기 권한이 정상 유지된다. 실제 계정 회수로 검사한다.
        org_directory.delete_user(org.MEMBER_A, actor="test")
        return result
    monkeypatch.setattr(store, "get", revoked_read)
    monkeypatch.setattr(factory, "_hotl_submission_store", lambda: store)
    response = api.client.get(BASE + "/hotl/submissions/" + body["client_request_id"], headers=headers())
    assert response.status_code in (403, 404), response.text
    assert "submission" not in response.json() and body["feedback"] not in response.text


def test_cancelled_request_waits_for_original_execution_and_receipt(submission, monkeypatch):
    from api.deps import Principal
    from api.routes import factory_control as factory
    from core.org_directory import org_directory
    api = submission
    _, body = saved_request(api)
    principal = Principal(org.MEMBER_A, org_directory.resolve_scope(org.MEMBER_A, fresh=True), org.NODES[org.DEPT_A])
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def held(*args, **kwargs):
            api.resume_calls.append((args, kwargs))
            started.set()
            await finish.wait()
            return True
        monkeypatch.setattr(api.orchestrator, "resume_hotl", held)
        request = asyncio.create_task(factory.resume_from_hotl(PROJECT, factory.HOTLResumeRequest(**body), principal))
        await asyncio.wait_for(started.wait(), 5)
        request.cancel()
        await asyncio.sleep(0)
        assert not request.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(request, 5)
    api.client.portal.call(scenario)
    response = api.client.get(BASE + "/hotl/submissions/" + body["client_request_id"], headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["submission"]["status"] == "ACCEPTED"
    assert len(api.resume_calls) == 1
