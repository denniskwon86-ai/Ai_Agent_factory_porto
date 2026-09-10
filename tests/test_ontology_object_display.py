from __future__ import annotations

import csv
import io

import pytest

from core.data_preparation.snapshot_service import checksum_bytes
from core.data_preparation import scope_index
from core.ontology_object_display import (
    ObjectDisplayIntegrityError,
    describe_dataset_object,
    describe_decision_object,
    describe_driver_object,
    describe_ecm_object,
    describe_scenario_object,
)


CASES = [
    ("PRC-01", "procurement-contract", "contract_id", "CTR-1",
     {"contract_quantity": "150", "quantity_uom": "TON", "incoterm": "FOB",
      "valid_from": "2026-01-01", "valid_to": "2026-12-31"},
     "조달 계약 1 · 150 TON · FOB · 2026-01-01~2026-12-31"),
    ("PRC-02", "purchase-order-line", "po_line_id", "PO-1-10",
     {"order_quantity": "15", "quantity_uom": "TON", "due_date": "2026-03-12"},
     "구매 주문행 1 · 15 TON · 2026-03-12 납기"),
    ("LOG-01", "partner-submission", "submission_id", "SUB-1",
     {"submission_status": "ACCEPTED", "submitted_at": "2026-03-01T09:00:00Z",
      "source_version": "3"},
     "파트너 제출 1 · ACCEPTED · 2026-03-01T09:00:00Z · 판 3"),
    ("LOG-02", "shipment", "shipment_id", "SHP-1",
     {"origin_port": "PERTH", "destination_port": "ULSAN", "shipment_quantity": "15",
      "quantity_uom": "TON", "eta": "2026-03-12"},
     "선적 1 · PERTH→ULSAN · 15 TON · 2026-03-12 도착 예정"),
    ("LOG-03", "shipment-milestone", "milestone_id", "MS-1",
     {"event_type": "ATA", "planned_at": "2026-03-12", "actual_at": "2026-03-14"},
     "선적 이정표 1 · ATA · 2026-03-14"),
    ("LOG-04", "customs-clearance", "clearance_id", "CLR-1",
     {"inspection_status": "PASSED", "status": "CLEARED", "cleared_at": "2026-03-15"},
     "통관 처리 1 · PASSED · CLEARED · 2026-03-15"),
    ("LOG-05", "transport-event", "transport_event_id", "TRN-1",
     {"event_type": "DELIVERED", "event_at": "2026-03-16", "delivered_quantity": "15",
      "quantity_uom": "TON"},
     "내륙 운송 사건 1 · DELIVERED · 2026-03-16 · 15 TON"),
    ("INV-01", "inventory-snapshot", "snapshot_id", "STK-1",
     {"snapshot_date": "2026-03-01", "unrestricted_quantity": "260",
      "quantity_uom": "TON"},
     "재고 현황 1 · 2026-03-01 기준 · 가용 260 TON"),
    ("MFG-01", "production-plan-line", "plan_line_id", "MPS-1",
     {"plan_date": "2026-03-05", "plan_quantity": "300", "quantity_uom": "TON"},
     "생산 계획행 1 · 2026-03-05 계획 · 300 TON"),
    ("MFG-02", "production-batch", "batch_id", "BAT-1",
     {"production_date": "2026-03-05", "output_quantity": "288", "quantity_uom": "TON",
      "actual_yield": "0.96", "status": "COMPLETED"},
     "생산 실적 배치 1 · 2026-03-05 생산 · 산출 288 TON · 수율 0.96 · COMPLETED"),
    ("SLS-01", "sales-line", "sales_line_id", "SO-1-10",
     {"due_date": "2026-03-20", "order_quantity": "181", "quantity_uom": "TON"},
     "판매 주문행 1 · 2026-03-20 납기 · 181 TON"),
    ("FIN-01", "cost-record", "cost_record_id", "CST-1",
     {"cost_component": "RAW_MATERIAL", "actual_unit_cost": "1250000",
      "currency": "KRW", "fiscal_period": "2026-03"},
     "원가 실적 1 · RAW_MATERIAL · 실제단가 1,250,000 KRW · 2026-03"),
    ("FIN-02", "finance-document", "finance_document_id", "DOC-1",
     {"document_type": "INVOICE", "amount": "2500000", "currency": "KRW",
      "status": "POSTED"},
     "재무 문서 1 · INVOICE · 2,500,000 KRW · POSTED"),
    ("FIN-03", "ledger-line", "ledger_line_id", "LED-1",
     {"debit_amount": "2500000", "credit_amount": "0", "currency": "KRW",
      "fiscal_period": "2026-03"},
     "원장 전기행 1 · 차변 2,500,000 · 대변 0 KRW · 2026-03"),
]

REFERENCE_CASES = [
    ("MDM-01", "mdm", "material", "material_id", "MAT-1",
     {"material_name": "동정광", "material_type": "RAW", "base_uom": "TON"},
     "품목 1 · 동정광 · RAW · 기준단위 TON"),
    ("MDM-02", "mdm", "supplier", "supplier_id", "SUP-1",
     {"supplier_name": "가상 공급사", "country_code": "KR", "risk_grade": "LOW"},
     "공급사 1 · 가상 공급사 · 국가 KR · 위험등급 LOW"),
    ("MDM-04", "mdm", "location", "location_id", "LOC-1",
     {"location_name": "원료창고", "storage_type": "RAW",
      "capacity_quantity": "80000", "capacity_uom": "TON"},
     "사업장 위치 1 · 원료창고 · RAW · 용량 80,000 TON"),
    ("MDM-06", "mdm", "equipment", "equipment_id", "EQ-1",
     {"equipment_name": "원료준비 설비", "rate_per_hour": "3.5", "rate_uom": "TON/H"},
     "설비 1 · 원료준비 설비 · 기준능력 3.5 TON/H"),
    ("MDM-07", "mdm", "account", "account_id", "1000",
     {"account_name": "현금및현금성자산", "account_type": "ASSET", "currency": "KRW"},
     "계정 1 · 현금및현금성자산 · ASSET · KRW"),
    ("MDM-08", "mdm", "logistics-reference", "reference_id", "INC-FOB",
     {"reference_type": "INCOTERM", "origin": "", "destination": ""},
     "물류 기준 1 · INCOTERM"),
    ("EXT-01", "external", "external-observation", "observation_id", "OBS-1",
     {"observed_at": "2026-03-01", "value": "1316.2845", "unit": "KRW/USD",
      "trust_grade": "DEMO_ONLY"},
     "대외 관측값 1 · 2026-03-01 · 1,316.28 KRW/USD · 신뢰등급 DEMO_ONLY"),
]


def _sealed_csv(tmp_path, id_column: str, object_id: str, fields: dict):
    columns = [id_column, *fields.keys()]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerow({id_column: object_id, **fields})
    payload = stream.getvalue().encode("utf-8")
    path = tmp_path / "sealed.csv"
    path.write_bytes(payload)
    return path, checksum_bytes(payload)


@pytest.mark.parametrize("contract_key,object_type,id_column,object_id,fields,expected", CASES)
def test_descriptor_uses_human_fields_not_object_id(
        tmp_path, contract_key, object_type, id_column, object_id, fields, expected):
    path, checksum = _sealed_csv(tmp_path, id_column, object_id, fields)
    descriptor = describe_dataset_object(
        namespace="dataset", object_type=object_type, object_id=object_id,
        snapshot_id="ds-sealed", dataset_contract_key=contract_key,
        raw_path=str(path), checksum=checksum)
    assert descriptor.display_name == expected
    assert object_id not in descriptor.display_name
    assert len(descriptor.display_fingerprint) == 64


@pytest.mark.parametrize(
    "contract_key,namespace,object_type,id_column,object_id,fields,expected",
    REFERENCE_CASES)
def test_reference_descriptor_uses_human_fields_not_object_id(
        tmp_path, contract_key, namespace, object_type, id_column, object_id,
        fields, expected):
    path, checksum = _sealed_csv(tmp_path, id_column, object_id, fields)
    descriptor = describe_dataset_object(
        namespace=namespace, object_type=object_type, object_id=object_id,
        snapshot_id="ds-sealed", dataset_contract_key=contract_key,
        raw_path=str(path), checksum=checksum)
    assert descriptor.display_name == expected
    assert object_id not in descriptor.display_name
    assert len(descriptor.display_fingerprint) == 64


def test_cost_center_descriptor_groups_repeated_account_rows(tmp_path):
    rows = [
        {"account_id": "1000", "cost_center_id": "CC-PROC",
         "cost_center_name": "원료구매 원가센터",
         "tenant_id": "tenant-a", "scope_node_id": "scope-a"},
        {"account_id": "5000", "cost_center_id": "CC-PROC",
         "cost_center_name": "원료구매 원가센터",
         "tenant_id": "tenant-a", "scope_node_id": "scope-a"},
        {"account_id": "5100", "cost_center_id": "CC-MFG",
         "cost_center_name": "생산 원가센터",
         "tenant_id": "tenant-a", "scope_node_id": "scope-a"},
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    payload = stream.getvalue().encode("utf-8")
    path = tmp_path / "MDM-07.csv"
    path.write_bytes(payload)
    descriptor = describe_dataset_object(
        namespace="mdm", object_type="cost-center", object_id="CC-PROC",
        snapshot_id="ds-sealed", dataset_contract_key="MDM-07",
        raw_path=str(path), checksum=checksum_bytes(payload))
    assert descriptor.display_name == "원가센터 2 · 원료구매 원가센터 · 연결 계정 2개"
    assert "CC-PROC" not in descriptor.display_name


def test_cost_center_descriptor_rejects_conflicting_human_names(tmp_path):
    rows = [
        {"account_id": "1000", "cost_center_id": "CC-PROC",
         "cost_center_name": "원료구매 원가센터",
         "tenant_id": "tenant-a", "scope_node_id": "scope-a"},
        {"account_id": "5000", "cost_center_id": "CC-PROC",
         "cost_center_name": "다른 원가센터",
         "tenant_id": "tenant-a", "scope_node_id": "scope-a"},
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    payload = stream.getvalue().encode("utf-8")
    path = tmp_path / "MDM-07.csv"
    path.write_bytes(payload)
    with pytest.raises(ObjectDisplayIntegrityError, match="집합형 객체 설명"):
        describe_dataset_object(
            namespace="mdm", object_type="cost-center", object_id="CC-PROC",
            snapshot_id="ds-sealed", dataset_contract_key="MDM-07",
            raw_path=str(path), checksum=checksum_bytes(payload))


@pytest.mark.parametrize("contract_key,object_type,key_columns,fields,expected", [
    ("MDM-05", "bom-line", ("bom_id", "line_no"), {
        "bom_id": "BOM-1", "line_no": "10", "component_role": "INPUT",
        "quantity_per_output": "3.3", "input_uom": "TON",
        "standard_yield": "0.98", "effective_from": "2024-01-01",
    }, "BOM 구성행 1 · INPUT · 기준투입 3.3 TON · 표준수율 0.98 · 2024-01-01부터"),
    ("MDM-06", "routing-operation", ("routing_id", "operation_seq"), {
        "routing_id": "ROUTE-1", "operation_seq": "20", "operation_name": "용해",
        "rate_per_hour": "4.2", "rate_uom": "TON/H", "setup_hours": "0.75",
    }, "라우팅 공정 1 · 용해 · 기준능력 4.2 TON/H · 준비 0.75시간"),
])
def test_composite_reference_descriptor_uses_canonical_identity(
        tmp_path, contract_key, object_type, key_columns, fields, expected):
    first_column = key_columns[0]
    remaining = {key: value for key, value in fields.items() if key != first_column}
    path, checksum = _sealed_csv(tmp_path, first_column, fields[first_column], remaining)
    object_id = scope_index.object_id_for(fields, key_columns)
    descriptor = describe_dataset_object(
        namespace="mdm", object_type=object_type, object_id=object_id,
        snapshot_id="ds-sealed", dataset_contract_key=contract_key,
        raw_path=str(path), checksum=checksum)
    assert descriptor.display_name == expected
    assert object_id not in descriptor.display_name
    assert len(descriptor.display_fingerprint) == 64


def test_descriptor_fingerprint_changes_with_the_sealed_snapshot(tmp_path):
    path, checksum = _sealed_csv(
        tmp_path, "shipment_id", "SHP-1",
        {"origin_port": "PERTH", "destination_port": "ULSAN",
         "shipment_quantity": "15", "quantity_uom": "TON", "eta": "2026-03-12"})
    first = describe_dataset_object(
        namespace="dataset", object_type="shipment", object_id="SHP-1",
        snapshot_id="ds-one", dataset_contract_key="LOG-02",
        raw_path=str(path), checksum=checksum)
    second = describe_dataset_object(
        namespace="dataset", object_type="shipment", object_id="SHP-1",
        snapshot_id="ds-two", dataset_contract_key="LOG-02",
        raw_path=str(path), checksum=checksum)
    assert first.display_name == second.display_name
    assert first.display_fingerprint != second.display_fingerprint


def test_tampered_source_never_falls_back_to_the_object_id(tmp_path):
    path, checksum = _sealed_csv(
        tmp_path, "shipment_id", "SHP-1",
        {"origin_port": "PERTH", "destination_port": "ULSAN",
         "shipment_quantity": "15", "quantity_uom": "TON", "eta": "2026-03-12"})
    path.write_text(path.read_text(encoding="utf-8").replace("15", "99"), encoding="utf-8")
    with pytest.raises(ObjectDisplayIntegrityError, match="봉인된 원본"):
        describe_dataset_object(
            namespace="dataset", object_type="shipment", object_id="SHP-1",
            snapshot_id="ds-one", dataset_contract_key="LOG-02",
            raw_path=str(path), checksum=checksum)


def test_ecm_descriptor_uses_entity_and_node_names_without_internal_ids():
    descriptor = describe_ecm_object(
        object_id="node_internal_1", node_name="동제련 공장",
        entity_id="entity_internal_1", entity_name="LS MnM", entity_mode="REAL")
    assert descriptor.display_name == "LS MnM · 동제련 공장"
    assert "node_internal_1" not in descriptor.display_name
    assert "entity_internal_1" not in descriptor.display_name
    assert len(descriptor.display_fingerprint) == 64


def test_driver_descriptor_uses_approved_human_material_not_internal_id():
    descriptor = describe_driver_object(
        object_id="DRV-FX", name="원달러 환율", version=1, fingerprint="a" * 64,
        category="fx", unit="%", external_code="USD-KRW", approved_at="2026-08-28T00:00:00Z")
    assert descriptor.display_name == "경영 동인 · 원달러 환율 · fx · %"
    assert "DRV-FX" not in descriptor.display_name
    assert len(descriptor.display_fingerprint) == 64


def test_ecm_descriptor_fingerprint_changes_when_the_canonical_name_changes():
    first = describe_ecm_object(
        object_id="node_1", node_name="동제련 공장",
        entity_id="entity_1", entity_name="LS MnM", entity_mode="REAL")
    second = describe_ecm_object(
        object_id="node_1", node_name="동제련 사업장",
        entity_id="entity_1", entity_name="LS MnM", entity_mode="REAL")
    assert first.display_fingerprint != second.display_fingerprint


def test_ecm_descriptor_never_uses_an_internal_id_as_a_name():
    with pytest.raises(ObjectDisplayIntegrityError, match="내부 객체 ID"):
        describe_ecm_object(
            object_id="node_1", node_name="node_1",
            entity_id="entity_1", entity_name="LS MnM", entity_mode="REAL")


def test_decision_descriptor_uses_the_decision_question_not_internal_id():
    descriptor = describe_decision_object(
        object_id="dec_internal_1", question="원료 재고 대응안을 승인할 것인가",
        evidence_hash="e" * 32, package_version=2, status="IN_REVIEW",
        outcome="", updated_at="2026-08-28T00:00:00+00:00")
    assert descriptor.display_name == "의사결정 안건 · 원료 재고 대응안을 승인할 것인가"
    assert "dec_internal_1" not in descriptor.display_name
    assert len(descriptor.display_fingerprint) == 64


def test_decision_descriptor_fingerprint_changes_with_evidence_version():
    common = dict(
        object_id="dec_1", question="원료 재고 대응안을 승인할 것인가",
        package_version=2, status="IN_REVIEW", outcome="",
        updated_at="2026-08-28T00:00:00+00:00")
    first = describe_decision_object(evidence_hash="a" * 32, **common)
    second = describe_decision_object(evidence_hash="b" * 32, **common)
    assert first.display_name == second.display_name
    assert first.display_fingerprint != second.display_fingerprint


def test_scenario_descriptor_is_release_backed_and_hides_internal_id():
    first = describe_scenario_object(
        object_id="scn_internal", name="원료비 상승", version=1,
        fingerprint="a" * 64, baseline_kind="PLAN", baseline_period="2027",
        approved_at="2026-08-28T00:00:00+00:00")
    second = describe_scenario_object(
        object_id="scn_internal", name="원료비 상승", version=2,
        fingerprint="b" * 64, baseline_kind="PLAN", baseline_period="2027",
        approved_at="2026-08-29T00:00:00+00:00")
    assert first.display_name == "승인 시나리오 · 원료비 상승 · 기준 2027 · PLAN"
    assert "scn_internal" not in first.display_name
    assert first.display_fingerprint != second.display_fingerprint
