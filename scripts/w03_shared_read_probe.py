# -*- coding: utf-8 -*-
"""[W03.1] **두 독립 프로세스가 같은 저장 위치를 읽는가.**

## 무엇을 증거로 삼는가

⚠️⚠️ 파일 복제본·표식 디렉터리·`.afs-shared` 같은 파일의 «존재» 는 공유 증거가 아니다.
  모의 `open` 도 아니다. 여기서 증거로 쓰는 것은 **서로 다른 작업 디렉터리에서 뜬 두
  프로세스가 제품 함수로 읽은 «판본과 소유문맥» 이 같다**는 사실뿐이다.

## 왜 두 «프로세스» 인가

같은 프로세스에서 경로만 바꿔 두 번 읽으면, 그것은 같은 해석기·같은 모듈 상태를
공유한 결과다. 배포에서 실제로 갈라지는 것은 **작업 디렉터리** 이고, 그것은 프로세스
경계에서만 제대로 재연된다.

## 음성 대조군을 함께 돌린다

★★ 「둘이 같았다」만으로는 아무것도 증명되지 않는다 — 고치기 전에도 **저장소 루트에서
  둘 다 띄우면** 같았다. 그래서 같은 harness 로 **옛 해석(작업 디렉터리 상대)** 을
  재연해 **갈라지는 것**을 함께 보인다. 갈라지지 않으면 이 시험이 경로 의존을 재연하지
  못한 것이지 제품이 증명된 것이 아니다.

## 경계

⚠️ 운영 `library/`·`projects/` 를 읽지도 쓰지도 않는다. 합성 릴리스 한 판을 격리
  경로에 만들고 그것만 본다.
⚠️ 단일 PC 두 프로세스 증거다. **두 호스트·공유 마운트 증거가 아니다** — 그 구분을
  결과에 그대로 적는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: 합성 릴리스. 실제 계정·실제 조직을 쓰지 않는다.
RELEASE_ID = "W03SYNTH_20260922_000001"
SYNTH = {
    "release_id": RELEASE_ID,
    "app_id": "w03_probe_app",
    "tenant_id": "t_w03",
    "entity_mode": "REAL",
    "enterprise_scope_id": "n_w03_scope",
    "owner_dept_id": "dept_w03",
    "created_by": "w03-probe@example.invalid",
    "created_at": "2026-09-22T00:00:00+00:00",
    "project_id": RELEASE_ID,
}
#: 「소유문맥」으로 대조할 필드. 판본 하나가 아니라 **누구의 것인가** 까지 본다.
OWNERSHIP_FIELDS = ("tenant_id", "entity_mode", "enterprise_scope_id",
                    "owner_dept_id", "created_by", "project_id")


def seed(library_root: str) -> str:
    """합성 릴리스 한 판을 격리 보관소에 만든다."""
    folder = os.path.join(library_root, RELEASE_ID)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "release.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(SYNTH, handle, ensure_ascii=False, indent=2)
    return path


def read_through_product(library_root: str) -> dict:
    """★ **제품 함수로** 읽는다. 이 파일이 경로를 다시 조립하면 제품이 아닌 것을 잰다.

    `library_paths._LIBRARY_DIR` 은 그 모듈이 **배포에서 보관소를 정하는 지점**이고,
    소비자는 값을 복사하지 않고 호출 시점에 읽는다. 그래서 여기서 그 지점만 정하고
    읽기는 전부 제품 경로로 흐른다."""
    from core import library_paths
    library_paths._LIBRARY_DIR = library_root

    from core.app_delivery import _default_release_lookup
    from core.program_lifecycle import program_lifecycle

    resolved = library_paths.release_json(RELEASE_ID)
    payload = _default_release_lookup(RELEASE_ID)
    out = {
        "cwd": os.getcwd(),
        "library_root_as_given": library_root,
        "resolved_release_json": resolved,
        "product_says_exists": bool(program_lifecycle._release_exists(RELEASE_ID)),
        "found": payload is not None,
    }
    if payload is None:
        out["digest"] = ""
        out["ownership"] = {}
        return out
    #: 판본 동일성은 **내용 digest** 로 본다. 경로 문자열이 같은지를 묻는 것이 아니다.
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    out["digest"] = hashlib.sha256(raw).hexdigest()
    out["ownership"] = {k: payload.get(k) for k in OWNERSHIP_FIELDS}
    return out


def _spawn(cwd: str, library_root: str) -> dict:
    """자식 프로세스 하나. **작업 디렉터리를 달리** 해서 띄운다."""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", os.path.abspath(__file__),
         "read", "--library-root", library_root],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    if result.returncode != 0:
        return {"error": (result.stderr or "").strip()[-400:], "cwd": cwd}
    return json.loads(result.stdout)


def compare(library_root: str, other_cwd: str, relative: bool) -> dict:
    """두 프로세스를 **다른 cwd** 로 띄우고 읽은 것을 맞춰 본다.

    `relative=True` 면 옛 해석(작업 디렉터리 상대)을 재연한다 — 음성 대조군이다."""
    given = os.path.basename(library_root) if relative else library_root
    #: ★ A 는 보관소를 «품고 있는» 디렉터리에서, B 는 전혀 다른 곳에서 띄운다.
    #:   옛 해석에서는 A 만 찾고 B 는 못 찾아야 한다 — 그 차이가 음성 대조군이다.
    a = _spawn(os.path.dirname(library_root), given)
    b = _spawn(other_cwd, given)
    same = (a.get("found") and b.get("found")
            and a.get("digest") == b.get("digest")
            and a.get("ownership") == b.get("ownership"))
    return {
        "mode": "작업디렉터리 상대(옛 해석)" if relative else "저장소 기준 절대경로",
        "process_a": a, "process_b": b,
        "both_found": bool(a.get("found") and b.get("found")),
        "same_revision_and_ownership": bool(same),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W03.1 공유 읽기 증거")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read", help="자식 프로세스 — 제품 경로로 한 번 읽는다")
    r.add_argument("--library-root", required=True)
    c = sub.add_parser("compare", help="두 프로세스를 다른 cwd 로 띄워 대조")
    c.add_argument("--root", default="", help="격리 보관소(없으면 임시로 만든다)")
    args = ap.parse_args(argv)

    if args.cmd == "read":
        print(json.dumps(read_through_product(args.library_root),
                         ensure_ascii=False, indent=2))
        return 0

    root = args.root or tempfile.mkdtemp(prefix="w03_library_")
    library_root = os.path.join(root, "library")
    seed(library_root)
    other = tempfile.mkdtemp(prefix="w03_elsewhere_")
    result = {
        "seeded_release": RELEASE_ID,
        "isolated_library_root": library_root,
        "second_process_cwd": other,
        "absolute": compare(library_root, other, relative=False),
        #: ★ 음성 대조군 — 옛 해석에서는 갈라져야 한다.
        "relative_control": compare(library_root, other, relative=True),
        "evidence_scope": "단일 PC 두 프로세스. 두 호스트·공유 마운트 증거가 아니다.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = (result["absolute"]["same_revision_and_ownership"]
          and not result["relative_control"]["same_revision_and_ownership"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
