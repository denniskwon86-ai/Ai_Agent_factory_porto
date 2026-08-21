"""★★★ [G2 5b / M0-1] **MVP 계산 모델 3종** 회귀.

계약: `docs/handoff/G2_A_PATH_CALCULATION_CONTRACT_2026-08-21.md` §7.

## 이 파일이 지키는 것

1. **결정론** — 같은 입력 3회, 같은 출력. 반올림·정렬·집계까지 같다.
2. **모르는 것을 0 으로 만들지 않는다** — 이 저장소가 계속 잡아 온 고장이다.
   「계산이 안 됐다」가 「영향이 없다」로 보이면 화면은 평온하고 사람은 그것을 사실로 읽는다.
3. **의미 규칙** — 예정이 아니라 실제 사건(ATA), BOM 이 정본, 실적 ≠ 시뮬레이션.
4. **부호의 뜻** — `available_quantity` 는 「지금 쓸 수 있는 양」이다.

⚠️ 승인·권한·저장소는 여기서 시험하지 않는다. 계산 모델은 그것을 모른다 —
  섞으면 산식이 틀렸는지 배선이 틀렸는지 구분할 수 없다.
"""
import pytest

from core import calc_models as cm

AS_OF = "2026-08-21T00:00:00+00:00"


# ── 자료 ─────────────────────────────────────────────────────────────────

def _shipments():
    return [
        {"shipment_id": "SHP-1", "material_code": "LIOH", "quantity": "1000",
         "eta": "2026-08-15T00:00:00+00:00"},          # 예정 지났고 미도착 → 지연
        {"shipment_id": "SHP-2", "material_code": "LIOH", "quantity": "500",
         "eta": "2026-08-30T00:00:00+00:00"},          # 운송 중이나 아직 예정 전
        {"shipment_id": "SHP-3", "material_code": "NIOH", "quantity": "700",
         "eta": "2026-08-10T00:00:00+00:00"},          # 이미 도착
        {"shipment_id": "SHP-4", "material_code": "NIOH", "quantity": "900",
         "eta": "2026-09-01T00:00:00+00:00"},          # 아직 출발 안 함
    ]


def _milestones():
    return [
        {"shipment_id": "SHP-1", "milestone_code": "ATD",
         "event_at": "2026-08-01T00:00:00+00:00"},
        {"shipment_id": "SHP-2", "milestone_code": "ATD",
         "event_at": "2026-08-05T00:00:00+00:00"},
        {"shipment_id": "SHP-3", "milestone_code": "ATD",
         "event_at": "2026-07-20T00:00:00+00:00"},
        {"shipment_id": "SHP-3", "milestone_code": "ATA",
         "event_at": "2026-08-12T00:00:00+00:00"},
    ]


def _inventory(**kw):
    base = [
        {"material_code": "LIOH", "warehouse_code": "WH1",
         "as_of_date": "2026-08-20T00:00:00+00:00", "on_hand_quantity": "300",
         "reserved_quantity": "50"},
        {"material_code": "LIOH", "warehouse_code": "WH1",
         "as_of_date": "2026-08-10T00:00:00+00:00", "on_hand_quantity": "999",
         "reserved_quantity": "0"},                    # 옛 판 — 쓰이면 안 된다
        {"material_code": "NIOH", "warehouse_code": "WH1",
         "as_of_date": "2026-08-20T00:00:00+00:00", "on_hand_quantity": "400",
         "reserved_quantity": "0"},
    ]
    for row in base:
        row.update(kw)
    return base


def _plan():
    return [{"plan_line_id": "PL-1", "product_code": "FG-CATHODE",
             "plan_quantity": "100", "plan_date": "2026-09-01T00:00:00+00:00"}]


def _bom():
    #: ★ FG-CATHODE 는 **같은 자재로 두 줄**이다(§7.2 — 자재별로 먼저 합산해야 한다).
    return [
        {"product_code": "FG-CATHODE", "material_code": "LIOH",
         "quantity_per_output": "0.4", "standard_yield": "0.925"},
        {"product_code": "FG-CATHODE", "material_code": "LIOH",
         "quantity_per_output": "0.2", "standard_yield": "0.925"},
        {"product_code": "FG-CATHODE", "material_code": "NIOH",
         "quantity_per_output": "0.5", "standard_yield": "0.925"},
    ]


# ── ① 도착 지연 ──────────────────────────────────────────────────────────

def test_운송_중_판정은_예정이_아니라_실제_사건으로_한다():
    """★★★ 실측: `LOG-02.status` 는 120건 전부 `DELIVERED` 이고 실제 도착은 `LOG-03`
    의 `ATA` 사건에만 있다. 예정으로 판정하면 **이미 도착한 배를 운송 중으로 센다.**"""
    got = cm.arrival_delay(shipments=_shipments(), milestones=_milestones(),
                           inventory=_inventory(), as_of=AS_OF)
    it = got["metrics"]["in_transit_quantity"]
    #: SHP-1(1000) + SHP-2(500) 만 운송 중. SHP-3 은 도착, SHP-4 는 미출발.
    assert it == {"LIOH": 1500.0}, it
    assert "NIOH" not in it, "도착한 배와 미출발 배가 운송 중으로 세어졌다"


def test_지연은_예정_도착이_지났고_실제_도착이_없을_때다():
    got = cm.arrival_delay(shipments=_shipments(), milestones=_milestones(),
                           inventory=_inventory(), as_of=AS_OF)
    delayed = {d["shipment_id"]: d["delay_days"] for d in got["delayed_shipments"]}
    assert delayed == {"SHP-1": 6}, delayed


def test_가용_재고는_가장_최근_판에서_예약을_뺀_값이다():
    """★ 부호의 뜻: 「지금 쓸 수 있는 양」이다. 기존 엔진의 「안 쓰고 남은 재고」와 반대다."""
    got = cm.arrival_delay(shipments=_shipments(), milestones=_milestones(),
                           inventory=_inventory(), as_of=AS_OF)
    #: LIOH: 최신판 300 − 예약 50 = 250 (옛 판 999 는 쓰이지 않는다)
    assert got["metrics"]["available_quantity"] == {"LIOH": 250.0, "NIOH": 400.0}


def test_예약_수량이_없으면_가정_없이는_계산하지_않는다():
    """★★★ §7.1 — 가정 없이 0 으로 채우면 「예약 없음」과 「예약 데이터 없음」이 **같은
    숫자**가 된다. 그 둘은 다른 사실이다."""
    rows = [{"material_code": "LIOH", "warehouse_code": "WH1",
             "as_of_date": "2026-08-20T00:00:00+00:00", "on_hand_quantity": "300"}]
    with pytest.raises(cm.CalcInputError, match="reserved_quantity"):
        cm.arrival_delay(shipments=[], milestones=[], inventory=rows, as_of=AS_OF)

    #: 가정을 명시하면 계산한다 — 그리고 그 가정이 **결과에 실린다**(지문에 들어간다).
    got = cm.arrival_delay(shipments=[], milestones=[], inventory=rows, as_of=AS_OF,
                           assumptions={"reserved_quantity_zero": True})
    assert got["metrics"]["available_quantity"] == {"LIOH": 300.0}
    assert got["assumptions_used"] == {"reserved_quantity_zero": True}


def test_시간대_없는_시각은_거부한다():
    """⚠️ 시간대 없는 시각은 서버 시간대에 따라 뜻이 달라진다 — 배포 환경이 바뀌면
    계산 결과가 바뀐다."""
    with pytest.raises(cm.CalcInputError, match="시간대"):
        cm.arrival_delay(shipments=[], milestones=[], inventory=[],
                         as_of="2026-08-21T00:00:00")


def test_밀스톤이_여러_건이면_가장_이른_것을_쓴다():
    """⚠️ 나중 사건을 쓰면 재전송·정정 기록이 도착을 늦춘 것처럼 보인다."""
    ms = _milestones() + [{"shipment_id": "SHP-3", "milestone_code": "ATA",
                           "event_at": "2026-08-25T00:00:00+00:00"}]
    got = cm.arrival_delay(shipments=_shipments(), milestones=ms,
                           inventory=_inventory(), as_of=AS_OF)
    assert "NIOH" not in got["metrics"]["in_transit_quantity"], \
        "늦은 정정 사건 때문에 도착한 배가 운송 중으로 돌아왔다"


# ── ② 원료 부족 ──────────────────────────────────────────────────────────

def test_BOM_이_정본이고_같은_자재는_먼저_합산한다():
    """★★★ §7.2 — FG-CATHODE 는 LIOH 로 두 줄이다.

        LIOH 필요량 = 100 × (0.4 + 0.2) ÷ 0.925 = 64.865
        NIOH 필요량 = 100 × 0.5 ÷ 0.925       = 54.054
    """
    got = cm.material_shortage(inventory=_inventory(), production_plan=_plan(),
                               bom=_bom(), as_of=AS_OF)
    need = got["required_quantity"]
    assert need == {"LIOH": 64.865, "NIOH": 54.054}, need


def test_부족량은_필요량에서_가용을_뺀_값이고_음수는_넣지_않는다():
    got = cm.material_shortage(inventory=_inventory(), production_plan=_plan(),
                               bom=_bom(), as_of=AS_OF)
    #: LIOH 필요 64.865 < 가용 250 → 부족 없음. NIOH 54.054 < 400 → 부족 없음.
    assert got["metrics"]["shortage_quantity"] == {}


def test_재고가_모자라면_부족량과_생산_가능량이_함께_줄어든다():
    inv = [{"material_code": "LIOH", "warehouse_code": "WH1",
            "as_of_date": "2026-08-20T00:00:00+00:00", "on_hand_quantity": "32.4325",
            "reserved_quantity": "0"},
           {"material_code": "NIOH", "warehouse_code": "WH1",
            "as_of_date": "2026-08-20T00:00:00+00:00", "on_hand_quantity": "400",
            "reserved_quantity": "0"}]
    got = cm.material_shortage(inventory=inv, production_plan=_plan(), bom=_bom(),
                               as_of=AS_OF)
    #: LIOH 가 절반뿐 → 부족 32.4325, 생산 가능량도 절반(50)
    #: 필요 64.86486… − 가용 32.4325 = 32.43236 → 32.432 (반올림은 **마지막에 한 번**)
    assert got["metrics"]["shortage_quantity"] == {"LIOH": 32.432}
    assert got["metrics"]["producible_quantity"] == {"PL-1": 50.0}


def test_저장된_소요량이_BOM_재계산과_다르면_고르지_않고_실패한다():
    """★★★ §7.2 — 실측 66.4 vs 67.35. **하나를 임의로 고르면** 어느 쪽이 정본인지
    아무도 모르게 되고, 그 선택은 코드 한 줄에 숨는다."""
    plan = _plan()
    plan[0]["material_requirement"] = "66.4"      # 재계산값은 118.919
    with pytest.raises(cm.CalcSemanticError, match="다릅니다"):
        cm.material_shortage(inventory=_inventory(), production_plan=plan,
                             bom=_bom(), as_of=AS_OF)


def test_저장된_소요량이_맞으면_대사_기록을_남긴다():
    """★ 대조군 — 대사가 「전부 막는 검사」면 저장값을 쓸 수 없다."""
    plan = _plan()
    plan[0]["material_requirement"] = "118.919"   # 64.865 + 54.054
    got = cm.material_shortage(inventory=_inventory(), production_plan=plan,
                               bom=_bom(), as_of=AS_OF)
    assert got["reconciliation"] == [{"plan_line_id": "PL-1", "stored": 118.919,
                                      "recomputed": 118.919, "matched": True}]


def test_BOM_이_없는_제품은_필요량을_추측하지_않는다():
    plan = [{"plan_line_id": "PL-9", "product_code": "FG-UNKNOWN",
             "plan_quantity": "10", "plan_date": "2026-09-01T00:00:00+00:00"}]
    with pytest.raises(cm.CalcSemanticError, match="BOM 이 없습니다"):
        cm.material_shortage(inventory=_inventory(), production_plan=plan,
                             bom=_bom(), as_of=AS_OF)


def test_재고를_모르는_자재는_0_으로_보지_않는다():
    """★★★ 없는 것을 0 으로 보면 **「부족하다」는 결론**이 나온다. 그것은 계산이 아니라
    추측이고, 그 추측은 회의에서 사실로 쓰인다."""
    inv = [{"material_code": "LIOH", "warehouse_code": "WH1",
            "as_of_date": "2026-08-20T00:00:00+00:00", "on_hand_quantity": "300",
            "reserved_quantity": "0"}]                 # NIOH 재고가 없다
    with pytest.raises(cm.CalcInputError, match="재고를 알 수 없습니다"):
        cm.material_shortage(inventory=inv, production_plan=_plan(), bom=_bom(),
                             as_of=AS_OF)


def test_같은_제품_자재에_수율이_둘이면_고르지_않는다():
    bom = _bom() + [{"product_code": "FG-CATHODE", "material_code": "LIOH",
                     "quantity_per_output": "0.1", "standard_yield": "0.8"}]
    with pytest.raises(cm.CalcSemanticError, match="수율이 둘"):
        cm.material_shortage(inventory=_inventory(), production_plan=_plan(),
                             bom=bom, as_of=AS_OF)


def test_앞_구간의_가용_재고를_받으면_그것을_쓴다():
    """★ 같은 경로에서 가용 재고를 두 번 계산하면 두 답이 갈릴 자리가 생긴다.

    ⚠️ 이 시험이 **실제 결함을 하나 잡았다**: 재고가 넉넉할 때 생산 가능량이 계획량을
      넘었다(계획 100 에 385). 계획량이 상한이다 — 설비·인력·수요를 보지 않은 값을
      「더 만들 수 있다」로 내보내면 안 된다."""
    arrival = cm.arrival_delay(shipments=_shipments(), milestones=_milestones(),
                               inventory=_inventory(), as_of=AS_OF)
    got = cm.material_shortage(inventory=[], production_plan=_plan(), bom=_bom(),
                               as_of=AS_OF, arrival=arrival)
    assert got["metrics"]["producible_quantity"] == {"PL-1": 100.0}


# ── ③ 매출 인식 시점 ─────────────────────────────────────────────────────

def _sales():
    return [{"sales_line_id": "SL-1", "plan_line_id": "PL-1",
             "recognition_span_days": "30", "due_date": "2026-09-10T00:00:00+00:00",
             "actual_ship_date": "2026-09-14T00:00:00+00:00"}]


def test_생산_가능량이_줄면_인식일이_그만큼_이동한다():
    """★★★ §7.3 — 이것이 **시뮬레이션 결과**다."""
    producible = {"metrics": {"producible_quantity": {"PL-1": 50.0}}}
    got = cm.revenue_timing(sales_lines=_sales(),
                            baseline_recognition={"SL-1": "2026-09-30T00:00:00+00:00"},
                            producible=producible, production_plan=_plan(), as_of=AS_OF)
    #: 절반만 생산 가능 → 30일 × 0.5 = 15일 이동
    assert got["metrics"]["revenue_shift_days"] == {"SL-1": 15}


def test_전량_생산_가능하면_이동이_없다():
    producible = {"metrics": {"producible_quantity": {"PL-1": 100.0}}}
    got = cm.revenue_timing(sales_lines=_sales(),
                            baseline_recognition={"SL-1": "2026-09-30T00:00:00+00:00"},
                            producible=producible, production_plan=_plan(), as_of=AS_OF)
    assert got["metrics"]["revenue_shift_days"] == {"SL-1": 0}


def test_기준선이_없으면_이동을_계산하지_않고_드러낸다():
    """★★★ 이동 일수는 **두 시점의 차이**다. 기준선이 없으면 «이동» 이라는 개념 자체가
    없다 — 그때 `due_date` 를 기준선으로 대신 쓰면 그것은 실적 지연이 된다."""
    producible = {"metrics": {"producible_quantity": {"PL-1": 50.0}}}
    got = cm.revenue_timing(sales_lines=_sales(), baseline_recognition={},
                            producible=producible, production_plan=_plan(), as_of=AS_OF)
    assert got["metrics"]["revenue_shift_days"] == {}
    assert got["missing_baseline"] == ["SL-1"], "계산 못 한 행이 조용히 빠졌다"


def test_생산_계획과_연결되지_않은_판매행은_0_이_아니라_미해결이다():
    """★★★ **0 은 「이동 없음」으로 읽히고, 그것은 「영향 없음」이다.**

    ⚠️ 이 회귀를 쓰기 전 첫 구현이 실제로 0 을 돌려줬다 — 내가 이 파일에서 금지한
      바로 그 결함을 같은 파일에 넣었다."""
    got = cm.revenue_timing(sales_lines=_sales(),
                            baseline_recognition={"SL-1": "2026-09-30T00:00:00+00:00"},
                            producible=None, production_plan=None, as_of=AS_OF)
    assert got["metrics"]["revenue_shift_days"] == {}
    assert got["missing_baseline"] == ["SL-1"]


def test_실적_납기지연은_별도_함수이고_시뮬레이션이_아니다():
    """★★★ §7.3 — `actual_ship_date − due_date` 는 **이미 일어난 일**이다.

    ⚠️ 이 값을 `revenue_shift_days` 자리에 쓰면 「시뮬레이션 결과」라며 과거 실적을
      보여 준다. 그 숫자는 시나리오를 바꿔도 변하지 않으므로, 사람은 시뮬레이션이
      작동한다고 믿으면서 아무 영향도 보지 못한다."""
    assert cm.delivery_delay_days(sales_lines=_sales()) == {"SL-1": 4}
    #: 두 지표는 **다른 값**이다 — 같으면 하나가 다른 것으로 쓰이고 있다는 뜻이다.
    producible = {"metrics": {"producible_quantity": {"PL-1": 50.0}}}
    sim = cm.revenue_timing(sales_lines=_sales(),
                            baseline_recognition={"SL-1": "2026-09-30T00:00:00+00:00"},
                            producible=producible, production_plan=_plan(),
                            as_of=AS_OF)["metrics"]["revenue_shift_days"]
    assert sim["SL-1"] != cm.delivery_delay_days(sales_lines=_sales())["SL-1"]


def test_출하되지_않은_행은_실적_지연이_0_이_아니다():
    """⚠️ 아직 일어나지 않은 일에 0 을 주면 「정시 출하」로 읽힌다."""
    sl = _sales()
    sl[0]["actual_ship_date"] = ""
    assert cm.delivery_delay_days(sales_lines=sl) == {}


# ── ④ 결정론 ─────────────────────────────────────────────────────────────

def test_같은_입력_세_번이면_같은_출력이다():
    """★★★ M0-1 완료 증거. 반올림·정렬·집계까지 같아야 한다.

    ⚠️ dict 순회 순서나 float 누적에 의존하면 같은 입력에 다른 답이 나온다 — 그러면
      재현 검증이 실패하고, 사람은 검증을 끄는 쪽을 택한다."""
    runs = []
    for _ in range(3):
        arrival = cm.arrival_delay(shipments=_shipments(), milestones=_milestones(),
                                   inventory=_inventory(), as_of=AS_OF)
        shortage = cm.material_shortage(inventory=_inventory(), production_plan=_plan(),
                                        bom=_bom(), as_of=AS_OF, arrival=arrival)
        timing = cm.revenue_timing(
            sales_lines=_sales(),
            baseline_recognition={"SL-1": "2026-09-30T00:00:00+00:00"},
            producible=shortage, production_plan=_plan(), as_of=AS_OF)
        runs.append((arrival, shortage, timing))
    assert runs[0] == runs[1] == runs[2]


def test_입력_순서가_바뀌어도_같은_출력이다():
    """★ 자료가 다른 순서로 들어와도 같은 답이어야 한다 — 순서가 답을 바꾸면 그것은
    산식이 아니라 우연이다."""
    a = cm.arrival_delay(shipments=_shipments(), milestones=_milestones(),
                         inventory=_inventory(), as_of=AS_OF)
    b = cm.arrival_delay(shipments=list(reversed(_shipments())),
                         milestones=list(reversed(_milestones())),
                         inventory=list(reversed(_inventory())), as_of=AS_OF)
    assert a == b


def test_산식_판이_세_모델_모두에_있다():
    """⚠️ 산식을 고치면서 판을 그대로 두면 재현 검증이 「같은 답」이라고 거짓말한다."""
    assert set(cm.MODEL_VERSIONS) == {
        "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
        "CALC.INVENTORY.MATERIAL_SHORTAGE.v1",
        "CALC.PRODUCTION.REVENUE_TIMING.v1"}
    for ref, ver in cm.MODEL_VERSIONS.items():
        assert ver, ref


def test_생산_가능량은_계획량을_넘지_않는다():
    """★★★ [구현 중 실측] 상한이 없으면 재고가 넉넉할 때 계획 100 에 385 가 나왔다.

    ⚠️ 그 숫자는 설비·인력·수요를 하나도 보지 않은 값인데 「이만큼 더 만들 수 있다」로
      읽힌다. 시뮬레이션이 없는 여유를 만들어 내면, 그 여유를 근거로 결정이 내려진다."""
    inv = [{"material_code": m, "warehouse_code": "WH1",
            "as_of_date": "2026-08-20T00:00:00+00:00", "on_hand_quantity": "999999",
            "reserved_quantity": "0"} for m in ("LIOH", "NIOH")]
    got = cm.material_shortage(inventory=inv, production_plan=_plan(), bom=_bom(),
                               as_of=AS_OF)
    assert got["metrics"]["producible_quantity"] == {"PL-1": 100.0}
    assert got["metrics"]["shortage_quantity"] == {}
