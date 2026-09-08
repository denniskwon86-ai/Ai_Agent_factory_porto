"""합성 샘플 조직·BOM의 검토용 변경 명세. 적용·인증·DB 쓰기를 제공하지 않는다."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from core.calc_models import BOM_INPUT_ROLES, MODEL_VERSIONS, material_shortage
from core.calc_projection import PROJECTION_DATASETS, project
from core.data_preparation.kit_sample_audit import inspect_rows, read_package

RULE_VERSION = "organization-bom-candidate/1"
BOM_COPY_RULE_VERSION = "exact-bom-copy-against-full/1"


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _number(value: object) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("유한한 0 이상 수량·수율이 필요합니다")
    return number


def _synthetic(rows: list[dict]) -> None:
    if any(row.get("data_class") != "SYNTHETIC" or row.get("data_origin") != "SYNTHETIC"
           for row in rows):
        raise ValueError("합성 샘플만 후보를 만들 수 있습니다. 실제값은 자동 보정하지 않습니다")


def _pending(row: dict) -> dict:
    return {**row, "quality_status": "PENDING_VALIDATION",
            "certification_status": "UNVERIFIED_CANDIDATE"}


def _recomputed(plan: dict, bom: list[dict]) -> tuple[str, list[dict]]:
    """Decimal 변환으로 제안한 값을 제품 산식으로 독립 대사한다."""
    when = date.fromisoformat(plan["plan_date"])
    candidates = [b for b in bom if b.get("tenant_id") == plan.get("tenant_id")
                  and b.get("scope_node_id") == plan.get("scope_node_id")
                  and b.get("output_material_id") == plan.get("product_id")]
    selected = [b for b in candidates
                if date.fromisoformat(b["effective_from"]) <= when <= date.fromisoformat(b["effective_to"])
                and b.get("component_role") in BOM_INPUT_ROLES]
    if not selected:
        raise ValueError("유효한 투입 BOM 없음 — 유효기간을 소급하지 않습니다")
    if len({b.get("bom_id") for b in selected}) != 1 or not selected[0].get("bom_id"):
        raise ValueError("동시 유효 BOM 충돌 — 대체판을 합치지 않습니다")
    coefficients, yields, identities = {}, {}, set()
    for b in selected:
        identity = (b.get("bom_id"), b.get("line_no"))
        if not identity[1] or identity in identities:
            raise ValueError("BOM 행 중복 또는 행 식별 누락")
        identities.add(identity)
        if not plan.get("quantity_uom") or any(b.get(k) != plan["quantity_uom"]
                                               for k in ("input_uom", "output_uom")):
            raise ValueError("단위 불일치 — 승인되지 않은 환산은 하지 않습니다")
        material = b["input_material_id"]
        per, ratio = _number(b["quantity_per_output"]), _number(b["standard_yield"])
        if not material or ratio <= 0 or ratio > 1:
            raise ValueError("자재 또는 수율 범위가 올바르지 않습니다")
        if material in yields and yields[material] != ratio:
            raise ValueError("같은 자재의 수율이 서로 다릅니다")
        yields[material] = ratio
        coefficients[material] = coefficients.get(material, Decimal(0)) + per
    quantity = _number(plan["plan_quantity"])
    total = sum((quantity * coefficients[m] / yields[m] for m in sorted(coefficients)), Decimal(0))
    proposed = str(total.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
    datasets = {key: [] for key in PROJECTION_DATASETS}
    datasets.update({"MFG-01": [{**plan, "material_requirement": proposed}], "MDM-05": selected})
    projected = project(datasets)
    # 가용 0은 대사용 진단 입력. 생산량·부족량은 결과로 발행하지 않는다.
    result = material_shortage(inventory=[], production_plan=projected["production_plan"],
                              bom=projected["bom"], as_of=plan["plan_date"],
                              arrival={"metrics": {"available_quantity": {m: 0 for m in coefficients}}})
    if len(result["reconciliation"]) != 1 or not result["reconciliation"][0]["matched"]:
        raise ValueError("제품 소요량 대사 근거가 없습니다")
    return proposed, selected


def _coalesce_bom_copies(data: dict, reference_bom: list[dict]) -> tuple[list, list]:
    """같은 패키지 full의 유일한 배합과 완전히 같은 복제만 후보에서 제외한다.

    대체판 선택기가 아니다. 행/계보/BOM 식별자만 제외하고 미지의 열까지 모두
    비교한다. 다른 데이터가 복제 ID를 참조하면 후보에서도 지우지 않는다.
    """
    _synthetic(reference_bom)
    groups, references = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    for rows, target in ((data.get("MDM-05", []), groups), (reference_bom, references)):
        for row in rows:
            key = (row.get("tenant_id"), row.get("scope_node_id"), row.get("output_material_id"))
            target[key][row.get("bom_id")].append(row)

    def signature(rows):
        lines = [str(row.get("line_no") or "") for row in rows]
        if not all(lines) or len(set(lines)) != len(lines):
            raise ValueError("BOM 행 번호 누락·중복")
        return sorted(_fingerprint({k: v for k, v in row.items()
                                    if k not in {"record_id", "lineage_id", "bom_id"}}) for row in rows)

    changes, held, excluded = [], [], set()
    for key, versions in sorted(groups.items()):
        if len(versions) < 2:
            continue
        try:
            refs = references.get(key, {})
            if len(refs) != 1:
                raise ValueError("같은 회사·범위·제품의 full 참조가 유일하지 않습니다")
            canonical_id, ref_rows = next(iter(refs.items()))
            if not canonical_id or canonical_id not in versions or not all(versions):
                raise ValueError("full과 동일한 BOM 식별자가 없습니다")
            expected = signature(ref_rows)
            if any(signature(rows) != expected for rows in versions.values()):
                raise ValueError("BOM 내용이 다릅니다 — 대체판을 자동 선택하지 않습니다")
            removed_ids = set(versions) - {canonical_id}
            if any(row.get("tenant_id") == key[0]
                   and any(isinstance(v, str) and v in removed_ids for v in row.values())
                   for dataset, rows in data.items() if dataset != "MDM-05" for row in rows):
                raise ValueError("다른 자료가 복제 BOM을 참조합니다 — 연결을 임의 변경하지 않습니다")
            proof = [{"bom_id": row["bom_id"], "line_no": row["line_no"],
                      "fingerprint": _fingerprint(row)} for row in ref_rows]
            for line, row in enumerate(data["MDM-05"], 2):
                if (row.get("tenant_id"), row.get("scope_node_id"), row.get("output_material_id")) == key and row["bom_id"] in removed_ids:
                    excluded.add(line)
                    changes.append({"dataset": "MDM-05", "action": "EXCLUDE_EXACT_COPY_FROM_CANDIDATE",
                                    "line": line, "key": [row["bom_id"], row["line_no"]],
                                    "tenant_id": key[0], "before": copy.deepcopy(row), "after": None,
                                    "retained_bom_id": canonical_id, "reference_bom_rows": proof,
                                    "rule": BOM_COPY_RULE_VERSION})
        except ValueError as exc:
            held.append({"dataset": "MDM-05", "tenant_id": key[0], "scope_node_id": key[1],
                         "product_id": key[2], "reason": str(exc)})
    data["MDM-05"] = [row for line, row in enumerate(data.get("MDM-05", []), 2) if line not in excluded]
    return changes, held


def propose_revision(data: dict, contracts: dict, reference_org: list[dict], *, reference_bom: list[dict] | None = None) -> dict:
    """입력을 보존하고 전체 변경 목록과 남은 결손을 반환한다."""
    _synthetic([row for rows in data.values() for row in rows])
    _synthetic(reference_org)
    revised = copy.deepcopy(data)
    before = inspect_rows(data, contracts)
    changes, held = [], []
    if reference_bom is not None:
        changes, held = _coalesce_bom_copies(revised, reference_bom)
    org = revised.get("FND-01", [])
    index, reference = defaultdict(list), defaultdict(list)
    for row in org:
        index[(row.get("tenant_id"), row.get("node_id"))].append(row)
    for row in reference_org:
        reference[(row.get("tenant_id"), row.get("node_id"))].append(row)

    def collect(key: tuple, visiting: set, additions: dict) -> None:
        if key in visiting:
            raise ValueError("조직 부모 순환")
        current = index.get(key) or reference.get(key, [])
        if len(current) != 1:
            raise ValueError("같은 회사의 조직 정본이 없거나 중복됩니다")
        row = current[0]
        parent = row.get("parent_id")
        if parent:
            collect((key[0], parent), visiting | {key}, additions)
        if key not in index:
            additions[key] = row

    needed = {(row.get("tenant_id"), row.get("scope_node_id"))
              for rows in revised.values() for row in rows}
    # scope로 쓰이지 않는 부서도 부모가 끊기지 않았는지 확인한다.
    needed.update(index)
    for key in sorted(needed, key=str):
        additions: dict = {}
        try:
            collect(key, set(), additions)
        except ValueError as exc:
            held.append({"dataset": "FND-01", "tenant_id": key[0], "scope_node_id": key[1],
                         "reason": str(exc)})
            continue
        for identity, source in additions.items():
            if identity in index:
                continue
            candidate = _pending(copy.deepcopy(source))
            org.append(candidate)
            index[identity].append(candidate)
            changes.append({"dataset": "FND-01", "action": "ADD", "key": identity[1],
                            "tenant_id": identity[0], "before": None, "after": candidate,
                            "rule": "same-package-full-organization-with-ancestors",
                            "source_record_id": source.get("record_id"),
                            "source_row_fingerprint": _fingerprint(source)})
    revised["FND-01"] = org

    # 소요량 외 입력 결함을 계산값 변경으로 숨기지 않는다.
    prepared_issues = inspect_rows(revised, contracts) if reference_bom is not None else before
    invalid_lines = {i["line"] for i in prepared_issues if i["dataset"] == "MFG-01"
                     and i["code"] not in {"BOM_PRODUCT_RECONCILIATION", "SCOPE_REFERENCE"}}
    for line, plan in enumerate(revised.get("MFG-01", []), 2):
        try:
            if line in invalid_lines:
                raise ValueError("소요량 외 입력 결함이 있습니다 — 원본 진단을 확인하십시오")
            if len(index.get((plan.get("tenant_id"), plan.get("scope_node_id")), [])) != 1:
                raise ValueError("조직 범위를 확정하지 못했습니다")
            proposed, bom = _recomputed(plan, revised.get("MDM-05", []))
            old = _number(plan.get("material_requirement"))
            if old == Decimal(proposed):
                continue
            original = copy.deepcopy(plan)
            plan.update(_pending({**plan, "material_requirement": proposed}))
            changes.append({"dataset": "MFG-01", "action": "REPLACE_DERIVED_VALUE", "line": line,
                            "key": plan["plan_line_id"], "tenant_id": plan["tenant_id"],
                            "before": original, "after": copy.deepcopy(plan),
                            "rule": "input-role-sum-per-material/divide-yield/round-total-3dp",
                            "source_bom_rows": [{"bom_id": b["bom_id"], "line_no": b["line_no"],
                                                 "fingerprint": _fingerprint(b)} for b in bom]})
        except (ValueError, KeyError, InvalidOperation, ArithmeticError) as exc:
            held.append({"dataset": "MFG-01", "line": line, "key": plan.get("plan_line_id"),
                         "plan_date": plan.get("plan_date"), "reason": str(exc)})

    after = inspect_rows(revised, contracts)
    def summary(issues):
        return {"issue_count": len(issues), "issue_counts": dict(sorted(Counter(i["code"] for i in issues).items()))}
    return {"status": "REVIEW_ONLY", "rule_version": RULE_VERSION,
            "bom_copy_rule": BOM_COPY_RULE_VERSION if reference_bom is not None else None,
            "product_model_version": MODEL_VERSIONS["CALC.INVENTORY.MATERIAL_SHORTAGE.v1"],
            "before": summary(before), "after": summary(after),
            "candidate_check": "FAIL" if after or held else "PASS_CHECKED_SCOPE",
            "change_counts": dict(sorted(Counter(c["dataset"] for c in changes).items())),
            "changes": changes, "held": held, "remaining_issues": after,
            "notice": "적용·등록·인증·실행 승인 없음. 후보 판정은 실제 준비도가 아닙니다.",
            "not_verified": ["installed organization and ownership mapping", "live certification",
                             "inventory and production-sales accounting chain", "public-source totals",
                             "browser workflow", "historical organization validity"]}


def plan_package_revision(root: Path, profile: str = "quick", *, resolve_exact_bom_copies: bool = False) -> dict:
    manifest, data, contracts, files, errors = read_package(root, profile)
    ref_manifest, ref_data, _, ref_files, ref_errors = read_package(root, "full")
    if errors or ref_errors:
        raise ValueError("판독할 수 없는 원본이 있습니다. 원본 샘플 검사부터 실행하십시오")
    if (manifest["kit_id"], manifest["version"]) != (ref_manifest["kit_id"], ref_manifest["version"]):
        raise ValueError("원천과 조직 참조의 패키지 판이 달라졌습니다")
    report = propose_revision(data, contracts, ref_data["FND-01"],
                              reference_bom=ref_data["MDM-05"] if resolve_exact_bom_copies else None)
    report.update({"kit_id": manifest["kit_id"], "source_version": manifest["version"],
                   "profile": profile, "source_files": files,
                   "manifest_fingerprint": _fingerprint(manifest),
                   "contracts_fingerprint": _fingerprint(contracts),
                   "organization_reference": {"profile": "full", **ref_files["FND-01"]}})
    if resolve_exact_bom_copies:
        report["bom_reference"] = {"profile": "full", **ref_files["MDM-05"]}
    report["proposal_fingerprint"] = _fingerprint(report)
    return report
