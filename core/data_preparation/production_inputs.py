"""배치 1건·생산 결과 1건을 유지하는 버전형 투입 명세.

합성 후보 산식이다. 측정된 실제 투입량, 로트 추적 또는 승인된 원가 모델이 아니다.
질량·개수를 합산하지 않으며 EA의 소비 기준·올림 규칙은 BOM에 명시해야 한다.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

from core.calc_models import BOM_INPUT_ROLES

INPUT_VERSION = "batch-inputs/1"
LEGACY_FIELDS = ("input_material_id", "input_quantity", "input_lot_id")
LINE_FIELDS = {"input_line_id", "material_id", "quantity", "quantity_uom", "lot_id", "bom_refs"}
UNITS = {"TON", "KG", "G", "EA"}


class ProductionInputError(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def required(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProductionInputError(f"MISSING_{field}")
    return value.strip()


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ProductionInputError("INVALID_INPUT_NUMBER") from exc
    if not result.is_finite() or result <= 0:
        raise ProductionInputError("INVALID_INPUT_NUMBER")
    return result


def modern(batch):
    # 빈 값·알 수 없는 판도 옛 형식으로 받아들이지 않는다.
    return "input_contract_version" in batch or "input_lines" in batch


def input_lines(batch):
    """CSV의 JSON 문자열과 배열을 같은 계약으로 검증. 옛 형식은 제한적으로 읽는다."""
    if not modern(batch):
        quantity = number(batch.get("input_quantity"))
        return [{"input_line_id": "", "material_id": required(batch, "input_material_id"),
                 "quantity": str(quantity), "quantity_uom": required(batch, "quantity_uom"),
                 "lot_id": batch.get("input_lot_id", ""), "bom_refs": []}]
    if batch.get("input_contract_version") != INPUT_VERSION:
        raise ProductionInputError("UNSUPPORTED_INPUT_VERSION")
    if any(batch.get(key) not in (None, "") for key in LEGACY_FIELDS):
        raise ProductionInputError("MIXED_INPUT_CONTRACT")
    lines = batch.get("input_lines")
    if isinstance(lines, str):
        try:
            lines = json.loads(lines)
        except (ValueError, TypeError) as exc:
            raise ProductionInputError("INVALID_INPUT_JSON") from exc
    if not isinstance(lines, list) or not lines:
        raise ProductionInputError("EMPTY_INPUT_LINES")
    ids, materials, result = set(), set(), []
    for line in lines:
        if not isinstance(line, dict) or set(line) != LINE_FIELDS:
            raise ProductionInputError("INVALID_INPUT_FIELDS")
        identity, material, unit, lot = (required(line, key) for key in
                                        ("input_line_id", "material_id", "quantity_uom", "lot_id"))
        quantity = number(line.get("quantity"))
        if identity in ids or material in materials:
            raise ProductionInputError("DUPLICATE_INPUT_LINE")
        if unit not in UNITS or unit == "EA" and quantity != quantity.to_integral_value():
            raise ProductionInputError("INVALID_INPUT_UNIT_OR_COUNT")
        refs = line.get("bom_refs")
        if not isinstance(refs, list) or not refs or any(
                not isinstance(r, dict) or set(r) != {"bom_id", "line_no", "fingerprint"}
                or any(not isinstance(r.get(k), str) or not r[k].strip() for k in r) for r in refs):
            raise ProductionInputError("INVALID_BOM_REFS")
        ids.add(identity)
        materials.add(material)
        result.append({**line, "quantity": str(quantity), "material_id": material,
                       "input_line_id": identity, "quantity_uom": unit, "lot_id": lot})
    return result


def unique(rows, field, identity, tenant):
    found = [r for r in rows if r.get("tenant_id") == tenant and r.get(field) == identity]
    if len(found) != 1:
        raise ProductionInputError("REFERENCE_NOT_UNIQUE")
    return found[0]


def model_inputs(batch, recipes, materials):
    """유효 BOM 계수·기록 수율로 합성 투입 명세 생성. 합산 후 원료별 한 번 반올림."""
    tenant, scope, batch_id, product, output_unit = (
        required(batch, key) for key in
        ("tenant_id", "scope_node_id", "batch_id", "output_material_id", "quantity_uom"))
    when = date.fromisoformat(required(batch, "production_date"))
    quantity, ratio = number(batch.get("output_quantity")), number(batch.get("actual_yield"))
    if ratio > 1:
        raise ProductionInputError("INVALID_YIELD")
    output = unique(materials, "material_id", product, tenant)
    if output.get("base_uom") != output_unit:
        raise ProductionInputError("OUTPUT_MASTER_UNIT_MISMATCH")
    selected = [r for r in recipes if r.get("tenant_id") == tenant
                and r.get("scope_node_id") == scope and r.get("output_material_id") == product
                and r.get("component_role") in BOM_INPUT_ROLES
                and date.fromisoformat(r["effective_from"]) <= when <= date.fromisoformat(r["effective_to"])]
    if not selected:
        raise ProductionInputError("NO_EFFECTIVE_INPUT_BOM")
    if len({required(r, "bom_id") for r in selected}) != 1:
        raise ProductionInputError("AMBIGUOUS_INPUT_BOM")
    grouped, seen = defaultdict(list), set()
    for row in selected:
        identity = (required(row, "bom_id"), str(row.get("line_no") or "").strip())
        if not identity[1] or identity in seen:
            raise ProductionInputError("DUPLICATE_BOM_LINE")
        seen.add(identity)
        material = required(row, "input_material_id")
        master = unique(materials, "material_id", material, tenant)
        unit = required(row, "input_uom")
        if unit != master.get("base_uom") or row.get("output_uom") != output_unit or unit not in UNITS:
            raise ProductionInputError("BOM_MASTER_UNIT_MISMATCH")
        if unit == "EA" and (row.get("consumption_basis") != "PER_GOOD_OUTPUT"
                             or row.get("count_rounding") != "CEILING"):
            raise ProductionInputError("EA_CONSUMPTION_POLICY_REQUIRED")
        grouped[material].append(row)
    result = []
    for material, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda r: str(r["line_no"]))
        unit = rows[0]["input_uom"]
        coefficient = sum((number(r.get("quantity_per_output")) for r in rows), Decimal(0))
        amount = quantity * coefficient
        if unit == "EA":
            amount = amount.to_integral_value(rounding=ROUND_CEILING)
        else:
            amount = (amount / ratio).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if amount <= 0:
            raise ProductionInputError("INPUT_ROUNDED_TO_ZERO")
        identity = fingerprint([tenant, batch_id, material])[:20]
        result.append({"input_line_id": f"BIN-{identity}", "material_id": material,
                       "quantity": format(amount, "f"), "quantity_uom": unit,
                       "lot_id": (batch.get("input_lot_id") if batch.get("input_material_id") == material
                                  and batch.get("input_lot_id") else f"SYN-LOT-{identity}"),
                       "bom_refs": [{"bom_id": r["bom_id"], "line_no": str(r["line_no"]),
                                     "fingerprint": fingerprint(r)} for r in rows]})
    return result


def verify_model(batch, recipes, materials):
    """모델 일치는 실측 보증이 아니다. BOM 근거·단위·원료별 수량을 대조한다."""
    actual = input_lines(batch)
    if not modern(batch):
        raise ProductionInputError("LEGACY_INPUT_NOT_MODEL_VERIFIED")
    expected = model_inputs(batch, recipes, materials)
    def signature(lines):
        return sorted((r["material_id"], r["quantity_uom"], Decimal(r["quantity"]),
                       fingerprint(r["bom_refs"])) for r in lines)
    if signature(actual) != signature(expected):
        raise ProductionInputError("INPUT_MODEL_MISMATCH")
    return actual

