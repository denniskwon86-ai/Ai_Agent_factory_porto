"""실행 주체·폴백 사유 계측 — **"누가 불렀고, 왜 다음 모델로 넘어갔나".**

## 왜 필요한가 (2026-07-29 카나리 실측)

카나리 36콜 중 **13콜(36%)이 `stage` 빈 값**이었다. `stage` 는 `ProjectState.current_stage`
에서 오는데 그것을 채우지 않는 노드가 있기 때문이다. 그 결과 폴백 4건 중 3건이 **어느 단계에서
났는지 알 수 없는 기록**으로 남았다 — 폴백 사유를 분석하려는 계측이 정작 "어디서"를 못 답한다.

상태에 의존하는 축(stage) 하나만 두면 상태가 비는 순간 계측도 함께 빈다.
**실행 중인 노드 이름**은 그래프가 아는 사실이므로 상태와 무관하게 남길 수 있다.

## 폴백 사유

LangChain 의 `with_fallbacks` 는 **개별 실패를 삼킨다**(성공하면 앞선 실패는 사라진다).
그래서 `attempts` 에는 "모델 5개를 거쳤다"까지만 남고 "왜 앞의 4개가 실패했는지"는 없었다.
`on_llm_error` 콜백으로 그 순간을 잡아 모델명과 오류 요약을 모은다.

⚠️ 두 값 모두 **contextvar** 다. 스웜은 에이전트 3개를 병렬로 돌리므로 모듈 전역에 담으면
서로의 기록이 섞인다.
"""
from contextvars import ContextVar
from typing import Any, Dict, List

_agent: ContextVar[str] = ContextVar("_agent", default="")
_fallback_errors: ContextVar[List[Dict[str, str]]] = ContextVar("_fallback_errors", default=None)


# ── 실행 주체 ────────────────────────────────────────────────────────────────
def set_agent(name: str) -> None:
    _agent.set(name or "")


def current_agent() -> str:
    return _agent.get() or ""


# ── 폴백 사유 ────────────────────────────────────────────────────────────────
def reset_fallback_errors() -> None:
    """호출 시작 시 비운다 — 안 비우면 앞 호출의 실패가 다음 호출에 붙는다."""
    _fallback_errors.set([])


def record_fallback_error(model: str, error: str) -> None:
    cur = _fallback_errors.get()
    if cur is None:
        cur = []
        _fallback_errors.set(cur)
    # 오류 문자열은 길고 대부분 중복이라 앞부분만 남긴다(로그 1줄이 수 KB 가 되면 아무도 안 본다).
    cur.append({"model": model or "?", "error": (error or "")[:200]})


def get_fallback_errors() -> List[Dict[str, str]]:
    return list(_fallback_errors.get() or [])


# ⚠️ [2026-07-29 사고] 이 콜백의 초판이 **A-1 재카나리를 두 번 죽였다.**
#   덕 타이핑으로 두고 `__getattr__` 이 모르는 속성에 `AttributeError` 를 던지게 했는데,
#   LangChain 내부가 `run_inline` 을 읽으면서 그대로 터졌다. 계측이 파이프라인을 죽인 것이다.
#   ★ 교훈: **상류가 무엇을 읽을지 우리가 열거할 수 있다고 가정하면 안 된다.** 속성 이름을
#     손으로 나열하는 방식은 상류 버전이 하나만 바뀌어도 같은 사고를 낸다.
#   → `BaseCallbackHandler` 를 **상속**한다(있으면). 그러면 상류가 요구하는 속성은 상류가 정의한
#     것을 그대로 쓰므로 열거할 필요가 없다. import 가 실패하는 환경에서만 덕 타이핑으로 내려간다.
try:                                            # pragma: no cover - 상류 경로는 환경에 따라 다르다
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCB
except Exception:                               # pragma: no cover
    try:
        from langchain.callbacks.base import BaseCallbackHandler as _BaseCB
    except Exception:
        _BaseCB = object


class FallbackErrorCollector(_BaseCB):
    """LangChain 콜백 — 체인 walk 중 실패한 모델과 사유를 수집한다.

    콜백에서 예외가 나면 **LLM 호출 자체가 죽는다.** 계측이 본체를 죽이면 안 되므로
    수집 로직은 전부 삼키고, 상류가 요구하는 인터페이스는 상속으로 충족한다."""

    raise_error = False       # 콜백 예외를 전파하지 않는다
    run_inline = False        # 별도 스레드 없이 인라인 실행(상류 내부 검사)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        try:
            serialized = kwargs.get("serialized") or {}
            name = ""
            if isinstance(serialized, dict):
                name = serialized.get("name") or ""
            meta = kwargs.get("metadata") or {}
            if not name and isinstance(meta, dict):
                name = meta.get("ls_model_name") or ""
            record_fallback_error(name, f"{type(error).__name__}: {error}")
        except Exception:
            pass

    def __getattr__(self, item):
        """상속으로도 없는 속성이 요구되면 **터지는 대신 무해한 기본값**을 준다.

        ⚠️ 초판은 여기서 `AttributeError` 를 던져 카나리를 죽였다. 계측 객체가 상류에게
          "그런 건 없다"고 답할 이유가 없다 — 모르면 '안 함/무시함'으로 답하는 것이 안전하다.
        (`__getattr__` 은 정상 조회가 실패했을 때만 불리므로 상속분 동작을 가리지 않는다.)"""
        if item.startswith("__"):
            raise AttributeError(item)          # 파이썬 프로토콜(dunder)까지 삼키면 오작동한다
        if item.startswith("on_"):
            return lambda *a, **k: None         # 알 수 없는 훅 → 아무것도 하지 않는다
        return False                            # ignore_*, run_inline 류 플래그 → 비활성
