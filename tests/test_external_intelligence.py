# ==========================================
# [§12] 외부환경 인텔리전스 — 원천 등록부 · 등급 정책 · 재현성
#
# §12.1 이 이 기능의 목적을 못박았다: "인터넷에서 가장 빠른 정보를 수집하는 것이 아니라,
#   출처·발표 시점·수정 이력·검증 상태가 명확한 외부 데이터를 **안전하게 연결**하는 것".
# 그래서 이 테스트는 수집 능력이 아니라 **안전장치**를 본다.
#
# 핵심 불변식 (§12.2):
#   기준 계획·공식 수치에는 Gold 만 쓴다. Silver/Bronze 로는 **값 자체를 돌려주지 않는다** —
#   경고만 하고 값을 주면 결국 쓰이고, 그 순간 "기사값으로 기준 계획이 바뀌는" 상황이 된다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.external_intelligence import (ExternalIntelligence,
                                        ExternalIntelligenceError)


@pytest.fixture
def ei(tmp_path):
    x = ExternalIntelligence(db_path=str(tmp_path / "ex.db"))
    x.upsert_indicator("ext_fx", "환율", required_grade="gold", acceptable_latency="1일",
                       next_action="공식 API 를 등록하십시오.")
    return x


def _gold_source(ei, approve=True):
    s = ei.register_source("중앙은행 공식 API", "API", trust_grade="gold")
    if approve:
        ei.approve_source(s["source_id"], "kim")
    return s["source_id"]


# ── 원천 등록부 (§12.4) ───────────────────────────────────────────────────
def test_source_is_disabled_until_approved(ei):
    """★★ 등록 즉시 활성이면 누구나 원천을 늘려 기준 계획의 근거를 바꿀 수 있다."""
    s = ei.register_source("어떤 블로그", "WEB")
    assert s["enabled"] == 0
    assert ei.list_sources(enabled_only=True) == []
    ei.approve_source(s["source_id"], "kim")
    assert len(ei.list_sources(enabled_only=True)) == 1


def test_approval_requires_an_approver(ei):
    s = ei.register_source("X", "API")
    with pytest.raises(ExternalIntelligenceError):
        ei.approve_source(s["source_id"], "")


def test_source_priority_follows_spec_order(ei):
    """§12.4 우선순위: 공식 API → CSV → RSS → 제공자 API → 보고서 → WEB."""
    ei.register_source("웹", "WEB")
    ei.register_source("공식 API", "API")
    ei.register_source("CSV", "CSV")
    assert [s["source_type"] for s in ei.list_sources()] == ["API", "CSV", "WEB"]


def test_unapproved_source_cannot_supply_values(ei):
    """★★ §12.4 "승인된 원천만 등록하고 수집한다"."""
    sid = _gold_source(ei, approve=False)
    with pytest.raises(ExternalIntelligenceError) as e:
        ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="2026-07-05",
                              grade="gold", source_id=sid)
    assert "승인되지 않은 원천" in str(e.value)


def test_value_cannot_outrank_its_source(ei):
    """★ 출처보다 값이 더 신뢰될 수는 없다 — 등급 세탁을 막는다."""
    s = ei.register_source("시장 블로그", "WEB", trust_grade="bronze")
    ei.approve_source(s["source_id"], "kim")
    with pytest.raises(ExternalIntelligenceError) as e:
        ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="v1",
                              grade="gold", source_id=s["source_id"])
    assert "출처보다 값이 더 신뢰될 수는 없습니다" in str(e.value)


# ── 재현성: vintage (§12.5) ───────────────────────────────────────────────
def test_vintage_is_mandatory(ei):
    """★★ 없으면 "이 계획이 당시 어떤 발표값을 썼는지" 재현할 수 없다."""
    with pytest.raises(ExternalIntelligenceError) as e:
        ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="", grade="gold")
    assert "vintage" in str(e.value)


def test_revised_value_does_not_erase_the_original(ei):
    """★★ 같은 시점의 값이 나중에 수정돼도 **당시 발표값으로 조회**할 수 있어야 한다."""
    sid = _gold_source(ei)
    ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="2026-07-05",
                          grade="gold", source_id=sid, quality_status="VALIDATED")
    ei.record_observation("ext_fx", "2026-07-01", 1390.7, vintage="2026-08-10",
                          grade="gold", source_id=sid, quality_status="VALIDATED")
    assert len(ei.list_observations("ext_fx")) == 2
    old = ei.resolve_value("ext_fx", "baseline_plan", vintage="2026-07-05")
    assert old["value"] == 1385.0, "과거 계획은 당시 발표값으로 재현돼야 한다"
    assert ei.resolve_value("ext_fx", "baseline_plan")["value"] == 1390.7


def test_as_of_excludes_future_observations(ei):
    """미래 관측값이 과거 시점 계산에 섞이면 백테스트가 거짓이 된다."""
    sid = _gold_source(ei)
    for d, v in (("2026-06-01", 1300.0), ("2026-07-01", 1385.0)):
        ei.record_observation("ext_fx", d, v, vintage=d, grade="gold", source_id=sid,
                              quality_status="VALIDATED")
    assert ei.resolve_value("ext_fx", "baseline_plan", as_of="2026-06-15")["value"] == 1300.0


# ── 등급 정책 강제 (§12.2) — 이 모듈의 핵심 ───────────────────────────────
def test_silver_cannot_be_used_for_baseline_plan(ei):
    """★★ 경고만 하고 값을 주면 결국 쓰인다. `value` 자체가 None 이어야 한다."""
    ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="v1", grade="silver")
    r = ei.resolve_value("ext_fx", "baseline_plan")
    assert r["allowed"] is False and r["value"] is None
    assert r["required_grade"] == "gold" and r["available_grade"] == "silver"
    assert r["next_action"]


def test_silver_is_fine_for_scenario(ei):
    """§12.2 상 Silver 는 전망·시나리오에 쓸 수 있다 — 전부 막으면 시나리오를 못 만든다."""
    ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="v1", grade="silver")
    r = ei.resolve_value("ext_fx", "scenario")
    assert r["allowed"] is True and r["value"] == 1385.0


def test_bronze_is_only_for_detection(ei):
    ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="v1", grade="bronze")
    assert ei.resolve_value("ext_fx", "scenario")["allowed"] is False
    assert ei.resolve_value("ext_fx", "detection")["allowed"] is True


def test_gold_is_preferred_when_both_exist(ei):
    """같은 시점에 등급이 섞여 있으면 높은 등급을 쓴다."""
    sid = _gold_source(ei)
    ei.record_observation("ext_fx", "2026-07-01", 1400.0, vintage="v1", grade="silver")
    ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="v1", grade="gold",
                          source_id=sid, quality_status="VALIDATED")
    r = ei.resolve_value("ext_fx", "baseline_plan")
    assert r["value"] == 1385.0 and r["grade"] == "gold"


def test_rejected_observation_is_not_used(ei):
    sid = _gold_source(ei)
    ei.record_observation("ext_fx", "2026-07-01", 9999.0, vintage="v1", grade="gold",
                          source_id=sid, quality_status="REJECTED")
    assert ei.resolve_value("ext_fx", "baseline_plan")["allowed"] is False


def test_unknown_purpose_is_rejected(ei):
    with pytest.raises(ExternalIntelligenceError):
        ei.resolve_value("ext_fx", "whatever")


def test_resolved_value_carries_display_rule(ei):
    """§12.2: 화면·API 는 실제값·전망·계획 가정·시나리오를 구분 표시해야 한다."""
    sid = _gold_source(ei)
    ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="v1", grade="gold",
                          source_id=sid, quality_status="VALIDATED")
    assert "구분해 표기" in ei.resolve_value("ext_fx", "baseline_plan")["note"]


# ── 플레이북 시드 ─────────────────────────────────────────────────────────
def test_seed_from_playbooks_does_not_invent_indicators(ei):
    """★★ 플레이북이 이미 무엇이 필요한지 적어 두었다. 여기서 새로 지어내면 두 곳이 어긋난다."""
    out = ei.seed_from_playbooks()
    assert out["seeded"] >= 6
    codes = {i["code"] for i in ei.list_indicators()}
    assert {"ext_fx", "ext_rate", "ext_wage", "ext_demand_index"} <= codes
    fx = ei.get_indicator("ext_fx")
    assert fx["required_grade"] == "gold" and fx["origin"] == "playbook"
    assert fx["acceptable_latency"] and fx["next_action"]


def test_seed_is_idempotent(ei):
    ei.seed_from_playbooks()
    n = len(ei.list_indicators())
    ei.seed_from_playbooks()
    assert len(ei.list_indicators()) == n


# ── 결손 리포트 — 지금 단계의 실질 산출물 ────────────────────────────────
def test_readiness_report_says_what_is_missing(ei):
    """★★ 수집기를 만들지 않은 지금, "무엇이 없는지 정확히 아는 것"이 산출물이다."""
    ei.seed_from_playbooks()
    r = ei.readiness_report()
    assert r["blocked"] == r["total"] and r["usable_for_baseline"] == 0
    assert r["approved_sources"] == 0
    for i in r["indicators"]:
        assert i["reason"] and i["next_action"], "무엇을 해야 하는지 없으면 방치된다"
    assert "수집기·스케줄러는 만들지 않았습니다" in r["note"]


def test_readiness_improves_when_gold_arrives(ei):
    ei.seed_from_playbooks()
    sid = _gold_source(ei)
    ei.record_observation("ext_fx", "2026-07-01", 1385.0, vintage="v1", grade="gold",
                          source_id=sid, quality_status="VALIDATED")
    r = ei.readiness_report()
    assert r["usable_for_baseline"] == 1 and r["approved_sources"] == 1
    assert r["indicators"][-1]["usable_for_baseline"] is True, "가용한 것이 뒤에 정렬된다"


def test_unregistered_indicator_is_reported_not_crashed(ei):
    r = ei.resolve_value("no_such_indicator", "baseline_plan")
    assert r["allowed"] is False and "등록되지 않은" in r["reason"]
