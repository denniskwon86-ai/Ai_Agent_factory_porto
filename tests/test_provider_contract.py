"""[DAO-2] Provider 계약 — **이 창구로만 나간다**를 시험이 센다.

이 파일이 막는 것 넷.

1. 원천 카드가 **비어 있거나 모르는 값**인 채 등록되는 것.
2. `normalize`·`validate`·`checkpoint`·`refresh` 가 **네트워크를 만지는** 것
   — 만지는 순간 fixture 만으로는 검증할 수 없는 코드가 된다.
3. 허용 호스트 밖·사설망·평문으로 나가는 것.
4. 자격증명이 **결과 객체에 실려** 로그·원장·화면으로 흘러가는 것.
"""
import pytest

from core.external_intelligence import acquisition_models as am
from core.external_intelligence import providers as P


KEY = "0123456789abcdef0123456789abcdef"


def _descriptor(**over):
    base = dict(
        provider_id="STUB", name="시험용 원천", publisher="시험", source_type="API",
        allowed_hosts=("stub.example.com",), license_url="https://stub.example.com/terms",
        allowed_usage="내부 분석", redistribution_allowed=False,
        requires_credential=True, credential_env="AFS_STUB_KEY", cost="무료",
        default_trust_grade="gold", refresh_frequency="daily",
        coverage_note="2016~2025", target_contract_keys=("EXT-01",),
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
    )
    base.update(over)
    return P.ProviderDescriptor(**base)


class StubProvider(P.Provider):
    descriptor = _descriptor()

    def discover(self, request):
        return [P.DiscoveryCandidate(provider_id="STUB", dataset_ref="D1", title="자료",
                                     target_contract_key="EXT-01", match_reason="지표명 일치")]

    def preview(self, candidate):
        return self.fetch(candidate)

    def fetch(self, candidate, *, checkpoint=None):
        url = f"https://stub.example.com/api?key={self.credential()}&id={candidate.dataset_ref}"
        return self._fetch_result(dataset_ref=candidate.dataset_ref,
                                  response=self._get(url), requested_url=url)

    def normalize(self, result):
        return P.NormalizedBatch(provider_id="STUB", contract_key="EXT-01",
                                 rows=({"value": 1.0},), rejected=(), source_row_count=1)

    def validate(self, batch):
        return P.ValidationReport(checks=(P.CheckResult("행수", True, count=len(batch.rows)),))

    def checkpoint(self, batch, *, previous=None):
        return P.Checkpoint(provider_id="STUB", dataset_ref="D1", cursor="1")

    def refresh(self, checkpoint):
        return [P.DiscoveryCandidate(provider_id="STUB", dataset_ref="D1", title="다음",
                                     target_contract_key="EXT-01", match_reason="이어받기")]


def _transport_ok(url, *, allowed_hosts, timeout=20.0):
    return {"body": b'{"ok":1}', "content_type": "application/json", "status": 200,
            "final_url": url, "fetched_at": "2026-09-05T00:00:00+00:00"}


def _transport_explodes(url, *, allowed_hosts, timeout=20.0):
    raise AssertionError(f"네트워크를 만졌다: {url}")


# ── 원천 카드 ────────────────────────────────────────────────────────────────
def test_descriptor_rejects_empty_allowed_hosts():
    """허용 호스트가 비면 «어디로든» 이 된다."""
    with pytest.raises(P.ProviderError):
        _descriptor(allowed_hosts=())


def test_descriptor_rejects_unknown_data_origin():
    with pytest.raises(am.AcquisitionStateError):
        _descriptor(data_origin="공개자료")


def test_descriptor_rejects_unknown_source_type_and_grade():
    with pytest.raises(P.ProviderError):
        _descriptor(source_type="SCRAPE")
    with pytest.raises(P.ProviderError):
        _descriptor(default_trust_grade="platinum")


def test_descriptor_requires_env_name_when_credential_needed():
    """이름이 없으면 키를 «어디서» 읽는지 코드가 정하게 되고, 결국 코드에 적힌다."""
    with pytest.raises(P.ProviderError):
        _descriptor(requires_credential=True, credential_env="")


def test_descriptor_carries_every_field_the_recommendation_screen_needs():
    """지시 3 — 추천 결과에 반드시 표시할 항목이 전부 카드에 있어야 한다."""
    d = _descriptor()
    for field in ("publisher", "license_url", "allowed_usage", "redistribution_allowed",
                  "requires_credential", "cost", "default_trust_grade", "refresh_frequency",
                  "coverage_note", "target_contract_keys", "data_origin"):
        assert hasattr(d, field), field


# ── 순수성 ───────────────────────────────────────────────────────────────────
def test_pure_methods_never_touch_the_network():
    """★★★ 실제 API 키 없이 fixture 만으로 종단 검증이 되려면 이 넷이 순수해야 한다.

    전송층이 호출되면 폭발하는 것을 주입한 뒤 넷을 전부 돌린다."""
    p = StubProvider(env={"AFS_STUB_KEY": KEY}, transport=_transport_explodes)
    batch = p.normalize(P.FetchResult(provider_id="STUB", dataset_ref="D1", payload=b"{}",
                                      content_type="application/json", requested_url="",
                                      fetched_at="2026-09-05T00:00:00+00:00"))
    assert p.validate(batch).ok
    cp = p.checkpoint(batch)
    assert p.refresh(cp)


def test_fetch_is_the_method_that_goes_out():
    p = StubProvider(env={"AFS_STUB_KEY": KEY}, transport=_transport_explodes)
    with pytest.raises(AssertionError):
        p.fetch(P.DiscoveryCandidate(provider_id="STUB", dataset_ref="D1", title="",
                                     target_contract_key="EXT-01"))


# ── 자격증명 ─────────────────────────────────────────────────────────────────
def test_credential_comes_from_the_environment_only():
    p = StubProvider(env={"AFS_STUB_KEY": KEY}, transport=_transport_ok)
    assert p.credential() == KEY
    assert p.secret_values() == (KEY,)


def test_missing_credential_says_which_variable_to_set():
    p = StubProvider(env={}, transport=_transport_ok)
    with pytest.raises(P.ProviderCredentialError) as exc:
        p.credential()
    assert "AFS_STUB_KEY" in str(exc.value)
    assert p.credential(required=False) == ""


def test_fetch_result_url_is_already_redacted():
    """★★★ 지우지 않은 URL 을 결과에 담으면 그 결과가 로그·원장·화면 어디로든 흘러간다."""
    p = StubProvider(env={"AFS_STUB_KEY": KEY}, transport=_transport_ok)
    out = p.fetch(P.DiscoveryCandidate(provider_id="STUB", dataset_ref="D1", title="",
                                       target_contract_key="EXT-01"))
    assert KEY not in out.requested_url
    assert "id=D1" in out.requested_url
    assert out.payload == b'{"ok":1}'


# ── 전송 차단 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url,hosts,why", [
    ("http://stub.example.com/x", ("stub.example.com",), "평문"),
    ("https://evil.test/x", ("stub.example.com",), "허용목록 밖"),
    ("https://stub.example.com:8443/x", ("stub.example.com",), "비표준 포트"),
    ("https://u:p@stub.example.com/x", ("stub.example.com",), "사용자정보"),
    ("https://stub.example.com/x#frag", ("stub.example.com",), "fragment"),
    ("https://stub.example.com/x", (), "허용목록 빈값"),
])
def test_transport_refuses_unsafe_targets(url, hosts, why):
    with pytest.raises(P.ProviderError):
        P.https_get(url, allowed_hosts=hosts, timeout=2)


def test_transport_refuses_hosts_resolving_to_private_addresses():
    """★★★ 문자열 검사만으로는 부족하다 — DNS 가 사설망을 가리키면 SSRF 다.

    `localhost` 를 **허용 목록에 넣고도** 막히는지 본다(호스트 검사는 통과시키고
    주소 확인 단계가 잡아야 한다)."""
    with pytest.raises(P.ProviderError) as exc:
        P.https_get("https://localhost/x", allowed_hosts=("localhost",), timeout=2)
    assert "공개망" in str(exc.value)


# ── 등록부 ───────────────────────────────────────────────────────────────────
def test_registry_rejects_duplicate_provider_id():
    reg = P.ProviderRegistry()
    reg.register(StubProvider)

    class Other(StubProvider):
        pass

    with pytest.raises(P.ProviderError):
        reg.register(Other)


def test_registry_reregistering_the_same_class_is_fine():
    """모듈이 두 번 import 되는 것만으로 터지면 안 된다."""
    reg = P.ProviderRegistry()
    reg.register(StubProvider)
    reg.register(StubProvider)
    assert reg.ids() == ("STUB",)


def test_unknown_provider_error_lists_what_exists():
    reg = P.ProviderRegistry()
    reg.register(StubProvider)
    with pytest.raises(P.ProviderError) as exc:
        reg.get("NOPE")
    assert "STUB" in str(exc.value)


def test_registry_refuses_a_class_without_a_descriptor():
    reg = P.ProviderRegistry()

    class NoCard:
        pass

    with pytest.raises(P.ProviderError):
        reg.register(NoCard)


def test_priority_reads_the_existing_table_not_a_second_one():
    """★★★ 우선순위 표가 둘이면 화면 순서와 적재 순서가 갈린다."""
    from core.external_intelligence import _SOURCE_PRIORITY
    for stype, expected in _SOURCE_PRIORITY.items():
        assert P.source_priority(stype) == expected
    assert P.source_priority("모르는것") == 99


def test_ranked_reports_why_a_source_was_excluded():
    """지시 3 — 「선택하지 않은 원천과 제외 사유」. 조용한 제외는 화면이 설명할 수 없다."""
    reg = P.ProviderRegistry()
    reg.register(StubProvider)
    chosen, excluded = reg.ranked(require_credential_present=True, env={})
    assert chosen == ()
    assert len(excluded) == 1
    assert excluded[0].provider_id == "STUB"
    assert "AFS_STUB_KEY" in excluded[0].reason

    chosen, excluded = reg.ranked(require_credential_present=True,
                                  env={"AFS_STUB_KEY": KEY})
    assert [d.provider_id for d in chosen] == ["STUB"]
    assert excluded == ()


def test_for_contract_finds_providers_that_fill_a_dataset():
    reg = P.ProviderRegistry()
    reg.register(StubProvider)
    assert [d.provider_id for d in reg.for_contract("EXT-01")] == ["STUB"]
    assert reg.for_contract("FIN-01") == ()


# ── 정규화 결과의 모양 ───────────────────────────────────────────────────────
def test_batch_accounting_catches_silently_dropped_rows():
    """★★★ 받은 줄은 «들어갔거나 사유와 함께 빠졌거나» 둘 중 하나여야 한다."""
    ok = P.NormalizedBatch(provider_id="STUB", contract_key="EXT-01",
                           rows=({"v": 1},), rejected=(P.RejectedRow(1, "단위 없음"),),
                           source_row_count=2)
    assert ok.accounted is True
    silent = P.NormalizedBatch(provider_id="STUB", contract_key="EXT-01",
                               rows=({"v": 1},), rejected=(), source_row_count=5)
    assert silent.accounted is False


def test_validation_report_does_not_raise_and_names_the_failure_kind():
    report = P.ValidationReport(checks=(
        P.CheckResult("행수", True),
        P.CheckResult("단위", False, "USD/MT 와 KRW/kg 혼용", failure_kind=am.FAILURE_QUALITY),
        P.CheckResult("전송", False, "타임아웃", failure_kind=am.FAILURE_TRANSPORT),
    ))
    assert report.ok is False
    assert len(report.failures) == 2
    #: 격리 사유가 있으면 그것이 우선 — 재시도로 풀리지 않는 문제이기 때문이다.
    assert report.worst_failure_kind() == am.FAILURE_QUALITY
    assert am.state_for_failure(report.worst_failure_kind()) == am.QUARANTINED


def test_empty_validation_report_is_ok_but_says_nothing():
    """검사가 0건이면 «통과» 다 — 그래서 Provider 마다 검사 목록을 시험이 따로 센다."""
    assert P.ValidationReport().ok is True
    assert P.ValidationReport().worst_failure_kind() == ""
