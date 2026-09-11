import json
import hashlib
from pathlib import Path

from core.data_preparation import kit_registry
from scripts.generate_sample_company_starter_kit import app_blueprints


def test_starter_package_catalog_separates_ready_and_preparing_packages():
    rows = kit_registry.starter_package_catalog()
    assert rows[0]["kit_id"] == "KIT-MFG-NONFERROUS-PROCUREMENT"
    by_id = {row["kit_id"]: row for row in rows}

    ready = by_id["KIT-MFG-NONFERROUS-PROCUREMENT"]
    assert ready["catalog_status"] == "AVAILABLE_FOR_DEMO"
    assert ready["selectable"] is True
    assert ready["dataset_count"] == 35
    assert ready["app_count"] == 7
    assert ready["report_count"] == 5

    preparing = by_id["KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT"]
    assert preparing["catalog_status"] == "PREPARING"
    assert preparing["selectable"] is False
    assert preparing["dataset_count"] == 35


def test_legacy_operational_profile_is_not_a_starter_package():
    ids = {row["kit_id"] for row in kit_registry.starter_package_catalog()}
    assert "afs_materials_procurement_v1" not in ids


def test_stored_app_blueprints_match_the_generator_and_cover_sales_and_enterprise():
    root = (Path("starter_kits") / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.1.0")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    generated = app_blueprints()
    assert manifest["app_blueprints"] == generated
    assert [row["app_id"] for row in generated] == [f"APP-{i:02d}" for i in range(1, 8)]
    by_id = {row["app_id"]: row for row in generated}
    assert {"SLS-01", "MFG-01", "FIN-02"} <= set(by_id["APP-06"]["datasets"])
    assert {"PRC-02", "LOG-02", "INV-01", "MFG-01", "SLS-01",
            "FIN-01", "FIN-02", "FIN-03", "SIM-02", "DEC-01"} <= set(
                by_id["APP-07"]["datasets"])
    stored = [json.loads(path.read_text(encoding="utf-8"))
              for path in sorted((root / "app_blueprints").glob("APP-*.json"))]
    assert stored == generated


def test_base_company_recommends_all_seven_executable_apps():
    path = (Path("starter_kits") / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.1.0"
            / "company_profiles" / "AFS-DEMO-MATERIALS-GROUP.json")
    profile = json.loads(path.read_text(encoding="utf-8"))
    assert profile["recommended_apps"] == [f"APP-{i:02d}" for i in range(1, 8)]
    assert "폐루프" not in profile["purpose"]


def test_starter_package_file_index_matches_every_stored_asset():
    root = Path("starter_kits") / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.1.0"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["file_index"]
    for item in manifest["file_index"]:
        path = root / item["path"]
        assert path.is_file(), item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], item["path"]
