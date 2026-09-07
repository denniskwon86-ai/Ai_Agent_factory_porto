"""[DAO-14] 공공데이터포털 — **포털은 원천이 아니다. 서비스가 원천이다.**

이 파일이 지키는 것 여섯.

  ① 서비스마다 **자기 등급**을 갖는다(KPX=silver · ECOS·KOSIS=gold).
  ② **쪽을 끝까지** 받고, 쪽마다 원문을 따로 보관한다.
  ③ 오류가 **두 봉투**로 온다 — 둘 다 읽는다.
  ④ 1건이면 `item` 이 배열이 아니라 객체다 — 놓치지 않는다.
  ⑤ `resultCode=03` 은 「자료 없음」이고 장애가 아니다.
  ⑥ `FIELDS` 를 선언하지 않은 서비스는 **만들 수 없다**.
"""
import json
import os
import re
import tempfile

import pytest

from core.decision_ledger import DecisionLedger
from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence import providers as P
from core.external_intelligence import provenance as PV
from core.external_intelligence.acquisition_store import AcquisitionStore
from core.external_intelligence.orchestrator import AcquisitionOrchestrator
from core.external_intelligence.providers import base as B
from core.external_intelligence.providers import datagokr as D
from core.external_intelligence.raw_store import RawStore

#: ⚠️ 발급되는 serviceKey 는 **이미 인코딩된 값**이다 — `%2F` 가 들어간다.
KEY = "datagokrkey0123456789abcdef%2Fxyz"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "datagokr")
REQUESTER = "t_member_a@test.invalid"
APPROVER = "t_dataadmin@test.invalid"


def _paged_transport(record=None):
    def call(url, *, allowed_hosts, timeout=20.0):
        if record is not None:
            record.append(url)
        m = re.search(r"pageNo=(\d+)", url)
        page = min(int(m.group(1)) if m else 1, 3)
        with open(os.path.join(FIX, f"smp_page{page}.json"), "rb") as f:
            return {"body": f.read(), "content_type": "application/json", "status": 200,
                    "final_url": url, "fetched_at": "2026-09-08T00:00:00+00:00"}
    return call


def _fixed_transport(name):
    def call(url, *, allowed_hosts, timeout=20.0):
        with open(os.path.join(FIX, name), "rb") as f:
            return {"body": f.read(), "content_type": "application/json", "status": 200,
                    "final_url": url, "fetched_at": "2026-09-08T00:00:00+00:00"}
    return call


def _provider(transport=None, env=None):
    return D.KpxSmpProvider(env={"AFS_DATA_GO_KR_SERVICE_KEY": KEY} if env is None else env,
                            transport=transport or _paged_transport())


def _request(**over):
    base = dict(subject_name="LS MnM", purpose="전력비 변동성", indicators=("SMP",),
                period_from="2025", period_to="2025")
    base.update(over)
    return B.AcquisitionRequest(**base)


def _candidate():
    return _provider().discover(_request())[0]


# ── ① 서비스마다 자기 등급 ─────────────────────────────────────────────────
def test_the_service_is_its_own_provider_not_the_portal():
    """★★★ 포털을 한 Provider 로 두면 등급 하나가 수천 서비스를 대표하게 된다."""
    assert "KPX_SMP" in P.provider_registry.ids()
    assert "DATA_GO_KR" not in P.provider_registry.ids()
    assert "DATAGOKR" not in P.provider_registry.ids()


def test_kpx_is_silver_while_the_others_are_gold():
    """설계서 §4.2 가 지정한 등급. 뭉치면 이 구분이 사라진다."""
    import core.external_intelligence.providers.ecos as E  # noqa: F401
    import core.external_intelligence.providers.kosis as KO  # noqa: F401
    assert D.KpxSmpProvider.descriptor.default_trust_grade == "silver"
    assert E.EcosProvider.descriptor.default_trust_grade == "gold"
    assert KO.KosisProvider.descriptor.default_trust_grade == "gold"


def test_the_limit_says_it_is_not_the_electricity_bill():
    """설계서 §4.3 — SMP 는 전기요금 청구서·계약요금의 대체값이 아니다."""
    limits = " ".join(D.KpxSmpProvider.descriptor.known_limits)
    assert "청구서" in limits and "실제 공장 전력비가 아닙니다" in limits
    assert "보조 동인" in limits
    assert "실측으로 확인되지 않았습니다" in limits


def test_the_grade_travels_into_the_stored_row(tmp_path):
    """등급이 카드에만 있고 행에 안 실리면 나중에 「이 값이 얼마나 믿을 만한가」를 못 답한다."""
    rig = _rig(tmp_path)
    _walk(rig)
    answer = PV.answer(rig["store"], contract_key="EXT-03",
                       match={"indicator_code": "KPX_SMP", "observed_at": "2025-01-03"},
                       value_field="value")
    assert answer.trust_grade == "silver"


# ── ⑥ FIELDS 를 선언하지 않으면 만들 수 없다 ───────────────────────────────
def test_a_service_without_fields_cannot_be_built():
    """★★★ 기본 구현을 주면 새 서비스가 「대충 돌아가는」 상태가 된다(지시 4)."""
    class Bare(D.DataGoKrService):
        descriptor = D.KpxSmpProvider.descriptor

    with pytest.raises(B.ProviderError) as exc:
        Bare(env={}, transport=None)
    assert "ENDPOINT·FIELDS" in str(exc.value)


def test_the_base_class_is_not_registered():
    """기반 클래스가 등록되면 등급 없는 «포털» 이 목록에 뜬다."""
    assert "DataGoKrService" not in P.provider_registry.ids()


# ── ③ 두 봉투 ───────────────────────────────────────────────────────────────
def test_the_standard_envelope_is_read():
    with open(os.path.join(FIX, "smp_page1.json"), "rb") as f:
        env = D.read_envelope(f.read())
    assert len(env["items"]) == 10
    assert env["page"] == 1 and env["total"] == 25


def test_the_other_envelope_is_an_auth_error_not_schema_drift():
    """★★★ 둘째 봉투를 모르면 인증 오류가 **표류**로 분류되고 사람은 파서를 고치러 간다."""
    with open(os.path.join(FIX, "err_other_envelope.json"), "rb") as f:
        with pytest.raises(D.DataGoKrError) as exc:
            D.read_envelope(f.read())
    assert exc.value.code == "30"
    assert exc.value.failure_kind == am.FAILURE_AUTH
    assert exc.value.envelope == "OpenAPI_ServiceResponse"
    assert am.state_for_failure(exc.value.failure_kind) == am.FAILED


def test_in_envelope_error_maps_too():
    with open(os.path.join(FIX, "err_quota.json"), "rb") as f:
        with pytest.raises(D.DataGoKrError) as exc:
            D.read_envelope(f.read())
    assert exc.value.code == "22" and exc.value.failure_kind == am.FAILURE_TRANSPORT


def test_unknown_code_is_retryable_not_success():
    payload = json.dumps({"response": {"header": {"resultCode": "77", "resultMsg": "?"},
                                       "body": {}}}).encode("utf-8")
    with pytest.raises(D.DataGoKrError) as exc:
        D.read_envelope(payload)
    assert exc.value.failure_kind == am.FAILURE_TRANSPORT


def test_neither_envelope_is_schema_drift():
    with pytest.raises(D.DataGoKrError) as exc:
        D.read_envelope(json.dumps({"something": 1}).encode("utf-8"))
    assert exc.value.failure_kind == am.FAILURE_SCHEMA_DRIFT


def test_other_providers_payloads_do_not_pass():
    """지시 4 — 느슨한 범용 파서를 만들지 않는다."""
    for sub, name in [("opendart", "fnltt_2025_cfs_ok.json"),
                      ("ecos", "search_fx_2025.json"),
                      ("kosis", "production_index_2025.json")]:
        path = os.path.join(os.path.dirname(__file__), "fixtures", sub, name)
        with open(path, "rb") as f:
            with pytest.raises(D.DataGoKrError):
                D.read_envelope(f.read())


def test_every_code_maps_to_a_known_failure_kind():
    for code, kind in D.RESULT_FAILURE_KIND.items():
        assert kind in am.FAILURE_KINDS, code
    assert D.RESULT_NO_DATA not in D.RESULT_FAILURE_KIND
    assert D.RESULT_OK not in D.RESULT_FAILURE_KIND


# ── ⑤ 자료 없음 ─────────────────────────────────────────────────────────────
def test_result_code_03_is_no_data():
    with open(os.path.join(FIX, "nodata.json"), "rb") as f:
        with pytest.raises(D.NoDataFromSource):
            D.read_envelope(f.read())


def test_no_data_is_a_distinct_exception():
    assert not issubclass(D.DataGoKrError, D.NoDataFromSource)
    assert not issubclass(D.NoDataFromSource, D.DataGoKrError)


# ── ④ 1건이면 배열이 아니다 ────────────────────────────────────────────────
def test_a_single_item_comes_back_as_an_object_and_is_not_lost():
    """★★★ XML→JSON 변환의 고전적 함정. 배열만 기대하면 **1건이 조용히 사라진다.**"""
    with open(os.path.join(FIX, "single_item.json"), "rb") as f:
        env = D.read_envelope(f.read())
    assert len(env["items"]) == 1
    assert env["items"][0]["baseDt"] == "20250101"


def test_empty_items_string_is_zero_rows_not_a_crash():
    payload = json.dumps({"response": {"header": {"resultCode": "00", "resultMsg": "OK"},
                                       "body": {"items": "", "totalCount": 0}}}).encode("utf-8")
    assert D.read_envelope(payload)["items"] == []


# ── ② 페이징 ────────────────────────────────────────────────────────────────
def test_fetch_returns_one_page_and_says_there_is_more():
    p = _provider()
    first = p.fetch(_candidate(), page=1)
    assert first.page == 1 and first.has_more is True and first.next_cursor == "2"
    last = p.fetch(_candidate(), page=3)
    assert last.page == 3 and last.has_more is False


def test_paging_fields_were_declared_but_unused_until_now():
    """★ `has_more`·`next_cursor` 는 `base.py` 에 선언만 돼 있었다 — 이 Provider 가 처음 쓴다."""
    import inspect
    from core.external_intelligence import orchestrator as O
    assert "has_more" in inspect.getsource(O.AcquisitionOrchestrator._collect)


def _rig(tmp_path, transport=None, record=None):
    store = AcquisitionStore(str(tmp_path / "ei.db"),
                             ledger=DecisionLedger(str(tmp_path / "ledger.db")))
    raw = RawStore(str(tmp_path / "raw"))
    orch = AcquisitionOrchestrator(
        store=store, raw_store=raw, registry=P.provider_registry,
        env={"AFS_DATA_GO_KR_SERVICE_KEY": KEY},
        transport=transport or _paged_transport(record))
    proposal = store.propose_contract(M.ext03_public_proposal(), proposed_by=REQUESTER)
    store.decide_contract(proposal["proposal_id"], approve=True, reviewed_by=APPROVER,
                          reason="공표 통계용")
    return {"store": store, "raw": raw, "orch": orch}


def _walk(rig):
    store, orch = rig["store"], rig["orch"]
    job = store.create(tenant_id="tenant_default", requested_by=REQUESTER,
                       subject_name="LS MnM", purpose="전력비 변동성",
                       request={"subject_name": "LS MnM", "purpose": "전력비 변동성",
                                "period_from": "2025", "period_to": "2025",
                                "indicators": ["SMP"],
                                "extras": {"provider_ids": ["KPX_SMP"]}})
    job = orch.discover(job["job_id"], actor_id=REQUESTER)
    job, dry = orch.dry_run(job["job_id"], actor_id=REQUESTER)
    job, applied = orch.apply(job["job_id"], actor_id=APPROVER)
    return {"job": job, "dry": dry, "applied": applied}


def test_the_orchestrator_collects_every_page(tmp_path):
    """★★★ `has_more` 를 안 읽으면 **첫 쪽만 받고 다 받았다고 보고한다.**"""
    calls = []
    rig = _rig(tmp_path, record=calls)
    out = _walk(rig)
    assert out["applied"].inserted == 25          # 10 + 10 + 5
    pages = [re.search(r"pageNo=(\d+)", u).group(1) for u in calls
             if "pageNo" in u]
    assert "1" in pages and "2" in pages and "3" in pages


def test_each_page_is_stored_as_its_own_raw_object(tmp_path):
    """⚠️⚠️ 쪽을 합쳐 하나의 「원문」으로 만들면 보관된 것이 **원천이 보낸 것이 아니게** 된다."""
    rig = _rig(tmp_path)
    out = _walk(rig)
    kept = rig["store"].raw_objects(out["job"]["job_id"])
    refs = {r["raw_object_ref"] for r in kept}
    assert len(refs) == 3
    for ref in refs:
        assert rig["raw"].verify(ref)["ok"] is True


def test_every_page_checksum_is_verified_not_just_the_last(tmp_path):
    """마지막 쪽만 보면 앞 쪽의 변조를 놓친다."""
    rig = _rig(tmp_path)
    out = _walk(rig)
    checksum_stage = next(s for s in out["applied"].stages if s.name == "CHECKSUM")
    assert checksum_stage.ok is True
    assert "3건 확인" in checksum_stage.detail


def test_the_page_count_is_visible_in_the_report(tmp_path):
    rig = _rig(tmp_path)
    out = _walk(rig)
    raw_stage = next(s for s in out["applied"].stages if s.name == "RAW_PRESERVED")
    assert "3쪽" in raw_stage.detail


def test_rejection_reasons_are_not_prefixed_with_the_page(tmp_path):
    """⚠️ 실측으로 어긋났다 — 사유 앞에 「1쪽: 」을 붙이자 사유로 세는 시험과 화면이
    전부 어긋났다. **사유는 비교 가능한 어휘**이고, 쪽은 상세에 넣는다."""
    rig = _rig(tmp_path, transport=_fixed_transport("smp_dirty.json"))
    store, orch = rig["store"], rig["orch"]
    job = store.create(tenant_id="tenant_default", requested_by=REQUESTER,
                       subject_name="LS MnM",
                       request={"subject_name": "LS MnM", "purpose": "전력",
                                "period_from": "2025", "period_to": "2025",
                                "indicators": ["SMP"],
                                "extras": {"provider_ids": ["KPX_SMP"]}})
    job = orch.discover(job["job_id"], actor_id=REQUESTER)
    job, dry = orch.dry_run(job["job_id"], actor_id=REQUESTER)
    reasons = [q["reason"] for q in dry.quarantined]
    assert "값을 숫자로 읽지 못함" in reasons        # 접두어가 붙지 않았다
    assert not any(r.startswith("1쪽") for r in reasons)


def test_paging_has_a_ceiling_in_two_layers():
    """★ 원천이 `has_more` 를 잘못 주면 영원히 돈다 — 층마다 상한을 둔다."""
    from core.external_intelligence import orchestrator as O
    assert O.MAX_COLLECT_PAGES > 0
    assert D.MAX_PAGES > 0


# ── 정규화·검증 ─────────────────────────────────────────────────────────────
def test_normalize_uses_the_declared_fields():
    p = _provider(_fixed_transport("smp_page1.json"))
    batch = p.normalize(p.fetch(_candidate(), page=1))
    assert len(batch.rows) == 10
    assert batch.rows[0]["indicator_code"] == "KPX_SMP"
    assert batch.rows[0]["unit"] == "KRW/kWh"
    assert batch.rows[0]["target_ref"] == "육지"


def test_regions_are_a_single_axis():
    """지역이 갈린다 — 섞으면 다른 시장이 한 지표로 뭉친다."""
    p = _provider(_fixed_transport("smp_dirty.json"))
    batch = p.normalize(p.fetch(_candidate(), page=1))
    report = p.validate(batch)
    assert report.ok is False
    assert "대상 단일" in {c.name for c in report.failures}


def test_unreadable_values_are_dropped_with_a_reason():
    p = _provider(_fixed_transport("smp_dirty.json"))
    batch = p.normalize(p.fetch(_candidate(), page=1))
    assert batch.accounted is True
    assert all(r["value"] is not None for r in batch.rows)
    assert [r.reason for r in batch.rejected].count("값을 숫자로 읽지 못함") == 2


def test_the_unverified_service_is_reported_without_blocking():
    """KOSIS 에서 배운 것 — 항상 실패하는 검사를 두지 않는다."""
    p = _provider(_fixed_transport("smp_page1.json"))
    batch = p.normalize(p.fetch(_candidate(), page=1))
    report = p.validate(batch)
    assert report.ok is True
    check = next(c for c in report.checks if "실측" in c.name)
    assert check.ok is True and "확인하지 못했습니다" in check.detail


def test_the_match_reason_warns_it_is_unverified():
    assert "실측으로 확인되지 않았습니다" in _candidate().match_reason


# ── 자격증명 ────────────────────────────────────────────────────────────────
def test_the_service_key_is_not_re_encoded():
    """⚠️ 발급되는 키는 **이미 인코딩된 값**이다 — 다시 인코딩하면 인증이 깨진다."""
    p = _provider()
    url = p._page_url(start="20250101", end="20251231", page=1, rows=10)
    assert f"serviceKey={KEY}" in url          # 그대로 들어간다
    assert "%252F" not in url                  # 이중 인코딩이 아니다


def test_the_key_never_reaches_the_result_or_the_raw_store(tmp_path):
    rig = _rig(tmp_path)
    out = _walk(rig)
    for row in rig["store"].raw_objects(out["job"]["job_id"]):
        meta = rig["raw"].meta(row["raw_object_ref"]) or {}
        assert KEY not in json.dumps(meta, ensure_ascii=False)


def test_missing_credential_names_the_variable():
    p = _provider(env={})
    with pytest.raises(B.ProviderCredentialError) as exc:
        p.discover(_request())
    assert "AFS_DATA_GO_KR_SERVICE_KEY" in str(exc.value)


def test_unknown_indicator_yields_no_candidate():
    assert _provider().discover(_request(indicators=("환율",))) == []


def test_period_is_required():
    with pytest.raises(B.ProviderError):
        _provider().discover(_request(period_from="", period_to=""))


# ── 순수성 ──────────────────────────────────────────────────────────────────
def test_pure_methods_do_not_touch_the_network():
    def explode(url, *, allowed_hosts, timeout=20.0):
        raise AssertionError("네트워크를 만졌다")

    p = _provider(_fixed_transport("smp_page1.json"))
    batch = p.normalize(p.fetch(_candidate(), page=1))
    pure = D.KpxSmpProvider(env={"AFS_DATA_GO_KR_SERVICE_KEY": KEY}, transport=explode)
    assert pure.validate(batch).ok
    cp = pure.checkpoint(batch)
    assert cp.covered_from == "2025-01-01"
    assert pure.refresh(cp)[0].params["start"] == "20250111"
