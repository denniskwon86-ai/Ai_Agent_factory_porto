"""부서 초기 적재 + 소유권 미러 재구축 (설계서 Phase 1).

⚠️ 왜 시드가 필요한가:
  부서 정보가 `factory_control.py` 안에 **하드코딩된 딕셔너리 3개**로 흩어져 있었다
  (`domain_agents_map` / `domain_templates_map` / `domain_ko_map`).
  그래서 부서를 하나 추가·개명·이동·폐지하려면 **코드를 고치고 배포**해야 했고,
  세 맵이 서로 어긋나도 아무도 알아채지 못했다(한 곳에만 추가하면 조용히 누락).
  → 부서를 기준정보로 옮기고, 코드에서는 조회만 한다. 이 시드는 그 최초 1회 이전이며 멱등하다.
"""
import json
import os
from typing import Any, Dict, List

from core.org_directory import org_directory

# 코드에 박혀 있던 부서 정의를 한 곳에 모은 이관 원천.
# 시드가 끝나면 `factory_control.py` 의 맵 3개는 제거되고 여기만 남는다(그마저도 최초 1회용).
_LEGACY_DEPARTMENTS: List[Dict[str, Any]] = [
    {"dept_id": "sales",       "name_ko": "영업",     "template": "manufacturing-market-forecast",
     "agents": ["Sales_Agent"],      "domains": ["kpi", "finance_param"]},
    {"dept_id": "procurement", "name_ko": "구매",     "template": "manufacturing-cost-analysis",
     "agents": ["Purchase_Agent"],   "domains": ["material", "bom"]},
    {"dept_id": "production",  "name_ko": "생산",     "template": "manufacturing-production",
     "agents": ["Production_Agent"], "domains": ["equipment", "bom", "simulation_node"]},
    {"dept_id": "quality",     "name_ko": "품질",     "template": "manufacturing-qc",
     "agents": ["Quality_Agent"],    "domains": ["quality_spec", "sensor_spec"]},
    {"dept_id": "logistics",   "name_ko": "물류",     "template": "manufacturing-production",
     "agents": ["Logistics_Agent"],  "domains": ["material"]},
    {"dept_id": "marketing",   "name_ko": "마케팅",   "template": "content-marketing",
     "agents": ["Marketing_Agent"],  "domains": ["kpi"]},
    {"dept_id": "finance",     "name_ko": "재무",     "template": "manufacturing-cost-analysis",
     "agents": ["Finance_Agent"],    "domains": ["finance_param", "kpi"]},
    {"dept_id": "accounting",  "name_ko": "회계",     "template": "manufacturing-cost-analysis",
     "agents": ["Finance_Agent"],    "domains": ["finance_param"]},
]

_ROOT = {"dept_id": "hq", "name_ko": "본사"}


def ensure_department_entity_type() -> bool:
    """`entity_types` 에 `department` 를 멱등 등록.

    온톨로지·크로스워크가 부서를 참조할 수 있고, 기준정보 화면과 같은 거버넌스 아래 놓인다."""
    from core.master_data import master_data
    if master_data.get_type("department"):
        return False
    master_data.create_type(
        type_id="department",
        name_ko="부서(조직)",
        description=("조직 계층의 부서. 산출물 소유·권한 상속의 단위이며 개편 이력이 보존된다. "
                     "실제 레코드는 org_directory 의 departments 테이블이 관리한다."),
        attr_schema={"dept_id": "str", "parent_id": "str", "path": "str"},
    )
    return True


def seed_departments() -> Dict[str, Any]:
    """하드코딩되어 있던 부서를 `departments` 로 적재(멱등).

    이미 등록된 부서는 건드리지 않는다 — 운영 중 개편본을 시드가 덮어쓰면 안 된다."""
    ensure_department_entity_type()
    created, skipped = [], []

    if not org_directory.get_department(_ROOT["dept_id"]):
        org_directory.create_department(_ROOT["dept_id"], _ROOT["name_ko"])
        created.append(_ROOT["dept_id"])
    else:
        skipped.append(_ROOT["dept_id"])

    for d in _LEGACY_DEPARTMENTS:
        if org_directory.get_department(d["dept_id"]):
            skipped.append(d["dept_id"])
            continue
        org_directory.create_department(
            dept_id=d["dept_id"], name_ko=d["name_ko"], parent_id=_ROOT["dept_id"],
            master_domains=d.get("domains", []), default_template_id=d.get("template", ""),
            domain_agents=d.get("agents", []), legacy_domain=d["dept_id"],
            aliases=[d["name_ko"]])
        created.append(d["dept_id"])
    return {"created": created, "skipped": skipped, "total": len(created) + len(skipped)}


def resolve_department_config(domain_key: str) -> Dict[str, Any]:
    """도메인 키(구 하드코딩 맵의 키)로 부서 설정을 조회한다.

    `factory_control.create_mega_project` 가 맵 3개 대신 이 함수를 쓴다.
    미등록 부서면 빈 설정을 돌려주므로 호출부는 기존처럼 기본값으로 동작한다(오차단 방지)."""
    d = org_directory.get_department(domain_key)
    if not d or d.get("status") != "active":
        return {"name_ko": domain_key, "template_id": "", "agents": [], "master_domains": []}
    return {
        "name_ko": d.get("name_ko") or domain_key,
        "template_id": d.get("default_template_id") or "",
        "agents": d.get("domain_agents") or [],
        "master_domains": d.get("master_domains") or [],
    }


def reconcile_ownership(projects_dir: str = "projects", library_dir: str = "library") -> Dict[str, Any]:
    """파일에서 `ownership` 미러를 재구축한다.

    진실원본은 `project_meta.json` / `release.json` 이고 이 테이블은 **검색 가능한 인덱스**다.
    목록 API 가 전량 디렉터리 스캔이라 거기에 부서 필터·정렬을 얹을 수 없어 미러가 필요하다."""
    n_proj = n_rel = 0

    if os.path.isdir(projects_dir):
        for pid in os.listdir(projects_dir):
            meta_path = os.path.join(projects_dir, pid, "project_meta.json")
            if not os.path.isfile(meta_path):
                continue
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f) or {}
            except Exception:
                continue
            org_directory.set_ownership(
                "project", pid,
                dept_id=str(meta.get("dept_id", "") or ""),
                owner_user_id=str(meta.get("owner_user_id", "") or ""),
                visibility=str(meta.get("visibility", "dept") or "dept"),
                nature=str(meta.get("nature", "") or ""))
            n_proj += 1

    if os.path.isdir(library_dir):
        for rid in os.listdir(library_dir):
            rel_path = os.path.join(library_dir, rid, "release.json")
            if not os.path.isfile(rel_path):
                continue
            try:
                with open(rel_path, encoding="utf-8") as f:
                    rel = json.load(f) or {}
            except Exception:
                continue
            org_directory.set_ownership(
                "release", rid,
                dept_id=str(rel.get("dept_id", "") or ""),
                owner_user_id=str(rel.get("owner_user_id", "") or ""),
                visibility=str(rel.get("visibility", "dept") or "dept"))
            n_rel += 1

    return {"projects": n_proj, "releases": n_rel}
