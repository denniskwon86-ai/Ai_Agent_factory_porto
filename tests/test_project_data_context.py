import hashlib

import pytest

from core.project_data_context import (
    ProjectDataBindingError,
    bind_instance,
    render_agent_context,
    validate_binding,
)


class FakeStore:
    def __init__(self, raw_path):
        self.instance = {
            "instance_id": "ki_hidden", "kit_id": "KIT-1", "version": "1.0.0",
            "kit_fingerprint": "kit-fp", "label": "비철 제련 시연 데이터",
            "tenant_id": "tenant-a", "scope_node_id": "plant-a",
            "entity_mode": "REAL", "status": "active",
        }
        self.kit = {
            "fingerprint": "kit-fp", "mode": "DEMO/SYNTHETIC",
            "profile": {"datasets": [
                {"dataset_contract_key": "PRC-01"},
                {"dataset_contract_key": "INV-01"},
            ]},
        }
        payload = raw_path.read_bytes()
        self.snapshots = {
            "ds_prc": {
                "snapshot_id": "ds_prc", "instance_id": "ki_hidden",
                "dataset_contract_key": "PRC-01", "state": "DEMO_CERTIFIED",
                "tenant_id": "tenant-a", "scope_node_id": "plant-a",
                "entity_mode": "REAL", "raw_path": str(raw_path),
                "checksum": hashlib.sha256(payload).hexdigest(), "certified_at": "2026-09-01",
            },
            "ds_inv": {
                "snapshot_id": "ds_inv", "instance_id": "ki_hidden",
                "dataset_contract_key": "INV-01", "state": "DEMO_CERTIFIED",
                "tenant_id": "tenant-a", "scope_node_id": "plant-a",
                "entity_mode": "REAL", "raw_path": str(raw_path),
                "checksum": hashlib.sha256(payload).hexdigest(), "certified_at": "2026-09-01",
            },
        }

    def get_instance(self, instance_id):
        return dict(self.instance) if instance_id == self.instance["instance_id"] else None

    def get_kit_version(self, kit_id, version):
        return dict(self.kit) if (kit_id, version) == ("KIT-1", "1.0.0") else None

    def list_snapshots(self, instance_id):
        return [dict(v) for v in self.snapshots.values() if v["instance_id"] == instance_id]

    def get_snapshot(self, snapshot_id):
        row = self.snapshots.get(snapshot_id)
        return dict(row) if row else None


@pytest.fixture()
def source(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("code,amount\nA,100\nB,200\n", encoding="utf-8")
    return path


def _bind(store):
    return bind_instance(store, "ki_hidden", tenant_id="tenant-a", entity_mode="REAL",
                         allowed_scope_nodes=["plant-a"])


def test_binding_seals_every_certified_contract(source):
    binding = _bind(FakeStore(source))
    assert binding["sealed_snapshots"] == {"INV-01": "ds_inv", "PRC-01": "ds_prc"}
    assert binding["instance_label"] == "비철 제련 시연 데이터"
    assert binding["kit_mode"] == "DEMO/SYNTHETIC"
    assert binding["prompt_egress_policy"] == "SYNTHETIC_ONLY"
    assert len(binding["binding_fingerprint"]) == 64


def test_out_of_scope_and_missing_have_same_public_error(source):
    store = FakeStore(source)
    messages = []
    for instance_id, scopes in (("does-not-exist", ["plant-a"]), ("ki_hidden", ["plant-b"])):
        with pytest.raises(ProjectDataBindingError) as exc:
            bind_instance(store, instance_id, tenant_id="tenant-a", entity_mode="REAL",
                          allowed_scope_nodes=scopes)
        messages.append(str(exc.value))
    assert messages[0] == messages[1]


def test_missing_certified_contract_is_not_silently_partial(source):
    store = FakeStore(source)
    store.snapshots["ds_inv"]["state"] = "RECONCILED"
    with pytest.raises(ProjectDataBindingError, match="1개 부족"):
        _bind(store)


def test_binding_tamper_is_rejected(source):
    store = FakeStore(source)
    binding = _bind(store)
    binding["scope_node_id"] = "plant-b"
    with pytest.raises(ProjectDataBindingError, match="지문"):
        validate_binding(store, binding)


def test_newer_snapshot_does_not_change_existing_binding(source):
    store = FakeStore(source)
    binding = _bind(store)
    newer = dict(store.snapshots["ds_prc"], snapshot_id="ds_prc_new",
                 certified_at="2026-09-02")
    store.snapshots["ds_prc_new"] = newer
    assert validate_binding(store, binding)["sealed_snapshots"]["PRC-01"] == "ds_prc"


def test_agent_receives_only_declared_contract(source):
    store = FakeStore(source)
    text = render_agent_context(store, _bind(store), ["PRC-01"])
    assert "[PRC-01]" in text
    assert "[INV-01]" not in text
    assert "전체 2행" in text
    assert "합성 시연 데이터" in text


def test_raw_file_change_fails_instead_of_becoming_empty_data(source):
    store = FakeStore(source)
    binding = _bind(store)
    source.write_text("code,amount\nA,999\n", encoding="utf-8")
    with pytest.raises(ProjectDataBindingError, match="체크섬"):
        render_agent_context(store, binding, ["PRC-01"])


def test_real_business_data_is_blocked_without_approved_model_route(source):
    store = FakeStore(source)
    store.kit["mode"] = "REAL"
    binding = _bind(store)
    assert binding["prompt_egress_policy"] == "BLOCKED_UNTIL_APPROVED_MODEL_ROUTE"
    with pytest.raises(ProjectDataBindingError, match="사설·무학습 모델"):
        render_agent_context(store, binding, ["PRC-01"])
