# ==========================================
# [§7.3 / §7.4] Shadow Mode — 후보를 병렬 적용하되 운영에는 쓰지 않는다
#
# 이 모듈의 값어치는 "실행"이 아니라 **막는 것**에 있다. 그래서 테스트의 대부분이
# "이런 승격은 거절되는가"를 본다.
#
#   ① 같은 입력이 아니면 비교하지 않는다 (다른 입력의 차이를 후보의 효과로 읽으면 잘못 승격한다)
#   ② 측정 못 한 지표는 0 이 아니라 unmeasured (0 이면 "후보 오류 0건"으로 읽힌다)
#   ③ 검토 없이 승격 불가 · 검토자 필수
#   ④ 악화 항목을 인정하지 않으면 승인 불가 (모르고 승격 vs 알고 승격은 다르다)
#   ⑤ 범위 없는 승격 불가 (§7.3 "승인된 범위에서만 제한적 운영 적용")
#   ⑥ 승격 전 결과는 운영값이 아니라는 것이 응답에 남는다
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shadow_mode import ShadowMode, ShadowModeError, snapshot_hash

SCOPE = "node_batt"


@pytest.fixture
def sm(tmp_path):
    return ShadowMode(db_path=str(tmp_path / "shadow.db"))


def _run(sm, **kw):
    kw.setdefault("name", "규칙 v2 검증")
    kw.setdefault("candidate_kind", "rule")
    kw.setdefault("enterprise_scope_id", SCOPE)
    kw.setdefault("evaluation_period", "2026-07")
    return sm.create_run(**kw)


def _both(sm, rid, base, cand, h="H1"):
    sm.record_side(rid, "baseline", base, input_hash=h)
    sm.record_side(rid, "candidate", cand, input_hash=h)


# ── 1단계: 기준선 설정 ────────────────────────────────────────────────────
def test_scope_is_mandatory(sm):
    """★★ D-014 개정 — M2 이후 신규 운영 데이터는 범위 지정 없이 등록할 수 없다."""
    with pytest.raises(ShadowModeError) as e:
        sm.create_run(name="x", candidate_kind="rule", enterprise_scope_id="",
                      evaluation_period="2026-07")
    assert "enterprise_scope_id" in str(e.value)


def test_evaluation_period_is_mandatory(sm):
    """평가 기간이 없으면 '언제의 데이터로 비교했나'에 답할 수 없다(§7.3 기준선 설정)."""
    with pytest.raises(ShadowModeError):
        sm.create_run(name="x", candidate_kind="rule", enterprise_scope_id=SCOPE,
                      evaluation_period="")


def test_new_run_is_not_promoted(sm):
    """★ 만들자마자 운영에 쓰일 수 있으면 Shadow Mode 가 아니다."""
    r = _run(sm)
    assert r["promoted"] is False and r["promotion_scope"] == ""
    assert r["review_status"] == "pending_review" and r["status"] == "pending"
    assert "운영값이 아닙니다" in r["note"]


def test_unknown_candidate_kind_is_rejected(sm):
    with pytest.raises(ShadowModeError):
        sm.create_run(name="x", candidate_kind="magic", enterprise_scope_id=SCOPE,
                      evaluation_period="2026-07")


# ── 2단계: 실행 결과 기록 ─────────────────────────────────────────────────
def test_input_proof_is_mandatory(sm):
    """★★ 같은 입력이었음을 증명할 수 없으면 비교가 후보의 효과인지 알 수 없다."""
    r = _run(sm)
    with pytest.raises(ShadowModeError) as e:
        sm.record_side(r["run_id"], "baseline", {"error_count": 3})
    assert "input_snapshot 또는 input_hash" in str(e.value)


def test_snapshot_hash_is_order_independent(sm):
    """키 순서가 달라도 같은 입력이면 같은 지문이어야 한다 — 아니면 오탐으로 비교가 막힌다."""
    assert snapshot_hash({"a": 1, "b": [1, 2]}) == snapshot_hash({"b": [1, 2], "a": 1})
    assert snapshot_hash({"a": 1}) != snapshot_hash({"a": 2})


def test_unknown_metric_is_rejected(sm):
    """★ 개선 방향을 모르는 지표는 받지 않는다 — 무엇이 개선인지 판정할 수 없다."""
    r = _run(sm)
    with pytest.raises(ShadowModeError) as e:
        sm.record_side(r["run_id"], "baseline", {"vibes": 10}, input_hash="H1")
    assert "개선 방향을 모르는 지표" in str(e.value)


def test_results_cannot_change_after_review(sm):
    """★★ 검토 근거가 사후에 바뀌면 그 검토는 무효다."""
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 5}, {"error_count": 2})
    sm.review(r["run_id"], "approved", "kim")
    with pytest.raises(ShadowModeError) as e:
        sm.record_side(r["run_id"], "candidate", {"error_count": 0}, input_hash="H1")
    assert "검토가 끝난" in str(e.value)


# ── 3단계: 비교 ───────────────────────────────────────────────────────────
def test_different_input_is_not_comparable(sm):
    """★★ 다른 입력으로 낸 차이는 후보의 효과가 아니라 입력의 차이다."""
    r = _run(sm)
    sm.record_side(r["run_id"], "baseline", {"error_count": 10}, input_hash="H1")
    sm.record_side(r["run_id"], "candidate", {"error_count": 1}, input_hash="H2")
    v = sm.compare(r["run_id"])
    assert v["comparable"] is False
    assert "입력이 다릅니다" in v["reason"]
    assert "잘못된 승격" in v["note"]


def test_one_side_missing_is_not_comparable(sm):
    r = _run(sm)
    sm.record_side(r["run_id"], "baseline", {"error_count": 10}, input_hash="H1")
    v = sm.compare(r["run_id"])
    assert v["comparable"] is False and "후보" in v["reason"]


def test_direction_decides_improvement(sm):
    """★ 클수록 좋은 지표와 작을수록 좋은 지표를 같은 방향으로 읽으면 판정이 뒤집힌다."""
    r = _run(sm)
    _both(sm, r["run_id"],
          {"kpi_value": 100, "error_count": 10, "cost_usd": 5.0},
          {"kpi_value": 120, "error_count": 3, "cost_usd": 7.0})
    v = sm.compare(r["run_id"])
    assert set(v["improved"]) == {"kpi_value", "error_count"}
    assert v["regressed"] == ["cost_usd"]
    assert v["verdict"] == "regressed", "악화가 하나라도 있으면 개선으로 뭉뚱그리지 않는다"


def test_unmeasured_metric_is_not_zero(sm):
    """★★ 0 으로 채우면 '후보가 오류 0건'으로 읽힌다."""
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 10, "cost_usd": 1.0},
          {"error_count": None, "cost_usd": 0.5})
    v = sm.compare(r["run_id"])
    assert v["unmeasured"] == ["error_count"]
    row = next(x for x in v["metrics"] if x["metric"] == "error_count")
    assert row["verdict"] == "unmeasured" and "0 이 아니라 미측정" in row["why"]
    assert "error_count" not in v["improved"] and "error_count" not in v["regressed"]


def test_no_difference_verdict(sm):
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 4}, {"error_count": 4})
    assert sm.compare(r["run_id"])["verdict"] == "no_difference"


def test_comparison_states_it_is_not_production(sm):
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 4}, {"error_count": 2})
    assert "운영값이 아닙니다" in sm.compare(r["run_id"])["note"]


# ── 4단계: 검토 ───────────────────────────────────────────────────────────
def test_review_requires_a_reviewer(sm):
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 4}, {"error_count": 2})
    with pytest.raises(ShadowModeError):
        sm.review(r["run_id"], "approved", "")


def test_cannot_approve_incomparable_run(sm):
    """비교가 성립하지 않은 것을 승인하면 근거 없는 승인이 된다."""
    r = _run(sm)
    sm.record_side(r["run_id"], "baseline", {"error_count": 10}, input_hash="H1")
    sm.record_side(r["run_id"], "candidate", {"error_count": 1}, input_hash="H2")
    with pytest.raises(ShadowModeError) as e:
        sm.review(r["run_id"], "approved", "kim")
    assert "비교가 성립하지 않은" in str(e.value)


def test_unacknowledged_regression_blocks_approval(sm):
    """★★ 모르고 승격하는 것과 알고 승격하는 것은 달라야 한다."""
    r = _run(sm)
    _both(sm, r["run_id"], {"kpi_value": 100, "cost_usd": 5.0},
          {"kpi_value": 120, "cost_usd": 9.0})
    with pytest.raises(ShadowModeError) as e:
        sm.review(r["run_id"], "approved", "kim")
    assert "cost_usd" in str(e.value)

    out = sm.review(r["run_id"], "approved", "kim", note="비용 증가는 감수",
                    acknowledged_regressions=["cost_usd"])
    assert out["review_status"] == "approved"
    assert out["acknowledged_regressions"] == ["cost_usd"]


def test_rejection_does_not_require_acknowledgement(sm):
    """반려는 악화를 인정할 필요가 없다 — 반려가 곧 인정하지 않는다는 뜻이다."""
    r = _run(sm)
    _both(sm, r["run_id"], {"kpi_value": 100}, {"kpi_value": 50})
    assert sm.review(r["run_id"], "rejected", "kim")["review_status"] == "rejected"


# ── 5단계: 승격 ───────────────────────────────────────────────────────────
def test_cannot_promote_without_review(sm):
    """★★ 검토 없는 승격은 §7.3 의 단계를 건너뛰는 것이다."""
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 4}, {"error_count": 2})
    with pytest.raises(ShadowModeError) as e:
        sm.promote(r["run_id"], "배터리소재 1공장 한정", "kim")
    assert "검토가 승인되지 않은" in str(e.value)


def test_cannot_promote_rejected_run(sm):
    r = _run(sm)
    _both(sm, r["run_id"], {"kpi_value": 100}, {"kpi_value": 50})
    sm.review(r["run_id"], "rejected", "kim")
    with pytest.raises(ShadowModeError):
        sm.promote(r["run_id"], "어디든", "kim")


def test_promotion_scope_is_mandatory(sm):
    """★★ 범위를 비우면 제한적 적용이 아니라 전면 적용이 된다."""
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 4}, {"error_count": 2})
    sm.review(r["run_id"], "approved", "kim")
    with pytest.raises(ShadowModeError) as e:
        sm.promote(r["run_id"], "", "kim")
    assert "promotion_scope" in str(e.value)


def test_successful_promotion_changes_the_note(sm):
    """승격 전후로 '운영값이 아니다'라는 문구가 바뀌어야 한다 — 화면이 이걸로 구분한다."""
    r = _run(sm)
    _both(sm, r["run_id"], {"error_count": 4}, {"error_count": 2})
    sm.review(r["run_id"], "approved", "kim")
    assert "운영값이 아닙니다" in sm.get(r["run_id"])["note"]

    out = sm.promote(r["run_id"], "제1공장 야간조 한정", "park")
    assert out["promoted"] is True and out["promotion_scope"] == "제1공장 야간조 한정"
    assert out["promoted_by"] == "park" and "승격된 범위에서만" in out["note"]


# ── 조직 격리 · 관측 ──────────────────────────────────────────────────────
def test_runs_are_scope_isolated(sm, monkeypatch):
    """★ 남의 사업부 실험이 보이면 안 된다."""
    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "visible_scopes", lambda n: {n})
    _run(sm, name="배터리 실험", enterprise_scope_id="node_batt")
    _run(sm, name="동제련 실험", enterprise_scope_id="node_copper")
    names = {r["name"] for r in sm.list_runs(scope_node_id="node_batt")}
    assert names == {"배터리 실험"}


def test_summary_surfaces_incomparable_runs(sm):
    """★ 비교 불가는 실패가 아니라 **판정 불가**다 — 조용히 묻히면 안 된다."""
    ok = _run(sm, name="정상")
    _both(sm, ok["run_id"], {"error_count": 4}, {"error_count": 2})
    sm.compare(ok["run_id"])

    bad = _run(sm, name="입력 불일치")
    sm.record_side(bad["run_id"], "baseline", {"error_count": 4}, input_hash="A")
    sm.record_side(bad["run_id"], "candidate", {"error_count": 1}, input_hash="B")
    sm.compare(bad["run_id"])

    s = sm.summary()
    assert s["total"] == 2 and s["promoted"] == 0
    assert [x["name"] for x in s["incomparable"]] == ["입력 불일치"]
    assert "판정 불가" in s["note"]
