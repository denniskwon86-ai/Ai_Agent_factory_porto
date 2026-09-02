"""Versioned, ledger-backed contract for translating operating metrics to accounts.

This module deliberately does not calculate profit, cash flow, or account balances.  It
only records the human-approved mapping boundary that a later financial model must use.
An absent, expired, tampered, or revoked contract is therefore a closed gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional


EVENT_APPROVED = "FINANCIAL_BRIDGE_APPROVED"
EVENT_REVOKED = "FINANCIAL_BRIDGE_REVOKED"
SUBJECT_TYPE = "financial_bridge_contract"

DRAFT = "DRAFT"
APPROVED = "APPROVED"
SUPERSEDED = "SUPERSEDED"
REVOKED = "REVOKED"

REQUIRED_RULES = (
    "purchase_working_capital",
    "production_margin",
    "revenue_recognition",
    "currency_translation",
)
EXPECTED_SOURCE_METRICS = {
    "purchase_working_capital": ("in_transit_qty",),
    "production_margin": ("producible_qty", "shortage_qty"),
    "revenue_recognition": ("revenue_shift_days",),
    "currency_translation": (
        "exchange_rate", "reporting_currency", "transaction_currency"),
}

MODEL_VERSION = "financial-bridge-1.0"
REPORTING_CURRENCY = "KRW"
EXCHANGE_RATE_SOURCE = "EXT-01"
SOURCE_DATASETS = ("MDM-07", "EXT-01")
RULE_FORMULAS = {
    "purchase_working_capital": "BRIDGE.PURCHASE_WC.v1",
    "production_margin": "BRIDGE.PRODUCTION_MARGIN.v1",
    "revenue_recognition": "BRIDGE.REVENUE_TIMING.v1",
    "currency_translation": "BRIDGE.CURRENCY_TRANSLATION.v1",
}
RULE_EVIDENCE = {
    "purchase_working_capital": ("MDM-07",),
    "production_margin": ("MDM-05", "MDM-07"),
    "revenue_recognition": ("MDM-07", "SLS-01"),
    "currency_translation": ("EXT-01", "MDM-07"),
}
RULE_ACCOUNT_ELEMENTS = {
    "purchase_working_capital": ("INVENTORY", "AP"),
    "production_margin": ("MATERIAL_COST", "CONVERSION_COST"),
    "revenue_recognition": ("REVENUE", "AR"),
}
RULE_LABELS = {
    "purchase_working_capital": "구매·운전자본 영향",
    "production_margin": "생산·마진 영향",
    "revenue_recognition": "매출 인식 영향",
    "currency_translation": "환율 환산",
}

_ACCOUNT_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,31}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

_DDL = """
CREATE TABLE IF NOT EXISTS financial_bridge_contracts (
    contract_id       TEXT PRIMARY KEY,
    tenant_id         TEXT NOT NULL,
    instance_id       TEXT NOT NULL,
    scope_node_id     TEXT NOT NULL,
    entity_mode       TEXT NOT NULL,
    revision          INTEGER NOT NULL,
    status            TEXT NOT NULL,
    fingerprint       TEXT NOT NULL,
    contract_json     TEXT NOT NULL,
    effective_from    TEXT NOT NULL,
    effective_to      TEXT NOT NULL DEFAULT '',
    drafted_by        TEXT NOT NULL,
    drafted_at        TEXT NOT NULL,
    approved_by       TEXT NOT NULL DEFAULT '',
    approved_at       TEXT NOT NULL DEFAULT '',
    ledger_event_id   TEXT NOT NULL DEFAULT '',
    rationale         TEXT NOT NULL DEFAULT '',
    updated_at        TEXT NOT NULL,
    CHECK (status IN ('DRAFT','APPROVED','SUPERSEDED','REVOKED')),
    UNIQUE (tenant_id, instance_id, scope_node_id, entity_mode, revision)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_bridge_approved
ON financial_bridge_contracts(tenant_id, instance_id, scope_node_id, entity_mode)
WHERE status='APPROVED';
CREATE INDEX IF NOT EXISTS idx_financial_bridge_context
ON financial_bridge_contracts(tenant_id, instance_id, scope_node_id, entity_mode, revision);
"""


class FinancialBridgeContractError(ValueError):
    """The requested contract transition violates the product contract."""


class FinancialBridgeStoreError(RuntimeError):
    """The contract or its ledger evidence could not be read or written."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instant(value: str, field: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        got = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise FinancialBridgeContractError(f"{field} must be an ISO-8601 timestamp.") from exc
    if got.tzinfo is None:
        raise FinancialBridgeContractError(f"{field} must include a timezone.")
    return got.astimezone(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_proposal(*, account_rows: List[Mapping[str, Any]],
                   account_snapshot_id: str,
                   exchange_rate_snapshot_id: str) -> Dict[str, Any]:
    """인증된 계정과목 행에서 사용자가 검토할 브리지 초안을 만든다.

    계정 코드는 사용자가 입력하지 않는다. 정본의 cost_element 의미를 기준으로
    서버가 고르고, 같은 의미가 없거나 둘 이상이면 임의 선택하지 않고 막는다.
    """
    account_sid = str(account_snapshot_id or "").strip()
    fx_sid = str(exchange_rate_snapshot_id or "").strip()
    if not account_sid or not fx_sid:
        raise FinancialBridgeContractError(
            "MDM-07 계정과목판과 EXT-01 환율판이 모두 인증되어야 합니다.")

    by_element: Dict[str, List[Dict[str, str]]] = {}
    for raw in account_rows:
        active = str(raw.get("active", "")).strip().casefold()
        if active not in {"true", "1", "yes", "y"}:
            continue
        code = str(raw.get("account_id") or "").strip().upper()
        name = str(raw.get("account_name") or "").strip()
        element = str(raw.get("cost_element") or "").strip().upper()
        currency = str(raw.get("currency") or "").strip().upper()
        if not code or not name or not element:
            continue
        if not _ACCOUNT_RE.fullmatch(code):
            raise FinancialBridgeContractError(
                f"MDM-07에 유효하지 않은 계정 코드가 있습니다: {code}")
        if currency and currency != REPORTING_CURRENCY:
            continue
        by_element.setdefault(element, []).append({
            "account_code": code,
            "account_name": name,
            "account_type": str(raw.get("account_type") or "").strip(),
            "cost_element": element,
        })

    selected: Dict[str, Dict[str, str]] = {}
    needed = sorted({v for values in RULE_ACCOUNT_ELEMENTS.values() for v in values})
    for element in needed:
        choices = by_element.get(element, [])
        if len(choices) != 1:
            raise FinancialBridgeContractError(
                f"MDM-07의 {element} 계정은 정확히 1개여야 합니다(현재 {len(choices)}개).")
        selected[element] = choices[0]

    rules: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    all_accounts = sorted({selected[e]["account_code"] for e in needed})
    for rule_id in REQUIRED_RULES:
        elements = RULE_ACCOUNT_ELEMENTS.get(rule_id, ())
        accounts = ([selected[e]["account_code"] for e in elements]
                    if elements else all_accounts)
        rule = {
            "rule_id": rule_id,
            "source_metrics": list(EXPECTED_SOURCE_METRICS[rule_id]),
            "target_account_codes": accounts,
            "formula_ref": RULE_FORMULAS[rule_id],
            "evidence_refs": list(RULE_EVIDENCE[rule_id]),
        }
        rules.append(rule)
        summaries.append({
            "rule_id": rule_id,
            "label": RULE_LABELS[rule_id],
            "target_accounts": [
                {"name": row["account_name"], "type": row["account_type"]}
                for row in (selected[e] for e in elements)
            ] if elements else [
                {"name": selected[e]["account_name"],
                 "type": selected[e]["account_type"]} for e in needed
            ],
        })
    contract = normalize_contract({
        "model_version": MODEL_VERSION,
        "reporting_currency": REPORTING_CURRENCY,
        "exchange_rate_source": EXCHANGE_RATE_SOURCE,
        "source_snapshots": {"MDM-07": account_sid, "EXT-01": fx_sid},
        "rules": rules,
    })
    material = {"contract": contract, "rule_summaries": summaries}
    return {**material, "proposal_fingerprint": fingerprint(material)}


def normalize_contract(payload: Mapping[str, Any]) -> Dict[str, Any]:
    allowed = {"model_version", "reporting_currency", "exchange_rate_source",
               "source_snapshots", "rules"}
    extra = sorted(set(payload) - allowed)
    if extra:
        raise FinancialBridgeContractError(f"Unsupported contract fields: {extra}")
    model_version = str(payload.get("model_version") or "").strip()
    reporting_currency = str(payload.get("reporting_currency") or "").strip().upper()
    exchange_rate_source = str(payload.get("exchange_rate_source") or "").strip()
    source_snapshots = payload.get("source_snapshots")
    if not model_version:
        raise FinancialBridgeContractError("model_version is required.")
    if not _CURRENCY_RE.fullmatch(reporting_currency):
        raise FinancialBridgeContractError("reporting_currency must be a three-letter code.")
    if exchange_rate_source != EXCHANGE_RATE_SOURCE:
        raise FinancialBridgeContractError(
            f"exchange_rate_source must be {EXCHANGE_RATE_SOURCE}.")
    if not isinstance(source_snapshots, Mapping):
        raise FinancialBridgeContractError("source_snapshots is required.")
    if set(source_snapshots) != set(SOURCE_DATASETS):
        raise FinancialBridgeContractError(
            f"source_snapshots must contain exactly {list(SOURCE_DATASETS)}.")
    normalized_sources = {
        key: str(source_snapshots.get(key) or "").strip() for key in SOURCE_DATASETS}
    if any(not value for value in normalized_sources.values()):
        raise FinancialBridgeContractError("source snapshot ids must not be empty.")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise FinancialBridgeContractError("rules must be a list.")
    rules: Dict[str, Dict[str, Any]] = {}
    allowed_rule = {"rule_id", "source_metrics", "target_account_codes",
                    "formula_ref", "evidence_refs"}
    for raw in raw_rules:
        if not isinstance(raw, Mapping):
            raise FinancialBridgeContractError("Every rule must be an object.")
        unknown = sorted(set(raw) - allowed_rule)
        if unknown:
            raise FinancialBridgeContractError(f"Unsupported rule fields: {unknown}")
        rule_id = str(raw.get("rule_id") or "").strip()
        if rule_id in rules:
            raise FinancialBridgeContractError(f"Duplicate financial bridge rule: {rule_id}")
        if rule_id not in REQUIRED_RULES:
            raise FinancialBridgeContractError(f"Unknown financial bridge rule: {rule_id}")
        metrics = tuple(sorted({str(v).strip() for v in raw.get("source_metrics") or []
                                if str(v).strip()}))
        if metrics != EXPECTED_SOURCE_METRICS[rule_id]:
            raise FinancialBridgeContractError(
                f"{rule_id} source_metrics must be {list(EXPECTED_SOURCE_METRICS[rule_id])}.")
        accounts = sorted({str(v).strip().upper()
                           for v in raw.get("target_account_codes") or [] if str(v).strip()})
        if not accounts or any(not _ACCOUNT_RE.fullmatch(v) for v in accounts):
            raise FinancialBridgeContractError(
                f"{rule_id} requires valid target_account_codes.")
        formula_ref = str(raw.get("formula_ref") or "").strip()
        evidence = sorted({str(v).strip() for v in raw.get("evidence_refs") or []
                           if str(v).strip()})
        if not formula_ref or not evidence:
            raise FinancialBridgeContractError(
                f"{rule_id} requires formula_ref and evidence_refs.")
        if formula_ref != RULE_FORMULAS[rule_id]:
            raise FinancialBridgeContractError(
                f"{rule_id} formula_ref must be {RULE_FORMULAS[rule_id]}.")
        if tuple(evidence) != tuple(sorted(RULE_EVIDENCE[rule_id])):
            raise FinancialBridgeContractError(
                f"{rule_id} evidence_refs must be {list(RULE_EVIDENCE[rule_id])}.")
        rules[rule_id] = {
            "rule_id": rule_id,
            "source_metrics": list(metrics),
            "target_account_codes": accounts,
            "formula_ref": formula_ref,
            "evidence_refs": evidence,
        }
    missing = [rule_id for rule_id in REQUIRED_RULES if rule_id not in rules]
    if missing:
        raise FinancialBridgeContractError(f"Missing financial bridge rules: {missing}")
    return {
        "model_version": model_version,
        "reporting_currency": reporting_currency,
        "exchange_rate_source": exchange_rate_source,
        "source_snapshots": normalized_sources,
        "rules": [rules[rule_id] for rule_id in REQUIRED_RULES],
    }


class FinancialBridgeContractStore:
    def __init__(self, repository=None, ledger=None):
        self._repo_override = repository
        self._ledger_override = ledger
        self._lock = threading.RLock()

    @property
    def _repo(self):
        if self._repo_override is not None:
            return self._repo_override
        from core.enterprise_context.repository import ecm_repository
        return ecm_repository

    @property
    def _ledger(self):
        if self._ledger_override is not None:
            return self._ledger_override
        from core.decision_ledger import decision_ledger
        return decision_ledger

    def _connect(self) -> sqlite3.Connection:
        try:
            path = str(self._repo.db_path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            conn = sqlite3.connect(path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=15000")
            conn.executescript(_DDL)
            return conn
        except (OSError, sqlite3.Error) as exc:
            raise FinancialBridgeStoreError(
                f"Could not prepare the financial bridge contract store: {exc}") from exc

    @staticmethod
    def _public(row: sqlite3.Row | Mapping[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        try:
            out["contract"] = json.loads(out.pop("contract_json"))
        except (TypeError, ValueError) as exc:
            raise FinancialBridgeStoreError("Could not read the financial bridge contract.") from exc
        return out

    def require(self, contract_id: str) -> Dict[str, Any]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM financial_bridge_contracts WHERE contract_id=?",
                    (str(contract_id or "").strip(),)).fetchone()
        except sqlite3.Error as exc:
            raise FinancialBridgeStoreError(f"Could not read the financial bridge contract: {exc}") from exc
        if not row:
            raise FinancialBridgeContractError("Financial bridge contract not found.")
        return self._public(row)

    def list_for(self, *, tenant_id: str, instance_id: str, scope_node_id: str,
                 entity_mode: str) -> List[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM financial_bridge_contracts WHERE tenant_id=? AND "
                    "instance_id=? AND scope_node_id=? AND entity_mode=? "
                    "ORDER BY revision DESC",
                    (tenant_id, instance_id, scope_node_id, entity_mode)).fetchall()
        except sqlite3.Error as exc:
            raise FinancialBridgeStoreError(f"Could not list financial bridge contracts: {exc}") from exc
        return [self._public(row) for row in rows]

    def create_draft(self, *, tenant_id: str, instance_id: str, scope_node_id: str,
                     entity_mode: str, contract: Mapping[str, Any], effective_from: str,
                     effective_to: str = "", actor: str) -> Dict[str, Any]:
        who = str(actor or "").strip()
        required = (tenant_id, instance_id, scope_node_id, entity_mode, who)
        if any(not str(v or "").strip() for v in required):
            raise FinancialBridgeContractError("Contract context and drafter are required.")
        start = _instant(effective_from, "effective_from")
        end = _instant(effective_to, "effective_to") if str(effective_to or "").strip() else None
        if end and end <= start:
            raise FinancialBridgeContractError("effective_to must be later than effective_from.")
        normalized = normalize_contract(contract)
        body = {
            "context": {"tenant_id": tenant_id, "instance_id": instance_id,
                        "scope_node_id": scope_node_id, "entity_mode": entity_mode},
            "effective_from": start.isoformat(),
            "effective_to": end.isoformat() if end else "",
            "contract": normalized,
        }
        fp = fingerprint(body)
        now = _now()
        contract_id = "fbc_" + uuid.uuid4().hex[:18]
        try:
            with self._lock, self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                revision = int(conn.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 FROM financial_bridge_contracts "
                    "WHERE tenant_id=? AND instance_id=? AND scope_node_id=? AND entity_mode=?",
                    (tenant_id, instance_id, scope_node_id, entity_mode)).fetchone()[0])
                conn.execute(
                    "INSERT INTO financial_bridge_contracts "
                    "(contract_id,tenant_id,instance_id,scope_node_id,entity_mode,revision,status,"
                    "fingerprint,contract_json,effective_from,effective_to,drafted_by,drafted_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (contract_id, tenant_id, instance_id, scope_node_id, entity_mode, revision,
                     DRAFT, fp, _canonical(normalized), start.isoformat(),
                     end.isoformat() if end else "", who, now, now))
                conn.commit()
        except sqlite3.Error as exc:
            raise FinancialBridgeStoreError(f"Could not save financial bridge draft: {exc}") from exc
        return self.require(contract_id)

    def approve(self, contract_id: str, *, seen_fingerprint: str, actor: str,
                rationale: str) -> Dict[str, Any]:
        item = self.require(contract_id)
        who, why = str(actor or "").strip(), str(rationale or "").strip()
        if item["status"] == APPROVED:
            return {**item, "idempotent": True}
        if item["status"] != DRAFT:
            raise FinancialBridgeContractError("Only a draft contract can be approved.")
        if not who or not why:
            raise FinancialBridgeContractError("Approver and rationale are required.")
        if who.casefold() == str(item["drafted_by"]).strip().casefold():
            raise FinancialBridgeContractError("The drafter cannot approve the same contract.")
        if str(seen_fingerprint or "").strip() != item["fingerprint"]:
            raise FinancialBridgeContractError("The contract changed after it was reviewed.")
        previous = next((
            row for row in self.list_for(
                tenant_id=item["tenant_id"], instance_id=item["instance_id"],
                scope_node_id=item["scope_node_id"], entity_mode=item["entity_mode"])
            if row["status"] == APPROVED and row["contract_id"] != item["contract_id"]), None)
        event = None
        try:
            event = self._ledger.append(
                event_type=EVENT_APPROVED, subject_type=SUBJECT_TYPE,
                subject_id=item["fingerprint"], actor_type="user", actor_id=who,
                decision="APPROVED", rationale=why,
                evidence_refs=[{"contract_id": item["contract_id"],
                                "scope_node_id": item["scope_node_id"]}],
                tenant_id=item["tenant_id"], entity_mode=item["entity_mode"])
            if previous and not self._ledger.has_invalidating_child(
                    previous["ledger_event_id"], (EVENT_REVOKED,)):
                self._ledger.append(
                    event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE,
                    subject_id=previous["fingerprint"], actor_type="user", actor_id=who,
                    decision="REVOKED", rationale=(
                        f"Superseded by financial bridge contract {item['contract_id']}"),
                    parent_event_id=previous["ledger_event_id"],
                    tenant_id=previous["tenant_id"], entity_mode=previous["entity_mode"])
        except Exception as exc:
            if event is not None:
                try:
                    self._ledger.append(
                        event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE,
                        subject_id=item["fingerprint"], actor_type="system",
                        actor_id="system@afs.invalid", decision="REVOKED",
                        rationale=f"Supersession failed and approval was cancelled: {exc}",
                        parent_event_id=event["event_id"], tenant_id=item["tenant_id"],
                        entity_mode=item["entity_mode"])
                except Exception as undo:
                    raise FinancialBridgeStoreError(
                        f"Financial bridge approval, supersession, and compensation failed: "
                        f"{exc}; {undo}") from undo
            raise FinancialBridgeStoreError(
                f"Could not record financial bridge approval or supersession: {exc}") from exc
        now = _now()
        try:
            with self._lock, self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE financial_bridge_contracts SET status=?,updated_at=? WHERE tenant_id=? "
                    "AND instance_id=? AND scope_node_id=? AND entity_mode=? AND status=?",
                    (SUPERSEDED, now, item["tenant_id"], item["instance_id"],
                     item["scope_node_id"], item["entity_mode"], APPROVED))
                changed = conn.execute(
                    "UPDATE financial_bridge_contracts SET status=?,approved_by=?,approved_at=?,"
                    "ledger_event_id=?,rationale=?,updated_at=? WHERE contract_id=? AND status=?",
                    (APPROVED, who, now, event["event_id"], why, now,
                     item["contract_id"], DRAFT)).rowcount
                if changed != 1:
                    raise sqlite3.IntegrityError("draft state changed during approval")
                conn.commit()
        except Exception as exc:
            try:
                self._ledger.append(
                    event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE,
                    subject_id=item["fingerprint"], actor_type="system",
                    actor_id="system@afs.invalid", decision="REVOKED",
                    rationale=f"Approval storage failed and was cancelled: {exc}",
                    parent_event_id=event["event_id"], tenant_id=item["tenant_id"],
                    entity_mode=item["entity_mode"])
            except Exception as undo:
                raise FinancialBridgeStoreError(
                    f"Approval storage and compensation both failed: {exc}; {undo}") from undo
            raise FinancialBridgeStoreError(f"Approval storage failed and was cancelled: {exc}") from exc
        return {**self.require(contract_id), "idempotent": False}

    def revoke(self, contract_id: str, *, actor: str, rationale: str) -> Dict[str, Any]:
        item = self.require(contract_id)
        who, why = str(actor or "").strip(), str(rationale or "").strip()
        if item["status"] == REVOKED:
            return {**item, "idempotent": True}
        if item["status"] != APPROVED:
            raise FinancialBridgeContractError("Only an approved contract can be revoked.")
        if not who or not why:
            raise FinancialBridgeContractError("Revoker and rationale are required.")
        try:
            self._ledger.append(
                event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE,
                subject_id=item["fingerprint"], actor_type="user", actor_id=who,
                decision="REVOKED", rationale=why,
                parent_event_id=item["ledger_event_id"], tenant_id=item["tenant_id"],
                entity_mode=item["entity_mode"])
        except Exception as exc:
            raise FinancialBridgeStoreError(f"Could not record financial bridge revocation: {exc}") from exc
        try:
            with self._lock, self._connect() as conn:
                changed = conn.execute(
                    "UPDATE financial_bridge_contracts SET status=?,updated_at=? "
                    "WHERE contract_id=? AND status=?",
                    (REVOKED, _now(), item["contract_id"], APPROVED)).rowcount
                if changed != 1:
                    raise sqlite3.IntegrityError("approved state changed during revocation")
                conn.commit()
        except sqlite3.Error as exc:
            raise FinancialBridgeStoreError(
                f"Revocation was recorded but local state update failed: {exc}") from exc
        return {**self.require(contract_id), "idempotent": False}

    def effective(self, *, tenant_id: str, instance_id: str, scope_node_id: str,
                  entity_mode: str, as_of: str) -> Optional[Dict[str, Any]]:
        moment = _instant(as_of, "as_of")
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM financial_bridge_contracts WHERE tenant_id=? AND instance_id=? "
                    "AND scope_node_id=? AND entity_mode=? AND status=? ORDER BY revision DESC LIMIT 1",
                    (tenant_id, instance_id, scope_node_id, entity_mode, APPROVED)).fetchone()
        except sqlite3.Error as exc:
            raise FinancialBridgeStoreError(f"Could not read effective financial bridge: {exc}") from exc
        if not row:
            return None
        item = self._public(row)
        start = _instant(item["effective_from"], "effective_from")
        end = _instant(item["effective_to"], "effective_to") if item["effective_to"] else None
        if moment < start or (end and moment >= end):
            return None
        try:
            normalized = normalize_contract(item["contract"])
        except FinancialBridgeContractError as exc:
            raise FinancialBridgeStoreError(
                f"Stored financial bridge contract is invalid: {exc}") from exc
        expected = fingerprint({
            "context": {"tenant_id": tenant_id, "instance_id": instance_id,
                        "scope_node_id": scope_node_id, "entity_mode": entity_mode},
            "effective_from": start.isoformat(), "effective_to": end.isoformat() if end else "",
            "contract": normalized,
        })
        if expected != item["fingerprint"]:
            raise FinancialBridgeStoreError("Financial bridge contract fingerprint mismatch.")
        try:
            event = self._ledger.get_event_strict(item["ledger_event_id"])
            invalid = self._ledger.has_invalidating_child(
                item["ledger_event_id"], (EVENT_REVOKED,))
        except Exception as exc:
            raise FinancialBridgeStoreError(f"Could not verify financial bridge approval: {exc}") from exc
        if invalid:
            return None
        if (event.get("event_type") != EVENT_APPROVED
                or event.get("subject_type") != SUBJECT_TYPE
                or event.get("subject_id") != item["fingerprint"]):
            raise FinancialBridgeStoreError("Financial bridge approval target mismatch.")
        return item


financial_bridge_contracts = FinancialBridgeContractStore()
