import json
from typing import Dict, Any
from state_models import ProjectState
from core.agent_registry import agent_skill

async def run_ui_designer(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)

    # VisionQA 게이트에서 사용자가 남긴 UI 피드백 소비 - 소비하지 않으면 재설계가 피드백을 모르고,
    # 잔류 피드백이 이후 Master_PMO 의 WBS 재분할 지시로 오염된다
    _fb_items = getattr(state_obj, "human_feedback_queue", []) or []
    _latest = _fb_items[-1] if _fb_items else None
    _latest_fb = (_latest.get("feedback", "") if isinstance(_latest, dict) else getattr(_latest, "feedback", "")) or ""
    _extra = ""
    if _latest_fb.strip():
        _extra = f"\n\n[ 사용자 UI 피드백 - 반드시 반영해 화면을 다시 디자인하십시오]:\n{_latest_fb.strip()}"
        print(f" [UIDesigner] 사용자 피드백 반영해 재디자인: {_latest_fb.strip()[:80]}")
    else:
        print(" [Agent] UIDesigner 가동 중: UI 목업 화면을 디자인합니다...")

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("UIDesigner", "ui_designer_skill", template_id=state_obj.template_id), "UI_DESIGN", extra_instruction=_extra)
    print(f"[OK] [Agent] UIDesigner 작업 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")

    # 디자이너는 Execution 모드로
    updates.setdefault("factory_mode", "EXECUTION")
    updates.setdefault("needs_revision", False)
    if _latest_fb.strip():
        updates["human_feedback_queue"] = []  # 소비한 피드백 비움(후속 단계 재적용 방지)
    return updates
