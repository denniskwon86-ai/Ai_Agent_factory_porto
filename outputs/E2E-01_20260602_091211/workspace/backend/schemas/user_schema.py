from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str # e.g., "admin", "planner", "viewer"

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    user_id: int

    class Config:
        from_attributes = True # For Pydantic v2, use from_attributes=True instead of orm_mode=True