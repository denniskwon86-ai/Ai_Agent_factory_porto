"""★★★ [G2 M0-3.1] **정본 스타터 키트에서 시연 부분집합을 뽑는다.**

## 왜 시드를 만들지 않고 뽑는가

앞 판은 시연 자료를 손으로 썼다. 그 순간 **열 이름을 내가 정하게** 되고, 실제 정본과
어긋나도 회귀는 초록이다(이미 한 번 그랬다 — `snapshot_at` vs `snapshot_date`).

★ 정본 CSV 에서 **행만 골라내면** 열 이름은 고를 여지가 없다. 이것이 「fixture 가 계약을
  대신 정의하는」 사고를 구조적으로 막는 유일한 방법이다.

    starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/samples/full/*.csv
      → 시연 이야기에 필요한 행만 결정론적으로 선별
      → 열은 **원본 그대로**

## 무엇을 고르나

`INV-01` 만 55,440행이라 전부 쓸 수 없다. 12분 시연의 한 이야기가 흐르는 최소 집합을
고른다 — 그리고 **고르는 규칙을 코드로 적는다**(손으로 행 번호를 적으면 자료가 바뀔 때
조용히 깨진다).

⚠️ 고르기는 **결정론적**이어야 한다. 정렬 없이 파일 순서에 기대면 자료가 재생성될 때
  다른 부분집합이 나오고, 그러면 「같은 입력 3회 같은 결과」를 증명할 수 없다.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: 정본 키트. ⚠️ **임의 생성 금지** — 시험이 만든 키트로 인증하면 「정본 열을 썼다」가
#: 증거가 되지 못한다(M0-3.1 지적).
KIT_ID = "KIT-MFG-NONFERROUS-PROCUREMENT"
KIT_VERSION = "1.0.0"

#: 계산 경로가 쓰는 7종. `PRC-02` 는 선적의 자재를 찾는 유일한 근거다.
SLICE_KEYS: Tuple[str, ...] = ("PRC-02", "LOG-02", "LOG-03", "INV-01",
                               "MFG-01", "MDM-05", "SLS-01")

#: 시연 기준 시각. ⚠️ 고정값 — `now()` 를 쓰면 매 실행마다 부분집합이 달라진다.
#:
#: ★★★ **자료에 맞춰 잡는다.** 정본 자료의 시간축은 2023-08 ~ 2026-08 이고, 계획·판매
#:   행이 «미래» 이려면 그 안쪽이어야 한다. 오늘 날짜를 쓰면 미래 계획이 0건이 되어
#:   「생산 차질 → 매출 이연」 이야기가 성립하지 않는다(실측: 2026-08-21 에서 0건).
#: ⚠️ 이 값을 바꾸면 부분집합이 달라지고 결과 지문도 달라진다 — 시연 대본과 함께 고칠 것.
AS_OF = "2026-06-01T00:00:00+00:00"

#: 시연 제품. 정본 `MDM-05.output_material_id` 에 실재하는 값이다.
PRODUCT = "FG-CATHODE"

#: 계획 지평 — **`as_of` 로부터 이만큼 뒤의 계획행**을 고른다.
#:
#: ## ⚠️⚠️ 0 이면 키트가 이틀 만에 아무 답도 못 낸다 (2026-08-24 실측)
#:
#: 종전에는 「`as_of` 이후 미래 계획행 앞 두 개」였다. 정본 계획은 거의 매일 있어서
#: 그 둘은 `as_of`+0 · `as_of`+2 였다. 재배치해도 **쓸 수 있는 창이 이틀**이고, 사흘째
#: 부터는 계획행이 전부 과거가 되어 생산가능량이 비고 계산이 `BLOCKED` 로 답한다.
#:
#: ★ 지평을 두면 이야기도 더 맞는다 — 「어제 실사한 재고」와 「한 달 반 뒤 계획」을
#:   비교하는 것이 「어제 재고 · 내일 계획」보다 실제 구매 의사결정에 가깝다.
#: ⚠️ 늘리려면 자료를 먼저 세어 볼 것. 정본 `MFG-01` 의 `FG-CATHODE` 계획은
#:   2026-07-30 까지이므로 60 이면 **0건**이 된다(실측).
HORIZON_DAYS = 45


# ── 업무 날짜 재배치 ─────────────────────────────────────────────────────
#:
#: ## ⚠️⚠️ 왜 필요한가 — 자료가 설치일보다 과거면 키트가 아무 숫자도 못 낸다
#:
#: `AS_OF` 는 **자료 안쪽**이어야 한다(위 주석 참조). 그런데 인증판과 관계 선언은
#: **설치 시각**에 찍힌다. 그래서 두 요구가 동시에 성립하지 않는다:
#:
#:   · 경로가 보이려면        `as_of ≥ certified_at`  (= 설치일)
#:   · 생산계획이 잡히려면    `as_of ≤ plan_date`     (= 정본 최대 2026-07-30)
#:
#: 실측(2026-08-24): 다섯 관문 전부 READY 인데 계산은 `BLOCKED` — 「기준선 없는
#: 판매행」이었다. 실제 원인은 계획행이 **전부 과거**여서 생산가능량이 비었던 것이다.
#: 업무 시점(2026-06-01)으로 돌리면 부족 4,366.7 · 이연 30일이 정상 산출된다.
#:
#: ★★★ 그래서 **자료의 업무 날짜를 통째로 옮긴다.** 정본 CSV 원본은 건드리지 않는다 —
#:   고른 조각에만 같은 오프셋을 더하므로 행 사이의 시간 관계(ETA↔ATA, 계획일↔납기)는
#:   **그대로 보존된다.**
#: ⚠️ 오프셋은 **한 번 정하면 고정**이다(`scripts/run_local_demo.py` 가 뿌리에 적어
#:   둔다). 실행할 때마다 다시 계산하면 나중에 보충한 판이 앞선 판과 다른 시간축에
#:   놓이고, 관계가 가리키는 객체 id 가 어긋난다.

#: 온전한 날짜/일시 문자열. ⚠️ 부분 일치를 허용하지 않는다 — 허용하면 「2026」 같은
#: 값이나 수량이 날짜로 보인다.
#: 「끝이 없다」를 뜻하는 해. 이 이상은 날짜로 다루지 않는다.
_SENTINEL_YEAR = 9000
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?![\d-])")
#: 식별자에 박힌 날짜(`STK-20260531-RM-CU-CONC-...`). ★ 이것도 옮기지 않으면 화면에
#: 「STK-20260531」인데 스냅샷 날짜는 8월인 물건이 생긴다.
_EMBEDDED_RE = re.compile(r"(?<!\d)(20[2-3]\d)(\d{2})(\d{2})(?!\d)")


def _shift_text(value: str, days: int) -> str:
    """문자열 하나에서 **날짜로 읽히는 것만** 옮긴다."""
    m = _DATE_RE.match(value)
    if m:
        try:
            base = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return value
        #: ⚠️ `9999-12-31` 은 날짜가 아니라 **「끝이 없다」는 표식**이다(`valid_to`·
        #:   `effective_to`). 옮기면 넘치고, 넘치지 않게 잘라도 유한한 종료일이 생겨
        #:   「아직 유효한 것」이 조용히 만료된다.
        if base.year >= _SENTINEL_YEAR:
            return value
        try:
            return (base + timedelta(days=days)).isoformat() + value[m.end():]
        except OverflowError:                       # pragma: no cover - 위에서 걸러진다
            return value

    def _one(mm: "re.Match[str]") -> str:
        try:
            base = date(int(mm.group(1)), int(mm.group(2)), int(mm.group(3)))
        except ValueError:
            return mm.group(0)
        return (base + timedelta(days=days)).strftime("%Y%m%d")

    return _EMBEDDED_RE.sub(_one, value)


def rebase(sl: Dict[str, Tuple[List[Dict[str, str]], List[str]]], days: int
           ) -> Tuple[Dict[str, Tuple[List[Dict[str, str]], List[str]]], Dict[str, int]]:
    """조각의 업무 날짜를 `days` 만큼 옮긴다. **모든 계약키에 같은 값을 쓴다.**

    돌려주는 것: `(옮긴 조각, {계약키: 바뀐 칸 수})` — 무엇이 바뀌었는지 셀 수 있어야
    「옮겼다」가 확인 가능한 주장이 된다.

    ⚠️ `days == 0` 이면 **원본을 그대로** 돌려준다(복사하지 않는다) — 옮기지 않은 것과
      옮겨서 같아진 것을 구분할 필요가 없고, 구분하려 들면 지문이 달라진다.
    """
    if not days:
        return sl, {}
    out: Dict[str, Tuple[List[Dict[str, str]], List[str]]] = {}
    counts: Dict[str, int] = {}
    for key, (rows, cols) in sl.items():
        moved = 0
        new_rows: List[Dict[str, str]] = []
        for row in rows:
            item: Dict[str, str] = {}
            for k, v in row.items():
                if isinstance(v, str) and v:
                    nv = _shift_text(v, days)
                    if nv != v:
                        moved += 1
                    item[k] = nv
                else:
                    item[k] = v
            new_rows.append(item)
        out[key] = (new_rows, cols)
        counts[key] = moved
    return out, counts


def kit_root() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "starter_kits", KIT_ID, KIT_VERSION)


def _read(key: str) -> Tuple[List[Dict[str, str]], List[str]]:
    path = os.path.join(kit_root(), "samples", "full", f"{key}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"정본 키트 자료가 없습니다: {path} — 시연 자료를 손으로 만들지 않습니다.")
    with io.open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(r) for r in reader]
        return rows, list(reader.fieldnames or [])


def kit_dataset_keys() -> List[str]:
    """정본 키트가 **실제로 들고 있는** 계약키 전부. 파일에서 센다.

    ★★★ [2026-08-23] 목록을 손으로 적지 않는다 — 적으면 키트가 늘어날 때 조용히
      어긋나고, 「없는 줄 알았던 것」이 생긴다.
    ⚠️ `SLICE_KEYS` 와 **다른 것**이다. 그쪽은 수직 폐루프 계산이 쓰는 최소 집합이고,
      이것은 키트 앱이 요구할 수 있는 전체다. 둘을 합치면 계산 경로의 뜻이 바뀐다."""
    root = os.path.join(kit_root(), "samples", "full")
    if not os.path.isdir(root):
        return []
    return sorted(f[:-4] for f in os.listdir(root) if f.endswith(".csv"))


def read_full(key: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """정본 CSV 를 **자르지 않고** 읽는다.

    ⚠️ 수직 폐루프는 시간축으로 잘라 쓴다(`build_slice`). 앱은 자르지 않는다 —
      앱 화면에서 「왜 우리 자료가 일부만 보이나」가 되면 그것은 다른 문제로 읽힌다."""
    return _read(key)


def _sorted_by(rows: Sequence[Dict[str, str]], *keys: str) -> List[Dict[str, str]]:
    """결정론적 정렬. ⚠️ 파일 순서에 기대면 자료 재생성 때 다른 집합이 나온다."""
    return sorted(rows, key=lambda r: tuple(str(r.get(k, "")) for k in keys))


def build_slice(*, scope_node_id: str = "", as_of: str = AS_OF
                ) -> Dict[str, Tuple[List[Dict[str, str]], List[str]]]:
    """시연 부분집합. 돌려주는 것: `{계약키: (행, 열)}` — **열은 정본 그대로**.

    ## 고르는 규칙

    1. `MDM-05` — 시연 제품의 BOM 행 전부(역할 무관. 계산이 `RETURN` 을 걸러 낸다).
    2. `MFG-01` — 그 제품의 **미래 계획행** 앞 두 개(우선순위·날짜 순).
       ★ 둘을 고르는 이유: **재고 배분 순서가 보이려면 계획행이 둘 이상**이어야 한다.
    3. `SLS-01` — 같은 제품의 판매행 앞 두 개.
    4. `INV-01` — BOM 이 요구하는 자재의 **`as_of` 이전 마지막 두 판**(자재당).
       ★ 두 판을 고르는 이유: 「가장 최근 판만 쓴다」가 실제로 검사되려면 옛 판이 있어야 한다.
    5. `PRC-02` — 그 자재들의 주문행.
    6. `LOG-02` — 그 주문행의 선적.
    7. `LOG-03` — 그 선적의 milestone 전부.

    ⚠️ 범위(`scope_node_id`)를 주면 그 범위 행만 고른다. 정본은 여러 조직에 걸쳐 있고,
      섞으면 조직 경계를 넘은 계산이 된다.
    """
    out: Dict[str, Tuple[List[Dict[str, str]], List[str]]] = {}
    raw: Dict[str, Tuple[List[Dict[str, str]], List[str]]] = {}
    for key in SLICE_KEYS:
        rows, cols = _read(key)
        if scope_node_id:
            rows = [r for r in rows if str(r.get("scope_node_id", "")) == scope_node_id]
        raw[key] = (rows, cols)

    # ① BOM
    bom_rows, bom_cols = raw["MDM-05"]
    bom = _sorted_by([r for r in bom_rows
                      if str(r.get("output_material_id", "")) == PRODUCT],
                     "bom_id", "line_no")
    if not bom:
        raise ValueError(f"MDM-05 에 {PRODUCT} 의 BOM 이 없습니다(범위 {scope_node_id!r}).")
    out["MDM-05"] = (bom, bom_cols)
    materials = sorted({str(r.get("input_material_id", "")) for r in bom
                        if str(r.get("component_role", "")).upper() == "INPUT"})

    # ② 생산계획 — 미래 계획행 둘
    plan_rows, plan_cols = raw["MFG-01"]
    #: ★ `as_of` 가 아니라 **`as_of` + 지평** 이후를 본다(`HORIZON_DAYS` 주석 참조).
    horizon = (date.fromisoformat(as_of[:10]) + timedelta(days=HORIZON_DAYS)).isoformat()
    future = [r for r in plan_rows
              if str(r.get("product_id", "")) == PRODUCT
              and str(r.get("plan_date", "")) >= horizon]
    plan = _sorted_by(future, "priority", "plan_date", "plan_line_id")[:2]
    if len(plan) < 2:
        raise ValueError(
            f"MFG-01 에 {PRODUCT} 의 계획행이 {horizon} 이후로 둘 미만입니다 — 배분 "
            f"순서를 보여 줄 수 없습니다(찾은 수 {len(plan)}). 지평(HORIZON_DAYS="
            f"{HORIZON_DAYS})이 자료의 끝을 넘었는지 확인하십시오.")
    #: ★★★ [M0-3.1 실측] **정본의 `material_requirement` 가 BOM 재계산과 어긋난다.**
    #:   이 범위의 200건 **전부**가 불일치다(예: 저장 137.78 vs 재계산 139.745).
    #:
    #: 계약 §7.2 는 「BOM 이 정본이고, 저장값과 다르면 하나를 임의로 고르지 않고
    #: 실패한다」로 정했다. 그래서 이 자료를 그대로 넣으면 경로가 `BLOCKED` 된다 —
    #: **계약이 정한 대로 작동한 것이지 결함이 아니다.**
    #:
    #: ★ 시연 부분집합에서는 **BOM 정본으로 파생값을 다시 계산해 넣는다.** 이것은
    #:   「하나를 고르는」 것이 아니라 정본 규칙으로 파생값을 복원하는 것이다.
    #: ⚠️ **원본 파일은 고치지 않는다.** 보정은 부분집합에만 적용하고, 보정 건수를
    #:   돌려줘 기록에 남긴다 — 조용히 고치면 「원래 맞았던 자료」로 오해된다.
    plan = _reconcile_requirement(plan, bom)
    out["MFG-01"] = (plan, plan_cols)

    # ③ 판매행 둘
    sls_rows, sls_cols = raw["SLS-01"]
    #: ★★★ 판매행은 **고른 계획행보다 뒤**여야 한다. 앞이면 「생산 차질 → 매출 이연」이
    #:   거꾸로 선다 — 아직 만들지도 않은 것의 납기가 이미 지난 이야기가 된다.
    #: ⚠️ 종전에는 `as_of` 만 봤다. 계획이 `as_of`+0 이던 시절에는 우연히 뒤였다.
    last_plan = max(str(r.get("plan_date", ""))[:10] for r in plan)
    sales = _sorted_by([r for r in sls_rows
                        if str(r.get("product_id", "")) == PRODUCT
                        and str(r.get("due_date", "")) >= last_plan],
                       "due_date", "sales_line_id")[:2]
    if len(sales) < 2:
        raise ValueError(
            f"SLS-01 에 {PRODUCT} 의 판매행이 마지막 계획일({last_plan}) 이후로 둘 "
            f"미만입니다 — 생산 차질이 어느 매출을 미루는지 말할 수 없습니다.")
    out["SLS-01"] = (sales, sls_cols)

    # ④ 재고 — 자재별 as_of 이전 마지막 두 판
    inv_rows, inv_cols = raw["INV-01"]
    inv: List[Dict[str, str]] = []
    for mat in materials:
        mine = _sorted_by([r for r in inv_rows
                           if str(r.get("material_id", "")) == mat
                           and str(r.get("snapshot_date", "")) <= as_of[:10]],
                          "snapshot_date", "location_id", "snapshot_id")
        if not mine:
            raise ValueError(f"INV-01 에 자재 {mat} 의 재고가 없습니다 — 없는 것을 0 으로 "
                             f"보지 않습니다.")
        inv.extend(mine[-2:])
    out["INV-01"] = (inv, inv_cols)

    # ⑤ 주문행 → ⑥ 선적 → ⑦ milestone
    prc_rows, prc_cols = raw["PRC-02"]
    po = _sorted_by([r for r in prc_rows
                     if str(r.get("material_id", "")) in materials], "po_line_id")
    log2_rows, log2_cols = raw["LOG-02"]
    po_ids = {str(r.get("po_line_id", "")) for r in po}
    ships = _sorted_by([r for r in log2_rows
                        if str(r.get("po_line_id", "")) in po_ids], "shipment_id")
    #: ★ 선적을 전부 쓰면 자료가 커진다. 이야기에 필요한 만큼만 — **결정론적으로** 앞 여섯.
    ships = ships[:6]
    ship_ids = {str(r.get("shipment_id", "")) for r in ships}
    #: ⚠️ 주문행은 **고른 선적이 가리키는 것만** 남긴다. 남기면 투영이 「자재를 못 찾는
    #:   선적」을 만들지 않는다.
    keep_po = {str(r.get("po_line_id", "")) for r in ships}
    out["PRC-02"] = ([r for r in po if str(r.get("po_line_id", "")) in keep_po], prc_cols)
    out["LOG-02"] = (ships, log2_cols)

    log3_rows, log3_cols = raw["LOG-03"]
    ms = _sorted_by([r for r in log3_rows
                     if str(r.get("shipment_id", "")) in ship_ids],
                    "shipment_id", "milestone_id")
    out["LOG-03"] = (ms, log3_cols)

    for key in SLICE_KEYS:
        if not out[key][0]:
            raise ValueError(f"{key}: 시연 부분집합이 비었습니다 — 빈 자료로 계산하지 않습니다.")
    return out


def _reconcile_requirement(plan: Sequence[Dict[str, str]],
                           bom: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    """`material_requirement` 를 **BOM 정본으로 다시 계산**해 넣는다.

    ⚠️ 열이 없으면 넣지 않는다 — 없는 열을 만들어 넣으면 정본 스키마가 달라진다.
    ★ 계산 규칙은 `calc_models.material_shortage` 와 **같아야** 한다. 두 벌로 쓰면
      보정한 값이 다시 대사에 걸린다."""
    from decimal import ROUND_HALF_UP, Decimal
    qpo: Dict[Tuple[str, str], Decimal] = {}
    yld: Dict[Tuple[str, str], Decimal] = {}
    for b in bom:
        if str(b.get("component_role", "")).upper() != "INPUT":
            continue
        k = (str(b.get("output_material_id", "")), str(b.get("input_material_id", "")))
        qpo[k] = qpo.get(k, Decimal(0)) + Decimal(str(b.get("quantity_per_output", "0")))
        yld[k] = Decimal(str(b.get("standard_yield", "1")))
    out = []
    for row in plan:
        item = dict(row)
        if "material_requirement" not in item:
            out.append(item)
            continue
        prod = str(item.get("product_id", ""))
        keys = [k for k in qpo if k[0] == prod]
        if not keys:
            out.append(item)
            continue
        need = sum(Decimal(str(item.get("plan_quantity", "0"))) * qpo[k] / yld[k]
                   for k in keys)
        item["material_requirement"] = str(
            need.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
        out.append(item)
    return out


def csv_bytes(rows: Sequence[Dict[str, str]], columns: Sequence[str]) -> bytes:
    """CSV 바이트. ⚠️ 줄바꿈을 고정한다 — 플랫폼마다 다르면 체크섬이 달라진다."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue().encode("utf-8")


def scope_of(sl: Dict[str, Tuple[List[Dict[str, str]], List[str]]]) -> Tuple[str, str]:
    """부분집합의 `(tenant_id, scope_node_id)`. **하나여야 한다.**

    ⚠️ 여러 조직이 섞이면 조직 경계를 넘은 계산이 된다 — 그것을 여기서 막는다."""
    tenants = {str(r.get("tenant_id", "")) for _k, (rows, _c) in sl.items() for r in rows}
    scopes = {str(r.get("scope_node_id", "")) for _k, (rows, _c) in sl.items() for r in rows}
    if len(tenants) != 1 or len(scopes) != 1:
        raise ValueError(
            f"부분집합에 조직이 섞였습니다(tenant {sorted(tenants)}, "
            f"scope {sorted(scopes)}) — 경계를 넘은 계산이 됩니다.")
    return tenants.pop(), scopes.pop()


def assumptions(sl: Dict[str, Tuple[List[Dict[str, str]], List[str]]]
                ) -> Dict[str, Any]:
    """계산 요청에 실리는 가정. **지문에 들어간다.**

    ⚠️ `sales_allocation`·`recognition_span_days`·`baseline_recognition` 은 정본에 없다 —
      **승인된 배분·인식 규칙·기준선**에서 와야 한다. 지금은 시연용으로 여기서 만들지만,
      그것이 곧 M0-3.2 가 닫아야 할 자리다(호출자 자기진술).
    """
    plan_ids = [str(r["plan_line_id"]) for r in sl["MFG-01"][0]]
    sales_ids = [str(r["sales_line_id"]) for r in sl["SLS-01"][0]]
    alloc = {s: p for s, p in zip(sales_ids, plan_ids)}
    return {
        "reserved_quantity_zero": True,
        "date_only_rule": "date_only_is_midnight_utc",
        "sales_allocation": alloc,
        "recognition_span_days": {s: "30" for s in sales_ids},
        #: 기준선 인식일 = 납기일 + 인식 기간. ⚠️ 시연 가정이다 — 승인된 기준선이 아니다.
        "baseline_recognition": {
            str(r["sales_line_id"]): f'{r["due_date"]}T00:00:00+00:00'
            for r in sl["SLS-01"][0]},
    }


def register_kit(store: Any) -> Dict[str, Any]:
    """정본 스타터 키트를 **등록부에 올린다.**

    ★★★ [M0-3.1 ④] `create_instance` 는 이제 등록된 판본만 받는다. 그래서 정본 키트를
      먼저 등록해야 하고, 그 지문은 **manifest 파일에서 계산**한다 — 손으로 적으면
      그것이 다시 자기진술이다.

    ⚠️ 「등록은 나중에」로 두면 정본이 아닌 계약으로 인증판이 쌓이고, 그 판들은 나중에
      어느 계약의 것인지 말할 수 없다.
    """
    from core.data_preparation import kit_registry
    manifest = os.path.join(kit_root(), "manifest.json")
    if not os.path.exists(manifest):
        raise FileNotFoundError(f"정본 키트 manifest 가 없습니다: {manifest}")
    with io.open(manifest, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    #: ★★★ [2026-08-23 실측] **raw 를 그대로 넣지 않는다.** manifest 는 데이터셋을
    #:   `dataset_id` 로 적고 등록부 독자는 `dataset_contract_key` 를 찾는다 — raw 로
    #:   넣었더니 준비도 보드가 계약키를 0개로 보고, 인증판 7종이 있는데 「required 0」
    #:   으로 답했다. 0은 「없다」로 읽힌다.
    profile = kit_registry.profile_from_manifest(raw)
    return store.upsert_kit_version(
        kit_id=KIT_ID, version=KIT_VERSION,
        name=str(profile.get("company_name") or KIT_ID),
        #: ⚠️ 이 자료는 합성이다 — 모드를 실제 업무로 적으면 둘이 섞인다.
        mode="DEMO/SYNTHETIC",
        source_path=os.path.relpath(manifest, os.path.dirname(kit_root())),
        fingerprint_value=kit_registry.file_fingerprint(manifest),
        profile=profile)


def kit_fingerprint(store: Any) -> str:
    """등록된 정본 키트의 지문. ⚠️ 손으로 적지 않는다 — 등록부에서 읽는다."""
    row = store.get_kit_version(KIT_ID, KIT_VERSION)
    if not row:
        raise ValueError(f"정본 키트가 등록되지 않았습니다: {KIT_ID}/{KIT_VERSION}")
    return str(row.get("fingerprint", ""))
