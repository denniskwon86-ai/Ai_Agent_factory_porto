import os
import time
import yaml
import re
from langchain_google_genai import ChatGoogleGenerativeAI

class AgentHarness:
    def __init__(self, model_names: list = None):
        self.fallback_list = model_names or [
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite-001",
            "gemini-2.0-flash-lite",
            "gemini-2.5-flash"
        ]
        self.exhausted_models = set()
        self.current_model_name = self.fallback_list[0]
        print(f"⚙️ [Harness Core] 초기 메인 엔진 가동: {self.current_model_name}")
        self._init_current_llm()
        self.skills_dir = "skills"

    def _init_current_llm(self):
        # [핵심] 구글 SDK 내부의 무한 재시도를 막기 위해 명시적 timeout(초)과 max_retries(0) 강제 주입!
        self.llm_pro = ChatGoogleGenerativeAI(
            model=self.current_model_name, 
            temperature=0.2, 
            timeout=120.0, 
            max_retries=0
        )
        self.llm_flash = ChatGoogleGenerativeAI(
            model=self.current_model_name, 
            temperature=0.1, 
            timeout=120.0, 
            max_retries=0
        )

    def _rotate_model(self):
        self.exhausted_models.add(self.current_model_name)
        available = [m for m in self.fallback_list if m not in self.exhausted_models]
        
        if not available:
            print("\n⛔ [CRITICAL ERROR] 패닉! 준비된 모든 예비 모델의 일일 무료 한도가 완전히 소진되었습니다.")
            raise Exception("QuotaExhaustedAllModelsException")
            
        self.current_model_name = available[0]
        print(f"🔄 [동적 라우터] -> 차순위 대안 모델인 '{self.current_model_name}'(으)로 즉시 엔진을 교체합니다.")
        self._init_current_llm()

    def _safe_invoke(self, is_pro: bool, prompt: str) -> str:
        retry_count = 0
        current_prompt = prompt

        while True:
            llm = self.llm_pro if is_pro else self.llm_flash
            
            try:
                # 타임아웃에 걸려 강제 반환되거나, 성공 시 6초 대기 후 반환
                response = llm.invoke(current_prompt)
                time.sleep(6)
                return response.content
                
            except Exception as e:
                # 발생한 모든 에러를 문자열로 전환하여 원시 포획
                error_msg = str(e).lower()
                
                # 429, Resource Exhausted, 또는 Timeout(네트워크 뻗음) 모두 포획
                if "429" in error_msg or "exhausted" in error_msg or "timeout" in error_msg:
                    
                    if "perday" in error_msg or "per_day" in error_msg or "free_tier_requests" in error_msg:
                        print(f"\n⚠️ [RPD 소진 감지] '{self.current_model_name}' 하루 할당량 초과.")
                        self._rotate_model()
                        retry_count = 0
                        continue
                        
                    else:
                        retry_count += 1
                        if retry_count > 3:
                            print(f"\n🚨 [네트워크/TPM 폭발 방어] 3회 이상 대기 실패! 프롬프트를 50% 강제 압축하여 탈출 시도.")
                            half_length = len(current_prompt) // 2
                            current_prompt = current_prompt[:half_length//2] + "\n\n... [중략 (안전 방어막 가동)] ...\n\n" + current_prompt[-half_length//2:]
                            retry_count = 0
                            time.sleep(5)
                            continue
                            
                        print(f"\n⏳ [병목 감지] '{self.current_model_name}' 서버 무응답 또는 과부하. 60초 대기 후 재시도... (시도: {retry_count}/3)")
                        time.sleep(60)
                        continue
                else:
                    raise e

    def _parse_skill_document(self, role_name: str) -> dict:
        file_path = os.path.join(self.skills_dir, f"{role_name}.md")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"스킬 문서 없음: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return {"meta": yaml.safe_load(parts[1]), "body": parts[2].strip()}
        return {"meta": {"Model": "pro"}, "body": content}

    def execute(self, role_name: str, context_data: str, feedback: str = None, previous_output: str = None) -> str:
        skill_data = self._parse_skill_document(role_name)
        is_pro = (skill_data["meta"].get("Model", "pro").lower() != "flash")
        
        safe_context = context_data
        if len(safe_context) > 10000:
            safe_context = "...(상단 생략)...\n" + safe_context[-10000:]
            
        prompt = f"다음 지침에 따라 임무 수행:\n\n{skill_data['body']}\n\n[Context]\n{safe_context}\n"
        
        if previous_output:
            safe_prev = previous_output
            if len(safe_prev) > 8000:
                safe_prev = "...(생략)...\n" + safe_prev[-8000:]
            prompt += f"\n[Previous Output]\n{safe_prev}\n"
            if feedback:
                prompt += f"\n[Feedback]\n수정(Delta Update) 지시:\n{feedback}\n"
        
        return self._safe_invoke(is_pro, prompt)

    def summarize_context(self, text: str) -> str:
        if not text:
            return ""
            
        safe_text = text
        if len(safe_text) > 4000:
            safe_text = safe_text[:2000] + "\n\n... (중간 생략) ...\n\n" + safe_text[-2000:]
            
        prompt = f"다음 텍스트를 파이프라인의 다음 에이전트가 이해하기 쉽도록 핵심만 500자 이내의 마크다운 불릿 포인트로 요약하십시오:\n\n{safe_text}"
        return self._safe_invoke(False, prompt)