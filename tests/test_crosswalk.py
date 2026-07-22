"""core/crosswalk.py — M2 스키마 레지스트리 + 키 크로스워크 검증(LLM 0콜, 결정론 경로).

핵심 불변식:
  - 매핑은 승인(approve)해야만 유효(confirmed=1) — 제안(pending)은 미사용.
  - 제안 external_key 는 '조인 컬럼' 포인터 "entity:field", 승인 시 인스턴스 값 지정 가능.
  - 승인된 매핑이 있어야 시스템 활성화(active) 가능.
  - 이미 승인된 (master_code,system_id) 는 재제안에서 스킵.
Flash 옵트인 경로(use_llm=True)는 쿼터가 필요해 여기선 미사용.
"""
import os
import asyncio
import tempfile
import pytest
from core.master_data import MasterData
from core.crosswalk import Crosswalk, CrosswalkError


def _fx():
    md = MasterData(db_path=os.path.join(tempfile.mkdtemp(), "m.db"))
    cw = Crosswalk(md=md)
    md.create_type("material", "자재")
    md.create_or_revise_record("MAT-100", "material", "강판 100", aliases=["MATNR", "강판"], domains=["mfg"])
    return md, cw


def test_system_crud_and_duplicate():
    _, cw = _fx()
    cw.create_system("sap", "SAP ERP")
    assert any(s["system_id"] == "sap" for s in cw.list_systems())
    with pytest.raises(CrosswalkError):
        cw.create_system("sap", "dup")            # 중복
    with pytest.raises(CrosswalkError):
        cw.create_system("Bad ID!", "x")          # 형식 위반


def test_activate_requires_confirmed_mapping():
    _, cw = _fx()
    cw.create_system("sap", "SAP")
    with pytest.raises(CrosswalkError):
        cw.update_system("sap", status="active")  # 승인 매핑 0 → 거부


def test_propose_deterministic_and_approve_flow():
    _, cw = _fx()
    cw.create_system("sap", "SAP")
    cw.add_schema_field("sap", "MARA", "MATNR", is_key=True)
    r = asyncio.run(cw.propose("sap", use_llm=False))
    assert r["proposed"] == 1 and r["deterministic"] == 1 and r["llm_used"] is False
    props = cw.list_proposals("sap", "pending")
    assert props[0]["external_key"] == "MARA:MATNR"         # 조인 컬럼 포인터
    assert props[0]["confidence"] >= 0.9                    # 별칭==키 정확일치
    # 승인 전에는 매핑 없음
    assert cw.list_mappings("sap") == []
    # 승인(인스턴스 값 지정)
    cw.approve_proposal(props[0]["id"], external_key="MARA:MATNR=100-200-30")
    mp = cw.list_mappings("sap")
    assert mp and mp[0]["external_key"] == "MARA:MATNR=100-200-30"
    # 승인 후 활성화 가능
    assert cw.update_system("sap", status="active")["status"] == "active"


def test_approved_skipped_on_repropose():
    _, cw = _fx()
    cw.create_system("sap", "SAP")
    cw.add_schema_field("sap", "MARA", "MATNR", is_key=True)
    asyncio.run(cw.propose("sap"))
    pid = cw.list_proposals("sap", "pending")[0]["id"]
    cw.approve_proposal(pid)
    # 재제안 시 승인된 (master_code,system_id) 는 제외
    r2 = asyncio.run(cw.propose("sap"))
    assert r2["proposed"] == 0


def test_reject_preserves_history():
    _, cw = _fx()
    cw.create_system("sap", "SAP")
    cw.add_schema_field("sap", "MARA", "MATNR", is_key=True)
    asyncio.run(cw.propose("sap"))
    pid = cw.list_proposals("sap", "pending")[0]["id"]
    cw.reject_proposal(pid)
    assert cw.list_proposals("sap", "pending") == []
    assert any(p["status"] == "rejected" for p in cw.list_proposals("sap"))
    with pytest.raises(CrosswalkError):
        cw.approve_proposal(pid)                  # 이미 처리됨 → 승인 불가


def test_propose_requires_schema():
    _, cw = _fx()
    cw.create_system("sap", "SAP")
    with pytest.raises(CrosswalkError):
        asyncio.run(cw.propose("sap"))            # 스키마 없음


def test_field_mapping_join_column():
    _, cw = _fx()
    cw.create_system("mes", "MES")
    cw.add_schema_field("mes", "work_order", "LEAD_TIME_HRS", field_type="number")
    # 조인 컬럼 정의: 외부 필드 ↔ 우리 속성
    cw.set_field_mapping("mes", "work_order", "LEAD_TIME_HRS", mapped_type="process", mapped_attr="표준리드타임_h")
    sch = cw.get_schema("mes")
    row = next(s for s in sch if s["field"] == "LEAD_TIME_HRS")
    assert row["mapped_attr"] == "표준리드타임_h" and row["mapped_type"] == "process"
