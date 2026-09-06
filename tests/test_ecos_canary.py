"""[DAO-10] ECOS 종단 — **두 번째 원천이 첫 번째의 배선을 그대로 탄다**.

첫 Provider 를 만들 때 세운 계약이 실제로 계약이었는지는, **두 번째를 붙여 봐야** 안다.
이 파일은 ECOS 를 같은 오케스트레이터에 흘려 보고 다음을 센다.

  ① 계약이 **말하는 성격**과 들어올 행의 성격이 다르면 막힌다(그리고 상태도 안 움직인다).
  ② 업무 키 규칙이 계약마다 다른데 **한 표에서** 나온다.
  ③ 두 원천의 행이 같은 격리 저장소에 있어도 서로를 덮지 않는다.
  ④ 계보 질의가 **계약마다 다른 열 이름**에도 답한다.

⚠️ 네트워크 0회. 통과는 「배선이 맞다」까지다.
"""
import os

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence import providers as P
from core.external_intelligence import provenance as PV
from core.external_intelligence.acquisition_store import AcquisitionStore
from core.external_intelligence.orchestrator import (AcquisitionOrchestrator,
                                                     OrchestrationError,
                                                     assert_origin_fits)
from core.external_intelligence.providers import ecos as E  # noqa: F401  (등록)
from core.external_intelligence.providers import opendart as od  # noqa: F401
from core.external_intelligence.raw_store import RawStore

ECOS_KEY = "ecoskey0123456789abcdefghij"
DART_KEY = "dartkey0123456789abcdef01234567"
ECOS_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "ecos")
DART_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "opendart")
REQUESTER = "t_member_a@test.invalid"
APPROVER = "t_dataadmin@test.invalid"


def _transport(search="search_fx_2025.json"):
    def call(url, *, allowed_hosts, timeout=20.0):
        if "ecos.bok.or.kr" in url:
            name = "item_list_fx.json" if "StatisticItemList" in url else search
            path, ctype = os.path.join(ECOS_FIX, name), "application/json"
        elif "corpCode.xml" in url:
            path, ctype = os.path.join(DART_FIX, "corp_code.zip"), "application/zip"
        else:
            path, ctype = os.path.join(DART_FIX, "fnltt_2025_cfs_ok.json"), "application/json"
        with open(path, "rb") as f:
            return {"body": f.read(), "content_type": ctype, "status": 200,
                    "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}
    return call


@pytest.fixture()
def rig(tmp_path):
    store = AcquisitionStore(str(tmp_path / "ei.db"),
                             ledger=DecisionLedger(str(tmp_path / "ledger.db")))
    raw = RawStore(str(tmp_path / "raw"))

    def make(search="search_fx_2025.json"):
        return AcquisitionOrchestrator(
            store=store, raw_store=raw, registry=P.provider_registry,
            env={"AFS_ECOS_API_KEY": ECOS_KEY, "AFS_OPENDART_API_KEY": DART_KEY},
            transport=_transport(search))

    return {"store": store, "raw": raw, "make": make}


def _approve(store, document):
    proposal = store.propose_contract(document, proposed_by=REQUESTER)
    return store.decide_contract(proposal["proposal_id"], approve=True,
                                 reviewed_by=APPROVER, reason="승인")


def _ecos_job(store):
    return store.create(
        tenant_id="tenant_default", requested_by=REQUESTER, subject_name="LS MnM",
        purpose="환율 가정",
        request={"subject_name": "LS MnM", "purpose": "환율 가정", "period_from": "2025",
                 "period_to": "2025", "indicators": ["환율"],
                 "extras": {"provider_ids": ["ECOS"]}})


def _dart_job(store):
    return store.create(
        tenant_id="tenant_default", requested_by=REQUESTER, subject_name="LS MnM",
        purpose="공개 재무실적",
        request={"subject_name": "LS MnM", "purpose": "공개 재무실적", "period_from": "2025",
                 "period_to": "2025", "extras": {"provider_ids": ["OPENDART"],
                                                 "fs_div": "CFS"}})


def _walk(rig, job, *, search="search_fx_2025.json"):
    orch = rig["make"](search)
    job = orch.discover(job["job_id"], actor_id=REQUESTER)
    job, dry = orch.dry_run(job["job_id"], actor_id=REQUESTER)
    job, applied = orch.apply(job["job_id"], actor_id=APPROVER)
    return {"job": job, "dry": dry, "applied": applied, "orch": orch}


# ── ① 계약 성격 검사 ────────────────────────────────────────────────────────
def test_a_synthetic_contract_refuses_public_rows(rig):
    """★★★ 「시연 자료」라고 적힌 그릇에 사실인 값이 담기면 계약이 거짓말을 한다."""
    store = rig["store"]
    synthetic = M.build_contract_proposal(
        dataset_id="EXT-01", dataset_name="환율(시연)", business_keys=["observation_id"],
        domain_fields=M.EXT01_DOMAIN_FIELDS, data_origin=am.ORIGIN_SYNTHETIC,
        rationale="시연용")
    _approve(store, synthetic)
    orch = rig["make"]()
    job = orch.discover(_ecos_job(store)["job_id"], actor_id=REQUESTER)
    job, _ = orch.dry_run(job["job_id"], actor_id=REQUESTER)
    with pytest.raises(OrchestrationError) as exc:
        orch.apply(job["job_id"], actor_id=APPROVER)
    assert "SYNTHETIC" in str(exc.value) and "PUBLIC_DISCLOSED" in str(exc.value)


def test_the_mismatch_does_not_move_the_state_or_stage_rows(rig):
    """거부는 「승인했는데 실패한」 기록을 남기지 않는다."""
    store = rig["store"]
    _approve(store, M.build_contract_proposal(
        dataset_id="EXT-01", dataset_name="환율(시연)", business_keys=["observation_id"],
        domain_fields=M.EXT01_DOMAIN_FIELDS, data_origin=am.ORIGIN_SYNTHETIC,
        rationale="시연용"))
    orch = rig["make"]()
    job = orch.discover(_ecos_job(store)["job_id"], actor_id=REQUESTER)
    job, _ = orch.dry_run(job["job_id"], actor_id=REQUESTER)
    with pytest.raises(OrchestrationError):
        orch.apply(job["job_id"], actor_id=APPROVER)
    assert store.get(job["job_id"])["status"] == am.REVIEW_REQUIRED
    assert store.staged_count() == 0
    kinds = [e["event_type"] for e in store.history(job["job_id"])]
    assert "DATA_ACQUISITION_APPROVED" not in kinds


def test_a_contract_without_a_declared_origin_is_refused():
    """무엇이 담기는지 말하지 않는 계약에는 넣지 않는다."""
    with pytest.raises(OrchestrationError):
        assert_origin_fits({"classification": {}}, am.ORIGIN_PUBLIC_DISCLOSED,
                           contract_key="X-01")


def test_matching_origins_pass():
    assert_origin_fits({"classification": {"data_origin": am.ORIGIN_PUBLIC_DISCLOSED}},
                       am.ORIGIN_PUBLIC_DISCLOSED, contract_key="EXT-01")


def test_the_kit_contract_is_the_case_this_check_exists_for():
    """★ 키트의 EXT-01 이 실제로 그 경우다 — 열은 관측값인데 분류만 SYNTHETIC."""
    import glob
    import json
    path = glob.glob("starter_kits/*/*/contracts/EXT-01.contract.json")[0]
    with open(path, encoding="utf-8") as f:
        kit = json.load(f)
    assert kit["classification"]["data_origin"] == am.ORIGIN_SYNTHETIC
    with pytest.raises(OrchestrationError):
        assert_origin_fits(kit, am.ORIGIN_PUBLIC_DISCLOSED, contract_key="EXT-01")


# ── 고친 계약으로는 완주한다 ────────────────────────────────────────────────
def test_the_corrected_contract_lets_the_walk_finish(rig):
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    out = _walk(rig, _ecos_job(store))
    assert out["job"]["status"] == am.ACTIVE
    assert out["applied"].ok is True and out["applied"].inserted == 6
    rows = store.staged_rows(contract_key="EXT-01")
    assert {r["data_origin"] for r in rows} == {am.ORIGIN_PUBLIC_DISCLOSED}
    assert {r["certification_status"] for r in rows} == {"UNCERTIFIED"}


def test_the_correction_proposal_keeps_the_contract_key(rig):
    """새 키를 만들면 「환율은 어느 계약인가」에 답이 둘이 된다."""
    doc = M.ext01_public_proposal()
    assert doc["dataset_id"] == "EXT-01"
    assert M.ROUTING_TABLE["fx_rate"] == "EXT-01"
    assert doc["status"] == "PROPOSED"
    assert "격리 적재본을 설명" in doc["proposal"]["rationale"]


def test_the_kit_file_is_not_touched(rig):
    """★★★ 인증된 키트를 몰래 바꾸지 않는다."""
    import glob
    import json
    _approve(rig["store"], M.ext01_public_proposal())
    _walk(rig, _ecos_job(rig["store"]))
    path = glob.glob("starter_kits/*/*/contracts/EXT-01.contract.json")[0]
    with open(path, encoding="utf-8") as f:
        kit = json.load(f)
    assert kit["classification"]["data_origin"] == am.ORIGIN_SYNTHETIC
    assert kit["status"] == "APPROVED_FOR_DEMO"


# ── ② 업무 키가 한 표에서 나온다 ────────────────────────────────────────────
def test_business_key_rules_are_declared_in_one_table():
    """★★★ 호출부가 각자 만들면 같은 행이 다른 키를 얻고, 중복 인덱스가 아무것도 막지 않는다."""
    rules = AcquisitionOrchestrator._BUSINESS_KEY_RULES
    assert rules["PUB-01"] is M.disclosure_row_id
    assert rules["EXT-01"] is M.observation_row_id


def test_observation_key_needs_all_three_parts():
    assert M.observation_row_id({"stat_code": "731Y001", "item_code": "0000001",
                                 "observed_at": "2025-03"}) == "731Y001:0000001:2025-03"
    with pytest.raises(M.MappingError):
        M.observation_row_id({"stat_code": "731Y001", "observed_at": "2025-03"})


def test_rerunning_ecos_inserts_nothing(rig):
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    first = _walk(rig, _ecos_job(store))
    second = _walk(rig, _ecos_job(store))
    assert first["applied"].inserted == 6
    assert second["applied"].inserted == 0 and second["applied"].duplicate == 6
    assert store.staged_count("EXT-01") == 6


def test_an_unknown_contract_falls_back_to_a_content_hash():
    """규칙이 없는 계약도 **같은 내용이면 같은 행**이 되어야 중복이 막힌다."""
    row = {"a": 1, "b": "x"}
    first = AcquisitionOrchestrator._business_key(row, "ZZZ-99")
    second = AcquisitionOrchestrator._business_key(dict(row), "ZZZ-99")
    assert first == second and len(first) == 32
    assert AcquisitionOrchestrator._business_key({"a": 2, "b": "x"}, "ZZZ-99") != first


# ── ③ 두 원천이 한 저장소에 있어도 섞이지 않는다 ────────────────────────────
def test_two_providers_coexist_without_overwriting(rig):
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    _approve(store, M.pub01_proposal())
    _walk(rig, _ecos_job(store))
    _walk(rig, _dart_job(store))

    ecos_rows = store.staged_rows(contract_key="EXT-01")
    dart_rows = store.staged_rows(contract_key="PUB-01")
    assert len(ecos_rows) == 6 and len(dart_rows) == 4
    assert store.staged_count() == 10
    #: 원문도 둘로 나뉘어 보관된다.
    sources = {r["source_id"] for r in store.raw_objects(store.list_jobs()[0]["job_id"])}
    assert sources <= {"ECOS", "OPENDART"}


def test_each_row_points_at_its_own_source(rig):
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    _approve(store, M.pub01_proposal())
    _walk(rig, _ecos_job(store))
    _walk(rig, _dart_job(store))
    assert {r["payload"]["source_id"] for r in store.staged_rows(contract_key="EXT-01")} \
        == {"ECOS"}
    assert {r["payload"]["source_id"] for r in store.staged_rows(contract_key="PUB-01")} \
        == {"OPENDART"}


# ── ④ 계보 질의가 계약마다 다른 열 이름에도 답한다 ──────────────────────────
def test_provenance_answers_for_both_contracts(rig):
    """⚠️ 실측으로 어긋났다 — `answer()` 가 DART 의 `bsns_year`·`currency` 를 박아 놔
      ECOS 를 붙이자 기간과 단위가 **조용히 빈 값**이었다."""
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    _approve(store, M.pub01_proposal())
    _walk(rig, _ecos_job(store))
    _walk(rig, _dart_job(store))

    fx = PV.answer(store, contract_key="EXT-01",
                   match={"indicator_code": "FX_USDKRW", "observed_at": "2025-03"},
                   value_field="value")
    assert fx.found and fx.value == 1466.0
    assert fx.period == "2025-03" and fx.unit == "원"
    assert fx.source_id == "ECOS" and fx.trust_grade == "gold"

    rev = PV.answer(store, contract_key="PUB-01",
                    match={"account_id": "ifrs-full_Revenue", "bsns_year": "2025"})
    assert rev.found and rev.period == "2025" and rev.unit == "KRW"
    assert rev.source_id == "OPENDART"


def test_both_answers_are_marked_not_internal_actual(rig):
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    _walk(rig, _ecos_job(store))
    fx = PV.answer(store, contract_key="EXT-01",
                   match={"indicator_code": "FX_USDKRW", "observed_at": "2025-01"},
                   value_field="value")
    assert fx.not_for_internal_actual is True


def test_series_carries_the_period_for_ecos(rig):
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    _walk(rig, _ecos_job(store))
    rows = PV.series(store, contract_key="EXT-01", match={"indicator_code": "FX_USDKRW"},
                     period_field="observed_at", value_field="value")
    assert [r.period for r in rows] == ["2025-01", "2025-02", "2025-03",
                                        "2025-04", "2025-05", "2025-06"]
    assert all(r.unit == "원" and r.source_id == "ECOS" for r in rows)
    assert all(r.raw_object_ref for r in rows)


def test_the_ecos_chain_verifies_to_the_raw_bytes(rig):
    store = rig["store"]
    _approve(store, M.ext01_public_proposal())
    _walk(rig, _ecos_job(store))
    ans = PV.answer(store, contract_key="EXT-01",
                    match={"indicator_code": "FX_USDKRW", "observed_at": "2025-06"},
                    value_field="value")
    assert PV.verify_chain(store, rig["raw"], ans)["ok"] is True


# ── 원천 카드가 화면까지 간다 ───────────────────────────────────────────────
def test_catalog_ranks_both_providers_and_names_missing_credentials():
    chosen, excluded = P.provider_registry.ranked(require_credential_present=True, env={})
    assert chosen == ()
    ids = {e.provider_id for e in excluded}
    assert {"ECOS", "OPENDART"} <= ids
    assert all(e.reason for e in excluded)

    ok, _ = P.provider_registry.ranked(
        require_credential_present=True,
        env={"AFS_ECOS_API_KEY": ECOS_KEY, "AFS_OPENDART_API_KEY": DART_KEY})
    assert {"ECOS", "OPENDART"} <= {d.provider_id for d in ok}


def test_for_contract_finds_the_right_provider():
    assert "ECOS" in {d.provider_id for d in P.provider_registry.for_contract("EXT-01")}
    assert "OPENDART" in {d.provider_id for d in P.provider_registry.for_contract("PUB-01")}
    assert "ECOS" not in {d.provider_id for d in P.provider_registry.for_contract("PUB-01")}
