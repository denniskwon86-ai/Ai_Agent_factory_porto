"""[R01.1] 앱이 요구하는 출처가 **실제 경로**에 연결되는가. 미지원은 조용히 접히지 않는가.

기존 `tests/test_provider_dispatch.py` 는 `host_runtime_provider.resolve()` 를 **단위로**
부른다. 여기서 보는 것은 그 앞단 — `api/routes/app_data_runtime._dispatch()` 라는 **실제
요청이 지나가는 자리**다. 그 자리는 지금까지 HTTP 시험으로만 간접 확인됐고, 그 HTTP 시험은
이 환경에서 픽스처 문제로 깨져 있다(`MaterializeError: arrivals` 10건, 범위 밖).

⚠️ **대상 7앱의 실제 요구는 실측하지 못했다.** 이 PC 에는 `library/` 가 0건이다. 여기서는
  「의도 4종이 실제 경로에서 어떻게 처리되는가」까지만 본다.
"""
import pytest
from fastapi import HTTPException

from api.routes import app_data_runtime as adr
from core import app_runtime_contract as arc
from core import host_runtime_provider as prov
from core import host_runtime_sdk as sdk


class _Plane:
    """`_dispatch` 가 결속을 얻는 유일한 창구. 여기만 대신하면 단위로 부를 수 있다."""

    def __init__(self, binding):
        self._binding = binding

    def binding_for(self, release_id, dataset_id):
        return self._binding


def _dispatch_with(monkeypatch, binding):
    monkeypatch.setattr(adr, "_plane", lambda proof: _Plane(binding))
    #: `p=None` 은 계약 이전 경로다 — 2.0 봉인 대조를 타지 않고 결속만 본다.
    return adr._dispatch({"release_id": "rel_r01", "tenant_id": "t", "scope_node_id": "n",
                          "entity_mode": "REAL"},
                         {"dataset_id": "ds_r01"}, p=None)


def test_the_two_support_tables_say_the_same_thing():
    """★★ 「이 출처가 지금 되는가」가 **두 곳**에 적혀 있다 — 갈리면 사고가 조용하다.

    · `app_runtime_contract.SOURCE_INTENT_DECISION` — **앱을 만들 때** 보는 표
    · `host_runtime_provider.SERVING_PROVIDERS`      — **앱이 돌 때** 보는 표

    한쪽만 열면 **앱은 만들어지는데 실행이 거절**되고(또는 그 반대), 어느 쪽도 오류를
    미리 내지 않는다. 지금은 일치하므로, 갈리는 순간 여기서 걸리게 고정한다.
    """
    for intent, (decision, _message) in arc.SOURCE_INTENT_DECISION.items():
        provider = prov.provider_for_intent(intent)
        assert provider, f"계약이 아는 의도 {intent} 를 provider 표가 모른다"
        serving = provider in prov.SERVING_PROVIDERS
        assert (decision == arc.SUPPORTED) is serving, (
            f"{intent}: 계약 표는 {decision!r} 인데 실행 표는 "
            f"{'서빙함' if serving else '서빙 안 함'} — 두 표가 갈렸다")


def test_every_declared_intent_is_known_to_the_runtime():
    """계약이 선언한 의도는 전부 실행 표에 대응이 있어야 한다. 없으면 실행 시 사라진다."""
    for intent in arc.SOURCE_INTENT_DECISION:
        assert prov.provider_for_intent(intent) in prov.PROVIDERS


def test_a_supported_intent_reaches_its_provider(monkeypatch):
    """지원 의도는 실제 경로에서 **그 provider 로 간다.**"""
    res = _dispatch_with(monkeypatch, {"source_intent": arc.AFS_NATIVE})
    assert res.provider == prov.NATIVE


def test_a_legacy_binding_without_an_intent_is_native_by_contract(monkeypatch):
    """★ 출처를 말한 적 없는 **옛 결속**은 Native 다 — 폴백이 아니라 그 시절 계약의 뜻이다.

    ⚠️ 주의해서 읽을 것: `provider_for_intent("")` 는 **거절**한다(모르면 우리 DB 금지).
      같은 빈 값에 두 곳이 다르게 답하는 자리이므로, 의도된 차이임을 여기 고정해 둔다.
      이 시험이 깨졌다면 둘 중 하나가 말없이 바뀐 것이다.
    """
    assert prov.provider_for_intent("") == "", "모르는 의도가 provider 를 얻었다"
    res = _dispatch_with(monkeypatch, {"source_intent": ""})
    assert res.provider == prov.NATIVE
    assert res.dataset_contract_key == "" and res.binding is None


@pytest.mark.parametrize("intent", [arc.EXTERNAL_REFERENCE, arc.DERIVED_READ])
def test_an_unsupported_intent_is_refused_on_the_real_path(monkeypatch, intent):
    """★★ 아직 못 하는 출처는 실제 경로에서 **거절**된다 — 빈 표가 아니다.

    빈 목록으로 답하면 앱이 화면에서 그 표를 지우고 사용자는 「데이터가 사라졌다」로 읽는다.
    """
    assert arc.SOURCE_INTENT_DECISION[intent][0] != arc.SUPPORTED, "전제가 바뀌었다"
    with pytest.raises(HTTPException) as caught:
        _dispatch_with(monkeypatch, {"source_intent": intent})
    assert caught.value.status_code >= 400

    #: ⚠️ 위 단언만으로는 **왜** 거절했는지 모른다 — 「미지원이라서」와 「계약 키가 없어서」가
    #:   같은 코드로 나온다. 처음에 그렇게 썼다가, 지원 표를 한쪽만 여는 변이에서도 이 시험이
    #:   초록인 것을 보고 조였다. 이유는 한 단계 아래에서 확인한다(앱에는 코드만 가므로).
    with pytest.raises(prov.ProviderError) as lower:
        prov.resolve(source_intent=intent, dataset_contract_key="k_r01",
                     binding=None, snapshots=[], now="2026-09-22T00:00:00+00:00")
    assert lower.value.reason == prov.NOT_YET_SUPPORTED, \
        f"{intent} 가 «지원 대기» 가 아닌 다른 이유로 거절됐다: {lower.value.reason}"


def test_an_unknown_intent_does_not_become_our_own_db(monkeypatch):
    """오타·손상된 의도가 Native 로 흘러 들어가지 않는다."""
    with pytest.raises(HTTPException):
        _dispatch_with(monkeypatch, {"source_intent": "NO_SUCH_INTENT"})


@pytest.mark.parametrize("intent", [arc.EXTERNAL_REFERENCE, arc.DERIVED_READ, "NO_SUCH_INTENT"])
def test_the_refusal_never_names_the_provider_or_the_reason(monkeypatch, intent):
    """★ 거절 문구에 **provider 이름도 내부 사유도** 실리지 않는다.

    사유(지원 대기·승인 전·격리)는 그 앱을 쓰는 사람이 볼 수 없는 조직의 내부 상태다.
    """
    with pytest.raises(HTTPException) as caught:
        _dispatch_with(monkeypatch, {"source_intent": intent})
    body = str(caught.value.detail)
    for leaked in (prov.CONNECTOR_QUERY, prov.DERIVED, prov.FILE_SNAPSHOT,
                   prov.NOT_YET_SUPPORTED, "source_intent", intent):
        assert leaked not in body, f"{leaked} 가 앱에 가는 문구로 샜다"


def test_a_source_store_failure_is_not_an_empty_table(monkeypatch):
    """원천 저장소가 죽으면 **빈 목록이 아니라 실패**다 — 0건은 「없다」로 읽힌다."""
    import core.data_preparation.store as store_module

    class _Broken:
        def active_binding(self, *a, **k):
            raise RuntimeError("원천 저장소 장애")

        def list_snapshots(self, *a, **k):
            raise RuntimeError("원천 저장소 장애")

    monkeypatch.setattr(store_module, "data_preparation_store", _Broken())
    with pytest.raises(HTTPException) as caught:
        _dispatch_with(monkeypatch, {"source_intent": arc.ENTERPRISE_READ,
                                     "enterprise_contract_key": "k_r01",
                                     "kit_instance_id": "ki_r01"})
    assert caught.value.status_code >= 400
    assert "장애" not in str(caught.value.detail), "내부 사유가 앱에 갔다"


def test_only_native_can_be_written_through_the_real_path(monkeypatch):
    """쓰기는 Native 한 곳뿐이다 — 실제 경로에서도 같다."""
    native = _dispatch_with(monkeypatch, {"source_intent": arc.AFS_NATIVE})
    adr._assert_native_write(native, {"dataset_id": "ds_r01"}, path="POST /records")

    snapshot = prov.Resolution(prov.FILE_SNAPSHOT, "k", None, None, False, "")
    with pytest.raises(HTTPException):
        adr._assert_native_write(snapshot, {"dataset_id": "ds_r01"}, path="POST /records")
