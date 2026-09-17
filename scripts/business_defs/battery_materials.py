"""전지소재 — MHP(니켈 중간재)를 사서 고순도 황산니켈을 만든다.

분류 좌표: 실제 회사는 법인 구조에 따라 갈린다.

| | KSIC | 판정 |
|---|---|---|
| 켐코 · 에코프로비엠 (별도 법인) | `C2820` | 부품제조 × 전자·정밀 × 전지·전원부품 |
| **LS MnM 배터리소재 사업부** (법인 안의 사업) | `C2421` | 모법인을 따라 제련으로 잡힌다 |

★ **같은 사업인데 법인 구조에 따라 분류가 달라진다.** 그래서 사업 정의는 분류
  좌표가 아니라 **사업 자체**를 단위로 둔다 — 그것이 이 패키지의 이유다.

## 이 사업의 얼개

    니켈 MHP + 황산 + 소석회 → 조황산니켈 용액 → 고순도 황산니켈(FG-NISO4)
                                              배터리급 수산화리튬(FG-LIOH)

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

    legal_entity = ("org-afs-advanced", "AFS_ADVANCED", "AFS 첨단소재 주식회사")
    shared = ("org-afs-advanced-shared", "ADV_SHARED", "AFS 첨단소재 전사공통")
    division = ("org-afs-battery-bu", "BATTERY_BU", "배터리소재사업부")
    plant = (_PLANT, "BATTERY_P2", "제2공장(황산니켈)")

    materials = (
        ("RM-MHP", "니켈 MHP", "RAW", "TON", "NICKEL"),
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
        "FG-LIOH": (("RM-H2SO4", 0.12, "INPUT"), ("RM-LIME", 0.05, "INPUT")),
    }
    yields = {"FG-NISO4": 0.94, "FG-LIOH": 0.94}
    byproducts = {}

    #: 습식 — 녹이고 걸러 결정으로 뽑는다. 1.1.0 까지 제련도 이 목록을 썼다.
    routing_ops = ("원료준비", "침출·용해", "정제", "결정화", "건조·포장")

    # ── 산업의 의미

    #: 전지소재의 등급은 **배터리급이냐 아니냐** 하나로 갈린다. 양극재사 규격을
    #: 통과하지 못하면 도금용·촉매용으로 훨씬 싸게 나간다.
    #: ⚠️ MHP 의 Ni 함량은 공개 지식으로 쓴 초안이다 — **도메인 검토 대상**
    grades = {
        "RM-MHP": "NI_40PCT",            # 니켈 MHP — Ni 35~40% 가 통상
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
