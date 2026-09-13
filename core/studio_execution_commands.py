"""B5 실행 명령의 영속 접수증. 명령 실행·권한 판정·자동 재시도는 하지 않는다.

호출자는 principal/서버 프로젝트 소속/현재 상태를 확인하고 input을 정규화한다.
주입한 AdvisorStore의 연결·잠금만 사용하며 생성자/import에는 DB 접근이 없다.
HEAL_LIMIT은 이번 명령 저장소의 명시적 서버 한도이지 빌드 실패 차수 정책이 아니다.
HEAL은 HOTL_PENDING 반환도 보수적으로 한도를 사용한다. input으로 예산을 면제하지 않는다.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import uuid

from core.enterprise_context.process_schema import ProcessError


MAX_REQUEST_BYTES = 64 * 1024
MAX_RECORD_BYTES = 256 * 1024
HEAL_LIMIT = 3
OPERATIONS = frozenset({"START", "RESUME", "RESUME_QUOTA", "PAUSE", "STOP", "HEAL"})
EXECUTIONS = OPERATIONS - {"PAUSE", "STOP"}
OUTCOMES = frozenset({"ACCEPTED", "REJECTED", "UNKNOWN"})
INPUT_FIELDS = frozenset({"initial_idea", "master_data", "feedback", "error_log"})
TABLE = "studio_execution_commands"


class CommandStoreError(ProcessError):
    pass


def fail(code, message, status=409):
    raise CommandStoreError("STUDIO_COMMAND_" + code, message, status)


def canonical(value, *, limit=MAX_RECORD_BYTES):
    def check(item, depth=0):
        if depth > 64:
            raise ValueError("JSON depth")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("JSON key")
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("JSON type")
    try:
        check(value)
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(raw.encode("utf-8")) > limit:
            raise ValueError("JSON size")
        return raw
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise CommandStoreError("STUDIO_COMMAND_INVALID", "허용된 크기와 형식의 JSON이 필요합니다.", 422) from exc


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def request_key(value):
    try:
        if type(value) is not str or len(value) != 36:
            raise ValueError("UUID")
        key = str(uuid.UUID(value))
        if key != value.lower():
            raise ValueError("UUID canonical")
        return key
    except (ValueError, AttributeError) as exc:
        raise CommandStoreError("STUDIO_COMMAND_INVALID", "하이픈을 포함한 UUID 요청 ID가 필요합니다.", 422) from exc


def _request(value):
    if type(value) is not dict or set(value) != {"client_request_id", "operation", "task_id", "input"}:
        fail("INVALID", "실행 명령의 필수 필드만 전달하십시오.", 422)
    operation, task, content = value["operation"], value["task_id"], value["input"]
    if (type(operation) is not str or operation not in OPERATIONS or type(task) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", task) or type(content) is not dict
            or set(content) - INPUT_FIELDS
            or any(type(text) is not str or len(text) > MAX_REQUEST_BYTES for text in content.values())):
        fail("INVALID", "명령·task와 허용된 문자열 입력을 확인하십시오.", 422)
    command = {**value, "client_request_id": request_key(value["client_request_id"])}
    return json.loads(canonical(command, limit=MAX_REQUEST_BYTES))


def _identity(project_id, actor_id, boundary):
    if (type(project_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", project_id)
            or type(actor_id) is not str or not actor_id.strip() or len(actor_id) > 256
            or type(boundary) is not dict or not boundary):
        fail("INVALID", "서버 프로젝트·인증 사용자·문맥이 필요합니다.", 422)
    return project_id, actor_id.strip().casefold(), canonical(boundary, limit=MAX_REQUEST_BYTES)


_DDL = (
    """CREATE TABLE IF NOT EXISTS studio_execution_commands (
      request_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, actor_id TEXT NOT NULL,
      boundary_json TEXT NOT NULL, operation TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('PROCESSING','ACCEPTED','REJECTED','UNKNOWN')),
      command_digest TEXT NOT NULL, receipt_digest TEXT NOT NULL,
      created_at TEXT NOT NULL, record_json TEXT NOT NULL, record_digest TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS studio_execution_commands_project ON studio_execution_commands(project_id,created_at)",
)


class CommandStore:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def transaction(self, write=False):
        """동기 트랜잭션. 이 문맥 안에서 await/재진입/외부 실행을 하지 않는다."""
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
            raise CommandStoreError("STUDIO_COMMAND_STORAGE_UNAVAILABLE", "명령 기록을 확인하지 못했습니다. 요청 ID를 보존하십시오.", 503) from exc

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
            expected = {"request_id", "project_id", "actor_id", "operation", "task_id", "input", "command_digest",
                        "status", "result", "created_at", "updated_at", "receipt_digest"}
            if type(value) is not dict or set(value) != expected:
                raise ValueError("record schema")
            command = _request(dict(client_request_id=value["request_id"], operation=value["operation"],
                                    task_id=value["task_id"], input=value["input"]))
            identity = _identity(value["project_id"], value["actor_id"], payload["boundary"])
            if (identity != (row["project_id"], row["actor_id"], row["boundary_json"])
                    or value["actor_id"] != identity[1] or value["request_id"] != command["client_request_id"]
                    or any(value[key] != row[key] for key in
                           ("request_id", "project_id", "actor_id", "operation", "status", "command_digest", "receipt_digest", "created_at"))
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
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError, CommandStoreError) as exc:
            raise CommandStoreError("STUDIO_COMMAND_INTEGRITY", "명령 기록의 무결성을 확인하지 못했습니다. 원기록을 보존합니다.", 503) from exc

    def _row(self, conn, identity, key):
        row = conn.execute("SELECT * FROM studio_execution_commands WHERE request_id=?", (key,)).fetchone() if self._ready(conn) else None
        if row is None or (row["project_id"], row["actor_id"], row["boundary_json"]) != identity:
            fail("NOT_FOUND", "현재 사용자·문맥에서 명령 기록을 찾을 수 없습니다.", 404)
        return row

    @staticmethod
    def _pack(value, boundary_json):
        value = {**value, "receipt_digest": digest({key: child for key, child in value.items() if key != "receipt_digest"})}
        payload = dict(boundary=json.loads(boundary_json), record=value)
        return value, canonical(payload), digest(payload)

    def begin(self, *, project_id, actor_id, boundary, request):
        identity, command = _identity(project_id, actor_id, boundary), _request(request)
        key, fingerprint = command["client_request_id"], digest(command)
        with self.transaction(write=True) as conn:
            prior = conn.execute("SELECT * FROM studio_execution_commands WHERE request_id=?", (key,)).fetchone()
            if prior is not None:
                value = self._unpack(self._row(conn, identity, key))
                if value["command_digest"] != fingerprint:
                    fail("IDEMPOTENCY_CONFLICT", "같은 요청 ID의 명령 내용이 다릅니다.")
                return value, False
            # 모든 작성자·문맥의 프로젝트 기록을 검증한다. 타인의 본문/ID/횟수는 반환하지 않는다.
            records = [self._unpack(row) for row in conn.execute(
                "SELECT * FROM studio_execution_commands WHERE project_id=?", (identity[0],)).fetchall()]
            if command["operation"] in EXECUTIONS and any(row["status"] in {"PROCESSING", "UNKNOWN"} for row in records):
                fail("PROJECT_BUSY", "프로젝트에 결과 확인이 필요한 명령이 있습니다. 새 실행을 보류하십시오.")
            if command["operation"] == "HEAL" and sum(row["operation"] == "HEAL" for row in records) >= HEAL_LIMIT:
                fail("HEAL_BUDGET_EXHAUSTED", "프로젝트의 서버 복구 시도 한도에 도달했습니다.")
            now = datetime.now(timezone.utc).isoformat()
            value, raw, record_digest = self._pack(dict(request_id=key, project_id=identity[0], actor_id=identity[1],
                operation=command["operation"], task_id=command["task_id"], input=command["input"], command_digest=fingerprint,
                status="PROCESSING", result=None, created_at=now, updated_at=now), identity[2])
            conn.execute("INSERT INTO studio_execution_commands VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (key, *identity, value["operation"], value["status"], fingerprint, value["receipt_digest"], now, raw, record_digest))
            return value, True

    def get(self, *, project_id, actor_id, boundary, request_id):
        identity, key = _identity(project_id, actor_id, boundary), request_key(request_id)
        with self.transaction() as conn:
            return self._unpack(self._row(conn, identity, key))

    def assert_execution_clear(self, project_id):
        """권한 확인 뒤 레거시 실행에도 적용한다. 다른 사용자의 기록은 공개하지 않는다."""
        with self.transaction() as conn:
            if not self._ready(conn):
                return
            records = [self._unpack(row) for row in conn.execute(
                "SELECT * FROM studio_execution_commands WHERE project_id=?", (project_id,)).fetchall()]
            if any(row["status"] in {"PROCESSING", "UNKNOWN"} for row in records):
                fail("PROJECT_BUSY", "프로젝트에 결과 확인이 필요한 명령이 있습니다. 원요청을 먼저 조회하십시오.")

    def list(self, *, project_id, actor_id, boundary, limit=50):
        identity = _identity(project_id, actor_id, boundary)
        if type(limit) is not int or not 1 <= limit <= 100:
            fail("INVALID", "조회 개수는 1~100 정수여야 합니다.", 422)
        with self.transaction() as conn:
            if not self._ready(conn):
                return []
            rows = conn.execute("""SELECT * FROM studio_execution_commands
                WHERE project_id=? AND actor_id=? AND boundary_json=? ORDER BY created_at DESC,request_id DESC LIMIT ?""",
                (*identity, limit)).fetchall()
            return [self._unpack(row) for row in rows]

    def finish(self, *, project_id, actor_id, boundary, request_id, outcome, result):
        identity, key = _identity(project_id, actor_id, boundary), request_key(request_id)
        if type(outcome) is not str or outcome not in OUTCOMES or type(result) is not dict:
            fail("INVALID", "명시적 종결 결과와 객체 본문이 필요합니다.", 422)
        result = json.loads(canonical(result, limit=MAX_REQUEST_BYTES))
        with self.transaction(write=True) as conn:
            row = self._row(conn, identity, key)
            previous = self._unpack(row)
            if previous["status"] != "PROCESSING":
                if previous["status"] == outcome and canonical(previous["result"]) == canonical(result):
                    return previous
                fail("TERMINAL_CONFLICT", "이미 종결된 명령의 결과는 변경할 수 없습니다.")
            now = max(datetime.now(timezone.utc), datetime.fromisoformat(previous["created_at"])).isoformat()
            value, raw, record_digest = self._pack({**previous, "status": outcome, "result": result, "updated_at": now}, identity[2])
            changed = conn.execute("""UPDATE studio_execution_commands SET status=?,receipt_digest=?,record_json=?,record_digest=?
                WHERE request_id=? AND status='PROCESSING' AND receipt_digest=? AND record_digest=?""",
                (outcome, value["receipt_digest"], raw, record_digest, key, row["receipt_digest"], row["record_digest"]))
            if changed.rowcount != 1:
                fail("CONFLICT", "명령 종결 상태가 변경됐습니다. 원키로 조회하십시오.")
            return value
