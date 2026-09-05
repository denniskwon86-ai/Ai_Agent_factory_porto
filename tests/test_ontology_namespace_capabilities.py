from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI

from api.routes import ontology_control
from core import ontology_namespace_capabilities as cap
from core import ontology_runtime
from core.data_preparation import scope_index


def test_runtime_namespace_totals_are_the_actual_product_coverage():
    status = cap.runtime_status()
    assert status["namespace_count"] == 7
    assert status["contract_object_type_count"] == 29
    assert status["resolver_available_namespace_count"] == 7
    assert status["resolver_object_type_count"] == 29
    assert status["display_object_type_count"] == 29
    assert status["fully_ready_namespace_count"] == 7
    assert status["status"] == cap.READY


def test_status_vocabulary_matches_the_runtime_and_design_contract():
    assert cap.NAMESPACES == ontology_runtime.NAMESPACES
    contract_path = (Path(__file__).parents[1] / "docs" / "architecture"
                     / "g2_first_vertical_ontology_contract_v1.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    declared_namespaces = tuple(row["id"] for row in contract["namespaces"])
    assert declared_namespaces == cap.NAMESPACES

    declared = {namespace: set() for namespace in cap.NAMESPACES}
    for row in contract["object_types"]:
        declared[row["namespace"]].add(row["type"])
    assert {key: tuple(sorted(value)) for key, value in declared.items()} == cap.CONTRACT_OBJECT_TYPES


def test_dataset_counts_come_from_the_real_scope_index_contract():
    actual = tuple(sorted({value[1] for value in scope_index.CONTRACT_OBJECTS.values()}))
    assert actual == cap.RESOLVER_OBJECT_TYPES["dataset"]
    assert cap.DISPLAY_OBJECT_TYPES["dataset"] == actual


def test_mdm_and_external_counts_come_from_the_safe_reference_index_contract():
    actual = {}
    for key in (set(scope_index.REFERENCE_OBJECTS)
                | set(scope_index.COMPOSITE_REFERENCE_OBJECTS)
                | set(scope_index.GROUPED_REFERENCE_OBJECTS)):
        for namespace, object_type, _ in scope_index.object_specs(key):
            actual.setdefault(namespace, set()).add(object_type)
    assert tuple(sorted(actual["mdm"])) == cap.RESOLVER_OBJECT_TYPES["mdm"]
    assert tuple(sorted(actual["external"])) == cap.RESOLVER_OBJECT_TYPES["external"]
    assert cap.DISPLAY_OBJECT_TYPES["mdm"] == cap.RESOLVER_OBJECT_TYPES["mdm"]
    assert cap.DISPLAY_OBJECT_TYPES["external"] == cap.RESOLVER_OBJECT_TYPES["external"]


def test_unwired_never_means_zero_business_rows():
    rows = {row["namespace"]: row for row in cap.runtime_status()["namespaces"]}
    assert rows["g4"]["resolver_status"] == cap.READY
    assert rows["g4"]["resolver_object_type_count"] == 1
    assert rows["decision"]["resolver_status"] == cap.READY
    assert rows["decision"]["resolver_object_type_count"] == 2
    assert rows["knowledge"]["resolver_status"] == cap.READY
    assert rows["knowledge"]["resolver_object_type_count"] == 1


def test_dataset_is_ready_only_after_all_fourteen_contract_types_are_wired():
    rows = {row["namespace"]: row for row in cap.runtime_status()["namespaces"]}
    assert rows["ecm"]["resolver_status"] == cap.READY
    assert rows["ecm"]["display_status"] == cap.READY
    assert rows["dataset"]["resolver_status"] == cap.READY
    assert rows["dataset"]["display_status"] == cap.READY
    assert rows["mdm"]["resolver_status"] == cap.READY
    assert rows["external"]["resolver_status"] == cap.READY


def test_materialization_is_reported_separately_from_implementation():
    status = cap.runtime_status({
        "ecm": ("organization-node",),
        "dataset": cap.RESOLVER_OBJECT_TYPES["dataset"],
    })
    rows = {row["namespace"]: row for row in status["namespaces"]}
    assert status["materialized_object_type_count"] == 15
    assert rows["mdm"]["resolver_object_type_count"] == 9
    assert rows["mdm"]["materialized_object_type_count"] == 0
    assert "명시적 결속" in rows["mdm"]["message"]
    assert rows["external"]["resolver_status"] == cap.READY
    assert rows["external"]["materialized_object_type_count"] == 0
    assert "데이터가 없다는 뜻" in rows["external"]["message"]


def test_runtime_status_route_is_mounted_on_the_product_router(tmp_path):
    runtime = ontology_runtime.OntologyRuntime(str(tmp_path / "ontology.db"))
    app = FastAPI()
    app.include_router(ontology_control.create_router(runtime))
    paths = {route.path for route in app.routes}
    assert "/api/v1/ontology/runtime/status" in paths


def test_ui_explains_blocked_namespace_without_exposing_internal_ids():
    root = Path(__file__).parents[1]
    source = (root / "frontend" / "src" / "components" / "OntologyExplorerView.tsx").read_text(
        encoding="utf-8")
    api = (root / "frontend" / "src" / "lib" / "ontologyApi.ts").read_text(encoding="utf-8")
    assert "연결 전은 데이터 없음이 아닙니다" in source
    assert "runtimeStatus" in source and "/api/v1/ontology/runtime/status" in api
    assert "resolver_object_type_count" in source and "display_object_type_count" in source
    assert "materialized_object_type_count" in source and "현재 정본 결속" in source
    assert ".filter((row) => row.resolver_object_type_count > 0)" in source
    assert "new Set(rows.map((o) => o.namespace))" not in source
    for namespace in ("ecm", "mdm", "dataset", "external", "decision"):
        assert f"'{namespace}'" in source


def test_ui_has_human_type_names_for_every_resolver_type():
    source = (Path(__file__).parents[1] / "frontend" / "src" / "components"
              / "OntologyExplorerView.tsx").read_text(encoding="utf-8")
    for object_types in cap.RESOLVER_OBJECT_TYPES.values():
        for object_type in object_types:
            assert (f"'{object_type}':" in source or f"{object_type}:" in source), object_type
