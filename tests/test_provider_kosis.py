"""[DAO-13] KOSIS Provider — **세 번째 원천이 앞의 둘과 또 다른가.**

이 파일이 지키는 것 다섯.

  ① 성공 응답이 **배열**이고 오류가 객체인 것을 명시적으로 가른다.
  ② 「자료 없음」이 **코드가 아니라 빈 배열**로 온다 — 0건을 적재 성공으로 읽지 않는다.
  ③ 모르는 오류 코드를 **성공으로 접지 않는다**(코드표가 실측 미확인이므로 특히 중요).
  ④ 분류축이 섞이면 서로 다른 계열이 한 지표로 뭉친다 — 버린다.
  ⑤ **항상 실패하는 검사를 두지 않는다** — 그러면 정상 자료가 늘 격리된다.
"""
import json
import os

import pytest

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import kosis as K

KEY = "kosiskey0123456789abcdef"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "kosis")


def _transport(name="production_index_2025.json"):
    def call(url, *, allowed_hosts, timeout=20.0):
        with open(os.path.join(FIX, name), "rb") as f:
            return {"body": f.read(), "content_type": "application/json", "status": 200,
                    "final_url": url, "fetched_at": "2026-09-08T00:00:00+00:00"}
    return call


def _provider(name="production_index_2025.json", env=None):
    return K.KosisProvider(env={"AFS_KOSIS_API_KEY": KEY} if env is None else env,
                           transport=_transport(name))


def _request(**over):
    base = dict(subject_name="LS MnM", purpose="업종 경기 기준선",
                indicators=("생산지수",), period_from="2025", period_to="2025")
    base.update(over)
    return B.AcquisitionRequest(**base)


def _candidate():
    return _provider().discover(_request())[0]


def _batch(name="production_index_2025.json"):
    p = _provider(name)
    return p, p.normalize(p.fetch(_candidate()))


# ── 원천 카드 ────────────────────────────────────────────────────────────────
def test_registered_alongside_the_other_two():
    from core.external_intelligence import providers as P
    import core.external_intelligence.providers.ecos  # noqa: F401
    import core.external_intelligence.providers.opendart  # noqa: F401
    assert {"KOSIS", "ECOS", "OPENDART"} <= set(P.provider_registry.ids())


def test_targets_ext03_per_the_routing_table():
    from core.external_intelligence import mapping as M
    assert K.KosisProvider.descriptor.target_contract_keys == ("EXT-03",)
    assert M.ROUTING_TABLE["industry_indicator"] == "EXT-03"


def test_limits_say_it_is_not_our_own_plant():
    """★ 산업 지수를 우리 가동률로 읽으면 계획이 조용히 틀린다."""
    limits = " ".join(K.KosisProvider.descriptor.known_limits)
    assert "우리 공장의 가동률" in limits
    assert "축을 섞으면" in limits
    assert "실측으로 확인되지 않았습니다" in limits


# ── ① 응답 모양을 명시적으로 가른다 ────────────────────────────────────────
def test_success_is_an_array_error_is_an_object():
    """★★★ DART 는 `{status}`, ECOS 는 `{StatisticSearch}`, KOSIS 는 **배열**이다."""
    rows = K.load_rows(json.dumps([{"PRD_DE": "202501", "DT": "1"}]).encode("utf-8"))
    assert rows == [{"PRD_DE": "202501", "DT": "1"}]
    with pytest.raises(K.KosisErrorResponse):
        K.load_rows(json.dumps({"err": "20", "errMsg": "x"}).encode("utf-8"))


def test_an_object_without_err_is_schema_drift():
    """모양이 예상 밖이면 «성공» 이 아니라 표류다."""
    with pytest.raises(K.KosisErrorResponse) as exc:
        K.load_rows(json.dumps({"whatever": 1}).encode("utf-8"))
    assert exc.value.failure_kind == am.FAILURE_SCHEMA_DRIFT


def test_html_is_schema_drift_not_a_crash():
    with pytest.raises(K.KosisErrorResponse) as exc:
        K.load_rows("<html>점검</html>".encode("utf-8"))
    assert exc.value.failure_kind == am.FAILURE_SCHEMA_DRIFT


def test_other_providers_responses_do_not_pass_this_parser():
    """지시 4 — 느슨한 범용 파서를 만들지 않는다."""
    dart = os.path.join(os.path.dirname(__file__), "fixtures", "opendart",
                        "fnltt_2025_cfs_ok.json")
    ecos = os.path.join(os.path.dirname(__file__), "fixtures", "ecos",
                        "search_fx_2025.json")
    for path in (dart, ecos):
        with open(path, "rb") as f:
            with pytest.raises(K.KosisErrorResponse):
                K.load_rows(f.read())


# ── ② 「자료 없음」이 모양으로 온다 ─────────────────────────────────────────
def test_empty_array_is_no_data_not_zero_rows_loaded():
    """★★★ 코드 표만 보는 판정기는 이것을 놓치고 **0건을 적재 성공**으로 읽는다."""
    with pytest.raises(K.NoDataFromSource):
        K.load_rows(b"[]")


def test_no_data_reaches_the_right_state():
    p = _provider("empty.json")
    with pytest.raises(K.NoDataFromSource):
        p.fetch(_candidate())


def test_no_data_is_a_distinct_exception():
    assert not issubclass(K.KosisErrorResponse, K.NoDataFromSource)
    assert not issubclass(K.NoDataFromSource, K.KosisErrorResponse)


# ── ③ 모르는 코드를 성공으로 접지 않는다 ────────────────────────────────────
@pytest.mark.parametrize("fixture,code,kind", [
    ("err_auth.json", "20", am.FAILURE_AUTH),
    ("err_quota.json", "22", am.FAILURE_TRANSPORT),
    ("err_param.json", "100", am.FAILURE_SCHEMA_DRIFT),
    ("err_server.json", "500", am.FAILURE_TRANSPORT),
])
def test_known_error_codes_map(fixture, code, kind):
    p = _provider(fixture)
    with pytest.raises(K.KosisErrorResponse) as exc:
        p.fetch(_candidate())
    assert exc.value.code == code and exc.value.failure_kind == kind


def test_unknown_code_is_retryable_not_success():
    """⚠️ 코드표가 **실측 미확인**이므로 특히 중요하다 — 모르는 코드가 성공이 되면
    오류 본문이 계약 모양으로 옮겨진다."""
    with pytest.raises(K.KosisErrorResponse) as exc:
        K.load_rows(json.dumps({"err": "999", "errMsg": "처음 보는 코드"}).encode("utf-8"))
    assert exc.value.failure_kind == am.FAILURE_TRANSPORT
    assert am.state_for_failure(exc.value.failure_kind) == am.FAILED


def test_every_code_in_the_table_is_a_known_failure_kind():
    for code, kind in K.ERROR_FAILURE_KIND.items():
        assert kind in am.FAILURE_KINDS, code


def test_the_table_is_marked_unverified():
    """★ 확인하지 않은 것을 확인한 것처럼 두지 않는다."""
    assert K.ERROR_TABLE_VERIFIED is False


# ── ④ 분류축 ────────────────────────────────────────────────────────────────
def test_category_axis_lands_in_target_ref():
    """`EXT-03.target_ref` 가 「무엇에 대한 지표인가」를 담는다."""
    _, batch = _batch()
    assert {r["target_ref"] for r in batch.rows} == {"제조업"}
    assert {r["category_code"] for r in batch.rows} == {"13"}


def test_rows_from_another_category_are_rejected():
    """★★★ 섞으면 「제조업 생산지수」와 「광업 생산지수」가 한 지표로 뭉친다."""
    _, batch = _batch("production_index_dirty.json")
    reasons = [r.reason for r in batch.rejected]
    assert "분류축 불일치" in reasons
    detail = next(r.detail for r in batch.rejected if r.reason == "분류축 불일치")
    assert "13" in detail and "14" in detail


def test_validation_checks_a_single_axis():
    p, batch = _batch()
    names = {c.name for c in p.validate(batch).checks}
    assert "분류축 단일" in names


def test_the_category_code_is_asked_not_hardcoded():
    """⚠️ 통계청이 분류를 개편하면 상수는 다른 계열을 받는다."""
    candidate = _candidate()
    assert candidate.params["category"] == "13"
    assert "첫 응답에서" in candidate.match_reason
    assert "13" not in json.dumps(K.TABLES, ensure_ascii=False)


# ── ⑤ 항상 실패하는 검사를 두지 않는다 ─────────────────────────────────────
def test_a_clean_response_validates():
    """⚠️⚠️ 처음에 「오류코드표 실측」을 `ok=False` 로 만들어 **매번 실패**하게 했다.
    그러면 정상 자료가 늘 격리되고 자동 적용은 영원히 막힌다."""
    p, batch = _batch()
    report = p.validate(batch)
    assert report.ok is True, [c.name for c in report.failures]


def test_the_unverified_table_is_reported_without_blocking():
    """주의사항은 **보이되 막지 않는다.**"""
    p, batch = _batch()
    check = next(c for c in p.validate(batch).checks if "오류코드표" in c.name)
    assert check.ok is True
    assert "확인하지 못했습니다" in check.detail


# ── 결손·단위 ───────────────────────────────────────────────────────────────
def test_unreadable_values_are_dropped_with_a_reason():
    """★ 지수를 0 으로 채우면 「생산이 멈췄다」로 읽힌다."""
    _, batch = _batch("production_index_dirty.json")
    assert batch.accounted is True
    assert all(r["value"] is not None for r in batch.rows)
    assert [r.reason for r in batch.rejected].count("값을 숫자로 읽지 못함") == 2


def test_mixed_units_are_caught():
    p, batch = _batch("production_index_dirty.json")
    report = p.validate(batch)
    assert report.ok is False
    assert "단위 단일" in {c.name for c in report.failures}


@pytest.mark.parametrize("raw,expected", [
    ("104.2", 104.2), ("1,042", 1042.0), ("-1.5", -1.5), ("0", 0.0),
    ("", None), ("-", None), ("해당없음", None), (None, None),
])
def test_value_parsing(raw, expected):
    assert K.parse_value(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("20250131", "2025-01-31"), ("202501", "2025-01"), ("2025", "2025"),
    ("", ""), ("20250", ""),
])
def test_period_parsing_never_invents_a_date(raw, expected):
    assert K.normalise_period(raw) == expected


# ── vintage · 순수성 ────────────────────────────────────────────────────────
def test_published_at_is_empty_because_the_source_does_not_give_it():
    _, batch = _batch()
    assert all(r["published_at"] == "" for r in batch.rows)
    assert all(r["vintage_date"] == r["observed_at"] for r in batch.rows)


def test_pure_methods_do_not_touch_the_network():
    def explode(url, *, allowed_hosts, timeout=20.0):
        raise AssertionError("네트워크를 만졌다")

    _, batch = _batch()
    pure = K.KosisProvider(env={"AFS_KOSIS_API_KEY": KEY}, transport=explode)
    assert pure.validate(batch).ok
    cp = pure.checkpoint(batch)
    assert cp.covered_from == "2025-01" and cp.covered_to == "2025-06"
    assert pure.refresh(cp)[0].params["start"] == "202507"


def test_refresh_is_deterministic_and_advances():
    p, batch = _batch()
    cp = p.checkpoint(batch)
    assert _provider().refresh(cp)[0].dataset_ref == _provider().refresh(cp)[0].dataset_ref
    assert "2025-06" in _provider().refresh(cp)[0].match_reason


def test_refresh_refuses_to_repeat_the_same_window():
    stuck = B.Checkpoint(provider_id="KOSIS", dataset_ref="101:DT_1F31502:13:D",
                         cursor="202506")
    assert _provider().refresh(stuck) == []


def test_source_fields_are_reported_for_drift_detection():
    """정기 갱신의 스키마 표류 관문이 이 값을 쓴다."""
    _, batch = _batch()
    assert "DT" in batch.source_fields and "PRD_DE" in batch.source_fields
    assert "C1_NM" in batch.source_fields


# ── 요청·자격증명 ───────────────────────────────────────────────────────────
def test_unknown_indicator_yields_no_candidate():
    assert _provider().discover(_request(indicators=("환율",))) == []
    assert _provider().discover(_request(indicators=())) == []


def test_period_is_required():
    with pytest.raises(B.ProviderError):
        _provider().discover(_request(period_from="", period_to=""))


def test_api_key_never_appears_in_the_result():
    p = _provider()
    result = p.fetch(_candidate())
    assert KEY not in result.requested_url
    assert "DT_1F31502" in result.requested_url


def test_missing_credential_names_the_variable():
    p = _provider(env={})
    with pytest.raises(B.ProviderCredentialError) as exc:
        p.discover(_request())
    assert "AFS_KOSIS_API_KEY" in str(exc.value)


def test_fetch_refuses_a_candidate_that_did_not_come_from_discover():
    with pytest.raises(B.ProviderError):
        _provider().fetch(B.DiscoveryCandidate(provider_id="KOSIS", dataset_ref="x",
                                               title="", target_contract_key="EXT-03"))


# ── EXT-03 계약 제안 ────────────────────────────────────────────────────────
def test_ext03_proposal_adds_the_missing_vintage_column():
    """★★★ 키트의 EXT-03 에는 형제 계약에 있는 `vintage_date` 가 **없다.**

    공표 통계는 정정 공표가 있어서 그 열이 없으면 「그 계획이 당시 어떤 값을 썼는가」를
    재현할 수 없다. 세 번째 Provider 를 붙이다 드러났다."""
    import glob
    from core.external_intelligence import mapping as M

    with open(glob.glob("starter_kits/*/*/contracts/EXT-03.contract.json")[0],
              encoding="utf-8") as f:
        kit = json.load(f)
    kit_fields = {x["name"] for x in kit["schema"]["fields"]}
    assert "vintage_date" not in kit_fields          # 키트에는 없고
    assert "target_ref" in kit_fields

    proposed = {x["name"] for x in M.ext03_public_proposal()["schema"]["fields"]}
    assert "vintage_date" in proposed                # 제안이 더한다
    assert "target_ref" in proposed


def test_ext03_proposal_keeps_the_contract_key_and_is_public():
    from core.external_intelligence import mapping as M
    doc = M.ext03_public_proposal()
    assert doc["dataset_id"] == "EXT-03"
    assert doc["status"] == "PROPOSED"
    assert doc["classification"]["data_origin"] == am.ORIGIN_PUBLIC_DISCLOSED
    assert "vintage_date 가 **빠져 있다**" in doc["proposal"]["rationale"]


def test_provider_output_matches_the_proposed_contract():
    """★★★ 이름이 갈리면 매핑은 통과하는데 적재에서 빈 칸이 된다."""
    from core.external_intelligence import mapping as M
    _, batch = _batch()
    produced = {k for row in batch.rows for k in row if not k.startswith("_")}
    declared = {f["name"] for f in M.ext03_public_proposal()["schema"]["fields"]}
    assert produced - declared == set(), f"계약에 없는 필드: {produced - declared}"
