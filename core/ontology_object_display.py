"""Human-readable ontology object descriptors derived from sealed dataset rows.

The ontology runtime does not own business-object bodies.  Dataset objects live in
certified snapshots, so their display descriptor must be derived from that exact
snapshot instead of being copied into a second mutable catalogue.

No object ID is used as a display fallback.  If the sealed row cannot be read or
described deterministically, callers must fail closed rather than expose the ID.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict

from core.data_preparation import scope_index


class ObjectDisplayIntegrityError(RuntimeError):
    """A sealed object row cannot produce a trustworthy display descriptor."""


@dataclass(frozen=True)
class ObjectDisplayDescriptor:
    display_name: str
    display_fingerprint: str


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def describe_ecm_object(*, object_id: str, node_name: str, entity_id: str,
                        entity_name: str, entity_mode: str) -> ObjectDisplayDescriptor:
    """Describe an organization node from the same ECM records used for scope.

    The display text is not object identity.  It is sealed separately so a renamed
    organization or a node moved to another entity cannot keep an old description.
    Internal IDs are fingerprint material only and never a display fallback.
    """
    node_label = " ".join(str(node_name or "").split()).strip()
    entity_label = " ".join(str(entity_name or "").split()).strip()
    if not node_label or not entity_label:
        raise ObjectDisplayIntegrityError("조직 객체의 사람용 명칭이 비어 있습니다.")
    display_name = (node_label if node_label == entity_label
                    else f"{entity_label} · {node_label}")
    if object_id and object_id in display_name:
        raise ObjectDisplayIntegrityError("조직 객체 표시 설명에 내부 객체 ID가 포함됐습니다.")
    material = {
        "namespace": "ecm",
        "object_type": "organization-node",
        "object_id": str(object_id or ""),
        "node_name": node_label,
        "entity_id": str(entity_id or ""),
        "entity_name": entity_label,
        "entity_mode": str(entity_mode or ""),
        "display_name": display_name,
    }
    return ObjectDisplayDescriptor(
        display_name=display_name,
        display_fingerprint=hashlib.sha256(
            _canonical(material).encode("utf-8")).hexdigest(),
    )


def describe_decision_object(*, object_id: str, question: str, evidence_hash: str,
                             package_version: int, status: str, outcome: str,
                             updated_at: str) -> ObjectDisplayDescriptor:
    """Describe a decision case without exposing its internal identifier.

    The question is the human identity of a decision case.  The evidence hash,
    package version and lifecycle state are fingerprint material: changing any
    of them must invalidate a previously rendered descriptor even when the
    question text stays the same.
    """
    normalized = " ".join(str(question or "").split()).strip()
    if not normalized:
        raise ObjectDisplayIntegrityError("의사결정 안건의 결정 질문이 비어 있습니다.")
    if object_id and object_id in normalized:
        raise ObjectDisplayIntegrityError("의사결정 표시 설명에 내부 객체 ID가 포함됐습니다.")
    if not str(evidence_hash or "").strip():
        raise ObjectDisplayIntegrityError("의사결정 안건의 근거 지문이 비어 있습니다.")
    rendered = normalized if len(normalized) <= 96 else normalized[:95].rstrip() + "…"
    display_name = f"의사결정 안건 · {rendered}"
    material = {
        "namespace": "decision",
        "object_type": "decision",
        "object_id": str(object_id or ""),
        "question": normalized,
        "evidence_hash": str(evidence_hash or ""),
        "package_version": int(package_version),
        "status": str(status or ""),
        "outcome": str(outcome or ""),
        "updated_at": str(updated_at or ""),
        "display_name": display_name,
    }
    return ObjectDisplayDescriptor(
        display_name=display_name,
        display_fingerprint=hashlib.sha256(
            _canonical(material).encode("utf-8")).hexdigest(),
    )


def describe_scenario_object(*, object_id: str, name: str, version: int,
                             fingerprint: str, baseline_kind: str,
                             baseline_period: str, approved_at: str) -> ObjectDisplayDescriptor:
    """Describe an approved scenario release, never its mutable draft row."""
    normalized = " ".join(str(name or "").split()).strip()
    if not normalized:
        raise ObjectDisplayIntegrityError("승인 시나리오의 이름이 비어 있습니다.")
    if object_id and object_id in normalized:
        raise ObjectDisplayIntegrityError("시나리오 표시 설명에 내부 객체 ID가 포함됐습니다.")
    if not str(fingerprint or "").strip() or int(version or 0) < 1:
        raise ObjectDisplayIntegrityError("시나리오 승인 판본의 지문 또는 판 번호가 없습니다.")
    period = str(baseline_period or "").strip()
    baseline = f"{period} · {baseline_kind}" if period else str(baseline_kind or "")
    display_name = f"승인 시나리오 · {normalized} · 기준 {baseline or '확인 필요'}"
    material = {
        "namespace": "decision", "object_type": "scenario",
        "object_id": str(object_id or ""), "name": normalized,
        "version": int(version), "fingerprint": str(fingerprint or ""),
        "baseline_kind": str(baseline_kind or ""), "baseline_period": period,
        "approved_at": str(approved_at or ""), "display_name": display_name,
    }
    return ObjectDisplayDescriptor(
        display_name=display_name,
        display_fingerprint=hashlib.sha256(
            _canonical(material).encode("utf-8")).hexdigest(),
    )


def describe_driver_object(*, object_id: str, name: str, version: int,
                           fingerprint: str, category: str, unit: str,
                           external_code: str, approved_at: str) -> ObjectDisplayDescriptor:
    """Describe an approved planning-driver release, never its editable draft."""
    normalized = " ".join(str(name or "").split()).strip()
    if not normalized or not str(fingerprint or "").strip() or int(version or 0) < 1:
        raise ObjectDisplayIntegrityError("승인 동인의 명칭·지문·판 번호가 완전하지 않습니다.")
    if object_id and object_id in normalized:
        raise ObjectDisplayIntegrityError("동인 표시 설명에 내부 객체 ID가 포함됐습니다.")
    detail = str(category or "").strip() or "분류 미등록"
    unit_label = str(unit or "").strip() or "단위 미등록"
    display_name = f"경영 동인 · {normalized} · {detail} · {unit_label}"
    material = {
        "namespace": "g4", "object_type": "driver", "object_id": str(object_id or ""),
        "name": normalized, "version": int(version), "fingerprint": str(fingerprint),
        "category": str(category or ""), "unit": str(unit or ""),
        "external_code": str(external_code or ""), "approved_at": str(approved_at or ""),
        "display_name": display_name,
    }
    return ObjectDisplayDescriptor(
        display_name=display_name,
        display_fingerprint=hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest(),
    )


def describe_knowledge_asset(*, object_id: str, filename: str, pack_id: str,
                             classification: str, approved_sha256: str,
                             approval_fingerprint: str, approved_at: str
                             ) -> ObjectDisplayDescriptor:
    """Describe a ledger-backed reference asset without exposing its internal ID."""
    raw_name = str(filename or "").strip()
    normalized = raw_name.rsplit(".", 1)[0] if "." in raw_name else raw_name
    normalized = " ".join(normalized.replace("_", " ").split()).strip()
    if not normalized:
        raise ObjectDisplayIntegrityError("승인 지식 자산의 사람용 문서명이 비어 있습니다.")
    if object_id and object_id in normalized:
        raise ObjectDisplayIntegrityError("승인 지식 표시 설명에 내부 자산 ID가 포함됐습니다.")
    if not all(str(value or "").strip() for value in
               (pack_id, classification, approved_sha256, approval_fingerprint, approved_at)):
        raise ObjectDisplayIntegrityError("승인 지식의 팩·분류·지문·승인 시각이 완전하지 않습니다.")
    display_name = f"승인 지식 · {normalized}"
    material = {
        "namespace": "knowledge", "object_type": "reference-asset",
        "object_id": str(object_id or ""), "filename": raw_name,
        "pack_id": str(pack_id), "classification": str(classification),
        "approved_sha256": str(approved_sha256),
        "approval_fingerprint": str(approval_fingerprint),
        "approved_at": str(approved_at), "display_name": display_name,
    }
    return ObjectDisplayDescriptor(
        display_name=display_name,
        display_fingerprint=hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest(),
    )


def _number(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "수량 미등록"
    try:
        parsed = Decimal(raw)
    except InvalidOperation:
        return "수량 확인 필요"
    rendered = format(parsed.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return f"{int(rendered):,}" if "." not in rendered else f"{float(rendered):,g}"


def _quantity(row: dict, field: str) -> str:
    value = _number(row.get(field))
    unit = str(row.get("quantity_uom", "") or "").strip()
    return f"{value} {unit}".strip()


def _date(row: dict, field: str, suffix: str) -> str:
    value = str(row.get(field, "") or "").strip()
    return f"{value} {suffix}" if value else suffix


def _purchase(row: dict, ordinal: int) -> str:
    return f"구매 주문행 {ordinal} · {_quantity(row, 'order_quantity')} · {_date(row, 'due_date', '납기')}"


def _procurement_contract(row: dict, ordinal: int) -> str:
    quantity = _quantity(row, "contract_quantity")
    incoterm = str(row.get("incoterm", "") or "").strip()
    period = f"{row.get('valid_from') or '시작일 미등록'}~{row.get('valid_to') or '종료일 미등록'}"
    return f"조달 계약 {ordinal} · {quantity} · {incoterm or '거래조건 미등록'} · {period}"


def _partner_submission(row: dict, ordinal: int) -> str:
    status = str(row.get("submission_status", "") or "").strip()
    submitted = str(row.get("submitted_at", "") or "").strip()
    version = str(row.get("source_version", "") or "").strip()
    return (f"파트너 제출 {ordinal} · {status or '상태 미등록'} · "
            f"{submitted or '제출시각 미등록'} · 판 {version or '미등록'}")


def _shipment(row: dict, ordinal: int) -> str:
    origin = str(row.get("origin_port", "") or "").strip()
    destination = str(row.get("destination_port", "") or "").strip()
    route = f"{origin}→{destination}" if origin and destination else "운송 구간 확인 필요"
    return f"선적 {ordinal} · {route} · {_quantity(row, 'shipment_quantity')} · {_date(row, 'eta', '도착 예정')}"


def _shipment_milestone(row: dict, ordinal: int) -> str:
    event = str(row.get("event_type", "") or "").strip()
    actual = str(row.get("actual_at", "") or "").strip()
    planned = str(row.get("planned_at", "") or "").strip()
    return f"선적 이정표 {ordinal} · {event or '사건 미등록'} · {actual or planned or '시각 미등록'}"


def _customs_clearance(row: dict, ordinal: int) -> str:
    inspection = str(row.get("inspection_status", "") or "").strip()
    status = str(row.get("status", "") or "").strip()
    cleared = str(row.get("cleared_at", "") or "").strip()
    return (f"통관 처리 {ordinal} · {inspection or '검사상태 미등록'} · "
            f"{status or '처리상태 미등록'} · {cleared or '완료시각 미등록'}")


def _transport_event(row: dict, ordinal: int) -> str:
    event = str(row.get("event_type", "") or "").strip()
    occurred = str(row.get("event_at", "") or "").strip()
    return f"내륙 운송 사건 {ordinal} · {event or '사건 미등록'} · {occurred or '시각 미등록'} · {_quantity(row, 'delivered_quantity')}"


def _inventory(row: dict, ordinal: int) -> str:
    quantity = _quantity(row, "unrestricted_quantity")
    return f"재고 현황 {ordinal} · {_date(row, 'snapshot_date', '기준')} · 가용 {quantity}"


def _production(row: dict, ordinal: int) -> str:
    return f"생산 계획행 {ordinal} · {_date(row, 'plan_date', '계획')} · {_quantity(row, 'plan_quantity')}"


def _production_batch(row: dict, ordinal: int) -> str:
    status = str(row.get("status", "") or "").strip()
    actual_yield = _number(row.get("actual_yield"))
    return (f"생산 실적 배치 {ordinal} · {_date(row, 'production_date', '생산')} · "
            f"산출 {_quantity(row, 'output_quantity')} · 수율 {actual_yield} · {status or '상태 미등록'}")


def _sales(row: dict, ordinal: int) -> str:
    return f"판매 주문행 {ordinal} · {_date(row, 'due_date', '납기')} · {_quantity(row, 'order_quantity')}"


def _cost_record(row: dict, ordinal: int) -> str:
    component = str(row.get("cost_component", "") or "").strip()
    actual = _number(row.get("actual_unit_cost"))
    currency = str(row.get("currency", "") or "").strip()
    period = str(row.get("fiscal_period", "") or "").strip()
    return (f"원가 실적 {ordinal} · {component or '원가요소 미등록'} · "
            f"실제단가 {actual} {currency or '통화 미등록'} · {period or '기간 미등록'}")


def _finance_document(row: dict, ordinal: int) -> str:
    kind = str(row.get("document_type", "") or "").strip()
    amount = _number(row.get("amount"))
    currency = str(row.get("currency", "") or "").strip()
    status = str(row.get("status", "") or "").strip()
    return (f"재무 문서 {ordinal} · {kind or '유형 미등록'} · "
            f"{amount} {currency or '통화 미등록'} · {status or '상태 미등록'}")


def _ledger_line(row: dict, ordinal: int) -> str:
    debit = _number(row.get("debit_amount"))
    credit = _number(row.get("credit_amount"))
    currency = str(row.get("currency", "") or "").strip()
    period = str(row.get("fiscal_period", "") or "").strip()
    return (f"원장 전기행 {ordinal} · 차변 {debit} · 대변 {credit} "
            f"{currency or '통화 미등록'} · {period or '기간 미등록'}")


def _material(row: dict, ordinal: int) -> str:
    name = str(row.get("material_name", "") or "").strip()
    kind = str(row.get("material_type", "") or "").strip()
    unit = str(row.get("base_uom", "") or "").strip()
    return f"품목 {ordinal} · {name or '명칭 확인 필요'} · {kind or '분류 확인 필요'} · 기준단위 {unit or '미등록'}"


def _supplier(row: dict, ordinal: int) -> str:
    name = str(row.get("supplier_name", "") or "").strip()
    country = str(row.get("country_code", "") or "").strip()
    risk = str(row.get("risk_grade", "") or "").strip()
    return f"공급사 {ordinal} · {name or '명칭 확인 필요'} · 국가 {country or '미등록'} · 위험등급 {risk or '미등록'}"


def _location(row: dict, ordinal: int) -> str:
    name = str(row.get("location_name", "") or "").strip()
    kind = str(row.get("storage_type", "") or "").strip()
    capacity = _number(row.get("capacity_quantity"))
    unit = str(row.get("capacity_uom", "") or "").strip()
    return f"사업장 위치 {ordinal} · {name or '명칭 확인 필요'} · {kind or '용도 미등록'} · 용량 {capacity} {unit}".strip()


def _equipment(row: dict, ordinal: int) -> str:
    name = str(row.get("equipment_name", "") or "").strip()
    rate = _number(row.get("rate_per_hour"))
    unit = str(row.get("rate_uom", "") or "").strip()
    return f"설비 {ordinal} · {name or '명칭 확인 필요'} · 기준능력 {rate} {unit}".strip()


def _bom_line(row: dict, ordinal: int) -> str:
    role = str(row.get("component_role", "") or "").strip()
    quantity = _number(row.get("quantity_per_output"))
    unit = str(row.get("input_uom", "") or "").strip()
    yield_rate = _number(row.get("standard_yield"))
    effective = str(row.get("effective_from", "") or "").strip()
    return (f"BOM 구성행 {ordinal} · {role or '역할 미등록'} · 기준투입 {quantity} "
            f"{unit or '단위 미등록'} · 표준수율 {yield_rate} · {effective or '유효일 미등록'}부터")


def _routing_operation(row: dict, ordinal: int) -> str:
    name = str(row.get("operation_name", "") or "").strip()
    rate = _number(row.get("rate_per_hour"))
    unit = str(row.get("rate_uom", "") or "").strip()
    setup = _number(row.get("setup_hours"))
    return (f"라우팅 공정 {ordinal} · {name or '공정명 확인 필요'} · 기준능력 {rate} "
            f"{unit or '단위 미등록'} · 준비 {setup}시간")


def _account(row: dict, ordinal: int) -> str:
    name = str(row.get("account_name", "") or "").strip()
    kind = str(row.get("account_type", "") or "").strip()
    currency = str(row.get("currency", "") or "").strip()
    return f"계정 {ordinal} · {name or '명칭 확인 필요'} · {kind or '유형 미등록'} · {currency or '통화 미등록'}"


def _logistics_reference(row: dict, ordinal: int) -> str:
    kind = str(row.get("reference_type", "") or "").strip()
    origin = str(row.get("origin", "") or "").strip()
    destination = str(row.get("destination", "") or "").strip()
    route = f" · {origin}→{destination}" if origin and destination else ""
    return f"물류 기준 {ordinal} · {kind or '유형 확인 필요'}{route}"


def _external(row: dict, ordinal: int) -> str:
    observed = str(row.get("observed_at", "") or "").strip()
    value = _number(row.get("value"))
    unit = str(row.get("unit", "") or "").strip()
    trust = str(row.get("trust_grade", "") or "").strip()
    return f"대외 관측값 {ordinal} · {observed or '관측시각 미등록'} · {value} {unit} · 신뢰등급 {trust or '미등록'}".strip()


_FORMATTERS: Dict[str, Callable[[dict, int], str]] = {
    "PRC-01": _procurement_contract,
    "PRC-02": _purchase,
    "LOG-01": _partner_submission,
    "LOG-02": _shipment,
    "LOG-03": _shipment_milestone,
    "LOG-04": _customs_clearance,
    "LOG-05": _transport_event,
    "INV-01": _inventory,
    "MFG-01": _production,
    "MFG-02": _production_batch,
    "SLS-01": _sales,
    "FIN-01": _cost_record,
    "FIN-02": _finance_document,
    "FIN-03": _ledger_line,
    "MDM-01": _material,
    "MDM-02": _supplier,
    "MDM-04": _location,
    "MDM-06": _equipment,
    "MDM-07": _account,
    "MDM-08": _logistics_reference,
    "EXT-01": _external,
    "EXT-02": _external,
    "EXT-03": _external,
}

_TYPE_FORMATTERS: Dict[tuple, Callable[[dict, int], str]] = {
    ("MDM-05", "bom-line"): _bom_line,
    ("MDM-06", "routing-operation"): _routing_operation,
}


def describe_dataset_object(*, namespace: str, object_type: str, object_id: str,
                            snapshot_id: str, dataset_contract_key: str,
                            raw_path: str, checksum: str) -> ObjectDisplayDescriptor:
    """Describe one object from the exact certified bytes that resolved its scope."""
    targets = [target for target in scope_index.object_specs(dataset_contract_key)
               if target[:2] == (namespace, object_type)]
    formatter = (_TYPE_FORMATTERS.get((dataset_contract_key, object_type))
                 or _FORMATTERS.get(dataset_contract_key))
    if len(targets) != 1 or formatter is None:
        raise ObjectDisplayIntegrityError(
            f"표시 설명 계약이 없는 데이터셋입니다({dataset_contract_key or '미등록'}).")
    _, _, key_columns = targets[0]

    try:
        rows, columns = scope_index.rows_from_raw(raw_path, checksum)
    except Exception as exc:
        raise ObjectDisplayIntegrityError("봉인된 원본에서 객체 표시 설명을 읽지 못했습니다.") from exc
    missing = [column for column in key_columns if column not in columns]
    if missing:
        raise ObjectDisplayIntegrityError(
            f"표시 설명 원본에 객체 열쇠 열이 없습니다({', '.join(missing)}).")

    matches = [(index, row) for index, row in enumerate(rows, start=1)
               if scope_index.object_id_for(row, key_columns) == object_id]
    if len(matches) != 1:
        raise ObjectDisplayIntegrityError(
            "봉인된 원본에서 객체 표시 대상을 하나로 확정하지 못했습니다.")
    ordinal, row = matches[0]
    display_name = " ".join(formatter(row, ordinal).split()).strip()
    if not display_name:
        raise ObjectDisplayIntegrityError("객체 표시 설명이 비어 있습니다.")
    if object_id and object_id in display_name:
        raise ObjectDisplayIntegrityError("객체 표시 설명에 내부 객체 ID가 포함됐습니다.")

    material = {
        "namespace": namespace,
        "object_type": object_type,
        "object_id": object_id,
        "snapshot_id": snapshot_id,
        "snapshot_checksum": checksum,
        "display_name": display_name,
    }
    return ObjectDisplayDescriptor(
        display_name=display_name,
        display_fingerprint=hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest(),
    )
