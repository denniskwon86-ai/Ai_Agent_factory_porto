"""기존 Host 승인 사건의 검증/파일 투영 복구. 새 승인·원장 append·실행은 하지 않는다.

서버 내부 전용. main은 현재 PROJECT_RUN/프로젝트 쓰기권·정확한 자원 문맥·
2.0 cohort/ProcessContext/체크포인트를 검증하고 두 함수를 동일 project guard 안에서
호출해야 한다. guard는 현재 가동과 start/resume/결정/컴파일 writer를 배제해야 한다.
이 모듈은 현재 PDP, 체크포인트 CAS, 다중 호스트 원자성 또는 실행 재개를 보장하지 않는다.
검증과 stamp 사이에 guard를 풀거나 VerifiedReview를 캐시/HTTP 입력으로 복원하지 않는다.

원장 전체 체인을 같은 BEGIN IMMEDIATE snapshot에서 검증한다(기존 hash v1 유지).
사건/부모/유일 결정/이후 review를 확인하며 DB 행·스키마를 쓰거나 빈 원장을 만들지 않는다.
stamp는 원래 actor/created_at/event_id를 사용하고 정확히 반영됐다면 파일도 다시 쓰지 않는다.
fsync+atomic replace와 raw-byte 재비교/read-back은 프로젝트 guard 하에서만 CAS 의미를 가진다.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from types import MappingProxyType

from core.advisor_revision_store import RevisionStoreError

_REQUEST = "APP_CONTRACT_REVIEW_REQUESTED"
_APPROVED = "APP_CONTRACT_APPROVED"
_REJECTED = "APP_CONTRACT_REJECTED"
_SEAL = object()


class ReconcileError(RevisionStoreError):
    """기존 Studio API와 같은 reason_code/status_code 오류 계약."""


@dataclass(frozen=True)
class VerifiedReview(Mapping):
    """validate_approval가 발급하는 일회성 서버 내부 읽기 전용 검증 결과."""
    _data: Mapping = field(repr=False)
    _seal: object = field(repr=False)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


def _fail(code, message, status=409):
    raise ReconcileError(code, message, status)


def _text(value):
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 256 or any(ord(c) < 32 for c in value)):
        _fail("RECONCILE_INPUT_INVALID", "명시적인 서버 식별자와 문맥이 필요합니다.", 422)
    return value


def _fingerprint(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        _fail("RECONCILE_INPUT_INVALID", "정확한 계약 지문이 필요합니다.", 422)
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("non-finite JSON")


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)


@contextmanager
def _snapshot(ledger):
    # _ready()는 빈 DB/schema를 생성할 수 있으므로 복구에서 호출하지 않는다.
    if not Path(ledger.db_path).is_file():
        _fail("RECONCILE_LEDGER_UNAVAILABLE", "기존 승인 원장을 읽을 수 없습니다.", 503)
    conn = None
    try:
        with ledger._lock:
            conn = ledger._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
            finally:
                # SELECT만 수행한다. 성공도 rollback으로 snapshot을 끝내며 append는 없다.
                try:
                    conn.rollback()
                finally:
                    conn.close()
                    conn = None
    except ReconcileError:
        raise
    except (sqlite3.Error, OSError) as exc:
        raise ReconcileError("RECONCILE_LEDGER_UNAVAILABLE", "기존 승인 원장을 읽을 수 없습니다.", 503) from exc


def _check_chain(conn):
    from core.decision_ledger import _compute_hash
    previous, sequence = "", 0
    cursor = conn.execute("SELECT * FROM decision_ledger_events ORDER BY seq")
    try:
        for stored in cursor:
            row = dict(stored)
            sequence += 1
            if (row["seq"] != sequence or row["prev_hash"] != previous
                    or row["event_hash"] != _compute_hash(row, previous)):
                _fail("RECONCILE_LEDGER_INTEGRITY", "승인 원장 체인을 확인할 수 없습니다.", 503)
            previous = row["event_hash"]
    finally:
        cursor.close()


def _event(conn, event_id):
    row = conn.execute("SELECT * FROM decision_ledger_events WHERE event_id=?", (event_id,)).fetchone()
    if row is None:
        _fail("RECONCILE_NOT_FOUND", "현재 문맥의 승인 사건을 찾을 수 없습니다.", 404)
    result = dict(row)
    try:
        for name in ("evidence_refs", "input_version_refs", "output_version_refs"):
            value = _decode(result.pop(name + "_json"))
            if not isinstance(value, list):
                raise ValueError("reference list required")
            result[name] = value
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ReconcileError("RECONCILE_LEDGER_INTEGRITY", "승인 근거 형식이 손상됐습니다.", 503) from exc
    return result


def validate_approval(ledger, *, project_id, task_id, request_event_id, event_id,
                             compiled_fingerprint, tenant_id, enterprise_scope_id, entity_mode):
    """현재 자원 문맥의 기존 승인만 검증한다. 거절 사건 재적용/새 승인 생성은 금지.

    enterprise_scope_id는 사용자가 고른 상위 scope가 아니라 main이 검증한 프로젝트
    자원의 실제 scope다. 빈/과거 오기록 문맥을 현재 값으로 보정하지 않는다.
    반환은 Mapping(.get/키 조회 지원)이며 원장 검증을 대신하는 HTTP bearer가 아니다.
    """
    for value in (project_id, task_id, request_event_id, event_id, tenant_id, enterprise_scope_id):
        _text(value)
    _fingerprint(compiled_fingerprint)
    if entity_mode not in ("REAL", "VIRTUAL"):
        _fail("RECONCILE_INPUT_INVALID", "실제/연습 문맥을 명시하십시오.", 422)
    with _snapshot(ledger) as conn:
        _check_chain(conn)
        event, parent = _event(conn, event_id), _event(conn, request_event_id)
        for row in (event, parent):
            if any(row[k] != value for k, value in (
                    ("project_id", project_id), ("tenant_id", tenant_id),
                    ("enterprise_scope_id", enterprise_scope_id), ("entity_mode", entity_mode))):
                _fail("RECONCILE_NOT_FOUND", "현재 문맥의 승인 사건을 찾을 수 없습니다.", 404)
        if (event["event_type"] != _APPROVED or parent["event_type"] != _REQUEST
                or event["parent_event_id"] != request_event_id
                or event["seq"] <= parent["seq"]
                or any(row["subject_type"] != "app_contract"
                       or row["subject_id"] != compiled_fingerprint for row in (event, parent))):
            _fail("RECONCILE_APPROVAL_CONFLICT", "같은 계약의 기존 승인·요청 연결이 아닙니다.")
        if event["actor_type"] != "user" or event["decision"] != "승인":
            _fail("RECONCILE_APPROVAL_CONFLICT", "사람이 승인한 사건만 복구할 수 있습니다.")
        try:
            _text(event["actor_id"])
            timestamp = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timezone required")
        except (ReconcileError, ValueError, TypeError, AttributeError) as exc:
            raise ReconcileError("RECONCILE_LEDGER_INTEGRITY", "원래 승인자·시각을 확인할 수 없습니다.", 503) from exc
        evidence = [r for r in event["evidence_refs"] if isinstance(r, dict) and "task_id" in r]
        requests = [r for r in parent["evidence_refs"] if isinstance(r, dict) and "task_ids" in r]
        if (len(evidence) != 1 or evidence[0].get("task_id") != task_id
                or evidence[0].get("compiled_fingerprint") != compiled_fingerprint
                or len(requests) != 1 or requests[0].get("compiled_fingerprint") != compiled_fingerprint
                or not isinstance(requests[0].get("task_ids"), list)
                or task_id not in requests[0]["task_ids"]):
            _fail("RECONCILE_TASK_CONFLICT", "기존 요청·승인이 지정한 같은 작업만 복구할 수 있습니다.")
        children = conn.execute(
            "SELECT event_id,event_type,parent_event_id FROM decision_ledger_events "
            "WHERE parent_event_id IN (?,?) ORDER BY seq", (request_event_id, event_id)).fetchall()
        decisions = [r["event_id"] for r in children if r["event_type"] in (_APPROVED, _REJECTED)]
        if (decisions != [event_id] or any(r["event_type"] == "CORRECTION"
                                          or r["parent_event_id"] == event_id for r in children)):
            _fail("RECONCILE_APPROVAL_CONFLICT", "유일한 기존 승인임을 확인할 수 없거나 후속 정정이 있습니다.")
        # 계약은 project 단위다. A→B→A나 동일 fp의 새 review도 과거 승인을 되살리지 않는다.
        if conn.execute(
                "SELECT 1 FROM decision_ledger_events WHERE project_id=? AND seq>? "
                "AND event_type IN (?,?,?) LIMIT 1",
                (project_id, event["seq"], _REQUEST, _APPROVED, _REJECTED)).fetchone():
            _fail("RECONCILE_REVIEW_SUPERSEDED", "승인 이후 새 검토/결정이 있습니다. 현재 검토를 확인하십시오.")
        data = {key: event[key] for key in (
            "event_id", "event_type", "subject_type", "subject_id", "parent_event_id",
            "project_id", "tenant_id", "enterprise_scope_id", "entity_mode",
            "actor_id", "actor_type", "created_at", "seq", "event_hash")}
        data.update(task_id=task_id, request_event_id=request_event_id,
                    compiled_fingerprint=compiled_fingerprint)
        return VerifiedReview(MappingProxyType(data), _SEAL)


def _read_regular(path):
    """링크/다른 inode/읽는 중 변경은 복구 대상으로 삼지 않는다."""
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or path.is_symlink()
            or getattr(before, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        _fail("RECONCILE_CONTRACT_CONFLICT", "일반 계약 정본 파일만 복구할 수 있습니다.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        current = os.fstat(stream.fileno())
        if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            _fail("RECONCILE_CONTRACT_CONFLICT", "계약 파일이 변경됐습니다.")
        raw = stream.read()
    after = path.lstat()
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        _fail("RECONCILE_CONTRACT_CONFLICT", "계약을 읽는 동안 정본이 변경됐습니다.")
    return raw


def _validated_contract(raw, verified, fingerprint):
    from core import app_runtime_contract as arc
    try:
        contract = _decode(raw)
        if not isinstance(contract, dict):
            raise ValueError("object required")
        if (contract.get("project_id") != verified["project_id"]
                or contract.get("task_id", "") not in ("", verified["task_id"])
                or contract.get("semantic_fingerprint") != fingerprint
                or contract.get("status") not in ("COMPILED", "APPROVED")):
            _fail("RECONCILE_CONTRACT_CONFLICT", "현재 프로젝트·작업·계약 판본이 기존 승인과 다릅니다.")
        if arc.validate(contract):
            _fail("RECONCILE_CONTRACT_INTEGRITY", "계약 원문/의미 지문을 검증하지 못했습니다.", 503)
        if contract.get("schema_version") == "2.0":
            key = contract["process_context"]["context_key"]
            if (key["tenant_id"] != verified["tenant_id"] or key["entity_mode"] != verified["entity_mode"]
                    or (key["scope_node_id"] or key["context_root_id"]) != verified["enterprise_scope_id"]):
                _fail("RECONCILE_CONTRACT_CONFLICT", "계약 업무 문맥이 승인 사건과 다릅니다.")
        return contract
    except ReconcileError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ReconcileError("RECONCILE_CONTRACT_INTEGRITY", "계약 정본 형식을 확인할 수 없습니다.", 503) from exc


def _atomic_stamp(path, before, after):
    descriptor, name = tempfile.mkstemp(prefix=".host-reconcile-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if _read_regular(path) != before:
            _fail("RECONCILE_CONTRACT_CONFLICT", "복구 중 계약 판본이 변경됐습니다.")
        os.replace(temporary, path)
    finally:
        # 이 호출이 만든 임시 파일만 정리한다. 기존 계약/다른 tmp는 삭제하지 않는다.
        if temporary.exists():
            temporary.unlink()


def stamp_approval(workspace, *, event, fingerprint):
    """파일 stamp/read-back만 수행한다. state_applied/재가동 성공을 뜻하지 않는다.

    이미 같은 승인 stamp면 byte-identical no-op. 원래 stamp의 시각만 ledger와 다르면
    원장 created_at으로 1회 고정한다. 다른 승인 사건의 stamp를 덮어쓰지 않는다.
    main은 서버 cohort/현재 ProcessContext를 검증하고 project guard를 유지해야 한다.
    """
    verified_event = event
    if type(verified_event) is not VerifiedReview or verified_event._seal is not _SEAL:
        _fail("RECONCILE_VERIFIED_EVENT_REQUIRED", "서버가 방금 검증한 기존 승인 사건이 필요합니다.", 422)
    _fingerprint(fingerprint)
    if fingerprint != verified_event["compiled_fingerprint"]:
        _fail("RECONCILE_CONTRACT_CONFLICT", "검증한 승인 지문과 현재 계약 지문이 다릅니다.")
    root = Path(workspace).absolute()
    if root.name != verified_event["project_id"] or root.is_symlink() or (root / "contracts").is_symlink():
        _fail("RECONCILE_CONTRACT_CONFLICT", "검증한 프로젝트의 계약 정본 경로가 아닙니다.")
    path = root / "contracts" / "app_runtime_contract.json"
    try:
        before = _read_regular(path)
        contract = _validated_contract(before, verified_event, fingerprint)
        approval = {"status": "APPROVED", "approved_by": verified_event["actor_id"],
                    "approved_at": verified_event["created_at"], "decision_ledger_id": verified_event["event_id"]}
        old = contract.get("approval") or {}
        if (old.get("status") not in ("PENDING", "APPROVED")
                or (contract["status"] == "APPROVED") != (old.get("status") == "APPROVED")):
            _fail("RECONCILE_APPROVAL_CONFLICT", "반려되거나 서로 모순된 승인 상태는 자동 복구하지 않습니다.")
        if old.get("status") == "APPROVED" and (
                old.get("decision_ledger_id") != verified_event["event_id"]
                or old.get("approved_by") != verified_event["actor_id"]):
            _fail("RECONCILE_APPROVAL_CONFLICT", "다른 승인 사건의 도장을 덮어쓸 수 없습니다.")
        # supersedes_fingerprint 등 기존 승인 메타도 보존한다.
        target = copy.deepcopy(contract)
        target["status"] = "APPROVED"
        target["approval"] = {**old, **approval}
        already_applied = target == contract
        after = before if already_applied else json.dumps(
            target, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
        _validated_contract(after, verified_event, fingerprint)
        if not already_applied:
            _atomic_stamp(path, before, after)
        readback = _read_regular(path)
        if readback != after:
            _fail("RECONCILE_CONTRACT_READBACK", "승인 도장의 저장 결과를 확인하지 못했습니다.", 503)
        _validated_contract(readback, verified_event, fingerprint)
        return {"event_id": verified_event["event_id"], "request_event_id": verified_event["request_event_id"],
                "project_id": verified_event["project_id"], "task_id": verified_event["task_id"],
                "contract_fingerprint": fingerprint, "stamp_applied": True,
                "already_applied": already_applied, "approved_by": approval["approved_by"],
                "approved_at": approval["approved_at"], "contract_digest": hashlib.sha256(readback).hexdigest()}
    except ReconcileError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise ReconcileError("RECONCILE_CONTRACT_IO", "계약 도장 반영을 완료하지 못했습니다. 같은 사건으로 재시도하십시오.", 503) from exc
