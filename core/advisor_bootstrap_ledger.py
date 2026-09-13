"""B3 saga의 예약 event ID를 실제 DecisionLedger에 한 번만 접수하는 어댑터.

서버 내부 전용: 현재 PDP, 승인 판본, exact boundary, 실제 프로젝트 read-back은
main이 먼저 검증한다. HTTP body를 그대로 **payload로 넘기지 않는다. event_id와
payload는 operation의 고정 값에서 구성해야 한다(재시도 시 시각/동적 DTO 삽입 금지).
기존 schema에는 context_root_id 열이 없다. main은 exact 4키 context_key를 고정된
input_version_refs/evidence_refs에 넣어 root 차이도 멱등 요청 비교에 포함해야 한다.

기존 원장 schema/해시 v1/_insert를 변경하지 않는다. 원장의 _ready/_lock/_connect를
사용하되 새 연결의 BEGIN IMMEDIATE 안에서 조회·체인 검사·삽입을 수행한다. 동일 ID는
동일 요청일 때만 원래 실제 행을 반환한다. 다른 ID의 같은 payload는 별도 사건이다.

전체 체인을 스트리밍 검사하므로 요청당 O(원장 행 수)다. hash v1은 event_id를 해시하지
않으며 외부 서명도 없다. DB 전체 재작성/꼬리 삭제까지 증명하는 보호 수단은 아니다.
이 모듈은 프로젝트를 생성하거나 advisor operation의 ack를 기록하지 않는다.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.decision_ledger import DecisionLedgerError, _compute_hash


class BootstrapLedgerError(DecisionLedgerError):
    def __init__(self, reason_code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


_SERVER_FIELDS = {"event_id", "created_at", "seq", "prev_hash", "event_hash"}
_REF_FIELDS = {"evidence_refs", "input_version_refs", "output_version_refs"}
_TEXT_FIELDS = {
    "event_type", "subject_type", "subject_id", "actor_type", "actor_id", "decision",
    "rationale", "parent_event_id", "tenant_id", "enterprise_scope_id", "entity_mode",
    "project_id", "blueprint_id",
}


def _invalid() -> None:
    raise BootstrapLedgerError("ADVISOR_LEDGER_INPUT_INVALID", "고정 ID의 프로젝트 승격 사건만 접수할 수 있습니다.", 422)


def _corrupt() -> None:
    raise BootstrapLedgerError("ADVISOR_LEDGER_INTEGRITY", "원장 사건/체인 무결성을 확인할 수 없습니다.", 503)


def _request_fields(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in _SERVER_FIELDS}


def _verify_chain(conn) -> tuple[int, str]:
    """같은 write snapshot에서 prev/hash/연속 seq 확인. 기존 해시 재료를 복제하지 않는다."""
    seq, previous_hash = 0, ""
    cursor = conn.execute("SELECT * FROM decision_ledger_events ORDER BY seq")
    try:
        for stored in cursor:
            row = dict(stored)
            seq += 1
            if (row["seq"] != seq or row["prev_hash"] != previous_hash
                    or row["event_hash"] != _compute_hash(row, previous_hash)):
                _corrupt()
            previous_hash = row["event_hash"]
    finally:
        cursor.close()
    return seq, previous_hash


def append_bootstrap_once(ledger, event_id: str, **payload: Any) -> dict:
    """원장 commit 뒤 고정 ID의 실제 public event를 반환한다(재시도도 같은 행).

    필수: event_type='PROJECT_BOOTSTRAPPED', subject_type='project',
    subject_id=project_id=예약한 프로젝트 ID. 나머지는 ledger._build_row의 필드다.
    동일 ID/다른 정규화 요청: 409. 잘못된 입력: 422. 저장/체인 장애: 503.
    호출자는 반환 event_id를 확인한 뒤에만 saga COMPLETED/ack를 기록한다.
    원장 commit 후 ack 실패는 같은 ID/동일 payload로 재접수하면 복구할 수 있다.
    """
    if (not isinstance(event_id, str) or not event_id or len(event_id) > 256
            or event_id != event_id.strip() or any(ord(c) < 32 for c in event_id)):
        _invalid()
    if set(payload) - (_TEXT_FIELDS | _REF_FIELDS):
        _invalid()
    if (payload.get("event_type") != "PROJECT_BOOTSTRAPPED"
            or payload.get("subject_type") != "project"):
        _invalid()
    project_id = payload.get("project_id")
    if (not isinstance(project_id, str) or not project_id.strip()
            or project_id != project_id.strip() or payload.get("subject_id") != project_id):
        _invalid()
    if any(not isinstance(payload[key], str) for key in _TEXT_FIELDS & set(payload)):
        _invalid()
    if any(payload[key] is not None and not isinstance(payload[key], list)
           for key in _REF_FIELDS & set(payload)):
        _invalid()
    try:
        # _build_row가 허용하는 NaN/Infinity를 새 감사 요청에 기록하지 않는다.
        json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        row = ledger._build_row(**payload)
    except (DecisionLedgerError, TypeError, ValueError, RecursionError) as exc:
        raise BootstrapLedgerError("ADVISOR_LEDGER_INPUT_INVALID", "승격 사건 본문 형식이 잘못되었습니다.", 422) from exc
    row["event_id"] = event_id
    requested = _request_fields(row)
    try:
        with ledger._lock:
            ledger._ready()
            conn = ledger._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT * FROM decision_ledger_events WHERE event_id=?", (event_id,)).fetchone()
                # 타깃 행만 해시하면 조상 변조/prev 단절을 정상 재접수로 오인할 수 있다.
                last_seq, last_hash = _verify_chain(conn)
                if existing is not None:
                    actual = dict(existing)
                    if _request_fields(actual) != requested:
                        raise BootstrapLedgerError("ADVISOR_LEDGER_IDEMPOTENCY_CONFLICT", "같은 원장 사건 ID의 문맥 또는 본문이 다릅니다.")
                else:
                    ledger._insert(conn, row)
                    stored = conn.execute(
                        "SELECT * FROM decision_ledger_events WHERE event_id=?", (event_id,)).fetchone()
                    if stored is None:
                        _corrupt()
                    actual = dict(stored)
                    if (_request_fields(actual) != requested or actual["seq"] != last_seq + 1
                            or actual["prev_hash"] != last_hash
                            or actual["event_hash"] != _compute_hash(actual, last_hash)):
                        _corrupt()
                public = ledger._to_public(actual)
                conn.commit()
                return public
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
    except BootstrapLedgerError:
        raise
    except DecisionLedgerError as exc:
        raise BootstrapLedgerError("ADVISOR_LEDGER_INPUT_INVALID", "승격 사건의 참조가 유효하지 않습니다.", 422) from exc
    except (sqlite3.Error, OSError) as exc:
        raise BootstrapLedgerError("ADVISOR_LEDGER_UNAVAILABLE", "승격 사건을 원장에 접수할 수 없습니다.", 503) from exc
