# ==========================================
# WBS 요구 누락 검사 (2026-07-27)
#
# 'WBS 가 잘못됐다'의 가장 흔한 형태는 **처리할 내용이 통째로 빠진 것**이다.
# 기존 PMO 검사는 태스크 개수·에이전트 배정 유무·태스크 크기만 봤고 요구 누락은 보지 않았다.
# 누락은 QA 의 fr_coverage 에서야 드러나는데 그때는 이미 다 만든 뒤라 되돌리는 비용이 가장 크다.
# WBS 시점에 잡으면 재분할 한 번으로 끝난다.
# ==========================================
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from criteria import DETERMINISTIC_CHECKS, STAGE_RUBRICS

_check = DETERMINISTIC_CHECKS["wbs_fr_coverage"]


class _S:
    """WBS 를 디스크에서 읽는 _read_wbs_tasks 를 우회하기 위해 wbs_tasks 를 직접 물린다."""
    def __init__(self, prd, tasks, tmp):
        self.prd_summary = prd
        self.workspace_root = str(tmp)
        os.makedirs(tmp, exist_ok=True)
        with open(os.path.join(tmp, "00_wbs_master_plan.json"), "w", encoding="utf-8") as f:
            json.dump({"tasks": tasks}, f, ensure_ascii=False)


_PRD = "FR-001 단위 변환, FR-002 이력 저장, FR-003 이력 삭제"


def test_all_frs_assigned_passes(tmp_path):
    s = _S(_PRD, [
        {"title": "변환", "goal": "FR-001 구현", "scope": ""},
        {"title": "이력", "goal": "FR-002, FR-003 구현", "scope": ""},
    ], tmp_path)
    assert _check(s) is True


def test_missing_fr_fails(tmp_path):
    """FR-003 이 어느 태스크에도 없으면 실패해야 한다 — 이게 이 검사의 존재 이유다."""
    s = _S(_PRD, [
        {"title": "변환", "goal": "FR-001 구현", "scope": ""},
        {"title": "이력", "goal": "FR-002 구현", "scope": ""},
    ], tmp_path)
    assert _check(s) is False


def test_fr_ids_field_also_counts(tmp_path):
    s = _S(_PRD, [
        {"title": "전부", "goal": "", "scope": "", "fr_ids": ["FR-001", "FR-002", "FR-003"]},
    ], tmp_path)
    assert _check(s) is True


def test_prd_without_fr_ids_is_not_blocked(tmp_path):
    """PRD 가 FR-ID 표기를 안 쓰는 형식이면 이 검사로 막지 않는다(오차단 방지)."""
    s = _S("단위 변환과 이력 저장이 필요합니다", [{"title": "구현", "goal": "", "scope": ""}], tmp_path)
    assert _check(s) is True


def test_empty_wbs_fails_when_frs_exist(tmp_path):
    s = _S(_PRD, [], tmp_path)
    assert _check(s) is False


def test_pmo_rubric_wires_the_check_and_stays_binary():
    """PMO 는 이진이다 — 임계 1.0 이 유지되어야 하고, 새 검사가 실제로 배선돼 있어야 한다."""
    pmo = STAGE_RUBRICS["PMO"]
    ids = [c["id"] for c in pmo["checks"]]
    assert "wbs_fr_coverage" in ids, "요구 누락 검사가 PMO 루브릭에 배선되지 않았습니다"
    assert pmo["pass_threshold"] == 1.0, (
        "WBS 는 이진이다 — '미흡하지만 통과'를 허용하면 잘못된 분할 위에 모든 구현이 얹힌다")
