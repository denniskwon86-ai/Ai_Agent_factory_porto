"""[P2] 판본별 정의 — 생성기 하나로 여러 판본을 만든다.

## 왜 필요한가

⚠️ 생성기에 `KIT_VERSION = "1.0.0"` 이 하드코딩돼 있었다. 1.1.0 을 내려면 그 줄을
  고쳐야 하는데, **고치는 순간 1.0.0 을 재현할 능력을 잃는다.** 판본이 늘어날 수 없는
  구조였고, 그래서 1.1.0 을 낸다는 것이 1.0.0 을 덮어쓰는 일이 됐다.

## 왜 「오버레이」인가 — 완전 분리가 아니라

★★★ 1.0.0 은 **동결된 판본**이다(P1). 새 구조로 재생성했을 때 **지문이 한 글자도
  달라지면 안 된다.** 1,300 줄 생성기에서 정의를 전부 뽑아내면 그 과정에서 순서·
  공백·기본값이 미묘하게 달라지고, 그것을 지문이 잡아낸다.

그래서 **기본 정의는 생성기에 그대로 두고, 판본별 「차이」만 얹는다.** 1.0.0 의
오버레이는 비어 있으므로 지금과 완전히 같은 결과가 나온다 — 이것이 P2-3 의 검증이다.

판본이 셋 이상으로 늘어 「기본이 무엇인지」가 흐려지면 그때 완전 분리로 옮긴다.
지금 그렇게 하지 않는 이유는 **동결 판본의 재현성이 그보다 중요하기 때문**이다.

## 왜 JSON 이 아니라 파이썬인가

이 정의는 사람이 손으로 고치는 것이고, **왜 그런지가 값보다 중요하다.** 「제련사는
금속 가격으로 벌지 않는다」 같은 설명이 JSON 에서는 살지 못한다. 값만 남은 표는
반년 뒤에 아무도 못 고친다.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable, Dict, List, Sequence, Tuple


class KitOverlay:
    """판본이 기본 정의에 얹는 차이. **비어 있으면 기본 그대로**다."""

    #: 이 판본이 만드는 키트
    kit_id: str = "KIT-MFG-NONFERROUS-PROCUREMENT"
    version: str = ""

    #: `generate_simulation_and_decisions()` 의 `driver_defs` 뒤에 붙는다.
    #: 튜플 형식: (driver_id, input_metric, output_metric, formula, lag_months, unit)
    extra_drivers: Sequence[Tuple[str, str, str, str, int, str]] = ()

    #: `scenarios_def` 뒤에 붙는다.
    #: (scenario_id, name, driver_id, change_value, change_unit, impact_metrics)
    extra_scenarios: Sequence[Tuple[str, str, str, float, str, str]] = ()

    #: `company_profiles()` 결과를 고친다 — {company_profile_id: {키: 새 값}}
    company_profile_patches: Dict[str, Dict[str, Any]] = {}

    #: manifest 최상위에 덮어쓸 값 (`industry_codes` 등)
    manifest_patches: Dict[str, Any] = {}

    def apply_drivers(self, base: List[Any]) -> List[Any]:
        return list(base) + list(self.extra_drivers)

    def apply_scenarios(self, base: List[Any]) -> List[Any]:
        return list(base) + list(self.extra_scenarios)

    def apply_company_profiles(self, base: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.company_profile_patches:
            return base
        out = []
        for p in base:
            patch = self.company_profile_patches.get(p.get("company_profile_id", ""))
            out.append({**p, **patch} if patch else p)
        return out

    def apply_manifest(self, base: Dict[str, Any]) -> Dict[str, Any]:
        return {**base, **self.manifest_patches} if self.manifest_patches else base


def _module_name(version: str) -> str:
    return "v" + version.replace(".", "_").replace("-", "_")


def load(version: str) -> KitOverlay:
    """판본 정의를 가져온다. **없는 판본은 만들지 않는다** — 오타로 새 판본이
    생기면 그것을 알아차리는 데 오래 걸린다."""
    name = _module_name(version)
    try:
        mod = importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as e:
        if getattr(e, "name", "") not in (f"{__name__}.{name}", name):
            raise
        raise SystemExit(
            f"판본 정의가 없습니다: {version}\n"
            f"  scripts/kit_defs/{name}.py 를 만드십시오. 기존 판본을 고치는 것이\n"
            f"  아니라 새 판본을 내는 것이 맞는지 먼저 확인하십시오."
        ) from None
    #: ★ 어떤 판본은 **다시 만들 수 없다.** 생성기 로직이 바뀌면 값 오버레이로는
    #:   되돌릴 수 없고, 그때 「돌렸더니 그 판본이 나왔는데 내용이 다른」 것이 가장
    #:   나쁘다. 그런 판본은 `REFUSE` 로 이유를 적고 만들기를 거부한다.
    refuse = getattr(mod, "REFUSE", "")
    if refuse:
        raise SystemExit(refuse)
    overlay = getattr(mod, "OVERLAY", None)
    if not isinstance(overlay, KitOverlay):
        raise SystemExit(f"scripts/kit_defs/{name}.py 에 OVERLAY(KitOverlay) 가 없습니다.")
    if overlay.version != version:
        raise SystemExit(
            f"판본 불일치: 요청 {version} · 정의 {overlay.version} — "
            f"복사해서 만들 때 version 을 고치지 않은 것으로 보입니다.")
    return overlay


def available() -> List[str]:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    out = []
    for f in sorted(os.listdir(here)):
        if f.startswith("v") and f.endswith(".py"):
            out.append(f[1:-3].replace("_", "."))
    return out
