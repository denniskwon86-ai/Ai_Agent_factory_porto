"""B3 고정 릴리스 준비도 시험. 실행은 main의 격리 runner 전용이다.

runtime fixture는 실제 임시 DP/PDP/승인/물질화와 합성 인증 메타데이터를 쓴다.
단위 투영 시험은 출처 검증을 명시적으로 대역 처리하므로 내부 데이터 앱의
종단 권한 검증 증거로 세지 않는다.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import app_runtime_contract as arc
from core import studio_release_readiness as sr
from core.data_preparation import readiness as rd
from core.enterprise_context.process_schema import ProcessError
from tests import kit_samples, org_seed as org
from tests.test_b3_runtime_data import (  # noqa: F401
    runtime, kit, installation, workspace, enforced_org, sample_certified, database, hold,
)
from tests.test_b2_installation import _state


def _readiness(w, **changes):
    args = dict(actor=org.MANAGER_A, context=w["context"], store=w["store"],
                processes=w["ctx"], revisions=SimpleNamespace(is_v2_project=lambda _: False))
    return sr.release_readiness(w["release"], **{**args, **changes})


def _used(w):
    keys = {d["enterprise_contract_key"] for d in w["contract"]["datasets"]
            if d["source_intent"] == arc.ENTERPRISE_READ}
    return {(r["instance_id"], r["contract_key"], r["snapshot_id"])
            for r in w["contract"]["process_context"]["verified_binding_refs"]
            if r["contract_key"] in keys}


def _no_discovery(w, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("2.0 readiness must not discover a registry/latest/current substitute")
    for name in ("list_snapshots", "active_binding", "get_kit_version"):
        monkeypatch.setattr(w["store"], name, forbidden)
    monkeypatch.setattr("core.data_preparation.kit_registry.resolve", forbidden)


def test_actual_release_has_only_used_fixed_rows_and_no_writes(runtime, monkeypatch):
    w = runtime
    before, sealed = _state(w), copy.deepcopy(w["release"])
    _no_discovery(w, monkeypatch)
    result = _readiness(w)
    assert result["runtime_document_version"] == "2.0"
    assert result["status"] == rd.INSTANCE_READY
    actual = {(r["instance_id"], r["dataset_contract_key"], r["snapshot_id"])
              for r in result["datasets"]}
    assert actual == _used(w)
    assert result["coverage"] == dict(required=len(actual), ready=len(actual), stale=0, blocked=0)
    assert result["fixed_snapshot_refs"] == sorted(f"{i}:{k}={s}" for i, k, s in actual)
    assert not {"MDM-05", "MDM-06"} & {r["dataset_contract_key"] for r in result["datasets"]}
    assert _state(w) == before and w["release"] == sealed


def test_actual_readiness_tokens_match_promotion_and_host_fingerprints(runtime, monkeypatch):
    from core import app_contract_gate as gate, release_promotion as rp
    from core.baseline_build import fingerprint_for
    from core.studio_runtime_data import data_fingerprint
    w = runtime
    monkeypatch.setattr("core.data_preparation.store.data_preparation_store", w["store"])
    result = _readiness(w)
    rows = [{"key": r["dataset_contract_key"], "inst": r["instance_id"]}
            for r in result["datasets"]]
    expected = gate.data_fingerprint(w["rid"], w["plane"], contract=w["contract"])
    assert expected not in (gate.NO_DATA, gate.UNREADABLE)
    assert rp.data_fingerprint(result) == expected
    assert fingerprint_for(result["fixed_snapshot_refs"]) == expected
    assert data_fingerprint(w["contract"], rows, w["store"]) == expected


def test_later_certification_cannot_replace_pinned_readiness(runtime, monkeypatch):
    w = runtime
    before = _readiness(w)
    newer = sample_certified(w, "INV-01", existing_binding=w["data"]["INV-01"]["binding"],
                             offset=kit_samples.SAMPLE_ROWS, extra={"new_amount": 1})
    _no_discovery(w, monkeypatch)
    after = _readiness(w)
    assert before == after
    assert newer["snapshot_id"] not in {r["snapshot_id"] for r in after["datasets"]}


def test_projection_unit_duplicate_runtime_datasets_have_one_fixed_row(runtime, monkeypatch):
    """실제 DP로 중복 투영을 검사하되 변경 계약의 승인 게이트만 명시적 대역이다."""
    from core import host_contract_compiler as compiler, studio_release_context as rc
    from core import release_promotion as rp
    w = runtime
    expected = _readiness(w)
    datasets = copy.deepcopy(w["contract"]["datasets"])
    datasets.append({**copy.deepcopy(datasets[0]), "name": "second_view_same_fixed_source"})
    compiled = compiler.compile_contract(
        {"app_class": w["contract"]["app_class"], "capability_intents": [], "datasets": datasets},
        project_id=w["contract"]["project_id"], task_id=w["contract"]["task_id"],
        document_version="2.0", process_context=w["contract"]["process_context"],
    )
    assert compiled.ok, compiled.errors
    contract = compiled.contract
    contract.update(status="APPROVED", approval=copy.deepcopy(w["contract"]["approval"]))
    assert arc.validate(contract) == []
    release = {**w["release"], "runtime_contract": contract}
    def approved_projection(*_args, **kwargs):
        assert kwargs["for_action"] == "RELEASE"
        return w["ctx"].revalidate(fixed_context=contract["process_context"], actor=kwargs["actor"],
                                   current_context=kwargs["context"], for_action="RELEASE")
    monkeypatch.setattr(rc, "require_release_context", approved_projection)
    actual = _readiness({**w, "release": release})
    pairs = [(r["instance_id"], r["dataset_contract_key"]) for r in actual["datasets"]]
    assert len(pairs) == len(set(pairs)) == expected["coverage"]["required"]
    assert actual["fixed_snapshot_refs"] == expected["fixed_snapshot_refs"]
    assert rp.data_fingerprint(actual) == rp.data_fingerprint(expected)


@pytest.mark.parametrize("days,status", [(29, rd.INSTANCE_READY), (31, rd.INSTANCE_PARTIAL)])
def test_freshness_uses_certified_time_of_fixed_snapshot(runtime, monkeypatch, days, status):
    w = runtime
    timestamps = [datetime.fromisoformat(w["store"].get_snapshot(s)["certified_at"].replace("Z", "+00:00"))
                  for _, _, s in _used(w)]
    when = (max(timestamps) + timedelta(days=days)).isoformat()
    monkeypatch.setattr(sr, "_now", lambda: when)
    result = _readiness(w)
    assert result["status"] == status
    assert {(r["instance_id"], r["dataset_contract_key"], r["snapshot_id"])
            for r in result["datasets"]} == _used(w)
    assert all(r["state"] == (rd.READY if days == 29 else rd.STALE) for r in result["datasets"])


@pytest.mark.parametrize("actor", [org.MEMBER_A, org.VIEWER_A])
def test_run_or_generate_permission_does_not_authorize_release(runtime, actor):
    with pytest.raises(ProcessError) as exc:
        _readiness(runtime, actor=actor)
    assert exc.value.status_code == 403


def test_wrong_selected_context_never_yields_readiness(runtime):
    context = {**runtime["context"], "scope_node_id": org.NODES[org.DEPT_B]}
    with pytest.raises(ProcessError):
        _readiness(runtime, context=context)


@pytest.mark.parametrize("damage", ["contract_missing", "legacy", "unknown", "context_missing"])
def test_known_cohort_missing_or_downgraded_contract_fails_closed(runtime, damage):
    from core.advisor_revision_store import RevisionStoreError
    w = {**runtime, "release": copy.deepcopy(runtime["release"])}
    if damage == "contract_missing":
        w["release"].pop("runtime_contract")
        w["release"].pop("runtime_document_version")
    elif damage == "context_missing":
        w["release"]["runtime_contract"].pop("process_context")
    else:
        w["release"]["runtime_contract"]["schema_version"] = "1.0" if damage == "legacy" else "9.0"
    with pytest.raises((ProcessError, RevisionStoreError)):
        _readiness(w)


def _after_authorization(monkeypatch, change):
    from core import studio_release_context as rc
    original = rc.require_release_context
    def checked_then_changed(*args, **kwargs):
        assert kwargs["for_action"] == "RELEASE"
        result = original(*args, **kwargs)
        change()
        return result
    monkeypatch.setattr(rc, "require_release_context", checked_then_changed)


def test_hold_after_initial_release_check_is_rechecked_in_dp_transaction(runtime, monkeypatch):
    _after_authorization(monkeypatch, lambda: hold(runtime))
    with pytest.raises(ProcessError) as exc:
        _readiness(runtime)
    assert exc.value.reason_code == "DATA_USAGE_HOLD"
    assert exc.value.status_code == 409


def test_snapshot_damage_after_initial_release_check_cannot_become_ready(runtime, monkeypatch):
    w = runtime
    def corrupt():
        with database(w, "dp") as conn:
            conn.execute("UPDATE dataset_snapshots SET checksum=? WHERE snapshot_id=?",
                         ("0" * 64, w["data"]["INV-01"]["snapshot_id"]))
    _after_authorization(monkeypatch, corrupt)
    with pytest.raises(ProcessError):
        _readiness(w)


def test_final_artifact_instance_reference_snapshot_share_one_read_transaction(runtime, monkeypatch):
    from core.data_preparation import process_pack_artifacts as pa
    from core import studio_runtime_data as data
    w, calls, statements = runtime, [], []
    phase = {"final": False}
    _after_authorization(monkeypatch, lambda: phase.update(final=True))
    transaction = w["store"].transaction
    @contextmanager
    def traced_transaction():
        with transaction() as conn:
            if phase["final"]:
                conn.set_trace_callback(statements.append)
            yield conn
    monkeypatch.setattr(w["store"], "transaction", traced_transaction)
    bundle, instance = pa.get_bundle, w["ctx"]._instance
    reference, snapshot = w["ctx"]._reference, data.fixed_snapshot_conn
    def note(kind, conn):
        if phase["final"]:
            assert conn.in_transaction
            calls.append((kind, conn))
    def read_bundle(view, digest):
        if phase["final"]:
            note("bundle", view.conn)
        return bundle(view, digest)
    def read_instance(conn, *args):
        note("instance", conn)
        return instance(conn, *args)
    def read_reference(conn, **kwargs):
        note("reference", conn)
        assert kwargs.get("fixed") is not None
        return reference(conn, **kwargs)
    def read_snapshot(conn, *args):
        note("snapshot", conn)
        return snapshot(conn, *args)
    monkeypatch.setattr(pa, "get_bundle", read_bundle)
    monkeypatch.setattr(w["ctx"], "_instance", read_instance)
    monkeypatch.setattr(w["ctx"], "_reference", read_reference)
    monkeypatch.setattr(data, "fixed_snapshot_conn", read_snapshot)
    _no_discovery(w, monkeypatch)
    result = _readiness(w)
    assert result["status"] == rd.INSTANCE_READY
    assert {kind for kind, _ in calls} == {"bundle", "instance", "reference", "snapshot"}
    assert len({id(conn) for _, conn in calls}) == 1
    assert statements and statements[0].strip().upper() == "BEGIN"
    assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"))
                   for sql in statements)


def _native_unit(monkeypatch, *, authorize=True):
    """출처 검증 대역을 명시한 내부 데이터 전용 단위 투영이다."""
    from core import studio_release_context as rc
    from tests.test_b3_materializer_v2 import _contract, _native
    contract = _contract(datasets=[_native()])
    release = {"release_id": "native-unit.invalid", "runtime_document_version": "2.0", "runtime_contract": contract}
    calls = []
    def require(sealed, **kwargs):
        calls.append(kwargs)
        if not authorize:
            raise ProcessError("STUDIO_ACTION_FORBIDDEN", "unit denial", 403)
        return copy.deepcopy(sealed["runtime_contract"]["process_context"])
    monkeypatch.setattr(rc, "require_release_context", require)
    class NoDP:
        def transaction(self):
            pytest.fail("native-only projection must not read DP after its provenance gate")
    return release, NoDP(), calls


def test_native_unit_explicit_ready_empty_rows_still_requires_release_context(monkeypatch):
    from core import app_contract_gate as gate, release_promotion as rp
    release, store, calls = _native_unit(monkeypatch)
    svc, rev = object(), object()
    out = sr.release_readiness(release, actor="unit", context={"scope_node_id": "unit"},
                               store=store, processes=svc, revisions=rev)
    assert out["runtime_document_version"] == "2.0" and out["status"] == rd.INSTANCE_READY
    assert out["datasets"] == [] and out["fixed_snapshot_refs"] == []
    assert out["coverage"] == dict(required=0, ready=0, stale=0, blocked=0)
    assert calls[0]["for_action"] == "RELEASE" and calls[0]["release_id"] == release["release_id"]
    assert calls[0]["store"] is store and calls[0]["processes"] is svc and calls[0]["revisions"] is rev
    assert rp.data_fingerprint(out) == gate.NO_DATA


def test_native_unit_is_not_a_permission_bypass(monkeypatch):
    release, store, _ = _native_unit(monkeypatch, authorize=False)
    with pytest.raises(ProcessError) as exc:
        sr.release_readiness(release, actor="unit", context={}, store=store, processes=object())
    assert exc.value.status_code == 403


@pytest.mark.parametrize("field,value", [("status", "DRAFT"), ("schema_version", "1.0"), ("schema_version", "9.0")])
def test_native_unit_draft_or_non_v2_is_not_no_data(monkeypatch, field, value):
    release, store, _ = _native_unit(monkeypatch)
    release["runtime_contract"][field] = value
    with pytest.raises(ProcessError):
        sr.release_readiness(release, actor="unit", context={}, store=store, processes=object())


def test_native_unit_missing_enterprise_ref_is_not_no_data(monkeypatch):
    from tests.test_b3_materializer_v2 import _contract, _ds
    release, store, _ = _native_unit(monkeypatch)
    release["runtime_contract"] = _contract(datasets=[_ds()])
    release["runtime_contract"]["process_context"]["verified_binding_refs"] = []
    with pytest.raises(ProcessError):
        sr.release_readiness(release, actor="unit", context={}, store=store, processes=object())


def _group(key, sid, *, stale=False):
    return rd.evaluate_instance(contract_keys=[key],
        bindings={key: {"binding_id": "binding-" + sid, "state": "ACTIVE", "config": {}}},
        snapshots={key: [{"snapshot_id": sid, "state": "OWNER_CERTIFIED", "data_kind": "REAL",
                          "certified_at": "2026-01-01T00:00:00+00:00" if stale else "2026-09-13T00:00:00+00:00"}]},
        now="2026-09-13T00:00:00+00:00", max_age_days=30, outputs=[])


def test_unit_multi_instance_aggregation_does_not_drop_same_named_keys():
    groups = [("instance-b", _group("same-key", "snapshot-b", stale=True)),
              ("instance-a", _group("same-key", "snapshot-a"))]
    out = sr._combine(groups)
    assert out["status"] == rd.INSTANCE_PARTIAL
    assert out["coverage"] == dict(required=2, ready=1, stale=1, blocked=0)
    assert out["fixed_snapshot_refs"] == ["instance-a:same-key=snapshot-a", "instance-b:same-key=snapshot-b"]
    assert out == sr._combine(list(reversed(groups)))
    assert len(out["datasets"]) == 2


@pytest.mark.parametrize("value", [True, "30", -1, float("inf"), float("nan")])
def test_unit_invalid_fixed_freshness_policy_fails_closed(value):
    with pytest.raises(ProcessError) as exc:
        sr._max_age({"max_age_days": value})
    assert exc.value.status_code == 503


def test_unit_fixed_freshness_default_is_existing_kit_policy():
    assert sr._max_age({}) == 30.0
    assert sr._max_age({"max_age_days": 7}) == 7.0
    assert sr._max_age({"max_age_days": None}) is None
