"""[DAO-2] Provider 등록부 — 「어떤 원천을 쓸 수 있고, 어느 것을 먼저 보는가」.

## 우선순위는 여기서 새로 정하지 않는다

지시 3 의 원천 우선순위(공식 API → 공식 공개 파일 → 계약 Provider → 공공기관 RSS·공시 →
일반 웹페이지)는 이미 `external_intelligence._SOURCE_PRIORITY` 에 값으로 있다. 두 번째
표를 만들면 두 표는 반드시 갈리고, 갈린 뒤에도 오류는 나지 않는다 — 화면이 A 순서로
보여 주고 적재는 B 순서로 도는 상태가 된다.

⚠️ **지시와 기존 표가 한 자리 다르다.** 기존 표는 `RSS=3 · PROVIDER_API=4` 인데 지시는
  「계약된 데이터 Provider」를 「공공기관 RSS·공시」보다 앞에 둔다. 지금 등록된 다섯 원천은
  전부 `API` 또는 `CSV` 라 이 차이가 결과를 바꾸지 않으므로 **기존 표를 그대로 쓰고**
  차이만 남겨 둔다. 바꿀 곳은 이 파일이 아니라 기존 표 하나다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Type

from core.external_intelligence.providers.base import (AcquisitionRequest, Checkpoint,
                                                       CheckResult, DiscoveryCandidate,
                                                       ExcludedSource, FetchResult,
                                                       NormalizedBatch, Provider,
                                                       ProviderCredentialError,
                                                       ProviderDescriptor, ProviderError,
                                                       ProviderTransportError, RejectedRow,
                                                       ValidationReport, https_get)

__all__ = [
    "AcquisitionRequest", "Checkpoint", "CheckResult", "DiscoveryCandidate", "ExcludedSource",
    "FetchResult", "NormalizedBatch", "Provider", "ProviderCredentialError",
    "ProviderDescriptor", "ProviderError", "ProviderTransportError", "RejectedRow",
    "ValidationReport", "https_get",
    "ProviderRegistry", "provider_registry", "register", "get", "descriptors", "ranked",
]


class ProviderRegistry:
    """Provider 구현의 등록부. **인스턴스를 캐시하지 않는다** — 환경(자격증명)이 호출마다
    다를 수 있고, 캐시하면 키를 바꿔도 옛 값을 쓴다."""

    def __init__(self):
        self._classes: Dict[str, Type[Provider]] = {}

    def register(self, cls: Type[Provider]) -> Type[Provider]:
        """클래스 데코레이터로도 쓴다."""
        desc = getattr(cls, "descriptor", None)
        if not isinstance(desc, ProviderDescriptor):
            raise ProviderError(f"{cls.__name__} 에 ProviderDescriptor 가 없습니다.")
        pid = desc.provider_id
        existing = self._classes.get(pid)
        if existing is not None and existing is not cls:
            raise ProviderError(
                f"provider_id 가 겹칩니다: {pid} (이미 {existing.__name__} 가 씀). "
                f"겹치면 어느 구현이 도는지 호출부가 알 수 없습니다.")
        self._classes[pid] = cls
        return cls

    def ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._classes))

    def get(self, provider_id: str, *, env: Optional[Mapping[str, str]] = None,
            transport=None) -> Provider:
        pid = str(provider_id or "").strip()
        cls = self._classes.get(pid)
        if cls is None:
            raise ProviderError(
                f"모르는 Provider 입니다: {pid!r}. 등록된 것: {', '.join(self.ids()) or '없음'}")
        return cls(env=env, transport=transport)

    def descriptors(self) -> Tuple[ProviderDescriptor, ...]:
        """원천 비교 카드의 원본. 화면은 이것만 보고 그린다."""
        return tuple(sorted((c.descriptor for c in self._classes.values()),
                            key=lambda d: (source_priority(d.source_type), d.provider_id)))

    def ranked(self, *, require_credential_present: bool = False,
               env: Optional[Mapping[str, str]] = None
               ) -> Tuple[Tuple[ProviderDescriptor, ...], Tuple[ExcludedSource, ...]]:
        """우선순위 순서와 **제외 사유 목록**을 함께 돌려준다(지시 3).

        ⚠️ 제외를 조용히 하면 화면이 「이 원천은 왜 안 보이나」에 답할 수 없다."""
        chosen: List[ProviderDescriptor] = []
        excluded: List[ExcludedSource] = []
        for desc in self.descriptors():
            if require_credential_present and desc.requires_credential:
                value = str((env or {}).get(desc.credential_env, "") or "").strip()
                if not value:
                    excluded.append(ExcludedSource(
                        desc.provider_id,
                        f"자격증명 미설정 — 환경변수 {desc.credential_env} 가 비어 있습니다."))
                    continue
            chosen.append(desc)
        return tuple(chosen), tuple(excluded)

    def for_contract(self, contract_key: str) -> Tuple[ProviderDescriptor, ...]:
        """이 데이터 계약을 채울 수 있는 원천들."""
        key = str(contract_key or "").strip()
        return tuple(d for d in self.descriptors() if key in d.target_contract_keys)


def source_priority(source_type: str) -> int:
    """지시 3 의 우선순위. **기존 표를 읽는다** — 여기서 숫자를 다시 적지 않는다."""
    from core.external_intelligence import _SOURCE_PRIORITY
    return int(_SOURCE_PRIORITY.get(str(source_type or ""), 99))


provider_registry = ProviderRegistry()
register = provider_registry.register
get = provider_registry.get
descriptors = provider_registry.descriptors
ranked = provider_registry.ranked
