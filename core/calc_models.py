"""★★★ [G2 5b / M0-1] **MVP 계산 모델 3종.** 순수·결정론·저장소를 모른다.

## 이 파일이 하는 일과 하지 않는 일

`core/calc_capability.py` 는 「무엇을 계산할 수 있다고 **선언**했는가」의 등록부이고,
이 파일은 그 산식이다. 등록부는 실행 관문(`assert_executable`)을 지키고, 이 파일은
숫자를 만든다.

**하지 않는 것**: 저장소 접근 · 승인 확인 · 권한 판정 · 스냅숏 조회. 전부 호출부의
일이다(`core/path_calculation.py`). 여기에 섞으면 계산을 시험하려면 DB 를 세워야 하고,
그러면 산식이 틀렸는지 배선이 틀렸는지 구분할 수 없다.

## 계약 근거

`docs/handoff/G2_A_PATH_CALCULATION_CONTRACT_2026-08-21.md` §7 (승인 반영):

- §7.1 `reserved_quantity` — 데모는 **0 으로 가정**하되 그 가정을 `assumptions` 로
  받아 지문에 싣는다. 값이 있으면 그 값을 쓴다.
- §7.2 `material_requirement` — **BOM 이 정본**이다.
      자재별 필요량 = plan_quantity × quantity_per_output ÷ standard_yield
  같은 자재의 BOM 행은 자재별로 **먼저 합산**한다. 저장된
  `MFG-01.material_requirement` 는 대사 대상 파생값이고, 재계산값과 다르면
  **하나를 고르지 않고 실패**한다(실측 66.4 vs 67.35).
- §7.3 `revenue_shift_days` = 시나리오 예상 인식일 − 기준선 예상 인식일.
  `actual_ship_date − due_date` 는 **이미 일어난 실적**(`delivery_delay_days`)이며
  시뮬레이션 결과가 아니다.

## 공통 규칙

★ **모르는 것을 0 으로 만들지 않는다.** 필수 열이 없거나 값이 비면 `CalcInputError` 다.
  0 은 「없다」가 아니라 「0 이다」이고, 화면은 그 둘을 구분하지 못한다.
★ 결정론: 같은 입력이면 같은 출력. 내부에서 `now()`·난수·dict 순회 순서에 의존하지
  않는다(정렬해서 처리한다).
★ 반올림은 **마지막에 한 번**, `ROUND_HALF_UP`, `Decimal` 로 한다. float 누적은 같은
  입력에 다른 답을 줄 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: 산식 판. **바뀌면 결과 지문이 바뀌고 옛 실행 증명이 무효가 된다.**
#: ⚠️ 산식을 고치면서 이 값을 그대로 두면, 재현 검증이 「같은 답」이라고 거짓말한다.
MODEL_VERSIONS: Dict[str, str] = {
    "CALC.LOGISTICS.ARRIVAL_DELAY.v1": "1.0.0",
    "CALC.INVENTORY.MATERIAL_SHORTAGE.v1": "1.0.0",
    "CALC.PRODUCTION.REVENUE_TIMING.v1": "1.0.0",
}

#: 수량 소수점. 계약 지표는 kg·일 단위이고, 세 자리면 실측 자료의 정밀도를 잃지 않는다.
_QTY = Decimal("0.001")


class CalcInputError(ValueError):
    """입력이 계약과 다르다. **계산하지 않는다.**

    ⚠️ 이것을 「0 으로 계산됨」으로 접으면 「계산이 안 됐다」가 「영향이 없다」로 보인다 —
      이 저장소가 계속 잡아 온 고장이다."""


class CalcSemanticError(ValueError):
    """자료가 계약의 의미 규칙과 어긋난다(예: BOM 재계산 불일치). **고르지 않는다.**"""


# ── 공통 도구 ────────────────────────────────────────────────────────────

def _num(row: Mapping[str, Any], key: str, *, where: str) -> Decimal:
    """수를 읽는다. 없거나 빈 값이면 예외 — **0 으로 접지 않는다.**"""
    if key not in row:
        raise CalcInputError(f"{where}: 필수 열이 없습니다: {key}")
    raw = row[key]
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise CalcInputError(
            f"{where}: {key} 가 비어 있습니다 — 빈 값을 0 으로 계산하지 않습니다.")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ArithmeticError) as e:
        raise CalcInputError(f"{where}: {key} 를 수로 읽을 수 없습니다({raw!r}): {e}")


def _text(row: Mapping[str, Any], key: str, *, where: str) -> str:
    if key not in row:
        raise CalcInputError(f"{where}: 필수 열이 없습니다: {key}")
    val = str(row[key] or "").strip()
    if not val:
        raise CalcInputError(f"{where}: {key} 가 비어 있습니다.")
    return val


def _utc(text: str, *, where: str) -> datetime:
    """시각을 UTC 로 읽는다. **시간대 없는 값은 거부한다.**

    ⚠️ 시간대 없는 시각을 받아 두면 나중에 비교하는 쪽이 추측하고, 그 추측은 서버
      시간대에 따라 달라진다 — 배포 환경이 바뀌면 계산 결과가 바뀐다."""
    raw = str(text or "").strip()
    if not raw:
        raise CalcInputError(f"{where}: 시각이 비어 있습니다.")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as e:
        raise CalcInputError(f"{where}: 시각을 읽을 수 없습니다({raw!r}): {e}")
    if dt.tzinfo is None:
        raise CalcInputError(
            f"{where}: 시간대가 없는 시각입니다({raw!r}) — UTC 오프셋이 필요합니다.")
    return dt.astimezone(timezone.utc)


def _round(value: Decimal) -> float:
    """**마지막에 한 번** 반올림한다(ROUND_HALF_UP)."""
    return float(value.quantize(_QTY, rounding=ROUND_HALF_UP))


def _days(later: datetime, earlier: datetime) -> int:
    """날짜 차이(일). ⚠️ 시각이 아니라 **날짜** 차이다 — 인식일은 날짜 단위 개념이다."""
    return (later.date() - earlier.date()).days


# ── ① CALC.LOGISTICS.ARRIVAL_DELAY.v1 ────────────────────────────────────

#: 실제 도착으로 인정하는 milestone 코드. ⚠️ `ETA`(예정)는 **들어가지 않는다.**
ARRIVED_MILESTONES = ("ATA",)
#: 실제 출발로 인정하는 milestone 코드.
DEPARTED_MILESTONES = ("ATD",)


def arrival_delay(*, shipments: Sequence[Mapping[str, Any]],
                  milestones: Sequence[Mapping[str, Any]],
                  inventory: Sequence[Mapping[str, Any]],
                  as_of: str,
                  assumptions: Optional[Mapping[str, Any]] = None
                  ) -> Dict[str, Any]:
    """선적 도착 지연이 재고 가용량에 미치는 영향.

    출력: `in_transit_quantity`(운송 중 수량) · `available_quantity`(가용 재고).

    ## ★★★ 운송 중 판정은 **실제 사건**으로 한다

        실제 출발(ATD) ≤ as_of  AND  실제 도착(ATA) 없음 또는 ATA > as_of

    ⚠️⚠️ 예정(`etd`/`eta`)으로 판정하면 **이미 도착한 배를 운송 중으로 센다.** 실측:
      `LOG-02.status` 는 120건 전부 `DELIVERED` 이고 실제 도착은 `LOG-03` 의 `ATA`
      사건에만 있다 — 상태 열을 믿으면 지연이 0 으로 보인다.

    ## 부호의 뜻

    `available_quantity` 는 **지금 쓸 수 있는 양**이다. 기존 계산 엔진의 「안 쓰고 남은
    재고」와 부호의 뜻이 반대다 — 이름만 이으면 「재고가 늘었으니 여유가 있다」로 읽히고
    실제로는 라인이 선다.

        가용 = 실물 − 예약(§7.1 가정)
    """
    at = _utc(as_of, where="arrival_delay.as_of")
    assume = dict(assumptions or {})

    #: 선적별 실제 사건. ⚠️ 여러 건이면 **가장 이른 것**을 쓴다 — 나중 사건을 쓰면
    #:   재전송·정정 기록이 도착을 늦춘 것처럼 보인다.
    departed: Dict[str, datetime] = {}
    arrived: Dict[str, datetime] = {}
    for i, ms in enumerate(milestones):
        where = f"arrival_delay.milestones[{i}]"
        sid = _text(ms, "shipment_id", where=where)
        code = _text(ms, "milestone_code", where=where).upper()
        when = _utc(_text(ms, "event_at", where=where), where=where)
        if code in DEPARTED_MILESTONES:
            if sid not in departed or when < departed[sid]:
                departed[sid] = when
        elif code in ARRIVED_MILESTONES:
            if sid not in arrived or when < arrived[sid]:
                arrived[sid] = when

    in_transit: Dict[str, Decimal] = {}
    delayed_shipments: List[Dict[str, Any]] = []
    for i, sh in enumerate(sorted(shipments, key=lambda r: str(r.get("shipment_id", "")))):
        where = f"arrival_delay.shipments[{i}]"
        sid = _text(sh, "shipment_id", where=where)
        material = _text(sh, "material_code", where=where)
        qty = _num(sh, "quantity", where=where)
        eta = _utc(_text(sh, "eta", where=where), where=where)
        left = departed.get(sid)
        got = arrived.get(sid)
        if left is None or left > at:
            continue                        # 아직 떠나지 않았다 — 운송 중이 아니다
        if got is not None and got <= at:
            continue                        # 이미 도착했다
        in_transit[material] = in_transit.get(material, Decimal(0)) + qty
        #: ★ 지연 = 예정 도착이 이미 지났는데 실제 도착 사건이 없다.
        if eta <= at:
            delayed_shipments.append(
                {"shipment_id": sid, "material_code": material,
                 "delay_days": _days(at, eta), "quantity": _round(qty)})

    #: 가용 재고 — as_of 시점의 **가장 최근** 스냅숏 한 줄만 자재·창고별로 쓴다.
    latest: Dict[Tuple[str, str], Tuple[datetime, Mapping[str, Any], int]] = {}
    for i, inv in enumerate(inventory):
        where = f"arrival_delay.inventory[{i}]"
        material = _text(inv, "material_code", where=where)
        wh = _text(inv, "warehouse_code", where=where)
        when = _utc(_text(inv, "as_of_date", where=where), where=where)
        if when > at:
            continue                        # 미래 스냅숏은 쓰지 않는다
        key = (material, wh)
        prev = latest.get(key)
        if prev is None or when > prev[0]:
            latest[key] = (when, inv, i)

    available: Dict[str, Decimal] = {}
    for (material, _wh), (_when, inv, i) in sorted(latest.items()):
        where = f"arrival_delay.inventory[{i}]"
        on_hand = _num(inv, "on_hand_quantity", where=where)
        reserved = _reserved(inv, assume, where=where)
        available[material] = available.get(material, Decimal(0)) + (on_hand - reserved)

    return {
        "capability_ref": "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
        "model_version": MODEL_VERSIONS["CALC.LOGISTICS.ARRIVAL_DELAY.v1"],
        "metrics": {
            "in_transit_quantity": {m: _round(v) for m, v in sorted(in_transit.items())},
            "available_quantity": {m: _round(v) for m, v in sorted(available.items())},
        },
        "delayed_shipments": sorted(delayed_shipments,
                                    key=lambda d: (d["shipment_id"],)),
        "assumptions_used": _assumptions_used(assume),
    }


def _reserved(inv: Mapping[str, Any], assume: Mapping[str, Any], *, where: str) -> Decimal:
    """예약 수량. **§7.1** — 값이 있으면 그 값, 없으면 **가정이 있을 때만** 0.

    ⚠️⚠️ 가정 없이 0 으로 채우면 「예약 0 으로 계산한 결과」와 「예약 데이터로 계산한
      결과」가 구분되지 않는다. 그래서 가정을 **명시적으로 받고** 지문에 싣는다.
    ⚠️ 운영 모델에서는 예약·할당 데이터 없이 0 으로 간주하면 안 된다."""
    if "reserved_quantity" in inv and inv["reserved_quantity"] not in (None, ""):
        return _num(inv, "reserved_quantity", where=where)
    if assume.get("reserved_quantity_zero") is True:
        return Decimal(0)
    raise CalcInputError(
        f"{where}: reserved_quantity 가 없습니다. 0 으로 보려면 "
        f"assumptions['reserved_quantity_zero']=True 를 명시해야 합니다 — 가정 없이 "
        f"0 으로 채우면 「예약 없음」과 「예약 데이터 없음」이 같은 숫자가 됩니다.")


def _assumptions_used(assume: Mapping[str, Any]) -> Dict[str, Any]:
    """★ 실제로 쓴 가정만 돌려준다 — 지문에 들어가는 값이다."""
    return {k: assume[k] for k in sorted(assume) if k in ("reserved_quantity_zero",)}


# ── ② CALC.INVENTORY.MATERIAL_SHORTAGE.v1 ────────────────────────────────

def material_shortage(*, inventory: Sequence[Mapping[str, Any]],
                      production_plan: Sequence[Mapping[str, Any]],
                      bom: Sequence[Mapping[str, Any]],
                      as_of: str,
                      assumptions: Optional[Mapping[str, Any]] = None,
                      arrival: Optional[Mapping[str, Any]] = None
                      ) -> Dict[str, Any]:
    """원료 부족이 생산 가능량에 미치는 영향.

    출력: `shortage_quantity`(자재별 부족량) · `producible_quantity`(계획행별 생산 가능량).

    ## ★★★ 낟알을 맞춘다 — BOM 이 정본(§7.2)

        계획행 → BOM 투입자재 → 자재별 필요량 = plan_quantity × qpo ÷ yield
               → 같은 자재 가용재고 → 자재별 부족량

    ⚠️⚠️ `INV-01` 은 자재×창고×일자이고 `MFG-01.material_requirement` 는 여러 BOM
      투입을 합친 **계획행 총량**이다. 단일 자재 재고와 바로 뺄 수 없다.
    ⚠️⚠️ 저장된 `material_requirement` 와 재계산값이 다르면 **하나를 고르지 않고
      실패한다**(실측 66.4 vs 67.35). 임의로 고르면 어느 쪽이 정본인지 아무도 모르게
      되고, 그 선택은 코드 한 줄에 숨는다.

    ## 인과 방향

    재고를 **원인**으로 받아 생산을 결과로 낸다. 기존 엔진은 재고를 생산의 결과로
    계산하므로 방향이 반대다 — 그 함수를 이 이름에 꽂으면 뜻이 뒤집힌다.
    """
    at = _utc(as_of, where="material_shortage.as_of")
    assume = dict(assumptions or {})

    #: BOM: (제품, 자재) → (자재별 합산 qpo, 수율). ⚠️ 같은 자재가 여러 줄일 수 있다.
    qpo: Dict[Tuple[str, str], Decimal] = {}
    yields: Dict[Tuple[str, str], Decimal] = {}
    for i, b in enumerate(bom):
        where = f"material_shortage.bom[{i}]"
        product = _text(b, "product_code", where=where)
        material = _text(b, "material_code", where=where)
        per = _num(b, "quantity_per_output", where=where)
        y = _num(b, "standard_yield", where=where)
        if y <= 0:
            raise CalcSemanticError(
                f"{where}: standard_yield 가 {y} 입니다 — 0 이하 수율로는 나눌 수 없습니다.")
        key = (product, material)
        qpo[key] = qpo.get(key, Decimal(0)) + per
        prev = yields.get(key)
        if prev is not None and prev != y:
            #: ⚠️ 같은 (제품,자재) 에 수율이 둘이면 어느 것이 맞는지 알 수 없다.
            raise CalcSemanticError(
                f"{where}: 같은 제품·자재에 수율이 둘입니다({prev} vs {y}) — "
                f"하나를 고르지 않습니다.")
        yields[key] = y

    #: 가용 재고. 앞 구간(도착 지연)이 계산한 값을 받으면 **그것을 쓴다** — 같은
    #: 경로에서 두 번 계산하면 두 답이 갈릴 자리가 생긴다.
    if arrival and isinstance(arrival.get("metrics"), Mapping):
        available = {m: Decimal(str(v)) for m, v in
                     (arrival["metrics"].get("available_quantity") or {}).items()}
    else:
        available = _available_from_inventory(inventory, at, assume)

    #: 계획행별 자재 필요량.
    need_by_material: Dict[str, Decimal] = {}
    producible: Dict[str, float] = {}
    reconciliation: List[Dict[str, Any]] = []
    for i, line in enumerate(sorted(production_plan,
                                    key=lambda r: str(r.get("plan_line_id", "")))):
        where = f"material_shortage.production_plan[{i}]"
        line_id = _text(line, "plan_line_id", where=where)
        product = _text(line, "product_code", where=where)
        plan_qty = _num(line, "plan_quantity", where=where)
        plan_at = _utc(_text(line, "plan_date", where=where), where=where)
        if plan_at < at:
            continue                        # 지난 계획은 이 시점의 영향이 아니다

        materials = sorted(k for k in qpo if k[0] == product)
        if not materials:
            raise CalcSemanticError(
                f"{where}: 제품 {product} 의 BOM 이 없습니다 — 필요량을 추측하지 않습니다.")

        line_need: Dict[str, Decimal] = {}
        for key in materials:
            need = plan_qty * qpo[key] / yields[key]
            line_need[key[1]] = line_need.get(key[1], Decimal(0)) + need
            need_by_material[key[1]] = need_by_material.get(key[1], Decimal(0)) + need

        #: ★★★ §7.2 대사 — 저장값이 있으면 재계산값과 **맞아야** 한다.
        if "material_requirement" in line and line["material_requirement"] not in (None, ""):
            stored = _num(line, "material_requirement", where=where)
            recomputed = sum(line_need.values(), Decimal(0))
            if _round(stored) != _round(recomputed):
                raise CalcSemanticError(
                    f"{where}: 저장된 material_requirement({_round(stored)}) 와 BOM "
                    f"재계산값({_round(recomputed)}) 이 다릅니다 — BOM 이 정본이지만 "
                    f"하나를 임의로 고르지 않습니다(§7.2). 자료를 고쳐야 합니다.")
            reconciliation.append({"plan_line_id": line_id, "stored": _round(stored),
                                   "recomputed": _round(recomputed), "matched": True})

        #: 생산 가능량 = 각 자재가 허용하는 최소 생산량.
        ratios = []
        for material, need in sorted(line_need.items()):
            if need <= 0:
                continue
            have = available.get(material)
            if have is None:
                raise CalcInputError(
                    f"{where}: 자재 {material} 의 재고를 알 수 없습니다 — 없는 것을 "
                    f"0 으로 보지 않습니다(0 이면 「부족하다」는 결론이 나온다).")
            ratios.append(max(Decimal(0), have) / need)
        #: ★★★ **계획량이 상한이다.** 재고가 남는다고 계획보다 더 만들 수는 없다.
        #: ⚠️ 상한 없이 비율을 곱하면 재고가 넉넉할 때 생산 가능량이 계획량을 넘고
        #:   (실측: 계획 100 에 385), 그 숫자가 「이만큼 더 만들 수 있다」로 읽힌다 —
        #:   설비·인력·수요를 하나도 보지 않은 값인데도.
        ratio = min(ratios) if ratios else Decimal(1)
        producible[line_id] = _round(plan_qty * min(Decimal(1), ratio))

    shortage = {}
    for material, need in sorted(need_by_material.items()):
        have = available.get(material, Decimal(0))
        gap = need - have
        if gap > 0:
            shortage[material] = _round(gap)

    return {
        "capability_ref": "CALC.INVENTORY.MATERIAL_SHORTAGE.v1",
        "model_version": MODEL_VERSIONS["CALC.INVENTORY.MATERIAL_SHORTAGE.v1"],
        "metrics": {
            "shortage_quantity": shortage,
            "producible_quantity": dict(sorted(producible.items())),
        },
        "required_quantity": {m: _round(v) for m, v in sorted(need_by_material.items())},
        "reconciliation": reconciliation,
        "assumptions_used": _assumptions_used(assume),
    }


def _available_from_inventory(inventory: Sequence[Mapping[str, Any]], at: datetime,
                              assume: Mapping[str, Any]) -> Dict[str, Decimal]:
    latest: Dict[Tuple[str, str], Tuple[datetime, Mapping[str, Any], int]] = {}
    for i, inv in enumerate(inventory):
        where = f"material_shortage.inventory[{i}]"
        material = _text(inv, "material_code", where=where)
        wh = _text(inv, "warehouse_code", where=where)
        when = _utc(_text(inv, "as_of_date", where=where), where=where)
        if when > at:
            continue
        key = (material, wh)
        prev = latest.get(key)
        if prev is None or when > prev[0]:
            latest[key] = (when, inv, i)
    out: Dict[str, Decimal] = {}
    for (material, _wh), (_when, inv, i) in sorted(latest.items()):
        where = f"material_shortage.inventory[{i}]"
        out[material] = out.get(material, Decimal(0)) + (
            _num(inv, "on_hand_quantity", where=where) - _reserved(inv, assume, where=where))
    return out


# ── ③ CALC.PRODUCTION.REVENUE_TIMING.v1 ──────────────────────────────────

def revenue_timing(*, sales_lines: Sequence[Mapping[str, Any]],
                   baseline_recognition: Mapping[str, str],
                   producible: Optional[Mapping[str, Any]] = None,
                   production_plan: Optional[Sequence[Mapping[str, Any]]] = None,
                   as_of: str) -> Dict[str, Any]:
    """생산 지연이 **매출 인식 시점**에 미치는 영향.

    출력: `revenue_shift_days`(판매행별 인식일 이동 일수).

    ## ★★★ 실적과 시뮬레이션을 가른다(§7.3)

        revenue_shift_days  = 시나리오 예상 인식일 − 기준선 예상 인식일   ← 이 함수
        delivery_delay_days = actual_ship_date − due_date                ← 별도 실적 KPI

    ⚠️⚠️ 앞엣것 자리에 뒤엣것을 쓰면 「시뮬레이션 결과」라며 **과거 실적을 보여 준다.**
      그 숫자는 시나리오를 바꿔도 변하지 않으므로, 사람은 시뮬레이션이 작동한다고 믿으면서
      아무 영향도 보지 못한다.

    ## 기준선이 없으면 계산하지 않는다

    이동 일수는 **두 시점의 차이**다. 기준선 인식일이 없으면 «이동» 이라는 개념 자체가
    없다 — 그때 `due_date` 를 기준선으로 대신 쓰면 그것은 실적 지연이 된다.
    """
    at = _utc(as_of, where="revenue_timing.as_of")
    #: 계획행 → 생산 완료 예상 이동. 생산 가능량이 계획보다 적으면 그만큼 늦어진다.
    line_rate: Dict[str, Decimal] = {}
    if producible and isinstance(producible.get("metrics"), Mapping):
        got = producible["metrics"].get("producible_quantity") or {}
        planned = {}
        for i, line in enumerate(production_plan or []):
            where = f"revenue_timing.production_plan[{i}]"
            planned[_text(line, "plan_line_id", where=where)] = _num(
                line, "plan_quantity", where=where)
        for line_id, qty in sorted(got.items()):
            plan_qty = planned.get(line_id)
            if plan_qty is None or plan_qty <= 0:
                continue
            line_rate[line_id] = Decimal(str(qty)) / plan_qty

    shifts: Dict[str, int] = {}
    unresolved: List[str] = []
    for i, sl in enumerate(sorted(sales_lines, key=lambda r: str(r.get("sales_line_id", "")))):
        where = f"revenue_timing.sales_lines[{i}]"
        line_id = _text(sl, "sales_line_id", where=where)
        base_raw = baseline_recognition.get(line_id)
        if not base_raw:
            #: ⚠️ 기준선이 없는 행은 **건너뛰지 않고 드러낸다.** 조용히 빼면 「이동 없음」과
            #:   「비교할 기준선이 없음」이 같은 결과가 된다.
            unresolved.append(line_id)
            continue
        #: ★ 기준선 인식일을 읽는 것 자체가 계약이다 — 형식이 틀리면 여기서 막힌다.
        _utc(base_raw, where=f"{where}.baseline")
        plan_line_id = str(sl.get("plan_line_id") or "").strip()
        rate = line_rate.get(plan_line_id)
        if rate is None:
            #: ⚠️⚠️ **0 을 주지 않는다.** 생산 계획과 연결되지 않은 판매행은 이동을
            #:   계산할 근거가 없다. 0 은 「이동 없음」으로 읽히고, 그것은 「영향 없음」이다 —
            #:   계산 못 한 것을 영향 없음으로 보이게 하는 것이 이 계약이 막는 첫 번째다.
            unresolved.append(line_id)
            continue
        #: 생산 가능 비율이 1 미만이면 그 비율만큼 인식이 늦어진다.
        #: ⚠️ 남은 물량을 다음 기간으로 미루는 규칙은 **경로 판(path_model_version)** 의
        #:   일이다 — 여기서는 인식 기간 길이에 비례한 이동만 계산한다.
        span = _num(sl, "recognition_span_days", where=where)
        delay = (Decimal(1) - min(Decimal(1), rate)) * span
        shifts[line_id] = int(delay.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return {
        "capability_ref": "CALC.PRODUCTION.REVENUE_TIMING.v1",
        "model_version": MODEL_VERSIONS["CALC.PRODUCTION.REVENUE_TIMING.v1"],
        "metrics": {"revenue_shift_days": dict(sorted(shifts.items()))},
        #: ★ 기준선이 없어 계산하지 못한 행. 비어 있지 않으면 호출부가 판단해야 한다.
        "missing_baseline": sorted(unresolved),
    }


def delivery_delay_days(*, sales_lines: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """**실적 KPI** — `actual_ship_date − due_date`. 시뮬레이션 결과가 아니다.

    ★ 별도 함수로 둔 이유: 같은 파일에 있어도 **이름과 반환 형태가 달라야** 실수로
      `revenue_shift_days` 자리에 꽂히지 않는다(§7.3 이 경고한 바로 그 혼동이다).
    ⚠️ 출하되지 않은 행은 **빼지 않고 넣지 않는다** — 아직 일어나지 않은 일에 0 을 주면
      「정시 출하」로 읽힌다."""
    out: Dict[str, int] = {}
    for i, sl in enumerate(sales_lines):
        where = f"delivery_delay_days.sales_lines[{i}]"
        line_id = _text(sl, "sales_line_id", where=where)
        shipped = str(sl.get("actual_ship_date") or "").strip()
        if not shipped:
            continue
        out[line_id] = _days(_utc(shipped, where=where),
                             _utc(_text(sl, "due_date", where=where), where=where))
    return dict(sorted(out.items()))
