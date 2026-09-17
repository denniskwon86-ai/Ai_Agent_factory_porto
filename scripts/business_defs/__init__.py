"""사업 정의 — **키트는 회사가 아니라 사업의 조합이다.**

## 왜 필요한가

⚠️ `KIT-MFG-NONFERROUS-PROCUREMENT` 는 **LS MnM 이라는 회사**를 모델링했고 제련과
  황산니켈이 한 덩어리였다. 그래서 고려아연(제련만)·켐코(황산니켈만)·대한전선
  (전선만)에는 **줄 수가 없다.** 같은 사업을 하는 다른 회사에 못 쓰는 키트다.

그런데 데이터는 이미 갈려 있었다 — 모든 데이터셋의 `scope_node_id` 가 사업을 가르고
(`plant-afs-smelting-01` vs `plant-afs-battery-02`), 조직에도 사업부가 있다.
**물리적으로 한 덩어리지만 논리적으로는 분리돼 있었다.**

그것을 실제로 갈라 낸 것이 이 패키지다.

## 무엇이 사업별이고 무엇이 공통인가

35 종 계약을 `scope_node_id` 분포로 갈라 보면 이렇다.

| 부류 | 종 | 무엇 |
|---|---|---|
| **사업별** | **20** | 품목 · 위치 · BOM · 공정 · 구매 · 물류 · 재고 · 생산 · 품질 · 판매 · 원가 |
| 회사 공통 | 13 | 사용자 · 달력 · 공급사 · 고객 · 계정 · 무역조건 · 외부지표 · 동인 · 결정 · 문서 |
| 혼재 | 2 | 조직(`FND-01`) · 회계(`FIN-03`) |

**「35 종」은 사업 하나 기준이다.** 두 사업을 하면 사업별 20 종이 배가 된다.

## 쓰는 법

    build(businesses=["smelting_nonferrous", "battery_materials"])   # LS MnM
    build(businesses=["smelting_nonferrous"])                        # 고려아연
    build(businesses=["battery_materials"])                          # 켐코

## ★ 분리(1.1.0)와 개선(1.2.0)을 섞지 않았다

이 패키지는 처음에 **생성기 안에 있던 값을 옮겨 담기만 했다.** 둘을 다 넣으면
1.1.0 과 지문이 한 글자도 다르지 않았고, 그것이 「손실 없이 갈랐다」는 증거다.
그 증거는 이제 **1.1.0 의 지문 대장**이 갖고 있다.

그때 고칠 것이 보여도 고치지 않았다 — 분리와 개선을 섞으면 무엇이 깨졌는지 알 수
없게 된다. 그 개선을 **1.2.0 에서 했다**: 공정 분리 · 등급 · 부산물 판매 · 판매
단위 · 기초재고 창고 · 사업 경계(BOM 원료 · 실사 조정 · 재고 스냅샷).
"""
from __future__ import annotations

import importlib
from typing import Any, Dict, List, Sequence, Tuple


class BusinessDef:
    """사업 하나의 정의. **값만 담고 로직은 담지 않는다.**"""

    #: `B1 3단`에 대응한다 — 분류의 「공정·형태」가 곧 사업의 단위다
    code: str = ""
    name: str = ""
    #: 필드 확장이 붙는 좌표 (`FieldExtension.scope`)
    sector: str = ""

    #: 조직 — (법인, 사업부, 공장). 각 항목은 (node_id, code, name)
    legal_entity: Tuple[str, str, str] = ("", "", "")
    #: 법인 전사공통 노드. ⚠️ 코드 규칙이 법인마다 달라(`METALS_SHARED` vs
    #:   `ADV_SHARED`) 유도할 수 없어 명시한다
    shared: Tuple[str, str, str] = ("", "", "")
    division: Tuple[str, str, str] = ("", "", "")
    plant: Tuple[str, str, str] = ("", "", "")

    #: (material_id, name, type, uom, benchmark_code)
    materials: Sequence[Tuple[str, str, str, str, str]] = ()
    #: (location_id, name, storage_type, capacity, quick)
    locations: Sequence[Tuple[str, str, str, int, bool]] = ()
    #: {product_id: ((input_id, qty, role), ...)}
    recipes: Dict[str, Sequence[Tuple[str, float, str]]] = {}
    #: {product_id: standard_yield}
    yields: Dict[str, float] = {}
    #: {product_id: byproduct_material_id}
    byproducts: Dict[str, str] = {}
    #: 공정 이름 — `MDM-06` Routing. **사업마다 다르다** (건식 제련 ≠ 습식 정제)
    routing_ops: Sequence[str] = ()

    # ── 산업의 의미 (「기존 필드에 의미 넣기」 층)
    #
    # 아래 셋은 **열을 늘리지 않는다.** 이미 있는 `grade`·`unit_price`·`product_id`
    # 에 그 산업이 실제로 쓰는 값을 넣을 뿐이다. 스키마를 건드리지 않으므로 플랫폼
    # 쪽 변경이 없고, 그러면서 현업이 열었을 때 「우리 얘기」가 된다.
    #
    # ⚠️ **값은 공개 지식으로 쓴 초안이다.** 등급 체계가 **존재한다**는 구조는 확실
    #   하지만 정확한 품위·단가는 회사·계약마다 다르다 — 도메인 검토 대상.

    #: {material_id: grade} — 그 산업이 실제로 쓰는 등급. 없으면 `DEMO_STANDARD`
    grades: Dict[str, str] = {}
    #: 완제품 말고 **더 파는 것**. 제련은 부산물(황산·금)이 손익의 큰 몫이다
    sellable_extra: Sequence[str] = ()
    #: {material_id: unit_price} — 판매 단가. 없으면 생성기 기본값
    sale_prices: Dict[str, float] = {}
    #: {product_id: ((byproduct_id, 완제품 1 단위당 산출량), ...)}
    #: ⚠️ **팔려면 만들어야 한다.** 이것을 비운 채 `sellable_extra` 만 넣으면
    #:   재고가 마이너스로 간다 — 실제로 그렇게 만들었다가 잡았다(2026-09-17).
    byproduct_rates: Dict[str, Sequence[Tuple[str, float]]] = {}
    #: {material_id: 판매 1 건당 수량 배율}. 금은 kg 이고 양이 적다
    sale_qty_scale: Dict[str, float] = {}

    # ── 편의

    @property
    def plant_id(self) -> str:
        return self.plant[0]

    @property
    def entity_id(self) -> str:
        return self.legal_entity[0]

    @property
    def division_id(self) -> str:
        return self.division[0]

    def owns(self, material_id: str) -> bool:
        """이 사업이 만드는 품목인가. **BOM·Routing 의 범위를 정한다.**"""
        return any(m[0] == material_id for m in self.materials)

    def _loc(self, storage: str) -> str:
        for loc_id, _n, st, _c, _q in self.locations:
            if st == storage:
                return loc_id
        return ""

    @property
    def raw_location(self) -> str:
        """원료 입고처. 구매·물류·재고가 여기로 들어온다."""
        return self._loc("RAW")

    @property
    def fg_location(self) -> str:
        """제품 출고처. 생산 산출과 판매 출하가 여기서 나간다."""
        return self._loc("FINISHED")

    def has_location(self, loc_id: str) -> bool:
        return any(l[0] == loc_id for l in self.locations)

    #: 품목 유형이 어느 보관구분으로 가나. 앞에서부터 있는 것을 쓴다.
    _OPENING_ORDER = {
        "RAW": ("RAW",), "CONSUMABLE": ("RAW",),
        "WIP": ("WIP", "RAW"),                    # quick 에는 공정재고가 없다
        "FINISHED": ("FINISHED",), "BYPRODUCT": ("FINISHED",),
    }

    def opening_location(self, material_type: str, available: Sequence[str] = ()) -> str:
        """기초재고를 넣을 창고. **유형에 맞는 곳으로 간다.**

        ⚠️ 예전에는 공장마다 규칙이 달랐다 — 제련은 `RAW` 만 원료창고(즉 WIP 도
          제품창고로 갔다)였고 전지소재는 `FINISHED` 만 제품창고였다. **이유가
          없었고**, 분리할 때는 동작을 지키려고 그대로 옮겼다. 1.2.0 에서 고친다.
        """
        order = self._OPENING_ORDER.get(material_type, ("RAW",))
        for storage in order:
            loc = self._loc(storage)
            if loc and (not available or loc in available):
                return loc
        #: ⚠️ 못 찾으면 **첫 후보를 그대로 돌려준다.** 호출부가 실재·범위를 검증해
        #:   멈추게 돼 있는데(`Opening warehouse unavailable…`), 여기서 다른 창고로
        #:   조용히 바꾸면 **그 안전장치가 무력해진다.** 실제로 그렇게 만들었다가
        #:   `test_generator_must_stop_instead_of_falling_back` 이 잡았다.
        return self._loc(order[0]) or self.raw_location

    def grade_of(self, material_id: str) -> str:
        """그 품목의 등급. **비어 있으면 `DEMO_STANDARD`** — 의미가 없다는 표시다."""
        return self.grades.get(material_id) or "DEMO_STANDARD"


def load(codes: Sequence[str]) -> List[BusinessDef]:
    """사업 정의를 가져온다. **없는 것은 만들지 않는다** — 오타로 사업이 생기면
    빈 키트가 조용히 나온다."""
    out = []
    for c in codes:
        try:
            mod = importlib.import_module(f"{__name__}.{c}")
        except ModuleNotFoundError as e:
            if getattr(e, "name", "") not in (f"{__name__}.{c}", c):
                raise
            raise SystemExit(
                f"그런 사업 정의가 없습니다: {c}\n"
                f"  scripts/business_defs/{c}.py 를 만드십시오. "
                f"지금 있는 것: {', '.join(available())}") from None
        d = getattr(mod, "BUSINESS", None)
        if not isinstance(d, BusinessDef):
            raise SystemExit(f"scripts/business_defs/{c}.py 에 BUSINESS(BusinessDef) 가 없습니다.")
        if d.code != c:
            raise SystemExit(
                f"사업 코드 불일치: 파일 {c} · 정의 {d.code} — "
                f"복사해서 만들 때 code 를 고치지 않은 것으로 보입니다.")
        out.append(d)
    if not out:
        raise SystemExit("사업을 하나는 넣어야 합니다 — 키트는 사업의 조합입니다.")
    return out


def available() -> List[str]:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    return sorted(f[:-3] for f in os.listdir(here)
                  if f.endswith(".py") and not f.startswith("_"))


# ── 조합에서 뽑아 쓰는 것들 (생성기가 부른다)

def materials_of(defs: Sequence[BusinessDef]) -> List[Dict[str, Any]]:
    """사업들의 고정 품목을 순서대로. **순서가 지문을 좌우하므로 바꾸지 않는다.**"""
    out = []
    for d in defs:
        for code, name, typ, uom, benchmark in d.materials:
            out.append({"code": code, "name": name, "type": typ, "uom": uom,
                        "benchmark": benchmark, "scope": d.plant_id})
    return out


def locations_of(defs: Sequence[BusinessDef], quick: bool) -> List[Dict[str, Any]]:
    out = []
    for d in defs:
        for loc_id, name, storage, cap, in_quick in d.locations:
            if quick and not in_quick:
                continue
            out.append({"location_id": loc_id, "site_id": d.plant_id, "name": name,
                        "storage_type": storage, "capacity": cap})
    return out


def recipes_of(defs: Sequence[BusinessDef]) -> Dict[str, Sequence]:
    out: Dict[str, Sequence] = {}
    for d in defs:
        out.update(d.recipes)
    return out


def owner_of(defs: Sequence[BusinessDef], material_id: str,
             default: str = "") -> str:
    """그 품목을 만드는 사업의 공장. BOM·Routing 의 `_scope` 가 된다."""
    for d in defs:
        if d.owns(material_id):
            return d.plant_id
    return default or (defs[-1].plant_id if defs else "")


def yield_of(defs: Sequence[BusinessDef], product_id: str, default: float = 0.94) -> float:
    for d in defs:
        if product_id in d.yields:
            return d.yields[product_id]
    return default


def byproduct_of(defs: Sequence[BusinessDef], product_id: str) -> str:
    for d in defs:
        if product_id in d.byproducts:
            return d.byproducts[product_id]
    return ""


def routing_ops_for(defs: Sequence[BusinessDef], material_id: str) -> List[str]:
    """**그 제품을 만드는 사업의** 공정 이름.

    ⚠️ 예전 `routing_ops_of()` 는 **첫 사업 것을 전부에 썼다.** 그래서 전기동도
      「침출·용해 → 결정화」라는 습식 공정으로 만들어졌다. 실제 동 제련은 건식
      (배소 → 용련 → 전로정련 → 전해정련)이다.
    """
    for d in defs:
        if d.owns(material_id) and d.routing_ops:
            return list(d.routing_ops)
    for d in defs:                       # 더미 제품 — 첫 사업으로 떨어진다
        if d.routing_ops:
            return list(d.routing_ops)
    return []


def sellable_of(defs: Sequence[BusinessDef], finished: Sequence[str]) -> List[str]:
    """파는 품목. 완제품에 **사업이 더 판다고 한 것**(부산물)을 얹는다.

    ⚠️ 예전에는 `FINISHED` 만 팔았다. 그래서 **제련인데 황산도 금도 팔지 않는**
      데이터가 나왔다 — 제련사 손익의 큰 몫이 부산물인데도.
    """
    out = list(finished)
    for d in defs:
        for mid in d.sellable_extra:
            if mid not in out:
                out.append(mid)
    return out


def byproduct_rates_of(defs: Sequence[BusinessDef], product_id: str) -> Sequence[Tuple[str, float]]:
    """그 제품을 만들 때 **함께 나오는 것**. 판매 가능한 부산물은 여기서 생긴다."""
    for d in defs:
        if product_id in d.byproduct_rates:
            return d.byproduct_rates[product_id]
    return ()


def sale_qty_scale_of(defs: Sequence[BusinessDef], material_id: str) -> float:
    for d in defs:
        if material_id in d.sale_qty_scale:
            return d.sale_qty_scale[material_id]
    return 1.0


def grade_of(defs: Sequence[BusinessDef], material_id: str) -> str:
    for d in defs:
        if d.owns(material_id):
            return d.grade_of(material_id)
    return "DEMO_STANDARD"


def sale_price_of(defs: Sequence[BusinessDef], material_id: str, default: float) -> float:
    for d in defs:
        if material_id in d.sale_prices:
            return d.sale_prices[material_id]
    return default


def uom_of(defs: Sequence[BusinessDef], material_id: str, default: str = "TON") -> str:
    """판매·이동의 수량 단위. ⚠️ 예전에는 판매가 **전부 `TON` 고정**이었다 —
    부산물 금을 팔면 톤으로 팔린다."""
    for d in defs:
        for code, _n, _t, uom, _b in d.materials:
            if code == material_id:
                return uom or default
    return default


def by_plant(defs: Sequence[BusinessDef], plant_id: str) -> BusinessDef:
    """공장으로 사업을 찾는다. 못 찾으면 첫 사업 — **하드코딩된 `PLANT1 if … else
    PLANT2` 를 대신한다.**"""
    for d in defs:
        if d.plant_id == plant_id:
            return d
    return defs[0]


def by_location(defs: Sequence[BusinessDef], loc_id: str) -> BusinessDef:
    """창고로 사업을 찾는다. 예전에는 `"P1" in loc` 같은 문자열 검사였다."""
    for d in defs:
        if d.has_location(loc_id):
            return d
    return defs[0]


def by_material(defs: Sequence[BusinessDef], material_id: str) -> BusinessDef:
    for d in defs:
        if d.owns(material_id):
            return d
    return defs[-1]
