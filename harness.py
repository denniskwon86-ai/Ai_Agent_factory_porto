import os
import time
import yaml
import re
from langchain_google_genai import ChatGoogleGenerativeAI

class AgentHarness:
    def __init__(self, model_names: list = None):
        # 1. 진단 스크립트로 사용 가능한 것이 확인된 2026년형 차세대 고효율 예비 탄창 리스트
        self.fallback_list = model_names or [
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite-001",
            "gemini-2.0-flash-lite",
            "gemini-2.5-flash"
        ]
        # [보완 2] 일일 할당량이 고갈된 모델을 격리 보관하는 영구 블랙리스트
        self.exhausted_models = set()
        
        # 최초 1순위 모델로 초기 설정
        self.current_model_name = self.fallback_list[0]
        print(f"⚙️ [Harness Core] 초기 메인 엔진 가동: {self.current_model_name}")
        
        self._init_current_llm()
        self.skills_dir = "skills"

    def _init_current_llm(self):
        """현재 지정된 모델명으로 랭체인 인스턴스를 메모리에 핫스와핑"""
        self.llm_pro = ChatGoogleGenerativeAI(model=self.current_model_name, temperature=0.2)
        self.llm_flash = ChatGoogleGenerativeAI(model=self.current_model_name, temperature=0.1)

    def _rotate_model(self):
        """RPD 고갈 시 현재 모델을 블랙리스트에 누적하고 차순위 예비 탄창을 즉시 장전"""
        self.exhausted_models.add(self.current_model_name)
        available = [m for m in self.fallback_list if m not in self.exhausted_models]
        
        if not available:
            print("\n⛔ [CRITICAL ERROR] 패닉! 준비된 모든 예비 모델의 일일 무료 한도가 완전히 소진되었습니다.")
            print("자정(UTC) 이후 쿼터 초기화를 기다리거나 유료 종량제(Pay-as-you-go) 플랜으로의 전환이 필수적입니다.")
            raise Exception("QuotaExhaustedAllModelsException")
            
        self.current_model_name = available[0]
        print(f"🔄 [동적 라우터] -> 차순위 대안 모델인 '{self.current_model_name}'(으)로 즉시 엔진을 교체합니다.")
        self._init_current_llm()

    def _safe_invoke(self, is_pro: bool, prompt: str) -> str:
        """[보완 1] 429 에러 유형을 RPM(분당) vs RPD(일일)로 정밀하게 분기 처리하는 철통 방어 엔진"""
        while True:
            # 핫스와프된 최신 인스턴스를 실시간 반영하여 호출
            llm = self.llm_pro if is_pro else self.llm_flash
            
            try:
                response = llm.invoke(prompt)
                
                # 정속 주행 Throttle 유지 (분당 호출 과부하 방지)
                time.sleep(6)
                return response.content
                
            except Exception as e:
                error_msg = str(e)
                
                # 429 자원 고갈 에러 패턴 매칭
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    
                    # 유형 1: 일일 요청 한도 완전 초과 (PerDay / Free Tier Requests Limit)
                    if "perday" in error_msg.lower() or "per_day" in error_msg.lower() or "free_tier_requests" in error_msg:
                        print(f"\n⚠️ [RPD 일일 한도 소진 감지] 모델 '{self.current_model_name}'의 하루 제공량이 끝났습니다.")
                        self._rotate_model()
                        print("▶️ 교체된 신규 엔진으로 작업을 즉시 재개합니다.\n")
                        continue  # 대기 없이 다음 탄창으로 즉시 다시 쏘기
                        
                    # 유형 2: 분당 호출 제한 과부하 (PerMinute / RPM)
                    else:
                        print(f"\n⏳ [RPM 분당 제한 감지] '{self.current_model_name}'의 분당 트래픽 한도 도달. 60초 대기 후 모델 유지한 채 재시도합니다...")
                        time.sleep(60)
                        continue
                else:
                    # 429 외의 기타 치명적인 예외 구조는 그대로 상위로 위임
                    raise e

    def _parse_skill_document(self, role_name: str) -> dict:
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
        skill_data = self._parse_skill_document(role_name)
        
        model_tier = skill_data["meta"].get("Model", "pro").lower()
        is_pro = (model_tier != "flash")
        
        if not is_pro:
            print(f"🔀 [Model Router] '{role_name}' 임무 ➔ [Lite/Flash] 모드 가동 (Active: {self.current_model_name})")
        else:
            print(f"🔀 [Model Router] '{role_name}' 임무 ➔ [Pro 심층] 모드 가동 (Active: {self.current_model_name})")
        
        prompt_template = skill_data["body"]
        prompt = f"다음 지침에 따라 임무를 수행하십시오.\n\n{prompt_template}\n\n[Context Data]\n{context_data}\n"
        
        if previous_output:
            prompt += f"\n[Previous Output (기존 산출물)]\n{previous_output}\n"
            if feedback:
                prompt += f"\n[Human Feedback (수정 지시사항)]\n사용자의 피드백을 엄격히 반영하여 기존 산출물을 수정(Delta Update) 하십시오:\n{feedback}\n"
        
        return self._safe_invoke(is_pro, prompt)

    def summarize_context(self, text: str) -> str:
        if not text:
            return ""
        prompt = f"다음 텍스트를 파이프라인의 다음 에이전트가 이해하기 쉽도록 핵심만 500자 이내의 마크다운 불릿 포인트로 요약하십시오:\n\n{text}"
        return self._safe_invoke(False, prompt)