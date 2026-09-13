"""실제 StateSnapshot 형태를 이용한 순수 HOTL 토큰 회귀. 그래프·DB를 실행하지 않는다."""
from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from langgraph.types import StateSnapshot

from core.studio_hotl_context import hotl_context


PROJECT = "project-hotl"
TASK = "task-hotl"
CHECKPOINT = "checkpoint-persisted-01"
_FIELDS = {"status", "pending", "available", "reason_code", "request_id",
           "questions_digest", "decision_kind"}


def _questions():
    return [{
        "id": "Q1", "question": "기밀 질문 원문", "why": "기밀 질문 이유", "multi": False,
        "options": [
            {"label": "첫 선택", "description": "첫 설명", "recommended": True},
            {"label": "둘째 선택", "description": "둘째 설명", "recommended": False},
        ],
    }]


def _snapshot():
    # 로컬 langgraph/types.py의 실제 NamedTuple 8필드를 모두 지정한다.
    return StateSnapshot(
        values={"current_stage": "CLARIFICATION", "factory_mode": "PLANNING",
                "clarification_questions": _questions()},
        next=("RFP_Analyst",),
        config={"configurable": {"checkpoint_id": CHECKPOINT, "thread_id": "server-thread"}},
        metadata={"source": "loop", "step": 3, "parents": {}},
        created_at="2026-09-13T00:00:00+00:00", parent_config=None,
        tasks=(), interrupts=(),
    )


def _context(snapshot, **kwargs):
    return hotl_context(snapshot, project_id=kwargs.pop("project_id", PROJECT),
                        task_id=kwargs.pop("task_id", TASK), **kwargs)


def _closed(result, status):
    assert set(result) == _FIELDS
    assert result["status"] == status
    assert result["available"] is False and result["pending"] is False
    assert result["request_id"] == result["questions_digest"] == result["decision_kind"] == ""
    assert result["reason_code"].startswith("HOTL_")


def test_exact_canonical_material_is_stable_after_snapshot_reconstruction_and_key_reordering():
    snapshot = _snapshot()
    before = copy.deepcopy(snapshot)
    result = _context(snapshot)
    # 기대값은 구현 내부 함수 대신 합의된 독립 정규형 원문에서 계산한다.
    request_bytes = (b'{"checkpoint_id":"checkpoint-persisted-01","next_nodes":["RFP_Analyst"],'
                     b'"project_id":"project-hotl","task_id":"task-hotl"}')
    question_bytes = ('[{"id":"Q1","multi":false,"options":['
                      '{"description":"첫 설명","label":"첫 선택","recommended":true},'
                      '{"description":"둘째 설명","label":"둘째 선택","recommended":false}],'
                      '"question":"기밀 질문 원문","why":"기밀 질문 이유"}]').encode("utf-8")
    assert result == {
        "status": "PENDING", "pending": True, "available": True,
        "reason_code": "HOTL_PENDING", "decision_kind": "CLARIFICATION",
        "request_id": hashlib.sha256(request_bytes).hexdigest(),
        "questions_digest": hashlib.sha256(question_bytes).hexdigest(),
    }
    # 영속값의 재구성을 재시작 대역으로 삼는다. 프로세스·체크포인터를 실행하지 않는다.
    restored = StateSnapshot(**json.loads(json.dumps(snapshot._asdict(), ensure_ascii=False)))
    restored.values["clarification_questions"][0] = dict(reversed(list(
        restored.values["clarification_questions"][0].items())))
    assert _context(restored) == _context(snapshot) == result
    assert snapshot == before
    public_json = json.dumps(result, ensure_ascii=False)
    for hidden in ("기밀 질문 원문", "기밀 질문 이유", "첫 설명", CHECKPOINT, "server-thread"):
        assert hidden not in public_json


@pytest.mark.parametrize("changed", ["checkpoint", "project", "task", "next_nodes", "node_order"])
def test_request_round_is_bound_to_checkpoint_and_exact_project_task_next_nodes(changed):
    snapshot = _snapshot()._replace(next=("RFP_Analyst", "Review"))
    old = _context(snapshot)
    kwargs = {}
    if changed == "checkpoint":
        snapshot.config["configurable"]["checkpoint_id"] = "checkpoint-persisted-02"
    elif changed == "project":
        kwargs["project_id"] = "other-project"
    elif changed == "task":
        kwargs["task_id"] = "other-task"
    elif changed == "node_order":
        snapshot = snapshot._replace(next=tuple(reversed(snapshot.next)))
    else:
        snapshot = snapshot._replace(next=("Other_Node",))
    new = _context(snapshot, **kwargs)
    assert new["available"] is True
    assert new["request_id"] != old["request_id"]
    assert new["questions_digest"] == old["questions_digest"]


@pytest.mark.parametrize("changed", ["text", "option", "option_order", "extra_field", "question_order"])
def test_question_digest_covers_actual_full_content_and_order(changed):
    snapshot = _snapshot()
    snapshot.values["clarification_questions"].append({"id": "Q2", "question": "둘째 질문"})
    old = _context(snapshot)
    questions = snapshot.values["clarification_questions"]
    if changed == "text":
        questions[0]["question"] += " 수정"
    elif changed == "option":
        questions[0]["options"][0]["recommended"] = False
    elif changed == "option_order":
        questions[0]["options"].reverse()
    elif changed == "extra_field":
        questions[0]["future_field"] = {"material": [1, True, None, 1.5]}
    else:
        questions.reverse()
    new = _context(snapshot)
    assert new["available"] is True
    assert new["request_id"] == old["request_id"]
    assert new["questions_digest"] != old["questions_digest"]


def test_stage_classification_empty_questions_and_model_values_do_not_invent_a_new_round():
    snapshot = _snapshot()
    snapshot.values["clarification_questions"] = []
    clarified = _context(snapshot)
    assert clarified["available"] is True and clarified["decision_kind"] == "CLARIFICATION"
    assert clarified["questions_digest"] == hashlib.sha256(b"[]").hexdigest()
    snapshot.values["current_stage"] = "CODE_REVIEW"
    snapshot.values["unrelated_display_label"] = "바뀐 표시 문구"
    snapshot = snapshot._replace(created_at="다른 표시 시각", metadata={"step": 99})
    general = _context(snapshot)
    assert general == {**clarified, "decision_kind": "GENERAL_HOTL"}
    assert _context(snapshot._replace(values=SimpleNamespace(**snapshot.values))) == general
    # 명확화 외 단계의 기존 상태는 질문 필드가 없어도 빈 목록으로 유지한다.
    del snapshot.values["clarification_questions"]
    assert _context(snapshot) == general


@pytest.mark.parametrize("condition,reason", [
    ("running", "HOTL_RUNNING"), ("quota", "HOTL_SUSPENDED_QUOTA"),
    ("end", "HOTL_NO_NEXT_NODES"), ("no_next", "HOTL_NO_NEXT_NODES"),
])
def test_not_pending_never_issues_tokens_even_without_checkpoint_id(condition, reason):
    snapshot = _snapshot()._replace(config={})
    kwargs = {}
    if condition == "running":
        kwargs["running"] = True
    elif condition == "quota":
        snapshot.values["factory_mode"] = "SUSPENDED_QUOTA"
    else:
        snapshot = snapshot._replace(next=() if condition == "end" else None)
    result = _context(snapshot, **kwargs)
    _closed(result, "NOT_PENDING")
    assert result["reason_code"] == reason


@pytest.mark.parametrize("config", [
    None, {}, {"configurable": None}, {"configurable": {}},
    {"configurable": {"checkpoint_id": ""}}, {"configurable": {"checkpoint_id": " "}},
    {"configurable": {"checkpoint_id": 42}}, {"configurable": {"checkpoint_id": True}},
])
def test_missing_persisted_checkpoint_never_falls_back_to_parent_metadata_or_values(config):
    snapshot = _snapshot()._replace(
        config=config, parent_config={"configurable": {"checkpoint_id": "parent-checkpoint"}},
        metadata={"checkpoint_id": "metadata-checkpoint"})
    snapshot.values.update(checkpoint_id="client-checkpoint", request_id="client-token")
    result = _context(snapshot)
    _closed(result, "UNKNOWN")
    assert result["reason_code"] == "HOTL_CHECKPOINT_ID_UNAVAILABLE"


@pytest.mark.parametrize("damage", [
    "missing_questions", "null_questions", "question_not_object", "non_json", "non_string_key",
    "nan", "cycle", "unicode", "missing_state", "invalid_stage", "invalid_next", "invalid_identity",
])
def test_corrupt_material_fails_closed_without_partial_tokens_or_original_text(damage):
    snapshot = _snapshot()
    kwargs = {}
    questions = snapshot.values["clarification_questions"]
    if damage == "missing_questions":
        del snapshot.values["clarification_questions"]
    elif damage == "null_questions":
        snapshot.values["clarification_questions"] = None
    elif damage == "question_not_object":
        questions.append("기밀 원문")
    elif damage == "non_json":
        questions[0]["unsupported"] = {"집합"}
    elif damage == "non_string_key":
        questions[0][1] = "숫자 키"
    elif damage == "nan":
        questions[0]["unsupported"] = float("nan")
    elif damage == "cycle":
        questions[0]["cycle"] = questions
    elif damage == "unicode":
        questions[0]["question"] = "\ud800"
    elif damage == "missing_state":
        snapshot = snapshot._replace(values=None)
    elif damage == "invalid_stage":
        snapshot.values["current_stage"] = ["CLARIFICATION"]
    elif damage == "invalid_next":
        snapshot = snapshot._replace(next="RFP_Analyst")
    else:
        kwargs["task_id"] = ""
    result = _context(snapshot, **kwargs)
    _closed(result, "UNKNOWN")
    assert "기밀" not in json.dumps(result, ensure_ascii=False)


def test_missing_snapshot_and_unknown_running_flag_are_not_treated_as_a_pending_round():
    _closed(_context(None), "UNKNOWN")
    _closed(_context(_snapshot(), running="false"), "UNKNOWN")
