# ==========================================
# 프론트엔드 입력 동작(인터랙티비티) 정적 검증기 - 순수 파이썬(Node 불필요)
# renderToString 검증은 "렌더되는가"만 확인할 수 있고 "입력이 동작하는가"는 못 잡는다.
# 대표 결함: 제어 컴포넌트(value={...})에 onChange 가 없으면 React 는 그 입력을
#   '읽기전용'으로 렌더한다 → 사용자가 타이핑해도 값이 안 들어가는 '동결된 입력'.
# JSX 속성식의 `=>`(화살표)나 문자열 속 `>` 에서 잘못 끊기지 않도록 중괄호/따옴표
#   깊이를 추적해 시작 태그를 정확히 잘라낸다. 네이티브 소문자 태그만 대상(컴포넌트 제외).
# ==========================================
import re
from typing import List, Dict, Any, Iterator, Tuple, Optional

# 사용자 입력을 받는 네이티브 폼 요소(소문자) - 대문자 컴포넌트(<Input/>)는 자체 처리 가정, 제외
_FORM_TAGS = ("input", "textarea", "select")

# value 가 라벨/정적 의미라 onChange 가 필요 없는 input type
_NON_TEXT_INPUT_TYPES = ("submit", "button", "reset", "hidden", "image", "file")


def _iter_tags(code: str, tag: str) -> Iterator[Tuple[int, str]]:
    """code 안의 `<tag ...>` 시작 태그를 중괄호/따옴표 인지 방식으로 잘라 (start, tag_text) 산출.
    JSX 표현식 `onChange={(e)=>...}` 의 `>` 나 `placeholder="a > b"` 의 `>` 에서 오절단 방지."""
    # 네이티브 태그는 소문자 - 대소문자 구분(<Input> 같은 컴포넌트는 매칭하지 않음)
    pattern = re.compile(r"<" + tag + r"(?=[\s/>])")
    for m in pattern.finditer(code):
        i = m.end()
        depth = 0
        quote = ""
        n = len(code)
        while i < n:
            c = code[i]
            if quote:
                if c == quote:
                    quote = ""
            elif c in ("'", '"', "`"):
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth = max(0, depth - 1)
            elif c == ">" and depth == 0:
                yield m.start(), code[m.start():i + 1]
                break
            i += 1


def _analyze_tag(tag_text: str, tag: str) -> Optional[str]:
    """동결(읽기전용) 입력이면 사람이 읽을 요약 문자열을 반환, 정상이면 None."""
    # readOnly / disabled 면 의도된 비입력 → 정상
    if re.search(r"\breadOnly\b", tag_text) or re.search(r"\bdisabled\b", tag_text):
        return None
    # input type 이 submit/button/hidden 등이면 value 는 라벨/메타 → 정상
    if tag == "input":
        tm = re.search(r"""\btype\s*=\s*['"]([a-zA-Z]+)['"]""", tag_text)
        if tm and tm.group(1).lower() in _NON_TEXT_INPUT_TYPES:
            return None
    # 제어 속성(value / checked) 존재? (\bvalue 는 defaultValue 와 매칭되지 않음)
    has_value = bool(re.search(r"\bvalue\s*=", tag_text)) or bool(re.search(r"\bchecked\s*=", tag_text))
    if not has_value:
        return None  # 비제어(defaultValue 등) 또는 value 없음 → 자유 입력
    # 변경 핸들러(onChange/onInput) 존재? → 정상 제어 컴포넌트
    if re.search(r"\bon(Change|Input)\s*=", tag_text):
        return None
    # value={...} 인데 onChange 없음 → React 가 읽기전용으로 만든다 = 동결 입력
    snippet = re.sub(r"\s+", " ", tag_text).strip()
    if len(snippet) > 120:
        snippet = snippet[:117] + "..."
    return snippet


def check_frontend_interactivity(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """프론트 파일 배열([{file_path, code}])의 '동결된 입력'을 정적 탐지.
    {ok, frozen: [...], errors: [...], skipped?} 반환. 결함이 없으면 ok=True."""
    if not files:
        return {"ok": True, "frozen": [], "skipped": True, "reason": "프론트 코드 없음"}

    frozen: List[Dict[str, str]] = []
    for f in files:
        path = f.get("file_path", "") or ""
        code = f.get("code", "") or ""
        if not re.search(r"\.(tsx?|jsx?)$", path):
            continue
        for tag in _FORM_TAGS:
            for _start, tag_text in _iter_tags(code, tag):
                desc = _analyze_tag(tag_text, tag)
                if desc:
                    frozen.append({"file": path, "tag": tag, "snippet": desc})

    errors = [
        f"[{fr['file']}] <{fr['tag']}> 가 value 로 제어되지만 onChange 가 없어 "
        f"사용자가 입력할 수 없습니다(읽기전용 동결): {fr['snippet']}"
        for fr in frozen[:8]
    ]
    return {"ok": len(frozen) == 0, "frozen": frozen, "errors": errors}
