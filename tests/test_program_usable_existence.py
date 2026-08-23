# -*- coding: utf-8 -*-
"""★★★ `GET /programs/{id}/usable` — **없는 프로그램에 「써도 된다」고 답하지 않는다.**

## 무엇을 잡는 시험인가 (2026-08-23 실측)

    GET /api/v1/programs/__없는id__/usable
      → {"usable": true, "status": "active", "recorded": false}

수명주기표(`program_status`)는 «관리자가 중단시켰는가» 만 기록한다. 기록이 없으면
「이 기능 이전에 게시된 프로그램」으로 보고 `active` 로 답한다 — **그 하위호환은 의도된
것이다.** 문제는 그 판정이 «존재하지 않는다» 와 «예전에 게시됐다» 를 구분하지 못한 것이다.

★ `recorded: false` 가 유일한 단서였지만, `usable` 만 보고 실행 버튼을 여는 호출자는 그
  칸을 읽지 않는다. 「예」라고 답해 놓고 각주로 부인하는 것은 답이 아니다.

⚠️ 이 시험은 **두 방향**을 함께 본다. 「없는 것은 false」만 단언하면 하위호환을 깨뜨려도
  초록이다 — 「게시됐지만 기록이 없는 것은 여전히 true」를 같이 단언한다.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """⚠️ 라이브러리 뿌리를 tmp 로 돌린다 — 운영 `library/` 를 읽지 않는다."""
    import core.library_paths as lp
    monkeypatch.setattr(lp, "_LIBRARY_DIR", str(tmp_path / "library"), raising=False)

    import core.program_lifecycle as plm
    plm.program_lifecycle.db_path = str(tmp_path / "programs.db")

    from main import app
    return TestClient(app), tmp_path


def _publish(tmp_path, release_id):
    """★ 「게시되었다」의 정의는 `release.json` 의 존재다(`library_paths` 머리말)."""
    d = tmp_path / "library" / release_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "release.json").write_text(json.dumps({"release_id": release_id}),
                                    encoding="utf-8")


def _get(c, rid):
    r = c.get(f"/api/v1/programs/{rid}/usable",
              headers={"X-Factory-User": "hikwon@lsmnm.com"})
    return r.status_code, (r.json().get("data") or {})   # ★ 봉투를 벗긴다


def test_unpublished_id_is_not_usable(client):
    """없는 식별자는 **false** 다. 「없음」과 「사용 중단」을 사유로 가른다."""
    c, tmp = client
    st, d = _get(c, "__probe_nonexistent__")
    assert st == 200, st
    assert d.get("usable") is False, d
    assert "없" in (d.get("reason") or ""), d


def test_published_but_unrecorded_is_still_usable(client):
    """⚠️ **하위호환을 깨지 않는다.** 이 기능 이전에 게시된 프로그램은 여전히 쓸 수 있다.

    이 단언이 없으면 「전부 false 로 막기」로도 위 시험이 초록이 된다 — 그것은 통제가
    아니라 기능 파괴다."""
    c, tmp = client
    _publish(tmp, "REL-OLD")
    st, d = _get(c, "REL-OLD")
    assert st == 200, st
    assert d.get("usable") is True, d
    #: ★ 「관리자가 승인했다」로 오해하지 않도록 미기록 사실은 그대로 남아야 한다.
    assert d.get("recorded") is False, d


def test_disabled_release_is_not_usable(client):
    """관리자가 중단시킨 것은 게시돼 있어도 false — 종전 계약 그대로."""
    c, tmp = client
    _publish(tmp, "REL-STOP")
    from core.program_lifecycle import program_lifecycle
    program_lifecycle.set_status("REL-STOP", "disabled", "admin@x.invalid", "사유")
    st, d = _get(c, "REL-STOP")
    assert d.get("usable") is False, d
    assert d.get("status") == "disabled", d


def test_existence_and_disabled_give_different_reasons(client):
    """★ 두 「false」가 **같은 이유로 보이면 안 된다** — 사용자가 할 일이 다르다.

    없음 → 식별자를 확인한다 / 중단 → 관리자에게 대체본을 묻는다."""
    c, tmp = client
    _publish(tmp, "REL-STOP2")
    from core.program_lifecycle import program_lifecycle
    program_lifecycle.set_status("REL-STOP2", "disabled", "admin@x.invalid", "사유")
    _, none_ = _get(c, "REL-MISSING")
    _, stop = _get(c, "REL-STOP2")
    assert none_.get("reason") != stop.get("reason"), (none_, stop)
