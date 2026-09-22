# -*- coding: utf-8 -*-
"""[W03.2 보완] 조건부 저장 · 상위 링크 · 실패 소비.

Codex 검토(2026-09-22 22:32)가 지목한 셋을 잠근다.

    ① lost update   부분 파일만 막고 「낡은 판본이 새 판본을 덮는 것」을 안 막았다
    ② 상위 링크     대상과 «바로 위 부모» 만 봐서 한 칸 더 위의 junction 이 통과했다
    ③ 실패 소비     관측만 남기고 정상 반환해 호출자가 성공 흐름을 이어갔다

⚠️ 「검사를 넣었으면 대상 줄을 지워 볼 것」 — 아래 시험들은 각각 제품의 한 줄을 지우면
  실패하도록 썼다(변이로 확인했다).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import atomic_write


def _try_junction(link: Path, target: Path) -> bool:
    """Windows 는 junction 을 **별도 권한 없이** 만들 수 있다(심볼릭 링크와 다르다)."""
    try:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return True
    except Exception:
        return False


# ── ① 조건부 저장 — lost update ─────────────────────────────────────────
def test_a_stale_writer_is_refused_and_writes_nothing(tmp_path):
    """★★ 읽은 판본이 이미 바뀌었으면 **거절하고 아무것도 쓰지 않는다.**

    이것이 없으면 늦게 도착한 쓰기가 항상 이긴다 — 남이 방금 올린 새 판본이 사라진다."""
    path = tmp_path / "state.json"
    first = atomic_write.replace_json_if_unchanged(
        path, {"revision": 1}, expected_digest="", indent=2)

    #: 남이 먼저 올렸다.
    second = atomic_write.replace_json_if_unchanged(
        path, {"revision": 2}, expected_digest=first, indent=2)
    assert second != first

    #: 낡은 기준을 들고 온 writer.
    with pytest.raises(atomic_write.StaleWriteError) as caught:
        atomic_write.replace_json_if_unchanged(
            path, {"revision": 99, "who": "stale"}, expected_digest=first, indent=2)

    assert atomic_write.digest_of(path) == second, "거절했는데 파일이 바뀌었다"
    assert "revision\": 2" in path.read_text(encoding="utf-8")
    assert caught.value.expected == first and caught.value.actual == second


def test_creating_a_new_file_uses_the_empty_digest(tmp_path):
    """「아직 없음」을 `None` 이 아니라 `""` 로 둔다 — 호출자가 두 어휘를 안 갈라도 된다."""
    path = tmp_path / "new.json"
    assert atomic_write.digest_of(path) == ""
    atomic_write.replace_json_if_unchanged(path, {"a": 1}, expected_digest="", indent=2)
    assert path.exists()

    #: 이미 생긴 뒤에 「없을 것」으로 오면 거절한다 — 두 writer 가 동시에 만들 때다.
    with pytest.raises(atomic_write.StaleWriteError):
        atomic_write.replace_json_if_unchanged(path, {"a": 2}, expected_digest="", indent=2)


def test_the_lock_lives_beside_the_target_not_in_node_local_data(tmp_path):
    """★★★ **잠금 권위의 위치**가 이 보완의 핵심이다.

    `studio_project_files.operation_lock` 은 잠금 파일을 `data/studio_bootstrap_locks`
    즉 **노드 로컬**에 둔다 — 두 노드가 같은 공유 저장에 써도 서로의 잠금이 안 보인다.
    정본 옆에 둬야 같은 권위가 된다.

    ⚠️ 잠금 파일 «이름» 을 단언하지 않는다(구현 세부다). 단언하는 것은 **어느 디렉터리에
      생기는가** — 그것이 계약이다."""
    path = tmp_path / "state.json"
    seen = {}
    real_open = os.open

    def watching_open(file, flags, *args, **kwargs):
        name = str(file)
        if name.endswith(".lck"):
            seen["dir"] = os.path.dirname(name)
        return real_open(file, flags, *args, **kwargs)

    import core.atomic_write as module
    original = module.os.open
    module.os.open = watching_open
    try:
        atomic_write.replace_json_if_unchanged(path, {"a": 1}, expected_digest="", indent=2)
    finally:
        module.os.open = original

    assert seen.get("dir") == str(tmp_path), \
        f"잠금이 정본 옆에 생기지 않았다: {seen.get('dir')!r}"


def test_the_lock_file_name_is_not_longer_than_the_target(tmp_path):
    """⚠️ MAX_PATH 결함을 **잠금 파일로 다시 만들지 않는다.**

    임시 파일에서 한 번 겪었다 — 원본은 써지는데 곁다리만 못 만드는 상태."""
    path = tmp_path / "latest_state.json"
    atomic_write.replace_json_if_unchanged(path, {"a": 1}, expected_digest="", indent=2)
    strays = [p.name for p in tmp_path.iterdir() if p.name != "latest_state.json"]
    for name in strays:
        assert len(name) <= len("latest_state.json"), f"곁다리 이름이 더 길다: {name}"


# ── ② 상위 링크 ─────────────────────────────────────────────────────────
def test_a_junction_two_levels_up_is_rejected(tmp_path):
    """★★★ **대상과 부모만 보면 이 반례가 통과한다.**

    `연결된_상위/일반_하위/state.json` — 대상도 부모도 링크가 아니지만 경로가 실제로
    가리키는 곳은 남의 저장소다. 검사를 부모에서 멈추면 그대로 열린다."""
    real = tmp_path / "real_root"
    (real / "sub").mkdir(parents=True)
    linked = tmp_path / "linked_root"
    if not _try_junction(linked, real):
        pytest.skip("이 환경에서는 junction 을 만들 수 없다")

    target = linked / "sub" / "state.json"
    assert not target.parent.is_symlink(), "부모 자체는 링크가 아니어야 반례가 성립한다"

    with pytest.raises(ValueError) as caught:
        atomic_write.replace_json(target, {"a": 1}, indent=2)
    assert "연결된" in str(caught.value)
    assert not (real / "sub" / "state.json").exists(), "거절했는데 실제 위치에 썼다"


def test_a_normal_deep_path_still_writes(tmp_path):
    """⚠️ **양성 하나를 함께 본다.** 전부 거절하는 검사도 위 시험은 통과시킨다."""
    target = tmp_path / "a" / "b" / "c" / "d" / "state.json"
    atomic_write.ensure_directory(target.parent)
    atomic_write.replace_json(target, {"deep": True}, indent=2)
    assert target.exists()


def test_a_formal_mount_is_not_treated_as_a_link(tmp_path, monkeypatch):
    """★★ 볼륨 마운트 지점도 reparse point 라 `is_junction()` 이 참이다.

    그것까지 막으면 **공유 저장을 정식 mount 로 붙인 구성에서 제품이 아예 못 쓴다.**
    `os.path.ismount` 로 가른다."""
    real = tmp_path / "real_root"
    (real / "sub").mkdir(parents=True)
    linked = tmp_path / "linked_root"
    if not _try_junction(linked, real):
        pytest.skip("이 환경에서는 junction 을 만들 수 없다")

    target = linked / "sub" / "state.json"
    #: 같은 경로를 «정식 mount» 라고 답하게 만든다 — 그러면 통과해야 한다.
    monkeypatch.setattr(atomic_write.os.path, "ismount",
                        lambda p: os.path.normcase(str(p)) == os.path.normcase(str(linked)))
    atomic_write.replace_json(target, {"a": 1}, indent=2)
    assert (real / "sub" / "state.json").exists(), "정식 mount 인데 쓰지 못했다"


def test_ensure_directory_checks_before_creating(tmp_path):
    """★ `mkdir` 이 검사 밖에 있으면 그 자체가 우회로다 — 연결된 상위 아래에 디렉터리를
    만들어 놓고 나서 「대상은 링크가 아니다」로 통과한다."""
    real = tmp_path / "real_root"
    real.mkdir()
    linked = tmp_path / "linked_root"
    if not _try_junction(linked, real):
        pytest.skip("이 환경에서는 junction 을 만들 수 없다")

    with pytest.raises(ValueError):
        atomic_write.ensure_directory(linked / "새폴더")
    assert not (real / "새폴더").exists(), "거절했는데 실제 위치에 폴더를 만들었다"


def test_an_unknown_root_checks_all_the_way_up_not_just_the_parent(tmp_path):
    """⚠️ 뿌리를 **모른다고 부모에서 멈추지 않는다.** 모르는 것을 안전으로 바꾸지 않는다."""
    real = tmp_path / "real_root"
    (real / "x" / "y").mkdir(parents=True)
    linked = tmp_path / "linked_root"
    if not _try_junction(linked, real):
        pytest.skip("이 환경에서는 junction 을 만들 수 없다")
    with pytest.raises(ValueError):
        atomic_write.replace_json(linked / "x" / "y" / "state.json", {"a": 1}, indent=2)


def test_a_root_outside_the_target_widens_the_check_instead_of_refusing(tmp_path):
    """⚠️ 뿌리 밖 경로를 **거절하지 않는다** — 이 모듈은 경로 봉쇄의 권위가 아니다.

    대신 **더 넓게** 본다. 처음에 거절로 만들었더니 임의 작업공간을 쓰는 정상 호출자가
    막혔다(실측: `_save_latest_state` 시험 1건)."""
    real = tmp_path / "real_root"
    (real / "sub").mkdir(parents=True)
    linked = tmp_path / "linked_root"
    if not _try_junction(linked, real):
        pytest.skip("이 환경에서는 junction 을 만들 수 없다")

    elsewhere = tmp_path / "unrelated_root"
    elsewhere.mkdir()
    #: 뿌리가 대상과 무관하다 — 거절이 아니라 전체 조상 검사로 떨어져야 한다.
    with pytest.raises(ValueError) as caught:
        atomic_write.replace_json(linked / "sub" / "state.json", {"a": 1},
                                  indent=2, root=elsewhere)
    assert "연결된" in str(caught.value), str(caught.value)


# ── ③ 실패 소비 ─────────────────────────────────────────────────────────
def _orchestrator(monkeypatch):
    """⚠️ `pytest-asyncio` 는 격리 러너에 없다. 기존 시험처럼 `asyncio.run` 으로 부른다.

    알림은 대역으로 바꾼다 — 실패 경로가 브로드캐스터를 부르기 때문이다."""
    from core import async_orchestrator as ao

    monkeypatch.setattr(ao.factory_broadcaster, "broadcast",
                        lambda event, payload: _noop(event, payload))
    return ao.AsyncFactoryOrchestrator()


async def _noop(event, payload):
    return None


def _run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


def test_save_returns_its_outcome_so_the_caller_can_consume_it(tmp_path, monkeypatch):
    """★★ 관측만 남기고 **정상 반환하면 호출자는 저장이 된 줄 안다.**"""
    orchestrator = _orchestrator(monkeypatch)
    workspace = tmp_path / "proj_ok"
    result = _run(orchestrator._save_latest_state({"a": 1}, str(workspace)))
    assert result["saved"] is True and result["error"] == ""

    def boom(*args, **kwargs):
        raise OSError("교체 거절")

    import core.async_orchestrator as module
    original = module.atomic_write.replace_json_if_unchanged
    module.atomic_write.replace_json_if_unchanged = boom
    try:
        failed = _run(orchestrator._save_latest_state({"a": 2}, str(workspace)))
    finally:
        module.atomic_write.replace_json_if_unchanged = original
    assert failed["saved"] is False and "OSError" in failed["error"]


def test_another_projects_success_does_not_erase_this_failure(tmp_path, monkeypatch):
    """★★★ 단일 필드 하나면 **A 의 실패를 B 의 성공이 지운다.** 물어보면 「없다」고 답한다."""
    orchestrator = _orchestrator(monkeypatch)

    def boom(*args, **kwargs):
        raise OSError("교체 거절")

    import core.async_orchestrator as module
    original = module.atomic_write.replace_json_if_unchanged
    module.atomic_write.replace_json_if_unchanged = boom
    try:
        _run(orchestrator._save_latest_state({"a": 1}, str(tmp_path / "proj_A")))
    finally:
        module.atomic_write.replace_json_if_unchanged = original

    assert "proj_A" in orchestrator.state_save_failures
    _run(orchestrator._save_latest_state({"a": 1}, str(tmp_path / "proj_B")))
    assert "proj_A" in orchestrator.state_save_failures, \
        "★ 다른 프로젝트의 성공이 이 프로젝트의 실패를 지웠다"
    assert "proj_B" not in orchestrator.state_save_failures


def test_a_stale_save_is_marked_differently_from_a_replace_failure(tmp_path, monkeypatch):
    """「낡은 판본으로 덮으려다 거절」과 「교체 자체가 실패」는 **대응이 다르다.**

    앞쪽은 다시 읽고 다시 만들어야 하고, 뒤쪽은 재시도로 풀린다."""
    orchestrator = _orchestrator(monkeypatch)

    def stale(*args, **kwargs):
        raise atomic_write.StaleWriteError("p", "aaa", "bbb")

    import core.async_orchestrator as module
    original = module.atomic_write.replace_json_if_unchanged
    module.atomic_write.replace_json_if_unchanged = stale
    try:
        result = _run(orchestrator._save_latest_state({"a": 1}, str(tmp_path / "proj_S")))
    finally:
        module.atomic_write.replace_json_if_unchanged = original
    assert result["stale"] is True
    assert orchestrator.state_save_failures["proj_S"]["stale"] is True
