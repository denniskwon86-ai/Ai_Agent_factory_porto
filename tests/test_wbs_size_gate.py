"""WBS 태스크 크기 결정론 게이트 + JUDGE_FORCE_HEAVY 되돌림 검증 — LLM 0콜."""
import json
from types import SimpleNamespace

import config
from criteria import DETERMINISTIC_CHECKS, STAGE_RUBRICS


def _state_with_wbs(tmp_path, tasks):
    (tmp_path / "00_wbs_master_plan.json").write_text(
        json.dumps({"tasks": tasks}), encoding="utf-8")
    return SimpleNamespace(workspace_root=str(tmp_path))


# ── wbs_task_sizes 게이트 ─────────────────────────────────────────────────────
def test_wbs_sizes_pass_when_all_within_cap(tmp_path):
    check = DETERMINISTIC_CHECKS["wbs_task_sizes"]
    s = _state_with_wbs(tmp_path, [
        {"task_id": "T1", "estimated_token_budget": 5000},
        {"task_id": "T2", "estimated_token_budget": 8000},
    ])
    assert check(s) is True


def test_wbs_sizes_fail_when_task_oversized(tmp_path):
    check = DETERMINISTIC_CHECKS["wbs_task_sizes"]
    s = _state_with_wbs(tmp_path, [
        {"task_id": "T1", "estimated_token_budget": 5000},
        {"task_id": "T_BIG", "estimated_token_budget": config.WBS_MAX_TASK_TOKENS + 1},
    ])
    assert check(s) is False


def test_wbs_sizes_missing_field_is_vacuous_pass(tmp_path):
    # 필드 없음/비숫자는 판단 불가 → 통과(오차단 방지)
    check = DETERMINISTIC_CHECKS["wbs_task_sizes"]
    s = _state_with_wbs(tmp_path, [
        {"task_id": "T1"},
        {"task_id": "T2", "estimated_token_budget": "n/a"},
    ])
    assert check(s) is True


def test_wbs_sizes_no_tasks_pass(tmp_path):
    check = DETERMINISTIC_CHECKS["wbs_task_sizes"]
    s = _state_with_wbs(tmp_path, [])
    assert check(s) is True


def test_pmo_rubric_registers_size_check():
    ids = [c["id"] for c in STAGE_RUBRICS["PMO"]["checks"]]
    assert "wbs_task_sizes" in ids
    # 과대 태스크는 재분할을 유도해야 하나 hard_fail 은 아님(soft 게이트)
    assert "wbs_task_sizes" not in STAGE_RUBRICS["PMO"]["hard_fail_checks"]


# ── JUDGE_FORCE_HEAVY 되돌림 ──────────────────────────────────────────────────
def test_judge_force_heavy_reverted():
    assert config.JUDGE_FORCE_HEAVY is False
