import copy

import pytest

from core import enterprise_financial_model as efm


def _bridge():
    return {
        "model_version": "financial-bridge-1.0",
        "reporting_currency": "KRW",
        "exchange_rate_source": "EXT-01",
        "source_snapshots": {"MDM-07": "ds-mdm", "EXT-01": "ds-fx"},
        "rules": [
            {"rule_id": "purchase_working_capital",
             "source_metrics": ["in_transit_quantity"],
             "target_account_codes": ["1200", "2000"]},
            {"rule_id": "production_margin",
             "source_metrics": ["producible_quantity", "shortage_quantity"],
             "target_account_codes": ["5000", "5100"]},
            {"rule_id": "revenue_recognition",
             "source_metrics": ["revenue_shift_days"],
             "target_account_codes": ["1100", "4000"]},
            {"rule_id": "currency_translation",
             "source_metrics": ["exchange_rate", "reporting_currency",
                                "transaction_currency"],
             "target_account_codes": ["1100", "1200", "2000", "4000", "5000", "5100"]},
        ],
    }


def _contributions():
    return {
        "APP-01": {"values": {"in_transit_quantity": {"MAT-1": 5}}},
        "APP-03": {"values": {
            "shortage_quantity": {"MAT-1": 2},
            "producible_quantity": {"PLAN-1": 8},
        }},
        "APP-06": {
            "values": {"revenue_shift_days": {"SL-1": 2}},
            "assumptions_used": {
                "baseline_recognition": {"SL-1": "2026-02-28T00:00:00Z"}},
        },
    }


def _datasets():
    return {
        "MDM-07": [
            {"account_id": "1200", "account_name": "재고자산"},
            {"account_id": "2000", "account_name": "매입채무"},
            {"account_id": "5000", "account_name": "재료비"},
            {"account_id": "5100", "account_name": "가공비"},
            {"account_id": "4000", "account_name": "제품매출"},
            {"account_id": "1100", "account_name": "매출채권"},
        ],
        "EXT-01": [{
            "indicator_code": "USD_KRW", "observed_at": "2026-02-27",
            "published_at": "2026-02-28", "value": "1300",
        }],
        "PRC-02": [{
            "po_line_id": "PO-1-10", "material_id": "MAT-1",
            "order_date": "2026-02-01", "unit_price": "10", "currency": "USD",
        }],
        "SLS-01": [{
            "sales_line_id": "SL-1", "product_id": "P-1",
            "order_quantity": "2", "unit_price": "100", "currency": "USD",
        }],
        "FIN-01": [
            {"cost_record_id": "C-1", "fiscal_period": "2026-02",
             "product_id": "P-1", "cost_component": "MATERIAL",
             "actual_unit_cost": "40", "currency": "USD"},
            {"cost_record_id": "C-2", "fiscal_period": "2026-02",
             "product_id": "P-1", "cost_component": "CONVERSION",
             "actual_unit_cost": "10", "currency": "USD"},
        ],
        "FIN-02": [{
            "finance_document_id": "AR-1", "document_type": "AR",
            "reference_id": "SL-1", "due_date": "2026-03-31",
            "amount": "200", "currency": "USD",
        }],
    }


def _run(**overrides):
    args = {
        "composition_fingerprint": "composition-fp",
        "as_of": "2026-02-28T12:00:00Z",
        "contributions": _contributions(),
        "datasets": _datasets(),
        "bridge_contract": _bridge(),
        "bridge_fingerprint": "bridge-fp",
        "source_snapshots": {key: f"ds-{key.lower()}" for key in efm.REQUIRED_DATASETS},
    }
    args.update(overrides)
    return efm.calculate(**args)


def test_운영영향을_기간별_손익과_현금회수_이동으로_계산한다():
    got = _run()

    assert got["status"] == "COMPLETE"
    assert got["summary"] == {
        "inventory_in_transit_krw": 65000.0,
        "revenue_timing_exposure_krw": 260000.0,
        "material_conversion_margin_timing_exposure_krw": 130000.0,
        "cash_receipts_timing_exposure_krw": 260000.0,
    }
    by_period = {row["period"]: row for row in got["period_impacts"]}
    assert by_period["2026-02"]["revenue_delta_krw"] == -260000.0
    assert by_period["2026-03"]["revenue_delta_krw"] == 260000.0
    assert by_period["2026-03"]["cash_receipts_delta_krw"] == -260000.0
    assert by_period["2026-04"]["cash_receipts_delta_krw"] == 260000.0
    assert got["affected_account_names"] == [
        "가공비", "매입채무", "매출채권", "재고자산", "재료비", "제품매출"]


def test_같은_입력이면_재무_결과_지문도_같다():
    assert _run()["result_fingerprint"] == _run()["result_fingerprint"]


def test_매출인식_기준선이_봉인되지_않으면_0으로_접지_않는다():
    contributions = _contributions()
    contributions["APP-06"]["assumptions_used"] = {}
    with pytest.raises(efm.EnterpriseFinancialModelError, match="기준선"):
        _run(contributions=contributions)


def test_실제_계산기와_다른_옛_지표명은_받지_않는다():
    contributions = _contributions()
    contributions["APP-01"]["values"] = {"in_transit_qty": {"MAT-1": 5}}
    with pytest.raises(efm.EnterpriseFinancialModelError, match="in_transit_quantity"):
        _run(contributions=contributions)


def test_기준시점에_공개되지_않은_환율을_미래에서_가져오지_않는다():
    datasets = copy.deepcopy(_datasets())
    datasets["EXT-01"][0]["published_at"] = "2026-03-01"
    with pytest.raises(efm.EnterpriseFinancialModelError, match="환율"):
        _run(datasets=datasets)


def test_실제원가_구성요소가_빠지면_마진을_추정하지_않는다():
    datasets = copy.deepcopy(_datasets())
    datasets["FIN-01"] = datasets["FIN-01"][:1]
    with pytest.raises(efm.EnterpriseFinancialModelError, match="CONVERSION"):
        _run(datasets=datasets)


@pytest.mark.parametrize(
    ("field", "value"),
    [("amount", "199"), ("currency", "KRW")],
)
def test_매출채권이_판매행의_금액과_통화에_일치하지_않으면_거부한다(field, value):
    datasets = copy.deepcopy(_datasets())
    datasets["FIN-02"][0][field] = value
    with pytest.raises(efm.EnterpriseFinancialModelError, match="매출채권"):
        _run(datasets=datasets)


def test_봉인된_입력판이_바뀌면_결과_지문도_바뀐다():
    first = _run()["result_fingerprint"]
    snapshots = {key: f"ds-{key.lower()}" for key in efm.REQUIRED_DATASETS}
    snapshots["FIN-01"] = "ds-fin-01-new"
    assert _run(source_snapshots=snapshots)["result_fingerprint"] != first


def test_데이터는_있어도_인증판_결속이_빠지면_계산하지_않는다():
    snapshots = {key: f"ds-{key.lower()}" for key in efm.REQUIRED_DATASETS}
    snapshots.pop("FIN-02")
    with pytest.raises(efm.EnterpriseFinancialModelError, match="인증판 결속"):
        _run(source_snapshots=snapshots)
