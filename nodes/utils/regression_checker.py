# ==========================================
# 심볼 회귀 게이트 - 순수 파이썬(결정적, LLM 0콜)
# 모든 게이트(렌더/입력동작/스모크/LLM리뷰)는 '신규 파일 단독(stateless)'만 보므로,
# 직전 태스크에 있던 기능이 새 버전에서 사라져도 잡지 못한다(삭제는 오히려 통과).
# 이 게이트는 '직전 커밋(baseline) 대비 사라진 심볼/입력요소/라우트'를 비교해 회귀를 차단한다.
#
# 리네임 오탐 방지: 카테고리별 '개수가 순감소'한 경우에만 회귀로 본다.
#   (1:1 리네임은 -1 +1 = 순증감 0 → 통과 / 진짜 삭제는 -1 +0 = 순감소 → 차단)
# ==========================================
import re
from typing import List, Dict, Any, Callable, Optional

_FE_EXTS = (".tsx", ".ts", ".jsx", ".js")
_BE_EXTS = (".py",)

# 삭제가 '의도된' 재작업이면 게이트를 우회(리뷰/사용자 피드백에 삭제 지시가 있을 때)
_DELETION_HINTS = ("삭제", "제거", "없애", "지워", "빼", "remove", "delete", "deprecat", "drop ")


def _fe_exports(code: str) -> set:
    return set(re.findall(
        r'export\s+(?:default\s+)?(?:async\s+)?(?:function|const|class|let|var)\s+([A-Za-z_$][\w$]*)', code))


def _fe_handlers(code: str) -> set:
    # const handleX = / function handleX / const onX = 형태의 이벤트 핸들러 정의
    return set(re.findall(r'(?:const|let|function)\s+(handle[A-Z]\w*|on[A-Z]\w*)\b', code))


def _fe_formtags(code: str) -> int:
    return len(re.findall(r'<(?:input|textarea|select)\b', code))


def _be_defs(code: str) -> set:
    defs = set(re.findall(r'(?:^|\s)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(', code))
    classes = set(re.findall(r'(?:^|\s)class\s+([A-Za-z_]\w*)', code))
    return defs | classes


def _be_routes(code: str) -> set:
    routes = set()
    for m in re.finditer(r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', code, re.IGNORECASE):
        routes.add(f"{m.group(1).upper()} {m.group(2)}")
    return routes


def _ext_of(path: str) -> str:
    return ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""


def _regressions_for_file(prev: str, new: str, ext: str) -> List[str]:
    """카테고리별 '순감소' 시 사라진 항목 라벨 리스트를 반환(없으면 빈 리스트)."""
    lost: List[str] = []
    if ext in _FE_EXTS:
        pe, ne = _fe_exports(prev), _fe_exports(new)
        if len(ne) < len(pe):
            lost += [f"export {x}" for x in sorted(pe - ne)]
        ph, nh = _fe_handlers(prev), _fe_handlers(new)
        if len(nh) < len(ph):
            lost += [f"핸들러 {x}" for x in sorted(ph - nh)]
        pf, nf = _fe_formtags(prev), _fe_formtags(new)
        if nf < pf:
            lost.append(f"입력요소(input/textarea/select) {pf}→{nf}개 감소")
    elif ext in _BE_EXTS:
        pd, nd = _be_defs(prev), _be_defs(new)
        if len(nd) < len(pd):
            lost += [f"def/class {x}" for x in sorted(pd - nd)]
        pr, nr = _be_routes(prev), _be_routes(new)
        if len(nr) < len(pr):
            lost += [f"엔드포인트 {x}" for x in sorted(pr - nr)]
    return lost


def is_deletion_intended(feedback_blob: str) -> bool:
    blob = (feedback_blob or "").lower()
    return any(h in blob for h in _DELETION_HINTS)


def check_symbol_regression(
    new_files: List[Dict[str, Any]],
    read_baseline: Callable[[str], Optional[str]],
    allow_deletion: bool = False,
) -> Dict[str, Any]:
    """new_files: [{file_path, code}] (이번 태스크 산출물).
    read_baseline(rel_path) -> 직전 커밋의 해당 파일 내용(없으면 None=신규 파일, 비교 생략).
    allow_deletion=True 면(삭제 의도 명시) 게이트 우회.
    반환: {ok, regressions: [{file, lost:[...]}], errors:[...], skipped?}"""
    if allow_deletion:
        return {"ok": True, "regressions": [], "skipped": True, "reason": "삭제 의도 명시 - 회귀 게이트 우회"}
    if not new_files:
        return {"ok": True, "regressions": [], "skipped": True, "reason": "신규 파일 없음"}

    regressions: List[Dict[str, Any]] = []
    for f in new_files:
        path = f.get("file_path", "") or ""
        new_code = f.get("code", "") or ""
        ext = _ext_of(path)
        if ext not in _FE_EXTS + _BE_EXTS:
            continue
        prev = read_baseline(path)
        if not prev:
            continue  # baseline 없음(신규 파일) → 비교 생략
        lost = _regressions_for_file(prev, new_code, ext)
        if lost:
            regressions.append({"file": path, "lost": lost})

    errors = [f"[{r['file']}] 직전 버전 대비 사라진 기능/심볼: " + ", ".join(r["lost"][:6]) for r in regressions]
    return {"ok": len(regressions) == 0, "regressions": regressions, "errors": errors}
