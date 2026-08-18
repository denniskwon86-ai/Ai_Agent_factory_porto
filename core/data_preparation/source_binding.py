"""[BDR-204] Source Binding — 「이 데이터셋은 어디서 오는가」를 하나로 정한다.

```text
DRAFT → VALIDATED → APPROVED → ACTIVE → RETIRED
                  ↘ BLOCKED
```

## 후보는 여럿, 활성은 하나

★ 같은 데이터셋에 후보를 여럿 둘 수 있어야 **비교해 고르는 일**이 가능하다.
★★★ 그러나 ACTIVE 는 하나뿐이다 — 둘이 되는 순간 「이 데이터셋은 어디서 오는가」에
  답이 두 개가 되고, 그 상태는 **오류를 내지 않는다.** 조회하는 쪽이 아무거나 하나를
  집을 뿐이다.

⚠️ 유일성은 `store` 의 **DB 부분 유일 인덱스**가 보장한다. 여기 판정은 「사람에게 왜
  안 되는지 말해 주는」 층이다 — 두 층이 다 있어야 한다. 코드만 있으면 경쟁 상태에서
  뚫리고, DB 만 있으면 사용자가 이유를 모른다.
"""
from typing import Any, Dict, List, NamedTuple

from core.data_preparation import models as m


class ValidationResult(NamedTuple):
    """검증 결과. **막는 이유를 사람이 읽을 문장으로** 함께 준다."""
    ok: bool
    reasons: List[str]

    @property
    def reason_text(self) -> str:
        return " / ".join(self.reasons)


def validate_config(provider: Any, config: Any) -> ValidationResult:
    """Provider 별 설정 검증. **던지지 않는다** — 호출부가 상태로 바꾼다.

    ⚠️ 「검증」이 형식만 보고 통과하면 그 뒤 승인·활성이 전부 형식 위에 쌓인다.
      여기서 보는 것은 «이 설정으로 실제로 데이터가 흐를 수 있는가» 다."""
    provider = str(provider or "")
    cfg = config if isinstance(config, dict) else {}
    reasons: List[str] = []

    if not m.provider_supported(provider):
        return ValidationResult(False, [f"지원하지 않는 provider 입니다: {provider}"])

    if provider == m.PROVIDER_CONNECTOR_QUERY:
        #: ★ 목록에는 있지만 **아직 되지 않는다.** 「선택은 되는데 아무 일도 안
        #:   일어나는」 화면을 만들지 않으려면 여기서 분명히 말해야 한다.
        return ValidationResult(False, [
            "CONNECTOR_QUERY 는 계약과 화면 자리만 있고 아직 지원하지 않습니다 — "
            "지금은 FILE_SNAPSHOT 또는 AFS_NATIVE 를 쓰십시오."])

    if provider == m.PROVIDER_FILE_SNAPSHOT:
        if not str(cfg.get("file_name", "")).strip():
            reasons.append("file_name 이 필요합니다 — 어느 파일에서 왔는지 없으면 "
                           "나중에 「이 숫자는 어디서 왔나」에 답할 수 없습니다.")
        cols = cfg.get("column_map")
        if not isinstance(cols, dict) or not cols:
            reasons.append("column_map 이 필요합니다 — 파일의 어느 열이 계약의 어느 "
                           "필드인지 사람이 정해야 합니다(추측하지 않습니다).")
    elif provider == m.PROVIDER_AFS_NATIVE:
        #: 앱이 직접 받는 데이터. 결속에 필요한 것은 «어느 데이터셋인가» 뿐이다.
        if not str(cfg.get("dataset_name", "")).strip():
            reasons.append("dataset_name 이 필요합니다 — 앱이 어느 표에 쓰는지 "
                           "가리키지 않으면 결속이 아무것도 가리키지 않습니다.")

    return ValidationResult(not reasons, reasons)


def validate(store: Any, binding_id: str) -> Dict[str, Any]:
    """`DRAFT` → `VALIDATED` 또는 `BLOCKED`.

    ★ 검증 실패를 **`BLOCKED` 로 남긴다.** 그냥 오류로 돌려주면 「무엇이 왜 막혔는가」의
      이력이 남지 않고, 다음 사람이 같은 설정을 다시 낸다."""
    row = store.get_binding(binding_id)
    if row is None:
        raise m.DataPreparationError(f"존재하지 않는 결속입니다: {binding_id}")
    result = validate_config(row.get("provider"), row.get("config"))
    if result.ok:
        return store.transition(binding_id, m.VALIDATED)
    return store.transition(binding_id, m.BLOCKED, blocked_reason=result.reason_text)


def approve(store: Any, binding_id: str) -> Dict[str, Any]:
    """`VALIDATED` → `APPROVED`. 상태 전이 규칙이 그 자리에서 말한다."""
    return store.transition(binding_id, m.APPROVED)


def activate(store: Any, binding_id: str) -> Dict[str, Any]:
    """`APPROVED` → `ACTIVE`. **기존 ACTIVE 종료와 한 트랜잭션**(store 가 한다).

    ⚠️ 물질화되지 않는 provider 는 활성화하지 않는다 — 활성인데 데이터가 안 흐르면
      사용자는 「원천을 붙였다」고 믿고 빈 화면을 본다. 그 오해가 가장 비싸다."""
    row = store.get_binding(binding_id)
    if row is None:
        raise m.DataPreparationError(f"존재하지 않는 결속입니다: {binding_id}")
    if not m.provider_materializable(row.get("provider")):
        raise m.StateConflict(
            f"«{row.get('provider')}» 는 아직 데이터가 흐르지 않습니다 — 활성으로 두면 "
            f"원천을 붙였다고 믿고 빈 화면을 보게 됩니다.")
    return store.transition(binding_id, m.ACTIVE)


def block(store: Any, binding_id: str, reason: str) -> Dict[str, Any]:
    return store.transition(binding_id, m.BLOCKED, blocked_reason=reason)


def coverage(store: Any, instance_id: str, required_keys: List[str]) -> Dict[str, Any]:
    """키트가 요구하는 데이터셋 중 **몇 개가 실제로 붙었는가.**

    ★ 「후보가 있다」와 「활성이다」를 구분해 센다 — 섞으면 준비도가 실제보다 높게
      보이고, 그 숫자로 시연 준비가 끝났다고 판단하게 된다."""
    keys = sorted({str(k) for k in (required_keys or []) if str(k)})
    bindings = store.list_bindings(instance_id)
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for b in bindings:
        by_key.setdefault(str(b.get("dataset_contract_key", "")), []).append(b)

    active, candidate, missing, blocked = [], [], [], []
    for k in keys:
        rows = by_key.get(k, [])
        if any(r.get("state") == m.ACTIVE for r in rows):
            active.append(k)
        elif any(r.get("state") in (m.DRAFT, m.VALIDATED, m.APPROVED) for r in rows):
            candidate.append(k)
        elif any(r.get("state") == m.BLOCKED for r in rows):
            blocked.append(k)
        else:
            missing.append(k)
    return {"required": keys, "active": active, "candidate": candidate,
            "blocked": blocked, "missing": missing,
            "ready": len(active) == len(keys) and bool(keys)}
