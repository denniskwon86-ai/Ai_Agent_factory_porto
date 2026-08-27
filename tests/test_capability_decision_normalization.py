"""★★★ 목록 밖 결정 — **결과가 같으면 바로잡고, 다르면 막는다.** (2026-08-27 실측)

## ⚠️⚠️ 무엇이 있었나

새 프로젝트(`CRM002`)를 돌렸더니 Tech Lead 가 `file.upload`(지원 대기)에
`REQUEST_HOST_FEATURE` 를 적었다. 능력 이름은 맞았고 **결정만 목록 밖**이었다.

    file.upload: 지원 대기 에는 REQUEST_HOST_FEATURE 를 고를 수 없습니다
                 (가능: ['REDUCE', 'WAIT'])

그래서 8개 태스크짜리 프로젝트가 **첫 태스크에서 세 번 연속** 멈췄다. 그동안 나는

  ① 스킬 문구를 고쳤고(「상태를 적지 마라」),
  ② 닫힌 목록과 허용 결정을 **코드에서 렌더링**해 프롬프트에 붙이기까지 했다.

프롬프트에 실제로 들어간 것을 확인했는데도 모델은 **같은 값을 세 번** 골랐다.
★ 설득은 차단기가 아니다 — 안 들으면 아무 일도 일어나지 않는다([[notice-is-not-a-blocker]]).

## 왜 «바로잡기» 가 통제를 무르게 하지 않는가

`NOT_YET_SUPPORTED` 에서 `WAIT` 과 `REQUEST_HOST_FEATURE` 는 **안전 결과가 같다** —
어느 쪽이든 그 능력은 만들어지지 않고 앱은 그 기능 없이 나온다. 목록이 후자를 뺀 것은
「지원 예정인 것을 다시 요청하지 말라」는 정리이지 경계가 아니다.

⚠️⚠️ `PROHIBITED` 는 다르다. 거기서 `REQUEST_HOST_FEATURE` 는 **「금지된 것을 열어
  달라」는 요청**이고, 그것이야말로 이 관문이 막으려는 것이다. 그래서 이 파일은
  **양쪽을 다** 본다 — 한쪽만 보면 「전부 바로잡기」로 고쳐 놓아도 초록이 된다.
"""
import pytest

from core import app_runtime_contract as arc
from core import host_contract_compiler as hcc


def _compile(capability: str, decision: str):
    """초안 하나를 컴파일하고 `(확정된 결정, 오류들)` 을 돌려준다."""
    intents, errors = hcc._compile_intents({"capability_intents": [
        {"capability": capability, "user_decision": decision,
         "requirement_ref": "FR-X"}]})[:2]
    return (intents[0].get("user_decision") if intents else None), errors


# ── 바로잡는 자리 ────────────────────────────────────────────────────────

def test_지원대기의_기능요청은_WAIT_으로_바로잡힌다():
    """★★★ **이 파일의 요지.** 실측에서 세 번 연속 막힌 값이 정확히 이것이다."""
    decision, errors = _compile("file.upload", "REQUEST_HOST_FEATURE")
    assert decision == "WAIT", f"바로잡히지 않았다: {decision!r}"
    assert not errors, f"바로잡았는데 오류가 남았다: {errors}"


def test_바로잡아도_그_능력은_만들어지지_않는다():
    """★★★ 바로잡기가 **안전 결과를 바꾸지 않는지**를 본다.

    ⚠️ 이것이 없으면 「막던 것을 통과시켰다」와 「같은 결과를 다른 이름으로 적었다」를
      구분하지 못한다 — 전자라면 이 변경은 통제를 무르게 한 것이다."""
    status, _reason = arc.decide("file.upload")
    assert not arc.is_buildable(status), (
        "지원 대기가 만들 수 있는 상태가 됐다 — 바로잡기의 전제가 무너졌다")


# ── ⚠️ 막는 자리 — 여기가 무너지면 안 된다 ──────────────────────────────

@pytest.mark.parametrize("capability", sorted(
    k for k, (s, _r) in arc.CAPABILITY_DECISION.items() if s == arc.PROHIBITED))
def test_금지_능력의_기능요청은_여전히_막힌다(capability):
    """★★★ 금지 항목에서 `REQUEST_HOST_FEATURE` 는 **「금지된 것을 열어 달라」**다.

    ⚠️ 닫힌 목록 **전체**에 대해 돈다 — 하나만 보면 새 금지 항목이 추가된 날
      그 항목만 조용히 새는 것을 못 잡는다."""
    decision, errors = _compile(capability, "REQUEST_HOST_FEATURE")
    assert errors, f"{capability}: 금지 항목의 기능 요청이 통과했다"
    assert not decision, f"{capability}: 막혔는데 결정이 남았다: {decision!r}"


def test_금지_능력의_REDUCE_는_통과한다():
    """★ 대조군 — 이것이 없으면 위 시험은 「금지는 항상 막힌다」만 증명한다."""
    decision, errors = _compile("auth.local_login", "REDUCE")
    assert decision == "REDUCE" and not errors, (decision, errors)


def test_호스트기능_필요의_기능요청은_원래_허용이다():
    """★ 대조군 — 바로잡기가 **엉뚱한 곳을 건드리지 않았는지.**"""
    decision, errors = _compile("server.custom_logic", "REQUEST_HOST_FEATURE")
    assert decision == "REQUEST_HOST_FEATURE" and not errors, (decision, errors)


def test_지원대기의_REDUCE_는_그대로다():
    """★ 바로잡기가 **이미 맞는 값을 덮지 않는지.**"""
    decision, errors = _compile("file.upload", "REDUCE")
    assert decision == "REDUCE" and not errors, (decision, errors)


# ── 범위가 좁은가 ────────────────────────────────────────────────────────

def test_바로잡기는_지원대기_한_상태에만_적용된다():
    """★★★ 조건을 넓히면 이 자리가 **통제를 무르게 하는 문**이 된다.

    ⚠️ 상태 이름을 조건에 박아 두었는지를 코드로 확인한다 — 「결과가 같으면」 같은
      일반 규칙으로 쓰면 다음 사람이 PROHIBITED 를 거기 넣는다."""
    import inspect

    src = inspect.getsource(hcc._compile_intents)
    i = src.index("WAIT 으로 바로잡습니다")
    around = src[max(0, i - 900):i]
    assert "arc.NOT_YET_SUPPORTED" in around, (
        "바로잡기 조건이 상태 하나로 좁혀져 있지 않다")


def test_다른_목록밖_값은_여전히_막힌다():
    """⚠️ 지어낸 결정값까지 통과시키면 결정 자체가 닫힌 목록이 아니게 된다."""
    decision, errors = _compile("file.upload", "그냥_만들어_주세요")
    assert errors, "목록에 없는 임의 결정이 통과했다"
    assert not decision
