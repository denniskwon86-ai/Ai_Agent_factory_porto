"""★★★ [트랙 H] 발간물 가시성 — **남의 대외 발간물을 내보낼 수 있었다.**

## 무엇이 열려 있었나 (2026-08-08 격리 저장소 실측)

```
생성자 = kim · 대외 발간물(EXTERNAL)
남남이 조회        → 성공 — 내용이 보인다
남남이 법무승인    → 통과
남남이 경영승인    → 통과
남남이 대외발간    → 통과
```

아무 상관 없는 **식별 사용자**가 남의 대외 발간물을 조회하고, 두 필수 검토를 혼자 채우고,
외부로 내보낼 수 있었다. 이 저장소가 `project.release` 에 대해 쓴 말이 그대로 적용된다 —
**「남에게 나간다. 회수해도 이미 본 사람이 있다」.**

원인: `Publication.get(id, user_id)` 이 `user_id` 를 **받고도 쓰지 않았다.** 판정이 아예 없었다.

## 왜 기존 테스트 33건이 못 잡았나

전부 **절차 게이트**만 봤다 — 렌더 → 승인 → 발간 순서, 대외 이중 검토, 반려 사유 필수.
교차 사용자 접근은 **한 건도 없었다.** 절차가 옳아도 «누가» 가 비어 있으면 통제가 아니다.
이 파일이 그 축을 맡는다.

## 하지 않은 것 — 이중 승인의 «사람» 분리

`EXECUTIVE`+`LEGAL_DISCLOSURE` 를 서로 다른 사람이 하도록 강제하지 **않았다**(사용자 결정
2026-08-08). 실측 근거: 조직에 법무 부서가 없고(활성 12개 부서에 `legal` 없음) 1인 부서가
넷이라, 강제하면 대외 발간이 `hq` 6명·실질 관리자 3명에게 몰리고 대행 경로가 막힌다.
막힌 흐름은 «승인 계정 돌려쓰기» 로 우회되며 그러면 기록만 더 나빠진다.

★ **가시성만으로 실제 위험의 대부분이 닫힌다** — 위험했던 것은 「한 사람이 두 번 눌렀다」가
  아니라 「관계없는 사람이 건드렸다」였다. 관계자 안에서 몇 사람이 승인하는가는 조직이
  정할 일이지 제품이 막을 일이 아니다.
"""
import os

import pytest

from core.collaboration_store import CollaborationStore
from core.publication import (AUDIENCE_EXTERNAL, AUDIENCE_INTERNAL, REVIEW_EXECUTIVE,
                              REVIEW_LEGAL, SOURCE_DECISION, UNRESTRICTED, Publication,
                              PublicationNotFound)
from tests.test_publication_control import SOURCE, _Ledger

#: 발간물이 속한 조직. 관계자는 이것을 갖고 남남은 갖지 않는다.
OWNER_SCOPE = "MNM_BATTERY"
INSIDER = frozenset({OWNER_SCOPE})
OUTSIDER = frozenset({"sales"})


@pytest.fixture
def svc(tmp_path):
    return Publication(store=CollaborationStore(db_path=str(tmp_path / "c.db")),
                       ledger=_Ledger(),
                       decision_source=lambda t, i: SOURCE if i == "dec_1" else None)


def _pub(svc, audience=AUDIENCE_EXTERNAL, scope_id=OWNER_SCOPE):
    p = svc.create(title="대외 보고", created_by="kim", source_type=SOURCE_DECISION,
                   source_id="dec_1", audience=audience,
                   publication_type="EXTERNAL_PUBLIC", security_class="PUBLIC",
                   scope_id=scope_id)
    return p["publication_id"]


def _ready_for_publish(svc, pid):
    """대외 발간 직전까지 관계자가 정상 절차로 올려 둔다."""
    svc.render(pid, "kim", viewer_scopes=INSIDER)
    svc.request_approval(pid, "kim", viewer_scopes=INSIDER)
    svc.approve(pid, "boss", review_type=REVIEW_LEGAL, viewer_scopes=INSIDER)
    svc.approve(pid, "boss", review_type=REVIEW_EXECUTIVE, viewer_scopes=INSIDER)


# ── ① 남남은 존재조차 알 수 없다 ────────────────────────────────────────────
def test_outsider_cannot_read(svc):
    """★★★ 이 파일 전체의 이유. **403 이 아니라 404** — 403 은 «있지만 못 본다» 를
    알려주므로 존재가 새어나간다(CL §3-10 경계표)."""
    pid = _pub(svc)
    with pytest.raises(PublicationNotFound):
        svc.get(pid, "완전히_남남", OUTSIDER)


@pytest.mark.parametrize("action", ["render", "request_approval", "correct", "withdraw"])
def test_outsider_cannot_mutate(svc, action):
    """변경 경로도 전부 막힌다 — `get()` 하나를 지나므로 함께 닫힌다."""
    pid = _pub(svc)
    fn = getattr(svc, action)
    with pytest.raises(PublicationNotFound):
        if action in ("correct", "withdraw"):
            fn(pid, "완전히_남남", "사유", OUTSIDER)
        else:
            fn(pid, "완전히_남남", viewer_scopes=OUTSIDER)


def test_outsider_cannot_approve(svc):
    """⚠️ 승인은 «검토 자격» 이전에 **그 문서에 닿을 수 있는가** 의 문제다."""
    pid = _pub(svc)
    svc.render(pid, "kim", viewer_scopes=INSIDER)
    svc.request_approval(pid, "kim", viewer_scopes=INSIDER)
    with pytest.raises(PublicationNotFound):
        svc.approve(pid, "완전히_남남", review_type=REVIEW_LEGAL, viewer_scopes=OUTSIDER)


def test_outsider_cannot_publish(svc):
    """★★★ 되돌릴 수 없는 유일한 경로. 게이트가 전부 통과한 상태에서도 남남은 못 낸다."""
    pid = _pub(svc)
    _ready_for_publish(svc, pid)
    assert svc.get(pid, "boss", INSIDER)["can_publish"] is True
    with pytest.raises(PublicationNotFound):
        svc.publish(pid, "완전히_남남", [{"target": "press@x", "channel": "EMAIL"}],
                    viewer_scopes=OUTSIDER)


def test_outsider_list_is_empty(svc):
    """목록만 열어 둬도 «어느 부서가 무엇을 대외로 내보내려 하는가» 가 샌다."""
    _pub(svc)
    assert svc.list(viewer_scopes=OUTSIDER, user_id="완전히_남남") == []
    assert len(svc.list(viewer_scopes=INSIDER, user_id="boss")) == 1


# ── ② 관계자·작성자·관리자는 막히지 않는다 (운영 흐름 보존) ─────────────────
def test_insider_completes_the_whole_flow(svc):
    """★ 봉합이 일을 막지 않는다는 증거. 관계자는 종전과 똑같이 끝까지 간다.

    ⚠️ 여기서 `boss` 한 사람이 두 검토를 **모두** 한다 — 사용자 결정 2026-08-08 에 따라
      «사람 분리» 는 강제하지 않는다. 이 단언을 «두 사람이어야 한다» 로 바꾸려면 조직에
      법무 담당이 생긴 뒤에 하라(지금은 1인 부서가 넷이다)."""
    pid = _pub(svc)
    _ready_for_publish(svc, pid)
    out = svc.publish(pid, "boss", [{"target": "press@x", "channel": "EMAIL"}],
                      viewer_scopes=INSIDER)
    assert out["status"] in ("PUBLISHED", "APPROVED")   # 어댑터가 없으면 APPROVED 에 머문다


def test_creator_sees_own_publication_without_scope_match(svc):
    """작성자는 범위가 어긋나도 자기 것을 본다 — 부서 이동·범위 미지정에서도 잃지 않는다."""
    pid = _pub(svc)
    assert svc.get(pid, "kim", OUTSIDER)["publication_id"] == pid


def test_unrestricted_viewer_sees_everything(svc):
    """플랫폼 관리자·조직 미도입 설치. **빈 집합과 다르다.**"""
    pid = _pub(svc)
    assert svc.get(pid, "admin", UNRESTRICTED)["publication_id"] == pid


def test_empty_scope_publication_is_not_company_wide(svc):
    """⚠️ 범위가 비어 있는 발간물은 «전사» 가 아니라 «미지정» 이다 — 작성자만 본다.
    미지정을 전사 공개로 읽으면 **분류하지 않은 문서가 전부 열린다.**"""
    pid = _pub(svc, scope_id="")
    assert svc.get(pid, "kim", OUTSIDER)["publication_id"] == pid       # 작성자
    with pytest.raises(PublicationNotFound):
        svc.get(pid, "남남", OUTSIDER)


def test_internal_audience_is_scoped_too(svc):
    """대내 발간도 범위를 지킨다 — «내부» 는 «전 직원» 이 아니다."""
    pid = _pub(svc, audience=AUDIENCE_INTERNAL)
    with pytest.raises(PublicationNotFound):
        svc.get(pid, "남남", OUTSIDER)


# ── ③ 라우트가 범위를 넘기지 않으면 봉합이 무의미해진다 ─────────────────────
def test_every_publication_route_passes_viewer_scopes():
    """★★ `viewer_scopes` 를 넘기지 않으면 서비스는 **판정을 통째로 끈다**(레거시 계약).
    즉 라우트 한 곳만 빠뜨려도 그 경로가 조용히 다시 열린다 — 그것을 여기서 잡는다.

    ⚠️ 이 검사는 **소스를 읽는다.** 라우트를 호출해 확인하려면 주체·저장소를 다 세워야 하고
      그러면 검사 자체가 무거워져 아무도 유지하지 않는다(트랙 G 가 겪은 유형)."""
    import inspect

    import api.routes.publication_control as pc
    missing = []
    for r in pc.router.routes:
        methods = {m for m in (getattr(r, "methods", set()) or set())
                   if m not in ("HEAD", "OPTIONS")}
        if not methods:
            continue
        try:
            src = inspect.getsource(r.endpoint)
        except Exception:
            continue
        if "publication." not in src:
            continue                       # 서비스를 부르지 않는 라우트
        if "_scopes(p)" not in src:
            missing.append(f"{sorted(methods)} {r.path}")
    # ⚠️ 생성(`POST /publications`)은 조회가 아니라 **새로 만드는 것**이라 판정 모양이 다르다 —
    #   «내가 속하지 않은 조직 이름으로 만들 수 없다» 를 라우트에서 검사한다. 그래서 이 검사는
    #   `_scopes(p)` 사용 여부만 보고, 무엇을 하는지는 아래 전용 검사가 본다.
    assert not missing, (
        "발간 서비스를 부르면서 열람 범위를 넘기지 않는 라우트 — 그 경로는 판정이 꺼진다:\n  "
        + "\n  ".join(missing))


def test_create_rejects_foreign_scope():
    """★ 남의 조직 이름으로 발간물을 만들 수 없다.

    ⚠️ 종전에는 `req.scope_id` 를 검증 없이 받았다. 그렇게 만든 문서는 **그 부서 사람들에게
      보이고** 작성자도 계속 볼 수 있다 — 가시성을 막아 놓고 이 입구를 열어 두면 우회로가 된다.
    ⚠️ 400 이다(404 가 아니다). 값을 사용자가 직접 입력했으므로 존재가 새지 않고, 무엇이
      잘못됐는지 알려주지 않으면 고칠 수가 없다."""
    import inspect

    import api.routes.publication_control as pc
    src = inspect.getsource(pc.create_publication)
    assert "not in allowed" in src, "생성 시 조직 범위를 검사하지 않는다"
    assert "status_code=400" in src, "범위 위반을 400 으로 알려야 한다"


def test_route_helper_does_not_pass_none():
    """⚠️ `_scopes()` 가 `None` 을 돌려주면 서비스가 판정을 끈다. 무제한은 **센티넬**이다."""
    from types import SimpleNamespace

    import api.routes.publication_control as pc
    unrestricted = SimpleNamespace(scope=SimpleNamespace(unrestricted=True))
    assert pc._scopes(unrestricted) is UNRESTRICTED
    limited = SimpleNamespace(scope=SimpleNamespace(
        unrestricted=False, readable_dept_ids=frozenset({"quality"}),
        readable_scope_nodes=frozenset({"node_q"})))
    got = pc._scopes(limited)
    assert got is not None and got == frozenset({"quality", "node_q"})
