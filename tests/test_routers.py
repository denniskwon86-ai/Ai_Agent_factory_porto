"""라우터·헬퍼 단위 테스트 — Phase 2 동적 빌더 전환의 '현행 동작' 골든 기준선.

라우터는 모두 상태만 받는 순수 함수다. LLM/네트워크 없이 SimpleNamespace 로 검증한다.
(게이트웨이 지연초기화 덕분에 core.agent_graph import 가 ~2s 로 빨라져 단위테스트 가능)
"""
import json
from types import SimpleNamespace
import config
import core.agent_graph as ag
from langgraph.graph import END


def S(**kw):
    base = dict(
        factory_mode="EXECUTION", current_sprint_task_id="T1", needs_revision=False,
        reviewer_decision="PASS", build_status="pending", developer_retry_count=0,
        failed_node="", current_required_agents=[], workspace_root="/no/such/dir",
        supervisor_hops=0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ── route_factory_mode ──────────────────────────────────────────────
def test_factory_mode_planning():
    assert ag.route_factory_mode(S(factory_mode="PLANNING")) == "RFP_Analyst"

def test_factory_mode_revision_to_techlead():
    assert ag.route_factory_mode(S(factory_mode="REVISION")) == "Tech_Lead"

def test_factory_mode_execution_first_is_architect():
    assert ag.route_factory_mode(S(current_required_agents=["Architect", "Backend"])) == "Architect"

def test_factory_mode_execution_skips_design_to_backend():
    assert ag.route_factory_mode(S(current_required_agents=["Backend"])) == "Backend"


# ── route_from_pm ───────────────────────────────────────────────────
def test_pm_no_task_to_pmo():
    assert ag.route_from_pm(S(current_sprint_task_id="")) == "Master_PMO"

def test_pm_needs_revision_to_techlead():
    assert ag.route_from_pm(S(current_sprint_task_id="T1", needs_revision=True)) == "Tech_Lead"

def test_pm_default_to_reviewer():
    assert ag.route_from_pm(S(current_sprint_task_id="T1", needs_revision=False)) == "Reviewer"


# ── route_from_reviewer (의사결정 분기 + hop 차단기) ─────────────────
def test_reviewer_escalate_to_pm():
    assert ag.route_from_reviewer(S(reviewer_decision="ESCALATE_PM")) == "Master_PM"

def test_reviewer_rework_to_techlead():
    assert ag.route_from_reviewer(S(reviewer_decision="REWORK_DEV")) == "Tech_Lead"

def test_reviewer_pass_no_qa_to_manual():
    assert ag.route_from_reviewer(S(reviewer_decision="PASS", current_required_agents=["Frontend"])) == "ManualWriter"

def test_reviewer_pass_qa_assigned_to_qa():
    assert ag.route_from_reviewer(S(reviewer_decision="PASS", current_required_agents=["QA"])) == "QA"

def test_reviewer_hop_cap_breaks_loop():
    s = S(reviewer_decision="REWORK_DEV", supervisor_hops=config.GLOBAL_MAX_SUPERVISOR_HOPS)
    assert ag.route_from_reviewer(s) == END

def test_reviewer_under_hop_cap_still_loops():
    assert ag.route_from_reviewer(S(reviewer_decision="REWORK_DEV", supervisor_hops=1)) == "Tech_Lead"

def test_reviewer_hop_cap_does_not_block_pass():
    # 상한 도달이어도 PASS(완료)는 막지 않는다 — 완료 신호 보호
    s = S(reviewer_decision="PASS", supervisor_hops=config.GLOBAL_MAX_SUPERVISOR_HOPS, current_required_agents=["Frontend"])
    assert ag.route_from_reviewer(s) == "ManualWriter"


# ── map_builder_router ──────────────────────────────────────────────
def test_builder_success_to_reviewer():
    assert ag.map_builder_router(S(build_status="success")) == "Reviewer"

def test_builder_fail_retry_back_to_backend():
    s = S(build_status="failed", developer_retry_count=1, failed_node="Backend", current_required_agents=["Backend"])
    assert ag.map_builder_router(s) == "Backend"

def test_builder_fail_max_retry_to_end():
    s = S(build_status="failed", developer_retry_count=3, failed_node="Backend", current_required_agents=["Backend"])
    assert ag.map_builder_router(s) == END


# ── 헬퍼: _is_final_task / _get_required_agents (WBS 파일 I/O) ───────
def test_is_final_task_all_done(tmp_path):
    wbs = {"tasks": [{"task_id": "T1", "status": "DONE"}, {"task_id": "T2", "status": "DONE"}]}
    (tmp_path / "00_wbs_master_plan.json").write_text(json.dumps(wbs), encoding="utf-8")
    assert ag._is_final_task(S(workspace_root=str(tmp_path))) is True

def test_is_final_task_not_all_done(tmp_path):
    wbs = {"tasks": [{"task_id": "T1", "status": "DONE"}, {"task_id": "T2", "status": "PENDING"}]}
    (tmp_path / "00_wbs_master_plan.json").write_text(json.dumps(wbs), encoding="utf-8")
    assert ag._is_final_task(S(workspace_root=str(tmp_path))) is False

def test_get_required_agents_from_wbs(tmp_path):
    wbs = {"tasks": [{"task_id": "T1", "required_agents": ["Architect", "Backend"]}]}
    (tmp_path / "00_wbs_master_plan.json").write_text(json.dumps(wbs), encoding="utf-8")
    s = S(workspace_root=str(tmp_path), current_sprint_task_id="T1")
    assert ag._get_required_agents(s) == ["Architect", "Backend"]

def test_get_required_agents_hardcoded_fallback():
    # WBS 없음 + current_required_agents 비어있음 → 전 직군 강제 투입 폴백
    s = S(workspace_root="/no/such/dir", current_required_agents=[], current_sprint_task_id="X")
    assert set(ag._get_required_agents(s)) >= {"Architect", "Backend", "Frontend", "QA"}
