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