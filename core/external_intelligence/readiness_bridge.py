"""[DAO-12] 준비도와 수집을 잇는다 — 「준비되지 않음」에서 끝내지 않는다.

지시의 마지막 문단이 요구한 것:

> 업무키트가 요구하는 데이터가 부족할 때 시스템이 단순히 「준비되지 않음」이라고 끝내지 않고,
> 부족한 자료를 찾고 **수집 계획을 제안**한다.

`readiness.evaluate_dataset()` 은 `NOT_CONFIGURED`(원천을 아직 고르지 않았다)까지만 말한다.
그 상태에서 사용자가 할 수 있는 일은 「원천을 고르세요」인데, **어떤 원천이 있는지는
그 화면이 모른다.** 이 모듈이 그 간극을 메운다.

## ★★★ 준비도를 조작하지 않는다

이 모듈은 **제안만** 만든다. `readiness` 의 상태를 바꾸지도, 새 상태를 만들지도 않는다.

⚠️ 「수집할 수 있으니 준비된 셈」으로 접으면 그 순간 준비도가 거짓말을 한다. 받아 온 것과
  **인증되어 업무키트에 결속된 것**은 다르고, 그 차이가 이 시스템의 전부다.

## ★★★ 이미 수집한 것이 있어도 「준비됨」이 아니다

격리 적재본에 6행이 있어도 업무키트의 그 계약은 여전히 `NOT_CONFIGURED` 다. 그것을
숨기지 않고 **함께** 말한다 — 「수집은 됐고, 결속이 남았습니다」.

⚠️ 이 문장을 「거의 다 됐습니다」로 줄이면 사람은 기다리기만 한다. 무엇이 남았는지
  이름으로 적는다.

## 순수하다

`readiness.py` 가 저장소를 모르는 것과 같은 이유로, 이 모듈도 **넘겨받은 값만 본다.**
같은 입력이면 같은 제안이 나온다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am

#: 수집 제안이 의미 있는 준비도 상태. **닫힌 목록**이다.
#:   ⚠️ `QUALITY_FAILED`·`RECONCILIATION_FAILED` 는 넣지 않는다 — 그것은 «원천이 없다» 가
#:     아니라 «받아온 것이 틀렸다» 이고, 새 원천을 권하면 원인을 덮는다.
SUGGESTIBLE_STATES: Tuple[str, ...] = ("NOT_CONFIGURED", "SOURCE_CONFIGURED")

#: 이미 수집돼 있으나 결속되지 않은 것을 부를 이름. 화면이 문구를 지어내지 않게.
GAP_NO_SOURCE = "NO_SOURCE_YET"
GAP_COLLECTED_NOT_BOUND = "COLLECTED_NOT_BOUND"
GAP_NO_PROVIDER = "NO_PROVIDER_FOR_THIS_CONTRACT"

GAP_LABELS: Dict[str, str] = {
    GAP_NO_SOURCE: "원천을 아직 고르지 않았습니다 — 아래 원천으로 채울 수 있습니다.",
    GAP_COLLECTED_NOT_BOUND: ("이미 수집돼 격리 저장소에 있습니다. 업무키트에 결속되지 "
                              "않아 준비도는 아직 오르지 않았습니다."),
    GAP_NO_PROVIDER: ("이 계약을 채울 수 있는 원천이 아직 등록되지 않았습니다 — "
                      "원천을 등록하거나 파일로 올려야 합니다."),
}


@dataclass(frozen=True)
class SourceOption:
    """이 계약을 채울 수 있는 원천 하나. **한계를 함께 들고 다닌다.**"""
    provider_id: str
    name: str
    publisher: str
    cost: str
    trust_grade: str
    refresh_frequency: str
    requires_credential: bool
    credential_configured: bool
    data_origin: str
    #: ★★★ 「이 값으로 하면 안 되는 것」. 제안에서 떼면 고르는 순간 사라진다.
    known_limits: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {"provider_id": self.provider_id, "name": self.name,
                "publisher": self.publisher, "cost": self.cost,
                "trust_grade": self.trust_grade,
                "refresh_frequency": self.refresh_frequency,
                "requires_credential": self.requires_credential,
                "credential_configured": self.credential_configured,
                "data_origin": self.data_origin,
                "known_limits": list(self.known_limits)}


@dataclass(frozen=True)
class Suggestion:
    """한 데이터셋에 대한 제안. **준비도 상태는 그대로 실어 보낸다** — 덮지 않는다."""
    dataset_contract_key: str
    readiness_state: str
    gap: str
    options: Tuple[SourceOption, ...] = ()
    collected_rows: int = 0
    #: ★ 결속까지 무엇이 남았는지 **이름으로**. 「거의 다 됐다」로 줄이지 않는다.
    remaining_steps: Tuple[str, ...] = ()

    @property
    def actionable(self) -> bool:
        """지금 사람이 할 수 있는 일이 있는가."""
        return bool(self.options) or self.gap == GAP_COLLECTED_NOT_BOUND

    def as_dict(self) -> Dict[str, Any]:
        return {"dataset_contract_key": self.dataset_contract_key,
                "readiness_state": self.readiness_state,
                "gap": self.gap, "gap_label": GAP_LABELS.get(self.gap, ""),
                "options": [o.as_dict() for o in self.options],
                "collected_rows": self.collected_rows,
                "remaining_steps": list(self.remaining_steps),
                "actionable": self.actionable}


#: 격리 적재본이 업무키트 준비도로 이어지려면 남은 단계. **이름으로 적는다.**
#: ⚠️ 마지막 둘은 아직 만들지 않았다 — 「거의 다 됐다」로 줄이면 사람은 기다리기만 한다.
REMAINING_AFTER_COLLECTION: Tuple[str, ...] = (
    "수집한 계약을 업무키트 판(version)에 편입",
    "Snapshot 인증(RAW → … → 인증판)",
    "데이터셋 결속(source binding) 활성화",
    "준비도 재평가",
)


def _option(descriptor: Any, *, env: Optional[Mapping[str, str]] = None) -> SourceOption:
    configured = True
    if descriptor.requires_credential:
        configured = bool(str((env or {}).get(descriptor.credential_env, "") or "").strip())
    return SourceOption(
        provider_id=descriptor.provider_id, name=descriptor.name,
        publisher=descriptor.publisher, cost=descriptor.cost,
        trust_grade=descriptor.default_trust_grade,
        refresh_frequency=descriptor.refresh_frequency,
        requires_credential=descriptor.requires_credential,
        credential_configured=configured,
        data_origin=descriptor.data_origin,
        known_limits=tuple(descriptor.known_limits))


def suggest_for_dataset(readiness_row: Mapping[str, Any], *, descriptors: Sequence[Any],
                        collected_rows: int = 0,
                        env: Optional[Mapping[str, str]] = None) -> Optional[Suggestion]:
    """데이터셋 하나에 대한 제안. 제안할 것이 없으면 `None`.

    ⚠️ **준비된 데이터셋에는 제안하지 않는다.** 「더 좋은 원천이 있습니다」는 이 자리의
      질문이 아니고, 그것을 섞으면 화면이 「무엇이 부족한가」를 못 보여 준다."""
    key = str(readiness_row.get("dataset_contract_key") or "").strip()
    state = str(readiness_row.get("state") or "")
    if not key or state not in SUGGESTIBLE_STATES:
        return None

    options = tuple(_option(d, env=env) for d in descriptors
                    if key in getattr(d, "target_contract_keys", ()))

    if collected_rows > 0:
        #: ★★★ 받아 온 것과 결속된 것은 다르다 — 둘 다 말한다.
        return Suggestion(dataset_contract_key=key, readiness_state=state,
                          gap=GAP_COLLECTED_NOT_BOUND, options=options,
                          collected_rows=int(collected_rows),
                          remaining_steps=REMAINING_AFTER_COLLECTION)
    if not options:
        return Suggestion(dataset_contract_key=key, readiness_state=state,
                          gap=GAP_NO_PROVIDER)
    return Suggestion(dataset_contract_key=key, readiness_state=state,
                      gap=GAP_NO_SOURCE, options=options)


def suggest(readiness_rows: Iterable[Mapping[str, Any]], *, descriptors: Sequence[Any],
            collected_by_contract: Optional[Mapping[str, int]] = None,
            env: Optional[Mapping[str, str]] = None) -> List[Suggestion]:
    """여러 데이터셋에 대한 제안. **순수** — 넘겨받은 값만 본다."""
    counts = dict(collected_by_contract or {})
    out: List[Suggestion] = []
    for row in readiness_rows:
        key = str(row.get("dataset_contract_key") or "")
        suggestion = suggest_for_dataset(row, descriptors=descriptors,
                                         collected_rows=int(counts.get(key, 0) or 0),
                                         env=env)
        if suggestion is not None:
            out.append(suggestion)
    #: 지금 손댈 수 있는 것을 앞에 둔다 — 자격증명이 없어 못 쓰는 원천만 있는 계약은 뒤로.
    out.sort(key=lambda s: (not s.actionable, s.dataset_contract_key))
    return out


def summarise(suggestions: Sequence[Suggestion]) -> Dict[str, Any]:
    """화면 머리말용 요약. **「준비도가 오른다」고 말하지 않는다.**"""
    collected = [s for s in suggestions if s.gap == GAP_COLLECTED_NOT_BOUND]
    fillable = [s for s in suggestions if s.gap == GAP_NO_SOURCE]
    stuck = [s for s in suggestions if s.gap == GAP_NO_PROVIDER]
    return {
        "total": len(suggestions),
        "fillable_by_a_source": len(fillable),
        "collected_but_not_bound": len(collected),
        "no_provider_yet": len(stuck),
        "notice": ("수집은 준비도를 **자동으로 올리지 않습니다** — 인증과 업무키트 결속이 "
                   "끝나야 오릅니다. 각 항목의 «남은 단계»를 보십시오."),
    }
