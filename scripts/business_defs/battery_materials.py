"""전지소재 — MHP(니켈 중간재)를 사서 고순도 황산니켈을 만든다.

분류 좌표: 실제 회사는 법인 구조에 따라 갈린다.

| | KSIC | 판정 |
|---|---|---|
| 켐코 · 에코프로비엠 (별도 법인) | `C2820` | 부품제조 × 전자·정밀 × 전지·전원부품 |
| **LS MnM 배터리소재 사업부** (법인 안의 사업) | `C2421` | 모법인을 따라 제련으로 잡힌다 |

★ **같은 사업인데 법인 구조에 따라 분류가 달라진다.** 그래서 사업 정의는 분류
  좌표가 아니라 **사업 자체**를 단위로 둔다 — 그것이 이 패키지의 이유다.

## 이 사업의 얼개

    니켈 MHP    + 황산 + 소석회 → 조황산니켈 용액 → 고순도 황산니켈(FG-NISO4)
    Black Mass  + 황산 + 소석회 →                  배터리급 수산화리튬(FG-LIOH)

★ **원료가 둘이다.** 황산니켈은 광물 유래 MHP 로, 수산화리튬은 **사 오는 리사이클
  원료(Black Mass)**로 만든다. 1.2.0 까지 후자가 빠져 있었다 — 리튬을 리튬 없이
  만들고 있었다.

## ⚠️ 신규 사업 단계는 여기 담지 않는다

램프업(초기 저수율 → 목표 수율)·고객 인증·저가동은 **사업이 아니라 단계**의 문제라
회사 프로파일이 맡는다
(`docs/data-kits/LSMNM_BATTERY_NEWBIZ_REVIEW_2026-09-16.md`).
지금 `yields` 는 **안정 운영**을 전제한 값이다.
"""
from . import BusinessDef

_PLANT = "plant-afs-battery-02"


class BatteryMaterials(BusinessDef):
    code = "battery_materials"
    name = "전지소재"
    sector = "B:전자·정밀>전지·전원부품>전지소재"

    kit_id = "KIT-MFG-BATTERY-MATERIALS"
    kit_name = "전지소재(황산니켈) 업무키트"
    #: ★ 양극재사 규격을 통과하지 못하면 도금용·촉매용으로 훨씬 싸게 나간다 —
    #:   **품질과 인증이 손익을 가른다.**
    use_case = "원료 확보에서 배터리급 품질·고객 인증까지"

    legal_entity = ("org-afs-advanced", "AFS_ADVANCED", "AFS 첨단소재 주식회사")
    shared = ("org-afs-advanced-shared", "ADV_SHARED", "AFS 첨단소재 전사공통")
    division = ("org-afs-battery-bu", "BATTERY_BU", "배터리소재사업부")
    plant = (_PLANT, "BATTERY_P2", "제2공장(황산니켈)")

    materials = (
        ("RM-MHP", "니켈 MHP", "RAW", "TON", "NICKEL"),
        #: ★ **리사이클 원료.** 폐배터리를 파쇄한 분말을 **사 와서** 투입하고, 그
        #:   안에 든 리튬을 공정에서 뽑는다. 폐배터리를 직접 수거·파쇄하는 것은
        #:   **다른 사업**이다(회사 프로파일 `AFS-VIRTUAL-CIRCULAR-METALS`).
        ("RM-BLACKMASS", "Black Mass(폐배터리 파쇄분)", "RAW", "TON", "LITHIUM"),
        ("RM-H2SO4", "황산 98%", "RAW", "TON", "SULFURIC_ACID"),
        ("RM-LIME", "소석회", "RAW", "TON", "INDUSTRIAL_CHEMICAL"),
        ("WIP-NISO4", "조황산니켈 용액", "WIP", "TON", ""),
        ("FG-NISO4", "고순도 황산니켈", "FINISHED", "TON", "NICKEL_SULFATE"),
        ("FG-LIOH", "배터리급 수산화리튬", "FINISHED", "TON", "LITHIUM"),
    )

    locations = (
        ("LOC-P2-RAW", "원료창고", "RAW", 45000, True),
        ("LOC-P2-QI", "품질검사창고", "QUALITY", 8000, False),
        ("LOC-P2-WIP", "공정재고", "WIP", 18000, False),
        ("LOC-P2-FG", "제품창고", "FINISHED", 22000, True),
    )

    recipes = {
        "FG-NISO4": (("RM-MHP", 1.15, "INPUT"), ("RM-H2SO4", 0.32, "INPUT"),
                     ("RM-LIME", 0.08, "INPUT")),
        #: ⚠️ 1.2.0 까지 **리튬이 어디서 오는지가 없었다** — 황산·소석회만 있었고,
        #:   그것은 부재료다. 「없는 것을 만드는」 데이터였다.
        #:
        #: 5.2 톤의 근거: 수산화리튬(LiOH·H2O) 1 톤에 든 Li 가 165 kg(16.5%)이고,
        #: Black Mass 의 Li 함량 4% · 회수율 80% 로 보면 165/(0.04×0.8) ≈ 5.2 톤이다.
        #:
        #: ⚠️⚠️ **이 값은 리튬만 기준이다.** 실제로는 같은 Black Mass 에서 니켈·
        #:   코발트·망간도 함께 나오므로, 투입량을 리튬 하나에 전부 귀속시키는 것은
        #:   과하다. **공동 산출을 어떻게 배분하는지는 도메인 검토 대상**이다
        #:   (`docs/decisions/DOMAIN_REVIEW_BATTERY_2026-09-22.md` 2.1).
        "FG-LIOH": (("RM-BLACKMASS", 5.20, "INPUT"), ("RM-H2SO4", 0.12, "INPUT"),
                    ("RM-LIME", 0.05, "INPUT")),
    }
    yields = {"FG-NISO4": 0.94, "FG-LIOH": 0.94}
    byproducts = {}

    #: 습식 — 녹이고 걸러 결정으로 뽑는다. 1.1.0 까지 제련도 이 목록을 썼다.
    routing_ops = ("원료준비", "침출·용해", "정제", "결정화", "건조·포장")

    # ── 산업의 의미

    #: 전지소재의 등급은 **배터리급이냐 아니냐** 하나로 갈린다. 양극재사 규격을
    #: 통과하지 못하면 도금용·촉매용으로 훨씬 싸게 나간다.
    #: ⚠️ MHP 의 Ni 함량은 공개 지식으로 쓴 초안이다 — **도메인 검토 대상**
    #: ★ **완제품 단가는 사업이 준다**(1.4.0). 없으면 생성기의 더미 기본값으로
    #:   떨어진다 — 1.3.0 에서 `FG-LIOH` 가 그랬다. 그때는 더미 기본값이 32,000 이라
    #:   우연히 맞아 보였고, 더미를 1,200 으로 낮추자 **수산화리튬 매출이 57% 에서
    #:   4.5% 로 무너졌다.** 우연에 기대고 있었다는 것이 그때 드러났다.
    #:
    #: ⚠️ 두 값의 **상대 크기**는 도메인 검토 대상이다
    #:   (`docs/decisions/DOMAIN_REVIEW_BATTERY_2026-09-22.md` 2.3).
    sale_prices = {"FG-NISO4": 24000.0, "FG-LIOH": 32000.0}


    grades = {
        "RM-MHP": "NI_40PCT",            # 니켈 MHP — Ni 35~40% 가 통상
        #: ⚠️ Black Mass 는 보통 Ni+Co+Li 합산 함량으로 거래된다고 알고 있으나,
        #:   지금은 **리튬 기준**으로만 적었다 — 도메인 검토 대상
        "RM-BLACKMASS": "LI_4PCT",
        "RM-H2SO4": "TECHNICAL_98PCT",
        "RM-LIME": "INDUSTRIAL",
        "WIP-NISO4": "CRUDE_SOLUTION",   # 조황산니켈 — 아직 등급이 없다
        "FG-NISO4": "BATTERY_GRADE",     # ★ 배터리급
        "FG-LIOH": "BATTERY_GRADE",
    }

    #: 부산물이 없다 — 이 공정은 폐수·석고를 내지만 키트에 품목이 없다.
    #: 있는 그대로 비워 둔다(없는 것을 있다고 하지 않는다).
    sellable_extra = ()


BUSINESS = BatteryMaterials()
