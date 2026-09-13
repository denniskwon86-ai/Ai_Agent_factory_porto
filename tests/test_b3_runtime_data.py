"""B3 실제 임시 DP/승인/물질화/Host dispatch. 합성 인증 메타데이터만 사용한다."""
import copy
import hashlib
from types import SimpleNamespace

import pytest

from tests.test_b3_kit_contract_v2 import (kit, installation, workspace, enforced_org,  # noqa: F401
    draft, approve, metadata_certified, database, hold)
from tests import org_seed as org


@pytest.fixture
def runtime(kit):
    from core import contract_materializer as cm
    from core.app_data import AppDataService
    from core.app_data_store import AppDataStore
    from core.studio_release_cohort import pin_release_cohort
    w = kit
    row = approve(w, draft(w))
    contract = row["contract"]
    rid = "b3-host.test.invalid"
    plane = AppDataService(AppDataStore(str(w["root"] / "b3-app-data.db")))
    out = cm.materialize(contract, release_id=rid, actor_id=org.MEMBER_A, store=w["store"],
        app_data=plane, **w["context"])
    pin_release_cohort(w["store"], release_id=rid, instance_id=w["instance_id"], app_id="APP-03",
                       context_key=w["fixed"]["context_key"])
    release = dict(release_id=rid, project_id=rid, instance_id=w["instance_id"], app_id="APP-03",
                   runtime_document_version="2.0", runtime_contract=contract)
    dataset = next(d for d in out.datasets if plane.binding_for(rid, d["dataset_id"])["enterprise_contract_key"] == "INV-01")
    binding = plane.binding_for(rid, dataset["dataset_id"])
    return {**w, "contract": contract, "release": release, "rid": rid, "plane": plane,
            "dataset": dataset, "binding": binding}


def require(w, **changes):
    from core.studio_release_context import require_release_context
    args = dict(release_id=w["rid"], actor=org.VIEWER_A, context=w["context"], store=w["store"],
        processes=w["ctx"], revisions=SimpleNamespace(is_v2_project=lambda _: False))
    return require_release_context(w["release"], **{**args, **changes})


def resolve(w, **changes):
    from core.studio_runtime_data import resolve_dataset
    return resolve_dataset(w["release"], w["binding"], actor=org.VIEWER_A,
        context=w["context"], store=w["store"], processes=w["ctx"], **changes)


def test_actual_approved_kit_viewer_can_read_exact_snapshot(runtime):
    assert "RUN" in require(runtime)["permitted_actions"]
    binding, snapshots, scope, max_age = resolve(runtime)
    assert len(snapshots) == 1
    assert snapshots[0]["snapshot_id"] == runtime["data"]["INV-01"]["snapshot_id"]
    assert binding["binding_id"] == runtime["data"]["INV-01"]["binding"]["binding_id"]
    assert scope == runtime["context"]
    assert max_age == 30.0


def test_later_certified_snapshot_changes_neither_consumed_data_nor_proof_fingerprint(runtime, monkeypatch):
    from core import app_contract_gate as gate
    w = runtime
    monkeypatch.setattr("core.data_preparation.store.data_preparation_store", w["store"])
    before = gate.data_fingerprint(w["rid"], w["plane"], contract=w["contract"])
    assert before not in (gate.UNREADABLE, gate.NO_DATA)
    newer = metadata_certified(w, "INV-01", existing_binding=w["data"]["INV-01"]["binding"], column="new_column")
    monkeypatch.setattr(w["store"], "list_snapshots", lambda *a, **k: pytest.fail("최신판 열거 금지"))
    assert resolve(w)[1][0]["snapshot_id"] != newer["snapshot_id"]
    assert gate.data_fingerprint(w["rid"], w["plane"], contract=w["contract"]) == before


def test_new_usage_hold_blocks_fixed_consumption_and_fingerprint(runtime, monkeypatch):
    from core import app_contract_gate as gate
    w = runtime
    monkeypatch.setattr("core.data_preparation.store.data_preparation_store", w["store"])
    hold(w)
    with pytest.raises(Exception):
        resolve(w)
    with pytest.raises(Exception):
        require(w)
    assert gate.data_fingerprint(w["rid"], w["plane"], contract=w["contract"]) == gate.UNREADABLE


@pytest.mark.parametrize("field,value", [("runtime_name", "unknown"), ("source_intent", ""),
    ("contract_bound", 0), ("kit_instance_id", "other"), ("enterprise_contract_key", "INV-02")])
def test_mismatched_materialized_binding_has_no_native_or_latest_fallback(runtime, field, value):
    from core.enterprise_context.process_schema import ProcessError
    runtime["binding"][field] = value
    with pytest.raises(ProcessError):
        resolve(runtime)


@pytest.mark.parametrize("damage", ["missing_contract", "legacy_contract", "wrong_instance", "missing_version", "missing_marker_only"])
def test_server_cohort_prevents_restored_release_downgrade(runtime, damage):
    from core.advisor_revision_store import RevisionStoreError
    if damage == "missing_contract":
        runtime["release"].pop("runtime_contract")
    elif damage == "legacy_contract":
        runtime["release"]["runtime_contract"] = {"schema_version": "1.0"}
    elif damage == "wrong_instance":
        runtime["release"]["instance_id"] = "other"
    elif damage == "missing_marker_only":
        runtime["release"].pop("runtime_document_version")
    else:
        runtime["release"].pop("runtime_document_version")
        runtime["release"].pop("runtime_contract")
    with pytest.raises(RevisionStoreError):
        require(runtime)


def test_actual_route_dispatch_consumes_fixed_only(runtime, monkeypatch):
    from api.routes import app_data_runtime as route
    from core import studio_release_context as rc, studio_runtime_data as data
    w = runtime
    original = data.resolve_dataset
    original_require = rc.require_release_context
    monkeypatch.setattr(route, "_plane", lambda _: w["plane"])
    monkeypatch.setattr(route.app_proof, "read_release", lambda _: w["release"])
    monkeypatch.setattr(route, "viewing_context", lambda _: w["context"])
    monkeypatch.setattr(rc, "require_release_context", lambda *a, **k: original_require(
        *a, **k, store=w["store"], processes=w["ctx"],
        revisions=SimpleNamespace(is_v2_project=lambda _: False)))
    monkeypatch.setattr(data, "resolve_dataset", lambda *a, **k: original(
        *a, **k, store=w["store"], processes=w["ctx"]))
    monkeypatch.setattr(w["store"], "list_snapshots", lambda *a, **k: pytest.fail("최신판 열거 금지"))
    monkeypatch.setattr("core.data_preparation.store.data_preparation_store", w["store"])
    seals = route.app_contract_gate.sealed_triple(w["release"], w["rid"], w["plane"])
    proof = dict(zip(("contract_fingerprint", "materialization_fingerprint", "data_fingerprint"), seals))
    result = route._dispatch({"release_id": w["rid"], **w["context"], **proof}, w["dataset"],
                             p=SimpleNamespace(user_id=org.VIEWER_A))
    assert result.snapshot["snapshot_id"] == w["data"]["INV-01"]["snapshot_id"]
    assert not result.stale
    proof["contract_fingerprint"] = "old-revision"
    with pytest.raises(Exception):
        route._dispatch({"release_id": w["rid"], **w["context"], **proof}, w["dataset"],
                        p=SimpleNamespace(user_id=org.VIEWER_A))
    # 원문/정책은 그대로 두고 실제 provider에 미래 시각을 주어 신선도 연결을 확인한다.
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    original_provider = route.prov.resolve
    monkeypatch.setattr(route.prov, "resolve", lambda **kw: original_provider(
        **{**kw, "now": (datetime.now(timezone.utc) + timedelta(days=31)).isoformat()}))
    proof["contract_fingerprint"] = seals[0]
    with pytest.raises(HTTPException) as exc:
        route._dispatch({"release_id": w["rid"], **w["context"], **proof}, w["dataset"],
                        p=SimpleNamespace(user_id=org.VIEWER_A))
    assert exc.value.status_code == 503


def test_new_candidate_approval_does_not_disable_existing_release(runtime):
    newer = draft(runtime, expected_revision=1, app_class="enterprise")
    approve(runtime, newer)
    assert "RUN" in require(runtime)["permitted_actions"]
    assert resolve(runtime)[1][0]["snapshot_id"] == runtime["data"]["INV-01"]["snapshot_id"]


@pytest.mark.parametrize("payload,ok", [(b"amount\n1\n", True), (b"amount\n999\n", False)])
def test_raw_parser_checks_actual_bytes_even_if_earlier_file_check_passed(tmp_path, monkeypatch, payload, ok):
    """합성 RAW만 사용. 사전 검사 직후 파일이 교체된 경합을 재현한다."""
    from api.routes import app_data_runtime as route
    from core.data_preparation import snapshot_service
    from fastapi import HTTPException
    path = tmp_path / "synthetic.test.invalid.csv"
    path.write_bytes(payload)
    snap = dict(raw_path=str(path), checksum=hashlib.sha256(b"amount\n1\n").hexdigest(),
                snapshot_id="synthetic-test", certified_at="2026-09-13T00:00:00Z")
    result = route.prov.Resolution("FILE_SNAPSHOT", "INV-01", {}, snap, False, snap["certified_at"])
    monkeypatch.setattr(snapshot_service, "verify_raw", lambda *a: True)
    if ok:
        served = route._serve_snapshot(result, limit=10)
        assert served["total"] == 1 and served["records"][0]["payload"] == {"amount": "1"}
    else:
        with pytest.raises(HTTPException) as exc:
            route._serve_snapshot(result, limit=10)
        assert exc.value.status_code == 503
