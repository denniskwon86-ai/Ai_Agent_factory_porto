"""★★★ [P0-1B] SSE 1회용 접속표 — **`?as_user=` 자기 신고를 대체한다.**

## 이 파일이 지키는 가장 무거운 계약

⚠️ **티켓 발급이 `current_principal` 을 쓰면 안 된다.** `ORG_TRUST_HEADER` 가 켜져 있는 동안
  그 함수는 `X-Factory-User` 헤더와 `?as_user=` 쿼리를 그대로 믿는다. 발급 라우트가 그것을
  쓰면 공격자가 `as_user=관리자` 로 **티켓까지 발급받아** 관리자로 구독한다 — 우회로를 막으려
  만든 장치가 새 우회로가 된다.

## 두 번째: 소비는 정확히 한 번

「읽고 → 확인하고 → 쓰기」로 나누면 두 요청이 그 사이를 통과해 **같은 표로 둘 다 연결**된다.
다중 워커에서는 더 쉽게 일어난다. `UPDATE ... WHERE consumed_at=''` 한 문장과 rowcount 로
판정해야 한다.
"""
import time

import pytest
from fastapi.testclient import TestClient

import config
from core.auth import SSE_TICKET_SECONDS, AuthStore

#: ★★ [P0-1C] 이 파일은 **인증 경로 자체**를 검증한다. principal override 를 받으면 실제
#  인증 연결 결함을 숨기게 되므로 전 테스트에서 override 를 끈다(승인된 3분류의 둘째 칸).
pytestmark = pytest.mark.real_auth


@pytest.fixture
def store(tmp_path):
    return AuthStore(db_path=str(tmp_path / "auth.db"))


# ── 저장소 계약 ──────────────────────────────────────────────────────────────

def test_티켓은_한_번만_소비된다(store):
    """★★ 재사용이 되면 표를 훔친 사람이 계속 구독할 수 있다."""
    t = store.issue_sse_ticket("kim", "sess-1")
    assert store.consume_sse_ticket(t["ticket"]) == "kim"
    assert store.consume_sse_ticket(t["ticket"]) == ""      # 두 번째는 실패


def test_동시_소비는_정확히_하나만_성공한다(tmp_path):
    """★★★ 원자성 — **다중 워커**를 재현한다.

    ⚠️⚠️ 처음에는 스레드 두 개로 같은 `AuthStore` 를 두드렸다. 그 테스트는 원자성을 제거해도
      **통과했다**(변이 검사로 잡았다). `self._lock` 이 같은 프로세스 안의 두 스레드를
      직렬화해 **DB 수준의 결함을 가려 버리기** 때문이다.

    실제 운영은 워커가 여럿이고 그때 파이썬 락은 아무 것도 보호하지 못한다. 그래서 **별도
    인스턴스 두 개**(각자 자기 락)가 같은 DB 파일을 두드리게 한다 — 다중 워커와 같은 상황이다.

    이 구조에서는 「읽고 → 확인하고 → 쓰기」가 반드시 둘 다 통과한다."""
    import threading

    db = str(tmp_path / "shared.db")
    issuer = AuthStore(db_path=db)
    t = issuer.issue_sse_ticket("kim", "sess-1")["ticket"]

    #: ★ 워커마다 다른 인스턴스 = 다른 락. 파이썬 락이 보호해 주지 않는다.
    workers = [AuthStore(db_path=db), AuthStore(db_path=db)]
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(len(workers))

    def worker(st):
        barrier.wait()                       # 같은 순간에 출발시킨다
        r = st.consume_sse_ticket(t)
        with lock:
            results.append(r)

    ths = [threading.Thread(target=worker, args=(w,)) for w in workers]
    for th in ths:
        th.start()
    for th in ths:
        th.join()

    assert sorted(results) == ["", "kim"], (
        f"동시 소비 결과가 {results} — 정확히 하나만 성공해야 한다. "
        f"둘 다 성공했다면 소비가 원자적이지 않다(읽고→확인→쓰기 구조).")


def test_만료된_티켓은_거부된다(store, monkeypatch):
    """30초 뒤에는 죽는다. 그렇지 않으면 URL 에 남은 표가 계속 유효하다."""
    import core.auth as auth_mod

    t = store.issue_sse_ticket("kim", "sess-1")["ticket"]
    real_now = auth_mod._now

    def later():
        from datetime import timedelta
        return real_now() + timedelta(seconds=SSE_TICKET_SECONDS + 5)

    monkeypatch.setattr(auth_mod, "_now", later)
    assert store.consume_sse_ticket(t) == ""


def test_위조_티켓은_거부된다(store):
    store.issue_sse_ticket("kim", "sess-1")
    assert store.consume_sse_ticket("아무렇게나-만든-값") == ""
    assert store.consume_sse_ticket("") == ""


def test_저장소에_원문이_남지_않는다(store):
    """★ 티켓은 URL 로 오간다 — 접근 로그에 남을 수 있다. 저장소까지 원문을 두지 않는다."""
    raw = store.issue_sse_ticket("kim", "sess-1")["ticket"]
    with store._connect() as conn:
        rows = conn.execute("SELECT token_hash FROM auth_sse_ticket").fetchall()
    assert rows, "티켓이 저장되지 않았습니다."
    assert all(r["token_hash"] != raw for r in rows), "원문이 그대로 저장돼 있습니다."


def test_사용자_없이는_발급하지_않는다(store):
    """호출자가 user_id 를 정하게 두면 그것이 곧 사칭이다 — 라우트가 세션에서 정한 값만 넘긴다."""
    with pytest.raises(ValueError):
        store.issue_sse_ticket("", "sess-1")


# ── 라우트 계약 ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    import core.auth as auth_mod
    from main import app

    fresh = AuthStore(db_path=str(tmp_path / "auth_api.db"))
    monkeypatch.setattr(auth_mod, "auth_store", fresh)
    import api.routes.auth_control as ac
    import api.routes.realtime as rt
    monkeypatch.setattr(ac, "auth_store", fresh)
    monkeypatch.setattr(rt, "auth_store", fresh)
    return TestClient(app), fresh


def test_인증_없이는_티켓을_받지_못한다(client):
    c, _ = client
    assert c.post("/api/v1/auth/sse-ticket").status_code == 401


def test_헤더_사칭으로는_티켓을_받지_못한다(client, monkeypatch):
    """★★★ 이 테스트가 이 파일의 존재 이유다.

    `ORG_TRUST_HEADER` 가 켜져 있어도 티켓 발급은 **세션 토큰만** 본다. 이것이 뚫리면
    `as_user` 를 막은 의미가 사라진다 — 티켓이 새로운 우회로가 되기 때문이다.

    ⚠️ [P0-1C] 종전에는 `assert config.ORG_TRUST_HEADER is True` 로 **전제를 확인만** 했다.
      그 기본값이 False 로 내려가자 이 테스트는 «전제가 깨졌다» 며 실패했다 — 그런데 정작
      확인하려던 계약(티켓은 세션만 본다)은 그대로 유효하다. 전제를 기다리지 말고 **이
      테스트가 최악의 조건을 스스로 만든다.** `monkeypatch` 라 이 테스트 밖으로 새지 않는다.
    ★ 이렇게 두면 나중에 누가 스위치를 되켜도 이 계약은 계속 검증된다."""
    c, _ = client
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)

    r1 = c.post("/api/v1/auth/sse-ticket", headers={"X-Factory-User": "hikwon@lsmnm.com"})
    assert r1.status_code == 401, "헤더 사칭으로 티켓이 발급됐습니다."

    r2 = c.post("/api/v1/auth/sse-ticket?as_user=hikwon@lsmnm.com")
    assert r2.status_code == 401, "as_user 쿼리로 티켓이 발급됐습니다."


def test_SSE_는_티켓_없이_열리지_않는다(client):
    """⚠️ 실패해도 `as_user` 로 폴백하지 않는다 — 폴백은 곧 우회로다."""
    c, _ = client
    assert c.get("/ws/timeline").status_code == 401
    assert c.get("/ws/timeline?as_user=hikwon@lsmnm.com").status_code == 401
    assert c.get("/ws/timeline?ticket=위조").status_code == 401


def test_오류_응답에_티켓이_되실리지_않는다(client):
    """표가 오류 메시지로 되돌아오면 로그·화면에 한 번 더 남는다."""
    c, _ = client
    secret = "ticket-should-not-echo-12345"
    r = c.get(f"/ws/timeline?ticket={secret}")
    assert r.status_code == 401
    assert secret not in r.text


# ── [P0-1B 보정] 재감사에서 지적된 세 건 ────────────────────────────────────

def test_요청자가_보낸_테넌트를_티켓에_싣지_않는다(client):
    """★★ 「요청자가 scope 를 지정하지 않는다」는 계약.

    ⚠️ 종전에는 `X-Tenant-Id` 헤더를 그대로 티켓에 저장했다. 그러면 공격자가 헤더 하나로
      **다른 테넌트 범위의 표**를 받는다 — 계약이 그 자리에서 깨진다.
    ⚠️ tenant 는 아직 서버 권한 모델과 연결되지 않았다(G1-C). 모르는 것을 헤더로 채우는 것보다
      **비워 두는 것**이 옳다 — 채워 두면 다음 사람이 「테넌트 경계가 있다」고 믿는다."""
    c, store = client
    lg = c.post("/api/v1/auth/login",
                json={"user_id": "hikwon@lsmnm.com", "password": "pass:"})
    assert lg.status_code == 200
    tok = lg.json()["data"]["token"]

    r = c.post("/api/v1/auth/sse-ticket",
               headers={"X-Session-Token": tok, "X-Tenant-Id": "other-tenant"})
    assert r.status_code == 200

    with store._connect() as conn:
        rows = conn.execute("SELECT tenant_id FROM auth_sse_ticket").fetchall()
    assert rows, "티켓이 저장되지 않았습니다."
    assert all(r0["tenant_id"] == "" for r0 in rows), (
        "요청 헤더의 테넌트가 티켓에 저장됐습니다 — 요청자가 scope 를 지정한 셈입니다.")


def test_접근_로그에서_티켓이_가려진다():
    """★★ 티켓은 URL 로 오간다 — `uvicorn.access` 의 request line 에 그대로 남는다.

    ⚠️ 응답의 `Referrer-Policy` 는 **브라우저가 다음 요청에 참조자를 싣지 않게** 할 뿐,
      서버가 자기 로그에 적는 것은 막지 못한다. 둘을 혼동하면 가린 줄 알고 넘어간다."""
    import io as _io
    import logging

    from core.log_redaction import install, redact

    assert redact("GET /ws/timeline?ticket=SECRET HTTP/1.1") == "GET /ws/timeline?ticket=*** HTTP/1.1"
    #: 키는 남긴다 — 무엇이 가려졌는지 보여야 조사할 수 있다.
    assert "ticket=" in redact("?ticket=SECRET")

    install()
    buf = _io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(message)s"))
    lg = logging.getLogger("uvicorn.access")
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    install()                     # 핸들러에도 걸린다(여러 번 호출해도 안전)
    try:
        # uvicorn.access 는 %s 포맷 + **인자 튜플**로 넘긴다 — msg 만 손보면 URL 이 샌다.
        lg.info('%s - "%s %s HTTP/1.1" %d', "127.0.0.1", "GET",
                "/ws/timeline?ticket=LEAKME", 200)
        out = buf.getvalue()
    finally:
        lg.removeHandler(h)
    assert "LEAKME" not in out, f"접근 로그에 티켓 원문이 남았습니다: {out}"
    assert "ticket=***" in out


def test_세션_토큰_계열도_함께_가린다():
    """티켓만 가리면 다음에 추가되는 비밀값이 또 샌다."""
    from core.log_redaction import redact

    for k in ("token", "session", "password", "api_key"):
        assert f"{k}=***" in redact(f"/x?{k}=VALUE"), f"{k} 가 가려지지 않았습니다."
