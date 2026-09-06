"""[DAO-5] 자연어 요청의 결정론적 관문 — **LLM 은 제안하고, 여기서 판정한다.**

이 파일이 막는 것 넷.

  ① LLM 이 조직 범위·신뢰등급·무제한권한을 **스스로 부여**하는 것.
  ② 목록 밖의 원천·계약·자료성격이 통과하는 것.
  ③ 빈 값이 **「전부」로 넓어지는** 것.
  ④ 내부 원문 레코드가 **LLM 프롬프트에 실려 나가는** 것.
"""
import json

import pytest

from core.external_intelligence import acquisition_models as am
from core.external_intelligence import request_interpreter as ri
from core.external_intelligence.providers import ProviderDescriptor

KNOWN_PROVIDERS = ["OPENDART", "ECOS"]
KNOWN_CONTRACTS = ["PUB-01", "EXT-01", "EXT-02", "FIN-03"]

GOOD = {
    "subject_name": "LS MnM", "purpose": "원료구매·손익 시뮬레이션",
    "period_from": "2016", "period_to": "2025",
    "indicators": ["매출", "영업이익", "현금흐름"],
    "target_contract_keys": ["PUB-01"], "provider_ids": ["OPENDART"],
    "frequency": "annual", "data_origin": am.ORIGIN_PUBLIC_DISCLOSED,
    "refresh_frequency": "연 1회",
    "excluded_providers": [{"provider_id": "ECOS", "reason": "회사 단위 재무를 주지 않음"}],
}


def _validate(proposal=None, **over):
    kwargs = dict(known_provider_ids=KNOWN_PROVIDERS, known_contract_keys=KNOWN_CONTRACTS,
                  scope_node_id="LS_MNM", purpose_kind="scenario", now_year=2026)
    kwargs.update(over)
    return ri.validate_proposal(dict(GOOD, **(proposal or {})), **kwargs)


def _fields(result):
    return {p.field for p in result.problems}


# ── 통과 ─────────────────────────────────────────────────────────────────────
def test_a_well_formed_proposal_becomes_a_structured_request():
    r = _validate()
    assert r.ok and r.problems == ()
    assert r.request.subject_name == "LS MnM"
    assert (r.request.period_from, r.request.period_to) == ("2016", "2025")
    assert r.request.target_contract_keys == ("PUB-01",)


def test_excluded_sources_keep_their_reason():
    """지시 3 — 「선택하지 않은 원천과 제외 사유」."""
    r = _validate()
    assert r.request.extras["excluded_providers"] == [
        {"provider_id": "ECOS", "reason": "회사 단위 재무를 주지 않음"}]


def test_exclusions_without_a_reason_are_discarded():
    """사유 없는 제외는 화면이 「이 원천은 왜 안 보이나」에 답할 수 없다."""
    r = _validate({"excluded_providers": [{"provider_id": "ECOS"}, {"reason": "그냥"}]})
    assert r.request.extras["excluded_providers"] == []


def test_reversed_period_is_corrected_not_rejected():
    r = _validate({"period_from": "2025", "period_to": "2016"})
    assert r.ok and (r.request.period_from, r.request.period_to) == ("2016", "2025")


# ── ① LLM 이 정할 수 없는 것 ────────────────────────────────────────────────
def test_proposal_cannot_widen_its_own_scope():
    """★★★ 이것을 제안에서 받으면 「범위를 넓혀 달라」는 문장 한 줄로 남의 부서가 열린다."""
    r = _validate({"scope_node_id": "BATTERY_DIV", "tenant_id": "other_tenant"})
    assert r.ok is True                       # 제안은 통과하되
    assert r.resolved_scope_node_id == "LS_MNM"   # 범위는 서버 값이다
    assert r.request.extras["scope_node_id"] == "LS_MNM"
    assert {o.field for o in r.overridden} >= {"scope_node_id", "tenant_id"}


def test_proposal_cannot_grant_itself_unrestricted_access():
    r = _validate({"unrestricted": True})
    assert "unrestricted" in {o.field for o in r.overridden}
    assert "unrestricted" not in r.request.extras


def test_proposal_cannot_lower_the_required_grade():
    """★ 등급은 **용도**가 정한다 — 출처보다 값이 더 신뢰될 수 없듯, 제안이 정책보다 셀 수 없다."""
    r = _validate({"required_grade": "bronze", "trust_grade": "bronze"})
    assert r.required_grade == "silver"        # purpose_kind="scenario" 의 정책값
    assert r.request.required_grade == "silver"
    assert {o.field for o in r.overridden} >= {"required_grade", "trust_grade"}


def test_grade_comes_from_the_existing_policy_table():
    """★★★ 두 번째 등급표를 만들지 않는다 — `PURPOSE_MIN_GRADE` 하나를 읽는다."""
    from core.external_intelligence import PURPOSE_MIN_GRADE
    for purpose_kind, expected in PURPOSE_MIN_GRADE.items():
        assert _validate(purpose_kind=purpose_kind).required_grade == expected


def test_unknown_purpose_kind_is_refused():
    r = _validate(purpose_kind="아무거나")
    assert r.ok is False and "purpose_kind" in _fields(r)


def test_overrides_are_reported_so_the_screen_can_explain_them():
    """사용자가 「왜 내가 쓴 대로 안 됐나」를 물으면 답이 있어야 한다."""
    r = _validate({"scope_node_id": "X"})
    assert r.overridden
    assert all(o.reason for o in r.overridden)
    assert all(o.got for o in r.overridden)


# ── ② 목록 밖 ───────────────────────────────────────────────────────────────
def test_unregistered_provider_is_refused():
    r = _validate({"provider_ids": ["SCRAPER_X"]})
    assert r.ok is False and "provider_ids" in _fields(r)


def test_unknown_contract_key_is_refused_rather_than_forced():
    """지시 5 — 의미가 다르면 억지로 연결하지 말고 **새 계약을 제안**한다."""
    r = _validate({"target_contract_keys": ["ZZZ-99"]})
    assert r.ok is False
    problem = next(p for p in r.problems if p.field == "target_contract_keys")
    assert "새 계약" in problem.reason


def test_unknown_data_origin_is_refused():
    r = _validate({"data_origin": "공개자료"})
    assert r.ok is False and "data_origin" in _fields(r)


def test_external_data_cannot_be_labelled_as_internal_actual():
    """★★★ 외부에서 받아 온 값을 `REAL` 로 적으면 상세 계산의 근거가 조용히 바뀐다."""
    r = _validate({"data_origin": am.ORIGIN_REAL})
    assert r.ok is False
    problem = next(p for p in r.problems if p.field == "data_origin")
    assert am.ORIGIN_PUBLIC_DISCLOSED in problem.reason


def test_public_and_derived_origins_are_allowed():
    for origin in (am.ORIGIN_PUBLIC_DISCLOSED, am.ORIGIN_SYNTHETIC,
                   am.ORIGIN_SYNTHETIC_DERIVED):
        assert _validate({"data_origin": origin}).ok is True


# ── ③ 빈 값이 범위를 넓히지 않는다 ──────────────────────────────────────────
def test_empty_period_is_an_error_not_all_time():
    """⚠️ 빈 값은 «지정 안 함»이지 «제한 없음»이 아니다."""
    r = _validate({"period_from": "", "period_to": ""})
    assert r.ok is False
    problem = next(p for p in r.problems if p.field == "period")
    assert "전 기간" in problem.reason


def test_missing_subject_or_purpose_is_refused():
    assert "subject_name" in _fields(_validate({"subject_name": "  "}))
    assert "purpose" in _fields(_validate({"purpose": ""}))


def test_period_is_bounded():
    r = _validate({"period_from": "1985", "period_to": "2025"})
    assert r.ok is False and "period" in _fields(r)


def test_future_year_is_a_bad_request_not_a_missing_dataset():
    """아직 오지 않은 해를 요청하면 「자료 없음」이 아니라 요청이 틀린 것이다."""
    r = _validate({"period_to": "2030"})
    assert r.ok is False and "period_to" in _fields(r)


def test_indicator_count_is_bounded():
    r = _validate({"indicators": [f"지표{i}" for i in range(ri.MAX_INDICATORS + 1)]})
    assert r.ok is False and "indicators" in _fields(r)


def test_duplicate_entries_are_folded():
    r = _validate({"indicators": ["매출", "매출", " 매출 ", "영업이익"]})
    assert r.request.indicators == ("매출", "영업이익")


# ── 내부 ID 노출 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("value", [
    "prj_4bf43a310aca691a32ce", "dst_0123456789abcdef0123",
    "회사 prj_4bf43a310aca691a32ce 의 자료", "daq_07d1d9d4e93f44989802",
])
def test_internal_ids_in_human_fields_are_refused(value):
    """지시 1 — 사람은 이름을 고르고 ID 는 시스템이 붙인다.

    ⚠️ 사람용 칸에 내부 ID 가 오는 것은 **화면이 ID 를 노출하고 있다는 신호**다.
      고지문으로는 막히지 않으므로 관문에서 거부한다."""
    r = _validate({"subject_name": value})
    assert r.ok is False and "subject_name" in _fields(r)


def test_normal_names_with_underscores_still_pass():
    """검사가 넓으면 정상 이름까지 막는다 — 그러면 사람이 검사를 끄게 된다."""
    assert _validate({"subject_name": "LS_MnM 배터리소재"}).ok is True
    assert _validate({"subject_name": "abc_1234"}).ok is True


# ── ④ LLM 에게 원문을 보내지 않는다 ─────────────────────────────────────────
def _descriptor():
    return ProviderDescriptor(
        provider_id="OPENDART", name="OpenDART", publisher="금융감독원", source_type="API",
        allowed_hosts=("opendart.fss.or.kr",), license_url="https://x/terms",
        allowed_usage="내부 분석", redistribution_allowed=False, requires_credential=True,
        credential_env="AFS_OPENDART_API_KEY", cost="무료", default_trust_grade="gold",
        refresh_frequency="연 1회", coverage_note="정기보고서", target_contract_keys=("PUB-01",),
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED, known_limits=("내부 실적을 대체하지 않습니다.",))


#: 계약 딕셔너리에 **실제 값이 섞여 있는** 경우를 일부러 만든다.
CONTRACT_WITH_DATA = {
    "dataset_id": "PUB-01", "dataset_name": "공개 재무실적",
    "schema": {"fields": [{"name": "amount", "type": "number", "description": "금액"},
                          {"name": "corp_code", "type": "string", "description": "법인코드"}]},
    "samples": [{"amount": 10500000000, "corp_code": "00126380"}],
    "rows": [{"amount": 999999999, "corp_code": "SECRET_CORP"}],
    "preview_text": "매출 10,500,000,000원",
}


def test_catalog_view_carries_field_names_not_values():
    """★★★ 「요약이니까 괜찮다」로 시작해 값이 섞여 들어가는 것을 막는다.

    이 함수가 **값을 만질 수 있는 자리 자체를 갖지 않아야** 한다."""
    view = ri.build_catalog_view(descriptors=[_descriptor()], contracts=[CONTRACT_WITH_DATA])
    blob = json.dumps(view, ensure_ascii=False)
    assert "amount" in blob and "corp_code" in blob        # 필드명은 있고
    for leaked in ("10500000000", "10,500,000,000", "SECRET_CORP", "999999999", "00126380"):
        assert leaked not in blob, leaked                   # 값은 없다


def test_prompt_carries_the_catalog_and_nothing_from_the_records():
    view = ri.build_catalog_view(descriptors=[_descriptor()], contracts=[CONTRACT_WITH_DATA])
    prompt = ri.build_prompt("최근 10년 LS MnM 재무실적을 모아줘", view)
    assert "LS MnM" in prompt
    for leaked in ("SECRET_CORP", "10500000000", "999999999"):
        assert leaked not in prompt, leaked


def test_prompt_does_not_ask_for_values_the_server_decides():
    """⚠️ 물으면 답이 오고, 답이 오면 언젠가 그 답을 쓰게 된다."""
    view = ri.build_catalog_view(descriptors=[_descriptor()], contracts=[CONTRACT_WITH_DATA])
    prompt = ri.build_prompt("요청", view)
    for banned in ("scope_node_id", "tenant_id", "required_grade", "unrestricted"):
        assert f'"{banned}"' not in prompt, banned


def test_prompt_lists_only_known_data_origins():
    view = ri.build_catalog_view(descriptors=[_descriptor()], contracts=[CONTRACT_WITH_DATA])
    prompt = ri.build_prompt("요청", view)
    for origin in am.DATA_ORIGINS:
        assert origin in prompt


def test_catalog_view_includes_the_limits_the_user_must_see():
    view = ri.build_catalog_view(descriptors=[_descriptor()], contracts=[CONTRACT_WITH_DATA])
    card = view["providers"][0]
    assert card["known_limits"] == ["내부 실적을 대체하지 않습니다."]
    assert card["redistribution_allowed"] is False
    assert card["allowed_usage"] == "내부 분석"


# ── 응답 읽기 ───────────────────────────────────────────────────────────────
def test_proposal_is_read_leniently_but_judged_strictly():
    """LLM 이 코드펜스·군더더기를 붙여도 읽는다 — 그러나 판정은 느슨해지지 않는다."""
    text = "네, 정리했습니다.\n```json\n" + json.dumps(
        {"subject_name": "LS MnM", "provider_ids": ["SCRAPER_X"]}, ensure_ascii=False) + "\n```"
    parsed = ri.parse_proposal(text)
    assert parsed["subject_name"] == "LS MnM"
    r = ri.validate_proposal(parsed, known_provider_ids=KNOWN_PROVIDERS,
                             known_contract_keys=KNOWN_CONTRACTS, scope_node_id="LS_MNM")
    assert r.ok is False
    assert {"provider_ids", "purpose", "period"} <= _fields(r)


def test_unparseable_response_yields_an_empty_proposal_not_a_crash():
    assert ri.parse_proposal("죄송합니다, 잘 모르겠습니다.") == {}
    assert ri.parse_proposal("") == {}
    assert ri.parse_proposal("[1,2,3]") == {}


def test_empty_proposal_is_refused_with_readable_problems():
    r = ri.validate_proposal({}, known_provider_ids=KNOWN_PROVIDERS,
                             known_contract_keys=KNOWN_CONTRACTS, scope_node_id="LS_MNM")
    assert r.ok is False
    assert {"subject_name", "purpose", "period"} <= _fields(r)
    assert all(p.reason for p in r.problems)
