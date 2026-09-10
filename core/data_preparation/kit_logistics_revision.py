"""K1-c1: 정본 시간축의 합성 물류 후보. 설치·인증·날짜 이동은 제공하지 않는다."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from core.data_preparation.kit_sample_audit import read_package

KEYS = {"PRC-02": "po_line_id", "LOG-02": "shipment_id", "LOG-03": "milestone_id",
        "LOG-04": "clearance_id", "LOG-05": "transport_event_id"}
DATES = {"PRC-02": ("order_date", "due_date"), "LOG-02": ("etd", "eta"),
         "LOG-03": ("planned_at", "actual_at"), "LOG-04": ("declaration_date", "cleared_at"),
         "LOG-05": ("event_at",)}
RULE_VERSION = "synthetic-logistics-common-timeline/1"


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _day(value: object) -> date:
    """날짜는 달력일, 시각은 UTC 달력일로 비교한다. 시각의 offset 추측은 금지."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    if len(value) == 10:
        return date.fromisoformat(value)
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("timestamp needs timezone")
    return moment.astimezone(timezone.utc).date()


def inspect_logistics(data: dict, contracts: dict) -> dict:
    """이 합성 키트의 참조·달력일 정합성만 검사한다. 수량·전사 준비도 검사가 아니다."""
    issues, indexes, parsed = [], {}, {}
    links = Counter()

    def issue(code, dataset, line, detail):
        issues.append({"code": code, "dataset": dataset, "line": line, "detail": detail})

    for dataset, identity in KEYS.items():
        rows = data.get(dataset, [])
        contract = contracts.get(dataset, {})
        if contract.get("business_keys") != [identity]:
            issue("CONTRACT_KEY_MISMATCH", dataset, 1, "지원하는 계약 업무키와 다릅니다")
        required = {f["name"] for f in contract.get("schema", {}).get("fields", []) if f.get("required")}
        required.update(("tenant_id", "scope_node_id", identity))
        index = indexes[dataset] = defaultdict(list)
        if not rows:
            issue("EMPTY_DATASET", dataset, 1, "빈 자료는 검사 통과가 아닙니다")
        for line, row in enumerate(rows, 2):
            missing = sorted(f for f in required if not str(row.get(f) or "").strip())
            if missing:
                issue("REQUIRED_VALUE", dataset, line, ", ".join(missing))
            if row.get("data_class") != "SYNTHETIC" or row.get("data_origin") != "SYNTHETIC":
                issue("SAMPLE_PROVENANCE", dataset, line, "합성 후보에서 실제 자료를 보정하지 않습니다")
            key = (row.get("tenant_id"), row.get(identity))
            if all(isinstance(x, str) and x.strip() for x in key):
                index[key].append((line, row))
            for field in DATES[dataset]:
                try:
                    parsed[dataset, line, field] = _day(row.get(field))
                except (ValueError, TypeError):
                    issue("INVALID_DATE", dataset, line, field)
        for matches in index.values():
            if len(matches) > 1:
                for line, _ in matches:
                    issue("DUPLICATE_BUSINESS_KEY", dataset, line, identity)

    def ordered(dataset, line, field, parent, parent_line, parent_field):
        later = parsed.get((dataset, line, field))
        earlier = parsed.get((parent, parent_line, parent_field))
        if later is not None and earlier is not None and later < earlier:
            issue("TIME_ORDER", dataset, line, f"{field} < {parent}.{parent_field}")

    for line, _ in enumerate(data.get("PRC-02", []), 2):
        ordered("PRC-02", line, "due_date", "PRC-02", line, "order_date")
    for dataset in ("LOG-02", "LOG-03", "LOG-04", "LOG-05"):
        parent, field = ("PRC-02", "po_line_id") if dataset == "LOG-02" else ("LOG-02", "shipment_id")
        for line, row in enumerate(data.get(dataset, []), 2):
            ref = row.get(field)
            matches = indexes[parent].get((row.get("tenant_id"), ref), []) if ref else []
            if not matches:
                issue("REFERENCE_MISSING", dataset, line, f"{field} -> {parent}")
                continue
            if len(matches) != 1:
                issue("REFERENCE_AMBIGUOUS", dataset, line, f"{field} -> {parent}")
                continue
            links[f"{dataset}->{parent}"] += 1
            parent_line, _ = matches[0]
            if dataset == "LOG-02":
                ordered(dataset, line, "etd", parent, parent_line, "order_date")
                ordered(dataset, line, "eta", dataset, line, "etd")
            elif dataset == "LOG-03":
                # BOOKED/PICKED_UP은 출항 전이 정상이다. 모든 사건에 ETD 하한을 적용하지 않는다.
                event = row.get("event_type")
                if event not in {"BOOKED", "PICKED_UP", "ETD", "ETA", "ATA", "UNLOADED"}:
                    issue("UNKNOWN_EVENT", dataset, line, "이 합성 키트의 지원 사건이 아닙니다")
                if event in {"ETD", "ETA"}:
                    actual = parsed.get((dataset, line, "actual_at"))
                    anchor = parsed.get((parent, parent_line, event.lower()))
                    # 생성기의 ETD/ETA 사건 actual_at은 선적 etd/eta와 같은 날짜다.
                    # planned_at은 생성기에서 지연만큼 당겨져 있으므로 대조 열로 쓰지 않는다.
                    if actual is not None and anchor is not None and actual != anchor:
                        issue("EVENT_ANCHOR_MISMATCH", dataset, line, f"actual_at != LOG-02.{event.lower()}")
                if event in {"ATA", "UNLOADED"}:
                    ordered(dataset, line, "actual_at", parent, parent_line, "etd")
            elif dataset == "LOG-04":
                ordered(dataset, line, "declaration_date", parent, parent_line, "etd")
                ordered(dataset, line, "cleared_at", dataset, line, "declaration_date")
            else:
                ordered(dataset, line, "event_at", parent, parent_line, "etd")
    return {"status": "FAIL" if issues else "PASS_CHECKED_SCOPE", "issues": issues,
            "issue_counts": dict(sorted(Counter(i["code"] for i in issues).items())),
            "row_counts": {key: len(data.get(key, [])) for key in KEYS},
            "unique_reference_counts": dict(sorted(links.items())),
            "checked_scope": "five synthetic datasets; required values, identity, references, calendar dates"}


def propose_logistics_candidate(data: dict, contracts: dict) -> dict:
    """원본 모든 행·업무값을 복사하고 후보 상태 두 열만 바꾼다. 실패도 명세에 남긴다."""
    selected = {key: copy.deepcopy(data.get(key, [])) for key in KEYS}
    inspection = inspect_logistics(selected, contracts)
    source_fingerprint = fingerprint(selected)
    for rows in selected.values():
        for row in rows:
            row["quality_status"] = "PENDING_VALIDATION"
            row["certification_status"] = "UNVERIFIED_CANDIDATE"
    report = {"status": "REVIEW_ONLY", "candidate_check": inspection["status"],
              "rule_version": RULE_VERSION, "installed": False,
              "source_rows_fingerprint": source_fingerprint,
              "candidate_rows_fingerprint": fingerprint(selected),
              "inspection": inspection, "candidate_rows": selected,
              "not_verified": ["PRC-01 contract validity", "MDM/FND ownership and scope bindings",
                               "INV-02 receipt quantities and units", "LOG-01 partner submissions",
                               "INV-01/MFG-01/MDM-05/SLS-01 calculation snapshots and sealed results",
                               "cross-event chronology and event completeness", "live certification and browser workflow"],
              "notice": "합성 검토 후보입니다. 날짜 이동·행 삭제·설치·인증·계산 실행 없음."}
    return report


def plan_logistics_revision(root: Path) -> dict:
    """full 정본 5종을 같은 판에서 읽는다. 기존 read_package의 바이트 지문을 재사용."""
    manifest, data, contracts, files, errors = read_package(root, "full")
    if any(e["dataset"] in KEYS for e in errors) or any(key not in contracts or key not in files for key in KEYS):
        raise ValueError("물류 5종 원본 또는 계약을 판독하지 못했습니다")
    report = propose_logistics_candidate(data, contracts)
    report.update({"kit_id": manifest["kit_id"], "source_version": manifest["version"], "profile": "full",
                   "source_files": {key: files[key] for key in KEYS},
                   "manifest_fingerprint": fingerprint(manifest),
                   "contracts_fingerprint": fingerprint({key: contracts[key] for key in KEYS})})
    report["proposal_fingerprint"] = fingerprint(report)
    return report
