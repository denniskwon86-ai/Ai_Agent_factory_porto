"""제품 전체의 SQLite 저장소 장애 응답 계약.

도메인 검증 실패(4xx)와 저장소 판독 실패(503)는 사용자가 해야 할 일이 다르다. 개별 라우트가
``sqlite3`` 예외를 놓치면 FastAPI 기본 500으로 떨어지고, 어떤 화면은 이를 빈 목록처럼 접는다.
한 곳에서 503으로 통일하되 SQL·파일 경로·표 이름은 응답에 노출하지 않는다.
"""
import sqlite3

from fastapi import Request
from fastapi.responses import JSONResponse


STORAGE_UNAVAILABLE_MESSAGE = (
    "저장소 상태를 확인할 수 없습니다. 잠시 후 다시 시도하거나 시스템 관리자에게 문의하십시오."
)


async def sqlite_storage_unavailable(request: Request, exc: sqlite3.Error) -> JSONResponse:
    # 경로와 예외 종류만 서버 로그에 남긴다. ``str(exc)``에는 DB 경로·표·SQL이 들어갈 수 있다.
    print(f"[ERROR] SQLite storage unavailable: {request.url.path} ({type(exc).__name__})")
    return JSONResponse(status_code=503, content={"detail": STORAGE_UNAVAILABLE_MESSAGE})
