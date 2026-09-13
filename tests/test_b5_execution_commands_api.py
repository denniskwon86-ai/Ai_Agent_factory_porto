"""실제 HTTP/PDP/명령 SQLite, 실행 엔진만 명시적 대역. LLM/Host 실행 증거가 아니다."""
import asyncio
import copy
from types import SimpleNamespace
import uuid

import pytest
from tests import org_seed as org
from tests.test_b5_input_drafts import PROJECT, TASK, api, enforced_org, headers, isolated_stores  # noqa: F401

BASE = f"/api/v1/factory/{PROJECT}/execution-commands"
KEY = "b5100000-0000-4000-8000-000000000001"


def body(operation="PAUSE", **changes):
    return dict(client_request_id=KEY, operation=operation, task_id=TASK, input={}, **changes)


def post(env, command, actor=org.MEMBER_A):
    return env.client.post(BASE, json=command, headers=headers(actor))


def get(env, key=KEY, actor=org.MEMBER_A):
    return env.client.get(BASE + "/" + key, headers=headers(actor))


def receipt(response):
    assert response.status_code == 200, response.text
    return response.json()["request"]


@pytest.fixture
def commands(api, monkeypatch):
    from api.routes import studio_execution_control as routes
    from core.studio_execution_guard import owns_execution_command
    api.executed = []
    async def pause(task_id, project_id, reason=""):
        assert owns_execution_command(api.orchestrator, project_id)
        assert routes.dispatch_context()["command"]["task_id"] == task_id
        api.executed.append((task_id, project_id, reason))
        return True
    monkeypatch.setattr(api.orchestrator, "pause_sprint", pause)
    return api


def test_actual_post_get_list_same_key_runs_once(commands):
    first = receipt(post(commands, body()))
    assert first["status"] == "ACCEPTED"
    assert first["result"] == dict(http_status=200, response=dict(status="paused", task_id=TASK))
    assert receipt(get(commands)) == first
    assert receipt(post(commands, body())) == first
    listed = commands.client.get(BASE, headers=headers(org.MEMBER_A))
    assert listed.status_code == 200 and listed.json()["requests"] == [first]
    assert len(commands.executed) == 1


def test_changed_same_key_rejected_without_dispatch(commands):
    receipt(post(commands, body()))
    command = body(); command["operation"] = "STOP"
    assert post(commands, command).status_code == 409
    assert len(commands.executed) == 1


@pytest.mark.parametrize("operation", ["RESUME", "RESUME_QUOTA", "PAUSE", "STOP"])
def test_no_state_spread_on_resume_or_control(commands, operation):
    command = body(operation); command["input"] = dict(factory_mode="EXECUTION")
    assert post(commands, command).status_code == 422
    assert get(commands).status_code == 404 and not commands.executed


@pytest.mark.parametrize("change", [{"actor_id": org.MEMBER_A}, {"project_state_payload": {}}, {"client_request_id": "bad"}])
def test_closed_payload_and_uuid(commands, change):
    assert post(commands, {**body(), **change}).status_code == 422
    assert not commands.executed


def test_missing_running_task_is_recorded_rejected_not_success(commands, monkeypatch):
    async def missing(*args, **kwargs): return False
    monkeypatch.setattr(commands.orchestrator, "pause_sprint", missing)
    row = receipt(post(commands, body()))
    assert row["status"] == "REJECTED" and row["result"]["http_status"] == 409
    assert receipt(get(commands)) == row


def test_exception_after_effect_is_unknown_and_new_execution_blocked(commands, monkeypatch):
    from api.routes import studio_execution_control as routes
    from fastapi import HTTPException
    async def ambiguous(*args, **kwargs):
        commands.executed.append("effect")
        routes.mark_effect_started()
        raise HTTPException(409, "종료 후 응답 실패")
    monkeypatch.setattr(commands.orchestrator, "pause_sprint", ambiguous)
    row = receipt(post(commands, body()))
    assert row["status"] == "UNKNOWN"
    assert receipt(get(commands)) == row
    assert receipt(post(commands, body())) == row and len(commands.executed) == 1
    start = dict(client_request_id=str(uuid.uuid4()), operation="START", task_id="TASK_FRESH", input={})
    assert post(commands, start).status_code == 409
    assert len(commands.executed) == 1


def test_get_404_never_executes(commands):
    assert get(commands).status_code == 404
    assert not commands.executed


def test_current_actor_and_context_own_receipt(commands):
    receipt(post(commands, body()))
    assert get(commands, actor=org.MEMBER_B).status_code == 404
    other = commands.client.get(BASE, headers=headers(org.MEMBER_B))
    assert other.status_code in (200, 404)
    if other.status_code == 200: assert other.json()["requests"] == []
    assert len(commands.executed) == 1


def test_legacy_heal_cannot_bypass_journal(commands):
    before = (commands.root / "latest_state.json").read_bytes()
    response = commands.client.post(f"/api/v1/factory/{PROJECT}/heal",
        json=dict(error_log="합성 오류"), headers=headers(org.MEMBER_A))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason_code"] == "EXECUTION_REQUEST_REQUIRED"
    assert not (commands.root / "00_wbs_master_plan.json").exists()
    assert (commands.root / "latest_state.json").read_bytes() == before


def test_start_adapter_builds_only_server_modes_and_allowed_input(commands, monkeypatch):
    from api.routes import factory_control as factory
    calls = []
    async def start(project_id, req, p):
        calls.append(copy.deepcopy(req.project_state_payload))
        return dict(status="started", task_id=req.task_id)
    monkeypatch.setattr(factory, "start_sprint", start)
    command = dict(client_request_id=KEY, operation="START", task_id="TASK_NEW",
        input=dict(initial_idea="합성 기획", feedback="검토 요청"))
    assert receipt(post(commands, command))["status"] == "ACCEPTED"
    assert calls[0]["factory_mode"] == "EXECUTION"
    assert calls[0]["reviewer_decision"] == "REWORK_DEV"
    assert "schema_version" not in calls[0] and "process_context" not in calls[0]


def test_planning_resume_uses_existing_method_not_start(commands, monkeypatch):
    from api.routes import factory_control as factory
    calls = []
    async def allowed(*args): calls.append("guard")
    async def resume(task, project):
        calls.append((task, project)); return True
    async def forbidden(*args, **kwargs): pytest.fail("새 기획 경로를 호출함")
    monkeypatch.setattr(factory, "_assert_resumable", allowed)
    monkeypatch.setattr(commands.orchestrator, "resume_existing", resume)
    monkeypatch.setattr(factory, "start_sprint", forbidden)
    command = dict(client_request_id=KEY, operation="RESUME", task_id="PLANNING_123", input={})
    row = receipt(post(commands, command))
    assert row["status"] == "ACCEPTED" and calls == ["guard", ("PLANNING_123", PROJECT)]


def test_exact_owner_only_child_task_cannot_inherit_execution_permission():
    from core.studio_execution_guard import command, execution_command, owns_execution_command
    class Engine:
        active_tasks = {}; task_projects = {}
        @execution_command("project_id")
        async def start(self, project_id): return True
    async def scenario():
        engine = Engine()
        with command(engine, "P", exclusive=True, allow_nested_execution=True):
            assert owns_execution_command(engine, "P")
            assert await engine.start("P")
            assert not await asyncio.create_task(engine.start("P"))
        assert await engine.start("P")
    asyncio.run(scenario())


def test_cancelled_http_worker_keeps_reservation_until_command_finished():
    from core.studio_execution_guard import command, finish_before_cancel
    async def scenario():
        engine = SimpleNamespace(active_tasks={}, task_projects={})
        entered, release = asyncio.Event(), asyncio.Event()
        async def worker():
            with command(engine, "P", exclusive=True, allow_nested_execution=True):
                entered.set()
                await release.wait()
        outer = asyncio.create_task(finish_before_cancel(worker()))
        await entered.wait(); outer.cancel(); await asyncio.sleep(0)
        assert engine._studio_commands == {"P": 1}
        release.set()
        with pytest.raises(asyncio.CancelledError): await outer
        assert not engine._studio_commands
    asyncio.run(scenario())


@pytest.mark.parametrize("accepted", [True, False])
def test_heal_actual_wbs_and_journal_replay_without_duplicate(commands, monkeypatch, accepted):
    from api.routes import factory_control as factory
    from core.studio_execution_guard import owns_execution_command
    from nodes.utils.wbs_manager import WBSManager
    import json
    WBSManager(str(commands.root)).initialize_wbs("합성 복구", [dict(task_id=TASK,
        title="실패한 원작업", goal="원본", status="FAILED", required_agents=["Frontend"])], runtime_contract_profile="v1")
    async def no_hotl(*args):
        return dict(status="NOT_PENDING", available=False)
    async def prepare(*args): pass
    executions = []
    async def start(task_id, payload, root):
        assert owns_execution_command(commands.orchestrator, PROJECT)
        executions.append((task_id, copy.deepcopy(payload)))
        assert task_id in [row["task_id"] for row in json.loads((commands.root / "00_wbs_master_plan.json").read_text(encoding="utf-8"))["tasks"]]
        return accepted
    monkeypatch.setattr(commands.orchestrator, "read_hotl_context", no_hotl)
    monkeypatch.setattr(commands.orchestrator, "start_sprint", start)
    monkeypatch.setattr(factory, "_prepare_project_execution_or_conflict", prepare)
    command = dict(client_request_id=KEY, operation="HEAL", task_id=TASK, input=dict(error_log="합성 오류 원문"))
    row = receipt(post(commands, command))
    assert row["status"] == ("ACCEPTED" if accepted else "UNKNOWN"), row
    task_id = "TASK_REV_HEAL_" + KEY.replace("-", "")
    assert executions[0][0] == task_id and executions[0][1]["build_error_log"] == "합성 오류 원문"
    original = (commands.root / "00_wbs_master_plan.json").read_bytes()
    assert receipt(post(commands, command)) == row and receipt(get(commands)) == row
    assert len(executions) == 1 and (commands.root / "00_wbs_master_plan.json").read_bytes() == original


def test_hotl_pending_heal_records_no_new_task_and_enforces_server_limit(commands, monkeypatch):
    async def pending(*args): return dict(status="PENDING", available=True)
    monkeypatch.setattr(commands.orchestrator, "read_hotl_context", pending)
    for n in range(3):
        command = dict(client_request_id=str(uuid.uuid4()), operation="HEAL", task_id=TASK, input=dict(error_log="합성 오류"))
        row = receipt(post(commands, command))
        assert row["status"] == "ACCEPTED" and row["result"]["response"]["hotl_task_id"] == "sprint_init"
    assert post(commands, {**command, "client_request_id": str(uuid.uuid4())}).status_code == 409
    assert not (commands.root / "00_wbs_master_plan.json").exists()


def test_heal_preserves_other_current_task_hotl_not_only_request_task(commands, monkeypatch):
    import json
    current = {**commands.state, "current_sprint_task_id": "TASK_OTHER"}
    (commands.root / "latest_state.json").write_text(json.dumps(current), encoding="utf-8")
    seen = []
    async def context(task, project):
        seen.append(task)
        return dict(status="PENDING" if task == "TASK_OTHER" else "NOT_PENDING", available=task == "TASK_OTHER")
    monkeypatch.setattr(commands.orchestrator, "read_hotl_context", context)
    command = dict(client_request_id=KEY, operation="HEAL", task_id=TASK, input=dict(error_log="이전 실패 근거"))
    row = receipt(post(commands, command))
    assert row["status"] == "ACCEPTED" and row["result"]["response"]["hotl_task_id"] == "TASK_OTHER"
    assert "TASK_OTHER" in seen and not (commands.root / "00_wbs_master_plan.json").exists()


def test_post_commit_authority_change_is_unknown_http_not_rejected(commands, monkeypatch):
    from api.routes import studio_execution_control as routes
    from fastapi import HTTPException
    original, count = routes._same_context, 0
    def recheck(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 3: raise HTTPException(403, "합성: 처리 뒤 권한 변경")
        return original(*args, **kwargs)
    monkeypatch.setattr(routes, "_same_context", recheck)
    response = post(commands, body())
    assert response.status_code == 503, response.text
    assert len(commands.executed) == 1
    assert receipt(get(commands))["status"] == "ACCEPTED"


def test_state_latest_reads_actual_execution_projection_without_rewrite(commands):
    before = (commands.root / "latest_state.json").read_bytes()
    response = commands.client.get(f"/api/v1/factory/{PROJECT}/state/latest", headers=headers(org.MEMBER_A))
    assert response.status_code == 200, response.text
    actual = response.json()["data"]["studio_execution_state"]
    assert actual["task_id"] == TASK and actual["running"] is False
    assert actual["pause"]["resumable"] is False
    assert (commands.root / "latest_state.json").read_bytes() == before


def test_legacy_start_cannot_bypass_persisted_unknown(commands, monkeypatch):
    from api.routes import studio_execution_control as routes
    async def ambiguous(*args, **kwargs):
        routes.mark_effect_started()
        raise OSError("합성 응답 실패")
    monkeypatch.setattr(commands.orchestrator, "pause_sprint", ambiguous)
    assert receipt(post(commands, body()))["status"] == "UNKNOWN"
    original = (commands.root / "latest_state.json").read_bytes()
    response = commands.client.post(f"/api/v1/factory/{PROJECT}/sprint/start",
        json=dict(task_id="TASK_NEW", project_state_payload={}), headers=headers(org.MEMBER_A))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason_code"] == "STUDIO_COMMAND_PROJECT_BUSY"
    assert (commands.root / "latest_state.json").read_bytes() == original
