"""시연 가격 후보의 범위·정밀도·비가격 보존 시험. DB/파일 저장을 수행하지 않는다."""
import copy
import json

import pytest

from scripts.prepare_kit_price_candidate import make_candidate, rounded_prices


def row(identity, **values):
    return {"record_id": identity, "lineage_id": "lineage-" + identity, "tenant_id": "target",
        "scope_node_id": "plant", "data_class": "SYNTHETIC", "data_origin": "SYNTHETIC",
        "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE", **values}


@pytest.fixture
def example():
    data = {k: [] for k in ("MDM-01", "MDM-02", "PRC-01", "PRC-02")}
    for i, code in [(2, "NICKEL"), (3, "SULFURIC_ACID"), (4, "NICKEL")]:
        cid, mid, sid = f"CTR-{i:05d}", f"M{i}", f"S{i}"
        n = 18 if i in (2, 3) else 1
        data["MDM-01"].append(row(mid, material_id=mid, benchmark_code=code, base_uom="TON"))
        data["MDM-02"].append(row(sid, supplier_id=sid, currency="USD", material_ids=json.dumps([mid])))
        data["PRC-01"].append(row(cid, contract_id=cid, material_id=mid, supplier_id=sid, benchmark_code=code,
            benchmark_price="999.99", premium_rate="-0.012" if i == 2 else "-0.004", currency="USD", quantity_uom="TON",
            valid_from="2023-08-18", valid_to="2024-12-31", contract_quantity="1000", ordered_quantity=str(n*10)))
        for j in range(n):
            pid = f"PO-{i}-{j}"
            data["PRC-02"].append(row(pid, po_line_id=pid, contract_id=cid, material_id=mid, supplier_id=sid,
                order_date="2023-09-01", due_date="2023-10-01", currency="USD", quantity_uom="TON",
                order_quantity="10", unit_price="999.99"))
    source = [row(code, tenant_id="source", scope_node_id="source-group", observation_id=code,
        commodity_code=code, observed_at="2023-07-31", published_at="2023-08-07", vintage_date="2023-08-07",
        currency="USD", unit="USD/TON", value=value) for code, value in [("NICKEL", "21622.8128"), ("SULFURIC_ACID", "103.0757")]]
    selected = [{"tenant_id": "target", "contract_id": f"CTR-{i:05d}"} for i in (2, 3)]
    return data, source, selected


def test_only_38_price_fields_change_and_inputs_preserved(example):
    before = copy.deepcopy(example)
    data, source, selected = example
    result = make_candidate(*example)
    assert example == before
    assert len(result["candidate_rows"]["PRC-01"]) == 2
    assert len(result["candidate_rows"]["PRC-02"]) == 36
    assert len(result["changes"]) == 38
    assert result["held_contract_ids"] == ["CTR-00004"]
    assert result["held_order_ids"] == ["PO-4-0"]
    assert [c["quantity"] for c in result["control_totals"]] == ["180", "180"]
    assert [e["unit_price"] for e in result["pricing_evidence"]] == ["21363.34", "102.67"]
    for dataset, key, price in [("PRC-01", "contract_id", "benchmark_price"), ("PRC-02", "po_line_id", "unit_price")]:
        old = {r[key]: r for r in data[dataset]}
        for new in result["candidate_rows"][dataset]:
            assert {k for k in new if new[k] != old[new[key]][k]} == {price}


@pytest.mark.parametrize("value,expected", [("2.345", "2.34"), ("2.355", "2.36")])
def test_round_half_even_explicit(value, expected):
    assert rounded_prices(value, "0") == (expected, expected)


@pytest.mark.parametrize("value,premium", [("NaN", "0"), ("Infinity", "0"), ("0", "0"), ("-1", "0"), ("1", "NaN"), ("1", "-1")])
def test_invalid_prices_rejected(value, premium):
    with pytest.raises(ValueError):
        rounded_prices(value, premium)


@pytest.mark.parametrize("problem", ["future", "currency", "unit", "actual", "mixed_source_tenant", "duplicate_source", "wrong_target", "missing_order", "material_benchmark", "certified"])
def test_unsafe_candidate_rejected(example, problem):
    data, source, selected = example
    if problem == "future":
        source[0]["vintage_date"] = "2025-01-01"
    elif problem == "currency":
        source[0]["currency"] = "KRW"
    elif problem == "unit":
        source[0]["unit"] = "USD/EA"
    elif problem == "actual":
        source[0]["data_origin"] = "ACTUAL"
    elif problem == "mixed_source_tenant":
        source[0]["tenant_id"] = "another-source"
    elif problem == "duplicate_source":
        source.append(dict(source[0]))
    elif problem == "wrong_target":
        selected[0]["contract_id"] = "CTR-00004"
    elif problem == "missing_order":
        data["PRC-02"].pop(0)
    elif problem == "material_benchmark":
        data["MDM-01"][0]["benchmark_code"] = "COPPER"
    elif problem == "certified":
        data["PRC-01"][0]["certification_status"] = "CERTIFIED_FOR_DEMO"
    with pytest.raises(ValueError):
        make_candidate(data, source, selected)
