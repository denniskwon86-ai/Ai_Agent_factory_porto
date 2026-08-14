"""★★★ [G1-B03] 생성 앱 데이터 접근용 단기 capability token.

## 이 파일이 지키는 것

1. **전문은 발급 응답에서 단 한 번만** 나간다 — 목록·판정·감사에는 지문만.
2. **만료와 «없는 토큰» 을 다르게 답한다** — 사용자가 할 일이 다르다(다시 열기 vs 접근 불가).
3. **문맥·릴리스·capability 없이는 발급되지 않는다** — 빈 값 토큰이 곧 «전부 허용» 이다.
4. **감사 이름이 화이트리스트에 실제로 등록돼 있다** — 등록하지 않으면 `UNKNOWN:` 으로
   기록되고, 그러면 「감사에 남는다」는 주장이 절반만 참이 된다.

⚠️ 이 토큰은 **앱에게 주지 않는다.** 부모(호스트 화면)가 들고 서버에 제시하는 «이 화면이 지금
  이 앱을 열고 있다» 는 증명이다(`design_app_data_plane_2026-08-08.md` §7).
"""
from datetime import datetime, timedelta, timezone

import pytest

import core.app_capability_token as act
from core.app_policy import DELETE, READ, WRITE


@pytest.fixture()
def store():
    return act.AppCapabilityTokenStore()


def _issue(store, **kw):
    base = dict(actor="u@x", session_id="sess_1", app_id="app_1", release_id="rel_1",
                capabilities=(READ, WRITE), tenant_id="tenant_default", entity_mode="REAL",
                scope_node_id="node_hq",
                #: ★ [2026-08-14] 발급 시점의 앱 선언을 봉인한다 — 판정이 이 값을 대조한다.
                manifest_fingerprint="fp_1", manifest_version="1.0")
    base.update(kw)
    return store.issue(**base)


def _expire(store, rec):
    """시간을 기다리지 않고 만료시킨다. 저장 키는 **해시**다."""
    with store._lock:
        store._tokens[act.token_hash(rec["token"])]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


# ── 발급 계약 ─────────────────────────────────────────────────────────────

def test_발급되면_전문과_지문을_함께_준다(store):
    rec = _issue(store)
    assert rec["token"].startswith(act.PREFIX)
    assert rec["fingerprint"] == rec["token"][:12]
    assert rec["capabilities"] == (READ, WRITE)
    assert rec["use_count"] == 0


@pytest.mark.parametrize("kw,needle", [
    ({"actor": ""}, "actor"),
    ({"release_id": ""}, "release_id"),
    ({"app_id": ""}, "app_id"),
    ({"capabilities": ()}, "capabilities"),
    ({"tenant_id": ""}, "tenant_id"),
    ({"entity_mode": ""}, "entity_mode"),
    #: ★ [rev.2 · 교차검토 지적 1·2] 세션·범위 공란도 막는다.
    ({"session_id": ""}, "session_id"),
    ({"scope_node_id": ""}, "scope_node_id"),
])
def test_빈_값으로는_발급되지_않는다(store, kw, needle):
    """⚠️ 빈 값 토큰은 «전부 허용» 으로 오해되기 쉽다. 만들 때 막는 편이 확실하다."""
    with pytest.raises(act.AppTokenError) as e:
        _issue(store, **kw)
    assert needle in str(e.value)


def test_알_수_없는_capability_는_거부한다(store):
    with pytest.raises(act.AppTokenError):
        _issue(store, capabilities=("exfiltrate",))


def test_만료_상한을_넘길_수_없다(store):
    """★ 긴 만료는 «이 화면이 지금 그 앱을 열고 있다» 는 증명이 아니라 상시 권한이다."""
    with pytest.raises(act.AppTokenError):
        _issue(store, ttl_minutes=act.MAX_TTL_MINUTES + 1)
    assert _issue(store, ttl_minutes=act.MAX_TTL_MINUTES)["ttl_minutes"] == act.MAX_TTL_MINUTES


@pytest.mark.parametrize("bad", [0, -5, "열다섯"])
def test_잘못된_만료값을_거부한다(store, bad):
    with pytest.raises(act.AppTokenError):
        _issue(store, ttl_minutes=bad)


def test_capability_중복은_한_번만_남는다(store):
    assert _issue(store, capabilities=(READ, READ, WRITE))["capabilities"] == (READ, WRITE)


# ── 사용·만료·회수 ────────────────────────────────────────────────────────

def test_판정용_결과에는_전문이_없다(store):
    """⚠️ 판정 경로에 전문을 들고 다니면 그것을 로그에 찍는 코드가 언젠가 생긴다."""
    tok = _issue(store)["token"]
    out = store.resolve(tok)
    assert "token" not in out
    assert out["fingerprint"] and out["release_id"] == "rel_1"


def test_쓸_때마다_사용_횟수가_는다(store):
    tok = _issue(store)["token"]
    store.resolve(tok)
    assert store.resolve(tok)["use_count"] == 2


def test_없는_토큰과_만료된_토큰을_다르게_답한다(store):
    """★★ 둘을 뭉개면 사용자는 «다시 열면 되는 상황» 과 «접근 불가» 를 구분하지 못한다.

    · 없는 토큰 → `None`
    · 만료 토큰 → `expired=True` 를 실은 dict (판정기가 사유를 나눌 수 있게)"""
    assert store.resolve("app_nope") is None
    rec = _issue(store, ttl_minutes=1)
    _expire(store, rec)
    out = store.resolve(rec["token"])
    assert out is not None and out["expired"] is True


def test_만료된_토큰은_사용_횟수를_늘리지_않는다(store):
    rec = _issue(store)
    _expire(store, rec)
    assert store.resolve(rec["token"])["use_count"] == 0


def test_회수된_토큰은_없는_것으로_답한다(store):
    tok = _issue(store)["token"]
    assert store.revoke(tok, actor="u@x") is True
    assert store.resolve(tok) is None
    assert store.revoke(tok) is False        # 멱등 — 두 번째는 False


def test_목록에는_전문이_실리지_않는다(store):
    """⚠️ 목록에 자격증명 전문이 실리면 그 목록을 읽을 수 있는 사람이 곧 권한자가 된다."""
    _issue(store)
    rows = store.active()
    assert rows and all("token" not in r for r in rows)
    assert rows[0]["fingerprint"]


def test_회수와_만료는_목록에서_빠진다(store):
    a = _issue(store)
    b = _issue(store)
    store.revoke(a["token"])
    _expire(store, b)
    assert store.active() == []


def test_만료분_정리는_살아있는_것을_지우지_않는다(store):
    alive = _issue(store)
    dead = _issue(store)
    _expire(store, dead)
    assert store.purge_expired() == 1
    assert store.resolve(alive["token"]) is not None


# ── 판정기와의 이음매 ─────────────────────────────────────────────────────

def test_판정기가_이_토큰을_그대로_먹는다(store):
    """★ 두 모듈의 «형태» 가 어긋나면 배선한 뒤에야 알게 된다. 여기서 잠근다."""
    import core.app_policy as ap
    tok = store.resolve(_issue(store)["token"])

    class _Scope:
        readable_dept_ids = frozenset({"hq"})
        writable_dept_ids = frozenset({"hq"})
        unrestricted = False

    subject = ap.Subject(user_id="u@x", scope=_Scope(), session_id="sess_1",
                         ctx={"tenant_id": "tenant_default", "entity_mode": "REAL",
                              "scope_node_id": ""},
                         via="app_token", token=tok)
    res = ap.ResourceScope(tenant_id="tenant_default", entity_mode="REAL",
                           scope_node_id="node_hq", owner_dept_id="hq")
    facts = ap.AppResourceFacts(app_id="app_1", release_id="rel_1",
                                manifest_fingerprint="fp_1", manifest_version="1.0",
                                declared_capabilities=(READ, WRITE))
    assert ap.decide(subject, res, READ, app=facts).allowed
    # 다른 릴리스면 막힌다 — 이 증명이 존재하는 이유다.
    other = ap.AppResourceFacts(app_id="app_1", release_id="rel_OTHER",
                                declared_capabilities=(READ,))
    d = ap.decide(subject, res, READ, app=other)
    assert not d.allowed and d.reason == ap.DENY_TOKEN_APP_MISMATCH
    # 토큰에 없는 행동도 막힌다.
    assert not ap.decide(subject, res, DELETE, app=facts).allowed


# ── 감사 ─────────────────────────────────────────────────────────────────

def test_감사_이름이_화이트리스트에_등록돼_있다():
    """★★ 등록하지 않으면 `audit.record` 가 `UNKNOWN:` 으로 적는다. 그러면 「감사에 남는다」는
    주장이 **절반만 참**이 되고, 집계에서 통째로 빠진다."""
    from core.enterprise_context import audit
    for name in ("APP_TOKEN_ISSUED", "APP_TOKEN_USED", "APP_TOKEN_EXPIRED",
                 "APP_TOKEN_REVOKED"):
        assert name in audit.EVENTS, f"{name} 이 EVENTS 화이트리스트에 없다"


def test_발급_사용_만료_회수가_감사에_남는다(store, monkeypatch):
    """⚠️ 추적되지 않는 임시 권한은 뒷문이다. 그리고 **전문은 남기지 않는다.**"""
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw) or True)

    rec = _issue(store)
    store.resolve(rec["token"])              # ★ 성공 사용
    _expire(store, rec)
    store.resolve(rec["token"])              # 만료 사용 시도
    store.revoke(rec["token"], actor="u@x")

    events = [k["event"] for k in seen]
    assert events == ["APP_TOKEN_ISSUED", "APP_TOKEN_USED", "APP_TOKEN_EXPIRED",
                      "APP_TOKEN_REVOKED"], f"감사 순서가 다르다: {events}"
    assert all(k["resource_id"] == rec["fingerprint"] for k in seen), "지문이 아니라 다른 값이 남았다"
    blob = str(seen)
    assert rec["token"] not in blob, "감사에 토큰 전문이 남았다"


# ── rev.2 — 교차검토 지적 2·5 의 나머지 절반 ─────────────────────────────

def test_저장소에는_전문이_없다(store):
    """★★★ [지적 5] 초판은 **원문을 메모리 키와 레코드에 그대로** 들고 있었다.
    프로세스 덤프·디버거·예외 출력 어디에서든 새면 곧 권한이다."""
    rec = _issue(store)
    with store._lock:
        keys = list(store._tokens.keys())
        rows = list(store._tokens.values())
    assert rec["token"] not in keys, "저장 키가 토큰 전문이다"
    assert act.token_hash(rec["token"]) in keys, "해시로 저장되지 않았다"
    assert all("token" not in r for r in rows), "레코드에 전문이 남아 있다"
    #: 지문은 남는다 — 추적에는 필요하고, 그것만으로는 인증할 수 없다.
    assert rows[0]["fingerprint"] == rec["token"][:12]


def test_세션이_끝나면_그_세션의_증명도_끝난다(store):
    """★★★ [지적 2] 로그아웃했는데 앱 증명이 살아 있으면 **회수할 수 없는 권한**이 남는다.
    `auth.destroy_all_for` 와 짝을 이루는 쪽이다."""
    mine_a = _issue(store, session_id="sess_A")
    mine_b = _issue(store, session_id="sess_A")
    other = _issue(store, session_id="sess_B")

    assert store.revoke_session("sess_A", actor="u@x") == 2
    assert store.resolve(mine_a["token"]) is None
    assert store.resolve(mine_b["token"]) is None
    #: ⚠️ 대조군 — 다른 세션의 증명까지 끊으면 그것은 회수가 아니라 장애다.
    assert store.resolve(other["token"]) is not None


def test_세션_회수는_멱등이고_빈_값에_반응하지_않는다(store):
    _issue(store, session_id="sess_A")
    assert store.revoke_session("sess_A") == 1
    assert store.revoke_session("sess_A") == 0
    assert store.revoke_session("") == 0


def test_세션_회수도_감사에_남는다(store, monkeypatch):
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw) or True)
    _issue(store, session_id="sess_A")
    store.revoke_session("sess_A", actor="u@x")
    assert [k["event"] for k in seen] == ["APP_TOKEN_ISSUED", "APP_TOKEN_REVOKED"]


def test_발급이_매니페스트를_봉인한다(store):
    """★★★ 「이 증명은 **그때 그 앱**에 대한 것」이 되려면 지문·판이 레코드에 남아야 한다."""
    rec = _issue(store)
    assert rec["manifest_fingerprint"] == "fp_1" and rec["manifest_version"] == "1.0"
    assert store.resolve(rec["token"])["manifest_fingerprint"] == "fp_1"


def test_성공_사용_기록은_해석이_아니라_판정_뒤에_남긴다(store, monkeypatch):
    """★★★ [교차검토 지적 3] 해석은 「토큰이 존재한다」까지만 증명한다. 그 뒤 PDP 가 거부할
    수 있는데, 해석 단계에서 «사용됨» 을 남기면 보안 감사에서 **「데이터를 만졌다」와
    「만지려다 막혔다」가 같은 줄**이 된다."""
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw.get("event")) or True)
    rec = _issue(store)
    store.resolve(rec["token"], quiet=True)
    assert "APP_TOKEN_USED" not in seen, "해석만 했는데 «사용됨» 이 남았다"
    store.record_use(store.resolve(rec["token"], quiet=True))
    assert "APP_TOKEN_USED" in seen, "판정 뒤에도 사용 기록이 남지 않는다"
