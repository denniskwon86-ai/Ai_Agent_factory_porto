"""★★★ [CL-2] Decision Package — **세 관점은 같은 문서의 다른 렌더링이다.**

작업서 §10 필수 케이스 6·7 을 여기서 고정한다.

## 왜 하나의 Package 인가

세 검토서를 각각 독립 생성하면 **숫자·가정·권고안이 달라진다.** 그리고 그 세 문서는 같은 회의에
올라간다 — 참석자들은 서로 다른 숫자를 보면서 같은 안건을 논의하고, 결정이 끝난 뒤에는 어느
숫자가 근거였는지 아무도 말할 수 없다.

## 결정을 막는 것들

⚠️ 가장 무거운 것은 **근거 변경**이다. 검토를 요청한 뒤 원천이 바뀌었을 때 숫자를 조용히
  갱신하면, 참석자가 읽은 문서와 결정된 문서가 달라진다 — 회의록이 거짓이 된다는 뜻이다.
  그래서 자동 갱신하지 않고 `EVIDENCE_CHANGED` 로 세우고 사람이 다시 보게 만든다.
"""
import pytest

from core.collaboration_store import CollaborationStore
from core.decision_ledger import EVENT_TYPES as LEDGER_EVENT_TYPES
from core.decision_ledger import SUBJECT_TYPES as LEDGER_SUBJECT_TYPES
from core.decision_case import (ACTIONED, DECIDED, DRAFT, EFFECT_MEASURED, EVIDENCE_CHANGED,
                                IN_REVIEW, MEETING_REQUESTED, OUTCOME_APPROVED,
                                OUTCOME_CONDITIONAL, RESPONSE_AGREE, RESPONSE_NEED_INFO,
                                REVIEW_REQUESTED, ROLE_AFFECTED, ROLE_DECIDER, VIEWS,
                                DecisionCase, DecisionCaseError, DecisionNotFound,
                                evidence_hash)

PKG = {
    "baseline": {"연간원가": 1000},
    "options": [{"name": "증설", "cost": 300}, {"name": "무행동", "cost": 0}],
    "executive_brief": "제3공장 증설 여부",
    "financial_impact": {"npv": 120},
}
EV = {"simulation": {"run_id": "res_1", "verified": True},
      "baseline_snapshot": {"id": "snap_1", "verified": True}}


class _Ledger:
    """가짜 원장 — **실제 허용목록을 그대로 검사한다.**

    ⚠️ 가짜가 진짜보다 관대하면 테스트는 통과가 아니라 가짜를 증명한다(CL-3 에서 실제로
      그 사고가 났다: 미등록 이벤트를 가짜가 받아 주어 32건이 전부 통과했고, 화면에서 500 이
      났다)."""

    def __init__(self):
        self.events = []

    def append(self, event_type, subject_type, subject_id, **kw):
        assert event_type in LEDGER_EVENT_TYPES, (
            f"`core.decision_ledger.EVENT_TYPES` 에 없는 이벤트입니다: {event_type}")
        assert subject_type in LEDGER_SUBJECT_TYPES, (
            f"등록되지 않은 subject_type 입니다: {subject_type}")
        self.events.append({"event": event_type, "subject_type": subject_type,
                            "subject_id": subject_id, **kw})
        return {"event_id": f"dle_{len(self.events)}"}


@pytest.fixture
def svc(tmp_path):
    return DecisionCase(store=CollaborationStore(db_path=str(tmp_path / "c.db")),
                        ledger=_Ledger())


def _case(svc, **kw):
    args = dict(question="제3공장을 증설할까요?", created_by="kim", simulation_run_id="run_1",
                baseline_id="snap_1", package=PKG, evidence=EV, scope_id="MNM_BATTERY")
    args.update(kw)
    return svc.create(**args)


def _reviewed(svc, decider="boss", affected=("logi",)):
    c = _case(svc)
    parts = [{"user_id": decider, "role": ROLE_DECIDER}]
    parts += [{"user_id": a, "role": ROLE_AFFECTED} for a in affected]
    svc.request_review(c["decision_id"], "kim", parts)
    return c["decision_id"]


# ── 생성 ──────────────────────────────────────────────────────────────────
def test_question_is_required(svc):
    """★★ 무엇을 승인·기각하는지 한 문장으로 없으면 참석자는 무엇을 결정하는지 모른다."""
    with pytest.raises(DecisionCaseError, match="결정 문장"):
        _case(svc, question="  ")


def test_baseline_and_options_are_required(svc):
    """★★★ 기준선과 대안이 없으면 비교할 것이 없고, 결정은 '하자/말자'만 남는다(도메인 §7.2)."""
    with pytest.raises(DecisionCaseError, match="기준선과 대안"):
        _case(svc, package={"executive_brief": "요약만 있음"})


def test_requester_is_registered_as_participant(svc):
    """★ 올린 사람이 참여자 목록에 없으면 누가 올렸는지 화면에서 사라진다."""
    c = _case(svc)
    assert [p["role"] for p in c["participants"]] == ["REQUESTER"]
    assert c["status"] == DRAFT


def test_main_queue_excludes_validation_cases_but_keeps_business(svc):
    """카나리도 같은 저장소에 보존하지만 경영 홈의 업무 대기열에는 섞지 않는다."""
    business = _case(svc, question="공급 지연 대응안을 승인할까요?")
    validation = _case(svc, question="[카나리] 알림 격리 확인용 안건",
                       simulation_run_id="canary_run", baseline_id="BL-CANARY",
                       record_purpose="VALIDATION")

    visible = svc.queue("kim")
    assert [row["decision_id"] for row in visible] == [business["decision_id"]]
    all_rows = svc.queue("kim", include_validation=True)
    assert {row["decision_id"] for row in all_rows} == {
        business["decision_id"], validation["decision_id"]}


def test_legacy_canary_binding_is_classified_without_title_matching(svc):
    """기존 오염은 제목 문구가 아니라 실행 ID와 기준선의 결속으로 분류한다."""
    legacy = _case(svc, question="문구가 바뀐 검증 안건",
                   simulation_run_id="test_mega_01", baseline_id="BL-CL4")
    # create 직후에는 기본 BUSINESS지만 다음 제품 조회의 멱등 마이그레이션이 재분류한다.
    svc._store.execute("UPDATE decision_cases SET record_purpose='BUSINESS' WHERE decision_id=?",
                       (legacy["decision_id"],))
    svc._store._ready = ""
    assert svc.queue("kim") == []
    assert svc.queue("kim", include_validation=True)[0]["record_purpose"] == "VALIDATION"


def test_evidence_hash_is_order_independent(svc):
    """★★ 키 순서가 달라도 같은 근거는 같은 지문이다 — 아니면 "바뀌었다"는 판정이 거짓이 된다."""
    assert evidence_hash({"a": 1, "b": 2}) == evidence_hash({"b": 2, "a": 1})


# ── 세 관점 (§10-6) ───────────────────────────────────────────────────────
def test_three_views_share_package_and_evidence_hash(svc):
    """★★★ **이 파일의 핵심.** 세 관점이 같은 `package_version`·`evidence_hash` 를 들고 나간다.

    다르면 참석자들이 서로 다른 숫자를 보면서 같은 안건을 논의하게 되고, 결정 후에는 어느
    숫자가 근거였는지 아무도 말할 수 없다."""
    c = _case(svc)
    views = [svc.render_view(c["decision_id"], v, "kim") for v in VIEWS]
    assert len({v["package_version"] for v in views}) == 1
    assert len({v["evidence_hash"] for v in views}) == 1
    assert len({v["decision_id"] for v in views}) == 1
    assert all(v["evidence_hash"] == c["evidence_hash"] for v in views)


def test_views_are_projections_not_copies(svc):
    """★★ 관점마다 **다른 섹션**을 보여주되 원본은 하나다 — 저장 테이블이 늘어나지 않는다."""
    c = _case(svc)
    req = svc.render_view(c["decision_id"], "requester", "kim")
    dec = svc.render_view(c["decision_id"], "decider", "kim")
    aff = svc.render_view(c["decision_id"], "affected", "kim")
    assert {s["key"] for s in req["sections"]} != {s["key"] for s in dec["sections"]}
    assert "decision_form" in dec and "decision_form" not in req
    assert "response_form" in aff
    # 원본 테이블은 하나 — 검토서용 별도 표가 없다(§3-5)
    tables = [r["name"] for r in svc._store.query(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    assert not any("review" in t or "views" in t for t in tables), tables


def test_missing_sections_are_shown_as_missing(svc):
    """★★★ 빈 섹션을 숨기면 검토자는 그 항목이 **검토됐다고 믿는다.**"""
    c = _case(svc)
    dec = svc.render_view(c["decision_id"], "decider", "kim")
    sens = next(s for s in dec["sections"] if s["key"] == "sensitivity")
    assert sens["missing"] is True, "채우지 않은 섹션이 숨겨졌다"
    brief = next(s for s in dec["sections"] if s["key"] == "executive_brief")
    assert brief["missing"] is False


def test_unknown_view_is_refused(svc):
    c = _case(svc)
    with pytest.raises(DecisionCaseError, match="view"):
        svc.render_view(c["decision_id"], "cfo", "kim")


# ── 검토 요청 ─────────────────────────────────────────────────────────────
def test_review_requires_a_decider(svc):
    """★★★ 결정자 없는 안건은 회의만 만들고 아무것도 끝내지 못한다."""
    c = _case(svc)
    with pytest.raises(DecisionCaseError, match="결정자"):
        svc.request_review(c["decision_id"], "kim",
                           [{"user_id": "logi", "role": ROLE_AFFECTED}])


def test_bad_role_is_refused(svc):
    """★★ 역할을 하나의 enum 으로 뭉개지 않는다 — 섞으면 "누가 결정했는가"에 답할 수 없다."""
    c = _case(svc)
    with pytest.raises(DecisionCaseError, match="role"):
        svc.request_review(c["decision_id"], "kim", [{"user_id": "x", "role": "REVIEWER"}])


def test_review_moves_to_requested_then_in_review(svc):
    """★ 요청만 하고 응답이 없는 상태와 검토가 시작된 상태를 구분한다."""
    did = _reviewed(svc)
    assert svc.get(did, "kim")["status"] == REVIEW_REQUESTED
    svc.participant_response(did, "logi", RESPONSE_AGREE)
    assert svc.get(did, "kim")["status"] == IN_REVIEW


def test_non_participant_response_is_hidden(svc):
    """★★★ 남의 안건에 의견을 남길 수 없고, **존재도 알리지 않는다**(404)."""
    did = _reviewed(svc)
    with pytest.raises(DecisionNotFound):
        svc.participant_response(did, "stranger", RESPONSE_AGREE)


def test_dissent_requires_content(svc):
    """★★ 이유 없는 반대는 결정자가 판단에 쓸 수 없다."""
    did = _reviewed(svc)
    with pytest.raises(DecisionCaseError, match="내용이 필요"):
        svc.participant_response(did, "logi", "DISAGREE", "")


# ── 회의 (§3-7) ───────────────────────────────────────────────────────────
def test_meeting_is_request_only_and_says_so(svc):
    """★★★ 외부 캘린더·메시지에 **사용자 확인 없이 쓰지 않는다.**

    시스템이 먼저 만들면 사용자가 모르는 초대가 나가고, 그것은 되돌릴 수 없다."""
    did = _reviewed(svc)
    out = svc.request_meeting(did, "kim", "증설 검토 회의", schedule="2026-08-10 14:00")
    assert out["status"] == MEETING_REQUESTED
    assert "외부 캘린더" in out["note"]
    m = out["meetings"][0]
    assert m["external_created"] is False and m["external_ref"] == ""
    # 안건 스냅샷이 고정된다 — 회의 시점에 무엇을 보고 있었는지 남는다
    assert m["agenda"]["evidence_hash"] == out["evidence_hash"]


def test_meeting_after_decision_is_refused(svc):
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "타당함")
    with pytest.raises(DecisionCaseError, match="회의를 요청할 수 없"):
        svc.request_meeting(did, "kim", "사후 회의")


# ── 결정 차단 (§10-7) ─────────────────────────────────────────────────────
def test_only_decider_can_decide(svc):
    """★★★ 결정자가 아니면 **404** 다 — 결정 권한이 없다는 사실조차 알려주지 않는다."""
    did = _reviewed(svc)
    with pytest.raises(DecisionNotFound):
        svc.decide(did, "logi", OUTCOME_APPROVED, "근거")


def test_cannot_decide_before_review(svc):
    """★★ 검토 요청 전 결정은 막는다 — 아무도 보지 않은 안건이 승인된다."""
    c = _case(svc)
    svc.request_review(c["decision_id"], "kim", [{"user_id": "boss", "role": ROLE_DECIDER}])
    svc._store.execute("UPDATE decision_cases SET status='DRAFT' WHERE decision_id=?",
                       (c["decision_id"],))
    with pytest.raises(DecisionCaseError, match="검토 요청 후"):
        svc.decide(c["decision_id"], "boss", OUTCOME_APPROVED, "근거")


def test_missing_baseline_blocks_decision(svc):
    """★★★ 기준선이 없으면 **무엇과 비교해 결정하는지** 알 수 없다."""
    c = _case(svc, baseline_id="")
    svc.request_review(c["decision_id"], "kim", [{"user_id": "boss", "role": ROLE_DECIDER}])
    d = svc.get(c["decision_id"], "boss")
    assert any(b["code"] == "NO_BASELINE" for b in d["blockers"])
    assert d["can_decide"] is False
    with pytest.raises(DecisionCaseError, match="막는 조건"):
        svc.decide(c["decision_id"], "boss", OUTCOME_APPROVED, "근거")


def test_unverified_evidence_blocks_decision(svc):
    """★★★ 검증되지 않은 핵심 근거로 결정하면, 그 결정의 근거는 추측이다."""
    c = _case(svc, evidence={"simulation": {"run_id": "r", "verified": False}})
    svc.request_review(c["decision_id"], "kim", [{"user_id": "boss", "role": ROLE_DECIDER}])
    d = svc.get(c["decision_id"], "boss")
    assert any(b["code"] == "UNVERIFIED_EVIDENCE" for b in d["blockers"])


def test_participant_needing_info_blocks_decision(svc):
    """★★ '정보 부족'을 답한 참여자가 있으면 결정을 막는다 — 그 답은 무시할 수 있는 것이 아니다."""
    did = _reviewed(svc)
    svc.participant_response(did, "logi", RESPONSE_NEED_INFO, "재고 데이터가 없습니다")
    d = svc.get(did, "boss")
    assert any(b["code"] == "PARTICIPANT_NEEDS_INFO" for b in d["blockers"])


def test_need_info_blocker_lists_each_person_once(svc):
    """★★ 한 사람이 두 역할을 겸해도 차단 사유에 이름이 한 번만 나온다.

    ⚠️ 2026-08-04 화면 실측에서 `['hikwon@lsmnm.com', 'hikwon@lsmnm.com']` 로 찍혔다.
      한 사람이 요청자이자 결정자인 안건은 흔하고, `participant_response` 는 그 사용자의 모든
      역할 행을 함께 갱신한다(한 사람의 의견은 하나다). 중복을 그대로 두면 읽는 사람은 두 명이
      정보 부족을 답한 것으로 오해한다 — 차단 사유는 **누가 몇 명인지**가 정보다."""
    c = _case(svc, created_by="kim")
    did = c["decision_id"]
    # kim 은 이미 요청자다. 여기서 결정자까지 겸한다.
    svc.request_review(did, "kim", [{"user_id": "kim", "role": ROLE_DECIDER}])
    svc.participant_response(did, "kim", RESPONSE_NEED_INFO, "정비 인력 소요를 모릅니다")
    d = svc.get(did, "kim")
    assert len([p for p in d["participants"] if p["user_id"] == "kim"]) == 2, "역할 두 개는 유지된다"
    blocker = next(b for b in d["blockers"] if b["code"] == "PARTICIPANT_NEEDS_INFO")
    assert blocker["reason"].count("kim") == 1


def test_evidence_change_blocks_and_does_not_auto_update(svc):
    """★★★ **가장 무거운 계약.** 근거가 바뀌면 숫자를 자동 갱신하지 않고 다시 보게 만든다.

    조용히 갱신하면 참석자가 읽은 문서와 결정된 문서가 달라진다 — 회의록이 거짓이 된다."""
    did = _reviewed(svc)
    before = svc.get(did, "boss")
    svc.refresh_evidence(did, {"simulation": {"run_id": "res_2", "verified": True}}, "system")
    after = svc.get(did, "boss")
    assert after["status"] == EVIDENCE_CHANGED
    assert after["package_version"] == before["package_version"] + 1
    assert any(b["code"] == "EVIDENCE_CHANGED" for b in after["blockers"])
    with pytest.raises(DecisionCaseError, match="막는 조건"):
        svc.decide(did, "boss", OUTCOME_APPROVED, "근거")


def test_evidence_hash_mismatch_is_detected(svc):
    """★★★ 저장소를 직접 고친 경우(스크립트 수정)도 잡는다 — 재현할 수 없는 근거다."""
    did = _reviewed(svc)
    svc._store.execute("UPDATE decision_cases SET evidence_json=? WHERE decision_id=?",
                       ('{"simulation": {"run_id": "hacked"}}', did))
    d = svc.get(did, "boss")
    assert any(b["code"] == "EVIDENCE_HASH_MISMATCH" for b in d["blockers"])


def test_decided_case_evidence_cannot_change(svc):
    """★★★ 이미 결정된 안건의 근거를 바꾸면 **그 결정을 설명할 수 없다.**"""
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "타당함")
    with pytest.raises(DecisionCaseError, match="이미 결정된"):
        svc.refresh_evidence(did, {"x": 1}, "system")


# ── 결정 기록 ─────────────────────────────────────────────────────────────
def test_decision_requires_rationale(svc):
    did = _reviewed(svc)
    with pytest.raises(DecisionCaseError, match="근거"):
        svc.decide(did, "boss", OUTCOME_APPROVED, "  ")


def test_conditional_requires_conditions(svc):
    """★★★ 조건 없는 조건부는 **그냥 승인**이고, 실행 단계에서 아무도 조건을 확인하지 않는다."""
    did = _reviewed(svc)
    with pytest.raises(DecisionCaseError, match="조건이 필요"):
        svc.decide(did, "boss", OUTCOME_CONDITIONAL, "일부 타당", conditions="")
    out = svc.decide(did, "boss", OUTCOME_CONDITIONAL, "일부 타당",
                     conditions="8월 재고 실사 완료 후 착수")
    assert out["outcome"] == OUTCOME_CONDITIONAL and "재고 실사" in out["outcome_conditions"]


def test_decision_is_recorded_in_the_ledger(svc):
    """★★ 결정은 운영 표에서 덮어쓰이지만 원장에는 남는다."""
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "NPV 120억 · 회수 3년")
    ev = [e for e in svc._ledger.events if e["event"] == "DECISION_RECORDED"][0]
    assert ev["actor_id"] == "boss" and "NPV" in ev["rationale"]
    assert ev["subject_type"] == "decision_case"


# ── 실행과제 ──────────────────────────────────────────────────────────────
def test_actions_require_owner_and_due(svc):
    """★★★ 담당 없는 과제는 아무도 하지 않고, 기한 없는 과제는 언제 늦었는지 알 수 없다 —
    결정이 실행으로 이어지지 않는 가장 흔한 경로다."""
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "타당")
    with pytest.raises(DecisionCaseError, match="담당"):
        svc.create_actions(did, "kim", [{"action": "설비 발주", "due_at": "2026-09-01"}])
    with pytest.raises(DecisionCaseError, match="기한"):
        svc.create_actions(did, "kim", [{"action": "설비 발주", "owner_user_id": "logi"}])


def test_actions_before_decision_are_refused(svc):
    did = _reviewed(svc)
    with pytest.raises(DecisionCaseError, match="결정 후"):
        svc.create_actions(did, "kim", [{"action": "x", "owner_user_id": "y",
                                        "due_at": "2026-09-01"}])


def test_actions_created_and_state_moves(svc):
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "타당")
    out = svc.create_actions(did, "kim", [
        {"action": "설비 발주", "owner_user_id": "logi", "due_at": "2026-09-01",
         "owner_scope_id": "logistics"}])
    assert out["status"] == ACTIONED and len(out["actions"]) == 1
    assert out["actions"][0]["status"] == "OPEN"


# ── 효과 측정 ─────────────────────────────────────────────────────────────
def test_unmeasured_is_not_zero(svc):
    """★★★ **미측정을 0 으로 저장하지 않는다.**

    0 은 "효과가 없었다"이고 미측정은 "아직 모른다"다. 두 개를 같게 표시하면 실패한 결정과
    측정하지 않은 결정이 같은 색으로 보인다."""
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "타당")
    out = svc.create_actions(did, "kim", [{"action": "발주", "owner_user_id": "logi",
                                          "due_at": "2026-09-01"}])
    aid = out["actions"][0]["action_id"]
    assert out["actions"][0]["measured_effect"] == "", "미측정은 빈 값이어야 한다"
    with pytest.raises(DecisionCaseError, match="미측정으로"):
        svc.measure_effect(did, "kim", aid, "   ")


def test_effect_is_measured_against_the_decision_baseline(svc):
    """★★ 결정 **당시** 기준선과 비교한다 — 나중에 기준선이 바뀌어도 그때 기준으로 남는다."""
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "타당")
    out = svc.create_actions(did, "kim", [{"action": "발주", "owner_user_id": "logi",
                                          "due_at": "2026-09-01"}])
    aid = out["actions"][0]["action_id"]
    fin = svc.measure_effect(did, "kim", aid, "원가 -4.2% (기준 1000 → 958)")
    assert fin["status"] == EFFECT_MEASURED
    ev = [e for e in svc._ledger.events if e["event"] == "DECISION_EFFECT_MEASURED"][0]
    assert "snap_1" in ev["rationale"], "결정 당시 기준선이 기록에 없다"


def test_measure_on_other_case_action_is_hidden(svc):
    """★★ 다른 안건의 과제에 효과를 기록할 수 없다(404)."""
    did = _reviewed(svc)
    svc.decide(did, "boss", OUTCOME_APPROVED, "타당")
    svc.create_actions(did, "kim", [{"action": "a", "owner_user_id": "u", "due_at": "2026-09-01"}])
    other = _reviewed(svc, decider="boss2")
    with pytest.raises(DecisionNotFound):
        svc.measure_effect(other, "kim", "act_nope", "효과")


# ── 목록 ──────────────────────────────────────────────────────────────────
def test_queue_shows_only_my_cases(svc):
    """★★★ 내가 참여자가 아닌 안건은 목록에 없다."""
    _reviewed(svc, decider="boss", affected=("logi",))
    assert [c["my_role"] for c in svc.queue("boss")] == [ROLE_DECIDER]
    assert svc.queue("stranger") == []


def test_overdue_is_flagged(svc):
    """★ 마감이 지난 안건은 표시된다 — 조용히 지나가면 아무도 결정하지 않는다."""
    c = _case(svc, due_at="2026-01-01")
    d = svc.get(c["decision_id"], "kim", today="2026-08-03")
    assert d["overdue"] is True
