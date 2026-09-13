"""B3 고정 원천 물질화 회귀. main의 격리 runner에서만 실행한다.

저장소는 메모리 double이다. 운영 DB·RAW·인증/서명 생성은 하지 않는다.
Host의 고정 snapshot 실제 소비는 별도 dispatch 회귀에서 검증해야 한다.
"""
from __future__ import annotations

import copy

import pytest

from core import app_runtime_contract as arc
from core import contract_materializer as cm
from core import host_contract_compiler as compiler


# 편집 전에 읽기 전용으로 확보한 원본 SHA. 현재 코드로 재생성하지 않는다.
_MATERIALIZER_PRE_EDIT_SHA256 = "945571aa697c348167999af4c9d10ba1658ef93ada01e0286d4138e44ebd30c8"
BOUNDARY = {"tenant_id": "b3_tenant", "scope_node_id": "b3_root", "entity_mode": "REAL"}


def _ref():
    return {
        "process_id": "b3_process", "requirement_key": "arrivals_need",
        "instance_id": "fixed_instance", "contract_key": "purchase_orders",
        "artifact_digest": "a" * 64, "binding_id": "fixed_binding",
        "binding_fingerprint": "b" * 64, "snapshot_id": "fixed_snapshot",
        "snapshot_fingerprint": "c" * 64, "checksum": "d" * 64,
        "ownership_binding_id": "fixed_owner", "ownership_fingerprint": "e" * 64,
        "certification_state": "SOURCE_CERTIFIED", "certification_subject_id": None,
        "certification_subject_digest": None, "signing_policy_id": None,
        "signing_policy_digest": None, "certified_use_kind": None,
        "usage_policy_fingerprint": "f" * 64,
    }


def _context():
    return {
        "schema_version": 1, "configuration_id": "b3_configuration", "profile_id": "b3_profile",
        "process_ids": ["b3_process"], "process_semantic_fingerprint": "1" * 64,
        "configuration_fingerprint": "2" * 64,
        "context_key": {"tenant_id": BOUNDARY["tenant_id"], "context_root_id": "b3_root",
                        "entity_mode": "REAL", "scope_node_id": ""},
        "data_requirements": [{"process_id": "b3_process", "requirement_key": "arrivals_need",
            "logical_requirement": "원료 입고 실적", "mandatory": True,
            "candidate_contract_keys": ["purchase_orders"], "unresolved_requirement": False}],
        "verified_binding_refs": [_ref()], "blockers": [],
        "permitted_actions": ["READ", "DRAFT", "BOOTSTRAP", "GENERATE", "RUN", "RELEASE"],
        "sources": [{"kind": "PROCESS_PROFILE", "configuration_id": "b3_configuration",
                     "profile_id": "b3_profile", "fingerprint": "2" * 64}],
    }


def _ds(name="arrivals", key="purchase_orders"):
    return {"name": name, "label": "입고 내역", "purpose": "승인된 입고 내역 조회",
            "allowed_actions": ["read"], "data_role": "ENTERPRISE_ACTUAL",
            "source_intent": "ENTERPRISE_READ", "enterprise_contract_key": key,
            "duplicate_entry_policy": "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS",
            "fields": [{"name": "quantity", "type": "number", "required": True,
                        "classification": "INTERNAL", "semantic_role": "quantity", "unit": "ton"}]}


def _native():
    ds = _ds("notes")
    ds.pop("enterprise_contract_key")
    ds.update(data_role="NATIVE_SUPPLEMENT", source_intent="AFS_NATIVE",
              duplicate_entry_policy="NO_DUPLICATE_CHECK_REQUIRED")
    return ds


def _contract(*, context=None, datasets=None):
    result = compiler.compile_contract(
        {"app_class": "departmental", "capability_intents": [],
         "datasets": [_ds()] if datasets is None else datasets}, project_id="B3-M",
        document_version="2.0", process_context=_context() if context is None else context)
    assert result.ok, result.errors
    contract = result.contract
    contract.update(status="APPROVED", approval={"status": "APPROVED", "approved_by": "b3_reviewer",
        "approved_at": "2026-09-13T00:00:00Z", "decision_ledger_id": "b3_ledger"})
    assert not arc.validate(contract)
    return contract


class FixedStore:
    def __init__(self):
        ref = _ref()
        self.instance = {**BOUNDARY, "instance_id": ref["instance_id"], "status": "active",
                         "kit_fingerprint": ref["artifact_digest"]}
        self.binding = {**BOUNDARY, "instance_id": ref["instance_id"], "binding_id": ref["binding_id"],
                        "dataset_contract_key": ref["contract_key"], "state": "ACTIVE",
                        "fingerprint": ref["binding_fingerprint"]}
        self.calls = []

    def get_instance(self, instance_id):
        self.calls.append(("get_instance", instance_id))
        return copy.deepcopy(self.instance)

    def get_binding(self, binding_id):
        self.calls.append(("get_binding", binding_id))
        return copy.deepcopy(self.binding)

    def list_instances(self, **kwargs):
        raise AssertionError("v2 must not discover current candidates")

    def active_binding(self, *args):
        raise AssertionError("v2 must not switch to the current active binding")

    def list_snapshots(self, *args):
        raise AssertionError("v2 must not select a latest snapshot")


class AppData:
    def __init__(self, *, adopt=False):
        self.calls = []
        self.adopt = adopt

    def adopt_dataset(self, *args, **kwargs):
        self.calls.append(("adopt", args, kwargs))
        return {"name": args[0], "dataset_id": "existing_dataset"} if self.adopt else None

    def create_dataset(self, *args, **kwargs):
        self.calls.append(("create", args, kwargs))
        return {"name": args[1], "dataset_id": "new_dataset"}


def _materialize(contract, store, app_data, **boundary):
    return cm.materialize(contract, release_id="b3_release", actor_id="b3_actor",
                          store=store, app_data=app_data, **(boundary or BOUNDARY))


def test_v2_uses_only_exact_instance_and_binding_ids():
    store = FixedStore()
    contract = _contract()
    original = copy.deepcopy(contract)
    result = cm.plan(contract, store=store, **BOUNDARY)
    assert result[0].kit_instance_id == "fixed_instance"
    assert store.calls == [("get_instance", "fixed_instance"), ("get_binding", "fixed_binding")]
    assert contract == original
    # Resolved의 기존 tuple shape는 바꾸지 않는다. 전체 증거는 봉인 계약에 남는다.
    assert cm.Resolved._fields == ("name", "allowed_actions", "data_role", "source_intent",
                                  "enterprise_contract_key", "kit_instance_id", "schema")


def test_exact_ref_api_returns_a_copy_including_pinned_snapshot():
    context = _context()
    result = cm.resolve_process_binding(FixedStore(), process_context=context,
                                        contract_key="purchase_orders", **BOUNDARY)
    assert result == _ref()
    assert result["snapshot_id"] == "fixed_snapshot"
    result["snapshot_id"] = "changed_by_caller"
    assert context["verified_binding_refs"][0]["snapshot_id"] == "fixed_snapshot"


@pytest.mark.parametrize("adopt", [False, True])
def test_materialize_keeps_exact_instance_when_creating_or_adopting(adopt):
    store, app = FixedStore(), AppData(adopt=adopt)
    result = _materialize(_contract(), store, app)
    assert result.resolved[0].kit_instance_id == "fixed_instance"
    assert [call[0] for call in app.calls] == (["adopt"] if adopt else ["adopt", "create"])
    assert all(call[2]["kit_instance_id"] == "fixed_instance" for call in app.calls)


@pytest.mark.parametrize("row,field,value", [
    ("instance", "instance_id", "substituted"), ("instance", "kit_fingerprint", "9" * 64),
    ("instance", "status", "inactive"), ("instance", "tenant_id", "other"),
    ("instance", "scope_node_id", "other"), ("instance", "entity_mode", "VIRTUAL"),
    ("binding", "binding_id", "replacement"), ("binding", "instance_id", "replacement"),
    ("binding", "dataset_contract_key", "other"), ("binding", "fingerprint", "9" * 64),
    ("binding", "state", "RETIRED"), ("binding", "tenant_id", "other"),
    ("binding", "scope_node_id", "other"), ("binding", "entity_mode", "VIRTUAL"),
])
def test_changed_fixed_row_fails_before_app_data_writes(row, field, value):
    store, app = FixedStore(), AppData()
    getattr(store, row)[field] = value
    with pytest.raises(cm.MaterializeError):
        _materialize(_contract(), store, app)
    assert app.calls == []


@pytest.mark.parametrize("row", ["instance", "binding"])
def test_missing_exact_row_never_falls_back_to_another_candidate(row):
    store, app = FixedStore(), AppData()
    setattr(store, row, None)
    with pytest.raises(cm.MaterializeError):
        _materialize(_contract(), store, app)
    assert app.calls == []


@pytest.mark.parametrize("field,value", [("tenant_id", "other"), ("scope_node_id", "other"),
                                         ("entity_mode", "VIRTUAL"), ("scope_node_id", "")])
def test_v2_destination_boundary_is_exact_even_for_native_only(field, value):
    boundary = {**BOUNDARY, field: value}
    store, app = FixedStore(), AppData()
    with pytest.raises(cm.MaterializeError):
        _materialize(_contract(datasets=[_native()]), store, app, **boundary)
    assert store.calls == [] and app.calls == []


def test_selected_scope_is_not_silently_replaced_by_root():
    context = _context()
    context["context_key"]["scope_node_id"] = "b3_department"
    store = FixedStore()
    store.instance["scope_node_id"] = store.binding["scope_node_id"] = "b3_department"
    result = cm.plan(_contract(context=context), store=store,
                     **{**BOUNDARY, "scope_node_id": "b3_department"})
    assert result[0].kit_instance_id == "fixed_instance"


@pytest.mark.parametrize("mutation", ["missing_context", "empty_context", "stale_semantic",
                                     "missing_snapshot", "unknown_version", "not_approved", "pending_approval"])
def test_invalid_v2_contract_does_not_read_candidates_or_write(mutation):
    contract = _contract()
    if mutation == "missing_context": contract.pop("process_context")
    elif mutation == "empty_context": contract["process_context"] = {}
    elif mutation == "stale_semantic": contract["process_context"]["process_semantic_fingerprint"] = "9" * 64
    elif mutation == "missing_snapshot": contract["process_context"]["verified_binding_refs"][0].pop("snapshot_id")
    elif mutation == "unknown_version": contract["schema_version"] = "3.0"
    elif mutation == "not_approved": contract["status"] = "COMPILED"
    elif mutation == "pending_approval": contract["approval"] = {"status": "PENDING"}
    store, app = FixedStore(), AppData()
    with pytest.raises(cm.MaterializeError):
        _materialize(contract, store, app)
    assert store.calls == [] and app.calls == []


def test_missing_key_is_not_resolved_from_current_store_even_after_other_dataset_planned():
    store, app = FixedStore(), AppData()
    contract = _contract(datasets=[_native(), _ds(), _ds("unfixed", "unfixed_contract")])
    with pytest.raises(cm.MaterializeError):
        _materialize(contract, store, app)
    assert app.calls == []


def _two_requirement_context():
    context = _context()
    ref = copy.deepcopy(context["verified_binding_refs"][0])
    req = copy.deepcopy(context["data_requirements"][0])
    ref["requirement_key"] = req["requirement_key"] = "secondary_need"
    context["verified_binding_refs"].append(ref)
    context["data_requirements"].append(req)
    return context


def test_multiple_requirements_can_share_the_same_exact_physical_evidence():
    store = FixedStore()
    result = cm.plan(_contract(context=_two_requirement_context()), store=store, **BOUNDARY)
    assert result[0].kit_instance_id == "fixed_instance"
    assert len(store.calls) == 2


@pytest.mark.parametrize("field,value", [("instance_id", "other_instance"), ("binding_id", "other_binding"),
    ("snapshot_id", "newer_snapshot"), ("snapshot_fingerprint", "8" * 64),
    ("checksum", "8" * 64), ("ownership_binding_id", "other_owner"),
    ("usage_policy_fingerprint", "8" * 64)])
def test_conflicting_evidence_for_same_contract_key_is_not_arbitrarily_selected(field, value):
    context = _two_requirement_context()
    context["verified_binding_refs"][1][field] = value
    store, app = FixedStore(), AppData()
    with pytest.raises(cm.MaterializeError):
        _materialize(_contract(context=context), store, app)
    assert store.calls == [] and app.calls == []


def test_store_outage_is_not_missing_data_or_a_fallback(monkeypatch):
    store, app = FixedStore(), AppData()
    def unavailable(_):
        raise OSError("storage unavailable")
    monkeypatch.setattr(store, "get_binding", unavailable)
    with pytest.raises(cm.MaterializeError, match="저장소"):
        _materialize(_contract(), store, app)
    assert app.calls == []


def test_legacy_partial_contract_still_uses_existing_discovery_path():
    class LegacyStore(FixedStore):
        def list_instances(self, **kwargs):
            self.calls.append(("list_instances", kwargs))
            return [self.instance]

        def active_binding(self, instance_id, key):
            self.calls.append(("active_binding", instance_id, key))
            return self.binding

        def get_instance(self, _):
            raise AssertionError("legacy path changed")

        def get_binding(self, _):
            raise AssertionError("legacy path changed")
    # 기존 물질화기는 이 부분 계약을 받는다. 2.0의 full schema 검증을 1.0에 소급하지 않는다.
    contract = {"schema_version": "1.0", "status": "APPROVED", "revision": 1, "datasets": [_ds()]}
    store, app = LegacyStore(), AppData()
    result = _materialize(contract, store, app)
    assert result.resolved[0].kit_instance_id == "fixed_instance"
    assert [call[0] for call in store.calls] == ["list_instances", "active_binding"]
    assert [call[0] for call in app.calls] == ["adopt", "create"]
