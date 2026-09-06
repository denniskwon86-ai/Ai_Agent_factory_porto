"""[DAO-3] OpenDART Provider — **공식 응답 모양의 fixture 로 종단까지** 검증한다.

★★★ 이 파일은 네트워크를 한 번도 쓰지 않는다. 실제 API 키가 없어도 여기까지 통과해야
  하고, 통과했다고 해서 **「실제 DART 수집 완료」로 기록하지 않는다**(지시 10).

이 파일이 지키는 것 다섯.

  ① 장애와 「자료 없음」이 다른 길로 간다.
  ② 연결(CFS)·별도(OFS)·회사·연도가 섞이지 않는다.
  ③ 정정공시가 앞의 판을 **지우지 않는다**.
  ④ 미래 발표값이 과거 계획에 새지 않는다.
  ⑤ 결손이 0 으로 바뀌지 않는다.
"""
import json
import os

import pytest

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import opendart as od

KEY = "dartkey0123456789abcdef01234567"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "opendart")


def _transport(mapping):
    def call(url, *, allowed_hosts, timeout=20.0):
        for marker, (name, ctype) in mapping.items():
            if marker in url:
                with open(os.path.join(FIX, name), "rb") as f:
                    return {"body": f.read(), "content_type": ctype, "status": 200,
                            "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}
        raise AssertionError(f"fixture 에 없는 URL 을 불렀다: {url}")
    return call


def _provider(financial="fnltt_2025_cfs_ok.json", corp="corp_code.zip", env=None):
    return od.OpenDartProvider(
        env={"AFS_OPENDART_API_KEY": KEY} if env is None else env,
        transport=_transport({"corpCode.xml": (corp, "application/zip"),
                              "fnlttSinglAcntAll": (financial, "application/json")}))


def _request(**over):
    base = dict(subject_name="LS MnM", purpose="원료구매·손익 시뮬레이션",
                period_from="2025", period_to="2025", extras={"fs_div": "CFS"})
    base.update(over)
    return B.AcquisitionRequest(**base)


def _batch(financial="fnltt_2025_cfs_ok.json", corp="corp_code.zip"):
    p = _provider(financial, corp)
    return p, p.normalize(p.fetch(p.discover(_request())[0]))


# ── 원천 카드 ────────────────────────────────────────────────────────────────
def test_descriptor_targets_a_new_contract_not_the_internal_ledger():
    """★★★ 지시 5 — 공시 재무제표를 내부 회계 계약(FIN-03)에 밀어 넣지 않는다."""
    d = od.OpenDartProvider.descriptor
    assert d.target_contract_keys == (od.CONTRACT_KEY,)
    assert od.CONTRACT_KEY == "PUB-01"
    assert "FIN-03" not in d.target_contract_keys


def test_descriptor_marks_the_origin_as_public_not_internal_actual():
    d = od.OpenDartProvider.descriptor
    assert d.data_origin == am.ORIGIN_PUBLIC_DISCLOSED
    assert d.data_origin not in am.ORIGINS_FOR_INTERNAL_ACTUAL


def test_descriptor_states_the_limit_that_matters():
    """「내부 실적을 대체하지 않는다」가 카드에 있어야 화면까지 간다."""
    limits = " ".join(od.OpenDartProvider.descriptor.known_limits)
    assert "대체하지 않습니다" in limits
    assert "CFS" in limits and "OFS" in limits


def test_provider_is_registered():
    from core.external_intelligence import providers as P
    assert "OPENDART" in P.provider_registry.ids()


# ── ① 장애와 자료 없음 ───────────────────────────────────────────────────────
def test_no_data_is_not_an_error(monkeypatch):
    """★★★ status=013 은 **정상 응답**이다. 예외로 던지면 스케줄러가 영원히 재시도한다."""
    p = _provider("fnltt_no_data.json")
    with pytest.raises(od.NoDataFromSource):
        p.fetch(p.discover(_request())[0])


def test_no_data_is_a_distinct_exception_from_status_failures():
    assert not issubclass(od.OpenDartStatusError, od.NoDataFromSource)
    assert not issubclass(od.NoDataFromSource, od.OpenDartStatusError)


@pytest.mark.parametrize("fixture,status,kind,state", [
    ("fnltt_bad_key.json", "010", am.FAILURE_AUTH, am.FAILED),
    ("fnltt_rate_limited.json", "020", am.FAILURE_TRANSPORT, am.FAILED),
])
def test_status_codes_map_to_the_right_failure_and_state(fixture, status, kind, state):
    p = _provider(fixture)
    with pytest.raises(od.OpenDartStatusError) as exc:
        p.fetch(p.discover(_request())[0])
    assert exc.value.status == status
    assert exc.value.failure_kind == kind
    assert am.state_for_failure(exc.value.failure_kind) == state


def test_every_known_status_maps_to_a_known_failure_kind():
    """표에 있는 값이 목록 밖을 가리키면 상태 결정이 예외로 죽는다."""
    for status, kind in od.STATUS_FAILURE_KIND.items():
        assert kind in am.FAILURE_KINDS, status
    assert od.STATUS_NO_DATA not in od.STATUS_FAILURE_KIND
    assert od.STATUS_OK not in od.STATUS_FAILURE_KIND


def test_unknown_status_is_treated_as_transport_not_as_success():
    """모르는 코드를 성공으로 접으면 오류 본문이 계약 모양으로 옮겨진다."""
    with pytest.raises(od.OpenDartStatusError) as exc:
        od._check_status({"status": "777", "message": "처음 보는 코드"})
    assert exc.value.failure_kind == am.FAILURE_TRANSPORT


def test_non_json_response_is_schema_drift_not_a_crash():
    with pytest.raises(od.OpenDartStatusError) as exc:
        od._load_json("<html>점검 중</html>".encode("utf-8"))
    assert exc.value.failure_kind == am.FAILURE_SCHEMA_DRIFT


# ── ② 섞이지 않는다 ─────────────────────────────────────────────────────────
def test_separate_statements_are_dropped_when_consolidated_was_requested():
    """★★★ 한 회사의 같은 해 매출이 두 개 있고 뜻이 다르다. 섞이면 합계가 조용히 틀린다."""
    _, batch = _batch()
    assert {r["fs_div"] for r in batch.rows} == {"CFS"}
    reasons = [r.reason for r in batch.rejected]
    assert "연결/별도 구분 불일치" in reasons


def test_rows_from_another_company_are_rejected_with_a_reason():
    """⚠️ 실측으로 뚫렸던 자리 — 요청 corp_code 와 다른 응답이 그대로 통과했다."""
    p, batch = _batch("fnltt_wrong_company.json")
    assert batch.rows == ()
    assert len(batch.rejected) == 2
    assert batch.rejected[0].reason == "회사 불일치"
    assert "00888888" in batch.rejected[0].detail
    report = p.validate(batch)
    assert report.ok is False
    assert am.state_for_failure(report.worst_failure_kind()) == am.QUARANTINED


def test_validation_names_single_company_year_currency_and_fs_div():
    _, batch = _batch()
    names = [c.name for c in _provider().validate(batch).checks]
    for expected in ("회사 단일", "사업연도 단일", "통화 단일", "연결/별도 단일"):
        assert expected in names


def test_unknown_fs_div_or_report_code_is_refused_before_any_call():
    p = _provider()
    with pytest.raises(B.ProviderError):
        p.discover(_request(extras={"fs_div": "BOTH"}))
    with pytest.raises(B.ProviderError):
        p.discover(_request(extras={"fs_div": "CFS", "reprt_code": "99999"}))


# ── 회사 식별 ────────────────────────────────────────────────────────────────
def test_user_never_supplies_the_internal_corp_code():
    """지시 1 — 사람은 회사명을 쓰고 내부 식별자는 시스템이 찾는다."""
    p = _provider()
    candidates = p.discover(_request())
    assert candidates
    assert candidates[0].params["corp_code"] == "00126380"
    assert "corp_code" in candidates[0].match_reason


def test_ambiguous_company_names_are_reported_not_silently_chosen():
    """같은 이름이 여럿이면 고른 것과 **못 고른 것**을 함께 알린다."""
    p = _provider(corp="corp_code_ambiguous.zip")
    candidates = p.discover(_request(subject_name="대한제련"))
    assert candidates[0].ambiguous_with == ("대한제련(00555002)",)


def test_listed_company_is_preferred_when_names_tie():
    p = _provider(corp="corp_code_ambiguous.zip")
    #: 상장(stock_code 있음)을 앞에 둔다 — 같은 이름의 비상장 계열사가 흔하다.
    assert p.discover(_request(subject_name="대한제련"))[0].params["corp_code"] == "00126380"


def test_unknown_company_returns_no_candidates_rather_than_raising():
    """「없다」는 예외가 아니다 — 탐색이 빈손인 것도 결과다."""
    assert _provider().discover(_request(subject_name="없는회사")) == []
    assert _provider().discover(_request(subject_name="")) == []


def test_company_name_folding_ignores_corporate_suffixes():
    assert od._fold("(주)엘에스엠앤엠") == od._fold("엘에스엠앤엠")
    assert od._fold("LS MnM") == od._fold("ls-mnm")


def test_period_range_is_bounded():
    p = _provider()
    assert len(p.discover(_request(period_from="2016", period_to="2025"))) == 10
    with pytest.raises(B.ProviderError):
        p.discover(_request(period_from="1900", period_to="2025"))


# ── ③ 정정공시 ──────────────────────────────────────────────────────────────
def test_correction_supersedes_without_deleting_the_earlier_filing():
    """★★★ 옛 판을 지우면 「그 계획이 당시 어떤 발표값을 썼는가」에 답할 수 없다."""
    _, batch = _batch("fnltt_corrected.json")
    current, superseded = od.resolve_supersessions(batch.rows)
    assert len(current) == 1 and len(superseded) == 1
    assert current[0]["rcept_no"] == "20260520000999"
    assert current[0]["amount"] == 10320000000.0
    #: 앞의 판은 **남아 있다** — 상태만 바뀐다.
    assert superseded[0]["rcept_no"] == "20260316000123"
    assert superseded[0]["amount"] == 10500000000.0
    assert superseded[0]["quality_status"] == "SUPERSEDED"
    assert superseded[0]["superseded_by_rcept_no"] == "20260520000999"


def test_supersession_conserves_every_row():
    _, batch = _batch("fnltt_corrected.json")
    current, superseded = od.resolve_supersessions(batch.rows)
    assert len(current) + len(superseded) == len(batch.rows)


def test_supersession_uses_the_quality_status_vocabulary_that_already_exists():
    """새 어휘를 만들지 않는다 — `external_intelligence.QUALITY_STATUS` 에 이미 있다."""
    from core import external_intelligence as ei
    _, batch = _batch("fnltt_corrected.json")
    current, superseded = od.resolve_supersessions(batch.rows)
    assert superseded[0]["quality_status"] in ei.QUALITY_STATUS
    assert current[0]["quality_status"] in ei.QUALITY_STATUS


# ── ④ 미래 발표값 ───────────────────────────────────────────────────────────
def test_future_disclosures_are_excluded_from_an_earlier_as_of():
    """2026-03 계획에 2026-05 정정값이 섞이면 재현이 아니라 사후 보정이다."""
    _, batch = _batch("fnltt_corrected.json")
    kept, leaked = od.drop_future_disclosures(batch.rows, "2026-04-01")
    assert [r["published_at"] for r in kept] == ["2026-03-16"]
    assert [r["published_at"] for r in leaked] == ["2026-05-20"]


def test_no_as_of_keeps_everything_rather_than_silently_filtering():
    _, batch = _batch("fnltt_corrected.json")
    kept, leaked = od.drop_future_disclosures(batch.rows, "")
    assert len(kept) == len(batch.rows) and leaked == ()


def test_published_at_comes_from_the_receipt_number_not_from_today():
    """★★★ 발표일을 「받은 날」로 채우면 §12.5 의 재현성이 조용히 깨진다."""
    assert od.published_at_from_rcept_no("20260316000123") == "2026-03-16"
    assert od.published_at_from_rcept_no("") == ""
    assert od.published_at_from_rcept_no("이상한값") == ""


def test_vintage_equals_published_at():
    _, batch = _batch()
    for row in batch.rows:
        assert row["vintage_date"] == row["published_at"] == "2026-03-16"


# ── ⑤ 결손을 0 으로 만들지 않는다 ───────────────────────────────────────────
def test_unreadable_amount_becomes_none_not_zero():
    """★★★ 0 은 결손보다 나쁘다 — 결손은 보이지만 0 은 계산에 섞인다."""
    assert od.parse_amount("-") is None
    assert od.parse_amount("") is None
    assert od.parse_amount("해당사항없음") is None
    assert od.parse_amount("0") == 0.0          # 진짜 0 은 0 이다
    assert od.parse_amount("10,500,000,000") == 10500000000.0
    assert od.parse_amount("(150,000,000)") == -150000000.0


def test_missing_amounts_survive_normalization_as_none():
    _, batch = _batch()
    nulls = [r for r in batch.rows if r["amount"] is None]
    assert len(nulls) == 1
    assert nulls[0]["account_nm"] == "매출총이익"


def test_validation_counts_missing_amounts_visibly():
    p, batch = _batch()
    check = next(c for c in p.validate(batch).checks if c.name == "금액 결손 표시")
    assert check.count == 1
    assert "0 이 아니라" in check.detail


# ── 정산·순수성 ─────────────────────────────────────────────────────────────
def test_every_source_row_is_either_loaded_or_rejected_with_a_reason():
    _, batch = _batch()
    assert batch.accounted is True
    assert batch.source_row_count == len(batch.rows) + len(batch.rejected)
    assert all(r.reason for r in batch.rejected)


def test_pure_methods_do_not_touch_the_network():
    """★★★ fixture 만으로 종단 검증이 되려면 이 넷이 순수해야 한다."""
    def explode(url, *, allowed_hosts, timeout=20.0):
        raise AssertionError("네트워크를 만졌다")

    _, batch = _batch()
    p = od.OpenDartProvider(env={"AFS_OPENDART_API_KEY": KEY}, transport=explode)
    report = p.validate(batch)
    cp = p.checkpoint(batch)
    nxt = p.refresh(cp)
    assert report.checks and cp.provider_id == "OPENDART"
    assert nxt[0].params["bsns_year"] == "2026"


def test_refresh_advances_one_period_from_the_checkpoint():
    p, batch = _batch()
    cp = p.checkpoint(batch)
    assert cp.covered_from == cp.covered_to == "2025"
    assert cp.cursor == "20260316000123"
    assert p.refresh(cp)[0].dataset_ref == "00126380:2026:11011:CFS"


def test_refresh_on_an_empty_checkpoint_returns_nothing():
    p = _provider()
    assert p.refresh(B.Checkpoint(provider_id="OPENDART", dataset_ref="")) == []


# ── 자격증명 ─────────────────────────────────────────────────────────────────
def test_api_key_never_appears_in_the_fetch_result():
    p = _provider()
    result = p.fetch(p.discover(_request())[0])
    assert KEY not in result.requested_url
    assert "corp_code=00126380" in result.requested_url


def test_missing_key_names_the_environment_variable():
    p = _provider(env={})
    with pytest.raises(B.ProviderCredentialError) as exc:
        p.discover(_request())
    assert "AFS_OPENDART_API_KEY" in str(exc.value)


def test_fetch_refuses_a_candidate_that_did_not_come_from_discover():
    p = _provider()
    with pytest.raises(B.ProviderError):
        p.fetch(B.DiscoveryCandidate(provider_id="OPENDART", dataset_ref="x",
                                     title="", target_contract_key=od.CONTRACT_KEY))


# ── corpCode ZIP ────────────────────────────────────────────────────────────
def test_corp_code_zip_is_parsed_explicitly_not_by_a_loose_parser():
    with open(os.path.join(FIX, "corp_code.zip"), "rb") as f:
        rows = od.parse_corp_code_zip(f.read())
    assert len(rows) == 3
    assert {"corp_code", "corp_name", "stock_code", "modify_date"} <= set(rows[0])


def test_non_zip_corp_code_response_is_schema_drift():
    with pytest.raises(od.OpenDartStatusError) as exc:
        od.parse_corp_code_zip(b"not a zip at all")
    assert exc.value.failure_kind == am.FAILURE_SCHEMA_DRIFT
