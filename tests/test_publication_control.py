"""★★★ [CL-3] 대내외 보고 발간 — **내보낸 것은 되돌릴 수 없다.**

작업서 §10 필수 케이스 8(EXTERNAL 단일 승인 publish 차단, 이중 승인 성공)과
9(publish adapter 실패 시 PUBLISHED 미기록)를 여기서 고정한다.

## 이 파일이 지키는 네 가지

1. **렌더 실패를 발간 준비 완료로 두지 않는다.** 실패했는데 상태가 올라가면 사람은
   "만들어졌다"고 믿고 승인을 누르고, 승인된 것은 내용 없는 문서다.
2. **EXTERNAL 은 두 승인 전에 API 가 막힌다.** 화면 버튼만 막으면 URL 을 아는 사람은 그대로
   게시할 수 있다.
3. **게시 실패를 성공으로 저장하지 않는다.** 아무 데도 안 나간 문서를 "발간했다"고 믿는 것이
   여기서 막으려는 사고다.
4. **정정·회수 후에도 원본과 이력이 남는다.** 원본이 사라지면 그것을 읽고 판단한 사람이 무엇을
   봤는지 아무도 말할 수 없다.
"""
import pytest

from core.collaboration_store import CollaborationStore
from core.decision_ledger import EVENT_TYPES as LEDGER_EVENT_TYPES
from core.decision_ledger import SUBJECT_TYPES as LEDGER_SUBJECT_TYPES
from core.publication import (APPROVED, AUDIENCE_EXTERNAL, AUDIENCE_INTERNAL, CORRECTED, DRAFT,
                              EXTERNAL_REDACT_KEYS, PUBLISHED, RENDERED, REVIEW_EXECUTIVE,
                              REVIEW_LEGAL, REVIEW_REJECTED, REVIEW_REQUESTED, REVIEW_SECURITY,
                              SOURCE_DECISION, WITHDRAWN, Publication, PublicationError,
                              PublicationNotFound, RenderFailed)


class _Ledger:
    """가짜 원장 — 다만 **실제 허용목록을 그대로 검사한다.**

    ⚠️ 2026-08-04 실측에서 이것이 없어 사고가 났다. 가짜 원장이 무엇이든 받아 주는 바람에
      단위 테스트 32건이 전부 통과했는데, 실제 화면에서 첫 발간 초안이 500 으로 죽었다 —
      `decision_ledger` 에 `PUBLICATION_CREATED` 가 등록돼 있지 않았기 때문이다.
      가짜가 진짜보다 관대하면, 테스트는 통과를 증명하는 것이 아니라 **가짜를 증명한다.**"""

    def __init__(self):
        self.events = []

    def append(self, event_type, subject_type="", **kw):
        assert event_type in LEDGER_EVENT_TYPES, (
            f"`core.decision_ledger.EVENT_TYPES` 에 없는 이벤트입니다: {event_type}")
        if subject_type:
            assert subject_type in LEDGER_SUBJECT_TYPES, (
                f"등록되지 않은 subject_type 입니다: {subject_type}")
        self.events.append({"event_type": event_type, "subject_type": subject_type, **kw})
        return {"event_id": f"e{len(self.events)}"}


#: 원천 Decision Package 한 건. 대외 제외 대상(`financial_impact`, `dissent`)을 일부러 넣는다.
SOURCE = {
    "decision_id": "dec_1",
    "question": "2공정 정련로 가동률을 85% 로 올릴 것인가",
    "outcome": "CONDITIONAL",
    "decided_by": "boss",
    "baseline_id": "snap_1",
    "package_version": 1,
    "evidence_hash": "abc123",
    "package": {
        "baseline": "무행동 시 생산량 변화 없음",
        "options": ["A안 85% 상향", "B안 82% 단계 상향"],
        "financial_impact": "연 12억 개선",          # 대외 제외 대상
        "dissent": "정비팀 인력 부족 우려",            # 대외 제외 대상
        "expected_effect": "정련 처리량 8% 증가",
    },
}


@pytest.fixture
def svc(tmp_path):
    return Publication(store=CollaborationStore(db_path=str(tmp_path / "c.db")),
                       ledger=_Ledger(),
                       decision_source=lambda t, i: SOURCE if i == "dec_1" else None)


def _pub(svc, **kw):
    args = dict(title="정련 가동률 상향 보고", created_by="kim", source_type=SOURCE_DECISION,
                source_id="dec_1", scope_id="MNM_BATTERY")
    args.update(kw)
    return svc.create(**args)


# ── 생성 ──────────────────────────────────────────────────────────────────
def test_source_is_required(svc):
    """★★ 원천 없는 발간물은 만들 수 없다 — 숫자의 출처를 되짚을 수 없기 때문이다."""
    with pytest.raises(PublicationError):
        _pub(svc, source_id="")


def test_unknown_audience_is_refused(svc):
    with pytest.raises(PublicationError):
        _pub(svc, audience="EVERYONE")


def test_new_publication_is_draft_and_not_renderable_as_ready(svc):
    """★ 만들기만 한 발간물은 «렌더링» 게이트를 통과하지 못한다."""
    p = _pub(svc)
    assert p["status"] == DRAFT
    assert p["document_version"] == 0
    assert not p["can_publish"]
    assert any(g["code"] == "RENDERED" and not g["passed"] for g in p["gates"])


# ── 렌더 ──────────────────────────────────────────────────────────────────
def test_render_creates_version_and_moves_to_rendered(svc):
    p = svc.render(_pub(svc)["publication_id"], "kim")
    assert p["status"] == RENDERED
    assert p["document_version"] == 1
    assert p["current_version"]["document"]["header"]["question"] == SOURCE["question"]


def test_render_failure_does_not_mark_ready(svc):
    """★★★ 작업서 §9 — **렌더 실패를 발간 준비 완료로 표시하지 않는다.**

    ⚠️ 실패했는데 `RENDERED` 로 올라가면 사람은 «만들어졌다»고 믿고 승인을 누른다. 그리고
      승인된 것은 내용이 없는 문서다."""
    pid = _pub(svc)["publication_id"]

    def boom(_ctx):
        raise RuntimeError("템플릿 엔진 오류")

    with pytest.raises(RenderFailed):
        svc.render(pid, "kim", renderer=boom)
    after = svc.get(pid, "kim")
    assert after["status"] == DRAFT, "실패는 DRAFT 에 머문다"
    assert after["document_version"] == 0
    assert "템플릿 엔진 오류" in after["render_error"]
    assert after["versions"] == []


def test_missing_source_is_render_failure_not_empty_document(svc):
    """★★ 원천이 없으면 **빈 문서를 만들지 않고** 렌더 실패로 둔다."""
    pid = _pub(svc, source_id="dec_gone")["publication_id"]
    with pytest.raises(RenderFailed):
        svc.render(pid, "kim")
    assert svc.get(pid, "kim")["status"] == DRAFT


def test_empty_render_result_is_a_failure(svc):
    """★ 섹션이 하나도 없는 결과는 성공이 아니다."""
    pid = _pub(svc)["publication_id"]
    with pytest.raises(RenderFailed):
        svc.render(pid, "kim", renderer=lambda _c: {"sections": []})


# ── 비식별·제외 ───────────────────────────────────────────────────────────
def test_external_render_excludes_sensitive_sections_with_reasons(svc):
    """★★★ 대외 문서는 민감 항목을 빼되 **무엇을 왜 뺐는지 함께 남긴다**(설계 §8.4).

    ⚠️ 조용히 빼면 다음 사람은 빠진 줄 모르고 그대로 인용한다."""
    pid = _pub(svc, audience=AUDIENCE_EXTERNAL)["publication_id"]
    doc = svc.render(pid, "kim")["current_version"]["document"]
    keys = {s["key"] for s in doc["sections"]}
    assert "financial_impact" not in keys and "dissent" not in keys
    assert "expected_effect" in keys, "제외 대상이 아닌 항목까지 지우지 않는다"
    excluded = {e["key"] for e in doc["redaction"]["excluded"]}
    assert excluded == {"financial_impact", "dissent"}
    assert all(e["reason"] for e in doc["redaction"]["excluded"]), "사유 없는 제외는 없다"


def test_internal_render_keeps_everything(svc):
    """★ 내부 문서는 같은 원본에서 **다르게 렌더링**될 뿐 항목을 잃지 않는다(설계 §8.2-2)."""
    pid = _pub(svc, audience=AUDIENCE_INTERNAL)["publication_id"]
    doc = svc.render(pid, "kim")["current_version"]["document"]
    keys = {s["key"] for s in doc["sections"]}
    assert set(EXTERNAL_REDACT_KEYS) & keys, "내부 문서에는 손익·반대의견이 남는다"
    assert doc["redaction"]["excluded"] == []


def test_external_document_does_not_name_the_decider(svc):
    """★ 대외 문서에 개인 이름을 싣지 않는다."""
    pid = _pub(svc, audience=AUDIENCE_EXTERNAL)["publication_id"]
    doc = svc.render(pid, "kim")["current_version"]["document"]
    assert "boss" not in doc["header"]["decided_by"]


# ── 승인 게이트 ───────────────────────────────────────────────────────────
def test_external_review_request_always_includes_both_gates(svc):
    """★★ 요청자가 법무 검토를 빼는 것을 허용하지 않는다 — 뺄 수 있으면 바쁜 날에 빠진다."""
    pid = _pub(svc, audience=AUDIENCE_EXTERNAL)["publication_id"]
    svc.render(pid, "kim")
    p = svc.request_approval(pid, "kim", [REVIEW_SECURITY])
    types = {r["review_type"] for r in p["reviews"]}
    assert {REVIEW_EXECUTIVE, REVIEW_LEGAL} <= types


def test_cannot_request_approval_before_render(svc):
    pid = _pub(svc)["publication_id"]
    with pytest.raises(PublicationError):
        svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])


def test_rejection_requires_a_reason(svc):
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])
    with pytest.raises(PublicationError):
        svc.approve(pid, "boss", REVIEW_EXECUTIVE, REVIEW_REJECTED, comment="")


def test_rejection_blocks_publish(svc):
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])
    p = svc.approve(pid, "boss", REVIEW_EXECUTIVE, REVIEW_REJECTED, comment="수치 근거 부족")
    assert p["status"] != APPROVED
    assert any("반려" in b["label"] or "REJECTED" in b["code"] for b in p["blockers"])


def test_re_render_invalidates_previous_approvals(svc):
    """★★ 다시 렌더되면 이전 승인은 무효다 — 승인자가 본 문서가 아니기 때문이다.

    (검토가 **아직 다 끝나지 않은** 상태에서 문서를 고치는 경우다. 전부 승인돼 `APPROVED` 가
    된 뒤에는 렌더 자체가 막힌다 — `test_approved_document_cannot_be_re_rendered`.)"""
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE, REVIEW_SECURITY])
    p = svc.approve(pid, "boss", REVIEW_EXECUTIVE)
    assert p["status"] == REVIEW_REQUESTED, "하나만 승인됐으므로 아직 승인 완료가 아니다"
    p = svc.render(pid, "kim")
    assert p["reviews"] == [], "승인 기록이 남아 있으면 새 문서가 옛 승인으로 나간다"
    assert p["status"] == RENDERED


def test_approved_document_cannot_be_re_rendered(svc):
    """★ 승인된 문서를 다시 렌더하지 않는다 — 승인자가 본 문서와 발간될 문서가 달라진다."""
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])
    svc.approve(pid, "boss", REVIEW_EXECUTIVE)
    with pytest.raises(PublicationError):
        svc.render(pid, "kim")


# ── §10-8 EXTERNAL 이중 승인 ──────────────────────────────────────────────
def test_external_single_approval_cannot_publish(svc):
    """★★★ 작업서 §10-8 — **EXTERNAL 단일 승인 publish 차단.**

    ⚠️ 화면 버튼이 아니라 여기가 경계다. URL 을 아는 사람이 그대로 게시할 수 있으면 게이트는
      존재하지 않는 것과 같다."""
    pid = _pub(svc, audience=AUDIENCE_EXTERNAL)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [])
    p = svc.approve(pid, "boss", REVIEW_EXECUTIVE)          # 임원 승인만
    assert p["status"] != APPROVED
    assert not p["can_publish"]
    with pytest.raises(PublicationError) as e:
        svc.publish(pid, "kim", [{"target": "ir@example.com", "channel": "EMAIL"}],
                    adapter=lambda _p, _t: "ok")
    assert REVIEW_LEGAL in str(e.value)


def test_external_double_approval_publishes(svc):
    """★★★ 작업서 §10-8 — 두 승인이 모두 있으면 발간된다."""
    pid = _pub(svc, audience=AUDIENCE_EXTERNAL)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [])
    svc.approve(pid, "boss", REVIEW_EXECUTIVE)
    p = svc.approve(pid, "legal", REVIEW_LEGAL)
    assert p["status"] == APPROVED and p["can_publish"]
    published = svc.publish(pid, "kim", [{"target": "ir@example.com", "channel": "EMAIL"}],
                            adapter=lambda _p, _t: "EXT-1")
    assert published["status"] == PUBLISHED
    assert published["distributions"][0]["external_ref"] == "EXT-1"


def test_internal_approval_does_not_open_external_publish(svc):
    """★★★ INTERNAL 승인 하나로 EXTERNAL 을 내보낼 수 없다(작업서 §CL-BE-04)."""
    pid = _pub(svc, audience=AUDIENCE_EXTERNAL)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_SECURITY])
    svc.approve(pid, "sec", REVIEW_SECURITY)
    p = svc.get(pid, "kim")
    assert not p["can_publish"]
    codes = {b["code"] for b in p["blockers"]}
    assert f"REVIEW_{REVIEW_EXECUTIVE}" in codes and f"REVIEW_{REVIEW_LEGAL}" in codes


# ── §10-9 게시 실패 ───────────────────────────────────────────────────────
def test_adapter_failure_does_not_record_published(svc):
    """★★★ 작업서 §10-9 — **publish adapter 실패 시 PUBLISHED 미기록.**

    ⚠️ 아무 데도 안 나간 문서를 «발간됨»으로 두면, 다음 사람은 이미 나갔다고 믿고 후속 조치를
      한다."""
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])
    svc.approve(pid, "boss", REVIEW_EXECUTIVE)

    def boom(_p, _t):
        raise ConnectionError("게시 서버 응답 없음")

    p = svc.publish(pid, "kim", [{"target": "portal", "channel": "WEB"}], adapter=boom)
    assert p["status"] == APPROVED, "실패했는데 PUBLISHED 로 올라가면 안 된다"
    assert p["published_at"] == ""
    d = p["distributions"][0]
    assert d["status"] == "FAILED" and "게시 서버 응답 없음" in d["error"]
    assert "배포 실패" in (p.get("note") or "")


def test_missing_adapter_is_recorded_as_failure(svc):
    """★★ 어댑터가 없으면 «성공한 척»하지 않는다 — 실패로 기록한다."""
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])
    svc.approve(pid, "boss", REVIEW_EXECUTIVE)
    p = svc.publish(pid, "kim", [{"target": "portal", "channel": "WEB"}])
    assert p["status"] == APPROVED
    assert p["distributions"][0]["status"] == "FAILED"


def test_partial_failure_does_not_publish(svc):
    """★★ 두 대상 중 하나만 나갔으면 발간이 아니다 — 부분 성공을 성공으로 뭉개지 않는다."""
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])
    svc.approve(pid, "boss", REVIEW_EXECUTIVE)

    def flaky(_p, t):
        if t["target"] == "bad":
            raise RuntimeError("거부")
        return "ok"

    p = svc.publish(pid, "kim", [{"target": "good"}, {"target": "bad"}], adapter=flaky)
    assert p["status"] == APPROVED
    assert {d["status"] for d in p["distributions"]} == {"PUBLISHED", "FAILED"}


def test_publish_before_approval_is_refused(svc):
    pid = _pub(svc)["publication_id"]
    svc.render(pid, "kim")
    with pytest.raises(PublicationError):
        svc.publish(pid, "kim", [{"target": "portal"}], adapter=lambda _p, _t: "ok")


# ── 정정·회수 ─────────────────────────────────────────────────────────────
def _published(svc, **kw):
    pid = _pub(svc, **kw)["publication_id"]
    svc.render(pid, "kim")
    svc.request_approval(pid, "kim", [REVIEW_EXECUTIVE])
    svc.approve(pid, "boss", REVIEW_EXECUTIVE)
    svc.publish(pid, "kim", [{"target": "portal"}], adapter=lambda _p, _t: "ok")
    return pid


def test_correction_creates_new_publication_and_keeps_original(svc):
    """★★★ 설계 §8.2-6 — 발간 후 원천이 바뀌어도 **덮어쓰지 않는다.** 정정판은 새 버전이다."""
    pid = _published(svc)
    new = svc.correct(pid, "kim", "가동률 수치 오기")
    assert new["publication_id"] != pid
    assert new["supersedes_id"] == pid
    original = svc.get(pid, "kim")
    assert original["status"] == CORRECTED
    assert original["versions"], "원본 버전은 남는다"


def test_correction_requires_a_reason(svc):
    pid = _published(svc)
    with pytest.raises(PublicationError):
        svc.correct(pid, "kim", "")


def test_cannot_correct_before_publish(svc):
    pid = _pub(svc)["publication_id"]
    with pytest.raises(PublicationError):
        svc.correct(pid, "kim", "아직 안 나갔다")


def test_withdraw_keeps_history(svc):
    """★★ 회수는 «없던 일»이 아니다 — 배포 이력과 버전은 그대로 남는다."""
    pid = _published(svc)
    p = svc.withdraw(pid, "kim", "원천 데이터 오류 확인")
    assert p["status"] == WITHDRAWN
    assert p["withdrawn_reason"] == "원천 데이터 오류 확인"
    assert p["distributions"], "배포 이력은 지워지지 않는다"
    assert p["versions"], "버전은 지워지지 않는다"


def test_withdraw_requires_a_reason(svc):
    pid = _published(svc)
    with pytest.raises(PublicationError):
        svc.withdraw(pid, "kim", "")


def test_withdraw_is_idempotent(svc):
    pid = _published(svc)
    svc.withdraw(pid, "kim", "오류")
    assert svc.withdraw(pid, "kim", "오류")["status"] == WITHDRAWN


def test_ledger_failure_leaves_no_orphan_row(svc):
    """★★★ 원장 기록이 실패하면 **발간물 행이 남지 않는다.**

    ⚠️ 2026-08-04 실측 사고: `PUBLICATION_CREATED` 가 원장 허용목록에 없어 500 이 났는데,
      INSERT 는 이미 끝난 뒤였다. 원장에 없는 발간물이 DB 에 남았고, 그 순간 "모든 발간
      이벤트를 원장에 기록한다"는 규칙은 사실이 아니게 된다. 없는 편이 낫다."""
    class _Broken:
        def append(self, *a, **k):
            raise RuntimeError("원장 거부")

    svc._ledger_override = _Broken()
    with pytest.raises(RuntimeError):
        _pub(svc)
    svc._ledger_override = _Ledger()
    assert svc.list() == [], "원장에 없는 발간물이 DB 에 남으면 안 된다"


# ── 조회 ──────────────────────────────────────────────────────────────────
def test_unknown_publication_is_not_found(svc):
    with pytest.raises(PublicationNotFound):
        svc.get("pub_nope", "kim")


def test_list_filters_by_audience_and_status(svc):
    _pub(svc, audience=AUDIENCE_INTERNAL)
    _pub(svc, audience=AUDIENCE_EXTERNAL)
    assert len(svc.list()) == 2
    assert len(svc.list(audience=AUDIENCE_EXTERNAL)) == 1
    assert len(svc.list(status=DRAFT)) == 2
    assert len(svc.list(status=PUBLISHED)) == 0


def test_ledger_records_every_stage(svc):
    """★★ 발간·정정·회수가 원장에 남는다(작업서 §9 완료조건)."""
    pid = _published(svc)
    svc.correct(pid, "kim", "오기")
    svc.withdraw(pid, "kim", "회수")
    events = {e["event_type"] for e in svc._ledger.events}
    assert {"PUBLICATION_CREATED", "PUBLICATION_RENDERED", "PUBLICATION_REVIEW_REQUESTED",
            "PUBLICATION_APPROVED", "PUBLICATION_PUBLISHED", "PUBLICATION_CORRECTED",
            "PUBLICATION_WITHDRAWN"} <= events
