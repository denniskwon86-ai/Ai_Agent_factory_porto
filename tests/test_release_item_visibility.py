"""[RELEASE-READ-VISIBILITY-01 · 2026-09-20] 릴리스 **단건 조회**의 열람 경계.

목록(`list_releases`)은 「보이는 프로젝트 집합」 밖을 건수까지 뺐는데, **단건
(`get_release`)에는 같은 검사가 없었다.** 릴리스 id 만 알면 그 프로젝트의 요구정의·기획서·
아키텍처·코드가 그대로 열렸다(격리 실측: 목록 제외 + 단건 200).

⚠️ 이 파일은 **차단이 존재를 누설하지 않는 것**까지 본다 — 「없는 릴리스」와 「안 보이는
  릴리스」의 응답이 같아야 한다. 사유를 세분해 주면 그 구분 자체가 존재를 알려 준다.
⚠️ 대역으로만 증명하지 않는다. 마지막 시험은 **실제 판정 경로**(`project_meta.json` →
  `project_visibility.project_visible`)를 그대로 태운다.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

VIEWER = "viewer@example.com"
CTX = {"tenant_id": "tenant_a", "scope_node_id": "", "entity_mode": "REAL"}


def _principal():
    #: ⚠️ `scope` 는 실제 `AccessScope` 와 **같은 모양**이어야 한다. 빈 네임스페이스를 주면
    #:   `ownership_visible` 이 `scope.unrestricted` 에서 예외 → 차단으로 답하고, 그러면
    #:   양성 대조가 «제품 결함처럼» 빨강이 된다(실제로 한 번 그렇게 났다).
    #: ★ `unrestricted=False` 로 둔다 — 무제한 통과가 아니라 **소유자 일치** 경로로 보이게 한다.
    return SimpleNamespace(user_id=VIEWER, scope=SimpleNamespace(
        unrestricted=False, is_admin=False, readable_dept_ids=frozenset()))


def _write_release(root, release_id: str, project_id: str, **extra):
    folder = root / release_id
    folder.mkdir()
    body = {
        "release_id": release_id,
        "project_id": project_id,
        "project_name": f"{project_id} 앱",
        "created_at": "2026-09-20T00:00:00Z",
        # 실행 payload — 차단 시 절대 나가면 안 되는 것들
        "frontend_code_summary": "SECRET_FRONTEND_CODE",
        "backend_code_summary": "SECRET_BACKEND_CODE",
        "artifacts": {"Frontend": "SECRET_ARTIFACT"},
    }
    body.update(extra)
    (folder / "release.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return folder / "release.json"


def _stub_visibility(monkeypatch, fc, visible_ids):
    monkeypatch.setattr(fc, "assert_identified", lambda p, what: None)
    monkeypatch.setattr(fc, "viewing_context", lambda p: dict(CTX))
    monkeypatch.setattr(fc, "_visible_projects_with_reasons",
                        lambda p, ctx: (list(visible_ids), {}))


def _get(fc, release_id):
    return asyncio.run(fc.get_release(release_id, _principal()))


def _expect_404(fc, release_id):
    with pytest.raises(HTTPException) as caught:
        _get(fc, release_id)
    assert caught.value.status_code == 404
    return caught.value


# ── 양성 대조 — 보이는 프로젝트의 릴리스는 그대로 열린다 ────────────────────
def test_item_serves_release_of_visible_project(tmp_path, monkeypatch):
    from api.routes import factory_control as fc
    from core import library_paths

    _write_release(tmp_path, "rel_ok", "project_visible")
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    _stub_visibility(monkeypatch, fc, ["project_visible"])

    body = _get(fc, "rel_ok")
    assert body["status"] == "success"
    assert body["data"]["release_id"] == "rel_ok"
    #: 이것이 없으면 아래 음성 시험이 「아무것도 안 주는」 시험이 된다.
    assert body["data"]["frontend_code_summary"] == "SECRET_FRONTEND_CODE"


# ── 음성 — 보이지 않는 프로젝트의 릴리스 ─────────────────────────────────
def test_item_hides_release_of_invisible_project(tmp_path, monkeypatch):
    from api.routes import factory_control as fc
    from core import library_paths

    _write_release(tmp_path, "rel_other", "project_other")
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    _stub_visibility(monkeypatch, fc, ["project_visible"])

    error = _expect_404(fc, "rel_other")
    #: 사유를 세분해 알려 주지 않는다 — 「다른 회사 것」이라고 답하면 존재가 새어 나간다.
    assert "project_other" not in str(error.detail)
    assert "SECRET" not in str(error.detail)


def test_item_hides_release_without_project_binding(tmp_path, monkeypatch):
    """소유 프로젝트가 없는 «고아» 릴리스도 열지 않는다 — 자동 귀속도 하지 않는다."""
    from api.routes import factory_control as fc
    from core import library_paths

    _write_release(tmp_path, "rel_unbound", "")
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    _stub_visibility(monkeypatch, fc, ["project_visible"])

    _expect_404(fc, "rel_unbound")


def test_item_hides_release_whose_owner_project_is_gone(tmp_path, monkeypatch):
    """소유 프로젝트가 «사라진» 릴리스 — 가시 집합에 없으므로 같은 404."""
    from api.routes import factory_control as fc
    from core import library_paths

    _write_release(tmp_path, "rel_orphan", "project_deleted")
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    _stub_visibility(monkeypatch, fc, ["project_visible"])

    _expect_404(fc, "rel_orphan")


# ── 차단이 존재를 누설하지 않는다 ────────────────────────────────────────
def test_hidden_release_answers_exactly_like_a_missing_one(tmp_path, monkeypatch):
    from api.routes import factory_control as fc
    from core import library_paths

    _write_release(tmp_path, "rel_other", "project_other")
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    _stub_visibility(monkeypatch, fc, ["project_visible"])

    hidden = _expect_404(fc, "rel_other")
    missing = _expect_404(fc, "rel_never_existed")
    assert (hidden.status_code, str(hidden.detail)) == (missing.status_code, str(missing.detail))


def test_hidden_release_file_is_not_modified(tmp_path, monkeypatch):
    """차단만 하고 **자료는 보존한다** — 읽기 경로가 파일을 만들거나 고치지 않는다."""
    from api.routes import factory_control as fc
    from core import library_paths

    path = _write_release(tmp_path, "rel_other", "project_other")
    before = path.read_bytes()
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    _stub_visibility(monkeypatch, fc, ["project_visible"])

    _expect_404(fc, "rel_other")
    assert path.read_bytes() == before


# ── 상태 확인 실패를 «사용 가능» 으로 취급하지 않는다 ──────────────────────
def test_lifecycle_lookup_failure_withholds_execution_payload(tmp_path, monkeypatch):
    """⚠️ 종전에는 `unknown` 으로만 바꾸고 실행 코드는 그대로 돌려줬다.

    상태를 «확인하지 못한 것» 과 «써도 되는 것» 은 다른 일이다."""
    from api.routes import factory_control as fc
    from core import library_paths, program_lifecycle as pl_module

    _write_release(tmp_path, "rel_ok", "project_visible")
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    _stub_visibility(monkeypatch, fc, ["project_visible"])

    class Broken:
        def assert_usable(self, _release_id):
            raise RuntimeError("SQLITE_DISK_IO_ERROR /operational/path/lifecycle.db")

    monkeypatch.setattr(pl_module, "program_lifecycle", Broken())

    data = _get(fc, "rel_ok")["data"]
    assert data["lifecycle"]["usable"] is None
    assert data["lifecycle"]["status"] == "unknown"
    #: 실행 payload 는 나가지 않는다.
    for key in ("frontend_code_summary", "backend_code_summary", "artifacts"):
        assert key not in data
    assert data["payload_withheld"]
    #: 예외 원문·파일 경로를 싣지 않는다.
    blob = json.dumps(data, ensure_ascii=False)
    assert "SQLITE_DISK_IO_ERROR" not in blob and "/operational/path" not in blob


# ── 대역이 아니라 «실제 판정 경로» 로 한 번 더 ────────────────────────────
def _write_project(root, project_id: str, tenant_id: str):
    folder = root / project_id
    folder.mkdir()
    (folder / "project_meta.json").write_text(json.dumps({
        "owner_user_id": VIEWER,          # 권한 축은 통과시키고 **문맥 축만** 가른다
        "visibility": "private",
        "tenant_id": tenant_id,
        #: ⚠️ 비우면 `RESOURCE_UNBOUND` 로 **비노출**이다(「범위 미지정은 전사 공용이 아니라
        #:   비노출」). 빈 값으로 두면 양성 대조가 «제품 결함처럼» 빨강이 된다 — 실제로
        #:   한 번 그렇게 났다. 두 프로젝트에 **같은** 범위를 주어 테넌트 축만 가른다.
        "enterprise_scope_id": "node_smelter",
        "entity_mode": "REAL",
        "ownership_basis": "USER_DECLARED",
    }, ensure_ascii=False), encoding="utf-8")


def test_item_uses_the_real_visibility_decision(tmp_path, monkeypatch):
    """`_visible_projects_with_reasons` 를 **대역으로 바꾸지 않고** 그대로 태운다.

    ⚠️ 가시 집합 대역만으로는 「내가 정한 규칙」을 확인할 뿐이다. 실제
      `project_meta.json` → `project_visibility.project_visible` 판정으로 갈린다는 것을
      한 번은 보아야 한다."""
    from api.routes import factory_control as fc
    from core import library_paths

    workspace = tmp_path / "projects"
    workspace.mkdir()
    _write_project(workspace, "project_mine", "tenant_a")      # 같은 테넌트 → 보인다
    _write_project(workspace, "project_theirs", "tenant_b")    # 다른 테넌트 → 안 보인다

    library = tmp_path / "library"
    library.mkdir()
    _write_release(library, "rel_mine", "project_mine")
    _write_release(library, "rel_theirs", "project_theirs")

    monkeypatch.setattr(library_paths, "library_dir", lambda: str(library))
    monkeypatch.setattr(fc, "workspace_path", lambda *a, **k: str(workspace))
    monkeypatch.setattr(fc, "assert_identified", lambda p, what: None)
    monkeypatch.setattr(fc, "viewing_context", lambda p: dict(CTX))
    #: ★ `_visible_projects_with_reasons` 는 **그대로 둔다.**

    mine = _get(fc, "rel_mine")["data"]
    assert mine["release_id"] == "rel_mine"

    error = _expect_404(fc, "rel_theirs")
    assert "project_theirs" not in str(error.detail)
