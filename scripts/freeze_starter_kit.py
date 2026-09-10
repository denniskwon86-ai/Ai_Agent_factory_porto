#!/usr/bin/env python3
"""[P1] 검증이 끝난 Starter Kit 판본을 동결한다.

    python scripts/freeze_starter_kit.py KIT-MFG-NONFERROUS-PROCUREMENT 1.0.0
    python scripts/freeze_starter_kit.py --list
    python scripts/freeze_starter_kit.py --verify KIT-MFG-NONFERROUS-PROCUREMENT 1.0.0

동결하면 판본 디렉터리에 두 파일이 생긴다.

- `fingerprint.json` — 파일별 sha256 대장. 검증기가 이것과 대조한다.
- `.frozen` — 언제·왜·누가 동결했는지. 생성기가 이 표식을 보고 거부한다.

**검증(`validate_sample_company_starter_kit.py`)이 PASS 한 뒤에 부른다.** 검증 전에
얼리면 깨진 판본을 확정하는 셈이 된다.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.data_preparation import kit_freeze  # noqa: E402

PACKAGES = ROOT / "starter_kits"


def _versions():
    for kit in sorted(p for p in PACKAGES.iterdir() if p.is_dir()):
        for ver in sorted(p for p in kit.iterdir() if p.is_dir()):
            yield kit.name, ver.name, ver


def cmd_list() -> int:
    rows = []
    for kit_id, version, path in _versions():
        ok, problems = kit_freeze.verify(str(path))
        rows.append({
            "kit_id": kit_id, "version": version,
            "manifest_status": kit_freeze.manifest_status(str(path)),
            "frozen": kit_freeze.is_frozen(str(path)),
            "has_fingerprint": kit_freeze.load_fingerprints(str(path)) is not None,
            "verify": "PASS" if ok else f"FAIL({len(problems)})",
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(kit_id: str, version: str) -> int:
    root = PACKAGES / kit_id / version
    if not root.is_dir():
        print(json.dumps({"status": "NOT_FOUND", "path": str(root)}, ensure_ascii=False))
        return 2
    ok, problems = kit_freeze.verify(str(root))
    print(json.dumps({"status": "PASS" if ok else "FAIL", "kit_id": kit_id,
                      "version": version, "problems": problems},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_freeze(kit_id: str, version: str, reason: str, force: bool) -> int:
    root = PACKAGES / kit_id / version
    if not root.is_dir():
        print(json.dumps({"status": "NOT_FOUND", "path": str(root)}, ensure_ascii=False))
        return 2
    # `manifest.status` 만으로 얼어 있는 판본은 **대장이 아직 없다.** 그 경우는
    # 「이미 동결」이 아니라 「처음 동결」이다 — 대장을 붙여 줘야 대조가 가능해진다.
    has_ledger = kit_freeze.load_fingerprints(str(root)) is not None
    if kit_freeze.is_frozen(str(root)) and has_ledger and not force:
        # 이미 얼어 있는데 다시 얼리면 **바뀐 내용으로 대장이 갱신된다** — 그 순간
        # 대조가 통과하게 되어 동결의 의미가 사라진다.
        ok, problems = kit_freeze.verify(str(root))
        print(json.dumps({
            "status": "ALREADY_FROZEN", "reason": kit_freeze.freeze_reason(str(root)),
            "verify": "PASS" if ok else "FAIL", "problems": problems,
            "hint": "대장을 다시 쓰려면 --force. 내용이 바뀌었다면 새 판본으로 내십시오.",
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    mark = kit_freeze.write_freeze(str(root), reason=reason, by=getpass.getuser())
    print(json.dumps({"status": "FROZEN", "kit_id": kit_id, "version": version,
                      **mark}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kit_id", nargs="?")
    ap.add_argument("version", nargs="?")
    ap.add_argument("--list", action="store_true", help="판본별 동결·대조 상태")
    ap.add_argument("--verify", action="store_true", help="대장과 대조만 한다")
    ap.add_argument("--reason", default="", help="왜 동결하는가")
    ap.add_argument("--force", action="store_true", help="이미 얼어 있어도 대장을 다시 쓴다")
    a = ap.parse_args()

    if a.list:
        return cmd_list()
    if not (a.kit_id and a.version):
        ap.error("kit_id 와 version 이 필요합니다 (또는 --list)")
    if a.verify:
        return cmd_verify(a.kit_id, a.version)
    return cmd_freeze(a.kit_id, a.version, a.reason, a.force)


if __name__ == "__main__":
    raise SystemExit(main())
