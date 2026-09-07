"""[DAO-11] 정기 갱신 — **자동 적용 관문이 실제로 막는가**.

이 파일이 지키는 것 다섯.

  ① 프로세스 안에 타이머가 **없다**(지시 9).
  ② 스케줄러는 `ACTIVE` 이고 시각이 된 것만 본다.
  ③ **자동 적용은 기본 꺼짐**이고, 켜는 것 자체가 원장에 남는 결정이다.
  ④ 켜져 있어도 **모양이 다르면** 막고 사람에게 넘긴다 — 특히 원천이 새 필드를 냈을 때.
  ⑤ 한 작업이 실패해도 바퀴가 멈추지 않는다.
"""
import json
import os

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence import providers as P
from core.external_intelligence import refresh_runner as RR
from core.external_intelligence.acquisition_store import (AcquisitionStore,
                                                          AcquisitionStoreError)
from core.external_intelligence.orchestrator import AcquisitionOrchestrator
from core.external_intelligence.providers import ecos as E  # noqa: F401
from core.external_intelligence.raw_store import RawStore

ECOS_KEY = "ecoskey0123456789abcdefghij"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "ecos")
REQUESTER = "t_member_a@test.invalid"
APPROVER = "t_dataadmin@test.invalid"
PAST = "2026-01-01T00:00:00+00:00"
NOW = "2026-09-05T00:00:00+00:00"


def _transport(search="search_fx_2025.json", extra_field=None):
    def call(url, *, allowed_hosts, timeout=20.0):
        name = "item_list_fx.json" if "StatisticItemList" in url else search
        with open(os.path.join(FIX, name), "rb") as f:
            body = f.read()
        if extra_field and "StatisticSearch" in url:
            #: 원천이 예고 없이 열을 추가한 상황을 만든다.
            data = json.loads(body.decode("utf-8"))
            for row in data["StatisticSearch"]["row"]:
                row[extra_field] = "새로 생긴 값"
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return {"body": body, "content_type": "application/json", "status": 200,
                "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}
    return call


@pytest.fixture()
def rig(tmp_path):
    store = AcquisitionStore(str(tmp_path / "ei.db"),
                             ledger=DecisionLedger(str(tmp_path / "ledger.db")))
    raw = RawStore(str(tmp_path / "raw"))

    def orchestrator(search="search_fx_2025.json", extra_field=None):
        return AcquisitionOrchestrator(store=store, raw_store=raw,
                                       registry=P.provider_registry,
                                       env={"AFS_ECOS_API_KEY": ECOS_KEY},
                                       transport=_transport(search, extra_field))

    return {"store": store, "raw": raw, "orchestrator": orchestrator}


def _active_job(rig, *, auto_apply=False, next_run_at=PAST):
    """요청부터 ACTIVE 까지 한 번 완주시키고 일정을 건다."""
    store = rig["store"]
    if not store.approved_contract("EXT-01"):
        proposal = store.propose_contract(M.ext01_public_proposal(), proposed_by=REQUESTER)
        store.decide_contract(proposal["proposal_id"], approve=True, reviewed_by=APPROVER,
                              reason="공표 통계용")
    orch = rig["orchestrator"]()
    job = store.create(tenant_id="tenant_default", requested_by=REQUESTER,
                       subject_name="LS MnM", purpose="환율 가정",
                       request={"subject_name": "LS MnM", "purpose": "환율 가정",
                                "period_from": "2025", "period_to": "2025",
                                "indicators": ["환율"],
                                "extras": {"provider_ids": ["ECOS"]}})
    job = orch.discover(job["job_id"], actor_id=REQUESTER)
    job, _ = orch.dry_run(job["job_id"], actor_id=REQUESTER)
    job, _ = orch.apply(job["job_id"], actor_id=APPROVER)
    return store.set_schedule(job["job_id"], schedule_rule="daily",
                              next_run_at=next_run_at, auto_apply=auto_apply,
                              actor_id=APPROVER)


# ── ① 타이머가 없다 ─────────────────────────────────────────────────────────
def test_no_in_process_timer_anywhere():
    """★★★ 프로세스 안에 타이머를 두면 웹 서버가 4개 뜰 때 같은 수집이 4번 돈다."""
    import inspect
    for module_path in ("core/external_intelligence/refresh_runner.py",
                        "scripts/run_acquisition_refresh.py"):
        with open(module_path, encoding="utf-8") as f:
            source = f.read()
        for banned in ("time.sleep", "threading.Timer", "asyncio.sleep",
                       "schedule.every", "while True"):
            assert banned not in source, f"{module_path} 에 {banned} 가 있다"


def test_run_once_really_runs_once(rig):
    """이름대로 한 바퀴만 돈다 — 두 번 부르면 두 바퀴다."""
    _active_job(rig, auto_apply=True)
    orch = rig["orchestrator"]()
    first = RR.run_once(orch, now=NOW)
    second = RR.run_once(orch, now=NOW)
    assert first.considered == 1 and second.considered == 1
    #: 두 번째는 새로 넣을 것이 없다(중복).
    assert first.inserted == 0        # 이미 apply 에서 6행이 들어갔다
    assert second.inserted == 0


# ── ② ACTIVE 이고 시각이 된 것만 ────────────────────────────────────────────
def test_only_due_active_jobs_are_considered(rig):
    _active_job(rig, next_run_at="2099-01-01T00:00:00+00:00")
    report = RR.run_once(rig["orchestrator"](), now=NOW)
    assert report.considered == 0
    assert report.outcomes == ()


def test_a_job_without_a_schedule_is_never_picked_up(rig):
    store = rig["store"]
    job = _active_job(rig, next_run_at="")
    assert job["next_run_at"] == ""
    assert RR.run_once(rig["orchestrator"](), now="2099-01-01T00:00:00+00:00").considered == 0


def test_a_disabled_job_is_skipped(rig):
    store = rig["store"]
    job = _active_job(rig, auto_apply=True)
    store.transition(job["job_id"], am.DISABLED, actor_id=APPROVER, reason="사람이 껐다")
    assert RR.run_once(rig["orchestrator"](), now=NOW).considered == 0


# ── ③ 자동 적용은 기본 꺼짐이고 켜는 것이 결정이다 ──────────────────────────
def test_auto_apply_defaults_to_off(rig):
    job = _active_job(rig)
    assert job["auto_apply"] is False


def test_turning_auto_apply_on_needs_an_actor(rig):
    store = rig["store"]
    job = _active_job(rig)
    with pytest.raises(AcquisitionStoreError) as exc:
        store.set_schedule(job["job_id"], schedule_rule="daily", next_run_at=PAST,
                           auto_apply=True, actor_id="")
    assert "누가 켰는지" in str(exc.value)


def test_turning_auto_apply_on_lands_in_the_ledger(rig):
    """★ 「사람 없이 들어온 자료」의 책임자가 원장에 있어야 한다."""
    store = rig["store"]
    job = _active_job(rig, auto_apply=True)
    decisions = [e["decision"] for e in store.history(job["job_id"])]
    assert "자동 적용 켬" in decisions


def test_turning_auto_apply_off_is_also_recorded(rig):
    """끄는 것도 결정이다 — 「언제부터 안 돌았지?」에 답해야 한다."""
    store = rig["store"]
    job = _active_job(rig, auto_apply=True)
    store.set_schedule(job["job_id"], schedule_rule="daily", next_run_at=PAST,
                       auto_apply=False, actor_id=APPROVER)
    decisions = [e["decision"] for e in store.history(job["job_id"])]
    assert "자동 적용 끔" in decisions


def test_setting_the_same_value_twice_does_not_spam_the_ledger(rig):
    store = rig["store"]
    job = _active_job(rig, auto_apply=True)
    store.set_schedule(job["job_id"], schedule_rule="daily", next_run_at=PAST,
                       auto_apply=True, actor_id=APPROVER)
    decisions = [e["decision"] for e in store.history(job["job_id"])]
    assert decisions.count("자동 적용 켬") == 1


def test_auto_apply_off_leaves_the_job_for_a_person(rig):
    """★★★ 꺼져 있으면 새 자료를 받아 두고 **검토 대기**에 둔다 — 적용하지 않는다."""
    _active_job(rig, auto_apply=False)
    report = RR.run_once(rig["orchestrator"](), now=NOW)
    outcome = report.outcomes[0]
    assert outcome.applied is False
    assert outcome.status == am.REVIEW_REQUIRED
    assert outcome.blocked == RR.BLOCK_AUTO_APPLY_OFF
    assert report.awaiting_review == 1


def test_auto_apply_on_with_the_same_shape_applies(rig):
    _active_job(rig, auto_apply=True)
    report = RR.run_once(rig["orchestrator"](), now=NOW)
    outcome = report.outcomes[0]
    assert outcome.applied is True
    assert outcome.status == am.ACTIVE
    assert outcome.blocked == ""
    assert report.applied == 1


# ── ④ 모양이 다르면 막는다 ──────────────────────────────────────────────────
def test_new_fields_from_the_source_block_auto_apply(rig):
    """★★★ 원천은 예고 없이 열을 추가한다.

    ⚠️⚠️ 이 시험이 **관문이 장식임을 잡았다.** 처음엔 정규화된 행을 계약과 대조했는데,
      명시적 변환기가 새 열을 애초에 버리므로 원천이 바뀌어도 아무 차이가 없었다.
      지금은 **원문의 필드 구성**을 마지막 적용 때와 비교한다."""
    _active_job(rig, auto_apply=True)
    report = RR.run_once(rig["orchestrator"](extra_field="NEW_COLUMN"), now=NOW)
    outcome = report.outcomes[0]
    assert outcome.applied is False
    assert outcome.blocked == RR.BLOCK_NEW_FIELDS
    assert "NEW_COLUMN" in outcome.blocked_detail
    assert outcome.status == am.REVIEW_REQUIRED


def test_the_drift_guard_compares_source_fields_not_normalized_rows():
    """★★★ 비교 대상이 무엇인지 못 박는다 — 정규화 결과를 보면 영원히 통과한다."""
    import inspect
    source = inspect.getsource(RR.auto_apply_gate)
    assert "batch.source_fields" in source
    assert "batch.rows" not in source.split("⑥")[-1]


def test_source_fields_are_recorded_at_apply_time(rig):
    """기준이 없으면 비교할 것이 없다 — 적용이 그때의 구성을 남긴다."""
    job = _active_job(rig, auto_apply=True)
    recorded = (job.get("checkpoint") or {}).get("source_fields") or []
    assert "DATA_VALUE" in recorded and "TIME" in recorded


def test_a_removed_source_field_also_blocks(rig):
    """열이 사라지는 것도 변경이다 — 우리가 쓰던 열일 수 있다."""
    _active_job(rig, auto_apply=True)
    #: `WGT` 를 지운 응답을 만든다.
    import json as _json
    import os as _os

    def transport(url, *, allowed_hosts, timeout=20.0):
        name = "item_list_fx.json" if "StatisticItemList" in url else "search_fx_2025.json"
        with open(_os.path.join(FIX, name), "rb") as f:
            body = f.read()
        if "StatisticSearch" in url:
            data = _json.loads(body.decode("utf-8"))
            for row in data["StatisticSearch"]["row"]:
                row.pop("WGT", None)
            body = _json.dumps(data, ensure_ascii=False).encode("utf-8")
        return {"body": body, "content_type": "application/json", "status": 200,
                "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}

    orch = AcquisitionOrchestrator(store=rig["store"], raw_store=rig["raw"],
                                   registry=P.provider_registry,
                                   env={"AFS_ECOS_API_KEY": ECOS_KEY}, transport=transport)
    report = RR.run_once(orch, now=NOW)
    outcome = report.outcomes[0]
    assert outcome.blocked == RR.BLOCK_NEW_FIELDS
    assert "사라짐" in outcome.blocked_detail


def test_an_unapproved_contract_blocks_auto_apply(rig):
    """사람이 계약 승인을 되돌렸을 수 있다."""
    import sqlite3
    store = rig["store"]
    _active_job(rig, auto_apply=True)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE data_contract_proposals SET status='REJECTED' "
                     "WHERE contract_key='EXT-01'")
    report = RR.run_once(rig["orchestrator"](), now=NOW)
    assert report.outcomes[0].blocked == RR.BLOCK_CONTRACT_NOT_APPROVED
    assert report.outcomes[0].applied is False


def test_quality_failure_blocks_and_quarantines(rig):
    """단위가 섞인 응답 — 사람이 봐야 한다."""
    _active_job(rig, auto_apply=True)
    report = RR.run_once(rig["orchestrator"]("search_fx_dirty.json"), now=NOW)
    outcome = report.outcomes[0]
    assert outcome.applied is False
    assert outcome.status == am.QUARANTINED
    assert report.failed == 1


def test_no_data_is_not_a_failure(rig):
    """★ 재시도해도 같다 — 실패로 세면 스케줄러가 알림을 잘못 건다."""
    _active_job(rig, auto_apply=True)
    report = RR.run_once(rig["orchestrator"]("result_no_data.json"), now=NOW)
    outcome = report.outcomes[0]
    assert outcome.status == am.NO_DATA
    assert report.no_data == 1 and report.failed == 0


def test_transport_failure_is_counted_as_failed(rig):
    _active_job(rig, auto_apply=True)
    report = RR.run_once(rig["orchestrator"]("result_traffic.json"), now=NOW)
    assert report.outcomes[0].status == am.FAILED
    assert report.failed == 1


def test_block_reasons_are_a_closed_list():
    """화면이 문구를 지어내지 않게 — 코드마다 사람이 읽을 문장이 있다."""
    codes = {RR.BLOCK_AUTO_APPLY_OFF, RR.BLOCK_SHAPE_CHANGED,
             RR.BLOCK_CONTRACT_NOT_APPROVED, RR.BLOCK_ORIGIN_MISMATCH,
             RR.BLOCK_QUALITY, RR.BLOCK_NEW_FIELDS}
    assert set(RR.BLOCK_REASONS) == codes
    assert all(RR.BLOCK_REASONS[c] for c in codes)


def test_the_gate_uses_the_same_origin_judge_as_apply():
    """★★★ 판정이 두 곳에 있으면 갈린다 — 관문과 적용이 같은 함수를 쓴다."""
    import inspect
    source = inspect.getsource(RR.auto_apply_gate)
    assert "assert_origin_fits" in source


# ── ⑤ 한 작업의 실패가 바퀴를 멈추지 않는다 ─────────────────────────────────
def test_one_failing_job_does_not_stop_the_others(rig, monkeypatch):
    """환율이 안 받아졌다고 물가까지 멈추면 안 된다."""
    store = rig["store"]
    first = _active_job(rig, auto_apply=True)
    second = _active_job(rig, auto_apply=True)
    assert first["job_id"] != second["job_id"]

    orch = rig["orchestrator"]()
    original = orch.dry_run
    calls = {"n": 0}

    def flaky(job_id, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("첫 작업에서 예상 못 한 오류")
        return original(job_id, **kwargs)

    monkeypatch.setattr(orch, "dry_run", flaky)
    report = RR.run_once(orch, now=NOW)
    assert report.considered == 2
    assert len(report.outcomes) == 2
    assert any(o.error for o in report.outcomes)
    assert any(o.applied for o in report.outcomes)


def test_run_once_never_raises(rig, monkeypatch):
    orch = rig["orchestrator"]()
    _active_job(rig, auto_apply=True)
    monkeypatch.setattr(orch, "dry_run",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("터짐")))
    report = RR.run_once(orch, now=NOW)          # 던지지 않는다
    assert report.outcomes[0].error


# ── 보고서 ──────────────────────────────────────────────────────────────────
def test_report_counts_are_consistent(rig):
    _active_job(rig, auto_apply=True)
    report = RR.run_once(rig["orchestrator"](), now=NOW)
    d = report.as_dict()
    assert d["considered"] == len(d["outcomes"])
    assert d["applied"] + d["awaiting_review"] + d["failed"] + d["no_data"] <= d["considered"]
    assert report.summary_line().startswith("수집 갱신")


def test_blocked_outcomes_carry_a_readable_reason(rig):
    _active_job(rig, auto_apply=False)
    report = RR.run_once(rig["orchestrator"](), now=NOW)
    entry = report.as_dict()["outcomes"][0]
    assert entry["blocked"] == RR.BLOCK_AUTO_APPLY_OFF
    assert entry["blocked_reason"]           # 사람이 읽을 문장이 함께 온다


# ── 스크립트 ────────────────────────────────────────────────────────────────
def test_script_dry_mode_changes_nothing(rig, monkeypatch, capsys):
    """`--dry` 는 목록만 읽는다 — 아무것도 바꾸지 않는다."""
    import scripts.run_acquisition_refresh as script
    store = rig["store"]
    _active_job(rig, auto_apply=True)
    before = store.staged_count()
    monkeypatch.setattr(
        "core.external_intelligence.acquisition_store.acquisition_store", store)
    code = script.main(["--dry", "--now", NOW, "--json"])
    assert code == 0
    assert store.staged_count() == before
    payload = json.loads(capsys.readouterr().out)
    assert payload["considered"] == 1
    assert payload["jobs"][0]["auto_apply"] is True


def test_script_exit_code_separates_failure_from_no_data():
    """★ 「자료 없음」으로 알림이 울리면 사람이 곧 알림을 끈다."""
    import inspect
    import scripts.run_acquisition_refresh as script
    source = inspect.getsource(script.main)
    assert "return 2 if report.failed else 0" in source


def test_script_skips_when_another_run_holds_the_lock(tmp_path, monkeypatch, capsys):
    """겹침은 오류가 아니다 — 다음 주기에 다시 온다."""
    import scripts.run_acquisition_refresh as script
    monkeypatch.setattr(script, "_lock_path", lambda: str(tmp_path / "lock"))
    held = script._acquire_lock()
    assert held is not None
    try:
        assert script.main(["--now", NOW]) == 0
        assert "건너뜁니다" in capsys.readouterr().out
    finally:
        script._release_lock(held)


def test_lock_is_released_after_a_normal_run(tmp_path, monkeypatch):
    import scripts.run_acquisition_refresh as script
    monkeypatch.setattr(script, "_lock_path", lambda: str(tmp_path / "lock"))
    fd = script._acquire_lock()
    script._release_lock(fd)
    assert not os.path.exists(str(tmp_path / "lock"))
    assert script._acquire_lock() is not None      # 다시 잡을 수 있다
