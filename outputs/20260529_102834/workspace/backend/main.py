from fastapi import FastAPI
from app.core.config import settings
from app.core.database import Base, engine
from app.api.v1 import api_v1_router
from app.exceptions.handlers import add_exception_handlers

# 데이터베이스 테이블 생성 (애플리케이션 시작 시)
# 실제 프로덕션 환경에서는 Alembic과 같은 마이그레이션 도구를 사용하는 것이 권장됩니다.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Backup & Recovery API",
    description="백업 세션, 항목 및 복구 로그를 관리하기 위한 API입니다.",
    version="1.0.0",
    docs_url="/docs", # OpenAPI 문서 (Swagger UI) 경로
    redoc_url="/redoc" # ReDoc 문서 경로
)

# API 라우터 등록
app.include_router(api_v1_router, prefix="/api/v1")

# 전역 예외 핸들러 등록
add_exception_handlers(app)

@app.get("/")
async def root():
    """
    루트 엔드포인트. API의 상태를 확인합니다.
    """
    return {"message": "Welcome to the Backup & Recovery API!"}

# 애플리케이션 실행 방법:
# uvicorn main:app --reload --port 8000