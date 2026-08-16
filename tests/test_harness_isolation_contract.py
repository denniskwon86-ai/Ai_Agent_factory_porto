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


def test_ledger_isolation_validates_its_own_path():
    """★★★ 결정 원장 격리는 **경로가 진짜 임시인지 스스로 확인**해야 한다.

    ⚠️ 이 규칙은 동작으로는 관찰되지 않는다 — 경로 계산이 옳은 한 검증을 통째로
      지워도 아무 시험이 깨지지 않는다(변이 검사에서 실측). 그런데 이 검증이
      막으려는 상황은 바로 «경로 계산이 틀어졌을 때» 다. 그래서 동작이 아니라
      **구조**를 잠근다.
    ⚠️ 2026-08-17 사고가 정확히 그 상황이었다: 격리했다고 믿었지만 경로가 운영
      파일이었고, 아무도 그것을 확인하지 않았다."""
    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fixture = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_isolate_runtime_telemetry"
    )
    called = {
        node.func.id
        for node in ast.walk(fixture)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "isolation_path_error" in called, (
        "conftest 가 결정 원장 격리 경로를 검증하지 않는다 — 경로가 운영 data/ 로 "
        "해석돼도 그대로 진행한다")

    # 그 판정 결과가 **실제로 예외로 이어지는지**까지 본다. 불러 놓고 버리면
    # 검증한 척이 된다.
    raises = [n for n in ast.walk(fixture)
              if isinstance(n, ast.Raise)]
    assert raises, "격리 경로 검증이 실패해도 아무것도 올리지 않는다"


def test_decision_ledger_is_in_the_isolation_list():
    """⚠️ 이 항목이 «없어서» 사고가 났다. 이름이 사라지면 다시 조용히 운영에 쓴다."""
    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    assert "decision_ledger" in source, "결정 원장이 격리 목록에서 사라졌다"
    assert '"_DB_PATH"' in source, "모듈 기본 경로를 갈아 끼우지 않는다"
    assert "decision_ledger, \"db_path\"" in source or \
           "decision_ledger, 'db_path'" in source, "전역 싱글턴을 갈아 끼우지 않는다"


def test_session_level_live_ledger_watch_exists():
    """★★★ 세션 **시작과 끝**을 대조하는 감시가 있어야 한다.

    ⚠️ 개별 시험의 앞뒤만 보면 «격리 fixture 를 타지 않은 경로»와 «수집 단계의
      쓰기»를 못 잡는다 — 이번 사고의 두 원인이 정확히 그 둘이었다.
    ⚠️ 이 규칙도 동작으로는 관찰되지 않는다(감시를 지워도 다른 시험은 초록이다).
      그래서 구조를 잠근다."""
    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    watch = next(
        (n for n in tree.body
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "_live_ledger_must_not_move"), None)
    assert watch is not None, "세션 단위 운영 원장 감시 fixture 가 없다"

    asserts = [n for n in ast.walk(watch) if isinstance(n, ast.Assert)]
    assert len(asserts) >= 2, "세션 감시가 원장 상태와 WAL/SHM 을 둘 다 보지 않는다"
    # `assert True or …` 같은 무력화를 막는다 — 상수로 시작하는 단언은 늘 참이다
    for a in asserts:
        assert not isinstance(a.test, ast.Constant), "세션 감시 단언이 상수로 무력화됐다"
        if isinstance(a.test, ast.BoolOp) and isinstance(a.test.op, ast.Or):
            assert not any(isinstance(v, ast.Constant) and bool(v.value)
                           for v in a.test.values), "세션 감시 단언이 «or True» 로 무력화됐다"


def test_ledger_isolation_happens_at_import_time():
    """★★★ 격리가 **모듈 최상단**에 있어야 한다 — fixture 는 수집보다 늦다."""
    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    first_def = next((i for i, n in enumerate(tree.body)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))),
                     len(tree.body))
    top = ast.unparse(ast.Module(body=tree.body[:first_def], type_ignores=[]))
    assert "_DB_PATH" in top, "모듈 최상단에서 원장 기본 경로를 돌려놓지 않는다"
    assert "decision_ledger.db_path" in top, "모듈 최상단에서 전역 싱글턴을 돌려놓지 않는다"
    assert "raise" in top, "수집 시점 격리 실패를 삼킨다"
