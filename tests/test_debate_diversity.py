"""nodes/utils/debate.py + core/llm_gateway.py — [3번] 토론 다양성 검증.

설계 docs/design_debate_diversity_cache.md §3 P1: 재작업 while 루프에서 캐시가 '동일 산출물'을
고정해 무한 동일 재작업에 빠지는 문제. 대응(방안 C):
  - gateway.aexecute(cacheable=False) 로 재작업·개정 경로 캐시 우회
  - 재작업 회차(attempt)를 프롬프트에 주입 → 회차마다 프롬프트(=해시)가 달라져 캐시 우회 + 다양성
pytest-asyncio 없이 asyncio.run 으로 구동(리포 관례).
"""
import asyncio
import pytest
import nodes.utils.debate as debate


def _capture_gateway(monkeypatch):
    """gateway.aexecute 를 가로채 (prompt, cacheable) 를 캡처하는 목."""
    from core.llm_gateway import gateway
    calls = []

    async def fake(state, prompt, **kw):
        calls.append({"prompt": prompt, "cacheable": kw.get("cacheable", True),
                      "output_mode": kw.get("output_mode")})
        return "revised-artifact"
    monkeypatch.setattr(gateway, "aexecute", fake)
    return calls


def test_single_revision_bypasses_cache(monkeypatch):
    calls = _capture_gateway(monkeypatch)
    asyncio.run(debate.run_single_revision(object(), "author", "prev", "fb", attempt=1, max_attempts=3))
    assert calls[-1]["cacheable"] is False               # 재작업은 항상 캐시 우회


def test_single_revision_attempt1_no_diversity_note(monkeypatch):
    calls = _capture_gateway(monkeypatch)
    asyncio.run(debate.run_single_revision(object(), "author", "prev", "fb", attempt=1, max_attempts=3))
    assert "회차" not in calls[-1]["prompt"]              # 1회차엔 다양성 문구 없음


def test_single_revision_attempt_injection_varies_prompt(monkeypatch):
    calls = _capture_gateway(monkeypatch)
    asyncio.run(debate.run_single_revision(object(), "author", "prev", "fb", attempt=2, max_attempts=3))
    asyncio.run(debate.run_single_revision(object(), "author", "prev", "fb", attempt=3, max_attempts=3))
    p2, p3 = calls[0]["prompt"], calls[1]["prompt"]
    assert "재작업 2/3회차" in p2 and "재작업 3/3회차" in p3
    assert p2 != p3                                      # 회차마다 프롬프트(해시) 상이 → 캐시 우회


def test_gateway_aexecute_accepts_cacheable_kwarg():
    """gateway.aexecute 시그니처에 cacheable 파라미터가 있어야 한다(기본 True=기존 동작)."""
    import inspect
    from core.llm_gateway import LLMGateway
    sig = inspect.signature(LLMGateway.aexecute)
    assert "cacheable" in sig.parameters
    assert sig.parameters["cacheable"].default is True   # 기본 True → draft/critique/judge 캐시 유지
