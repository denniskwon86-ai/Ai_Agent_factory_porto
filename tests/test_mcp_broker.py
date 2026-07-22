"""core/mcp_broker.py — M3 MCP 데이터 브로커 검증(목 어댑터, LLM 0콜).

핵심 불변식:
  - 승인된 크로스워크(confirmed=1) + 활성 시스템만 조회. 미승인/비활성은 거부.
  - 온디맨드: 캐시 미스→조회→캐시, 히트는 재조회 안 함. TTL 만료 시 재조회.
  - as_of 항상 스탬프(재현성). 외부 필드→우리 속성명 라벨링.
  - 정직한 실패: 어댑터 오류 시 ok=False(옛 캐시/골든값 자동대체 없음).
"""
import os
import tempfile
import pytest
from core.master_data import MasterData
from core.crosswalk import Crosswalk
from core.mcp_broker import MCPBroker, MockMCPAdapter, MCPError


def _fx(ttl=300, adapter=None):
    md = MasterData(db_path=os.path.join(tempfile.mkdtemp(), "m.db"))
    cw = Crosswalk(md=md)
    md.create_type("process", "공정")
    md.create_or_revise_record("PROC-ASSY-01", "process", "조립 공정", aliases=["ASSY"], domains=["mfg"])
    cw.create_system("mes", "MES")
    cw.add_schema_field("mes", "work_order", "LEAD_TIME_HRS", field_type="number", mapped_attr="표준리드타임_h")
    cw.add_schema_field("mes", "work_order", "WO_TYPE", is_key=True)
    # 크로스워크 직접 승인(필드명이 별칭과 안 맞으므로 수동)
    c = md._connect()
    c.execute("INSERT INTO key_crosswalk VALUES('PROC-ASSY-01','mes','work_order:WO_TYPE=ASSY',1)")
    c.commit(); c.close()
    cw.update_system("mes", status="active")
    ad = adapter or MockMCPAdapter(data={("mes", "work_order", "WO_TYPE=ASSY"):
                                         {"LEAD_TIME_HRS": 68, "WO_TYPE": "ASSY"}})
    br = MCPBroker(adapter=ad, cw=cw, db_path=os.path.join(tempfile.mkdtemp(), "c.db"), default_ttl=ttl)
    return md, cw, br


def test_resolve_miss_then_hit_and_labeling():
    _, _, br = _fx()
    r1 = br.resolve("PROC-ASSY-01", "mes")
    assert r1["ok"] and r1["cached"] is False
    assert r1["values"]["표준리드타임_h"] == 68        # 외부 LEAD_TIME_HRS → 우리 속성 라벨링
    assert r1["as_of"]                                  # as_of 스탬프
    r2 = br.resolve("PROC-ASSY-01", "mes")
    assert r2["cached"] is True and r2["as_of"] == r1["as_of"]


def test_ttl_expiry_refetch():
    _, _, br = _fx(ttl=0)                                # ttl=0 저장 → 항상 만료
    br.resolve("PROC-ASSY-01", "mes")
    r2 = br.resolve("PROC-ASSY-01", "mes")
    assert r2["cached"] is False                        # 만료로 재조회


def test_invalidate():
    _, _, br = _fx()
    br.resolve("PROC-ASSY-01", "mes")
    assert br.invalidate("mes") == 1
    assert br.resolve("PROC-ASSY-01", "mes")["cached"] is False


def test_force_refetch():
    _, _, br = _fx()
    br.resolve("PROC-ASSY-01", "mes")
    assert br.resolve("PROC-ASSY-01", "mes", force=True)["cached"] is False


def test_honest_failure_on_adapter_error():
    class Boom(MockMCPAdapter):
        def fetch(self, *a):
            raise RuntimeError("conn refused")
    _, _, br = _fx(adapter=Boom())
    r = br.resolve("PROC-ASSY-01", "mes")
    assert r["ok"] is False and "conn refused" in r["error"]
    assert r["values"] == {}                            # 골든값 자동대체 없음


def test_reject_unapproved_mapping():
    _, _, br = _fx()
    with pytest.raises(MCPError):
        br.resolve("UNKNOWN-CODE", "mes")               # 승인 매핑 없음


def test_reject_inactive_system():
    _, cw, br = _fx()
    cw.update_system("mes", status="inactive")
    with pytest.raises(MCPError):
        br.resolve("PROC-ASSY-01", "mes")               # 비활성 → 거부


def test_health_via_adapter():
    _, _, br = _fx()
    assert br.health("mes")["healthy"] is True
    with pytest.raises(MCPError):
        br.health("no_such_system")


def test_batch_mixed():
    _, _, br = _fx()
    out = br.resolve_batch(["PROC-ASSY-01", "MISSING"], "mes")
    assert out[0]["ok"] is True
    assert out[1]["ok"] is False                         # 미승인은 개별 실패로
