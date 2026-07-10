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


def _format_upstream(artifacts: Dict[str, str], summaries: Dict[str, str], self_id: str) -> str:
    """이전 단계 산출물을 사람이 읽는 블록으로 — 범용 노드가 맥락을 이어 작업하도록.
    직전 노드(가장 마지막 항목)는 원본(artifacts)을 쓰고, 그 이전은 요약본(summaries)을 쓴다."""
    keys = [k for k in artifacts.keys() if k != self_id and (artifacts.get(k) or "").strip()]
    if not keys:
        return "(아직 이전 단계 산출물이 없습니다 — 이번이 첫 단계입니다.)"
    
    # 마지막 키(직전 노드)는 원본, 나머지는 요약본
    last_key = keys[-1]
    
    blocks = []
    for k in keys:
        if k == last_key:
            content = artifacts.get(k, "").strip()
            blocks.append(f"### [{k}] (원본 상세)\n{content}")
        else:
            # 요약본이 없으면 원본이라도 쓴다 (하위호환)
            content = summaries.get(k) or artifacts.get(k, "")
            content = content.strip()
            blocks.append(f"### [{k}] (핵심 요약)\n{content}")
            
    return "\n\n".join(blocks)


def _get_format_injection(format_id: str) -> str:
    from api.routes.format_control import load_formats
    formats = load_formats()
    for f in formats:
        if f["id"] == format_id:
            return f["prompt_injection"]
    # 기본 폴백
    return "당신의 최종 결과물은 반드시 <artifact> ... </artifact> 태그 안에 작성하시오. 그 전에 <summary> ... </summary> 태그 안에 핵심 요약을 3줄 이내로 작성하시오."


def make_universal_node(agent_id: str):
    """레지스트리 메타로 구동되는 범용 노드 함수를 생성(클로저로 agent_id 고정)."""

    async def _node(state: Any) -> Dict[str, Any]:
        from core.llm_gateway import gateway  # 지연 임포트(순환 방지)
        from core.parser import extract_summary, extract_artifact
        state_obj = ProjectState.model_validate(state)
        tid = getattr(state_obj, "template_id", "default") or "default"
        fmt_id_from_state = getattr(state_obj, "output_format_id", "default") or "default"
        meta = agent_meta(agent_id, tid)
        fmt_id = meta.get("output_format") or fmt_id_from_state

        role = meta.get("role", "") or agent_id
        name_ko = meta.get("name_ko", "") or agent_id
        is_heavy = (meta.get("model_tier", "flash") == "pro")
        skill = _load_skill(agent_skill(agent_id, "", template_id=tid))

        print(f"🧩 [Universal] {name_ko}({agent_id}) 실행 중... (tier={'pro' if is_heavy else 'flash'}, format={fmt_id})")

        artifacts = dict(getattr(state_obj, "artifacts", {}) or {})
        summaries = dict(getattr(state_obj, "artifact_summaries", {}) or {})
        upstream = _format_upstream(artifacts, summaries, agent_id)
        
        goal = (getattr(state_obj, "initial_idea", "") or "").strip()
        master_data = (getattr(state_obj, "master_data", "") or "").strip()

        master_block = f"[전사 마스터 데이터 및 제약사항]\n{master_data}\n\n" if master_data else ""
        format_injection = _get_format_injection(fmt_id) if fmt_id else ""

        prompt = (
            f"[당신의 역할]\n{role}\n\n"
            + (f"{skill}\n\n" if skill else "")
            + master_block
            + f"[프로젝트 목표]\n{goal}\n\n"
            f"[이전 단계 산출물]\n{upstream}\n\n"
            "[지시]\n위 역할에 충실하게, 프로젝트 목표와 이전 단계 산출물을 바탕으로 "
            "이번 단계의 산출물을 구체적이고 완결성 있게 작성하라. (마스터 데이터가 주어진 경우 최우선으로 준수할 것.)\n\n"
            f"[출력 양식 제약 (중요)]\n{format_injection}"
        )

        output = await gateway.aexecute(state_obj, prompt, is_heavy=is_heavy, output_mode="document", light=True)
        
        # 파싱 (Level 2 하네스)
        out_summary = extract_summary(output)
        out_artifact = extract_artifact(output)
        
        artifacts[agent_id] = str(out_artifact or "")
        summaries[agent_id] = str(out_summary or "")
        
        print(f"✅ [Universal] {name_ko} 산출물 생성 (요약 {len(summaries[agent_id])}자, 상세 {len(artifacts[agent_id])}자)")
        return {"artifacts": artifacts, "artifact_summaries": summaries}

    _node.__name__ = f"universal_{agent_id}"
    return _node
