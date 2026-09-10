"""합성 후보의 명시적 질량 환산·이동원장 재산출. 실제 데이터/DB에는 적용하지 않는다.

재고 산술의 대사는 생산 투입 모델 검증이 아니다. EA를 질량으로 바꾸거나,
음수 재고를 감추려고 기초재고·입고·출고 시점을 만들어 넣지 않는다.
"""
from __future__ import annotations

import copy
import hashlib
import json
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from core.calc_models import BOM_INPUT_ROLES
from core.data_preparation.kit_quantity_audit import MOVEMENT_RULES, inspect_quantity_flow
from core.data_preparation.production_inputs import input_lines, modern, verify_model

RULE_VERSION = "explicit-mass-conversion-and-ledger-rebuild/1"
MASS_UNITS = {"TON", "KG", "G"}
MASS_KG = {"TON": Decimal("1000"), "KG": Decimal("1"), "G": Decimal("0.001")}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _number(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_NUMBER") from exc
    if not number.is_finite():
        raise ValueError("NONFINITE_NUMBER")
    return number


def _stored(number):
    # 환산 결과의 소수 부분을 조용히 버리지 않는다. 저장 정밀도 초과는 보류한다.
    rounded = number.quantize(Decimal("0.001"))
    if rounded != number:
        raise ValueError("CONVERSION_PRECISION_LOSS")
    return format(rounded, "f")


def _index(rows, field):
    result = defaultdict(list)
    for row in rows:
        result[(row.get("tenant_id"), row.get(field))].append(row)
    return result


def _one(index, tenant, identity):
    if not tenant or not identity or len(index.get((tenant, identity), [])) != 1:
        raise ValueError("REFERENCE_NOT_UNIQUE")
    return index[(tenant, identity)][0]


def _factor(references, tenant, source, target, when):
    if source == target:
        return Decimal(1), None
    if source not in MASS_UNITS or target not in MASS_UNITS:
        raise ValueError("NO_COUNT_MASS_CONVERSION")
    candidates = []
    for row in references:
        if row.get("tenant_id") != tenant or row.get("reference_type") != "CONVERSION":
            continue
        if row.get("unit") not in {f"{target}/{source}", f"{source}/{target}"}:
            continue
        effective = date.fromisoformat(row["effective_date"])
        if effective <= when:
            candidates.append((effective, row))
    if not candidates:
        raise ValueError("NO_EFFECTIVE_CONVERSION")
    latest = max(effective for effective, _ in candidates)
    selected = [row for effective, row in candidates if effective == latest]
    if len(selected) != 1:
        raise ValueError("AMBIGUOUS_CONVERSION")
    ref = selected[0]
    factor = _number(ref.get("value"))
    if factor <= 0:
        raise ValueError("INVALID_CONVERSION_FACTOR")
    if ref["unit"] == f"{source}/{target}":
        factor = Decimal(1) / factor
    if factor != MASS_KG[source] / MASS_KG[target]:
        raise ValueError("CONVERSION_FACTOR_CONFLICTS_WITH_UNIT")
    return factor, ref


def _pending(row):
    return {**row, "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE"}


def inspect_batch_input_contract(data):
    """현행 단일 투입 배치가 유효 BOM을 표현하는지 검사. 산식/기록을 추정하지 않는다."""
    materials = _index(data.get("MDM-01", []), "material_id")
    findings = []
    recipes = defaultdict(list)
    for row in data.get("MDM-05", []):
        recipes[(row.get("tenant_id"), row.get("scope_node_id"), row.get("output_material_id"))].append(row)
    for line, batch in enumerate(data.get("MFG-02", []), 2):
        try:
            if modern(batch):
                verify_model(batch, data.get("MDM-05", []), data.get("MDM-01", []))
                continue
            when = date.fromisoformat(batch["production_date"])
            selected = [b for b in recipes[(batch.get("tenant_id"), batch.get("scope_node_id"), batch.get("output_material_id"))]
                        if date.fromisoformat(b["effective_from"]) <= when <= date.fromisoformat(b["effective_to"])
                        and b.get("component_role") in BOM_INPUT_ROLES]
            if not selected:
                raise ValueError("NO_EFFECTIVE_INPUT_BOM")
            if len({b.get("bom_id") for b in selected}) != 1:
                raise ValueError("AMBIGUOUS_INPUT_BOM")
            if len({b.get("input_material_id") for b in selected}) > 1:
                raise ValueError("MULTI_INPUT_NOT_REPRESENTABLE")
            for bom in selected:
                master = _one(materials, batch.get("tenant_id"), bom.get("input_material_id"))
                if bom.get("input_uom") != master.get("base_uom"):
                    raise ValueError("BOM_MASTER_UNIT_MISMATCH")
                if batch.get("input_material_id") != bom.get("input_material_id"):
                    raise ValueError("BATCH_INPUT_DIFFERS_FROM_BOM")
        except (ValueError, KeyError) as exc:
            findings.append({"dataset": "MFG-02", "line": line, "key": batch.get("batch_id"), "reason": str(exc)})
    return {"issue_count": len(findings), "issue_counts": dict(Counter(f["reason"] for f in findings)),
            "issues": findings, "not_verified": ["actual input quantities and yields", "production-to-sales allocation"]}


def rebuild_stock_candidate(data, *, stock_reference=None):
    """입력의 사본과 검토 명세를 반환한다. 원본·인증·저장소를 변경하지 않는다."""
    stock_reference = stock_reference or []
    if any(r.get("data_class") != "SYNTHETIC" or r.get("data_origin") != "SYNTHETIC"
           for rows in [*data.values(), stock_reference] for r in rows):
        raise ValueError("SYNTHETIC_ONLY")
    candidate = copy.deepcopy(data)
    changes, held = [], []
    masters = _index(candidate.get("MDM-01", []), "material_id")
    stores = _index(candidate.get("MDM-04", []), "location_id")
    refs = candidate.get("FND-03", [])
    move_ids = _index(candidate.get("INV-02", []), "movement_id")

    # 독립 재고조정만 환산한다. 구매·생산·판매 수량은 출처 자료와 함께 바꿔야 한다.
    for line, row in enumerate(candidate.get("INV-02", []), 2):
        if row.get("movement_type") != "CYCLE_COUNT_ADJUSTMENT":
            continue
        try:
            master = _one(masters, row.get("tenant_id"), row.get("material_id"))
            target = master.get("base_uom")
            if target == row.get("quantity_uom"):
                continue
            _one(move_ids, row.get("tenant_id"), row.get("movement_id"))
            store = _one(stores, row.get("tenant_id"), row.get("to_location_id"))
            if (store.get("scope_node_id") != row.get("scope_node_id")
                    or str(store.get("active")).lower() != "true"
                    or row.get("from_location_id") != "ADJUSTMENT" or row.get("reference_type") != "CYCLE_COUNT"):
                raise ValueError("INVALID_ADJUSTMENT_CONTEXT")
            factor, ref = _factor(refs, row["tenant_id"], row.get("quantity_uom"), target,
                                  date.fromisoformat(row["movement_date"]))
            quantity = _number(row.get("quantity"))
            if quantity == 0:
                raise ValueError("ZERO_ADJUSTMENT")
            before = copy.deepcopy(row)
            row.update(_pending({**row, "quantity": _stored(quantity * factor), "quantity_uom": target}))
            changes.append({"dataset": "INV-02", "action": "CONVERT_QUANTITY_AND_UNIT", "line": line,
                            "key": row["movement_id"], "before": before, "after": copy.deepcopy(row),
                            "factor": str(factor), "reference": ref, "reference_fingerprint": _hash(ref)})
        except (ValueError, KeyError, ArithmeticError) as exc:
            held.append({"dataset": "INV-02", "line": line, "key": row.get("movement_id"), "reason": str(exc)})

    audit = inspect_quantity_flow(candidate)
    blocked_materials, global_blockers = set(), []
    # 잘못된 이동을 빼고 합계를 맞추지 않는다. 품목을 특정 못 하는 결함은 전체 보류.
    fields = {"INV-02": ("material_id",), "MDM-01": ("material_id",),
              "MFG-02": ("input_material_id", "output_material_id"), "SLS-01": ("product_id",),
              "PRC-02": ("material_id",), "MFG-01": ("product_id",)}
    derived_errors = {"Q_UNIT", "Q_NEGATIVE_STOCK", "Q_STOCK_BALANCE", "Q_SNAPSHOT_MISSING"}
    for issue in audit["issues"]:
        dataset, line = issue["dataset"], issue["line"]
        if dataset == "INV-01" and issue["code"] in derived_errors:
            continue
        if dataset not in fields or not 2 <= line < len(candidate.get(dataset, [])) + 2:
            global_blockers.append(issue)
            continue
        row = candidate[dataset][line - 2]
        identities = [row.get(field) for field in fields[dataset]]
        if dataset == "MFG-02" and modern(row):
            try:
                identities = [row.get("output_material_id"), *(r["material_id"] for r in input_lines(row))]
            except (ValueError, KeyError):
                identities = []
                global_blockers.append(issue)
                continue
        if not row.get("tenant_id") or not all(identities):
            global_blockers.append(issue)
        else:
            blocked_materials.update((row["tenant_id"], identity) for identity in identities)
    timelines = defaultdict(list)
    for row in candidate.get("INV-02", []):
        if global_blockers or (row.get("tenant_id"), row.get("material_id")) in blocked_materials:
            continue
        field = MOVEMENT_RULES[row["movement_type"]][0]
        bucket = (row["tenant_id"], row["scope_node_id"], row["material_id"], row[field], row["quantity_uom"])
        timelines[bucket].append(row)
    prefixes, evidence, shortages = {}, [], []
    for bucket, rows in sorted(timelines.items()):
        daily = defaultdict(list)
        for row in rows:
            daily[row["movement_date"]].append(row)
        days, balances, balance, low, first = [], [], Decimal(0), Decimal(0), None
        for day, events in sorted(daily.items()):
            opening = balance
            balance += sum((_number(r["quantity"]) for r in events), Decimal(0))
            days.append(day)
            balances.append(balance)
            if balance < 0 and first is None:
                first = {"date": day, "balance_before_day": str(opening), "balance_after_day": str(balance),
                         "movements": [{"id": r["movement_id"], "type": r["movement_type"], "quantity": r["quantity"]}
                                       for r in sorted(events, key=lambda r: r["movement_id"])]}
            low = min(low, balance)
        proof = _hash(sorted(rows, key=lambda r: (r["movement_date"], r["movement_id"])))
        prefixes[bucket] = (days, balances, proof)
        evidence.append({"bucket": list(bucket), "movement_count": len(rows), "fingerprint": proof})
        if first:
            shortages.append({"bucket": list(bucket), "first_shortfall": first, "minimum_daily_balance": str(low),
                              "additional_quantity_applied": "0", "basis": "recorded_movements_only"})

    snapshots = candidate.get("INV-01", [])
    existing = _index(snapshots, "snapshot_id")
    calendar = defaultdict(set)
    occupied = set()
    references = defaultdict(list)
    for row in stock_reference:
        references[(row.get("tenant_id"), row.get("scope_node_id"), row.get("material_id"),
                    row.get("location_id"), row.get("snapshot_date"))].append(row)
    for row in snapshots:
        calendar[(row.get("tenant_id"), row.get("scope_node_id"))].add(row.get("snapshot_date"))
        occupied.add((row.get("tenant_id"), row.get("scope_node_id"), row.get("material_id"),
                      row.get("location_id"), row.get("snapshot_date")))
    pending = [(line, row, False, None) for line, row in enumerate(snapshots, 2)]
    # 새 창고도 기존 회사·조직 달력 안에서만. 안전재고 정책은 그 창고의 full 행으로 증명한다.
    for bucket in sorted(prefixes):
        tenant, scope, material, location, unit = bucket
        for day in sorted(calendar[(tenant, scope)]):
            if (tenant, scope, material, location, day) in occupied:
                continue
            matches = references[(tenant, scope, material, location, day)]
            if len(matches) != 1:
                held.append({"dataset": "INV-01", "key": list(bucket), "reason": "NEW_WAREHOUSE_POLICY_UNBOUND"})
                continue
            template = copy.deepcopy(matches[0])
            identity = template.get("snapshot_id")
            if not identity or (tenant, identity) in existing:
                held.append({"dataset": "INV-01", "key": identity, "reason": "NEW_SNAPSHOT_ID_COLLISION"})
                continue
            pending.append((None, template, True, _hash(matches[0])))

    rebuilt = 0
    for line, row, added, template_proof in pending:
        try:
            tenant, scope, material = row.get("tenant_id"), row.get("scope_node_id"), row.get("material_id")
            master = _one(masters, tenant, material)
            if global_blockers or (tenant, material) in blocked_materials:
                raise ValueError("UPSTREAM_MOVEMENTS_UNRESOLVED")
            if not added:
                _one(existing, tenant, row.get("snapshot_id"))
            store = _one(stores, tenant, row.get("location_id"))
            if store.get("scope_node_id") != scope or str(store.get("active")).lower() != "true":
                raise ValueError("INVALID_SNAPSHOT_WAREHOUSE")
            if row.get("lot_id") != "ALL" or any(_number(row.get(f)) != 0 for f in ("quality_quantity", "blocked_quantity")):
                raise ValueError("STOCK_COMPARTMENT_ALLOCATION_UNBOUND")
            when = date.fromisoformat(row["snapshot_date"])
            target = master["base_uom"]
            factor, ref = _factor(refs, tenant, row.get("quantity_uom"), target, when)
            safety = _number(row.get("safety_stock_quantity"))
            if safety < 0:
                raise ValueError("NEGATIVE_SAFETY_POLICY")
            bucket = (tenant, scope, material, row["location_id"], target)
            days, balances, proof = prefixes.get(bucket, ([], [], _hash([])))
            pos = bisect_right(days, when.isoformat()) - 1
            quantity = balances[pos] if pos >= 0 else Decimal(0)
            result = {**row, "unrestricted_quantity": _stored(quantity), "quantity_uom": target,
                      "safety_stock_quantity": _stored(safety * factor)}
            rebuilt += 1
            if (not added and result["quantity_uom"] == row.get("quantity_uom")
                    and all(_number(result[k]) == _number(row.get(k))
                            for k in ("unrestricted_quantity", "safety_stock_quantity"))):
                continue
            before = None if added else copy.deepcopy(row)
            row.update(_pending(result))
            if added:
                snapshots.append(row)
            changes.append({"dataset": "INV-01", "action": "ADD_DERIVED_STOCK" if added else "REBUILD_FROM_MOVEMENTS",
                            "line": line, "key": row["snapshot_id"], "before": before, "after": copy.deepcopy(row),
                            "bucket": list(bucket), "source_movement_fingerprint": proof,
                            "reference_stock_fingerprint": template_proof,
                            "policy_conversion_fingerprint": _hash(ref) if ref else None})
        except (ValueError, KeyError, ArithmeticError) as exc:
            held.append({"dataset": "INV-01", "line": line, "key": row.get("snapshot_id"), "reason": str(exc)})
    input_model = inspect_batch_input_contract(candidate)
    final_quantity = inspect_quantity_flow(candidate)
    return candidate, {"rule_version": RULE_VERSION, "status": "REVIEW_ONLY", "changes": changes, "held": held,
                       "change_counts": dict(Counter(c["action"] for c in changes)),
                       "rebuilt_snapshot_count": rebuilt, "blocked_material_count": len(blocked_materials),
                       "global_blockers": global_blockers, "stock_inputs": evidence, "shortages": shortages,
                       "production_input_contract": input_model,
                       "remaining_quantity_issue_count": final_quantity["issue_count"],
                       "not_verified": ["opening stock against a previous certified period", "within-day movement order",
                                        "physical inventory observation", "consumption quantities/yield and financial valuation"],
                       "candidate_check": "FAIL" if (held or global_blockers or shortages or input_model["issue_count"]
                                                     or final_quantity["status"] != "PASS_CHECKED_SCOPE") else "PASS_CHECKED_SCOPE"}
