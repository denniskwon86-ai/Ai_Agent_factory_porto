"""[ECM E2] 크로스워크·MCP 조직 범위 격리.

★★ 이 파일이 잠그는 실제 결함: `mcp_broker.get_live_context()` 가 **활성 시스템을 전부**
   순회해 실측값을 프롬프트에 붙였다. 배터리소재 프로젝트의 프롬프트에 동제련 연계 시스템의
   값이 섞여 들어갔다 — `ProjectState` 는 이미 조직 문맥을 갖고 있었는데 이 경로가 보지 않았다.

프롬프트 유출은 화면 유출보다 위험하다. 산출물에 인용된 뒤에야 드러나고, 그때는 이미 늦다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.crosswalk import Crosswalk, CrosswalkError
from core.master_data import MasterData
from core.mcp_broker import MCPBroker, MockMCPAdapter, MCPError


@pytest.fixture()
def cw(tmp_path, monkeypatch):
    """격리된 master.db + 조상 해석을 고정한 크로스워크.

    ECM 리솔버를 실제로 태우지 않는다 — 이 테스트가 보는 것은 **가시성 판정의 배선**이지
    조직도 자체가 아니다(조직도는 test_ecm_e1 이 본다)."""
    md = MasterData(db_path=str(tmp_path / "master.db"))
    c = Crosswalk(md=md)

    import core.enterprise_context.scoping as sc
    # BATTERY / SMELTING 은 형제, 둘 다 MNM 을 운영 상위로 둔다.
    monkeypatch.setattr(sc, "visible_scopes",
                        lambda n: {"BATTERY", "MNM"} if n == "BATTERY"
                        else ({"SMELTING", "MNM"} if n == "SMELTING" else {n}))
    monkeypatch.setattr(sc, "resolve_scope_ref", lambda ref: ref)
    return c


def _code(sid: str) -> str:
    """master_code 는 대문자 규격(^[A-Z0-9][A-Z0-9_-]{1,31}$)이다."""
    return "MC-" + sid.upper().replace("-", "_")


def _seed_records(c, *codes):
    """주입 후보가 되려면 골든 레코드가 실제로 있어야 한다(매핑만으로는 부족)."""
    try:
        c.md.create_type("material", "자재")
    except Exception:
        pass
    for code in codes:
        c.md.create_or_revise_record(master_code=code, type_id="material", name=code)
    c.md._cache = None


def _make_system(c, sid, scope, active=True):
    c.create_system(sid, sid, mcp_endpoint="mock://x", enterprise_scope_id=scope)
    c.add_schema_field(sid, "item", "code", is_key=True)
    c.add_schema_field(sid, "item", "qty", mapped_attr="수량")
    # 승인된 매핑이 1건 있어야 활성화할 수 있다(기존 계약).
    conn = c._connect()
    try:
        conn.execute("INSERT INTO key_crosswalk(master_code,system_id,external_key,confirmed) "
                     "VALUES(?,?,?,1)", (_code(sid), sid, "item:code=X"))
        conn.commit()
    finally:
        conn.close()
    if active:
        c.update_system(sid, status="active")


# ── 목록·판정 ────────────────────────────────────────────────────────────────
def test_sibling_business_units_do_not_see_each_others_systems(cw):
    _make_system(cw, "sap-bat", "BATTERY")
    _make_system(cw, "mes-sml", "SMELTING")

    bat = [s["system_id"] for s in cw.list_systems(scope_node_id="BATTERY")]
    sml = [s["system_id"] for s in cw.list_systems(scope_node_id="SMELTING")]
    assert bat == ["sap-bat"] and sml == ["mes-sml"]
    assert cw.is_system_visible("mes-sml", "BATTERY") is False


def test_parent_scoped_system_is_visible_to_children(cw):
    """전사(MNM) 시스템은 하위 사업부가 본다 — 상속은 위에서 아래로만 흐른다."""
    _make_system(cw, "erp-group", "MNM")
    assert cw.is_system_visible("erp-group", "BATTERY") is True
    assert cw.is_system_visible("erp-group", "SMELTING") is True


def test_unscoped_system_is_invisible_and_counted(cw):
    """★★ [관문 A · 2026-07-30] 범위 미지정 연계 시스템은 **보이지 않고, 그래도 세어진다.**

    이 경로의 위험은 특별히 크다 — `mcp_broker.get_live_context()` 는 활성 시스템을 순회해
    **실측값을 프롬프트에 붙인다.** 그래서 미지정 시스템 하나가 곧 타 조직 운영값 유출이었다
    (배터리소재 프로젝트 프롬프트에 동제련 연계 시스템 값이 섞인 실제 사고).

    세는 것을 함께 잠그는 이유: 비노출로 바꾸면 이번엔 **연계가 조용히 끊긴다.** 운영자가
    "왜 값이 안 붙나"에 답할 수 있어야 한다."""
    _make_system(cw, "legacy", "")
    _make_system(cw, "sap-bat", "BATTERY")
    assert cw.is_system_visible("legacy", "SMELTING") is False, \
        "범위 미지정 시스템이 타 조직에 보인다 — 프롬프트에 실측값이 섞인다"

    cov = cw.systems_coverage()
    assert cov["total"] == 2 and cov["unscoped"] == 1
    assert cov["unscoped_systems"] == ["legacy"]
    assert cov["hidden_unscoped"] == 1
    assert "보이지 않습니다" in cov["note"]


def test_no_scope_means_no_filter(cw):
    """범위를 주지 않는 호출(ECM 미도입 흐름)은 종전대로 전량을 본다."""
    _make_system(cw, "sap-bat", "BATTERY")
    _make_system(cw, "mes-sml", "SMELTING")
    assert len(cw.list_systems()) == 2


def test_virtual_mode_systems_do_not_mix_into_real(cw):
    """VIRTUAL(가상 기업 Sandbox) 시스템이 REAL 문맥에 섞이면 그 자체가 오염이다."""
    cw.create_system("sim-plant", "sim", enterprise_scope_id="BATTERY", entity_mode="VIRTUAL")
    _make_system(cw, "sap-bat", "BATTERY")
    real = [s["system_id"] for s in cw.list_systems(scope_node_id="BATTERY", entity_mode="REAL")]
    virt = [s["system_id"] for s in cw.list_systems(scope_node_id="BATTERY", entity_mode="VIRTUAL")]
    assert real == ["sap-bat"] and virt == ["sim-plant"]


def test_invisible_system_error_does_not_reveal_existence(cw):
    """'권한 없음'이라고 답하면 그 시스템이 **있다는 사실**을 알려주는 것이다."""
    _make_system(cw, "mes-sml", "SMELTING")
    with pytest.raises(CrosswalkError) as e1:
        cw.require_system_visible("mes-sml", "BATTERY")
    with pytest.raises(CrosswalkError) as e2:
        cw.require_system_visible("does-not-exist", "BATTERY")
    assert str(e1.value).replace("mes-sml", "X") == str(e2.value).replace("does-not-exist", "X")


# ── MCP 조회 ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def broker(cw, tmp_path):
    # 목 어댑터는 (system_id, entity, selector) 키로 값을 돌려준다 — 두 시스템 모두 채워
    # "값이 없어서 안 나온 것"과 "격리돼서 안 나온 것"이 구분되게 한다.
    data = {(sid, "item", "code=X"): {"code": "X", "qty": 42}
            for sid in ("sap-bat", "mes-sml", "erp-group", "legacy")}
    return MCPBroker(adapter=MockMCPAdapter(data), cw=cw,
                     db_path=str(tmp_path / "mcp_cache.db"))


def test_resolve_refuses_invisible_system(broker, cw):
    _make_system(cw, "mes-sml", "SMELTING")
    with pytest.raises(MCPError, match="등록되지 않은 시스템"):
        broker.resolve(_code("mes-sml"), "mes-sml", scope_node_id="BATTERY")
    # 자기 조직에서는 정상 조회된다(게이트가 기능 자체를 막지 않는다).
    assert broker.resolve(_code("mes-sml"), "mes-sml", scope_node_id="SMELTING")["ok"] is True


def test_scope_is_checked_before_the_cache(broker, cw):
    """★★ 가장 놓치기 쉬운 유출: 캐시는 시스템 단위라, 판정을 캐시 뒤에 두면
    다른 조직이 채워 둔 캐시가 그대로 흘러나간다."""
    _make_system(cw, "mes-sml", "SMELTING")
    warm = broker.resolve(_code("mes-sml"), "mes-sml", scope_node_id="SMELTING")
    assert warm["cached"] is False
    assert broker.resolve(_code("mes-sml"), "mes-sml", scope_node_id="SMELTING")["cached"] is True

    with pytest.raises(MCPError):
        broker.resolve(_code("mes-sml"), "mes-sml", scope_node_id="BATTERY")


class _State:
    def __init__(self, scope="", tenant="", mode="REAL"):
        self.enterprise_scope_id = scope
        self.tenant_id = tenant
        self.entity_mode = mode
        self.master_domains = []
        self.mcp_live_grounding = True


def test_live_context_does_not_leak_sibling_measurements(broker, cw):
    """★★ 이 파일의 핵심 — 프롬프트에 남의 사업부 실측값이 들어가지 않는다."""
    _make_system(cw, "sap-bat", "BATTERY")
    _make_system(cw, "mes-sml", "SMELTING")
    # 두 시스템의 매핑 대상 골든 레코드를 만든다(주입 후보가 되려면 마스터에 있어야 한다).
    _seed_records(cw, _code("sap-bat"), _code("mes-sml"))

    ctx = broker.get_live_context(_State(scope="BATTERY"))
    assert "sap-bat" in ctx
    assert "mes-sml" not in ctx, "다른 사업부의 연계 시스템 실측값이 프롬프트에 섞였다"


def test_live_context_unfiltered_when_no_scope_declared(broker, cw):
    _make_system(cw, "sap-bat", "BATTERY")
    _make_system(cw, "mes-sml", "SMELTING")
    _seed_records(cw, _code("sap-bat"), _code("mes-sml"))

    ctx = broker.get_live_context(_State())      # ECM 미도입 — 종전 동작
    assert "sap-bat" in ctx and "mes-sml" in ctx


def test_live_context_fails_closed_when_scope_cannot_be_resolved(broker, cw, monkeypatch):
    """★ 범위를 선언했는데 해석에 실패하면 **병기를 생략한다**.

    기준정보 주입은 같은 상황에서 필터를 생략하고 계속한다(최악이 과다 주입). 여기는 최악이
    **남의 조직 실측값 유출**이라 반대로 간다 — 두 모듈의 처리가 다른 것은 의도된 차이다."""
    _make_system(cw, "sap-bat", "BATTERY")
    _seed_records(cw, _code("sap-bat"))

    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "resolve_scope_ref", lambda ref: "")   # 해석 실패
    assert broker.get_live_context(_State(scope="BATTERY")) == ""


# ── API 계약 ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def client(cw, broker, monkeypatch):
    """라우터의 싱글턴을 tmp 인스턴스로 갈아끼운다 — 개발 DB 를 건드리지 않는다."""
    from fastapi.testclient import TestClient
    import api.routes.crosswalk_control as cc
    import api.routes.mcp_control as mc
    import main

    monkeypatch.setattr(cc, "crosswalk", cw)
    monkeypatch.setattr(mc, "mcp_broker", broker)
    # mcp_control 의 게이트는 지연 임포트로 크로스워크 싱글턴을 집는다 — 그쪽도 갈아끼운다.
    import core.crosswalk as cw_mod
    monkeypatch.setattr(cw_mod, "crosswalk", cw)
    return TestClient(main.app)


def test_coverage_route_is_not_shadowed_by_system_id(client, cw):
    """`/systems/coverage` 가 `/systems/{system_id}` 아래에 있으면 404 다(실측 사고 이력)."""
    r = client.get("/api/v1/crosswalk/systems/coverage")
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]) >= {"total", "unscoped", "unscoped_systems"}


def test_api_list_systems_applies_scope(client, cw):
    _make_system(cw, "sap-bat", "BATTERY")
    _make_system(cw, "mes-sml", "SMELTING")
    ids = [s["system_id"] for s in
           client.get("/api/v1/crosswalk/systems?scope_node_id=BATTERY").json()["data"]]
    assert ids == ["sap-bat"]
    assert len(client.get("/api/v1/crosswalk/systems").json()["data"]) == 2   # 미지정 = 종전


@pytest.mark.parametrize("path", [
    "/api/v1/crosswalk/systems/mes-sml/schema",
    "/api/v1/crosswalk/systems/mes-sml/mappings",
    "/api/v1/crosswalk/systems/mes-sml/proposals",
])
def test_api_child_resources_are_gated(client, cw, path):
    """자식 자원에 범위 키를 복제하지 않은 대가 — 모든 자식 경로가 부모 게이트를 지나야 한다."""
    _make_system(cw, "mes-sml", "SMELTING")
    assert client.get(path).status_code == 200                                   # 미지정 = 종전
    assert client.get(f"{path}?scope_node_id=SMELTING").status_code == 200       # 자기 조직
    assert client.get(f"{path}?scope_node_id=BATTERY").status_code == 404        # 남의 조직


def test_api_mcp_resolve_is_gated(client, cw):
    _make_system(cw, "mes-sml", "SMELTING")
    body = {"master_code": _code("mes-sml"), "system_id": "mes-sml"}
    assert client.post("/api/v1/mcp/resolve", json=body).json()["data"]["ok"] is True
    # ★ [2026-07-29 갱신 · M2 관문 B-1] 종전에는 409(MCPError 일괄)였다. 409 는 "자원이 있으나
    #   상태가 맞지 않다"는 뜻이라 **존재를 알려준다** — 타 조직 자원은 존재 자체를 숨겨야 하므로
    #   404 로 바뀌었다(§3.3 경계표). 상태 충돌(비활성·매핑 없음)은 여전히 409 다.
    r = client.post("/api/v1/mcp/resolve", json={**body, "scope_node_id": "BATTERY"})
    assert r.status_code == 404 and "등록되지 않은 시스템" in r.json()["detail"]


def test_api_mcp_health_does_not_reveal_other_org_systems(client, cw):
    _make_system(cw, "mes-sml", "SMELTING")
    assert client.get("/api/v1/mcp/systems/mes-sml/health").status_code == 200
    assert client.get(
        "/api/v1/mcp/systems/mes-sml/health?scope_node_id=BATTERY").status_code == 404
