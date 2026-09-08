"""Read-only quantity reconciliation for the starter package's signed-movement contract.

This is neither a stock valuation nor an approved production-to-sales allocation.
It never supplies missing quantities as zero or repairs source rows.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from core.data_preparation.production_inputs import input_lines, modern, verify_model

RULE_VERSION = "starter-quantity-flow/2"
TOLERANCE = Decimal("0.001")  # Stored quantities are rounded to three decimal places.
IDENTITIES = {"MDM-01": "material_id", "MDM-04": "location_id", "INV-02": "movement_id",
              "MFG-01": "plan_line_id", "MFG-02": "batch_id", "SLS-01": "sales_line_id",
              "LOG-02": "shipment_id", "LOG-05": "transport_event_id", "PRC-02": "po_line_id"}
MOVEMENT_RULES = {
    # physical warehouse field, opposite endpoint, sign, reference type
    "OPENING": ("to_location_id", "", 1, "OPENING_BALANCE"),
    "PURCHASE_RECEIPT": ("to_location_id", "IN_TRANSIT", 1, "SHIPMENT"),
    "PRODUCTION_ISSUE": ("from_location_id", "PRODUCTION", -1, "BATCH"),
    "PRODUCTION_RECEIPT": ("to_location_id", "PRODUCTION", 1, "BATCH"),
    "SALES_SHIPMENT": ("from_location_id", "CUSTOMER", -1, "SALES_ORDER"),
    "CYCLE_COUNT_ADJUSTMENT": ("to_location_id", "ADJUSTMENT", 0, "CYCLE_COUNT"),
}


class _Invalid(ValueError):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail
        super().__init__(detail)


def _text(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise _Invalid("Q_REQUIRED", f"Missing {field}")
    return value.strip()


def _number(row, field):
    try:
        value = Decimal(str(row.get(field)))
    except InvalidOperation as exc:
        raise _Invalid("Q_NUMBER", f"Invalid {field}") from exc
    if not value.is_finite():
        raise _Invalid("Q_NUMBER", f"Non-finite {field}")
    return value


def _day(row, field):
    value = _text(row, field)
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError("ISO date required")
        return result
    except ValueError as exc:
        raise _Invalid("Q_DATE", f"Invalid {field}: {value}") from exc


def inspect_quantity_flow(data: dict[str, list[dict]]) -> dict:
    """Audit explicit inventory flows; absence of this contract is not a pass."""
    issues, checks = [], Counter()

    def issue(code, dataset, line, detail):
        issues.append(dict(code=code, dataset=dataset, line=line, detail=detail))

    def report(status):
        return {"rule_version": RULE_VERSION, "status": status, "checks": dict(checks),
                "population": {"movements": len(data.get("INV-02", [])),
                               "snapshots": len(data.get("INV-01", [])),
                               "production_batches": len(data.get("MFG-02", [])),
                               "sales_lines": len(data.get("SLS-01", []))},
                "issue_count": len(issues), "issue_counts": dict(sorted(Counter(i["code"] for i in issues).items())),
                "issues": issues,
                "not_verified": ["opening balances against prior certified period",
                                 "missing whole periods outside supplied snapshot calendar",
                                 "measured consumption; legacy inputs not BOM-model verified",
                                 "lot-level genealogy and production-to-sales allocation",
                                 "inventory valuation and financial postings"]}

    if not any(key in data for key in ("INV-02", "MFG-02")):
        return report("NOT_IN_SCOPE")
    for key in (*IDENTITIES, "INV-01"):
        if not data.get(key):
            issue("Q_DATASET_UNAVAILABLE", key, 0, "Required quantity-flow source missing or empty")

    indexes = {}
    for dataset, field in IDENTITIES.items():
        index = defaultdict(list)
        for line, row in enumerate(data.get(dataset, []), 2):
            try:
                key = (_text(row, "tenant_id"), _text(row, field))
                index[key].append(row)
                if len(index[key]) > 1:
                    issue("Q_DUPLICATE_KEY", dataset, line, f"Duplicate tenant + {field}: {key[1]}")
            except _Invalid as exc:
                issue(exc.code, dataset, line, exc.detail)
        indexes[dataset] = index

    def one(dataset, tenant, identity):
        rows = indexes[dataset].get((tenant, identity), [])
        if len(rows) != 1:
            raise _Invalid("Q_REFERENCE", f"{dataset}: {identity!r} has {len(rows)} same-company matches")
        return rows[0]

    def context(row, material_field="material_id"):
        tenant, scope, material, unit = (_text(row, f) for f in
                                        ("tenant_id", "scope_node_id", material_field, "quantity_uom"))
        master = one("MDM-01", tenant, material)
        if _text(master, "base_uom") != unit:
            raise _Invalid("Q_UNIT", f"{material}: unit differs from master; no implicit conversion")
        return tenant, scope, material, unit

    def warehouse(ctx, identity):
        tenant, scope, material, unit = ctx
        master = one("MDM-04", tenant, identity)
        if _text(master, "scope_node_id") != scope:
            raise _Invalid("Q_WAREHOUSE_SCOPE", f"{identity}: warehouse belongs to another scope")
        if str(master.get("active")).strip().lower() != "true":
            raise _Invalid("Q_WAREHOUSE_INACTIVE", f"{identity}: warehouse is not active")
        return tenant, scope, material, identity, unit

    def same(row, source, material_field):
        actual, expected = context(row), context(source, material_field)
        if actual != expected:
            raise _Invalid("Q_SOURCE_CONTEXT", "Movement differs from source company/scope/material/unit")

    batch_inputs = {}

    def inputs(batch):
        key = id(batch)
        if key not in batch_inputs:
            try:
                batch_inputs[key] = (verify_model(batch, data.get("MDM-05", []), data.get("MDM-01", []))
                                     if modern(batch) else input_lines(batch))
            except (ValueError, KeyError, ArithmeticError) as exc:
                batch_inputs[key] = _Invalid("Q_INPUT_CONTRACT", str(exc))
        result = batch_inputs[key]
        if isinstance(result, _Invalid):
            raise result
        return result

    def total_key(row, kind, identity):
        key = (row.get("tenant_id"), kind, identity)
        if kind == "PRODUCTION_ISSUE":
            key += (row.get("material_id"), row.get("quantity_uom"), row.get("input_line_id") or "")
        return key

    totals, receipts, invalid_groups = defaultdict(Decimal), defaultdict(Decimal), set()
    movements = defaultdict(list)
    invalid_movements = 0
    for line, row in enumerate(data.get("INV-02", []), 2):
        kind = row.get("movement_type")
        group = total_key(row, kind, row.get("reference_id"))
        try:
            one("INV-02", _text(row, "tenant_id"), _text(row, "movement_id"))
            if kind not in MOVEMENT_RULES:
                raise _Invalid("Q_MOVEMENT_TYPE", f"Unsupported movement type: {kind}")
            field, opposite, sign, reference = MOVEMENT_RULES[kind]
            other = "from_location_id" if field == "to_location_id" else "to_location_id"
            if row.get(other, "") != opposite or row.get("reference_type") != reference:
                raise _Invalid("Q_MOVEMENT_ENDPOINT", "Movement endpoint/reference type disagrees with contract")
            ref = _text(row, "reference_id")
            ctx = context(row)
            bucket = warehouse(ctx, _text(row, field))
            qty, when = _number(row, "quantity"), _day(row, "movement_date")
            if ctx[3] == "EA" and qty != qty.to_integral_value():
                raise _Invalid("Q_COUNT", "EA movement requires an integer count")
            if (sign and qty * sign <= 0) or (not sign and qty == 0):
                raise _Invalid("Q_MOVEMENT_SIGN", "Signed quantity disagrees with movement type")
            if kind in {"PRODUCTION_ISSUE", "PRODUCTION_RECEIPT"}:
                batch = one("MFG-02", ctx[0], ref)
                if kind == "PRODUCTION_ISSUE":
                    matches = [item for item in inputs(batch)
                               if item["input_line_id"] == (row.get("input_line_id") or "")]
                    if len(matches) != 1:
                        raise _Invalid("Q_INPUT_LINE_REFERENCE", "Production issue is not bound to one input line")
                    item = matches[0]
                    same(row, {**batch, **item}, "material_id")
                    if modern(batch) and row.get("lot_id") != item["lot_id"]:
                        raise _Invalid("Q_INPUT_LOT", "Issue lot differs from the declared input line")
                else:
                    same(row, batch, "output_material_id")
                if when != _day(batch, "production_date"):
                    raise _Invalid("Q_SOURCE_DATE", "Movement date differs from production date")
            elif kind == "SALES_SHIPMENT":
                sales = one("SLS-01", ctx[0], ref)
                same(row, sales, "product_id")
                # Partial shipments may precede the final shipment, but not the order itself.
                if not _day(sales, "order_date") <= when <= _day(sales, "actual_ship_date"):
                    raise _Invalid("Q_SOURCE_DATE", "Shipment outside order/final-shipment dates")
            elif kind == "PURCHASE_RECEIPT":
                shipment = one("LOG-02", ctx[0], ref)
                po = one("PRC-02", ctx[0], _text(shipment, "po_line_id"))
                # Destination warehouse owns received stock; source purchasing scope can differ.
                if row.get("material_id") != po.get("material_id") or row.get("quantity_uom") != po.get("quantity_uom"):
                    raise _Invalid("Q_SOURCE_CONTEXT", "Receipt material/unit differs from purchase order")
            totals[group] += qty
            # Receipt-event comparison must also retain date and physical destination.
            if kind == "PURCHASE_RECEIPT":
                receipts[(ctx[0], ref, when, bucket)] += qty
            movements[bucket].append((when, kind, qty))
            checks["valid_movements"] += 1
        except _Invalid as exc:
            invalid_movements += 1
            invalid_groups.add(group)
            issue(exc.code, "INV-02", line, exc.detail)

    def reconcile(dataset, line, row, kind, identity_field, quantity_field, sign=1):
        key = total_key(row, kind, _text(row, identity_field))
        expected = _number(row, quantity_field)
        if expected < 0:
            raise _Invalid("Q_SOURCE_QUANTITY", f"Negative {quantity_field}")
        if key in invalid_groups:
            checks["blocked_source_totals"] += 1
            return
        actual = totals.get(key, Decimal(0)) * sign
        if abs(actual - expected) > TOLERANCE:
            issue("Q_SOURCE_TOTAL", dataset, line, f"{identity_field}={key[2]}, {kind}: expected={expected}, movements={actual}")
        else:
            checks["matched_source_totals"] += 1

    for line, row in enumerate(data.get("MFG-02", []), 2):
        try:
            tenant, scope, product, unit = context(row, "output_material_id")
            items = inputs(row)
            _day(row, "production_date")
            plan = one("MFG-01", tenant, _text(row, "plan_line_id"))
            if context(plan, "product_id") != (tenant, scope, product, unit):
                raise _Invalid("Q_BATCH_PLAN", "Batch differs from referenced production plan")
            for item in items:
                source = {**row, **item}
                context(source)
                reconcile("MFG-02", line, source, "PRODUCTION_ISSUE", "batch_id", "quantity", -1)
            if modern(row):
                checks["matched_synthetic_input_models"] += 1
            reconcile("MFG-02", line, row, "PRODUCTION_RECEIPT", "batch_id", "output_quantity")
        except _Invalid as exc:
            issue(exc.code, "MFG-02", line, exc.detail)
    for line, row in enumerate(data.get("SLS-01", []), 2):
        try:
            context(row, "product_id")
            if _number(row, "shipped_quantity") > _number(row, "order_quantity") + TOLERANCE:
                raise _Invalid("Q_SALES_OVER_ORDER", "Shipped quantity exceeds order; no over-delivery allowance supplied")
            reconcile("SLS-01", line, row, "SALES_SHIPMENT", "sales_line_id", "shipped_quantity", -1)
        except _Invalid as exc:
            issue(exc.code, "SLS-01", line, exc.detail)

    deliveries = defaultdict(Decimal)
    invalid_deliveries = False
    for line, row in enumerate(data.get("LOG-05", []), 2):
        if row.get("event_type") != "DELIVERED":
            continue
        try:
            tenant, ref = _text(row, "tenant_id"), _text(row, "shipment_id")
            one("LOG-05", tenant, _text(row, "transport_event_id"))
            shipment = one("LOG-02", tenant, ref)
            po = one("PRC-02", tenant, _text(shipment, "po_line_id"))
            ctx = context({**row, "material_id": po.get("material_id")})
            if ctx[3] != po.get("quantity_uom"):
                raise _Invalid("Q_UNIT", "Delivery unit differs from order")
            bucket = warehouse(ctx, _text(row, "destination_location_id"))
            # LOG-05 contract records local date + time; the date is its business posting day.
            event_at = _text(row, "event_at")
            try:
                if len(event_at) <= 10 or event_at[10] not in {"T", " "}:
                    raise ValueError("timestamp required")
                when = datetime.fromisoformat(event_at).date()
            except ValueError as exc:
                raise _Invalid("Q_DATE", "Invalid delivery event timestamp") from exc
            quantity = _number(row, "delivered_quantity")
            if quantity < 0:
                raise _Invalid("Q_SOURCE_QUANTITY", "Negative delivered quantity")
            deliveries[(tenant, ref, when, bucket)] += quantity
        except _Invalid as exc:
            invalid_deliveries = True
            issue(exc.code, "LOG-05", line, exc.detail)
    if not invalid_deliveries and data.get("LOG-05"):
        keys = set(deliveries) | set(receipts)
        for key in sorted(keys):
            if (key[0], "PURCHASE_RECEIPT", key[1]) in invalid_groups:
                checks["blocked_receipt_totals"] += 1
                continue
            if abs(deliveries.get(key, Decimal(0)) - receipts.get(key, Decimal(0))) > TOLERANCE:
                issue("Q_RECEIPT_TOTAL", "LOG-05", 0, f"shipment={key[1]}, day={key[2]}, warehouse={key[3][3]}: delivery/receipt mismatch")
            else:
                checks["matched_receipt_totals"] += 1

    # Prefix sums keep full-profile cost O(m log m + s log m), not one scan per snapshot.
    timelines = {}
    for bucket, rows in movements.items():
        daily = defaultdict(Decimal)
        first_day = min(r[0] for r in rows)
        openings = [r for r in rows if r[1] == "OPENING"]
        if len(openings) > 1 or any(r[0] != first_day for r in openings):
            invalid_movements += 1
            issue("Q_OPENING_POSITION", "INV-02", 0, f"{bucket}: duplicate or late opening balance")
        for when, _, quantity in rows:
            daily[when] += quantity
        dates, amounts, running = [], [], Decimal(0)
        for when, quantity in sorted(daily.items()):
            running += quantity
            dates.append(when)
            amounts.append(running)
        timelines[bucket] = (dates, amounts)

    snapshots, days = {}, set()
    for line, row in enumerate(data.get("INV-01", []), 2):
        try:
            quantities = [_number(row, field) for field in
                          ("unrestricted_quantity", "quality_quantity", "blocked_quantity")]
            # A bad unit/reference must not hide a separately observable negative stock.
            if any(q < 0 for q in quantities):
                issue("Q_NEGATIVE_STOCK", "INV-01", line, f"{row.get('snapshot_id')}: negative physical stock")
            bucket = warehouse(context(row), _text(row, "location_id"))
            when = _day(row, "snapshot_date")
            if _text(row, "lot_id") != "ALL":
                raise _Invalid("Q_SNAPSHOT_GRAIN", "Only warehouse/material ALL-lot reconciliation is supported")
            key = (bucket, when)
            if key in snapshots:
                raise _Invalid("Q_SNAPSHOT_DUPLICATE", "Duplicate company/scope/material/warehouse/unit/date")
            # Safety stock is policy, not a fourth physical stock compartment.
            snapshots[key] = (line, sum(quantities, Decimal(0)))
            days.add((bucket[0], bucket[1], when))
        except _Invalid as exc:
            issue(exc.code, "INV-01", line, exc.detail)

    if invalid_movements or not data.get("INV-02"):
        # Do not call an accidentally matching subtotal reconciled after dropping invalid movements.
        checks["blocked_snapshot_comparisons"] = len(snapshots)
    else:
        for (bucket, when), (line, expected) in snapshots.items():
            dates, amounts = timelines.get(bucket, ([], []))
            pos = bisect_right(dates, when) - 1
            actual = amounts[pos] if pos >= 0 else Decimal(0)
            if abs(actual - expected) > TOLERANCE:
                issue("Q_STOCK_BALANCE", "INV-01", line, f"{bucket}, {when}: snapshot={expected}, ledger={actual}")
            else:
                checks["matched_snapshot_totals"] += 1
        # A removed snapshot must not vanish from the comparison population.
        for bucket, (dates, amounts) in timelines.items():
            if not any((tenant, scope) == bucket[:2] for tenant, scope, _ in days):
                issue("Q_SNAPSHOT_MISSING", "INV-01", 0, f"{bucket}: no snapshot calendar for this company/scope")
            for tenant, scope, when in sorted(days):
                if (tenant, scope) != bucket[:2] or (bucket, when) in snapshots:
                    continue
                pos = bisect_right(dates, when) - 1
                if pos >= 0 and abs(amounts[pos]) > TOLERANCE:
                    issue("Q_SNAPSHOT_MISSING", "INV-01", 0, f"{bucket}, {when}: nonzero stock has no snapshot")
    return report("FAIL" if issues else "PASS_CHECKED_SCOPE")
