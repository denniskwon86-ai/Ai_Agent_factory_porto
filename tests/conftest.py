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
    try:
        # 감사로그는 특히 중요하다 — 테스트가 남긴 거부 기록이 섞이면 "실제 침해 시도"를
        # 세는 지표가 오염되고, 반대로 테스트는 남의 기록을 보고 통과할 수 있다(실제 발생).
        from core.enterprise_context import audit
        monkeypatch.setattr(audit, "_LOG_PATH",
                            str(tmp_path / "access_audit.jsonl"), raising=False)
    except Exception:
        pass
    try:
        # 승격 기록도 같은 이유로 격리한다 — 테스트가 남긴 전사 승격이 실제 목록에 섞이면
        # "이 앱이 전사 앱인가"의 답이 틀린다.
        from core import workspace_promotion
        monkeypatch.setattr(workspace_promotion.workspace, "db_path",
                            str(tmp_path / "workspace.db"), raising=False)
        # 운영 준비(체크리스트·롤백)도 같은 저장소를 쓴다 — 롤백 기록이 실제 이력에 섞이면
        #   "이 릴리스가 내려간 적이 있나"의 답이 틀린다.
        from core import release_readiness
        monkeypatch.setattr(release_readiness.release_readiness, "db_path",
                            str(tmp_path / "workspace.db"), raising=False)
    except Exception:
        pass
    try:
        # Shadow run 은 "무엇을 승격했는가"의 근거다. 테스트가 남긴 승격 기록이 실제 목록에
        # 섞이면 운영 판단의 근거가 오염된다 — 감사로그와 같은 이유로 격리한다.
        from core import shadow_mode
        monkeypatch.setattr(shadow_mode.shadow_mode, "db_path",
                            str(tmp_path / "shadow_runs.db"), raising=False)
    except Exception:
        pass
    try:
        # 프로그램 사용여부도 격리한다 — 테스트가 남긴 비활성화가 실제 DB 에 들어가면
        # **실제 프로그램이 못 쓰게 된다.** 이건 오염이 아니라 사고다.
        from core import program_lifecycle
        monkeypatch.setattr(program_lifecycle.program_lifecycle, "db_path",
                            str(tmp_path / "program_lifecycle.db"), raising=False)
        monkeypatch.setattr(program_lifecycle.program_lifecycle, "_ready", "",
                            raising=False)
    except Exception:
        pass
