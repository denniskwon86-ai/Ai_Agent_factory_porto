"""B5 명령 ID에 결속된 healing task의 단일 WBS append. 실행은 하지 않는다.

호출자는 새 영속 CommandStore 접수·권한·프로젝트 예약·HEAL 예산을 먼저 확인한다.
여기는 기존 FileLock/strict reader/CAS/원자 교체만 담당하며 DB와 분산 원자적이지 않다.
"""
import json
import os
import re
import tempfile

from filelock import FileLock, Timeout

from core.enterprise_context.process_schema import ProcessError
from core import studio_revision_requests as strict
from core.studio_execution_commands import canonical, digest, request_key, MAX_REQUEST_BYTES
from nodes.utils.wbs_manager import WBSManager


class HealingTaskError(ProcessError):
    pass


def fail(code, message, status=409):
    raise HealingTaskError("STUDIO_HEAL_" + code, message, status)


FIXED_FIELDS = ("task_id", "title", "goal", "required_agents", "artifact_kind", "artifact_kind_source",
                "studio_execution_request_id", "source_task_id", "studio_execution_command_digest")


def append_healing_task(workspace_root, *, request_id, source_task_id, error_log):
    """동기 함수. 같은 key/body는 task ID만 재반환하며 본문이나 진행 상태를 초기화하지 않는다."""
    temporary = None
    try:
        key = request_key(request_id)
        if (type(source_task_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", source_task_id)
                or type(error_log) is not str or not error_log.strip() or len(error_log) > MAX_REQUEST_BYTES):
            fail("INVALID", "복구 원 task와 비어 있지 않은 오류 원문이 필요합니다.", 422)
        command = dict(request_id=key, source_task_id=source_task_id, error_log=error_log)
        canonical(command, limit=MAX_REQUEST_BYTES)
        task_id = "TASK_REV_HEAL_" + key.replace("-", "")
        path = strict.wbs_path(workspace_root)
        with FileLock(str(path) + ".lock").acquire(timeout=10):
            document, original_digest = strict.read_wbs_strict(path)
            task = WBSManager._apply_profile(document, dict(task_id=task_id, title="오류 복구 요청 반영",
                goal=f"🚨 [자동 캡처 에러 리포트] UI 렌더링 중 에러 발생:\n{error_log}\n해당 에러를 분석하여 코드를 즉시 복원하십시오.",
                status="TODO", required_agents=["Tech_Lead", "Backend", "Frontend"], artifact_kind="APP",
                studio_execution_request_id=key, source_task_id=source_task_id,
                studio_execution_command_digest=digest(command)))
            matching = [item for item in document["tasks"] if item["task_id"] == task_id
                        or (isinstance(item.get("studio_execution_request_id"), str)
                            and item["studio_execution_request_id"].casefold() == key)]
            if matching:
                if len(matching) != 1 or matching[0]["task_id"] != task_id:
                    fail("INTEGRITY", "복구 명령에 결속된 task가 중복되거나 변경됐습니다.", 503)
                prior = matching[0]
                fingerprint = prior.get("studio_execution_command_digest")
                if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                    fail("INTEGRITY", "기존 복구 task의 명령 지문을 확인하지 못했습니다.", 503)
                if fingerprint != task["studio_execution_command_digest"]:
                    fail("IDEMPOTENCY_CONFLICT", "같은 복구 요청 ID의 원 task·오류 본문이 다릅니다.")
                if {name: prior[name] for name in FIXED_FIELDS if name in prior} != {
                        name: task[name] for name in FIXED_FIELDS if name in task}:
                    fail("INTEGRITY", "고정 복구 task의 원문·프로필 결속을 확인하지 못했습니다.", 503)
                return task_id
            if not document["tasks"]:
                fail("WBS_REQUIRED", "복구할 기존 작업 목록이 필요합니다.")
            if source_task_id != "sprint_init" and not any(item["task_id"] == source_task_id for item in document["tasks"]):
                fail("TARGET_CONFLICT", "복구 원 task가 현재 WBS에 없습니다.")
            document["tasks"].append(task)
            document["total_tasks"] = len(document["tasks"])
            raw = json.dumps(document, ensure_ascii=False, indent=4, allow_nan=False).encode("utf-8")
            if len(raw) > strict.MAX_WBS_BYTES:
                fail("CAPACITY", "복구 task 추가가 WBS 크기 제한을 넘습니다. 원본을 보존합니다.")
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".healing-task-", suffix=".tmp",
                                             dir=str(path.parent), delete=False) as stream:
                temporary = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _, current_digest = strict.read_wbs_strict(path)
            if current_digest != original_digest:
                fail("CONFLICT", "복구 task 저장 직전 WBS가 변경됐습니다. 원본을 보존합니다.")
            os.replace(temporary, path)
            temporary = None
            return task_id
    except HealingTaskError:
        raise
    except Timeout as exc:
        raise HealingTaskError("STUDIO_HEAL_BUSY", "다른 WBS 처리가 진행 중입니다. 원요청 ID를 보존하십시오.", 409) from exc
    except ProcessError as exc:
        code = exc.reason_code.removeprefix("REVISION_REQUEST_").removeprefix("STUDIO_COMMAND_")
        raise HealingTaskError("STUDIO_HEAL_" + code, str(exc), exc.status_code) from exc
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        raise HealingTaskError("STUDIO_HEAL_WBS_UNAVAILABLE", "복구 task 저장 결과를 확정하지 못했습니다. 원요청 ID를 보존하십시오.", 503) from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
