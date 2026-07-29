"""테스트 전역 격리 — **테스트가 실제 운영 로그를 오염시키지 않게 한다.**

## 왜 필요한가 (2026-07-29 실측)

`data/quality_outcomes.jsonl` 에 프로젝트명이 빈 실패 기록 4건이 쌓여 있었다. 카나리가 남긴
것이 아니라 **pytest 가 남긴 것**이었다 — 게이트 계측이 `nodes/utils/scoring.py` 에 붙어
있으므로, 채점기를 부르는 어떤 테스트든 실로그에 한 줄을 쓴다.

⚠️ 이건 단순한 지저분함이 아니다. 그 로그는 **품질 지표의 원천**이고, 카나리 증적으로 제출된다.
  테스트가 만든 가짜 실패가 섞이면 "게이트 실패율"이 오염되고, 그 숫자로 모델·프롬프트를
  판단하게 된다. 계측의 신뢰성은 "무엇이 들어오는가"만큼 **"무엇이 들어오지 않는가"** 에 달렸다.

개별 테스트가 자기 것을 monkeypatch 하는 것으로는 부족하다 — 계측을 의식하지 않는 테스트가
문제이기 때문이다. 그래서 **전역 autouse** 로 막는다.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_telemetry(tmp_path, monkeypatch):
    """모든 테스트의 텔레메트리 기록을 tmp 로 돌린다(개별 테스트가 다시 덮어써도 무해)."""
    try:
        from core import quality_telemetry
        monkeypatch.setattr(quality_telemetry, "_LOG_PATH",
                            str(tmp_path / "quality_outcomes.jsonl"), raising=False)
    except Exception:
        pass
    try:
        import core.llm_gateway as gw
        monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH",
                            str(tmp_path / "llm_call_log.jsonl"), raising=False)
    except Exception:
        pass
