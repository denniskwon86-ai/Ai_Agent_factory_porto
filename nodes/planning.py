import os
import json
import re
from typing import Dict, Any
from state_models import ProjectState
from core.llm_gateway import gateway
from core.agent_registry import agent_skill
from nodes.utils.wbs_manager import WBSManager

def _load_skill(role_name: str) -> str:
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return f.read()
    return ""

def _extract_code_from_ssot(json_str: str) -> str:
    try:
        data = json.loads(json_str)
        files = data.get("files", [])
        if files and isinstance(files, list): return files[0].get("code", "")
    except Exception: pass
    return ""

async def run_rfp_analyst(state: Any) -> Dict[str, Any]:
    """요구사항 정의서(RFP) 작성 - 기획(PM) 이전에 '무엇을·왜'를 확정하는 기준 계약.
    RFP HOTL 게이트에서 사용자가 피드백을 주면(route_from_rfp 가 여기로 되돌림) 그 피드백을
    재작성 지시로 주입해 RFP 자체를 고친다(다음 단계 PRD 로 새지 않도록)."""
    state_obj = ProjectState.model_validate(state)

    # HOTL 피드백 흡수: 게이트웨이/ContextEngine 은 human_feedback_queue 를 LLM 에 전달하지 않으므로,
    # 최신 피드백을 extra_instruction 으로 직접 합성하는 것이 RFP 재작성에 반영하는 유일한 통로.
    _fb_items = getattr(state_obj, "human_feedback_queue", []) or []
    _latest = _fb_items[-1] if _fb_items else None
    _latest_fb = (_latest.get("feedback", "") if isinstance(_latest, dict) else getattr(_latest, "feedback", "")) or ""

    _clar_qs = getattr(state_obj, "clarification_questions", []) or []
    _clar_sum = (getattr(state_obj, "clarification_summary", "") or "").strip()
    _new_clar_sum = ""
    _extra = ""
    if _clar_qs and not _clar_sum and _latest_fb.strip():
        # 요구 확인 인터뷰(선택형 질문) 답변 최초 소비: RFP 입력으로 주입 + 이후 단계(PRD) 참조용 영속화
        _new_clar_sum = _latest_fb.strip()
        _extra = (f"\n\n[ 사용자 요구 확인(인터뷰) 결과 - 아래 선택/답변을 RFP(요구정의서)에 반드시 반영하십시오]:\n{_new_clar_sum}")
        print(f" [RFP Analyst] 요구 확인 인터뷰 답변 반영해 RFP 작성: {_new_clar_sum[:80]}")
    elif _latest_fb.strip():
        _extra = (f"\n\n[ 사용자 피드백 - RFP(요구정의서)를 이 피드백에 맞게 반드시 수정/반영해 재작성하십시오. "
                  f"다음 단계(기획서)로 미루지 말 것]:\n{_latest_fb.strip()}")
        print(f" [RFP Analyst] 사용자 피드백 반영해 RFP 재작성: {_latest_fb.strip()[:80]}")
    else:
        print(" [Agent] RFP Analyst - 토론·합의 기반 요구사항 정의서(RFP) 작성 중...")

    # 재작성 루프에서도 인터뷰에서 확정한 방향이 유실되지 않도록 항상 참조로 동봉
    if _clar_sum:
        _extra += f"\n\n[참조: 사용자 요구 확인(인터뷰) 결과 - 이 확정 방향과 모순되지 않게 작성하십시오]:\n{_clar_sum}"

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("RFP_Analyst", "rfp_skill", template_id=state_obj.template_id), "RFP", extra_instruction=_extra)
    print(f"[OK] [Agent] RFP 요구정의 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    # 재진입 시 다시 Master_PM 으로 흐르도록 needs_revision 리셋 + 소비한 피드백 큐 비움(다음 단계 재적용 방지)
    updates["needs_revision"] = False
    updates["human_feedback_queue"] = []
    if _new_clar_sum:
        updates["clarification_summary"] = _new_clar_sum
    return updates

async def run_master_pm(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    
    #  [PM 상신 루프] 리뷰어가 기획 모순으로 판단하여 PM을 호출한 경우
    if getattr(state_obj, "reviewer_decision", "") == "ESCALATE_PM":
        print("⚖️ [Agent] Master PM: Reviewer의 기획 모순 에스컬레이션 검토 중...")
        prompt = _load_skill(agent_skill("Master_PM", "pm_skill", template_id=state_obj.template_id))
        prompt += (
            f"\n\n[ Reviewer 결재 상신 내용 (ESCALATE_PM)]:\n{state_obj.reviewer_feedback}\n\n"
            "당신은 프로젝트의 총괄 PM입니다. 코드 리뷰어가 기획서의 논리적 모순이나 위배 사항을 보고했습니다.\n"
            "1. 만약 이 지적사항이 전체 흐름상 무시해도 좋다면 응답을 반환하는 JSON 데이터 내에 `\"decision\": \"REJECT\"`로 적고 `\"reason\": \"사유\"`를 명시하십시오.\n"
            "2. 만약 기획 보완이 필요하다면 `\"decision\": \"ACCEPT\"`로 적고, `\"prd_summary\": \"보완된 PRD 내용\"`을 작성하십시오.\n"
            "응답은 반드시 아래 JSON 포맷을 준수하십시오:\n"
            "\x60\x60\x60json\n"
            "{\n"
            "  \"decision\": \"REJECT\" 또는 \"ACCEPT\",\n"
            "  \"reason\": \"(REJECT일 경우 기각 사유)\",\n"
            "  \"prd_summary\": \"(ACCEPT일 경우 수정된 PRD)\"\n"
            "}\n"
            "\x60\x60\x60"
        )
        output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="json")

        try:
            clean_str = output.strip()
            md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*?\})\s*\x60{3}', clean_str)
            if md_match: clean_str = md_match.group(1)
            else:
                bracket_match = re.search(r'(\{[\s\S]*\})', clean_str)
                if bracket_match: clean_str = bracket_match.group(1)
            data = json.loads(clean_str)
            
            if data.get("decision") == "REJECT":
                print("[OK] [PM Decision] PM이 피드백을 기각(Override)했습니다. 개발팀에 강행을 지시합니다.")
                return {
                    "reviewer_decision": "PASS", # 결재 완료 처리
                    "pm_override_reason": data.get("reason", "PM 판단하에 무시 진행"), 
                    "needs_revision": False
                }
            else:
                print(" [PM Decision] PM이 피드백을 수용(ACCEPT)했습니다. PRD를 업데이트하고 개발팀 재작업(Rework)을 지시합니다.")
                return {
                    "reviewer_decision": "REWORK_DEV", # 개발팀으로 루프 반환
                    "pm_override_reason": "",
                    "needs_revision": True,
                    "prd_summary": data.get("prd_summary", state_obj.prd_summary)
                }
        except Exception as e:
            print(f"⚠️ PM 의사결정 파싱 실패, 강제 승인으로 폴백: {e}")
            return {"reviewer_decision": "PASS", "pm_override_reason": "PM 자동 강행 폴백"}

    else:
        # 요구 확인 인터뷰에서 사용자가 선택으로 확정한 방향을 PRD 에도 직접 주입
        _extra = ""
        _clar_sum = (getattr(state_obj, "clarification_summary", "") or "").strip()
        if _clar_sum:
            _extra = f"\n\n[참조: 사용자 요구 확인(인터뷰) 결과 - 기획서(PRD)에 반드시 반영하십시오]:\n{_clar_sum}"

        # PRD 게이트에서 사용자가 피드백을 준 경우(route_from_pm 자기루프) 재작성 지시로 소비
        _fb_items = getattr(state_obj, "human_feedback_queue", []) or []
        _latest = _fb_items[-1] if _fb_items else None
        _latest_fb = (_latest.get("feedback", "") if isinstance(_latest, dict) else getattr(_latest, "feedback", "")) or ""
        if _latest_fb.strip():
            _extra += (f"\n\n[ 사용자 피드백 - 기획서(PRD)를 이 피드백에 맞게 반드시 수정/반영해 재작성하십시오. "
                       f"다음 단계로 미루지 말 것]:\n{_latest_fb.strip()}")
            print(f" [Master PM] 사용자 피드백 반영해 PRD 재작성: {_latest_fb.strip()[:80]}")
        else:
            print(" [Agent] Master PM 토론·합의 기반 기획(PRD) 진행 중...")

        from nodes.utils.debate import run_supervised_stage
        updates, result = await run_supervised_stage(state_obj, agent_skill("Master_PM", "pm_skill", template_id=state_obj.template_id), "PLANNING", extra_instruction=_extra)
        print(f"[OK] [Agent] Master PM 기획 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
        updates["needs_revision"] = False
        if _latest_fb.strip():
            updates["human_feedback_queue"] = []  # 소비한 피드백 비움(후속 단계 재적용 방지)
        return updates

async def run_master_pmo(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    
    print(" [Agent] Master PMO 비동기 WBS 분할 및 에이전트 스케줄링 진행 중...")
    prompt = _load_skill(agent_skill("Master_PMO", "pmo_skill", template_id=state_obj.template_id))
    prompt += f"\n\n[참조: Master PM이 작성한 PRD]\n{state_obj.prd_summary}"
    # 아키텍처는 기획 단계(UI 승인 직후)에서 이미 확정됨 — WBS 분할의 입력으로 주입
    if (getattr(state_obj, "architecture_summary", "") or "").strip():
        prompt += f"\n\n[참조: Architect가 확정한 시스템 아키텍처 - 태스크 분해 시 모듈 경계와 의존성을 이 설계에 맞추십시오]\n{state_obj.architecture_summary}"
    prompt += (
        "\n\n[ 절대 준수 사항]: PRD를 분석하여 반드시 **최소 4개 이상**의 구체적인 WBS 태스크로 분할하십시오. "
        "각 태스크에는 투입될 에이전트 명단(`required_agents`)을 반드시 포함하십시오. "
        "아키텍처 설계는 기획 단계에서 이미 확정되었으므로 `required_agents`에 `Architect`를 절대 배정하지 마십시오."
    )

    # WBS 게이트에서 사용자가 피드백을 줬으면(재분할 루프) 그 내용을 반영해 다시 분할한다.
    _fb_items = getattr(state_obj, "human_feedback_queue", []) or []
    _latest_fb = (_fb_items[-1].get("feedback", "") if _fb_items and isinstance(_fb_items[-1], dict) else "") or ""
    if _latest_fb.strip():
        prompt += f"\n\n[ 사용자 피드백 - WBS 재분할 시 반드시 반영하십시오]:\n{_latest_fb.strip()}"
        print(f" [Master PMO] 사용자 피드백을 반영해 WBS 를 재분할합니다: {_latest_fb.strip()[:80]}")

    output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="json")
    wbs_code = _extract_code_from_ssot(output) or output

    wbs_tasks = []
    try:
        clean_str = wbs_code.strip()
        md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*?\})\s*\x60{3}', clean_str)
        if md_match: clean_str = md_match.group(1)
        else:
            bracket_match = re.search(r'(\{[\s\S]*\})', clean_str)
            if bracket_match: clean_str = bracket_match.group(1)
        wbs_data = json.loads(clean_str)
        wbs_tasks = wbs_data.get("tasks", [])
    except Exception as e:
        print(f"⚠️ WBS 파싱 실패. 비상 백로그 강제 주입 가동: {e}")
        wbs_tasks = []

    if state_obj.workspace_root:
        wbs_mgr = WBSManager(state_obj.workspace_root)
        wbs_mgr.initialize_wbs(state_obj.project_name, wbs_tasks)
        print(f"[OK] WBS 초기화 완료: 총 {len(wbs_tasks)}개의 태스크가 스케줄링되었습니다.")

    # 첫 번째 실행 가능 태스크의 required_agents를 현재 스프린트 에이전트 명단으로 저장
    first_task_agents = []
    if wbs_tasks:
        first_task_agents = wbs_tasks[0].get("required_agents", [])

    # Supervisor: WBS 분할 기준(deterministic, LLM 0콜) 채점 기록
    from nodes.utils.scoring import score_stage
    pmo_result = await score_stage(state_obj, "PMO")
    scores = dict(getattr(state_obj, "stage_scores", {}) or {})
    scores["PMO"] = pmo_result.get("score", 0.0)
    crit_log = list(getattr(state_obj, "criteria_log", []) or [])
    crit_log.append({
        "stage": "PMO",
        "score": pmo_result.get("score", 0.0),
        "verdict": pmo_result.get("verdict", "PASS"),
        "blocking_fails": pmo_result.get("blocking_fails", []),
    })
    print(f" [Master PMO] WBS 기준 채점 - 점수 {pmo_result.get('score')} / 판정 {pmo_result.get('verdict')}")

    return {
        "factory_mode": "EXECUTION",
        "needs_revision": False,
        "human_feedback_queue": [],  # 소비한 피드백 비움 - 다음 게이트에서 과거 피드백 재적용 방지
        "current_required_agents": first_task_agents,
        "current_stage": "PMO",
        "stage_scores": scores,
        "criteria_log": crit_log,
        "supervisor_feedback": "" if pmo_result.get("verdict") == "PASS" else f"WBS 기준 미달: {pmo_result.get('blocking_fails')}",
    }

async def run_pm(state: Any) -> Dict[str, Any]:
    return await run_master_pm(state)