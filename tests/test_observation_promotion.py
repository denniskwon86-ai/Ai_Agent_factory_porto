"""[F-6] 격리 적재본 → 관측값 승격 — Q2 를 여는 마지막 고리.

이 파일이 지키는 것 여섯.

  ①★★★ 승인되지 않은 원천이면 **전부 거부된다.** 그것이 정상이다(§12.4)
  ②★★★ `PUB-01`(공시 재무제표)은 **승격되지 않는다** — 지표가 아니라 회사 실적이다
  ③★★★ 없는 지표를 **말없이 만들지 않는다.** 명시해야 만든다
  ④ 계보가 끊기지 않는다 — 관측값에서 원문 파일까지 되짚을 수 있다
  ⑤ 정산: 고려 = 승격 + 거부. 조용히 사라지는 행이 없다
  ⑥ 승격된 값이 **계획 동인에 실제로 도달한다** — 이것이 F-6 의 목적이다
"""
from __future__ import annotations

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import observation_promotion as OP
from core.external_intelligence.acquisition_store import AcquisitionStore

APPROVER = "t_dataadmin@test.invalid"


@pytest.fixture()
def intel(tmp_path, monkeypatch):
    from core.external_intelligence import external_intelligence as ei
    monkeypatch.setattr(ei, "db_path", str(tmp_path / "ei_intel.db"), raising=False)
    #: ⚠️ 경로만 바꾸면 «표가 없다». 이 저장소는 `__init__` 에서 DDL 을 돌리므로
    #:   경로를 갈아끼운 뒤 «다시 한 번» 만들어 줘야 한다.
    ei._init_db()
    return ei


@pytest.fixture()
def store(tmp_path):
    return AcquisitionStore(str(tmp_path / "aq.db"),
                            ledger=DecisionLedger(str(tmp_path / "ledger.db")))


def _stage(store, *, contract="EXT-02", code="WB_COPPER", source_id="",
           origin=am.ORIGIN_PUBLIC_DISCLOSED, grade="silver", n=3):
    """격리 적재본을 만든다 — 실제 Provider 가 만드는 것과 같은 모양으로."""
    job = store.create(tenant_id="tenant_default", requested_by="t_member_a@test.invalid",
                       subject_name="LS MnM", purpose="원료구매 시나리오",
                       request={"subject_name": "LS MnM", "indicators": ["구리"]})
    rows = [{
        "business_key": code + ":nominal_price:2025-0" + str(i + 1),
        "contract_key": contract, "data_origin": origin,
        "raw_object_ref": "WB_PINK_SHEET/ab/abc123.xlsx",
        "payload": {"indicator_code": code, "observed_at": "2025-0" + str(i + 1),
                    "value": 9000.0 + i, "unit": "$/mt", "vintage_date": "2025-0" + str(i + 1),
                    "trust_grade": grade, "source_id": source_id,
                    "commodity_name": "Copper", "published_at": ""},
    } for i in range(n)]
    store.stage_rows(job["job_id"], rows)
    return job["job_id"]


def _approved_source(intel, name="World Bank Pink Sheet", grade="silver"):
    src = intel.register_source(name=name, source_type="CSV", trust_grade=grade,
                                allowed_usage="출처 표시 시 재사용 가능")
    intel.approve_source(src["source_id"], APPROVER)
    return src["source_id"]


# ── ① 승인되지 않은 원천 ─────────────────────────────────────────────────────
def test_unapproved_source_blocks_everything(store, intel):
    """★★★ 승인 전에는 «전부 거부»가 정상이다 — §12.4."""
    src = intel.register_source(name="미승인 원천", source_type="CSV", trust_grade="silver")
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    job = _stage(store, source_id=src["source_id"])
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 0
    assert all(r.reason == OP.REJECT_GATE for r in rep.rejected)
    assert any("승인" in r.detail for r in rep.rejected)
    assert any("승인해야" in a for a in rep.next_actions)


def test_approving_the_source_opens_it(store, intel):
    """승인만 바뀌면 같은 행이 통과한다 — 막던 것이 «승인»이었음을 증명한다."""
    src = intel.register_source(name="World Bank", source_type="CSV", trust_grade="silver")
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    job = _stage(store, source_id=src["source_id"])
    assert OP.promote(store, job, actor_id=APPROVER).promoted == 0
    intel.approve_source(src["source_id"], APPROVER)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 3, [r.detail for r in rep.rejected]


# ── ② PUB-01 은 지표가 아니다 ────────────────────────────────────────────────
def test_public_financials_are_never_promoted(store, intel):
    """★★★ 공시 재무제표를 관측값으로 올리면 «외생 지표»와 «회사 실적»이 한 통에 섞인다."""
    src = _approved_source(intel)
    job = _stage(store, contract="PUB-01", source_id=src)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 0
    assert {r.reason for r in rep.rejected} == {OP.REJECT_CONTRACT}
    assert "PUB-01" not in OP.PROMOTABLE_CONTRACTS


@pytest.mark.parametrize("contract", ["EXT-01", "EXT-02", "EXT-03"])
def test_external_contracts_are_promotable(contract):
    assert contract in OP.PROMOTABLE_CONTRACTS


def test_internal_actual_origin_is_refused(store, intel):
    """성격이 REAL(내부 실적)이면 외생 지표로 올리지 않는다."""
    src = _approved_source(intel)
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    job = _stage(store, source_id=src, origin=am.ORIGIN_REAL)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 0
    assert {r.reason for r in rep.rejected} == {OP.REJECT_ORIGIN}


# ── ③ 지표를 말없이 만들지 않는다 ────────────────────────────────────────────
def test_unknown_indicator_is_refused_not_invented(store, intel):
    """★★★ 어휘를 자동 생성하면 같은 뜻의 지표가 둘 생기고 집계가 조각난다."""
    src = _approved_source(intel)
    job = _stage(store, code="WB_TUNGSTEN", source_id=src)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 0
    assert {r.reason for r in rep.rejected} == {OP.REJECT_NO_INDICATOR}
    assert rep.indicators_registered == ()
    assert any("WB_TUNGSTEN" in a for a in rep.next_actions)
    assert intel.get_indicator("WB_TUNGSTEN") is None


def test_registering_is_possible_but_must_be_asked_for(store, intel):
    src = _approved_source(intel)
    job = _stage(store, code="WB_TUNGSTEN", source_id=src)
    rep = OP.promote(store, job, actor_id=APPROVER, register_missing=True)
    assert rep.promoted == 3
    assert rep.indicators_registered == ("WB_TUNGSTEN",)
    assert intel.get_indicator("WB_TUNGSTEN") is not None


# ── ④ 계보 ───────────────────────────────────────────────────────────────────
def test_lineage_survives_the_promotion(store, intel):
    """★ 관측값에서 «원문 파일»까지 되짚을 수 있어야 한다 — Q4 의 마지막 고리."""
    src = _approved_source(intel)
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    job = _stage(store, source_id=src)
    OP.promote(store, job, actor_id=APPROVER)
    obs = intel.list_observations("WB_COPPER")
    assert obs
    assert all(o["source_record_ref"].endswith(".xlsx") for o in obs)
    assert all(o["vintage"] for o in obs)


def test_unit_and_grade_travel_with_the_value(store, intel):
    src = _approved_source(intel)
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    OP.promote(store, _stage(store, source_id=src), actor_id=APPROVER)
    obs = intel.list_observations("WB_COPPER")
    assert {o["unit"] for o in obs} == {"$/mt"}
    assert {o["grade"] for o in obs} == {"silver"}


# ── ⑤ 정산 ───────────────────────────────────────────────────────────────────
def test_every_row_is_promoted_or_refused_with_a_reason(store, intel):
    src = _approved_source(intel)
    job = _stage(store, code="WB_TUNGSTEN", source_id=src)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.accounted, (rep.considered, rep.promoted, len(rep.rejected))
    assert all(r.reason and r.detail for r in rep.rejected)


def test_an_empty_job_says_what_to_do(store, intel):
    job = store.create(tenant_id="tenant_default", requested_by="t_member_a@test.invalid",
                       subject_name="LS MnM", purpose="x", request={})
    rep = OP.promote(store, job["job_id"], actor_id=APPROVER)
    assert rep.considered == 0
    assert rep.next_actions


# ── ⑥★★★ 승격된 값이 «계획 동인»에 도달하는가 — F-6 의 목적 ─────────────────
def test_promoted_value_reaches_the_planning_driver(store, intel, tmp_path, monkeypatch):
    """★★★ 이것이 F-6 이 열려는 경로다.

    수집 → 격리 적재 → 승격 → 관측값 → 계획 동인 → 「쓸 수 있는가」 판정."""
    from core import planning_drivers as PD
    from core.planning_model import planning_store
    monkeypatch.setattr(planning_store, "db_path", str(tmp_path / "planning.db"),
                        raising=False)
    for attr in ("_ready", "_prepared_for"):
        if hasattr(planning_store, attr):
            monkeypatch.setattr(planning_store, attr, None, raising=False)

    src = _approved_source(intel)
    intel.upsert_indicator("WB_COPPER", "구리 국제가격", required_grade="silver")
    OP.promote(store, _stage(store, source_id=src), actor_id=APPROVER)

    #: 동인을 «외부 지표에 연결»한다. 탄력도는 도메인 결정이라 여기서 지어내지 않는다.
    PD.register_driver("COPPER_PRICE", "구리 가격", unit="$/mt",
                       category="원자재", external_code="WB_COPPER")

    out = PD.resolve_external_change("COPPER_PRICE", purpose="scenario",
                                     baseline_value=9000.0)
    assert out["usable"] is True, out
    assert out["external_code"] == "WB_COPPER"
    assert out["observed_value"] > 0
    assert out["grade"] == "silver"
    assert out["vintage"]                      # 재현성 — 어느 발표값으로 계산했나


def test_a_driver_without_an_external_code_says_so(tmp_path, monkeypatch):
    """연결이 «없다»와 값이 «없다»는 다른 일이다 — 0% 로 대체하지 않는다."""
    from core import planning_drivers as PD
    from core.planning_model import planning_store
    monkeypatch.setattr(planning_store, "db_path", str(tmp_path / "p2.db"), raising=False)
    for attr in ("_ready", "_prepared_for"):
        if hasattr(planning_store, attr):
            monkeypatch.setattr(planning_store, attr, None, raising=False)
    PD.register_driver("LONELY", "연결 없는 동인")
    out = PD.resolve_external_change("LONELY", purpose="scenario", baseline_value=100.0)
    assert out["usable"] is False
    assert "연결" in out["reason"]
    assert "0%" not in str(out.get("observed_value", ""))


# ── 원천 등록 — 승인은 «하지 않는다» ────────────────────────────────────────
def test_registering_a_provider_source_does_not_approve_it(intel):
    """★★★ 등록과 승인은 다른 일이다. 코드가 승인하면 §12.4 가 장식이 된다."""
    from core.external_intelligence.providers import worldbank as W
    src = OP.register_provider_source(W.WorldBankPinkSheetProvider.descriptor)
    assert src["enabled"] in (0, False)
    assert src["trust_grade"] == "silver"
    assert src["name"] == W.WorldBankPinkSheetProvider.descriptor.name


def test_registering_twice_does_not_duplicate(intel):
    from core.external_intelligence.providers import worldbank as W
    d = W.WorldBankPinkSheetProvider.descriptor
    a = OP.register_provider_source(d)
    b = OP.register_provider_source(d)
    assert a["source_id"] == b["source_id"]


# ── 【2026-09-09 Codex 지적】 네 결함의 회귀 ──────────────────────────────────
#: ⚠️ 앞의 시험들이 초록이었던 이유: fixture 가 «진짜 src_… id» 를 주입했다.
#:   실제 수집 경로는 provider_id 를 싣는다 — 내 말로 쓴 fixture 가 계약을 대신 정의했다.

def test_the_registered_source_id_is_the_provider_id(intel):
    """★★★ ① 수집 행의 source_id(provider_id)와 등록 원천 id 가 «같아야» 한다.

    다르면 승인 여부 이전에 「존재하지 않는 원천」으로 전부 거부된다(재현 확인)."""
    from core.external_intelligence.providers import worldbank as W
    d = W.WorldBankPinkSheetProvider.descriptor
    src = OP.register_provider_source(d)
    assert src["source_id"] == d.provider_id, "원천 id 와 provider_id 가 갈리면 사슬이 끊긴다"
    assert intel.get_source(d.provider_id) is not None


def test_the_real_collection_path_source_id_resolves(store, intel):
    """수집기가 «실제로 싣는» 값으로 승격이 도는가 — fixture 가 아니라."""
    from core.external_intelligence.providers import worldbank as W
    d = W.WorldBankPinkSheetProvider.descriptor
    src = OP.register_provider_source(d)
    intel.approve_source(src["source_id"], APPROVER)
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    #: orchestrator.py:587 이 넣는 것과 같은 값 — provider_id 다.
    job = _stage(store, source_id=d.provider_id)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 3, [r.detail for r in rep.rejected]


def test_an_empty_source_id_is_refused_here_not_downstream(store, intel):
    """★★★ ② `record_observation` 은 빈 source_id 면 승인 검사를 «건너뛴다».

    아래 관문에 기대면 §12.4 가 빈 문자열 하나로 우회된다 — 여기서 막는다.
    (재현 확인: 빈 값으로 관측값이 그냥 등록됐다.)"""
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    job = _stage(store, source_id="")
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 0
    assert {r.reason for r in rep.rejected} == {OP.REJECT_NO_SOURCE}
    assert intel.list_observations("WB_COPPER") == []
    assert any("승인 검사를 건너뛰" in a for a in rep.next_actions)


def test_the_downstream_gate_really_does_skip_on_empty(intel):
    """★ 위 시험이 «가상의 위험»이 아님을 증명한다 — 관문이 실제로 건너뛴다."""
    intel.upsert_indicator("PROBE_SKIP", "탐침", required_grade="silver")
    intel.record_observation(indicator_code="PROBE_SKIP", observed_at="2025-01",
                             value=1.0, vintage="2025-01", grade="silver", source_id="")
    assert intel.list_observations("PROBE_SKIP"), (
        "관문이 빈 source_id 를 막는다면 이 시험을 지우고 승격의 방어도 재검토할 것")


def test_hitting_the_read_limit_stops_instead_of_lying(store, intel):
    """★★★ ③ 저장소가 5,000행에서 자른다. 일부만 올리면서 accounted=True 면 «정산이 거짓»이다."""
    src = _approved_source(intel)
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    job = _stage(store, source_id=src, n=OP.STAGED_READ_LIMIT)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert rep.promoted == 0
    assert rep.considered == 0
    assert any("한도" in a for a in rep.next_actions)
    assert any("나누어" in a for a in rep.next_actions)


def test_a_failure_is_not_reported_as_a_policy_block(store, intel, monkeypatch):
    """★★★ ④ DB 장애를 «승인 대기»로 표시하면 사람이 승인하러 가서 헛수고한다."""
    src = _approved_source(intel)
    intel.upsert_indicator("WB_COPPER", "구리", required_grade="silver")
    job = _stage(store, source_id=src)

    def boom(*a, **k):
        raise RuntimeError("디스크가 응답하지 않습니다")

    monkeypatch.setattr(intel, "record_observation", boom)
    rep = OP.promote(store, job, actor_id=APPROVER)
    assert {r.reason for r in rep.rejected} == {OP.REJECT_ERROR}
    assert OP.REJECT_GATE not in {r.reason for r in rep.rejected}
    assert any("장애" in a for a in rep.next_actions)
    assert not any("승인해야" in a for a in rep.next_actions), \
        "장애인데 «승인하러 가라»고 하면 헛걸음시킨다"
