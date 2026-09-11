"""Prepare 1,800 purchase rows for the copied factory context. No DB writes/approvals."""
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

from core.data_preparation.kit_logistics_revision import fingerprint
from core.data_preparation.kit_procurement_reference_revision import plan_reference_revision, inspect_procurement
from core.data_preparation.kit_sample_audit import read_package
from scripts.rehearse_kit_factory_connection import ROOT, REVIEW, tables, digest

RUN = REVIEW / "factory-rehearsal-7h8jvgww"
KIT = ROOT / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"


def verified(path, field):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value[field] != fingerprint({k: v for k, v in value.items() if k != field}):
        raise ValueError("Artifact fingerprint mismatch: " + path.name)
    return value


def main():
    def read_only_sqlite(event, args):
        if event == "sqlite3.connect" and not str(args[0]).endswith("?mode=ro"):
            raise PermissionError("Preparation cannot write SQLite")
    sys.addaudithook(read_only_sqlite)
    connection = verified(RUN / "result.json", "report_fingerprint")
    access = verified(RUN / "access-result.json", "result_fingerprint")
    plan = verified(REVIEW / "department-alignment-plan.json", "plan_fingerprint")
    if access["parent_report_fingerprint"] != connection["report_fingerprint"] or connection["plan_fingerprint"] != plan["plan_fingerprint"]:
        raise ValueError("Rehearsal parents differ")
    for key, path in connection["copy_paths"].items():
        if digest(tables(Path(path))) != connection["copy_table_fingerprints"][key]:
            raise ValueError("Copied organization changed")
    refs = json.loads((REVIEW / "reference-candidate.json").read_text(encoding="utf-8"))
    if refs != plan_reference_revision(KIT, REVIEW / "candidate.json"):
        raise ValueError("Reference candidate differs from current source")
    logistics = verified(REVIEW / "candidate.json", "proposal_fingerprint")
    _, data, _, files, errors = read_package(KIT, "full")
    if errors:
        raise ValueError("Source kit cannot be read")
    reference_data = {**data, **logistics["candidate_rows"], **refs["candidate_rows"]}
    reference_counts, _ = inspect_procurement(reference_data)
    if any(reference_counts.values()):
        raise ValueError("Reference reconciliation did not pass")
    source = logistics["candidate_rows"]["PRC-02"]
    mapping = {m["source_scope_node_id"]: m["target_scope_node_id"] for m in connection["mapping"]}
    candidate = [{**r, "tenant_id": plan["target_tenant_id"], "scope_node_id": mapping[r["scope_node_id"]]} for r in source]
    if len(candidate) != 1800 or len({r["po_line_id"] for r in candidate}) != 1800:
        raise ValueError("Expected complete 1,800-row purchase population")
    for old, new in zip(source, candidate):
        if {k for k in old if old[k] != new[k]} != {"tenant_id", "scope_node_id"}:
            raise ValueError("Unexpected change outside context columns")
        if new["data_origin"] != "SYNTHETIC" or new["certification_status"] != "UNVERIFIED_CANDIDATE":
            raise ValueError("Candidate must remain synthetic and uncertified")
    db = ROOT / "data/data_preparation.db"
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        snapshots = [dict(r) for r in conn.execute("SELECT snapshot_id,dataset_contract_key,tenant_id,scope_node_id,entity_mode,state,row_count,checksum FROM dataset_snapshots WHERE dataset_contract_key IN ('PRC-01','PRC-02','MDM-01','MDM-02')")]
        ownership = [dict(r) for r in conn.execute("SELECT tenant_id,entity_mode,scope_node_id,owner_dept_id,status FROM dataset_ownership_bindings WHERE dataset_contract_key='PRC-02'")]
    inventory = {key: {"rows": len(reference_data[key]),
                      "source_scopes": dict(Counter(r["scope_node_id"] for r in reference_data[key])),
                      "unmapped_source_scopes": sorted({r["scope_node_id"] for r in reference_data[key]} - set(mapping))}
                 for key in ("PRC-01", "MDM-01", "MDM-02")}
    report = {"status": "PREPARED_NOT_INSTALLED", "installed": False, "executable": False,
              "candidate_rows": {"PRC-02": candidate}, "candidate_rows_fingerprint": fingerprint(candidate),
              "row_count": len(candidate), "scope_counts": dict(Counter(r["scope_node_id"] for r in candidate)),
              "changed_columns": ["tenant_id", "scope_node_id"],
              "parent_connection_fingerprint": connection["report_fingerprint"],
              "parent_access_fingerprint": access["result_fingerprint"],
              "parent_logistics_fingerprint": logistics["proposal_fingerprint"],
              "parent_reference_fingerprint": refs["proposal_fingerprint"],
              "source_files": {k: files[k] for k in ("PRC-01", "PRC-02", "MDM-01", "MDM-02")},
              "source_context_reference_counts": reference_counts, "reference_inventory": inventory,
              "observed_snapshots": snapshots, "observed_ownership": ownership,
              "ownership_requests": [{"dataset_contract_key": "PRC-02", "tenant_id": plan["target_tenant_id"],
                  "entity_mode": "REAL", "scope_node_id": target, "owner_dept_id": "procurement",
                  "approval_event_id": None, "effective_from": None} for target in mapping.values()],
              "strategy": "new context instance/bindings/snapshots; preserve old snapshots, NOT replace_demo_snapshot",
              "blocks": ["reference data must be mapped/certified in target context",
                         "MDM-02 supplier scopes require an explicit non-factory mapping",
                         "two new-context purchase ownership approvals are not issued",
                         "copied preparation/ledger stores and RAW lineage are not yet staged"],
              "certification_caveat": "certify_demo can index without owner; resulting RESOURCE_UNBOUND is not readiness",
              "not_verified": ["target-context reference reconciliation", "ledger authorization", "certification", "browser"]}
    report["proposal_fingerprint"] = fingerprint(report)
    with (RUN / "purchase-preparation.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("status", "row_count", "scope_counts", "source_context_reference_counts", "reference_inventory", "proposal_fingerprint")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
