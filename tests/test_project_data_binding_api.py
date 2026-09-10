import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.factory_control as fc


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import core.agent_registry as ar
    import core.paths as paths
    monkeypatch.setattr(paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(ar, "TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(tmp_path / "agents_registry.json"))
    ar.copy_template("default", "grounded", "데이터 결속 시험")
    template = ar.load_template_strict("grounded")
    template["agents"][0]["data_contracts"] = ["PRC-01"]
    ar.save_template("grounded", template)

    app = FastAPI()
    app.include_router(fc.router)
    return TestClient(app), tmp_path


def test_data_using_template_requires_visible_instance_selection(env):
    client, _ = env
    response = client.post("/api/v1/factory/projects", json={
        "project_name": "구매 시뮬레이션", "template_id": "grounded",
    })
    assert response.status_code == 422
    assert "적용본" in response.text


def test_server_binding_is_persisted_and_client_payload_cannot_replace_it(
        env, monkeypatch):
    client, tmp_path = env
    sealed = {
        "binding_version": "v1", "binding_fingerprint": "server-fp",
        "instance_id": "ki_server", "sealed_snapshots": {"PRC-01": "ds_server"},
    }
    monkeypatch.setattr("core.project_data_context.bind_instance", lambda *a, **k: dict(sealed))
    response = client.post("/api/v1/factory/projects", json={
        "project_name": "구매 시뮬레이션", "template_id": "grounded",
        "kit_instance_id": "ki_selected",
    })
    assert response.status_code == 200, response.text
    project_id = response.json()["project_id"]
    meta_path = tmp_path / "projects" / project_id / "project_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["business_data_binding"] == sealed

    monkeypatch.setattr("core.project_data_context.validate_binding",
                        lambda store, value: dict(value))
    captured = {}

    async def fake_start(task_id, payload, workspace_root):
        captured.update(payload)

    monkeypatch.setattr(fc.orchestrator, "start_sprint", fake_start)
    response = client.post(f"/api/v1/factory/{project_id}/sprint/start", json={
        "task_id": "PLANNING-1",
        "project_state_payload": {"business_data_binding": {"instance_id": "ki_client"}},
    })
    assert response.status_code == 200, response.text
    assert captured["business_data_binding"] == sealed


def test_old_unbound_grounded_project_is_blocked_before_agent_run(env, monkeypatch):
    client, tmp_path = env
    project = tmp_path / "projects" / "P_UNBOUND"
    project.mkdir(parents=True)
    fc._write_project_meta(str(project), "grounded", owner_user_id="test",
                           enterprise_scope_id="sandbox", entity_mode="SYNTHETIC_TEST",
                           data_binding={})
    called = False

    async def fake_start(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(fc.orchestrator, "start_sprint", fake_start)
    response = client.post("/api/v1/factory/P_UNBOUND/sprint/start", json={
        "task_id": "PLANNING-1", "project_state_payload": {},
    })
    assert response.status_code == 409
    assert called is False
