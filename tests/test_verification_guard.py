"""별도 audit 객체에 이벤트를 입력한다. 실제 외부 파일/DB에는 접근하지 않는다."""
import os
from pathlib import Path

import pytest

from scripts.verification_isolation import VerificationIsolation, VerificationTiming


@pytest.fixture
def boundary(tmp_path):
    run = tmp_path / "worker-one"
    run.mkdir()
    return VerificationIsolation(run, strict=True), tmp_path


@pytest.mark.parametrize("relative", ["../worker-two/db.sqlite", "../original.sqlite"])
def test_sqlite_rejects_other_worker_and_original(boundary, relative):
    guard, _ = boundary
    with pytest.raises(PermissionError):
        guard("sqlite3.connect", (str(guard.run_root / relative),))
    assert len(guard.blocked_sqlite_paths) == 1


@pytest.mark.parametrize("raw", ["file:inside.db?mode=ro", ":memory:"])
def test_sqlite_uri_and_memory_stay_prohibited(boundary, raw):
    guard, _ = boundary
    with pytest.raises(PermissionError):
        guard("sqlite3.connect", (raw,))


def test_own_database_and_write_allowed(boundary):
    guard, _ = boundary
    path = str(guard.run_root / "own.sqlite")
    guard("sqlite3.connect", (path,))
    guard("open", (path, "w", os.O_WRONLY | os.O_CREAT))
    assert guard.sqlite_paths == guard.write_paths == {path}
    assert not guard.blocked_file_writes


def test_canonical_own_readonly_uri_is_allowed_and_sqlite_cannot_write(boundary):
    import sqlite3
    guard, _ = boundary
    path = guard.run_root / "own space.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE example(value TEXT)")
    raw = path.as_uri() + "?mode=ro"
    guard("sqlite3.connect", (raw,))
    with sqlite3.connect(raw, uri=True) as conn:
        assert conn.execute("SELECT * FROM example").fetchall() == []
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO example VALUES('blocked')")
    assert guard.sqlite_paths == {str(path)}
    assert not guard.blocked_sqlite_paths


@pytest.mark.parametrize("query", ["", "?mode=rw", "?mode=rwc", "?mode=memory", "?mode=ro&vfs=unix-dotfile", "?mode=ro&immutable=1", "?mode=ro#fragment"])
def test_uri_cannot_select_write_vfs_memory_or_extra_options(boundary, query):
    guard, _ = boundary
    path = guard.run_root / "existing.sqlite"
    path.touch()
    with pytest.raises(PermissionError):
        guard("sqlite3.connect", (path.as_uri() + query,))


def test_readonly_uri_rejects_other_run_missing_file_and_noncanonical_path(boundary):
    guard, parent = boundary
    external = parent / "other.sqlite"
    external.touch()
    own = guard.run_root / "own.sqlite"
    own.touch()
    for raw in (external.as_uri() + "?mode=ro", (guard.run_root / "missing.sqlite").as_uri() + "?mode=ro",
                guard.run_root.as_uri() + "/../worker-one/own.sqlite?mode=ro"):
        with pytest.raises(PermissionError):
            guard("sqlite3.connect", (raw,))


def test_readonly_uri_cannot_hide_resolved_link_outside_run(boundary, monkeypatch):
    guard, parent = boundary
    own, external = guard.run_root / "link.sqlite", parent / "outside.sqlite"
    external.touch()
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **k: external if p == own else original(p, *a, **k))
    with pytest.raises(PermissionError):
        guard("sqlite3.connect", (own.as_uri() + "?mode=ro",))


@pytest.mark.parametrize("event", ["open", "os.mkdir", "os.remove", "os.rename", "os.link"])
def test_all_file_writes_reject_sibling_run(boundary, event):
    guard, parent = boundary
    external = str(parent / "worker-two" / "payload")
    own = str(guard.run_root / "payload")
    args = {"open": (external, "w", os.O_WRONLY), "os.mkdir": (external, 511, -1),
            "os.remove": (external, -1), "os.rename": (own, external, -1, -1),
            "os.link": (external, own, -1, -1)}[event]
    with pytest.raises(PermissionError):
        guard(event, args)
    assert guard.blocked_file_writes


def test_relative_dir_fd_cannot_escape(boundary):
    guard, _ = boundary
    with pytest.raises(PermissionError):
        guard("os.mkdir", (str(guard.run_root / "safe-looking"), 511, 42))


@pytest.mark.parametrize("event", ["subprocess.Popen", "os.system", "os.posix_spawn", "os.startfile", "os.startfile/2"])
def test_no_worker_subprocess(boundary, event):
    guard, _ = boundary
    with pytest.raises(PermissionError):
        guard(event, ("never-executed",))


def test_only_final_report_path_may_be_exported_after_tests(boundary):
    guard, parent = boundary
    target = parent / "result.json"
    with pytest.raises(PermissionError):
        guard("open", (str(target), "x", os.O_WRONLY | os.O_CREAT | os.O_EXCL))
    guard.final_report = target.resolve()
    guard("open", (str(target), "x", os.O_WRONLY | os.O_CREAT | os.O_EXCL))
    with pytest.raises(PermissionError):
        guard("open", (str(parent / "other.json"), "w", os.O_WRONLY))


def test_relative_write_open_cannot_hide_external_dir_fd(boundary, monkeypatch):
    guard, _ = boundary
    monkeypatch.chdir(guard.run_root)
    with pytest.raises(PermissionError):
        guard("open", ("looks-local.txt", None, os.O_WRONLY | os.O_CREAT))
    assert guard.blocked_file_writes[-1]["event"] == "open"
    guard("open", ("read-only-relative.txt", "r", os.O_RDONLY))


def test_symlink_relative_dir_fd_is_not_approved(boundary):
    guard, _ = boundary
    with pytest.raises(PermissionError):
        guard("os.symlink", (str(guard.run_root / "target"), str(guard.run_root / "link"), 42))


def test_resolved_link_target_is_not_approved(boundary, monkeypatch):
    guard, parent = boundary
    own, external = guard.run_root / "link", parent / "outside"
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **k: external if p == own else original(p, *a, **k))
    with pytest.raises(PermissionError):
        guard("open", (str(own), "w", os.O_WRONLY))


@pytest.mark.skipif(os.name != "nt", reason="Windows 확장 drive 경로")
def test_extended_own_run_lock_path_uses_normal_boundary(boundary):
    guard, _ = boundary
    own = guard.run_root / "00_wbs_master_plan.json.lock"
    extended = "\\\\?\\" + str(own)
    guard("open", (extended, None, os.O_RDWR | os.O_CREAT))
    guard("os.remove", (extended, -1))
    assert guard.write_paths == {str(own)} and not guard.blocked_file_writes


@pytest.mark.skipif(os.name != "nt", reason="Windows 확장 drive 경로")
def test_extended_result_from_resolve_remains_inside_own_run(boundary, monkeypatch):
    guard, _ = boundary
    own = guard.run_root / "contended.json.lock"
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **k:
        Path("\\\\?\\" + str(own)) if p == own else original(p, *a, **k))
    guard("open", (str(own), None, os.O_RDWR | os.O_CREAT))
    assert guard.write_paths == {str(own)} and not guard.blocked_file_writes


@pytest.mark.skipif(os.name != "nt", reason="Windows 확장 drive 경로")
@pytest.mark.parametrize("kind", ["outside", "sibling_prefix", "device", "unc", "extended_unc",
                                  "volume", "parent", "dot", "trailing_dot", "stream", "reserved", "slash_unc"])
def test_extended_path_does_not_open_other_namespaces_or_noncanonical_paths(boundary, kind):
    guard, parent = boundary
    own = "\\\\?\\" + str(guard.run_root)
    candidates = {
        "outside": "\\\\?\\" + str(parent / "worker-two" / "outside.lock"),
        "sibling_prefix": own + "-other\\outside.lock",
        "device": "\\\\.\\C:\\outside.lock",
        "unc": "\\\\server\\share\\outside.lock",
        "slash_unc": "//server/share/outside.lock",
        "extended_unc": "\\\\?\\UNC\\server\\share\\outside.lock",
        "volume": "\\\\?\\Volume{00000000-0000-0000-0000-000000000000}\\outside.lock",
        "parent": own + "\\..\\worker-two\\outside.lock",
        "dot": own + "\\.\\own.lock",
        "trailing_dot": own + "\\alias.\\own.lock",
        "stream": own + "\\own.lock:payload",
        "reserved": own + "\\NUL.lock",
    }
    with pytest.raises(PermissionError):
        guard("open", (candidates[kind], None, os.O_RDWR | os.O_CREAT))
    assert not guard.write_paths and len(guard.blocked_file_writes) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows 확장 drive 경로")
@pytest.mark.parametrize("inside", [True, False])
def test_extended_junction_resolution_is_not_a_canonical_path(boundary, monkeypatch, inside):
    # 기존 guard 회귀와 같은 resolve 대역. 실제 junction/외부 파일은 만들지 않는다.
    guard, parent = boundary
    alias = guard.run_root / "junction" / "own.lock"
    target = (guard.run_root if inside else parent) / "destination" / "own.lock"
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **k: target if p == alias else original(p, *a, **k))
    with pytest.raises(PermissionError):
        guard("open", ("\\\\?\\" + str(alias), None, os.O_RDWR | os.O_CREAT))
    assert not guard.write_paths and guard.blocked_file_writes


@pytest.mark.skipif(os.name != "nt", reason="Windows 확장 drive 경로")
def test_extended_own_run_path_keeps_protected_root_denial(boundary):
    guard, _ = boundary
    guard.protected_roots = (guard.run_root / "protected",)
    with pytest.raises(PermissionError):
        guard("open", ("\\\\?\\" + str(guard.protected_roots[0] / "own.lock"), None, os.O_RDWR | os.O_CREAT))
    assert not guard.write_paths and guard.blocked_file_writes


def test_timing_includes_setup_skip_and_teardown_errors():
    from types import SimpleNamespace
    observer = VerificationTiming()
    observer.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid="tests/test_a.py::test_a")]))
    for when, outcome in (("setup", "skipped"), ("teardown", "failed")):
        observer.pytest_runtest_logreport(SimpleNamespace(nodeid="tests/test_a.py::test_a", when=when,
                                                        outcome=outcome, duration=0.25))
    assert observer.collected_nodeids == sorted(observer.executed_nodeids)
    assert observer.phase_seconds["setup"] == observer.phase_seconds["teardown"] == 0.25
    assert observer.phase_outcomes[-1]["outcome"] == "failed"


def test_subtest_failure_is_retained_without_duplicate_call_or_double_timing():
    from types import SimpleNamespace
    class SubtestReport(SimpleNamespace):
        pass
    observer = VerificationTiming()
    row = dict(nodeid="tests/test_a.py::test_a", when="call", outcome="failed", duration=0.25)
    observer.pytest_runtest_logreport(SubtestReport(**row))
    observer.pytest_runtest_logreport(SimpleNamespace(**{**row, "outcome": "passed", "duration": 0.5}))
    assert len(observer.phase_outcomes) == len(observer.subtest_outcomes) == 1
    assert observer.subtest_outcomes[0]["outcome"] == "failed"
    assert observer.phase_seconds["call"] == 0.5
