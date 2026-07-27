# ==========================================
# CodeBuilder 트랜잭션 계약 테스트 (2026-07-27, C4)
#
# 고치는 결함 두 가지:
#   ① "한 파일만 써져도 성공" — 기존 판정이 `any(results)` 였다. 3개 중 1개만 써져도
#      build_status=success 가 되어 반쯤 쓰인 워크스페이스가 커밋되고, 다음 태스크가
#      그 위에서 돌았다.
#   ② 부분 쓰기 오염 — 파일 단위 원자성은 있었지만 프로젝트 단위 트랜잭션이 아니었다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.code_builder import CodeBuilder


def _files(*pairs):
    return [{"file_path": p, "code": c} for p, c in pairs]


def test_all_files_written_marks_success(tmp_path):
    b = CodeBuilder(workspace_root=str(tmp_path))
    state, results = b.run({}, _files(
        ("src/a.ts", "export const a = 1;"),
        ("src/b.ts", "export const b = 2;"),
        ("main.py", "print('x')"),
    ))
    assert state["build_status"] == "success"
    assert results == [True, True, True]
    assert (tmp_path / "src" / "a.ts").read_text(encoding="utf-8") == "export const a = 1;"
    assert (tmp_path / "main.py").exists()


def test_candidate_staging_area_is_cleaned_up(tmp_path):
    """후보 영역(.candidate)이 산출물로 남으면 안 된다 — 컨텍스트·프리뷰가 중복 인식한다."""
    b = CodeBuilder(workspace_root=str(tmp_path))
    b.run({}, _files(("src/a.ts", "export const a = 1;")))
    assert not (tmp_path / ".candidate").exists()


def test_partial_write_failure_does_not_leave_partial_workspace(tmp_path, monkeypatch):
    """두 번째 파일 쓰기가 실패하면 실물에 아무것도 남기지 않고 failed 로 끝나야 한다."""
    b = CodeBuilder(workspace_root=str(tmp_path))

    real_write = b._atomic_write
    calls = {"n": 0}

    def flaky(full_path, code):
        # 후보 단계(.candidate)의 두 번째 파일에서 실패시킨다.
        if ".candidate" in str(full_path):
            calls["n"] += 1
            if calls["n"] == 2:
                return False
        return real_write(full_path, code)

    monkeypatch.setattr(b, "_atomic_write", flaky)

    state, results = b.run({}, _files(
        ("src/a.ts", "export const a = 1;"),
        ("src/b.ts", "export const b = 2;"),
    ))

    assert state["build_status"] == "failed", "부분 반영은 실패로 처리되어야 합니다"
    # 후보 단계에서 끊겼으므로 실물에는 아무 파일도 없어야 한다.
    assert not (tmp_path / "src" / "a.ts").exists(), "실물 워크스페이스가 부분 반영으로 오염되면 안 됩니다"
    assert not (tmp_path / "src" / "b.ts").exists()
    assert "완전하지 않" in state["build_error_log"]


def test_no_valid_files_is_failure_with_reason(tmp_path):
    b = CodeBuilder(workspace_root=str(tmp_path))
    state, results = b.run({}, _files(("src/empty.ts", ""), ("", "code")))
    assert state["build_status"] == "failed"
    assert results == []
    assert "유효한 파일이 없습니다" in state["build_error_log"]


def test_file_index_updated_only_for_promoted_files(tmp_path):
    b = CodeBuilder(workspace_root=str(tmp_path))
    state = {"current_sprint_task_id": "E2E-01"}
    state, _ = b.run(state, _files(("src/a.ts", "export const a = 1;")))
    assert "src/a.ts" in state["file_index"]
    assert state["file_index"]["src/a.ts"]["last_modified_task"] == "E2E-01"
