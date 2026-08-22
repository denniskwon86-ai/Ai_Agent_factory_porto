"""★★★ [G2 M0-3] **첫 수직 경로 시연 데이터** — 정본 열 이름·결정론.

## 무엇을 만드나

12분 시연의 한 이야기를 흐르게 하는 최소 자료다:

    구매주문 → 선적 지연 → 재고 부족 → 생산 차질 → 매출 인식 이연

## 규칙

★ **정본 열 이름을 쓴다.** `core/calc_projection.FIELD_MAP` 의 왼쪽 열이 그대로 들어간다.
  ⚠️ 계산 모델의 말(`material_code`·`milestone_code`)로 쓰면 실제 파이프라인에서
    한 줄도 안 돈다 — 그 실수를 이미 한 번 했다.
★ **결정론.** 난수·현재 시각을 쓰지 않는다. 같은 함수 호출이면 같은 바이트가 나오고,
  그래야 인증판 체크섬이 재현된다.
★ **`DEMO/SYNTHETIC`.** 이 자료는 합성이다. 저장소가 `data_kind` 로 표시하고, 화면도
  그 표시를 지운 채 보여 주면 안 된다.

## 이야기가 실제로 성립하는가

숫자를 아무렇게나 넣으면 「지연은 있는데 부족은 없는」 자료가 되어 시연이 밋밋해진다.
그래서 다음이 성립하도록 맞췄다(회귀가 이 사실을 고정한다):

    · 선적 2건이 예정 도착을 지나고도 실제 도착 사건이 없다 → 운송 중·지연
    · 그만큼 재고가 모자라 생산계획 두 행 중 뒤 행이 계획량을 못 채운다
    · 그래서 그 계획행에 배분된 판매행의 인식일이 밀린다
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Sequence, Tuple

#: 시연 기준 시각. ⚠️ **고정값**이다 — `now()` 를 쓰면 매 실행마다 자료가 달라지고,
#: 그러면 「같은 입력 3회 같은 결과」를 증명할 수 없다.
AS_OF = "2026-08-21T00:00:00+00:00"

TENANT = "tenant_default"
ENTITY_MODE = "REAL"
#: 시연 조직 노드. ⚠️ 실존 조직에 임의 배정하지 않는다 — 배터리소재 사업부는 스타터
#: 키트가 정의한 **합성 회사**의 노드다.
DEFAULT_SCOPE = "MNM_BATTERY"

#: 원료 2종·제품 1종(계약 §4.4 의 최소 규모 안에서 이야기가 성립하는 최소 조합).
MAT_LI = "MAT-LIOH"
MAT_NI = "MAT-NISO4"
PRODUCT = "FG-NCM811"


#: ★★★ **범위 세 값은 행마다 들어간다.** 색인이 요구한다(D-014 — 범위 미지정은
#: 전사 공용이 아니라 **비노출**이다). 정본 CSV 도 이 열을 갖는다.
#: ⚠️ 이것을 시드에서 빼면 색인이 «범위 없음» 으로 거부하고, 그 거부는 「자료가 없다」가
#:   아니라 「통제 밖에 놓일 뻔했다」는 뜻이다.
SCOPE_COLUMNS = ("tenant_id", "scope_node_id", "entity_mode")


def _with_scope(rows: Sequence[Dict[str, Any]], scope_node_id: str
                ) -> List[Dict[str, Any]]:
    return [{**r, "tenant_id": TENANT, "scope_node_id": scope_node_id,
             "entity_mode": ENTITY_MODE} for r in rows]


def _csv(columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> bytes:
    """CSV 바이트. ⚠️ 줄바꿈을 `\\n` 으로 고정한다 — 플랫폼마다 다르면 체크섬이 달라진다."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue().encode("utf-8")


# ── PRC-02 구매주문 행 ───────────────────────────────────────────────────
#   ★ 선적의 자재를 찾는 **유일한 근거**다(LOG-02 에 자재 ID 가 없다).

PRC02_COLUMNS = ("po_line_id", "contract_id", "supplier_id", "material_id",
                 "order_quantity", "unit", "promised_date", "unit_price_krw")

_PRC02: Tuple[Dict[str, Any], ...] = (
    {"po_line_id": "POL-0001", "contract_id": "CTR-LI-01", "supplier_id": "SUP-AU-01",
     "material_id": MAT_LI, "order_quantity": "600", "unit": "KG",
     "promised_date": "2026-08-10T00:00:00+00:00", "unit_price_krw": "31000"},
    {"po_line_id": "POL-0002", "contract_id": "CTR-LI-01", "supplier_id": "SUP-AU-01",
     "material_id": MAT_LI, "order_quantity": "400", "unit": "KG",
     "promised_date": "2026-08-18T00:00:00+00:00", "unit_price_krw": "31000"},
    {"po_line_id": "POL-0003", "contract_id": "CTR-NI-01", "supplier_id": "SUP-ID-01",
     "material_id": MAT_NI, "order_quantity": "900", "unit": "KG",
     "promised_date": "2026-08-05T00:00:00+00:00", "unit_price_krw": "18500"},
    {"po_line_id": "POL-0004", "contract_id": "CTR-NI-01", "supplier_id": "SUP-ID-01",
     "material_id": MAT_NI, "order_quantity": "500", "unit": "KG",
     "promised_date": "2026-09-02T00:00:00+00:00", "unit_price_krw": "18500"},
)

# ── LOG-02 선적 ─────────────────────────────────────────────────────────
LOG02_COLUMNS = ("shipment_id", "po_line_id", "carrier_id", "shipment_quantity",
                 "unit", "etd", "eta", "status")

_LOG02: Tuple[Dict[str, Any], ...] = (
    #: ① 예정 도착이 지났는데 실제 도착이 없다 → **지연**(이야기의 출발점).
    {"shipment_id": "SHP-0001", "po_line_id": "POL-0001", "carrier_id": "CAR-01",
     "shipment_quantity": "600", "unit": "KG", "etd": "2026-07-28T00:00:00+00:00",
     "eta": "2026-08-14T00:00:00+00:00", "status": "IN_TRANSIT"},
    #: ② 아직 예정 전 — 운송 중이지만 지연은 아니다(대조군이 자료 안에 있어야 한다).
    {"shipment_id": "SHP-0002", "po_line_id": "POL-0002", "carrier_id": "CAR-01",
     "shipment_quantity": "400", "unit": "KG", "etd": "2026-08-12T00:00:00+00:00",
     "eta": "2026-08-30T00:00:00+00:00", "status": "IN_TRANSIT"},
    #: ③ 이미 도착 — `status` 만 보면 ①과 구분되지 않는다(실측된 함정).
    {"shipment_id": "SHP-0003", "po_line_id": "POL-0003", "carrier_id": "CAR-02",
     "shipment_quantity": "900", "unit": "KG", "etd": "2026-07-20T00:00:00+00:00",
     "eta": "2026-08-06T00:00:00+00:00", "status": "DELIVERED"},
    #: ④ 아직 출발 전.
    {"shipment_id": "SHP-0004", "po_line_id": "POL-0004", "carrier_id": "CAR-02",
     "shipment_quantity": "500", "unit": "KG", "etd": "2026-09-01T00:00:00+00:00",
     "eta": "2026-09-18T00:00:00+00:00", "status": "PLANNED"},
)

# ── LOG-03 선적 Milestone ───────────────────────────────────────────────
#   ★★ 운송 중 판정의 **정본**이다. `LOG-02.status` 가 아니다.

LOG03_COLUMNS = ("milestone_id", "shipment_id", "event_type", "planned_at", "actual_at",
                 "location_id")

_LOG03: Tuple[Dict[str, Any], ...] = (
    {"milestone_id": "MS-0001", "shipment_id": "SHP-0001", "event_type": "ATD",
     "planned_at": "2026-07-28T00:00:00+00:00", "actual_at": "2026-07-29T00:00:00+00:00",
     "location_id": "PORT-DAMPIER"},
    {"milestone_id": "MS-0002", "shipment_id": "SHP-0002", "event_type": "ATD",
     "planned_at": "2026-08-12T00:00:00+00:00", "actual_at": "2026-08-12T00:00:00+00:00",
     "location_id": "PORT-DAMPIER"},
    {"milestone_id": "MS-0003", "shipment_id": "SHP-0003", "event_type": "ATD",
     "planned_at": "2026-07-20T00:00:00+00:00", "actual_at": "2026-07-20T00:00:00+00:00",
     "location_id": "PORT-SURABAYA"},
    #: ★ 실제 도착은 여기에만 있다 — `LOG-02.status='DELIVERED'` 는 근거가 아니다.
    {"milestone_id": "MS-0004", "shipment_id": "SHP-0003", "event_type": "ATA",
     "planned_at": "2026-08-06T00:00:00+00:00", "actual_at": "2026-08-07T00:00:00+00:00",
     "location_id": "PORT-BUSAN"},
)

# ── INV-01 재고 스냅숏 ──────────────────────────────────────────────────
INV01_COLUMNS = ("snapshot_id", "material_id", "location_id", "snapshot_at",
                 "unrestricted_quantity", "reserved_quantity", "safety_stock_quantity",
                 "unit")

_INV01: Tuple[Dict[str, Any], ...] = (
    #: 옛 판 — **쓰이면 안 된다**(가장 최근 판만 쓴다). 자료 안에 함정을 남겨 둔다.
    {"snapshot_id": "STK-0001", "material_id": MAT_LI, "location_id": "WH-POHANG",
     "snapshot_at": "2026-08-10T00:00:00+00:00", "unrestricted_quantity": "980",
     "reserved_quantity": "0", "safety_stock_quantity": "200", "unit": "KG"},
    #: 최신 판 — 리튬이 모자라다(이야기의 핵심).
    {"snapshot_id": "STK-0002", "material_id": MAT_LI, "location_id": "WH-POHANG",
     "snapshot_at": "2026-08-20T00:00:00+00:00", "unrestricted_quantity": "260",
     "reserved_quantity": "0", "safety_stock_quantity": "200", "unit": "KG"},
    {"snapshot_id": "STK-0003", "material_id": MAT_NI, "location_id": "WH-POHANG",
     "snapshot_at": "2026-08-20T00:00:00+00:00", "unrestricted_quantity": "1400",
     "reserved_quantity": "0", "safety_stock_quantity": "300", "unit": "KG"},
)

# ── MFG-01 생산계획 ─────────────────────────────────────────────────────
MFG01_COLUMNS = ("plan_line_id", "site_id", "product_id", "plan_quantity", "unit",
                 "plan_date", "priority")

_MFG01: Tuple[Dict[str, Any], ...] = (
    {"plan_line_id": "PPL-0001", "site_id": "PLANT-POHANG", "product_id": PRODUCT,
     "plan_quantity": "300", "unit": "KG", "plan_date": "2026-09-05T00:00:00+00:00",
     "priority": "1"},
    #: ★ 뒤 계획행 — 앞 행이 재고를 먼저 쓰므로 **계획량을 못 채운다**(배분 순서가 보인다).
    {"plan_line_id": "PPL-0002", "site_id": "PLANT-POHANG", "product_id": PRODUCT,
     "plan_quantity": "300", "unit": "KG", "plan_date": "2026-09-12T00:00:00+00:00",
     "priority": "2"},
)

# ── MDM-05 BOM·수율 ─────────────────────────────────────────────────────
MDM05_COLUMNS = ("bom_id", "line_no", "output_material_id", "input_material_id",
                 "quantity_per_output", "standard_yield", "effective_from",
                 "effective_to")

_MDM05: Tuple[Dict[str, Any], ...] = (
    #: ★ 같은 자재가 **두 줄**이다(§7.2 — 자재별로 먼저 합산해야 한다).
    {"bom_id": "BOM-NCM811", "line_no": "1", "output_material_id": PRODUCT,
     "input_material_id": MAT_LI, "quantity_per_output": "0.42",
     "standard_yield": "0.925", "effective_from": "2026-01-01T00:00:00+00:00",
     "effective_to": ""},
    {"bom_id": "BOM-NCM811", "line_no": "2", "output_material_id": PRODUCT,
     "input_material_id": MAT_LI, "quantity_per_output": "0.08",
     "standard_yield": "0.925", "effective_from": "2026-01-01T00:00:00+00:00",
     "effective_to": ""},
    {"bom_id": "BOM-NCM811", "line_no": "3", "output_material_id": PRODUCT,
     "input_material_id": MAT_NI, "quantity_per_output": "1.35",
     "standard_yield": "0.925", "effective_from": "2026-01-01T00:00:00+00:00",
     "effective_to": ""},
)

# ── SLS-01 판매행 ───────────────────────────────────────────────────────
SLS01_COLUMNS = ("sales_line_id", "customer_id", "product_id", "order_quantity", "unit",
                 "due_date", "actual_ship_date")

_SLS01: Tuple[Dict[str, Any], ...] = (
    {"sales_line_id": "SOL-0001", "customer_id": "CUS-CELL-A", "product_id": PRODUCT,
     "order_quantity": "300", "unit": "KG", "due_date": "2026-09-20T00:00:00+00:00",
     "actual_ship_date": ""},
    {"sales_line_id": "SOL-0002", "customer_id": "CUS-CELL-B", "product_id": PRODUCT,
     "order_quantity": "300", "unit": "KG", "due_date": "2026-09-28T00:00:00+00:00",
     "actual_ship_date": ""},
)

#: ★★★ **승인된 생산-판매 배분.** 정본 데이터에 없고 승인에서 온다(§관계표
#: `FULFILLS_SALES` 의 근거가 «승인된 allocation» 이다).
#: ⚠️ 제품·기간이 같다고 코드가 이어 붙이면 그것은 승인이 아니라 추측이다.
SALES_ALLOCATION: Dict[str, str] = {"SOL-0001": "PPL-0001", "SOL-0002": "PPL-0002"}

#: ★ 인식 기간(일). 이것도 정본에 없고 **승인된 인식 규칙**에서 온다.
RECOGNITION_SPAN_DAYS: Dict[str, str] = {"SOL-0001": "30", "SOL-0002": "30"}

#: ★ 기준선 인식일. 시나리오 이연은 **이 값과의 차이**다(§7.3).
BASELINE_RECOGNITION: Dict[str, str] = {
    "SOL-0001": "2026-09-30T00:00:00+00:00",
    "SOL-0002": "2026-10-08T00:00:00+00:00",
}

#: 계약키 → (열, 행). ⚠️ 순서를 고정한다 — 적재 순서가 바뀌면 지문이 달라진다.
DATASETS: Tuple[Tuple[str, Tuple[str, ...], Tuple[Dict[str, Any], ...]], ...] = (
    ("PRC-02", PRC02_COLUMNS, _PRC02),
    ("LOG-02", LOG02_COLUMNS, _LOG02),
    ("LOG-03", LOG03_COLUMNS, _LOG03),
    ("INV-01", INV01_COLUMNS, _INV01),
    ("MFG-01", MFG01_COLUMNS, _MFG01),
    ("MDM-05", MDM05_COLUMNS, _MDM05),
    ("SLS-01", SLS01_COLUMNS, _SLS01),
)


def rows_for(key: str, *, scope_node_id: str = DEFAULT_SCOPE) -> List[Dict[str, Any]]:
    for k, _cols, rows in DATASETS:
        if k == key:
            return _with_scope(rows, scope_node_id)
    raise KeyError(key)


def columns_for(key: str) -> List[str]:
    for k, cols, _rows in DATASETS:
        if k == key:
            return list(cols) + list(SCOPE_COLUMNS)
    raise KeyError(key)


def csv_for(key: str, *, scope_node_id: str = DEFAULT_SCOPE) -> bytes:
    for k, cols, rows in DATASETS:
        if k == key:
            return _csv(list(cols) + list(SCOPE_COLUMNS),
                        _with_scope(rows, scope_node_id))
    raise KeyError(key)


def assumptions() -> Dict[str, Any]:
    """계산 요청에 실리는 가정 묶음. **지문에 들어간다.**

    ⚠️ `reserved_quantity_zero` 는 데모 가정이다(§7.1) — 운영에서는 예약·할당 데이터
      없이 0 으로 간주하면 안 된다."""
    return {
        "reserved_quantity_zero": True,
        "sales_allocation": dict(SALES_ALLOCATION),
        "recognition_span_days": dict(RECOGNITION_SPAN_DAYS),
        "baseline_recognition": dict(BASELINE_RECOGNITION),
    }
