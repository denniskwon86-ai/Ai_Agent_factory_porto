"""K1-c6b: two factory connections in fresh local SQLite copies, never installation."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

from core.data_preparation.kit_department_alignment import read_organization, plan_alignment
from core.data_preparation.kit_logistics_revision import fingerprint

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "output/kit-logistics-review-2026-09-10"


def ro(path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def tables(path):
    with closing(ro(path)) as conn:
        conn.execute("BEGIN")
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted(conn.execute('SELECT * FROM "' + name.replace('"', '""') + '"'), key=repr)
                for name in names}


def digest(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()


def backup(source, target):
    deadline = time.monotonic() + 15
    def bounded(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite backup exceeded the checkpoint budget")
    with closing(ro(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst, pages=128, progress=bounded)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup integrity check failed")


def main():
    plan = json.loads((REVIEW / "department-alignment-plan.json").read_text(encoding="utf-8-sig"))
    logistics = json.loads((REVIEW / "candidate.json").read_text(encoding="utf-8-sig"))
    instance = json.loads((ROOT / "data/instance.json").read_text(encoding="utf-8-sig"))
    sources = {"master": ROOT / "data/master/master.db", "ecm": ROOT / "data/enterprise_context.db"}
    organization = read_organization(sources["master"], sources["ecm"])
    if plan_alignment(organization, logistics, instance, as_of=plan["as_of"]) != plan:
        raise ValueError("Source organization/plan changed; review before rehearsal")
    before = {key: tables(path) for key, path in sources.items()}
    instance_bytes = (ROOT / "data/instance.json").read_bytes()
    run = Path(tempfile.mkdtemp(prefix="factory-rehearsal-", dir=REVIEW)).resolve()
    paths = {"master": run / "master/master.db", "ecm": run / "enterprise_context.db"}
    paths["master"].parent.mkdir()

    # In this fresh process even an accidentally imported singleton cannot open
    # installation SQLite for writing. Original reads must use exact read-only URIs.
    read_uris = {p.resolve().as_uri() + "?mode=ro" for p in (*sources.values(), *paths.values())}
    def sqlite_boundary(event, args):
        if event != "sqlite3.connect":
            return
        target = str(args[0])
        if target in read_uris:
            return
        if target.startswith("file:") or not Path(target).resolve().is_relative_to(run):
            raise PermissionError("Rehearsal SQLite writes must stay inside its fresh directory")
    sys.addaudithook(sqlite_boundary)
    for key in sources:
        backup(sources[key], paths[key])
        if tables(paths[key]) != before[key]:
            raise ValueError("Source changed during backup; no connection applied")

    import core.paths
    core.paths.DATA_DIR = str(run)
    from core.enterprise_context.repository import EcmRepository, ecm_repository
    from core.enterprise_context.models import OrganizationNode, OrganizationEdge
    if Path(ecm_repository.db_path).resolve() != paths["ecm"]:
        raise ValueError("Singleton did not bind to rehearsal copy")
    repo = EcmRepository(db_path=str(paths["ecm"]))
    now = datetime.now(timezone.utc).isoformat()
    mapping = []
    for target in plan["factory_targets"]:
        parent = repo.get_node(target["target_parent_node_id"])
        if not parent or parent.tenant_id != plan["target_tenant_id"] or parent.node_type != "business_division":
            raise ValueError("Invalid parent in copied organization")
        node = repo.upsert_node(OrganizationNode(
            entity_id=parent.entity_id, tenant_id=parent.tenant_id, node_type="site_plant",
            name_ko=target["source_name"] + " · 연결 리허설", default_parent_id=parent.node_id,
            status="ACTIVE", effective_from=now))
        edge = repo.add_edge(OrganizationEdge(
            tenant_id=parent.tenant_id, from_node_id=parent.node_id, to_node_id=node.node_id,
            relation_type="OPERATING_PARENT", effective_from=now))
        persisted = repo.get_node(node.node_id)
        if persisted is None or persisted.dept_id or repo.parents(node.node_id, "OPERATING_PARENT") != [parent.node_id]:
            raise ValueError("Factory/parent round-trip verification failed")
        mapping.append({**target, "target_scope_node_id": node.node_id, "edge_id": edge.edge_id,
                        "effective_from": now, "action": "CREATED_IN_ISOLATED_COPY_ONLY",
                        "source_data_origin": "SYNTHETIC", "source_entity_mode": "VIRTUAL"})

    after = tables(paths["ecm"])
    if set(after) != set(before["ecm"]):
        raise ValueError("Unexpected schema table change")
    for name, rows in before["ecm"].items():
        allowed = 2 if name in ("organization_nodes", "organization_edges") else 0
        if not set(rows).issubset(set(after[name])) or len(after[name]) != len(rows) + allowed:
            raise ValueError("Unexpected copied table change: " + name)
    if tables(paths["master"]) != before["master"]:
        raise ValueError("Copied departments/users/roles changed")
    for key, path in sources.items():
        if tables(path) != before[key]:
            raise ValueError("Installation changed during rehearsal; outcome needs recheck")
    if (ROOT / "data/instance.json").read_bytes() != instance_bytes:
        raise ValueError("Installation context changed")
    report = {"schema": "laxs.factory_connection_rehearsal.v1", "status": "COPY_CONNECTION_VERIFIED",
              "installed": False, "created_at": now, "plan_fingerprint": plan["plan_fingerprint"],
              "source_organization_fingerprint": fingerprint(organization),
              "copy_paths": {k: str(p) for k, p in paths.items()}, "mapping": mapping,
              "source_table_fingerprints": {k: digest(v) for k, v in before.items()},
              "copy_table_fingerprints": {"master": digest(tables(paths["master"])), "ecm": digest(after)},
              "checks": {"backup_integrity": True, "new_nodes": 2, "new_edges": 2,
                         "existing_ecm_rows_preserved": True, "departments_users_roles_unchanged": True,
                         "installation_table_rows_unchanged": True, "instance_bytes_unchanged": True},
              "not_verified": ["PDP access", "ownership approval", "certification", "browser"],
              "next": "2-c: access checks using copied departments and real policy; no role grants"}
    report["report_fingerprint"] = fingerprint(report)
    with (run / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "report": str(run / "result.json"),
                      "checks": report["checks"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
