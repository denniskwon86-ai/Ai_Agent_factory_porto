"""[F-4] 생성 → 부서 전달 — **실제 라이브러리 릴리스로** 이음매를 관통시킨다.

## 왜 이 파일이 따로 필요했나

`test_app_delivery.py` 38건은 전달 «논리»를 잘 덮는다. 그런데 전부 **가짜
`release_lookup`** 을 주입한다. 즉 「릴리스가 있다고 치면」 그 뒤가 맞는지를 본다.

★★★ 그래서 **실제 `library/` 와 만나는 이음매는 한 번도 검증된 적이 없었다.**
  F-0 탐침이 `app_deliveries` 0건을 찾아냈을 때, 그것이 「안 썼다」인지 「돌리면 깨진다」인지
  가를 수 없었던 이유가 이것이다.

이 파일은 **주입하지 않는다** — 기본값(`_default_release_lookup`)이 실제 `library/` 를
읽게 두고, 거기 있는 릴리스로 끝까지 간다.

⚠️ 라이브러리가 비어 있으면 **건너뛴다.** 없는 것을 있다고 가정하지 않는다.
⚠️ 협업 저장소는 conftest 가 tmp 로 격리한다 — 운영 `collaboration.db` 에 쓰지 않는다.
"""
from __future__ import annotations

import glob
import json
import os
import shutil

import pytest

from core import library_paths
from core.app_delivery import AppDeliveryError, app_delivery
from core.paths import PROJECT_ROOT

SENDER = "t_manager_a@test.invalid"
RECIPIENT = "t_member_a@test.invalid"


@pytest.fixture()
def real_release() -> str:
    """서비스가 **실제로 여는** 라이브러리에 진짜 릴리스를 하나 놓고 그 id 를 준다.

    ⚠️⚠️ 첫 판은 `PROJECT_ROOT/library` 를 훑었다가 틀렸다. conftest 가 `library_paths`
      를 tmp 로 돌려놓기 때문에 **서비스는 다른 곳을 본다.** 「심었다/비었다」를 말하기
      전에 «앱이 여는 경로»를 물어야 한다.

    ★ 그래서 운영 라이브러리에서 릴리스 «하나를 복사»해 격리 라이브러리에 놓는다 —
      읽는 것은 진짜 내용이고, 쓰는 곳은 tmp 다. conftest 가 템플릿에 쓰는 방식과 같다."""
    dst_root = library_paths.library_dir()
    src = sorted(glob.glob(os.path.join(PROJECT_ROOT, "library", "*", "release.json")))
    if not src:
        pytest.skip("운영 library/ 에 릴리스가 없다 — 먼저 생성·게시가 있어야 한다.")
    src_dir = os.path.dirname(src[0])
    rid = os.path.basename(src_dir)
    os.makedirs(dst_root, exist_ok=True)
    dst = os.path.join(dst_root, rid)
    if not os.path.exists(dst):
        shutil.copytree(src_dir, dst, dirs_exist_ok=True)
    #: ★ 재는 도구부터 증명한다 — 서비스가 이것을 «실제로 읽는지» 먼저 확인한다.
    from core.app_delivery import _default_release_lookup
    assert _default_release_lookup(rid), (
        "격리 라이브러리에 놓았는데 서비스가 못 읽는다: " + rid + " (" + dst_root + ")")
    return rid


# ── ★★★ 한 번도 검증되지 않았던 이음매 ──────────────────────────────────────
def test_the_real_library_is_readable_by_the_delivery_service(real_release):
    """전달 서비스가 «주입 없이» 실제 릴리스를 읽는가.

    이것이 안 되면 전달은 영원히 0건이고, 시험은 가짜 lookup 으로 초록이다."""
    from core.app_delivery import _default_release_lookup
    rel = _default_release_lookup(real_release)
    assert rel, "실제 릴리스를 읽지 못했다: " + real_release
    assert isinstance(rel, dict) and rel


def test_delivery_of_a_real_release_goes_through(real_release):
    """★★★ F-4 의 핵심 질문 — 생성물이 «사람 손에» 닿는가.

    주입하지 않는다. 기본 lookup 이 실제 `library/` 를 읽는다."""
    out = app_delivery.create(
        release_id=real_release, sender_user_id=SENDER, recipient_user_id=RECIPIENT,
        purpose="F-4 이음매 확인 — 실제 릴리스 전달")
    assert out["delivery_id"]
    assert out["release_id"] == real_release
    assert out["status"]
    #: 전달 시점의 권한·매니페스트가 «박제»돼야 나중에 「무엇을 받았나」에 답할 수 있다.
    assert out.get("manifest_fingerprint"), "매니페스트 지문이 없으면 받은 것이 무엇인지 굳지 않는다"


def test_a_release_that_is_not_in_the_library_is_refused():
    """★ 없는 앱을 전달하면 수신자는 «수락할 수 없는 요청»을 받는다."""
    with pytest.raises(Exception) as exc:
        app_delivery.create(release_id="없는릴리스_20990101", sender_user_id=SENDER,
                            recipient_user_id=RECIPIENT, purpose="있으면 안 된다")
    assert exc.value


# ── 받는 쪽까지 — 「전달됐다」는 보낸 쪽 사실일 뿐이다 ───────────────────────
def test_the_recipient_actually_sees_it(real_release):
    """보냈다고 닿은 것이 아니다. 받은 사람의 목록에 있어야 «전달»이다."""
    made = app_delivery.create(release_id=real_release, sender_user_id=SENDER,
                               recipient_user_id=RECIPIENT, purpose="수신 확인")
    inbox = app_delivery.inbox(RECIPIENT)
    assert any(d["delivery_id"] == made["delivery_id"] for d in inbox), \
        "보낸 것이 받는 사람 목록에 없다 — 이음매가 끊긴다"


def test_a_third_party_does_not_see_it(real_release):
    """★ 당사자가 아니면 보이지 않는다 — 전달은 «한 사람에게»다."""
    made = app_delivery.create(release_id=real_release, sender_user_id=SENDER,
                               recipient_user_id=RECIPIENT, purpose="격리 확인")
    other = app_delivery.inbox("t_member_b@test.invalid")
    assert all(d["delivery_id"] != made["delivery_id"] for d in other)


def test_accepting_completes_the_seam(real_release):
    """★★★ F-4 가 «이어졌다»고 말할 수 있는 지점 — 받은 사람이 수락한다."""
    made = app_delivery.create(release_id=real_release, sender_user_id=SENDER,
                               recipient_user_id=RECIPIENT, purpose="수락까지")
    done = app_delivery.accept(made["delivery_id"], RECIPIENT)
    assert done["status"] != made["status"], "수락했는데 상태가 그대로다"
    assert done.get("responded_at"), "응답 시각이 없으면 «언제 받았나»에 답할 수 없다"


def test_the_sender_cannot_accept_on_the_recipients_behalf(real_release):
    """보낸 사람이 대신 수락하면 «전달»이 아니라 «자기 배포»다."""
    made = app_delivery.create(release_id=real_release, sender_user_id=SENDER,
                               recipient_user_id=RECIPIENT, purpose="대리 수락 금지")
    with pytest.raises(Exception):
        app_delivery.accept(made["delivery_id"], SENDER)


# ── 목적·만료 — 설계가 요구한 것이 실제로 강제되는가 ────────────────────────
def test_purpose_is_required_on_a_real_release(real_release):
    """목적 없는 앱을 받은 사람은 수락 여부를 판단할 근거가 없다."""
    with pytest.raises(AppDeliveryError, match="목적"):
        app_delivery.create(release_id=real_release, sender_user_id=SENDER,
                            recipient_user_id=RECIPIENT, purpose="   ")


def test_delivery_to_self_is_refused(real_release):
    with pytest.raises(AppDeliveryError):
        app_delivery.create(release_id=real_release, sender_user_id=SENDER,
                            recipient_user_id=SENDER, purpose="자기 자신")


# ── 제품 경로(HTTP)로도 도는가 ──────────────────────────────────────────────
def test_the_route_serves_preflight_for_a_real_release(real_release):
    """★ 화면이 «권한 Manifest» 3단계를 그리는 원천이다(UI 설계서 §5.3)."""
    from fastapi.testclient import TestClient
    import main
    r = TestClient(main.app).get("/api/v1/app-deliveries/preflight",
                                 params={"release_id": real_release},
                                 headers={"X-Factory-User": SENDER})
    assert r.status_code == 200, r.text[:200]
    assert r.json().get("data") is not None
