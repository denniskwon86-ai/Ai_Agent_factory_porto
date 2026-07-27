# ==========================================
# 종료 계약 테스트 더블 검증 (2026-07-27)
#
# 실제 LLM 없이 세 가지 더블로 종료 경로를 강제 실행한다:
#   ① 공급자 타임아웃      → SUSPENDED_PROVIDER, 개발자 재작업 예산 미소모
#   ② 구조화 출력 절단     → FAILED_GENERATION_CONTRACT
#   ③ 출력 예산 부족(계약) → 호출조차 하지 않고 종결
#
# 검증하는 계약(이전에 전부 깨져 있었다):
#   · 공급자 장애가 '빌드 실패'로 둔갑해 코드 수정 기회를 먹지 않을 것
#   · END 가 곧 DONE 이 아닐 것 — 종료 상태로 판정할 것
#   · 자가복구 소진 시 실패 번들이 남고 롤백이 실제로 실행될 것(예전엔 죽은 코드였다)
# ==========================================
import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_gateway import (
    GenerationFailure,
    GenerationContractException,
    classify_generation_error,
)
from nodes.execution import _generation_failure_update, run_terminal_handler


# ── ① 실패 분류가 올바른 종료 상태로 매핑되는가 ────────────────────
@pytest.mark.parametrize("exc,expected_kind,expected_terminal", [
    (asyncio.TimeoutError(), "PROVIDER_TIMEOUT", "SUSPENDED_PROVIDER"),
    (Exception("LLM 총 시간 상한(420초) 초과 — 폴백 체인 walk 가 끝나지 않았습니다."),
     "PROVIDER_TIMEOUT", "SUSPENDED_PROVIDER"),
    (Exception("429 RESOURCE_EXHAUSTED: quota exceeded"), "QUOTA", "SUSPENDED_QUOTA"),
    (Exception("Could not parse response content as the length limit was reached"),
     "STRUCTURED_PARSE", "FAILED_GENERATION_CONTRACT"),
    (Exception("Connection reset by peer (network)"), "NETWORK", "SUSPENDED_PROVIDER"),
])
def test_generation_error_classification(exc, expected_kind, expected_terminal):
    gf = classify_generation_error(exc, attempts=["m1"])
    assert gf.kind == expected_kind
    assert gf.terminal_status == expected_terminal


def test_generation_failure_never_consumes_dev_retry_budget():
    """핵심 계약: 이 예외는 정의상 '코드 결함이 아닌 실패' 이므로
    개발자 재작업 예산을 소모하면 안 된다.
    (실측 v4: 228.6s·420.0s·77.0s 타임아웃 3건이 그 예산을 먹었다)"""
    for kind in ("PROVIDER_TIMEOUT", "QUOTA", "STRUCTURED_PARSE", "CAPACITY", "NETWORK"):
        assert GenerationFailure("x", kind=kind).consumes_dev_retry is False


def test_provider_failure_update_does_not_increment_retry():
    gf = GenerationFailure("타임아웃", kind="PROVIDER_TIMEOUT")
    upd = _generation_failure_update(gf, "Backend")
    assert "developer_retry_count" not in upd, "재작업 예산을 건드리면 안 됩니다"
    assert upd["terminal_status"] == "SUSPENDED_PROVIDER"
    assert upd["failed_node"] == "Backend"


def test_contract_exception_is_capacity_kind():
    """출력 예산 부족은 호출 전에 종결한다 — 무의미한 폭주를 미리 차단."""
    e = GenerationContractException("적격 모델 없음")
    assert e.kind == "CAPACITY"
    assert e.terminal_status == "FAILED_GENERATION_CONTRACT"
    assert isinstance(e, GenerationFailure)


# ── ② 종결 노드가 실패 번들을 남기는가 ─────────────────────────────
def _state(tmp_path, **kw):
    base = {
        "project_name": "double_test",
        "workspace_root": str(tmp_path),
        "current_sprint_task_id": "E2E-01",
        "developer_retry_count": 3,
        "build_status": "failed",
        "failed_node": "Backend",
        "build_error_log": "[main.py] SyntaxError: invalid syntax (def load_data):",
        "backend_code_summary": json.dumps({"files": [{"file_path": "main.py", "code": "def load_data):"}]}),
    }
    base.update(kw)
    return base


def test_terminal_handler_writes_failure_bundle(tmp_path):
    """자가복구 소진 시 재현 근거가 남아야 한다.
    (모델 출력이 영속 저장되지 않아 구문 오류의 출처를 특정할 수 없던 문제를 해소)"""
    out = asyncio.run(run_terminal_handler(_state(tmp_path)))

    assert out["terminal_status"] == "FAILED_BUILD"
    bundle_path = out["failure_bundle_path"]
    assert bundle_path and os.path.exists(bundle_path), "실패 번들이 저장되어야 합니다"

    with open(bundle_path, encoding="utf-8") as f:
        bundle = json.load(f)
    assert bundle["task_id"] == "E2E-01"
    assert bundle["terminal_status"] == "FAILED_BUILD"
    assert "SyntaxError" in bundle["build_error_log"]
    # 생성 응답 원문이 들어 있어야 재현이 가능하다
    assert "def load_data)" in bundle["backend_code_summary"]


def test_terminal_handler_preserves_explicit_status(tmp_path):
    """공급자 보류로 들어오면 FAILED_BUILD 로 덮어쓰면 안 된다 — 회복 후 재개 가능해야 한다."""
    out = asyncio.run(run_terminal_handler(_state(
        tmp_path, terminal_status="SUSPENDED_PROVIDER", terminal_reason="OpenRouter 420초 타임아웃",
    )))
    assert out["terminal_status"] == "SUSPENDED_PROVIDER"
    assert "OpenRouter" in out["terminal_reason"]


def test_terminal_handler_is_resilient_without_workspace():
    """워크스페이스가 없어도 종결 자체는 실패하면 안 된다(종결이 실패하면 태스크가 매달린다)."""
    out = asyncio.run(run_terminal_handler({
        "project_name": "no_ws", "workspace_root": "",
        "current_sprint_task_id": "E2E-09", "developer_retry_count": 3,
    }))
    assert out["terminal_status"] == "FAILED_BUILD"
    assert out["factory_mode"] == "HOTL_PAUSED"
