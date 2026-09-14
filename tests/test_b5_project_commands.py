"""실제 HTTP/PDP/접수 원장/프로젝트 handler 회귀. 엔진·템플릿 준비만 명시 대역.

운영 실행/게시 수용 증거가 아니다. 공통 strict-writes 런너 안에서만 실행한다.
"""
import json
import os
from pathlib import Path
import uuid

import pytest

from tests import org_seed as org
from tests.test_b5_input_drafts import PROJECT, api, enforced_org, headers, isolated_stores  # noqa: F401


BASE = f"/api/v1/factory/{PROJECT}/execution-commands"


def command(operation="RELEASE"):
    return dict(client_request_id=str(uuid.uuid4()), operation=operation, task_id="PROJECT", input={})


def post(env, body, actor=org.MANAGER_A):
    return env.client.post(BASE, json=body, headers=headers(actor))


def read(env, body, actor=org.MANAGER_A):
    return env.client.get(BASE + "/" + body["client_request_id"], headers=headers(actor))


def receipt(response):
    assert response.status_code == 200, response.text
    return response.json()["request"]


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def project_commands(api, monkeypatch):
    from core import library_paths
    api.library = api.env.root / "command-library"
    monkeypatch.setattr(library_paths, "_LIBRARY_DIR", str(api.library))
    return api


@pytest.mark.parametrize("actor", [org.MEMBER_A, org.VIEWER_A])
def test_release_requires_publisher_not_just_project_run(project_commands, actor):
    env, body = project_commands, command()
    before = snapshot(env.root)
    assert post(env, body, actor).status_code == 403
    assert read(env, body, actor).status_code == 404
    assert snapshot(env.root) == before and not env.library.exists()


@pytest.mark.parametrize("operation", ["RELEASE", "REPLAN"])
def test_real_handler_missing_state_is_rejected_and_replay_does_not_dispatch(project_commands, operation):
    env, body = project_commands, command(operation)
    (env.root / "latest_state.json").unlink()
    before = snapshot(env.root)
    row = receipt(post(env, body))
    assert row["status"] == "REJECTED" and row["result"]["http_status"] == 404
    assert receipt(read(env, body)) == row
    # 이제 상태가 있어도 원키를 다시 실행하지 않는다.
    (env.root / "latest_state.json").write_text(json.dumps(env.state), encoding="utf-8")
    restored = snapshot(env.root)
    assert receipt(post(env, body)) == row
    assert snapshot(env.root) == restored and not env.library.exists()
    assert "latest_state.json" not in before


def test_replan_missing_prd_is_rejected_and_does_not_poison_next_key(project_commands):
    env = project_commands
    before = snapshot(env.root)
    for _ in range(2):
        body = command("REPLAN")
        row = receipt(post(env, body, org.MEMBER_A))
        assert row["status"] == "REJECTED" and row["result"]["http_status"] == 400
        assert receipt(read(env, body, org.MEMBER_A)) == row
    assert snapshot(env.root) == before and not env.library.exists()


@pytest.mark.parametrize("revoke_at", [1, 2, 3])
def test_release_rechecks_fresh_role_initial_reserved_and_before_dispatch(project_commands, monkeypatch, revoke_at):
    from api.routes import studio_execution_control as routes
    from core.org_directory import org_directory
    from core.studio_execution_guard import owns_execution_command
    env, body = project_commands, command()
    before = snapshot(env.root)
    original, calls = routes._command_authority, []
    cached = org_directory.resolve_scope(org.MANAGER_A)

    def current(pid, p, operation):
        calls.append(operation)
        if len(calls) == revoke_at:
            # 다른 연결에서 역할을 회수해 공유 scope 캐시를 무효화하지 않는다.
            with org_directory._connect() as conn:
                conn.execute("UPDATE user_dept_roles SET role='member' WHERE user_id=?", (org.MANAGER_A,))
                conn.commit()
            assert org_directory.resolve_scope(org.MANAGER_A) is cached
        return original(pid, p, operation)

    monkeypatch.setattr(routes, "_command_authority", current)
    response = post(env, body)
    if revoke_at < 3:
        assert response.status_code == 403, response.text
        assert read(env, body).status_code == 404
    else:
        # 접수 뒤 권한 회수: HTTP 미접수로 가장하지 않고 원키 조회로 복구한다.
        assert response.status_code == 503, response.text
        row = receipt(read(env, body))
        assert row["status"] == "REJECTED" and row["result"]["http_status"] == 403
    assert snapshot(env.root) == before and not env.library.exists()
    # 실제 command ownership은 worker task에만 있으므로 to_thread에서 허위 소유를 만들지 않는다.
    assert not owns_execution_command(env.orchestrator, PROJECT)


def prepare_replan(env, monkeypatch, *, engine_result=True):
    from api.routes import factory_control as factory
    from api.routes import studio_execution_control as routes
    from core.studio_execution_guard import owns_execution_command
    state = {**env.state, "prd_summary": "합성 PRD"}
    (env.root / "latest_state.json").write_text(json.dumps(state), encoding="utf-8")
    env.effects = []

    async def prepare(root, state):
        assert Path(root) == env.root
        assert owns_execution_command(env.orchestrator, PROJECT)
        assert routes.dispatch_context()["effect_started"] is True
        env.effects.append("prepare")
        (env.root / "synthetic-preparation.json").write_text(json.dumps(state), encoding="utf-8")

    async def start(task_id, state, root):
        assert task_id.startswith("REPLAN_")
        assert owns_execution_command(env.orchestrator, PROJECT)
        assert routes.dispatch_context()["effect_started"] is True
        env.effects.append("engine")
        return engine_result

    # 실제 replan handler와 _prepare_project_execution_or_conflict 효과 경계는 유지한다.
    monkeypatch.setattr(factory, "_prepare_project_execution", prepare)
    monkeypatch.setattr(env.orchestrator, "start_sprint", start)


def test_real_replan_accept_get_replay_and_changed_body_conflict(project_commands, monkeypatch):
    env, body = project_commands, command("REPLAN")
    prepare_replan(env, monkeypatch)
    row = receipt(post(env, body))
    assert row["status"] == "ACCEPTED"
    assert row["result"]["response"]["task_id"].startswith("REPLAN_")
    before = snapshot(env.root)
    assert receipt(read(env, body)) == row
    assert receipt(post(env, body)) == row
    assert post(env, {**body, "operation": "RELEASE"}).status_code == 409
    assert env.effects == ["prepare", "engine"] and snapshot(env.root) == before


def test_replan_effect_then_409_is_unknown_replay_never_restarts(project_commands, monkeypatch):
    env, body = project_commands, command("REPLAN")
    prepare_replan(env, monkeypatch, engine_result=False)
    row = receipt(post(env, body))
    assert row["status"] == "UNKNOWN" and row["result"]["http_status"] == 409
    assert receipt(read(env, body)) == row
    assert receipt(post(env, body)) == row
    assert post(env, command("REPLAN")).status_code == 409
    assert env.effects == ["prepare", "engine"]


@pytest.mark.parametrize("route", ["release", "wbs/replan"])
def test_legacy_project_route_cannot_bypass_persisted_unknown(project_commands, monkeypatch, route):
    env, body = project_commands, command("REPLAN")
    prepare_replan(env, monkeypatch, engine_result=False)
    row = receipt(post(env, body))
    assert row["status"] == "UNKNOWN"
    before = snapshot(env.root)
    response = env.client.post(f"/api/v1/factory/{PROJECT}/{route}", headers=headers(org.MANAGER_A))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason_code"] == "STUDIO_COMMAND_PROJECT_BUSY"
    assert receipt(read(env, body)) == row
    assert env.effects == ["prepare", "engine"]
    assert snapshot(env.root) == before and not env.library.exists()


def isolate_release_assets(env, monkeypatch):
    from core import master_data
    # 지연 import의 자산 singleton도 시험별 DB만 사용한다. 바깥 RUN 허용으로
    # inner SQLite guard를 넓히지 않는다.
    asset_db = str(env.env.root / "release-agent-assets.db")
    monkeypatch.setattr(master_data, "_DB_PATH", asset_db)
    from core import agent_assets, agent_asset_adapter
    monkeypatch.setattr(agent_assets.agent_assets, "db_path", asset_db)
    monkeypatch.setattr(agent_asset_adapter, "resolve_workflow", lambda *a, **k: {"id": "default", "agents": []})


def test_legacy_release_fresh_capability_revoked_after_preflight_writes_nothing(project_commands, monkeypatch):
    from core import library_paths
    from core.org_directory import org_directory
    env = project_commands
    isolate_release_assets(env, monkeypatch)
    original, reached = library_paths.release_dir, []

    def revoke(release_id):
        result = original(release_id)
        # 실제 사전 조회를 지난 뒤 별도 DB 연결에서 게시권한만 회수한다.
        with org_directory._connect() as conn:
            conn.execute("UPDATE user_dept_roles SET role='member' WHERE user_id=?", (org.MANAGER_A,))
            conn.commit()
        reached.append(release_id)
        return result

    monkeypatch.setattr(library_paths, "release_dir", revoke)
    before = snapshot(env.root)
    response = env.client.post(f"/api/v1/factory/{PROJECT}/release", headers=headers(org.MANAGER_A))
    assert response.status_code == 403, response.text
    assert len(reached) == 1 and not env.library.exists()
    assert snapshot(env.root) == before


def test_real_release_first_directory_effect_then_409_is_unknown(project_commands, monkeypatch):
    from fastapi import HTTPException
    env, body = project_commands, command()
    isolate_release_assets(env, monkeypatch)
    original, writes = os.makedirs, []

    def mkdir(path, *args, **kwargs):
        if Path(path).parent == env.library:
            original(path, *args, **kwargs)
            writes.append(str(path))
            raise HTTPException(409, "합성 디렉터리 생성 후 응답 장애")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", mkdir)
    row = receipt(post(env, body))
    assert row["status"] == "UNKNOWN" and row["result"]["http_status"] == 409
    assert len(writes) == 1 and Path(writes[0]).is_dir()
    assert receipt(read(env, body)) == row
    assert receipt(post(env, body)) == row
    assert post(env, command()).status_code == 409 and len(writes) == 1


def test_replan_committed_receipt_ack_loss_get_and_replay_do_not_repeat(project_commands, monkeypatch):
    from core.studio_execution_commands import CommandStore
    env, body = project_commands, command("REPLAN")
    prepare_replan(env, monkeypatch)
    original = CommandStore.finish
    calls = []

    def lost(self, **kwargs):
        result = original(self, **kwargs)
        calls.append(result)
        raise OSError("합성 commit acknowledgement loss")

    monkeypatch.setattr(CommandStore, "finish", lost)
    assert post(env, body).status_code == 503
    row = receipt(read(env, body))
    assert row["status"] == "ACCEPTED" and row == calls[0]
    assert receipt(post(env, body)) == row
    assert len(calls) == 1 and env.effects == ["prepare", "engine"]
