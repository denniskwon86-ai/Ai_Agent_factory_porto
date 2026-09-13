"""Host 복구 HTTP/실제 임시 원장·PDP·파일 + 명시적 그래프 엔진 대역.

복구 API는 실제 Factory router/권한표를 통과한다. LLM/실제 체크포인터/실행 재개는
검증하지 않는다. 실제 orchestrator의 bound-engine 투영 메서드만 메모리 엔진으로 호출한다.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import org_seed as org
from tests.test_b3_studio_drafts import isolated_stores, enforced_org
from tests.test_b1_process_configuration import headers


PROJECT = "RECONCILE_TEST"
TASK = "TASK-01"
URL = f"/api/v1/factory/{PROJECT}/contract-review/reconcile"


class MemoryEngine:
    def __init__(self, state):
        self.state, self.writes, self.fail = copy.deepcopy(state), [], False

    async def aget_state(self, config):
        assert config["configurable"]["thread_id"] == f"sprint_{PROJECT}__{TASK}"
        return SimpleNamespace(values=copy.deepcopy(self.state))

    async def aupdate_state(self, config, updates):
        if self.fail:
            raise ConnectionError("synthetic checkpoint unavailable")
        self.writes.append(copy.deepcopy(updates))
        self.state.update(updates)


@pytest.fixture
def api(isolated_stores, enforced_org, monkeypatch, request):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import factory_control as factory
    from core import advisor_store, decision_ledger, contract_review_gate as gate
    from core import host_contract_compiler as compiler
    from core.async_orchestrator import AsyncFactoryOrchestrator
    from core.paths import workspace_path

    record_initial = getattr(request, "param", True)
    env = isolated_stores
    monkeypatch.setattr(advisor_store, "advisor_store", env.advisor)
    monkeypatch.setattr(decision_ledger, "decision_ledger", env.ledger)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "")
    monkeypatch.setattr(config, "ECM_DEFAULT_TENANT_ID", "tenant_default")
    root = Path(workspace_path(PROJECT))
    (root / "contracts").mkdir(parents=True)
    contract_result = compiler.compile_contract(
        {"app_class": "departmental", "datasets": [], "capability_intents": []},
        project_id=PROJECT, task_id=TASK)
    assert contract_result.ok, contract_result.errors
    contract = contract_result.contract
    fp = contract["semantic_fingerprint"]
    boundary = dict(tenant_id="tenant_default", enterprise_scope_id=org.NODES[org.DEPT_A], entity_mode="REAL")
    decision = gate.evaluate(requires_contract=True, compiled_fingerprint=fp, approved_fingerprint="")
    request, _ = gate.ensure_review_request(env.ledger, decision, project_id=PROJECT, task_ids=[TASK], **boundary)
    event = gate.record_decision(env.ledger, decision, project_id=PROJECT,
        request_event_id=request["event_id"], approved=True, actor_id=org.MANAGER_A,
        rationale="기록만 성공한 승인 복구 합성 시험", task_id=TASK, **boundary) if record_initial else {"event_id": ""}
    state = dict(app_runtime_contract_fingerprint=fp, approved_contract_fingerprint="",
        app_runtime_contract_status="COMPILED", contract_review_request_event_id=request["event_id"],
        runtime_document_version="1.0")
    meta = {**boundary, "runtime_document_version": "1.0", "owner_dept_id": org.DEPT_A,
            "owner_user_id": "", "visibility": "dept"}
    (root / "project_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (root / "latest_state.json").write_text(json.dumps(state), encoding="utf-8")
    path = root / "contracts" / "app_runtime_contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    engine, orchestrator = MemoryEngine(state), AsyncFactoryOrchestrator()
    async def bound(project_id):
        assert project_id == PROJECT
        return engine
    monkeypatch.setattr(orchestrator, "_bound_engine", bound)
    monkeypatch.setattr(factory, "orchestrator", orchestrator)
    app = FastAPI()
    app.include_router(factory.router)
    body = dict(task_id=TASK, request_event_id=request["event_id"], event_id=event["event_id"], compiled_fingerprint=fp)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, body=body, path=path, ledger=env.ledger,
            engine=engine, orchestrator=orchestrator, event=event, decision=decision, boundary=boundary)


def post(api, **changes):
    return api.client.post(URL, json={**api.body, **changes}, headers=headers(org.MEMBER_A))


def test_actual_api_restores_same_approval_without_new_event_or_execution(api):
    response = post(api)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state_applied"] is True
    assert response.json()["data"]["execution_started"] is False
    original = api.path.read_bytes()
    approved = json.loads(original)["approval"]
    assert approved["approved_by"] == api.event["actor_id"]
    assert approved["approved_at"] == api.event["created_at"]
    assert post(api).json()["data"]["state_applied"] is True
    assert api.path.read_bytes() == original and len(api.engine.writes) == 1
    assert len(api.ledger.list_events(project_id=PROJECT)) == 2
    assert not api.orchestrator.active_tasks


def test_checkpoint_failure_remains_partial_and_same_event_recovers(api):
    api.engine.fail = True
    first = post(api)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["state_applied"] is False
    stamped = api.path.read_bytes()
    api.engine.fail = False
    assert post(api).json()["data"]["state_applied"] is True
    assert api.path.read_bytes() == stamped and len(api.ledger.list_events(project_id=PROJECT)) == 2


def test_stamp_failure_does_not_apply_checkpoint_or_report_success(api, monkeypatch):
    from core import studio_contract_reconcile as recovery
    original, before = recovery.stamp_approval, api.path.read_bytes()
    def fail(*args, **kwargs):
        raise recovery.ReconcileError("RECONCILE_CONTRACT_UNAVAILABLE", "합성 쓰기 장애", 503)
    monkeypatch.setattr(recovery, "stamp_approval", fail)
    assert post(api).json()["data"]["state_applied"] is False
    assert api.path.read_bytes() == before and not api.engine.writes
    monkeypatch.setattr(recovery, "stamp_approval", original)
    assert post(api).json()["data"]["state_applied"] is True


def test_wrong_current_fingerprint_or_different_review_never_writes(api):
    before = api.path.read_bytes()
    assert post(api, compiled_fingerprint="f" * 64).status_code == 409
    api.engine.state["contract_review_request_event_id"] = "different-review"
    assert post(api).status_code == 409
    assert api.path.read_bytes() == before and not api.engine.writes


def test_new_review_same_fingerprint_cannot_restore_old_approval(api):
    from core import contract_review_gate as gate
    gate.ensure_review_request(api.ledger, api.decision, project_id=PROJECT, task_ids=[TASK], **api.boundary)
    before = api.path.read_bytes()
    assert post(api).status_code == 409
    assert api.path.read_bytes() == before and not api.engine.writes


def test_current_permission_revocation_before_stamp_is_not_cached(api, monkeypatch):
    from core import studio_contract_reconcile as recovery
    from core.org_directory import org_directory
    original = recovery.validate_approval
    def revoke(*args, **kwargs):
        value = original(*args, **kwargs)
        org_directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
        return value
    monkeypatch.setattr(recovery, "validate_approval", revoke)
    before = api.path.read_bytes()
    assert post(api).status_code == 403
    assert api.path.read_bytes() == before and not api.engine.writes


@pytest.mark.parametrize("actor,code", [(None, 401), (org.VIEWER_A, 403), (org.MEMBER_B, 404)])
def test_real_reconcile_route_authority_and_scope(api, actor, code):
    response = api.client.post(URL, json=api.body, headers=headers(actor) if actor else {})
    assert response.status_code == code, response.text
    assert not api.engine.writes


def test_reconcile_request_does_not_accept_new_approval_actor(api):
    response = post(api, actor_id=org.ADMIN)
    assert response.status_code == 422 and not api.engine.writes


@pytest.mark.parametrize("api", [False], indirect=True)
def test_actual_decision_partial_result_recovers_with_asset_boundary(api, monkeypatch):
    async def read_contract_state(task_id, project_id):
        assert (task_id, project_id) == (TASK, PROJECT)
        return copy.deepcopy(api.engine.state)
    monkeypatch.setattr(api.orchestrator, "read_contract_state", read_contract_state)
    api.engine.fail = True
    response = api.client.post(f"/api/v1/factory/{PROJECT}/contract-review/decision",
        json={"task_id": TASK, "request_event_id": api.body["request_event_id"],
              "decision": "APPROVE", "rationale": "실제 결정 후 반영 장애 복구"},
        headers=headers(org.MEMBER_A))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["state_applied"] is False
    api.body["event_id"] = data["event_id"]
    event = api.ledger.get_event_strict(data["event_id"])
    assert {key: event[key] for key in api.boundary} == api.boundary
    api.engine.fail = False
    assert post(api).json()["data"]["state_applied"] is True
    assert len(api.ledger.list_events(project_id=PROJECT)) == 2


def test_busy_decision_does_not_disclose_other_department_project(api):
    from core.studio_execution_guard import reconcile
    body = {"task_id": TASK, "request_event_id": api.body["request_event_id"],
            "decision": "APPROVE", "rationale": "동시 요청"}
    with reconcile(api.orchestrator, PROJECT):
        for actor, code in ((org.MEMBER_B, 404), (org.MEMBER_A, 409)):
            response = api.client.post(f"/api/v1/factory/{PROJECT}/contract-review/decision",
                json=body, headers=headers(actor))
            assert response.status_code == code, response.text
    assert not api.engine.writes


def test_authority_unavailable_after_stamp_returns_recoverable_partial(api, monkeypatch):
    from fastapi import HTTPException
    from api.routes import studio_reconcile_control as routes
    original, calls = routes._authorized, []
    async def unavailable_after_stamp(*args):
        calls.append(1)
        if len(calls) == 4:
            raise HTTPException(503, "합성 권한 조회 장애")
        return await original(*args)
    monkeypatch.setattr(routes, "_authorized", unavailable_after_stamp)
    response = post(api)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state_applied"] is False
    assert response.json()["data"]["event_id"] == api.body["event_id"]
    assert json.loads(api.path.read_bytes())["approval"]["approved_by"] == api.event["actor_id"]
    assert not api.engine.writes
    monkeypatch.setattr(routes, "_authorized", original)
    assert post(api).json()["data"]["state_applied"] is True


@pytest.mark.parametrize("api", [False], indirect=True)
def test_parent_ledger_read_failure_is_503_before_decision_write(api, monkeypatch):
    from core.decision_ledger import DecisionLedgerError
    async def state(*args):
        return copy.deepcopy(api.engine.state)
    def unavailable(event_id):
        raise DecisionLedgerError("합성 원장 조회 장애")
    monkeypatch.setattr(api.orchestrator, "read_contract_state", state)
    monkeypatch.setattr(api.ledger, "get_event_strict", unavailable)
    before = api.path.read_bytes()
    response = api.client.post(f"/api/v1/factory/{PROJECT}/contract-review/decision",
        json={"task_id": TASK, "request_event_id": api.body["request_event_id"], "decision": "APPROVE"},
        headers=headers(org.MEMBER_A))
    assert response.status_code == 503, response.text
    assert api.path.read_bytes() == before and not api.engine.writes
    assert len(api.ledger.list_events(project_id=PROJECT)) == 1
