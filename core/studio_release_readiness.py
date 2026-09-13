"""승인된 고정 데이터 집합만 평가하는 2.0 릴리스 준비도.

레거시 분기 함수가 아니다. 호출부는 신뢰하는 릴리스 ID와 본문 ID를 먼저
대조해야 한다. 등록·물질화·DDL·최신판 탐색·릴리스 파일 접근을 하지 않는다.
"""
from __future__ import annotations

import copy
import hashlib
import math
from datetime import datetime, timezone

from core import app_runtime_contract as arc
from core.data_preparation import readiness as rd
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError


DOCUMENT_VERSION = "2.0"
# B2 골격 전용 프로필에는 신선도 재정의가 없다. API 라우트를 가져오거나
# 1.0 동작을 바꾸지 않고 기존 키트 승격의 30일 정책을 따른다.
DEFAULT_MAX_AGE_DAYS = 30.0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(arc.canonical_json(value).encode("utf-8")).hexdigest()


def _max_age(profile):
    value = profile.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProcessError("PROCESS_FRESHNESS_UNAVAILABLE", "고정 원본의 신선도 정책을 확인할 수 없습니다.", 503)
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ProcessError("PROCESS_FRESHNESS_UNAVAILABLE", "고정 원본의 신선도 정책을 확인할 수 없습니다.", 503)
    return value


def _combine(groups):
    """다른 인스턴스의 행을 누락하지 않고 evaluate_instance 반환 형태를 유지한다."""
    rows = sorted(
        ({**row, "instance_id": instance_id}
         for instance_id, result in groups for row in result["datasets"]),
        key=lambda row: (row["instance_id"], row["dataset_contract_key"]),
    )
    ready = sum(row["state"] == rd.READY for row in rows)
    stale = sum(row["state"] == rd.STALE for row in rows)
    if any(row["state"] == rd.LEGACY_OWNERSHIP_QUARANTINED for row in rows):
        status = rd.INSTANCE_BLOCKED
    elif rows and ready == len(rows):
        status = rd.INSTANCE_READY
    elif ready or stale:
        status = rd.INSTANCE_PARTIAL
    else:
        status = rd.INSTANCE_BLOCKED
    return {
        "runtime_document_version": DOCUMENT_VERSION,
        "status": status,
        "as_of": min((row["as_of"] for row in rows if row["as_of"]), default=""),
        "coverage": {"required": len(rows), "ready": ready, "stale": stale,
                     "blocked": len(rows) - ready - stale},
        "datasets": rows,
        # 다른 청사진이 아니라 봉인된 앱이 실제로 쓰는 데이터셋만 평가한다.
        "available_outputs": [], "blocked_outputs": [], "outputs": [],
        "context_omitted": 0, "ownership_quarantined": {},
        "binding_set_fingerprint": _digest({i: r["binding_set_fingerprint"] for i, r in groups}),
        "snapshot_set_fingerprint": _digest({i: r["snapshot_set_fingerprint"] for i, r in groups}),
        # STALE 결과에도 고정 근거는 남긴다. 승격 성공의 지문을 봉인하기 전에
        # 호출부가 READY를 요구해야 한다.
        "fixed_snapshot_refs": sorted({
            f"{row['instance_id']}:{row['dataset_contract_key']}={row['snapshot_id']}"
            for row in rows
        }),
    }


def release_readiness(release, *, actor, context, store=None, processes=None, revisions=None):
    """2.0 표식이 있는 준비도를 반환한다. 잘못되거나 현재 못 쓰는 근거는 예외다.

    내부 데이터 전용 앱도 RELEASE 권한과 출처를 검사한다. 실제 사용 원본·인스턴스·
    결속·인증·사용 보류는 하나의 DP 읽기 트랜잭션에서 다시 확인한다. 신선도는
    고정 인증판만으로 평가한다. 내부 데이터만 쓰면 READY와 빈 datasets 및
    fixed_snapshot_refs를 명시한다. 이때 지문은 fingerprint_for([])가 아닌 Host의 NO_DATA다.
    """
    from core.data_preparation.process_pack_artifacts import get_bundle
    from core.enterprise_context.process_context import ProcessContextService
    from core.studio_release_context import require_release_context
    from core.studio_runtime_data import _ReadView, fixed_reference, fixed_snapshot_conn

    if not isinstance(release, dict) or not isinstance(release.get("release_id"), str) or not release["release_id"].strip():
        raise ProcessError("STUDIO_RELEASE_CONTEXT_REQUIRED", "검증할 릴리스 정체성이 필요합니다.", 409)
    sealed = copy.deepcopy(release)
    current_context = copy.deepcopy(context)
    if store is None:
        from core.data_preparation.store import data_preparation_store
        store = data_preparation_store
    svc = processes if processes is not None else ProcessContextService(store=store)
    verified = require_release_context(
        sealed, release_id=sealed["release_id"], actor=actor, context=current_context,
        for_action="RELEASE", store=store, processes=svc, revisions=revisions,
    )
    contract = sealed.get("runtime_contract")
    if (verified is None or not isinstance(contract, dict)
            or contract.get("schema_version") != DOCUMENT_VERSION or arc.validate(contract)
            or contract.get("status") != "APPROVED"
            or (contract.get("approval") or {}).get("status") != "APPROVED"):
        raise ProcessError("STUDIO_RELEASE_CONTEXT_INVALID", "승인된 2.0 고정 계약이 필요합니다.", 409)
    fixed = contract["process_context"]
    boundary = ProcessBoundary.model_validate(fixed["context_key"])
    scope = {"tenant_id": boundary.tenant_id, "entity_mode": boundary.entity_mode,
             "scope_node_id": boundary.scope_node_id or boundary.context_root_id}
    wanted = {}
    for dataset in contract["datasets"]:
        if dataset["source_intent"] == arc.AFS_NATIVE:
            if dataset.get("enterprise_contract_key"):
                raise ProcessError("PROCESS_BINDING_CONFLICT", "내부 데이터에 외부 계약키가 있습니다.", 409)
            continue
        if dataset["source_intent"] != arc.ENTERPRISE_READ:
            raise ProcessError("PROCESS_SOURCE_UNSUPPORTED", "지원하지 않는 데이터 출처입니다.", 409)
        key = dataset["enterprise_contract_key"]
        instance_id = next((ref["instance_id"] for ref in fixed["verified_binding_refs"]
                            if ref["contract_key"] == key), "")
        ref = fixed_reference(fixed, key, instance_id)
        wanted[(instance_id, key)] = ref

    if not wanted:
        result = _combine([])
        result["status"] = rd.INSTANCE_READY
        return result

    groups, bundles = {}, {}
    with svc._errors(), store.transaction() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN")
        now = _now()
        for (instance_id, key), ref in sorted(wanted.items()):
            digest = ref["artifact_digest"]
            if digest not in bundles:
                bundles[digest] = get_bundle(_ReadView(conn), digest)
            bundle = bundles[digest]
            if key not in {row["dataset_contract_key"] for row in bundle["profile"]["datasets"]}:
                raise ProcessError("PROCESS_BINDING_CONFLICT", "고정 원본에 데이터 계약키가 없습니다.", 409)
            instance = svc._instance(conn, boundary, {"kit_instance_ref": instance_id}, bundle)
            requirements = [r for r in fixed["data_requirements"]
                            if (r["process_id"], r["requirement_key"])
                            == (ref["process_id"], ref["requirement_key"])]
            if len(requirements) != 1:
                raise ProcessError("PROCESS_BINDING_CONFLICT", "고정 데이터 요구 근거가 없습니다.", 409)
            svc._reference(conn, instance=instance, bundle=bundle, requirement=requirements[0],
                           contract_key=key, actor=actor, context=current_context, fixed=ref)
            snapshot = fixed_snapshot_conn(conn, store, ref)
            raw_binding = conn.execute("SELECT * FROM source_bindings WHERE binding_id=?",
                                       (ref["binding_id"],)).fetchone()
            if raw_binding is None or snapshot is None:
                raise ProcessError("PROCESS_BINDING_CONFLICT", "고정 결속 또는 인증판이 없습니다.", 409)
            group = groups.setdefault(instance_id, {"keys": [], "bindings": {}, "snapshots": {},
                                                   "max_age": _max_age(bundle["profile"])})
            group["keys"].append(key)
            group["bindings"][key] = store._public(dict(raw_binding))
            group["snapshots"][key] = [snapshot]
        evaluated = []
        for instance_id, group in sorted(groups.items()):
            evaluated.append((instance_id, rd.evaluate_instance(
                contract_keys=group["keys"], bindings=group["bindings"], snapshots=group["snapshots"],
                outputs=[], now=now, max_age_days=group["max_age"], scope=scope,
            )))
        return _combine(evaluated)
