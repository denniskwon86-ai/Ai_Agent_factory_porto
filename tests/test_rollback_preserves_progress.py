"""★★★ 실패 롤백이 **진행 기록을 지우지 않는다.** (2026-08-26 실측)

## ⚠️⚠️ 무엇이 있었나

종결 처리의 롤백은 `git reset --hard` + `git clean -fd` 다. 목적은 「실패한 코드가 실물에
남지 않게」이고 그 자체는 옳다. 그런데 추적되지 않은 파일을 **전부** 지우면서 파이프라인
자신의 기록까지 날렸다:

    · `00_wbs_master_plan.json` — 완료 표시가 사라져 **끝난 태스크가 다시 돌았다.**
      실측에서 E2E-01 이 두 번, TASK-02 가 두 번 돌았고 그때마다 LLM 비용을 다시 썼다.
    · `contracts/` — 승인 도장과 초안이 사라졌다. 승인이 없어지니 재승인을 다시 받아야
      했고, 초안이 없어지니 「계약 대상인데 초안이 없다」로 **다른 태스크까지 영영 막혔다.**

★ 같은 판단을 이 저장소가 이미 한 번 했다 — 실패 번들을 워크스페이스 **밖**으로 옮긴
  이유가 「진단 자료는 롤백 대상이 되면 안 된다」였다. WBS·계약은 밖으로 옮길 수 없으므로
  (프로젝트의 것이다) 롤백을 넘겨 보존한다.
⚠️ 생성 **코드는 그대로 되돌린다.** 되돌리는 목적이 그것이다 — 이 시험의 대조군이다.
"""
import json
import os
import subprocess

import pytest

from nodes.utils.git_manager import GitManager


def _git(ws, *args):
    return subprocess.run(["git", *args], cwd=ws, capture_output=True, text=True)


@pytest.fixture()
def ws(tmp_path):
    """커밋이 하나 있는 워크스페이스. 그 뒤의 변경이 롤백 대상이다."""
    root = tmp_path / "ws"
    root.mkdir()
    gm = GitManager(str(root))
    (root / "README.md").write_text("base", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    return root, gm


def test_완료된_태스크_표시가_살아남는다(ws):
    """★★★ **실측: 끝난 태스크가 다시 돌았다.** 그때마다 LLM 비용을 다시 쓴다."""
    root, gm = ws
    (root / "00_wbs_master_plan.json").write_text(
        json.dumps({"tasks": [{"task_id": "T-1", "status": "DONE"},
                              {"task_id": "T-2", "status": "FAILED"}]},
                   ensure_ascii=False), encoding="utf-8")

    gm.rollback_to_safe_state()

    saved = json.loads((root / "00_wbs_master_plan.json").read_text(encoding="utf-8"))
    by = {t["task_id"]: t["status"] for t in saved["tasks"]}
    assert by == {"T-1": "DONE", "T-2": "FAILED"}, \
        "롤백이 WBS 진행 상태를 지웠다 — 끝난 태스크가 다시 돈다"


def test_계약_정본과_승인_도장이_살아남는다(ws):
    """★★★ 승인이 사라지면 **재승인을 다시 받아야 한다.** 실측에서 그렇게 됐다."""
    root, gm = ws
    (root / "contracts").mkdir()
    (root / "contracts" / "app_runtime_contract.json").write_text(
        json.dumps({"semantic_fingerprint": "a" * 64,
                    "status": "APPROVED",
                    "approval": {"status": "APPROVED"}}, ensure_ascii=False),
        encoding="utf-8")

    gm.rollback_to_safe_state()

    c = json.loads((root / "contracts" / "app_runtime_contract.json").read_text(encoding="utf-8"))
    assert c["approval"]["status"] == "APPROVED", "롤백이 승인 도장을 지웠다"


def test_계약_초안이_살아남는다(ws):
    """★★★ 초안이 사라지면 「계약 대상인데 초안이 없다」로 **다른 태스크까지 막힌다.**"""
    root, gm = ws
    d = root / "contracts" / "drafts"
    d.mkdir(parents=True)
    (d / "T-3.json").write_text('{"app_class": "departmental"}', encoding="utf-8")

    gm.rollback_to_safe_state()

    assert (d / "T-3.json").is_file(), "롤백이 계약 초안을 지웠다 — 다음 컴파일이 막힌다"


def test_템플릿_바인딩이_살아남는다(ws):
    """⚠️ `project_meta.json` 을 잃으면 이후 **모든 태스크가 'default' 템플릿으로 강등**된다.
    `start_sprint` 의 아카이빙도 같은 이유로 이 파일을 예외로 둔다."""
    root, gm = ws
    (root / "project_meta.json").write_text('{"template_id": "custom-a"}', encoding="utf-8")

    gm.rollback_to_safe_state()

    assert json.loads((root / "project_meta.json").read_text(encoding="utf-8"))["template_id"] \
        == "custom-a"


# ══════════════════════════════════════════════════════════════════════════
# 대조군 — **생성 코드는 그대로 되돌아가야 한다**
#
# ⚠️⚠️ 보존을 넓히다 보면 「아무것도 안 지우는 롤백」이 된다. 그러면 실패한 코드가 실물에
#   남고, 롤백의 목적이 사라진다.
# ══════════════════════════════════════════════════════════════════════════

def test_실패한_생성_코드는_되돌아간다(ws):
    """★★★ **대조군.** 이것까지 남기면 롤백이 아니다."""
    root, gm = ws
    src = root / "src"
    src.mkdir()
    (src / "App.tsx").write_text("깨진 코드", encoding="utf-8")

    gm.rollback_to_safe_state()

    assert not (src / "App.tsx").exists(), "실패한 생성 코드가 실물에 남았다"


def test_추적되던_파일의_수정도_되돌아간다(ws):
    """⚠️ 커밋된 파일을 실패 중에 고쳤다면 그것도 되돌아가야 한다."""
    root, gm = ws
    (root / "README.md").write_text("실패 중에 덮어씀", encoding="utf-8")

    gm.rollback_to_safe_state()

    assert (root / "README.md").read_text(encoding="utf-8") == "base"


def test_보존_목록이_코드에_적혀_있고_이유가_붙어_있다():
    """⚠️ 목록이 조용히 늘면 롤백이 무력해진다. **무엇을 왜 남기는지**가 코드에 있어야
    다음 사람이 함부로 늘리지 않는다."""
    import inspect

    src = inspect.getsource(GitManager)
    for path in GitManager.PRESERVE:
        assert path in src
    assert "진행 기록" in src, "무엇을 왜 보존하는지 적혀 있지 않다"
    #: ★ 코드(`src/`)는 보존 목록에 **없어야** 한다.
    assert "src" not in GitManager.PRESERVE
