"""서명 읽기 일관성·멱등 경합·정책 무결성의 추가 회귀."""
import copy
import concurrent.futures
import sqlite3
import threading

import pytest

from core.data_preparation import certification_authority as ca, certification_subject as cs, models as m
from core.data_preparation.store import DataPreparationStore
from core.org_directory import org_directory
from tests import org_seed as org
from tests.test_b0_certification_subject import company, policy, request, sign, delegation


def test_same_request_race_returns_one_event_and_same_result(company):
    policy(company)
    req = request(company, use="OPERATIONAL")
    other = {**company, "store": DataPreparationStore(company["store"].db_path)}
    other["store"]._ready()
    barrier = threading.Barrier(2)

    def run(c):
        barrier.wait(timeout=5)
        return sign(c, req)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(run, c) for c in (company, other)]
        results = [task.result(timeout=20) for task in tasks]
    assert results[0] == results[1]
    with company["store"].transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM certification_signatures").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM certification_requests").fetchone()[0] == 1


def test_get_reads_snapshot_subject_and_signatures_at_one_sqlite_instant(company, monkeypatch):
    policy(company)
    first = sign(company, request(company))
    original = cs.visible_snapshot

    def race(conn, *args, **kwargs):
        row = original(conn, *args, **kwargs)
        other = sqlite3.connect(company["store"].db_path)
        try:
            with other:
                other.execute("UPDATE dataset_snapshots SET state=? WHERE snapshot_id=?", (m.REVOKED, company["sid"]))
                # 격리 시험 손상 주입: 주체 head가 같은 읽기 중 사라져도 혼합하지 않는다.
                other.execute("DELETE FROM certification_subject_heads WHERE snapshot_id=?", (company["sid"],))
        finally:
            other.close()
        return row

    monkeypatch.setattr(cs, "visible_snapshot", race)
    result = cs.read(company["store"], company["sid"], actor=org.MANAGER_A, context=company["context"])
    assert result["state"] == m.RECONCILED
    assert result["subject"]["subject_id"] == first["subject_id"]
    assert len(result["signatures"]) == 1
    assert result["missing"] == ["EXECUTIVE"]
    assert company["store"].get_snapshot(company["sid"])["state"] == m.REVOKED


def test_invalid_first_delegation_does_not_hide_valid_second(company):
    another = "second_owner@test.invalid"
    org_directory.upsert_user(another, "합성 다른 소유자", primary_dept_id=org.DEPT_A, actor="test")
    org_directory.set_user_roles(another, {org.DEPT_A: "manager"}, actor="test")
    doc = copy.deepcopy(company["document"])
    doc["delegations"] = [delegation(), delegation(delegator=another)]
    policy(company, doc)
    org_directory.delete_user(org.MANAGER_A, actor="test")
    assert sign(company, request(company, org.MEMBER_A, use="OPERATIONAL"))["certified"] is True


def test_policy_rows_subjects_signatures_and_request_results_are_immutable(company):
    policy(company)
    sign(company, request(company, use="OPERATIONAL"))
    for table in ("certification_policies", "certification_subjects", "certification_signatures", "certification_requests"):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with company["store"].transaction() as conn:
                conn.execute(f"DELETE FROM {table}")


def test_wrong_policy_head_or_ledger_lookup_failure_is_503(company, monkeypatch):
    policy(company)
    def unavailable(*args, **kwargs):
        raise RuntimeError("test-only-ledger-offline")
    monkeypatch.setattr(company["ledger"], "get_event_strict", unavailable)
    with company["store"].transaction() as conn:
        with pytest.raises(ca.CertificationError) as exc:
            ca.resolve_policy(conn, tenant_id="tenant_default", entity_mode="REAL", context_root_id=company["root"])
    assert exc.value.status_code == 503


def test_first_signature_write_failure_leaves_no_subject_or_request(company, monkeypatch):
    policy(company)
    req = request(company, use="OPERATIONAL")
    before = company["store"].get_snapshot(company["sid"])
    original = company["store"]._advance_snapshot_conn

    def fail(conn, *args, **kwargs):
        original(conn, *args, **kwargs)
        raise RuntimeError("test-only-failure")

    monkeypatch.setattr(company["store"], "_advance_snapshot_conn", fail)
    with pytest.raises(RuntimeError):
        sign(company, req)
    assert company["store"].get_snapshot(company["sid"]) == before
    with company["store"].transaction() as conn:
        for table in ("certification_subjects", "certification_subject_heads", "certification_signatures", "certification_requests"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
