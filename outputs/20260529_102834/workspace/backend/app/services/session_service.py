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