"""★★★ [I-4 4c-7] 실행 가능한 릴리스는 **분류가 무엇이든** 계약을 지나야 한다.

이 시험이 전제하는 것: **조직도를 쓰지 않는다.** 게이트 판정은 릴리스 기록과
물질화 상태만 본다.

## 막으려는 경로

`artifact_kind` 는 기획이 **선언**한 값이라 유효하지만 틀릴 수 있다. LLM 이 실행
앱을 `REPORT` 로 분류하면 그 태스크는 계약 대상에서 빠지고, 만들어진 앱에는 계약이
**아예 없다** — 그러면 게이트의 「계약 없음 = 레거시」 경로로 조용히 열린다.

⚠️ 그 앱은 계약도 승인도 없이 데이터를 만지고, **아무 오류도 나지 않는다.**
★ 그래서 분류를 믿지 않고 **결과물**을 본다. 다만 계약 이전에 만든 판까지 막으면
  기존 앱이 전부 멈추므로, 경계는 릴리스가 들고 있는 `runtime_contract_profile` 이다.
"""
import pytest

from core import app_contract_gate as cg


def _release(**kw):
    base = {"project_id": "P1", "runtime_contract_profile": "v1",
            "manifest": {"fingerprint": "f", "manifest": {"app_class": "departmental",
                                                          "capabilities": ["ds:read"]}}}
    base.update(kw)
    return base


# ── 실행 가능한가 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("kind", ["APP", "SIMULATOR", "", "이상한값", None])
def test_anything_not_explicitly_exempt_is_executable(kind):
    """⚠️ 「모르면 면제」는 우회로다 — 판독 불가는 **실행 가능**으로 본다."""
    assert cg.is_executable_app_in_app(_release(artifact_kind=kind)) is True


def test_a_non_dict_release_is_executable():
    assert cg.is_executable_app_in_app(None) is True
    assert cg.is_executable_app_in_app("깨진 릴리스") is True


@pytest.mark.parametrize("kind", ["REPORT", "DOCUMENT", "LIBRARY"])
def test_a_declared_non_app_without_app_traces_is_exempt(kind):
    """★ 선언이 `REPORT` 이고 **실행 산출물의 흔적도 없으면** 실행 앱이 아니다."""
    rel = _release(artifact_kind=kind, manifest={}, view_type="")
    assert cg.is_executable_app_in_app(rel) is False


@pytest.mark.parametrize("kind", ["REPORT", "DOCUMENT", "LIBRARY"])
def test_a_declared_non_app_with_capabilities_is_still_executable(kind):
    """★★★ **선언만으로 면제하지 않는다.** 매니페스트에 권한이 선언돼 있으면 그 앱은
    데이터를 만지겠다고 말한 것이고, 선언이 틀린 것이다."""
    assert cg.is_executable_app_in_app(_release(artifact_kind=kind)) is True


@pytest.mark.parametrize("kind", ["REPORT", "DOCUMENT", "LIBRARY"])
def test_a_declared_non_app_with_a_view_is_still_executable(kind):
    """화면이 있으면 사람이 실행한다 — 그것이 App-in-App 이다."""
    rel = _release(artifact_kind=kind, manifest={}, view_type="react_app")
    assert cg.is_executable_app_in_app(rel) is True


def test_the_explicit_exception_mode_is_honoured():
    """★ 설계 §4 의 **명시적 예외 모드** — 사람이 「Host 런타임을 쓰지 않는다」고 적은 판.

    ⚠️ 이것만이 유일한 면제다. 사람이 적었다는 것 자체가 근거이고, 그래서 감사할 수 있다."""
    assert cg.is_executable_app_in_app(
        _release(requires_host_runtime=False)) is False
    #: ⚠️ `True` 나 없는 값은 면제가 아니다 — 「명시적」이란 그런 뜻이다
    assert cg.is_executable_app_in_app(_release(requires_host_runtime=True)) is True
    assert cg.is_executable_app_in_app(_release()) is True


# ── 릴리스가 든 프로필 ──────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("v1", "v1"), ("V1", "v1"), (" v1 ", "v1"),
    ("", ""), (None, ""), ("v2", ""), (1, ""), ({"v": 1}, ""),
])
def test_release_profile_is_read_fail_open(raw, expected):
    """⚠️ 여기만 fail-**open** 이다. 판독 실패를 「계약 필요」로 떨어뜨리면 계약
    이전에 만든 **모든 판**이 즉시 막힌다 — 4c-0 과 같은 비대칭이고 같은 이유다."""
    assert cg.release_contract_profile(_release(runtime_contract_profile=raw)) == expected


def test_a_release_without_the_key_reads_as_legacy():
    rel = {"project_id": "P1"}
    assert cg.release_contract_profile(rel) == ""


# ── 게이트 판정 ─────────────────────────────────────────────────────────
class _Bound(dict):
    pass


@pytest.fixture
def no_bindings(monkeypatch):
    """물질화는 비어 있다 — 계약 유무만 보이게 한다."""
    monkeypatch.setattr(cg, "_materialized", lambda rid: {})
    monkeypatch.setattr(cg.app_data_service, "materialization_fingerprint",
                        lambda rid: "m" * 64, raising=False)


def test_a_v1_executable_release_without_a_contract_is_blocked(no_bindings):
    """★★★ 이것이 4c-7 의 전부다 — 잘못 분류된 `REPORT` 가 계약을 피하는 경로."""
    v = cg.evaluate(_release(artifact_kind="REPORT"), "rel_1")
    assert v.ok is False
    assert v.legacy is False
    assert "실행 가능한 앱인데 승인된 런타임 계약이 없습니다" in " ".join(v.reasons)


def test_a_legacy_release_without_a_contract_still_opens(no_bindings):
    """★ 계약 이전에 만든 판은 그대로 연다 — 여기가 깨지면 기존 앱이 전부 멈춘다."""
    v = cg.evaluate(_release(runtime_contract_profile=""), "rel_1")
    assert v.ok is True
    assert v.legacy is True
    assert v.contract_fingerprint == cg.NO_CONTRACT


def test_a_v1_non_executable_release_without_a_contract_opens(no_bindings):
    """★ `v1` 프로젝트라도 **실행 앱이 아니면** 계약이 필요 없다 — 보고서는 보고서다."""
    rel = _release(artifact_kind="REPORT", manifest={}, view_type="")
    v = cg.evaluate(rel, "rel_1")
    assert v.ok is True and v.legacy is True


def test_the_explicit_exception_mode_opens_even_under_v1(no_bindings):
    v = cg.evaluate(_release(requires_host_runtime=False), "rel_1")
    assert v.ok is True and v.legacy is True


def test_a_rogue_binding_still_blocks_before_the_new_rule(no_bindings, monkeypatch):
    """⚠️ 「계약은 없는데 결속은 있다」가 먼저다 — 그것은 **물질화가 승인보다 앞선**
    상태이고, 새 규칙과 다른 사실이다. 두 사유가 섞이면 원인을 못 찾는다."""
    monkeypatch.setattr(cg, "_materialized", lambda rid: {"production": {"bound": 1}})
    v = cg.evaluate(_release(runtime_contract_profile=""), "rel_1")
    assert v.ok is False
    assert "승인된 계약이 없는데 계약 결속이 있습니다" in " ".join(v.reasons)


@pytest.mark.parametrize("kind", ["이상한값", "app", "SIM", None, 7])
def test_an_unknown_kind_is_executable_even_without_any_app_traces(kind):
    """★★★ **모르는 분류는 면제가 아니다.**

    ⚠️ 「APP·SIMULATOR 가 아니면 면제」로 뒤집으면 오타 하나가 통제를 끄는 스위치가
      된다. 면제되는 것은 **적어 둔 세 값**뿐이고, 그 밖은 전부 실행 가능으로 본다.
    ★ 흔적(권한·화면)이 하나도 없어도 그렇다 — 흔적은 «면제 선언을 뒤집는» 근거이지
      «면제를 주는» 근거가 아니다."""
    rel = _release(artifact_kind=kind, manifest={}, view_type="")
    assert cg.is_executable_app_in_app(rel) is True


@pytest.mark.parametrize("value", [0, "", None, "false", "False", [], {}])
def test_only_a_real_false_is_an_explicit_exemption(value):
    """★★★ **「명시적」은 `False` 하나를 뜻한다.**

    ⚠️ 거짓 같은 값(`0`·`""`·`None`)까지 면제로 읽으면, 필드를 비워 둔 릴리스가
      면제를 얻는다 — 그것은 사람이 판단해 적은 것이 아니라 **빠뜨린 것**이다.
      그리고 빠뜨림으로 얻는 면제는 감사할 수 없다."""
    rel = _release(requires_host_runtime=value, manifest={}, view_type="")
    assert cg.is_executable_app_in_app(rel) is True, (
        f"{value!r} 를 명시적 예외로 읽었다 — `False` 만 면제다")


def test_the_release_writer_seals_the_profile():
    """★★★ 릴리스가 **자기 안에** 프로필을 들고 있어야 한다.

    ⚠️ 프로젝트 메타는 나중에 바뀐다. 릴리스가 들고 있지 않으면 「이 판이 계약
      절차를 지나야 했는가」가 그때그때 달라지고, 게이트 판정이 흔들린다.
    ⚠️ 이 규칙은 게이트 쪽에서 관찰되지 않는다(게이트는 이미 쓰인 값을 읽을 뿐이다).
      그래서 **쓰는 자리**를 구조로 잠근다 — 변이 검사에서 이 줄을 지워도 아무
      시험이 깨지지 않았다."""
    import ast
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.release_project) if hasattr(fc, "release_project") else ""
    if not src:
        #: 함수 이름이 바뀌었을 수 있다 — 모듈 전체에서 찾는다
        src = inspect.getsource(fc)
    assert 'release["runtime_contract_profile"]' in src, (
        "릴리스에 계약 프로필을 봉인하지 않는다")
    assert "_read_project_runtime_contract_profile" in src, (
        "프로필을 프로젝트 정본에서 읽지 않는다")
