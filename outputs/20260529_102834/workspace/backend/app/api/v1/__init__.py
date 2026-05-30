from fastapi import APIRouter
from app.api.v1.endpoints import session_router

# v1 API 라우터를 통합하는 메인 라우터
api_v1_router = APIRouter()
api_v1_router.include_router(session_router.router)