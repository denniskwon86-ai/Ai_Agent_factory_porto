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