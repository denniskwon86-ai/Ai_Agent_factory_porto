"""창고 보정은 합성 후보에서만 수행하고 수량·조직·기간은 재작성하지 않는다."""
import copy
import hashlib
import json
import random
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from core.data_preparation import kit_sample_revision as revision

KIT = Path(__file__).resolve().parents[1] / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0"


@pytest.fixture
def warehouse_case():
    def row(**fields):
        return {"tenant_id": "company", "scope_node_id": "a", "data_class": "SYNTHETIC",
                "data_origin": "SYNTHETIC", "quality_status": "PASS",
                "certification_status": "CERTIFIED_FOR_DEMO", **fields}
    def location(key, scope):
        return row(location_id=key, location_name=key, site_id=scope, scope_node_id=scope, active="True")
    opening = row(movement_id="open", movement_type="OPENING", material_id="product", lot_id="lot",
                  movement_date="2026-02-01", from_location_id="", to_location_id="raw-b", quantity="100",
                  quantity_uom="KG", reference_type="OPENING_BALANCE", reference_id="initial",
                  record_id="source", lineage_id="source-lineage")
    data = {"FND-01": [row(node_id="a"), row(node_id="b", scope_node_id="b")],
            "MDM-01": [row(material_id="raw", base_uom="KG"), row(material_id="product", base_uom="KG")],
            "MDM-04": [location("raw-a", "a"), location("raw-b", "b")], "INV-02": [opening],
            "INV-01": [row(material_id="product", location_id="raw-b", scope_node_id="b", unrestricted_quantity="100")]}
    ref_locations = [*copy.deepcopy(data["MDM-04"]), location("fg-a", "a")]
    ref_moves = [{**opening, "to_location_id": "fg-a", "movement_date": "2024-01-01",
                  "record_id": "full", "lineage_id": "full-lineage"}]
    return data, ref_locations, ref_moves


def opening_changes(changes):
    return [c for c in changes if c["dataset"] == "INV-02"]


def test_same_package_repairs_proven_fallback_and_preserves_quantities_dates_scope(warehouse_case):
    data, locations, moves = warehouse_case
    source = copy.deepcopy(warehouse_case)
    changes, held, rebuild = revision._warehouse_candidates(data, locations, moves)
    assert held == []
    assert len(changes) == 2 and len(rebuild) == 2
    change = opening_changes(changes)[0]
    assert change["before"] == source[0]["INV-02"][0]
    assert {k for k in change["before"] if change["before"][k] != change["after"][k]} == {
        "to_location_id", "quality_status", "certification_status"}
    assert change["after"]["to_location_id"] == "fg-a"
    assert change["after"]["movement_date"] == "2026-02-01"
    assert change["reference_movement_date"] == "2024-01-01"
    assert change["legacy_fallback"] == {"material_position": 1, "active_location_ids": ["raw-a", "raw-b"]}
    assert data["INV-01"] == source[0]["INV-01"]  # 파생 재고를 조용히 옮기거나 덮지 않음.
    assert (locations, moves) == (source[1], source[2])
    for c in changes:
        assert c["after"]["certification_status"] == "UNVERIFIED_CANDIDATE"
    expected = hashlib.sha256(json.dumps(moves[0], ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert change["reference_movement_fingerprint"] == expected
    assert revision._warehouse_candidates(data, locations, moves) == ([], [], [])


@pytest.mark.parametrize("field,value", [
    ("quantity", "200"), ("quantity_uom", "TON"), ("material_id", "raw"),
    ("tenant_id", "other"), ("scope_node_id", "b"), ("lot_id", "another"),
    ("reference_type", "SHIPMENT"), ("new_business_field", "not-ignored"),
    ("movement_date", "2027-01-01"),
])
def test_different_or_future_reference_never_relocates_opening(warehouse_case, field, value):
    data, locations, moves = warehouse_case
    before = copy.deepcopy(data["INV-02"])
    moves[0][field] = value
    changes, held, _ = revision._warehouse_candidates(data, locations, moves)
    assert opening_changes(changes) == [] and held
    assert data["INV-02"] == before


@pytest.mark.parametrize("problem", ["missing", "duplicate", "other_tenant", "other_scope", "inactive", "wrong_site", "org_missing"])
def test_full_warehouse_must_be_unique_active_and_same_company_scope(warehouse_case, problem):
    data, locations, moves = warehouse_case
    if problem == "missing":
        locations.pop()
    elif problem == "duplicate":
        locations.append(copy.deepcopy(locations[-1]))
    elif problem == "org_missing":
        data["FND-01"].pop(0)
    else:
        field, value = {"other_tenant": ("tenant_id", "other"), "other_scope": ("scope_node_id", "b"),
                        "inactive": ("active", "False"), "wrong_site": ("site_id", "b")}[problem]
        locations[-1][field] = value
    before = copy.deepcopy(data["INV-02"])
    changes, held, _ = revision._warehouse_candidates(data, locations, moves)
    assert changes == [] and held
    assert data["INV-02"] == before


@pytest.mark.parametrize("source", ["current", "full"])
def test_duplicate_opening_identity_is_not_selected(warehouse_case, source):
    data, locations, moves = warehouse_case
    rows = data["INV-02"] if source == "current" else moves
    rows.append(copy.deepcopy(rows[0]))
    changes, held, _ = revision._warehouse_candidates(data, locations, moves)
    assert opening_changes(changes) == [] and held


def test_existing_valid_alternate_warehouse_is_not_replaced(warehouse_case):
    data, locations, moves = warehouse_case
    data["MDM-04"].append(copy.deepcopy(locations[-1]))
    changes, held, _ = revision._warehouse_candidates(data, locations, moves)
    assert changes == [] and held


def test_only_exact_legacy_fallback_is_repaired(warehouse_case):
    data, locations, moves = warehouse_case
    data["INV-02"][0]["to_location_id"] = "raw-a"  # 위치상 옛 fallback은 raw-b여야 함.
    changes, held, _ = revision._warehouse_candidates(data, locations, moves)
    assert opening_changes(changes) == [] and held


def test_same_scope_legacy_fallback_can_also_be_repaired(warehouse_case):
    data, locations, moves = warehouse_case
    data["MDM-01"].reverse()  # product 위치 0의 fallback은 raw-a.
    data["INV-02"][0]["to_location_id"] = "raw-a"
    changes, held, _ = revision._warehouse_candidates(data, locations, moves)
    assert held == []
    assert opening_changes(changes)[0]["after"]["to_location_id"] == "fg-a"


@pytest.mark.parametrize("target", ["locations", "moves"])
def test_public_reference_is_not_used_as_synthetic_repair(warehouse_case, target):
    data, locations, moves = warehouse_case
    (locations if target == "locations" else moves)[-1]["data_origin"] = "PUBLIC_DISCLOSURE"
    with pytest.raises(ValueError, match="합성"):
        revision._warehouse_candidates(data, locations, moves)


def test_normal_transactions_do_not_get_opening_relocation(warehouse_case):
    data, locations, moves = warehouse_case
    data["INV-02"][0].update(movement_type="PURCHASE_RECEIPT", from_location_id="IN_TRANSIT", reference_type="SHIPMENT")
    before = copy.deepcopy(data["INV-02"])
    changes, held, _ = revision._warehouse_candidates(data, locations, moves)
    assert changes == [] and held
    assert data["INV-02"] == before


def test_referenced_missing_warehouse_is_added_without_rewriting_movements(warehouse_case):
    data, locations, moves = warehouse_case
    data["INV-02"][0].update(movement_type="PRODUCTION_RECEIPT", from_location_id="PRODUCTION",
                            reference_type="BATCH", to_location_id="fg-a")
    before = copy.deepcopy(data["INV-02"])
    changes, held, rebuild = revision._warehouse_candidates(data, locations, moves)
    assert held == [] and len(changes) == len(rebuild) == 1
    assert changes[0]["dataset"] == "MDM-04"
    assert data["INV-02"] == before


def test_quick_real_candidate_removes_warehouse_errors_but_keeps_stock_rebuild_pending():
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()}
    report = revision.plan_package_revision(KIT, resolve_exact_bom_copies=True, repair_warehouses=True)
    assert report["change_counts"] == {"FND-01": 3, "MDM-05": 5, "MFG-01": 500, "MDM-04": 1, "INV-02": 11}
    assert report["warehouse_rule"] == "same-package-warehouse-and-opening-fallback/1"
    assert report["held"] == [] and len(report["warehouse_rebuild_required"]) == 12
    codes = report["quantity_flow"]["issue_counts"]
    assert "Q_REFERENCE" not in codes and "Q_WAREHOUSE_SCOPE" not in codes
    assert codes["Q_UNIT"] == 1098 and codes["Q_NEGATIVE_STOCK"] == 16
    assert report["candidate_check"] == "FAIL"  # BOM·창고 개선만으로 준비 완료로 판정하지 않음.
    assert report["warehouse_reference"]["files"]["MDM-04"]["sha256"]
    assert report["warehouse_reference"]["files"]["INV-02"]["sha256"]
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()} == before
    repeat = revision.plan_package_revision(KIT, resolve_exact_bom_copies=True, repair_warehouses=True)
    assert repeat == report


def test_full_profile_is_not_relocated_or_backdated():
    report = revision.plan_package_revision(KIT, "full", resolve_exact_bom_copies=True, repair_warehouses=True)
    assert report["change_counts"] == {"MFG-01": 5157}
    assert report["warehouse_rebuild_required"] == []
    assert report["after"]["issue_counts"] == {"BOM_NOT_BOUND": 843}
    assert len(report["held"]) == 843


def test_cli_option_is_wired_and_does_not_claim_ready(tmp_path):
    target = tmp_path / "candidate.json"
    result = subprocess.run([sys.executable, "-m", "scripts.plan_business_kit_initial_revision",
                             "--resolve-exact-bom-copies", "--repair-warehouses", "--report", str(target)],
                            capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["change_counts"]["INV-02"] == 11
    assert report["status"] == "REVIEW_ONLY" and report["candidate_check"] == "FAIL"


def test_quick_generator_includes_its_production_warehouse_without_writing_assets():
    from scripts.generate_sample_company_starter_kit import PROFILES, generate_locations, generate_materials, generate_movements_and_snapshots
    p = PROFILES["quick"]
    locations, materials = generate_locations(p), generate_materials(p)
    assert {r["location_id"] for r in locations} == {"LOC-P1-RAW", "LOC-P1-FG", "LOC-P2-RAW", "LOC-P2-FG"}
    original = copy.deepcopy((locations, materials))
    movements, _ = generate_movements_and_snapshots(p, [], [], [], [], [], materials, locations,
                                                   date(2026, 2, 1), date(2026, 2, 28), random.Random(1))
    for move in movements:
        if move["movement_type"] == "OPENING":
            target = [r for r in locations if r["location_id"] == move["to_location_id"]]
            assert len(target) == 1 and target[0]["scope_node_id"] == move["scope_node_id"]
    assert (locations, materials) == original


@pytest.mark.parametrize("problem", ["missing", "inactive", "scope", "tenant", "duplicate"])
def test_generator_must_stop_instead_of_falling_back(problem):
    from scripts.generate_sample_company_starter_kit import PROFILES, generate_locations, generate_materials, generate_movements_and_snapshots
    p = PROFILES["quick"]
    locations, materials = generate_locations(p), generate_materials(p)
    target = next(r for r in locations if r["location_id"] == "LOC-P1-FG")
    if problem == "missing":
        locations.remove(target)
    elif problem == "duplicate":
        locations.append(copy.deepcopy(target))
    else:
        field, value = {"inactive": ("active", False), "scope": ("scope_node_id", "other"), "tenant": ("tenant_id", "other")}[problem]
        target[field] = value
    with pytest.raises(ValueError, match="Opening warehouse unavailable"):
        generate_movements_and_snapshots(p, [], [], [], [], [], materials, locations,
                                         date(2026, 2, 1), date(2026, 2, 28), random.Random(1))


def test_stock_rebuild_requirement_independently_blocks_candidate(monkeypatch):
    monkeypatch.setattr(revision, "inspect_quantity_flow", lambda rows: {"status": "PASS_CHECKED_SCOPE", "issues": []})
    report = revision.plan_package_revision(KIT, resolve_exact_bom_copies=True, repair_warehouses=True)
    assert report["after"]["issue_count"] == 0 and report["held"] == []
    assert report["warehouse_rebuild_required"]
    assert report["candidate_check"] == "FAIL"
