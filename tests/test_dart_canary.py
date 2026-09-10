"""[DAO-9] DART 종단 카나리 — 지시 10 의 완주 조건을 **하나씩 센다**.

    사용자 요청: 「LS MnM 최근 10년 연결 재무실적을 수집해 전사 손익·현금 업무키트와 연결해줘」

## ★★★ 이 파일이 «완주» 라고 말하는 범위

    ①  회사명으로 corp_code 자동 식별            ✔ 시험한다
    ②  2016~2025 CFS 연간재무제표 수집           ✔ (fixture)
    ③  접수번호·발표일·원본 체크섬 보존           ✔
    ④  정정공시 supersedes 처리                  ✔
    ⑤  계정과목 매핑 제안                        ✔ (제안이지 매핑이 아니다)
    ⑥  공개실적과 내부 계정 연결 미리보기          ✔ (전 항목 사람 승인 필요)
    ⑦  Dry-run 결과 제공                        ✔
    ⑧  격리 DB 적용                             ✔
    ⑨  동일 요청 재실행 시 중복 0건               ✔
    ⑩  재무 업무키트 준비도 갱신                  ✘ **하지 않았다** — 아래 참조
    ⑪  출처와 vintage 를 포함한 질의 응답          ✔

⚠️⚠️ **⑩ 은 못 했고, 못 했다는 것을 시험이 단언한다.** 업무키트 결속은 계약이 인증된
  키트에 편입된 뒤에 의미가 있고, `PUB-01` 은 아직 제안에서 승인된 «별도 계약»이다.
  「거의 다 됐다」로 적으면 그 줄만 읽는 사람은 준비도가 올라간 줄 안다.

⚠️⚠️⚠️ **네트워크를 한 번도 쓰지 않는다.** 공식 응답 모양의 fixture 로만 돈다. 그러므로
  이 파일이 통과해도 「실제 DART 수집 완료」가 아니다 — 지시 10 의 마지막 문장이다.
  `test_canary_does_not_claim_real_collection` 이 그 경계를 시험으로 못 박는다.
"""
import json
import os

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence import providers as P
from core.external_intelligence import provenance as PV
from core.external_intelligence.acquisition_store import AcquisitionStore
from core.external_intelligence.orchestrator import PENDING_STAGES, AcquisitionOrchestrator
from core.external_intelligence.providers import opendart as od  # noqa: F401
from core.external_intelligence.raw_store import RawStore

KEY = "dartkey0123456789abcdef01234567"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "opendart")
REQUESTER = "t_member_a@test.invalid"
APPROVER = "t_dataadmin@test.invalid"
YEARS = list(range(2016, 2026))
AS_OF = "2026-12-31"

#: ⚠️ 합성 신원만 쓴다 — 실존 계정을 시험 기대값으로 못박지 않는다(`tests/org_seed` 규칙).


def _multiyear_transport(corrections=None):
    """연도별 fixture 를 돌려주는 전송층. **네트워크로 나가지 않는다.**"""
    corrections = corrections or {}

    def call(url, *, allowed_hosts, timeout=20.0):
        if "corpCode.xml" in url:
            name, ctype = "corp_code.zip", "application/zip"
        else:
            year = next((y for y in YEARS if f"bsns_year={y}" in url), YEARS[-1])
            name = corrections.get(year) or f"fnltt_{year}_cfs.json"
            ctype = "application/json"
        with open(os.path.join(FIX, name), "rb") as f:
            return {"body": f.read(), "content_type": ctype, "status": 200,
                    "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}
    return call


@pytest.fixture()
def rig(tmp_path):
    ledger = DecisionLedger(str(tmp_path / "ledger.db"))
    store = AcquisitionStore(str(tmp_path / "ei.db"), ledger=ledger)
    raw = RawStore(str(tmp_path / "raw"))

    def orchestrator(corrections=None):
        return AcquisitionOrchestrator(store=store, raw_store=raw,
                                       registry=P.provider_registry,
                                       env={"AFS_OPENDART_API_KEY": KEY},
                                       transport=_multiyear_transport(corrections))

    return {"store": store, "raw": raw, "orchestrator": orchestrator}


def _request(period_from="2016", period_to="2025"):
    return {"subject_name": "LS MnM", "purpose": "전사 손익·현금 업무키트 연결",
            "period_from": period_from, "period_to": period_to,
            "indicators": ["매출", "영업이익", "영업활동현금흐름"],
            "extras": {"provider_ids": ["OPENDART"], "fs_div": "CFS"}}


def _walk_one_year(rig, year, *, corrections=None, approve=True):
    """한 해를 요청부터 격리 적재까지 완주시킨다."""
    store = rig["store"]
    orch = rig["orchestrator"](corrections)
    if approve and not store.approved_contract("PUB-01"):
        proposal = store.propose_contract(M.pub01_proposal(), proposed_by=REQUESTER)
        store.decide_contract(proposal["proposal_id"], approve=True, reviewed_by=APPROVER,
                              reason="공개 재무자료 전용 계약으로 승인")
    job = store.create(tenant_id="tenant_default", requested_by=REQUESTER,
                       subject_name="LS MnM", purpose="전사 손익·현금 업무키트 연결",
                       request=_request(str(year), str(year)))
    job = orch.discover(job["job_id"], actor_id=REQUESTER)
    job, dry = orch.dry_run(job["job_id"], actor_id=REQUESTER, as_of=AS_OF)
    job, applied = orch.apply(job["job_id"], actor_id=APPROVER, as_of=AS_OF)
    return {"job": job, "dry": dry, "applied": applied, "orch": orch}


@pytest.fixture()
def ten_years(rig):
    """2016~2025 열 해를 전부 완주시킨다."""
    results = [_walk_one_year(rig, y) for y in YEARS]
    return {"rig": rig, "results": results}


# ── ① 회사명으로 corp_code 자동 식별 ────────────────────────────────────────
def test_01_company_code_is_resolved_from_the_name(rig):
    """지시 1 — 사용자에게 내부 ID 를 입력시키지 않는다."""
    out = _walk_one_year(rig, 2025)
    chosen = out["job"]["plan"]["chosen"]
    assert chosen["params"]["corp_code"] == "00126380"
    assert "LS MnM" in chosen["match_reason"]
    #: 요청 본문 어디에도 corp_code 를 넣지 않았다.
    assert "corp_code" not in json.dumps(_request(), ensure_ascii=False)


# ── ② 2016~2025 CFS 연간재무제표 ────────────────────────────────────────────
def test_02_ten_years_of_consolidated_annual_statements(ten_years):
    store = ten_years["rig"]["store"]
    rows = store.staged_rows(contract_key="PUB-01", limit=5000)
    years = sorted({r["payload"]["bsns_year"] for r in rows})
    assert years == [str(y) for y in YEARS]
    #: ★★★ 연결만 — 별도가 섞이면 합계가 조용히 틀린다.
    assert {r["payload"]["fs_div"] for r in rows} == {"CFS"}
    assert {r["payload"]["reprt_code"] for r in rows} == {"11011"}
    assert len(rows) == 40                       # 10년 × 4계정


def test_02b_every_year_reached_active(ten_years):
    assert [r["job"]["status"] for r in ten_years["results"]] == [am.ACTIVE] * 10
    assert all(r["applied"].ok for r in ten_years["results"])
    assert not any(r["applied"].partial for r in ten_years["results"])


# ── ③ 접수번호·발표일·원본 체크섬 보존 ──────────────────────────────────────
def test_03_receipt_number_published_date_and_checksum_are_preserved(ten_years):
    store, raw = ten_years["rig"]["store"], ten_years["rig"]["raw"]
    for row in store.staged_rows(contract_key="PUB-01", limit=5000):
        payload = row["payload"]
        assert payload["rcept_no"], "접수번호가 없다"
        assert payload["published_at"], "발표일이 없다"
        #: ★★★ 발표일은 접수번호에서 온다 — 「받은 날」이 아니다.
        assert payload["published_at"] == od.published_at_from_rcept_no(payload["rcept_no"])
        assert payload["vintage_date"] == payload["published_at"]
        assert row["checksum"] and row["raw_object_ref"]
        assert raw.verify(row["raw_object_ref"])["ok"] is True


def test_03b_raw_objects_are_content_addressed_per_year(ten_years):
    """해마다 다른 응답이므로 원문도 열 개여야 한다 — 하나면 같은 것을 열 번 적재했다."""
    store = ten_years["rig"]["store"]
    refs = {r["raw_object_ref"] for r in store.staged_rows(contract_key="PUB-01", limit=5000)}
    assert len(refs) == 10


# ── ④ 정정공시 supersedes ───────────────────────────────────────────────────
def test_04_correction_supersedes_without_losing_the_earlier_filing(rig):
    """★★★ 옛 판을 지우면 「그 계획이 당시 어떤 발표값을 썼는가」에 답할 수 없다."""
    out = _walk_one_year(rig, 2025, corrections={2025: "fnltt_corrected.json"})
    assert out["applied"].superseded == 1
    rows = rig["store"].staged_rows(contract_key="PUB-01")
    assert {r["quality_status"] for r in rows} == {"VALIDATED", "SUPERSEDED"}
    old = next(r for r in rows if r["quality_status"] == "SUPERSEDED")
    new = next(r for r in rows if r["quality_status"] == "VALIDATED")
    assert old["superseded_by"] == new["payload"]["rcept_no"]
    assert old["payload"]["amount"] != new["payload"]["amount"]


def test_04b_business_key_keeps_both_filings(rig):
    _walk_one_year(rig, 2025, corrections={2025: "fnltt_corrected.json"})
    keys = {r["business_key"] for r in rig["store"].staged_rows(contract_key="PUB-01")}
    assert len(keys) == 2, "정정 전후가 같은 키가 되면 하나가 다른 하나를 덮어쓴다"


# ── ⑤ 계정과목 매핑 제안 ────────────────────────────────────────────────────
def test_05_mapping_proposal_is_validated_but_never_auto_applied(ten_years):
    contract = ten_years["rig"]["store"].approved_contract("PUB-01")["document"]
    source_fields = ["thstrm_amount", "account_id", "rcept_no", "published_at",
                     "vintage_date", "corp_code", "bsns_year", "fs_div", "sj_div",
                     "reprt_code", "currency", "disclosure_row_id", "source_id",
                     "raw_object_ref", "trust_grade"]
    proposal = [{"source": f, "target": t} for f, t in [
        ("thstrm_amount", "amount"), ("account_id", "account_id"), ("rcept_no", "rcept_no"),
        ("published_at", "published_at"), ("vintage_date", "vintage_date"),
        ("corp_code", "corp_code"), ("bsns_year", "bsns_year"), ("fs_div", "fs_div"),
        ("sj_div", "sj_div"), ("reprt_code", "reprt_code"), ("currency", "currency"),
        ("disclosure_row_id", "disclosure_row_id"), ("source_id", "source_id"),
        ("raw_object_ref", "raw_object_ref"), ("trust_grade", "trust_grade")]]
    report = M.validate_mapping(proposal, contract=contract, source_fields=source_fields)
    assert report.ok is True
    #: ★★★ 형식이 맞다 ≠ 적용해도 된다.
    assert report.auto_appliable is False
    assert "account_id → account_id" in report.requires_human_approval


# ── ⑥ 공개실적과 내부 계정 연결 미리보기 ────────────────────────────────────
def test_06_account_linkage_preview_marks_every_item_for_human_approval(ten_years):
    store = ten_years["rig"]["store"]
    rows = store.staged_rows(contract_key="PUB-01", limit=5000)
    internal = [{"code": "4100", "name": "매출액"}, {"code": "4300", "name": "영업이익"},
                {"code": "1000", "name": "자산총계"}, {"code": "5900", "name": "잡손실"}]
    preview = PV.account_mapping_preview(rows, internal_accounts=internal)
    assert preview["public_account_count"] == 4
    assert len(preview["suggestions"]) == 4
    #: ★★★ 예외 없이 전부 사람 승인이다 — 가르면 「자신 있는 쪽」이 자동 승인된다.
    assert all(s["requires_human_approval"] for s in preview["suggestions"])
    assert all(s["basis"] for s in preview["suggestions"])
    revenue = next(s for s in preview["suggestions"]
                   if s["public_account_id"] == "ifrs-full_Revenue")
    assert "4100" in revenue["candidate_internal"]
    assert "매핑이 아닙니다" in preview["notice"]


def test_06b_no_overlap_is_reported_as_no_basis(ten_years):
    rows = ten_years["rig"]["store"].staged_rows(contract_key="PUB-01", limit=5000)
    preview = PV.account_mapping_preview(rows, internal_accounts=[{"code": "9", "name": "잡비"}])
    assert all(s["candidate_internal"] == [] for s in preview["suggestions"])
    assert all("없음" in s["basis"] for s in preview["suggestions"])


# ── ⑦ Dry-run 결과 ─────────────────────────────────────────────────────────
def test_07_dry_run_report_is_complete_and_writes_nothing(rig):
    store = rig["store"]
    orch = rig["orchestrator"]()
    proposal = store.propose_contract(M.pub01_proposal(), proposed_by=REQUESTER)
    store.decide_contract(proposal["proposal_id"], approve=True, reviewed_by=APPROVER,
                          reason="승인")
    job = store.create(tenant_id="tenant_default", requested_by=REQUESTER,
                       subject_name="LS MnM", request=_request("2025", "2025"))
    job = orch.discover(job["job_id"], actor_id=REQUESTER)
    before = store.staged_count()
    job, report = orch.dry_run(job["job_id"], actor_id=REQUESTER, as_of=AS_OF)
    assert store.staged_count() == before          # ★ 한 줄도 쓰지 않는다
    assert job["status"] == am.REVIEW_REQUIRED
    d = report.as_dict()
    assert d["expected_rows"] == 4 and d["new_rows"] == 4
    assert d["target_contract_status"] == "APPROVED"
    assert d["chosen_reason"] and d["estimated_bytes"] > 0
    assert d["validation"] and all(v["ok"] for v in d["validation"])


# ── ⑧ 격리 DB 적용 ─────────────────────────────────────────────────────────
def test_08_rows_land_in_the_isolated_store_uncertified(ten_years):
    store = ten_years["rig"]["store"]
    rows = store.staged_rows(contract_key="PUB-01", limit=5000)
    assert len(rows) == 40
    #: ★★★ 운영 데이터셋이 아니다.
    assert {r["certification_status"] for r in rows} == {"UNCERTIFIED"}
    assert {r["data_origin"] for r in rows} == {am.ORIGIN_PUBLIC_DISCLOSED}
    assert {r["contract_key"] for r in rows} == {"PUB-01"}


def test_08b_the_isolated_store_is_not_a_kit_dataset(ten_years):
    """격리 적재본이 업무키트 데이터셋과 같은 곳에 있으면 경계가 이름뿐이다."""
    import sqlite3
    store = ten_years["rig"]["store"]
    with sqlite3.connect(store.db_path) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "data_acquisition_rows" in tables
    assert "dataset_snapshots" not in tables, "업무키트 표가 이 DB 에 있다 — 경계가 무너졌다"


# ── ⑨ 재실행 중복 0건 ───────────────────────────────────────────────────────
def test_09_rerunning_the_whole_request_inserts_nothing(rig):
    first = [_walk_one_year(rig, y) for y in YEARS]
    assert sum(r["applied"].inserted for r in first) == 40

    second = [_walk_one_year(rig, y) for y in YEARS]
    assert sum(r["applied"].inserted for r in second) == 0
    assert sum(r["applied"].duplicate for r in second) == 40
    assert rig["store"].staged_count("PUB-01") == 40
    #: 중복 0건은 실패가 아니다 — 「이미 최신」이다.
    assert all(r["job"]["status"] == am.ACTIVE for r in second)


# ── ⑩ 업무키트 준비도 — **하지 않았다** ─────────────────────────────────────
def test_10_kit_readiness_is_declared_not_done(ten_years):
    """⚠️⚠️ 이 시험은 「됐다」가 아니라 **「안 됐다고 말하고 있다」** 를 센다.

    ★★★ 「거의 다 됐다」로 적으면 그 줄만 읽는 사람은 준비도가 올라간 줄 안다."""
    skipped = {name for name, _ in PENDING_STAGES}
    assert {"KIT_BOUND", "READINESS_REEVALUATED", "SNAPSHOT_CERTIFIED"} <= skipped

    for result in ten_years["results"]:
        report = result["applied"]
        done = {s.name for s in report.stages}
        assert done & skipped == set(), "안 한 단계가 완료 목록에 들어 있다"
        pending = {p["name"] for p in report.pending_stages}
        assert pending == skipped
        assert all(p["reason"] for p in report.pending_stages)


def test_10b_pub01_is_not_in_the_certified_kit(ten_years):
    """준비도가 안 바뀌는 이유가 실제로 성립하는지 — 계약이 키트에 없다."""
    import glob
    assert glob.glob("starter_kits/*/*/contracts/PUB-01.contract.json") == []
    approved = ten_years["rig"]["store"].approved_contract("PUB-01")
    assert approved is not None                      # 별도 계약으로는 승인됐고
    assert approved["document"]["status"] == "PROPOSED"   # 키트 인증본은 아니다


# ── ⑪ 출처와 vintage 를 포함한 질의 응답 ────────────────────────────────────
def test_11_a_value_never_comes_back_without_its_source(ten_years):
    """설계서 §6.2 — 「그 계획은 어떤 값을 썼는가」에 답할 수 있어야 한다."""
    store = ten_years["rig"]["store"]
    ans = PV.answer(store, contract_key="PUB-01",
                    match={"account_id": "ifrs-full_Revenue", "bsns_year": "2020"})
    assert ans.found is True
    assert ans.value == 9_558_000_000.0
    assert ans.unit == "KRW"
    assert ans.source_id == "OPENDART"
    assert ans.trust_grade == "gold"
    assert ans.vintage_date == ans.published_at == "2021-03-19"
    assert ans.raw_object_ref and ans.checksum
    #: ★★★ 공개 자료는 사실이지만 내부 실적이 아니다.
    assert ans.not_for_internal_actual is True


def test_11b_the_answer_chain_verifies_down_to_the_raw_bytes(ten_years):
    rig = ten_years["rig"]
    ans = PV.answer(rig["store"], contract_key="PUB-01",
                    match={"account_id": "dart_OperatingIncomeLoss", "bsns_year": "2016"})
    chain = PV.verify_chain(rig["store"], rig["raw"], ans)
    assert chain["ok"] is True and chain["source_id"] == "OPENDART"


def test_11c_a_broken_chain_is_reported_not_hidden(ten_years):
    """원문이 사라지면 그 답은 **근거가 없다** — 값이 남아 있어도 그렇다."""
    rig = ten_years["rig"]
    ans = PV.answer(rig["store"], contract_key="PUB-01",
                    match={"account_id": "ifrs-full_Revenue", "bsns_year": "2019"})
    path = os.path.join(rig["raw"].root, ans.raw_object_ref)
    with open(path, "wb") as f:
        f.write(b"tampered")
    chain = PV.verify_chain(rig["store"], rig["raw"], ans)
    assert chain["ok"] is False
    assert chain["reason"] == "CHECKSUM_MISMATCH"


def test_11d_series_carries_provenance_for_every_period(ten_years):
    """★ 값만 담은 배열을 돌려주지 않는다 — 그래프에 그려진 뒤에는 아무도 되짚지 않는다."""
    rows = PV.series(ten_years["rig"]["store"], contract_key="PUB-01",
                     match={"account_id": "ifrs-full_Revenue"})
    assert [r.period for r in rows] == [str(y) for y in YEARS]
    assert all(r.source_id and r.vintage_date and r.raw_object_ref for r in rows)
    assert all(r.not_for_internal_actual for r in rows)


def test_11e_as_of_reproduces_the_answer_that_was_visible_then(rig):
    """★★★ 정정공시 뒤에도 **그때 사람이 볼 수 있었던 값**으로 답한다."""
    _walk_one_year(rig, 2025, corrections={2025: "fnltt_corrected.json"})
    match = {"account_id": "ifrs-full_Revenue", "bsns_year": "2025"}
    now = PV.answer(rig["store"], contract_key="PUB-01", match=match)
    then = PV.answer(rig["store"], contract_key="PUB-01", match=match, as_of="2026-04-01")
    assert now.value == 10_320_000_000.0 and now.published_at == "2026-05-20"
    assert then.value == 10_500_000_000.0 and then.published_at == "2026-03-16"
    assert then.other_vintages == ()          # 그때는 정정본이 아직 없었다
    assert now.other_vintages == ("2026-03-16",)


def test_11f_an_empty_query_is_an_error_not_everything(ten_years):
    """빈 조건으로 아무거나 하나를 돌려주면 그 값이 근거가 된다."""
    with pytest.raises(PV.ProvenanceError):
        PV.answer(ten_years["rig"]["store"], contract_key="PUB-01", match={})


def test_11g_a_missing_value_says_so_rather_than_returning_zero(ten_years):
    ans = PV.answer(ten_years["rig"]["store"], contract_key="PUB-01",
                    match={"account_id": "ifrs-full_Revenue", "bsns_year": "2030"})
    assert ans.found is False and ans.value is None
    assert "아직 수집되지 않았" in ans.reason


# ── 카나리가 주장하지 않는 것 ───────────────────────────────────────────────
def test_canary_does_not_claim_real_collection(ten_years):
    """⚠️⚠️⚠️ 지시 10 의 마지막 문장 — 「실제 DART 수집 완료」라고 기록하지 않는다.

    이 시험은 **네트워크가 쓰이지 않았음**을 구조로 확인한다: 전송층이 fixture 파일만
    읽는다는 것이 전부이고, 그러므로 통과는 「배선이 맞다」까지다."""
    store = ten_years["rig"]["store"]
    for row in store.staged_rows(contract_key="PUB-01", limit=5000):
        #: 인증되지 않았고, 공개 자료이며, 내부 실적이 아니다.
        assert row["certification_status"] == "UNCERTIFIED"
        assert row["data_origin"] == am.ORIGIN_PUBLIC_DISCLOSED
        assert row["data_origin"] not in am.ORIGINS_FOR_INTERNAL_ACTUAL


def test_the_ledger_holds_the_whole_walk(ten_years):
    """열 해 × (요청 + 전이 6) 이 전부 원장에 있다."""
    store = ten_years["rig"]["store"]
    for result in ten_years["results"]:
        events = store.history(result["job"]["job_id"])
        kinds = [e["event_type"] for e in events]
        assert kinds.count("DATA_ACQUISITION_REQUESTED") == 1
        assert kinds.count("DATA_ACQUISITION_APPROVED") == 1
        assert kinds.count("DATA_ACQUISITION_ACTIVATED") == 1
        #: 승인자와 요청자가 **다른 사람**이어야 직무 분리가 성립한다.
        approved = next(e for e in events if e["event_type"] == "DATA_ACQUISITION_APPROVED")
        requested = next(e for e in events if e["event_type"] == "DATA_ACQUISITION_REQUESTED")
        assert approved["actor_id"] == APPROVER
        assert requested["actor_id"] == REQUESTER
        assert approved["actor_id"] != requested["actor_id"]


def test_contract_approval_is_recorded_once_for_the_whole_walk(ten_years):
    store = ten_years["rig"]["store"]
    events = store.ledger().list_events("data_contract", "PUB-01")
    published = [e for e in events if e["event_type"] == "DATA_CONTRACT_PUBLISHED"]
    assert len(published) == 1
    assert published[0]["actor_id"] == APPROVER
