import hashlib
import json
import re
import sqlite3
import os
from typing import Dict, Any, Optional

# 프롬프트 템플릿 외부 분리 (하드코딩 지양)
# 확장성과 유지보수 용이성을 위해 딕셔너리로 분리. 향후 YAML 등 외부 파일로 분리 가능.
PROMPT_TEMPLATES = {
    "xml_strict": (
        "<system_instruction>\n{skill_prompt}\n</system_instruction>\n"
        "<project_context>\n{context}\n</project_context>\n"
        "🚨 반드시 <files>, <file>, <replace-block> XML 태그만 사용하여 응답하십시오."
    )
}

class ContextEngine:
    """
    LLM 호출 전 프롬프트를 정규화하고, 캐싱을 통해 과금을 방어하는 중앙 두뇌 모듈.
    멀티 워커 환경에서 완벽하게 동작하도록 Zero-Config 파일 캐싱(SQLite)을 사용합니다.
    """
    def __init__(self, db_path: str = "factory_cache.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """멀티 워커 안전형 SQLite 파일 캐시 초기화 및 동시 쓰기(Lock) 방어"""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache "
                "(cache_key TEXT PRIMARY KEY, response TEXT)"
            )

    def _generate_cache_key(self, task_id: str, context_hash: str, model_name: str) -> str:
        """컨텍스트와 모델의 고유 조합을 해싱하여 식별자를 생성합니다."""
        raw_key = f"{task_id}_{context_hash}_{model_name}"
        return hashlib.md5(raw_key.encode('utf-8')).hexdigest()

    def _truncate_text(self, text: str, max_len: int) -> str:
        """물리적 토큰 압축 방어선 (Fallback Truncation)"""
        if not text:
            return ""
        if len(text) > max_len:
            half = max_len // 2
            return text[:half] + "\n\n...[System: Context Truncated for Token Limit]...\n\n" + text[-half:]
        return text

    def compress_and_format(self, state: Any, skill_prompt: str, max_chars: int = 15000) -> str:
        """
        JSON 파괴 버그 방지 로직 적용:
        직렬화(json.dumps)를 수행하기 전에 개별 텍스트 데이터를 먼저 절삭하여 포맷을 안전하게 보존합니다.
        """
        # 필드가 늘어났으므로 균등 분배 비율 조정
        field_max = max_chars // 6 

        # 🚨 [패치 1] Pydantic Object vs Dict 하이브리드 안전 추출기
        get_val = lambda key, default="": state.get(key, default) if isinstance(state, dict) else getattr(state, key, default)

        # 🚨 [패치 2] 신규 프로젝트 환각/복제 방지를 위해 project_name과 initial_idea 명시적 주입
        core_context = {
            "project_name": get_val("project_name", "Unknown Project"),
            "initial_idea": get_val("initial_idea", ""),
            "prd": self._truncate_text(get_val("prd_summary", ""), field_max),
            "architecture": self._truncate_text(get_val("architecture_summary", ""), field_max),
            "tech_spec": self._truncate_text(get_val("tech_spec_summary", ""), field_max),
            "target_task": get_val("current_sprint_task_id", "Unknown Task")
        }
        
        # 절삭이 모두 끝난 안전한 텍스트들을 마지막에 직렬화
        context_str = json.dumps(core_context, ensure_ascii=False, indent=2)

        formatted_prompt = PROMPT_TEMPLATES["xml_strict"].format(
            skill_prompt=skill_prompt,
            context=context_str
        )
        return formatted_prompt

    def check_cache(self, prompt: str, model: str) -> Optional[str]:
        """비용 최적화: 동일한 컨텍스트/프롬프트에 대한 중복 LLM 호출 방어"""
        key = self._generate_cache_key("current_task", hashlib.md5(prompt.encode('utf-8')).hexdigest(), model)
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.execute("SELECT response FROM llm_cache WHERE cache_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                print(f"⚡ [Cache Hit] SQLite 캐시에서 응답 반환 ({model})")
                return row[0]
        return None

    def save_cache(self, prompt: str, model: str, response: str):
        """성공한 LLM 응답을 영구 캐시에 저장"""
        key = self._generate_cache_key("current_task", hashlib.md5(prompt.encode('utf-8')).hexdigest(), model)
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (cache_key, response) VALUES (?, ?)", 
                (key, response)
            )

    def normalize_output(self, raw_output: str) -> str:
        """Zero-Chatter Policy: 모델의 잡담을 제거하고 순수 XML/JSON 블록만 추출"""
        clean_blocks = re.findall(r'<file\s[^>]*>.*?</file>', raw_output, re.DOTALL)
        if clean_blocks:
            return "\n".join(clean_blocks)
        return raw_output