#!/usr/bin/env python3
"""Starter Kit 가상회사 5종을 Enterprise Context에 멱등 등록한다.

가상회사는 반드시 REAL 원본의 격리 복제로만 생성하며 거래·자격증명은 복사하지 않는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.enterprise_context.clone_service import clone_service
from core.enterprise_context.models import EnterpriseProfile
from core.enterprise_context.repository import ecm_repository
from scripts.generate_sample_company_starter_kit import company_profiles


TENANT_ID = "tenant_default"
ACTOR = "starter-kit-seed"
SOURCE_CODE = {
    "AFS-VIRTUAL-BATTERY-EXPANSION-2030": "MNM_BATTERY",
    "AFS-VIRTUAL-CIRCULAR-METALS": "MNM_COPPER",
    "AFS-VIRTUAL-GLOBAL-SMELTING": "LS_MNM",
    "AFS-VIRTUAL-SMART-POWER": "LS_ELECTRIC",
    "AFS-VIRTUAL-SUBSEA-CABLE-NA": "LS_CABLE",
}


def seed() -> dict:
    existing = {
        entity.name_ko: entity
        for entity in ecm_repository.list_entities(tenant_id=TENANT_ID, entity_mode="VIRTUAL")
    }
    results = []
    for profile in company_profiles():
        profile_id = profile["company_profile_id"]
        if profile_id not in SOURCE_CODE:
            continue
        name = profile["company_name"]
        if name in existing:
            results.append({"company_profile_id": profile_id, "company_name": name,
                            "status": "skipped", "entity_id": existing[name].entity_id})
            continue

        source_code = SOURCE_CODE[profile_id]
        source_node = ecm_repository.find_node_by_code(
            source_code, tenant_id=TENANT_ID, entity_mode="REAL"
        )
        if not source_node:
            results.append({"company_profile_id": profile_id, "company_name": name,
                            "status": "blocked", "reason": f"REAL 원본 코드 없음: {source_code}"})
            continue

        scenario = clone_service.clone_to_virtual(
            base_entity_id=source_node.entity_id,
            name_ko=name,
            purpose=profile["purpose"],
            valid_until=profile["valid_until"],
            actor=ACTOR,
            tenant_id=TENANT_ID,
            assumption_set_id=f"starter:{profile_id}",
            copy={"org_nodes": True, "profiles": True, "process_kpi": False,
                  "catalog": False, "snapshots": False},
        )
        virtual_nodes = [
            node for node in ecm_repository.list_nodes(tenant_id=TENANT_ID)
            if node.entity_id == scenario["entity_id"]
        ]
        root = next((node for node in virtual_nodes if node.code.endswith("_" + source_code)),
                    virtual_nodes[0] if virtual_nodes else None)
        if root:
            ecm_repository.upsert_profile(EnterpriseProfile(
                tenant_id=TENANT_ID,
                scope_node_id=root.node_id,
                industry_code=profile["industry_code"],
                profile_kind="business_profile",
                payload={
                    "starter_company_profile_id": profile_id,
                    "company_name": name,
                    "profile_role": profile["profile_role"],
                    "industry_name": profile["industry_name"],
                    "purpose": profile["purpose"],
                    "products": profile["products"],
                    "organization_blueprint": profile["organization_blueprint"],
                    "recommended_apps": profile["recommended_apps"],
                    "default_assumptions": profile["default_assumptions"],
                    "data_class": "SYNTHETIC",
                    "not_for_management_decision": True,
                },
                inheritance_mode="merge",
                status="DRAFT",
                approved_by="",
                approved_at="",
            ))
        results.append({
            "company_profile_id": profile_id,
            "company_name": name,
            "status": "seeded",
            "entity_id": scenario["entity_id"],
            "scenario_id": scenario["scenario_id"],
            "source_code": source_code,
            "nodes": len(virtual_nodes),
            "valid_until": scenario["valid_until"],
        })

    return {
        "status": "completed" if all(row["status"] != "blocked" for row in results) else "partial",
        "seeded": sum(row["status"] == "seeded" for row in results),
        "skipped": sum(row["status"] == "skipped" for row in results),
        "blocked": sum(row["status"] == "blocked" for row in results),
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
