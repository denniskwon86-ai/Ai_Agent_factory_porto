import os
import time
import yaml
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
import config

class AgentHarness:
    def __init__(self):
        self.pro_fallback_list = config.LLM_PRO_FALLBACK_LIST
        self.flash_fallback_list = config.LLM_FLASH_FALLBACK_LIST
        self.pro_idx = 0
        self.flash_idx = 0
        self.skills_dir = "skills"
        self._init_current_llm()

    def _init_current_llm(self):
        """현재 인덱스에 맞춰 Gemini 또는 Groq 클라이언트를 동적으로 생성합니다."""
        pro_model = self.pro_fallback_list[self.pro_idx]
        flash_model = self.flash_fallback_list[self.flash_idx]
        
        print(f"⚙️ [Harness Core] 현재 엔진 ➔ PRO: {pro_model} / FLASH: {flash_model}")

        # PRO 모델 인스턴스화
        if "gemini" in pro_model:
            self.llm_pro = ChatGoogleGenerativeAI(model=pro_model, temperature=0.2, timeout=120.0, max_retries=0)
        else:
            self.llm_pro = ChatGroq(model=pro_model, temperature=0.2, timeout=120.0, max_retries=0)

        # FLASH 모델 인스턴스화
        if "gemini" in flash_model:
            self.llm_flash = ChatGoogleGenerativeAI(model=flash_model, temperature=0.1, timeout=120.0, max_retries=0)
        else:
            self.llm_flash = ChatGroq(model=flash_model, temperature=0.1, timeout=120.0, max_retries=0)

    def _rotate_model(self, is_pro: bool):
        """할당량 초과 시 예비 모델로 크로스오버(스위칭)합니다."""
        if is_pro:
            self.pro_idx += 1
            if self.pro_idx >= len(self.pro_fallback_list):
                raise Exception("⛔ [CRITICAL ERROR] PRO 예비 모델 한도 전면 소진")
        else:
            self.flash_idx += 1
            if self.flash_idx >= len(self.flash_fallback_list):
                raise Exception("⛔ [CRITICAL ERROR] FLASH 예비 모델 한도 전면 소진")
        
        print(f"🔄 [동적 라우터] 서킷 브레이커 가동. 엔진 교체 및 핫스와핑 진행 중...")
        self._init_current_llm()

    def _get_safe_char_limit(self, is_pro: bool) -> int:
        """모델별 토큰 한도를 기반으로 동적 문자열 압축 허용치를 계산합니다."""
        model_name = self.pro_fallback_list[self.pro_idx] if is_pro else self.flash_fallback_list[self.flash_idx]
        token_limit = config.MODEL_CONTEXT_LIMITS.get(model_name, 6000)
        return int(token_limit * config.CHARS_PER_TOKEN_ESTIMATE)

    def _safe_invoke(self, is_pro: bool, skill_body: str, current_context: str) -> str:
        """System/User 메시지 분리 및 HumanMessage 전용 다이나믹 압축 방어막"""
        retry_count = 0
        
        while True:
            # 페르소나(System)와 작업 데이터(Human)를 엄격히 분리
            messages = [
                SystemMessage(content=skill_body),
                HumanMessage(content=current_context)
            ]
            
            llm = self.llm_pro if is_pro else self.llm_flash

            try:
                response = llm.invoke(messages)
                time.sleep(4) 
                return response.content

            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "exhausted" in error_msg or "timeout" in error_msg or "limit" in error_msg:
                    # 일일 할당량 소진 에러 감지 시 즉각 스위칭
                    if "perday" in error_msg or "per_day" in error_msg or "free_tier_requests" in error_msg:
                        self._rotate_model(is_pro)
                        retry_count = 0
                        continue
                    else:
                        retry_count += 1
                        if retry_count > 3:
                            print("🚨 [압축 방어] 토큰 오버플로우 감지. 작업 데이터(HumanMessage)를 동적 압축합니다.")
                            char_limit = self._get_safe_char_limit(is_pro)
                            if len(current_context) > char_limit:
                                half = char_limit // 3
                                # SystemMessage(skill_body)는 건드리지 않고 오직 작업 데이터만 압축
                                current_context = current_context[:half] + "\n\n...[중략 (안전 방어막)]...\n\n" + current_context[-half:]
                            retry_count = 0
                            time.sleep(5)
                            continue
                        
                        print(f"⏳ [병목 감지] 30초 대기 후 재시도... ({retry_count}/3)")
                        time.sleep(30)
                        continue
                else:
                    raise e

    def _parse_skill_document(self, role_name: str) -> dict:
        file_path = os.path.join(self.skills_dir, f"{role_name}.md")
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return {"meta": yaml.safe_load(parts[1]), "body": parts[2].strip()}
        return {"meta": {"Model": "pro"}, "body": content}

    def execute(self, role_name, context_data, feedback=None, previous_output=None) -> str:
        skill_data = self._parse_skill_document(role_name)
        
        # 명시적 TIER_MAP 기반 티어 할당
        model_tier = skill_data["meta"].get("Model", "pro").lower()
        TIER_MAP = {"pro": True, "flash": False, "lite": False}
        is_pro = TIER_MAP.get(model_tier, True)

        skill_body = f"다음 지침에 따라 임무를 수행하십시오:\n\n{skill_data['body']}"
        
        context = f"[Context]\n{context_data}\n"
        if previous_output:
            context += f"\n[Previous Output]\n{previous_output}\n"
        if feedback:
            context += f"\n[Feedback]\n수정 지시:\n{feedback}\n"

        output = self._safe_invoke(is_pro, skill_body, context)

        # 코딩 에이전트의 Zero-Chatter 강제 (XML 태그 외의 찌꺼기 제거)
        if role_name in ("frontend_skill", "backend_skill"):
            clean_blocks = re.findall(r'<file\s[^>]*>.*?</file>', output, re.DOTALL)
            if clean_blocks:
                output = "\n".join(clean_blocks)
                print(f"  🧹 [Chatter Stripper] XML 태그 외 텍스트 제거 완료 ({role_name})")

        return output

    def summarize_context(self, context: str) -> str:
        """
        컨텍스트가 너무 길 경우 요약본을 생성합니다. (Head+Tail 기법 적용 유지)
        """
        if not context or len(context) < 3000:
            return context
            
        print("  ✂️ [Diet] 컨텍스트 크기가 커서 요약을 진행합니다.")
        
        # Head + Tail 기법: 앞 2000자, 뒤 2000자만 추출하여 토큰 폭발 방어
        if len(context) > 6000:
            context = context[:2000] + "\n\n...[중간 생략]...\n\n" + context[-2000:]
            
        skill_body = "당신은 제공된 문서를 핵심만 간결하게 요약하는 전문 요약 에이전트입니다. 코드 마크다운과 핵심 로직은 훼손하지 마십시오."
        
        # 요약은 속도와 비용을 위해 flash 모델 사용
        return self._safe_invoke(is_pro=False, skill_body=skill_body, current_context=context)