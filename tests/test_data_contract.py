# ==========================================
# [§6.3 / §6.1] 데이터 계약 — "직접 DB 결합의 대안"
#
# JSON 을 저장하는 것만으로는 계약이 아니다. 약속은 **지금 지켜지고 있는지 확인될 때**
# 비로소 결합의 대안이 된다. 그래서 이 테스트의 중심은 등록이 아니라 `evaluate()` 다.
#
# 가장 중요한 성질: **확인하지 못한 것을 '지켜짐'이라고 하지 않는다.**
#   품질 프로파일이 없으면 unverifiable 이지 kept 가 아니다. 통과로 처리하면
#   "계약 준수 중"이라는 거짓 안심이 생기고, 그건 계약이 없는 것보다 나쁘다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_catalog import DataCatalog
from core.data_contract import DataContractError, DataContracts
from core.master_data import MasterData


@pytest.fixture
def env(tmp_path):
    md = MasterData(db_path=str(tmp_path / "m.db"))
    dc, dk = DataCatalog(md), DataContracts(md)
    a = dc.create_asset("생산실적", owner_dept_id="p", refresh_cadence="daily",
                        sensitivity="internal")
    dc.upsert_field(a["asset_id"], "qty", logical_type="int")
    return dc, dk, a["asset_id"]


def _c(dk, dc, aid, **kw):
    kw.setdefault("name", "공급계약")
    kw.setdefault("consumer", "planning_app")
    return dk.create(producer_asset_id=aid, catalog=dc, **kw)


# ── 등록·개정 ─────────────────────────────────────────────────────────────
def test_consumer_is_required(env):
    """★ 누구와의 약속인지 없으면 계약이 아니다."""
    dc, dk, aid = env
    with pytest.raises(DataContractError):
        dk.create(name="x", producer_asset_id=aid, consumer="", catalog=dc)


def test_unknown_producer_is_rejected(env):
    dc, dk, _ = env
    with pytest.raises(DataContractError):
        dk.create(name="x", producer_asset_id="da_nope", consumer="app", catalog=dc)


def test_revision_creates_new_version_not_overwrite(env):
    """★★ 덮어쓰면 소비자가 **어떤 약속을 보고 붙었는지** 사라지고 파기적 변경을 증명할 수 없다."""
    dc, dk, aid = env
    v1 = _c(dk, dc, aid, schema={"fields": [{"name": "qty", "type": "int"}]})
    v2 = dk.revise(v1["contract_key"], schema={"fields": [{"name": "qty", "type": "text"}]},
                   catalog=dc)
    assert v2["version"] == 2 and v2["supersedes"] == f"{v1['contract_key']}@1"
    assert dk.get(v1["contract_id"])["schema"]["fields"][0]["type"] == "int", "v1 이 남아야 한다"


# ── 파기적 변경 판정 ──────────────────────────────────────────────────────
def test_breaking_changes_are_detected(env):
    """★★ 사람이 기억해서 챙기게 두면 반드시 놓친다."""
    _, dk, _ = env
    old = {"fields": [{"name": "a", "type": "int"}, {"name": "b", "type": "text"},
                      {"name": "c", "type": "int", "required": False}]}
    new = {"fields": [{"name": "a", "type": "text"},
                      {"name": "c", "type": "int", "required": True},
                      {"name": "d", "type": "int"}]}
    d = dk.diff_schema(old, new)
    kinds = {b["kind"] for b in d["breaking"]}
    assert kinds == {"type_changed", "field_removed", "became_required"}
    assert d["is_breaking"] is True
    assert {x["kind"] for x in d["compatible"]} == {"field_added"}


def test_additive_change_is_not_breaking(env):
    """필드 추가와 필수→선택은 소비자를 깨뜨리지 않는다 — 이걸 파기적이라 하면 개정을 못 한다."""
    _, dk, _ = env
    d = dk.diff_schema({"fields": [{"name": "a", "required": True}]},
                       {"fields": [{"name": "a", "required": False}, {"name": "b"}]})
    assert d["is_breaking"] is False


def test_preview_revision_uses_current_contract(env):
    dc, dk, aid = env
    v1 = _c(dk, dc, aid, schema={"fields": [{"name": "qty", "type": "int"}]})
    pv = dk.preview_revision(v1["contract_key"], {"fields": []})
    assert pv["is_breaking"] and pv["from_version"] == 1 and pv["consumer"] == "planning_app"


# ── 검증: 확인 못 한 것을 통과로 치지 않는가 ──────────────────────────────
def test_missing_field_is_a_breach(env):
    dc, dk, aid = env
    c = _c(dk, dc, aid, schema={"fields": [{"name": "qty"}, {"name": "plant"}]})
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    assert ev["state"] == "breached"
    assert any(f["kind"] == "field_missing" for f in ev["findings"])


def test_type_mismatch_is_a_breach(env):
    dc, dk, aid = env
    c = _c(dk, dc, aid, schema={"fields": [{"name": "qty", "type": "text"}]})
    assert dk.evaluate(c["contract_id"], catalog=dc)["state"] == "breached"


def test_quality_rule_without_profile_is_unverifiable_not_kept(env):
    """★★ 이 테스트가 이 모듈의 핵심이다. 통과로 처리하면 거짓 안심이 생긴다."""
    dc, dk, aid = env
    c = _c(dk, dc, aid, schema={"fields": [{"name": "qty", "type": "int"}]},
           quality_rules={"min_completeness": 0.95})
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    assert ev["state"] == "unverifiable", "품질을 못 봤는데 kept 면 안 된다"
    assert any(u["kind"] == "quality" for u in ev["unverifiable"])
    assert "통과가 아닙니다" in ev["note"]


def test_unmeasured_metric_is_unverifiable_not_zero(env):
    """미측정(NULL)을 0 으로 읽으면 '완전성 0%'라는 없는 위반이 생긴다."""
    dc, dk, aid = env
    dc.record_quality_profile(aid, method="declared", validity=0.99)   # completeness 미측정
    c = _c(dk, dc, aid, quality_rules={"min_completeness": 0.95})
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    assert not any(f["kind"] == "quality_completeness" for f in ev["findings"])
    assert any(u["kind"] == "quality.completeness" for u in ev["unverifiable"])


def test_quality_threshold_breach(env):
    dc, dk, aid = env
    dc.record_quality_profile(aid, method="measured", completeness=0.80, evidence_ref="r1")
    c = _c(dk, dc, aid, quality_rules={"min_completeness": 0.95})
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    assert ev["state"] == "breached"
    assert any(f["kind"] == "quality_completeness" for f in ev["findings"])


def test_required_method_mismatch_is_at_risk(env):
    """신고값으로 측정 요구를 충족했다고 하면 안 되지만, 값 자체가 어긋난 건 아니라 medium."""
    dc, dk, aid = env
    dc.record_quality_profile(aid, method="declared", completeness=0.99)
    c = _c(dk, dc, aid, quality_rules={"min_completeness": 0.95, "required_method": "measured"})
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    assert ev["state"] == "at_risk"
    assert any(f["kind"] == "quality_method" for f in ev["findings"])


def test_cadence_slower_than_sla_is_structural_breach(env):
    """★ 갱신주기가 SLA 보다 느리면 지금 최신이어도 **구조적으로 못 지킨다.**"""
    dc, dk, aid = env
    dc.update_asset(aid, refresh_cadence="weekly", last_refreshed_at="2026-07-29T00:00:00+00:00")
    c = _c(dk, dc, aid, quality_rules={"max_staleness": "daily"})
    ev = dk.evaluate(c["contract_id"], catalog=dc, now="2026-07-29T01:00:00+00:00")
    assert any(f["kind"] == "cadence_slower_than_sla" for f in ev["findings"])


def test_stale_asset_breaches_sla(env):
    dc, dk, aid = env
    dc.update_asset(aid, last_refreshed_at="2026-07-01T00:00:00+00:00")
    c = _c(dk, dc, aid, quality_rules={"max_staleness": "daily"})
    ev = dk.evaluate(c["contract_id"], catalog=dc, now="2026-07-29T00:00:00+00:00")
    assert ev["state"] == "breached" and any(f["kind"] == "stale" for f in ev["findings"])


def test_unknown_freshness_is_unverifiable(env):
    dc, dk, aid = env                                   # last_refreshed_at 없음
    c = _c(dk, dc, aid, quality_rules={"max_staleness": "daily"})
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    assert any(u["kind"] == "freshness" for u in ev["unverifiable"])


def test_access_policy_violations(env):
    dc, dk, aid = env
    dc.update_asset(aid, sensitivity="restricted")
    dc.upsert_field(aid, "worker", pii_classification="pii")
    c = _c(dk, dc, aid, access_policy={"max_sensitivity": "internal", "pii_allowed": False})
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    kinds = {f["kind"] for f in ev["findings"]}
    assert "sensitivity_exceeds_policy" in kinds and "pii_not_allowed" in kinds


def test_fully_satisfied_contract_is_kept(env):
    dc, dk, aid = env
    dc.record_quality_profile(aid, method="measured", completeness=0.99, evidence_ref="r1")
    dc.update_asset(aid, last_refreshed_at="2026-07-29T09:00:00+00:00")
    c = _c(dk, dc, aid, schema={"fields": [{"name": "qty", "type": "int"}]},
           quality_rules={"min_completeness": 0.95, "max_staleness": "daily",
                          "required_method": "measured"},
           access_policy={"max_sensitivity": "internal", "pii_allowed": False})
    ev = dk.evaluate(c["contract_id"], catalog=dc, now="2026-07-29T12:00:00+00:00")
    assert ev["state"] == "kept" and set(ev["checked"]) >= {"schema", "quality", "freshness"}


def test_missing_producer_asset_is_a_breach(env):
    dc, dk, aid = env
    c = _c(dk, dc, aid)
    dc.retire_asset(aid)
    ev = dk.evaluate(c["contract_id"], catalog=dc)
    assert ev["state"] == "breached"
    assert any(f["kind"] == "producer_missing" for f in ev["findings"])


# ── 활성화 ────────────────────────────────────────────────────────────────
def test_breached_contract_cannot_be_activated(env):
    """★★ 활성화는 "이 약속으로 붙어도 된다"는 선언이다. 이미 위반 중이면 선언이 거짓이 된다."""
    dc, dk, aid = env
    c = _c(dk, dc, aid, schema={"fields": [{"name": "nope"}]})
    with pytest.raises(DataContractError) as e:
        dk.activate(c["contract_id"], "kim", catalog=dc)
    assert "위반 중" in str(e.value)
    out = dk.activate(c["contract_id"], "kim", catalog=dc, allow_breached=True)
    assert out["status"] == "active" and out["evaluation_at_activation"] == "breached"


def test_activation_requires_an_approver(env):
    dc, dk, aid = env
    c = _c(dk, dc, aid)
    with pytest.raises(DataContractError):
        dk.activate(c["contract_id"], "", catalog=dc)


def test_activating_new_version_deprecates_previous(env):
    """★ 같은 키에 활성이 둘이면 어느 약속이 유효한지 알 수 없다."""
    dc, dk, aid = env
    v1 = _c(dk, dc, aid)
    dk.activate(v1["contract_id"], "kim", catalog=dc)
    v2 = dk.revise(v1["contract_key"], note="개정", catalog=dc)
    dk.activate(v2["contract_id"], "kim", catalog=dc)
    assert dk.get(v1["contract_id"])["status"] == "deprecated"
    assert dk.get_active(v1["contract_key"])["version"] == 2


def test_retired_contract_cannot_be_activated(env):
    dc, dk, aid = env
    c = _c(dk, dc, aid)
    dk.retire(c["contract_id"])
    with pytest.raises(DataContractError):
        dk.activate(c["contract_id"], "kim", catalog=dc)


def test_evaluate_all_summarises_active_only(env):
    dc, dk, aid = env
    active = _c(dk, dc, aid, schema={"fields": [{"name": "qty", "type": "int"}]})
    dk.activate(active["contract_id"], "kim", catalog=dc)
    _c(dk, dc, aid, contract_key="other", schema={"fields": [{"name": "nope"}]})  # draft
    out = dk.evaluate_all(catalog=dc)
    assert out["total"] == 1 and out["by_state"].get("kept") == 1
