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
    # ★ [2026-08-05] 작업공간 경로가 절대경로로 고정됐다(`core/paths.py`). cwd 만 옮기면
    #   더 이상 격리되지 않으므로 **격리 지점을 함께 돌린다.** 이 한 줄이 없으면 테스트가
    #   제품 `projects/` 에 프로젝트를 만든다.
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    app = FastAPI()
    app.include_router(fc.router)
    return TestClient(app)


def test_meta_roundtrip(tmp_path):
    fc._write_project_meta(str(tmp_path), "default")
    assert fc._read_project_template(str(tmp_path)) == "default"


def test_meta_missing_defaults_to_default(tmp_path):
    assert fc._read_project_template(str(tmp_path)) == "default"


def test_create_project_default_writes_meta(client, tmp_path):
    r = client.post("/api/v1/factory/projects", json={"project_id": "P1"})
    assert r.status_code == 200, r.text
    assert r.json()["template_id"] == "default"
    meta = tmp_path / "projects" / "P1" / "project_meta.json"
    body = json.loads(meta.read_text(encoding="utf-8"))
    assert body["template_id"] == "default"
    assert len(body["template_fingerprint"]) == 16
    assert body["template_binding_version"] == "v1"


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
    assert len(captured["payload"]["config_fingerprint"]) == 16


def _custom_template(tmp_path, monkeypatch, template_id="mk"):
    import core.agent_registry as ar
    monkeypatch.setattr(ar, "TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(tmp_path / "agents_registry.json"))
    ar.copy_template("default", template_id, "테스트 템플릿")
    return ar


def test_changed_template_is_blocked_before_orchestrator(client, tmp_path, monkeypatch):
    ar = _custom_template(tmp_path, monkeypatch)
    assert client.post("/api/v1/factory/projects",
                       json={"project_id": "P_CHANGED", "template_id": "mk"}).status_code == 200
    changed = ar.load_template_strict("mk")
    changed["agents"][0]["skill"] = "changed_skill"
    ar.save_template("mk", changed)
    called = False

    async def fake_start(*args, **kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(fc.orchestrator, "start_sprint", fake_start)
    r = client.post("/api/v1/factory/P_CHANGED/sprint/start",
                    json={"task_id": "PLANNING-1", "project_state_payload": {}})
    assert r.status_code == 409, r.text
    assert "변경" in r.text and called is False


@pytest.mark.parametrize("damage", ["delete", "corrupt"])
def test_missing_or_corrupt_bound_template_never_falls_back_to_default(
        client, tmp_path, monkeypatch, damage):
    _custom_template(tmp_path, monkeypatch)
    assert client.post("/api/v1/factory/projects",
                       json={"project_id": f"P_{damage}", "template_id": "mk"}).status_code == 200
    path = tmp_path / "templates" / "mk.json"
    path.unlink() if damage == "delete" else path.write_text("{broken", encoding="utf-8")
    r = client.post(f"/api/v1/factory/P_{damage}/sprint/start",
                    json={"task_id": "PLANNING-1", "project_state_payload": {}})
    assert r.status_code == 409, r.text
    assert "기본 템플릿으로 대체하지 않습니다" in r.text


def test_legacy_project_is_sealed_on_first_explicit_start(client, tmp_path, monkeypatch):
    project = tmp_path / "projects" / "P_LEGACY"
    project.mkdir(parents=True)
    (project / "project_meta.json").write_text(
        json.dumps({"template_id": "default", "owner_user_id": "test"}), encoding="utf-8")

    async def fake_start(*args, **kwargs):
        return True

    monkeypatch.setattr(fc.orchestrator, "start_sprint", fake_start)
    r = client.post("/api/v1/factory/P_LEGACY/sprint/start",
                    json={"task_id": "PLANNING-1", "project_state_payload": {}})
    assert r.status_code == 200, r.text
    body = json.loads((project / "project_meta.json").read_text(encoding="utf-8"))
    assert body["template_binding_version"] == "v1"
    assert len(body["template_fingerprint"]) == 16


def test_runtime_rechecks_expected_fingerprint(monkeypatch):
    import asyncio
    from core import agent_graph
    from core.config_snapshot import ConfigSnapshot
    monkeypatch.setattr("core.config_snapshot.capture", lambda tid: ConfigSnapshot(
        template_id=tid, fingerprint="current"))
    with pytest.raises(RuntimeError, match="실행 직전 지문"):
        asyncio.run(agent_graph.get_runtime_app("default", "sealed"))
