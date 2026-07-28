#!/usr/bin/env python3
"""
LS MnM 온산공장 실제급 제조 합성 시드 데이터 생성 스크립트
문서 데이터(M1~M4 JSON)의 도메인 파라미터를 읽어, Enterprise Context Master(ECM) 상속 모델에 맞춘
실제급 엔터프라이즈 시드 데이터를 생성하고 `data/ls_mnm_realistic_enterprise_seed.json`으로 출력합니다.
"""

import json
import os
import random
from datetime import datetime, timezone

# 프로젝트 루트 경로 계산
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER_DATA_DIR = os.path.join(BASE_DIR, "docs", "master_data")
OUTPUT_DIR = os.path.join(BASE_DIR, "data")


def load_json(filename):
    filepath = os.path.join(MASTER_DATA_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_realistic_seed():
    m1 = load_json("battery_material_m1.json")
    m2 = load_json("copper_smelting_m2.json")
    m3 = load_json("global_standard_m3.json")
    m4 = load_json("digital_twin_simulation_m4.json")

    timestamp = datetime.now(timezone.utc).isoformat()

    # 1. Enterprise Context Master (ECM) 조직 노드 & 엣지
    organization_tree = {
        "tenant_id": "tenant-ls-group-001",
        "tenant_name": "LS 그룹 (LS Enterprise Group)",
        "entity_mode": "REAL",
        "status": "ACTIVE",
        "effective_from": "2026-01-01T00:00:00Z",
        "nodes": [
            {
                "node_id": "node-ls-group",
                "node_type": "ENTERPRISE_GROUP",
                "code": "LS_GROUP",
                "name": "LS 그룹 지주사",
                "parent_id": None,
            },
            {
                "node_id": "node-ls-mnm",
                "node_type": "LEGAL_ENTITY",
                "code": "LS_MNM",
                "name": "LS MnM (주)",
                "industry_code": "C24120",  # 동제련 및 금속 재활용 소재
                "parent_id": "node-ls-group",
            },
            {
                "node_id": "node-ls-mnm-shared",
                "node_type": "SHARED_SERVICE",
                "code": "LS_MNM_SHARED",
                "name": "LS MnM 전사공통 (경영관리/재무회계/IT)",
                "parent_id": "node-ls-mnm",
            },
            {
                "node_id": "node-ls-mnm-smelting-bu",
                "node_type": "BUSINESS_DIVISION",
                "code": "BU_SMELTING",
                "name": "동제련 사업부",
                "parent_id": "node-ls-mnm",
            },
            {
                "node_id": "node-ls-mnm-onsan-plant1",
                "node_type": "PLANT",
                "code": "PLANT_ONSAN_1",
                "name": "온산 제1공장 (동제련/전해조)",
                "parent_id": "node-ls-mnm-smelting-bu",
            },
            {
                "node_id": "node-ls-mnm-battery-bu",
                "node_type": "BUSINESS_DIVISION",
                "code": "BU_BATTERY",
                "name": "배터리 소재 사업부",
                "parent_id": "node-ls-mnm",
            },
            {
                "node_id": "node-ls-mnm-onsan-plant2",
                "node_type": "PLANT",
                "code": "PLANT_ONSAN_2",
                "name": "온산 제2공장 (황산니켈/수산화리튬)",
                "parent_id": "node-ls-mnm-battery-bu",
            },
        ],
    }

    # 2. 통합 품목 마스터 & BOM (M1 배터리 + M2 동제련)
    materials = m1.get("material_master", []) + m2.get("material_master", [])
    boms = m1.get("bill_of_materials", []) + m2.get("bill_of_materials", [])

    # 3. 통합 설비 마스터 (M1 + M2)
    equipments = m1.get("equipment_master", []) + m2.get("equipment_master", [])

    # 4. 통합 품질 기준 & SPC (M1 + M2)
    quality_specs = m1.get("quality_master", []) + m2.get("quality_master", [])

    # 5. 통합 SIOP 재무 & 경제 지표 (M1 + M2)
    siop_economics = {
        "market_prices": {
            "lme_copper_usd_ton": m2["siop_finance_master"][0]["lme_copper_price_usd_ton"],
            "lme_nickel_usd_ton": m1["siop_finance_master"][0]["lme_nickel_price_usd_ton"],
            "lbma_gold_usd_oz": m2["siop_finance_master"][0]["lbma_gold_price_usd_oz"],
            "krw_usd_exchange_rate": m1["siop_finance_master"][0]["exchange_rate_krw_usd"],
        },
        "smelting_charges": m2["siop_finance_master"][1],
        "cost_rates": m1["siop_finance_master"][1],
    }

    # 6. 실시간 센서 스트림 텔레메트리 스펙 (M4)
    telemetry_spec = m4.get("data_sync_fidelity", {})
    spatial_layout = m4.get("spatial_3d_fab_layout", {})

    # 전체 엔터프라이즈 시드 패키지 조립
    enterprise_seed = {
        "seed_metadata": {
            "version": "1.0-REALISTIC-SEED",
            "generated_at": timestamp,
            "description": "LS MnM 온산공장 실제급 제조 합성 시드 데이터 (M1~M4 문서 파라미터 통합)",
        },
        "organization_tree": organization_tree,
        "material_master": materials,
        "bill_of_materials": boms,
        "equipment_master": equipments,
        "quality_master": quality_specs,
        "siop_economics": siop_economics,
        "digital_twin_telemetry_spec": telemetry_spec,
        "spatial_layout": spatial_layout,
        "global_standard_rules": m3.get("erp_business_logic", {}),
    }

    # 파일 저장
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_filepath = os.path.join(OUTPUT_DIR, "ls_mnm_realistic_enterprise_seed.json")
    with open(out_filepath, "w", encoding="utf-8") as f:
        json.dump(enterprise_seed, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] 실제급 합성 시드 데이터 생성 완료: {out_filepath}")
    print(f"  - 조직 노드: {len(organization_tree['nodes'])}개")
    print(f"  - 품목 마스터: {len(materials)}개")
    print(f"  - BOM 구조: {len(boms)}개")
    print(f"  - 주요 설비: {len(equipments)}개")
    print(f"  - 품질 검사 규격: {len(quality_specs)}개")


if __name__ == "__main__":
    generate_realistic_seed()
