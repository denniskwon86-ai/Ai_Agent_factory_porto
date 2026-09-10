"""K1-c3 합성 계약·공급사 보정 후보. 실제 계약 소급·원본 수정·DB 설치는 제공하지 않는다."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from core.data_preparation.kit_logistics_revision import KEYS, fingerprint, inspect_logistics
from core.data_preparation.kit_sample_audit import read_package

RULE_VERSION = "synthetic-procurement-reference-review/1"
IDENTITIES = {"PRC-01": "contract_id", "MDM-02": "supplier_id",
              "MDM-01": "material_id", "PRC-02": "po_line_id"}
TARGETS = ("PRC-01", "MDM-02")


def _index(rows, field):
    if not rows:
        raise ValueError(f"필수 자료가 비어 있습니다: {field}")
    index = {}
    for row in rows:
        if row.get("data_class") != "SYNTHETIC" or row.get("data_origin") != "SYNTHETIC":
            raise ValueError("합성자료만 보정 후보를 만들 수 있습니다")
        if any(not isinstance(row.get(k), str) or not row[k].strip()
               for k in ("tenant_id", "scope_node_id", field)):
            raise ValueError("업무키·회사·조직 범위가 없습니다")
        key = row["tenant_id"], row[field]
        if key in index:
            raise ValueError(f"중복 업무키: {field}")
        index[key] = row
    return index


def _number(value):
    try:
        value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("수량을 판독할 수 없습니다") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("유한한 0 이상 수량이 필요합니다")
    return value


def _date(value):
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다")
    return result


def _parent(index, row, field):
    parent = index.get((row["tenant_id"], row[field]))
    if parent is None:
        raise ValueError(f"같은 회사의 유일한 참조가 없습니다: {field}")
    return parent


def _materials(row, material_index):
    values = json.loads(row["material_ids"])
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        raise ValueError("공급 자재는 문자열 목록이어야 합니다")
    if len(values) != len(set(values)):
        raise ValueError("공급 자재 목록 중복은 자동 정리하지 않습니다")
    if any((row["tenant_id"], v) not in material_index for v in values):
        raise ValueError("자재 정본에 없는 공급 자재를 자동 등록하지 않습니다")
    return values


def inspect_procurement(data):
    """검토 범위의 날짜·선언 불일치를 계산한다. 권한·인증 검사가 아니다."""
    indexes = {k: _index(data[k], f) for k, f in IDENTITIES.items()}
    declared = {k: set(_materials(r, indexes["MDM-01"])) for k, r in indexes["MDM-02"].items()}
    counts = Counter({"orders_outside_contract_period": 0, "orders_outside_supplier_materials": 0,
                      "contracts_outside_supplier_materials": 0})
    totals, orders = defaultdict(Decimal), defaultdict(list)
    for key, row in indexes["PRC-01"].items():
        supplier = _parent(indexes["MDM-02"], row, "supplier_id")
        _parent(indexes["MDM-01"], row, "material_id")
        if _date(row["valid_from"]) > _date(row["valid_to"]):
            raise ValueError("계약 유효기간이 역전됐습니다")
        if row["currency"] != supplier["currency"]:
            raise ValueError("계약·공급사 통화 불일치는 보정 범위 밖입니다")
        _number(row["contract_quantity"])
        _number(row["ordered_quantity"])
        if row["material_id"] not in declared[row["tenant_id"], row["supplier_id"]]:
            counts["contracts_outside_supplier_materials"] += 1
    for row in data["PRC-02"]:
        contract = _parent(indexes["PRC-01"], row, "contract_id")
        for field in ("supplier_id", "material_id", "currency", "quantity_uom"):
            if not row.get(field) or row[field] != contract[field]:
                raise ValueError(f"발주·계약 {field} 불일치는 자동 보정하지 않습니다")
        when = _date(row["order_date"])
        if when > _date(row["due_date"]):
            raise ValueError("발주일이 납기일보다 늦습니다")
        if when > _date(contract["valid_to"]):
            raise ValueError("만료 뒤 발주는 계약 연장을 별도 검토해야 합니다")
        if when < _date(contract["valid_from"]):
            counts["orders_outside_contract_period"] += 1
        if row["material_id"] not in declared[row["tenant_id"], row["supplier_id"]]:
            counts["orders_outside_supplier_materials"] += 1
        key = row["tenant_id"], row["contract_id"]
        totals[key] += _number(row["order_quantity"])
        orders[key].append(row)
    for key, contract in indexes["PRC-01"].items():
        if totals[key] != _number(contract["ordered_quantity"]):
            raise ValueError("계약 저장 발주량과 전체 발주 합계가 다릅니다")
        if totals[key] > _number(contract["contract_quantity"]):
            raise ValueError("계약 총량을 초과했습니다")
    return dict(counts), orders


def propose_reference_candidate(data):
    """완전한 합성 발주 모수에서만 후보를 만든다. 두 대상 외 입력은 수정하지 않는다."""
    before, orders = inspect_procurement(data)
    candidates = {k: copy.deepcopy(data[k]) for k in TARGETS}
    changes = []

    def change(dataset, row, field, new, reason, evidence):
        old = row[field]
        if old != new:
            changes.append({"dataset": dataset, "tenant_id": row["tenant_id"],
                            "object_id": row[IDENTITIES[dataset]], "field": field,
                            "before": old, "after": new, "reason": reason, "evidence": evidence})
            row[field] = new

    for contract in candidates["PRC-01"]:
        related = orders[contract["tenant_id"], contract["contract_id"]]
        if related:
            earliest = min(r["order_date"] for r in related)
            change("PRC-01", contract, "valid_from", min(contract["valid_from"], earliest),
                   "합성 계약 이력을 같은 자료의 첫 발주일부터 구성하는 제안",
                   sorted(r["po_line_id"] for r in related if r["order_date"] == earliest))
    for supplier in candidates["MDM-02"]:
        old = json.loads(supplier["material_ids"])
        related = [r for r in candidates["PRC-01"] if (r["tenant_id"], r["supplier_id"])
                   == (supplier["tenant_id"], supplier["supplier_id"])]
        additions = sorted({r["material_id"] for r in related} - set(old))
        if additions:
            # 기존 선언 순서·항목은 보존. 실제 계약에 없는 자재를 새로 넣지 않는다.
            change("MDM-02", supplier, "material_ids", json.dumps(old + additions, ensure_ascii=False),
                   "합성 계약에 이미 등장한 자재를 공급 자재 선언에 보완하는 제안",
                   sorted(r["contract_id"] for r in related if r["material_id"] in additions))
    for rows in candidates.values():
        for row in rows:
            row["quality_status"] = "PENDING_VALIDATION"
            row["certification_status"] = "UNVERIFIED_CANDIDATE"
    after, _ = inspect_procurement({**data, **candidates})
    return {"status": "REVIEW_ONLY", "installed": False, "rule_version": RULE_VERSION,
            "candidate_check": "FAIL" if any(after.values()) else "PASS_CHECKED_SCOPE",
            "before_counts": before, "after_counts": after, "changes": changes,
            "row_counts": {k: len(v) for k, v in candidates.items()}, "candidate_rows": candidates,
            "candidate_rows_fingerprint": fingerprint(candidates),
            "not_verified": ["actual contract authorization or historical validity", "supplier eligibility policy",
                             "organization effective dates and ownership", "inventory/production/sales integration",
                             "certification, installation and browser workflow"]}


def plan_reference_revision(root: Path, logistics_path: Path):
    manifest, data, contracts, files, errors = read_package(root, "full")
    if errors:
        raise ValueError("원천 키트 판독에 실패했습니다")
    source = logistics_path.read_bytes()
    parent = json.loads(source)
    if parent["proposal_fingerprint"] != fingerprint({k: v for k, v in parent.items() if k != "proposal_fingerprint"}):
        raise ValueError("물류 후보 명세 지문 불일치")
    if parent["status"] != "REVIEW_ONLY" or parent["installed"] is not False:
        raise ValueError("비설치 물류 후보만 연결할 수 있습니다")
    if parent["source_files"] != {k: files[k] for k in KEYS} or parent["manifest_fingerprint"] != fingerprint(manifest):
        raise ValueError("물류 후보와 현재 원천의 판이 다릅니다")
    if parent["contracts_fingerprint"] != fingerprint({k: contracts[k] for k in KEYS}):
        raise ValueError("물류 계약의 판이 다릅니다")
    expected = {k: [{**r, "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE"}
                    for r in data[k]] for k in KEYS}
    if parent["candidate_rows"] != expected or parent["candidate_rows_fingerprint"] != fingerprint(expected):
        raise ValueError("물류 후보의 업무값이 원천과 다릅니다")
    if inspect_logistics(expected, contracts)["status"] != "PASS_CHECKED_SCOPE":
        raise ValueError("물류 후보의 검사 범위를 다시 통과하지 못했습니다")
    for k, identity in IDENTITIES.items():
        if contracts[k]["business_keys"] != [identity]:
            raise ValueError("지원하는 참조 계약의 업무키와 다릅니다")
    report = propose_reference_candidate({**data, **expected})
    required = sorted(set(IDENTITIES) | set(KEYS))
    report.update({"kit_id": manifest["kit_id"], "source_version": manifest["version"], "profile": "full",
                   "parent_logistics_fingerprint": parent["proposal_fingerprint"],
                   "parent_logistics_file_sha256": hashlib.sha256(source).hexdigest(),
                   "source_files": {k: files[k] for k in required},
                   "contracts_fingerprint": fingerprint({k: contracts[k] for k in required}),
                   "manifest_fingerprint": fingerprint(manifest)})
    report["proposal_fingerprint"] = fingerprint(report)
    return report
