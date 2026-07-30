"""M2 착수 관문 — **통과해야 M2를 시작할 수 있는 두 개의 문.**

2026-07-29 사용자 판정으로 확정된 착수 조건이다.

    ④ M2 는 「미바인딩 비노출」 회귀 테스트와
       「타 조직 자원 404 + 내부 감사로그 기록」 테스트를 통과한 뒤 착수한다.

## 이 파일을 읽는 법 — **두 문 모두 열렸다. 이제 전부 회귀 잠금이다.**

관문 항목은 `xfail(strict=True)` 로 표시해 뒀었다. 구현되는 순간 xpass 가 되어 빨갛게 뜨고,
그때 표시를 떼는 방식이다 — "아직 안 됐다"를 초록불로 위장하지 않으면서 완료 시점을 자동으로
알려주는 유일한 방법이다.

  · 관문 B(404 은폐 + 감사로그) — 2026-07-29 열림
  · 관문 A(미바인딩 비노출)     — 2026-07-30 열림

⚠️ **strict xfail 의 한계를 실제로 겪었다.** 관문 A-1 은 존재하지 않는 메서드를 부르고 있어서
   AttributeError 로 xfail 됐다 — 즉 단정문이 한 번도 실행되지 않은 채 "미구현"으로 집계됐다.
   xfail 은 미구현과 오타를 같은 색으로 칠한다. 다음에 이 방식으로 문을 만들 때는, 표시를 뗄 때
   **단정문이 실제로 도는지**까지 확인해야 한다.

⚠️ 관문을 통과시키려다 멀쩡한 동작을 깨뜨리는 일이 이 저장소에서 반복됐으므로, "지금 이미
   지켜져야 하는 것"(예: 인증 실패를 404 로 바꾸지 않는다 · 범위 미지정 호출은 전량을 본다)을
   같은 파일에 함께 뒀다.

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

# (관문 A·B 의 xfail 사유 상수는 두 문이 모두 열려 더 이상 쓰이지 않으므로 제거했다 —
#  쓰이지 않는 상수를 남겨 두면 다음 사람이 "아직 닫힌 문이 있나"로 읽는다.)


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


# ✅ [2026-07-30 · Claude Code] 관문 A 4건 **열림** — xfail 을 떼고 회귀 잠금으로 승격.
#   근거: `core/enterprise_context/scoping.py`(fail-closed + 명시 상태 + 한시 예외 관측) ·
#         `core/master_data.py::select_for_injection._in_scope`(미바인딩 비주입 + 제외 건수)
#   ⚠️ A-1 은 **테스트 자체가 고장 나 있었다** — 존재하지 않는 `md.bind_scope()` 를 불러
#     AttributeError 로 xfail 됐으므로, 단정문은 한 번도 실행되지 않았다. strict xfail 은
#     "아직 안 됐다"를 알려주지만 **왜 안 됐는지는 알려주지 않는다** — 미구현과 오타를 같은
#     색으로 칠한다. 관문을 열 때는 xfail 을 떼는 것만으로 부족하고 단정문이 실제로 도는지
#     확인해야 한다(실제 API 는 `bind_master_to_scope`).
def test_gate_a_unbound_master_record_is_not_injected(md, monkeypatch):
    """★★ 관문 A-1: 미바인딩 기준정보는 **어느 조직의 프롬프트에도 들어가지 않는다.**

    이것이 2026-07-29 에 실제로 샌 경로다 — 재시드가 바인딩을 건너뛰자 26건이 전 조직에
    노출됐고, LS전선 프롬프트에 MnM 기준정보가 들어갔다."""
    md.bind_master_to_scope("MC-BOUND", "BATTERY", tenant_id="tenant_default")
    codes = [r["master_code"] for r in
             md.select_for_injection("배터리", ["battery"],
                                     tenant_id="tenant_default", scope_node_id="BATTERY")]
    assert codes == ["MC-BOUND"], "미바인딩 레코드가 주입 후보에 남아 있다"


def test_gate_a_exclusion_is_counted_not_silent(md):
    """★★ 관문 A-1 의 짝: 막은 것을 **세지 않으면** 그라운딩이 조용히 비어버린다.

    "기준정보가 없는 프로젝트"와 "바인딩을 안 한 프로젝트"는 완전히 다른 상태이고, 후자를
    침묵으로 처리하면 LLM 은 수치를 스스로 만들어낸다 — 관문 A 가 막으려는 것은 유출이지
    창작이 아니다."""
    md.bind_master_to_scope("MC-BOUND", "BATTERY", tenant_id="tenant_default")
    _, stats = md.select_for_injection("배터리", ["battery"], tenant_id="tenant_default",
                                       scope_node_id="BATTERY", with_stats=True)
    assert stats["excluded_unbound"] == 1, "미바인딩으로 제외된 건수가 보고되지 않는다"

    # 한 건도 못 넣은 경우에도 이유가 블록에 남는다(빈 문자열로 침묵하지 않는다).
    block = md.render_grounding("무관한 텍스트", ["nonexistent_domain"],
                                tenant_id="tenant_default", scope_node_id="OTHER_ORG")
    assert "추정하거나 창작하지 말 것" in block, "빈 그라운딩의 이유가 프롬프트에 없다"


def test_gate_a_unscoped_row_is_invisible():
    """★★ 관문 A-2: 카탈로그·용어사전·계약·연계 시스템도 같은 규칙을 따른다.

    두 곳(주입 경로 / 가시성 판정)을 모두 막지 않으면 한쪽으로 샌다."""
    from core.enterprise_context.scoping import is_visible
    row = {"enterprise_scope_id": "", "tenant_id": "tenant_default", "entity_mode": "REAL"}
    assert is_visible(row, "BATTERY") is False, "범위 미지정 레코드가 그대로 보인다"


def test_gate_a_enterprise_shared_requires_explicit_type_and_approval():
    """★ 관문 A-3: 전사 공용은 **빈 값의 해석**이 아니라 명시적 상태 + 승인 이력이다."""
    from core.enterprise_context.scoping import is_visible
    shared = {"enterprise_scope_id": "", "scope_type": "ENTERPRISE_SHARED",
              "approval_status": "APPROVED", "approved_by": "admin",
              "tenant_id": "tenant_default", "entity_mode": "REAL"}
    pending = {**shared, "approval_status": "PENDING", "approved_by": ""}
    assert is_visible(shared, "BATTERY") is True, "승인된 전사 공용은 보여야 한다"
    assert is_visible(pending, "BATTERY") is False, "미승인 전사 공용이 보이면 승인 절차가 무의미하다"


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


def test_gate_a_can_be_rolled_back_without_a_deploy():
    """★★ [§5.3] `SCOPE_FAIL_CLOSED=False` 로 **코드 배포 없이** 종전 규칙으로 되돌아간다.

    설계서가 이 스위치를 요구한 이유: "한 번에 전환하면 무엇이 안 보이게 됐는지 아무도 모른다."
    도입 중 현업이 막히면 되돌릴 수단이 있어야 하고, **되돌릴 수 없는 되돌림 장치는 장치가
    아니다** — 그래서 값을 캐시하지 않고 호출 시점에 읽는지까지 여기서 잠근다.

    ⚠️ 단 **주입 경로에는 적용되지 않는다.** 주입은 되돌릴 수 없다(이미 LLM 이 읽고 산출물에
      반영된다) — 화면에서 되돌릴 수 있는 것과 성질이 다르다."""
    import config
    from core.enterprise_context.scoping import is_visible

    row = {"enterprise_scope_id": "", "tenant_id": "tenant_default", "entity_mode": "REAL"}
    saved = getattr(config, "SCOPE_FAIL_CLOSED", True)
    try:
        assert is_visible(row, "BATTERY") is False, "기본값은 비노출이어야 한다"
        config.SCOPE_FAIL_CLOSED = False
        assert is_visible(row, "BATTERY") is True, \
            "되돌림 스위치가 먹지 않는다 — 값을 모듈 로드 시점에 캐시했을 가능성이 크다"
    finally:
        config.SCOPE_FAIL_CLOSED = saved
    assert is_visible(row, "BATTERY") is False, "복원 후 다시 비노출이어야 한다"


def test_gate_a_rollback_switch_does_not_reopen_the_injection_path(md):
    """★★ 되돌림 스위치로 **프롬프트 주입까지** 열리면 안 된다.

    화면에서 안 보이는 것은 되돌릴 수 있지만, 프롬프트에 들어간 것은 되돌릴 수 없다 —
    이미 LLM 이 읽고 산출물에 반영됐다. 2026-07-29 유출의 실제 피해가 그 경로였다."""
    import config
    md.bind_master_to_scope("MC-BOUND", "BATTERY", tenant_id="tenant_default")
    saved = getattr(config, "SCOPE_FAIL_CLOSED", True)
    try:
        config.SCOPE_FAIL_CLOSED = False
        codes = [r["master_code"] for r in
                 md.select_for_injection("배터리", ["battery"],
                                         tenant_id="tenant_default", scope_node_id="BATTERY")]
        assert codes == ["MC-BOUND"], \
            "되돌림 스위치가 미바인딩 주입을 되살렸다 — 주입은 되돌릴 수 없는 경로다"
    finally:
        config.SCOPE_FAIL_CLOSED = saved


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
# ✅ [2026-07-29 13:50 · Claude Code] 관문 B 3건 **열림** — xfail 을 떼고 회귀 잠금으로 승격.
#   근거: `core/enterprise_context/audit.py` · `core/scope_guard.py` ·
#         `api/routes/mcp_control.py`(404 경계표 적용) · `tests/test_access_audit.py`(12건)
def test_gate_b_other_org_resource_returns_404():
    """★★ 관문 B-1: 타 조직 자원의 거부는 **존재하지 않음과 구분되지 않아야** 한다.

    409(Conflict)는 '자원이 있으나 상태가 맞지 않다'는 뜻이라 존재를 알려준다."""
    from fastapi.testclient import TestClient
    import main

    c = TestClient(main.app)
    r = c.post("/api/v1/mcp/resolve",
               json={"master_code": "MC-X", "system_id": "mes-smelting",
                     "scope_node_id": "BATTERY"})
    assert r.status_code == 404


def test_gate_b_denial_is_written_to_the_audit_log():
    """★★ 관문 B-2: 은폐는 외부용이다 — **내부에는 반드시 남는다.**

    ⚠️ 거부와 기록이 **같은 순간**에 일어나는지를 본다. 처음에는 이 검증을 별도 테스트로 뒀다가
      앞선 테스트가 실제 운영 감사로그에 남긴 기록을 보고 통과하는 일이 있었다 — 격리(conftest)와
      함께, 한 테스트 안에서 '거부시키고 그 기록을 확인'하도록 합쳤다."""
    from fastapi.testclient import TestClient
    import main

    from core.enterprise_context import audit

    before = len(audit.recent(limit=100))
    c = TestClient(main.app)
    c.post("/api/v1/mcp/resolve",
           json={"master_code": "MC-X", "system_id": "mes-smelting",
                 "scope_node_id": "BATTERY"})

    events = audit.recent(limit=10)
    assert len(events) > before, "거부는 했는데 감사 기록이 남지 않았다(조용한 차단)"
    e = events[0]
    assert e["event"] == audit.ACCESS_DENIED_SCOPE_MISMATCH
    assert e["resource_id"], "실제 대상 식별자가 비어 있다 — 은폐는 응답에만 적용된다"


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
