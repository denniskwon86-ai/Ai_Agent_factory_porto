#!/usr/bin/env python3
"""키트 선반 — **무엇을 줄 수 있고 어디가 비었나.**

    python scripts/kit_shelf.py            # 표
    python scripts/kit_shelf.py --json     # 기계용

## 왜 스크립트인가

손으로 쓴 표는 낡는다. 이 저장소에서 여러 번 겪었다 — 「사업 하나 50 줄」이 실제로는
30 줄이었고, 존재하지 않는 `wire_cable.py` 가 예시에 남아 있었다.

**진실은 두 곳에 있다.**

    씨앗   scripts/business_defs/*.py        무엇을 만들 수 있나
    선반   starter_kits/<KIT_ID>/<판본>/     실제로 만들어 둔 것

이 도구는 그 둘을 **대조**한다. 한쪽에만 있으면 그것이 빈 칸이다.

| 한쪽에만 | 뜻 |
|---|---|
| 씨앗만 있다 | 뽑아서 봉인하면 줄 수 있다 — **명령 세 개** |
| 선반만 있다 | 이 키트가 **어느 사업에서 나왔는지 모른다.** 재현할 수 없다 |

## 그리고 **지워도 되나**

★ 판본이 쌓이면 묵은 것을 지우고 싶어진다. 그때 물어야 할 것은 「오래됐나」가 아니라
  **「누가 가리키고 있나」**다.

⚠️ 실제로 데었다. 1.0.0·1.1.0 을 「봉인 결함이 있던 판본」이라고 지우려다 멈췄다 —
  둘은 **시험의 고정물**이었다. 특히 1.1.0 은 그 봉인 결함이 되살아나는지 지켜보는
  표본(`test_kit_freeze.py`)이고, 1.0.0 의 CSV 는 플랫폼 계산 카나리의 정본이다
  (`core/demo_vertical_slice.py`). 지웠으면 **감시가 조용히 사라졌을 것이다.**

그래서 손으로 「이건 지우지 마시오」를 적어 두지 않는다 — 그런 표는 낡는다.
**훑어서 센다.** 참조가 0 이면 지울 수 있고, 아니면 어디가 걸리는지 이름을 댄다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import business_defs  # noqa: E402
from core.data_preparation import kit_freeze, kit_registry  # noqa: E402


def seeds() -> list[dict]:
    """씨앗 — **뽑을 수 있는 것.** 사업 하나짜리와 **알려진 조합**을 함께 센다.

    ⚠️ 조합을 빼면 `KIT-MFG-NONFERROUS-PROCUREMENT`(제련+전지소재)가 「어느 사업에서
      나왔는지 모른다」로 잘못 잡힌다. 그것은 기본 조합에서 나온다.
    """
    out = []
    for code in business_defs.available():
        d = business_defs.load([code])[0]
        out.append({"code": code, "name": d.name, "kit_id": d.kit_id,
                    "kit_name": d.kit_name, "sector": d.sector, "use_case": d.use_case,
                    "businesses": [code]})
    import generate_sample_company_starter_kit as gen
    combo = business_defs.load(list(gen.DEFAULT_BUSINESSES))
    out.append({"code": "(기본 조합)", "name": " + ".join(d.name for d in combo),
                "kit_id": gen.DEFAULT_KIT[0], "kit_name": gen.DEFAULT_KIT[1],
                "sector": " / ".join(d.sector for d in combo), "use_case": gen.DEFAULT_KIT[2],
                "businesses": list(gen.DEFAULT_BUSINESSES)})
    return out


#: 참조를 훑을 곳. **선반 자신은 뺀다** — 판본 안의 파일이 제 판본 번호를 적고 있어
#: 전부가 「자기를 가리킨다」로 잡힌다. 남의 워크트리(`.claude/worktrees`)와 의존성도
#: 뺀다 — 이 저장소가 책임지는 코드가 아니다.
_SCAN_DIRS = ("core", "api", "scripts", "tests")
_SCAN_EXT = (".py", ".ts", ".tsx")

#: ⚠️ **이 파일도 뺀다.** 위 설명이 판본 번호를 예로 들고 있어, 빼지 않으면 그 판본
#:   전부가 「선반 도구가 쓴다」로 잡힌다 — 세는 도구가 제 그림자를 세는 꼴이다.
_SELF_FILE = "scripts/kit_shelf.py"

#: 훑은 결과를 한 번만 읽는다. 판본 9 개 × 파일 수백 개를 매번 읽으면 느리다.
_SOURCE_CACHE: list[tuple[str, str]] = []


def _sources() -> list[tuple[str, str]]:
    """훑을 파일 (상대경로, 내용). **문서는 보지 않는다** — 언급은 참조가 아니다."""
    if _SOURCE_CACHE:
        return _SOURCE_CACHE
    for d in _SCAN_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for cur, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in {"__pycache__", "node_modules", ".venv"}]
            for name in files:
                if not name.endswith(_SCAN_EXT):
                    continue
                full = os.path.join(cur, name)
                try:
                    with open(full, encoding="utf-8") as f:
                        text = f.read()
                except (OSError, ValueError):
                    continue
                rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
                if rel == _SELF_FILE:
                    continue
                _SOURCE_CACHE.append((rel, text))
    return _SOURCE_CACHE


def referrers(kit_id: str, version: str) -> dict:
    """이 판본을 **누가 가리키고 있나.** 지워도 되는지가 여기서 갈린다.

    두 가지를 가른다 — 확실한 것과 후보다.

    | | 어떻게 잡나 | 예 |
    |---|---|---|
    | `direct` | 경로가 **한 덩어리**로 적혀 있다 | `starter_kits/KIT-.../1.0.0/samples` |
    | `probable` | 한 파일에 키트 이름과 판본이 **따로** 있다 | `KIT_ID = "KIT-..."` + `KIT_VERSION = "1.0.0"` |

    ⚠️ **후보를 넉넉히 잡는다.** 지워도 되는지를 판단하는 도구라, 놓치는 쪽이
      더 나쁘다. `core/demo_vertical_slice.py` 가 바로 `probable` 로만 잡히는 꼴인데
      그것이 1.0.0 을 실제로 읽는 **가장 중요한 참조**다.

    ⚠️ **import 로 이어진 것은 못 잡는다.** `tests/test_calc_canary.py` 는 경로를
      직접 쓰지 않고 `demo_vertical_slice` 를 부른다. 그래서 여기 안 나온다 —
      나온 파일에서 사람이 한 겹 더 따라가야 한다.
    """
    joined = f"{kit_id}/{version}"
    #: `os.path.join(..., "KIT-...", "1.0.0")` 꼴. 따옴표·쉼표·공백을 느슨하게 본다.
    split = re.compile(re.escape(kit_id) + r'"\s*,\s*"' + re.escape(version))
    direct, probable = [], []
    for rel, text in _sources():
        if joined in text or split.search(text):
            direct.append(rel)
        elif kit_id in text and f'"{version}"' in text:
            probable.append(rel)
    return {"direct": sorted(direct), "probable": sorted(probable),
            "count": len(direct) + len(probable)}


def _manifest(path: str) -> dict:
    """판본의 manifest. **구조가 달라도 죽지 않는다** — 옛 키트는 키가 다르다."""
    try:
        with open(os.path.join(path, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def shelf() -> list[dict]:
    """선반 — **실제로 만들어 둔 것.** 디렉터리에 있는 것만 센다."""
    root = kit_registry.starter_packages_dir()
    if not os.path.isdir(root):
        return []
    out = []
    for kit_id in sorted(os.listdir(root)):
        kdir = os.path.join(root, kit_id)
        if not os.path.isdir(kdir):
            continue
        versions = []
        for ver in sorted(n for n in os.listdir(kdir) if os.path.isdir(os.path.join(kdir, n))):
            vdir = os.path.join(kdir, ver)
            m = _manifest(vdir)
            ok, problems = kit_freeze.verify(vdir)
            versions.append({
                "version": ver,
                "frozen": kit_freeze.is_frozen(vdir),
                "ledger": kit_freeze.load_fingerprints(vdir) is not None,
                "integrity": ("PASS" if ok else "FAIL") if kit_freeze.load_fingerprints(vdir) else "UNVERIFIED",
                "problems": problems[:3],
                "status": str(m.get("status") or ""),
                #: ⚠️ `kit_name` 은 새 필드다 — 옛 판본에는 없다. 카탈로그가 「이름이
                #:   없다」와 「이름이 회사명이다」를 구분할 수 있게 그대로 둔다
                "kit_name": str(m.get("kit_name") or ""),
                "company_name": str(m.get("company_name") or ""),
                "sector": m.get("sector") or [],
                "datasets": m.get("dataset_count"),
                #: ★ **지워도 되나.** 오래된 것이 아니라 가리키는 것이 없는 것이
                #:   지울 수 있는 것이다
                "referrers": referrers(kit_id, ver),
            })
        out.append({"kit_id": kit_id, "versions": versions})
    return out


def catalog() -> dict:
    """씨앗과 선반을 대조한다. **빈 칸이 이 도구의 산출물이다.**"""
    sd, sh = seeds(), shelf()
    by_kit = {k["kit_id"]: k for k in sh}
    for s in sd:
        s["on_shelf"] = [v["version"] for v in by_kit.get(s["kit_id"], {}).get("versions", [])]
    seeded = {s["kit_id"] for s in sd if s["kit_id"]}
    for k in sh:
        k["from_business"] = k["kit_id"] in seeded
    return {
        "seeds": sd, "shelf": sh,
        "summary": {
            "seed_count": len(sd),
            "seed_on_shelf": sum(1 for s in sd if s["on_shelf"]),
            "shelf_kits": len(sh),
            "shelf_without_business": sum(1 for k in sh if not k["from_business"]),
            "versions": sum(len(k["versions"]) for k in sh),
            #: 가리키는 곳이 없는 판본. **지울 후보이지 지우라는 말이 아니다** —
            #: import 로 이어진 것은 훑기가 못 잡는다(`referrers` 참고)
            "unreferenced": [f'{k["kit_id"]}/{v["version"]}' for k in sh
                             for v in k["versions"] if not v["referrers"]["count"]],
        },
    }


def _print(c: dict) -> None:
    print("── 씨앗 (뽑을 수 있는 것)")
    for s in c["seeds"]:
        mark = " ".join(s["on_shelf"]) if s["on_shelf"] else "✗ 선반에 없다"
        print("   %-20s %-32s %s" % (s["code"], s["kit_id"] or "(이름 없다)", mark))
        print("   %-20s %s" % ("", s["sector"]))
    print("\n── 선반 (실제로 만들어 둔 것)")
    for k in c["shelf"]:
        tag = "" if k["from_business"] else "   ⚠️ 어느 사업에서 나왔는지 모른다"
        print("   %s%s" % (k["kit_id"], tag))
        for v in k["versions"]:
            #: ⚠️ `kit_name` 이 없으면 카탈로그가 **회사명을 키트 이름으로 쓴다**
            #:   (`kit_registry.py:126`). 그 사실이 보이게 적는다.
            name = v["kit_name"] or (v["company_name"] and f'{v["company_name"]} ← 회사명')                 or "(이름 없음)"
            r = v["referrers"]
            #: ★ 참조가 있으면 **지우면 깨진다.** 그 사실을 판본 줄에 바로 붙인다
            ref = ("← %d 곳이 쓴다" % r["count"]) if r["count"] else "지울 수 있다"
            print("      %-7s %-6s %-11s %-30s %-13s %s" % (
                v["version"], "동결" if v["frozen"] else "작업중", v["integrity"],
                name, v["status"], ref))
            for p in v["problems"]:
                print("               ! %s" % p[:80])
            for who in r["direct"][:4]:
                print("               · %s" % who)
            for who in r["probable"][:3]:
                print("               · %s  (판본만 따로 적혀 있다)" % who)
    s = c["summary"]
    print("\n── 요약")
    print("   씨앗 %d · 그중 선반에 %d" % (s["seed_count"], s["seed_on_shelf"]))
    print("   선반 키트 %d · 판본 %d · 그중 **사업 정의가 없는 것 %d**"
          % (s["shelf_kits"], s["versions"], s["shelf_without_business"]))
    if s["unreferenced"]:
        print("\n   가리키는 곳이 없는 판본: %s" % ", ".join(s["unreferenced"]))
        print("      ⚠️ **지워도 된다는 뜻은 아니다.** import 로 이어진 참조는"
              " 이 훑기가 못 본다")
    else:
        print("\n   ★ 모든 판본을 무언가가 쓰고 있다 — 지울 수 있는 것이 없다")
    missing = [x["code"] for x in c["seeds"] if not x["on_shelf"]]
    if missing:
        print("\n   ⚠️ 뽑아 두지 않은 사업: %s" % ", ".join(missing))
        print("      python scripts/generate_sample_company_starter_kit.py "
              "--version <판본> --business %s" % missing[0])


def main() -> None:
    #: ⚠️ Windows 기본 콘솔은 cp949 라 `⚠️`·`★` 에서 `UnicodeEncodeError` 로 죽는다.
    #:   출력이 쓰임새의 전부인 도구가 그것 때문에 안 도는 것은 결함이다.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description="키트 선반 — 무엇을 줄 수 있고 어디가 비었나")
    ap.add_argument("--json", action="store_true", help="기계용 출력")
    args = ap.parse_args()
    c = catalog()
    if args.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))
    else:
        _print(c)


if __name__ == "__main__":
    main()
