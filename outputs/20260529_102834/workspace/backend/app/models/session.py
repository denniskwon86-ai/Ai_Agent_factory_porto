from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum

# Enum for item_type
class ItemType(str, enum.Enum):
    FILE = "file"
    DIRECTORY = "directory"

# Enum for action_type
class RecoveryActionType(str, enum.Enum):
    BACKUP = "backup"
    RESTORE = "restore"
    DELETE = "delete"

# Enum for log status
class RecoveryLogStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DBSession(Base):
    __tablename__ = "sessions"

    session_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    storage_path = Column(String, nullable=False)
    compression = Column(Boolean, default=False)
    encryption = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    items = relationship("DBSessionItem", back_populates="session", cascade="all, delete-orphan")
    recovery_logs = relationship("DBRecoveryLog", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DBSession(id={self.session_id}, name='{self.name}')>"


class DBSessionItem(Base):
    __tablename__ = "session_items"

    session_item_id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.session_id"), nullable=False)
    item_path = Column(String, nullable=False)
    item_type = Column(Enum(ItemType), nullable=False) # 'file' or 'directory'

    # Relationship
    session = relationship("DBSession", back_populates="items")

    def __repr__(self):
        return f"<DBSessionItem(id={self.session_item_id}, path='{self.item_path}', type='{self.item_type}')>"


class DBRecoveryLog(Base):
    __tablename__ = "recovery_logs"

    log_id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.session_id"), nullable=False)
    item_path = Column(String, nullable=False)
    action_type = Column(Enum(RecoveryActionType), nullable=False) # 'backup', 'restore', 'delete'
    status = Column(Enum(RecoveryLogStatus), nullable=False) # 'pending', 'in_progress', 'completed', 'failed', 'cancelled'
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)

    # Relationship
    session = relationship("DBSession", back_populates="recovery_logs")

    def __repr__(self):
        return f"<DBRecoveryLog(id={self.log_id}, action='{self.action_type}', status='{self.status}')>"