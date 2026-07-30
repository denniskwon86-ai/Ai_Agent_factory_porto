"""[사용자 결정 2026-07-30] 감사로그 5년 보존 · admin 전용 열람 · 만료일 admin 변경.

이 파일이 잠그는 것:
  · 감사로그 열람은 **관리자만**(감사로그 자체가 민감정보 — 거부 시도 목록은 곧 자산 지도다)
  · 보존 기간은 5년이고 **자동 삭제하지 않는다**(조사 중인 증거를 지울 수 있다)
  · 정리는 예행이 기본 · 원본을 남긴다 · **정리 자체가 감사에 기록된다**
  · 만료일은 **코드 배포 없이** 바뀐다(관리자 화면) — 상수로 두면 하루 미루는 데도 배포가 필요하다
  · 형식이 깨진 만료일은 거부한다(문자열 비교라 **조용히 항상 만료/항상 유효**가 된다)
  · 정책 저장소가 없거나 깨져도 **코드 기본값**으로 동작한다(만료 없음이 되면 한시가 영구가 된다)
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enterprise_context import audit


@pytest.fixture()
def policy_env(tmp_path, monkeypatch):
    import core.scope_policy as sp
    monkeypatch.setattr(sp, "_POLICY_PATH", str(tmp_path / "scope_policy.json"))
    return sp


# ── 만료일: 관리자가 배포 없이 바꾼다 ───────────────────────────────────────
def test_default_applies_when_policy_store_is_empty(policy_env):
    """★★ 저장소가 없으면 **코드 기본값**으로 동작한다 — "만료 없음"이 되면 한시가 영구가 된다."""
    from core.enterprise_context.scoping import LEGACY_GRANDFATHER_UNTIL, policy_deadline
    assert policy_env.legacy_deadline() == LEGACY_GRANDFATHER_UNTIL
    assert policy_deadline() == LEGACY_GRANDFATHER_UNTIL


def test_broken_policy_file_falls_back_to_default(policy_env):
    """★ 깨진 정책 파일이 통제를 끄면 안 된다."""
    with open(policy_env._POLICY_PATH, "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    assert policy_env.legacy_deadline() == policy_env.legacy_deadline_default()


def test_admin_can_change_the_deadline_without_a_deploy(policy_env):
    """★★ 이행 기한은 현업 사정에 따라 조정된다 — 배포가 필요하면 사람들은 만료일을 아예 없앤다."""
    out = policy_env.set_legacy_deadline("2027-06-30", actor="admin@ls", reason="이행 지연")
    assert out["legacy_grandfather_until"] == "2027-06-30"
    assert policy_env.legacy_deadline() == "2027-06-30"
    assert "미뤘습니다" in out["note"], "미루는 결정의 대가를 알려야 한다"

    # 판정 함수가 **호출 시점에** 정책을 읽는다(캐시하면 재시작이 필요해진다).
    from core.enterprise_context.scoping import is_expired
    assert is_expired({"scope_type": "LEGACY_UNSCOPED"}, today="2027-01-01") is False
    assert is_expired({"scope_type": "LEGACY_UNSCOPED"}, today="2027-12-31") is True


def test_row_level_deadline_still_wins(policy_env):
    """★ 행에 적힌 만료일이 전역 정책을 이긴다 — 부서마다 정리 속도가 다르다."""
    policy_env.set_legacy_deadline("2027-06-30", actor="admin@ls")
    from core.enterprise_context.scoping import legacy_deadline
    assert legacy_deadline({"effective_to": "2026-03-31"}) == "2026-03-31"
    assert legacy_deadline({}) == "2027-06-30"


def test_malformed_deadline_is_refused(policy_env):
    """★★ 만료 판정은 문자열 비교다 — 형식이 깨지면 통제가 **조용히** 꺼진다."""
    for bad in ("2027/06/30", "27-06-30", "다음달", "", "2027-13-45"):
        with pytest.raises(policy_env.ScopePolicyError):
            policy_env.set_legacy_deadline(bad, actor="admin@ls")
    assert policy_env.legacy_deadline() == policy_env.legacy_deadline_default()


def test_deadline_change_requires_an_actor_and_is_audited(policy_env):
    """★★ 만료일을 미루는 것은 통제를 느슨하게 하는 결정이다 — 책임자가 남아야 한다."""
    with pytest.raises(policy_env.ScopePolicyError, match="변경자 식별"):
        policy_env.set_legacy_deadline("2027-01-01", actor="")

    before = len(audit.recent(limit=200))
    policy_env.set_legacy_deadline("2027-01-01", actor="admin@ls", reason="현업 요청")
    events = audit.recent(limit=5)
    assert len(events) > before
    assert events[0]["event"] == audit.SCOPE_BINDING_CHANGED
    assert events[0]["resource_id"] == "legacy_grandfather_until"
    assert "->" in (events[0]["detail"] or ""), "무엇에서 무엇으로 바뀌었는지 남아야 한다"


def test_history_is_kept_for_reversal(policy_env):
    """★ 되돌릴 수 있어야 한다 — 이전 값이 없으면 무엇으로 돌아갈지 모른다."""
    policy_env.set_legacy_deadline("2027-01-01", actor="a@ls")
    policy_env.set_legacy_deadline("2026-09-30", actor="b@ls", reason="앞당김")
    pol = policy_env.policy()
    assert pol["legacy_grandfather_until"] == "2026-09-30" and pol["is_default"] is False
    assert [h["to"] for h in pol["history"]][:2] == ["2026-09-30", "2027-01-01"]
    assert pol["history"][0]["from"] == "2027-01-01"


# ── 감사로그 보존 5년 ───────────────────────────────────────────────────────
def _log(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_retention_report_counts_expired_without_deleting(tmp_path):
    """★★ 지우기 전에 **무엇을 지우는지** 본다. 자동 삭제는 조사 중인 증거를 지울 수 있다."""
    p = str(tmp_path / "audit.jsonl")
    _log(p, [{"ts": "2019-01-01T00:00:00", "event": "X"},
             {"ts": "2026-07-30T00:00:00", "event": "Y"}])
    rep = audit.retention_report(p, today="2026-07-30T00:00:00")
    assert audit.RETENTION_YEARS == 5
    assert rep["total"] == 2 and rep["expired"] == 1
    assert rep["cutoff"].startswith("2021-")
    assert "자동 삭제하지 않습니다" in rep["note"]
    assert len(audit.read_events(p)) == 2, "보고서가 파일을 바꿨다"


def test_prune_is_dry_run_by_default(tmp_path):
    p = str(tmp_path / "audit.jsonl")
    _log(p, [{"ts": "2019-01-01T00:00:00", "event": "X"}])
    out = audit.prune(apply=False, path=p, today="2026-07-30T00:00:00")
    assert out["applied"] is False and len(audit.read_events(p)) == 1


def test_prune_keeps_the_original_and_audits_itself(tmp_path):
    """★★★ 감사로그를 지우는 작업이 감사되지 않으면 그게 가장 큰 구멍이다."""
    p = str(tmp_path / "audit.jsonl")
    _log(p, [{"ts": "2019-01-01T00:00:00", "event": "OLD"},
             {"ts": "2026-07-30T00:00:00", "event": "NEW"}])
    before = len(audit.recent(limit=200))

    out = audit.prune(apply=True, path=p, today="2026-07-30T00:00:00")
    assert out["applied"] is True and out["removed"] == 1 and out["kept"] == 1
    kept = audit.read_events(p)
    assert [e["event"] for e in kept] == ["NEW"]

    archived = [f for f in os.listdir(tmp_path) if ".pruned-" in f]
    assert archived, "원본을 남기지 않았다 — 삭제는 되돌릴 수 없다"
    assert len(audit.read_events(str(tmp_path / archived[0]))) == 2

    # 정리 자체가 (운영) 감사로그에 남는다.
    assert len(audit.recent(limit=5)) > before
    assert audit.recent(limit=1)[0]["resource_type"] == "audit_log"


# ── admin 전용 열람 ─────────────────────────────────────────────────────────
def test_audit_routes_require_admin():
    """★★★ 감사로그 열람을 열어 두면 그것이 새로운 유출 경로다 — 거부 시도 목록은 곧 자산 지도다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.admin_control as ac
    from api.deps import Principal, current_principal
    from core.org_directory import AccessScope

    app = FastAPI()
    app.include_router(ac.router)

    def _as(scope):
        app.dependency_overrides[current_principal] = lambda: Principal(
            user_id="u@ls", scope=scope)

    c = TestClient(app)
    paths = ["/api/v1/admin/audit/events", "/api/v1/admin/audit/stats",
             "/api/v1/admin/audit/retention", "/api/v1/admin/scope-policy"]

    # 일반 사용자 → 403(전부)
    _as(AccessScope(unrestricted=False, user_id="u@ls"))
    for path in paths:
        assert c.get(path).status_code == 403, f"{path} 가 일반 사용자에게 열렸다"
    assert c.post("/api/v1/admin/audit/prune", json={}).status_code == 403
    assert c.put("/api/v1/admin/scope-policy/legacy-deadline",
                 json={"legacy_grandfather_until": "2027-01-01"}).status_code == 403

    # 관리자 → 통과
    _as(AccessScope(unrestricted=False, user_id="admin@ls", can_edit_org=True))
    for path in paths:
        assert c.get(path).status_code == 200, f"{path} 가 관리자에게 막혔다"


def test_admin_routes_require_identity():
    """★ 권한만 보고 행위자를 안 남기면 "누가 정책을 바꿨나"에 답할 수 없다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.admin_control as ac
    from api.deps import Principal, current_principal
    from core.org_directory import AccessScope

    app = FastAPI()
    app.include_router(ac.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="", scope=AccessScope(unrestricted=True))
    c = TestClient(app)
    r = c.get("/api/v1/admin/audit/events")
    assert r.status_code == 401 and "사용자 식별" in r.text
