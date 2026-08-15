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

from tests import org_seed

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
    #: ★ [G1-C1.1] 소비 결과가 **문맥 사전**이 됐다. 신원만으로는 이벤트를 가를 수 없어
    #  테넌트·조직범위·실행모드를 발급 시점에 표에 묶어 함께 돌려준다.
    assert store.consume_sse_ticket(t["ticket"])["user_id"] == "kim"
    assert store.consume_sse_ticket(t["ticket"]) == {}      # 두 번째는 실패


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

    #: [G1-C1.1] 결과가 문맥 사전이 됐으므로 «성공한 소비» 를 사용자 id 로 센다.
    succeeded = [r.get("user_id") for r in results if r]
    assert succeeded == ["kim"] and len(results) == 2, (
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
    assert store.consume_sse_ticket(t) == {}


def test_위조_티켓은_거부된다(store):
    store.issue_sse_ticket("kim", "sess-1")
    assert store.consume_sse_ticket("아무렇게나-만든-값") == {}
    assert store.consume_sse_ticket("") == {}


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
def client(tmp_path, monkeypatch, seeded_org):
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

    r1 = c.post("/api/v1/auth/sse-ticket", headers={"X-Factory-User": org_seed.ADMIN})
    assert r1.status_code == 401, "헤더 사칭으로 티켓이 발급됐습니다."

    r2 = c.post("/api/v1/auth/sse-ticket?as_user=시험 계정")
    assert r2.status_code == 401, "as_user 쿼리로 티켓이 발급됐습니다."


def test_SSE_는_티켓_없이_열리지_않는다(client):
    """⚠️ 실패해도 `as_user` 로 폴백하지 않는다 — 폴백은 곧 우회로다."""
    c, _ = client
    assert c.get("/ws/timeline").status_code == 401
    assert c.get("/ws/timeline?as_user=시험 계정").status_code == 401
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
    ★★ [G1-C1.1] 이제 서버가 **자기 조직 정보에서** 테넌트·조직범위·실행모드를 해석해 티켓에
      묶는다. 종전 계약은 「연결이 없으니 비워 둔다」였다 — 그 상태에서는 티켓에 문맥이 없어
      브로드캐스터가 테넌트 경계를 대조할 수 없었다.
    ⚠️ 바뀐 것은 **누가 채우는가** 뿐이다. 요청 헤더는 여전히 쳐다보지 않는다 — 그것이 이
      테스트가 지키는 계약이다."""
    c, store = client
    lg = c.post("/api/v1/auth/login",
                json={"user_id": org_seed.ADMIN, "password": "pass:"})
    assert lg.status_code == 200
    tok = lg.json()["data"]["token"]

    r = c.post("/api/v1/auth/sse-ticket",
               headers={"X-Session-Token": tok, "X-Tenant-Id": "other-tenant"})
    assert r.status_code == 200

    with store._connect() as conn:
        rows = conn.execute(
            "SELECT tenant_id, entity_mode FROM auth_sse_ticket").fetchall()
    assert rows, "티켓이 저장되지 않았습니다."
    assert all(r0["tenant_id"] != "other-tenant" for r0 in rows), (
        "요청 헤더의 테넌트가 티켓에 저장됐습니다 — 요청자가 scope 를 지정한 셈입니다.")
    #: ★ 「헤더를 안 쓴다」만 확인하면 **서버가 아무것도 안 채워도 통과**한다. 문맥이 실제로
    #  실렸는지 함께 본다 — 비어 있으면 브로드캐스터가 테넌트 경계를 대조할 수 없다.
    import config
    assert all(r0["tenant_id"] == config.ECM_DEFAULT_TENANT_ID for r0 in rows), (
        "서버가 해석한 테넌트가 티켓에 실리지 않았습니다.")
    assert all((r0["entity_mode"] or "") for r0 in rows), (
        "실행 모드(REAL/VIRTUAL)가 비어 있습니다 — 샌드박스 자료와 실제 자료를 가를 수 없습니다.")


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


# ── 스키마 이행: **옛 DB 로도 기동한다** ──────────────────────────────────────
#
# ★★★ [2026-08-13 실서버 실측으로 발견] 이 파일의 다른 테스트는 전부 **새 tmp DB** 를 쓴다.
#   그래서 「기존 DB 를 열었을 때」를 **구조적으로 볼 수 없었다** — 그 사이 로그인은 운영에서
#   500 으로 죽어 있었다(2026-08-12 `3641a02e9` 이후). 단위 초록이 실측을 대신하지 못한
#   전형적인 사례이고, 그것을 여기서 잠근다.

#: G1-C1.3 **이전** 스키마 — `auth_session.token_hash` 가 없다.
_OLD_DDL = """
CREATE TABLE IF NOT EXISTS auth_credential (
    user_id     TEXT PRIMARY KEY,
    salt        TEXT NOT NULL,
    hash        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_session (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_user ON auth_session(user_id);
CREATE TABLE IF NOT EXISTS auth_sse_ticket (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    tenant_id   TEXT NOT NULL DEFAULT '',
    audience    TEXT NOT NULL DEFAULT 'sse',
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    consumed_at TEXT NOT NULL DEFAULT ''
);
"""


def test_옛_스키마_DB_에서도_로그인이_된다(tmp_path):
    """★★★ 실서버 회귀 — `no such column: token_hash` 로 `_init()` 이 통째로 죽었다.

    원인은 **순서**였다. 컬럼 보강(`ALTER`) 코드는 있었는데 `executescript` **뒤**에 있었고,
    그 스크립트 안의 `CREATE INDEX ... (token_hash)` 가 먼저 죽어 보강에 도달하지 못했다.
    즉 «고치는 코드가 있는데 실행되지 않는» 상태였고, 새 DB 로만 도는 테스트는 이것을
    영원히 못 본다.

    ⚠️ 이 테스트가 지키는 것은 「로그인이 된다」가 아니라 **「기존 DB 를 열 수 있다」** 다.
      스키마에 컬럼을 더할 때마다 이 경로가 다시 깨질 수 있다."""
    import sqlite3

    from core.auth import AuthStore

    p = tmp_path / "auth.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(_OLD_DDL)
    conn.commit()
    conn.close()

    store = AuthStore(db_path=str(p))
    store.set_password(org_seed.ADMIN, "pw12345")     # `_init()` 이 여기서 돈다
    assert store.verify(org_seed.ADMIN, "pw12345"), "옛 DB 에서 로그인이 되지 않는다"

    #: 보강이 실제로 일어났는지 — 인덱스가 서야 SSE 세션 확인이 동작한다.
    conn = sqlite3.connect(str(p))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auth_session)")}
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='auth_session'")}
    conn.close()
    assert "token_hash" in cols, "컬럼 보강이 일어나지 않았다"
    assert "idx_session_hash" in idx, "해시 인덱스가 서지 않았다 — 세션 확인이 전수 훑기가 된다"


def test_새_DB_도_같은_경로로_정상_생성된다(tmp_path):
    """⚠️ 대조군. 보강을 앞으로 옮겼으므로 **새 DB 에서는 ALTER 가 전부 실패한다** —
    그 실패가 조용히 삼켜지고 뒤의 `executescript` 가 옳은 스키마를 만드는지 확인한다.
    이 짝이 없으면 「옛 DB 만 고치고 새 DB 를 깨뜨린」 상태도 초록이 된다."""
    import sqlite3

    from core.auth import AuthStore

    p = tmp_path / "fresh.db"
    store = AuthStore(db_path=str(p))
    store.set_password(org_seed.ADMIN, "pw12345")
    assert store.verify(org_seed.ADMIN, "pw12345")
    conn = sqlite3.connect(str(p))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auth_session)")}
    tcols = {r[1] for r in conn.execute("PRAGMA table_info(auth_sse_ticket)")}
    conn.close()
    assert "token_hash" in cols
    assert {"scope_node_id", "entity_mode", "context_version"} <= tcols
