# ==========================================
# 프론트엔드 코드 품질 정적 백스톱 — 순수 파이썬(Node 불필요)
# Phase 2 — 3단 품질 사다리의 Reviewer(단위 코드/기능) 보강.
#
# render/interactivity/smoke 검사기는 "객관적 파손"(렌더 실패·동결 입력·부팅 크래시)을
# 잡는 hard fast-fail 이다. 이 검사기는 그보다 약한 "소프트 품질 신호"
#   ① 거대 단일 파일(컴포넌트 분리 누락)  ② 리스트 렌더 시 빈 상태 처리 누락
#   ③ 디자인 토큰 위반(임의 hex / 인라인 color)
# 을 탐지한다. 이들은 오탐 시 재작업을 폭증시킬 수 있으므로(재작업이 최대 비용 핫스팟)
# 하드 차단이 아니라 **권고(advisory)** 로 반환 — 호출부(run_reviewer)가 LLM 리뷰어
# 프롬프트에 주입해 판단에 참고하게 한다. frontend_skill / design_system 가 1차로
# 품질을 끌어올리고, 이 검사기는 그 규율이 무너졌을 때를 잡는 **백스톱**이다.
# ==========================================
import re
from typing import List, Dict, Any

import config

# 컴포넌트 정의로 간주할 패턴 (PascalCase 함수/화살표/클래스). 소문자 헬퍼·hook(useX) 제외.
_COMPONENT_DEFS = [
    re.compile(r"\bfunction\s+([A-Z][A-Za-z0-9]*)\s*\("),            # function Foo(
    re.compile(r"\bconst\s+([A-Z][A-Za-z0-9]*)\s*=\s*(?:React\.)?(?:memo\()?\(?[^=\n]*?=>"),  # const Foo = (..) =>
    re.compile(r"\bclass\s+([A-Z][A-Za-z0-9]*)\s+extends\b"),         # class Foo extends
]

# 임의 색상값: 인라인 style 또는 Tailwind 임의값(bg-[#fff]) — 디자인 토큰 팔레트 이탈 신호.
_HEX_RE = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b")
# className 임의 색 유틸 (bg-[#..], text-[#..], border-[#..]) 또는 rgb()/rgba() 인라인
_ARBITRARY_COLOR_UTIL_RE = re.compile(r"\b(?:bg|text|border|ring|from|to|via)-\[#?[0-9a-fA-F]{3,8}\]")

# .map( ... => <JSX> ) — 리스트를 JSX 로 렌더하는 패턴(빈 상태 점검 대상)
_LIST_RENDER_RE = re.compile(r"\.map\s*\(\s*\(?[^)]*\)?\s*=>\s*[\s\S]{0,40}?<", re.MULTILINE)
# 빈 상태/길이 가드 흔적 (하나라도 있으면 빈 상태를 다뤘다고 간주 — 보수적, 오탐 최소)
_EMPTY_GUARD_RE = re.compile(
    r"\.length\s*(?:===?|!==?|>|<|\?|&&|\|\|)"   # items.length === 0 / length > 0 / length &&
    r"|\.length\s*\)"                              # ...length)
    r"|length\s*===\s*0"
    r"|!\s*[A-Za-z_$][\w$]*\.length"               # !items.length
    r"|empty|Empty|비어|없[습으]|0건|no\s+(?:items|results|data)"  # 빈 상태 안내 문구
)

_JSX_FILE_RE = re.compile(r"\.(tsx?|jsx?)$")


def _component_count(code: str) -> int:
    names = set()
    for pat in _COMPONENT_DEFS:
        for m in pat.finditer(code):
            names.add(m.group(1))
    return len(names)


def check_code_quality(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """프론트 파일 배열([{file_path, code}])의 소프트 품질 결함을 정적 탐지.
    {ok, warnings:[str], issues:[{file,kind,detail}], metrics} 반환.
    하드 차단용이 아님 — ok=False 여도 호출부는 '권고'로만 사용(재작업 강제 금지)."""
    if not files:
        return {"ok": True, "warnings": [], "issues": [], "skipped": True, "reason": "프론트 코드 없음"}

    issues: List[Dict[str, str]] = []
    metrics = {"files": 0, "max_lines": 0, "max_components": 0}

    max_lines = int(getattr(config, "FE_MONOLITH_MAX_LINES", 400))
    min_comps = int(getattr(config, "FE_MONOLITH_MIN_COMPONENTS", 3))

    for f in files:
        path = f.get("file_path", "") or ""
        code = f.get("code", "") or ""
        if not _JSX_FILE_RE.search(path):
            continue
        metrics["files"] += 1
        n_lines = code.count("\n") + 1
        n_comps = _component_count(code)
        metrics["max_lines"] = max(metrics["max_lines"], n_lines)
        metrics["max_components"] = max(metrics["max_components"], n_comps)

        # ① 거대 단일 파일 — 여러 컴포넌트가 한 파일에 몰려 분리되지 않음
        if n_lines >= max_lines and n_comps >= min_comps:
            issues.append({
                "file": path, "kind": "monolith",
                "detail": f"한 파일에 {n_comps}개 컴포넌트가 {n_lines}줄로 뭉쳐 있습니다 — "
                          f"컴포넌트를 파일별로 분리하십시오(거대 단일 파일 지양).",
            })

        # ② 리스트 렌더에 빈 상태 처리 누락
        if _LIST_RENDER_RE.search(code) and not _EMPTY_GUARD_RE.search(code):
            issues.append({
                "file": path, "kind": "empty_state",
                "detail": "리스트(.map)를 렌더하지만 항목이 0건일 때의 빈 상태 처리가 보이지 않습니다 — "
                          "길이 0 분기(빈 상태 안내문/플레이스홀더)를 추가하십시오.",
            })

        # ③ 디자인 토큰 위반 — 임의 hex / 인라인 color
        hex_hits = set()
        for m in _ARBITRARY_COLOR_UTIL_RE.finditer(code):
            hex_hits.add(m.group(0))
        # 인라인 style={{ ... }} 안의 hex
        for sm in re.finditer(r"style\s*=\s*\{\{[\s\S]*?\}\}", code):
            for hm in _HEX_RE.finditer(sm.group(0)):
                hex_hits.add(hm.group(0))
        if hex_hits:
            sample = ", ".join(list(hex_hits)[:5])
            issues.append({
                "file": path, "kind": "design_token",
                "detail": f"디자인 토큰 팔레트를 벗어난 임의 색상값({sample})이 사용되었습니다 — "
                          f"design_system 의 Tailwind 색 토큰(indigo/slate/rose/emerald 등)을 사용하십시오.",
            })

    warnings = [f"[{it['file']}] {it['detail']}" for it in issues]
    return {"ok": len(issues) == 0, "warnings": warnings, "issues": issues, "metrics": metrics}
