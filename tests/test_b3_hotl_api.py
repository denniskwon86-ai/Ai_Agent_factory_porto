"""실제 HTTP/PDP와 HOTL 차수 adapter 시험. 그래프 실행·재개 검증은 별도이다."""
import json

import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import headers
from tests.test_b3_reconcile_api import api, isolated_stores, enforced_org, PROJECT, TASK


@pytest.fixture
def hotl(api, monkeypatch):
    from api.routes import factory_control as factory
    from core import contract_review_gate as gate
    from core.enterprise_context.process_schema import ProcessError
    calls = []
    context = dict(status="PENDING", pending=True, available=True, request_id="a" * 64,
                   questions_digest="b" * 64, decision_kind="CLARIFICATION", reason_code="HOTL_PENDING")
    async def pending(task_id, project_id):
        return task_id == TASK
    async def read_context(task_id, project_id):
        assert project_id == PROJECT
        if task_id == "sprint_init":
            return {**context, "status": "NOT_PENDING", "pending": False, "available": False,
                    "request_id": "", "questions_digest": ""}
        assert task_id == TASK
        return context
    async def resumable(*args):
        return None
    async def review(*args):
        return gate.evaluate(requires_contract=False, compiled_fingerprint="", approved_fingerprint=""), {}
    async def resume(task_id, feedback, project_id, **kwargs):
        calls.append((task_id, feedback, project_id, kwargs))
        if kwargs["expected_request_id"] != context["request_id"]:
            raise ProcessError("HOTL_ROUND_CONFLICT", "합성 차수 충돌", 409)
        return True
    monkeypatch.setattr(api.orchestrator, "is_hotl_pending", pending)
    monkeypatch.setattr(api.orchestrator, "read_hotl_context", read_context)
    monkeypatch.setattr(api.orchestrator, "resume_hotl", resume)
    monkeypatch.setattr(factory, "_assert_resumable", resumable)
    monkeypatch.setattr(factory, "_contract_review_context", review)
    latest = api.path.parent.parent / "latest_state.json"
    state = json.loads(latest.read_bytes())
    latest.write_text(json.dumps({**state, "current_sprint_task_id": TASK}), encoding="utf-8")
    return api, context, calls


def test_hotl_check_provides_server_round_and_resume_forwards_exact_tokens(hotl):
    api, context, calls = hotl
    response = api.client.get(f"/api/v1/factory/{PROJECT}/hotl/check", headers=headers(org.MEMBER_A))
    assert response.status_code == 200, response.text
    assert response.json()["hotl_task_id"] == TASK
    assert response.json()["hotl_context"] == context
    response = api.client.post(f"/api/v1/factory/{PROJECT}/hotl/resume", headers=headers(org.MEMBER_A),
        json=dict(task_id=TASK, feedback="이 차수의 답변", expected_request_id=context["request_id"],
                  expected_questions_digest=context["questions_digest"]))
    assert response.status_code == 200, response.text
    assert calls == [(TASK, "이 차수의 답변", PROJECT, dict(expected_request_id="a" * 64,
        expected_questions_digest="b" * 64, expected_studio_context=None))]


def test_hotl_conflict_keeps_structured_reason(hotl):
    api, _, calls = hotl
    response = api.client.post(f"/api/v1/factory/{PROJECT}/hotl/resume", headers=headers(org.MEMBER_A),
        json=dict(task_id=TASK, feedback="미소비 답변", expected_request_id="old"))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason_code"] == "HOTL_ROUND_CONFLICT"
    assert len(calls) == 1


def test_other_department_cannot_read_round_or_submit(hotl):
    api, _, calls = hotl
    assert api.client.get(f"/api/v1/factory/{PROJECT}/hotl/check", headers=headers(org.MEMBER_B)).status_code == 404
    assert api.client.post(f"/api/v1/factory/{PROJECT}/hotl/resume", headers=headers(org.MEMBER_B),
        json=dict(task_id=TASK)).status_code == 404
    assert not calls


def test_check_does_not_turn_checkpoint_failure_into_no_pending(hotl, monkeypatch):
    from core.studio_hotl_context import hotl_context
    api, _, _ = hotl
    async def unavailable(task_id, project_id):
        return hotl_context(None, project_id=project_id, task_id=task_id)
    async def forbidden_bool(*args):
        pytest.fail("UNKNOWN을 숨기는 bool 조회를 먼저 호출했습니다.")
    monkeypatch.setattr(api.orchestrator, "read_hotl_context", unavailable)
    monkeypatch.setattr(api.orchestrator, "is_hotl_pending", forbidden_bool)
    response = api.client.get(f"/api/v1/factory/{PROJECT}/hotl/check", headers=headers(org.MEMBER_A))
    assert response.status_code == 200, response.text
    assert response.json()["hotl_context"]["status"] == "UNKNOWN"
    assert response.json()["hotl_context"]["available"] is False
    assert response.json()["hotl_task_id"] is None


def test_resume_unknown_outcome_is_503_not_state_conflict(hotl, monkeypatch):
    from core.enterprise_context.process_schema import ProcessError
    api, context, _ = hotl
    async def uncertain(*args, **kwargs):
        raise ProcessError("HOTL_RESUME_OUTCOME_UNKNOWN", "반영 상태 확인 필요", 503)
    monkeypatch.setattr(api.orchestrator, "resume_hotl", uncertain)
    response = api.client.post(f"/api/v1/factory/{PROJECT}/hotl/resume", headers=headers(org.MEMBER_A),
        json=dict(task_id=TASK, expected_request_id=context["request_id"], expected_questions_digest=context["questions_digest"]))
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["reason_code"] == "HOTL_RESUME_OUTCOME_UNKNOWN"


@pytest.mark.parametrize("suffix,failed_read", [("hotl/resume", 1), ("hotl/resume", 2), ("sprint/resume-quota", 1)])
def test_actual_preflight_and_contract_query_errors_keep_503(api, monkeypatch, suffix, failed_read):
    """실제 HTTP/PDP·엄격 bound 조회. 승인 문맥/템플릿 준비 판정만 명시적 대역이다."""
    from types import SimpleNamespace
    from api.routes import factory_control as factory
    from core import studio_project_context, resume_guard
    server = dict(runtime_document_version="2.0", process_context={"server": "synthetic"},
        approved_blueprint_revision_id="revision", approved_blueprint_digest="a" * 64,
        bootstrap_operation_id="operation")
    api.engine.state.update(server)
    monkeypatch.setattr(studio_project_context, "for_principal", lambda *args: server)
    monkeypatch.setattr(factory, "_assert_contract_profile_readable", lambda *args: None)
    monkeypatch.setattr(factory, "_verify_project_template_binding", lambda *args, **kwargs: None)
    monkeypatch.setattr(factory, "_read_project_template", lambda *args: "default")
    monkeypatch.setattr(resume_guard, "check", lambda *args: SimpleNamespace(ok=True))
    original, reads = api.engine.aget_state, []
    async def failure(config):
        reads.append(config)
        if len(reads) == failed_read:
            raise ConnectionError("합성 선행 조회 장애")
        return await original(config)
    async def forbidden(*args, **kwargs):
        pytest.fail("선행 조회 장애 뒤 실행 재개 또는 오류를 삼키는 구 조회를 호출했습니다.")
    monkeypatch.setattr(api.engine, "aget_state", failure)
    monkeypatch.setattr(api.orchestrator, "read_contract_state", forbidden)
    monkeypatch.setattr(api.orchestrator, "resume_hotl", forbidden)
    monkeypatch.setattr(api.orchestrator, "resume_from_suspend", forbidden)
    response = api.client.post(f"/api/v1/factory/{PROJECT}/{suffix}", headers=headers(org.MEMBER_A),
        json=dict(task_id=TASK))
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["reason_code"] == "CONTRACT_CHECKPOINT_UNAVAILABLE"
    assert len(reads) == failed_read and not api.engine.writes
