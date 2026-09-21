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
"""
from __future__ import annotations

import argparse
import json
import os
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
            print("      %-7s %-6s %-11s %-34s %s" % (
                v["version"], "동결" if v["frozen"] else "작업중", v["integrity"],
                name, v["status"]))
            for p in v["problems"]:
                print("               ! %s" % p[:80])
    s = c["summary"]
    print("\n── 요약")
    print("   씨앗 %d · 그중 선반에 %d" % (s["seed_count"], s["seed_on_shelf"]))
    print("   선반 키트 %d · 그중 **사업 정의가 없는 것 %d**"
          % (s["shelf_kits"], s["shelf_without_business"]))
    missing = [x["code"] for x in c["seeds"] if not x["on_shelf"]]
    if missing:
        print("\n   ⚠️ 뽑아 두지 않은 사업: %s" % ", ".join(missing))
        print("      python scripts/generate_sample_company_starter_kit.py "
              "--version <판본> --business %s" % missing[0])


def main() -> None:
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
