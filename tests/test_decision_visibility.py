"""★★★ [트랙 H] 의사결정 안건 가시성 — **머리말이 규정한 404 가 구현돼 있지 않았다.**

`api/routes/decision_control.py` 머리말은 이렇게 적어 두었다:

    · 참여자가 아닌 안건 → **404** (403 은 존재를 알린다)

**그런데 그 판정이 없었다.** 2026-08-08 격리 저장소 실측:

```
안건 생성자 = kim (MNM_BATTERY)
남남이 조회      → 성공 — 패키지·참여자·회의가 전부 보인다
남남이 뷰 렌더    → 통과
남남이 검토요청   → 통과      ← 남의 안건에 **참여자를 임의로 추가**한다
남남이 회의소집   → 통과
남남이 참여응답   → 404 은폐   ← 이 둘만 `my_role` 을 봤다
남남이 결정      → 404 은폐
```

`decide()`·`participant_response()` 만 역할을 검사했고, 나머지는 `get()` 을 그냥 지났다.
`core/publication.py` 에서 같은 날 잡은 것과 **같은 유형**이다 — 규약이 문서에만 있고
구현에 없으면 그것은 규약이 아니다.

## 왜 «참여자» 를 판정에 넣는가

안건은 여러 부서가 함께 보는 것이다. 참여자로 지정된 사람은 **자기 부서 밖 안건이라도
답해야 한다** — 범위만 보면 그 사람이 자기 할 일을 못 본다. 그래서 판정은
작성자 · 참여자 · 조직 범위 · 무제한 주체 넷이다.

## 이 파일이 맡는 축

기존 `test_decision_case.py` 35건은 **절차**(상태 전이·차단 조건·결정 자격)를 본다.
여기는 **«누가»** 를 본다. 절차가 옳아도 관계없는 사람이 닿을 수 있으면 통제가 아니다.
"""
import pytest

from core.collaboration_store import CollaborationStore
from core.decision_case import UNRESTRICTED, DecisionCase, DecisionNotFound
from tests.test_decision_case import EV, PKG, _Ledger

OWNER_SCOPE = "MNM_BATTERY"
INSIDER = frozenset({OWNER_SCOPE})
OUTSIDER = frozenset({"sales"})
OUT = "완전히_남남"


@pytest.fixture
def svc(tmp_path):
    return DecisionCase(store=CollaborationStore(db_path=str(tmp_path / "c.db")),
                        ledger=_Ledger())


@pytest.fixture
def did(svc):
    c = svc.create(question="제3공장을 증설할까요?", created_by="kim", simulation_run_id="run_1",
                   baseline_id="snap_1", package=PKG, evidence=EV, scope_id=OWNER_SCOPE)
    return c["decision_id"]


# ── ① 남남은 존재조차 알 수 없다 ────────────────────────────────────────────
def test_outsider_cannot_read(svc, did):
    """★★★ 패키지·참여자·회의가 전부 보이고 있었다."""
    with pytest.raises(DecisionNotFound):
        svc.get(did, OUT, viewer_scopes=OUTSIDER)


def test_outsider_cannot_render_view(svc, did):
    """세 관점 렌더는 **패키지 본문을 그대로 노출**한다."""
    with pytest.raises(DecisionNotFound):
        svc.render_view(did, "decider", OUT, viewer_scopes=OUTSIDER)


def test_outsider_cannot_add_participants(svc, did):
    """★★ 가장 나빴던 것 — 남의 안건에 **참여자를 임의로 넣을 수 있었다.**

    ⚠️ 참여자가 되면 그 사람은 이후 그 안건을 계속 볼 수 있다. 즉 이 한 경로가
      가시성 판정 전체를 무력화하는 «스스로 초대하기» 였다."""
    with pytest.raises(DecisionNotFound):
        svc.request_review(did, OUT, [{"user_id": OUT, "role": "DECIDER"}],
                           viewer_scopes=OUTSIDER)


def test_outsider_cannot_call_a_meeting(svc, did):
    with pytest.raises(DecisionNotFound):
        svc.request_meeting(did, OUT, title="긴급", viewer_scopes=OUTSIDER)


@pytest.mark.parametrize("action", ["participant_response", "decide"])
def test_outsider_still_blocked_on_role_gated_paths(svc, did, action):
    """이 둘은 종전에도 막혀 있었다 — 봉합이 그것을 **깨지 않았는지** 확인한다."""
    with pytest.raises(DecisionNotFound):
        if action == "participant_response":
            svc.participant_response(did, OUT, "AGREE", viewer_scopes=OUTSIDER)
        else:
            svc.decide(did, OUT, "APPROVED", "사유", viewer_scopes=OUTSIDER)


# ── ② 관계자는 막히지 않는다 (운영 흐름 보존) ───────────────────────────────
def test_creator_sees_own_case_outside_scope(svc, did):
    """작성자는 범위가 어긋나도 자기 안건을 본다 — 부서 이동에서도 잃지 않는다."""
    assert svc.get(did, "kim", viewer_scopes=OUTSIDER)["decision_id"] == did


def test_participant_sees_case_outside_own_scope(svc, did):
    """★★ **참여자는 자기 부서 밖 안건이라도 본다.**

    이것이 «범위만 보면 안 되는» 이유다 — 다른 부서가 나를 검토자로 지정했는데 내가 그
    안건을 못 보면, 나는 답해야 할 일이 있다는 것조차 알 수 없다."""
    svc.request_review(did, "kim", [{"user_id": "boss", "role": "DECIDER"}],
                       viewer_scopes=INSIDER)
    assert svc.get(did, "boss", viewer_scopes=OUTSIDER)["my_role"] == "DECIDER"


def test_same_scope_member_sees_case(svc, did):
    assert svc.get(did, "누구든", viewer_scopes=INSIDER)["decision_id"] == did


def test_unrestricted_viewer_sees_everything(svc, did):
    assert svc.get(did, "admin", viewer_scopes=UNRESTRICTED)["decision_id"] == did


def test_full_flow_still_works_for_insiders(svc, did):
    """★ 봉합이 일을 막지 않는다는 증거 — 관계자는 결정까지 그대로 간다."""
    svc.request_review(did, "kim", [{"user_id": "boss", "role": "DECIDER"}],
                       viewer_scopes=INSIDER)
    svc.participant_response(did, "boss", "AGREE", viewer_scopes=INSIDER)
    out = svc.decide(did, "boss", "APPROVED", "근거 충분", viewer_scopes=INSIDER)
    assert out["status"] == "DECIDED"


def test_empty_scope_case_is_not_company_wide(svc):
    """⚠️ 범위가 빈 안건은 «전사» 가 아니라 «미지정» 이다 — 작성자·참여자만 본다."""
    c = svc.create(question="q", created_by="kim", simulation_run_id="run_1",
                   baseline_id="snap_1", package=PKG, evidence=EV, scope_id="")
    pid = c["decision_id"]
    assert svc.get(pid, "kim", viewer_scopes=OUTSIDER)["decision_id"] == pid
    with pytest.raises(DecisionNotFound):
        svc.get(pid, OUT, viewer_scopes=OUTSIDER)


# ── ③ 라우트가 범위를 넘기지 않으면 봉합이 무의미해진다 ─────────────────────
def test_every_decision_route_passes_viewer_scopes():
    """★★ `viewer_scopes` 를 안 넘기면 서비스는 **판정을 통째로 끈다**(레거시 계약).
    라우트 한 곳만 빠뜨려도 그 경로가 조용히 다시 열린다."""
    import inspect

    import api.routes.decision_control as dc
    missing = []
    for r in dc.router.routes:
        methods = {m for m in (getattr(r, "methods", set()) or set())
                   if m not in ("HEAD", "OPTIONS")}
        if not methods:
            continue
        try:
            src = inspect.getsource(r.endpoint)
        except Exception:
            continue
        if "decision_case." not in src:
            continue
        # `queue` 는 설계상 **본인 것만** 돌려주므로(SQL 이 user_id 로 조인) 범위가 필요 없다.
        if "decision_case.queue(" in src and "decision_case.get(" not in src:
            continue
        if "_scopes(p)" not in src:
            missing.append(f"{sorted(methods)} {r.path}")
    assert not missing, (
        "의사결정 서비스를 부르면서 열람 범위를 넘기지 않는 라우트 — 판정이 꺼진다:\n  "
        + "\n  ".join(missing))


def test_create_rejects_foreign_scope(monkeypatch):
    """서버 결속 조회에 실제 열람 범위를 넘기고, 범위 밖 실행은 존재도 알리지 않는다."""
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException
    import api.routes.decision_control as dc
    from core.decision_source_binding import DecisionSourceNotFound

    seen = {}

    def reject_foreign(run_id, visible_scopes):
        seen["run_id"] = run_id
        seen["visible_scopes"] = visible_scopes
        raise DecisionSourceNotFound("찾을 수 없습니다")

    monkeypatch.setattr(dc.decision_sources, "resolve", reject_foreign)
    principal = SimpleNamespace(
        user_id="kim",
        scope=SimpleNamespace(
            unrestricted=False,
            readable_dept_ids=frozenset({"quality"}),
            readable_scope_nodes=frozenset({"node_q"}),
        ),
    )
    request = dc.CaseCreate(question="q", package=PKG)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dc.create_case("foreign-run", request, principal))

    assert exc.value.status_code == 404
    assert seen == {
        "run_id": "foreign-run",
        "visible_scopes": frozenset({"quality", "node_q"}),
    }


def test_scopes_helper_never_returns_none():
    """⚠️ `None` 을 돌려주면 서비스가 판정을 끈다. 무제한은 **센티넬**이다."""
    from types import SimpleNamespace

    import api.routes.decision_control as dc
    unrestricted = SimpleNamespace(scope=SimpleNamespace(unrestricted=True))
    assert dc._scopes(unrestricted) is UNRESTRICTED
    limited = SimpleNamespace(scope=SimpleNamespace(
        unrestricted=False, readable_dept_ids=frozenset({"quality"}),
        readable_scope_nodes=frozenset({"node_q"})))
    got = dc._scopes(limited)
    assert got is not None and got == frozenset({"quality", "node_q"})
