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


def test_a_root_that_does_not_contain_the_target_is_refused(tmp_path):
    """★★ [CR-W03-2B 정정] 뿌리 밖 경로는 **거절**한다.

    ⚠️⚠️ 앞 판에서 나는 정반대를 단언했다 — 「거절하지 않고 더 넓게 본다」. 근거는
      「거절로 만들었더니 정상 호출자가 막혔다」였는데, 검토가 짚은 대로 **임시 fixture
      한 건이 막혔다는 것이 정상 제품의 외부 경로 필요성을 증명하지 않는다.**
      독립 작업공간은 **명시적으로 검증된 다른 뿌리**로 넘기는 것이 맞고, 실제로
      `_save_latest_state` 는 그렇게 고쳤다(`_declared_root`).
      시험을 지워서 초록을 만들지 않고 **새 계약을 단언하도록** 고쳐 둔다."""
    elsewhere = tmp_path / "unrelated_root"
    elsewhere.mkdir()
    (tmp_path / "mine").mkdir()
    with pytest.raises(ValueError) as caught:
        atomic_write.replace_json(tmp_path / "mine" / "state.json", {"a": 1},
                                  indent=2, root=elsewhere)
    assert "뿌리" in str(caught.value), str(caught.value)


def test_a_junction_above_the_declared_root_is_still_caught(tmp_path):
    """★★★ [CR-W03-2B] **명시 뿌리가 그보다 위의 junction 을 숨기면 안 된다.**

    앞 판은 `root` 가 조상이면 그 위를 잘라냈다. 그래서 실제 제품 호출 형태인
    `root=junction/projects` 로 `junction/projects/proj/state.json` 을 쓰면 **예외 없이
    링크 너머에 저장**됐다. 「뿌리보다 위는 배포의 몫」이라는 주석이 곧 구멍이었다."""
    real = tmp_path / "real_root"
    (real / "projects" / "proj").mkdir(parents=True)
    linked = tmp_path / "linked_root"
    if not _try_junction(linked, real):
        pytest.skip("이 환경에서는 junction 을 만들 수 없다")

    declared = linked / "projects"          # 뿌리 «자체» 는 링크가 아니다
    target = declared / "proj" / "state.json"
    assert not declared.is_symlink(), "뿌리가 링크면 이 반례가 성립하지 않는다"

    with pytest.raises(ValueError) as caught:
        atomic_write.replace_json(target, {"a": 1}, indent=2, root=declared)
    assert "연결된" in str(caught.value), str(caught.value)
    assert not (real / "projects" / "proj" / "state.json").exists(), \
        "거절했는데 링크 너머 실제 위치에 썼다"


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


# ── [CR 판단②③] writer 의 «의미» 별 처리 ────────────────────────────────
#
# ⚠️ 앞 표는 두 곳이 틀렸다. 「릴리스 id 마다 새 디렉터리라 경쟁 없음」으로 뭉뚱그렸는데
#   실제로는 생성과 갱신이 섞여 있었다. 아래 시험이 그 구분을 고정한다.

def test_the_release_id_is_second_grained_so_collision_is_possible():
    """★★ 「새 디렉터리라 경쟁 없음」의 전제가 **성립하지 않는다**.

    `release_id` 가 초 단위라 같은 프로젝트를 같은 초에 두 번 게시하면 같은 id 다.
    전제를 시험으로 박아 두면, 누가 id 규칙을 바꿀 때 이 판단도 함께 재검토된다."""
    import re

    body = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "api", "routes", "factory_control.py"), encoding="utf-8").read()
    assert re.search(r"release_id = f\"\{project_id\}_\{datetime\.now\(\)\.strftime\('%Y%m%d_%H%M%S'\)\}\"",
                     body), "release_id 생성 규칙이 바뀌었다 — 생성/갱신 판단을 다시 보라"


def test_the_kit_app_release_id_is_deterministic_so_republish_is_an_update():
    """★★ `release_id_for` 는 결정론적이다 — 재게시는 **갱신**이지 생성이 아니다.

    이 사실 때문에 `kit_app_builder` 는 조건부 저장이어야 한다."""
    from core.kit_app_builder import release_id_for

    assert release_id_for("inst", "app") == release_id_for("inst", "app")
    assert release_id_for("inst", "app") != release_id_for("inst2", "app")


def test_exclusive_create_refuses_an_existing_canonical_file(tmp_path):
    """생성 전용 writer 의 계약 — 이미 있으면 **거절**한다. 조용히 덮지 않는다."""
    path = tmp_path / "latest_state.json"
    atomic_write.replace_json_if_unchanged(path, {"a": 1}, expected_digest="", indent=2)
    with pytest.raises(atomic_write.StaleWriteError):
        atomic_write.replace_json_if_unchanged(path, {"a": 2}, expected_digest="", indent=2)
    assert "\"a\": 1" in path.read_text(encoding="utf-8"), "거절했는데 내용이 바뀌었다"


def test_the_conditional_variant_keeps_the_same_serialization_policy(tmp_path):
    """⚠️ 조건부 갈래가 **다른 직렬화**를 쓰면 같은 값인데 digest 가 갈려 조건이 엉뚱하게
    실패한다. 두 갈래가 한 함수 안에 있으므로 여기서 고정해 둔다."""
    from core.studio_project_files import write_json

    a, b = tmp_path / "a.json", tmp_path / "b.json"
    value = {"z": 1, "a": {"y": 2, "b": 3}}
    write_json(a, value)
    write_json(b, value, expected_digest="")
    assert a.read_bytes() == b.read_bytes(), "두 갈래의 직렬화 정책이 갈렸다"


def test_the_bootstrap_binds_its_writes_to_a_prior_read():
    """★★★ [10.2-B] `studio_bootstrap` 이 **공유 정본**을 쓴다 — 이제 조건부로 쓴다.

    ⚠️ 앞서 나는 이 자리를 「열린 결함」으로 남기고 시험도 그렇게 썼다. 근거는 ①기준이
      그 조작의 앞선 읽기여야 하는데 단계 기계가 안 들고 다닌다 ②`write_json` 의 호출
      모양을 바꾸면 실패 주입 대역이 깨진다 였는데, 검토가 짚은 대로 **대역이 안 맞는
      것은 제품을 되돌릴 이유가 아니었다.** 읽기가 내용과 지문을 함께 돌려주게 하고
      (`read_json_with_digest`), 대역은 인자를 전달하도록 함께 고쳤다.

    여기서 고정하는 것은 **「읽은 판본을 그 쓰기에 넘긴다」** 는 사실이다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    body = open(os.path.join(root, "core", "studio_bootstrap.py"), encoding="utf-8").read()
    assert "read_json_with_digest" in body, "bootstrap 이 읽은 판본을 기준으로 삼지 않는다"
    assert body.count("expected_digest=") >= 2,         "초기 기록과 READY 갱신 둘 다 기준을 넘겨야 한다"
    assert "operation_lock" in body


def test_a_read_returns_content_and_digest_from_the_same_bytes(tmp_path):
    """★★ 따로 읽으면 그 사이가 창이다 — 「내가 읽은 것」이 남이 바꾼 뒤의 지문이 된다."""
    from core.studio_project_files import read_json_with_digest, write_json

    path = tmp_path / "latest_state.json"
    assert read_json_with_digest(path) == (None, "")
    write_json(path, {"a": 1})
    value, digest = read_json_with_digest(path)
    assert value == {"a": 1} and digest == atomic_write.digest_of(path)
