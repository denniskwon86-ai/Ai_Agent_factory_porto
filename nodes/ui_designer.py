import json
from typing import Dict, Any
from core.state_models import ProjectState
from skills import agent_skill

async def run_ui_designer(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print("🎨 [Agent] UIDesigner 가동 중: UI 목업 화면을 디자인합니다...")
    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("UIDesigner", "ui_designer_skill", template_id=state_obj.template_id), "UI_DESIGN")
    print(f"✅ [Agent] UIDesigner 작업 완료 — 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    
    # 디자이너는 Execution 모드로
    updates.setdefault("factory_mode", "EXECUTION")
    updates.setdefault("needs_revision", False)
    return updates
