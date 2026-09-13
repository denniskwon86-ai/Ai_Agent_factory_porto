"""명시적 일시정지의 체크포인트 증거. 승인이나 분산 실행 잠금이 아니다.

읽기는 파일을 만들지 않는다. 쓰기는 기존 프로젝트 안에서 잠금·원자 교체하며,
체크포인트 본문 대신 지문만 보존한다. 재개 접수 후 증거는 재사용하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from filelock import FileLock

from core.enterprise_context.process_schema import ProcessError

FILENAME = ".studio_pause_state.json"
MAX_BYTES = 4 * 1024 * 1024
EVIDENCE_KEYS = {"project_id", "task_id", "thread_id", "checkpoint_id", "state_digest",
                 "next_nodes", "factory_mode", "template_id", "config_fingerprint"}


def fail(code, message, status=409):
    raise ProcessError("STUDIO_PAUSE_" + code, message, status)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _path(root):
    root = Path(root)
    path = root / FILENAME
    for item in (root, *root.parents, path, Path(str(path) + ".lock")):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            fail("UNAVAILABLE", "연결된 정지 증거 경로는 사용할 수 없습니다.", 503)
    if not root.is_dir():
        fail("UNAVAILABLE", "기존 프로젝트 경로를 확인하지 못했습니다.", 503)
    return path


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 JSON 키")
        result[key] = value
    return result


def _load(path):
    try:
        before = path.stat()
    except FileNotFoundError:
        return {"schema_version": 1, "records": {}}
    if before.st_size > MAX_BYTES or before.st_nlink != 1:
        raise ValueError("증거 크기 또는 연결 수")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    after = path.stat()
    if len(raw) != before.st_size or any(getattr(before, k) != getattr(after, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns")):
        fail("CONFLICT", "조회 중 정지 증거가 변경되었습니다.")
    doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError("비유한 값")))
    if (type(doc) is not dict or set(doc) != {"schema_version", "records"}
            or type(doc["schema_version"]) is not int or doc["schema_version"] != 1
            or type(doc["records"]) is not dict):
        raise ValueError("정지 증거 형식")
    for task_id, row in doc["records"].items():
        if (type(row) is not dict or set(row) != {"evidence", "status", "recorded_at", "digest"}
                or row["status"] not in {"PAUSED", "CONSUMED"}
                or type(row["evidence"]) is not dict or set(row["evidence"]) != EVIDENCE_KEYS
                or row["evidence"]["task_id"] != task_id
                or row["evidence"]["project_id"] != path.parent.name
                or not isinstance(row["recorded_at"], str)
                or row["digest"] != digest({k: v for k, v in row.items() if k != "digest"})):
            raise ValueError("정지 증거 무결성")
    return doc


def read(root, task_id):
    try:
        return _load(_path(root))["records"].get(task_id)
    except ProcessError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ProcessError("STUDIO_PAUSE_UNAVAILABLE", "정지 증거를 검증하지 못했습니다.", 503) from exc


def _write(root, task_id, evidence, expected=None):
    temp_path = None
    try:
        path = _path(root)
        with FileLock(str(path) + ".lock", timeout=5):
            doc = _load(_path(root))
            old = doc["records"].get(task_id)
            if expected is not None and (old != expected or old["status"] != "PAUSED"):
                fail("CONFLICT", "정지 증거가 변경되었거나 이미 재개 접수되었습니다.")
            row = {"evidence": evidence, "status": "CONSUMED" if expected is not None else "PAUSED",
                   "recorded_at": datetime.now(timezone.utc).isoformat()}
            row["digest"] = digest(row)
            doc["records"][task_id] = row
            raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
            if len(raw) > MAX_BYTES:
                raise ValueError("정지 증거 크기")
            fd, temp_path = tempfile.mkstemp(prefix=".studio_pause_", suffix=".tmp", dir=path.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _path(root)
            os.replace(temp_path, path)
            temp_path = None
            return row
    except ProcessError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ProcessError("STUDIO_PAUSE_UNAVAILABLE", "정지 증거를 저장하지 못했습니다.", 503) from exc
    finally:
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)


def record(root, evidence):
    return _write(root, evidence["task_id"], evidence)


def consume(root, row):
    return _write(root, row["evidence"]["task_id"], row["evidence"], expected=row)
