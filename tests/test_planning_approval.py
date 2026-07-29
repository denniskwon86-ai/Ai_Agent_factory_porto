"""[M4] 계획 제출·승인 — **승인이 실제로 무언가를 의미하는가.**

승인을 상태 플래그로만 두면 흔한 사고가 난다: 3월에 승인받은 계획의 숫자가 5월에 바뀌어
있는데 상태는 여전히 `APPROVED` 다. 아무도 거짓말하지 않았고 오류도 없었지만, 그 계획서는
이미 **승인받지 않은 문서**다.

이 파일이 잠그는 것은 그 한 가지다 — **승인 시점의 값을 지문으로 박아 두면 속일 수 없다.**
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import planning_approval as ap
from core.planning_model import ACTUAL, PLAN, PlanningError, PlanningStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = PlanningStore(db_path=str(tmp_path / "planning.db"))
    monkeypatch.setattr("core.planning_model.planning_store", s)
    monkeypatch.setattr(ap, "planning_store", s)
    s.upsert_account("4000", "매출", "REVENUE", sign=1)
    s.upsert_account("5000", "원가", "COGS", sign=-1)
    s.put_fact("MNM_BATTERY", "4000", "2027", PLAN, 1000.0)
    s.put_fact("MNM_BATTERY", "5000", "2027", PLAN, 600.0)
    return s


# ── 제출 ─────────────────────────────────────────────────────────────────────
def test_empty_plan_cannot_be_submitted(store):
    """★ 빈 계획을 승인하면 '승인된 계획이 있다'는 사실만 남고 내용은 없다."""
    with pytest.raises(PlanningError, match="제출할 값이 없습니다"):
        ap.submit("EMPTY_ORG", "2027", "alice")


def test_anonymous_submit_is_refused(store):
    with pytest.raises(PlanningError, match="제출자 식별"):
        ap.submit("MNM_BATTERY", "2027", "")


def test_new_submission_supersedes_old(store):
    """제출이 여러 건 살아 있으면 **무엇이 현재 계획인지** 알 수 없다."""
    first = ap.submit("MNM_BATTERY", "2027", "alice")
    second = ap.submit("MNM_BATTERY", "2027", "alice")
    rows = {s["submission_id"]: s for s in ap.list_submissions("MNM_BATTERY", "2027")}
    assert rows[first["submission_id"]]["status"] == ap.DRAFT
    assert rows[second["submission_id"]]["status"] == ap.SUBMITTED


# ── 승인 ─────────────────────────────────────────────────────────────────────
def test_anonymous_approval_is_refused(store):
    """★★ 익명 승인은 **아무도 승인하지 않은 것을 승인된 것으로** 만든다."""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    with pytest.raises(PlanningError, match="승인자 식별"):
        ap.approve(s["submission_id"], "")


def test_self_approval_is_blocked_by_default(store):
    """제출자와 승인자가 같으면 통제가 아니라 형식이다."""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    with pytest.raises(PlanningError, match="자기 승인"):
        ap.approve(s["submission_id"], "alice")


def test_self_approval_can_be_opted_in_and_is_audited(store, tmp_path, monkeypatch):
    """1인 부서·시범 운영을 위해 열 수 있되, **그 사실이 감사에 남는다**."""
    from core.enterprise_context import audit
    monkeypatch.setattr(audit, "_LOG_PATH", str(tmp_path / "audit.jsonl"))

    s = ap.submit("MNM_BATTERY", "2027", "alice")
    ap.approve(s["submission_id"], "alice", allow_self_approval=True)
    e = audit.recent(1)[0]
    assert e["event"] == audit.APPROVAL_GRANTED and e["reason"] == "self_approval"


def test_approval_records_the_fingerprint(store):
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    out = ap.approve(s["submission_id"], "bob")
    assert out["status"] == ap.APPROVED
    assert out["approved_fingerprint"], "승인 시점 지문이 비어 있으면 무결성을 판정할 수 없다"


def test_double_approval_is_refused(store):
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    ap.approve(s["submission_id"], "bob")
    with pytest.raises(PlanningError, match="제출 상태가 아닙니다"):
        ap.approve(s["submission_id"], "bob")


# ── 반려 ─────────────────────────────────────────────────────────────────────
def test_rejection_requires_a_reason(store):
    """★ 사유 없는 반려는 제출자가 **무엇을 고쳐야 할지 모른다.**"""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    with pytest.raises(PlanningError, match="반려 사유"):
        ap.reject(s["submission_id"], "bob", "")


def test_rejection_keeps_the_reason(store):
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    out = ap.reject(s["submission_id"], "bob", "원가 가정 근거 부족")
    assert out["status"] == ap.REJECTED and out["reject_reason"] == "원가 가정 근거 부족"


# ── ★★ 이 파일의 본론: 승인 후 값이 바뀌면 잡아낸다 ─────────────────────────
def test_silent_change_after_approval_is_detected(store):
    """★★ 상태는 `APPROVED` 그대로인데 값만 바뀐 상황 — **가장 위험한 사고**다.

    아무 오류도 나지 않고 아무도 거짓말하지 않았지만, 그 계획서는 승인받지 않은 문서다."""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    ap.approve(s["submission_id"], "bob")
    assert ap.verify_integrity(s["submission_id"])["intact"] is True

    store.put_fact("MNM_BATTERY", "4000", "2027", PLAN, 1500.0)   # 승인 후 조용히 변경

    v = ap.verify_integrity(s["submission_id"])
    assert v["intact"] is False
    assert v["status"] == ap.APPROVED, "상태는 그대로다 — 그래서 지문이 필요하다"
    assert "재승인" in v["message"]


def test_unrelated_kind_change_does_not_break_integrity(store):
    """★ 실적(ACTUAL)이 입력됐다고 **계획 승인이 깨지면 안 된다** — 지문은 종류별로 계산된다."""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    ap.approve(s["submission_id"], "bob")
    store.put_fact("MNM_BATTERY", "4000", "2027", ACTUAL, 900.0)
    assert ap.verify_integrity(s["submission_id"])["intact"] is True


def test_unverifiable_is_not_ok(store):
    """★ 승인되지 않은 제출은 '이상 없음'이 아니라 **'확인 불가'** 다(둘은 다르다)."""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    v = ap.verify_integrity(s["submission_id"])
    assert v["verifiable"] is False and "확인 불가" in v["note"]


def test_current_approved_includes_integrity(store):
    """'승인됐다'만으로는 부족하다 — **'승인받은 그 값 그대로인가'** 가 실제 질문이다."""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    ap.approve(s["submission_id"], "bob")
    cur = ap.current_approved("MNM_BATTERY", "2027")
    assert cur["integrity"]["intact"] is True

    store.put_fact("MNM_BATTERY", "5000", "2027", PLAN, 700.0)
    assert ap.current_approved("MNM_BATTERY", "2027")["integrity"]["intact"] is False


def test_fingerprint_is_order_independent(store):
    """조회 순서가 달라졌을 뿐인데 다른 지문이 나오면 **거짓 불일치**가 된다."""
    f1 = ap.fingerprint("MNM_BATTERY", "2027")
    store.put_fact("MNM_BATTERY", "4000", "2027", PLAN, 1000.0)   # 같은 값 재기록
    assert ap.fingerprint("MNM_BATTERY", "2027") == f1


# ── API 계약 ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def client(store, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    import api.routes.planning_control as pc

    monkeypatch.setattr(pc.approval, "planning_store", store)
    monkeypatch.setattr(pc, "planning_store", store)
    return TestClient(main.app)


@pytest.mark.parametrize("path", [
    "/api/v1/planning/submissions",
    "/api/v1/planning/submissions/current?org_id=X&period=2027",
])
def test_submission_routes_are_reachable(client, path):
    """`/submissions/current` 가 `/submissions/{id}` 에 잡아먹히지 않는지도 함께 본다."""
    assert client.get(path).status_code != 404, f"{path} 미도달"


def test_api_refuses_anonymous_approval(client, store, monkeypatch):
    """★★ 익명 승인은 아무도 승인하지 않은 것을 승인된 것으로 만든다."""
    import config
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    saved = getattr(config, "ORG_DEFAULT_USER_ID", "")
    config.ORG_DEFAULT_USER_ID = ""
    try:
        r = client.post(f"/api/v1/planning/submissions/{s['submission_id']}/approve", json={})
        assert r.status_code == 401 and "익명" in r.json()["detail"]
    finally:
        config.ORG_DEFAULT_USER_ID = saved


def test_api_integrity_endpoint_reports_silent_change(client, store):
    """★★ 승인 후 값이 바뀌면 API 가 그 사실을 말한다 — 상태만 보면 알 수 없다."""
    s = ap.submit("MNM_BATTERY", "2027", "alice")
    ap.approve(s["submission_id"], "bob")
    store.put_fact("MNM_BATTERY", "4000", "2027", PLAN, 9999.0)

    d = client.get(f"/api/v1/planning/submissions/{s['submission_id']}/integrity").json()["data"]
    assert d["intact"] is False and d["status"] == ap.APPROVED


def test_api_current_returns_null_when_none(client):
    """없으면 빈 객체로 위장하지 않고 null 이다 — '승인본이 있다'로 오독되면 안 된다."""
    d = client.get("/api/v1/planning/submissions/current?org_id=NOBODY&period=2027").json()
    assert d["data"] is None
