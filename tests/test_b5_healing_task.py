"""B5 healing WBS helper 회귀. 기존 tmp 격리 사용, 실행·수집은 main 전용.

실제 FileLock/원자 파일 교체를 검증하며 명령 API·실행·HEAL 예산 검증과 구분한다.
링크 차단 사례는 Path 판독 대역이며 실제 junction을 만들지 않는다.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from tests.test_b3_studio_drafts import isolated_stores  # noqa: F401


KEY = "b5000000-0000-4000-8000-000000000001"
TASK = "TASK-01"
ERROR = "  합성 오류 원문\n결과를 보존하세요.  "


@pytest.fixture
def healing(tmp_path, isolated_stores):
    from core import studio_healing_task as module
    from nodes.utils.wbs_manager import WBSManager
    root = tmp_path / "healing-workspace"
    manager = WBSManager(str(root))
    manager.initialize_wbs("합성 복구", [{"task_id": TASK, "title": "원 작업", "goal": "원본 보존",
        "status": "DONE", "artifact_kind": "APP", "required_agents": ["Backend"]}], runtime_contract_profile="v1")
    artifact = root / "result.txt"
    artifact.write_text("원래 산출물", encoding="utf-8")
    return SimpleNamespace(module=module, root=root, wbs=root / "00_wbs_master_plan.json", artifact=artifact)


def append(env, **changes):
    return env.module.append_healing_task(env.root, **{**dict(request_id=KEY, source_task_id=TASK, error_log=ERROR), **changes})


def document(env):
    return json.loads(env.wbs.read_text(encoding="utf-8"))


def reject(env, call, status, reason):
    with pytest.raises(env.module.HealingTaskError) as exc:
        call()
    assert exc.value.status_code == status and exc.value.reason_code == "STUDIO_HEAL_" + reason


@pytest.mark.parametrize("profile", ["v1", ""])
def test_deterministic_append_preserves_source_and_existing_contract_profile(healing, profile):
    env = healing
    doc = document(env)
    doc["runtime_contract_profile"] = profile
    env.wbs.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    source, artifact = copy.deepcopy(doc["tasks"]), env.artifact.read_bytes()
    task_id = append(env)
    assert task_id == "TASK_REV_HEAL_" + KEY.replace("-", "")
    actual = document(env)
    assert actual["total_tasks"] == 2 and actual["tasks"][:-1] == source
    task = actual["tasks"][-1]
    assert task["status"] == "TODO" and task["required_agents"] == ["Tech_Lead", "Backend", "Frontend"]
    assert task["studio_execution_request_id"] == KEY and task["source_task_id"] == TASK
    assert ERROR in task["goal"] and not any(name.startswith("studio_revision_") for name in task)
    assert (task.get("artifact_kind"), task.get("artifact_kind_source")) == (("APP", "declared") if profile else (None, None))
    assert env.artifact.read_bytes() == artifact
    env.module.strict.read_wbs_strict(env.wbs)  # 기존 수정요청 strict reader와 공존한다.


def test_same_key_exact_body_retry_does_not_rewrite_or_reset_completed_task(healing):
    env = healing
    task_id = append(env)
    doc = document(env)
    doc["tasks"][-1].update(status="DONE", completed_agents=["Backend"], execution_note="진행 상태")
    env.wbs.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    before = env.wbs.read_bytes()
    assert append(env, request_id=KEY.upper()) == task_id
    assert env.wbs.read_bytes() == before


@pytest.mark.parametrize("changes", [{"error_log": "다른 오류"}, {"source_task_id": "TASK-02"}])
def test_same_request_key_different_body_is_409_without_append(healing, changes):
    env = healing
    append(env)
    before = env.wbs.read_bytes()
    reject(env, lambda: append(env, **changes), 409, "IDEMPOTENCY_CONFLICT")
    assert env.wbs.read_bytes() == before


@pytest.mark.parametrize("damage", ["goal", "fingerprint", "binding", "agents", "duplicate_binding", "duplicate_binding_case"])
def test_tampered_healing_task_is_not_repaired_or_returned_as_success(healing, damage):
    env = healing
    append(env)
    doc = document(env)
    task = doc["tasks"][-1]
    if damage == "goal":
        task["goal"] = "변조된 원문"
    elif damage == "fingerprint":
        task.pop("studio_execution_command_digest")
    elif damage == "binding":
        task["studio_execution_request_id"] = "other"
    elif damage == "agents":
        task["required_agents"] = ["Frontend"]
    else:
        doc["tasks"].append({**copy.deepcopy(task), "task_id": "TASK-OTHER"})
        if damage == "duplicate_binding_case":
            doc["tasks"][-1]["studio_execution_request_id"] = KEY.upper()
        doc["total_tasks"] += 1
    env.wbs.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    before = env.wbs.read_bytes()
    reject(env, lambda: append(env), 503, "INTEGRITY")
    assert env.wbs.read_bytes() == before


@pytest.mark.parametrize("raw", ["{", '{"tasks":{}}', '{"tasks":[{"task_id":"A"},{"task_id":"A"}]}',
                                '{"tasks":[],"runtime_contract_profile":"unknown"}'])
def test_corrupt_wbs_is_503_without_empty_recovery(healing, raw):
    env = healing
    env.wbs.write_text(raw, encoding="utf-8")
    before = env.wbs.read_bytes()
    reject(env, lambda: append(env), 503, "WBS_UNAVAILABLE")
    assert env.wbs.read_bytes() == before


@pytest.mark.parametrize("missing", ["file", "empty", "source", "workspace"])
def test_missing_wbs_or_source_is_not_silently_initialized(healing, missing):
    env = healing
    if missing == "file":
        env.wbs.unlink()  # 이 시험이 만든 tmp WBS만 제거한다.
    elif missing == "empty":
        env.wbs.write_text('{"tasks":[],"total_tasks":0}', encoding="utf-8")
    elif missing == "workspace":
        absent = env.root / "never-created"
        reject(env, lambda: env.module.append_healing_task(absent, request_id=KEY, source_task_id=TASK, error_log=ERROR),
               409, "WBS_REQUIRED")
        assert not absent.exists()
        return
    before = env.wbs.read_bytes() if env.wbs.exists() else None
    reject(env, lambda: append(env, source_task_id="UNKNOWN_TASK" if missing == "source" else TASK),
           409, "TARGET_CONFLICT" if missing == "source" else "WBS_REQUIRED")
    assert (env.wbs.read_bytes() if env.wbs.exists() else None) == before


def test_sprint_init_fallback_uses_existing_nonempty_wbs(healing):
    env = healing
    task_id = append(env, source_task_id="sprint_init")
    assert document(env)["tasks"][-1]["task_id"] == task_id
    assert document(env)["tasks"][-1]["source_task_id"] == "sprint_init"


@pytest.mark.parametrize("changes", [{"request_id": "bad"}, {"source_task_id": "../outside"},
                                      {"error_log": " \n "}, {"error_log": None}, {"error_log": "가" * 24000}])
def test_invalid_or_oversized_request_preserves_wbs(healing, changes):
    env = healing
    before = env.wbs.read_bytes()
    reject(env, lambda: append(env, **changes), 422, "INVALID")
    assert env.wbs.read_bytes() == before


@pytest.mark.parametrize("same_key", [True, False])
def test_actual_filelock_prevents_duplicate_ids_and_lost_concurrent_appends(healing, same_key):
    env = healing
    source = document(env)["tasks"][0]
    barrier = threading.Barrier(4)
    def write(number):
        barrier.wait(timeout=5)
        key = KEY if same_key else f"b5000000-0000-4000-8000-{number:012d}"
        return append(env, request_id=key)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(write, number) for number in range(1, 5)]
        ids = [future.result(timeout=15) for future in futures]
    doc = document(env)
    assert len(set(ids)) == (1 if same_key else 4)
    assert len(doc["tasks"]) == doc["total_tasks"] == (2 if same_key else 5)
    assert len({task["task_id"] for task in doc["tasks"]}) == len(doc["tasks"])
    assert doc["tasks"][0] == source


@pytest.mark.parametrize("after", [False, True])
def test_atomic_replace_failure_preserves_original_or_recovers_existing_id(healing, monkeypatch, after):
    env = healing
    before = env.wbs.read_bytes()
    original = os.replace
    writes = []
    def failed(source, destination):
        if Path(destination) != env.wbs:
            return original(source, destination)
        writes.append(True)
        if after:
            original(source, destination)
        raise OSError("합성 원자 교체 응답 실패")
    monkeypatch.setattr(os, "replace", failed)
    reject(env, lambda: append(env), 503, "WBS_UNAVAILABLE")
    assert writes == [True]
    if after:
        recorded = env.wbs.read_bytes()
        assert append(env) == document(env)["tasks"][-1]["task_id"]
        assert env.wbs.read_bytes() == recorded and writes == [True]
    else:
        assert env.wbs.read_bytes() == before
    assert not list(env.root.glob(".healing-task-*.tmp"))


def test_external_wbs_change_before_replace_is_not_overwritten(healing, monkeypatch):
    env = healing
    original = env.module.strict.read_wbs_strict
    calls, preserved = [], []
    def raced(path):
        calls.append(True)
        if len(calls) == 2:
            doc = document(env)
            doc["tasks"][0]["goal"] = "외부의 새 원문"
            env.wbs.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            preserved.append(env.wbs.read_bytes())
        return original(path)
    monkeypatch.setattr(env.module.strict, "read_wbs_strict", raced)
    reject(env, lambda: append(env), 409, "CONFLICT")
    assert len(preserved) == 1 and env.wbs.read_bytes() == preserved[0]
    assert not list(env.root.glob(".healing-task-*.tmp"))


def test_fsync_failure_does_not_publish_partial_wbs(healing, monkeypatch):
    env = healing
    before = env.wbs.read_bytes()
    def failed(_fd):
        raise OSError("합성 flush 실패")
    monkeypatch.setattr(os, "fsync", failed)
    reject(env, lambda: append(env), 503, "WBS_UNAVAILABLE")
    assert env.wbs.read_bytes() == before and not list(env.root.glob(".healing-task-*.tmp"))


def test_wbs_capacity_rejection_does_not_rewrite_original(healing, monkeypatch):
    env = healing
    before = env.wbs.read_bytes()
    monkeypatch.setattr(env.module.strict, "MAX_WBS_BYTES", len(before) + 8)
    reject(env, lambda: append(env), 409, "CAPACITY")
    assert env.wbs.read_bytes() == before


def test_filelock_timeout_is_explicit_conflict_without_write(healing, monkeypatch):
    env = healing
    before = env.wbs.read_bytes()
    class Busy:
        def __init__(self, path):
            assert Path(path) == Path(str(env.wbs) + ".lock")
        def acquire(self, timeout):
            assert timeout == 10
            raise env.module.Timeout(str(env.wbs) + ".lock")
    monkeypatch.setattr(env.module, "FileLock", Busy)
    reject(env, lambda: append(env), 409, "BUSY")
    assert env.wbs.read_bytes() == before


@pytest.mark.parametrize("linked", ["workspace", "wbs", "lock"])
def test_linked_path_is_refused_before_append(healing, monkeypatch, linked):
    env = healing
    target = {"workspace": env.root, "wbs": env.wbs, "lock": Path(str(env.wbs) + ".lock")}[linked]
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == target or original(path))
    before = env.wbs.read_bytes()
    reject(env, lambda: append(env), 503, "WBS_UNAVAILABLE")
    assert env.wbs.read_bytes() == before
