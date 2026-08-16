"""테스트 하니스가 격리 실패 뒤 운영 경로로 계속 진행하지 않는지 잠근다."""
from __future__ import annotations

import ast
from pathlib import Path


def test_runtime_isolation_is_fail_closed():
    """모든 격리 예외 처리기는 테스트를 실패시키는 경로를 호출해야 한다.

    경고 출력이나 ``pass``는 clean checkout에서는 보이지 않다가 개발 작업폴더의 운영 DB·
    프로젝트·템플릿에 쓰는 회귀를 다시 연다. 예외 처리기 수까지 고정하지는 않되, 새 격리
    대상이 추가돼도 같은 규칙을 자동 적용한다.
    """
    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fixture = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_isolate_runtime_telemetry"
    )
    handlers = [node for node in ast.walk(fixture) if isinstance(node, ast.ExceptHandler)]
    assert handlers, "런타임 격리 예외 처리기가 하나도 없다"

    for handler in handlers:
        calls = {
            node.func.id
            for node in ast.walk(handler)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "isolation_failed" in calls, (
            f"{handler.lineno}행 격리 실패가 fail-closed가 아니다"
        )
        assert not any(isinstance(node, ast.Pass) for node in ast.walk(handler)), (
            f"{handler.lineno}행 격리 실패를 pass로 삼켰다"
        )
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            for node in ast.walk(handler)
        ), f"{handler.lineno}행 격리 실패가 경고 출력 후 계속 진행한다"
