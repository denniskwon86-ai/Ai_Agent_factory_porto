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
    # 기획 신규 가동은 요구 확인 인터뷰(선택형 질문 게이트)부터 시작
    assert ag.route_factory_mode(S(factory_mode="PLANNING")) == "Requirement_Interviewer"

def test_factory_mode_revision_to_techlead():
    assert ag.route_factory_mode(S(factory_mode="REVISION")) == "Tech_Lead"

def test_factory_mode_replan_to_pmo():
    # WBS 재분할(REPLAN_*): 기획 산출물 재사용, Master_PMO 만 재실행
    assert ag.route_factory_mode(S(current_sprint_task_id="REPLAN_123")) == "Master_PMO"

def test_factory_mode_execution_first_is_architect():
    assert ag.route_factory_mode(S(current_required_agents=["Architect", "Backend"])) == "Architect"

def test_factory_mode_execution_skips_design_to_backend():
    assert ag.route_factory_mode(S(current_required_agents=["Backend"])) == "Backend"


# ── route_from_interviewer (요구 확인 인터뷰 → RFP) ──────────────────
def test_interviewer_always_proceeds_to_rfp():
    # 답변 유무와 무관하게 RFP 로 진행(답변은 human_feedback_queue 로 RFP 가 소비)
    assert ag.route_from_interviewer(S()) == "RFP_Analyst"
    assert ag.route_from_interviewer(S(needs_revision=True)) == "RFP_Analyst"


# ── route_from_pm ───────────────────────────────────────────────────
def test_pm_no_task_to_uidesigner():
    # 기획 흐름: PM(PRD) 직후에는 UIDesigner 로 진행 (UI→VisionQA→Architect→PMO 순)
    assert ag.route_from_pm(S(current_sprint_task_id="")) == "UIDesigner"

def test_pm_needs_revision_to_techlead():
    assert ag.route_from_pm(S(current_sprint_task_id="T1", needs_revision=True)) == "Tech_Lead"

def test_pm_default_to_reviewer():
    assert ag.route_from_pm(S(current_sprint_task_id="T1", needs_revision=False)) == "Reviewer"


# ── route_from_vision_qa (UI 승인 → Architect) ───────────────────────
def test_vision_qa_pass_to_architect():
    # UI 확정 후 아키텍처 설계가 WBS 분할(PMO)보다 선행한다
    assert ag.route_from_vision_qa(S(reviewer_decision="NONE")) == "Architect"

def test_vision_qa_rework_is_advisory_not_blocking():
    # [자문 강등] VisionQA 가 REWORK_DEV 소견을 내도 더 이상 UIDesigner 로 자동 반려하지 않고
    # 다음 단계(Architect)로 진행한다(왕복 루프 제거 — 무료 티어 콜 폭발 방지). 판단은 사람 HOTL.
    assert ag.route_from_vision_qa(S(reviewer_decision="REWORK_DEV")) == "Architect"

def test_vision_qa_user_feedback_back_to_designer():
    # 사람(HOTL)이 미리보기 보고 재설계를 요청한 경우에만 UIDesigner 로 되돌린다
    assert ag.route_from_vision_qa(S(reviewer_decision="NONE", needs_revision=True)) == "UIDesigner"


# ── route_from_architect (기획: →PMO / 실행 폴백: →Tech_Lead 등) ─────
def test_architect_planning_flow_to_pmo():
    # WBS 파일이 아직 없으면 기획 흐름 → Master_PMO 로 WBS 분할 지시
    s = S(workspace_root="/no/such/dir", current_sprint_task_id="PLANNING_123")
    assert ag.route_from_architect(s) == "Master_PMO"

def test_architect_execution_fallback_to_techlead(tmp_path):
    # WBS 가 존재하는 실행 태스크(레거시 폴백)에서는 기존처럼 다음 배정 에이전트로
    wbs = {"tasks": [{"task_id": "T1", "required_agents": ["Tech_Lead", "Backend"]}]}
    (tmp_path / "00_wbs_master_plan.json").write_text(json.dumps(wbs), encoding="utf-8")
    s = S(workspace_root=str(tmp_path), current_sprint_task_id="T1")
    assert ag.route_from_architect(s) == "Tech_Lead"

def test_factory_mode_execution_arch_reuse_skips_architect():
    # 기획 단계에서 아키텍처가 이미 확정됐으면(architecture_summary 존재) Architect 재진입 생략
    s = S(current_required_agents=["Architect", "Tech_Lead", "Backend"], architecture_summary="# 확정 설계")
    assert ag.route_factory_mode(s) == "Tech_Lead"


# ── route_from_pmo (WBS 게이트 피드백 루프) ──────────────────────────
def test_pmo_feedback_loops_back_to_resplit():
    assert ag.route_from_pmo(S(needs_revision=True)) == "Master_PMO"

def test_pmo_approve_goes_to_wbs_approved():
    # 승인 시 END 직행이 아니라 실제 종결 노드로 가야 interrupt_after 가 멈춤(WBS 게이트 작동)
    assert ag.route_from_pmo(S(needs_revision=False)) == "WBS_Approved"


# ── route_from_rfp (RFP 게이트 피드백 루프) ──────────────────────────
def test_rfp_feedback_loops_back_to_rewrite():
    assert ag.route_from_rfp(S(needs_revision=True)) == "RFP_Analyst"

def test_rfp_approve_proceeds_to_pm():
    assert ag.route_from_rfp(S(needs_revision=False)) == "Master_PM"


# ── route_from_qa (QA 통합검수 → Supervisor 수용검수 / 미달→Tech_Lead) ──
# (현행화) _is_final_task 는 명시적 역할 배정으로 대체·삭제됨(커밋 0467c7d42) —
# QA 통과 후 Supervisor 진행 여부는 '최종 태스크 판정'이 아니라 WBS 배정 명단에 따른다.
def test_qa_pass_with_supervisor_assigned_goes_to_supervisor():
    s = S(qa_verdict="PASS", current_required_agents=["QA", "Supervisor"])
    assert ag.route_from_qa(s) == "Supervisor"

def test_qa_fail_reworks_to_techlead():
    # FAIL 은 배정 명단과 무관하게 즉시 Tech_Lead 재작업
    assert ag.route_from_qa(S(qa_verdict="FAIL")) == "Tech_Lead"

def test_qa_pass_without_supervisor_ends():
    s = S(qa_verdict="PASS", current_required_agents=["QA"])
    assert ag.route_from_qa(s) == END


# ── route_from_supervisor (고객 수용검수: 수용→매뉴얼 / 반려→PM / 상한→종료) ──
def test_supervisor_accept_writes_manual():
    assert ag.route_from_supervisor(S(supervisor_verdict="PASS")) == "ManualWriter"

def test_supervisor_reject_escalates_to_pm():
    assert ag.route_from_supervisor(S(supervisor_verdict="REJECT", stage_attempt_counts={"SUPERVISOR": 1})) == "Master_PM"

def test_supervisor_reject_cap_ends():
    assert ag.route_from_supervisor(S(supervisor_verdict="REJECT", stage_attempt_counts={"SUPERVISOR": 2})) == END


# ── route_from_reviewer (의사결정 분기 + hop 차단기) ─────────────────
def test_reviewer_escalate_to_pm():
    assert ag.route_from_reviewer(S(reviewer_decision="ESCALATE_PM")) == "Master_PM"

def test_reviewer_rework_to_techlead():
    assert ag.route_from_reviewer(S(reviewer_decision="REWORK_DEV")) == "Tech_Lead"

def test_reviewer_pass_nonfinal_ends_no_manual():
    # 비최종 태스크 PASS → END (매뉴얼은 최종 QA 직후에만 1회)
    assert ag.route_from_reviewer(S(reviewer_decision="PASS", current_required_agents=["Frontend"])) == END

def test_reviewer_pass_qa_assigned_to_qa():
    assert ag.route_from_reviewer(S(reviewer_decision="PASS", current_required_agents=["QA"])) == "QA"

def test_reviewer_hop_cap_breaks_loop():
    # [2026-07-27 계약 변경] 상한 도달은 조용한 END 가 아니라 **종결 처리**로 간다.
    #   예전엔 END 였고, 오케스트레이터가 그 END 를 DONE 으로 마킹해 '가짜 통과'가 됐다.
    s = S(reviewer_decision="REWORK_DEV", supervisor_hops=config.GLOBAL_MAX_SUPERVISOR_HOPS)
    assert ag.route_from_reviewer(s) == "TerminalHandler"

def test_terminal_status_short_circuits_reviewer():
    # 종료 상태가 이미 부여됐으면 판정 내용과 무관하게 종결 처리로 간다.
    s = S(reviewer_decision="PASS", terminal_status="SUSPENDED_PROVIDER")
    assert ag.route_from_reviewer(s) == "TerminalHandler"

def test_terminal_status_short_circuits_developer_routes():
    # 공급자 실패는 코드 결함이 아니므로 개발자 재작업 루프로 되돌리지 않는다.
    s = S(terminal_status="SUSPENDED_PROVIDER", current_required_agents=["Frontend"])
    assert ag.route_from_backend(s) == "TerminalHandler"
    assert ag.route_from_frontend(s) == "TerminalHandler"
    assert ag.map_builder_router(s) == "TerminalHandler"

def test_completed_terminal_status_does_not_short_circuit():
    # COMPLETED 는 정상 흐름이므로 가로채지 않는다.
    s = S(terminal_status="COMPLETED", build_status="success")
    assert ag.map_builder_router(s) == "Reviewer"

def test_reviewer_under_hop_cap_still_loops():
    assert ag.route_from_reviewer(S(reviewer_decision="REWORK_DEV", supervisor_hops=1)) == "Tech_Lead"

def test_reviewer_hop_cap_does_not_block_pass():
    # 상한 도달이어도 PASS(완료)는 막지 않는다 — 비최종이면 END 로 정상 종료
    s = S(reviewer_decision="PASS", supervisor_hops=config.GLOBAL_MAX_SUPERVISOR_HOPS, current_required_agents=["Frontend"])
    assert ag.route_from_reviewer(s) == END


# ── map_builder_router ──────────────────────────────────────────────
def test_builder_success_to_reviewer():
    assert ag.map_builder_router(S(build_status="success")) == "Reviewer"

def test_builder_fail_retry_back_to_backend():
    s = S(build_status="failed", developer_retry_count=1, failed_node="Backend", current_required_agents=["Backend"])
    assert ag.map_builder_router(s) == "Backend"

def test_builder_fail_max_retry_to_terminal_handler():
    # [2026-07-27 계약 변경] 자가복구 소진은 END 가 아니라 종결 노드로 간다.
    #   예전 END 경로 때문에 (a) CodeBuilder 의 롤백 분기가 도달 불가였고
    #   (b) 오케스트레이터가 DONE 으로 마킹했다.
    s = S(build_status="failed", developer_retry_count=3, failed_node="Backend", current_required_agents=["Backend"])
    assert ag.map_builder_router(s) == "TerminalHandler"


# ── 헬퍼: _get_required_agents (WBS 파일 I/O) ────────────────────────
# (현행화) test_is_final_task_* 2건은 대상 함수 _is_final_task 가 명시적 역할 배정으로
# 대체·삭제(커밋 0467c7d42)되어 함께 제거 — 해당 의도는 위 route_from_qa 역할 기반 테스트가 커버.
def test_get_required_agents_from_wbs(tmp_path):
    wbs = {"tasks": [{"task_id": "T1", "required_agents": ["Architect", "Backend"]}]}
    (tmp_path / "00_wbs_master_plan.json").write_text(json.dumps(wbs), encoding="utf-8")
    s = S(workspace_root=str(tmp_path), current_sprint_task_id="T1")
    assert ag._get_required_agents(s) == ["Architect", "Backend"]

def test_get_required_agents_hardcoded_fallback():
    # WBS 없음 + current_required_agents 비어있음 → 전 직군 강제 투입 폴백
    s = S(workspace_root="/no/such/dir", current_required_agents=[], current_sprint_task_id="X")
    assert set(ag._get_required_agents(s)) >= {"Architect", "Backend", "Frontend", "QA"}
