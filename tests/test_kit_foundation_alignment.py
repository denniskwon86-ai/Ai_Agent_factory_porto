"""선행자료 정렬·보류·원문 보존의 회귀. SQLite 연결은 필요하지 않다."""
from copy import deepcopy
from pathlib import Path

import pytest

from core.data_preparation.kit_foundation_alignment import FOUNDATION, prepare_foundation, inspect_foundation_links
from core.data_preparation.kit_sample_audit import read_package


@pytest.fixture(scope="module")
def kit():
    root = Path(__file__).resolve().parents[1] / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"
    _, data, contracts, _, errors = read_package(root, "full")
    assert not errors
    keys = (*FOUNDATION, "PRC-01", "PRC-02", "MDM-01", "MDM-02", "LOG-05")
    return {key: data[key] for key in keys}, contracts


@pytest.fixture
def context(kit):
    rows = [("G", "enterprise_group", ""), ("C", "legal_entity", "G"),
            ("D1", "business_division", "C"), ("D2", "business_division", "C"),
            ("P1", "site_plant", "D1"), ("P2", "site_plant", "D2")]
    org = {"nodes": [{"node_id": key, "entity_id": "E" + key, "node_type": kind,
        "tenant_id": "T", "status": "ACTIVE", "default_parent_id": parent, "name_ko": key}
        for key, kind, parent in rows],
        "entities": [{"entity_id": "E" + key, "tenant_id": "T", "status": "ACTIVE", "entity_mode": "REAL"}
        for key, _, _ in rows],
        "edges": [{"tenant_id": "T", "from_node_id": parent, "to_node_id": key, "status": "ACTIVE",
            "relation_type": "LEGAL_OWNERSHIP" if kind == "legal_entity" else "OPERATING_PARENT",
            "effective_from": "2026-09-10T00:00:00+00:00" if kind == "site_plant" else "", "effective_to": ""}
            for key, kind, parent in rows if parent]}
    return deepcopy(kit[0]), kit[1], org, dict(source_tenant="tenant-afs-demo-materials", tenant="T", company="C",
        factories={"plant-afs-smelting-01": "P1", "plant-afs-battery-02": "P2"}, as_of="2026-09-11T00:00:00+00:00")


def build(context):
    source, contracts, org, args = context
    return prepare_foundation(source, contracts, org, **args)


def test_five_datasets_1397_rows_preserve_sources_and_business_fields(context):
    source, _, org, _ = context
    before = deepcopy((source, org))
    result = build(context)
    assert (source, org) == before
    assert result == build(context)
    data = result["candidate_rows"]
    assert {k: len(v) for k, v in data.items()} == {"FND-01": 6, "FND-03": 1101, "MDM-04": 7, "MDM-08": 43, "EXT-02": 240}
    for key in FOUNDATION[1:]:
        originals = {r["record_id"]: r for r in source[key]}
        for row in data[key]:
            allowed = {"tenant_id", "scope_node_id", "quality_status", "certification_status"}
            if key == "MDM-04":
                allowed.add("site_id")
            assert {field for field in row if row[field] != originals[row["record_id"]][field]} <= allowed
    assert not result["installed"] and not result["executable"] and not result["certified"]


def test_unmapped_warehouse_is_preserved_not_reassigned_or_discarded(context):
    source, _, _, _ = context
    result = build(context)
    held = result["held_source_rows"]
    assert len(held) == 1 and held[0]["source_row"] == source["MDM-04"][-1]
    assert held[0]["source_row"]["location_id"] == "LOC-P3-SIM"
    assert all(r["site_id"] == r["scope_node_id"] for r in result["candidate_rows"]["MDM-04"])


def test_current_org_does_not_invent_historical_dates_or_legal_aliases(context):
    result = build(context)
    assert result["organization_projection"]["source_template_rows_preserved"] == 15
    assert result["organization_projection"]["historical_validity_asserted"] is False
    assert result["organization_projection"]["legal_entity_alias_created"] is False
    for row in result["candidate_rows"]["FND-01"]:
        assert row["effective_from"] == row["effective_to"] == ""
        assert row["data_origin"] == "SYNTHETIC"
        assert row["certification_status"] == "UNVERIFIED_CANDIDATE"
    assert {r["node_id"] for r in result["candidate_rows"]["FND-01"]} == {"G", "C", "D1", "D2", "P1", "P2"}


@pytest.mark.parametrize("problem", ["source_tenant", "real_source", "source_certification", "duplicate_key",
    "empty", "duplicate_target", "unknown_source", "virtual_target", "foreign_ancestor", "cycle",
    "missing_edge", "duplicate_edge", "future_edge", "expired_edge", "naive_asof", "warehouse_site",
    "unmapped_active", "shared_scope", "wrong_company"])
def test_ambiguous_unsafe_or_changed_context_is_rejected(context, problem):
    source, _, org, args = context
    if problem == "source_tenant": source["EXT-02"][0]["tenant_id"] = "other"
    elif problem == "real_source": source["EXT-02"][0]["data_origin"] = "ACTUAL"
    elif problem == "source_certification": source["EXT-02"][0]["certification_status"] = "SOURCE_CERTIFIED"
    elif problem == "duplicate_key": source["EXT-02"].append(dict(source["EXT-02"][0]))
    elif problem == "empty": source["EXT-02"] = []
    elif problem == "duplicate_target": args["factories"]["plant-afs-battery-02"] = "P1"
    elif problem == "unknown_source": args["factories"] = {"plant-afs-expansion-03": "P1", "plant-afs-battery-02": "P2"}
    elif problem == "virtual_target": org["entities"][-1]["entity_mode"] = "VIRTUAL"
    elif problem == "foreign_ancestor": org["nodes"][0]["tenant_id"] = "other"
    elif problem == "cycle": org["nodes"][0]["default_parent_id"] = "C"
    elif problem == "missing_edge": org["edges"].pop()
    elif problem == "duplicate_edge": org["edges"].append(dict(org["edges"][-1]))
    elif problem == "future_edge": org["edges"][-1]["effective_from"] = "2027-01-01T00:00:00+00:00"
    elif problem == "expired_edge": org["edges"][-1]["effective_to"] = args["as_of"]
    elif problem == "naive_asof": args["as_of"] = "2026-09-11"
    elif problem == "warehouse_site": source["MDM-04"][0]["site_id"] = "different"
    elif problem == "unmapped_active": source["MDM-04"][-1]["active"] = "True"
    elif problem == "shared_scope": source["FND-03"][0]["scope_node_id"] = "org-afs-metals"
    elif problem == "wrong_company": args["company"] = "D1"
    with pytest.raises(ValueError): build(context)


@pytest.fixture
def linked(context):
    source, contracts, _, _ = context
    data = build(context)["candidate_rows"]
    def mapped(row):
        return {**row, "tenant_id": "T", "scope_node_id": "P1"}
    po = source["PRC-02"][0]
    contract = next(r for r in source["PRC-01"] if r["contract_id"] == po["contract_id"])
    data["PRC-01"] = [mapped(contract)]
    data["PRC-02"] = [mapped(po)]
    data["MDM-01"] = [mapped(next(r for r in source["MDM-01"] if r["material_id"] == po["material_id"]))]
    data["MDM-02"] = [mapped(next(r for r in source["MDM-02"] if r["supplier_id"] == po["supplier_id"]))]
    data["LOG-05"] = [mapped(source["LOG-05"][0])]
    return data, contracts


def test_structural_links_do_not_clear_usage_holds(linked):
    data, contracts = linked
    checks = inspect_foundation_links(data, contracts)
    assert checks["reference_counts"] == {"TRANSPORT_LOCATION": 1, "REFERENCE_INCOTERM": 1,
        "REFERENCE_PAYMENT_TERM": 1, "BENCHMARK_CODE": 1, "ORDER_CALENDAR": 1}
    assert len(checks["historical_org_nodes_unverified"]) == 6
    assert len(checks["usage_holds"]) == 3
    assert checks["executable"] is False and checks["certified"] is False


@pytest.mark.parametrize("problem,code", [("missing_location", "TRANSPORT_LOCATION"),
    ("foreign_location", "TRANSPORT_LOCATION"), ("wrong_factory", "TRANSPORT_LOCATION"),
    ("inactive_location", "TRANSPORT_LOCATION"), ("held_location", "TRANSPORT_LOCATION"),
    ("missing_calendar", "ORDER_CALENDAR"), ("missing_term", "REFERENCE_PAYMENT_TERM"),
    ("missing_benchmark", "BENCHMARK_CODE"), ("future_observation", "PRICE_OBSERVATION_ORDER")])
def test_broken_foundation_link_is_not_a_pass(linked, problem, code):
    data, contracts = linked
    location = next(r for r in data["MDM-04"] if r["location_id"] == data["LOG-05"][0]["destination_location_id"])
    if problem == "missing_location": data["MDM-04"].remove(location)
    elif problem == "foreign_location": location["tenant_id"] = "other"
    elif problem == "wrong_factory": location["scope_node_id"] = "P2"
    elif problem == "inactive_location": location["active"] = "False"
    elif problem == "held_location": data["LOG-05"][0]["destination_location_id"] = "LOC-P3-SIM"
    elif problem == "missing_calendar": data["PRC-02"][0]["order_date"] = "1900-01-01"
    elif problem == "missing_term": data["PRC-01"][0]["payment_terms"] = "UNKNOWN"
    elif problem == "missing_benchmark": data["PRC-01"][0]["benchmark_code"] = "UNKNOWN"
    elif problem == "future_observation": data["EXT-02"][0]["observed_at"] = "2099-01-01"
    result = inspect_foundation_links(data, contracts)
    assert code in {issue["code"] for issue in result["structural_issues"]}
