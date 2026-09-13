"""실제 권한 검사를 유지하는 경합·HTTP 부정 시험."""
import concurrent.futures
import threading

import pytest

from core.data_preparation import certification_authority as ca, certification_subject as cs, models as m, snapshot_service as svc
from core.data_preparation.store import DataPreparationStore
from tests import org_seed as org
from tests.test_b0_certification_subject import company, policy, request, sign, EVIDENCE


@pytest.mark.parametrize("difference", ["none", "period", "use"])
def test_real_authority_independent_connections_cannot_mix_subjects(company, difference):
    policy(company)
    owner = request(company, use="OPERATIONAL" if difference == "use" else "MANAGEMENT")
    changes = dict(period_from="2026-09-01", period_to="2026-09-30") if difference == "period" else {}
    executive = request(company, org.EXEC, "EXECUTIVE", **changes)
    second_store = DataPreparationStore(company["store"].db_path)
    second_store._ready()
    barrier = threading.Barrier(2)

    def run(store, req):
        barrier.wait(timeout=5)
        try:
            return svc.sign_actual_certification(store, company["sid"], **req)
        except (m.StateConflict, ca.CertificationError) as exc:
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(run, company["store"], owner), pool.submit(run, second_store, executive)]
        results = [task.result(timeout=20) for task in tasks]
    errors = [r for r in results if isinstance(r, Exception)]
    signatures = svc.actual_certifications(company["store"], company["sid"])
    if difference == "none":
        assert not errors and len(signatures) == 2
        assert sum(r["certified"] for r in results) == 1
    else:
        assert len(errors) == 1 and len(signatures) == 1
        with company["store"].transaction() as conn:
            assert conn.execute("SELECT COUNT(*) FROM certification_subjects").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM certification_requests").fetchone()[0] == 1


def test_real_authority_final_write_failure_rolls_back_request_signature_and_state(company, monkeypatch):
    policy(company)
    sign(company, request(company))
    executive = request(company, org.EXEC, "EXECUTIVE")
    before = company["store"].get_snapshot(company["sid"])
    original = company["store"]._advance_snapshot_conn

    def fail(conn, *args, **kwargs):
        out = original(conn, *args, **kwargs)
        assert out["state"] == m.OWNER_CERTIFIED
        raise RuntimeError("test-only-final-failure")

    monkeypatch.setattr(company["store"], "_advance_snapshot_conn", fail)
    with pytest.raises(RuntimeError, match="test-only-final-failure"):
        sign(company, executive)
    assert company["store"].get_snapshot(company["sid"]) == before
    with company["store"].transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM certification_signatures").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM certification_requests").fetchone()[0] == 1


def test_completed_retry_requires_current_read_access(company):
    from core.org_directory import org_directory
    policy(company)
    req = request(company, use="OPERATIONAL")
    sign(company, req)
    org_directory.delete_user(org.MANAGER_A, actor="test")
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, req)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("method", ["get", "post", "preview"])
@pytest.mark.parametrize("boundary", ["tenant", "mode", "scope", "root"])
def test_http_cross_context_same_404_as_absent(company, monkeypatch, method, boundary):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as route
    from core.enterprise_context.repository import ecm_repository
    from core.enterprise_context.models import EnterpriseEntity, OrganizationNode, STATUS_ACTIVE
    policy(company)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(route, "store", company["store"])
    # 문맥 결정을 대역으로 바꾸지 않고 실제 다른 루트 선택 또는 대상 문맥을 쓴다.
    selected = company["context"]["scope_node_id"]
    actor = org.ADMIN
    if boundary == "scope":
        selected, actor = org.NODES[org.DEPT_B], org.MEMBER_B
    elif boundary == "mode":
        selected = org.NODES[org.VIRTUAL_CODE_B]
    elif boundary == "root":
        ecm_repository.upsert_entity(EnterpriseEntity(entity_id="other-real-entity", tenant_id="tenant_default", entity_mode="REAL", legal_name="합성 타 법인", name_ko="합성 타 법인", status=STATUS_ACTIVE))
        ecm_repository.upsert_node(OrganizationNode(node_id="other-real-root", tenant_id="tenant_default", entity_id="other-real-entity", node_type="business_division", code="other-real", name_ko="합성 다른 루트", status=STATUS_ACTIVE))
        selected = "other-real-root"
    else:
        with company["store"].transaction() as conn:
            conn.execute("UPDATE dataset_snapshots SET tenant_id='other-tenant' WHERE snapshot_id=?", (company["sid"],))
            conn.execute("UPDATE kit_instances SET tenant_id='other-tenant'")
    app = FastAPI()
    app.include_router(route.router)
    headers = {"X-Factory-User": actor, "X-Enterprise-Scope": selected}
    results = []
    with TestClient(app) as client:
        for sid in (company["sid"], "absent"):
            base = f"/api/v1/data-preparation/snapshots/{sid}"
            if method == "post":
                response = client.post(base + "/certifications", headers=headers, json={"review_kind": "DATA_OWNER", "use_kind": "OPERATIONAL", "reconciliation_evidence": EVIDENCE})
            elif method == "preview":
                response = client.get(base + "/certification-subject", headers=headers, params={"use_kind": "OPERATIONAL", "period_from": "2026-08-01", "period_to": "2026-08-31"})
            else:
                response = client.get(base + "/certifications", headers=headers)
            assert response.status_code == 404, response.text
            results.append(response.json())
    assert results[0] == results[1]


def test_http_wrong_signer_403_and_mapping_absent_409(company, monkeypatch):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as route
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(route, "store", company["store"])
    app = FastAPI()
    app.include_router(route.router)
    base = f"/api/v1/data-preparation/snapshots/{company['sid']}"
    headers = {"X-Factory-User": org.ADMIN, "X-Enterprise-Scope": company["context"]["scope_node_id"]}
    params = dict(use_kind="OPERATIONAL", period_from="2026-08-01", period_to="2026-08-31")
    with TestClient(app) as client:
        absent = client.get(base + "/certification-subject", headers=headers, params=params)
        assert absent.status_code == 409 and absent.json()["detail"]["reason_code"] == "ROLE_MAPPING_REQUIRED"
        policy(company)
        preview = client.get(base + "/certification-subject", headers=headers, params=params).json()["data"]
        denied = client.post(base + "/certifications", headers=headers, json={**params,
                            "review_kind": "DATA_OWNER", "reconciliation_evidence": EVIDENCE,
                            "subject_id": preview["subject_id"], "expected_subject_digest": preview["digest"], "client_request_id": "wrong-signer"})
        assert denied.status_code == 403 and denied.json()["detail"]["reason_code"] == "SIGNER_INELIGIBLE"
