"""프론트엔드에 남은 과거·현행 용어의 정확한 등장 위치를 변경 후보로 기록한다.

자동 치환은 의미 경계를 깨뜨릴 수 있으므로 수행하지 않는다. 이 보고서는 사용자 노출 여부를
사람이 확인할 수 있는 줄 단위 후보 목록이며, API·DB·코드 식별자 변경 허가가 아니다.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "data" / "terminology" / "technology_terminology_glossary.json"
FRONTEND = ROOT / "frontend" / "src"
OUTPUT = ROOT / "docs" / "architecture" / "TECHNOLOGY_TERMINOLOGY_UI_MIGRATION_BACKLOG_2026-08-12.md"
SCAN_SUFFIXES = {".ts", ".tsx", ".html"}
SKIP_PATHS = {
    FRONTEND / "data" / "technologyTerminologyGlossary.json",
    FRONTEND / "components" / "TerminologyGlossaryPanel.tsx",
}


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def exposure_kind(line: str, needle: str) -> str:
    stripped = line.strip()
    if stripped.startswith(("//", "/*", "*", "{/*")):
        return "주석"
    escaped = re.escape(needle)
    if re.search(rf">[^<]*{escaped}[^<]*<", line):
        return "사용자 노출 유력"
    ui_prop = r"(?:label|title|description|caption|placeholder|tooltip|message|emptyText|aria-label|ariaLabel|kicker|name)"
    if re.search(rf"\b{ui_prop}\b\s*[:=]\s*['\"`]([^'\"`]*{escaped}[^'\"`]*)['\"`]", line):
        return "사용자 노출 유력"
    if needle in line and any(mark in line for mark in ("toast", "alert(", "confirm(", "setError", "setMessage")):
        return "사용자 노출 유력"
    if any(quote in line for quote in ("'", '"', "`")):
        return "문자열 확인 필요"
    return "기술 식별자 가능성"


def main() -> None:
    payload = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    files = [
        path for path in FRONTEND.rglob("*")
        if path.is_file() and path.suffix in SCAN_SUFFIXES and path not in SKIP_PATHS
    ]
    contents = {path: path.read_text(encoding="utf-8", errors="replace") for path in files}
    findings: dict[str, list[tuple[Path, int, str, str]]] = defaultdict(list)

    candidates = [
        entry for entry in payload["entries"]
        if entry["migration_status"] in {"권장안", "과거 별칭"}
        and entry["current_term"] != entry["recommended_user_term"]
        and len(entry["current_term"].strip()) >= 2
    ]
    for entry in candidates:
        needle = entry["current_term"]
        for path, text in contents.items():
            start = 0
            while True:
                pos = text.find(needle, start)
                if pos < 0:
                    break
                number = line_number(text, pos)
                snippet = text.splitlines()[number - 1].strip()
                findings[entry["id"]].append((path, number, snippet[:180], exposure_kind(snippet, needle)))
                start = pos + len(needle)

    rows = []
    for entry in candidates:
        matches = findings.get(entry["id"], [])
        if matches:
            rows.append((entry, matches))
    rows.sort(key=lambda item: (
        0 if item[0]["migration_status"] == "과거 별칭" else 1,
        -len(item[1]),
        item[0]["id"],
    ))

    total_occurrences = sum(len(matches) for _, matches in rows)
    likely_visible = sum(1 for _, matches in rows for *_, kind in matches if kind == "사용자 노출 유력")
    string_review = sum(1 for _, matches in rows for *_, kind in matches if kind == "문자열 확인 필요")
    likely_technical = sum(1 for _, matches in rows for *_, kind in matches if kind == "기술 식별자 가능성")
    comments = sum(1 for _, matches in rows for *_, kind in matches if kind == "주석")
    lines = [
        "# 기술·제품 용어 UI 전환 백로그",
        "",
        "> 생성일: 2026-08-12  ",
        "> 성격: 자동 치환 목록이 아닌 사용자 노출 여부 확인용 후보 목록  ",
        "> 정본: `data/terminology/technology_terminology_glossary.json`",
        "",
        "## 1. 실측 요약",
        "",
        f"- 검사 파일: **{len(files)}개** (`frontend/src`의 TS·TSX·HTML)",
        f"- 등장한 전환 후보 용어: **{len(rows)}개**",
        f"- 정확 문자열 등장 위치: **{total_occurrences}건**",
        f"- 사용자 노출 유력: **{likely_visible}건** · 문자열 확인 필요: **{string_review}건**",
        f"- 기술 식별자 가능성: **{likely_technical}건** · 주석: **{comments}건**",
        "- API 경로, 변수명, 타입명, 테스트 식별자는 이 목록만으로 변경하지 않습니다.",
        "",
        "## 2. 적용 순서",
        "",
        "1. `과거 별칭`이 실제 화면 문구로 노출되는 위치를 먼저 제거합니다.",
        "2. 메뉴·페이지 제목·버튼·빈 상태·도움말 순으로 권장 용어를 적용합니다.",
        "3. 로그·관리자 화면은 사용자 문구와 기술 식별자를 구분해 병기합니다.",
        "4. 한 화면군씩 시각 검증 후 반영하며 일괄 검색·치환은 금지합니다.",
        "",
        "## 3. 정확 문자열 후보",
        "",
        "| 우선 | ID | 현재 용어 | 권장 사용자 용어 | 상태 | 노출 유력 | 전체 위치 |",
        "|---:|---|---|---|---|---:|---:|",
    ]
    for index, (entry, matches) in enumerate(rows, start=1):
        visible_count = sum(1 for *_, kind in matches if kind == "사용자 노출 유력")
        lines.append(
            f'| {index} | `{entry["id"]}` | {entry["current_term"]} | '
            f'{entry["recommended_user_term"]} | {entry["migration_status"]} | {visible_count} | {len(matches)} |'
        )

    lines.extend(["", "## 4. 파일·줄 단위 확인 목록", ""])
    for entry, matches in rows:
        lines.extend([
            f'### {entry["id"]} · {entry["current_term"]} → {entry["recommended_user_term"]}',
            "",
        ])
        ordered_matches = sorted(matches, key=lambda item: (
            {"사용자 노출 유력": 0, "문자열 확인 필요": 1, "주석": 2, "기술 식별자 가능성": 3}[item[3]],
            item[0].as_posix(),
            item[1],
        ))
        for path, number, snippet, kind in ordered_matches[:30]:
            relative = path.relative_to(ROOT).as_posix()
            escaped = snippet.replace("`", "\\`")
            lines.append(f"- **{kind}** · `{relative}:{number}` — `{escaped}`")
        if len(matches) > 30:
            lines.append(f"- 그 외 {len(matches) - 30}건 — 동일 용어가 반복되는 구현 식별자일 수 있어 별도 확인")
        lines.append("")

    lines.extend([
        "## 5. 완료 판정",
        "",
        "- 사용자에게 보이는 문자열은 권장 용어 또는 승인된 병기 방식으로 표시됩니다.",
        "- 과거 별칭은 검색·이력에서만 찾을 수 있고 신규 UI 제목·메뉴·버튼에는 나타나지 않습니다.",
        "- 기술 표준명은 API·DB·코드 호환성을 유지하며 사용자 UI 변경과 분리됩니다.",
        "- 변경한 화면군은 1280×720과 1440×900에서 시각 검증합니다.",
        "",
        "## 6. 재생성",
        "",
        "```powershell",
        r"venv\Scripts\python.exe scripts\audit_terminology_usage.py",
        "```",
        "",
    ])
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {len(rows)}개 용어, {total_occurrences}개 위치")
    print(OUTPUT)


if __name__ == "__main__":
    main()
