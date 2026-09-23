#!/usr/bin/env python3
"""AFS 데모소재그룹 Starter Kit 생성기.

제품 정본:
  docs/data-kits/SAMPLE_COMPANY_STARTER_KIT_MASTER_SPEC_2026-08-11.md
  docs/data-kits/SAMPLE_COMPANY_DATA_REGISTRATION_EXECUTION_PLAN_2026-08-11.md

이 생성기는 실제 회사 데이터를 만들지 않는다. 모든 출력은 SYNTHETIC이며
경영 의사결정·예측 정확도 증명에 사용할 수 없다. 동일 profile/seed는 동일한
업무 데이터 행을 생성한다(생성 시각 메타데이터 제외).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.data_preparation import kit_freeze  # noqa: E402
import kit_defs  # noqa: E402
import business_defs  # noqa: E402

KIT_ID = "KIT-MFG-NONFERROUS-PROCUREMENT"
#: ★ **키트는 회사가 아니라 사업의 조합이다.** 예전에는 제련과 전지소재가 생성기
#:   안에 한 덩어리로 박혀 있어, 고려아연(제련만)·켐코(황산니켈만)에 줄 수 없었다.
#:   `--business` 로 갈아 끼운다 — `scripts/business_defs/` 참고.
DEFAULT_BUSINESSES = ("smelting_nonferrous", "battery_materials")
BUSINESS_CODES: Tuple[str, ...] = DEFAULT_BUSINESSES
#: 기본 조합(LS MnM 형 — 한 법인이 두 사업)의 정체성. **하위호환을 위해 그대로 둔다** —
#: 1.0.0~1.2.0 이 이 이름으로 봉인돼 있다.
DEFAULT_KIT = ("KIT-MFG-NONFERROUS-PROCUREMENT", "비철 제련·전지소재 통합 업무키트",
               "원료 구매·도입계획에서 경영 영향과 실행 결정까지")
DEFAULT_COMPANY = "AFS 데모소재그룹"
BUSINESSES: list = []
KIT_NAME: str = DEFAULT_KIT[1]
USE_CASE: str = DEFAULT_KIT[2]


#: 품목 → 그 품목이 속한 사업의 공장. **품목 마스터(`MDM-01`)가 정본이다.**
#:
#: ⚠️ 예전에는 어디서나 `business_defs.owner_of()` 를 불렀는데, 그것은 **사업 정의에
#:   적힌 품목만 안다.** 더미 품목(`MAT-*`)은 모르니 기본값(마지막 사업)으로 떨어졌고,
#:   마침 1.1.0 에서는 더미 완제품이 전부 마지막 사업에 몰려 있어 **우연히 맞았다.**
#:   배정을 고르게 고치자 판매 1,089 행이 마스터와 어긋났다.
_MATERIAL_SCOPE: Dict[str, str] = {}


def scope_of(material_id: str) -> str:
    """그 품목의 사업 범위. 마스터에 있으면 그것, 없으면 사업 정의로."""
    return _MATERIAL_SCOPE.get(material_id) or business_defs.owner_of(BUSINESSES, material_id)


def use_businesses(codes, kit_id: str = "", kit_name: str = "") -> None:
    """이 키트가 담을 사업과 **그 키트의 이름**을 정한다.

    순서가 지문을 좌우하므로 사업 순서는 바꾸지 않는다.

    ⚠️ 이름을 사업에서 받지 않으면, 전지소재만 뽑아도 manifest 가
      `KIT-MFG-NONFERROUS-PROCUREMENT` 로 나온다 — **데이터는 전지소재인데 이름표가
      제련**이고, 그대로 주면 켐코에 「비철 조달 키트」를 주는 셈이다.
    """
    global BUSINESSES, BUSINESS_CODES, KIT_ID, KIT_NAME, USE_CASE
    BUSINESSES = business_defs.load(list(codes))
    #: ★ 어느 사업에서 나왔는지를 **manifest 에 남긴다**(1.4.0). 선반이 「재현할 수
    #:   있나」를 묻고 검증기가 「무엇이 주력인가」를 물을 때 이것이 답이다. 없으면
    #:   둘 다 이름으로 추측해야 한다.
    BUSINESS_CODES = tuple(codes)
    #: 기본 조합은 **기존 이름을 그대로 쓴다** — 1.0.0~1.2.0 이 그 이름으로 봉인돼 있다
    if not kit_id and tuple(codes) == DEFAULT_BUSINESSES:
        kit_id, kit_name = DEFAULT_KIT[0], DEFAULT_KIT[1]
        KIT_ID, KIT_NAME, USE_CASE = DEFAULT_KIT
        return
    KIT_ID, KIT_NAME, USE_CASE = business_defs.kit_identity(BUSINESSES, kit_id, kit_name)


def company_name() -> str:
    """샘플 회사 이름. **사업이 하나면 그 법인**, 여럿이면 그룹.

    ⚠️ 이 값이 지금 **카탈로그의 키트 이름**으로 쓰인다
      (`kit_registry.py:126` · `demo_vertical_slice.py:431`). 제련만 담은 키트에
      「AFS 데모소재그룹」이 뜨면 고르는 사람이 무엇인지 알 수 없다.
    """
    return BUSINESSES[0].legal_entity[2] if len(BUSINESSES) == 1 else DEFAULT_COMPANY
#: **판본은 `--version` 으로 받는다** (P2). 예전에는 여기에 "1.0.0" 이 박혀 있어서,
#: 1.1.0 을 내려면 이 줄을 고쳐야 했고 고치는 순간 1.0.0 을 재현할 수 없게 됐다.
#: `main()`/`build()` 이 아래 셋을 판본에 맞게 다시 세운다.
KIT_VERSION = "1.7.0"
KIT_ROOT = ROOT / "starter_kits" / KIT_ID / KIT_VERSION
OVERLAY: kit_defs.KitOverlay = kit_defs.KitOverlay()


#: `--out` 으로 경로를 직접 준 경우. **이때는 `KIT_ID` 가 바뀌어도 경로를 다시 잡지
#: 않는다** — 부른 쪽이 정한 자리를 존중한다.
_OUT_OVERRIDE: Path | None = None


def use_version(version: str, out: Path | None = None) -> None:
    """판본을 갈아 끼운다 — 정의(오버레이)와 출력 경로를 함께 바꾼다.

    ⚠️ `KIT_ROOT` 는 **`KIT_ID` 로 조립된다.** 사업이 키트 이름을 정하므로
      `use_businesses()` 뒤에 다시 불러야 한다(`build()` 가 그렇게 한다).
    """
    global KIT_VERSION, KIT_ROOT, OVERLAY, _OUT_OVERRIDE
    OVERLAY = kit_defs.load(version)
    KIT_VERSION = version
    if out is not None:
        _OUT_OVERRIDE = Path(out)
    KIT_ROOT = _OUT_OVERRIDE or (ROOT / "starter_kits" / KIT_ID / version)
TENANT_ID = "tenant-afs-demo-materials"
GROUP_SCOPE = "org-afs-demo-group"
METALS_SCOPE = "org-afs-metals"
ADV_SCOPE = "org-afs-advanced"
PLANT1 = "plant-afs-smelting-01"
PLANT2 = "plant-afs-battery-02"
PLANT3 = "plant-afs-expansion-03"
AS_OF = "2026-08-11"


COMMON_FIELDS = [
    "record_id", "tenant_id", "scope_node_id", "data_class",
    "business_data_kind", "data_origin", "quality_status",
    "certification_status", "as_of_date", "lineage_id",
]

REQUIRED_DATASET_FIELDS = {
    "MDM-07": {"cost_center_name"},
}


DATASETS: Dict[str, Dict[str, Any]] = {
    "FND-01": {"name": "기업·조직 계층", "keys": ["node_id"], "deps": []},
    "FND-02": {"name": "사용자·역할·권한", "keys": ["user_id", "role_id", "scope_node_id"], "deps": ["FND-01"]},
    "FND-03": {"name": "달력·통화·단위·환산", "keys": ["reference_type", "reference_key", "effective_date"], "deps": []},
    "MDM-01": {"name": "품목·제품·원료", "keys": ["material_id"], "deps": ["FND-01", "FND-03"]},
    "MDM-02": {"name": "공급사·파트너", "keys": ["supplier_id"], "deps": ["FND-01", "FND-03", "MDM-01"]},
    "MDM-03": {"name": "고객·시장", "keys": ["customer_id"], "deps": ["FND-01", "FND-03", "MDM-01"]},
    "MDM-04": {"name": "공장·창고·저장 위치", "keys": ["location_id"], "deps": ["FND-01"]},
    "MDM-05": {"name": "BOM·수율·부산물", "keys": ["bom_id", "line_no"], "deps": ["MDM-01"]},
    "MDM-06": {"name": "Routing·설비·생산능력", "keys": ["routing_id", "operation_seq"], "deps": ["FND-01", "MDM-01"]},
    "MDM-07": {"name": "계정·원가요소·원가센터", "keys": ["account_id", "cost_center_id"], "deps": ["FND-01", "FND-03"]},
    "MDM-08": {"name": "계약조건·Incoterms·항만·운송구간", "keys": ["reference_id"], "deps": ["FND-03"]},
    "PRC-01": {"name": "구매계약·가격조건", "keys": ["contract_id"], "deps": ["MDM-01", "MDM-02", "MDM-08", "EXT-02"]},
    "PRC-02": {"name": "구매주문·납기 일정", "keys": ["po_line_id"], "deps": ["PRC-01"]},
    "LOG-01": {"name": "파트너 제출 상태", "keys": ["submission_id"], "deps": ["PRC-02", "MDM-02"]},
    "LOG-02": {"name": "선적 헤더·운송편", "keys": ["shipment_id"], "deps": ["PRC-02", "MDM-08"]},
    "LOG-03": {"name": "선적 Milestone", "keys": ["milestone_id"], "deps": ["LOG-02"]},
    "LOG-04": {"name": "통관·검사·관세", "keys": ["clearance_id"], "deps": ["LOG-02"]},
    "LOG-05": {"name": "내륙 운송 Milestone", "keys": ["transport_event_id"], "deps": ["LOG-02", "MDM-04"]},
    "INV-01": {"name": "재고 스냅샷", "keys": ["snapshot_id"], "deps": ["INV-02", "MDM-01", "MDM-04"]},
    "INV-02": {"name": "재고 이동·Lot", "keys": ["movement_id"], "deps": ["LOG-05", "MFG-02", "SLS-01"]},
    "MFG-01": {"name": "생산계획·소요량", "keys": ["plan_line_id"], "deps": ["MDM-05", "MDM-06", "SLS-01"]},
    "MFG-02": {"name": "생산실적·수율", "keys": ["batch_id"], "deps": ["MFG-01", "MFG-03", "MDM-05"]},
    "MFG-03": {"name": "가동·고장·정비", "keys": ["equipment_event_id"], "deps": ["MDM-06"]},
    "QLT-01": {"name": "입고·공정·제품 품질", "keys": ["inspection_id"], "deps": ["LOG-05", "MFG-02", "MDM-01"]},
    "SLS-01": {"name": "판매계획·수주·출하", "keys": ["sales_line_id"], "deps": ["MDM-01", "MDM-03"]},
    "FIN-01": {"name": "표준원가·실제원가", "keys": ["cost_record_id"], "deps": ["PRC-01", "MFG-02", "LOG-02"]},
    "FIN-02": {"name": "매입·미지급·매출채권", "keys": ["finance_document_id"], "deps": ["PRC-02", "SLS-01"]},
    "FIN-03": {"name": "예산·회계실적·현금흐름", "keys": ["ledger_line_id"], "deps": ["FIN-01", "FIN-02", "MDM-07"]},
    "EXT-01": {"name": "환율·금리·물가", "keys": ["observation_id"], "deps": []},
    "EXT-02": {"name": "원자재·제품 기준가격", "keys": ["observation_id"], "deps": []},
    "EXT-03": {"name": "운임·에너지·기상·산업지표", "keys": ["observation_id"], "deps": []},
    "KNW-01": {"name": "표준서·계약·규정·연구자료", "keys": ["document_id"], "deps": ["FND-01"]},
    "SIM-01": {"name": "Driver·계산식·제약", "keys": ["driver_id"], "deps": ["EXT-01", "EXT-02", "EXT-03", "FIN-03"]},
    "SIM-02": {"name": "기준·위험·대안 시나리오", "keys": ["scenario_id"], "deps": ["SIM-01"]},
    "DEC-01": {"name": "결정·실행과제·효과", "keys": ["decision_id"], "deps": ["SIM-02", "FND-02"]},
}


@dataclass(frozen=True)
class Profile:
    name: str
    months: int
    materials: int
    suppliers: int
    customers: int
    equipments: int
    contracts: int
    purchase_orders: int
    shipments: int
    production_plans: int
    production_batches: int
    sales_lines: int
    gl_documents: int
    users: int
    seed: int


PROFILES = {
    "quick": Profile("quick", 6, 30, 10, 8, 12, 20, 200, 120, 500, 650, 300, 900, 8, 20260811),
    "full": Profile("full", 36, 220, 40, 24, 48, 100, 1800, 1200, 6000, 8000, 2500, 7500, 24, 20260811),
}


def iso(d: date | datetime) -> str:
    if isinstance(d, datetime):
        return d.astimezone(timezone.utc).isoformat(timespec="seconds")
    return d.isoformat()


def add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def month_end(d: date) -> date:
    return add_months(date(d.year, d.month, 1), 1) - timedelta(days=1)


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def stamp(dataset_id: str, rows: Iterable[Dict[str, Any]], *, kind: str,
          default_scope: str = ADV_SCOPE) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, 1):
        r = dict(row)
        scope = r.pop("_scope", default_scope)
        rid = r.get("record_id") or stable_id(dataset_id.lower(), idx, *(list(r.values())[:3]))
        meta = {
            "record_id": rid,
            "tenant_id": TENANT_ID,
            "scope_node_id": scope,
            "data_class": "SYNTHETIC",
            "business_data_kind": kind,
            "data_origin": "SYNTHETIC",
            "quality_status": r.pop("_quality", "PASS"),
            "certification_status": "CERTIFIED_FOR_DEMO",
            "as_of_date": AS_OF,
            "lineage_id": stable_id("lin", dataset_id, rid),
        }
        meta.update(r)
        out.append(meta)
    return out


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers: List[str] = []
    seen = set()
    for key in COMMON_FIELDS:
        if any(key in r for r in rows):
            headers.append(key)
            seen.add(key)
    for row in rows:
        for key in row:
            if key not in seen:
                headers.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v
                     for k, v in row.items()}
            writer.writerow(clean)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")


def infer_type(values: Sequence[Any]) -> str:
    populated = [v for v in values if v not in (None, "")]
    if not populated:
        return "string"
    if all(isinstance(v, bool) for v in populated):
        return "boolean"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in populated):
        return "integer"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in populated):
        return "number"
    return "string"


def generate_org(profile: Profile) -> List[Dict[str, Any]]:
    #: ★ 법인·전사공통·사업부·공장은 **사업이 정한다**. 그룹과 부서만 여기 남는다.
    #: ⚠️ 부서가 **마지막 사업**에 붙는 것은 지금 데이터가 그렇기 때문이고(배터리
    #:   사업부 소속), 의미가 있어서가 아니다. 분리하면서 바꾸지 않았다.
    host = BUSINESSES[-1]
    nodes = [(GROUP_SCOPE, "ENTERPRISE_GROUP", "AFS_GROUP", "AFS 데모소재그룹", "", "VIRTUAL")]
    for b in BUSINESSES:
        eid, ecode, ename = b.legal_entity
        sid, scode, sname = b.shared
        did, dcode, dname = b.division
        pid, pcode, pname = b.plant
        nodes += [
            (eid, "LEGAL_ENTITY", ecode, ename, GROUP_SCOPE, "VIRTUAL"),
            (sid, "SHARED_SERVICE", scode, sname, eid, "VIRTUAL"),
            (did, "BUSINESS_DIVISION", dcode, dname, eid, "VIRTUAL"),
            (pid, "PLANT", pcode, pname, did, "VIRTUAL"),
        ]
    nodes += [
        #: 증설 제3공장은 **사업이 아니라 시나리오**다(회사 프로파일).
        (PLANT3, "PLANT", "EXPANSION_P3", "증설 제3공장", host.division_id, "VIRTUAL_EXPANSION"),
        ("dept-procurement", "DEPARTMENT", "PROC", "원료구매팀", host.division_id, "VIRTUAL"),
        ("dept-logistics", "DEPARTMENT", "LOG", "물류팀", host.division_id, "VIRTUAL"),
        ("dept-production", "DEPARTMENT", "MFG", "생산관리팀", host.division_id, "VIRTUAL"),
        ("dept-finance", "DEPARTMENT", "FIN", "재무회계팀", host.shared[0], "VIRTUAL"),
        ("dept-management", "DEPARTMENT", "MGT", "경영관리팀", host.shared[0], "VIRTUAL"),
    ]
    if profile.name == "quick":
        #: Quick 은 **마지막 사업 한 갈래**만 남긴다 — 그룹 → 법인 → 사업부 → 공장.
        keep = {GROUP_SCOPE, host.entity_id, host.division_id, host.plant_id,
                "dept-procurement", "dept-logistics", "dept-management"}
        nodes = [n for n in nodes if n[0] in keep]
        parent_map = {host.entity_id: GROUP_SCOPE, host.division_id: host.entity_id,
                      host.plant_id: host.division_id,
                      "dept-procurement": host.division_id, "dept-logistics": host.division_id,
                      "dept-management": host.entity_id}
        nodes = [(a, b, c, d, parent_map.get(a, e), f) for a, b, c, d, e, f in nodes]
    rows = [{"node_id": n[0], "node_type": n[1], "code": n[2], "name": n[3],
             "parent_id": n[4], "entity_mode": n[5], "industry_code": "C24",
             "effective_from": "2024-01-01", "effective_to": "9999-12-31",
             "_scope": n[0] if n[1] in {"LEGAL_ENTITY", "BUSINESS_DIVISION", "PLANT"} else GROUP_SCOPE}
            for n in nodes]
    return stamp("FND-01", rows, kind="REFERENCE", default_scope=GROUP_SCOPE)


def generate_users(profile: Profile) -> List[Dict[str, Any]]:
    personas = [
        ("admin", "플랫폼 관리자", "PLATFORM_ADMIN", GROUP_SCOPE, "platform.admin"),
        ("buyer", "원료 구매 담당", "PROCUREMENT_USER", "dept-procurement", "procurement.read,procurement.write"),
        ("buyer_mgr", "구매 책임자", "PROCUREMENT_MANAGER", "dept-procurement", "procurement.approve,decision.request"),
        ("logistics", "물류 담당", "LOGISTICS_USER", "dept-logistics", "logistics.read,logistics.write"),
        ("planner", "생산관리 담당", "PRODUCTION_PLANNER", "dept-production", "production.read,production.plan"),
        ("finance", "재무 담당", "FINANCE_USER", "dept-finance", "finance.read,finance.plan"),
        ("controller", "경영관리 담당", "CONTROLLER", "dept-management", "twin.run,report.create"),
        ("executive", "경영진", "EXECUTIVE", ADV_SCOPE, "decision.approve,report.publish"),
        ("auditor", "감사 담당", "AUDITOR", GROUP_SCOPE, "audit.read"),
    ]
    rows = []
    for i in range(profile.users):
        p = personas[i % len(personas)]
        rows.append({
            "user_id": f"demo_{p[0]}_{i+1:02d}@afs.example",
            "display_name": f"{p[1]} {i+1:02d} (예시)",
            "department_id": p[3] if p[3].startswith("dept-") else "dept-management",
            "role_id": p[2], "scope_node_id_grant": p[3], "capabilities": p[4],
            "effect": "ALLOW", "effective_from": "2024-01-01", "effective_to": "9999-12-31",
            "is_example": True, "_scope": p[3] if p[3].startswith("org-") else ADV_SCOPE,
        })
    return stamp("FND-02", rows, kind="REFERENCE", default_scope=GROUP_SCOPE)


def generate_references(profile: Profile, start: date, end: date) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    d = start
    while d <= end:
        rows.append({"reference_type": "FISCAL_CALENDAR", "reference_key": iso(d),
                     "effective_date": iso(d), "value": d.month, "unit": "MONTH",
                     "fiscal_year": d.year, "fiscal_period": d.month, "is_workday": d.weekday() < 5})
        d += timedelta(days=1)
    for code, value, unit in [("USD_KRW", 1350.0, "KRW/USD"), ("EUR_KRW", 1470.0, "KRW/EUR"),
                              ("TON_KG", 1000.0, "KG/TON"), ("KG_G", 1000.0, "G/KG"),
                              ("M3_L", 1000.0, "L/M3")]:
        rows.append({"reference_type": "CONVERSION", "reference_key": code,
                     "effective_date": iso(start), "value": value, "unit": unit,
                     "fiscal_year": "", "fiscal_period": "", "is_workday": ""})
    return stamp("FND-03", rows, kind="REFERENCE", default_scope=GROUP_SCOPE)


def generate_materials(profile: Profile) -> List[Dict[str, Any]]:
    #: ★ 품목은 **사업이 정한다**(`business_defs/`). 예전에는 제련과 전지소재가
    #:   여기 한 목록으로 박혀 있어 따로 뽑을 수가 없었다.
    #:   ⚠️ 원래 순서는 `RM-*` → `WIP-*` → `FG-*` → `BP-*` 로 **유형별**이었다.
    #:   사업별로 모으면 순서가 달라지므로, 지문을 지키려고 유형 순으로 다시 세운다.
    _order = {"RAW": 0, "WIP": 1, "FINISHED": 2, "BYPRODUCT": 3}
    fixed = sorted(business_defs.materials_of(BUSINESSES),
                   key=lambda m: _order.get(m["type"], 9))
    rows = []
    for m in fixed:
        code, name, typ = m["code"], m["name"], m["type"]
        rows.append({"material_id": code, "material_code": code, "material_name": name,
                     "aliases": f"{name}|{code.replace('-', ' ')}", "material_type": typ,
                     #: ★ 등급은 **사업이 준다** — 1.1.0 까지 실제 품목 12 개가 전부
                     #:   `DEMO_STANDARD` 였고, 정작 더미 품목에만 `G1~G4` 가 있었다.
                     "grade": business_defs.grade_of(BUSINESSES, code),
                     "base_uom": m["uom"], "valuation_class": typ,
                     "benchmark_code": m["benchmark"], "active": True, "_scope": m["scope"]})
    categories = ["원료첨가제", "공정소모품", "포장재", "예비품", "중간재", "완제품"]
    #: ★ 유형 **안에서** 번갈아 붙인다. 예전에는 `i % len(BUSINESSES)` 였는데,
    #:   유형도 `i % 6` 으로 정해져 **둘이 맞물렸다** — `WIP` 는 언제나 짝수 i,
    #:   `FINISHED` 는 언제나 홀수 i 라서 **더미 완제품이 전부 한 사업에** 갔다.
    #:   그 결과 판매 2,500 건 중 제련이 193 건(7.7%)뿐이었다.
    per_type: Dict[str, int] = defaultdict(int)
    while len(rows) < profile.materials:
        i = len(rows) + 1
        cat = categories[i % len(categories)]
        typ = "RAW" if i % 6 < 2 else "CONSUMABLE" if i % 6 < 4 else "WIP" if i % 6 == 4 else "FINISHED"
        scope = BUSINESSES[per_type[typ] % len(BUSINESSES)].plant_id
        per_type[typ] += 1
        code = f"MAT-{typ[:2]}-{i:04d}"
        rows.append({"material_id": code, "material_code": code, "material_name": f"{cat} {i:03d}",
                     "aliases": f"{cat}{i:03d}|DEMO-{i:03d}", "material_type": typ,
                     "grade": f"G{1+i%4}", "base_uom": "TON" if typ != "CONSUMABLE" else "EA",
                     "valuation_class": typ, "benchmark_code": "", "active": i % 23 != 0,
                     "_scope": scope})
    out = rows[:profile.materials]
    _MATERIAL_SCOPE.clear()
    _MATERIAL_SCOPE.update({r["material_id"]: r["_scope"] for r in out})
    return stamp("MDM-01", out, kind="REFERENCE")


def generate_suppliers(profile: Profile, materials: Sequence[Mapping[str, Any]], rng: random.Random) -> List[Dict[str, Any]]:
    raw_ids = [m["material_id"] for m in materials if m["material_type"] in {"RAW", "CONSUMABLE"}]
    countries = ["KR", "ID", "AU", "CL", "PE", "CN", "JP", "CA"]
    rows = []
    for i in range(profile.suppliers):
        mats = rng.sample(raw_ids, min(len(raw_ids), 1 + i % 3))
        rows.append({"supplier_id": f"SUP-{i+1:04d}", "supplier_name": f"글로벌 원료공급사 {i+1:02d} (가상)",
                     "country_code": countries[i % len(countries)], "currency": "USD" if i % 4 else "KRW",
                     "lead_time_days": 18 + (i * 7) % 73, "payment_terms": ["NET30", "NET45", "NET60"][i % 3],
                     "risk_grade": ["LOW", "MEDIUM", "HIGH"][i % 3], "material_ids": mats,
                     "active": True, "_scope": ADV_SCOPE if i % 2 else METALS_SCOPE})
    return stamp("MDM-02", rows, kind="REFERENCE")


def generate_customers(profile: Profile, products: Sequence[str]) -> List[Dict[str, Any]]:
    markets = ["KOREA", "CHINA", "EU", "NORTH_AMERICA", "JAPAN"]
    rows = []
    for i in range(profile.customers):
        rows.append({"customer_id": f"CUS-{i+1:04d}", "customer_name": f"배터리·금속 고객사 {i+1:02d} (가상)",
                     "market": markets[i % len(markets)], "country_code": ["KR", "CN", "DE", "US", "JP"][i % 5],
                     "currency": "KRW" if i % 4 == 0 else "USD", "credit_terms": ["NET30", "NET45", "NET60"][i % 3],
                     "product_ids": products[i % len(products):] + products[:i % len(products)],
                     "active": True, "_scope": ADV_SCOPE if i % 2 else METALS_SCOPE})
    return stamp("MDM-03", rows, kind="REFERENCE")


def generate_locations(profile: Profile) -> List[Dict[str, Any]]:
    #: 창고는 사업이 정한다. Quick 프로필은 각 사업의 입고·출고 목적지만 남긴다 —
    #: 그러지 않으면 구매·물류 데이터가 **존재하지 않는 창고**를 참조한다.
    quick = profile.name == "quick"
    all_rows = [(d["location_id"], d["site_id"], d["name"], d["storage_type"], d["capacity"])
                for d in business_defs.locations_of(BUSINESSES, quick)]
    #: ⚠️ 증설 제3공장 창고는 **사업이 아니라 시나리오**다(회사 프로파일
    #:   `AFS-VIRTUAL-BATTERY-EXPANSION-2030`). 그래서 사업 정의에 두지 않는다.
    if not quick:
        all_rows.append(("LOC-P3-SIM", PLANT3, "가상 증설창고", "VIRTUAL", 35000))
    rows = [{"location_id": a, "site_id": b, "location_name": c, "storage_type": d,
             "capacity_quantity": e, "capacity_uom": "TON", "active": d != "VIRTUAL", "_scope": b}
            for a, b, c, d, e in all_rows]
    return stamp("MDM-04", rows, kind="REFERENCE")


def generate_bom(profile: Profile, materials: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    recipes = business_defs.recipes_of(BUSINESSES)
    product_ids = [m["material_id"] for m in materials if m["material_type"] == "FINISHED"]
    raw_ids = [m["material_id"] for m in materials if m["material_type"] in {"RAW", "CONSUMABLE"}]
    rows = []
    target = 8 if profile.name == "quick" else 30
    # target은 상한이다. 품목 수를 넘겨 순회하면 같은 기간·같은 배합의
    # -02 BOM이 생겨 제품 Resolver가 대체판 충돌로 거부한다.
    for pidx in range(min(target, len(product_ids))):
        product = product_ids[pidx % len(product_ids)]
        #: ★ 더미 제품의 원료도 **그 사업 것**에서 고른다. 예전에는 전체 원료를
        #:   순환해서 **제련 제품이 소석회(전지소재 원료)로 만들어졌고**, 그 배치가
        #:   남의 창고에서 출고돼 재고가 어긋났다(3,733 행).
        _mine = [r for r in raw_ids if scope_of(r) == scope_of(product)] or raw_ids
        lines = recipes.get(product) or [(_mine[pidx % len(_mine)], 1.05 + (pidx % 5) * 0.03, "INPUT")]
        for line_no, (inp, qty, role) in enumerate(lines, 1):
            rows.append({"bom_id": f"BOM-{product}-{pidx//max(1,len(product_ids))+1:02d}", "line_no": line_no,
                         "output_material_id": product, "input_material_id": inp, "component_role": role,
                         "quantity_per_output": qty,
                         "input_uom": business_defs.uom_of(BUSINESSES, inp),
                         "output_uom": business_defs.uom_of(BUSINESSES, product),
                         "standard_yield": business_defs.yield_of(BUSINESSES, product),
                         "byproduct_material_id": business_defs.byproduct_of(BUSINESSES, product),
                         "effective_from": "2024-01-01", "effective_to": "9999-12-31",
                         "_scope": scope_of(product)})
    return stamp("MDM-05", rows, kind="REFERENCE")


def generate_routing(profile: Profile, materials: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    products = ([m["material_id"] for m in materials if m["material_type"] == "FINISHED"]
                or [BUSINESSES[-1].plant_id])
    #: ★ **실제 제품부터 전체 공정을 채운다.** 예전에는 설비를 제품과 공정에 각각
    #:   나머지 연산으로 돌려서 **어떤 제품도 전체 공정을 갖지 못했다** — 전기동이
    #:   배소와 전로정련만 거치고 용련·정제·전해정련이 빠졌다. 제련 담당자가 열면
    #:   바로 보이는 자리다.
    plan: List[tuple[str, int, str]] = []
    seen = set()
    for product in [p for p in products if not p.startswith("MAT-")] + list(products):
        for seq, op in enumerate(business_defs.routing_ops_for(BUSINESSES, product), 1):
            if len(plan) >= profile.equipments:
                break
            if (product, op) in seen:
                continue
            seen.add((product, op))
            plan.append((product, seq * 10, op))
    rows = []
    for i, (product, op_seq, op_name) in enumerate(plan):
        scope = scope_of(product)
        rows.append({"routing_id": f"ROUTE-{product}", "operation_seq": op_seq,
                     "operation_name": op_name, "equipment_id": f"EQ-{scope[-2:]}-{i+1:03d}",
                     "equipment_name": f"{op_name} 설비 {i+1:02d}", "product_id": product,
                     "rate_per_hour": round(3.5 + (i % 8) * 0.7, 2), "rate_uom": "TON/H",
                     "setup_hours": round(0.5 + (i % 4) * 0.25, 2), "rated_oee": round(0.82 + (i % 8) * 0.015, 3),
                     "calendar_hours_month": 720, "_scope": scope})
    return stamp("MDM-06", rows, kind="REFERENCE")


def generate_accounts(profile: Profile) -> List[Dict[str, Any]]:
    base = [
        ("1000", "현금및현금성자산", "ASSET", "CASH"), ("1100", "매출채권", "ASSET", "AR"),
        ("1200", "재고자산", "ASSET", "INVENTORY"), ("2000", "매입채무", "LIABILITY", "AP"),
        ("4000", "제품매출", "REVENUE", "REVENUE"), ("5000", "재료비", "EXPENSE", "MATERIAL_COST"),
        ("5100", "가공비", "EXPENSE", "CONVERSION_COST"), ("5200", "물류비", "EXPENSE", "LOGISTICS_COST"),
        ("5300", "에너지비", "EXPENSE", "ENERGY_COST"), ("5400", "품질손실", "EXPENSE", "QUALITY_LOSS"),
    ]
    cost_centers = {
        "CC-PROC": "원료구매 원가센터",
        "CC-LOG": "물류 원가센터",
        "CC-MFG": "생산 원가센터",
        "CC-FIN": "재무 원가센터",
        "CC-MGT": "경영관리 원가센터",
    }
    rows = []
    target = 30 if profile.name == "quick" else 80
    for i in range(target):
        if i < len(base):
            acc, name, typ, elem = base[i]
        else:
            acc, name, typ, elem = f"6{i:03d}", f"관리계정 {i:03d}", "EXPENSE", f"OPEX_{i:03d}"
        cc = ["CC-PROC", "CC-LOG", "CC-MFG", "CC-FIN", "CC-MGT"][i % 5]
        rows.append({"account_id": acc, "account_name": name, "account_type": typ,
                     "cost_element": elem, "cost_center_id": cc,
                     "cost_center_name": cost_centers[cc],
                     "pnl_line": "REVENUE" if typ == "REVENUE" else "COGS" if elem.endswith("COST") else "OPEX" if typ == "EXPENSE" else "BALANCE_SHEET",
                     "cashflow_line": "OPERATING", "currency": "KRW", "active": True,
                     "_scope": ADV_SCOPE})
    return stamp("MDM-07", rows, kind="REFERENCE")


def generate_trade_refs(profile: Profile) -> List[Dict[str, Any]]:
    rows = []
    for code in ["FOB", "CIF", "CFR", "DAP"]:
        rows.append({"reference_id": f"INC-{code}", "reference_type": "INCOTERM", "code": code,
                     "name": code, "origin": "", "destination": "", "mode": "", "lead_time_days": 0,
                     "currency": ""})
    for code, days in [("NET30", 30), ("NET45", 45), ("NET60", 60)]:
        rows.append({"reference_id": f"PAY-{code}", "reference_type": "PAYMENT_TERM", "code": code,
                     "name": code, "origin": "", "destination": "", "mode": "", "lead_time_days": days,
                     "currency": ""})
    ports = ["BUSAN", "ULSAN", "JAKARTA", "PERTH", "VALPARAISO", "SHANGHAI"]
    for p in ports:
        rows.append({"reference_id": f"PORT-{p}", "reference_type": "PORT", "code": p,
                     "name": f"{p} Port", "origin": "", "destination": "", "mode": "SEA",
                     "lead_time_days": 0, "currency": "USD"})
    lane_count = 10 if profile.name == "quick" else 30
    for i in range(lane_count):
        rows.append({"reference_id": f"LANE-{i+1:03d}", "reference_type": "TRANSPORT_LANE", "code": f"LN{i+1:03d}",
                     "name": f"{ports[(i+2)%len(ports)]}→ULSAN", "origin": ports[(i+2)%len(ports)],
                     "destination": "ULSAN", "mode": "SEA", "lead_time_days": 12 + i % 35,
                     "currency": "USD"})
    return stamp("MDM-08", rows, kind="REFERENCE", default_scope=GROUP_SCOPE)


def generate_external(profile: Profile, start: date, rng: random.Random) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    months = max(profile.months, 60)
    ext1, ext2, ext3 = [], [], []
    fx, copper, nickel, freight, power = 1320.0, 9000.0, 17000.0, 82.0, 125.0
    for i in range(months):
        d = add_months(start, i - (months - profile.months))
        fx = max(950, fx * (1 + rng.gauss(0.001, 0.018)))
        copper = max(4500, copper * (1 + rng.gauss(0.002, 0.045)))
        nickel = max(8000, nickel * (1 + rng.gauss(0.001, 0.065)))
        freight = max(35, freight * (1 + rng.gauss(0.001, 0.07)))
        power = max(80, power * (1 + rng.gauss(0.002, 0.015)))
        for code, value, unit in [("USD_KRW", fx, "KRW/USD"), ("BASE_RATE_KR", 3.25 + math.sin(i/8)*0.35, "%"),
                                  ("PPI_MFG", 100 + i*0.12 + math.sin(i/6)*1.5, "INDEX")]:
            ext1.append({"observation_id": f"EXT1-{code}-{d:%Y%m}", "indicator_code": code,
                         "observed_at": iso(month_end(d)), "published_at": iso(month_end(d)+timedelta(days=10)),
                         "vintage_date": iso(month_end(d)+timedelta(days=10)), "value": round(value, 4), "unit": unit,
                         "source_id": "AFS_SYNTHETIC_REFERENCE", "trust_grade": "DEMO_ONLY"})
        for code, value, unit in [("COPPER", copper, "USD/TON"), ("NICKEL", nickel, "USD/TON"),
                                  ("SULFURIC_ACID", 115 + math.sin(i/5)*12, "USD/TON"),
                                  ("LITHIUM", 24000 + math.sin(i/9)*4500, "USD/TON")]:
            ext2.append({"observation_id": f"EXT2-{code}-{d:%Y%m}", "commodity_code": code,
                         "observed_at": iso(month_end(d)), "published_at": iso(month_end(d)+timedelta(days=7)),
                         "vintage_date": iso(month_end(d)+timedelta(days=7)), "value": round(value, 4), "unit": unit,
                         "currency": "USD", "source_id": "AFS_SYNTHETIC_REFERENCE", "trust_grade": "DEMO_ONLY"})
        for code, value, unit, target in [("SEA_FREIGHT", freight, "USD/TON", "LANE"),
                                          ("INDUSTRIAL_POWER", power, "KRW/KWH", BUSINESSES[-1].plant_id),
                                          ("MFG_DEMAND_INDEX", 100 + math.sin(i/4)*6, "INDEX", "INDUSTRY")]:
            ext3.append({"observation_id": f"EXT3-{code}-{d:%Y%m}", "indicator_code": code,
                         "target_ref": target, "observed_at": iso(month_end(d)),
                         "published_at": iso(month_end(d)+timedelta(days=12)), "value": round(value, 4), "unit": unit,
                         "source_id": "AFS_SYNTHETIC_REFERENCE", "trust_grade": "DEMO_ONLY"})
    return (stamp("EXT-01", ext1, kind="REFERENCE", default_scope=GROUP_SCOPE),
            stamp("EXT-02", ext2, kind="REFERENCE", default_scope=GROUP_SCOPE),
            stamp("EXT-03", ext3, kind="REFERENCE", default_scope=GROUP_SCOPE))


def latest_indicator(rows: Sequence[Mapping[str, Any]], code_field: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for r in rows:
        out[str(r[code_field])] = float(r["value"])
    return out


def generate_contracts(profile: Profile, suppliers: Sequence[Mapping[str, Any]], materials: Sequence[Mapping[str, Any]],
                       ext2: Sequence[Mapping[str, Any]], rng: random.Random,
                       need: Mapping[str, float] = MappingProxyType({})) -> List[Dict[str, Any]]:
    raw = [m for m in materials if m["material_type"] in {"RAW", "CONSUMABLE"} and m["active"]]
    #: ★ **사는 장면이 보여야 한다**(1.5.0). 위 `_PRC_CYCLE` 설명을 보라.
    _known_raw = {m["code"] for m in business_defs.materials_of(BUSINESSES)}
    _major_raw = [m for m in raw if m["material_id"] in _known_raw]
    _other_raw = [m for m in raw if m["material_id"] not in _known_raw]
    prices = latest_indicator(ext2, "commodity_code")
    rows = []
    for i in range(profile.contracts):
        supplier = suppliers[i % len(suppliers)]
        #: 주기 4 중 1 을 주력 원료에. 나머지는 부자재·소모품이 돈다
        if _major_raw and (i % _PRC_CYCLE) < _PRC_MAJOR:
            mat = _major_raw[(i // _PRC_CYCLE) % len(_major_raw)]
        else:
            mat = (_other_raw or raw)[i % len(_other_raw or raw)]
        benchmark = mat.get("benchmark_code") or "NICKEL"
        if benchmark not in prices:
            benchmark = "NICKEL"
        scope = mat["scope_node_id"]
        #: ★ 계약 수량이 발주 합계보다 작으면 **발주가 잘린다**(`remaining`). 주력
        #:   원료는 소비 전체를 덮을 만큼 잡는다 — 계약은 「살 수 있는 상한」이다
        _cq = round(max(10000 + (i % 10)*2500, need.get(mat["material_id"], 0.0) * 1.5), 3)
        rows.append({"contract_id": f"CTR-{i+1:05d}", "supplier_id": supplier["supplier_id"],
                     "material_id": mat["material_id"], "contract_quantity": _cq,
                     "ordered_quantity": 0.0, "quantity_uom": mat["base_uom"], "benchmark_code": benchmark,
                     "benchmark_price": round(prices[benchmark], 2), "premium_rate": round(-0.02 + (i%9)*0.008, 4),
                     "currency": supplier["currency"], "incoterm": ["CIF", "FOB", "CFR"][i%3],
                     "payment_terms": supplier["payment_terms"], "valid_from": "2024-01-01", "valid_to": "2027-12-31",
                     "price_formula": "BENCHMARK_PRICE*(1+PREMIUM_RATE)", "_scope": scope})
    return stamp("PRC-01", rows, kind="ACTUAL")


def generate_purchase_and_logistics(profile: Profile, contracts: List[Dict[str, Any]], suppliers: Sequence[Mapping[str, Any]],
                                    start: date, end: date, rng: random.Random,
                                    need: Mapping[str, float] = MappingProxyType({})) -> tuple[List[Dict[str, Any]], ...]:
    po_rows, submission_rows, shipment_rows, milestone_rows, customs_rows, transport_rows = [], [], [], [], [], []
    span = max(1, (end - start).days)
    #: ★★★ **소비에서 역산한다** (1.6.0). `material_need` 의 설명을 보라.
    #:
    #: ⚠️ 발주가 전부 입고되지는 않는다 — `shipments`(1,200) 만 배송되고 나머지는
    #:   `OPEN` 으로 남는다(발주 1,800 중 **3 분의 2**). 그만큼 더 주문해야 실제
    #:   입고가 소비를 댄다. 이것을 빼면 발주는 맞는데 **재고가 음수로 간다.**
    _deliver = min(1.0, profile.shipments / max(1, profile.purchase_orders))
    _po_per_contract = defaultdict(int)
    for _i in range(profile.purchase_orders):
        _po_per_contract[contracts[_i % len(contracts)]["contract_id"]] += 1
    #: 그 원료를 파는 계약이 몇 건이고 각 계약에 발주가 몇 건 붙는가 — 한 건이 얼마를
    #: 주문해야 하는지가 거기서 나온다
    _po_count: Dict[str, int] = defaultdict(int)
    for _c in contracts:
        _po_count[str(_c["material_id"])] += _po_per_contract[_c["contract_id"]]
    _target = {m: (q * _BUY_MARGIN / _deliver / _po_count[m]) for m, q in need.items()
               if _po_count.get(m)}
    shipment_po_indexes = set(rng.sample(range(profile.purchase_orders), min(profile.shipments, profile.purchase_orders)))
    contract_ordered: Dict[str, float] = defaultdict(float)
    supplier_by_id = {s["supplier_id"]: s for s in suppliers}
    for i in range(profile.purchase_orders):
        c = contracts[i % len(contracts)]
        order_date = start + timedelta(days=(i * 17 + i//7) % span)
        lead = int(supplier_by_id[c["supplier_id"]]["lead_time_days"])
        due_date = order_date + timedelta(days=lead)
        #: ★ 주력 원료는 **소비에서 역산한 양**을, 나머지는 예전대로. 변동은 주되
        #:   평균이 목표가 되게 한다(0.85 + 0~0.30 → 평균 1.0)
        _t = _target.get(str(c["material_id"]))
        quantity = round(_t * (0.85 + (i % 7) * 0.05) if _t else 15 + (i % 11) * 4.5, 3)
        remaining = float(c["contract_quantity"]) - contract_ordered[c["contract_id"]]
        if remaining < quantity:
            quantity = max(1.0, remaining)
        contract_ordered[c["contract_id"]] += quantity
        po_id = f"PO-{i+1:06d}"
        unit_price = round(float(c["benchmark_price"]) * (1 + float(c["premium_rate"])), 2)
        shipped = i in shipment_po_indexes
        po_rows.append({"po_id": po_id, "po_line_id": f"{po_id}-10", "contract_id": c["contract_id"],
                        "supplier_id": c["supplier_id"], "material_id": c["material_id"],
                        "order_date": iso(order_date), "due_date": iso(due_date), "order_quantity": quantity,
                        "quantity_uom": c["quantity_uom"], "unit_price": unit_price, "currency": c["currency"],
                        "status": "DELIVERED" if shipped else "OPEN", "_scope": c["scope_node_id"]})
        submission_rows.append({"submission_id": f"SUB-{i+1:06d}", "source_system_id": "DEMO_PARTNER_PORTAL",
                                "partner_id": c["supplier_id"], "business_ref": f"{po_id}-10",
                                "submission_status": "COMPLETE" if shipped else "PENDING",
                                "submitted_at": iso(datetime.combine(order_date+timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)) if shipped else "",
                                "revised_at": "", "source_version": 1, "_scope": c["scope_node_id"]})
        if not shipped:
            continue
        ship_no = len(shipment_rows) + 1
        shipment_id = f"SHP-{ship_no:06d}"
        etd = order_date + timedelta(days=max(3, lead//4))
        delay = 14 if ship_no % 37 == 0 else rng.randint(-2, 5)
        eta = due_date + timedelta(days=delay)
        # 실제 도착은 ETA보다 빠를 수 있지만, 이벤트 원장의 순서는
        # ETA(예정 시점) -> ATA(실제 시점)로 검증하므로 같은 날 이후로 고정한다.
        ata = eta + timedelta(days=rng.randint(0, 3))
        freight = round(quantity * (70 + (ship_no % 13)*3.5), 2)
        shipment_rows.append({"shipment_id": shipment_id, "po_line_id": f"{po_id}-10",
                              "vessel_or_mode": f"DEMO-VESSEL-{ship_no%17+1:02d}", "origin_port": ["JAKARTA", "PERTH", "VALPARAISO", "SHANGHAI"][ship_no%4],
                              "destination_port": "ULSAN", "lane_id": f"LANE-{ship_no%30+1:03d}",
                              "shipment_quantity": quantity, "quantity_uom": c["quantity_uom"],
                              "freight_amount": freight, "freight_currency": "USD", "etd": iso(etd), "eta": iso(eta),
                              "status": "DELIVERED", "_scope": c["scope_node_id"]})
        events = [("BOOKED", order_date+timedelta(days=1)), ("PICKED_UP", etd-timedelta(days=2)),
                  ("ETD", etd), ("ETA", eta), ("ATA", ata), ("UNLOADED", ata+timedelta(days=1))]
        for seq, (event, actual) in enumerate(events, 1):
            milestone_rows.append({"milestone_id": f"MS-{ship_no:06d}-{seq:02d}", "shipment_id": shipment_id,
                                   "event_type": event, "planned_at": iso(datetime.combine(actual-timedelta(days=max(0,delay)), datetime.min.time(), tzinfo=timezone.utc)),
                                   "actual_at": iso(datetime.combine(actual, datetime.min.time(), tzinfo=timezone.utc)),
                                   "location": "ORIGIN" if seq < 3 else "DESTINATION", "status": "COMPLETED",
                                   "source_version": 1, "_scope": c["scope_node_id"]})
        clearance_at = ata + timedelta(days=2 + (ship_no % 4))
        duty = round(float(c["benchmark_price"]) * quantity * (0.01 if ship_no % 5 == 0 else 0.0), 2)
        customs_rows.append({"clearance_id": f"CUSCLR-{ship_no:06d}", "shipment_id": shipment_id,
                             "declaration_date": iso(ata+timedelta(days=1)), "inspection_status": "INSPECTED" if ship_no%11==0 else "CLEARED",
                             "duty_amount": duty, "currency": c["currency"], "cleared_at": iso(clearance_at),
                             "status": "CLEARED", "source_version": 1, "_scope": c["scope_node_id"]})
        delivered = clearance_at + timedelta(days=1 + ship_no % 2)
        for seq, (event, actual) in enumerate([("DISPATCHED", clearance_at), ("DELIVERED", delivered)], 1):
            transport_rows.append({"transport_event_id": f"TR-{ship_no:06d}-{seq}", "transport_id": f"TR-{ship_no:06d}",
                                   "shipment_id": shipment_id, "event_type": event,
                                   "event_at": iso(datetime.combine(actual, datetime.min.time(), tzinfo=timezone.utc)),
                                   "destination_location_id": business_defs.by_plant(BUSINESSES, c["scope_node_id"]).raw_location,
                                   "delivered_quantity": quantity if event == "DELIVERED" else 0.0,
                                   "quantity_uom": c["quantity_uom"], "status": "COMPLETED", "_scope": c["scope_node_id"]})
    for c in contracts:
        c["ordered_quantity"] = round(contract_ordered[c["contract_id"]], 3)
    return (stamp("PRC-02", po_rows, kind="ACTUAL"), stamp("LOG-01", submission_rows, kind="ACTUAL"),
            stamp("LOG-02", shipment_rows, kind="ACTUAL"), stamp("LOG-03", milestone_rows, kind="ACTUAL"),
            stamp("LOG-04", customs_rows, kind="ACTUAL"), stamp("LOG-05", transport_rows, kind="ACTUAL"))


#: ★★★ **주력이 매출을 만든다** (1.4.0).
#:
#: 1.3.0 까지 판매가 품목을 **균등하게** 돌았다. 그런데 완제품은 사업이 정의한 것
#: 1~2 종이고 볼륨용 더미(`MAT-FI-*`)가 35 종이라, 매출의 **99% 를 「완제품 011」
#: 같은 이름 없는 품목**이 차지했다. 게다가 더미 기본 단가가 32,000 으로 **전기동
#: (9,500)보다 3.4 배 비쌌다.**
#:
#:     1.3.0   전기동 0.8% · 금 0.1% · 황산 0.0% · 더미 99%
#:
#: 「이 산업은 이렇게 일한다」를 보이려는 키트인데 **산업이 1% 뿐**이었다. 현업에게
#: 「매출 구성이 이렇습니다」라고 드린 숫자도 더미를 빼고 센 것이라 **데이터를 열면
#: 맞지 않았다.**
#:
#: ⚠️ **더미를 안 팔 수는 없다.** 생산(MFG)은 BOM 을 따라 계속 만들므로, 팔지 않으면
#:   재고가 끝없이 쌓인다. 그래서 **없애지 않고 비중을 낮춘다.**
#:
#: | | 값 | 왜 |
#: |---|---|---|
#: | 주력 반복 | **30** | 제조사는 주력 제품으로 번다. 부대 품목이 매출의 다수인 제조사는 없다 |
#: | 더미 단가 | **1,200** | 부대 품목이 주력보다 비쌀 이유가 없다 |
#:
#: 그 결과 주력이 매출의 **89%**(제련) · **95%**(전지소재)가 되고, 건수로는 더미도
#: 4 분의 1 이 남아 **볼륨은 그대로**다.
#:
#: ⚠️ 이 둘은 **산업 공통**이라 여기 둔다. 「주력이 몇 %인가」는 회사마다 다르지만
#:   「주력이 대부분이다」는 제조업이면 그렇다. 회사 실제 비중은 현업이 플랫폼 안에서
#:   채운다.
_MAJOR_REPEAT = 30
_FILLER_PRICE = 1200.0

#: 생산 쪽 가중. **주력은 자주, 작은 배치로** 만든다 — 총 배치 수가 고정이라
#: 가중만 올리면 주력 재고가 터무니없이 쌓이므로 배치 크기를 함께 줄인다.
#: `generate_plans_batches_events` 의 설명을 보라.
#: ⚠️ **판매 가중과 맞춰야 한다.** 완제품이 2 종이면 배치가 나뉘어 종당 생산이
#:   줄어드는데 판매는 종당 그대로라, 가중이 작으면 **만든 것보다 많이 파는** 쪽으로
#:   기운다 — 전지소재가 실제로 그랬다(생산 12,412 < 판매 17,187).
_MAJOR_REPEAT_MFG = 30
_MAJOR_BATCH_SCALE = 0.45

#: ⚠️ 0.45 는 **quick 프로파일이 정한 값**이다. quick 은 배치 650 · 판매 300 이라
#:   배치 대비 판매가 full(8,000 · 2,500)보다 크고, 배치를 너무 작게 잡으면 거기서만
#:   「만든 것보다 많이 판다」가 난다. 두 프로파일 모두 통과하는 자리를 골랐다.

#: ★★★ **구매 쪽 가중** (1.5.0).
#:
#: 1.4.0 까지 구매가 품목을 균등하게 돌았다. 구매 대상이 144 종(원료 72 · 소모품 72)
#: 인데 사업이 아는 원료는 1~5 종이라, **정광 구매가 발주의 1%** 였다. 그런데 이
#: 키트의 용도는 「원료 구매·도입계획에서 경영 영향과 실행 결정까지」다 —
#: **사는 장면이 데이터에 없으면 그 용도가 성립하지 않는다.**
#:
#: ⚠️ 더 나쁜 것은 수급이었다. 동정광을 **20,176 톤 쓰면서 612 톤만 샀다.**
#:   기초재고 23,202 톤이 받쳐 재고 음수는 나지 않았지만, 그것은 「사는 회사」가
#:   아니라 **「쌓아둔 것을 쓰는 회사」**다.
#: ⚠️ **반복 목록으로 하면 안 된다.** 계약은 100 건인데 가중한 목록이 그보다 길면
#:   앞부분만 잘려 **전부 주력**이 된다 — 전지소재(원료 4 종 × 25 = 100)가 실제로
#:   발주 100% 가 나왔다. 그래서 **주기**로 정한다: 개수와 무관하게 비율이 지켜진다.
_PRC_CYCLE, _PRC_MAJOR = 4, 1

#: 소비보다 얼마나 더 사는가. 딱 맞춰 사면 **시점이 조금만 어긋나도 음수**가 난다.
_BUY_MARGIN = 1.25

#: 기초재고를 **몇 달치**로 둘 것인가 (주력 원료만). 구매가 나머지를 댄다.
#: ⚠️ 첫 몇 달은 발주가 아직 도착하지 않는다 — 리드타임과 배송 지연이 있다.
#:   그 구간을 이 재고가 버텨야 한다.
_OPEN_STOCK_MONTHS = 5.0


def generate_sales(profile: Profile, customers: Sequence[Mapping[str, Any]], products: Sequence[str],
                   start: date, end: date, rng: random.Random) -> List[Dict[str, Any]]:
    span = max(1, (end-start).days)
    #: ★ 주력과 더미를 **품목 마스터가 아니라 사업 정의로** 가른다 — `MAT-` 접두사로
    #:   가르면 사업이 그런 이름을 쓰는 순간 조용히 어긋난다.
    _known = {m["code"] for m in business_defs.materials_of(BUSINESSES)}
    major = [p for p in products if p in _known]
    filler = [p for p in products if p not in _known]
    #: 주력이 없으면(가능성은 낮지만) 원래대로 돈다 — 나누기 0 을 만들지 않는다
    products = (major * _MAJOR_REPEAT + filler) if major else list(products)
    rows = []
    for i in range(profile.sales_lines):
        order_date = start + timedelta(days=(i*13 + i//9) % span)
        due = order_date + timedelta(days=20 + i%25)
        actual = due + timedelta(days=2 if i%31==0 else rng.randint(-2, 2))
        product = products[i % len(products)]
        #: 품목마다 거래 단위가 다르다 — 금을 전기동과 같은 수량으로 팔 수는 없다
        qty = round((8 + (i%17)*1.7) * business_defs.sale_qty_scale_of(BUSINESSES, product), 3)
        #: ★ 단가는 **사업이 준다**(1.4.0). 1.3.0 까지는 여기서 품목 이름으로 분기해
        #:   `FG-NISO4`·`FG-CATHODE` 만 알았고, **나머지 완제품은 더미 기본값으로
        #:   떨어졌다** — `FG-LIOH` 가 그랬다. 사업이 품목을 늘릴 때마다 생성기를
        #:   고쳐야 하는 구조였고, 고치지 않으면 조용히 틀렸다.
        _base = _FILLER_PRICE
        price = round(business_defs.sale_price_of(BUSINESSES, product, _base) * (0.95 + (i%9)*0.012), 2)
        customer = customers[i % len(customers)]
        rows.append({"sales_line_id": f"SO-{i+1:06d}-10", "customer_id": customer["customer_id"],
                     "product_id": product, "order_date": iso(order_date), "due_date": iso(due),
                     "actual_ship_date": iso(actual), "plan_quantity": qty, "order_quantity": qty,
                     #: ★ 단위도 품목이 정한다 — 1.1.0 까지 전부 `TON` 이라 금을 팔면
                     #:   톤으로 팔렸다.
                     "shipped_quantity": qty,
                     "quantity_uom": business_defs.uom_of(BUSINESSES, product),
                     "unit_price": price,
                     "currency": customer["currency"], "status": "SHIPPED",
                     "_scope": scope_of(product)})
    return stamp("SLS-01", rows, kind="ACTUAL")


def generate_plans_batches_events(profile: Profile, bom: Sequence[Mapping[str, Any]], routing: Sequence[Mapping[str, Any]],
                                  sales: Sequence[Mapping[str, Any]], start: date, end: date,
                                  rng: random.Random) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    products = sorted({str(b["output_material_id"]) for b in bom})
    #: ★★★ **만든 것보다 많이 팔 수는 없다** (1.4.0).
    #:
    #: 생산은 품목을 **균등하게** 돌았고 판매와 아무 관계가 없었다. 1.3.0 까지는
    #: 주력 판매가 워낙 적어(전기동 1,415 톤 vs 생산 6,972 톤) 드러나지 않았는데,
    #: 판매를 주력 중심으로 고치자 **전기동을 6,972 톤 만들면서 12,980 톤 파는**
    #: 데이터가 됐다.
    #:
    #: ⚠️ **재고 음수 검사가 이것을 못 잡았다.** 조정 이벤트(`MOV-ADJ`, 이동의 32%)가
    #:   재고를 채워 잔고가 양수로 남기 때문이다 — 「없는 것을 판다」가 조정에 가렸다.
    #:
    #: 그래서 생산도 주력 쪽으로 기울인다. 판매(30)보다 작게 주는 이유는 **총 배치 수가
    #: 고정**이라 너무 기울이면 주력 재고가 터무니없이 쌓이기 때문이다 — 생산이
    #: 판매의 1.5 배쯤 되는 자리를 골랐다.
    _known_mfg = {m["code"] for m in business_defs.materials_of(BUSINESSES)}
    _major_mfg = [p for p in products if p in _known_mfg]
    if _major_mfg:
        products = _major_mfg * _MAJOR_REPEAT_MFG + [p for p in products if p not in _known_mfg]
    bom_by_product: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for b in bom:
        bom_by_product[str(b["output_material_id"])].append(b)
    span = max(1, (end-start).days)
    plans = []
    for i in range(profile.production_plans):
        product = products[i % len(products)]
        d = start + timedelta(days=(i*5 + i//11) % span)
        #: ★ 주력은 **작은 배치로 자주** 만든다(1.5.0) — 가중만 올리면 총량이
        #:   판매를 크게 웃돌아 재고가 쌓인다
        qty = round((10 + (i%19)*2.1) * (_MAJOR_BATCH_SCALE if product in _known_mfg else 1.0), 3)
        requirement = round(sum(float(x["quantity_per_output"]) for x in bom_by_product[product]) * qty, 3)
        scope = scope_of(product)
        plans.append({"plan_line_id": f"MPS-{i+1:07d}", "plan_date": iso(d), "site_id": scope,
                      "product_id": product, "plan_quantity": qty, "quantity_uom": "TON",
                      "priority": 1 + i%3, "material_requirement": requirement,
                      "capacity_requirement_hours": round(qty/5.5, 3), "status": "RELEASED", "_scope": scope})
    events = []
    for i in range(max(80, profile.equipments*12)):
        eq = routing[i % len(routing)]
        d = start + timedelta(days=(i*23) % span)
        planned = i%4==0
        duration = 3 + i%17 if planned else 1 + i%11
        events.append({"equipment_event_id": f"EQEV-{i+1:06d}", "equipment_id": eq["equipment_id"],
                       "event_type": "PLANNED_MAINTENANCE" if planned else "BREAKDOWN",
                       "start_at": iso(datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)),
                       "end_at": iso(datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)+timedelta(hours=duration)),
                       "planned": planned, "root_cause": "DEMO_WEAR" if not planned else "PERIODIC_PM",
                       "capacity_loss_hours": duration, "_scope": eq["scope_node_id"]})
    batches = []
    for i in range(profile.production_batches):
        plan = plans[i % len(plans)]
        product = str(plan["product_id"])
        recipe = bom_by_product[product]
        batch_date = date.fromisoformat(str(plan["plan_date"])) + timedelta(days=i%4)
        out_qty = round(float(plan["plan_quantity"]) * (0.85 + (i%11)*0.012), 3)
        std_yield = float(recipe[0]["standard_yield"])
        actual_yield = max(0.78, min(0.995, std_yield + rng.gauss(0, 0.012)))
        input_qty = round(out_qty / actual_yield, 3)
        batches.append({"batch_id": f"BATCH-{i+1:07d}", "plan_line_id": plan["plan_line_id"],
                        "production_date": iso(batch_date), "site_id": plan["site_id"],
                        "input_material_id": recipe[0]["input_material_id"], "input_lot_id": f"LOT-RM-{i%5000+1:06d}",
                        "input_quantity": input_qty, "output_material_id": product, "output_lot_id": f"LOT-FG-{i+1:07d}",
                        "output_quantity": out_qty, "quantity_uom": "TON", "actual_yield": round(actual_yield, 5),
                        "scrap_quantity": round(max(0, input_qty-out_qty), 3), "downtime_hours": 0 if i%29 else 4,
                        "status": "CONFIRMED", "_scope": plan["site_id"]})
    return (stamp("MFG-01", plans, kind="PLAN"), stamp("MFG-02", batches, kind="ACTUAL"),
            stamp("MFG-03", events, kind="ACTUAL"))


def material_need(batches: Sequence[Mapping[str, Any]],
                  bom: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    """★★★ **생산이 원료를 얼마나 쓰는가** (1.6.0).

    1.5.0 까지 구매가 이것을 몰랐다. 발주량은 `purchase_qty_scale` 이라는 **손으로
    맞춘 상수**로 정했고, 사업·판본이 바뀔 때마다 다시 맞춰야 했다 — 실제로 1.5.0 을
    내면서 네 번 고쳤다. 그래도 **구매/소비가 0.66~0.75** 에 머물렀다.

    이제 **생산을 먼저 만들고 그 소비량으로 구매를 낸다.** 상수를 맞출 일이 없다.

    ⚠️ 부재료까지 센다 — BOM 첫 줄(주원료)은 배치가 수율을 반영해 이미 갖고 있고,
      나머지는 `출력량 × 소요량`이다(1.5.0 에서 출고를 그렇게 만들었다).
    """
    by_out: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for line in bom:
        if str(line.get("component_role") or "") == "INPUT":
            by_out[str(line["output_material_id"])].append(line)
    need: Dict[str, float] = defaultdict(float)
    for b in batches:
        need[str(b["input_material_id"])] += abs(float(b["input_quantity"]))
        for line in by_out.get(str(b["output_material_id"]), ())[1:]:
            need[str(line["input_material_id"])] += abs(
                float(b["output_quantity"]) * float(line["quantity_per_output"]))
    return dict(need)


def generate_movements_and_snapshots(profile: Profile, logistics: Sequence[Mapping[str, Any]], shipments: Sequence[Mapping[str, Any]],
                                     purchase_orders: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]],
                                     sales: Sequence[Mapping[str, Any]], materials: Sequence[Mapping[str, Any]],
                                     locations: Sequence[Mapping[str, Any]], start: date, end: date,
                                     rng: random.Random,
                                     bom: Sequence[Mapping[str, Any]] = ()) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    #: ★★★ **배합대로 원료를 내보내려면 BOM 이 있어야 한다** (1.5.0).
    #:   `MFG-02` 는 업무키가 `batch_id` 하나라 배치당 **한 행**이고, 그래서
    #:   `input_material_id` 도 하나뿐이다 — 주원료만 담긴다. 부재료는 여기, 재고
    #:   이동으로 내보낸다. 실제 ERP 도 배치 헤더와 자재 출고를 나눠 쓴다.
    _bom_in: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for _b in bom:
        if str(_b.get("component_role") or "") == "INPUT":
            _bom_in[str(_b["output_material_id"])].append(_b)
    po_by_line = {p["po_line_id"]: p for p in purchase_orders}
    shp_by_id = {s["shipment_id"]: s for s in shipments}
    movements: List[Dict[str, Any]] = []
    balances: Dict[tuple[str, str], float] = defaultdict(float)
    active_locations = [l for l in locations if str(l["active"]).lower() == "true"]
    material_ids = [m["material_id"] for m in materials]
    # Opening stock keeps production and sales movement sequences physically possible.
    #: 생산이 이 품목을 얼마나 꺼내 쓰는가 — 기초재고가 그보다 적으면 음수가 난다
    #: ⚠️ 생산 투입만 보면 모자란다 — **판매가 생산보다 앞선 달**에 완제품이 음수로
    #:   간다. 월별 스냅샷은 그 시점을 그대로 찍는다.
    _issue_need: Dict[str, float] = defaultdict(float)
    for _b in batches:
        _issue_need[str(_b["input_material_id"])] += abs(float(_b["input_quantity"]))
        #: ★ **부재료도 센다**(1.5.0). 배치가 BOM 전체를 출고하게 되었으므로, 여기서
        #:   주원료만 세면 부재료 기초재고가 모자라 **초기 몇 달이 음수**가 된다 —
        #:   총량은 구매가 대는데 **시점**이 안 맞는 것이다. 실제로 황산이 그랬다.
        for _line in _bom_in.get(str(_b["output_material_id"]), ())[1:]:
            _issue_need[str(_line["input_material_id"])] += abs(
                float(_b["output_quantity"]) * float(_line["quantity_per_output"]))
    for _s in sales:
        _issue_need[str(_s["product_id"])] += abs(float(_s["shipped_quantity"]))
    for idx, m in enumerate(materials):
        #: 그 품목이 속한 사업의 창고로 넣는다. 예전에는 `PLANT1 이면 P1, 아니면 P2`
        #: 로 굳어 있어 **사업이 셋이 되면 전부 두 번째로 갔다.**
        _b = business_defs.by_plant(BUSINESSES, m["scope_node_id"])
        #: ★ 유형에 맞는 창고로 간다 — 1.1.0 까지는 공장마다 규칙이 달라(제련은
        #:   공정재고까지 제품창고로) **공정재고 창고가 비어 있었다.**
        _avail = [l["location_id"] for l in active_locations
                  if l["tenant_id"] == m["tenant_id"] and l["scope_node_id"] == m["scope_node_id"]]
        loc = _b.opening_location(m["material_type"], _avail)
        matches = [l for l in active_locations if l["location_id"] == loc and l["tenant_id"] == m["tenant_id"]]
        if len(matches) != 1 or matches[0]["scope_node_id"] != m["scope_node_id"]:
            raise ValueError(f"Opening warehouse unavailable or outside material scope: {loc}")
        #: ★ **쓸 만큼은 있어야 한다.** 예전에는 유형별 고정값이라, 생산에 많이 들어가는
        #:   원료는 기초재고가 모자라 **재고가 마이너스로 갔다**(1.1.0 에서 1,082 행,
        #:   가장 깊은 곳 −5,276). 없는 것을 투입해 만든 데이터는 분석에 쓸 수 없다.
        _base = 2000.0 if m["material_type"] == "RAW" else 800.0 if m["material_type"] == "FINISHED" else 100.0
        #: ★★★ **주력 원료는 몇 달치만 둔다** (1.6.0).
        #:
        #: 1.15 배는 **36 개월치**이고, 그러면 살 이유가 없어진다 — 1.4.0 에서
        #: 동정광을 20,176 톤 쓰면서 612 톤만 산 것이 그래서였다. 재고 음수가 나지
        #: 않으니 검사도 통과했다. 현실의 원료 재고는 몇 달치다.
        #:
        #: ⚠️ 1.5.0 에서 **모든 품목**을 0.20 으로 내렸다가 되돌렸다 — 더미 소모품은
        #:   구매가 따라오지 않아 **음수 842 행**이 터졌다. 이제 구매가 소비를 보고
        #:   들어오므로 **주력만** 낮춘다. 더미는 그대로 1.15 다.
        #: ⚠️ **비율이 아니라 개월치로 잡아야 한다.** `_issue_need` 는 **전 기간**
        #:   소비라, 같은 비율이어도 quick(6 개월)과 full(36 개월)에서 뜻이 전혀
        #:   다르다. 0.25 로 고정했더니 full 은 9 개월치인데 quick 은 1.5 개월치가
        #:   되어 **quick 에서만 음수**가 났다(2 행).
        _known_open = {mm["code"] for mm in business_defs.materials_of(BUSINESSES)}
        _open_ratio = (min(1.15, _OPEN_STOCK_MONTHS / max(1, profile.months))
                       if m["material_id"] in _known_open else 1.15)
        qty = round(max(_base, _issue_need[m["material_id"]] * _open_ratio), 3)
        balances[(m["material_id"], loc)] += qty
        movements.append({"movement_id": f"MOV-OPEN-{idx+1:05d}", "movement_date": iso(start),
                          "movement_type": "OPENING", "material_id": m["material_id"], "lot_id": f"LOT-OPEN-{idx+1:05d}",
                          "from_location_id": "", "to_location_id": loc, "quantity": qty, "quantity_uom": m["base_uom"],
                          "reference_type": "OPENING_BALANCE", "reference_id": "DEMO-OPENING", "_scope": m["scope_node_id"]})
    # Delivered inbound.
    for tr in logistics:
        if tr["event_type"] != "DELIVERED":
            continue
        shp = shp_by_id[tr["shipment_id"]]
        po = po_by_line[shp["po_line_id"]]
        d = str(tr["event_at"])[:10]
        movements.append({"movement_id": f"MOV-IN-{tr['transport_id']}", "movement_date": d,
                          "movement_type": "PURCHASE_RECEIPT", "material_id": po["material_id"],
                          "lot_id": f"LOT-{tr['shipment_id']}", "from_location_id": "IN_TRANSIT",
                          "to_location_id": tr["destination_location_id"], "quantity": tr["delivered_quantity"],
                          "quantity_uom": tr["quantity_uom"], "reference_type": "SHIPMENT",
                          "reference_id": tr["shipment_id"], "_scope": po["scope_node_id"]})
    # Production issue and receipt. Keep raw issue on the same day and product receipt after it.
    for b in batches:
        _bd = business_defs.by_plant(BUSINESSES, b["site_id"])
        raw_loc, fg_loc = _bd.raw_location, _bd.fg_location
        movements.append({"movement_id": f"MOV-ISS-{b['batch_id']}", "movement_date": b["production_date"],
                          "movement_type": "PRODUCTION_ISSUE", "material_id": b["input_material_id"],
                          "lot_id": b["input_lot_id"], "from_location_id": raw_loc, "to_location_id": "PRODUCTION",
                          "quantity": -float(b["input_quantity"]), "quantity_uom": b["quantity_uom"],
                          "reference_type": "BATCH", "reference_id": b["batch_id"], "_scope": b["site_id"]})
        #: ★★★ **부재료도 나간다** (1.5.0). 1.4.0 까지는 BOM 첫 줄만 출고했다 —
        #:   「수산화리튬 = Black Mass 5.2 + 황산 0.12 + 소석회 0.05」인데 Black Mass
        #:   만 나갔고, **황산·소석회는 사 놓고 쓰지 않는** 데이터였다(조합 키트에서
        #:   황산 706 톤 구매 · 0 톤 소비).
        #:
        #: 주원료(`recipe[0]`)는 위에서 **수율을 반영해** 이미 나갔으므로 건너뛴다.
        for _k, _line in enumerate(_bom_in.get(str(b["output_material_id"]), ())[1:], 2):
            _mid = str(_line["input_material_id"])
            movements.append({"movement_id": f"MOV-ISS-{b['batch_id']}-{_k}",
                              "movement_date": b["production_date"],
                              "movement_type": "PRODUCTION_ISSUE", "material_id": _mid,
                              "lot_id": f"LOT-RM-{_mid}-{b['batch_id']}",
                              "from_location_id": raw_loc, "to_location_id": "PRODUCTION",
                              "quantity": -round(float(b["output_quantity"]) * float(_line["quantity_per_output"]), 3),
                              "quantity_uom": business_defs.uom_of(BUSINESSES, _mid),
                              "reference_type": "BATCH", "reference_id": b["batch_id"],
                              "_scope": b["site_id"]})
        movements.append({"movement_id": f"MOV-RCP-{b['batch_id']}", "movement_date": b["production_date"],
                          "movement_type": "PRODUCTION_RECEIPT", "material_id": b["output_material_id"],
                          "lot_id": b["output_lot_id"], "from_location_id": "PRODUCTION", "to_location_id": fg_loc,
                          "quantity": float(b["output_quantity"]), "quantity_uom": b["quantity_uom"],
                          "reference_type": "BATCH", "reference_id": b["batch_id"], "_scope": b["site_id"]})
        #: ★ **부산물도 함께 나온다.** 이것이 없으면 부산물을 팔 때 재고가 마이너스로
        #:   간다 — 1.2.0 을 만들면서 실제로 −1,203 톤까지 갔다.
        for _bp, _rate in business_defs.byproduct_rates_of(BUSINESSES, b["output_material_id"]):
            movements.append({"movement_id": f"MOV-BP-{_bp}-{b['batch_id']}", "movement_date": b["production_date"],
                              "movement_type": "PRODUCTION_RECEIPT", "material_id": _bp,
                              "lot_id": f"LOT-BP-{_bp}-{b['batch_id']}", "from_location_id": "PRODUCTION",
                              "to_location_id": _bd.opening_location("BYPRODUCT", [l["location_id"] for l in active_locations]),
                              "quantity": round(float(b["output_quantity"]) * _rate, 3),
                              "quantity_uom": business_defs.uom_of(BUSINESSES, _bp),
                              "reference_type": "BATCH", "reference_id": b["batch_id"], "_scope": b["site_id"]})
    for s in sales:
        loc = business_defs.by_plant(BUSINESSES, s["scope_node_id"]).fg_location
        movements.append({"movement_id": f"MOV-SO-{s['sales_line_id']}", "movement_date": s["actual_ship_date"],
                          "movement_type": "SALES_SHIPMENT", "material_id": s["product_id"],
                          "lot_id": f"LOT-SALES-{s['sales_line_id']}", "from_location_id": loc, "to_location_id": "CUSTOMER",
                          "quantity": -float(s["shipped_quantity"]), "quantity_uom": s["quantity_uom"],
                          "reference_type": "SALES_ORDER", "reference_id": s["sales_line_id"], "_scope": s["scope_node_id"]})
    # Add controlled transfer/adjustment events so Full has operational density without breaking conservation.
    target = 5000 if profile.name == "quick" else 30000
    i = 0
    _mat_by_id = {m["material_id"]: m for m in materials}
    while len(movements) < target:
        #: 몇 바퀴째 · 그 안에서 몇 번째 품목인가 — 부호와 크기가 여기서 나온다
        _k = i % len(material_ids)
        _round = i // len(material_ids)
        mat = material_ids[_k]
        #: ★★★ **그 품목이 실제로 있는 창고**에만 조정한다 (1.7.0).
        #:
        #: 예전에는 그 사업의 창고를 **순환**해서, 완제품이 원료 창고에 조정 입고되는
        #: 일이 생겼다(1.6.0 까지는 전부 양수라 「완제품이 원료 창고에 조금 있다」로
        #: 남았고, **음수 조정을 넣자마자 재고가 −6,430 행**이 됐다 — 애초에 없는
        #: 재고를 줄였기 때문이다).
        #:
        #: 기초재고가 들어가는 창고와 **같은 곳**을 고른다. 실사는 재고가 있는 데서 한다.
        _mrow = _mat_by_id.get(mat)
        _bd = business_defs.by_plant(BUSINESSES, scope_of(mat))
        _avail_adj = [l["location_id"] for l in active_locations
                      if business_defs.by_location(BUSINESSES, l["location_id"]).plant_id == scope_of(mat)]
        loc = _bd.opening_location(str(_mrow["material_type"]) if _mrow else "RAW", _avail_adj)
        d = start + timedelta(days=(i*7) % max(1,(end-start).days))
        #: ★★★ **실사 조정은 양방향이다** (1.7.0).
        #:
        #: 장부보다 많을 때도 있고 적을 때도 있다. 1.6.0 까지 **전부 입고(양수)** 라서
        #: **재고가 저절로 늘었다** — 제련 키트에서 순증 +326 톤. 그것이 「없는 것을
        #: 판다·쓴다」를 재고 음수로 드러나지 않게 가렸다(9.5~9.7 의 세 결함이 모두
        #: 그래서 늦게 발견됐다).
        #:
        #: ★ `i%2`(부호)와 `i%9`(크기)는 서로소라 **18 주기마다 정확히 상쇄**된다 —
        #:   각 크기가 `+` 한 번, `−` 한 번 나온다.
        #: ⚠️ 부호를 `i%2` 로 잡으면 **품목 수가 짝수일 때 같은 품목이 늘 같은 부호**를
        #:   받는다(품목 210 개). `_k + _round` 로 잡으면 품목마다도, 바퀴마다도
        #:   번갈아 나온다.
        _sign = 1 if (_k + _round) % 2 == 0 else -1
        qty = round((0.05 + (_k % 9)*0.03) * _sign, 3)
        movements.append({"movement_id": f"MOV-ADJ-{i+1:07d}", "movement_date": iso(d),
                          "movement_type": "CYCLE_COUNT_ADJUSTMENT", "material_id": mat, "lot_id": f"LOT-ADJ-{i+1:07d}",
                          #: 재고가 **나가는** 조정이면 창고가 출발지다
                          "from_location_id": "ADJUSTMENT" if _sign > 0 else loc,
                          "to_location_id": loc if _sign > 0 else "ADJUSTMENT", "quantity": qty,
                          "quantity_uom": business_defs.uom_of(BUSINESSES, mat),
                          "reference_type": "CYCLE_COUNT", "reference_id": f"CC-{i+1:07d}",
                          "_scope": business_defs.by_location(BUSINESSES, loc).plant_id})
        i += 1
    movements = sorted(movements, key=lambda x: (x["movement_date"], x["movement_id"]))
    stamped_movements = stamp("INV-02", movements, kind="ACTUAL")

    # Monthly snapshots exactly derived from movement ledger.
    current: Dict[tuple[str, str], float] = defaultdict(float)
    idx = 0
    snapshots = []
    month_cursor = date(start.year, start.month, 1)
    while month_cursor <= end:
        cutoff = month_end(month_cursor)
        while idx < len(stamped_movements) and date.fromisoformat(str(stamped_movements[idx]["movement_date"])[:10]) <= cutoff:
            m = stamped_movements[idx]
            qty = float(m["quantity"])
            #: ★ **부호가 방향을 정한다** (1.7.0). 예전에는 이동 유형을 나열했는데
            #:   (`PRODUCTION_ISSUE`·`SALES_SHIPMENT` 면 출발지), 유형이 늘 때마다
            #:   여기를 고쳐야 했고 **빠뜨리면 조용히 반대쪽에 쌓인다.** 실제로
            #:   음수 조정을 넣자마자 그렇게 될 뻔했다.
            #:
            #: ⚠️ 바꾸기 전에 대조했다 — 기존 데이터 30,000 행에서 **두 방식의 판정이
            #:   한 건도 다르지 않다.** 나가는 이동은 전부 음수였기 때문이다.
            loc = m["from_location_id"] if qty < 0 else m["to_location_id"]
            if loc not in {"", "PRODUCTION", "CUSTOMER", "IN_TRANSIT", "ADJUSTMENT"}:
                current[(m["material_id"], loc)] += qty
            idx += 1
        for mat in material_ids:
            #: ★ **그 품목의 사업에 속한 창고만** 센다. 예전에는 품목 × 창고를 전부
            #:   돌려서 절반이 남의 사업 창고였고(27,756 행), 제련 키트를 뽑아도
            #:   **황산니켈 재고 행이 따라왔다.**
            relevant = [l["location_id"] for l in active_locations
                        if business_defs.by_location(BUSINESSES, l["location_id"]).plant_id == scope_of(mat)]
            for loc in relevant:
                qty = round(current[(mat, loc)], 3)
                snapshots.append({"snapshot_id": f"STK-{cutoff:%Y%m%d}-{mat}-{loc}", "snapshot_date": iso(cutoff),
                                  "location_id": loc, "material_id": mat, "lot_id": "ALL",
                                  "unrestricted_quantity": qty, "quality_quantity": 0.0, "blocked_quantity": 0.0,
                                  "safety_stock_quantity": 50.0 if mat.startswith("RM-") else 10.0,
                                  "quantity_uom": business_defs.uom_of(BUSINESSES, mat),
                                  "_scope": business_defs.by_location(BUSINESSES, loc).plant_id})
        month_cursor = add_months(month_cursor, 1)
    return stamped_movements, stamp("INV-01", snapshots, kind="ACTUAL")


def generate_quality(profile: Profile, shipments: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]],
                     rng: random.Random) -> List[Dict[str, Any]]:
    rows = []
    targets = [("INBOUND", s["shipment_id"], str(s["eta"])[:10], s["scope_node_id"]) for s in shipments]
    targets += [("PRODUCT", b["batch_id"], b["production_date"], b["scope_node_id"]) for b in batches]
    target_count = 1500 if profile.name == "quick" else 12000
    for i in range(target_count):
        typ, ref, d, scope = targets[i % len(targets)]
        spec = 10.0 if typ == "PRODUCT" else 15.0
        value = max(0, rng.gauss(5.0 if typ == "PRODUCT" else 8.0, 1.8))
        rows.append({"inspection_id": f"QI-{i+1:07d}", "inspection_type": typ, "object_ref": ref,
                     "inspection_date": d, "characteristic": "IMPURITY_PPM", "result_value": round(value, 4),
                     "lower_spec": 0.0, "upper_spec": spec, "unit": "PPM",
                     "verdict": "PASS" if value <= spec else "FAIL", "action": "RELEASE" if value <= spec else "BLOCK",
                     "spec_version": "DEMO-1.0", "_scope": scope})
    return stamp("QLT-01", rows, kind="ACTUAL")


def generate_finance(profile: Profile, contracts: Sequence[Mapping[str, Any]], purchase_orders: Sequence[Mapping[str, Any]],
                     shipments: Sequence[Mapping[str, Any]], sales: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]],
                     start: date, end: date, rng: random.Random) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    contract_by_id = {c["contract_id"]: c for c in contracts}
    shipped_po = {s["po_line_id"] for s in shipments}
    fin2 = []
    for p in purchase_orders:
        if p["po_line_id"] not in shipped_po:
            continue
        amount = round(float(p["order_quantity"]) * float(p["unit_price"]), 2)
        post = date.fromisoformat(p["due_date"])
        fin2.append({"finance_document_id": f"AP-{p['po_line_id']}", "document_type": "AP",
                     "partner_id": p["supplier_id"], "reference_id": p["po_line_id"],
                     "posting_date": iso(post), "due_date": iso(post+timedelta(days=45)),
                     "amount": amount, "currency": p["currency"], "paid_at": iso(post+timedelta(days=42)),
                     "status": "PAID", "_scope": p["scope_node_id"]})
    for s in sales:
        amount = round(float(s["shipped_quantity"]) * float(s["unit_price"]), 2)
        post = date.fromisoformat(s["actual_ship_date"])
        fin2.append({"finance_document_id": f"AR-{s['sales_line_id']}", "document_type": "AR",
                     "partner_id": s["customer_id"], "reference_id": s["sales_line_id"],
                     "posting_date": iso(post), "due_date": iso(post+timedelta(days=45)),
                     "amount": amount, "currency": s["currency"], "paid_at": iso(post+timedelta(days=43)),
                     "status": "COLLECTED", "_scope": s["scope_node_id"]})
    fin2s = stamp("FIN-02", fin2, kind="ACTUAL")

    # Monthly product cost components from synthetic operating drivers.
    products = sorted({str(b["output_material_id"]) for b in batches})
    fin1 = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        for product in products:
            base = 15500 if product == "FG-NISO4" else 7200 if product == "FG-CATHODE" else 19000
            for component, share in [("MATERIAL", .72), ("CONVERSION", .16), ("LOGISTICS", .07), ("QUALITY_LOSS", .05)]:
                standard = base * share
                actual = standard * (0.97 + rng.random()*0.08)
                fin1.append({"cost_record_id": f"COST-{cursor:%Y%m}-{product}-{component}", "fiscal_period": f"{cursor:%Y-%m}",
                             "product_id": product, "cost_component": component, "standard_unit_cost": round(standard, 2),
                             "actual_unit_cost": round(actual, 2), "variance_amount": round(actual-standard, 2),
                             "currency": "USD", "quantity_uom": "TON", "_scope": scope_of(product)})
        cursor = add_months(cursor, 1)
    fin1s = stamp("FIN-01", fin1, kind="ACTUAL")

    # Double-entry ledger. Every document has equal debit and credit.
    ledger = []
    line_no = 0
    for doc in fin2s:
        amount = float(doc["amount"])
        if doc["document_type"] == "AP":
            pairs = [("1200", amount, 0.0, "INVENTORY"), ("2000", 0.0, amount, "AP")]
        else:
            pairs = [("1100", amount, 0.0, "AR"), ("4000", 0.0, amount, "REVENUE")]
        for account, debit, credit, cf in pairs:
            line_no += 1
            ledger.append({"ledger_line_id": f"GL-{line_no:08d}", "document_id": doc["finance_document_id"],
                           "posting_date": doc["posting_date"], "fiscal_period": str(doc["posting_date"])[:7],
                           "account_id": account, "cost_center_id": "CC-PROC" if doc["document_type"] == "AP" else "CC-MGT",
                           "debit_amount": debit, "credit_amount": credit, "currency": doc["currency"],
                           "cashflow_line": cf, "plan_actual": "ACTUAL", "_scope": doc["scope_node_id"]})
    # Paired overhead postings add operational density but remain balanced.
    while line_no < profile.gl_documents * 2:
        doc_no = line_no//2 + 1
        d = start + timedelta(days=(doc_no*11) % max(1,(end-start).days))
        amount = round(1000 + (doc_no%43)*137.5, 2)
        for account, debit, credit in [("5100", amount, 0.0), ("1000", 0.0, amount)]:
            line_no += 1
            ledger.append({"ledger_line_id": f"GL-{line_no:08d}", "document_id": f"OPEX-{doc_no:07d}",
                           "posting_date": iso(d), "fiscal_period": f"{d:%Y-%m}", "account_id": account,
                           "cost_center_id": "CC-MFG", "debit_amount": debit, "credit_amount": credit,
                           "currency": "KRW", "cashflow_line": "OPERATING", "plan_actual": "ACTUAL", "_scope": ADV_SCOPE})
    return fin1s, fin2s, stamp("FIN-03", ledger, kind="ACTUAL")


def generate_knowledge() -> List[Dict[str, Any]]:
    rows = []
    titles = [
        "원료 구매·도입계획 업무표준", "선적·통관 사건 데이터 계약", "재고 물량 대사 기준",
        "생산 수율·부산물 계산 기준", "구매원가·운전자본 계산 기준", "시나리오 승인·비교 절차",
        "의사결정 요청 검토서 작성 기준", "합성 데이터 사용 제한", "외부지표 적용·시차 기준",
        "생성 앱 Host Runtime 데이터 접근 원칙",
    ]
    for i, title in enumerate(titles, 1):
        rows.append({"document_id": f"KNW-DEMO-{i:03d}", "title": title, "document_type": "STARTER_KIT_GUIDE",
                     "classification": "INTERNAL_DEMO", "owner_org_id": "dept-management",
                     "effective_from": "2026-08-11", "effective_to": "9999-12-31",
                     "approval_status": "APPROVED_FOR_DEMO", "source_ref": "docs/data-kits",
                     "checksum": stable_id("sha", title), "rag_eligible": True, "_scope": GROUP_SCOPE})
    return stamp("KNW-01", rows, kind="REFERENCE", default_scope=GROUP_SCOPE)


def generate_simulation_and_decisions() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    driver_defs = [
        ("DRV-FX", "USD_KRW", "PURCHASE_COST", "PURCHASE_USD*USD_KRW", 0, "KRW"),
        ("DRV-COMMODITY", "COMMODITY_PRICE", "PURCHASE_PRICE", "BENCHMARK*(1+PREMIUM)", 0, "USD/TON"),
        ("DRV-FREIGHT", "SEA_FREIGHT", "LANDED_COST", "GOODS_COST+FREIGHT+DUTY", 0, "USD"),
        ("DRV-DELAY", "ETA_DELAY_DAYS", "AVAILABLE_INVENTORY", "OPENING+RECEIPTS-CONSUMPTION", 1, "TON"),
        ("DRV-SUPPLY", "SUPPLY_REDUCTION", "MATERIAL_SHORTAGE", "REQUIREMENT-AVAILABLE", 0, "TON"),
        ("DRV-YIELD", "YIELD", "PRODUCTION_OUTPUT", "INPUT*YIELD", 0, "TON"),
        ("DRV-DOWNTIME", "DOWNTIME_HOURS", "AVAILABLE_CAPACITY", "RATE*(CALENDAR-DOWNTIME)*OEE", 0, "TON"),
        ("DRV-POWER", "POWER_PRICE", "CONVERSION_COST", "KWH*POWER_PRICE", 0, "KRW"),
        ("DRV-DEMAND", "DEMAND_CHANGE", "REVENUE", "VOLUME*PRICE", 0, "USD"),
        ("DRV-CAPEX", "CAPEX", "CASH_BALANCE", "OPENING_CASH+INFLOW-OUTFLOW-CAPEX", 0, "KRW"),
        ("DRV-GM", "REVENUE_AND_COST", "GROSS_MARGIN", "REVENUE-COGS", 0, "KRW"),
        ("DRV-CASH", "AR_AP_TIMING", "ENDING_CASH", "OPENING+COLLECTIONS-PAYMENTS", 1, "KRW"),
    ]
    drivers = stamp("SIM-01", [{"driver_id": a, "input_metric": b, "output_metric": c,
                                "formula_definition": d, "lag_period_months": e, "output_unit": f,
                                "formula_version": "1.0.0", "approval_status": "APPROVED_FOR_DEMO",
                                "effective_from": "2026-08-11", "effective_to": "9999-12-31",
                                "_scope": GROUP_SCOPE} for a,b,c,d,e,f in OVERLAY.apply_drivers(driver_defs)],
                    kind="REFERENCE", default_scope=GROUP_SCOPE)
    scenarios_def = [
        ("SCN-01", "환율 10% 상승", "DRV-FX", 0.10, "%", "PURCHASE_COST,CASH,GROSS_MARGIN"),
        ("SCN-02", "원료가격 15% 상승", "DRV-COMMODITY", 0.15, "%", "PURCHASE_COST,COGS,GROSS_MARGIN"),
        ("SCN-03", "해상운임 30% 상승", "DRV-FREIGHT", 0.30, "%", "LANDED_COST,INVENTORY_VALUE"),
        ("SCN-04", "선적·통관 14일 지연", "DRV-DELAY", 14, "DAY", "INVENTORY,PRODUCTION,REVENUE"),
        ("SCN-05", "핵심 공급사 공급량 20% 감소", "DRV-SUPPLY", -0.20, "%", "SUPPLY,PRODUCTION,CASH"),
        ("SCN-06", "생산수율 2%p 하락", "DRV-YIELD", -0.02, "PERCENT_POINT", "OUTPUT,UNIT_COST"),
        ("SCN-07", "주요 설비 48시간 정지", "DRV-DOWNTIME", 48, "HOUR", "CAPACITY,SHIPMENT,REVENUE"),
        ("SCN-08", "전력단가 12% 상승", "DRV-POWER", 0.12, "%", "CONVERSION_COST,GROSS_MARGIN"),
        ("SCN-09", "제품수요 15% 감소", "DRV-DEMAND", -0.15, "%", "SALES,INVENTORY,CASH"),
        ("SCN-10", "신규 공장 투자", "DRV-CAPEX", 180_000_000_000, "KRW", "CAPACITY,CASH,ROI"),
    ]
    scenarios = stamp("SIM-02", [{"scenario_id": a, "scenario_name": b, "baseline_id": "BASELINE-DEMO-1.0",
                                  "driver_id": c, "change_value": d, "change_unit": e,
                                  "impact_metrics": f, "scenario_period_start": "2026-09-01",
                                  "scenario_period_end": "2027-12-31", "approval_status": "APPROVED_FOR_DEMO",
                                  "rationale": "제품 기능 검증용 Golden Decision Case", "_scope": GROUP_SCOPE}
                                 for a,b,c,d,e,f in OVERLAY.apply_scenarios(scenarios_def)],
                                kind="SCENARIO", default_scope=GROUP_SCOPE)
    decisions = []
    for i, scn in enumerate(scenarios[:3], 1):
        decisions.append({"decision_id": f"DEC-DEMO-{i:03d}", "package_id": f"PKG-DEMO-{i:03d}",
                          "scenario_id": scn["scenario_id"], "requester_user_id": "demo_controller_07@afs.example",
                          "approver_user_id": "demo_executive_08@afs.example", "decision_status": "APPROVED",
                          "decision_text": f"{scn['scenario_name']} 대응안 단계적 실행", "action_id": f"ACT-DEMO-{i:03d}",
                          "action_owner_org_id": ["dept-finance", "dept-procurement", "dept-logistics"][i-1],
                          "kpi_before": 100.0, "kpi_target": 95.0-i, "kpi_actual": 96.0-i,
                          "effect_status": "MEASURED_DEMO", "_scope": ADV_SCOPE})
    golden = {
        "baseline_id": "BASELINE-DEMO-1.0", "data_class": "SYNTHETIC",
        "not_for_management_decision": True,
        "cases": [{"scenario_id": a, "driver_id": c, "change_value": d, "change_unit": e,
                   "expected_direction": "DECREASE" if d < 0 or a in {"SCN-01","SCN-02","SCN-03","SCN-04","SCN-07","SCN-08"} else "MIXED",
                   "tolerance": {"type": "RELATIVE", "value": 0.005}}
                  for a,b,c,d,e,f in scenarios_def]
    }
    return drivers, scenarios, stamp("DEC-01", decisions, kind="ACTUAL"), golden


def generate_profile(profile: Profile) -> Dict[str, List[Dict[str, Any]]]:
    rng = random.Random(profile.seed + (0 if profile.name == "quick" else 1000))
    end = date(2026, 7, 31)
    start = add_months(date(end.year, end.month, 1), -(profile.months-1))
    datasets: Dict[str, List[Dict[str, Any]]] = {}
    datasets["FND-01"] = generate_org(profile)
    datasets["FND-02"] = generate_users(profile)
    datasets["FND-03"] = generate_references(profile, start, end)
    datasets["MDM-01"] = generate_materials(profile)
    #: ★ 완제품 + 사업이 더 판다고 한 것(부산물). 1.1.0 까지는 `FINISHED` 뿐이라
    #:   **제련인데 황산도 금도 팔지 않았다.**
    products = business_defs.sellable_of(
        BUSINESSES, [m["material_id"] for m in datasets["MDM-01"] if m["material_type"] == "FINISHED"])
    datasets["MDM-02"] = generate_suppliers(profile, datasets["MDM-01"], rng)
    datasets["MDM-03"] = generate_customers(profile, products)
    datasets["MDM-04"] = generate_locations(profile)
    datasets["MDM-05"] = generate_bom(profile, datasets["MDM-01"])
    datasets["MDM-06"] = generate_routing(profile, datasets["MDM-01"])
    datasets["MDM-07"] = generate_accounts(profile)
    datasets["MDM-08"] = generate_trade_refs(profile)
    datasets["EXT-01"], datasets["EXT-02"], datasets["EXT-03"] = generate_external(profile, start, rng)
    #: ★★★ **파는 것 → 만드는 것 → 사는 것** 순으로 낸다 (1.6.0).
    #:
    #: 1.5.0 까지는 구매가 **맨 앞**이었다. 그래서 「얼마나 쓸지」를 모른 채 발주를
    #: 만들었고, 발주량은 `purchase_qty_scale` 이라는 손으로 맞춘 상수로 정했다 —
    #: 사업·판본이 바뀔 때마다 다시 맞춰야 했고(1.5.0 에서 네 번 고쳤다) 그래도
    #: **구매/소비가 0.66~0.75** 에 머물렀다.
    #:
    #: 의존은 그대로다 — 구매는 품목·공급사·지표만 보고, 그 셋은 여전히 앞에 있다.
    datasets["SLS-01"] = generate_sales(profile, datasets["MDM-03"], products, start, end, rng)
    datasets["MFG-01"], datasets["MFG-02"], datasets["MFG-03"] = generate_plans_batches_events(
        profile, datasets["MDM-05"], datasets["MDM-06"], datasets["SLS-01"], start, end, rng)
    #: 이제 **얼마나 쓸지 안다**
    _need = material_need(datasets["MFG-02"], datasets["MDM-05"])
    datasets["PRC-01"] = generate_contracts(profile, datasets["MDM-02"], datasets["MDM-01"],
                                            datasets["EXT-02"], rng, _need)
    (datasets["PRC-02"], datasets["LOG-01"], datasets["LOG-02"], datasets["LOG-03"],
     datasets["LOG-04"], datasets["LOG-05"]) = generate_purchase_and_logistics(
        profile, datasets["PRC-01"], datasets["MDM-02"], start, end, rng, _need)
    datasets["INV-02"], datasets["INV-01"] = generate_movements_and_snapshots(
        profile, datasets["LOG-05"], datasets["LOG-02"], datasets["PRC-02"], datasets["MFG-02"],
        datasets["SLS-01"], datasets["MDM-01"], datasets["MDM-04"], start, end, rng,
        datasets["MDM-05"])
    datasets["QLT-01"] = generate_quality(profile, datasets["LOG-02"], datasets["MFG-02"], rng)
    datasets["FIN-01"], datasets["FIN-02"], datasets["FIN-03"] = generate_finance(
        profile, datasets["PRC-01"], datasets["PRC-02"], datasets["LOG-02"], datasets["SLS-01"],
        datasets["MFG-02"], start, end, rng)
    datasets["KNW-01"] = generate_knowledge()
    datasets["SIM-01"], datasets["SIM-02"], datasets["DEC-01"], golden = generate_simulation_and_decisions()
    datasets["_GOLDEN"] = [golden]
    return datasets


def make_contract(dataset_id: str, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    headers: List[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    fields = []
    for key in headers:
        values = [r.get(key) for r in rows[:500]]
        fields.append({"name": key, "type": infer_type(values),
                       "required": (key in COMMON_FIELDS
                                    or key in DATASETS[dataset_id]["keys"]
                                    or key in REQUIRED_DATASET_FIELDS.get(dataset_id, set())),
                       "business_key": key in DATASETS[dataset_id]["keys"],
                       "description": f"{DATASETS[dataset_id]['name']}의 {key}"})
    return {
        "dataset_id": dataset_id, "dataset_name": DATASETS[dataset_id]["name"],
        "contract_version": KIT_VERSION, "status": "APPROVED_FOR_DEMO",
        "scope": {"tenant_required": True, "scope_required": True,
                  "allowed_scope_types": ["ENTERPRISE_GROUP", "LEGAL_ENTITY", "BUSINESS_DIVISION", "PLANT", "DEPARTMENT"]},
        "classification": {"data_class": "SYNTHETIC", "data_origin": "SYNTHETIC",
                           "not_for_management_decision": True},
        "business_keys": DATASETS[dataset_id]["keys"], "dependencies": DATASETS[dataset_id]["deps"],
        "schema": {"fields": fields},
        "quality": {"required_common_fields": COMMON_FIELDS, "fail_closed_on_scope_missing": True,
                    "quarantine_on_reference_failure": True},
        "lineage": {"generator": "scripts/generate_sample_company_starter_kit.py", "kit_version": KIT_VERSION},
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def app_blueprints() -> List[Dict[str, Any]]:
    return [
        {"app_id": "APP-01", "name": "원료 도입계획·추적", "datasets": ["PRC-01","PRC-02","LOG-01","LOG-02","LOG-03","LOG-04","LOG-05","EXT-01","EXT-02","EXT-03"]},
        {"app_id": "APP-02", "name": "물류 사건 확인·입력", "datasets": ["LOG-01","LOG-02","LOG-03","LOG-04","LOG-05","INV-02"]},
        {"app_id": "APP-03", "name": "재고·생산 영향 분석", "datasets": ["INV-01","INV-02","MFG-01","MFG-02","MFG-03","QLT-01"]},
        {"app_id": "APP-04", "name": "구매원가·현금 전망", "datasets": ["PRC-01","FIN-01","FIN-02","FIN-03","EXT-01","EXT-02"]},
        {"app_id": "APP-05", "name": "공급 위험·대체안", "datasets": ["MDM-02","PRC-01","PRC-02","EXT-02","EXT-03","SIM-02"]},
        {"app_id": "APP-06", "name": "판매·납기·매출 영향", "datasets": ["SLS-01","MFG-01","INV-01","FIN-02","FIN-03","EXT-01"]},
        {"app_id": "APP-07", "name": "전사 시나리오·실적 통합", "datasets": ["PRC-02","LOG-02","INV-01","MFG-01","SLS-01","FIN-01","FIN-02","FIN-03","EXT-01","EXT-02","SIM-01","SIM-02","DEC-01"]},
    ]


def report_templates() -> List[Dict[str, Any]]:
    return [
        {"report_id": "RPT-01", "name": "원료 도입·재고 경영 현황"},
        {"report_id": "RPT-02", "name": "시나리오 비교 보고서"},
        {"report_id": "RPT-03", "name": "의사결정 요청 검토서"},
        {"report_id": "RPT-04", "name": "실행 효과 보고서"},
        {"report_id": "RPT-05", "name": "대내외 발간 초안"},
    ]


def company_profiles() -> List[Dict[str, Any]]:
    """회사 선택·복사·신사업 시뮬레이션용 명시적 가상회사 Profile."""
    common = {
        "data_class": "SYNTHETIC",
        "data_origin": "SYNTHETIC",
        "entity_mode": "VIRTUAL",
        "certification_status": "CERTIFIED_FOR_DEMO",
        "not_for_management_decision": True,
        "currency": "KRW",
        "timezone": "Asia/Seoul",
    }
    return [
        {
            **common,
            "company_profile_id": "AFS-DEMO-MATERIALS-GROUP",
            "company_name": "AFS 데모소재그룹",
            "profile_role": "BASE_SAMPLE_COMPANY",
            "source_profile_id": "",
            "industry_code": "C24",
            "industry_name": "비철금속·배터리소재 제조",
            "purpose": "Starter Kit 기준회사와 부서 업무·전사 시나리오 흐름 체험",
            "valid_until": "9999-12-31",
            "organization_blueprint": ["기업집단", "제련법인", "첨단소재법인", "사업부", "공장", "기능부서"],
            "products": ["전기동", "고순도 황산니켈", "배터리급 수산화리튬", "귀금속 부산물"],
            "recommended_apps": ["APP-01", "APP-02", "APP-03", "APP-04", "APP-05",
                                 "APP-06", "APP-07"],
            "default_assumptions": {"baseline": "BASELINE-DEMO-1.0"},
        },
        {
            **common,
            "company_profile_id": "AFS-VIRTUAL-BATTERY-EXPANSION-2030",
            "company_name": "AFS 배터리소재 제3공장 증설안",
            "profile_role": "VIRTUAL_EXPANSION",
            "source_profile_id": "AFS-DEMO-MATERIALS-GROUP",
            "industry_code": "C2013",
            "industry_name": "무기화학·배터리 전구체 소재",
            "purpose": "황산니켈 생산능력 증설과 전력·원료·현금 영향을 사전 검증",
            "valid_until": "2032-12-31",
            "organization_blueprint": ["배터리소재사업부", "기존 제2공장", "가상 제3공장", "증설 PMO"],
            "products": ["고순도 황산니켈", "배터리급 수산화리튬"],
            "recommended_apps": ["APP-01", "APP-03", "APP-04"],
            "default_assumptions": {
                "capacity_increase_pct": 35.0, "capex_krw_billion": 180.0,
                "electricity_price_change_pct": 12.0, "commissioning_year": 2030,
                "ramp_up_months": 18,
            },
        },
        {
            **common,
            "company_profile_id": "AFS-VIRTUAL-CIRCULAR-METALS",
            "company_name": "AFS 순환금속 리사이클링 신사업안",
            "profile_role": "VIRTUAL_NEW_BUSINESS",
            "source_profile_id": "AFS-DEMO-MATERIALS-GROUP",
            "industry_code": "C3832",
            "industry_name": "금속 폐기물 재생·순환소재",
            "purpose": "폐배터리·스크랩 회수와 구리·니켈·귀금속 재생사업의 수익성 검증",
            "valid_until": "2032-12-31",
            "organization_blueprint": ["순환소재법인", "원료회수사업부", "전처리공장", "습식제련공장"],
            "products": ["재생 구리", "재생 니켈염", "회수 귀금속", "블랙매스 중간재"],
            "recommended_apps": ["APP-01", "APP-03", "APP-05"],
            "default_assumptions": {
                "feedstock_ton_per_year": 120000, "metal_recovery_rate_pct": 92.0,
                "scrap_price_to_benchmark_pct": 85.0, "capex_krw_billion": 240.0,
                "carbon_credit_krw_per_ton": 18000,
            },
        },
        {
            **common,
            "company_profile_id": "AFS-VIRTUAL-GLOBAL-SMELTING",
            "company_name": "AFS 글로벌 제련법인 진출안",
            "profile_role": "VIRTUAL_OVERSEAS_ENTITY",
            "source_profile_id": "AFS-DEMO-MATERIALS-GROUP",
            "industry_code": "C2412",
            "industry_name": "비철금속 제련·정련",
            "purpose": "해외 원료 산지 인접 제련법인의 물류·환율·투자·연결손익 검증",
            "valid_until": "2032-12-31",
            "organization_blueprint": ["해외 제련법인", "제련사업부", "현지 제1공장", "수출물류센터"],
            "products": ["전기동", "동 아노드", "황산", "금·은 부산물"],
            "recommended_apps": ["APP-01", "APP-02", "APP-04", "APP-05"],
            "default_assumptions": {
                "capacity_ton_per_year": 300000, "capex_krw_billion": 650.0,
                "usd_krw": 1380.0, "ocean_lead_time_days": 21,
                "local_tax_rate_pct": 22.0,
            },
        },
        {
            **common,
            "company_profile_id": "AFS-VIRTUAL-SMART-POWER",
            "company_name": "AFS 스마트 전력기기 신규법인안",
            "profile_role": "VIRTUAL_ADJACENT_BUSINESS",
            "source_profile_id": "AFS-DEMO-MATERIALS-GROUP",
            "industry_code": "C2812",
            "industry_name": "전기회로 개폐·보호장치 제조",
            "purpose": "전력기기 사업 진출과 자동화 투자·고용·품질·납기 효과 검증",
            "valid_until": "2032-12-31",
            "organization_blueprint": ["스마트전력기기법인", "영업설계", "부품조달", "조립공장", "품질보증"],
            "products": ["스마트 배전반", "산업용 차단기", "설비 예지센서 패키지"],
            "recommended_apps": ["APP-03", "APP-04", "APP-05"],
            "default_assumptions": {
                "order_growth_pct": 18.0, "automation_productivity_pct": 20.0,
                "defect_reduction_pct": 15.0, "workforce_change_pct": 8.0,
                "capex_krw_billion": 95.0,
            },
        },
        {
            **common,
            "company_profile_id": "AFS-VIRTUAL-SUBSEA-CABLE-NA",
            "company_name": "AFS 북미 해저케이블 생산법인안",
            "profile_role": "VIRTUAL_OVERSEAS_ENTITY",
            "source_profile_id": "AFS-DEMO-MATERIALS-GROUP",
            "industry_code": "C2830",
            "industry_name": "절연선·케이블 제조",
            "purpose": "북미 해상풍력용 해저케이블 현지생산의 수주·구리·투자·물류 영향 검증",
            "valid_until": "2032-12-31",
            "organization_blueprint": ["북미 생산법인", "프로젝트영업", "해저케이블공장", "항만출하센터"],
            "products": ["HVDC 해저케이블", "해상풍력 Array Cable", "접속재"],
            "recommended_apps": ["APP-01", "APP-03", "APP-04"],
            "default_assumptions": {
                "annual_capacity_km": 1800, "copper_price_change_pct": 10.0,
                "capex_krw_billion": 820.0, "local_content_pct": 55.0,
                "order_backlog_krw_billion": 1400.0,
            },
        },
    ]


def quarantine_fixture() -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """정상 데이터와 물리적으로 분리된 수집 단계 오류 예시를 만든다.

    이 후보들은 35개 CERTIFIED_FOR_DEMO CSV에 섞지 않는다. 등록기의
    QUARANTINE UX와 사유별 집계를 검증하기 위한 RAW 입력 예시다.
    """
    definitions = [
        ("UNMAPPED_SOURCE_CODE", "MDM-01", 5, "원천 품목 코드가 Crosswalk에 없음"),
        ("DUPLICATE_MILESTONE", "LOG-03", 3, "동일 선적·사건·시각의 중복"),
        ("CUSTOMS_CORRECTION", "LOG-04", 4, "통관 정정본의 선행 버전 연결 필요"),
        ("LATE_ACTUAL", "MFG-02", 8, "마감 이후 도착한 생산 실적"),
        ("UOM_MISMATCH_CANDIDATE", "PRC-02", 2, "계약 단위와 발주 단위 불일치"),
        ("QUALITY_HOLD_STOCK", "INV-01", 6, "품질 보류 재고의 가용 재고 제외 필요"),
        ("PRODUCTION_VARIANCE", "MFG-02", 10, "계획 대비 생산 편차 임계치 초과"),
        ("PARTNER_NOT_SUBMITTED", "LOG-01", 12, "파트너 필수 제출 미완료"),
    ]
    candidates: List[Dict[str, Any]] = []
    expected = []
    sequence = 1
    for reason, dataset_id, count, description in definitions:
        expected.append({"reason_code": reason, "source_dataset_id": dataset_id,
                         "expected_count": count, "description": description})
        for index in range(1, count + 1):
            candidates.append({
                "candidate_id": f"QTN-{sequence:04d}",
                "tenant_id": TENANT_ID,
                "scope_node_id": BUSINESSES[sequence % len(BUSINESSES)].plant_id,
                "data_class": "SYNTHETIC",
                "data_origin": "SYNTHETIC",
                "source_dataset_id": dataset_id,
                "source_record_key": f"DEMO-{dataset_id}-{index:04d}",
                "reason_code": reason,
                "reason_detail": description,
                "expected_disposition": "QUARANTINE",
                "raw_payload": json.dumps({"demo_sequence": sequence, "invalid_by_design": True},
                                          ensure_ascii=False, sort_keys=True),
            })
            sequence += 1
    manifest = {
        "kit_id": KIT_ID,
        "version": KIT_VERSION,
        "data_class": "SYNTHETIC",
        "purpose": "등록 전 QUARANTINE 분류와 사유 집계 검증",
        "must_not_enter_certified_demo": True,
        "expected_total": len(candidates),
        "expected_by_reason": expected,
    }
    return candidates, manifest


#: ⚠️ **모듈을 임포트하기만 해도 기본 조합이 채워져 있어야 한다.**
#:
#:   시험 일부는 `build()` 를 거치지 않고 `generate_materials(p)` 처럼 **함수를 직접
#:   부른다.** 게다가 `scripts.generate_...` 로 임포트하면 `generate_...` 와 **다른
#:   모듈 객체**가 되어 전역도 따로 논다. 분리(`a86a45295`) 이후 `BUSINESSES` 가 빈
#:   채로 남아 `i % len(BUSINESSES)` 가 ZeroDivisionError 를 냈고, 좁은 범위만
#:   돌려서 2026-09-17 재점검까지 몰랐다.
use_businesses(DEFAULT_BUSINESSES)


def build(clean: bool = True, force: bool = False, businesses=None,
          kit_id: str = "", kit_name: str = "") -> Dict[str, Any]:
    #: ★ 키트는 **사업의 조합**이다. 안 주면 기본 조합(제련 + 전지소재 = LS MnM 모델).
    use_businesses(businesses or DEFAULT_BUSINESSES, kit_id, kit_name)
    #: ★ `KIT_ROOT` 는 `KIT_ID` 로 조립된다 — 사업이 이름을 정한 **뒤에** 다시 잡는다.
    #:   `--out` 으로 경로를 직접 준 경우는 그대로 둔다.
    if _OUT_OVERRIDE is None:
        use_version(KIT_VERSION)
    # **확정 판본은 다시 만들지 않는다** (P1). 아래 `rmtree` 가 판본 디렉터리를 통째로
    # 지우므로, 검증이 끝난 판본에 이것을 돌리면 그 판본이 사라졌다가 다른 내용으로
    # 되살아난다. 실제로 1.0.0 이 그렇게 바뀌었고 아무 오류도 나지 않았다.
    kit_freeze.guard(str(KIT_ROOT), force=force)
    if clean and KIT_ROOT.exists():
        shutil.rmtree(KIT_ROOT)
    KIT_ROOT.mkdir(parents=True, exist_ok=True)
    all_profiles: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    file_index = []
    for profile_name, profile in PROFILES.items():
        datasets = generate_profile(profile)
        all_profiles[profile_name] = datasets
        for dataset_id in DATASETS:
            path = KIT_ROOT / "samples" / profile_name / f"{dataset_id}.csv"
            write_csv(path, datasets[dataset_id])
            file_index.append({"path": path.relative_to(KIT_ROOT).as_posix(), "sha256": sha256_file(path),
                               "rows": len(datasets[dataset_id]), "dataset_id": dataset_id, "profile": profile_name})
        write_json(KIT_ROOT / "golden_cases" / f"{profile_name}.expected_results.json", datasets["_GOLDEN"][0])

    full = all_profiles["full"]
    for dataset_id in DATASETS:
        contract_path = KIT_ROOT / "contracts" / f"{dataset_id}.contract.json"
        write_json(contract_path, make_contract(dataset_id, full[dataset_id]))
        file_index.append({"path": contract_path.relative_to(KIT_ROOT).as_posix(), "sha256": sha256_file(contract_path),
                           "dataset_id": dataset_id, "profile": "contract"})
    for row in full["SIM-02"]:
        write_json(KIT_ROOT / "scenarios" / f"{row['scenario_id']}.json", row)
    for app in app_blueprints():
        write_json(KIT_ROOT / "app_blueprints" / f"{app['app_id']}.json", app)
    for rpt in report_templates():
        write_json(KIT_ROOT / "reports" / f"{rpt['report_id']}.json", rpt)
    profiles = OVERLAY.apply_company_profiles(company_profiles())
    for profile in profiles:
        path = KIT_ROOT / "company_profiles" / f"{profile['company_profile_id']}.json"
        write_json(path, profile)
        file_index.append({"path": path.relative_to(KIT_ROOT).as_posix(), "sha256": sha256_file(path),
                           "rows": 1, "dataset_id": "COMPANY-PROFILE", "profile": "company-profile"})
    quarantine_rows, quarantine_manifest = quarantine_fixture()
    quarantine_csv = KIT_ROOT / "samples" / "full" / "quarantine" / "candidates.csv"
    write_csv(quarantine_csv, quarantine_rows)
    quarantine_manifest_path = KIT_ROOT / "samples" / "full" / "quarantine" / "expected_quarantine_manifest.json"
    write_json(quarantine_manifest_path, quarantine_manifest)
    file_index.extend([
        {"path": quarantine_csv.relative_to(KIT_ROOT).as_posix(), "sha256": sha256_file(quarantine_csv),
         "rows": len(quarantine_rows), "dataset_id": "QUARANTINE-CANDIDATES", "profile": "full-quarantine"},
        {"path": quarantine_manifest_path.relative_to(KIT_ROOT).as_posix(),
         "sha256": sha256_file(quarantine_manifest_path), "rows": len(quarantine_manifest["expected_by_reason"]),
         "dataset_id": "QUARANTINE-MANIFEST", "profile": "full-quarantine"},
    ])
    manifest = {
        "kit_id": KIT_ID, "version": KIT_VERSION, "status": "GENERATED_UNDER_VALIDATION",
        #: ★ 사람이 고르는 이름. 없으면 카탈로그가 `company_name` 을 대신 쓴다
        "kit_name": KIT_NAME,
        "company_profile_id": "AFS-DEMO-MATERIALS-GROUP", "company_name": company_name(),
        "entity_mode": "VIRTUAL", "data_class": "SYNTHETIC", "not_for_management_decision": True,
        #: ⚠️ `industry_codes`(KSIC)를 뺐다. 같은 황산니켈 제조라도 **켐코는 C2820,
        #:   LS MnM 사업부는 C24** 로 간다 — **법인 구조가 정하는 값**이지 키트 속성이
        #:   아니다. 분류와 잇는 열은 우리 좌표 `sector` 다.
        "sector": [b.sector for b in BUSINESSES],
        #: ★ 이 키트가 **어느 사업 정의에서 나왔나**(1.4.0). 재현·검증의 근거다
        "businesses": list(BUSINESS_CODES),
        "primary_use_case": USE_CASE,
        "profiles": {name: {k: v for k, v in vars(p).items()} for name, p in PROFILES.items()},
        "datasets": [{"dataset_id": ds, **DATASETS[ds], "required": ds not in {"KNW-01"}}
                     for ds in DATASETS],
        "dataset_count": len(DATASETS), "operational_baseline_count": 28,
        "app_blueprints": app_blueprints(), "report_templates": report_templates(),
        "company_profiles": [{"company_profile_id": p["company_profile_id"],
                              "company_name": p["company_name"],
                              "profile_role": p["profile_role"],
                              "industry_code": p["industry_code"]} for p in profiles],
        "company_profile_count": len(profiles),
        "scenario_ids": [f"SCN-{i:02d}" for i in range(1,11)],
        "generator": {"path": "scripts/generate_sample_company_starter_kit.py", "version": "1.0.0"},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_index": file_index,
    }
    manifest = OVERLAY.apply_manifest(manifest)
    write_json(KIT_ROOT / "manifest.json", manifest)
    readme = f"""# {KIT_ID} {KIT_VERSION}\n\n- 회사: AFS 데모소재그룹(명시적 가상기업)\n- 데이터: SYNTHETIC\n- 프로필: Quick 6개월, Full 36개월\n- 데이터셋: {len(DATASETS)}개\n- 주의: 실제 경영 의사결정과 예측 정확도 증명에 사용할 수 없습니다.\n\n1. 데이터 생성: `venv\\Scripts\\python.exe scripts\\generate_sample_company_starter_kit.py`\n2. 데이터 검증: `venv\\Scripts\\python.exe scripts\\validate_sample_company_starter_kit.py`\n3. Excel 생성: `venv\\Scripts\\python.exe scripts\\generate_sample_company_excel_templates.py`\n4. Excel 재계산: `powershell -ExecutionPolicy Bypass -File scripts\\recalculate_sample_company_excel_templates.ps1`\n5. Excel 검증: `venv\\Scripts\\python.exe scripts\\validate_sample_company_excel_templates.py`\n"""
    (KIT_ROOT / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.0.0",
                        help="만들 판본 (scripts/kit_defs/v{판본}.py 가 있어야 한다)")
    parser.add_argument("--out", default="",
                        help="다른 경로에 생성 — 동결 판본을 건드리지 않고 대조할 때 쓴다")
    parser.add_argument("--business", action="append", default=None, metavar="CODE",
                        help="담을 사업 (여러 번 줄 수 있다). 기본: "
                             + " + ".join(DEFAULT_BUSINESSES))
    parser.add_argument("--list-businesses", action="store_true", help="쓸 수 있는 사업을 보여준다")
    parser.add_argument("--no-clean", action="store_true", help="기존 키트 디렉터리를 지우지 않음")
    parser.add_argument("--force", action="store_true",
                        help="확정 판본이어도 덮어쓴다 — 왜 그래야 하는지 커밋에 남길 것")
    parser.add_argument("--kit-id", default="", metavar="ID",
                        help="키트 식별자. 사업이 여럿이면 필요하다(하나면 사업 정의가 준다)")
    parser.add_argument("--kit-name", default="", metavar="NAME",
                        help="카탈로그에 뜨는 이름. `--kit-id` 와 함께 준다")
    args = parser.parse_args()
    if args.list_businesses:
        for c in business_defs.available():
            d = business_defs.load([c])[0]
            print("%-24s %-10s %-30s %s" % (c, d.name, d.kit_id, d.sector))
        return
    use_version(args.version, Path(args.out) if args.out else None)
    manifest = build(clean=not args.no_clean, force=args.force, businesses=args.business,
                     kit_id=args.kit_id, kit_name=args.kit_name)
    print(json.dumps({"status": "generated", "version": args.version,
                      "kit_id": KIT_ID, "kit_name": KIT_NAME,
                      "businesses": [b.code for b in BUSINESSES],
                      "kit_root": str(KIT_ROOT),
                      "dataset_count": manifest["dataset_count"],
                      "quick_rows": sum(x.get("rows",0) for x in manifest["file_index"] if x.get("profile")=="quick"),
                      "full_rows": sum(x.get("rows",0) for x in manifest["file_index"] if x.get("profile")=="full")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
