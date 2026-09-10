"""롤백 버튼의 실제 인증 HTTP 경로: 중단·부분 실패·기록·재시도. 모든 쓰기는 tmp_path."""
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.real_auth
REL = 'rollback-fixture-v1'
ADMIN = 'operator@rollback.invalid'
USER = 'reader@rollback.invalid'


@pytest.fixture
def env(tmp_path, monkeypatch):
    import api.deps as deps
    import api.routes.auth_control as ac
    import api.routes.readiness_control as rc
    import core.org_directory as orgmod
    import core.scope_policy as sp
    import core.workspace_promotion as wm
    from core import library_paths
    from core.org_directory import OrgDirectory
    from core.program_lifecycle import program_lifecycle as pl
    from core.release_readiness import ReleaseReadiness
    from core.workspace_promotion import WorkspacePromotion

    org = OrgDirectory(db_path=str(tmp_path / 'org.db'))
    org.create_department('hq', '본사', scope_node_id='corp-fixture', actor='fixture')
    org.upsert_user(ADMIN, '운영 관리자', primary_dept_id='hq', is_data_admin=True, actor='fixture')
    org.upsert_user(USER, '조회 사용자', primary_dept_id='hq', actor='fixture')
    for mod in (orgmod, deps, ac):
        monkeypatch.setattr(mod, 'org_directory', org)
    monkeypatch.setattr(sp, '_read', lambda: {'org_enforce': True})
    library = tmp_path / 'library'
    (library / REL).mkdir(parents=True)
    release = library / REL / 'release.json'
    release.write_text(json.dumps({'release_id': REL, 'project_id': 'fixture',
                                    'frontend_code_summary': 'original artifact'}), encoding='utf-8')
    monkeypatch.setattr(library_paths, '_LIBRARY_DIR', str(library))
    ws = WorkspacePromotion(db_path=str(tmp_path / 'workspace.db'))
    rd = ReleaseReadiness(db_path=ws.db_path)
    monkeypatch.setattr(wm, 'workspace', ws)
    monkeypatch.setattr(rc, 'release_readiness', rd)
    app = FastAPI()
    app.include_router(ac.router)
    app.include_router(rc.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, rd, ws, pl, release


def login(client, user=ADMIN):
    from core.auth import DEFAULT_PASSWORD
    r = client.post('/api/v1/auth/login', json={'user_id': user, 'password': DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    return {'X-Session-Token': r.json()['data']['token']}


def post(client, headers, **overrides):
    return client.post('/api/v1/readiness/rollback', headers=headers,
                       json={'release_id': REL, 'reason': '격리 회귀: 결과 오류', **overrides})


def promote(ws):
    ws.request_promotion(REL, 'corp-fixture', ADMIN)
    ws.owner_approve(REL, ADMIN)
    # 승격 자체의 검증을 우회하는 제품 경로가 아니라 철회 시험의 초기 상태다.
    with ws._connect() as conn:
        conn.execute("UPDATE release_promotions SET status='promoted' WHERE release_id=?", (REL,))


def test_authenticated_button_disables_and_records_without_deleting(env):
    client, rd, ws, pl, release = env
    before = release.read_bytes()
    promote(ws)
    r = post(client, login(client))
    assert r.status_code == 200, r.text
    out = r.json()['data']
    assert out['outcome'] == 'complete' and out['program_disabled'] is True
    assert out['revoked_promotion'] is True and out['history_recorded'] is True
    assert pl.get_status(REL)['status'] == 'disabled'
    assert ws.get_promotion(REL)['status'] == 'revoked'
    assert rd.rollback_history(REL)[0]['outcome'] == 'complete'
    assert release.read_bytes() == before


def test_disable_failure_is_503_and_does_not_revoke(env, monkeypatch):
    client, rd, ws, pl, _ = env
    promote(ws)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('locked')
    monkeypatch.setattr(pl, 'disable', fail)
    r = post(client, login(client))
    assert r.status_code == 503, r.text
    out = r.json()['detail']['rollback']
    assert out['outcome'] == 'failed' and out['program_disabled'] is False
    assert ws.get_promotion(REL)['status'] == 'promoted'
    assert rd.rollback_history(REL)[0]['outcome'] == 'failed'


@pytest.mark.parametrize('method', ['get_promotion', 'revoke_promotion'])
def test_promotion_failure_is_partial_and_retry_preserves_disable_history(env, monkeypatch, method):
    client, rd, ws, pl, _ = env
    promote(ws)
    headers = login(client)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('locked')
    with monkeypatch.context() as m:
        m.setattr(ws, method, fail)
        r = post(client, headers)
    assert r.status_code == 503, r.text
    out = r.json()['detail']['rollback']
    assert out['outcome'] == 'partial' and out['program_disabled'] is True
    assert rd.rollback_history(REL)[0]['outcome'] == 'partial'
    state, history = pl.get_status(REL), pl.history(REL)
    retry = post(client, headers)
    assert retry.status_code == 200, retry.text
    assert retry.json()['data']['outcome'] == 'complete'
    assert ws.get_promotion(REL)['status'] == 'revoked'
    assert pl.get_status(REL) == state and pl.history(REL) == history


def test_noop_disable_is_not_success(env, monkeypatch):
    client, rd, ws, pl, _ = env
    monkeypatch.setattr(pl, 'disable', lambda *args, **kwargs: {})
    r = post(client, login(client))
    assert r.status_code == 503
    assert r.json()['detail']['rollback']['outcome'] == 'failed'


@pytest.mark.parametrize('body', [
    {'reason': '  '}, {'release_id': 'missing'}, {'release_id': '../outside'},
    {'to_release_id': REL}, {'to_release_id': '../outside'},
])
def test_invalid_request_changes_nothing(env, body):
    client, rd, ws, pl, _ = env
    r = post(client, login(client), **body)
    assert r.status_code == 400, r.text
    assert rd.rollback_history() == [] and pl.history(REL) == []


@pytest.mark.parametrize('user', [None, USER])
def test_anonymous_or_reader_cannot_disable(env, user):
    client, rd, ws, pl, _ = env
    r = post(client, login(client, user) if user else {})
    assert r.status_code in (401, 403), r.text
    assert rd.rollback_history() == [] and pl.history(REL) == []


def test_history_unavailable_before_start_changes_nothing(env, monkeypatch):
    client, rd, ws, pl, _ = env
    def fail():
        raise sqlite3.OperationalError('locked')
    monkeypatch.setattr(rd, '_connect', fail)
    r = post(client, login(client))
    assert r.status_code == 503 and pl.history(REL) == []


def test_history_failure_after_disable_never_returns_success(env, monkeypatch):
    client, rd, ws, pl, _ = env
    original, count = rd._connect, 0
    def fail_second():
        nonlocal count
        count += 1
        if count == 2:
            raise sqlite3.OperationalError('locked')
        return original()
    monkeypatch.setattr(rd, '_connect', fail_second)
    r = post(client, login(client))
    assert r.status_code == 503, r.text
    assert r.json()['detail']['rollback']['history_recorded'] is False
    assert pl.get_status(REL)['status'] == 'disabled'
    assert rd.rollback_history(REL)[0]['outcome'] == 'in_progress'


def test_legacy_history_is_unknown_not_assumed_success(tmp_path):
    from core.release_readiness import ReleaseReadiness
    db = str(tmp_path / 'legacy.db')
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE release_rollbacks (rollback_id TEXT PRIMARY KEY, '
                     'release_id TEXT NOT NULL,to_release_id TEXT,reason TEXT NOT NULL,'
                     'actor TEXT NOT NULL,revoked_promotion INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)')
        conn.execute("INSERT INTO release_rollbacks VALUES('old','app','','old reason','actor',0,'2026-01-01')")
    rd = ReleaseReadiness(db_path=db)
    row = rd.rollback_history()[0]
    assert row['outcome'] == 'unknown' and row['program_disabled'] is None
    assert ReleaseReadiness(db_path=db).rollback_history() == [row]
