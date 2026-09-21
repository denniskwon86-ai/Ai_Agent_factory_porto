"""배포 R1 문서/JSON Schema 검사. 제품·DB·GitHub·agent를 실행하지 않는다.

실행: venv/Scripts/python.exe -B docs/design/contracts/verify_deployment_control_contract.py
의존: 이미 준비된 jsonschema. 외부 설치·네트워크·파일 쓰기 없음.
전체 OpenAPI 표준 validator나 수용 E2E를 대신하지 않는다.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
API_PATH = ROOT / "docs/design/contracts/deployment-control-v1.openapi.json"
api = json.loads(API_PATH.read_text(encoding="utf-8"))
schemas = api["components"]["schemas"]
counts = {"refs": 0, "operations": 0, "schema_cases": 0, "links": 0}


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


for node in walk(api):
    if not isinstance(node, dict):
        continue
    if "$ref" in node:
        pointer = node["$ref"]
        assert pointer.startswith("#/"), ("외부 ref 금지", pointer)
        target = api
        for part in pointer[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        counts["refs"] += 1
    if "required" in node and "properties" in node:
        assert set(node["required"]) <= set(node["properties"])
        assert len(node["required"]) == len(set(node["required"]))

operation_ids = set()
for path, item in api["paths"].items():
    for method, operation in item.items():
        if method not in {"get", "post", "put", "patch", "delete"}:
            continue
        assert operation["operationId"] not in operation_ids
        operation_ids.add(operation["operationId"])
        counts["operations"] += 1
        params = operation.get("parameters", [])
        actual = {p["name"] for p in params if p.get("in") == "path" and p.get("required")}
        assert actual == set(re.findall(r"\{([^}]+)\}", path)), path
        for security in operation.get("security", api["security"]):
            assert set(security) <= set(api["components"]["securitySchemes"])

for schema in schemas.values():
    Draft202012Validator.check_schema(schema)

assert api["info"]["version"] == "1.0.0-design-r1"
assert len(schemas["PlanState"]["enum"]) == 15
assert len(schemas["StepName"]["enum"]) == 8
assert schemas["EnvironmentName"]["enum"] == ["staging", "trial"]
context_api = api["paths"]["/internal/ops/v1/claims/{claim_id}/execution-context"]["get"]
assert context_api["security"] == [{"AgentMtls": []}]
assert context_api["responses"]["200"]["headers"]["Cache-Control"]["schema"]["const"] == "no-store"
assert not any(re.search(r"/(approve|reject)(/|$)", p) for p in api["paths"])

fixture = api["x-plan-digest-fixture"]
canonical = json.dumps(fixture["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
assert canonical == fixture["canonical_json"]
assert hashlib.sha256(canonical.encode()).hexdigest() == fixture["sha256"]
assert len(fixture["payload"]) == 18


def check(name, value, valid=True):
    schema = {"$ref": "#/components/schemas/" + name, "components": api["components"]}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    assert bool(errors) != valid, (name, valid, [e.message for e in errors])
    counts["schema_cases"] += 1


now = "2026-09-21T02:00:00Z"
uid = "00000000-0000-4000-8000-000000000003"
proof = {"code": "ROLE_API", "status": "PASS", "message": "합성 예제", "checked_at": now, "evidence_id": uid}
preflight = {"id": uid, "checked_at": now, "expires_at": "2026-09-21T02:10:00Z", "inputs_digest": "a" * 64, "checks": [proof], "passed": True, "environment": "staging", "staging_evidence_id": None}
plan = deepcopy(fixture["payload"])
plan["id"] = plan.pop("plan_id")
plan.pop("format_version")
plan.pop("service")
plan.update(reason="합성 계약 예제", plan_digest=fixture["sha256"], state="PREPARING", revision=2, preflight=preflight, github_run=None, can_cancel=False, can_dispatch=False, execution_mode="EXECUTING", finalization_deadline=None, created_at=now, updated_at=now)
claim = {"id": uid, "plan_id": plan["id"], "environment": "staging", "run_id": "1", "fence": 1, "lease_expires_at": "2026-09-21T02:01:00Z", "plan": plan, "allowed_steps": ["install"], "mode": "EXECUTING", "finished_at": None, "authorization_checked_at": now}
context = {"claim_id": uid, "plan_id": plan["id"], "environment": "staging", "agent_id": "synthetic-agent", "fence": 1, "mode": "EXECUTING", "plan": plan, "target_slot": "green", "previous_active_slot": "blue", "allowed_steps": ["install"], "checked_at": now, "valid_until": "2026-09-21T02:00:05Z", "lease_expires_at": claim["lease_expires_at"]}
check("Plan", plan)
check("Claim", claim)
check("ExecutionContext", context)
check("Check", {**proof, "status": "TIMEOUT"}, False)
check("ExecutionContext", {**context, "mode": "RELEASED"}, False)
check("ExecutionContext", {**context, "fence": 0}, False)
check("ExecutionContext", {**context, "command": "arbitrary"}, False)
check("ExecutionContext", {**context, "allowed_steps": []}, False)
check("ExecutionContext", {**context, "allowed_steps": ["install", "drain"]}, False)
check("ExecutionContext", {**context, "mode": "CLEANUP_ONLY", "allowed_steps": ["cleanup_candidate"]})
check("ExecutionContext", {**context, "mode": "CLEANUP_ONLY", "allowed_steps": ["switch_traffic"]}, False)
check("ExecutionContext", {**context, "allowed_steps": ["cleanup_candidate"]}, False)
released = {**claim, "mode": "RELEASED", "finished_at": now, "allowed_steps": []}
check("Claim", released)
check("Claim", {**released, "allowed_steps": ["install"]}, False)
check("Claim", {**released, "finished_at": None}, False)
check("Claim", {**claim, "mode": "CLEANUP_ONLY", "allowed_steps": ["switch_traffic"]}, False)
check("StepResult", {"plan_id": plan["id"], "state": "FINALIZING", "step": "observe", "accepted": True, "claim_mode": "RELEASED", "finalization_deadline": "2026-09-21T02:10:00Z"})
readiness = {"node_id": "synthetic-node", "slot": "green", "observed_at": now, "runtime_artifact_sha256": "a" * 64, "runtime_config_digest": "d" * 64, "db_backend": "postgresql", "db_binding_digest": "a" * 64, "storage_binding_digest": "b" * 64, "checks": [proof]}
check("ReadinessEvidence", readiness)
check("ReadinessEvidence", {**readiness, "checks": []}, False)
check("ReadinessEvidence", {**readiness, "db_backend": "sqlite"}, False)
observation = {"serving_artifact_sha256": None, "schema_epoch": 1, "health": "UNKNOWN", "slots": [], "lb_configuration_digest": "a" * 64, "smoke_passed": False, "unresolved_job_handoffs": 0, "readiness_evidence": []}
check("ObservationPayload", observation)
check("ObservationPayload", {**observation, "health": "HEALTHY"}, False)
check("ObservationPayload", {**observation, "health": "HEALTHY", "readiness_evidence": [readiness], "serving_artifact_sha256": "a" * 64, "smoke_passed": True})

docs = [ROOT / "docs/design/DEPLOYMENT_CONTROL_PLANE_V1_2026-09-21.md", ROOT / "docs/handoff/CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md", ROOT / "docs/handoff/CODEX_HYBRID_DEPLOYMENT_R1_2026-09-21.md"]
for doc in docs:
    text = doc.read_text(encoding="utf-8")
    assert len(re.findall(r"^```", text, re.M)) % 2 == 0, doc
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if re.match(r"[a-z]+://", target) or target.startswith("#"):
            continue
        assert (doc.parent / target.split("#")[0]).exists(), (doc, target)
        counts["links"] += 1
handoff = docs[1].read_text(encoding="utf-8")
ids = re.findall(r"^\| ((?:[ACUEO]\d{2})|(?:IR-\d{2})) \|", handoff, re.M)
assert len(ids) == len(set(ids)) == 52, ids
# 심각도 P0/P1과 작업 패키지 번호는 구분한다.
package_text = handoff.replace("P0/P1 차단", "").replace("미해소 P1", "")
assert not re.search(r"(?<!OPS-)(?<!DEP-)\bP[0-7]\b", package_text)

print(json.dumps({"status": "PASS", "scope": "문서·JSON Schema만; 제품/DB/GitHub/NCP NOT_RUN", "paths": len(api["paths"]), "schemas": len(schemas), "acceptance_definitions_not_run": len(ids), **counts}, ensure_ascii=False))
