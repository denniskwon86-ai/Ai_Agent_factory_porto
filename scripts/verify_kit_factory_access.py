"""K1-c6c: copied real memberships through product PDP; synthetic resources only.

This is not HTTP authentication, certified-row access, or an ownership approval.
No user or role is created to make a positive control pass.
"""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

from scripts.rehearse_kit_factory_connection import ROOT, REVIEW, tables, digest
from core.data_preparation.kit_logistics_revision import fingerprint

RUN = REVIEW / "factory-rehearsal-7h8jvgww"


def main():
    report = json.loads((RUN / "result.json").read_text(encoding="utf-8"))
    if report["report_fingerprint"] != fingerprint({k: v for k, v in report.items() if k != "report_fingerprint"}):
        raise ValueError("Rehearsal report changed")
    paths = {k: Path(v).resolve() for k, v in report["copy_paths"].items()}
    if any(not p.is_relative_to(RUN.resolve()) for p in paths.values()):
        raise ValueError("Copy path escaped the known rehearsal directory")
    plan = json.loads((REVIEW / "department-alignment-plan.json").read_text(encoding="utf-8"))
    if plan["plan_fingerprint"] != report["plan_fingerprint"] or plan["plan_fingerprint"] != fingerprint({k: v for k, v in plan.items() if k != "plan_fingerprint"}):
        raise ValueError("Parent plan changed")
    before = {k: tables(p) for k, p in paths.items()}
    if {k: digest(v) for k, v in before.items()} != report["copy_table_fingerprints"]:
        raise ValueError("Copied rows changed since connection rehearsal")
    sources = {"master": ROOT / "data/master/master.db", "ecm": ROOT / "data/enterprise_context.db"}
    installation = {k: tables(p) for k, p in sources.items()}
    policy_path = ROOT / "data/scope_policy.json"
    protected = {p: p.read_bytes() for p in (policy_path, ROOT / "data/instance.json")}

    allowed_rw = {str(p) for p in paths.values()}
    allowed_ro = {p.resolve().as_uri() + "?mode=ro" for p in (*paths.values(), *sources.values())}
    def boundary(event, args):
        if event == "sqlite3.connect" and str(args[0]) not in allowed_rw | allowed_ro:
            raise PermissionError("Only the two known copies may be opened for writing")
    sys.addaudithook(boundary)
    import core.paths
    core.paths.DATA_DIR = str(RUN.resolve())
    from core import scope_policy
    scope_policy._POLICY_PATH = str(policy_path)  # Read current policy; do not override its value.
    from core.org_directory import org_directory, _org_enforce_effective
    from core.enterprise_context.repository import ecm_repository
    from core.project_visibility import _scope_is_ancestor
    from core import app_policy as ap
    from api.deps import Principal, visibility_block_reason
    if Path(org_directory.db_path).resolve() != paths["master"] or Path(ecm_repository.db_path).resolve() != paths["ecm"]:
        raise ValueError("Product singletons are not isolated")
    if org_directory.is_bootstrap() or not _org_enforce_effective():
        raise ValueError("Actual policy does not enforce ordinary-user permissions")

    with closing(sqlite3.connect(paths["master"].as_uri() + "?mode=ro", uri=True)) as conn:
        ids = [r[0] for r in conn.execute("SELECT user_id FROM users WHERE status='active' "
               "AND is_admin=0 AND is_executive=0 AND is_data_admin=0 AND is_ai_admin=0 "
               "AND user_id NOT LIKE '%.invalid' ORDER BY user_id")]
    users = [org_directory.get_user(uid) for uid in ids]
    subjects = {}
    for dept in ("procurement", "logistics", "finance"):
        found = [u for u in users if u["primary_dept_id"] == dept and dept in u["roles"]]
        if not found:
            raise ValueError("No existing ordinary user for " + dept)
        u = found[0]
        scope = org_directory.resolve_scope(u["user_id"])
        principal = Principal(user_id=u["user_id"], scope=scope)
        if scope.unrestricted or visibility_block_reason(principal):
            raise ValueError("Cannot use this principal as an ordinary positive control")
        if plan["target_company_node_id"] not in scope.readable_scope_nodes:
            raise ValueError("Selected company is outside this user's registered scope")
        subjects[dept] = ap.Subject(user_id=u["user_id"], scope=scope,
            blocked_reason=visibility_block_reason(principal),
            ctx={"tenant_id": plan["target_tenant_id"], "entity_mode": "REAL",
                 "scope_node_id": plan["target_company_node_id"]})

    mappings = {m["source_scope_node_id"]: m for m in report["mapping"]}
    results, hierarchy = [], []
    for m in mappings.values():
        other = next(v for v in mappings.values() if v != m)
        for parent, expected in ((m["target_parent_node_id"], True), (other["target_parent_node_id"], False)):
            actual, failed = _scope_is_ancestor(parent, m["target_scope_node_id"])
            if failed or actual != expected:
                raise ValueError("Copied factory hierarchy does not match its department")
            hierarchy.append({"factory": m["source_scope_node_id"], "own_division": expected, "matched": True})

    for binding in plan["ownership_targets"]:
        m = mappings[binding["source_scope_node_id"]]
        other = next(v for v in mappings.values() if v != m)
        owner = binding["owner_dept_id"]
        subject = subjects[owner]
        peer = subjects["logistics" if owner == "procurement" else "procurement"]
        # Explicit probe, not a certified binding or persisted data row.
        resource = ap.ResourceScope(tenant_id=plan["target_tenant_id"], entity_mode="REAL",
                    scope_node_id=m["target_scope_node_id"], owner_dept_id=owner)
        cases = [
            ("owner_company_context", subject, resource, True, ap.ALLOW),
            ("other_owner_department", peer, resource, False, ap.DENY_SCOPE),
            ("unrelated_finance", subjects["finance"], resource, False, ap.DENY_SCOPE),
            ("wrong_factory_context", replace(subject, ctx={**subject.ctx, "scope_node_id": other["target_scope_node_id"]}), resource, False, ap.DENY_SCOPE),
            ("old_tenant_context", replace(subject, ctx={**subject.ctx, "tenant_id": plan["source_tenant_id"]}), resource, False, ap.DENY_CONTEXT),
            ("missing_owner_binding", subject, replace(resource, owner_dept_id=""), False, ap.DENY_UNBOUND),
        ]
        for name, who, what, allowed, reason in cases:
            decision = ap.decide(who, what, ap.READ)
            if decision.allowed != allowed or decision.reason != reason:
                raise ValueError("Unexpected PDP outcome: " + binding["dataset_contract_key"] + "/" + name + "/" + decision.reason)
            results.append({"dataset": binding["dataset_contract_key"], "factory": m["source_scope_node_id"],
                            "case": name, "allowed": decision.allowed, "reason": decision.reason})
    for k, p in paths.items():
        if tables(p) != before[k]:
            raise ValueError("Copied organization/users/roles were changed")
    for k, p in sources.items():
        if tables(p) != installation[k]:
            raise ValueError("Installation changed during verification")
    if any(p.read_bytes() != value for p, value in protected.items()):
        raise ValueError("Installation policy/context changed")
    result = {"status": "PASS_SCOPED_POLICY_PROBES", "installed": False,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "parent_report_fingerprint": report["report_fingerprint"],
              "resource_source": "synthetic probes using UNAPPROVED ownership plan, not certified data",
              "subject_source": "existing ordinary users + product resolve_scope + visibility_block_reason",
              "policy_source": "unchanged installation scope_policy.json", "checks": results,
              "hierarchy_checks": hierarchy, "copies_and_installation_rows_unchanged": True,
              "direct_copper_ordinary_member_count": sum("production_copper" in u["roles"] for u in users),
              "not_verified": ["HTTP session authentication", "certified dataset read", "ownership approval", "browser"]}
    result["result_fingerprint"] = fingerprint(result)
    with (RUN / "access-result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": result["status"], "policy_checks": len(results),
                      "allowed": sum(r["allowed"] for r in results), "denied": sum(not r["allowed"] for r in results),
                      "hierarchy_checks": len(hierarchy), "report": str(RUN / "access-result.json"),
                      "direct_copper_ordinary_member_count": result["direct_copper_ordinary_member_count"]}))


if __name__ == "__main__":
    main()
