"""2.0 Host: 승인된 고정 판만 해석하며 최신판으로 대체하지 않는다."""
from contextlib import contextmanager

from core.enterprise_context.process_schema import ProcessBoundary, ProcessError


def fixed_reference(process_context, key, instance_id):
    from core.app_runtime_contract import canonical_json
    refs = [r for r in process_context["verified_binding_refs"] if r["contract_key"] == key]
    identities = {canonical_json({k: v for k, v in r.items()
                                  if k not in ("process_id", "requirement_key")}) for r in refs}
    if len(identities) != 1 or refs[0]["instance_id"] != instance_id:
        raise ProcessError("PROCESS_BINDING_CONFLICT", "승인된 고정 결속을 확인할 수 없습니다.", 409)
    return refs[0]


class _ReadView:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def transaction(self):
        yield self.conn


def fixed_snapshot_conn(conn, store, ref):
    from core.enterprise_context.process_context import snapshot_fingerprint
    from core.data_preparation.usage_policy import require_usable_conn
    row = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?", (ref["snapshot_id"],)).fetchone()
    if not row or snapshot_fingerprint(dict(row)) != ref["snapshot_fingerprint"]:
        raise ProcessError("PROCESS_BINDING_CONFLICT", "고정 인증판이 변경되었거나 없습니다.", 409)
    require_usable_conn(conn, dict(row))
    return store.get_snapshot(ref["snapshot_id"], conn=conn)


def resolve_dataset(release, binding, *, actor, context, store=None, processes=None):
    """호출부의 release/PDP 검증 후, 실제 제공 직전 동일 DP snapshot에서 재검증한다."""
    from core import app_runtime_contract as arc
    from core.data_preparation.process_pack_artifacts import get_bundle
    from core.enterprise_context.process_context import ProcessContextService
    if store is None:
        from core.data_preparation.store import data_preparation_store
        store = data_preparation_store
    contract = release["runtime_contract"]
    if arc.validate(contract) or contract["schema_version"] != "2.0":
        raise ProcessError("STUDIO_RELEASE_CONTEXT_INVALID", "업무 계약을 확인할 수 없습니다.", 409)
    matches = [d for d in contract["datasets"] if d["name"] == binding.get("runtime_name")]
    if len(matches) != 1 or not binding.get("contract_bound"):
        raise ProcessError("PROCESS_BINDING_CONFLICT", "승인된 데이터셋 결속이 아닙니다.", 409)
    ds = matches[0]
    if any(str(binding.get(k) or "") != str(ds.get(k) or "")
           for k in ("source_intent", "enterprise_contract_key", "data_role")):
        raise ProcessError("PROCESS_BINDING_CONFLICT", "승인된 데이터 출처와 결속이 다릅니다.", 409)
    fixed = contract["process_context"]
    boundary = ProcessBoundary.model_validate(fixed["context_key"])
    scope = {"tenant_id": boundary.tenant_id, "entity_mode": boundary.entity_mode,
             "scope_node_id": boundary.scope_node_id or boundary.context_root_id}
    if ds["source_intent"] == arc.AFS_NATIVE:
        if binding.get("enterprise_contract_key") or binding.get("kit_instance_id"):
            raise ProcessError("PROCESS_BINDING_CONFLICT", "내부 데이터 결속에 외부 출처가 있습니다.", 409)
        return None, [], scope, None
    if ds["source_intent"] != arc.ENTERPRISE_READ:
        raise ProcessError("PROCESS_SOURCE_UNSUPPORTED", "아직 지원하지 않는 데이터 출처입니다.", 409)
    ref = fixed_reference(fixed, ds["enterprise_contract_key"], binding.get("kit_instance_id"))
    requirements = [r for r in fixed["data_requirements"]
                    if (r["process_id"], r["requirement_key"]) == (ref["process_id"], ref["requirement_key"])]
    if len(requirements) != 1:
        raise ProcessError("PROCESS_BINDING_CONFLICT", "고정 데이터 요구 근거가 없습니다.", 409)
    svc = processes or ProcessContextService(store=store)
    with svc._errors(), store.transaction() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN")
        bundle = get_bundle(_ReadView(conn), ref["artifact_digest"])
        instance = svc._instance(conn, boundary, {"kit_instance_ref": ref["instance_id"]}, bundle)
        svc._reference(conn, instance=instance, bundle=bundle, requirement=requirements[0],
                       contract_key=ref["contract_key"], actor=actor, context=context, fixed=ref)
        snapshot = fixed_snapshot_conn(conn, store, ref)
        row = conn.execute("SELECT * FROM source_bindings WHERE binding_id=?", (ref["binding_id"],)).fetchone()
        from core.studio_release_readiness import _max_age
        return store._public(dict(row)), [snapshot], scope, _max_age(bundle["profile"])


def data_fingerprint(contract, rows, store):
    """지문도 실제 2.0 소비와 같은 고정 판 집합을 사용한다. 1.0은 호출하지 않는다."""
    from core.baseline_build import fingerprint_for
    from core.app_runtime_contract import ENTERPRISE_READ
    fixed = contract["process_context"]
    wanted = {(d["enterprise_contract_key"], fixed_reference(
        fixed, d["enterprise_contract_key"], next((r["instance_id"] for r in fixed["verified_binding_refs"]
             if r["contract_key"] == d["enterprise_contract_key"]), ""))["instance_id"])
        for d in contract["datasets"] if d["source_intent"] == ENTERPRISE_READ}
    actual = {(str(r["key"] or ""), str(r["inst"] or "")) for r in rows if r["key"] or r["inst"]}
    if actual != wanted:
        raise ProcessError("PROCESS_BINDING_CONFLICT", "승인된 데이터 집합과 물질화가 다릅니다.", 409)
    if not wanted:
        from core.app_contract_gate import NO_DATA
        return NO_DATA
    ids = []
    with store.transaction() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN")
        for key, instance in sorted(wanted):
            ref = fixed_reference(fixed, key, instance)
            fixed_snapshot_conn(conn, store, ref)
            ids.append(f"{instance}:{key}={ref['snapshot_id']}")
    return fingerprint_for(ids)
