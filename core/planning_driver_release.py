"""Immutable, ledger-backed releases for planning drivers and their impacts."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from core.decision_ledger import DecisionLedger, DecisionLedgerError, decision_ledger
from core.planning_model import PlanningError, PlanningStore, planning_store
from core.system_ids import allocate


APPROVED = "APPROVED"
REVOKED = "REVOKED"
EVENT_APPROVED = "PLANNING_DRIVER_APPROVED"
EVENT_REVOKED = "PLANNING_DRIVER_REVOKED"
SUBJECT_TYPE = "planning_driver_release"


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlanningError("동인 판본의 유효 시각을 읽지 못했습니다.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source(store: PlanningStore, driver_code: str) -> dict[str, Any]:
    conn = store._connect()
    try:
        conn.execute("BEGIN")
        driver = conn.execute(
            "SELECT driver_code,name,unit,category,external_code,note FROM plan_drivers "
            "WHERE driver_code=?", (driver_code,)).fetchone()
        impacts = conn.execute(
            "SELECT account_code,elasticity,rationale,source FROM driver_impacts "
            "WHERE driver_code=? ORDER BY account_code,elasticity,rationale,source",
            (driver_code,)).fetchall()
    finally:
        conn.close()
    if not driver:
        raise PlanningError("승인할 계획 동인을 찾을 수 없습니다.")
    if not str(driver["name"] or "").strip():
        raise PlanningError("계획 동인의 사람용 이름이 비어 있습니다.")
    if not impacts:
        raise PlanningError("파급계수가 없는 계획 동인은 승인할 수 없습니다.")
    normalized = []
    for raw in impacts:
        row = dict(raw)
        if not str(row.get("rationale") or "").strip() or not str(row.get("source") or "").strip():
            raise PlanningError("근거·출처가 없는 파급계수는 승인할 수 없습니다.")
        normalized.append(row)
    return {**dict(driver), "impacts": normalized}


def fingerprint(source: dict[str, Any], *, tenant_id: str, scope_node_id: str,
                entity_mode: str) -> str:
    material = {
        "driver_code": str(source.get("driver_code") or ""),
        "name": str(source.get("name") or ""), "unit": str(source.get("unit") or ""),
        "category": str(source.get("category") or ""),
        "external_code": str(source.get("external_code") or ""),
        "note": str(source.get("note") or ""), "tenant_id": str(tenant_id or ""),
        "scope_node_id": str(scope_node_id or ""), "entity_mode": str(entity_mode or ""),
        "impacts": source.get("impacts") or [],
    }
    payload = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _public(row: dict[str, Any], *, idempotent: bool = False) -> dict[str, Any]:
    return {key: row.get(key) for key in (
        "driver_code", "version", "fingerprint", "name", "status", "approved_by",
        "approved_at", "revoked_by", "revoked_at")} | {"idempotent": idempotent}


def approve(driver_code: str, actor: str, rationale: str, *, tenant_id: str,
            scope_node_id: str, entity_mode: str, store: Optional[PlanningStore] = None,
            ledger: Optional[DecisionLedger] = None) -> dict[str, Any]:
    store, ledger = store or planning_store, ledger or decision_ledger
    if not all(str(value or "").strip() for value in
               (actor, rationale, tenant_id, scope_node_id, entity_mode)):
        raise PlanningError("동인 승인자·근거·tenant·조직 범위·실행 문맥이 모두 필요합니다.")
    source = _source(store, driver_code)
    fp = fingerprint(source, tenant_id=tenant_id, scope_node_id=scope_node_id,
                     entity_mode=entity_mode)
    conn = store._connect()
    try:
        active = conn.execute(
            "SELECT * FROM driver_releases WHERE driver_code=? AND status=? "
            "ORDER BY version DESC LIMIT 1", (driver_code, APPROVED)).fetchone()
        if active:
            current = dict(active)
            if current["fingerprint"] == fp:
                return _public(current, idempotent=True)
            raise PlanningError("이미 승인된 다른 동인 판본이 있습니다. 먼저 철회하십시오.")
        version = int(conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM driver_releases WHERE driver_code=?",
            (driver_code,)).fetchone()[0])
    finally:
        conn.close()
    event = ledger.append(
        event_type=EVENT_APPROVED, subject_type=SUBJECT_TYPE, subject_id=fp,
        actor_type="user", actor_id=actor, decision="APPROVE", rationale=rationale.strip(),
        evidence_refs=[{"driver_code": driver_code, "version": version}],
        tenant_id=tenant_id, enterprise_scope_id=scope_node_id, entity_mode=entity_mode)
    approved_at = str(event["created_at"])
    release_id = allocate("driver_release")[0]
    impacts_json = json.dumps(source["impacts"], ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"))
    try:
        conn = store._connect()
        try:
            conn.execute(
                "INSERT INTO driver_releases(release_id,driver_code,version,fingerprint,name,unit,"
                "category,external_code,note,tenant_id,scope_node_id,entity_mode,impacts_json,status,"
                "approved_by,approved_at,approval_event_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (release_id, driver_code, version, fp, source["name"], source.get("unit") or "",
                 source.get("category") or "", source.get("external_code") or "",
                 source.get("note") or "", tenant_id, scope_node_id, entity_mode, impacts_json,
                 APPROVED, actor, approved_at, event["event_id"], approved_at))
            conn.commit()
            row = dict(conn.execute(
                "SELECT * FROM driver_releases WHERE release_id=?", (release_id,)).fetchone())
        finally:
            conn.close()
    except Exception as exc:
        ledger.append(
            event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE, subject_id=fp,
            actor_type="system", actor_id=actor, decision="COMPENSATE",
            rationale=f"동인 판본 등록 실패: {type(exc).__name__}",
            parent_event_id=event["event_id"], tenant_id=tenant_id,
            enterprise_scope_id=scope_node_id, entity_mode=entity_mode)
        raise
    return _public(row)


def revoke(driver_code: str, actor: str, rationale: str, *,
           store: Optional[PlanningStore] = None,
           ledger: Optional[DecisionLedger] = None) -> dict[str, Any]:
    store, ledger = store or planning_store, ledger or decision_ledger
    if not str(actor or "").strip() or not str(rationale or "").strip():
        raise PlanningError("철회자와 철회 사유가 모두 필요합니다.")
    conn = store._connect()
    try:
        raw = conn.execute(
            "SELECT * FROM driver_releases WHERE driver_code=? AND status=? "
            "ORDER BY version DESC LIMIT 1", (driver_code, APPROVED)).fetchone()
    finally:
        conn.close()
    if not raw:
        raise PlanningError("철회할 승인 동인 판본이 없습니다.")
    row = dict(raw)
    event = ledger.append(
        event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE, subject_id=row["fingerprint"],
        actor_type="user", actor_id=actor, decision="REVOKE", rationale=rationale.strip(),
        parent_event_id=row["approval_event_id"], tenant_id=row["tenant_id"],
        enterprise_scope_id=row["scope_node_id"], entity_mode=row["entity_mode"])
    revoked_at = str(event["created_at"])
    conn = store._connect()
    try:
        changed = conn.execute(
            "UPDATE driver_releases SET status=?,revoked_by=?,revoked_at=?,revocation_event_id=? "
            "WHERE release_id=? AND status=?", (REVOKED, actor, revoked_at, event["event_id"],
                                                row["release_id"], APPROVED)).rowcount
        conn.commit()
        if changed != 1:
            raise PlanningError("동인 판본 철회 상태가 동시에 변경됐습니다.")
        updated = dict(conn.execute(
            "SELECT * FROM driver_releases WHERE release_id=?", (row["release_id"],)).fetchone())
    finally:
        conn.close()
    return _public(updated)


def effective_release(driver_code: str, as_of: str = "", *,
                      store: Optional[PlanningStore] = None,
                      ledger: Optional[DecisionLedger] = None) -> Optional[dict[str, Any]]:
    store, ledger = store or planning_store, ledger or decision_ledger
    cutoff = _instant(as_of) if str(as_of or "").strip() else datetime.now(timezone.utc)
    conn = store._connect()
    try:
        rows = conn.execute(
            "SELECT * FROM driver_releases WHERE driver_code=? ORDER BY version DESC",
            (driver_code,)).fetchall()
    finally:
        conn.close()
    for raw in rows:
        row = dict(raw)
        if row["status"] not in (APPROVED, REVOKED):
            raise PlanningError("동인 승인 판본의 상태가 허용 계약과 다릅니다.")
        if _instant(row["approved_at"]) > cutoff:
            continue
        if row.get("revoked_at") and _instant(row["revoked_at"]) <= cutoff:
            continue
        try:
            event = ledger.get_event_strict(row["approval_event_id"])
            invalid = ledger.has_invalidating_child(
                row["approval_event_id"], (EVENT_REVOKED,), as_of=cutoff.isoformat())
        except (DecisionLedgerError, sqlite3.Error) as exc:
            raise PlanningError("동인 승인 원장을 확인하지 못했습니다.") from exc
        if (event.get("event_type") != EVENT_APPROVED or event.get("subject_type") != SUBJECT_TYPE
                or event.get("subject_id") != row["fingerprint"]):
            raise PlanningError("동인 판본과 승인 사건의 대상이 일치하지 않습니다.")
        try:
            impacts = json.loads(row["impacts_json"])
        except (TypeError, ValueError) as exc:
            raise PlanningError("동인 판본의 파급계수 본문을 읽지 못했습니다.") from exc
        sealed = fingerprint({**row, "impacts": impacts}, tenant_id=row["tenant_id"],
                             scope_node_id=row["scope_node_id"], entity_mode=row["entity_mode"])
        if sealed != row["fingerprint"]:
            raise PlanningError("동인 승인 판본의 내용 지문이 일치하지 않습니다.")
        event_binding = tuple(str(event.get(key) or "") for key in
                              ("actor_id", "tenant_id", "enterprise_scope_id", "entity_mode", "created_at"))
        release_binding = tuple(str(row.get(key) or "") for key in
                                ("approved_by", "tenant_id", "scope_node_id", "entity_mode", "approved_at"))
        if event_binding != release_binding:
            raise PlanningError("동인 승인 판본과 원장의 승인 결속값이 일치하지 않습니다.")
        if not invalid:
            return row
    return None
