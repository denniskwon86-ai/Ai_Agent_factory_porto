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


def test_세_가지_전제가_적힌다():
    """★★★ [2026-08-27 4차] **오늘 실제로 틀어진 셋만** 적는다.

    ⚠️⚠️ 3차까지는 35줄이었다. Supervisor 가 「무슨 말인지 솔직히 나는 잘 이해가
      안되는데」라고 했다 — **사람이 못 읽으면 모델이 읽는다고 볼 근거도 없다.**
    ★ 그리고 실측이 짧은 쪽을 받친다: 로그인은 실제로 막혔고, 그때 걸린 문장은
      「로그인/로그아웃 화면·API·세션을 요구사항에 적지 마십시오」 **한 줄**이었다.
      권한 관리는 문장이 길고 묻혀 있어서 안 걸렸다."""
    clause = render_clause()
    assert "로그인 기능은 필요 없습니다" in clause
    assert "권한을 만들거나 관리하는 기능도 필요 없습니다" in clause
    assert "서버·데이터베이스도 필요 없습니다" in clause
    assert "요구사항·화면·태스크 어디에도 넣지 마십시오" in clause


def test_짧게_유지된다():
    """★★★ **길이 자체가 설계 속성이다.**

    ⚠️ 실패할 때마다 문장을 붙이는 것이 반사였고, 세 번 만에 35줄이 됐다. 이 시험은
      그 반사를 막는다 — 다시 늘리려면 이 시험을 먼저 지워야 하고, 그때 왜 늘리는지
      적게 된다.
    ⚠️ 「대신 이렇게 적으십시오」(복사할 문장)를 뺀 근거: 그것은 «완성도 검사와 싸우지
      않으려면 출구가 필요하다» 는 **추론**이었는데, 실제로는 시키지 않아도 모델이
      「별도의 로그인/회원가입 기능은 구현하지 않는다」라고 알아서 적었다.
      **관측하지 않은 문제를 미리 막지 않는다.**"""
    body = [l for l in render_clause().splitlines() if l.strip()]
    assert len(body) <= 6, f"고지문이 {len(body)}줄로 늘었다 — 왜 늘리는지 먼저 적을 것"


def test_오늘_틀어진_셋을_모두_덮는다():
    """★ 실측 대응: `CRM002` 에서 실제로 새어 나간 셋.

    ⚠️ 나머지 금지 능력(`api.direct_call`·`storage.credentials`)은 이 문구가 아니라
      **게이트**가 막는다 — 계약 컴파일러와 `server_build_checker` 다. 기획 문구는
      기획에서 새는 것만 다룬다(문구를 늘리면 그만큼 묽어진다)."""
    clause = render_clause()
    for word in ("로그인", "권한", "서버", "데이터베이스"):
        assert word in clause, word


def test_문구에_특정_도메인_낱말이_없다():
    """⚠️ 이 문구는 **모든 프로젝트**에 붙는다. 한 도메인의 낱말을 박으면 다른
    프로젝트에서 엉뚱한 예시가 되고, 모델이 그 도메인을 끌어온다."""
    clause = render_clause()
    for word in ("거래처", "고객사", "재고", "발주"):
        assert word not in clause, f"도메인 낱말이 박혀 있다: {word}"


def test_만들라는_말이_없다():
    """★★★ Supervisor 3차 지적: 「권한 관리 기능을 **넣으라는 의미로 읽혀**」.

    ⚠️ 금지 고지문 안에 「만들어야」·「구현하십시오」가 한 번이라도 나오면 모델은
      그 절을 «만들 목록» 으로 읽는다. 이 문구는 **금지만** 말한다."""
    clause = render_clause()
    for word in ("만들어야", "구현하십시오", "반드시 구현"):
        assert word not in clause, f"만들라는 말이 남아 있다: {word}"


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
