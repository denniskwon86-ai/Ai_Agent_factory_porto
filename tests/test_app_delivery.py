"""★★★ [CL-1] 개인 앱 전달·수락·내 앱 — **수락은 권한을 넓히지 않는다.**

작업서 §10 필수 케이스 1~5 를 여기서 고정한다.

## 가장 무거운 계약

⚠️ **수락만으로 수신자의 데이터 접근 범위가 늘어나면 앱 전달이 권한 우회 경로가 된다.**
  앱을 받는 것과 데이터를 볼 수 있는 것은 별개다 — 앱은 호스트 권한으로 돌고, 수신자가 원래
  못 보던 자료는 앱에서도 보이지 않는다. 이 규칙이 무너지면 이 저장소가 권한 모델에 들인
  모든 통제가 "앱 하나 보내기"로 우회된다.

## 두 번째로 무거운 것: 404 은폐

남의 요청에 403 을 주면 "있지만 못 본다"가 되어 **존재가 새어나간다.** 그래서 `NotFoundOrHidden`
하나로 묶어 라우트가 구분하지 못하게 했다 — 구분할 수 있으면 언젠가 구분해서 답한다.
"""
import json

import pytest

from core.app_delivery import (ACCEPTED, EXPIRED, PENDING, REJECTED, REVOKED, AppDelivery,
                               AppDeliveryError, NotFoundOrHidden)
from core.collaboration_store import CollaborationStore

RELEASE = {
    "release_id": "REL_OK", "version": "1.0",
    "manifest": {"valid": True, "fingerprint": "f" * 32,
                 "manifest": {"auth_mode": "PLATFORM_INHERITED",
                              "capabilities": ["arrival.update"]}},
    "platform_auth_scan": {"ok": True, "summary": {"blocking": 0}},
}


class _FakeLedger:
    """원장 대역 — 실물과 같은 시그니처. 기록된 이벤트를 검사할 수 있게 모아 둔다."""
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    def append(self, event_type, subject_type, subject_id, **kw):
        if self.fail:
            raise RuntimeError("원장 디스크 오류")
        self.events.append({"event": event_type, "subject_type": subject_type,
                            "subject_id": subject_id, **kw})
        return {"event_id": f"dle_{len(self.events)}"}


@pytest.fixture
def svc(tmp_path):
    store = CollaborationStore(db_path=str(tmp_path / "collab.db"))
    return AppDelivery(store=store, ledger=_FakeLedger())


def _lookup(rel=None):
    table = {RELEASE["release_id"]: (rel or RELEASE)}
    return lambda rid: table.get(rid)


def _created(svc, **kw):
    args = dict(release_id="REL_OK", sender_user_id="kim", recipient_user_id="lee",
                purpose="물류 입력 협업", release_lookup=_lookup())
    args.update(kw)
    return svc.create(**args)


# ── 생성 ──────────────────────────────────────────────────────────────────
def test_delivery_requires_purpose(svc):
    """★★ 목적 없는 앱을 받은 사람은 **수락 여부를 판단할 근거가 없다.**"""
    with pytest.raises(AppDeliveryError, match="목적"):
        _created(svc, purpose="")


def test_cannot_deliver_to_self(svc):
    """★ 자기에게 보내는 전달은 상태만 늘리고 아무것도 바꾸지 않는다."""
    with pytest.raises(AppDeliveryError, match="자기 자신"):
        _created(svc, recipient_user_id="kim")


def test_missing_release_is_404_not_400(svc):
    """★★★ 없는 릴리스는 `NotFoundOrHidden` — 다른 회사의 릴리스 id 를 넣어 존재를 탐지하는
    경로를 막는다(작업서 §10-3)."""
    with pytest.raises(NotFoundOrHidden):
        _created(svc, release_id="REL_OTHER_COMPANY")


def test_expiry_is_bounded(svc):
    """★★ 만료 없는 대기 요청은 영구히 남아 목록을 채우고, 결국 아무도 읽지 않는다
    (이 저장소가 '한시 예외'에서 겪은 유형)."""
    with pytest.raises(AppDeliveryError, match="만료"):
        _created(svc, expires_in_days=0)
    with pytest.raises(AppDeliveryError, match="만료"):
        _created(svc, expires_in_days=999)


def test_app_with_local_auth_cannot_be_delivered(svc):
    """★★★ [작업서 §10-5] **자체 인증을 가진 앱은 전달되지 않는다.**

    게시 때 막지 않은 이유는 이미 만든 산출물을 지우면 다음 사람이 검사를 끄기 때문이다.
    전달은 사람에게 넘기는 행위이므로 여기가 차단 지점이다."""
    bad = dict(RELEASE)
    bad["platform_auth_scan"] = {"ok": False, "summary": {"blocking": 3}}
    with pytest.raises(AppDeliveryError, match="자체 인증"):
        _created(svc, release_lookup=_lookup(bad))


def test_invalid_manifest_cannot_be_delivered(svc):
    """★★ Manifest 가 유효하지 않으면 **수신자가 무엇을 수락하는지 알 수 없다.**"""
    bad = dict(RELEASE)
    bad["manifest"] = {"valid": False, "errors": ["auth_mode 는 ..."], "manifest": {}}
    with pytest.raises(AppDeliveryError, match="Manifest"):
        _created(svc, release_lookup=_lookup(bad))


def test_manifest_fingerprint_is_snapshotted(svc):
    """★★★ 전달 시점의 지문을 복사해 둔다 — 나중에 릴리스가 바뀌면 **사용자가 수락한 것과
    다른 앱**이 실행되는 것을 잡는 근거다."""
    d = _created(svc)
    assert d["manifest_fingerprint"] == "f" * 32
    assert d["manifest_snapshot"]["capabilities"] == ["arrival.update"]


# ── idempotency (§10-1) ───────────────────────────────────────────────────
def test_same_idempotency_key_creates_one_delivery(svc):
    """★★★ 중복 클릭·재시도로 전달이 두 개 생기면 수신자는 같은 앱을 두 번 수락하게 되고,
    어느 것이 유효한지 아무도 모른다."""
    a = _created(svc, idempotency_key="k1")
    b = _created(svc, idempotency_key="k1")
    assert a["delivery_id"] == b["delivery_id"]
    assert b["replayed"] is True
    assert len(svc.outbox("kim")) == 1


def test_empty_idempotency_keys_do_not_collide(svc):
    """★★ 키 없는 호출까지 하나로 묶으면 **서로 다른 전달이 충돌한다.**"""
    a = _created(svc, purpose="첫 번째")
    b = _created(svc, purpose="두 번째")
    assert a["delivery_id"] != b["delivery_id"] and len(svc.outbox("kim")) == 2


# ── 수락 (§10-1, §10-4) ───────────────────────────────────────────────────
def test_accept_creates_exactly_one_pocket_even_on_retry(svc):
    """★★★ [§10-1] 재수락에도 주머니는 하나다."""
    d = _created(svc)
    first = svc.accept(d["delivery_id"], "lee")
    again = svc.accept(d["delivery_id"], "lee")
    assert first["status"] == ACCEPTED and again["status"] == ACCEPTED
    assert again["replayed"] is True
    assert len(svc.my_apps("lee")) == 1


def test_accept_does_not_widen_data_scope(svc):
    """★★★ [§10-4] **이 파일에서 가장 무거운 테스트.**

    수락 응답이 "권한은 넓어지지 않았다"를 명시적으로 말해야 한다. 화면이 이 문구를 보여주지
    않으면 사용자는 앱을 받으면 자료도 보인다고 믿는다. 그리고 실제로 넓어진다면 앱 전달이
    권한 우회 경로가 된다 — 이 저장소의 통제 전체가 무력화된다."""
    d = _created(svc)
    out = svc.accept(d["delivery_id"], "lee")
    assert out["scope_unchanged"] is True
    assert "넓어지지 않았습니다" in out["scope_note"]
    # 주머니에는 앱만 들어간다 — 권한·부서 필드가 없다(있으면 그것이 권한 확대 경로가 된다)
    pocket = out["pocket"]
    assert set(pocket) & {"readable_dept_ids", "permissions", "scope"} == set()


def test_recipient_only_sees_own_inbox(svc):
    """★★ 수신자는 **본인 요청만** 본다."""
    _created(svc, recipient_user_id="lee")
    _created(svc, recipient_user_id="park", purpose="다른 사람 것")
    assert [x["recipient_user_id"] for x in svc.inbox("lee")] == ["lee"]
    assert [x["recipient_user_id"] for x in svc.inbox("park")] == ["park"]


# ── 404 은폐 (§10-2) ──────────────────────────────────────────────────────
def test_other_users_delivery_is_hidden_everywhere(svc):
    """★★★ [§10-2] 상세·수락·거절 **모두** 남의 것은 `NotFoundOrHidden` 이다.

    ⚠️ 403 을 주면 "있지만 못 본다"가 되어 존재가 새어나간다. URL 을 직접 입력해도 마찬가지다."""
    d = _created(svc)
    did = d["delivery_id"]
    for fn in (lambda: svc.get(did, "stranger"),
               lambda: svc.accept(did, "stranger"),
               lambda: svc.reject(did, "stranger"),
               lambda: svc.revoke(did, "stranger")):
        with pytest.raises(NotFoundOrHidden):
            fn()


def test_sender_cannot_accept_own_delivery(svc):
    """★★ 보낸 사람이 자기 요청을 수락하는 경로를 막는다 — 수락은 수신자의 행위다."""
    d = _created(svc)
    with pytest.raises(NotFoundOrHidden):
        svc.accept(d["delivery_id"], "kim")


def test_other_users_pocket_is_hidden(svc):
    """★★ 남의 주머니는 수정할 수 없다(존재도 알리지 않는다)."""
    d = _created(svc)
    p = svc.accept(d["delivery_id"], "lee")["pocket"]
    with pytest.raises(NotFoundOrHidden):
        svc.update_pocket(p["pocket_id"], "stranger", pinned=True)


# ── 만료·거절·회수 ────────────────────────────────────────────────────────
def test_expiry_is_evaluated_at_read_time(svc):
    """★★★ 만료를 **읽는 시점에** 판정한다. 배치에 맡기면 배치가 멈춘 동안 만료된 요청이
    수락 가능해진다."""
    d = _created(svc, expires_in_days=1)
    later = svc.inbox("lee", today="2099-01-01")[0]
    assert later["status"] == EXPIRED and "만료" in later["note"]
    assert later["stored_status"] == PENDING, "저장된 상태를 덮어쓰지 않는다"


def test_expired_delivery_cannot_be_accepted(svc):
    d = _created(svc, expires_in_days=1)
    with pytest.raises(AppDeliveryError, match="만료"):
        svc.accept(d["delivery_id"], "lee", today="2099-01-01")


def test_reject_is_idempotent_and_keeps_reason(svc):
    """★ 거절 사유가 남아야 보낸 사람이 다시 판단할 수 있다."""
    d = _created(svc)
    r1 = svc.reject(d["delivery_id"], "lee", note="담당이 아닙니다")
    r2 = svc.reject(d["delivery_id"], "lee")
    assert r1["status"] == REJECTED and r2["replayed"] is True
    assert "담당이 아닙니다" in r1["response_note"]


def test_revoke_after_accept_marks_pocket_not_deletes_it(svc):
    """★★★ 수락된 앱을 **조용히 사라지게 하지 않는다.**

    말없이 없어지면 수신자는 이유를 알 수 없다. 주머니는 `REVOKED` 로 표시되고 이유가 남는다."""
    d = _created(svc)
    svc.accept(d["delivery_id"], "lee")
    svc.revoke(d["delivery_id"], "kim", reason="잘못 보냈습니다")
    assert svc.my_apps("lee") == []                       # 활성 목록에서는 빠진다
    all_apps = svc.my_apps("lee", include_revoked=True)
    assert len(all_apps) == 1 and all_apps[0]["status"] == "REVOKED"


def test_recipient_cannot_revoke(svc):
    """★ 회수는 보낸 사람의 행위다."""
    d = _created(svc)
    with pytest.raises(NotFoundOrHidden):
        svc.revoke(d["delivery_id"], "lee")


# ── 주머니 ────────────────────────────────────────────────────────────────
def test_pocket_rename_and_pin(svc):
    """★ 사용자가 자기 주머니를 정리할 수 있어야 목록이 쓸모 있게 유지된다."""
    d = _created(svc)
    p = svc.accept(d["delivery_id"], "lee")["pocket"]
    up = svc.update_pocket(p["pocket_id"], "lee", display_name="입고 입력", pinned=True)
    assert up["display_name"] == "입고 입력" and up["pinned"] == 1


def test_pocket_name_cannot_be_emptied(svc):
    d = _created(svc)
    p = svc.accept(d["delivery_id"], "lee")["pocket"]
    with pytest.raises(AppDeliveryError):
        svc.update_pocket(p["pocket_id"], "lee", display_name="   ")


# ── 원장 (§10-10) ─────────────────────────────────────────────────────────
def test_lifecycle_is_recorded_in_the_ledger(svc):
    """★★★ 운영 표는 상태를 **덮어쓴다**(PENDING → ACCEPTED). 누가 언제 무엇을 수락했는지는
    덮어쓸 수 없는 곳에 있어야 하고, 그것이 원장이다."""
    d = _created(svc)
    svc.accept(d["delivery_id"], "lee")
    svc.revoke(d["delivery_id"], "kim", reason="회수")
    evs = [e["event"] for e in svc._ledger.events]
    assert evs == ["APP_DELIVERY_CREATED", "APP_DELIVERY_ACCEPTED", "APP_DELIVERY_REVOKED"]
    assert all(e["subject_type"] == "app_delivery" for e in svc._ledger.events)
    assert svc._ledger.events[0]["actor_id"] == "kim"
    assert svc._ledger.events[1]["actor_id"] == "lee"


def test_ledger_failure_is_not_swallowed(tmp_path):
    """★★★ 원장 실패를 숨기고 성공 응답하지 않는다(§5.2).

    ⚠️ 여기서 예외를 잡아 로그만 남기면 **"수락 기록이 없는 수락"** 이 생긴다. 상태는 이미 바뀐
      뒤이므로 호출자가 그 사실을 알아야 한다 — 두 저장소의 원자성은 §12 독립 검토 대상이며
      `.agents/TEAM_BOARD.md` 에 요청을 올렸다."""
    store = CollaborationStore(db_path=str(tmp_path / "c.db"))
    svc = AppDelivery(store=store, ledger=_FakeLedger(fail=True))
    with pytest.raises(RuntimeError, match="원장"):
        svc.create(release_id="REL_OK", sender_user_id="kim", recipient_user_id="lee",
                   purpose="p", release_lookup=_lookup())


# ── 저장소 규약 ───────────────────────────────────────────────────────────
def test_schema_is_rerunnable(tmp_path):
    """★★ 마이그레이션은 재실행 가능하고 기존 데이터를 보존한다(§CL-BE-01)."""
    path = str(tmp_path / "c.db")
    s1 = CollaborationStore(db_path=path)
    s1.ensure_schema()
    s1.execute("INSERT INTO app_deliveries (delivery_id, release_id, sender_user_id, "
               "recipient_user_id, created_at, updated_at) VALUES ('d1','r','a','b','t','t')")
    CollaborationStore(db_path=path).ensure_schema()      # 두 번째 실행
    assert s1.one("SELECT * FROM app_deliveries WHERE delivery_id='d1'") is not None


def test_import_does_not_create_the_database(tmp_path, monkeypatch):
    """★★★ import 부작용으로 DB 를 만들면 테스트가 경로를 바꿔치기할 틈이 없고, **잘못된 작업
    디렉터리에 파일이 생긴다** — 이 저장소가 이미 겪은 유형이다."""
    import os
    path = tmp_path / "never.db"
    s = CollaborationStore(db_path=str(path))
    assert not os.path.exists(path), "생성자에서 DB 를 만들면 안 된다"
    s.ensure_schema()
    assert os.path.exists(path)
