from __future__ import annotations

from dataclasses import dataclass

import pytest

from core import app_policy
from core.ontology_runtime import (
    ObjectRef, OntologyError, OntologyIntegrityError, OntologyRuntime, RelationProposal,
)


@dataclass
class _Scope:
    readable_dept_ids: frozenset = frozenset({"org_demo"})
    writable_dept_ids: frozenset = frozenset({"org_demo"})
    unrestricted: bool = False


def _subject(tenant="tenant_demo", mode="VIRTUAL", selected="plant_demo",
             readable=frozenset({"org_demo"})):
    return app_policy.Subject(
        user_id="buyer@example.com",
        scope=_Scope(readable_dept_ids=readable, writable_dept_ids=readable),
        ctx={"tenant_id": tenant, "entity_mode": mode, "scope_node_id": selected},
    )


def _resolver(hidden=frozenset(), tenant="tenant_demo", mode="VIRTUAL"):
    def resolve(ref: ObjectRef):
        if ref.key in hidden:
            return app_policy.ResourceScope(
                tenant_id=tenant, entity_mode=mode, scope_node_id="secret_plant",
                owner_dept_id="secret_org", binding_state=app_policy.BOUND)
        return app_policy.ResourceScope(
            tenant_id=tenant, entity_mode=mode, scope_node_id="plant_demo",
            owner_dept_id="org_demo", binding_state=app_policy.BOUND)
    return resolve


def _approval_resolver(ledger_id, action, actor, target_type="", target_id=""):
    """시험 대역. ★ **다섯 인자**다 — 제품 계약과 같은 모양이어야
    시험이 제품을 대신한다(2026-08-20: 3인자 폴백을 없앨다)."""
    return bool(ledger_id and action and actor)


def _model_contract(status="APPROVED", version="1.0.0"):
    contract = {
        "contract_id": "G2-FIRST-VERTICAL-ONTOLOGY",
        "contract_version": version,
        "status": status,
        "relation_types": [
            {"id": "AFFECTS", "name_ko": "영향을 줌", "inverse": "AFFECTED_BY",
             "quantitative": True},
            {"id": "ORDERS_MATERIAL", "name_ko": "주문 원료", "inverse": "ORDERED_BY",
             "quantitative": False},
        ],
        "constraints": [
            {"subject": "dataset:shipment", "relation": "AFFECTS",
             "object": "dataset:inventory-snapshot", "evidence": ["approved delay model"],
             "calculation_ref": "CALC.LOGISTICS.ARRIVAL_DELAY.v1"},
            {"subject": "dataset:purchase-order-line", "relation": "ORDERS_MATERIAL",
             "object": "mdm:material", "evidence": ["PRC-02.material_id"]},
        ],
    }
    if status == "APPROVED":
        contract["approval"] = {
            "approved_by": "data-governor",
            "decision_ledger_id": "ledger-g2-model-v1",
            "effective_from": "2026-01-01T00:00:00Z",
        }
    return contract


@pytest.fixture
def runtime(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    rt.register_relation_type("AFFECTS", "영향을 줌", "AFFECTED_BY", True, "1.0.0",
                              "model_owner", "2026-01-01T00:00:00Z",
                              ledger_correlation_id="led-type-affects")
    rt.register_constraint("dataset", "shipment", "AFFECTS", "dataset",
                           "inventory-snapshot", ["approved delay model"], "model_owner",
                           "CALC.LOGISTICS.ARRIVAL_DELAY.v1")
    rt.register_constraint("dataset", "inventory-snapshot", "AFFECTS", "dataset",
                           "production-plan-line", ["approved inventory model"], "model_owner",
                           "CALC.INVENTORY.MATERIAL_SHORTAGE.v1")
    return rt


def _proposal(subject, obj, start="2026-01-01T00:00:00Z", end="",
              calc="CALC.LOGISTICS.ARRIVAL_DELAY.v1", tenant="tenant_demo",
              scope="plant_demo", owner="org_demo"):
    return RelationProposal(
        subject=subject, relation_type_id="AFFECTS", object=obj,
        tenant_id=tenant, enterprise_scope_id=scope, entity_mode="VIRTUAL",
        owner_organization_id=owner, effective_from=start, effective_to=end,
        origin="derived", evidence_refs=("SNAPSHOT:LOG-02:v1",), calculation_ref=calc,
    )


def _approve(rt, proposal, proposer="steward", approver="governor"):
    row = rt.propose_relation(proposal, proposer, _subject())
    assert row["approval_status"] == "DRAFT"
    row = rt.submit(row["relation_id"], proposer, _subject())
    assert row["approval_status"] == "IN_REVIEW"
    return rt.approve(row["relation_id"], approver, "ledger-approval", _subject())


def test_governed_relation_lifecycle_and_self_approval(runtime):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-001")
    row = runtime.propose_relation(_proposal(shipment, inventory), "steward", _subject())
    row = runtime.submit(row["relation_id"], "steward", _subject())
    with pytest.raises(OntologyError, match="self approval"):
        runtime.approve(row["relation_id"], "steward", "ledger-x", _subject())
    row = runtime.approve(row["relation_id"], "governor", "ledger-x", _subject())
    assert row["approval_status"] == "APPROVED"
    assert row["approved_by"] == "governor"


def test_constraint_and_calculation_reference_are_enforced(runtime):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    wrong = ObjectRef("dataset", "production-plan-line", "PLAN-001")
    with pytest.raises(OntologyError, match="combination"):
        runtime.propose_relation(_proposal(shipment, wrong), "steward", _subject())
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-001")
    with pytest.raises(OntologyError, match="calculation reference"):
        runtime.propose_relation(_proposal(shipment, inventory, calc="WRONG"), "steward",
                                 _subject())


def test_unbound_relation_is_rejected_before_storage(runtime):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-001")
    with pytest.raises(OntologyError, match="unbound"):
        runtime.propose_relation(_proposal(shipment, inventory, scope=""), "steward", _subject())


def test_approved_period_overlap_is_rejected(runtime):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-001")
    _approve(runtime, _proposal(shipment, inventory, end="2026-07-01T00:00:00Z"))
    row = runtime.propose_relation(
        _proposal(shipment, inventory, start="2026-06-01T00:00:00Z"), "other", _subject())
    runtime.submit(row["relation_id"], "other", _subject())
    with pytest.raises(OntologyError, match="covers this effective period"):
        runtime.approve(row["relation_id"], "governor", "ledger-2", _subject())


def test_as_of_and_deterministic_path_fingerprint(runtime):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-001")
    production = ObjectRef("dataset", "production-plan-line", "PLAN-001")
    _approve(runtime, _proposal(shipment, inventory, end="2026-07-01T00:00:00Z"))
    _approve(runtime, _proposal(
        inventory, production, start="2026-01-01T00:00:00Z", end="2026-07-01T00:00:00Z",
        calc="CALC.INVENTORY.MATERIAL_SHORTAGE.v1"))

    first = runtime.find_paths(_subject(), [shipment], ["production-plan-line"], ["AFFECTS"],
                               "2026-03-01T00:00:00Z")
    second = runtime.find_paths(_subject(), [shipment], ["production-plan-line"], ["AFFECTS"],
                                "2026-03-01T00:00:00Z")
    assert first == second
    assert first["status"] == "COMPLETE"
    assert len(first["paths"]) == 1
    assert len(first["paths"][0]["edges"]) == 2
    assert first["context_omitted"] is None

    expired = runtime.find_paths(_subject(), [shipment], ["production-plan-line"], ["AFFECTS"],
                                 "2026-08-01T00:00:00Z")
    assert expired["status"] == "NO_VISIBLE_PATH"
    assert "blocked" not in expired


def test_hidden_middle_node_removes_entire_path_without_bridge(tmp_path):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-SECRET")
    production = ObjectRef("dataset", "production-plan-line", "PLAN-001")
    # The steward could see the object when the relationship was approved.  Access is revoked
    # later; traversal must re-check current scope and remove the whole path.
    hidden = set()
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(hidden), _approval_resolver)
    rt.register_relation_type("AFFECTS", "영향을 줌", "AFFECTED_BY", True, "1.0.0",
                              "model_owner", "2026-01-01T00:00:00Z",
                              ledger_correlation_id="led-type")
    rt.register_constraint("dataset", "shipment", "AFFECTS", "dataset", "inventory-snapshot",
                           ["delay"], "model_owner", "CALC.LOGISTICS.ARRIVAL_DELAY.v1")
    rt.register_constraint("dataset", "inventory-snapshot", "AFFECTS", "dataset",
                           "production-plan-line", ["stock"], "model_owner",
                           "CALC.INVENTORY.MATERIAL_SHORTAGE.v1")
    _approve(rt, _proposal(shipment, inventory))
    _approve(rt, _proposal(inventory, production,
                           calc="CALC.INVENTORY.MATERIAL_SHORTAGE.v1"))
    hidden.add(inventory.key)
    result = rt.find_paths(_subject(), [shipment], ["production-plan-line"], ["AFFECTS"],
                           "2026-03-01T00:00:00Z")
    assert result["status"] == "NO_VISIBLE_PATH"
    assert result["paths"] == []
    assert "blocked" not in result


def test_cross_tenant_and_unapproved_relations_do_not_leak(runtime):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-001")
    # A caller cannot create a relation in another tenant merely by putting that tenant in input.
    with pytest.raises(OntologyError, match="cannot be changed"):
        runtime.propose_relation(_proposal(shipment, inventory, tenant="tenant_other"),
                                 "steward", _subject())
    draft = runtime.propose_relation(_proposal(shipment, inventory), "steward", _subject())
    assert draft["approval_status"] == "DRAFT"
    result = runtime.find_paths(_subject(), [shipment], ["inventory-snapshot"], ["AFFECTS"],
                                "2026-03-01T00:00:00Z")
    assert result["status"] == "NO_VISIBLE_PATH"
    assert result["paths"] == []
    assert "blocked" not in result


def test_proposal_requires_both_endpoint_visibility(tmp_path):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    hidden = ObjectRef("dataset", "inventory-snapshot", "INV-HIDDEN")
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(frozenset({hidden.key})),
                         _approval_resolver)
    rt.register_relation_type("AFFECTS", "영향을 줌", "AFFECTED_BY", True, "1.0.0",
                              "model_owner", "2026-01-01T00:00:00Z",
                              ledger_correlation_id="led-type")
    rt.register_constraint("dataset", "shipment", "AFFECTS", "dataset",
                           "inventory-snapshot", ["delay"], "model_owner",
                           "CALC.LOGISTICS.ARRIVAL_DELAY.v1")
    with pytest.raises(OntologyError, match="endpoints"):
        rt.propose_relation(_proposal(shipment, hidden), "steward", _subject())


def test_relation_transition_requires_write_scope(runtime):
    shipment = ObjectRef("dataset", "shipment", "SHP-001")
    inventory = ObjectRef("dataset", "inventory-snapshot", "INV-001")
    row = runtime.propose_relation(_proposal(shipment, inventory), "steward", _subject())
    no_write = _subject(readable=frozenset({"other_org"}))
    with pytest.raises(OntologyError, match="cannot be changed"):
        runtime.submit(row["relation_id"], "steward", no_write)


def test_missing_object_scope_resolver_fails_closed(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"))
    with pytest.raises(OntologyIntegrityError, match="resolver"):
        rt.find_paths(_subject(), [ObjectRef("dataset", "shipment", "S")], [], [],
                      "2026-03-01T00:00:00Z")


def test_design_contract_can_be_validated_but_not_installed(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    report = rt.validate_model_contract(_model_contract("DESIGN_ONLY"))
    assert report["status"] == "DESIGN_ONLY"
    assert report["installable"] is False
    assert len(report["contract_fingerprint"]) == 64
    with pytest.raises(OntologyError, match="only an APPROVED"):
        rt.install_model_contract(_model_contract("DESIGN_ONLY"), "installer")
    assert rt.model_status() == {"status": "NOT_INSTALLED", "contracts": [], "count": 0}


def test_approved_model_install_is_atomic_and_idempotent(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    first = rt.install_model_contract(_model_contract(), "installer")
    assert first["installed"] is True
    assert first["relation_type_count"] == 2
    assert first["constraint_count"] == 2
    second = rt.install_model_contract(_model_contract(), "installer")
    assert second["installed"] is False
    assert second["idempotent"] is True
    status = rt.model_status("G2-FIRST-VERTICAL-ONTOLOGY")
    assert status["status"] == "READY"
    assert status["count"] == 1

    # The installed dictionary is usable by the governed relation lifecycle.
    row = rt.propose_relation(
        _proposal(ObjectRef("dataset", "shipment", "SHP-1"),
                  ObjectRef("dataset", "inventory-snapshot", "INV-1")), "steward", _subject())
    assert row["approval_status"] == "DRAFT"


def test_install_marker_does_not_hide_dictionary_damage(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    rt.install_model_contract(_model_contract(), "installer")
    with rt._connect() as conn:
        conn.execute("DELETE FROM semantic_relation_constraints")
    assert rt.model_status()["status"] == "NOT_READY"
    with pytest.raises(OntologyIntegrityError, match="missing or has changed"):
        rt.install_model_contract(_model_contract(), "installer")


def test_model_install_requires_a_real_approval_resolver(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver())
    with pytest.raises(OntologyIntegrityError, match="approval resolver"):
        rt.install_model_contract(_model_contract(), "installer")


def test_same_model_id_and_version_cannot_change_content(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    rt.install_model_contract(_model_contract(), "installer")
    changed = _model_contract()
    changed["relation_types"][0]["name_ko"] = "다른 의미"
    with pytest.raises(OntologyIntegrityError, match="different content"):
        rt.install_model_contract(changed, "installer")
    assert rt.model_status()["count"] == 1


def test_invalid_contract_leaves_no_partial_dictionary(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    broken = _model_contract()
    broken["constraints"][1]["relation"] = "UNKNOWN_RELATION"
    with pytest.raises(OntologyError, match="unknown relation type"):
        rt.install_model_contract(broken, "installer")
    assert rt.model_status()["count"] == 0
    with rt._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM semantic_relation_types").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM semantic_relation_constraints").fetchone()[0] == 0


def test_quantitative_constraint_without_calculation_is_rejected(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    broken = _model_contract()
    broken["constraints"][0].pop("calculation_ref")
    with pytest.raises(OntologyError, match="calculation_ref"):
        rt.validate_model_contract(broken)


def test_second_model_version_is_refused_until_dictionary_is_versioned(tmp_path):
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), _resolver(), _approval_resolver)
    rt.install_model_contract(_model_contract(), "installer")
    with pytest.raises(OntologyIntegrityError, match="versioned relation dictionaries"):
        rt.install_model_contract(_model_contract(version="2.0.0"), "installer")
