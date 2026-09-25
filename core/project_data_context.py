"""프로젝트가 사용할 업무키트 인증판을 봉인하고 에이전트용 문맥으로 만든다."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping, Sequence

from core.calc_dataset_loader import SealedDatasetError, active_seals, load_sealed
from core.data_preparation import kit_registry


class ProjectDataBindingError(RuntimeError):
    """업무 데이터 결속을 만들거나 재검증할 수 없다."""

    def __init__(self, message: str, *, reason_code: str = "DATA_CONTRACT_INVALID",
                 category: str = "invalid"):
        super().__init__(message)
        self.reason_code = reason_code
        self.category = category

    @property
    def status_code(self) -> int:
        return {"not_found": 404, "conflict": 409, "unavailable": 503}.get(self.category, 422)


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bind_instance(store: Any, instance_id: str, *, tenant_id: str,
                  entity_mode: str, allowed_scope_nodes: Iterable[str],
                  unrestricted: bool = False) -> Dict[str, Any]:
    """가시성이 확인된 적용본의 인증판을 프로젝트 입력으로 봉인한다."""
    inst = store.get_instance(str(instance_id or "").strip())
    scopes = {str(x) for x in allowed_scope_nodes if str(x)}
    visible = bool(inst) and (
        unrestricted or (
            str(inst.get("tenant_id", "")) == str(tenant_id or "")
            and str(inst.get("entity_mode", "")) == str(entity_mode or "")
            and str(inst.get("scope_node_id", "")) in scopes
        )
    )
    if not visible:
        raise ProjectDataBindingError("업무키트 적용본을 찾을 수 없습니다.",
                                      reason_code="DATA_INSTANCE_NOT_FOUND", category="not_found")
    if str(inst.get("status", "")) != "active":
        raise ProjectDataBindingError("현재 사용할 수 없는 업무키트 적용본입니다.")

    kit = kit_registry.resolve(store, str(inst.get("kit_id", "")),
                               str(inst.get("version", "")))
    if not kit:
        raise ProjectDataBindingError("적용된 업무키트 계약 판본을 읽을 수 없습니다.")
    if str(kit.get("fingerprint", "")) != str(inst.get("kit_fingerprint", "")):
        raise ProjectDataBindingError("적용본과 업무키트 계약의 지문이 다릅니다.")
    keys = kit_registry.dataset_keys(kit.get("profile"))
    try:
        seals = active_seals(store, instance_id=str(inst["instance_id"]), contract_keys=keys)
    except SealedDatasetError as exc:
        raise ProjectDataBindingError(str(exc), reason_code=exc.reason_code,
                                      category=exc.category) from exc
    missing = sorted(set(keys) - set(seals))
    if missing:
        raise ProjectDataBindingError(
            f"인증된 업무 데이터가 준비되지 않았습니다({len(missing)}개 부족).")

    kit_mode = str(kit.get("mode", ""))
    body: Dict[str, Any] = {
        "binding_version": "v1",
        "instance_id": str(inst["instance_id"]),
        "instance_label": str(inst.get("label", "")),
        "kit_id": str(inst.get("kit_id", "")),
        "kit_version": str(inst.get("version", "")),
        "kit_fingerprint": str(inst.get("kit_fingerprint", "")),
        "kit_mode": kit_mode,
        # 현재 범용 노드는 상용 LLM 경로를 사용할 수 있다. 합성 자료만 기본 허용하고,
        # 실제 업무 자료는 승인된 사설/무학습 모델 경로가 구현될 때까지 막는다.
        "prompt_egress_policy": (
            "SYNTHETIC_ONLY" if kit_mode == "DEMO/SYNTHETIC"
            else "BLOCKED_UNTIL_APPROVED_MODEL_ROUTE"),
        "tenant_id": str(inst.get("tenant_id", "")),
        "scope_node_id": str(inst.get("scope_node_id", "")),
        "entity_mode": str(inst.get("entity_mode", "")),
        "sealed_snapshots": dict(sorted(seals.items())),
    }
    return {**body, "binding_fingerprint": _digest(body)}


def validate_binding(store: Any, binding: Mapping[str, Any], *, actor_id: str = "",
                     context: Mapping[str, Any] = None, repo: Any = None) -> Dict[str, Any]:
    """저장된 봉인을 재검증한다. 최신판으로 바꿔치기하지 않는다."""
    if isinstance(binding, Mapping) and binding.get("binding_version") == "v2":
        return validate_process_binding(store, binding, actor_id=actor_id, context=context, repo=repo)
    body = {k: v for k, v in dict(binding or {}).items() if k != "binding_fingerprint"}
    if not body or str(binding.get("binding_version", "")) != "v1":
        raise ProjectDataBindingError("프로젝트에 업무 데이터 결속이 없습니다.")
    if _digest(body) != str(binding.get("binding_fingerprint", "")):
        raise ProjectDataBindingError("프로젝트 업무 데이터 결속 지문이 다릅니다.")
    inst = store.get_instance(str(binding.get("instance_id", "")))
    if not inst or str(inst.get("status", "")) != "active":
        raise ProjectDataBindingError("결속된 업무키트 적용본을 사용할 수 없습니다.")
    pairs = (("kit_id", "kit_id"), ("kit_version", "version"),
             ("kit_fingerprint", "kit_fingerprint"), ("tenant_id", "tenant_id"),
             ("scope_node_id", "scope_node_id"), ("entity_mode", "entity_mode"))
    for bound_key, instance_key in pairs:
        if str(binding.get(bound_key, "")) != str(inst.get(instance_key, "")):
            raise ProjectDataBindingError("업무키트 적용본이 프로젝트 결속 이후 변경되었습니다.")
    kit = kit_registry.resolve(store, str(inst.get("kit_id", "")), str(inst.get("version", "")))
    if not kit or str(binding.get("kit_mode", "")) != str(kit.get("mode", "")):
        raise ProjectDataBindingError("업무키트 데이터 모드가 프로젝트 결속 이후 변경되었습니다.")
    return dict(binding)


def render_agent_context(store: Any, binding: Mapping[str, Any],
                         contract_keys: Sequence[str], *, max_rows: int = 3,
                         max_chars: int = 9000, actor_id: str = "",
                         context: Mapping[str, Any] = None, repo: Any = None) -> str:
    """한 에이전트가 선언한 계약만 읽어 제한된 근거 블록으로 만든다."""
    valid = validate_binding(store, binding, actor_id=actor_id, context=context, repo=repo)
    requested = sorted({str(x).strip() for x in contract_keys if str(x).strip()})
    if not requested:
        return ""
    if str(valid.get("prompt_egress_policy", "")) != "SYNTHETIC_ONLY":
        raise ProjectDataBindingError(
            "실제 업무 데이터는 승인된 사설·무학습 모델 경로가 결속되기 전까지 "
            "외부 LLM 프롬프트로 보낼 수 없습니다.")
    sealed = dict(valid.get("sealed_snapshots") or {})
    missing = sorted(set(requested) - set(sealed))
    if missing:
        raise ProjectDataBindingError(
            f"에이전트가 요구한 인증 데이터가 결속에 없습니다: {', '.join(missing)}")
    selected = {key: sealed[key] for key in requested}
    try:
        rows_by_key = load_sealed(
            store, sealed_snapshots=selected,
            tenant_id=str(valid["tenant_id"]), entity_mode=str(valid["entity_mode"]),
            scope_node_id=str(valid["scope_node_id"]), verify_fingerprint=True)
    except SealedDatasetError as exc:
        raise ProjectDataBindingError(str(exc), reason_code=exc.reason_code,
                                      category=exc.category) from exc

    blocks = [
        f"적용본: {valid.get('instance_label') or '이름 미등록'}",
        "주의: 합성 시연 데이터이며 실제 회사 실적으로 해석하면 안 됩니다.",
        "아래 값은 인증된 업무 데이터 Snapshot에서 읽었습니다. 없는 값은 추정하지 마십시오.",
    ]
    for key in requested:
        rows = rows_by_key[key]
        public_rows = [{k: v for k, v in row.items() if not k.startswith("__")}
                       for row in rows[:max_rows]]
        blocks.append(
            f"\n[{key}] 전체 {len(rows)}행 · 표본 {len(public_rows)}행\n"
            + json.dumps(public_rows, ensure_ascii=False, sort_keys=True))
    text = "\n".join(blocks)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n(업무 데이터 문맥 길이 제한으로 이후 표본 생략)"
    return text


def process_instance(store, instance_id, *, actor_id, context, process_context,
                     for_action="GENERATE", repo=None):
    """B2 정확 인스턴스와 서버 고정 문맥을 읽는다. 레거시 registry 폴백은 없다."""
    from core.data_preparation.process_kit_instances import pin_for_store
    from core.data_preparation.process_pack_artifacts import get_bundle
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessError
    service = ProcessContextService(repo=repo, store=store)
    with service._errors():
        verified = service.revalidate(fixed_context=process_context, actor=actor_id,
                                      current_context=context, for_action=for_action)
        source = [s for s in verified["sources"] if s["kind"] == "PROCESS_PACK" and s["instance_id"] == instance_id]
        if len(source) != 1:
            raise ProcessError("PROCESS_INSTANCE_NOT_FOUND", "고정 업무 문맥의 적용본을 찾을 수 없습니다.", 404)
        instance = store.get_instance(instance_id)
        if not instance:
            raise ProcessError("PROCESS_INSTANCE_NOT_FOUND", "고정 업무 문맥의 적용본을 찾을 수 없습니다.", 404)
        boundary = verified["context_key"]
        expected = {"tenant_id": boundary["tenant_id"], "entity_mode": boundary["entity_mode"],
                    "scope_node_id": boundary["scope_node_id"] or boundary["context_root_id"]}
        if any(instance.get(k) != v for k, v in expected.items()):
            raise ProcessError("PROCESS_INSTANCE_NOT_FOUND", "고정 업무 문맥의 적용본을 찾을 수 없습니다.", 404)
        #: ★ [2026-09-25] 업그레이드한 적용본은 고정 이력을 갖는다 — 이 문맥이 가리키는 원본이
        #:   그 이력 안에 있어야 한다(인스턴스 행·원 링크는 원 정체성으로 검증된다).
        pin = pin_for_store(store, instance, source[0]["artifact_digest"])
        if (not pin or instance.get("status") != "active" or pin["context_root_id"] != boundary["context_root_id"]
                or pin["identity"]["kit_fingerprint"] != pin["artifact_digest"]):
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "고정 적용본·원본·현재 상태가 다릅니다.", 409)
        bundle = get_bundle(store, pin["artifact_digest"])
        if pin["identity"]["kit_id"] != bundle["kit_id"] or pin["identity"]["version"] != bundle["version"]:
            raise ProcessError("PROCESS_ARTIFACT_UNAVAILABLE", "고정 키트 원본 정체성이 다릅니다.", 503)
        return instance, bundle, verified


def process_refs_for_instance(process_context, instance_id):
    """한 계약키에 서로 다른 실제 근거를 임의 선택하지 않는다."""
    from core.enterprise_context.process_schema import ProcessError, canonical
    refs = {}
    for ref in process_context["verified_binding_refs"]:
        if ref["instance_id"] != instance_id:
            continue
        key = ref["contract_key"]
        identity = {k: v for k, v in ref.items() if k not in ("process_id", "requirement_key")}
        if key in refs and canonical(identity) != canonical({
                k: v for k, v in refs[key].items() if k not in ("process_id", "requirement_key")}):
            raise ProcessError("PROCESS_BINDING_CONFLICT", "계약키의 고정 데이터 근거가 여러 개입니다.", 409)
        refs[key] = ref
    return refs


def check_process_refs_conn(conn, *, store, instance, bundle, process_context, actor_id, context, repo=None):
    """계약 저장과 같은 DP transaction에서 재검사. nested store.transaction은 금지."""
    from core.enterprise_context.process_context import ProcessContextService, _HeldReference
    from core.enterprise_context.process_schema import ProcessBoundary, ProcessError
    if not conn.in_transaction:
        raise ProcessError("PROCESS_TRANSACTION_REQUIRED", "열린 DP transaction이 필요합니다.", 503)
    service = ProcessContextService(repo=repo, store=store)
    with service._errors():
        boundary = ProcessBoundary.model_validate(process_context["context_key"])
        fresh = service._instance(conn, boundary, {"kit_instance_ref": instance["instance_id"]}, bundle)
        requirements = {(r["process_id"], r["requirement_key"]): r for r in process_context["data_requirements"]}
        for ref in process_context["verified_binding_refs"]:
            if ref["instance_id"] != instance["instance_id"]:
                # 키트 계약 저장은 그 키트 한 적용본의 근거만 다룬다.
                raise ProcessError("PROCESS_BINDING_CONFLICT", "키트 계약에 다른 적용본 근거가 섞여 있습니다.", 409)
            try:
                service._reference(conn, instance=fresh, bundle=bundle,
                    requirement=requirements[(ref["process_id"], ref["requirement_key"])],
                    contract_key=ref["contract_key"], actor=actor_id, context=context, fixed=ref)
            except _HeldReference as exc:
                raise ProcessError("DATA_USAGE_HOLD", "계약 저장 직전 데이터 사용 보류가 확인되었습니다.", 409) from exc


def bind_process_instance(store, instance_id, *, actor_id, context, process_context, repo=None):
    """인증된 고정 참조만 프로젝트 v2 봉인으로 만든다. 무데이터 bootstrap과 구분한다."""
    instance, bundle, verified = process_instance(store, instance_id, actor_id=actor_id,
        context=context, process_context=process_context, repo=repo)
    refs = process_refs_for_instance(verified, instance_id)
    from core.enterprise_context.process_schema import ProcessError
    if not refs:
        raise ProcessError("CERTIFIED_BINDINGS_REQUIRED", "검증된 고정 데이터 참조가 필요합니다.", 409)
    body = dict(binding_version="v2", instance_id=instance_id, instance_label=instance["label"],
        kit_id=instance["kit_id"], kit_version=bundle["version"], kit_fingerprint=bundle["artifact_digest"],
        kit_mode=bundle["profile"]["mode"], context_key=verified["context_key"], process_context=verified,
        tenant_id=instance["tenant_id"], scope_node_id=instance["scope_node_id"], entity_mode=instance["entity_mode"],
        prompt_egress_policy="BLOCKED_UNTIL_APPROVED_MODEL_ROUTE",
        sealed_snapshots={key: ref["snapshot_id"] for key, ref in sorted(refs.items())})
    return {**body, "binding_fingerprint": _digest(body)}


def validate_process_binding(store, binding, *, actor_id, context, for_action="RUN", repo=None):
    from core.enterprise_context.process_schema import ProcessError
    fields = {"binding_version", "instance_id", "instance_label", "kit_id", "kit_version", "kit_fingerprint",
              "kit_mode", "context_key", "process_context", "tenant_id", "scope_node_id", "entity_mode",
              "prompt_egress_policy", "sealed_snapshots", "binding_fingerprint"}
    if not isinstance(binding, Mapping) or set(binding) != fields or binding["binding_version"] != "v2":
        raise ProcessError("PROCESS_DATA_BINDING_INVALID", "프로젝트 v2 봉인 형식을 확인하십시오.", 422)
    body = {k: v for k, v in binding.items() if k != "binding_fingerprint"}
    if _digest(body) != binding["binding_fingerprint"]:
        raise ProcessError("PROCESS_DATA_BINDING_CONFLICT", "프로젝트 v2 봉인 지문이 다릅니다.", 409)
    instance, bundle, verified = process_instance(store, binding["instance_id"], actor_id=actor_id,
        context=context, process_context=binding["process_context"], for_action=for_action, repo=repo)
    refs = process_refs_for_instance(verified, instance["instance_id"])
    expected = {"kit_id": instance["kit_id"], "kit_version": bundle["version"],
                "kit_fingerprint": bundle["artifact_digest"], "kit_mode": bundle["profile"]["mode"],
                "context_key": verified["context_key"], "tenant_id": instance["tenant_id"],
                "scope_node_id": instance["scope_node_id"], "entity_mode": instance["entity_mode"],
                "sealed_snapshots": {key: ref["snapshot_id"] for key, ref in sorted(refs.items())},
                "prompt_egress_policy": "BLOCKED_UNTIL_APPROVED_MODEL_ROUTE"}
    if any(binding[k] != v for k, v in expected.items()):
        raise ProcessError("PROCESS_DATA_BINDING_CONFLICT", "프로젝트 v2 봉인과 현재 고정 근거가 다릅니다.", 409)
    return dict(binding)
