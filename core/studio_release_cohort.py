"""B3 kit release의 서버 소유 2.0 cohort. 파일 marker나 계약 revision이 아니다.

publish 전에 pin하고 Host는 신뢰한 release_id로 get한다. revision/계약 지문/
현재 승인은 kit_app_contract 서버 행에서 별도로 확인해야 한다. cohort 존재 자체는
실행권한이 아니다. 기존 테이블에는 DDL/DML을 하지 않는다.

get은 전용 테이블/행의 실제 부재에만 None이다. 저장소 장애·기존 행 손상·B2 근거
누락은 예외이며 legacy로 내려가지 않는다. get은 DDL을 실행하지 않는다.
DB 소유자가 테이블 전체를 삭제하거나 정합적인 DB 전체를 재작성한 경우까지
증명하는 외부 서명은 아니다. table 부재를 legacy로 읽는 API 경계는 의도적이다.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
from typing import Any

from core.enterprise_context.process_schema import ProcessError


class ReleaseCohortError(ProcessError):
    """서버 내부 cohort 오류. 존재 여부나 내부 ID를 외부 응답으로 노출하지 않는다."""


TABLE = "kit_process_release_cohorts"
DOCUMENT_VERSION = "2.0"
_CONTEXT_KEYS = {"tenant_id", "context_root_id", "entity_mode", "scope_node_id"}
_IDENTITY_KEYS = {"release_id", "instance_id", "app_id", "context_key", "runtime_document_version"}
_COLUMNS = {"release_id", "instance_id", "app_id", "runtime_document_version",
            "identity_json", "identity_digest", "artifact_digest"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _error(code: str, message: str, status: int = 503):
    raise ReleaseCohortError(code, message, status)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, *, empty: bool = False, limit: int = 200) -> str:
    if (not isinstance(value, str) or len(value) > limit or value != value.strip()
            or (not value and not empty) or any(ord(c) < 32 for c in value)):
        _error("STUDIO_RELEASE_COHORT_INVALID", "릴리스 cohort 식별자 형식을 확인하십시오.", 422)
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ReleaseCohortError("STUDIO_RELEASE_COHORT_INVALID", "유효한 UTF-8 식별자가 필요합니다.", 422) from exc
    return value


def _identity(release_id, instance_id, app_id, context_key) -> dict:
    if not isinstance(context_key, dict) or set(context_key) != _CONTEXT_KEYS:
        _error("STUDIO_RELEASE_COHORT_INVALID", "회사·루트·실행모드·범위 네 키를 정확히 지정하십시오.", 422)
    context = {k: _text(context_key[k], empty=k == "scope_node_id") for k in sorted(_CONTEXT_KEYS)}
    if context["entity_mode"] not in ("REAL", "VIRTUAL", "COMPETITOR_REFERENCE"):
        _error("STUDIO_RELEASE_COHORT_INVALID", "지원하지 않는 실행모드입니다.", 422)
    return dict(release_id=_text(release_id, limit=512), instance_id=_text(instance_id),
                app_id=_text(app_id), context_key=context, runtime_document_version=DOCUMENT_VERSION)


def _object(raw: Any) -> dict:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    def reject_constant(_):
        raise ValueError("nonfinite JSON")
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("invalid identity JSON")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def _table_exists(conn, name: str) -> bool:
    row = conn.execute("SELECT type FROM sqlite_master WHERE name=?", (name,)).fetchone()
    if row is None:
        return False
    if row["type"] != "table":
        _error("STUDIO_RELEASE_COHORT_CORRUPT", "서버 cohort 또는 참조 저장소 형식이 다릅니다.")
    return True


def _check_table(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(kit_process_release_cohorts)")}
    if columns != _COLUMNS:
        _error("STUDIO_RELEASE_COHORT_CORRUPT", "서버 cohort 테이블 형식을 확인할 수 없습니다.")


def _ensure_table(conn):
    # executescript는 열린 BEGIN IMMEDIATE를 조기 commit할 수 있어 사용하지 않는다.
    conn.execute("""CREATE TABLE IF NOT EXISTS kit_process_release_cohorts (
        release_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, app_id TEXT NOT NULL,
        runtime_document_version TEXT NOT NULL CHECK(runtime_document_version='2.0'),
        identity_json TEXT NOT NULL, identity_digest TEXT NOT NULL, artifact_digest TEXT NOT NULL)""")
    _check_table(conn)
    for operation in ("UPDATE", "DELETE"):
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS kit_process_release_cohorts_no_{operation.lower()}
            BEFORE {operation} ON kit_process_release_cohorts BEGIN
            SELECT RAISE(ABORT, 'STUDIO_RELEASE_COHORT_IMMUTABLE'); END""")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS kit_process_release_cohorts_no_replace
        BEFORE INSERT ON kit_process_release_cohorts WHEN EXISTS (
            SELECT 1 FROM kit_process_release_cohorts WHERE release_id=NEW.release_id) BEGIN
        SELECT RAISE(ABORT, 'STUDIO_RELEASE_COHORT_IMMUTABLE'); END""")


def _read(conn, release_id: str) -> dict | None:
    if not _table_exists(conn, TABLE):
        return None
    _check_table(conn)
    rows = conn.execute("SELECT * FROM kit_process_release_cohorts WHERE release_id=? LIMIT 2",
                        (release_id,)).fetchall()
    if not rows:
        return None
    try:
        if len(rows) != 1:
            raise ValueError("duplicate identity")
        row = dict(rows[0])
        identity = _object(row["identity_json"])
        if set(identity) != _IDENTITY_KEYS:
            raise ValueError("unknown identity fields")
        expected = _identity(identity["release_id"], identity["instance_id"], identity["app_id"],
                             identity["context_key"])
        if (identity != expected or row["identity_json"] != _canonical(expected)
                or row["identity_digest"] != _digest(expected)
                or any(row[k] != expected[k] for k in ("release_id", "instance_id", "app_id", "runtime_document_version"))
                or row["release_id"] != release_id or not isinstance(row["artifact_digest"], str)
                or not _HEX.fullmatch(row["artifact_digest"])):
            raise ValueError("identity mismatch")
        return {**expected, "artifact_digest": row["artifact_digest"], "identity_digest": row["identity_digest"]}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ReleaseCohortError("STUDIO_RELEASE_COHORT_CORRUPT", "저장된 릴리스 cohort의 무결성을 확인할 수 없습니다.", 503) from exc


class _ConnectionView:
    """get_bundle의 공개 API를 같은 DB snapshot에 연결한다. commit/close하지 않는다."""
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def transaction(self):
        yield self.conn


def _references(conn, identity: dict, *, stored: bool) -> str:
    from core.data_preparation.process_pack_artifacts import get_bundle, ProcessPackError
    for table in ("kit_instances", "kit_process_instances", "kit_process_artifacts"):
        if not _table_exists(conn, table):
            _error("STUDIO_RELEASE_COHORT_REFERENCE_MISSING", "릴리스 cohort의 고정 B2 근거가 없습니다.")
    instance = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (identity["instance_id"],)).fetchone()
    link = conn.execute("SELECT * FROM kit_process_instances WHERE instance_id=?", (identity["instance_id"],)).fetchone()
    if instance is None or link is None:
        _error("STUDIO_RELEASE_COHORT_REFERENCE_MISSING", "릴리스 cohort의 고정 적용본 또는 B2 결속이 없습니다.")
    try:
        instance, link = dict(instance), dict(link)
        sealed = _object(link["identity_json"])
        keys = {"kit_id", "version", "kit_fingerprint", "tenant_id", "scope_node_id", "entity_mode"}
        if (set(sealed) != keys or any(not isinstance(sealed[k], str) or not sealed[k] for k in keys)
                or _digest(sealed) != link["identity_digest"]
                or link["instance_id"] != identity["instance_id"]
                or not isinstance(link["operation_id"], str) or not link["operation_id"]
                or any(instance[k] != sealed[k] for k in keys)
                or not isinstance(link["artifact_digest"], str) or not _HEX.fullmatch(link["artifact_digest"])
                or link["artifact_digest"] != sealed["kit_fingerprint"]):
            raise ValueError("B2 identity mismatch")
        artifact = get_bundle(_ConnectionView(conn), link["artifact_digest"])
        if (instance["kit_id"] != artifact["kit_id"] or instance["version"] != artifact["version"]
                or instance["kit_fingerprint"] != artifact["artifact_digest"]):
            raise ValueError("artifact mismatch")
        boundary = identity["context_key"]
        expected = {"tenant_id": boundary["tenant_id"], "entity_mode": boundary["entity_mode"],
                    "scope_node_id": boundary["scope_node_id"] or boundary["context_root_id"]}
        matches = (link["context_root_id"] == boundary["context_root_id"]
                   and all(instance[k] == v for k, v in expected.items())
                   and instance["status"] == "active"
                   and sum(bp["app_id"] == identity["app_id"] for bp in artifact["blueprints"]["blueprints"]) == 1)
    except ProcessPackError as exc:
        missing = exc.reason_code == "PROCESS_ARTIFACT_NOT_FOUND"
        code = "STUDIO_RELEASE_COHORT_REFERENCE_MISSING" if missing else "STUDIO_RELEASE_COHORT_REFERENCE_CORRUPT"
        raise ReleaseCohortError(code, "릴리스 cohort의 고정 artifact를 확인할 수 없습니다.", 503) from exc
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ReleaseCohortError("STUDIO_RELEASE_COHORT_REFERENCE_CORRUPT", "릴리스 cohort의 B2 정체성·artifact 근거가 손상되었습니다.", 503) from exc
    if not matches:
        _error("STUDIO_RELEASE_COHORT_REFERENCE_CONFLICT", "고정 적용본·앱 후보·현재 경계가 릴리스 cohort와 다릅니다.",
               503 if stored else 409)
    return artifact["artifact_digest"]


def pin_release_cohort(store, *, release_id, instance_id, app_id, context_key) -> dict:
    """서버 검증 뒤 publish 전에 호출한다. 동일 정체성은 멱등, 다른 본문은 409.

    fresh store.transaction을 소유한다. 이미 열린 transaction을 중간 commit하거나
    deferred transaction을 BEGIN IMMEDIATE였다고 가정하지 않는다.
    """
    identity = _identity(release_id, instance_id, app_id, context_key)
    try:
        with store.transaction() as conn:
            if conn.in_transaction:
                _error("STUDIO_RELEASE_COHORT_TRANSACTION_REQUIRED", "cohort 고정에는 새 쓰기 transaction이 필요합니다.")
            conn.execute("BEGIN IMMEDIATE")
            existing = _read(conn, identity["release_id"])
            if existing and any(existing[k] != identity[k] for k in _IDENTITY_KEYS):
                _error("STUDIO_RELEASE_COHORT_CONFLICT", "같은 release ID의 다른 정체성은 고정할 수 없습니다.", 409)
            artifact_digest = _references(conn, identity, stored=existing is not None)
            if existing and existing["artifact_digest"] != artifact_digest:
                _error("STUDIO_RELEASE_COHORT_REFERENCE_CORRUPT", "저장된 cohort의 artifact가 B2 정체성과 다릅니다.")
            _ensure_table(conn)
            if existing:
                return existing
            digest = _digest(identity)
            conn.execute("""INSERT INTO kit_process_release_cohorts
                (release_id,instance_id,app_id,runtime_document_version,identity_json,identity_digest,artifact_digest)
                VALUES (?,?,?,?,?,?,?)""", (identity["release_id"], identity["instance_id"], identity["app_id"],
                    DOCUMENT_VERSION, _canonical(identity), digest, artifact_digest))
            return {**identity, "artifact_digest": artifact_digest, "identity_digest": digest}
    except (sqlite3.Error, OSError) as exc:
        raise ReleaseCohortError("STUDIO_RELEASE_COHORT_STORAGE_UNAVAILABLE", "서버 릴리스 cohort를 고정할 수 없습니다.", 503) from exc


def get_release_cohort(store, release_id) -> dict | None:
    """신뢰한 release ID로 조회한다. table/행 부재만 None이며 READ DDL은 없다."""
    release_id = _text(release_id, limit=512)
    try:
        with store.transaction() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN")
            existing = _read(conn, release_id)
            if existing is None:
                return None
            artifact_digest = _references(conn, existing, stored=True)
            if artifact_digest != existing["artifact_digest"]:
                _error("STUDIO_RELEASE_COHORT_REFERENCE_CORRUPT", "저장된 cohort의 artifact가 B2 정체성과 다릅니다.")
            return existing
    except (sqlite3.Error, OSError) as exc:
        raise ReleaseCohortError("STUDIO_RELEASE_COHORT_STORAGE_UNAVAILABLE", "서버 릴리스 cohort를 읽을 수 없습니다.", 503) from exc
