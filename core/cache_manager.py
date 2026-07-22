import os
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "llm_cache.db")

def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exact_cache (
                hash_key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

# 초기화 실행
_init_db()

def _get_exact_cache_sync(hash_key: str) -> Optional[str]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT response FROM exact_cache WHERE hash_key = ?", (hash_key,))
        row = cursor.fetchone()
        return row[0] if row else None

def _set_exact_cache_sync(hash_key: str, response: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO exact_cache (hash_key, response, created_at) VALUES (?, ?, ?)",
            (hash_key, response, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()

async def get_exact_cache(hash_key: str) -> Optional[str]:
    """주어진 SHA-256 해시 키에 대한 캐시된 응답을 비동기적으로 조회합니다."""
    return await asyncio.to_thread(_get_exact_cache_sync, hash_key)

async def set_exact_cache(hash_key: str, response: str):
    """주어진 SHA-256 해시 키와 응답을 캐시에 비동기적으로 저장합니다."""
    await asyncio.to_thread(_set_exact_cache_sync, hash_key, response)
