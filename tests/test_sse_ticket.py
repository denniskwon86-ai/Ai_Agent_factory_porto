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


def test_헤더_사칭으로는_티켓을_받지_못한다(client):
    """★★★ 이 테스트가 이 파일의 존재 이유다.

    `ORG_TRUST_HEADER` 가 켜져 있어도 티켓 발급은 **세션 토큰만** 본다. 이것이 뚫리면
    `as_user` 를 막은 의미가 사라진다 — 티켓이 새로운 우회로가 되기 때문이다."""
    c, _ = client
    assert config.ORG_TRUST_HEADER is True, "이 테스트는 헤더 신뢰가 켜진 상태를 전제한다"

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
