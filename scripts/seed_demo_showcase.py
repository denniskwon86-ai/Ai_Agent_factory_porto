"""Register one realistic, explicitly synthetic ontology/knowledge showcase.

This command uses the same HTTP routes as the product UI.  It never writes a
database directly, never attributes a decision to a real employee and is
idempotent for the fixed demo object chain.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


TENANT = "tenant-afs-demo-materials"
PLANT_SCOPE = "plant-afs-smelting-01"
# `org-laxs-mnm` is the legal-entity identifier shown by the operating-context
# UI.  Authorization and knowledge ownership are sealed to the canonical ECM
# organization node instead (D-018).  Mixing the two makes a valid LS MnM
# asset look out-of-scope at approval time.
COMPANY_SCOPE = "node_41402723bc90"
OWNER_DEPT = "demo_smelting"
ENTITY_MODE = "REAL"
EFFECTIVE_FROM = "2026-08-24T02:00:00Z"
AS_OF = "2026-08-28T00:00:00Z"
PROPOSER = "demo.ontology.proposer@test.invalid"
APPROVER = "demo.ontology.approver@test.invalid"
REFERENCE_PATH = (
    "demo_synthetic/SCM_공급망_생산_매출_영향판단_운영기준_DEMO_SYNTHETIC.md"
)

RELATIONS = (
    {
        "subject": ("shipment", "SHP-000001"),
        "object": ("inventory-snapshot", "STK-20260823-RM-CU-CONC-LOC-P1-RAW"),
        "calculation_ref": "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
        "evidence_refs": (
            "DEMO/SYNTHETIC",
            "SNAPSHOT:ds_5d070b554cbf4d:LOG-02",
            "SNAPSHOT:ds_39c5d0fe963f40:INV-01",
            "LINEAGE:SHP-000001:RM-CU-CONC:LOC-P1-RAW",
        ),
    },
    {
        "subject": ("inventory-snapshot", "STK-20260823-RM-CU-CONC-LOC-P1-RAW"),
        "object": ("production-plan-line", "MPS-0003871"),
        "calculation_ref": "CALC.INVENTORY.MATERIAL_SHORTAGE.v1",
        "evidence_refs": (
            "DEMO/SYNTHETIC",
            "SNAPSHOT:ds_39c5d0fe963f40:INV-01",
            "SNAPSHOT:ds_807147d0a6a74e:MFG-01",
            "BOM:RM-CU-CONC:FG-CATHODE",
        ),
    },
    {
        "subject": ("production-plan-line", "MPS-0003871"),
        "object": ("sales-line", "SO-000667-10"),
        "calculation_ref": "CALC.PRODUCTION.REVENUE_TIMING.v1",
        "evidence_refs": (
            "DEMO/SYNTHETIC",
            "SNAPSHOT:ds_807147d0a6a74e:MFG-01",
            "SNAPSHOT:ds_4bb377e48d7645:SLS-01",
            "PRODUCT:FG-CATHODE",
        ),
    },
)

# A previous paper-path probe left three approved demo relations with one
# placeholder evidence reference and a non-existent owner department.  They are
# not trustworthy enough for screenshots or decision evidence.  Match the
# complete business keys, never a loose calculation-ref pattern.
OBSOLETE_DEMO_RELATIONS = (
    (("shipment", "SHP-000001"),
     ("inventory-snapshot", "STK-20260823-RM-CU-CONC-LOC-P1-RAW")),
    (("inventory-snapshot", "STK-20260823-RM-CU-CONC-LOC-P1-RAW"),
     ("production-plan-line", "MPS-0005161")),
    (("production-plan-line", "MPS-0005161"),
     ("sales-line", "SO-001000-10")),
)


class ApiError(RuntimeError):
    pass


def _request(base: str, method: str, path: str, *, token: str = "",
             scope: str = "", body: dict[str, Any] | None = None) -> Any:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Session-Token"] = token
    if scope:
        headers.update({
            "X-Enterprise-Tenant": TENANT,
            "X-Enterprise-Scope": scope,
            "X-Entity-Mode": ENTITY_MODE,
        })
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(base.rstrip("/") + path, data=data,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(f"{method} {path} failed: {exc}") from exc
    if payload.get("status") != "success":
        raise ApiError(f"{method} {path} returned an unexpected envelope: {payload}")
    return payload.get("data")


def _login(base: str, user_id: str, password: str) -> str:
    data = _request(base, "POST", "/api/v1/auth/login",
                    body={"user_id": user_id, "password": password})
    token = str((data or {}).get("token") or "")
    if not token:
        raise ApiError(f"login for {user_id} did not return a session")
    return token


def _ensure_user(base: str, admin_token: str, user_id: str, display_name: str) -> None:
    users = _request(base, "GET", "/api/v1/org/users", token=admin_token)
    current = next((row for row in users if row.get("user_id") == user_id), None)
    expected_roles = {OWNER_DEPT: "manager"}
    if (current
            and current.get("display_name") == display_name
            and current.get("primary_dept_id") == OWNER_DEPT
            and not current.get("is_executive")
            and not current.get("is_admin")
            and current.get("is_data_admin")
            and not current.get("is_ai_admin")
            and current.get("roles") == expected_roles):
        return
    _request(base, "POST", "/api/v1/org/users", token=admin_token, body={
        "user_id": user_id,
        "display_name": display_name,
        "primary_dept_id": OWNER_DEPT,
        "is_executive": False,
        "is_admin": False,
        "is_data_admin": True,
        "is_ai_admin": False,
    })
    encoded = urllib.parse.quote(user_id, safe="")
    _request(base, "PUT", f"/api/v1/org/users/{encoded}/roles", token=admin_token,
             body={"roles": expected_roles})


def _ensure_reference(base: str, token: str) -> dict[str, Any]:
    assets = _request(base, "GET", "/api/v1/reference/assets", token=token,
                      scope=COMPANY_SCOPE)
    matches = [row for row in assets if row.get("relative_path") == REFERENCE_PATH]
    if not matches:
        _request(base, "POST", "/api/v1/reference/scan", token=token,
                 scope=COMPANY_SCOPE)
        assets = _request(base, "GET", "/api/v1/reference/assets", token=token,
                          scope=COMPANY_SCOPE)
        matches = [row for row in assets if row.get("relative_path") == REFERENCE_PATH]
    if len(matches) != 1:
        raise ApiError(f"the demo reference asset was not registered exactly once: {len(matches)}")
    asset = matches[0]
    if asset.get("approval_binding") != "LEDGER_BOUND":
        asset = _request(
            base, "POST",
            f"/api/v1/reference/assets/{urllib.parse.quote(str(asset['asset_id']), safe='')}/approve",
            token=token, scope=COMPANY_SCOPE,
            body={"note": (
                "DEMO/SYNTHETIC 공급망 영향 경로의 기능·문서 시연용 지식입니다. "
                "실제 실적 또는 운영 승인으로 사용할 수 없습니다."
            )},
        )
    return asset


def _dry_run_reference_index(base: str, token: str,
                             asset: dict[str, Any]) -> dict[str, Any]:
    """Prove index eligibility without writing irreversible vector chunks."""
    return _request(
        base, "POST", "/api/v1/reference/index", token=token,
        scope=COMPANY_SCOPE,
        body={"dry_run": True, "asset_ids": [str(asset["asset_id"])],
              "force": False},
    )


def _same_relation(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    return (
        row.get("relation_type_id") == "AFFECTS"
        and row.get("subject", {}).get("namespace") == "dataset"
        and row.get("subject", {}).get("object_type") == spec["subject"][0]
        and row.get("subject", {}).get("object_id") == spec["subject"][1]
        and row.get("object", {}).get("namespace") == "dataset"
        and row.get("object", {}).get("object_type") == spec["object"][0]
        and row.get("object", {}).get("object_id") == spec["object"][1]
        and row.get("calculation_ref") == spec["calculation_ref"]
    )


def _obsolete_demo_relation(row: dict[str, Any]) -> bool:
    endpoints = (
        (str(row.get("subject", {}).get("object_type") or ""),
         str(row.get("subject", {}).get("object_id") or "")),
        (str(row.get("object", {}).get("object_type") or ""),
         str(row.get("object", {}).get("object_id") or "")),
    )
    return (
        row.get("relation_type_id") == "AFFECTS"
        and endpoints in OBSOLETE_DEMO_RELATIONS
        and list(row.get("evidence_refs") or []) == ["SNAPSHOT:LOG-02:v1"]
        and row.get("owner_organization_id") == "smelting"
    )


def _retire_obsolete_demo_relations(base: str, admin_token: str) -> list[str]:
    current = _request(base, "GET", "/api/v1/ontology/relations?limit=500",
                       token=admin_token, scope=PLANT_SCOPE)
    retired: list[str] = []
    for row in current.get("relations", []):
        if row.get("approval_status") != "APPROVED" or not _obsolete_demo_relation(row):
            continue
        relation_id = str(row["relation_id"])
        _request(
            base, "POST",
            f"/api/v1/ontology/relations/{relation_id}/decisions/retire",
            token=admin_token, scope=PLANT_SCOPE,
            body={"rationale": (
                "DEMO/SYNTHETIC 종이 경로 탐침을 종료합니다. 소유 부서와 구간별 인증판 "
                "근거가 결속된 시연 관계로 대체합니다."
            )},
        )
        retired.append(relation_id)
    return retired


def _ensure_relation(base: str, proposer_token: str, approver_token: str,
                     spec: dict[str, Any]) -> dict[str, Any]:
    current = _request(base, "GET", "/api/v1/ontology/relations?limit=500",
                       token=proposer_token, scope=PLANT_SCOPE)
    matches = [row for row in current.get("relations", []) if _same_relation(row, spec)]
    approved = [row for row in matches if row.get("approval_status") == "APPROVED"]
    if len(approved) > 1:
        raise ApiError("more than one approved demo relation has the same business meaning")
    if approved:
        return approved[0]

    live = next((row for row in matches if row.get("approval_status") in
                 ("DRAFT", "IN_REVIEW")), None)
    if live is None:
        superseded = next((row for row in matches if row.get("approval_status") in
                           ("REJECTED", "RETIRED")), None)
        subject_type, subject_id = spec["subject"]
        object_type, object_id = spec["object"]
        live = _request(base, "POST", "/api/v1/ontology/relations/propose",
                        token=proposer_token, scope=PLANT_SCOPE, body={
            "subject": {"namespace": "dataset", "object_type": subject_type,
                        "object_id": subject_id},
            "relation_type_id": "AFFECTS",
            "object": {"namespace": "dataset", "object_type": object_type,
                       "object_id": object_id},
            "tenant_id": TENANT,
            "enterprise_scope_id": PLANT_SCOPE,
            "entity_mode": ENTITY_MODE,
            "owner_organization_id": OWNER_DEPT,
            "effective_from": EFFECTIVE_FROM,
            "origin": "derived",
            "evidence_refs": list(spec["evidence_refs"]),
            "source_lineage": list(spec["evidence_refs"]),
            "calculation_ref": spec["calculation_ref"],
            "classification": "INTERNAL",
            "scope_type": "ORG_PRIVATE",
            "scope_assignments": [PLANT_SCOPE],
            "supersedes_relation_id": str((superseded or {}).get("relation_id") or ""),
        })
    relation_id = str(live["relation_id"])
    if live.get("approval_status") == "DRAFT":
        live = _request(base, "POST", f"/api/v1/ontology/relations/{relation_id}/submit",
                        token=proposer_token, scope=PLANT_SCOPE, body={})
    if live.get("approval_status") == "IN_REVIEW":
        decision = _request(
            base, "POST",
            f"/api/v1/ontology/relations/{relation_id}/decisions/approve",
            token=approver_token, scope=PLANT_SCOPE,
            body={"rationale": (
                "DEMO/SYNTHETIC 인증판·업무키·계산 참조를 대조한 시연용 영향 관계입니다. "
                "실제 경영 실적 관계로 사용할 수 없습니다."
            )},
        )
        live = decision["relation"]
    if live.get("approval_status") != "APPROVED":
        raise ApiError(f"demo relation did not reach APPROVED: {live}")
    return live


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--password", default="")
    args = parser.parse_args()
    password = args.password or getpass.getpass("Initial/demo password: ")

    admin_token = _login(args.base_url, args.admin_user, password)
    _ensure_user(args.base_url, admin_token, PROPOSER, "시연 온톨로지 제안자")
    _ensure_user(args.base_url, admin_token, APPROVER, "시연 온톨로지 승인자")
    proposer_token = _login(args.base_url, PROPOSER, password)
    approver_token = _login(args.base_url, APPROVER, password)

    knowledge = _ensure_reference(args.base_url, approver_token)
    retired = _retire_obsolete_demo_relations(args.base_url, admin_token)
    index_preview = _dry_run_reference_index(
        args.base_url, approver_token, knowledge)
    relations = [
        _ensure_relation(args.base_url, proposer_token, approver_token, spec)
        for spec in RELATIONS
    ]
    impact = _request(args.base_url, "POST", "/api/v1/ontology/query/impact",
                      token=proposer_token, scope=PLANT_SCOPE, body={
        "roots": [{"namespace": "dataset", "object_type": "shipment",
                   "object_id": "SHP-000001"}],
        "target_types": ["sales-line"],
        "relation_types": ["AFFECTS"],
        "as_of": AS_OF,
        "max_depth": 6,
        "max_paths": 20,
    })
    print(json.dumps({
        "knowledge": {
            "asset_id": knowledge.get("asset_id"),
            "relative_path": knowledge.get("relative_path"),
            "approval_status": knowledge.get("approval_status"),
            "approval_binding": knowledge.get("approval_binding", "LEDGER_BOUND"),
            "index_dry_run": index_preview,
        },
        "relations": [{
            "relation_id": row.get("relation_id"),
            "subject": (row.get("subject") or {
                "namespace": row.get("subject_namespace"),
                "object_type": row.get("subject_type"),
                "object_id": row.get("subject_id"),
            }),
            "object": (row.get("object") or {
                "namespace": row.get("object_namespace"),
                "object_type": row.get("object_type"),
                "object_id": row.get("object_id"),
            }),
            "approval_status": row.get("approval_status"),
        } for row in relations],
        "retired_obsolete_demo_relations": retired,
        "impact": impact,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
