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


# ══════════════════════════════════════════════════════════════════════════
# 조직 권한 강제 전환 — 이 스위치가 오늘 만든 통제의 실제 가동 스위치다
# ══════════════════════════════════════════════════════════════════════════
class _FakeOrg:
    """조직 대역. `resolve_scope` 는 강제 여부에 따라 달라진다(실물과 같은 규약)."""

    def __init__(self, depts, users, enforce=False):
        self._d, self._u, self.enforce = depts, users, enforce

    def list_departments(self): return self._d
    def list_users(self): return self._u

    def resolve_scope(self, uid):
        from core.org_directory import AccessScope
        u = next((x for x in self._u if x["user_id"] == uid), None)
        if not self._d or not self._u or not self.enforce:
            return AccessScope(user_id=uid, unrestricted=True)
        if not u:
            return AccessScope(user_id=uid, unrestricted=False)
        if u.get("is_admin"):
            return AccessScope(user_id=uid, unrestricted=True, is_admin=True)
        dept = (u.get("primary_dept_id") or "").strip()
        return AccessScope(user_id=uid, unrestricted=False,
                           readable_dept_ids=frozenset({dept} if dept else set()))


def test_preflight_blocks_activation_without_an_admin(policy_env):
    """★★★ 관리자 없이 켜면 **첫 관리자를 만들 사람이 아무도 없어 시스템이 잠긴다**(실측 사고)."""
    from core.org_activation import preflight
    org = _FakeOrg([{"dept_id": "sales"}],
                   [{"user_id": "staff", "display_name": "S", "is_admin": 0,
                     "primary_dept_id": "sales"}])
    out = preflight(org)
    assert out["ready"] is False
    assert any("관리자 계정이 없습니다" in b for b in out["blockers"])
    assert "아직 켜지 마십시오" in out["note"]


def test_preflight_warns_about_test_accounts_and_unassigned(policy_env):
    """★★ [실측] 실 DB 의 사용자 4명이 전부 테스트 잔여물이었다(`admin`·`bob`·`exec`·`bob2`).

    그 상태로 강제를 켜면 테스트가 만든 `admin` 이 **전권을 갖는다.**"""
    from core.org_activation import preflight
    org = _FakeOrg(
        [{"dept_id": "sales"}],
        [{"user_id": "admin", "display_name": "Admin", "is_admin": 1, "primary_dept_id": ""},
         {"user_id": "bob", "display_name": "Bob", "is_admin": 0, "primary_dept_id": ""},
         {"user_id": "hikwon@lsmnm.com", "display_name": "권희권", "is_admin": 1,
          "primary_dept_id": "hq"}])
    out = preflight(org)
    assert out["ready"] is True, "관리자가 있으면 켤 수 있다"
    assert out["test_looking"] == 2 and out["unassigned"] == 2
    joined = " ".join(out["warnings"])
    assert "실제 권한을 갖습니다" in joined and "아무 부서 자료도 읽지 못합니다" in joined
    # 사용자별로 **켠 뒤 무엇을 읽는지**가 나와야 한다 — 켠 뒤에 놀라지 않게.
    assert {r["user_id"] for r in out["users_detail"]} == {"admin", "bob", "hikwon@lsmnm.com"}


def test_enforcement_switch_flips_and_invalidates_the_cache(policy_env, monkeypatch):
    """★★★ 권한 스코프는 캐시된다 — 무효화하지 않으면 스위치를 켜도 **아무 일도 안 일어난다.**

    재시작이 필요한 스위치는 사고 상황에서 되돌림 장치가 되지 못한다."""
    import core.org_directory as od

    calls = {"invalidated": 0}
    monkeypatch.setattr(od.org_directory, "_invalidate",
                        lambda: calls.__setitem__("invalidated",
                                                  calls["invalidated"] + 1))
    assert policy_env.org_enforce() is None, "미설정이면 None — 코드 기본값을 쓴다"

    out = policy_env.set_org_enforce(True, actor="admin@ls", reason="파일럿 준비")
    assert out["org_enforce"] is True and policy_env.org_enforce() is True
    assert calls["invalidated"] == 1, "권한 캐시를 비우지 않았다"
    assert "실제로 작동합니다" in out["note"]

    off = policy_env.set_org_enforce(False, actor="admin@ls", reason="사고 대응")
    assert policy_env.org_enforce() is False
    assert "작동하지 않습니다" in off["note"], "끄는 것의 대가를 알려야 한다"


def test_effective_enforcement_prefers_policy_over_config(policy_env, monkeypatch):
    """★ 정책이 코드 기본값을 이긴다 — 배포 없이 켜고 끌 수 있어야 한다.
    단 정책이 없으면 코드 기본값이다(정책 파일이 없다고 통제가 켜지거나 꺼지면 안 된다)."""
    import config
    from core.org_directory import _org_enforce_effective

    saved = getattr(config, "ORG_ENFORCE", False)
    try:
        config.ORG_ENFORCE = False
        assert _org_enforce_effective() is False          # 정책 미설정 → 코드 기본값
        policy_env.set_org_enforce(True, actor="admin@ls")
        assert _org_enforce_effective() is True           # 정책이 이긴다
        config.ORG_ENFORCE = True
        policy_env.set_org_enforce(False, actor="admin@ls")
        assert _org_enforce_effective() is False          # 끄는 것도 정책이 이긴다
    finally:
        config.ORG_ENFORCE = saved


def test_api_refuses_to_enable_when_preflight_blocks(policy_env, monkeypatch):
    """★★ 사전 점검을 통과하지 못하면 **409 로 거부**한다 — 잠금 사고를 막는 문이다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.admin_control as ac
    from api.deps import Principal, current_principal
    from core.org_directory import AccessScope

    monkeypatch.setattr(ac, "preflight",
                        lambda: {"blockers": ["관리자 계정이 없습니다."], "warnings": []})
    app = FastAPI()
    app.include_router(ac.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="admin@ls", scope=AccessScope(unrestricted=False, can_edit_org=True))
    c = TestClient(app)

    r = c.put("/api/v1/admin/org-enforcement", json={"enabled": True})
    assert r.status_code == 409 and "관리자 계정이 없습니다" in r.text
    assert "force=true" in r.text, "우회 방법을 알려줘야 막다른 길이 아니다"

    # 끄는 것은 점검 없이 허용된다 — 사고 상황에서 막히면 안 된다.
    assert c.put("/api/v1/admin/org-enforcement", json={"enabled": False}).status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# `/org/me` — 강제를 켠 뒤 **빈 화면의 이유**를 화면이 말할 수 있어야 한다
# ══════════════════════════════════════════════════════════════════════════
def _me_client(monkeypatch, *, enforced, user_id, registered, scope_kw=None,
               status="active"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.org_control as oc
    import core.org_directory as od
    from api.deps import Principal, current_principal
    from core.org_directory import AccessScope

    monkeypatch.setattr(od, "_org_enforce_effective", lambda: enforced)
    # ★ 대역도 실물과 같은 모양을 줘야 한다 — `status` 가 없으면 폐지 판정을 검증할 수 없고,
    #   대역이 실물과 다르면 그 테스트는 실물이 아니라 대역을 검증한다.
    monkeypatch.setattr(od.org_directory, "get_user",
                        lambda uid: ({"user_id": uid, "status": status}
                                     if (registered and uid) else None))
    monkeypatch.setattr(od.org_directory, "is_bootstrap", lambda: False)

    app = FastAPI()
    app.include_router(oc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id, scope=AccessScope(user_id=user_id, **(scope_kw or
                                                              {"unrestricted": False})))
    return TestClient(app)


def test_me_explains_why_lists_are_empty_when_anonymous(monkeypatch):
    """★★★ 강제를 켠 뒤 익명 사용자는 목록이 전부 빈다. 그 이유를 화면이 말하지 못하면
    사용자는 **"시스템이 고장났다"** 고 판단한다 — 오늘 내내 막아 온 조용한 실패다."""
    c = _me_client(monkeypatch, enforced=True, user_id="", registered=False)
    d = c.get("/api/v1/org/me").json()["data"]
    assert d["org_enforced"] is True and d["identified"] is False
    assert "익명으로 보고 있습니다" in d["access_note"]
    assert "자료가 없는 것이 아닙니다" in d["access_note"], "빈 목록의 이유를 말해야 한다"
    # ⚠️ [P0-1C] 종전 안내는 «우측 상단에서 사용자를 지정하십시오» 였다. 그 전환기는 로그인
    #   도입으로 사라졌고 헤더 신뢰도 껐다 — 지금 할 수 있는 행동은 로그인뿐이다. 이 테스트가
    #   보는 것은 **다음 행동을 말하는가** 이므로, 그 행동의 이름만 바뀐 것이다.
    assert "로그인" in d["access_note"], "다음 행동이 없으면 막다른 길이다"


def test_me_explains_unregistered_user(monkeypatch):
    """★★ 등록되지 않은 사용자는 식별은 됐지만 아무 부서도 못 읽는다 — 다른 안내가 필요하다."""
    c = _me_client(monkeypatch, enforced=True, user_id="ghost@ls", registered=False)
    d = c.get("/api/v1/org/me").json()["data"]
    assert d["identified"] is True and d["registered"] is False
    assert "등록되지 않은 사용자입니다" in d["access_note"]
    assert "사용자 등록·부서 배정을 요청" in d["access_note"]


def test_me_explains_unassigned_but_registered(monkeypatch):
    """★ 등록됐지만 부서가 없는 경우 — 요청할 것이 '부서 배정'이라고 정확히 말해야 한다."""
    c = _me_client(monkeypatch, enforced=True, user_id="staff@ls", registered=True)
    d = c.get("/api/v1/org/me").json()["data"]
    assert "부서가 배정되지 않았습니다" in d["access_note"]


def test_me_explains_retired_account_not_missing_dept(monkeypatch):
    """★★★ [2026-07-31 실측 결함] **폐지 계정에게 화면이 틀린 이유를 말하고 있었다.**

    실서버에서 폐지한 `admin` 으로 `/me` 를 부르니 권한은 정확히 0이었지만(고침이 동작했다)
    안내는 "부서가 배정되지 않았습니다" 였다. 판정은 맞고 **설명이 틀린** 경우다.

    ⚠️ 이 조합이 가장 고치기 어렵다: 사용자는 관리자에게 부서 배정을 요청하고, 관리자는 배정이
      이미 되어 있는 것을 보고 시스템 오류라고 판단한다. 실제 이유(계정 폐지)는 화면 어디에도
      없으므로 아무도 도달하지 못한다. 통제가 옳게 동작할 때조차 **설명이 틀리면 운영은 멈춘다.**
    """
    c = _me_client(monkeypatch, enforced=True, user_id="admin", registered=True,
                   status="retired")
    d = c.get("/api/v1/org/me").json()["data"]
    assert d["retired"] is True
    assert d["registered"] is False, "폐지는 권한 판정에서 미등록과 같게 취급한다"
    assert "폐지되었습니다" in d["access_note"]
    assert "부서 배정 문제가 아닙니다" in d["access_note"], "틀린 방향으로 안내하면 안 된다"
    assert "부서가 배정되지 않았습니다" not in d["access_note"]


def test_me_warns_when_enforcement_is_off(monkeypatch):
    """★★ 강제가 꺼진 상태도 **말해야 한다.** 통제가 작동한다고 착각하는 것이 더 위험하다."""
    c = _me_client(monkeypatch, enforced=False, user_id="staff@ls", registered=True,
                   scope_kw={"unrestricted": True})
    d = c.get("/api/v1/org/me").json()["data"]
    assert d["org_enforced"] is False
    assert "꺼져 있습니다" in d["access_note"] and "작동하지 않습니다" in d["access_note"]


def test_me_is_quiet_when_everything_is_fine(monkeypatch):
    """★ 정상 상태에서는 경고를 띄우지 않는다 — 항상 뜨는 경고는 아무도 읽지 않는다."""
    c = _me_client(monkeypatch, enforced=True, user_id="batt@ls", registered=True,
                   scope_kw={"unrestricted": False,
                             "readable_dept_ids": frozenset({"production_battery"})})
    d = c.get("/api/v1/org/me").json()["data"]
    assert d["access_note"] == ""


def test_retired_user_loses_all_access(tmp_path, monkeypatch):
    """★★★ [2026-07-30 실측 결함] **폐지가 권한을 제거하지 않고 있었다.**

    `list_users()` 는 `status='active'` 를 거르는데 `get_user()` 는 거르지 않아서, 폐지한 계정이
    권한을 그대로 유지했다 — 실측: 테스트 계정 `admin` 을 폐지한 뒤에도
    `resolve_scope('admin')` 이 `unrestricted=True`(**전권**)를 돌려줬다.

    ⚠️ 이건 목록에서만 사라지기 때문에 **더 위험하다.** 관리자는 정리했다고 믿는다."""
    import config
    from core.org_directory import OrgDirectory

    org = OrgDirectory(db_path=str(tmp_path / "org.db"))
    org.create_department("hq", "본사")
    org.create_department("sales", "영업", parent_id="hq")
    org.upsert_user("boss", "관리자", primary_dept_id="hq", is_admin=True)
    org.upsert_user("boss2", "관리자2", primary_dept_id="hq", is_admin=True)
    org.upsert_user("staff", "직원", primary_dept_id="sales")

    saved = getattr(config, "ORG_ENFORCE", False)
    try:
        config.ORG_ENFORCE = True
        assert org.resolve_scope("staff").readable_dept_ids == frozenset({"sales"})
        assert org.resolve_scope("boss").unrestricted is True

        # 폐지 → 권한이 **즉시** 사라져야 한다(캐시도 무효화된다).
        assert org.delete_user("staff") is True
        s = org.resolve_scope("staff")
        assert s.unrestricted is False and not s.readable_dept_ids, "폐지 후에도 부서를 읽는다"

        # 폐지된 **관리자**도 전권을 잃는다. 활성 관리자(boss2)를 남겨 둔다 —
        #   아래 테스트가 보여주듯 전원을 폐지하면 시스템이 부트스트랩으로 되돌아간다.
        assert org.delete_user("boss") is True
        b = org.resolve_scope("boss")
        assert b.unrestricted is False, "폐지된 관리자가 전권을 유지한다 — 실측된 결함"
        assert b.is_admin is False
    finally:
        config.ORG_ENFORCE = saved


def test_retiring_every_user_returns_to_bootstrap(tmp_path):
    """★★ 활성 사용자가 0명이 되면 **부트스트랩으로 되돌아간다**(전원 무제한).

    잠금 방지 장치이며 의도된 동작이다 — 아무도 없는 상태에서 강제하면 첫 관리자를 만들 사람이
    없다. 다만 **의도를 모르면 "폐지했는데 왜 다 보이나"로 읽힌다.**
    운영에서는 활성 관리자를 최소 1명 남겨 두는 것이 전제다(그래서 사전 점검이 관리자 존재를
    차단 조건으로 본다)."""
    import config
    from core.org_directory import OrgDirectory

    org = OrgDirectory(db_path=str(tmp_path / "org2.db"))
    org.create_department("hq", "본사")
    org.upsert_user("only", "유일", primary_dept_id="hq")
    saved = getattr(config, "ORG_ENFORCE", False)
    try:
        config.ORG_ENFORCE = True
        assert org.resolve_scope("only").unrestricted is False
        org.delete_user("only")
        assert org.is_bootstrap() is True
        assert org.resolve_scope("anyone").unrestricted is True, "부트스트랩 잠금 방지"
    finally:
        config.ORG_ENFORCE = saved
