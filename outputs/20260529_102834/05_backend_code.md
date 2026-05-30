백엔드 엔지니어로서 주어진 기술 명세서와 데이터베이스 스키마를 바탕으로 FastAPI 기반의 서버 사이드 비즈니스 로직과 RESTful API를 구현합니다. 이전 빌드 오류 피드백 중 `pydantic-core` 관련 에러는 Python 환경의 링커 문제로, 코드 자체의 문제는 아니므로 Pydantic v2 사용을 유지하며 환경 설정이 올바르게 되어있음을 가정합니다. Node.js 관련 에러는 FastAPI 백엔드 구현과는 무관하므로 무시합니다.

아래는 요청된 구조와 엄격한 XML 출력 표준에 맞춰 생성된 파일들입니다.

---

<file path="backend/requirements.txt">
fastapi
uvicorn
sqlalchemy
pydantic>=2.0.0
pydantic-settings
python-dotenv
</file>

<file path="backend/.env">
NODE_ENV=development
PORT=8000
DATABASE_URL=sqlite:///./sql_app.db
</file>

# 1. 환경 설정 및 데이터베이스 초기화 (Config / Database)

<file path="backend/app/core/config.py">
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    """
    환경 변수를 관리하는 설정 클래스입니다.
    .env 파일에서 환경 변수를 로드합니다.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    NODE_ENV: str = "development"
    PORT: int = 8000
    DATABASE_URL: str = "sqlite:///./sql_app.db" # SQLite 데이터베이스 URL

settings = Settings()
</file>

<file path="backend/app/core/database.py">
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 데이터베이스 연결 URL 설정
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy 엔진 생성
# SQLite는 기본적으로 단일 스레드에서만 작동하므로, FastAPI와 같은 멀티스레드 환경에서는
# "check_same_thread": False 옵션을 추가해야 합니다.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 데이터베이스 세션 생성기
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모든 ORM 모델의 기반 클래스
Base = declarative_base()

def get_db():
    """
    의존성 주입을 위한 데이터베이스 세션 제공 함수입니다.
    요청마다 새로운 세션을 생성하고, 요청이 완료되면 세션을 닫습니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
</file>

# 2. 데이터 모델 및 스키마 (Models / Schemas)

<file path="backend/app/exceptions/custom_exceptions.py">
from fastapi import HTTPException, status

class NotFoundException(HTTPException):
    """
    리소스를 찾을 수 없을 때 발생하는 사용자 정의 예외입니다 (HTTP 404).
    """
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class ConflictException(HTTPException):
    """
    리소스 충돌이 발생했을 때 발생하는 사용자 정의 예외입니다 (HTTP 409).
    예: 고유해야 하는 이름이 이미 존재할 때.
    """
    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)

class BadRequestException(HTTPException):
    """
    잘못된 요청이 발생했을 때 발생하는 사용자 정의 예외입니다 (HTTP 400).
    """
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

# 필요에 따라 다른 사용자 정의 예외를 추가할 수 있습니다.
</file>

<file path="backend/app/schemas/common.py">
from pydantic import BaseModel, Field

class ErrorResponse(BaseModel):
    """
    API 에러 응답의 표준 스키마입니다.
    """
    detail: str = Field(..., example="Resource not found")
</file>

<file path="backend/app/models/session_model.py">
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class DBSession(Base):
    """
    `sessions` 테이블과 매핑되는 ORM 모델입니다.
    백업/복구 세션의 기본 정보를 저장합니다.
    """
    __tablename__ = "sessions"

    session_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    storage_path = Column(String, nullable=False)
    compression = Column(Boolean, default=False)
    encryption = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계 정의: Sessions 1:N SessionItems, Sessions 1:N RecoveryLogs
    items = relationship("DBSessionItem", back_populates="session", cascade="all, delete-orphan")
    recovery_logs = relationship("DBRecoveryLog", back_populates="session", cascade="all, delete-orphan")

class DBSessionItem(Base):
    """
    `session_items` 테이블과 매핑되는 ORM 모델입니다.
    각 세션에 포함된 개별 백업/복구 항목(파일 또는 디렉토리)을 저장합니다.
    """
    __tablename__ = "session_items"

    session_item_id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.session_id"), nullable=False)
    item_path = Column(String, nullable=False)
    item_type = Column(String, nullable=False) # 예: 'file', 'directory'

    # 관계 정의: SessionItems N:1 Sessions
    session = relationship("DBSession", back_populates="items")

class DBRecoveryLog(Base):
    """
    `recovery_logs` 테이블과 매핑되는 ORM 모델입니다.
    각 세션에 대한 복구/백업 작업의 로그를 저장합니다.
    """
    __tablename__ = "recovery_logs"

    log_id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.session_id"), nullable=False)
    item_path = Column(String, nullable=False)
    action_type = Column(String, nullable=False) # 예: 'backup', 'restore'
    status = Column(String, nullable=False) # 예: 'pending', 'in_progress', 'completed', 'failed'
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)

    # 관계 정의: RecoveryLogs N:1 Sessions
    session = relationship("DBSession", back_populates="recovery_logs")
</file>

<file path="backend/app/schemas/session.py">
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# --- SessionItem Schemas ---
class SessionItemBase(BaseModel):
    """세션 항목의 기본 스키마."""
    item_path: str = Field(..., example="/path/to/file.txt", description="백업/복구 대상 항목의 경로")
    item_type: str = Field(..., example="file", pattern="^(file|directory)$", description="항목의 타입 (file 또는 directory)")

class SessionItemCreate(SessionItemBase):
    """세션 항목 생성 요청 스키마."""
    pass

class SessionItemResponse(SessionItemBase):
    """세션 항목 응답 스키마."""
    session_item_id: int = Field(..., example=1, description="세션 항목의 고유 ID")
    session_id: int = Field(..., example=101, description="연결된 세션의 ID")

    class Config:
        from_attributes = True # Pydantic v2에서 ORM 모델 매핑을 위해 필요

# --- RecoveryLog Schemas ---
class RecoveryLogBase(BaseModel):
    """복구 로그의 기본 스키마."""
    item_path: str = Field(..., example="/path/to/recovered_file.txt", description="로그와 관련된 항목의 경로")
    action_type: str = Field(..., example="backup", pattern="^(backup|restore)$", description="수행된 작업의 타입 (backup 또는 restore)")
    status: str = Field(..., example="completed", pattern="^(pending|in_progress|completed|failed)$", description="작업의 현재 상태")
    started_at: Optional[datetime] = Field(None, example="2023-10-27T10:00:00Z", description="작업 시작 시간 (ISO 8601 형식)")
    completed_at: Optional[datetime] = Field(None, example="2023-10-27T10:05:00Z", description="작업 완료 시간 (ISO 8601 형식)")
    error_message: Optional[str] = Field(None, example="Permission denied during backup", description="오류 발생 시 오류 메시지")

class RecoveryLogCreate(RecoveryLogBase):
    """복구 로그 생성 요청 스키마."""
    pass

class RecoveryLogResponse(RecoveryLogBase):
    """복구 로그 응답 스키마."""
    log_id: int = Field(..., example=1, description="복구 로그의 고유 ID")
    session_id: int = Field(..., example=101, description="연결된 세션의 ID")
    started_at: datetime # DB에서 기본값 설정되므로 응답에서는 필수로 간주

    class Config:
        from_attributes = True # Pydantic v2에서 ORM 모델 매핑을 위해 필요

# --- Session Schemas ---
class SessionBase(BaseModel):
    """세션의 기본 스키마."""
    name: str = Field(..., min_length=1, max_length=100, example="My Important Backup", description="세션의 고유 이름")
    storage_path: str = Field(..., example="/mnt/backup_drive/backups", description="백업 데이터가 저장될 경로")
    compression: bool = Field(False, example=True, description="데이터 압축 여부")
    encryption: bool = Field(False, example=False, description="데이터 암호화 여부")

class SessionCreate(SessionBase):
    """세션 생성 요청 스키마."""
    items: Optional[List[SessionItemCreate]] = Field(None, description="세션 생성 시 함께 추가할 항목 목록")

class SessionUpdate(BaseModel):
    """세션 업데이트 요청 스키마."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, example="My Updated Backup", description="업데이트할 세션 이름")
    storage_path: Optional[str] = Field(None, example="/mnt/backup_drive/new_backups", description="업데이트할 저장 경로")
    compression: Optional[bool] = None
    encryption: Optional[bool] = None

class SessionResponse(SessionBase):
    """세션 응답 스키마 (상세 정보 포함)."""
    session_id: int = Field(..., example=101, description="세션의 고유 ID")
    created_at: datetime = Field(..., example="2023-10-27T09:00:00Z", description="세션 생성 시간 (ISO 8601 형식)")
    updated_at: Optional[datetime] = Field(None, example="2023-10-27T11:30:00Z", description="세션 마지막 업데이트 시간 (ISO 8601 형식)")
    items: List[SessionItemResponse] = Field([], description="세션에 포함된 항목 목록")
    recovery_logs: List[RecoveryLogResponse] = Field([], description="세션과 관련된 복구 로그 목록")

    class Config:
        from_attributes = True # Pydantic v2에서 ORM 모델 매핑을 위해 필요

class SessionListResponse(BaseModel):
    """세션 목록 응답 스키마."""
    sessions: List[SessionResponse] = Field(..., description="세션 목록")
    total: int = Field(..., example=5, description="총 세션 수")
</file>

# 3. 비즈니스 로직 및 API 엔드포인트 (Services / Routers)

<file path="backend/app/services/session_service.py">
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime

from app.models.session_model import DBSession, DBSessionItem, DBRecoveryLog
from app.schemas.session import (
    SessionCreate, SessionUpdate, SessionItemCreate, RecoveryLogCreate
)
from app.exceptions.custom_exceptions import NotFoundException, ConflictException, BadRequestException

class SessionService:
    """
    세션 관련 비즈니스 로직을 처리하는 서비스 레이어입니다.
    데이터베이스와의 상호작용 및 예외 처리를 담당합니다.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_all_sessions(self) -> List[DBSession]:
        """
        모든 세션 목록을 조회합니다.
        """
        return self.db.query(DBSession).all()

    def get_session_by_id(self, session_id: int) -> DBSession:
        """
        특정 ID의 세션을 조회합니다.
        세션이 없으면 NotFoundException을 발생시킵니다.
        """
        session = self.db.query(DBSession).filter(DBSession.session_id == session_id).first()
        if not session:
            raise NotFoundException(detail=f"Session with ID {session_id} not found.")
        return session

    def create_session(self, session_data: SessionCreate) -> DBSession:
        """
        새로운 세션을 생성합니다.
        동일한 이름의 세션이 이미 존재하면 ConflictException을 발생시킵니다.
        """
        existing_session = self.db.query(DBSession).filter(DBSession.name == session_data.name).first()
        if existing_session:
            raise ConflictException(detail=f"Session with name '{session_data.name}' already exists.")

        db_session = DBSession(
            name=session_data.name,
            storage_path=session_data.storage_path,
            compression=session_data.compression,
            encryption=session_data.encryption
        )
        self.db.add(db_session)
        try:
            self.db.commit()
            self.db.refresh(db_session)
        except IntegrityError:
            self.db.rollback()
            raise ConflictException(detail=f"Session with name '{session_data.name}' already exists.")

        # If items are provided, add them to the session
        if session_data.items:
            for item_data in session_data.items:
                db_item = DBSessionItem(
                    session_id=db_session.session_id,
                    item_path=item_data.item_path,
                    item_type=item_data.item_type
                )
                self.db.add(db_item)
            try:
                self.db.commit()
                self.db.refresh(db_session) # Refresh to load newly added items
            except IntegrityError:
                self.db.rollback()
                raise ConflictException(detail="One or more session items conflict with existing data.")

        return db_session

    def update_session(self, session_id: int, session_data: SessionUpdate) -> DBSession:
        """
        특정 ID의 세션 정보를 업데이트합니다.
        세션이 없으면 NotFoundException을 발생시킵니다.
        업데이트하려는 이름이 이미 다른 세션에 사용 중이면 ConflictException을 발생시킵니다.
        """
        db_session = self.get_session_by_id(session_id)

        if session_data.name is not None and session_data.name != db_session.name:
            existing_session = self.db.query(DBSession).filter(DBSession.name == session_data.name).first()
            if existing_session and existing_session.session_id != session_id:
                raise ConflictException(detail=f"Session with name '{session_data.name}' already exists for another session.")

        update_data = session_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_session, key, value)

        try:
            self.db.add(db_session)
            self.db.commit()
            self.db.refresh(db_session)
        except IntegrityError:
            self.db.rollback()
            raise ConflictException(detail=f"Session with name '{session_data.name}' already exists.")
        return db_session

    def delete_session(self, session_id: int):
        """
        특정 ID의 세션을 삭제합니다. 관련 항목 및 복구 로그도 함께 삭제됩니다.
        세션이 없으면 NotFoundException을 발생시킵니다.
        """
        db_session = self.get_session_by_id(session_id)
        self.db.delete(db_session)
        self.db.commit()

    def add_session_item(self, session_id: int, item_data: SessionItemCreate) -> DBSessionItem:
        """
        특정 세션에 항목을 추가합니다.
        세션이 없으면 NotFoundException을 발생시킵니다.
        동일한 세션에 동일한 경로의 항목이 이미 존재하면 ConflictException을 발생시킵니다.
        """
        db_session = self.get_session_by_id(session_id) # 세션 존재 여부 확인

        existing_item = self.db.query(DBSessionItem).filter(
            DBSessionItem.session_id == session_id,
            DBSessionItem.item_path == item_data.item_path
        ).first()
        if existing_item:
            raise ConflictException(detail=f"Item with path '{item_data.item_path}' already exists in session {session_id}.")

        db_item = DBSessionItem(
            session_id=session_id,
            item_path=item_data.item_path,
            item_type=item_data.item_type
        )
        self.db.add(db_item)
        try:
            self.db.commit()
            self.db.refresh(db_item)
        except IntegrityError:
            self.db.rollback()
            raise ConflictException(detail=f"Item with path '{item_data.item_path}' already exists in session {session_id}.")
        return db_item

    def create_recovery_log(self, session_id: int, log_data: RecoveryLogCreate) -> DBRecoveryLog:
        """
        특정 세션에 대한 복구 로그를 생성합니다.
        세션이 없으면 NotFoundException을 발생시킵니다.
        """
        db_session = self.get_session_by_id(session_id) # 세션 존재 여부 확인

        db_log = DBRecoveryLog(
            session_id=session_id,
            item_path=log_data.item_path,
            action_type=log_data.action_type,
            status=log_data.status,
            started_at=log_data.started_at if log_data.started_at else datetime.now(),
            completed_at=log_data.completed_at,
            error_message=log_data.error_message
        )
        self.db.add(db_log)
        try:
            self.db.commit()
            self.db.refresh(db_log)
        except IntegrityError as e:
            self.db.rollback()
            raise BadRequestException(detail=f"Failed to create recovery log: {e}")
        return db_log
</file>

<file path="backend/app/api/v1/__init__.py">
from fastapi import APIRouter
from app.api.v1.endpoints import session_router

# v1 API 라우터를 통합하는 메인 라우터
api_v1_router = APIRouter()
api_v1_router.include_router(session_router.router)
</file>

<file path="backend/app/api/v1/endpoints/__init__.py">
# 이 파일은 'endpoints' 디렉토리를 Python 패키지로 만들기 위해 존재합니다.
# 필요한 경우 이 파일에서 하위 엔드포인트 모듈을 임포트할 수 있습니다.
</file>

<file path="backend/app/api/v1/endpoints/session_router.py">
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.services.session_service import SessionService
from app.schemas.session import (
    SessionCreate, SessionUpdate, SessionResponse, SessionListResponse,
    SessionItemCreate, SessionItemResponse,
    RecoveryLogCreate, RecoveryLogResponse
)
from app.schemas.common import ErrorResponse

# APIRouter 인스턴스 생성
router = APIRouter(
    prefix="/sessions", # 모든 엔드포인트에 "/sessions" 접두사 적용
    tags=["Sessions"], # OpenAPI 문서에 표시될 태그
    responses={ # 공통 에러 응답 스키마 정의
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Not Found"},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Bad Request"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Conflict"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse, "description": "Validation Error"}
    }
)

@router.get(
    "/",
    response_model=SessionListResponse,
    summary="모든 세션 조회",
    description="시스템에 등록된 모든 세션 목록을 조회합니다."
)
def get_all_sessions(db: Session = Depends(get_db)):
    """
    모든 세션을 조회하고 목록으로 반환합니다.
    """
    service = SessionService(db)
    sessions = service.get_all_sessions()
    return SessionListResponse(sessions=sessions, total=len(sessions))

@router.post(
    "/",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="새로운 세션 생성",
    description="새로운 세션을 생성하고, 선택적으로 관련 항목들을 추가합니다."
)
def create_session(session_data: SessionCreate, db: Session = Depends(get_db)):
    """
    새로운 세션을 생성합니다.
    - `session_data`: 생성할 세션의 정보 (이름, 저장 경로, 압축/암호화 여부, 항목 목록).
    """
    service = SessionService(db)
    return service.create_session(session_data)

@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="ID로 세션 조회",
    description="고유 ID를 사용하여 특정 세션의 상세 정보를 조회합니다."
)
def get_session_by_id(session_id: int, db: Session = Depends(get_db)):
    """
    특정 ID의 세션을 조회합니다.
    - `session_id`: 조회할 세션의 고유 ID.
    """
    service = SessionService(db)
    return service.get_session_by_id(session_id)

@router.put(
    "/{session_id}",
    response_model=SessionResponse,
    summary="세션 업데이트",
    description="고유 ID를 사용하여 기존 세션의 정보를 업데이트합니다."
)
def update_session(session_id: int, session_data: SessionUpdate, db: Session = Depends(get_db)):
    """
    특정 ID의 세션 정보를 업데이트합니다.
    - `session_id`: 업데이트할 세션의 고유 ID.
    - `session_data`: 업데이트할 세션의 정보.
    """
    service = SessionService(db)
    return service.update_session(session_id, session_data)

@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="세션 삭제",
    description="고유 ID를 사용하여 세션을 삭제합니다. 관련 항목 및 복구 로그도 함께 삭제됩니다."
)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """
    특정 ID의 세션을 삭제합니다.
    - `session_id`: 삭제할 세션의 고유 ID.
    """
    service = SessionService(db)
    service.delete_session(session_id)
    return

@router.post(
    "/{session_id}/items",
    response_model=SessionItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="세션에 항목 추가",
    description="기존 세션에 새로운 항목(파일 또는 디렉토리)을 추가합니다."
)
def add_session_item(session_id: int, item_data: SessionItemCreate, db: Session = Depends(get_db)):
    """
    특정 세션에 항목을 추가합니다.
    - `session_id`: 항목을 추가할 세션의 고유 ID.
    - `item_data`: 추가할 항목의 정보 (경로, 타입).
    """
    service = SessionService(db)
    return service.add_session_item(session_id, item_data)

@router.post(
    "/{session_id}/recovery-logs",
    response_model=RecoveryLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="세션에 복구 로그 생성",
    description="기존 세션에 대한 새로운 복구 로그 항목을 생성합니다."
)
def create_recovery_log(session_id: int, log_data: RecoveryLogCreate, db: Session = Depends(get_db)):
    """
    특정 세션에 대한 복구 로그를 생성합니다.
    - `session_id`: 복구 로그를 생성할 세션의 고유 ID.
    - `log_data`: 생성할 복구 로그의 정보.
    """
    service = SessionService(db)
    return service.create_recovery_log(session_id, log_data)
</file>

<file path="backend/app/exceptions/handlers.py">
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.exceptions.custom_exceptions import NotFoundException, ConflictException, BadRequestException
from app.schemas.common import ErrorResponse

def add_exception_handlers(app: FastAPI):
    """
    FastAPI 애플리케이션에 전역 예외 핸들러를 등록합니다.
    """

    @app.exception_handler(NotFoundException)
    async def not_found_exception_handler(request: Request, exc: NotFoundException):
        """NotFoundException (HTTP 404) 처리 핸들러."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump()
        )

    @app.exception_handler(ConflictException)
    async def conflict_exception_handler(request: Request, exc: ConflictException):
        """ConflictException (HTTP 409) 처리 핸들러."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump()
        )

    @app.exception_handler(BadRequestException)
    async def bad_request_exception_handler(request: Request, exc: BadRequestException):
        """BadRequestException (HTTP 400) 처리 핸들러."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump()
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        FastAPI의 요청 유효성 검사 오류 (HTTP 422) 처리 핸들러.
        Pydantic 모델 유효성 검사 실패 시 발생합니다.
        """
        errors = []
        for error in exc.errors():
            loc = ".".join(map(str, error["loc"]))
            errors.append(f"{loc}: {error['msg']}")
        detail_message = "Validation Error: " + "; ".join(errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(detail=detail_message).model_dump()
        )

    @app.exception_handler(ValidationError) # Pydantic v2의 일반 ValidationError 처리
    async def pydantic_validation_error_handler(request: Request, exc: ValidationError):
        """
        Pydantic 모델의 일반 유효성 검사 오류 (HTTP 422) 처리 핸들러.
        RequestValidationError 외의 Pydantic 유효성 검사 오류를 처리합니다.
        """
        errors = []
        for error in exc.errors():
            loc = ".".join(map(str, error["loc"]))
            errors.append(f"{loc}: {error['msg']}")
        detail_message = "Pydantic Validation Error: " + "; ".join(errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(detail=detail_message).model_dump()
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """
        처리되지 않은 모든 예외를 처리하는 제네릭 핸들러 (HTTP 500).
        """
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(detail=f"An unexpected error occurred: {str(exc)}").model_dump()
        )
</file>

<file path="backend/main.py">
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
</file>