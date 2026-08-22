# -*- coding: utf-8 -*-
"""[WEB-1] **런타임 의존성 정본**을 코드에서 도출한다.

## 왜 `pip freeze` 를 쓰지 않는가

이 환경에는 189개가 설치돼 있고 그중 다수는 시험·도구다(pytest·playwright·ruff…).
통째로 얼려 배포하면 **서버에 시험 도구가 깔린다** — 용량 문제가 아니라, 배포본에
있는 것은 언젠가 실행되고 그때 그것은 통제 밖이다.

## 어떻게 도출하는가 — 두 축을 합친다

    ① 정적 스캔   `main.py`·`run.py`·`api/`·`core/` 의 import 문
    ② 실측        `import main` 뒤 `sys.modules` 에 남은 서드파티 최상위 모듈

⚠️ 하나만 쓰면 빠진다. ①은 **동적 import**(문자열·지연 로딩)를 못 보고, ②는 **요청
  시점에만 불리는 모듈**을 못 본다. 합집합이 런타임 집합이다.

⚠️⚠️ 그래도 이것은 **후보**다. 「Ubuntu 빈 VM 에서 설치되고 첫 화면이 열린다」는
  WEB-1 완료 조건은 실제 VM 에서만 증명된다 — 이 스크립트가 그것을 대신하지 않는다.

사용:
    venv/Scripts/python.exe scripts/derive_runtime_requirements.py            # 미리보기
    venv/Scripts/python.exe scripts/derive_runtime_requirements.py --write    # 파일 생성
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from importlib import metadata
from typing import Dict, Set

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: 런타임에 실제로 도는 코드. ⚠️ `tests/`·`scripts/` 는 넣지 않는다 — 배포되지 않는다.
RUNTIME_ROOTS = ("main.py", "run.py", "config.py", "api", "core")

def _first_party() -> Set[str]:
    """저장소 자체 모듈 — **저장소 루트를 보고 판정한다.**

    ⚠️ 손으로 나열하지 않는다. `criteria`·`nodes`·`state_models` 처럼 루트에 놓인
      최상위 모듈이 서드파티로 오인돼 「배포 이름을 찾지 못함」으로 나왔다 — 목록을
      손으로 관리하면 파일이 하나 늘 때마다 같은 일이 난다."""
    out: Set[str] = set()
    for name in os.listdir(ROOT):
        full = os.path.join(ROOT, name)
        if name.endswith(".py"):
            out.add(name[:-3])
        elif os.path.isdir(full) and not name.startswith("."):
            #: 패키지든 아니든 루트 디렉터리 이름은 import 이름이 될 수 있다.
            out.add(name)
    return out


FIRST_PARTY = _first_party()

#: ⚠️ 표준 라이브러리 판정은 **버전에 따라 다르다.** 하드코딩하지 않는다.
STDLIB = set(sys.stdlib_module_names)

#: **설치돼 있지 않은 것이 정상인 모듈**과 그 이유.
#:
#: ⚠️ 「나중에 보자」로 여기 올리지 않는다 — 면제 목록은 조용히 자란다. 각 항목은
#:   «없어도 앱이 도는 이유» 를 적어야 하고, 그러지 못하면 그것은 빠진 의존성이다.
#: ★ 비워 두면 매번 경고가 나오고, **매번 나오는 경고는 아무도 안 읽는다.**
KNOWN_ABSENT = {
    "langchain": ("core/run_context.py 의 방어된 대체 import — langchain_core 를 먼저 "
                  "시도하고, 둘 다 실패하면 object 로 내려간다."),
    "cython_runtime": "Cython 확장이 만드는 가짜 모듈. 배포 패키지가 아니다.",
}


def _top(name: str) -> str:
    return (name or "").split(".")[0]


def static_imports() -> Set[str]:
    """정적 스캔 — import 문에서 최상위 모듈 이름을 모은다."""
    found: Set[str] = set()
    for rel in RUNTIME_ROOTS:
        path = os.path.join(ROOT, rel)
        files = []
        if os.path.isfile(path):
            files = [path]
        elif os.path.isdir(path):
            for base, _dirs, names in os.walk(path):
                if "__pycache__" in base:
                    continue
                files += [os.path.join(base, n) for n in names if n.endswith(".py")]
        for f in files:
            try:
                tree = ast.parse(open(f, "r", encoding="utf-8").read(), filename=f)
            except SyntaxError:
                #: ⚠️ 못 읽은 파일을 조용히 넘기지 않는다 — 그 파일의 의존성이 통째로 빠진다.
                print(f"  ⚠️ 구문 오류로 건너뜀: {f}", file=sys.stderr)
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        found.add(_top(a.name))
                elif isinstance(node, ast.ImportFrom):
                    #: 상대 import(`from .x import y`)는 자기 패키지다.
                    if node.level == 0 and node.module:
                        found.add(_top(node.module))
    return found


def runtime_imports() -> Set[str]:
    """실측 — 앱을 import 한 뒤 실제로 적재된 서드파티 최상위 모듈."""
    sys.path.insert(0, ROOT)
    before = set(sys.modules)
    try:
        import main  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        #: ⚠️ 앱을 못 띄우면 **도출을 멈춘다.** 반쪽 목록으로 배포본을 만들면 서버에서
        #:   ModuleNotFoundError 가 나고, 그때 원인은 「배포 스크립트」로 보인다.
        raise SystemExit(f"앱을 import 하지 못해 의존성을 도출할 수 없습니다: {exc}")
    return {_top(m) for m in set(sys.modules) - before}


def _dist_map() -> Dict[str, str]:
    """최상위 모듈 → 배포 이름. ⚠️ 둘은 자주 다르다(`yaml` → `PyYAML`)."""
    out: Dict[str, str] = {}
    for mod, dists in metadata.packages_distributions().items():
        for d in dists:
            out.setdefault(mod, d)
    return out


def _is_stdlib(mod: str) -> bool:
    if mod in STDLIB:
        return True
    try:
        spec = __import__(mod) and None
    except Exception:  # noqa: BLE001
        spec = None
    _ = spec
    return False


def main_() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="requirements.txt 를 만든다")
    args = ap.parse_args()

    static = static_imports()
    live = runtime_imports()
    mods = {m for m in (static | live)
            if m and m not in FIRST_PARTY and not m.startswith("_")
            and not _is_stdlib(m)}

    dmap = _dist_map()
    pinned: Dict[str, str] = {}
    unknown = []
    for m in sorted(mods):
        dist = dmap.get(m)
        if not dist:
            #: 설치돼 있지 않거나 이름을 못 찾았다 — **조용히 빼지 않는다.**
            unknown.append(m)
            continue
        try:
            pinned[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            unknown.append(m)

    lines = [f"{d}=={v}" for d, v in sorted(pinned.items(), key=lambda kv: kv[0].lower())]
    print(f"런타임 의존성 {len(lines)}개 (정적 {len(static)} · 실측 {len(live)})")
    for line in lines:
        print("  " + line)
    benign = sorted(m for m in unknown if m in KNOWN_ABSENT)
    real_unknown = sorted(m for m in unknown if m not in KNOWN_ABSENT)
    if benign:
        print("")
        print("· 설치되지 않은 것이 정상인 모듈:")
        for m in benign:
            print(f"    {m} — {KNOWN_ABSENT[m]}")
    if real_unknown:
        #: ⚠️ 「모르는 것」을 목록에서 조용히 빼면 배포본이 그것 없이 나간다.
        print("")
        print("⚠️ 배포 이름을 찾지 못한 모듈(직접 확인 필요): "
              + ", ".join(real_unknown))

    if args.write:
        header = [
            "# [WEB-1] 런타임 의존성 **정본**.",
            "#",
            "# ⚠️ 손으로 고치지 말 것 — `scripts/derive_runtime_requirements.py --write` 가 만든다.",
            "#   손으로 고치면 코드가 쓰는 것과 배포본이 갈라지고, 갈린 날 서버에서만 죽는다.",
            "#",
            "# ⚠️ `pip freeze` 가 아니다. 시험·도구(pytest·playwright…)는 여기 없다 —",
            "#   배포본에 있는 것은 언젠가 실행되고, 그때 그것은 통제 밖이다.",
            "#   개발 의존성은 `requirements-dev.txt` 에 있다.",
            f"# 도출 기준: {RUNTIME_ROOTS}",
            "",
        ]
        out = os.path.join(ROOT, "requirements.txt")
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(header + lines) + "\n")
        print(f"\n{out} 생성")
        if real_unknown:
            print("⚠️ 위 «찾지 못한 모듈» 은 파일에 들어가지 않았다 — 직접 확인할 것.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_())
