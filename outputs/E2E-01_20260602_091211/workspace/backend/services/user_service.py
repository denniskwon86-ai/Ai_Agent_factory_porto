from sqlalchemy.orm import Session
from backend.models.user import User
from backend.schemas.user_schema import UserCreate
from backend.core.security import get_password_hash
from backend.core.exceptions import NotFoundException, ConflictException

class UserService:
    def get_user(self, db: Session, user_id: int) -> User:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise NotFoundException(detail=f"User with id {user_id} not found")
        return user

    def get_user_by_email(self, db: Session, email: str) -> User:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise NotFoundException(detail=f"User with email {email} not found")
        return user

    def get_users(self, db: Session, skip: int = 0, limit: int = 100) -> list[User]:
        return db.query(User).offset(skip).limit(limit).all()

    def create_user(self, db: Session, user: UserCreate) -> User:
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise ConflictException(detail=f"User with email {user.email} already exists")
        
        hashed_password = get_password_hash(user.password)
        db_user = User(
            username=user.username,
            email=user.email,
            hashed_password=hashed_password,
            role=user.role
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

user_service = UserService()