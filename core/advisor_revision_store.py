"""B3 §8.5 초안 revision과 승격 operation의 저장 기반. 실행·권한 엔진이 아니다.

기본 ``RevisionStore(advisor_store)``는 주입한 AdvisorStore의 ``_connect``/``_lock``을
사용한다. import/생성자는 IO를 하지 않으며 기존 상담/blueprint 업무 행은 읽지도
쓰지도 않는다. 기본 모드의 최초 호출에서 ``advisor_v2_*`` 테이블만 준비한다.
읽기 전용 모드는 기존 DB를 mode=ro로 열며 초기화·복구하지 않는다.
SQLite의 WAL/SHM 보조 파일은 생길 수 있다. 모든 파일에 대한 물리적 무쓰기를 뜻하지 않는다.

신뢰 경계:
* 모든 메서드는 서버 내부 전용이다. main 서비스가 현재 PDP/선택 문맥/ProcessContext를
  검증한 뒤 인증 principal의 actor를 명시해야 한다. HTTP body를 **kwargs로 넘기지 않는다.
* 이 층은 exact boundary, 저장 시 작성자, operation의 행위자, 승인자 분리를 강제한다.
  다른 사람의 초안 조회/승인 적격성은 외부 PDP 책임이다(식별자만으로 허가하지 않는다).
* blueprint는 요구사항 내용만 받는다. 승인/소유/판본 메타는 별도 서버 필드다.
  process_ref는 서버가 검증한 DTO/초안 참조이며 이 모듈은 ECM 진위를 증명하지 않는다.
* save는 main이 검증·합성한 전체 blueprint를 받는다. HTTP patch를 이 층이 적용하지 않는다.
  command_digest는 서버가 정규화한 HTTP 명령의 SHA-256이며 클라이언트 값을 받지 않는다.
  replay_save도 현재 권한 검증 뒤 호출한다. 동적 ProcessContext를 다시 합성하기 전의 조회다.
* is_v2_project/get_for_project는 서버 내부 provenance 조회다. metadata/client의 actor나
  v2 marker를 신뢰하지 않는다. 문맥 없는 존재 여부를 외부 API/사용자에게 노출하지 않는다.
* advance의 read-back/원장 증거 역시 main이 실제 IO로 확인해야 한다. 이 층은 그 증거의
  형식/일관성만 검사한다. 파일·프로젝트·원장 이벤트를 직접 생성하지 않는다.

기존 1.0 계약/레거시 flow와 독립이다. UI/API 연결이나 B3 전체 완료를 뜻하지 않는다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
import uuid


class RevisionStoreError(ValueError):
    def __init__(self, reason_code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


STAGES = ("RESERVED", "PROVISIONING", "CONTEXT_WRITTEN", "LEDGER_PENDING", "COMPLETED",
          "FAILED_RETRYABLE", "FAILED_BLOCKED")
_NEXT = dict(zip(STAGES[:4], STAGES[1:5]))
_FAILURES = {"FAILED_RETRYABLE", "FAILED_BLOCKED"}
_BOUNDARY_KEYS = {"tenant_id", "context_root_id", "entity_mode", "scope_node_id"}
_AUTHORITY_FIELDS = {
    "actor", "author", "author_actor", "created_by", "created_at", "updated_at",
    "owner_actor", "owner_user_id", "owner_dept_id", "approved_by", "approved_at",
    "approved_revision_id", "approval", "decision_actor", "decision", "status",
    "draft_id", "revision_id", "revision", "version", "digest", "blueprint_id",
    "tenant_id", "context_root_id", "entity_mode", "scope_node_id", "enterprise_scope_id",
    "context_key", "process_context", "process_ref", "bootstrap_operation_id",
    "permitted_actions", "rejected_reason", "consultation_id", "command_digest",
    "runtime_document_version", "setup_status", "approved_blueprint_revision_id", "approved_blueprint_digest",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _json(value: Any) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise RevisionStoreError("ADVISOR_INPUT_INVALID", "유효한 JSON 값이 필요합니다.", 422) from exc
    if len(raw.encode("utf-8")) > 1_048_576:
        raise RevisionStoreError("ADVISOR_INPUT_INVALID", "저장 요청이 너무 큽니다.", 422)
    return raw


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, field: str, *, empty: bool = False, limit: int = 256) -> str:
    if not isinstance(value, str) or len(value) > limit or value != value.strip():
        raise RevisionStoreError("ADVISOR_INPUT_INVALID", f"{field} 형식이 잘못되었습니다.", 422)
    if (not value and not empty) or any(ord(char) < 32 for char in value):
        raise RevisionStoreError("ADVISOR_INPUT_INVALID", f"{field} 값이 필요합니다.", 422)
    return value


def _actor(value: Any) -> str:
    return _text(value, "actor").casefold()


def _reason(value: Any, field: str = "reason") -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > 4000
            or any(ord(char) < 32 and char not in "\r\n\t" for char in value)):
        raise RevisionStoreError("ADVISOR_INPUT_INVALID", f"{field}을 명시해야 합니다.", 422)
    return value


def _digest(value: Any, *, empty: bool = False) -> str:
    if empty and value == "":
        return ""
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise RevisionStoreError("ADVISOR_INPUT_INVALID", "SHA-256 digest가 필요합니다.", 422)
    return value


def _boundary(value: Any) -> tuple[dict, str]:
    if not isinstance(value, dict) or set(value) != _BOUNDARY_KEYS:
        raise RevisionStoreError("ADVISOR_CONTEXT_INVALID", "문맥 4개 키를 정확히 지정해야 합니다.", 422)
    context = {key: _text(value[key], key, empty=key == "scope_node_id")
               for key in sorted(_BOUNDARY_KEYS)}
    if context["entity_mode"] not in {"REAL", "VIRTUAL", "COMPETITOR_REFERENCE"}:
        raise RevisionStoreError("ADVISOR_CONTEXT_INVALID", "지원하지 않는 실행 문맥입니다.", 422)
    return context, _json(context)


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RevisionStoreError("ADVISOR_INPUT_INVALID", f"{name}은 JSON 객체여야 합니다.", 422)
    return json.loads(_json(value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _missing() -> None:
    raise RevisionStoreError("ADVISOR_NOT_FOUND", "현재 문맥에서 자료를 찾을 수 없습니다.", 404)


def _corrupt() -> None:
    raise RevisionStoreError("ADVISOR_STORAGE_INTEGRITY", "저장한 판본의 무결성을 확인할 수 없습니다.", 503)


_DDL = """
CREATE TABLE IF NOT EXISTS advisor_v2_drafts (
 draft_id TEXT PRIMARY KEY, boundary_json TEXT NOT NULL, owner_actor TEXT NOT NULL,
 head_revision INTEGER NOT NULL DEFAULT 0, head_revision_id TEXT NOT NULL DEFAULT '',
 head_digest TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS advisor_v2_revisions (
 revision_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES advisor_v2_drafts(draft_id),
 revision INTEGER NOT NULL CHECK(revision > 0), content_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('DRAFT','APPROVED','REJECTED')),
 digest TEXT NOT NULL, decision_actor TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
 decided_at TEXT NOT NULL DEFAULT '', decision_request_fingerprint TEXT NOT NULL DEFAULT '',
 UNIQUE(draft_id,revision)
);
CREATE TABLE IF NOT EXISTS advisor_v2_requests (
 boundary_json TEXT NOT NULL, actor TEXT NOT NULL, client_request_id TEXT NOT NULL,
 request_fingerprint TEXT NOT NULL, result_json TEXT NOT NULL, result_digest TEXT NOT NULL,
 PRIMARY KEY(boundary_json,actor,client_request_id)
);
CREATE TABLE IF NOT EXISTS advisor_v2_bootstraps (
 operation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL UNIQUE, event_id TEXT NOT NULL UNIQUE,
 approved_revision_id TEXT NOT NULL REFERENCES advisor_v2_revisions(revision_id),
 approved_digest TEXT NOT NULL, boundary_json TEXT NOT NULL, actor TEXT NOT NULL,
 client_request_id TEXT NOT NULL, request_fingerprint TEXT NOT NULL,
 process_semantic_digest TEXT NOT NULL, stage TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version > 0), resume_stage TEXT NOT NULL DEFAULT '',
 result_json TEXT NOT NULL, result_digest TEXT NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 CHECK(stage IN ('RESERVED','PROVISIONING','CONTEXT_WRITTEN','LEDGER_PENDING','COMPLETED',
                 'FAILED_RETRYABLE','FAILED_BLOCKED')),
 UNIQUE(boundary_json,actor,approved_revision_id,client_request_id)
);
CREATE TABLE IF NOT EXISTS advisor_v2_transitions (
 operation_id TEXT NOT NULL REFERENCES advisor_v2_bootstraps(operation_id),
 from_version INTEGER NOT NULL, request_fingerprint TEXT NOT NULL,
 result_json TEXT NOT NULL, result_digest TEXT NOT NULL,
 PRIMARY KEY(operation_id,from_version)
);
-- REPLACE의 암묵 DELETE는 recursive_triggers=OFF에서 DELETE trigger를 건너뛴다.
-- 충돌 해결 전에 INSERT 자체를 막아 모든 명시 PK/UNIQUE 정체성을 보호한다.
-- 최초 INSERT는 허용하며 레거시 테이블/connection PRAGMA는 변경하지 않는다.
CREATE TRIGGER IF NOT EXISTS advisor_v2_draft_insert_identity BEFORE INSERT ON advisor_v2_drafts
 WHEN EXISTS(SELECT 1 FROM advisor_v2_drafts WHERE draft_id=NEW.draft_id)
 BEGIN SELECT RAISE(ABORT,'advisor v2 insert identity collision'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_revision_insert_identity BEFORE INSERT ON advisor_v2_revisions
 WHEN EXISTS(SELECT 1 FROM advisor_v2_revisions WHERE revision_id=NEW.revision_id
             OR (draft_id=NEW.draft_id AND revision=NEW.revision))
 BEGIN SELECT RAISE(ABORT,'advisor v2 insert identity collision'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_request_insert_identity BEFORE INSERT ON advisor_v2_requests
 WHEN EXISTS(SELECT 1 FROM advisor_v2_requests WHERE boundary_json=NEW.boundary_json
             AND actor=NEW.actor AND client_request_id=NEW.client_request_id)
 BEGIN SELECT RAISE(ABORT,'advisor v2 insert identity collision'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_operation_insert_identity BEFORE INSERT ON advisor_v2_bootstraps
 WHEN EXISTS(SELECT 1 FROM advisor_v2_bootstraps WHERE operation_id=NEW.operation_id
             OR project_id=NEW.project_id OR event_id=NEW.event_id
             OR (boundary_json=NEW.boundary_json AND actor=NEW.actor
                 AND approved_revision_id=NEW.approved_revision_id AND client_request_id=NEW.client_request_id))
 BEGIN SELECT RAISE(ABORT,'advisor v2 insert identity collision'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_transition_insert_identity BEFORE INSERT ON advisor_v2_transitions
 WHEN EXISTS(SELECT 1 FROM advisor_v2_transitions WHERE operation_id=NEW.operation_id
             AND from_version=NEW.from_version)
 BEGIN SELECT RAISE(ABORT,'advisor v2 insert identity collision'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_draft_identity BEFORE UPDATE ON advisor_v2_drafts
 WHEN NEW.draft_id<>OLD.draft_id OR NEW.boundary_json<>OLD.boundary_json
   OR NEW.owner_actor<>OLD.owner_actor OR NEW.created_at<>OLD.created_at
 BEGIN SELECT RAISE(ABORT,'advisor draft identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_draft_no_delete BEFORE DELETE ON advisor_v2_drafts
 BEGIN SELECT RAISE(ABORT,'advisor draft deletion is forbidden'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_revision_immutable BEFORE UPDATE ON advisor_v2_revisions
 WHEN OLD.status<>'DRAFT' OR NEW.revision_id<>OLD.revision_id OR NEW.draft_id<>OLD.draft_id
   OR NEW.revision<>OLD.revision OR NEW.content_json<>OLD.content_json
   OR NEW.status NOT IN ('APPROVED','REJECTED')
 BEGIN SELECT RAISE(ABORT,'advisor revision content/decision is immutable'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_revision_no_delete BEFORE DELETE ON advisor_v2_revisions
 BEGIN SELECT RAISE(ABORT,'advisor revision deletion is forbidden'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_request_immutable BEFORE UPDATE ON advisor_v2_requests
 BEGIN SELECT RAISE(ABORT,'advisor request is immutable'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_request_no_delete BEFORE DELETE ON advisor_v2_requests
 BEGIN SELECT RAISE(ABORT,'advisor request deletion is forbidden'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_operation_identity BEFORE UPDATE ON advisor_v2_bootstraps
 WHEN OLD.stage IN ('COMPLETED','FAILED_BLOCKED') OR NEW.operation_id<>OLD.operation_id
   OR NEW.project_id<>OLD.project_id OR NEW.event_id<>OLD.event_id
   OR NEW.approved_revision_id<>OLD.approved_revision_id OR NEW.approved_digest<>OLD.approved_digest
   OR NEW.boundary_json<>OLD.boundary_json OR NEW.actor<>OLD.actor
   OR NEW.client_request_id<>OLD.client_request_id OR NEW.request_fingerprint<>OLD.request_fingerprint
   OR NEW.process_semantic_digest<>OLD.process_semantic_digest OR NEW.created_at<>OLD.created_at
 BEGIN SELECT RAISE(ABORT,'advisor bootstrap identity/final state is immutable'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_operation_no_delete BEFORE DELETE ON advisor_v2_bootstraps
 BEGIN SELECT RAISE(ABORT,'advisor bootstrap deletion is forbidden'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_transition_immutable BEFORE UPDATE ON advisor_v2_transitions
 BEGIN SELECT RAISE(ABORT,'advisor transition is immutable'); END;
CREATE TRIGGER IF NOT EXISTS advisor_v2_transition_no_delete BEFORE DELETE ON advisor_v2_transitions
 BEGIN SELECT RAISE(ABORT,'advisor transition deletion is forbidden'); END;
"""


class RevisionStore:
    """기존 AdvisorStore 연결을 주입한다. 메서드 호출 전 외부 권한 검사는 필수다."""

    def __init__(self, store, *, read_only=False):
        if not callable(getattr(store, "_connect", None)) or not hasattr(store, "_lock"):
            raise TypeError("AdvisorStore의 _connect와 _lock이 필요합니다.")
        self.store = store
        self.read_only = read_only
        self._prepared_for = None

    def _ensure(self):
        if self.read_only:
            raise RevisionStoreError("ADVISOR_READ_ONLY", "읽기 전용 저장소에서는 초기화·변경할 수 없습니다.", 503)
        with self.store._lock:
            if self._prepared_for == self.store.db_path:
                return
            conn = self.store._connect()
            try:
                conn.executescript("BEGIN IMMEDIATE;\n" + _DDL)
                conn.commit()
                self._prepared_for = self.store.db_path
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @contextmanager
    def _transaction(self, *, write=False):
        if self.read_only and write:
            raise RevisionStoreError("ADVISOR_READ_ONLY", "읽기 전용 저장소에서는 변경할 수 없습니다.", 503)
        try:
            if not self.read_only:
                self._ensure()
            with self.store._lock:
                if self.read_only:
                    # _connect의 디렉터리 생성·journal_mode 변경·schema 준비를 우회한다.
                    # immutable은 쓰지 않는다. 다른 연결이 커밋한 WAL도 정상 조회해야 한다.
                    path = Path(self.store.db_path).resolve()
                    if not path.is_file():
                        raise RevisionStoreError("ADVISOR_STORAGE_UNAVAILABLE", "기존 판본 저장소를 찾을 수 없습니다.", 503)
                    uri = path.as_uri() + "?mode=ro"
                    conn = sqlite3.connect(uri, uri=True, timeout=5)
                    conn.row_factory = sqlite3.Row
                else:
                    conn = self.store._connect()
                try:
                    # 독립 AdvisorStore 객체/프로세스의 경합도 직렬화한다.
                    conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
        except sqlite3.Error as exc:
            raise RevisionStoreError("ADVISOR_STORAGE_UNAVAILABLE", "초안 저장소를 사용할 수 없습니다.", 503) from exc

    @staticmethod
    def _revision(conn, revision_id, boundary_json):
        row = conn.execute(
            "SELECT r.*,d.boundary_json,d.owner_actor FROM advisor_v2_revisions r "
            "JOIN advisor_v2_drafts d ON d.draft_id=r.draft_id "
            "WHERE r.revision_id=? AND d.boundary_json=?", (revision_id, boundary_json)).fetchone()
        if not row:
            _missing()
        row = dict(row)
        try:
            content = json.loads(row["content_json"])
            if (content["draft_id"] != row["draft_id"] or content["revision_id"] != revision_id
                    or content["revision"] != row["revision"]
                    or _json(content["context_key"]) != boundary_json
                    or content["author_actor"] != row["owner_actor"]):
                _corrupt()
            decision = {"actor": row["decision_actor"], "reason": row["reason"], "at": row["decided_at"]}
            if row["digest"] != _hash({"content": content, "status": row["status"], "decision": decision}):
                _corrupt()
            if row["status"] == "DRAFT":
                if any(decision.values()) or row["decision_request_fingerprint"]:
                    _corrupt()
            elif not all(decision.values()) or not row["decision_request_fingerprint"]:
                _corrupt()
            if row["status"] == "APPROVED" and row["decision_actor"] == row["owner_actor"]:
                _corrupt()
            row["content"] = content
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise RevisionStoreError("ADVISOR_STORAGE_INTEGRITY", "판본을 읽을 수 없습니다.", 503) from exc
        return row

    @classmethod
    def _head(cls, conn, draft_id, boundary_json):
        head = conn.execute("SELECT * FROM advisor_v2_drafts WHERE draft_id=? AND boundary_json=?",
                            (draft_id, boundary_json)).fetchone()
        if not head:
            _missing()
        head = dict(head)
        row = cls._revision(conn, head["head_revision_id"], boundary_json)
        newest = conn.execute("SELECT MAX(revision) FROM advisor_v2_revisions WHERE draft_id=?", (draft_id,)).fetchone()[0]
        if (row["draft_id"] != draft_id or row["revision"] != head["head_revision"]
                or newest != head["head_revision"] or row["digest"] != head["head_digest"]):
            _corrupt()
        return head, row

    @staticmethod
    def _public(row):
        content = row["content"]
        return {**content, "digest": row["digest"], "status": row["status"],
                "approved_revision_id": row["revision_id"] if row["status"] == "APPROVED" else "",
                "decision_actor": row["decision_actor"], "reason": row["reason"],
                "decided_at": row["decided_at"]}

    @staticmethod
    def _stored_result(row):
        try:
            result = json.loads(row["result_json"])
            if not isinstance(result, dict) or _hash(result) != row["result_digest"]:
                _corrupt()
            return result
        except (TypeError, json.JSONDecodeError) as exc:
            raise RevisionStoreError("ADVISOR_STORAGE_INTEGRITY", "저장한 결과를 읽을 수 없습니다.", 503) from exc

    def _replay_save(self, conn, key, actor, request_id, request_fp):
        previous = conn.execute(
            "SELECT * FROM advisor_v2_requests WHERE boundary_json=? AND actor=? AND client_request_id=?",
            (key, actor, request_id)).fetchone()
        if not previous:
            return None
        if previous["request_fingerprint"] != request_fp:
            raise RevisionStoreError("ADVISOR_IDEMPOTENCY_CONFLICT", "같은 요청 키의 내용이 다릅니다.")
        result = self._stored_result(previous)
        try:
            head, _ = self._head(conn, result["draft_id"], key)
            if head["owner_actor"] != actor:
                _missing()
            row = self._revision(conn, result["revision_id"], key)
            # 이후 승인/새 편집이 있어도 최초 save의 DRAFT 결과를 반환한다.
            # 단순 캐시 해시뿐 아니라 실제 불변 content/현재 head 소유자까지 검증한다.
            original_digest = _hash({"content": row["content"], "status": "DRAFT",
                                     "decision": {"actor": "", "reason": "", "at": ""}})
            original = {**row["content"], "digest": original_digest, "status": "DRAFT",
                        "approved_revision_id": "", "decision_actor": "", "reason": "", "decided_at": ""}
            if result != original:
                _corrupt()
        except (KeyError, TypeError) as exc:
            raise RevisionStoreError("ADVISOR_STORAGE_INTEGRITY", "저장 요청의 원래 판본을 확인할 수 없습니다.", 503) from exc
        return result

    def replay_save(self, *, boundary: dict, actor: str, client_request_id: str,
                    command_digest: str) -> dict | None:
        """현재 PDP 검사 후, HTTP patch 적용/동적 문맥 합성 전에 원래 결과를 조회한다.

        서버만 계산한 소문자 hex SHA-256(64자리)을 받는다. 미등록 키만 None;
        다른 명령은 409, 저장 장애/무결성 오류는 성공이나 미등록으로 접지 않는다.
        조회 후 save 사이 경합은 save의 동일 write transaction 내 재검사/CAS가 닫는다.
        """
        _, key = _boundary(boundary)
        actor = _actor(actor)
        request_id = _text(client_request_id, "client_request_id")
        command_digest = _digest(command_digest)
        with self._transaction() as conn:
            return self._replay_save(conn, key, actor, request_id,
                                     _hash({"command_digest": command_digest}))

    def save(self, *, boundary: dict, actor: str, draft_id: str = "", expected_revision: int,
             expected_digest: str, blueprint: dict, client_request_id: str,
             process_ref: dict | None = None, command_digest: str = "") -> dict:
        """전체 요구사항을 새 revision으로 저장한다. 동일 요청 재전송은 최초 결과를 준다.

        새 초안은 draft_id='', expected_revision=0, expected_digest=''.
        승인 뒤 편집에는 승인 응답의 새 digest를 사용한다. 승인 직전 digest는 stale이다.
        command_digest가 있으면 서버의 원 HTTP 명령을 멱등 기준으로 삼는다. 클라이언트가
        임의로 지정하게 해서는 안 된다. 미지정 시 기존 전체 본문 fingerprint 계약을 유지한다.
        """
        context, key = _boundary(boundary)
        actor = _actor(actor)
        draft_id = _text(draft_id, "draft_id", empty=True)
        request_id = _text(client_request_id, "client_request_id")
        command_digest = _digest(command_digest, empty=True)
        if type(expected_revision) is not int or expected_revision < 0:
            raise RevisionStoreError("ADVISOR_INPUT_INVALID", "expected_revision이 잘못되었습니다.", 422)
        _digest(expected_digest, empty=expected_revision == 0)
        if (not draft_id) != (expected_revision == 0) or (expected_revision == 0 and expected_digest):
            raise RevisionStoreError("ADVISOR_INPUT_INVALID", "신규 초안은 빈 ID/digest와 revision=0이 필요합니다.", 422)
        blueprint = _object(blueprint, "blueprint")
        if _AUTHORITY_FIELDS & set(blueprint):
            raise RevisionStoreError("ADVISOR_AUTHORITY_FIELDS_FORBIDDEN", "blueprint에는 승인·소유·판본 필드를 넣을 수 없습니다.", 422)
        ref = _object(process_ref, "process_ref") if process_ref is not None else None
        if ref is not None and "context_key" in ref and _boundary(ref["context_key"])[1] != key:
            raise RevisionStoreError("ADVISOR_CONTEXT_MISMATCH", "업무 참조의 문맥이 다릅니다.", 422)
        request_fp = (_hash({"command_digest": command_digest}) if command_digest else
                      _hash({"draft_id": draft_id, "revision": expected_revision, "digest": expected_digest,
                             "blueprint": blueprint, "process_ref": ref}))
        with self._transaction(write=True) as conn:
            previous = self._replay_save(conn, key, actor, request_id, request_fp)
            if previous is not None:
                return previous
            if draft_id:
                head, _ = self._head(conn, draft_id, key)
                if head["owner_actor"] != actor:
                    _missing()
                if head["head_revision"] != expected_revision or head["head_digest"] != expected_digest:
                    raise RevisionStoreError("ADVISOR_REVISION_CONFLICT", "초안이 변경되었습니다. 입력을 보존하고 최신판을 확인하십시오.")
            else:
                draft_id = _uid("adv")
                conn.execute("INSERT INTO advisor_v2_drafts(draft_id,boundary_json,owner_actor,created_at) VALUES(?,?,?,?)",
                             (draft_id, key, actor, _now()))
            revision_id = _uid("avr")
            revision = expected_revision + 1
            content = {"schema_version": 1, "draft_id": draft_id, "revision_id": revision_id,
                       "revision": revision, "context_key": context, "author_actor": actor,
                       "blueprint": blueprint, "process_ref": ref, "created_at": _now()}
            digest = _hash({"content": content, "status": "DRAFT", "decision": {"actor": "", "reason": "", "at": ""}})
            conn.execute("INSERT INTO advisor_v2_revisions(revision_id,draft_id,revision,content_json,status,digest) VALUES(?,?,?,?,'DRAFT',?)",
                         (revision_id, draft_id, revision, _json(content), digest))
            changed = conn.execute("UPDATE advisor_v2_drafts SET head_revision=?,head_revision_id=?,head_digest=? "
                                   "WHERE draft_id=? AND head_revision=? AND head_digest=?",
                                   (revision, revision_id, digest, draft_id, expected_revision, expected_digest))
            if changed.rowcount != 1:
                raise RevisionStoreError("ADVISOR_REVISION_CONFLICT", "초안 저장이 다른 변경과 충돌했습니다.")
            result = self._public(self._revision(conn, revision_id, key))
            conn.execute("INSERT INTO advisor_v2_requests VALUES(?,?,?,?,?,?)",
                         (key, actor, request_id, request_fp, _json(result), _hash(result)))
            return result

    def decide(self, *, boundary: dict, actor: str, draft_id: str, expected_revision: int,
               draft_digest: str, decision: str, reason: str) -> dict:
        """현재 DRAFT만 확정. 외부 PDP 승인권 검사 필수. 같은 결정 재전송은 원 승인판 반환."""
        _, key = _boundary(boundary)
        actor = _actor(actor)
        draft_id = _text(draft_id, "draft_id")
        _digest(draft_digest)
        if type(expected_revision) is not int or expected_revision < 1:
            raise RevisionStoreError("ADVISOR_INPUT_INVALID", "판본 번호가 필요합니다.", 422)
        decision = _text(decision, "decision").upper()
        if decision not in {"APPROVED", "REJECTED"}:
            raise RevisionStoreError("ADVISOR_INPUT_INVALID", "APPROVED 또는 REJECTED만 가능합니다.", 422)
        reason = _reason(reason)
        request_fp = _hash({"draft_id": draft_id, "revision": expected_revision, "digest": draft_digest,
                            "decision": decision, "reason": reason, "actor": actor, "boundary": key})
        with self._transaction(write=True) as conn:
            head, current = self._head(conn, draft_id, key)
            candidate = conn.execute("SELECT revision_id FROM advisor_v2_revisions WHERE draft_id=? AND revision=?",
                                     (draft_id, expected_revision)).fetchone()
            if not candidate:
                raise RevisionStoreError("ADVISOR_REVISION_CONFLICT", "요청한 판본이 현재 초안이 아닙니다.")
            row = self._revision(conn, candidate["revision_id"], key)
            if row["status"] != "DRAFT":
                if row["decision_request_fingerprint"] == request_fp:
                    return self._public(row)
                raise RevisionStoreError("ADVISOR_DECISION_CONFLICT", "이미 확정된 판본을 변경할 수 없습니다.")
            if current["revision"] != expected_revision or current["digest"] != draft_digest:
                raise RevisionStoreError("ADVISOR_REVISION_CONFLICT", "현재 초안과 검토한 판본이 다릅니다.")
            if decision == "APPROVED" and head["owner_actor"] == actor:
                raise RevisionStoreError("ADVISOR_SELF_APPROVAL_FORBIDDEN", "초안 작성자는 자기 판본을 승인할 수 없습니다.", 403)
            when = _now()
            digest = _hash({"content": row["content"], "status": decision,
                            "decision": {"actor": actor, "reason": reason, "at": when}})
            updated = conn.execute("UPDATE advisor_v2_revisions SET status=?,digest=?,decision_actor=?,reason=?,decided_at=?,decision_request_fingerprint=? "
                                   "WHERE revision_id=? AND status='DRAFT' AND digest=?",
                                   (decision, digest, actor, reason, when, request_fp, row["revision_id"], draft_digest))
            changed = conn.execute("UPDATE advisor_v2_drafts SET head_digest=? WHERE draft_id=? AND head_revision=? AND head_digest=?",
                                   (digest, draft_id, expected_revision, draft_digest))
            if updated.rowcount != 1 or changed.rowcount != 1:
                raise RevisionStoreError("ADVISOR_REVISION_CONFLICT", "승인과 편집이 충돌했습니다.")
            return self._public(self._revision(conn, row["revision_id"], key))

    @staticmethod
    def _bootstrap_ref(row, key, semantic_digest):
        ref = row["content"].get("process_ref")
        if not isinstance(ref, dict) or not ref:
            raise RevisionStoreError("ADVISOR_PROCESS_CONTEXT_REQUIRED", "승격에는 승인된 업무 문맥이 필요합니다.", 422)
        if ref.get("state", "APPROVED") != "APPROVED" or ref.get("status", "APPROVED") != "APPROVED":
            raise RevisionStoreError("ADVISOR_PROCESS_CONTEXT_REQUIRED", "업무 초안 참조로 프로젝트를 승격할 수 없습니다.")
        if _boundary(ref.get("context_key"))[1] != key:
            raise RevisionStoreError("ADVISOR_CONTEXT_MISMATCH", "업무 참조 문맥이 다릅니다.")
        ids = ref.get("process_ids")
        if (not ref.get("profile_id") or not ref.get("configuration_id") or not isinstance(ids, list)
                or not ids or any(not isinstance(v, str) or not v.strip() for v in ids)
                or len(set(ids)) != len(ids)):
            raise RevisionStoreError("ADVISOR_PROCESS_CONTEXT_REQUIRED", "승인 profile/process 참조가 필요합니다.", 422)
        _text(ref["profile_id"], "profile_id")
        _text(ref["configuration_id"], "configuration_id")
        for process_id in ids:
            _text(process_id, "process_id")
        if ref.get("process_semantic_fingerprint") != semantic_digest:
            raise RevisionStoreError("ADVISOR_PROCESS_SEMANTIC_CONFLICT", "승인한 업무 의미와 승격 요청이 다릅니다.")

    def reserve_bootstrap(self, *, approved_revision_id: str, digest: str, context_key: dict,
                          actor: str, client_request_id: str, semantic_digest: str) -> dict:
        """프로젝트/event ID만 예약한다. 실제 프로젝트·원장은 만들지 않는다.

        같은 요청의 재전송은 현재 operation(항상 같은 IDs)을 반환한다. 권한/현재 ECM
        검증은 main이 재시도에도 수행해야 한다. 새 초안이 생겨도 과거 승인판은 유지된다.
        """
        _, key = _boundary(context_key)
        actor = _actor(actor)
        _text(approved_revision_id, "approved_revision_id")
        _digest(digest)
        _digest(semantic_digest)
        request_id = _text(client_request_id, "client_request_id")
        fp = _hash({"revision_id": approved_revision_id, "digest": digest, "context": key,
                    "actor": actor, "semantic_digest": semantic_digest})
        with self._transaction(write=True) as conn:
            row = self._revision(conn, approved_revision_id, key)
            if row["status"] != "APPROVED":
                raise RevisionStoreError("ADVISOR_APPROVAL_REQUIRED", "승인된 Blueprint 판본만 승격할 수 있습니다.")
            if row["digest"] != digest:
                raise RevisionStoreError("ADVISOR_REVISION_CONFLICT", "승인 판본의 digest가 다릅니다.")
            self._bootstrap_ref(row, key, semantic_digest)
            previous = conn.execute("SELECT * FROM advisor_v2_bootstraps WHERE boundary_json=? AND actor=? AND approved_revision_id=? AND client_request_id=?",
                                    (key, actor, approved_revision_id, request_id)).fetchone()
            if previous:
                if previous["request_fingerprint"] != fp:
                    raise RevisionStoreError("ADVISOR_IDEMPOTENCY_CONFLICT", "같은 승격 요청 키의 내용이 다릅니다.")
                return self._operation(conn, previous["operation_id"], key, actor)
            operation_id, project_id, event_id = _uid("bop"), _uid("prj"), _uid("dle")
            when = _now()
            result = {"project_id": project_id, "event_id": event_id}
            conn.execute("INSERT INTO advisor_v2_bootstraps(operation_id,project_id,event_id,approved_revision_id,approved_digest,boundary_json,actor,client_request_id,request_fingerprint,process_semantic_digest,stage,version,result_json,result_digest,created_at,updated_at) "
                         "VALUES(?,?,?,?,?,?,?,?,?,?,'RESERVED',1,?,?,?,?)",
                         (operation_id, project_id, event_id, approved_revision_id, digest, key, actor,
                          request_id, fp, semantic_digest, _json(result), _hash(result), when, when))
            return self._operation(conn, operation_id, key, actor)

    def _operation(self, conn, operation_id, key, actor, *, verify_history=True):
        row = conn.execute("SELECT * FROM advisor_v2_bootstraps WHERE operation_id=? AND boundary_json=? AND actor=?",
                           (operation_id, key, actor)).fetchone()
        if not row:
            _missing()
        result = self._stored_result(row)
        approved = self._revision(conn, row["approved_revision_id"], key)
        if approved["status"] != "APPROVED" or approved["digest"] != row["approved_digest"]:
            _corrupt()
        if result.get("project_id") != row["project_id"] or result.get("event_id") != row["event_id"]:
            _corrupt()
        if "ledger_event_id" in result and result["ledger_event_id"] != row["event_id"]:
            _corrupt()
        expected = _hash({"revision_id": row["approved_revision_id"], "digest": row["approved_digest"],
                          "context": key, "actor": actor, "semantic_digest": row["process_semantic_digest"]})
        if expected != row["request_fingerprint"]:
            _corrupt()
        self._bootstrap_ref(approved, key, row["process_semantic_digest"])
        out = {"operation_id": row["operation_id"], "project_id": row["project_id"], "event_id": row["event_id"],
                "approved_revision_id": row["approved_revision_id"], "approved_digest": row["approved_digest"],
                "context_key": json.loads(key), "actor": actor, "process_semantic_digest": row["process_semantic_digest"],
                "stage": row["stage"], "version": row["version"], "resume_stage": row["resume_stage"],
                "result": result, "created_at": row["created_at"], "updated_at": row["updated_at"]}
        if verify_history:
            # 초기 구현에서 잘못된 ledger ID가 중간 단계에 저장된 이력도 성공/재개로
            # 반환하지 않는다. 한 read snapshot에서 과거 결과의 해시/고정 ID를 확인한다.
            latest, count = None, 0
            events = conn.execute("SELECT * FROM advisor_v2_transitions WHERE operation_id=? ORDER BY from_version",
                                  (operation_id,))
            try:
                for event in events:
                    count += 1
                    historical = self._stored_result(event)
                    proof = historical.get("result")
                    if (event["from_version"] != count or historical.get("version") != count + 1
                            or historical.get("operation_id") != operation_id
                            or historical.get("event_id") != row["event_id"]
                            or historical.get("project_id") != row["project_id"]
                            or not isinstance(proof, dict)
                            or proof.get("event_id") != row["event_id"]
                            or proof.get("project_id") != row["project_id"]
                            or ("ledger_event_id" in proof and proof["ledger_event_id"] != row["event_id"])):
                        _corrupt()
                    latest = historical
            finally:
                events.close()
            if count != row["version"] - 1:
                _corrupt()
            if row["version"] == 1:
                if (row["stage"] != "RESERVED" or row["resume_stage"] or row["created_at"] != row["updated_at"]
                        or result != {"project_id": row["project_id"], "event_id": row["event_id"]}):
                    _corrupt()
            else:
                if latest != out:
                    _corrupt()
        return out

    def advance(self, *, operation_id: str, boundary: dict, actor: str, current_stage: str,
                next_stage: str, expected_version: int, result: dict) -> dict:
        """단계+version CAS. 동일 전이 재전송은 그 전이의 고정 결과를 반환한다.

        CONTEXT_WRITTEN: 실제 read-back한 meta/state의 고정 blueprint/process 참조 투영
        digest(meta_digest/state_digest). 계속 바뀌는 전체 프로젝트 파일 해시가 아니다.
        LEDGER_PENDING: 예약된 event_id를 사용(원장 전송은 main).
        ledger_event_id를 제공하는 모든 단계에서 예약 event_id와 일치해야 한다.
        COMPLETED: ledger_event_id==예약 event_id, ledger_acknowledged=True.
        실패: error_code/error_message. RETRYABLE은 resume_stage로만 복구하며 BLOCKED는
        자동 재개하지 않는다. 근거들은 누적되고 성공 뒤에는 바뀌지 않는다.
        """
        _, key = _boundary(boundary)
        actor = _actor(actor)
        _text(operation_id, "operation_id")
        if current_stage not in STAGES or next_stage not in STAGES or type(expected_version) is not int or expected_version < 1:
            raise RevisionStoreError("ADVISOR_INPUT_INVALID", "단계와 expected_version을 확인하십시오.", 422)
        result = _object(result, "result")
        if _AUTHORITY_FIELDS & set(result):
            raise RevisionStoreError("ADVISOR_AUTHORITY_FIELDS_FORBIDDEN", "전이 결과에는 권한·판본 필드를 넣을 수 없습니다.", 422)
        for name in ("meta_digest", "state_digest"):
            if name in result:
                _digest(result[name])
        if "ledger_event_id" in result:
            _text(result["ledger_event_id"], "ledger_event_id")
        if "ledger_acknowledged" in result and (next_stage != "COMPLETED" or result["ledger_acknowledged"] is not True):
            raise RevisionStoreError("ADVISOR_LEDGER_ACK_REQUIRED", "실제 원장 접수 확인은 완료 전이에서만 기록합니다.")
        fp = _hash({"current_stage": current_stage, "next_stage": next_stage, "version": expected_version, "result": result})
        with self._transaction(write=True) as conn:
            op = self._operation(conn, operation_id, key, actor)
            if "ledger_event_id" in result and result["ledger_event_id"] != op["event_id"]:
                raise RevisionStoreError("ADVISOR_LEDGER_ACK_REQUIRED", "예약한 원장 사건과 다른 ID는 저장할 수 없습니다.")
            previous = conn.execute("SELECT * FROM advisor_v2_transitions WHERE operation_id=? AND from_version=?",
                                    (operation_id, expected_version)).fetchone()
            if previous:
                if previous["request_fingerprint"] != fp:
                    raise RevisionStoreError("ADVISOR_OPERATION_CONFLICT", "같은 단계 전이의 내용이 다릅니다.")
                return self._stored_result(previous)
            if op["stage"] != current_stage or op["version"] != expected_version:
                raise RevisionStoreError("ADVISOR_OPERATION_CONFLICT", "승격 operation이 변경되었습니다.")
            resume = op["resume_stage"]
            legal = (_NEXT.get(current_stage) == next_stage
                     or (current_stage in _NEXT and next_stage in _FAILURES)
                     or (current_stage == "FAILED_RETRYABLE" and next_stage == resume))
            if not legal:
                raise RevisionStoreError("ADVISOR_STAGE_INVALID", "허용되지 않는 승격 단계 전이입니다.")
            if next_stage in _FAILURES:
                _text(result.get("error_code"), "error_code")
                _reason(result.get("error_message"), "error_message")
                resume = current_stage
            elif current_stage == "FAILED_RETRYABLE":
                resume = ""
            merged = {**op["result"], **result}
            if current_stage == "FAILED_RETRYABLE":
                # 실패 증거는 불변 전이 이력에 남는다. 현재 성공/재개 결과와 혼동하지 않는다.
                merged.pop("error_code", None)
                merged.pop("error_message", None)
            if merged["project_id"] != op["project_id"] or merged["event_id"] != op["event_id"]:
                raise RevisionStoreError("ADVISOR_OPERATION_CONFLICT", "예약한 project/event ID는 바꿀 수 없습니다.")
            # 이미 확인한 증거를 나중 단계가 조용히 교체할 수 없다.
            for name in ("meta_digest", "state_digest", "ledger_event_id", "ledger_acknowledged"):
                if name in op["result"] and name in result and op["result"][name] != result[name]:
                    raise RevisionStoreError("ADVISOR_OPERATION_CONFLICT", "이미 기록한 승격 증거가 다릅니다.")
            if next_stage in {"CONTEXT_WRITTEN", "LEDGER_PENDING", "COMPLETED"}:
                _digest(merged.get("meta_digest"))
                _digest(merged.get("state_digest"))
            if next_stage == "COMPLETED" and (merged.get("ledger_event_id") != op["event_id"]
                                               or merged.get("ledger_acknowledged") is not True):
                raise RevisionStoreError("ADVISOR_LEDGER_ACK_REQUIRED", "고정 원장 사건의 접수 확인이 필요합니다.")
            updated = conn.execute("UPDATE advisor_v2_bootstraps SET stage=?,version=version+1,resume_stage=?,result_json=?,result_digest=?,updated_at=? "
                                   "WHERE operation_id=? AND version=? AND stage=?",
                                   (next_stage, resume, _json(merged), _hash(merged), _now(), operation_id, expected_version, current_stage))
            if updated.rowcount != 1:
                raise RevisionStoreError("ADVISOR_OPERATION_CONFLICT", "승격 단계 전이가 충돌했습니다.")
            out = self._operation(conn, operation_id, key, actor, verify_history=False)
            conn.execute("INSERT INTO advisor_v2_transitions VALUES(?,?,?,?,?)",
                         (operation_id, expected_version, fp, _json(out), _hash(out)))
            return out

    def is_v2_project(self, project_id: str) -> bool:
        """서버 내부 cohort oracle. 예약 행이 있으면 상태/metadata와 무관하게 True.

        외부 노출/권한 판단에 사용하지 않는다. 손상 op도 legacy로 내리지 않도록 존재만
        확인한다. 이후 현재 PDP + get_for_project 검증 필수. DB 장애는 False가 아니다.
        기본 모드는 최초 호출에 스키마를 준비한다. 읽기 전용은 v2 스키마가 전혀 없는
        정상 legacy DB만 미등록으로 판정하며 부분 스키마는 장애로 거절한다. DB 미등록이라도
        meta/state가 v2를 표방하면 main이 fail closed 해야 한다(자동 1.0 폴백 금지).
        """
        project_id = _text(project_id, "project_id")
        with self._transaction() as conn:
            if self.read_only:
                # 조회에 쓰이는 모든 열을 검사한다. 이름만 남은 손상 테이블은 legacy가 아니다.
                expected = {
                    "advisor_v2_drafts": "draft_id boundary_json owner_actor head_revision head_revision_id head_digest created_at",
                    "advisor_v2_revisions": "revision_id draft_id revision content_json status digest decision_actor reason decided_at decision_request_fingerprint",
                    "advisor_v2_requests": "boundary_json actor client_request_id request_fingerprint result_json result_digest",
                    "advisor_v2_bootstraps": "operation_id project_id event_id approved_revision_id approved_digest boundary_json actor client_request_id request_fingerprint process_semantic_digest stage version resume_stage result_json result_digest created_at updated_at",
                    "advisor_v2_transitions": "operation_id from_version request_fingerprint result_json result_digest",
                }
                rows = conn.execute("SELECT name,type FROM sqlite_master WHERE name GLOB 'advisor_v2_*'").fetchall()
                if not rows:
                    legacy = {row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('consultations','solution_blueprints')")}
                    if legacy != {"consultations", "solution_blueprints"}:
                        raise RevisionStoreError("ADVISOR_STORAGE_UNAVAILABLE", "기존 상담 저장소 구조를 확인할 수 없습니다.", 503)
                    return False
                tables = {row["name"] for row in rows if row["type"] == "table"}
                if not set(expected).issubset(tables):
                    raise RevisionStoreError("ADVISOR_STORAGE_UNAVAILABLE", "판본 저장소 구조를 확인할 수 없습니다.", 503)
                for table, fields in expected.items():
                    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                    if not set(fields.split()).issubset(columns):
                        raise RevisionStoreError("ADVISOR_STORAGE_UNAVAILABLE", "판본 저장소 열을 확인할 수 없습니다.", 503)
            return conn.execute("SELECT 1 FROM advisor_v2_bootstraps WHERE project_id=?",
                                (project_id,)).fetchone() is not None

    def boundary_of(self, *, draft_id: str) -> dict | None:
        """[DRAFT-ENTRY-01] 초안이 **자기 경계를 들고 있다.** 그 경계만 돌려준다.

        ★★★ 진입 확인은 「이 초안이 어느 문맥의 것인가」를 먼저 알아야 하는데, 기존
          `get()` 은 **경계를 인자로 받아** 그 경계와 일치하는 행만 준다. 그래서
          호출자가 경계를 «지어내야» 했고, 지어낸 값이 사용자의 현재 선택과 다르면
          다른 문맥의 초안을 여는 길이 생긴다.

        ⚠️ **내용도 판본도 주지 않는다.** 소유 4키와 소유자뿐이다 — 판정은 호출부가
          기존 권한 층(`_authorize`)에 맡기고, 여기서 권한을 새로 만들지 않는다.
        ⚠️ 없으면 `None` 이다. 호출부가 **다른 거절과 같은 문구**로 접어야 한다 —
          여기서 「없다」와 「못 본다」를 구분해 주면 존재가 응답으로 샌다."""
        draft_id = _text(draft_id, "draft_id")
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT boundary_json, owner_actor FROM advisor_v2_drafts WHERE draft_id=?",
                (draft_id,)).fetchone()
        if row is None:
            return None
        try:
            boundary = json.loads(row["boundary_json"])
        except Exception:
            return None
        if not isinstance(boundary, dict) or set(boundary) != _BOUNDARY_KEYS:
            return None
        return {"boundary": boundary, "owner_actor": row["owner_actor"]}

    def get_for_project(self, *, boundary: dict, project_id: str) -> dict | None:
        """현재 PDP가 허용한 exact boundary의 현재 operation을 서버 내부에서 조회한다.

        미등록만 None; 다른 경계는 404. actor는 client/metadata 대신 저장된 예약 행에서
        얻으며 동일 read transaction에서 _operation의 승인판/이력 무결성을 검증한다.
        RESERVED/실패 상태도 반환하므로 실행 허용 단계(COMPLETED) 확인은 main 책임이다.
        """
        _, key = _boundary(boundary)
        project_id = _text(project_id, "project_id")
        with self._transaction() as conn:
            identity = conn.execute(
                "SELECT operation_id,boundary_json,actor FROM advisor_v2_bootstraps WHERE project_id=?",
                (project_id,)).fetchone()
            if not identity:
                return None
            if identity["boundary_json"] != key:
                _missing()
            return self._operation(conn, identity["operation_id"], key, identity["actor"])

    def get(self, *, boundary: dict, actor: str, draft_id: str = "", revision: int | None = None,
            approved_revision_id: str = "", operation_id: str = "") -> dict:
        """서버가 가시성을 검증한 뒤 조회한다. operation은 예약 actor만 조회할 수 있다.

        초안/승인판은 같은 boundary의 적격 검토자도 읽어야 하므로 owner-only가 아니다.
        다른 사용자 자료의 조회 허가는 main PDP가 담당한다. 식별자는 하나만 지정한다.
        """
        _, key = _boundary(boundary)
        actor = _actor(actor)
        for name, value in (("draft_id", draft_id), ("approved_revision_id", approved_revision_id), ("operation_id", operation_id)):
            _text(value, name, empty=True)
        if sum(bool(v) for v in (draft_id, approved_revision_id, operation_id)) != 1:
            raise RevisionStoreError("ADVISOR_INPUT_INVALID", "조회 대상 식별자를 하나만 지정하십시오.", 422)
        if revision is not None and (not draft_id or type(revision) is not int or revision < 1):
            raise RevisionStoreError("ADVISOR_INPUT_INVALID", "초안 판본 조회 형식이 잘못되었습니다.", 422)
        with self._transaction() as conn:
            if operation_id:
                return self._operation(conn, operation_id, key, actor)
            if approved_revision_id:
                row = self._revision(conn, approved_revision_id, key)
                if row["status"] != "APPROVED":
                    _missing()
                return self._public(row)
            _, row = self._head(conn, draft_id, key)
            if revision is not None:
                found = conn.execute("SELECT revision_id FROM advisor_v2_revisions WHERE draft_id=? AND revision=?",
                                     (draft_id, revision)).fetchone()
                if not found:
                    _missing()
                row = self._revision(conn, found["revision_id"], key)
            return self._public(row)
