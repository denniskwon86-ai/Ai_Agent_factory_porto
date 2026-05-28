# harness.py
import os
import re
from langchain_core.messages import SystemMessage, HumanMessage

class AgentHarness:
    def __init__(self, llm_pro, llm_flash):
        """
        토큰 최적화를 위해 무거운 추론용(Pro)과 가벼운 요약/정제용(Flash) 
        두 가지 모델을 모두 주입받습니다.
        """
        self.llm_pro = llm_pro
        self.llm_flash = llm_flash
        self.skills_dir = os.path.join(os.path.dirname(__file__), 'skills')

    def _parse_skill_document(self, role_name: str) -> dict:
        """스킬 문서에서 티어링(Model) 정보와 프롬프트 본문을 분리하여 파싱합니다."""
        file_path = os.path.join(self.skills_dir, f"{role_name.lower()}_skill.md")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 정규식으로 최상단 메타데이터(--- Model: pro ---) 추출
            meta_match = re.search(r'^---\nModel:\s*(pro|flash)\n---\n(.*)', content, re.DOTALL)
            if meta_match:
                model_tier = meta_match.group(1).strip()
                instruction = meta_match.group(2).strip()
            else:
                model_tier = 'pro' # 기본값은 안전하게 Pro로 설정
                instruction = content
                
            return {"tier": model_tier, "instruction": instruction}
        except FileNotFoundError:
            return {"tier": "pro", "instruction": f"당신은 {role_name} 전문가입니다."}

    def execute(self, role_name: str, context_data: str, feedback: list = None, previous_output: str = None) -> str:
        """
        모델 티어링 및 델타(Delta) 업데이트 로직이 포함된 코어 실행기
        """
        parsed_skill = self._parse_skill_document(role_name)
        
        # 1. 라우터: 티어에 맞는 모델 선택
        selected_llm = self.llm_pro if parsed_skill["tier"] == "pro" else self.llm_flash
        
        # 2. 델타 업데이트 로직: 피드백이 존재하면 전체 재작성 대신 수정본만 요청하여 토큰 절약
        if feedback and previous_output:
            system_prompt = (
                f"{parsed_skill['instruction']}\n\n"
                "--- [DELTA UPDATE MODE] ---\n"
                "사용자의 피드백이 접수되었습니다. 문서를 처음부터 다시 쓰지 마시오.\n"
                "기존 산출물에서 피드백이 반영되어야 할 부분만 수정하고, 변경되지 않은 부분은 그대로 유지하여 완성된 마크다운을 반환하시오.\n"
                "인사말이나 부연 설명은 절대 금지합니다."
            )
            human_input = f"[기존 산출물]\n{previous_output}\n\n[사용자 피드백]\n{feedback}"
        else:
            system_prompt = (
                f"{parsed_skill['instruction']}\n\n"
                "--- [STRICT RULES] ---\n"
                "1. 인사말이나 부연 설명을 절대 포함하지 마시오.\n"
                "2. 오직 요구된 산출물의 결과(Markdown 내용)만 출력하시오."
            )
            human_input = f"[입력 데이터/컨텍스트]\n{context_data}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_input)
        ]

        response = selected_llm.invoke(messages)
        return response.content.strip()

    def summarize_context(self, text: str) -> str:
        """
        컨텍스트 압축(Pruning) 전용 메서드: 저렴한 Flash 모델을 강제 사용합니다.
        다음 작업자에게 불필요한 맥락이 전달되는 것을 방지하여 입력 토큰을 획기적으로 줄입니다.
        """
        messages = [
            SystemMessage(content="주어진 문서에서 개발 및 설계에 필요한 '핵심 기술 요구사항'과 '기능 명세'만 500자 이내의 마크다운 불릿 포인트로 압축하시오. 부연 설명은 금지합니다."),
            HumanMessage(content=text)
        ]
        response = self.llm_flash.invoke(messages)
        return response.content.strip()