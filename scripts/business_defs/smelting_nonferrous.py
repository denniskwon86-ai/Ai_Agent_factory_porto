"""제련·정련 (비철금속) — 정광을 사서 금속을 돌려주고 수수료로 번다.

분류 좌표: `소재제조 × 금속 × 비철금속 × 제련·정련`
대상: 롱리스트 11 개사 30.6 조 (엘에스엠앤엠 14.4 조 · 고려아연 10.5 조 …)

## 이 사업의 얼개

    동정광(RM-CU-CONC) → 동 매트 → 아노드동 → 전기동(FG-CATHODE)
                                              ↘ 부산물 황산 · 금

⚠️ **제련사는 금속 가격으로 벌지 않는다.** 가격은 헤지로 중립화하고 제련수수료
  (TC/RC)·회수율·부산물로 번다. 그 인과는 아직 드라이버로 들어가 있지 않다
  (`docs/data-kits/NONFERROUS_SMELTING_SPECIALIZATION_DRAFT_2026-09-09.md`).
"""
from . import BusinessDef

_PLANT = "plant-afs-smelting-01"


class Smelting(BusinessDef):
    code = "smelting_nonferrous"
    name = "제련·정련"
    sector = "B:금속>비철금속>제련·정련"

    legal_entity = ("org-afs-metals", "AFS_METALS", "AFS 메탈 주식회사")
    shared = ("org-afs-metals-shared", "METALS_SHARED", "AFS 메탈 전사공통")
    division = ("org-afs-smelting-bu", "SMELTING_BU", "제련사업부")
    plant = (_PLANT, "SMELTING_P1", "제1공장(제련·정제)")

    #: (material_id, name, type, uom, benchmark_code)
    materials = (
        ("RM-CU-CONC", "동정광", "RAW", "TON", "LME_COPPER"),
        ("WIP-MATTE", "동 매트", "WIP", "TON", ""),
        ("WIP-ANODE", "아노드동", "WIP", "TON", ""),
        ("FG-CATHODE", "전기동", "FINISHED", "TON", "COPPER"),
        ("BP-H2SO4", "부산물 황산", "BYPRODUCT", "TON", "SULFURIC_ACID"),
        ("BP-GOLD", "부산물 금", "BYPRODUCT", "KG", "GOLD"),
    )

    #: (location_id, name, storage_type, capacity, quick 에 넣나)
    locations = (
        ("LOC-P1-RAW", "원료창고", "RAW", 80000, True),
        ("LOC-P1-WIP", "공정재고", "WIP", 40000, False),
        ("LOC-P1-FG", "제품창고", "FINISHED", 30000, True),
    )

    recipes = {
        #: 정광 3.3 톤에서 전기동 1 톤. 매트는 공정 내 반송(RETURN)이다.
        "FG-CATHODE": (("RM-CU-CONC", 3.30, "INPUT"), ("WIP-MATTE", 0.02, "RETURN")),
    }
    yields = {"FG-CATHODE": 0.98}
    byproducts = {"FG-CATHODE": "BP-H2SO4"}

    #: ⚠️ 지금은 습식 정제 공정 이름이다. 건식 제련(배소·용련·전해정련)과 다르지만
    #:   **분리하면서 고치지 않았다** — 분리와 개선을 섞으면 무엇이 깨졌는지 모른다.
    routing_ops = ("원료준비", "침출·용해", "정제", "결정화", "건조·포장")
    #: 원래 로직: `PLANT1 이고 RAW 면 원료창고, 아니면 제품창고`
    opening_stock_to_fg = ("WIP", "FINISHED", "BYPRODUCT", "CONSUMABLE")


BUSINESS = Smelting()
