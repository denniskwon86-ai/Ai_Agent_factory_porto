import pytest
import os
import sqlite3
import hashlib
import asyncio
from core import cache_manager

def test_exact_hash_cache():
    async def run_test():
        # 1. 해시 준비
        test_str = "system_content + final_prompt + output_mode"
        prompt_hash = hashlib.sha256(test_str.encode("utf-8")).hexdigest()
        
        # 2. 초기 상태 (미스) - 이전에 남은 게 있을 수 있으니 다른 키를 쓴다
        unique_hash = hashlib.sha256(os.urandom(16)).hexdigest()
        miss_res = await cache_manager.get_exact_cache(unique_hash)
        assert miss_res is None, "초기에는 캐시가 비어 있어야 합니다."
        
        # 3. 값 저장
        mock_response = '{"decision": "PASS", "feedback": "Test Cache HIT!"}'
        await cache_manager.set_exact_cache(unique_hash, mock_response)
        
        # 4. 저장된 값 검증 (히트)
        hit_res = await cache_manager.get_exact_cache(unique_hash)
        assert hit_res == mock_response, "캐시된 응답이 원본과 정확히 일치해야 합니다."
        
    asyncio.run(run_test())
