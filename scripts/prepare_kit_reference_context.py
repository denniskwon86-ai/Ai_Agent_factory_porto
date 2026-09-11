"""Adapt three synthetic reference datasets to one company's rehearsal context.

Supplier scope adaptation is dataset-specific, NOT an identity alias/merger of
the source virtual legal entities. No DB write, certification, or role grant.
"""
from collections import Counter, defaultdict
import json
import sys
from pathlib import Path

from scripts.prepare_kit_purchase_rehearsal import RUN, KIT, verified
from scripts.rehearse_kit_factory_connection import REVIEW, tables, digest
from core.data_preparation.kit_department_alignment import read_organization
from core.data_preparation.kit_procurement_reference_revision import plan_reference_revision, inspect_procurement, IDENTITIES
from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation.kit_logistics_revision import fingerprint

KEYS = ("PRC-01", "MDM-01", "MDM-02")
SUPPLIER_SOURCE_SCOPES = {"org-afs-metals", "org-afs-advanced"}


def remap(source, *, tenant, company, factories, source_tenant):
    """Keep all business fields and rows; preserve origin in the separate change map."""
    result, changes = {}, []
    for key in KEYS:
        result[key] = []
        seen = set()
        for row in source[key]:
            identity = row[IDENTITIES[key]]
            if identity in seen:
                raise ValueError("Duplicate reference key")
            seen.add(identity)
            if row["tenant_id"] != source_tenant or row["data_class"] != "SYNTHETIC" or row["data_origin"] != "SYNTHETIC":
                raise ValueError("Only the known synthetic company input can be adapted")
            scope = row["scope_node_id"]
            if key == "MDM-02":
                if scope not in SUPPLIER_SOURCE_SCOPES:
                    raise ValueError("Unknown supplier source scope")
                target = company
            else:
                if scope not in factories:
                    raise ValueError("Unknown contract/material factory")
                target = factories[scope]
            updated = {**row, "tenant_id": tenant, "scope_node_id": target,
                       "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE"}
            result[key].append(updated)
            changes.append({"dataset": key, "object_id": identity, "source_record_id": row["record_id"],
                "source_lineage_id": row["lineage_id"], "from_tenant": row["tenant_id"], "from_scope": scope,
                "to_tenant": tenant, "to_scope": target,
                "rule": "SYNTHETIC_COMPANY_SUPPLIER_CATALOG" if key == "MDM-02" else "EXISTING_FACTORY_MAPPING"})
    return result, changes


def main():
    def readonly(event, args):
        if event == "sqlite3.connect" and not str(args[0]).endswith("?mode=ro"):
            raise PermissionError("Reference preparation may not write SQLite")
    sys.addaudithook(readonly)
    purchase = verified(RUN / "purchase-preparation.json", "proposal_fingerprint")
    connection = verified(RUN / "result.json", "report_fingerprint")
    plan = verified(REVIEW / "department-alignment-plan.json", "plan_fingerprint")
    if purchase["parent_connection_fingerprint"] != connection["report_fingerprint"] or connection["plan_fingerprint"] != plan["plan_fingerprint"]:
        raise ValueError("Parent artifacts differ")
    paths = {k: Path(p) for k, p in connection["copy_paths"].items()}
    if any(digest(tables(p)) != connection["copy_table_fingerprints"][k] for k, p in paths.items()):
        raise ValueError("Copied organization changed")
    refs = verified(REVIEW / "reference-candidate.json", "proposal_fingerprint")
    if refs != plan_reference_revision(KIT, REVIEW / "candidate.json") or refs["proposal_fingerprint"] != purchase["parent_reference_fingerprint"]:
        raise ValueError("Source reference candidate changed")
    _, data, contracts, files, errors = read_package(KIT, "full")
    if errors:
        raise ValueError("Source kit cannot be read")
    source = {key: refs["candidate_rows"].get(key, data[key]) for key in KEYS}
    org = read_organization(paths["master"], paths["ecm"])
    companies = [n for n in org["nodes"] if n["node_id"] == plan["target_company_node_id"]]
    if len(companies) != 1 or companies[0]["node_type"] != "legal_entity" or companies[0]["tenant_id"] != plan["target_tenant_id"] or companies[0]["status"] != "ACTIVE":
        raise ValueError("Existing company target is not valid")
    source_org = {r["node_id"]: r for r in data["FND-01"]}
    if any(source_org[s]["node_type"] != "LEGAL_ENTITY" or source_org[s]["entity_mode"] != "VIRTUAL" for s in SUPPLIER_SOURCE_SCOPES):
        raise ValueError("Source legal scopes no longer match the synthetic adaptation")
    factories = {m["source_scope_node_id"]: m["target_scope_node_id"] for m in connection["mapping"]}
    candidate, changes = remap(source, tenant=plan["target_tenant_id"], company=plan["target_company_node_id"],
                               factories=factories, source_tenant=plan["source_tenant_id"])
    if {key: len(rows) for key, rows in candidate.items()} != {"PRC-01": 100, "MDM-01": 220, "MDM-02": 40}:
        raise ValueError("Reference population changed")
    reconciliation, _ = inspect_procurement({**candidate, **purchase["candidate_rows"]})
    if any(reconciliation.values()):
        raise ValueError("New-context procurement references do not reconcile")
    materials = {r["material_id"]: r for r in candidate["MDM-01"]}
    contracts_by_id = {r["contract_id"]: r for r in candidate["PRC-01"]}
    for row in candidate["PRC-01"]:
        if row["scope_node_id"] != materials[row["material_id"]]["scope_node_id"]:
            raise ValueError("Contract and material belong to different factories")
    for row in purchase["candidate_rows"]["PRC-02"]:
        if row["scope_node_id"] != contracts_by_id[row["contract_id"]]["scope_node_id"]:
            raise ValueError("Purchase and contract belong to different factories")
    suppliers = {r["supplier_id"]: r for r in source["MDM-02"]}
    used = defaultdict(set)
    matrix = Counter()
    for row in source["PRC-01"]:
        used[row["supplier_id"]].add(row["scope_node_id"])
        matrix[(suppliers[row["supplier_id"]]["scope_node_id"], row["scope_node_id"])] += 1
    report = {"status": "PREPARED_NOT_INSTALLED", "installed": False, "executable": False,
        "candidate_rows": candidate, "candidate_rows_fingerprint": fingerprint(candidate), "changes": changes,
        "parent_purchase_fingerprint": purchase["proposal_fingerprint"], "parent_reference_fingerprint": refs["proposal_fingerprint"],
        "parent_connection_fingerprint": connection["report_fingerprint"],
        "source_files": {key: files[key] for key in (*KEYS, "FND-01")},
        "row_counts": {key: len(rows) for key, rows in candidate.items()},
        "scope_counts": {key: dict(Counter(r["scope_node_id"] for r in rows)) for key, rows in candidate.items()},
        "supplier_adaptation": {"target_scope": plan["target_company_node_id"], "shared_supplier_count": sum(len(s)==2 for s in used.values()),
            "source_contract_scope_matrix": [{"supplier_scope": k[0], "contract_scope": k[1], "count": v} for k, v in sorted(matrix.items())],
            "is_legal_entity_identity_mapping": False, "grants_permissions": False},
        "new_context_reconciliation": reconciliation, "checked_purchase_rows": 1800,
        "other_declared_dependencies": sorted(set(d for key in KEYS for d in contracts[key]["dependencies"]) - set(KEYS)),
        "not_verified": ["all declared dependencies in target context", "reference data ownership authorization", "snapshot certification", "HTTP/browser"],
        "next": "Stage RAW only in copied preparation storage; no source retirement or automatic approvals"}
    report["proposal_fingerprint"] = fingerprint(report)
    with (RUN / "reference-context-preparation.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("status", "row_counts", "scope_counts", "new_context_reconciliation", "other_declared_dependencies", "proposal_fingerprint")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
