import os
import json
import re
import asyncio
from typing import Any
from google import genai
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from core.context_engine import ContextEngine
from state_models import ProjectState
import config

# 시스템 부팅 시 최우선으로 .env 파일의 환경변수를 메모리에 안전하게 로드합니다.
load_dotenv()

# 모든 LLM 호출에 공통 적용되는 언어 지침 — Gemini의 한자(漢字) 혼입 미관 이슈 억제.
_LANG_DIRECTIVE = (
    " 모든 자연어 텍스트는 한국어(한글)로만 작성하고 한자(漢字)는 절대 사용하지 마라"
    " (예: '滿'이 아니라 '가득', '完了'가 아니라 '완료'). 코드 식별자·기술용어의 영문 표기만 허용한다."
)

class LLMGateway:
    """
    LLM 호출과 자원 최적화를 전담하는 비동기 게이트웨이.
    최신 google.genai SDK 기반의 동적 탐색 및 Groq(Llama3) Fallback 무중단 라우팅 메커니즘을 포함합니다.
    """
    def __init__(self):
        # 1. API 키 로드 및 최신 genai 클라이언트 초기화
        api_key = os.environ.get("GOOGLE_API_KEY")
        client = None
        if api_key:
            client = genai.Client(api_key=api_key)

        # 2. 동적 가용 모델 탐색 (최신 SDK 규격 'supported_actions' 적용)
        available_gemini_models = []
        if client:
            try:
                for m in client.models.list():
                    if getattr(m, 'supported_actions', None) and 'generateContent' in m.supported_actions:
                        model_name = m.name.replace('models/', '')
                        available_gemini_models.append(model_name)
            except Exception as e:
                print(f"⚠️ [Gateway] 최신 Gemini SDK 모델 동적 검색 실패 (기본값으로 진행): {e}")

        # 3. [Track 1] Pro 모델 체인 조립 (고난도 추론용)
        pro_candidates = [config.LLM_PRO_FALLBACK_LIST[0]]
        for m in available_gemini_models:
            if 'pro' in m.lower() and m not in pro_candidates:
                pro_candidates.append(m)
        
        pro_fallbacks = []
        for m in pro_candidates[1:]:
            pro_fallbacks.append(ChatGoogleGenerativeAI(model=m, temperature=0.2, max_retries=0))
        # 최후의 보루: 타사(Groq) LLM 추가
        pro_fallbacks.append(ChatGroq(model=config.LLM_PRO_FALLBACK_LIST[1], temperature=0.2, max_retries=0))
        
        self.llm_pro = ChatGoogleGenerativeAI(
            model=pro_candidates[0], temperature=0.2, max_retries=0
        ).with_fallbacks(pro_fallbacks)

        # 4. [Track 2] Flash 모델 체인 조립 (고속 단순 작업용)
        flash_candidates = [config.LLM_FLASH_FALLBACK_LIST[0]]
        for m in available_gemini_models:
            if 'flash' in m.lower() and m not in flash_candidates:
                flash_candidates.append(m)
                
        flash_fallbacks = []
        for m in flash_candidates[1:]:
            flash_fallbacks.append(ChatGoogleGenerativeAI(model=m, temperature=0.1, max_retries=0))
        flash_fallbacks.append(ChatGroq(model=config.LLM_FLASH_FALLBACK_LIST[1], temperature=0.1, max_retries=0))
        
        self.llm_flash = ChatGoogleGenerativeAI(
            model=flash_candidates[0], temperature=0.1, max_retries=0
        ).with_fallbacks(flash_fallbacks)

        # 콘솔에 완성된 라우팅 체인 구조 출력
        print(f"\n[OK] [LLM Gateway] 다중 계층 동적 라우팅 엔진 가동 완료 (최신 SDK 적용)")
        print(f"   [Pro Tier] {' -> '.join(pro_candidates)} -> Groq({config.LLM_PRO_FALLBACK_LIST[1]})")
        print(f"   [Flash Tier] {' -> '.join(flash_candidates)} -> Groq({config.LLM_FLASH_FALLBACK_LIST[1]})\n")

    @staticmethod
    def _stringify(raw: Any) -> str:
        # Gemini Flash 등의 멀티파트 응답(list/dict of {type,text})에서 실제 text만 추출
        if raw is None:
            return ""
        if isinstance(raw, list):
            return "\n".join([
                str(c.get("text", c.get("content", ""))) if isinstance(c, dict) else str(c)
                for c in raw
            ])
        if isinstance(raw, dict):
            v = raw.get("text", raw.get("content"))
            return str(v) if v is not None else str(raw)
        return str(raw)

    async def aexecute(self, state: Any, skill_prompt: str, is_heavy: bool = True, retry_count: int = 0,
                       output_mode: str = "code", light: bool = False) -> str:
        """output_mode: 'code'(파일 스키마 강제 JSON) | 'json'(자유 스키마 JSON) | 'document'(자유 서술 문서).
        light=True이면 경량 컨텍스트(요약만)로 호출하여 토큰·429를 절감한다."""
        state_obj = ProjectState.model_validate(state) if isinstance(state, dict) else state

        llm = self.llm_pro if is_heavy else self.llm_flash
        logical_model_name = "pro_router" if is_heavy else "flash_router"

        core_context = ContextEngine.build_core_context(state_obj, light=light)

        if output_mode == "code":
            strict_json_rule = ContextEngine.get_strict_json_instruction()
            final_prompt = f"{core_context}\n\n[요청 지시사항]:\n{skill_prompt}\n\n{strict_json_rule}"
            system_content = "You are a V5.0 AI Software Factory Agent. Strictly output in valid JSON format only."
        elif output_mode == "json":
            final_prompt = f"{core_context}\n\n[요청 지시사항]:\n{skill_prompt}"
            system_content = "You are a V5.0 AI Software Factory Agent. Output ONLY a single valid JSON object exactly as instructed."
        else:  # document
            final_prompt = f"{core_context}\n\n[요청 지시사항]:\n{skill_prompt}"
            system_content = "You are a V5.0 AI Software Factory Agent. Produce a thorough, well-structured document exactly as instructed. Do NOT wrap it in JSON or code fences."

        system_content += _LANG_DIRECTIVE

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=final_prompt)
        ]

        print(f"📡 [LLM Gateway] LangChain 라우터 체인 실행 중... ({logical_model_name}/{output_mode})")

        try:
            # 1. 일차적으로 LangChain의 with_fallbacks 체인 호출
            response = await llm.ainvoke(messages)
            # 🚨 Gemini Flash 멀티파트(list/dict {type,text}) 응답을 순수 텍스트로 정규화
            #    (이걸 빼면 str()로 뭉개져 JSON 파싱 실패 → 코드 미생성 버그 발생)
            raw_output = self._stringify(response.content)

        except Exception as e:
            error_str = str(e)
            # 2. 🚨 [크로스 티어 우회] Pro 체인이 429로 터지면 즉시 Flash 티어로 수직 강하
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if is_heavy:
                    print(f"⚠️ [LLM Gateway] Pro 계열 모델 및 Groq 체인 모두 할당량 초과(429) 또는 한도 도달.")
                    print(f"🔄 [LLM Gateway] 고속(Flash) 티어로 수직 강하(Cross-Tier Fallback) 하여 임무를 속행합니다!")
                    return await self.aexecute(state, skill_prompt, is_heavy=False, retry_count=retry_count + 1,
                                               output_mode=output_mode, light=light)
                else:
                    if retry_count < 3:
                        print(f"🚨 [LLM Gateway] Flash 체인마저 할당량 초과. 15초 대기 후 재시도 (시도 {retry_count+1}/3)...")
                        await asyncio.sleep(15)
                        return await self.aexecute(state, skill_prompt, is_heavy=False, retry_count=retry_count + 1,
                                                   output_mode=output_mode, light=light)
                    else:
                        print("💥 [LLM Gateway] 치명적 에러: 가용한 모든 LLM API의 할당량이 고갈되었습니다.")
                        return json.dumps({"files": [], "error": "LLM API LIMIT ERROR"})
            else:
                print(f"❌ [LLM Gateway] 예측 불가능한 네트워크 에러 발생: {error_str}")
                if is_heavy and retry_count == 0:
                    print("🔄 [LLM Gateway] 알 수 없는 오류 복구를 위해 Flash 체인으로 긴급 우회합니다.")
                    return await self.aexecute(state, skill_prompt, is_heavy=False, retry_count=1,
                                               output_mode=output_mode, light=light)
                return json.dumps({"files": [], "error": f"LLM UNKNOWN ERROR: {error_str}"})

        # 3. 문서 모드는 원문 그대로, 그 외는 JSON 정제 엔진 통과
        if output_mode == "document":
            return self._stringify(raw_output).strip()
        return self._repair_and_parse_json(raw_output)

    def _repair_and_parse_json(self, raw_text: str) -> str:
        text = str(raw_text).strip()
        
        # 1. 마크다운 백틱 제거
        md_match = re.search(r'\x60\x60\x60(?:json)?\s*(\{[\s\S]*?\})\s*\x60\x60\x60', text)
        if md_match:
            text = md_match.group(1)
        else:
            bracket_match = re.search(r'(\{[\s\S]*\})', text)
            if bracket_match:
                text = bracket_match.group(1)
                
        # 2. 잔존하는 XML 찌꺼기 제거
        text = re.sub(r'</?file[^>]*>', '', text)
        text = re.sub(r'</?files>', '', text)
        
        # 3. JSON 문법 유효성 검증 (실패 시 트레일링 콤마 제거 후 1회 재시도)
        for candidate in (text, re.sub(r',(\s*[}\]])', r'\1', text)):
            try:
                parsed = json.loads(candidate)
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                continue
        print("⚠️ [JSON Repair] 디코딩 실패. 원시 텍스트를 반환합니다.")
        return text

gateway = LLMGateway()