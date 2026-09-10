"""K1-c2 검토 도구: 읽기 전용과 집계 단위만 검증한다. 설치 시험이 아니다."""
import sqlite3
from copy import deepcopy

import pytest

from scripts.review_kit_logistics_impact import measured_relations, readonly


def _rows():
    data = {k: [] for k in ("PRC-01", "PRC-02", "LOG-01", "LOG-02", "LOG-03",
                            "LOG-04", "LOG-05", "INV-02", "MDM-02")}
    common = {"tenant_id": "test-tenant", "scope_node_id": "test-plant"}
    data["PRC-01"] = [{**common, "contract_id": "C1", "supplier_id": "S1", "material_id": "M1",
                       "currency": "KRW", "quantity_uom": "TON", "valid_from": "2024-01-01",
                       "valid_to": "2025-12-31", "contract_quantity": "20", "ordered_quantity": "10"}]
    data["PRC-02"] = [{**data["PRC-01"][0], "po_line_id": "P1", "order_date": "2024-01-01", "order_quantity": "10"}]
    data["MDM-02"] = [{**common, "supplier_id": "S1", "material_ids": '["M1"]'}]
    data["LOG-01"] = [{**common, "submission_id": "U1", "business_ref": "P1", "partner_id": "S1", "submitted_at": ""}]
    data["LOG-02"] = [{**common, "shipment_id": "H1", "po_line_id": "P1"}]
    data["LOG-05"] = [{**common, "transport_event_id": "D1", "shipment_id": "H1", "event_type": "DELIVERED",
                       "destination_location_id": "W1", "quantity_uom": "TON", "event_at": "2024-01-10T00:00:00+00:00", "delivered_quantity": "10"}]
    data["INV-02"] = [{**common, "movement_type": "PURCHASE_RECEIPT", "reference_id": "H1", "material_id": "M1",
                       "to_location_id": "W1", "quantity_uom": "TON", "movement_date": "2024-01-10", "quantity": "10"}]
    return data


def _counts(data):
    return measured_relations(data, [], [], "REAL")["counts"]


def test_readonly_blocks_writes_and_missing_db(tmp_path):
    db = tmp_path / "source.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sample(value TEXT)")
    before = db.read_bytes()
    with readonly(db) as conn:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO sample VALUES ('not allowed')")
    assert db.read_bytes() == before
    missing = tmp_path / "not-created.db"
    with pytest.raises(FileNotFoundError):
        with readonly(missing):
            pass
    assert not missing.exists()


def test_contract_date_boundary_and_pending_submission():
    data = _rows()
    assert _counts(data).get("PO_OUTSIDE_CONTRACT_DATE", 0) == 0
    assert _counts(data)["SUBMISSION_DATE_NOT_RECORDED"] == 1
    data["PRC-02"][0]["order_date"] = "2023-12-31"
    assert _counts(data)["PO_OUTSIDE_CONTRACT_DATE"] == 1


@pytest.mark.parametrize("field,value", [("quantity", "9"), ("tenant_id", "another-tenant"),
                                         ("movement_date", "2024-01-11"), ("quantity_uom", "KG")])
def test_receipt_same_total_is_not_enough(field, value):
    data = _rows()
    assert _counts(data)["RECEIPT_DELIVERY_EQUAL_BUCKETS"] == 1
    data["INV-02"][0][field] = value
    assert _counts(data)["RECEIPT_DELIVERY_EQUAL_BUCKETS"] == 0


def test_ownership_coverage_is_not_tenant_wide_permission():
    data = _rows()
    baseline = deepcopy(data)
    declared = [{"tenant_id": "test-tenant", "entity_mode": "REAL", "dataset_contract_key": k,
                 "scope_node_id": "test-plant", "status": "ACTIVE"} for k in ("PRC-02", "LOG-02", "LOG-05")]
    nodes = [{"tenant_id": "test-tenant", "node_id": "test-plant", "status": "ACTIVE"}]
    assert measured_relations(data, declared, nodes, "REAL")["counts"].get("OWNERSHIP_ACTIVE_ROW_MISSING", 0) == 0
    data["PRC-02"][0]["scope_node_id"] = "another-plant"
    assert measured_relations(data, declared, nodes, "REAL")["counts"]["OWNERSHIP_ACTIVE_ROW_MISSING"] == 1
    assert baseline["PRC-02"][0]["scope_node_id"] == "test-plant"
