"""기존 합성 배치의 다중 투입 후보. 배치·품질 참조와 생산량을 보존한다.

추가 원료는 기존 배치 투입 창고를 공급 창고로 가정한 새 합성 시나리오다.
이 가정을 실제 재고 위치나 로트 추적의 근거로 승격하지 않는다.
"""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from core.data_preparation.production_inputs import (
    INPUT_VERSION, LEGACY_FIELDS, ProductionInputError, fingerprint, input_lines,
    model_inputs, modern, number, required, verify_model,
)

RULE_VERSION = "synthetic-batch-input-rebuild/1"
CONTRACT_DELTA = {
    "dataset": "MFG-02", "status": "DRAFT_NOT_INSTALLED", "input_contract_version": INPUT_VERSION,
    "batch_business_key": ["tenant_id", "batch_id"],
    "new_fields": {"input_contract_version": "string", "input_lines": "JSON array"},
    "legacy_fields": list(LEGACY_FIELDS), "legacy_policy": "read-only legacy; never fallback from invalid new input",
    "input_fields": ["input_line_id", "material_id", "quantity", "quantity_uom", "lot_id", "bom_refs"],
    "inventory_link": "INV-02.reference_id=batch_id + input_line_id; receipt remains once per batch",
    "ea_policy": "native EA; BOM PER_GOOD_OUTPUT + CEILING required; no count/mass conversion",
}


def _pending(row):
    return {**row, "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE"}


def rebuild_production_candidate(data):
    if any(row.get("data_class") != "SYNTHETIC" or row.get("data_origin") != "SYNTHETIC"
           for rows in data.values() for row in rows):
        raise ProductionInputError("SYNTHETIC_ONLY")
    result = copy.deepcopy(data)
    changes, held, additions = [], [], []
    batch_ids = Counter((r.get("tenant_id"), r.get("batch_id")) for r in result.get("MFG-02", []))
    move_ids = Counter((r.get("tenant_id"), r.get("movement_id")) for r in result.get("INV-02", []))
    indexes = {}
    for dataset, field in (("MFG-01", "plan_line_id"), ("MDM-04", "location_id")):
        index = defaultdict(list)
        for row in result.get(dataset, []):
            index[(row.get("tenant_id"), row.get(field))].append(row)
        indexes[dataset] = index
    references = defaultdict(list)
    for line, row in enumerate(result.get("INV-02", []), 2):
        if row.get("movement_type") in {"PRODUCTION_ISSUE", "PRODUCTION_RECEIPT"}:
            references[(row.get("tenant_id"), row.get("reference_id"), row["movement_type"])].append((line, row))

    def one(dataset, tenant, identity):
        rows = indexes[dataset].get((tenant, identity), [])
        if len(rows) != 1:
            raise ProductionInputError("REFERENCE_NOT_UNIQUE")
        return rows[0]

    def movement(rows, batch, item, kind):
        if len(rows) != 1:
            raise ProductionInputError("LEGACY_MOVEMENT_NOT_UNIQUE")
        line, row = rows[0]
        if move_ids[(row.get("tenant_id"), row.get("movement_id"))] != 1 or not row.get("movement_id"):
            raise ProductionInputError("MOVEMENT_ID_CONFLICT")
        if (row.get("scope_node_id") != batch["scope_node_id"]
                or row.get("movement_date") != batch["production_date"] or row.get("reference_type") != "BATCH"
                or row.get("material_id") != item["material_id"] or row.get("quantity_uom") != item["quantity_uom"]):
            raise ProductionInputError("LEGACY_MOVEMENT_CONTEXT")
        if item.get("lot_id") and row.get("lot_id") != item["lot_id"]:
            raise ProductionInputError("LEGACY_MOVEMENT_LOT")
        issue = kind == "PRODUCTION_ISSUE"
        try:
            actual = Decimal(str(row["quantity"]))
            if not actual.is_finite():
                raise ValueError("finite signed quantity required")
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise ProductionInputError("LEGACY_MOVEMENT_QUANTITY") from exc
        if (actual == 0 or (actual < 0) != issue
                or abs(abs(actual) - number(item["quantity"])) > number("0.001")):
            raise ProductionInputError("LEGACY_MOVEMENT_QUANTITY")
        warehouse_field, opposite_field = (("from_location_id", "to_location_id") if issue
                                            else ("to_location_id", "from_location_id"))
        if row.get(opposite_field) != "PRODUCTION":
            raise ProductionInputError("LEGACY_MOVEMENT_ENDPOINT")
        warehouse = one("MDM-04", batch["tenant_id"], row.get(warehouse_field))
        if (warehouse.get("scope_node_id") != batch["scope_node_id"]
                or str(warehouse.get("active")).lower() != "true"):
            raise ProductionInputError("INPUT_WAREHOUSE_UNAVAILABLE")
        return line, row

    for line, batch in enumerate(result.get("MFG-02", []), 2):
        try:
            tenant, batch_id = required(batch, "tenant_id"), required(batch, "batch_id")
            if batch_ids[(tenant, batch_id)] != 1:
                raise ProductionInputError("DUPLICATE_BATCH")
            if modern(batch):
                # 이미 새 형식인 값이 틀리면 재산출로 덮지 않는다.
                verify_model(batch, result.get("MDM-05", []), result.get("MDM-01", []))
                continue
            legacy = input_lines(batch)[0]
            proposed = model_inputs(batch, result.get("MDM-05", []), result.get("MDM-01", []))
            if legacy["material_id"] not in {r["material_id"] for r in proposed}:
                raise ProductionInputError("LEGACY_MATERIAL_OUTSIDE_BOM")
            plan = one("MFG-01", tenant, required(batch, "plan_line_id"))
            if (plan.get("product_id") != batch["output_material_id"] or plan.get("quantity_uom") != batch["quantity_uom"]
                    or plan.get("scope_node_id") != batch["scope_node_id"]):
                raise ProductionInputError("BATCH_PLAN_CONTEXT")
            issue_line, issue = movement(references[(tenant, batch_id, "PRODUCTION_ISSUE")], batch, legacy, "PRODUCTION_ISSUE")
            movement(references[(tenant, batch_id, "PRODUCTION_RECEIPT")], batch,
                     {"material_id": batch["output_material_id"], "quantity_uom": batch["quantity_uom"],
                      "quantity": batch["output_quantity"], "lot_id": batch.get("output_lot_id")}, "PRODUCTION_RECEIPT")
            before = copy.deepcopy(batch)
            updated = {k: v for k, v in batch.items() if k not in (*LEGACY_FIELDS, "scrap_quantity")}
            updated.update(input_contract_version=INPUT_VERSION, input_lines=proposed,
                           input_quantity_basis="SYNTHETIC_BOM_MODEL", scrap_basis="NOT_MODELLED",
                           input_source_fingerprint=fingerprint(before))
            updated = _pending(updated)
            verify_model(updated, result.get("MDM-05", []), result.get("MDM-01", []))
            planned = []
            for item in proposed:
                reuse = item["material_id"] == legacy["material_id"]
                identity = issue["movement_id"] if reuse else f"MOV-INP-{fingerprint([tenant, batch_id, item['input_line_id']])[:20]}"
                if not reuse and move_ids[(tenant, identity)]:
                    raise ProductionInputError("GENERATED_MOVEMENT_ID_CONFLICT")
                revised = _pending({**issue, "movement_id": identity, "input_line_id": item["input_line_id"],
                                    "material_id": item["material_id"], "lot_id": item["lot_id"],
                                    "quantity": "-" + item["quantity"], "quantity_uom": item["quantity_uom"],
                                    "quantity_basis": "SYNTHETIC_BOM_MODEL"})
                if not reuse:
                    for field, prefix in (("record_id", "REC"), ("lineage_id", "LIN")):
                        if field in revised:
                            revised[field] = f"{prefix}-{fingerprint([tenant, identity])[:20]}"
                planned.append((reuse, revised))
            # 여기까지 전부 성공해야 배치와 출고를 함께 바꾼다.
            changes.append({"dataset": "MFG-02", "action": "REBUILD_SYNTHETIC_INPUTS", "line": line,
                            "key": batch_id, "before": before, "after": copy.deepcopy(updated)})
            batch.clear()
            batch.update(updated)
            for reuse, revised in planned:
                changes.append({"dataset": "INV-02", "action": "REPLACE_INPUT_MOVEMENT" if reuse else "ADD_INPUT_MOVEMENT",
                                "line": issue_line if reuse else None, "key": revised["movement_id"],
                                "before": copy.deepcopy(issue) if reuse else None, "after": copy.deepcopy(revised)})
                if reuse:
                    issue.clear()
                    issue.update(revised)
                else:
                    additions.append(revised)
                    move_ids[(tenant, revised["movement_id"])] += 1
        except (ValueError, KeyError, ArithmeticError) as exc:
            held.append({"dataset": "MFG-02", "line": line, "key": batch.get("batch_id"), "reason": str(exc)})
    result.setdefault("INV-02", []).extend(additions)
    return result, {
        "status": "REVIEW_ONLY", "rule_version": RULE_VERSION, "contract_delta": copy.deepcopy(CONTRACT_DELTA),
        "converted_batches": sum(c["dataset"] == "MFG-02" for c in changes),
        "added_input_movements": len(additions), "held_count": len(held),
        "held_counts": dict(Counter(r["reason"] for r in held)), "held": held, "changes": changes,
        "not_verified": ["measured consumption and lot genealogy", "production-plan allocation",
                         "sales allocation and chronology", "stock recalculation", "valuation and postings"],
        "assumptions": ["new synthetic inputs use existing batch input warehouse",
                        "missing input lots receive synthetic identifiers, not certified genealogy",
                        "mass uses recorded yield; EA needs explicit per-good-output count policy",
                        "scrap is not inferred by subtracting unlike materials"],
    }
