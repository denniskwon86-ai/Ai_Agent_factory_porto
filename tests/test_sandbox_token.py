"""[M2 §4.3] VIRTUAL Sandbox capability token — **권한 승급이 아니다.**

이 파일이 잠그는 것:
  · 토큰은 **REAL 데이터를 한 조각도** 열지 않는다 (이것이 "승급이 아니다"의 실질)
  · 토큰 없이는 `SANDBOX` 행이 열리지 않는다 — 조직 권한이 아무리 높아도
  · 만료된 토큰은 거부되고 **감사에 남는다**(만료 재사용은 침해 신호다)
  · 쓰기에는 통하지 않는다(읽기 전용)
  · 긴 만료를 요청할 수 없다(세션 토큰이 상시 권한이 되는 것을 막는다)
  · 발급·사용·만료가 전부 감사에 남는다(추적되지 않는 임시 권한은 뒷문이다)
  · 감사로그·목록에 **토큰 전문을 싣지 않는다**(로그가 곧 자격증명이 된다)
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enterprise_context.scoping import SANDBOX, is_visible
from core.sandbox_token import (DEFAULT_TTL_MINUTES, MAX_TTL_MINUTES, SandboxTokenError,
                               SandboxTokenStore)

VSCOPE = "VIRT_COMPETITOR_A"


@pytest.fixture()
def store():
    return SandboxTokenStore()


def _vrow(scope=VSCOPE):
    return {"scope_type": SANDBOX, "entity_mode": "VIRTUAL", "tenant_id": "tenant_default",
            "owner_organization_id": scope}


def _rrow(scope=VSCOPE):
    """같은 조건인데 **REAL** 인 행 — 토큰이 이것을 열면 승급이 된 것이다."""
    return {"scope_type": SANDBOX, "entity_mode": "REAL", "tenant_id": "tenant_default",
            "owner_organization_id": scope}


# ── 승급이 아니다 ───────────────────────────────────────────────────────────
def test_token_opens_virtual_row(store):
    """★ 가상 문맥에서는 토큰으로 열린다 — 그게 이 토큰의 존재 이유다."""
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE)
    assert t["capability"] == "read" and t["entity_mode"] == "VIRTUAL"
    assert store.allows(t["token"], _vrow(), VSCOPE) is True


def test_token_never_opens_real_data(store):
    """★★ 토큰은 **REAL 데이터에 대한 권한을 한 조각도** 주지 않는다.

    가상 실험을 하려고 실제 권한을 올리면 실험이 끝난 뒤에도 그 권한이 남는다 —
    임시로 준 권한이 영구가 되는 것이 이 저장소가 이미 겪은 유형이다."""
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE)
    assert store.allows(t["token"], _rrow(), VSCOPE) is False


def test_sandbox_row_is_closed_without_token():
    """★★ 조직 권한이 아무리 높아도 토큰 없이는 열리지 않는다."""
    assert is_visible(_vrow(), VSCOPE, entity_mode="VIRTUAL") is False
    assert is_visible(_vrow(), VSCOPE, entity_mode="VIRTUAL", sandbox_token="") is False


def test_sandbox_row_opens_through_is_visible_with_token(monkeypatch, store):
    """★ 판정 단일 지점(`is_visible`)을 통해서도 같은 규칙이 적용된다 —
    두 곳에서 판정하면 반드시 어긋난다."""
    import core.sandbox_token as mod
    monkeypatch.setattr(mod, "sandbox_tokens", store)
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE)

    assert is_visible(_vrow(), VSCOPE, entity_mode="VIRTUAL",
                      sandbox_token=t["token"]) is True
    # REAL 문맥 조회는 토큰이 있어도 열리지 않는다(entity_mode 불일치에서 이미 막힌다).
    assert is_visible(_rrow(), VSCOPE, entity_mode="REAL", sandbox_token=t["token"]) is False


def test_token_is_scoped_to_its_virtual_org(store):
    """★ 다른 가상 조직 범위에는 통하지 않는다 — 범위 없는 토큰은 '전부 허용'이다."""
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE)
    assert store.allows(t["token"], _vrow("OTHER_VIRT"), "OTHER_VIRT") is False


def test_token_does_not_work_for_writes(store):
    """★★ 쓰기 토큰은 존재하지 않는다 — 가상 실험이 실제 데이터를 바꿀 경로는 없어야 한다."""
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE)
    assert store.allows(t["token"], _vrow(), VSCOPE, capability="write") is False


# ── 만료 ────────────────────────────────────────────────────────────────────
def test_expired_token_is_refused_and_audited(store):
    """★★ 만료된 토큰은 거부되고 **감사에 남는다.**

    만료된 토큰으로 계속 두드리는 것은 "세션이 끝난 줄 모르는 클라이언트"이거나 **재사용
    시도**이고, 둘을 구분하려면 기록이 있어야 한다."""
    from core.enterprise_context import audit
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE, ttl_minutes=1)
    # 만료를 시계 조작 없이 만든다 — 저장된 만료시각을 과거로 바꾼다.
    store._tokens[t["token"]]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    before = len(audit.recent(limit=200))
    assert store.resolve(t["token"]) is None
    assert store.allows(t["token"], _vrow(), VSCOPE) is False

    events = audit.recent(limit=5)
    assert len(events) > before
    assert events[0]["event"] == audit.SANDBOX_TOKEN_EXPIRED
    assert events[0]["outcome"] == "denied"


def test_long_ttl_is_refused(store):
    """★ 긴 만료는 세션 토큰이 아니라 상시 권한이다."""
    with pytest.raises(SandboxTokenError, match=f"최대 {MAX_TTL_MINUTES}분"):
        store.issue(actor="a@ls", scope_node_id=VSCOPE, ttl_minutes=MAX_TTL_MINUTES + 1)
    assert store.issue(actor="a@ls", scope_node_id=VSCOPE)["ttl_minutes"] == DEFAULT_TTL_MINUTES


def test_revoke_kills_token_immediately(store):
    """★ 만료를 기다리지 않고 끊을 수단이 없으면 사고에 대응할 수 없다."""
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE)
    assert store.revoke(t["token"], actor="admin@ls") is True
    assert store.allows(t["token"], _vrow(), VSCOPE) is False
    assert store.revoke(t["token"]) is False, "이미 회수된 것은 False"


def test_unknown_token_is_refused(store):
    assert store.resolve("sbx_nope") is None
    assert store.allows("sbx_nope", _vrow(), VSCOPE) is False
    assert store.allows("", _vrow(), VSCOPE) is False


# ── 발급 검증 ───────────────────────────────────────────────────────────────
def test_issue_requires_actor_and_scope(store):
    """★ 누구에게 발급했는지 없는 임시 권한은 뒷문이고, 범위 없는 토큰은 '전부 허용'이다."""
    with pytest.raises(SandboxTokenError, match="발급 대상"):
        store.issue(actor="", scope_node_id=VSCOPE)
    with pytest.raises(SandboxTokenError, match="가상 조직 범위"):
        store.issue(actor="a@ls", scope_node_id="")


# ── 관측 ────────────────────────────────────────────────────────────────────
def test_issue_and_use_are_both_audited(store):
    """★★ 발급만 남기면 "받아 갔지만 쓰지 않았다"와 구분되지 않는다."""
    from core.enterprise_context import audit
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE, purpose="경쟁사 시나리오 검토")
    assert audit.recent(limit=1)[0]["event"] == audit.SANDBOX_TOKEN_ISSUED

    store.allows(t["token"], _vrow(), VSCOPE)
    used = audit.recent(limit=1)[0]
    assert used["event"] == audit.SANDBOX_TOKEN_USED and used["outcome"] == "allowed"
    assert "use_count=1" in (used["detail"] or "")


def test_audit_and_listing_never_carry_the_full_token(store):
    """★★ 감사로그·목록에 토큰 전문을 실으면 **로그가 곧 자격증명**이 된다."""
    from core.enterprise_context import audit
    t = store.issue(actor="analyst@ls", scope_node_id=VSCOPE)
    e = audit.recent(limit=1)[0]
    assert t["token"] not in str(e), "감사로그에 토큰 전문이 남았다"
    assert e["resource_id"].endswith("…")

    listed = store.active()
    assert listed and t["token"] not in str(listed), "목록에 토큰 전문이 실렸다"


def test_active_lists_live_tokens_and_drops_expired(store):
    """★ "지금 열려 있는 임시 권한이 무엇인가"에 답할 수 없으면 임시 권한을 운영할 수 없다."""
    a = store.issue(actor="a@ls", scope_node_id=VSCOPE)
    b = store.issue(actor="b@ls", scope_node_id=VSCOPE)
    store._tokens[b["token"]]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    rows = store.active()
    assert len(rows) == 1 and rows[0]["actor"] == "a@ls"
    assert len(store.active(actor="a@ls")) == 1
    assert store.active(actor="nobody@ls") == []
    assert a["token"] in store._tokens


# ── API ─────────────────────────────────────────────────────────────────────
def test_sandbox_routes_are_reachable():
    """★ 라우터를 등록하지 않으면 모듈 전체가 장식이다."""
    from fastapi.testclient import TestClient
    import main

    c = TestClient(main.app)
    assert c.get("/api/v1/sandbox/tokens").status_code != 404


def test_api_refuses_anonymous_issue():
    """★ 식별 없는 임시 권한 발급은 401 — 누구에게 줬는지 모르는 토큰은 추적이 불가능하다."""
    from fastapi.testclient import TestClient
    import config
    import main

    saved = getattr(config, "ORG_DEFAULT_USER_ID", "")
    config.ORG_DEFAULT_USER_ID = ""
    try:
        c = TestClient(main.app)
        r = c.post("/api/v1/sandbox/token", json={"scope_node_id": VSCOPE})
        assert r.status_code == 401
    finally:
        config.ORG_DEFAULT_USER_ID = saved
