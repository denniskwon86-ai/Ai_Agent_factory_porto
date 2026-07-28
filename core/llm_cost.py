"""LLM 호출 비용 산정 — P0 「비용 관측」 / 마스터 명세서 §10.1·§10.3.

⚠️ 이 모듈의 존재 이유는 "숫자를 만들어내는 것"이 아니라 **모르는 것을 모른다고 표시하는 것**이다.
  §10.1 의 핵심 KPI(승인된 결과물 1건당 비용)를 근거 없는 단가로 채우면 그럴듯한 거짓 숫자가
  경영 판단에 들어간다. 마스터 명세서 §16(비협상 조건)과 §5.2 원칙이 "근거 데이터가 없는 수치는
  '검증되지 않은 추정'으로 표시한다"고 못 박은 것이 바로 이 경우다.
  → 단가를 모르는 유료 모델은 비용을 **0 으로 두지 않고** `unpriced` 로 분리한다. 0 으로 두면
    "이 프로젝트는 공짜였다"는 거짓말이 되고, 임의 추정치를 넣으면 근거 없는 숫자가 된다.

이 파일은 `config` 만 의존한다. 두 가지 이유로 게이트웨이에서 분리했다:
  ① 텔레메트리 집계 API 가 무거운 LLM 의존성 없이 import 할 수 있어야 한다.
  ② 그래야 **단가표를 채운 뒤 과거 로그를 소급 산정**할 수 있다 — 기존 로그에 이미
    `used`/`input_tokens`/`output_tokens` 가 남아 있으므로 비용만 나중에 계산해 붙일 수 있다.
"""
from typing import Optional, Tuple

import config

# 캐시 적중은 API 호출이 아니다 — 비용 0 이 추정이 아니라 사실인 유일한 경우.
_CACHE_SENTINELS = {"cache_hit"}


def is_paid_model(name: str) -> bool:
    """유료/종량제 모델인가.

    판정 규약은 `config.PAID_MODEL_MARKERS` 로, 쿨다운 정책이 쓰는 것과 **같은 기준**이다
    (`llm_gateway._is_paid_model` 이 이 함수에 위임한다 — 두 곳에 두면 조용히 어긋난다).
    OpenRouter 유료 슬러그는 `:free` 접미사가 없다."""
    if not name or name.endswith(":free"):
        return False
    markers = getattr(config, "PAID_MODEL_MARKERS", ()) or ()
    return any(m in name for m in markers)


def provider_of(model: str) -> str:
    """모델명 → 제공사(마스터 명세서 §10.3 `provider`).

    `ENGINE_TIERS` 를 역인덱스로 쓴다 — 제공사 맵을 새로 하드코딩하면 모델을 교체할 때마다
    두 곳을 고쳐야 하고, 한 곳만 고치면 텔레메트리가 조용히 틀린 제공사를 보고한다."""
    m = (model or "").strip()
    if not m:
        return ""
    if m in _CACHE_SENTINELS:
        return "cache"
    if "/" in m:
        return "openrouter"          # OpenRouter 슬러그는 `provider/model` 형식
    for engine, tiers in (getattr(config, "ENGINE_TIERS", {}) or {}).items():
        if m in ((tiers or {}).values()):
            return engine
    # `PRO_TIER_EXTRA_GEMINI` 같은 변종 풀은 ENGINE_TIERS 에 없다 → 접두어로 보완.
    if m.startswith("gemini-"):
        return "gemini"
    if m.startswith("grok-"):
        return "xai"
    return ""


def estimate_cost_usd(model: str, input_tokens: int = 0,
                      output_tokens: int = 0) -> Tuple[Optional[float], str]:
    """(비용 USD | None, 산정근거) 를 돌려준다.

    산정근거(`cost_basis`)는 집계가 **거짓 합계를 내지 않도록** 하는 장치다:
      · `cache_hit`     — 캐시 적중, API 호출 없음. 0 이 사실.
      · `free_tier`     — 무료 티어 직접 호출. 과금 0 이 사실.
                          ⚠️ 단 '유한 일일 쿼터'를 소진한다 — 그건 비용이 아니라 별도 지표다.
      · `paid`          — 유료. 입·출력 단가 모두 등록됨.
      · `paid_partial`  — 유료인데 단가 일부만 등록됨 → 아는 부분만 합산(과소 추정임을 명시).
      · `unpriced`      — 유료인데 단가 미등록 → **None**. 0 으로 두면 공짜라는 거짓이 된다.
    """
    m = (model or "").strip()
    if m in _CACHE_SENTINELS:
        return 0.0, "cache_hit"
    if not m:
        return None, "unpriced"
    if not is_paid_model(m):
        return 0.0, "free_tier"

    price = (getattr(config, "LLM_PRICE_PER_MTOK", {}) or {}).get(m)
    if not price:
        return None, "unpriced"
    p_in, p_out = price.get("in"), price.get("out")
    if p_in is None and p_out is None:
        return None, "unpriced"

    cost = 0.0
    if p_in is not None:
        cost += (max(0, int(input_tokens or 0)) / 1_000_000.0) * float(p_in)
    if p_out is not None:
        cost += (max(0, int(output_tokens or 0)) / 1_000_000.0) * float(p_out)
    basis = "paid" if (p_in is not None and p_out is not None) else "paid_partial"
    return round(cost, 6), basis
