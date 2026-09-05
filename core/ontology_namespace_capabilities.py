"""Product truth for ontology namespace resolver and display readiness.

This is deliberately separate from model installation status.  An approved
relation dictionary can be installed while a business-object namespace is not
yet connected to its authoritative store.  Reporting the model as READY in
that state must not make the UI imply that every namespace is queryable.

The public status contains implementation counts only.  It never counts hidden
business objects, so it does not disclose that another organisation has data.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Tuple


READY = "READY"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
CONTRACT_REQUIRED = "CONTRACT_REQUIRED"

NAMESPACES = ("ecm", "mdm", "dataset", "external", "g4", "decision", "knowledge")

# The approved design contract's object vocabulary.  Runtime deployment must
# not depend on a docs/ path, so this compact copy is checked against the JSON
# contract by a regression test.
CONTRACT_OBJECT_TYPES: Dict[str, Tuple[str, ...]] = {
    "ecm": ("organization-node",),
    "mdm": (
        "account", "bom-line", "cost-center", "equipment", "location",
        "logistics-reference", "material", "routing-operation", "supplier",
    ),
    "dataset": (
        "cost-record", "customs-clearance", "finance-document", "inventory-snapshot",
        "ledger-line", "partner-submission", "procurement-contract", "production-batch",
        "production-plan-line", "purchase-order-line", "sales-line", "shipment",
        "shipment-milestone", "transport-event",
    ),
    "external": ("external-observation",),
    "g4": ("driver",),
    "decision": ("decision", "scenario"),
    "knowledge": ("reference-asset",),
}

# Actual product resolver coverage.  These are object *types*, not row counts.
# Hidden or out-of-scope object counts are never exposed here.
RESOLVER_OBJECT_TYPES: Dict[str, Tuple[str, ...]] = {
    "ecm": ("organization-node",),
    "mdm": (
        "account", "bom-line", "cost-center", "equipment", "location",
        "logistics-reference", "material", "routing-operation", "supplier",
    ),
    "dataset": (
        "cost-record", "customs-clearance", "finance-document", "inventory-snapshot",
        "ledger-line", "partner-submission", "procurement-contract", "production-batch",
        "production-plan-line", "purchase-order-line", "sales-line", "shipment",
        "shipment-milestone", "transport-event",
    ),
    "external": ("external-observation",),
    "g4": ("driver",),
    "decision": ("decision", "scenario"),
    "knowledge": ("reference-asset",),
}

# A resolver may find an object while still lacking a trustworthy human label.
# Only types with deterministic, ID-free human descriptions belong here.
DISPLAY_OBJECT_TYPES: Dict[str, Tuple[str, ...]] = {
    "ecm": ("organization-node",),
    "mdm": RESOLVER_OBJECT_TYPES["mdm"],
    "dataset": RESOLVER_OBJECT_TYPES["dataset"],
    "external": RESOLVER_OBJECT_TYPES["external"],
    "g4": RESOLVER_OBJECT_TYPES["g4"],
    "decision": RESOLVER_OBJECT_TYPES["decision"],
    "knowledge": RESOLVER_OBJECT_TYPES["knowledge"],
}

LABELS = {
    "ecm": "회사·조직",
    "mdm": "기준정보",
    "dataset": "업무 데이터",
    "external": "대외정보",
    "g4": "경영 동인",
    "decision": "시나리오·의사결정",
    "knowledge": "승인 지식",
}

NEXT_ACTION = {
    "ecm": "회사·조직 정본 연결 유지와 명칭 변경 지문을 감시",
    "mdm": "9종 인증판 색인과 원가센터 집합·명칭 계약을 유지",
    "dataset": "14종 인증판 색인과 표시 계약을 유지하고 현재 정본 물질화를 감시",
    "external": "인증된 대외 관측값 색인을 물질화하고 공표 출처 판을 감시",
    "g4": "승인 동인 판본의 원장·조직 범위 결속을 유지",
    "decision": "의사결정 안건과 승인 시나리오 판본의 원장·범위 결속을 유지",
    "knowledge": "옛 문자열 승인 자산을 원문 해시·원장·조직 문맥에 재승인",
}


def _coverage(target: Tuple[str, ...], ready: Tuple[str, ...]) -> str:
    if not target:
        return CONTRACT_REQUIRED
    if len(ready) == len(target) and set(ready) == set(target):
        return READY
    return PARTIAL if ready else BLOCKED


def _message(namespace: str, resolver_status: str, display_status: str,
             target_count: int, resolver_count: int, display_count: int) -> str:
    if resolver_status == CONTRACT_REQUIRED:
        return "표시할 업무 객체 유형 계약이 아직 없습니다. 데이터가 없다는 뜻이 아닙니다."
    if resolver_status == BLOCKED:
        return "정본 저장소와 Resolver가 아직 연결되지 않았습니다. 데이터가 없다는 뜻이 아닙니다."
    if resolver_status == PARTIAL:
        return (f"계약 대상 {target_count}종 중 {resolver_count}종만 조회할 수 있고 "
                f"{display_count}종만 사람용 설명이 준비됐습니다.")
    if display_status != READY:
        return "업무 객체는 조회할 수 있지만 사람용 표시 설명 계약은 아직 준비 중입니다."
    return "정본 조회와 사람용 표시 설명이 모두 준비됐습니다."


def runtime_status(
        materialized: Optional[Mapping[str, Tuple[str, ...]]] = None) -> dict:
    """Return implementation readiness and, when supplied, live materialization.

    ``materialized`` contains object *types* only.  It deliberately never exposes
    row counts, IDs, or the existence of another organisation's individual data.
    """
    rows = []
    for namespace in NAMESPACES:
        target = tuple(sorted(CONTRACT_OBJECT_TYPES.get(namespace, ())))
        resolver = tuple(sorted(RESOLVER_OBJECT_TYPES.get(namespace, ())))
        display = tuple(sorted(DISPLAY_OBJECT_TYPES.get(namespace, ())))
        live = tuple(sorted((materialized or {}).get(namespace, ())))
        resolver_status = _coverage(target, resolver)
        display_status = _coverage(target, display)
        message = _message(namespace, resolver_status, display_status,
                           len(target), len(resolver), len(display))
        if materialized is not None and resolver and len(live) < len(resolver):
            message = (f"구현된 {len(resolver)}종 중 현재 정본 결속은 {len(live)}종입니다. "
                       "데이터가 없다는 뜻이 아니라 현재 정본과의 명시적 결속이 필요합니다.")
        rows.append({
            "namespace": namespace,
            "label": LABELS[namespace],
            "contract_object_type_count": len(target),
            "resolver_object_type_count": len(resolver),
            "display_object_type_count": len(display),
            "materialized_object_type_count": len(live),
            "resolver_status": resolver_status,
            "display_status": display_status,
            "message": message,
            "next_action": NEXT_ACTION[namespace],
        })

    target_total = sum(r["contract_object_type_count"] for r in rows)
    resolver_total = sum(r["resolver_object_type_count"] for r in rows)
    display_total = sum(r["display_object_type_count"] for r in rows)
    materialized_total = sum(r["materialized_object_type_count"] for r in rows)
    fully_ready = sum(1 for r in rows
                      if r["resolver_status"] == READY and r["display_status"] == READY)
    available = sum(1 for r in rows if r["resolver_object_type_count"] > 0)
    overall = READY if fully_ready == len(rows) else (PARTIAL if available else BLOCKED)
    return {
        "status": overall,
        "namespace_count": len(rows),
        "resolver_available_namespace_count": available,
        "fully_ready_namespace_count": fully_ready,
        "contract_object_type_count": target_total,
        "resolver_object_type_count": resolver_total,
        "display_object_type_count": display_total,
        "materialized_object_type_count": materialized_total,
        "namespaces": rows,
    }
