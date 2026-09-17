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

    #: 건식 제련 — 정광을 태워 녹이고 전기로 닦는다.
    #: ⚠️ 1.1.0 까지는 습식 공정 이름(「침출·용해 → 결정화」)을 전지소재와 **함께**
    #:   썼다. 전기동을 습식으로 만드는 셈이었다.
    routing_ops = ("배소", "용련", "전로정련", "정제", "전해정련")

    # ── 산업의 의미

    #: 제련의 등급은 **거래 조건 그 자체**다. 정광은 Cu 품위로 값이 정해지고
    #: (품위가 낮을수록 제련수수료를 더 받는다), 전기동은 LME 등록 등급이라야
    #: 거래소에 낼 수 있다.
    #: ⚠️ 품위 숫자는 공개 지식으로 쓴 초안이다 — **도메인 검토 대상**
    grades = {
        "RM-CU-CONC": "CU_25PCT",        # 동정광 — Cu 25% 내외가 표준 거래 품위
        "WIP-MATTE": "CU_60PCT",         # 매트
        "WIP-ANODE": "CU_99_5PCT",       # 아노드동
        "FG-CATHODE": "LME_GRADE_A",     # ★ 전기동 — LME 등록 등급(Cu 99.99%)
        "BP-H2SO4": "TECHNICAL_98PCT",   # 공업용 황산
        "BP-GOLD": "FINE_GOLD_9999",     # 순금 99.99%
    }

    #: ★ **제련사는 부산물로 번다.** 금속 가격은 헤지로 중립화하고, 제련수수료와
    #:   회수율과 **부산물**이 손익을 가른다. 1.1.0 까지는 부산물이 재고로 쌓이기만
    #:   하고 **한 톤도 팔리지 않았다** — 제련 현업이 열면 바로 보이는 자리다.
    sellable_extra = ("BP-H2SO4", "BP-GOLD")

    #: 전기동 9,500 을 기준으로 한 상대값이다. 황산은 **양이 많고 싸고**, 금은
    #: **양이 적고 압도적으로 비싸다** — 그 구조가 보여야 제련 데이터다.
    #: ⚠️ 절대값은 데모 척도다 — **도메인 검토 대상**
    sale_prices = {"BP-H2SO4": 40.0, "BP-GOLD": 79000.0}


BUSINESS = Smelting()
