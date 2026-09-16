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

## ★ 분리는 동작을 바꾸지 않는다

이 패키지는 **생성기 안에 있던 값을 옮겨 담았을 뿐**이다. 둘을 다 넣으면 1.1.0 과
지문이 같아야 하고, 그것이 「손실 없이 갈랐다」는 유일한 증거다.

고칠 것이 보여도(예: `routing_ops` 가 두 사업 공통인데 실제 공정은 다르다) **여기서
고치지 않는다.** 분리와 개선을 섞으면 무엇이 깨졌는지 알 수 없게 된다.
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
    #: 공정 이름 — `MDM-06` Routing
    routing_ops: Sequence[str] = ()
    #: 기초재고를 **제품창고**에 넣는 품목 유형. 나머지는 원료창고로 간다.
    #: ⚠️ 원래 로직이 공장마다 달랐고 **이유가 없다** — 제련은 RAW 만 원료창고였고
    #:   전지소재는 FINISHED 만 제품창고였다. 분리하면서 그대로 옮겼다(동작 보존).
    #:   통일하면 `INV-01`·`INV-02` 지문이 바뀐다.
    opening_stock_to_fg: Sequence[str] = ("FINISHED",)

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


def routing_ops_of(defs: Sequence[BusinessDef]) -> List[str]:
    """공정 이름. ⚠️ **지금은 두 사업이 같은 목록을 쓴다** — 실제로는 건식 제련과
    습식 정제가 다르지만, 분리하면서 고치지 않았다(동작 보존)."""
    for d in defs:
        if d.routing_ops:
            return list(d.routing_ops)
    return []


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
