import os
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from core.context_engine import ContextEngine
from state_models import ProjectState

class LLMGateway:
    """
    LLM 호출과 자원 최적화(Task-Based Routing)를 전담하는 비동기 게이트웨이.
    LangChain을 통해 모델과 통신하며, ContextEngine의 캐시 및 절삭 로직을 통과시킵니다.
    """
    def __init__(self):
        self.context_engine = ContextEngine()
        
        # 모델 불가지성 및 자원 최적화를 위한 듀얼 엔진 세팅 (Flash vs Pro)
        # OMEGA ERP V3.2 등 고난도 도메인 지식은 Pro가, 단순 문법 처리는 Flash가 전담
        self.llm_pro = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)
        self.llm_flash = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.1)

    async def aexecute(self, state: ProjectState, skill_prompt: str, is_heavy: bool = True) -> str:
        """비동기 LLM 호출기 (캐시 방어 및 에러 핸들링 포함)"""
        llm = self.llm_pro if is_heavy else self.llm_flash
        model_name = "gemini-2.5-pro" if is_heavy else "gemini-2.5-flash-lite"
        
        # 1. 템플릿 포맷팅 및 토큰 압축 (JSON 파괴 방어선 통과)
        formatted_prompt = self.context_engine.compress_and_format(state, skill_prompt)
        
        # 2. Semantic Cache 히트 확인 (과금 및 무한 루프 낭비 방어)
        cached_response = self.context_engine.check_cache(formatted_prompt, model_name)
        if cached_response:
            return cached_response

        # 3. 비동기 추론 (ainvoke)
        messages = [
            SystemMessage(content="You are a V5.0 AI Software Factory Agent. Strictly output in requested format."),
            HumanMessage(content=formatted_prompt)
        ]
        
        response = await llm.ainvoke(messages)
        raw_output = response.content

        # 4. Zero-Chatter 정규화 (잡담 제거) 및 성공 캐시 저장
        normalized_output = self.context_engine.normalize_output(raw_output)
        self.context_engine.save_cache(formatted_prompt, model_name, normalized_output)

        return normalized_output

gateway = LLMGateway()