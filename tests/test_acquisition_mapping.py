"""[DAO-6] 라우팅·매핑·새 계약 제안 — **억지로 연결하지 않는다**를 시험이 센다.

이 파일이 막는 것 다섯.

  ① 라우팅표에 없는 자료를 **가장 비슷한 계약에 밀어 넣는** 것.
  ② 계약에 없는 필드를 **지어내는** 것.
  ③ 단위가 다른데 **조용히 환산**하는 것.
  ④ 계정과목 대응이 **형식 검사만으로 승인**되는 것.
  ⑤ 새 계약이 인증된 키트를 **몰래 바꾸는** 것.
"""
import json
import glob

import pytest

from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M

KIT_CONTRACTS = ["EXT-01", "EXT-02", "EXT-03", "MDM-01", "KNW-01", "FIN-03"]
CONTRACT = M.pub01_proposal()

FULL_MAPPING = [{"source": s, "target": t} for s, t in [
    ("thstrm_amount", "amount"), ("currency", "currency"), ("rcept_no", "rcept_no"),
    ("published_at", "published_at"), ("vintage_date", "vintage_date"),
    ("account_id", "account_id"), ("corp_code", "corp_code"), ("bsns_year", "bsns_year"),
    ("reprt_code", "reprt_code"), ("fs_div", "fs_div"), ("sj_div", "sj_div"),
    ("disclosure_row_id", "disclosure_row_id"), ("source_id", "source_id"),
    ("raw_object_ref", "raw_object_ref"), ("trust_grade", "trust_grade")]]
SOURCES = [m["source"] for m in FULL_MAPPING] + ["prior_amount", "account_nm"]


def _validate(mapping=None, **over):
    kwargs = dict(contract=CONTRACT, source_fields=SOURCES)
    kwargs.update(over)
    return M.validate_mapping(mapping if mapping is not None else FULL_MAPPING, **kwargs)


# ── ① 라우팅 ────────────────────────────────────────────────────────────────
def test_routing_table_covers_every_kind_the_instruction_lists():
    """지시 5 의 목적지가 전부 표에 있어야 한다."""
    for kind, expected in [("company_identity", "MDM-01"), ("public_financials", "PUB-01"),
                           ("fx_rate", "EXT-01"), ("commodity_price", "EXT-02"),
                           ("freight", "EXT-03"), ("disclosure_document", "KNW-01")]:
        assert M.ROUTING_TABLE[kind] == expected


def test_known_kind_routes_to_its_contract():
    s = M.route("fx_rate", known_contract_keys=KIT_CONTRACTS)
    assert s.contract_key == "EXT-01" and s.needs_new_contract is False


def test_unknown_kind_is_not_forced_into_the_nearest_contract():
    """★★★ 밀어 넣으면 그 계약을 읽는 쪽이 **자기가 아는 뜻으로** 읽는다."""
    s = M.route("임원보수현황", known_contract_keys=KIT_CONTRACTS)
    assert s.needs_new_contract is True
    assert s.contract_key == ""
    assert "밀어 넣지 않습니다" in s.reason


def test_known_kind_with_a_missing_contract_asks_for_a_new_one():
    """`PUB-01` 은 표에 있지만 키트에는 없다 — 그러면 새 계약 제안이다."""
    s = M.route("public_financials", known_contract_keys=KIT_CONTRACTS)
    assert s.contract_key == "PUB-01" and s.needs_new_contract is True


def test_route_all_separates_the_two_piles():
    routed, pending = M.route_all(["fx_rate", "public_financials", "임원보수"],
                                  known_contract_keys=KIT_CONTRACTS)
    assert [r.contract_key for r in routed] == ["EXT-01"]
    assert len(pending) == 2


def test_route_refuses_an_unknown_data_origin():
    with pytest.raises(am.AcquisitionStateError):
        M.route("fx_rate", known_contract_keys=KIT_CONTRACTS, data_origin="공개")


def test_derived_detail_uses_the_origin_not_a_separate_contract():
    """지시 5 마지막 줄 — 내부 상세 추정치는 **성격**으로 표시한다."""
    assert M.DERIVED_ORIGIN == am.ORIGIN_SYNTHETIC_DERIVED
    assert M.DERIVED_ORIGIN not in M.ROUTING_TABLE.values()


# ── ② 필드를 지어내지 않는다 ────────────────────────────────────────────────
def test_target_field_must_exist_in_the_contract():
    r = _validate([{"source": "thstrm_amount", "target": "revenue_krw"}])
    assert any("지어내지 않습니다" in p.reason for p in r.problems)


def test_source_field_must_exist_in_this_response():
    """원천에 없는 필드를 이으면 적재에서 빈 칸이 된다 — 매핑은 통과한 채로."""
    r = _validate([{"source": "없는필드", "target": "amount"}])
    assert any("원천에 없는 필드" in p.reason for p in r.problems)


def test_two_sources_cannot_share_one_target():
    r = _validate(FULL_MAPPING + [{"source": "prior_amount", "target": "amount"}])
    assert any("두 원천이 붙었습니다" in p.reason for p in r.problems)


def test_malformed_entries_are_reported_not_skipped():
    r = _validate([{"source": "", "target": "amount"}, "문자열", {"source": "x"}])
    assert len(r.problems) == 3


# ── ③ 단위 ──────────────────────────────────────────────────────────────────
def test_differing_units_without_a_rule_are_blocked():
    """★★★ 「대충 맞겠지」로 넘어간 환산은 나중에 자릿수로 돌아온다."""
    r = _validate([{"source": "thstrm_amount", "target": "amount",
                    "source_unit": "KRW/1000", "target_unit": "KRW"}])
    assert any("환산 규칙이 없습니다" in p.reason for p in r.problems)


def test_explicit_conversion_is_accepted_and_recorded():
    r = _validate([{"source": "thstrm_amount", "target": "amount",
                    "source_unit": "KRW/1000", "target_unit": "KRW",
                    "unit_conversion": {"factor": 1000, "note": "천원→원"}}])
    assert not any("환산" in p.reason for p in r.problems)
    assert r.conversions[0]["factor"] == 1000.0
    assert r.conversions[0]["note"] == "천원→원"


def test_same_units_with_a_conversion_is_a_contradiction():
    """둘 중 하나가 거짓말이다 — 통과시키면 어느 쪽이 틀렸는지 영영 모른다."""
    r = _validate([{"source": "thstrm_amount", "target": "amount",
                    "source_unit": "KRW", "target_unit": "KRW",
                    "unit_conversion": {"factor": 1000}}])
    assert any("단위가 같은데" in p.reason for p in r.problems)


def test_zero_or_unparseable_factor_is_not_a_rule():
    for bad in ({"factor": 0}, {"factor": "천배"}, {"note": "천원→원"}, "1000"):
        r = _validate([{"source": "thstrm_amount", "target": "amount",
                        "source_unit": "KRW/1000", "target_unit": "KRW",
                        "unit_conversion": bad}])
        assert any("환산 규칙이 없습니다" in p.reason for p in r.problems), bad


def test_nonsense_unit_text_is_refused():
    r = _validate([{"source": "currency", "target": "currency",
                    "source_unit": "원 단위(천원 기준)", "target_unit": "KRW",
                    "unit_conversion": {"factor": 1000}}])
    assert any("형식이 이상합니다" in p.reason for p in r.problems)


# ── ④ 사람 승인 ─────────────────────────────────────────────────────────────
def test_a_complete_mapping_is_ok_but_not_auto_appliable():
    """★★★ 형식이 맞다 ≠ 적용해도 된다."""
    r = _validate()
    assert r.ok is True
    assert r.unmapped_required == ()
    assert r.auto_appliable is False
    assert r.requires_human_approval == ("account_id → account_id",)


def test_account_mapping_always_needs_a_person():
    """형식 검사를 승인으로 읽으면 아무도 보지 않은 계정 대응으로 손익이 만들어진다."""
    r = _validate([{"source": "account_nm", "target": "account_nm"}] +
                  [m for m in FULL_MAPPING if m["target"] != "account_nm"])
    assert r.requires_human_approval


def test_mapping_without_accounts_can_be_auto_appliable():
    """반대 방향도 확인한다 — 사람 승인이 **언제나** 걸리면 그 표시는 뜻이 없다."""
    simple = {"dataset_id": "EXT-01", "dataset_name": "환율",
              "schema": {"fields": [
                  {"name": "indicator_code", "required": True},
                  {"name": "value", "required": True},
                  {"name": "published_at", "required": True},
                  {"name": "vintage_date", "required": True}]}}
    r = M.validate_mapping(
        [{"source": s, "target": s} for s in
         ("indicator_code", "value", "published_at", "vintage_date")],
        contract=simple,
        source_fields=["indicator_code", "value", "published_at", "vintage_date"])
    assert r.ok is True and r.auto_appliable is True


# ── 봉투와 시점 ─────────────────────────────────────────────────────────────
def test_common_envelope_is_system_assigned_not_the_mappings_job():
    """⚠️ 봉투를 미매핑으로 세면 어떤 매핑도 통과하지 못하고, 그러면 사람이 검사를 끈다.

    Provider 는 테넌트·범위를 모르는 것이 설계다 — 적용 시점에 씌운다."""
    r = _validate()
    assert set(r.system_assigned) == set(M.REQUIRED_COMMON_FIELDS)
    for f in M.REQUIRED_COMMON_FIELDS:
        assert f not in r.unmapped_required


def test_missing_temporal_fields_are_flagged():
    """★★★ 빠지면 「그 계획이 당시 어떤 발표값을 썼는가」에 답할 수 없다.

    `PUB-01` 에서 둘은 **필수**라 `unmapped_required` 로 잡힌다."""
    without = [m for m in FULL_MAPPING if m["target"] not in ("published_at", "vintage_date")]
    r = _validate(without)
    assert set(r.unmapped_required) >= {"published_at", "vintage_date"}
    assert r.ok is False


def test_optional_temporal_fields_are_still_flagged():
    """⚠️ 필수가 아니어도 짚는다 — 아니면 계약이 느슨할수록 재현성이 조용히 약해진다.

    필수 목록에 기대는 검사는 **필수가 아닌 계약에서 사라진다.** 이 시험이 그 자리를 지킨다."""
    loose = {"dataset_id": "EXT-09", "dataset_name": "느슨한 계약",
             "schema": {"fields": [{"name": "value", "required": True},
                                   {"name": "published_at", "required": False},
                                   {"name": "vintage_date", "required": False}]}}
    r = M.validate_mapping([{"source": "value", "target": "value"}], contract=loose,
                           source_fields=["value", "published_at", "vintage_date"])
    flagged = {p.target_field for p in r.problems if "시점 필드" in p.reason}
    assert flagged == {"published_at", "vintage_date"}


def test_missing_required_domain_fields_are_listed():
    r = _validate([m for m in FULL_MAPPING if m["target"] not in ("corp_code", "fs_div")])
    assert set(r.unmapped_required) >= {"corp_code", "fs_div"}
    assert r.ok is False


# ── ⑤ 새 계약 제안 ──────────────────────────────────────────────────────────
def test_pub01_is_a_proposal_not_an_approved_contract():
    """★★★ 인증된 키트를 몰래 바꾸지 않는다 — 사람이 승인해야 계약이 된다."""
    p = M.pub01_proposal()
    assert p["status"] == "PROPOSED"
    assert p["proposal"]["requires_human_approval"] is True
    #: 기존 35개는 `APPROVED_FOR_DEMO` 다 — 상태가 구별되어야 한다.
    for path in glob.glob("starter_kits/*/*/contracts/*.contract.json"):
        with open(path, encoding="utf-8") as f:
            assert json.load(f)["status"] != "PROPOSED", path


def test_pub01_does_not_exist_in_the_certified_kit_yet():
    """제안 단계에서 키트 파일이 생기면 「제안」과 「계약」의 구분이 사라진다."""
    assert glob.glob("starter_kits/*/*/contracts/PUB-01.contract.json") == []


def test_pub01_is_public_disclosed_and_not_for_management_decision():
    p = M.pub01_proposal()
    assert p["classification"]["data_origin"] == am.ORIGIN_PUBLIC_DISCLOSED
    assert p["classification"]["not_for_management_decision"] is True


def test_pub01_uses_the_same_envelope_as_the_existing_contracts():
    """새 계약이 다른 그릇이면 적재·준비도 판정이 이 계약만 다르게 다뤄야 한다."""
    p = M.pub01_proposal()
    names = [f["name"] for f in p["schema"]["fields"]]
    assert names[:len(M.REQUIRED_COMMON_FIELDS)] == list(M.REQUIRED_COMMON_FIELDS)
    assert p["quality"]["required_common_fields"] == list(M.REQUIRED_COMMON_FIELDS)
    assert p["quality"]["fail_closed_on_scope_missing"] is True
    with open(glob.glob("starter_kits/*/*/contracts/EXT-01.contract.json")[0],
              encoding="utf-8") as f:
        existing = json.load(f)
    assert set(p["scope"]) == set(existing["scope"])
    assert set(p["quality"]) == set(existing["quality"])


def test_pub01_states_why_the_existing_contract_does_not_fit():
    """이유 없는 새 계약은 곧 두 번째 정본이 된다."""
    rationale = M.pub01_proposal()["proposal"]["rationale"]
    assert "FIN-03" in rationale
    assert "내부 실적" in rationale


def test_pub01_is_deterministic():
    assert M.pub01_proposal() == M.pub01_proposal()


def test_proposal_requires_a_rationale_and_business_keys():
    with pytest.raises(M.MappingError):
        M.build_contract_proposal(dataset_id="XYZ-01", dataset_name="x", business_keys=["k"],
                                  domain_fields=[{"name": "k"}],
                                  data_origin=am.ORIGIN_PUBLIC_DISCLOSED, rationale="  ")
    with pytest.raises(M.MappingError):
        M.build_contract_proposal(dataset_id="XYZ-01", dataset_name="x", business_keys=[],
                                  domain_fields=[{"name": "k"}],
                                  data_origin=am.ORIGIN_PUBLIC_DISCLOSED, rationale="이유")


def test_proposal_refuses_a_business_key_that_is_not_a_field():
    """키가 필드에 없으면 「같은 행인지」 판정이 없는 열을 본다."""
    with pytest.raises(M.MappingError):
        M.build_contract_proposal(dataset_id="XYZ-01", dataset_name="x",
                                  business_keys=["missing_key"], domain_fields=[{"name": "k"}],
                                  data_origin=am.ORIGIN_PUBLIC_DISCLOSED, rationale="이유")


@pytest.mark.parametrize("bad", ["PUB01", "PUBLIC-01", "PUB-1", "P-01", "PUB-001", ""])
def test_proposal_key_shape_is_enforced(bad):
    with pytest.raises(M.MappingError):
        M.build_contract_proposal(dataset_id=bad, dataset_name="x", business_keys=["k"],
                                  domain_fields=[{"name": "k"}],
                                  data_origin=am.ORIGIN_PUBLIC_DISCLOSED, rationale="이유")


# ── 업무 키 ─────────────────────────────────────────────────────────────────
def test_lowercase_key_is_normalised_not_refused():
    """검사가 좁게 까다로우면 사람이 우회한다 — 대소문자는 고쳐 주고 모양만 강제한다."""
    p = M.build_contract_proposal(dataset_id="pub-02", dataset_name="x", business_keys=["k"],
                                  domain_fields=[{"name": "k"}],
                                  data_origin=am.ORIGIN_PUBLIC_DISCLOSED, rationale="이유")
    assert p["dataset_id"] == "PUB-02"


def test_business_key_makes_a_correction_a_different_row():
    """★★★ 접수번호를 빼면 정정 전후가 같은 키가 되어 하나가 다른 하나를 덮어쓴다."""
    base = {"rcept_no": "20260316000123", "fs_div": "CFS", "sj_div": "IS",
            "account_id": "ifrs-full_Revenue"}
    corrected = dict(base, rcept_no="20260520000999")
    assert M.disclosure_row_id(base) != M.disclosure_row_id(corrected)


def test_business_key_separates_consolidated_from_separate():
    base = {"rcept_no": "20260316000123", "fs_div": "CFS", "sj_div": "IS",
            "account_id": "ifrs-full_Revenue"}
    assert M.disclosure_row_id(base) != M.disclosure_row_id(dict(base, fs_div="OFS"))


def test_business_key_refuses_incomplete_rows():
    with pytest.raises(M.MappingError):
        M.disclosure_row_id({"fs_div": "CFS", "account_id": "x"})
    with pytest.raises(M.MappingError):
        M.disclosure_row_id({"rcept_no": "2026", "fs_div": "CFS", "account_id": ""})


def test_provider_output_field_names_match_the_proposed_contract():
    """★★★ 이름이 갈리면 매핑 검증은 통과하는데 **적재에서 빈 칸**이 된다.

    Provider 의 `normalize()` 가 실제로 내는 키와 계약 필드를 대조한다."""
    import os
    from core.external_intelligence.providers import base as B
    from core.external_intelligence.providers import opendart as od

    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "opendart",
                           "fnltt_2025_cfs_ok.json")
    with open(fixture, "rb") as f:
        payload = f.read()
    provider = od.OpenDartProvider(env={"AFS_OPENDART_API_KEY": "k" * 24},
                                   transport=lambda *a, **k: None)
    batch = provider.normalize(B.FetchResult(
        provider_id="OPENDART", dataset_ref="00126380:2025:11011:CFS", payload=payload,
        content_type="application/json", requested_url="", fetched_at="2026-09-05T00:00:00Z"))
    produced = {k for row in batch.rows for k in row if not k.startswith("_")}
    contract_fields = {f["name"] for f in M.pub01_proposal()["schema"]["fields"]}
    orphans = produced - contract_fields
    assert orphans == set(), f"Provider 가 내는데 계약에 없는 필드: {orphans}"
