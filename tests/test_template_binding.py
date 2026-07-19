"""T2-b 증분3 — 프로젝트↔워크플로우 템플릿 바인딩(factory_control).
create_project 가 template 을 검증·영속하고, start_sprint/heal 이 그 바인딩을 권위 있게
페이로드에 주입하는지(프론트 state 가 stale 해도 같은 템플릿으로 실행) 검증한다."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.factory_control as fc


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # ./projects 가 tmp 아래에 생기도록
    app = FastAPI()
    app.include_router(fc.router)
    return TestClient(app)


def test_meta_roundtrip(tmp_path):
    fc._write_project_meta(str(tmp_path), "marketing")
    assert fc._read_project_template(str(tmp_path)) == "marketing"


def test_meta_missing_defaults_to_default(tmp_path):
    assert fc._read_project_template(str(tmp_path)) == "default"


def test_create_project_default_writes_meta(client, tmp_path):
    r = client.post("/api/v1/factory/projects", json={"project_id": "P1"})
    assert r.status_code == 200, r.text
    assert r.json()["template_id"] == "default"
    meta = tmp_path / "projects" / "P1" / "project_meta.json"
    assert json.loads(meta.read_text(encoding="utf-8"))["template_id"] == "default"


def test_create_project_unknown_template_404(client):
    r = client.post("/api/v1/factory/projects", json={"project_id": "P2", "template_id": "ghost_xyz"})
    assert r.status_code == 404


def test_create_project_bad_format_400(client):
    r = client.post("/api/v1/factory/projects", json={"project_id": "P3", "template_id": "../etc"})
    assert r.status_code == 400


def test_start_sprint_injects_bound_template(client, tmp_path, monkeypatch):
    # 마케팅 템플릿을 격리 디렉터리에 생성
    import core.agent_registry as ar
    monkeypatch.setattr(ar, "TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(tmp_path / "agents_registry.json"))
    ar.copy_template("default", "mk", "마케팅")

    r = client.post("/api/v1/factory/projects", json={"project_id": "PB", "template_id": "mk"})
    assert r.status_code == 200, r.text

    captured = {}
    async def fake_start(task_id, payload, workspace_root):
        captured["payload"] = dict(payload)
        return True
    monkeypatch.setattr(fc.orchestrator, "start_sprint", fake_start)

    r = client.post("/api/v1/factory/PB/sprint/start",
                    json={"task_id": "PLANNING-1", "project_state_payload": {}})
    assert r.status_code == 200, r.text
    # 페이로드가 비어 있어도 바인딩된 템플릿이 권위 있게 주입돼야 한다
    assert captured["payload"]["template_id"] == "mk"
