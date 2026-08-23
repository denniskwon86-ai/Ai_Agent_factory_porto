# -*- coding: utf-8 -*-
"""★★★ `PATCH /api/v1/auth/me` — **자기 표시 이름만** 바꾼다.

## 왜 생겼는가 (2026-08-23 사용자 지적)

이름을 바꾸는 유일한 경로가 `POST /org/users` 였고 거기에는 `assert_can_edit_org` 가
걸려 있다. 즉 **조직 관리자가 아니면 자기 이름조차 못 바꿨다.**

## 이 시험이 지키는 경계

  · 자기 것만 — 대상 사용자를 인자로 받지 않는다
  · 표시 이름만 — 권한 표식·소속 부서는 그대로여야 한다
  · 모르는 칸은 **조용히 무시하지 않고 거절**한다(`extra="forbid"`)

⚠️ 가장 위험한 회귀는 **권한이 조용히 꺼지는 것**이다. `upsert_user` 는 전체를 덮어쓰므로,
  현재 값을 읽지 않고 기본값으로 부르면 `is_admin` 이 False 가 된다. 그 상태는 오류를
  내지 않고 «이름만 바꿨는데 관리자가 아니게 되는» 형태로 나타난다 — 반드시 단언한다.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """⚠️ 인증·조직 저장소를 **파일 경계**로 격리한다 — 운영 `data/` 를 건드리지 않는다."""
    import core.auth as auth_mod
    import core.org_directory as orgmod
    from core.org_directory import OrgDirectory

    auth_mod.auth_store.db_path = str(tmp_path / "auth.db")
    org = OrgDirectory(db_path=str(tmp_path / "org.db"))
    monkeypatch.setattr(orgmod, "org_directory", org, raising=False)

    import api.deps as deps
    monkeypatch.setattr(deps, "org_directory", org, raising=False)
    import api.routes.auth_control as ac
    monkeypatch.setattr(ac, "org_directory", org, raising=False)

    org.create_department("hq", "본사", parent_id="", scope_node_id="corp-afs", actor="t")
    org.upsert_user("boss@x.invalid", "옛 이름", primary_dept_id="hq",
                    is_admin=True, is_data_admin=True, actor="t")
    org.upsert_user("other@x.invalid", "남", primary_dept_id="hq", actor="t")

    from main import app
    return TestClient(app), org


def _login(c, uid):
    from core.auth import DEFAULT_PASSWORD
    r = c.post("/api/v1/auth/login", json={"user_id": uid, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]      # ★ 봉투를 벗긴다


def test_changes_own_name(client):
    c, org = client
    tok = _login(c, "boss@x.invalid")
    r = c.patch("/api/v1/auth/me", json={"display_name": "새 이름"},
                headers={"X-Session-Token": tok})
    assert r.status_code == 200, r.text
    assert org.get_user("boss@x.invalid")["display_name"] == "새 이름"


def test_does_not_silently_drop_admin_flags(client):
    """⚠️⚠️ 이름만 바꿨는데 **관리자가 아니게 되면** 안 된다.

    `upsert_user` 는 전체를 덮어쓴다 — 현재 값을 읽지 않으면 여기서 권한이 꺼진다."""
    c, org = client
    tok = _login(c, "boss@x.invalid")
    before = org.get_user("boss@x.invalid")
    assert before["is_admin"] and before["is_data_admin"], "대조군 확인 — 원래 관리자여야 한다"
    c.patch("/api/v1/auth/me", json={"display_name": "이름만"},
            headers={"X-Session-Token": tok})
    after = org.get_user("boss@x.invalid")
    assert after["is_admin"] is True or after["is_admin"] == 1, after
    assert after["is_data_admin"] is True or after["is_data_admin"] == 1, after
    assert after["primary_dept_id"] == before["primary_dept_id"]


def test_cannot_target_another_user(client):
    """대상을 지정하는 칸이 **아예 받아들여지지 않는다** — 조용히 무시되지도 않는다."""
    c, org = client
    tok = _login(c, "boss@x.invalid")
    r = c.patch("/api/v1/auth/me",
                json={"display_name": "탈취", "user_id": "other@x.invalid"},
                headers={"X-Session-Token": tok})
    assert r.status_code == 422, r.text
    assert org.get_user("other@x.invalid")["display_name"] == "남"


def test_cannot_escalate_via_extra_fields(client):
    """⚠️ `is_admin` 을 끼워 보내면 **거절**한다. 무시하면 호출자는 «올렸다» 고 믿는다."""
    c, org = client
    tok = _login(c, "other@x.invalid")
    r = c.patch("/api/v1/auth/me", json={"display_name": "나", "is_admin": True},
                headers={"X-Session-Token": tok})
    assert r.status_code == 422, r.text
    assert not org.get_user("other@x.invalid")["is_admin"]


def test_non_admin_can_change_own_name(client):
    """★ 이 라우트가 생긴 이유 그 자체 — 관리자가 아니어도 자기 이름은 바꾼다."""
    c, org = client
    tok = _login(c, "other@x.invalid")
    r = c.patch("/api/v1/auth/me", json={"display_name": "내가 고친 이름"},
                headers={"X-Session-Token": tok})
    assert r.status_code == 200, r.text
    assert org.get_user("other@x.invalid")["display_name"] == "내가 고친 이름"


def test_anonymous_is_rejected(client):
    c, org = client
    r = c.patch("/api/v1/auth/me", json={"display_name": "익명"})
    assert r.status_code in (401, 403), r.text


def test_blank_name_is_rejected(client):
    c, org = client
    tok = _login(c, "boss@x.invalid")
    r = c.patch("/api/v1/auth/me", json={"display_name": "   "},
                headers={"X-Session-Token": tok})
    assert r.status_code == 400, r.text
    assert org.get_user("boss@x.invalid")["display_name"] == "옛 이름"
