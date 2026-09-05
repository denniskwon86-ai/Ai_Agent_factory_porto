"""프로젝트가 사용할 업무키트 인증판을 봉인하고 에이전트용 문맥으로 만든다."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping, Sequence

from core.calc_dataset_loader import SealedDatasetError, active_seals, load_sealed
from core.data_preparation import kit_registry


class ProjectDataBindingError(RuntimeError):
    """업무 데이터 결속을 만들거나 재검증할 수 없다."""


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
        raise ProjectDataBindingError("업무키트 적용본을 찾을 수 없습니다.")
    if str(inst.get("status", "")) != "active":
        raise ProjectDataBindingError("현재 사용할 수 없는 업무키트 적용본입니다.")

    kit = kit_registry.resolve(store, str(inst.get("kit_id", "")),
                               str(inst.get("version", "")))
    if not kit:
        raise ProjectDataBindingError("적용된 업무키트 계약 판본을 읽을 수 없습니다.")
    if str(kit.get("fingerprint", "")) != str(inst.get("kit_fingerprint", "")):
        raise ProjectDataBindingError("적용본과 업무키트 계약의 지문이 다릅니다.")
    keys = kit_registry.dataset_keys(kit.get("profile"))
    seals = active_seals(store, instance_id=str(inst["instance_id"]), contract_keys=keys)
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


def validate_binding(store: Any, binding: Mapping[str, Any]) -> Dict[str, Any]:
    """저장된 봉인을 재검증한다. 최신판으로 바꿔치기하지 않는다."""
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
                         max_chars: int = 9000) -> str:
    """한 에이전트가 선언한 계약만 읽어 제한된 근거 블록으로 만든다."""
    valid = validate_binding(store, binding)
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
        raise ProjectDataBindingError(str(exc)) from exc

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
