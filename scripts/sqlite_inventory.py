# -*- coding: utf-8 -*-
"""[WEB-0] **SQLite 사용처 목록** — PostgreSQL 이관의 기준선을 봉인한다.

## 왜 지금 세는가

시연에서 SQLite 를 쓴다는 결정이 **상용 저장소 결정으로 굳지 않게** 하려면, 지금
「무엇이 어디에 있는가」를 적어 둬야 한다. 나중에 세면 그때는 이미 늘어 있고, 늘어난
것을 세는 일은 아무도 하지 않는다.

## 무엇을 세는가

    파일        어느 `.db` 가 있는가 (경로 · 소유 모듈)
    표          그 안의 표와 인덱스
    마이그레이션 `ALTER TABLE`·`PRAGMA table_info` 로 열을 늘리는 곳

⚠️ **운영 DB 를 열되 읽기만 한다.** 이 스크립트는 아무것도 쓰지 않는다.

사용:
    venv/Scripts/python.exe scripts/sqlite_inventory.py            # 표준출력
    venv/Scripts/python.exe scripts/sqlite_inventory.py --write    # 문서 생성
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SCAN_DIRS = ("core", "api")

#: 소유 모듈 판정용 — 코드에서 `db_path` 기본값에 쓰인 파일 이름을 찾는다.
_DB_LITERAL = re.compile(r'["\']([A-Za-z0-9_\-]+\.db)["\']')
#: ⚠️⚠️ 이 저장소의 마이그레이션은 **f-string 으로 조립된다**
#:   (`f"ALTER TABLE {table} ADD COLUMN {col} {decl}"`). 이름만 찾는 정규식은 0건을
#:   내고, 그 0은 「없다」로 읽힌다 — 실제로 이 도구가 처음에 그렇게 적었다.
#: ★ 그래서 **자리표시자도 토큰으로 받는다.** 이름을 정적으로 풀지 않는다(그것은 추측이다) —
#:   목적은 「어디서 스키마를 바꾸는가」를 세는 것이지 무엇으로 바꾸는가가 아니다.
_TOKEN = r'(\{[A-Za-z0-9_.\[\]\'"]+\}|[A-Za-z0-9_]+)'
_ALTER = re.compile(r'ALTER\s+TABLE\s+' + _TOKEN + r'\s+ADD\s+COLUMN\s+' + _TOKEN,
                    re.IGNORECASE)


def owners() -> Dict[str, List[str]]:
    """`.db` 파일 이름 → 그것을 언급하는 모듈들.

    ⚠️ 한 파일을 여러 모듈이 언급할 수 있다 — **하나로 접지 않는다.** 접으면 「소유자가
      하나」로 보이고, 실제로는 두 모듈이 같은 파일을 열고 있는 상태를 놓친다."""
    out: Dict[str, List[str]] = {}
    for d in SCAN_DIRS:
        for base, _dirs, names in os.walk(os.path.join(ROOT, d)):
            if "__pycache__" in base:
                continue
            for n in names:
                if not n.endswith(".py"):
                    continue
                path = os.path.join(base, n)
                try:
                    text = open(path, "r", encoding="utf-8").read()
                except OSError:
                    continue
                rel = os.path.relpath(path, ROOT).replace("\\", "/")
                for m in set(_DB_LITERAL.findall(text)):
                    out.setdefault(m, []).append(rel)
    return {k: sorted(set(v)) for k, v in out.items()}


def migrations() -> List[Tuple[str, str, str]]:
    """`ALTER TABLE … ADD COLUMN` 이 있는 곳 — (모듈, 표, 열).

    ★ 이것이 「마이그레이션 판」의 실체다. 이 저장소에는 마이그레이션 도구가 없고
      코드가 기동 때 열을 더한다 — PostgreSQL 로 갈 때 **그 자리가 전부 손으로 옮겨야
      하는 곳**이다."""
    out: List[Tuple[str, str, str]] = []
    for d in SCAN_DIRS:
        for base, _dirs, names in os.walk(os.path.join(ROOT, d)):
            if "__pycache__" in base:
                continue
            for n in names:
                if not n.endswith(".py"):
                    continue
                path = os.path.join(base, n)
                try:
                    text = open(path, "r", encoding="utf-8").read()
                except OSError:
                    continue
                rel = os.path.relpath(path, ROOT).replace("\\", "/")
                for i, line in enumerate(text.splitlines(), start=1):
                    for table, col in _ALTER.findall(line):
                        out.append((f"{rel}:{i}", table, col))
    return sorted(set(out))


def db_files() -> List[Tuple[str, int, List[str]]]:
    """`data/` 의 `.db` — (파일, 바이트, 표 목록). ⚠️ **읽기 전용**으로 연다."""
    out = []
    if not os.path.isdir(DATA):
        return out
    for n in sorted(os.listdir(DATA)):
        if not n.endswith(".db"):
            continue
        p = os.path.join(DATA, n)
        tables: List[str] = []
        try:
            #: ★ `mode=ro` — 이 스크립트는 아무것도 쓰지 않는다.
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            try:
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            finally:
                conn.close()
        except sqlite3.Error as exc:
            #: ⚠️ 못 읽은 것을 «표 0개» 로 적지 않는다.
            tables = [f"(읽지 못함: {exc})"]
        out.append((n, os.path.getsize(p), tables))
    return out


def render() -> str:
    own = owners()
    files = db_files()
    migs = migrations()

    lines: List[str] = [
        "# [WEB-0] SQLite 사용처 목록 — PostgreSQL 이관 기준선",
        "",
        "> ⚠️ **손으로 고치지 말 것** — `scripts/sqlite_inventory.py --write` 가 만든다.",
        ">",
        "> 시연에서 SQLite 를 쓴다는 결정이 **상용 저장소 결정으로 굳지 않게** 하려고",
        "> 지금 세어 둔다. 나중에 세면 그때는 이미 늘어 있다.",
        "",
        f"## 요약 — 파일 {len(files)}개 · 표 {sum(len(t) for _n, _s, t in files)}개 "
        f"· 기동 시 열 추가 {len(migs)}곳",
        "",
        "## 파일",
        "",
        "| 파일 | 크기 | 표 | 언급하는 모듈 |",
        "|---|---:|---:|---|",
    ]
    for name, size, tables in files:
        mods = own.get(name, [])
        # ⚠️ 소유 모듈을 못 찾은 파일은 «(코드에서 이름을 찾지 못함)» 으로 적는다 —
        #   빈 칸으로 두면 「소유자 없음」이 아니라 「안 봤음」이다.
        who = ", ".join(f"`{m}`" for m in mods) or "**(코드에서 이름을 찾지 못함)**"
        lines.append(f"| `{name}` | {size:,} | {len(tables)} | {who} |")

    lines += ["", "## 표", ""]
    for name, _size, tables in files:
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append(", ".join(f"`{t}`" for t in tables) if tables else "_(표 없음)_")
        lines.append("")

    lines += [
        "## ⚠️ 기동 시 열을 더하는 곳 — 이관에서 손으로 옮겨야 한다",
        "",
        "이 저장소에는 마이그레이션 도구가 없다. 코드가 기동 때 `ALTER TABLE ADD COLUMN`",
        "으로 열을 더한다. PostgreSQL 로 갈 때 **이 자리들이 전부 이관 대상**이다.",
        "",
        "| 위치 | 표 | 열 |",
        "|---|---|---|",
    ]
    for mod, table, col in migs:
        lines.append(f"| `{mod}` | `{table}` | `{col}` |")
    if not migs:
        #: ⚠️ **0을 「없음」으로 적지 않는다.** 이 도구가 처음에 그렇게 적었고 틀렸다 —
        #:   정규식이 f-string 자리표시자를 못 봤을 뿐이었다.
        lines.append("| _(0건)_ | | |")
        lines += ["",
                  "> ⚠️ 0건입니다. **「없다」가 아니라 「이 도구가 못 찾았다」일 수 있습니다** —",
                  "> `grep -rn \"ADD COLUMN\" core/ api/` 로 직접 확인하십시오."]

    lines += [
        "",
        "## 이관에서 특히 조심할 것",
        "",
        "- **부분 UNIQUE 인덱스**(`… WHERE status='active'`) — PostgreSQL 에도 있지만",
        "  문법과 계획이 다르다. 멱등을 DB 가 지키던 자리가 여기다.",
        "- **`julianday()` 트리거** — 기간 겹침을 막는 트리거가 SQLite 함수를 쓴다.",
        "  PostgreSQL 에는 없다(`tstzrange` + 배제 제약으로 옮겨야 한다).",
        "- **`executescript()` 의 조기 커밋** — 감싼 트랜잭션을 끊는다. 이관 스크립트가",
        "  같은 가정을 하면 반쪽만 적용된 스키마가 남는다.",
        "- **파일 경계가 곧 격리** — Preview 는 별도 파일이라 «논리 분리» 사고를 피했다.",
        "  한 DB 로 합치면 그 경계가 코드 조건문으로 내려온다(`core/app_preview.py` 머리말).",
        "",
    ]
    return "\n".join(lines)


def main_() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    text = render()
    if args.write:
        out = os.path.join(ROOT, "docs", "architecture", "SQLITE_INVENTORY.md")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"{out} 생성")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_())
