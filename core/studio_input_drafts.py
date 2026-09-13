"""B5 입력 전용 초안. 요구 Blueprint/실행/승인 저장소로 사용할 수 없다.

외부 호출자는 현재 principal·서버 자산 귀속·실제 target 차수를 매번 확인한다.
기존 AdvisorStore의 연결/락만 주입하며 import/생성자는 DB에 접근하지 않는다.
소비/폐기는 내용 삭제가 아닌 종결 표시다. 과거 입력 복원 API는 제공하지 않는다.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import uuid
from typing import Literal

from pydantic import Field, model_validator

from core.enterprise_context.process_schema import ProcessError, StrictModel


class InputDraftError(ProcessError):
    pass


def fail(code, message, status=409):
    raise InputDraftError("INPUT_DRAFT_" + code, message, status)


def canonical(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(raw.encode("utf-8")) > 262144:
            raise ValueError("size")
        return raw
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise InputDraftError("INPUT_DRAFT_INVALID", "유효한 크기의 JSON 입력이 필요합니다.", 422) from exc


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class Target(StrictModel):
    kind: Literal["CLARIFICATION", "DECISION_COMMENT", "REVISION_REQUEST"]
    task_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    decision_kind: Literal["", "GENERAL_HOTL", "HOST_CONTRACT", "CAPABILITY", "DATASET"] = ""
    request_id: str = Field(min_length=1, max_length=200)
    target_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    subject_id: str = Field(default="", max_length=256)

    @model_validator(mode="after")
    def closed_kind(self):
        if (self.kind == "DECISION_COMMENT") != bool(self.decision_kind):
            raise ValueError("결정 의견에만 decision_kind가 필요합니다.")
        if (self.decision_kind in {"CAPABILITY", "DATASET"}) != bool(self.subject_id):
            raise ValueError("능력/데이터셋 결정에만 실제 subject_id가 필요합니다.")
        return self


class Content(StrictModel):
    text: str = Field(max_length=32000)
    decision: str = Field(default="", max_length=256)
    selections: dict[str, list[str]] = Field(default_factory=dict, max_length=100)


def validate_content(target, content):
    content = Content.model_validate(content).model_dump()
    if target["kind"] != "CLARIFICATION" and content["selections"]:
        fail("INVALID", "명확화 답변에만 질문 선택값을 저장할 수 있습니다.", 422)
    choice = content["decision"]
    if target["decision_kind"] == "HOST_CONTRACT":
        if choice not in {"", "APPROVE", "REJECT"}:
            fail("INVALID", "승인/반려 선택을 확인하십시오.", 422)
    elif target["decision_kind"] == "CAPABILITY":
        if choice not in {"", "REDUCE", "WAIT", "REQUEST_HOST_FEATURE"}:
            fail("INVALID", "지원 능력 선택을 확인하십시오.", 422)
    elif target["decision_kind"] != "DATASET" and choice:
        fail("INVALID", "이 입력은 결정 선택을 받지 않습니다.", 422)
    canonical(content)
    return content


def validate_selections(target, content, questions):
    """현재 서버 질문 ID/label에 결속한다. 미완성/빈 선택은 초안으로 허용한다."""
    if not isinstance(questions, list) or digest(questions) != target["target_digest"]:
        fail("TARGET_CONFLICT", "명확화 질문집이 바뀌었습니다. 기존 선택을 보존하십시오.")
    known = {}
    for q in questions:
        if not isinstance(q, dict) or not isinstance(q.get("id"), str) or not q["id"] or q["id"] in known:
            fail("QUESTIONS_UNAVAILABLE", "서버 질문 식별자를 확인할 수 없습니다.", 503)
        options = q.get("options")
        if (not isinstance(options, list) or any(not isinstance(o, dict) or not isinstance(o.get("label"), str)
                or not o["label"] for o in options)):
            fail("QUESTIONS_UNAVAILABLE", "서버 질문 선택지를 확인할 수 없습니다.", 503)
        labels = [o["label"] for o in options]
        if len(set(labels)) != len(labels) or type(q.get("multi", False)) is not bool:
            fail("QUESTIONS_UNAVAILABLE", "서버 질문 선택지가 모호합니다.", 503)
        known[q["id"]] = (set(labels), q.get("multi", False))
    for qid, labels in content.get("selections", {}).items():
        if (qid not in known or len(labels) > 100 or len(set(labels)) != len(labels)
                or any(label not in known[qid][0] for label in labels)
                or (not known[qid][1] and len(labels) > 1)):
            fail("SELECTION_INVALID", "현재 질문 ID와 허용된 선택지 label만 저장하십시오.", 422)


_DDL = """
CREATE TABLE IF NOT EXISTS studio_input_drafts (
 draft_id TEXT PRIMARY KEY, boundary_json TEXT NOT NULL, actor TEXT NOT NULL,
 project_id TEXT NOT NULL, target_json TEXT NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('DRAFT','CONSUMED','DISCARDED')),
 result_json TEXT NOT NULL, result_digest TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS studio_input_active_target
 ON studio_input_drafts(boundary_json,actor,project_id,target_json) WHERE status='DRAFT';
CREATE TABLE IF NOT EXISTS studio_input_requests (
 boundary_json TEXT NOT NULL, actor TEXT NOT NULL, project_id TEXT NOT NULL,
 client_request_id TEXT NOT NULL, command_digest TEXT NOT NULL,
 draft_id TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(boundary_json,actor,project_id,client_request_id)
);
"""


class InputDraftStore:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def transaction(self, write=False):
        try:
            with self.store._lock:
                conn = self.store._connect()
                try:
                    # 새 전용 테이블만 준비한다. 기존 Blueprint 테이블/판본은 변경하지 않는다.
                    if write:
                        conn.executescript("BEGIN IMMEDIATE;\n" + _DDL)
                    else:
                        conn.execute("BEGIN")
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
        except sqlite3.Error as exc:
            raise InputDraftError("INPUT_DRAFT_STORAGE_UNAVAILABLE", "초안 저장소를 확인하지 못했습니다. 입력을 보존하십시오.", 503) from exc

    @staticmethod
    def _key(boundary, actor, project_id):
        # boundary는 HTTP 본문이 아닌 서버 소속/선택 문맥에서만 만든다.
        if not actor or not project_id or not isinstance(boundary, dict) or not boundary:
            fail("CONTEXT_REQUIRED", "인증 사용자와 서버 자산 문맥이 필요합니다.", 422)
        return canonical(boundary), actor.casefold(), project_id

    @staticmethod
    def _ready(conn):
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_input_drafts'").fetchone() is not None

    @staticmethod
    def _unpack(row):
        try:
            value = json.loads(row["result_json"])
            if (digest(value) != row["result_digest"] or value["draft_id"] != row["draft_id"]
                    or value["revision"] != row["revision"] or value["status"] != row["status"]
                    or canonical(value["target"]) != row["target_json"]
                    or value["project_id"] != row["project_id"]
                    or canonical(value["context_key"]) != row["boundary_json"]
                    or value["actor"] != row["actor"]):
                raise ValueError("identity")
            return {**value, "digest": row["result_digest"]}
        except (ValueError, TypeError, KeyError) as exc:
            raise InputDraftError("INPUT_DRAFT_INTEGRITY", "저장한 초안의 무결성을 확인하지 못했습니다.", 503) from exc

    def _get(self, conn, key, draft_id):
        row = conn.execute("SELECT * FROM studio_input_drafts WHERE boundary_json=? AND actor=? AND project_id=? AND draft_id=?",
                           (*key, draft_id)).fetchone() if self._ready(conn) else None
        if row is None:
            fail("NOT_FOUND", "현재 문맥에서 초안을 찾을 수 없습니다.", 404)
        return self._unpack(row)

    def get(self, *, boundary, actor, project_id, draft_id):
        with self.transaction() as conn:
            return self._get(conn, self._key(boundary, actor, project_id), draft_id)

    def active(self, *, boundary, actor, project_id, target):
        key = self._key(boundary, actor, project_id)
        with self.transaction() as conn:
            if not self._ready(conn):
                return None
            row = conn.execute("SELECT * FROM studio_input_drafts WHERE boundary_json=? AND actor=? AND project_id=? AND target_json=? AND status='DRAFT'",
                               (*key, canonical(target))).fetchone()
            return self._unpack(row) if row else None

    @staticmethod
    def public(row):
        # 종결된 입력은 기본값으로 복원하지 않는다. 원문은 서버에 그대로 보존한다.
        return {k: v for k, v in {**row, "restorable": row["status"] == "DRAFT",
                "content": row["content"] if row["status"] == "DRAFT" else None}.items() if k != "actor"}

    def mutate(self, *, boundary, actor, project_id, operation, draft_id, expected_revision,
               expected_digest, client_request_id, target=None, content=None, submission_id="", verified=None):
        key = self._key(boundary, actor, project_id)
        if operation not in {"SAVE", "DISCARD", "CONSUME"} or not client_request_id.strip():
            fail("INVALID", "명시적인 초안 명령과 요청 ID가 필요합니다.", 422)
        if type(expected_revision) is not int or expected_revision < 0:
            fail("INVALID", "초안 revision을 확인하십시오.", 422)
        if operation == "SAVE":
            target = Target.model_validate(target).model_dump()
            content = validate_content(target, content)
        command = digest(dict(operation=operation, draft_id=draft_id, expected_revision=expected_revision,
            expected_digest=expected_digest, target=target, content=content, submission_id=submission_id))
        with self.transaction(write=True) as conn:
            prior = conn.execute("SELECT * FROM studio_input_requests WHERE boundary_json=? AND actor=? AND project_id=? AND client_request_id=?",
                                 (*key, client_request_id)).fetchone()
            if prior:
                if prior["command_digest"] != command:
                    fail("IDEMPOTENCY_CONFLICT", "같은 요청 ID의 내용이 다릅니다.")
                row = self._get(conn, key, prior["draft_id"])
                if row["revision"] != prior["revision"]:
                    fail("REQUEST_SUPERSEDED", "이 저장 이후 초안이 변경됐습니다. 현재 초안을 조회하십시오.")
                return self.public(row)
            if draft_id:
                row = self._get(conn, key, draft_id)
                if row["revision"] != expected_revision or row["digest"] != expected_digest:
                    fail("REVISION_CONFLICT", "다른 탭에서 초안이 변경됐습니다. 입력을 보존하십시오.")
                if row["status"] != "DRAFT":
                    fail("CLOSED", "종결된 초안은 다시 편집하거나 복원할 수 없습니다.")
                if operation == "SAVE" and row["target"] != target:
                    fail("TARGET_CONFLICT", "다른 대상이나 새 차수로 초안을 복사할 수 없습니다.")
            else:
                if operation != "SAVE" or expected_revision != 0 or expected_digest:
                    fail("REVISION_CONFLICT", "새 초안은 revision 0과 빈 digest로 저장하십시오.")
                existing = conn.execute("SELECT 1 FROM studio_input_drafts WHERE boundary_json=? AND actor=? AND project_id=? AND target_json=? AND status='DRAFT'",
                                        (*key, canonical(target))).fetchone()
                if existing:
                    fail("ACTIVE_EXISTS", "현재 대상의 초안이 있습니다. 먼저 조회하십시오.")
                row = dict(draft_id="sid_" + uuid.uuid4().hex, project_id=project_id,
                           actor=key[1], context_key=boundary, target=target, created_at=datetime.now(timezone.utc).isoformat())
            if operation == "CONSUME":
                # verified는 서버 reader가 실제 사건과 입력을 확인한 결과여야 한다.
                if (not isinstance(verified, dict) or verified != dict(submission_id=submission_id,
                        draft_id=draft_id, draft_digest=expected_digest)):
                    fail("SUBMISSION_UNCONFIRMED", "실제 제출 결과를 확인하지 못했습니다. 초안을 보존합니다.", 503)
            row.pop("digest", None)
            row.update(revision=expected_revision + 1,
                       status={"SAVE": "DRAFT", "DISCARD": "DISCARDED", "CONSUME": "CONSUMED"}[operation],
                       updated_at=datetime.now(timezone.utc).isoformat())
            if operation == "SAVE":
                row["content"] = content
            if operation == "CONSUME":
                row["submission_id"] = submission_id
            raw, fp = canonical(row), digest(row)
            if draft_id:
                changed = conn.execute("UPDATE studio_input_drafts SET revision=?,status=?,result_json=?,result_digest=? WHERE draft_id=? AND revision=? AND result_digest=?",
                    (row["revision"], row["status"], raw, fp, draft_id, expected_revision, expected_digest))
                if changed.rowcount != 1:
                    fail("REVISION_CONFLICT", "초안 변경이 충돌했습니다.")
            else:
                conn.execute("INSERT INTO studio_input_drafts VALUES(?,?,?,?,?,?,?,?,?)",
                    (row["draft_id"], *key[:2], project_id, canonical(target), row["revision"], row["status"], raw, fp))
            conn.execute("INSERT INTO studio_input_requests VALUES(?,?,?,?,?,?,?)",
                         (*key, client_request_id, command, row["draft_id"], row["revision"]))
            return self.public({**row, "digest": fp})


def verify_decision_submission(row, event, parent=None):
    """실제 원장 reader의 사건만 받는다. HTTP submitted=true는 증거가 아니다."""
    target, content = row["target"], row["content"]
    if target["kind"] != "DECISION_COMMENT" or target["decision_kind"] == "GENERAL_HOTL":
        fail("CONSUME_UNSUPPORTED", "현재 제출 API는 차수·입력 결속 증거를 제공하지 않습니다. 초안을 보존합니다.", 409)
    if not event:
        fail("SUBMISSION_UNCONFIRMED", "제출 결과를 확인하지 못했습니다. 초안을 보존합니다.", 503)
    own = row["context_key"]["ownership"]
    if (event.get("project_id") != row["project_id"] or event.get("actor_type") != "user"
            or str(event.get("actor_id", "")).casefold() != row["actor"]
            or any(event.get(k) != v for k, v in own.items())
            or not content["text"].strip() or not content["decision"]
            or event.get("rationale") != (content["text"] if target["decision_kind"] == "HOST_CONTRACT" else content["text"].strip())):
        fail("SUBMISSION_CONFLICT", "제출 사건의 작성자·문맥·입력이 이 초안과 다릅니다.")
    kind = target["decision_kind"]
    if kind == "HOST_CONTRACT":
        from core import contract_review_gate as gate
        expected = gate.EVENT_APPROVED if content["decision"] == "APPROVE" else gate.EVENT_REJECTED
        if (not parent or parent.get("event_type") != gate.EVENT_REVIEW_REQUESTED
                or parent.get("event_id") != target["request_id"]
                or parent.get("project_id") != row["project_id"]
                or parent.get("subject_id") != target["target_digest"]
                or any(parent.get(k) != v for k, v in own.items())
                or event.get("event_type") != expected or event.get("subject_type") != gate.SUBJECT_TYPE
                or event.get("parent_event_id") != target["request_id"]
                or event.get("subject_id") != target["target_digest"]
                or not any(isinstance(ref, dict) and ref.get("task_id") == target["task_id"]
                           and ref.get("compiled_fingerprint") == target["target_digest"] for ref in event.get("evidence_refs", []))):
            fail("SUBMISSION_CONFLICT", "계약 결정 사건의 요청·task·지문이 다릅니다.")
    else:
        from core import contract_decision as decision
        rounds = [ref for ref in event.get("input_version_refs", []) if isinstance(ref, dict)
                  and ref.get("kind") == "CONTRACT_DECISION_ROUND"
                  and ref.get("decision_request_id") == target["request_id"]
                  and ref.get("digest") == target["target_digest"]]
        evidence = event.get("evidence_refs", [])
        task_bound = "task:" + target["task_id"] in evidence
        if kind == "DATASET":
            # 생산자의 evidence_refs는 실제 변경 task만 담는다. winner(또는 이미
            # winner와 같은 선언)는 변경되지 않으므로 고정 입력 판 집합에서 확인한다.
            versions = rounds[0].get("draft_versions") if len(rounds) == 1 else None
            changed = [ref[5:] for ref in evidence if isinstance(ref, str) and ref.startswith("task:")]
            task_bound = (isinstance(versions, dict) and target["task_id"] in versions
                          and content["decision"] in versions and bool(changed)
                          and all(tid in versions and tid != content["decision"] for tid in changed)
                          and "project:" + row["project_id"] in evidence)
        if (event.get("event_type") != "APP_CONTRACT_DECISION_RECORDED"
                or event.get("subject_type") != (decision.SUBJECT_CAPABILITY if kind == "CAPABILITY" else decision.SUBJECT_DATASET)
                or event.get("subject_id") != target["subject_id"] or event.get("decision") != content["decision"]
                or not task_bound or len(rounds) != 1):
            fail("SUBMISSION_CONFLICT", "결정 사건의 차수·대상·선택이 다릅니다.")
    return dict(submission_id=event["event_id"], draft_id=row["draft_id"], draft_digest=row["digest"])
