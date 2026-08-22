"""★★★ [G2 P0-CALC-INPUT] **정본 계약행 → 계산 DTO 투영.**

## 왜 투영 계층이 따로 있나

계산 모델(`core/calc_models.py`)은 「자재별 수량」·「실제 도착 사건」 같은 **계산의 말**로
입력을 받는다. 정본 데이터는 「업무의 말」로 적혀 있고 둘은 다르다:

    계산의 말            정본(계약키)
    material_code    ←   LOG-02 에는 **없다.** PRC-02 를 거쳐야 나온다
    quantity         ←   LOG-02.shipment_quantity
    milestone_code   ←   LOG-03.event_type
    event_at         ←   LOG-03.actual_at
    on_hand_quantity ←   INV-01.unrestricted_quantity
    product_code     ←   MFG-01.product_id
    material_code    ←   MDM-05.input_material_id

⚠️⚠️ 앞 판은 이 층 없이 계산 모델의 이름을 그대로 정본 이름인 것처럼 썼다. 실제 CSV 를
  넣자 `milestone_code` 누락으로 즉시 실패했다 — **정본 데이터로는 한 줄도 계산되지
  않는 상태**였는데 집중 회귀는 전부 초록이었다(fixture 가 계산 모델의 말로 쓰여 있었다).

## 결합은 **승인된 관계 근거**로만 한다

    purchase-order-line -ORDERS_MATERIAL->        material    PRC-02.material_id
    purchase-order-line -FULFILLED_BY_SHIPMENT->  shipment    LOG-02.po_line_id
    shipment            -HAS_MILESTONE->          milestone   LOG-03.shipment_id
    inventory-snapshot  -STOCKS_MATERIAL->        material    INV-01.material_id
    bom-line            -CONSUMES_MATERIAL->      material    MDM-05.input_material_id
    bom-line            -PRODUCES_MATERIAL->      material    MDM-05.output_material_id
    production-plan-line-FULFILLS_SALES->         sales-line  승인된 allocation

★ 근거 열이 없거나 결합이 끊기면 **추측하지 않고 실패**한다. 이름이 비슷한 다른 열로
  이어 붙이면 그 순간 「어느 자재의 선적인가」가 코드 한 줄의 추측이 된다.

⚠️ `production-plan-line -FULFILLS_SALES-> sales-line` 은 정본 근거가 «승인된
  allocation» 이다. 그 승인 자료가 없으면 **연결하지 않는다** — 제품·기간이 같다고
  이어 붙이면 그것은 승인이 아니라 추측이고, 매출 이연이 그 추측 위에 세워진다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.calc_models import CalcInputError

#: 투영이 요구하는 계약키. ⚠️ `PRC-02` 가 들어 있다 — `LOG-02` 에 자재 ID 가 없기 때문이다.
PROJECTION_DATASETS: Tuple[str, ...] = (
    "PRC-02", "LOG-02", "LOG-03", "INV-01", "MFG-01", "MDM-05", "SLS-01")

#: 정본 → 계산의 말. **이 표가 계약이다.** 열 이름을 코드 곳곳에 흩으면 정본이 바뀔 때
#: 어디를 고쳐야 하는지 알 수 없다.
FIELD_MAP: Dict[str, Dict[str, str]] = {
    "PRC-02": {"po_line_id": "po_line_id", "material_id": "material_code"},
    "LOG-02": {"shipment_id": "shipment_id", "po_line_id": "po_line_id",
               "shipment_quantity": "quantity", "eta": "eta"},
    "LOG-03": {"shipment_id": "shipment_id", "event_type": "milestone_code",
               "actual_at": "event_at"},
    "INV-01": {"material_id": "material_code", "location_id": "warehouse_code",
               "snapshot_at": "as_of_date", "unrestricted_quantity": "on_hand_quantity"},
    "MFG-01": {"plan_line_id": "plan_line_id", "product_id": "product_code",
               "plan_quantity": "plan_quantity", "plan_date": "plan_date"},
    "MDM-05": {"output_material_id": "product_code",
               "input_material_id": "material_code",
               "quantity_per_output": "quantity_per_output",
               "standard_yield": "standard_yield"},
    "SLS-01": {"sales_line_id": "sales_line_id", "product_id": "product_code",
               "due_date": "due_date"},
}

#: 있으면 옮기고 없어도 되는 열. ⚠️ **필수와 섞지 않는다** — 섞으면 필수 열이 빠져도
#: 조용히 계산되고, 그 결과는 가정 위에 선다.
OPTIONAL_MAP: Dict[str, Dict[str, str]] = {
    "LOG-02": {"etd": "etd"},
    "INV-01": {"reserved_quantity": "reserved_quantity",
               "safety_stock_quantity": "safety_stock_quantity"},
    "MFG-01": {"priority": "priority", "material_requirement": "material_requirement"},
    "SLS-01": {"actual_ship_date": "actual_ship_date"},
}


class ProjectionError(CalcInputError):
    """정본을 계산 DTO 로 옮길 수 없다. ⚠️ 추측해서 채우지 않는다."""


def _project_rows(key: str, rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """한 계약키의 행들을 계산의 말로 옮긴다. **필수 열이 없으면 실패.**"""
    required = FIELD_MAP[key]
    optional = OPTIONAL_MAP.get(key, {})
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        missing = [src for src in required if src not in row]
        if missing:
            raise ProjectionError(
                f"{key}[{i}]: 정본 열이 없습니다: {missing} — 계산에 필요한 값을 다른 "
                f"열로 추측해 채우지 않습니다. 사용 가능한 열: {sorted(row)[:12]}")
        item = {dst: row[src] for src, dst in required.items()}
        for src, dst in optional.items():
            if src in row:
                item[dst] = row[src]
        #: ★ 봉인 판 식별자는 그대로 들고 간다 — 실행기가 「봉인한 판을 읽었는가」를
        #:   확인하는 근거다.
        if "__snapshot_id__" in row:
            item["__snapshot_id__"] = row["__snapshot_id__"]
        out.append(item)
    return out


def project(datasets: Mapping[str, Sequence[Mapping[str, Any]]], *,
            sales_allocation: Optional[Mapping[str, str]] = None,
            recognition_span_days: Optional[Mapping[str, Any]] = None
            ) -> Dict[str, List[Dict[str, Any]]]:
    """정본 7종을 계산 DTO 로 투영한다.

    돌려주는 것: `{"shipments", "milestones", "inventory", "production_plan", "bom",
    "sales_lines"}` — 계산 모델이 그대로 받는 모양.

    ## 결합 두 곳

    ① **선적 → 자재**: `LOG-02` 에는 자재 ID 가 없다.
       `LOG-02.po_line_id → PRC-02.po_line_id → PRC-02.material_id` 로 잇는다.
       ⚠️ 끊기면 그 선적은 **어느 자재인지 모르는** 것이고, 계산에서 빼지 않고 **실패**한다
         — 빼면 운송 중 수량이 조용히 줄어들고 그것은 「지연이 없다」로 읽힌다.

    ② **생산계획 → 판매행**: 정본 근거가 «승인된 allocation» 이다. `sales_allocation`
       ({sales_line_id: plan_line_id})이 없으면 연결하지 않는다.
       ⚠️ 제품·기간이 같다고 이어 붙이면 그것은 승인이 아니라 추측이고, 매출 이연이
         그 추측 위에 세워진다. 연결이 없는 판매행은 계산기가 `missing_baseline` 으로
         드러낸다(0 으로 접지 않는다).

    ⚠️ `recognition_span_days` 도 정본에 없다 — **승인된 인식 기간 규칙**에서 온다.
      없는 판매행은 연결하지 않는다(추측한 기간으로 이연 일수를 만들지 않는다).
    """
    missing_keys = [k for k in PROJECTION_DATASETS if k not in datasets]
    if missing_keys:
        raise ProjectionError(
            f"투영에 필요한 계약키가 없습니다: {missing_keys} — `PRC-02` 는 선적의 자재를 "
            f"찾는 유일한 근거입니다(LOG-02 에는 자재 ID 가 없습니다).")

    proj = {k: _project_rows(k, datasets[k]) for k in PROJECTION_DATASETS}

    #: ① 선적 → 자재 (PRC-02 경유)
    po_material: Dict[str, str] = {}
    for i, row in enumerate(proj["PRC-02"]):
        po = str(row["po_line_id"] or "").strip()
        mat = str(row["material_code"] or "").strip()
        if not po or not mat:
            raise ProjectionError(
                f"PRC-02[{i}]: po_line_id·material_id 가 비어 있습니다 — 선적의 자재를 "
                f"찾을 근거가 없습니다.")
        prev = po_material.get(po)
        if prev is not None and prev != mat:
            #: ⚠️ 한 주문행에 자재가 둘이면 어느 것인지 고를 수 없다.
            raise ProjectionError(
                f"PRC-02[{i}]: 주문행 {po} 에 자재가 둘입니다({prev} vs {mat}) — "
                f"하나를 임의로 고르지 않습니다.")
        po_material[po] = mat

    shipments = []
    for i, row in enumerate(proj["LOG-02"]):
        po = str(row.get("po_line_id") or "").strip()
        mat = po_material.get(po)
        if not mat:
            raise ProjectionError(
                f"LOG-02[{i}]: 선적 {row.get('shipment_id')} 의 주문행({po or '(빈 값)'})"
                f"을 PRC-02 에서 찾을 수 없어 자재를 알 수 없습니다 — 계산에서 빼지 "
                f"않습니다(빼면 운송 중 수량이 조용히 줄고 「지연이 없다」로 읽힙니다).")
        shipments.append({**row, "material_code": mat})

    #: ② 생산계획 → 판매행 (승인된 allocation 경유)
    alloc = dict(sales_allocation or {})
    spans = dict(recognition_span_days or {})
    plan_ids = {str(r["plan_line_id"]) for r in proj["MFG-01"]}
    sales = []
    for i, row in enumerate(proj["SLS-01"]):
        sid = str(row["sales_line_id"])
        item = dict(row)
        plan_line = str(alloc.get(sid) or "").strip()
        if plan_line:
            if plan_line not in plan_ids:
                raise ProjectionError(
                    f"SLS-01[{i}]: 승인된 allocation 이 가리키는 계획행({plan_line})이 "
                    f"MFG-01 에 없습니다 — 없는 계획에 매출을 붙이지 않습니다.")
            item["plan_line_id"] = plan_line
        if sid in spans:
            item["recognition_span_days"] = spans[sid]
        sales.append(item)

    return {
        "shipments": shipments,
        "milestones": proj["LOG-03"],
        "inventory": proj["INV-01"],
        "production_plan": proj["MFG-01"],
        "bom": proj["MDM-05"],
        "sales_lines": sales,
    }
