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
            
        print(f" [SkillEvolution] 에이전트 '{agent_id}'의 스킬 개선안이 승인 대기열에 등록되었습니다. ({proposal_id})")

    @staticmethod
    def resolve_skill_file(agent_id: str) -> str:
        """이 에이전트의 규칙이 실제로 들어가는 스킬 파일 경로.

        ⚠️ 이 규칙은 원래 `apply_approved_update` 안에만 있었다 — 그래서 **승인 화면은 어느
          파일이 바뀌는지도, 지금 그 파일에 무엇이 적혀 있는지도 보여 줄 수 없었다.**
          승인하는 사람이 「현재 규칙」을 못 보면 추가 규칙이 기존 규칙과 충돌하는지 알 수
          없고, 충돌은 승인 뒤 에이전트가 이상하게 행동할 때에야 드러난다."""
        from core.agent_registry import agent_skill, list_templates

        skill_name = None
        try:
            for t in list_templates():
                s = agent_skill(agent_id, template_id=t["id"])
                if s:
                    skill_name = s
                    break
        except Exception:
            skill_name = None

        if not skill_name:
            low = (agent_id or "").lower()
            skill_name = f"{low}_skill"
            if low == "rfp_analyst": skill_name = "rfp_skill"
            if low == "master_pm": skill_name = "pm_skill"
            if low == "master_pmo": skill_name = "pmo_skill"
            if low == "codebuilder": skill_name = "backend_skill"
            if low == "manualwriter": skill_name = "manual_skill"
            # 레지스트리 정규 id 는 Backend/Frontend 이다(과거 developer_be/fe 는 오탈자였음).
            if low in ("backend", "developer_be"): skill_name = "backend_skill"
            if low in ("frontend", "developer_fe"): skill_name = "frontend_skill"

        if not skill_name.endswith(".md"):
            skill_name += ".md"
        target = os.path.join(SKILLS_DIR, skill_name)
        if not os.path.exists(target):
            target = os.path.join(SKILLS_DIR, "common_rules.md")
        return target

    @staticmethod
    def _agents_sharing(skill_file: str, exclude: str = "") -> List[str]:
        """같은 스킬 파일을 쓰는 다른 에이전트 — [설계 §5.7] 「**영향 Agent**」.

        ⚠️ 스킬 파일은 공유된다. 한 에이전트의 실패에서 나온 규칙이 그 파일을 쓰는 **모든**
          에이전트의 행동을 바꾼다. 그 사실을 승인 전에 보이지 않으면, 승인자는 한 에이전트만
          손대는 줄 알고 여러 개를 바꾼다."""
        from core.agent_registry import agent_skill, list_templates

        out: List[str] = []
        try:
            for t in list_templates():
                for a in (t.get("agents") or []):
                    aid = a.get("id") or ""
                    if not aid or aid == exclude or aid in out:
                        continue
                    s = agent_skill(aid, template_id=t["id"])
                    if s and os.path.join(SKILLS_DIR,
                                          s if s.endswith(".md") else f"{s}.md") == skill_file:
                        out.append(aid)
        except Exception:
            return out
        return sorted(out)

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
        #: ★ [UI 설계서 §5.7] 제안 카드는 「실패 근거, **현재 규칙**, 추가 규칙, **영향 Agent**,
        #  예상 회귀」를 나란히 보여야 한다. 목록에 함께 실어 화면이 따로 조회하지 않게 한다.
        for p in proposals:
            p.update(self.proposal_context(p.get("agent_id") or ""))
        return proposals

    def proposal_context(self, agent_id: str) -> Dict:
        """승인 판단에 필요한 문맥 — 대상 파일·현재 규칙·영향 Agent.

        ⚠️ 파일을 못 읽으면 **빈 문자열이 아니라 못 읽었다는 사실**을 남긴다. 빈 규칙으로
          보이면 승인자는 「아직 규칙이 없구나」로 읽고 충돌 가능성을 아예 검토하지 않는다."""
        skill_file = self.resolve_skill_file(agent_id)
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                current = f.read()
            readable = True
        except Exception:
            current, readable = "", False
        return {
            "skill_file": os.path.basename(skill_file),
            "current_rules": current,
            "current_rules_readable": readable,
            "affected_agents": self._agents_sharing(skill_file, exclude=agent_id),
        }

    def apply_approved_update(self, proposal_id: str) -> bool:
        pending_path = os.path.join(PENDING_DIR, f"{proposal_id}.json")
        if not os.path.exists(pending_path):
            return False
            
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                proposal = json.load(f)
                
            agent_id = proposal["agent_id"]
            rules = proposal["proposed_rules"]
            
            # ⚠️ 대상 파일 결정은 `resolve_skill_file` **한 곳**에서만 한다. 종전에는 이 안에
            #   같은 규칙이 따로 적혀 있었고, 승인 화면은 그 규칙에 접근할 수 없어 「어느 파일이
            #   바뀌는지」를 보여 주지 못했다. 두 벌이 있으면 한쪽만 고쳐지고, 그러면 화면이
            #   보여 준 파일과 실제로 바뀌는 파일이 갈린다.
            target_file = self.resolve_skill_file(agent_id)
            if not os.path.exists(target_file):
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write("# 공통 주의사항\n\n")


            # 스킬 파일 업데이트 (Append)
            with open(target_file, "a", encoding="utf-8") as f:
                f.write("\n\n###  자가 반성 및 사용자 피드백 기반 추가 규칙\n")
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
