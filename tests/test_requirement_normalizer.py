"""★★★ 요구가 **들어오는 자리**에서 「이미 충족된 것」을 못박는다. (2026-08-27)

## ⚠️⚠️ 왜 입구인가 — 뒤에서 잡으려다 두 시간을 태웠다

사용자 아이디어에 「사용자 로그인과 권한 관리를 포함한다」가 들어왔고, 파이프라인은
그것을 안고 끝까지 돌았다(RFP Must → WBS 태스크 → 계약에서 말없이 증발 → 5태스크 더).

뒤의 세 겹이 전부 못 막은 이유는 각각 다르다 — 그리고 **셋 다 같은 뿌리**다:

  ① `debate.run_debate` 는 `extra_instruction`(플랫폼 고지문)을 **작성자에게만** 붙인다.
     비평가는 이 플랫폼이 무엇을 못 만드는지 모른 채 비평한다.
  ② 채점 8단계 35개 검사 중 「만들 수 있는가」는 **0개**, 완성도·추적성은 **7개**다.
     `must_have_components` 는 「빠짐없이 있는가」를 보므로 **포함을 보상**했다.
  ③ `context_engine` 은 `initial_idea` 를 모든 에이전트 문맥에 `[초기 기획]` 으로 넣는다.
     원문이 «목표» 로 매 단계에 뿌려지는데 고지문은 뒤에 붙는 부록이었다.

⇒ **측정되는 것과 부탁하는 것이 싸우면 측정되는 쪽이 이긴다.** 부탁을 늘리는 대신
  목표 자체를 고친다.

## 이 파일이 지키는 것

  · 원문을 **지우지 않는다** — 지우면 사용자가 자기 요청이 어디 갔는지 모른다
  · 목록을 **손으로 적지 않는다** — 컴파일러가 막는 닫힌 목록에서 읽는다
  · **두 번 붙지 않는다** — `start_sprint` 는 태스크마다 불린다
  · 레거시(계약 프로필 꺼짐)에는 **붙지 않는다**
"""
import pytest

from core import app_runtime_contract as arc
from core.requirement_normalizer import (MARKER, already_applied, normalize_idea,
                                         render_clause)

_IDEA = ("거래처 관리 시스템. 거래처 정보를 등록·조회·수정·삭제하고, "
         "목록을 검색·필터링한다. 사용자 로그인과 권한 관리를 포함한다.")


# ── 원문 보존 ────────────────────────────────────────────────────────────

def test_원문을_지우지_않는다():
    """★★★ 지우면 사용자는 자기가 요청한 것이 어디 갔는지 알 수 없고,
    완성도 검사도 「빠졌다」로 깎는다."""
    out = normalize_idea(_IDEA, enforced=True)
    assert out.startswith(_IDEA), "원문이 바뀌었다"
    assert "사용자 로그인과 권한 관리를 포함한다" in out


def test_지시문이_붙는다():
    """★ [2026-08-27 2차] 문구를 지시문으로 바꾸면서 이 단언도 같이 옮겼다 —
    옛 문구(「이미 제공」)를 계속 단언하면 시험이 옛 계약을 지키게 된다."""
    out = normalize_idea(_IDEA, enforced=True)
    assert MARKER in out
    assert "이미 수행합니다" in out, "A무리(회사 시스템이 수행)가 없다"
    assert "본 프로젝트 구현 범위 아님" in out, "복사할 문장이 없다"


def test_출구로_적을_문장을_그대로_준다():
    """★★★ 「지우라」가 아니라 **복사해 쓸 문장**을 준다.

    ⚠️ [2026-08-27 2차] 1차 문구는 「~로 적으면 됩니다」였다 — 허용문이라 지시가 아니고
      **어디에** 적으라는 것도 없었다. 문장을 통째로 주고 위치를 지정한다."""
    clause = render_clause()
    assert "호스트 시스템이 수행함. 본 프로젝트 구현 범위 아님." in clause, (
        "그대로 복사할 문장이 없다 — 해석의 여지가 남는다")
    assert "삭제하지 마십시오" in clause


def test_금지_대상을_산출물_종류로_말한다():
    """★★★ 「적지 마십시오」만으로는 무엇을 만들지 말라는 건지 모호하다.

    ⚠️ 실측에서 요구사항에는 안 적혀도 **WBS 태스크**는 생겼다. 막을 대상을
      종류로 나열한다 — 요구사항·화면·API·데이터셋·태스크."""
    clause = render_clause()
    for kind in ("요구사항", "화면", "API", "데이터셋", "태스크"):
        assert kind in clause, kind
    assert "Must" in clause and "Should" in clause, (
        "우선순위 어디에도 넣지 말라는 말이 없다")


def test_허용되는_것을_함께_적는다():
    """★★★ 금지만 적으면 **만들어야 하는 것까지** 안 만든다.

    ⚠️ 실측: `E2E-06` 의 정당한 절반이 「호스트가 준 권한으로 버튼을 끄는 일」이었다.
      그것은 권한을 **만드는** 것이 아니라 **쓰는** 것이고, 반드시 구현해야 한다."""
    clause = render_clause()
    assert "만들어야 합니다" in clause
    assert "비활성화" in clause, "허용되는 예시가 없다"


def test_표지가_금지문이다():
    """⚠️ [2026-08-27 2차] 종전 표지 「아래는 이미 충족되어 있습니다」는 **무엇을 하지
    말라는 건지** 말하지 않았다 — 「이미 있으니 연동 화면을 만들자」로 읽힌다."""
    from core.requirement_normalizer import MARKER

    assert "만들지 않습니다" in MARKER, MARKER


def test_옛_표지가_붙은_요구문에는_다시_안_붙인다():
    """★ 표지를 바꿨으므로 옛 표지도 재진입 판정에서 봐야 한다 —
    아니면 같은 지시가 두 벌로 실린다."""
    from core.requirement_normalizer import _LEGACY_MARKERS

    old_text = _IDEA + chr(10) * 2 + _LEGACY_MARKERS[0] + chr(10) + "(옛 본문)"
    assert normalize_idea(old_text, enforced=True) == old_text


# ── 목록은 닫힌 목록에서 온다 ────────────────────────────────────────────

def test_금지_능력을_모두_고지한다():
    """★★★ 손으로 적은 목록은 바뀐 날 조용히 갈린다 — 이 저장소가 세 번 겪었다.

    ⚠️ 닫힌 목록의 `PROHIBITED` **전부**가 문구에 나타나는지 본다. 새 금지 항목이
      추가된 날 이 시험이 잡는다."""
    clause = render_clause()
    prohibited = [k for k, (s, _r) in arc.CAPABILITY_DECISION.items()
                  if s == arc.PROHIBITED]
    assert prohibited, "금지 능력이 하나도 없다 — 대조군이 성립하지 않는다"
    missing = [c for c in prohibited
               if c.split(".")[-1] not in clause and _ko_hint(c) not in clause]
    assert not missing, f"고지문에 안 실린 금지 능력: {missing}"


def _ko_hint(cap: str) -> str:
    from core.requirement_normalizer import _KO
    return _KO.get(cap, cap)


def test_인증_세_가지가_이미_충족으로_적힌다():
    """★ 사용자가 실제로 겪은 셋 — 로그인·권한·세션."""
    clause = render_clause()
    for word in ("로그인", "권한", "세션"):
        assert word in clause, word


# ── 두 번 붙지 않는다 ───────────────────────────────────────────────────

def test_재진입해도_한_번만_붙는다():
    """⚠️ `start_sprint` 는 **태스크마다** 불린다. 표지가 없으면 목표가 매번 길어지고,
    문맥 예산을 그만큼 먹는다."""
    once = normalize_idea(_IDEA, enforced=True)
    twice = normalize_idea(once, enforced=True)
    assert twice == once
    assert once.count(MARKER) == 1


def test_already_applied_가_표지를_본다():
    assert already_applied(normalize_idea(_IDEA, enforced=True))
    assert not already_applied(_IDEA)


# ── 경계 ────────────────────────────────────────────────────────────────

def test_레거시에는_붙이지_않는다():
    """★★★ 계약 프로필이 꺼진 프로젝트는 자유 형식 앱을 만들어 왔다 —
    소급하면 이미 도는 것들이 깨진다."""
    assert normalize_idea(_IDEA, enforced=False) == _IDEA


def test_빈_요구문은_그대로다():
    """⚠️ 빈 목표에 고지문만 붙으면 「고지문이 목표인 프로젝트」가 된다."""
    assert normalize_idea("", enforced=True) == ""
    assert normalize_idea(None, enforced=True) == ""


# ── 실제로 입구에 걸려 있는가 ───────────────────────────────────────────

def test_스프린트_시작이_이_정규화를_부른다():
    """⚠️⚠️ 만들어 두고 부르는 곳이 없으면 없는 것과 같다 —
    이 저장소가 이번 세션에만 네 번 겪은 모양이다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.start_sprint)
    assert "normalize_idea" in src, "요구 입구에서 정규화하지 않는다"


def test_계약_프로필과_같은_판정을_쓴다():
    """★ 레거시 경계를 두 곳에서 정하면 언젠가 갈린다."""
    import inspect

    import api.routes.factory_control as fc

    src = inspect.getsource(fc.start_sprint)
    i = src.index("normalize_idea")
    assert "runtime_contract_profile" in src[i:i + 400], (
        "정규화가 계약 프로필과 다른 기준으로 켜진다")
