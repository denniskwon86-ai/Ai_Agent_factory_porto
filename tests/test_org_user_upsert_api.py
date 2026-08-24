# -*- coding: utf-8 -*-
"""★★★ `POST /api/v1/org/users` — **관리자 화면에서 사용자를 추가·수정한다.**

## 왜 생겼는가 (2026-08-24 실측)

라우트가 저장소로 인자를 **위치로** 넘기면서 `is_ai_admin` 을 빠뜨렸다. 그래서
`actor` 문자열이 `is_ai_admin` 자리에 들어갔고, 저장소가 `int('hikwon@lsmnm.com')` 을
시도하며 **500** 이 났다. 즉 관리자 화면에서 **사용자를 하나도 만들 수 없었다.**

⚠️ 이 결함은 화면에서만 드러난다 — 저장소 단위 시험은 이름으로 부르므로 통과한다.
  그래서 여기서 **라우트로** 부른다.

★ 위치 인자는 서명이 늘어나는 순간 조용히 어긋난다. 그 사실 자체를 마지막 시험이
  잠근다 — 새 칸이 생겨도 라우트가 이름으로 넘기면 깨지지 않는다.
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
    import api.routes.org_control as oc
    monkeypatch.setattr(oc, "org_directory", org, raising=False)
    #: ⚠️ 로그인 라우트도 **자기 참조**를 들고 있다 — 여기를 안 바꾸면 인증이 운영
    #:   조직을 보고 401 이 난다(격리가 반쪽이면 시험이 엉뚱한 곳에서 빨개진다).
    import api.routes.auth_control as ac
    monkeypatch.setattr(ac, "org_directory", org, raising=False)

    org.create_department("hq", "본사", parent_id="", scope_node_id="corp-afs", actor="t")
    org.upsert_user("boss@x.invalid", "관리자", primary_dept_id="hq",
                    is_admin=True, is_data_admin=True, actor="t")

    from main import app
    return TestClient(app), org


def _login(c, uid):
    from core.auth import DEFAULT_PASSWORD

    r = c.post("/api/v1/auth/login", json={"user_id": uid, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]          # ★ 봉투를 벗긴다


def _post(c, tok, body):
    return c.post("/api/v1/org/users", json=body, headers={"X-Session-Token": tok})


def test_관리자가_사용자를_추가한다(client):
    """★★★ 이것이 500 이었다. 「목록이 안 보인다」가 아니라 **만들 수가 없었다.**"""
    c, org = client
    tok = _login(c, "boss@x.invalid")
    r = _post(c, tok, {"user_id": "new@x.invalid", "display_name": "새 사람",
                       "primary_dept_id": "hq"})
    assert r.status_code == 200, r.text
    #: ★ 응답만 믿지 않는다 — 저장소에 실제로 있는지 본다.
    got = org.get_user("new@x.invalid")
    assert got is not None, "200 을 받았는데 저장소에 없다"
    assert got["display_name"] == "새 사람"
    assert got["primary_dept_id"] == "hq"


def test_행위자가_권한칸으로_새지_않는다(client):
    """⚠️⚠️ **결함의 정확한 모양.** `actor` 가 `is_ai_admin` 자리에 들어갔었다.

    ★ 「500 이 아니다」로는 부족하다 — 그 값이 **어디로 갔는지**를 본다."""
    c, org = client
    tok = _login(c, "boss@x.invalid")
    r = _post(c, tok, {"user_id": "plain@x.invalid", "display_name": "일반"})
    assert r.status_code == 200, r.text
    got = org.get_user("plain@x.invalid")
    for flag in ("is_admin", "is_data_admin", "is_ai_admin", "is_executive"):
        assert not got.get(flag), f"{flag} 가 켜져 있다 — 인자가 밀렸다: {got}"


def test_저장소가_받는_모든_권한칸을_화면에서_켤_수_있다(client):
    """★ 저장소에 있는데 라우트가 안 받는 칸이 있으면, 그 권한은 **DB 를 직접 고쳐야**
    켜진다. `is_ai_admin` 이 정확히 그 상태였다."""
    c, org = client
    tok = _login(c, "boss@x.invalid")
    r = _post(c, tok, {"user_id": "ai@x.invalid", "display_name": "AI 관리자",
                       "primary_dept_id": "hq", "is_ai_admin": True})
    assert r.status_code == 200, r.text
    got = org.get_user("ai@x.invalid")
    assert got.get("is_ai_admin"), got


def test_라우트는_저장소에_이름으로_넘긴다():
    """★★★ **위치 인자를 다시 쓰지 못하게 잠근다.**

    ⚠️ 위 세 시험은 «지금 서명» 에서만 유효하다. 저장소에 칸이 하나 더 생기면 위치
      호출은 또 조용히 밀리고, 그때 세 시험이 전부 통과할 수도 있다(밀린 값이 우연히
      불리언이면). 그래서 **호출 방식 자체**를 고정한다.
    """
    import inspect

    import api.routes.org_control as oc

    import core.org_directory as orgmod

    src = inspect.getsource(oc.upsert_user)
    #: 저장소가 **기본값을 가진 칸**(= 위치로 밀릴 수 있는 칸)은 전부 이름으로 넘겨야 한다.
    sig = inspect.signature(orgmod.OrgDirectory.upsert_user)
    optional = [n for n, prm in sig.parameters.items()
                if prm.default is not inspect.Parameter.empty]
    assert optional, "대조군 확인 — 기본값 있는 칸이 하나는 있어야 이 시험이 의미가 있다"
    missing = [n for n in optional if f"{n}=" not in src]
    assert not missing, (
        f"라우트가 {missing} 을(를) 이름으로 넘기지 않는다 — 위치로 넘기면 저장소 "
        f"서명이 늘어나는 순간 조용히 밀린다(그래서 actor 가 is_ai_admin 자리로 갔다).")
