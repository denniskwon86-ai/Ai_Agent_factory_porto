"""검증 전용 audit 경계와 pytest 시간 관찰기. 앱/DB를 import하지 않는다."""
from __future__ import annotations

import os
from pathlib import Path
import re
import time
import traceback
from urllib.parse import urlsplit
from urllib.request import url2pathname


class VerificationIsolation:
    def __init__(self, run_root, *, strict=False, protected_roots=()):
        self.run_root = Path(run_root).resolve()
        self.strict = strict
        self.protected_roots = tuple(Path(p).resolve() for p in protected_roots)
        self.sqlite_paths = set()
        self.write_paths = set()
        self.blocked_sqlite_paths = []
        self.blocked_file_writes = []
        self.final_report = None

    def _deny_write(self, event, path=None):
        self.blocked_file_writes.append({
            "event": event, "path": str(path) if path is not None else None,
            "test": os.environ.get("PYTEST_CURRENT_TEST", "collection"),
            "stack": traceback.format_stack(limit=10),
        })
        raise PermissionError("검증 작업은 지정된 RUN 밖에 쓰거나 하위 프로세스를 실행할 수 없습니다")

    def _write_path(self, candidate):
        """Windows FileLock의 확장 drive 표기만 동일한 RUN 경로로 대조한다."""
        raw = os.fsdecode(candidate)

        def local_path(value):
            if os.name != "nt" or not value.replace("/", "\\").startswith("\\\\"):
                return Path(value), False
            # UNC/장치/Volume 경로를 drive 경로인 것처럼 잘라내지 않는다.
            if (not value.startswith("\\\\?\\") or len(value) < 7
                    or value[4] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                    or value[5:7] != ":\\"):
                raise ValueError("확장 로컬 drive 경로만 허용")
            normal = value[4:]
            for part in normal[3:].split("\\"):
                if (not part or part in {".", ".."} or part.endswith((".", " "))
                        or any(ord(char) < 32 or char in '/:<>"|?*' for char in part)
                        or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]",
                                        part.split(".")[0], re.IGNORECASE)):
                    raise ValueError("비정규 확장 경로")
            path = Path(normal)
            if not path.is_relative_to(self.run_root):
                raise ValueError("다른 RUN의 확장 경로")
            return path, True

        path, extended = local_path(raw)
        resolved, _ = local_path(str(path.resolve()))
        if extended and resolved != path:
            raise ValueError("확장 경로의 링크/상위 이동 우회")
        return resolved

    def __call__(self, event, arguments):
        if event == "sqlite3.connect":
            raw = str(arguments[0])
            if raw.startswith("file:"):
                # 기존 RUN의 정규화된 읽기 전용 URI만 허용한다. URI의 별도
                # VFS/쓰기/메모리/상대경로/다른 RUN 우회는 계속 금지한다.
                try:
                    parts = urlsplit(raw)
                    readonly = Path(url2pathname(parts.path)).resolve()
                    if (not parts.netloc and raw == readonly.as_uri() + "?mode=ro"
                            and readonly.is_relative_to(self.run_root) and readonly.is_file()):
                        self.sqlite_paths.add(str(readonly))
                        return
                except (OSError, ValueError):
                    pass
                self.blocked_sqlite_paths.append(raw)
                raise PermissionError("읽기 전용 SQLite URI는 현재 RUN의 기존 정규 파일만 허용합니다")
            path = Path(raw).resolve()
            if raw == ":memory:" or not path.is_relative_to(self.run_root):
                self.blocked_sqlite_paths.append(raw)
                raise PermissionError("검증은 현재 RUN 안의 신규 SQLite 경로만 사용할 수 있습니다")
            self.sqlite_paths.add(str(path))
            return
        if not self.strict and not self.protected_roots:
            return
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "os.exec", "os.spawn",
                     "os.startfile", "os.startfile/2"}:
            self._deny_write(event)
        candidates = []
        if event == "open" and len(arguments) >= 3:
            flags = arguments[2]
            write = isinstance(flags, int) and bool(flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if write:
                candidates = [arguments[0]]
                if (self.strict and isinstance(arguments[0], (str, bytes, os.PathLike))
                        and not Path(os.fsdecode(arguments[0])).is_absolute()):
                    # open audit에는 dir_fd가 없다. cwd와 다른 fd 기준을 증명할 수 없다.
                    self._deny_write(event, arguments[0])
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.truncate", "os.chmod", "os.utime"}:
            candidates = [arguments[0]]
            # dir_fd 기준의 상대 경로를 cwd 기준으로 잘못 승인하지 않는다.
            dir_index = {"os.remove": 1, "os.rmdir": 1, "os.mkdir": 2,
                         "os.chmod": 2, "os.utime": 3}.get(event)
            if self.strict and dir_index is not None and len(arguments) > dir_index:
                if arguments[dir_index] not in (None, -1):
                    self._deny_write(event, "dir_fd")
        elif event in {"os.rename", "os.replace", "os.link", "os.symlink"}:
            candidates = list(arguments[:2])
            if self.strict and event == "os.symlink" and len(arguments) > 2:
                if arguments[2] not in (None, -1):
                    self._deny_write(event, "dir_fd")
            if self.strict and event in {"os.rename", "os.replace", "os.link"}:
                if any(fd not in (None, -1) for fd in arguments[2:4]):
                    self._deny_write(event, "dir_fd")
        for candidate in candidates:
            if not isinstance(candidate, (str, bytes, os.PathLike)):
                continue  # 이미 열린 stdout/stderr 등 fd는 새 파일 경로가 아니다.
            try:
                path = self._write_path(candidate)
            except (OSError, ValueError):
                self._deny_write(event, candidate)
            if self.final_report is not None and event == "open" and path == self.final_report:
                continue  # pytest 종료 후 단일 create-x 보고서에만 활성화한다.
            denied = (self.strict and not path.is_relative_to(self.run_root)) or any(
                path.is_relative_to(root) for root in self.protected_roots)
            if denied:
                self._deny_write(event, path)
            if path.is_relative_to(self.run_root):
                self.write_paths.add(str(path))


class VerificationTiming:
    def __init__(self):
        self.started = time.perf_counter()
        self.collected_nodeids = []
        self.executed_nodeids = set()
        self.phase_outcomes = []
        self.subtest_outcomes = []
        self.phase_seconds = {"setup": 0.0, "call": 0.0, "teardown": 0.0}

    def pytest_collection_finish(self, session):
        self.collected_nodeids = [item.nodeid for item in session.items]
        self.phase_seconds["collection"] = time.perf_counter() - self.started

    def pytest_runtest_logreport(self, report):
        self.executed_nodeids.add(report.nodeid)
        row = {"nodeid": report.nodeid, "when": report.when,
               "outcome": report.outcome, "duration": report.duration}
        if type(report).__name__.casefold() == "subtestreport":
            self.subtest_outcomes.append(row)
            return  # 기본 call 시간에 포함되므로 시간·기본 단계 수를 중복 합산하지 않는다.
        self.phase_outcomes.append(row)
        self.phase_seconds[report.when] = self.phase_seconds.get(report.when, 0.0) + report.duration
