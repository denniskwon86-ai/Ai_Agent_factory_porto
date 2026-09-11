"""RAW 진단의 누락/자료형 및 가격 단위 검토 모수 회귀. DB를 열지 않는다."""
import pytest

from scripts.inspect_kit_raw_quality import field_profile, price_basis_review


def test_required_missing_is_not_optional_missing():
    c = {"schema": {"fields": [{"name": "id", "type": "string", "required": True},
                                {"name": "benchmark_code", "type": "string", "required": False}]}}
    p = field_profile([{"id": "", "benchmark_code": ""}], c)
    assert p["missing_required"] == {"id": 1}
    assert p["missing"]["benchmark_code"] == 1
    assert p["declared_enum_fields"] == []


@pytest.mark.parametrize("field,kind,value", [
    ("quantity", "number", "NaN"), ("quantity", "number", "Infinity"),
    ("quantity", "integer", "1.2"), ("active", "boolean", "yes"),
    ("order_date", "string", "2026-02-30"), ("other", "unknown", "x"),
])
def test_invalid_contract_value_detected(field, kind, value):
    c = {"schema": {"fields": [{"name": field, "type": kind, "required": True}]}}
    assert len(field_profile([{field: value}], c)["invalid_values"]) == 1


def test_explicit_enum_is_checked():
    c = {"schema": {"fields": [{"name": "status", "type": "string", "enum": ["OPEN"]}]}}
    assert len(field_profile([{"status": "UNKNOWN"}], c)["invalid_values"]) == 1


def data_for_prices():
    contracts = [{"tenant_id": "t", "contract_id": str(i), "benchmark_code": "NICKEL", "currency": cc,
        "quantity_uom": unit, "price_formula": "BENCHMARK_PRICE*(1+PREMIUM_RATE)",
        "benchmark_price": "100", "premium_rate": "0.1"}
        for i, (cc, unit) in enumerate([("USD", "TON"), ("KRW", "TON"), ("USD", "EA"), ("KRW", "EA")])]
    orders = [{"tenant_id": "t", "po_line_id": str(i), "contract_id": str(i), "unit_price": "110"} for i in range(4)]
    return {"PRC-01": contracts, "PRC-02": orders}


def test_currency_unit_overlap_counted_once_and_no_tenant_fallback():
    data = data_for_prices()
    data["PRC-02"].append({"tenant_id": "other", "po_line_id": "other-3", "contract_id": "3", "unit_price": "110"})
    r = price_basis_review(data, [{"commodity_code": "NICKEL", "currency": "USD", "unit": "USD/TON"}])
    assert r["affected_contract_count"] == 3
    assert r["affected_order_count"] == 3
    assert r["unconverted_formula_match_count"] == 4
    assert r["contract_reason_counts"] == {"PRICE_CURRENCY_CONVERSION_UNEVIDENCED": 2,
                                          "PRICE_QUANTITY_CONVERSION_UNEVIDENCED": 2}


@pytest.mark.parametrize("source", [[], [
    {"commodity_code": "NICKEL", "currency": "USD", "unit": "USD/TON"},
    {"commodity_code": "NICKEL", "currency": "KRW", "unit": "KRW/TON"}],
    [{"commodity_code": "NICKEL", "currency": "USD", "unit": "INDEX"}]])
def test_missing_ambiguous_or_unknown_benchmark_never_passes(source):
    r = price_basis_review(data_for_prices(), source)
    assert r["affected_contract_count"] == 4
    assert r["affected_order_count"] == 4
