import os
import json
import asyncio
import config
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state_models import ProjectState

from nodes.planning import run_rfp_analyst, run_master_pm, run_master_pmo
from nodes.execution import (
    run_architect,
    run_tech_lead,
    run_developer_fe,
    run_developer_be,
    run_code_builder,
    run_terminal_handler,
    run_reviewer,
    run_qa,
    run_supervisor,
    run_manual_writer
)

# 요구 에이전트 명단 정규화: 별칭(영문 키워드/한글) → 정규 노드 id.
# PMO 는 정규 영문 id(Architect/Tech_Lead/Backend/Frontend/Reviewer/QA)를 내도록 지시받지만,
# 간헐적 비정형 출력에 대비해 정규화 후 '정확 id 일치'로 라우팅한다(substring 오탐 제거).
_AGENT_ALIASES = {
    "Architect": ("architect", "아키"),
    "Tech_Lead": ("tech_lead", "techlead", "tech lead", "테크", "기술"),
    "Backend": ("backend", "백엔드"),
    "Frontend": ("frontend", "프론트"),
    "QA": ("qa", "품질", "테스트"),
    "Reviewer": ("reviewer", "리뷰", "검수"),
    "RFP_Analyst": ("rfp_analyst", "rfp", "요구"),
    "Master_PM": ("master_pm", "기획"),
    "Master_PMO": ("master_pmo", "pmo", "wbs"),
    "CodeBuilder": ("codebuilder", "code_builder", "빌더"),
    "ManualWriter": ("manualwriter", "manual_writer", "manual", "매뉴얼"),
}
_CANON_IDS = set(_AGENT_ALIASES.keys())


def _canonicalize(raw: str) -> str:
    """단일 요구 에이전트 문자열 → 정규 노드 id. 정규 id 면 그대로, 별칭이면 매핑, 미상이면 원문 유지(보수)."""
    if not raw:
        return raw
    s = str(raw).strip()
    if s in _CANON_IDS:  # 이미 정규 id (PMO 정상 출력) → 별칭 검사 생략(오탐 방지)
        return s
    low = s.lower()
    for cid, aliases in _AGENT_ALIASES.items():
        if low == cid.lower() or any(al in low for al in aliases):
            return cid
    return s


def _normalize_agents(raw_list) -> list:
    seen, out = set(), []
    for r in (raw_list or []):
        c = _canonicalize(r)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _get_required_agents(state: ProjectState) -> list:
    agents = []
    try:
        wbs_path = os.path.join(state.workspace_root, "00_wbs_master_plan.json")
        if os.path.exists(wbs_path):
            with open(wbs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for t in data.get("tasks", []):
                    if t.get("task_id") == state.current_sprint_task_id:
                        agents = t.get("required_agents", [])
                        break
    except Exception:
        pass

    #  [치명적 버그 수정] 피드백(Revision) 생성 시 WBS 투입 명단이 비어버리는 현상 완벽 방어
    # agents가 비어있으면 AI가 코딩을 건너뛰는 사태를 막기 위해 강제로 개발 요원을 투입합니다.
    if not agents or len(agents) == 0:
        agents = getattr(state, "current_required_agents", [])

    if not agents or len(agents) == 0:
        agents = ["Architect", "Tech_Lead", "Backend", "Frontend", "QA"]

    # 정규 id 로 정규화 → 라우터의 정확 일치(_has_role) 입력
    return _normalize_agents(agents)


def _has_role(agents: list, role_en: str, role_ko: str = "") -> bool:
    # agents 는 _normalize_agents 로 정규화된 정규 id 목록 → 정확 일치(substring 오탐 제거).
    # role_en 은 항상 정규 id(Architect/Tech_Lead/Backend/Frontend/QA 등). role_ko 는 하위호환용 미사용.
    return role_en in (agents or [])

# (_is_final_task 함수가 명시적 역할 배정 로직으로 대체되어 삭제되었습니다)

def _route_to_first_assigned(agents: list, include_design: bool = True, include_architect: bool = True) -> str:
    """배정된 에이전트 명단에서 파이프라인 순서상 첫 실행 대상 노드를 고른다."""
    if include_design:
        if include_architect and _has_role(agents, "Architect", "아키"): return "Architect"
        if _has_role(agents, "Tech_Lead", "테크") or _has_role(agents, "Tech_Lead", "기술"): return "Tech_Lead"
    if _has_role(agents, "Backend", "백엔드"): return "Backend"
    if _has_role(agents, "Frontend", "프론트"): return "Frontend"
    return "CodeBuilder"

def _wbs_file_exists(state: ProjectState) -> bool:
    """WBS 마스터플랜 파일 존재 여부 — 기획 파이프라인(PMO 이전)과 실행 태스크를 구분하는 신호.
    기획 재가동 시 옛 산출물은 .archive 로 이동되므로, 기획 흐름에서는 항상 False 다."""
    try:
        return os.path.exists(os.path.join(state.workspace_root, "00_wbs_master_plan.json"))
    except Exception:
        return False

def route_factory_mode(state: ProjectState) -> str:
    # WBS 재분할(REPLAN_*): 기획 산출물(RFP/PRD/UI/아키텍처)을 그대로 재사용해 Master_PMO 만 재실행.
    # WBS 분할이 실패/부실했을 때 기획 전체를 다시 돌리지 않고 복구하는 경로.
    if (state.current_sprint_task_id or "").startswith("REPLAN"): return "Master_PMO"
    # PLANNING 신규 가동: 요구 확인 인터뷰(선택형 질문 게이트)부터 시작 → 답변이 RFP/PRD 입력이 된다
    if state.factory_mode == "PLANNING": return "Requirement_Interviewer"
    elif state.factory_mode == "REVISION": return "Tech_Lead"
    # EXECUTION: 태스크에 배정된 에이전트 기준으로 진입 (설계 재사용 - 미배정 시 Architect/Tech_Lead 생략)
    # 아키텍처는 기획 단계(UI 승인 직후)에서 1회 확정되므로, 산출물이 이미 있으면 Architect 재진입을
    # 생략한다(설계 재사용). 기획 단계 아키텍처가 없는 레거시 프로젝트만 폴백으로 Architect 를 실행.
    has_arch = bool((getattr(state, "architecture_summary", "") or "").strip())
    return _route_to_first_assigned(_get_required_agents(state), include_design=True, include_architect=not has_arch)

def route_from_architect(state: ProjectState) -> str:
    # 기획 파이프라인(UI 승인 → Architect → WBS): WBS 가 아직 없으면 기획 흐름이므로 PMO 로 진행.
    # factory_mode 는 UIDesigner 가 이미 EXECUTION 으로 바꿔놓아 신뢰할 수 없다 → 태스크 id/WBS 파일로 판별.
    tid = getattr(state, "current_sprint_task_id", "") or ""
    if (tid.startswith("PLANNING") and len(tid.split("_")) == 2) or not _wbs_file_exists(state):
        print("️ [기획 설계 완료] 아키텍처 확정 - Master PMO 에게 WBS 분할을 지시합니다.")
        return "Master_PMO"
    # 실행(폴백) 경로: Architect 완료 후, 배정된 다음 에이전트로 (Tech_Lead 미배정 시 생략)
    return _route_to_first_assigned(_get_required_agents(state), include_design=False) \
        if not _has_role(_get_required_agents(state), "Tech_Lead", "테크") \
        else "Tech_Lead"

def route_from_tech_lead(state: ProjectState) -> str:
    agents = _get_required_agents(state)
    if _has_role(agents, "Backend", "백엔드"): return "Backend"
    if _has_role(agents, "Frontend", "프론트"): return "Frontend"
    return "CodeBuilder"

def _terminated(state: ProjectState) -> bool:
    """이미 업무 종료 상태가 부여됐는가.

    ⚠️ [2026-07-27] 공급자 타임아웃·출력 계약 실패는 '코드 결함'이 아니므로 개발자 재작업
      루프로 되돌리면 안 된다(그 예산은 코드를 고치라고 준 것이다). 종료 상태가 찍힌 순간
      더 이상 노드를 돌리지 않고 BuildRecoveryExhausted 종결 노드로 보낸다."""
    t = (getattr(state, "terminal_status", "") or "").strip()
    return bool(t) and t != "COMPLETED"

def route_from_backend(state: ProjectState) -> str:
    if _terminated(state):
        return "TerminalHandler"
    agents = _get_required_agents(state)
    if _has_role(agents, "Frontend", "프론트"): return "Frontend"
    return "CodeBuilder"

def route_from_frontend(state: ProjectState) -> str:
    """Frontend 도 공급자/계약 실패로 종료 상태를 낼 수 있으므로 무조건 CodeBuilder 로 보내면 안 된다."""
    if _terminated(state):
        return "TerminalHandler"
    return "CodeBuilder"

def map_builder_router(state: ProjectState) -> str:
    if _terminated(state):
        return "TerminalHandler"
    if state.build_status == "failed":
        if state.developer_retry_count < 3:
            failed_target = state.failed_node
            allowed_agents = _get_required_agents(state)
            
            if failed_target == "Backend" and _has_role(allowed_agents, "Backend", "백엔드"):
                print(" [Circuit Breaker] 빌드 실패. Backend 담당자에게 수정을 지시합니다.")
                return "Backend"
            elif failed_target == "Frontend" and _has_role(allowed_agents, "Frontend", "프론트"):
                print(" [Circuit Breaker] 빌드 실패. Frontend 담당자에게 수정을 지시합니다.")
                return "Frontend"
            else:
                return "Reviewer"
        else:
            # ★ [2026-07-27] 예전엔 END 였다. 그래서 (a) CodeBuilder 의 롤백 분기가 영영
            #   도달하지 못했고(retry>=3 으로 진입할 일이 없다), (b) 오케스트레이터가 이 END 를
            #   DONE 으로 마킹했다. 종결 노드로 보내 롤백·실패 번들·종료 상태를 남긴다.
            print(" [Circuit Breaker] 최대 재시도 초과. 종결 처리(롤백·실패 번들)로 보냅니다.")
            return "TerminalHandler"
    return "Reviewer"

def route_from_reviewer(state: ProjectState) -> str:
    if _terminated(state):
        return "TerminalHandler"
    decision = getattr(state, "reviewer_decision", "PASS")

    #  무한루프 차단: 리뷰 의사결정 왕복(ESCALATE_PM/REWORK_DEV)이 전역 상한 도달 시 강제 종료
    hops = getattr(state, "supervisor_hops", 0)
    if decision in ("ESCALATE_PM", "REWORK_DEV") and hops >= config.GLOBAL_MAX_SUPERVISOR_HOPS:
        # ★ [2026-07-27] 예전엔 그냥 END 였다 — 그러면 오케스트레이터가 DONE 으로 마킹했다.
        #   종결 노드로 보내 실패 번들·롤백·종료 상태를 남긴다.
        print(f" [Supervisor Circuit Breaker] 리뷰 의사결정 왕복 {hops}회 도달"
              f"(상한 {config.GLOBAL_MAX_SUPERVISOR_HOPS}) - 무한 루프 차단, 종결 처리로 보냅니다.")
        return "TerminalHandler"

    if decision == "ESCALATE_PM":
        print(" [PM 상신 루프] 기획적 모순 발견. PM에게 최종 판단을 받으러 갑니다.")
        return "Master_PM"
    elif decision == "REWORK_DEV":
        print(" [실무 재작업 루프] 코드/설계 결함 발견. Tech Lead에게 재설계 및 코딩 재작업을 지시합니다.")
        return "Tech_Lead"
        
    agents = _get_required_agents(state)
    # QA 역할이 명시적으로 배정된 경우 진입
    if _has_role(agents, "QA", "QA") or _has_role(agents, "QA", "테스트"):
        return "QA"
    # QA는 없지만 Supervisor 역할이 명시적으로 배정된 경우 진입
    if _has_role(agents, "Supervisor", "고객수용") or _has_role(agents, "Supervisor", "Supervisor"):
        return "Supervisor"
    
    # 명시적 검수 역할이 없으면 스프린트 종료(END)
    print("[OK] [태스크 완료] 추가 검수 역할이 배정되지 않았습니다 - 스프린트 종료.")
    return END

def route_from_pm(state: ProjectState) -> str:
    # 기획(PLANNING) 단계 신규 가동이거나 task_id가 비어있으면 UIDesigner로 진행
    if not state.current_sprint_task_id or state.factory_mode == "PLANNING":
        # PRD 게이트에서 사용자가 피드백을 줬으면 PM 자기루프로 PRD 재작성
        # (피드백이 UIDesigner/PMO 로 새어 엉뚱한 단계의 지시로 오염되는 것 방지)
        if getattr(state, "needs_revision", False):
            print(" [PRD 재작성] 사용자 피드백 반영 - Master_PM 으로 되돌려 기획서를 다시 작성합니다.")
            return "Master_PM"
        return "UIDesigner"
    
    if getattr(state, "needs_revision", False):
        print("⏩ [의사결정 완료] PM이 기획서를 수정했습니다. Tech Lead에게 변경된 설계 반영을 지시합니다.")
        return "Tech_Lead" 
        
    print("⏩ [의사결정 완료] PM이 강행을 지시했습니다. Reviewer에게 강제 승인을 지시합니다.")
    return "Reviewer"

def route_from_ui_designer(state: ProjectState) -> str:
    # UIDesigner 직후에는 무조건 VisionQA로 넘겨 시각적 검수를 1차로 받습니다.
    return "VisionQA"

def route_from_vision_qa(state: ProjectState) -> str:
    # [자문 강등] VisionQA 는 더 이상 자동 반려(REWORK_DEV → UIDesigner 왕복)하지 않는다.
    #   소견(ui_review_advisory)만 남기고, UI 승인/재설계 판단은 사람(HOTL 미리보기)이 한다.
    #   → 텍스트 추정 판정의 부정확성 + 무료 티어 콜 폭발(왕복)의 주범을 동시 제거.
    #   방어적으로 남아 있을 수 있는 REWORK_DEV 는 무시하고 다음 단계로 진행한다.

    # 사용자(HOTL)가 미리보기를 보고 재설계를 요청한 경우에만 UIDesigner 로 되돌린다.
    if getattr(state, "needs_revision", False):
        print(" [사용자 UI 재설계 요청] 피드백 반영 - UIDesigner 로 되돌려 다시 디자인합니다.")
        return "UIDesigner"

    # UI 확정 후 아키텍처 설계 → WBS 분할 순서(설계가 WBS 의 입력이 되도록 기획 단계에서 확정)
    return "Architect"

def route_from_pmo(state: ProjectState) -> str:
    """WBS(PMO) 게이트 직후 분기: 사용자가 피드백을 줬으면(needs_revision) WBS 재분할을 위해
    Master_PMO 로 되돌리고, 승인(피드백 없음)이면 종결 노드(WBS_Approved)로 진행.
    ⚠️ 승인 경로를 END 로 직접 두면 interrupt_after 가 '멈출 다음 노드'가 없어 HOTL 일시정지가
    생기지 않는다(=WBS 승인 게이트가 작동 안 함). 실제 노드(WBS_Approved)로 보내야 게이트가 멈추고,
    재개 시 needs_revision 으로 재평가되어 재분할/종료가 갈린다(RFP 게이트와 동일 패턴)."""
    if getattr(state, "needs_revision", False):
        print(" [WBS 재분할] 사용자 피드백 반영 - Master_PMO 로 되돌려 WBS 를 다시 분할합니다.")
        return "Master_PMO"
    return "WBS_Approved"


def run_wbs_approved(state: ProjectState) -> dict:
    """WBS 승인 종결 노드(no-op) - WBS 게이트가 실제로 멈출 수 있도록 두는 '다음 노드'.
    승인되면 여기로 진행한 뒤 END 로 종료(기획 완료). 상태는 변경하지 않는다."""
    print("[OK] [WBS 승인] 사용자가 WBS 를 승인했습니다 - 기획 단계를 종료합니다.")
    return {}

def route_from_interviewer(state: ProjectState) -> str:
    """요구 확인 인터뷰 직후(게이트 재개 시): 사용자의 선택 답변은 human_feedback_queue 에 실려
    RFP_Analyst 가 소비·영속화한다. 질문이 없었거나 무피드백 승인이어도 그대로 RFP 진행."""
    return "RFP_Analyst"

def route_from_rfp(state: ProjectState) -> str:
    """RFP HOTL 게이트 직후 분기: 사용자 피드백(needs_revision)이면 RFP 재작성을 위해
    RFP_Analyst 로 되돌리고(자기루프), 승인(피드백 없음)이면 다음 단계(Master_PM)로 진행.
    interrupt_after=RFP_Analyst 라 매 라운드 인간 게이트가 강제되므로 자동 무한루프 없음."""
    if getattr(state, "needs_revision", False):
        print(" [RFP 재작성] 사용자 피드백 반영 - RFP_Analyst 로 되돌려 요구정의서를 다시 작성합니다.")
        return "RFP_Analyst"
    return "Master_PM"

def route_from_qa(state: ProjectState) -> str:
    """QA(수행사 통합검수) 직후 분기: 합격이면 고객사 수용검수(Supervisor)로, 미달이면 Tech_Lead 재작업.
    (비최종 태스크의 전용 QA는 드물게 실행되며 통과 시 그대로 스프린트 종료.)"""
    if getattr(state, "qa_verdict", "") == "FAIL":
        print(" [QA 미달] 설계·통합 결함 - Tech_Lead 에게 재작업 지시.")
        return "Tech_Lead"
        
    agents = _get_required_agents(state)
    if _has_role(agents, "Supervisor", "고객수용") or _has_role(agents, "Supervisor", "Supervisor"):
        print("➡️ [QA 통과] WBS 명단에 따라 고객사 수용검수(Supervisor)로 진행.")
        return "Supervisor"
        
    print("[OK] [QA 통과] Supervisor 역할이 배정되지 않았으므로 스프린트 종료.")
    return END

def route_from_supervisor(state: ProjectState) -> str:
    """고객사 수용검수(Supervisor) 직후 분기: 수용(PASS)→매뉴얼, 반려(REJECT)→PM 재조정.
    수용 시도 2회 초과(반복 반려) 시 무한 루프 대신 종료(인간 검토)로 표면화 - 보수적."""
    if getattr(state, "supervisor_verdict", "") == "PASS":
        return "ManualWriter"
    attempts = (getattr(state, "stage_attempt_counts", {}) or {}).get("SUPERVISOR", 0)
    if attempts >= 2:
        print("⚠️ [수용검수 상한] 반복 반려 - 무한 루프 방지 위해 종료(인간 검토 필요).")
        return END
    print(" [고객 수용 미달] PM 에게 요구·기능 재조정 상신.")
    return "Master_PM"

# 레지스트리 id → 노드 구현 함수. 레지스트리가 노드 멤버십을 구동하기 위한 seam.
# (모든 레지스트리 에이전트 id 를 커버해야 동적 빌더가 임의 enabled 집합을 생성 가능)
NODE_IMPL = {
    "Requirement_Interviewer": __import__("nodes.clarification", fromlist=["run_requirement_interviewer"]).run_requirement_interviewer,
    "RFP_Analyst": run_rfp_analyst,
    "Master_PM": run_master_pm,
    "UIDesigner": __import__("nodes.ui_designer", fromlist=["run_ui_designer"]).run_ui_designer,
    "Master_PMO": run_master_pmo,
    "Architect": run_architect,
    "Tech_Lead": run_tech_lead,
    "Backend": run_developer_be,
    "Frontend": run_developer_fe,
    "CodeBuilder": run_code_builder,
    "Reviewer": run_reviewer,
    "QA": run_qa,
    "Supervisor": run_supervisor,
    "ManualWriter": run_manual_writer,
    "VisionQA": __import__("nodes.vision_qa", fromlist=["run_vision_qa"]).run_vision_qa,
}


def _wire_edges(workflow):
    """현 SW 파이프라인의 엣지/라우터 구조.
    (b)-1 동작 보존: 하드코딩 유지. (b)-2 에서 레지스트리 order/category 기반 데이터 구동으로 전환 예정.
    (상태 구동 결정 라우터 - include_design·역방향 수렴·QA 자동투입·빌드실패 되돌림 - 은 함수 로직 유지)"""
    workflow.set_conditional_entry_point(
        route_factory_mode,
        {
            "Requirement_Interviewer": "Requirement_Interviewer",
            "RFP_Analyst": "RFP_Analyst", "Master_PM": "Master_PM", "Master_PMO": "Master_PMO",
            "Tech_Lead": "Tech_Lead", "Architect": "Architect",
            "Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"
        }
    )
    # 요구 확인 인터뷰 게이트: 선택형 질문 생성 직후 멈추고(hotl_after), 사용자의 선택 답변과 함께 RFP 로
    workflow.add_conditional_edges("Requirement_Interviewer", route_from_interviewer, {"RFP_Analyst": "RFP_Analyst"})
    # RFP 게이트 피드백 루프: 피드백 시 RFP_Analyst 재실행(요구정의 재작성), 승인 시 Master_PM 진행
    workflow.add_conditional_edges("RFP_Analyst", route_from_rfp, {"RFP_Analyst": "RFP_Analyst", "Master_PM": "Master_PM"})
    workflow.add_conditional_edges("Master_PM", route_from_pm, {"Master_PM": "Master_PM", "UIDesigner": "UIDesigner", "Tech_Lead": "Tech_Lead", "Reviewer": "Reviewer"})
    
    workflow.add_conditional_edges("UIDesigner", route_from_ui_designer, {"VisionQA": "VisionQA"})
    # UI 승인(VisionQA 게이트) → Architect(아키텍처 확정) → Master_PMO(WBS 분할) — 설계가 WBS 의 입력
    workflow.add_conditional_edges("VisionQA", route_from_vision_qa, {"UIDesigner": "UIDesigner", "Architect": "Architect"})
    
    # WBS 게이트: interrupt_after=Master_PMO 가 실제로 멈추도록 승인 경로를 '실제 노드'(WBS_Approved)로
    # 보낸다. 피드백 시 Master_PMO 재실행(WBS 재분할), 승인 시 WBS_Approved→END(기획 종료).
    workflow.add_node("WBS_Approved", run_wbs_approved)
    workflow.add_conditional_edges("Master_PMO", route_from_pmo, {"Master_PMO": "Master_PMO", "WBS_Approved": "WBS_Approved"})
    workflow.add_edge("WBS_Approved", END)

    workflow.add_conditional_edges("Architect", route_from_architect, {"Master_PMO": "Master_PMO", "Tech_Lead": "Tech_Lead", "Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    workflow.add_conditional_edges("Tech_Lead", route_from_tech_lead, {"Backend": "Backend", "Frontend": "Frontend", "CodeBuilder": "CodeBuilder"})
    # ★ [2026-07-27] 업무 종결 노드 — 실패를 '조용한 END' 로 흘리지 않고 롤백·실패 번들·종료 상태를 남긴다.
    workflow.add_node("TerminalHandler", run_terminal_handler)
    workflow.add_edge("TerminalHandler", END)

    workflow.add_conditional_edges("Backend", route_from_backend, {"Frontend": "Frontend", "CodeBuilder": "CodeBuilder", "TerminalHandler": "TerminalHandler"})
    # Frontend 도 생성 실패 시 종료 상태를 낼 수 있으므로 무조건 간선에서 조건부로 승격한다.
    workflow.add_conditional_edges("Frontend", route_from_frontend, {"CodeBuilder": "CodeBuilder", "TerminalHandler": "TerminalHandler"})
    workflow.add_conditional_edges("CodeBuilder", map_builder_router, {"Frontend": "Frontend", "Backend": "Backend", "Reviewer": "Reviewer", "TerminalHandler": "TerminalHandler", END: END})

    workflow.add_conditional_edges("Reviewer", route_from_reviewer, {"QA": "QA", "ManualWriter": "ManualWriter", "Master_PM": "Master_PM", "Tech_Lead": "Tech_Lead", "TerminalHandler": "TerminalHandler", END: END})
    # 3단 수용 사다리: QA(수행사 통합검수) → Supervisor(고객사 수용검수) → ManualWriter
    #   QA: 통과→Supervisor / 미달→Tech_Lead 재작업
    #   Supervisor: 수용→ManualWriter / 반려→PM 재조정(상한 초과 시 종료)
    workflow.add_conditional_edges("QA", route_from_qa, {"Supervisor": "Supervisor", "Tech_Lead": "Tech_Lead", END: END})
    workflow.add_conditional_edges("Supervisor", route_from_supervisor, {"ManualWriter": "ManualWriter", "Master_PM": "Master_PM", END: END})
    workflow.add_edge("ManualWriter", END)


def build_graph_from_registry(registry=None):
    """레지스트리의 enabled 에이전트 id 로 노드를 생성(NODE_IMPL 매핑)하고, 엣지/라우터와
    interrupt_after(hotl_after) 를 적용해 (workflow, interrupt_after) 반환.

    (b)-1 동작 보존: DEFAULT_REGISTRY(전부 enabled)에서는 기존 하드코딩 토폴로지와 동일하다.
    엣지는 아직 _wire_edges 하드코딩이므로, enabled 에서 노드를 빼는 것은 (b)-2 에서 엣지 데이터화와
    함께 지원한다(현재 임의 비활성화는 dangling edge 로 compile 실패할 수 있음)."""
    from core.agent_registry import load_registry
    reg = registry or load_registry()
    # reg.agents 는 _normalize 로 order 정렬됨 - 범용 선형 그래프의 실행 순서로 사용
    enabled = [a for a in reg.get("agents", []) if a.get("enabled", True)]
    enabled_ids = [a["id"] for a in enabled]

    workflow = StateGraph(ProjectState)

    # 토폴로지 분기:
    #  - 순수 SW 템플릿(모든 enabled 노드가 NODE_IMPL 에 구현됨) → 기존 하드코딩 라우팅(동작 보존).
    #  - 커스텀 에이전트가 하나라도 있으면 → 범용 선형 파이프라인(T3): 모든 노드를 범용 실행기로
    #    생성하고 order 순으로 연결. SW 전용 라우터/필드에 의존하지 않는다.
    is_sw_pipeline = bool(enabled_ids) and all(aid in NODE_IMPL for aid in enabled_ids)

    if is_sw_pipeline:
        for aid in enabled_ids:
            impl = NODE_IMPL.get(aid)
            if impl is not None:
                workflow.add_node(aid, impl)
        _wire_edges(workflow)
        # HOTL 중단점 = "전달된 레지스트리" 의 hotl_after(SW 노드로 한정). DEFAULT_REGISTRY 면 기존과 동일.
        interrupt_after = [a["id"] for a in enabled
                           if a.get("hotl_after", False) and a["id"] in NODE_IMPL]
    else:
        # 범용 선형 파이프라인 - 설정만으로 새 에이전트 타입(마케팅/리서치/문서 등) 실행
        from nodes.universal import make_universal_node
        for aid in enabled_ids:
            workflow.add_node(aid, make_universal_node(aid))
            
        if enabled_ids:
            def route_universal(state: ProjectState, current_node_id: str) -> str:
                # 재실행(resimulate) 모드일 경우 시작점을 다르게 라우팅
                if state.factory_mode == "EXECUTION" and reg.get("simulation_framework", False):
                    resim_entry = reg.get("framework_agents", {}).get("resim_entry", "")
                    if resim_entry and current_node_id == "" and resim_entry in enabled_ids:
                        print(f" [Resimulate] 기존 설계 건너뛰기. {resim_entry}부터 재실행합니다.")
                        return resim_entry
                
                # 다음 실행할 노드를 찾습니다.
                try:
                    current_idx = enabled_ids.index(current_node_id) if current_node_id else -1
                except ValueError:
                    current_idx = -1
                
                # domain_agents 필터가 있으면 적용 (프레임워크 에이전트는 무조건 실행)
                domain_agents = getattr(state, "domain_agents", [])
                framework_agents = []
                if reg.get("simulation_framework", False):
                    framework_agents = reg.get("framework_agents", {}).get("preparation", []) + \
                                       reg.get("framework_agents", {}).get("evaluation", [])
                
                for idx in range(current_idx + 1, len(enabled_ids)):
                    next_node = enabled_ids[idx]
                    # 서브 프로젝트의 domain_agents가 지정된 경우 필터링
                    if domain_agents and next_node not in framework_agents and next_node not in domain_agents:
                        continue
                    return next_node
                
                return END

            # 조건부 진입점 설정
            workflow.set_conditional_entry_point(
                lambda s: route_universal(s, ""),
                {aid: aid for aid in enabled_ids}
            )
            
            for a_id in enabled_ids:
                workflow.add_conditional_edges(
                    a_id,
                    lambda s, current_node=a_id: route_universal(s, current_node),
                    {aid: aid for aid in enabled_ids} | {END: END}
                )
            
        # HOTL 중단점 = enabled 노드 중 hotl_after(범용 노드는 모두 add_node 됐으므로 제한 없음)
        interrupt_after = [a["id"] for a in enabled if a.get("hotl_after", False)]

    return workflow, interrupt_after


def _build_workflow(registry=None):
    """토폴로지 빌더 진입점 - 레지스트리 구동(build_graph_from_registry)으로 위임.
    create_factory_graph(studio/테스트)와 get_runtime_app(런타임 영속)이 공유한다.
    registry 미지정 시 default 레지스트리(하위호환)."""
    return build_graph_from_registry(registry)


def create_factory_graph():
    """동기 컴파일(MemorySaver) - LangGraph Studio/langgraph.json 및 단위 테스트용.
    런타임(오케스트레이터)은 재시작 내성을 위해 영속 체크포인터를 쓰는 get_runtime_app()을 사용한다."""
    workflow, interrupt_after = _build_workflow()
    # ★ [2026-07-29] 체크포인트 직렬화 허용목록을 여기서도 적용한다(휘발성이라도 동일 규칙).
    #   두 saver 가 다른 직렬화 규칙을 쓰면 "스튜디오에서는 되는데 런타임에서는 상태가 빈" 식의
    #   재현 불가 차이가 생긴다. 규칙은 `core/checkpoint_serde.py` 한 곳에만 둔다.
    from core.checkpoint_serde import build_serializer
    _serde = build_serializer()
    _mem = MemorySaver(serde=_serde) if _serde else MemorySaver()
    return workflow.compile(checkpointer=_mem, interrupt_after=interrupt_after)


# 스튜디오/langgraph.json/테스트용 동기 인스턴스(휘발성). 런타임은 get_runtime_app() 사용.
app = create_factory_graph()


# ── 런타임 전용 영속 체크포인터 그래프 (재시작 내성) ──────────────────────────────
# AsyncSqliteSaver 는 생성 시 실행 중 이벤트루프가 필요하므로 모듈 import 시점엔 만들 수 없다.
# → 첫 호출(오케스트레이터의 async 컨텍스트) 때 1회 lazy 생성하고 캐시한다.
# T2-b: 템플릿마다 토폴로지가 다를 수 있으므로 컴파일 그래프를 template_id 별로 캐시한다.
#       체크포인터(SQLite saver)는 전 템플릿이 공유한다 - thread_id(project__task)가 상태를
#       격리하고, 한 프로젝트/태스크는 항상 같은 템플릿으로 실행되므로 충돌하지 않는다.
_runtime_saver = None                 # 공유 AsyncSqliteSaver(1회 생성)
_runtime_apps: dict = {}              # template_id -> 컴파일된 그래프
_runtime_lock = asyncio.Lock()


async def _get_runtime_saver():
    global _runtime_saver
    if _runtime_saver is None:
        # ⚠️ 커스텀 상태 타입(state_models.*)을 등록하지 않으면 strict 직렬화에서 **복원 시
        #   그 키가 통째로 사라진다**(예외 없이 조용히). 대기 중이던 HOTL 스프린트가 빈 상태로
        #   재개되는 사고라, 체크포인터를 만들 때 반드시 함께 건다. 근거: core/checkpoint_serde.py
        from core.checkpoint_serde import build_serializer
        _serde = build_serializer()
        postgres_uri = os.environ.get("POSTGRES_URI")
        if postgres_uri:
            try:
                import asyncpg
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                conn = await asyncpg.connect(postgres_uri)
                _runtime_saver = AsyncPostgresSaver(conn, serde=_serde) if _serde else AsyncPostgresSaver(conn)
                await _runtime_saver.setup()
                print(" [Checkpointer] PostgreSQL 분산 DB 어댑터 연결 성공.")
            except ImportError:
                print("⚠️ [Checkpointer] asyncpg 모듈이 없어 PostgreSQL 연동 실패. SQLite로 Fallback합니다.")
                postgres_uri = None
        
        if not postgres_uri:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            conn = await aiosqlite.connect(config.PIPELINE_DB_FILE, check_same_thread=False)
            _runtime_saver = AsyncSqliteSaver(conn, serde=_serde) if _serde else AsyncSqliteSaver(conn)
            await _runtime_saver.setup()
            print("️ [Checkpointer] 기본 SQLite 어댑터 연결 완료.")
            
    return _runtime_saver


async def get_runtime_app(template_id: str = "default"):
    """오케스트레이터용 그래프(영속 체크포인터=SQLite). template_id 별로 1회 compile·캐시.
    → 서버 재시작 시에도 HOTL 대기 체크포인트가 디스크에 보존되어 스프린트 재개가 가능하다.
    → 템플릿마다 enabled/hotl_after 가 다르면 토폴로지·중단점도 그에 맞게 컴파일된다(T2-b)."""
    tid = template_id or "default"
    cached = _runtime_apps.get(tid)
    if cached is not None:
        return cached
    async with _runtime_lock:
        if tid not in _runtime_apps:
            from core.agent_registry import load_template
            saver = await _get_runtime_saver()
            workflow, interrupt_after = _build_workflow(load_template(tid))
            _runtime_apps[tid] = workflow.compile(checkpointer=saver, interrupt_after=interrupt_after)
    return _runtime_apps[tid]