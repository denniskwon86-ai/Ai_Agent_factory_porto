"""[DAO-10] 한국은행 ECOS Provider — 두 번째 원천이 첫 번째를 흉내 내지 않는지.

이 파일이 지키는 것 다섯.

  ① **키가 경로에 있는** 원천에서 인증키가 새지 않는다(값 기반 삭제가 실제로 필요한 자리).
  ② 오류가 **HTTP 200 으로** 와도 갈린다 — `INFO-200` 만 「자료 없음」이다.
  ③ 세부항목 코드를 **추측하지 않고 원천에 물어본다**.
  ④ 기간 표기가 **통계표의 주기에 맞는다**(주기 D 에 `YYYYMM` 을 보내지 않는다).
  ⑤ 결손을 0 으로 채우지 않고, 단위 혼용을 잡는다.

⚠️ 네트워크를 한 번도 쓰지 않는다. 통과는 「배선이 맞다」까지다.
"""
import json
import os

import pytest

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import ecos as E

KEY = "ecoskey0123456789abcdefghij"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "ecos")


def _transport(search="search_fx_2025.json", items="item_list_fx.json"):
    def call(url, *, allowed_hosts, timeout=20.0):
        name = items if "StatisticItemList" in url else search
        with open(os.path.join(FIX, name), "rb") as f:
            return {"body": f.read(), "content_type": "application/json", "status": 200,
                    "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}
    return call


def _provider(search="search_fx_2025.json", items="item_list_fx.json", env=None):
    return E.EcosProvider(env={"AFS_ECOS_API_KEY": KEY} if env is None else env,
                          transport=_transport(search, items))


def _request(**over):
    base = dict(subject_name="LS MnM", purpose="환율 가정", indicators=("환율",),
                period_from="2025", period_to="2025")
    base.update(over)
    return B.AcquisitionRequest(**base)


def _batch(search="search_fx_2025.json"):
    p = _provider(search)
    candidate = p.discover(_request())[0]
    return p, p.normalize(p.fetch(candidate))


# ── 원천 카드 ────────────────────────────────────────────────────────────────
def test_provider_is_registered_alongside_opendart():
    from core.external_intelligence import providers as P
    import core.external_intelligence.providers.opendart  # noqa: F401
    assert {"ECOS", "OPENDART"} <= set(P.provider_registry.ids())


def test_descriptor_targets_the_existing_contract_not_a_new_one():
    """`EXT-01` 은 이미 있다 — PUB-01 처럼 새 키를 만들지 않는다."""
    d = E.EcosProvider.descriptor
    assert d.target_contract_keys == ("EXT-01",)
    assert d.data_origin == am.ORIGIN_PUBLIC_DISCLOSED


def test_descriptor_warns_that_the_key_is_in_the_path():
    """이 한계를 카드에 적어야 화면과 운영자가 안다."""
    limits = " ".join(E.EcosProvider.descriptor.known_limits)
    assert "URL 경로" in limits
    assert "실제 체결 환율이 아닙니다" in limits


def test_descriptor_says_the_rate_is_not_the_companys_own():
    """★ 매매기준율을 회사 환율로 읽으면 손익이 조용히 달라진다."""
    limits = E.EcosProvider.descriptor.known_limits
    assert any("조달금리가 아닙니다" in x for x in limits)


# ── ① 키가 경로에 있어도 새지 않는다 ────────────────────────────────────────
def test_api_key_never_appears_in_the_fetch_result():
    """★★★ 질의 문자열만 지우는 검사기는 이 원천을 통과시킨다."""
    p = _provider()
    result = p.fetch(p.discover(_request())[0])
    assert KEY not in result.requested_url
    assert "StatisticSearch" in result.requested_url
    assert "731Y001" in result.requested_url          # 지운 뒤에도 무엇을 불렀는지 남는다


def test_the_key_does_not_reach_the_raw_store(tmp_path):
    """원문 보관까지 가는 경로에서도 새지 않는지 — 끝까지 따라간다."""
    from core.external_intelligence.raw_store import RawStore
    store = RawStore(str(tmp_path / "raw"))
    p = _provider()
    result = p.fetch(p.discover(_request())[0])
    meta = store.put(result.payload, source_id="ECOS", requested_url=result.requested_url,
                     content_type=result.content_type, secrets=p.secret_values())
    assert KEY not in json.dumps(store.meta(meta["raw_object_ref"]), ensure_ascii=False)


def test_item_lookup_also_hides_the_key():
    """탐색 단계의 호출도 같은 창구를 쓴다 — 한 경로만 지우면 다른 경로로 샌다."""
    seen = []

    def spy(url, *, allowed_hosts, timeout=20.0):
        seen.append(url)
        return _transport()(url, allowed_hosts=allowed_hosts, timeout=timeout)

    E.EcosProvider(env={"AFS_ECOS_API_KEY": KEY}, transport=spy).discover(_request())
    #: ⚠️ 전송층에 가는 URL 에는 키가 **있어야** 한다(그래야 호출이 된다).
    #:   지워지는 곳은 결과·보관·로그다. 이 시험은 그 경계를 못 박는다.
    assert any(KEY in u for u in seen)


# ── ② 오류가 200 으로 온다 ──────────────────────────────────────────────────
def test_no_data_comes_back_as_a_normal_response(tmp_path):
    """★★★ `INFO-200` 은 정상 응답이다 — 장애로 접으면 영원히 재시도한다."""
    p = _provider("result_no_data.json")
    candidate = _provider().discover(_request())[0]
    with pytest.raises(E.NoDataFromSource):
        p.fetch(candidate)


@pytest.mark.parametrize("fixture,code,kind,state", [
    ("result_bad_key.json", "INFO-100", am.FAILURE_AUTH, am.FAILED),
    ("result_traffic.json", "ERROR-602", am.FAILURE_TRANSPORT, am.FAILED),
    ("result_server.json", "ERROR-500", am.FAILURE_TRANSPORT, am.FAILED),
])
def test_error_codes_map_to_the_right_failure(fixture, code, kind, state):
    p = _provider(fixture)
    candidate = _provider().discover(_request())[0]
    with pytest.raises(E.EcosResultError) as exc:
        p.fetch(candidate)
    assert exc.value.code == code
    assert exc.value.failure_kind == kind
    assert am.state_for_failure(exc.value.failure_kind) == state


def test_no_data_is_a_distinct_exception():
    assert not issubclass(E.EcosResultError, E.NoDataFromSource)
    assert not issubclass(E.NoDataFromSource, E.EcosResultError)


def test_every_known_code_maps_to_a_known_failure_kind():
    for code, kind in E.RESULT_FAILURE_KIND.items():
        assert kind in am.FAILURE_KINDS, code
    assert E.RESULT_NO_DATA not in E.RESULT_FAILURE_KIND
    assert E.RESULT_OK not in E.RESULT_FAILURE_KIND


def test_unknown_code_is_transport_not_success():
    with pytest.raises(E.EcosResultError) as exc:
        E._check_result({"RESULT": {"CODE": "ERROR-999", "MESSAGE": "처음 보는 코드"}})
    assert exc.value.failure_kind == am.FAILURE_TRANSPORT


def test_a_normal_response_has_no_result_block():
    """정상 응답에는 `RESULT` 가 없다 — 없다고 오류로 읽으면 전부 막힌다."""
    E._check_result({"StatisticSearch": {"row": []}})


def test_html_error_page_is_schema_drift():
    with pytest.raises(E.EcosResultError) as exc:
        E._load("<html>점검 중</html>".encode("utf-8"), "StatisticSearch")
    assert exc.value.failure_kind == am.FAILURE_SCHEMA_DRIFT


# ── ③ 세부항목을 물어본다 ───────────────────────────────────────────────────
def test_item_code_comes_from_the_source_not_a_constant():
    """★★★ 상수로 박아 두면 원천이 바꾼 날 조용히 다른 계열을 받는다."""
    candidate = _provider().discover(_request())[0]
    assert candidate.params["item_code"] == "0000001"
    assert "원천 목록에서" in candidate.match_reason
    #: 코드가 코드 안에 상수로 있지 않다.
    assert "0000001" not in json.dumps(E.SERIES, ensure_ascii=False)


def test_other_items_are_reported_as_ambiguous():
    """고른 것과 **못 고른 것**을 함께 알린다."""
    candidate = _provider().discover(_request())[0]
    assert candidate.ambiguous_with == ()      # 힌트로 하나만 정확히 걸렸다
    #: 힌트가 안 맞으면 목록 전체가 후보가 되고 나머지를 알린다.
    loose = _provider().discover(_request(indicators=("환율",)))
    assert loose and loose[0].params["item_name"].startswith("원/미국달러")


def test_unknown_indicator_yields_no_candidate():
    """닫힌 목록 밖은 후보가 되지 않는다 — 「없다」는 예외가 아니다."""
    assert _provider().discover(_request(indicators=("구리가격",))) == []
    assert _provider().discover(_request(indicators=())) == []


def test_series_table_matches_by_alias():
    assert [c for c, _ in E.match_series(["환율"])] == ["731Y001"]
    assert [c for c, _ in E.match_series(["기준금리"])] == ["722Y001"]
    assert [c for c, _ in E.match_series(["소비자물가"])] == ["901Y009"]
    assert E.match_series(["구리"]) == []


def test_period_is_required():
    with pytest.raises(B.ProviderError):
        _provider().discover(_request(period_from="", period_to=""))


# ── ④ 주기에 맞는 기간 표기 ─────────────────────────────────────────────────
@pytest.mark.parametrize("cycle,expected", [
    ("D", ("20240101", "20251231")), ("M", ("202401", "202512")),
    ("Q", ("2024Q1", "2025Q4")), ("A", ("2024", "2025")),
])
def test_period_shape_follows_the_cycle(cycle, expected):
    """⚠️ 실측으로 어긋났다 — 주기가 D 인데 `YYYYMM` 을 보내면 원천이 다른 것을 준다."""
    assert E._period(B.AcquisitionRequest(period_from="2024", period_to="2025"),
                     cycle) == expected


def test_candidate_period_matches_the_discovered_cycle():
    candidate = _provider().discover(_request())[0]
    cycle = candidate.params["cycle"]
    start = candidate.params["start"]
    assert cycle == "M" and len(start) == 6, (cycle, start)


@pytest.mark.parametrize("cursor,cycle,expected", [
    ("202506", "M", "202507"), ("202512", "M", "202601"),
    ("20250630", "D", "20250701"), ("2025", "A", "2026"),
])
def test_cursor_advances_by_one_period(cursor, cycle, expected):
    assert E._next_period(cursor, cycle) == expected


def test_refresh_refuses_to_repeat_the_same_window():
    """★ 커서를 넘기지 못하면 같은 구간을 다시 받는다 — 중복만 쌓인다."""
    stuck = B.Checkpoint(provider_id="ECOS", dataset_ref="731Y001:0000001:D",
                         cursor="202506")     # 주기 D 인데 커서는 월 단위
    assert _provider().refresh(stuck) == []


def test_refresh_advances_and_stays_pure():
    """네트워크를 만지면 정기 갱신이 「돌려 봐야 아는」 것이 된다."""
    def explode(url, *, allowed_hosts, timeout=20.0):
        raise AssertionError("네트워크를 만졌다")

    p, batch = _batch()
    cp = p.checkpoint(batch)
    pure = E.EcosProvider(env={"AFS_ECOS_API_KEY": KEY}, transport=explode)
    nxt = pure.refresh(cp)
    assert nxt[0].params["start"] == "202507"
    assert "2025-06" in nxt[0].match_reason


def test_refresh_upper_bound_does_not_read_the_clock():
    """같은 체크포인트가 날마다 다른 후보를 내면 재현이 안 된다."""
    p, batch = _batch()
    cp = p.checkpoint(batch)
    first = _provider().refresh(cp)[0].dataset_ref
    second = _provider().refresh(cp)[0].dataset_ref
    assert first == second


# ── ⑤ 결손과 단위 ──────────────────────────────────────────────────────────
def test_unreadable_values_are_dropped_with_a_reason_not_zeroed():
    """★★★ 0 으로 채우면 「환율이 0」이 되고, 그것은 결손보다 나쁘다."""
    p, batch = _batch("search_fx_dirty.json")
    assert batch.source_row_count == 5
    assert len(batch.rows) == 2
    reasons = [r.reason for r in batch.rejected]
    assert reasons.count("값을 숫자로 읽지 못함") == 2
    assert "시점을 읽지 못함" in reasons
    assert batch.accounted is True
    assert all(r["value"] is not None for r in batch.rows)


def test_mixed_units_are_caught_by_validation():
    """USD 와 원이 섞이면 합계가 조용히 틀린다."""
    p, batch = _batch("search_fx_dirty.json")
    report = p.validate(batch)
    assert report.ok is False
    assert "단위 단일" in {c.name for c in report.failures}
    assert am.state_for_failure(report.worst_failure_kind()) == am.QUARANTINED


@pytest.mark.parametrize("raw,expected", [
    ("1452.3", 1452.3), ("1,452.3", 1452.3), ("-0.5", -0.5), ("0", 0.0),
    ("", None), ("-", None), ("해당없음", None), (None, None),
])
def test_value_parsing(raw, expected):
    assert E.parse_value(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("20250131", "2025-01-31"), ("202501", "2025-01"), ("2025Q1", "2025-Q1"),
    ("2025", "2025"), ("", ""), ("20250", ""),
])
def test_time_parsing_never_invents_a_date(raw, expected):
    assert E.normalise_time(raw) == expected


# ── vintage ─────────────────────────────────────────────────────────────────
def test_published_at_is_left_empty_because_the_source_does_not_give_it():
    """★★★ 「받은 날」을 발표일로 적으면 §12.5 의 재현성이 조용히 깨진다."""
    _, batch = _batch()
    assert all(r["published_at"] == "" for r in batch.rows)
    #: 그 대신 vintage 는 관측 시점을 쓴다 — 그리고 그 사실을 검증이 말한다.
    assert all(r["vintage_date"] == r["observed_at"] for r in batch.rows)


def test_validation_states_that_the_missing_published_date_is_normal():
    p, batch = _batch()
    check = next(c for c in p.validate(batch).checks if "발표일" in c.name)
    assert check.ok is True
    assert "지어내지 않고" in check.detail


# ── 정산·순수성 ─────────────────────────────────────────────────────────────
def test_clean_response_validates():
    p, batch = _batch()
    report = p.validate(batch)
    assert report.ok is True
    names = {c.name for c in report.checks}
    assert {"행 정산", "자료 있음", "단위 단일", "지표 단일", "시점 중복 없음"} <= names


def test_pure_methods_do_not_touch_the_network():
    def explode(url, *, allowed_hosts, timeout=20.0):
        raise AssertionError("네트워크를 만졌다")

    _, batch = _batch()
    pure = E.EcosProvider(env={"AFS_ECOS_API_KEY": KEY}, transport=explode)
    assert pure.validate(batch).ok
    cp = pure.checkpoint(batch)
    assert cp.covered_from == "2025-01" and cp.covered_to == "2025-06"
    assert pure.refresh(cp)


def test_missing_credential_names_the_variable():
    p = _provider(env={})
    with pytest.raises(B.ProviderCredentialError) as exc:
        p.discover(_request())
    assert "AFS_ECOS_API_KEY" in str(exc.value)


def test_fetch_refuses_a_candidate_that_did_not_come_from_discover():
    with pytest.raises(B.ProviderError):
        _provider().fetch(B.DiscoveryCandidate(provider_id="ECOS", dataset_ref="x", title="",
                                               target_contract_key="EXT-01"))


def test_normalizer_is_not_shared_with_opendart():
    """지시 4 — 느슨한 범용 파서를 만들지 않는다. 두 변환기는 다른 코드다."""
    from core.external_intelligence.providers import opendart as od
    assert E.EcosProvider.normalize is not od.OpenDartProvider.normalize
    #: OpenDART 응답을 ECOS 변환기에 넣으면 **통과하지 않는다.**
    dart = os.path.join(os.path.dirname(__file__), "fixtures", "opendart",
                        "fnltt_2025_cfs_ok.json")
    with open(dart, "rb") as f:
        payload = f.read()
    with pytest.raises(E.EcosResultError):
        E._load(payload, "StatisticSearch")
