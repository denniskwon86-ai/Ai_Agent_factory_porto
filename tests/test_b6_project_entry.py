"""진입 확인 HTTP: 실제 격리 PDP/SQLite. 관리형 READ는 별도 실제 승인 fixture로 확인.

실제 실행/브라우저/업무 승인 증거가 아니다. main strict-writes 런너 전용.
"""
import json
import hashlib
import re
import sqlite3

import pytest

from tests import org_seed as org
from tests.test_b5_input_drafts import PROJECT, api, enforced_org, headers, isolated_stores  # noqa: F401
from tests.test_b3_execution_context import project, real_studio  # noqa: F401


URL = f"/api/v1/factory/{PROJECT}/entry-metadata"


def metadata(env, **changes):
    path = env.root / "project_meta.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update(changes)
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def get(env, actor=org.MEMBER_A, scope=None):
    return env.client.get(URL, headers=headers(actor, scope))


def data(response):
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"status", "data"}
    value = response.json()["data"]
    #: ⚠️ 정확히 이 집합이다. 느슨하게 풀지 않는다 — 이 단언이 「응답에 뭐가 더
    #:   따라 나오지 않는가」를 지키는 유일한 통제다.
    #: ★ [MEGA-ENTRY-01] 소속 두 칸이 계약에 «의도적으로» 늘었다(설계안 §10.3).
    assert set(value) == {"project_id", "project_name", "runtime_document_version",
                          "ownership", "viewing_context", "is_mega_project", "child"}
    assert set(value["ownership"]) == {"tenant_id", "enterprise_scope_id", "entity_mode"}
    assert set(value["viewing_context"]) == {"tenant_id", "scope_node_id", "entity_mode"}
    return value


@pytest.mark.parametrize("version_present", [True, False])
def test_legacy_exact_read_dto_and_missing_version_falls_back_to_1(api, version_present):
    value = metadata(api, project_name="합성 구매 프로젝트", private_note="응답에 노출하면 안 됨")
    if not version_present:
        value.pop("runtime_document_version")
        (api.root / "project_meta.json").write_text(json.dumps(value), encoding="utf-8")
    response = get(api, org.VIEWER_A)
    value = data(response)
    assert value == dict(project_id=PROJECT, project_name="합성 구매 프로젝트", runtime_document_version="1.0",
        is_mega_project=False, child=None,
        ownership=api.boundary, viewing_context=dict(tenant_id="tenant_default",
            scope_node_id=org.NODES[org.DEPT_A], entity_mode="REAL"))
    assert "private_note" not in response.text and "clarification_questions" not in response.text


def test_project_name_falls_back_to_id_without_state_name(api):
    assert data(get(api))["project_name"] == PROJECT


def test_managed_read_uses_verified_studio_version_without_leaking_context(api, monkeypatch):
    from core import studio_project_context
    metadata(api, runtime_document_version="2.0")
    studio = dict(runtime_document_version="2.0", process_context={"private": "no-return"},
                  approved_blueprint_revision_id="synthetic-approved")
    actions = []
    def verified(pid, principal, action):
        assert pid == PROJECT
        actions.append(action)
        return studio
    monkeypatch.setattr(studio_project_context, "for_principal", verified)
    response = get(api)
    assert data(response)["runtime_document_version"] == "2.0"
    assert actions == ["READ", "READ"] and "synthetic-approved" not in response.text


def test_unregistered_v2_does_not_downgrade_to_legacy(api):
    metadata(api, runtime_document_version="2.0")
    response = get(api)
    assert response.status_code == 503, response.text
    assert "data" not in response.json()


@pytest.mark.parametrize("version", [None, "3.0"])
def test_invalid_runtime_version_is_unavailable(api, version):
    metadata(api, runtime_document_version=version)
    assert get(api).status_code == 503


def test_deleted_project_is_hidden_even_for_admin(api):
    metadata(api, deleted_at="2026-09-14T00:00:00Z")
    response = get(api, org.ADMIN)
    assert response.status_code == 404 and "data" not in response.json()


def test_nonexistent_project_is_404_without_creating_directory(api):
    missing = api.root.parent / "MISSING_B6_PROJECT"
    assert not missing.exists()
    response = api.client.get("/api/v1/factory/MISSING_B6_PROJECT/entry-metadata", headers=headers())
    assert response.status_code == 404 and not missing.exists()


@pytest.mark.parametrize("raw", ["{broken", "[]"])
def test_corrupt_metadata_never_returns_legacy_success(api, raw):
    path = api.root / "project_meta.json"
    path.write_text(raw, encoding="utf-8")
    response = get(api)
    # 기존 PDP는 손상 소속을 먼저 404 은폐할 수도 있다.
    assert response.status_code in (404, 503) and "data" not in response.json()
    assert path.read_text(encoding="utf-8") == raw


def test_selected_other_scope_hides_project(api):
    response = get(api, org.ADMIN, org.NODES[org.DEPT_B])
    assert response.status_code == 404 and "data" not in response.json()


@pytest.mark.parametrize("method", ["direct_sql_department_move", "delete_user"])
def test_final_fresh_authority_rejects_revocation_after_metadata_read(api, monkeypatch, method):
    from api.routes import studio_revision_control
    from core.org_directory import org_directory
    original = studio_revision_control._same_context
    calls = []
    def revoke(pid, p, boundary, studio, *, write):
        assert write is False
        if method == "delete_user":
            org_directory.delete_user(org.MEMBER_A, actor="test")
        else:
            # 최초 실패를 보존: 공유 scope 캐시 무효화 없는 타 연결의 실제 권한 이동.
            with org_directory._connect() as conn:
                conn.execute("UPDATE user_dept_roles SET dept_id=? WHERE user_id=?", (org.DEPT_B, org.MEMBER_A))
                conn.execute("UPDATE users SET primary_dept_id=? WHERE user_id=?", (org.DEPT_B, org.MEMBER_A))
                conn.commit()
        calls.append(pid)
        return original(pid, p, boundary, studio, write=write)
    monkeypatch.setattr(studio_revision_control, "_same_context", revoke)
    response = get(api)
    assert calls == [PROJECT] and response.status_code == 404, response.text
    assert "data" not in response.json()


@pytest.mark.parametrize("name", [{}, [], 7, False, "x" * 2001], ids=["object", "array", "number", "bool", "too-long"])
def test_corrupt_project_name_is_503_without_echo(api, name):
    metadata(api, project_name=name)
    response = get(api)
    assert response.status_code == 503 and "data" not in response.json()


@pytest.mark.parametrize("name", [None, ""])
def test_empty_project_name_keeps_id_fallback(api, name):
    metadata(api, project_name=name)
    assert data(get(api))["project_name"] == PROJECT


def test_legacy_entry_no_checkpoint_input_store_or_sql_schema_and_business_writes(api, monkeypatch):
    from api.routes import studio_input_draft_control as drafts
    def normalized(sql):
        return " ".join(re.sub(r"--[^\n]*", "", sql).split()).rstrip(";")
    before = {str(p.relative_to(api.root)): p.read_bytes() for p in api.root.rglob("*") if p.is_file()}
    def forbidden(*args, **kwargs):
        pytest.fail("entry GET은 checkpoint/입력 원장을 사용하지 않는다")
    for name in ("read_pause_state", "read_hotl_context", "read_reconcile_state"):
        monkeypatch.setattr(api.orchestrator, name, forbidden)
    monkeypatch.setattr(drafts, "_storage", forbidden)
    connect, statements = sqlite3.connect, []
    def traced(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(sqlite3, "connect", traced)
    assert data(get(api))["project_id"] == PROJECT
    invalid = []
    for sql in statements:
        clean = normalized(sql)
        if clean.upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE", "WITH")):
            # 이전 알려진 DDL 예외를 제거했다. 성공 legacy 조회는 DDL/DML 모두0이다.
            invalid.append({"operation": clean.split()[0], "sha256": hashlib.sha256(clean.encode()).hexdigest()})
    assert not invalid, {"unexpected_sql": invalid}
    assert {str(p.relative_to(api.root)): p.read_bytes() for p in api.root.rglob("*") if p.is_file()} == before


def test_real_managed_read_uses_readonly_revision_connection_and_preserves_pdp(project, monkeypatch):
    """실제 승인판/승격/ECM/PDP. 인증 팩/데이터는 없으며 전체 DB 무쓰기 증거는 아니다."""
    from core import advisor_store
    from core.studio_project_context import project_context
    from pathlib import Path
    env = project
    monkeypatch.setattr(advisor_store, "advisor_store", env.advisor)
    expected_uri = Path(env.advisor.db_path).resolve().as_uri() + "?mode=ro"
    connect, statements, connections = sqlite3.connect, [], []
    def traced(database, *args, **kwargs):
        conn = connect(database, *args, **kwargs)
        if str(database) == expected_uri:
            connections.append(database)
            conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(sqlite3, "connect", traced)
    def forbidden():
        pytest.fail("관리형 READ도 AdvisorStore의 쓰기용 _connect를 호출하면 안 된다")
    monkeypatch.setattr(env.advisor, "_connect", forbidden)
    result = project_context(env.project_id, actor=env.author, context=env.context,
                             for_action="READ", processes=env.processes)
    assert result["runtime_document_version"] == "2.0" and result["setup_status"] == "READY"
    assert result["process_context"] == env.approved["process_ref"]
    assert len(connections) == 3  # cohort, 승격 원장, 승인판
    assert all(sql.lstrip().upper().startswith(("SELECT", "BEGIN", "COMMIT", "PRAGMA TABLE_INFO")) for sql in statements)
    from core.enterprise_context.process_schema import ProcessError
    with pytest.raises(ProcessError):
        project_context(env.project_id, actor=env.other, context=env.context,
                        for_action="READ", processes=env.processes)


@pytest.mark.parametrize("suffix", ["?mode=rw", "?mode=ro&immutable=1", "?mode=ro&vfs=unix", "?mode=memory"])
def test_fixture_still_rejects_uri_option_bypasses(isolated_stores, suffix):
    from pathlib import Path
    value = Path(isolated_stores.advisor.db_path).as_uri() + suffix
    with pytest.raises(AssertionError):
        sqlite3.connect(value, uri=True)


def test_entry_with_missing_advisor_database_is_503_without_recreating_it(api, monkeypatch):
    missing = api.env.root / "absent-advisor" / "advisor.db"
    monkeypatch.setattr(api.env.advisor, "db_path", str(missing))
    response = get(api)
    assert response.status_code == 503 and "data" not in response.json()
    assert not missing.parent.exists()
