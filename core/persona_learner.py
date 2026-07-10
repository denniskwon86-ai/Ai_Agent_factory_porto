import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any

from core.llm_gateway import gateway

DATA_DIR = "data"
INTERACTION_LOG_PATH = os.path.join(DATA_DIR, "interaction_log.jsonl")
PROFILE_PATH = os.path.join(DATA_DIR, "company_profile.json")

class PersonaLearner:
    """
    사용자의 피드백, 채팅 내용 등 상호작용을 기록하고 백그라운드에서 분석하여
    company_profile.json을 점진적으로 구축 및 갱신합니다.
    """
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._ensure_files()

    def _ensure_files(self):
        if not os.path.exists(PROFILE_PATH):
            default_profile = {
                "preferred_tone": "친절하고 전문적인 어조",
                "quality_standards": "기본 품질 기준",
                "domain_terminology": [],
                "common_corrections": [],
                "industry_context": "일반적인 비즈니스 환경"
            }
            with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(default_profile, f, ensure_ascii=False, indent=2)

    def record_interaction(self, event_type: str, content: str, project_id: str = "global"):
        """채팅 내용이나 HOTL 피드백 등 사용자 상호작용 기록"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "project_id": project_id,
            "content": content
        }
        with open(INTERACTION_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_company_profile(self) -> Dict[str, Any]:
        """현재 학습된 기업/사용자 성향 프로필 반환"""
        if os.path.exists(PROFILE_PATH):
            try:
                with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ [PersonaLearner] 프로필 읽기 실패: {e}")
        return {}

    async def analyze_and_update_profile(self):
        """누적된 interaction_log를 LLM으로 분석하여 프로필 업데이트"""
        if not os.path.exists(INTERACTION_LOG_PATH):
            return

        with open(INTERACTION_LOG_PATH, "r", encoding="utf-8") as f:
            logs = f.readlines()
            
        if not logs:
            return

        # 최근 50개의 상호작용만 분석
        recent_logs = [json.loads(line) for line in logs[-50:]]
        log_text = json.dumps(recent_logs, ensure_ascii=False, indent=2)
        
        current_profile = self.get_company_profile()

        prompt = f"""
당신은 사용자의 성향과 피드백을 분석하여 기업 맞춤형 페르소나를 구축하는 'Profile Optimizer Agent'입니다.

[기존 기업 프로필]
{json.dumps(current_profile, ensure_ascii=False, indent=2)}

[최근 사용자 상호작용 로그 (채팅 및 피드백)]
{log_text}

사용자가 지시한 내용, 반복적으로 수정을 요구하는 사항, 선호하는 문서 스타일, 업무 도메인 특수 용어 등을 분석하여 기존 프로필을 갱신하십시오.
결과값은 JSON으로 반환해야 합니다.

필수 포함 필드:
- preferred_tone: 문체 및 어조
- quality_standards: 자주 요구하는 품질이나 검수 기준
- domain_terminology: 사용자 회사에서 쓰는 특수 용어 리스트
- common_corrections: 반복적으로 지적받은 사항이나 금지어
- industry_context: 추정되는 산업군이나 프로젝트 문맥
"""
        try:
            from state_models import ProjectState
            response = await gateway.aexecute(
                state=ProjectState(), 
                skill_prompt=prompt, 
                is_heavy=False, 
                output_mode="json",
                light=True
            )
            updated_profile = json.loads(response)
            
            with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(updated_profile, f, ensure_ascii=False, indent=2)
                
            print(f"🧠 [PersonaLearner] 기업 프로필이 사용자 상호작용을 바탕으로 업데이트 되었습니다.")
        except Exception as e:
            print(f"⚠️ [PersonaLearner] 프로필 분석 중 오류 발생: {e}")

persona_learner = PersonaLearner()
