import json
from typing import Dict, Any
from state_models import ProjectState
from core.llm_gateway import gateway, QuotaExhaustedException
from core.agent_registry import agent_skill


async def run_requirement_interviewer(state: Any) -> Dict[str, Any]:
    """요구 확인 인터뷰(RFP 이전 게이트) — 아이디어의 결정적 모호점을 '선택형 질문'으로 생성한다.
    이 노드 직후 interrupt_after 로 파이프라인이 멈추고, 사용자가 프론트에서 선택지를 클릭해
    답하면 그 결과가 human_feedback_queue 로 실려 RFP_Analyst 가 소비한다.
    질문 생성에 실패하거나 질문이 없어도 무해하다(게이트에서 '승인 및 진행'으로 그대로 통과)."""
    state_obj = ProjectState.model_validate(state)

    # 리플레이/재진입 시 재질문 방지 — 이미 답변 요약이 확보됐으면 통과
    if (getattr(state_obj, "clarification_summary", "") or "").strip():
        return {}

    print(" [Agent] Requirement Interviewer 가동: 요구사항 확인 질문(선택형)을 생성합니다...")
    from nodes.planning import _load_skill
    prompt = _load_skill(agent_skill("Requirement_Interviewer", "interviewer_skill", template_id=state_obj.template_id))
    prompt += f"\n\n[사용자 최초 아이디어]\n{state_obj.initial_idea}"

    questions = []
    try:
        output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="json")
        data = json.loads(output)
        for i, q in enumerate((data.get("questions") or [])[:4]):
            opts = []
            for o in (q.get("options") or [])[:4]:
                label = str(o.get("label", "")).strip()
                if not label:
                    continue
                opts.append({
                    "label": label,
                    "description": str(o.get("description", "")).strip(),
                    "recommended": bool(o.get("recommended", False)),
                })
            text = str(q.get("question", "")).strip()
            if not text or len(opts) < 2:
                continue
            # 추천안이 없거나 여럿이면 첫 옵션 하나만 추천으로 정규화(프론트 기본 선택값 보장)
            if sum(1 for o in opts if o["recommended"]) != 1:
                for o in opts:
                    o["recommended"] = False
                opts[0]["recommended"] = True
            questions.append({
                "id": str(q.get("id") or f"Q{i + 1}"),
                "question": text,
                "why": str(q.get("why", "")).strip(),
                "multi": bool(q.get("multi", False)),
                "options": opts,
            })
    except QuotaExhaustedException:
        raise
    except Exception as e:
        print(f"⚠️ [Interviewer] 확인 질문 생성 실패 - 질문 없이 진행합니다: {e}")
        questions = []

    if questions:
        print(f"✋ [Interviewer] 확인 질문 {len(questions)}건 생성 - 사용자의 선택을 기다립니다.")
    else:
        print("⏩ [Interviewer] 확인 질문 없음 - 게이트에서 그대로 승인해 RFP 로 진행하십시오.")

    return {"clarification_questions": questions, "current_stage": "CLARIFICATION"}
