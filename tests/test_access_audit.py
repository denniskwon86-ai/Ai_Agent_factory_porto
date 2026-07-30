"""[M2 관문 B] 접근 감사 + 서버측 범위 계산 + 404 은폐.

관문 B 가 지켜야 하는 것은 **두 방향이 동시에** 성립하는 것이다.

  - 바깥으로는 **아무것도 알려주지 않는다**(404, 존재하지 않는 자원과 같은 응답)
  - 안으로는 **전부 남긴다**(누가·무엇을·어떤 범위로 시도했는가)

하나만 하면 각각 다른 방식으로 실패한다. 은폐만 하면 침해 시도를 영영 못 보고,
기록만 하면 존재가 새어 나간다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enterprise_context import audit
from core.scope_guard import resolve_effective_scope


@pytest.fixture(autouse=True)
def _audit_log(tmp_path, monkeypatch):
    """감사로그를 tmp 로 — 테스트가 운영 감사 기록을 오염시키면 그 로그는 증거가 못 된다."""
    monkeypatch.setattr(audit, "_LOG_PATH", str(tmp_path / "access_audit.jsonl"))
    monkeypatch.setattr(audit, "_write_failures", 0, raising=False)


# ── 감사 기록 계약 ───────────────────────────────────────────────────────────
def test_denial_records_the_real_resource_id():
    """★★ 응답은 404 로 은폐해도 **기록에는 실제 대상**이 남아야 한다.

    여기까지 비면 운영자는 "누군가 무언가를 시도했다"만 알고 끝난다."""
    audit.denied_scope("external_system", "mes-smelting", actor="bob",
                       actor_scopes=["MNM_BATTERY"], requested_scope="SMELTING")
    e = audit.recent(1)[0]
    assert e["event"] == audit.ACCESS_DENIED_SCOPE_MISMATCH
    assert e["resource_id"] == "mes-smelting"
    assert e["actor"] == "bob"


def test_requested_and_computed_scopes_are_both_kept():
    """★★ 요청값과 서버 계산값을 나란히 둬야 **권한 상승 시도**가 보인다.

    하나만 남기면 '정상 조회'와 '남의 범위를 적어 보낸 시도'가 같은 모양이 된다."""
    audit.denied_scope("mcp_resource", "MC-X@mes-smelting", actor="bob",
                       actor_scopes=["MNM_BATTERY"], requested_scope="MNM_COPPER")
    e = audit.recent(1)[0]
    assert e["requested_scope"] == "MNM_COPPER"        # 무엇을 요구했나
    assert e["actor_scopes"] == ["MNM_BATTERY"]        # 무엇이 허용됐나


def test_anonymous_actor_is_explicit_not_empty():
    """식별 없는 주체를 빈 문자열로 두면 **기록 누락과 구분되지 않는다**."""
    audit.record(audit.ACCESS_DENIED_UNAUTHENTICATED, "master_record", "RM-001")
    assert audit.recent(1)[0]["actor"] == audit.ANONYMOUS


def test_unknown_event_is_marked_not_silently_accepted():
    """자유 문자열을 그대로 받으면 같은 사건이 여러 이름으로 쌓여 집계가 무너진다."""
    audit.record("made_up_event", "x", "y")
    assert audit.recent(1)[0]["event"].startswith("UNKNOWN:")


def test_write_failure_is_counted_not_swallowed(monkeypatch):
    """★ 감사 기록의 유실 자체가 사건이다 — 조용히 넘기면 '거부가 없었다'는 거짓 안심을 준다."""
    monkeypatch.setattr(audit, "_LOG_PATH", os.path.join("Z:", "nope", "audit.jsonl"))
    assert audit.denied_scope("external_system", "x", actor="a") is False
    assert audit.stats()["write_failures"] >= 1


def test_broken_line_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "_LOG_PATH", str(tmp_path / "a.jsonl"))
    audit.denied_scope("external_system", "s1", actor="a")
    with open(tmp_path / "a.jsonl", "a", encoding="utf-8") as f:
        f.write('{"event": "broke\n')
    audit.denied_scope("external_system", "s2", actor="a")
    assert len(audit.read_events()) == 2


# ── 서버측 범위 계산 (관문 B-4) ──────────────────────────────────────────────
class _Scope:
    def __init__(self, dept_ids=(), unrestricted=False, primary=""):
        self.readable_dept_ids = frozenset(dept_ids)
        self.unrestricted = unrestricted
        self.primary_dept_id = primary


class _P:
    def __init__(self, user_id="u1", **kw):
        self.user_id = user_id
        self.scope = _Scope(**kw)


@pytest.fixture()
def org(monkeypatch):
    """부서 → 노드 해석과 운영 상속을 고정한다(조직도 자체는 test_ecm_e1 이 본다)."""
    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "resolve_scope_ref", lambda ref: {
        "battery": "MNM_BATTERY", "copper": "MNM_COPPER"}.get(ref, ref))
    monkeypatch.setattr(sc, "visible_scopes", lambda n, **kw: (
        {"MNM_BATTERY", "MNM"} if n == "MNM_BATTERY"
        else {"MNM_COPPER", "MNM"} if n == "MNM_COPPER" else {n}))


def test_client_supplied_scope_is_verified_not_trusted(org):
    """★★ 관문 B-4 — 남의 조직 코드를 적어 보내면 거부된다."""
    eff = resolve_effective_scope(_P(dept_ids=["battery"]), "MNM_COPPER")
    assert eff.denied is True
    assert "MNM_BATTERY" in eff.allowed_scopes


def test_own_scope_is_allowed(org):
    eff = resolve_effective_scope(_P(dept_ids=["battery"]), "MNM_BATTERY")
    assert eff.denied is False and eff.scope_node_id == "MNM_BATTERY"


def test_parent_scope_drilldown_is_allowed(org):
    """상위 조직(MNM) 문맥 조회는 **정당한 사용**이다 — 막으면 경영진 드릴다운이 사라진다."""
    eff = resolve_effective_scope(_P(dept_ids=["battery"]), "MNM")
    assert eff.denied is False and eff.scope_node_id == "MNM"


def test_unrestricted_principal_passes_through(org):
    """조직 미도입(무제한)에서 막으면 조직을 세우기도 전에 전 API 가 잠긴다."""
    eff = resolve_effective_scope(_P(unrestricted=True), "ANYTHING")
    assert eff.denied is False and eff.scope_node_id == "ANYTHING"


def test_no_requested_scope_does_not_silently_narrow(org):
    """★ 요청이 없으면 필터도 없다 — 주체 범위로 **자동 축소하지 않는다**.

    조용한 축소는 "왜 결과가 줄었는지" 아무도 모르게 만든다."""
    eff = resolve_effective_scope(_P(dept_ids=["battery"]), "")
    assert eff.denied is False and eff.scope_node_id == ""


def test_resolver_failure_is_fail_closed(monkeypatch):
    """리솔버 장애를 '전부 허용'으로 처리하면 그 장애가 곧 전사 유출이 된다."""
    import core.enterprise_context.scoping as sc

    def _boom(*a, **k):
        raise RuntimeError("resolver down")

    monkeypatch.setattr(sc, "resolve_scope_ref", _boom)
    monkeypatch.setattr(sc, "visible_scopes", _boom)
    eff = resolve_effective_scope(_P(dept_ids=["battery"]), "MNM_BATTERY")
    assert eff.denied is True and eff.allowed_scopes == []
