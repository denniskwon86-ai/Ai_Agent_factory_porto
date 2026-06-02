from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.schemas.user_schema import UserCreate, UserResponse
from backend.schemas.common_schema import ErrorResponse
from backend.services.user_service import user_service
from backend.core.exceptions import NotFoundException, ConflictException

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Not Found"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Conflict"}
    }
)

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(user: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user.
    """
    return user_service.create_user(db=db, user=user)

@router.get("/", response_model=List[UserResponse])
def read_users_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of users.
    """
    users = user_service.get_users(db, skip=skip, limit=limit)
    return users

@router.get("/{user_id}", response_model=UserResponse)
def read_user_endpoint(user_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single user by ID.
    """
    return user_service.get_user(db, user_id=user_id)