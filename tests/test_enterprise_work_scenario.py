import sqlite3
from types import SimpleNamespace

import pytest

from core import enterprise_work_scenario as ews


def _store(tmp_path):
    return ews.EnterpriseWorkScenarioStore(
        repository=SimpleNamespace(db_path=str(tmp_path / "enterprise.db")))


def _result(app_id="APP-01", fingerprint="fp-result-1"):
    segments = {
        "APP-01": "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
        "APP-03": "CALC.INVENTORY.MATERIAL_SHORTAGE.v1",
        "APP-06": "CALC.PRODUCTION.REVENUE_TIMING.v1",
    }
    refs = list(segments.values())
    return {
        "status": "COMPLETE",
        "query_id": "oq-question",
        "path_fingerprint": "path-topology",
        "request_fingerprint": "request-inputs",
        "result_fingerprint": fingerprint,
        "baseline_id": "bl-enterprise-1",
        "baseline_fingerprint": "bl-fingerprint-1",
        "required_relation_ids": ["rel-1", "rel-2", "rel-3"],
        "capability_fingerprints": {ref: f"cap-{i}" for i, ref in enumerate(refs)},
        "segment_model_versions": {ref: f"model-{i}" for i, ref in enumerate(refs)},
        "used_snapshots": {"LOG-02": "ds-log", "INV-01": "ds-inv",
                           "SLS-01": "ds-sales"},
        "assumptions_used": {"reserved_quantity_zero": True},
        "segment_outputs": {
            refs[0]: {"in_transit_quantity": {"MAT-1": 100.0}},
            refs[1]: {"shortage_quantity": {"MAT-1": 20.0},
                      "producible_quantity": {"PLAN-1": 80.0}},
            refs[2]: {"revenue_shift_days": {"SO-1": 7.0}},
        },
    }


def _scenario(store):
    return store.create(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", name="2026 하반기 원료 수급 대응",
        purpose="구매 지연이 생산·판매에 미치는 전사 영향을 검토",
        actor="planner@a.invalid")


def _record(store, scenario_id, app_id, fingerprint):
    return store.record_contribution(
        scenario_id=scenario_id, app_id=app_id,
        result=_result(app_id, fingerprint), as_of="2026-09-02T00:00:00Z",
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", actor="planner@a.invalid")


def test_세_부서_기여가_모여야_전사_조합_준비다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    assert scenario["coverage"]["ready_for_enterprise"] is False

    _record(store, scenario["scenario_id"], "APP-01", "result-procurement")
    _record(store, scenario["scenario_id"], "APP-03", "result-production")
    partial = store.require(scenario["scenario_id"])
    assert partial["coverage"]["missing_apps"] == ["APP-06"]
    assert partial["coverage"]["ready_for_enterprise"] is False

    _record(store, scenario["scenario_id"], "APP-06", "result-sales")
    complete = store.require(scenario["scenario_id"])
    assert complete["coverage"]["present_apps"] == ["APP-01", "APP-03", "APP-06"]
    assert complete["coverage"]["ready_for_enterprise"] is True


def test_앱별로_자기_계산_구간만_저장한다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    procurement = _record(store, scenario["scenario_id"], "APP-01", "result-p")
    production = _record(store, scenario["scenario_id"], "APP-03", "result-m")
    sales = _record(store, scenario["scenario_id"], "APP-06", "result-s")

    assert set(procurement["values"]) == {"in_transit_quantity"}
    assert set(production["values"]) == {"shortage_quantity", "producible_quantity"}
    assert set(sales["values"]) == {"revenue_shift_days"}
    assert procurement["used_snapshots"]["LOG-02"] == "ds-log"
    assert procurement["required_relation_ids"] == ["rel-1", "rel-2", "rel-3"]


def test_같은_결과_재시도는_중복_기여를_만들지_않는다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    first = _record(store, scenario["scenario_id"], "APP-01", "same-result")
    again = _record(store, scenario["scenario_id"], "APP-01", "same-result")

    assert first["idempotent"] is False
    assert again["idempotent"] is True
    assert again["contribution_id"] == first["contribution_id"]
    assert len(store.require(scenario["scenario_id"])["contributions"]) == 1


def test_전사_앱은_가짜_부서_기여를_등록할_수_없다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    with pytest.raises(ews.WorkScenarioError, match="집계"):
        _record(store, scenario["scenario_id"], "APP-07", "result-enterprise")


@pytest.mark.parametrize("status", ["BLOCKED", ""])
def test_완료되지_않은_계산은_저장하지_않는다(tmp_path, status):
    store = _store(tmp_path)
    scenario = _scenario(store)
    result = _result()
    result["status"] = status
    with pytest.raises(ews.WorkScenarioError, match="완료되지 않은"):
        store.record_contribution(
            scenario_id=scenario["scenario_id"], app_id="APP-01", result=result,
            as_of="2026-09-02T00:00:00Z", tenant_id="tenant-a", instance_id="ki-a",
            scope_node_id="plant-a", entity_mode="REAL", actor="planner@a.invalid")


@pytest.mark.parametrize("missing", ["baseline_id", "baseline_fingerprint"])
def test_기준선_결속이_없는_완료결과도_저장하지_않는다(tmp_path, missing):
    store = _store(tmp_path)
    scenario = _scenario(store)
    result = _result()
    result.pop(missing)
    with pytest.raises(ews.WorkScenarioError, match=missing):
        store.record_contribution(
            scenario_id=scenario["scenario_id"], app_id="APP-01", result=result,
            as_of="2026-09-02T00:00:00Z", tenant_id="tenant-a", instance_id="ki-a",
            scope_node_id="plant-a", entity_mode="REAL", actor="planner@a.invalid")


def test_조직_문맥이_다르면_저장하지_않는다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    with pytest.raises(ews.WorkScenarioError, match="조직 문맥"):
        store.record_contribution(
            scenario_id=scenario["scenario_id"], app_id="APP-01", result=_result(),
            as_of="2026-09-02T00:00:00Z", tenant_id="tenant-b", instance_id="ki-a",
            scope_node_id="plant-a", entity_mode="REAL", actor="planner@a.invalid")


def test_저장소_장애를_빈_목록으로_접지_않는다(tmp_path):
    # 디렉터리를 DB 파일로 주면 sqlite가 열 수 없다.
    store = ews.EnterpriseWorkScenarioStore(
        repository=SimpleNamespace(db_path=str(tmp_path)))
    with pytest.raises(ews.WorkScenarioStoreError):
        store.list_for(tenant_id="tenant-a", instance_id="ki-a")


def test_구버전_기여표는_행을_지우지_않고_기준선_열을_추가한다(tmp_path):
    db_path = tmp_path / "enterprise.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE enterprise_work_scenario_contributions ("
            "contribution_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO enterprise_work_scenario_contributions VALUES (?,?,?)",
            ("old-row", "old-scenario", "2026-01-01T00:00:00Z"))
        conn.commit()
    store = _store(tmp_path)
    with store._connect() as conn:
        columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(enterprise_work_scenario_contributions)").fetchall()}
        kept = conn.execute(
            "SELECT contribution_id FROM enterprise_work_scenario_contributions").fetchall()
    assert {"baseline_id", "baseline_fingerprint"} <= columns
    assert [row[0] for row in kept] == ["old-row"]


def test_전사_조합은_세_부서가_모이기_전에는_숫자를_만들지_않는다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    _record(store, scenario["scenario_id"], "APP-01", "result-p")

    composed = store.compose(scenario["scenario_id"])

    assert composed["status"] == ews.COMPOSITION_BLOCKED
    assert composed["reason_code"] == "DEPARTMENT_RESULTS_REQUIRED"
    assert composed["missing_department_roles"] == ["production", "sales"]
    assert composed["financial_impact"] is None


def test_전사_조합은_운영영향을_결속하고_재무숫자는_계약_전까지_막는다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    for app_id, fingerprint in (
            ("APP-01", "result-p"), ("APP-03", "result-m"),
            ("APP-06", "result-s")):
        _record(store, scenario["scenario_id"], app_id, fingerprint)

    first = store.compose(scenario["scenario_id"])
    again = store.compose(scenario["scenario_id"])

    assert first["status"] == ews.COMPOSITION_READY
    assert first["composition_fingerprint"] == again["composition_fingerprint"]
    assert first["baseline_id"] == "bl-enterprise-1"
    assert first["baseline_fingerprint"] == "bl-fingerprint-1"
    assert [row["department_role"] for row in first["department_results"]] == [
        "procurement", "production", "sales"]
    assert first["financial_impact"] == {
        "status": ews.COMPOSITION_BLOCKED,
        "reason_code": ews.FINANCIAL_BRIDGE_REQUIRED,
        "message": "업무 영향은 결합되었습니다. 손익·현금흐름은 승인된 업무-회계 변환 계약이 연결된 뒤 계산합니다.",
    }


def test_전사_조합은_서로_다른_기준시점을_거부한다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    _record(store, scenario["scenario_id"], "APP-01", "result-p")
    _record(store, scenario["scenario_id"], "APP-03", "result-m")
    store.record_contribution(
        scenario_id=scenario["scenario_id"], app_id="APP-06",
        result=_result("APP-06", "result-s"), as_of="2026-09-03T00:00:00Z",
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", actor="planner@a.invalid")

    with pytest.raises(ews.WorkScenarioError, match="기준시점"):
        store.compose(scenario["scenario_id"])


def test_전사_조합은_서로_다른_기준선을_거부한다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    _record(store, scenario["scenario_id"], "APP-01", "result-p")
    _record(store, scenario["scenario_id"], "APP-03", "result-m")
    sales = _result("APP-06", "result-s")
    sales["baseline_fingerprint"] = "other-baseline"
    store.record_contribution(
        scenario_id=scenario["scenario_id"], app_id="APP-06", result=sales,
        as_of="2026-09-02T00:00:00Z", tenant_id="tenant-a", instance_id="ki-a",
        scope_node_id="plant-a", entity_mode="REAL", actor="planner@a.invalid")

    with pytest.raises(ews.WorkScenarioError, match="기준선이 서로 다릅니다"):
        store.compose(scenario["scenario_id"])


def test_전사_조합은_겹치는_계약키의_다른_인증판을_거부한다(tmp_path):
    store = _store(tmp_path)
    scenario = _scenario(store)
    _record(store, scenario["scenario_id"], "APP-01", "result-p")
    _record(store, scenario["scenario_id"], "APP-03", "result-m")
    sales = _result("APP-06", "result-s")
    sales["used_snapshots"] = {**sales["used_snapshots"], "INV-01": "ds-other"}
    store.record_contribution(
        scenario_id=scenario["scenario_id"], app_id="APP-06", result=sales,
        as_of="2026-09-02T00:00:00Z", tenant_id="tenant-a", instance_id="ki-a",
        scope_node_id="plant-a", entity_mode="REAL", actor="planner@a.invalid")

    with pytest.raises(ews.WorkScenarioError, match="서로 다른 인증판"):
        store.compose(scenario["scenario_id"])
