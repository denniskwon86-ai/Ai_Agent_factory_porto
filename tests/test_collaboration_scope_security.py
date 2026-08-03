"""★★★ [CL-1] 협업 API 경계 — **403 이 아니라 404 로 은폐한다.**

작업서 §3-10: "타 회사·부서·사용자의 자원은 403/409로 존재를 알리지 않고 권한 경계에서 404로
은폐한다. 인증 실패 401과 요청 형식 오류 422는 그대로 구분한다."

## 왜 코드가 갈려야 하는가

| 응답 | 사용자가 알게 되는 것 |
|---|---|
| 403 | "그 자원은 **있다.** 다만 내가 못 본다" ← 존재가 새어나간다 |
| 404 | "그런 것은 없다" ← 아무것도 알려주지 않는다 |
| 401 | "로그인이 필요하다" ← 숨기면 사용자가 무엇을 해야 할지 모른다 |
| 422 | "요청 형식이 틀렸다" ← 형식은 알려줘도 정보가 새지 않는다 |

⚠️ URL 을 직접 입력하는 경로에서도 같아야 한다. 화면에서 링크를 숨기는 것은 통제가 아니다.

이 파일은 **모듈이 아니라 라우트**를 부른다 — 모듈이 옳게 판정해도 라우트가 다른 코드로 답하면
계약이 깨지고, 그 차이는 화면에서 보이지 않는다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import Principal, current_principal
from core.org_directory import AccessScope

RELEASE = {
    "release_id": "REL_OK", "version": "1.0",
    "manifest": {"valid": True, "fingerprint": "f" * 32,
                 "manifest": {"auth_mode": "PLATFORM_INHERITED", "capabilities": []}},
    "platform_auth_scan": {"ok": True, "summary": {"blocking": 0}},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """실물 라우터 + tmp 저장소. 사용자는 헤더 대신 의존성 오버라이드로 바꾼다."""
    import api.routes.app_delivery_control as adc
    import core.app_delivery as ad
    from core.app_delivery import AppDelivery
    from core.collaboration_store import CollaborationStore

    class _Ledger:
        def append(self, *a, **kw):
            return {"event_id": "x"}

    svc = AppDelivery(store=CollaborationStore(db_path=str(tmp_path / "c.db")),
                      ledger=_Ledger())
    # 릴리스 조회를 tmp 표로 바꾼다 — 실제 `library/` 를 읽으면 테스트가 로컬 파일에 좌우된다.
    monkeypatch.setattr(ad, "_default_release_lookup",
                        lambda rid: RELEASE if rid == "REL_OK" else None, raising=False)
    monkeypatch.setattr(adc, "app_delivery", svc, raising=False)

    app = FastAPI()
    app.include_router(adc.router)
    state = {"uid": "kim"}

    def _principal():
        return Principal(user_id=state["uid"],
                         scope=AccessScope(user_id=state["uid"], unrestricted=False,
                                           readable_dept_ids=frozenset({"hq"})))
    app.dependency_overrides[current_principal] = _principal
    c = TestClient(app)
    c.state = state          # 테스트에서 사용자를 바꾸는 손잡이
    return c


def _create(c, recipient="lee", **kw):
    body = {"release_id": "REL_OK", "recipient_user_id": recipient, "purpose": "협업"}
    body.update(kw)
    return c.post("/api/v1/app-deliveries", json=body)


# ── 401: 인증 실패는 숨기지 않는다 ─────────────────────────────────────────
def test_anonymous_gets_401_not_404(client):
    """★★★ 식별되지 않은 요청은 **401** 이다.

    ⚠️ 이것을 404 로 숨기면 사용자는 "로그인하면 된다"는 것을 모르고, 시스템이 고장났다고
      판단한다 — 이 저장소가 목록 통제에서 겪은 것과 같은 유형(빈 화면의 이유를 말하지 않는 것)."""
    client.state["uid"] = ""
    for r in (_create(client),
              client.get("/api/v1/app-deliveries/inbox"),
              client.get("/api/v1/me/apps")):
        assert r.status_code == 401, r.text
        assert "사용자 식별" in r.json()["detail"]


# ── 422: 형식 오류는 그대로 ────────────────────────────────────────────────
def test_bad_body_is_422(client):
    """★★ 형식 오류를 400/404 로 뭉개면 개발자가 원인을 찾을 수 없다."""
    assert client.post("/api/v1/app-deliveries", json={"release_id": "REL_OK"}).status_code == 422


def test_unknown_field_is_rejected(client):
    """★★ `extra='forbid'`(§CL-BE-01) — 오타 필드를 조용히 무시하면 호출자는 값이 반영됐다고
    믿는다(예: `purpse` 로 보낸 목적이 사라진다)."""
    r = client.post("/api/v1/app-deliveries",
                    json={"release_id": "REL_OK", "recipient_user_id": "lee",
                          "purpose": "협업", "purpse": "오타"})
    assert r.status_code == 422


# ── 404: 남의 것·없는 것 ───────────────────────────────────────────────────
def test_other_users_delivery_is_404_on_every_route(client):
    """★★★ [§10-2] 상세·수락·거절·회수·재배정 **전부** 404 다.

    URL 직접 입력으로도 존재가 드러나지 않아야 한다 — 화면에서 링크를 숨기는 것은 통제가 아니다."""
    did = _create(client).json()["data"]["delivery_id"]
    client.state["uid"] = "stranger"
    assert client.get(f"/api/v1/app-deliveries/{did}").status_code == 404
    for path in ("accept", "reject", "revoke"):
        r = client.post(f"/api/v1/app-deliveries/{did}/{path}", json={})
        assert r.status_code == 404, f"{path}: {r.status_code} — 403 은 존재를 알린다"
    r = client.post(f"/api/v1/app-deliveries/{did}/reassign-request",
                    json={"note": "담당 아님"})
    assert r.status_code == 404


def test_nonexistent_release_is_404(client):
    """★★★ [§10-3] 다른 회사 릴리스 id 를 넣어 존재를 탐지하는 경로를 막는다."""
    assert _create(client, release_id="REL_SOMEONE_ELSE").status_code == 404


def test_nonexistent_delivery_is_404(client):
    assert client.get("/api/v1/app-deliveries/del_nope").status_code == 404


def test_other_users_pocket_patch_is_404(client):
    did = _create(client).json()["data"]["delivery_id"]
    client.state["uid"] = "lee"
    pid = client.post(f"/api/v1/app-deliveries/{did}/accept",
                      json={}).json()["data"]["pocket"]["pocket_id"]
    client.state["uid"] = "stranger"
    assert client.patch(f"/api/v1/me/apps/{pid}", json={"pinned": True}).status_code == 404


# ── 400: 내 자원에 대한 정책 위반은 이유를 말한다 ──────────────────────────
def test_policy_violation_on_own_resource_is_400_with_reason(client):
    """★★ 내 자원이면 이유를 말해도 정보가 새지 않는다 — 오히려 말하지 않으면 사용자가 다음
    행동을 알 수 없다."""
    r = _create(client, purpose="")
    assert r.status_code == 400 and "목적" in r.json()["detail"]


def test_double_response_is_400_not_500(client):
    did = _create(client).json()["data"]["delivery_id"]
    client.state["uid"] = "lee"
    client.post(f"/api/v1/app-deliveries/{did}/reject", json={"note": "거절"})
    r = client.post(f"/api/v1/app-deliveries/{did}/accept", json={})
    assert r.status_code == 400 and "REJECTED" in r.json()["detail"]


# ── 흐름 ──────────────────────────────────────────────────────────────────
def test_full_flow_through_the_api(client):
    """★★★ 전달 → 수신함 → 수락 → 내 앱 이 **API 로** 이어진다.

    모듈 테스트가 통과해도 라우트 배선이 빠지면 화면에서는 아무 일도 일어나지 않는다 —
    오늘 아침 목록 API 에서 겪은 유형이다."""
    did = _create(client).json()["data"]["delivery_id"]
    assert [d["delivery_id"] for d in
            client.get("/api/v1/app-deliveries/outbox").json()["data"]] == [did]

    client.state["uid"] = "lee"
    inbox = client.get("/api/v1/app-deliveries/inbox").json()["data"]
    assert [d["delivery_id"] for d in inbox] == [did] and inbox[0]["can_respond"] is True

    acc = client.post(f"/api/v1/app-deliveries/{did}/accept",
                      json={"display_name": "입고 입력"}).json()["data"]
    assert acc["status"] == "ACCEPTED" and acc["scope_unchanged"] is True
    apps = client.get("/api/v1/me/apps").json()["data"]
    assert len(apps) == 1 and apps[0]["display_name"] == "입고 입력"

    # 재수락(중복 클릭) — 주머니는 여전히 하나
    client.post(f"/api/v1/app-deliveries/{did}/accept", json={})
    assert len(client.get("/api/v1/me/apps").json()["data"]) == 1


def test_idempotency_key_replays_through_the_api(client):
    """★★ 네트워크 재시도에도 전달이 하나다."""
    a = _create(client, idempotency_key="k9").json()["data"]
    b = _create(client, idempotency_key="k9").json()["data"]
    assert a["delivery_id"] == b["delivery_id"] and b["replayed"] is True
    assert len(client.get("/api/v1/app-deliveries/outbox").json()["data"]) == 1


def test_reassign_request_does_not_auto_route(client):
    """★★★ 시스템이 **다른 사람에게 자동 재배정하지 않는다.**

    누가 담당인지는 조직이 정하는 것이고, 시스템이 추측해 넘기면 아무도 그 배정을 근거로
    설명할 수 없다."""
    did = _create(client).json()["data"]["delivery_id"]
    client.state["uid"] = "lee"
    r = client.post(f"/api/v1/app-deliveries/{did}/reassign-request",
                    json={"note": "물류팀 담당입니다"}).json()["data"]
    assert r["reassign_requested"] is True
    assert "자동으로 다른 담당자를 지정하지 않습니다" in r["note"]
    assert "[재배정 요청]" in r["response_note"]


def test_reassign_without_reason_is_400(client):
    """★ 사유가 없으면 보낸 사람이 다시 판단할 수 없다."""
    did = _create(client).json()["data"]["delivery_id"]
    client.state["uid"] = "lee"
    assert client.post(f"/api/v1/app-deliveries/{did}/reassign-request",
                       json={"note": ""}).status_code == 400
