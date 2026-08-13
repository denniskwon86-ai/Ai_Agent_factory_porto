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
    base = dict(actor="u@x", app_id="app_1", release_id="rel_1",
                capabilities=(READ, WRITE), tenant_id="tenant_default", entity_mode="REAL")
    base.update(kw)
    return store.issue(**base)


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
    with store._lock:                        # 시간을 기다리지 않고 만료시킨다
        store._tokens[rec["token"]]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    out = store.resolve(rec["token"])
    assert out is not None and out["expired"] is True


def test_만료된_토큰은_사용_횟수를_늘리지_않는다(store):
    rec = _issue(store)
    with store._lock:
        store._tokens[rec["token"]]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
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
    with store._lock:
        store._tokens[b["token"]]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert store.active() == []


def test_만료분_정리는_살아있는_것을_지우지_않는다(store):
    alive = _issue(store)
    dead = _issue(store)
    with store._lock:
        store._tokens[dead["token"]]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
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

    subject = ap.Subject(user_id="u@x", scope=_Scope(),
                         ctx={"tenant_id": "tenant_default", "entity_mode": "REAL"},
                         via="app_token", token=tok)
    res = ap.Resource(release_id="rel_1", dataset_id="ds_1", owner_dept_id="hq",
                      tenant_id="tenant_default", entity_mode="REAL",
                      declared_capabilities=(READ, WRITE))
    assert ap.decide(subject, res, READ).allowed
    # 다른 릴리스면 막힌다 — 이 토큰이 존재하는 이유다.
    other = ap.Resource(release_id="rel_OTHER", dataset_id="ds_9", owner_dept_id="hq",
                        tenant_id="tenant_default", entity_mode="REAL",
                        declared_capabilities=(READ,))
    d = ap.decide(subject, other, READ)
    assert not d.allowed and d.reason == ap.DENY_TOKEN_APP_MISMATCH
    # 토큰에 없는 행동도 막힌다.
    assert not ap.decide(subject, res, DELETE).allowed


# ── 감사 ─────────────────────────────────────────────────────────────────

def test_감사_이름이_화이트리스트에_등록돼_있다():
    """★★ 등록하지 않으면 `audit.record` 가 `UNKNOWN:` 으로 적는다. 그러면 「감사에 남는다」는
    주장이 **절반만 참**이 되고, 집계에서 통째로 빠진다."""
    from core.enterprise_context import audit
    for name in ("APP_TOKEN_ISSUED", "APP_TOKEN_EXPIRED", "APP_TOKEN_REVOKED"):
        assert name in audit.EVENTS, f"{name} 이 EVENTS 화이트리스트에 없다"


def test_발급_사용_만료_회수가_감사에_남는다(store, monkeypatch):
    """⚠️ 추적되지 않는 임시 권한은 뒷문이다. 그리고 **전문은 남기지 않는다.**"""
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw) or True)

    rec = _issue(store)
    with store._lock:
        store._tokens[rec["token"]]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    store.resolve(rec["token"])              # 만료 사용 시도
    store.revoke(rec["token"], actor="u@x")

    events = [k["event"] for k in seen]
    assert events == ["APP_TOKEN_ISSUED", "APP_TOKEN_EXPIRED", "APP_TOKEN_REVOKED"]
    assert all(k["resource_id"] == rec["fingerprint"] for k in seen), "지문이 아니라 다른 값이 남았다"
    blob = str(seen)
    assert rec["token"] not in blob, "감사에 토큰 전문이 남았다"
