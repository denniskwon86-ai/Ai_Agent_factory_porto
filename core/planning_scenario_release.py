"""Approved, immutable planning-scenario releases.

The editable ``scenarios`` and ``scenario_assumptions`` tables are authoring
state.  Ontology paths and management reports must not treat those drafts as
approved truth.  This module snapshots their semantic content, binds it to an
append-only approval event, and exposes only a release whose approval is still
alive.
"""
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
EVENT_APPROVED = "PLANNING_SCENARIO_APPROVED"
EVENT_REVOKED = "PLANNING_SCENARIO_REVOKED"
SUBJECT_TYPE = "planning_scenario_release"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlanningError("시나리오 판본의 유효 시각을 읽지 못했습니다.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source(store: PlanningStore, scenario_id: str) -> dict[str, Any]:
    conn = store._connect()
    try:
        # Scenario and assumptions are one approval material.  A concurrent edit
        # between the two SELECTs must not create a combination nobody reviewed.
        conn.execute("BEGIN")
        scenario = conn.execute(
            "SELECT scenario_id,name,org_id,baseline_kind,baseline_period,tenant_id,"
            "owner_organization_id,entity_mode FROM scenarios WHERE scenario_id=?",
            (scenario_id,)).fetchone()
        assumptions = conn.execute(
            "SELECT target_kind,target_code,operator,value,unit,rationale "
            "FROM scenario_assumptions WHERE scenario_id=? "
            "ORDER BY target_kind,target_code,operator,value,unit,rationale",
            (scenario_id,)).fetchall()
    finally:
        conn.close()
    if not scenario:
        raise PlanningError("승인할 시나리오를 찾을 수 없습니다.")
    row = dict(scenario)
    required = {
        "name": "시나리오 이름", "org_id": "대상 조직", "tenant_id": "tenant",
        "owner_organization_id": "조직 범위", "entity_mode": "실행 문맥",
        "baseline_kind": "기준선 종류",
    }
    missing = [label for key, label in required.items() if not str(row.get(key) or "").strip()]
    if missing:
        raise PlanningError("승인 전 필수 결속이 비어 있습니다: " + ", ".join(missing))
    if not assumptions:
        raise PlanningError("가정이 없는 빈 시나리오는 승인할 수 없습니다.")
    normalized = []
    for raw in assumptions:
        item = dict(raw)
        if not str(item.get("rationale") or "").strip():
            raise PlanningError("근거가 비어 있는 시나리오 가정은 승인할 수 없습니다.")
        normalized.append(item)
    return {**row, "assumptions": normalized}


def fingerprint(source: dict[str, Any]) -> str:
    material = {
        "scenario_id": str(source.get("scenario_id") or ""),
        "name": str(source.get("name") or ""),
        "org_id": str(source.get("org_id") or ""),
        "tenant_id": str(source.get("tenant_id") or ""),
        "scope_node_id": str(source.get("owner_organization_id") or ""),
        "entity_mode": str(source.get("entity_mode") or ""),
        "baseline_kind": str(source.get("baseline_kind") or ""),
        "baseline_period": str(source.get("baseline_period") or ""),
        "assumptions": source.get("assumptions") or [],
    }
    payload = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _public(row: dict[str, Any], *, idempotent: bool = False) -> dict[str, Any]:
    return {
        "scenario_id": row["scenario_id"], "version": int(row["version"]),
        "fingerprint": row["fingerprint"], "name": row["name"],
        "status": row["status"], "approved_by": row["approved_by"],
        "approved_at": row["approved_at"], "revoked_by": row.get("revoked_by", ""),
        "revoked_at": row.get("revoked_at", ""), "idempotent": idempotent,
    }


def approve(scenario_id: str, actor: str, rationale: str, *,
            store: Optional[PlanningStore] = None,
            ledger: Optional[DecisionLedger] = None) -> dict[str, Any]:
    store = store or planning_store
    ledger = ledger or decision_ledger
    if not str(actor or "").strip():
        raise PlanningError("시나리오 승인자 식별이 필요합니다.")
    if not str(rationale or "").strip():
        raise PlanningError("시나리오 승인 근거가 필요합니다.")
    source = _source(store, scenario_id)
    fp = fingerprint(source)
    conn = store._connect()
    try:
        active = conn.execute(
            "SELECT * FROM scenario_releases WHERE scenario_id=? AND status=? "
            "ORDER BY version DESC LIMIT 1", (scenario_id, APPROVED)).fetchone()
        if active:
            current = dict(active)
            if current["fingerprint"] == fp:
                return _public(current, idempotent=True)
            raise PlanningError("이미 승인된 다른 판본이 있습니다. 먼저 기존 판본을 철회하십시오.")
        previous = conn.execute(
            "SELECT COALESCE(MAX(version),0) FROM scenario_releases WHERE scenario_id=?",
            (scenario_id,)).fetchone()[0]
    finally:
        conn.close()

    event = ledger.append(
        event_type=EVENT_APPROVED, subject_type=SUBJECT_TYPE, subject_id=fp,
        actor_type="user", actor_id=actor, decision="APPROVE",
        rationale=str(rationale).strip(),
        evidence_refs=[{"scenario_id": scenario_id, "version": int(previous) + 1}],
        tenant_id=source["tenant_id"],
        enterprise_scope_id=source["owner_organization_id"],
        entity_mode=source["entity_mode"])
    approved_at = str(event["created_at"])
    release_id = allocate("scenario_release")[0]
    assumptions_json = json.dumps(
        source["assumptions"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        conn = store._connect()
        try:
            conn.execute(
                "INSERT INTO scenario_releases(release_id,scenario_id,version,fingerprint,name,"
                "org_id,tenant_id,scope_node_id,entity_mode,baseline_kind,baseline_period,"
                "assumptions_json,status,approved_by,approved_at,approval_event_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (release_id, scenario_id, int(previous) + 1, fp, source["name"],
                 source["org_id"], source["tenant_id"], source["owner_organization_id"],
                 source["entity_mode"], source["baseline_kind"],
                 source.get("baseline_period") or "", assumptions_json, APPROVED, actor,
                 approved_at, event["event_id"], approved_at))
            conn.commit()
            row = dict(conn.execute(
                "SELECT * FROM scenario_releases WHERE release_id=?", (release_id,)).fetchone())
        finally:
            conn.close()
    except Exception as exc:
        # The compensating child kills the approval even if the release insert failed.
        ledger.append(
            event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE, subject_id=fp,
            actor_type="system", actor_id=actor, decision="COMPENSATE",
            rationale=f"시나리오 판본 등록 실패: {type(exc).__name__}",
            parent_event_id=event["event_id"], tenant_id=source["tenant_id"],
            enterprise_scope_id=source["owner_organization_id"],
            entity_mode=source["entity_mode"])
        raise
    return _public(row)


def revoke(scenario_id: str, actor: str, rationale: str, *,
           store: Optional[PlanningStore] = None,
           ledger: Optional[DecisionLedger] = None) -> dict[str, Any]:
    store = store or planning_store
    ledger = ledger or decision_ledger
    if not str(actor or "").strip() or not str(rationale or "").strip():
        raise PlanningError("철회자와 철회 사유가 모두 필요합니다.")
    conn = store._connect()
    try:
        raw = conn.execute(
            "SELECT * FROM scenario_releases WHERE scenario_id=? AND status=? "
            "ORDER BY version DESC LIMIT 1", (scenario_id, APPROVED)).fetchone()
    finally:
        conn.close()
    if not raw:
        raise PlanningError("철회할 승인 시나리오 판본이 없습니다.")
    row = dict(raw)
    event = ledger.append(
        event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE, subject_id=row["fingerprint"],
        actor_type="user", actor_id=actor, decision="REVOKE",
        rationale=str(rationale).strip(), parent_event_id=row["approval_event_id"],
        tenant_id=row["tenant_id"], enterprise_scope_id=row["scope_node_id"],
        entity_mode=row["entity_mode"])
    revoked_at = str(event["created_at"])
    conn = store._connect()
    try:
        conn.execute(
            "UPDATE scenario_releases SET status=?,revoked_by=?,revoked_at=?,"
            "revocation_event_id=? WHERE release_id=? AND status=?",
            (REVOKED, actor, revoked_at, event["event_id"], row["release_id"], APPROVED))
        conn.commit()
        updated = dict(conn.execute(
            "SELECT * FROM scenario_releases WHERE release_id=?", (row["release_id"],)).fetchone())
    finally:
        conn.close()
    return _public(updated)


def effective_release(scenario_id: str, as_of: str = "", *,
                      store: Optional[PlanningStore] = None,
                      ledger: Optional[DecisionLedger] = None) -> Optional[dict[str, Any]]:
    """Return the latest approved release at ``as_of`` after ledger revalidation."""
    store = store or planning_store
    ledger = ledger or decision_ledger
    cutoff = _instant(as_of) if str(as_of or "").strip() else datetime.now(timezone.utc)
    conn = store._connect()
    try:
        rows = conn.execute(
            "SELECT * FROM scenario_releases WHERE scenario_id=? ORDER BY version DESC",
            (scenario_id,)).fetchall()
    finally:
        conn.close()
    for raw in rows:
        row = dict(raw)
        if str(row.get("status") or "") not in (APPROVED, REVOKED):
            raise PlanningError("시나리오 승인 판본의 상태가 허용 계약과 다릅니다.")
        if _instant(row["approved_at"]) > cutoff:
            continue
        if row.get("revoked_at") and _instant(row["revoked_at"]) <= cutoff:
            continue
        try:
            event = ledger.get_event_strict(row["approval_event_id"])
            invalidated = ledger.has_invalidating_child(
                row["approval_event_id"], (EVENT_REVOKED,), as_of=cutoff.isoformat())
        except (DecisionLedgerError, sqlite3.Error) as exc:
            raise PlanningError("시나리오 승인 원장을 확인하지 못했습니다.") from exc
        if not event or event.get("event_type") != EVENT_APPROVED:
            raise PlanningError("시나리오 판본의 승인 사건이 유효하지 않습니다.")
        if (event.get("subject_type") != SUBJECT_TYPE
                or event.get("subject_id") != row["fingerprint"]):
            raise PlanningError("시나리오 판본과 승인 사건의 대상이 일치하지 않습니다.")
        try:
            assumptions = json.loads(str(row.get("assumptions_json") or "[]"))
        except (TypeError, ValueError) as exc:
            raise PlanningError("시나리오 승인 판본의 가정 본문을 읽지 못했습니다.") from exc
        sealed = fingerprint({
            "scenario_id": row["scenario_id"], "name": row["name"], "org_id": row["org_id"],
            "tenant_id": row["tenant_id"], "owner_organization_id": row["scope_node_id"],
            "entity_mode": row["entity_mode"], "baseline_kind": row["baseline_kind"],
            "baseline_period": row["baseline_period"], "assumptions": assumptions,
        })
        if sealed != row["fingerprint"]:
            raise PlanningError("시나리오 승인 판본의 내용 지문이 일치하지 않습니다.")
        event_binding = (
            str(event.get("actor_id") or ""), str(event.get("tenant_id") or ""),
            str(event.get("enterprise_scope_id") or ""), str(event.get("entity_mode") or ""),
            str(event.get("created_at") or ""),
        )
        release_binding = (
            str(row.get("approved_by") or ""), str(row.get("tenant_id") or ""),
            str(row.get("scope_node_id") or ""), str(row.get("entity_mode") or ""),
            str(row.get("approved_at") or ""),
        )
        if event_binding != release_binding:
            raise PlanningError("시나리오 승인 판본과 원장의 승인 결속값이 일치하지 않습니다.")
        if invalidated:
            continue
        return row
    return None
