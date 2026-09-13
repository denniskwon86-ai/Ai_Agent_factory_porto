"""Stdlib-only verification dispatcher. Never imports core or pytest.

Collection establishes the expected node IDs before 1-2 isolated child runners
execute disjoint FILE groups. Only the registered regression scope is certified;
browser verification and full execution-task integration remain separate gates.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNNER = "scripts/verify_data_usage_holds.py"
_SHA = re.compile(r"[0-9a-fA-F]{64}")
# Main-supplied historical serial JUnit costs; never read history at dispatch.
# These fixed LPT hints are relative allocation costs, NOT a runtime forecast.
_BASELINE_HINTS = {
    "tests/test_b3_kit_contract_v2.py": 751.102,
    "tests/test_b3_release_readiness.py": 315.768,
    "tests/test_b3_runtime_data.py": 287.756,
    "tests/test_b3_kit_rejection.py": 267.612,
    "tests/test_b3_kit_api.py": 156.785,
    "tests/test_b3_process_context.py": 99.270,
}
_BASELINE_PROVENANCE = "output/usage-holds-6m4qchly"


class EvidenceError(ValueError):
    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _require(condition, message):
    if not condition:
        raise EvidenceError(message)


def _relative(value):
    _require(isinstance(value, str) and bool(value), "nonempty relative path required")
    value = value.replace("\\", "/")
    _require(not any(ch in value for ch in ("\x00", "\n", "\r", ":")), "invalid relative path")
    _require(all(part not in ("", ".", "..") for part in value.split("/")), "unsafe relative path")
    return value


def canonical_target(value):
    _require(isinstance(value, str), "target must be a string")
    path, separator, selector = value.partition("::")
    path = _relative(path)
    _require(path.startswith("tests/") and path.endswith(".py"), "target must be a tests/*.py file or node")
    if separator:
        _require(bool(selector) and not any(ch in selector for ch in ("\x00", "\n", "\r")), "empty/invalid node selector")
    return path + (separator + selector if separator else "")


def covers(selector, nodeid):
    left, right = selector.split("::", 1), nodeid.split("::", 1)
    if left[0].casefold() != right[0].casefold():
        return False
    if len(left) == 1:
        return True
    if len(right) == 1:
        return False
    return right[1] == left[1] or right[1].startswith(left[1] + "::") or right[1].startswith(left[1] + "[")


def canonical_targets(values):
    _require(isinstance(values, (list, tuple)) and bool(values), "zero targets are not verifiable")
    targets = [canonical_target(value) for value in values]
    for index, target in enumerate(targets):
        _require(not any(covers(target, other) or covers(other, target) for other in targets[:index]),
                 "duplicate/overlapping targets: " + target)
    return targets


def prepare_plan(raw, full, *, tier):
    """Pure validation. Planner labels cannot promote a subset to a full PASS."""
    _require(tier in {"quick", "feature", "full"}, "invalid verification tier")
    _require(isinstance(raw, dict) and all(key in raw for key in ("targets", "coverage", "reasons")), "incomplete plan")
    targets, full = canonical_targets(raw["targets"]), canonical_targets(full)
    is_full = set(targets) == set(full)
    _require(tier != "full" or is_full, "full tier does not match full_targets registry")
    try:
        json.dumps({"coverage": raw["coverage"], "reasons": raw["reasons"]}, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise EvidenceError("planner explanations are not JSON data") from exc
    return {"tier": tier, "targets": targets, "coverage": raw["coverage"], "reasons": raw["reasons"],
            "scope": "FULL_REGISTERED" if is_full else "SELECTED", "full_target_count": len(full),
            "selected_target_count": len(targets),
            "separate_gates": ["full_execution_task_integration", "browser"]}


def partition_targets(targets, jobs=1, weights=None):
    """Pure deterministic LPT. Default cost is ONE per file, not elapsed seconds.
    Never split node selectors from the same file across workers.
    """
    targets = canonical_targets(targets)
    _require(type(jobs) is int and jobs in (1, 2), "jobs must be 1 or 2")
    groups = {}
    for target in targets:
        groups.setdefault(target.split("::", 1)[0].casefold(), []).append(target)
    supplied = {} if weights is None else weights
    _require(isinstance(supplied, dict) and set(supplied).issubset(groups), "unknown file weight")
    fixed = {path: supplied.get(path, 1.0) for path in groups}
    _require(all(_number(value) and value > 0 for value in fixed.values()), "invalid file weight")
    count = min(jobs, len(groups))
    bins, totals = [[] for _ in range(count)], [0.0] * count
    for path in sorted(groups, key=lambda key: (-fixed[key], key)):
        index = min(range(count), key=lambda i: (totals[i], i))
        bins[index].extend(sorted(groups[path]))
        totals[index] += fixed[path]
    validate_partition(targets, bins)
    return {"partitions": bins, "weights": fixed, "worker_weights": totals,
            "weight_source": "baseline_equal_file" if weights is None else "supplied_fixed",
            "weight_unit": "relative_cost_not_seconds"}


def partition_with_baseline_hints(targets, jobs=1):
    """Filter fixed file-cost hints to the selected plan; no history/file I/O."""
    targets = canonical_targets(targets)
    files = {target.split("::", 1)[0].casefold() for target in targets}
    hints = {path: weight for path, weight in _BASELINE_HINTS.items() if path in files}
    if not hints:
        return partition_targets(targets, jobs)
    result = partition_targets(targets, jobs, weights=hints)
    result.update(weight_source="baseline_fixed_serial_junit_hints", weight_hints=hints,
                  weight_provenance=_BASELINE_PROVENANCE, weight_is_forecast=False,
                  weight_note="Main-supplied prior serial JUnit whole-file costs, frozen as LPT allocation hints only. "
                              "Unlisted files cost 1; selectors retain the whole-file hint. "
                              "Estimates for partitioning, not predicted elapsed seconds; no history lookup.")
    return result


def validate_partition(targets, partitions):
    targets = canonical_targets(targets)
    _require(isinstance(partitions, list) and 1 <= len(partitions) <= 2, "one or two workers required")
    flat, files = [], set()
    for group in partitions:
        normalized = canonical_targets(group)
        group_files = {target.split("::", 1)[0].casefold() for target in normalized}
        _require(not files.intersection(group_files), "same test file assigned to multiple workers")
        files.update(group_files)
        flat.extend(normalized)
    _require(len(flat) == len(set(flat)) and set(flat) == set(targets), "partition has missing/extra/duplicate targets")


def _number(value):
    return type(value) in (float, int) and math.isfinite(value) and value >= 0


def _hashes(value, label):
    _require(isinstance(value, dict) and bool(value), label + " is missing/empty")
    out = {}
    for key, digest in value.items():
        key = _relative(key)
        _require(key not in out and isinstance(digest, str) and bool(_SHA.fullmatch(digest)), label + " is malformed")
        out[key] = digest.lower()
    return out


def _nodeids(value, *, empty_allowed=False):
    _require(isinstance(value, list), "node IDs must be an explicit list")
    result = [canonical_target(node) for node in value]
    _require(all("::" in node for node in result), "collected/executed node ID lacks test selector")
    _require(empty_allowed or bool(result), "zero tests are not verifiable")
    _require(len(result) == len(set(result)), "duplicate node IDs")
    return result


def _absolute(value):
    _require(isinstance(value, str) and bool(value) and not value.startswith("file:"), "absolute filesystem path required")
    _require(Path(value).is_absolute(), "relative runtime path")
    return Path(os.path.normcase(os.path.abspath(value)))


@dataclass(frozen=True)
class Invocation:
    label: str
    invocation_id: str
    targets: tuple[str, ...]
    collect_only: bool
    report_file: Path


def validate_phases(value, executed, *, collect_only):
    """Require terminal setup/call/teardown evidence, including setup skips."""
    _require(isinstance(value, list), "phase_outcomes missing")
    if collect_only:
        _require(not value and not executed, "collector ran test phases")
        return
    phases = {node: {} for node in executed}
    for row in value:
        _require(isinstance(row, dict), "invalid phase row")
        node = canonical_target(row.get("nodeid"))
        when, outcome = row.get("when"), row.get("outcome")
        _require(node in phases and when in ("setup", "call", "teardown"), "unexpected test phase")
        _require(when not in phases[node], "duplicate test phase")
        _require(outcome in ("passed", "skipped"), "test phase failed/error/interrupted")
        _require(_number(row.get("duration")), "invalid phase duration")
        _require(when != "call" or phases[node].get("setup") == "passed", "call before successful setup")
        _require(when != "teardown" or "setup" in phases[node], "teardown before setup")
        _require("teardown" not in phases[node], "phase after teardown")
        phases[node][when] = outcome
    for row in phases.values():
        _require(row.get("setup") in ("passed", "skipped") and row.get("teardown") == "passed", "missing/unsuccessful terminal phases")
        required = {"setup", "teardown"} if row["setup"] == "skipped" else {"setup", "call", "teardown"}
        _require(set(row) == required, "missing/extra call phase")


def validate_subtests(value, executed, phases, *, collect_only):
    """Subtests may repeat a node/phase; they never replace terminal phases."""
    _require(isinstance(value, list), "subtest_outcomes missing/non-list")
    if collect_only:
        _require(not value, "collector ran subtests")
        return
    executed = set(executed)
    main_phases = {(canonical_target(row["nodeid"]), row["when"]) for row in phases}
    for row in value:
        _require(isinstance(row, dict), "invalid subtest row")
        node = canonical_target(row.get("nodeid"))
        when = row.get("when")
        _require(node in executed and when in ("setup", "call", "teardown"), "unexpected subtest node/phase")
        _require((node, when) in main_phases, "subtest lacks corresponding main phase")
        _require(row.get("outcome") in ("passed", "skipped"), "subtest failed/error/interrupted")
        _require(_number(row.get("duration")), "invalid subtest duration")


def validate_report(report, invocation, *, root, returncode, reference=None):
    """Pure evidence validator: no filesystem/DB/process reads or writes."""
    _require(isinstance(report, dict), "missing/non-object child report")
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    check(type(returncode) is int and returncode == 0, "child process did not exit zero")
    check(type(report.get("exit_code")) is int and report["exit_code"] == 0, "reported pytest exit is not zero")
    check(type(report.get("wrapper_exit_code")) is int and report["wrapper_exit_code"] == 0, "reported wrapper exit is not zero")
    check(report.get("invocation_id") == invocation.invocation_id, "invocation ID mismatch")
    check(report.get("strict_writes") is True, "strict write guard not attested")
    check(report.get("audit_hook_installed") is True, "audit hook not attested")
    check(report.get("pytest_environment_sanitized") is True, "pytest environment sanitization not attested")
    check(report.get("collect_only") is invocation.collect_only, "collect-only mode mismatch")
    check(report.get("repository_conftest_loaded") is False, "repository conftest loaded/unreported")
    check(report.get("sources_unchanged") is True, "source invariance not attested")
    check(report.get("protected_assets_unchanged") is True, "asset invariance not attested")
    check(report.get("selection") == "", "hidden pytest selection")
    for field in ("blocked_sqlite_paths", "blocked_file_writes"):
        check(type(report.get(field)) is list and not report[field], field + " is nonempty/unreported")
    if "blocked_subprocesses" in report:
        check(type(report["blocked_subprocesses"]) is list and not report["blocked_subprocesses"], "subprocess guard violations")
    check(_number(report.get("elapsed_seconds")), "invalid elapsed_seconds")
    phases = report.get("phase_seconds")
    check(isinstance(phases, dict) and bool(phases) and all(isinstance(k, str) and _number(v) for k, v in phases.items()),
          "invalid phase_seconds")
    try:
        targets = canonical_targets(report.get("targets"))
        check(set(targets) == set(invocation.targets), "reported targets mismatch")
        collected = _nodeids(report.get("collected_nodeids"))
        executed = _nodeids(report.get("executed_nodeids"), empty_allowed=invocation.collect_only)
        check(all(any(covers(target, node) for target in invocation.targets) for node in collected), "collected node outside targets")
        check(all(any(covers(target, node) for node in collected) for target in invocation.targets), "target collected zero tests")
        if invocation.collect_only:
            check(not executed, "collector executed tests")
        else:
            check(set(executed) == set(collected), "executed nodes differ from collection")
        validate_phases(report.get("phase_outcomes"), executed, collect_only=invocation.collect_only)
        validate_subtests(report.get("subtest_outcomes"), executed, report["phase_outcomes"],
                          collect_only=invocation.collect_only)
        source_before = _hashes(report.get("source_hashes_before"), "source hashes before")
        source_after = _hashes(report.get("source_hashes_after"), "source hashes after")
        asset_before = _hashes(report.get("asset_hashes_before"), "asset hashes before")
        asset_after = _hashes(report.get("asset_hashes_after"), "asset hashes after")
        check(source_before == source_after, "source hashes changed")
        check(asset_before == asset_after, "asset hashes changed")
        if reference is not None:
            check(source_before == reference["source_hashes_before"], "different source snapshot between children")
            check(asset_before == reference["asset_hashes_before"], "different asset snapshot between children")
        runtime = _absolute(report.get("run_root"))
        output = _absolute(str(Path(root) / "output"))
        check(runtime.parent == output and runtime.name.startswith("usage-holds-") and runtime.name != "usage-holds-",
              "child RUN is not its own output/usage-holds-* directory")
        paths = report.get("sqlite_paths")
        check(isinstance(paths, list), "SQLite paths unreported")
        if isinstance(paths, list):
            actual_paths = [_absolute(path) for path in paths]
            check(len(actual_paths) == len(set(actual_paths)), "duplicate SQLite paths")
            check(all(path != runtime and path.is_relative_to(runtime) for path in actual_paths), "SQLite outside own child RUN")
        writes = report.get("write_paths")
        check(isinstance(writes, list), "write paths unreported")
        if isinstance(writes, list):
            check(all(_absolute(path).is_relative_to(runtime) for path in writes), "file write outside own child RUN")
    except EvidenceError as exc:
        errors.extend(exc.errors)
    if errors:
        raise EvidenceError(errors)
    return {**report, "targets": targets, "collected_nodeids": collected, "executed_nodeids": executed,
            "source_hashes_before": source_before, "source_hashes_after": source_after,
            "asset_hashes_before": asset_before, "asset_hashes_after": asset_after,
            "run_root": str(runtime)}


def aggregate_reports(collection, workers, *, root, targets, partitions):
    """Pure aggregation. Each record has invocation, report and returncode.
    No claimed top-level PASS, flags or test counts can replace exact node sets.
    """
    validate_partition(targets, partitions)
    _require(len(workers) == len(partitions), "missing/extra worker report")
    ref = validate_report(collection["report"], collection["invocation"], root=root, returncode=collection["returncode"])
    _require(collection["invocation"].collect_only and set(ref["targets"]) == set(targets), "collector did not cover complete planned targets")
    expected = set(ref["collected_nodeids"])
    seen, roots, ids, errors = set(), {ref["run_root"]}, {collection["invocation"].invocation_id}, []
    for index, (worker, assigned) in enumerate(zip(workers, partitions)):
        try:
            invocation = worker["invocation"]
            _require(not invocation.collect_only and set(invocation.targets) == set(assigned), "worker assignment mismatch")
            _require(invocation.invocation_id not in ids, "reused invocation ID")
            ids.add(invocation.invocation_id)
            report = validate_report(worker["report"], invocation, root=root, returncode=worker["returncode"], reference=ref)
            _require(report["run_root"] not in roots, "reused child RUN")
            roots.add(report["run_root"])
            expected_worker = {node for node in expected if any(covers(target, node) for target in assigned)}
            _require(set(report["collected_nodeids"]) == expected_worker, "worker collection differs from expected manifest")
            actual = set(report["executed_nodeids"])
            _require(not seen.intersection(actual), "node executed by multiple workers")
            seen.update(actual)
        except (EvidenceError, KeyError, TypeError) as exc:
            errors.append("worker %d: %s" % (index + 1, exc))
    if seen != expected:
        errors.append("expected node IDs missing/extra: missing=%d extra=%d" % (len(expected - seen), len(seen - expected)))
    if errors:
        raise EvidenceError(errors)
    return {"expected_node_count": len(expected), "executed_node_count": len(seen), "executed_nodeids": sorted(seen)}


def sanitized_env(source):
    """Pure copy; never log values or mutate the calling process environment.

    Compare keys case-insensitively so Windows aliases cannot reintroduce pytest
    selection/plugin injection. Bytecode suppression remains enforced per child.
    """
    excluded = {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONDONTWRITEBYTECODE"}
    result = {key: value for key, value in source.items() if key.upper() not in excluded}
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    return result


def build_command(root, invocation):
    """Pure fixed executable/entrypoint construction; no shell command strings."""
    targets = canonical_targets(invocation.targets)
    root, destination = _absolute(str(root)), _absolute(str(invocation.report_file))
    parent = destination.parent
    _require(parent.parent == root / "output" and parent.name.startswith("verification-"), "unsafe report parent")
    _require(destination.suffix == ".json", "report must be JSON")
    try:
        _require(str(uuid.UUID(invocation.invocation_id)) == invocation.invocation_id, "noncanonical invocation UUID")
    except (ValueError, AttributeError) as exc:
        raise EvidenceError("invalid invocation UUID") from exc
    _require(type(invocation.collect_only) is bool, "invalid invocation mode")
    command = [sys.executable, "-B", str(root / RUNNER), "--b0", "--b1", "--b2", "--b3"]
    for target in targets:
        command.extend(["--target", target])
    command.extend(["--strict-writes", "--report-file", str(destination), "--invocation-id", invocation.invocation_id])
    if invocation.collect_only:
        command.append("--collect-only")
    return command


def _no_links(path, root):
    """Reject symlink/junction ancestors, including Windows reparse points."""
    root, path = Path(root), Path(path)
    _require(path.is_relative_to(root), "path outside expected root")
    current = root
    for part in (None, *path.relative_to(root).parts):
        if part is not None:
            current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        _require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
                 "symlink/reparse point is not evidence: " + str(current))


def _snapshot(root):
    """Independent parent inventory; never reads runtime/operational DB folders."""
    root = Path(root)
    sources = set(root.glob("*.py"))
    assets = set()
    for folder, sink, python_only in [
        *((name, sources, True) for name in ("core", "api", "nodes", "tests", "scripts")),
        *((name, assets, False) for name in ("starter_kits", "docs/data-kits", "process_packs")),
    ]:
        base = root / folder
        _no_links(base, root)
        for directory, dirs, names in os.walk(base, followlinks=False):
            for name in list(dirs):
                child = Path(directory) / name
                _no_links(child, root)
                if python_only and name in ("__pycache__", ".git"):
                    dirs.remove(name)
            for name in names:
                if not python_only or name.endswith(".py"):
                    sink.add(Path(directory) / name)
    result = {}
    for label, paths in (("sources", sources), ("assets", assets)):
        hashes = {}
        for path in sorted(paths):
            _no_links(path, root)
            _require(path.is_file(), "snapshot entry is not a file")
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        _require(bool(hashes), "empty parent " + label + " manifest")
        result[label] = hashes
    return result


def _verify_disk_evidence(root, report):
    for label in ("source_hashes_after", "asset_hashes_after"):
        for relative, expected in report[label].items():
            path = Path(root) / _relative(relative)
            _no_links(path, root)
            _require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                     "reported hash does not match disk: " + relative)
    runtime = Path(report["run_root"])
    _no_links(runtime, root)
    _require(runtime.is_dir(), "child RUN missing")
    for name in ("sqlite_paths", "write_paths"):
        for value in report[name]:
            _no_links(_absolute(value), root)


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        _require(key not in obj, "duplicate JSON key: " + key)
        obj[key] = value
    return obj


def _invalid_constant(value):
    raise EvidenceError("nonfinite JSON constant: " + value)


def _load_report(child, root):
    path = child.invocation.report_file
    _no_links(path, root)
    info = path.stat()
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "report not a unique regular file")
    _require(0 < info.st_size <= 64 * 1024 * 1024, "missing/oversized report")
    _require(info.st_mtime >= child.started_wall - 2, "stale report timestamp")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def _write_json_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class Cancelled(Exception):
    pass


@dataclass
class Child:
    invocation: Invocation
    process: object
    stdout: object
    stderr: object
    started_wall: float
    started_monotonic: float
    logged: bool = False


class Dispatcher:
    """Owns every child handle from launch through cancellation/termination."""
    def __init__(self, root, directory):
        self.root, self.directory = Path(root), Path(directory)
        self.children = []
        self.cancelled = False
        self.events = (self.directory / "events.jsonl").open("x", encoding="utf-8")

    def event(self, kind, **payload):
        self.events.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": kind, **payload}, ensure_ascii=False) + "\n")
        self.events.flush()

    def cancel(self, signum, frame):
        # Do not raise between Popen and registering its returned process handle.
        self.cancelled = True

    def check_cancelled(self):
        if self.cancelled:
            raise Cancelled("verification cancelled; no PASS may be issued")

    def start(self, label, targets, *, collect_only=False):
        self.check_cancelled()
        _require(sum(child.process.poll() is None for child in self.children) < 2, "at most two concurrent children")
        invocation_id = str(uuid.uuid4())
        invocation = Invocation(label, invocation_id, tuple(targets), collect_only, self.directory / (label + "-" + invocation_id + ".json"))
        _require(not invocation.report_file.exists(), "report destination already exists")
        out = (self.directory / (label + ".stdout.log")).open("xb")
        try:
            err = (self.directory / (label + ".stderr.log")).open("xb")
        except BaseException:
            out.close()
            raise
        started_wall, started_monotonic = time.time(), time.monotonic()
        try:
            process = subprocess.Popen(build_command(self.root, invocation), cwd=str(self.root), shell=False,
                                       stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       env=sanitized_env(os.environ),
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except BaseException:
            out.close()
            err.close()
            raise
        child = Child(invocation, process, out, err, started_wall, started_monotonic)
        self.children.append(child)
        self.event("child_started", label=label, pid=process.pid, invocation_id=invocation_id,
                   targets=list(targets), collect_only=collect_only, report_file=str(invocation.report_file))
        self.check_cancelled()
        return child

    def finish_log(self, child):
        if child.logged:
            return
        child.stdout.close()
        child.stderr.close()
        self.event("child_finished", label=child.invocation.label, pid=child.process.pid,
                   returncode=child.process.poll(), elapsed_seconds=time.monotonic() - child.started_monotonic)
        child.logged = True

    def wait(self, children):
        pending = list(children)
        while pending:
            self.check_cancelled()
            for child in list(pending):
                if child.process.poll() is not None:
                    self.finish_log(child)
                    pending.remove(child)
            if pending:
                time.sleep(0.1)
        self.check_cancelled()

    def record(self, child):
        return {"invocation": child.invocation, "returncode": child.process.returncode,
                "report": _load_report(child, self.root)}

    def cleanup(self):
        errors = []
        for child in self.children:
            try:
                if child.process.poll() is None:
                    child.process.terminate()
                    try:
                        child.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.process.kill()
                        child.process.wait(timeout=5)
                self.finish_log(child)
            except Exception as exc:
                errors.append("child cleanup failed: %s: %s" % (child.invocation.label, exc))
        return errors


def _new_directory(root):
    output = Path(root) / "output"
    _no_links(output, root)
    output.mkdir(exist_ok=True)
    _require(output.is_dir(), "output is not a directory")
    directory = Path(tempfile.mkdtemp(prefix="verification-", dir=output))
    _no_links(directory, root)
    return directory


def run(root, prepared, split):
    """Return exit status. Only this function launches children or writes evidence."""
    started = time.monotonic()
    directory = _new_directory(root)
    runner = Dispatcher(root, directory)
    summary = {"status": "FAIL", "plan": prepared, "partition": split, "evidence_directory": str(directory),
               "errors": [], "children": [], "overall_product_pass": False}
    previous = {}
    baseline = None
    try:
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            number = getattr(signal, name, None)
            if number is not None:
                previous[number] = signal.signal(number, runner.cancel)
        _write_json_new(directory / "plan.json", {"plan": prepared, "partition": split})
        baseline = _snapshot(root)
        _write_json_new(directory / "parent-hashes-before.json", baseline)
        collector = runner.start("collect", prepared["targets"], collect_only=True)
        runner.wait([collector])
        collection = runner.record(collector)
        reference = validate_report(collection["report"], collection["invocation"], root=root, returncode=collection["returncode"])
        _verify_disk_evidence(root, reference)
        _require(_snapshot(root) == baseline, "parent source/asset inventory changed during collection")
        expected = reference["collected_nodeids"]
        _write_json_new(directory / "expected-nodeids.json", {"invocation_id": collector.invocation.invocation_id,
                         "targets": prepared["targets"], "nodeids": expected})
        workers = []
        for index, group in enumerate(split["partitions"], 1):
            workers.append(runner.start("worker-%d" % index, group))
        runner.wait(workers)
        records, errors = [], []
        for child in workers:
            try:
                record = runner.record(child)
                report = validate_report(record["report"], record["invocation"], root=root,
                                         returncode=record["returncode"], reference=reference)
                _verify_disk_evidence(root, report)
                records.append(record)
            except (EvidenceError, OSError, ValueError, TypeError, KeyError) as exc:
                errors.append(child.invocation.label + ": " + str(exc))
        _require(not errors, errors)
        result = aggregate_reports(collection, records, root=root, targets=prepared["targets"], partitions=split["partitions"])
        _require(_snapshot(root) == baseline, "parent source/asset inventory changed during execution")
        runner.check_cancelled()
        summary.update(result)
        summary["status"] = "PASS"
    except (Cancelled, KeyboardInterrupt) as exc:
        runner.cancelled = True
        summary["errors"].append(str(exc) or "verification interrupted")
    except Exception as exc:
        summary["errors"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        summary["errors"].extend(runner.cleanup())
        if baseline is not None:
            try:
                after = _snapshot(root)
                _write_json_new(directory / "parent-hashes-after.json", after)
                _require(after == baseline, "parent source/assets changed before completion")
            except Exception as exc:
                summary["errors"].append("final source/asset check: " + str(exc))
        if runner.cancelled:
            summary["status"] = "CANCELLED"
        elif summary["errors"]:
            summary["status"] = "FAIL"
        summary["children"] = [{"label": child.invocation.label, "invocation_id": child.invocation.invocation_id,
                                "report_file": str(child.invocation.report_file), "returncode": child.process.poll()}
                               for child in runner.children]
        summary["elapsed_seconds"] = time.monotonic() - started
        try:
            runner.event("verification_finished", status=summary["status"], errors=summary["errors"])
            _write_json_new(directory / "summary.json", summary)
        finally:
            runner.events.close()
            for number, handler in previous.items():
                signal.signal(number, handler)
    # Cancellation in the final write window still cannot yield process success.
    if runner.cancelled and summary["status"] != "CANCELLED":
        _write_json_new(directory / "cancelled.json", {"status": "CANCELLED", "supersedes": "summary.json"})
        summary["status"] = "CANCELLED"
    print(json.dumps({"status": summary["status"], "scope": prepared["scope"], "tier": prepared["tier"],
                      "executed_node_count": summary.get("executed_node_count", 0),
                      "separate_gates": prepared["separate_gates"], "summary": str(directory / "summary.json"),
                      "errors": summary["errors"]}, ensure_ascii=False), flush=True)
    return 130 if summary["status"] == "CANCELLED" else int(summary["status"] != "PASS")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("quick", "feature", "full"), default="full")
    parser.add_argument("--changed", action="append", default=[])
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=1)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        # Running this script without -B must not write planner bytecode either.
        sys.dont_write_bytecode = True
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.verification_plan import full_targets, normalize_target, plan

        raw = plan(ROOT, tier=args.tier, changed=tuple(args.changed))
        raw = {**raw, "targets": [normalize_target(ROOT, target) for target in raw["targets"]]}
        full = [normalize_target(ROOT, target) for target in full_targets(ROOT)]
        prepared = prepare_plan(raw, full, tier=args.tier)
        split = partition_with_baseline_hints(prepared["targets"], args.jobs)
        if args.plan_only:
            print(json.dumps({"status": "PLAN_ONLY", "plan": prepared, "partition": split}, ensure_ascii=False, indent=2))
            return 0
        return run(ROOT, prepared, split)
    except KeyboardInterrupt:
        print(json.dumps({"status": "CANCELLED", "errors": ["interrupted before dispatch completion"]}), file=sys.stderr)
        return 130
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "errors": [type(exc).__name__ + ": " + str(exc)]}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
