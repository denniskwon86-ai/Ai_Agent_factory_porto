"""원천 결속의 사용 보류를 인증·소비 경계에서 공통으로 강제한다.

보류 해제 API는 없다. 설치 여부는 승인 근거가 아니며 원문·기존 판은 보존한다.
"""
import json
from typing import Any, Dict, Optional, Tuple

from core.data_preparation import models as m

INVALID = "USAGE_POLICY_UNREADABLE"
NEXT_ACTION = "가격·시점·소유권 보류 근거를 검토하고 승인된 새 결속·판으로 준비하십시오."


class UsageHoldError(m.StateConflict):
    """준비된 데이터라도 사용 보류가 남아 있으면 승격·소비하지 않는다."""


def _codes(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list) or any(
            not isinstance(code, str) or not code.strip() for code in value):
        return (INVALID,)
    return tuple(sorted({code.strip() for code in value}))


def binding_holds(binding: Optional[Dict[str, Any]]) -> Tuple[str, ...]:
    if binding is None:
        return ("SOURCE_BINDING_UNAVAILABLE",)
    if binding.get("config_unreadable"):
        return (INVALID,)
    try:
        config = (json.loads(binding["config_json"]) if "config_json" in binding
                  else binding.get("config", {}))
    except (TypeError, ValueError):
        return (INVALID,)
    if not isinstance(config, dict):
        return (INVALID,)
    holds = set(_codes(config["usage_holds"]) if "usage_holds" in config else ())
    if "rehearsal_only" in config:
        if not isinstance(config["rehearsal_only"], bool):
            holds.add(INVALID)
        elif config["rehearsal_only"]:
            holds.add("REHEARSAL_ONLY")
    # 과거 사본의 설치 상태 표식은 사용 승인이 아니다. True로 바꿔도 해제하지 않는다.
    if any(key in config for key in ("price_hold_runtime_enforcement_installed",
                                    "runtime_price_hold_enforcement_installed")):
        holds.add("PRICE_VINTAGE_AND_CONVERSION_POLICY_REQUIRED")
    return tuple(sorted(holds))


def snapshot_holds(conn: Any, snapshot: Dict[str, Any]) -> Tuple[str, ...]:
    binding = conn.execute("SELECT * FROM source_bindings WHERE binding_id=?",
                           (str(snapshot.get("binding_id") or ""),)).fetchone()
    if binding is None:
        return ("SOURCE_BINDING_UNAVAILABLE",)
    binding = dict(binding)
    for key in ("instance_id", "dataset_contract_key", "tenant_id", "scope_node_id", "entity_mode"):
        if str(binding.get(key) or "") != str(snapshot.get(key) or ""):
            return ("SOURCE_BINDING_CONTEXT_MISMATCH",)
    return binding_holds(binding)


def require_no_holds(holds: Any) -> None:
    codes = _codes(holds)
    if codes:
        raise UsageHoldError("사용 보류: " + ", ".join(codes) + ". " + NEXT_ACTION)


def require_usable_conn(conn: Any, snapshot: Dict[str, Any]) -> None:
    require_no_holds(list(snapshot_holds(conn, snapshot)))


def require_usable(store: Any, snapshot: Dict[str, Any]) -> None:
    with store.transaction() as conn:
        require_usable_conn(conn, snapshot)
