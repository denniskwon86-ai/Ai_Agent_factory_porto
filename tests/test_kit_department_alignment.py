"""부서 기반 전환 계획의 보호 조건. 실제 권한·설치 완료를 증명하는 시험은 아니다."""
import copy
import hashlib
import sqlite3

import pytest

from core.data_preparation.kit_department_alignment import plan_alignment, read_organization
from core.data_preparation.kit_logistics_revision import KEYS, fingerprint

WHEN = "2026-09-10T00:00:00+00:00"


@pytest.fixture
def inputs():
    depts = []
    nodes = []
    for did, nid in (("hq", "company"), ("procurement", "company"), ("logistics", "company"),
                     ("production_copper", "copper"), ("production_battery", "battery")):
        depts.append(dict(dept_id=did, name_ko=did, scope_node_id=nid, parent_id="hq" if did != "hq" else "",
                          version=1, valid_to=None, status="active"))
    for nid, kind, tenant, parent in (("company", "legal_entity", "existing", ""),
            ("copper", "business_division", "existing", "company"),
            ("battery", "business_division", "existing", "company"),
            ("plant-afs-smelting-01", "site_plant", "kit", ""),
            ("plant-afs-battery-02", "site_plant", "kit", "")):
        nodes.append(dict(node_id=nid, name_ko=nid, entity_id=tenant, tenant_id=tenant,
                          node_type=kind, default_parent_id=parent, status="ACTIVE"))
    org = dict(departments=depts, nodes=nodes,
               entities=[dict(entity_id=t, tenant_id=t, entity_mode="REAL", status="ACTIVE") for t in ("existing", "kit")],
               edges=[dict(tenant_id="existing", from_node_id="company", to_node_id=n, relation_type="OPERATING_PARENT",
                           status="ACTIVE", effective_from="", effective_to="") for n in ("copper", "battery")])
    rows = {key: [dict(tenant_id="kit", scope_node_id=scope, data_class="SYNTHETIC", data_origin="SYNTHETIC",
                      **{identity: str(i)}) for i, scope in enumerate(("plant-afs-smelting-01", "plant-afs-battery-02"))]
            for key, identity in KEYS.items()}
    parent = dict(status="REVIEW_ONLY", installed=False, candidate_check="PASS_CHECKED_SCOPE",
                  candidate_rows=rows, candidate_rows_fingerprint=fingerprint(rows))
    parent["proposal_fingerprint"] = fingerprint(parent)
    return org, parent, dict(tenant_id="kit")


def plan(inputs, **kw):
    return plan_alignment(*inputs, as_of=kw.get("as_of", WHEN))


def test_existing_departments_selected_without_mutation_or_grain_collapse(inputs):
    before = copy.deepcopy(inputs)
    result = plan(inputs)
    assert inputs == before and result == plan(inputs)
    assert result["target_tenant_id"] == "existing"
    assert result["target_company_node_id"] == "company"
    assert result["new_department_count"] == 0 and result["role_changes"] == []
    assert result["status"] == "PLANNED_NOT_APPLIED"
    assert result["executable"] is False and result["installed"] is False
    assert len(result["ownership_targets"]) == 10 and result["affected_rows"] == 10
    for target in result["ownership_targets"]:
        expected = "procurement" if target["dataset_contract_key"] == "PRC-02" else "logistics"
        assert target["owner_dept_id"] == expected
        assert target["target_scope_node_id"] is None
        assert target["effective_from"] is None and target["approval_event_id"] is None
    for target, parent in zip(result["factory_targets"], ("copper", "battery"), strict=True):
        assert target["target_parent_node_id"] == parent
        assert target["target_scope_node_id"] is None  # 사업부 ID를 공장 ID로 쓰지 않는다.
        assert target["target_node_type"] == "site_plant"
    assert result["plan_fingerprint"] == fingerprint({k: v for k, v in result.items() if k != "plan_fingerprint"})


@pytest.mark.parametrize("failure", ["dept_missing", "dept_retired", "dept_duplicate", "node_missing", "node_retired",
    "foreign_entity", "virtual_entity", "company_mismatch", "division_grain", "edge_missing", "edge_ambiguous",
    "edge_foreign", "edge_expired", "edge_future", "wrong_relation", "instance_tenant", "parent_hash", "installed"])
def test_does_not_guess_missing_or_conflicting_connections(inputs, failure):
    org, parent, instance = inputs
    if failure == "dept_missing": org["departments"].pop()
    elif failure == "dept_retired": org["departments"][-1]["status"] = "retired"
    elif failure == "dept_duplicate": org["departments"].append(copy.deepcopy(org["departments"][-1]))
    elif failure == "node_missing": org["nodes"].pop()
    elif failure == "node_retired": org["nodes"][-1]["status"] = "REVOKED"
    elif failure == "foreign_entity": org["entities"][0]["tenant_id"] = "other"
    elif failure == "virtual_entity": org["entities"][0]["entity_mode"] = "VIRTUAL"
    elif failure == "company_mismatch": org["departments"][1]["scope_node_id"] = "battery"
    elif failure == "division_grain": org["nodes"][2]["node_type"] = "site_plant"
    elif failure == "edge_missing": org["edges"].pop()
    elif failure == "edge_ambiguous": org["edges"].append(copy.deepcopy(org["edges"][-1]))
    elif failure == "edge_foreign": org["edges"][-1]["tenant_id"] = "other"
    elif failure == "edge_expired": org["edges"][-1]["effective_to"] = WHEN
    elif failure == "edge_future": org["edges"][-1]["effective_from"] = "2027-01-01T00:00:00+00:00"
    elif failure == "wrong_relation": org["edges"][-1]["relation_type"] = "SHARED_SERVICE"
    elif failure == "instance_tenant": instance["tenant_id"] = "other"
    elif failure == "parent_hash": parent["candidate_rows"]["PRC-02"][0]["scope_node_id"] = "other"
    elif failure == "installed":
        parent["installed"] = True
        parent["proposal_fingerprint"] = fingerprint({k: v for k, v in parent.items() if k != "proposal_fingerprint"})
    with pytest.raises(ValueError):
        plan(inputs)


@pytest.mark.parametrize("failure", ["unknown_scope", "real", "duplicate", "empty", "row_hash"])
def test_row_validation_independent_of_outer_self_hash(inputs, failure):
    _, parent, _ = inputs
    rows = parent["candidate_rows"]["PRC-02"]
    if failure == "unknown_scope": rows[0]["scope_node_id"] = "new-unknown-factory"
    elif failure == "real": rows[0]["data_origin"] = "REAL"
    elif failure == "duplicate": rows.append(copy.deepcopy(rows[0]))
    elif failure == "empty": rows.clear()
    elif failure == "row_hash": parent["candidate_rows_fingerprint"] = "incorrect"
    if failure != "row_hash": parent["candidate_rows_fingerprint"] = fingerprint(parent["candidate_rows"])
    parent["proposal_fingerprint"] = fingerprint({k: v for k, v in parent.items() if k != "proposal_fingerprint"})
    with pytest.raises(ValueError):
        plan(inputs)


def test_naive_as_of_rejected(inputs):
    with pytest.raises(ValueError, match="시간대"):
        plan(inputs, as_of="2026-09-10")


def test_ro_reader_never_creates_missing_database(tmp_path):
    missing = tmp_path / "does-not-exist.db"
    with pytest.raises(sqlite3.OperationalError):
        read_organization(missing, missing)
    assert not missing.exists()


def test_ro_reader_uses_exact_files_and_does_not_read_user_secrets(tmp_path, inputs):
    org, _, _ = inputs
    master, ecm = tmp_path / "org.db", tmp_path / "ecm.db"
    for path, tables in ((master, ["departments"]), (ecm, ["nodes", "entities", "edges"])):
        conn = sqlite3.connect(path)
        for name in tables:
            table = {"nodes": "organization_nodes", "entities": "enterprise_entities", "edges": "organization_edges"}.get(name, name)
            fields = list(org[name][0])
            conn.execute('CREATE TABLE '+table+' ('+','.join(f+' TEXT' for f in fields)+')')
            conn.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in fields)+')',
                             [[r.get(f) for f in fields] for r in org[name]])
        conn.execute('CREATE TABLE users(password TEXT)')
        conn.execute("INSERT INTO users VALUES ('do-not-read')")
        conn.commit(); conn.close()
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (master, ecm)]
    actual = read_organization(master, ecm)
    assert set(actual) == {"departments", "nodes", "entities", "edges"}
    assert "do-not-read" not in repr(actual)
    assert len(actual["departments"]) == 5
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (master, ecm)] == before
    assert plan_alignment(actual, inputs[1], inputs[2], as_of=WHEN)["affected_rows"] == 10
