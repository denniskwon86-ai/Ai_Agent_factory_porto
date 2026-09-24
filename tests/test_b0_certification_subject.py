"""실제 격리 조직·PDP·승인 원장으로 B0-B 경계를 검증한다. 운영 정책은 만들지 않는다."""
import copy
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.data_preparation import certification_authority as ca, certification_subject as cs
from core.data_preparation import models as m, ownership_binding as ob, snapshot_service as svc
from core.data_preparation.store import DataPreparationStore
from core.org_directory import org_directory
from tests import kit_samples, org_seed as org

EVIDENCE = "합성 시험 ERP 마감본 2026/08 총계 대사 일치"


@pytest.fixture
def company(tmp_path, monkeypatch, enforced_org):
    from core.decision_ledger import decision_ledger
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"))
    monkeypatch.setattr(decision_ledger, "_prepared_for", None)
    store = DataPreparationStore(str(tmp_path / "subjects.db"))
    context = dict(tenant_id="tenant_default", entity_mode="REAL", scope_node_id=org.NODES[org.DEPT_A])
    root = org.NODES[org.DEPT_ROOT]
    #: ★ [2026-09-25] 인증은 설치가 고정한 데이터셋 계약과 봉인 원문을 대조한다. 그래서 등록부
    #:   키트·`a` 한 칸 RAW 대신 계약을 싣는 팩(1.2.0)을 실제로 고정하고 FIN-03 정본 샘플을 올린다.
    inst = kit_samples.pinned_instance(store, context=context, context_root_id=root, actor=org.ADMIN,
                                       operation_id="b0-company-install")
    source = store.create_binding(instance_id=inst["instance_id"], dataset_contract_key="FIN-03",
                                   provider=m.PROVIDER_FILE_SNAPSHOT, config={}, **context)
    snap, parsed = kit_samples.ingest_sample(store, source, "FIN-03", context, created_by=org.MANAGER_A)
    sid = snap["snapshot_id"]
    rows = parsed.rows
    svc.profile(store, sid, rows, parsed.columns)
    svc.standardize(store, sid, rows)
    svc.reconcile(store, sid, rows, {"row_count": len(rows)})
    owner_args = dict(**context, dataset_contract_key="FIN-03", owner_dept_id=org.DEPT_A,
                      evidence_ref="test-only-company-owner-approval")
    approved = ob.approve(**owner_args, actor_id=org.ADMIN)
    with store.transaction() as conn:
        owner = ob.declare(conn, **owner_args, approved_by=org.ADMIN,
                           approval_event_id=approved["approval_event_id"], effective_from=approved["effective_from"])
    document = {"required_reviews": {"OPERATIONAL": ["DATA_OWNER"], "MANAGEMENT": ["DATA_OWNER", "EXECUTIVE"]},
                "grants": {"DATA_OWNER": [{"dept_id": org.DEPT_A, "role": "manager", "scope_node_id": org.NODES[org.DEPT_A]}],
                           "EXECUTIVE": [{"dept_id": org.DEPT_ROOT, "role": "viewer", "scope_node_id": root}]},
                "delegations": [], "allow_same_actor": False, "min_evidence_length": 10}
    return {"store": store, "sid": sid, "context": context, "root": root, "document": document,
            "ledger": decision_ledger, "owner": owner, "owner_args": owner_args}


def policy(c, document=None, expected=""):
    return ca.approve_policy(c["store"], tenant_id=c["context"]["tenant_id"], entity_mode="REAL", context_root_id=c["root"],
                             actor=org.ADMIN, evidence_ref="test-only-company-signing-policy-approval",
                             document=document or c["document"], expected_policy_id=expected)


def request(c, actor=org.MANAGER_A, kind="DATA_OWNER", use="MANAGEMENT", **changes):
    args = dict(actor=actor, context=c["context"], use_kind=use, period_from="2026-08-01", period_to="2026-08-31")
    args.update(changes)
    subject = cs.preview(c["store"], c["sid"], **args)
    return {**args, "review_kind": kind, "reconciliation_evidence": EVIDENCE, "subject_id": subject["subject_id"],
            "expected_subject_digest": subject["digest"], "client_request_id": str(uuid.uuid4())}


def sign(c, req):
    return svc.sign_actual_certification(c["store"], c["sid"], **req)


def test_mapping_is_required_even_for_admin(company):
    with pytest.raises(ca.CertificationError) as exc:
        request(company, actor=org.ADMIN)
    assert exc.value.reason_code == "ROLE_MAPPING_REQUIRED"
    assert svc.actual_certifications(company["store"], company["sid"]) == []


@pytest.mark.parametrize("actor,kind", [(org.ADMIN, "DATA_OWNER"), (org.DATA_ADMIN, "EXECUTIVE"),
                                        (org.MANAGER_A, "EXECUTIVE"), (org.EXEC, "DATA_OWNER"),
                                        (org.MEMBER_A, "DATA_OWNER")])
def test_general_or_wrong_kind_authority_does_not_sign(company, actor, kind):
    policy(company)
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, request(company, actor, kind))
    assert exc.value.status_code == 403 and exc.value.reason_code == "SIGNER_INELIGIBLE"


def test_real_roles_parallel_completion_and_lost_response_retry(company):
    policy(company)
    owner = request(company)
    executive = request(company, org.EXEC, "EXECUTIVE")
    first = sign(company, executive)
    assert first["certified"] is False
    complete = sign(company, owner)
    assert complete["certified"] is True
    assert sign(company, owner) == complete
    assert sign(company, executive) == first  # 당시 결과를 그대로 돌려준다.
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, {**owner, "reconciliation_evidence": EVIDENCE + "다른 본문"})
    assert exc.value.reason_code == "IDEMPOTENCY_CONFLICT"
    assert len(svc.actual_certifications(company["store"], company["sid"])) == 2
    with pytest.raises(m.StateConflict):
        cs.preview(company["store"], company["sid"], actor=org.MANAGER_A, context=company["context"],
                   use_kind="MANAGEMENT", period_from="2026-08-01", period_to="2026-08-31", new_revision=True)


def test_owner_role_revoked_after_first_signature_blocks_completion(company):
    policy(company)
    sign(company, request(company))
    executive = request(company, org.EXEC, "EXECUTIVE")
    org_directory.set_user_roles(org.MANAGER_A, {org.DEPT_A: "member"}, actor="test")
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, executive)
    assert exc.value.reason_code == "SIGNER_INELIGIBLE"
    assert company["store"].get_snapshot(company["sid"])["state"] == m.RECONCILED
    assert len(svc.actual_certifications(company["store"], company["sid"])) == 1


@pytest.mark.parametrize("allow_same", [False, True])
def test_same_actor_requires_versioned_explicit_exception_and_both_roles(company, allow_same):
    doc = copy.deepcopy(company["document"])
    doc["allow_same_actor"] = allow_same
    org_directory.set_user_roles(org.MANAGER_A, {org.DEPT_A: "manager", org.DEPT_ROOT: "viewer"}, actor="test")
    policy(company, doc)
    sign(company, request(company))
    executive = request(company, org.MANAGER_A, "EXECUTIVE")
    if allow_same:
        assert sign(company, executive)["certified"] is True
    else:
        with pytest.raises(ca.CertificationError) as exc:
            sign(company, executive)
        assert exc.value.reason_code == "DISTINCT_SIGNER_REQUIRED"


def test_policy_change_requires_explicit_new_revision_preserving_old_signatures(company):
    old = policy(company)
    owner = request(company)
    first = sign(company, owner)
    executive = request(company, org.EXEC, "EXECUTIVE")
    doc = copy.deepcopy(company["document"])
    doc["min_evidence_length"] = 11
    policy(company, doc, old["policy_id"])
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, executive)
    assert exc.value.reason_code == "REVIEW_STALE"
    args = dict(actor=org.MANAGER_A, context=company["context"], use_kind="MANAGEMENT", period_from="2026-08-01", period_to="2026-08-31")
    preview = cs.preview(company["store"], company["sid"], **args, new_revision=True)
    newer = cs.restart(company["store"], company["sid"], **args, expected_subject_digest=preview["digest"], previous_subject_id=first["subject_id"])
    assert newer["payload"]["revision"] == 2
    assert svc.actual_certifications(company["store"], company["sid"]) == []
    assert sign(company, owner) == first  # 새 판으로 옛 요청을 다시 적용하지 않는다.
    assert sign(company, request(company, org.EXEC, "EXECUTIVE"))["certified"] is False
    assert sign(company, request(company))["certified"] is True
    with company["store"].transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM certification_signatures").fetchone()[0] == 3


def test_changed_ownership_is_stale(company):
    policy(company)
    sign(company, request(company))
    executive = request(company, org.EXEC, "EXECUTIVE")
    with company["store"].transaction() as conn:
        ob.revoke(conn, company["owner"]["binding_id"], org.ADMIN, "test-only-reassignment")
    approved = ob.approve(**company["owner_args"], actor_id=org.ADMIN)
    with company["store"].transaction() as conn:
        ob.declare(conn, **company["owner_args"], approved_by=org.ADMIN,
                   approval_event_id=approved["approval_event_id"], effective_from=approved["effective_from"])
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, executive)
    assert exc.value.reason_code == "REVIEW_STALE"


@pytest.mark.parametrize("change,reason", [("sealed_original", "SUBJECT_CONFLICT"),
                                           ("checksum_only", "RAW_CHECKSUM_MISMATCH")])
def test_expected_digest_rejects_changed_raw_checksum(company, change, reason):
    """확인한 뒤 원문이 바뀌면 서명하지 않는다.

    [2026-09-25] 인증이 봉인 원문을 계약과 대조하게 되면서 두 경우가 갈린다.
    - 원문과 기록이 **함께** 바뀜(정본 형식은 지킴) → 관문은 통과, 서명 대상 지문이 달라 `SUBJECT_CONFLICT`.
    - 기록만 바뀜 → 원문과 어긋나 그보다 먼저 `RAW_CHECKSUM_MISMATCH`."""
    import hashlib
    from pathlib import Path
    policy(company)
    req = request(company)
    checksum = "changed"
    if change == "sealed_original":
        columns, table = kit_samples.sample_table("FIN-03", company["context"], offset=kit_samples.SAMPLE_ROWS)
        payload = kit_samples.to_csv(columns, table)
        Path(company["store"].get_snapshot(company["sid"])["raw_path"]).write_bytes(payload)
        checksum = hashlib.sha256(payload).hexdigest()
    with company["store"].transaction() as conn:
        conn.execute("UPDATE dataset_snapshots SET checksum=? WHERE snapshot_id=?", (checksum, company["sid"]))
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, req)
    assert exc.value.reason_code == reason
    assert svc.actual_certifications(company["store"], company["sid"]) == []


def test_plain_state_transition_cannot_bypass_signatures(company):
    with pytest.raises(ca.CertificationError) as exc:
        company["store"].advance_snapshot(company["sid"], m.OWNER_CERTIFIED, certified_by=org.ADMIN)
    assert exc.value.reason_code == "CERTIFICATION_SIGNATURES_REQUIRED"


def delegation(actor=org.MEMBER_A, delegator=org.MANAGER_A, expired=False):
    at = datetime.now(timezone.utc)
    return {"actor": actor, "delegator": delegator, "review_kind": "DATA_OWNER", "scope_node_id": org.NODES[org.DEPT_A],
            "valid_from": (at - timedelta(days=2)).isoformat(),
            "valid_to": (at + timedelta(days=-1 if expired else 1)).isoformat(), "evidence_ref": "test-only-approved-delegation"}


@pytest.mark.parametrize("expired", [False, True])
def test_delegation_is_time_bounded(company, expired):
    doc = copy.deepcopy(company["document"])
    doc["delegations"] = [delegation(expired=expired)]
    policy(company, doc)
    req = request(company, org.MEMBER_A, use="OPERATIONAL")
    if expired:
        with pytest.raises(ca.CertificationError) as exc:
            sign(company, req)
        assert exc.value.status_code == 403
    else:
        assert sign(company, req)["certified"] is True


def test_delegated_read_revocation_in_other_instance_ignores_old_scope_cache(company):
    from core.org_directory import OrgDirectory
    actor = "temporary_delegate@test.invalid"
    org_directory.upsert_user(actor, "합성 임시 수임자", actor="test")
    org_directory.set_user_roles(actor, {org.DEPT_A: "viewer"}, actor="test")
    doc = copy.deepcopy(company["document"])
    doc["delegations"] = [delegation(actor=actor)]
    policy(company, doc)
    req = request(company, actor, use="OPERATIONAL")
    assert org.DEPT_A in org_directory.resolve_scope(actor).readable_dept_ids
    other = OrgDirectory(db_path=org_directory.db_path)
    other.set_user_roles(actor, {}, actor="test")
    assert org.DEPT_A in org_directory.resolve_scope(actor).readable_dept_ids  # 이전 캐시를 실제 만들었다.
    with pytest.raises(ca.CertificationError) as exc:
        sign(company, req)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("key,value", [("required_reviews", ["OPERATIONAL", "MANAGEMENT"]),
                                        ("grants", ["DATA_OWNER", "EXECUTIVE"]), ("delegations", [None])])
def test_malformed_nested_policy_has_structured_422(company, key, value):
    doc = copy.deepcopy(company["document"])
    doc[key] = value
    with pytest.raises(ca.CertificationError) as exc:
        policy(company, doc)
    assert exc.value.status_code == 422


def test_revoked_company_policy_does_not_fall_back(company):
    approved = policy(company)
    company["ledger"].append(event_type=ca.REVOKED, subject_type=ca.SUBJECT_TYPE, subject_id=approved["digest"],
                              actor_type="user", actor_id=org.ADMIN, parent_event_id=approved["approval_event_id"])
    with pytest.raises(ca.CertificationError) as exc:
        request(company)
    assert exc.value.reason_code == "POLICY_UNAVAILABLE"


@pytest.mark.parametrize("actor,context", [(org.ADMIN, "tenant"), (org.ADMIN, "mode"), (org.MEMBER_B, "scope")])
def test_context_hides_even_from_admin(company, actor, context):
    ctx = dict(company["context"])
    if context == "tenant":
        ctx["tenant_id"] = "another-tenant"
    elif context == "mode":
        ctx["entity_mode"] = "VIRTUAL"
    else:
        ctx["scope_node_id"] = org.NODES[org.DEPT_B]
    with pytest.raises(ca.CertificationError) as exc:
        cs.read(company["store"], company["sid"], actor=actor, context=ctx)
    assert exc.value.status_code == 404


def test_actual_http_preview_sign_read_and_retry(company, monkeypatch):
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as route
    policy(company)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(route, "store", company["store"])
    app = FastAPI()
    app.include_router(route.router)
    base = f"/api/v1/data-preparation/snapshots/{company['sid']}"
    headers = {"X-Factory-User": org.MANAGER_A, "X-Enterprise-Scope": company["context"]["scope_node_id"]}
    with TestClient(app) as client:
        params = dict(use_kind="OPERATIONAL", period_from="2026-08-01", period_to="2026-08-31")
        preview = client.get(base + "/certification-subject", params=params, headers=headers)
        assert preview.status_code == 200, preview.text
        subject = preview.json()["data"]
        body = {**params, "review_kind": "DATA_OWNER", "reconciliation_evidence": EVIDENCE,
                "subject_id": subject["subject_id"], "expected_subject_digest": subject["digest"], "client_request_id": "http-request"}
        response = client.post(base + "/certifications", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert client.post(base + "/certifications", json=body, headers=headers).json() == response.json()
        read = client.get(base + "/certifications", headers=headers)
        assert read.status_code == 200 and read.json()["data"]["state"] == m.OWNER_CERTIFIED
