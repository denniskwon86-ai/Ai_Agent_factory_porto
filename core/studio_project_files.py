"""B3 승격 전용 파일 IO. 고정 참조와 일반 실행 상태를 분리한다."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from core import atomic_write
from core.advisor_revision_store import RevisionStoreError
from core.enterprise_context.process_schema import fingerprint

STUDIO_FIELDS = ("runtime_document_version", "process_context", "approved_blueprint_revision_id",
                 "approved_blueprint_digest", "bootstrap_operation_id", "context_root_id", "setup_status")
PROJECTION_FIELDS = ("runtime_document_version", "process_context", "approved_blueprint_revision_id",
                     "approved_blueprint_digest", "bootstrap_operation_id", "context_root_id",
                     "tenant_id", "enterprise_scope_id", "entity_mode", "blueprint_id", "owner_user_id")
MARKER = ".studio_setup.json"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("object required")
        return value
    except (OSError, ValueError, TypeError) as exc:
        raise RevisionStoreError("STUDIO_PROJECT_UNREADABLE", "프로젝트 저장 상태를 확인할 수 없습니다.", 503) from exc


def read_json_with_digest(path):
    """★★ [10.2-B] 내용과 지문을 **같은 바이트에서** 얻는다.

    읽고 나서 따로 `digest_of` 를 부르면 그 사이가 창이다 — 남이 바꾼 뒤의 지문을
    「내가 읽은 것」으로 삼게 된다. 읽기-수정-쓰기의 기준은 **그 읽기** 여야 한다.

    파일이 없으면 `(None, "")` 이다."""
    try:
        with open(path, "rb") as stream:
            raw = stream.read()
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        raise RevisionStoreError("STUDIO_PROJECT_UNREADABLE",
                                 "프로젝트 저장 상태를 확인할 수 없습니다.", 503) from exc
    try:
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("object required")
    except (ValueError, TypeError) as exc:
        raise RevisionStoreError("STUDIO_PROJECT_UNREADABLE",
                                 "프로젝트 저장 상태를 확인할 수 없습니다.", 503) from exc
    return value, hashlib.sha256(raw).hexdigest()


def write_json(path, value, *, expected_digest=None):
    """같은 폴더 임시 파일 → 교체. 오류를 성공으로 삼키지 않는다.

    구현은 `core/atomic_write.py` 한 곳에 있다(여기서 먼저 쓰던 것을 그리로 옮겼다).
    직렬화 정책 — `sort_keys`·`allow_nan=False` — 은 이 저장의 것이므로 여기 남는다.

    ★★ [CR 판단③] `expected_digest` 를 주면 **조건부 저장**이 된다 — 읽은 판본이
      그대로일 때만 바꾼다. `operation_lock` 은 잠금 파일이 `data/studio_bootstrap_locks`
      즉 **노드 로컬**이라 승격 조작의 «이 노드 안» 멱등성만 지키고, 다른 노드의 writer 는
      막지 못한다. 저장 수준의 보장은 정본 옆 잠금 + 판본 조건으로 세운다.

    ⚠️ 별도 함수로 빼지 않는다. 한 번 빼 봤더니 **실패 주입 지점이 갈라져**
      `monkeypatch.setattr(module, "write_json", …)` 로 세운 기존 보장이 조용히
      무력화됐다(시험이 잡았다). 이음매는 하나로 둔다.
    """
    if expected_digest is None:
        atomic_write.replace_json(path, value, sort_keys=True, indent=2, allow_nan=False)
        return ""
    return atomic_write.replace_json_if_unchanged(
        path, value, expected_digest=expected_digest,
        sort_keys=True, indent=2, allow_nan=False)


def projection(value):
    if any(key not in value for key in PROJECTION_FIELDS):
        raise RevisionStoreError("STUDIO_PROJECT_CONTEXT_MISSING", "프로젝트의 고정 승인 참조가 누락되었습니다.")
    return {key: value[key] for key in PROJECTION_FIELDS}


def recover_marker(workspace, marker):
    """빈 예약 폴더 또는 완성된 동일 operation 임시 marker만 복구한다.

    강제 종료로 finally가 못 지운 완성 임시파일은 보존한다. 이름만 같은 파일,
    부분 JSON/다른 operation/외부 파일/링크의 소유권은 추측하지 않는다.
    """
    import re
    folder = Path(workspace)
    if not folder.is_dir() or folder.is_symlink():
        raise FileExistsError(str(workspace))
    for entry in folder.iterdir():
        if (entry.is_symlink() or not entry.is_file()
                or not re.fullmatch(re.escape(MARKER) + r"\.[0-9a-f]{32}\.tmp", entry.name)):
            raise FileExistsError(str(workspace))
        try:
            if read_json(entry) != marker:
                raise FileExistsError(str(workspace))
        except RevisionStoreError as exc:
            raise FileExistsError(str(workspace)) from exc
    write_json(folder / MARKER, marker)


def verify_files(workspace, expected, *, ready=False):
    values = [read_json(Path(workspace) / name) for name in ("project_meta.json", "latest_state.json")]
    target = projection(expected)
    for value in values:
        if projection(value) != target or (ready and value.get("setup_status") != "READY"):
            raise RevisionStoreError("STUDIO_PROJECT_CONTEXT_CONFLICT", "프로젝트와 승인된 업무 참조가 다릅니다.")
    return {"meta_digest": fingerprint(projection(values[0])), "state_digest": fingerprint(projection(values[1]))}


@contextmanager
def operation_lock(project_id):
    """다중 프로세스 중복 I/O를 직렬화한다. 기다리지 않고 409로 재시도를 안내한다."""
    import re
    from core.paths import data_path
    if not re.fullmatch(r"prj_[0-9a-f]{32}", project_id):
        raise RevisionStoreError("STUDIO_PROJECT_ID_INVALID", "서버가 예약한 프로젝트 ID가 필요합니다.", 422)
    root = Path(data_path("studio_bootstrap_locks"))
    root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(root / (project_id + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise RevisionStoreError("STUDIO_BOOTSTRAP_BUSY", "같은 승격 요청을 처리 중입니다. 동일 요청으로 다시 확인하십시오.") from exc
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
