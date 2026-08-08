"""[D-017 §9 P4-2] 조직별 운영 현황 — **거버넌스 콘솔에서 0은 「문제 없음」으로 읽힌다.**

이 화면은 정의상 «무엇이 안 되어 있는가» 를 모아 보여 준다. 그래서 원천 하나를 못 읽었을 때
0 을 찍으면 **가장 나쁜 방식으로 틀린다** — 사람은 그것을 「승인 대기 없음」·「위반 없음」으로
읽고 안심하며, 아무도 「왜 0인가」를 묻지 않는다.

`governance_block_reason` 은 같은 이유로 이 화면을 아무에게나 열지 않는다:
「어디가 비어 있는지는 그 자체로 보호해야 하는 정보」. 그 화면이 **틀린 0** 을 보여 주면
보호할 가치조차 없어진다.

★ 그래서 모든 지표는 `Metric` 이다 — 값과 «읽었는가» 를 함께 들고 다닌다.
"""
import pytest

from core import org_operations as oo


def _rec(**kw):
    base = {"owner_dept_id": "D1", "ok": True, "cost_estimate_usd": 0.01}
    base.update(kw)
    return base


# ── ① Metric — 읽지 못한 것과 0 을 가른다 ───────────────────────────────────
def test_unreadable_source_is_none_not_zero():
    """★★★ 이 파일 전체의 이유."""
    m = oo._metric(lambda: (_ for _ in ()).throw(OSError("db locked")))
    assert m.value is None and not m.known
    assert "db locked" in m.error


def test_zero_is_zero_when_actually_read():
    m = oo._metric(lambda: 0)
    assert m.value == 0 and m.known and not m.error


def test_programming_error_is_announced(capsys):
    """⚠️ 이름 오타를 «읽지 못함» 으로 위장하면 아무도 고치지 않는다.

    `agent_design_context._safe` 가 같은 함정에 빠졌던 것(모듈 이름 오타 → 「지식 허브를 읽지
    못했습니다」)을 되풀이하지 않는다."""
    m = oo._metric(lambda: (_ for _ in ()).throw(AttributeError("no attr")))
    assert not m.known
    assert "수집기 버그" in capsys.readouterr().out


# ── ② 사용량 — 부서 미상을 버리지 않는다 ────────────────────────────────────
def test_unattributed_org_is_kept():
    u = oo.usage_by_org([_rec(), _rec(owner_dept_id=""), _rec(owner_dept_id=None)])
    assert "(미상)" in [o["org"] for o in u["orgs"]]
    assert sum(o["calls"] for o in u["orgs"]) == 3, "호출이 사라졌다"
    assert u["coverage"]["without_org"] == 2
    assert "전체가 아닙니다" in u["coverage"]["note"]


def test_full_attribution_has_no_warning():
    """늘 경고하면 경고를 아무도 안 읽는다."""
    assert oo.usage_by_org([_rec(), _rec(owner_dept_id="D2")])["coverage"]["note"] == ""


def test_unpriced_calls_are_not_free():
    """0 으로 더하면 「공짜였다」는 거짓이 된다."""
    u = oo.usage_by_org([_rec(cost_estimate_usd=None), _rec(cost_estimate_usd=1.0)])
    o = u["orgs"][0]
    assert o["unpriced_calls"] == 1 and o["cost_usd"] == 1.0


def test_failure_rate_is_none_without_calls():
    """호출이 없으면 실패율은 **0% 가 아니라 «모름»** 이다."""
    u = oo.usage_by_org([])
    assert u["orgs"] == []
    assert u["coverage"]["attribution_rate"] is None


# ── ③ 정책 위반 0 을 «좋은 소식» 으로 읽지 않게 한다 ────────────────────────
def test_zero_denials_carries_a_caveat(monkeypatch):
    """★★ 「위반 0」은 통제가 지켜진 것일 수도, **통제가 없는 것**일 수도 있다."""
    monkeypatch.setattr(oo, "_denied_events",
                        lambda: {"total": 0, "by_kind": {}, "top_actors": []})
    out = oo.collect([], None)
    assert out["policy_denials"]["value"] == 0
    assert "통제가 걸려" in out["policy_denials"]["note"]


def test_nonzero_denials_has_no_caveat(monkeypatch):
    monkeypatch.setattr(oo, "_denied_events",
                        lambda: {"total": 3, "by_kind": {"식별 없음": 3}, "top_actors": []})
    out = oo.collect([], None)
    assert out["policy_denials"]["value"] == 3
    assert out["policy_denials"]["note"] == ""
    assert out["policy_denials"]["detail"]["by_kind"] == {"식별 없음": 3}


def test_denial_kinds_come_from_audit_constants():
    """★ 이벤트 문자열을 여기서 새로 적지 않는다 — `audit` 상수를 그대로 쓴다.

    ⚠️ 복사하면 상수가 바뀔 때 이 화면만 조용히 0 이 된다."""
    import inspect
    src = inspect.getsource(oo._denied_events)
    assert "audit.ACCESS_DENIED_SCOPE_MISMATCH" in src
    assert '"ACCESS_DENIED' not in src, "이벤트 문자열을 복사해 적고 있다"


# ── ④ 승인 대기 — 실패해도 0 이 되지 않는다 ─────────────────────────────────
def test_pending_failure_is_unknown_not_zero(monkeypatch):
    """★★★ 승인 대기 조회가 실패했는데 «0건» 이라고 하면 **아무도 승인하러 가지 않는다.**"""
    def _boom(*a, **kw):
        raise RuntimeError("asset store down")

    monkeypatch.setattr(oo, "_pending_assets", _boom)
    monkeypatch.setattr(oo, "_denied_events",
                        lambda: {"total": 0, "by_kind": {}, "top_actors": []})
    out = oo.collect([], None)
    a = out["pending_approvals"]["assets"]
    assert a["value"] is None and a["known"] is False
    assert "asset store down" in a["error"]


def test_promotion_pending_counts_unfinished_only():
    """★ 상태 문자열을 지어내지 않고 **끝나지 않은 것**을 센다.

    ⚠️ 「pending」 같은 이름을 가정하면 저장소가 다른 이름을 쓸 때 조용히 0 이 된다."""
    import inspect
    src = inspect.getsource(oo._pending_promotions)
    assert "done" in src and "promoted" in src


# ── ⑤ 라우트 배선 ───────────────────────────────────────────────────────────
def test_route_requires_governance_and_reuses_scope():
    """⚠️ 자격 판정을 새로 만들지 않는다 — 이 화면은 «전사 정비 상태» 이고 그 자격은
    `assert_governance_readable` 한 곳이 정한다."""
    import inspect

    import api.routes.telemetry_control as tc
    src = inspect.getsource(tc.telemetry_by_org)
    assert "assert_governance_readable(p)" in src
    assert "apply_scope(_read_records(project), p)" in src, "범위 규칙을 다시 만들고 있다"
    assert "viewer_scope_nodes(p)" in src, "자산 가시 범위를 넘기지 않는다"


def test_all_governance_console_routes_share_one_gate():
    """★★★ [2026-08-08 P2-4 역할별 실측] **세 형제 화면이 갈라져 있었다.**

    거버넌스 콘솔은 화면 하나가 아니라 셋이다 — 조직 운영 현황(`/orgs`) · 에이전트 집계
    (`/agents`) · 자산 위생(`/asset-hygiene`). 셋 다 「무엇이 안 되어 있는가」를 보여 주므로
    **같은 관문**을 지나야 한다.

    ⚠️ 실측에서 `/agents` 만 `assert_governance_readable` 이 빠져 **익명에게 200** 이 나갔다
      (형제 둘은 403). 에이전트별 비용·성공률은 「어느 에이전트가 얼마나 실패하는가」이고,
      P4-2 가 「어디가 비어 있는지는 그 자체로 보호 대상」이라고 규정한 정보와 같은 성격이다.
      **셋 중 하나만 열려 있으면 그 하나로 다 보인다.**

    ★ 라우트마다 자격을 새로 적으면 이렇게 한 곳이 빠진다 — 이 검사는 «같은 관문을 쓰는가»
      를 세 곳에서 한꺼번에 본다."""
    import inspect

    import api.routes.telemetry_control as tc
    missing = [name for name, fn in (
        ("telemetry_by_org", tc.telemetry_by_org),
        ("telemetry_by_agent", tc.telemetry_by_agent),
        ("asset_hygiene", tc.asset_hygiene),
    ) if "assert_governance_readable(p)" not in inspect.getsource(fn)]
    assert not missing, (
        "거버넌스 콘솔 화면인데 자격 관문을 지나지 않는다 — 이 경로로 다 보인다: "
        + ", ".join(missing))
