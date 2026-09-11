"""[M4] 계획 동인 — **가정을 업무 언어로, 파급 계수는 근거와 함께.**

"판매량 +10%" 는 경영진이 읽을 수 있지만 "4000 계정 pct +10" 은 읽을 수 없다.
그런데 동인을 도입하면 새로운 위험이 생긴다 — **파급 계수가 그럴듯한 가짜 인과**가 되는 것이다.
`환율 +10% → 원가 +6%` 는 자명하지 않은데, 한 번 등록되면 경영 보고서에
"환율 때문에 원가가 이만큼 오릅니다"로 인쇄된다.

그래서 이 파일이 잠그는 것은 계산이 아니라 **근거의 강제**다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import planning_drivers as dr
from core import planning_engine as eng
from core import planning_driver_release as driver_release
from core.decision_ledger import DecisionLedger
from core.planning_model import PLAN, PlanningError, PlanningStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = PlanningStore(db_path=str(tmp_path / "planning.db"))
    monkeypatch.setattr("core.planning_model.planning_store", s)
    monkeypatch.setattr(dr, "planning_store", s)
    monkeypatch.setattr(eng, "planning_store", s)
    monkeypatch.setattr(driver_release, "planning_store", s)
    ledger = DecisionLedger(str(tmp_path / "ledger.db"))
    monkeypatch.setattr(driver_release, "decision_ledger", ledger)
    s._test_driver_ledger = ledger
    s.upsert_account("4000", "매출", "REVENUE", sign=1)
    s.upsert_account("5000", "원가", "COGS", sign=-1)
    s.upsert_account("6000", "판관비", "SGA", sign=-1)
    s.put_fact("MNM_BATTERY", "4000", "2027", PLAN, 1000.0)
    s.put_fact("MNM_BATTERY", "5000", "2027", PLAN, 600.0)
    s.put_fact("MNM_BATTERY", "6000", "2027", PLAN, 200.0)
    return s


# ── 근거의 강제 ──────────────────────────────────────────────────────────────
def test_impact_requires_rationale(store):
    """★★ 근거 없는 파급 계수는 창작이다 — 그리고 그 창작이 경영 보고서에 인쇄된다."""
    dr.register_driver("SALES_VOL", "판매량", unit="ton", category="volume")
    with pytest.raises(PlanningError, match="rationale"):
        dr.add_impact("SALES_VOL", "4000", 1.0, "", "실적회귀")


def test_impact_requires_source(store):
    """실적회귀인지 업계자료인지 전문가판단인지 — 출처가 없으면 검증할 수 없다."""
    dr.register_driver("SALES_VOL", "판매량")
    with pytest.raises(PlanningError, match="source"):
        dr.add_impact("SALES_VOL", "4000", 1.0, "판매량과 매출은 비례", "")


def test_unregistered_driver_is_refused(store):
    with pytest.raises(PlanningError, match="등록되지 않은 동인"):
        dr.add_impact("GHOST", "4000", 1.0, "근거", "출처")


# ── 펼치기 ───────────────────────────────────────────────────────────────────
def test_driver_expands_to_accounts_with_elasticity(store):
    """판매량 +10% → 매출 +10%(탄력도 1.0), 원가 +8%(탄력도 0.8)."""
    dr.register_driver("SALES_VOL", "판매량")
    dr.add_impact("SALES_VOL", "4000", 1.0, "판매량과 매출은 비례", "실적회귀 2024-2026", "cfo")
    dr.add_impact("SALES_VOL", "5000", 0.8, "변동비 비중 80%", "원가분석", "cfo")

    rows, warns = dr.expand_driver_assumption("SALES_VOL", 10.0)
    vals = {r["target_code"]: r["value"] for r in rows}
    assert vals["4000"] == 10.0 and vals["5000"] == 8.0
    assert warns == []
    # 펼쳐진 가정에도 근거가 따라붙는다 — 나중에 "왜 8%인가"에 답할 수 있어야 한다.
    assert "탄력도 0.8" in next(r["rationale"] for r in rows if r["target_code"] == "5000")


def test_driver_without_mapping_is_reported_not_silent(store):
    """★★ "판매량 10% 올렸는데 아무것도 안 변했다"의 유일한 단서."""
    dr.register_driver("FX_RATE", "환율")
    rows, warns = dr.expand_driver_assumption("FX_RATE", 10.0)
    assert rows == []
    assert warns and "파급 계수가 없습니다" in warns[0]


def test_unapproved_elasticity_is_flagged_but_not_blocked(store):
    """미승인 계수를 막으면 도입이 멈춘다 — 대신 결과에 표시한다."""
    dr.register_driver("FX_RATE", "환율")
    dr.add_impact("FX_RATE", "5000", 0.6, "수입 원자재 비중", "업계자료")   # approved_by 없음
    rows, warns = dr.expand_driver_assumption("FX_RATE", 10.0)
    assert rows[0]["approved"] is False
    assert any("미승인" in w for w in warns)


def test_non_pct_driver_operator_is_rejected_with_reason(store):
    """동인은 비율 변화만 의미가 있다 — 조용히 무시하지 않고 사유를 남긴다."""
    dr.register_driver("SALES_VOL", "판매량")
    _, warns = dr.expand_assumptions([{"target_kind": "driver", "target_code": "SALES_VOL",
                                       "operator": "set", "value": 100}])
    assert warns and "pct 만 지원" in warns[0]


def test_account_assumptions_pass_through(store):
    """계정 가정은 그대로 통과 — 두 형태가 한 경로로 합류한다."""
    rows, warns = dr.expand_assumptions([
        {"target_kind": "account", "target_code": "4000", "operator": "pct", "value": 5}])
    assert rows[0]["target_code"] == "4000" and warns == []


# ── 엔진 통합 ────────────────────────────────────────────────────────────────
def _scenario(store, sid, target_kind, code, op, val):
    conn = store._connect()
    try:
        conn.execute("INSERT INTO scenarios(scenario_id,name,org_id,tenant_id,"
                     "owner_organization_id,entity_mode,created_at) VALUES(?,?,?,?,?,?,?)",
                     (sid, sid, "MNM_BATTERY", "tenant-a", "node-a", "REAL", "2026-07-29"))
        conn.execute("INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,"
                     "target_code,operator,value,rationale,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (f"a-{sid}", sid, target_kind, code, op, val, "테스트", "2026-07-29"))
        conn.commit()
    finally:
        conn.close()


def test_engine_applies_driver_assumption(store):
    """★★ 시나리오에 동인 가정을 넣으면 여러 계정에 **한 번에** 파급된다."""
    dr.register_driver("SALES_VOL", "판매량")
    dr.add_impact("SALES_VOL", "4000", 1.0, "비례", "실적회귀", "cfo")
    dr.add_impact("SALES_VOL", "5000", 0.8, "변동비 80%", "원가분석", "cfo")
    driver_release.approve(
        "SALES_VOL", "cfo@test.invalid", "파급계수 검토", tenant_id="tenant-a",
        scope_node_id="node-a", entity_mode="REAL", store=store,
        ledger=store._test_driver_ledger)
    _scenario(store, "vol-up", "driver", "SALES_VOL", "pct", 10)

    r = eng.run_scenario("vol-up", "MNM_BATTERY", "2027")
    # 매출 1100, 원가 648, 판관비 200 → 영업이익 252
    assert r["result"]["operating_profit"] == 252.0
    assert r["expanded_count"] == 2          # 동인 하나가 계정 둘로 펼쳐졌다
    assert r["driver_warnings"] == []


def test_execution_uses_the_sealed_impact_not_a_later_draft_edit(store):
    dr.register_driver("SALES_VOL", "판매량")
    dr.add_impact("SALES_VOL", "4000", 1.0, "비례", "실적회귀", "cfo")
    driver_release.approve(
        "SALES_VOL", "cfo@test.invalid", "검토", tenant_id="tenant-a",
        scope_node_id="node-a", entity_mode="REAL", store=store,
        ledger=store._test_driver_ledger)
    conn = store._connect()
    try:
        conn.execute("UPDATE driver_impacts SET elasticity=9 WHERE driver_code='SALES_VOL'")
        conn.commit()
    finally:
        conn.close()
    _scenario(store, "sealed", "driver", "SALES_VOL", "pct", 10)
    result = eng.run_scenario("sealed", "MNM_BATTERY", "2027")
    assert result["result"]["operating_profit"] == 300.0


def test_driver_release_from_another_scope_cannot_run(store):
    dr.register_driver("SALES_VOL", "판매량")
    dr.add_impact("SALES_VOL", "4000", 1.0, "비례", "실적회귀", "cfo")
    driver_release.approve(
        "SALES_VOL", "cfo@test.invalid", "검토", tenant_id="tenant-a",
        scope_node_id="node-other", entity_mode="REAL", store=store,
        ledger=store._test_driver_ledger)
    _scenario(store, "wrong-scope", "driver", "SALES_VOL", "pct", 10)
    with pytest.raises(PlanningError, match="조직 범위가 시나리오와 다릅니다"):
        eng.run_scenario("wrong-scope", "MNM_BATTERY", "2027")


def test_engine_blocks_driver_without_an_approved_release(store):
    """미승인 동인을 0 변화로 접지 않는다 — 0은 영향 없음이라는 거짓 주장이다."""
    dr.register_driver("FX_RATE", "환율")
    _scenario(store, "fx", "driver", "FX_RATE", "pct", 10)

    with pytest.raises(PlanningError, match="승인된 동인 판본"):
        eng.run_scenario("fx", "MNM_BATTERY", "2027")


def test_external_indicator_link_is_recorded_not_auto_injected(store):
    """★ §12 외부 지표 연결은 **표시일 뿐 자동 주입이 아니다**(등급 정책은 그쪽에서 강제된다)."""
    d = dr.register_driver("FX_RATE", "환율", external_code="ECOS.USD_KRW", category="fx")
    assert d["external_code"] == "ECOS.USD_KRW"
    # 연결만으로 값이 들어오지 않는다 — 파급 계수가 없으면 아무 일도 일어나지 않는다.
    rows, warns = dr.expand_driver_assumption("FX_RATE", 5.0)
    assert rows == [] and warns


# ── 외부 지표 실연결 (§12.7 · §12.8) ────────────────────────────────────────
class _FakeExt:
    """외부 인텔리전스 대역 — 등급 정책의 **판정 결과**를 그대로 흉내낸다."""
    def __init__(self, result):
        self._r = result

    def resolve_value(self, code, purpose="baseline_plan", as_of="", vintage=""):
        return dict(self._r, indicator_code=code)


def _patch_ext(monkeypatch, result):
    import core.external_intelligence as ei
    monkeypatch.setattr(ei, "external_intelligence", _FakeExt(result))


def test_external_value_flows_into_driver(store, monkeypatch):
    """★★ 지금까지 `external_code` 는 **표시**일 뿐이었다 — 실제 값이 흐르게 한다."""
    dr.register_driver("FX_RATE", "환율", unit="KRW/USD", external_code="ECOS.USD_KRW")
    _patch_ext(monkeypatch, {"allowed": True, "value": 1400.0, "unit": "KRW/USD",
                             "grade": "gold", "observed_at": "2027-01-31",
                             "vintage": "2027-02-01", "source_id": "ECOS", "note": "n"})

    r = dr.resolve_external_change("FX_RATE", baseline_value=1300.0)
    assert r["usable"] is True
    assert r["pct_change"] == pytest.approx(7.6923, abs=0.001)
    # 재현성: 어느 시점 발표값으로 계산했는지가 결과에 남는다
    assert r["vintage"] == "2027-02-01" and r["grade"] == "gold"


def test_grade_policy_is_not_reimplemented_here(store, monkeypatch):
    """★★ 등급 게이트(§12.2)는 외부 인텔리전스가 강제한다 — 여기서 다시 구현하면
    두 곳이 어긋나고 한쪽만 고쳐졌을 때 **정책이 조용히 뚫린다.**"""
    dr.register_driver("RATE", "금리", external_code="ECOS.BASE_RATE")
    _patch_ext(monkeypatch, {"allowed": False, "value": None, "required_grade": "gold",
                             "available_grade": "bronze",
                             "reason": "기준 계획에는 gold 가 필요합니다.",
                             "next_action": "공식 원천을 등록하십시오."})

    r = dr.resolve_external_change("RATE", purpose="baseline_plan", baseline_value=3.0)
    assert r["usable"] is False
    assert r["required_grade"] == "gold" and r["available_grade"] == "bronze"


def test_unusable_value_is_not_replaced_with_zero(store, monkeypatch):
    """★★ 0% 는 '변화 없음'이라는 **적극적 주장**이고 '모른다'와 완전히 다르다."""
    dr.register_driver("RATE", "금리", external_code="ECOS.BASE_RATE")
    _patch_ext(monkeypatch, {"allowed": False, "value": None, "reason": "관측값이 없습니다."})

    r = dr.resolve_external_change("RATE", baseline_value=3.0)
    assert r["usable"] is False
    assert "pct_change" not in r or r.get("pct_change") is None
    assert "0% 로 대체하지 않았습니다" in r["note"]


def test_driver_without_external_link_says_so(store):
    dr.register_driver("SALES_VOL", "판매량")     # external_code 없음
    r = dr.resolve_external_change("SALES_VOL", baseline_value=100.0)
    assert r["usable"] is False and "연결돼 있지 않습니다" in r["reason"]


def test_without_baseline_no_pct_is_invented(store, monkeypatch):
    """★ 관측값만으로는 '무엇 대비 몇 %'인지 알 수 없다 — 지어내지 않는다."""
    dr.register_driver("FX_RATE", "환율", external_code="ECOS.USD_KRW")
    _patch_ext(monkeypatch, {"allowed": True, "value": 1400.0, "unit": "KRW/USD",
                             "grade": "gold", "observed_at": "2027-01-31",
                             "vintage": "2027-02-01", "source_id": "ECOS"})
    r = dr.resolve_external_change("FX_RATE")
    assert r["usable"] is True and r["pct_change"] is None
    assert "기준값" in r["reason"]


def test_external_lookup_failure_is_reported(store, monkeypatch):
    """외부 모듈 장애를 조용히 0 으로 만들지 않는다."""
    import core.external_intelligence as ei
    dr.register_driver("FX_RATE", "환율", external_code="X")

    class _Boom:
        def resolve_value(self, *a, **k):
            raise RuntimeError("DB down")

    monkeypatch.setattr(ei, "external_intelligence", _Boom())
    r = dr.resolve_external_change("FX_RATE", baseline_value=1300.0)
    assert r["usable"] is False and "조회에 실패" in r["reason"]


# ── 계수를 «고칠» 수 있는가 — 2026-09-11 에 드러난 구멍 ─────────────────────
def test_a_wrong_coefficient_can_be_withdrawn(store):
    """★★★ 종전에는 `add_impact()` 만 있었다 — **더할 수는 있는데 고칠 수가 없었다.**

    같은 (동인, 계정)에 다시 넣으면 `impacts_of()` 가 둘 다 돌려주고
    `expand_driver_assumption()` 이 행마다 가정을 만들어 **겹쳐 쌓는다.**
    즉 「고치려고 다시 넣는」 행동이 조용히 **두 배 적용**이 된다."""
    dr.register_driver("D1", "동인", external_code="")
    dr.add_impact("D1", "5000", 0.80, rationale="첫 판", source="업계자료")
    out = dr.remove_impact("D1", "5000", "someone@test.invalid", reason="부호 방향이 뒤집혔다")
    assert out["removed"] == 1
    assert out["previous"][0]["elasticity"] == 0.80
    assert dr.impacts_of("D1") == []


def test_re_adding_without_removing_stacks(store):
    """★ 위 시험이 «왜» 필요한지 — 안 거두고 다시 넣으면 두 배가 된다."""
    dr.register_driver("D1", "동인", external_code="")
    dr.add_impact("D1", "5000", 0.80, rationale="첫 판", source="업계자료")
    dr.add_impact("D1", "5000", 0.90, rationale="고친 판", source="업계자료")
    rows, _ = dr.expand_driver_assumption("D1", 10.0)
    assert len(rows) == 2, "같은 계정에 두 행이 생겼다 — 합치면 17% 가 적용된다"
    assert sum(r["value"] for r in rows) == pytest.approx(17.0)


def test_an_approved_release_blocks_editing_its_coefficients(store):
    """★★★ 승인된 계수를 «밑에서» 갈아치우면 「우리가 승인한 그 숫자」에 답할 수 없다."""
    dr.register_driver("D1", "동인", external_code="")
    dr.add_impact("D1", "5000", 0.80, rationale="근거", source="업계자료")
    driver_release.approve("D1", "a@test.invalid", "승인", tenant_id="t",
                           scope_node_id="n", entity_mode="REAL")
    with pytest.raises(PlanningError) as e:
        dr.remove_impact("D1", "5000", "someone@test.invalid", reason="고치고 싶다")
    assert "먼저 철회" in str(e.value)


def test_after_revoking_the_coefficient_can_be_fixed(store):
    """철회하면 고칠 수 있다 — 순서가 강제될 뿐 막히는 게 아니다."""
    dr.register_driver("D1", "동인", external_code="")
    dr.add_impact("D1", "5000", 0.80, rationale="근거", source="업계자료")
    driver_release.approve("D1", "a@test.invalid", "승인", tenant_id="t",
                           scope_node_id="n", entity_mode="REAL")
    driver_release.revoke("D1", "a@test.invalid", "부호가 뒤집혔다")
    dr.remove_impact("D1", "5000", "a@test.invalid", reason="부호 정정")
    dr.add_impact("D1", "5000", 0.90, rationale="정정 근거", source="업계자료")
    assert [i["elasticity"] for i in dr.impacts_of("D1")] == [0.90]


def test_withdrawing_a_coefficient_needs_an_actor_and_a_reason(store):
    """계수를 거두는 것도 «판단» 이다 — 근거 없이 지우면 왜 지웠는지 알 수 없다."""
    dr.register_driver("D1", "동인", external_code="")
    dr.add_impact("D1", "5000", 0.80, rationale="근거", source="업계자료")
    with pytest.raises(PlanningError):
        dr.remove_impact("D1", "5000", "", reason="사유")
    with pytest.raises(PlanningError):
        dr.remove_impact("D1", "5000", "a@test.invalid", reason="")


def test_withdrawing_a_missing_coefficient_is_refused(store):
    dr.register_driver("D1", "동인", external_code="")
    with pytest.raises(PlanningError) as e:
        dr.remove_impact("D1", "9999", "a@test.invalid", reason="없는 것")
    assert "등록되지 않은 파급 계수" in str(e.value)
