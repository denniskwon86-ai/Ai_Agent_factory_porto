"""일반 게시의 2.0 문맥·고정 원문 전달 회귀. 메인 격리 runner 전용."""
import asyncio
import copy
from types import SimpleNamespace

import pytest
from tests.test_b3_studio_drafts import isolated_stores  # noqa: F401
from tests.test_b3_materializer_v2 import _contract, _context


def release_pair():
    context = _context()
    contract = _contract(context=context)
    studio = dict(runtime_document_version="2.0", process_context=context,
                  tenant_id="b3_tenant", enterprise_scope_id="b3_root", entity_mode="REAL")
    release = {**copy.deepcopy(studio), "runtime_contract": contract, "project_id": contract["project_id"]}
    return release, studio


def test_general_publish_requires_same_server_context_and_approved_contract():
    from core.studio_release_context import assert_project_release
    release, studio = release_pair()
    assert_project_release(release, studio)


@pytest.mark.parametrize("field", ["runtime_contract", "runtime_document_version", "tenant_id", "enterprise_scope_id", "entity_mode", "process_context"])
def test_general_publish_rejects_missing_or_overwritten_context(field):
    from core.studio_release_context import assert_project_release
    from core.enterprise_context.process_schema import ProcessError
    release, studio = release_pair()
    release.pop(field)
    with pytest.raises(ProcessError):
        assert_project_release(release, studio)


def test_legacy_release_entry_keeps_existing_missing_state_error(isolated_stores, monkeypatch):
    from api.routes import factory_control as factory
    from core import studio_project_context
    from fastapi import HTTPException
    monkeypatch.setattr(factory, "assert_project_writable", lambda *a: None)
    monkeypatch.setattr(studio_project_context, "for_principal", lambda *a: None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(factory.create_release("legacy-missing-test", SimpleNamespace(user_id="test.invalid")))
    assert exc.value.status_code == 404


def test_materializer_uses_verified_sealed_document_not_workspace_reread(isolated_stores, monkeypatch):
    from api.routes import factory_control as factory
    from core import contract_materializer as cm
    release, _ = release_pair()
    original = copy.deepcopy(release["runtime_contract"])
    seen = []
    targets = []
    def materialize(contract, **kwargs):
        seen.append(copy.deepcopy(contract))
        targets.append({k: kwargs[k] for k in ("tenant_id", "scope_node_id", "entity_mode")})
        return cm.Result(datasets=[], resolved=[])
    monkeypatch.setattr(cm, "materialize", materialize)
    out = factory._materialize_contract_for_release("no-workspace-test", "synthetic-release",
        actor_id="test.invalid", profile="v1", ctx={"scope_node_id": "selected-parent"}, plane=object(), sealed_contract=original)
    assert out["state"] == "MATERIALIZED" and seen == [original]
    expected = dict(tenant_id="b3_tenant", scope_node_id="b3_root", entity_mode="REAL")
    assert targets == [expected]
    run = factory._promotion_materializer(release, "synthetic-release", "test.invalid", {"scope_node_id": "selected-parent"})
    run()
    assert targets == [expected, expected]
