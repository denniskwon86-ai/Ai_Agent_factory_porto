from types import SimpleNamespace

import pytest

from core.decision_ledger import DecisionLedger
from core import enterprise_work_scenario as ews
from core import financial_bridge_contract as fbc


def _contract(account="1200"):
    return {
        "model_version": fbc.MODEL_VERSION,
        "reporting_currency": fbc.REPORTING_CURRENCY,
        "exchange_rate_source": fbc.EXCHANGE_RATE_SOURCE,
        "source_snapshots": {"MDM-07": "snapshot-accounts",
                             "EXT-01": "snapshot-exchange-rate"},
        "rules": [
            {"rule_id": "purchase_working_capital",
             "source_metrics": ["in_transit_quantity"],
             "target_account_codes": [account, "2000"],
             "formula_ref": "BRIDGE.PURCHASE_WC.v1", "evidence_refs": ["MDM-07"]},
            {"rule_id": "production_margin",
             "source_metrics": ["shortage_quantity", "producible_quantity"],
             "target_account_codes": ["5000", "5100"],
             "formula_ref": "BRIDGE.PRODUCTION_MARGIN.v1",
             "evidence_refs": ["MDM-05", "MDM-07"]},
            {"rule_id": "revenue_recognition",
             "source_metrics": ["revenue_shift_days"],
             "target_account_codes": ["4000", "1100"],
             "formula_ref": "BRIDGE.REVENUE_TIMING.v1",
             "evidence_refs": ["MDM-07", "SLS-01"]},
            {"rule_id": "currency_translation",
             "source_metrics": ["transaction_currency", "reporting_currency",
                                "exchange_rate"],
             "target_account_codes": ["1100", "1200", "2000", "4000", "5000", "5100"],
             "formula_ref": "BRIDGE.CURRENCY_TRANSLATION.v1",
             "evidence_refs": ["EXT-01", "MDM-07"]},
        ],
    }


def _account_rows():
    return [
        {"account_id": "1100", "account_name": "매출채권", "account_type": "ASSET",
         "cost_element": "AR", "currency": "KRW", "active": "True"},
        {"account_id": "1200", "account_name": "재고자산", "account_type": "ASSET",
         "cost_element": "INVENTORY", "currency": "KRW", "active": "True"},
        {"account_id": "2000", "account_name": "매입채무", "account_type": "LIABILITY",
         "cost_element": "AP", "currency": "KRW", "active": "True"},
        {"account_id": "4000", "account_name": "제품매출", "account_type": "REVENUE",
         "cost_element": "REVENUE", "currency": "KRW", "active": "True"},
        {"account_id": "5000", "account_name": "재료비", "account_type": "EXPENSE",
         "cost_element": "MATERIAL_COST", "currency": "KRW", "active": "True"},
        {"account_id": "5100", "account_name": "가공비", "account_type": "EXPENSE",
         "cost_element": "CONVERSION_COST", "currency": "KRW", "active": "True"},
    ]


def _env(tmp_path):
    repo = SimpleNamespace(db_path=str(tmp_path / "enterprise.db"))
    ledger = DecisionLedger(str(tmp_path / "ledger.db"))
    return fbc.FinancialBridgeContractStore(repo, ledger), repo, ledger


def _draft(store, **overrides):
    values = dict(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", contract=_contract(),
        effective_from="2026-01-01T00:00:00Z", effective_to="",
        actor="author@a.invalid")
    values.update(overrides)
    return store.create_draft(**values)


def _approve(store, draft):
    return store.approve(
        draft["contract_id"], seen_fingerprint=draft["fingerprint"],
        actor="controller@a.invalid", rationale="회계 정책과 계정 매핑 검토 완료")


def test_네_변환영역이_모두_없으면_초안을_만들지_않는다(tmp_path):
    store, _repo, _ledger = _env(tmp_path)
    contract = _contract()
    contract["rules"] = contract["rules"][:-1]
    with pytest.raises(fbc.FinancialBridgeContractError, match="Missing"):
        _draft(store, contract=contract)


def test_출처지표나_계정이_틀리면_계약을_거부한다(tmp_path):
    store, _repo, _ledger = _env(tmp_path)
    contract = _contract()
    contract["rules"][0]["source_metrics"] = ["arbitrary_number"]
    with pytest.raises(fbc.FinancialBridgeContractError, match="source_metrics"):
        _draft(store, contract=contract)


def test_인증계정의_의미로_제안하고_사용자_코드입력을_받지_않는다():
    got = fbc.build_proposal(
        account_rows=_account_rows(), account_snapshot_id="accounts-v1",
        exchange_rate_snapshot_id="fx-v1")
    by_rule = {row["rule_id"]: row for row in got["contract"]["rules"]}

    assert by_rule["purchase_working_capital"]["target_account_codes"] == ["1200", "2000"]
    assert by_rule["production_margin"]["target_account_codes"] == ["5000", "5100"]
    assert by_rule["revenue_recognition"]["target_account_codes"] == ["1100", "4000"]
    assert got["contract"]["exchange_rate_source"] == "EXT-01"
    assert got["proposal_fingerprint"]


def test_필수_계정의미가_없거나_둘이면_임의선택하지_않는다():
    missing = [row for row in _account_rows() if row["cost_element"] != "AP"]
    with pytest.raises(fbc.FinancialBridgeContractError, match="AP"):
        fbc.build_proposal(
            account_rows=missing, account_snapshot_id="accounts-v1",
            exchange_rate_snapshot_id="fx-v1")

    duplicate = _account_rows() + [{**_account_rows()[0], "account_id": "1110"}]
    with pytest.raises(fbc.FinancialBridgeContractError, match="AR"):
        fbc.build_proposal(
            account_rows=duplicate, account_snapshot_id="accounts-v1",
            exchange_rate_snapshot_id="fx-v1")


def test_산식과_근거_계약키는_닫힌_목록이다(tmp_path):
    store, _repo, _ledger = _env(tmp_path)
    contract = _contract()
    contract["rules"][3]["evidence_refs"] = ["EXT-FX"]
    with pytest.raises(fbc.FinancialBridgeContractError, match="evidence_refs"):
        _draft(store, contract=contract)

    contract = _contract()
    contract["rules"][0]["target_account_codes"] = ["사용자 입력 문장"]
    with pytest.raises(fbc.FinancialBridgeContractError, match="account"):
        _draft(store, contract=contract)


def test_내용과_문맥이_바뀌면_새_판과_새_지문이다(tmp_path):
    store, _repo, _ledger = _env(tmp_path)
    first = _draft(store)
    second = _draft(store, contract=_contract("1210"))
    assert (first["revision"], second["revision"]) == (1, 2)
    assert first["fingerprint"] != second["fingerprint"]
    other = _draft(store, scope_node_id="plant-b")
    assert other["revision"] == 1
    assert other["fingerprint"] != first["fingerprint"]


def test_초안은_자동승인되지_않고_작성자_자기승인도_막는다(tmp_path):
    store, _repo, _ledger = _env(tmp_path)
    draft = _draft(store)
    assert draft["status"] == fbc.DRAFT
    assert store.effective(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", as_of="2026-09-02T00:00:00Z") is None
    with pytest.raises(fbc.FinancialBridgeContractError, match="drafter"):
        store.approve(draft["contract_id"], seen_fingerprint=draft["fingerprint"],
                      actor="AUTHOR@a.invalid", rationale="self")


def test_승인된_판만_유효기간과_문맥에_맞을_때_해석된다(tmp_path):
    store, _repo, _ledger = _env(tmp_path)
    approved = _approve(store, _draft(store, effective_to="2027-01-01T00:00:00Z"))
    got = store.effective(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", as_of="2026-09-02T00:00:00Z")
    assert got["contract_id"] == approved["contract_id"]
    assert store.effective(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-b",
        entity_mode="REAL", as_of="2026-09-02T00:00:00Z") is None
    assert store.effective(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", as_of="2027-01-01T00:00:00Z") is None


def test_철회는_원승인을_죽이고_다른_대상을_철회할_수_없다(tmp_path):
    store, _repo, ledger = _env(tmp_path)
    approved = _approve(store, _draft(store))
    with pytest.raises(Exception, match="대상"):
        ledger.append(
            event_type=fbc.EVENT_REVOKED, subject_type=fbc.SUBJECT_TYPE,
            subject_id="different", actor_type="user", actor_id="x",
            parent_event_id=approved["ledger_event_id"])
    revoked = store.revoke(
        approved["contract_id"], actor="controller@a.invalid", rationale="정책 변경")
    assert revoked["status"] == fbc.REVOKED
    assert store.effective(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", as_of="2026-09-02T00:00:00Z") is None


def test_승인후_본문변조는_지문불일치로_실패한다(tmp_path):
    store, repo, _ledger = _env(tmp_path)
    approved = _approve(store, _draft(store))
    import sqlite3
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute(
            "UPDATE financial_bridge_contracts SET contract_json=? WHERE contract_id=?",
            ('{"model_version":"tampered"}', approved["contract_id"]))
    with pytest.raises(fbc.FinancialBridgeStoreError, match="contract"):
        store.effective(
            tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
            entity_mode="REAL", as_of="2026-09-02T00:00:00Z")


def test_APP07은_승인전과_승인후_모두_재무숫자를_만들지_않는다(tmp_path):
    bridge, repo, ledger = _env(tmp_path)
    scenario_store = ews.EnterpriseWorkScenarioStore(repo, ledger)
    scenario = scenario_store.create(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", name="전사 조합", purpose="재무 관문 확인",
        actor="planner@a.invalid")

    def result(app_id, fp):
        segment = ews.APP_SEGMENTS[app_id][1]
        return {
            "status": "COMPLETE", "query_id": "q", "path_fingerprint": "path",
            "request_fingerprint": "request", "result_fingerprint": fp,
            "baseline_id": "baseline-financial-bridge",
            "baseline_fingerprint": "baseline-financial-bridge-fp",
            "required_relation_ids": ["rel"], "capability_fingerprints": {segment: "cap"},
            "segment_model_versions": {segment: "model"},
            "used_snapshots": {app_id: "snapshot-" + app_id},
            "assumptions_used": {}, "segment_outputs": {segment: {"metric": 1}},
        }

    for app_id in ews.REQUIRED_APPS:
        scenario_store.record_contribution(
            scenario_id=scenario["scenario_id"], app_id=app_id,
            result=result(app_id, "result-" + app_id),
            as_of="2026-09-02T00:00:00Z", tenant_id="tenant-a", instance_id="ki-a",
            scope_node_id="plant-a", entity_mode="REAL", actor="planner@a.invalid")
    before = scenario_store.compose(scenario["scenario_id"])
    assert before["financial_impact"]["reason_code"] == ews.FINANCIAL_BRIDGE_REQUIRED

    _approve(bridge, _draft(bridge))
    after = scenario_store.compose(scenario["scenario_id"])
    assert after["financial_impact"]["reason_code"] == ews.FINANCIAL_MODEL_REQUIRED
    assert "values" not in after["financial_impact"]


def test_새_승인판은_기존판을_DB와_원장에서_함께_대체한다(tmp_path):
    store, _repo, ledger = _env(tmp_path)
    first = _approve(store, _draft(store))
    second_draft = _draft(store, contract=_contract("1210"))
    second = _approve(store, second_draft)

    rows = store.list_for(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL")
    by_id = {row["contract_id"]: row for row in rows}
    assert by_id[first["contract_id"]]["status"] == fbc.SUPERSEDED
    assert by_id[second["contract_id"]]["status"] == fbc.APPROVED
    assert ledger.has_invalidating_child(
        first["ledger_event_id"], (fbc.EVENT_REVOKED,)) is True
    effective = store.effective(
        tenant_id="tenant-a", instance_id="ki-a", scope_node_id="plant-a",
        entity_mode="REAL", as_of="2026-09-02T00:00:00Z")
    assert effective["contract_id"] == second["contract_id"]
