"""업무 키트 앱이 다시 원본 표 브라우저로 퇴행하지 않게 하는 구조 회귀."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "frontend" / "src" / "components" / "KitBusinessView.tsx"
PANEL = ROOT / "frontend" / "src" / "components" / "KitAppPanel.tsx"


def test_three_demo_apps_have_business_specific_entry_views():
    src = VIEW.read_text(encoding="utf-8")
    expected = {
        "'APP-01'": "defaultDataset: 'PRC-02'",
        "'APP-03'": "defaultDataset: 'INV-01'",
        "'APP-04'": "defaultDataset: 'FIN-02'",
    }
    for app_id, default_dataset in expected.items():
        assert app_id in src
        assert default_dataset in src
    assert "원료 도입 현황" in src
    assert "재고·생산 영향" in src
    assert "구매원가·현금 전망" in src


def test_business_view_keeps_provenance_and_moves_raw_fields_to_diagnostics():
    src = VIEW.read_text(encoding="utf-8")
    assert "시연용 합성 데이터" in src
    assert "오래된 인증판" in src and "인증 기준" in src
    assert "관리자 진단 — 원본 칸 보기" in src
    assert "TECHNICAL_KEYS" in src
    assert "tenant_id" in src and "lineage_id" in src


def test_business_totals_disclose_the_visible_window_and_mixed_units():
    src = VIEW.read_text(encoding="utf-8")
    assert "현재 표시 범위" in src
    assert "단위 혼합" in src
    assert "통화 혼합" in src
    assert "commonValue(rows, 'quantity_uom')" in src
    assert "commonValue(rows, 'currency')" in src


def test_app_panel_passes_identity_and_uses_business_view():
    src = PANEL.read_text(encoding="utf-8")
    assert "<KitBusinessView" in src
    assert "appId={row.app_id}" in src
    assert "preferredDatasetName(appId, ds)" in src
    assert "datasetDisplayName(appId, d)" in src
    assert "asOf={rows.as_of}" in src and "stale={rows.stale}" in src


def test_materialized_lowercase_dataset_names_keep_business_labels_and_defaults():
    src = VIEW.read_text(encoding="utf-8")
    assert "function canonicalDatasetKey" in src
    assert ".toUpperCase().replace(/_/g, '-')" in src
    assert "canonicalDatasetKey(row.name) === preferred" in src
    assert "datasets[canonicalDatasetKey(dataset.name)]" in src
    assert "const datasetKey = canonicalDatasetKey(datasetName);" in src
    assert "metrics(appId, datasetKey, records, total)" in src


def test_certification_time_is_localized_and_internal_dataset_id_is_secondary():
    src = VIEW.read_text(encoding="utf-8")
    assert "new Intl.DateTimeFormat('ko-KR'" in src
    assert "formatDateTime(asOf)" in src
    assert "title={`데이터셋 식별자: ${datasetName}`}" in src
    assert "{view?.label || datasetLabel}</span>" in src


def test_operating_view_keeps_approval_and_release_ids_secondary():
    src = PANEL.read_text(encoding="utf-8")
    assert "계약 승인이 확인되었습니다." in src
    assert "title={row.approved_by ? `승인 기록: ${row.approved_by}`" in src
    assert "mode === 'build' && (" in src
    assert "title={row.release_id}" in src


def test_public_app_api_keeps_internal_snapshot_ids_out_of_the_client_contract():
    src = (ROOT / "frontend" / "src" / "lib" / "kitAppViewApi.ts").read_text(
        encoding="utf-8")
    assert "as_of: string" in src and "stale: boolean" in src
    assert "snapshot_id:" not in src
