"""★★★ 렌더 실패 메시지가 **무엇을 고쳐야 하는지** 말한다. (2026-08-27 실측)

## ⚠️⚠️ 무엇이 있었나

새 프로젝트 `CRM003` 의 첫 태스크가 리뷰 왕복 8회를 태우고 죽었다. 오류는 이랬다:

    [src/index.tsx] 로드/컴파일 실패: /src/styles/index.css:
    Support for the experimental syntax 'decorators' isn't currently enabled (1:1):
    > 1 | @tailwind base;

에이전트는 **webpack + tailwind CLI** 방식으로 골격을 짰다(`webpack.config.js` ·
`tailwind.config.js` · `src/index.tsx` · `src/styles/index.css`). 그런데 미리보기
런타임에는 **번들러가 없다** — 브라우저 안 Babel 이 TSX 를 바로 컴파일하고 Tailwind 는
이미 로드돼 있다. 그래서 Babel 이 CSS 를 JS 로 파싱하다 죽는다.

★ 규칙은 **이미 `skills/frontend_skill.md:23` 에 있었다** — 「CSS 파일 생성 금지 ·
  Tailwind 유틸 클래스만(샌드박스에 CDN 로드됨)」. 문제는 오류 메시지가 「decorators
  문법」이라 **그 규칙과 이어지지 않는 것**이다. 에이전트는 자기가 어떤 규칙을 어겼는지
  알 수 없었고, 8번 다른 곳을 고쳤다.

⇒ **거절이 행동으로 이어지지 않으면 그것은 통제가 아니라 교착이다.**
  이 저장소가 오늘만 세 번 같은 결론에 도달했다(계약 오류 되돌림 · 능력 이름 · 이것).

## 선례

바로 위에 「미해결 import 해결법」이 같은 이유로 이미 있다(2026-07-26) —
「일반 문구뿐이어서 가장 흔한 실패에 맞는 해결책을 알려주지 못했다」. 같은 방식이다.
"""
import inspect
import re

import pytest

#: `CRM003` 이 **실제로** 낸 오류 문자열. 바꾸지 않는다.
_REAL_CSS_ERROR = (
    "[src/index.tsx] 로드/컴파일 실패: /src/styles/index.css: Support for the "
    "experimental syntax 'decorators' isn't currently enabled (1:1): "
    "> 1 | @tailwind base;")
_REAL_IMPORT_ERROR = (
    '[src/App.tsx] 로드/컴파일 실패: 미해결 상대 모듈 import: "./generated/afs-contract"')
_RUNTIME_ERROR = (
    "[src/App.tsx] 런타임 오류: Cannot read properties of undefined (reading map)")


def _branches(errs):
    """제품과 **같은 판정식**을 쓴다 — 여기서 다시 쓰면 시험과 제품이 갈린다."""
    joined = " ".join(errs)
    missing = re.findall(r'미해결 상대 모듈 import:\s*"([^"]+)"', joined)
    css = re.search(r"(@tailwind|\.css|\.scss|\.less)", joined, re.I)
    return {"css": bool(css and not missing), "import": bool(missing)}


# ── 갈래가 정확히 갈리는가 ───────────────────────────────────────────────

def test_실제_CSS_실패를_CSS_갈래로_보낸다():
    """★★★ **이 파일의 요지.** 제품이 실제로 낸 오류를 잡아야 한다."""
    b = _branches([_REAL_CSS_ERROR])
    assert b["css"] and not b["import"], b


def test_import_실패는_import_갈래로_간다():
    """⚠️ import 실패에도 `.css` 가 섞여 있을 수 있다 — 그때는 import 쪽이 우선이다.
    두 조언을 함께 주면 무엇부터 고칠지 모른다."""
    b = _branches([_REAL_IMPORT_ERROR])
    assert b["import"] and not b["css"], b


def test_두_오류가_함께면_import_가_우선이다():
    b = _branches([_REAL_IMPORT_ERROR, _REAL_CSS_ERROR])
    assert b["import"] and not b["css"], b


def test_관계없는_런타임_오류에는_안_붙는다():
    """★★★ 대조군. 아무 실패에나 스타일 조언을 붙이면 조언이 잡음이 되고,
    잡음이 되면 사람도 모델도 안 읽는다."""
    b = _branches([_RUNTIME_ERROR])
    assert not b["css"] and not b["import"], b


# ── 조언이 실제로 **행동 가능한가** ─────────────────────────────────────

def test_조언이_무엇을_하지_말라고_말한다():
    """⚠️ 「스타일을 고치십시오」로는 못 고친다. **파일을 만들지 말라**고 해야 한다."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    i = src.index("스타일 해결법")
    hint = src[i:i + 1200]
    assert "만들지 마십시오" in hint
    assert "지우십시오" in hint, "이미 만든 파일을 어떻게 하라는 말이 없다"


def test_조언이_대안을_함께_준다():
    """★★★ 금지만 말하면 스타일을 아예 안 넣는다. **무엇으로 대신하라**를 함께 준다."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    i = src.index("스타일 해결법")
    hint = src[i:i + 1200]
    assert "이미 로드돼 있습니다" in hint, "Tailwind 가 이미 있다는 사실이 없다"
    assert "className" in hint, "쓰는 방법 예시가 없다"
    assert "인라인" in hint, "추가 스타일 대안이 없다"


def test_빌드_설정_파일도_함께_막는다():
    """⚠️ CSS 만 막으면 `webpack.config.js` 는 계속 나온다 — 실측에서 함께 나왔다."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    i = src.index("스타일 해결법")
    hint = src[i:i + 1200]
    assert "webpack.config.js" in hint and "tailwind.config.js" in hint


def test_런타임에_번들러가_없다는_사실을_말한다():
    """★ 「왜」가 없으면 다음 회차에 같은 구조를 다시 만든다."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    i = src.index("스타일 해결법")
    assert "번들러가 없습니다" in src[i:i + 400]
