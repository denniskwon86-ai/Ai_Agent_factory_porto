"""★★★ **없는 모델 이름은 기다려도 살아나지 않는다.** (2026-08-26 실측)

## ⚠️⚠️ 무엇이 있었나

완주 실측에서 103회 호출 중 **61%(26분)** 가 「죽은 사슬을 헛짚는 데」 나갔다. 계측 로그의
폴백 실패를 모델별로 세어 보니:

    gemini-2.5-pro   404 NOT_FOUND        28회   ← 쿼터가 아니라 **없는 이름**
    grok-2-latest    400 Model not found  24회   ← 같음
    gemini-pro-latest        RESOURCE_EXHAUSTED  ← 이건 쿼터(기다리면 산다)

쿨다운은 「쿼터(길게)」와 「일시적(짧게)」 둘만 알았다. **없는 이름**은 90초 뒤에도 없는데
매 walk 마다 다시 두들겼고, `GEMINI_MAX_RETRIES` 만큼 재시도까지 붙었다.

## 그런데 먼저 **재는 도구**가 틀려 있었다

폴백 실패 기록이 전부 `model: "?"` 였다 — `serialized["name"]` 도 `metadata` 도 비어서.
그래서 「어느 모델이 왜 죽는가」에 답할 수 없었다. 오류 본문에는 이름이 **그대로 적혀
있었으므로** 거기서 건져 내도록 고쳤다. 계측이 틀리면 그 위의 판단이 전부 틀린다.
"""
import re

import pytest

from core.llm_gateway import _DEAD_NAME_SIGNAL, _dead_model_names
from core.run_context import _model_from_error, record_fallback_error, reset_fallback_errors


# ══════════════════════════════════════════════════════════════════════════
# ① 재는 도구 — 오류 본문에서 이름을 건져 낸다
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("error,expected", [
    ("ChatGoogleGenerativeAIError: Error calling model 'gemini-2.5-pro' (NOT_FOUND): 404 …",
     "gemini-2.5-pro"),
    ("BadRequestError: Error code: 400 - {'code': 'invalid-argument', "
     "'error': 'Model not found: grok-2-latest'}", "grok-2-latest"),
    ("ChatGoogleGenerativeAIError: Error calling model 'gemini-pro-latest' "
     "(RESOURCE_EXHAUSTED): 429", "gemini-pro-latest"),
])
def test_오류_본문에서_모델_이름을_읽는다(error, expected):
    """★★★ 이것이 없으면 폴백 실패가 전부 «?» 로 쌓이고 아무것도 셀 수 없다."""
    assert _model_from_error(error) == expected


def test_이름이_없으면_지어내지_않는다():
    """⚠️ 못 찾았을 때 아무 이름이나 돌려주면, **엉뚱한 모델이 영구 배제**된다."""
    assert _model_from_error("ServerError: 503 UNAVAILABLE") == ""
    assert _model_from_error("") == ""


def test_상류가_이름을_주면_그것을_쓴다():
    """⚠️ 본문 파싱은 **마지막 수단**이다. 상류가 주는 값이 언제나 더 정확하다."""
    reset_fallback_errors()
    record_fallback_error("gemini-flash-latest",
                          "Error calling model 'something-else' (NOT_FOUND)")
    from core.run_context import get_fallback_errors
    assert get_fallback_errors()[0]["model"] == "gemini-flash-latest"


# ══════════════════════════════════════════════════════════════════════════
# ② 판정 — 「없는 이름」과 「쿼터 소진」을 가른다
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("error", [
    "ChatGoogleGenerativeAIError: Error calling model 'x' (NOT_FOUND): 404 NOT_FOUND",
    "BadRequestError: 400 - {'error': 'Model not found: x'}",
])
def test_없는_이름을_잡는다(error):
    reset_fallback_errors()
    record_fallback_error("x", error)
    assert _dead_model_names(["x"]) == {"x"}


@pytest.mark.parametrize("error", [
    "ChatGoogleGenerativeAIError: Error calling model 'x' (RESOURCE_EXHAUSTED): 429",
    "ServerError: 503 UNAVAILABLE",
    "ServerError: 504 DEADLINE_EXCEEDED. Stream cancelled",
    "AuthenticationError: Error code: 401",
    "JSONDecodeError: Expecting value: line 8",
])
def test_기다리면_살아나는_것을_영구_배제하지_않는다(error):
    """⚠️⚠️ **가장 위험한 오탐.** 쿼터·타임아웃·인증은 고치거나 기다리면 살아난다.
    영구 배제하면 그 모델을 이번 실행 내내 잃고, 사슬이 더 얇아져 오히려 느려진다."""
    reset_fallback_errors()
    record_fallback_error("x", error)
    assert _dead_model_names(["x"]) == set(), f"살아날 모델을 영구 배제했다: {error}"


def test_한_모델의_404가_다른_모델을_끌고_들어가지_않는다():
    """★★★ 판정은 **모델별 오류**로 해야 한다. 체인의 마지막 예외 하나로 판단하면
    A 가 404 이고 B 가 429 일 때 **살아 있는 B 까지** 영구 배제된다."""
    reset_fallback_errors()
    record_fallback_error("dead-one", "Error calling model 'dead-one' (NOT_FOUND): 404")
    record_fallback_error("alive-one", "Error calling model 'alive-one' (RESOURCE_EXHAUSTED): 429")
    assert _dead_model_names(["dead-one", "alive-one"]) == {"dead-one"}


def test_이름을_모르는_기록은_배제하지_않는다():
    """⚠️ «?» 를 배제 대상으로 삼으면 **아무 모델이나** 걸린다."""
    reset_fallback_errors()
    record_fallback_error("", "ServerError: 503")
    assert _dead_model_names(["?"]) == set()


def test_신호는_model_이라는_말과_함께_있을_때만_본다():
    """⚠️ 404 라고 다 없는 이름은 아니다. 넓게 잡으면 되돌리기 어려운 오탐이 된다."""
    assert not _DEAD_NAME_SIGNAL.search("HTTPError: 404 Not Found for url: https://x/y")


# ══════════════════════════════════════════════════════════════════════════
# ③ 배선 — 판정이 실제로 사슬에서 빼는가
# ══════════════════════════════════════════════════════════════════════════

def test_쿨다운_갱신이_영구_배제를_적용한다():
    """⚠️⚠️ 「만들어 두고 부르는 곳이 없다」의 **여덟 번째** 반복을 막는다."""
    import inspect

    from core import llm_gateway as g

    src = inspect.getsource(g.LLMGateway._update_cooldowns)
    assert "_dead_model_names" in src, "쿨다운이 영구 배제를 쓰지 않는다"
    assert "_DEAD_MODEL_COOLDOWN_SEC" in src
    #: ★ 조용히 빼면 설정이 틀린 채로 영원히 굴러간다 — 사람에게 말해야 한다.
    assert "config.py" in src or "설정" in src, "설정을 고치라고 알리지 않는다"


def test_영구_배제는_이번_실행_동안만이다():
    """★ 설정을 고치고 다시 띄우면 살아나야 한다 — 디스크에 굳히지 않는다."""
    import inspect

    from core import llm_gateway as g

    src = inspect.getsource(g)
    assert "self._dead_models = set()" in src, "프로세스 안의 집합이 아니다"
    assert not re.search(r"_dead_models[^\n]*json\.dump", src), "영구 배제를 파일에 굳혔다"
