"""B0-B의 DP 원자성·HTTP 가시성만 검증. 회사별 서명 적격성 검증과 구분한다."""
import concurrent.futures
import threading

import pytest

from core import actual_certification_policy as acp
from core.data_preparation import models as m, snapshot_service as svc
from core.data_preparation.store import DataPreparationStore
from tests.test_actual_certification import (
    ACTOR_EXEC, ACTOR_OWNER, EVIDENCE, _reconciled, _sign, authority, store,
)


@pytest.mark.parametrize("start,end", [("", ""), ("2026-08-01", ""), ("", "2026-08-31"),
                                        ("2026-02-30", "2026-08-31"),
                                        ("2026-09-01", "2026-08-31")])
def test_invalid_period_cannot_leave_any_signature(store, tmp_path, authority, start, end):
    sid = _reconciled(store, tmp_path)
    before = store.get_snapshot(sid)
    with pytest.raises(m.DataPreparationError, match="귀속 기간"):
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, period_from=start, period_to=end)
    assert store.get_snapshot(sid) == before
    assert svc.actual_certifications(store, sid) == []


def test_final_transition_failure_rolls_back_signature_and_period(store, tmp_path, authority, monkeypatch):
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT,
          period_from="2026-08-01", period_to="2026-08-31")
    before = store.get_snapshot(sid)
    before_signatures = svc.actual_certifications(store, sid)
    original = store._advance_snapshot_conn

    def fail_after_state(conn, *args, **kwargs):
        original(conn, *args, **kwargs)
        # 서명과 최종 상태 모두 SQL로 쓴 뒤 실패해야 강한 롤백 시험이다.
        assert conn.execute("SELECT COUNT(*) FROM certification_signatures WHERE snapshot_id=?", (sid,)).fetchone()[0] == 2
        assert conn.execute("SELECT state FROM dataset_snapshots WHERE snapshot_id=?", (sid,)).fetchone()[0] == m.OWNER_CERTIFIED
        raise RuntimeError("TEST_FINAL_WRITE_FAILURE")

    monkeypatch.setattr(store, "_advance_snapshot_conn", fail_after_state)
    with pytest.raises(RuntimeError, match="TEST_FINAL_WRITE_FAILURE"):
        _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_MANAGEMENT,
              period_from="2026-08-01", period_to="2026-08-31")
    assert store.get_snapshot(sid) == before
    assert svc.actual_certifications(store, sid) == before_signatures


@pytest.mark.parametrize("different_period", [False, True])
def test_independent_stores_serialize_signatures(store, tmp_path, authority, different_period):
    sid = _reconciled(store, tmp_path)
    other = DataPreparationStore(store.db_path)
    other.get_snapshot(sid)  # DDL과 실제 동시 서명 경쟁을 분리한다.
    barrier = threading.Barrier(2)

    def sign(selected, kind, actor, changed):
        barrier.wait(timeout=5)
        try:
            return _sign(selected, sid, kind, actor, use_kind=acp.USE_MANAGEMENT,
                         period_from="2026-09-01" if changed else "2026-08-01",
                         period_to="2026-09-30" if changed else "2026-08-31")
        except m.StateConflict as exc:
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(sign, store, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, False),
                   pool.submit(sign, other, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, different_period)]
        results = [future.result(timeout=15) for future in futures]
    errors = [result for result in results if isinstance(result, Exception)]
    row = store.get_snapshot(sid)
    signatures = svc.actual_certifications(store, sid)
    if different_period:
        assert len(errors) == 1 and "귀속 기간" in str(errors[0])
        assert row["state"] == m.RECONCILED and len(signatures) == 1
    else:
        assert errors == []
        assert row["state"] == m.OWNER_CERTIFIED and len(signatures) == 2
        assert sorted(result["certified"] for result in results) == [False, True]


@pytest.mark.parametrize("change", ["actor", "evidence"])
def test_a_different_signature_cannot_overwrite_a_previous_one(store, tmp_path, authority, change):
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT)
    before = svc.actual_certifications(store, sid)
    with pytest.raises(m.StateConflict, match="덮어쓸"):
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_EXEC if change == "actor" else ACTOR_OWNER,
              use_kind=acp.USE_MANAGEMENT,
              reconciliation_evidence="서로 다른 마감본과 대사한 증거입니다" if change == "evidence" else EVIDENCE)
    assert svc.actual_certifications(store, sid) == before


@pytest.mark.parametrize("method", ["get", "post"])
def test_certification_http_hides_out_of_scope_same_as_missing(tmp_path, monkeypatch, enforced_org, method):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as route
    from tests import org_seed
    import config

    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    selected = DataPreparationStore(str(tmp_path / "http-cert.db"))
    monkeypatch.setattr(route, "store", selected)
    context = dict(tenant_id="tenant_default", entity_mode="REAL", scope_node_id=org_seed.NODES[org_seed.DEPT_A])
    selected.upsert_kit_version(kit_id="TEST", version="1", name="인증 HTTP 합성 시험",
                                source_path="test", fingerprint_value="fp", profile={}, mode=m.DATA_KIND_DEMO)
    inst = selected.create_instance(kit_id="TEST", version="1", kit_fingerprint="fp", **context)
    row = selected.create_snapshot(instance_id=inst["instance_id"], binding_id="test", dataset_contract_key="FIN-03", **context)
    app = FastAPI()
    app.include_router(route.router)
    responses = []
    with TestClient(app) as client:
        for sid in (row["snapshot_id"], "missing"):
            kwargs = {"headers": {"X-Factory-User": org_seed.MEMBER_B}}
            if method == "post":
                kwargs["json"] = dict(review_kind="DATA_OWNER", use_kind="OPERATIONAL", reconciliation_evidence=EVIDENCE)
            response = getattr(client, method)(f"/api/v1/data-preparation/snapshots/{sid}/certifications", **kwargs)
            assert response.status_code == 404, response.text
            responses.append(response.json())
    assert responses[0] == responses[1]
    assert svc.actual_certifications(selected, row["snapshot_id"]) == []
