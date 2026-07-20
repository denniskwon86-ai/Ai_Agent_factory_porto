"""[FinOps 2단계] 변경분 정적 위험도 분석기 — LLM 0콜.

산출물 파일 집합을 정적 신호(경로/확장자/내용 패턴 + git baseline 대비 변경 여부)로
LOW / MEDIUM / HIGH 로 분류한다. 소비처(run_reviewer):
  - LOW  → 리뷰어 LLM 호출 생략(자동 승인) — 쿼터 절감 + 인간/LLM 대기 시간 감소
  - HIGH → 리뷰어 프롬프트에 정밀 검토 지시 주입(스키마/API/의존성/인증 변경)
  - MEDIUM → 현행 동작 유지(일반 LLM 리뷰)

설계 원칙(보수적):
  - 모르면 MEDIUM — 오분류가 나도 '평소와 동일한 리뷰'로 수렴해 안전.
  - HIGH 는 명시적 패턴만. HIGH 오탐은 리뷰가 조금 엄격해질 뿐 차단이 아니므로 무해.
  - LOW 는 확장자 화이트리스트만(내용 휴리스틱 금지) — 자동 승인의 오탐이 가장 위험하므로.
  - baseline(git 직전 커밋) 과 내용이 동일한 파일은 '변경 없음'으로 집계에서 제외.
"""
import os
import re
from typing import Any, Callable, Dict, List, Optional

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}

# 자동 승인(LOW) 대상 — 로직에 영향 없는 정적 자산/문서만 (화이트리스트)
_LOW_EXTS = {".css", ".scss", ".less", ".md", ".txt", ".svg", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

# 의존성 매니페스트 — 패키지 추가/변경은 공급망·빌드 전체에 파급 (HIGH)
_MANIFEST_NAMES = {"package.json", "package-lock.json", "requirements.txt", "requirements-dev.txt",
                   "pyproject.toml", "pipfile", "poetry.lock", "yarn.lock"}

# 경로 힌트 — DB 스키마/마이그레이션, 인증·보안 관련 파일 (HIGH)
_SCHEMA_PATH_HINTS = ("models.py", "schema", "migration")
_AUTH_PATH_HINTS = ("auth", "login", "security", "permission")

# 내용 패턴 — baseline 대비 '개수가 달라졌을 때만' HIGH (기존부터 있던 라우트가
# 그대로면 매 태스크 HIGH 로 오탐되지 않도록 변경량 기준으로 판정)
_HIGH_CONTENT_PATTERNS = [
    (re.compile(r"@(?:app|router)\.(?:get|post|put|delete|patch)\s*\(", re.IGNORECASE), "API 엔드포인트 정의 변경"),
    (re.compile(r"\b(?:CREATE|ALTER|DROP)\s+TABLE\b", re.IGNORECASE), "DB 스키마(DDL) 변경"),
    (re.compile(r"\bsubprocess\b|\bos\.system\b|\beval\s*\(|\bexec\s*\(", re.IGNORECASE), "시스템 실행/동적 평가 코드 변경"),
]


def classify_file(path: str, code: str, old_code: Optional[str] = None) -> Dict[str, str]:
    """단일 파일의 위험도 분류. 반환: {"path", "level", "reason"}.
    old_code 가 주어지고 내용이 동일하면 level='UNCHANGED'(집계 제외 대상)."""
    if old_code is not None and old_code == code:
        return {"path": path, "level": "UNCHANGED", "reason": "baseline 과 동일(변경 없음)"}

    p = (path or "").replace("\\", "/").lower()
    name = os.path.basename(p)
    ext = os.path.splitext(name)[1]

    if name in _MANIFEST_NAMES:
        return {"path": path, "level": HIGH, "reason": "의존성 매니페스트 변경(패키지 추가/갱신)"}
    if any(h in p for h in _SCHEMA_PATH_HINTS):
        return {"path": path, "level": HIGH, "reason": "DB 스키마/마이그레이션 관련 파일 변경"}
    if any(h in p for h in _AUTH_PATH_HINTS):
        return {"path": path, "level": HIGH, "reason": "인증/보안 관련 파일 변경"}

    # 내용 신호: baseline 대비 패턴 등장 '횟수가 달라진' 경우만 변경으로 취급
    for pat, why in _HIGH_CONTENT_PATTERNS:
        new_n = len(pat.findall(code or ""))
        old_n = len(pat.findall(old_code or "")) if old_code is not None else 0
        if new_n != old_n:
            return {"path": path, "level": HIGH, "reason": f"{why} ({old_n}→{new_n})"}

    if ext in _LOW_EXTS:
        return {"path": path, "level": LOW, "reason": "정적 자산/문서(스타일·텍스트) 변경"}

    return {"path": path, "level": MEDIUM, "reason": "일반 코드 변경(기본 리뷰 대상)"}


def assess_changes(files: List[Dict[str, Any]], read_old: Optional[Callable[[str], Optional[str]]] = None) -> Dict[str, Any]:
    """파일 집합({file_path, code} 목록 — CodeOutput 규격)의 종합 위험도 산출.
    read_old(rel_path) 는 baseline(직전 커밋)의 파일 내용을 돌려주는 콜백(없으면 None 허용).
    반환: {"level", "summary", "per_file": [...], "high_reasons": [...], "changed": n}"""
    per_file: List[Dict[str, str]] = []
    overall = LOW
    high_reasons: List[str] = []
    changed = 0

    for f in files or []:
        path = f.get("file_path", "") or ""
        code = f.get("code", "") or ""
        old = None
        if read_old is not None:
            try:
                old = read_old(path)
            except Exception:
                old = None
        c = classify_file(path, code, old_code=old)
        per_file.append(c)
        if c["level"] == "UNCHANGED":
            continue
        changed += 1
        if _ORDER.get(c["level"], 1) > _ORDER[overall]:
            overall = c["level"]
        if c["level"] == HIGH:
            high_reasons.append(f"{c['path']}: {c['reason']}")

    if changed == 0:
        return {"level": LOW, "summary": "변경 파일 없음(전부 baseline 동일)",
                "per_file": per_file, "high_reasons": [], "changed": 0}

    summary = {LOW: "스타일/문서 수준 저위험 변경", MEDIUM: "일반 코드 변경",
               HIGH: "스키마/API/의존성/인증 고위험 변경"}[overall]
    return {"level": overall, "summary": summary, "per_file": per_file,
            "high_reasons": high_reasons, "changed": changed}


def format_risk_report(assessment: Dict[str, Any]) -> str:
    """리뷰 리포트/프롬프트 주입용 요약(마크다운). LLM 판단이 아닌 정적 집계임을 명시."""
    if not assessment:
        return ""
    lines = [f"### 🧮 정적 리스크 분석 (LLM 0콜 집계) — 종합: {assessment['level']} ({assessment['summary']}, 변경 {assessment.get('changed', 0)}개 파일)"]
    for c in assessment.get("per_file", []):
        if c["level"] == "UNCHANGED":
            continue
        mark = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(c["level"], "⚪")
        lines.append(f"- {mark} `{c['path']}` — {c['reason']}")
    return "\n".join(lines)
