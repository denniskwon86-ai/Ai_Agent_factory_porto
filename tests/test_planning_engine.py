"""[M4] 경영계획 계산 엔진 — **재현 가능한가, 그리고 모르는 것을 0 으로 두지 않는가.**

명세서 §11.3 은 "실제·계획·예측·시나리오를 절대 섞지 않는다"를, §17.3 은 "세 개의 시나리오를
동일 기준선에서 재현한다"를 요구한다. 이 파일은 그 두 가지가 **코드로 강제되는지**를 본다.

경영 보고에서 가장 위험한 것은 틀린 숫자가 아니라 **틀린 줄 모르는 숫자**다. 그래서 여기서
잠그는 것의 절반은 계산이 아니라 "빠진 것을 빠졌다고 말하는가"이다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import planning_engine as eng
from core.planning_model import (ACTUAL, FORECAST, PLAN, SCENARIO, PlanningError,
                                 PlanningStore)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = PlanningStore(db_path=str(tmp_path / "planning.db"))
    monkeypatch.setattr("core.planning_model.planning_store", s)
    monkeypatch.setattr(eng, "planning_store", s)
    s.upsert_account("4000", "제품매출", "REVENUE", sign=1)
    s.upsert_account("5000", "제조원가", "COGS", sign=-1)
    s.upsert_account("6000", "판관비", "SGA", sign=-1)
    return s


def _baseline(s, org="MNM_BATTERY", period="2027"):
    s.put_fact(org, "4000", period, PLAN, 1000.0)
    s.put_fact(org, "5000", period, PLAN, 600.0)
    s.put_fact(org, "6000", period, PLAN, 200.0)


# ── §11.3 네 가지를 섞지 않는다 ──────────────────────────────────────────────
def test_value_kind_is_required_and_validated(store):
    """★★ 기본값이 없다 — 있으면 호출자가 생각 없이 넣고 '실적처럼 보이는 계획'이 생긴다."""
    with pytest.raises(PlanningError, match="value_kind"):
        store.put_fact("ORG", "4000", "2027", "실적", 100.0)


def test_scenario_value_requires_scenario_id(store):
    """어느 가정에서 나온 숫자인지 모르면 재현할 수 없다."""
    with pytest.raises(PlanningError, match="scenario_id"):
        store.put_fact("ORG", "4000", "2027", SCENARIO, 100.0)


def test_non_scenario_value_cannot_carry_scenario_id(store):
    """★ 시나리오 결과가 실적·계획으로 섞여 들어가는 경로를 막는다."""
    with pytest.raises(PlanningError, match="scenario_id"):
        store.put_fact("ORG", "4000", "2027", ACTUAL, 100.0, scenario_id="scn-1")


def test_kinds_are_stored_separately(store):
    store.put_fact("ORG", "4000", "2027", PLAN, 1000.0)
    store.put_fact("ORG", "4000", "2027", ACTUAL, 900.0)
    store.put_fact("ORG", "4000", "2027", FORECAST, 950.0)
    assert len(store.list_facts(org_id="ORG", value_kind=PLAN)) == 1
    assert store.list_facts(org_id="ORG", value_kind=ACTUAL)[0]["amount"] == 900.0
    assert len(store.list_facts(org_id="ORG")) == 3      # 셋이 공존하되 섞이지 않는다


# ── 손익 계산 ────────────────────────────────────────────────────────────────
def test_pl_arithmetic(store):
    _baseline(store)
    pl = eng.compute_pl(store.list_facts(org_id="MNM_BATTERY", value_kind=PLAN))
    assert pl["gross_profit"] == 400.0        # 1000 - 600
    assert pl["operating_profit"] == 200.0    # 400 - 200
    assert pl["net_profit"] == 200.0
    assert pl["complete"] is True


def test_unmapped_account_is_surfaced_not_dropped(store):
    """★★ 등록되지 않은 계정을 조용히 버리면 **합계가 맞아 보이는데 틀린다.**"""
    _baseline(store)
    store.put_fact("MNM_BATTERY", "9999", "2027", PLAN, 500.0)   # 미등록 계정
    pl = eng.compute_pl(store.list_facts(org_id="MNM_BATTERY", value_kind=PLAN))
    assert pl["complete"] is False
    assert pl["unmapped"][0]["account_code"] == "9999"


# ── 시나리오 재현성 (§17.3) ─────────────────────────────────────────────────
def _scenario(store, sid, code, op, val, name="시나리오"):
    conn = store._connect()
    try:
        conn.execute("INSERT INTO scenarios(scenario_id,name,org_id,created_at) VALUES(?,?,?,?)",
                     (sid, name, "MNM_BATTERY", "2026-07-29"))
        conn.execute("INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,"
                     "target_code,operator,value,rationale,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (f"a-{sid}", sid, "account", code, op, val, "테스트 근거", "2026-07-29"))
        conn.commit()
    finally:
        conn.close()


def test_same_input_gives_same_fingerprint_and_result(store):
    """★★ §17.3 의 '재현한다' — 같은 입력이면 지문도 결과도 같아야 한다."""
    _baseline(store)
    _scenario(store, "scn-a", "4000", "pct", 10)
    r1 = eng.run_scenario("scn-a", "MNM_BATTERY", "2027")
    r2 = eng.run_scenario("scn-a", "MNM_BATTERY", "2027")
    assert r1["input_hash"] == r2["input_hash"]
    assert r1["result"]["net_profit"] == r2["result"]["net_profit"] == 300.0   # 1100-600-200
    assert r1["run_id"] != r2["run_id"]        # 실행 이력은 별개로 남는다


def test_assumption_operators(store):
    _baseline(store)
    _scenario(store, "pct", "5000", "pct", -10)      # 원가 10% 절감
    _scenario(store, "delta", "4000", "delta", 100)  # 매출 +100
    _scenario(store, "set", "6000", "set", 150)      # 판관비 150 고정
    assert eng.run_scenario("pct", "MNM_BATTERY", "2027")["result"]["net_profit"] == 260.0
    assert eng.run_scenario("delta", "MNM_BATTERY", "2027")["result"]["net_profit"] == 300.0
    assert eng.run_scenario("set", "MNM_BATTERY", "2027")["result"]["net_profit"] == 250.0


def test_unapplied_assumption_is_reported(store):
    """★★ "가정을 넣었는데 결과가 그대로"의 유일한 단서 — 조용히 넘기면 아무도 모른다."""
    _baseline(store)
    _scenario(store, "ghost", "7777", "pct", 50)     # 기준선에 없는 계정
    r = eng.run_scenario("ghost", "MNM_BATTERY", "2027")
    assert r["unapplied_assumptions"], "적용되지 않은 가정이 보고되지 않았다"
    assert r["delta"]["net_profit"] == 0.0


def test_empty_baseline_is_refused(store):
    """★ 기준선 없이 계산하면 **0 에서 시작한 숫자가 계획처럼 보인다.**"""
    _scenario(store, "scn-x", "4000", "pct", 10)
    with pytest.raises(PlanningError, match="기준선"):
        eng.run_scenario("scn-x", "MNM_BATTERY", "2027")


def test_scenario_cannot_be_stacked_on_scenario(store):
    """시나리오 위에 시나리오를 얹으면 **무엇이 기준인지 사라진다.**"""
    _baseline(store)
    _scenario(store, "scn-y", "4000", "pct", 10)
    with pytest.raises(PlanningError, match="기준선"):
        eng.run_scenario("scn-y", "MNM_BATTERY", "2027", baseline_kind=SCENARIO)


def test_three_scenarios_on_one_baseline(store):
    """★★ §17.3 파일럿 성공 기준 — 세 시나리오를 **동일 기준선에서** 비교한다."""
    _baseline(store)
    _scenario(store, "base", "4000", "pct", 0, "기본")
    _scenario(store, "aggressive", "4000", "pct", 20, "공격")
    _scenario(store, "risk", "5000", "pct", 15, "위험")
    cmp = eng.compare_scenarios(["base", "aggressive", "risk"], "MNM_BATTERY", "2027")
    assert cmp["same_baseline"] is True
    nets = {s["scenario_id"]: s["net_profit"] for s in cmp["scenarios"]}
    assert nets["base"] == 200.0 and nets["aggressive"] == 400.0 and nets["risk"] == 110.0


def test_persist_is_opt_in(store):
    """탐색적 실행이 기록을 오염시키면 안 된다 — 저장은 명시적 선택이다."""
    _baseline(store)
    _scenario(store, "scn-p", "4000", "pct", 10)
    eng.run_scenario("scn-p", "MNM_BATTERY", "2027")
    assert store.list_facts(org_id="MNM_BATTERY", value_kind=SCENARIO) == []
    eng.run_scenario("scn-p", "MNM_BATTERY", "2027", persist=True)
    assert len(store.list_facts(org_id="MNM_BATTERY", value_kind=SCENARIO)) == 3


# ── 차이 분석 (§17.2 기능 4) ────────────────────────────────────────────────
def test_variance_refuses_when_actual_is_missing(store):
    """★★ 실적이 없는 것과 실적이 0 인 것은 **완전히 다르다.**

    없는 값을 0 으로 두면 "계획 100 · 실적 0 → 100 미달"로 보이지만,
    실제로는 아직 안 들어온 것뿐이다."""
    _baseline(store)
    v = eng.variance("MNM_BATTERY", "2027")
    assert v["comparable"] is False and "입력되지 않았" in v["reason"]


def test_variance_marks_partial_rows(store):
    _baseline(store)
    store.put_fact("MNM_BATTERY", "4000", "2027", ACTUAL, 1100.0)
    store.put_fact("MNM_BATTERY", "5000", "2027", ACTUAL, 650.0)
    # 판관비(6000) 실적은 아직 없다
    v = eng.variance("MNM_BATTERY", "2027")
    assert v["comparable"] is True
    row = next(r for r in v["by_account"] if r["account_code"] == "6000")
    assert row["diff"] is None and row["missing"] == "actual"   # 0 으로 채우지 않는다


# ── 범위 계약이 처음부터 들어 있는가 ────────────────────────────────────────
def test_scope_contract_fields_exist_from_the_start(store):
    """★ 나중에 붙이면 마이그레이션이 필요하고, 경영 데이터의 마이그레이션이 가장 비싸다."""
    _baseline(store)
    f = store.list_facts(org_id="MNM_BATTERY")[0]
    assert f["scope_type"] == "ORG_PRIVATE"          # 기본값은 소유 조직 전용(D-014)
    assert f["owner_organization_id"] == "MNM_BATTERY"
    assert f["classification"] == "INTERNAL" and f["entity_mode"] == "REAL"


def test_other_org_cannot_see_facts(store, monkeypatch):
    """★★ 조직별 손익은 새어 나가면 끝이다 — 범위 필터가 실제로 건다."""
    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "visible_scopes",
                        lambda n: {"MNM_BATTERY", "MNM"} if n == "MNM_BATTERY" else {n})
    _baseline(store)
    assert len(store.list_facts(org_id="MNM_BATTERY", scope_node_id="MNM_BATTERY")) == 3
    assert store.list_facts(org_id="MNM_BATTERY", scope_node_id="MNM_COPPER") == []


# ── API 계약 ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def client(store, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    import api.routes.planning_control as pc

    monkeypatch.setattr(pc, "planning_store", store)
    return TestClient(main.app)


@pytest.mark.parametrize("path", [
    "/api/v1/planning/accounts",
    "/api/v1/planning/facts",
    "/api/v1/planning/scenarios",
    "/api/v1/planning/variance?org_id=X&period=2027",
])
def test_planning_routes_are_reachable(client, path):
    assert client.get(path).status_code != 404, f"{path} 미도달"


def test_api_rejects_missing_value_kind(client):
    """★ 스키마에 기본값이 없으므로 누락은 422 다 — '실적처럼 보이는 계획'이 생기지 않는다."""
    r = client.post("/api/v1/planning/facts",
                    json={"org_id": "O", "account_code": "4000", "period": "2027", "amount": 1})
    assert r.status_code == 422


def test_api_requires_rationale_for_assumptions(client):
    """★★ 근거 없는 가정은 재현은 되지만 **설명되지 않는다** — 경영 보고엔 둘 다 필요하다."""
    client.post("/api/v1/planning/scenarios",
                json={"scenario_id": "s1", "name": "테스트", "org_id": "MNM_BATTERY"})
    r = client.post("/api/v1/planning/scenarios/s1/assumptions",
                    json={"target_code": "4000", "operator": "pct", "value": 10})
    assert r.status_code == 400 and "근거" in r.json()["detail"]


def test_api_compare_exposes_same_baseline_flag(client, store):
    """`same_baseline=false` 인 비교는 무효다 — 응답이 그 사실을 숨기지 않는다."""
    _baseline(store)
    for sid, val in (("a", 0), ("b", 20)):
        client.post("/api/v1/planning/scenarios",
                    json={"scenario_id": sid, "name": sid, "org_id": "MNM_BATTERY"})
        client.post(f"/api/v1/planning/scenarios/{sid}/assumptions",
                    json={"target_code": "4000", "operator": "pct", "value": val,
                          "rationale": "테스트"})
    r = client.post("/api/v1/planning/scenarios/compare",
                    json={"scenario_ids": ["a", "b"], "org_id": "MNM_BATTERY", "period": "2027"})
    assert r.status_code == 200
    assert "same_baseline" in r.json()["data"]


# ── 현금흐름 (§17.2 기능 6) ──────────────────────────────────────────────────
def _cf_accounts(s):
    s.upsert_account("7100", "감가상각비", "DEPRECIATION", sign=-1)
    s.upsert_account("7200", "운전자본증감", "WORKING_CAPITAL", sign=-1)
    s.upsert_account("7300", "설비투자", "CAPEX", sign=-1)
    s.upsert_account("7400", "차입금증감", "FINANCING", sign=1)


def test_cash_flow_refuses_when_inputs_are_missing(store):
    """★★ 이 기능의 핵심은 계산이 아니라 **거절**이다.

    감가상각·운전자본·CAPEX 없이 0 으로 채우면 '영업현금흐름 = 순이익'이 되어
    **현금이 충분한 것처럼 보인다.** 흑자도산은 정확히 그 착시에서 온다."""
    _baseline(store)
    cf = eng.cash_flow_for("MNM_BATTERY", "2027")
    assert cf["computable"] is False
    assert set(cf["missing"]) == {"DEPRECIATION", "WORKING_CAPITAL", "CAPEX"}
    assert "흑자도산" in cf["note"]


def test_cash_flow_names_exactly_what_is_missing(store):
    """무엇이 없는지 이름을 대야 사용자가 채울 수 있다."""
    _baseline(store)
    _cf_accounts(store)
    store.put_fact("MNM_BATTERY", "7100", "2027", PLAN, 50.0)   # 감가상각만 입력
    cf = eng.cash_flow_for("MNM_BATTERY", "2027")
    assert cf["computable"] is False
    assert set(cf["missing"]) == {"WORKING_CAPITAL", "CAPEX"}


def test_cash_flow_arithmetic(store):
    """영업 = 순이익 + 감가상각 − 운전자본증가 / 투자 = −CAPEX / FCF = 영업 + 투자."""
    _baseline(store)
    _cf_accounts(store)
    store.put_fact("MNM_BATTERY", "7100", "2027", PLAN, 50.0)    # 감가상각
    store.put_fact("MNM_BATTERY", "7200", "2027", PLAN, 30.0)    # 운전자본 증가
    store.put_fact("MNM_BATTERY", "7300", "2027", PLAN, 80.0)    # CAPEX
    store.put_fact("MNM_BATTERY", "7400", "2027", PLAN, 100.0)   # 차입

    cf = eng.cash_flow_for("MNM_BATTERY", "2027")
    assert cf["computable"] is True
    assert cf["net_profit"] == 200.0
    assert cf["operating_cf"] == 220.0        # 200 + 50 - 30
    assert cf["investing_cf"] == -80.0
    assert cf["free_cash_flow"] == 140.0      # 220 - 80
    assert cf["net_change"] == 240.0          # + 재무 100


def test_cf_accounts_do_not_pollute_the_pl(store):
    """★★ 감가상각은 비용이지만 현금 유출이 아니고, CAPEX 는 현금 유출이지만 당기 비용이 아니다.

    두 표를 섞으면 "이익이 나는데 현금이 없다"는 현실을 설명할 수 없다.
    그리고 현금흐름 계정을 `unmapped` 로 처리하면 누락 경고가 상시 떠서
    **진짜 누락이 그 소음에 묻힌다.**"""
    _baseline(store)
    _cf_accounts(store)
    store.put_fact("MNM_BATTERY", "7300", "2027", PLAN, 80.0)
    pl = eng.compute_pl(store.list_facts(org_id="MNM_BATTERY", value_kind=PLAN))
    assert pl["operating_profit"] == 200.0      # CAPEX 가 손익을 건드리지 않는다
    assert pl["complete"] is True               # 누락 경고가 아니다
    assert "7300" in pl["excluded_non_pl"]      # 제외됐다는 사실은 남는다


def test_cash_flow_carries_pl_incompleteness(store):
    """손익이 불완전하면 현금흐름도 그만큼 불완전하다 — 그 사실을 물고 간다."""
    _baseline(store)
    _cf_accounts(store)
    for code, amt in (("7100", 50.0), ("7200", 30.0), ("7300", 80.0)):
        store.put_fact("MNM_BATTERY", code, "2027", PLAN, amt)
    store.put_fact("MNM_BATTERY", "9999", "2027", PLAN, 10.0)   # 미등록 계정
    cf = eng.cash_flow_for("MNM_BATTERY", "2027")
    assert cf["computable"] is True and cf["pl_complete"] is False


def test_empty_input_does_not_produce_zero_cash_flow(store):
    """빈 입력으로 계산하면 **0 이 결과처럼 보인다.**"""
    cf = eng.cash_flow_for("NOBODY", "2027")
    assert cf["computable"] is False and cf["missing"] == ["ALL"]
