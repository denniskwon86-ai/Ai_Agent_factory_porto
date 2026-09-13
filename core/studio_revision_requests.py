"""B5 수정 요청의 고정 접수 영수증. 실행·승인·초안 소비는 수행하지 않는다.

접수 기록과 task는 같은 WBS 파일에 저장한다. 다른 DB·프로세스·외부 파일 편집까지
원자적이라고 주장하지 않으며, 호출자는 서버 실행 예약과 현재 권한 검사를 유지한다.
"""
from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import re
import uuid

from pydantic import Field, field_validator, model_validator

from core.enterprise_context.process_schema import StrictModel, ProcessError
from core.studio_input_drafts import Target, digest, validate_content

RECORDS_KEY = "studio_revision_requests"
MAX_WBS_BYTES = 32 * 1024 * 1024
TASK_FIELDS = ("task_id", "title", "goal", "required_agents", "artifact_kind", "artifact_kind_source",
               "studio_revision_submission_id", "studio_revision_request_id", "studio_revision_target")


def fail(code, message, status=409):
    raise ProcessError("REVISION_REQUEST_" + code, message, status)


def request_key(value):
    if not isinstance(value, str):
        fail("INVALID", "UUID 요청 ID가 필요합니다.", 422)
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ProcessError("REVISION_REQUEST_INVALID", "UUID 요청 ID가 필요합니다.", 422) from exc
    if parsed != value.lower():
        fail("INVALID", "하이픈을 포함한 UUID 요청 ID가 필요합니다.", 422)
    return value


class InputDraftRef(StrictModel):
    draft_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class Submission(StrictModel):
    client_request_id: str = Field(min_length=36, max_length=36)
    target: Target
    feedback: str = Field(min_length=1, max_length=32000)
    input_draft: InputDraftRef

    @field_validator("client_request_id")
    @classmethod
    def normalize_key(cls, value):
        try:
            return request_key(value)
        except ProcessError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("feedback", mode="before")
    @classmethod
    def normalize_feedback(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("수정 의견이 필요합니다.")
        return value

    @model_validator(mode="after")
    def revision_target(self):
        if self.target.kind != "REVISION_REQUEST" or self.target.request_id != "artifact_" + self.target.target_digest:
            raise ValueError("현재 산출물의 수정 요청 대상이 필요합니다.")
        return self


def wbs_path(workspace_root):
    root = Path(workspace_root)
    for part in (root, *root.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            fail("WBS_UNAVAILABLE", "연결된 프로젝트 경로는 사용할 수 없습니다.", 503)
    if not root.is_dir():
        fail("WBS_REQUIRED", "기존 프로젝트와 WBS가 필요합니다.")
    path = root / "00_wbs_master_plan.json"
    for item in (path, Path(str(path) + ".lock")):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            fail("WBS_UNAVAILABLE", "연결된 WBS 경로는 사용할 수 없습니다.", 503)
    return path


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 JSON 키")
        result[key] = value
    return result


def read_wbs_strict(path):
    """GET은 잠금 파일이나 빈 WBS를 만들지 않는다. 원자 교체 전후의 혼합도 거절한다."""
    path = wbs_path(Path(path).parent)
    try:
        before = path.stat()
        if before.st_size > MAX_WBS_BYTES or before.st_nlink > 1:
            raise ValueError("WBS 크기 또는 연결 수")
        with path.open("rb") as stream:
            raw = stream.read(MAX_WBS_BYTES + 1)
        after = path.stat()
        if (len(raw) != before.st_size or any(getattr(before, k) != getattr(after, k)
                for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns"))):
            fail("CONFLICT", "조회 중 WBS가 변경되었습니다. 다시 조회하십시오.")
        doc = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("비유한 JSON")))
        if not isinstance(doc, dict) or not isinstance(doc.get("tasks"), list):
            raise ValueError("WBS 형식")
        from core import wbs_artifact_kind as kind
        if kind.classify_profile(doc.get(kind.PROFILE_KEY), key_present=kind.PROFILE_KEY in doc) == kind.UNREADABLE:
            raise ValueError("WBS 계약 프로필 손상")
        tasks = doc["tasks"]
        if any(not isinstance(t, dict) or not isinstance(t.get("task_id"), str)
               or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", t["task_id"]) for t in tasks):
            raise ValueError("task 식별자")
        if len({t["task_id"] for t in tasks}) != len(tasks):
            raise ValueError("중복 task")
        if "total_tasks" in doc and (type(doc["total_tasks"]) is not int or doc["total_tasks"] != len(tasks)):
            raise ValueError("task 개수")
        if RECORDS_KEY in doc and not isinstance(doc[RECORDS_KEY], dict):
            raise ValueError("접수 원장 형식")
        for task in tasks:
            if any(key.startswith("studio_revision_") for key in task):
                record = doc.get(RECORDS_KEY, {}).get(task.get("studio_revision_request_id"))
                if (not isinstance(record, dict) or not isinstance(record.get("receipt"), dict)
                        or record["receipt"].get("task_id") != task["task_id"]):
                    raise ValueError("접수 원장 없는 task")
        return doc, hashlib.sha256(raw).hexdigest()
    except FileNotFoundError as exc:
        raise ProcessError("REVISION_REQUEST_WBS_REQUIRED", "접수할 기존 WBS가 없습니다.", 409) from exc
    except ProcessError:
        raise
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise ProcessError("REVISION_REQUEST_WBS_UNAVAILABLE", "WBS를 정확히 읽지 못했습니다. 원본을 보존합니다.", 503) from exc


def _task_fixed(task):
    return {k: task[k] for k in TASK_FIELDS if k in task}


def verified_record(doc, key, *, project_id, actor_id, boundary):
    record = doc.get(RECORDS_KEY, {}).get(key)
    if record is None:
        return None
    if not isinstance(record, dict) or not isinstance(record.get("receipt"), dict):
        fail("RECEIPT_UNAVAILABLE", "접수 증거 형식을 확인하지 못했습니다.", 503)
    receipt = record["receipt"]
    if not isinstance(receipt.get("actor_id"), str) or not receipt["actor_id"] or not isinstance(record.get("context_key"), dict):
        fail("RECEIPT_UNAVAILABLE", "접수 사용자·문맥 증거가 손상됐습니다.", 503)
    if (receipt.get("actor_id", "").casefold() != actor_id.casefold()
            or record.get("context_key") != boundary or receipt.get("project_id") != project_id):
        fail("NOT_FOUND", "현재 사용자·문맥에서 접수 기록을 찾을 수 없습니다.", 404)
    try:
        command = Submission.model_validate(dict(client_request_id=receipt["request_id"], target=receipt["target"],
            feedback=receipt["feedback"], input_draft=receipt["input_draft"])).model_dump()
        material = {k: v for k, v in receipt.items() if k != "receipt_digest"}
        if (request_key(key) != key or receipt["request_id"] != key or receipt["status"] != "ACCEPTED"
                or receipt["execution_started"] is not False or receipt["receipt_digest"] != digest(material)
                or record["command_digest"] != digest(command)
                or record["record_digest"] != digest({k: v for k, v in record.items() if k != "record_digest"})
                or not re.fullmatch(r"srr_[0-9a-f]{32}", receipt["submission_id"])
                or receipt["task_id"] != "TASK_REV_" + receipt["submission_id"][4:]
                or not datetime.fromisoformat(receipt["created_at"]).tzinfo):
            raise ValueError("접수 지문 또는 상태")
        tasks = [t for t in doc["tasks"] if t["task_id"] == receipt["task_id"]]
        if (len(tasks) != 1 or _task_fixed(tasks[0]) != record["task"]
                or not isinstance(tasks[0].get("status"), str) or not tasks[0]["status"]
                or tasks[0]["goal"] != receipt["feedback"]
                or tasks[0]["studio_revision_submission_id"] != receipt["submission_id"]
                or tasks[0]["studio_revision_request_id"] != key
                or tasks[0]["studio_revision_target"] != receipt["target"]):
            raise ValueError("접수 task 증거")
        return copy.deepcopy(receipt)
    except (KeyError, TypeError, ValueError, AttributeError, ProcessError) as exc:
        raise ProcessError("REVISION_REQUEST_RECEIPT_UNAVAILABLE", "고정 영수증과 실제 WBS task의 일치를 확인하지 못했습니다.", 503) from exc


def read_receipt(workspace_root, *, project_id, actor_id, boundary, client_request_id=None, submission_id=None, allow_missing=False):
    doc, _ = read_wbs_strict(wbs_path(workspace_root))
    if client_request_id is not None:
        key = request_key(client_request_id)
    else:
        if not isinstance(submission_id, str) or not re.fullmatch(r"srr_[0-9a-f]{32}", submission_id):
            fail("INVALID", "서버 발급 접수 ID가 필요합니다.", 422)
        matches = [key for key, value in doc.get(RECORDS_KEY, {}).items() if isinstance(value, dict)
                   and isinstance(value.get("receipt"), dict)
                   and value["receipt"].get("submission_id") == submission_id]
        if len(matches) > 1:
            fail("RECEIPT_UNAVAILABLE", "접수 ID가 중복됐습니다.", 503)
        key = matches[0] if matches else None
    receipt = verified_record(doc, key, project_id=project_id, actor_id=actor_id, boundary=boundary) if key else None
    if not receipt and not allow_missing:
        fail("NOT_FOUND", "현재 사용자·문맥에서 접수 기록을 찾을 수 없습니다.", 404)
    return receipt


def make_record(manager, doc, *, project_id, actor_id, boundary, command):
    if not doc["tasks"]:
        fail("WBS_REQUIRED", "작업이 있는 기존 WBS가 필요합니다.")
    if command["target"]["task_id"] != "sprint_init" and not any(
            task["task_id"] == command["target"]["task_id"] for task in doc["tasks"]):
        fail("TARGET_CONFLICT", "기준 task가 현재 WBS에 없습니다.")
    submission_id = "srr_" + uuid.uuid4().hex
    task_id = "TASK_REV_" + submission_id[4:]
    if any(t["task_id"] == task_id for t in doc["tasks"]):
        fail("CONFLICT", "새 task 식별자가 충돌했습니다.")
    task = manager._apply_profile(doc, dict(task_id=task_id, title="사용자 수정 요청 반영", goal=command["feedback"],
        status="TODO", required_agents=["Tech_Lead", "Backend", "Frontend"], artifact_kind="APP",
        studio_revision_submission_id=submission_id, studio_revision_request_id=command["client_request_id"],
        studio_revision_target=copy.deepcopy(command["target"])))
    receipt = dict(request_id=command["client_request_id"], submission_id=submission_id, project_id=project_id,
        actor_id=actor_id, target=copy.deepcopy(command["target"]), feedback=command["feedback"],
        input_draft=copy.deepcopy(command["input_draft"]), task_id=task_id, status="ACCEPTED",
        execution_started=False, created_at=datetime.now(timezone.utc).isoformat())
    receipt["receipt_digest"] = digest(receipt)
    record = dict(receipt=receipt, context_key=copy.deepcopy(boundary), command_digest=digest(command), task=_task_fixed(task))
    record["record_digest"] = digest(record)
    return record, task


def reject_duplicate_draft(doc, *, project_id, actor_id, boundary, command):
    """요청 키를 바꿔도 같은 저장 초안 판으로 수정 task 두 개를 만들지 않는다."""
    for key, record in doc.get(RECORDS_KEY, {}).items():
        if not isinstance(record, dict) or not isinstance(record.get("receipt"), dict):
            fail("RECEIPT_UNAVAILABLE", "기존 접수 증거가 손상됐습니다.", 503)
        receipt = record["receipt"]
        if (record.get("context_key") == boundary and receipt.get("actor_id", "").casefold() == actor_id.casefold()
                and receipt.get("input_draft") == command["input_draft"]):
            verified_record(doc, key, project_id=project_id, actor_id=actor_id, boundary=boundary)
            fail("DRAFT_ALREADY_SUBMITTED", "같은 저장 초안 판이 이미 접수됐습니다. 기존 요청 ID의 영수증을 확인하십시오.")


def verify_input_draft(row, command):
    ref = command["input_draft"]
    content = validate_content(row["target"], row["content"])
    if (row["status"] != "DRAFT" or row["draft_id"] != ref["draft_id"] or row["revision"] != ref["revision"]
            or row["digest"] != ref["digest"] or row["target"] != command["target"]
            or content["text"].strip() != command["feedback"]):
        fail("DRAFT_CONFLICT", "저장한 수정 초안의 대상·본문·판본과 제출 내용이 다릅니다.")


def accept_request(workspace_root, *, project_id, actor_id, boundary, submission, before_write):
    from nodes.utils.wbs_manager import WBSManager
    # 생성자의 디렉터리 생성이 없는 프로젝트를 복구하는 것처럼 보이지 않게 한다.
    wbs_path(workspace_root)
    return WBSManager(str(workspace_root)).accept_revision_request(project_id=project_id, actor_id=actor_id,
        boundary=boundary, submission=submission, before_write=before_write)


def verify_consumption(row, receipt, *, expected_revision, expected_digest):
    ref = receipt["input_draft"]
    if (receipt["project_id"] != row["project_id"] or receipt["actor_id"].casefold() != row["actor"]
            or receipt["target"] != row["target"] or receipt["feedback"] != row["content"]["text"].strip()
            or ref != dict(draft_id=row["draft_id"], revision=expected_revision, digest=expected_digest)):
        fail("SUBMISSION_CONFLICT", "접수 영수증의 사용자·대상·저장 초안·본문이 다릅니다.")
    if row["status"] == "DRAFT":
        if row["revision"] != expected_revision or row["digest"] != expected_digest:
            fail("DRAFT_CONFLICT", "접수한 초안 판본과 현재 초안이 다릅니다.")
    elif (row["status"] != "CONSUMED" or row.get("submission_id") != receipt["submission_id"]
          or row["revision"] != expected_revision + 1):
        fail("DRAFT_CONFLICT", "접수 후 초안 상태가 변경되었습니다.")
    return dict(submission_id=receipt["submission_id"], draft_id=row["draft_id"], draft_digest=expected_digest)
