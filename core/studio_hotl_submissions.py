"""B5 일반 HOTL 제출의 영속 접수증. 재개 실행·권한 판정·자동 재시도는 하지 않는다.

호출자는 principal/서버 프로젝트 소속/현재 차수를 확인하고 target을 서버에서 만든다.
주입한 AdvisorStore의 연결·잠금만 사용하며 생성자/import에는 DB 접근이 없다.
지문 규칙은 `studio_input_drafts`와 같은 것을 쓴다 — 초안 판본과 대조해야 하므로
두 벌을 두면 같은 본문이 서로 다른 지문을 갖는다.

일반 HOTL 검토 의견과 명확화 답변을 받는다. 계약·능력·데이터셋 결정은 원장 사건이
증거이므로 여기 오지 않는다(`studio_input_drafts.verify_decision_submission`).

★ 두 종류는 **본문 대조 지점이 다르다.**
  · 일반 HOTL — 제출 본문이 초안 `content.text` 를 다듬은 것이라 소비 시점에 바로 맞춘다.
  · 명확화 — 화면이 질문·선택지·설명을 엮어 제출하므로 **접수 시점에** 서버가
    `core.clarify_answers.serialize` 로 재현해 대조한다(설계안 갈래 A,
    `docs/design_l2_clarification_draft_consumption_2026-09-14.md`). 접수된 뒤에는 그
    대조가 끝났으므로 소비는 저장 판본 결속만 확인한다 — 차수가 지나가면 질문을 다시
    읽을 수 없기 때문이다.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import re
import sqlite3
import uuid

from core.enterprise_context.process_schema import ProcessError
from core.studio_input_drafts import InputDraftError, InputDraftStore, Target, canonical, digest, validate_content

MAX_REQUEST_BYTES = 64 * 1024
OUTCOMES = frozenset({"ACCEPTED", "REJECTED", "UNKNOWN"})
TABLE = "studio_hotl_submissions"


class HOTLSubmissionError(ProcessError):
    pass


def fail(code, message, status=409):
    raise HOTLSubmissionError("STUDIO_HOTL_" + code, message, status)


def request_key(value):
    try:
        if type(value) is not str or len(value) != 36:
            raise ValueError("UUID")
        key = str(uuid.UUID(value))
        if key != value.lower():
            raise ValueError("UUID canonical")
        return key
    except (ValueError, AttributeError) as exc:
        raise HOTLSubmissionError("STUDIO_HOTL_INVALID", "하이픈을 포함한 UUID 요청 ID가 필요합니다.", 422) from exc


def _draft_ref(value):
    if (type(value) is not dict or set(value) != {"draft_id", "revision", "digest"}
            or type(value["draft_id"]) is not str or not 1 <= len(value["draft_id"]) <= 128
            or type(value["revision"]) is not int or type(value["revision"]) is bool or value["revision"] < 1
            or type(value["digest"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["digest"])):
        fail("INVALID", "저장한 초안의 식별자·판본·지문이 필요합니다.", 422)
    return dict(value)


def _submission(value):
    """서버가 만든 target과 사용자 본문만 받는다. 문맥·권한·차수는 여기서 정하지 않는다."""
    if type(value) is not dict or set(value) != {"client_request_id", "task_id", "target", "feedback", "input_draft"}:
        fail("INVALID", "일반 HOTL 제출의 필수 필드만 전달하십시오.", 422)
    task, feedback = value["task_id"], value["feedback"]
    if (type(task) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", task)
            or type(feedback) is not str or not feedback.strip() or len(feedback) > 32000):
        fail("INVALID", "task와 비어 있지 않은 검토 의견을 확인하십시오.", 422)
    try:
        target = Target.model_validate(value["target"]).model_dump()
    except Exception as exc:
        raise HOTLSubmissionError("STUDIO_HOTL_INVALID", "현재 결정 대상을 확인하십시오.", 422) from exc
    #: 일반 HOTL 검토 의견과 명확화 답변만 받는다. 계약·능력·데이터셋 결정은 원장 사건이 증거다.
    if not ((target["kind"] == "DECISION_COMMENT" and target["decision_kind"] == "GENERAL_HOTL")
            or (target["kind"] == "CLARIFICATION" and not target["decision_kind"])):
        fail("TARGET_UNSUPPORTED", "일반 HOTL 검토 의견과 명확화 답변만 이 경로로 접수합니다.", 422)
    if target["task_id"] != task:
        fail("TARGET_CONFLICT", "제출 task와 대상 task가 다릅니다.")
    command = dict(client_request_id=request_key(value["client_request_id"]), task_id=task,
                   target=target, feedback=feedback.strip(), input_draft=_draft_ref(value["input_draft"]))
    return json.loads(canonical(command))


def _identity(project_id, actor_id, boundary):
    if (type(project_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", project_id)
            or type(actor_id) is not str or not actor_id.strip() or len(actor_id) > 256
            or type(boundary) is not dict or not boundary):
        fail("INVALID", "서버 프로젝트·인증 사용자·문맥이 필요합니다.", 422)
    return project_id, actor_id.strip().casefold(), canonical(boundary)


_DDL = (
    """CREATE TABLE IF NOT EXISTS studio_hotl_submissions (
      request_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, actor_id TEXT NOT NULL,
      boundary_json TEXT NOT NULL, task_id TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('PROCESSING','ACCEPTED','REJECTED','UNKNOWN')),
      command_digest TEXT NOT NULL, receipt_digest TEXT NOT NULL,
      created_at TEXT NOT NULL, record_json TEXT NOT NULL, record_digest TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS studio_hotl_submissions_project ON studio_hotl_submissions(project_id,created_at)",
)


class HOTLSubmissionStore:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def transaction(self, write=False):
        """동기 트랜잭션. 이 문맥 안에서 await/재진입/재개 실행을 하지 않는다."""
        try:
            with self.store._lock:
                conn = self.store._connect()
                try:
                    conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                    if write:
                        for statement in _DDL:
                            conn.execute(statement)
                    yield conn
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
        except (sqlite3.Error, OSError) as exc:
            raise HOTLSubmissionError("STUDIO_HOTL_STORAGE_UNAVAILABLE", "제출 기록을 확인하지 못했습니다. 요청 ID를 보존하십시오.", 503) from exc

    @staticmethod
    def _ready(conn):
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is not None

    @staticmethod
    def _unpack(row):
        try:
            raw = row["record_json"]
            payload = json.loads(raw)
            if (canonical(payload) != raw or digest(payload) != row["record_digest"]
                    or set(payload) != {"boundary", "record"}
                    or canonical(payload["boundary"]) != row["boundary_json"]):
                raise ValueError("record fingerprint")
            value = payload["record"]
            expected = {"request_id", "project_id", "actor_id", "task_id", "target", "feedback", "input_draft",
                        "command_digest", "status", "result", "created_at", "updated_at", "receipt_digest"}
            if type(value) is not dict or set(value) != expected:
                raise ValueError("record schema")
            command = _submission(dict(client_request_id=value["request_id"], task_id=value["task_id"],
                                       target=value["target"], feedback=value["feedback"], input_draft=value["input_draft"]))
            identity = _identity(value["project_id"], value["actor_id"], payload["boundary"])
            if (identity != (row["project_id"], row["actor_id"], row["boundary_json"])
                    or value["actor_id"] != identity[1] or value["request_id"] != command["client_request_id"]
                    or any(value[key] != row[key] for key in
                           ("request_id", "project_id", "actor_id", "task_id", "status", "command_digest", "receipt_digest", "created_at"))
                    or value["command_digest"] != digest(command)
                    or value["receipt_digest"] != digest({key: child for key, child in value.items() if key != "receipt_digest"})
                    or value["status"] not in OUTCOMES | {"PROCESSING"}
                    or (value["status"] == "PROCESSING" and value["result"] is not None)
                    or (value["status"] in OUTCOMES and type(value["result"]) is not dict)):
                raise ValueError("record binding")
            created, updated = (datetime.fromisoformat(value[key]) for key in ("created_at", "updated_at"))
            if not created.tzinfo or not updated.tzinfo or updated < created:
                raise ValueError("record timestamp")
            return value
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError, HOTLSubmissionError) as exc:
            raise HOTLSubmissionError("STUDIO_HOTL_INTEGRITY", "제출 기록의 무결성을 확인하지 못했습니다. 원기록을 보존합니다.", 503) from exc

    def _row(self, conn, identity, key):
        row = conn.execute("SELECT * FROM studio_hotl_submissions WHERE request_id=?", (key,)).fetchone() if self._ready(conn) else None
        if row is None or (row["project_id"], row["actor_id"], row["boundary_json"]) != identity:
            fail("NOT_FOUND", "현재 사용자·문맥에서 제출 기록을 찾을 수 없습니다.", 404)
        return row

    @staticmethod
    def _pack(value, boundary_json):
        value = {**value, "receipt_digest": digest({key: child for key, child in value.items() if key != "receipt_digest"})}
        payload = dict(boundary=json.loads(boundary_json), record=value)
        return value, canonical(payload), digest(payload)

    def _assert_current_draft(self, conn, identity, command):
        """접수 INSERT와 같은 BEGIN IMMEDIATE 연결에서만 초안 판을 확인한다."""
        ref = command["input_draft"]
        try:
            row = InputDraftStore(self.store)._get(conn,
                (identity[2], identity[1], identity[0]), ref["draft_id"])
        except InputDraftError as exc:
            if exc.status_code == 404:
                fail("DRAFT_CONFLICT", "접수할 저장 초안을 현재 문맥에서 확인할 수 없습니다.")
            raise HOTLSubmissionError("STUDIO_HOTL_DRAFT_INTEGRITY",
                "접수할 초안의 무결성을 확인하지 못했습니다.", 503) from exc
        if (row["status"] != "DRAFT" or row["target"] != command["target"]
                or row["revision"] != ref["revision"] or row["digest"] != ref["digest"]):
            fail("DRAFT_CONFLICT", "접수 직전 저장 초안의 상태·대상·판본이 바뀌었습니다.")
        try:
            content = validate_content(row["target"], row["content"])
        except (ValueError, KeyError, ProcessError) as exc:
            raise HOTLSubmissionError("STUDIO_HOTL_DRAFT_INTEGRITY",
                "접수할 초안 본문의 무결성을 확인하지 못했습니다.", 503) from exc
        # 명확화 조합은 API가 락 밖에서 검증한다. 같은 초안 digest를 재검증했으므로
        # 검증한 선택/메모가 접수 사이 바뀌면 위에서 차단된다.
        if row["target"]["kind"] == "DECISION_COMMENT" and command["feedback"] != content["text"].strip():
            fail("DRAFT_CONFLICT", "제출 의견과 저장 초안 본문이 다릅니다.")

    def begin(self, *, project_id, actor_id, boundary, submission, require_current_draft=False):
        """PROCESSING 선기록. HTTP 접수는 require_current_draft=True를 필수로 전달한다.

        기존 단독 원장 호출은 기본값으로 호환한다. 현재 권한/질문 조회는 락 밖에서
        호출자가 수행하며 여기서는 동일 DB 초안 판만 검사한다. 원키 replay는
        이미 접수된 판을 반환하므로 소비/수정된 현재 초안을 다시 요구하지 않는다.
        """
        if type(require_current_draft) is not bool:
            fail("INVALID", "초안 현재판 검증 여부는 명시적 bool이어야 합니다.", 422)
        identity, command = _identity(project_id, actor_id, boundary), _submission(submission)
        key, fingerprint = command["client_request_id"], digest(command)
        with self.transaction(write=True) as conn:
            prior = conn.execute("SELECT * FROM studio_hotl_submissions WHERE request_id=?", (key,)).fetchone()
            if prior is not None:
                value = self._unpack(self._row(conn, identity, key))
                if value["command_digest"] != fingerprint:
                    fail("IDEMPOTENCY_CONFLICT", "같은 요청 ID의 제출 내용이 다릅니다.")
                return value, False
            if require_current_draft:
                self._assert_current_draft(conn, identity, command)
            #: ★ 요청 키를 바꿔도 같은 초안 판으로 두 번 제출하지 않는다. 같은 사용자·문맥만 본다 —
            #:   타인의 본문/판본을 이 판정으로 노출하지 않는다.
            for row in conn.execute("""SELECT * FROM studio_hotl_submissions
                    WHERE project_id=? AND actor_id=? AND boundary_json=?""", identity).fetchall():
                if self._unpack(row)["input_draft"] == command["input_draft"]:
                    fail("DRAFT_ALREADY_SUBMITTED", "같은 저장 초안 판이 이미 제출됐습니다. 기존 요청 ID를 조회하십시오.")
            now = datetime.now(timezone.utc).isoformat()
            value, raw, record_digest = self._pack(dict(request_id=key, project_id=identity[0], actor_id=identity[1],
                task_id=command["task_id"], target=command["target"], feedback=command["feedback"],
                input_draft=command["input_draft"], command_digest=fingerprint,
                status="PROCESSING", result=None, created_at=now, updated_at=now), identity[2])
            conn.execute("INSERT INTO studio_hotl_submissions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (key, *identity, value["task_id"], value["status"], fingerprint, value["receipt_digest"], now, raw, record_digest))
            return value, True

    def get(self, *, project_id, actor_id, boundary, request_id):
        identity, key = _identity(project_id, actor_id, boundary), request_key(request_id)
        with self.transaction() as conn:
            return self._unpack(self._row(conn, identity, key))

    def finish(self, *, project_id, actor_id, boundary, request_id, outcome, result):
        identity, key = _identity(project_id, actor_id, boundary), request_key(request_id)
        if type(outcome) is not str or outcome not in OUTCOMES or type(result) is not dict:
            fail("INVALID", "명시적 종결 결과와 객체 본문이 필요합니다.", 422)
        result = json.loads(canonical(result))
        with self.transaction(write=True) as conn:
            row = self._row(conn, identity, key)
            previous = self._unpack(row)
            if previous["status"] != "PROCESSING":
                if previous["status"] == outcome and canonical(previous["result"]) == canonical(result):
                    return previous
                fail("TERMINAL_CONFLICT", "이미 종결된 제출의 결과는 변경할 수 없습니다.")
            now = max(datetime.now(timezone.utc), datetime.fromisoformat(previous["created_at"])).isoformat()
            value, raw, record_digest = self._pack({**previous, "status": outcome, "result": result, "updated_at": now}, identity[2])
            changed = conn.execute("""UPDATE studio_hotl_submissions SET status=?,receipt_digest=?,record_json=?,record_digest=?
                WHERE request_id=? AND status='PROCESSING' AND receipt_digest=? AND record_digest=?""",
                (outcome, value["receipt_digest"], raw, record_digest, key, row["receipt_digest"], row["record_digest"]))
            if changed.rowcount != 1:
                fail("CONFLICT", "제출 종결 상태가 변경됐습니다. 원키로 조회하십시오.")
            return value


def verify_consumption(row, receipt, *, expected_revision, expected_digest):
    """접수된 제출과 저장 초안을 대조한다. 접수 자체는 소비가 아니다.

    ⚠️ 종결되지 않았거나 접수되지 않은 제출로는 초안을 닫지 않는다. UNKNOWN은
    원키 조회만 제공하며 여기서 성공으로 바꾸지 않는다."""
    if receipt["status"] != "ACCEPTED":
        fail("SUBMISSION_UNCONFIRMED", "접수가 확정된 제출만 초안을 사용완료로 닫습니다. 초안을 보존합니다.", 503)
    content = validate_content(row["target"], row["content"])
    ref = receipt["input_draft"]
    if (receipt["project_id"] != row["project_id"] or receipt["actor_id"].casefold() != row["actor"]
            or receipt["target"] != row["target"]
            or ref != dict(draft_id=row["draft_id"], revision=expected_revision, digest=expected_digest)):
        fail("SUBMISSION_CONFLICT", "제출 기록의 사용자·대상·저장 초안이 다릅니다.")
    #: 일반 HOTL 만 여기서 본문을 맞춘다. 명확화는 접수 시점에 서버가 질문으로 재현해
    #: 대조를 끝냈다 — 차수가 지나가면 그 질문을 다시 읽을 수 없으므로 여기서 되풀이하지 않는다.
    if row["target"]["kind"] == "DECISION_COMMENT" and receipt["feedback"] != content["text"].strip():
        fail("SUBMISSION_CONFLICT", "제출 기록의 본문이 저장한 초안과 다릅니다.")
    if row["status"] == "DRAFT":
        if row["revision"] != expected_revision or row["digest"] != expected_digest:
            fail("DRAFT_CONFLICT", "제출한 초안 판본과 현재 초안이 다릅니다.")
    elif (row["status"] != "CONSUMED" or row.get("submission_id") != receipt["request_id"]
          or row["revision"] != expected_revision + 1):
        fail("DRAFT_CONFLICT", "제출 후 초안 상태가 변경되었습니다.")
    return dict(submission_id=receipt["request_id"], draft_id=row["draft_id"], draft_digest=expected_digest)
