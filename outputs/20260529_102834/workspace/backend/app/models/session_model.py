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