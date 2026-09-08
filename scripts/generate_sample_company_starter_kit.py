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
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
KIT_ID = "KIT-MFG-NONFERROUS-PROCUREMENT"
KIT_VERSION = "1.0.0"
KIT_ROOT = ROOT / "starter_kits" / KIT_ID / KIT_VERSION
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
    nodes = [
        (GROUP_SCOPE, "ENTERPRISE_GROUP", "AFS_GROUP", "AFS 데모소재그룹", "", "VIRTUAL"),
        (METALS_SCOPE, "LEGAL_ENTITY", "AFS_METALS", "AFS 메탈 주식회사", GROUP_SCOPE, "VIRTUAL"),
        ("org-afs-metals-shared", "SHARED_SERVICE", "METALS_SHARED", "AFS 메탈 전사공통", METALS_SCOPE, "VIRTUAL"),
        ("org-afs-smelting-bu", "BUSINESS_DIVISION", "SMELTING_BU", "제련사업부", METALS_SCOPE, "VIRTUAL"),
        (PLANT1, "PLANT", "SMELTING_P1", "제1공장(제련·정제)", "org-afs-smelting-bu", "VIRTUAL"),
        (ADV_SCOPE, "LEGAL_ENTITY", "AFS_ADVANCED", "AFS 첨단소재 주식회사", GROUP_SCOPE, "VIRTUAL"),
        ("org-afs-advanced-shared", "SHARED_SERVICE", "ADV_SHARED", "AFS 첨단소재 전사공통", ADV_SCOPE, "VIRTUAL"),
        ("org-afs-battery-bu", "BUSINESS_DIVISION", "BATTERY_BU", "배터리소재사업부", ADV_SCOPE, "VIRTUAL"),
        (PLANT2, "PLANT", "BATTERY_P2", "제2공장(황산니켈)", "org-afs-battery-bu", "VIRTUAL"),
        (PLANT3, "PLANT", "EXPANSION_P3", "증설 제3공장", "org-afs-battery-bu", "VIRTUAL_EXPANSION"),
        ("dept-procurement", "DEPARTMENT", "PROC", "원료구매팀", "org-afs-battery-bu", "VIRTUAL"),
        ("dept-logistics", "DEPARTMENT", "LOG", "물류팀", "org-afs-battery-bu", "VIRTUAL"),
        ("dept-production", "DEPARTMENT", "MFG", "생산관리팀", "org-afs-battery-bu", "VIRTUAL"),
        ("dept-finance", "DEPARTMENT", "FIN", "재무회계팀", "org-afs-advanced-shared", "VIRTUAL"),
        ("dept-management", "DEPARTMENT", "MGT", "경영관리팀", "org-afs-advanced-shared", "VIRTUAL"),
    ]
    if profile.name == "quick":
        keep = {GROUP_SCOPE, ADV_SCOPE, "org-afs-battery-bu", PLANT2,
                "dept-procurement", "dept-logistics", "dept-management"}
        nodes = [n for n in nodes if n[0] in keep]
        parent_map = {ADV_SCOPE: GROUP_SCOPE, "org-afs-battery-bu": ADV_SCOPE, PLANT2: "org-afs-battery-bu",
                      "dept-procurement": "org-afs-battery-bu", "dept-logistics": "org-afs-battery-bu",
                      "dept-management": ADV_SCOPE}
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
    fixed = [
        ("RM-CU-CONC", "동정광", "RAW", "TON", PLANT1, "LME_COPPER"),
        ("RM-MHP", "니켈 MHP", "RAW", "TON", PLANT2, "NICKEL"),
        ("RM-H2SO4", "황산 98%", "RAW", "TON", PLANT2, "SULFURIC_ACID"),
        ("RM-LIME", "소석회", "RAW", "TON", PLANT2, "INDUSTRIAL_CHEMICAL"),
        ("WIP-MATTE", "동 매트", "WIP", "TON", PLANT1, ""),
        ("WIP-ANODE", "아노드동", "WIP", "TON", PLANT1, ""),
        ("WIP-NISO4", "조황산니켈 용액", "WIP", "TON", PLANT2, ""),
        ("FG-CATHODE", "전기동", "FINISHED", "TON", PLANT1, "COPPER"),
        ("FG-NISO4", "고순도 황산니켈", "FINISHED", "TON", PLANT2, "NICKEL_SULFATE"),
        ("FG-LIOH", "배터리급 수산화리튬", "FINISHED", "TON", PLANT2, "LITHIUM"),
        ("BP-H2SO4", "부산물 황산", "BYPRODUCT", "TON", PLANT1, "SULFURIC_ACID"),
        ("BP-GOLD", "부산물 금", "BYPRODUCT", "KG", PLANT1, "GOLD"),
    ]
    rows = []
    for code, name, typ, uom, scope, benchmark in fixed:
        rows.append({"material_id": code, "material_code": code, "material_name": name,
                     "aliases": f"{name}|{code.replace('-', ' ')}", "material_type": typ,
                     "grade": "DEMO_STANDARD", "base_uom": uom, "valuation_class": typ,
                     "benchmark_code": benchmark, "active": True, "_scope": scope})
    categories = ["원료첨가제", "공정소모품", "포장재", "예비품", "중간재", "완제품"]
    while len(rows) < profile.materials:
        i = len(rows) + 1
        cat = categories[i % len(categories)]
        typ = "RAW" if i % 6 < 2 else "CONSUMABLE" if i % 6 < 4 else "WIP" if i % 6 == 4 else "FINISHED"
        scope = PLANT1 if i % 2 == 0 else PLANT2
        code = f"MAT-{typ[:2]}-{i:04d}"
        rows.append({"material_id": code, "material_code": code, "material_name": f"{cat} {i:03d}",
                     "aliases": f"{cat}{i:03d}|DEMO-{i:03d}", "material_type": typ,
                     "grade": f"G{1+i%4}", "base_uom": "TON" if typ != "CONSUMABLE" else "EA",
                     "valuation_class": typ, "benchmark_code": "", "active": i % 23 != 0,
                     "_scope": scope})
    return stamp("MDM-01", rows[:profile.materials], kind="REFERENCE")


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
    all_rows = [
        ("LOC-P1-RAW", PLANT1, "원료창고", "RAW", 80000), ("LOC-P1-WIP", PLANT1, "공정재고", "WIP", 40000),
        ("LOC-P1-FG", PLANT1, "제품창고", "FINISHED", 30000), ("LOC-P2-RAW", PLANT2, "원료창고", "RAW", 45000),
        ("LOC-P2-QI", PLANT2, "품질검사창고", "QUALITY", 8000), ("LOC-P2-WIP", PLANT2, "공정재고", "WIP", 18000),
        ("LOC-P2-FG", PLANT2, "제품창고", "FINISHED", 22000), ("LOC-P3-SIM", PLANT3, "가상 증설창고", "VIRTUAL", 35000),
    ]
    if profile.name == "quick":
        # Quick 프로필도 두 실제 사업 범위의 입고 목적지를 모두 포함해야 한다.
        # 그렇지 않으면 구매·물류 데이터가 존재하지 않는 창고를 참조하게 된다.
        quick_ids = {"LOC-P1-RAW", "LOC-P1-FG", "LOC-P2-RAW", "LOC-P2-FG"}
        all_rows = [r for r in all_rows if r[0] in quick_ids]
    rows = [{"location_id": a, "site_id": b, "location_name": c, "storage_type": d,
             "capacity_quantity": e, "capacity_uom": "TON", "active": d != "VIRTUAL", "_scope": b}
            for a, b, c, d, e in all_rows]
    return stamp("MDM-04", rows, kind="REFERENCE")


def generate_bom(profile: Profile, materials: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    recipes = {
        "FG-CATHODE": [("RM-CU-CONC", 3.30, "INPUT"), ("WIP-MATTE", 0.02, "RETURN")],
        "FG-NISO4": [("RM-MHP", 1.15, "INPUT"), ("RM-H2SO4", 0.32, "INPUT"), ("RM-LIME", 0.08, "INPUT")],
        "FG-LIOH": [("RM-H2SO4", 0.12, "INPUT"), ("RM-LIME", 0.05, "INPUT")],
    }
    product_ids = [m["material_id"] for m in materials if m["material_type"] == "FINISHED"]
    raw_ids = [m["material_id"] for m in materials if m["material_type"] in {"RAW", "CONSUMABLE"}]
    rows = []
    target = 8 if profile.name == "quick" else 30
    # target은 상한이다. 품목 수를 넘겨 순회하면 같은 기간·같은 배합의
    # -02 BOM이 생겨 제품 Resolver가 대체판 충돌로 거부한다.
    for pidx in range(min(target, len(product_ids))):
        product = product_ids[pidx % len(product_ids)]
        lines = recipes.get(product) or [(raw_ids[pidx % len(raw_ids)], 1.05 + (pidx % 5) * 0.03, "INPUT")]
        for line_no, (inp, qty, role) in enumerate(lines, 1):
            rows.append({"bom_id": f"BOM-{product}-{pidx//max(1,len(product_ids))+1:02d}", "line_no": line_no,
                         "output_material_id": product, "input_material_id": inp, "component_role": role,
                         "quantity_per_output": qty, "input_uom": "TON", "output_uom": "TON",
                         "standard_yield": 0.98 if product == "FG-CATHODE" else 0.94,
                         "byproduct_material_id": "BP-H2SO4" if product == "FG-CATHODE" else "",
                         "effective_from": "2024-01-01", "effective_to": "9999-12-31",
                         "_scope": PLANT1 if product == "FG-CATHODE" else PLANT2})
    return stamp("MDM-05", rows, kind="REFERENCE")


def generate_routing(profile: Profile, materials: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    products = [m["material_id"] for m in materials if m["material_type"] == "FINISHED"] or ["FG-NISO4"]
    ops = ["원료준비", "침출·용해", "정제", "결정화", "건조·포장"]
    rows = []
    for i in range(profile.equipments):
        product = products[i % len(products)]
        op_seq = (i % len(ops) + 1) * 10
        scope = PLANT1 if product == "FG-CATHODE" else PLANT2
        rows.append({"routing_id": f"ROUTE-{product}", "operation_seq": op_seq,
                     "operation_name": ops[i % len(ops)], "equipment_id": f"EQ-{scope[-2:]}-{i+1:03d}",
                     "equipment_name": f"{ops[i%len(ops)]} 설비 {i+1:02d}", "product_id": product,
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
                                          ("INDUSTRIAL_POWER", power, "KRW/KWH", PLANT2),
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
                       ext2: Sequence[Mapping[str, Any]], rng: random.Random) -> List[Dict[str, Any]]:
    raw = [m for m in materials if m["material_type"] in {"RAW", "CONSUMABLE"} and m["active"]]
    prices = latest_indicator(ext2, "commodity_code")
    rows = []
    for i in range(profile.contracts):
        supplier = suppliers[i % len(suppliers)]
        mat = raw[i % len(raw)]
        benchmark = mat.get("benchmark_code") or "NICKEL"
        if benchmark not in prices:
            benchmark = "NICKEL"
        scope = mat["scope_node_id"]
        rows.append({"contract_id": f"CTR-{i+1:05d}", "supplier_id": supplier["supplier_id"],
                     "material_id": mat["material_id"], "contract_quantity": round(10000 + (i % 10)*2500, 3),
                     "ordered_quantity": 0.0, "quantity_uom": mat["base_uom"], "benchmark_code": benchmark,
                     "benchmark_price": round(prices[benchmark], 2), "premium_rate": round(-0.02 + (i%9)*0.008, 4),
                     "currency": supplier["currency"], "incoterm": ["CIF", "FOB", "CFR"][i%3],
                     "payment_terms": supplier["payment_terms"], "valid_from": "2024-01-01", "valid_to": "2027-12-31",
                     "price_formula": "BENCHMARK_PRICE*(1+PREMIUM_RATE)", "_scope": scope})
    return stamp("PRC-01", rows, kind="ACTUAL")


def generate_purchase_and_logistics(profile: Profile, contracts: List[Dict[str, Any]], suppliers: Sequence[Mapping[str, Any]],
                                    start: date, end: date, rng: random.Random) -> tuple[List[Dict[str, Any]], ...]:
    po_rows, submission_rows, shipment_rows, milestone_rows, customs_rows, transport_rows = [], [], [], [], [], []
    span = max(1, (end - start).days)
    shipment_po_indexes = set(rng.sample(range(profile.purchase_orders), min(profile.shipments, profile.purchase_orders)))
    contract_ordered: Dict[str, float] = defaultdict(float)
    supplier_by_id = {s["supplier_id"]: s for s in suppliers}
    for i in range(profile.purchase_orders):
        c = contracts[i % len(contracts)]
        order_date = start + timedelta(days=(i * 17 + i//7) % span)
        lead = int(supplier_by_id[c["supplier_id"]]["lead_time_days"])
        due_date = order_date + timedelta(days=lead)
        quantity = round(15 + (i % 11) * 4.5, 3)
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
                                   "destination_location_id": "LOC-P1-RAW" if c["scope_node_id"] == PLANT1 else "LOC-P2-RAW",
                                   "delivered_quantity": quantity if event == "DELIVERED" else 0.0,
                                   "quantity_uom": c["quantity_uom"], "status": "COMPLETED", "_scope": c["scope_node_id"]})
    for c in contracts:
        c["ordered_quantity"] = round(contract_ordered[c["contract_id"]], 3)
    return (stamp("PRC-02", po_rows, kind="ACTUAL"), stamp("LOG-01", submission_rows, kind="ACTUAL"),
            stamp("LOG-02", shipment_rows, kind="ACTUAL"), stamp("LOG-03", milestone_rows, kind="ACTUAL"),
            stamp("LOG-04", customs_rows, kind="ACTUAL"), stamp("LOG-05", transport_rows, kind="ACTUAL"))


def generate_sales(profile: Profile, customers: Sequence[Mapping[str, Any]], products: Sequence[str],
                   start: date, end: date, rng: random.Random) -> List[Dict[str, Any]]:
    span = max(1, (end-start).days)
    rows = []
    for i in range(profile.sales_lines):
        order_date = start + timedelta(days=(i*13 + i//9) % span)
        due = order_date + timedelta(days=20 + i%25)
        actual = due + timedelta(days=2 if i%31==0 else rng.randint(-2, 2))
        product = products[i % len(products)]
        qty = round(8 + (i%17)*1.7, 3)
        price = round((24000 if product == "FG-NISO4" else 9500 if product == "FG-CATHODE" else 32000) * (0.95 + (i%9)*0.012), 2)
        customer = customers[i % len(customers)]
        rows.append({"sales_line_id": f"SO-{i+1:06d}-10", "customer_id": customer["customer_id"],
                     "product_id": product, "order_date": iso(order_date), "due_date": iso(due),
                     "actual_ship_date": iso(actual), "plan_quantity": qty, "order_quantity": qty,
                     "shipped_quantity": qty, "quantity_uom": "TON", "unit_price": price,
                     "currency": customer["currency"], "status": "SHIPPED",
                     "_scope": PLANT1 if product == "FG-CATHODE" else PLANT2})
    return stamp("SLS-01", rows, kind="ACTUAL")


def generate_plans_batches_events(profile: Profile, bom: Sequence[Mapping[str, Any]], routing: Sequence[Mapping[str, Any]],
                                  sales: Sequence[Mapping[str, Any]], start: date, end: date,
                                  rng: random.Random) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    products = sorted({str(b["output_material_id"]) for b in bom})
    bom_by_product: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for b in bom:
        bom_by_product[str(b["output_material_id"])].append(b)
    span = max(1, (end-start).days)
    plans = []
    for i in range(profile.production_plans):
        product = products[i % len(products)]
        d = start + timedelta(days=(i*5 + i//11) % span)
        qty = round(10 + (i%19)*2.1, 3)
        requirement = round(sum(float(x["quantity_per_output"]) for x in bom_by_product[product]) * qty, 3)
        scope = PLANT1 if product == "FG-CATHODE" else PLANT2
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


def generate_movements_and_snapshots(profile: Profile, logistics: Sequence[Mapping[str, Any]], shipments: Sequence[Mapping[str, Any]],
                                     purchase_orders: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]],
                                     sales: Sequence[Mapping[str, Any]], materials: Sequence[Mapping[str, Any]],
                                     locations: Sequence[Mapping[str, Any]], start: date, end: date,
                                     rng: random.Random) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    po_by_line = {p["po_line_id"]: p for p in purchase_orders}
    shp_by_id = {s["shipment_id"]: s for s in shipments}
    movements: List[Dict[str, Any]] = []
    balances: Dict[tuple[str, str], float] = defaultdict(float)
    active_locations = [l for l in locations if str(l["active"]).lower() == "true"]
    material_ids = [m["material_id"] for m in materials]
    # Opening stock keeps production and sales movement sequences physically possible.
    for idx, m in enumerate(materials):
        loc = "LOC-P1-RAW" if m["scope_node_id"] == PLANT1 and m["material_type"] == "RAW" else \
              "LOC-P1-FG" if m["scope_node_id"] == PLANT1 else \
              "LOC-P2-FG" if m["material_type"] == "FINISHED" else "LOC-P2-RAW"
        matches = [l for l in active_locations if l["location_id"] == loc and l["tenant_id"] == m["tenant_id"]]
        if len(matches) != 1 or matches[0]["scope_node_id"] != m["scope_node_id"]:
            raise ValueError(f"Opening warehouse unavailable or outside material scope: {loc}")
        qty = 2000.0 if m["material_type"] == "RAW" else 800.0 if m["material_type"] == "FINISHED" else 100.0
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
        raw_loc = "LOC-P1-RAW" if b["site_id"] == PLANT1 else "LOC-P2-RAW"
        fg_loc = "LOC-P1-FG" if b["site_id"] == PLANT1 else "LOC-P2-FG"
        movements.append({"movement_id": f"MOV-ISS-{b['batch_id']}", "movement_date": b["production_date"],
                          "movement_type": "PRODUCTION_ISSUE", "material_id": b["input_material_id"],
                          "lot_id": b["input_lot_id"], "from_location_id": raw_loc, "to_location_id": "PRODUCTION",
                          "quantity": -float(b["input_quantity"]), "quantity_uom": b["quantity_uom"],
                          "reference_type": "BATCH", "reference_id": b["batch_id"], "_scope": b["site_id"]})
        movements.append({"movement_id": f"MOV-RCP-{b['batch_id']}", "movement_date": b["production_date"],
                          "movement_type": "PRODUCTION_RECEIPT", "material_id": b["output_material_id"],
                          "lot_id": b["output_lot_id"], "from_location_id": "PRODUCTION", "to_location_id": fg_loc,
                          "quantity": float(b["output_quantity"]), "quantity_uom": b["quantity_uom"],
                          "reference_type": "BATCH", "reference_id": b["batch_id"], "_scope": b["site_id"]})
    for s in sales:
        loc = "LOC-P1-FG" if s["scope_node_id"] == PLANT1 else "LOC-P2-FG"
        movements.append({"movement_id": f"MOV-SO-{s['sales_line_id']}", "movement_date": s["actual_ship_date"],
                          "movement_type": "SALES_SHIPMENT", "material_id": s["product_id"],
                          "lot_id": f"LOT-SALES-{s['sales_line_id']}", "from_location_id": loc, "to_location_id": "CUSTOMER",
                          "quantity": -float(s["shipped_quantity"]), "quantity_uom": s["quantity_uom"],
                          "reference_type": "SALES_ORDER", "reference_id": s["sales_line_id"], "_scope": s["scope_node_id"]})
    # Add controlled transfer/adjustment events so Full has operational density without breaking conservation.
    target = 5000 if profile.name == "quick" else 30000
    i = 0
    while len(movements) < target:
        mat = material_ids[i % len(material_ids)]
        loc = active_locations[i % len(active_locations)]["location_id"]
        d = start + timedelta(days=(i*7) % max(1,(end-start).days))
        qty = round(0.05 + (i%9)*0.03, 3)
        movements.append({"movement_id": f"MOV-ADJ-{i+1:07d}", "movement_date": iso(d),
                          "movement_type": "CYCLE_COUNT_ADJUSTMENT", "material_id": mat, "lot_id": f"LOT-ADJ-{i+1:07d}",
                          "from_location_id": "ADJUSTMENT", "to_location_id": loc, "quantity": qty,
                          "quantity_uom": "TON", "reference_type": "CYCLE_COUNT", "reference_id": f"CC-{i+1:07d}",
                          "_scope": PLANT1 if "P1" in loc else PLANT2})
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
            if m["movement_type"] == "PRODUCTION_ISSUE" or m["movement_type"] == "SALES_SHIPMENT":
                loc = m["from_location_id"]
            else:
                loc = m["to_location_id"]
            if loc not in {"", "PRODUCTION", "CUSTOMER", "IN_TRANSIT", "ADJUSTMENT"}:
                current[(m["material_id"], loc)] += qty
            idx += 1
        for mat in material_ids:
            relevant = [l["location_id"] for l in active_locations]
            for loc in relevant:
                qty = round(current[(mat, loc)], 3)
                snapshots.append({"snapshot_id": f"STK-{cutoff:%Y%m%d}-{mat}-{loc}", "snapshot_date": iso(cutoff),
                                  "location_id": loc, "material_id": mat, "lot_id": "ALL",
                                  "unrestricted_quantity": qty, "quality_quantity": 0.0, "blocked_quantity": 0.0,
                                  "safety_stock_quantity": 50.0 if mat.startswith("RM-") else 10.0,
                                  "quantity_uom": "TON", "_scope": PLANT1 if "P1" in loc else PLANT2})
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
                             "currency": "USD", "quantity_uom": "TON", "_scope": PLANT1 if product == "FG-CATHODE" else PLANT2})
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
                                "_scope": GROUP_SCOPE} for a,b,c,d,e,f in driver_defs],
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
                                 for a,b,c,d,e,f in scenarios_def], kind="SCENARIO", default_scope=GROUP_SCOPE)
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
    products = [m["material_id"] for m in datasets["MDM-01"] if m["material_type"] == "FINISHED"]
    datasets["MDM-02"] = generate_suppliers(profile, datasets["MDM-01"], rng)
    datasets["MDM-03"] = generate_customers(profile, products)
    datasets["MDM-04"] = generate_locations(profile)
    datasets["MDM-05"] = generate_bom(profile, datasets["MDM-01"])
    datasets["MDM-06"] = generate_routing(profile, datasets["MDM-01"])
    datasets["MDM-07"] = generate_accounts(profile)
    datasets["MDM-08"] = generate_trade_refs(profile)
    datasets["EXT-01"], datasets["EXT-02"], datasets["EXT-03"] = generate_external(profile, start, rng)
    datasets["PRC-01"] = generate_contracts(profile, datasets["MDM-02"], datasets["MDM-01"], datasets["EXT-02"], rng)
    (datasets["PRC-02"], datasets["LOG-01"], datasets["LOG-02"], datasets["LOG-03"],
     datasets["LOG-04"], datasets["LOG-05"]) = generate_purchase_and_logistics(
        profile, datasets["PRC-01"], datasets["MDM-02"], start, end, rng)
    datasets["SLS-01"] = generate_sales(profile, datasets["MDM-03"], products, start, end, rng)
    datasets["MFG-01"], datasets["MFG-02"], datasets["MFG-03"] = generate_plans_batches_events(
        profile, datasets["MDM-05"], datasets["MDM-06"], datasets["SLS-01"], start, end, rng)
    datasets["INV-02"], datasets["INV-01"] = generate_movements_and_snapshots(
        profile, datasets["LOG-05"], datasets["LOG-02"], datasets["PRC-02"], datasets["MFG-02"],
        datasets["SLS-01"], datasets["MDM-01"], datasets["MDM-04"], start, end, rng)
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
                "scope_node_id": PLANT2 if sequence % 2 else PLANT1,
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


def build(clean: bool = True) -> Dict[str, Any]:
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
    profiles = company_profiles()
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
        "company_profile_id": "AFS-DEMO-MATERIALS-GROUP", "company_name": "AFS 데모소재그룹",
        "entity_mode": "VIRTUAL", "data_class": "SYNTHETIC", "not_for_management_decision": True,
        "industry_codes": ["C24"], "primary_use_case": "원료 구매·도입계획에서 경영 영향과 실행 결정까지",
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
    write_json(KIT_ROOT / "manifest.json", manifest)
    readme = f"""# {KIT_ID} {KIT_VERSION}\n\n- 회사: AFS 데모소재그룹(명시적 가상기업)\n- 데이터: SYNTHETIC\n- 프로필: Quick 6개월, Full 36개월\n- 데이터셋: {len(DATASETS)}개\n- 주의: 실제 경영 의사결정과 예측 정확도 증명에 사용할 수 없습니다.\n\n1. 데이터 생성: `venv\\Scripts\\python.exe scripts\\generate_sample_company_starter_kit.py`\n2. 데이터 검증: `venv\\Scripts\\python.exe scripts\\validate_sample_company_starter_kit.py`\n3. Excel 생성: `venv\\Scripts\\python.exe scripts\\generate_sample_company_excel_templates.py`\n4. Excel 재계산: `powershell -ExecutionPolicy Bypass -File scripts\\recalculate_sample_company_excel_templates.ps1`\n5. Excel 검증: `venv\\Scripts\\python.exe scripts\\validate_sample_company_excel_templates.py`\n"""
    (KIT_ROOT / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-clean", action="store_true", help="기존 키트 디렉터리를 지우지 않음")
    args = parser.parse_args()
    manifest = build(clean=not args.no_clean)
    print(json.dumps({"status": "generated", "kit_root": str(KIT_ROOT),
                      "dataset_count": manifest["dataset_count"],
                      "quick_rows": sum(x.get("rows",0) for x in manifest["file_index"] if x.get("profile")=="quick"),
                      "full_rows": sum(x.get("rows",0) for x in manifest["file_index"] if x.get("profile")=="full")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
