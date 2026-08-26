"""★★★ 생성 앱이 **지어낸 데이터를 사실처럼 보여 주는가**. (2026-08-26)

## ⚠️⚠️ 무엇이 있었나 — 실측

실제 가동(`live-walk-03`)이 만든 앱이 이랬다:

```ts
} catch (err) {
  setError("데이터를 불러오는 데 실패했습니다. 목업 데이터를 표시합니다.");
  setInboundData(sortData(mockData));      // ← 지어낸 입고 내역을 표로 그린다
}
```

**사용자는 그 표를 보고 발주를 판단한다.** 「목업입니다」는 표 위쪽 한 줄이고, 행 자체는
진짜와 똑같이 생겼다. 못 읽은 것을 그럴듯하게 채우는 것은 **오답보다 나쁘다** — 틀렸다는
사실조차 알 수 없기 때문이다.

원인은 모델이 아니라 `skills/frontend_skill.md` 였다. 거기에 「mock 우선 … 실패 시 아무
것도 하지 말고 mock 유지」라고 **적혀 있었다.** 지시문은 고쳤고, 이 검사기는 그 규율이
무너졌을 때 잡는 백스톱이다.

## 무엇을 잡고 무엇을 놓아주는가

⚠️⚠️ 검사기의 어려운 부분은 「무엇을 잡을까」가 아니라 **「무엇을 놓아줄까」**다. 오탐이
  늘면 검사기는 꺼지고, 꺼진 검사기는 없는 것과 같다(`platform_auth_checker` 머리말과
  같은 판단이다).

★ 그래서 **이름으로 잡지 않는다.** `mockData` 라는 이름 자체는 죄가 아니다 — 개발 중에
  참고용으로 둘 수도 있다. 죄는 **행위**다:

    ① 실패 분기(`catch` · 호스트 미존재 `else`)에서 **표시 상태에 값을 넣는 것**
    ② 업무 데이터 상태의 `useState` **초기값에 지어낸 행을 넣는 것**

  둘 다 「못 읽었는데 뭔가를 그린다」는 한 가지 사실의 두 모양이다.

★ 놓아주는 것:
    · `set*(null)` · `set*([])` · `set*('')` · `set*(false)` — 비우는 것은 fail-closed 다.
    · `setError(...)` · `setLoading(...)` 처럼 **표시 데이터가 아닌** 상태.
    · 빈 배열/객체 리터럴 초기값 — 그것이 바로 우리가 시킨 모양이다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

#: 표시 데이터가 **아닌** 상태. 실패 분기에서 이것들을 세우는 것은 정상이다.
#: ⚠️ 이름 기반 예외이므로 **좁게** 둔다 — 넓히면 검사기가 아무것도 안 잡는다.
_NON_DATA_SETTER = re.compile(
    r"^set(Error|Err|Loading|Busy|Pending|Message|Msg|Status|Failed|Warning|Notice)",
    re.IGNORECASE)

#: 비우는 값. 이것을 넣는 것은 **fail-closed** 이므로 통과시킨다.
_EMPTY_VALUE = re.compile(r"""^\s*(
      null | undefined | \[\s*\] | \{\s*\} | ''|""|`` | false | 0
)\s*$""", re.VERBOSE)

#: `catch (...) { ... }` 와 `window.afs` 가 없을 때의 `else { ... }`.
#: ★ 중괄호 균형을 세어 블록을 잡는다 — 정규식으로 중첩을 잡으려 하면 조용히 틀린다.
_CATCH_HEAD = re.compile(r"\bcatch\s*(\([^)]*\))?\s*\{")
_ELSE_HEAD = re.compile(r"\}\s*else\s*\{")
_SETTER_CALL = re.compile(r"\b(set[A-Z]\w*)\s*\(([^;]*?)\)\s*;", re.DOTALL)
_USESTATE = re.compile(r"useState\s*(?:<[^>]*>)?\s*\(([^;]*?)\)\s*[;,)]", re.DOTALL)

#: 배열 리터럴 안에 **객체가 둘 이상** — 지어낸 «행» 의 모양이다.
#: ⚠️ 하나짜리는 놓아준다(설정 기본값일 수 있다). 둘부터가 «목록» 이다.
_ROWS_LITERAL = re.compile(r"\[\s*\{.*?\}\s*,\s*\{", re.DOTALL)


def _block_at(text: str, open_brace: int) -> str:
    """`{` 위치에서 시작해 짝이 맞는 `}` 까지. 못 닫히면 끝까지."""
    depth, i, n = 0, open_brace, len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1:i]
        i += 1
    return text[open_brace + 1:]


def _failure_blocks(text: str) -> List[str]:
    """실패 분기의 본문들. `catch` 전부 + 호스트 가용성 검사의 `else`."""
    out = []
    for m in _CATCH_HEAD.finditer(text):
        out.append(_block_at(text, m.end() - 1))
    #: ★ 모든 `else` 를 보지 않는다 — 앞 조건이 **호스트 가용성**을 물을 때만 본다.
    #:   그래야 평범한 분기 로직이 오탐으로 잡히지 않는다.
    for m in _ELSE_HEAD.finditer(text):
        head = text[max(0, m.start() - 400):m.start()]
        if re.search(r"window\s*\.\s*afs|afs\s*\.\s*data|\bafs\b", head):
            out.append(_block_at(text, m.end() - 1))
    return out


def scan_text(text: str, path: str = "") -> List[Dict[str, Any]]:
    """한 파일에서 발견한 것들. 심각도는 전부 `block` 이다 — 이것은 취향이 아니다."""
    found: List[Dict[str, Any]] = []

    # ① 실패 분기에서 표시 상태를 채운다
    for body in _failure_blocks(text):
        for setter, value in _SETTER_CALL.findall(body):
            if _NON_DATA_SETTER.match(setter):
                continue                      # 오류·로딩 표시는 정상이다
            if _EMPTY_VALUE.match(value):
                continue                      # 비우는 것은 fail-closed 다
            found.append({
                "id": "data_on_failure", "path": path, "severity": "block",
                "detail": (f"읽기 실패 분기에서 `{setter}(...)` 로 표시 데이터를 채웁니다 — "
                           f"못 읽었으면 그리지 않아야 합니다. 비우거나(`[]`·`null`) "
                           f"실패 상태만 세우십시오."),
                "evidence": f"{setter}({value.strip()[:60]})",
            })

    # ② 업무 데이터 상태의 초기값에 지어낸 행을 넣는다
    for init in _USESTATE.findall(text):
        if _ROWS_LITERAL.search(init):
            found.append({
                "id": "fabricated_state_seed", "path": path, "severity": "block",
                "detail": ("`useState` 초기값에 지어낸 행이 들어 있습니다 — 화면이 뜨는 "
                           "순간 사용자는 그것을 실제 데이터로 봅니다. `[]` 로 시작하고 "
                           "실제로 읽은 것만 채우십시오."),
                "evidence": init.strip()[:60],
            })
    return found


def check_synthetic_data(files: Any) -> Dict[str, Any]:
    """`[{file_path, code}]` 를 훑는다. `{ok, blocking, summary}`.

    ⚠️ 파일 목록이 비면 **검사할 것이 없다**(`skipped`) — 그것을 `ok` 로 뭉개면
      「검사가 안 돌았다」와 「깨끗하다」가 같아진다."""
    rows = files if isinstance(files, list) else []
    if not rows:
        return {"ok": True, "blocking": [], "skipped": True, "reason": "검사할 프론트 코드 없음"}

    blocking: List[Dict[str, Any]] = []
    for f in rows:
        if not isinstance(f, dict):
            continue
        path = str(f.get("file_path") or f.get("path") or "")
        if not path.lower().endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        code = f.get("code") if f.get("code") is not None else f.get("content")
        if not isinstance(code, str):
            continue
        blocking.extend(scan_text(code, path))

    return {"ok": not blocking, "blocking": blocking,
            "summary": {"blocking": len(blocking), "files": len(rows)}}


def render_report(result: Dict[str, Any]) -> str:
    """사람이 읽고 **고칠 수 있는** 한 덩어리. 개수만 말하지 않는다."""
    items = result.get("blocking") or []
    if not items:
        return ""
    lines = ["지어낸 데이터를 실제처럼 보여 주는 코드가 있습니다:"]
    for it in items[:8]:
        lines.append(f"- [{it['path']}] {it['detail']}  (근거: {it['evidence']})")
    return "\n".join(lines)
