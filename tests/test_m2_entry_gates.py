"""M2 착수 관문 — **통과해야 M2를 시작할 수 있는 두 개의 문.**

2026-07-29 사용자 판정으로 확정된 착수 조건이다.

    ④ M2 는 「미바인딩 비노출」 회귀 테스트와
       「타 조직 자원 404 + 내부 감사로그 기록」 테스트를 통과한 뒤 착수한다.

## 이 파일을 읽는 법 — `xfail` 은 실패가 아니라 **아직 열리지 않은 문**이다

관문 항목은 `xfail(strict=True)` 로 표시했다. 지금은 구현이 없으므로 xfail(=예상된 미달)로
집계되고, **구현이 되는 순간 xpass 가 되어 테스트가 빨갛게 뜬다.** 그때 이 표시를 떼면 된다.
"아직 안 됐다"를 초록불로 위장하지 않으면서, 완료 시점을 자동으로 알려주는 유일한 방법이다.

⚠️ `xfail` 이 아닌 테스트도 섞여 있다. 그것은 **지금 이미 지켜져야 하는 것**이다
   (예: 인증 실패를 404 로 바꾸지 않는다). 둘을 섞어 둔 이유는, 관문을 통과시키려다
   멀쩡한 동작을 깨뜨리는 일이 이 저장소에서 반복됐기 때문이다.

## 관문 A — 미바인딩 비노출 (MDM-SCOPE-01)

"범위 미지정 = 전사 공용"은 폐기됐다. 기본값은 **비노출(fail-closed)** 이고, 전사 공용은
`scope_type=ENTERPRISE_SHARED` + 승인 이력이 있는 **명시적 상태**여야 한다.
현재 이 규칙이 사는 곳은 정확히 두 곳이다 —
`core/master_data.py::select_for_injection._in_scope` 와
`core/enterprise_context/scoping.py::is_visible`. 두 곳 다 막지 않으면 한쪽으로 샌다.

## 관문 B — 타 조직 자원 404 + 감사로그 (ECM-E2-XWALK-01)

거부는 "존재하지 않음"과 구분되지 않아야 하고(Data Stealth), **그 순간 서버 감사로그에는
`ACCESS_DENIED_SCOPE_MISMATCH` 와 실제 대상 식별자가 남아야 한다.** 조용한 차단은 운영자가
침해 시도를 볼 수 없게 만든다 — 은폐는 외부용이지 내부용이 아니다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_GATE_A = "M2 관문 A — 미바인딩 비노출 미구현(현재는 '미바인딩 = 전사 공용'으로 통과한다)"
_GATE_B = "M2 관문 B — 404 은폐/감사로그 미구현(현재는 409 이고 감사 기록이 없다)"


# ══════════════════════════════════════════════════════════════════════
# 관문 A — 미바인딩 비노출
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture()
def md(tmp_path):
    from core.master_data import MasterData
    m = MasterData(db_path=str(tmp_path / "master.db"))
    m.create_type("material", "자재")
    m.create_or_revise_record(master_code="MC-BOUND", type_id="material", name="바인딩된 자재",
                              domains=["battery"])
    m.create_or_revise_record(master_code="MC-UNBOUND", type_id="material", name="미바인딩 자재",
                              domains=["battery"])
    m._cache = None
    return m


@pytest.mark.xfail(strict=True, reason=_GATE_A)
def test_gate_a_unbound_master_record_is_not_injected(md, monkeypatch):
    """★★ 관문 A-1: 미바인딩 기준정보는 **어느 조직의 프롬프트에도 들어가지 않는다.**

    이것이 2026-07-29 에 실제로 샌 경로다 — 재시드가 바인딩을 건너뛰자 26건이 전 조직에
    노출됐고, LS전선 프롬프트에 MnM 기준정보가 들어갔다."""
    md.bind_scope("MC-BOUND", tenant_id="tenant_default", scope_node_id="BATTERY")
    codes = [r["master_code"] for r in
             md.select_for_injection("배터리", ["battery"],
                                     tenant_id="tenant_default", scope_node_id="BATTERY")]
    assert codes == ["MC-BOUND"], "미바인딩 레코드가 주입 후보에 남아 있다"


@pytest.mark.xfail(strict=True, reason=_GATE_A)
def test_gate_a_unscoped_row_is_invisible():
    """★★ 관문 A-2: 카탈로그·용어사전·계약·연계 시스템도 같은 규칙을 따른다.

    두 곳(주입 경로 / 가시성 판정)을 모두 막지 않으면 한쪽으로 샌다."""
    from core.enterprise_context.scoping import is_visible
    row = {"enterprise_scope_id": "", "tenant_id": "tenant_default", "entity_mode": "REAL"}
    assert is_visible(row, "BATTERY") is False, "범위 미지정 레코드가 그대로 보인다"


@pytest.mark.xfail(strict=True, reason=_GATE_A)
def test_gate_a_enterprise_shared_requires_explicit_type_and_approval():
    """★ 관문 A-3: 전사 공용은 **빈 값의 해석**이 아니라 명시적 상태 + 승인 이력이다."""
    from core.enterprise_context.scoping import is_visible
    shared = {"enterprise_scope_id": "", "scope_type": "ENTERPRISE_SHARED",
              "approval_status": "APPROVED", "approved_by": "admin",
              "tenant_id": "tenant_default", "entity_mode": "REAL"}
    pending = {**shared, "approval_status": "PENDING", "approved_by": ""}
    assert is_visible(shared, "BATTERY") is True, "승인된 전사 공용은 보여야 한다"
    assert is_visible(pending, "BATTERY") is False, "미승인 전사 공용이 보이면 승인 절차가 무의미하다"


@pytest.mark.xfail(strict=True, reason=_GATE_A)
def test_gate_a_legacy_rows_are_grandfathered_but_counted():
    """★ 관문 A-4: 레거시는 한시 정책으로 통과시키되 **반드시 세어져야** 한다.

    기존 데이터를 하루아침에 안 보이게 하면 도입이 멈춘다. 그러나 통과시키는 것과
    통과한 줄 모르는 것은 다르다 — 한시 예외에는 만료일과 건수 관측이 붙어야 한다."""
    from core.enterprise_context.scoping import coverage, is_visible
    legacy = {"enterprise_scope_id": "", "scope_type": "LEGACY_UNSCOPED",
              "tenant_id": "tenant_default", "entity_mode": "REAL"}
    assert is_visible(legacy, "BATTERY") is True
    cov = coverage([legacy], "레코드")
    assert cov.get("legacy_grandfathered") == 1, "한시 예외 건수가 별도로 세어져야 한다"


def test_gate_a_no_scope_call_still_works():
    """★ 회귀 잠금(지금도 지켜져야 함): 범위를 **주지 않는** 호출은 계속 전량을 본다.

    ECM 미도입 환경과 관리자 도구가 여기에 의존한다. 관문 A 를 구현하다 이걸 깨면
    도입 전 사용자가 자기 데이터를 못 본다."""
    from core.enterprise_context.scoping import filter_visible
    rows = [{"enterprise_scope_id": ""}, {"enterprise_scope_id": "BATTERY"}]
    assert len(filter_visible(rows)) == 2


# ══════════════════════════════════════════════════════════════════════
# 관문 B — 타 조직 자원 404 + 감사로그
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.xfail(strict=True, reason=_GATE_B)
def test_gate_b_other_org_resource_returns_404():
    """★★ 관문 B-1: 타 조직 자원의 거부는 **존재하지 않음과 구분되지 않아야** 한다.

    현재 MCP 는 409(Conflict)를 준다 — 409 는 '자원이 있으나 상태가 맞지 않다'는 뜻이라
    존재를 알려준다."""
    from fastapi.testclient import TestClient
    import main

    c = TestClient(main.app)
    r = c.post("/api/v1/mcp/resolve",
               json={"master_code": "MC-X", "system_id": "mes-smelting",
                     "scope_node_id": "BATTERY"})
    assert r.status_code == 404


@pytest.mark.xfail(strict=True, reason=_GATE_B)
def test_gate_b_denial_is_written_to_the_audit_log():
    """★★ 관문 B-2: 은폐는 외부용이다 — **내부에는 반드시 남는다.**

    `ACCESS_DENIED_SCOPE_MISMATCH` + 실제 대상 식별자(요청 주체, 시스템/레코드 id, 요청 범위).
    이것이 없으면 운영자는 침해 시도를 영원히 볼 수 없다."""
    from core.enterprise_context import audit      # 아직 없는 모듈(설계: docs/design_m2_scope_contract_and_audit.md)

    events = audit.recent(limit=10)
    assert any(e["event"] == "ACCESS_DENIED_SCOPE_MISMATCH" for e in events)


@pytest.mark.xfail(strict=True, reason=_GATE_B)
def test_gate_b_mcp_does_not_trust_client_supplied_scope():
    """★★ 관문 B-4: 서버가 **인증 주체로부터** 범위를 계산해야 한다.

    현재는 요청 본문의 `scope_node_id` 를 그대로 믿는다 — 즉 아무나 남의 조직 범위를 적어
    보내면 그 범위로 조회된다. 클라이언트가 보낸 범위는 '요청'일 뿐 '권한'이 아니다."""
    import inspect

    import api.routes.mcp_control as mc

    src = inspect.getsource(mc)
    assert "current_principal" in src, "MCP 라우트가 인증 주체를 보지 않는다"


def test_gate_b_auth_failures_are_not_disguised_as_404():
    """★ 회귀 잠금(지금도 지켜져야 함): 인증 실패·요청 형식 오류까지 404 로 만들면
    운영 진단이 불가능해진다. 은폐 대상은 **개별 자원 조회**뿐이다."""
    from fastapi.testclient import TestClient
    import config
    import main

    c = TestClient(main.app)
    # 잘못된 요청 형식 → 422(FastAPI 검증). 404 로 뭉개면 클라이언트가 원인을 못 찾는다.
    assert c.post("/api/v1/mcp/resolve", json={"system_id": "x"}).status_code == 422

    # 식별 없는 쓰기 → 401. (품질 분류 API 로 확인 — 같은 원칙이 전 API 에 적용된다)
    _saved = getattr(config, "ORG_DEFAULT_USER_ID", "")
    config.ORG_DEFAULT_USER_ID = ""
    try:
        r = c.post("/api/v1/telemetry/quality/classify",
                   json={"outcome_id": "x", "root_cause": "model_quality"})
        assert r.status_code == 401, "인증 실패는 401 이어야 한다(404 로 은폐 금지)"
    finally:
        config.ORG_DEFAULT_USER_ID = _saved
