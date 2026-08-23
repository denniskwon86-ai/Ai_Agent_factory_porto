import os
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Optional

#: ⚠️ 뿌리를 **직접 조립하지 않는다.** `core/paths.py` 가 단일 기준점이고, 그 머리말이
#:   「모두 여기서 같은 답을 얻는다」고 못박고 있다. 여기만 자기 경로를 만들고 있어서
#:   시연 서버가 저장소를 전부 `demo_data/` 로 돌려도 **이 파일만 운영 `data/` 를 열었다**
#:   (2026-08-23 실측 — 격리 차단기가 물었다).
#: ★ 함수로 읽는다. 모듈 적재 시점에 값을 얼려 버리면 뿌리를 바꿔도 따라오지 않는다.
def _db_path() -> str:
    from core.paths import data_path
    return data_path("llm_cache.db")


def _connect() -> sqlite3.Connection:
    """캐시 저장소를 연다. **열 때마다 표를 보장한다.**

    ## ⚠️⚠️ [2026-08-23 실측] `_init_db()` 를 import 시점에 한 번만 부르면 안 된다

    종전에는 모듈을 적재하면서 표를 만들고 끝이었다. 그러면 **뿌리가 바뀐 뒤에는 표가
    없는 DB 를 연다** — 시험이 `paths.DATA_DIR` 을 임시 폴더로 돌리자 곧바로
    `no such table: exact_cache` 로 터졌다(회귀 1,151건째에서 멈췄다).

    ★ 「한 번만 만들면 된다」는 **뿌리가 절대 안 바뀐다**는 가정 위에 서 있었고, 그
      가정은 격리를 넣는 순간 깨진다. 열 때 보장하면 뿌리가 어디로 가든 따라온다.
    ⚠️ import 시점에 파일을 만들지도 않는다 — 그것 자체가 이 저장소가 금지한 부작용이다."""
    path = _db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exact_cache (
            hash_key TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    return conn


def _get_exact_cache_sync(hash_key: str) -> Optional[str]:
    with _connect() as conn:
        cursor = conn.execute("SELECT response FROM exact_cache WHERE hash_key = ?", (hash_key,))
        row = cursor.fetchone()
        return row[0] if row else None

def _set_exact_cache_sync(hash_key: str, response: str):
    with _connect() as conn:
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
