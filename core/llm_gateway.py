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
from pydantic import BaseModel, Field

from core.context_engine import ContextEngine
from state_models import ProjectState
import config

# --- Structured Output Schemas ---
class FileUpdate(BaseModel):
    file_path: str = Field(description="생성/수정할 파일의 상대 경로 (예: src/App.tsx, backend/main.py)")
    code: str = Field(description="여기에 전체 소스 코드를 작성 (부분 패치 불가, 반드시 전체 코드)")

class ArchitectureDecision(BaseModel):
    id: str = Field(description="ADR 아이디", default="")
    decision: str = Field(description="결정 내용", default="")
    reason: str = Field(description="결정 이유", default="")

class TechnicalDebt(BaseModel):
    id: str = Field(description="부채 아이디", default="")
    description: str = Field(description="부채 설명", default="")
    priority: int = Field(description="우선순위 (1~5)", default=3)

class FileIndexUpdate(BaseModel):
    change_summary: str = Field(description="변경 요약", default="")
    purpose: str = Field(description="파일 목적", default="")

class StateUpdates(BaseModel):
    architecture_decisions: list[ArchitectureDecision] = Field(default_factory=list)
    technical_debt: list[TechnicalDebt] = Field(default_factory=list)
    file_index_updates: dict[str, FileIndexUpdate] = Field(default_factory=dict)

class CodeOutput(BaseModel):
    files: list[FileUpdate] = Field(default_factory=list, description="수정/생성된 파일 목록")
    state_updates: StateUpdates = Field(default_factory=StateUpdates)
    error: str = Field(default="", description="오류 메시지")
# ---------------------------------


# 시스템 부팅 시 최우선으로 .env 파일의 환경변수를 메모리에 안전하게 로드합니다.
load_dotenv()


def _gemini_out(model: str) -> int:
    return config.MODEL_OUTPUT_LIMITS.get(model, config.DEFAULT_OUTPUT_LIMIT_GEMINI)


def _groq_out(model: str) -> int:
    return config.MODEL_OUTPUT_LIMITS.get(model, config.DEFAULT_OUTPUT_LIMIT_GROQ)


def _is_truncated(response: Any) -> bool:
    """LLM 응답이 출력 토큰 상한으로 잘렸는지 best-effort 판정.
    Gemini: finish_reason 'MAX_TOKENS' / Groq(OpenAI 호환): 'length'. 메타데이터 위치가
    제공자/버전마다 달라 여러 경로를 방어적으로 탐색하며, 불확실하면 False(오탐 방지)."""
    try:
        candidates = []
        meta = getattr(response, "response_metadata", None) or {}
        if isinstance(meta, dict):
            candidates.append(meta.get("finish_reason"))
            candidates.append(((meta.get("candidates") or [{}])[0] or {}).get("finish_reason"))
        rmeta = getattr(response, "additional_kwargs", None) or {}
        if isinstance(rmeta, dict):
            candidates.append(rmeta.get("finish_reason"))
        for c in candidates:
            if isinstance(c, str) and c.strip().upper() in ("MAX_TOKENS", "LENGTH"):
                return True
    except Exception:
        pass
    return False

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
            pro_fallbacks.append(ChatGoogleGenerativeAI(model=m, temperature=0.2, max_retries=0, max_output_tokens=_gemini_out(m)))
        # 최후의 보루: 타사(Groq) LLM 추가
        pro_fallbacks.append(ChatGroq(model=config.LLM_PRO_FALLBACK_LIST[1], temperature=0.2, max_retries=0, max_tokens=_groq_out(config.LLM_PRO_FALLBACK_LIST[1])))

        self.llm_pro = ChatGoogleGenerativeAI(
            model=pro_candidates[0], temperature=0.2, max_retries=0, max_output_tokens=_gemini_out(pro_candidates[0])
        ).with_fallbacks(pro_fallbacks)

        # [Track 1 - Code Mode] Structured Output 전용 Pro 체인
        pro_base = ChatGoogleGenerativeAI(model=pro_candidates[0], temperature=0.2, max_retries=0, max_output_tokens=_gemini_out(pro_candidates[0]))
        self.llm_pro_code = pro_base.with_structured_output(CodeOutput).with_fallbacks([f.with_structured_output(CodeOutput) for f in pro_fallbacks])

        # 4. [Track 2] Flash 모델 체인 조립 (고속 단순 작업용)
        flash_candidates = [config.LLM_FLASH_FALLBACK_LIST[0]]
        for m in available_gemini_models:
            if 'flash' in m.lower() and m not in flash_candidates:
                flash_candidates.append(m)
                
        flash_fallbacks = []
        for m in flash_candidates[1:]:
            flash_fallbacks.append(ChatGoogleGenerativeAI(model=m, temperature=0.1, max_retries=0, max_output_tokens=_gemini_out(m)))
        flash_fallbacks.append(ChatGroq(model=config.LLM_FLASH_FALLBACK_LIST[1], temperature=0.1, max_retries=0, max_tokens=_groq_out(config.LLM_FLASH_FALLBACK_LIST[1])))

        self.llm_flash = ChatGoogleGenerativeAI(
            model=flash_candidates[0], temperature=0.1, max_retries=0, max_output_tokens=_gemini_out(flash_candidates[0])
        ).with_fallbacks(flash_fallbacks)

        # [Track 2 - Code Mode] Structured Output 전용 Flash 체인
        flash_base = ChatGoogleGenerativeAI(model=flash_candidates[0], temperature=0.1, max_retries=0, max_output_tokens=_gemini_out(flash_candidates[0]))
        self.llm_flash_code = flash_base.with_structured_output(CodeOutput).with_fallbacks([f.with_structured_output(CodeOutput) for f in flash_fallbacks])

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
                       output_mode: str = "code", light: bool = False, full_file_exts=None) -> str:
        """output_mode: 'code'(파일 스키마 강제 JSON) | 'json'(자유 스키마 JSON) | 'document'(자유 서술 문서).
        light=True이면 경량 컨텍스트(요약만)로 호출하여 토큰·429를 절감한다.
        full_file_exts: 개발자가 전체 재출력할 소유 파일 확장자(예: (".tsx",".ts")) — 해당 파일은
        절단 없이 전체 주입되어 멀티태스크 기능 누락(회귀)을 차단한다(증분 codegen)."""
        state_obj = ProjectState.model_validate(state) if isinstance(state, dict) else state

        if output_mode == "code":
            llm = self.llm_pro_code if is_heavy else self.llm_flash_code
        else:
            llm = self.llm_pro if is_heavy else self.llm_flash
            
        logical_model_name = "pro_router" if is_heavy else "flash_router"

        core_context = ContextEngine.build_core_context(state_obj, light=light, full_file_exts=full_file_exts)

        if output_mode == "code":
            strict_json_rule = ContextEngine.get_strict_json_instruction()
            final_prompt = f"{core_context}\n\n[요청 지시사항]:\n{skill_prompt}\n\n{strict_json_rule}"
            system_content = "You are a V5.0 AI Software Factory Agent. Output your response strictly conforming to the requested schema. Do not include markdown blocks."
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
            
            if output_mode == "code":
                # response가 CodeOutput (Pydantic 모델)이므로 바로 JSON 변환 후 반환
                # Note: structured_output 모드에서는 _is_truncated 체크가 어려우나 파싱 실패 시 예외로 넘어감
                return response.model_dump_json(by_alias=True)
                
            # 🚨 Gemini Flash 멀티파트(list/dict {type,text}) 응답을 순수 텍스트로 정규화
            raw_output = self._stringify(response.content)

            if output_mode == "code" and _is_truncated(response):
                print("🚨 [LLM Gateway] 응답이 출력 토큰 상한에서 절단됨(MAX_TOKENS). 부분 코드 폐기 → 빌드 실패 처리.")
                return json.dumps({"files": [], "error": "OUTPUT_TRUNCATED"}, ensure_ascii=False)

        except Exception as e:
            error_str = str(e)
            # 2. 🚨 [크로스 티어 우회] Pro 체인이 429로 터지면 즉시 Flash 티어로 수직 강하
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if is_heavy:
                    print(f"⚠️ [LLM Gateway] Pro 계열 모델 및 Groq 체인 모두 할당량 초과(429) 또는 한도 도달.")
                    print(f"🔄 [LLM Gateway] 고속(Flash) 티어로 수직 강하(Cross-Tier Fallback) 하여 임무를 속행합니다!")
                    return await self.aexecute(state, skill_prompt, is_heavy=False, retry_count=retry_count + 1,
                                               output_mode=output_mode, light=light, full_file_exts=full_file_exts)
                else:
                    if retry_count < 3:
                        print(f"🚨 [LLM Gateway] Flash 체인마저 할당량 초과. 15초 대기 후 재시도 (시도 {retry_count+1}/3)...")
                        await asyncio.sleep(15)
                        return await self.aexecute(state, skill_prompt, is_heavy=False, retry_count=retry_count + 1,
                                                   output_mode=output_mode, light=light, full_file_exts=full_file_exts)
                    else:
                        print("💥 [LLM Gateway] 치명적 에러: 가용한 모든 LLM API의 할당량이 고갈되었습니다.")
                        return json.dumps({"files": [], "error": "LLM API LIMIT ERROR"})
            else:
                print(f"❌ [LLM Gateway] 예측 불가능한 네트워크 에러 발생: {error_str}")
                if is_heavy and retry_count == 0:
                    print("🔄 [LLM Gateway] 알 수 없는 오류 복구를 위해 Flash 체인으로 긴급 우회합니다.")
                    return await self.aexecute(state, skill_prompt, is_heavy=False, retry_count=1,
                                               output_mode=output_mode, light=light, full_file_exts=full_file_exts)
                return json.dumps({"files": [], "error": f"LLM UNKNOWN ERROR: {error_str}"})

        # 3. 문서 모드는 원문 그대로, 그 외는 JSON 정제 엔진 통과
        if output_mode == "document":
            return self._stringify(raw_output).strip()
        return self._repair_and_parse_json(raw_output)

    @staticmethod
    def _escape_raw_control_chars(text: str) -> str:
        """JSON 문자열 리터럴 내부의 escape 안 된 제어문자(리터럴 개행/CR/탭 등)를 escape.
        LLM이 code 필드에 raw 개행을 그대로 넣어 'Invalid control character' 로 파싱이 통째로
        깨지는(=파일 전량 폐기) 가장 흔한 실패를 보정. 문자열 '밖'의 구조는 건드리지 않는다."""
        out = []
        in_string = False
        escaped = False
        for ch in text:
            if in_string:
                if escaped:
                    out.append(ch); escaped = False; continue
                if ch == "\\":
                    out.append(ch); escaped = True; continue
                if ch == '"':
                    out.append(ch); in_string = False; continue
                if ch == "\n":
                    out.append("\\n"); continue
                if ch == "\r":
                    out.append("\\r"); continue
                if ch == "\t":
                    out.append("\\t"); continue
                if ord(ch) < 0x20:
                    out.append("\\u%04x" % ord(ch)); continue
                out.append(ch)
            else:
                if ch == '"':
                    in_string = True
                out.append(ch)
        return "".join(out)

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

        # 3. JSON 유효성 검증 — 단계적 보정 후보를 순서대로 시도(가장 보존적인 것부터):
        #    원본 → 트레일링콤마 제거 → 제어문자 escape → (제어문자 escape + 트레일링콤마 제거)
        no_trailing = re.sub(r',(\s*[}\]])', r'\1', text)
        escaped = self._escape_raw_control_chars(text)
        escaped_no_trailing = re.sub(r',(\s*[}\]])', r'\1', escaped)
        for candidate in (text, no_trailing, escaped, escaped_no_trailing):
            try:
                parsed = json.loads(candidate)
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                continue
        print("⚠️ [JSON Repair] 디코딩 실패. 원시 텍스트를 반환합니다.")
        return text


class _LazyGateway:
    """LLMGateway 지연 초기화 프록시.
    import/compile 시점에 SDK·모델목록 조회(네트워크)를 트리거하지 않고, 첫 실제 호출 때 1회 생성한다.
    공개 메서드(aexecute)를 명시적으로 위임 정의한다 — __getattr__ 로 위임하면 LangGraph compile 의
    노드 클로저 정적 분석(get_function_nonlocals 의 getattr)이 프록시 생성을 유발하므로,
    getattr 가 메서드 객체만 돌려주고 실제 호출 시에만 생성되도록 한다."""
    _inst = None

    @classmethod
    def _instance(cls):
        if cls._inst is None:
            cls._inst = LLMGateway()
        return cls._inst

    async def aexecute(self, *args, **kwargs):
        return await type(self)._instance().aexecute(*args, **kwargs)


gateway = _LazyGateway()