import json
from pathlib import Path

from core.data_preparation.business_kits import (
    BUSINESS_KITS,
    classify_dataset,
    represented_business_kits,
)
from core.data_preparation import kit_registry


def test_business_kit_catalog_has_foundation_and_eight_business_functions():
    assert [row["business_kit_id"] for row in BUSINESS_KITS] == [
        "FOUNDATION", "BK-01", "BK-02", "BK-03", "BK-04",
        "BK-05", "BK-06", "BK-07", "BK-08",
    ]


def test_all_35_nonferrous_contracts_have_an_explicit_business_kit():
    package = next(
        row for row in kit_registry.starter_package_catalog()
        if row["kit_id"] == "KIT-MFG-NONFERROUS-PROCUREMENT"
    )
    assert package["dataset_count"] == 35
    assert package["business_kit_count"] == 8

    raw = json.loads(Path(
        "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/manifest.json"
    ).read_text(encoding="utf-8"))
    keys = kit_registry.dataset_keys(kit_registry.profile_from_manifest(raw))
    assert len(keys) == 35
    assert all(classify_dataset(key)["business_kit_id"] != "UNCLASSIFIED" for key in keys)
    assert len(represented_business_kits(keys)) == 8


def test_unknown_contract_is_visible_as_unclassified_not_silently_foundation():
    row = classify_dataset("NEW-01")
    assert row["business_kit_id"] == "UNCLASSIFIED"
    assert "보완" in row["business_kit_name"]
