"""품질 결과 계측의 **배선**을 잠근다 — 생산자(파이프라인)와 소비자(로그)가 실제로 이어졌는가.

⚠️ 이 파일이 따로 있는 이유: 계측 모듈 단위 테스트는 전부 통과하는데 **아무도 호출하지 않는**
  상태가 이 프로젝트에서 반복된 결함 유형이다(주입 상한·별칭 히트 경로 모두 "테스트는 통과하고
  있었다"). 그래서 모듈이 아니라 **노드에서 호출되는지**를 본다.

여기서 LLM 은 한 번도 부르지 않는다(결정론 검사만 있는 rubric + 빌드 실패 경로).
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import quality_telemetry as qt


@pytest.fixture()
def log(tmp_path, monkeypatch):
    p = tmp_path / "quality_outcomes.jsonl"
    monkeypatch.setattr(qt, "_LOG_PATH", str(p))
    return p


def test_score_stage_records_the_gate_verdict(log, monkeypatch, tmp_path):
    """★★ 채점기가 판정을 내리면 반드시 계측 1건이 남는다(게이트 = 유일한 채점 지점)."""
    import core.work_standard as ws
    from state_models import ProjectState
    from nodes.utils import scoring

    # 결정론 검사 하나뿐인 rubric — LLM 을 부르지 않는다.
    monkeypatch.setattr(ws, "get_standard", lambda k: {
        "checks": [{"id": "rfp_min_length", "type": "deterministic", "weight": 1}],
        "pass_threshold": 0.7, "hard_fail_checks": ["rfp_min_length"],
    })

    state = ProjectState.model_validate({
        "project_name": "P", "workspace_root": str(tmp_path / "projects" / "p9"),
        "owner_dept_id": "D-BAT", "rfp_summary": "짧음",
    })
    result = asyncio.run(scoring.score_stage(state, "RFP"))

    events = qt.read_events()
    assert len(events) == 1, "채점은 됐는데 계측이 없다 — 배선 누락"
    rec = events[0]
    assert rec["gate_name"] == "RFP" and rec["verdict"] == result["verdict"]
    assert rec["pass_fail"] == "FAIL" and rec["owner_dept_id"] == "D-BAT"
    # 점수 미달의 원인은 자동 분류하지 않지만, 어느 기준이 미달인지는 사실로 남는다.
    assert rec["root_cause"] == qt.CAUSE_UNCLASSIFIED
    assert "rfp_min_length" in rec["failed_checks"]


def test_build_failure_records_with_classified_cause(log, tmp_path):
    """★★ 빌드 실패 반환지점이 여러 곳이라도 계측은 한 곳(`_build_failed`)을 통과한다."""
    from state_models import ProjectState
    from nodes.execution import _build_failed

    state = ProjectState.model_validate({
        "project_name": "P", "workspace_root": str(tmp_path / "projects" / "p9"),
    })
    out = _build_failed(state, "Frontend", "[src/App.tsx] SyntaxError: Unexpected token", 1)

    assert out["build_status"] == "failed" and out["developer_retry_count"] == 2
    rec = qt.read_events()[0]
    assert rec["gate_name"] == "BUILD"
    assert rec["root_cause"] == qt.CAUSE_MODEL_QUALITY          # 구문 오류 = 생성 코드 결함
    assert rec["root_cause_rule"] == "build:syntax_or_missing_symbol"


def test_builder_error_log_is_no_longer_dropped(log, tmp_path):
    """빌더가 남긴 실패 사유를 상태에 실어 보낸다.

    종전에는 이 경로에서 `build_error_log` 가 버려져 **자가복구 재시도가 원인을 모른 채**
    같은 프롬프트를 다시 돌렸다(자가복구 P1 의 전제가 깨진 상태였다)."""
    from state_models import ProjectState
    from nodes.execution import _build_failed

    state = ProjectState.model_validate({"project_name": "P", "workspace_root": str(tmp_path)})
    out = _build_failed(state, "Backend", "디스크 쓰기 실패: permission denied", 0)
    assert out["build_error_log"] == "디스크 쓰기 실패: permission denied"


def test_generation_failure_is_not_charged_to_the_code(log, tmp_path):
    """★★ 공급자 실패는 `외부 환경` 으로 남고 **개발자 재작업 예산을 소모하지 않는다**."""
    from state_models import ProjectState
    from core.llm_gateway import GenerationFailure
    from nodes.execution import _generation_failure_update

    state = ProjectState.model_validate({"project_name": "P", "workspace_root": str(tmp_path)})
    gf = GenerationFailure("총 시간 상한 초과", kind="PROVIDER_TIMEOUT")
    out = _generation_failure_update(gf, "Frontend", state)

    assert "developer_retry_count" not in out          # 예산을 태우지 않는다(기존 계약 유지)
    assert out["terminal_status"] == "SUSPENDED_PROVIDER"
    rec = qt.read_events()[0]
    assert rec["root_cause"] == qt.CAUSE_EXTERNAL_ENV
    assert rec["root_cause_rule"] == "gen_kind:PROVIDER_TIMEOUT"


def test_judge_infrastructure_failure_is_external_not_artifact_defect(log, tmp_path):
    """심판 LLM 장애가 '산출물 실패'로 집계되면 게이트 실패율이 공급자 장애로 부풀어 오른다."""
    from state_models import ProjectState
    from nodes.utils.scoring import _judge_unavailable, JudgeUnavailableError

    state = ProjectState.model_validate({"project_name": "P", "workspace_root": str(tmp_path)})
    exc = _judge_unavailable(state, "QA", "[QA] 심판 LLM 호출 실패(인프라 오류)")
    assert isinstance(exc, JudgeUnavailableError)
    rec = qt.read_events()[0]
    assert rec["root_cause"] == qt.CAUSE_EXTERNAL_ENV
    assert rec["root_cause_rule"] == "judge_unavailable"


def test_state_ref_reads_both_dict_and_object_states(log):
    """★ 체크포인트 상태가 dict 든 객체든 같은 식별을 뽑아야 한다.

    한쪽에서만 동작하면 그 형태의 세션에서만 사람 판정이 조용히 사라진다 —
    '기록은 되는데 어떤 환경에서만 빠지는' 유형이라 화면만 보고는 절대 못 찾는다."""
    from state_models import ProjectState

    d = {"project_name": "P", "owner_dept_id": "D-BAT", "current_stage": "QA"}
    o = ProjectState.model_validate({"project_name": "P", "owner_dept_id": "D-BAT",
                                     "current_stage": "QA", "workspace_root": "./projects/p9"})
    for st in (d, o):
        ref = qt.StateRef(st, workspace_root="./projects/p9", task_id="WBS-002")
        assert ref.project_name == "P" and ref.owner_dept_id == "D-BAT"
        assert ref.current_sprint_task_id == "WBS-002"
        qt.record_human_decision(ref, gate_name="HOTL", accepted=True, actor="u1")

    evs = qt.read_events()
    assert len(evs) == 2
    assert all(e["project_id"] == "p9" and e["owner_dept_id"] == "D-BAT" for e in evs)
