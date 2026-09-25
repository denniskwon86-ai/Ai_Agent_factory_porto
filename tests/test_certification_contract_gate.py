"""인증 계약 관문(`certification_subject._conforming_contract`). 격리 runner 전용.

실제 격리 조직·PDP·승인 원장·B0 정책 위에서(`test_b0_certification_subject.company`),
계약을 싣는 팩 1.2.0 을 실제로 고정한 인스턴스의 FIN-03 판으로 본다. 대역 없음.

★ 2026-09-24 실측 결함: 인증이 판의 열을 어떤 계약과도 대조하지 않아 정본에 없는
  `amount` 한 칸짜리 판이 인증·게시·운영 조회까지 통과했다.
★ 2026-09-25 결정: 계약은 팩 1.2.0 에 싣고 설치가 고정한다. 고정 계약이 없으면 인증을 막는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.data_preparation import certification_authority as ca, certification_subject as cs
from core.data_preparation import contract_conformance as cc, models as m, snapshot_service as svc
from tests import kit_samples, org_seed as org
from tests.test_b0_certification_subject import company, policy  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401

KEY = "FIN-03"


def _preview(c, sid):
    return cs.preview(c["store"], sid, actor=org.MANAGER_A, context=c["context"], use_kind="MANAGEMENT",
                      period_from="2026-08-01", period_to="2026-08-31")


def _refused(c, sid):
    with pytest.raises(ca.CertificationError) as caught:
        _preview(c, sid)
    return caught.value


def _reconciled(c, binding, payload: bytes):
    """같은 결속에 **임의 원문** 판 하나를 대사까지 올린다(제품 수집·파서 그대로)."""
    store = c["store"]
    snap = svc.ingest(store, binding=binding, payload=payload, file_name=f"{KEY}.csv",
                      workspace_root=kit_samples.raw_root(), created_by=org.MANAGER_A, data_kind=m.DATA_KIND_REAL)
    parsed = svc.parse_csv(payload, file_name=f"{KEY}.csv")
    svc.profile(store, snap["snapshot_id"], parsed.rows, parsed.columns)
    svc.standardize(store, snap["snapshot_id"], parsed.rows)
    svc.reconcile(store, snap["snapshot_id"], parsed.rows, {"row_count": len(parsed.rows)})
    return snap["snapshot_id"]


def _binding(c):
    store = c["store"]
    return store.get_binding(store.get_snapshot(c["sid"])["binding_id"])


def _sample_bytes(c, mutate=None, *, rows=4):
    columns, table = kit_samples.sample_table(KEY, c["context"], rows=rows)
    if mutate:
        mutate(columns, table)
    return kit_samples.to_csv(columns, table)


def _other_instance(c, *, install):
    """같은 조직 문맥에 **다른 설치**의 FIN-03 결속을 만든다."""
    store, context = c["store"], c["context"]
    instance = install(store, context)
    return store.create_binding(instance_id=instance["instance_id"], dataset_contract_key=KEY,
                                provider=m.PROVIDER_FILE_SNAPSHOT, config={}, **context)


def test_a_conforming_snapshot_binds_the_pinned_contract_into_the_subject(company):
    from core.data_preparation.process_kit_instances import pinned_dataset_contract
    from core.data_preparation.process_pack_artifacts import CANDIDATE_MANIFEST, load_bundle
    policy(company)
    subject = _preview(company, company["sid"])
    store = company["store"]
    instance = store.get_instance(store.get_snapshot(company["sid"])["instance_id"])
    with store.transaction() as conn:
        pinned = pinned_dataset_contract(conn, instance, KEY)
    expected = next(x for x in load_bundle(CANDIDATE_MANIFEST)["dataset_contracts"]["contracts"]
                    if x["dataset_contract_key"] == KEY)
    assert pinned == expected
    assert subject["payload"]["dataset_contract_digest"] == ca.digest(expected)


def test_the_single_column_snapshot_that_reached_production_is_refused(company):
    """★★★ 실측된 결함 그대로 — 정본에 없는 한 칸짜리 판."""
    policy(company)
    sid = _reconciled(company, _binding(company), b"amount\n1\n")
    error = _refused(company, sid)
    assert (error.reason_code, error.status_code) == ("CONTRACT_CONFORMANCE_FAILED", 422)
    required, _ = cc.requirements(
        kit_samples.canonical_contract(KEY))
    assert error.issues == [{"code": "MISSING_FIELD", "fields": required}]
    assert f"필수 필드 누락 {len(required)}개" in str(error)
    #: 막힌 판은 그대로 대사 상태다 — 인증도 서명도 남지 않았다.
    assert company["store"].get_snapshot(sid)["state"] == m.RECONCILED
    assert svc.actual_certifications(company["store"], sid) == []


def test_an_empty_business_key_is_refused_by_line_without_values(company):
    policy(company)
    business_key = kit_samples.canonical_contract(KEY)["business_keys"][0]

    def blank(columns, table):
        table[2][business_key] = ""
    error = _refused(company, _reconciled(company, _binding(company), _sample_bytes(company, blank)))
    assert error.reason_code == "CONTRACT_CONFORMANCE_FAILED"
    assert error.issues == [{"code": "EMPTY_BUSINESS_KEY", "line": 4, "fields": [business_key]}]
    assert "줄 4" in str(error)


def test_a_duplicate_business_key_is_refused_by_line_without_values(company):
    policy(company)
    business_key = kit_samples.canonical_contract(KEY)["business_keys"][0]
    seen = {}

    def duplicate(columns, table):
        seen["value"] = table[0][business_key]
        table[3][business_key] = table[0][business_key]
    error = _refused(company, _reconciled(company, _binding(company), _sample_bytes(company, duplicate)))
    assert error.issues == [{"code": "DUPLICATE_BUSINESS_KEY", "line": 5, "first_line": 2,
                             "fields": [business_key]}]
    assert seen["value"] not in str(error), "오류 문장에 업무키 값이 실렸다"


def test_an_installation_of_the_contractless_pack_cannot_certify(company):
    """1.1.0 은 계약을 싣지 않는다 — 그 설치본의 판은 대조할 계약이 없어 막힌다(추측으로 다른 판을 찾지 않는다)."""
    from core.data_preparation import process_kit_instances as pki
    from core.data_preparation.process_pack_artifacts import CANDIDATE_MANIFEST, load_bundle
    from core.enterprise_context.process_schema import ProcessBoundary

    def install(store, context):
        bundle = load_bundle(CANDIDATE_MANIFEST.parents[1] / "1.1.0" / "manifest.json")
        assert "dataset_contracts" not in bundle
        boundary = ProcessBoundary(tenant_id=context["tenant_id"], context_root_id=company["root"],
                                   entity_mode=context["entity_mode"], scope_node_id=context["scope_node_id"])
        return pki.create_or_get(store, operation_id="legacy-v110", bundle=bundle, boundary=boundary, actor=org.ADMIN)
    policy(company)
    sid = _reconciled(company, _other_instance(company, install=install), _sample_bytes(company))
    error = _refused(company, sid)
    assert (error.reason_code, error.status_code) == ("CONTRACT_NOT_PINNED", 409)


def test_a_registry_kit_instance_cannot_certify(company):
    """등록부는 같은 판번을 내용으로 덮는 mutable 목록이다 — 거기 적힌 것은 «설치에 고정된 계약» 이 아니다."""
    def install(store, context):
        store.upsert_kit_version(kit_id="REGISTRY", version="1", name="등록부 키트", source_path="test",
                                 fingerprint_value="registry-fp", profile={}, mode=m.DATA_KIND_DEMO)
        return store.create_instance(kit_id="REGISTRY", version="1", kit_fingerprint="registry-fp", **context)
    policy(company)
    sid = _reconciled(company, _other_instance(company, install=install), _sample_bytes(company))
    error = _refused(company, sid)
    assert (error.reason_code, error.status_code) == ("CONTRACT_NOT_PINNED", 409)


def test_a_raw_changed_after_reconciliation_is_not_inspected(company):
    policy(company)
    raw = Path(company["store"].get_snapshot(company["sid"])["raw_path"])
    raw.write_bytes(raw.read_bytes() + b"\n")
    error = _refused(company, company["sid"])
    assert error.reason_code == "RAW_CHECKSUM_MISMATCH"


# ── [2026-09-25] 행의 조직 경계 · 이력 조회 ───────────────────────────────────────
def test_a_row_of_another_tenant_is_refused(company):
    policy(company)

    def other_tenant(columns, table):
        table[1]["tenant_id"] = "tenant_other"
    error = _refused(company, _reconciled(company, _binding(company), _sample_bytes(company, other_tenant)))
    assert error.reason_code == "CONTRACT_CONFORMANCE_FAILED"
    assert error.issues == [{"code": "TENANT_MISMATCH", "line": 3, "fields": ["tenant_id"]}]
    assert "tenant_other" not in str(error)


def test_a_row_of_a_sibling_department_is_out_of_scope(company):
    """판은 알파 부서 범위다 — 베타(형제) 부서의 행은 기존 권한 계약이 허용한 범위 밖이다."""
    policy(company)
    sibling = org.NODES[org.DEPT_B]

    def sibling_scope(columns, table):
        table[0]["scope_node_id"] = sibling
    error = _refused(company, _reconciled(company, _binding(company), _sample_bytes(company, sibling_scope)))
    assert error.issues == [{"code": "SCOPE_OUT_OF_BOUNDS", "line": 2, "fields": ["scope_node_id"]}]
    assert sibling not in str(error)


def test_a_blocked_in_progress_signature_is_still_readable_as_history(company, monkeypatch):
    """관문은 새 서명을 막을 뿐이다 — 진행 중 서명의 이력 조회는 상태와 사유로 보여 준다."""
    def install(store, context):
        store.upsert_kit_version(kit_id="REGISTRY", version="1", name="등록부 키트", source_path="test",
                                 fingerprint_value="registry-fp", profile={}, mode=m.DATA_KIND_DEMO)
        return store.create_instance(kit_id="REGISTRY", version="1", kit_fingerprint="registry-fp", **context)
    policy(company)
    sid = _reconciled(company, _other_instance(company, install=install), _sample_bytes(company))
    args = dict(actor=org.MANAGER_A, context=company["context"], use_kind="MANAGEMENT",
                period_from="2026-08-01", period_to="2026-08-31")
    with monkeypatch.context() as before_the_gate:
        before_the_gate.setattr(cs, "_conforming_contract", lambda conn, row: "")
        subject = cs.preview(company["store"], sid, **args)
        partial = svc.sign_actual_certification(company["store"], sid, review_kind="DATA_OWNER",
            reconciliation_evidence="합성 시험 ERP 마감본 2026/08 총계 대사 일치", subject_id=subject["subject_id"],
            expected_subject_digest=subject["digest"], client_request_id="in-progress-before-gate", **args)
    assert partial["certified"] is False
    history = cs.read(company["store"], sid, actor=org.MANAGER_A, context=company["context"])
    assert history["review_status"] == "CONTRACT_BLOCKED"
    assert history["review_issue"]["reason_code"] == "CONTRACT_NOT_PINNED"
    assert len(history["signatures"]) == 1
