from core.data_preparation import models as m
from core.data_preparation import snapshot_service as svc
from core.data_preparation.store import DataPreparationStore
from scripts import run_local_demo as demo
from scripts import seed_starter_data as seed


def _active_binding(store, instance_id, key):
    row = store.create_binding(
        instance_id=instance_id, dataset_contract_key=key,
        provider=m.PROVIDER_FILE_SNAPSHOT, config={}, tenant_id="tenant-test",
        scope_node_id="scope-test", entity_mode="REAL")
    for state in (m.VALIDATED, m.APPROVED, m.ACTIVE):
        row = store.transition(row["binding_id"], state)
    return row


def test_changed_app_dataset_is_a_new_snapshot_and_old_raw_survives(tmp_path,
                                                                    monkeypatch):
    from core import demo_vertical_slice as dv
    from core.data_preparation import store as dp

    store = DataPreparationStore(str(tmp_path / "dp.db"))
    monkeypatch.setattr(dp, "data_preparation_store", store)
    monkeypatch.setattr(demo, "TARGET_ROOT", str(tmp_path))
    store.upsert_kit_version(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION, name="old", mode="DEMO/SYNTHETIC",
        source_path="old.json", fingerprint_value="old-fp", profile={"datasets": []})
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION, kit_fingerprint="old-fp",
        tenant_id="tenant-test", scope_node_id="scope-test", entity_mode="REAL")
    binding = _active_binding(store, inst["instance_id"], "MDM-07")
    old_payload = b"cost_center_id,tenant_id,scope_node_id\nCC-1,tenant-test,scope-test\n"
    old = svc.ingest(store, binding=binding, payload=old_payload, file_name="MDM-07.csv",
                     workspace_root=str(tmp_path / "raw"))
    for state in (m.PROFILED, m.STANDARDIZED, m.RECONCILED, m.DEMO_CERTIFIED):
        old = store.advance_snapshot(old["snapshot_id"], state)

    rows = [{"cost_center_id": "CC-1", "cost_center_name": "구매 원가센터",
             "account_id": "A-1", "tenant_id": "tenant-test",
             "scope_node_id": "scope-test"}]
    cols = list(rows[0])
    monkeypatch.setattr(dv, "kit_dataset_keys", lambda: ["MDM-07"])
    monkeypatch.setattr(dv, "read_full", lambda _key: (rows, cols))

    assert seed._refresh_changed_app_datasets(inst["instance_id"]) == ["MDM-07"]
    snaps = store.list_snapshots(inst["instance_id"])
    assert [s["state"] for s in snaps] == [m.REVOKED, m.DEMO_CERTIFIED]
    assert svc.verify_raw(old["raw_path"], old["checksum"])
    with store.transaction() as conn:
        indexed = conn.execute(
            "SELECT count(*) FROM object_scope_index WHERE object_type='cost-center'").fetchone()[0]
    assert indexed == 1


def test_manifest_sync_updates_profile_and_instance_fingerprint(tmp_path, monkeypatch):
    from core import demo_vertical_slice as dv
    from core.data_preparation import store as dp

    store = DataPreparationStore(str(tmp_path / "dp.db"))
    monkeypatch.setattr(dp, "data_preparation_store", store)
    store.upsert_kit_version(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION, name="old", mode="DEMO/SYNTHETIC",
        source_path="old.json", fingerprint_value="old-fp",
        profile={"datasets": [], "outputs": [{"output": "APP-01"}]})
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION, kit_fingerprint="old-fp",
        tenant_id="tenant-test", scope_node_id="scope-test", entity_mode="REAL")

    assert seed._sync_kit_contract(inst["instance_id"]) is True
    kit = store.get_kit_version(dv.KIT_ID, dv.KIT_VERSION)
    assert [o["output"] for o in kit["profile"]["outputs"]] == [
        "APP-01", "APP-02", "APP-03", "APP-04", "APP-05", "APP-06", "APP-07"]
    assert store.get_instance(inst["instance_id"])["kit_fingerprint"] == kit["fingerprint"]
    before = store.get_kit_version(dv.KIT_ID, dv.KIT_VERSION)
    assert seed._sync_kit_contract(inst["instance_id"]) is False
    assert store.get_kit_version(dv.KIT_ID, dv.KIT_VERSION) == before
