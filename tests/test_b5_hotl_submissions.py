"""B5 일반 HOTL 제출 기록 집중 회귀. 실행/수집은 main의 기존 strict-writes 런너 전용.

기존 실제 AdvisorStore·tmp SQLite 격리를 재사용한다. 재개 엔진/PDP/HTTP 검증으로
표현하지 않으며 DB 밖 task·WBS·운영 자료·RAW를 건드리지 않는다.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from tests.test_b3_studio_drafts import isolated_stores  # noqa: F401


PROJECT = "B5_HOTL_TEST"
ACTOR = "author@hotl.test.invalid"
BOUNDARY = {"ownership": {"tenant_id": "test", "enterprise_scope_id": "scope-A", "entity_mode": "REAL"},
            "viewing_context": {"scope_node_id": "scope-A"}, "process_context": {}}
QUESTIONS_DIGEST = "c" * 64
NOTE = "산출물 검토 의견 원문"


def key(number=1):
    return f"b5000000-0000-4000-8000-{number:012d}"


def target(task_id="TASK-01", **changes):
    return {**dict(kind="DECISION_COMMENT", task_id=task_id, decision_kind="GENERAL_HOTL",
                   request_id="hotl-round-1", target_digest=QUESTIONS_DIGEST, subject_id=""), **changes}


@pytest.fixture
def env(isolated_stores):
    from core.studio_hotl_submissions import HOTLSubmissionStore
    from core.studio_input_drafts import InputDraftStore
    return SimpleNamespace(
        store=HOTLSubmissionStore(isolated_stores.advisor), drafts=InputDraftStore(isolated_stores.advisor),
        args=dict(project_id=PROJECT, actor_id=ACTOR, boundary=copy.deepcopy(BOUNDARY)),
        draft_args=dict(boundary=copy.deepcopy(BOUNDARY), actor=ACTOR, project_id=PROJECT))


def save_draft(env, text=NOTE, task_id="TASK-01"):
    """실제 초안 저장소를 쓴다. 소비 대조는 합성 dict로 대신하지 않는다."""
    saved = env.drafts.mutate(**env.draft_args, operation="SAVE", draft_id="", expected_revision=0,
        expected_digest="", client_request_id="save-" + task_id, target=target(task_id),
        content=dict(text=text, decision="", selections={}))
    return env.drafts.get(**env.draft_args, draft_id=saved["draft_id"])


def ref(row):
    return dict(draft_id=row["draft_id"], revision=row["revision"], digest=row["digest"])


def submission(row, number=1, **changes):
    return {**dict(client_request_id=key(number), task_id=row["target"]["task_id"], target=copy.deepcopy(row["target"]),
                   feedback=row["content"]["text"], input_draft=ref(row)), **changes}


def failure(call, status, reason):
    from core.studio_hotl_submissions import HOTLSubmissionError
    with pytest.raises(HOTLSubmissionError) as exc:
        call()
    assert exc.value.status_code == status and exc.value.reason_code == "STUDIO_HOTL_" + reason
    return str(exc.value)


def test_begin_records_processing_before_any_resume_and_get_returns_the_same_row(env):
    row = save_draft(env)
    value, created = env.store.begin(**env.args, submission=submission(row))
    assert created is True and value["status"] == "PROCESSING" and value["result"] is None
    assert value["feedback"] == NOTE and value["input_draft"] == ref(row)
    assert env.store.get(**env.args, request_id=key()) == value


def test_same_key_is_idempotent_and_a_changed_body_is_rejected_without_a_second_record(env):
    row = save_draft(env)
    first, _ = env.store.begin(**env.args, submission=submission(row))
    again, created = env.store.begin(**env.args, submission=submission(row))
    assert created is False and again == first
    failure(lambda: env.store.begin(**env.args, submission=submission(row, feedback="다른 본문")),
            409, "IDEMPOTENCY_CONFLICT")
    assert env.store.get(**env.args, request_id=key()) == first


def test_a_new_key_cannot_submit_the_same_saved_draft_revision_twice(env):
    row = save_draft(env)
    env.store.begin(**env.args, submission=submission(row))
    failure(lambda: env.store.begin(**env.args, submission=submission(row, client_request_id=key(2))),
            409, "DRAFT_ALREADY_SUBMITTED")


def test_clarification_and_mismatched_task_are_refused_at_the_boundary(env):
    row = save_draft(env)
    failure(lambda: env.store.begin(**env.args, submission=submission(
        row, target=target(kind="CLARIFICATION", decision_kind=""))), 422, "TARGET_UNSUPPORTED")
    failure(lambda: env.store.begin(**env.args, submission=submission(row, task_id="TASK-99")),
            409, "TARGET_CONFLICT")
    failure(lambda: env.store.begin(**env.args, submission=submission(row, feedback="   ")),
            422, "INVALID")


def test_another_actor_or_context_cannot_see_or_finish_the_record(env):
    row = save_draft(env)
    env.store.begin(**env.args, submission=submission(row))
    other = {**env.args, "actor_id": "someone.else@hotl.test.invalid"}
    failure(lambda: env.store.get(**other, request_id=key()), 404, "NOT_FOUND")
    moved = {**env.args, "boundary": {**copy.deepcopy(BOUNDARY), "viewing_context": {"scope_node_id": "scope-B"}}}
    failure(lambda: env.store.get(**moved, request_id=key()), 404, "NOT_FOUND")
    failure(lambda: env.store.finish(**other, request_id=key(), outcome="ACCEPTED", result={}), 404, "NOT_FOUND")


def test_finish_is_a_cas_and_a_terminal_record_keeps_its_first_outcome(env):
    row = save_draft(env)
    env.store.begin(**env.args, submission=submission(row))
    done = env.store.finish(**env.args, request_id=key(), outcome="ACCEPTED", result={"resumed": True})
    assert done["status"] == "ACCEPTED" and done["result"] == {"resumed": True}
    assert env.store.finish(**env.args, request_id=key(), outcome="ACCEPTED", result={"resumed": True}) == done
    failure(lambda: env.store.finish(**env.args, request_id=key(), outcome="REJECTED", result={}),
            409, "TERMINAL_CONFLICT")


def test_a_tampered_record_is_reported_as_integrity_not_silently_accepted(env):
    row = save_draft(env)
    env.store.begin(**env.args, submission=submission(row))
    with env.store.transaction(write=True) as conn:
        stored = conn.execute("SELECT record_json FROM studio_hotl_submissions WHERE request_id=?", (key(),)).fetchone()
        payload = json.loads(stored["record_json"])
        payload["record"]["feedback"] = "몰래 바뀐 본문"
        conn.execute("UPDATE studio_hotl_submissions SET record_json=? WHERE request_id=?",
                     (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), key()))
    failure(lambda: env.store.get(**env.args, request_id=key()), 503, "INTEGRITY")


def test_consumption_requires_an_accepted_receipt_and_matching_draft_revision(env):
    from core.studio_hotl_submissions import verify_consumption
    row = save_draft(env)
    env.store.begin(**env.args, submission=submission(row))
    pending = env.store.get(**env.args, request_id=key())
    #: 접수 전/불명 상태로는 닫지 않는다. 「응답을 못 받았다」를 성공으로 바꾸지 않는다.
    failure(lambda: verify_consumption(row, pending, expected_revision=row["revision"], expected_digest=row["digest"]),
            503, "SUBMISSION_UNCONFIRMED")
    env.store.finish(**env.args, request_id=key(), outcome="UNKNOWN", result={"reason": "응답 유실"})
    failure(lambda: verify_consumption(row, env.store.get(**env.args, request_id=key()),
            expected_revision=row["revision"], expected_digest=row["digest"]), 503, "SUBMISSION_UNCONFIRMED")


def test_accepted_receipt_consumes_only_the_exact_saved_revision(env):
    from core.studio_hotl_submissions import verify_consumption
    row = save_draft(env)
    env.store.begin(**env.args, submission=submission(row))
    receipt = env.store.finish(**env.args, request_id=key(), outcome="ACCEPTED", result={"resumed": True})
    verified = verify_consumption(row, receipt, expected_revision=row["revision"], expected_digest=row["digest"])
    assert verified == dict(submission_id=key(), draft_id=row["draft_id"], draft_digest=row["digest"])
    #: 제출 뒤 초안을 더 고쳤으면 그 판은 이 제출이 만든 것이 아니다.
    edited = env.drafts.mutate(**env.draft_args, operation="SAVE", draft_id=row["draft_id"],
        expected_revision=row["revision"], expected_digest=row["digest"], client_request_id="edit-1",
        target=copy.deepcopy(row["target"]), content=dict(text="나중에 고친 본문", decision="", selections={}))
    later = env.drafts.get(**env.draft_args, draft_id=row["draft_id"])
    failure(lambda: verify_consumption(later, receipt, expected_revision=edited["revision"],
            expected_digest=later["digest"]), 409, "SUBMISSION_CONFLICT")


def test_consumed_draft_stays_bound_to_the_original_submission_id(env):
    from core.studio_hotl_submissions import verify_consumption
    row = save_draft(env)
    env.store.begin(**env.args, submission=submission(row))
    receipt = env.store.finish(**env.args, request_id=key(), outcome="ACCEPTED", result={"resumed": True})
    verified = verify_consumption(row, receipt, expected_revision=row["revision"], expected_digest=row["digest"])
    env.drafts.mutate(**env.draft_args, operation="CONSUME", draft_id=row["draft_id"],
        expected_revision=row["revision"], expected_digest=row["digest"], client_request_id="consume-1",
        submission_id=key(), verified=verified)
    closed = env.drafts.get(**env.draft_args, draft_id=row["draft_id"])
    assert closed["status"] == "CONSUMED" and closed["submission_id"] == key()
    #: 이미 닫힌 초안을 같은 제출로 다시 확인해도 판본·제출 ID가 어긋나면 열어주지 않는다.
    assert verify_consumption(closed, receipt, expected_revision=row["revision"],
                              expected_digest=row["digest"]) == verified
