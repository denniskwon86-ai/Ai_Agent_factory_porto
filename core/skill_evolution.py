import os
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List

from core.llm_gateway import gateway

DATA_DIR = "data"
PROPOSALS_DIR = os.path.join(DATA_DIR, "skill_proposals")
PENDING_DIR = os.path.join(PROPOSALS_DIR, "pending")
APPROVED_DIR = os.path.join(PROPOSALS_DIR, "approved")
REJECTED_DIR = os.path.join(PROPOSALS_DIR, "rejected")
SKILLS_DIR = "skills"

class SkillEvolutionEngine:
    """
    에이전트가 실패하거나 피드백을 받았을 때 스스로 반성하고,
    자신의 스킬 마크다운 파일에 추가할 '개선 Rule'을 제안(Propose)합니다.
    """
    def __init__(self):
        for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
            os.makedirs(d, exist_ok=True)

    async def analyze_failure(self, agent_id: str, feedback: str, state_data: Any):
        """실패 원인을 분석하여 새로운 룰(Rule) 제안"""
        from state_models import ProjectState
        
        prompt = f"""
당신은 AI 에이전트들의 성능을 모니터링하고 훈련시키는 'Skill Optimizer Agent'입니다.
현재 '{agent_id}' 에이전트가 다음과 같은 피드백/반려 사유를 받았습니다:

[피드백 / 반려 사유]
{feedback}

에이전트가 향후 동일한 실수를 반복하지 않으려면, 이 에이전트의 스킬 문서(Prompt)에 어떤 '주의사항(Rule)'을 추가해야 할까요?
피드백을 근본적으로 해결할 수 있는 **구체적이고 명확한 지시문 1~2개**를 도출하세요.

응답은 오직 JSON 포맷으로 아래 구조에 맞춰 작성하세요:
{{
  "analysis": "왜 이런 문제가 발생했는지에 대한 분석 (1~2줄)",
  "proposed_rules": [
    "- [지시사항 1]",
    "- [지시사항 2]"
  ]
}}
"""
        try:
            # state_data는 dict일 수도 있고 pydantic 모델일 수도 있음
            # 가벼운 처리를 위해 빈 ProjectState로 컨텍스트 최소화 (feedback이 핵심이므로)
            st = ProjectState() if not isinstance(state_data, ProjectState) else state_data
            
            response = await gateway.aexecute(
                state=st, 
                skill_prompt=prompt, 
                is_heavy=False, 
                output_mode="json",
                light=True
            )
            result = json.loads(response)
            
            if result.get("proposed_rules"):
                self.propose_skill_update(agent_id, result["proposed_rules"], result.get("analysis", ""))
                
        except Exception as e:
            print(f"⚠️ [SkillEvolution] 실패 분석 중 오류 발생: {e}")

    def propose_skill_update(self, agent_id: str, proposed_rules: List[str], analysis: str):
        proposal_id = f"prop_{uuid.uuid4().hex[:8]}"
        proposal = {
            "id": proposal_id,
            "agent_id": agent_id,
            "proposed_rules": proposed_rules,
            "analysis": analysis,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        filepath = os.path.join(PENDING_DIR, f"{proposal_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(proposal, f, ensure_ascii=False, indent=2)
            
        print(f"🧬 [SkillEvolution] 에이전트 '{agent_id}'의 스킬 개선안이 승인 대기열에 등록되었습니다. ({proposal_id})")

    def list_pending_proposals(self) -> List[Dict]:
        proposals = []
        if not os.path.exists(PENDING_DIR):
            return proposals
            
        for fname in os.listdir(PENDING_DIR):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(PENDING_DIR, fname), "r", encoding="utf-8") as f:
                        proposals.append(json.load(f))
                except:
                    pass
        # 최신순 정렬
        proposals.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return proposals

    def apply_approved_update(self, proposal_id: str) -> bool:
        pending_path = os.path.join(PENDING_DIR, f"{proposal_id}.json")
        if not os.path.exists(pending_path):
            return False
            
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                proposal = json.load(f)
                
            agent_id = proposal["agent_id"]
            rules = proposal["proposed_rules"]
            
            from core.agent_registry import list_templates, agent_skill
            
            skill_name = None
            # 전체 템플릿을 순회하며 해당 agent_id의 skill 설정값을 찾음
            for t in list_templates():
                s = agent_skill(agent_id, template_id=t["id"])
                if s:
                    skill_name = s
                    break
                    
            if not skill_name:
                # 못 찾을 경우 기존의 범용 폴백 룰 적용
                skill_name = f"{agent_id.lower()}_skill"
                if agent_id.lower() == "rfp_analyst": skill_name = "rfp_skill"
                if agent_id.lower() == "master_pm": skill_name = "pm_skill"
                if agent_id.lower() == "master_pmo": skill_name = "pmo_skill"
                if agent_id.lower() == "codebuilder": skill_name = "backend_skill"
                if agent_id.lower() == "manualwriter": skill_name = "manual_skill"
                # 레지스트리 정규 id 는 Backend/Frontend 이다(과거 developer_be/fe 는 오탈자였음).
                if agent_id.lower() in ("backend", "developer_be"): skill_name = "backend_skill"
                if agent_id.lower() in ("frontend", "developer_fe"): skill_name = "frontend_skill"
            
            if not skill_name.endswith(".md"):
                skill_name += ".md"
                
            target_file = os.path.join(SKILLS_DIR, skill_name)
            
            if not os.path.exists(target_file):
                # 못 찾으면 범용적으로 일단 기록
                target_file = os.path.join(SKILLS_DIR, f"common_rules.md")
                if not os.path.exists(target_file):
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write("# 공통 주의사항\n\n")
            
            # 스킬 파일 업데이트 (Append)
            with open(target_file, "a", encoding="utf-8") as f:
                f.write("\n\n### 💡 자가 반성 및 사용자 피드백 기반 추가 규칙\n")
                f.write(f"*(업데이트: {datetime.now().strftime('%Y-%m-%d')})*\n")
                for rule in rules:
                    f.write(f"{rule}\n")
                    
            # 이동
            proposal["status"] = "approved"
            proposal["applied_at"] = datetime.now().isoformat()
            proposal["target_file"] = target_file
            
            os.remove(pending_path)
            with open(os.path.join(APPROVED_DIR, f"{proposal_id}.json"), "w", encoding="utf-8") as f:
                json.dump(proposal, f, ensure_ascii=False, indent=2)
                
            return True
        except Exception as e:
            print(f"⚠️ [SkillEvolution] 스킬 업데이트 적용 실패: {e}")
            return False

    def reject_proposal(self, proposal_id: str) -> bool:
        pending_path = os.path.join(PENDING_DIR, f"{proposal_id}.json")
        if not os.path.exists(pending_path):
            return False
            
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                proposal = json.load(f)
                
            proposal["status"] = "rejected"
            proposal["rejected_at"] = datetime.now().isoformat()
            
            os.remove(pending_path)
            with open(os.path.join(REJECTED_DIR, f"{proposal_id}.json"), "w", encoding="utf-8") as f:
                json.dump(proposal, f, ensure_ascii=False, indent=2)
                
            return True
        except Exception as e:
            return False

skill_evolution = SkillEvolutionEngine()
