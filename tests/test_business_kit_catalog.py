import json
from pathlib import Path

from core.data_preparation.business_kits import (
    BUSINESS_KITS,
    classify_dataset,
    represented_business_kits,
)
from core.data_preparation import kit_registry


ROOT = Path(__file__).resolve().parents[1]
DATA_PREP_PANEL = ROOT / "frontend" / "src" / "components" / "DataPrepPanel.tsx"
READINESS_BOARD = ROOT / "frontend" / "src" / "components" / "DataReadinessBoard.tsx"


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


def test_ui_does_not_call_dataset_groups_executable_business_kits_or_show_ids():
    panel = DATA_PREP_PANEL.read_text(encoding="utf-8")
    board = READINESS_BOARD.read_text(encoding="utf-8")
    assert "업무영역 {k.business_kit_count}" in panel
    assert "실행 앱 {k.app_count}" in panel
    assert "업무키트 {k.business_kit_count}" not in panel
    assert "<strong style={{ minWidth: 78 }}>{group.id}</strong>" not in board
    assert "<span style={{ flex: 1 }}>{group.name}</span>" not in board
    assert "<strong style={{ flex: 1 }}>{group.name}</strong>" in board
    assert "<strong>{row.output}</strong>" not in board
    assert "{row.dataset_contract_key}</div>" not in board
    assert "이름이 등록되지 않은 업무 결과" in board


def test_local_browser_audit_uses_the_same_business_area_and_app_counts():
    audit = (ROOT / "scripts" / "audit_local_ui.py").read_text(encoding="utf-8")
    assert "업무영역 8" in audit
    assert "실행 앱 7" in audit
    assert "판매·납기·매출 영향" in audit
    assert "전사 시나리오·실적 통합" in audit
    assert "업무키트 8종 모수" not in audit
