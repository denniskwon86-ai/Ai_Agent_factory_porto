import os
import time
import yaml
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq  # 👈 [신규 추가] Groq 라이브러리

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
        # 1. 메인 엔진: 구글 Gemini 초기화
        self.llm_pro = ChatGoogleGenerativeAI(
            model=self.current_model_name, 
            temperature=0.2, 
            timeout=300.0, 
            max_retries=0
        )
        self.llm_flash = ChatGoogleGenerativeAI(
            model=self.current_model_name, 
            temperature=0.1, 
            timeout=300.0, 
            max_retries=0
        )

        # 2. 보조(Fallback) 엔진: Groq 초기화 (키가 있을 때만 활성화)
        groq_key = os.environ.get("GROQ_API_KEY")
        self.use_groq = bool(groq_key)
        
        if self.use_groq:
            print("🚀 [System] Groq API Key 감지됨. 듀얼 코어 하이브리드 엔진을 스탠바이합니다.")
            self.groq_pro = ChatGroq(
                model="llama3-70b-8192", # Architect/PM 등 복잡한 추론용 대형 모델
                temperature=0.2, 
                max_retries=0, 
                timeout=120.0, 
                api_key=groq_key
            )
            self.groq_flash = ChatGroq(
                model="mixtral-8x7b-32768", # 코드/문서 작성용 빠르고 컨텍스트 긴 모델
                temperature=0.1, 
                max_retries=0, 
                timeout=120.0, 
                api_key=groq_key
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

    def _safe_invoke(self, is_pro: bool, skill_body: str, context: str) -> str:
        """
        LLM 호출 및 에러 핸들링. 
        [하이브리드 로직] 구글 API 실패 시 Groq로 즉시 우회(Fallback)합니다.
        """
        import time
        retry_count = 0
        current_context = context

        while True:
            full_prompt = f"{skill_body}\n\n{current_context}"
            llm = self.llm_pro if is_pro else self.llm_flash

            try:
                # [1지망] 구글 Gemini 호출 시도
                response = llm.invoke(full_prompt)
                time.sleep(6) # 구글 Rate limit 방어
                return response.content

            except Exception as e:
                error_msg = str(e).lower()
                
                # 타임아웃(504)이나 할당량 초과(429) 감지 시
                if "429" in error_msg or "exhausted" in error_msg or "timeout" in error_msg or "timed out" in error_msg or "deadline_exceeded" in error_msg or "504" in error_msg:
                    
                    # 🚀 [비상 가동] Groq API로 즉시 우회 (Fallback)
                    if getattr(self, 'use_groq', False):
                        print("🔄 [Fallback] 구글 API 병목/타임아웃 감지! 초고속 Groq 엔진으로 즉시 우회하여 생성합니다...")
                        try:
                            fallback_llm = self.groq_pro if is_pro else self.groq_flash
                            groq_response = fallback_llm.invoke(full_prompt)
                            time.sleep(2) # Groq는 속도가 빠르므로 대기시간 단축
                            return groq_response.content
                        except Exception as groq_e:
                            print(f"⚠️ [Fallback 경고] Groq 엔진도 응답하지 않습니다 (재시도 루프 진입): {groq_e}")
                            # Groq도 뻗었으면 아래의 기존 구글 재시도/압축 로직으로 자연스럽게 넘어감

                    # [기존 로직] 구글 일일 할당량 완전 소진 시 모델 교체
                    if "perday" in error_msg or "per_day" in error_msg or "free_tier_requests" in error_msg:
                        self._rotate_model()
                        retry_count = 0
                        continue
                    else:
                        retry_count += 1
                        if retry_count > 3:
                            print("🚨 [압축 방어] context만 50% 압축. skill_body(지침)는 안전하게 보존합니다.")
                            half = len(current_context) // 4
                            current_context = (
                                current_context[:half]
                                + "\n\n... [context 중략 - 안전 방어막 가동] ...\n\n"
                                + current_context[-half:]
                            )
                            retry_count = 0
                            time.sleep(5)
                            continue
                        print(f"⏳ [병목 감지] 60초 대기 후 재시도... (시도: {retry_count}/3)")
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

    def execute(self, role_name, context_data, feedback=None, previous_output=None) -> str:
        """
        스킬 문서를 읽어 프롬프트를 조립하고 안전하게 실행합니다.
        [수정] skill_body와 context를 분리하여 _safe_invoke에 전달합니다.
        """
        skill_data = self._parse_skill_document(role_name)
        is_pro = (skill_data["meta"].get("Model", "pro").lower() != "flash")

        # 1. 절대 압축 금지 영역 (역할 지침)
        skill_body = f"다음 지침에 따라 임무를 수행하십시오:\n\n{skill_data['body']}"

        # 2. 압축 허용 영역 (컨텍스트 및 이전 산출물)
        safe_context = context_data
        if len(safe_context) > 10000:
            safe_context = "...(상단 생략)...\n" + safe_context[-10000:]

        context = f"[Context]\n{safe_context}\n"

        if previous_output:
            safe_prev = previous_output
            if len(safe_prev) > 8000:
                safe_prev = "...(생략)...\n" + safe_prev[-8000:]
            context += f"\n[Previous Output]\n{safe_prev}\n"
            
        if feedback:
            context += f"\n[Feedback]\n수정(Delta Update) 지시:\n{feedback}\n"

        return self._safe_invoke(is_pro, skill_body, context)

    def summarize_context(self, text: str) -> str:
        if not text:
            return ""
            
        safe_text = text
        if len(safe_text) > 4000:
            safe_text = safe_text[:2000] + "\n\n... (중간 생략) ...\n\n" + safe_text[-2000:]
            
        # [수정] 지침(skill_body)과 대상 텍스트(context)를 명확히 분리하여 안전하게 호출
        skill_body = "다음 텍스트를 파이프라인의 다음 에이전트가 이해하기 쉽도록 핵심만 500자 이내의 마크다운 불릿 포인트로 요약하십시오."
        context_data = f"[요약 대상 텍스트]\n{safe_text}"
        
        return self._safe_invoke(False, skill_body, context_data)