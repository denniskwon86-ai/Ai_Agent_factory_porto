"""★★★ 기획이 **호스팅 가능한 것**을 설계하는가. (2026-08-26 실측)

## ⚠️⚠️ 무엇이 있었나

실제 가동(`live-walk-02`)에서 Architect 가 이렇게 설계했다:

    백엔드 API 서버 … **경량 백엔드 프레임워크(예: Spring Boot)** 를 사용하여 구현합니다

그래서 공장은 `InboundApplication.java` · `schema.sql` 을 만들었고, 프론트 렌더 검증이
「App 루트가 없다」로 8회 반려한 뒤 `FAILED_REVIEW` 로 끝났다. **앱이 한 줄도 안 나왔다.**

그런데 `server.custom_logic`·`api.direct_call` 은 계약상 **금지**다. 즉 기획이 처음부터
**이 플랫폼이 만들 수 없는 것**을 설계했고, 아무도 그 사실을 알려 주지 않았다
(`architect_skill.md` 에 `afs.data` 언급 0회 · 오히려 「High FR 은 반드시 REST 엔드포인트로
설계하라」고 적혀 있었다).

★ 모델이 틀린 것이 아니다 — **못 만드는 것을 만들라고 시킨 것**이다. 같은 날 `capability`
  닫힌 목록에서 똑같은 일이 있었다(`test_tech_lead_contract_draft`).
"""
import os

import pytest


def _skill(name: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "skills", name), encoding="utf-8") as f:
        return f.read()


class _State:
    def __init__(self, profile: str):
        self.runtime_contract_profile = profile


# ══════════════════════════════════════════════════════════════════════════
# 고지문 자체
# ══════════════════════════════════════════════════════════════════════════

def test_금지_목록을_코드에서_읽어_싣는다():
    """⚠️ 손으로 옮겨 적으면 결정표가 바뀔 때 조용히 어긋난다. **코드가 원본**이다."""
    from core import app_runtime_brief as brief
    from core import app_runtime_contract as arc

    text = brief.render(_State("v1"))
    banned = [k for k, (s, _r) in arc.CAPABILITY_DECISION.items() if s == arc.PROHIBITED]
    assert banned, "금지 목록이 비어 있다 — 시험 전제가 깨졌다"
    missing = [k for k in banned if k not in text]
    assert not missing, "고지문에 없는 금지 능력: " + ", ".join(sorted(missing))


def test_호스트_대행_목록도_함께_알려_준다():
    """★ 「금지」만 알려 주면 모델은 그것을 우회할 방법을 설계한다. **호스트가 대신 해
    준다**는 사실까지 알려야 «그럼 어떻게 하나»에 답이 있다."""
    from core import app_runtime_brief as brief
    from core import app_runtime_contract as arc

    text = brief.render(_State("v1"))
    hosted = [k for k, (s, _r) in arc.CAPABILITY_DECISION.items()
              if s == arc.HOST_SERVICE_REQUIRED]
    missing = [k for k in hosted if k not in text]
    assert not missing, "고지문에 없는 호스트 대행 능력: " + ", ".join(sorted(missing))


def test_백엔드_서버를_설계하지_말라고_명시한다():
    """★★★ 실측에서 나온 바로 그 단어들. 추상적으로 「계약을 지키라」고만 하면
    모델은 Spring Boot 가 그 위반인 줄 모른다."""
    from core import app_runtime_brief as brief

    text = brief.render(_State("v1"))
    for word in ("Spring Boot", "REST"):
        assert word in text, f"«{word}» 를 짚어 주지 않는다 — 실측에서 그것이 나왔다"


def test_레거시_프로젝트에는_붙지_않는다():
    """⚠️⚠️ **대조군.** 계약 프로필이 꺼진 프로젝트는 자유 형식 앱을 만들어 왔다.
    거기에 이 제약을 걸면 멀쩡히 돌던 프로젝트가 깨진다."""
    from core import app_runtime_brief as brief

    assert brief.render(_State("")) == ""
    assert brief.applies(_State("")) is False
    assert brief.applies(_State("v1")) is True


def test_판정을_두_곳에서_하지_않는다():
    """⚠️ 계약을 거는 판정(`profile_enforces_contract`)과 고지하는 판정이 갈리면
    「계약은 거는데 알려 주지는 않는」 프로젝트가 생긴다 — 지금 그 상태였다."""
    import inspect

    from core import app_runtime_brief as brief

    src = inspect.getsource(brief.applies)
    assert "profile_enforces_contract" in src, "고지 판정을 따로 계산하고 있다"


# ══════════════════════════════════════════════════════════════════════════
# 실제로 프롬프트에 실리는가 — 「만들었는데 부르는 곳이 없다」를 다시 만들지 않는다
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("module,func", [
    ("nodes.execution", "run_architect"),
    ("nodes.ui_designer", "run_ui_designer"),
    ("nodes.planning", "run_master_pm"),
])
def test_기획_노드가_고지문을_실제로_붙인다(module, func):
    """⚠️⚠️ 이 저장소에서 **다섯 번째** 반복이라 시험으로 못박는다 — 고지문을 만들어
    두고 어디서도 부르지 않으면 아무 일도 일어나지 않는다."""
    import importlib
    import inspect

    mod = importlib.import_module(module)
    fn = getattr(mod, func, None)
    assert fn is not None, f"{module}.{func} 가 없다 — 이름이 바뀌었으면 시험도 고칠 것"
    src = inspect.getsource(fn)
    assert "app_runtime_brief" in src, f"{func} 가 런타임 고지문을 붙이지 않는다"


def test_아키텍트_스킬이_REST_지시와_충돌하지_않는다():
    """★★★ 한 프롬프트 안에 「반드시 REST 엔드포인트로 설계하라」와 「REST 를 설계하지
    말라」가 함께 있으면, 모델은 둘 중 하나를 **예측할 수 없게** 고른다.

    ⚠️ 스킬 파일은 레거시 프로젝트와 공유하므로 지우지 않는다 — 대신 **어느 쪽이
      우선인지**를 적어 둔다."""
    text = _skill("architect_skill.md")
    assert "런타임 계약 고지문이 함께 주어졌다면" in text, \
        "REST 지시와 런타임 계약 중 무엇이 우선인지 스킬이 말하지 않는다"
