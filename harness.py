import os
import time
import yaml

class AgentHarness:
    def __init__(self, llm_pro, llm_flash):
        self.llm_pro = llm_pro
        self.llm_flash = llm_flash
        self.skills_dir = "skills"

    def _safe_invoke(self, llm, prompt: str) -> str:
        """429 Rate Limit 방어를 위한 지수 백오프(Exponential Backoff) 자동 재시도 로직"""
        max_retries = 3
        delay = 35

        for attempt in range(max_retries):
            try:
                response = llm.invoke(prompt)
                return response.content
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    if attempt < max_retries - 1:
                        print(f"\n⏳ [Rate Limit 쉴드 가동] API 분당 호출 한도 도달. {int(delay)}초간 대기 후 파이프라인을 자동 재개합니다... (재시도: {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        delay *= 1.5
                    else:
                        print("\n🚨 최대 재시도 대기 횟수를 초과하여 파이프라인을 중단합니다.")
                        raise e
                else:
                    raise e

    def _parse_skill_document(self, role_name: str) -> dict:
        """마크다운 스킬 문서에서 YAML 프론트매터와 프롬프트 본문을 분리합니다."""
        file_path = os.path.join(self.skills_dir, f"{role_name}.md")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"스킬 문서를 찾을 수 없습니다: {file_path}")
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                return {"meta": frontmatter, "body": body}
        
        return {"meta": {"Model": "pro"}, "body": content}

    def execute(self, role_name: str, context_data: str, feedback: str = None, previous_output: str = None) -> str:
        """에이전트 역할에 맞는 프롬프트를 조립하고 LLM을 실행합니다."""
        skill_data = self._parse_skill_document(role_name)
        
        # [복구 및 수정됨] YAML 프론트매터 기반 동적 모델 라우팅
        model_tier = skill_data["meta"].get("Model", "pro").lower()
        if model_tier == "flash":
            llm = self.llm_flash
            print(f"🔀 [Model Router] '{role_name}' 임무 ➔ [Flash 모델] 할당 (고속/경량 처리)")
        else:
            llm = self.llm_pro
            print(f"🔀 [Model Router] '{role_name}' 임무 ➔ [Pro 모델] 할당 (복잡/심층 추론)")
        
        prompt_template = skill_data["body"]
        prompt = f"다음 지침에 따라 임무를 수행하십시오.\n\n{prompt_template}\n\n[Context Data]\n{context_data}\n"
        
        if previous_output:
            prompt += f"\n[Previous Output (기존 산출물)]\n{previous_output}\n"
            if feedback:
                prompt += f"\n[Human Feedback (수정 지시사항)]\n사용자의 피드백을 엄격히 반영하여 기존 산출물을 수정(Delta Update) 하십시오:\n{feedback}\n"
        
        return self._safe_invoke(llm, prompt)

    def summarize_context(self, text: str) -> str:
        """다음 에이전트로 넘길 컨텍스트 토큰 최적화를 위한 500자 요약기"""
        if not text:
            return ""
        # 요약은 단순 작업이므로 항상 비용이 저렴한 Flash 모델을 고정 사용합니다.
        prompt = f"다음 텍스트를 파이프라인의 다음 에이전트가 이해하기 쉽도록 핵심만 500자 이내의 마크다운 불릿 포인트로 요약하십시오:\n\n{text}"
        return self._safe_invoke(self.llm_flash, prompt)