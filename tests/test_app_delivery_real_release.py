"""[F-4] 생성 → 부서 전달 — **실제 라이브러리 릴리스로** 이음매를 관통시킨다.

## 왜 이 파일이 따로 필요했나

`test_app_delivery.py` 38건은 전달 «논리»를 잘 덮는다. 그런데 전부 **가짜
`release_lookup`** 을 주입한다. 즉 「릴리스가 있다고 치면」 그 뒤가 맞는지를 본다.

★★★ 그래서 **실제 `library/` 와 만나는 이음매는 한 번도 검증된 적이 없었다.**
  F-0 탐침이 `app_deliveries` 0건을 찾아냈을 때, 그것이 「안 썼다」인지 「돌리면 깨진다」인지
  가를 수 없었던 이유가 이것이다.

이 파일은 **주입하지 않는다** — 기본값(`_default_release_lookup`)이 디스크의 진짜
`release.json` 을 읽게 두고 끝까지 간다.

## ⚠️ 첫 판은 운영 `library/` 를 복사했다 — 그러면 깨끗한 clone 에서 «건너뛴다»

Codex 지적이 맞았다. **「자료가 없어 건너뛴 시험」은 통과가 아니다.** 그래서 고정 시험
자료를 저장소에 뒀다(`tests/fixtures/releases/`), 다만 **실제 `release.json` 에서 파생**했다 —
내 말로 쓰면 그 fixture 가 계약을 대신 정의한다(이 저장소가 이미 겪은 함정이다).

## 막히는 세 경우도 여기서 처음 덮는다

`platform_auth_scan` 이 없다 / 걸렸다 / `manifest` 가 무효 — **보안 관문**이고 실제 파일로
시험된 적이 없었다. 세 사유가 **다른 문장**이어야 한다는 것까지 센다(뭉개면 개발자가
있지도 않은 자체 인증 코드를 찾아 헤맨다).

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


#: ★ 저장소에 «고정»된 시험 릴리스. 실제 `release.json` 에서 파생했다(내 상상이 아니다).
#:   ⚠️⚠️ 첫 판은 운영 `library/` 를 복사했다. 그러면 **깨끗한 clone 에서는 건너뛴다** —
#:     Codex 가 지적했고 맞다. 「자료가 없어 건너뛴 시험」은 통과가 아니다.
#:   ★ 그래도 «가짜 lookup» 으로 되돌아가지 않는다. 파일은 디스크에 진짜로 있고
#:     `_default_release_lookup` 이 그것을 읽는다 — 주입하지 않는다.
#: ⚠️ 디렉터리 이름이 `releases` 인 이유: `.gitignore` 가 «어느 깊이든» `library/` 를
#:   무시한다(운영 릴리스 저장소용 규칙). `fixtures/library` 로 뒀다가 **커밋되지 않아
#:   깨끗한 clone 에서 실패할 뻔했다** — 고치려던 바로 그 문제다.
FIXTURE_RELEASES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "fixtures", "releases")

DELIVERABLE = "fx_deliverable_20260910_000000"
NO_SCAN = "fx_no_scan_20260910_000000"
SCAN_FAILED = "fx_scan_failed_20260910_000000"
MANIFEST_INVALID = "fx_manifest_invalid_20260910_000000"


def _seed(release_id: str) -> str:
    """격리 라이브러리에 고정 릴리스를 놓고, **서비스가 실제로 읽는지 확인**한다."""
    dst_root = library_paths.library_dir()
    src = os.path.join(FIXTURE_RELEASES, release_id)
    assert os.path.isdir(src), "고정 시험 자료가 없다: " + src
    os.makedirs(dst_root, exist_ok=True)
    dst = os.path.join(dst_root, release_id)
    if not os.path.exists(dst):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    #: ★ 재는 도구부터 증명한다 — 「놓았다」와 「서비스가 읽는다」는 다르다.
    from core.app_delivery import _default_release_lookup
    assert _default_release_lookup(release_id), (
        "격리 라이브러리에 놓았는데 서비스가 못 읽는다: " + release_id + " (" + dst_root + ")")
    return release_id


@pytest.fixture()
def real_release() -> str:
    """전달 가능한 고정 릴리스. **건너뛰지 않는다** — 깨끗한 clone 에서도 돈다."""
    return _seed(DELIVERABLE)


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


# ── ★★★ 막히는 세 경우 — 실제 파일로는 «한 번도» 시험된 적이 없었다 ─────────
#: 이 셋은 보안 관문이다. 자체 인증 코드를 가진 앱이 남의 손에 들어가면 안 된다.
#: 그리고 세 사유는 **다른 문장으로** 답해야 한다 — 뭉개면 개발자가 있지도 않은
#: 자체 인증 코드를 찾아 헤맨다(`app_delivery.py` 주석이 그렇게 적어 뒀다).

def test_a_release_without_an_auth_scan_cannot_be_delivered():
    """★ 「검사한 적 없음」과 「검사 통과」는 다르다."""
    rid = _seed(NO_SCAN)
    with pytest.raises(AppDeliveryError) as exc:
        app_delivery.create(release_id=rid, sender_user_id=SENDER,
                            recipient_user_id=RECIPIENT, purpose="검사 결과 없음")
    msg = str(exc.value)
    assert "검사한 적이" in msg or "검사 결과가 없어" in msg, msg
    assert "다시 게시" in msg, "사람이 무엇을 해야 하는지 없으면 고칠 수 없다"


def test_a_release_that_failed_the_auth_scan_cannot_be_delivered():
    """★★★ 자체 인증 코드가 있는 앱 — 앱은 호스트 인증을 «상속»해야 한다."""
    rid = _seed(SCAN_FAILED)
    with pytest.raises(AppDeliveryError) as exc:
        app_delivery.create(release_id=rid, sender_user_id=SENDER,
                            recipient_user_id=RECIPIENT, purpose="검사 실패")
    msg = str(exc.value)
    assert "자체 인증 코드" in msg, msg
    assert "3건" in msg, "몇 건인지 없으면 무엇을 고칠지 모른다"


def test_a_release_with_an_invalid_manifest_cannot_be_delivered():
    """★ 수신자가 «무엇을 수락하는지» 모르면 전달이 아니다."""
    rid = _seed(MANIFEST_INVALID)
    with pytest.raises(AppDeliveryError) as exc:
        app_delivery.create(release_id=rid, sender_user_id=SENDER,
                            recipient_user_id=RECIPIENT, purpose="manifest 무효")
    assert "Manifest" in str(exc.value)


def test_the_three_refusals_say_different_things():
    """★★★ 뭉개면 안 된다 — 세 사유가 같은 문장이면 원인을 못 찾는다."""
    msgs = []
    for rid in (NO_SCAN, SCAN_FAILED, MANIFEST_INVALID):
        _seed(rid)
        try:
            app_delivery.create(release_id=rid, sender_user_id=SENDER,
                                recipient_user_id=RECIPIENT, purpose="사유 구분")
        except AppDeliveryError as e:
            msgs.append(str(e))
    assert len(msgs) == 3, "셋 다 막혀야 한다"
    assert len(set(msgs)) == 3, "세 사유가 같은 문장이다 — 원인을 구분할 수 없다"


def test_the_fixture_library_is_committed_and_needs_no_live_data():
    """★ 깨끗한 clone 에서도 돈다 — 「자료가 없어 건너뛴 시험」은 통과가 아니다."""
    for rid in (DELIVERABLE, NO_SCAN, SCAN_FAILED, MANIFEST_INVALID):
        p = os.path.join(FIXTURE_RELEASES, rid, "release.json")
        assert os.path.isfile(p), "고정 자료가 저장소에 없다: " + p
