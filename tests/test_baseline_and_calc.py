"""★★★ [Wave G] Baseline · 온톨로지 경로 · 최소 계산.

## 이 파일이 막으려는 네 가지

★★★ ① **재현할 수 없는 숫자.** 「최신 데이터 기준」이라고만 적힌 보고서는 한 달 뒤
  다시 돌리면 다른 답을 낸다. 그리고 어느 쪽이 맞는지 아무도 모른다.
★★★ ② **인증되지 않은 판이 기준선에 들어가는 것.** 그 위의 숫자는 아무도 보증하지
  않은 값이다.
★★★ ③ **없는 값을 0으로 채우는 것.** 「데이터가 없다」가 「값이 0이다」가 되면
  보고서가 완성돼 보인다.
★★★ ④ **성격 표시가 빠지는 것.** 시연 데이터로 만든 결과는 시연 결과다.
"""
import pytest

from core import baseline_build as bb
from core import calc_graph as cg
from core import ontology_path as op
from core.data_preparation import models as dpm

SCOPE = {"tenant_id": "t1", "scope_node_id": "n1", "entity_mode": "REAL"}


def _snap(sid="ds_1", *, state=dpm.DEMO_CERTIFIED, at="2026-08-17T00:00:00+00:00",
          kind=dpm.DATA_KIND_DEMO, **kw):
    base = {"snapshot_id": sid, "state": state, "certified_at": at,
            "data_kind": kind, **SCOPE}
    base.update(kw)
    return base


# ── ① 재현성 ────────────────────────────────────────────────────────────
def test_the_same_set_gives_the_same_fingerprint():
    """★★★ 순서·중복이 지문을 흔들면 「같은 기준선인가」에 답할 수 없다."""
    assert bb.fingerprint_for(["b", "a"]) == bb.fingerprint_for(["a", "b", "a"])
    assert bb.fingerprint_for(["a"]) != bb.fingerprint_for(["a", "b"])


def test_the_fingerprint_is_the_set_itself_not_how_many():
    """★★★ 개수만 담으면 **다른 판 두 개**가 같은 기준선으로 통과한다.

    ⚠️ 그러면 「같은 지문 = 같은 근거」라는 약속이 거짓이 되고, 두 회의가 서로 다른
      숫자를 같은 이름으로 부른다."""
    assert bb.fingerprint_for(["ds_a", "ds_b"]) != bb.fingerprint_for(["ds_c", "ds_d"])
    assert bb.fingerprint_for(["ds_a"]) != bb.fingerprint_for(["ds_z"])


def test_a_baseline_pins_ids_not_a_latest_pointer():
    b = bb.build([_snap("ds_2"), _snap("ds_1")], scope=SCOPE)
    assert b.snapshot_ids == ["ds_1", "ds_2"], "집합이 정렬돼 고정되지 않았다"
    assert b.fingerprint == bb.fingerprint_for(["ds_1", "ds_2"])
    assert bb.same_inputs(b, bb.build([_snap("ds_1"), _snap("ds_2")], scope=SCOPE))


def test_the_as_of_is_the_oldest_not_the_newest():
    """⚠️ 최신을 쓰면 기준선이 실제보다 신선해 보인다."""
    b = bb.build([_snap("a", at="2026-01-01T00:00:00+00:00"),
                  _snap("b", at="2026-08-17T00:00:00+00:00")], scope=SCOPE)
    assert b.as_of == "2026-01-01T00:00:00+00:00"


# ── ② 인증된 판만 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("state", [dpm.RAW, dpm.RECONCILED, dpm.QUARANTINED,
                                   dpm.REVOKED, "아무거나"])
def test_an_uncertified_snapshot_cannot_enter_a_baseline(state):
    """★★★ 승인 전 판이 기준선에 들어가면 그 위의 숫자는 아무도 보증하지 않는다."""
    with pytest.raises(bb.BaselineError) as e:
        bb.build([_snap(state=state)], scope=SCOPE)
    assert "인증되지 않은" in str(e.value)


def test_a_snapshot_without_an_as_of_is_refused():
    with pytest.raises(bb.BaselineError):
        bb.build([_snap(at="")], scope=SCOPE)


@pytest.mark.parametrize("field,value", [("tenant_id", "t2"),
                                         ("scope_node_id", "n2"),
                                         ("entity_mode", "VIRTUAL")])
def test_scopes_are_not_mixed_in_one_baseline(field, value):
    """★★★ 한 기준선에 다른 조직의 판이 섞이면 그 합계는 **아무 회사의 숫자도 아니다.**

    ⚠️ 세 필드를 하나씩 본다 — 한꺼번에만 보면 판정이 그중 하나만 봐도 통과한다."""
    with pytest.raises(bb.BaselineError):
        bb.build([_snap("a"), _snap("b", **{field: value})], scope=SCOPE)


def test_demo_and_real_are_not_mixed():
    with pytest.raises(bb.BaselineError):
        bb.build([_snap("a", kind=dpm.DATA_KIND_DEMO),
                  _snap("b", kind=dpm.DATA_KIND_REAL)], scope=SCOPE)


def test_an_empty_baseline_is_refused():
    """★★★ 빈 기준선 위의 보고서는 합계가 0이고, 아무도 고장으로 보지 않는다."""
    with pytest.raises(bb.BaselineError):
        bb.build([], scope=SCOPE)


# ── ④ 성격 표시 ─────────────────────────────────────────────────────────
def test_the_label_says_it_is_demo_data():
    b = bb.build([_snap()], scope=SCOPE)
    assert dpm.DATA_KIND_DEMO in b.public()["display_label"]
    assert "실적이 아닙니다" in b.public()["display_label"]


def test_an_unknown_kind_is_not_called_real():
    """⚠️ 모르는 성격을 «실제» 로 떨어뜨리지 않는다."""
    label = bb.display_label("아무거나")
    assert "알 수 없는" in label and "공식 보고에 쓰지" in label


# ── 온톨로지 경로 ───────────────────────────────────────────────────────
def test_the_chain_is_the_first_vertical_path_only():
    """★ 설계서가 「첫 경로만 구현/사용한다」고 못 박았다."""
    assert [n.key for n in op.CHAIN] == [
        "material", "purchase_order", "shipment", "arrival",
        "production_plan", "product", "cash_pl"]


def test_the_path_runs_one_way_only():
    """⚠️ 역방향을 허용하면 「입고가 구매주문에 영향을 준다」가 나온다."""
    assert [n.key for n in op.impact_path("purchase_order", "arrival")] == \
        ["purchase_order", "shipment", "arrival"]
    with pytest.raises(op.OntologyError):
        op.impact_path("arrival", "purchase_order")


def test_an_unknown_node_is_refused():
    with pytest.raises(op.OntologyError):
        op.node("없는칸")


def test_the_external_indicator_only_feeds_cash_pl():
    assert [n.key for n in op.downstream("external_indicator")] == ["cash_pl"]
    assert op.EXTERNAL in op.upstream("cash_pl")
    with pytest.raises(op.OntologyError):
        op.impact_path("external_indicator", "arrival")


def test_missing_evidence_is_surfaced_not_hidden():
    """★★★ 근거 없는 칸을 조용히 빼면 「전부 근거가 있다」로 보인다."""
    out = op.trace("purchase_order", "arrival",
                   snapshot_index={"purchase_orders": "ds_1"})
    assert out["complete"] is False
    assert out["missing_evidence"] == ["material_arrivals", "shipments"]
    #: 근거가 있는 칸은 식별자를 들고 있다 — **본문이 아니라 id 다**
    assert out["path"][0]["snapshot_id"] == "ds_1"
    assert "rows" not in repr(out) and "payload" not in repr(out)


def test_a_fully_evidenced_path_is_complete():
    """⚠️ 대조군 — 위 시험이 「늘 미완」으로도 통과하지 않게 한다."""
    out = op.trace("purchase_order", "arrival", snapshot_index={
        "purchase_orders": "d1", "shipments": "d2", "material_arrivals": "d3"})
    assert out["complete"] is True and out["missing_evidence"] == []


# ── 최소 계산 ───────────────────────────────────────────────────────────
BASE = {"production_qty": 100.0, "ending_inventory": 20.0,
        "purchase_payment": 1000.0, "ending_cash": 5000.0,
        "operating_profit": 300.0, "power_cost": 200.0, "period_days": 30.0}


class _B:
    fingerprint = "fp_base"
    data_kind = dpm.DATA_KIND_DEMO


def test_the_driver_and_output_lists_are_closed():
    assert cg.DRIVER_KEYS == ("fx_rate_pct", "lead_time_days", "power_price_pct")
    assert cg.OUTPUT_KEYS == ("production_qty", "ending_inventory",
                              "purchase_payment", "ending_cash", "operating_profit")


def test_the_same_inputs_give_the_same_result():
    """★★★ 같은 기준선 + 같은 가정 = 같은 결과 **그리고 같은 지문.**"""
    a = cg.simulate(_B(), BASE, {"fx_rate_pct": 10})
    b = cg.simulate(_B(), BASE, {"fx_rate_pct": 10})
    assert a.values == b.values and a.fingerprint == b.fingerprint


def test_a_different_assumption_changes_the_fingerprint():
    """⚠️ 지문이 같으면 「무엇으로 만든 숫자인가」에 답할 수 없다."""
    a = cg.simulate(_B(), BASE, {"fx_rate_pct": 10})
    b = cg.simulate(_B(), BASE, {"fx_rate_pct": 11})
    assert a.fingerprint != b.fingerprint


def test_a_different_baseline_changes_the_fingerprint():
    class _Other:
        fingerprint = "fp_other"
        data_kind = dpm.DATA_KIND_DEMO

    assert cg.simulate(_B(), BASE, {}).fingerprint != \
        cg.simulate(_Other(), BASE, {}).fingerprint


def test_calculating_without_a_baseline_is_refused():
    """★★★ 「최신 데이터로 대충」은 재현할 수 없는 숫자를 낳는다."""
    class _NoFp:
        fingerprint = ""
        data_kind = ""

    with pytest.raises(cg.CalcError) as e:
        cg.simulate(_NoFp(), BASE, {})
    assert "기준선 없이" in str(e.value)


@pytest.mark.parametrize("missing", list(BASE))
def test_a_missing_base_value_is_not_filled_with_zero(missing):
    """★★★ 「데이터가 없다」가 「값이 0이다」가 되면 보고서가 완성돼 보인다."""
    base = {k: v for k, v in BASE.items() if k != missing}
    with pytest.raises(cg.CalcError):
        cg.simulate(_B(), base, {})


def test_a_non_numeric_assumption_is_refused_not_read_as_zero():
    """★★★ 숫자가 아닌 가정을 0으로 읽으면 **「가정하지 않음」과 「0으로 가정」**이
      같아진다 — 화면은 그 둘을 구분해 보여 줄 수 없고, 결과는 그럴듯하다."""
    for bad in ("열흘", None, [], {"v": 1}):
        with pytest.raises(cg.CalcError) as e:
            cg.normalize_assumptions({"lead_time_days": bad})
        assert "숫자가 아닙니다" in str(e.value), f"{bad!r} 가 조용히 통과했다"


def test_a_zero_length_period_is_refused_not_divided_by():
    """★★★ 기간이 0이면 **하루당 값을 낼 수 없다.**

    ⚠️ 여기서 막지 않으면 0으로 나누거나(폭발) 0으로 채운다(조용한 거짓말). 둘 다
      회의에 올라가는 숫자다."""
    base = dict(BASE)
    for bad in (0.0, -1.0):
        base["period_days"] = bad
        with pytest.raises(cg.CalcError) as e:
            cg.simulate(_B(), base, {"lead_time_days": 1.0})
        assert "기간" in str(e.value), f"period_days={bad} 가 통과했다"


def test_an_unknown_driver_is_refused_not_ignored():
    """⚠️ 조용히 무시하면 사용자가 「값을 바꿨는데 결과가 그대로」를 보고 원인을 못 찾는다."""
    with pytest.raises(cg.CalcError) as e:
        cg.simulate(_B(), BASE, {"magic_driver": 1})
    assert "알 수 없는 Driver" in str(e.value)


def test_the_three_drivers_each_move_something():
    """★★★ Driver 를 하나씩 움직인다 — 셋을 동시에 주면 하나가 죽어 있어도 모른다."""
    base = cg.simulate(_B(), BASE, {})
    for key in cg.DRIVER_KEYS:
        moved = cg.simulate(_B(), BASE, {key: 10})
        assert moved.values != base.values, f"{key} 를 움직였는데 아무것도 안 바뀌었다"


def test_a_delay_longer_than_the_period_gives_zero_not_negative():
    """⚠️ 「지연이 기간보다 길다」는 «생산 0» 이지 «음의 생산» 이 아니다."""
    out = cg.simulate(_B(), BASE, {"lead_time_days": 999})
    assert out.values["production_qty"] == 0.0


def test_the_result_carries_its_data_kind():
    """★★★ 시연 데이터로 만든 결과는 **시연 결과**다."""
    out = cg.simulate(_B(), BASE, {}).public()
    assert out["data_kind"] == dpm.DATA_KIND_DEMO
    assert out["calc_version"] == cg.CALC_VERSION
    assert out["baseline_fingerprint"] == "fp_base"


def test_compare_gives_both_the_delta_and_the_ratio():
    """⚠️ 비율만 주면 작은 기준값에서 「+300%」가 나오고 실제 규모보다 크게 읽힌다."""
    rows = cg.compare(cg.simulate(_B(), BASE, {}),
                      cg.simulate(_B(), BASE, {"fx_rate_pct": 10}))
    by = {r["key"]: r for r in rows}
    assert by["purchase_payment"]["delta"] == 100.0
    assert by["purchase_payment"]["delta_pct"] == 10.0
    assert all(r["unit"] and r["label"] for r in rows), "단위·이름이 빠졌다"


def test_a_zero_base_gives_no_ratio_instead_of_infinity():
    """★★★ 기준이 0이면 비율은 **없다** — 무한대를 0으로 적지 않는다."""
    base = dict(BASE, operating_profit=0.0)
    rows = cg.compare(cg.simulate(_B(), base, {}),
                      cg.simulate(_B(), base, {"fx_rate_pct": 10}))
    profit = [r for r in rows if r["key"] == "operating_profit"][0]
    assert profit["delta_pct"] is None


# ── 의사결정 패키지 ─────────────────────────────────────────────────────
from core import decision_package as dpkg                            # noqa: E402


class _BL:
    fingerprint = "fp_base"
    data_kind = dpm.DATA_KIND_DEMO
    build_id = "bl_1"
    snapshot_ids = ["ds_1"]
    as_of = "2026-08-17T00:00:00+00:00"


def _pkg(**kw):
    base = cg.simulate(_B(), BASE, {})
    scen = cg.simulate(_B(), BASE, kw.pop("assumptions", {"fx_rate_pct": 10}))
    args = dict(title="환율 대응", owner="구매팀장", due="2026-08-30",
                base=base, scenario=scen, baseline=_BL())
    args.update(kw)
    return dpkg.build(**args)


@pytest.mark.parametrize("field", ["title", "owner", "due"])
def test_an_agenda_without_owner_or_due_is_refused(field):
    """★★★ 책임자·기한 없는 안건은 「검토하겠습니다」로 끝나고 아무 일도 안 난다."""
    with pytest.raises(dpkg.DecisionError):
        _pkg(**{field: "  "})


def test_two_results_from_different_baselines_are_not_compared():
    """★★★ 그 차이가 **가정 때문인지 데이터 때문인지** 구분할 수 없다."""
    class _Other:
        fingerprint = "fp_other"
        data_kind = dpm.DATA_KIND_DEMO

    with pytest.raises(dpkg.DecisionError) as e:
        dpkg.build(title="x", owner="o", due="d",
                   base=cg.simulate(_B(), BASE, {}),
                   scenario=cg.simulate(_Other(), BASE, {}), baseline=_BL())
    assert "기준선이 다른" in str(e.value)


def test_the_three_views_read_the_same_numbers():
    """★★★ 관점마다 **다른 숫자**를 만들지 않는다 — 회의에서 「어느 게 맞습니까」가
    나오면 자료 전체의 신뢰가 무너진다."""
    pkg = _pkg()
    assert [v["view"] for v in pkg.views] == list(dpkg.VIEWS)
    seen = []
    for v in pkg.views:
        rows = {r["key"]: (r["base"], r["scenario"]) for r in v["highlights"] + v["others"]}
        assert set(rows) == set(cg.OUTPUT_KEYS), "관점마다 항목 수가 다르다"
        seen.append(rows)
    assert seen[0] == seen[1] == seen[2], "관점마다 숫자가 다르다"


def test_each_view_leads_with_what_that_person_cares_about():
    """⚠️ 한 장으로 뭉치면 각자 자기에게 필요한 것을 못 찾는다."""
    pkg = _pkg()
    lead = {v["view"]: [r["key"] for r in v["highlights"]] for v in pkg.views}
    assert lead[dpkg.VIEW_DECIDER][0] == "operating_profit"
    assert lead[dpkg.VIEW_REQUESTER][0] == "production_qty"
    assert lead[dpkg.VIEW_DECIDER] != lead[dpkg.VIEW_REQUESTER]


def test_the_evidence_carries_the_lineage():
    """★★★ 어느 기준선 · 어느 산식 판 · 어떤 가정에서 나온 숫자인가.

    ⚠️ 없으면 다음 회의에서 같은 숫자를 다시 만들 수 없고, 결정을 되짚을 수도 없다."""
    e = _pkg().evidence
    assert e["baseline_fingerprint"] == "fp_base"
    assert e["snapshot_ids"] == ["ds_1"]
    assert e["calc_version"] == cg.CALC_VERSION
    assert e["assumptions"]["fx_rate_pct"] == 10.0
    assert e["result_fingerprint"]


def test_the_briefing_says_it_is_demo_data():
    lines = dpkg.briefing_lines(_pkg())
    assert dpm.DATA_KIND_DEMO in lines[0]


def test_the_briefing_does_not_hide_missing_evidence():
    """★★★ 근거가 빠진 단계를 숨기면 그 보고는 «전부 설명된 것» 으로 읽힌다."""
    path = op.trace("purchase_order", "arrival",
                    snapshot_index={"purchase_orders": "ds_1"})
    lines = dpkg.briefing_lines(_pkg(path=path))
    assert any("근거가 없는 단계" in ln for ln in lines)


def test_the_briefing_numbers_come_from_the_table_not_prose():
    """⚠️ 그럴듯한 요약을 만들면 그 요약이 원본과 갈라지고, 사람은 요약만 읽는다."""
    pkg = _pkg()
    rows = {r["key"]: r for v in pkg.views for r in v["highlights"]}
    text = "\n".join(dpkg.briefing_lines(pkg))
    assert f"{rows['purchase_payment']['delta']:+,.0f}" in text
