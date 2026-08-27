from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace


def _write_release(root, release_id: str, project_id: str):
    folder = root / release_id
    folder.mkdir()
    (folder / "release.json").write_text(json.dumps({
        "release_id": release_id,
        "project_id": project_id,
        "project_name": f"{project_id} 앱",
        "created_at": "2026-08-27T00:00:00Z",
    }), encoding="utf-8")


def test_release_list_hides_other_context_and_unbound_releases(tmp_path, monkeypatch):
    from api.routes import factory_control as fc
    from core import library_paths

    _write_release(tmp_path, "rel_visible", "project_visible")
    _write_release(tmp_path, "rel_other_tenant", "project_other")
    _write_release(tmp_path, "rel_unbound", "")

    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    monkeypatch.setattr(fc, "assert_identified", lambda p, what: None)
    monkeypatch.setattr(fc, "viewing_context", lambda p: {
        "tenant_id": "tenant_a", "scope_node_id": "", "entity_mode": "REAL"})
    monkeypatch.setattr(fc, "_visible_projects_with_reasons",
                        lambda p, ctx: (["project_visible"], {"TENANT_MISMATCH": 1}))

    principal = SimpleNamespace(user_id="viewer@example.com", scope=SimpleNamespace())
    response = asyncio.run(fc.list_releases(principal))

    assert [row["release_id"] for row in response["data"]] == ["rel_visible"]
    assert "project_other" not in json.dumps(response, ensure_ascii=False)
    assert "TENANT_MISMATCH" not in json.dumps(response, ensure_ascii=False)


def test_release_list_does_not_fail_open_when_visibility_lookup_returns_empty(tmp_path, monkeypatch):
    from api.routes import factory_control as fc
    from core import library_paths

    _write_release(tmp_path, "rel_hidden", "project_hidden")
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(tmp_path))
    monkeypatch.setattr(fc, "assert_identified", lambda p, what: None)
    monkeypatch.setattr(fc, "viewing_context", lambda p: {
        "tenant_id": "tenant_a", "scope_node_id": "", "entity_mode": "REAL"})
    monkeypatch.setattr(fc, "_visible_projects_with_reasons", lambda p, ctx: ([], {}))

    principal = SimpleNamespace(user_id="viewer@example.com", scope=SimpleNamespace())
    response = asyncio.run(fc.list_releases(principal))

    assert response["data"] == []
