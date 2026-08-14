"""★★★ [P0-1C] 테스트 인증 전략 — **운영 코드가 헤더를 믿지 않게 하되 테스트는 살린다.**

## 왜 이 파일이 필요한가

`ORG_TRUST_HEADER=True` 인 동안 서버는 `X-Factory-User` 헤더와 `?as_user=` 쿼리를 **그대로
믿는다.** 즉 로그인 화면이 있어도 헤더 한 줄로 관리자 API 를 읽을 수 있다(2026-08-09 실서버
실측: HTTP 200). 그 스위치를 끄는 것이 P0-1C 다.

그런데 기존 테스트 **34개 파일·49곳**이 그 헤더로 사용자를 지정한다. 스위치만 끄면 전부
익명이 되어 무더기로 깨진다.

## 승인된 3분류 (Supervisor, 2026-08-09)

    일반 기능 테스트   → dependency_overrides 로 principal 주입   ← 이 플러그인
    인증·권한 테스트   → 실제 로그인 + X-Session-Token
    레거시 스위치 테스트 → 그 테스트에서만 ORG_TRUST_HEADER=True

⚠️⚠️ **인증 테스트까지 override 하면 실제 인증 연결 결함을 숨긴다.** 그래서 이 플러그인은
  `@pytest.mark.real_auth` 가 붙은 테스트에서는 **스스로 물러난다.**

## 왜 conftest.py 가 아니라 플러그인인가

`tests/conftest.py` 는 지금 **다른 세션이 수정 중**이다(`git status: M`). 같은 파일을 동시에
고치면 그쪽 작업과 충돌한다 — 바로 그 이유로 이 세션에서 이미 한 번 HEAD 를 깨뜨렸다.
새 파일 + `pytest.ini` 한 줄이면 충돌 없이 같은 일을 한다.

## ⚠️ 이 override 가 «실서버와 다른 세계» 를 만들지 않게

override 는 **헤더를 읽어** principal 을 만든다. 즉 테스트 안에서는 여전히 헤더가 먹는다 —
편의를 위해서다. 그러나 **운영 코드(`api/deps.py`)는 그 헤더를 보지 않는다.** 둘이 갈리는
지점이 바로 위험한 곳이므로, 그 경계를 지키는 테스트를 따로 둔다:

  · `tests/test_org_trust_header.py`  — 운영 모드에서 헤더·쿼리 사칭이 401 인가
  · `tests/test_sse_ticket.py`        — 실제 세션으로만 티켓·SSE 가 열리는가
"""
from __future__ import annotations

import pytest
from fastapi import Request

#: ⚠️⚠️ `Request` 는 **반드시 모듈 전역에서 import** 한다. 이 파일은 `from __future__ import
#  annotations` 를 쓰므로 주석이 문자열로 남고, FastAPI 는 그 문자열을 **함수의 모듈 전역**에서
#  해석한다. 함수 안에서만 import 하면 이름을 못 찾아 «타입 모를 쿼리 파라미터» 로 처리하고,
#  모든 요청이 `422 missing query request_obj` 가 된다 — 2026-08-09 실제로 217건이 그렇게 깨졌다.


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_auth: 이 테스트는 principal override 없이 **실제 세션**으로 인증한다."
        " 인증·권한 경로 자체를 검증할 때 쓴다.",
    )


@pytest.fixture(autouse=True)
def _principal_override(request):
    """모든 테스트에서 `current_principal` 을 override 한다.

    요청 헤더(`X-Factory-User`)나 쿼리(`as_user`)에서 사용자를 읽어 principal 을 만든다.
    **운영 경로와 달리 여기서는 헤더를 신뢰한다** — 테스트 편의이며, 그래서 인증 테스트는
    이 fixture 를 쓰지 않는다(`@pytest.mark.real_auth`).

    ⚠️ 권한(scope) 은 **실제 `org_directory` 로 해석한다.** 여기서 권한까지 가짜로 만들면
      권한 테스트가 통째로 무의미해진다 — 우리가 대신하는 것은 「누구인가」뿐이다.
    """
    if request.node.get_closest_marker("real_auth"):
        yield          # 인증 테스트는 실제 경로를 그대로 쓴다
        return

    import config
    from fastapi import HTTPException
    from api.deps import Principal, _enforced, _session_hash, current_principal
    from main import app

    def _override(request_obj: Request) -> Principal:
        uid = (request_obj.headers.get(getattr(config, "ORG_USER_HEADER", "X-Factory-User"), "")
               or request_obj.headers.get("X-User-Id", "")
               or request_obj.query_params.get("as_user", "")
               or getattr(config, "ORG_DEFAULT_USER_ID", "")).strip()
        #: 세션 토큰이 함께 왔다면 그쪽을 우선한다 — 실제 로그인 흐름을 섞어 쓰는 테스트가 있다.
        tok = request_obj.headers.get("X-Session-Token", "")
        if tok:
            try:
                from core.auth import auth_store
                resolved = auth_store.resolve(tok)
                if resolved:
                    uid = resolved
            except Exception:
                pass
        from core.org_directory import org_directory
        #: ⚠️ 운영 경로(`api/deps.current_principal`)와 **같은 함수**로 권한을 만든다.
        #  여기서 다른 것을 쓰면 테스트가 통과해도 실서버 권한이 다르게 나온다.
        scope = org_directory.resolve_scope(uid)
        #: ★★ 익명 거부 규칙도 **운영과 같은 조건**을 그대로 쓴다(`_enforced` 를 직접 가져온다).
        #  이것을 빼면 「신원 없이 부르면 401」을 보는 테스트가 200 을 받고 조용히 통과한다 —
        #  일반 기능 파일 안에 그런 테스트가 섞여 있어서 실제로 1건이 그렇게 무력화됐다.
        if _enforced() and not scope.unrestricted and not uid:
            raise HTTPException(status_code=401, detail="사용자 식별 정보가 없습니다.")
        #: ★★★ [2026-08-14] **세션 해시도 운영과 같은 함수로 만든다.**
        #
        #  종전에는 이 줄이 없어서 override 가 만든 principal 의 `session_id` 가 **언제나 비어
        #  있었다.** 그러면 세션에 묶인 통제(앱 증명 발급·재사용 차단)는 테스트에서 **한 번도
        #  참인 적이 없고**, 그 사실이 「세션 없음」이라는 정상 거부처럼 보여 조용히 지나간다 —
        #  실제로 그 상태로 런타임 시험 전부가 401 이었고, 원인을 찾는 데 여러 번 헛짚었다.
        #
        #  ⚠️ 이 파일의 머리말이 경고한 바로 그 함정이다: 「override 가 실서버와 다른 세계를
        #    만들지 않게」. principal 에 필드가 늘면 **여기도 함께 늘려야** 한다.
        #: ⚠️ `requested_scope_node_id` 도 같은 이유로 빠져 있었다. 이것이 비면 화면이 고른
        #:   조직 범위가 **테스트에서는 언제나 «미지정»** 이 되고, 범위에 달린 통제는
        #:   전부 「미지정이라 막혔다」로만 관측된다.
        want = (request_obj.headers.get(
                    getattr(config, "ECM_SCOPE_HEADER", "X-Enterprise-Scope"), "")
                or request_obj.query_params.get("enterprise_scope", "") or "").strip()
        return Principal(user_id=uid, scope=scope, requested_scope_node_id=want,
                         session_id=_session_hash(request_obj))

    app.dependency_overrides[current_principal] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(current_principal, None)


@pytest.fixture(autouse=True)
def _isolate_auth_db(tmp_path, monkeypatch):
    """★★ 인증 저장소(`data/auth.db`)를 테스트마다 격리한다.

    `conftest.py` 가 기준정보·경영계획·앱데이터를 격리하면서 **인증만 빠져 있었다.**
    로그인이 2026-08-09 에 들어왔고 그 뒤로 세션을 만드는 테스트가 생겼으므로, 그대로 두면
    테스트가 **운영 계정 DB에 세션·비밀번호를 쓴다.** 실제 인원의 자격 증명이 담기는 곳이다.

    ⚠️ `_ready` 도 함께 비운다 — 그 값이 남아 있으면 새 경로에 DDL 을 돌리지 않고
      «no such table» 이 된다(다른 격리 fixture 들이 같은 이유로 같은 일을 한다).
    """
    from core.auth import auth_store
    monkeypatch.setattr(auth_store, "db_path", str(tmp_path / "auth.db"), raising=False)
    monkeypatch.setattr(auth_store, "_ready", "", raising=False)
    yield
