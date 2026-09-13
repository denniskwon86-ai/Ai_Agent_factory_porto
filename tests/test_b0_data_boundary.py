"""B0-A: 일관된 읽기·구조화 오류·실제 프로젝트 HTTP 차단의 격리 회귀."""
import json
import sqlite3

import pytest

from core import calc_dataset_loader as loader
from core.data_preparation import models as m, snapshot_service as svc
from core.data_preparation.store import DataPreparationStore
from core.project_data_context import ProjectDataBindingError, bind_instance, render_agent_context
from tests.test_data_usage_holds import HOLDS, prepare, set_test_config
from tests.test_project_data_context import FakeStore


@pytest.mark.parametrize("read", ["get", "list", "between_rows"])
def test_snapshot_and_policy_share_one_read_snapshot(tmp_path, monkeypatch, read):
    store = DataPreparationStore(str(tmp_path / "read.db"))
    binding, first = prepare(store, tmp_path, key="FND-03")
    second = store.create_snapshot(**{k: first[k] for k in (
        "binding_id", "instance_id", "dataset_contract_key", "tenant_id", "scope_node_id", "entity_mode")})
    with store.transaction() as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    original = store._snapshot_public
    projections = []

    def project(conn, row):
        # get/list의 첫 SELECT 뒤 또는 목록의 두 행 사이에 독립 연결이 커밋한다.
        if len(projections) == (1 if read == "between_rows" else 0):
            rival = sqlite3.connect(store.db_path, timeout=1)
            try:
                with rival:
                    rival.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
                                  (json.dumps({"usage_holds": HOLDS}), binding["binding_id"]))
                    rival.execute("UPDATE dataset_snapshots SET row_count=99 WHERE instance_id=?",
                                  (binding["instance_id"],))
            finally:
                rival.close()
        result = original(conn, row)
        projections.append(result)
        return result

    monkeypatch.setattr(store, "_snapshot_public", project)
    rows = ([store.get_snapshot(first["snapshot_id"])] if read == "get"
            else store.list_snapshots(binding["instance_id"]))
    assert all(row["usage_holds"] == [] and row["row_count"] != 99 for row in rows)
    if read != "get":
        assert {r["snapshot_id"] for r in rows} == {first["snapshot_id"], second["snapshot_id"]}
    monkeypatch.setattr(store, "_snapshot_public", original)
    # 조회 DTO는 영구 승인이 아니다. 다음 조회는 새 보류와 새 스냅샷을 함께 본다.
    fresh = store.get_snapshot(first["snapshot_id"])
    assert fresh["row_count"] == 99 and set(fresh["usage_holds"]) == set(HOLDS)


@pytest.mark.parametrize("holds", ["MISSING", None, "not-list", [1], [""], ["FUTURE_UNKNOWN_HOLD"], HOLDS])
@pytest.mark.parametrize("consumer", ["active", "load", "binding", "render"])
def test_projection_only_consumers_fail_closed(tmp_path, holds, consumer):
    path = tmp_path / "synthetic.csv"
    path.write_text("code,amount\nA,1\n", encoding="utf-8")
    store = FakeStore(path)  # transaction()을 의도적으로 제공하지 않는 DTO 저장소
    binding = bind_instance(store, "ki_hidden", tenant_id="tenant-a", entity_mode="REAL",
                            allowed_scope_nodes=["plant-a"])
    store.snapshots["ds_prc"]["usage_holds"] = holds
    if holds == "MISSING":
        del store.snapshots["ds_prc"]["usage_holds"]
    error = ProjectDataBindingError if consumer in ("binding", "render") else loader.SealedDatasetError
    with pytest.raises(error) as exc:
        if consumer == "active":
            loader.active_seals(store, instance_id="ki_hidden", contract_keys=["PRC-01"])
        elif consumer == "load":
            loader.load_sealed(store, sealed_snapshots={"PRC-01": "ds_prc"},
                               tenant_id="tenant-a", entity_mode="REAL", scope_node_id="plant-a")
        elif consumer == "binding":
            bind_instance(store, "ki_hidden", tenant_id="tenant-a", entity_mode="REAL",
                          allowed_scope_nodes=["plant-a"])
        else:
            render_agent_context(store, binding, ["PRC-01"])
    unreadable = holds in ("MISSING", None, "not-list", [1], [""])
    assert exc.value.reason_code == ("USAGE_POLICY_UNREADABLE" if unreadable else "DATA_USAGE_HOLD")
    assert exc.value.category == ("unavailable" if unreadable else "conflict")


@pytest.mark.parametrize("case,expected,reason", [
    ("hold", 409, "DATA_USAGE_HOLD"), ("unreadable", 503, "USAGE_POLICY_UNREADABLE"),
    ("not_certified", 422, "DATA_CONTRACT_INVALID"),
    ("other_scope", 404, "DATA_INSTANCE_NOT_FOUND"),
    ("other_tenant", 404, "DATA_INSTANCE_NOT_FOUND"),
    ("other_mode", 404, "DATA_INSTANCE_NOT_FOUND"),
    ("missing", 404, "DATA_INSTANCE_NOT_FOUND"),
])
def test_project_http_preserves_boundary_and_creates_nothing(
        tmp_path, monkeypatch, enforced_org, case, expected, reason):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import factory_control as fc
    from core import agent_registry, paths
    from core.data_preparation import store as store_module
    from tests import org_seed
    import config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(agent_registry, "TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setattr(agent_registry, "REGISTRY_PATH", str(tmp_path / "agents_registry.json"))
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)  # 합성 신원, 실제 권한 판정은 유지
    store = DataPreparationStore(str(tmp_path / "http.db"))
    monkeypatch.setattr(store_module, "data_preparation_store", store)
    context = {"tenant_id": "tenant_default", "entity_mode": "REAL",
               "scope_node_id": org_seed.NODES[org_seed.DEPT_A]}
    if case == "other_scope":
        context["scope_node_id"] = org_seed.NODES[org_seed.DEPT_B]
    if case == "other_tenant":
        context["tenant_id"] = "other-tenant"
    if case == "other_mode":
        context["entity_mode"] = "VIRTUAL"
    store.upsert_kit_version(kit_id="B0", version="1", name="합성 HTTP 시험",
                            source_path="test", fingerprint_value="fp", mode=m.DATA_KIND_DEMO,
                            profile={"datasets": [{"dataset_contract_key": "FND-03"}]})
    inst = store.create_instance(kit_id="B0", version="1", kit_fingerprint="fp", **context)
    binding = store.create_binding(instance_id=inst["instance_id"], dataset_contract_key="FND-03",
                                   provider=m.PROVIDER_FILE_SNAPSHOT, config={}, **context)
    snap = store.create_snapshot(binding_id=binding["binding_id"], instance_id=inst["instance_id"],
                                  dataset_contract_key="FND-03", **context)
    for state in (m.PROFILED, m.STANDARDIZED, m.RECONCILED):
        store.advance_snapshot(snap["snapshot_id"], state)
    if case != "not_certified":
        store.advance_snapshot(snap["snapshot_id"], m.DEMO_CERTIFIED, certified_by=org_seed.MANAGER_A)
    set_test_config(store, binding, "{broken" if case == "unreadable" else {"usage_holds": HOLDS})
    app = FastAPI()
    app.include_router(fc.router)
    with TestClient(app) as client:
        result = client.post("/api/v1/factory/projects", headers={"X-Factory-User": org_seed.MEMBER_A},
                             json={"project_id": "B0_NO_PROJECT", "template_id": "default",
                                   "kit_instance_id": "missing" if case == "missing" else inst["instance_id"]})
    assert result.status_code == expected, result.text
    assert result.json()["detail"]["reason_code"] == reason
    assert not (tmp_path / "projects" / "B0_NO_PROJECT").exists()
    if expected == 404:
        assert "사용 보류" not in result.text and not any(code in result.text for code in HOLDS)
