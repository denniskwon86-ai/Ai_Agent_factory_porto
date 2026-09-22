# -*- coding: utf-8 -*-
"""[W03.1] **두 독립 실행 주체가 같은 보관소를 읽는가.**

## 무엇이 문제였나

`projects/` 는 2026-08-05 에 저장소 루트 기준 절대경로가 됐다(`core/paths.py`). 그런데
**`library/` 만 작업 디렉터리 상대경로로 남아 있었다.** 두 저장 위치의 기준이 다르면
그 자체가 결함이다 — 실측:

    저장소 루트에서 실행   → <root>/library      (릴리스 29건)
    다른 디렉터리에서 실행 → <그곳>/library      **없다. 0건으로 보인다**

⚠️ 「목록이 비어 보인다」로 끝나지 않는다. 게시는 A 를 보고 사용여부 제어는 B 를 보므로
  **실제로 존재하는 프로그램을 끌 수 없다.** 그리고 `makedirs` 하는 경로가 엉뚱한 곳에
  빈 보관소를 새로 만들어 이후 게시물이 그쪽에 쌓인다.

## 증거로 인정하지 않는 것

⚠️ 파일 복제본·표식 디렉터리·`.afs-shared` 존재·모의 `open` 은 공유 증거가 아니다.
  여기서 쓰는 증거는 **서로 다른 cwd 에서 뜬 두 프로세스가 제품 함수로 읽은 판본과
  소유문맥이 같다**는 사실뿐이다.

⚠️ 그리고 이것은 **단일 PC 두 프로세스** 증거다. 두 호스트·공유 마운트 증거가 아니다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import library_paths
from core.paths import PROJECT_ROOT

_PROBE = os.path.join(PROJECT_ROOT, "scripts", "w03_shared_read_probe.py")


def test_library_root_is_anchored_to_the_repository_not_the_cwd():
    """★★ 보관소 뿌리는 **절대경로**이고 저장소 루트 아래여야 한다."""
    root = library_paths.library_dir()
    assert os.path.isabs(root), f"보관소 뿌리가 상대경로다: {root!r}"
    assert os.path.abspath(root).startswith(os.path.abspath(PROJECT_ROOT))


def test_changing_the_working_directory_does_not_move_the_library(tmp_path, monkeypatch):
    """⚠️ cwd 를 옮겨도 **같은 파일**을 가리켜야 한다.

    이것이 깨지면 「두 프로세스가 같은 것을 본다」는 주장이 성립할 수 없다."""
    before = library_paths.release_json("REL_X")
    monkeypatch.chdir(tmp_path)
    assert library_paths.release_json("REL_X") == before


def test_a_fresh_import_under_another_cwd_resolves_to_the_same_root(tmp_path,
                                                                    monkeypatch):
    """★★★ **새 프로세스가 보는 값**을 프로세스를 띄우지 않고 잡는다.

    두 번째 프로세스는 이 모듈을 «처음부터» import 한다. 그러니 위 `chdir` 시험만으로는
    부족하다 — 이미 import 된 값이 안 변한다는 것뿐이기 때문이다. 뿌리를 **import
    시점에 cwd 로 계산**하도록 되돌리면 그 시험은 그대로 초록인 채 새 프로세스만
    엉뚱한 곳을 본다. 그래서 다른 cwd 에서 **다시 import** 해 같은 값이 나오는지 본다.

    ⚠️ 두 «프로세스» 로 읽는 실제 증거는 `scripts/w03_shared_read_probe.py compare`
      에 있고 격리 러너 밖에서 돌린다 — 러너가 `subprocess.Popen` 을 막기 때문이다.
      그 통제를 끄고 통과시키지 않는다.

    ⚠️⚠️ **`importlib.reload` 로 하지 않는다.** 처음에 그렇게 썼다가 이 시험이 **세션을
      오염**시켰다: 단독으로는 15건 통과하던 `test_app_delivery_real_release` 가 같은
      묶음에서 4실패·9오류가 됐다. 살아 있는 제품 모듈을 시험이 다시 읽으면 그 뒤의
      모든 시험이 다른 모듈 객체·다른 전역을 보게 된다. 시험이 제품 상태를 바꾸면
      그 시험은 자기가 재는 것을 스스로 망가뜨린다.
      대신 `runpy` 로 **새 이름공간에서** 소스를 한 번 더 실행한다 — 살아 있는 모듈은
      그대로 두고, 「새로 import 하면 무슨 값이 나오는가」만 본다."""
    import runpy

    #: ⚠️ 살아 있는 모듈의 «현재 값» 과 비교하지 않는다. 격리 러너가 이 상수를 자기
    #:   실행 뿌리로 갈아끼우기 때문이다(그래서 시험이 운영 보관소에 쓰지 않는다).
    #:   ★ 그 사실이 곧 이 변경의 안전 근거이기도 하다 — 러너의 격리 지점은 cwd 가
    #:     아니라 **이 상수**이므로, 뿌리를 절대경로로 바꿔도 격리가 깨지지 않는다.
    before = library_paths.library_dir()

    monkeypatch.chdir(tmp_path)
    namespace = runpy.run_path(library_paths.__file__)
    fresh = namespace["_LIBRARY_DIR"]
    assert os.path.isabs(fresh), \
        f"다른 cwd 에서 새로 읽으니 상대경로가 나온다 — 새 프로세스는 다른 곳을 본다: {fresh!r}"
    assert fresh == os.path.join(PROJECT_ROOT, "library"), fresh
    #: 그리고 **살아 있는 모듈을 건드리지 않았다.**
    assert library_paths.library_dir() == before


def test_the_two_process_probe_exists_and_declares_its_evidence_scope():
    """⚠️ 증거 범위를 **파일이 스스로 말하게** 한다.

    단일 PC 두 프로세스 증거를 「두 호스트·공유 마운트에서 된다」로 읽으면 안 된다."""
    assert os.path.isfile(_PROBE), "두 프로세스 증거 probe 가 사라졌다"
    body = open(_PROBE, encoding="utf-8").read()
    assert "두 호스트" in body and "공유 마운트" in body, \
        "probe 가 증거 범위의 한계를 적고 있지 않다"


# ── [W03.1 보완 / 2026-09-22] 프로젝트 갈래와 접근권한 ────────────────────────
#
# 첫 제출은 릴리스 한 갈래였다. 출구는 「두 노드가 같은 **프로젝트/릴리스** 판본을 읽고
# **접근권한을 확인한다**」이므로 아래 둘이 비어 있었다.

def test_workspace_root_is_anchored_to_the_repository_not_the_cwd(tmp_path, monkeypatch):
    """프로젝트 작업공간도 저장소 기준이어야 한다 — 릴리스와 같은 조건이다.

    ⚠️ **살아 있는 `PROJECTS_DIR` 와 `PROJECT_ROOT/projects` 를 견주지 않는다.** 격리 러너가
      이 상수도 자기 실행 뿌리로 갈아끼우기 때문이다(`_LIBRARY_DIR` 과 같다). 처음에 그렇게
      썼다가 걸렸고, 그 실패가 러너의 격리 지점을 다시 확인해 줬다. 새 프로세스가 볼 값은
      `runpy` 로 — 살아 있는 모듈은 건드리지 않는다.
    """
    import runpy

    from core import paths

    live = paths.PROJECTS_DIR
    assert os.path.isabs(live), f"작업공간 뿌리가 상대경로다: {live!r}"
    assert os.path.abspath(live).startswith(os.path.abspath(PROJECT_ROOT))

    monkeypatch.chdir(tmp_path)
    fresh = runpy.run_path(paths.__file__)["PROJECTS_DIR"]
    assert os.path.isabs(fresh), f"다른 cwd 에서 새로 읽으니 상대경로다: {fresh!r}"
    assert fresh == os.path.join(PROJECT_ROOT, "projects"), fresh
    assert paths.PROJECTS_DIR == live, "시험이 살아 있는 모듈을 바꿨다"


def test_changing_the_working_directory_does_not_move_the_workspace(tmp_path, monkeypatch):
    from core.paths import workspace_path

    before = workspace_path("p1")
    monkeypatch.chdir(tmp_path)
    assert workspace_path("p1") == before, "cwd 를 바꾸자 작업공간이 따라 움직였다"


def test_access_is_decided_per_subject_not_per_node(tmp_path):
    """★ 접근권한 — 같은 자원인데 **주체에 따라 갈린다.**

    셋 다 통과하면 판정이 죽은 것이다. `AccessScope.unrestricted` 기본값이 `True` 라
    명시하지 않으면 실제로 전부 통과한다 — 그 함정을 시험이 밟아 보고 적는다.
    """
    from core import atomic_write
    from core.org_directory import AccessScope
    from core.project_visibility import ownership_visible, read_project_ownership

    workspace = tmp_path / "W03SYNTHPROJ"
    workspace.mkdir()
    atomic_write.replace_json(workspace / "project_meta.json", {
        "project_id": "W03SYNTHPROJ", "tenant_id": "t_w03", "entity_mode": "REAL",
        "enterprise_scope_id": "n_w03_scope", "owner_dept_id": "dept_w03",
        "owner_user_id": "owner@example.invalid", "visibility": "dept",
    }, indent=2)
    own = read_project_ownership(str(workspace))
    assert own.get("binding_state") == "BOUND", own

    def visible(dept, unrestricted=False, uid="reader@example.invalid"):
        scope = AccessScope(user_id=uid, unrestricted=unrestricted,
                            readable_dept_ids=frozenset([dept] if dept else []))
        return ownership_visible(scope, uid, own)

    assert visible("dept_w03") is True, "소유 부서가 못 본다"
    assert visible("dept_other") is False, "★ 다른 부서가 보인다 — 접근 판정이 죽었다"
    assert visible(None, unrestricted=True) is True, "조직 미도입 계약(unrestricted)이 깨졌다"
    #: 소유자 본인은 부서와 무관하게 본다.
    assert visible("dept_other", uid="owner@example.invalid") is True


def test_the_probe_covers_the_project_branch_and_access(tmp_path):
    """probe 가 프로젝트 갈래와 접근 판정을 **실제로 들고 있다**(첫 제출에는 없었다)."""
    body = open(_PROBE, encoding="utf-8").read()
    for token in ("read-project", "compare_projects", "ownership_visible",
                  "project_access_denies_the_outsider"):
        assert token in body, f"probe 에 {token} 이 없다 — 보완이 빠졌다"
