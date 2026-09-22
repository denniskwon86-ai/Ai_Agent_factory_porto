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

# ── [W03.1 보완 / 2026-09-22] 프로젝트 갈래와 접근권한 ────────────────────────
#
# 첫 제출은 **릴리스 한 갈래**였다. 출구는 「두 노드가 같은 **프로젝트/릴리스** 판본을 읽고
# **접근권한을 확인한다**」이므로 두 가지가 비어 있었다 — 프로젝트측, 그리고 권한 판정.
#
# ⚠️ 권한 판정도 **자식 프로세스 안에서** 한다. 부모가 대신 판정하면 「그 노드가 그렇게
#   판정한다」가 아니라 「내가 그렇게 계산했다」가 된다.

PROJECT_ID = "W03SYNTHPROJ_20260922_000001"
#: 프로젝트 정본. `latest_state.json` 은 상태, `project_meta.json` 은 소유권이다.
PROJECT_STATE = {
    "project_id": PROJECT_ID,
    "project_name": "W03 합성 프로젝트",
    "template_id": "w03_probe_template",
    "initial_idea": "공유 읽기 증거용 합성 자료",
}
PROJECT_META = {
    "project_id": PROJECT_ID,
    "tenant_id": "t_w03",
    "entity_mode": "REAL",
    "enterprise_scope_id": "n_w03_scope",
    "owner_dept_id": "dept_w03",
    "owner_user_id": "w03-probe@example.invalid",
    "visibility": "dept",
}
PROJECT_OWNERSHIP_FIELDS = ("tenant_id", "entity_mode", "enterprise_scope_id",
                            "owner_dept_id", "owner_user_id", "visibility")

#: 접근권한을 물어볼 주체 셋. **하나는 거절돼야 한다** — 전원 통과면 판정이 죽은 것이다.
#: `unrestricted` 기본값이 `True` 라 명시하지 않으면 전부 통과한다(AccessScope 계약).
SUBJECTS = {
    "owner_dept":  {"user_id": "someone-else@example.invalid",
                    "readable_dept_ids": ["dept_w03"], "unrestricted": False, "expect": True},
    "other_dept":  {"user_id": "outsider@example.invalid",
                    "readable_dept_ids": ["dept_other"], "unrestricted": False, "expect": False},
    "unrestricted": {"user_id": "legacy@example.invalid",
                     "readable_dept_ids": [], "unrestricted": True, "expect": True},
}


def seed_project(projects_root: str) -> str:
    """합성 프로젝트 한 판을 격리 작업공간에 만든다. 운영 `projects/` 는 건드리지 않는다."""
    from core import atomic_write

    folder = os.path.join(projects_root, PROJECT_ID)
    os.makedirs(folder, exist_ok=True)
    atomic_write.replace_json(os.path.join(folder, "latest_state.json"), PROJECT_STATE, indent=2)
    atomic_write.replace_json(os.path.join(folder, "project_meta.json"), PROJECT_META, indent=2)
    return folder


def read_project_through_product(projects_root: str) -> dict:
    """★ 제품 경로로 프로젝트를 읽고, **그 자리에서 접근권한까지 판정**한다.

    경로 격리 지점은 `core.paths.PROJECTS_DIR` 하나다 — `workspace_path()` 가 호출 시점에
    그 값을 읽으므로(`core/paths.py` 의 격리 주석), 여기서 그 지점만 정하면 나머지는 제품이
    정한다. 이 파일이 경로를 다시 조립하면 제품이 아닌 것을 재게 된다.
    """
    from core import paths
    paths.PROJECTS_DIR = projects_root

    from core.org_directory import AccessScope
    from core.paths import workspace_path
    from core.project_visibility import ownership_visible, read_project_ownership
    from core.studio_project_files import read_json

    workspace = workspace_path(PROJECT_ID)
    out = {
        "cwd": os.getcwd(),
        "projects_root_as_given": projects_root,
        "resolved_workspace": workspace,
        "found": os.path.exists(os.path.join(workspace, "latest_state.json")),
    }
    if not out["found"]:
        out.update({"digest": "", "ownership": {}, "access": {}})
        return out

    state = read_json(os.path.join(workspace, "latest_state.json"))
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")
    out["digest"] = hashlib.sha256(raw).hexdigest()

    own = read_project_ownership(workspace)
    out["ownership"] = {k: own.get(k) for k in PROJECT_OWNERSHIP_FIELDS}
    out["binding_state"] = own.get("binding_state")
    #: ⚠️ 판정은 **이 프로세스가** 제품 함수로 한다. 부모가 대신 계산하지 않는다.
    out["access"] = {
        name: bool(ownership_visible(
            AccessScope(user_id=spec["user_id"], unrestricted=spec["unrestricted"],
                        readable_dept_ids=frozenset(spec["readable_dept_ids"])),
            spec["user_id"], own))
        for name, spec in SUBJECTS.items()
    }
    return out


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


def _spawn_project(cwd: str, projects_root: str) -> dict:
    """프로젝트 갈래의 자식 하나. 릴리스와 같은 방식으로 **cwd 를 달리** 한다."""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", os.path.abspath(__file__),
         "read-project", "--projects-root", projects_root],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    if result.returncode != 0:
        return {"error": (result.stderr or "").strip()[-400:], "cwd": cwd}
    return json.loads(result.stdout)


def compare_projects(projects_root: str, other_cwd: str, relative: bool) -> dict:
    """프로젝트 정본을 두 프로세스가 같게 읽고 **같게 판정하는가.**"""
    given = os.path.basename(projects_root) if relative else projects_root
    a = _spawn_project(os.path.dirname(projects_root), given)
    b = _spawn_project(other_cwd, given)
    same = (a.get("found") and b.get("found")
            and a.get("digest") == b.get("digest")
            and a.get("ownership") == b.get("ownership"))
    #: ★ 판본이 같아도 **권한 판정이 갈리면** 한쪽 노드에서만 열리는 자원이 된다.
    same_access = bool(a.get("found") and b.get("found") and a.get("access") == b.get("access"))
    expected = {name: spec["expect"] for name, spec in SUBJECTS.items()}
    return {
        "mode": "작업디렉터리 상대(옛 해석)" if relative else "저장소 기준 절대경로",
        "process_a": a, "process_b": b,
        "both_found": bool(a.get("found") and b.get("found")),
        "same_revision_and_ownership": bool(same),
        "same_access_decisions": same_access,
        "access_matches_expectation": a.get("access") == expected if a.get("found") else False,
        "expected_access": expected,
    }


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
    rp = sub.add_parser("read-project", help="자식 프로세스 — 프로젝트를 읽고 권한까지 판정")
    rp.add_argument("--projects-root", required=True)
    c = sub.add_parser("compare", help="두 프로세스를 다른 cwd 로 띄워 대조")
    c.add_argument("--root", default="", help="격리 보관소(없으면 임시로 만든다)")
    args = ap.parse_args(argv)

    if args.cmd == "read":
        print(json.dumps(read_through_product(args.library_root),
                         ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "read-project":
        print(json.dumps(read_project_through_product(args.projects_root),
                         ensure_ascii=False, indent=2))
        return 0

    root = args.root or tempfile.mkdtemp(prefix="w03_library_")
    library_root = os.path.join(root, "library")
    seed(library_root)
    other = tempfile.mkdtemp(prefix="w03_elsewhere_")
    projects_root = os.path.join(root, "projects")
    seed_project(projects_root)
    release = {
        "absolute": compare(library_root, other, relative=False),
        #: ★ 음성 대조군 — 옛 해석에서는 갈라져야 한다.
        "relative_control": compare(library_root, other, relative=True),
    }
    project = {
        "absolute": compare_projects(projects_root, other, relative=False),
        "relative_control": compare_projects(projects_root, other, relative=True),
    }
    result = {
        "seeded_release": RELEASE_ID,
        "seeded_project": PROJECT_ID,
        "isolated_library_root": library_root,
        "isolated_projects_root": projects_root,
        "second_process_cwd": other,
        "release": release,
        "project": project,
        "verdict": {
            "release_shared": release["absolute"]["same_revision_and_ownership"],
            "release_control_splits": not release["relative_control"]["same_revision_and_ownership"],
            "project_shared": project["absolute"]["same_revision_and_ownership"],
            "project_control_splits": not project["relative_control"]["same_revision_and_ownership"],
            #: 두 노드가 **같은 판정**을 내리고, 그 판정이 **기대와 같다**(하나는 거절).
            "project_access_agrees_across_nodes": project["absolute"]["same_access_decisions"],
            "project_access_denies_the_outsider": project["absolute"]["access_matches_expectation"],
        },
        #: 뒤로 호환 — 첫 제출이 이 두 키를 썼다. 릴리스 갈래를 그대로 둔다.
        "absolute": release["absolute"],
        "relative_control": release["relative_control"],
        "evidence_scope": "단일 PC 두 프로세스. 두 호스트·공유 마운트 증거가 아니다.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(result["verdict"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
