# -*- coding: utf-8 -*-
"""운영 DB를 열지 않고 저장소 장애의 제품 응답 계약을 검증한다."""
import asyncio
import json
import sqlite3
from pathlib import Path

from starlette.requests import Request

from api.storage_errors import STORAGE_UNAVAILABLE_MESSAGE, sqlite_storage_unavailable


ROOT = Path(__file__).resolve().parents[1]


def _request(path: str = "/api/v1/external/indicators") -> Request:
    return Request({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "headers": [],
        "client": ("test", 1234), "server": ("test", 80),
    })


def test_sqlite_판독실패는_빈목록이나_500이_아니라_503이다():
    response = asyncio.run(sqlite_storage_unavailable(
        _request(), sqlite3.OperationalError("no such table: confidential_table")))

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body == {"detail": STORAGE_UNAVAILABLE_MESSAGE}
    assert "confidential_table" not in response.body.decode("utf-8")


def test_SQLite_장애계약은_FastAPI_앱_전체에_등록된다():
    src = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "app.add_exception_handler(sqlite3.Error, sqlite_storage_unavailable)" in src
    assert "str(exc)" not in (ROOT / "api/storage_errors.py").read_text(encoding="utf-8").split(
        "return JSONResponse", 1)[1]
