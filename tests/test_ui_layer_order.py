"""★★★ 화면 **층 순서**(z-index) — 셸이 대화상자를 덮으면 나갈 길이 사라진다. (2026-08-25)

## ⚠️⚠️ 무엇이 있었나 (사용자 실측)

> 다른 모든 페이지에 최상단 고정 메뉴 영역 밑에 표시되는 각 페이지의 상단 영역이
> 겹쳐서 짤려요. 닫기 버튼이 5분의1정도만 살짝 보여서 뭔지 알수없어요.

승인 시안의 상단 셸을 옮겨 오면서 `z-index: 10000` 을 함께 가져왔다. 그때 대화상자
배경은 `z-index: 60` 이었다 — 즉 **셸이 모든 대화상자의 위쪽을 덮었다.**

★ 이것은 미관 문제가 아니다. 대화상자의 머리 바에는 **제목과 「닫기」**가 있고, 그것이
  가려지면 사용자는 **그 화면에서 나갈 방법을 잃는다.**

## 왜 시험으로 두는가

숫자가 두 파일에 흩어져 있어 한쪽만 고치면 조용히 어긋난다. 눈으로는 «조금 겹쳤네» 로
보이고, 그때는 이미 사용자가 갇힌 뒤다. **순서 자체를 못박는다.**
"""
import os
import re

import pytest


def _css(*parts) -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "frontend", "src", "design", *parts),
              encoding="utf-8") as f:
        return f.read()


def _z(text: str, selector: str) -> int:
    """`selector` 규칙 블록의 `z-index` 를 읽는다. **없으면 실패한다** — 「못 찾았다」를
    «0» 으로 바꾸면 순서 비교가 조용히 참이 된다."""
    #: 규칙 블록을 통째로 잡는다(주석 안의 숫자에 속지 않도록 블록 안에서만 찾는다).
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\}", text, re.DOTALL)
    assert m, f"«{selector}» 규칙을 찾지 못했습니다 — 선택자가 바뀌었으면 이 시험도 함께 고치십시오."
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.DOTALL)
    zm = re.search(r"z-index:\s*(\d+)", body)
    assert zm, f"«{selector}» 에 z-index 가 없습니다."
    return int(zm.group(1))


SHELL = ".afs-product-shell"
BACKDROP = ".afs-dialog-backdrop"


def test_대화상자가_상단_셸보다_위에_있다():
    """★★★ **이 파일의 요지.** 이 순서가 뒤집히면 사용자가 화면에서 나갈 수 없다."""
    shell = _z(_css("product-shell.css"), SHELL)
    backdrop = _z(_css("afs.css"), BACKDROP)
    assert backdrop > shell, (
        f"상단 셸({shell})이 대화상자({backdrop}) 위에 있습니다 — 제목과 「닫기」가 "
        f"가려져 사용자가 그 화면에서 나갈 수 없습니다.")


def test_대화상자_규칙이_셸_층을_가리킨다():
    """⚠️ 숫자가 **두 파일에 흩어져** 있다(`afs.css` · `product-shell.css`). 한쪽만
    고치면 조용히 어긋나므로, 대화상자 쪽이 셸의 값을 적어 두어 다음 사람이 함께 고친다.

    ⚠️ 셸 쪽 주석은 여기서 요구하지 않는다 — 그 파일은 다른 작업과 함께 움직이는 중이라,
      이 시험이 남의 진행 중 편집에 걸려 빨개지면 안 된다. 순서 자체는 위 시험이 지킨다."""
    assert "10000" in _css("afs.css"), "대화상자가 셸 층(10000)을 언급하지 않는다"


def test_셸이_고정_배치라_층이_실제로_적용된다():
    """⚠️ `z-index` 는 `position: static` 에서는 **아무 일도 하지 않는다.**
    순서를 시험하면서 그 전제를 확인하지 않으면, 값만 맞고 실제로는 안 먹는 상태를
    초록으로 넘긴다."""
    shell_css = _css("product-shell.css")
    m = re.search(re.escape(SHELL) + r"\s*\{(.*?)\}", shell_css, re.DOTALL)
    assert m
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.DOTALL)
    assert re.search(r"position:\s*(sticky|fixed|absolute|relative)", body), \
        "셸에 배치가 없어 z-index 가 적용되지 않습니다."


@pytest.mark.parametrize("selector,css_file", [
    (BACKDROP, "afs.css"),
])
def test_대화상자_배경이_화면_전체를_덮는다(selector, css_file):
    """★ 층만 위에 있고 영역이 좁으면 셸이 옆으로 비쳐 보인다 — 「반쯤 걸친 배경」은
    의도가 아니라 사고로 읽힌다(이 저장소가 2026-08-04 에 이미 지적받았다)."""
    text = _css(css_file)
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\}", text, re.DOTALL)
    assert m
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.DOTALL)
    assert "position: fixed" in body
    assert "inset: 0" in body, "배경이 화면 전체를 덮지 않습니다."
