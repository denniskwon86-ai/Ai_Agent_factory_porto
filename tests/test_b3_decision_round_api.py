"""실제 HTTP/PDP·임시 원장·서버 초안 판/컴파일러 소비자 연결. LLM 실행 아님."""
import json

import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import headers
from tests.test_b3_reconcile_api import api, isolated_stores, enforced_org, PROJECT, TASK


BASE = f"/api/v1/factory/{PROJECT}/contract-decisions"
DRAFT = {"app_class": "departmental", "datasets": [], "capability_intents": [
    {"intent_id": "i1", "requirement_ref": "FR-01", "capability": "file.upload"}]}


@pytest.fixture
def round_api(api):
    from nodes.contract import save_draft
    root = api.path.parent.parent
    (root / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [
        {"task_id": TASK, "artifact_kind": "APP"}]}), encoding="utf-8")
    save_draft(str(root), TASK, DRAFT, require_metadata=True)
    api.root = root
    return api


def pending(api):
    response = api.client.get(BASE + "/pending", headers=headers(org.MEMBER_A))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def body(item):
    return dict(task_id=TASK, capability="file.upload", decision="REDUCE", rationale="현재 초안만 축소",
                decision_request_id=item["decision_request_id"], expected_digest=item["expected_digest"])


def submit(api, value):
    return api.client.post(BASE + "/resolve", json=value, headers=headers(org.MEMBER_A))


def test_actual_round_ledger_then_compiler_projection_and_consumed_retry(round_api):
    from nodes.contract import load_drafts
    api = round_api
    item = pending(api)["capability_decisions"][0]
    assert pending(api)["capability_decisions"][0] == item
    original = (api.root / "contracts" / "drafts" / f"{TASK}.json").read_bytes()
    response = submit(api, body(item))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["draft_applied"] is True
    event = api.ledger.get_event_strict(data["event_id"])
    assert event["actor_id"] == org.MEMBER_A
    assert {key: event[key] for key in api.boundary} == api.boundary
    assert event["input_version_refs"][0]["decision_request_id"] == item["decision_request_id"]
    assert load_drafts(str(api.root))[TASK]["capability_intents"][0]["user_decision"] == "REDUCE"
    assert (api.root / "contracts" / "drafts" / f"{TASK}.json").read_bytes() == original
    assert not pending(api)["capability_decisions"]
    assert submit(api, body(item)).status_code == 409
    assert len(api.ledger.list_events(project_id=PROJECT)) == 3


def test_same_content_new_server_generation_rejects_old_decision(round_api):
    from nodes.contract import save_draft, load_drafts
    api = round_api
    old = pending(api)["capability_decisions"][0]
    save_draft(str(api.root), TASK, DRAFT, require_metadata=True)
    current = pending(api)["capability_decisions"][0]
    assert current["decision_request_id"] != old["decision_request_id"]
    assert submit(api, body(old)).status_code == 409
    assert "user_decision" not in load_drafts(str(api.root))[TASK]["capability_intents"][0]
    assert len(api.ledger.list_events(project_id=PROJECT)) == 2


def test_managed_round_requires_tokens_and_refuses_client_actor(round_api):
    api = round_api
    assert submit(api, dict(task_id=TASK, capability="file.upload", decision="REDUCE")).status_code == 422
    item = pending(api)["capability_decisions"][0]
    assert submit(api, {**body(item), "actor_id": org.ADMIN}).status_code == 422
    assert len(api.ledger.list_events(project_id=PROJECT)) == 2


def test_other_department_cannot_discover_or_resolve_current_round(round_api):
    api = round_api
    item = pending(api)["capability_decisions"][0]
    assert api.client.get(BASE + "/pending", headers=headers(org.MEMBER_B)).status_code == 404
    assert api.client.post(BASE + "/resolve", json=body(item), headers=headers(org.MEMBER_B)).status_code == 404
    assert len(api.ledger.list_events(project_id=PROJECT)) == 2


def test_ledger_readback_failure_keeps_event_id_and_never_reappends(round_api, monkeypatch):
    from nodes.contract import load_drafts
    api = round_api
    item = pending(api)["capability_decisions"][0]
    original = api.ledger.get_event_strict
    def unavailable(event_id):
        row = original(event_id)
        if row["event_type"] == "APP_CONTRACT_DECISION_RECORDED":
            raise ConnectionError("합성 기록 후 읽기 장애")
        return row
    monkeypatch.setattr(api.ledger, "get_event_strict", unavailable)
    response = submit(api, body(item))
    assert response.status_code == 503, response.text
    data = response.json()["detail"]
    assert data["event_id"] and data["draft_applied"] is False
    assert data["decision_request_id"] == item["decision_request_id"]
    assert "user_decision" not in load_drafts(str(api.root))[TASK]["capability_intents"][0]
    retry = submit(api, body(item))
    assert retry.status_code == 503, retry.text
    assert retry.json()["detail"]["event_id"] == data["event_id"]
    assert len(api.ledger.list_events(project_id=PROJECT)) == 3


def test_legacy_two_drafts_can_be_decided_sequentially_without_implicit_conversion(api):
    from nodes.contract import load_drafts
    root = api.path.parent.parent
    directory = root / "contracts" / "drafts"
    directory.mkdir()
    (root / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [
        {"task_id": tid, "artifact_kind": "APP"} for tid in ("T-A", "T-B")]}), encoding="utf-8")
    for tid in ("T-A", "T-B"):
        (directory / f"{tid}.json").write_text(json.dumps(DRAFT), encoding="utf-8")
    for tid in ("T-A", "T-B"):
        assert any(item["task_id"] == tid for item in pending(api)["capability_decisions"])
        response = submit(api, dict(task_id=tid, capability="file.upload", decision="REDUCE"))
        assert response.status_code == 200, response.text
        assert response.json()["data"]["draft_applied"] is True
    assert not pending(api)["capability_decisions"]
    assert all(value["capability_intents"][0]["user_decision"] == "REDUCE"
               for value in load_drafts(str(root)).values())
    assert len(api.ledger.list_events(project_id=PROJECT)) == 4


@pytest.mark.parametrize("version", ["1.0", "2.0"])
def test_actual_tech_lead_draft_adapter_uses_server_document_version_only(api, version):
    from types import SimpleNamespace
    from nodes.execution import _save_contract_draft
    from core.contract_decision import has_round_metadata
    root = api.path.parent.parent
    (root / "00_wbs_master_plan.json").write_text(json.dumps({"tasks": [
        {"task_id": TASK, "artifact_kind": "APP"}]}), encoding="utf-8")
    output = "```json contract-draft\n" + json.dumps({**DRAFT, "runtime_document_version": "2.0"}) + "\n```"
    _save_contract_draft(SimpleNamespace(workspace_root=str(root), current_sprint_task_id=TASK,
        runtime_document_version=version), output)
    assert has_round_metadata(str(root)) == (version == "2.0")
    data = pending(api)
    assert data["round_metadata_status"] == ("READY" if version == "2.0" else "LEGACY_UNPREPARED")
