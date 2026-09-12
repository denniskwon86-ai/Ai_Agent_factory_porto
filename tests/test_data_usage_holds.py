"""보류 표식의 생산자→저장소→인증/준비도/앱/계산 연결 회귀. DB는 임시 경로만 사용."""
import json
import sqlite3
from pathlib import Path

import pytest

from core import calc_dataset_loader as loader, kit_app_builder as apps
from core.data_preparation import models as m, readiness as rd, scope_index as ix
from core.data_preparation import snapshot_service as svc, usage_policy as policy
from core.data_preparation.store import DataPreparationStore

HOLDS = ["OWNERSHIP_AND_CERTIFICATION_REQUIRED", "HISTORICAL_ORGANIZATION_VALIDITY_REQUIRED",
         "PRICE_VINTAGE_AND_CONVERSION_POLICY_REQUIRED"]
CTX = {"tenant_id": "test-tenant", "scope_node_id": "test-plant", "entity_mode": "REAL"}
CSV = b"shipment_id,po_line_id,tenant_id,scope_node_id\nSHP-1,PO-1,test-tenant,test-plant\n"


@pytest.fixture
def store(tmp_path):
    return DataPreparationStore(str(tmp_path / "usage.db"))


def prepare(store, tmp_path, config=None, key="LOG-02", kind=m.DATA_KIND_DEMO):
    store.upsert_kit_version(kit_id="TEST-HOLD", version="1", name="보류 경계 시험",
                            source_path="test", fingerprint_value="test-only", profile={}, mode=m.DATA_KIND_DEMO)
    inst = store.create_instance(kit_id="TEST-HOLD", version="1", kit_fingerprint="test-only", **CTX)
    binding = store.create_binding(instance_id=inst["instance_id"], dataset_contract_key=key,
                                   provider=m.PROVIDER_FILE_SNAPSHOT, config=config or {}, **CTX)
    for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
        binding = store.transition(binding["binding_id"], target)
    snap = svc.ingest(store, binding=binding, payload=CSV, file_name="synthetic.csv",
                      workspace_root=str(tmp_path), data_kind=kind)
    parsed = svc.parse_csv(CSV)
    svc.profile(store, snap["snapshot_id"], parsed.rows, parsed.columns)
    svc.standardize(store, snap["snapshot_id"], parsed.rows)
    svc.reconcile(store, snap["snapshot_id"], parsed.rows, {"row_count": 1})
    return binding, store.get_snapshot(snap["snapshot_id"])


def set_test_config(store, binding, config):
    """인증된 구버전/손상 결속을 재현하는 시험 전용 SQL. 제품에 해제 경로를 만들지 않는다."""
    value = config if isinstance(config, str) else json.dumps(config)
    with store.transaction() as conn:
        conn.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
                     (value, binding["binding_id"]))


@pytest.mark.parametrize("config", [
    {"usage_holds": [hold]} for hold in HOLDS
] + [{"rehearsal_only": True}, {"price_hold_runtime_enforcement_installed": False},
     {"price_hold_runtime_enforcement_installed": True},
     {"usage_holds": "not-a-list"}, {"usage_holds": None}, {"usage_holds": [""]},
     {"usage_holds": [42]}, {"usage_holds": ["FUTURE_UNKNOWN_HOLD"]},
     {"rehearsal_only": "false"}])
def test_binding_holds_are_fail_closed(config):
    with pytest.raises(policy.UsageHoldError):
        policy.require_no_holds(list(policy.binding_holds({"config": config})))


@pytest.mark.parametrize("config", [{}, {"usage_holds": []}, {"rehearsal_only": False}])
def test_ordinary_bindings_are_not_held(config):
    assert policy.binding_holds({"config": config}) == ()


@pytest.mark.parametrize("key", ["FND-01", "FND-03", "MDM-04", "MDM-08", "EXT-02", "LOG-02"])
@pytest.mark.parametrize("endpoint", ["service", "store"])
def test_hold_prevents_certification_without_changing_raw_or_index(store, tmp_path, key, endpoint):
    binding, snap = prepare(store, tmp_path, {"usage_holds": HOLDS, "rehearsal_only": True}, key)
    before = Path(snap["raw_path"]).read_bytes()
    callback = []
    with pytest.raises(policy.UsageHoldError, match="사용 보류"):
        if endpoint == "service":
            svc.certify_demo(store, snap["snapshot_id"])
        else:
            store.advance_snapshot(snap["snapshot_id"], m.DEMO_CERTIFIED,
                                   certified_by="test-owner@afs.invalid", on_commit=lambda *_: callback.append(1))
    after = store.get_snapshot(snap["snapshot_id"])
    assert after["state"] == m.RECONCILED and not after["certified_at"]
    assert not after["certified_by"] and callback == []
    assert ix.bound_to(store, snap["snapshot_id"]) == 0
    assert Path(snap["raw_path"]).read_bytes() == before == CSV
    result = rd.evaluate_dataset(key, binding=binding, snapshots=[after], now="2026-09-12T00:00:00Z")
    assert result["state"] == rd.UNAVAILABLE and result["reason_code"] == "DATA_USAGE_HOLD"
    assert result["responsible_role"] == "데이터 오너" and result["next_action"]
    assert rd.evaluate_outputs([result], [{"output": "APP", "requires": [key]}])[0]["state"] == "BLOCKED"


@pytest.mark.parametrize("target", m.CERTIFIED_STATES)
def test_hold_blocks_every_certification_endpoint(store, tmp_path, target):
    _, snap = prepare(store, tmp_path, {"usage_holds": HOLDS}, kind=m.CERTIFICATION_DATA_KIND[target])
    with pytest.raises(policy.UsageHoldError):
        store.advance_snapshot(snap["snapshot_id"], target, certified_by="test@afs.invalid")
    assert store.get_snapshot(snap["snapshot_id"])["state"] == m.RECONCILED


@pytest.mark.parametrize("endpoint", ["service", "store"])
def test_replacement_hold_preserves_old_certified_snapshot(store, tmp_path, endpoint):
    binding, snap = prepare(store, tmp_path)
    svc.certify_demo(store, snap["snapshot_id"])
    new = svc.ingest(store, binding=binding, payload=CSV, file_name="replacement.csv", workspace_root=str(tmp_path))
    for target in (m.PROFILED, m.STANDARDIZED, m.RECONCILED):
        store.advance_snapshot(new["snapshot_id"], target)
    set_test_config(store, binding, {"usage_holds": HOLDS})
    with pytest.raises(policy.UsageHoldError):
        if endpoint == "service":
            svc.certify_demo_replacement(store, snap["snapshot_id"], new["snapshot_id"])
        else:
            store.replace_demo_snapshot(snap["snapshot_id"], new["snapshot_id"])
    assert store.get_snapshot(snap["snapshot_id"])["state"] == m.DEMO_CERTIFIED
    assert store.get_snapshot(new["snapshot_id"])["state"] == m.RECONCILED
    assert ix.bound_to(store, snap["snapshot_id"]) == 1 and ix.bound_to(store, new["snapshot_id"]) == 0


@pytest.mark.parametrize("config", [{"usage_holds": HOLDS}, "{bad", "null", "[]"])
def test_legacy_certified_hold_is_blocked_at_all_consumers(store, tmp_path, config, monkeypatch):
    binding, snap = prepare(store, tmp_path)
    svc.certify_demo(store, snap["snapshot_id"])
    set_test_config(store, binding, config)
    fresh = store.get_snapshot(snap["snapshot_id"])
    # 현재 ACTIVE 결속이 아닌 기존 판에 보류가 있어도 숨겨지지 않는다.
    result = rd.evaluate_dataset("LOG-02", binding={**binding, "config": {}},
                                 snapshots=store.list_snapshots(binding["instance_id"]), now="2026-09-12T00:00:00Z")
    assert result["state"] == rd.UNAVAILABLE
    assert ix.materialized_object_types(store) == {}
    assert ix.evidence_bound(store, ["LOG-02.shipment_id"], fresh["snapshot_id"])[0] is False
    with pytest.raises(ix.ScopeIndexError):
        ix.lookup(store, "dataset", "shipment", "SHP-1", CTX["tenant_id"], CTX["entity_mode"])
    with pytest.raises(ix.ScopeIndexError):
        ix.backfill_supported_snapshots(store)
    with pytest.raises(apps.KitAppError):
        apps.fields_from_certified(store, binding["instance_id"], "LOG-02")
    with pytest.raises(loader.SealedDatasetError):
        loader.active_seals(store, instance_id=binding["instance_id"], contract_keys=["LOG-02"])
    def forbidden_read(*args, **kwargs):
        pytest.fail("사용 보류 판의 업무 행을 읽었습니다")
    monkeypatch.setattr(loader, "_read_rows", forbidden_read)
    with pytest.raises(loader.SealedDatasetError):
        loader.load_sealed(store, sealed_snapshots={"LOG-02": fresh["snapshot_id"]}, **CTX)
    assert store.get_snapshot(fresh["snapshot_id"])["state"] == m.DEMO_CERTIFIED
    assert ix.bound_to(store, fresh["snapshot_id"]) == 1


def test_certification_policy_is_reread_inside_commit(store, tmp_path, monkeypatch):
    binding, snap = prepare(store, tmp_path)
    original = ix.plan
    def changed_after_plan(snapshot):
        payload = original(snapshot)
        set_test_config(store, binding, {"usage_holds": HOLDS})
        return payload
    monkeypatch.setattr(ix, "plan", changed_after_plan)
    with pytest.raises(policy.UsageHoldError):
        svc.certify_demo(store, snap["snapshot_id"])
    assert store.get_snapshot(snap["snapshot_id"])["state"] == m.RECONCILED
    assert ix.bound_to(store, snap["snapshot_id"]) == 0


def test_precomputed_index_payload_cannot_bypass_hold(store, tmp_path):
    binding, snap = prepare(store, tmp_path)
    payload = ix.plan(snap)
    set_test_config(store, binding, {"usage_holds": HOLDS})
    with pytest.raises(ix.ScopeIndexError):
        ix.write(store, payload, "2026-09-12T00:00:00Z")
    assert ix.bound_to(store, snap["snapshot_id"]) == 0


def test_held_newest_snapshot_never_falls_back_to_older_clear_one(store, tmp_path):
    binding, first = prepare(store, tmp_path)
    svc.certify_demo(store, first["snapshot_id"])
    second_binding = store.create_binding(instance_id=binding["instance_id"], dataset_contract_key="LOG-02",
                                          provider=m.PROVIDER_FILE_SNAPSHOT, config={}, **CTX)
    second = svc.ingest(store, binding=second_binding, payload=CSV, file_name="next.csv", workspace_root=str(tmp_path))
    for target in (m.PROFILED, m.STANDARDIZED, m.RECONCILED):
        store.advance_snapshot(second["snapshot_id"], target)
    svc.certify_demo(store, second["snapshot_id"])
    with store.transaction() as conn:
        for snapshot, date in ((first, "2026-01-01T00:00:00Z"), (second, "2026-02-01T00:00:00Z")):
            conn.execute("UPDATE dataset_snapshots SET certified_at=? WHERE snapshot_id=?", (date, snapshot["snapshot_id"]))
            conn.execute("UPDATE object_scope_index SET certified_at=? WHERE snapshot_id=?", (date, snapshot["snapshot_id"]))
    set_test_config(store, second_binding, {"usage_holds": HOLDS})
    with pytest.raises(loader.SealedDatasetError):
        loader.active_seals(store, instance_id=binding["instance_id"], contract_keys=["LOG-02"])
    with pytest.raises(ix.ScopeIndexError):
        ix.lookup(store, "dataset", "shipment", "SHP-1", CTX["tenant_id"], CTX["entity_mode"])
    assert ix.lookup(store, "dataset", "shipment", "SHP-1", CTX["tenant_id"], CTX["entity_mode"],
                     as_of="2026-01-15T00:00:00Z")[0] == ix.FOUND


def test_normal_data_reaches_real_consumers(store, tmp_path):
    binding, snap = prepare(store, tmp_path)
    certified = svc.certify_demo(store, snap["snapshot_id"])
    assert rd.evaluate_dataset("LOG-02", binding=binding, snapshots=[certified],
                               now="2026-09-12T00:00:00Z")["state"] == rd.READY
    assert ix.lookup(store, "dataset", "shipment", "SHP-1", CTX["tenant_id"], CTX["entity_mode"])[0] == ix.FOUND
    assert apps.fields_from_certified(store, binding["instance_id"], "LOG-02")
    seals = loader.active_seals(store, instance_id=binding["instance_id"], contract_keys=["LOG-02"])
    assert loader.load_sealed(store, sealed_snapshots=seals, **CTX)["LOG-02"][0]["shipment_id"] == "SHP-1"


@pytest.mark.parametrize("fault", ["missing", "wrong_context"])
def test_snapshot_cannot_borrow_another_binding_policy(store, tmp_path, fault):
    binding, snap = prepare(store, tmp_path)
    with store.transaction() as conn:
        if fault == "missing":
            conn.execute("DELETE FROM source_bindings WHERE binding_id=?", (binding["binding_id"],))
        else:
            conn.execute("UPDATE source_bindings SET tenant_id='other' WHERE binding_id=?", (binding["binding_id"],))
    with pytest.raises(policy.UsageHoldError):
        store.advance_snapshot(snap["snapshot_id"], m.DEMO_CERTIFIED, certified_by="test@afs.invalid")


def test_real_certification_route_returns_409_for_hold(store, tmp_path, monkeypatch, enforced_org):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as route
    from tests import org_seed
    import config

    binding, _ = prepare(store, tmp_path, {"usage_holds": HOLDS})
    raw = svc.ingest(store, binding=binding, payload=CSV, file_name="api-hold.csv", workspace_root=str(tmp_path))
    monkeypatch.setattr(route, "store", store)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(route, "_ctx", lambda _: {"tenant_id": CTX["tenant_id"], "entity_mode": CTX["entity_mode"]})
    monkeypatch.setattr(route, "_visible_scopes", lambda _: [CTX["scope_node_id"]])
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as client:
        result = client.post(f"/api/v1/data-preparation/snapshots/{raw['snapshot_id']}/certify",
                             json={"control": {"row_count": 1}}, headers={"X-Factory-User": org_seed.ADMIN})
    assert result.status_code == 409, result.text
    assert "사용 보류" in result.json()["detail"]
    assert store.get_snapshot(raw["snapshot_id"])["state"] == m.RECONCILED
    assert ix.bound_to(store, raw["snapshot_id"]) == 0


@pytest.mark.parametrize("endpoint", ["certify", "replace", "index"])
def test_policy_check_and_certification_are_serialized_across_connections(store, tmp_path, monkeypatch, endpoint):
    binding, snap = prepare(store, tmp_path, key="LOG-02" if endpoint == "index" else "FND-03")
    index_payload = ix.plan(snap) if endpoint == "index" else []
    if endpoint == "replace":
        svc.certify_demo(store, snap["snapshot_id"])
        new = svc.ingest(store, binding=binding, payload=CSV, file_name="next.csv", workspace_root=str(tmp_path))
        for state in (m.PROFILED, m.STANDARDIZED, m.RECONCILED):
            store.advance_snapshot(new["snapshot_id"], state)
    attempts = []
    original = policy.require_usable_conn
    def race(conn, snapshot):
        original(conn, snapshot)
        rival = sqlite3.connect(store.db_path, timeout=0.01)
        try:
            with rival:
                rival.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
                              (json.dumps({"usage_holds": HOLDS}), binding["binding_id"]))
            attempts.append("committed")
        except sqlite3.OperationalError as exc:
            assert "locked" in str(exc)
            attempts.append("locked")
        finally:
            rival.close()
    monkeypatch.setattr(policy, "require_usable_conn", race)
    if endpoint == "replace":
        store.replace_demo_snapshot(snap["snapshot_id"], new["snapshot_id"])
    elif endpoint == "index":
        ix.write(store, index_payload, "2026-09-12T00:00:00Z")
    else:
        store.advance_snapshot(snap["snapshot_id"], m.DEMO_CERTIFIED, certified_by="test@afs.invalid")
    assert attempts == ["locked"], "정책 검사와 인증 기록 사이에 다른 연결이 보류를 커밋했습니다"
    # 인증이 끝난 뒤의 보류 기록은 가능하며, 이후 소비를 실제로 차단한다.
    monkeypatch.setattr(policy, "require_usable_conn", original)
    set_test_config(store, binding, {"usage_holds": HOLDS})
    if endpoint == "index":
        with pytest.raises(policy.UsageHoldError):
            policy.require_usable(store, snap)
        return
    with pytest.raises(loader.SealedDatasetError):
        loader.active_seals(store, instance_id=binding["instance_id"], contract_keys=["FND-03"])
