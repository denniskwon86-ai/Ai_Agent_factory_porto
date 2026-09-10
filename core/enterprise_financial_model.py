"""Deterministic enterprise financial impact model for composed work scenarios.

The operating path calculates quantities and timing.  This module translates only
those sealed results into period movements using certified account, cost, receivable,
purchase-price, and FX rows.  It never invents an ending cash balance: the supported
output is the movement of revenue, material-and-conversion margin, and cash receipts
between periods.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Sequence, Tuple


MODEL_VERSION = "enterprise-financial-impact-1.0"
REQUIRED_DATASETS = ("MDM-07", "EXT-01", "PRC-02", "SLS-01", "FIN-01", "FIN-02")
REPORTING_CURRENCY = "KRW"
USD_KRW = "USD_KRW"


class EnterpriseFinancialModelError(ValueError):
    """The sealed business inputs cannot support a financial conclusion."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(row: Mapping[str, Any], key: str, where: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise EnterpriseFinancialModelError(f"{where}: {key} 값이 비어 있습니다.")
    return value


def _number(row: Mapping[str, Any], key: str, where: str) -> Decimal:
    raw = row.get(key)
    if raw in (None, ""):
        raise EnterpriseFinancialModelError(f"{where}: {key} 값이 비어 있습니다.")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise EnterpriseFinancialModelError(
            f"{where}: {key} 값이 숫자가 아닙니다.") from exc
    if not value.is_finite():
        raise EnterpriseFinancialModelError(f"{where}: {key} 값이 유한수가 아닙니다.")
    return value


def _day(value: Any, where: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise EnterpriseFinancialModelError(f"{where}: 날짜가 비어 있습니다.")
    try:
        if "T" in raw:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            got = datetime.fromisoformat(raw)
            if got.tzinfo is None:
                raise ValueError
            return got.astimezone(timezone.utc).date()
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise EnterpriseFinancialModelError(
            f"{where}: ISO-8601 날짜를 읽을 수 없습니다.") from exc


def _period(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _metric(contributions: Mapping[str, Mapping[str, Any]], app_id: str,
            name: str) -> Mapping[str, Any]:
    row = contributions.get(app_id)
    if not isinstance(row, Mapping):
        raise EnterpriseFinancialModelError(f"{app_id} 부서 결과가 없습니다.")
    values = row.get("values")
    if not isinstance(values, Mapping) or name not in values:
        raise EnterpriseFinancialModelError(
            f"{app_id} 결과에 실제 계산 지표 {name}이 없습니다.")
    metric = values[name]
    if not isinstance(metric, Mapping):
        raise EnterpriseFinancialModelError(f"{name} 지표가 객체별 값이 아닙니다.")
    return metric


def _unique(rows: Sequence[Mapping[str, Any]], key: str, where: str
            ) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for i, row in enumerate(rows):
        value = _text(row, key, f"{where}[{i}]")
        if value in out:
            raise EnterpriseFinancialModelError(
                f"{where}: {key}={value} 행이 둘 이상입니다.")
        out[value] = row
    return out


def _fx_rates(rows: Sequence[Mapping[str, Any]], as_of: date) -> Dict[str, Decimal]:
    candidates: List[Tuple[date, date, Decimal]] = []
    for i, row in enumerate(rows):
        if str(row.get("indicator_code") or "").strip().upper() != USD_KRW:
            continue
        observed = _day(row.get("observed_at"), f"EXT-01[{i}].observed_at")
        published = _day(row.get("published_at"), f"EXT-01[{i}].published_at")
        if observed <= as_of and published <= as_of:
            candidates.append((observed, published, _number(row, "value", f"EXT-01[{i}]")))
    if not candidates:
        raise EnterpriseFinancialModelError(
            "기준시점에 공개되어 있던 USD/KRW 환율이 없습니다.")
    candidates.sort(key=lambda item: (item[0], item[1]))
    latest_day = candidates[-1][:2]
    latest = [item[2] for item in candidates if item[:2] == latest_day]
    if len(set(latest)) != 1:
        raise EnterpriseFinancialModelError(
            "같은 관측·발표시점의 USD/KRW 환율이 둘 이상입니다.")
    return {"KRW": Decimal("1"), "USD": latest[0]}


def _to_krw(amount: Decimal, currency: str, rates: Mapping[str, Decimal], where: str
            ) -> Decimal:
    code = str(currency or "").strip().upper()
    rate = rates.get(code)
    if rate is None:
        raise EnterpriseFinancialModelError(
            f"{where}: {code or '미상'} 통화의 인증 환율이 없습니다.")
    return amount * rate


def _costs(rows: Sequence[Mapping[str, Any]], as_of: date,
           rates: Mapping[str, Decimal]) -> Dict[str, Decimal]:
    period = _period(as_of)
    grouped: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for row in rows:
        if str(row.get("fiscal_period") or "").strip() > period:
            continue
        product = str(row.get("product_id") or "").strip()
        component = str(row.get("cost_component") or "").strip().upper()
        if product and component in {"MATERIAL", "CONVERSION"}:
            grouped.setdefault((product, component), []).append(row)
    out: Dict[str, Decimal] = {}
    products = sorted({key[0] for key in grouped})
    for product in products:
        total = Decimal(0)
        for component in ("MATERIAL", "CONVERSION"):
            choices = grouped.get((product, component), [])
            if not choices:
                raise EnterpriseFinancialModelError(
                    f"{product}: {component} 실제 단위원가가 없습니다.")
            latest_period = max(str(row.get("fiscal_period") or "") for row in choices)
            latest = [row for row in choices
                      if str(row.get("fiscal_period") or "") == latest_period]
            if len(latest) != 1:
                raise EnterpriseFinancialModelError(
                    f"{product}: {latest_period} {component} 원가가 둘 이상입니다.")
            row = latest[0]
            total += _to_krw(
                _number(row, "actual_unit_cost", f"FIN-01 {product}/{component}"),
                str(row.get("currency") or ""), rates,
                f"FIN-01 {product}/{component}")
        out[product] = total
    return out


def _purchase_prices(rows: Sequence[Mapping[str, Any]], as_of: date,
                     rates: Mapping[str, Decimal]) -> Dict[str, Decimal]:
    grouped: Dict[str, List[Tuple[date, Mapping[str, Any]]]] = {}
    for i, row in enumerate(rows):
        ordered = _day(row.get("order_date"), f"PRC-02[{i}].order_date")
        if ordered <= as_of:
            material = _text(row, "material_id", f"PRC-02[{i}]")
            grouped.setdefault(material, []).append((ordered, row))
    out: Dict[str, Decimal] = {}
    for material, choices in grouped.items():
        latest_day = max(item[0] for item in choices)
        latest = [item[1] for item in choices if item[0] == latest_day]
        prices = {
            _to_krw(_number(row, "unit_price", f"PRC-02 {material}"),
                    str(row.get("currency") or ""), rates, f"PRC-02 {material}")
            for row in latest
        }
        if len(prices) != 1:
            raise EnterpriseFinancialModelError(
                f"{material}: 같은 최신 주문일의 구매단가가 둘 이상입니다.")
        out[material] = prices.pop()
    return out


def _account_names(bridge: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> List[str]:
    names = {str(row.get("account_id") or "").strip():
             str(row.get("account_name") or "").strip() for row in rows}
    required = sorted({str(code) for rule in bridge.get("rules") or []
                       for code in rule.get("target_account_codes") or []})
    missing = [code for code in required if not names.get(code)]
    if missing:
        raise EnterpriseFinancialModelError(
            "승인된 변환 계약의 계정과목을 인증판에서 찾을 수 없습니다.")
    return sorted({names[code] for code in required})


def calculate(*, composition_fingerprint: str, as_of: str,
              contributions: Mapping[str, Mapping[str, Any]],
              datasets: Mapping[str, Sequence[Mapping[str, Any]]],
              bridge_contract: Mapping[str, Any], bridge_fingerprint: str,
              source_snapshots: Mapping[str, str]) -> Dict[str, Any]:
    """Calculate sealed financial timing movements for one enterprise scenario."""
    if not str(composition_fingerprint or "").strip():
        raise EnterpriseFinancialModelError("전사 조합 지문이 비어 있습니다.")
    if not str(bridge_fingerprint or "").strip():
        raise EnterpriseFinancialModelError("업무-회계 변환 계약 지문이 비어 있습니다.")
    missing = [key for key in REQUIRED_DATASETS if key not in datasets]
    if missing:
        raise EnterpriseFinancialModelError(
            "전사 재무 영향에 필요한 인증 데이터가 없습니다: " + ", ".join(missing))
    unsealed = [key for key in REQUIRED_DATASETS
                if not str(source_snapshots.get(key) or "").strip()]
    if unsealed:
        raise EnterpriseFinancialModelError(
            "전사 재무 영향의 인증판 결속이 없습니다: " + ", ".join(unsealed))
    at = _day(as_of, "as_of")
    rates = _fx_rates(datasets["EXT-01"], at)
    sales = _unique(datasets["SLS-01"], "sales_line_id", "SLS-01")
    receivables = {
        key: row for key, row in _unique(
            [row for row in datasets["FIN-02"]
             if str(row.get("document_type") or "").strip().upper() == "AR"],
            "reference_id", "FIN-02 AR").items()
    }
    unit_costs = _costs(datasets["FIN-01"], at, rates)
    purchase_prices = _purchase_prices(datasets["PRC-02"], at, rates)

    in_transit = _metric(contributions, "APP-01", "in_transit_quantity")
    _metric(contributions, "APP-03", "shortage_quantity")
    _metric(contributions, "APP-03", "producible_quantity")
    shifts = _metric(contributions, "APP-06", "revenue_shift_days")
    sales_assumptions = contributions["APP-06"].get("assumptions_used") or {}
    baselines = sales_assumptions.get("baseline_recognition")
    if not isinstance(baselines, Mapping):
        raise EnterpriseFinancialModelError(
            "매출 인식 기준선이 계산 결과에 봉인되지 않았습니다.")

    inventory_exposure = Decimal(0)
    for material, raw_qty in sorted(in_transit.items()):
        if material not in purchase_prices:
            raise EnterpriseFinancialModelError(
                f"{material}: 운송 중 수량을 금액화할 인증 구매단가가 없습니다.")
        try:
            qty = Decimal(str(raw_qty))
        except InvalidOperation as exc:
            raise EnterpriseFinancialModelError(
                f"{material}: 운송 중 수량이 숫자가 아닙니다.") from exc
        inventory_exposure += qty * purchase_prices[material]

    period_moves: Dict[str, Dict[str, Decimal]] = {}
    line_impacts: List[Dict[str, Any]] = []
    revenue_exposure = Decimal(0)
    margin_exposure = Decimal(0)
    cash_exposure = Decimal(0)

    def add(period: str, name: str, amount: Decimal) -> None:
        period_moves.setdefault(period, {}).setdefault(name, Decimal(0))
        period_moves[period][name] += amount

    for sales_line_id, raw_days in sorted(shifts.items()):
        try:
            days = int(raw_days)
        except (TypeError, ValueError) as exc:
            raise EnterpriseFinancialModelError(
                f"{sales_line_id}: 매출 인식 이동일이 정수가 아닙니다.") from exc
        if days < 0:
            raise EnterpriseFinancialModelError(
                f"{sales_line_id}: 매출 인식 이동일이 음수입니다.")
        if days == 0:
            continue
        row = sales.get(sales_line_id)
        ar = receivables.get(sales_line_id)
        if row is None or ar is None:
            raise EnterpriseFinancialModelError(
                f"{sales_line_id}: 판매행 또는 매출채권 기준정보가 없습니다.")
        product = _text(row, "product_id", f"SLS-01 {sales_line_id}")
        if product not in unit_costs:
            raise EnterpriseFinancialModelError(
                f"{product}: 실제 재료비·가공비 단위원가가 없습니다.")
        baseline_raw = baselines.get(sales_line_id)
        baseline_day = _day(baseline_raw, f"{sales_line_id}.baseline_recognition")
        scenario_day = baseline_day + timedelta(days=days)
        cash_day = _day(ar.get("due_date"), f"FIN-02 {sales_line_id}.due_date")
        scenario_cash_day = cash_day + timedelta(days=days)
        qty = _number(row, "order_quantity", f"SLS-01 {sales_line_id}")
        revenue = _to_krw(
            qty * _number(row, "unit_price", f"SLS-01 {sales_line_id}"),
            str(row.get("currency") or ""), rates, f"SLS-01 {sales_line_id}")
        cost = qty * unit_costs[product]
        margin = revenue - cost
        add(_period(baseline_day), "revenue", -revenue)
        add(_period(scenario_day), "revenue", revenue)
        ar_amount = _number(ar, "amount", f"FIN-02 {sales_line_id}")
        ar_currency = str(ar.get("currency") or "").strip().upper()
        sales_currency = str(row.get("currency") or "").strip().upper()
        if ar_currency != sales_currency or ar_amount != qty * _number(
                row, "unit_price", f"SLS-01 {sales_line_id}"):
            raise EnterpriseFinancialModelError(
                f"{sales_line_id}: 판매행 금액과 매출채권 금액·통화가 일치하지 않습니다.")
        add(_period(baseline_day), "margin", -margin)
        add(_period(scenario_day), "margin", margin)
        add(_period(cash_day), "cash_receipts", -revenue)
        add(_period(scenario_cash_day), "cash_receipts", revenue)
        revenue_exposure += revenue
        margin_exposure += margin
        cash_exposure += revenue
        line_impacts.append({
            "sales_line_id": sales_line_id,
            "baseline_period": _period(baseline_day),
            "scenario_period": _period(scenario_day),
            "baseline_cash_period": _period(cash_day),
            "scenario_cash_period": _period(scenario_cash_day),
            "shift_days": days,
            "revenue_krw": _money(revenue),
            "material_conversion_margin_krw": _money(margin),
        })

    public_periods = [
        {"period": period,
         "revenue_delta_krw": _money(values.get("revenue", Decimal(0))),
         "material_conversion_margin_delta_krw": _money(
             values.get("margin", Decimal(0))),
         "cash_receipts_delta_krw": _money(values.get("cash_receipts", Decimal(0)))}
        for period, values in sorted(period_moves.items())
    ]
    account_names = _account_names(bridge_contract, datasets["MDM-07"])
    result_material = {
        "model_version": MODEL_VERSION,
        "composition_fingerprint": str(composition_fingerprint),
        "bridge_fingerprint": str(bridge_fingerprint),
        "as_of": str(as_of),
        "source_snapshots": dict(sorted(source_snapshots.items())),
        "period_impacts": public_periods,
        "line_impacts": line_impacts,
        "inventory_in_transit_krw": _money(inventory_exposure),
    }
    return {
        "status": "COMPLETE",
        "message": "부서별 운영 영향이 매출·재료비·가공비 기여액과 현금회수의 기간 이동으로 연결되었습니다.",
        "model_version": MODEL_VERSION,
        "bridge_fingerprint": str(bridge_fingerprint),
        "reporting_currency": REPORTING_CURRENCY,
        "summary": {
            "inventory_in_transit_krw": _money(inventory_exposure),
            "revenue_timing_exposure_krw": _money(revenue_exposure),
            "material_conversion_margin_timing_exposure_krw": _money(margin_exposure),
            "cash_receipts_timing_exposure_krw": _money(cash_exposure),
        },
        "period_impacts": public_periods,
        "affected_sales_lines": len(line_impacts),
        "affected_account_names": account_names,
        "result_fingerprint": _fingerprint(result_material),
    }
