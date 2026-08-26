from core.data_preparation import kit_registry


def test_starter_package_catalog_separates_ready_and_preparing_packages():
    rows = kit_registry.starter_package_catalog()
    assert rows[0]["kit_id"] == "KIT-MFG-NONFERROUS-PROCUREMENT"
    by_id = {row["kit_id"]: row for row in rows}

    ready = by_id["KIT-MFG-NONFERROUS-PROCUREMENT"]
    assert ready["catalog_status"] == "AVAILABLE_FOR_DEMO"
    assert ready["selectable"] is True
    assert ready["dataset_count"] == 35
    assert ready["app_count"] == 5
    assert ready["report_count"] == 5

    preparing = by_id["KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT"]
    assert preparing["catalog_status"] == "PREPARING"
    assert preparing["selectable"] is False
    assert preparing["dataset_count"] == 35


def test_legacy_operational_profile_is_not_a_starter_package():
    ids = {row["kit_id"] for row in kit_registry.starter_package_catalog()}
    assert "afs_materials_procurement_v1" not in ids
