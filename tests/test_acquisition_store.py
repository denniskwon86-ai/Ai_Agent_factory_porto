"""[DAO-4] 수집 작업 저장소 — 두 층이 **각각** 도는지 본다.

★★★ 이 파일의 핵심은 「막혔다」가 아니라 **「어느 층이 막았나」** 다. 응용층이 먼저 잡으면
  DB 층은 한 번도 불리지 않고, 그 상태로 몇 달이 지나면 DB 층이 실제로는 없는데 있다고
  믿게 된다(「변이 0건은 앞선 관문 탓일 수 있다」).

  그래서 DB 층을 시험할 때는 **응용층을 일부러 통과시킨다** — 낡은 스냅샷을 쥐여 주거나
  SQL 을 직접 넣는다.
"""
import json
import sqlite3

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence.acquisition_store import (LEDGER_EVENT_BY_STATE,
                                                          LEDGER_SUBJECT_TYPE,
                                                          AcquisitionStore,
                                                          AcquisitionStoreError)

ACTOR = "hikwon@lsmnm.com"


@pytest.fixture()
def store(tmp_path):
    ledger = DecisionLedger(str(tmp_path / "ledger.db"))
    return AcquisitionStore(str(tmp_path / "ei.db"), ledger=ledger)


def _job(store, **over):
    base = dict(tenant_id="tenant_default", requested_by=ACTOR,
                request={"subject": "LS MnM", "years": "2016-2025"},
                subject_name="LS MnM", purpose="원료구매·손익 시뮬레이션")
    base.update(over)
    return store.create(**base)


def _walk(store, job, *targets, actor_id=ACTOR):
    for t in targets:
        job = store.transition(job["job_id"], t, actor_id=actor_id,
                               reason="시험" if t in (am.FAILED, am.NO_DATA, am.QUARANTINED,
                                                    am.DISABLED) else "")
    return job


# ── 만들기 ───────────────────────────────────────────────────────────────────
def test_new_job_always_starts_at_draft(store):
    """호출부가 시작 상태를 정하게 두면 「탐색도 안 했는데 계획 완료」가 만들어진다."""
    job = _job(store)
    assert job["status"] == am.DRAFT
    assert job["job_id"].startswith("daq_")
    assert job["request"]["subject"] == "LS MnM"
    assert job["is_schedulable"] is False


def test_job_requires_a_requester(store):
    """누가 요청했는지 없는 수집은 없다 — 나중에 「누가 이걸 켰지?」에 답해야 한다."""
    with pytest.raises(AcquisitionStoreError):
        _job(store, requested_by="")
    with pytest.raises(AcquisitionStoreError):
        _job(store, tenant_id="")


# ── 응용층 ───────────────────────────────────────────────────────────────────
def test_full_walk_reaches_active(store):
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED, am.APPLYING, am.ACTIVE)
    assert job["status"] == am.ACTIVE
    assert job["is_schedulable"] is True
    assert job["awaits_human"] is False


def test_human_gate_cannot_be_skipped(store):
    """★★★ dry-run 에서 곧바로 운영으로 가는 길이 한 줄이라도 있으면 언젠가 그 줄로 간다."""
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN)
    with pytest.raises(am.AcquisitionStateError):
        store.transition(job["job_id"], am.ACTIVE, actor_id=ACTOR)
    assert store.get(job["job_id"])["status"] == am.DRY_RUN


def test_review_required_marks_the_job_as_awaiting_a_person(store):
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED)
    assert job["awaits_human"] is True
    assert job["is_schedulable"] is False


def test_terminal_states_require_a_reason(store):
    """사유가 없으면 「왜 이렇게 됐지?」에 답할 수 없고, 그러면 아무도 되돌리지 못한다."""
    job = _walk(store, _job(store), am.DISCOVERING)
    for target in (am.FAILED, am.NO_DATA, am.DISABLED):
        with pytest.raises(AcquisitionStoreError) as exc:
            store.transition(job["job_id"], target, actor_id=ACTOR, reason="  ")
        assert "사유" in str(exc.value)


def test_failure_kind_must_agree_with_the_destination(store):
    """⚠️ 어긋나면 「품질 문제인데 재시도 대상」이 된다 — 재시도해도 영원히 같다."""
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN)
    with pytest.raises(AcquisitionStoreError) as exc:
        store.transition(job["job_id"], am.FAILED, actor_id=ACTOR, reason="단위 불일치",
                         failure_kind=am.FAILURE_QUALITY)
    assert am.QUARANTINED in str(exc.value)
    ok = store.transition(job["job_id"], am.QUARANTINED, actor_id=ACTOR,
                          reason="단위 불일치", failure_kind=am.FAILURE_QUALITY)
    assert ok["failure_kind"] == am.FAILURE_QUALITY


def test_unknown_failure_kind_is_refused(store):
    job = _walk(store, _job(store), am.DISCOVERING)
    with pytest.raises(am.AcquisitionStateError):
        store.transition(job["job_id"], am.FAILED, actor_id=ACTOR, reason="x",
                         failure_kind="WHATEVER")


# ── ★★★ DB 층이 실제로 도는가 ──────────────────────────────────────────────
def test_db_check_constraint_refuses_a_status_outside_the_list(store, tmp_path):
    """응용층을 **완전히 건너뛰고** SQL 로 직접 넣어 본다.

    ⚠️ 이 시험이 없으면 「CHECK 를 적었다」와 「CHECK 가 막는다」를 구분할 수 없다."""
    job = _job(store)
    with sqlite3.connect(store.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE data_acquisition_jobs SET status='ALMOST_DONE' WHERE job_id=?",
                         (job["job_id"],))


def test_conditional_update_stops_a_second_transition_from_a_stale_read(store, monkeypatch):
    """★★★ 응용층을 **일부러 통과시켜** DB 층만 남긴다.

    두 사람이 같은 `REVIEW_REQUIRED` 화면을 보고 동시에 승인을 누른 상황이다. 응용층은
    둘 다 통과시킨다(둘 다 REVIEW_REQUIRED 를 읽었으니까). 막는 것은 조건부 UPDATE 다."""
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED)
    stale = dict(store.get(job["job_id"]))          # 첫 사람이 읽은 화면
    first = store.transition(job["job_id"], am.APPLYING, actor_id=ACTOR)
    assert first["status"] == am.APPLYING

    #: 두 번째 사람은 아직 낡은 화면을 들고 있다.
    monkeypatch.setattr(store, "get", lambda _id, _s=stale: dict(_s))
    with pytest.raises(AcquisitionStoreError) as exc:
        store.transition(job["job_id"], am.APPLYING, actor_id="someone.else@lsmnm.com")
    assert "그 사이 바뀌었습니다" in str(exc.value)


def test_losing_a_race_does_not_overwrite_the_winner(store, monkeypatch):
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED)
    stale = dict(store.get(job["job_id"]))
    store.transition(job["job_id"], am.APPLYING, actor_id=ACTOR)
    monkeypatch.setattr(store, "get", lambda _id, _s=stale: dict(_s))
    with pytest.raises(AcquisitionStoreError):
        store.transition(job["job_id"], am.DISABLED, actor_id="other", reason="중지")
    monkeypatch.undo()
    assert store.get(job["job_id"])["status"] == am.APPLYING


# ── 원장 ─────────────────────────────────────────────────────────────────────
def test_every_transition_lands_in_the_ledger(store):
    """지시 2 — 「각 전환은 사건 원장에 기록한다」."""
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED, am.APPLYING, am.ACTIVE)
    events = store.history(job["job_id"])
    assert len(events) == 7                       # 생성 + 전이 6
    decisions = [e["decision"] for e in events]
    assert "(신규) → DRAFT" in decisions
    assert "REVIEW_REQUIRED → APPLYING" in decisions
    assert "APPLYING → ACTIVE" in decisions


def test_history_comes_from_the_ledger_not_a_local_copy(store):
    """이력 표를 하나 더 두면 두 이력은 반드시 갈린다."""
    job = _walk(store, _job(store), am.DISCOVERING)
    with sqlite3.connect(store.db_path) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any("transition" in t or "history" in t for t in tables), tables
    assert len(store.history(job["job_id"])) == 2


def test_human_approval_is_a_distinct_ledger_event(store):
    """★ 승인은 찾을 수 있어야 한다 — 기계적 전이와 같은 이름이면 감사에서 안 보인다."""
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED, am.APPLYING)
    kinds = [e["event_type"] for e in store.history(job["job_id"])]
    assert "DATA_ACQUISITION_APPROVED" in kinds
    assert kinds.count("DATA_ACQUISITION_APPROVED") == 1


def test_every_state_has_a_ledger_event_name(store):
    """대응이 빠진 상태로 옮기면 기록 없는 전이가 생긴다."""
    assert set(LEDGER_EVENT_BY_STATE) == set(am.ACQUISITION_STATES)
    from core.decision_ledger import EVENT_TYPES, SUBJECT_TYPES
    for name in LEDGER_EVENT_BY_STATE.values():
        assert name in EVENT_TYPES, name
    assert LEDGER_SUBJECT_TYPE in SUBJECT_TYPES


def test_failure_kind_reaches_the_ledger_rationale(store):
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN)
    store.transition(job["job_id"], am.QUARANTINED, actor_id=ACTOR,
                     reason="원천 합계와 3건 어긋남", failure_kind=am.FAILURE_RECONCILIATION)
    last = store.history(job["job_id"])[0]
    assert am.FAILURE_RECONCILIATION in last["rationale"]
    assert "3건" in last["rationale"]


def test_state_is_not_moved_when_the_ledger_refuses(store, monkeypatch):
    """★★★ 기록 실패를 삼키면 「승인 이력 없는 승인」이 생긴다.

    기록만 남고 상태가 안 바뀌는 쪽이 덜 나쁘다 — 남은 기록은 보이지만 없는 기록은 안 보인다."""
    job = _walk(store, _job(store), am.DISCOVERING)

    class Broken:
        def append(self, **_kw):
            raise RuntimeError("원장 디스크 오류")

        def list_events(self, *_a, **_k):
            return []

    monkeypatch.setattr(store, "_ledger", Broken())
    with pytest.raises(RuntimeError):
        store.transition(job["job_id"], am.PLAN_READY, actor_id=ACTOR)
    monkeypatch.undo()
    assert store.get(job["job_id"])["status"] == am.DISCOVERING


# ── 원문 결속 ────────────────────────────────────────────────────────────────
def test_raw_objects_survive_a_failed_apply(store):
    """지시 8 — 「적용 실패 시 원천 응답과 정상 데이터까지 삭제하지 않는다」."""
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN)
    store.record_raw_object(job["job_id"], {
        "raw_object_ref": "SRC_DART/ab/" + "a" * 64 + ".json", "checksum": "a" * 64,
        "source_id": "SRC_DART", "byte_size": 2633, "fetched_at": "2026-09-05T00:00:00+00:00"})
    store.transition(job["job_id"], am.QUARANTINED, actor_id=ACTOR,
                     reason="대사 실패", failure_kind=am.FAILURE_RECONCILIATION)
    kept = store.raw_objects(job["job_id"])
    assert len(kept) == 1
    assert kept[0]["checksum"] == "a" * 64


def test_recording_the_same_raw_object_twice_is_idempotent(store):
    job = _job(store)
    meta = {"raw_object_ref": "SRC/aa/" + "b" * 64 + ".json", "checksum": "b" * 64,
            "source_id": "SRC"}
    store.record_raw_object(job["job_id"], meta)
    store.record_raw_object(job["job_id"], meta)
    assert len(store.raw_objects(job["job_id"])) == 1


def test_raw_object_needs_both_reference_and_checksum(store):
    job = _job(store)
    with pytest.raises(AcquisitionStoreError):
        store.record_raw_object(job["job_id"], {"raw_object_ref": "x"})
    with pytest.raises(AcquisitionStoreError):
        store.record_raw_object(job["job_id"], {"checksum": "y"})


def test_already_collected_answers_the_duplicate_question(store):
    """중복 적재 방지 — 보관소(파일)와 저장소(DB) 양쪽에서 답할 수 있어야 한다."""
    job = _job(store)
    store.record_raw_object(job["job_id"], {
        "raw_object_ref": "SRC_DART/cc/" + "c" * 64 + ".json", "checksum": "c" * 64,
        "source_id": "SRC_DART"})
    assert store.already_collected("SRC_DART", "c" * 64)["job_id"] == job["job_id"]
    assert store.already_collected("SRC_DART", "d" * 64) is None
    assert store.already_collected("SRC_OTHER", "c" * 64) is None


# ── 스케줄러 ─────────────────────────────────────────────────────────────────
def test_scheduler_sees_only_active_jobs(store):
    """지시 9 — ACTIVE 아닌 작업을 스케줄러가 움직이면 사람 관문이 무력해진다."""
    waiting = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                    am.REVIEW_REQUIRED)
    store.transition(waiting["job_id"], am.APPLYING, actor_id=ACTOR)
    active = store.transition(waiting["job_id"], am.ACTIVE, actor_id=ACTOR,
                              patch={"next_run_at": "2026-09-01T00:00:00+00:00"})
    other = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                  am.REVIEW_REQUIRED)
    assert other["status"] == am.REVIEW_REQUIRED

    due = store.due_for_refresh(now="2026-09-05T00:00:00+00:00")
    assert [j["job_id"] for j in due] == [active["job_id"]]


def test_scheduler_skips_jobs_not_yet_due(store):
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED, am.APPLYING)
    store.transition(job["job_id"], am.ACTIVE, actor_id=ACTOR,
                     patch={"next_run_at": "2026-12-01T00:00:00+00:00"})
    assert store.due_for_refresh(now="2026-09-05T00:00:00+00:00") == []


def test_active_job_without_a_schedule_is_not_picked_up(store):
    """일정 없는 ACTIVE 를 매번 돌리면 「켜 두기만 한」 작업이 계속 남의 서버를 두드린다."""
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED, am.APPLYING, am.ACTIVE)
    assert job["next_run_at"] == ""
    assert store.due_for_refresh(now="2999-01-01T00:00:00+00:00") == []


def test_disabled_job_is_never_scheduled(store):
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY, am.DRY_RUN,
                am.REVIEW_REQUIRED, am.APPLYING)
    store.transition(job["job_id"], am.ACTIVE, actor_id=ACTOR,
                     patch={"next_run_at": "2026-01-01T00:00:00+00:00"})
    store.transition(job["job_id"], am.DISABLED, actor_id=ACTOR, reason="사람이 껐다")
    assert store.due_for_refresh(now="2999-01-01T00:00:00+00:00") == []


# ── 조회 ─────────────────────────────────────────────────────────────────────
def test_list_filters_by_tenant_and_status(store):
    a = _job(store, tenant_id="t_a")
    _job(store, tenant_id="t_b")
    store.transition(a["job_id"], am.DISCOVERING, actor_id=ACTOR)
    assert len(store.list_jobs(tenant_id="t_a")) == 1
    assert len(store.list_jobs(status=am.DRAFT)) == 1
    assert len(store.list_jobs()) == 2


def test_list_refuses_an_unknown_status(store):
    with pytest.raises(AcquisitionStoreError):
        store.list_jobs(status="ALMOST")


def test_json_columns_are_returned_decoded(store):
    job = _walk(store, _job(store), am.DISCOVERING, am.PLAN_READY)
    out = store.transition(job["job_id"], am.DRY_RUN, actor_id=ACTOR,
                           patch={"dry_run": {"expected_rows": 120, "rejected": 3}})
    assert out["dry_run"]["expected_rows"] == 120
    assert "dry_run_json" not in out
