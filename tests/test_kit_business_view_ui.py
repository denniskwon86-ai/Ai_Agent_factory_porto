"""업무 키트 앱이 다시 원본 표 브라우저로 퇴행하지 않게 하는 구조 회귀."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "frontend" / "src" / "components" / "KitBusinessView.tsx"
PANEL = ROOT / "frontend" / "src" / "components" / "KitAppPanel.tsx"


def test_seven_kit_apps_have_business_specific_entry_views():
    src = VIEW.read_text(encoding="utf-8")
    expected = {
        "'APP-01'": "defaultDataset: 'PRC-02'",
        "'APP-02'": "defaultDataset: 'LOG-03'",
        "'APP-03'": "defaultDataset: 'INV-01'",
        "'APP-04'": "defaultDataset: 'FIN-02'",
        "'APP-05'": "defaultDataset: 'MDM-02'",
        "'APP-06'": "defaultDataset: 'SLS-01'",
        "'APP-07'": "defaultDataset: 'SIM-02'",
    }
    for app_id, default_dataset in expected.items():
        assert app_id in src
        assert default_dataset in src
    assert "원료 도입 현황" in src
    assert "물류 사건 확인" in src
    assert "재고·생산 영향" in src
    assert "구매원가·현금 전망" in src
    assert "공급 위험·대체안" in src
    assert "판매·납기·매출 영향" in src
    assert "전사 시나리오·실적 통합" in src


def test_app_02_does_not_promise_native_input_before_the_input_loop_exists():
    panel = PANEL.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert "label: '물류 사건 확인'" in panel
    assert "현업 입력은 후속 단계에서 지원합니다." in panel
    assert "현업 입력은 후속 단계입니다." in view
    assert "appLabel(row)" in panel


def test_app_05_does_not_turn_missing_calculations_into_safe_scores_or_recommendations():
    panel = PANEL.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert "위험 계산과 대체 공급사 추천은 지원 대기입니다." in panel
    assert "계산 점수가 아닌 공급사 기준정보" in view
    assert "등급 근거 없음" in view
    assert "등록 고위험" in view
    assert "value: grades.length ?" in view


def test_app_05_normalizes_csv_boolean_and_material_list_for_people():
    src = VIEW.read_text(encoding="utf-8")
    assert "function booleanValue" in src
    assert "normalized === 'TRUE'" in src and "normalized === 'FALSE'" in src
    assert "active ? '사용' : '중지'" in src
    assert "function listValue" in src
    assert "parsed.map(String).join(', ')" in src
    assert "rows.map((row) => booleanValue(row.active))" in src


def test_sales_and_enterprise_apps_show_business_specific_metrics():
    src = VIEW.read_text(encoding="utf-8")
    assert "실제 출하일이 약속일보다 늦은 표시 건" in src
    assert "sum(rows, 'shipped_quantity')" in src
    assert "APPROVED_FOR_DEMO" in src
    assert "현재 표시 범위의 시나리오 동인" in src


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


def test_active_department_and_enterprise_apps_open_the_real_path_calculation_journey():
    panel = PANEL.read_text(encoding="utf-8")
    operations = (ROOT / "frontend" / "src" / "components" / "KitOperationsPanel.tsx").read_text(
        encoding="utf-8")
    path_panel = (ROOT / "frontend" / "src" / "components" / "PathCalcPanel.tsx").read_text(
        encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    for app_id in ("APP-01", "APP-03", "APP-06", "APP-07"):
        assert f"'{app_id}'" in panel
    assert "'APP-02': '전사 영향 시뮬레이션'" not in panel
    assert "row.lifecycle_state === 'active'" in panel
    assert "onOpenSimulation(instanceId, row.app_id)" in panel
    assert "onOpenSimulation={onOpenSimulation}" in operations
    assert "initialInstanceId" in path_panel
    assert "initialAppId" in path_panel
    assert "rows.some" in path_panel
    assert "setPathCalcInitialInstanceId(instanceId)" in app
    assert "setPathCalcInitialAppId(appId)" in app
    assert "setSpace('path')" in app


def test_department_results_are_saved_to_one_enterprise_work_scenario_without_typing_ids():
    panel = (ROOT / "frontend" / "src" / "components" / "PathCalcPanel.tsx").read_text(
        encoding="utf-8")
    api = (ROOT / "frontend" / "src" / "lib" / "calculationApi.ts").read_text(
        encoding="utf-8")

    assert "createEnterpriseWorkScenario" in panel
    assert "saveDepartmentContribution" in panel
    assert "부서 결과 저장" in panel
    assert "전사 조합 준비 완료" in panel
    assert "APP-07은" not in panel  # 사용자 화면은 앱 코드가 아니라 역할로 설명한다.
    assert "전사 통합 앱은 별도 부서 결과를 만들지 않습니다" in panel
    assert "/work-scenarios" in api
    assert "/contributions/" in api
    # 선택값으로는 내부 ID가 필요하지만 option 본문에는 사람용 이름만 보여야 한다.
    assert ">{scenario.scenario_id}<" not in panel
    assert "{scenario.name} · {scenario.status" in panel


def test_materialized_lowercase_dataset_names_keep_business_labels_and_defaults():
    src = VIEW.read_text(encoding="utf-8")
    assert "function canonicalDatasetKey" in src
    assert ".toUpperCase().replace(/_/g, '-')" in src
    assert "canonicalDatasetKey(row.name) === preferred" in src
    assert "datasets[canonicalDatasetKey(dataset.name)]" in src
    assert "const datasetKey = canonicalDatasetKey(datasetName);" in src
    assert "metrics(appId, datasetKey, records, total)" in src


def test_certification_time_is_localized_and_internal_dataset_id_is_not_exposed():
    src = VIEW.read_text(encoding="utf-8")
    assert "new Intl.DateTimeFormat('ko-KR'" in src
    assert "formatDateTime(asOf)" in src
    assert "데이터셋 식별자: ${datasetName}" not in src
    assert "{view?.label || datasetLabel}</span>" in src


def test_logistics_events_use_business_labels_and_local_datetimes():
    src = VIEW.read_text(encoding="utf-8")
    assert "BOOKED: '예약'" in src
    assert "ATA: '실제 도착'" in src
    assert "UNLOADED: '하역 완료'" in src
    assert "ORIGIN: '출발지'" in src and "DESTINATION: '도착지'" in src
    assert "key.endsWith('_at')" in src
    assert "return formatDateTime(value)" in src


def test_operating_view_keeps_approval_but_hides_actor_and_release_ids():
    src = PANEL.read_text(encoding="utf-8")
    assert "계약 승인이 확인되었습니다." in src
    assert "승인 권한자의 승인이 확인되었습니다." in src
    assert "승인 기록: ${row.approved_by}" not in src
    assert "title={row.release_id}" not in src
    assert "{row.app_id} · 준비" not in src


def test_public_app_api_keeps_internal_snapshot_ids_out_of_the_client_contract():
    src = (ROOT / "frontend" / "src" / "lib" / "kitAppViewApi.ts").read_text(
        encoding="utf-8")
    assert "as_of: string" in src and "stale: boolean" in src
    assert "snapshot_id:" not in src

def test_enterprise_app_composes_financials_and_saves_the_same_result_as_a_decision():
    panel = (ROOT / "frontend" / "src" / "components" /
             "PathCalcPanel.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "src" / "lib" / "calculationApi.ts").read_text(
        encoding="utf-8")
    assert "getEnterpriseComposition" in panel
    assert "전사 운영 영향 조합" in panel
    assert "세 부서 운영 영향 결합 완료" in panel
    assert "composition.financial_impact?.message" in panel
    assert "createEnterpriseDecision" in panel
    assert "의사결정 안건으로 저장" in panel
    assert "seen_composition_fingerprint" in api
    assert "seen_financial_result_fingerprint" in api
    assert "FINANCIAL_BRIDGE_REQUIRED" in api
    assert "/composition`" in api
