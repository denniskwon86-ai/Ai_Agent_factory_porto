"""Starter Package 안의 업무기능별 Business Kit 정본 분류.

Starter Package는 샘플 회사 하나를 통째로 체험하는 묶음이고, Business Kit는 그 안에서
구매·물류·재고처럼 사용자가 이해하고 선택하는 업무 기능이다. 데이터 계약 35개를 평면으로
보여 주면 제품에는 패키지 하나만 있고 업무키트는 없는 것처럼 보이므로, 분류를 서버 한 곳에
고정한다. 계약 키 자체는 바꾸지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, List


BUSINESS_KITS: List[Dict[str, Any]] = [
    {"business_kit_id": "FOUNDATION", "business_kit_name": "회사·조직·기준정보 기반팩",
     "description": "회사·조직과 공통 기준정보", "prefixes": ("FND", "MDM"), "order": 0},
    {"business_kit_id": "BK-01", "business_kit_name": "구매·원료 도입관리",
     "description": "계약·발주·납기와 구매 조건", "prefixes": ("PRC",), "order": 1},
    {"business_kit_id": "BK-02", "business_kit_name": "국제물류·도착관리",
     "description": "선적·통관·내륙 운송 이정표", "prefixes": ("LOG",), "order": 2},
    {"business_kit_id": "BK-03", "business_kit_name": "재고·수급관리",
     "description": "재고 판·이동·Lot", "prefixes": ("INV",), "order": 3},
    {"business_kit_id": "BK-04", "business_kit_name": "생산계획·자재영향",
     "description": "생산계획·소요량·설비 영향", "prefixes": ("MFG",), "order": 4},
    {"business_kit_id": "BK-05", "business_kit_name": "품질·Lot 추적",
     "description": "품질 결과와 근거 문서", "prefixes": ("QLT", "KNW"), "order": 5},
    {"business_kit_id": "BK-06", "business_kit_name": "판매·수요·매출시점",
     "description": "판매계획·수주·출하", "prefixes": ("SLS",), "order": 6},
    {"business_kit_id": "BK-07", "business_kit_name": "원가·현금·경영전망",
     "description": "원가·채권채무·손익·현금", "prefixes": ("FIN",), "order": 7},
    {"business_kit_id": "BK-08", "business_kit_name": "공급위험·시나리오·의사결정",
     "description": "외부지표·가정·대안·결정", "prefixes": ("EXT", "SIM", "DEC"), "order": 8},
]


def classify_dataset(dataset_contract_key: str) -> Dict[str, Any]:
    """계약 키의 주 업무기능을 돌려준다. 모르는 접두사는 숨기지 않고 미분류로 드러낸다."""
    key = str(dataset_contract_key or "").strip().upper()
    prefix = key.split("-", 1)[0]
    for row in BUSINESS_KITS:
        if prefix in row["prefixes"]:
            return {k: v for k, v in row.items() if k != "prefixes"}
    return {
        "business_kit_id": "UNCLASSIFIED",
        "business_kit_name": "미분류 — 정본 보완 필요",
        "description": "새 데이터 계약의 업무기능 분류가 필요합니다.",
        "order": 999,
    }


def represented_business_kits(dataset_contract_keys: List[str]) -> List[Dict[str, Any]]:
    """데이터 계약 집합에 실제로 나타나는 Business Kit(공통 기반팩 제외)."""
    found = {classify_dataset(key)["business_kit_id"] for key in dataset_contract_keys}
    return [
        {k: v for k, v in row.items() if k != "prefixes"}
        for row in BUSINESS_KITS
        if row["business_kit_id"] != "FOUNDATION" and row["business_kit_id"] in found
    ]
