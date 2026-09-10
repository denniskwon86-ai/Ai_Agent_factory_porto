"""[DAO-7] 수집 오케스트레이터 — 요청부터 격리 적재까지 **fixture 로 관통**한다.

이 파일이 지키는 것 여섯.

  ① Dry-run 은 **격리 적재본에 한 줄도 쓰지 않는다**(주석이 아니라 건수로 센다).
  ② 승인되지 않은 계약에는 적재하지 않고, **상태도 옮기지 않는다**.
  ③ 부분 실패를 성공으로 표시하지 않는다.
  ④ 적용이 실패해도 원문과 이미 들어간 행을 **지우지 않는다**.
  ⑤ 같은 요청을 다시 돌려도 **중복 0건**.
  ⑥ 정정공시가 앞의 행을 **덮어쓰지 않는다**.
"""
import json
import os

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence import providers as P
from core.external_intelligence.acquisition_store import AcquisitionStore
from core.external_intelligence.orchestrator import (APPLY_STAGES, PENDING_STAGES,
                                                     AcquisitionOrchestrator,
                                                     OrchestrationError)
from core.external_intelligence.providers import opendart as od  # noqa: F401  (등록)
from core.external_intelligence.raw_store import RawStore

KEY = "dartkey0123456789abcdef01234567"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "opendart")
ACTOR = "hikwon@lsmnm.com"
AS_OF = "2026-12-31"


def _transport(financial="fnltt_2025_cfs_ok.json", corp="corp_code.zip"):
    def call(url, *, allowed_hosts, timeout=20.0):
        name = corp if "corpCode.xml" in url else financial
        ctype = "application/zip" if name.endswith(".zip") else "application/json"
        with open(os.path.join(FIX, name), "rb") as f:
            return {"body": f.read(), "content_type": ctype, "status": 200,
                    "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}
    return call


@pytest.fixture()
def rig(tmp_path):
    ledger = DecisionLedger(str(tmp_path / "ledger.db"))
    store = AcquisitionStore(str(tmp_path / "ei.db"), ledger=ledger)
    raw = RawStore(str(tmp_path / "raw"))

    def make(financial="fnltt_2025_cfs_ok.json", corp="corp_code.zip", env=None):
        return AcquisitionOrchestrator(
            store=store, raw_store=raw, registry=P.provider_registry,
            env={"AFS_OPENDART_API_KEY": KEY} if env is None else env,
            transport=_transport(financial, corp))

    return {"store": store, "raw": raw, "make": make}


def _job(store, **over):
    request = {"subject_name": "LS MnM", "purpose": "원료구매·손익 시뮬레이션",
               "period_from": "2025", "period_to": "2025",
               "extras": {"provider_ids": ["OPENDART"], "fs_div": "CFS",
                          "excluded_providers": [{"provider_id": "ECOS",
                                                  "reason": "회사 단위 재무를 주지 않음"}]}}
    request.update(over.pop("request", {}))
    return store.create(tenant_id="tenant_default", requested_by=ACTOR, subject_name="LS MnM",
                        purpose="원료구매·손익 시뮬레이션", request=request, **over)


def _approve_contract(store):
    proposal = store.propose_contract(M.pub01_proposal(), proposed_by=ACTOR)
    return store.decide_contract(proposal["proposal_id"], approve=True,
                                 reviewed_by="cfo@lsmnm.com", reason="공개 재무 전용 계약")


def _to_review(rig, orch=None, **kw):
    store = rig["store"]
    orch = orch or rig["make"]()
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    job, report = orch.dry_run(job["job_id"], actor_id=ACTOR, as_of=AS_OF, **kw)
    return orch, job, report


# ── 관통 ─────────────────────────────────────────────────────────────────────
def test_full_walk_reaches_active_and_stages_rows(rig):
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    job, report = orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert job["status"] == am.ACTIVE
    assert report.ok is True and report.partial is False
    assert report.inserted == 4
    assert [s.name for s in report.stages] == list(APPLY_STAGES)
    assert store.staged_count("PUB-01") == 4


def test_discover_records_the_chosen_candidate_and_its_reason(rig):
    orch = rig["make"]()
    job = orch.discover(_job(rig["store"])["job_id"], actor_id=ACTOR)
    assert job["status"] == am.PLAN_READY
    assert job["target_contract_key"] == "PUB-01"
    assert job["dataset_ref"] == "00126380:2025:11011:CFS"
    assert "corp_code" in job["plan"]["chosen"]["match_reason"]


# ── ① Dry-run 은 쓰지 않는다 ────────────────────────────────────────────────
def test_dry_run_writes_nothing_to_the_isolated_store(rig):
    """★★★ 「쓰지 않는다」를 주석으로 적는 것과 실제로 안 쓰는 것은 다르다."""
    store = rig["store"]
    before = store.staged_count()
    orch, job, _ = _to_review(rig)
    assert store.staged_count() == before == 0
    assert job["status"] == am.REVIEW_REQUIRED


def test_dry_run_does_preserve_the_raw_response(rig):
    """격리 «수집»은 한다 — 원문이 없으면 나중에 무엇이 왔는지 알 수 없다."""
    store = rig["store"]
    orch, job, report = _to_review(rig)
    kept = store.raw_objects(job["job_id"])
    assert len(kept) == 1
    assert rig["raw"].verify(kept[0]["raw_object_ref"])["ok"] is True


def test_dry_run_report_carries_every_item_the_instruction_lists(rig):
    """지시 7 — 화면은 이 보고서만 보고 그린다."""
    _, _, report = _to_review(rig, mapping_proposal=[
        {"source": "amount", "target": "amount"},
        {"source": "account_id", "target": "account_id"}])
    d = report.as_dict()
    for key in ("chosen_reason", "excluded_sources", "expected_rows", "new_rows",
                "duplicate_rows", "superseded_rows", "rejected_rows", "missing_fields",
                "mapping_needs_human", "mapping_failed", "unit_conversions",
                "target_contract_status", "quarantined", "estimated_bytes",
                "refresh_schedule", "readiness_change_note", "pending_stages"):
        assert key in d, key
    assert d["expected_rows"] == 4
    assert d["excluded_sources"] == [{"provider_id": "ECOS",
                                      "reason": "회사 단위 재무를 주지 않음"}]
    assert d["estimated_bytes"] > 0


def test_dry_run_shows_missing_fields_rather_than_zeros(rig):
    """★★★ 0 으로 채우면 지표가 「값이 0」으로 보이고 결손보다 나쁘다."""
    _, _, report = _to_review(rig)
    assert report.missing_fields.get("amount") == 1


def test_dry_run_lists_what_would_be_quarantined(rig):
    _, _, report = _to_review(rig)
    reasons = [q["reason"] for q in report.quarantined]
    assert "연결/별도 구분 불일치" in reasons


def test_dry_run_says_the_contract_is_not_approved_yet(rig):
    _, _, report = _to_review(rig)
    assert report.target_contract_status == "PROPOSED(미승인)"
    _approve_contract(rig["store"])
    _, _, report2 = _to_review(rig)
    assert report2.target_contract_status == "APPROVED"


def test_dry_run_names_the_stages_it_does_not_do(rig):
    """지시 14 — 「운영 적용」과 「격리 적재」를 섞어 보고하지 않는다."""
    _, _, report = _to_review(rig)
    names = [p["name"] for p in report.pending_stages]
    assert names == [n for n, _ in PENDING_STAGES]
    assert all(p["reason"] for p in report.pending_stages)
    assert "준비도" in report.readiness_change_note


# ── ② 승인 없이는 적재하지 않는다 ───────────────────────────────────────────
def test_apply_refuses_an_unapproved_contract(rig):
    orch, job, _ = _to_review(rig)
    with pytest.raises(OrchestrationError) as exc:
        orch.apply(job["job_id"], actor_id=ACTOR)
    assert "승인" in str(exc.value)


def test_refusing_an_unapproved_contract_does_not_move_the_state(rig):
    """★★★ APPLYING 으로 갔다가 실패하면 「승인했는데 실패한」 기록이 남는다."""
    store = rig["store"]
    orch, job, _ = _to_review(rig)
    with pytest.raises(OrchestrationError):
        orch.apply(job["job_id"], actor_id=ACTOR)
    assert store.get(job["job_id"])["status"] == am.REVIEW_REQUIRED
    kinds = [e["event_type"] for e in store.history(job["job_id"])]
    assert "DATA_ACQUISITION_APPROVED" not in kinds


def test_contract_approval_is_a_human_decision_in_the_ledger(rig):
    store = rig["store"]
    approved = _approve_contract(store)
    assert approved["status"] == "APPROVED"
    assert approved["reviewed_by"] == "cfo@lsmnm.com"
    events = store.ledger().list_events("data_contract", "PUB-01")
    assert events[0]["event_type"] == "DATA_CONTRACT_PUBLISHED"
    assert events[0]["actor_id"] == "cfo@lsmnm.com"


def test_a_second_approval_of_the_same_contract_is_refused(rig):
    from core.external_intelligence.acquisition_store import AcquisitionStoreError
    store = rig["store"]
    _approve_contract(store)
    with pytest.raises(AcquisitionStoreError):
        store.propose_contract(M.pub01_proposal(), proposed_by=ACTOR)


def test_an_already_approved_document_cannot_enter_as_a_proposal(rig):
    """제안 경로로 인증된 계약을 넣으면 「제안」과 「계약」이 섞인다."""
    from core.external_intelligence.acquisition_store import AcquisitionStoreError
    doc = dict(M.pub01_proposal(), status="APPROVED_FOR_DEMO")
    with pytest.raises(AcquisitionStoreError):
        rig["store"].propose_contract(doc, proposed_by=ACTOR)


def test_rejecting_a_contract_needs_a_reason(rig):
    from core.external_intelligence.acquisition_store import AcquisitionStoreError
    store = rig["store"]
    proposal = store.propose_contract(M.pub01_proposal(), proposed_by=ACTOR)
    with pytest.raises(AcquisitionStoreError):
        store.decide_contract(proposal["proposal_id"], approve=False,
                              reviewed_by="cfo@lsmnm.com", reason="")


# ── ③④ 부분 실패 ───────────────────────────────────────────────────────────
def test_quality_failure_never_reaches_active(rig):
    """★★★ 부분 실패를 성공으로 표시하지 않는다(지시 8)."""
    store = rig["store"]
    _approve_contract(store)
    orch = rig["make"]("fnltt_wrong_company.json")
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    job, _ = orch.dry_run(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    #: 품질 관문에서 이미 걸려 격리로 간다 — 사람 검토 자리에 도달하지 않는다.
    assert job["status"] == am.QUARANTINED
    assert job["failure_kind"] == am.FAILURE_QUALITY
    assert store.staged_count() == 0


def test_a_failed_apply_keeps_the_raw_object(rig):
    """지시 8 — 「적용 실패 시 원천 응답과 정상 데이터까지 삭제하지 않는다」."""
    store = rig["store"]
    _approve_contract(store)
    orch = rig["make"]("fnltt_wrong_company.json")
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    job, _ = orch.dry_run(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    kept = store.raw_objects(job["job_id"])
    assert len(kept) == 1
    assert rig["raw"].verify(kept[0]["raw_object_ref"])["ok"] is True


def test_previously_staged_rows_survive_a_later_failure(rig):
    """앞선 작업이 넣은 정상 행은 뒤 작업의 실패로 사라지지 않는다."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert store.staged_count("PUB-01") == 4

    bad = rig["make"]("fnltt_wrong_company.json")
    job2 = bad.discover(_job(store)["job_id"], actor_id=ACTOR)
    bad.dry_run(job2["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert store.staged_count("PUB-01") == 4


def test_apply_report_marks_partial_when_rows_landed_but_a_stage_failed():
    """`partial` 이 「일부만 들어갔다」를 말한다 — 그것은 성공이 아니다."""
    from core.external_intelligence.orchestrator import ApplyReport, StageResult
    report = ApplyReport(job_id="x", inserted=3,
                         stages=(StageResult("A", True), StageResult("B", False, "대사 실패")))
    assert report.ok is False and report.partial is True


# ── 장애와 자료 없음 ─────────────────────────────────────────────────────────
def test_no_data_from_the_source_is_not_a_failure(rig):
    """★★★ 재시도해도 같다 — FAILED 로 접으면 스케줄러가 영원히 두드린다."""
    store = rig["store"]
    orch = rig["make"]("fnltt_no_data.json")
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    with pytest.raises(OrchestrationError):
        orch.dry_run(job["job_id"], actor_id=ACTOR)
    assert store.get(job["job_id"])["status"] == am.NO_DATA


def test_unknown_company_ends_in_no_data_not_failed(rig):
    store = rig["store"]
    orch = rig["make"]()
    job = _job(store, request={"subject_name": "없는회사"})
    out = orch.discover(job["job_id"], actor_id=ACTOR)
    assert out["status"] == am.NO_DATA
    assert "자료가 없습니다" in out["status_reason"]


def test_bad_credentials_fail_with_the_auth_kind(rig):
    """★★★ Provider 가 판정한 실패 종류를 오케스트레이터가 **덮어쓰지 않는다.**

    ⚠️ 실측으로 어긋났다 — OpenDART 는 `status=010`(등록되지 않은 키)을 AUTH 로 판정해
      예외에 실어 보내는데, 오케스트레이터가 예외 **타입만** 보고 POLICY 로 적었다.
      그러면 화면은 「정책 위반」이라 말하고 사람은 권한 설정을 뒤진다."""
    store = rig["store"]
    orch = rig["make"]("fnltt_bad_key.json")
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    with pytest.raises(OrchestrationError):
        orch.dry_run(job["job_id"], actor_id=ACTOR)
    out = store.get(job["job_id"])
    assert out["status"] == am.FAILED
    assert out["failure_kind"] == am.FAILURE_AUTH


def test_rate_limit_is_transport_not_policy(rig):
    """한도 초과는 재시도로 풀린다 — 정책 위반으로 적으면 사람이 권한을 뒤진다."""
    store = rig["store"]
    orch = rig["make"]("fnltt_rate_limited.json")
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    with pytest.raises(OrchestrationError):
        orch.dry_run(job["job_id"], actor_id=ACTOR)
    assert store.get(job["job_id"])["failure_kind"] == am.FAILURE_TRANSPORT


def test_failure_kind_is_decided_in_one_place():
    """실패 종류 판정이 두 곳에 있으면 반드시 갈린다."""
    from core.external_intelligence.orchestrator import failure_kind_of
    from core.external_intelligence.providers import base as B

    assert failure_kind_of(od.OpenDartStatusError("010", "키", am.FAILURE_AUTH)) == am.FAILURE_AUTH
    assert failure_kind_of(od.OpenDartStatusError("100", "필드", am.FAILURE_SCHEMA_DRIFT))         == am.FAILURE_SCHEMA_DRIFT
    assert failure_kind_of(B.ProviderCredentialError("키 없음")) == am.FAILURE_AUTH
    assert failure_kind_of(B.ProviderTransportError("타임아웃")) == am.FAILURE_TRANSPORT
    assert failure_kind_of(B.ProviderError("그 밖")) == am.FAILURE_POLICY


def test_missing_credential_is_reported_as_auth(rig):
    store = rig["store"]
    orch = rig["make"](env={})
    job = _job(store)
    out = orch.discover(job["job_id"], actor_id=ACTOR)
    assert out["status"] == am.FAILED
    assert out["failure_kind"] == am.FAILURE_AUTH
    assert "AFS_OPENDART_API_KEY" in out["status_reason"]


def test_a_request_without_a_provider_is_refused(rig):
    store = rig["store"]
    orch = rig["make"]()
    job = _job(store, request={"extras": {"fs_div": "CFS"}})
    with pytest.raises(OrchestrationError):
        orch.discover(job["job_id"], actor_id=ACTOR)
    assert store.get(job["job_id"])["status"] == am.FAILED


# ── ⑤ 중복 ─────────────────────────────────────────────────────────────────
def test_rerunning_the_same_request_inserts_nothing(rig):
    """★★★ 카나리 조건 — 「동일 요청 재실행 시 중복 0건」."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    _, first = orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert first.inserted == 4

    orch2, job2, _ = _to_review(rig)
    _, second = orch2.apply(job2["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert second.inserted == 0
    assert second.duplicate == 4
    assert store.staged_count("PUB-01") == 4


def test_the_second_run_still_reaches_active(rig):
    """중복 0건은 실패가 아니다 — 「이미 최신」인 정상 결과다."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    orch2, job2, _ = _to_review(rig)
    out, report = orch2.apply(job2["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert out["status"] == am.ACTIVE and report.ok is True


def test_dry_run_counts_duplicates_against_what_is_already_staged(rig):
    """「예상」이 아니라 실측이다 — 이미 들어간 업무 키와 대조한다."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    _, _, report = _to_review(rig)
    assert report.duplicate_rows == 4 and report.new_rows == 0


def test_the_raw_object_is_not_stored_twice(rig):
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    refs = {r["raw_object_ref"] for r in store.raw_objects(job["job_id"])}
    assert len(refs) == 1               # dry-run 과 apply 가 같은 응답을 받았다


# ── ⑥ 정정공시 ─────────────────────────────────────────────────────────────
def test_a_correction_adds_a_row_instead_of_overwriting(rig):
    """★★★ 접수번호가 업무 키에 있어 **다른 행**이 된다 — 옛 판이 남는다."""
    store = rig["store"]
    _approve_contract(store)
    orch = rig["make"]("fnltt_corrected.json")
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    job, _ = orch.dry_run(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    job, report = orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert report.superseded == 1
    rows = store.staged_rows(contract_key="PUB-01")
    assert len(rows) == 2
    statuses = {r["quality_status"] for r in rows}
    assert statuses == {"VALIDATED", "SUPERSEDED"}
    superseded = next(r for r in rows if r["quality_status"] == "SUPERSEDED")
    assert superseded["superseded_by"] == "20260520000999"
    assert superseded["payload"]["amount"] == 10500000000.0


def test_future_disclosures_are_excluded_at_the_as_of(rig):
    """2026-03 계획에 2026-05 정정값이 섞이면 재현이 아니라 사후 보정이다."""
    store = rig["store"]
    _approve_contract(store)
    orch = rig["make"]("fnltt_corrected.json")
    job = orch.discover(_job(store)["job_id"], actor_id=ACTOR)
    job, _ = orch.dry_run(job["job_id"], actor_id=ACTOR, as_of="2026-04-01")
    job, report = orch.apply(job["job_id"], actor_id=ACTOR, as_of="2026-04-01")
    published = {r["payload"]["published_at"] for r in store.staged_rows(contract_key="PUB-01")}
    assert "2026-05-20" not in published


# ── 봉투와 계보 ─────────────────────────────────────────────────────────────
def test_the_envelope_is_stamped_at_apply_time_not_by_the_provider(rig):
    """Provider 는 테넌트를 모른다 — 봉투는 여기서만 채운다."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    row = store.staged_rows(contract_key="PUB-01")[0]
    assert row["tenant_id"] == "tenant_default"
    assert row["data_origin"] == am.ORIGIN_PUBLIC_DISCLOSED
    assert row["certification_status"] == "UNCERTIFIED"
    assert row["lineage_id"].startswith("lin_")


def test_every_staged_row_points_back_to_its_raw_object(rig):
    """계보의 마지막 고리 — 값에서 원문까지 되짚을 수 있어야 한다."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    _, report = orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    for row in store.staged_rows(contract_key="PUB-01"):
        assert row["raw_object_ref"] == report.raw_object_ref
        assert rig["raw"].verify(row["raw_object_ref"])["ok"] is True


def test_staged_rows_are_not_certified(rig):
    """★★★ 격리 적재본은 운영 데이터셋이 아니다 — 인증 표시가 붙으면 안 된다."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert {r["certification_status"] for r in store.staged_rows()} == {"UNCERTIFIED"}


def test_checkpoint_is_recorded_for_the_next_refresh(rig):
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    out, _ = orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    assert out["checkpoint"]["covered_to"] == "2025"
    assert out["checkpoint"]["cursor"] == "20260316000123"
    assert out["last_success_at"]


def test_apply_report_never_claims_the_stages_it_skipped(rig):
    """지시 14 — 「운영 적용」을 했다고 말하지 않는다."""
    store = rig["store"]
    _approve_contract(store)
    orch, job, _ = _to_review(rig)
    _, report = orch.apply(job["job_id"], actor_id=ACTOR, as_of=AS_OF)
    done = {s.name for s in report.stages}
    skipped = {p["name"] for p in report.pending_stages}
    assert done & skipped == set()
    assert "KIT_BOUND" in skipped and "READINESS_REEVALUATED" in skipped
