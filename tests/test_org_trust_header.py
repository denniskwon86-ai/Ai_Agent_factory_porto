"""★★★ [P0-1C] 헤더 신뢰 스위치의 경계 — **로그인 옆문이 실제로 닫혔는가.**

## 이 파일이 지키는 것

2026-08-09 실서버 실측에서 이랬다.

    curl -H 'X-Factory-User: <아무개>' .../api/v1/admin/scope-policy   → HTTP 200

로그인 화면을 만들고 세션을 발급하고 서버가 세션을 먼저 보게까지 해 놓았는데, **헤더 경로를
함께 남겨 두었기 때문에** 로그인하지 않고도 관리자 API 가 열렸다. 정문을 잠그고 옆문을
그대로 둔 것이다.

`config.ORG_TRUST_HEADER` 를 False 로 내려 그 문을 닫았다. 이 파일은 그 상태를 **매번 다시
확인한다** — 기본값 한 줄은 되돌리기 쉽고, 되돌아가도 아무 화면도 오류를 내지 않는다.

## ⚠️ 왜 `@pytest.mark.real_auth` 인가

`tests/plugin_test_auth.py` 는 일반 테스트에 `current_principal` override 를 건다. 그 override
는 **테스트 편의를 위해 헤더를 읽는다.** 이 파일에 그것이 걸리면 「헤더가 안 먹는가」를 묻는
테스트가 **헤더가 먹는 세계에서** 돌게 되어, 무엇을 확인해도 의미가 없다.

## 세는 규칙

★ **401 만 인정한다.** 403 은 「당신이 누구인지는 알지만 권한이 없다」는 뜻이라 신원이
  헤더로 만들어졌다는 증거가 된다 — 차단으로 세면 안 된다. 422 도 마찬가지다
  (`tests/test_track_g_route_sealing.py` 의 세는 규칙과 같다).
"""
import pytest
from fastapi.testclient import TestClient

from tests import org_seed

#: 이 파일 전체가 인증 경로 자체를 본다 — principal override 를 받지 않는다.
pytestmark = pytest.mark.real_auth

#: 사용자의 실측이 이 경로에서 나왔다. 관리자 권한을 요구하므로 익명이면 401 이어야 한다.
ADMIN_URL = "/api/v1/admin/scope-policy"
ME_URL = "/api/v1/org/me"

#: ★★★ **시험 전용 합성 계정**(`tests/org_seed.py`).
#: ⚠️ 예전에는 운영 조직도의 실존 계정을 적었다. 그러면 두 가지가 깨진다 —
#:   ① 깨끗한 checkout 에는 그 계정이 없어 조직이 «부트스트랩»(전원 무제한)이 되고,
#:      경계 시험이 **아무것도 검증하지 못한 채** 통과하거나 뒤집힌다(2026-08-15 실측 255건).
#:   ② 실존 인물의 권한이 시험 기대값으로 못박혀, 조직도가 바뀌면 시험이 조용히 다른 것을 본다.
USER_A = org_seed.MEMBER_A
USER_B = org_seed.MEMBER_B


@pytest.fixture()
def client(monkeypatch, ecm_org_seed, seeded_org):
    """권한 강제를 켠 앱. 헤더 신뢰는 **운영 기본값(꺼짐)** 그대로 둔다.

    ⚠️ 앞뒤로 스코프 캐시를 비운다 — 강제를 켠 캐시가 남으면 뒤에 도는 다른 파일이 그것을
      물려받는다(`test_track_g_route_sealing.py` 가 같은 이유로 같은 일을 한다)."""
    import config
    from core.org_directory import org_directory
    #: ⚠️ 조직도가 비어 있으면 `is_bootstrap()` 이 **전원 무제한**을 돌려주므로
    #:   강제를 켜도 401 이 나오지 않는다 — `seeded_org` 가 그것을 심는다.
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


def _me(r) -> dict:
    """`/org/me` 응답에서 **알맹이를 꺼낸다.**

    ⚠️⚠️ 이 저장소의 응답은 `{"status": ..., "data": {...}}` 봉투다. 봉투째로 `.get("user_id")`
      를 하면 언제나 `None` 이고, 그러면 「신원이 안 생겼다」는 뜻으로 읽혀 **보안 테스트가
      거짓으로 초록이 된다.** 실제로 이 세션에서만 같은 실수를 네 번 했다 — 그래서 직접
      꺼내지 않고 반드시 이 함수를 쓴다."""
    d = r.json()
    body = d.get("data") if isinstance(d, dict) and "data" in d else d
    assert isinstance(body, dict), f"응답 모양이 예상과 다르다: {str(d)[:200]}"
    return body


def _session(user_id: str) -> str:
    """실제 세션을 발급한다. 인증 DB 는 플러그인이 tmp 로 격리해 두었다."""
    from core.auth import auth_store
    return str(auth_store.create_session(user_id)["token"])


# ── 운영 기본값: 자기 신고를 믿지 않는다 ──────────────────────────────────

@pytest.mark.parametrize("headers,params,label", [
    ({"X-Factory-User": USER_A}, {}, "새 헤더"),
    ({"X-User-Id": USER_A}, {}, "구 헤더(Phase 1 하위호환)"),
    ({}, {"as_user": USER_A}, "쿼리(SSE·다운로드 링크용이었다)"),
    ({"X-Factory-User": USER_A}, {"as_user": USER_A}, "헤더+쿼리 동시"),
])
def test_자기신고_신원은_거부된다(client, headers, params, label):
    """세션 없이 «나는 누구다» 라고 적기만 한 요청은 **401** 이어야 한다."""
    r = client.get(ADMIN_URL, headers=headers, params=params)
    assert r.status_code == 401, (
        f"{label} 만으로 관리자 API 가 열렸다(HTTP {r.status_code}). "
        f"403 이면 신원이 만들어졌다는 뜻이므로 그것도 실패다. 본문={r.text[:200]}")


def test_신원_조회조차_헤더로는_열리지_않는다(client):
    """`/org/me` 도 헤더만으로는 **401** 이다.

    ⚠️ 처음엔 이 경로가 «익명입니다» 라고 200 으로 답할 것이라 적었다가 실측에서 틀렸다 —
      강제 모드에서는 `current_principal` 이 먼저 401 을 낸다. 실제 동작이 더 엄격한 쪽이라
      그대로 두고 단언을 실측에 맞춘다.
    ★ 이 경로를 따로 보는 이유: `/org/me` 는 화면이 **가장 먼저** 부르는 곳이고, 여기서
      헤더로 신원이 서면 그 뒤 모든 화면이 그 사람으로 그려진다."""
    r = client.get(ME_URL, headers={"X-Factory-User": USER_A})
    assert r.status_code == 401, (
        f"헤더만으로 신원 조회가 열렸다(HTTP {r.status_code}). 본문={r.text[:200]}")


# ── 정상 경로: 세션은 살아 있어야 한다 ────────────────────────────────────

def test_세션_토큰으로는_정상_동작한다(client):
    """옆문을 닫으면서 정문까지 닫지 않았는지 본다.

    ⚠️ 200 을 요구하지 않는다 — 이 계정에 관리자 권한이 없으면 403 이 맞다. 확인할 것은
      **«누구인지 모른다»(401) 가 아니라는 것**이다."""
    tok = _session(USER_A)
    r = client.get(ADMIN_URL, headers={"X-Session-Token": tok})
    assert r.status_code != 401, f"세션으로도 신원이 서지 않는다. 본문={r.text[:200]}"
    me = _me(client.get(ME_URL, headers={"X-Session-Token": tok}))
    assert me.get("user_id") == USER_A and me.get("identified") is True


def test_세션이_있어도_헤더로_남이_될_수_없다(client):
    """A 로 로그인한 사람이 헤더에 B 를 적어도 **A 로 남는다.**"""
    tok = _session(USER_A)
    me = _me(client.get(ME_URL, headers={"X-Session-Token": tok, "X-Factory-User": USER_B},
                        params={"as_user": USER_B}))
    assert me.get("user_id") == USER_A, f"헤더로 남이 됐다: {me.get('user_id')!r}"


# ── 레거시 스위치: 켜는 것은 «의도적인 한 동작» 이어야 한다 ────────────────

def test_기본값은_꺼짐이다():
    """`config` 를 새로 읽어도 꺼져 있는가. 환경변수 없이는 켜지지 않는다.

    ⚠️ 이 단언이 이 파일의 **핵심**이다. 위 테스트들은 스위치가 꺼진 상태를 검증하지만,
      기본값이 True 로 되돌아가면 그 테스트들이 **먼저 깨지는 대신 이것이 깨져** 원인을
      한 줄로 말해 준다."""
    import config
    assert config.ORG_TRUST_HEADER is False, (
        "ORG_TRUST_HEADER 기본값이 켜져 있다. 이것이 켜지면 로그인 없이 헤더 한 줄로 "
        "관리자 API 를 읽을 수 있다(2026-08-09 실측 HTTP 200). 개발용으로 필요하면 "
        "환경변수 AFS_DEV_TRUST_HEADER=1 로 그 실행에서만 켜라.")


def test_레거시_스위치를_켜면_헤더가_다시_먹는다(client, monkeypatch):
    """하위호환 경로가 **살아는 있는지** 확인한다.

    ⚠️ 이것이 통과한다고 안전한 것이 아니다. 반대다 — 이 테스트가 통과한다는 것은
      «스위치를 켜면 실제로 뚫린다» 는 증거이고, 그래서 기본값이 꺼져 있어야 한다는 근거다.
    ★ `monkeypatch` 라 이 테스트 밖으로 새지 않는다. 다른 파일이 물려받지 않는다."""
    import config
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    me = _me(client.get(ME_URL, headers={"X-Factory-User": USER_A}))
    assert me.get("user_id") == USER_A, (
        "레거시 스위치를 켰는데도 헤더가 안 먹는다. 하위호환 경로가 의도치 않게 사라졌거나, "
        "`api/deps._extract_user_id` 가 이 스위치를 더는 보지 않는다.")
