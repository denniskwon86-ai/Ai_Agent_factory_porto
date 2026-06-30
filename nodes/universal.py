# ==========================================
# 범용 노드 실행기 (T3 — 범용 멀티에이전트 플랫폼)
# SW 전용 노드 함수(run_architect 등) 없이, 레지스트리 메타(역할·스킬·모델티어)만으로
# 임의의 에이전트 타입(마케팅/리서치/문서 등)을 실행하는 일반화된 LLM 노드.
#
# 동작: 자기 역할/스킬 + 프로젝트 목표(initial_idea) + 상류 단계 산출물(artifacts)을 묶어
#       LLM 을 호출하고, 결과를 state.artifacts[<agent_id>] 에 누적한다.
# - SW 파이프라인(NODE_IMPL 에 구현이 있는 노드)에는 쓰지 않는다(그쪽은 기존 함수 보존).
# - 커스텀 에이전트로 구성된 '범용 템플릿'의 모든 노드가 이 실행기로 동작한다.
# ==========================================
import os
from typing import Any, Dict

from state_models import ProjectState
from core.agent_registry import agent_meta, agent_skill


def _load_skill(skill_name: str) -> str:
    if not skill_name:
        return ""
    path = f"skills/{skill_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _format_upstream(artifacts: Dict[str, str], self_id: str) -> str:
    """이전 단계 산출물을 사람이 읽는 블록으로 — 범용 노드가 맥락을 이어 작업하도록."""
    items = [(k, v) for k, v in (artifacts or {}).items() if k != self_id and (v or "").strip()]
    if not items:
        return "(아직 이전 단계 산출물이 없습니다 — 이번이 첫 단계입니다.)"
    return "\n\n".join(f"### [{k}]\n{(v or '').strip()}" for k, v in items)


def make_universal_node(agent_id: str):
    """레지스트리 메타로 구동되는 범용 노드 함수를 생성(클로저로 agent_id 고정)."""

    async def _node(state: Any) -> Dict[str, Any]:
        from core.llm_gateway import gateway  # 지연 임포트(순환 방지)
        state_obj = ProjectState.model_validate(state)
        tid = getattr(state_obj, "template_id", "default") or "default"

        meta = agent_meta(agent_id, tid)
        role = meta.get("role", "") or agent_id
        name_ko = meta.get("name_ko", "") or agent_id
        is_heavy = (meta.get("model_tier", "flash") == "pro")
        skill = _load_skill(agent_skill(agent_id, "", template_id=tid))

        print(f"🧩 [Universal] {name_ko}({agent_id}) 실행 중... (tier={'pro' if is_heavy else 'flash'})")

        artifacts = dict(getattr(state_obj, "artifacts", {}) or {})
        upstream = _format_upstream(artifacts, agent_id)
        goal = (getattr(state_obj, "initial_idea", "") or "").strip()

        prompt = (
            f"[당신의 역할]\n{role}\n\n"
            + (f"{skill}\n\n" if skill else "")
            + f"[프로젝트 목표]\n{goal}\n\n"
            f"[이전 단계 산출물]\n{upstream}\n\n"
            "[지시]\n위 역할에 충실하게, 프로젝트 목표와 이전 단계 산출물을 바탕으로 "
            "이번 단계의 산출물을 구체적이고 완결성 있게 작성하라. (서술형 문서로 출력)"
        )

        output = await gateway.aexecute(state_obj, prompt, is_heavy=is_heavy, output_mode="document", light=True)
        artifacts[agent_id] = str(output or "")
        print(f"✅ [Universal] {name_ko} 산출물 {len(artifacts[agent_id])}자 생성")
        return {"artifacts": artifacts}

    _node.__name__ = f"universal_{agent_id}"
    return _node
