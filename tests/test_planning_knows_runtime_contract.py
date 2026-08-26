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
    #: ★★★ [2026-08-26 실측] **사슬의 첫 칸과 마지막 칸이 빠져 있었다.**
    #:   요구사항을 처음 적는 곳(RFP)에서 「사용자 로그인」이 들어가면 뒤 단계는 받아쓰고,
    #:   WBS 를 쪼개는 곳(PMO)에서 새로 만들면 앞이 깨끗해도 소용없다.
    #:   실제로 TEST001 에 「로그인·권한 관리」 태스크가 생겼다 — 계약 단계에서 금지로
    #:   막히므로 **처음부터 만들 수 없는 것을 계획한 것**이다.
    ("nodes.planning", "run_rfp_analyst"),
    ("nodes.planning", "run_master_pmo"),
    #: ★★★ [2026-08-26 실측] **코드를 쓰는 끝 칸이 빠져 있었다.** 기획이 옳아도 개발자가
    #:   없는 API 를 부르면 앱은 안 돈다 — 실제로 `window.afs.auth` 를 지어내 화면이
    #:   첫 줄에서 멈췄다. 완주는 했는데 앱이 안 떴다.
    ("nodes.execution", "run_developer_fe"),
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


def test_사용자가_이미_로그인되어_있음을_알려_준다():
    """★★★ **[2026-08-26 사용자 지적] 「하지 마라」만으로는 부족했다.**

    금지 목록에 `auth.local_login` 이 있었는데도 기획은 「사용자 로그인」을 요구사항으로
    남겼다. 모델 입장에서는 **요구는 있는데 금지된 상태**이므로 우회로를 찾는다.

    ★ 필요한 것은 **사실**이다: 이 앱은 회사 시스템 «안에서» 열리고(앱인앱), 사용자는
      이미 인증돼 있으며 권한도 이미 정해져 있다. 그러면 요구는 **이미 충족된 것**이 된다.
    """
    from core import app_runtime_brief as brief

    text = brief.render(_State("v1"))
    assert "이미 로그인되어 있습니다" in text, "이미 인증된 상태라는 사실을 안 알려 준다"
    assert "앱인앱" in text, "왜 그런지(앱인앱)를 안 알려 준다"
    for word in ("로그아웃", "권한 관리"):
        assert word in text, f"«{word}» 를 짚어 주지 않는다 — 실측에서 그것이 나왔다"


def test_요구를_거절하지_말고_충족된_것으로_다루라고_한다():
    """⚠️ 「사용자가 요청해도 만들지 마라」로만 적으면 모델은 요구를 **삭제**하거나
    거절 문구를 남긴다. 사용자는 자기 요구가 사라진 것을 보게 된다.
    ★ 「이미 충족됐다」로 적으라고 해야 요구 추적이 끊기지 않는다."""
    from core import app_runtime_brief as brief

    text = brief.render(_State("v1"))
    assert "이미 충족된 것" in text


# ══════════════════════════════════════════════════════════════════════════
# 호스트 표면 — **있는 것과 없는 것을 둘 다** 알려 준다 (2026-08-26 실측)
# ══════════════════════════════════════════════════════════════════════════

def test_호스트가_주는_것을_전부_알려_준다():
    """★★★ **실측: 앱이 `window.afs.auth` 를 지어내 첫 줄에서 멈췄다.**

    `SDK_SURFACE` 는 **이미 코드에 있었고 시험까지 있었다.** 그런데 그것을 에이전트에게
    알려 주는 곳이 **0곳**이었다 — 오늘 `capability` 닫힌 목록·`data_role` 에서 반복된
    것과 정확히 같은 모양이다."""
    from core import app_runtime_brief as brief
    from core import host_runtime_sdk as sdk

    text = brief.render(_State("v1"))
    missing = [n for n in sdk.SDK_SURFACE if n not in text]
    assert not missing, "고지문에 없는 호스트 표면: " + ", ".join(missing)


def test_없는_것도_이름으로_알려_준다():
    """⚠️ 「있는 것만」 알려 주면 모델은 없는 것을 **있다고 가정**한다. 이름을 적어 두어야
    지어내지 않는다 — `host_runtime_sdk` 가 `FORBIDDEN_SURFACE` 를 둔 이유와 같다."""
    from core import app_runtime_brief as brief
    from core import host_runtime_sdk as sdk

    text = brief.render(_State("v1"))
    missing = [n for n in sdk.FORBIDDEN_SURFACE if n not in text]
    assert not missing, "고지문에 없는 금지 표면: " + ", ".join(missing)
    assert "afs.auth" in text, "실측에서 지어낸 바로 그 이름이 빠졌다"


def test_데이터셋_이름이_인자임을_알려_준다():
    """★★★ 이름만 주면 모델은 **속성**으로 부른다 — 실측에서 `data.<데이터셋>.list()` 로
    불렀고 호스트에는 그런 것이 없다. 호출 모양을 함께 줘야 한다."""
    from core import app_runtime_brief as brief

    text = brief.render(_State("v1"))
    assert "window.afs.data.list(datasetName" in text, "호출 인자 모양을 안 알려 준다"
    assert "속성이 아닙니다" in text


def test_인자_모양을_손으로_적지_않는다():
    """⚠️ 셔임이 바뀌면 고지문도 따라가야 한다. `OPS` 에서 **파생**하지 않고 옮겨 적으면
    조용히 어긋난다."""
    import inspect

    from core import app_runtime_brief as brief

    src = inspect.getsource(brief._surface_lines)
    assert "sdk.OPS[" in src, "인자 모양을 코드에서 파생하지 않는다"


def test_레거시에는_표면_고지도_안_붙는다():
    """⚠️ 대조군 — 계약을 안 타는 프로젝트는 종전대로 동작해야 한다."""
    from core import app_runtime_brief as brief

    assert brief.render(_State("")) == ""
