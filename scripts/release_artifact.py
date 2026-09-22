# -*- coding: utf-8 -*-
"""[P1 · DEP-02/09] 배포 산출물 — **허용목록 · 내용 검사 · 완결성 · manifest**.

## 왜 필요한가

`deploy/README.md` §4 는 「`update.sh` 가 `git archive` 로 추적된 파일만 내보낸다」고
적어 두었는데, **그 스크립트에는 `git archive` 가 없다.** 운영 위치에서 `git pull` 을 하고
끝난다. 즉 **허용목록이 문서에만 있다**(2026-09-21 확인 · DEP-02).

⚠️⚠️ 그리고 **「추적된 파일만」은 비밀·업무자료 배제의 충분조건이 아니다.**
추적되는 파일 안에 키가 적혀 있으면 그대로 나간다. 그래서 세 가지를 따로 본다 —
**무엇을 넣는가(경로)** · **그 안에 무엇이 들었는가(내용)** · **빠진 게 없는가(완결성)**.

## 네 가지 판정

    선별   허용목록에 든 것만. 거부목록이 허용목록을 «이긴다».
    내용   비밀로 보이는 것이 있으면 **산출물을 만들지 않는다.**
    필수   있어야 할 자산이 없으면 «성공» 하지 않는다(빌드 누락을 통과시키지 않는다).
    완결   ★ 앱이 import 하는데 허용목록에 없는 모듈이 있으면 **실패**한다.

★ 넷째가 없으면 **조용히 깨진 산출물**이 나간다. 실제로 이 도구의 첫 초안이 그랬다 —
  `config.py`(19곳에서 import)를 허용목록에 넣지 않았는데 앞의 세 검사는 전부 초록이었다.
  「필수 자산 목록」은 내가 «생각난 것» 만 담는다. 완결성 검사는 **코드에게 묻는다.**

⚠️ 이 도구는 **읽기만 한다.** manifest 출력 경로 외에는 아무것도 쓰지 않는다.
⚠️ 찾은 내용을 **출력하지 않는다.** 「어느 파일 몇 번째 줄에 어떤 «종류»」까지만 말한다 —
  경고문에 값을 실으면 그 경고가 다시 유출 경로가 된다.

사용:
    venv/Scripts/python.exe scripts/release_artifact.py --check
    venv/Scripts/python.exe scripts/release_artifact.py --manifest out/manifest.json
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import sys
from typing import Dict, Iterable, List, Optional, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: ── 허용목록 — **여기 없으면 나가지 않는다.** ────────────────────────────
#:   ⚠️ 「제외할 것을 적는」 방식이 아니다. 새 디렉터리가 생겼을 때 조용히 딸려 나가는 쪽은
#:     언제나 제외목록 방식이다 — 아무도 새 디렉터리를 제외목록에 더하지 않는다.
#:
#:   ★ `scripts/**` 는 **일부러 뺐다.** 실측: `deploy/*.sh` 와 `afs.service` 어디에서도
#:     `scripts/` 를 부르지 않고(`ExecStart=… -m uvicorn main:app`), 제품 코드도 import 하지
#:     않는다. 그런데 그 안에는 **운영 DB 에 자료를 심는 도구 8종과 이관 도구**가 있다.
#:     운영 호스트가 그것을 들고 있을 이유가 없다. 필요하면 «이름을 적어» 다시 넣는다.
ALLOW = (
    "main.py", "run.py", "config.py", "criteria.py", "state_models.py",
    "requirements.txt",
    "api/**", "core/**", "nodes/**", "deploy/**",
    "frontend/dist/**",
    #: 런타임에 «읽는» 자산 — 코드가 아니라서 import 폐포로는 안 잡힌다.
    #:   실측한 참조처를 옆에 적는다. 근거 없이 디렉터리를 더하지 않는다.
    #: ★ `scripts/` 에서 **이름을 적어** 되넣은 유일한 것. 이 탐침은 승격 판정을 내리는
    #:   주체라서 **노드 위에 있어야 한다**(DEP-06). 표준 라이브러리만 쓴다.
    "scripts/serving_readiness_probe.py",
    "playbooks/**",     # core/advisor_playbook.py: PLAYBOOKS_DIR
    "process_packs/**", # api/routes/process_installation_control.py: manifest.json
    "skills/**",        # api/routes/factory_control.py: skills/{id}.md
    "starter_kits/**",  # core/data_preparation/kit_registry.py
    "templates/**",     # core/agent_registry.py: TEMPLATES_DIR
    "tools/**",         # nodes/utils/backend_smoke.py: tools/backend_smoke_run.py
)

#: ── 거부목록 — 허용목록을 «이긴다». 두 종류로 나눈다. ───────────────────
#:   ★ 나누는 이유: 「업무자료 형식」 거부를 그대로 두면 `starter_kits/` 의 CSV 71·XLSX 36 이
#:     함께 잘려 **스타터 킷이 조용히 반쪽**으로 나간다. 반대로 통째로 허용하면 그 규칙이
#:     장식이 된다. 그래서 **예외가 «없는» 거부**와 **제품 자산 안에서만 풀리는 거부**를
#:     가르고, 예외로 나가는 건수를 매 실행 결과에 **숫자로 남긴다**(§verify).
DENY_ALWAYS = (
    "**/.env", "**/.env.*", "**/*.db", "**/*.sqlite", "**/*.sqlite3",
    "**/*.db-wal", "**/*.db-shm",
    "data/**", "output/**", "library/**", "projects/**", "workspace/**",
    #: `raw/` 는 스냅숏이 올린 **불변 원자료** 영역이다(snapshot_service.RAW_DIRNAME).
    "raw/**", "data_sync/**", "demo_data/**", "_archive/**", "tmp/**",
    #: 사용자가 만든 제안 — 제품 자산이 아니다.
    "skills/_proposals/**",
    "**/__pycache__/**", "**/node_modules/**", "**/.git/**", "venv/**",
    "**/*.pem", "**/*.key", "**/*.pfx", "**/*.p12",
    "**/*.log", "**/*.jsonl", "**/*.bak",
    #: ★ [W03.2] 원자·조건부 저장이 정본 «옆에» 남기는 것들. 잠금 파일은 지우면
    #:   상호배제가 깨지므로 **남는 것이 규약**이고(`core.atomic_write.LOCK_SUFFIX`),
    #:   임시 파일은 실행 중에 스쳐 지나간다. 둘 다 산출물이 아니다.
    #: ⚠️ 지금은 정본이 `library/`·`projects/` 에 있어 어차피 제외되지만, **제품이 새로
    #:   만드는 파일 종류는 명시로 막는다** — 「어차피 안 걸린다」에 기대면 정본 위치가
    #:   바뀌는 날 조용히 실린다.
    "**/*.lck", "**/*.tmp",
)

#: 업무자료 «형식» — 코드 디렉터리에 섞여 있으면 내보내지 않는다.
DENY_FORMAT = ("**/*.zip", "**/*.csv", "**/*.xlsx", "**/*.xls", "**/*.pdf", "**/*.hwp")

#: ⚠️ 형식 거부가 풀리는 **유일한** 자리. 여기 아닌 곳의 CSV·XLSX 는 그대로 잘린다.
#:   ★ 이 목록을 늘리는 것은 **승인 경계**다 — 늘릴 때는 무엇이 왜 제품 자산인지 적는다.
ASSET_PREFIXES = ("starter_kits/", "process_packs/", "templates/")

#: ── 필수 자산 — 없으면 «성공» 하지 않는다. ──────────────────────────────
#:   ★ [DEP-09] `preview-vendor` 3종은 `prebuild` 가 만든다. index/chunk 만 보면
#:     **미리보기가 통째로 죽은 산출물**을 정상으로 내보낸다.
REQUIRED = (
    "frontend/dist/index.html",
    "frontend/dist/preview-vendor/runtime.js",
    "frontend/dist/preview-vendor/babel.js",
    "frontend/dist/preview-vendor/tailwind.js",
    "main.py", "requirements.txt",
)

#: 완결성 검사의 출발점. 서비스가 실제로 켜는 것은 `main:app` 이다(`afs.service`).
ENTRY_POINTS = ("main.py", "run.py")

#: ── 내용 검사 — «종류» 만 보고하고 값은 싣지 않는다. ─────────────────────
SECRET_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("개인키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS 접근키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Anthropic 키", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI 키", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("Google 키", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("암호가 박힌 DSN", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb)://[^\s:@/]+:[^\s@/]+@")),
    ("Slack 토큰", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
)

#: ★ **예외 목록을 두지 않는다.**
#:   처음엔 「검사기 자신은 패턴을 적어 두니 빼 두자」고 예외를 넣었는데, 실측해 보니
#:   자기 자신도 걸리지 않았다 — 패턴의 «소스» 는 그 패턴에 맞지 않는다.
#:   ⚠️ 예외가 한 줄 생기면 **그 파일 전체가 영원히 검사 밖**이 된다. 나중에 같은 파일에
#:     들어온 진짜 키는 아무도 못 본다. 그래서 없는 채로 둔다.
#:   실제로 이 검사기가 처음 잡은 한 건(`core/connector_registry.py` 주석의 DSN 예시)도
#:   예외로 덮지 않고 **그 «모양» 자체를 없애서** 풀었다.

#: 내용을 읽을 수 있는 형식. ★ `.csv` 가 들어 있는 이유: 형식 예외로 «나가는» 파일이면
#:   반드시 내용도 본다 — 나가는데 안 보는 자리가 생기면 거기가 구멍이다.
#: ⚠️ **`.xlsx` 36건은 이 검사를 받지 못한다**(바이너리). 스타터 킷의 엑셀은 사람이
#:   내용을 확인해야 하고, 이 도구가 「봤다」고 말하지 않는다.
TEXT_SUFFIX = (".py", ".js", ".mjs", ".ts", ".tsx", ".json", ".sh", ".md",
               ".yml", ".yaml", ".html", ".css", ".txt", ".service", ".sql", ".csv")


# ── 선별 ────────────────────────────────────────────────────────────────
def _matches(path: str, patterns: Iterable[str]) -> bool:
    posix = path.replace(os.sep, "/")
    for pattern in patterns:
        if fnmatch.fnmatch(posix, pattern):
            return True
        #: `api/**` 는 `api/x.py` 도 잡아야 한다(fnmatch 는 `**` 를 그렇게 보지 않는다).
        if pattern.endswith("/**") and posix.startswith(pattern[:-2]):
            return True
    return False


def _is_product_asset(rel: str) -> bool:
    return rel.startswith(ASSET_PREFIXES)


def is_denied(rel: str) -> bool:
    """거부되는가. **항상 거부**가 먼저고, 형식 거부는 제품 자산 안에서만 풀린다."""
    if _matches(rel, DENY_ALWAYS):
        return True
    return _matches(rel, DENY_FORMAT) and not _is_product_asset(rel)


def selected_files(root: Optional[str] = None) -> List[str]:
    """산출물에 들어갈 파일. **허용목록에 들고 거부되지 않는 것만.**"""
    root = root or ROOT
    out: List[str] = []
    for folder, dirs, names in os.walk(root):
        rel_dir = os.path.relpath(folder, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        #: 거부되는 디렉터리는 **내려가지도 않는다** — 큰 트리를 걷는 시간도 비용이다.
        dirs[:] = [d for d in dirs
                   if not _matches(f"{rel_dir}/{d}".lstrip("/") + "/x", DENY_ALWAYS)]
        for name in names:
            rel = f"{rel_dir}/{name}".lstrip("/")
            if is_denied(rel):
                continue
            if _matches(rel, ALLOW):
                out.append(rel)
    return sorted(out)


def business_format_exceptions(files: Iterable[str]) -> Dict[str, int]:
    """★ 형식 거부를 «풀고» 나가는 파일을 prefix 별로 센다.

    ⚠️ 이 숫자는 숨기지 않는다. 예외가 조용하면 그 예외는 반드시 자란다."""
    counts: Dict[str, int] = {}
    for rel in files:
        if _matches(rel, DENY_FORMAT) and _is_product_asset(rel):
            prefix = next(a for a in ASSET_PREFIXES if rel.startswith(a))
            counts[prefix] = counts.get(prefix, 0) + 1
    return dict(sorted(counts.items()))


# ── 내용 ────────────────────────────────────────────────────────────────
def scan_contents(files: Iterable[str],
                  root: Optional[str] = None) -> List[Dict[str, object]]:
    """비밀로 보이는 내용을 찾는다. **값은 돌려주지 않는다** — 종류와 자리만."""
    root = root or ROOT
    findings: List[Dict[str, object]] = []
    for rel in files:
        if not rel.endswith(TEXT_SUFFIX):
            continue
        try:
            with open(os.path.join(root, rel), "r", encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    for kind, pattern in SECRET_PATTERNS:
                        if pattern.search(line):
                            findings.append({"path": rel, "line": lineno, "kind": kind})
        except OSError:
            findings.append({"path": rel, "line": 0, "kind": "읽지 못함"})
    return findings


# ── 완결성 ──────────────────────────────────────────────────────────────
#: ⚠️ **앱을 import 해서 알아내지 않는다.** import 는 DDL·seed 를 돌리고 자료를 바꾼다.
#:   그래서 파일을 «읽어» 해석한다 — 실행하지 않는다.
def _module_file(dotted: str, root: str) -> Optional[str]:
    rel = dotted.replace(".", "/")
    for candidate in (rel + ".py", rel + "/__init__.py"):
        if os.path.exists(os.path.join(root, candidate)):
            return candidate
    return None


def _packages_above(rel: str) -> List[str]:
    """`core/a/b.py` → `core/__init__.py`, `core/a/__init__.py`.

    ⚠️ 패키지 `__init__.py` 가 빠지면 그 아래 모듈은 **import 자체가 안 된다.**"""
    parts = rel.split("/")[:-1]
    return ["/".join(parts[: i + 1]) + "/__init__.py" for i in range(len(parts))]


def _dotted_names(tree: ast.AST, package: str) -> List[str]:
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                #: 상대 import — 현 패키지에서 `level-1` 만큼 올라간다.
                parts = [p for p in package.split(".") if p]
                if node.level > 1:
                    parts = parts[: max(0, len(parts) - (node.level - 1))]
                base = ".".join(parts + ([base] if base else []))
            if base:
                names.append(base)
                #: `from pkg import mod` 의 `mod` 는 **모듈일 수도** 심볼일 수도 있다.
                names.extend(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            #: `importlib.import_module("core.x")` — 문자열이 리터럴일 때만 따라간다.
            func = node.func
            called = getattr(func, "attr", None) or getattr(func, "id", None)
            #: `__import__("nodes.vision_qa", fromlist=[...])` 가 실제로 쓰인다
            #:   (`core/agent_graph.py`). 이름이 다르다고 놓치면 **패키지 하나가 통째로**
            #:   산출물에서 빠진 채 초록이 된다.
            if called in ("import_module", "__import__") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.append(first.value)
    return names


def imported_local_files(root: Optional[str] = None,
                         entries: Iterable[str] = ENTRY_POINTS) -> Set[str]:
    """진입점에서 출발해 **저장소 안의** 모듈만 따라간 폐포."""
    root = root or ROOT
    found: Set[str] = set()
    queue = [e for e in entries if os.path.exists(os.path.join(root, e))]
    found.update(queue)
    seen: Set[str] = set()
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.add(rel)
        try:
            with open(os.path.join(root, rel), "r", encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read(), filename=rel)
        except (OSError, SyntaxError):
            continue
        package = os.path.dirname(rel).replace("/", ".")
        for dotted in _dotted_names(tree, package):
            target = _module_file(dotted, root)
            if not target:
                continue  #: 표준 라이브러리·서드파티 — 저장소 밖이면 우리 몫이 아니다.
            for extra in _packages_above(target) + [target]:
                if os.path.exists(os.path.join(root, extra)) and extra not in found:
                    found.add(extra)
                    queue.append(extra)
    return found


def missing_imports(files: Iterable[str], root: Optional[str] = None) -> List[str]:
    """★ 앱이 읽는데 산출물에 **없는** 모듈. 하나라도 있으면 그 산출물은 깨져 있다."""
    root = root or ROOT
    present = set(files)
    return sorted(m for m in imported_local_files(root) if m not in present)


# ── 필수 · 기록 ─────────────────────────────────────────────────────────
def missing_required(files: Iterable[str]) -> List[str]:
    present = set(files)
    return [r for r in REQUIRED if r not in present]


def build_manifest(files: Iterable[str],
                   root: Optional[str] = None) -> Dict[str, object]:
    """경로별 SHA-256. **배포된 것이 무엇이었는지** 나중에 답할 수 있게."""
    root = root or ROOT
    entries = {}
    for rel in files:
        full = os.path.join(root, rel)
        digest = hashlib.sha256()
        with open(full, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                digest.update(block)
        entries[rel] = {"sha256": digest.hexdigest(), "bytes": os.path.getsize(full)}
    return {"file_count": len(entries), "files": entries}


def verify(root: Optional[str] = None) -> Dict[str, object]:
    """선별 → 필수 → 완결 → 내용. **하나라도 걸리면 ok=False.**"""
    #: ⚠️ 기본값에 `ROOT` 를 «박지» 않는다. 파이썬은 기본값을 **정의 시점에 한 번** 묶으므로
    #:   나중에 `ROOT` 를 바꿔도 따라오지 않는다 — 「바꿀 수 있어 보이는데 안 바뀌는」
    #:   함정이고, 실제로 내 시험이 그것에 걸렸다.
    root = root or ROOT
    files = selected_files(root)
    missing_req = missing_required(files)
    missing_mod = missing_imports(files, root)
    findings = scan_contents(files, root)
    return {"ok": not (missing_req or missing_mod or findings),
            "file_count": len(files),
            "missing_required": missing_req,
            "missing_imported_modules": missing_mod,
            "secret_findings": findings,
            #: 실패 사유가 아니다 — **보여 주는** 값이다. 늘어나면 눈에 띄어야 한다.
            "business_format_exceptions": business_format_exceptions(files)}


def main() -> int:
    ap = argparse.ArgumentParser(description="배포 산출물 허용목록·검사·manifest")
    #: 검사는 «언제나» 돈다 — 이 플래그는 CI 에서 의도를 드러내는 이름일 뿐이다.
    ap.add_argument("--check", action="store_true", help="선별·필수·완결·내용 검사(기본 동작)")
    ap.add_argument("--manifest", metavar="PATH", help="manifest 를 이 경로에 쓴다")
    ap.add_argument("--list", action="store_true", help="선별된 경로를 출력")
    args = ap.parse_args()

    result = verify()
    if args.list:
        for rel in selected_files():
            print(rel)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.manifest:
        if not result["ok"]:
            #: ⚠️ 검사에 걸린 트리로 manifest 를 만들지 않는다 — 그 manifest 가
            #:   「검사를 통과했다」는 기록처럼 쓰인다.
            print("검사에 걸려 manifest 를 만들지 않았습니다.", file=sys.stderr)
            return 1
        folder = os.path.dirname(os.path.abspath(args.manifest))
        os.makedirs(folder, exist_ok=True)
        with open(args.manifest, "w", encoding="utf-8") as f:
            json.dump(build_manifest(selected_files()), f, ensure_ascii=False, indent=2)
        print(f"manifest: {args.manifest}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
