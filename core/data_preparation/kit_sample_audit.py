"""Read-only starter-data checks. A pass is NOT certification or simulation readiness.

No store, source registration, migration, or approval is imported here. The existing
generator/validator rewrites assets; this inspector must never do so.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from core.calc_models import BOM_INPUT_ROLES, CalcInputError, material_shortage
from core.calc_projection import PROJECTION_DATASETS, project
from core.data_preparation.business_kits import classify_dataset
from core.data_preparation.kit_quantity_audit import inspect_quantity_flow


def _number(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("missing/invalid number") from exc
    if not result.is_finite():
        raise ValueError("non-finite number")
    return result


def inspect_rows(data: dict[str, list[dict]], contracts: dict[str, dict]) -> list[dict]:
    """Check the supplied file rows, not rows in a live DB. Sample line numbers include header."""
    issues: list[dict] = []

    def issue(code: str, dataset: str, line: int, detail: str):
        issues.append(dict(code=code, dataset=dataset, line=line, detail=detail))

    for key, contract in contracts.items():
        rows = data.get(key, [])
        if not rows:
            issue("EMPTY_DATASET", key, 1, "No readable rows; empty is not ready")
        fields = contract["schema"]["fields"]
        required = [f["name"] for f in fields if f.get("required")]
        keys = contract["business_keys"]
        seen = set()
        for line, row in enumerate(rows, 2):
            missing = [field for field in required if not str(row.get(field) or "").strip()]
            if missing:
                issue("REQUIRED_VALUE", key, line, ", ".join(missing))
            identity = (row.get("tenant_id"), *(row.get(field) for field in keys))
            if identity in seen:
                issue("DUPLICATE_BUSINESS_KEY", key, line, "Duplicate tenant + declared business key")
            seen.add(identity)
            if row.get("data_class") != "SYNTHETIC" or row.get("data_origin") != "SYNTHETIC":
                issue("SAMPLE_PROVENANCE", key, line, "Starter sample must remain explicitly synthetic")

    # Including tenant prevents a same-named object in another company from satisfying a reference.
    def lookup(dataset: str, field: str):
        grouped = defaultdict(list)
        for row in data.get(dataset, []):
            grouped[(row.get("tenant_id"), row.get(field))].append(row)
        return grouped

    references = [
        ("PRC-01", "supplier_id", "MDM-02", "supplier_id"),
        ("PRC-01", "material_id", "MDM-01", "material_id"),
        ("PRC-02", "contract_id", "PRC-01", "contract_id"),
        ("PRC-02", "material_id", "MDM-01", "material_id"),
        ("PRC-02", "supplier_id", "MDM-02", "supplier_id"),
        ("LOG-02", "po_line_id", "PRC-02", "po_line_id"),
        ("LOG-03", "shipment_id", "LOG-02", "shipment_id"),
        ("INV-01", "material_id", "MDM-01", "material_id"),
        ("INV-01", "location_id", "MDM-04", "location_id"),
        ("MDM-05", "input_material_id", "MDM-01", "material_id"),
        ("MDM-05", "output_material_id", "MDM-01", "material_id"),
        ("MFG-01", "product_id", "MDM-01", "material_id"),
        ("SLS-01", "product_id", "MDM-01", "material_id"),
        ("SLS-01", "customer_id", "MDM-03", "customer_id"),
    ]
    for source, field, target, target_field in references:
        targets = lookup(target, target_field)
        for line, row in enumerate(data.get(source, []), 2):
            matches = targets.get((row.get("tenant_id"), row.get(field)), [])
            if len(matches) != 1:
                issue("REFERENCE_NOT_UNIQUE", source, line, f"{field} -> {target}.{target_field}: {len(matches)} matches")

    org = lookup("FND-01", "node_id")
    for key, rows in data.items():
        for line, row in enumerate(rows, 2):
            if len(org.get((row.get("tenant_id"), row.get("scope_node_id")), [])) != 1:
                issue("SCOPE_REFERENCE", key, line, "Scope not uniquely present in this tenant's organization sample")

    purchase_contracts = lookup("PRC-01", "contract_id")
    for line, po in enumerate(data.get("PRC-02", []), 2):
        matches = purchase_contracts.get((po.get("tenant_id"), po.get("contract_id")), [])
        if len(matches) == 1:
            for field in ("material_id", "supplier_id", "quantity_uom", "currency"):
                if po.get(field) != matches[0].get(field):
                    issue("PO_CONTRACT_MISMATCH", "PRC-02", line, field)

    # Compare ALL partial shipments, not each shipment independently against the whole order.
    orders = lookup("PRC-02", "po_line_id")
    shipped: dict[tuple, Decimal] = defaultdict(Decimal)
    for line, row in enumerate(data.get("LOG-02", []), 2):
        key = (row.get("tenant_id"), row.get("po_line_id"))
        matches = orders.get(key, [])
        if len(matches) != 1:
            continue  # the broken join has already been reported above
        po = matches[0]
        try:
            quantity, ordered = _number(row.get("shipment_quantity")), _number(po.get("order_quantity"))
            if quantity < 0 or ordered < 0:
                raise ValueError("negative shipment/order quantity")
            if not row.get("quantity_uom") or row.get("quantity_uom") != po.get("quantity_uom"):
                issue("SHIPMENT_UNIT", "LOG-02", line, "No approved unit conversion applied")
                continue
            shipped[key] += quantity
            if shipped[key] > ordered:
                issue("SHIPMENT_TOTAL_EXCEEDS_ORDER", "LOG-02", line, f"{shipped[key]} > {ordered}")
        except ValueError as exc:
            issue("SHIPMENT_NUMBER", "LOG-02", line, str(exc))

    # Use the product's actual projection + BOM reconciliation, separately per plan.
    # Zero available quantities below are diagnostic inputs only. Never publish its calculated
    # production/shortage outputs: this is NOT a forecast, approved execution, or full-path run.
    for line, plan in enumerate(data.get("MFG-01", []), 2):
        bom = [b for b in data.get("MDM-05", [])
               if b.get("tenant_id") == plan.get("tenant_id")
               and b.get("scope_node_id") == plan.get("scope_node_id")
               and b.get("output_material_id") == plan.get("product_id")
               and str(b.get("effective_from") or "") <= str(plan.get("plan_date") or "")
               and str(plan.get("plan_date") or "") <= str(b.get("effective_to") or "")]
        inputs = [b for b in bom if b.get("component_role") in BOM_INPUT_ROLES]
        if not inputs:
            issue("BOM_NOT_BOUND", "MFG-01", line, "No effective input BOM in the same tenant/scope")
            continue
        if len({b.get("bom_id") for b in inputs}) != 1:
            issue("BOM_AMBIGUOUS", "MFG-01", line, "Multiple effective BOMs; do not sum alternative versions")
            continue
        if any(not plan.get("quantity_uom") or b.get("input_uom") != plan.get("quantity_uom")
               or b.get("output_uom") != plan.get("quantity_uom") for b in inputs):
            issue("BOM_UNIT", "MFG-01", line, "Cannot reconcile mixed units without an approved conversion")
            continue
        if plan.get("material_requirement") in (None, ""):
            issue("BOM_STORED_REQUIREMENT_MISSING", "MFG-01", line, "No stored amount to reconcile")
            continue
        datasets = {key: [] for key in PROJECTION_DATASETS}
        datasets.update({"MFG-01": [plan], "MDM-05": inputs})
        try:
            projected = project(datasets)
            material_shortage(
                inventory=[], production_plan=projected["production_plan"], bom=projected["bom"],
                as_of=plan["plan_date"],
                arrival={"metrics": {"available_quantity": {b["input_material_id"]: 0 for b in inputs}}})
        except (CalcInputError, ValueError, KeyError, ArithmeticError) as exc:
            issue("BOM_PRODUCT_RECONCILIATION", "MFG-01", line, str(exc))

    balances: dict[tuple, Decimal] = defaultdict(Decimal)
    for line, row in enumerate(data.get("FIN-03", []), 2):
        key = (row.get("tenant_id"), row.get("document_id"), row.get("currency"))
        try:
            balances[key] += _number(row.get("debit_amount")) - _number(row.get("credit_amount"))
        except ValueError as exc:
            issue("LEDGER_NUMBER", "FIN-03", line, str(exc))
    for key, delta in balances.items():
        if abs(delta) > Decimal("0.01"):
            issue("LEDGER_UNBALANCED", "FIN-03", 0, f"document={key[1]}, currency={key[2]}, delta={delta}")
    return issues


def read_package(root: Path, profile: str = "quick") -> tuple:
    """Parse the same bytes fingerprinted; no DB or source writes."""
    if profile not in {"quick", "full"}:
        raise ValueError("profile must be quick or full")
    root = root.resolve(strict=True)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8-sig"))
    entries = manifest["datasets"]
    if not entries or len({entry["dataset_id"] for entry in entries}) != len(entries):
        raise ValueError("manifest datasets must be nonempty and unique")
    data, contracts, files, read_errors = {}, {}, {}, []
    for entry in entries:
        key = entry["dataset_id"]
        if not isinstance(key, str) or not key or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in key):
            raise ValueError("invalid dataset identifier in manifest")
        try:
            contracts[key] = json.loads((root / "contracts" / f"{key}.contract.json").read_text(encoding="utf-8-sig"))
            path = root / "samples" / profile / f"{key}.csv"
            raw = path.read_bytes()
            files[key] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            # Parse exactly the bytes fingerprinted, not a second read that could have changed.
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("missing or duplicate CSV headers")
            expected = {f["name"] for f in contracts[key]["schema"]["fields"] if f.get("required")}
            if not expected.issubset(reader.fieldnames):
                raise ValueError(f"missing headers: {sorted(expected - set(reader.fieldnames))}")
            data[key] = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in data[key]):
                raise ValueError("CSV row width differs from its header")
        except (OSError, UnicodeError, ValueError, KeyError, csv.Error) as exc:
            data[key] = []
            read_errors.append(dict(code="UNREADABLE_ASSET", dataset=key, line=0, detail=str(exc)))
    return manifest, data, contracts, files, read_errors


def audit_package(root: Path, profile: str = "quick") -> dict:
    """Read explicit starter assets only; no DB or source writes."""
    manifest, data, contracts, files, read_errors = read_package(root, profile)
    quantity_flow = inspect_quantity_flow(data)
    issues = read_errors + inspect_rows(data, contracts) + quantity_flow["issues"]
    grouped = Counter(classify_dataset(key)["business_kit_id"] for key in data)
    examples = defaultdict(list)
    for item in issues:
        if len(examples[item["code"]]) < 3:
            examples[item["code"]].append(item)
    return {
        "status": "FAIL" if issues else "PASS_CHECKED_SCOPE",
        "profile": profile, "kit_id": manifest["kit_id"], "version": manifest["version"],
        "dataset_count": len(manifest["datasets"]), "business_area_dataset_counts": dict(grouped),
        "rows": {key: len(rows) for key, rows in data.items()}, "files": files,
        "issue_count": len(issues), "issue_counts": dict(Counter(i["code"] for i in issues)),
        "issue_examples": dict(examples),
        "quantity_flow": {k: v for k, v in quantity_flow.items() if k != "issues"},
        "not_verified": ["live database bindings and certification", "permissions and browser journey",
                         "full enterprise profit/cash model", "DART/ECOS actual-source reconciliation",
                         "actual BOM consumption and lot genealogy", "production-to-sales approved allocation"],
        "notice": "Read-only sample inspection; no registration, approval or certification performed.",
    }
